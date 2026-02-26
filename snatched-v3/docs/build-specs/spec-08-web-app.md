# SPEC-08: Web Application (FastAPI Backend)

**Status:** Final
**Version:** 3.0
**Date:** 2026-02-23

---

## Module Overview

Spec-08 defines the FastAPI web application factory, authentication integration, job queue management, and HTTP route handlers for Snatched v3.

**What this builds:**
- FastAPI application factory with lifespan management (startup/shutdown)
- Authelia header extraction (`X-Remote-User`, `X-Remote-Groups`) with dev-mode JWT fallback
- Job queue: create, track, cancel, and stream progress via Server-Sent Events (SSE)
- Four route modules: pages (HTML), api (JSON), uploads (file handling), and admin

**Where it fits:**
```
Browser ─HTTPS─> Traefik (172.20.1.10) ─> [Authelia] ─> Snatched FastAPI (172.20.1.30:8000)
                                                               ↓
                                                   PostgreSQL (172.20.6.10:5432)  ← app state
                                                   Per-user SQLite (/data/{user}/proc.db)
```

**V2 source file:** `/home/dave/tools/snapfix/snatched.py`

The v2 monolith (4,814 lines) is decomposed here. Key sections:

| V2 Section | Lines | V3 Disposition |
|------------|-------|----------------|
| Guided wizard | 3776–4135 | Removed — replaced by web upload flow |
| Banner printing | 4140–4404 | Replicated in `/results` page (spec-09) |
| All phase functions | 1–3775 | Moved to `snatched/processing/` package, preserved exactly |

---

## Files to Create

**Build context: `/home/dave/docker/compose/snatched/`**

```
snatched/
├── app.py                     # FastAPI factory + middleware + lifespan
├── auth.py                    # Authelia header extraction + dev-mode JWT
├── jobs.py                    # Job queue + SSE streaming
├── models.py                  # Pydantic request/response schemas
├── config.py                  # Config class (loads snatched.toml)
├── routes/
│   ├── __init__.py
│   ├── pages.py               # HTML page routes (GET /upload, GET /dashboard, etc.)
│   ├── api.py                 # JSON API endpoints
│   └── uploads.py             # File upload validation + storage
├── templates/                 # Created by spec-09
│   └── [8 Jinja2 files]
└── static/                    # Created by spec-09
    ├── style.css
    └── htmx.min.js
```

---

## Dependencies

**Python packages** (add to `requirements.txt`):
```
fastapi==0.109.0
uvicorn[standard]==0.27.0
python-multipart==0.0.6
asyncpg==0.29.0
jinja2==3.1.2
pydantic==2.5.0
pydantic-settings==2.1.0
tomli==2.0.1
PyJWT==2.8.1
```

**External tools** (available in Docker container):
- PostgreSQL 16+ (reuse `memory-store` container at 172.20.6.10, separate `snatched` database)
- `exiftool`, `ImageMagick`, `ffmpeg` (inherited from v2 pipeline, installed in Dockerfile)

**Internal module imports:**
```python
from processing import ingest, match, enrich, export, lanes
from processing.sqlite import open_database  # per-user SQLite connection
```

---

## Database Schema

The PostgreSQL schema is created automatically on startup via the FastAPI lifespan. This schema is for shared application state (users, jobs, events). Per-user processing data lives in per-user SQLite files at `/data/{username}/proc.db` — each user gets a fully isolated SQLite database with the 12-table v2 schema (assets, memories, chat_messages, chat_media_ids, snap_messages, stories, snap_pro, friends, locations, places, matches, run_log).

**Create in the `snatched` PostgreSQL database on `memory-store` (172.20.6.10):**

