# Spec 03 — Ingest (Phase 1)

## Module Overview

Phase 1 ingests all Snapchat export data into the per-user SQLite database. It parses 8 JSON source files (memories, chat, snaps, stories, snap_pro, friends, locations, places) and discovers all media files on disk (memories/, chat_media/, shared_story/).

The orchestrator (`phase1_ingest()`) coordinates 9 sub-functions plus asset discovery. Each sub-function is independently testable. Progress is reported via optional callback for web UI updates.

**This is a direct port of v2 code** (`/home/dave/tools/snapfix/snatched.py` lines 501–1247) with these adaptations:
- Replace hardcoded `INPUT_BASE` path with `input_dir` parameter
- Replace `print()` calls with optional `progress_cb()` callback
- Replace `sys.exit()` with exceptions (callers handle job failure)
- All paths use `pathlib.Path` (never strings)
- `Optional[X]` → `X | None`, `Dict[X,Y]` → `dict[X,Y]`, `List[X]` → `list[X]`

---

## Files to Create

```
snatched/
└── processing/
    └── ingest.py                  # ~600 lines: 12 functions + orchestrator
```

---

## Dependencies

**Build order:** Spec 01 (Foundation) and Spec 02 (Database Layer) must exist first.

**Python imports:**
```python
import json
import logging
import re
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable
import sqlite3

from snatched.utils import (
    MEMORY_RE, CHAT_FILE_RE, UUID_RE,
    parse_snap_date, parse_snap_date_iso, parse_snap_date_dateonly,
    parse_location, extract_mid, is_video,
    detect_real_format, is_fragmented_mp4, sha256_file,
)
from snatched.processing.sqlite import batch_insert, BATCH_SIZE

logger = logging.getLogger(__name__)
```

**Dependency on Spec 01:** Uses `sqlite3.Connection` returned by `open_database()`.
**Dependency on Spec 02:** Operates on the per-user SQLite schema created by `create_schema()`.

---

## V2 Source Reference

All functions ported from `/home/dave/tools/snapfix/snatched.py`:

| Function | V2 Lines | Notes |
|----------|----------|-------|
| `ingest_memories()` | 503–559 | Parse memories_history.json |
| `ingest_chat()` | 562–659 | Parse chat_history.json + explode media IDs |
| `ingest_snaps()` | 662–735 | Parse snap_history.json with dedup |
| `ingest_stories()` | 738–773 | Parse shared_story.json |
| `ingest_friends()` | 776–837 | Parse friends.json with priority dedup |
| `ingest_locations()` | 840–919 | Parse location_history.json + uncertainty format |
| `ingest_places()` | 922–1001 | Parse snap_map_places.json (flexible structure) |
| `ingest_snap_pro()` | 1004–1049 | Parse snap_pro.json (optional file) |
| `scan_assets()` | 1052–1197 | Scan memories/, chat_media/, shared_story/ |
| `phase1_ingest()` | 1200–1246 | Orchestrator |
| `extract_zips()` | 3534–3585 | ZIP extraction with path traversal protection |
| `discover_export()` | 3590–3692 | Find export structure in base_dir |
| `list_exports()` | 3695–3773 | Enumerate available exports |

---

## Function Signatures & Implementation Notes

### JSON Parsing Functions

```python
def ingest_memories(
    db: sqlite3.Connection,
    json_dir: Path,
    progress_cb: Callable[[str], None] | None = None,
) -> int:
    """Parse memories_history.json → memories table.

    Key behaviors:
    - Extracts mid from Download Link URL query parameter using extract_mid()
    - Parses date and location into discrete columns
    - Handles missing file gracefully (returns 0, logs warning)
    - Uses batch insert (BATCH_SIZE rows per commit)

    Args:
        db: SQLite connection
        json_dir: Directory containing memories_history.json
        progress_cb: Optional callback(message: str) for progress reporting

    Returns:
        int: Number of memories ingested (0 if file missing).

    SQL used:
        INSERT OR IGNORE INTO memories
            (mid, date, date_dt, media_type, location_raw, lat, lon, download_link)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)

    Implementation (v2 lines 503–559):
    - Open json_dir / 'memories_history.json'
    - Extract 'Saved Media' array
    - For each entry: extract mid from 'Download Link' URL,
      parse date via parse_snap_date_iso(), parse Location via parse_location()
    - Batch insert
    - Log: "{count:,} memories ingested ({gps_count:,} with GPS)"
    """
```

