"""HTML page routes served via Jinja2 templates.

All page routes require authentication via get_current_user dependency.
"""

import asyncio
import collections
import json
import logging
import os
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from snatched.auth import (
    get_current_user, get_optional_user, DEV_MODE, create_dev_jwt,
    create_jwt, hash_password, verify_password,
)
from snatched import tags as tags_module

logger = logging.getLogger("snatched.routes.pages")
router = APIRouter()


async def _load_tier_info(pool, username: str) -> dict:
    """Load user's tier info for template context. Returns empty dict if user not found."""
    from snatched.tiers import get_tier_limits, TIER_LIMITS, TIER_ORDER
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
        "label": limits["label"],
        "color": limits["color"],
        "limits": limits,
        "all_tiers": all_tiers,
    }


@router.get("/dev-login")
async def dev_login(request: Request, username: str = "dave"):
    """GET /dev-login — Dev mode auto-login.

    Sets a JWT cookie and redirects to landing page.
    Only works when SNATCHED_DEV_MODE=1.
    """
    if not DEV_MODE:
        raise HTTPException(404, "Not found")
    token = create_dev_jwt(username)
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie("auth_token", token, httponly=True, max_age=86400, samesite="lax")
    logger.info(f"Dev login: set JWT cookie for '{username}'")
    return response


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """GET /login — Show login form."""
    # If already authenticated, go to dashboard
    user = await get_optional_user(request)
    if user:
        return RedirectResponse(url="/dashboard", status_code=302)
    templates = request.app.state.templates
    error = request.query_params.get("error")
    return templates.TemplateResponse("login.html", {
        "request": request, "title": "Login — SNATCHED", "error": error,
    })


@router.post("/login")
async def login_submit(request: Request):
    """POST /login — Verify credentials and set JWT cookie."""
    pool = request.app.state.db_pool
    form = await request.form()
    username = (form.get("username") or "").strip().lower()
    password = form.get("password") or ""

    if not username or not password:
        return RedirectResponse(url="/login?error=Missing+username+or+password", status_code=302)

    # Look up user
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, password_hash FROM users WHERE username = $1", username
        )

    if not row or not row["password_hash"]:
        return RedirectResponse(url="/login?error=Invalid+username+or+password", status_code=302)

    if not verify_password(password, row["password_hash"]):
        return RedirectResponse(url="/login?error=Invalid+username+or+password", status_code=302)

    # Update last_seen
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET last_seen = NOW() WHERE id = $1", row["id"])

    token = create_jwt(username)
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie("auth_token", token, httponly=True, max_age=86400, samesite="lax")
    logger.info(f"Login: {username}")
    return response


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """GET /register — Show registration form."""
    user = await get_optional_user(request)
    if user:
        return RedirectResponse(url="/dashboard", status_code=302)
    templates = request.app.state.templates
    error = request.query_params.get("error")
    return templates.TemplateResponse("register.html", {
        "request": request, "title": "Register — SNATCHED", "error": error,
    })


@router.post("/register")
async def register_submit(request: Request):
    """POST /register — Create account with hashed password."""
    pool = request.app.state.db_pool
    form = await request.form()
    username = (form.get("username") or "").strip().lower()
    email = (form.get("email") or "").strip().lower() or None
    password = form.get("password") or ""
    confirm = form.get("confirm_password") or ""

    if not username or not password:
        return RedirectResponse(url="/register?error=Username+and+password+required", status_code=302)
    if len(username) < 3 or len(username) > 30:
        return RedirectResponse(url="/register?error=Username+must+be+3-30+characters", status_code=302)
    import re
    if not re.match(r'^[a-z0-9_]+$', username):
        return RedirectResponse(url="/register?error=Username+can+only+contain+letters+numbers+underscores", status_code=302)
    if len(password) < 8:
        return RedirectResponse(url="/register?error=Password+must+be+at+least+8+characters", status_code=302)
    if password != confirm:
        return RedirectResponse(url="/register?error=Passwords+do+not+match", status_code=302)

    # Check if username taken
    async with pool.acquire() as conn:
        existing = await conn.fetchval("SELECT id FROM users WHERE username = $1", username)
    if existing:
        return RedirectResponse(url="/register?error=Username+already+taken", status_code=302)

    # Create user
    pw_hash = hash_password(password)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users (username, email, password_hash, auth_provider, tier)
            VALUES ($1, $2, $3, 'local', 'free')
            """,
            username, email, pw_hash,
        )

    token = create_jwt(username)
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie("auth_token", token, httponly=True, max_age=86400, samesite="lax")
    logger.info(f"Registered new user: {username}")
    return response


@router.get("/logout")
async def logout(request: Request):
    """GET /logout — Clear auth cookie and redirect to login."""
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("auth_token")
    return response


@router.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    """GET / — Landing page.

    Shows welcome message and links to /upload and /dashboard.
    Redirects to /dashboard if user is authenticated and has at least 1 job.
    """
    templates = request.app.state.templates
    username = await get_optional_user(request)

    if username:
        # Authenticated — redirect to dashboard if they have jobs
        pool = request.app.state.db_pool
        async with pool.acquire() as conn:
            user_row = await conn.fetchrow(
                "SELECT id FROM users WHERE username = $1", username,
            )
            if user_row:
                job_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM processing_jobs WHERE user_id = $1",
                    user_row["id"],
                )
                if job_count > 0:
                    return RedirectResponse("/dashboard", status_code=302)

    return templates.TemplateResponse("landing.html", {
        "request": request,
        "username": username,
    })


@router.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request, username: str = Depends(get_current_user)):
    """GET /upload — Upload form page.

    Shows drag-drop file upload form for Snapchat export ZIPs.
    Loads user preferences to pre-populate checkboxes.
    Loads tier info for upload size limit display and enforcement (Feature #29).
    """
    from snatched.tiers import get_tier_limits

    pool = request.app.state.db_pool
    templates = request.app.state.templates

    # Load user preferences (if they exist) to pre-populate form
    prefs = {
        "burn_overlays": True, "dark_mode_pngs": False, "exif_enabled": True,
        "xmp_enabled": False, "gps_window_seconds": 300,
    }
    tier = "free"

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT burn_overlays, dark_mode_pngs, exif_enabled, xmp_enabled, gps_window_seconds
            FROM user_preferences up
            JOIN users u ON up.user_id = u.id
            WHERE u.username = $1
            """,
            username,
        )
        tier_row = await conn.fetchrow(
            "SELECT tier FROM users WHERE username = $1",
            username,
        )

    if row:
        prefs = dict(row)
    if tier_row:
        tier = tier_row["tier"]

    limits = get_tier_limits(tier)
    tier_info = {
        "tier": tier,
        "label": limits["label"],
        "max_upload_bytes": limits["max_upload_bytes"],
        "max_upload_label": limits["max_upload_label"],
        "bulk_upload": limits["bulk_upload"],
        "color": limits["color"],
    }

    return templates.TemplateResponse("upload.html", {
        "request": request,
        "username": username,
        "max_upload_bytes": limits["max_upload_bytes"],
        "prefs": prefs,
        "tier_info": tier_info,
    })


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, username: str = Depends(get_current_user)):
    """GET /dashboard — Job status page.

    Shows active jobs (polling every 2s via htmx) and job history.
    Passes tier info and slot data for Features #30 and #31.
    """
    from snatched.tiers import get_tier_limits

    pool = request.app.state.db_pool
    templates = request.app.state.templates

    async with pool.acquire() as conn:
        # Aggregate job stats
        stats = await conn.fetchrow(
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

        # Feature #30 / #31: read user tier
        tier_row = await conn.fetchrow(
            "SELECT tier FROM users WHERE username = $1",
            username,
        )
        tier = tier_row["tier"] if tier_row else "free"

        # Feature #31: count active jobs (running + pending) for this user
        active_row = await conn.fetchrow(
            """
            SELECT COUNT(*) as active_count
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE u.username = $1 AND pj.status IN ('running', 'pending')
            """,
            username,
        )
        active_jobs_count = active_row["active_count"] if active_row else 0

        # Feature #31: count queued jobs and determine queue position
        # A job is "queued" (pending) when all slots are occupied.
        # queue_position = how many OTHER users' pending jobs were submitted
        # before this user's oldest pending job (simplified: 1-based position
        # among all pending jobs system-wide for this user's oldest pending job).
        queued_jobs_count = 0
        queue_position = None
        tier_limits = get_tier_limits(tier)
        max_slots = tier_limits.get("concurrent_jobs")  # None = unlimited

        if max_slots is not None and active_jobs_count >= max_slots:
            # Count this user's pending (queued) jobs
            queued_row = await conn.fetchrow(
                """
                SELECT COUNT(*) as queued_count
                FROM processing_jobs pj
                JOIN users u ON pj.user_id = u.id
                WHERE u.username = $1 AND pj.status = 'pending'
                """,
                username,
            )
            queued_jobs_count = queued_row["queued_count"] if queued_row else 0

            # queue_position: find the earliest pending job for this user and
            # count how many pending jobs system-wide were created before it.
            if queued_jobs_count > 0:
                oldest_pending = await conn.fetchrow(
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
                if oldest_pending and oldest_pending["created_at"]:
                    position_row = await conn.fetchrow(
                        """
                        SELECT COUNT(*) as pos
                        FROM processing_jobs
                        WHERE status = 'pending'
                          AND created_at < $1
                        """,
                        oldest_pending["created_at"],
                    )
                    queue_position = (position_row["pos"] + 1) if position_row else 1

    total_storage_mb = round(stats["total_storage_bytes"] / (1024 * 1024), 1) if stats["total_storage_bytes"] else 0

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "username": username,
        "total_jobs": stats["total_jobs"],
        "completed_jobs": stats["completed_jobs"],
        "total_storage_mb": total_storage_mb,
        # Feature #30 / #31
        "tier_info": {
            "tier": tier,
            "label": tier_limits.get("label", tier.title()),
            "color": tier_limits.get("color", "var(--text-muted)"),
            "retention_days": tier_limits.get("retention_days"),
            "concurrent_jobs": max_slots,
        },
        "active_jobs_count": active_jobs_count,
        "max_slots": max_slots,
        "queued_jobs_count": queued_jobs_count,
        "queue_position": queue_position,
    })


