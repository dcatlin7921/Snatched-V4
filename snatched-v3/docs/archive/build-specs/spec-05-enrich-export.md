# Spec 05 — Enrich + Export + XMP

## Module Overview

This spec covers three interconnected modules forming Phase 3 (Enrichment) and Phase 4 (Export):

1. **`snatched/processing/enrich.py`** — Enriches all best matches with GPS coordinates, display names, output file paths, and EXIF metadata tags
2. **`snatched/processing/export.py`** — Copies files to output directories, embeds EXIF metadata, burns overlays, and exports chat transcripts + PNG renders
3. **`snatched/processing/xmp.py`** — Generates XMP sidecar files alongside media (alternative to embedded EXIF)

Together, these modules transform database rows into finalized exported files with complete metadata.

**Chat PNG rendering** is handled by `snatched/processing/chat_renderer.py` (separate module). The `ChatRenderer` class is imported by `export.py`'s `export_chat_png()` function. The chat renderer uses Pillow to generate high-resolution PNG screenshots (2880×5120 px, 600 DPI) of full conversation threads, with dark mode support. Its source is `/home/dave/tools/snapfix/chat_renderer.py`.

---

## Files to Create

```
snatched/
└── processing/
    ├── enrich.py              # Phase 3: GPS, names, paths, EXIF tags
    ├── export.py              # Phase 4: copy, EXIF embed, overlays, chat exports
    ├── xmp.py                 # XMP sidecar generator
    └── chat_renderer.py       # Chat PNG renderer (ported from chat_renderer.py)
```

---

## Dependencies

**Build order:** Spec 01 (Foundation), Spec 02 (Database Layer), Spec 03 (Ingest), Spec 04 (Match) must exist first. Phase 3/4 require Phase 1+2 to have run and the matches table to have is_best=1 rows.

**Python imports for `enrich.py`:**
```python
import sqlite3
import json
import logging
import time
from bisect import bisect_left
from pathlib import Path
from typing import Callable

from snatched.config import Config
from snatched.utils import sanitize_filename, parse_iso_dt, exif_dt, gps_tags, date_tags

logger = logging.getLogger(__name__)
```

**Python imports for `export.py`:**
```python
import sqlite3
import json
import logging
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

from snatched.config import Config
from snatched.utils import sha256_file, is_video
from snatched.processing.chat_renderer import ChatRenderer

logger = logging.getLogger(__name__)
```

**Python imports for `xmp.py`:**
```python
import logging
import sqlite3
import time
from pathlib import Path
from typing import Callable
from xml.sax.saxutils import escape as escape_xml

from snatched.config import Config

logger = logging.getLogger(__name__)
```

**External system binaries (all optional — phases degrade gracefully):**
- `exiftool` — EXIF metadata embedding
- `ffmpeg` — fMP4 remux + video overlay compositing
- `magick` or `composite` (ImageMagick) — image overlay compositing

**External Python packages:**
- `Pillow` — used by `chat_renderer.py` for PNG rendering

---

## V2 Source Reference

All functions ported from `/home/dave/tools/snapfix/snatched.py`:

### Phase 3 (enrich.py)

| Function | V2 Lines | Description |
|----------|----------|-------------|
| `_load_location_timeline(db)` | 1652–1664 | Load GPS breadcrumbs for binary search |
| `_find_nearest_location(...)` | 1667–1683 | Binary search within GPS_WINDOW |
| `enrich_gps(db, ...)` | 1686–1766 | Enrich GPS for all best matches |
| `_resolve_conversation_name(...)` | 1769–1791 | Conversation name fallback chain |
| `_build_chat_folder_map(db)` | 1794–1915 | Build conv_id → folder name map |
| `enrich_display_names(db)` | 1918–1994 | Resolve contact display names |
| `enrich_output_paths(db)` | 1997–2113 | Compute output file paths |
| `enrich_exif_tags(db)` | 2116–2233 | Build EXIF tag dicts |
| `phase3_enrich(db, project_dir)` | 2236–2288 | Phase 3 orchestrator |

### Phase 4 (export.py)

| Function | V2 Lines | Description |
|----------|----------|-------------|
| `_copy_files(db, project_dir, args)` | 2293–2445 | Copy + remux files |
| `_write_exif(db, project_dir, args)` | 2448–2589 | EXIF embed via exiftool |
| `_burn_overlays(db, project_dir, args)` | 2592–2707 | Overlay compositing |
| `_export_text(db, project_dir, args)` | 2710–3004 | Chat text + PNG export |
| `_write_reports(db, project_dir, args, stats)` | 3007–3367 | Report generation |
| `phase4_export(db, project_dir, args)` | 3370–3455 | Phase 4 orchestrator |