---

```python
def ingest_chat(
    db: sqlite3.Connection,
    json_dir: Path,
    progress_cb: Callable[[str], None] | None = None,
) -> int:
    """Parse chat_history.json → chat_messages + chat_media_ids tables.

    Key behaviors:
    - Ingests ALL message types including messages without media
      (fixes v1 bug where MEDIA-less messages were skipped)
    - Explodes pipe-separated Media IDs into separate rows in chat_media_ids
      for efficient joining in Phase 2 Strategy 1

    Args:
        db: SQLite connection
        json_dir: Directory containing chat_history.json
        progress_cb: Optional callback

    Returns:
        int: Number of chat messages ingested.

    SQL used:
        INSERT INTO chat_messages
            (conversation_id, from_user, media_type, media_ids, content,
             created, created_ms, is_sender, conversation_title, created_dt, created_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

        INSERT INTO chat_media_ids (chat_message_id, media_id) VALUES (?, ?)

    Implementation (v2 lines 562–659):
    - Open json_dir / 'chat_history.json' as dict of {conversation_id: [messages]}
    - For each conversation + message:
      - Parse created_raw via parse_snap_date_iso() and parse_snap_date_dateonly()
      - Normalize Media IDs: if list, join with ' | '; if string, use as-is
      - Insert row into chat_messages
    - After all inserts, explode Media IDs:
      SELECT id, media_ids FROM chat_messages WHERE media_ids IS NOT NULL AND media_ids != ''
      Split by '|', strip whitespace, insert each mid into chat_media_ids
    - Log: "{msg_count:,} messages from {total_convs} conversations"
    - Log: "{mid_count:,} exploded media IDs"
    """
```

---

```python
def ingest_snaps(
    db: sqlite3.Connection,
    json_dir: Path,
    progress_cb: Callable[[str], None] | None = None,
) -> int:
    """Parse snap_history.json → snap_messages table.

    Key behaviors:
    - Filters to IMAGE and VIDEO media types only (case-insensitive)
    - Deduplicates multi-recipient snaps using a composite key:
      (timestamp_ms // 100) | sender | media_type
      (10ms time bucket handles snaps sent within milliseconds of each other)

    Args:
        db: SQLite connection
        json_dir: Directory containing snap_history.json
        progress_cb: Optional callback

    Returns:
        int: Number of snaps ingested (after deduplication).

    SQL used:
        INSERT OR IGNORE INTO snap_messages
            (conversation_id, from_user, media_type, created, created_ms,
             is_sender, conversation_title, created_dt, created_date, dedup_key)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

    Implementation (v2 lines 662–735):
    - Open json_dir / 'snap_history.json'
    - Filter to IMAGE/VIDEO only (skip other types)
    - dedup_key = f"{created_ms // 100}|{from_user}|{media_type}"
      or fallback to created_raw if created_ms unavailable
    - INSERT OR IGNORE (dedup_key is UNIQUE in schema)
    - Log: "{count:,} snap messages ({img_count:,} images, {vid_count:,} videos)"
    - Log: "{dupes:,} duplicates suppressed"
    """
```

---

```python
def ingest_stories(
    db: sqlite3.Connection,
    json_dir: Path,
    progress_cb: Callable[[str], None] | None = None,
) -> int:
    """Parse shared_story.json → stories table.

    Args:
        db: SQLite connection
        json_dir: Directory containing shared_story.json
        progress_cb: Optional callback

    Returns:
        int: Number of stories ingested (0 if file missing).

    SQL used:
        INSERT INTO stories (story_id, created, created_dt, content_type)
        VALUES (?, ?, ?, ?)

    Implementation (v2 lines 738–773):
    - Open json_dir / 'shared_story.json'
    - Extract 'Shared Story' array
    - For each entry: extract 'Story Id', 'Created', 'Content Type'
    - Parse created_raw → created_dt via parse_snap_date_iso()
    - Uppercase content_type (IMAGE, VIDEO)
    - Batch insert
    - Log: "{count:,} shared stories ingested"
    """
```

