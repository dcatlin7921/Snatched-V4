"""Chunked multi-file upload system for Snapchat exports.

Handles resumable uploads of large ZIP files (2GB+) via 5MB chunks,
with server-side integrity verification and automatic pipeline trigger.
"""

import asyncio
import hashlib
import json
import logging
import os
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiofiles
import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from snatched.auth import get_current_user
from snatched.db import get_or_create_user
from snatched.jobs import create_processing_job, run_job

logger = logging.getLogger("snatched.routes.uploads")
router = APIRouter()


# ============================================================================
# 1. POST /api/upload/init — Initialize upload session
# ============================================================================

@router.post("/init", status_code=201)
async def init_upload(
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """Initialize a chunked upload session.

    Request body: {
        "files": [
            {"filename": "mydata~1.zip", "size": 2147483648, "sha256": "a1b2c3..."},
            ...
        ]
    }

    Response (201): {
        "session_id": "uuid...",
        "expires_at": "2026-02-25T14:30:00Z",
        "chunk_size": 5242880,
        "files": [
            {"index": 0, "filename": "...", "status": "pending", "bytes_received": 0},
            ...
        ]
    }
    """
    config = request.app.state.config
    pool = request.app.state.db_pool

    # Parse request body
    try:
        body = await request.json()
        files_manifest = body.get("files", [])
    except Exception as e:
        raise HTTPException(400, f"Invalid request body: {e}")

    if not files_manifest:
        raise HTTPException(400, "No files in request")

    # Parse processing options, lane selection, phase selection, and processing mode
    options = body.get("options", {})
    lanes = body.get("lanes", ["memories", "chats", "stories"])
    phases = body.get("phases", ["ingest", "match", "enrich", "export"])
    # processing_mode: 'speed_run' (fast, sane defaults) or 'power_user' (all knobs exposed)
    # Handles both new format (top-level) and old format (nested in options)
    processing_mode = body.get("processing_mode", options.get("processing_mode", "speed_run"))
    if processing_mode not in ("speed_run", "power_user"):
        processing_mode = "speed_run"

    # Validate lanes
    valid_lanes = {"memories", "chats", "stories"}
    lanes = [l for l in lanes if l in valid_lanes]
    if not lanes:
        lanes = ["memories", "chats", "stories"]

    # Validate phases (ingest is always required)
    valid_phases = {"ingest", "match", "enrich", "export"}
    phases = [p for p in phases if p in valid_phases]
    if "ingest" not in phases:
        phases.insert(0, "ingest")

    # Validate all files are .zip and within size limits
    upload_config = config.upload
    for f in files_manifest:
        filename = f.get("filename", "")
        if not filename.lower().endswith(".zip"):
            raise HTTPException(400, f"File '{filename}' is not a .zip archive")

        size = f.get("size", 0)
        if size > upload_config.max_file_bytes:
            raise HTTPException(
                413,
                f"File '{filename}' exceeds {upload_config.max_file_bytes} byte limit",
            )

    total_size = sum(f.get("size", 0) for f in files_manifest)
    if total_size > upload_config.max_total_bytes:
        raise HTTPException(
            413,
            f"Total upload size {total_size} exceeds {upload_config.max_total_bytes} byte limit",
        )

    # Get or create user
    user_id = await get_or_create_user(pool, username)

    # Check quota
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT u.storage_quota_bytes,
                   COALESCE(SUM(pj.upload_size_bytes), 0) AS used_bytes
            FROM users u
            LEFT JOIN processing_jobs pj ON u.id = pj.user_id
                AND pj.status NOT IN ('failed', 'cancelled')
            WHERE u.id = $1
            GROUP BY u.id, u.storage_quota_bytes
            """,
            user_id,
        )

    if row["used_bytes"] + total_size > row["storage_quota_bytes"]:
        raise HTTPException(507, "Storage quota exceeded")

    # Check max concurrent sessions per user
    async with pool.acquire() as conn:
        concurrent = await conn.fetchval(
            """
            SELECT COUNT(*) FROM upload_sessions
            WHERE user_id = $1 AND status = 'active'
            """,
            user_id,
        )

    if concurrent >= upload_config.max_concurrent_sessions:
        raise HTTPException(
            429,
            f"Maximum {upload_config.max_concurrent_sessions} concurrent upload(s) per user",
        )

    # Create session token and directories
    session_token = str(uuid.uuid4())
    session_dir = Path(str(config.server.data_dir)) / username / "staging" / session_token
    os.makedirs(session_dir, mode=0o750, exist_ok=True)

    # Create .part files (pre-allocated)
    for idx, f in enumerate(files_manifest):
        part_path = session_dir / f"file_{idx}.part"
        async with aiofiles.open(str(part_path), "wb") as pf:
            # Pre-allocate empty file
            await pf.write(b"")

    # Create session in database
    expires_at = datetime.now(tz=timezone.utc) + timedelta(
        hours=upload_config.session_ttl_hours
    )

    # Build session options (processing prefs + lanes)
    gps_window = int(options.get("gps_window_seconds", 300))
    gps_window = max(30, min(1800, gps_window))  # Clamp to valid range

    session_options = {
        "burn_overlays": bool(options.get("burn_overlays", True)),
        "dark_mode_pngs": bool(options.get("dark_mode_pngs", False)),
        "exif_enabled": bool(options.get("exif_enabled", True)),
        "xmp_enabled": bool(options.get("xmp_enabled", False)),
        "gps_window_seconds": gps_window,
        "lanes": lanes,
        "phases": phases,
        # Living Canvas: persisted so verify endpoint can forward to job creation
        "processing_mode": processing_mode,
    }

    async with pool.acquire() as conn:
        session_id = await conn.fetchval(
            """
            INSERT INTO upload_sessions
                (user_id, session_token, file_count, total_bytes, expires_at, status, options_json)
            VALUES ($1, $2, $3, $4, $5, 'active', $6::JSONB)
            RETURNING id
            """,
            user_id,
            session_token,
            len(files_manifest),
            total_size,
            expires_at,
            json.dumps(session_options),
        )

        # Create upload_files records
        for idx, f in enumerate(files_manifest):
            await conn.execute(
                """
                INSERT INTO upload_files
                    (session_id, file_index, filename, file_size, sha256_expected, status)
                VALUES ($1, $2, $3, $4, $5, 'pending')
                """,
                session_id,
                idx,
                f.get("filename", ""),
                f.get("size", 0),
                f.get("sha256", ""),
            )

    # Only update preferences if options were explicitly provided
    if options:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_preferences
                    (user_id, burn_overlays, dark_mode_pngs, exif_enabled, xmp_enabled, gps_window_seconds)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (user_id) DO UPDATE SET
                    burn_overlays = EXCLUDED.burn_overlays,
                    dark_mode_pngs = EXCLUDED.dark_mode_pngs,
                    exif_enabled = EXCLUDED.exif_enabled,
                    xmp_enabled = EXCLUDED.xmp_enabled,
                    gps_window_seconds = EXCLUDED.gps_window_seconds,
                    updated_at = NOW()
                """,
                user_id,
                session_options["burn_overlays"],
                session_options["dark_mode_pngs"],
                session_options["exif_enabled"],
                session_options["xmp_enabled"],
                session_options["gps_window_seconds"],
            )

    logger.info(
        f"Created upload session {session_token} for user {username} with {len(files_manifest)} files"
    )

    return {
        "session_id": session_token,
        "expires_at": expires_at.isoformat(),
        "chunk_size": upload_config.chunk_size_bytes,
        "files": [
            {
                "index": idx,
                "filename": f.get("filename", ""),
                "status": "pending",
                "bytes_received": 0,
            }
            for idx, f in enumerate(files_manifest)
        ],
    }


