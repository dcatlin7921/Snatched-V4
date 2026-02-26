"""JSON API endpoints for the Snatched v3 web application.

All endpoints except /api/health require authentication.
"""

import asyncio
import io
import json
import logging
import os
import re
import sqlite3
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from snatched.auth import get_current_user
from snatched.jobs import cancel_job, create_processing_job, job_stream, run_job, _make_progress_cb
from snatched.routes import uploads as uploads_module
from snatched import tags as tags_module

logger = logging.getLogger("snatched.routes.api")
router = APIRouter()

# Include chunked upload routes under /upload prefix
router.include_router(uploads_module.router, prefix="/upload", tags=["upload"])


@router.get("/jobs")
async def list_jobs(
    request: Request,
    status: str | None = Query(None),
    username: str = Depends(get_current_user),
) -> list[dict]:
    """GET /api/jobs — List authenticated user's jobs.

    Optional query param: ?status=running
    """
    pool = request.app.state.db_pool

    if status:
        # Support comma-separated statuses: ?status=completed,failed,cancelled
        statuses = [s.strip() for s in status.split(",")]
        placeholders = ", ".join(f"${i+2}" for i in range(len(statuses)))
        query = f"""
            SELECT pj.id, pj.status, pj.progress_pct, pj.current_phase,
                   pj.upload_filename, pj.created_at, pj.completed_at,
                   pj.error_message, pj.stats_json, pj.upload_size_bytes
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE u.username = $1 AND pj.status IN ({placeholders})
            ORDER BY pj.created_at DESC
        """
        params = [username] + statuses
    else:
        query = """
            SELECT pj.id, pj.status, pj.progress_pct, pj.current_phase,
                   pj.upload_filename, pj.created_at, pj.completed_at,
                   pj.error_message, pj.stats_json, pj.upload_size_bytes
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE u.username = $1
            ORDER BY pj.created_at DESC
        """
        params = [username]

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)

    return [dict(row) for row in rows]


@router.get("/jobs/html")
async def list_jobs_html(
    request: Request,
    status: str | None = Query(None),
    username: str = Depends(get_current_user),
) -> HTMLResponse:
    """GET /api/jobs/html — HTML fragment of job cards for htmx swap."""
    pool = request.app.state.db_pool
    templates = request.app.state.templates

    if status:
        # Support comma-separated statuses: ?status=completed,failed,cancelled
        statuses = [s.strip() for s in status.split(",")]
        placeholders = ", ".join(f"${i+2}" for i in range(len(statuses)))
        query = f"""
            SELECT pj.id, pj.status, pj.progress_pct, pj.current_phase,
                   pj.upload_filename, pj.created_at, pj.completed_at,
                   pj.error_message, pj.stats_json, pj.upload_size_bytes,
                   pj.retention_expires_at, u.tier
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE u.username = $1 AND pj.status IN ({placeholders})
            ORDER BY pj.created_at DESC
        """
        params = [username] + statuses
    else:
        query = """
            SELECT pj.id, pj.status, pj.progress_pct, pj.current_phase,
                   pj.upload_filename, pj.created_at, pj.completed_at,
                   pj.error_message, pj.stats_json, pj.upload_size_bytes,
                   pj.retention_expires_at, u.tier
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE u.username = $1
            ORDER BY pj.created_at DESC
        """
        params = [username]

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)

    from datetime import datetime, timezone
    jobs = []
    for row in rows:
        j = dict(row)
        # Compute retention_days_remaining for template
        if j.get("retention_expires_at"):
            delta = j["retention_expires_at"] - datetime.now(timezone.utc)
            j["retention_days_remaining"] = max(0, delta.days)
        else:
            j["retention_days_remaining"] = None
        jobs.append(j)
    return templates.TemplateResponse("_job_cards.html", {"request": request, "jobs": jobs})


@router.get("/jobs/{job_id}")
async def job_detail(
    job_id: int,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """GET /api/jobs/{job_id} — Job detail with full stats.

    Verifies ownership (404 if not found or belongs to another user).
    """
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT pj.*
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )

    if not row:
        raise HTTPException(404, "Job not found")

    return dict(row)


@router.get("/jobs/{job_id}/stream")
async def stream_job(
    job_id: int,
    request: Request,
    username: str = Depends(get_current_user),
):
    """GET /api/jobs/{job_id}/stream — SSE progress stream.

    Verifies ownership before streaming.
    """
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        owner = await conn.fetchval(
            """
            SELECT u.username FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1
            """,
            job_id,
        )

    if owner != username:
        raise HTTPException(403, "Access denied")

    return StreamingResponse(
        job_stream(pool, job_id),
        media_type="text/event-stream",
    )


@router.post("/jobs/{job_id}/cancel")
async def cancel(
    job_id: int,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """POST /api/jobs/{job_id}/cancel — Request job cancellation."""
    pool = request.app.state.db_pool

    # Verify ownership
    async with pool.acquire() as conn:
        owner = await conn.fetchval(
            """
            SELECT u.username FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1
            """,
            job_id,
        )

    if owner != username:
        raise HTTPException(403, "Access denied")

    cancelled = await cancel_job(pool, job_id)
    if cancelled:
        return {"cancelled": True}
    return {"cancelled": False, "reason": "Job already in terminal state"}


@router.delete("/jobs/{job_id}")
async def delete_job(
    job_id: int,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """DELETE /api/jobs/{job_id} — Delete a terminal job and its data."""
    import shutil
    pool = request.app.state.db_pool
    config = request.app.state.config

    async with pool.acquire() as conn:
        job = await conn.fetchrow(
            "SELECT id, status, user_id FROM processing_jobs WHERE id=$1",
            job_id,
        )

    if not job:
        raise HTTPException(404, "Job not found")

    # Verify ownership
    async with pool.acquire() as conn:
        user_id = await conn.fetchval(
            "SELECT id FROM users WHERE username=$1", username
        )
    if job["user_id"] != user_id:
        raise HTTPException(403, "Not your job")

    # Only allow deletion of terminal or paused jobs
    if job["status"] not in ("completed", "failed", "cancelled", "scanned", "matched", "enriched"):
        raise HTTPException(
            409, f"Cannot delete job in '{job['status']}' state. Cancel it first."
        )

    # Delete events, then job
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM job_events WHERE job_id=$1", job_id)
        # Detach upload sessions referencing this job
        await conn.execute(
            "UPDATE upload_sessions SET job_id=NULL WHERE job_id=$1", job_id
        )
        await conn.execute("DELETE FROM processing_jobs WHERE id=$1", job_id)

    # Clean up user data directory
    data_dir = Path(str(config.server.data_dir)) / username
    if data_dir.exists():
        # Remove proc.db and extracted dir if they exist
        for item in ["proc.db", "extracted"]:
            target = data_dir / item
            if target.is_file():
                target.unlink()
            elif target.is_dir():
                shutil.rmtree(target)

    logger.info(f"Deleted job {job_id} for user {username}")
    return {"deleted": True, "job_id": job_id}


@router.post("/jobs/{job_id}/retry")
async def retry_job(
    job_id: int,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """POST /api/jobs/{job_id}/retry — Retry a failed job with the same parameters."""
    pool = request.app.state.db_pool

    # Verify ownership and check status
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT pj.id, pj.status, pj.phases_requested, pj.lanes_requested,
                   pj.upload_filename, pj.upload_size_bytes, pj.processing_mode,
                   u.id as user_id
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )

    if not row:
        raise HTTPException(404, "Job not found")

    if row["status"] not in ("failed", "cancelled"):
        raise HTTPException(400, f"Job is not in a retryable state (current: {row['status']})")

    new_job_id = await create_processing_job(
        pool,
        user_id=row["user_id"],
        upload_filename=row["upload_filename"],
        upload_size_bytes=row["upload_size_bytes"] or 0,
        phases_requested=row["phases_requested"] or [],
        lanes_requested=row["lanes_requested"] or [],
        processing_mode=row["processing_mode"] or "speed_run",
    )

    asyncio.create_task(
        run_job(pool, new_job_id, username, request.app.state.config)
    )

    logger.info(f"Retry of job {job_id} started as new job {new_job_id} for user '{username}'")
    return {"new_job_id": new_job_id}


@router.post("/jobs/{job_id}/reprocess")
async def reprocess(
    job_id: int,
    request: Request,
    phases: list[str] = Query(...),
    lanes: list[str] = Query(...),
    username: str = Depends(get_current_user),
) -> dict:
    """POST /api/jobs/{job_id}/reprocess — Trigger selective reprocessing."""
    pool = request.app.state.db_pool

    # Verify ownership
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT pj.id, u.id as user_id FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )

    if not row:
        raise HTTPException(404, "Job not found")

    new_job_id = await create_processing_job(
        pool,
        user_id=row["user_id"],
        upload_filename=f"reprocess-of-{job_id}",
        upload_size_bytes=0,
        phases_requested=phases,
        lanes_requested=lanes,
    )

    asyncio.create_task(
        run_job(pool, new_job_id, username, request.app.state.config)
    )

    return {"new_job_id": new_job_id, "message": "Reprocessing started"}


@router.get("/jobs/{job_id}/report")
async def job_report(
    job_id: int,
    request: Request,
    format: str = Query("json"),
    username: str = Depends(get_current_user),
):
    """GET /api/jobs/{job_id}/report?format=json|csv — Download job stats as file."""
    import csv as csv_mod

    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT pj.*
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )

    if not row:
        raise HTTPException(404, "Job not found")

    job = dict(row)
    stats = job.get("stats_json") or {}

    if format == "csv":
        output = io.StringIO()
        writer = csv_mod.writer(output)
        writer.writerow(["metric", "value"])
        writer.writerow(["job_id", job_id])
        writer.writerow(["status", job.get("status", "")])
        writer.writerow(["upload_filename", job.get("upload_filename", "")])
        for k, v in stats.items():
            if isinstance(v, dict):
                for sk, sv in v.items():
                    writer.writerow([f"{k}.{sk}", sv])
            else:
                writer.writerow([k, v])
        content = output.getvalue()
        return StreamingResponse(
            iter([content]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=snatched-job-{job_id}-report.csv"},
        )
    else:
        report = {
            "job_id": job_id,
            "status": job.get("status"),
            "upload_filename": job.get("upload_filename"),
            "created_at": str(job.get("created_at", "")),
            "completed_at": str(job.get("completed_at", "")),
            "stats": stats,
        }
        return StreamingResponse(
            iter([__import__("json").dumps(report, indent=2)]),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=snatched-job-{job_id}-report.json"},
        )


@router.get("/summary")
async def user_summary(
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """GET /api/summary — Aggregate pipeline metrics for authenticated user."""
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) as total_jobs,
                COUNT(*) FILTER (WHERE pj.status = 'completed') as completed_jobs,
                COALESCE(SUM(pj.upload_size_bytes), 0) as total_storage_bytes
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE u.username = $1
            """,
            username,
        )

    return {
        "total_jobs": row["total_jobs"],
        "completed_jobs": row["completed_jobs"],
        "total_storage_bytes": row["total_storage_bytes"],
    }


@router.get("/assets")
async def list_assets(
    job_id: int = Query(...),
    page: int = Query(1),
    request: Request = None,
    username: str = Depends(get_current_user),
) -> dict:
    """GET /api/assets?job_id=42&page=1 — Paginated asset list from user's SQLite."""
    config = request.app.state.config
    page_size = 50

    # Verify job ownership
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        owner = await conn.fetchval(
            """
            SELECT u.username FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1
            """,
            job_id,
        )

    if owner != username:
        raise HTTPException(403, "Access denied")

    # Read from per-user SQLite
    import sqlite3

    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    if not db_path.exists():
        return {"items": [], "total": 0, "page": page, "page_size": page_size, "total_pages": 0}

    loop = asyncio.get_running_loop()
    def _query_assets():
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        total = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
        total_pages = (total + page_size - 1) // page_size
        offset = (page - 1) * page_size
        rows = conn.execute(
            "SELECT * FROM assets ORDER BY id LIMIT ? OFFSET ?",
            (page_size, offset),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows], total, total_pages

    items, total, total_pages = await loop.run_in_executor(None, _query_assets)

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


@router.get("/matches")
async def list_matches(
    job_id: int = Query(...),
    page: int = Query(1),
    request: Request = None,
    username: str = Depends(get_current_user),
) -> dict:
    """GET /api/matches?job_id=42&page=1 — Match list with confidence scores."""
    config = request.app.state.config
    page_size = 50

    # Verify job ownership
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        owner = await conn.fetchval(
            """
            SELECT u.username FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1
            """,
            job_id,
        )

    if owner != username:
        raise HTTPException(403, "Access denied")

    import sqlite3

    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    if not db_path.exists():
        return {"items": [], "total": 0, "page": page, "page_size": page_size, "total_pages": 0}

    loop = asyncio.get_running_loop()
    def _query_matches():
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        total = conn.execute("SELECT COUNT(*) FROM matches WHERE is_best = 1").fetchone()[0]
        total_pages = (total + page_size - 1) // page_size
        offset = (page - 1) * page_size
        rows = conn.execute(
            """
            SELECT m.*, a.path, a.asset_type
            FROM matches m
            JOIN assets a ON m.asset_id = a.id
            WHERE m.is_best = 1
            ORDER BY m.confidence DESC, m.id
            LIMIT ? OFFSET ?
            """,
            (page_size, offset),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows], total, total_pages

    items, total, total_pages = await loop.run_in_executor(None, _query_matches)

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


@router.get("/download/tree")
async def download_tree(
    job_id: int = Query(...),
    request: Request = None,
    username: str = Depends(get_current_user),
) -> HTMLResponse:
    """GET /api/download/tree?job_id=42 — Return HTML file tree for HTMX swap.

    Scans the user's output directory and returns a nested file listing.
    """
    config = request.app.state.config
    pool = request.app.state.db_pool

    # Verify job ownership
    async with pool.acquire() as conn:
        owner = await conn.fetchval(
            """
            SELECT u.username FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1
            """,
            job_id,
        )

    if owner != username:
        raise HTTPException(403, "Access denied")

    output_dir = Path(str(config.server.data_dir)) / username / "output"
    if not output_dir.exists():
        return HTMLResponse("<p>No output files yet.</p>")

    # Build HTML file tree
    lines = ['<div class="file-tree">']
    for dirpath, dirnames, filenames in os.walk(str(output_dir)):
        dirnames.sort()
        rel_dir = os.path.relpath(dirpath, str(output_dir))
        if rel_dir == ".":
            rel_dir = ""

        if rel_dir:
            indent = rel_dir.count(os.sep)
            lines.append(
                f'<div class="file-item folder" style="margin-left:{indent}rem">'
                f'{os.path.basename(dirpath)}/</div>'
            )

        for fname in sorted(filenames):
            rel_path = os.path.join(rel_dir, fname) if rel_dir else fname
            indent = rel_path.count(os.sep)
            download_url = f"/api/download/{rel_path}"
            lines.append(
                f'<div class="file-item" style="margin-left:{indent + 1}rem">'
                f'<a href="{download_url}">{fname}</a></div>'
            )

    lines.append("</div>")
    return HTMLResponse("\n".join(lines))


@router.get("/download/all")
async def download_all(
    job_id: int = Query(...),
    request: Request = None,
    username: str = Depends(get_current_user),
):
    """GET /api/download/all?job_id=42 — Download all output files as ZIP."""
    config = request.app.state.config
    pool = request.app.state.db_pool

    # Verify job ownership
    async with pool.acquire() as conn:
        owner = await conn.fetchval(
            """
            SELECT u.username FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1
            """,
            job_id,
        )

    if owner != username:
        raise HTTPException(403, "Access denied")

    output_dir = Path(str(config.server.data_dir)) / username / "output"
    if not output_dir.exists():
        raise HTTPException(404, "No output files found")

    # Build ZIP in memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, _, filenames in os.walk(str(output_dir)):
            for fname in filenames:
                full_path = os.path.join(dirpath, fname)
                arcname = os.path.relpath(full_path, str(output_dir))
                zf.write(full_path, arcname)

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=snatched-job-{job_id}.zip"},
    )


@router.get("/matches/html")
async def list_matches_html(
    job_id: int = Query(...),
    page: int = Query(1),
    request: Request = None,
    username: str = Depends(get_current_user),
) -> HTMLResponse:
    """GET /api/matches/html — HTML fragment of match rows for htmx swap."""
    config = request.app.state.config
    templates = request.app.state.templates
    page_size = 50

    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        owner = await conn.fetchval(
            "SELECT u.username FROM processing_jobs pj JOIN users u ON pj.user_id = u.id WHERE pj.id = $1",
            job_id,
        )
    if owner != username:
        raise HTTPException(403, "Access denied")

    import sqlite3
    from pathlib import Path

    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    if not db_path.exists():
        return templates.TemplateResponse("_match_rows.html", {
            "request": request, "items": [], "total": 0, "page": page, "total_pages": 0, "job_id": job_id
        })

    loop = asyncio.get_running_loop()
    def _query_matches():
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        total = conn.execute("SELECT COUNT(*) FROM matches WHERE is_best = 1").fetchone()[0]
        total_pages = (total + page_size - 1) // page_size
        offset = (page - 1) * page_size
        rows = conn.execute(
            "SELECT m.*, a.path, a.asset_type FROM matches m JOIN assets a ON m.asset_id = a.id WHERE m.is_best = 1 ORDER BY m.confidence DESC, m.id LIMIT ? OFFSET ?",
            (page_size, offset),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows], total, total_pages

    items, total, total_pages = await loop.run_in_executor(None, _query_matches)
    return templates.TemplateResponse("_match_rows.html", {
        "request": request, "items": items, "total": total, "page": page, "total_pages": total_pages, "job_id": job_id
    })


@router.get("/assets/html")
async def list_assets_html(
    job_id: int = Query(...),
    page: int = Query(1),
    request: Request = None,
    username: str = Depends(get_current_user),
) -> HTMLResponse:
    """GET /api/assets/html — HTML fragment of asset rows for htmx swap."""
    config = request.app.state.config
    templates = request.app.state.templates
    page_size = 50

    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        owner = await conn.fetchval(
            "SELECT u.username FROM processing_jobs pj JOIN users u ON pj.user_id = u.id WHERE pj.id = $1",
            job_id,
        )
    if owner != username:
        raise HTTPException(403, "Access denied")

    import sqlite3
    from pathlib import Path

    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    if not db_path.exists():
        return templates.TemplateResponse("_asset_rows.html", {
            "request": request, "items": [], "total": 0, "page": page, "total_pages": 0, "job_id": job_id
        })

    loop = asyncio.get_running_loop()
    def _query_assets():
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        total = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
        total_pages = (total + page_size - 1) // page_size
        offset = (page - 1) * page_size
        rows = conn.execute("SELECT * FROM assets ORDER BY id LIMIT ? OFFSET ?", (page_size, offset)).fetchall()
        conn.close()
        return [dict(r) for r in rows], total, total_pages

    items, total, total_pages = await loop.run_in_executor(None, _query_assets)
    return templates.TemplateResponse("_asset_rows.html", {
        "request": request, "items": items, "total": total, "page": page, "total_pages": total_pages, "job_id": job_id
    })


class TagEditsBody(BaseModel):
    edits: dict[str, str | None]


@router.get("/assets/{asset_id}/tags")
async def get_asset_tags(
    asset_id: int,
    job_id: int = Query(...),
    request: Request = None,
    username: str = Depends(get_current_user),
) -> dict:
    """GET /api/assets/{asset_id}/tags?job_id=42 — Return full tag dict as JSON.

    Verifies job ownership, resolves the output file, reads all EXIF/XMP tags.
    """
    config = request.app.state.config
    pool = request.app.state.db_pool

    # Verify job ownership
    async with pool.acquire() as conn:
        owner = await conn.fetchval(
            "SELECT u.username FROM processing_jobs pj JOIN users u ON pj.user_id = u.id WHERE pj.id = $1",
            job_id,
        )
    if owner != username:
        raise HTTPException(403, "Access denied")

    # Load asset from SQLite
    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    if not db_path.exists():
        raise HTTPException(404, "Asset database not found")

    loop = asyncio.get_running_loop()

    def _get_asset():
        conn_sq = sqlite3.connect(str(db_path))
        conn_sq.row_factory = sqlite3.Row
        row = conn_sq.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
        conn_sq.close()
        return dict(row) if row else None

    asset = await loop.run_in_executor(None, _get_asset)
    if not asset:
        raise HTTPException(404, "Asset not found")

    output_path = asset.get("output_path") or asset.get("path") or ""
    if output_path and not os.path.isabs(output_path):
        output_dir = Path(str(config.server.data_dir)) / username / "output"
        full_output_path = str(output_dir / output_path)
    else:
        full_output_path = output_path

    if not full_output_path or not os.path.isfile(full_output_path):
        raise HTTPException(404, "Output file not found")

    flat_tags = await tags_module.read_tags(full_output_path)
    return {"asset_id": asset_id, "file_path": full_output_path, "tags": flat_tags}


@router.put("/assets/{asset_id}/tags")
async def update_asset_tags(
    asset_id: int,
    body: TagEditsBody,
    job_id: int = Query(...),
    request: Request = None,
    username: str = Depends(get_current_user),
) -> dict:
    """PUT /api/assets/{asset_id}/tags?job_id=42 — Apply tag edits to output file.

    Accepts {"edits": {"EXIF:DateTimeOriginal": "2024:07:04 14:30:00", ...}}.
    Reads old values first (audit trail), calls write_tags(), logs each change
    to the tag_edits PostgreSQL table.
    """
    config = request.app.state.config
    pool = request.app.state.db_pool

    if not body.edits:
        raise HTTPException(400, "No edits provided")

    # Verify job ownership and get user_id
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT pj.id, u.id as user_id, u.username
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )
    if not row:
        raise HTTPException(403, "Access denied")

    user_id = row["user_id"]

    # Load asset from SQLite
    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    if not db_path.exists():
        raise HTTPException(404, "Asset database not found")

    loop = asyncio.get_running_loop()

    def _get_asset():
        conn_sq = sqlite3.connect(str(db_path))
        conn_sq.row_factory = sqlite3.Row
        r = conn_sq.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
        conn_sq.close()
        return dict(r) if r else None

    asset = await loop.run_in_executor(None, _get_asset)
    if not asset:
        raise HTTPException(404, "Asset not found")

    output_path = asset.get("output_path") or asset.get("path") or ""
    if output_path and not os.path.isabs(output_path):
        output_dir = Path(str(config.server.data_dir)) / username / "output"
        full_output_path = str(output_dir / output_path)
    else:
        full_output_path = output_path

    if not full_output_path or not os.path.isfile(full_output_path):
        raise HTTPException(404, "Output file not found")

    # Read old values before editing (audit trail)
    tag_names = list(body.edits.keys())
    old_values = await tags_module.read_tags_before_edit(full_output_path, tag_names)

    # Apply edits via exiftool
    write_result = await tags_module.write_tags(full_output_path, body.edits)

    if not write_result["success"]:
        raise HTTPException(500, f"exiftool write failed: {write_result['message']}")

    # Log each changed field to PostgreSQL tag_edits table
    async with pool.acquire() as conn:
        for field_name, new_value in body.edits.items():
            old_value = old_values.get(field_name)
            # Only log if value actually changed (or if old was None and new is set)
            if str(old_value) != str(new_value):
                await conn.execute(
                    """
                    INSERT INTO tag_edits
                        (user_id, job_id, asset_id, file_path, field_name, old_value, new_value, edit_type)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, 'manual')
                    """,
                    user_id, job_id, asset_id,
                    full_output_path, field_name,
                    str(old_value) if old_value is not None else None,
                    str(new_value) if new_value is not None else None,
                )

    logger.info(
        f"Tag edit: user='{username}' job={job_id} asset={asset_id} "
        f"fields={list(body.edits.keys())} result={write_result['message']}"
    )

    # Return updated tags after write
    updated_tags = await tags_module.read_tags(full_output_path)
    return {
        "success": True,
        "message": write_result["message"],
        "warnings": write_result.get("warnings", []),
        "tags": updated_tags,
    }


@router.get("/download/{path:path}")
async def download_file(
    path: str,
    request: Request,
    username: str = Depends(get_current_user),
):
    """GET /api/download/{path} — Stream a processed output file.

    Path traversal protection: resolves path relative to /data/{username}/output/
    and verifies it stays within that directory.
    """
    config = request.app.state.config
    user_output_dir = os.path.realpath(
        str(Path(str(config.server.data_dir)) / username / "output")
    )
    target = os.path.realpath(os.path.join(user_output_dir, path))

    if not target.startswith(user_output_dir + os.sep):
        raise HTTPException(400, "Path traversal attempt blocked")

    if not os.path.isfile(target):
        raise HTTPException(404, "File not found")

    return FileResponse(target)


class PreferencesBody(BaseModel):
    burn_overlays: bool = True
    dark_mode_pngs: bool = False
    exif_enabled: bool = True
    xmp_enabled: bool = False
    gps_window_seconds: int = Field(default=300, ge=30, le=1800)