@router.get("/job/{job_id}", response_class=HTMLResponse)
async def job_canvas(
    request: Request,
    job_id: int,
    username: str = Depends(get_current_user),
):
    """GET /job/{job_id} — The Living Canvas: single evolving job screen.

    Renders differently based on job state (pending/running/scanned/matched/
    enriched/completed/failed/cancelled). Replaces the separate progress,
    configure, and results pages.
    """
    pool = request.app.state.db_pool
    templates = request.app.state.templates

    async with pool.acquire() as conn:
        job = await conn.fetchrow(
            """
            SELECT pj.*, u.username AS owner_username
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )

    if not job:
        raise HTTPException(404, "Job not found")

    # Compute phase index for template rendering
    # 0=ingesting, 1=ingest done/matching, 2=match done/enriching,
    # 3=enrich done/exporting, 4=completed
    status = job["status"]
    phase_map = {
        'pending': 0, 'running': 0, 'scanned': 1,
        'matched': 2, 'enriched': 3, 'completed': 4,
        'failed': -1, 'cancelled': -1,
    }
    phase_idx = phase_map.get(status, 0)

    # If actively running, refine phase_idx from current_phase column
    if status == 'running' and job['current_phase']:
        cp = job['current_phase']
        if cp == 'ingest':
            phase_idx = 0
        elif cp == 'match':
            phase_idx = 1
        elif cp == 'enrich':
            phase_idx = 2
        elif cp == 'export':
            phase_idx = 3

    raw_stats = job["stats_json"] or {}
    if isinstance(raw_stats, str):
        raw_stats = json.loads(raw_stats)
    # Use defaultdict so Jinja2 dot-access returns None for missing keys
    stats = collections.defaultdict(lambda: None, raw_stats)

    tier_info = await _load_tier_info(pool, username)
    return templates.TemplateResponse("job.html", {
        "request": request,
        "username": username,
        "job": dict(job),
        "stats": stats,
        "phase_idx": phase_idx,
        "tier_info": tier_info,
    })


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
async def job_progress(
    request: Request,
    job_id: int,
    username: str = Depends(get_current_user),
):
    """GET /jobs/{job_id} — Legacy route: redirects to /job/{job_id}.

    Kept for backward compatibility (bookmarks, existing SSE streams).
    """
    return RedirectResponse(url=f"/job/{job_id}", status_code=301)


@router.get("/results/{job_id}", response_class=HTMLResponse)
async def results(
    request: Request,
    job_id: int,
    username: str = Depends(get_current_user),
):
    """GET /results/{job_id} — Results browser.

    Verifies job belongs to authenticated user. Shows summary, matches, assets.
    """
    pool = request.app.state.db_pool
    templates = request.app.state.templates

    async with pool.acquire() as conn:
        job = await conn.fetchrow(
            """
            SELECT pj.*
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )

    if not job:
        raise HTTPException(404, "Job not found")

    # Guard: redirect non-completed jobs to the Living Canvas page
    job_status = job["status"]
    if job_status in ("running", "pending", "scanned", "matched", "enriched"):
        return RedirectResponse(f"/job/{job_id}", status_code=302)
    if job_status == "cancelled":
        return RedirectResponse("/dashboard", status_code=302)

    tier_info = await _load_tier_info(pool, username)
    return templates.TemplateResponse("results.html", {
        "request": request,
        "username": username,
        "job_id": job_id,
        "job": dict(job),
        "tier_info": tier_info,
    })