```sql
-- Users (auto-populated from Authelia X-Remote-User header)
CREATE TABLE IF NOT EXISTS users (
    id                   SERIAL PRIMARY KEY,
    username             TEXT UNIQUE NOT NULL,
    display_name         TEXT,
    created_at           TIMESTAMPTZ DEFAULT NOW(),
    last_seen            TIMESTAMPTZ,
    storage_quota_bytes  BIGINT DEFAULT 10737418240  -- 10 GB default
);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

-- Processing Jobs
CREATE TABLE IF NOT EXISTS processing_jobs (
    id                   SERIAL PRIMARY KEY,
    user_id              INTEGER REFERENCES users(id) ON DELETE CASCADE,
    status               TEXT NOT NULL DEFAULT 'pending',
    -- status values: 'pending', 'running', 'completed', 'failed', 'cancelled'
    upload_filename      TEXT,
    upload_size_bytes    BIGINT,
    phases_requested     TEXT[],           -- e.g. {ingest,match,enrich,export}
    lanes_requested      TEXT[],           -- e.g. {memories,chats,stories}
    progress_pct         INTEGER DEFAULT 0,
    current_phase        TEXT,
    error_message        TEXT,
    created_at           TIMESTAMPTZ DEFAULT NOW(),
    started_at           TIMESTAMPTZ,
    completed_at         TIMESTAMPTZ,
    stats_json           JSONB             -- final run statistics from pipeline
);
CREATE INDEX IF NOT EXISTS idx_jobs_user_id   ON processing_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status    ON processing_jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON processing_jobs(created_at DESC);

-- Job Events (for SSE streaming)
CREATE TABLE IF NOT EXISTS job_events (
    id          SERIAL PRIMARY KEY,
    job_id      INTEGER REFERENCES processing_jobs(id) ON DELETE CASCADE,
    event_type  TEXT NOT NULL,
    -- event_type values: 'phase_start', 'progress', 'match', 'error', 'complete'
    message     TEXT,
    data_json   JSONB,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_events_job_id     ON job_events(job_id);
CREATE INDEX IF NOT EXISTS idx_events_created_at ON job_events(created_at DESC);

-- User Preferences (for v3.1+; created now to avoid migration later)
CREATE TABLE IF NOT EXISTS user_preferences (
    id               SERIAL PRIMARY KEY,
    user_id          INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    burn_overlays    BOOLEAN DEFAULT true,
    dark_mode_pngs   BOOLEAN DEFAULT false,
    exif_enabled     BOOLEAN DEFAULT true,
    xmp_enabled      BOOLEAN DEFAULT false,
    gps_window_seconds INTEGER DEFAULT 300,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Key SQL Queries

**Get user's active jobs:**
```sql
SELECT id, status, progress_pct, current_phase, created_at
FROM processing_jobs
WHERE user_id = (SELECT id FROM users WHERE username = $1)
  AND status = 'running'
ORDER BY created_at DESC;
```

**Get job events for SSE polling (after a given event ID):**
```sql
SELECT id, event_type, message, created_at
FROM job_events
WHERE job_id = $1 AND id > $2
ORDER BY id ASC
LIMIT 100;
```

**Check storage quota:**
```sql
SELECT
    u.storage_quota_bytes,
    COALESCE(SUM(pj.upload_size_bytes), 0) AS used_bytes
FROM users u
LEFT JOIN processing_jobs pj ON u.id = pj.user_id
WHERE u.username = $1
GROUP BY u.id, u.storage_quota_bytes;
```

**Verify job ownership:**
```sql
SELECT id FROM processing_jobs
WHERE id = $1
  AND user_id = (SELECT id FROM users WHERE username = $2);
```

---

## Multi-User Adaptation

**Key changes from v2 single-user CLI to v3 multi-user web app:**

| Aspect | V2 | V3 |
|--------|----|----|
| User context | None (CLI only) | `X-Remote-User` header from Authelia |
| Data isolation | Single `/data` directory | `/data/{username}/` per user |
| Job tracking | None (synchronous CLI run) | PostgreSQL job queue + SSE streaming |
| Config per user | Global `snatched.toml` | Server TOML + PostgreSQL `user_preferences` |
| Upload handling | Command-line argument | Browser file upload + ZIP validation |
| Auth | None | Authelia delegation (zero code in app) |

**Data isolation enforcement:**
- All paths validated: `os.path.realpath(path).startswith(user_dir)`
- SQLite databases are per-user: `/data/{username}/proc.db`
- Job ownership verified on every request: `WHERE job.user_id = (SELECT id FROM users WHERE username = $1)`
- No shared mutable state between users

---

## Function Signatures

### `snatched/app.py` — FastAPI Application Factory

```python
from contextlib import asynccontextmanager
from datetime import datetime
import asyncpg
import logging
import os

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

logger = logging.getLogger("snatched")


