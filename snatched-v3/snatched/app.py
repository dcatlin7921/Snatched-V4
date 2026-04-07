"""FastAPI application factory with lifespan management.

Creates the Snatched v3 web application: middleware, templates,
static files, route registration, and database pool lifecycle.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Configure root logger so all snatched.* loggers emit to stderr
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger("snatched")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager: startup and shutdown.

    Startup: connect PostgreSQL pool, run init_schema, create /data dir.
    Shutdown: close PostgreSQL pool.
    """
    logger.info("Starting Snatched v3...")

    from snatched.db import get_pool, init_schema, seed_builtin_presets, seed_tier_plans
    from snatched.tiers import warm_cache

    pool = await get_pool(
        app.state.config.database.postgres_url,
        min_size=app.state.config.database.pool_min_size,
        max_size=app.state.config.database.pool_max_size,
    )
    app.state.db_pool = pool

    await init_schema(pool)
    await seed_builtin_presets(pool)
    await seed_tier_plans(pool)
    await warm_cache(pool)

    data_dir = str(app.state.config.server.data_dir)
    os.makedirs(data_dir, mode=0o750, exist_ok=True)

    # Smart recovery for orphaned jobs — attempt to resume where possible
    # rather than blindly marking everything as failed.
    # Advisory lock (id=2) ensures only one uvicorn worker runs recovery.
    async with pool.acquire() as conn:
        await conn.execute("SELECT pg_advisory_lock(2)")
        try:
            orphaned = await conn.fetch(
                """
                SELECT pj.id, pj.status, pj.processing_mode,
                       u.username,
                       us.session_token, us.options_json
                FROM processing_jobs pj
                JOIN users u ON pj.user_id = u.id
                LEFT JOIN upload_sessions us ON us.job_id = pj.id
                WHERE pj.status IN ('running', 'pending', 'queued')
                """
            )

            recovered = 0
            failed_count = 0
            relaunch_jobs = []  # (job_id, username, pipeline_dir) — launched after lock

            for job in orphaned:
                job_id = job["id"]
                username = job["username"]
                job_dir = Path(data_dir) / username / "jobs" / str(job_id)
                proc_db = job_dir / "proc.db"

                if job["status"] in ("running", "queued") and proc_db.exists():
                    # Ingest completed — proc.db on disk. Reset to 'scanned'
                    # so user can re-trigger remaining phases via configure page.
                    # Re-set 72h TTL so recovered jobs eventually expire if unclaimed.
                    await conn.execute(
                        """
                        UPDATE processing_jobs
                        SET status = 'scanned', error_message = NULL,
                            retention_expires_at = NOW() + INTERVAL '72 hours'
                        WHERE id = $1
                        """,
                        job_id,
                    )
                    recovered += 1
                    logger.info(
                        f"Recovered job {job_id}: {job['status']} → scanned (proc.db exists)"
                    )

                elif job["status"] == "pending" and job["session_token"]:
                    # Pending job — check if staging data still on disk
                    session_token = job["session_token"]
                    opts = job["options_json"] or {}
                    if isinstance(opts, str):
                        import json as _json
                        opts = _json.loads(opts)
                    upload_type = opts.get("upload_type", "zip") if isinstance(opts, dict) else "zip"

                    # Check ramdisk first, then disk
                    ramdisk_staging = Path("/ramdisk") / "staging" / username / session_token
                    disk_staging = Path(data_dir) / username / "staging" / session_token
                    staging_path = ramdisk_staging if ramdisk_staging.exists() else disk_staging
                    if upload_type == "folder":
                        pipeline_path = staging_path.parent / "extracted" / session_token
                    else:
                        pipeline_path = staging_path

                    if pipeline_path.exists():
                        # Staging data intact — clear error and re-launch
                        await conn.execute(
                            "UPDATE processing_jobs SET error_message = NULL WHERE id = $1",
                            job_id,
                        )
                        relaunch_jobs.append((job_id, username, str(pipeline_path)))
                        recovered += 1
                        logger.info(
                            f"Recovered job {job_id}: pending, staging exists — will re-launch"
                        )
                    else:
                        await conn.execute(
                            """
                            UPDATE processing_jobs
                            SET status = 'failed',
                                error_message = 'Server restarted; staging data not found',
                                completed_at = NOW()
                            WHERE id = $1
                            """,
                            job_id,
                        )
                        failed_count += 1

                else:
                    # No recovery possible — mark failed
                    await conn.execute(
                        """
                        UPDATE processing_jobs
                        SET status = 'failed',
                            error_message = 'Server restarted before job completed',
                            completed_at = NOW()
                        WHERE id = $1
                        """,
                        job_id,
                    )
                    failed_count += 1

            if orphaned:
                logger.warning(
                    f"Orphan recovery: {recovered} recovered, {failed_count} failed "
                    f"(of {len(orphaned)} orphaned)"
                )

        finally:
            await conn.execute("SELECT pg_advisory_unlock(2)")

    # Recover orphaned exports (building/pending when server restarted)
    async with pool.acquire() as conn:
        orphaned_exports = await conn.fetch(
            "UPDATE exports SET status = 'failed', "
            "error_message = 'Server restarted during export. Please retry.', "
            "completed_at = NOW() "
            "WHERE status IN ('building', 'pending') "
            "RETURNING id, job_id"
        )
        if orphaned_exports:
            ids = [r["id"] for r in orphaned_exports]
            logger.warning(f"Marked {len(ids)} orphaned exports as failed: {ids}")

    # Re-launch recovered pending jobs (outside the advisory lock)
    if relaunch_jobs:
        from snatched.jobs import run_job
        config = app.state.config
        for job_id, username, pipeline_dir in relaunch_jobs:
            task = asyncio.create_task(
                run_job(pool, job_id, username, config, staging_dir=pipeline_dir)
            )
            task.add_done_callback(
                lambda t, jid=job_id: t.exception() and logger.error(
                    "Recovered job %d crashed: %s", jid, t.exception(),
                    exc_info=t.exception(),
                )
            )
            logger.info(f"Re-launched job {job_id} for user {username}")

    logger.info(f"Snatched ready on port {app.state.config.server.port}")

    # Periodic cleanup of expired upload sessions
    async def _session_cleanup_loop():
        from snatched.routes.uploads import cleanup_expired_sessions
        while True:
            await asyncio.sleep(3600)  # Every hour
            try:
                cleaned = await cleanup_expired_sessions(pool, app.state.config)
                if cleaned:
                    logger.info(f"Cleaned up {cleaned} expired upload sessions")
            except Exception as e:
                logger.warning(f"Session cleanup error: {e}")

    cleanup_task = asyncio.create_task(_session_cleanup_loop())

    # Scan TTL cleanup: expire unconfigured scanned jobs after 72h
    async def _scan_ttl_cleanup_loop():
        import shutil as _shutil
        while True:
            await asyncio.sleep(3600)  # Every hour
            try:
                async with pool.acquire() as conn:
                    expired = await conn.fetch(
                        """
                        UPDATE processing_jobs
                        SET status = 'cancelled', error_message = 'Scan expired (72h TTL)'
                        WHERE status = 'scanned'
                          AND retention_expires_at IS NOT NULL
                          AND retention_expires_at < NOW()
                          AND payment_status NOT IN ('pending', 'paid')
                        RETURNING id, user_id
                        """
                    )
                for row in expired:
                    job_id = row["id"]
                    # Look up username for disk cleanup
                    user_row = await pool.fetchval(
                        "SELECT username FROM users WHERE id = $1", row["user_id"]
                    )
                    if user_row:
                        job_dir = Path(str(app.state.config.server.data_dir)) / user_row / "jobs" / str(job_id)
                        if job_dir.exists():
                            _shutil.rmtree(str(job_dir), ignore_errors=True)
                    logger.info(f"Expired scanned job {job_id} (72h TTL)")
                if expired:
                    logger.info(f"Scan TTL cleanup: expired {len(expired)} unconfigured jobs")
            except Exception as e:
                logger.warning(f"Scan TTL cleanup error: {e}")

    scan_ttl_task = asyncio.create_task(_scan_ttl_cleanup_loop())

    # Stale pending payment cleanup: Stripe sessions expire after 24h.
    # Jobs stuck in payment_status='pending' for >24h will never get a webhook.
    # Reset to 'unpaid' so TTL cleanup can handle them normally.
    async def _stale_payment_cleanup_loop():
        while True:
            await asyncio.sleep(3600)  # Every hour
            try:
                async with pool.acquire() as conn:
                    stale = await conn.execute(
                        """
                        UPDATE processing_jobs
                        SET payment_status = 'unpaid'
                        WHERE status = 'scanned'
                          AND payment_status = 'pending'
                          AND retention_expires_at IS NOT NULL
                          AND retention_expires_at < NOW() + INTERVAL '48 hours'
                        """
                    )
                    # retention_expires_at is set to NOW()+72h at scan time.
                    # If it's less than 48h from now, the scan is >24h old — Stripe expired.
                    count = int(stale.split()[-1]) if stale and stale.split()[-1].isdigit() else 0
                    if count > 0:
                        logger.info(f"Stale payment cleanup: reset {count} abandoned checkouts to unpaid")
            except Exception as e:
                logger.warning(f"Stale payment cleanup error: {e}")

    stale_payment_task = asyncio.create_task(_stale_payment_cleanup_loop())

    # Retention cleanup: delete expired job data from disk.
    # Users see "30 days" on the website, actual deletion runs at retention_expires_at + 3 days
    # (3-day grace period for customer service issues).
    RETENTION_GRACE_DAYS = 3

    async def _retention_cleanup_loop():
        import shutil
        from datetime import datetime, timedelta, timezone
        while True:
            await asyncio.sleep(6 * 3600)  # Every 6 hours
            try:
                now = datetime.now(timezone.utc)
                async with pool.acquire() as conn:
                    expired = await conn.fetch(
                        """
                        SELECT pj.id, pj.status, pj.retention_expires_at,
                               u.username
                        FROM processing_jobs pj
                        JOIN users u ON pj.user_id = u.id
                        WHERE pj.retention_expires_at IS NOT NULL
                          AND pj.retention_expires_at + $1 < $2
                          AND pj.status IN ('completed', 'failed', 'cancelled',
                                            'scanned', 'matched', 'enriched')
                        """,
                        timedelta(days=RETENTION_GRACE_DAYS), now,
                    )

                if not expired:
                    continue

                deleted_count = 0
                for row in expired:
                    job_id = row["id"]
                    username = row["username"]
                    job_dir = config.server.data_dir / username / "jobs" / str(job_id)

                    # Delete files from disk
                    if job_dir.exists():
                        try:
                            shutil.rmtree(job_dir)
                            logger.info(
                                "Retention cleanup: deleted job dir %s (expired %s, grace +%dd)",
                                job_dir, row["retention_expires_at"].date(), RETENTION_GRACE_DAYS,
                            )
                        except Exception as e:
                            logger.warning("Retention cleanup: failed to delete %s: %s", job_dir, e)
                            continue

                    # Clean up exports and DB rows
                    async with pool.acquire() as conn:
                        await conn.execute("DELETE FROM exports WHERE job_id=$1", job_id)
                        await conn.execute("DELETE FROM job_events WHERE job_id=$1", job_id)
                        await conn.execute(
                            "UPDATE upload_sessions SET job_id=NULL WHERE job_id=$1", job_id
                        )
                        await conn.execute("DELETE FROM processing_jobs WHERE id=$1", job_id)

                    deleted_count += 1

                if deleted_count:
                    logger.warning(
                        "Retention cleanup: purged %d expired jobs (%d candidates)",
                        deleted_count, len(expired),
                    )

                # Orphan cleanup: stale upload sessions (no job, older than 24h)
                async with pool.acquire() as conn:
                    orphan_sessions = await conn.fetch(
                        """DELETE FROM upload_files WHERE session_id IN (
                            SELECT id FROM upload_sessions
                            WHERE job_id IS NULL AND created_at < $1
                        ) RETURNING session_id""",
                        now - timedelta(hours=24),
                    )
                    orphan_count = await conn.fetchval(
                        """WITH deleted AS (
                            DELETE FROM upload_sessions
                            WHERE job_id IS NULL AND created_at < $1
                            RETURNING id
                        ) SELECT count(*) FROM deleted""",
                        now - timedelta(hours=24),
                    )
                    if orphan_count:
                        logger.info("Orphan cleanup: removed %d stale upload sessions", orphan_count)

            except Exception as e:
                logger.exception("Retention cleanup error: %s", e)

    retention_task = asyncio.create_task(_retention_cleanup_loop())

    # ARQ Redis pool for enqueuing jobs
    try:
        from arq import create_pool as arq_create_pool
        from snatched.worker import REDIS_HOST, REDIS_PORT, REDIS_DB
        from arq.connections import RedisSettings
        arq_pool = await arq_create_pool(
            RedisSettings(host=REDIS_HOST, port=REDIS_PORT, database=REDIS_DB)
        )
        app.state.arq_pool = arq_pool
        logger.info("ARQ Redis pool connected: %s:%d/db%d", REDIS_HOST, REDIS_PORT, REDIS_DB)
    except Exception as e:
        logger.warning("ARQ Redis pool failed to connect: %s — falling back to direct execution", e)
        app.state.arq_pool = None

    yield

    # Shutdown
    if getattr(app.state, "arq_pool", None):
        await app.state.arq_pool.close()
    retention_task.cancel()
    cleanup_task.cancel()
    logger.info("Shutting down Snatched...")
    await pool.close()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    """FastAPI application factory.

    Returns configured FastAPI instance with middleware, templates,
    static files, and routes registered.

    Called by uvicorn: uvicorn snatched.app:create_app --factory
    """
    from snatched.config import load_config
    from snatched.routes import api, pages, payment

    config = load_config()

    app = FastAPI(
        title="Snatched v3",
        version="3.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    app.state.config = config

    # CSRF protection (raw ASGI middleware — avoids body consumption issues)
    from snatched.csrf import CSRFMiddleware
    from snatched.auth import REQUIRE_HTTPS
    app.add_middleware(CSRFMiddleware, dev_mode=config.server.dev_mode, require_https=REQUIRE_HTTPS)

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = datetime.now()
        response = await call_next(request)
        elapsed = (datetime.now() - start).total_seconds()
        logger.info(
            f"{request.method} {request.url.path} - {response.status_code} ({elapsed:.2f}s)"
        )
        return response

    @app.middleware("http")
    async def add_version_header(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Snatched-Version"] = "3.0"
        return response

    templates_dir = os.path.join(os.path.dirname(__file__), "templates")
    templates = Jinja2Templates(directory=templates_dir)

    # Register Jinja2 filters
    def format_size(bytes_value):
        """Convert bytes to human-readable size string."""
        if bytes_value == 0:
            return "0 B"
        k = 1024
        sizes = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        size = float(bytes_value)
        while size >= k and i < len(sizes) - 1:
            size /= k
            i += 1
        return f"{size:.1f} {sizes[i]}"

    templates.env.filters["format_size"] = format_size
    app.state.templates = templates

    static_dir = os.path.join(os.path.dirname(__file__), "static")
    app.mount("/static", StaticFiles(directory=static_dir, html=False), name="static")

    app.include_router(pages.router, prefix="", tags=["pages"])
    app.include_router(api.router, prefix="/api", tags=["api"])
    app.include_router(payment.router, prefix="/api", tags=["payment"])

    @app.exception_handler(HTTPException)
    async def auth_redirect_handler(request: Request, exc: HTTPException):
        """Redirect browsers to /login on 401. Render error page for other HTML errors. API clients get JSON."""
        accept = request.headers.get("accept", "")
        is_browser = "text/html" in accept

        if exc.status_code == 401 and is_browser:
            # Preserve intended destination so login can redirect back
            next_url = request.url.path
            if next_url and next_url not in ("/login", "/register", "/logout"):
                return RedirectResponse(url=f"/login?next={next_url}", status_code=302)
            return RedirectResponse(url="/login", status_code=302)

        # Render styled error page for browser requests (not API)
        if is_browser and not request.url.path.startswith("/api/"):
            STATUS_TITLES = {
                400: "Bad Request",
                402: "Payment Required",
                403: "Forbidden",
                404: "Not Found",
                409: "Conflict",
                500: "Server Error",
            }
            # Try to extract username from auth cookie so error page shows correct nav
            _username = None
            try:
                from snatched.auth import get_optional_user
                _username = await get_optional_user(request)
            except Exception:
                pass
            templates = request.app.state.templates
            return templates.TemplateResponse("error.html", {
                "request": request,
                "username": _username,
                "error": {
                    "title": STATUS_TITLES.get(exc.status_code, f"Error {exc.status_code}"),
                    "message": exc.detail or "An unexpected error occurred.",
                },
            }, status_code=exc.status_code)

        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    from fastapi.exceptions import RequestValidationError

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        """Render styled error for browser validation errors (e.g. /configure/abc)."""
        accept = request.headers.get("accept", "")
        if "text/html" in accept and not request.url.path.startswith("/api/"):
            _username = None
            try:
                from snatched.auth import get_optional_user
                _username = await get_optional_user(request)
            except Exception:
                pass
            templates = request.app.state.templates
            return templates.TemplateResponse("error.html", {
                "request": request,
                "username": _username,
                "error": {
                    "title": "Bad Request",
                    "message": "The URL you entered is not valid.",
                },
            }, status_code=400)
        return JSONResponse(status_code=422, content={"detail": exc.errors()})

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        """Catch-all for unhandled exceptions. Styled for browsers, JSON for API."""
        logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
        accept = request.headers.get("accept", "")
        if "text/html" in accept and not request.url.path.startswith("/api/"):
            _username = None
            try:
                from snatched.auth import get_optional_user
                _username = await get_optional_user(request)
            except Exception:
                pass
            templates = request.app.state.templates
            return templates.TemplateResponse("error.html", {
                "request": request,
                "username": _username,
                "error": {
                    "title": "Server Error",
                    "message": "Something went wrong. Please try again or contact support.",
                },
            }, status_code=500)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    return app


if __name__ == "__main__":
    import uvicorn

    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