# ============================================================================
# 2. PUT /api/upload/chunk/{session_id}/{file_index} — Receive chunk
# ============================================================================

@router.put("/chunk/{session_id}/{file_index}")
async def receive_chunk(
    session_id: str,
    file_index: int,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """Upload a single chunk to a file within a session.

    Headers:
        X-Chunk-Offset: byte offset within the file (must match bytes_received)
        Content-Length: chunk size in bytes
        Content-Type: application/octet-stream

    Response (200): {
        "file_index": 0,
        "bytes_received": 5242880,
        "file_size": 2147483648,
        "complete": false
    }
    """
    config = request.app.state.config
    pool = request.app.state.db_pool

    # Get chunk offset from header
    chunk_offset = request.headers.get("X-Chunk-Offset")
    if chunk_offset is None:
        raise HTTPException(400, "Missing X-Chunk-Offset header")

    try:
        chunk_offset = int(chunk_offset)
    except ValueError:
        raise HTTPException(400, "Invalid X-Chunk-Offset (must be integer)")

    # Verify session exists and belongs to user
    async with pool.acquire() as conn:
        session_row = await conn.fetchrow(
            """
            SELECT us.id, us.user_id, us.expires_at, us.status
            FROM upload_sessions us
            JOIN users u ON us.user_id = u.id
            WHERE us.session_token = $1 AND u.username = $2
            """,
            session_id,
            username,
        )

    if not session_row:
        raise HTTPException(404, "Upload session not found")

    if session_row["status"] != "active":
        raise HTTPException(
            400, f"Upload session is {session_row['status']}, not active"
        )

    if datetime.now(tz=timezone.utc) > session_row["expires_at"]:
        raise HTTPException(410, "Upload session has expired")

    session_db_id = session_row["id"]

    # Verify file_index is in range
    async with pool.acquire() as conn:
        file_row = await conn.fetchrow(
            """
            SELECT uf.id, uf.file_size, uf.bytes_received, uf.status
            FROM upload_files uf
            WHERE uf.session_id = $1 AND uf.file_index = $2
            """,
            session_db_id,
            file_index,
        )

    if not file_row:
        raise HTTPException(
            404, f"File {file_index} not found in session {session_id}"
        )

    if file_row["status"] == "complete":
        raise HTTPException(409, f"File {file_index} is already complete")

    if file_row["status"] == "failed":
        raise HTTPException(409, f"File {file_index} upload failed (retry session)")

    # Validate offset matches bytes_received (no gaps or duplicates)
    if chunk_offset != file_row["bytes_received"]:
        raise HTTPException(
            400,
            f"Invalid offset {chunk_offset}: expected {file_row['bytes_received']} (bytes already received)",
        )

    # Stream chunk directly to disk
    user_data_dir = Path(str(config.server.data_dir)) / username
    staging_dir = user_data_dir / "staging" / session_id
    part_path = staging_dir / f"file_{file_index}.part"

    if not part_path.exists():
        raise HTTPException(500, f"Part file {part_path} does not exist")

    # Read Content-Length
    content_length = request.headers.get("Content-Length")
    if not content_length:
        raise HTTPException(400, "Missing Content-Length header")

    try:
        chunk_size = int(content_length)
    except ValueError:
        raise HTTPException(400, "Invalid Content-Length")

    # Validate chunk won't overflow file boundary
    if chunk_offset + chunk_size > file_row["file_size"]:
        raise HTTPException(
            400,
            f"Chunk overflows file boundary: offset {chunk_offset} + size {chunk_size} > file_size {file_row['file_size']}",
        )

    # Stream request body to disk
    bytes_written = 0
    try:
        async with aiofiles.open(str(part_path), "r+b") as pf:
            await pf.seek(chunk_offset)
            await pf.truncate()  # Remove leftover bytes from any failed retry
            async for chunk_data in request.stream():
                if chunk_data:
                    await pf.write(chunk_data)
                    bytes_written += len(chunk_data)
    except Exception as e:
        logger.error(f"Error writing chunk to {part_path}: {e}")
        raise HTTPException(500, f"Failed to write chunk to disk: {e}")

    # Validate we wrote the expected amount
    if bytes_written != chunk_size:
        logger.warning(
            f"Bytes written ({bytes_written}) != Content-Length ({chunk_size})"
        )

    new_bytes_received = file_row["bytes_received"] + bytes_written

    # Update progress in database
    async with pool.acquire() as conn:
        # Transition file status to 'uploading' on first chunk
        if chunk_offset == 0:
            await conn.execute(
                "UPDATE upload_files SET status = 'uploading' WHERE id = $1 AND status = 'pending'",
                file_row["id"],
            )

        await conn.execute(
            "UPDATE upload_files SET bytes_received = $1 WHERE id = $2",
            new_bytes_received,
            file_row["id"],
        )
        await conn.execute(
            """
            UPDATE upload_sessions
            SET bytes_received = bytes_received + $1
            WHERE id = $2
            """,
            bytes_written,
            session_db_id,
        )

    is_complete = new_bytes_received == file_row["file_size"]

    logger.info(
        f"Received {bytes_written} bytes for session {session_id} file {file_index} "
        f"(total: {new_bytes_received}/{file_row['file_size']})"
    )

    return {
        "file_index": file_index,
        "bytes_received": new_bytes_received,
        "file_size": file_row["file_size"],
        "complete": is_complete,
    }


# ============================================================================
# 3. POST /api/upload/verify/{session_id}/{file_index} — Verify integrity
# ============================================================================

@router.post("/verify/{session_id}/{file_index}")
async def verify_file(
    session_id: str,
    file_index: int,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """Verify SHA-256 integrity of an uploaded file.

    Computes hash of the assembled .part file and compares to expected value.

    Response (200): {
        "file_index": 0,
        "verified": true,
        "sha256": "a1b2c3...",
        "job_id": 42  (optional, only if this was the last file)
    }

    Response (409): {
        "file_index": 0,
        "verified": false,
        "expected": "a1b2c3...",
        "actual": "x9y8z7...",
        "action": "re-upload"
    }
    """
    config = request.app.state.config
    pool = request.app.state.db_pool

    # Verify session
    async with pool.acquire() as conn:
        session_row = await conn.fetchrow(
            """
            SELECT us.id, us.user_id, us.expires_at, us.status, us.file_count,
                   us.total_bytes, us.options_json
            FROM upload_sessions us
            JOIN users u ON us.user_id = u.id
            WHERE us.session_token = $1 AND u.username = $2
            """,
            session_id,
            username,
        )

    if not session_row:
        raise HTTPException(404, "Upload session not found")

    # Check session is still active
    if session_row["status"] != "active":
        raise HTTPException(
            400, f"Upload session is {session_row['status']}, not active"
        )

    session_db_id = session_row["id"]

    # Verify file exists
    async with pool.acquire() as conn:
        file_row = await conn.fetchrow(
            """
            SELECT uf.id, uf.file_size, uf.bytes_received,
                   uf.sha256_expected, uf.sha256_actual, uf.status
            FROM upload_files uf
            WHERE uf.session_id = $1 AND uf.file_index = $2
            """,
            session_db_id,
            file_index,
        )

    if not file_row:
        raise HTTPException(404, f"File {file_index} not found")

    if file_row["status"] == "complete":
        return {
            "file_index": file_index,
            "verified": True,
            "sha256": file_row["sha256_actual"] or file_row["sha256_expected"],
        }

    # Ensure all chunks received
    if file_row["bytes_received"] != file_row["file_size"]:
        raise HTTPException(
            400,
            f"File {file_index} incomplete: {file_row['bytes_received']} / {file_row['file_size']} bytes",
        )

    # Mark file as verifying
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE upload_files SET status = 'verifying' WHERE id = $1",
            file_row["id"],
        )

    # Compute SHA-256 of assembled file (in thread pool to not block event loop)
    user_data_dir = Path(str(config.server.data_dir)) / username
    staging_dir = user_data_dir / "staging" / session_id
    part_path = staging_dir / f"file_{file_index}.part"

    loop = asyncio.get_running_loop()

    def _compute_sha256():
        """Compute SHA-256 of file on disk (synchronous)."""
        sha256_hash = hashlib.sha256()
        try:
            with open(part_path, "rb") as f:
                while chunk := f.read(65536):  # 64KB chunks
                    sha256_hash.update(chunk)
            return sha256_hash.hexdigest()
        except Exception as e:
            raise IOError(f"Failed to compute hash: {e}")

    try:
        actual_sha256 = await loop.run_in_executor(None, _compute_sha256)
    except Exception as e:
        logger.error(f"Error computing hash for file {file_index}: {e}")
        raise HTTPException(500, f"Failed to verify file integrity: {e}")

    expected_sha256 = file_row["sha256_expected"]

    # Compare hashes (skip verification if client didn't provide hash — large files)
    if expected_sha256 and actual_sha256 != expected_sha256:
        logger.warning(
            f"SHA-256 mismatch for session {session_id} file {file_index}: "
            f"expected {expected_sha256}, got {actual_sha256}"
        )

        # Mark file as failed in database
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE upload_files SET status = 'failed' WHERE id = $1",
                file_row["id"],
            )

        return JSONResponse(
            status_code=409,
            content={
                "file_index": file_index,
                "verified": False,
                "expected": expected_sha256,
                "actual": actual_sha256,
                "action": "re-upload",
            },
        )

    if not expected_sha256:
        logger.info(f"File {file_index} hash skipped (client did not provide hash), server hash: {actual_sha256}")

    # Mark file as complete
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE upload_files
            SET status = 'complete', sha256_actual = $1, completed_at = NOW()
            WHERE id = $2
            """,
            actual_sha256,
            file_row["id"],
        )

    logger.info(f"File {file_index} verified successfully: {actual_sha256}")

    response = {
        "file_index": file_index,
        "verified": True,
        "sha256": actual_sha256,
    }

    # Check if this was the last file to complete (advisory lock prevents race)
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Advisory lock on session ID prevents two concurrent verify calls
                # from both seeing "all complete" and creating duplicate jobs
                await conn.execute(
                    "SELECT pg_advisory_xact_lock($1)", session_db_id
                )

                completed_count = await conn.fetchval(
                    """
                    SELECT COUNT(*) FROM upload_files
                    WHERE session_id = $1 AND status = 'complete'
                    """,
                    session_db_id,
                )

                # Re-check session status inside the lock (another verify may have already triggered)
                current_status = await conn.fetchval(
                    "SELECT status FROM upload_sessions WHERE id = $1",
                    session_db_id,
                )

                if completed_count == session_row["file_count"] and current_status == "active":
                    # All files complete — create processing job with INGEST ONLY
                    logger.info(f"All files in session {session_id} verified. Creating job for ingest scan...")

                    user_id = session_row["user_id"]
                    staging_dir = str(
                        Path(str(config.server.data_dir)) / username / "staging" / session_id
                    )

                    # Read processing options from session
                    raw_opts = session_row["options_json"]
                    if isinstance(raw_opts, str):
                        session_opts = json.loads(raw_opts)
                    else:
                        session_opts = raw_opts or {}
                    job_lanes = session_opts.get("lanes", ["memories", "chats", "stories"])
                    # STORY-1: Ingest-only scan — phases_requested is ["ingest"] (not full pipeline)
                    job_phases = ["ingest"]
                    # Living Canvas: forward mode from upload session options (default: speed_run)
                    job_mode = session_opts.get("processing_mode", "speed_run")
                    if job_mode not in ("speed_run", "power_user"):
                        job_mode = "speed_run"

                    job_id = await conn.fetchval(
                        """
                        INSERT INTO processing_jobs
                            (user_id, upload_filename, upload_size_bytes,
                             phases_requested, lanes_requested, processing_mode, status)
                        VALUES ($1, $2, $3, $4, $5, $6, 'pending')
                        RETURNING id
                        """,
                        user_id,
                        f"upload-{session_id}",
                        session_row["total_bytes"],
                        job_phases,
                        job_lanes,
                        job_mode,
                    )
                    # Note: SQL mirrors jobs.py:create_processing_job() — keep in sync
                    logger.info(f"Created job {job_id} for session {session_id}")

                    # Mark session as completed and link job
                    await conn.execute(
                        """
                        UPDATE upload_sessions
                        SET status = 'completed', completed_at = NOW(), job_id = $1
                        WHERE id = $2
                        """,
                        job_id,
                        session_db_id,
                    )

                    # Launch job as background task (with staging_dir so pipeline finds files)
                    # Job will set status to 'scanned' when ingest completes (see jobs.py)
                    asyncio.create_task(
                        run_job(pool, job_id, username, config, staging_dir=staging_dir)
                    )

                    response["job_id"] = job_id
                    logger.info(f"Job {job_id} created for upload session {session_id}")

    except Exception as e:
        logger.error(f"Error in post-verify job creation for session {session_id}: {e}", exc_info=True)
        response["warning"] = "File verified but job creation failed. Please retry."

    return response


# ============================================================================
# 4. GET /api/upload/status/{session_id} — Resume state
# ============================================================================

@router.get("/status/{session_id}")
async def upload_status(
    session_id: str,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """Get current state of upload session (for resume).

    Response (200): {
        "session_id": "uuid...",
        "status": "active",
        "expires_at": "2026-02-25T14:30:00Z",
        "total_bytes": 5368709120,
        "bytes_received": 3221225472,
        "percent": 60.0,
        "files": [
            {
                "index": 0,
                "filename": "...",
                "status": "complete",
                "bytes_received": 2147483648,
                "file_size": 2147483648
            },
            ...
        ]
    }
    """
    pool = request.app.state.db_pool

    # Verify session belongs to user
    async with pool.acquire() as conn:
        session_row = await conn.fetchrow(
            """
            SELECT us.id, us.session_token, us.status, us.total_bytes, us.bytes_received,
                   us.expires_at, us.file_count
            FROM upload_sessions us
            JOIN users u ON us.user_id = u.id
            WHERE us.session_token = $1 AND u.username = $2
            """,
            session_id,
            username,
        )

    if not session_row:
        raise HTTPException(404, "Upload session not found")

    # Get file details
    async with pool.acquire() as conn:
        file_rows = await conn.fetch(
            """
            SELECT file_index, filename, status, bytes_received, file_size
            FROM upload_files
            WHERE session_id = $1
            ORDER BY file_index ASC
            """,
            session_row["id"],
        )

    files = [
        {
            "index": row["file_index"],
            "filename": row["filename"],
            "status": row["status"],
            "bytes_received": row["bytes_received"],
            "file_size": row["file_size"],
        }
        for row in file_rows
    ]

    percent = (
        100.0
        if session_row["total_bytes"] == 0
        else (session_row["bytes_received"] / session_row["total_bytes"]) * 100.0
    )

    return {
        "session_id": session_id,
        "status": session_row["status"],
        "expires_at": session_row["expires_at"].isoformat(),
        "total_bytes": session_row["total_bytes"],
        "bytes_received": session_row["bytes_received"],
        "percent": round(percent, 1),
        "files": files,
    }


# ============================================================================
# 5. DELETE /api/upload/abort/{session_id} — Cancel upload
# ============================================================================

@router.delete("/abort/{session_id}", status_code=204)
async def abort_upload(
    session_id: str,
    request: Request,
    username: str = Depends(get_current_user),
) -> None:
    """Cancel an upload session and clean up files.

    Response: 204 No Content
    """
    config = request.app.state.config
    pool = request.app.state.db_pool

    # Verify session belongs to user
    async with pool.acquire() as conn:
        session_row = await conn.fetchrow(
            """
            SELECT us.id
            FROM upload_sessions us
            JOIN users u ON us.user_id = u.id
            WHERE us.session_token = $1 AND u.username = $2
            """,
            session_id,
            username,
        )

    if not session_row:
        raise HTTPException(404, "Upload session not found")

    # Mark as aborted in database
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE upload_sessions SET status = 'aborted' WHERE id = $1",
            session_row["id"],
        )

    # Delete staging directory
    user_data_dir = Path(str(config.server.data_dir)) / username
    staging_dir = user_data_dir / "staging" / session_id

    if staging_dir.exists():
        try:
            shutil.rmtree(staging_dir)
            logger.info(f"Deleted staging directory {staging_dir}")
        except Exception as e:
            logger.error(f"Failed to delete staging directory {staging_dir}: {e}")

    logger.info(f"Aborted upload session {session_id}")
    return None


# ============================================================================
# Background cleanup function
# ============================================================================

async def cleanup_expired_sessions(pool: asyncpg.Pool, config) -> int:
    """Find and clean up expired upload sessions.

    Returns:
        Number of sessions cleaned up.
    """
    # Find expired sessions
    async with pool.acquire() as conn:
        expired_rows = await conn.fetch(
            """
            SELECT id, user_id, session_token
            FROM upload_sessions
            WHERE status = 'active' AND expires_at < NOW()
            """
        )

    if not expired_rows:
        logger.debug("No expired upload sessions to clean up")
        return 0

    cleaned_count = 0

    for row in expired_rows:
        session_id = row["session_token"]
        user_id = row["user_id"]

        try:
            # Get username for path construction
            async with pool.acquire() as conn:
                username = await conn.fetchval(
                    "SELECT username FROM users WHERE id = $1", user_id
                )

            # Mark as expired
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE upload_sessions SET status = 'expired' WHERE id = $1",
                    row["id"],
                )

            # Delete staging directory
            user_data_dir = Path(str(config.server.data_dir)) / username
            staging_dir = user_data_dir / "staging" / session_id

            if staging_dir.exists():
                shutil.rmtree(staging_dir)
                logger.info(f"Cleaned up expired session {session_id}")

            cleaned_count += 1

        except Exception as e:
            logger.error(f"Error cleaning up session {session_id}: {e}")

    return cleaned_count
