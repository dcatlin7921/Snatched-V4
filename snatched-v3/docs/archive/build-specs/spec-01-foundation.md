# Spec 01 — Foundation Layer

## Module Overview

This spec defines the foundational modules that all other v3 modules depend on:

- **`snatched/utils.py`** — Parsing, hashing, format detection utilities (ported from v2)
- **`snatched/config.py`** — Configuration system (Pydantic Settings, TOML loading)
- **`snatched/models.py`** — Pydantic request/response schemas
- **`snatched/processing/sqlite.py`** — Per-user SQLite database management
- **`snatched/processing/schema.sql`** — Complete SQLite schema (12 tables + v3 additions)

These modules have **zero processing logic**. They are pure utilities, config, and schema.

---

## Files to Create

```
snatched/
├── utils.py                       # ~350 lines: parsing, hashing, format detection
├── config.py                      # ~200 lines: Pydantic Settings + TOML loading
├── models.py                      # ~180 lines: Pydantic models (User, Job, etc)
└── processing/
    ├── __init__.py                # Empty init
    ├── sqlite.py                  # ~250 lines: SQLite open, migrate, helpers
    └── schema.sql                 # ~180 lines: DDL for all 12 tables + v3 additions
```

---

## Dependencies

**No external v3 modules** — these are foundation only.

**External packages:**
```
fastapi
pydantic
pydantic-settings
tomli
aiofiles
Pillow
asyncpg    # used by db.py (Spec 02), not in this spec
```

**Standard library:**
```
datetime, timezone
hashlib
json
logging
pathlib
re
sqlite3
subprocess
urllib.parse
```

---

## V2 Source Reference

- **`utils.py` contents** ported from `/home/dave/tools/snapfix/snatched.py` lines 88–268 (utility functions)
- **Constants** from `/home/dave/tools/snapfix/snatched.py` lines 45–62 (regexes, magic bytes)
- **Schema** from `/home/dave/tools/snapfix/snatched.py` lines 272–471 (`SCHEMA_SQL`)
- Config and models are **new in v3** (v2 had no TOML or multi-user support)
- Chat renderer source: `/home/dave/tools/snapfix/chat_renderer.py` (used in Spec 05)

---

## Function Signatures

### `snatched/utils.py` — Complete Public Interface