### Chat renderer (chat_renderer.py)

| Item | Source |
|------|--------|
| `ChatRenderer` class | `/home/dave/tools/snapfix/chat_renderer.py` |
| Purpose | Generate hi-res PNG screenshots of full conversation threads |
| Output | 2880×5120 px at 600 DPI per page |
| Dependencies | Pillow (PIL) |

---

## Function Signatures

### `snatched/processing/enrich.py`

```python
def load_location_timeline(
    db: sqlite3.Connection,
) -> tuple[list[int], list[float], list[float]]:
    """Load GPS breadcrumbs from locations table for binary search.

    Returns three parallel lists sorted by timestamp:
        (timestamps_unix, latitudes, longitudes)

    Returns empty lists if no location data exists.
    """


def find_nearest_location(
    target_unix: int,
    timestamps: list[int],
    lats: list[float],
    lons: list[float],
    gps_window: int = 300,
) -> tuple[float, float] | None:
    """Binary search for nearest GPS location within time window.

    Uses bisect_left to find insertion point, then checks ±1 neighbors.

    Args:
        target_unix: Target timestamp (seconds since epoch)
        timestamps: Sorted list of GPS timestamps (from load_location_timeline)
        lats: Parallel list of latitudes
        lons: Parallel list of longitudes
        gps_window: Maximum allowed time difference in seconds (default 300 = ±5 min)

    Returns:
        (lat, lon) if a match within window is found, None otherwise.
    """


def enrich_gps(
    db: sqlite3.Connection,
    timestamps: list[int],
    lats: list[float],
    lons: list[float],
    gps_window: int = 300,
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    """Enrich GPS for all best matches using two-pass strategy.

    Pass 1: GPS already set from memory metadata (strategy 2: memory_uuid)
            — count existing matched_lat IS NOT NULL.
    Pass 2: For matches with no GPS, do binary search against location timeline.
            Update matches.matched_lat, matches.matched_lon, matches.gps_source='location_history'.

    Args:
        db: SQLite connection
        timestamps, lats, lons: From load_location_timeline()
        gps_window: Max seconds for location match (default 300)
        progress_cb: Optional progress callback

    Returns:
        {
            'memory_gps': int,      # Already had GPS from memory metadata
            'location_gps': int,    # Added from location history
            'no_gps': int,          # No GPS available
            'elapsed': float,
        }
    """


def resolve_conversation_name(
    conv_title: str | None,
    conv_id: str,
    friends_map: dict[str, str],
    from_user: str | None = None,
) -> str:
    """Determine human-readable conversation name with fallback chain.

    Fallback order (first non-empty result wins):
    1. conv_title if non-empty and not a UUID
    2. friends_map[conv_id] if conv_id is not a UUID
    3. conv_id itself if it's not a UUID
    4. friends_map[from_user] if from_user is known
    5. from_user as-is if provided
    6. 'Unknown'

    Result is passed through sanitize_filename() before return.

    Args:
        conv_title: conversation_title from chat_messages
        conv_id: conversation_id (may be UUID or username)
        friends_map: dict[username] → display_name from friends table
        from_user: Sender of message (for 1:1 fallback)

    Returns:
        Filesystem-safe human-readable name string.
    """


def build_chat_folder_map(db: sqlite3.Connection) -> dict[str, str]:
    """Build conversation_id → rich folder name mapping.

    Iterates all distinct conversations in chat_messages.
    For each: calls resolve_conversation_name().
    Deduplicates folder names by appending numeric suffix (_2, _3, ...).

    Used by both enrich_output_paths() and export_chat_text()/export_chat_png()
    to ensure the same parent folder name everywhere.

    This map is NOT persisted to the database — rebuilt on each Phase 3 run.

    Returns:
        dict: {conversation_id: folder_name, ...}
        Example:
        {
            'uuid-1234': 'Alice Smith 2025',
            'uuid-5678': 'Group - Alice Bob Carol',
            'dave_username': 'Unknown',
        }
    """


def enrich_display_names(
    db: sqlite3.Connection,
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    """Resolve display names for chat/snap matches from friends table.

    For each best match linked to a chat_message or snap_message:
    - display_name: friend's display_name, or '@username' fallback
    - creator_str: 'Display Name (@username)' or '@username'
    - direction: 'sent' (is_sender=1) or 'received' (is_sender=0)
    - conversation: resolved name from build_chat_folder_map()

    Updates matches table in bulk via batch UPDATE.

    Returns:
        {'resolved': int, 'elapsed': float}
    """


def enrich_output_paths(
    db: sqlite3.Connection,
    config: Config,
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    """Compute output_subdir and output_filename for every best match.

    Path structure by asset type:
    - memory_main/overlay:
        memories/{YYYY}/{MM}/Snap_Memory_{YYYY-MM-DD}_{HHMMSS}{ext}
    - chat:
        chat/{CONVERSATION}/Media/Snap_Chat_{YYYY-MM-DD}_{HHMMSS}{ext}
    - story:
        stories/Snap_Story_{YYYY-MM-DD}_{HHMMSS}{ext}
    - unmatched:
        unmatched/Snap_{ASSETTYPE}_{STEM}{ext}

    Handles filename collisions by appending _2, _3, etc.
    Uses real_ext over ext when file format was misidentified.

    Args:
        db: SQLite connection
        config: Config object (may contain output path preferences)
        progress_cb: Optional progress callback

    Returns:
        {'computed': int, 'elapsed': float}
    """


def enrich_exif_tags(
    db: sqlite3.Connection,
    config: Config,
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    """Build exif_tags_json for every best match.

    Constructs EXIF tag dict combining:
    - Date tags (from matched_date) via date_tags()
    - GPS tags (from matched_lat/matched_lon) via gps_tags()
    - Creator/XPAuthor (from creator_str)
    - Conversation/XPComment (from conversation)
    - Software = 'Snatched v3.0'
    - FileID (from assets.file_id or assets.memory_uuid)

    Stores as JSON string in matches.exif_tags_json.
    Phase 4 reads this to drive exiftool batch embedding.

    Returns:
        {
            'built': int,       # Matches processed
            'with_gps': int,    # Had GPS coordinates
            'with_date': int,   # Had date metadata
            'elapsed': float,
        }
    """


def phase3_enrich(
    db: sqlite3.Connection,
    project_dir: Path,
    config: Config,
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    """Phase 3 orchestrator: Enrich all best matches.

    Sequentially calls:
    1. load_location_timeline()
    2. enrich_gps()
    3. enrich_display_names()
    4. enrich_output_paths()
    5. enrich_exif_tags()

    Args:
        db: SQLite connection (Phase 2 must have run first)
        project_dir: Project directory (input/output root for this user)
        config: Application configuration
        progress_cb: Optional progress callback

    Returns:
        {
            'total': int,
            'gps_metadata': int,
            'gps_location_history': int,
            'gps_none': int,
            'names_resolved': int,
            'paths_computed': int,
            'tags_built': int,
            'elapsed': float,
        }
    """
```

