# Spec 04 — Match (Phase 2)

## Module Overview

Phase 2 links media assets to their metadata sources via a **6-strategy priority cascade** plus a bonus overlay/ZIP strategy. Each strategy assigns a confidence score, and the highest-confidence match per asset is marked `is_best = 1`.

This is the **heart of Snatched** — matching quality defines output data quality. All strategy SQL is a **direct port from v2** with no algorithmic changes.

The cascade ensures:
1. High-confidence matches (exact IDs, UUIDs) are tried first
2. Date-based fallbacks catch orphaned files
3. Every asset with a known date gets at least a date-only match (confidence 0.3)

**6-strategy confidence scores (authoritative):**

| # | Strategy | Confidence | Description |
|---|----------|-----------|-------------|
| 1 | `exact_media_id` | 1.0 | Chat file_id = message Media ID |
| 2 | `memory_uuid` | 1.0 | Memory filename UUID = memories.mid |
| 3 | `story_id` | 0.9 / 0.5 | Ordered pairing by type (0.9 if counts match, else 0.5) |
| 4 | `timestamp_type` | 0.8 | Unique date + media type on both sides |
| 5 | `date_type_count` | 0.7 | Count-aligned ordered pairing by date + type |
| 6 | `date_only` | 0.3 | Any asset with a date_str (fallback) |
| B | `memory_uuid_zip` | 0.9 | UUID extracted from overlay~zip filename |

---

## Files to Create

```
snatched/
└── processing/
    └── match.py                   # ~400 lines: 9 strategy functions + orchestrator
```

---

## Dependencies

**Build order:** Spec 01 (Foundation), Spec 02 (Database Layer), Spec 03 (Ingest) must exist first. Phase 2 requires the SQLite database to be fully populated by Phase 1.

**Python imports:**
```python
import sqlite3
import logging
import time
from typing import Callable, Any

logger = logging.getLogger(__name__)
```

**No external package dependencies** — all logic is pure SQLite.

---

## V2 Source Reference

All functions ported from `/home/dave/tools/snapfix/snatched.py`:

| Function | V2 Lines | Notes |
|----------|----------|-------|
| `_matched_asset_ids()` | 1251–1254 | Helper: set of already-matched asset IDs |
| `_strategy1_exact_media_id()` | 1257–1274 | Confidence 1.0 |
| `_strategy2_memory_uuid()` | 1277–1296 | Confidence 1.0 |
| `_strategy3_story_id()` | 1299–1350 | Confidence 0.9 or 0.5 |
| `_strategy4_timestamp_type()` | 1353–1388 | Confidence 0.8 |
| `_strategy5_date_type_count()` | 1391–1440 | Confidence 0.7 |
| `_strategy6_date_only()` | 1443–1459 | Confidence 0.3 |
| `_match_overlay_and_media_zips()` | 1462–1514 | Confidence 0.9 (bonus) |
| `_set_best_matches()` | 1517–1555 | Select is_best=1 per asset |
| `phase2_match()` | 1558–1647 | Orchestrator |

All function logic is a **direct SQL port** with no algorithmic changes.

---

## Function Signatures & SQL Queries

### Helper

```python
def _matched_asset_ids(db: sqlite3.Connection) -> set[int]:
    """Return set of all asset IDs that already have at least one match row.

    Used to skip already-matched assets in subsequent strategies.

    Returns:
        set[int]: Set of asset_id values present in matches table.
    """
```

**SQL (v2 line 1253):**
```sql
SELECT DISTINCT asset_id FROM matches
```

---

### Strategy 1: Exact Media ID (Confidence 1.0)

```python
def _strategy1_exact_media_id(db: sqlite3.Connection) -> int:
    """Strategy 1: Exact Media ID match (confidence 1.0).

    For chat assets, match assets.file_id against chat_media_ids.media_id.
    If a chat message's Media ID equals the asset's file_id, link them.

    This is the most accurate match — zero false positives.
    chat_media_ids was populated by ingest_chat() for this exact join.

    Returns:
        int: Number of new match rows created.
    """
```

**SQL (v2 lines 1259–1274):**
```sql
INSERT INTO matches (asset_id, strategy, confidence, chat_message_id, matched_date)
SELECT a.id, 'exact_media_id', 1.0, cm.id, cm.created_dt
FROM assets a
JOIN chat_media_ids cmi ON a.file_id = cmi.media_id
JOIN chat_messages cm ON cmi.chat_message_id = cm.id
WHERE a.asset_type = 'chat'
AND a.id NOT IN (SELECT DISTINCT asset_id FROM matches)
```