---

```python
def ingest_friends(
    db: sqlite3.Connection,
    json_dir: Path,
    progress_cb: Callable[[str], None] | None = None,
) -> int:
    """Parse friends.json → friends table.

    Deduplication: For each username, selects best entry:
    1. Prefer entries with non-empty display_name
    2. Among ties, prefer lower category priority:
       Friends=0, Shortcuts=1, Deleted Friends=2, Blocked Users=3, Ignored=4

    Args:
        db: SQLite connection
        json_dir: Directory containing friends.json
        progress_cb: Optional callback

    Returns:
        int: Number of unique friends ingested.

    SQL used:
        INSERT OR IGNORE INTO friends (username, display_name, category)
        VALUES (?, ?, ?)

    Implementation (v2 lines 776–837):
    - Open json_dir / 'friends.json' as dict of {category: [entries]}
    - Category priority: Friends=0, Shortcuts=1, Deleted Friends=2,
      Blocked Users=3, Ignored Snaps From=4
    - Collect all candidates per username
    - Sort by (not has_display_name, category_priority): best first
    - Insert only the best entry per username
    - Log: "{count:,} friends ingested (deduplicated)"
    - Log: "Categories: {cat_str}"
    """
```

---

```python
def ingest_locations(
    db: sqlite3.Connection,
    json_dir: Path,
    progress_cb: Callable[[str], None] | None = None,
) -> int:
    """Parse location_history.json → locations table.

    Handles the '± accuracy' format added in newer Snapchat exports
    (key fix from v2 — was previously skipping these entries).

    Parsed formats:
    - Simple: '39.66, -89.65'
    - With uncertainty: '39.66 ± 14.22, -89.65 ± 14.22'
    - With unit: '39.66 meters ± 14.22, -89.65 meters ± 14.22'

    Args:
        db: SQLite connection
        json_dir: Directory containing location_history.json
        progress_cb: Optional callback

    Returns:
        int: Number of GPS breadcrumbs ingested.

    SQL used:
        INSERT INTO locations (timestamp, timestamp_unix, lat, lon, accuracy_m)
        VALUES (?, ?, ?, ?, ?)

    Implementation (v2 lines 840–919):
    - Open json_dir / 'location_history.json'
    - Extract 'Location History' array
    - Each entry is [timestamp_str, coords_str]
    - Parse timestamp via parse_snap_date(), convert to unix epoch
    - Parse coords_str: strip uncertainty (±NNN) to get raw lat, lon
    - Extract accuracy_m from uncertainty value if present
    - Sort all rows by timestamp_unix before inserting
    - Log: "{count:,} location breadcrumbs"
    - Log: "{bad:,} entries skipped (parse failures)"
    """
```

---

```python
def ingest_places(
    db: sqlite3.Connection,
    json_dir: Path,
    progress_cb: Callable[[str], None] | None = None,
) -> int:
    """Parse snap_map_places.json → places table.

    Handles multiple JSON structures (Snapchat is inconsistent across exports):
    - Direct list of place dicts
    - Dict with key 'Snap Map Places', 'Places', or 'places'
    - Nested dict where any value is a list

    Args:
        db: SQLite connection
        json_dir: Directory containing snap_map_places.json
        progress_cb: Optional callback

    Returns:
        int: Number of places ingested (0 if file missing).

    SQL used:
        INSERT INTO places (name, lat, lon, address, visit_count)
        VALUES (?, ?, ?, ?, ?)

    Implementation (v2 lines 922–1001):
    - Open json_dir / 'snap_map_places.json'
    - Detect structure and extract list of place dicts
    - For each place dict:
      - name from 'Name' or 'name'
      - lat/lon from 'Latitude'/'Longitude' or 'Location' string
      - address from 'Address' or 'address'
      - visit_count from 'Number of Visits' or 'visit_count'
    - Log: "{count:,} places ingested"
    """
```

---