@router.post("/preferences")
async def save_preferences(
    body: PreferencesBody,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """POST /api/preferences — Upsert user processing preferences."""
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        user_id = await conn.fetchval(
            "SELECT id FROM users WHERE username = $1",
            username,
        )
        if not user_id:
            raise HTTPException(404, "User not found")

        await conn.execute(
            """
            INSERT INTO user_preferences
                (user_id, burn_overlays, dark_mode_pngs, exif_enabled, xmp_enabled, gps_window_seconds)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (user_id) DO UPDATE SET
                burn_overlays       = EXCLUDED.burn_overlays,
                dark_mode_pngs      = EXCLUDED.dark_mode_pngs,
                exif_enabled        = EXCLUDED.exif_enabled,
                xmp_enabled         = EXCLUDED.xmp_enabled,
                gps_window_seconds  = EXCLUDED.gps_window_seconds,
                updated_at          = NOW()
            """,
            user_id,
            body.burn_overlays,
            body.dark_mode_pngs,
            body.exif_enabled,
            body.xmp_enabled,
            body.gps_window_seconds,
        )

    logger.info(f"Preferences saved for user '{username}'")
    return {"saved": True}


@router.get("/jobs/{job_id}/match-stats")
async def match_stats(
    job_id: int,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """GET /api/jobs/{job_id}/match-stats — Match strategy breakdown from SQLite."""
    config = request.app.state.config
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        owner = await conn.fetchval(
            "SELECT u.username FROM processing_jobs pj JOIN users u ON pj.user_id = u.id WHERE pj.id = $1",
            job_id,
        )
    if owner != username:
        raise HTTPException(403, "Access denied")

    import sqlite3

    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    if not db_path.exists():
        return {"strategies": [], "histogram": [], "total_matched": 0, "total_assets": 0}

    loop = asyncio.get_running_loop()
    def _query_stats():
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        strategies = conn.execute(
            """
            SELECT strategy, COUNT(*) as count, AVG(confidence) as avg_confidence
            FROM matches WHERE is_best = 1
            GROUP BY strategy ORDER BY count DESC
            """
        ).fetchall()
        total_matched = conn.execute("SELECT COUNT(*) FROM matches WHERE is_best = 1").fetchone()[0]
        total_assets = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
        histogram = conn.execute(
            """
            SELECT CAST(confidence * 10 AS INTEGER) as bucket, COUNT(*) as count
            FROM matches WHERE is_best = 1
            GROUP BY bucket ORDER BY bucket
            """
        ).fetchall()
        conn.close()
        return [dict(r) for r in strategies], [dict(r) for r in histogram], total_matched, total_assets

    strategies, histogram, total_matched, total_assets = await loop.run_in_executor(None, _query_stats)
    return {
        "strategies": strategies,
        "histogram": histogram,
        "total_matched": total_matched,
        "total_assets": total_assets,
    }


@router.get("/jobs/{job_id}/match-stats/html")
async def match_stats_html(
    job_id: int,
    request: Request,
    username: str = Depends(get_current_user),
) -> HTMLResponse:
    """GET /api/jobs/{job_id}/match-stats/html — HTML fragment for htmx swap."""
    data = await match_stats(job_id, request, username)
    templates = request.app.state.templates
    return templates.TemplateResponse("_match_stats.html", {
        "request": request,
        "strategies": data["strategies"],
        "histogram": data["histogram"],
        "total_matched": data["total_matched"],
        "total_assets": data["total_assets"],
    })



class BatchTagEditsBody(BaseModel):
    asset_ids: list[int]
    edits: dict[str, str | None]  # tag_name -> new_value (None to delete)


@router.post("/assets/batch-tags/preview")
async def batch_edit_preview(
    body: BatchTagEditsBody,
    job_id: int = Query(...),
    request: Request = None,
    username: str = Depends(get_current_user),
) -> dict:
    """POST /api/assets/batch-tags/preview?job_id=42 -- Preview batch tag edit.

    Returns the count of matched assets and a sample (up to 5) of current tag
    values without applying any changes.
    """
    import sqlite3

    config = request.app.state.config
    pool = request.app.state.db_pool

    # Verify job ownership
    async with pool.acquire() as conn:
        owner = await conn.fetchval(
            """
            SELECT u.username FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1
            """,
            job_id,
        )

    if owner != username:
        raise HTTPException(403, "Access denied")

    if not body.asset_ids:
        return {"count": 0, "sample_values": {}}

    if not body.edits:
        return {"count": len(body.asset_ids), "sample_values": {}}

    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    if not db_path.exists():
        raise HTTPException(404, "No asset database found")

    loop = asyncio.get_running_loop()

    def _lookup_paths(asset_ids: list[int]) -> list[dict]:
        conn_sq = sqlite3.connect(str(db_path))
        conn_sq.row_factory = sqlite3.Row
        placeholders = ",".join("?" * len(asset_ids))
        rows = conn_sq.execute(
            f"SELECT id, output_path, path FROM assets WHERE id IN ({placeholders})",
            asset_ids,
        ).fetchall()
        conn_sq.close()
        return [dict(r) for r in rows]

    assets = await loop.run_in_executor(None, _lookup_paths, body.asset_ids)

    from snatched import tags as tags_module

    tag_names = list(body.edits.keys())
    output_dir = Path(str(config.server.data_dir)) / username / "output"
    sample_values: dict[str, list] = {tag: [] for tag in tag_names}

    for asset in assets[:5]:  # sample up to 5 assets
        raw_path = asset.get("output_path") or asset.get("path") or ""
        if not raw_path:
            continue
        full_path = raw_path if os.path.isabs(raw_path) else str(output_dir / raw_path)
        if not os.path.isfile(full_path):
            continue
        try:
            old_vals = await tags_module.read_tags_before_edit(full_path, tag_names)
            for tag in tag_names:
                val = old_vals.get(tag)
                if val is not None:
                    sample_values[tag].append(val)
        except Exception as exc:
            logger.warning(f"Preview read failed for asset {asset['id']}: {exc}")

    return {
        "count": len(assets),
        "sample_values": sample_values,
    }


@router.post("/assets/batch-tags")
async def batch_edit_tags(
    body: BatchTagEditsBody,
    job_id: int = Query(...),
    request: Request = None,
    username: str = Depends(get_current_user),
) -> dict:
    """POST /api/assets/batch-tags?job_id=42 -- Apply tag edits to a set of assets.

    Processes assets sequentially to avoid exiftool conflicts.
    Logs every field change individually to the tag_edits audit table (edit_type='batch').

    Returns: {total, succeeded, failed, errors: [{asset_id, error}]}
    """
    import sqlite3

    from snatched import tags as tags_module

    config = request.app.state.config
    pool = request.app.state.db_pool

    # Verify job ownership and get user_id
    async with pool.acquire() as conn:
        job_row = await conn.fetchrow(
            """
            SELECT u.username, u.id as user_id
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1
            """,
            job_id,
        )

    if not job_row or job_row["username"] != username:
        raise HTTPException(403, "Access denied")

    user_id: int = job_row["user_id"]

    if not body.asset_ids:
        return {"total": 0, "succeeded": 0, "failed": 0, "errors": []}

    if not body.edits:
        n = len(body.asset_ids)
        return {"total": n, "succeeded": n, "failed": 0, "errors": []}

    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    if not db_path.exists():
        raise HTTPException(404, "No asset database found")

    loop = asyncio.get_running_loop()

    def _lookup_assets(asset_ids: list[int]) -> list[dict]:
        conn_sq = sqlite3.connect(str(db_path))
        conn_sq.row_factory = sqlite3.Row
        placeholders = ",".join("?" * len(asset_ids))
        rows = conn_sq.execute(
            f"SELECT id, output_path, path FROM assets WHERE id IN ({placeholders})",
            asset_ids,
        ).fetchall()
        conn_sq.close()
        return [dict(r) for r in rows]

    assets = await loop.run_in_executor(None, _lookup_assets, body.asset_ids)
    asset_map = {a["id"]: a for a in assets}

    tag_names = list(body.edits.keys())
    output_dir = Path(str(config.server.data_dir)) / username / "output"
    succeeded = 0
    failed = 0
    errors: list[dict] = []

    # Process sequentially to avoid exiftool conflicts
    for asset_id in body.asset_ids:
        asset = asset_map.get(asset_id)
        if not asset:
            failed += 1
            errors.append({"asset_id": asset_id, "error": "Asset not found in database"})
            continue

        raw_path = asset.get("output_path") or asset.get("path") or ""
        if not raw_path:
            failed += 1
            errors.append({"asset_id": asset_id, "error": "Asset has no output path"})
            continue

        full_path = raw_path if os.path.isabs(raw_path) else str(output_dir / raw_path)

        if not os.path.isfile(full_path):
            failed += 1
            errors.append({"asset_id": asset_id, "error": f"File not found: {full_path}"})
            continue

        # Capture old values before edit (audit trail)
        try:
            old_values = await tags_module.read_tags_before_edit(full_path, tag_names)
        except Exception as exc:
            logger.warning(f"Could not read old tags for asset {asset_id}: {exc}")
            old_values = {tag: None for tag in tag_names}

        # Apply edits via exiftool
        try:
            write_result = await tags_module.write_tags(full_path, body.edits)
        except Exception as exc:
            failed += 1
            errors.append({"asset_id": asset_id, "error": str(exc)})
            logger.error(f"write_tags raised for asset {asset_id}: {exc}")
            continue

        if not write_result.get("success"):
            failed += 1
            errors.append({
                "asset_id": asset_id,
                "error": write_result.get("message", "Unknown write error"),
            })
            continue

        # Log each changed field individually to PostgreSQL tag_edits
        async with pool.acquire() as conn:
            for field_name, new_value in body.edits.items():
                old_value = old_values.get(field_name)
                # Skip unchanged values
                if str(old_value) == str(new_value):
                    continue
                try:
                    await conn.execute(
                        """
                        INSERT INTO tag_edits
                            (user_id, job_id, asset_id, file_path,
                             field_name, old_value, new_value, edit_type)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, 'batch')
                        """,
                        user_id, job_id, asset_id, full_path, field_name,
                        str(old_value) if old_value is not None else None,
                        str(new_value) if new_value is not None else None,
                    )
                except Exception as exc:
                    logger.error(
                        f"Failed to log tag_edit for asset {asset_id} "
                        f"field {field_name}: {exc}"
                    )

        succeeded += 1
        if write_result.get("warnings"):
            logger.info(
                f"Batch tag warnings asset={asset_id}: {write_result['warnings']}"
            )

    logger.info(
        f"Batch tag edit job={job_id} user='{username}': "
        f"{succeeded}/{len(body.asset_ids)} succeeded, {failed} failed"
    )

    return {
        "total": len(body.asset_ids),
        "succeeded": succeeded,
        "failed": failed,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Tag Preset endpoints (Feature #12)
# ---------------------------------------------------------------------------

class PresetBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    tags_json: dict[str, str] = Field(default_factory=dict)


@router.get("/presets")
async def list_presets(
    request: Request,
    username: str = Depends(get_current_user),
) -> list[dict]:
    """GET /api/presets — List built-in presets plus the authenticated user's custom presets."""
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, user_id, name, description, tags_json, is_builtin, created_at, updated_at
            FROM tag_presets
            WHERE is_builtin = true
               OR user_id = (SELECT id FROM users WHERE username = $1)
            ORDER BY is_builtin DESC, name ASC
            """,
            username,
        )

    result = []
    for row in rows:
        d = dict(row)
        tags = d.get("tags_json") or {}
        if isinstance(tags, str):
            tags = json.loads(tags)
        d["tags_json"] = tags
        d["tag_count"] = len(tags)
        result.append(d)

    return result


@router.post("/presets")
async def create_preset(
    body: PresetBody,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """POST /api/presets — Create a new custom preset for the authenticated user."""
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        user_id = await conn.fetchval(
            "SELECT id FROM users WHERE username = $1", username
        )
        if not user_id:
            raise HTTPException(404, "User not found")

        tags_str = json.dumps(body.tags_json)
        row = await conn.fetchrow(
            """
            INSERT INTO tag_presets (user_id, name, description, tags_json, is_builtin)
            VALUES ($1, $2, $3, $4::JSONB, false)
            RETURNING id, user_id, name, description, tags_json, is_builtin, created_at, updated_at
            """,
            user_id,
            body.name,
            body.description,
            tags_str,
        )

    d = dict(row)
    tags = d.get("tags_json") or {}
    if isinstance(tags, str):
        tags = json.loads(tags)
    d["tags_json"] = tags
    d["tag_count"] = len(tags)
    logger.info(f"Created preset '{body.name}' (id={d['id']}) for user '{username}'")
    return d


@router.put("/presets/{preset_id}")
async def update_preset(
    preset_id: int,
    body: PresetBody,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """PUT /api/presets/{preset_id} — Update a user-owned custom preset."""
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            """
            SELECT tp.id, tp.is_builtin, u.username as owner
            FROM tag_presets tp
            LEFT JOIN users u ON tp.user_id = u.id
            WHERE tp.id = $1
            """,
            preset_id,
        )

        if not existing:
            raise HTTPException(404, "Preset not found")
        if existing["is_builtin"]:
            raise HTTPException(403, "Built-in presets cannot be modified")
        if existing["owner"] != username:
            raise HTTPException(403, "Access denied")

        tags_str = json.dumps(body.tags_json)
        row = await conn.fetchrow(
            """
            UPDATE tag_presets
            SET name = $1, description = $2, tags_json = $3::JSONB, updated_at = NOW()
            WHERE id = $4
            RETURNING id, user_id, name, description, tags_json, is_builtin, created_at, updated_at
            """,
            body.name,
            body.description,
            tags_str,
            preset_id,
        )

    d = dict(row)
    tags = d.get("tags_json") or {}
    if isinstance(tags, str):
        tags = json.loads(tags)
    d["tags_json"] = tags
    d["tag_count"] = len(tags)
    logger.info(f"Updated preset {preset_id} for user '{username}'")
    return d


@router.delete("/presets/{preset_id}")
async def delete_preset(
    preset_id: int,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """DELETE /api/presets/{preset_id} — Delete a user-owned custom preset."""
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            """
            SELECT tp.id, tp.is_builtin, u.username as owner
            FROM tag_presets tp
            LEFT JOIN users u ON tp.user_id = u.id
            WHERE tp.id = $1
            """,
            preset_id,
        )

        if not existing:
            raise HTTPException(404, "Preset not found")
        if existing["is_builtin"]:
            raise HTTPException(403, "Built-in presets cannot be deleted")
        if existing["owner"] != username:
            raise HTTPException(403, "Access denied")

        await conn.execute("DELETE FROM tag_presets WHERE id = $1", preset_id)

    logger.info(f"Deleted preset {preset_id} for user '{username}'")
    return {"deleted": True, "preset_id": preset_id}


@router.post("/assets/{asset_id}/apply-preset")
async def apply_preset(
    asset_id: int,
    request: Request,
    preset_id: int = Query(...),
    job_id: int = Query(...),
    username: str = Depends(get_current_user),
) -> dict:
    """POST /api/assets/{asset_id}/apply-preset?preset_id=X&job_id=Y

    Applies a tag preset to a single asset.
    Verifies job ownership and preset access, looks up output_path from
    per-user SQLite, writes tags via exiftool, logs to tag_edits.
    """
    config = request.app.state.config
    pool = request.app.state.db_pool

    # 1. Verify job ownership
    async with pool.acquire() as conn:
        owner = await conn.fetchval(
            """
            SELECT u.username FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1
            """,
            job_id,
        )
    if owner != username:
        raise HTTPException(403, "Access denied to job")

    # 2. Load preset (must be builtin or owned by user)
    async with pool.acquire() as conn:
        preset_row = await conn.fetchrow(
            """
            SELECT tp.id, tp.tags_json, tp.is_builtin, u.username as owner
            FROM tag_presets tp
            LEFT JOIN users u ON tp.user_id = u.id
            WHERE tp.id = $1
            """,
            preset_id,
        )

    if not preset_row:
        raise HTTPException(404, "Preset not found")
    if not preset_row["is_builtin"] and preset_row["owner"] != username:
        raise HTTPException(403, "Access denied to preset")

    tags = preset_row["tags_json"] or {}
    if isinstance(tags, str):
        tags = json.loads(tags)

    # 3. Look up asset output_path from per-user SQLite
    db_path = Path(str(config.server.data_dir)) / username / "proc.db"

    loop = asyncio.get_running_loop()

    def _get_asset_path():
        if not db_path.exists():
            return None
        conn_sq = sqlite3.connect(str(db_path))
        conn_sq.row_factory = sqlite3.Row
        row = conn_sq.execute(
            "SELECT output_path FROM assets WHERE id = ?", (asset_id,)
        ).fetchone()
        conn_sq.close()
        return dict(row)["output_path"] if row else None

    output_path = await loop.run_in_executor(None, _get_asset_path)
    if not output_path:
        raise HTTPException(404, "Asset not found or has no output path")

    # Resolve to absolute path
    if not os.path.isabs(output_path):
        output_dir = Path(str(config.server.data_dir)) / username / "output"
        full_output_path = str(output_dir / output_path)
    else:
        full_output_path = output_path

    if not os.path.isfile(full_output_path):
        raise HTTPException(404, f"Output file not found: {os.path.basename(full_output_path)}")

    # 4. Read old values for audit trail
    old_values = await tags_module.read_tags_before_edit(full_output_path, list(tags.keys()))

    # 5. Write tags
    write_result = await tags_module.write_tags(full_output_path, tags)
    if not write_result["success"]:
        raise HTTPException(500, f"exiftool write failed: {write_result['message']}")

    # 6. Log to tag_edits
    async with pool.acquire() as conn:
        user_id = await conn.fetchval(
            "SELECT id FROM users WHERE username = $1", username
        )
        for field_name, new_value in tags.items():
            old_value = old_values.get(field_name)
            await conn.execute(
                """
                INSERT INTO tag_edits
                    (user_id, job_id, asset_id, file_path, field_name, old_value, new_value, edit_type)
                VALUES ($1, $2, $3, $4, $5, $6, $7, 'preset')
                """,
                user_id, job_id, asset_id, full_output_path,
                field_name, old_value, str(new_value),
            )

    logger.info(
        f"Applied preset {preset_id} to asset {asset_id} (job {job_id}) "
        f"for user '{username}': {len(tags)} tags written"
    )
    return {
        "applied": True,
        "asset_id": asset_id,
        "preset_id": preset_id,
        "tags_written": len(tags),
        "warnings": write_result.get("warnings", []),
    }


class BatchPresetBody(BaseModel):
    asset_ids: list[int]
    preset_id: int


@router.post("/assets/batch-apply-preset")
async def batch_apply_preset(
    body: BatchPresetBody,
    request: Request,
    job_id: int = Query(...),
    username: str = Depends(get_current_user),
) -> dict:
    """POST /api/assets/batch-apply-preset?job_id=Y

    Applies a tag preset to multiple assets.
    Returns per-asset success/failure summary.
    """
    config = request.app.state.config
    pool = request.app.state.db_pool

    if not body.asset_ids:
        raise HTTPException(400, "asset_ids must not be empty")

    # 1. Verify job ownership
    async with pool.acquire() as conn:
        owner = await conn.fetchval(
            """
            SELECT u.username FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1
            """,
            job_id,
        )
    if owner != username:
        raise HTTPException(403, "Access denied to job")

    # 2. Load preset
    async with pool.acquire() as conn:
        preset_row = await conn.fetchrow(
            """
            SELECT tp.id, tp.tags_json, tp.is_builtin, u.username as owner
            FROM tag_presets tp
            LEFT JOIN users u ON tp.user_id = u.id
            WHERE tp.id = $1
            """,
            body.preset_id,
        )

    if not preset_row:
        raise HTTPException(404, "Preset not found")
    if not preset_row["is_builtin"] and preset_row["owner"] != username:
        raise HTTPException(403, "Access denied to preset")

    tags = preset_row["tags_json"] or {}
    if isinstance(tags, str):
        tags = json.loads(tags)

    if not tags:
        raise HTTPException(400, "Preset has no tags to apply")

    # 3. Bulk-fetch output paths from per-user SQLite
    db_path = Path(str(config.server.data_dir)) / username / "proc.db"

    loop = asyncio.get_running_loop()

    def _get_asset_paths():
        if not db_path.exists():
            return {}
        conn_sq = sqlite3.connect(str(db_path))
        conn_sq.row_factory = sqlite3.Row
        placeholders = ",".join("?" * len(body.asset_ids))
        rows = conn_sq.execute(
            f"SELECT id, output_path FROM assets WHERE id IN ({placeholders})",
            body.asset_ids,
        ).fetchall()
        conn_sq.close()
        return {dict(r)["id"]: dict(r)["output_path"] for r in rows}

    asset_paths = await loop.run_in_executor(None, _get_asset_paths)
    output_dir = Path(str(config.server.data_dir)) / username / "output"

    # 4. Get user_id once
    async with pool.acquire() as conn:
        user_id = await conn.fetchval(
            "SELECT id FROM users WHERE username = $1", username
        )

    # 5. Process each asset
    results = []
    for aid in body.asset_ids:
        rel_path = asset_paths.get(aid)
        if not rel_path:
            results.append({"asset_id": aid, "success": False, "error": "Asset not found"})
            continue

        full_path = str(output_dir / rel_path) if not os.path.isabs(rel_path) else rel_path
        if not os.path.isfile(full_path):
            results.append({"asset_id": aid, "success": False, "error": "Output file missing"})
            continue

        old_values = await tags_module.read_tags_before_edit(full_path, list(tags.keys()))
        write_result = await tags_module.write_tags(full_path, tags)

        if not write_result["success"]:
            results.append({
                "asset_id": aid,
                "success": False,
                "error": write_result["message"],
            })
            continue

        # Log to tag_edits
        async with pool.acquire() as conn:
            for field_name, new_value in tags.items():
                old_value = old_values.get(field_name)
                await conn.execute(
                    """
                    INSERT INTO tag_edits
                        (user_id, job_id, asset_id, file_path, field_name, old_value, new_value, edit_type)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, 'preset')
                    """,
                    user_id, job_id, aid, full_path,
                    field_name, old_value, str(new_value),
                )

        results.append({
            "asset_id": aid,
            "success": True,
            "tags_written": len(tags),
            "warnings": write_result.get("warnings", []),
        })

    succeeded = sum(1 for r in results if r["success"])
    failed = len(results) - succeeded
    logger.info(
        f"Batch applied preset {body.preset_id} to job {job_id} for '{username}': "
        f"{succeeded} succeeded, {failed} failed"
    )
    return {
        "total": len(body.asset_ids),
        "succeeded": succeeded,
        "failed": failed,
        "results": results,
    }


# ============================================================
# Feature #10 — XMP Sidecar Viewer & Editor
# ============================================================


def _resolve_xmp_path(asset: dict, config, username: str) -> str | None:
    """Resolve absolute xmp_path from an asset row, or return None."""
    xmp_path = asset.get("xmp_path") or ""
    if not xmp_path:
        return None
    if not os.path.isabs(xmp_path):
        output_dir = Path(str(config.server.data_dir)) / username / "output"
        return str(output_dir / xmp_path)
    return xmp_path


@router.get("/assets/{asset_id}/xmp")
async def get_xmp(
    asset_id: int,
    job_id: int = Query(...),
    request: Request = None,
    username: str = Depends(get_current_user),
) -> dict:
    """GET /api/assets/{asset_id}/xmp?job_id=42 — Read XMP sidecar content.

    Returns {"content": "<raw XML>", "path": "...", "exists": true/false}.
    Looks up xmp_path from per-user SQLite assets table, then reads via tags module.
    """
    config = request.app.state.config
    pool = request.app.state.db_pool

    # Verify job ownership
    async with pool.acquire() as conn:
        owner = await conn.fetchval(
            "SELECT u.username FROM processing_jobs pj JOIN users u ON pj.user_id = u.id WHERE pj.id = $1",
            job_id,
        )
    if owner != username:
        raise HTTPException(403, "Access denied")

    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    if not db_path.exists():
        raise HTTPException(404, "Asset database not found")

    loop = asyncio.get_running_loop()

    def _get_asset():
        conn_sq = sqlite3.connect(str(db_path))
        conn_sq.row_factory = sqlite3.Row
        row = conn_sq.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
        conn_sq.close()
        return dict(row) if row else None

    asset = await loop.run_in_executor(None, _get_asset)
    if not asset:
        raise HTTPException(404, "Asset not found")

    full_xmp_path = _resolve_xmp_path(asset, config, username)
    if not full_xmp_path:
        return {"content": None, "path": None, "exists": False}

    content = await tags_module.read_xmp_sidecar(full_xmp_path)
    return {
        "content": content,
        "path": full_xmp_path,
        "exists": content is not None,
    }


class XmpBody(BaseModel):
    content: str


@router.put("/assets/{asset_id}/xmp")
async def update_xmp(
    asset_id: int,
    body: XmpBody,
    job_id: int = Query(...),
    request: Request = None,
    username: str = Depends(get_current_user),
) -> dict:
    """PUT /api/assets/{asset_id}/xmp?job_id=42 — Write XMP sidecar content.

    Validates well-formed XML with <x:xmpmeta root, saves via tags module,
    logs edit to tag_edits PostgreSQL table.
    Returns {"saved": true}.
    """
    config = request.app.state.config
    pool = request.app.state.db_pool

    # Validate: well-formed XML
    try:
        root_el = ET.fromstring(body.content)
    except ET.ParseError as exc:
        raise HTTPException(400, f"Invalid XML: {exc}")

    # Validate: must contain x:xmpmeta root element (strip namespace for check)
    local_tag = root_el.tag.split("}")[-1] if "}" in root_el.tag else root_el.tag
    if local_tag != "xmpmeta":
        raise HTTPException(400, "XMP content must have <x:xmpmeta> as root element")

    # Verify job ownership and get user_id
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT pj.id, u.id as user_id, u.username
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )
    if not row:
        raise HTTPException(403, "Access denied")

    user_id = row["user_id"]

    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    if not db_path.exists():
        raise HTTPException(404, "Asset database not found")

    loop = asyncio.get_running_loop()

    def _get_asset():
        conn_sq = sqlite3.connect(str(db_path))
        conn_sq.row_factory = sqlite3.Row
        r = conn_sq.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
        conn_sq.close()
        return dict(r) if r else None

    asset = await loop.run_in_executor(None, _get_asset)
    if not asset:
        raise HTTPException(404, "Asset not found")

    full_xmp_path = _resolve_xmp_path(asset, config, username)
    if not full_xmp_path:
        raise HTTPException(400, "Asset has no XMP path configured")

    # Read old content for audit trail
    old_content = await tags_module.read_xmp_sidecar(full_xmp_path)

    # Write new content
    await tags_module.write_xmp_sidecar(full_xmp_path, body.content)

    # Log to tag_edits audit table
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO tag_edits
                (user_id, job_id, asset_id, file_path, field_name, old_value, new_value, edit_type)
            VALUES ($1, $2, $3, $4, 'xmp_sidecar', $5, $6, 'manual')
            """,
            user_id, job_id, asset_id,
            full_xmp_path,
            str(old_content)[:2000] if old_content else None,
            body.content[:2000],
        )

    logger.info(
        f"XMP sidecar updated: user='{username}' job={job_id} asset={asset_id} "
        f"path={full_xmp_path}"
    )
    return {"saved": True}


# ============================================================
# Feature #11 — Custom Metadata Schema
# ============================================================

_VALID_PREFIX_RE = re.compile(r"^[a-zA-Z0-9_]+$")
_VALID_FIELD_NAME_RE = re.compile(r"^[a-zA-Z0-9_]+$")
_VALID_FIELD_TYPES = {"text", "number", "date", "boolean", "url"}


def _validate_schema_body(body: "SchemaBody") -> None:
    """Raise HTTPException for invalid schema fields."""
    if not _VALID_PREFIX_RE.match(body.namespace_prefix):
        raise HTTPException(400, "namespace_prefix must be alphanumeric + underscore only")
    if not (
        body.namespace_uri.startswith("http://") or body.namespace_uri.startswith("https://")
    ):
        raise HTTPException(400, "namespace_uri must start with http:// or https://")
    for field in body.fields:
        name = field.get("name", "")
        ftype = field.get("type", "")
        if not name or not _VALID_FIELD_NAME_RE.match(name):
            raise HTTPException(
                400, f"Field name '{name}' must be alphanumeric + underscore only"
            )
        if ftype not in _VALID_FIELD_TYPES:
            raise HTTPException(
                400,
                f"Field type '{ftype}' must be one of: {', '.join(sorted(_VALID_FIELD_TYPES))}",
            )


class SchemaBody(BaseModel):
    namespace_uri: str
    namespace_prefix: str
    fields: list[dict]


@router.get("/schemas")
async def list_schemas(
    request: Request,
    username: str = Depends(get_current_user),
) -> list[dict]:
    """GET /api/schemas — List authenticated user's custom metadata schemas."""
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT cs.id, cs.namespace_uri, cs.namespace_prefix, cs.fields_json,
                   cs.created_at, cs.updated_at
            FROM custom_schemas cs
            JOIN users u ON cs.user_id = u.id
            WHERE u.username = $1
            ORDER BY cs.created_at ASC
            """,
            username,
        )

    result = []
    for row in rows:
        d = dict(row)
        # asyncpg returns JSONB as a native Python object; coerce if somehow still a string
        if isinstance(d.get("fields_json"), str):
            d["fields_json"] = json.loads(d["fields_json"])
        result.append(d)

    return result


@router.post("/schemas")
async def create_schema(
    body: SchemaBody,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """POST /api/schemas — Create a new custom metadata schema."""
    pool = request.app.state.db_pool
    _validate_schema_body(body)

    async with pool.acquire() as conn:
        user_id = await conn.fetchval("SELECT id FROM users WHERE username = $1", username)
        if not user_id:
            raise HTTPException(404, "User not found")

        try:
            row = await conn.fetchrow(
                """
                INSERT INTO custom_schemas (user_id, namespace_uri, namespace_prefix, fields_json)
                VALUES ($1, $2, $3, $4::JSONB)
                RETURNING id, namespace_uri, namespace_prefix, fields_json, created_at, updated_at
                """,
                user_id,
                body.namespace_uri,
                body.namespace_prefix,
                json.dumps(body.fields),
            )
        except Exception as exc:
            if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
                raise HTTPException(
                    409, f"A schema with prefix '{body.namespace_prefix}' already exists"
                )
            raise

    logger.info(f"Schema created: user='{username}' prefix='{body.namespace_prefix}'")
    return dict(row)


@router.put("/schemas/{schema_id}")
async def update_schema(
    schema_id: int,
    body: SchemaBody,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """PUT /api/schemas/{schema_id} — Update an existing custom schema.

    Verifies ownership before update.
    """
    pool = request.app.state.db_pool
    _validate_schema_body(body)

    async with pool.acquire() as conn:
        # Verify ownership
        owner = await conn.fetchval(
            """
            SELECT u.username FROM custom_schemas cs
            JOIN users u ON cs.user_id = u.id
            WHERE cs.id = $1
            """,
            schema_id,
        )
        if owner is None:
            raise HTTPException(404, "Schema not found")
        if owner != username:
            raise HTTPException(403, "Access denied")

        try:
            row = await conn.fetchrow(
                """
                UPDATE custom_schemas
                SET namespace_uri    = $1,
                    namespace_prefix = $2,
                    fields_json      = $3::JSONB,
                    updated_at       = NOW()
                WHERE id = $4
                RETURNING id, namespace_uri, namespace_prefix, fields_json, created_at, updated_at
                """,
                body.namespace_uri,
                body.namespace_prefix,
                json.dumps(body.fields),
                schema_id,
            )
        except Exception as exc:
            if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
                raise HTTPException(
                    409, f"A schema with prefix '{body.namespace_prefix}' already exists"
                )
            raise

    logger.info(f"Schema updated: user='{username}' schema_id={schema_id}")
    return dict(row)


@router.delete("/schemas/{schema_id}")
async def delete_schema(
    schema_id: int,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """DELETE /api/schemas/{schema_id} — Delete a custom schema.

    Verifies ownership before deletion.
    """
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        owner = await conn.fetchval(
            """
            SELECT u.username FROM custom_schemas cs
            JOIN users u ON cs.user_id = u.id
            WHERE cs.id = $1
            """,
            schema_id,
        )
        if owner is None:
            raise HTTPException(404, "Schema not found")
        if owner != username:
            raise HTTPException(403, "Access denied")

        await conn.execute("DELETE FROM custom_schemas WHERE id = $1", schema_id)

    logger.info(f"Schema deleted: user='{username}' schema_id={schema_id}")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# GPS Correction & Override — Feature #13
# ---------------------------------------------------------------------------

import math as _math


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in metres between two WGS-84 points."""
    R = 6_371_000.0  # Earth radius in metres
    phi1, phi2 = _math.radians(lat1), _math.radians(lat2)
    dphi = _math.radians(lat2 - lat1)
    dlam = _math.radians(lon2 - lon1)
    a = _math.sin(dphi / 2) ** 2 + _math.cos(phi1) * _math.cos(phi2) * _math.sin(dlam / 2) ** 2
    return R * 2 * _math.atan2(_math.sqrt(a), _math.sqrt(1 - a))


def _gps_exif_tags(lat: float, lon: float) -> dict:
    """Return exiftool tag dict for a decimal-degree GPS fix.

    exiftool expects the absolute value for Latitude/Longitude and a separate
    Ref tag containing N/S or E/W.
    """
    return {
        "EXIF:GPSLatitude": str(abs(lat)),
        "EXIF:GPSLatitudeRef": "N" if lat >= 0 else "S",
        "EXIF:GPSLongitude": str(abs(lon)),
        "EXIF:GPSLongitudeRef": "E" if lon >= 0 else "W",
    }


async def _resolve_asset_path(
    asset_id: int,
    username: str,
    config,
    loop,
) -> tuple[dict | None, str | None]:
    """Load asset row from SQLite and resolve the full output path.

    Returns (asset_dict, full_output_path). Either can be None on failure.
    """
    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    if not db_path.exists():
        return None, None

    def _get():
        conn_sq = sqlite3.connect(str(db_path))
        conn_sq.row_factory = sqlite3.Row
        r = conn_sq.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
        conn_sq.close()
        return dict(r) if r else None

    asset = await loop.run_in_executor(None, _get)
    if not asset:
        return None, None

    out = asset.get("output_path") or asset.get("path") or ""
    if out and not os.path.isabs(out):
        out = str(Path(str(config.server.data_dir)) / username / "output" / out)

    return asset, out if out else None


class GpsUpdateBody(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)


@router.put("/assets/{asset_id}/gps")
async def update_asset_gps(
    asset_id: int,
    body: GpsUpdateBody,
    job_id: int = Query(...),
    request: Request = None,
    username: str = Depends(get_current_user),
) -> dict:
    """PUT /api/assets/{asset_id}/gps?job_id=42 — Write GPS coordinates to output file.

    Writes EXIF:GPSLatitude/Longitude + Ref tags via exiftool.
    Logs each tag change to the tag_edits audit trail.
    """
    config = request.app.state.config
    pool = request.app.state.db_pool

    # Verify job ownership and get user_id
    async with pool.acquire() as conn:
        job_row = await conn.fetchrow(
            """
            SELECT pj.id, u.id as user_id
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )
    if not job_row:
        raise HTTPException(403, "Access denied")

    user_id = job_row["user_id"]
    loop = asyncio.get_running_loop()

    asset, full_output_path = await _resolve_asset_path(asset_id, username, config, loop)
    if not asset:
        raise HTTPException(404, "Asset not found")
    if not full_output_path or not os.path.isfile(full_output_path):
        raise HTTPException(404, "Output file not found")

    edits = _gps_exif_tags(body.lat, body.lon)
    tag_names = list(edits.keys())

    # Capture old values for audit trail
    old_values = await tags_module.read_tags_before_edit(full_output_path, tag_names)

    # Write GPS tags
    write_result = await tags_module.write_tags(full_output_path, edits)
    if not write_result["success"]:
        raise HTTPException(500, f"exiftool write failed: {write_result['message']}")

    # Log to tag_edits audit table
    async with pool.acquire() as conn:
        for field_name, new_value in edits.items():
            old_value = old_values.get(field_name)
            await conn.execute(
                """
                INSERT INTO tag_edits
                    (user_id, job_id, asset_id, file_path, field_name, old_value, new_value, edit_type)
                VALUES ($1, $2, $3, $4, $5, $6, $7, 'gps_override')
                """,
                user_id, job_id, asset_id,
                full_output_path, field_name,
                str(old_value) if old_value is not None else None,
                str(new_value),
            )

    logger.info(
        f"GPS override: user='{username}' job={job_id} asset={asset_id} "
        f"lat={body.lat} lon={body.lon}"
    )
    return {"success": True, "asset_id": asset_id, "lat": body.lat, "lon": body.lon}


class BatchGpsBody(BaseModel):
    asset_ids: list[int]
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)


@router.post("/assets/batch-gps")
async def batch_update_gps(
    body: BatchGpsBody,
    job_id: int = Query(...),
    request: Request = None,
    username: str = Depends(get_current_user),
) -> dict:
    """POST /api/assets/batch-gps?job_id=42 — Apply GPS to multiple assets.

    Processes assets sequentially. Returns {total, succeeded, failed}.
    """
    config = request.app.state.config
    pool = request.app.state.db_pool

    if not body.asset_ids:
        raise HTTPException(400, "No asset_ids provided")

    # Verify job ownership
    async with pool.acquire() as conn:
        job_row = await conn.fetchrow(
            """
            SELECT pj.id, u.id as user_id
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )
    if not job_row:
        raise HTTPException(403, "Access denied")

    user_id = job_row["user_id"]
    loop = asyncio.get_running_loop()
    edits = _gps_exif_tags(body.lat, body.lon)
    tag_names = list(edits.keys())

    succeeded = 0
    failed = 0

    for asset_id in body.asset_ids:
        try:
            asset, full_output_path = await _resolve_asset_path(
                asset_id, username, config, loop
            )
            if not asset or not full_output_path or not os.path.isfile(full_output_path):
                failed += 1
                continue

            old_values = await tags_module.read_tags_before_edit(full_output_path, tag_names)
            write_result = await tags_module.write_tags(full_output_path, edits)
            if not write_result["success"]:
                failed += 1
                continue

            async with pool.acquire() as conn:
                for field_name, new_value in edits.items():
                    old_value = old_values.get(field_name)
                    await conn.execute(
                        """
                        INSERT INTO tag_edits
                            (user_id, job_id, asset_id, file_path, field_name,
                             old_value, new_value, edit_type)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, 'gps_batch')
                        """,
                        user_id, job_id, asset_id,
                        full_output_path, field_name,
                        str(old_value) if old_value is not None else None,
                        str(new_value),
                    )
            succeeded += 1

        except Exception as exc:
            logger.warning(f"Batch GPS failed for asset {asset_id}: {exc}")
            failed += 1

    logger.info(
        f"Batch GPS: user='{username}' job={job_id} "
        f"total={len(body.asset_ids)} ok={succeeded} fail={failed}"
    )
    return {"total": len(body.asset_ids), "succeeded": succeeded, "failed": failed}


# Saved Locations CRUD

class SavedLocationBody(BaseModel):
    name: str
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    radius_m: int = Field(default=50, ge=10, le=5000)


@router.get("/saved-locations")
async def list_saved_locations(
    request: Request,
    username: str = Depends(get_current_user),
) -> list[dict]:
    """GET /api/saved-locations — Return all saved locations for the user."""
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        user_id = await conn.fetchval(
            "SELECT id FROM users WHERE username = $1", username
        )
        if not user_id:
            raise HTTPException(403, "User not found")

        rows = await conn.fetch(
            """
            SELECT id, name, lat, lon, radius_m, created_at
            FROM saved_locations
            WHERE user_id = $1
            ORDER BY created_at DESC
            """,
            user_id,
        )

    result = []
    for r in rows:
        d = dict(r)
        if d.get("created_at"):
            d["created_at"] = d["created_at"].isoformat()
        result.append(d)
    return result


@router.post("/saved-locations", status_code=201)
async def create_saved_location(
    body: SavedLocationBody,
    request: Request = None,
    username: str = Depends(get_current_user),
) -> dict:
    """POST /api/saved-locations — Create a new saved location."""
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        user_id = await conn.fetchval(
            "SELECT id FROM users WHERE username = $1", username
        )
        if not user_id:
            raise HTTPException(403, "User not found")

        new_id = await conn.fetchval(
            """
            INSERT INTO saved_locations (user_id, name, lat, lon, radius_m)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            user_id, body.name.strip(), body.lat, body.lon, body.radius_m,
        )
        row = await conn.fetchrow(
            "SELECT id, name, lat, lon, radius_m, created_at FROM saved_locations WHERE id = $1",
            new_id,
        )

    d = dict(row)
    if d.get("created_at"):
        d["created_at"] = d["created_at"].isoformat()
    logger.info(f"Saved location created: user='{username}' id={new_id} name='{body.name}'")
    return d


@router.delete("/saved-locations/{location_id}")
async def delete_saved_location(
    location_id: int,
    request: Request = None,
    username: str = Depends(get_current_user),
) -> dict:
    """DELETE /api/saved-locations/{location_id} — Delete a saved location."""
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        owner = await conn.fetchval(
            """
            SELECT u.username FROM saved_locations sl
            JOIN users u ON sl.user_id = u.id
            WHERE sl.id = $1
            """,
            location_id,
        )
        if owner is None:
            raise HTTPException(404, "Saved location not found")
        if owner != username:
            raise HTTPException(403, "Access denied")

        await conn.execute("DELETE FROM saved_locations WHERE id = $1", location_id)

    logger.info(f"Saved location deleted: user='{username}' id={location_id}")
    return {"deleted": True}


@router.post("/assets/snap-to-location")
async def snap_to_location(
    location_id: int = Query(...),
    job_id: int = Query(...),
    request: Request = None,
    username: str = Depends(get_current_user),
) -> dict:
    """POST /api/assets/snap-to-location?location_id=N&job_id=M

    Finds all assets whose current GPS is within radius_m metres of the saved
    location, then overwrites their GPS to the exact saved-location coordinates.
    Uses Haversine formula for distance calculation.
    """
    config = request.app.state.config
    pool = request.app.state.db_pool

    # Verify job ownership and get user_id
    async with pool.acquire() as conn:
        job_row = await conn.fetchrow(
            """
            SELECT pj.id, u.id as user_id
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )
    if not job_row:
        raise HTTPException(403, "Access denied")

    user_id = job_row["user_id"]

    # Fetch the saved location (verify ownership)
    async with pool.acquire() as conn:
        loc_row = await conn.fetchrow(
            """
            SELECT sl.id, sl.name, sl.lat, sl.lon, sl.radius_m
            FROM saved_locations sl
            JOIN users u ON sl.user_id = u.id
            WHERE sl.id = $1 AND u.username = $2
            """,
            location_id, username,
        )
    if not loc_row:
        raise HTTPException(404, "Saved location not found")

    target_lat = loc_row["lat"]
    target_lon = loc_row["lon"]
    radius_m = loc_row["radius_m"]

    # Load all assets with GPS from SQLite and filter by radius
    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    loop = asyncio.get_running_loop()

    def _load_gps_assets():
        if not db_path.exists():
            return []
        conn_sq = sqlite3.connect(str(db_path))
        conn_sq.row_factory = sqlite3.Row
        try:
            rows = conn_sq.execute(
                """
                SELECT a.id, a.output_path, a.filename,
                       m.matched_lat, m.matched_lon
                FROM assets a
                JOIN matches m ON m.asset_id = a.id
                WHERE m.matched_lat IS NOT NULL AND m.matched_lon IS NOT NULL
                """
            ).fetchall()
        except Exception:
            rows = []
        conn_sq.close()
        return [dict(r) for r in rows]

    all_assets = await loop.run_in_executor(None, _load_gps_assets)

    # Filter assets within radius
    nearby = [
        a for a in all_assets
        if _haversine_m(a["matched_lat"], a["matched_lon"], target_lat, target_lon) <= radius_m
    ]

    if not nearby:
        return {"snapped": 0, "location": loc_row["name"]}

    edits = _gps_exif_tags(target_lat, target_lon)
    tag_names = list(edits.keys())
    snapped = 0

    for asset in nearby:
        try:
            out_path = asset.get("output_path") or ""
            if out_path and not os.path.isabs(out_path):
                out_path = str(
                    Path(str(config.server.data_dir)) / username / "output" / out_path
                )
            if not out_path or not os.path.isfile(out_path):
                continue

            old_values = await tags_module.read_tags_before_edit(out_path, tag_names)
            write_result = await tags_module.write_tags(out_path, edits)
            if not write_result["success"]:
                continue

            async with pool.acquire() as conn:
                for field_name, new_value in edits.items():
                    old_value = old_values.get(field_name)
                    await conn.execute(
                        """
                        INSERT INTO tag_edits
                            (user_id, job_id, asset_id, file_path, field_name,
                             old_value, new_value, edit_type)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, 'snap_to_location')
                        """,
                        user_id, job_id, asset["id"],
                        out_path, field_name,
                        str(old_value) if old_value is not None else None,
                        str(new_value),
                    )
            snapped += 1

        except Exception as exc:
            logger.warning(f"Snap-to-location failed for asset {asset['id']}: {exc}")

    logger.info(
        f"Snap-to-location: user='{username}' job={job_id} "
        f"location_id={location_id} snapped={snapped}/{len(nearby)}"
    )
    return {"snapped": snapped, "total_nearby": len(nearby), "location": loc_row["name"]}


# ---------------------------------------------------------------------------
# Timestamp Correction — Feature #14
# ---------------------------------------------------------------------------

@router.get("/jobs/{job_id}/timestamps")
async def get_timestamps(
    job_id: int,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """GET /api/jobs/{job_id}/timestamps — List asset timestamps for timeline rendering.

    Returns a list of {asset_id, filename, asset_type, current_date, output_path}
    sourced from SQLite match data (matched_date preferred over date_str).
    """
    config = request.app.state.config
    pool = request.app.state.db_pool

    # Verify job ownership
    async with pool.acquire() as conn:
        job = await conn.fetchrow(
            """
            SELECT pj.id FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )
    if not job:
        raise HTTPException(404, "Job not found")

    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    loop = asyncio.get_running_loop()

    def _load():
        if not db_path.exists():
            return []
        conn_sq = sqlite3.connect(str(db_path))
        conn_sq.row_factory = sqlite3.Row
        try:
            rows = conn_sq.execute(
                """
                SELECT
                    a.id AS asset_id,
                    a.filename,
                    a.asset_type,
                    a.output_path,
                    a.is_video,
                    COALESCE(m.matched_date, a.date_str) AS current_date
                FROM assets a
                LEFT JOIN matches m ON m.asset_id = a.id AND m.is_best = 1
                ORDER BY current_date ASC, a.id ASC
                """
            ).fetchall()
        except Exception:
            rows = []
        conn_sq.close()
        return [dict(r) for r in rows]

    assets = await loop.run_in_executor(None, _load)
    return {"job_id": job_id, "assets": assets}


class TimestampBody(BaseModel):
    datetime_str: str  # "2024:07:04 14:30:00" (EXIF) or "2024-07-04T14:30:00" (ISO)


@router.put("/assets/{asset_id}/timestamp")
async def update_timestamp(
    asset_id: int,
    body: TimestampBody,
    job_id: int = Query(...),
    request: Request = None,
    username: str = Depends(get_current_user),
) -> dict:
    """PUT /api/assets/{asset_id}/timestamp?job_id=42 — Set absolute timestamp.

    Accepts EXIF format "YYYY:MM:DD HH:MM:SS" or ISO "YYYY-MM-DDTHH:MM:SS".
    Writes DateTimeOriginal, CreateDate, ModifyDate (+ QuickTime equivalents for video).
    Logs each change to tag_edits.
    """
    from datetime import datetime as _datetime

    config = request.app.state.config
    pool = request.app.state.db_pool

    # Normalise datetime string: accept both EXIF and ISO formats
    raw = body.datetime_str.strip()
    if "T" in raw or "-" in raw[:10]:
        # ISO format: "2024-07-04T14:30:00" or "2024-07-04 14:30:00"
        raw_clean = raw.replace("T", " ")[:19]
        try:
            dt = _datetime.strptime(raw_clean, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            raise HTTPException(400, f"Cannot parse datetime: {body.datetime_str!r}")
        exif_str = dt.strftime("%Y:%m:%d %H:%M:%S")
    else:
        # EXIF format: "2024:07:04 14:30:00"
        try:
            dt = _datetime.strptime(raw[:19], "%Y:%m:%d %H:%M:%S")
            exif_str = raw[:19]
        except ValueError:
            raise HTTPException(400, f"Cannot parse datetime: {body.datetime_str!r}")

    # Verify job ownership and get user_id
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT pj.id, u.id AS user_id FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )
    if not row:
        raise HTTPException(404, "Job not found")
    user_id = row["user_id"]

    # Load asset from SQLite
    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    loop = asyncio.get_running_loop()

    def _get_asset():
        if not db_path.exists():
            return None
        conn_sq = sqlite3.connect(str(db_path))
        conn_sq.row_factory = sqlite3.Row
        r = conn_sq.execute(
            "SELECT id, output_path, is_video FROM assets WHERE id = ?", (asset_id,)
        ).fetchone()
        conn_sq.close()
        return dict(r) if r else None

    asset = await loop.run_in_executor(None, _get_asset)
    if not asset:
        raise HTTPException(404, "Asset not found")

    # Resolve output path
    output_path = asset.get("output_path") or ""
    if output_path and not os.path.isabs(output_path):
        output_dir = Path(str(config.server.data_dir)) / username / "output"
        full_output_path = str(output_dir / output_path)
    else:
        full_output_path = output_path

    if not full_output_path or not os.path.isfile(full_output_path):
        raise HTTPException(404, "Output file not found")

    # Build tag edits: photo tags always; QuickTime tags for video
    is_video = bool(asset.get("is_video"))
    edits: dict[str, str] = {
        "EXIF:DateTimeOriginal": exif_str,
        "EXIF:CreateDate": exif_str,
        "EXIF:ModifyDate": exif_str,
    }
    if is_video:
        edits["QuickTime:CreateDate"] = exif_str
        edits["QuickTime:ModifyDate"] = exif_str

    tag_names = list(edits.keys())
    old_values = await tags_module.read_tags_before_edit(full_output_path, tag_names)

    write_result = await tags_module.write_tags(full_output_path, edits)
    if not write_result["success"]:
        raise HTTPException(500, f"exiftool write failed: {write_result['message']}")

    # Log to tag_edits
    async with pool.acquire() as conn:
        for field_name, new_value in edits.items():
            old_value = old_values.get(field_name)
            if str(old_value) != str(new_value):
                await conn.execute(
                    """
                    INSERT INTO tag_edits
                        (user_id, job_id, asset_id, file_path, field_name, old_value, new_value, edit_type)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, 'timestamp')
                    """,
                    user_id, job_id, asset_id,
                    full_output_path, field_name,
                    str(old_value) if old_value is not None else None,
                    new_value,
                )

    logger.info(
        f"Timestamp set: user='{username}' job={job_id} asset={asset_id} "
        f"exif_str='{exif_str}' is_video={is_video}"
    )
    return {"success": True, "asset_id": asset_id, "datetime_written": exif_str}


class BatchTimeshiftBody(BaseModel):
    asset_ids: list[int]
    offset_hours: float  # positive = add hours, negative = subtract


@router.post("/assets/batch-timeshift")
async def batch_timeshift(
    body: BatchTimeshiftBody,
    job_id: int = Query(...),
    request: Request = None,
    username: str = Depends(get_current_user),
) -> dict:
    """POST /api/assets/batch-timeshift?job_id=42 — Shift timestamps by ±N hours.

    Reads current DateTimeOriginal for each asset, adds offset_hours, writes back.
    Handles both photo EXIF tags and video QuickTime tags.
    Returns {total, succeeded, failed, errors}.
    """
    from datetime import datetime as _datetime, timedelta as _timedelta

    if not body.asset_ids:
        raise HTTPException(400, "No asset_ids provided")

    config = request.app.state.config
    pool = request.app.state.db_pool

    # Verify job ownership and get user_id
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT pj.id, u.id AS user_id FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )
    if not row:
        raise HTTPException(404, "Job not found")
    user_id = row["user_id"]

    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    loop = asyncio.get_running_loop()

    def _get_assets(ids: list[int]):
        if not db_path.exists():
            return {}
        conn_sq = sqlite3.connect(str(db_path))
        conn_sq.row_factory = sqlite3.Row
        placeholders = ",".join("?" * len(ids))
        rows = conn_sq.execute(
            f"SELECT id, output_path, is_video FROM assets WHERE id IN ({placeholders})",
            ids,
        ).fetchall()
        conn_sq.close()
        return {r["id"]: dict(r) for r in rows}

    asset_map = await loop.run_in_executor(None, _get_assets, body.asset_ids)

    offset = _timedelta(hours=body.offset_hours)
    total = len(body.asset_ids)
    succeeded = 0
    failed = 0
    errors = []

    for asset_id in body.asset_ids:
        asset = asset_map.get(asset_id)
        if not asset:
            failed += 1
            errors.append({"asset_id": asset_id, "error": "Asset not found"})
            continue

        output_path = asset.get("output_path") or ""
        if output_path and not os.path.isabs(output_path):
            output_dir = Path(str(config.server.data_dir)) / username / "output"
            full_output_path = str(output_dir / output_path)
        else:
            full_output_path = output_path

        if not full_output_path or not os.path.isfile(full_output_path):
            failed += 1
            errors.append({"asset_id": asset_id, "error": "Output file not found"})
            continue

        is_video = bool(asset.get("is_video"))

        # Read current DateTimeOriginal
        old_vals = await tags_module.read_tags_before_edit(full_output_path, ["DateTimeOriginal"])
        old_dt_str = old_vals.get("DateTimeOriginal")

        if not old_dt_str:
            failed += 1
            errors.append({"asset_id": asset_id, "error": "No DateTimeOriginal to shift"})
            continue

        try:
            old_dt = _datetime.strptime(old_dt_str.strip()[:19], "%Y:%m:%d %H:%M:%S")
        except ValueError:
            try:
                old_dt = _datetime.strptime(old_dt_str.strip()[:19], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                failed += 1
                errors.append({"asset_id": asset_id, "error": f"Cannot parse date: {old_dt_str!r}"})
                continue

        new_dt = old_dt + offset
        new_exif_str = new_dt.strftime("%Y:%m:%d %H:%M:%S")

        edits: dict[str, str] = {
            "EXIF:DateTimeOriginal": new_exif_str,
            "EXIF:CreateDate": new_exif_str,
            "EXIF:ModifyDate": new_exif_str,
        }
        if is_video:
            edits["QuickTime:CreateDate"] = new_exif_str
            edits["QuickTime:ModifyDate"] = new_exif_str

        tag_names = list(edits.keys())
        old_values = await tags_module.read_tags_before_edit(full_output_path, tag_names)

        write_result = await tags_module.write_tags(full_output_path, edits)
        if not write_result.get("success"):
            failed += 1
            errors.append({"asset_id": asset_id, "error": write_result.get("message", "Write failed")})
            continue

        # Log to tag_edits
        async with pool.acquire() as conn:
            for field_name, new_value in edits.items():
                old_value = old_values.get(field_name)
                if str(old_value) != str(new_value):
                    try:
                        await conn.execute(
                            """
                            INSERT INTO tag_edits
                                (user_id, job_id, asset_id, file_path, field_name, old_value, new_value, edit_type)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, 'batch')
                            """,
                            user_id, job_id, asset_id,
                            full_output_path, field_name,
                            str(old_value) if old_value is not None else None,
                            new_value,
                        )
                    except Exception as log_exc:
                        logger.warning(f"tag_edits log failed for asset {asset_id}: {log_exc}")

        succeeded += 1

    logger.info(
        f"Batch timeshift: user='{username}' job={job_id} "
        f"offset_hours={body.offset_hours} total={total} succeeded={succeeded} failed={failed}"
    )
    return {"total": total, "succeeded": succeeded, "failed": failed, "errors": errors}


class BatchTimezoneBody(BaseModel):
    asset_ids: list[int]
    from_tz: str  # e.g. "UTC", "US/Central"
    to_tz: str    # e.g. "US/Eastern"


@router.post("/assets/batch-timezone")
async def batch_timezone(
    body: BatchTimezoneBody,
    job_id: int = Query(...),
    request: Request = None,
    username: str = Depends(get_current_user),
) -> dict:
    """POST /api/assets/batch-timezone?job_id=42 — Convert timestamps between timezones.

    Uses Python stdlib zoneinfo to localize from_tz then convert to to_tz.
    Writes updated timestamps back via exiftool.
    Returns {total, succeeded, failed}.
    """
    from datetime import datetime as _datetime
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    if not body.asset_ids:
        raise HTTPException(400, "No asset_ids provided")

    # Validate timezone strings before processing anything
    try:
        tz_from = ZoneInfo(body.from_tz)
        tz_to = ZoneInfo(body.to_tz)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(400, f"Unknown timezone: {exc}")

    config = request.app.state.config
    pool = request.app.state.db_pool

    # Verify job ownership and get user_id
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT pj.id, u.id AS user_id FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )
    if not row:
        raise HTTPException(404, "Job not found")
    user_id = row["user_id"]

    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    loop = asyncio.get_running_loop()

    def _get_assets(ids: list[int]):
        if not db_path.exists():
            return {}
        conn_sq = sqlite3.connect(str(db_path))
        conn_sq.row_factory = sqlite3.Row
        placeholders = ",".join("?" * len(ids))
        rows = conn_sq.execute(
            f"SELECT id, output_path, is_video FROM assets WHERE id IN ({placeholders})",
            ids,
        ).fetchall()
        conn_sq.close()
        return {r["id"]: dict(r) for r in rows}

    asset_map = await loop.run_in_executor(None, _get_assets, body.asset_ids)

    total = len(body.asset_ids)
    succeeded = 0
    failed = 0

    for asset_id in body.asset_ids:
        asset = asset_map.get(asset_id)
        if not asset:
            failed += 1
            continue

        output_path = asset.get("output_path") or ""
        if output_path and not os.path.isabs(output_path):
            output_dir = Path(str(config.server.data_dir)) / username / "output"
            full_output_path = str(output_dir / output_path)
        else:
            full_output_path = output_path

        if not full_output_path or not os.path.isfile(full_output_path):
            failed += 1
            continue

        is_video = bool(asset.get("is_video"))

        # Read current date
        old_vals = await tags_module.read_tags_before_edit(full_output_path, ["DateTimeOriginal"])
        old_dt_str = old_vals.get("DateTimeOriginal")

        if not old_dt_str:
            failed += 1
            continue

        try:
            old_dt_naive = _datetime.strptime(old_dt_str.strip()[:19], "%Y:%m:%d %H:%M:%S")
        except ValueError:
            try:
                old_dt_naive = _datetime.strptime(old_dt_str.strip()[:19], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                failed += 1
                continue

        # Localize to from_tz then convert to to_tz
        dt_from = old_dt_naive.replace(tzinfo=tz_from)
        dt_to = dt_from.astimezone(tz_to)
        new_exif_str = dt_to.strftime("%Y:%m:%d %H:%M:%S")

        edits: dict[str, str] = {
            "EXIF:DateTimeOriginal": new_exif_str,
            "EXIF:CreateDate": new_exif_str,
            "EXIF:ModifyDate": new_exif_str,
        }
        if is_video:
            edits["QuickTime:CreateDate"] = new_exif_str
            edits["QuickTime:ModifyDate"] = new_exif_str

        tag_names = list(edits.keys())
        old_values = await tags_module.read_tags_before_edit(full_output_path, tag_names)

        write_result = await tags_module.write_tags(full_output_path, edits)
        if not write_result.get("success"):
            failed += 1
            continue

        # Log to tag_edits
        async with pool.acquire() as conn:
            for field_name, new_value in edits.items():
                old_value = old_values.get(field_name)
                if str(old_value) != str(new_value):
                    try:
                        await conn.execute(
                            """
                            INSERT INTO tag_edits
                                (user_id, job_id, asset_id, file_path, field_name, old_value, new_value, edit_type)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, 'timezone')
                            """,
                            user_id, job_id, asset_id,
                            full_output_path, field_name,
                            str(old_value) if old_value is not None else None,
                            new_value,
                        )
                    except Exception as log_exc:
                        logger.warning(f"tag_edits timezone log failed for asset {asset_id}: {log_exc}")

        succeeded += 1

    logger.info(
        f"Batch timezone: user='{username}' job={job_id} "
        f"from={body.from_tz} to={body.to_tz} total={total} succeeded={succeeded} failed={failed}"
    )
    return {"total": total, "succeeded": succeeded, "failed": failed}


# ============================================================
# Feature #15 — Friend Name Mapping & Aliases
# ============================================================


@router.get("/friends")
async def list_friends(
    request: Request,
    job_id: int | None = Query(None),
    username: str = Depends(get_current_user),
) -> list[dict]:
    """GET /api/friends — List friends from SQLite export + any user aliases.

    If job_id provided: use that job's SQLite (verifies ownership).
    If not: find the most recent completed job for the user.

    Returns list of {snap_username, original_name, alias, alias_id,
    merged_with, message_count, category}.
    """
    config = request.app.state.config
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        user_row = await conn.fetchrow(
            "SELECT id FROM users WHERE username = $1", username
        )
        if not user_row:
            raise HTTPException(404, "User not found")
        user_id = user_row["id"]

        if job_id is not None:
            owner = await conn.fetchval(
                """
                SELECT u.username FROM processing_jobs pj
                JOIN users u ON pj.user_id = u.id
                WHERE pj.id = $1
                """,
                job_id,
            )
            if owner != username:
                raise HTTPException(403, "Access denied")
        else:
            job_id = await conn.fetchval(
                """
                SELECT pj.id FROM processing_jobs pj
                WHERE pj.user_id = $1 AND pj.status = 'completed'
                ORDER BY pj.created_at DESC
                LIMIT 1
                """,
                user_id,
            )

        # Load all aliases from PostgreSQL for this user
        alias_rows = await conn.fetch(
            """
            SELECT id, snap_username, display_name, merged_with
            FROM friend_aliases
            WHERE user_id = $1
            """,
            user_id,
        )

    # Build alias lookup: snap_username -> {alias_id, alias, merged_with}
    alias_map: dict[str, dict] = {}
    for ar in alias_rows:
        alias_map[ar["snap_username"]] = {
            "alias_id": ar["id"],
            "alias": ar["display_name"],
            "merged_with": ar["merged_with"],
        }

    if job_id is None:
        # No completed jobs yet — return aliases only
        result = []
        for snap_username, a in alias_map.items():
            result.append({
                "snap_username": snap_username,
                "original_name": None,
                "alias": a["alias"],
                "alias_id": a["alias_id"],
                "merged_with": a["merged_with"],
                "message_count": 0,
                "category": None,
            })
        return result

    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    loop = asyncio.get_running_loop()

    def _load_sqlite_friends():
        if not db_path.exists():
            return [], {}, set()

        conn_sq = sqlite3.connect(str(db_path))
        conn_sq.row_factory = sqlite3.Row

        try:
            friend_rows = conn_sq.execute(
                "SELECT username, display_name, category FROM friends ORDER BY display_name"
            ).fetchall()
        except Exception:
            friend_rows = []

        try:
            msg_rows = conn_sq.execute(
                """
                SELECT from_user, COUNT(*) as cnt
                FROM chat_messages
                GROUP BY from_user
                """
            ).fetchall()
        except Exception:
            msg_rows = []

        try:
            all_senders = conn_sq.execute(
                "SELECT DISTINCT from_user FROM chat_messages WHERE from_user IS NOT NULL"
            ).fetchall()
        except Exception:
            all_senders = []

        conn_sq.close()

        friends = [dict(r) for r in friend_rows]
        msg_counts = {r["from_user"]: r["cnt"] for r in msg_rows}
        sender_set = {r["from_user"] for r in all_senders}
        return friends, msg_counts, sender_set

    friends, msg_counts, sender_set = await loop.run_in_executor(None, _load_sqlite_friends)

    # Merge SQLite friends with PostgreSQL aliases
    seen_usernames: set[str] = set()
    result: list[dict] = []

    for f in friends:
        snap_username = f["username"]
        seen_usernames.add(snap_username)
        a = alias_map.get(snap_username, {})
        result.append({
            "snap_username": snap_username,
            "original_name": f["display_name"],
            "alias": a.get("alias"),
            "alias_id": a.get("alias_id"),
            "merged_with": a.get("merged_with"),
            "message_count": msg_counts.get(snap_username, 0),
            "category": f.get("category"),
        })

    # Add alias-only entries (aliases for usernames not in friends table)
    for snap_username, a in alias_map.items():
        if snap_username not in seen_usernames:
            seen_usernames.add(snap_username)
            result.append({
                "snap_username": snap_username,
                "original_name": None,
                "alias": a["alias"],
                "alias_id": a["alias_id"],
                "merged_with": a["merged_with"],
                "message_count": msg_counts.get(snap_username, 0),
                "category": None,
            })

    # Add unknown senders (in chat_messages but not in friends or aliases)
    for sender in sorted(sender_set):
        if sender and sender not in seen_usernames:
            seen_usernames.add(sender)
            a = alias_map.get(sender, {})
            result.append({
                "snap_username": sender,
                "original_name": None,
                "alias": a.get("alias"),
                "alias_id": a.get("alias_id"),
                "merged_with": a.get("merged_with"),
                "message_count": msg_counts.get(sender, 0),
                "category": "unknown_sender",
            })

    return result


class FriendAliasBody(BaseModel):
    snap_username: str
    display_name: str
    merged_with: str | None = None  # username this is merged into


@router.post("/friends/alias")
async def upsert_friend_alias(
    body: FriendAliasBody,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """POST /api/friends/alias — Create or update a friend display name alias.

    Upserts into friend_aliases (ON CONFLICT DO UPDATE).
    Returns the alias record with id, snap_username, display_name, merged_with.
    """
    pool = request.app.state.db_pool

    if not body.snap_username.strip():
        raise HTTPException(400, "snap_username must not be empty")
    if not body.display_name.strip():
        raise HTTPException(400, "display_name must not be empty")

    async with pool.acquire() as conn:
        user_id = await conn.fetchval(
            "SELECT id FROM users WHERE username = $1", username
        )
        if not user_id:
            raise HTTPException(404, "User not found")

        row = await conn.fetchrow(
            """
            INSERT INTO friend_aliases (user_id, snap_username, display_name, merged_with)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id, snap_username) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                merged_with  = COALESCE(friend_aliases.merged_with, EXCLUDED.merged_with),
                updated_at   = NOW()
            RETURNING id, snap_username, display_name, merged_with, created_at, updated_at
            """,
            user_id,
            body.snap_username.strip(),
            body.display_name.strip(),
            body.merged_with,
        )

    d = dict(row)
    if d.get("created_at"):
        d["created_at"] = d["created_at"].isoformat()
    if d.get("updated_at"):
        d["updated_at"] = d["updated_at"].isoformat()

    logger.info(
        f"Friend alias upserted: user='{username}' snap_username='{body.snap_username}' "
        f"display_name='{body.display_name}'"
    )
    return d


@router.delete("/friends/alias/{alias_id}")
async def delete_friend_alias(
    alias_id: int,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """DELETE /api/friends/alias/{alias_id} — Delete a friend alias (revert to original name).

    Verifies ownership before deletion.
    """
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        owner = await conn.fetchval(
            """
            SELECT u.username FROM friend_aliases fa
            JOIN users u ON fa.user_id = u.id
            WHERE fa.id = $1
            """,
            alias_id,
        )

        if owner is None:
            raise HTTPException(404, "Alias not found")
        if owner != username:
            raise HTTPException(403, "Access denied")

        await conn.execute("DELETE FROM friend_aliases WHERE id = $1", alias_id)

    logger.info(f"Friend alias deleted: user='{username}' alias_id={alias_id}")
    return {"deleted": True, "alias_id": alias_id}


class ApplyNamesBody(BaseModel):
    job_id: int
    # [{snap_username, new_display_name}] — or empty list to apply all saved aliases
    aliases: list[dict]


@router.post("/friends/apply")
async def apply_friend_names(
    body: ApplyNamesBody,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """POST /api/friends/apply — Apply friend name corrections to output files.

    For each alias: finds assets in SQLite where matches.creator_str or
    matches.display_name matches the snap_username. Updates XMP:Creator tag
    on those output files via write_tags(). Logs to tag_edits with edit_type='batch'.
    Returns {total_assets_updated, aliases_applied}.
    """
    config = request.app.state.config
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        job_row = await conn.fetchrow(
            """
            SELECT pj.id, u.id as user_id, u.username
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            body.job_id, username,
        )
        if not job_row:
            raise HTTPException(403, "Access denied to job")

        user_id = job_row["user_id"]

        if not body.aliases:
            alias_rows = await conn.fetch(
                """
                SELECT snap_username, display_name
                FROM friend_aliases
                WHERE user_id = $1
                """,
                user_id,
            )
            aliases_to_apply = [
                {
                    "snap_username": r["snap_username"],
                    "new_display_name": r["display_name"],
                }
                for r in alias_rows
            ]
        else:
            aliases_to_apply = body.aliases

    if not aliases_to_apply:
        return {"total_assets_updated": 0, "aliases_applied": 0}

    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    if not db_path.exists():
        raise HTTPException(404, "No asset database found")

    output_dir = Path(str(config.server.data_dir)) / username / "output"
    loop = asyncio.get_running_loop()
    total_assets_updated = 0
    aliases_applied = 0

    for alias_entry in aliases_to_apply:
        snap_username = alias_entry.get("snap_username", "")
        new_display_name = alias_entry.get("new_display_name", "")
        if not snap_username or not new_display_name:
            continue

        def _find_assets(su=snap_username):
            conn_sq = sqlite3.connect(str(db_path))
            conn_sq.row_factory = sqlite3.Row
            try:
                rows = conn_sq.execute(
                    """
                    SELECT DISTINCT a.id, a.output_path
                    FROM assets a
                    LEFT JOIN matches m ON m.asset_id = a.id
                    WHERE a.output_path IS NOT NULL
                      AND (m.creator_str = ? OR m.display_name = ?)
                    """,
                    (su, su),
                ).fetchall()
            except Exception:
                rows = []
            conn_sq.close()
            return [dict(r) for r in rows]

        asset_rows = await loop.run_in_executor(None, _find_assets)

        if not asset_rows:
            continue

        alias_updated = 0
        for asset in asset_rows:
            raw_path = asset.get("output_path") or ""
            if not raw_path:
                continue
            full_path = (
                raw_path if os.path.isabs(raw_path) else str(output_dir / raw_path)
            )
            if not os.path.isfile(full_path):
                continue

            try:
                old_values = await tags_module.read_tags_before_edit(
                    full_path, ["XMP:Creator"]
                )
                write_result = await tags_module.write_tags(
                    full_path, {"XMP:Creator": new_display_name}
                )
            except Exception as exc:
                logger.warning(
                    f"apply_friend_names: failed to update asset {asset['id']}: {exc}"
                )
                continue

            if not write_result.get("success"):
                logger.warning(
                    f"apply_friend_names: exiftool failed for asset {asset['id']}: "
                    f"{write_result.get('message')}"
                )
                continue

            old_val = old_values.get("XMP:Creator")
            async with pool.acquire() as conn:
                try:
                    await conn.execute(
                        """
                        INSERT INTO tag_edits
                            (user_id, job_id, asset_id, file_path,
                             field_name, old_value, new_value, edit_type)
                        VALUES ($1, $2, $3, $4, 'XMP:Creator', $5, $6, 'batch')
                        """,
                        user_id, body.job_id, asset["id"], full_path,
                        str(old_val) if old_val is not None else None,
                        new_display_name,
                    )
                except Exception as exc:
                    logger.error(
                        f"apply_friend_names: failed to log tag_edit for asset "
                        f"{asset['id']}: {exc}"
                    )

            alias_updated += 1

        if alias_updated > 0:
            aliases_applied += 1
            total_assets_updated += alias_updated

    logger.info(
        f"apply_friend_names: user='{username}' job={body.job_id} "
        f"aliases_applied={aliases_applied} total_assets_updated={total_assets_updated}"
    )
    return {
        "total_assets_updated": total_assets_updated,
        "aliases_applied": aliases_applied,
    }