---

### Strategy 2: Memory UUID (Confidence 1.0)

```python
def _strategy2_memory_uuid(db: sqlite3.Connection) -> int:
    """Strategy 2: Memory UUID match (confidence 1.0).

    For memory_main assets, match assets.memory_uuid against memories.mid.
    The memory_uuid in the filename IS the mid parameter in the download URL
    (key insight: 100% match, zero collisions — verified against full dataset).

    Also captures GPS (lat/lon) directly from memory metadata record.

    Returns:
        int: Number of new match rows created.
    """
```

**SQL (v2 lines 1279–1296):**
```sql
INSERT INTO matches (asset_id, strategy, confidence, memory_id, matched_date,
                     matched_lat, matched_lon, gps_source)
SELECT a.id, 'memory_uuid', 1.0, m.id, m.date_dt,
       m.lat, m.lon,
       CASE WHEN m.lat IS NOT NULL THEN 'metadata' ELSE NULL END
FROM assets a
JOIN memories m ON a.memory_uuid = m.mid
WHERE a.asset_type = 'memory_main'
AND a.id NOT IN (SELECT DISTINCT asset_id FROM matches)
```

---

### Strategy 3: Story ID (Confidence 0.9 or 0.5)

```python
def _strategy3_story_id(db: sqlite3.Connection) -> int:
    """Strategy 3: Story ID ordered pairing (confidence 0.9 or 0.5).

    Pairs story assets with story metadata entries by media type (IMAGE vs VIDEO).
    Both sides are sorted and paired positionally (i-th asset with i-th story).

    Confidence logic:
    - 0.9 if len(assets) == len(stories) for the type (counts match perfectly)
    - 0.5 if counts differ (partial coverage, less certain)

    Implemented separately for IMAGE and VIDEO to handle mixed content correctly.

    Returns:
        int: Total new match rows created (IMAGE + VIDEO).

    Implementation (v2 lines 1301–1350):
    1. Fetch unmatched story assets sorted by filename
    2. Fetch story metadata sorted by created_dt
    3. Group both by is_video / content_type
    4. For IMAGE: conf = 0.9 if counts equal else 0.5; pair up to min count
    5. For VIDEO: same logic
    6. INSERT match rows
    """
```

**SQL (v2 lines 1301–1350):**
```sql
-- Fetch unmatched story assets
SELECT id, filename, is_video FROM assets
WHERE asset_type = 'story'
AND id NOT IN (SELECT DISTINCT asset_id FROM matches)
ORDER BY filename

-- Fetch story metadata (IMAGE)
SELECT id, created_dt FROM stories
WHERE content_type = 'IMAGE'
ORDER BY created_dt

-- Fetch story metadata (VIDEO)
SELECT id, created_dt FROM stories
WHERE content_type = 'VIDEO'
ORDER BY created_dt

-- Insert match rows
INSERT INTO matches (asset_id, strategy, confidence, story_id, matched_date)
VALUES (?, ?, ?, ?, ?)
```

---

### Strategy 4: Timestamp + Type (Confidence 0.8)

```python
def _strategy4_timestamp_type(db: sqlite3.Connection) -> int:
    """Strategy 4: Unique timestamp + type match (confidence 0.8).

    For chat assets, if there is EXACTLY ONE unmatched asset with a given
    date_str + is_video, AND exactly ONE unmatched snap_message with the same
    created_date + media_type, link them.

    Uniqueness on BOTH sides prevents false positives.
    Uses subquery count checks to enforce the uniqueness constraint.

    Returns:
        int: Number of new match rows created.
    """
```