@router.get("/assets/{job_id}/{asset_id}", response_class=HTMLResponse)
async def asset_detail(
    request: Request,
    job_id: int,
    asset_id: int,
    username: str = Depends(get_current_user),
):
    """GET /assets/{job_id}/{asset_id} — Individual asset tag viewer & editor.

    Verifies job ownership, loads the asset row from per-user SQLite,
    reads EXIF tags from the output file, and renders the tag editor UI.
    """
    config = request.app.state.config
    pool = request.app.state.db_pool
    templates = request.app.state.templates

    # Verify job ownership
    async with pool.acquire() as conn:
        job = await conn.fetchrow(
            """
            SELECT pj.id, pj.status, pj.upload_filename
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )

    if not job:
        raise HTTPException(404, "Job not found")

    # Load asset row from per-user SQLite
    db_path = Path(str(config.server.data_dir)) / username / "proc.db"

    loop = asyncio.get_running_loop()

    def _get_asset():
        if not db_path.exists():
            return None
        conn_sq = sqlite3.connect(str(db_path))
        conn_sq.row_factory = sqlite3.Row
        row = conn_sq.execute(
            "SELECT * FROM assets WHERE id = ?", (asset_id,)
        ).fetchone()
        conn_sq.close()
        return dict(row) if row else None

    asset = await loop.run_in_executor(None, _get_asset)

    if not asset:
        raise HTTPException(404, "Asset not found")

    # Resolve the output file path
    output_path = asset.get("output_path") or asset.get("path") or ""
    if output_path and not os.path.isabs(output_path):
        output_dir = Path(str(config.server.data_dir)) / username / "output"
        full_output_path = str(output_dir / output_path)
    else:
        full_output_path = output_path

    # Read EXIF tags — gracefully handle missing file
    grouped_tags = {}
    tag_read_error = None
    if full_output_path and os.path.isfile(full_output_path):
        try:
            flat_tags = await tags_module.read_tags(full_output_path)
            grouped_tags = tags_module.group_tags(flat_tags)
        except Exception as exc:
            logger.warning(f"Failed to read tags for asset {asset_id}: {exc}")
            tag_read_error = str(exc)
    elif not full_output_path:
        tag_read_error = "No output path recorded for this asset."
    else:
        tag_read_error = f"Output file not found: {os.path.basename(full_output_path)}"

    # Read XMP sidecar if available
    xmp_content = None
    xmp_path = asset.get("xmp_path") or ""
    if xmp_path:
        if not os.path.isabs(xmp_path):
            output_dir = Path(str(config.server.data_dir)) / username / "output"
            full_xmp_path = str(output_dir / xmp_path)
        else:
            full_xmp_path = xmp_path
        xmp_content = await tags_module.read_xmp_sidecar(full_xmp_path)

    # Fetch recent tag edits from PostgreSQL for this asset
    async with pool.acquire() as conn:
        edit_rows = await conn.fetch(
            """
            SELECT te.field_name, te.old_value, te.new_value, te.edit_type, te.created_at
            FROM tag_edits te
            JOIN users u ON te.user_id = u.id
            WHERE te.asset_id = $1 AND te.job_id = $2 AND u.username = $3
            ORDER BY te.created_at DESC
            LIMIT 50
            """,
            asset_id, job_id, username,
        )

    edit_history = [dict(r) for r in edit_rows]

    return templates.TemplateResponse("asset_detail.html", {
        "request": request,
        "username": username,
        "job_id": job_id,
        "job": dict(job),
        "asset_id": asset_id,
        "asset": asset,
        "grouped_tags": grouped_tags,
        "xmp_content": xmp_content,
        "edit_history": edit_history,
        "tag_read_error": tag_read_error,
        "full_output_path": full_output_path,
    })


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, username: str = Depends(get_current_user)):
    """GET /settings — Account & preferences page.

    Shows account info, storage usage, and editable processing preferences.
    """
    pool = request.app.state.db_pool
    templates = request.app.state.templates

    prefs = {
        "burn_overlays": True, "dark_mode_pngs": False, "exif_enabled": True,
        "xmp_enabled": False, "gps_window_seconds": 300,
    }

    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            """
            SELECT u.id, u.username, u.display_name, u.created_at, u.storage_quota_bytes
            FROM users u
            WHERE u.username = $1
            """,
            username,
        )
        if not user:
            raise HTTPException(404, "User not found")

        storage_used = await conn.fetchval(
            """
            SELECT COALESCE(SUM(upload_size_bytes), 0)
            FROM processing_jobs
            WHERE user_id = $1 AND status NOT IN ('failed', 'cancelled')
            """,
            user["id"],
        )

        job_count = await conn.fetchval(
            "SELECT COUNT(*) FROM processing_jobs WHERE user_id = $1",
            user["id"],
        )

        row = await conn.fetchrow(
            """
            SELECT burn_overlays, dark_mode_pngs, exif_enabled, xmp_enabled, gps_window_seconds
            FROM user_preferences up
            JOIN users u ON up.user_id = u.id
            WHERE u.username = $1
            """,
            username,
        )
    if row:
        prefs = dict(row)

    # Compute human-readable storage values
    storage_used_gb = round((storage_used or 0) / (1024 ** 3), 2)
    quota_bytes = user["storage_quota_bytes"] or 0
    quota_gb = round(quota_bytes / (1024 ** 3), 1) if quota_bytes else None
    storage_pct = min(100, round((storage_used or 0) / quota_bytes * 100)) if quota_bytes else 0

    # Load tier info for nav badge + Plan & Tier section
    tier_info = await _load_tier_info(pool, username)
    all_tiers = tier_info.pop("all_tiers", [])

    return templates.TemplateResponse("settings.html", {
        "request": request,
        "username": username,
        "user": dict(user),
        "prefs": prefs,
        "storage_used_gb": storage_used_gb,
        "quota_gb": quota_gb,
        "storage_pct": storage_pct,
        "job_count": job_count,
        "tier_info": tier_info,
        "all_tiers": all_tiers,
    })


@router.get("/friends", response_class=HTMLResponse)
async def friends_page(request: Request, username: str = Depends(get_current_user)):
    """GET /friends — Friend Name Mapping & Aliases page.

    Queries PostgreSQL for user's friend_aliases and the most recent
    completed job's SQLite for the friends export table and chat message
    senders. Merges and passes to template. All datetimes serialized to strings.
    """
    config = request.app.state.config
    pool = request.app.state.db_pool
    templates = request.app.state.templates

    async with pool.acquire() as conn:
        user_row = await conn.fetchrow(
            "SELECT id FROM users WHERE username = $1", username
        )
        if not user_row:
            raise HTTPException(404, "User not found")
        user_id = user_row["id"]

        # Most recent completed job
        latest_job = await conn.fetchrow(
            """
            SELECT pj.id, pj.upload_filename, pj.created_at
            FROM processing_jobs pj
            WHERE pj.user_id = $1 AND pj.status = 'completed'
            ORDER BY pj.created_at DESC
            LIMIT 1
            """,
            user_id,
        )

        # All completed jobs (for the job selector dropdown)
        job_rows = await conn.fetch(
            """
            SELECT pj.id, pj.upload_filename, pj.created_at
            FROM processing_jobs pj
            WHERE pj.user_id = $1 AND pj.status = 'completed'
            ORDER BY pj.created_at DESC
            LIMIT 50
            """,
            user_id,
        )

        # All aliases for this user
        alias_rows = await conn.fetch(
            """
            SELECT id, snap_username, display_name, merged_with, created_at, updated_at
            FROM friend_aliases
            WHERE user_id = $1
            ORDER BY snap_username
            """,
            user_id,
        )

    # Build alias map: snap_username -> dict
    alias_map: dict[str, dict] = {}
    for ar in alias_rows:
        d = dict(ar)
        if d.get("created_at"):
            d["created_at"] = d["created_at"].isoformat()
        if d.get("updated_at"):
            d["updated_at"] = d["updated_at"].isoformat()
        alias_map[d["snap_username"]] = d

    # Prep jobs list for template
    jobs = []
    for r in job_rows:
        j = dict(r)
        if j.get("created_at"):
            j["created_at"] = j["created_at"].isoformat()
        jobs.append(j)

    latest_job_id = latest_job["id"] if latest_job else None

    # Load friends + message counts from per-user SQLite
    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    loop = asyncio.get_running_loop()

    def _load_friends():
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

    friends, msg_counts, sender_set = await loop.run_in_executor(None, _load_friends)

    # Merge into unified friend list
    seen_usernames: set[str] = set()
    friend_list: list[dict] = []

    for f in friends:
        snap_username = f["username"]
        seen_usernames.add(snap_username)
        a = alias_map.get(snap_username, {})
        friend_list.append({
            "snap_username": snap_username,
            "original_name": f["display_name"],
            "alias": a.get("display_name"),
            "alias_id": a.get("id"),
            "merged_with": a.get("merged_with"),
            "message_count": msg_counts.get(snap_username, 0),
            "category": f.get("category"),
            "is_unknown": False,
        })

    # Aliases for usernames not in friends table
    for snap_username, a in alias_map.items():
        if snap_username not in seen_usernames:
            seen_usernames.add(snap_username)
            friend_list.append({
                "snap_username": snap_username,
                "original_name": None,
                "alias": a["display_name"],
                "alias_id": a["id"],
                "merged_with": a["merged_with"],
                "message_count": msg_counts.get(snap_username, 0),
                "category": None,
                "is_unknown": False,
            })

    # Unknown senders (chat_messages only, not in friends table)
    unknown_senders: list[dict] = []
    for sender in sorted(sender_set):
        if sender and sender not in seen_usernames:
            seen_usernames.add(sender)
            a = alias_map.get(sender, {})
            unknown_senders.append({
                "snap_username": sender,
                "original_name": None,
                "alias": a.get("display_name"),
                "alias_id": a.get("id"),
                "merged_with": a.get("merged_with"),
                "message_count": msg_counts.get(sender, 0),
                "category": "unknown_sender",
                "is_unknown": True,
            })

    # Stats
    total_friends = len(friend_list)
    with_aliases = sum(1 for f in friend_list if f["alias"])
    unknown_names = sum(1 for f in friend_list if not f["original_name"] and not f["alias"])
    merged_contacts = sum(1 for f in (friend_list + unknown_senders) if f["merged_with"])

    return templates.TemplateResponse("friends.html", {
        "request": request,
        "username": username,
        "friend_list": friend_list,
        "unknown_senders": unknown_senders,
        "jobs": jobs,
        "latest_job_id": latest_job_id,
        "total_friends": total_friends,
        "with_aliases": with_aliases,
        "unknown_names": unknown_names,
        "merged_contacts": merged_contacts,
        "title": "Friend Names — SNATCHED",
    })


@router.get("/presets", response_class=HTMLResponse)
async def presets_page(request: Request, username: str = Depends(get_current_user)):
    """GET /presets — Tag Template Presets management page.

    Shows built-in (read-only) and user-owned presets.
    Loads all jobs so the user can pick a target job for apply-to-job.
    """
    pool = request.app.state.db_pool
    templates = request.app.state.templates

    async with pool.acquire() as conn:
        # Fetch presets: builtins first, then user-owned by name
        preset_rows = await conn.fetch(
            """
            SELECT id, user_id, name, description, tags_json, is_builtin, created_at, updated_at
            FROM tag_presets
            WHERE is_builtin = true
               OR user_id = (SELECT id FROM users WHERE username = $1)
            ORDER BY is_builtin DESC, name ASC
            """,
            username,
        )

        # Fetch user's completed jobs for "apply to job" dropdown
        job_rows = await conn.fetch(
            """
            SELECT pj.id, pj.upload_filename, pj.status, pj.created_at
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE u.username = $1 AND pj.status = 'completed'
            ORDER BY pj.created_at DESC
            LIMIT 50
            """,
            username,
        )

    import json as _json

    presets = []
    for row in preset_rows:
        d = dict(row)
        tags = d.get("tags_json") or {}
        if isinstance(tags, str):
            tags = _json.loads(tags)
        d["tags_json"] = tags
        d["tag_count"] = len(tags)
        # Convert datetimes to strings for JSON serialization in template
        if d.get("created_at"):
            d["created_at"] = d["created_at"].isoformat()
        if d.get("updated_at"):
            d["updated_at"] = d["updated_at"].isoformat()
        presets.append(d)

    builtin_presets = [p for p in presets if p["is_builtin"]]
    custom_presets = [p for p in presets if not p["is_builtin"]]
    jobs = []
    for r in job_rows:
        j = dict(r)
        # Convert datetimes to strings for JSON serialization in template
        if j.get("created_at"):
            j["created_at"] = j["created_at"].isoformat()
        jobs.append(j)

    return templates.TemplateResponse("presets.html", {
        "request": request,
        "username": username,
        "builtin_presets": builtin_presets,
        "custom_presets": custom_presets,
        "jobs": jobs,
        "title": "Tag Presets — SNATCHED",
    })


@router.get("/download/{job_id}", response_class=HTMLResponse)
async def download_page(
    request: Request,
    job_id: int,
    username: str = Depends(get_current_user),
):
    """GET /download/{job_id} — Download manager page.

    Shows file tree for /data/{username}/output/ plus output stats.
    """
    config = request.app.state.config
    pool = request.app.state.db_pool
    templates = request.app.state.templates

    async with pool.acquire() as conn:
        job = await conn.fetchrow(
            """
            SELECT pj.*
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )

    if not job:
        raise HTTPException(404, "Job not found")

    # Count files and sum sizes in the output directory
    output_dir = Path(str(config.server.data_dir)) / username / "output"
    file_count = 0
    total_size = 0
    if output_dir.exists():
        for dirpath, dirnames, filenames in os.walk(str(output_dir)):
            for f in filenames:
                file_count += 1
                total_size += os.path.getsize(os.path.join(dirpath, f))

    total_size_mb = round(total_size / (1024 * 1024), 1)

    tier_info = await _load_tier_info(pool, username)
    return templates.TemplateResponse("download.html", {
        "request": request,
        "username": username,
        "job_id": job_id,
        "job": dict(job),
        "file_count": file_count,
        "total_size_mb": total_size_mb,
        "tier_info": tier_info,
    })


@router.get("/gps/{job_id}", response_class=HTMLResponse)
async def gps_correction(
    request: Request,
    job_id: int,
    username: str = Depends(get_current_user),
):
    """GET /gps/{job_id} — GPS Correction & Override map tool.

    Shows an embedded Leaflet map with:
    - Asset pins (draggable, yellow) for assets with GPS coordinates
    - GPS breadcrumb trail (green polyline) from locations table
    - Saved locations (blue circles) from PostgreSQL saved_locations table
    - Snap Map places (orange markers) from places table

    All data is serialised to JSON and injected into the template.
    """
    import json as _json

    config = request.app.state.config
    pool = request.app.state.db_pool
    templates = request.app.state.templates

    # Verify job ownership and get user_id
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT pj.id, pj.status, pj.upload_filename, u.id as user_id
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )

    if not row:
        raise HTTPException(404, "Job not found")

    user_id = row["user_id"]

    # Load per-user SQLite data
    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    loop = asyncio.get_running_loop()

    def _load_sqlite_data():
        if not db_path.exists():
            return [], [], []

        conn_sq = sqlite3.connect(str(db_path))
        conn_sq.row_factory = sqlite3.Row

        # Assets with GPS from matches table joined to assets
        try:
            asset_rows = conn_sq.execute(
                """
                SELECT
                    a.id, a.filename, a.output_path, a.asset_type,
                    m.matched_lat, m.matched_lon, m.gps_source,
                    m.match_confidence
                FROM assets a
                JOIN matches m ON m.asset_id = a.id
                WHERE m.matched_lat IS NOT NULL
                  AND m.matched_lon IS NOT NULL
                ORDER BY a.id
                """
            ).fetchall()
        except Exception:
            asset_rows = []

        # GPS breadcrumb trail
        try:
            location_rows = conn_sq.execute(
                """
                SELECT id, timestamp, timestamp_unix, lat, lon, accuracy_m
                FROM locations
                WHERE lat IS NOT NULL AND lon IS NOT NULL
                ORDER BY timestamp_unix ASC
                """
            ).fetchall()
        except Exception:
            location_rows = []

        # Snap Map places
        try:
            place_rows = conn_sq.execute(
                """
                SELECT name, lat, lon, address, visit_count
                FROM places
                WHERE lat IS NOT NULL AND lon IS NOT NULL
                ORDER BY visit_count DESC
                """
            ).fetchall()
        except Exception:
            place_rows = []

        conn_sq.close()

        assets = [dict(r) for r in asset_rows]
        locations = [dict(r) for r in location_rows]
        places = [dict(r) for r in place_rows]
        return assets, locations, places

    assets, locations, places = await loop.run_in_executor(None, _load_sqlite_data)

    # Query saved locations from PostgreSQL
    async with pool.acquire() as conn:
        saved_rows = await conn.fetch(
            """
            SELECT id, name, lat, lon, radius_m, created_at
            FROM saved_locations
            WHERE user_id = $1
            ORDER BY created_at DESC
            """,
            user_id,
        )

    saved_locations = []
    for r in saved_rows:
        d = dict(r)
        if d.get("created_at"):
            d["created_at"] = d["created_at"].isoformat()
        saved_locations.append(d)

    # Serialise to JSON for template injection
    # (Datetimes already converted to strings; all floats are native)
    assets_json = _json.dumps(assets)
    locations_json = _json.dumps(locations)
    places_json = _json.dumps(places)
    saved_locations_json = _json.dumps(saved_locations)

    return templates.TemplateResponse("gps_correction.html", {
        "request": request,
        "username": username,
        "job_id": job_id,
        "job": dict(row),
        "assets_json": assets_json,
        "locations_json": locations_json,
        "places_json": places_json,
        "saved_locations_json": saved_locations_json,
        "asset_count": len(assets),
        "location_count": len(locations),
        "place_count": len(places),
        "title": f"GPS Correction — Job #{job_id} — SNATCHED",
    })


