# Spec 00 — Project Overview & Architecture

## Module Overview

This is the root specification for **Snatched v3.0** — a web-first multi-user Snapchat data export processor. It rewrites the 4,814-line v2 Python monolith into a modular FastAPI + htmx web application with multi-user support, background job queue, and per-user data isolation.

**Core Concept:** Users log in via Authelia, upload Snapchat export ZIPs through the browser, and the server processes them through a proven 4-phase pipeline (Ingest → Match → Enrich → Export), storing results in per-user SQLite databases.

---

## Files to Create

```
snatched/
├── app.py                   # FastAPI application factory + middleware
├── auth.py                  # Authelia header extraction + user context
├── config.py                # Pydantic Settings: server, database, pipeline config
├── models.py                # Pydantic request/response models
├── db.py                    # PostgreSQL connection pool + schema initialization
├── utils.py                 # Shared utilities: parsing, hashing, format detection
├── processing/              # Core pipeline (operates on per-user SQLite)
│   ├── __init__.py
│   ├── schema.sql           # SQLite schema definition (12 tables + v3 additions)
│   ├── sqlite.py            # Per-user SQLite open, migrate, helpers
│   ├── ingest.py            # Phase 1: Parse JSON + scan assets
│   ├── match.py             # Phase 2: 6-strategy match cascade
│   ├── enrich.py            # Phase 3: GPS, names, paths, EXIF tags
│   ├── export.py            # Phase 4: Copy, EXIF embed, overlays, chat PNG
│   ├── lanes.py             # Three-lane controller (memories/chats/stories)
│   ├── xmp.py               # XMP sidecar generation
│   ├── reprocess.py         # Reprocessing engine
│   └── chat_renderer.py     # Chat PNG rendering (Pillow)
├── jobs.py                  # Job queue: create, run, track, progress events
├── routes/                  # Web routes (htmx + JSON API)
│   ├── __init__.py
│   ├── pages.py             # HTML page routes (Jinja2)
│   ├── api.py               # JSON API endpoints
│   └── uploads.py           # File upload handling
├── templates/               # Jinja2 HTML templates
│   ├── base.html            # Base template with navigation
│   ├── landing.html         # Home / login redirect
│   ├── upload.html          # Upload form + drag-drop
│   ├── dashboard.html       # Job queue, progress, history
│   ├── results.html         # Results browser (matches, assets)
│   ├── download.html        # Download processor
│   ├── memories.html        # Memory browser (optional)
│   └── conversations.html   # Chat conversation browser (optional)
├── static/                  # Minimal static assets
│   ├── style.css            # Base styling (Pico CSS or custom)
│   └── htmx.min.js          # Only JavaScript library (~14KB)
├── cli.py                   # Optional CLI interface (admin tool)
├── main.py                  # Entry point: uvicorn startup
├── requirements.txt         # Python package dependencies
└── tests/                   # Test suite
    ├── __init__.py
    ├── test_utils.py        # Unit tests for parsing functions
    ├── test_matching.py     # Unit tests for match cascade
    └── test_ingest.py       # Unit tests for JSON parsing
```

---

## Dependencies

**Python:** 3.12+

**requirements.txt:**
```
fastapi==0.104.1
uvicorn[standard]==0.24.0
jinja2==3.1.2
python-multipart==0.0.6
asyncpg==0.29.0
pydantic==2.5.0
pydantic-settings==2.1.0
tomli==2.0.1
aiofiles==23.2.1
Pillow==10.1.0
```

**Optional (testing/dev):**
```
pytest==7.4.3
pytest-asyncio==0.21.1
httpx==0.25.1
```

**System binaries (optional — phases degrade gracefully if absent):**
- `exiftool` — EXIF embedding
- `ffmpeg` — fMP4 remux + video overlay compositing
- `magick` / `composite` (ImageMagick) — image overlay compositing

---

## V2 Source Reference

- **V2 source file:** `/home/dave/tools/snapfix/snatched.py` (4,814 lines)
- **Chat renderer source:** `/home/dave/tools/snapfix/chat_renderer.py`
- v3 is a full rewrite of v2 into a web-first multi-user architecture
- All 4 pipeline phases are preserved; the web layer, job queue, and multi-user isolation are new