---

### `snatched/processing/export.py`

```python
def copy_files(
    db: sqlite3.Connection,
    project_dir: Path,
    config: Config,
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    """Copy all best-matched assets to their computed output paths.

    For each best match with output_subdir + output_filename set:
    - Constructs full destination path: project_dir/output/{subdir}/{filename}
    - Creates parent directories if needed
    - If asset.is_fmp4 AND ffmpeg available: remux with 'ffmpeg -c copy'
    - Otherwise: shutil.copy2()
    - For non-remuxed copies: verify SHA-256 matches source

    Updates assets table:
    - output_path = final destination path (absolute)
    - output_sha256 = SHA-256 of copied file (if not remuxed)

    Args:
        db: SQLite connection
        project_dir: Root project directory
        config: Configuration (test_mode, test_count for limiting during dev)
        progress_cb: Optional progress callback

    Returns:
        {
            'copied': int,     # Files successfully copied
            'remuxed': int,    # fMP4 files remuxed with ffmpeg
            'verified': int,   # Files with matching SHA-256
            'errors': int,     # Files that failed
            'elapsed': float,
        }
    """


def write_exif(
    db: sqlite3.Connection,
    project_dir: Path,
    config: Config,
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    """Embed EXIF tags into copied files using exiftool stay_open batch mode.

    Uses exiftool in -stay_open mode for performance:
    - Single long-running exiftool process
    - Tags sent via stdin pipe, no subprocess per file
    - Skips files without exif_tags_json or without output_path
    - Skips silently if exiftool binary not found (degrades gracefully)

    For video files: adds '-api QuickTimeUTC' flag.
    Always uses: '-overwrite_original -ignoreMinorErrors'.

    Updates assets table:
    - exif_written = 1 on success, 0 on error
    - exif_error = exiftool stderr message if failure

    Returns:
        {
            'written': int,    # Files with EXIF successfully embedded
            'errors': int,     # Files that failed
            'skipped': int,    # Files with no tags or missing output_path
            'elapsed': float,
        }
    """


def burn_overlays(
    db: sqlite3.Connection,
    project_dir: Path,
    config: Config,
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    """Burn overlay PNGs onto their corresponding main memory files.

    Pairs memory_main (output copy) + memory_overlay (source PNG)
    by matching assets.memory_uuid.

    For images: ImageMagick 'composite -compose Over overlay.png main.jpg result.jpg'
    For videos: ffmpeg 'filter_complex overlay=0:0' to composite overlay onto video
    After video burn: re-embed EXIF if exif_tags_json is available.

    Skips silently if ImageMagick/ffmpeg not available (degrades gracefully).

    Returns:
        {
            'burned': int,    # Overlays successfully composited
            'errors': int,    # Failed overlays
            'elapsed': float,
        }
    """


def export_chat_text(
    db: sqlite3.Connection,
    project_dir: Path,
    config: Config,
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    """Export per-conversation chat transcripts as plain text files.

    Output path: project_dir/output/chat/{CONVERSATION}/Transcripts/{CONVERSATION}.txt

    File format:
    ```
    === Conversation: {title} ===
    Partner: @{username} ({display_name})
    Messages: {count}
    Date range: YYYY-MM-DD to YYYY-MM-DD
    ================================================================

    [YYYY-MM-DD HH:MM:SS] SenderName: Message text
    [YYYY-MM-DD HH:MM:SS] SenderName: [MEDIA: image]
    [YYYY-MM-DD HH:MM:SS] SenderName: [MEDIA: video]
    ```

    One file per unique conversation_id. Uses build_chat_folder_map()
    for consistent folder naming with enrich_output_paths().

    Args:
        db: SQLite connection
        project_dir: Root project directory
        config: Configuration (skip_chat_text flag to disable)
        progress_cb: Optional progress callback

    Returns:
        {
            'conversations': int,    # Conversations exported
            'messages': int,         # Total messages written
            'elapsed': float,
        }
    """


def export_chat_png(
    db: sqlite3.Connection,
    project_dir: Path,
    config: Config,
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    """Export per-conversation chat as high-resolution PNG screenshots.

    Output path: project_dir/output/chat/{CONVERSATION}/Saved Chat Screenshots/page-{N:04d}.png

    Each page: 2880×5120 px at 600 DPI.
    Uses ChatRenderer class from snatched/processing/chat_renderer.py.
    Dark mode controlled by config.lanes['chats'].dark_mode.

    Skips silently if Pillow not available.

    Args:
        db: SQLite connection
        project_dir: Root project directory
        config: Configuration (dark_mode flag)
        progress_cb: Optional progress callback

    Returns:
        {
            'conversations': int,    # Conversations rendered
            'pages': int,            # Total PNG pages generated
            'elapsed': float,
        }
    """


def write_reports(
    db: sqlite3.Connection,
    project_dir: Path,
    config: Config,
    stats: dict,
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    """Write human-readable and machine-readable processing reports.

    Outputs:
    - {project_dir}/.snatched/report.txt — human-readable summary
    - {project_dir}/.snatched/report.json — machine-readable version

    report.txt sections:
    - Summary: total assets, best matches, GPS coverage, match rate
    - Match strategy breakdown (count + avg confidence per strategy)
    - GPS source breakdown (memory metadata vs location history)
    - Year distribution (memories only, grouped by YYYY)
    - Asset type breakdown
    - EXIF embedding results
    - Orphan overlays (memory_overlay with no matched memory_main)
    - True unmatched files (no match at all)
    - Warnings (date-only matches, format mismatches, fMP4 needing remux)

    Args:
        db: SQLite connection
        project_dir: Project directory
        config: Configuration
        stats: Combined stats dict from Phases 1–4
        progress_cb: Optional progress callback

    Returns:
        {
            'report_txt': Path,     # Path to written .txt report
            'report_json': Path,    # Path to written .json report
            'elapsed': float,
        }
    """


def phase4_export(
    db: sqlite3.Connection,
    project_dir: Path,
    config: Config,
    lanes: list[str] | None = None,
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    """Phase 4 orchestrator: Export all enriched files.

    Sequentially calls (lane filtering applied where relevant):
    1. copy_files()       — copy assets to output dir
    2. burn_overlays()    — composite overlay PNGs onto main files
    3. write_exif()       — embed EXIF metadata via exiftool
    4. export_chat_text() — export conversation transcripts
    5. export_chat_png()  — render conversation PNG screenshots
    6. write_reports()    — generate audit reports

    Args:
        db: SQLite connection (Phases 1–3 must have run first)
        project_dir: Root project directory
        config: Configuration
        lanes: Optional lane filter (e.g., ['memories', 'chats']).
            None = process all lanes.
        progress_cb: Optional progress callback

    Returns:
        {
            'copied': int,
            'remuxed': int,
            'burned': int,
            'exif_written': int,
            'chat_conversations': int,
            'chat_messages': int,
            'chat_pages': int,
            'elapsed': float,
        }
    """
```