@router.get("/redact/{job_id}", response_class=HTMLResponse)
async def redaction_page(
    request: Request,
    job_id: int,
    username: str = Depends(get_current_user),
):
    """GET /redact/{job_id} — Privacy Redaction tool.

    Lets users strip sensitive metadata (GPS, creator, dates, custom fields)
    from their processed output files. Non-destructive to the pipeline database —
    only the output files are modified. All writes are logged to tag_edits.
    """
    import json as _json

    config = request.app.state.config
    pool = request.app.state.db_pool
    templates = request.app.state.templates

    # Verify job ownership and get user_id
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT pj.id, pj.status, pj.upload_filename, u.id as user_id
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )

    if not row:
        raise HTTPException(404, "Job not found")

    user_id = row["user_id"]

    # Query user's saved redaction profiles + recent redaction log
    async with pool.acquire() as conn:
        profile_rows = await conn.fetch(
            """
            SELECT id, name, description, rules_json, created_at, updated_at
            FROM redaction_profiles
            WHERE user_id = $1
            ORDER BY created_at DESC
            """,
            user_id,
        )

        log_rows = await conn.fetch(
            """
            SELECT te.id, te.asset_id, te.field_name, te.old_value, te.edit_type,
                   te.file_path, te.created_at
            FROM tag_edits te
            WHERE te.user_id = $1 AND te.job_id = $2 AND te.new_value IS NULL
            ORDER BY te.created_at DESC
            LIMIT 100
            """,
            user_id, job_id,
        )

    # Convert datetimes to strings for template JSON serialization
    profiles = []
    for r in profile_rows:
        d = dict(r)
        rules = d.get("rules_json") or []
        if isinstance(rules, str):
            rules = _json.loads(rules)
        d["rules_json"] = rules
        d["rule_count"] = len(rules)
        if d.get("created_at"):
            d["created_at"] = d["created_at"].isoformat()
        if d.get("updated_at"):
            d["updated_at"] = d["updated_at"].isoformat()
        profiles.append(d)

    redaction_log = []
    for r in log_rows:
        d = dict(r)
        if d.get("created_at"):
            d["created_at"] = d["created_at"].isoformat()
        fp = d.get("file_path") or ""
        d["filename_display"] = os.path.basename(fp) if fp else f"asset #{d['asset_id']}"
        redaction_log.append(d)

    # Query assets + match GPS/creator info from per-user SQLite
    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    loop = asyncio.get_running_loop()

    def _load_assets():
        if not db_path.exists():
            return []
        conn_sq = sqlite3.connect(str(db_path))
        conn_sq.row_factory = sqlite3.Row
        try:
            rows = conn_sq.execute(
                """
                SELECT
                    a.id, a.filename, a.output_path, a.asset_type,
                    m.matched_lat, m.matched_lon, m.creator_str
                FROM assets a
                LEFT JOIN matches m ON m.asset_id = a.id AND m.is_best = 1
                ORDER BY a.id
                """
            ).fetchall()
        except Exception:
            rows = []
        conn_sq.close()
        return [dict(r) for r in rows]

    assets = await loop.run_in_executor(None, _load_assets)

    return templates.TemplateResponse("redaction.html", {
        "request": request,
        "username": username,
        "job_id": job_id,
        "job": dict(row),
        "profiles": profiles,
        "profiles_json": _json.dumps(profiles),
        "assets": assets,
        "assets_json": _json.dumps(assets),
        "redaction_log": redaction_log,
        "title": f"Privacy Redaction — Job #{job_id} — SNATCHED",
    })


@router.get("/schemas", response_class=HTMLResponse)
async def schemas_page(request: Request, username: str = Depends(get_current_user)):
    """GET /schemas — Custom Metadata Schemas management page.

    Lists user's custom XMP namespace schemas (namespace_prefix, namespace_uri, fields).
    Provides create/edit/delete via client-side JS calling the /api/schemas endpoints.
    """
    import json as _json

    pool = request.app.state.db_pool
    templates = request.app.state.templates

    async with pool.acquire() as conn:
        schema_rows = await conn.fetch(
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

    schemas = []
    for row in schema_rows:
        d = dict(row)
        fields = d.get("fields_json") or []
        if isinstance(fields, str):
            fields = _json.loads(fields)
        d["fields_json"] = fields
        d["field_count"] = len(fields)
        # Convert datetimes to strings for JSON serialization in template
        if d.get("created_at"):
            d["created_at"] = d["created_at"].isoformat()
        if d.get("updated_at"):
            d["updated_at"] = d["updated_at"].isoformat()
        schemas.append(d)

    return templates.TemplateResponse("schemas.html", {
        "request": request,
        "username": username,
        "schemas": schemas,
        "title": "Custom Metadata Schemas — SNATCHED",
    })


@router.get("/match-config/{job_id}", response_class=HTMLResponse)
async def match_config(
    request: Request,
    job_id: int,
    username: str = Depends(get_current_user),
):
    """GET /match-config/{job_id} — Match Confidence Threshold & Strategy Configuration.

    Features:
    - Confidence histogram (pure CSS, snap-yellow bars)
    - Threshold slider with live keep/filter counts
    - Strategy table with enable/disable, weight overrides, reorder buttons
    - Save as default (user_preferences) or preset (pipeline_configs)
    - Saved presets list with Load/Delete
    """
    import json as _json

    config = request.app.state.config
    pool = request.app.state.db_pool
    templates = request.app.state.templates

    # Verify job ownership and get user_id
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT pj.id, pj.status, pj.upload_filename, u.id as user_id
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )

    if not row:
        raise HTTPException(404, "Job not found")

    user_id = row["user_id"]

    # Load user preferences (match_confidence_min + strategy_weights_json)
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
        current_weights = _json.loads(current_weights)

    # Load pipeline_configs (presets)
    async with pool.acquire() as conn:
        preset_rows = await conn.fetch(
            """
            SELECT id, name, description, config_json, is_default, created_at, updated_at
            FROM pipeline_configs
            WHERE user_id = $1
            ORDER BY created_at DESC
            """,
            user_id,
        )

    presets = []
    for pr in preset_rows:
        d = dict(pr)
        if d.get("created_at"):
            d["created_at"] = d["created_at"].isoformat()
        if d.get("updated_at"):
            d["updated_at"] = d["updated_at"].isoformat()
        cfg = d.get("config_json") or {}
        if isinstance(cfg, str):
            cfg = _json.loads(cfg)
        d["config_json"] = cfg
        presets.append(d)

    # Load match stats from per-user SQLite
    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    loop = asyncio.get_running_loop()

    def _load_match_stats():
        if not db_path.exists():
            return {}, []

        conn_sq = sqlite3.connect(str(db_path))
        conn_sq.row_factory = sqlite3.Row

        try:
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

    strategy_counts, confidences = await loop.run_in_executor(None, _load_match_stats)

    # Build histogram: 10 buckets
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

    # Default strategy definitions (canonical order + default confidence)
    default_strategies = [
        {"name": "exact_media_id",   "default_confidence": 1.0, "description": "chat file_id = message Media ID"},
        {"name": "memory_uuid",      "default_confidence": 1.0, "description": "memory filename UUID = memories.mid"},
        {"name": "story_id",         "default_confidence": 0.9, "description": "ordered pairing (0.5 if counts differ)"},
        {"name": "memory_uuid_zip",  "default_confidence": 0.9, "description": "UUID from overlay~zip filename"},
        {"name": "timestamp_type",   "default_confidence": 0.8, "description": "unique date + media type on both sides"},
        {"name": "date_type_count",  "default_confidence": 0.7, "description": "count-aligned ordered pairing"},
        {"name": "date_only",        "default_confidence": 0.3, "description": "any asset with a date_str (fallback)"},
    ]

    # Merge per-job match counts into strategy definitions
    strategies = []
    for s in default_strategies:
        name = s["name"]
        job_stats = strategy_counts.get(name, {"count": 0, "avg_confidence": s["default_confidence"], "best_count": 0})
        weight_override = current_weights.get(name)
        strategies.append({
            "name": name,
            "default_confidence": s["default_confidence"],
            "description": s["description"],
            "match_count": job_stats["count"],
            "best_count": job_stats["best_count"],
            "avg_confidence": job_stats["avg_confidence"],
            "enabled": current_weights.get(f"{name}_enabled", True) if current_weights else True,
            "weight": weight_override if weight_override is not None else s["default_confidence"],
        })

    total_matches = len(confidences)

    return templates.TemplateResponse("match_config.html", {
        "request": request,
        "username": username,
        "job_id": job_id,
        "job": dict(row),
        "histogram_json": _json.dumps(histogram),
        "strategies_json": _json.dumps(strategies),
        "presets_json": _json.dumps(presets),
        "current_threshold": current_threshold,
        "total_matches": total_matches,
        "title": f"Match Config — Job #{job_id} — SNATCHED",
    })