```python
import re
import hashlib
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
import logging

logger = logging.getLogger(__name__)

# Compiled regex constants (preserved exactly from v2)
MEMORY_RE: re.Pattern[str]       # Memory filename: YYYYMMDD_HHmmss-{uuid}-{overlay|main}.ext
CHAT_FILE_RE: re.Pattern[str]    # Chat filename: YYYYMMDD_HHmmss-{file_id}.ext
LOCATION_RE: re.Pattern[str]     # GPS: "lat ± accuracy, lon ± accuracy"
UUID_RE: re.Pattern[str]         # UUID v4 validation
UNSAFE_FILENAME_RE: re.Pattern[str]  # Characters illegal in filenames

# Magic bytes for format detection (preserved exactly from v2)
RIFF_MAGIC: bytes    # b'RIFF' — WebP/WAV/AVI container
FMP4_STYP: bytes     # b'styp' — fragmented MP4 marker

# Extension sets
VIDEO_EXTS: set[str]  # {'.mp4', '.mov', '.avi', '.webm', ...}


def parse_snap_date(s: str) -> datetime | None:
    """Parse Snapchat date string to timezone-aware UTC datetime.

    Handles format: '2026-02-20 08:17:52 UTC'
    Returns None for None input or unparseable strings.

    Args:
        s: Snapchat date string

    Returns:
        datetime with tzinfo=UTC, or None
    """

def parse_snap_date_iso(s: str) -> str | None:
    """Parse Snapchat date string to ISO 8601 format.

    Returns: '2026-02-20T08:17:52+00:00' or None
    """

def parse_snap_date_dateonly(s: str) -> str | None:
    """Parse Snapchat date string, return date portion only.

    Returns: 'YYYY-MM-DD' or None
    """

def parse_location(s: str) -> tuple[float, float] | None:
    """Parse Snapchat location string to (lat, lon).

    Handles formats:
    - 'Latitude, Longitude: 39.56, -89.65'
    - '39.56 ± 10.5, -89.65 ± 10.5'

    Returns:
        (lat, lon) float tuple, or None if unparseable
    """

def extract_mid(url: str) -> str | None:
    """Extract 'mid' query parameter from Snapchat download URL.

    Args:
        url: Full download URL from memories_history.json

    Returns:
        UUID string, or None if not found
    """

def detect_real_format(path: Path) -> str | None:
    """Detect actual file format by reading magic bytes.

    Checks if file's extension matches actual format.
    Returns corrected extension if mismatched (e.g., '.webp' for a renamed .jpg).
    Returns None if extension matches actual format.

    Args:
        path: Path to file to inspect

    Returns:
        Corrected extension string (e.g., '.webp'), or None
    """

def is_fragmented_mp4(path: Path) -> bool:
    """Check if MP4 uses fragmented (fMP4) container.

    fMP4 files require ffmpeg remux before EXIF embedding works correctly.

    Args:
        path: Path to MP4 file

    Returns:
        True if file uses fragmented MP4 container
    """

def sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file.

    Reads in 64KB chunks to avoid loading large files into memory.

    Args:
        path: Path to file

    Returns:
        64-character lowercase hex string
    """

def sanitize_filename(name: str) -> str:
    """Sanitize a string for safe use as a filename or directory component.

    Replaces illegal characters, collapses multiple underscores,
    strips leading/trailing whitespace and dots.

    Args:
        name: Arbitrary string

    Returns:
        Filesystem-safe string (no special characters)
    """

def parse_iso_dt(s: str) -> datetime | None:
    """Parse ISO 8601 string to timezone-aware datetime.

    Args:
        s: ISO 8601 date string

    Returns:
        datetime with UTC tzinfo, or None
    """

def exif_dt(dt: datetime) -> str:
    """Format datetime for EXIF tag value.

    Returns:
        String in EXIF format: '2026:02:20 08:17:52'
    """

def gps_tags(lat: float, lon: float, is_video: bool, dt: datetime | None = None) -> dict:
    """Build GPS EXIF tag dict for photos or videos.

    Args:
        lat: Latitude in decimal degrees
        lon: Longitude in decimal degrees
        is_video: True if file is video (uses different tag names)
        dt: Optional datetime for GPS timestamp tags

    Returns:
        Dict of {exif_tag_name: value, ...}
    """

def date_tags(dt: datetime, is_video: bool, subsec_ms: int | None = None) -> dict:
    """Build date/time EXIF tag dict for photos or videos.

    Args:
        dt: Datetime to embed
        is_video: True if file is video
        subsec_ms: Optional subsecond millisecond value

    Returns:
        Dict of {exif_tag_name: value, ...}
    """

def format_chat_date(s: str) -> str:
    """Format a Snapchat date string for chat transcript display.

    Args:
        s: Snapchat date string ('2026-02-20 08:17:52 UTC')

    Returns:
        Display string ('2026-02-20 08:17:52')
    """

def is_video(path: Path) -> bool:
    """Check if path has a recognized video extension.

    Args:
        path: File path to check

    Returns:
        True if extension is in VIDEO_EXTS
    """

def safe_user_path(base_dir: Path, user_path: str) -> Path:
    """Resolve user_path relative to base_dir, validate it stays within base_dir.

    Prevents path traversal attacks (e.g., '../../etc/passwd').

    Args:
        base_dir: Trusted base directory (e.g., Path('/data'))
        user_path: Untrusted path component (e.g., 'dave/proc.db')

    Returns:
        Resolved absolute Path within base_dir

    Raises:
        ValueError: If resolved path escapes base_dir
    """
```

