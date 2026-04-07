# SnapFix v2.0 Specification

**Status**: DRAFT
**Date**: 2026-02-21
**Location**: `~/tools/snapfix/snapfix.py` (replaces v1 in-place)
**v1 Reference**: 1,871 lines, single-file Python, sequential phase architecture

---

## Overview

SnapFix v2 processes Snapchat data exports: it matches every media file to maximum available metadata, embeds EXIF tags, and produces a queryable SQLite database of all assets and messages.

**Purpose**: Take a raw Snapchat data export (stripped of all EXIF by Snapchat) and reconstruct the richest possible metadata for every file -- dates, GPS, sender/receiver, conversation context, match confidence -- then write that metadata back into the files as EXIF tags.

**Input**: Snapchat data export directory (already extracted) or ZIP file(s).

**Output**:
- EXIF-tagged media files organized by type and date
- SQLite database containing all parsed metadata, match results, and audit trail
- Per-conversation text export of chat messages (Content field)
- Machine-readable audit report with match confidence scores

**Key change from v1**: Instead of parsing JSON incrementally and matching on-the-fly during copy, v2 ingests ALL data sources into SQLite first, then runs matching as SQL joins. This makes the matching logic auditable, replayable, and extensible.

---

## Architecture: Unified Table Approach

v1 processes data in a sequential pipeline: parse JSON into Python dicts, match files to dicts during copy, embed EXIF, report. Each phase reads from the previous phase's in-memory structures. Matching logic is scattered across `phase2()` with three separate passes for chat media.

v2 replaces this with four clean phases that separate concerns:

```
  Export ZIP/Dir
       |
  [1. INGEST] -- Parse ALL data sources into SQLite tables
       |
  [2. MATCH]  -- Link assets to metadata via priority cascade (SQL)
       |
  [3. ENRICH] -- Add GPS, display names, context to every asset row
       |
  [4. EXPORT] -- Write EXIF tags, copy files, generate reports
```

### Phase 1: Ingest

Parse every data source into its own SQLite table. No matching logic here -- just faithful ingestion of raw data.

**Responsibilities**:
- Extract ZIPs if needed (reuse v1 logic with path-traversal protection)
- Discover export structure: primary (has `json/`), secondaries (memories-only), overlays dir
- Scan all media files on disk and register them in `assets` table
- Parse all JSON files into their respective tables
- Parse `friends.json` into `friends` table (all categories, deduplicated)
- Detect file format mismatches (WebP disguised as .png, etc.) and record in `assets.real_ext`
- Detect fragmented MP4s and record in `assets.is_fmp4`
- Compute SHA-256 of every source file and store in `assets.sha256`

**Data sources to parse**:

| File | Table | Key fields |
|------|-------|------------|
| `memories_history.json` | `memories` | mid (from Download Link URL), date, location, media_type |
| `chat_history.json` | `chat_messages` | media_ids, created, created_us, from_user, is_sender, conversation_title, media_type, content |
| `snap_history.json` | `snap_messages` | created, created_us, from_user, is_sender, conversation_title, media_type |
| `shared_story.json` | `stories` | story_id, created, content_type |
| `friends.json` | `friends` | username, display_name, category |
| `location_history.json` | `locations` | timestamp, lat, lon |
| `snap_map_places.json` | `places` | name, lat, lon, address, visits |
| `snap_pro.json` (if present) | `snap_pro` | saved story URLs |
| Filesystem scan | `assets` | path, filename, date_str, file_id, ext, real_ext, asset_type, sha256 |

**Critical v1 bug fix**: v1 filters `chat_history.json` to only `Media Type == 'MEDIA'` messages. This drops STICKER type messages that have valid Media IDs, losing approximately 18 potential matches. v2 ingests ALL message types into `chat_messages` and lets the match phase decide relevance.

**Critical v1 bug fix**: v1 never searches `overlay~zip` and `media~zip` style UUIDs against any JSON source. v2 records the full parsed filename components (including the `b~` prefix pattern used for Media IDs) so the match phase can use them.