@router.get("/dry-run/{job_id}", response_class=HTMLResponse)
async def dry_run_page(
    request: Request,
    job_id: int,
    username: str = Depends(get_current_user),
):
    """GET /dry-run/{job_id} — Dry Run / Preview Mode results page.

    Shows what would be exported if the export phase were run.
    Only valid for jobs where export was excluded from phases_requested.
    Loads match stats, strategy breakdown, and builds a mock export tree
    from the per-user SQLite matches table.
    """
    import json as _json

    config = request.app.state.config
    pool = request.app.state.db_pool
    templates = request.app.state.templates

    # Verify job ownership
    async with pool.acquire() as conn:
        job = await conn.fetchrow(
            """
            SELECT pj.*
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )

    if not job:
        raise HTTPException(404, "Job not found")

    # Serialize job for template (convert datetimes)
    job_dict = dict(job)
    for dt_field in ("created_at", "started_at", "completed_at"):
        if job_dict.get(dt_field):
            job_dict[dt_field] = job_dict[dt_field].isoformat()

    # Load match stats and export tree from per-user SQLite
    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    loop = asyncio.get_running_loop()

    def _load_dry_run_data():
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
                SELECT match_strategy as strategy,
                       COUNT(*) as count,
                       AVG(match_confidence) as avg_confidence
                FROM matches
                WHERE is_best = 1
                GROUP BY match_strategy
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
                SELECT CAST(match_confidence * 10 AS INTEGER) as bucket,
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

        # Build export tree grouped by output_subdir
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

        match_rate = round(matched_assets / total_assets * 100, 1) if total_assets else 0.0
        gps_coverage = round(gps_count / total_assets * 100, 1) if total_assets else 0.0
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

    dry_data = await loop.run_in_executor(None, _load_dry_run_data)

    # Find other dry-run jobs for comparison panel
    async with pool.acquire() as conn:
        other_dry_runs_rows = await conn.fetch(
            """
            SELECT pj.id, pj.created_at, pj.stats_json
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE u.username = $1
              AND pj.id != $2
              AND 'export' != ALL(COALESCE(pj.phases_requested, ARRAY[]::TEXT[]))
              AND pj.status = 'completed'
            ORDER BY pj.created_at DESC
            LIMIT 5
            """,
            username, job_id,
        )

    other_dry_runs = []
    for r in other_dry_runs_rows:
        d = dict(r)
        if d.get("created_at"):
            d["created_at"] = d["created_at"].isoformat()
        stats = d.get("stats_json") or {}
        d["matched"] = stats.get("total_matches") or stats.get("matched_assets") or 0
        other_dry_runs.append(d)

    # Max histogram count for CSS bar scaling
    max_hist_count = max((h["count"] for h in dry_data["histogram"]), default=1)

    return templates.TemplateResponse("dry_run.html", {
        "request": request,
        "username": username,
        "job_id": job_id,
        "job": job_dict,
        "dry_data": dry_data,
        "dry_data_json": _json.dumps(dry_data),
        "other_dry_runs": other_dry_runs,
        "max_hist_count": max_hist_count,
        "title": f"Dry Run Preview — Job #{job_id} — SNATCHED",
    })


@router.get("/timestamps/{job_id}", response_class=HTMLResponse)
async def timestamp_correction(
    request: Request,
    job_id: int,
    username: str = Depends(get_current_user),
):
    """GET /timestamps/{job_id} — Timestamp correction tool with visual timeline.

    Loads all assets for the job grouped by date (YYYY-MM-DD) for display.
    Assets are joined with their best match to get matched_date.
    """
    import json as _json

    config = request.app.state.config
    pool = request.app.state.db_pool
    templates = request.app.state.templates

    # Verify job ownership
    async with pool.acquire() as conn:
        job = await conn.fetchrow(
            """
            SELECT pj.id, pj.status, pj.upload_filename
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )

    if not job:
        raise HTTPException(404, "Job not found")

    # Load assets joined with best matches from per-user SQLite
    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    loop = asyncio.get_running_loop()

    def _load_assets():
        if not db_path.exists():
            return []
        conn_sq = sqlite3.connect(str(db_path))
        conn_sq.row_factory = sqlite3.Row
        try:
            rows = conn_sq.execute(
                """
                SELECT
                    a.id,
                    a.filename,
                    a.output_path,
                    a.asset_type,
                    a.is_video,
                    a.date_str,
                    m.matched_date
                FROM assets a
                LEFT JOIN matches m ON m.asset_id = a.id AND m.is_best = 1
                ORDER BY COALESCE(m.matched_date, a.date_str) ASC, a.id ASC
                """
            ).fetchall()
        except Exception as exc:
            logger.warning(f"timestamp_correction SQLite query failed: {exc}")
            rows = []
        conn_sq.close()
        return [dict(r) for r in rows]

    assets = await loop.run_in_executor(None, _load_assets)

    # Group assets by date (YYYY-MM-DD) using matched_date, falling back to date_str
    by_date = collections.OrderedDict()
    no_date_assets = []
    date_range_min = None
    date_range_max = None

    for asset in assets:
        # Prefer matched_date; fall back to date_str (first 10 chars = YYYY-MM-DD)
        raw_date = asset.get("matched_date") or asset.get("date_str") or ""
        date_key = raw_date[:10] if raw_date else None

        # Ensure matched_date is always a string (safe for JSON)
        asset["matched_date"] = asset.get("matched_date") or None

        if date_key and len(date_key) == 10:
            if date_key not in by_date:
                by_date[date_key] = []
            by_date[date_key].append(asset)

            if date_range_min is None or date_key < date_range_min:
                date_range_min = date_key
            if date_range_max is None or date_key > date_range_max:
                date_range_max = date_key
        else:
            no_date_assets.append(asset)

    # Serialize grouped data for template JS
    timeline_data = []
    for date_key in sorted(by_date.keys()):
        day_assets = by_date[date_key]
        day_summary = {
            "date": date_key,
            "count": len(day_assets),
            "by_type": {
                "memory": sum(1 for a in day_assets if a.get("asset_type") == "memory"),
                "chat": sum(1 for a in day_assets if a.get("asset_type") == "chat"),
                "story": sum(1 for a in day_assets if a.get("asset_type") == "story"),
            },
            "asset_ids": [a["id"] for a in day_assets],
        }
        timeline_data.append(day_summary)

    # Flatten all assets for the table (dated + undated)
    all_assets = []
    for date_key in sorted(by_date.keys()):
        all_assets.extend(by_date[date_key])
    all_assets.extend(no_date_assets)

    return templates.TemplateResponse("timestamp_correction.html", {
        "request": request,
        "username": username,
        "job_id": job_id,
        "job": dict(job),
        "timeline_data_json": _json.dumps(timeline_data),
        "assets_json": _json.dumps(all_assets),
        "total_assets": len(assets),
        "dated_assets": len(assets) - len(no_date_assets),
        "missing_date_assets": len(no_date_assets),
        "date_range_min": date_range_min or "",
        "date_range_max": date_range_max or "",
        "title": f"Timestamp Correction — Job #{job_id} — SNATCHED",
    })


@router.get("/export-config", response_class=HTMLResponse)
async def export_config_page(request: Request, username: str = Depends(get_current_user)):
    """GET /export-config — Global Export Configuration page.

    Feature #19: Custom Output Folder Structure
    Feature #20: Export Format Controls

    Loads user_preferences (all columns including folder_pattern and export_settings_json)
    and passes them to the template. All datetimes converted to ISO strings.
    """
    import json as _json

    pool = request.app.state.db_pool
    templates = request.app.state.templates

    default_export_settings = {
        "jpeg_quality": 95,
        "png_compression": 6,
        "video_handling": "copy",
        "generate_thumbnails": False,
        "thumbnail_size": 256,
    }

    prefs = {
        "folder_pattern": "{YYYY}/{MM}",
        "export_settings_json": default_export_settings,
        "burn_overlays": True,
        "dark_mode_pngs": False,
        "exif_enabled": True,
        "xmp_enabled": False,
        "gps_window_seconds": 300,
    }

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

    if row:
        d = dict(row)
        if d.get("folder_pattern") is not None:
            prefs["folder_pattern"] = d["folder_pattern"]
        if d.get("burn_overlays") is not None:
            prefs["burn_overlays"] = d["burn_overlays"]
        if d.get("dark_mode_pngs") is not None:
            prefs["dark_mode_pngs"] = d["dark_mode_pngs"]
        if d.get("exif_enabled") is not None:
            prefs["exif_enabled"] = d["exif_enabled"]
        if d.get("xmp_enabled") is not None:
            prefs["xmp_enabled"] = d["xmp_enabled"]
        if d.get("gps_window_seconds") is not None:
            prefs["gps_window_seconds"] = d["gps_window_seconds"]

        raw_export = d.get("export_settings_json")
        if raw_export is not None:
            if isinstance(raw_export, str):
                try:
                    raw_export = _json.loads(raw_export)
                except Exception:
                    raw_export = {}
            if isinstance(raw_export, dict):
                prefs["export_settings_json"] = {**default_export_settings, **raw_export}

    export_settings = prefs["export_settings_json"]
    export_settings_json_str = _json.dumps(export_settings)

    return templates.TemplateResponse("export_config.html", {
        "request": request,
        "username": username,
        "prefs": prefs,
        "export_settings": export_settings,
        "export_settings_json": export_settings_json_str,
        "title": "Export Config — SNATCHED",
    })


# ============================================================
# P4 BROWSE & VISUALIZE — Insertion slots (agents replace these)
# ============================================================