---

## Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI 0.104+ |
| Frontend | Jinja2 + htmx (14KB) |
| Shared DB | PostgreSQL (users, jobs, events) |
| Per-user DB | SQLite (processing data per user) |
| Auth | Authelia via Traefik `X-Remote-User` header |
| Deployment | Docker container on `dashboard-net` (172.20.1.0/24), port 8000 internal |

---

## Coding Conventions

All v3 code follows these rules:

1. **No `print()` — use `logging` everywhere**
   ```python
   logger = logging.getLogger(__name__)
   logger.info("Starting ingest...")
   logger.warning("Asset not found: %s", path)
   ```
   Log levels: DEBUG (parsing details), INFO (phase progress), WARNING (recoverable issues), ERROR (failed asset)

2. **Type-hint all function signatures using Python 3.12 syntax (`X | None`, not `Optional[X]`)**
   ```python
   def parse_snap_date(s: str) -> datetime | None: ...
   def ingest_memories(db: sqlite3.Connection, json_dir: Path) -> int: ...
   async def handle_upload(file: UploadFile, username: str) -> dict: ...
   ```

3. **Use `pathlib.Path` everywhere, never string paths**
   ```python
   # Good
   db_path = Path(data_dir) / username / "proc.db"
   # Bad
   db_path = data_dir + "/" + username + "/proc.db"
   ```

4. **Parameterized SQL everywhere — never string interpolation**
   ```python
   # Good — SQLite
   db.execute("INSERT INTO assets (path, sha256) VALUES (?, ?)", (path, hash))
   # Good — PostgreSQL
   await pool.execute("SELECT * FROM jobs WHERE user_id = $1", user_id)
   # Bad
   db.execute(f"INSERT INTO assets VALUES ('{path}', '{hash}')")
   ```

5. **Async/await for all I/O**
   - File operations: `aiofiles.open()`
   - PostgreSQL queries: `asyncpg`
   - Streaming responses: `FastAPI.StreamingResponse`

6. **Configuration via Pydantic Settings**
   - TOML file → built-in defaults
   - No globals (except `logger`)
   - Dependency injection for config

7. **Error handling**
   - Structured logging: `logger.exception("Phase failed", exc_info=True)`
   - Graceful degradation: missing optional JSON files = warn, not crash
   - Job status tracks failures in PostgreSQL
   - No `sys.exit()` — raise exceptions, let callers handle

---

## Complete v2→v3 Function Mapping

Maps every function in v2 `/home/dave/tools/snapfix/snatched.py` (4,814 lines) to its v3 module:

### Constants & Configuration (Lines 41–64)

| Symbol | V2 Line | V3 Module | Notes |
|--------|---------|-----------|-------|
| `VERSION` | 41 | `config.py` | `__version__ = "3.0"` |
| `INPUT_BASE` | 42 | Removed | v2 hardcoded path; v3 uses `/data/{user}/uploads/` |
| `OUTPUT_BASE` | 43 | Removed | v2 hardcoded path; v3 uses `/data/{user}/output/` |
| `MEMORY_RE` | 45 | `utils.py` | Preserved exactly: memory filename regex |
| `CHAT_FILE_RE` | 47 | `utils.py` | Preserved exactly: chat filename regex |
| `LOCATION_RE` | 48 | `utils.py` | Preserved exactly: GPS coordinate regex |
| `VIDEO_EXTS` | 51 | `utils.py` | Preserved exactly: video extension set |
| `GPS_WINDOW` | 52 | `config.py` | `gps_window_seconds = 300` (parameter) |
| `UUID_RE` | 53 | `utils.py` | Preserved exactly: UUID validation regex |
| `RIFF_MAGIC` | 56 | `utils.py` | Preserved exactly: magic bytes |
| `FMP4_STYP` | 57 | `utils.py` | Preserved exactly: magic bytes |
| `BATCH_SIZE` | 59 | `config.py` | `batch_size = 500` (parameter) |
| `UNSAFE_FILENAME_RE` | 62 | `utils.py` | Preserved exactly: filename sanitizer |

### Utility Functions (Lines 88–268)

