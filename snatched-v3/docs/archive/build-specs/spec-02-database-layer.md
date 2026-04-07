# Spec 02 — Database Layer

## Module Overview

The database layer provides persistence for Snatched v3's multi-user architecture. It consists of two components:

1. **`snatched/db.py`** — Shared PostgreSQL layer for application state (users, jobs, events)
2. **`snatched/processing/sqlite.py`** — Per-user SQLite for isolated processing data

This separation allows:
- Multiple users to submit jobs without contention
- Each user's processing data isolated in a separate SQLite database
- Async job tracking and SSE event streaming via PostgreSQL
- Full audit trail of processing events per job

**Note:** `snatched/processing/sqlite.py` schema and helpers are also defined in **Spec 01 (Foundation)**. This spec focuses on the PostgreSQL layer (`db.py`) and provides the complete reference for both layers as a standalone document.

---

## Files to Create

```
snatched/
├── db.py                          # PostgreSQL connection pool + schema init
└── processing/
    └── sqlite.py                  # Per-user SQLite + migration logic
```

---

## Dependencies

**Build order:** Spec 02 must be built before Spec 03–05 (which use the per-user SQLite).

**Python imports for `db.py`:**
```python
import asyncpg
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
```

**Python imports for `processing/sqlite.py`:**
```python
import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

BATCH_SIZE: int = 500  # Rows per commit batch
```

**External packages:**
- `asyncpg` — async PostgreSQL driver (`pip install asyncpg`)
- `sqlite3` — Python stdlib (no install needed)

---

## V2 Source Reference

### PostgreSQL (new in v3)
Not present in v2. This is the web-first multi-user enhancement. Schema designed to support async job orchestration across multiple users.

### SQLite (ported from v2)
- **Schema:** `/home/dave/tools/snapfix/snatched.py` lines 272–471
  - 12 core tables: assets, chat_messages, chat_media_ids, snap_messages, memories, stories, snap_pro, friends, locations, places, matches, run_log
  - Indexes on all key columns for efficient matching
  - Foreign keys enabled via PRAGMA
- **`open_database()`:** `/home/dave/tools/snapfix/snatched.py` lines 4553–4574
  - Creates directory if needed
  - Applies SCHEMA_SQL via `executescript`
  - Migrates old column names (e.g., `created_us` → `created_ms`)
- **`create_schema()`:** `/home/dave/tools/snapfix/snatched.py` lines 474–498

---

## Function Signatures

### `snatched/db.py` — PostgreSQL Layer