# --- P4-SLOT-22: Memory Browser Page ---

@router.get("/browse/{job_id}", response_class=HTMLResponse)
async def memory_browser(
    request: Request,
    job_id: int,
    username: str = Depends(get_current_user),
):
    """GET /browse/{job_id} — Gallery-style memory browser.

    Verifies job ownership via PostgreSQL, loads initial stats from per-user
    SQLite, and renders the memory_browser.html template.  The gallery cards
    themselves are loaded lazily via htmx from GET /api/jobs/{job_id}/gallery/html.
    """
    config = request.app.state.config
    pool = request.app.state.db_pool
    templates = request.app.state.templates

    # Verify job ownership
    async with pool.acquire() as conn:
        job = await conn.fetchrow(
            """
            SELECT pj.id, pj.status, pj.upload_filename
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )

    if not job:
        raise HTTPException(404, "Job not found")

    # Load initial stats from per-user SQLite
    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    loop = asyncio.get_running_loop()

    def _load_stats():
        if not db_path.exists():
            return {
                "total_assets": 0,
                "total_matched": 0,
                "type_options": [],
            }
        conn_sq = sqlite3.connect(str(db_path))
        conn_sq.row_factory = sqlite3.Row
        try:
            total_assets = conn_sq.execute(
                "SELECT COUNT(*) FROM assets"
            ).fetchone()[0]

            total_matched = conn_sq.execute(
                "SELECT COUNT(DISTINCT asset_id) FROM matches WHERE is_best = 1"
            ).fetchone()[0]

            type_rows = conn_sq.execute(
                "SELECT DISTINCT asset_type FROM assets WHERE asset_type IS NOT NULL ORDER BY asset_type"
            ).fetchall()
            type_options = [r["asset_type"] for r in type_rows if r["asset_type"]]
        except Exception:
            total_assets = 0
            total_matched = 0
            type_options = []
        finally:
            conn_sq.close()

        return {
            "total_assets": total_assets,
            "total_matched": total_matched,
            "type_options": type_options,
        }

    stats = await loop.run_in_executor(None, _load_stats)

    return templates.TemplateResponse("memory_browser.html", {
        "request": request,
        "username": username,
        "job_id": job_id,
        "job": dict(job),
        "total_assets": stats["total_assets"],
        "total_matched": stats["total_matched"],
        "type_options": stats["type_options"],
        "filters": {},
        "title": f"Memory Browser — Job #{job_id} — SNATCHED",
    })

# --- P4-SLOT-23: Conversation Browser Page ---

@router.get("/browse/chats/{job_id}", response_class=HTMLResponse)
async def conversation_browser(
    request: Request,
    job_id: int,
    username: str = Depends(get_current_user),
):
    """GET /browse/chats/{job_id} — Conversation browser page.

    Verifies job ownership via PostgreSQL, then loads the conversation list
    from the per-user SQLite (GROUP BY conversation_id), joins friends for
    display names, and renders the two-panel chat browser UI.
    """
    config = request.app.state.config
    pool = request.app.state.db_pool
    templates = request.app.state.templates

    # Verify job ownership
    async with pool.acquire() as conn:
        job = await conn.fetchrow(
            """
            SELECT pj.id, pj.status, pj.upload_filename
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )

    if not job:
        raise HTTPException(404, "Job not found")

    # Load conversation list from per-user SQLite
    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    loop = asyncio.get_running_loop()

    def _load_conversations():
        if not db_path.exists():
            return []
        conn_sq = sqlite3.connect(str(db_path))
        conn_sq.row_factory = sqlite3.Row
        try:
            rows = conn_sq.execute(
                """
                SELECT
                    cm.conversation_id,
                    cm.conversation_title,
                    COUNT(cm.id) AS message_count,
                    MIN(cm.created_dt) AS first_date,
                    MAX(cm.created_dt) AS last_date,
                    MAX(CASE WHEN cm.media_ids IS NOT NULL AND cm.media_ids != '' THEN 1 ELSE 0 END) AS has_media,
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

    conversations = await loop.run_in_executor(None, _load_conversations)

    # Normalise: prefer display_name, fall back to conversation_title, then conversation_id
    for c in conversations:
        if not c.get("display_name"):
            c["display_name"] = c.get("conversation_title") or c.get("conversation_id") or ""

    return templates.TemplateResponse("conversation_browser.html", {
        "request": request,
        "username": username,
        "job_id": job_id,
        "conversations": conversations,
        "title": "Conversations — SNATCHED",
    })

# --- P4-SLOT-24: Timeline Visualization ---

@router.get("/timeline/{job_id}", response_class=HTMLResponse)
async def timeline_page(request: Request, job_id: int, username: str = Depends(get_current_user)):
    """GET /timeline/{job_id} — Interactive timeline visualization.

    Verifies job ownership via PostgreSQL, loads aggregated year-level
    timeline data and lane counts from per-user SQLite, and renders the
    timeline.html template.  Drill-down (month/day) is handled client-side
    via fetch() calls to GET /api/jobs/{job_id}/timeline-data.
    """
    config = request.app.state.config
    pool = request.app.state.db_pool
    templates = request.app.state.templates

    # Verify job ownership
    async with pool.acquire() as conn:
        job = await conn.fetchrow(
            """
            SELECT pj.id, pj.status, pj.upload_filename
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )

    if not job:
        raise HTTPException(404, "Job not found")

    # Load aggregated timeline stats from per-user SQLite
    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    loop = asyncio.get_running_loop()

    def _load_timeline_summary():
        if not db_path.exists():
            return 0, {}, None, None

        conn_sq = sqlite3.connect(str(db_path))
        conn_sq.row_factory = sqlite3.Row
        try:
            # Total matched items
            total = conn_sq.execute(
                "SELECT COUNT(*) FROM matches WHERE is_best = 1"
            ).fetchone()[0]

            # Lane counts
            lane_rows = conn_sq.execute(
                """
                SELECT lane, COUNT(*) AS cnt
                FROM matches
                WHERE is_best = 1 AND lane IS NOT NULL
                GROUP BY lane
                """
            ).fetchall()
            lane_counts = {r["lane"]: r["cnt"] for r in lane_rows}

            # Date range
            date_row = conn_sq.execute(
                """
                SELECT MIN(matched_date) AS min_date, MAX(matched_date) AS max_date
                FROM matches
                WHERE is_best = 1 AND matched_date IS NOT NULL
                """
            ).fetchone()
            min_date = date_row["min_date"] if date_row else None
            max_date = date_row["max_date"] if date_row else None
        except Exception:
            total, lane_counts, min_date, max_date = 0, {}, None, None
        finally:
            conn_sq.close()
        return total, lane_counts, min_date, max_date

    total_items, lane_counts, min_date, max_date = await loop.run_in_executor(None, _load_timeline_summary)

    # Build human-readable date range string
    if min_date and max_date:
        date_range = f"{str(min_date)[:10]} — {str(max_date)[:10]}"
    elif min_date:
        date_range = str(min_date)[:10]
    else:
        date_range = "No dates"

    return templates.TemplateResponse("timeline.html", {
        "request": request,
        "username": username,
        "job_id": job_id,
        "total_items": total_items,
        "lane_counts": lane_counts,
        "date_range": date_range,
        "title": f"Timeline — Job #{job_id} — SNATCHED",
    })


# --- P4-SLOT-25: Map Visualization ---