async def init_schema(conn: asyncpg.Connection) -> None:
    """Create PostgreSQL tables if they do not exist.

    Executes the full CREATE TABLE IF NOT EXISTS DDL for:
    - users
    - processing_jobs
    - job_events
    - user_preferences

    This is idempotent — safe to call on every startup.
    """
    ...


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager: startup and shutdown.

    Startup:
    - Connect to PostgreSQL connection pool (min 5, max 20 connections)
    - Call init_schema() to create tables if needed
    - Create /data directory with mode 0o750

    Shutdown:
    - Close PostgreSQL connection pool

    Yields after startup completes; teardown runs after yield.
    """
    logger.info("Starting Snatched v3...")

    pool = await asyncpg.create_pool(
        app.state.config.database.postgres_url,
        min_size=5,
        max_size=20,
        timeout=30.0
    )
    app.state.db_pool = pool

    async with pool.acquire() as conn:
        await init_schema(conn)

    data_dir = app.state.config.server.data_dir
    os.makedirs(data_dir, mode=0o750, exist_ok=True)

    logger.info(f"Snatched ready on port {app.state.config.server.port}")
    yield

    logger.info("Shutting down Snatched...")
    await pool.close()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    """FastAPI application factory.

    Returns:
        Configured FastAPI instance with:
        - Config loaded from snatched.toml
        - Middleware (request logging, version header)
        - Jinja2 template environment
        - Static file mount at /static
        - Routes registered (pages, api)
        - Health check endpoint at /health

    Called by uvicorn: uvicorn snatched.app:create_app --factory
    """
    from config import Config
    from routes import pages, api

    config = Config.load()

    app = FastAPI(
        title="Snatched v3",
        version="3.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json"
    )

    app.state.config = config

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = datetime.now()
        response = await call_next(request)
        elapsed = (datetime.now() - start).total_seconds()
        logger.info(f"{request.method} {request.url.path} - {response.status_code} ({elapsed:.2f}s)")
        return response

    @app.middleware("http")
    async def add_version_header(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Snatched-Version"] = "3.0"
        return response

    templates = Jinja2Templates(directory="templates")
    app.state.templates = templates

    app.mount("/static", StaticFiles(directory="static", html=False), name="static")

    app.include_router(pages.router, prefix="", tags=["pages"])
    app.include_router(api.router, prefix="/api", tags=["api"])

    @app.get("/health")
    async def health():
        return {"status": "ok", "version": "3.0"}

    return app


if __name__ == "__main__":
    import uvicorn
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
```

### `snatched/auth.py` — Authelia Integration

```python
from datetime import datetime, timedelta, timezone
import os

import jwt
from fastapi import HTTPException, Request

DEV_MODE = os.getenv("SNATCHED_DEV_MODE") == "1"
JWT_SECRET = os.getenv("SNATCHED_JWT_SECRET", "dev-key-change-me")


async def get_current_user(request: Request) -> str:
    """Extract authenticated username from Authelia headers.

    Production: reads X-Remote-User header set by Authelia middleware.
    Dev mode: reads JWT cookie 'auth_token' as fallback.

    Args:
        request: FastAPI Request object

    Returns:
        Username string

    Raises:
        HTTPException(401): If not authenticated
    """
    username = request.headers.get("X-Remote-User")
    if username:
        return username

    if DEV_MODE:
        token = request.cookies.get("auth_token")
        if not token:
            raise HTTPException(401, "Not authenticated (dev mode: missing JWT cookie)")
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            username = payload.get("sub")
            if not username:
                raise ValueError("No 'sub' in JWT payload")
            return username
        except jwt.InvalidTokenError as e:
            raise HTTPException(401, f"Invalid JWT: {e}")

    raise HTTPException(
        401,
        "Not authenticated. Request must include X-Remote-User header (set by Authelia)."
    )


async def get_user_groups(request: Request) -> list[str]:
    """Extract user groups from Authelia X-Remote-Groups header.

    Args:
        request: FastAPI Request object

    Returns:
        List of group name strings (empty list if header absent)
    """
    groups_str = request.headers.get("X-Remote-Groups", "")
    return [g.strip() for g in groups_str.split(",") if g.strip()]


async def require_admin(request: Request) -> str:
    """Dependency for admin-only routes.

    Verifies authenticated user is in the 'admin' group.

    Returns:
        Username if user is admin

    Raises:
        HTTPException(403): If user is not in admin group
    """
    username = await get_current_user(request)
    groups = await get_user_groups(request)

    if "admin" not in groups:
        raise HTTPException(403, f"User '{username}' is not in admin group.")

    return username


def create_dev_jwt(username: str, expires_hours: int = 24) -> str:
    """Create a JWT token for dev mode login (NOT for production use).

    Args:
        username: User identifier
        expires_hours: Token lifetime in hours

    Returns:
        Encoded JWT token string
    """
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": username,
        "iat": now,
        "exp": now + timedelta(hours=expires_hours)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")
```

### `snatched/jobs.py` — Job Queue & SSE

```python
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import AsyncIterator

import asyncpg

logger = logging.getLogger("snatched.jobs")


@dataclass
class JobStatus:
    """Snapshot of a processing job's current state."""
    id: int
    user_id: int
    status: str           # pending | running | completed | failed | cancelled
    progress_pct: int
    current_phase: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