**Critical v1 bug fix**: v1 does not parse `snap_pro.json` which contains saved story URLs (2 known entries). v2 ingests this if present.

### Phase 2: Match

Run the match cascade as SQL queries against the ingested tables. Each match strategy is a separate query that writes to the `matches` join table. Strategies run in priority order; later strategies skip assets already matched by earlier ones.

**Responsibilities**:
- Execute match cascade (see Match Cascade section below)
- Record every match attempt in `matches` table with strategy name and confidence score
- Allow multiple matches per asset (best match wins, others kept for audit)
- Flag conflicts (asset matched by multiple strategies with different metadata)

### Phase 3: Enrich

Walk every asset and add derived metadata from the best match and supplementary sources.

**Responsibilities**:
- Look up GPS coordinates: first from matched metadata (memories have embedded GPS), then from `locations` table via nearest-timestamp binary search (reuse v1's +/-5min window)
- Resolve display names from `friends` table for all username references
- Build conversation context string (who sent it, which conversation, sent/received)
- Compute output path (directory structure, descriptive filename, collision handling)
- Build the complete EXIF tag dict for each asset
- Set match confidence score (0.0-1.0) based on strategy and data completeness

### Phase 4: Export

Write files and generate reports. This is the only phase that modifies the filesystem (besides the initial ZIP extraction).

**Responsibilities**:
- Copy files to output directory with SHA-256 verification
- Fix format mismatches (rename .png to .webp where detected)
- Remux fragmented MP4s via ffmpeg (reuse v1 logic)
- Embed EXIF via exiftool `-stay_open` batch mode (reuse v1 logic)
- Burn overlays if requested (reuse v1 ImageMagick/ffmpeg logic)
- Generate text export of chat conversations
- Write audit report
- Preserve the SQLite database as a deliverable

---

## SQLite Schema

Database file: `{project_dir}/.snapfix/snapfix.db`

```sql
-- Pragmas for performance
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

-- ═══════════════════════════════════════════════════════════════
-- ASSETS: Every media file discovered on disk
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE assets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    -- Source file info
    path            TEXT NOT NULL UNIQUE,        -- absolute path to source file
    filename        TEXT NOT NULL,               -- just the filename
    -- Parsed filename components
    date_str        TEXT,                        -- YYYY-MM-DD from filename (NULL if unparseable)
    file_id         TEXT,                        -- the ID portion after date (UUID, b~base64, etc.)
    ext             TEXT NOT NULL,               -- file extension as-is (.jpg, .mp4, etc.)
    real_ext        TEXT,                        -- corrected extension if format mismatch detected
    -- Classification
    asset_type      TEXT NOT NULL                -- 'memory_main', 'memory_overlay', 'chat', 'story'
                    CHECK(asset_type IN ('memory_main', 'memory_overlay', 'chat', 'story')),
    is_video        BOOLEAN NOT NULL DEFAULT 0,
    is_fmp4         BOOLEAN NOT NULL DEFAULT 0, -- fragmented MP4 needing remux
    -- Parsed UUID for memories (extracted from filename pattern YYYY-MM-DD_UUID-main.ext)
    memory_uuid     TEXT,                        -- UUID portion for memory files
    -- Integrity
    file_size       INTEGER,                    -- bytes
    sha256          TEXT,                        -- hex digest of source file
    -- Export state (populated in Phase 4)
    output_path     TEXT,                        -- destination path after copy
    output_sha256   TEXT,                        -- hex digest after copy (should match sha256)
    exif_written    BOOLEAN DEFAULT 0,
    exif_error      TEXT,                        -- error message if EXIF write failed
    -- Timestamps
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_assets_file_id ON assets(file_id);
CREATE INDEX idx_assets_memory_uuid ON assets(memory_uuid);
CREATE INDEX idx_assets_date_str ON assets(date_str);
CREATE INDEX idx_assets_asset_type ON assets(asset_type);

-- ═══════════════════════════════════════════════════════════════
-- CHAT_MESSAGES: Every message from chat_history.json
-- ALL types, not just MEDIA (v1 bug fix)
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE chat_messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,               -- the top-level key in chat_history.json
    -- Message fields
    from_user       TEXT,
    media_type      TEXT,                        -- 'MEDIA', 'STICKER', 'NOTE', 'SHARE', etc.
    media_ids       TEXT,                        -- pipe-separated media IDs (e.g. "b~abc|b~def")
    content         TEXT,                        -- the text content of the message
    created         TEXT,                        -- ISO timestamp string from JSON
    created_us      INTEGER,                     -- Created(microseconds) from JSON
    is_sender       BOOLEAN DEFAULT 0,
    conversation_title TEXT,
    -- Parsed fields
    created_dt      TEXT,                        -- parsed to ISO 8601
    created_date    TEXT                         -- YYYY-MM-DD only (for date matching)
);

CREATE INDEX idx_chat_media_ids ON chat_messages(media_ids);
CREATE INDEX idx_chat_created_date ON chat_messages(created_date);
CREATE INDEX idx_chat_conversation ON chat_messages(conversation_id);
CREATE INDEX idx_chat_media_type ON chat_messages(media_type);

-- Exploded media IDs for efficient joining (one row per media ID)
CREATE TABLE chat_media_ids (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_message_id INTEGER NOT NULL REFERENCES chat_messages(id),
    media_id        TEXT NOT NULL                -- single media ID (e.g. "b~abc123...")
);

CREATE INDEX idx_chat_mid ON chat_media_ids(media_id);

-- ═══════════════════════════════════════════════════════════════
-- SNAP_MESSAGES: Every entry from snap_history.json (276 entries)
-- These are snap sends/receives with microsecond timestamps
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE snap_messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    from_user       TEXT,
    media_type      TEXT,                        -- 'IMAGE', 'VIDEO'
    created         TEXT,
    created_us      INTEGER,
    is_sender       BOOLEAN DEFAULT 0,
    conversation_title TEXT,
    -- Parsed fields
    created_dt      TEXT,
    created_date    TEXT,                        -- YYYY-MM-DD
    -- Dedup tracking (v1: 10ms bucket + from + type)
    dedup_key       TEXT UNIQUE                  -- "bucket|from|type" for dedup
);

CREATE INDEX idx_snap_created_date ON snap_messages(created_date);
CREATE INDEX idx_snap_media_type ON snap_messages(media_type);
CREATE INDEX idx_snap_date_type ON snap_messages(created_date, media_type);

-- ═══════════════════════════════════════════════════════════════
-- MEMORIES: All 2,408 entries from memories_history.json
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE memories (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    mid             TEXT UNIQUE,                 -- the ?mid= param from Download Link URL
    date            TEXT,                        -- raw date string from JSON
    date_dt         TEXT,                        -- parsed to ISO 8601
    media_type      TEXT,                        -- 'PHOTO', 'VIDEO' (from JSON Media Type)
    location_raw    TEXT,                        -- raw "Latitude, Longitude: ..." string
    lat             REAL,                        -- parsed latitude
    lon             REAL,                        -- parsed longitude
    download_link   TEXT                         -- full CDN URL (informational only)
);

CREATE INDEX idx_memories_mid ON memories(mid);
CREATE INDEX idx_memories_date ON memories(date_dt);

-- ═══════════════════════════════════════════════════════════════
-- STORIES: Entries from shared_story.json
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE stories (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id        TEXT,
    created         TEXT,
    created_dt      TEXT,
    content_type    TEXT                         -- 'IMAGE', 'VIDEO' (uppercased Content field)
);

CREATE INDEX idx_stories_id ON stories(story_id);
CREATE INDEX idx_stories_type ON stories(content_type);

-- ═══════════════════════════════════════════════════════════════
-- SNAP_PRO: Saved stories from snap_pro.json (if present)
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE snap_pro (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    url             TEXT,
    created         TEXT,
    created_dt      TEXT,
    title           TEXT
);

-- ═══════════════════════════════════════════════════════════════
-- FRIENDS: Username to display name mapping (395 entries)
-- All categories from friends.json, deduplicated
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE friends (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT NOT NULL UNIQUE,
    display_name    TEXT,
    category        TEXT                         -- 'Friends', 'Deleted Friends', etc.
);

CREATE INDEX idx_friends_username ON friends(username);

-- ═══════════════════════════════════════════════════════════════
-- LOCATIONS: GPS breadcrumbs from location_history.json (2,151 points)
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE locations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,               -- raw timestamp string
    timestamp_unix  REAL NOT NULL,               -- Unix timestamp (for binary search)
    lat             REAL NOT NULL,
    lon             REAL NOT NULL
);

CREATE INDEX idx_locations_ts ON locations(timestamp_unix);

-- ═══════════════════════════════════════════════════════════════
-- PLACES: Snap Map places from snap_map_places.json (19 records)
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE places (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT,
    lat             REAL,
    lon             REAL,
    address         TEXT,
    visit_count     INTEGER
);

-- ═══════════════════════════════════════════════════════════════
-- MATCHES: Join table linking assets to their metadata sources
-- This is the core output of Phase 2
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE matches (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id        INTEGER NOT NULL REFERENCES assets(id),
    -- What matched
    strategy        TEXT NOT NULL,               -- 'exact_media_id', 'memory_uuid', 'story_id',
                                                 -- 'timestamp_type', 'date_type_count', 'date_only'
    confidence      REAL NOT NULL DEFAULT 0.0,   -- 0.0 to 1.0
    is_best         BOOLEAN NOT NULL DEFAULT 0,  -- 1 if this is the selected match for the asset
    -- Source reference (polymorphic: exactly one of these is non-NULL)
    memory_id       INTEGER REFERENCES memories(id),
    chat_message_id INTEGER REFERENCES chat_messages(id),
    snap_message_id INTEGER REFERENCES snap_messages(id),
    story_id        INTEGER REFERENCES stories(id),
    -- Derived metadata (populated in Phase 3: Enrich)
    matched_date    TEXT,                        -- best datetime from matched source
    matched_lat     REAL,                        -- GPS from matched source or location lookup
    matched_lon     REAL,                        -- GPS from matched source or location lookup
    gps_source      TEXT,                        -- 'metadata', 'location_history', NULL
    display_name    TEXT,                        -- resolved from friends table
    creator_str     TEXT,                        -- formatted "Display Name (@username)"
    direction       TEXT,                        -- 'sent', 'received', NULL
    conversation    TEXT,                        -- conversation title or partner name
    output_subdir   TEXT,                        -- computed output subdirectory
    output_filename TEXT,                        -- computed output filename (with collision suffix)
    -- EXIF tag dict (stored as JSON for reference/replay)
    exif_tags_json  TEXT,
    -- Timestamps
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_matches_asset ON matches(asset_id);
CREATE INDEX idx_matches_best ON matches(asset_id, is_best);
CREATE INDEX idx_matches_strategy ON matches(strategy);

-- ═══════════════════════════════════════════════════════════════
-- RUN_LOG: Audit trail for each snapfix execution
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE run_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    version         TEXT NOT NULL,               -- 'v2.0'
    person          TEXT NOT NULL,
    input_path      TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    phase           TEXT,                        -- current/last phase
    status          TEXT DEFAULT 'running',      -- 'running', 'completed', 'failed'
    flags_json      TEXT,                        -- CLI flags as JSON
    -- Summary stats (populated at end)
    total_assets    INTEGER,
    total_matched   INTEGER,
    total_exif_ok   INTEGER,
    total_exif_err  INTEGER,
    total_copied    INTEGER,
    elapsed_seconds REAL,
    error_message   TEXT
);
```

---

## Match Cascade

Strategies run in strict priority order. Each strategy marks matched assets in the `matches` table. Later strategies skip assets that already have a match with `is_best = 1`.

### Strategy 1: Exact Media ID (confidence: 1.0)

For chat media files whose `file_id` starts with `b~` (base64 media reference).

```
assets.file_id = chat_media_ids.media_id
WHERE assets.asset_type = 'chat'
```

The `b~` prefix is how Snapchat encodes media IDs in filenames. The same ID appears in `chat_history.json` under the `Media IDs` field (pipe-delimited for multi-image messages).

**v1 equivalent**: Pass 1 of `phase2()` chat matching.

**v1 bug fixed**: v1 only checks messages with `Media Type == 'MEDIA'`. v2 checks all `chat_media_ids` rows regardless of parent message type, catching STICKER and other types that also carry Media IDs.

### Strategy 2: Memory UUID (confidence: 1.0)

For memory files whose filename contains a UUID matching `memories.mid`.

```
assets.memory_uuid = memories.mid
WHERE assets.asset_type = 'memory_main'
```

**v1 equivalent**: Direct dict lookup `mem_map.get(uuid)` in `phase2()`.

### Strategy 3: Story ID (confidence: 0.9)

For shared story files. Match by ordered pairing within content type groups (IMAGE, VIDEO), same as v1.

```
ORDER stories by created, match to story files sorted by filename
WHERE count(stories of type) == count(files of type)
```

**v1 equivalent**: `match_group()` in `phase2()`.

If counts don't match perfectly, confidence drops to 0.5.

### Strategy 4: Timestamp + Type (confidence: 0.8)

For unmatched chat files where the filename date + media type matches exactly one `snap_messages` entry.

```
assets.date_str = snap_messages.created_date
AND asset is_video matches snap_messages.media_type
AND exactly one snap_message exists for that (date, type) combination
```

**v1 equivalent**: Not present in v1. v1 jumps straight to count-based matching. This new strategy captures cases where there is only one snap of a given type on a given date -- a guaranteed unique match without needing count alignment.

### Strategy 5: Date + Type + Count (confidence: 0.7)

For unmatched chat files where the filename date + media type has the SAME count in both files and snap_messages.

```
COUNT(assets WHERE date_str = D AND is_video = V) == COUNT(snap_messages WHERE created_date = D AND media_type = V)
```

When counts match, pair files (sorted by filename) with snap_messages (sorted by timestamp).

**v1 equivalent**: Pass 2 of `phase2()` chat matching (the "rescue" logic using `snap_pool`).

### Strategy 6: Date-Only Fallback (confidence: 0.3)

For chat files still unmatched. Use the date from the filename, set time to 00:00:00 UTC. No JSON match -- just the date prefix.

```
assets.date_str IS NOT NULL
AND no prior match exists
```

**v1 equivalent**: Pass 3 of `phase2()` chat matching.

### Unmatched Assets (confidence: 0.0)

Files that matched no strategy. Still copied to output under `unmatched/` directory. Minimal EXIF tags (Software, ImageDescription).

### Special Cases

**`overlay~zip` and `media~zip` UUIDs**: v1 does not attempt to match files with these filename patterns against any JSON source. v2 should extract the UUID portion and attempt Memory UUID matching (Strategy 2). If the UUID portion of an `overlay~zip` or `media~zip` filename matches a `memories.mid`, link them.

**`snap_pro.json` saved stories**: v1 does not parse this file. v2 ingests it into `snap_pro` table and attempts to cross-reference story URLs with story files. Low priority (2 known entries) but prevents data loss.

---

## GPS Enrichment

After matching, every asset gets a GPS lookup pass:

1. **Memory metadata GPS**: If the asset matched a memory with non-zero lat/lon, use that. (Confidence: highest -- Snapchat's own location tag.)
2. **Location history breadcrumb**: Binary search `locations` table for the nearest timestamp within +/-5 minutes (300 seconds). If found, use it.
3. **No GPS**: If neither source has a fix, leave GPS fields NULL.

Record `gps_source` in the `matches` table so the audit report can distinguish "GPS from Snapchat metadata" vs "GPS interpolated from location breadcrumbs".

### GPS Tag Construction (unchanged from v1)

Images:
```
GPSLatitude, GPSLatitudeRef (N/S)
GPSLongitude, GPSLongitudeRef (E/W)
GPSDateStamp, GPSTimeStamp (if datetime available)
```

Videos (QuickTime/XMP):
```
Keys:GPSCoordinates = "lat lon"
XMP:GPSLatitude, XMP:GPSLongitude
```

Note: v1 correctly handles N/S for latitude and E/W for longitude (fixing the Snatch bug). v2 preserves this.

---

## EXIF Tag Specification

### All files get:
| Tag | Value |
|-----|-------|
| `Software` | `SnapFix v2.0` |
| `ImageDescription` | `Snapchat Memory`, `Snapchat Chat`, `Snapchat Shared Story`, etc. |

### Files with dates additionally get:

**Images**:
| Tag | Format |
|-----|--------|
| `DateTimeOriginal` | `YYYY:MM:DD HH:MM:SS` |
| `CreateDate` | `YYYY:MM:DD HH:MM:SS` |
| `ModifyDate` | `YYYY:MM:DD HH:MM:SS` |
| `OffsetTimeOriginal` | `+00:00` |
| `SubSecDateTimeOriginal` | `YYYY:MM:DD HH:MM:SS.mmm` (if microseconds available) |

**Videos (QuickTime/XMP)**:
| Tag | Format |
|-----|--------|
| `QuickTime:CreateDate` | `YYYY:MM:DD HH:MM:SS` |
| `QuickTime:ModifyDate` | `YYYY:MM:DD HH:MM:SS` |
| `XMP:DateTimeOriginal` | `YYYY:MM:DD HH:MM:SS+00:00` |
| `XMP:CreateDate` | `YYYY:MM:DD HH:MM:SS+00:00` |

### Chat-specific additional tags:
| Tag | Value |
|-----|-------|
| `XMP:Creator` | `Display Name (@username)` |
| `XMP:Description` | `Sent` or `Received` |
| `XMP:Subject` | Conversation title (if group chat) |
| `ImageUniqueID` | Media ID or UUID |

### Memory-specific additional tags:
| Tag | Value |
|-----|-------|
| `ImageUniqueID` | Memory UUID |
| `XMP:Software` | `SnapFix v2.0` (videos only, for broader reader compat) |

---

## Output Directory Structure

```
{project_dir}/
  .snapfix/
    snapfix.db              -- SQLite database (the v2 deliverable)
    report.txt              -- human-readable audit report
    report.json             -- machine-readable audit report
  output/
    memories/
      {YYYY}/
        {MM}/
          Snap_Memory_YYYY-MM-DD_HHMMSS.{ext}
          Snap_Memory_YYYY-MM-DD_HHMMSS_2.{ext}  -- collision suffix
    chat/
      {ConversationName}/
        Snap_Chat_YYYY-MM-DD_HHMMSS.{ext}
      Unmatched/
        Snap_Chat_YYYY-MM-DD_000000.{ext}
    stories/
      Snap_Story_YYYY-MM-DD_HHMMSS.{ext}
    unmatched/
      Snap_Memory_{original_stem}.{ext}
      Snap_Chat_{original_stem}.{ext}
  text_export/
    {ConversationName}.txt  -- full chat text per conversation
```

### Conversation folder naming (unchanged from v1):

1. If `conversation_title` is set (group chats): sanitize and use as folder name.
2. If `conversation_id` is a username (not a UUID): look up display name from `friends` table, use `DisplayName` or `username`.
3. Fallback: `Unknown`.

### Collision handling (unchanged from v1):

If `Snap_Memory_2024-07-15_143022.jpg` already exists, append `_2`, `_3`, etc.

---

## Chat Text Export

New in v2. For every conversation in `chat_messages`, produce a plain-text transcript.

**Format**:
```
=== Conversation: {title or partner display name} ===
Partner: @{username} ({display_name})
Messages: {count}
Date range: {first} to {last}
================================================================

[2026-01-15 08:23:41] Dave: Hey what's up
[2026-01-15 08:24:02] @frienduser: Not much
[2026-01-15 08:24:15] Dave: [MEDIA: image]
[2026-01-15 08:25:01] @frienduser: [STICKER]
[2026-01-15 08:30:00] Dave: Cool talk later
```

**Rules**:
- Include ALL message types (MEDIA, STICKER, NOTE, SHARE, etc.)
- For MEDIA messages, show `[MEDIA: {type}]` placeholder
- For messages with Content text, show the text
- Use display names where available, fall back to @username
- Sort messages by `created_us` (microsecond precision) within each conversation
- One `.txt` file per conversation in `text_export/` directory

---

## Audit Report

### Human-readable report (`report.txt`)

Similar to v1 but enhanced with:
- Match strategy breakdown (how many matched by each strategy)
- Confidence score distribution
- GPS source breakdown (metadata vs location_history vs none)
- Per-conversation file counts
- Year breakdown
- File type breakdown
- Collision report
- Unmatched file listing with diagnostic info (why no match)
- Warnings section

### Machine-readable report (`report.json`)

```json
{
  "version": "2.0",
  "person": "dave",
  "timestamp": "2026-02-21T14:30:00Z",
  "elapsed_seconds": 127.4,
  "input": "/mnt/nas-pool/media/photos/snapchat-import/",
  "output": "/mnt/nas-pool/snapchat-processing/dave/output/",
  "database": "/mnt/nas-pool/snapchat-processing/dave/.snapfix/snapfix.db",
  "flags": {"no_overlays": false, "dry_run": false, "export_text": true},
  "counts": {
    "total_assets": 3175,
    "memories": {"total": 2408, "matched": 2408, "gps": 2367, "overlays": 638},
    "chat": {"total": 759, "exact_media_id": 487, "timestamp_type": 23, "date_type_count": 134, "date_only": 97, "unmatched": 18},
    "stories": {"total": 8, "matched": 7},
    "text_conversations": 45
  },
  "match_strategies": {
    "exact_media_id": {"count": 487, "avg_confidence": 1.0},
    "memory_uuid": {"count": 2408, "avg_confidence": 1.0},
    "story_id": {"count": 7, "avg_confidence": 0.9},
    "timestamp_type": {"count": 23, "avg_confidence": 0.8},
    "date_type_count": {"count": 134, "avg_confidence": 0.7},
    "date_only": {"count": 97, "avg_confidence": 0.3},
    "unmatched": {"count": 19, "avg_confidence": 0.0}
  },
  "gps_sources": {
    "metadata": 2367,
    "location_history": 412,
    "none": 396
  },
  "year_breakdown": {"2016": 45, "2017": 230, "...": "..."},
  "exif": {"written": 3156, "errors": 0, "skipped": 19},
  "warnings": []
}
```

---

## CLI Interface

### Basic usage (unchanged from v1):
```bash
snapfix /path/to/export --for dave
snapfix export.zip --for jake
snapfix --guided
```

### New flags:
```
--export-db         Write SQLite database to output (default: ON)
--export-text       Write per-conversation text exports (default: ON)
--no-exif           Skip EXIF embedding (just copy + database)
--no-copy           Skip file copy (just build database, no output files)
--match-only        Run Phases 1-2 only (ingest + match), print match report, exit
--resume            Resume from existing .snapfix/snapfix.db (skip re-ingest)
--json-report       Write report.json (default: ON)
```

### Preserved flags from v1:
```
--for PERSON        Person name (output folder name) [required]
--no-overlays       Skip burning overlay PNGs
--dry-run           Show plan without processing
--test N            Process first N items of each asset type
--test-video N      Process first N video files only
--source IDS        Comma-separated export IDs to process
--guided            Interactive step-by-step setup wizard
```

### New subcommands (optional, can be deferred):
```
snapfix query DB_PATH "SELECT ..."     # Run a query against an existing snapfix.db
snapfix stats DB_PATH                  # Print summary stats from existing DB
```

---

## Dependencies

| Dependency | Purpose | Required | Install |
|-----------|---------|----------|---------|
| Python 3.8+ | Runtime | Yes | System |
| sqlite3 | Database (stdlib) | Yes | Included in Python |
| exiftool | EXIF tag embedding | Yes (for EXIF mode) | `sudo apt install libimage-exiftool-perl` |
| ffmpeg | fMP4 remux + video overlay burn | Optional | `sudo apt install ffmpeg` |
| ImageMagick | Image overlay burn | Optional | `sudo apt install imagemagick` |

No pip dependencies. v2 remains a single-file tool using only stdlib modules (same as v1).

---

## Migration from v1

v2 replaces v1 in-place at `~/tools/snapfix/snapfix.py`. The CLI interface is backward-compatible: all v1 flags and arguments work identically. New features are additive.

**Breaking changes**: None. v2 produces the same output directory structure and EXIF tags as v1. The only additions are the `.snapfix/` directory (database + reports) and the `text_export/` directory.

**Guided mode**: Preserved in full, same interactive wizard with the same personality. Updated version string and added prompts for new export modes.

---

## Implementation Notes

### Single-file constraint

v2 must remain a single Python file. No package structure, no external dependencies beyond stdlib. This is a portable tool that gets handed to friends alongside their Snapchat export.

### Performance targets

- Ingest phase: < 5 seconds for a full export (2,408 memories + 1,720 chat messages + 276 snaps)
- Match phase: < 1 second (SQL queries on indexed tables)
- Copy + EXIF: dominated by I/O and exiftool, same as v1 (~2-3 minutes for full export)

### Error handling

- If SQLite fails: fall back to in-memory database and warn (never block processing)
- If exiftool is missing: skip EXIF but still copy files and build database
- Each phase should be independently restartable via `--resume`

### Testing

- v2 should produce identical EXIF output to v1 for the same input (regression test)
- Match counts should be >= v1 counts (v2 fixes bugs that lost matches)
- Expected improvement: ~18 additional chat matches from STICKER type fix
- Database should be queryable after run: `sqlite3 .snapfix/snapfix.db "SELECT count(*) FROM matches WHERE is_best = 1"`

---

## Known Data Volumes (Dave's export, 2026-02-20)

These numbers anchor the schema and match logic:

| Source | Count | Notes |
|--------|-------|-------|
| Memory files (main) | 2,408 | 1,439 images + 969 videos |
| Memory overlays | 638 | PNG overlay files |
| Chat media files | 759 | 607 images, 134 videos, 18 overlays |
| Shared story files | 8 | 7 JSON entries |
| `memories_history.json` entries | 2,408 | 100% have GPS (41 at 0,0) |
| `chat_history.json` messages | ~1,720 | ALL types, not just MEDIA |
| `snap_history.json` entries | 276 | Deduplicated |
| `location_history.json` breadcrumbs | 2,151 | Jan 5 - Feb 19, 2026 only |
| `friends.json` entries | 395 | Current + deleted friends |
| `snap_map_places.json` entries | 19 | Named places |

---

## Open Questions

1. **Should `--resume` re-run matching on existing ingested data, or skip straight to export?** Proposed: re-run match + enrich + export, skip ingest. This lets you tweak match parameters without re-scanning files.

2. **Should the text export include messages from conversations with zero media files?** Proposed: yes, export ALL conversations. The text export is a complete backup of chat history, independent of media.

3. **Should overlay files get their own entries in the `assets` table?** Proposed: yes, as `asset_type = 'memory_overlay'`, linked to their parent memory via `memory_uuid`. This makes the overlay inventory queryable.

4. **Maximum database size concern?** For Dave's export: ~6,000 rows across all tables, estimated < 5MB. Not a concern even for much larger exports.