---

### `snatched/config.py` — Configuration System

```python
from pathlib import Path
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
import tomli
import logging

logger = logging.getLogger(__name__)


class ServerConfig(BaseModel):
    """Server binding and runtime settings."""
    host: str = "0.0.0.0"
    port: int = 8000
    data_dir: Path = Path("/data")
    max_upload_bytes: int = 5 * 1024 * 1024 * 1024  # 5 GB
    dev_mode: bool = False  # Enable dev bypass for auth (NEVER True in production)


class DatabaseConfig(BaseModel):
    """PostgreSQL connection settings."""
    postgres_url: str = "postgresql://snatched:snatched@postgres:5432/snatched"
    pool_min_size: int = 2
    pool_max_size: int = 10


class PipelineConfig(BaseModel):
    """Pipeline execution settings."""
    batch_size: int = 500           # Rows per SQLite commit batch
    gps_window_seconds: int = 300   # ±5 min for GPS cross-reference


class ExifConfig(BaseModel):
    """EXIF embedding settings."""
    enabled: bool = True
    tool: str = "exiftool"          # System binary name


class XmpConfig(BaseModel):
    """XMP sidecar generation settings."""
    enabled: bool = False
    alongside_exif: bool = True     # Generate XMP in addition to EXIF
    only: bool = False              # Generate XMP instead of EXIF
    include_snatched_ns: bool = True


class LaneConfig(BaseModel):
    """Per-lane processing settings."""
    enabled: bool = True
    folder_pattern: str = "{YYYY}/{MM}"  # Folder structure for output

    # Memories lane
    burn_overlays: bool = True

    # Chats lane
    export_text: bool = True
    export_png: bool = True
    dark_mode: bool = False


class Config(BaseModel):
    """Complete application configuration."""
    server: ServerConfig = ServerConfig()
    database: DatabaseConfig = DatabaseConfig()
    pipeline: PipelineConfig = PipelineConfig()
    exif: ExifConfig = ExifConfig()
    xmp: XmpConfig = XmpConfig()
    lanes: dict[str, LaneConfig] = {}


def load_config(toml_path: Path | None = None) -> Config:
    """Load configuration from TOML file with built-in defaults.

    Priority (lowest → highest):
    1. Built-in defaults (hardcoded in Config model)
    2. snatched.toml values (if file exists)

    Args:
        toml_path: Path to TOML config file. Defaults to /app/snatched.toml.

    Returns:
        Populated Config object.

    Raises:
        ValueError: If TOML file exists but has invalid syntax.
    """


def get_user_data_dir(config: Config, username: str) -> Path:
    """Return per-user data directory: config.server.data_dir / username.

    Args:
        config: Application configuration
        username: Authenticated username

    Returns:
        Path to user's data directory (not validated to exist)
    """
```

---

### `snatched/models.py` — Pydantic Models