| Function | V2 Line | V3 Module | Status |
|----------|---------|-----------|--------|
| `die(msg)` | 88 | Removed | v3 uses exceptions + structured logging |
| `warn(msg)` | 94 | `utils.py` → `logger.warning()` | Replaced with logging |
| `is_video(path)` | 98 | `utils.py` | Preserved |
| `parse_snap_date(s)` | 102 | `utils.py` | Preserved; signature: `(s: str) -> datetime \| None` |
| `parse_snap_date_iso(s)` | 113 | `utils.py` | Preserved; signature: `(s: str) -> str \| None` |
| `parse_snap_date_dateonly(s)` | 120 | `utils.py` | Preserved; signature: `(s: str) -> str \| None` |
| `parse_location(s)` | 129 | `utils.py` | Preserved; signature: `(s: str) -> tuple[float, float] \| None` |
| `extract_mid(url)` | 142 | `utils.py` | Preserved; signature: `(url: str) -> str \| None` |
| `detect_real_format(path)` | 152 | `utils.py` | Preserved; signature: `(path: Path) -> str \| None` |
| `is_fragmented_mp4(path)` | 167 | `utils.py` | Preserved; signature: `(path: Path) -> bool` |
| `sha256_file(path)` | 177 | `utils.py` | Preserved; signature: `(path: Path) -> str` |
| `sanitize_filename(name)` | 189 | `utils.py` | Preserved; signature: `(name: str) -> str` |
| `parse_iso_dt(s)` | 202 | `utils.py` | Preserved; signature: `(s: str) -> datetime \| None` |
| `exif_dt(dt)` | 214 | `utils.py` | Preserved; signature: `(dt: datetime) -> str` |
| `gps_tags(lat, lon, vid, dt)` | 219 | `processing/xmp.py` | Moved to XMP module |
| `date_tags(dt, vid, subsec_ms)` | 239 | `processing/xmp.py` | Moved to XMP module |
| `_format_chat_date(s)` | 263 | `utils.py` | Preserved as `format_chat_date()` |
| **NEW** | — | `utils.py` | `safe_user_path(base_dir, user_path)` — path traversal prevention |

### Schema Functions (Lines 274–498)

| Item | V2 Line | V3 Module | Status |
|------|---------|-----------|--------|
| `SCHEMA_SQL` | 272 | `processing/schema.sql` | Moved to separate file, additions for v3 |
| `create_schema(db)` | 474 | `processing/sqlite.py` | `def open_database(db_path: Path) -> sqlite3.Connection` |

### Phase 1: Ingest (Lines 503–1247)

| Function | V2 Line | V3 Module | Status |
|----------|---------|-----------|--------|
| `ingest_memories(db, json_dir)` | 503 | `processing/ingest.py` | Preserved; signature: `(db: Connection, json_dir: Path) -> int` |
| `ingest_chat(db, json_dir)` | 562 | `processing/ingest.py` | Preserved; signature: `(db: Connection, json_dir: Path) -> int` |
| `ingest_snaps(db, json_dir)` | 662 | `processing/ingest.py` | Preserved; signature: `(db: Connection, json_dir: Path) -> int` |
| `ingest_stories(db, json_dir)` | 738 | `processing/ingest.py` | Preserved; signature: `(db: Connection, json_dir: Path) -> int` |
| `ingest_friends(db, json_dir)` | 776 | `processing/ingest.py` | Preserved; signature: `(db: Connection, json_dir: Path) -> int` |
| `ingest_locations(db, json_dir)` | 840 | `processing/ingest.py` | Preserved; signature: `(db: Connection, json_dir: Path) -> int` |
| `ingest_places(db, json_dir)` | 922 | `processing/ingest.py` | Preserved; signature: `(db: Connection, json_dir: Path) -> int` |
| `ingest_snap_pro(db, json_dir)` | 1004 | `processing/ingest.py` | Preserved; signature: `(db: Connection, json_dir: Path) -> int` |
| `scan_assets(db, input_dir, ...)` | 1052 | `processing/ingest.py` | Preserved; signature: `(db: Connection, input_dir: Path) -> int` |
| `phase1_ingest(db, input_dir, json_dir, args)` | 1200 | `processing/ingest.py` | Refactored: `def phase1_ingest(db: Connection, input_dir: Path, json_dir: Path, config: dict | None, progress_cb: Callable | None) -> dict[str, int]` |