**SQL (v2 lines 1355–1388):**
```sql
INSERT INTO matches (asset_id, strategy, confidence, snap_message_id, matched_date)
SELECT a.id, 'timestamp_type', 0.8, sm.id, sm.created_dt
FROM assets a
JOIN snap_messages sm
    ON a.date_str = sm.created_date
    AND (
        (a.is_video = 1 AND sm.media_type = 'VIDEO')
        OR (a.is_video = 0 AND sm.media_type = 'IMAGE')
    )
WHERE a.asset_type = 'chat'
AND a.id NOT IN (SELECT DISTINCT asset_id FROM matches)
AND (
    SELECT COUNT(*) FROM assets a2
    WHERE a2.asset_type = 'chat'
    AND a2.date_str = a.date_str
    AND a2.is_video = a.is_video
    AND a2.id NOT IN (SELECT DISTINCT asset_id FROM matches)
) = 1
AND (
    SELECT COUNT(*) FROM snap_messages sm2
    WHERE sm2.created_date = a.date_str
    AND sm2.media_type = sm.media_type
    AND sm2.id NOT IN (
        SELECT snap_message_id FROM matches WHERE snap_message_id IS NOT NULL
    )
) = 1
```

---

### Strategy 5: Date + Type + Count (Confidence 0.7)

```python
def _strategy5_date_type_count(db: sqlite3.Connection) -> int:
    """Strategy 5: Date + type + count ordered pairing (confidence 0.7).

    For each (date_str, is_video) group of unmatched chat assets:
    - Count unmatched snap_messages with same date + media_type
    - If counts match AND > 0: pair i-th asset with i-th snap (both sorted)
    - Insert matches at confidence 0.7

    Lower confidence than Strategy 4 because uniqueness is not enforced —
    just count alignment (two photos from same day paired with two snaps).

    Returns:
        int: Number of new match rows created.

    Implementation (v2 lines 1393–1440):
    1. Fetch all unmatched chat assets grouped by (date_str, is_video)
    2. For each group:
       a. Fetch unmatched snaps with same date + type, sorted by created_ms
       b. If len(assets) == len(snaps) and both > 0: zip and insert
    """
```

**SQL (v2 lines 1393–1440):**
```sql
-- Fetch unmatched chat assets by date+type
SELECT id, date_str, is_video, filename FROM assets
WHERE asset_type = 'chat'
AND date_str IS NOT NULL
AND id NOT IN (SELECT DISTINCT asset_id FROM matches)
ORDER BY date_str, is_video, filename

-- Fetch unmatched snaps for a specific date+type
SELECT id, created_dt FROM snap_messages
WHERE created_date = ?
AND media_type = ?
AND id NOT IN (
    SELECT snap_message_id FROM matches WHERE snap_message_id IS NOT NULL
)
ORDER BY created_ms, created_dt

-- Insert paired matches
INSERT INTO matches (asset_id, strategy, confidence, snap_message_id, matched_date)
VALUES (?, 'date_type_count', 0.7, ?, ?)
```

---

### Strategy 6: Date Only (Confidence 0.3)

```python
def _strategy6_date_only(db: sqlite3.Connection) -> int:
    """Strategy 6: Date-only fallback match (confidence 0.3).

    Any unmatched chat or story asset with a known date_str gets a match
    using only the date (no source record linked). matched_date is set to
    date_str + ' 00:00:00' (midnight).

    Ensures every asset gets at least a timestamp for EXIF embedding.
    Low confidence signals this is a date-only guess, not a real match.

    Returns:
        int: Number of new match rows created.
    """
```

**SQL (v2 lines 1445–1459):**
```sql
INSERT INTO matches (asset_id, strategy, confidence, matched_date)
SELECT id, 'date_only', 0.3, date_str || ' 00:00:00'
FROM assets
WHERE asset_type IN ('chat', 'story')
AND date_str IS NOT NULL
AND id NOT IN (SELECT DISTINCT asset_id FROM matches)
```

---

### Bonus: Overlay / ZIP UUID (Confidence 0.9)

```python
def _match_overlay_and_media_zips(db: sqlite3.Connection) -> int:
    """Bonus strategy: Extract UUID from overlay~zip filenames (confidence 0.9).

    Files with names like 'overlay~{uuid}~zip' or 'media~{uuid}~zip' contain
    a UUID that can be matched to memories.mid, bypassing chat/snap intermediaries.

    Algorithm (v2 lines 1464–1514):
    1. Find unmatched assets with file_id containing '~zip', 'overlay~', or 'media~'
    2. For each, try to extract a UUID from parts split by '~':
       - Try each part as-is against UUID_RE
       - Try removing suffixes (-overlay, -main, .zip) from each part
    3. Look up extracted UUID in memories.mid
    4. If found: INSERT as strategy='memory_uuid_zip', confidence=0.9

    Returns:
        int: Number of new match rows created.
    """
```