```python
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class User(BaseModel):
    """User profile from PostgreSQL."""
    id: int
    username: str
    display_name: str | None = None
    created_at: datetime
    last_seen: datetime | None = None
    storage_quota_bytes: int = 10 * 1024 * 1024 * 1024  # 10 GB default


class JobStatus(str, Enum):
    """Job lifecycle status values."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Job(BaseModel):
    """Processing job as stored in PostgreSQL."""
    id: int
    user_id: int
    status: JobStatus
    upload_filename: str
    upload_size_bytes: int
    phases_requested: list[str]   # e.g., ['ingest', 'match', 'enrich', 'export']
    lanes_requested: list[str]    # e.g., ['memories', 'chats', 'stories']
    progress_pct: int = 0
    current_phase: str | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    stats_json: dict | None = None


class JobCreate(BaseModel):
    """Request body to create a new processing job."""
    upload_filename: str
    upload_size_bytes: int = Field(gt=0)
    phases_requested: list[str]
    lanes_requested: list[str]


class JobEventType(str, Enum):
    """Job event types streamed via SSE."""
    PHASE_START = "phase_start"
    PROGRESS = "progress"
    MATCH_FOUND = "match_found"
    ERROR = "error"
    COMPLETE = "complete"


class JobEvent(BaseModel):
    """Single job event record for SSE streaming."""
    id: int
    job_id: int
    event_type: JobEventType
    message: str
    data_json: dict | None = None
    created_at: datetime


class MatchResult(BaseModel):
    """Single match result row."""
    asset_id: int
    strategy: str
    confidence: float
    is_best: bool
    matched_date: str | None = None
    matched_lat: float | None = None
    matched_lon: float | None = None
    display_name: str | None = None
    output_subdir: str | None = None
    output_filename: str | None = None


class AssetInfo(BaseModel):
    """Single asset metadata record."""
    id: int
    path: str
    filename: str
    date_str: str | None = None
    asset_type: str
    is_video: bool
    file_size: int
    sha256: str
    output_path: str | None = None
    exif_written: bool = False


class PipelineStats(BaseModel):
    """Summary statistics from a complete pipeline run."""
    total_assets: int = 0
    total_matched: int = 0
    total_exif_ok: int = 0
    total_exif_err: int = 0
    total_copied: int = 0
    gps_count: int = 0
    elapsed_seconds: float = 0.0


class UploadResponse(BaseModel):
    """Response after a successful file upload."""
    job_id: int
    upload_filename: str
    message: str
    redirect_url: str   # e.g., '/dashboard?job_id=123'
```

---

### `snatched/processing/sqlite.py` — Database Management

```python
import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

BATCH_SIZE: int = 500  # Rows per commit batch


def open_database(db_path: Path) -> sqlite3.Connection:
    """Open (or create) the per-user SQLite processing database.

    Creates parent directories if they don't exist.
    Applies schema.sql (idempotent — uses CREATE TABLE IF NOT EXISTS).
    Runs v2→v3 migrations for databases created by older versions.

    Args:
        db_path: Path to SQLite file. Use Path(':memory:') for testing.

    Returns:
        sqlite3.Connection with WAL mode, foreign keys enabled, row_factory set.

    Raises:
        sqlite3.Error: If DB cannot be opened or schema cannot be applied.
    """


def create_schema(db: sqlite3.Connection) -> list[str]:
    """Execute full schema.sql, creating all 12 core tables + 2 v3 tables.

    Idempotent — uses CREATE TABLE IF NOT EXISTS.

    Returns:
        List of table names that exist after creation (for verification).
    """


def migrate_schema(db: sqlite3.Connection) -> None:
    """Apply v2→v3 schema migrations for databases created by older versions.

    Migrations applied (all idempotent — safe to run multiple times):
    - ALTER TABLE matches ADD COLUMN lane TEXT DEFAULT 'memories'
    - ALTER TABLE assets ADD COLUMN xmp_written BOOLEAN DEFAULT 0
    - ALTER TABLE assets ADD COLUMN xmp_path TEXT
    - CREATE TABLE IF NOT EXISTS reprocess_log (...)
    - CREATE TABLE IF NOT EXISTS lane_config (...)

    Uses try/except around each ALTER to skip columns that already exist.
    (SQLite does not support IF NOT EXISTS on ALTER TABLE ADD COLUMN.)
    """


def batch_insert(
    db: sqlite3.Connection,
    table: str,
    columns: list[str],
    rows: list[tuple],
    batch_size: int = BATCH_SIZE,
) -> int:
    """Bulk insert rows into a table with per-batch commits.

    IMPORTANT: `table` and `columns` are used directly in SQL — callers must
    pass only trusted constant values, never user-controlled input.

    Args:
        db: SQLite connection
        table: Table name (must be a trusted constant)
        columns: Column names (must be trusted constants)
        rows: List of value tuples to insert
        batch_size: Rows per commit (default 500)

    Returns:
        Total rows inserted.
    """


def batch_update(
    db: sqlite3.Connection,
    sql: str,
    rows: list[tuple],
    batch_size: int = BATCH_SIZE,
) -> int:
    """Execute a parameterized UPDATE/INSERT on multiple row tuples with batching.

    Args:
        db: SQLite connection
        sql: Parameterized SQL template (e.g., "UPDATE assets SET x=? WHERE id=?")
        rows: List of parameter tuples
        batch_size: Rows per commit (default 500)

    Returns:
        Total rows affected.
    """


def log_run(
    db: sqlite3.Connection,
    version: str,
    person: str,
    input_path: str,
    status: str = "running",
    stats: dict | None = None,
) -> int:
    """Insert a run_log entry and return the new row ID.

    Args:
        db: SQLite connection
        version: Snatched version string (e.g., "3.0")
        person: Username running the pipeline
        input_path: Path to the input export directory
        status: Initial status ('running')
        stats: Optional initial stats dict (serialized to JSON)

    Returns:
        run_log row ID.
    """
```