```python
async def get_pool(
    postgres_url: str,
    min_size: int = 2,
    max_size: int = 10,
) -> asyncpg.Pool:
    """Create and return an asyncpg connection pool.

    Retries up to 3 times on connection failure (1s delay between retries).

    Args:
        postgres_url: Full DSN, e.g. 'postgresql://user:pass@host:5432/db'
        min_size: Minimum pool connections
        max_size: Maximum pool connections

    Returns:
        asyncpg.Pool ready for queries.

    Raises:
        ConnectionError: If unable to connect after 3 retries.
    """


async def init_schema(pool: asyncpg.Pool) -> None:
    """Create all PostgreSQL tables if they don't exist.

    Idempotent — safe to call on every startup.

    Tables created:
    - users
    - processing_jobs
    - job_events
    """


async def create_user(
    pool: asyncpg.Pool,
    username: str,
    display_name: str | None = None,
    storage_quota_bytes: int = 10 * 1024 * 1024 * 1024,
) -> int:
    """Create a new user. Return user_id.

    Args:
        pool: asyncpg connection pool
        username: Unique username (from Authelia X-Remote-User header)
        display_name: Optional display name
        storage_quota_bytes: Storage limit in bytes (default 10 GB)

    Returns:
        int: New user ID.

    Raises:
        asyncpg.UniqueViolationError: If username already exists.
    """


async def get_or_create_user(
    pool: asyncpg.Pool,
    username: str,
    display_name: str | None = None,
) -> int:
    """Get user_id for username, creating the user if not found.

    Used on every authenticated request to auto-provision users.

    Args:
        pool: asyncpg connection pool
        username: Username from Authelia header
        display_name: Optional display name (used only on creation)

    Returns:
        int: User ID (existing or newly created).
    """


async def create_job(
    pool: asyncpg.Pool,
    user_id: int,
    upload_filename: str,
    upload_size_bytes: int,
    phases_requested: list[str],
    lanes_requested: list[str],
) -> int:
    """Create a new processing job. Return job_id.

    Initial status is 'pending'. Job runner picks it up and transitions to 'running'.

    Args:
        pool: asyncpg connection pool
        user_id: PK from users table
        upload_filename: Original ZIP filename (e.g., 'snapchat-export-1234.zip')
        upload_size_bytes: Total bytes of uploaded ZIP
        phases_requested: Subset of ['ingest', 'match', 'enrich', 'export']
        lanes_requested: Subset of ['memories', 'chats', 'stories'] (empty = all)

    Returns:
        int: New job ID.
    """


async def update_job(
    pool: asyncpg.Pool,
    job_id: int,
    status: str | None = None,
    current_phase: str | None = None,
    progress_pct: int | None = None,
    error_message: str | None = None,
    stats_json: dict | None = None,
) -> None:
    """Update job fields. None values are skipped (no UPDATE for that column).

    Auto-behavior:
    - Sets started_at = NOW() on first transition away from 'pending'
    - Sets completed_at = NOW() when status becomes 'completed' or 'failed'

    Args:
        pool: asyncpg connection pool
        job_id: Job to update
        status: New status ('pending', 'running', 'completed', 'failed')
        current_phase: Currently executing phase name
        progress_pct: Integer 0–100
        error_message: Error description if status='failed'
        stats_json: Final stats dict (serialized to JSONB)
    """


async def emit_event(
    pool: asyncpg.Pool,
    job_id: int,
    event_type: str,
    message: str | None = None,
    data_json: dict | None = None,
) -> int:
    """Log an event for a job. Return event_id.

    Event types used by the pipeline:
    - 'phase_started' — phase is beginning
    - 'phase_completed' — phase finished successfully
    - 'progress' — progress percentage update
    - 'warning' — non-fatal issue
    - 'error' — fatal error, job will fail
    - 'complete' — entire job finished

    Args:
        pool: asyncpg connection pool
        job_id: Job this event belongs to
        event_type: Event category string
        message: Human-readable description
        data_json: Optional structured data dict

    Returns:
        int: New event ID.
    """


async def get_events_after(
    pool: asyncpg.Pool,
    job_id: int,
    after_event_id: int,
) -> list[dict]:
    """Get all events for a job after a given event_id.

    Used by the SSE endpoint to stream events to the browser.

    Args:
        pool: asyncpg connection pool
        job_id: Job to query
        after_event_id: Return only events with id > this value (0 = all)

    Returns:
        List of event dicts: [
            {
                'id': int,
                'event_type': str,
                'message': str | None,
                'data_json': dict | None,
                'created_at': datetime,
            },
            ...
        ]
    """


async def get_user_jobs(
    pool: asyncpg.Pool,
    user_id: int,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Get jobs for a user, most recent first.

    Args:
        pool: asyncpg connection pool
        user_id: Filter to this user
        limit: Max results
        offset: Pagination offset

    Returns:
        List of job dicts: [
            {
                'id': int,
                'status': str,
                'upload_filename': str,
                'upload_size_bytes': int,
                'progress_pct': int,
                'current_phase': str | None,
                'created_at': datetime,
                'started_at': datetime | None,
                'completed_at': datetime | None,
                'stats_json': dict | None,
            },
            ...
        ]
    """
```

---

### `snatched/processing/sqlite.py` — Per-User SQLite Layer