**SQL (v2 lines 1464–1514):**
```sql
-- Find candidates
SELECT id, file_id FROM assets
WHERE file_id IS NOT NULL
AND (
    file_id LIKE '%~zip%'
    OR file_id LIKE 'overlay~%'
    OR file_id LIKE 'media~%'
)
AND id NOT IN (SELECT DISTINCT asset_id FROM matches)

-- Look up extracted UUID in memories
SELECT id, date_dt, lat, lon FROM memories WHERE mid = ?

-- Insert match
INSERT INTO matches (asset_id, strategy, confidence, memory_id, matched_date,
                     matched_lat, matched_lon, gps_source)
VALUES (?, 'memory_uuid_zip', 0.9, ?, ?, ?, ?,
        CASE WHEN ? IS NOT NULL THEN 'metadata' ELSE NULL END)
```

---

### Best Match Selection

```python
def _set_best_matches(db: sqlite3.Connection) -> int:
    """Select the highest-confidence match per asset as is_best = 1.

    When confidence is tied between strategies, uses strategy priority ranking:
    1. exact_media_id  (highest)
    2. memory_uuid
    3. memory_uuid_zip
    4. story_id
    5. timestamp_type
    6. date_type_count
    7. date_only
    8. (anything else — lowest)

    Guarantees: every asset with any matches gets exactly one is_best=1 row.

    Returns:
        int: Number of rows updated to is_best=1.
    """
```

**SQL (v2 lines 1523–1555):**
```sql
UPDATE matches SET is_best = 1
WHERE id IN (
    SELECT m.id FROM matches m
    INNER JOIN (
        SELECT asset_id, MAX(confidence) as max_conf
        FROM matches
        GROUP BY asset_id
    ) best ON m.asset_id = best.asset_id AND m.confidence = best.max_conf
    WHERE m.id = (
        SELECT m2.id FROM matches m2
        WHERE m2.asset_id = m.asset_id AND m2.confidence = best.max_conf
        ORDER BY CASE m2.strategy
            WHEN 'exact_media_id'  THEN 1
            WHEN 'memory_uuid'     THEN 2
            WHEN 'memory_uuid_zip' THEN 3
            WHEN 'story_id'        THEN 4
            WHEN 'timestamp_type'  THEN 5
            WHEN 'date_type_count' THEN 6
            WHEN 'date_only'       THEN 7
            ELSE 8
        END, m2.id
        LIMIT 1
    )
)
```

---

## Orchestrator

```python
def phase2_match(
    db: sqlite3.Connection,
    progress_cb: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Phase 2 orchestrator: Match assets to metadata via priority cascade.

    Runs all strategies in order:
    1. _strategy1_exact_media_id()
    2. _strategy2_memory_uuid()
    3. _strategy3_story_id()
    4. _strategy4_timestamp_type()
    5. _strategy5_date_type_count()
    6. _strategy6_date_only()
    7. _match_overlay_and_media_zips()
    8. _set_best_matches()

    IMPORTANT: Clears the matches table at the start (DELETE FROM matches).
    This allows Phase 2 to be rerun without duplicates.

    Args:
        db: SQLite connection (Phase 1 must have run first)
        progress_cb: Optional callback(message: str)

    Returns:
        dict[str, Any]:
        {
            'exact_media_id': int,
            'memory_uuid': int,
            'story_id': int,
            'timestamp_type': int,
            'date_type_count': int,
            'date_only': int,
            'memory_uuid_zip': int,
            'best': int,           # total is_best=1 rows
            'total_matched': int,  # same as best
            'true_orphans': int,   # unmatched non-overlay assets
            'overlays': int,       # memory_overlay asset count
            'filtered': int,       # chat_overlay + chat_thumbnail count
            'eligible': int,       # total - overlays - filtered
            'match_rate': float,   # total_matched / eligible (0.0–1.0)
            'elapsed': float,      # seconds
        }

    Implementation (v2 lines 1558–1647):
    1. Check asset count; return empty dict if 0
    2. DELETE FROM matches (clear previous run)
    3. Call each strategy, collect counts, call progress_cb after each
    4. Call _set_best_matches()
    5. Compute summary statistics
    6. Query confidence distribution (bucket by 0.1 increments)
    7. Log/callback summary report
    8. Return stats dict
    """
```