---

## Database Schema

### Complete SQLite DDL

**File:** `snatched/processing/schema.sql`

```sql
-- Pragmas for performance and safety
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

-- ── ASSETS: Every media file discovered on disk ───────────────────────────────
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

-- ── CHAT_MESSAGES: Every message from chat_history.json ───────────────────────
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

-- ── CHAT_MEDIA_IDS: Exploded pipe-separated media IDs ─────────────────────────
CREATE TABLE IF NOT EXISTS chat_media_ids (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_message_id INTEGER NOT NULL REFERENCES chat_messages(id),
    media_id        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_mid ON chat_media_ids(media_id);

-- ── SNAP_MESSAGES: Every entry from snap_history.json ─────────────────────────
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

-- ── MEMORIES: All entries from memories_history.json ──────────────────────────
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

-- ── STORIES: Entries from shared_story.json ───────────────────────────────────
CREATE TABLE IF NOT EXISTS stories (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id        TEXT,
    created         TEXT,
    created_dt      TEXT,
    content_type    TEXT
);

CREATE INDEX IF NOT EXISTS idx_stories_id   ON stories(story_id);
CREATE INDEX IF NOT EXISTS idx_stories_type ON stories(content_type);

-- ── SNAP_PRO: Saved stories from snap_pro.json ────────────────────────────────
CREATE TABLE IF NOT EXISTS snap_pro (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    url             TEXT,
    created         TEXT,
    created_dt      TEXT,
    title           TEXT
);

-- ── FRIENDS: Username to display name mapping ─────────────────────────────────
CREATE TABLE IF NOT EXISTS friends (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT NOT NULL UNIQUE,
    display_name    TEXT,
    category        TEXT
);

CREATE INDEX IF NOT EXISTS idx_friends_username ON friends(username);

-- ── LOCATIONS: GPS breadcrumbs from location_history.json ─────────────────────
CREATE TABLE IF NOT EXISTS locations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    timestamp_unix  REAL NOT NULL,
    lat             REAL NOT NULL,
    lon             REAL NOT NULL,
    accuracy_m      REAL
);

CREATE INDEX IF NOT EXISTS idx_locations_ts ON locations(timestamp_unix);

-- ── PLACES: Snap Map places from snap_map_places.json ────────────────────────
CREATE TABLE IF NOT EXISTS places (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT,
    lat             REAL,
    lon             REAL,
    address         TEXT,
    visit_count     INTEGER
);

-- ── MATCHES: Join table linking assets to metadata sources (Phase 2) ──────────
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

-- ── RUN_LOG: Audit trail for each execution ───────────────────────────────────
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

-- ── REPROCESS_LOG: Audit trail for reprocessing runs (v3 addition) ────────────
CREATE TABLE IF NOT EXISTS reprocess_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL DEFAULT (datetime('now')),
    phases          TEXT,
    lanes           TEXT,
    triggered_by    TEXT,
    status          TEXT DEFAULT 'pending',
    result_json     TEXT
);

-- ── LANE_CONFIG: Per-lane user overrides (v3 addition) ───────────────────────
CREATE TABLE IF NOT EXISTS lane_config (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    lane_name       TEXT UNIQUE NOT NULL,
    config_json     TEXT
);
```