```python
def open_database(db_path: Path) -> sqlite3.Connection:
    """Open (or create) the per-user SQLite processing database.

    Creates parent directories if they don't exist.
    Applies full schema (idempotent — uses CREATE TABLE IF NOT EXISTS).
    Runs v2→v3 migrations for databases from older versions.

    Args:
        db_path: Path to SQLite file. Use Path(':memory:') for testing.

    Returns:
        sqlite3.Connection with:
        - row_factory = sqlite3.Row (dict-like row access)
        - WAL journal mode
        - Foreign keys enabled

    Raises:
        sqlite3.Error: If DB cannot be opened or schema cannot be applied.
    """


def create_schema(db: sqlite3.Connection) -> list[str]:
    """Create all 14 SQLite tables and 18 indexes.

    Idempotent — uses CREATE TABLE IF NOT EXISTS throughout.

    Returns:
        List of table names verified to exist (sorted alphabetically).
    """


def migrate_schema(db: sqlite3.Connection) -> None:
    """Apply v2→v3 schema migrations.

    All migrations are idempotent — safe to run on an already-migrated DB.

    Migrations:
    - ALTER TABLE matches ADD COLUMN lane TEXT DEFAULT 'memories'
    - ALTER TABLE assets ADD COLUMN xmp_written BOOLEAN DEFAULT 0
    - ALTER TABLE assets ADD COLUMN xmp_path TEXT
    - CREATE TABLE IF NOT EXISTS reprocess_log (...)
    - CREATE TABLE IF NOT EXISTS lane_config (...)

    Implementation note: SQLite does not support IF NOT EXISTS on ALTER TABLE.
    Use PRAGMA table_info() to check for existing columns before ALTER.
    """


def batch_insert(
    db: sqlite3.Connection,
    table: str,
    columns: list[str],
    rows: list[tuple],
    batch_size: int = BATCH_SIZE,
) -> int:
    """Bulk insert rows into a table with per-batch commits.

    SECURITY: `table` and `columns` are inserted directly into SQL.
    Callers must pass only trusted constant values — never user input.

    Args:
        db: SQLite connection
        table: Table name (trusted constant, e.g., 'memories')
        columns: Column names (trusted constants)
        rows: List of value tuples
        batch_size: Rows per commit (default BATCH_SIZE=500)

    Returns:
        Total rows inserted.
    """


def batch_update(
    db: sqlite3.Connection,
    sql: str,
    rows: list[tuple],
    batch_size: int = BATCH_SIZE,
) -> int:
    """Execute a parameterized SQL statement on multiple row tuples with batching.

    Args:
        db: SQLite connection
        sql: Parameterized SQL (e.g., "UPDATE assets SET output_path=? WHERE id=?")
        rows: List of parameter tuples
        batch_size: Rows per commit (default BATCH_SIZE=500)

    Returns:
        Total rows affected.
    """


def log_run(
    db: sqlite3.Connection,
    version: str,
    person: str,
    input_path: str,
    flags_json: dict | None = None,
) -> int:
    """Insert a run_log entry. Return the new run_id.

    Args:
        db: SQLite connection
        version: Snatched version (e.g., '3.0')
        person: Username
        input_path: Path to input export directory
        flags_json: Optional dict of pipeline flags/config snapshot

    Returns:
        int: run_log row ID.
    """


def update_run(
    db: sqlite3.Connection,
    run_id: int,
    phase: str | None = None,
    status: str | None = None,
    total_assets: int | None = None,
    total_matched: int | None = None,
    total_exif_ok: int | None = None,
    total_exif_err: int | None = None,
    total_copied: int | None = None,
    elapsed_seconds: float | None = None,
    error_message: str | None = None,
) -> None:
    """Update a run_log entry. None values are skipped."""
```

---

## Database Schema

### PostgreSQL DDL (for `snatched/db.py`)