---

## Database Schema

The full SQLite DDL is defined in `snatched/processing/schema.sql`. Key tables used by Phase 2:

```sql
-- MATCHES: Created by Phase 2 — links assets to metadata sources
CREATE TABLE IF NOT EXISTS matches (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id        INTEGER NOT NULL REFERENCES assets(id),
    strategy        TEXT NOT NULL,        -- 'exact_media_id', 'memory_uuid', etc.
    confidence      REAL NOT NULL DEFAULT 0.0,  -- 0.3, 0.7, 0.8, 0.9, or 1.0
    is_best         BOOLEAN NOT NULL DEFAULT 0, -- 1 = best match for this asset
    memory_id       INTEGER REFERENCES memories(id),
    chat_message_id INTEGER REFERENCES chat_messages(id),
    snap_message_id INTEGER REFERENCES snap_messages(id),
    story_id        INTEGER REFERENCES stories(id),
    matched_date    TEXT,             -- ISO 8601 or 'YYYY-MM-DD HH:MM:SS'
    matched_lat     REAL,             -- from memory metadata GPS
    matched_lon     REAL,             -- from memory metadata GPS
    gps_source      TEXT,             -- 'metadata' | NULL (location_history set by Phase 3)
    display_name    TEXT,             -- set by Phase 3 enrich_display_names()
    creator_str     TEXT,             -- set by Phase 3
    direction       TEXT,             -- 'sent' | 'received' | NULL (set by Phase 3)
    conversation    TEXT,             -- human-readable name (set by Phase 3)
    lane            TEXT DEFAULT 'memories',   -- 'memories' | 'chats' | 'stories'
    output_subdir   TEXT,             -- set by Phase 3 enrich_output_paths()
    output_filename TEXT,             -- set by Phase 3 enrich_output_paths()
    exif_tags_json  TEXT,             -- JSON dict set by Phase 3 enrich_exif_tags()
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_matches_asset    ON matches(asset_id);
CREATE INDEX IF NOT EXISTS idx_matches_best     ON matches(asset_id, is_best);
CREATE INDEX IF NOT EXISTS idx_matches_strategy ON matches(strategy);
CREATE INDEX IF NOT EXISTS idx_matches_lane     ON matches(lane);
```

---

## Key SQL Queries

```sql
-- After Phase 2: overall match summary
SELECT
    COUNT(*) as total_assets,
    COUNT(CASE WHEN m.is_best = 1 THEN 1 END) as matched,
    COUNT(CASE WHEN m.is_best IS NULL THEN 1 END) as unmatched
FROM assets a
LEFT JOIN matches m ON a.id = m.asset_id AND m.is_best = 1;

-- Confidence distribution
SELECT
    ROUND(confidence, 1) as conf_bucket,
    COUNT(*) as count
FROM matches
WHERE is_best = 1
GROUP BY conf_bucket
ORDER BY conf_bucket DESC;

-- Strategy breakdown
SELECT strategy, COUNT(*) as count, ROUND(AVG(confidence), 2) as avg_conf
FROM matches
WHERE is_best = 1
GROUP BY strategy
ORDER BY count DESC;

-- True orphans (chat/story assets with no match at all)
SELECT COUNT(*) FROM assets
WHERE asset_type IN ('chat', 'story')
AND id NOT IN (SELECT DISTINCT asset_id FROM matches);

-- Verify is_best uniqueness (should return 0)
SELECT asset_id, COUNT(*) FROM matches
WHERE is_best = 1
GROUP BY asset_id
HAVING COUNT(*) > 1;
```

---

## Multi-User Adaptation

**Zero changes required.** All Phase 2 strategies are pure SQLite operations on the per-user database. There is no shared state and no concurrency issues — each user's Phase 2 runs on their own isolated `proc.db`.

The only v3 adaptation is replacing `print()` with the optional `progress_cb` callback:
```python
# v2
print(f"  Strategy 1: {count:,} exact matches")

# v3
msg = f"Strategy 1 (exact_media_id): {count:,} matches"
if progress_cb:
    progress_cb(msg)
logger.info(msg)
```

---

## Code Examples

### Running Phase 2