---

### `snatched/processing/xmp.py`

```python
def generate_xmp(match_row: dict, config: Config) -> str:
    """Generate a complete XMP XML document for a single match.

    Combines:
    - Date/time metadata (from matched_date)
    - GPS coordinates (from matched_lat/matched_lon)
    - Creator/contributor tags (from creator_str)
    - Conversation metadata (from conversation)
    - Custom Snatched namespace tags (strategy, confidence, source)

    Args:
        match_row: Dict with keys from the matches JOIN assets query:
            matched_date, matched_lat, matched_lon, gps_source,
            display_name, creator_str, conversation, direction,
            strategy, confidence
        config: Config object (for version string, software tags)

    Returns:
        Complete XMP XML string.
    """


def build_xmp_xml(tags: dict, snatched_meta: dict) -> str:
    """Render XMP XML from a tag dictionary.

    Generates valid XMP 1.0 document with proper namespace declarations.

    Namespaces included:
    - dc: (Dublin Core — Creator, Subject, Description)
    - exif: (EXIF — DateTimeOriginal, GPSLatitude, GPSLongitude)
    - xmpMM: (XMP Media Management — DocumentID, DerivedFrom)

    Args:
        tags: Dict of {tag_name: value, ...}
        snatched_meta: Dict with:
            - version: str — e.g., '3.0'
            - strategy: str — match strategy used
            - confidence: float — match confidence 0.0–1.0
            - source_type: str — e.g., 'snapchat'
            - file_id: str — asset identifier (optional)

    Returns:
        Properly formatted XMP XML string.
        All values are XML-escaped via xml.sax.saxutils.escape().
    """


def write_xmp_sidecars(
    db: sqlite3.Connection,
    project_dir: Path,
    config: Config,
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    """Write XMP sidecar files for all exported assets.

    Sidecar naming: same path as output file + '.xmp' suffix.
    Example: output/memories/2025/01/Snap_Memory_2025-01-15_143022.jpg.xmp

    Skips assets with no output_path (not yet copied).

    Args:
        db: SQLite connection
        project_dir: Root project directory
        config: Configuration
        progress_cb: Optional progress callback

    Returns:
        {
            'written': int,    # Sidecar files created
            'skipped': int,    # Assets with no output_path
            'errors': int,     # Write failures
            'elapsed': float,
        }
    """
```