```sql
-- USERS: One row per authenticated user (auto-created on first login)
CREATE TABLE IF NOT EXISTS users (
    id                   SERIAL PRIMARY KEY,
    username             TEXT UNIQUE NOT NULL,
    display_name         TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen            TIMESTAMPTZ,
    storage_quota_bytes  BIGINT NOT NULL DEFAULT 10737418240
);

CREATE INDEX IF NOT EXISTS idx_users_username   ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at DESC);

-- PROCESSING_JOBS: One row per upload/pipeline job
CREATE TABLE IF NOT EXISTS processing_jobs (
    id                   SERIAL PRIMARY KEY,
    user_id              INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status               TEXT NOT NULL DEFAULT 'pending'
                         CHECK(status IN ('pending', 'running', 'completed', 'failed')),
    upload_filename      TEXT,
    upload_size_bytes    BIGINT,
    phases_requested     TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    lanes_requested      TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    progress_pct         INTEGER NOT NULL DEFAULT 0
                         CHECK(progress_pct >= 0 AND progress_pct <= 100),
    current_phase        TEXT,
    error_message        TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at           TIMESTAMPTZ,
    completed_at         TIMESTAMPTZ,
    stats_json           JSONB
);

CREATE INDEX IF NOT EXISTS idx_jobs_user_id    ON processing_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status     ON processing_jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON processing_jobs(created_at DESC);

-- JOB_EVENTS: SSE / polling event stream per job
CREATE TABLE IF NOT EXISTS job_events (
    id           SERIAL PRIMARY KEY,
    job_id       INTEGER NOT NULL REFERENCES processing_jobs(id) ON DELETE CASCADE,
    event_type   TEXT NOT NULL,
    message      TEXT,
    data_json    JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_events_job_id    ON job_events(job_id);
CREATE INDEX IF NOT EXISTS idx_events_created_at ON job_events(created_at DESC);
```

### SQLite DDL (for `snatched/processing/sqlite.py`)

Full DDL lives in `snatched/processing/schema.sql`. Reproduced here for self-containment:

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

-- ASSETS: Every media file discovered on disk
CREATE TABLE IF NOT EXISTS assets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    path            TEXT NOT NULL UNIQUE,
    filename        TEXT NOT NULL,
    date_str        TEXT,
    file_id         TEXT,
    ext             TEXT NOT NULL,
    real_ext        TEXT,
    asset_type      TEXT NOT NULL
                    CHECK(asset_type IN ('memory_main', 'memory_overlay', 'chat',
                                        'chat_overlay', 'chat_thumbnail', 'story')),
    is_video        BOOLEAN NOT NULL DEFAULT 0,
    is_fmp4         BOOLEAN NOT NULL DEFAULT 0,
    memory_uuid     TEXT,
    file_size       INTEGER,
    sha256          TEXT,
    output_path     TEXT,
    output_sha256   TEXT,
    exif_written    BOOLEAN DEFAULT 0,
    exif_error      TEXT,
    xmp_written     BOOLEAN DEFAULT 0,
    xmp_path        TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_assets_file_id     ON assets(file_id);
CREATE INDEX IF NOT EXISTS idx_assets_memory_uuid ON assets(memory_uuid);
CREATE INDEX IF NOT EXISTS idx_assets_date_str    ON assets(date_str);
CREATE INDEX IF NOT EXISTS idx_assets_asset_type  ON assets(asset_type);

-- CHAT_MESSAGES: Every message from chat_history.json
CREATE TABLE IF NOT EXISTS chat_messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    from_user       TEXT,
    media_type      TEXT,
    media_ids       TEXT,
    content         TEXT,
    created         TEXT,
    created_ms      INTEGER,
    is_sender       BOOLEAN DEFAULT 0,
    conversation_title TEXT,
    created_dt      TEXT,
    created_date    TEXT
);

CREATE INDEX IF NOT EXISTS idx_chat_media_ids    ON chat_messages(media_ids);
CREATE INDEX IF NOT EXISTS idx_chat_created_date ON chat_messages(created_date);
CREATE INDEX IF NOT EXISTS idx_chat_conversation ON chat_messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_chat_media_type   ON chat_messages(media_type);