### Phase 2: Match (Lines 1249–1647)

| Function | V2 Line | V3 Module | Status |
|----------|---------|-----------|--------|
| `_matched_asset_ids(db)` | 1251 | `processing/match.py` | Preserved |
| `_strategy1_exact_media_id(db)` | 1257 | `processing/match.py` | Preserved; confidence 1.0 |
| `_strategy2_memory_uuid(db)` | 1277 | `processing/match.py` | Preserved; confidence 1.0 |
| `_strategy3_story_id(db)` | 1299 | `processing/match.py` | Preserved; confidence 0.9 or 0.5 |
| `_strategy4_timestamp_type(db)` | 1353 | `processing/match.py` | Preserved; confidence 0.8 |
| `_strategy5_date_type_count(db)` | 1391 | `processing/match.py` | Preserved; confidence 0.7 |
| `_strategy6_date_only(db)` | 1443 | `processing/match.py` | Preserved; confidence 0.3 |
| `_match_overlay_and_media_zips(db)` | 1462 | `processing/match.py` | Preserved; confidence 0.9 |
| `_set_best_matches(db)` | 1517 | `processing/match.py` | Preserved |
| `phase2_match(db)` | 1558 | `processing/match.py` | Preserved: `def phase2_match(db: Connection, progress_cb: Callable | None) -> dict[str, Any]` |

### Phase 3: Enrich (Lines 1650–2288)

| Function | V2 Line | V3 Module | Status |
|----------|---------|-----------|--------|
| `_load_location_timeline(db)` | 1652 | `processing/enrich.py` | Preserved |
| `_find_nearest_location(...)` | 1667 | `processing/enrich.py` | Preserved |
| `enrich_gps(db, ...)` | 1686 | `processing/enrich.py` | Preserved |
| `_resolve_conversation_name(...)` | 1769 | `processing/enrich.py` | Preserved |
| `_build_chat_folder_map(db)` | 1794 | `processing/enrich.py` | Preserved |
| `enrich_display_names(db)` | 1918 | `processing/enrich.py` | Preserved |
| `enrich_output_paths(db)` | 1997 | `processing/enrich.py` | Preserved |
| `enrich_exif_tags(db)` | 2116 | `processing/enrich.py` | Preserved |
| `phase3_enrich(db, project_dir, args)` | 2236 | `processing/enrich.py` | Refactored: `def phase3_enrich(db: Connection, project_dir: Path, config: Config, progress_cb: Callable | None) -> dict` |

### Phase 4: Export (Lines 2291–3457)

| Function | V2 Line | V3 Module | Status |
|----------|---------|-----------|--------|
| `_copy_files(db, project_dir, args)` | 2293 | `processing/export.py` | Preserved as `copy_files()` |
| `_write_exif(db, project_dir, args)` | 2448 | `processing/export.py` | Preserved as `write_exif()` |
| `_burn_overlays(db, project_dir, args)` | 2592 | `processing/export.py` | Preserved as `burn_overlays()` |
| `_export_text(db, project_dir, args)` | 2710 | `processing/export.py` | Preserved as `export_chat_text()` + `export_chat_png()` |
| `_write_reports(db, project_dir, args, stats)` | 3007 | `processing/export.py` | Preserved as `write_reports()` |
| `phase4_export(db, project_dir, args)` | 3370 | `processing/export.py` | Refactored: `def phase4_export(db: Connection, project_dir: Path, config: Config, lanes: list[str] | None, progress_cb: Callable | None) -> dict` |

### CLI & Discovery (Lines 3460–3773)

| Function | V2 Line | V3 Module | Status |
|----------|---------|-----------|--------|
| `parse_args(argv)` | 3462 | `cli.py` | CLI module (admin tool, not primary) |
| `extract_zips(input_path, scratch_dir, ...)` | 3534 | `routes/uploads.py` | `async def extract_upload_zip(zip_path: Path, dest_dir: Path) -> None` |
| `discover_export(base_dir)` | 3590 | `processing/ingest.py` | `def discover_export(base_dir: Path) -> dict | None` |
| `list_exports(root)` | 3695 | `processing/ingest.py` | `def list_exports(root: Path) -> list[dict]` |