class MergeFriendsBody(BaseModel):
    primary_username: str   # the username to keep
    merge_username: str     # the username to be merged into primary


@router.post("/friends/merge")
async def merge_friends(
    body: MergeFriendsBody,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """POST /api/friends/merge — Mark two usernames as the same person.

    Sets merged_with on the merge_username alias pointing to primary_username.
    Creates the alias if it does not yet exist (preserving any existing display_name).
    """
    pool = request.app.state.db_pool

    if body.primary_username == body.merge_username:
        raise HTTPException(400, "primary_username and merge_username must be different")
    if not body.primary_username.strip() or not body.merge_username.strip():
        raise HTTPException(400, "Both usernames must be non-empty")

    async with pool.acquire() as conn:
        user_id = await conn.fetchval(
            "SELECT id FROM users WHERE username = $1", username
        )
        if not user_id:
            raise HTTPException(404, "User not found")

        # Preserve any existing display_name for merge_username
        existing_display = await conn.fetchval(
            """
            SELECT display_name FROM friend_aliases
            WHERE user_id = $1 AND snap_username = $2
            """,
            user_id, body.merge_username.strip(),
        )
        display_name_to_use = existing_display or body.merge_username.strip()

        row = await conn.fetchrow(
            """
            INSERT INTO friend_aliases (user_id, snap_username, display_name, merged_with)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id, snap_username) DO UPDATE SET
                merged_with = EXCLUDED.merged_with,
                updated_at  = NOW()
            RETURNING id, snap_username, display_name, merged_with
            """,
            user_id,
            body.merge_username.strip(),
            display_name_to_use,
            body.primary_username.strip(),
        )

    d = dict(row)
    logger.info(
        f"Friend merge: user='{username}' merge='{body.merge_username}' "
        f"into='{body.primary_username}'"
    )
    return {
        "merged": True,
        "merge_username": body.merge_username,
        "primary_username": body.primary_username,
        "alias_id": d["id"],
    }


# ============================================================
# Feature #16 — Privacy Redaction Tool
# ============================================================


class RedactionProfileBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = ""
    rules_json: list[dict]


@router.get("/redaction-profiles")
async def list_redaction_profiles(
    request: Request,
    username: str = Depends(get_current_user),
) -> list[dict]:
    """GET /api/redaction-profiles — List authenticated user's saved redaction profiles."""
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        user_id = await conn.fetchval("SELECT id FROM users WHERE username = $1", username)
        if not user_id:
            raise HTTPException(404, "User not found")

        rows = await conn.fetch(
            """
            SELECT id, name, description, rules_json, created_at, updated_at
            FROM redaction_profiles
            WHERE user_id = $1
            ORDER BY created_at DESC
            """,
            user_id,
        )

    result = []
    for row in rows:
        d = dict(row)
        d["created_at"] = str(d["created_at"]) if d.get("created_at") else None
        d["updated_at"] = str(d["updated_at"]) if d.get("updated_at") else None
        result.append(d)
    return result


@router.post("/redaction-profiles")
async def create_redaction_profile(
    body: RedactionProfileBody,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """POST /api/redaction-profiles — Create a new redaction profile."""
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        user_id = await conn.fetchval("SELECT id FROM users WHERE username = $1", username)
        if not user_id:
            raise HTTPException(404, "User not found")

        row = await conn.fetchrow(
            """
            INSERT INTO redaction_profiles (user_id, name, description, rules_json)
            VALUES ($1, $2, $3, $4)
            RETURNING id, name, description, rules_json, created_at, updated_at
            """,
            user_id, body.name, body.description, json.dumps(body.rules_json),
        )

    d = dict(row)
    d["created_at"] = str(d["created_at"]) if d.get("created_at") else None
    d["updated_at"] = str(d["updated_at"]) if d.get("updated_at") else None
    logger.info(f"Redaction profile created: user='{username}' id={d['id']} name='{body.name}'")
    return d


@router.put("/redaction-profiles/{profile_id}")
async def update_redaction_profile(
    profile_id: int,
    body: RedactionProfileBody,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """PUT /api/redaction-profiles/{profile_id} — Update a saved redaction profile.

    Verifies ownership before updating.
    """
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        user_id = await conn.fetchval("SELECT id FROM users WHERE username = $1", username)
        if not user_id:
            raise HTTPException(404, "User not found")

        owner_id = await conn.fetchval(
            "SELECT user_id FROM redaction_profiles WHERE id = $1", profile_id
        )
        if owner_id is None:
            raise HTTPException(404, "Profile not found")
        if owner_id != user_id:
            raise HTTPException(403, "Access denied")

        row = await conn.fetchrow(
            """
            UPDATE redaction_profiles
            SET name = $1, description = $2, rules_json = $3, updated_at = NOW()
            WHERE id = $4
            RETURNING id, name, description, rules_json, created_at, updated_at
            """,
            body.name, body.description, json.dumps(body.rules_json), profile_id,
        )

    d = dict(row)
    d["created_at"] = str(d["created_at"]) if d.get("created_at") else None
    d["updated_at"] = str(d["updated_at"]) if d.get("updated_at") else None
    logger.info(f"Redaction profile updated: user='{username}' id={profile_id}")
    return d


@router.delete("/redaction-profiles/{profile_id}")
async def delete_redaction_profile(
    profile_id: int,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """DELETE /api/redaction-profiles/{profile_id} — Delete a saved redaction profile.

    Verifies ownership before deleting.
    """
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        user_id = await conn.fetchval("SELECT id FROM users WHERE username = $1", username)
        if not user_id:
            raise HTTPException(404, "User not found")

        owner_id = await conn.fetchval(
            "SELECT user_id FROM redaction_profiles WHERE id = $1", profile_id
        )
        if owner_id is None:
            raise HTTPException(404, "Profile not found")
        if owner_id != user_id:
            raise HTTPException(403, "Access denied")

        await conn.execute("DELETE FROM redaction_profiles WHERE id = $1", profile_id)

    logger.info(f"Redaction profile deleted: user='{username}' id={profile_id}")
    return {"deleted": True, "id": profile_id}


# ---------------------------------------------------------------------------
# Redaction tag resolution helpers
# ---------------------------------------------------------------------------

_GPS_TAGS = [
    "EXIF:GPSLatitude", "EXIF:GPSLongitude", "EXIF:GPSLatitudeRef",
    "EXIF:GPSLongitudeRef", "EXIF:GPSAltitude", "EXIF:GPSDateStamp",
    "EXIF:GPSTimeStamp", "Composite:GPSPosition",
    "XMP:GPSLatitude", "XMP:GPSLongitude",
]
_CREATOR_TAGS = [
    "XMP:Creator", "EXIF:Artist", "IPTC:By-line",
]
_DATE_TAGS = [
    "EXIF:DateTimeOriginal", "EXIF:CreateDate", "EXIF:ModifyDate",
    "QuickTime:CreateDate", "QuickTime:ModifyDate",
    "XMP:DateTimeOriginal", "XMP:CreateDate",
]


def _redact_tags_for_rule(rule: dict, existing_tags: dict) -> list[str]:
    """Return tag names to strip for a single rule dict.

    Supports: strip_gps, strip_creator, strip_dates, strip_field, strip_all_custom.
    Only returns tags that are actually present in existing_tags.
    """
    action = rule.get("action", "")
    if action == "strip_gps":
        return [t for t in _GPS_TAGS if t in existing_tags]
    if action == "strip_creator":
        return [t for t in _CREATOR_TAGS if t in existing_tags]
    if action == "strip_dates":
        return [t for t in _DATE_TAGS if t in existing_tags]
    if action == "strip_field":
        field = rule.get("field", "")
        return [field] if field and field in existing_tags else []
    if action == "strip_all_custom":
        return [k for k in existing_tags
                if k.startswith("snatched:") or k.startswith("XMP-snatched:")]
    return []


def _redact_resolve_path(asset: dict, output_dir: Path) -> str | None:
    """Return absolute output path for an asset dict, or None if unresolvable."""
    raw = asset.get("output_path") or asset.get("path") or ""
    if not raw:
        return None
    return raw if os.path.isabs(raw) else str(output_dir / raw)


# ---------------------------------------------------------------------------
# Preview redaction — read-only
# ---------------------------------------------------------------------------

class RedactPreviewBody(BaseModel):
    asset_ids: list[int]
    rules: list[dict]


@router.post("/assets/redact/preview")
async def redact_preview(
    body: RedactPreviewBody,
    job_id: int = Query(...),
    request: Request = None,
    username: str = Depends(get_current_user),
) -> dict:
    """POST /api/assets/redact/preview?job_id=42 — Show what tags would be stripped.

    READ-ONLY — does not modify any files. Returns per-asset tag lists.
    """
    config = request.app.state.config
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        owner = await conn.fetchval(
            "SELECT u.username FROM processing_jobs pj JOIN users u ON pj.user_id = u.id WHERE pj.id = $1",
            job_id,
        )
    if owner != username:
        raise HTTPException(403, "Access denied")

    if not body.asset_ids or not body.rules:
        return {"total_assets": 0, "total_tags_to_strip": 0, "per_asset": []}

    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    if not db_path.exists():
        raise HTTPException(404, "Asset database not found")

    output_dir = Path(str(config.server.data_dir)) / username / "output"
    loop = asyncio.get_running_loop()

    def _lookup_assets_preview(ids: list[int]) -> list[dict]:
        conn_sq = sqlite3.connect(str(db_path))
        conn_sq.row_factory = sqlite3.Row
        placeholders = ",".join("?" * len(ids))
        rows = conn_sq.execute(
            f"SELECT id, output_path, path FROM assets WHERE id IN ({placeholders})",
            ids,
        ).fetchall()
        conn_sq.close()
        return [dict(r) for r in rows]

    asset_rows = await loop.run_in_executor(None, _lookup_assets_preview, body.asset_ids)

    per_asset = []
    total_stripped = 0

    for asset in asset_rows:
        full_path = _redact_resolve_path(asset, output_dir)
        if not full_path or not os.path.isfile(full_path):
            per_asset.append({
                "asset_id": asset["id"],
                "tags_to_strip": [],
                "error": "File not found",
            })
            continue

        existing_tags = await tags_module.read_tags(full_path)

        tags_to_strip: list[str] = []
        seen: set[str] = set()
        for rule in body.rules:
            for tag in _redact_tags_for_rule(rule, existing_tags):
                if tag not in seen:
                    seen.add(tag)
                    tags_to_strip.append(tag)

        per_asset.append({"asset_id": asset["id"], "tags_to_strip": tags_to_strip})
        total_stripped += len(tags_to_strip)

    return {
        "total_assets": len(per_asset),
        "total_tags_to_strip": total_stripped,
        "per_asset": per_asset,
    }


# ---------------------------------------------------------------------------
# Apply redaction
# ---------------------------------------------------------------------------

class RedactApplyBody(BaseModel):
    asset_ids: list[int]            # empty = all assets in job
    profile_id: int | None = None   # use saved profile
    rules: list[dict] | None = None  # or inline rules


@router.post("/assets/redact/apply")
async def apply_redaction(
    body: RedactApplyBody,
    job_id: int = Query(...),
    request: Request = None,
    username: str = Depends(get_current_user),
) -> dict:
    """POST /api/assets/redact/apply?job_id=42 — Apply redaction rules to assets.

    Strips the resolved tags from each output file via write_tags(tag, None).
    Logs every stripped field to tag_edits with new_value=NULL and edit_type='batch'.
    Returns {total, succeeded, failed, tags_stripped}.
    """
    config = request.app.state.config
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT pj.id, u.id as user_id
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )
    if not row:
        raise HTTPException(403, "Access denied")

    user_id = row["user_id"]

    # Resolve rules: saved profile takes precedence over inline rules
    rules: list[dict] = []
    if body.profile_id is not None:
        async with pool.acquire() as conn:
            profile = await conn.fetchrow(
                "SELECT rules_json, user_id FROM redaction_profiles WHERE id = $1",
                body.profile_id,
            )
        if not profile:
            raise HTTPException(404, "Profile not found")
        if profile["user_id"] != user_id:
            raise HTTPException(403, "Access denied to profile")
        raw = profile["rules_json"]
        rules = json.loads(raw) if isinstance(raw, str) else (raw or [])
    elif body.rules:
        rules = body.rules
    else:
        raise HTTPException(400, "Provide either profile_id or rules")

    if not rules:
        raise HTTPException(400, "No redaction rules provided")

    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    if not db_path.exists():
        raise HTTPException(404, "Asset database not found")

    output_dir = Path(str(config.server.data_dir)) / username / "output"
    loop = asyncio.get_running_loop()

    # Empty asset_ids means apply to all assets in the job
    asset_ids = list(body.asset_ids)
    if not asset_ids:
        def _all_asset_ids():
            conn_sq = sqlite3.connect(str(db_path))
            conn_sq.row_factory = sqlite3.Row
            ids = [r["id"] for r in conn_sq.execute("SELECT id FROM assets ORDER BY id").fetchall()]
            conn_sq.close()
            return ids
        asset_ids = await loop.run_in_executor(None, _all_asset_ids)

    if not asset_ids:
        return {"total": 0, "succeeded": 0, "failed": 0, "tags_stripped": 0}

    def _lookup_assets_apply(ids: list[int]) -> list[dict]:
        conn_sq = sqlite3.connect(str(db_path))
        conn_sq.row_factory = sqlite3.Row
        placeholders = ",".join("?" * len(ids))
        rows = conn_sq.execute(
            f"SELECT id, output_path, path FROM assets WHERE id IN ({placeholders})",
            ids,
        ).fetchall()
        conn_sq.close()
        return [dict(r) for r in rows]

    asset_rows = await loop.run_in_executor(None, _lookup_assets_apply, asset_ids)

    succeeded = 0
    failed = 0
    total_tags_stripped = 0

    for asset in asset_rows:
        full_path = _redact_resolve_path(asset, output_dir)
        if not full_path or not os.path.isfile(full_path):
            failed += 1
            logger.warning(f"Redact: file not found for asset {asset['id']}: {full_path}")
            continue

        try:
            existing_tags = await tags_module.read_tags(full_path)
        except Exception as exc:
            failed += 1
            logger.warning(f"Redact: read_tags failed for asset {asset['id']}: {exc}")
            continue

        # Collect deduplicated set of tags to strip
        tags_to_strip: list[str] = []
        seen: set[str] = set()
        for rule in rules:
            for tag in _redact_tags_for_rule(rule, existing_tags):
                if tag not in seen:
                    seen.add(tag)
                    tags_to_strip.append(tag)

        if not tags_to_strip:
            succeeded += 1
            continue

        # Capture old values for audit trail before stripping
        old_values = {
            tag: str(existing_tags[tag]) if tag in existing_tags else None
            for tag in tags_to_strip
        }

        write_result = await tags_module.write_tags(full_path, {tag: None for tag in tags_to_strip})

        if not write_result["success"]:
            failed += 1
            logger.warning(
                f"Redact: write_tags failed for asset {asset['id']}: {write_result['message']}"
            )
            continue

        succeeded += 1
        total_tags_stripped += len(tags_to_strip)

        async with pool.acquire() as conn:
            for field_name in tags_to_strip:
                old_val = old_values.get(field_name)
                await conn.execute(
                    """
                    INSERT INTO tag_edits
                        (user_id, job_id, asset_id, file_path, field_name,
                         old_value, new_value, edit_type)
                    VALUES ($1, $2, $3, $4, $5, $6, NULL, 'batch')
                    """,
                    user_id, job_id, asset["id"], full_path, field_name, old_val,
                )

    logger.info(
        f"Redact apply: user='{username}' job={job_id} total={len(asset_rows)} "
        f"succeeded={succeeded} failed={failed} tags_stripped={total_tags_stripped}"
    )
    return {
        "total": len(asset_rows),
        "succeeded": succeeded,
        "failed": failed,
        "tags_stripped": total_tags_stripped,
    }


# ---------------------------------------------------------------------------
# Match Configuration — Feature #17 & #18
# ---------------------------------------------------------------------------

class MatchPreferencesBody(BaseModel):
    match_confidence_min: float = Field(default=0.0, ge=0.0, le=1.0)
    strategy_weights_json: dict = Field(default_factory=dict)


class PipelineConfigBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    config_json: dict = Field(default_factory=dict)


@router.get("/jobs/{job_id}/match-config")
async def get_match_config(
    job_id: int,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """GET /api/jobs/{job_id}/match-config — Returns current match configuration data.

    Returns histogram buckets, strategy counts, current threshold, and current weights.
    """
    config = request.app.state.config
    pool = request.app.state.db_pool

    # Verify job ownership
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT pj.id, u.id as user_id
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )

    if not row:
        raise HTTPException(404, "Job not found")

    user_id = row["user_id"]

    # Load user preferences
    async with pool.acquire() as conn:
        prefs_row = await conn.fetchrow(
            """
            SELECT match_confidence_min, strategy_weights_json
            FROM user_preferences
            WHERE user_id = $1
            """,
            user_id,
        )

    current_threshold = float(prefs_row["match_confidence_min"]) if prefs_row and prefs_row["match_confidence_min"] is not None else 0.0
    current_weights = prefs_row["strategy_weights_json"] if prefs_row and prefs_row["strategy_weights_json"] else {}
    if isinstance(current_weights, str):
        current_weights = json.loads(current_weights)

    # Load match data from per-user SQLite
    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    loop = asyncio.get_running_loop()

    def _load_match_data():
        if not db_path.exists():
            return {}, []

        conn_sq = sqlite3.connect(str(db_path))
        conn_sq.row_factory = sqlite3.Row

        try:
            # Strategy counts + avg confidence
            strategy_rows = conn_sq.execute(
                """
                SELECT strategy, COUNT(*) as count,
                       AVG(confidence) as avg_confidence,
                       SUM(CASE WHEN is_best = 1 THEN 1 ELSE 0 END) as best_count
                FROM matches
                GROUP BY strategy
                ORDER BY avg_confidence DESC
                """
            ).fetchall()
        except Exception:
            strategy_rows = []

        try:
            # All confidence scores for histogram
            conf_rows = conn_sq.execute(
                "SELECT confidence FROM matches"
            ).fetchall()
        except Exception:
            conf_rows = []

        conn_sq.close()

        strategy_counts = {}
        for r in strategy_rows:
            strategy_counts[r["strategy"]] = {
                "count": r["count"],
                "avg_confidence": round(float(r["avg_confidence"] or 0), 3),
                "best_count": r["best_count"],
            }

        confidences = [float(r["confidence"]) for r in conf_rows]
        return strategy_counts, confidences

    strategy_counts, confidences = await loop.run_in_executor(None, _load_match_data)

    # Build histogram: 10 buckets 0-10%, 10-20%, ..., 90-100%
    buckets = [0] * 10
    for c in confidences:
        idx = min(int(c * 10), 9)
        buckets[idx] += 1

    histogram = []
    for i, count in enumerate(buckets):
        histogram.append({
            "label": f"{i * 10}-{(i + 1) * 10}%",
            "min": round(i * 0.1, 1),
            "max": round((i + 1) * 0.1, 1),
            "count": count,
        })

    return {
        "job_id": job_id,
        "histogram": histogram,
        "total_matches": len(confidences),
        "strategy_counts": strategy_counts,
        "current_threshold": current_threshold,
        "current_weights": current_weights,
    }


@router.put("/match-preferences")
async def save_match_preferences(
    body: MatchPreferencesBody,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """PUT /api/match-preferences — Save threshold + strategy weights to user_preferences."""
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        user_id = await conn.fetchval(
            "SELECT id FROM users WHERE username = $1", username
        )
        if not user_id:
            raise HTTPException(404, "User not found")

        await conn.execute(
            """
            UPDATE user_preferences
            SET match_confidence_min = $2,
                strategy_weights_json = $3
            WHERE user_id = $1
            """,
            user_id,
            body.match_confidence_min,
            json.dumps(body.strategy_weights_json),
        )

    logger.info(
        f"match-preferences saved: user='{username}' threshold={body.match_confidence_min} "
        f"strategies={list(body.strategy_weights_json.keys())}"
    )
    return {"saved": True, "match_confidence_min": body.match_confidence_min}


@router.post("/pipeline-configs")
async def create_pipeline_config(
    body: PipelineConfigBody,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """POST /api/pipeline-configs — Create a named pipeline config preset."""
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        user_id = await conn.fetchval(
            "SELECT id FROM users WHERE username = $1", username
        )
        if not user_id:
            raise HTTPException(404, "User not found")

        new_id = await conn.fetchval(
            """
            INSERT INTO pipeline_configs (user_id, name, description, config_json)
            VALUES ($1, $2, $3, $4)
            RETURNING id
            """,
            user_id,
            body.name,
            body.description,
            json.dumps(body.config_json),
        )

    logger.info(f"pipeline-config created: user='{username}' id={new_id} name='{body.name}'")
    return {"id": new_id, "name": body.name}


@router.get("/pipeline-configs")
async def list_pipeline_configs(
    request: Request,
    username: str = Depends(get_current_user),
) -> list[dict]:
    """GET /api/pipeline-configs — List user's pipeline config presets."""
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT pc.id, pc.name, pc.description, pc.config_json,
                   pc.is_default, pc.created_at, pc.updated_at
            FROM pipeline_configs pc
            JOIN users u ON pc.user_id = u.id
            WHERE u.username = $1
            ORDER BY pc.created_at DESC
            """,
            username,
        )

    result = []
    for row in rows:
        d = dict(row)
        if d.get("created_at"):
            d["created_at"] = d["created_at"].isoformat()
        if d.get("updated_at"):
            d["updated_at"] = d["updated_at"].isoformat()
        cfg = d.get("config_json") or {}
        if isinstance(cfg, str):
            cfg = json.loads(cfg)
        d["config_json"] = cfg
        result.append(d)

    return result


@router.delete("/pipeline-configs/{config_id}")
async def delete_pipeline_config(
    config_id: int,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """DELETE /api/pipeline-configs/{config_id} — Delete a pipeline config preset."""
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        # Verify ownership before delete
        existing = await conn.fetchrow(
            """
            SELECT pc.id FROM pipeline_configs pc
            JOIN users u ON pc.user_id = u.id
            WHERE pc.id = $1 AND u.username = $2
            """,
            config_id, username,
        )
        if not existing:
            raise HTTPException(404, "Pipeline config not found")

        await conn.execute(
            "DELETE FROM pipeline_configs WHERE id = $1",
            config_id,
        )

    logger.info(f"pipeline-config deleted: user='{username}' id={config_id}")
    return {"deleted": True, "id": config_id}


@router.get("/jobs/{job_id}/dry-run-summary")
async def dry_run_summary(
    job_id: int,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """GET /api/jobs/{job_id}/dry-run-summary — Dry run analysis for a job.

    Returns match stats, strategy breakdown, confidence histogram, and a
    preview of the folder/file tree that *would* be generated if export ran.
    Only valid for jobs that skipped the export phase.
    """
    config = request.app.state.config
    pool = request.app.state.db_pool

    # Verify job ownership
    async with pool.acquire() as conn:
        job = await conn.fetchrow(
            """
            SELECT pj.id, pj.status, pj.phases_requested, pj.stats_json
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )

    if not job:
        raise HTTPException(404, "Job not found")

    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    loop = asyncio.get_running_loop()

    def _compute_summary():
        if not db_path.exists():
            return {
                "total_assets": 0,
                "matched_assets": 0,
                "match_rate": 0.0,
                "gps_coverage": 0.0,
                "strategies": [],
                "histogram": [],
                "unmatched_count": 0,
                "export_tree": [],
                "estimated_files": 0,
            }

        conn_sq = sqlite3.connect(str(db_path))
        conn_sq.row_factory = sqlite3.Row

        try:
            total_assets = conn_sq.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
        except Exception:
            total_assets = 0

        try:
            matched_assets = conn_sq.execute(
                "SELECT COUNT(DISTINCT asset_id) FROM matches WHERE is_best = 1"
            ).fetchone()[0]
        except Exception:
            matched_assets = 0

        try:
            gps_count = conn_sq.execute(
                """
                SELECT COUNT(DISTINCT asset_id)
                FROM matches
                WHERE is_best = 1
                  AND matched_lat IS NOT NULL
                  AND matched_lon IS NOT NULL
                """
            ).fetchone()[0]
        except Exception:
            gps_count = 0

        try:
            strategy_rows = conn_sq.execute(
                """
                SELECT strategy,
                       COUNT(*) as count,
                       AVG(confidence) as avg_confidence
                FROM matches
                WHERE is_best = 1
                GROUP BY strategy
                ORDER BY count DESC
                """
            ).fetchall()
            strategies = [
                {
                    "strategy": r["strategy"] or "unknown",
                    "count": r["count"],
                    "avg_confidence": round(float(r["avg_confidence"] or 0), 3),
                }
                for r in strategy_rows
            ]
        except Exception:
            strategies = []

        try:
            conf_rows = conn_sq.execute(
                """
                SELECT CAST(confidence * 10 AS INTEGER) as bucket,
                       COUNT(*) as count
                FROM matches
                WHERE is_best = 1
                GROUP BY bucket
                ORDER BY bucket
                """
            ).fetchall()
            histogram = [{"bucket": r["bucket"], "count": r["count"]} for r in conf_rows]
        except Exception:
            histogram = []

        try:
            tree_rows = conn_sq.execute(
                """
                SELECT output_subdir,
                       COUNT(*) as file_count
                FROM matches
                WHERE is_best = 1
                  AND output_subdir IS NOT NULL
                GROUP BY output_subdir
                ORDER BY output_subdir
                """
            ).fetchall()
            export_tree = [
                {"path": r["output_subdir"], "file_count": r["file_count"]}
                for r in tree_rows
            ]
            estimated_files = sum(r["file_count"] for r in tree_rows)
        except Exception:
            export_tree = []
            estimated_files = matched_assets

        conn_sq.close()

        match_rate = round(matched_assets / total_assets, 4) if total_assets else 0.0
        gps_coverage = round(gps_count / total_assets, 4) if total_assets else 0.0
        unmatched_count = total_assets - matched_assets

        return {
            "total_assets": total_assets,
            "matched_assets": matched_assets,
            "match_rate": match_rate,
            "gps_coverage": gps_coverage,
            "strategies": strategies,
            "histogram": histogram,
            "unmatched_count": unmatched_count,
            "export_tree": export_tree,
            "estimated_files": estimated_files,
        }

    return await loop.run_in_executor(None, _compute_summary)


@router.post("/jobs/{job_id}/promote")
async def promote_dry_run(
    job_id: int,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """POST /api/jobs/{job_id}/promote — Convert a dry run to a full export.

    Triggers reprocessing with phases=['export'] only, using the existing
    ingested and matched data. Returns the new job id.
    """
    pool = request.app.state.db_pool

    # Verify ownership and that this was a dry run (no export phase)
    async with pool.acquire() as conn:
        job = await conn.fetchrow(
            """
            SELECT pj.id, pj.status, pj.phases_requested, pj.user_id,
                   pj.upload_filename, pj.lanes_requested
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )

    if not job:
        raise HTTPException(404, "Job not found")

    phases = list(job["phases_requested"] or [])
    if "export" in phases:
        raise HTTPException(400, "Job already includes export phase — not a dry run")

    if job["status"] not in ("completed", "failed"):
        raise HTTPException(409, "Job must be completed before promoting to full export")

    # Create a new processing job with only the export phase
    new_job_id = await create_processing_job(
        pool=pool,
        user_id=job["user_id"],
        upload_filename=job["upload_filename"],
        upload_size_bytes=0,
        phases_requested=["export"],
        lanes_requested=list(job["lanes_requested"] or []),
    )

    logger.info(
        f"dry-run promoted: user='{username}' dry_run_job={job_id} new_job={new_job_id}"
    )
    return {"new_job_id": new_job_id, "source_job_id": job_id}


# ---------------------------------------------------------------------------
# Export Config — Feature #19 (Custom Output Folder Structure) &
#                 Feature #20 (Export Format Controls)
# ---------------------------------------------------------------------------

@router.get("/export-settings")
async def get_export_settings(
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """GET /api/export-settings — Get current export settings for the authenticated user.

    Returns folder_pattern, export_settings_json, and existing processing prefs.
    """
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT up.folder_pattern, up.export_settings_json,
                   up.burn_overlays, up.dark_mode_pngs, up.exif_enabled,
                   up.xmp_enabled, up.gps_window_seconds
            FROM user_preferences up
            JOIN users u ON up.user_id = u.id
            WHERE u.username = $1
            """,
            username,
        )

    if not row:
        return {
            "folder_pattern": "{YYYY}/{MM}",
            "export_settings_json": None,
            "burn_overlays": True,
            "dark_mode_pngs": False,
            "exif_enabled": True,
            "xmp_enabled": False,
            "gps_window_seconds": 300,
        }

    d = dict(row)
    if d.get("export_settings_json") and isinstance(d["export_settings_json"], str):
        d["export_settings_json"] = json.loads(d["export_settings_json"])
    return d


class ExportSettingsBody(BaseModel):
    folder_pattern: str = Field(default="{YYYY}/{MM}", max_length=512)
    export_settings_json: dict | None = Field(default=None)


@router.put("/export-settings")
async def put_export_settings(
    request: Request,
    body: ExportSettingsBody,
    username: str = Depends(get_current_user),
) -> dict:
    """PUT /api/export-settings — Save folder pattern and export format to user_preferences."""
    pool = request.app.state.db_pool

    export_json_str = json.dumps(body.export_settings_json) if body.export_settings_json is not None else None

    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE user_preferences
            SET folder_pattern = $1, export_settings_json = $2
            FROM users u
            WHERE user_preferences.user_id = u.id AND u.username = $3
            """,
            body.folder_pattern,
            export_json_str,
            username,
        )

    logger.info(f"export-settings saved: user='{username}' pattern='{body.folder_pattern}'")
    return {"saved": True}


class PreviewPathsBody(BaseModel):
    folder_pattern: str = Field(default="{YYYY}/{MM}", max_length=512)
    job_id: int | None = Field(default=None)


def _resolve_folder_pattern(pattern: str, variables: dict) -> str:
    """Resolve a folder pattern string using a dict of variable values.

    Handles {YYYY-MM-DD} before individual {YYYY}/{MM}/{DD} to avoid double-substitution.
    """
    result = pattern
    # Resolve compound token first
    if "{YYYY-MM-DD}" in result:
        yyyy = variables.get("YYYY", "????")
        mm = variables.get("MM", "??")
        dd = variables.get("DD", "??")
        full_date = variables.get("matched_date", "")[:10] or f"{yyyy}-{mm}-{dd}"
        result = result.replace("{YYYY-MM-DD}", full_date)
    result = result.replace("{YYYY}", variables.get("YYYY", "????"))
    result = result.replace("{MM}", variables.get("MM", "??"))
    result = result.replace("{DD}", variables.get("DD", "??"))
    result = result.replace("{friend_name}", variables.get("friend_name", "unknown"))
    result = result.replace("{type}", variables.get("type", "unknown"))
    result = result.replace("{lane}", variables.get("lane", "unknown"))
    return result


_MOCK_PREVIEW_SAMPLES = [
    {
        "filename": "snap_memory_abc123.jpg",
        "matched_date": "2024-07-04",
        "friend_name": "john_doe",
        "asset_type": "memory_main",
        "lane": "memories",
        "YYYY": "2024", "MM": "07", "DD": "04",
    },
    {
        "filename": "chat_msg_def456.jpg",
        "matched_date": "2023-12-25",
        "friend_name": "jane_smith",
        "asset_type": "chat",
        "lane": "chats",
        "YYYY": "2023", "MM": "12", "DD": "25",
    },
    {
        "filename": "story_ghi789.mp4",
        "matched_date": "2024-01-15",
        "friend_name": "my_story",
        "asset_type": "story",
        "lane": "stories",
        "YYYY": "2024", "MM": "01", "DD": "15",
    },
    {
        "filename": "snap_memory_jkl012.jpg",
        "matched_date": "2022-06-21",
        "friend_name": "alex_k",
        "asset_type": "memory_main",
        "lane": "memories",
        "YYYY": "2022", "MM": "06", "DD": "21",
    },
]

_LANE_MAP = {
    "memory_main": "memories",
    "memory_b": "memories",
    "chat": "chats",
    "story": "stories",
}


@router.post("/export-settings/preview-paths")
async def preview_export_paths(
    request: Request,
    body: PreviewPathsBody,
    username: str = Depends(get_current_user),
) -> dict:
    """POST /api/export-settings/preview-paths — Preview resolved folder paths for a pattern.

    If job_id is provided, loads up to 5 sample matches from the user's per-user SQLite.
    Otherwise uses mock sample data. Returns {paths: [{filename, resolved_path, variables}]}.
    """
    config = request.app.state.config
    pattern = body.folder_pattern
    samples: list[dict] = []

    if body.job_id is not None:
        pool = request.app.state.db_pool
        async with pool.acquire() as conn:
            job_row = await conn.fetchrow(
                """
                SELECT pj.id FROM processing_jobs pj
                JOIN users u ON pj.user_id = u.id
                WHERE pj.id = $1 AND u.username = $2
                """,
                body.job_id, username,
            )
        if not job_row:
            raise HTTPException(404, "Job not found")

        db_path = Path(str(config.server.data_dir)) / username / "proc.db"
        loop = asyncio.get_running_loop()

        def _load_samples():
            if not db_path.exists():
                return []
            conn_sq = sqlite3.connect(str(db_path))
            conn_sq.row_factory = sqlite3.Row
            try:
                rows = conn_sq.execute(
                    """
                    SELECT
                        a.filename,
                        a.asset_type,
                        m.matched_date,
                        m.creator_str,
                        m.display_name
                    FROM assets a
                    LEFT JOIN matches m ON m.asset_id = a.id AND m.is_best = 1
                    WHERE a.filename IS NOT NULL
                    ORDER BY a.id ASC
                    LIMIT 5
                    """
                ).fetchall()
            except Exception:
                rows = []
            conn_sq.close()
            return [dict(r) for r in rows]

        raw_rows = await loop.run_in_executor(None, _load_samples)

        for r in raw_rows:
            matched_date = r.get("matched_date") or ""
            date_parts = matched_date[:10].split("-") if len(matched_date) >= 10 else []
            samples.append({
                "filename": r.get("filename", "unknown.jpg"),
                "matched_date": matched_date,
                "friend_name": r.get("display_name") or r.get("creator_str") or "unknown",
                "asset_type": r.get("asset_type") or "unknown",
                "lane": _LANE_MAP.get(r.get("asset_type") or "", "unknown"),
                "YYYY": date_parts[0] if len(date_parts) > 0 else "????",
                "MM": date_parts[1] if len(date_parts) > 1 else "??",
                "DD": date_parts[2] if len(date_parts) > 2 else "??",
            })

    if not samples:
        samples = list(_MOCK_PREVIEW_SAMPLES)

    paths = []
    for s in samples:
        resolved_folder = _resolve_folder_pattern(pattern, s)
        paths.append({
            "filename": s["filename"],
            "resolved_path": f"{resolved_folder}/{s['filename']}",
            "variables": {
                "YYYY": s.get("YYYY", "????"),
                "MM": s.get("MM", "??"),
                "DD": s.get("DD", "??"),
                "friend_name": s.get("friend_name", "unknown"),
                "type": s.get("asset_type", "unknown"),
                "lane": s.get("lane", "unknown"),
                "YYYY-MM-DD": s.get("matched_date", "")[:10],
            },
        })

    return {"paths": paths}


# ============================================================
# P4 BROWSE & VISUALIZE — Insertion slots (agents replace these)
# ============================================================

# --- P4-SLOT-22: Memory Browser API ---

@router.get("/jobs/{job_id}/gallery")
async def gallery_json(
    request: Request,
    job_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(40, ge=1, le=200),
    date_start: str | None = Query(None),
    date_end: str | None = Query(None),
    asset_type: str | None = Query(None),
    lane: str | None = Query(None),
    confidence_min: float | None = Query(None, ge=0.0, le=1.0),
    search: str | None = Query(None),
    username: str = Depends(get_current_user),
) -> dict:
    """GET /api/jobs/{job_id}/gallery — Paginated gallery data as JSON.

    Query params: page, per_page, date_start, date_end, asset_type, lane,
    confidence_min (0.0-1.0), search (matches filename or display_name).

    Returns:
        {
            items: [{id, filename, asset_type, is_video, matched_date,
                     confidence, lane, has_gps, display_name, output_path}],
            total: int,
            page: int,
            pages: int,
        }
    """
    from pathlib import Path
    import sqlite3

    config = request.app.state.config
    pool = request.app.state.db_pool

    # Verify job ownership
    async with pool.acquire() as conn:
        owner = await conn.fetchval(
            """
            SELECT u.username FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1
            """,
            job_id,
        )
    if owner != username:
        raise HTTPException(403, "Access denied")

    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    if not db_path.exists():
        return {"items": [], "total": 0, "page": page, "pages": 0}

    loop = asyncio.get_running_loop()

    def _query_gallery():
        conn_sq = sqlite3.connect(str(db_path))
        conn_sq.row_factory = sqlite3.Row

        # Build WHERE clauses dynamically
        where_parts = ["m.is_best = 1"]
        params: list = []

        if date_start:
            where_parts.append("m.matched_date >= ?")
            params.append(date_start)
        if date_end:
            where_parts.append("m.matched_date <= ?")
            params.append(date_end + "T23:59:59")
        if asset_type:
            where_parts.append("a.asset_type = ?")
            params.append(asset_type)
        if lane:
            where_parts.append("m.lane = ?")
            params.append(lane)
        if confidence_min is not None and confidence_min > 0:
            where_parts.append("m.confidence >= ?")
            params.append(confidence_min)
        if search:
            like = "%" + search.replace("%", "\\%").replace("_", "\\_") + "%"
            where_parts.append("(a.filename LIKE ? ESCAPE '\\' OR m.display_name LIKE ? ESCAPE '\\')")
            params.extend([like, like])

        where_sql = " AND ".join(where_parts)

        base_query = f"""
            FROM assets a
            LEFT JOIN matches m ON m.asset_id = a.id
            WHERE {where_sql}
        """

        total = conn_sq.execute(
            f"SELECT COUNT(*) {base_query}", params
        ).fetchone()[0]

        pages = max(1, (total + per_page - 1) // per_page) if total > 0 else 0
        offset = (page - 1) * per_page

        rows = conn_sq.execute(
            f"""
            SELECT
                a.id,
                a.filename,
                a.asset_type,
                a.is_video,
                a.output_path,
                m.confidence,
                m.lane,
                m.matched_date,
                m.matched_lat,
                m.matched_lon,
                m.display_name
            {base_query}
            ORDER BY m.matched_date DESC NULLS LAST, a.id
            LIMIT ? OFFSET ?
            """,
            params + [per_page, offset],
        ).fetchall()
        conn_sq.close()

        items = []
        for r in rows:
            items.append({
                "id": r["id"],
                "filename": r["filename"],
                "asset_type": r["asset_type"],
                "is_video": bool(r["is_video"]),
                "matched_date": r["matched_date"],
                "confidence": r["confidence"],
                "lane": r["lane"],
                "has_gps": bool(r["matched_lat"] is not None and r["matched_lon"] is not None),
                "display_name": r["display_name"],
                "output_path": r["output_path"],
            })

        return items, total, pages

    items, total, pages = await loop.run_in_executor(None, _query_gallery)

    return {
        "items": items,
        "total": total,
        "page": page,
        "pages": pages,
    }


@router.get("/jobs/{job_id}/gallery/html", response_class=HTMLResponse)
async def gallery_html(
    request: Request,
    job_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(40, ge=1, le=200),
    date_start: str | None = Query(None),
    date_end: str | None = Query(None),
    asset_type: str | None = Query(None),
    lane: str | None = Query(None),
    confidence_min: float | None = Query(None, ge=0.0, le=1.0),
    search: str | None = Query(None),
    username: str = Depends(get_current_user),
) -> HTMLResponse:
    """GET /api/jobs/{job_id}/gallery/html — Gallery card fragment for htmx swap.

    Same filtering as /gallery JSON endpoint.  Returns an HTML fragment
    containing <div class="gallery-card"> elements and an optional
    "Load More" button if more pages exist.

    Response headers:
        X-Gallery-Total   — total matching assets
        X-Gallery-Showing — cumulative assets shown so far (page * per_page, capped at total)
    """
    from pathlib import Path
    import sqlite3

    config = request.app.state.config
    pool = request.app.state.db_pool

    # Verify job ownership
    async with pool.acquire() as conn:
        owner = await conn.fetchval(
            """
            SELECT u.username FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1
            """,
            job_id,
        )
    if owner != username:
        raise HTTPException(403, "Access denied")

    db_path = Path(str(config.server.data_dir)) / username / "proc.db"

    if not db_path.exists():
        html = (
            '<div class="gallery-empty" style="grid-column:1/-1;">'
            '<span class="material-symbols-outlined">inventory_2</span>'
            '<p>No database found for this job.</p>'
            '</div>'
        )
        return HTMLResponse(content=html, headers={"X-Gallery-Total": "0", "X-Gallery-Showing": "0"})

    loop = asyncio.get_running_loop()

    def _query_gallery():
        conn_sq = sqlite3.connect(str(db_path))
        conn_sq.row_factory = sqlite3.Row

        where_parts = ["m.is_best = 1"]
        params: list = []

        if date_start:
            where_parts.append("m.matched_date >= ?")
            params.append(date_start)
        if date_end:
            where_parts.append("m.matched_date <= ?")
            params.append(date_end + "T23:59:59")
        if asset_type:
            where_parts.append("a.asset_type = ?")
            params.append(asset_type)
        if lane:
            where_parts.append("m.lane = ?")
            params.append(lane)
        if confidence_min is not None and confidence_min > 0:
            where_parts.append("m.confidence >= ?")
            params.append(confidence_min)
        if search:
            like = "%" + search.replace("%", "\\%").replace("_", "\\_") + "%"
            where_parts.append("(a.filename LIKE ? ESCAPE '\\' OR m.display_name LIKE ? ESCAPE '\\')")
            params.extend([like, like])

        where_sql = " AND ".join(where_parts)
        base_query = f"""
            FROM assets a
            LEFT JOIN matches m ON m.asset_id = a.id
            WHERE {where_sql}
        """

        total = conn_sq.execute(
            f"SELECT COUNT(*) {base_query}", params
        ).fetchone()[0]

        pages = max(1, (total + per_page - 1) // per_page) if total > 0 else 0
        offset = (page - 1) * per_page

        rows = conn_sq.execute(
            f"""
            SELECT
                a.id,
                a.filename,
                a.asset_type,
                a.is_video,
                a.output_path,
                m.confidence,
                m.lane,
                m.matched_date,
                m.matched_lat,
                m.matched_lon,
                m.display_name
            {base_query}
            ORDER BY m.matched_date DESC NULLS LAST, a.id
            LIMIT ? OFFSET ?
            """,
            params + [per_page, offset],
        ).fetchall()
        conn_sq.close()
        return [dict(r) for r in rows], total, pages

    items, total, pages = await loop.run_in_executor(None, _query_gallery)

    showing = min(page * per_page, total)

    # --- Build HTML fragment ---
    def _conf_class(conf):
        if conf is None:
            return "none"
        if conf >= 0.8:
            return "high"
        if conf >= 0.5:
            return "mid"
        return "low"

    def _conf_label(conf):
        if conf is None:
            return "unmatched"
        return f"{int(round(conf * 100))}%"

    def _escape(s):
        if s is None:
            return ""
        return (
            str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    def _fmt_date(d):
        if not d:
            return ""
        # d may be "2021-05-14T12:34:56" or "2021-05-14 12:34:56"
        try:
            return str(d)[:10]
        except Exception:
            return str(d)

    if not items:
        html_parts = [
            '<div class="gallery-empty" style="grid-column:1/-1;">',
            '<span class="material-symbols-outlined">image_search</span>',
            "<p>No memories match the current filters.</p>",
            "</div>",
        ]
        html = "\n".join(html_parts)
        return HTMLResponse(
            content=html,
            headers={
                "X-Gallery-Total": str(total),
                "X-Gallery-Showing": "0",
            },
        )

    html_parts = []
    for item in items:
        asset_id = item["id"]
        filename = item["filename"] or ""
        asset_type = item["asset_type"] or "unknown"
        is_video = item.get("is_video", False)
        matched_date = item.get("matched_date")
        confidence = item.get("confidence")
        lane_val = item.get("lane") or ""
        has_gps = item.get("has_gps", False)
        display_name = item.get("display_name") or ""

        # Thumbnail icon
        if is_video:
            icon = "videocam"
        else:
            icon = "image"

        thumb_html = (
            '<div class="gallery-thumb">'
            f'<span class="material-symbols-outlined">{icon}</span>'
            "</div>"
        )

        # Confidence badge
        cc = _conf_class(confidence)
        cl = _conf_label(confidence)
        conf_badge = f'<span class="conf-badge {cc}">{_escape(cl)}</span>'

        # Lane pill
        lane_pill = ""
        if lane_val:
            lane_pill = f'<span class="lane-pill">{_escape(lane_val)}</span>'

        # GPS indicator
        gps_html = ""
        if has_gps:
            gps_html = (
                '<span class="gps-indicator">'
                '<span class="material-symbols-outlined">location_on</span>'
                "GPS"
                "</span>"
            )

        # Date line
        date_str = _fmt_date(matched_date)
        date_html = ""
        if date_str:
            date_html = f'<div class="gallery-card-date">{_escape(date_str)}</div>'

        # Display name (secondary label when different from filename)
        dn_html = ""
        if display_name and display_name != filename:
            dn_html = (
                f'<div class="gallery-card-date" style="color:var(--text-dim);">'
                f"{_escape(display_name[:40])}"
                "</div>"
            )

        card = (
            f'<a class="gallery-card" href="/assets/{job_id}/{asset_id}">'
            + thumb_html
            + '<div class="gallery-card-body">'
            + f'<div class="gallery-card-filename" title="{_escape(filename)}">{_escape(filename)}</div>'
            + date_html
            + dn_html
            + '<div class="gallery-card-badges">'
            + conf_badge
            + lane_pill
            + gps_html
            + "</div>"
            + "</div>"
            + "</a>"
        )
        html_parts.append(card)

    # Pagination — "Load More" button appended as a full-width grid item
    if page < pages:
        next_page = page + 1
        html_parts.append(
            '<div id="load-more-container" style="grid-column:1/-1; text-align:center; padding:1.5rem 0;">'
            f'<button class="btn-outline" onclick="loadMoreGallery({next_page})" style="font-size:0.85rem;">'
            f"LOAD MORE &mdash; page {next_page} of {pages}"
            "</button>"
            "</div>"
        )

    html = "\n".join(html_parts)
    return HTMLResponse(
        content=html,
        headers={
            "X-Gallery-Total": str(total),
            "X-Gallery-Showing": str(showing),
        },
    )

# --- P4-SLOT-23: Conversation Browser API ---

@router.get("/jobs/{job_id}/conversations")
async def list_conversations(
    request: Request,
    job_id: int,
    search: str | None = Query(None),
    username: str = Depends(get_current_user),
) -> dict:
    """GET /api/jobs/{job_id}/conversations — Conversation list as JSON.

    Optional query param: ?search= filters by friend display name or message content.
    Returns {conversations: [{conversation_id, friend_username, display_name,
    message_count, first_date, last_date, has_media}]}.
    """
    import sqlite3 as _sqlite3
    from pathlib import Path as _Path

    config = request.app.state.config
    pool = request.app.state.db_pool
    loop = asyncio.get_running_loop()

    # Verify job ownership
    async with pool.acquire() as conn:
        job_row = await conn.fetchrow(
            """
            SELECT pj.id FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )
    if not job_row:
        raise HTTPException(404, "Job not found")

    db_path = _Path(str(config.server.data_dir)) / username / "proc.db"

    def _query():
        if not db_path.exists():
            return []
        conn_sq = _sqlite3.connect(str(db_path))
        conn_sq.row_factory = _sqlite3.Row
        try:
            if search:
                # Filter by friend display name OR message content keyword
                rows = conn_sq.execute(
                    """
                    SELECT
                        cm.conversation_id,
                        cm.conversation_title,
                        COUNT(cm.id) AS message_count,
                        MIN(cm.created_dt) AS first_date,
                        MAX(cm.created_dt) AS last_date,
                        MAX(CASE WHEN cm.media_ids IS NOT NULL AND cm.media_ids != ''
                                 THEN 1 ELSE 0 END) AS has_media,
                        f.display_name,
                        f.username AS friend_username
                    FROM chat_messages cm
                    LEFT JOIN friends f ON f.username = cm.conversation_id
                    WHERE
                        cm.conversation_id IN (
                            SELECT DISTINCT conversation_id FROM chat_messages
                            WHERE content LIKE ?
                        )
                        OR f.display_name LIKE ?
                        OR cm.conversation_id LIKE ?
                    GROUP BY cm.conversation_id
                    ORDER BY MAX(cm.created_dt) DESC
                    """,
                    (f"%{search}%", f"%{search}%", f"%{search}%"),
                ).fetchall()
            else:
                rows = conn_sq.execute(
                    """
                    SELECT
                        cm.conversation_id,
                        cm.conversation_title,
                        COUNT(cm.id) AS message_count,
                        MIN(cm.created_dt) AS first_date,
                        MAX(cm.created_dt) AS last_date,
                        MAX(CASE WHEN cm.media_ids IS NOT NULL AND cm.media_ids != ''
                                 THEN 1 ELSE 0 END) AS has_media,
                        f.display_name,
                        f.username AS friend_username
                    FROM chat_messages cm
                    LEFT JOIN friends f ON f.username = cm.conversation_id
                    GROUP BY cm.conversation_id
                    ORDER BY MAX(cm.created_dt) DESC
                    """
                ).fetchall()
        except Exception:
            rows = []
        conn_sq.close()
        return [dict(r) for r in rows]

    conversations = await loop.run_in_executor(None, _query)

    # Normalise display names
    for c in conversations:
        if not c.get("display_name"):
            c["display_name"] = c.get("conversation_title") or c.get("conversation_id") or ""

    return {"conversations": conversations}


@router.get("/jobs/{job_id}/conversations/html", response_class=HTMLResponse)
async def list_conversations_html(
    request: Request,
    job_id: int,
    search: str | None = Query(None),
    date_start: str | None = Query(None),
    date_end: str | None = Query(None),
    username: str = Depends(get_current_user),
) -> HTMLResponse:
    """GET /api/jobs/{job_id}/conversations/html — htmx fragment for the conversation sidebar list.

    Supports filtering by keyword (friend name or message content) and date range.
    Returns raw HTML sidebar entries, not a full page.
    """
    import sqlite3 as _sqlite3
    from pathlib import Path as _Path

    config = request.app.state.config
    pool = request.app.state.db_pool
    loop = asyncio.get_running_loop()

    # Verify job ownership
    async with pool.acquire() as conn:
        job_row = await conn.fetchrow(
            """
            SELECT pj.id FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )
    if not job_row:
        raise HTTPException(404, "Job not found")

    db_path = _Path(str(config.server.data_dir)) / username / "proc.db"

    def _query():
        if not db_path.exists():
            return []
        conn_sq = _sqlite3.connect(str(db_path))
        conn_sq.row_factory = _sqlite3.Row
        try:
            conditions = []
            params: list = []

            if search:
                conditions.append(
                    "(cm.conversation_id IN ("
                    "  SELECT DISTINCT conversation_id FROM chat_messages WHERE content LIKE ?"
                    ") OR f.display_name LIKE ? OR cm.conversation_id LIKE ?)"
                )
                params += [f"%{search}%", f"%{search}%", f"%{search}%"]

            if date_start:
                conditions.append("MAX(cm.created_dt) >= ?")
                params.append(date_start)

            if date_end:
                conditions.append("MIN(cm.created_dt) <= ?")
                params.append(date_end + "T23:59:59")

            having_clause = ("HAVING " + " AND ".join(conditions)) if conditions else ""

            rows = conn_sq.execute(
                f"""
                SELECT
                    cm.conversation_id,
                    cm.conversation_title,
                    COUNT(cm.id) AS message_count,
                    MIN(cm.created_dt) AS first_date,
                    MAX(cm.created_dt) AS last_date,
                    MAX(CASE WHEN cm.media_ids IS NOT NULL AND cm.media_ids != ''
                             THEN 1 ELSE 0 END) AS has_media,
                    f.display_name,
                    f.username AS friend_username
                FROM chat_messages cm
                LEFT JOIN friends f ON f.username = cm.conversation_id
                GROUP BY cm.conversation_id
                {having_clause}
                ORDER BY MAX(cm.created_dt) DESC
                """,
                params,
            ).fetchall()
        except Exception:
            rows = []
        conn_sq.close()
        return [dict(r) for r in rows]

    conversations = await loop.run_in_executor(None, _query)

    # Normalise display names
    for c in conversations:
        if not c.get("display_name"):
            c["display_name"] = c.get("conversation_title") or c.get("conversation_id") or ""

    if not conversations:
        return HTMLResponse(
            '<div class="empty-state" style="padding:2rem;text-align:center;">'
            '<p class="text-muted" style="font-size:0.85rem;">No conversations match your filters.</p>'
            '</div>'
        )

    # Build sidebar HTML
    lines = []
    for c in conversations:
        cid = c["conversation_id"] or ""
        display = c.get("display_name") or cid
        friend_un = c.get("friend_username") or ""
        msg_count = c.get("message_count", 0)
        first_date = (c.get("first_date") or "")[:10]
        last_date = (c.get("last_date") or "")[:10]
        has_media = bool(c.get("has_media"))

        date_str = ""
        if first_date and last_date and first_date != last_date:
            date_str = f"{first_date} &rarr; {last_date}"
        elif first_date:
            date_str = first_date

        sub_line = ""
        if friend_un and display != friend_un:
            sub_line = (
                f'<div class="mono text-muted" style="font-size:0.7rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'
                f'{friend_un}</div>'
            )

        media_icon = (
            '<span class="material-symbols-outlined" style="font-size:0.9rem;color:var(--text-muted);" title="Has media">photo_camera</span>'
            if has_media else ''
        )

        # Escape for HTML attribute (basic — conversation_id is internal data, not user HTML)
        import html as _html
        cid_attr = _html.escape(cid, quote=True)
        display_lower = _html.escape(display.lower(), quote=True)

        lines.append(
            f'<div class="convo-entry" '
            f'data-convo-id="{cid_attr}" '
            f'data-display-name="{display_lower}" '
            f'data-first-date="{first_date}" '
            f'data-last-date="{last_date}" '
            f'onclick="loadConversation(\'{cid_attr}\', {job_id}, this)" '
            f'style="padding:0.75rem 1rem;border-bottom:1px solid var(--border-dark);cursor:pointer;">'
            f'  <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:0.5rem;">'
            f'    <div style="flex:1;min-width:0;">'
            f'      <div style="font-weight:700;font-size:0.875rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--text-primary);">{_html.escape(display)}</div>'
            f'      {sub_line}'
            f'      <div class="text-muted" style="font-size:0.7rem;margin-top:0.2rem;">{date_str}</div>'
            f'    </div>'
            f'    <div style="flex-shrink:0;display:flex;flex-direction:column;align-items:flex-end;gap:0.2rem;">'
            f'      <span style="background:var(--snap-yellow);color:#000;font-family:\'JetBrains Mono\',monospace;font-size:0.65rem;font-weight:700;padding:0.15rem 0.4rem;min-width:1.4rem;text-align:center;">{msg_count}</span>'
            f'      {media_icon}'
            f'    </div>'
            f'  </div>'
            f'</div>'
        )

    return HTMLResponse("\n".join(lines))


@router.get("/jobs/{job_id}/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    request: Request,
    job_id: int,
    conversation_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    search: str | None = Query(None),
    username: str = Depends(get_current_user),
) -> dict:
    """GET /api/jobs/{job_id}/conversations/{conversation_id}/messages — Paginated messages as JSON.

    Returns {messages: [{id, from_user, content, created_dt, is_sender, media_type,
    media_ids, has_matched_media}], total, page, pages}.
    """
    import sqlite3 as _sqlite3
    from pathlib import Path as _Path

    config = request.app.state.config
    pool = request.app.state.db_pool
    loop = asyncio.get_running_loop()

    # Verify job ownership
    async with pool.acquire() as conn:
        job_row = await conn.fetchrow(
            """
            SELECT pj.id FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )
    if not job_row:
        raise HTTPException(404, "Job not found")

    db_path = _Path(str(config.server.data_dir)) / username / "proc.db"
    offset = (page - 1) * per_page

    def _query():
        if not db_path.exists():
            return [], 0

        conn_sq = _sqlite3.connect(str(db_path))
        conn_sq.row_factory = _sqlite3.Row
        try:
            base_where = "WHERE cm.conversation_id = ?"
            params: list = [conversation_id]

            if search:
                base_where += " AND cm.content LIKE ?"
                params.append(f"%{search}%")

            total_row = conn_sq.execute(
                f"SELECT COUNT(*) FROM chat_messages cm {base_where}", params
            ).fetchone()
            total = total_row[0] if total_row else 0

            rows = conn_sq.execute(
                f"""
                SELECT
                    cm.id,
                    cm.from_user,
                    cm.content,
                    cm.created_dt,
                    cm.is_sender,
                    cm.media_type,
                    cm.media_ids,
                    EXISTS (
                        SELECT 1 FROM chat_media_ids cmi
                        JOIN assets a ON a.file_id = cmi.media_id
                        WHERE cmi.chat_message_id = cm.id AND a.output_path IS NOT NULL
                    ) AS has_matched_media
                FROM chat_messages cm
                {base_where}
                ORDER BY cm.created_dt ASC, cm.id ASC
                LIMIT ? OFFSET ?
                """,
                params + [per_page, offset],
            ).fetchall()
        except Exception:
            rows = []
            total = 0

        conn_sq.close()
        result = []
        for r in rows:
            d = dict(r)
            # Parse media_ids CSV string into a list
            raw_media = d.get("media_ids") or ""
            d["media_ids"] = [m.strip() for m in raw_media.split(",") if m.strip()] if raw_media else []
            d["has_matched_media"] = bool(d.get("has_matched_media"))
            result.append(d)
        return result, total

    messages, total = await loop.run_in_executor(None, _query)
    import math
    pages = max(1, math.ceil(total / per_page)) if total > 0 else 1

    return {
        "messages": messages,
        "total": total,
        "page": page,
        "pages": pages,
    }


@router.get("/jobs/{job_id}/conversations/{conversation_id}/messages/html", response_class=HTMLResponse)
async def get_conversation_messages_html(
    request: Request,
    job_id: int,
    conversation_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    search: str | None = Query(None),
    username: str = Depends(get_current_user),
) -> HTMLResponse:
    """GET /api/jobs/{job_id}/conversations/{conversation_id}/messages/html — htmx chat bubble fragment.

    Returns HTML partial of chat bubbles for the given conversation page.
    Sent messages (is_sender=1) are right-aligned yellow; received are left dark.
    """
    import sqlite3 as _sqlite3
    from pathlib import Path as _Path
    import html as _html
    import math as _math

    config = request.app.state.config
    pool = request.app.state.db_pool
    loop = asyncio.get_running_loop()

    # Verify job ownership
    async with pool.acquire() as conn:
        job_row = await conn.fetchrow(
            """
            SELECT pj.id FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )
    if not job_row:
        raise HTTPException(404, "Job not found")

    db_path = _Path(str(config.server.data_dir)) / username / "proc.db"
    offset = (page - 1) * per_page

    def _query():
        if not db_path.exists():
            return [], 0
        conn_sq = _sqlite3.connect(str(db_path))
        conn_sq.row_factory = _sqlite3.Row
        try:
            base_where = "WHERE cm.conversation_id = ?"
            params: list = [conversation_id]
            if search:
                base_where += " AND cm.content LIKE ?"
                params.append(f"%{search}%")

            total_row = conn_sq.execute(
                f"SELECT COUNT(*) FROM chat_messages cm {base_where}", params
            ).fetchone()
            total = total_row[0] if total_row else 0

            rows = conn_sq.execute(
                f"""
                SELECT
                    cm.id,
                    cm.from_user,
                    cm.content,
                    cm.created_dt,
                    cm.is_sender,
                    cm.media_type,
                    cm.media_ids,
                    EXISTS (
                        SELECT 1 FROM chat_media_ids cmi
                        JOIN assets a ON a.file_id = cmi.media_id
                        WHERE cmi.chat_message_id = cm.id AND a.output_path IS NOT NULL
                    ) AS has_matched_media
                FROM chat_messages cm
                {base_where}
                ORDER BY cm.created_dt ASC, cm.id ASC
                LIMIT ? OFFSET ?
                """,
                params + [per_page, offset],
            ).fetchall()
        except Exception:
            rows = []
            total = 0
        conn_sq.close()
        return [dict(r) for r in rows], total

    messages, total = await loop.run_in_executor(None, _query)
    pages = max(1, _math.ceil(total / per_page)) if total > 0 else 1

    if not messages:
        return HTMLResponse(
            '<div class="empty-state" style="padding:3rem;text-align:center;">'
            '<p class="text-muted">No messages found.</p>'
            '</div>'
        )

    lines = []
    for m in messages:
        is_sender = bool(m.get("is_sender"))
        align = "flex-end" if is_sender else "flex-start"
        bubble_bg = "rgba(255,252,0,0.08)" if is_sender else "var(--charcoal)"
        bubble_border = "rgba(255,252,0,0.4)" if is_sender else "var(--border-dark)"
        text_color = "var(--snap-yellow)" if is_sender else "var(--text-primary)"

        content = m.get("content") or ""
        media_type = m.get("media_type") or ""
        raw_media_ids = m.get("media_ids") or ""
        media_ids = [x.strip() for x in raw_media_ids.split(",") if x.strip()] if raw_media_ids else []
        has_matched = bool(m.get("has_matched_media"))
        from_user = m.get("from_user") or ""
        created_dt = (m.get("created_dt") or "").replace("T", " ")[:16]

        # Content HTML
        if content:
            content_html = f'<div style="font-size:0.875rem;color:{text_color};word-break:break-word;white-space:pre-wrap;">{_html.escape(content)}</div>'
        elif media_type:
            content_html = (
                f'<div style="font-size:0.875rem;color:var(--text-muted);font-style:italic;">'
                f'[{_html.escape(media_type)}]</div>'
            )
        else:
            content_html = '<div style="font-size:0.875rem;color:var(--text-muted);font-style:italic;">[no content]</div>'

        # Media indicator
        media_html = ""
        if has_matched:
            media_html = '<div style="margin-top:0.35rem;font-size:0.72rem;color:var(--success);"><span class="material-symbols-outlined" style="font-size:0.85rem;vertical-align:middle;">check_circle</span> media matched</div>'
        elif media_ids:
            n = len(media_ids)
            media_html = (
                f'<div style="margin-top:0.35rem;font-size:0.72rem;color:var(--text-muted);">'
                f'<span class="material-symbols-outlined" style="font-size:0.85rem;vertical-align:middle;">attach_file</span> '
                f'{n} media file{"s" if n != 1 else ""}</div>'
            )

        # Timestamp
        sender_label = "you" if is_sender else _html.escape(from_user)
        meta_html = (
            f'<div style="margin-top:0.3rem;font-family:\'JetBrains Mono\',monospace;font-size:0.65rem;'
            f'color:var(--text-dim);display:flex;gap:0.5rem;justify-content:{align};">'
            f'{sender_label + " &middot; " if sender_label else ""}{_html.escape(created_dt)}</div>'
        )

        lines.append(
            f'<div style="display:flex;justify-content:{align};margin-bottom:0.6rem;">'
            f'  <div style="max-width:72%;padding:0.5rem 0.75rem;border:1px solid {bubble_border};background:{bubble_bg};">'
            f'    {content_html}'
            f'    {media_html}'
            f'    {meta_html}'
            f'  </div>'
            f'</div>'
        )

    # Pagination footer
    if page < pages:
        showing = page * per_page
        lines.append(
            f'<div style="text-align:center;padding:1rem;">'
            f'  <button type="button" class="btn-outline" style="font-size:0.8rem;" onclick="loadMoreMessages()">LOAD MORE</button>'
            f'  <p class="mono text-muted" style="font-size:0.72rem;margin-top:0.5rem;">Showing {showing} of {total} messages</p>'
            f'</div>'
        )

    return HTMLResponse("\n".join(lines))

# --- P4-SLOT-24: Timeline API ---

@router.get("/jobs/{job_id}/timeline-data")
async def timeline_data(
    request: Request,
    job_id: int,
    granularity: str = Query("year", regex="^(year|month|day)$"),
    year: str | None = Query(None),
    month: str | None = Query(None),
    lane: list[str] | None = Query(None),
    confidence_min: float | None = Query(None, ge=0.0, le=1.0),
    username: str = Depends(get_current_user),
) -> dict:
    """GET /api/jobs/{job_id}/timeline-data — Aggregated timeline data.

    Returns item counts grouped by period (year / month / day) with
    per-lane breakdowns.  For day granularity returns individual item
    records instead of aggregates.

    Query params:
      granularity: year | month | day  (default: year)
      year:        filter to a specific year  (required for month/day)
      month:       filter to a specific month as MM  (required for day)
      lane:        one or more of memories | chats | stories (repeatable)
      confidence_min: 0.0-1.0 minimum match confidence
    """
    config = request.app.state.config
    pool = request.app.state.db_pool

    # Verify job ownership
    async with pool.acquire() as conn:
        owner = await conn.fetchval(
            """
            SELECT u.username FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1
            """,
            job_id,
        )

    if owner != username:
        raise HTTPException(403, "Access denied")

    import sqlite3 as _sq3
    from collections import OrderedDict as _OD

    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    if not db_path.exists():
        return {"granularity": granularity, "items": [], "total": 0}

    loop = asyncio.get_running_loop()
    _lane = lane
    _year = year
    _month = month
    _conf_min = confidence_min
    _granularity = granularity

    def _query_timeline():
        conn_sq = _sq3.connect(str(db_path))
        conn_sq.row_factory = _sq3.Row

        # Build WHERE clauses
        where_parts = ["m.is_best = 1", "m.matched_date IS NOT NULL"]
        params = []

        if _lane:
            placeholders = ",".join("?" for _ in _lane)
            where_parts.append(f"m.lane IN ({placeholders})")
            params.extend(_lane)

        if _conf_min is not None:
            where_parts.append("m.confidence >= ?")
            params.append(_conf_min)

        if _granularity in ("month", "day") and _year:
            where_parts.append("substr(m.matched_date, 1, 4) = ?")
            params.append(str(_year))

        if _granularity == "day" and _month:
            where_parts.append("substr(m.matched_date, 6, 2) = ?")
            params.append(str(_month).zfill(2))

        where_sql = " AND ".join(where_parts)

        try:
            if _granularity == "day":
                rows = conn_sq.execute(
                    f"""
                    SELECT
                        m.asset_id,
                        a.filename,
                        a.asset_type,
                        m.matched_date,
                        m.confidence,
                        m.lane,
                        CASE WHEN m.matched_lat IS NOT NULL AND m.matched_lon IS NOT NULL THEN 1 ELSE 0 END AS has_gps
                    FROM matches m
                    LEFT JOIN assets a ON a.id = m.asset_id
                    WHERE {where_sql}
                    ORDER BY m.matched_date ASC, m.confidence DESC
                    LIMIT 2000
                    """,
                    params,
                ).fetchall()
                items = [dict(r) for r in rows]
                return {"granularity": "day", "items": items, "total": len(items)}
            else:
                if _granularity == "year":
                    period_expr = "substr(m.matched_date, 1, 4)"
                else:
                    period_expr = "substr(m.matched_date, 1, 7)"

                rows = conn_sq.execute(
                    f"""
                    SELECT
                        {period_expr} AS period,
                        m.lane,
                        COUNT(*) AS cnt
                    FROM matches m
                    WHERE {where_sql}
                    GROUP BY {period_expr}, m.lane
                    ORDER BY {period_expr} ASC
                    """,
                    params,
                ).fetchall()

                period_map = _OD()
                for r in rows:
                    p = r["period"] or "Unknown"
                    if p not in period_map:
                        period_map[p] = {"period": p, "count": 0, "lane_counts": {"memories": 0, "chats": 0, "stories": 0}}
                    cnt = r["cnt"] or 0
                    period_map[p]["count"] += cnt
                    lane_key = r["lane"] or "unknown"
                    if lane_key in period_map[p]["lane_counts"]:
                        period_map[p]["lane_counts"][lane_key] += cnt

                items = list(period_map.values())
                total = sum(item["count"] for item in items)
                return {"granularity": _granularity, "items": items, "total": total}
        except Exception as exc:
            logger.warning(f"timeline_data SQLite error: {exc}")
            return {"granularity": _granularity, "items": [], "total": 0}
        finally:
            conn_sq.close()

    return await loop.run_in_executor(None, _query_timeline)


# --- P4-SLOT-25: Map API ---

@router.get("/jobs/{job_id}/map-data")
async def map_data(
    request: Request,
    job_id: int,
    date_start: str | None = Query(None),
    date_end: str | None = Query(None),
    lane: list[str] | None = Query(None),
    friend: str | None = Query(None),
    confidence_min: float | None = Query(None, ge=0.0, le=1.0),
    username: str = Depends(get_current_user),
) -> dict:
    """GET /api/jobs/{job_id}/map-data — GPS marker data for map view.

    Returns up to 5000 GPS-enriched match records with lat/lon and metadata
    for Leaflet marker rendering.  Also returns bounding box for auto-fit.

    Query params:
      date_start:     ISO date YYYY-MM-DD lower bound (inclusive)
      date_end:       ISO date YYYY-MM-DD upper bound (inclusive)
      lane:           one or more of memories | chats | stories (repeatable)
      friend:         partial display_name match (case-insensitive)
      confidence_min: 0.0-1.0 minimum match confidence
    """
    config = request.app.state.config
    pool = request.app.state.db_pool

    # Verify job ownership
    async with pool.acquire() as conn:
        owner = await conn.fetchval(
            """
            SELECT u.username FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1
            """,
            job_id,
        )

    if owner != username:
        raise HTTPException(403, "Access denied")

    import sqlite3 as _sq3

    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    if not db_path.exists():
        return {"markers": [], "total": 0, "bounds": None}

    loop = asyncio.get_running_loop()
    _lane = lane
    _date_start = date_start
    _date_end = date_end
    _friend = friend
    _conf_min = confidence_min

    def _query_map():
        conn_sq = _sq3.connect(str(db_path))
        conn_sq.row_factory = _sq3.Row

        where_parts = [
            "m.is_best = 1",
            "m.matched_lat IS NOT NULL",
            "m.matched_lon IS NOT NULL",
        ]
        params = []

        if _lane:
            placeholders = ",".join("?" for _ in _lane)
            where_parts.append(f"m.lane IN ({placeholders})")
            params.extend(_lane)

        if _date_start:
            where_parts.append("m.matched_date >= ?")
            params.append(_date_start)

        if _date_end:
            end_val = (_date_end + "T23:59:59") if "T" not in _date_end else _date_end
            where_parts.append("m.matched_date <= ?")
            params.append(end_val)

        if _conf_min is not None:
            where_parts.append("m.confidence >= ?")
            params.append(_conf_min)

        if _friend:
            where_parts.append("LOWER(COALESCE(m.display_name, '')) LIKE ?")
            params.append("%" + _friend.lower() + "%")

        where_sql = " AND ".join(where_parts)

        try:
            rows = conn_sq.execute(
                f"""
                SELECT
                    m.asset_id,
                    m.matched_lat  AS lat,
                    m.matched_lon  AS lon,
                    a.filename,
                    m.matched_date,
                    m.confidence,
                    m.lane,
                    m.display_name,
                    a.asset_type
                FROM matches m
                LEFT JOIN assets a ON a.id = m.asset_id
                WHERE {where_sql}
                ORDER BY m.matched_date ASC
                LIMIT 5000
                """,
                params,
            ).fetchall()

            markers = [dict(r) for r in rows]

            bounds = None
            if markers:
                lats = [r["lat"] for r in markers if r["lat"] is not None]
                lons = [r["lon"] for r in markers if r["lon"] is not None]
                if lats and lons:
                    bounds = {
                        "min_lat": min(lats),
                        "max_lat": max(lats),
                        "min_lon": min(lons),
                        "max_lon": max(lons),
                    }

            return {"markers": markers, "total": len(markers), "bounds": bounds}
        except Exception as exc:
            logger.warning(f"map_data SQLite error: {exc}")
            return {"markers": [], "total": 0, "bounds": None}
        finally:
            conn_sq.close()

    return await loop.run_in_executor(None, _query_map)

# --- P4-SLOT-26: Duplicate Detection API ---

@router.get("/jobs/{job_id}/duplicates")
async def get_duplicates(
    request: Request,
    job_id: int,
    username: str = Depends(get_current_user),
) -> dict:
    """GET /api/jobs/{job_id}/duplicates — Find all duplicate asset groups.

    Queries the per-user SQLite for sha256 hashes that appear more than once.
    For each group returns the list of assets with match data.
    Returns: { groups, summary }
    """
    config = request.app.state.config
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        job_row = await conn.fetchrow(
            """
            SELECT pj.id FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )
    if not job_row:
        raise HTTPException(404, "Job not found")

    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    loop = asyncio.get_running_loop()

    def _find_duplicates():
        if not db_path.exists():
            return {
                "groups": [],
                "summary": {
                    "total_assets": 0,
                    "unique_hashes": 0,
                    "duplicate_groups": 0,
                    "duplicate_files": 0,
                },
            }
        conn_sq = sqlite3.connect(str(db_path))
        conn_sq.row_factory = sqlite3.Row
        try:
            total_assets = conn_sq.execute(
                "SELECT COUNT(*) FROM assets"
            ).fetchone()[0]

            unique_hashes = conn_sq.execute(
                "SELECT COUNT(DISTINCT sha256) FROM assets WHERE sha256 IS NOT NULL"
            ).fetchone()[0]

            dup_hashes = conn_sq.execute(
                """
                SELECT sha256, COUNT(*) as cnt
                FROM assets
                WHERE sha256 IS NOT NULL
                GROUP BY sha256
                HAVING COUNT(*) > 1
                ORDER BY cnt DESC, sha256
                """
            ).fetchall()

            groups = []
            total_dup_files = 0
            for hash_row in dup_hashes:
                h = hash_row["sha256"]
                count = hash_row["cnt"]
                total_dup_files += count

                asset_rows = conn_sq.execute(
                    """
                    SELECT
                        a.id         AS asset_id,
                        a.filename,
                        a.asset_type,
                        a.file_size,
                        m.confidence,
                        m.strategy,
                        m.matched_date,
                        m.is_best    AS is_best_match
                    FROM assets a
                    LEFT JOIN matches m ON m.asset_id = a.id AND m.is_best = 1
                    WHERE a.sha256 = ?
                    ORDER BY COALESCE(m.confidence, 0) DESC, a.id ASC
                    """,
                    (h,),
                ).fetchall()

                files = [
                    {
                        "asset_id": r["asset_id"],
                        "filename": r["filename"],
                        "asset_type": r["asset_type"],
                        "file_size": r["file_size"],
                        "confidence": r["confidence"],
                        "strategy": r["strategy"],
                        "matched_date": r["matched_date"],
                        "is_best_match": bool(r["is_best_match"]) if r["is_best_match"] is not None else False,
                    }
                    for r in asset_rows
                ]

                groups.append({"hash": h, "count": count, "files": files})

            return {
                "groups": groups,
                "summary": {
                    "total_assets": total_assets,
                    "unique_hashes": unique_hashes,
                    "duplicate_groups": len(groups),
                    "duplicate_files": total_dup_files,
                },
            }
        except Exception as exc:
            logger.exception("Error scanning duplicates for job %s: %s", job_id, exc)
            return {
                "groups": [],
                "summary": {
                    "total_assets": 0,
                    "unique_hashes": 0,
                    "duplicate_groups": 0,
                    "duplicate_files": 0,
                },
            }
        finally:
            conn_sq.close()

    return await loop.run_in_executor(None, _find_duplicates)


class DuplicateResolveBody(BaseModel):
    hash: str
    keep_asset_id: int
    action: str = "keep_best"


@router.post("/jobs/{job_id}/duplicates/resolve")
async def resolve_duplicate(
    request: Request,
    job_id: int,
    body: DuplicateResolveBody,
    username: str = Depends(get_current_user),
) -> dict:
    """POST /api/jobs/{job_id}/duplicates/resolve — Mark a duplicate group resolved.

    Body: { hash, keep_asset_id, action }
    Actual file deletion is a future feature; records intent and returns success.
    Returns: { resolved, kept, dismissed }
    """
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        job_row = await conn.fetchrow(
            """
            SELECT pj.id FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )
    if not job_row:
        raise HTTPException(404, "Job not found")

    config = request.app.state.config
    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    loop = asyncio.get_running_loop()

    keep_id = body.keep_asset_id

    def _get_dismissed():
        if not db_path.exists():
            return []
        conn_sq = sqlite3.connect(str(db_path))
        conn_sq.row_factory = sqlite3.Row
        try:
            rows = conn_sq.execute(
                """
                SELECT id FROM assets
                WHERE sha256 = (SELECT sha256 FROM assets WHERE id = ?)
                  AND id != ?
                """,
                (keep_id, keep_id),
            ).fetchall()
            return [r["id"] for r in rows]
        except Exception:
            return []
        finally:
            conn_sq.close()

    dismissed = await loop.run_in_executor(None, _get_dismissed)
    logger.info(
        "Duplicate resolve: job=%s hash=%s keep=%s dismissed=%s action=%s",
        job_id, body.hash[:16], keep_id, dismissed, body.action,
    )
    return {"resolved": True, "kept": keep_id, "dismissed": dismissed}


@router.get("/jobs/{job_id}/duplicates/html", response_class=HTMLResponse)
async def get_duplicates_html(
    request: Request,
    job_id: int,
    username: str = Depends(get_current_user),
) -> HTMLResponse:
    """GET /api/jobs/{job_id}/duplicates/html — htmx fragment for duplicate groups.

    Same logic as get_duplicates() but returns an HTML fragment ready to be
    swapped into #dup-results on duplicates.html.
    """
    config = request.app.state.config
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        job_row = await conn.fetchrow(
            """
            SELECT pj.id FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )
    if not job_row:
        raise HTTPException(404, "Job not found")

    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    loop = asyncio.get_running_loop()

    def _find_dup_groups():
        if not db_path.exists():
            return []
        conn_sq = sqlite3.connect(str(db_path))
        conn_sq.row_factory = sqlite3.Row
        try:
            dup_hashes = conn_sq.execute(
                """
                SELECT sha256, COUNT(*) as cnt
                FROM assets
                WHERE sha256 IS NOT NULL
                GROUP BY sha256
                HAVING COUNT(*) > 1
                ORDER BY cnt DESC, sha256
                """
            ).fetchall()
            groups = []
            for hash_row in dup_hashes:
                h = hash_row["sha256"]
                count = hash_row["cnt"]
                asset_rows = conn_sq.execute(
                    """
                    SELECT
                        a.id         AS asset_id,
                        a.filename,
                        a.asset_type,
                        a.file_size,
                        m.confidence,
                        m.matched_date,
                        m.is_best    AS is_best_match
                    FROM assets a
                    LEFT JOIN matches m ON m.asset_id = a.id AND m.is_best = 1
                    WHERE a.sha256 = ?
                    ORDER BY COALESCE(m.confidence, 0) DESC, a.id ASC
                    """,
                    (h,),
                ).fetchall()
                groups.append({"hash": h, "count": count, "files": [dict(r) for r in asset_rows]})
            return groups
        except Exception:
            return []
        finally:
            conn_sq.close()

    groups = await loop.run_in_executor(None, _find_dup_groups)

    if not groups:
        html = (
            '<div class="empty-state">'
            '<span class="material-symbols-outlined" '
            '  style="font-size:2.5rem;color:var(--success);display:block;margin-bottom:1rem;">check_circle</span>'
            '<p style="color:var(--success);font-family:\'JetBrains Mono\',monospace;">'
            'No duplicates found &mdash; all files are unique</p>'
            '</div>'
        )
        return HTMLResponse(content=html)

    parts: list[str] = [
        f'<p class="mono text-muted" style="font-size:0.8rem;margin-bottom:1.25rem;">'
        f'Found <strong style="color:var(--snap-yellow);">{len(groups)}</strong> duplicate group(s).</p>'
    ]

    for idx, group in enumerate(groups):
        h = group["hash"]
        h_short = h[:16] + "..."
        count = group["count"]
        files = group["files"]
        best_id = files[0]["asset_id"] if files else 0

        rows_html = ""
        for f in files:
            is_best = bool(f.get("is_best_match"))
            row_class = "dup-row-best" if is_best else ""
            conf_str = f"{f['confidence'] * 100:.0f}%" if f.get("confidence") is not None else "—"
            date_str = (f.get("matched_date") or "")[:10] or "—"
            size_str = f"{f['file_size']:,}" if f.get("file_size") else "—"
            rows_html += (
                f'<tr class="{row_class}">'
                f"<td>{f.get('filename', '—')}</td>"
                f"<td>{f.get('asset_type', '—')}</td>"
                f"<td>{size_str}</td>"
                f"<td>{date_str}</td>"
                f"<td>{conf_str}</td>"
                f"</tr>"
            )

        h_esc = h.replace('"', "&quot;").replace("'", "\\'")
        parts.append(
            f'<div class="dup-group" id="dup-group-{idx}">'
            f'  <div class="dup-group-header" onclick="toggleDupGroup({idx})">'
            f'    <span class="dup-hash">{h_short}</span>'
            f'    <div style="display:flex;align-items:center;gap:0.5rem;">'
            f'      <span class="dup-count-badge">{count} files</span>'
            f'      <span class="material-symbols-outlined" id="dup-icon-{idx}" '
            f'            style="font-size:1.1rem;color:var(--text-muted);">expand_more</span>'
            f'    </div>'
            f'  </div>'
            f'  <div class="dup-group-body" id="dup-body-{idx}" style="display:none;">'
            f'    <table>'
            f'      <thead><tr><th>Filename</th><th>Type</th><th>Size</th><th>Date</th><th>Conf</th></tr></thead>'
            f'      <tbody>{rows_html}</tbody>'
            f'    </table>'
            f'    <div class="dup-actions">'
            f'      <button class="btn-primary" style="font-size:0.78rem;" '
            f"        onclick=\"resolveDuplicate('{h_esc}', {best_id}, 'keep_best', this)\">KEEP BEST</button>"
            f'      <button class="btn-outline" style="font-size:0.78rem;" '
            f"        onclick=\"dismissGroup('{h_esc}', this)\">KEEP ALL</button>"
            f'    </div>'
            f'    <p class="dup-status"></p>'
            f'  </div>'
            f'</div>'
        )

    return HTMLResponse(content="\n".join(parts))


# --- P4-SLOT-27: Album Auto-Creation API ---

import math as _math


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in kilometres between two GPS points."""
    R = 6371.0
    dlat = _math.radians(lat2 - lat1)
    dlon = _math.radians(lon2 - lon1)
    a = (
        _math.sin(dlat / 2) ** 2
        + _math.cos(_math.radians(lat1))
        * _math.cos(_math.radians(lat2))
        * _math.sin(dlon / 2) ** 2
    )
    return R * 2 * _math.asin(_math.sqrt(a))


@router.post("/jobs/{job_id}/albums/generate")
async def generate_albums(
    request: Request,
    job_id: int,
    username: str = Depends(get_current_user),
) -> dict:
    """POST /api/jobs/{job_id}/albums/generate — GPS+time cluster into trip albums.

    Algorithm:
    1. Load all GPS-enriched best matches (lat, lon, date NOT NULL) from SQLite
    2. Sort by matched_date
    3. Iterate: start new cluster when dist > 50km OR gap > 3 days
    4. For each cluster with >= 3 items: save album + items to PostgreSQL
    Returns: { albums_created, albums }
    """
    config = request.app.state.config
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        job_row = await conn.fetchrow(
            """
            SELECT pj.id, u.id as user_id FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )
    if not job_row:
        raise HTTPException(404, "Job not found")

    user_id = job_row["user_id"]
    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    loop = asyncio.get_running_loop()

    def _load_gps_points():
        if not db_path.exists():
            return []
        conn_sq = sqlite3.connect(str(db_path))
        conn_sq.row_factory = sqlite3.Row
        try:
            rows = conn_sq.execute(
                """
                SELECT
                    a.id           AS asset_id,
                    m.matched_lat  AS lat,
                    m.matched_lon  AS lon,
                    m.matched_date AS date
                FROM assets a
                JOIN matches m ON m.asset_id = a.id AND m.is_best = 1
                WHERE m.matched_lat  IS NOT NULL
                  AND m.matched_lon  IS NOT NULL
                  AND m.matched_date IS NOT NULL
                ORDER BY m.matched_date ASC
                """
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
        finally:
            conn_sq.close()

    points = await loop.run_in_executor(None, _load_gps_points)

    if not points:
        return {"albums_created": 0, "albums": []}

    # --- Clustering ---
    MAX_DIST_KM = 50.0
    MAX_GAP_DAYS = 3

    from datetime import datetime as _dt

    clusters: list[list[dict]] = []
    current: list[dict] = [points[0]]

    for pt in points[1:]:
        prev = current[-1]

        try:
            d1 = _dt.fromisoformat(prev["date"][:10])
            d2 = _dt.fromisoformat(pt["date"][:10])
            gap_days = abs((d2 - d1).days)
        except (ValueError, TypeError):
            gap_days = 0

        c_lat = sum(p["lat"] for p in current) / len(current)
        c_lon = sum(p["lon"] for p in current) / len(current)
        dist_km = _haversine_km(c_lat, c_lon, pt["lat"], pt["lon"])

        if dist_km > MAX_DIST_KM or gap_days > MAX_GAP_DAYS:
            clusters.append(current)
            current = [pt]
        else:
            current.append(pt)

    clusters.append(current)

    # --- Persist qualifying clusters ---
    created_albums: list[dict] = []
    async with pool.acquire() as conn:
        for cluster in clusters:
            if len(cluster) < 3:
                continue

            dates = sorted(p["date"][:10] for p in cluster)
            start_date = dates[0]
            end_date = dates[-1]
            center_lat = sum(p["lat"] for p in cluster) / len(cluster)
            center_lon = sum(p["lon"] for p in cluster) / len(cluster)

            try:
                d_s = _dt.fromisoformat(start_date)
                d_e = _dt.fromisoformat(end_date)
                if d_s.year == d_e.year and d_s.month == d_e.month:
                    name = f"{d_s.strftime('%b')} {d_s.day}\u2013{d_e.day}, {d_s.year}"
                elif d_s.year == d_e.year:
                    name = f"{d_s.strftime('%b %-d')} \u2013 {d_e.strftime('%b %-d')}, {d_s.year}"
                else:
                    name = f"{d_s.strftime('%b %-d, %Y')} \u2013 {d_e.strftime('%b %-d, %Y')}"
            except (ValueError, TypeError):
                name = f"{start_date} \u2013 {end_date}"

            album_id = await conn.fetchval(
                """
                INSERT INTO albums
                    (user_id, job_id, name, auto_generated,
                     center_lat, center_lon, start_date, end_date, item_count)
                VALUES ($1, $2, $3, true, $4, $5, $6, $7, $8)
                RETURNING id
                """,
                user_id, job_id, name,
                center_lat, center_lon,
                start_date, end_date,
                len(cluster),
            )

            for sort_order, pt in enumerate(cluster):
                await conn.execute(
                    """
                    INSERT INTO album_items (album_id, asset_id, job_id, sort_order)
                    VALUES ($1, $2, $3, $4)
                    """,
                    album_id, pt["asset_id"], job_id, sort_order,
                )

            created_albums.append({
                "id": album_id,
                "name": name,
                "item_count": len(cluster),
                "start_date": start_date,
                "end_date": end_date,
            })

    logger.info(
        "Generated %d albums for job %s user '%s'",
        len(created_albums), job_id, username,
    )
    return {"albums_created": len(created_albums), "albums": created_albums}


@router.get("/jobs/{job_id}/albums")
async def list_job_albums(
    request: Request,
    job_id: int,
    username: str = Depends(get_current_user),
) -> dict:
    """GET /api/jobs/{job_id}/albums — List albums for a job.

    Returns: { albums: [{id, name, description, auto_generated, location_name,
                          start_date, end_date, item_count, center_lat, center_lon,
                          created_at}] }
    """
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        job_row = await conn.fetchrow(
            """
            SELECT pj.id, u.id as user_id FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )
    if not job_row:
        raise HTTPException(404, "Job not found")

    user_id = job_row["user_id"]

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, name, description, auto_generated,
                   location_name, start_date, end_date, item_count,
                   center_lat, center_lon, created_at
            FROM albums
            WHERE user_id = $1 AND job_id = $2
            ORDER BY start_date ASC NULLS LAST, created_at ASC
            """,
            user_id, job_id,
        )

    albums = []
    for row in rows:
        d = dict(row)
        for k, v in d.items():
            if hasattr(v, "isoformat"):
                d[k] = v.isoformat()
        albums.append(d)

    return {"albums": albums}


class AlbumUpdateBody(BaseModel):
    name: str | None = None
    description: str | None = None


@router.put("/albums/{album_id}")
async def update_album(
    request: Request,
    album_id: int,
    body: AlbumUpdateBody,
    username: str = Depends(get_current_user),
) -> dict:
    """PUT /api/albums/{album_id} — Rename or update an album.

    Verifies user ownership via albums.user_id JOIN users.
    Body: { name?, description? }
    Returns: { updated: true }
    """
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        album_row = await conn.fetchrow(
            """
            SELECT al.id FROM albums al
            JOIN users u ON al.user_id = u.id
            WHERE al.id = $1 AND u.username = $2
            """,
            album_id, username,
        )
        if not album_row:
            raise HTTPException(404, "Album not found")

        updates: dict = {}
        if body.name is not None:
            updates["name"] = body.name
        if body.description is not None:
            updates["description"] = body.description

        if not updates:
            return {"updated": True}

        set_clauses = ", ".join(
            f"{col} = ${i + 2}" for i, col in enumerate(updates)
        )
        values = list(updates.values())
        await conn.execute(
            f"UPDATE albums SET {set_clauses}, updated_at = NOW() WHERE id = $1",
            album_id, *values,
        )

    logger.info("Album %s updated by '%s': %s", album_id, username, list(updates.keys()))
    return {"updated": True}


@router.delete("/albums/{album_id}")
async def delete_album(
    request: Request,
    album_id: int,
    username: str = Depends(get_current_user),
) -> dict:
    """DELETE /api/albums/{album_id} — Delete an album and all its items.

    Verifies user ownership, then deletes the album row (ON DELETE CASCADE
    removes album_items automatically).
    Returns: { deleted: true }
    """
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        album_row = await conn.fetchrow(
            """
            SELECT al.id FROM albums al
            JOIN users u ON al.user_id = u.id
            WHERE al.id = $1 AND u.username = $2
            """,
            album_id, username,
        )
        if not album_row:
            raise HTTPException(404, "Album not found")

        await conn.execute("DELETE FROM albums WHERE id = $1", album_id)

    logger.info("Album %s deleted by '%s'", album_id, username)
    return {"deleted": True}


@router.get("/albums/{album_id}/items")
async def get_album_items(
    request: Request,
    album_id: int,
    username: str = Depends(get_current_user),
) -> dict:
    """GET /api/albums/{album_id}/items — List items in an album.

    Cross-references PostgreSQL album_items with per-user SQLite asset details.
    Returns: { items: [{asset_id, filename, asset_type, matched_date, confidence, lat, lon}] }
    """
    config = request.app.state.config
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        album_row = await conn.fetchrow(
            """
            SELECT al.id, al.job_id FROM albums al
            JOIN users u ON al.user_id = u.id
            WHERE al.id = $1 AND u.username = $2
            """,
            album_id, username,
        )
        if not album_row:
            raise HTTPException(404, "Album not found")

        item_rows = await conn.fetch(
            """
            SELECT asset_id, sort_order
            FROM album_items
            WHERE album_id = $1
            ORDER BY sort_order ASC
            """,
            album_id,
        )

    asset_ids = [r["asset_id"] for r in item_rows]
    if not asset_ids:
        return {"items": []}

    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    loop = asyncio.get_running_loop()

    def _load_asset_details():
        if not db_path.exists():
            return {}
        conn_sq = sqlite3.connect(str(db_path))
        conn_sq.row_factory = sqlite3.Row
        try:
            placeholders = ",".join("?" * len(asset_ids))
            rows = conn_sq.execute(
                f"""
                SELECT
                    a.id        AS asset_id,
                    a.filename,
                    a.asset_type,
                    a.is_video,
                    m.matched_date,
                    m.confidence,
                    m.matched_lat  AS lat,
                    m.matched_lon  AS lon
                FROM assets a
                LEFT JOIN matches m ON m.asset_id = a.id AND m.is_best = 1
                WHERE a.id IN ({placeholders})
                """,
                asset_ids,
            ).fetchall()
            return {r["asset_id"]: dict(r) for r in rows}
        except Exception:
            return {}
        finally:
            conn_sq.close()

    asset_map = await loop.run_in_executor(None, _load_asset_details)

    items = []
    for item_row in item_rows:
        aid = item_row["asset_id"]
        detail = asset_map.get(aid, {})
        items.append({
            "asset_id": aid,
            "filename": detail.get("filename"),
            "asset_type": detail.get("asset_type"),
            "is_video": bool(detail.get("is_video")),
            "matched_date": detail.get("matched_date"),
            "confidence": detail.get("confidence"),
            "lat": detail.get("lat"),
            "lon": detail.get("lon"),
        })

    return {"items": items}


@router.get("/tier")
async def get_tier(request: Request, username: str = Depends(get_current_user)) -> dict:
    """GET /api/tier — Return the current user's tier and all tier limits.

    Returns:
        tier: tier key (free/pro)
        tier_label: human-readable label
        color: CSS color string for UI theming
        limits: full limits dict for the user's tier
        all_tiers: list of all tier dicts with keys tier, label, color, storage_gb,
                   max_upload_bytes, max_upload_label, retention_days,
                   concurrent_jobs, bulk_upload
    """
    from snatched.tiers import get_tier_limits, TIER_LIMITS, TIER_ORDER

    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        tier = await conn.fetchval(
            "SELECT tier FROM users WHERE username = $1", username
        )
    if not tier:
        tier = "free"

    limits = get_tier_limits(tier)
    all_tiers = [
        {"tier": t, **TIER_LIMITS[t]}
        for t in TIER_ORDER
    ]

    return {
        "tier": tier,
        "tier_label": limits["label"],
        "color": limits["color"],
        "limits": {
            "storage_gb": limits["storage_gb"],
            "max_upload_bytes": limits["max_upload_bytes"],
            "max_upload_label": limits["max_upload_label"],
            "retention_days": limits["retention_days"],
            "concurrent_jobs": limits["concurrent_jobs"],
            "bulk_upload": limits["bulk_upload"],
        },
        "all_tiers": all_tiers,
    }


# ============================================================
# P5 ACCOUNT & QUOTA MANAGEMENT — Insertion slots
# ============================================================

# --- P5-SLOT-28: Storage Quota Dashboard API ---

@router.get("/quota")
async def quota_api(
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """GET /api/quota — Storage and quota info as JSON.

    Returns tier, limits, disk usage breakdown by lane, usage_pct, and
    per-job retention data.  All blocking I/O is offloaded via run_in_executor.

    Response shape:
        {
            tier, tier_label,
            limits: {storage_gb, retention_days, concurrent_jobs, ...},
            usage: {
                total_bytes, total_gb,
                breakdown: [{lane, file_count, size_bytes}]
            },
            usage_pct,
            jobs: [{id, filename, created_at, retention_expires_at,
                    days_remaining, status}]
        }
    """
    from snatched.tiers import get_tier_limits

    import asyncio as _asyncio
    import datetime as _dt

    config = request.app.state.config
    pool = request.app.state.db_pool
    loop = _asyncio.get_running_loop()

    # ── 1. Load user tier ───────────────────────────────────────────────────
    async with pool.acquire() as conn:
        user_row = await conn.fetchrow(
            "SELECT id, tier FROM users WHERE username = $1",
            username,
        )
    if not user_row:
        raise HTTPException(404, "User not found")

    user_id = user_row["id"]
    tier = user_row["tier"] or "free"
    limits = get_tier_limits(tier)

    # ── 2. Load jobs (retention) ─────────────────────────────────────────────
    async with pool.acquire() as conn:
        job_rows = await conn.fetch(
            """
            SELECT id, status, upload_filename, created_at,
                   retention_expires_at
            FROM processing_jobs
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT 20
            """,
            user_id,
        )

    now_utc = _dt.datetime.now(_dt.timezone.utc)
    jobs_out = []
    for row in job_rows:
        exp = row["retention_expires_at"]
        days_remaining = None
        if exp is not None:
            days_remaining = max(0, (exp - now_utc).days)
        jobs_out.append({
            "id": row["id"],
            "filename": row["upload_filename"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "retention_expires_at": exp.isoformat() if exp else None,
            "days_remaining": days_remaining,
            "status": row["status"],
        })

    # ── 3. Disk scan ─────────────────────────────────────────────────────────
    data_dir = Path(str(config.server.data_dir)) / username

    def _scan():
        if not data_dir.exists():
            return 0, {}
        lane_bytes_d: dict[str, int] = {}
        lane_count_d: dict[str, int] = {}
        total = 0
        for root, _dirs, files in os.walk(str(data_dir)):
            rp = Path(root)
            try:
                parts = rp.relative_to(data_dir).parts
                subdir = parts[0].lower() if parts else "other"
            except ValueError:
                subdir = "other"
            for fname in files:
                try:
                    sz = (rp / fname).stat().st_size
                except OSError:
                    continue
                total += sz
                lane_bytes_d[subdir] = lane_bytes_d.get(subdir, 0) + sz
                lane_count_d[subdir] = lane_count_d.get(subdir, 0) + 1
        return total, lane_bytes_d, lane_count_d

    total_bytes, lane_bytes, lane_count = await loop.run_in_executor(None, _scan)

    # ── 4. SQLite asset breakdown ─────────────────────────────────────────────
    db_path = Path(str(config.server.data_dir)) / username / "proc.db"

    def _sqlite_lanes():
        if not db_path.exists():
            return {}
        try:
            conn_sq = sqlite3.connect(str(db_path))
            conn_sq.row_factory = sqlite3.Row
            rows = conn_sq.execute(
                """
                SELECT asset_type,
                       COUNT(*) AS file_count,
                       SUM(COALESCE(file_size, 0)) AS size_bytes
                FROM assets
                GROUP BY asset_type
                """
            ).fetchall()
            conn_sq.close()
            return {r["asset_type"]: dict(r) for r in rows}
        except Exception:
            return {}

    sqlite_lanes = await loop.run_in_executor(None, _sqlite_lanes)

    # ── 5. Build breakdown list ──────────────────────────────────────────────
    known_lanes = ["memories", "chats", "stories"]
    all_keys = list(dict.fromkeys(
        known_lanes + [k for k in lane_bytes if k not in known_lanes]
    ))

    breakdown = []
    for lane_key in all_keys:
        sq = sqlite_lanes.get(lane_key, {})
        size_bytes = lane_bytes.get(lane_key, 0) or sq.get("size_bytes", 0) or 0
        file_count = lane_count.get(lane_key, 0) or sq.get("file_count", 0) or 0
        if size_bytes == 0 and file_count == 0:
            continue
        breakdown.append({
            "lane": lane_key,
            "file_count": file_count,
            "size_bytes": size_bytes,
        })

    # ── 6. Usage percentage ──────────────────────────────────────────────────
    quota_bytes = (limits["storage_gb"] * 1024 ** 3) if limits.get("storage_gb") else None
    usage_pct = round(total_bytes / quota_bytes * 100, 2) if quota_bytes else 0.0

    return {
        "tier": tier,
        "tier_label": limits["label"],
        "limits": {
            "storage_gb": limits.get("storage_gb"),
            "retention_days": limits.get("retention_days"),
            "concurrent_jobs": limits.get("concurrent_jobs"),
            "max_upload_bytes": limits.get("max_upload_bytes"),
            "max_upload_label": limits.get("max_upload_label"),
            "bulk_upload": limits.get("bulk_upload"),
        },
        "usage": {
            "total_bytes": total_bytes,
            "total_gb": round(total_bytes / (1024 ** 3), 3),
            "breakdown": breakdown,
        },
        "usage_pct": usage_pct,
        "jobs": jobs_out,
    }


@router.get("/quota/upload-history", response_class=HTMLResponse)
async def quota_upload_history(
    request: Request,
    username: str = Depends(get_current_user),
) -> HTMLResponse:
    """GET /api/quota/upload-history — HTML fragment: recent upload history table.

    Returns an HTML table (no wrapping template) suitable for htmx innerHTML swap.
    Lists the last 20 processing_jobs for the authenticated user, ordered by
    created_at DESC.
    """
    pool = request.app.state.db_pool
    templates = request.app.state.templates

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, upload_filename, created_at, upload_size_bytes, status
            FROM processing_jobs
            WHERE user_id = (SELECT id FROM users WHERE username = $1)
            ORDER BY created_at DESC
            LIMIT 20
            """,
            username,
        )

    uploads = []
    for row in rows:
        d = dict(row)
        if d.get("created_at") and hasattr(d["created_at"], "isoformat"):
            d["created_at"] = d["created_at"].isoformat()
        uploads.append(d)

    def _fmt_size(b: int | None) -> str:
        if not b:
            return "—"
        if b >= 1024 ** 3:
            return f"{b / (1024 ** 3):.1f} GB"
        if b >= 1024 ** 2:
            return f"{b / (1024 ** 2):.1f} MB"
        if b >= 1024:
            return f"{b / 1024:.1f} KB"
        return f"{b} B"

    # Build inline HTML fragment (no Jinja2 template dependency)
    if not uploads:
        html = '<p class="text-muted" style="font-size:0.9rem;padding:1rem 0;text-align:center;">No uploads yet.</p>'
    else:
        rows_html = ""
        for u in uploads:
            status_css = u["status"] or "unknown"
            created = (u["created_at"] or "")[:10]
            filename = u.get("upload_filename") or "—"
            size_str = _fmt_size(u.get("upload_size_bytes"))
            rows_html += (
                f'<tr style="border-bottom:1px solid rgba(255,255,255,0.04);">'
                f'<td style="padding:0.55rem 0.9rem;font-family:monospace;color:var(--snap-yellow);">'
                f'<a href="/results/{u["id"]}" style="color:var(--snap-yellow);text-decoration:none;">#{u["id"]}</a></td>'
                f'<td style="padding:0.55rem 0.9rem;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="{filename}">{filename}</td>'
                f'<td style="padding:0.55rem 0.9rem;color:var(--text-muted);font-family:monospace;font-size:0.8rem;">{created}</td>'
                f'<td style="padding:0.55rem 0.9rem;font-family:monospace;">{size_str}</td>'
                f'<td style="padding:0.55rem 0.9rem;">'
                f'<span class="status-badge status-{status_css}" style="font-size:0.75rem;padding:0.2rem 0.6rem;">{status_css}</span>'
                f'</td>'
                f'</tr>'
            )
        html = (
            '<div class="info-card" style="padding:0;overflow:hidden;">'
            '<table style="width:100%;border-collapse:collapse;font-size:0.85rem;">'
            '<thead><tr style="background:var(--charcoal);">'
            '<th style="text-align:left;padding:0.6rem 0.9rem;border-bottom:1px solid var(--border);color:var(--text-muted);font-size:0.75rem;text-transform:uppercase;letter-spacing:0.05em;">Job</th>'
            '<th style="text-align:left;padding:0.6rem 0.9rem;border-bottom:1px solid var(--border);color:var(--text-muted);font-size:0.75rem;text-transform:uppercase;letter-spacing:0.05em;">Filename</th>'
            '<th style="text-align:left;padding:0.6rem 0.9rem;border-bottom:1px solid var(--border);color:var(--text-muted);font-size:0.75rem;text-transform:uppercase;letter-spacing:0.05em;">Uploaded</th>'
            '<th style="text-align:left;padding:0.6rem 0.9rem;border-bottom:1px solid var(--border);color:var(--text-muted);font-size:0.75rem;text-transform:uppercase;letter-spacing:0.05em;">Size</th>'
            '<th style="text-align:left;padding:0.6rem 0.9rem;border-bottom:1px solid var(--border);color:var(--text-muted);font-size:0.75rem;text-transform:uppercase;letter-spacing:0.05em;">Status</th>'
            '</tr></thead>'
            f'<tbody>{rows_html}</tbody>'
            '</table></div>'
        )

    return HTMLResponse(content=html)


# --- P5-SLOT-29: Upload Size Limit Tiers API ---

@router.get("/upload-limits")
async def upload_limits(
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """GET /api/upload-limits — Return the current user's tier-based upload limits.

    Returns tier label, max_upload_bytes (null = unlimited), max_upload_label,
    bulk_upload flag, and current cumulative upload usage in bytes.
    """
    from snatched.tiers import get_tier_limits

    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT u.tier,
                   COALESCE(SUM(pj.upload_size_bytes), 0) AS current_usage_bytes
            FROM users u
            LEFT JOIN processing_jobs pj ON pj.user_id = u.id
            WHERE u.username = $1
            GROUP BY u.tier
            """,
            username,
        )

    if not row:
        tier = "free"
        current_usage = 0
    else:
        tier = row["tier"]
        current_usage = int(row["current_usage_bytes"])

    limits = get_tier_limits(tier)
    return {
        "tier": tier,
        "max_upload_bytes": limits["max_upload_bytes"],
        "max_upload_label": limits["max_upload_label"],
        "bulk_upload": limits["bulk_upload"],
        "current_usage_bytes": current_usage,
    }

# --- Feature #30: Retention Period Control API ---

@router.post("/jobs/{job_id}/extend-retention")
async def extend_retention(
    job_id: int,
    request: Request,
    username: str = Depends(get_current_user),
):
    """POST /api/jobs/{job_id}/extend-retention

    Extends the retention period for a job.
    Free tier: 403. Paid tiers: set retention_expires_at to NOW() + tier retention_days.
    Returns: { extended, new_expires_at, days_remaining }
    """
    from datetime import datetime, timezone, timedelta
    from snatched.tiers import get_tier_limits

    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        # Verify ownership
        job = await conn.fetchrow(
            """
            SELECT pj.id, pj.retention_expires_at
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        # Load user tier
        tier_row = await conn.fetchrow(
            "SELECT tier FROM users WHERE username = $1", username
        )
        tier = tier_row["tier"] if tier_row else "free"
        limits = get_tier_limits(tier)

        if tier == "free":
            raise HTTPException(status_code=403, detail="Upgrade to Pro to extend retention")

        retention_days = limits.get("retention_days")

        now = datetime.now(timezone.utc)
        new_expires = now + timedelta(days=retention_days)

        await conn.execute(
            "UPDATE processing_jobs SET retention_expires_at = $1 WHERE id = $2",
            new_expires, job_id,
        )

    days_remaining = (new_expires - now).days
    return {
        "extended": True,
        "new_expires_at": new_expires.isoformat(),
        "days_remaining": days_remaining,
    }


@router.get("/jobs/{job_id}/retention")
async def get_retention(
    job_id: int,
    request: Request,
    username: str = Depends(get_current_user),
):
    """GET /api/jobs/{job_id}/retention

    Returns retention metadata for a job.
    Returns: { retention_expires_at, days_remaining, tier, retention_days_allowed, can_extend }
    """
    from datetime import datetime, timezone
    from snatched.tiers import get_tier_limits

    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        job = await conn.fetchrow(
            """
            SELECT pj.id, pj.retention_expires_at
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        tier_row = await conn.fetchrow(
            "SELECT tier FROM users WHERE username = $1", username
        )

    tier = tier_row["tier"] if tier_row else "free"
    limits = get_tier_limits(tier)
    retention_days_allowed = limits.get("retention_days")
    can_extend = tier != "free"

    expires_at = job["retention_expires_at"]
    days_remaining = None
    if expires_at is not None:
        now = datetime.now(timezone.utc)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        days_remaining = (expires_at - now).days
        expires_iso = expires_at.isoformat()
    else:
        expires_iso = None

    return {
        "retention_expires_at": expires_iso,
        "days_remaining": days_remaining,
        "tier": tier,
        "retention_days_allowed": retention_days_allowed,
        "can_extend": can_extend,
    }


# --- Feature #31: Concurrent Job Slots API ---

@router.get("/slots")
async def get_slots(
    request: Request,
    username: str = Depends(get_current_user),
):
    """GET /api/slots

    Returns slot usage and queue information for the current user.
    Returns: { tier, tier_label, max_slots, active_jobs, available_slots, queue_position }
    """
    from snatched.tiers import get_tier_limits

    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        tier_row = await conn.fetchrow(
            "SELECT tier FROM users WHERE username = $1", username
        )
        tier = tier_row["tier"] if tier_row else "free"

        active_row = await conn.fetchrow(
            """
            SELECT COUNT(*) as active_count
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE u.username = $1 AND pj.status IN ('running', 'pending')
            """,
            username,
        )
        active_jobs = active_row["active_count"] if active_row else 0

    limits = get_tier_limits(tier)
    max_slots = limits.get("concurrent_jobs")
    tier_label = limits.get("label", tier.title())

    if max_slots is None:
        available_slots = None
        queue_position = None
    else:
        available_slots = max(0, max_slots - active_jobs)
        queue_position = None

        if available_slots == 0:
            async with pool.acquire() as conn:
                oldest = await conn.fetchrow(
                    """
                    SELECT pj.created_at
                    FROM processing_jobs pj
                    JOIN users u ON pj.user_id = u.id
                    WHERE u.username = $1 AND pj.status = 'pending'
                    ORDER BY pj.created_at ASC
                    LIMIT 1
                    """,
                    username,
                )
                if oldest and oldest["created_at"]:
                    pos_row = await conn.fetchrow(
                        """
                        SELECT COUNT(*) as pos
                        FROM processing_jobs
                        WHERE status = 'pending' AND created_at < $1
                        """,
                        oldest["created_at"],
                    )
                    queue_position = (pos_row["pos"] + 1) if pos_row else 1

    return {
        "tier": tier,
        "tier_label": tier_label,
        "max_slots": max_slots,
        "active_jobs": active_jobs,
        "available_slots": available_slots,
        "queue_position": queue_position,
    }

# --- P5-SLOT-32: Bulk Upload Support API ---

@router.get("/job-groups/{group_id}")
async def get_job_group(
    request: Request,
    group_id: str,
    username: str = Depends(get_current_user),
) -> dict:
    """GET /api/job-groups/{group_id} — Return all jobs in a bulk upload group.

    Jobs are ordered by creation time ascending.
    """
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT pj.id, pj.upload_filename, pj.status, pj.created_at
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.job_group_id = $1 AND u.username = $2
            ORDER BY pj.created_at ASC
            """,
            group_id,
            username,
        )

    jobs = [
        {
            "id": r["id"],
            "filename": r["upload_filename"],
            "status": r["status"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]

    return {"group_id": group_id, "jobs": jobs}


@router.get("/job-groups")
async def list_job_groups(
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """GET /api/job-groups — List all job groups for the current user.

    Returns one entry per distinct job_group_id with job count,
    earliest creation time, and a comma-separated list of distinct statuses.
    """
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                pj.job_group_id,
                COUNT(*) AS job_count,
                MIN(pj.created_at) AS created_at,
                array_agg(DISTINCT pj.status) AS statuses
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.job_group_id IS NOT NULL AND u.username = $1
            GROUP BY pj.job_group_id
            ORDER BY MIN(pj.created_at) DESC
            """,
            username,
        )

    groups = [
        {
            "group_id": r["job_group_id"],
            "job_count": r["job_count"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "statuses": list(r["statuses"]) if r["statuses"] else [],
        }
        for r in rows
    ]

    return {"groups": groups}


# --- Feature #33: API Access Keys ---

_API_KEY_TIER_LIMITS = {
    "free":      {"max_keys": 0,    "rate_limit_rpm": 0},
    "pro":       {"max_keys": 3,    "rate_limit_rpm": 60},
}


class ApiKeyCreateBody(BaseModel):
    name: str = Field(default="default", max_length=80)
    scopes: str = Field(default="read,write", max_length=200)


@router.post("/keys")
async def create_api_key(
    body: ApiKeyCreateBody,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """POST /api/keys — Create a new API access key.

    Generates a cryptographically random 32-byte hex token. The full token
    is returned exactly once — it is never stored. Only a SHA-256 hash and
    the first 8-character prefix are persisted.

    Tier gate: free tier returns 403. Pro/Team/Unlimited check the key count.
    """
    import hashlib
    import secrets
    from snatched.tiers import get_tier_limits

    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        tier_row = await conn.fetchrow(
            "SELECT id, tier FROM users WHERE username = $1", username
        )
        if not tier_row:
            raise HTTPException(status_code=404, detail="User not found")
        user_id = int(tier_row["id"])
        tier = tier_row["tier"] or "free"

        key_limits = _API_KEY_TIER_LIMITS.get(tier, _API_KEY_TIER_LIMITS["free"])
        max_keys = key_limits["max_keys"]
        rate_limit_rpm = key_limits["rate_limit_rpm"]

        if max_keys == 0:
            raise HTTPException(
                status_code=403,
                detail="API keys require Pro tier or above. Upgrade your plan to create API keys.",
            )

        # Count existing active (non-revoked) keys
        active_count = await conn.fetchval(
            """
            SELECT COUNT(*) FROM api_keys
            WHERE user_id = $1 AND revoked_at IS NULL
            """,
            user_id,
        )

        if max_keys is not None and active_count >= max_keys:
            raise HTTPException(
                status_code=403,
                detail=f"API key limit reached ({max_keys} keys max on {tier} plan). Revoke an existing key or upgrade.",
            )

        # Generate token: "sn_" prefix + 32 random hex bytes
        raw_token = "sn_" + secrets.token_hex(32)
        key_prefix = raw_token[:11]  # "sn_" + first 8 hex chars = 11 chars
        key_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        row = await conn.fetchrow(
            """
            INSERT INTO api_keys (user_id, key_hash, key_prefix, name, scopes, rate_limit_rpm)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id, name, key_prefix, scopes, rate_limit_rpm, created_at
            """,
            user_id, key_hash, key_prefix, body.name, body.scopes, rate_limit_rpm,
        )

    return {
        "id": row["id"],
        "token": raw_token,  # Full token — shown ONCE, never stored
        "key_prefix": row["key_prefix"],
        "name": row["name"],
        "scopes": row["scopes"],
        "rate_limit_rpm": row["rate_limit_rpm"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


@router.get("/keys")
async def list_api_keys(
    request: Request,
    username: str = Depends(get_current_user),
) -> list[dict]:
    """GET /api/keys — List all API keys for the authenticated user.

    Returns id, name, key_prefix, scopes, rate_limit_rpm, created_at,
    last_used_at, and revoked_at for each key. The full token is never
    returned — only the prefix.
    """
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ak.id, ak.name, ak.key_prefix, ak.scopes,
                   ak.rate_limit_rpm, ak.created_at, ak.last_used_at, ak.revoked_at
            FROM api_keys ak
            JOIN users u ON ak.user_id = u.id
            WHERE u.username = $1
            ORDER BY ak.created_at DESC
            """,
            username,
        )

    return [
        {
            "id": r["id"],
            "name": r["name"],
            "key_prefix": r["key_prefix"],
            "scopes": r["scopes"],
            "rate_limit_rpm": r["rate_limit_rpm"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "last_used_at": r["last_used_at"].isoformat() if r["last_used_at"] else None,
            "revoked_at": r["revoked_at"].isoformat() if r["revoked_at"] else None,
        }
        for r in rows
    ]


@router.delete("/keys/{key_id}")
async def revoke_api_key(
    key_id: int,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """DELETE /api/keys/{key_id} — Revoke an API key (soft delete).

    Sets revoked_at = NOW(). The key record is preserved for audit purposes.
    Returns 404 if the key does not belong to the authenticated user.
    Returns 409 if the key is already revoked.
    """
    from datetime import datetime, timezone

    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        # Verify ownership and fetch current state
        row = await conn.fetchrow(
            """
            SELECT ak.id, ak.revoked_at
            FROM api_keys ak
            JOIN users u ON ak.user_id = u.id
            WHERE ak.id = $1 AND u.username = $2
            """,
            key_id, username,
        )
        if not row:
            raise HTTPException(status_code=404, detail="API key not found")

        if row["revoked_at"] is not None:
            raise HTTPException(status_code=409, detail="API key is already revoked")

        now = datetime.now(timezone.utc)
        await conn.execute(
            "UPDATE api_keys SET revoked_at = $1 WHERE id = $2",
            now, key_id,
        )

    return {"revoked": True, "key_id": key_id, "revoked_at": now.isoformat()}


# --- Feature #34: Webhook Notifications (CRUD + test) ---

_WEBHOOK_TIER_LIMITS = {
    "free": 0,
    "pro": 3,
}


class WebhookCreate(BaseModel):
    url: str
    name: str = ""
    events: str = "job.completed,job.failed"
    secret: str | None = None


class WebhookUpdate(BaseModel):
    url: str | None = None
    name: str | None = None
    events: str | None = None
    active: bool | None = None
    secret: str | None = None


async def _get_user_tier_for_webhooks(pool, username: str) -> str:
    """Return the tier for a username, defaulting to 'free'."""
    async with pool.acquire() as conn:
        tier = await conn.fetchval("SELECT tier FROM users WHERE username = $1", username)
    return tier or "free"


@router.post("/webhooks")
async def create_webhook(
    request: Request,
    body: WebhookCreate,
    username: str = Depends(get_current_user),
) -> dict:
    """POST /api/webhooks -- Create a new webhook for the current user.

    Validates HTTPS URL and enforces tier-based webhook count limit.
    """
    pool = request.app.state.db_pool

    if not body.url.startswith("https://"):
        raise HTTPException(400, "Webhook URL must start with https://")

    tier = await _get_user_tier_for_webhooks(pool, username)
    max_wh = _WEBHOOK_TIER_LIMITS.get(tier, 0)

    async with pool.acquire() as conn:
        if max_wh is not None:
            count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM webhooks w
                JOIN users u ON w.user_id = u.id
                WHERE u.username = $1
                """,
                username,
            )
            if count >= max_wh:
                if max_wh == 0:
                    raise HTTPException(403, "Webhooks require Pro tier or above")
                raise HTTPException(
                    403,
                    f"Webhook limit reached ({max_wh} max on {tier.title()} plan). Upgrade to add more.",
                )

        row = await conn.fetchrow(
            """
            INSERT INTO webhooks (user_id, url, name, events, secret)
            SELECT u.id, $2, $3, $4, $5
            FROM users u WHERE u.username = $1
            RETURNING id, url, name, events, secret, active,
                      last_triggered_at, last_status_code, failure_count, created_at
            """,
            username,
            body.url,
            body.name,
            body.events,
            body.secret,
        )

    if not row:
        raise HTTPException(404, "User not found")

    return {
        "id": row["id"],
        "url": row["url"],
        "name": row["name"],
        "events": row["events"],
        "secret": row["secret"],
        "active": row["active"],
        "last_triggered_at": row["last_triggered_at"].isoformat() if row["last_triggered_at"] else None,
        "last_status_code": row["last_status_code"],
        "failure_count": row["failure_count"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


@router.get("/webhooks")
async def list_webhooks(
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """GET /api/webhooks -- List all webhooks for the current user."""
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT w.id, w.url, w.name, w.events, w.secret, w.active,
                   w.last_triggered_at, w.last_status_code, w.failure_count, w.created_at
            FROM webhooks w
            JOIN users u ON w.user_id = u.id
            WHERE u.username = $1
            ORDER BY w.created_at DESC
            """,
            username,
        )

    return {
        "webhooks": [
            {
                "id": r["id"],
                "url": r["url"],
                "name": r["name"],
                "events": r["events"],
                "secret": r["secret"],
                "active": r["active"],
                "last_triggered_at": r["last_triggered_at"].isoformat() if r["last_triggered_at"] else None,
                "last_status_code": r["last_status_code"],
                "failure_count": r["failure_count"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]
    }


@router.put("/webhooks/{webhook_id}")
async def update_webhook(
    request: Request,
    webhook_id: int,
    body: WebhookUpdate,
    username: str = Depends(get_current_user),
) -> dict:
    """PUT /api/webhooks/{webhook_id} -- Update a webhook (url, name, events, active, secret)."""
    pool = request.app.state.db_pool

    if body.url is not None and not body.url.startswith("https://"):
        raise HTTPException(400, "Webhook URL must start with https://")

    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            """
            SELECT w.id, w.url, w.name, w.events, w.active, w.secret
            FROM webhooks w
            JOIN users u ON w.user_id = u.id
            WHERE w.id = $1 AND u.username = $2
            """,
            webhook_id,
            username,
        )
        if not existing:
            raise HTTPException(404, "Webhook not found")

        new_url = body.url if body.url is not None else existing["url"]
        new_name = body.name if body.name is not None else existing["name"]
        new_events = body.events if body.events is not None else existing["events"]
        new_active = body.active if body.active is not None else existing["active"]
        new_secret = body.secret if body.secret is not None else existing["secret"]

        row = await conn.fetchrow(
            """
            UPDATE webhooks
            SET url = $2, name = $3, events = $4, active = $5, secret = $6
            WHERE id = $1
            RETURNING id, url, name, events, secret, active,
                      last_triggered_at, last_status_code, failure_count, created_at
            """,
            webhook_id,
            new_url,
            new_name,
            new_events,
            new_active,
            new_secret,
        )

    return {
        "id": row["id"],
        "url": row["url"],
        "name": row["name"],
        "events": row["events"],
        "secret": row["secret"],
        "active": row["active"],
        "last_triggered_at": row["last_triggered_at"].isoformat() if row["last_triggered_at"] else None,
        "last_status_code": row["last_status_code"],
        "failure_count": row["failure_count"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


@router.delete("/webhooks/{webhook_id}")
async def delete_webhook(
    request: Request,
    webhook_id: int,
    username: str = Depends(get_current_user),
) -> dict:
    """DELETE /api/webhooks/{webhook_id} -- Permanently delete a webhook."""
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        deleted = await conn.fetchval(
            """
            DELETE FROM webhooks
            WHERE id = $1
              AND user_id = (SELECT id FROM users WHERE username = $2)
            RETURNING id
            """,
            webhook_id,
            username,
        )

    if not deleted:
        raise HTTPException(404, "Webhook not found")

    return {"deleted": True, "webhook_id": webhook_id}


@router.post("/webhooks/{webhook_id}/test")
async def test_webhook(
    request: Request,
    webhook_id: int,
    username: str = Depends(get_current_user),
) -> dict:
    """POST /api/webhooks/{webhook_id}/test -- Fire a test payload at the webhook URL.

    Uses urllib.request (stdlib only -- no httpx).
    Updates last_triggered_at and last_status_code regardless of outcome.
    Returns the HTTP status code received (or 0 on connection error).
    """
    import urllib.request as _urllib_req
    import urllib.error as _urllib_err
    from datetime import datetime, timezone

    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT w.id, w.url
            FROM webhooks w
            JOIN users u ON w.user_id = u.id
            WHERE w.id = $1 AND u.username = $2
            """,
            webhook_id,
            username,
        )

    if not row:
        raise HTTPException(404, "Webhook not found")

    target_url = row["url"]
    payload = json.dumps({
        "event": "test",
        "job_id": 0,
        "message": "Test webhook from Snatched",
    }).encode("utf-8")

    status_code = 0
    try:
        req = _urllib_req.Request(
            target_url,
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "Snatched-Webhook/3.0"},
            method="POST",
        )
        with _urllib_req.urlopen(req, timeout=10) as resp:
            status_code = resp.status
    except _urllib_err.HTTPError as exc:
        status_code = exc.code
    except Exception:
        status_code = 0

    now = datetime.now(timezone.utc)

    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE webhooks
            SET last_triggered_at = $2,
                last_status_code = $3,
                failure_count = CASE WHEN $3 >= 200 AND $3 < 300
                                     THEN 0
                                     ELSE failure_count + 1
                                END
            WHERE id = $1
            """,
            webhook_id,
            now,
            status_code,
        )

    return {
        "webhook_id": webhook_id,
        "status_code": status_code,
        "triggered_at": now.isoformat(),
        "success": 200 <= status_code < 300,
    }


# --- P6-SLOT-REPORTS: Job report download endpoints ---


@router.get("/jobs/{job_id}/match-report")
async def job_match_report(
    job_id: int,
    request: Request,
    format: str = Query("csv"),
    username: str = Depends(get_current_user),
):
    """GET /api/jobs/{job_id}/match-report?format=csv|json

    Per-file match report: each match joined with its asset and memory.
    CSV columns: asset_filename, media_type, match_strategy, confidence,
                 memory_date, memory_type, memory_lat, memory_lon, is_correct
    """
    import csv as csv_mod

    config = request.app.state.config
    pool = request.app.state.db_pool

    # Verify job belongs to this user
    async with pool.acquire() as conn:
        owner = await conn.fetchval(
            """
            SELECT u.username FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1
            """,
            job_id,
        )

    if owner != username:
        raise HTTPException(403, "Access denied")

    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    if not db_path.exists():
        raise HTTPException(404, "No processing database found for this job")

    loop = asyncio.get_running_loop()

    def _query_matches():
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
                a.filename          AS asset_filename,
                a.asset_type        AS media_type,
                m.strategy          AS match_strategy,
                m.confidence        AS confidence,
                mem.date            AS memory_date,
                mem.media_type      AS memory_type,
                mem.lat             AS memory_lat,
                mem.lon             AS memory_lon
            FROM matches m
            JOIN assets a   ON m.asset_id  = a.id
            LEFT JOIN memories mem ON m.memory_id = mem.id
            ORDER BY a.filename, m.confidence DESC
            """,
            (),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    rows = await loop.run_in_executor(None, _query_matches)

    if format == "csv":
        output = io.StringIO()
        writer = csv_mod.writer(output)
        writer.writerow([
            "asset_filename", "media_type", "match_strategy", "confidence",
            "memory_date", "memory_type", "memory_lat", "memory_lon",
        ])
        for r in rows:
            writer.writerow([
                r.get("asset_filename", ""),
                r.get("media_type", ""),
                r.get("match_strategy", ""),
                r.get("confidence", ""),
                r.get("memory_date", ""),
                r.get("memory_type", ""),
                r.get("memory_lat", ""),
                r.get("memory_lon", ""),
            ])
        content = output.getvalue()
        return StreamingResponse(
            iter([content]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=snatched-job-{job_id}-match-report.csv"},
        )
    else:
        return StreamingResponse(
            iter([json.dumps(rows, indent=2)]),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=snatched-job-{job_id}-match-report.json"},
        )


@router.get("/jobs/{job_id}/asset-report")
async def job_asset_report(
    job_id: int,
    request: Request,
    format: str = Query("csv"),
    username: str = Depends(get_current_user),
):
    """GET /api/jobs/{job_id}/asset-report?format=csv|json

    All assets for the job with match status and EXIF info.
    CSV columns: filename, media_type, file_size, sha256, has_exif, exif_date,
                 exif_lat, exif_lon, match_count, best_confidence, best_strategy
    """
    import csv as csv_mod

    config = request.app.state.config
    pool = request.app.state.db_pool

    # Verify job belongs to this user
    async with pool.acquire() as conn:
        owner = await conn.fetchval(
            """
            SELECT u.username FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1
            """,
            job_id,
        )

    if owner != username:
        raise HTTPException(403, "Access denied")

    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    if not db_path.exists():
        raise HTTPException(404, "No processing database found for this job")

    loop = asyncio.get_running_loop()

    def _query_assets():
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
                a.filename                                                          AS filename,
                a.asset_type                                                        AS media_type,
                a.file_size                                                         AS file_size,
                a.sha256                                                            AS sha256,
                a.exif_written                                                      AS has_exif,
                a.date_str                                                          AS exif_date,
                MAX(CASE WHEN m.is_best = 1 THEN m.matched_lat ELSE NULL END)      AS exif_lat,
                MAX(CASE WHEN m.is_best = 1 THEN m.matched_lon ELSE NULL END)      AS exif_lon,
                COUNT(m.id)                                                         AS match_count,
                MAX(m.confidence)                                                   AS best_confidence,
                MAX(CASE WHEN m.confidence = (
                    SELECT MAX(m2.confidence) FROM matches m2
                    WHERE m2.asset_id = a.id
                ) THEN m.strategy ELSE NULL END)                                    AS best_strategy
            FROM assets a
            LEFT JOIN matches m ON m.asset_id = a.id
            GROUP BY a.id
            ORDER BY a.filename
            """,
            (),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    rows = await loop.run_in_executor(None, _query_assets)

    if format == "csv":
        output = io.StringIO()
        writer = csv_mod.writer(output)
        writer.writerow([
            "filename", "media_type", "file_size", "sha256", "has_exif",
            "exif_date", "exif_lat", "exif_lon", "match_count", "best_confidence", "best_strategy",
        ])
        for r in rows:
            writer.writerow([
                r.get("filename", ""),
                r.get("media_type", ""),
                r.get("file_size", ""),
                r.get("sha256", ""),
                r.get("has_exif", ""),
                r.get("exif_date", ""),
                r.get("exif_lat", ""),
                r.get("exif_lon", ""),
                r.get("match_count", 0),
                r.get("best_confidence", ""),
                r.get("best_strategy", ""),
            ])
        content = output.getvalue()
        return StreamingResponse(
            iter([content]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=snatched-job-{job_id}-asset-report.csv"},
        )
    else:
        return StreamingResponse(
            iter([json.dumps(rows, indent=2)]),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=snatched-job-{job_id}-asset-report.json"},
        )


# --- P6-SLOT-SCHEDULES: CRUD for scheduled/recurring exports ---

import datetime as _dt


def _calc_next_run(frequency: str, day_of_month: int | None, day_of_week: int | None) -> _dt.datetime:
    """Calculate next_run_at (UTC) for a given schedule frequency.

    - monthly:  next occurrence of day_of_month (1-28) at 09:00 UTC
    - weekly:   next occurrence of day_of_week (0=Mon, 6=Sun) at 09:00 UTC
    - biweekly: exactly 14 days from now at 09:00 UTC
    """
    now = _dt.datetime.now(_dt.timezone.utc)
    target_hour = 9  # 09:00 UTC

    if frequency == "monthly":
        dom = day_of_month or 1
        candidate = now.replace(day=1, hour=target_hour, minute=0, second=0, microsecond=0)
        try:
            candidate = candidate.replace(day=dom)
        except ValueError:
            # day_of_month > days-in-month: fall back to 28
            candidate = candidate.replace(day=28)
        if candidate <= now:
            if candidate.month == 12:
                candidate = candidate.replace(year=candidate.year + 1, month=1)
            else:
                candidate = candidate.replace(month=candidate.month + 1)
        return candidate

    elif frequency == "weekly":
        dow = day_of_week if day_of_week is not None else 0  # default Monday
        days_ahead = (dow - now.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        target_date = (now + _dt.timedelta(days=days_ahead)).date()
        return _dt.datetime(
            target_date.year, target_date.month, target_date.day,
            target_hour, 0, 0, tzinfo=_dt.timezone.utc,
        )

    else:  # biweekly
        target = now + _dt.timedelta(days=14)
        return target.replace(hour=target_hour, minute=0, second=0, microsecond=0)


_SCHEDULE_TIER_LIMITS: dict[str, int] = {
    "free":      0,
    "pro":       2,
}


class ScheduleCreateBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    frequency: str = Field("monthly", pattern=r"^(monthly|weekly|biweekly)$")
    day_of_month: int | None = Field(None, ge=1, le=28)
    day_of_week: int | None = Field(None, ge=0, le=6)
    notify_email: bool = False
    notify_webhook: bool = False


class ScheduleUpdateBody(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    frequency: str | None = Field(None, pattern=r"^(monthly|weekly|biweekly)$")
    day_of_month: int | None = Field(None, ge=1, le=28)
    day_of_week: int | None = Field(None, ge=0, le=6)
    active: bool | None = None
    notify_email: bool | None = None
    notify_webhook: bool | None = None


@router.post("/schedules")
async def create_schedule(
    request: Request,
    body: ScheduleCreateBody,
    username: str = Depends(get_current_user),
) -> dict:
    """POST /api/schedules — Create a new recurring export schedule.

    Checks tier limit before inserting. Calculates next_run_at from frequency.
    """
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        tier = await conn.fetchval(
            "SELECT tier FROM users WHERE username = $1", username
        ) or "free"
        max_schedules = _SCHEDULE_TIER_LIMITS.get(tier, 0)

        if max_schedules == 0:
            raise HTTPException(403, "Scheduled exports require Pro tier or above.")

        user_id = await conn.fetchval(
            "SELECT id FROM users WHERE username = $1", username
        )
        if not user_id:
            raise HTTPException(404, "User not found.")

        current_count = await conn.fetchval(
            "SELECT COUNT(*) FROM schedules WHERE user_id = $1", user_id
        )
        if max_schedules is not None and current_count >= max_schedules:
            raise HTTPException(
                403,
                f"Schedule limit reached ({max_schedules} for {tier} tier). "
                "Delete an existing schedule or upgrade your plan.",
            )

        next_run = _calc_next_run(body.frequency, body.day_of_month, body.day_of_week)

        row = await conn.fetchrow(
            """
            INSERT INTO schedules
                (user_id, name, frequency, day_of_month, day_of_week,
                 next_run_at, active, notify_email, notify_webhook)
            VALUES ($1, $2, $3, $4, $5, $6, true, $7, $8)
            RETURNING id, name, frequency, day_of_month, day_of_week,
                      next_run_at, last_run_at, active,
                      notify_email, notify_webhook, created_at
            """,
            user_id, body.name, body.frequency, body.day_of_month, body.day_of_week,
            next_run, body.notify_email, body.notify_webhook,
        )

    return {
        "id": row["id"],
        "name": row["name"],
        "frequency": row["frequency"],
        "day_of_month": row["day_of_month"],
        "day_of_week": row["day_of_week"],
        "next_run_at": row["next_run_at"].isoformat() if row["next_run_at"] else None,
        "last_run_at": row["last_run_at"].isoformat() if row["last_run_at"] else None,
        "active": row["active"],
        "notify_email": row["notify_email"],
        "notify_webhook": row["notify_webhook"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


@router.get("/schedules")
async def list_schedules(
    request: Request,
    username: str = Depends(get_current_user),
) -> list[dict]:
    """GET /api/schedules — List all schedules for the authenticated user."""
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT s.id, s.name, s.frequency, s.day_of_month, s.day_of_week,
                   s.next_run_at, s.last_run_at, s.active,
                   s.notify_email, s.notify_webhook, s.created_at
            FROM schedules s
            JOIN users u ON s.user_id = u.id
            WHERE u.username = $1
            ORDER BY s.created_at DESC
            """,
            username,
        )

    return [
        {
            "id": r["id"],
            "name": r["name"],
            "frequency": r["frequency"],
            "day_of_month": r["day_of_month"],
            "day_of_week": r["day_of_week"],
            "next_run_at": r["next_run_at"].isoformat() if r["next_run_at"] else None,
            "last_run_at": r["last_run_at"].isoformat() if r["last_run_at"] else None,
            "active": r["active"],
            "notify_email": r["notify_email"],
            "notify_webhook": r["notify_webhook"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]


@router.put("/schedules/{schedule_id}")
async def update_schedule(
    schedule_id: int,
    request: Request,
    body: ScheduleUpdateBody,
    username: str = Depends(get_current_user),
) -> dict:
    """PUT /api/schedules/{schedule_id} — Update a schedule.

    Only fields present in the body are updated. Recalculates next_run_at
    whenever frequency, day_of_month, or day_of_week changes.
    """
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            """
            SELECT s.id, s.frequency, s.day_of_month, s.day_of_week,
                   s.name, s.active, s.notify_email, s.notify_webhook,
                   s.next_run_at, s.last_run_at, s.created_at
            FROM schedules s
            JOIN users u ON s.user_id = u.id
            WHERE s.id = $1 AND u.username = $2
            """,
            schedule_id, username,
        )
        if not existing:
            raise HTTPException(404, "Schedule not found.")

        # Merge incoming changes with existing values
        new_name = body.name if body.name is not None else existing["name"]
        new_freq = body.frequency if body.frequency is not None else existing["frequency"]
        new_dom = body.day_of_month if body.day_of_month is not None else existing["day_of_month"]
        new_dow = body.day_of_week if body.day_of_week is not None else existing["day_of_week"]
        new_active = body.active if body.active is not None else existing["active"]
        new_email = body.notify_email if body.notify_email is not None else existing["notify_email"]
        new_webhook = body.notify_webhook if body.notify_webhook is not None else existing["notify_webhook"]

        # Recalculate next_run_at only when scheduling fields changed
        schedule_changed = (
            new_freq != existing["frequency"]
            or new_dom != existing["day_of_month"]
            or new_dow != existing["day_of_week"]
        )
        next_run = _calc_next_run(new_freq, new_dom, new_dow) if schedule_changed else existing["next_run_at"]

        row = await conn.fetchrow(
            """
            UPDATE schedules
            SET name = $1, frequency = $2, day_of_month = $3, day_of_week = $4,
                next_run_at = $5, active = $6, notify_email = $7, notify_webhook = $8
            WHERE id = $9
            RETURNING id, name, frequency, day_of_month, day_of_week,
                      next_run_at, last_run_at, active,
                      notify_email, notify_webhook, created_at
            """,
            new_name, new_freq, new_dom, new_dow, next_run,
            new_active, new_email, new_webhook, schedule_id,
        )

    return {
        "id": row["id"],
        "name": row["name"],
        "frequency": row["frequency"],
        "day_of_month": row["day_of_month"],
        "day_of_week": row["day_of_week"],
        "next_run_at": row["next_run_at"].isoformat() if row["next_run_at"] else None,
        "last_run_at": row["last_run_at"].isoformat() if row["last_run_at"] else None,
        "active": row["active"],
        "notify_email": row["notify_email"],
        "notify_webhook": row["notify_webhook"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(
    schedule_id: int,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """DELETE /api/schedules/{schedule_id} — Permanently delete a schedule."""
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        deleted = await conn.fetchval(
            """
            DELETE FROM schedules
            WHERE id = $1
              AND user_id = (SELECT id FROM users WHERE username = $2)
            RETURNING id
            """,
            schedule_id, username,
        )

    if not deleted:
        raise HTTPException(404, "Schedule not found.")

    return {"deleted": True, "schedule_id": schedule_id}


# --- STORY-3: Scan results API ---
@router.get("/jobs/{job_id}/scan-results")
async def get_scan_results(
    job_id: int,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """GET /api/jobs/{job_id}/scan-results — Get ingest scan results (asset counts by type).

    Returns counts of memories, stories, chats, and total bytes.
    Only available if job status is 'scanned' (ingest complete, waiting for configuration).

    Response (200): {
        "memories": 42,
        "stories": 15,
        "chats": 8,
        "total_assets": 65,
        "total_size_bytes": 1234567890
    }
    """
    pool = request.app.state.db_pool
    config = request.app.state.config

    # Verify job ownership
    async with pool.acquire() as conn:
        job_row = await conn.fetchrow(
            """
            SELECT pj.id, pj.status, pj.upload_size_bytes, u.id as user_id
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )

    if not job_row:
        raise HTTPException(404, "Job not found")

    if job_row["status"] not in ("scanned", "completed"):
        raise HTTPException(
            400,
            f"Scan results only available after ingest (current status: {job_row['status']})"
        )

    # Open the per-user SQLite database
    data_dir = Path(str(config.server.data_dir)) / username
    db_path = data_dir / "proc.db"

    if not db_path.exists():
        raise HTTPException(500, "Processing database not found")

    # Query SQLite for asset counts by type
    try:
        db = sqlite3.connect(str(db_path))
        db.row_factory = sqlite3.Row

        # Count memories (memory_main + memory_overlay)
        memory_main_count = db.execute(
            "SELECT COUNT(*) FROM assets WHERE asset_type = 'memory_main'"
        ).fetchone()[0]
        memory_overlay_count = db.execute(
            "SELECT COUNT(*) FROM assets WHERE asset_type = 'memory_overlay'"
        ).fetchone()[0]
        memories = memory_main_count + memory_overlay_count

        # Count stories
        stories = db.execute(
            "SELECT COUNT(*) FROM assets WHERE asset_type = 'story'"
        ).fetchone()[0]

        # Count chats
        chats = db.execute(
            "SELECT COUNT(*) FROM assets WHERE asset_type LIKE 'chat%'"
        ).fetchone()[0]

        # Total assets
        total_assets = db.execute(
            "SELECT COUNT(*) FROM assets"
        ).fetchone()[0]

        db.close()

        return {
            "memories": memories,
            "stories": stories,
            "chats": chats,
            "total_assets": total_assets,
            "total_size_bytes": job_row["upload_size_bytes"] or 0,
        }

    except sqlite3.Error as e:
        logger.error(f"Failed to query scan results for job {job_id}: {e}")
        raise HTTPException(500, f"Failed to read scan results: {e}")


# --- STORY-4: Configure and start remaining phases ---
@router.post("/jobs/{job_id}/configure")
async def configure_and_start(
    job_id: int,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """POST /api/jobs/{job_id}/configure — Set lanes/options and start remaining phases.

    Request body: {
        "lanes": ["memories", "chats"],  // or ["stories"] or any combo
        "options": {
            "burn_overlays": true,
            "dark_mode_pngs": false,
            "exif_enabled": true,
            "xmp_enabled": false,
            "gps_window_seconds": 300
        }
    }

    Only works if job status is 'scanned'. Updates job and starts match→enrich→export
    in the background.

    Response (200): {
        "status": "running",
        "job_id": 42,
        "phases": ["match", "enrich", "export"]
    }
    """
    pool = request.app.state.db_pool
    config = request.app.state.config

    # Parse request body
    try:
        body = await request.json()
        lanes = body.get("lanes", ["memories", "chats", "stories"])
        options = body.get("options", {})
    except Exception as e:
        raise HTTPException(400, f"Invalid request body: {e}")

    # Validate lanes
    valid_lanes = {"memories", "chats", "stories"}
    lanes = [l for l in lanes if l in valid_lanes]
    if not lanes:
        lanes = ["memories", "chats", "stories"]

    # Verify job ownership and status
    async with pool.acquire() as conn:
        job_row = await conn.fetchrow(
            """
            SELECT pj.id, pj.status, pj.phases_requested, u.id as user_id
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )

    if not job_row:
        raise HTTPException(404, "Job not found")

    if job_row["status"] != "scanned":
        raise HTTPException(
            400,
            f"Configuration only available for scanned jobs (current status: {job_row['status']})"
        )

    # Only update preferences if options were explicitly provided
    if options:
        gps_window = int(options.get("gps_window_seconds", 300))
        gps_window = max(30, min(1800, gps_window))
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
                job_row["user_id"],
                bool(options.get("burn_overlays", True)),
                bool(options.get("dark_mode_pngs", False)),
                bool(options.get("exif_enabled", True)),
                bool(options.get("xmp_enabled", False)),
                gps_window,
            )

    # Get processing mode to determine which phases to run
    async with pool.acquire() as conn:
        mode_row = await conn.fetchval(
            "SELECT processing_mode FROM processing_jobs WHERE id=$1", job_id
        )
    processing_mode = mode_row or "speed_run"

    if processing_mode == "power_user":
        # Power User: run only match, pause for review
        remaining_phases = ["match"]
    else:
        # Speed Run: run all remaining phases
        remaining_phases = ["match", "enrich", "export"]

    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE processing_jobs
                SET lanes_requested = $1, phases_requested = $2, status = 'running'
                WHERE id = $3
                """,
                lanes,
                ["ingest"] + remaining_phases,
                job_id,
            )

        logger.info(
            f"Job {job_id} configured with lanes={lanes}. Starting remaining phases..."
        )

        # Schedule remaining phases to run in background
        asyncio.create_task(
            _run_remaining_phases(pool, job_id, username, config, remaining_phases)
        )

        return {
            "status": "running",
            "job_id": job_id,
            "phases": remaining_phases,
        }

    except Exception as e:
        logger.error(f"Failed to configure job {job_id}: {e}", exc_info=True)
        raise HTTPException(500, f"Failed to configure job: {e}")


@router.post("/jobs/{job_id}/start-enrich")
async def start_enrich(
    job_id: int,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """Power User: start enrich phase after reviewing match results.

    Only valid when job status is 'matched'.
    """
    from snatched.db import update_job

    pool = request.app.state.db_pool
    config = request.app.state.config

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT pj.id, pj.status, pj.processing_mode, u.username
            FROM processing_jobs pj JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )

    if not row:
        raise HTTPException(404, "Job not found")
    if row["status"] != "matched":
        raise HTTPException(409, f"Job must be in 'matched' status, currently '{row['status']}'")

    # Determine phases based on mode
    if row["processing_mode"] == "power_user":
        phases = ["enrich"]  # Power User: enrich only, pause before export
    else:
        phases = ["enrich", "export"]  # Speed Run: finish everything

    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE processing_jobs SET phases_requested = phases_requested || $1::text[] WHERE id = $2",
            ["enrich"], job_id,
        )
    await update_job(pool, job_id, status="running", current_phase="enrich")
    asyncio.create_task(
        _run_remaining_phases(pool, job_id, username, config, phases)
    )
    return {"status": "started", "phases": phases}


@router.post("/jobs/{job_id}/start-export")
async def start_export(
    job_id: int,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """Power User: start export phase after reviewing enrichment results.

    Only valid when job status is 'enriched'.

    Optional request body:
    {
        "lanes": ["memories", "chats", "stories"],  // subset to export
        "options": {
            "burn_overlays": true,
            "dark_mode_pngs": false,
            "exif_enabled": true,
            "xmp_enabled": false,
            "gps_window_seconds": 300
        }
    }
    """
    from snatched.db import update_job

    pool = request.app.state.db_pool
    config = request.app.state.config

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT pj.id, pj.status, u.username
            FROM processing_jobs pj JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )

    if not row:
        raise HTTPException(404, "Job not found")
    if row["status"] != "enriched":
        raise HTTPException(409, f"Job must be in 'enriched' status, currently '{row['status']}'")

    # Read optional config from request body
    try:
        body = await request.json()
    except Exception:
        body = {}

    lanes = body.get("lanes")
    options = body.get("options")

    # Update lanes if provided
    if lanes:
        valid_lanes = {"memories", "chats", "stories"}
        lanes = [l for l in lanes if l in valid_lanes]
        if lanes:
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE processing_jobs SET lanes_requested = $1 WHERE id = $2",
                    lanes, job_id,
                )

    # Only update preferences if options were explicitly provided
    if options:
        async with pool.acquire() as conn:
            user_id = await conn.fetchval(
                "SELECT id FROM users WHERE username = $1", username
            )
        gps_window = int(options.get("gps_window_seconds", 300))
        gps_window = max(30, min(1800, gps_window))
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
                bool(options.get("burn_overlays", True)),
                bool(options.get("dark_mode_pngs", False)),
                bool(options.get("exif_enabled", True)),
                bool(options.get("xmp_enabled", False)),
                gps_window,
            )

    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE processing_jobs SET phases_requested = phases_requested || $1::text[] WHERE id = $2",
            ["export"], job_id,
        )
    await update_job(pool, job_id, status="running", current_phase="export")
    asyncio.create_task(
        _run_remaining_phases(pool, job_id, username, config, ["export"])
    )
    return {"status": "started", "phases": ["export"]}


async def _run_remaining_phases(
    pool: asyncpg.Pool,
    job_id: int,
    username: str,
    config: "Config",
    phases: list[str],
) -> None:
    """Run match→enrich→export phases for a scanned job.

    This is a continuation of the ingest-only job. The SQLite DB
    already has all assets populated by ingest.
    """
    from snatched.processing import enrich, export, match
    from snatched.processing.sqlite import open_database
    from snatched.db import update_job, emit_event

    data_dir = Path(str(config.server.data_dir)) / username
    db_path = data_dir / "proc.db"
    project_dir = data_dir
    loop = asyncio.get_running_loop()

    config = config.model_copy(deep=True)

    sqlite_db = None
    try:
        # Read user preferences
        async with pool.acquire() as conn:
            prefs = await conn.fetchrow(
                """
                SELECT burn_overlays, dark_mode_pngs, exif_enabled,
                       xmp_enabled, gps_window_seconds
                FROM user_preferences up
                JOIN users u ON up.user_id = u.id
                WHERE u.username = $1
                """,
                username,
            )

        if prefs:
            from snatched.config import LaneConfig
            config.exif.enabled = prefs["exif_enabled"]
            config.xmp.enabled = prefs["xmp_enabled"]
            config.pipeline.gps_window_seconds = prefs["gps_window_seconds"]
            config.lanes["memories"] = LaneConfig(
                burn_overlays=prefs["burn_overlays"],
            )
            config.lanes["chats"] = LaneConfig(
                dark_mode=prefs["dark_mode_pngs"],
            )

        sqlite_db = open_database(str(db_path))
        progress_cb = _make_progress_cb(pool, job_id, loop)

        # Read lanes from updated job
        async with pool.acquire() as conn:
            job_row = await conn.fetchrow(
                "SELECT lanes_requested FROM processing_jobs WHERE id=$1",
                job_id,
            )
        if not job_row:
            raise RuntimeError(f"Job {job_id} not found after update")
        job_lanes = job_row["lanes_requested"] or ["memories", "chats", "stories"]

        all_stats = {"phase_durations": {}}
        phase_pct = 100 // max(len(phases), 1)
        cumulative_pct = 0

        # Phase 2: Match
        if "match" in phases:
            await emit_event(
                pool, job_id, "phase_start",
                "Running match cascade...",
                {"phase": "match", "progress_pct": cumulative_pct}
            )
            match_stats = await loop.run_in_executor(
                None, match.phase2_match, sqlite_db, progress_cb
            )
            cumulative_pct += phase_pct
            await update_job(pool, job_id, current_phase="match", progress_pct=cumulative_pct)
            await emit_event(
                pool, job_id, "progress",
                "Match complete",
                {"phase": "match", "progress_pct": cumulative_pct}
            )
            if isinstance(match_stats, dict):
                all_stats["total_matches"] = match_stats.get("total_matched", 0)
                all_stats["match_rate"] = match_stats.get("match_rate", 0)
                all_stats["true_orphans"] = match_stats.get("true_orphans", 0)
                all_stats["phase_durations"]["match"] = match_stats.get("elapsed", 0)

        # Phase 3: Enrich
        if "enrich" in phases:
            await emit_event(
                pool, job_id, "phase_start",
                "Enriching metadata...",
                {"phase": "enrich", "progress_pct": cumulative_pct}
            )
            enrich_stats = await loop.run_in_executor(
                None, enrich.phase3_enrich, sqlite_db, project_dir, config, progress_cb
            )
            cumulative_pct += phase_pct
            await update_job(pool, job_id, current_phase="enrich", progress_pct=cumulative_pct)
            await emit_event(
                pool, job_id, "progress",
                "Enrich complete",
                {"phase": "enrich", "progress_pct": cumulative_pct}
            )
            if isinstance(enrich_stats, dict):
                gps_total = enrich_stats.get("gps_metadata", 0) + enrich_stats.get("gps_location_history", 0)
                total = enrich_stats.get("total", 1)
                all_stats["gps_coverage"] = round((gps_total / total) * 100, 1) if total > 0 else 0
                all_stats["phase_durations"]["enrich"] = enrich_stats.get("elapsed", 0)

        # Phase 4: Export
        if "export" in phases:
            await emit_event(
                pool, job_id, "phase_start",
                "Exporting files...",
                {"phase": "export", "progress_pct": cumulative_pct}
            )
            export_stats = await loop.run_in_executor(
                None, export.phase4_export, sqlite_db, project_dir, config, job_lanes, progress_cb
            )
            if isinstance(export_stats, dict):
                all_stats["files_exported"] = export_stats.get("copied", 0)
                all_stats["exif_written"] = export_stats.get("exif_written", 0)
                all_stats["phase_durations"]["export"] = export_stats.get("elapsed", 0)

        # Set final status based on last phase run
        if phases[-1] == "match":
            final_status = "matched"
        elif phases[-1] == "enrich":
            final_status = "enriched"
        else:
            final_status = "completed"

        await update_job(pool, job_id, status=final_status, progress_pct=100, stats_json=all_stats)
        await emit_event(pool, job_id, final_status, f"Phase {phases[-1]} complete", {"progress_pct": 100})
        logger.info(f"Job {job_id} remaining phases completed successfully (status={final_status})")

    except Exception as e:
        logger.error(f"Job {job_id} remaining phases failed: {e}", exc_info=True)
        await update_job(pool, job_id, status="failed", error_message=str(e))
        await emit_event(pool, job_id, "error", str(e))

    finally:
        if sqlite_db:
            sqlite_db.close()


@router.get("/health")
async def health() -> dict:
    """GET /api/health — Health check (no auth required)."""
    return {"status": "ok", "version": "3.0"}