**Table count:** 14 (12 core + 2 v3 additions)
**Index count:** 18 custom indexes

---

## Key SQL Queries

```python
# Count total assets
count = db.execute("SELECT COUNT(*) FROM assets").fetchone()[0]

# Get all unmatched assets
unmatched = db.execute("""
    SELECT id, path, filename FROM assets
    WHERE id NOT IN (SELECT DISTINCT asset_id FROM matches)
    ORDER BY date_str
""").fetchall()

# Get best match per asset
best_matches = db.execute("""
    SELECT asset_id, strategy, confidence, is_best
    FROM matches
    WHERE is_best = 1
    ORDER BY asset_id
""").fetchall()

# Count matches by strategy
strategy_counts = db.execute("""
    SELECT strategy, COUNT(*) as count, AVG(confidence) as avg_conf
    FROM matches
    GROUP BY strategy
    ORDER BY count DESC
""").fetchall()

# Get all GPS-enabled memories
gps_memories = db.execute("""
    SELECT id, mid, lat, lon, date_dt
    FROM memories
    WHERE lat IS NOT NULL AND lon IS NOT NULL
    ORDER BY date_dt
""").fetchall()

# Get location timeline for GPS binary search
locations = db.execute("""
    SELECT timestamp_unix, lat, lon, accuracy_m
    FROM locations
    ORDER BY timestamp_unix
""").fetchall()

# Find matches for a specific conversation
conv_matches = db.execute("""
    SELECT m.id, a.filename, m.strategy, m.confidence
    FROM matches m
    JOIN assets a ON m.asset_id = a.id
    WHERE m.conversation = ?
    ORDER BY m.confidence DESC
""", (conv_name,)).fetchall()

# Batched insert pattern used in all Phase 1 ingest functions
rows = [(val1, val2, val3), ...]
db.executemany(
    "INSERT INTO table (col1, col2, col3) VALUES (?, ?, ?)",
    rows
)
db.commit()

# Parameterized update
db.execute(
    "UPDATE assets SET output_path = ? WHERE id = ?",
    (output_path, asset_id)
)
db.commit()

# Check if column exists (for migrations)
columns = db.execute("PRAGMA table_info(assets)").fetchall()
col_names = [col[1] for col in columns]
if 'xmp_written' not in col_names:
    db.execute("ALTER TABLE assets ADD COLUMN xmp_written BOOLEAN DEFAULT 0")
    db.commit()
```

---

## Multi-User Adaptation

All v2 code assumes single-user with hardcoded paths. v3 adapts as follows:

### Path Changes

**v2 (single user):**
```python
INPUT_BASE = Path("/mnt/nas-pool/snapchat-input")
OUTPUT_BASE = Path("/mnt/nas-pool/snapchat-output")
db_path = "/mnt/nas-pool/.snatched/snatched.db"
```

**v3 (multi-user — every path derived from user context):**
```python
from snatched.config import Config, get_user_data_dir
from snatched.utils import safe_user_path

config = load_config()
user_dir = get_user_data_dir(config, username)  # /data/{username}

uploads_dir    = user_dir / "uploads"
processing_dir = user_dir / "processing"
output_dir     = user_dir / "output"
db_path        = user_dir / "proc.db"

# Path validation before use
safe_db = safe_user_path(config.server.data_dir, f"{username}/proc.db")
```

### Configuration

v2 used hardcoded constants + CLI flags. v3 uses layered config:

```python
# Load defaults → TOML file
config = load_config(Path("/app/snatched.toml"))

# Access pipeline settings
gps_window = config.pipeline.gps_window_seconds  # 300
batch_size  = config.pipeline.batch_size          # 500
```

### Data Isolation

```
/data/
├── dave/
│   ├── uploads/      # ZIP files uploaded by dave
│   ├── processing/   # Extracted ZIPs
│   ├── output/       # Exported files
│   └── proc.db       # dave's SQLite processing DB
└── shannon/
    └── ...           # Completely separate
```

---

## Code Examples

### Using `utils.py`

```python
from pathlib import Path
from snatched.utils import (
    parse_snap_date, extract_mid, sha256_file,
    sanitize_filename, is_video, safe_user_path
)

# Parse a Snapchat date
dt = parse_snap_date("2026-02-20 08:17:52 UTC")
assert dt.year == 2026 and dt.tzinfo is not None

# Extract MID from download URL
mid = extract_mid("https://example.com/dl?mid=550e8400-e29b-41d4-a716-446655440000")
assert mid == "550e8400-e29b-41d4-a716-446655440000"

# Hash a file
path = Path("/tmp/photo.jpg")
h = sha256_file(path)
assert len(h) == 64  # hex digest

# Sanitize a filename
clean = sanitize_filename("My   Memory <2026>|\"bad\"")
# Returns filesystem-safe string with no special characters

# Check for video
assert is_video(Path("snapshot.mp4")) is True

# Path traversal prevention
user_db = safe_user_path(Path("/data"), "dave/proc.db")
assert user_db == Path("/data/dave/proc.db")

try:
    safe_user_path(Path("/data"), "../etc/passwd")
except ValueError:
    pass  # Correctly blocked
```

### Using `config.py`

```python
from snatched.config import load_config

config = load_config(Path("/app/snatched.toml"))

assert config.server.port == 8000
assert config.pipeline.batch_size == 500
assert config.pipeline.gps_window_seconds == 300
assert config.exif.enabled is True

if config.exif.enabled:
    logger.info("EXIF embedding enabled, using %s", config.exif.tool)
```

### Using `sqlite.py`

```python
from snatched.processing.sqlite import open_database, batch_insert
from pathlib import Path

# Open or create database
db = open_database(Path("/data/dave/proc.db"))

# Verify schema
tables = db.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
).fetchall()
table_names = [t[0] for t in tables]
assert 'assets' in table_names
assert 'matches' in table_names
assert 'reprocess_log' in table_names  # v3 addition

# Batch insert memories
rows = [
    ("mid-123", "2026-02-20 08:17:52 UTC", "2026-02-20T08:17:52+00:00",
     "photo", None, 39.5, -89.6, "https://..."),
    ("mid-124", "2026-02-21 10:30:00 UTC", "2026-02-21T10:30:00+00:00",
     "video", None, None, None, "https://..."),
]
inserted = batch_insert(
    db, "memories",
    ["mid", "date", "date_dt", "media_type", "location_raw", "lat", "lon", "download_link"],
    rows
)
assert inserted == 2
```

### Using `models.py`

```python
from snatched.models import JobCreate, JobStatus, Job, PipelineStats
from datetime import datetime

# Create a job request
job_req = JobCreate(
    upload_filename="snapchat-export-2026.zip",
    upload_size_bytes=100 * 1024 * 1024,  # 100MB
    phases_requested=["ingest", "match", "enrich", "export"],
    lanes_requested=["memories", "chats", "stories"],
)

# Create job from PostgreSQL row
job = Job(
    id=1,
    user_id=42,
    status=JobStatus.RUNNING,
    upload_filename=job_req.upload_filename,
    upload_size_bytes=job_req.upload_size_bytes,
    phases_requested=job_req.phases_requested,
    lanes_requested=job_req.lanes_requested,
    progress_pct=25,
    current_phase="ingest",
    created_at=datetime.now(),
)
assert job.status == JobStatus.RUNNING
assert job.progress_pct == 25

# Pydantic validation catches bad data
try:
    JobCreate(upload_filename="x", upload_size_bytes=-1,
              phases_requested=[], lanes_requested=[])
except Exception:
    pass  # upload_size_bytes must be > 0
```