-- CHAT_MEDIA_IDS: Exploded pipe-separated media IDs for efficient JOIN
CREATE TABLE IF NOT EXISTS chat_media_ids (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_message_id INTEGER NOT NULL REFERENCES chat_messages(id),
    media_id        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_mid ON chat_media_ids(media_id);

-- SNAP_MESSAGES: Every entry from snap_history.json
CREATE TABLE IF NOT EXISTS snap_messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    from_user       TEXT,
    media_type      TEXT,
    created         TEXT,
    created_ms      INTEGER,
    is_sender       BOOLEAN DEFAULT 0,
    conversation_title TEXT,
    created_dt      TEXT,
    created_date    TEXT,
    dedup_key       TEXT UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_snap_created_date ON snap_messages(created_date);
CREATE INDEX IF NOT EXISTS idx_snap_media_type   ON snap_messages(media_type);
CREATE INDEX IF NOT EXISTS idx_snap_date_type    ON snap_messages(created_date, media_type);

-- MEMORIES: All entries from memories_history.json
CREATE TABLE IF NOT EXISTS memories (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    mid             TEXT UNIQUE,
    date            TEXT,
    date_dt         TEXT,
    media_type      TEXT,
    location_raw    TEXT,
    lat             REAL,
    lon             REAL,
    download_link   TEXT
);

CREATE INDEX IF NOT EXISTS idx_memories_mid  ON memories(mid);
CREATE INDEX IF NOT EXISTS idx_memories_date ON memories(date_dt);

-- STORIES: Entries from shared_story.json
CREATE TABLE IF NOT EXISTS stories (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id        TEXT,
    created         TEXT,
    created_dt      TEXT,
    content_type    TEXT
);

CREATE INDEX IF NOT EXISTS idx_stories_id   ON stories(story_id);
CREATE INDEX IF NOT EXISTS idx_stories_type ON stories(content_type);

-- SNAP_PRO: Saved stories from snap_pro.json
CREATE TABLE IF NOT EXISTS snap_pro (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    url             TEXT,
    created         TEXT,
    created_dt      TEXT,
    title           TEXT
);

-- FRIENDS: Username to display name mapping
CREATE TABLE IF NOT EXISTS friends (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT NOT NULL UNIQUE,
    display_name    TEXT,
    category        TEXT
);

CREATE INDEX IF NOT EXISTS idx_friends_username ON friends(username);

-- LOCATIONS: GPS breadcrumbs from location_history.json
CREATE TABLE IF NOT EXISTS locations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    timestamp_unix  REAL NOT NULL,
    lat             REAL NOT NULL,
    lon             REAL NOT NULL,
    accuracy_m      REAL
);

CREATE INDEX IF NOT EXISTS idx_locations_ts ON locations(timestamp_unix);

-- PLACES: Snap Map places from snap_map_places.json
CREATE TABLE IF NOT EXISTS places (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT,
    lat             REAL,
    lon             REAL,
    address         TEXT,
    visit_count     INTEGER
);

-- MATCHES: Join table linking assets to metadata sources (Phase 2)
CREATE TABLE IF NOT EXISTS matches (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id        INTEGER NOT NULL REFERENCES assets(id),
    strategy        TEXT NOT NULL,
    confidence      REAL NOT NULL DEFAULT 0.0,
    is_best         BOOLEAN NOT NULL DEFAULT 0,
    memory_id       INTEGER REFERENCES memories(id),
    chat_message_id INTEGER REFERENCES chat_messages(id),
    snap_message_id INTEGER REFERENCES snap_messages(id),
    story_id        INTEGER REFERENCES stories(id),
    matched_date    TEXT,
    matched_lat     REAL,
    matched_lon     REAL,
    gps_source      TEXT,
    display_name    TEXT,
    creator_str     TEXT,
    direction       TEXT,
    conversation    TEXT,
    lane            TEXT DEFAULT 'memories',
    output_subdir   TEXT,
    output_filename TEXT,
    exif_tags_json  TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_matches_asset    ON matches(asset_id);
CREATE INDEX IF NOT EXISTS idx_matches_best     ON matches(asset_id, is_best);
CREATE INDEX IF NOT EXISTS idx_matches_strategy ON matches(strategy);
CREATE INDEX IF NOT EXISTS idx_matches_lane     ON matches(lane);

-- RUN_LOG: Audit trail for each pipeline execution
CREATE TABLE IF NOT EXISTS run_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    version         TEXT NOT NULL,
    person          TEXT NOT NULL,
    input_path      TEXT NOT NULL,
    started_at      TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at     TEXT,
    phase           TEXT,
    status          TEXT DEFAULT 'running',
    flags_json      TEXT,
    total_assets    INTEGER,
    total_matched   INTEGER,
    total_exif_ok   INTEGER,
    total_exif_err  INTEGER,
    total_copied    INTEGER,
    elapsed_seconds REAL,
    error_message   TEXT
);

-- REPROCESS_LOG: Track reprocessing runs (v3 addition)
CREATE TABLE IF NOT EXISTS reprocess_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL DEFAULT (datetime('now')),
    phases          TEXT,
    lanes           TEXT,
    triggered_by    TEXT,
    status          TEXT DEFAULT 'pending',
    result_json     TEXT
);