async def create_processing_job(
    pool: asyncpg.Pool,
    user_id: int,
    upload_filename: str,
    upload_size_bytes: int,
    phases_requested: list[str],
    lanes_requested: list[str]
) -> int:
    """Insert a new processing job record in PostgreSQL.

    Args:
        pool: asyncpg connection pool
        user_id: User ID from PostgreSQL users table
        upload_filename: Saved filename (e.g., "2026-02-23T14-30-45_export.zip")
        upload_size_bytes: File size in bytes
        phases_requested: e.g. ['ingest', 'match', 'enrich', 'export']
        lanes_requested: e.g. ['memories', 'chats', 'stories']

    Returns:
        New job ID (integer)
    """
    async with pool.acquire() as conn:
        job_id = await conn.fetchval(
            """
            INSERT INTO processing_jobs
                (user_id, upload_filename, upload_size_bytes,
                 phases_requested, lanes_requested, status)
            VALUES ($1, $2, $3, $4, $5, 'pending')
            RETURNING id
            """,
            user_id, upload_filename, upload_size_bytes,
            phases_requested, lanes_requested
        )
    logger.info(f"Created job {job_id} for user_id {user_id}")
    return job_id


async def run_job(
    pool: asyncpg.Pool,
    job_id: int,
    username: str,
    config: "Config"
) -> None:
    """Execute the 4-phase processing pipeline as a background asyncio task.

    Phases:
    1. Ingest:  Parse ZIP, scan asset files, populate per-user SQLite assets table
    2. Match:   Run 6-strategy match cascade against JSON metadata
    3. Enrich:  Add GPS, display names, output paths, EXIF tags
    4. Export:  Copy files, embed EXIF/XMP, burn overlays, render chat PNGs

    Args:
        pool: asyncpg connection pool
        job_id: Processing job ID from processing_jobs table
        username: Authenticated username (used to locate /data/{username}/)
        config: Snatched configuration object

    Side effects:
        - Updates processing_jobs (status, progress_pct, current_phase)
        - Inserts job_events rows (consumed by SSE streaming)
        - Modifies /data/{username}/proc.db (per-user SQLite)
        - Creates /data/{username}/output/ directory tree
    """
    from processing import ingest, match, enrich, export
    from processing.sqlite import open_database

    db_path = f"{config.server.data_dir}/{username}/proc.db"
    project_dir = f"{config.server.data_dir}/{username}"

    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE processing_jobs SET status='running', started_at=NOW() WHERE id=$1",
                job_id
            )

        sqlite_db = open_database(db_path)

        await emit_event(pool, job_id, "phase_start", "Ingesting export data...")
        ingest.phase_ingest(sqlite_db, project_dir, config)
        await update_job(pool, job_id, current_phase="ingest", progress_pct=25)

        await emit_event(pool, job_id, "phase_start", "Running match cascade...")
        match.phase_match(sqlite_db, config)
        await update_job(pool, job_id, current_phase="match", progress_pct=50)

        await emit_event(pool, job_id, "phase_start", "Enriching metadata...")
        enrich.phase_enrich(sqlite_db, project_dir, config)
        await update_job(pool, job_id, current_phase="enrich", progress_pct=75)

        await emit_event(pool, job_id, "phase_start", "Exporting files...")
        export.phase_export(sqlite_db, project_dir, config)
        await update_job(pool, job_id, status="completed", progress_pct=100)

        sqlite_db.close()
        logger.info(f"Job {job_id} completed successfully")

    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}", exc_info=True)
        await update_job(pool, job_id, status="failed", error_message=str(e))
        await emit_event(pool, job_id, "error", str(e))