```python
def ingest_snap_pro(
    db: sqlite3.Connection,
    json_dir: Path,
    progress_cb: Callable[[str], None] | None = None,
) -> int:
    """Parse snap_pro.json → snap_pro table.

    This file is optional — not all Snapchat exports include it.

    Args:
        db: SQLite connection
        json_dir: Directory containing snap_pro.json
        progress_cb: Optional callback

    Returns:
        int: Number of snap_pro entries ingested (0 if file missing).

    SQL used:
        INSERT INTO snap_pro (url, created, created_dt, title)
        VALUES (?, ?, ?, ?)

    Implementation (v2 lines 1004–1049):
    - Check if json_dir / 'snap_pro.json' exists; return 0 if not
    - Extract entry list from flexible JSON structure (same approach as places)
    - For each entry: extract url, created, title
    - Parse created via parse_snap_date_iso()
    - Log: "{count:,} snap pro entries ingested"
    """
```

---

### Asset Discovery

```python
def scan_assets(
    db: sqlite3.Connection,
    input_dir: Path,
    config: dict | None = None,
    progress_cb: Callable[[str], None] | None = None,
) -> int:
    """Scan memories/, chat_media/, shared_story/ for media files.

    Extracts metadata from filename patterns and file magic bytes:
    - Memory: YYYYMMDD_HHmmss-{uuid}-{overlay|main}.{ext}
    - Chat:   YYYYMMDD_HHmmss-{file_id}.{ext}
    - Story:  YYYYMMDD_HHmmss-{file_id}.{ext}

    Detections per file:
    - video vs image (VIDEO_EXTS set + magic bytes)
    - real file format (magic bytes vs extension — e.g., WebP saved as .jpg)
    - fragmented MP4 requiring ffmpeg remux (fMP4 marker in bytes)
    - SHA-256 hash
    - file size

    Args:
        db: SQLite connection
        input_dir: Root export directory (parent of memories/, chat_media/, etc.)
        config: Optional dict with keys:
            - 'scan_siblings': bool — also scan sibling directories' memories/
        progress_cb: Optional callback

    Returns:
        int: Number of asset files scanned and inserted.

    SQL used:
        INSERT OR IGNORE INTO assets
            (path, filename, date_str, file_id, ext, real_ext,
             asset_type, is_video, is_fmp4, memory_uuid, file_size, sha256)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

    Implementation (v2 lines 1052–1197):
    - Scan directories: input_dir/memories, input_dir/chat_media, input_dir/shared_story
    - If config.get('scan_siblings'): also scan sibling dirs' memories/
    - For each file found:
      * Match against MEMORY_RE → asset_type='memory_main' or 'memory_overlay'
        extract memory_uuid from filename
      * Match against CHAT_FILE_RE → asset_type='chat' or 'story'
        extract file_id from filename
      * Parse date_str from filename (YYYYMMDD prefix)
      * Run detect_real_format() — record real_ext if mismatch
      * Run is_fragmented_mp4() — record is_fmp4
      * Compute sha256_file()
      * INSERT OR IGNORE (path is UNIQUE)
    - Progress every 100 files: "{total:,} files | {MB:.0f} MB | {rate:.0f} files/s"
    - Log summary: "{count:,} assets scanned ({MB:.0f} MB, {elapsed:.1f}s)"
    - Log: "Types: {type_str}", "Videos: {vid_count:,}", "fMP4: {fmp4_count:,}"
    """
```

---

### ZIP Handling and Export Discovery

```python
def extract_zips(
    input_path: Path,
    scratch_dir: Path,
    source_filter: str | None = None,
) -> Path:
    """Extract Snapchat export ZIP file(s) with path traversal protection.

    Args:
        input_path: Path to a single ZIP file or directory containing ZIPs
        scratch_dir: Target directory for extraction
        source_filter: Optional comma-separated export IDs to include.
            Only ZIPs whose filename contains a matching ID are extracted.
            Example: '1771628972897,1771628972898'

    Returns:
        Path: scratch_dir (extraction destination).

    Raises:
        ValueError: If input_path does not exist.
        ValueError: If a file is not a valid ZIP.
        ValueError: If any ZIP member path starts with '/' or contains '..'.
        ValueError: If extracted path would escape scratch_dir.

    Security (from v2 lines 3534–3585):
    - Reject member paths starting with '/'
    - Reject member paths containing '..'
    - Verify resolved path stays within scratch_dir using Path.resolve()
    """
```