-- LANE_CONFIG: Per-lane user overrides (v3 addition)
CREATE TABLE IF NOT EXISTS lane_config (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    lane_name       TEXT UNIQUE NOT NULL,
    config_json     TEXT
);
```

---

## Key SQL Queries

```sql
-- PostgreSQL: Get or create user
INSERT INTO users (username, display_name)
VALUES ($1, $2)
ON CONFLICT (username) DO UPDATE SET last_seen = NOW()
RETURNING id;

-- PostgreSQL: Create a pending job
INSERT INTO processing_jobs
    (user_id, upload_filename, upload_size_bytes, phases_requested, lanes_requested)
VALUES ($1, $2, $3, $4::TEXT[], $5::TEXT[])
RETURNING id;

-- PostgreSQL: Mark job as running (set started_at on first transition)
UPDATE processing_jobs
SET status = 'running', started_at = COALESCE(started_at, NOW()), current_phase = $2
WHERE id = $1;

-- PostgreSQL: Mark job completed
UPDATE processing_jobs
SET status = 'completed', completed_at = NOW(), progress_pct = 100, stats_json = $2
WHERE id = $1;

-- PostgreSQL: Get events after last seen ID (for SSE polling)
SELECT id, event_type, message, data_json, created_at
FROM job_events
WHERE job_id = $1 AND id > $2
ORDER BY id ASC;

-- SQLite: Count unmatched assets (used by Phase 2 match)
SELECT COUNT(*) FROM assets
WHERE id NOT IN (SELECT DISTINCT asset_id FROM matches);

-- SQLite: Get all best matches with asset info (used by Phase 4 export)
SELECT a.path, a.ext, a.real_ext, a.is_video, a.is_fmp4, a.asset_type, a.memory_uuid,
       m.matched_date, m.matched_lat, m.matched_lon,
       m.output_subdir, m.output_filename, m.exif_tags_json
FROM matches m
JOIN assets a ON m.asset_id = a.id
WHERE m.is_best = 1
ORDER BY a.asset_type, a.filename;

-- SQLite: Asset type distribution (for progress reporting)
SELECT asset_type, COUNT(*) FROM assets GROUP BY asset_type;

-- SQLite: Verify all 14 tables exist
SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;
```

---

## Multi-User Adaptation

**SQLite is strictly per-user.** Each user gets an isolated database:
```
/data/
├── dave/
│   └── proc.db     # dave's SQLite processing database
└── shannon/
    └── proc.db     # shannon's SQLite processing database — no overlap
```

**PostgreSQL tracks shared state:**
- Job submissions (one row per user per upload)
- Event logs (SSE stream per job)
- User records (auto-provisioned from Authelia headers)

**No shared SQLite state** — all v2 single-user pipeline logic operates within its own isolated DB file per user.

**Auth flow:**
1. Traefik receives request → forwards to Authelia
2. Authelia validates session → Traefik adds `X-Remote-User` header
3. Snatched reads `X-Remote-User` → calls `get_or_create_user()` → gets `user_id`
4. All subsequent DB queries scope to that `user_id`

---

## Code Examples

### Setting up the PostgreSQL pool

```python
import asyncio
from snatched.db import get_pool, init_schema

async def startup():
    pool = await get_pool(
        postgres_url="postgresql://snatched:secret@postgres:5432/snatched",
        min_size=2,
        max_size=10,
    )
    await init_schema(pool)
    return pool

pool = asyncio.run(startup())
```

### Creating a job and emitting events

```python
from snatched.db import get_or_create_user, create_job, update_job, emit_event

async def run_pipeline(pool, username: str, upload_filename: str):
    # Auto-provision user
    user_id = await get_or_create_user(pool, username)

    # Create job record
    job_id = await create_job(
        pool, user_id,
        upload_filename=upload_filename,
        upload_size_bytes=100 * 1024 * 1024,
        phases_requested=["ingest", "match", "enrich", "export"],
        lanes_requested=["memories", "chats", "stories"],
    )

    # Mark running
    await update_job(pool, job_id, status="running", current_phase="ingest")
    await emit_event(pool, job_id, "phase_started", "Starting Phase 1: Ingest")

    # ... run ingest ...

    await emit_event(pool, job_id, "progress", "Phase 1 complete", {"assets": 1847})
    await update_job(pool, job_id, progress_pct=25, current_phase="match")

    # ... etc ...

    await update_job(pool, job_id, status="completed", stats_json={"total": 1847})