---

## Database Schema

All tables are created by `snatched/processing/schema.sql` (full DDL in Spec 01 and Spec 02). Key columns written by Phase 3/4:

```sql
-- Phase 3 enrichment writes to matches:
CREATE TABLE IF NOT EXISTS matches (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id        INTEGER NOT NULL REFERENCES assets(id),
    strategy        TEXT NOT NULL,
    confidence      REAL NOT NULL DEFAULT 0.0,
    is_best         BOOLEAN NOT NULL DEFAULT 0,
    -- GPS enrichment (set by enrich_gps):
    matched_lat     REAL,
    matched_lon     REAL,
    gps_source      TEXT,  -- 'metadata' | 'location_history' | NULL
    -- Display name enrichment (set by enrich_display_names):
    display_name    TEXT,
    creator_str     TEXT,
    direction       TEXT,  -- 'sent' | 'received' | NULL
    conversation    TEXT,
    -- Output path enrichment (set by enrich_output_paths):
    output_subdir   TEXT,
    output_filename TEXT,
    -- EXIF tags (set by enrich_exif_tags):
    exif_tags_json  TEXT,  -- JSON dict of {tag_name: value}
    lane            TEXT DEFAULT 'memories',
    -- ... other columns ...
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Phase 4 export writes to assets:
CREATE TABLE IF NOT EXISTS assets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    -- ... Phase 1 columns ...
    -- Phase 4 output:
    output_path   TEXT,        -- Absolute path of copied file
    output_sha256 TEXT,        -- SHA-256 of copied file
    exif_written  BOOLEAN DEFAULT 0,   -- 1 if EXIF embedded successfully
    exif_error    TEXT,                -- exiftool error message if failed
    xmp_written   BOOLEAN DEFAULT 0,   -- 1 if XMP sidecar written
    xmp_path      TEXT                 -- Path to .xmp sidecar file
);
```