---

```python
def discover_export(
    base_dir: Path,
) -> dict | None:
    """Find Snapchat export directory structure within base_dir.

    Returns a structure dict with keys:
    - 'primary': Path — primary export directory (has json/memories_history.json)
    - 'secondaries': list[Path] — secondary export directories (have memories/ only)
    - 'overlays_dir': Path | None — overlays-merged/ directory
    - 'json_dir': Path — primary/json/ subdirectory
    - 'memories_dirs': list[Path] — all memories/ paths (primary + secondaries)
    - 'chat_dir': Path | None — primary/chat_media/
    - 'story_dir': Path | None — primary/shared_story/
    - 'html_dir': Path | None — primary/html/

    Returns None if no valid export structure found.

    Logic (v2 lines 3590–3692):
    1. Check if base_dir itself has json/memories_history.json → primary
    2. Scan base_dir children:
       - 'overlays-merged/' → overlays_dir
       - {child}/json/memories_history.json → primary candidate
       - {child}/memories/ (no json/) → secondary
    3. If still no primary, recurse one level deeper
    4. Return None if no primary found
    """
```

---

```python
def list_exports(
    root: Path,
) -> list[dict]:
    """Scan root directory for all available Snapchat exports (dirs and ZIPs).

    Returns a list of dicts, each with:
    - 'path': Path — export directory or ZIP file
    - 'export_id': str — ID extracted from filename (after last '~')
    - 'name': str — directory or ZIP stem name
    - 'type': 'full' | 'memories-only'
    - 'is_zip': bool
    - 'mem_count': int — files in memories/
    - 'chat_count': int — files in chat_media/
    - 'story_count': int — files in shared_story/
    - 'size_mb': float — ZIP size in MB (ZIPs only)

    Useful for presenting a selection UI before processing.

    Implementation (v2 lines 3695–3773):
    - Scan root for directories with json/memories_history.json or memories/
    - Scan root for *.zip files
    - Extract export_id from filename (part after last '~')
    - Count files in each subdirectory
    """
```

---

## Orchestrator

```python
def phase1_ingest(
    db: sqlite3.Connection,
    input_dir: Path,
    json_dir: Path,
    config: dict | None = None,
    progress_cb: Callable[[str], None] | None = None,
) -> dict[str, int]:
    """Phase 1 orchestrator: Ingest all Snapchat data sources into SQLite.

    Calls all ingest functions in order:
    1. ingest_memories()
    2. ingest_chat()
    3. ingest_snaps()
    4. ingest_stories()
    5. ingest_friends()
    6. ingest_locations()
    7. ingest_places()
    8. ingest_snap_pro()
    9. scan_assets()

    Reports progress via callback after each function.
    Missing JSON files are warned (not errors) — returns 0 count for them.

    Args:
        db: SQLite connection (already open)
        input_dir: Root export directory (parent of memories/, chat_media/, etc.)
        json_dir: Directory containing all JSON source files
        config: Optional config dict (e.g., {'scan_siblings': True})
        progress_cb: Optional callback(message: str) for web UI progress updates

    Returns:
        dict[str, int]: Per-source counts:
        {
            'memories': int,
            'chat_messages': int,
            'snap_messages': int,
            'stories': int,
            'friends': int,
            'locations': int,
            'places': int,
            'snap_pro': int,
            'assets': int,
        }

    Implementation (v2 lines 1200–1246):
    - Call each ingest function, collect counts
    - Log per-table counts via progress_cb or logger
    - Log database file size after completion
    - Return stats dict
    """
```

---

## Database Schema

The full SQLite DDL lives in `snatched/processing/schema.sql`. All tables populated by Phase 1 are listed below with complete DDL:

```sql
-- MEMORIES: Populated by ingest_memories()
CREATE TABLE IF NOT EXISTS memories (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    mid          TEXT UNIQUE,
    date         TEXT,
    date_dt      TEXT,
    media_type   TEXT,
    location_raw TEXT,
    lat          REAL,
    lon          REAL,
    download_link TEXT
);

-- CHAT_MESSAGES: Populated by ingest_chat()
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

-- CHAT_MEDIA_IDS: Populated by ingest_chat() — exploded from chat_messages.media_ids
CREATE TABLE IF NOT EXISTS chat_media_ids (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_message_id INTEGER NOT NULL REFERENCES chat_messages(id),
    media_id        TEXT NOT NULL
);

-- SNAP_MESSAGES: Populated by ingest_snaps()
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
    dedup_key       TEXT UNIQUE   -- prevents multi-recipient snap duplication
);

-- ASSETS: Populated by scan_assets()
CREATE TABLE IF NOT EXISTS assets (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    path         TEXT NOT NULL UNIQUE,
    filename     TEXT NOT NULL,
    date_str     TEXT,
    file_id      TEXT,
    ext          TEXT NOT NULL,
    real_ext     TEXT,
    asset_type   TEXT NOT NULL
                 CHECK(asset_type IN ('memory_main', 'memory_overlay', 'chat',
                                     'chat_overlay', 'chat_thumbnail', 'story')),
    is_video     BOOLEAN NOT NULL DEFAULT 0,
    is_fmp4      BOOLEAN NOT NULL DEFAULT 0,
    memory_uuid  TEXT,
    file_size    INTEGER,
    sha256       TEXT,
    -- ... output columns updated by Phase 3/4 ...
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
```

---

## Key SQL Queries

```sql
-- Count by asset type (progress reporting after scan_assets)
SELECT asset_type, COUNT(*) FROM assets GROUP BY asset_type ORDER BY COUNT(*) DESC;

-- Count videos
SELECT COUNT(*) FROM assets WHERE is_video = 1;

-- Count format mismatches
SELECT COUNT(*) FROM assets WHERE real_ext IS NOT NULL;

-- Count fMP4 files needing remux
SELECT COUNT(*) FROM assets WHERE is_fmp4 = 1;

-- Count memories with GPS
SELECT COUNT(*) FROM memories WHERE lat IS NOT NULL;

-- Chat message distribution by media type
SELECT media_type, COUNT(*) FROM chat_messages
GROUP BY media_type ORDER BY COUNT(*) DESC;

-- Count exploded media IDs (should be >= chat messages with media)
SELECT COUNT(*) FROM chat_media_ids;

-- Count snap messages after dedup
SELECT COUNT(*), COUNT(DISTINCT from_user) FROM snap_messages;

-- Location breadcrumb date range
SELECT MIN(timestamp), MAX(timestamp) FROM locations;
```

---

## Multi-User Adaptation

All v2 ingest logic is single-user with hardcoded paths. v3 adaptations:

1. **Parameterized paths** — Replace hardcoded `INPUT_BASE` with `input_dir` parameter:
   ```python
   # v2
   INPUT_BASE = Path("/mnt/nas-pool/snapchat-input")
   ingest_memories(db, INPUT_BASE / "json")

   # v3
   def ingest_memories(db: sqlite3.Connection, json_dir: Path, ...) -> int:
       # json_dir is always within user's data directory
       # Validated via safe_user_path() before this call
   ```

2. **Progress callback** — Replace `print()` with optional callback:
   ```python
   # v2
   print(f"  ✓ {count:,} memories ingested")

   # v3
   if progress_cb:
       progress_cb(f"{count:,} memories ingested")
   else:
       logger.info("%d memories ingested", count)
   ```

3. **Exception-based errors** — Replace `sys.exit()` with exceptions:
   ```python
   # v2
   sys.exit(f"ERROR: {msg}")

   # v3
   raise RuntimeError(f"Ingest failed: {msg}")
   # Caller (jobs.py) catches and updates job status to 'failed'
   ```

4. **Isolated SQLite** — Each user gets their own DB at `/data/{username}/proc.db`.
   No changes needed inside the ingest functions themselves; isolation is enforced by the caller.

---

## Code Examples