async def update_job(
    pool: asyncpg.Pool,
    job_id: int,
    status: str | None = None,
    progress_pct: int | None = None,
    current_phase: str | None = None,
    error_message: str | None = None
) -> None:
    """Update one or more fields on a processing_jobs row.

    Only specified (non-None) fields are updated. Setting status='completed'
    also sets completed_at=NOW().
    """
    updates = []
    params: list = [job_id]

    if status is not None:
        updates.append(f"status=${len(params)+1}")
        params.append(status)
        if status == "completed":
            updates.append("completed_at=NOW()")

    if progress_pct is not None:
        updates.append(f"progress_pct=${len(params)+1}")
        params.append(progress_pct)

    if current_phase is not None:
        updates.append(f"current_phase=${len(params)+1}")
        params.append(current_phase)

    if error_message is not None:
        updates.append(f"error_message=${len(params)+1}")
        params.append(error_message)

    if not updates:
        return

    async with pool.acquire() as conn:
        await conn.execute(
            f"UPDATE processing_jobs SET {', '.join(updates)} WHERE id=$1",
            *params
        )


async def emit_event(
    pool: asyncpg.Pool,
    job_id: int,
    event_type: str,
    message: str,
    data_json: dict | None = None
) -> None:
    """Insert a job event row for SSE consumption.

    Event types: 'phase_start', 'progress', 'match', 'error', 'complete'
    """
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO job_events (job_id, event_type, message, data_json)
            VALUES ($1, $2, $3, $4)
            """,
            job_id, event_type, message, data_json or {}
        )


async def get_events_after(
    pool: asyncpg.Pool,
    job_id: int,
    last_id: int
) -> list[dict]:
    """Fetch job events with id > last_id for SSE polling.

    Returns:
        List of event dicts with keys: id, event_type, message, created_at
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, event_type, message, created_at
            FROM job_events
            WHERE job_id=$1 AND id > $2
            ORDER BY id ASC
            LIMIT 100
            """,
            job_id, last_id
        )
    return [dict(row) for row in rows]


async def is_job_complete(pool: asyncpg.Pool, job_id: int) -> bool:
    """Return True if job has reached a terminal state (completed or failed)."""
    async with pool.acquire() as conn:
        status = await conn.fetchval(
            "SELECT status FROM processing_jobs WHERE id=$1",
            job_id
        )
    return status in ("completed", "failed", "cancelled")


async def cancel_job(pool: asyncpg.Pool, job_id: int) -> bool:
    """Request job cancellation.

    Marks job as 'cancelled' in the database. Does not forcefully
    terminate the running asyncio task (graceful shutdown via polling).

    Returns:
        True if job was cancelled, False if already in terminal state
    """
    async with pool.acquire() as conn:
        current_status = await conn.fetchval(
            "SELECT status FROM processing_jobs WHERE id=$1",
            job_id
        )

    if current_status in ("completed", "failed", "cancelled"):
        return False

    await update_job(pool, job_id, status="cancelled")
    logger.info(f"Job {job_id} cancellation requested")
    return True


async def job_stream(
    pool: asyncpg.Pool,
    job_id: int
) -> AsyncIterator[str]:
    """Server-Sent Events generator for job progress.

    Polls job_events table every 0.5s. Yields SSE-formatted strings.
    Terminates when job reaches terminal state.

    Usage in route:
        return StreamingResponse(job_stream(pool, job_id), media_type="text/event-stream")

    SSE format yielded:
        "event: {event_type}\\ndata: {message}\\n\\n"
        "event: complete\\ndata: done\\n\\n"  (final event)
    """
    last_id = 0

    while True:
        events = await get_events_after(pool, job_id, last_id)

        for event in events:
            yield f"event: {event['event_type']}\n"
            yield f"data: {event['message']}\n\n"
            last_id = event['id']

        if await is_job_complete(pool, job_id):
            yield "event: complete\ndata: done\n\n"
            break

        await asyncio.sleep(0.5)
```

### `snatched/routes/pages.py` — HTML Page Routes

```python
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from auth import get_current_user

logger = logging.getLogger("snatched.routes.pages")
router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def landing(request: Request, username: str = Depends(get_current_user)):
    """GET / — Landing page.

    Shows welcome message and links to /upload and /dashboard.
    Template: landing.html
    Context: {request, username}
    """
    ...


@router.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request, username: str = Depends(get_current_user)):
    """GET /upload — Upload form page.

    Template: upload.html
    Context: {request, username, max_upload_bytes}
    """
    ...


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, username: str = Depends(get_current_user)):
    """GET /dashboard — Job status page.

    Shows active jobs (polling every 2s via htmx) and job history.
    Template: dashboard.html
    Context: {request, username}
    """
    ...


@router.get("/results/{job_id}", response_class=HTMLResponse)
async def results(
    request: Request,
    job_id: int,
    username: str = Depends(get_current_user)
):
    """GET /results/{job_id} — Results browser.

    Verifies job belongs to authenticated user (404 if not found).
    Shows summary tab, matches tab, assets tab.
    Template: results.html
    Context: {request, username, job_id, job}
    """
    ...


@router.get("/download/{job_id}", response_class=HTMLResponse)
async def download_page(
    request: Request,
    job_id: int,
    username: str = Depends(get_current_user)
):
    """GET /download/{job_id} — Download manager page.

    Shows file tree for /data/{username}/output/{job_id}/.
    Template: download.html
    Context: {request, username, job_id}
    """
    ...
```

### `snatched/routes/api.py` — JSON API Endpoints

```python
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse

from auth import get_current_user
from jobs import cancel_job, create_processing_job, job_stream, run_job

logger = logging.getLogger("snatched.routes.api")
router = APIRouter()


@router.post("/upload")
async def upload(
    file: UploadFile,
    request: Request,
    username: str = Depends(get_current_user)
) -> dict:
    """POST /api/upload — Accept Snapchat export ZIP.

    Validates: file type (ZIP), size limit, storage quota, Snapchat structure.
    Saves to /data/{username}/uploads/.
    Creates job in PostgreSQL.
    Launches run_job() as asyncio background task.

    Response:
        {"job_id": 42, "redirect_to": "/dashboard"}
    """
    from routes.uploads import handle_upload
    result = await handle_upload(file, username, request.app.state)
    asyncio.create_task(
        run_job(request.app.state.db_pool, result['job_id'], username, request.app.state.config)
    )
    return result


@router.get("/jobs")
async def list_jobs(
    request: Request,
    status: str | None = Query(None),
    username: str = Depends(get_current_user)
) -> list[dict]:
    """GET /api/jobs — List authenticated user's jobs.

    Optional query param: ?status=running (or completed, failed, etc.)

    Response: List of job dicts with id, status, progress_pct, current_phase,
              created_at, completed_at
    """
    ...


@router.get("/jobs/{job_id}")
async def job_detail(
    job_id: int,
    request: Request,
    username: str = Depends(get_current_user)
) -> dict:
    """GET /api/jobs/{job_id} — Job detail with full stats.

    Verifies ownership (404 if job not found or belongs to another user).
    Returns full job row including stats_json.
    """
    ...


@router.get("/jobs/{job_id}/stream")
async def stream_job(
    job_id: int,
    request: Request,
    username: str = Depends(get_current_user)
):
    """GET /api/jobs/{job_id}/stream — SSE progress stream.

    Verifies ownership before streaming.

    Returns: StreamingResponse with media_type="text/event-stream"

    Events:
        event: phase_start
        data: Ingesting export data...

        event: progress
        data: {"phase": "ingest", "pct": 25}

        event: complete
        data: done
    """
    async with request.app.state.db_pool.acquire() as conn:
        owner = await conn.fetchval(
            "SELECT u.username FROM processing_jobs pj "
            "JOIN users u ON pj.user_id = u.id WHERE pj.id = $1",
            job_id
        )
    if owner != username:
        raise HTTPException(403, "Access denied")

    return StreamingResponse(
        job_stream(request.app.state.db_pool, job_id),
        media_type="text/event-stream"
    )


@router.post("/jobs/{job_id}/cancel")
async def cancel(
    job_id: int,
    request: Request,
    username: str = Depends(get_current_user)
) -> dict:
    """POST /api/jobs/{job_id}/cancel — Request job cancellation.

    Response: {"cancelled": true} or {"cancelled": false, "reason": "..."}
    """
    ...


@router.post("/jobs/{job_id}/reprocess")
async def reprocess(
    job_id: int,
    request: Request,
    phases: list[str] = Query(...),
    lanes: list[str] = Query(...),
    username: str = Depends(get_current_user)
) -> dict:
    """POST /api/jobs/{job_id}/reprocess — Trigger selective reprocessing.

    Query params: ?phases=match&phases=enrich&lanes=memories&lanes=chats

    Response: {"new_job_id": 43, "message": "Reprocessing started"}
    """
    ...


@router.get("/summary")
async def user_summary(
    request: Request,
    username: str = Depends(get_current_user)
) -> dict:
    """GET /api/summary — Aggregate pipeline metrics for authenticated user.

    Response:
        {
          "total_jobs": 5,
          "completed_jobs": 4,
          "total_assets_processed": 12847,
          "total_matches": 9284,
          "total_storage_bytes": 1234567890
        }
    """
    ...


@router.get("/assets")
async def list_assets(
    job_id: int = Query(...),
    page: int = Query(1),
    username: str = Depends(get_current_user),
    request: Request = None
) -> dict:
    """GET /api/assets?job_id=42&page=1 — Paginated asset list.

    Response:
        {"items": [...], "total": 5000, "page": 1, "page_size": 50, "total_pages": 100}
    """
    ...


@router.get("/matches")
async def list_matches(
    job_id: int = Query(...),
    page: int = Query(1),
    username: str = Depends(get_current_user),
    request: Request = None
) -> dict:
    """GET /api/matches?job_id=42&page=1 — Match list with confidence scores."""
    ...


@router.get("/download/{path:path}")
async def download_file(
    path: str,
    username: str = Depends(get_current_user),
    request: Request = None
):
    """GET /api/download/{path} — Stream a processed output file.

    Path traversal protection: resolves path relative to /data/{username}/output/
    and verifies it stays within that directory before serving.

    Raises:
        HTTPException(400): Path traversal attempt detected
        HTTPException(404): File not found
    """
    ...


@router.get("/health")
async def health() -> dict:
    """GET /api/health — Health check (no auth required)."""
    return {"status": "ok", "version": "3.0"}
```

### `snatched/routes/uploads.py` — Upload Handling

```python
import logging
import os
import zipfile
from datetime import datetime

from fastapi import HTTPException, UploadFile

logger = logging.getLogger("snatched.routes.uploads")


async def handle_upload(
    file: UploadFile,
    username: str,
    app_state
) -> dict:
    """Validate, save, and register an uploaded Snapchat export ZIP.

    Args:
        file: UploadFile from FastAPI multipart
        username: Authenticated username
        app_state: request.app.state (contains config, db_pool)

    Returns:
        {"job_id": int, "upload_path": str}

    Raises:
        HTTPException(400): Validation failed (bad ZIP, missing json/ directory)
        HTTPException(413): File exceeds max_upload_bytes
        HTTPException(507): User storage quota exceeded
    """
    config = app_state.config
    pool = app_state.db_pool

    content = await file.read()

    # Size check
    if len(content) > config.server.max_upload_bytes:
        raise HTTPException(413, f"File too large: {len(content)} > {config.server.max_upload_bytes}")

    # Quota check
    user_id = await get_or_create_user(pool, username)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT u.storage_quota_bytes,
                   COALESCE(SUM(pj.upload_size_bytes), 0) AS used_bytes
            FROM users u
            LEFT JOIN processing_jobs pj ON u.id = pj.user_id
            WHERE u.id = $1
            GROUP BY u.id, u.storage_quota_bytes
            """,
            user_id
        )
    if row['used_bytes'] + len(content) > row['storage_quota_bytes']:
        raise HTTPException(507, "Storage quota exceeded")

    # ZIP structure check
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            namelist = z.namelist()
            has_json = any(
                n.startswith("json/") or n == "memories_history.json"
                for n in namelist
            )
            if not has_json:
                raise HTTPException(
                    400,
                    "Invalid Snapchat export: missing json/ directory or memories_history.json"
                )
    except zipfile.BadZipFile:
        raise HTTPException(400, "File is not a valid ZIP archive")

    # Save file
    user_dir = f"{config.server.data_dir}/{username}"
    uploads_dir = f"{user_dir}/uploads"
    os.makedirs(uploads_dir, mode=0o750, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    filename = f"{timestamp}_{file.filename}"
    filepath = os.path.join(uploads_dir, filename)

    with open(filepath, "wb") as f:
        f.write(content)

    logger.info(f"Uploaded {filename} ({len(content)} bytes) for user {username}")

    from jobs import create_processing_job
    job_id = await create_processing_job(
        pool,
        user_id=user_id,
        upload_filename=filename,
        upload_size_bytes=len(content),
        phases_requested=["ingest", "match", "enrich", "export"],
        lanes_requested=["memories", "chats", "stories"]
    )

    return {"job_id": job_id, "upload_path": filepath, "redirect_to": "/dashboard"}


async def get_or_create_user(pool, username: str) -> int:
    """Get user ID from PostgreSQL, creating the user record if it does not exist.

    Args:
        pool: asyncpg connection pool
        username: Username from Authelia header

    Returns:
        User ID (integer)
    """
    async with pool.acquire() as conn:
        user_id = await conn.fetchval(
            "SELECT id FROM users WHERE username=$1",
            username
        )
        if not user_id:
            user_id = await conn.fetchval(
                "INSERT INTO users (username) VALUES ($1) RETURNING id",
                username
            )
    return user_id
```

---

## Code Examples

### Complete Upload + Stream Flow

```python
# POST /api/upload → returns job_id, launches background task
# Frontend then connects to SSE:

# HTML (htmx):
# <form hx-post="/api/upload" hx-encoding="multipart/form-data"
#       hx-target="#status" hx-indicator="#spinner">
#   <input type="file" name="file" accept=".zip">
#   <button type="submit">Process</button>
# </form>

# After upload succeeds, redirect to dashboard:
# <div hx-ext="sse" sse-connect="/api/jobs/42/stream">
#   <div sse-swap="phase_start" hx-swap="beforeend">...</div>
# </div>
```

### Path Traversal Protection

```python
import os

def safe_user_path(username: str, relative_path: str, config) -> str:
    """Resolve a path relative to user's output directory.

    Raises HTTPException(400) if the resolved path escapes the user dir.
    """
    user_output_dir = os.path.realpath(
        f"{config.server.data_dir}/{username}/output"
    )
    target = os.path.realpath(
        os.path.join(user_output_dir, relative_path)
    )
    if not target.startswith(user_output_dir + os.sep):
        raise HTTPException(400, "Path traversal attempt blocked")
    return target
```

---

## Acceptance Criteria

- [ ] `create_app()` returns a `FastAPI` instance with all middleware registered
- [ ] Lifespan startup creates PostgreSQL pool and runs `init_schema()`
- [ ] Lifespan shutdown closes the pool cleanly
- [ ] `auth.py` extracts `X-Remote-User` header in production
- [ ] `auth.py` accepts JWT cookie in dev mode (`SNATCHED_DEV_MODE=1`)
- [ ] `get_current_user()` raises `HTTPException(401)` when neither auth method works
- [ ] `create_processing_job()` inserts a row and returns the new job ID
- [ ] `run_job()` updates `processing_jobs` status at each phase boundary
- [ ] SSE stream: `curl -s "http://localhost:8000/api/jobs/1/stream"` produces events
- [ ] `GET /` returns 200 HTML (landing.html)
- [ ] `GET /upload` returns 200 HTML (upload.html) with `max_upload_bytes` in context
- [ ] `GET /dashboard` returns 200 HTML
- [ ] `GET /api/health` returns `{"status": "ok"}` with no auth required
- [ ] Upload validation rejects files without `json/` directory structure
- [ ] Upload validation rejects non-ZIP files with HTTP 400
- [ ] Upload exceeding `max_upload_bytes` returns HTTP 413
- [ ] Upload exceeding user quota returns HTTP 507
- [ ] Path traversal in `GET /api/download/../../etc/passwd` returns HTTP 400
- [ ] Job ownership verified: user A cannot access user B's jobs (HTTP 403)
- [ ] `cancel_job()` marks job as 'cancelled'; returns False if already terminal
- [ ] PostgreSQL schema created automatically on startup (idempotent)
- [ ] Docker health check passes: `curl -sf http://127.0.0.1:8000/api/health`
- [ ] Dev-mode JWT: `create_dev_jwt("dave")` produces a valid token that `auth.py` accepts