---

## Key SQL Queries

### Load Best Matches for Export (Phase 4)

```sql
SELECT
    a.id as asset_id, a.path, a.ext, a.real_ext, a.is_video, a.is_fmp4,
    a.asset_type, a.memory_uuid, a.file_id, a.is_fmp4,
    m.id as match_id, m.matched_date, m.matched_lat, m.matched_lon, m.gps_source,
    m.display_name, m.creator_str, m.direction, m.conversation,
    m.output_subdir, m.output_filename, m.exif_tags_json, m.lane
FROM matches m
JOIN assets a ON m.asset_id = a.id
WHERE m.is_best = 1
ORDER BY a.asset_type, a.filename;
```

### Find Chat Messages for Text Export

```sql
SELECT
    conversation_id,
    conversation_title,
    COUNT(*) as msg_count,
    MIN(created) as first_date,
    MAX(created) as last_date
FROM chat_messages
GROUP BY conversation_id
ORDER BY conversation_id;
```

### Get Messages for a Conversation (ordered)

```sql
SELECT
    created_dt, from_user, media_type, content, is_sender
FROM chat_messages
WHERE conversation_id = ?
ORDER BY created_ms, created_dt;
```

### Pair Overlay with Main for Burning

```sql
SELECT
    main_a.id as main_id,
    main_a.output_path as main_output,
    main_a.is_video,
    ov_a.path as overlay_src,
    main_m.exif_tags_json
FROM assets main_a
JOIN matches main_m ON main_a.id = main_m.asset_id AND main_m.is_best = 1
JOIN assets ov_a ON main_a.memory_uuid = ov_a.memory_uuid
WHERE main_a.asset_type = 'memory_main'
  AND ov_a.asset_type = 'memory_overlay'
  AND main_a.output_path IS NOT NULL;
```

### GPS Enrichment — Find Matches Needing Location History GPS

```sql
SELECT
    m.id, m.matched_date, a.id as asset_id
FROM matches m
JOIN assets a ON m.asset_id = a.id
WHERE m.is_best = 1
  AND m.matched_lat IS NULL
  AND m.matched_date IS NOT NULL
ORDER BY m.matched_date;
```

### Update GPS from Location History

```sql
UPDATE matches
SET matched_lat = ?, matched_lon = ?, gps_source = 'location_history'
WHERE id = ?;
```

---

## Multi-User Adaptation

### Key Differences from v2

In v2, all output goes to hardcoded `/mnt/nas-pool/snapchat-output/`. In v3:

**v2:**
```python
OUTPUT_BASE = Path("/mnt/nas-pool/snapchat-output")
output_dir = OUTPUT_BASE / person_name
```

**v3:**
```python
# project_dir is always passed from the caller (jobs.py)
# project_dir = /data/{username}/processing/{job_id}/
output_dir = project_dir / "output"

# Enrich functions receive project_dir + config
def enrich_output_paths(db, config, progress_cb=None):
    # Reads config for output path patterns
    # All paths constructed relative to project_dir

def phase4_export(db, project_dir, config, ...):
    # All output goes under project_dir/output/
```

**Path isolation guaranteed:** `project_dir` is always under `/data/{username}/`, validated upstream by `safe_user_path()` before the pipeline runs.

---

## Code Examples

### Binary Search GPS Implementation