### Guided Mode & Banner (Lines 3776–4404)

| Function | V2 Line | V3 Module | Status |
|----------|---------|-----------|--------|
| `guided_mode()` | 3778 | Removed | v3 is web-first; no CLI wizard |
| `print_banner(db, elapsed, project_dir, ...)` | 4140 | `routes/api.py` | Results endpoint: `GET /api/jobs/{id}/report` |

### Subcommand Handlers (Lines 4407–4514)

| Function | V2 Line | V3 Module | Status |
|----------|---------|-----------|--------|
| `handle_query(args)` | 4409 | `cli.py` | `snatched query --user dave "SELECT ..."` |
| `handle_stats(args)` | 4448 | `routes/api.py` | `GET /api/jobs/{id}/stats` |
| `handle_chat(args)` | 4473 | `jobs.py` | Re-render via reprocessing engine |

### Main Entry (Lines 4516–4814)

| Function | V2 Line | V3 Module | Status |
|----------|---------|-----------|--------|
| `progress(cur, total, t0, ...)` | 4521 | `jobs.py` | Progress callbacks to SSE events |
| `open_database(db_path)` | 4553 | `processing/sqlite.py` | `def open_database(db_path: Path) -> Connection` |
| `main()` | 4579 | `main.py` | FastAPI app + uvicorn |

---

## Database Schema

### Two-Database Architecture

**PostgreSQL** (`snatched/db.py`) — Shared application state:
```sql
-- users: Application users (created on first auth)
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    display_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen TIMESTAMPTZ,
    storage_quota_bytes BIGINT NOT NULL DEFAULT 10737418240
);

-- processing_jobs: Per-user job submissions
CREATE TABLE IF NOT EXISTS processing_jobs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending', 'running', 'completed', 'failed')),
    upload_filename TEXT,
    upload_size_bytes BIGINT,
    phases_requested TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    lanes_requested TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    progress_pct INTEGER NOT NULL DEFAULT 0 CHECK(progress_pct >= 0 AND progress_pct <= 100),
    current_phase TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    stats_json JSONB
);

-- job_events: Event log (SSE / polling source)
CREATE TABLE IF NOT EXISTS job_events (
    id SERIAL PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES processing_jobs(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    message TEXT,
    data_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**SQLite** (`/data/{username}/proc.db`) — Per-user processing data. Full DDL in `snatched/processing/schema.sql`. 12 core tables: `assets`, `chat_messages`, `chat_media_ids`, `snap_messages`, `memories`, `stories`, `snap_pro`, `friends`, `locations`, `places`, `matches`, `run_log`. Plus 2 v3 additions: `reprocess_log`, `lane_config`.

---

## Key SQL Queries

```sql
-- Check user exists (PostgreSQL)
SELECT id FROM users WHERE username = $1;

-- Get user's recent jobs (PostgreSQL)
SELECT id, status, upload_filename, progress_pct, created_at
FROM processing_jobs WHERE user_id = $1 ORDER BY created_at DESC LIMIT 20;

-- Count matched assets per strategy (SQLite)
SELECT strategy, COUNT(*) as count, AVG(confidence) as avg_conf
FROM matches GROUP BY strategy ORDER BY count DESC;

-- Get best matches for export (SQLite)
SELECT a.path, m.matched_date, m.matched_lat, m.matched_lon,
       m.output_subdir, m.output_filename, m.exif_tags_json