@router.get("/map/{job_id}", response_class=HTMLResponse)
async def map_page(request: Request, job_id: int, username: str = Depends(get_current_user)):
    """GET /map/{job_id} — Interactive GPS map visualization.

    Verifies job ownership via PostgreSQL, loads summary stats (total GPS
    items, coverage %) from per-user SQLite, and renders the map.html
    template.  Actual marker data is loaded client-side via fetch() calls
    to GET /api/jobs/{job_id}/map-data.
    """
    config = request.app.state.config
    pool = request.app.state.db_pool
    templates = request.app.state.templates

    # Verify job ownership
    async with pool.acquire() as conn:
        job = await conn.fetchrow(
            """
            SELECT pj.id, pj.status, pj.upload_filename
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )

    if not job:
        raise HTTPException(404, "Job not found")

    # Load GPS summary stats from per-user SQLite
    db_path = Path(str(config.server.data_dir)) / username / "proc.db"
    loop = asyncio.get_running_loop()

    def _load_map_summary():
        if not db_path.exists():
            return 0, 0

        conn_sq = sqlite3.connect(str(db_path))
        conn_sq.row_factory = sqlite3.Row
        try:
            total_matches = conn_sq.execute(
                "SELECT COUNT(*) FROM matches WHERE is_best = 1"
            ).fetchone()[0]

            gps_count = conn_sq.execute(
                """
                SELECT COUNT(*) FROM matches
                WHERE is_best = 1
                  AND matched_lat IS NOT NULL
                  AND matched_lon IS NOT NULL
                """
            ).fetchone()[0]
        except Exception:
            total_matches, gps_count = 0, 0
        finally:
            conn_sq.close()

        coverage = round((gps_count / total_matches * 100), 1) if total_matches > 0 else 0.0
        return gps_count, coverage

    gps_total, gps_coverage = await loop.run_in_executor(None, _load_map_summary)

    return templates.TemplateResponse("map.html", {
        "request": request,
        "username": username,
        "job_id": job_id,
        "gps_total": gps_total,
        "gps_coverage": gps_coverage,
        "title": f"GPS Map — Job #{job_id} — SNATCHED",
    })

# --- P4-SLOT-26: Duplicate Detection ---

@router.get("/duplicates/{job_id}", response_class=HTMLResponse)
async def duplicates_page(
    request: Request,
    job_id: int,
    username: str = Depends(get_current_user),
):
    """GET /duplicates/{job_id} — Duplicate detection page.

    Verifies job ownership via PostgreSQL, loads initial duplicate summary
    stats from per-user SQLite (count assets with sha256, distinct hashes,
    groups with count > 1), and renders duplicates.html.
    """
    config = request.app.state.config
    pool = request.app.state.db_pool
    templates = request.app.state.templates

    # Verify job ownership
    async with pool.acquire() as conn:
        job = await conn.fetchrow(
            """
            SELECT pj.id, pj.status, pj.upload_filename
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

    def _load_dup_stats():
        if not db_path.exists():
            return {
                "total_assets": 0,
                "unique_hashes": 0,
                "duplicate_groups": 0,
                "duplicate_files": 0,
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

            # Groups = sha256 values that appear more than once
            dup_group_row = conn_sq.execute(
                """
                SELECT COUNT(*) FROM (
                    SELECT sha256
                    FROM assets
                    WHERE sha256 IS NOT NULL
                    GROUP BY sha256
                    HAVING COUNT(*) > 1
                ) g
                """
            ).fetchone()
            duplicate_groups = dup_group_row[0] if dup_group_row else 0

            # Duplicate files = total assets belonging to duplicated hashes
            dup_file_row = conn_sq.execute(
                """
                SELECT COALESCE(SUM(cnt), 0) FROM (
                    SELECT COUNT(*) as cnt
                    FROM assets
                    WHERE sha256 IS NOT NULL
                    GROUP BY sha256
                    HAVING COUNT(*) > 1
                ) g
                """
            ).fetchone()
            duplicate_files = dup_file_row[0] if dup_file_row else 0
        except Exception:
            total_assets = 0
            unique_hashes = 0
            duplicate_groups = 0
            duplicate_files = 0
        finally:
            conn_sq.close()

        return {
            "total_assets": total_assets,
            "unique_hashes": unique_hashes,
            "duplicate_groups": duplicate_groups,
            "duplicate_files": duplicate_files,
        }

    stats = await loop.run_in_executor(None, _load_dup_stats)

    return templates.TemplateResponse("duplicates.html", {
        "request": request,
        "username": username,
        "job_id": job_id,
        "job": dict(job),
        "stats": stats,
        "title": f"Duplicate Detection — Job #{job_id} — SNATCHED",
    })


# --- P4-SLOT-27: Album Auto-Creation ---

@router.get("/albums/{job_id}", response_class=HTMLResponse)
async def albums_page(
    request: Request,
    job_id: int,
    username: str = Depends(get_current_user),
):
    """GET /albums/{job_id} — Album management page.

    Verifies job ownership via PostgreSQL, loads existing albums for this
    user + job, converts all datetimes to isoformat, and renders albums.html.
    """
    pool = request.app.state.db_pool
    templates = request.app.state.templates

    # Verify job ownership and get user_id
    async with pool.acquire() as conn:
        job = await conn.fetchrow(
            """
            SELECT pj.id, pj.status, pj.upload_filename, u.id as user_id
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )

    if not job:
        raise HTTPException(404, "Job not found")

    user_id = job["user_id"]

    # Load albums from PostgreSQL for this user + job
    async with pool.acquire() as conn:
        album_rows = await conn.fetch(
            """
            SELECT id, name, description, auto_generated,
                   center_lat, center_lon, location_name,
                   start_date, end_date, item_count,
                   created_at, updated_at
            FROM albums
            WHERE user_id = $1 AND job_id = $2
            ORDER BY start_date ASC NULLS LAST, created_at ASC
            """,
            user_id, job_id,
        )

    # Convert asyncpg records to plain dicts, serialising any datetime values
    albums = []
    for row in album_rows:
        d = dict(row)
        for k, v in d.items():
            if hasattr(v, "isoformat"):
                d[k] = v.isoformat()
        albums.append(d)

    return templates.TemplateResponse("albums.html", {
        "request": request,
        "username": username,
        "job_id": job_id,
        "job": dict(job),
        "albums": albums,
        "title": f"Auto Albums — Job #{job_id} — SNATCHED",
    })


# ============================================================
# P5 ACCOUNT & QUOTA MANAGEMENT — Insertion slots
# ============================================================

# --- P5-SLOT-28: Storage Quota Dashboard ---

@router.get("/quota", response_class=HTMLResponse)
async def quota_page(request: Request, username: str = Depends(get_current_user)):
    """GET /quota — Storage & Quota dashboard.

    Loads user tier from PostgreSQL, scans the user's data directory on disk
    for storage usage (grouped by top-level subdirectory / lane), loads per-job
    retention info, and enriches with SQLite asset breakdown when proc.db exists.
    All blocking I/O (os.walk, sqlite3) is offloaded via run_in_executor.
    """
    from snatched.tiers import get_tier_limits, TIER_LIMITS, TIER_ORDER

    config = request.app.state.config
    pool = request.app.state.db_pool
    templates = request.app.state.templates
    loop = asyncio.get_running_loop()

    # ── 1. Load user record (tier) from PostgreSQL ──────────────────────────
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
    tier_label = limits["label"]
    tier_color = limits["color"]

    # ── 2. Load jobs with retention info from PostgreSQL ────────────────────
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

    import datetime as _dt
    now_utc = _dt.datetime.now(_dt.timezone.utc)

    retention_jobs = []
    for row in job_rows:
        d = dict(row)
        # Store raw asyncpg value for days_remaining calc before isoformat conversion
        exp = row["retention_expires_at"]
        # Convert datetimes to isoformat strings
        for k, v in d.items():
            if hasattr(v, "isoformat"):
                d[k] = v.isoformat()
        # Compute days remaining
        if exp is None:
            d["days_remaining"] = None
        else:
            delta = exp - now_utc
            d["days_remaining"] = max(0, delta.days)
        retention_jobs.append(d)

    # ── 3. Scan disk for storage usage ──────────────────────────────────────
    data_dir = Path(str(config.server.data_dir)) / username

    LANE_COLORS = {
        "memories": "var(--snap-yellow)",
        "chats": "var(--success)",
        "stories": "#3b9eed",
        "other": "var(--text-muted)",
    }

    def _scan_disk():
        """Walk user data dir, sum bytes by top-level subdirectory (lane)."""
        if not data_dir.exists():
            return 0, {}, {}

        lane_bytes_d: dict[str, int] = collections.defaultdict(int)
        lane_count_d: dict[str, int] = collections.defaultdict(int)
        total = 0

        for root, _dirs, files in os.walk(str(data_dir)):
            root_path = Path(root)
            try:
                rel = root_path.relative_to(data_dir)
                parts = rel.parts
                subdir = parts[0].lower() if parts else "other"
            except ValueError:
                subdir = "other"

            for fname in files:
                try:
                    fsize = (root_path / fname).stat().st_size
                except OSError:
                    continue
                total += fsize
                lane_bytes_d[subdir] += fsize
                lane_count_d[subdir] += 1

        return total, dict(lane_bytes_d), dict(lane_count_d)

    total_bytes, lane_bytes, lane_count = await loop.run_in_executor(None, _scan_disk)

    # ── 4. Optionally enrich lane breakdown from SQLite asset table ──────────
    db_path = Path(str(config.server.data_dir)) / username / "proc.db"

    def _load_sqlite_lanes():
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

    sqlite_lanes = await loop.run_in_executor(None, _load_sqlite_lanes)

    # ── 5. Helper: human-readable file size ─────────────────────────────────
    def _fmt_size(b: int) -> str:
        if b >= 1024 ** 3:
            return f"{b / (1024 ** 3):.1f} GB"
        if b >= 1024 ** 2:
            return f"{b / (1024 ** 2):.1f} MB"
        if b >= 1024:
            return f"{b / 1024:.1f} KB"
        return f"{b} B"

    # ── 6. Build lane_breakdown list ─────────────────────────────────────────
    known_lanes = ["memories", "chats", "stories"]
    all_lane_keys = list(dict.fromkeys(
        known_lanes + [k for k in lane_bytes if k not in known_lanes]
    ))

    lane_breakdown = []
    for lane_key in all_lane_keys:
        disk_sz = lane_bytes.get(lane_key, 0)
        disk_cnt = lane_count.get(lane_key, 0)
        sq = sqlite_lanes.get(lane_key, {})
        size_bytes = disk_sz or sq.get("size_bytes", 0) or 0
        file_count = disk_cnt or sq.get("file_count", 0) or 0
        if size_bytes == 0 and file_count == 0:
            continue
        pct = round((size_bytes / total_bytes * 100), 1) if total_bytes > 0 else 0.0
        color = LANE_COLORS.get(lane_key.lower(), LANE_COLORS["other"])
        lane_breakdown.append({
            "name": lane_key.capitalize(),
            "key": lane_key,
            "file_count": file_count,
            "size_bytes": size_bytes,
            "size_human": _fmt_size(size_bytes),
            "pct": pct,
            "color": color,
        })

    # Fix rounding so percentages sum exactly to 100
    if lane_breakdown:
        total_pct = sum(lane["pct"] for lane in lane_breakdown)
        diff = round(100.0 - total_pct, 1)
        if diff != 0:
            lane_breakdown[-1]["pct"] = round(lane_breakdown[-1]["pct"] + diff, 1)

    # ── 7. Quota usage percentage ─────────────────────────────────────────────
    quota_bytes = (limits["storage_gb"] * 1024 ** 3) if limits.get("storage_gb") else None
    if quota_bytes and quota_bytes > 0:
        usage_pct = round(total_bytes / quota_bytes * 100, 1)
    else:
        usage_pct = 0.0

    warn_approaching = 80.0 <= usage_pct < 100.0
    warn_over_quota = usage_pct >= 100.0

    # ── 8. All-tiers list for comparison table ───────────────────────────────
    all_tiers = []
    for t_key in TIER_ORDER:
        t = dict(TIER_LIMITS[t_key])
        t["key"] = t_key
        all_tiers.append(t)

    return templates.TemplateResponse("quota.html", {
        "request": request,
        "username": username,
        "title": "Storage & Quota — SNATCHED",
        # Tier
        "tier": tier,
        "tier_label": tier_label,
        "tier_color": tier_color,
        "limits": limits,
        # Storage
        "total_bytes": total_bytes,
        "total_size_human": _fmt_size(total_bytes),
        "usage_pct": usage_pct,
        "warn_approaching": warn_approaching,
        "warn_over_quota": warn_over_quota,
        "lane_breakdown": lane_breakdown,
        # Jobs / Retention
        "retention_jobs": retention_jobs,
        # Comparison table
        "all_tiers": all_tiers,
    })


# Feature #29 (Upload Size Limit Tiers): tier badge, size enforcement, and bulk indicator logic is integrated into the existing upload_page route above.

# --- Feature #30: Retention Period Control ---
# Retention countdown UI is rendered inside snatched/templates/_job_cards.html.
# The dashboard route passes tier_info so the EXTEND button is tier-gated.
# API endpoints for extend/query are in api.py (POST /api/jobs/{id}/extend-retention,
# GET /api/jobs/{id}/retention).

# --- Feature #31: Concurrent Job Slots ---
# Slot indicator UI is rendered in snatched/templates/dashboard.html.
# The dashboard route passes tier_info, active_jobs_count, max_slots,
# queued_jobs_count, and queue_position to the template.
# Live slot data is also available via GET /api/slots in api.py.

# Feature #32 (Bulk Upload Support): bulk upload UI is in upload.html; job_group_id is generated in JS and
# passed in fileManifest options. The route below handles viewing a job group page.

@router.get("/job-group/{group_id}", response_class=HTMLResponse)
async def job_group_page(
    request: Request,
    group_id: str,
    username: str = Depends(get_current_user),
):
    """GET /job-group/{group_id} — Job group viewer.

    Shows all jobs linked under a single bulk upload group ID (Feature #32).
    """
    pool = request.app.state.db_pool
    templates = request.app.state.templates

    async with pool.acquire() as conn:
        jobs = await conn.fetch(
            """
            SELECT pj.id, pj.upload_filename, pj.status, pj.created_at, pj.job_group_id
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.job_group_id = $1 AND u.username = $2
            ORDER BY pj.created_at ASC
            """,
            group_id,
            username,
        )

    if not jobs:
        raise HTTPException(404, "Job group not found")

    jobs_list = [
        {
            "id": r["id"],
            "filename": r["upload_filename"],
            "status": r["status"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "job_group_id": r["job_group_id"],
        }
        for r in jobs
    ]

    return templates.TemplateResponse("job_group.html", {
        "request": request,
        "username": username,
        "group_id": group_id,
        "jobs": jobs_list,
        "title": f"Job Group {group_id[:8]}... — SNATCHED",
    })


@router.get("/api-keys", response_class=HTMLResponse)
async def api_keys_page(request: Request, username: str = Depends(get_current_user)):
    """GET /api-keys — API Access Key management page.

    Loads the user's tier info and all api_keys rows. Tier gate: free users
    see a locked message. Pro+ users see the full CRUD UI (Feature #33).
    """
    from snatched.tiers import get_tier_limits

    pool = request.app.state.db_pool
    templates = request.app.state.templates

    tier_info = await _load_tier_info(pool, username)
    tier = tier_info["tier"]
    limits = get_tier_limits(tier)

    # Determine tier limits for API keys
    _API_KEY_LIMITS = {
        "free":      {"max_keys": 0,    "rate_limit_rpm": 0},
        "pro":       {"max_keys": 3,    "rate_limit_rpm": 60},
    }
    key_limits = _API_KEY_LIMITS.get(tier, _API_KEY_LIMITS["free"])
    max_keys = key_limits["max_keys"]
    rate_limit_rpm = key_limits["rate_limit_rpm"]

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

    keys = [
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

    return templates.TemplateResponse("api_keys.html", {
        "request": request,
        "username": username,
        "title": "API Access Keys — SNATCHED",
        "tier_info": tier_info,
        "keys": keys,
        "max_keys": max_keys,
        "rate_limit_rpm": rate_limit_rpm,
    })


# --- Feature #34: Webhook Notifications ---

@router.get("/webhooks", response_class=HTMLResponse)
async def webhooks_page(request: Request, username: str = Depends(get_current_user)):
    """GET /webhooks — Webhook notification configuration page.

    Shows all webhooks registered by the user, tier gate, and CRUD controls.
    """
    pool = request.app.state.db_pool
    templates = request.app.state.templates

    tier_info = await _load_tier_info(pool, username)

    # Determine max webhooks allowed for this tier (no max_webhooks in TIER_LIMITS,
    # so we map tier name directly per spec)
    tier_key = tier_info.get("tier", "free")
    _max_webhooks_map = {
        "free": 0,
        "pro": 3,
    }
    max_webhooks = _max_webhooks_map.get(tier_key, 0)

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

    webhooks_list = [
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

    return templates.TemplateResponse("webhooks.html", {
        "request": request,
        "username": username,
        "tier_info": tier_info,
        "max_webhooks": max_webhooks,
        "webhooks": webhooks_list,
        "title": "Webhooks — SNATCHED",
    })


# --- P6-SLOT-SCHEDULES: Scheduled exports page ---

_SCHEDULE_LIMITS = {
    "free":      0,
    "pro":       2,
}


@router.get("/schedules", response_class=HTMLResponse)
async def schedules_page(request: Request, username: str = Depends(get_current_user)):
    """GET /schedules — Scheduled / recurring exports management page.

    Loads the user's tier info and all schedules rows. Tier gate: free users
    see a locked message. Pro+ users see the full CRUD UI (Feature #36).
    """
    pool = request.app.state.db_pool
    templates = request.app.state.templates

    tier_info = await _load_tier_info(pool, username)
    tier = tier_info["tier"]
    max_schedules = _SCHEDULE_LIMITS.get(tier, 0)

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

    schedules = [
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

    return templates.TemplateResponse("schedules.html", {
        "request": request,
        "username": username,
        "title": "Scheduled Exports — SNATCHED",
        "tier_info": tier_info,
        "schedules": schedules,
        "max_schedules": max_schedules,
    })


# --- STORY-5: Configure page for scanned jobs ---
@router.get("/configure/{job_id}", response_class=HTMLResponse)
async def configure_page(
    request: Request,
    job_id: int,
    username: str = Depends(get_current_user),
):
    """GET /configure/{job_id} — Configuration page after ingest scan.

    Shows scan results (counts by lane) and allows user to select lanes
    and configure processing options before starting remaining phases.
    Only available if job status is 'scanned'.
    """
    pool = request.app.state.db_pool
    templates = request.app.state.templates

    # Verify job ownership and status
    async with pool.acquire() as conn:
        job_row = await conn.fetchrow(
            """
            SELECT pj.id, pj.status, pj.upload_filename, pj.created_at, pj.upload_size_bytes,
                   pj.stats_json
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )

    if not job_row:
        raise HTTPException(404, "Job not found")

    # Living Canvas handles all states now — redirect non-scanned/completed to /job/{id}
    if job_row["status"] in ("running", "pending", "matched", "enriched"):
        return RedirectResponse(f"/job/{job_id}", status_code=302)
    if job_row["status"] not in ("scanned", "completed"):
        raise HTTPException(
            400,
            f"Configuration only available for scanned jobs (current: {job_row['status']})"
        )

    # Fetch scan results (asset counts)
    # This would normally come from /api/jobs/{job_id}/scan-results
    # but for template rendering, we call the API directly or query SQLite
    config = request.app.state.config
    data_dir = Path(str(config.server.data_dir)) / username
    db_path = data_dir / "proc.db"

    scan_results = {
        "memories": 0,
        "memories_size": 0,
        "stories": 0,
        "stories_size": 0,
        "chats": 0,
        "chats_size": 0,
        "total_assets": 0,
        "total_size_bytes": job_row["upload_size_bytes"] or 0,
    }

    if db_path.exists():
        try:
            db = sqlite3.connect(str(db_path))
            db.row_factory = sqlite3.Row

            # Count and size by type
            memory_main = db.execute(
                "SELECT COUNT(*), COALESCE(SUM(file_size), 0) FROM assets WHERE asset_type = 'memory_main'"
            ).fetchone()
            memory_overlay = db.execute(
                "SELECT COUNT(*), COALESCE(SUM(file_size), 0) FROM assets WHERE asset_type = 'memory_overlay'"
            ).fetchone()
            stories_row = db.execute(
                "SELECT COUNT(*), COALESCE(SUM(file_size), 0) FROM assets WHERE asset_type = 'story'"
            ).fetchone()
            chats_row = db.execute(
                "SELECT COUNT(*), COALESCE(SUM(file_size), 0) FROM assets WHERE asset_type LIKE 'chat%'"
            ).fetchone()
            total = db.execute(
                "SELECT COUNT(*) FROM assets"
            ).fetchone()[0]

            db.close()

            scan_results = {
                "memories": memory_main[0] + memory_overlay[0],
                "memories_size": memory_main[1] + memory_overlay[1],
                "stories": stories_row[0],
                "stories_size": stories_row[1],
                "chats": chats_row[0],
                "chats_size": chats_row[1],
                "total_assets": total,
                "total_size_bytes": job_row["upload_size_bytes"] or 0,
            }
        except sqlite3.Error:
            pass  # Use defaults if DB query fails

    # Load user preferences as defaults
    prefs = {
        "burn_overlays": True,
        "dark_mode_pngs": False,
        "exif_enabled": True,
        "xmp_enabled": False,
        "gps_window_seconds": 300,
    }

    async with pool.acquire() as conn:
        pref_row = await conn.fetchrow(
            """
            SELECT burn_overlays, dark_mode_pngs, exif_enabled, xmp_enabled, gps_window_seconds
            FROM user_preferences up
            JOIN users u ON up.user_id = u.id
            WHERE u.username = $1
            """,
            username,
        )

    if pref_row:
        prefs = dict(pref_row)

    tier_info = await _load_tier_info(pool, username)
    return templates.TemplateResponse("configure.html", {
        "request": request,
        "username": username,
        "job_id": job_id,
        "upload_filename": job_row["upload_filename"],
        "created_at": job_row["created_at"].isoformat() if job_row["created_at"] else None,
        "scan_results": scan_results,
        "prefs": prefs,
        "tier_info": tier_info,
    })