```python
from bisect import bisect_left

def find_nearest_location(target_unix, timestamps, lats, lons, gps_window=300):
    """Binary search for nearest GPS within time window."""
    if not timestamps:
        return None

    idx = bisect_left(timestamps, target_unix)
    best_dist = gps_window + 1
    best_idx = None

    for i in (idx - 1, idx):
        if 0 <= i < len(timestamps):
            dist = abs(timestamps[i] - target_unix)
            if dist < best_dist:
                best_dist = dist
                best_idx = i

    if best_idx is not None and best_dist <= gps_window:
        return lats[best_idx], lons[best_idx]
    return None
```

### Exiftool Stay-Open Batch Mode

```python
import subprocess
import threading

def _run_exiftool_batch(files_and_tags: list[tuple]):
    """Run exiftool in stay_open mode for efficient batch EXIF embedding."""
    proc = subprocess.Popen(
        ['exiftool', '-stay_open', 'True', '-@', '-'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    def drain(pipe, dest):
        for line in pipe:
            dest.append(line)
        pipe.close()

    stdout_buf, stderr_buf = [], []
    t_out = threading.Thread(target=drain, args=(proc.stdout, stdout_buf), daemon=True)
    t_err = threading.Thread(target=drain, args=(proc.stderr, stderr_buf), daemon=True)
    t_out.start()
    t_err.start()

    for tags, output_path, is_vid in files_and_tags:
        lines = ['-overwrite_original', '-ignoreMinorErrors']
        if is_vid:
            lines.extend(['-api', 'QuickTimeUTC'])
        for k, v in tags.items():
            lines.append(f'-{k}={v}')
        lines.append(str(output_path))
        lines.append('-execute')
        proc.stdin.write(('\n'.join(lines) + '\n').encode())

    proc.stdin.write(b'-stay_open\nFalse\n')
    proc.stdin.flush()
    proc.stdin.close()
    t_out.join(timeout=60)
    t_err.join(timeout=60)
    proc.wait(timeout=60)

    return stdout_buf, stderr_buf
```

### Chat Folder Map (simplified)

```python
def build_chat_folder_map(db):
    friends = {row[0]: row[1] for row in
               db.execute("SELECT username, display_name FROM friends")}

    folder_map = {}
    used_names = set()

    for conv_id, conv_title in db.execute(
        "SELECT DISTINCT conversation_id, conversation_title FROM chat_messages"
    ):
        safe_name = resolve_conversation_name(conv_title, conv_id, friends)

        # Deduplicate
        base = safe_name
        n = 2
        while safe_name in used_names:
            safe_name = f"{base}_{n}"
            n += 1

        used_names.add(safe_name)
        folder_map[conv_id] = safe_name

    return folder_map
```

### XMP Sidecar Template

```python
from xml.sax.saxutils import escape

def build_xmp_xml(tags: dict, snatched_meta: dict) -> str:
    tags_xml = '\n'.join(
        f'      <{k}>{escape(str(v))}</{k}>'
        for k, v in tags.items()
    )
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="Snatched v{snatched_meta["version"]}">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:Description rdf:about=""
        xmlns:dc="http://purl.org/dc/elements/1.1/"
        xmlns:exif="http://ns.adobe.com/exif/1.0/"
        xmlns:xmpMM="http://ns.adobe.com/xap/1.0/mm/">
{tags_xml}
      <xmpMM:DocumentID>snatched://{escape(snatched_meta.get("file_id", "unknown"))}</xmpMM:DocumentID>
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>'''
```

### Running Phase 3 + Phase 4

```python
from pathlib import Path
from snatched.config import load_config
from snatched.processing.sqlite import open_database
from snatched.processing.enrich import phase3_enrich
from snatched.processing.export import phase4_export

config = load_config(Path("/app/snatched.toml"))
db = open_database(Path("/data/dave/proc.db"))
project_dir = Path("/data/dave/processing/job-42")

def on_progress(msg: str):
    print(f"[Pipeline] {msg}")

# Phase 3
enrich_stats = phase3_enrich(db, project_dir, config, progress_cb=on_progress)
print(f"GPS enriched: {enrich_stats['gps_metadata'] + enrich_stats['gps_location_history']}")
print(f"Output paths computed: {enrich_stats['paths_computed']}")

# Phase 4
export_stats = phase4_export(db, project_dir, config,
                              lanes=['memories', 'chats', 'stories'],
                              progress_cb=on_progress)
print(f"Files copied: {export_stats['copied']}")
print(f"EXIF embedded: {export_stats['exif_written']}")
print(f"Chat conversations: {export_stats['chat_conversations']}")
```

