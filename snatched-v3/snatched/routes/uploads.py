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


def _staging_dir(data_dir: str, username: str, session_id: str) -> Path:
    """Return the staging directory for an upload session.

    Prefers /ramdisk for fast I/O; falls back to data_dir on disk.
    Also checks both locations for existing sessions (backwards compat).
    """
    ramdisk = Path("/ramdisk")
    if ramdisk.exists():
        ram_path = ramdisk / "staging" / username / session_id
        if ram_path.exists():
            return ram_path
        disk_path = Path(data_dir) / username / "staging" / session_id
        if disk_path.exists():
            return disk_path
        # New session — use ramdisk
        return ram_path
    return Path(data_dir) / username / "staging" / session_id


# ============================================================================
# Background archive function
# ============================================================================

async def _archive_upload(username: str, job_id: int, source_path: Path, metadata: dict):
    """Silently copy verified upload to admin archive on NAS.

    Fire-and-forget — if archive write fails (NAS offline, disk full),
    log a warning and continue. Never fail the user's job.
    """
    try:
        archive_base = Path("/archive")
        if not archive_base.exists():
            logger.warning("Archive directory /archive not mounted — skipping archive")
            return

        archive_dir = archive_base / username / str(job_id)
        await asyncio.to_thread(archive_dir.mkdir, parents=True, exist_ok=True)

        # Copy uploaded files from staging
        if source_path.is_dir():
            for part_file in sorted(source_path.glob("*.part")):
                await asyncio.to_thread(
                    shutil.copy2, str(part_file), str(archive_dir / part_file.name)
                )
        elif source_path.is_file():
            await asyncio.to_thread(
                shutil.copy2, str(source_path), str(archive_dir / "original.zip")
            )

        # Write manifest
        manifest = {
            **metadata,
            "archived_at": datetime.now(timezone.utc).isoformat(),
        }
        manifest_path = archive_dir / "manifest.json"
        await asyncio.to_thread(
            manifest_path.write_text,
            json.dumps(manifest, indent=2, default=str)
        )

        logger.info(f"Archived upload for {username}/job-{job_id} to {archive_dir}")

    except Exception as e:
        logger.warning(f"Failed to archive upload for {username}/job-{job_id}: {e}")


# ============================================================================
# Path validation helper
# ============================================================================