FROM matches m JOIN assets a ON m.asset_id = a.id
WHERE m.is_best = 1 ORDER BY a.asset_type, a.filename;
```

---

## Multi-User Adaptation

v2 is single-user with hardcoded paths. v3 key adaptations:

| v2 | v3 |
|----|-----|
| `INPUT_BASE = Path("/mnt/nas-pool/snapchat-input")` | `/data/{username}/uploads/` |
| `OUTPUT_BASE = Path("/mnt/nas-pool/snapchat-output")` | `/data/{username}/output/` |
| Single SQLite at hardcoded path | Per-user SQLite at `/data/{username}/proc.db` |
| `print()` for progress | `progress_cb: Callable | None` callback |
| `sys.exit()` on error | Raise exceptions, job status → `failed` |
| CLI wizard (`guided_mode`) | Web UI (FastAPI + htmx) |

Path isolation enforced by `safe_user_path()`:
```python
user_db = safe_user_path(Path("/data"), f"{username}/proc.db")
# Returns /data/dave/proc.db — raises ValueError if "../etc/passwd"
```

---

## Docker Deployment

**Image Building:**
- Base: `python:3.12-slim`
- WORKDIR: `/app`
- Expose: 8000 (internal port)
- Run as non-root (`appuser:appuser`)

**Health Check Endpoint:**
```python
@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "3.0"}
```

**Network:**
- Connected to: `dashboard-net` (172.20.1.0/24)
- Routed via Traefik
- Protected by Authelia 2FA via Traefik `X-Remote-User` header

**Data Mounts:**
- `/data/` → persistent user data (uploads, processing, output, SQLite DBs)
- `/app/` → read-only application code

---

## Module Dependency Graph

```
FOUNDATION MODULES (No processing dependencies)
  config.py ────┐
  auth.py       │
  models.py     ├──→ All other modules depend on these
  utils.py      │
  db.py ────────┘
  app.py
         │
         ▼
PROCESSING MODULES (per-user SQLite layer)
  processing/schema.sql ──┐
  processing/sqlite.py    ├──→ Open + migrate user DB

  processing/ingest.py  (Phase 1) ──┐
  processing/match.py   (Phase 2)   ├──→ Pipeline phases
  processing/enrich.py  (Phase 3)   │
  processing/export.py  (Phase 4)   │
                                    │
  processing/lanes.py  ─────────────┤
  processing/xmp.py    ─────────────┤
  processing/reprocess.py ──────────┤
  processing/chat_renderer.py ──────┘
         │
         ▼
WEB APPLICATION MODULES
  jobs.py ─────────────────┐
  (Orchestrates pipeline)  ├──→ Coordinate all modules
  routes/pages.py (HTML)   │
  routes/api.py (JSON)     │
  routes/uploads.py ───────┘
             │
             ▼
      app.py + main.py
         │
         ▼
OPTIONAL
  cli.py ──→ Admin CLI tool
  tests/  ──→ Unit test suite
```

---

## Configuration Precedence

Configuration layered (highest → lowest priority):

1. **Per-user PostgreSQL overrides** — user-specific settings in `user_preferences` table
2. **Server config file** — `/app/snatched.toml` (admin-managed)
3. **Built-in defaults** — hardcoded in `config.py`

No environment variables, no CLI flags (web-first).

---

## Build Specifications Index

Each spec is **self-contained** and buildable independently. Dependency order:

```
Spec 00 (this document — read first)
  └── Spec 01: Foundation
        ├── utils.py, config.py, models.py, processing/sqlite.py, processing/schema.sql
  └── Spec 02: Database Layer
        ├── db.py (PostgreSQL), processing/sqlite.py (per-user SQLite)
  └── Spec 03: Phase 1 — Ingest
        ├── processing/ingest.py
  └── Spec 04: Phase 2 — Match
        ├── processing/match.py
  └── Spec 05: Phase 3 + 4 — Enrich + Export + XMP
        ├── processing/enrich.py, processing/export.py, processing/xmp.py
```

An AI reading **Spec 01** has all it needs to build the foundation layer.
An AI reading **Spec 03** (with Spec 01+02 built) has all it needs to build Phase 1.
And so on.

---

## Acceptance Criteria

- [ ] Full project directory tree matches the layout above
- [ ] `requirements.txt` lists all packages at pinned versions
- [ ] `snatched/` module prefix used consistently across all files
- [ ] Two-database architecture implemented: PostgreSQL (shared) + per-user SQLite
- [ ] Auth via `X-Remote-User` header — zero auth code inside Snatched
- [ ] All pipeline functions accept `progress_cb: Callable | None` for web UI updates
- [ ] `safe_user_path()` enforced at all user-supplied path boundaries
- [ ] Docker container runs as non-root user on port 8000
- [ ] `/api/health` endpoint returns `{"status": "ok", "version": "3.0"}`