---

## Acceptance Criteria

### Phase 3: Enrich (`enrich.py`)

- [ ] `load_location_timeline()` returns 3 parallel sorted lists (timestamps, lats, lons)
- [ ] `load_location_timeline()` returns empty lists if no location data
- [ ] `find_nearest_location()` uses bisect_left for O(log n) search
- [ ] `find_nearest_location()` returns None when no location is within gps_window
- [ ] `find_nearest_location()` checks both idx-1 and idx neighbors
- [ ] `enrich_gps()` correctly counts pre-existing metadata GPS vs newly added location history GPS
- [ ] `resolve_conversation_name()` follows the 6-step fallback chain
- [ ] `resolve_conversation_name()` returns filesystem-safe string
- [ ] `build_chat_folder_map()` returns same names used in output paths
- [ ] `build_chat_folder_map()` deduplicates colliding names with _2, _3 suffixes
- [ ] `enrich_display_names()` updates all chat/snap match rows with display_name, direction
- [ ] `enrich_output_paths()` computes correct paths for each asset_type
- [ ] `enrich_output_paths()` handles filename collisions with numeric suffix
- [ ] `enrich_output_paths()` uses real_ext instead of ext when format was misidentified
- [ ] `enrich_exif_tags()` stores JSON dict in matches.exif_tags_json
- [ ] `phase3_enrich()` returns dict with all required keys
- [ ] All enrich functions use parameterized SQL (no string interpolation)
- [ ] All enrich functions call progress_cb at reasonable intervals

### Phase 4: Export (`export.py`)

- [ ] `copy_files()` creates output directory tree before copying
- [ ] `copy_files()` remuxes fMP4 files with ffmpeg if available
- [ ] `copy_files()` verifies SHA-256 for non-remuxed copies
- [ ] `copy_files()` updates assets.output_path and assets.output_sha256
- [ ] `write_exif()` uses exiftool stay_open batch mode (not per-file subprocess)
- [ ] `write_exif()` adds QuickTimeUTC flag for video files
- [ ] `write_exif()` records success/failure per file in assets.exif_written + assets.exif_error
- [ ] `write_exif()` skips gracefully if exiftool binary not found
- [ ] `burn_overlays()` pairs memory_main + memory_overlay by memory_uuid
- [ ] `burn_overlays()` uses ImageMagick for images, ffmpeg for videos
- [ ] `burn_overlays()` skips gracefully if ImageMagick/ffmpeg not found
- [ ] `export_chat_text()` creates one .txt file per conversation
- [ ] `export_chat_text()` uses the same folder names as enrich_output_paths()
- [ ] `export_chat_png()` uses ChatRenderer for PNG generation
- [ ] `export_chat_png()` skips gracefully if Pillow not available
- [ ] `write_reports()` writes both report.txt and report.json
- [ ] `phase4_export()` calls all 6 sub-functions in order
- [ ] All single-file errors are logged + counted — they do NOT abort the phase

### XMP (`xmp.py`)

- [ ] `generate_xmp()` produces valid XMP XML (parseable by standard XML parser)
- [ ] `build_xmp_xml()` XML-escapes all values (no injection via special characters)
- [ ] `write_xmp_sidecars()` uses {output_path}.xmp naming convention
- [ ] `write_xmp_sidecars()` skips assets without output_path
- [ ] XMP files reference correct namespace declarations

---

## Implementation Notes

### Batch Operations

Both enrich and export use batch SQLite updates (`BATCH_SIZE = 500` rows per commit) to balance memory pressure and I/O. Do not change batch size without profiling.

### Chat Folder Map

The chat folder map is computed fresh on each Phase 3 run. It is NOT persisted to the database. This allows folder naming logic to evolve without requiring data migrations.

### External Tool Availability

All Phase 4 functions check for external binary availability before use and degrade gracefully:
```python
import shutil

exiftool_available = shutil.which("exiftool") is not None
ffmpeg_available   = shutil.which("ffmpeg") is not None
magick_available   = shutil.which("magick") is not None or shutil.which("composite") is not None
```

If unavailable: log a warning, increment skipped counter, continue.

### Error Handling Per File

No single-file error should abort the entire phase. Pattern:
```python
errors = 0
for row in rows:
    try:
        process(row)
    except Exception:
        logger.exception("Failed to process %s", row['path'])
        errors += 1

logger.info("Completed: %d errors out of %d files", errors, len(rows))
```