```

### Opening a per-user SQLite database

```python
from snatched.processing.sqlite import open_database, batch_insert
from pathlib import Path

# Open user's database (creates directories + schema if absent)
db = open_database(Path("/data/dave/proc.db"))

# Check WAL mode is active
journal_mode = db.execute("PRAGMA journal_mode").fetchone()[0]
assert journal_mode == "wal"

# Check foreign keys enabled
fk_enabled = db.execute("PRAGMA foreign_keys").fetchone()[0]
assert fk_enabled == 1

# Bulk insert memories
rows = [
    ("mid-001", "2026-01-15 10:30:00 UTC", "2026-01-15T10:30:00+00:00",
     "photo", None, 41.87, -87.63, "https://example.com/dl?mid=mid-001"),
    ("mid-002", "2026-01-16 14:20:00 UTC", "2026-01-16T14:20:00+00:00",
     "video", None, None, None, "https://example.com/dl?mid=mid-002"),
]
count = batch_insert(
    db, "memories",
    ["mid", "date", "date_dt", "media_type", "location_raw", "lat", "lon", "download_link"],
    rows,
)
assert count == 2
```

### Running v2→v3 migrations

```python
from snatched.processing.sqlite import open_database

# open_database() calls migrate_schema() automatically
db = open_database(Path("/data/dave/proc.db"))

# Verify migration columns exist
cols = {row[1] for row in db.execute("PRAGMA table_info(assets)").fetchall()}
assert "xmp_written" in cols
assert "xmp_path" in cols

cols = {row[1] for row in db.execute("PRAGMA table_info(matches)").fetchall()}
assert "lane" in cols

# Verify v3 tables exist
tables = {row[0] for row in db.execute(
    "SELECT name FROM sqlite_master WHERE type='table'"
).fetchall()}
assert "reprocess_log" in tables
assert "lane_config" in tables
```

---

## Acceptance Criteria

### PostgreSQL (`db.py`)

- [ ] `get_pool()` creates asyncpg pool with retry logic (3 retries, 1s delay)
- [ ] `init_schema()` creates all 3 tables (users, processing_jobs, job_events)
- [ ] `init_schema()` is idempotent — running twice does not error
- [ ] `create_user()` raises error on duplicate username
- [ ] `get_or_create_user()` returns same ID on repeated calls for same username
- [ ] `create_job()` creates job in 'pending' status linked to valid user_id
- [ ] `update_job()` sets `started_at` on first transition from 'pending'
- [ ] `update_job()` sets `completed_at` when status becomes 'completed' or 'failed'
- [ ] `emit_event()` returns a valid positive integer event_id
- [ ] `get_events_after(pool, job_id, 0)` returns all events for job
- [ ] `get_user_jobs()` returns jobs most-recent-first
- [ ] All `db.py` functions are `async`

### SQLite (`processing/sqlite.py`)

- [ ] `open_database(Path(':memory:'))` creates in-memory database without error
- [ ] `open_database()` creates parent directories if absent
- [ ] Schema creates all 14 tables (12 core + 2 v3 additions)
- [ ] All 18 indexes exist after `create_schema()`
- [ ] `PRAGMA journal_mode` = `wal` after open
- [ ] `PRAGMA foreign_keys` = `1` after open
- [ ] `assets.asset_type` CHECK constraint rejects unknown values
- [ ] `batch_insert()` with 1,100 rows uses 3 commits (500/500/100)
- [ ] `migrate_schema()` is idempotent — running twice raises no error
- [ ] `migrate_schema()` adds `xmp_written`, `xmp_path` to assets if absent
- [ ] `migrate_schema()` adds `lane` to matches if absent
- [ ] `migrate_schema()` creates `reprocess_log` and `lane_config` if absent
- [ ] Foreign key constraints work: inserting `matches` row with invalid `asset_id` fails