### Running Phase 1 in the pipeline

```python
from pathlib import Path
from snatched.processing.sqlite import open_database
from snatched.processing.ingest import phase1_ingest

# Open user's DB
db = open_database(Path("/data/dave/proc.db"))

# Point to their extracted export
input_dir = Path("/data/dave/processing/snapchat-export-20260220")
json_dir  = input_dir / "json"

# Define progress callback (for SSE streaming to browser)
def on_progress(msg: str):
    logger.info("[Phase 1] %s", msg)

# Run ingest
stats = phase1_ingest(
    db=db,
    input_dir=input_dir,
    json_dir=json_dir,
    config={"scan_siblings": False},
    progress_cb=on_progress,
)

print(f"Phase 1 complete: {stats['assets']:,} assets, {stats['memories']:,} memories")
```

### Testing individual ingest functions

```python
import sqlite3
from pathlib import Path
from snatched.processing.sqlite import open_database
from snatched.processing.ingest import ingest_memories, ingest_chat

db = open_database(Path(":memory:"))

# Test memories
json_dir = Path("/tmp/test-export/json")
count = ingest_memories(db, json_dir)
assert count >= 0  # 0 if file missing, > 0 if found

# Verify table populated
rows = db.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
assert rows == count

# Test chat — verify media IDs are exploded
count = ingest_chat(db, json_dir)
mid_count = db.execute("SELECT COUNT(*) FROM chat_media_ids").fetchone()[0]
assert mid_count >= 0
```

### ZIP extraction with security validation

```python
from pathlib import Path
from snatched.processing.ingest import extract_zips

# Extract a single ZIP
scratch = Path("/data/dave/processing")
result = extract_zips(
    input_path=Path("/data/dave/uploads/snapchat-export-20260220.zip"),
    scratch_dir=scratch,
)
assert result == scratch

# Path traversal is rejected
try:
    extract_zips(Path("/bad.zip"), scratch)
except ValueError as e:
    pass  # ZIP containing '../etc/passwd' is rejected
```

---

## Acceptance Criteria

- [ ] `ingest_memories()` parses memories_history.json, extracts mid from Download Link URL
- [ ] `ingest_memories()` returns 0 gracefully if file is missing (no crash)
- [ ] `ingest_chat()` parses all message types including messages without media
- [ ] `ingest_chat()` explodes pipe-separated Media IDs into chat_media_ids table
- [ ] `ingest_snaps()` deduplicates multi-recipient snaps by 10ms time bucket
- [ ] `ingest_snaps()` filters to IMAGE and VIDEO only
- [ ] `ingest_stories()` parses shared_story.json correctly
- [ ] `ingest_friends()` deduplicates by username, selects best entry by priority
- [ ] `ingest_locations()` parses '39.66 ± 14.22, -89.65 ± 14.22' format correctly
- [ ] `ingest_locations()` populates accuracy_m column when uncertainty present
- [ ] `ingest_places()` handles direct list, dict-with-key, and nested dict structures
- [ ] `ingest_snap_pro()` returns 0 gracefully if snap_pro.json is missing
- [ ] `scan_assets()` detects real file format via magic bytes (not just extension)
- [ ] `scan_assets()` sets `real_ext` when format differs from extension
- [ ] `scan_assets()` computes SHA-256 hash for every file
- [ ] `scan_assets()` correctly classifies memory_main vs memory_overlay by filename
- [ ] `extract_zips()` rejects member paths starting with '/'
- [ ] `extract_zips()` rejects member paths containing '..'
- [ ] `extract_zips()` rejects paths that resolve outside scratch_dir
- [ ] `discover_export()` finds primary + secondary directories
- [ ] `discover_export()` returns None when no export found
- [ ] `phase1_ingest()` orchestrates all 9 functions and returns count dict
- [ ] `phase1_ingest()` calls progress_cb after each sub-function
- [ ] All functions use `pathlib.Path` (no string path manipulation)
- [ ] All functions use parameterized SQL (no string interpolation)
- [ ] Batch size = `BATCH_SIZE` (500) for all insertions
- [ ] Missing JSON files log a warning — they do NOT raise exceptions
