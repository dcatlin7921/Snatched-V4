# Snatched v3.0 — Architecture & Requirements Plan (v2)

> **Version:** 3.0 (Plan v2 — Post-Debate Revision)
> **Date:** 2026-02-23
> **Authors:** Dave + Claude (Opus)
> **Status:** PRE-DEVELOPMENT — Non-destructive. v2.0 remains the running system.
> **Revision Notes:** Incorporates findings from two rounds of 5-agent architecture debate. Key shifts: web-first multi-user app (not CLI tool), FastAPI + htmx, Authelia auth delegation, hybrid two-tier database, vibe-coded (build order irrelevant).

---

## Table of Contents

- [1. Vision](#1-vision)
- [2. V2 Codebase Audit](#2-v2-codebase-audit) *(unchanged from v1)*
- [3. V3 Architecture](#3-v3-architecture)
  - [3.1 System Overview](#31-system-overview)
  - [3.2 Module Decomposition](#32-module-decomposition)
  - [3.3 Two-Tier Database Architecture](#33-two-tier-database-architecture)
  - [3.4 Authentication & Multi-User](#34-authentication--multi-user)
  - [3.5 Upload & Job Queue](#35-upload--job-queue)
  - [3.6 Three-Lane Export System](#36-three-lane-export-system)
  - [3.7 Reprocessing Engine](#37-reprocessing-engine)
  - [3.8 XMP Sidecar System](#38-xmp-sidecar-system)
  - [3.9 Web Application](#39-web-application)
  - [3.10 Configuration System](#310-configuration-system)
  - [3.11 CLI (Secondary)](#311-cli-secondary)
- [4. Module Specifications](#4-module-specifications)
- [5. Requirements](#5-requirements)
- [6. Migration Strategy](#6-migration-strategy)
- [7. Security Considerations](#7-security-considerations)
- [8. Open Questions](#8-open-questions)

---

## 1. Vision

Snatched v3.0 is a **web-first, multi-user Snapchat data export processor** hosted on Dave's server. Users log in through a browser, upload their Snapchat data export, and the server processes it — matching media files to metadata, enriching with GPS and display names, embedding EXIF data, and organizing output.

The 4,814-line v2 monolith is decomposed into focused modules. The proven 4-phase pipeline (Ingest → Match → Enrich → Export) and 6-strategy match cascade are preserved. Everything else is rebuilt for multi-user web access.

**What's New in v3:**
- **Web-first** — Browser is the primary interface, not CLI
- **Multi-user** — Multiple people log in to process their own exports
- **Upload pipeline** — Users upload ZIP exports through the browser
- **Job queue** — Background processing with real-time progress via SSE
- **Authelia integration** — Leverages Dave's existing Traefik + Authelia stack
- **Hybrid database** — Per-user SQLite (processing) + shared PostgreSQL (app state)
- **Reprocessing** — Re-run any phase without re-extracting or re-ingesting
- **XMP sidecars** — Non-destructive metadata files (shipped disabled, code ready)
- **Three export lanes** — Memories, Stories, Chats as independent pipelines

**What's Preserved:**
- SQLite-first processing architecture (per-user)
- 6-strategy match cascade with confidence scores
- 4-phase pipeline (Ingest → Match → Enrich → Export)
- SHA-256 checksums and audit trail
- exiftool stay_open batch mode
- Chat PNG rendering (Pillow)
- Format detection (WebP-as-PNG, fMP4)
- Overlay burning (ImageMagick + ffmpeg)

**What's Gone:**
- CLI as primary interface (retained as optional admin tool)
- Guided wizard (replaced by web upload flow)
- Terminal art / banner (processing status moves to web dashboard)
- Hardcoded single-user paths
- Zero-dependency constraint (web app needs FastAPI, Jinja2, etc.)
- 5-layer config precedence (simplified to 3)

---

## 2. V2 Codebase Audit

*(Unchanged from Plan v1 — see sections 2.1 through 2.6 in SNATCHED-V3-PLAN-v1-RESTORED.md)*

---

## 3. V3 Architecture

### 3.1 System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     BROWSER (User)                          │
│   Upload ZIP → Dashboard → Results → Download               │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTPS
┌──────────────────────┼──────────────────────────────────────┐
│  TRAEFIK             │                                      │
│  ┌───────────────────┼───────────────────────────────────┐  │
│  │  AUTHELIA (2FA)   │                                   │  │
│  │  X-Remote-User →  │                                   │  │
│  └───────────────────┼───────────────────────────────────┘  │
│                      ▼                                      │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  SNATCHED (FastAPI)                                   │  │
│  │                                                       │  │
│  │  ┌─────────┐  ┌──────────┐  ┌───────────────────┐    │  │
│  │  │ Web     │  │ Job      │  │ Processing Engine │    │  │
│  │  │ Routes  │  │ Queue    │  │ (4-phase pipeline)│    │  │
│  │  │ + htmx  │  │          │  │                   │    │  │
│  │  └────┬────┘  └────┬─────┘  └────────┬──────────┘    │  │
│  │       │            │                 │                │  │
│  │  ┌────┴────────────┴─────────────────┴────────────┐   │  │
│  │  │              DATA LAYER                        │   │  │
│  │  │  ┌──────────────┐  ┌─────────────────────┐    │   │  │
│  │  │  │ PostgreSQL   │  │ Per-User SQLite DBs  │    │   │  │
│  │  │  │ (shared)     │  │ /data/{user}/proc.db │    │   │  │
│  │  │  │ users, jobs  │  │ assets, matches, etc │    │   │  │
│  │  │  └──────────────┘  └─────────────────────┘    │   │  │
│  │  └────────────────────────────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  STORAGE                                              │  │
│  │  /data/{user}/uploads/    ← uploaded ZIPs             │  │
│  │  /data/{user}/processing/ ← extracted + working       │  │
│  │  /data/{user}/output/     ← final export              │  │
│  │  /data/{user}/proc.db     ← user's SQLite DB          │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Module Decomposition

```
snatched/
├── app.py               # FastAPI app factory, middleware, lifespan
├── config.py            # Configuration: server + per-user defaults
├── auth.py              # Authelia header extraction + user context
├── models.py            # Pydantic models (request/response schemas)
├── db.py                # PostgreSQL connection (shared app state)
├── processing/          # Core pipeline (operates on per-user SQLite)
│   ├── __init__.py
│   ├── schema.sql       # SQLite schema (12 tables + v3 additions)
│   ├── sqlite.py        # Per-user SQLite open, migrate, helpers
│   ├── ingest.py        # Phase 1: Parse JSON + scan assets
│   ├── match.py         # Phase 2: 6-strategy match cascade
│   ├── enrich.py        # Phase 3: GPS, names, paths, EXIF tags
│   ├── export.py        # Phase 4: Copy, EXIF embed, overlays, chat
│   ├── lanes.py         # Three-lane controller
│   ├── xmp.py           # XMP sidecar generation
│   ├── reprocess.py     # Reprocessing engine
│   └── chat_renderer.py # Chat PNG rendering (Pillow)
├── jobs.py              # Job queue: create, run, track, SSE progress
├── routes/              # Web routes (htmx + JSON API)
│   ├── __init__.py
│   ├── pages.py         # HTML page routes (Jinja2 + htmx)
│   ├── api.py           # JSON API endpoints
│   └── uploads.py       # File upload handling
├── templates/           # Jinja2 HTML templates
│   ├── base.html
│   ├── login.html       # Landing / login redirect
│   ├── upload.html      # Upload page
│   ├── dashboard.html   # Job status + history
│   ├── results.html     # Results browser (matches, assets)
│   ├── download.html    # Download page
│   ├── memories.html    # Memory browser (optional)
│   └── conversations.html # Chat browser (optional)
├── static/              # CSS, JS (minimal — htmx handles interactivity)
│   ├── style.css
│   └── htmx.min.js      # ~14KB, only JS dependency
├── utils.py             # Shared utilities: parsing, hashing, formats
├── cli.py               # Optional CLI interface (admin tool)
└── tests/               # Test suite
```

### 3.3 Two-Tier Database Architecture

The debate produced strong consensus for a hybrid approach:

#### Shared PostgreSQL (App State)

Stores data that spans all users and the application itself. Can reuse Dave's existing `memory-store` PostgreSQL instance (172.20.6.10) or a dedicated instance.

```sql
-- Users (populated from Authelia, not managed by Snatched)
CREATE TABLE users (
    id          SERIAL PRIMARY KEY,
    username    TEXT UNIQUE NOT NULL,      -- from X-Remote-User header
    display_name TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    last_seen   TIMESTAMPTZ,
    storage_quota_bytes BIGINT DEFAULT 10737418240  -- 10GB default
);

-- Processing Jobs
CREATE TABLE processing_jobs (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id),
    status      TEXT NOT NULL DEFAULT 'pending',  -- pending/running/completed/failed
    upload_filename TEXT,
    upload_size_bytes BIGINT,
    phases_requested TEXT[],                       -- {'ingest','match','enrich','export'}
    lanes_requested TEXT[],                        -- {'memories','chats','stories'}
    progress_pct INTEGER DEFAULT 0,
    current_phase TEXT,
    error_message TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    started_at  TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    stats_json  JSONB                             -- final run stats
);

-- Job Events (for SSE streaming)
CREATE TABLE job_events (
    id          SERIAL PRIMARY KEY,
    job_id      INTEGER REFERENCES processing_jobs(id),
    event_type  TEXT NOT NULL,                    -- phase_start/progress/match/error/complete
    message     TEXT,
    data_json   JSONB,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
```

#### Per-User SQLite (Processing Data)

Each user gets their own SQLite database at `/data/{username}/proc.db`. This preserves full v2 compatibility — the 12-table schema, match cascade, enrichment pipeline all work identically. SQLite files are portable, debuggable, and can be downloaded by the user.

The v2 schema is preserved exactly, with v3 additions:
- `matches.lane` column (TEXT: 'memories', 'chats', 'stories')
- `assets.xmp_written` (BOOLEAN DEFAULT 0)
- `assets.xmp_path` (TEXT)
- `reprocess_log` table
- `lane_config` table

**Why hybrid?**
- PostgreSQL handles concurrent web requests, job tracking, user management
- SQLite handles per-user processing (proven architecture, v2 compatible, portable)
- Users could theoretically download their SQLite DB and run queries locally
- No risk of cross-user data leakage — each user's processing is physically isolated

### 3.4 Authentication & Multi-User

Snatched delegates ALL authentication to Authelia via Traefik. Zero auth code in Snatched itself.

```
Request Flow:
  Browser → Traefik → Authelia (2FA check) → Snatched
                                               ↓
                                    X-Remote-User: dave
                                    X-Remote-Email: dave@example.com
                                    X-Remote-Groups: admin,users
```

#### auth.py — Header Extraction

```python
from fastapi import Request, HTTPException

async def get_current_user(request: Request) -> str:
    """Extract authenticated user from Authelia headers."""
    username = request.headers.get("X-Remote-User")
    if not username:
        raise HTTPException(401, "Not authenticated")
    return username

async def get_user_groups(request: Request) -> list[str]:
    """Extract user groups from Authelia headers."""
    groups = request.headers.get("X-Remote-Groups", "")
    return [g.strip() for g in groups.split(",") if g.strip()]
```

#### User Data Isolation

Each user's data lives in a sandboxed directory:

```
/data/
├── dave/
│   ├── uploads/           # Raw uploaded ZIPs
│   ├── processing/        # Extracted exports (working dir)
│   ├── output/            # Final processed output
│   │   ├── memories/
│   │   ├── chat/
│   │   └── stories/
│   └── proc.db            # User's SQLite processing DB
├── shannon/
│   ├── uploads/
│   ├── processing/
│   ├── output/
│   └── proc.db
└── ...
```

Path traversal prevention: all file paths are resolved relative to user's directory and validated against it. No `../` escapes.

#### Standalone Dev Mode

For local development without Traefik/Authelia, a simple JWT fallback:

```python
# When SNATCHED_DEV_MODE=1, bypass Authelia headers
# Use simple login form → JWT cookie
# NEVER in production
```

### 3.5 Upload & Job Queue

#### Upload Flow

1. User navigates to Upload page
2. Selects Snapchat export ZIP file (or folder of ZIPs)
3. htmx streams upload progress via `hx-post` with progress indicator
4. Server validates: file type, size limit, available quota
5. ZIP stored to `/data/{user}/uploads/`
6. Job created in PostgreSQL → returns job ID
7. User redirected to Dashboard showing job progress

#### Job Processing

```python
# jobs.py — Background processing
async def run_job(job_id: int, username: str):
    """Execute processing pipeline as background task."""
    db_path = f"/data/{username}/proc.db"
    job = await get_job(job_id)

    try:
        await update_job(job_id, status="running", started_at=now())

        # Phase 1: Ingest
        await emit_event(job_id, "phase_start", "Ingesting export data...")
        sqlite_db = open_database(db_path)
        phase1_ingest(sqlite_db, input_dir, json_dir, config)
        await update_job(job_id, current_phase="ingest", progress_pct=25)

        # Phase 2: Match
        await emit_event(job_id, "phase_start", "Running match cascade...")
        phase2_match(sqlite_db)
        await update_job(job_id, current_phase="match", progress_pct=50)

        # Phase 3: Enrich
        await emit_event(job_id, "phase_start", "Enriching metadata...")
        phase3_enrich(sqlite_db, project_dir, config)
        await update_job(job_id, current_phase="enrich", progress_pct=75)

        # Phase 4: Export
        await emit_event(job_id, "phase_start", "Exporting files...")
        phase4_export(sqlite_db, project_dir, config, lanes)
        await update_job(job_id, status="completed", progress_pct=100)

    except Exception as e:
        await update_job(job_id, status="failed", error_message=str(e))
```

#### SSE Progress Streaming

```python
# routes/api.py
@router.get("/api/jobs/{job_id}/stream")
async def job_stream(job_id: int, username: str = Depends(get_current_user)):
    """Server-Sent Events stream for job progress."""
    async def event_generator():
        last_id = 0
        while True:
            events = await get_events_after(job_id, last_id)
            for event in events:
                yield f"event: {event.event_type}\ndata: {event.message}\n\n"
                last_id = event.id
            if await is_job_complete(job_id):
                yield f"event: complete\ndata: done\n\n"
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

### 3.6 Three-Lane Export System

*(Preserved from v1 — each lane operates independently, sharing the per-user SQLite database)*

```
                    ┌─────────────────────────────┐
                    │   SHARED CORE               │
                    │   ┌─────────┐ ┌──────────┐  │
                    │   │ Ingest  │ │  Match   │  │
                    │   └────┬────┘ └────┬─────┘  │
                    │        │           │         │
                    │   ┌────┴───────────┴─────┐  │
                    │   │   Per-User SQLite DB  │  │
                    │   └────┬────────┬────┬────┘  │
                    └────────┼────────┼────┼───────┘
                             │        │    │
              ┌──────────────┤        │    ├──────────────┐
              ▼              ▼        │    ▼              │
    ┌─────────────────┐ ┌────────────┴┐ ┌──────────────┐ │
    │  MEMORIES LANE  │ │ CHATS LANE  │ │ STORIES LANE │ │
    │                 │ │             │ │              │ │
    │ • Enrich GPS    │ │ • Enrich    │ │ • Enrich     │ │
    │ • Burn overlays │ │   names     │ │   dates      │ │
    │ • EXIF embed    │ │ • Text      │ │ • EXIF embed │ │
    │ • XMP sidecars  │ │   export    │ │ • XMP        │ │
    │ • Year/Month    │ │ • PNG       │ │   sidecars   │ │
    │   folder org    │ │   render    │ │ • Flat folder│ │
    │                 │ │ • EXIF      │ │   org        │ │
    │                 │ │ • XMP       │ │              │ │
    └─────────────────┘ └─────────────┘ └──────────────┘
```

#### Lane-Specific Behavior

| Feature | Memories Lane | Chats Lane | Stories Lane |
|---------|:-------------:|:----------:|:------------:|
| GPS enrichment | Yes | No | No |
| Overlay burning | Yes | No | No |
| Display name resolution | No | Yes | No |
| Text transcript export | No | Yes | No |
| PNG chat rendering | No | Yes | No |
| EXIF embedding | Yes | Yes | Yes |
| XMP sidecars | Yes | Yes | Yes |
| Folder structure | `memories/{YYYY}/{MM}/` | `chat/{ConvName}/` | `stories/` |
| fMP4 remuxing | Yes | Yes | Yes |

### 3.7 Reprocessing Engine

Re-run any phase without re-extracting ZIPs or re-ingesting raw data. In the web UI, reprocessing is triggered from the Dashboard page with checkboxes for phases and lanes.

#### Reprocess Modes

| Mode | What It Does | Use Case |
|------|-------------|----------|
| `match` | Clear matches, re-run Phase 2 | Tweaked matching strategy |
| `enrich` | Re-run Phase 3 from existing matches | Changed GPS window |
| `export` | Re-run Phase 4 from existing enrichment | Changed output paths |
| `chat` | Re-render chat exports only | Changed theme or format |
| `xmp` | Regenerate XMP sidecars only | Changed XMP template |
| `lane <name>` | Re-run a specific lane | Lane config changed |
| `all` | Re-run Phases 2-4 | Full re-process |

### 3.8 XMP Sidecar System

*(Preserved from v1 — code implemented, shipped disabled by default)*

XMP sidecars generate `.xmp` files alongside each exported media file. Immich, Lightroom, and darktable all support sidecar import. The code is built and tested but `xmp_enabled` defaults to `false` — users opt in when ready.

See Plan v1 sections 3.4 for full XMP format, namespace rules, and expanded tag set.

Key settings:

| Setting | Default | Description |
|---------|---------|-------------|
| `xmp_enabled` | `false` | Generate XMP sidecars |
| `xmp_alongside_exif` | `true` | Sidecars even when EXIF embedded |
| `xmp_only` | `false` | Sidecars instead of EXIF |
| `xmp_include_snatched_ns` | `true` | Include `snatched:*` metadata |

### 3.9 Web Application

#### Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **Backend** | FastAPI | Async (needed for uploads + SSE), Pydantic validation, auto OpenAPI docs |
| **Frontend** | htmx + Jinja2 | Server-rendered, no SPA, no build step, 14KB JS total |
| **Styling** | Simple CSS (or Pico CSS) | Minimal, classless where possible |
| **Auth** | Authelia delegation | Already running on Dave's server, zero auth code in Snatched |
| **Progress** | Server-Sent Events | Native browser support, FastAPI async generators |

#### Pages (5-7 MVP)

| Page | URL | Description |
|------|-----|-------------|
| Landing | `/` | Welcome + login redirect (if not authenticated) |
| Upload | `/upload` | Drag-drop or browse for Snapchat export ZIP |
| Dashboard | `/dashboard` | Active jobs, progress bars, history |
| Results | `/results` | Browse processed output: matches, assets, stats |
| Download | `/download` | Download processed files (ZIP or individual) |
| Memories | `/memories` | Memory browser by year/month *(optional v3.0)* |
| Conversations | `/conversations` | Chat conversation browser *(optional v3.0)* |

#### htmx Patterns

The frontend uses htmx for all interactivity. No custom JavaScript required.

```html
<!-- Upload with progress -->
<form hx-post="/upload" hx-encoding="multipart/form-data"
      hx-target="#upload-status" hx-indicator="#spinner">
  <input type="file" name="export_zip" accept=".zip">
  <button type="submit">Process Export</button>
  <div id="spinner" class="htmx-indicator">Uploading...</div>
</form>
<div id="upload-status"></div>

<!-- Live job progress via SSE -->
<div hx-ext="sse" sse-connect="/api/jobs/{{job_id}}/stream">
  <div sse-swap="progress" hx-swap="innerHTML">
    Waiting for updates...
  </div>
</div>

<!-- Results table with pagination -->
<div hx-get="/results/matches?page=1" hx-trigger="load"
     hx-target="this" hx-swap="innerHTML">
  Loading matches...
</div>
```

#### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/upload` | POST | Upload Snapchat export ZIP |
| `/api/jobs` | GET | List user's jobs |
| `/api/jobs/{id}` | GET | Job detail + stats |
| `/api/jobs/{id}/stream` | GET (SSE) | Live progress events |
| `/api/jobs/{id}/reprocess` | POST | Trigger reprocessing |
| `/api/summary` | GET | User's pipeline metrics |
| `/api/assets` | GET | Paginated asset list |
| `/api/matches` | GET | Match list with confidence |
| `/api/matches/{id}` | GET | Match detail |
| `/api/conversations` | GET | Conversation index |
| `/api/conversations/{id}` | GET | Conversation with messages |
| `/api/memories` | GET | Memory list |
| `/api/download/{path}` | GET | Download processed file |
| `/api/download/all` | GET | Download all output as ZIP |

### 3.10 Configuration System

Simplified from v1's 5-layer precedence to 3 layers:

#### Three-Layer Precedence (highest → lowest)

1. **Per-user overrides** — stored in PostgreSQL `user_preferences` table
2. **Server config** — `snatched.toml` (single file, admin-managed)
3. **Built-in defaults** — hardcoded in `config.py`

No CLI flags (web-first), no environment variable layer, no per-project config.

#### Server Config: `snatched.toml`

```toml
[server]
host = "0.0.0.0"
port = 8080
data_dir = "/data"                    # Root for all user data
max_upload_bytes = 5368709120         # 5 GB
dev_mode = false                      # Enable JWT fallback (local dev only)

[database]
postgres_url = "postgresql://snatched:***@memory-store:5432/snatched"

[pipeline]
batch_size = 500
gps_window_seconds = 300

[exif]
enabled = true
tool = "exiftool"

[xmp]
enabled = false
alongside_exif = true
include_snatched_ns = true

[lanes.memories]
enabled = true
burn_overlays = true
folder_pattern = "memories/{YYYY}/{MM}"

[lanes.chats]
enabled = true
export_text = true
export_png = true
dark_mode = false
folder_pattern = "chat/{ConvName}"

[lanes.stories]
enabled = true
folder_pattern = "stories"
```

### 3.11 CLI (Secondary)

The CLI is a lightweight admin tool, not the primary interface. It exists for debugging, batch operations, and server management.

```bash
# Admin: process a specific user's export from command line
snatched process --user dave --input /path/to/export.zip

# Admin: check a user's database
snatched query --user dave "SELECT COUNT(*) FROM matches"

# Admin: reprocess for a user
snatched reprocess --user dave --phases match,enrich,export

# Admin: list all users and their job history
snatched users

# Admin: server health check
snatched status
```

No wizard, no terminal art, no guided mode. The web UI replaces all of that.

---

## 4. Module Specifications

### 4.1 app.py — FastAPI Application

**Functions:**
- `create_app()` — FastAPI factory with middleware, lifespan, route registration
- `lifespan()` — startup (connect PostgreSQL, init dirs) / shutdown (cleanup)

**Key middleware:**
- Authelia header extraction
- Per-user data directory creation on first request
- Request logging

**Size estimate:** ~100 lines

### 4.2 config.py — Configuration

**Functions:**
- `load_config()` — load server config from TOML
- `get_user_config(username)` — merge server defaults + user overrides
- `Config` class — typed access to all settings
- `DEFAULT_CONFIG` — built-in defaults

**Size estimate:** ~120 lines

### 4.3 auth.py — Authentication

**Functions:**
- `get_current_user(request)` — extract username from Authelia headers
- `get_user_groups(request)` — extract groups for admin checks
- `require_admin(request)` — dependency for admin-only routes
- `dev_mode_auth(request)` — JWT fallback for local dev

**Size estimate:** ~80 lines

### 4.4 models.py — Pydantic Models

**Models:**
- `User` — user profile from PostgreSQL
- `Job` / `JobCreate` / `JobStatus` — processing job lifecycle
- `JobEvent` — SSE event
- `MatchResult` — match with confidence and strategy
- `AssetInfo` — asset metadata
- `UploadResponse` — upload result with job ID
- `PipelineStats` — summary statistics

**Size estimate:** ~150 lines

### 4.5 db.py — PostgreSQL Layer

**Functions:**
- `get_db_pool()` — connection pool (asyncpg)
- `init_schema()` — create tables if not exist
- `create_user(username)` — upsert user on first login
- `create_job(user_id, ...)` — create processing job
- `update_job(job_id, ...)` — update job status/progress
- `emit_event(job_id, event_type, message)` — insert job event
- `get_events_after(job_id, last_id)` — poll events for SSE

**Size estimate:** ~200 lines

### 4.6 processing/sqlite.py — Per-User SQLite

**Functions:**
- `open_database(db_path)` — open SQLite, apply schema, run migrations
- `create_schema(db)` — execute schema.sql
- `migrate(db)` — ALTER TABLE migrations for v2 → v3
- `batch_insert(db, table, columns, rows)` — batched inserts
- `batch_update(db, sql, rows)` — batched updates
- `log_run(db, ...)` — insert into run_log

**Size estimate:** ~180 lines

### 4.7 processing/schema.sql — SQLite Schema

*(Unchanged from v1 — 12 tables + v3 additions)*

**Size estimate:** ~120 lines SQL

### 4.8 processing/ingest.py — Phase 1

*(Unchanged from v1 — all ingest functions preserved)*

**Size estimate:** ~800 lines

### 4.9 processing/match.py — Phase 2

*(Unchanged from v1 — all 6 strategies preserved exactly)*

**Size estimate:** ~400 lines

### 4.10 processing/enrich.py — Phase 3

*(Unchanged from v1 — GPS, names, paths, EXIF tags)*

**Size estimate:** ~650 lines

### 4.11 processing/export.py — Phase 4

*(Unchanged from v1 — copy, EXIF, overlays, chat export)*

**Size estimate:** ~700 lines

### 4.12 processing/lanes.py — Three-Lane Controller

*(Unchanged from v1)*

**Size estimate:** ~300 lines

### 4.13 processing/xmp.py — XMP Engine

*(Unchanged from v1)*

**Size estimate:** ~250 lines

### 4.14 processing/reprocess.py — Reprocessing Engine

*(Unchanged from v1, triggered from web UI instead of CLI)*

**Size estimate:** ~200 lines

### 4.15 processing/chat_renderer.py — Chat PNG Engine

*(Unchanged from v1/v2 — 1,101 lines, mostly preserved)*

**Size estimate:** ~1,100 lines

### 4.16 jobs.py — Job Queue

**Functions:**
- `create_processing_job(user_id, upload_path, config)` — create job + return ID
- `run_job(job_id, username)` — async: execute full pipeline
- `cancel_job(job_id)` — request cancellation
- `get_job_status(job_id)` — current status + progress
- `cleanup_uploads(username, max_age_days)` — remove old uploads

**Size estimate:** ~250 lines

### 4.17 routes/pages.py — HTML Routes

**Routes:**
- `GET /` — landing page
- `GET /upload` — upload form
- `GET /dashboard` — job list + progress
- `GET /results` — results browser
- `GET /download` — download manager
- `GET /memories` — memory browser (optional)
- `GET /conversations` — chat browser (optional)

**Size estimate:** ~200 lines

### 4.18 routes/api.py — JSON API

**Routes:**
- All `/api/*` endpoints listed in section 3.9

**Size estimate:** ~300 lines

### 4.19 routes/uploads.py — Upload Handling

**Functions:**
- `handle_upload(file, username)` — validate, save, create job
- `validate_upload(file)` — check type, size, structure
- `extract_upload(zip_path, dest)` — safe extraction with path traversal protection

**Size estimate:** ~150 lines

### 4.20 utils.py — Shared Utilities

*(Unchanged from v1 — parsing, hashing, format detection)*

**Size estimate:** ~300 lines

### 4.21 cli.py — Optional CLI

**Functions:**
- `main()` — argparse with admin subcommands
- `cmd_process(args)` — process a specific user's export
- `cmd_query(args)` — SQL query against user's DB
- `cmd_reprocess(args)` — reprocess for a user
- `cmd_users(args)` — list users
- `cmd_status(args)` — server health

**Size estimate:** ~150 lines

---

## 5. Requirements

### 5.1 Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01 | Web-first multi-user application | Critical |
| FR-02 | File upload for Snapchat export ZIPs | Critical |
| FR-03 | Background job queue with SSE progress | Critical |
| FR-04 | Per-user data isolation (directory + SQLite) | Critical |
| FR-05 | Authelia authentication delegation | Critical |
| FR-06 | Three independent export lanes | Critical |
| FR-07 | Preserve 6-strategy match cascade | Critical |
| FR-08 | Preserve 4-phase pipeline (Ingest → Match → Enrich → Export) | Critical |
| FR-09 | Preserve SQLite processing architecture (per-user) | Critical |
| FR-10 | Preserve EXIF embedding (exiftool stay_open) | Critical |
| FR-11 | Preserve SHA-256 checksums | Critical |
| FR-12 | Reprocessing without re-extraction | Critical |
| FR-13 | XMP sidecar generation (shipped disabled) | High |
| FR-14 | Preserve overlay burning | High |
| FR-15 | Preserve chat PNG rendering | High |
| FR-16 | Preserve format detection (WebP-as-PNG, fMP4) | High |
| FR-17 | Results browser in web UI | High |
| FR-18 | Download processed files (individual + ZIP) | High |
| FR-19 | Server-side config file (TOML) | High |
| FR-20 | Admin CLI tool (secondary interface) | Medium |
| FR-21 | Per-user storage quotas | Medium |
| FR-22 | Reprocessing from web UI | Medium |
| FR-23 | Memory browser in web UI | Medium |
| FR-24 | Conversation browser in web UI | Medium |
| FR-25 | Map view (GPS-tagged memories) | Low |
| FR-26 | Proper Python logging | Medium |
| FR-27 | Unit tests for matching strategies | Medium |
| FR-28 | Unit tests for ingest parsers | Medium |

### 5.2 Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-01 | Process 5,000+ assets in under 10 minutes |
| NFR-02 | Per-user SQLite DBs under 5 MB for typical exports |
| NFR-03 | Web UI pages load in under 2 seconds |
| NFR-04 | No data loss during reprocessing |
| NFR-05 | Backward-compatible with v2 SQLite databases |
| NFR-06 | Upload supports files up to 5 GB |
| NFR-07 | XMP sidecars parseable by standard DAM tools |
| NFR-08 | Zero cross-user data access |

### 5.3 Dependencies

#### Python Packages (pip)

| Package | Purpose |
|---------|---------|
| fastapi | Web framework |
| uvicorn | ASGI server |
| jinja2 | Template rendering |
| python-multipart | File upload support |
| asyncpg | PostgreSQL async driver |
| pydantic | Request/response validation |
| tomli | TOML parsing (Python <3.11) |

#### External Tools (system packages)

| Tool | Purpose |
|------|---------|
| exiftool | EXIF embedding |
| ImageMagick | Overlay burning |
| ffmpeg | Video overlay + fMP4 remux |
| PostgreSQL | Shared app database |

#### Optional Python Packages

| Package | Purpose |
|---------|---------|
| Pillow | Chat PNG rendering |
| pyjwt | Dev mode JWT auth |

---

## 6. Migration Strategy

V3 development is **non-destructive** to the running v2 system.

### Phase 1: Scaffold
1. Set up FastAPI project structure
2. Connect to PostgreSQL (new `snatched` database)
3. Implement auth.py (Authelia header extraction)
4. Build upload + job queue skeleton

### Phase 2: Port Pipeline
1. Copy v2 processing code into `processing/` package
2. Adapt to per-user SQLite paths (remove hardcoded paths)
3. Add progress callbacks for SSE integration
4. Test against v2's database output — match counts must be identical

### Phase 3: Build Web UI
1. Build 5 core pages (Landing, Upload, Dashboard, Results, Download)
2. Wire SSE progress streaming
3. Build htmx interactions

### Phase 4: Validation
1. Run v3 against same input data as v2
2. Compare: match counts, GPS counts, EXIF tags, output file hashes
3. Diff report.json between v2 and v3
4. Zero regression = green light

### Phase 5: Deploy
1. Docker container with FastAPI + uvicorn
2. Add to Traefik routing (alongside dashboard, Immich)
3. Configure Authelia protection

### Database Migration

Per-user SQLite databases are backward-compatible with v2. New columns/tables added via `ALTER TABLE` migrations in `processing/sqlite.py`.

---

## 7. Security Considerations

From the debate's 14-point security analysis:

### Addressed by Architecture (12/14)

| Gap | How It's Addressed |
|-----|--------------------|
| Auth bypass | Authelia at Traefik level — requests never reach Snatched unauthenticated |
| Session hijacking | Authelia manages sessions, not Snatched |
| Cross-user data access | Physical isolation: separate directories + SQLite per user |
| Path traversal (uploads) | Validate all paths resolve within user's data directory |
| ZIP bombs | Check uncompressed size ratio before extraction (>100:1 = reject) |
| Malicious filenames | `sanitize_filename()` from v2, applied to all extracted files |
| Arbitrary file upload | Validate ZIP contents — only allow known Snapchat export structure |
| SQL injection (SQLite) | Parameterized queries everywhere (inherited from v2) |
| SQL injection (PostgreSQL) | asyncpg parameterized queries |
| Denial of service | Storage quotas per user, upload size limits |
| Sensitive data in logs | Structured logging, no PII in log messages |
| Container escape | Docker with read-only rootfs, no capabilities, non-root user |

### Remaining (2/14)

| Gap | Status | Notes |
|-----|--------|-------|
| XMP metadata redaction | Deferred | Users may not want all metadata in XMP sidecars — need redaction config |
| GDPR / data deletion | Deferred | Need "delete my data" endpoint — trivial (rm user's directory + PostgreSQL rows) |

---

## 8. Open Questions

| # | Question | Leaning | Debate Notes |
|---|----------|---------|--------------|
| 1 | Reuse existing `memory-store` PostgreSQL or dedicated instance? | Dedicated | Isolation, independent lifecycle |
| 2 | Storage quotas: enforce at upload or total? | Both | Upload limit + total quota |
| 3 | Allow users to download their SQLite DB? | Yes | Portable, debuggable, transparency |
| 4 | Admin panel for user management? | Defer to v3.1 | Authelia handles user creation |
| 5 | Multiple exports per user (e.g., yearly re-exports)? | Yes, append | Each upload adds to their DB, don't overwrite |
| 6 | Rate limiting on uploads? | Yes | Prevent abuse, one concurrent job per user |
| 7 | CSS framework? | Pico or plain | Minimal, classless styling |
| 8 | Notifications when job completes? | Defer | Could add email/push later |

---

## Appendix: V1 → V2 Plan Changelog

Major changes from Plan v1 to v2:

| Area | V1 (Plan v1) | V2 (This Plan) |
|------|-------------|-----------------|
| **Primary Interface** | CLI with web add-on | Web-first, CLI secondary |
| **Users** | Single user (Dave) | Multi-user with Authelia |
| **Database** | Single SQLite | Hybrid: PostgreSQL (shared) + per-user SQLite |
| **Framework** | Flask | FastAPI (async for uploads + SSE) |
| **Frontend** | Flask + Jinja2 + vanilla JS | FastAPI + Jinja2 + htmx (14KB) |
| **Auth** | None (CLI tool) | Authelia delegation via Traefik |
| **File Input** | Local paths | Upload through browser |
| **Job Execution** | Synchronous CLI | Background job queue with SSE progress |
| **Config Layers** | 5 layers | 3 layers (defaults, server TOML, user prefs) |
| **Wizard** | Preserved from v2 | Removed (web UI replaces it) |
| **Terminal Art** | Preserved from v2 | Removed (web dashboard replaces it) |
| **Build Order** | Sequential 17-step plan | Irrelevant (vibe-coded) |
| **XMP** | Default on (debated) | Code ready, shipped disabled |
| **Module Count** | 16 modules + web/ | ~21 modules (more focused decomposition) |

---

*This document is the blueprint. The baby is gone, the blow is out, we're stabbing GPL-1s, and it's time for our mommy job.*