```python
from pathlib import Path
from snatched.processing.sqlite import open_database
from snatched.processing.match import phase2_match

db = open_database(Path("/data/dave/proc.db"))

def on_progress(msg: str):
    print(f"[Phase 2] {msg}")

stats = phase2_match(db, progress_cb=on_progress)

print(f"Match rate: {stats['match_rate']:.1%}")
print(f"Best matches: {stats['total_matched']:,}")
print(f"True orphans: {stats['true_orphans']:,}")
```

### Testing individual strategies

```python
from snatched.processing.match import (
    _strategy1_exact_media_id,
    _strategy2_memory_uuid,
    _set_best_matches,
)

db = open_database(Path(":memory:"))
# ... populate Phase 1 data ...

# Run strategies individually
s1 = _strategy1_exact_media_id(db)
s2 = _strategy2_memory_uuid(db)
print(f"Strategy 1: {s1} matches, Strategy 2: {s2} matches")

# Set best matches
best = _set_best_matches(db)
print(f"Best selected: {best}")

# Verify no asset has multiple is_best rows
dupes = db.execute("""
    SELECT asset_id, COUNT(*) FROM matches
    WHERE is_best = 1
    GROUP BY asset_id HAVING COUNT(*) > 1
""").fetchall()
assert len(dupes) == 0, f"Duplicate best matches found: {dupes}"
```

### Verifying confidence scores

```python
# After running phase2_match(), verify confidence values are correct
rows = db.execute("""
    SELECT strategy, MIN(confidence), MAX(confidence)
    FROM matches
    GROUP BY strategy
""").fetchall()

expected = {
    'exact_media_id':  (1.0, 1.0),
    'memory_uuid':     (1.0, 1.0),
    'memory_uuid_zip': (0.9, 0.9),
    'story_id':        (0.5, 0.9),  # can be either
    'timestamp_type':  (0.8, 0.8),
    'date_type_count': (0.7, 0.7),
    'date_only':       (0.3, 0.3),
}

for strategy, min_conf, max_conf in rows:
    if strategy in expected:
        exp_min, exp_max = expected[strategy]
        assert min_conf >= exp_min and max_conf <= exp_max, \
            f"Unexpected confidence for {strategy}: [{min_conf}, {max_conf}]"
```

---

## Acceptance Criteria

- [ ] `_matched_asset_ids()` returns a Python `set[int]` of existing matched asset IDs
- [ ] `_strategy1_exact_media_id()` links chat assets to chat_messages via file_id = media_id
- [ ] `_strategy1_exact_media_id()` assigns confidence exactly 1.0
- [ ] `_strategy2_memory_uuid()` links memory_main assets to memories via UUID
- [ ] `_strategy2_memory_uuid()` captures GPS (lat/lon) from memories table when available
- [ ] `_strategy2_memory_uuid()` assigns confidence exactly 1.0
- [ ] `_strategy3_story_id()` pairs story assets with stories by media type (IMAGE vs VIDEO)
- [ ] `_strategy3_story_id()` assigns confidence 0.9 when counts match, 0.5 when they differ
- [ ] `_strategy4_timestamp_type()` only matches when both sides have exactly 1 record for date+type
- [ ] `_strategy4_timestamp_type()` assigns confidence exactly 0.8
- [ ] `_strategy5_date_type_count()` pairs assets with snaps when counts align per date+type group
- [ ] `_strategy5_date_type_count()` assigns confidence exactly 0.7
- [ ] `_strategy6_date_only()` matches any unmatched chat/story asset with a date_str
- [ ] `_strategy6_date_only()` assigns confidence exactly 0.3
- [ ] `_match_overlay_and_media_zips()` extracts UUIDs from complex overlay~zip filenames
- [ ] `_match_overlay_and_media_zips()` assigns confidence exactly 0.9
- [ ] `_set_best_matches()` selects exactly one is_best=1 row per asset
- [ ] `_set_best_matches()` breaks confidence ties by strategy priority order
- [ ] `phase2_match()` clears matches table before running (idempotent reruns)
- [ ] `phase2_match()` calls all 7 strategy functions in the correct order
- [ ] `phase2_match()` calls progress_cb after each strategy (if provided)
- [ ] `phase2_match()` returns dict with all required keys including match_rate
- [ ] After `phase2_match()`, every chat/story asset with date_str has at least one match
- [ ] SQL queries are exact ports from v2 — no algorithmic changes
- [ ] All `_strategy*` functions are pure SQLite — no Python-side filtering logic