def _validate_relative_path(rel_path: str) -> bool:
    """Validate a client-provided relative path is safe.

    Prevents path traversal attacks, absolute paths, and other suspicious
    patterns that could allow writing outside the extraction directory.
    """
    if not rel_path:
        return False
    # No null bytes
    if "\x00" in rel_path:
        return False
    # No absolute paths
    if rel_path.startswith("/"):
        return False
    # No home-directory expansion
    if rel_path.startswith("~"):
        return False
    # No .. components (check each segment individually to catch foo/../bar)
    parts = rel_path.replace("\\", "/").split("/")
    if ".." in parts:
        return False
    # Reject empty segments that could cause confusion (e.g. foo//bar)
    if "" in parts[:-1]:  # trailing empty is ok for "dir/" but mid-empty is not
        return False
    return True


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

    # Upload type: "zip" (default, single/multi ZIP archives) or "folder" (raw folder files)
    upload_type = body.get("upload_type", "zip")
    if upload_type not in ("zip", "folder"):
        upload_type = "zip"

    # Parse processing options, lane selection, phase selection, and processing mode
    options = body.get("options", {})
    lanes = body.get("lanes", ["memories", "chats", "stories"])
    phases = body.get("phases", ["ingest", "match", "enrich", "export"])
    # processing_mode: 'speed_run' | 'power_user' | 'quick_rescue'
    # Handles both new format (top-level) and old format (nested in options)
    processing_mode = body.get("processing_mode", options.get("processing_mode", "speed_run"))
    if processing_mode not in ("speed_run", "power_user", "quick_rescue"):
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

    # Validate files and size limits
    upload_config = config.upload
    for f in files_manifest:
        filename = f.get("filename", "")

        if upload_type == "zip":
            # ZIP uploads: every file in the manifest must be a .zip archive
            if not filename.lower().endswith(".zip"):
                raise HTTPException(400, f"File '{filename}' is not a .zip archive")
        else:
            # Folder uploads: individual files (.jpg, .json, .mp4, etc.) — no extension check
            # Validate relative_path if provided
            rel_path = f.get("relative_path")
            if rel_path is not None and not _validate_relative_path(rel_path):
                raise HTTPException(
                    400,
                    f"File '{filename}' has an invalid relative_path: '{rel_path}'",
                )

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

    from snatched.tiers import get_tier_limits_async, get_system_config

    # Get or create user
    user_id = await get_or_create_user(pool, username)

    # --- Global concurrent job cap (circuit breaker) ---
    sys_cfg = await get_system_config(pool)
    max_global = sys_cfg.get("max_global_concurrent_jobs", 4)
    async with pool.acquire() as conn:
        global_active = await conn.fetchval(
            "SELECT COUNT(*) FROM processing_jobs WHERE status IN ('running', 'pending', 'queued')"
        )
    if global_active >= max_global:
        raise HTTPException(503, "System is at capacity. Please try again shortly.")

    # --- Storage quota from tier_plans (dynamic) ---
    async with pool.acquire() as conn:
        user_row = await conn.fetchrow(
            "SELECT tier FROM users WHERE id = $1", user_id
        )
        used_bytes = await conn.fetchval(
            """
            SELECT COALESCE(SUM(upload_size_bytes), 0)
            FROM processing_jobs
            WHERE user_id = $1 AND status NOT IN ('failed', 'cancelled')
            """,
            user_id,
        )

    tier = user_row["tier"] if user_row else "free"
    limits = await get_tier_limits_async(pool, tier)
    storage_gb = limits.get("storage_gb")
    if storage_gb is not None:
        quota_bytes = storage_gb * (1024 ** 3)
        if used_bytes + total_size > quota_bytes:
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

    # Create session token and directories — prefer ramdisk for fast I/O
    session_token = str(uuid.uuid4())
    session_dir = _staging_dir(str(config.server.data_dir), username, session_token)
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
        "job_group_id": body.get("job_group_id"),
        # Upload type: "zip" or "folder" — controls verification and reconstruction
        "upload_type": upload_type,
        # Original filenames for vault fingerprinting
        "original_filenames": [f.get("filename", "") for f in files_manifest],
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
            session_options,  # JSONB codec handles serialization
        )

        # Create upload_files records
        for idx, f in enumerate(files_manifest):
            # For folder uploads, preserve the relative_path so we can reconstruct
            # the directory tree once all files are verified.
            relative_path = f.get("relative_path", None)
            await conn.execute(
                """
                INSERT INTO upload_files
                    (session_id, file_index, filename, file_size, sha256_expected,
                     status, relative_path)
                VALUES ($1, $2, $3, $4, $5, 'pending', $6)
                """,
                session_id,
                idx,
                f.get("filename", ""),
                f.get("size", 0),
                f.get("sha256", ""),
                relative_path,
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

    # Stream chunk to staging (ramdisk preferred)
    staging_dir = _staging_dir(str(config.server.data_dir), username, session_id)
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

    # Reject partial writes — client must retry the chunk
    if bytes_written != chunk_size:
        logger.error(
            f"Partial chunk write: got {bytes_written} bytes, expected {chunk_size}. "
            f"Removing partial file {part_path}"
        )
        if part_path.exists():
            part_path.unlink()
        raise HTTPException(
            400,
            f"Chunk incomplete: received {bytes_written} of {chunk_size} bytes. Retry this chunk."
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
    staging_dir = _staging_dir(str(config.server.data_dir), username, session_id)
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
                    staging_dir_path = _staging_dir(str(config.server.data_dir), username, session_id)
                    staging_dir = str(staging_dir_path)

                    # Read processing options from session
                    raw_opts = session_row["options_json"]
                    if isinstance(raw_opts, str):
                        session_opts = json.loads(raw_opts)
                    else:
                        session_opts = raw_opts or {}
                    # Handle double-encoded JSON (string wrapping a JSON string)
                    if isinstance(session_opts, str):
                        session_opts = json.loads(session_opts)
                    job_lanes = session_opts.get("lanes", ["memories", "chats", "stories"])
                    # STORY-1: Ingest-only scan — phases_requested is ["ingest"] (not full pipeline)
                    job_phases = ["ingest"]
                    # Living Canvas: forward mode from upload session options (default: speed_run)
                    job_mode = session_opts.get("processing_mode", "speed_run")
                    if job_mode not in ("speed_run", "power_user", "quick_rescue"):
                        job_mode = "speed_run"

                    # ----------------------------------------------------------------
                    # Folder upload reconstruction
                    # For folder uploads, move each .part file to its original path
                    # inside an "extracted/" directory alongside staging.
                    # The pipeline receives extracted_dir instead of staging_dir.
                    # ----------------------------------------------------------------
                    upload_type = session_opts.get("upload_type", "zip")
                    pipeline_dir = staging_dir  # default: ZIP path, pipeline handles it

                    if upload_type == "folder":
                        extracted_dir = staging_dir_path.parent / "extracted" / session_id
                        extracted_dir.mkdir(parents=True, exist_ok=True)

                        # Fetch all file records within this transaction (lock already held)
                        file_records = await conn.fetch(
                            """
                            SELECT file_index, relative_path
                            FROM upload_files
                            WHERE session_id = $1
                            ORDER BY file_index
                            """,
                            session_db_id,
                        )

                        reconstructed = 0
                        for record in file_records:
                            source = staging_dir_path / f"file_{record['file_index']}.part"
                            rel_path = record["relative_path"]

                            if not rel_path:
                                logger.warning(
                                    f"Session {session_id} file {record['file_index']} "
                                    f"has no relative_path — skipping reconstruction"
                                )
                                continue

                            # Security: validate the path again server-side before use
                            if not _validate_relative_path(rel_path):
                                logger.warning(
                                    f"Skipping suspicious relative_path for file "
                                    f"{record['file_index']}: '{rel_path}'"
                                )
                                continue

                            # Extra safety: resolve and confirm target stays inside extracted_dir
                            target = (extracted_dir / rel_path).resolve()
                            try:
                                target.relative_to(extracted_dir.resolve())
                            except ValueError:
                                logger.warning(
                                    f"Path traversal detected after resolve for file "
                                    f"{record['file_index']}: '{rel_path}' -> {target}"
                                )
                                continue

                            if not source.exists():
                                logger.warning(
                                    f"Part file missing for file {record['file_index']}: {source}"
                                )
                                continue

                            target.parent.mkdir(parents=True, exist_ok=True)
                            await asyncio.to_thread(shutil.move, str(source), str(target))
                            reconstructed += 1

                        logger.info(
                            f"Reconstructed folder structure: {reconstructed}/{len(file_records)} "
                            f"files in {extracted_dir}"
                        )
                        pipeline_dir = str(extracted_dir)

                    job_group_id = session_opts.get("job_group_id")
                    job_id = await conn.fetchval(
                        """
                        INSERT INTO processing_jobs
                            (user_id, upload_filename, upload_size_bytes,
                             phases_requested, lanes_requested, processing_mode,
                             job_group_id, status)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, 'pending')
                        RETURNING id
                        """,
                        user_id,
                        # Use original ZIP filename for vault fingerprinting (fallback to session ID)
                        (session_opts.get("original_filenames", [None])[0]) or f"upload-{session_id}",
                        session_row["total_bytes"],
                        job_phases,
                        job_lanes,
                        job_mode,
                        job_group_id,
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

                    response["job_id"] = job_id
                    logger.info(f"Job {job_id} created for upload session {session_id}")

            # ── Post-transaction: enqueue job to ARQ worker ──
            # The transaction is now committed so the worker can read the job row.
            if response.get("job_id"):
                arq_pool = getattr(request.app.state, "arq_pool", None)
                if arq_pool:
                    # Enqueue to ARQ worker — durable Redis queue
                    await arq_pool.enqueue_job(
                        "process_job",
                        job_id,
                        username,
                        pipeline_dir,
                        _queue_name="snatched:default",
                    )
                    # Update status to 'queued' (worker will set 'running' when it picks up)
                    from snatched.db import update_job
                    await update_job(pool, job_id, status="queued")
                    logger.info("Job %d enqueued to ARQ for user %s", job_id, username)
                else:
                    # Fallback: direct execution if Redis unavailable
                    logger.warning("ARQ unavailable — running job %d directly", job_id)
                    task = asyncio.create_task(
                        run_job(pool, job_id, username, config, staging_dir=pipeline_dir)
                    )
                    task.add_done_callback(
                        lambda t, jid=job_id: t.exception() and logger.error(
                            "Job %d background task crashed: %s", jid, t.exception(),
                            exc_info=t.exception(),
                        )
                    )

                # Silent archive — fire-and-forget, never blocks the user
                try:
                    staging_path = staging_dir_path
                    archive_metadata = {
                        "job_id": job_id,
                        "username": username,
                        "session_id": session_id,
                        "total_bytes": session_row["total_bytes"],
                        "uploaded_at": datetime.now(timezone.utc).isoformat(),
                    }
                    archive_task = asyncio.create_task(
                        _archive_upload(username, job_id, staging_path, archive_metadata)
                    )
                    archive_task.add_done_callback(
                        lambda t, jid=job_id: t.exception() and logger.warning(
                            "Archive task for job %d failed: %s", jid, t.exception(),
                        )
                    )
                except Exception as e:
                    logger.warning(f"Failed to schedule archive task: {e}")

    except Exception as e:
        logger.error(f"Error in post-verify job creation for session {session_id}: {e}", exc_info=True)
        response["warning"] = "File verified but job creation failed. Please retry."
        # Mark session as failed so resume system doesn't show stale banner
        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE upload_sessions SET status = 'failed' WHERE session_token = $1",
                    session_id,
                )
        except Exception:
            pass

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

    # Delete staging directory (check both ramdisk and disk)
    staging_dir = _staging_dir(str(config.server.data_dir), username, session_id)
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

            # Delete staging directory (check both ramdisk and disk)
            staging_dir = _staging_dir(str(config.server.data_dir), username, session_id)
            if staging_dir.exists():
                shutil.rmtree(staging_dir)
                logger.info(f"Cleaned up expired session {session_id}")

            cleaned_count += 1

        except Exception as e:
            logger.error(f"Error cleaning up session {session_id}: {e}")

    return cleaned_count