---

## Acceptance Criteria

### `utils.py`

- [ ] All 16 functions import and have correct signatures
- [ ] `parse_snap_date("2026-02-20 08:17:52 UTC")` returns `datetime(2026, 2, 20, 8, 17, 52, tzinfo=UTC)`
- [ ] `parse_snap_date(None)` returns `None` (no crash)
- [ ] `parse_location("Latitude, Longitude: 39.56, -89.65")` returns `(39.56, -89.65)`
- [ ] `extract_mid("https://example.com?mid=abc-123")` returns `"abc-123"`
- [ ] `detect_real_format(webp_with_png_ext)` returns `".webp"`
- [ ] `sha256_file()` output matches `sha256sum` command
- [ ] `sanitize_filename("My<>File:Name")` returns a string with no illegal characters
- [ ] `safe_user_path(Path("/data"), "dave/proc.db")` returns `Path("/data/dave/proc.db")`
- [ ] `safe_user_path(Path("/data"), "../etc/passwd")` raises `ValueError`
- [ ] All 5 regex constants compile without error

### `config.py`

- [ ] `load_config()` returns `Config` with all defaults populated
- [ ] TOML file values override defaults
- [ ] Missing TOML file falls back to defaults (no error)
- [ ] `config.pipeline.batch_size` defaults to `500`
- [ ] `config.pipeline.gps_window_seconds` defaults to `300`

### `models.py`

- [ ] `JobCreate` rejects `upload_size_bytes <= 0`
- [ ] `JobStatus.RUNNING == "running"` (str enum)
- [ ] `PipelineStats` serializes to JSON and deserializes without loss
- [ ] Invalid `JobStatus` value raises Pydantic `ValidationError`

### `sqlite.py` + `schema.sql`

- [ ] `open_database(Path(":memory:"))` creates in-memory DB without error
- [ ] `open_database()` creates file and parent directories if absent
- [ ] Schema creates all 14 tables (12 core + 2 v3)
- [ ] All 18 indexes exist after `create_schema()`
- [ ] `PRAGMA journal_mode` returns `wal` after open
- [ ] `PRAGMA foreign_keys` returns `1` after open
- [ ] `assets.asset_type` CHECK constraint enforced (rejects unknown values)
- [ ] `batch_insert()` with 1,100 rows → 3 batches of 500/500/100
- [ ] `migrate_schema()` is idempotent — running twice does not error
- [ ] Migrations add `xmp_written`, `xmp_path` to `assets` if missing
- [ ] Migrations add `lane` column to `matches` if missing

---

## Implementation Notes

1. **Logger per module:**
   ```python
   import logging
   logger = logging.getLogger(__name__)
   ```

2. **Exception handling pattern:**
   ```python
   try:
       result = risky_operation()
   except Exception:
       logger.exception("Operation failed for %s", path, exc_info=True)
       raise
   ```

3. **TOML loading (Python 3.12 stdlib has `tomllib`):**
   ```python
   # Python 3.12+: use stdlib
   import tomllib
   with open("snatched.toml", "rb") as f:
       data = tomllib.load(f)
   # Python < 3.12: use tomli package
   import tomli
   with open("snatched.toml", "rb") as f:
       data = tomli.load(f)
   ```

4. **SQLite row factory for dict-like access:**
   ```python
   db.row_factory = sqlite3.Row
   # Now: row['column_name'] works
   ```

5. **SQL injection prevention — always parameterized queries:**
   ```python
   # Always
   db.execute("SELECT * FROM users WHERE username = ?", (username,))
   # Never
   db.execute(f"SELECT * FROM users WHERE username = '{username}'")
   ```
