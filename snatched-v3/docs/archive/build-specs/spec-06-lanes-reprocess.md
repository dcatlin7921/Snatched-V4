# SPEC-06: Lanes + Reprocess

**Status:** Final
**Version:** 3.0
**Date:** 2026-02-23

---

## Module Overview

This specification covers TWO modules that manage export lanes and selective reprocessing:

1. **`snatched/processing/lanes.py`** — Lane controller managing three independent export pipelines (Memories, Stories, Chats) with lane-specific feature sets
2. **`snatched/processing/reprocess.py`** — Selective reprocessing engine allowing re-runs of any phase without full re-ingest

Together, these modules enable efficient, targeted exports and iterative refinement without destroying the full processing database.

**V2 source file:** `/home/dave/tools/snapfix/snatched.py`

---

## Files to Create

```
snatched/
├── processing/
│   ├── lanes.py              # Three-lane export controller
│   └── reprocess.py          # Selective reprocessing engine
```

---

## Dependencies

**Modules that must be built first:**
- `snatched/processing/ingest.py` — Phase 1 pipeline (spec-03)
- `snatched/processing/match.py` — Phase 2 matching logic (spec-04)
- `snatched/processing/enrich.py` — Phase 3 enrichment functions (spec-05)
- `snatched/processing/export.py` — Phase 4 export functions (spec-05)
- `snatched/db.py` — SQLite connection + schema (spec-02)

**Module imports:**
```python
import sqlite3
import time
from enum import Enum
from pathlib import Path
from typing import Callable

from processing import ingest, match, enrich, export
```

---

## V2 Source Reference

**Source file:** `/home/dave/tools/snapfix/snatched.py`

The `main()` function (lines 4579–4813 of snatched.py) orchestrates all four phases as a single sequential run. In v3, this logic is split:

- `lanes.py` — Lane-specific orchestration (which asset types each lane processes)
- `reprocess.py` — Selective phase re-run logic (re-run phase N without re-running earlier phases)

V2 does NOT have explicit lane or reprocess concepts; these are v3 innovations. The lane design generalizes v2's single-pass pipeline into three independent pipelines that share the same SQLite database.

---

## Lane System Architecture

### Three Lanes Overview

| Lane | Asset Types | Phase 3 Enrich | Phase 4 Export | EXIF | XMP | Chat Render |
|------|-------------|----------------|----------------|------|-----|-------------|
| **Memories** | memory_main, memory_overlay | GPS, names, paths, tags | Copy, burn overlays | Yes | Yes | No |
| **Stories** | story | Names, paths, tags | Copy, EXIF | Yes | Yes | No |
| **Chats** | chat | Names, paths, tags | Copy, EXIF, text export, PNG | Yes | Yes | Yes |

### Lane Design Rationale

- **Independent pipelines:** Allows exporting just memories without processing chats
- **Shared database:** All lanes query the same per-user SQLite database (matches, assets, etc.)
- **Shared Phase 3/4 logic:** Enrich and export functions are lane-agnostic; lanes control which assets they process via SQL filters
- **Feature toggles:** Some features (overlay burning, chat PNG) are memory/chat specific

### Lane SQL Filters

Each lane applies a SQL WHERE clause to enrich/export operations:

```sql
-- Memories lane
WHERE asset_type IN ('memory_main', 'memory_overlay')

-- Stories lane
WHERE asset_type = 'story'

-- Chats lane
WHERE asset_type = 'chat'
```

---

## Function Signatures

### `snatched/processing/lanes.py`

```python
import sqlite3
import time
from enum import Enum
from pathlib import Path
from typing import Callable


class Lane(Enum):
    """Export lane identifiers."""
    MEMORIES = "memories"
    STORIES = "stories"
    CHATS = "chats"
    ALL = "all"


class LaneController:
    """Manages lane-specific export orchestration.

    Each lane processes a subset of assets (by asset_type) through
    Phase 3 (enrich) and Phase 4 (export) using shared pipeline functions.
    """

    def __init__(
        self,
        db: sqlite3.Connection,
        project_dir: Path,
        config: "Config",
        progress_cb: Callable[[str], None] | None = None
    ) -> None:
        """Initialize lane controller.

        Args:
            db: SQLite database connection (per-user proc.db)
            project_dir: Project root directory (user's /data/{username}/ dir)
            config: Configuration object (snatched.toml parsed)
            progress_cb: Optional callback for progress messages
        """
        ...

    def get_lane_asset_filter(self, lane: "Lane | str") -> str:
        """Return SQL WHERE clause fragment for lane asset filtering.

        Args:
            lane: Lane identifier (Lane enum or string name)

        Returns:
            SQL fragment, e.g., "asset_type = 'chat'" or
            "asset_type IN ('memory_main', 'memory_overlay')"

        Raises:
            ValueError: If lane is not recognized
        """
        ...

    def count_assets_in_lane(self, lane: "Lane | str") -> int:
        """Count best-matched assets eligible for export in lane.

        Queries: SELECT COUNT(*) FROM assets a
                 JOIN matches m ON a.id = m.asset_id
                 WHERE m.is_best = 1 AND {lane_filter}

        Args:
            lane: Lane identifier

        Returns:
            Integer count of assets eligible for export
        """
        ...

    def run_lane(
        self,
        lane: "Lane | str",
        phases: list[int] | None = None,
        skip_phase: list[int] | None = None
    ) -> dict:
        """Run enrich + export for a specific lane.

        Phases:
            1 = ingest (full ingest, rarely run per-lane)
            2 = match
            3 = enrich
            4 = export

        If phases is None, runs phases 3 and 4 (the lane-relevant phases).
        Phase 1 and 2 always operate on all asset types; they are not
        lane-filtered. If phases=[1,2,3,4] is requested, phases 1 and 2
        run without lane filtering; phases 3 and 4 apply lane filters.

        Args:
            lane: Lane to run ('memories', 'stories', 'chats', or 'all')
            phases: Phases to run (default: [3, 4])
            skip_phase: Phases to skip

        Returns:
            {
                'lane': str,
                'assets_processed': int,
                'phase_results': {
                    '3': {...},  # enrich result dict (if run)
                    '4': {...}   # export result dict (if run)
                },
                'elapsed': float
            }
        """
        ...

    def run_memories(self, **kwargs) -> dict:
        """Shortcut: run_lane(Lane.MEMORIES, **kwargs)"""
        ...

    def run_stories(self, **kwargs) -> dict:
        """Shortcut: run_lane(Lane.STORIES, **kwargs)"""
        ...

    def run_chats(self, **kwargs) -> dict:
        """Shortcut: run_lane(Lane.CHATS, **kwargs)"""
        ...

    def run_all(self, **kwargs) -> dict:
        """Run all three lanes sequentially.

        Runs memories, then stories, then chats. Each lane runs
        phases 3 and 4 (enrich + export) with its lane filter.

        Returns:
            {
                'memories': {...},  # result from run_lane('memories')
                'stories': {...},   # result from run_lane('stories')
                'chats': {...},     # result from run_lane('chats')
                'total_elapsed': float
            }
        """
        ...
```

### `snatched/processing/reprocess.py`

```python
import sqlite3
import time
from enum import Enum
from pathlib import Path
from typing import Callable

from processing import match, enrich, export


class ReprocessMode(Enum):
    """Reprocessing modes for selective phase re-runs."""
    MATCH = "match"        # Re-run Phase 2 only
    ENRICH = "enrich"      # Re-run Phase 3 only
    EXPORT = "export"      # Re-run Phase 4 only
    CHAT = "chat"          # Re-run chat export only (export_chat_text + export_chat_png)
    XMP = "xmp"            # Re-run XMP sidecar generation only
    LANE = "lane"          # Re-run enrich+export for a lane (requires lane=)
    ALL = "all"            # Re-run phases 2–4 (full reprocess, preserves ingest)


def validate_reprocess(
    db: sqlite3.Connection,
    mode: "ReprocessMode | str",
    lane: str | None = None
) -> tuple[bool, str]:
    """Validate that reprocessing is safe and prerequisite data exists.

    Checks:
    - Phase 1 assets exist (required for all modes)
    - Phase 2 matches exist (required if mode starts at phase 3+)
    - Output directory is writable (required if mode includes phase 4)

    Args:
        db: SQLite database connection
        mode: Reprocessing mode (ReprocessMode enum or string)
        lane: Optional lane filter ('memories', 'stories', 'chats')

    Returns:
        (is_valid: bool, reason: str)
        reason is empty string if is_valid is True.
    """
    ...


def clear_phase_data(
    db: sqlite3.Connection,
    phase: int,
    lane: str | None = None
) -> dict:
    """Clear all data from a phase to enable safe re-run.

    Phase 2 (match):
        DELETE FROM matches
        UPDATE assets SET is_best=0 (reset best-match flags)

    Phase 3 (enrich):
        UPDATE matches SET
            matched_lat=NULL, matched_lon=NULL, gps_source=NULL,
            display_name=NULL, creator_str=NULL, direction=NULL, conversation=NULL,
            output_subdir=NULL, output_filename=NULL, exif_tags_json=NULL

    Phase 4 (export):
        UPDATE assets SET output_path=NULL, output_sha256=NULL,
                          exif_written=NULL, exif_error=NULL

    If lane is specified, only clears data for that lane's asset types:
        'memories' → asset_type IN ('memory_main', 'memory_overlay')
        'stories'  → asset_type = 'story'
        'chats'    → asset_type = 'chat'

    Args:
        db: SQLite database connection
        phase: Phase number to clear (2, 3, or 4)
        lane: Optional lane filter

    Returns:
        {
            'rows_affected': int,
            'phase': int,
            'lane': str | None
        }

    Raises:
        ValueError: If phase is not 2, 3, or 4
    """
    ...


def reprocess(
    db: sqlite3.Connection,
    project_dir: Path,
    config: "Config",
    mode: "ReprocessMode | str",
    lane: str | None = None,
    clear: bool = True,
    progress_cb: Callable[[str], None] | None = None
) -> dict:
    """Main reprocessing engine.

    Selectively re-runs one or more phases without full re-ingest (Phase 1).
    Phase 1 data (assets table) is never touched by reprocess().

    Args:
        db: SQLite database connection
        project_dir: User's project directory (/data/{username}/)
        config: Configuration object
        mode: Reprocessing mode (MATCH, ENRICH, EXPORT, CHAT, XMP, LANE, ALL)
        lane: Optional lane filter ('memories', 'stories', 'chats')
               Required if mode is LANE.
        clear: If True, clear phase data before reprocessing (safe default)
               If False, appends to existing data (requires expertise)
        progress_cb: Optional progress callback

    Returns:
        {
            'mode': str,
            'lane': str | None,
            'cleared': bool,
            'phase_results': {
                '2': {...},     # match results (if mode includes phase 2)
                '3': {...},     # enrich results (if mode includes phase 3)
                '4': {...},     # export results (if mode includes phase 4)
                'chat': {...},  # chat export results (if mode == CHAT)
                'xmp': {...},   # XMP results (if mode == XMP)
            },
            'success': bool,
            'errors': list[str],
            'elapsed': float
        }
    """
    ...


# Convenience wrappers

def reprocess_match(
    db: sqlite3.Connection,
    project_dir: Path,
    config: "Config",
    **kwargs
) -> dict:
    """Shortcut: reprocess(mode=ReprocessMode.MATCH, **kwargs)"""
    ...


def reprocess_enrich(
    db: sqlite3.Connection,
    project_dir: Path,
    config: "Config",
    lane: str | None = None,
    **kwargs
) -> dict:
    """Shortcut: reprocess(mode=ReprocessMode.ENRICH, lane=lane, **kwargs)"""
    ...


def reprocess_export(
    db: sqlite3.Connection,
    project_dir: Path,
    config: "Config",
    lane: str | None = None,
    **kwargs
) -> dict:
    """Shortcut: reprocess(mode=ReprocessMode.EXPORT, lane=lane, **kwargs)"""
    ...


def reprocess_chat(
    db: sqlite3.Connection,
    project_dir: Path,
    config: "Config",
    **kwargs
) -> dict:
    """Shortcut: reprocess(mode=ReprocessMode.CHAT, **kwargs)"""
    ...


def reprocess_xmp(
    db: sqlite3.Connection,
    project_dir: Path,
    config: "Config",
    **kwargs
) -> dict:
    """Shortcut: reprocess(mode=ReprocessMode.XMP, **kwargs)"""
    ...


def reprocess_lane(
    db: sqlite3.Connection,
    project_dir: Path,
    config: "Config",
    lane: str,
    **kwargs
) -> dict:
    """Shortcut: reprocess(mode=ReprocessMode.LANE, lane=lane, **kwargs)"""
    ...
```

---

## Database Schema

No new tables are required for lanes or reprocessing. Lanes are implemented as SQL filters applied to the existing per-user SQLite schema. Each user has their own SQLite database at `/data/{username}/proc.db`.

The complete `assets` table DDL (the primary table used by lane filtering):

```sql
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
    xmp_written     BOOLEAN DEFAULT 0,  -- v3 addition
    xmp_path        TEXT,               -- v3 addition
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_assets_file_id ON assets(file_id);
CREATE INDEX IF NOT EXISTS idx_assets_memory_uuid ON assets(memory_uuid);
CREATE INDEX IF NOT EXISTS idx_assets_date_str ON assets(date_str);
CREATE INDEX IF NOT EXISTS idx_assets_asset_type ON assets(asset_type);

-- Matches table (lane column used for lane filtering)
CREATE TABLE IF NOT EXISTS matches (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id        INTEGER NOT NULL REFERENCES assets(id),
    strategy        TEXT NOT NULL,
    confidence      REAL NOT NULL DEFAULT 0.0,
    is_best         BOOLEAN NOT NULL DEFAULT 0,
    lane            TEXT,               -- v3 addition: 'memories', 'chats', 'stories'
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
    output_subdir   TEXT,
    output_filename TEXT,
    exif_tags_json  TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_matches_asset ON matches(asset_id);
CREATE INDEX IF NOT EXISTS idx_matches_best ON matches(asset_id, is_best);
CREATE INDEX IF NOT EXISTS idx_matches_strategy ON matches(strategy);

-- Lane filter examples:
-- Memories: WHERE asset_type IN ('memory_main', 'memory_overlay')
-- Stories:  WHERE asset_type = 'story'
-- Chats:    WHERE asset_type = 'chat'
```

**Optional future column** (NOT required for v3.0):
```sql
-- Add to track which lanes have processed each match (v3.1+):
ALTER TABLE matches ADD COLUMN lane_processed TEXT;
-- Values: 'memories' | 'stories' | 'chats' | NULL
```

---

## Key SQL Queries

**Count assets in a lane:**
```sql
SELECT COUNT(*)
FROM assets a
JOIN matches m ON a.id = m.asset_id
WHERE m.is_best = 1
  AND asset_type IN ('memory_main', 'memory_overlay');  -- memories lane
```

**Clear Phase 3 data for a lane:**
```sql
UPDATE matches SET
    matched_lat=NULL, matched_lon=NULL, gps_source=NULL,
    display_name=NULL, creator_str=NULL, direction=NULL, conversation=NULL,
    output_subdir=NULL, output_filename=NULL, exif_tags_json=NULL
WHERE id IN (
    SELECT m.id FROM matches m
    JOIN assets a ON m.asset_id = a.id
    WHERE a.asset_type IN ('memory_main', 'memory_overlay')
);
```

**Clear Phase 4 data for a lane:**
```sql
UPDATE assets SET
    output_path=NULL, output_sha256=NULL,
    exif_written=NULL, exif_error=NULL
WHERE asset_type = 'chat';  -- chats lane
```

**Check Phase 2 data exists (for validate_reprocess):**
```sql
SELECT COUNT(*) FROM matches WHERE is_best = 1;
```

---

## Multi-User Adaptation

Lanes are entirely per-user because each user has an isolated SQLite database (`/data/{username}/proc.db`). There is no cross-user state:

- `LaneController` receives `db` (user's SQLite connection) and `project_dir` (user's data directory)
- Lane filters are SQL WHERE clauses on the user's local asset data
- `reprocess()` operates on a single user's database at a time
- The web app (spec-08) passes the correct `db` and `project_dir` for the authenticated user

---

## Lane Feature Matrix

### What Each Lane Does in Detail

#### Memories Lane

```
Phase 3 (Enrich):
  enrich_gps()           — GPS from metadata + location history breadcrumbs
  enrich_display_names() — names from chat/contact metadata (for overlay text)
  enrich_output_paths()  — output/memories/{YYYY}/{MM}/ directory paths
  enrich_exif_tags()     — full metadata: GPS, date, creator, tags

Phase 4 (Export):
  copy_files()           — copies memory_main + memory_overlay files
  burn_overlays()        — composites overlay PNGs/videos onto main media
  write_exif()           — embeds EXIF metadata into output files
  (skips) export_chat_text() — not applicable
  (skips) export_chat_png()  — not applicable

Output structure:
  output/memories/{YYYY}/{MM}/Snap_Memory_{UUID}.jpg
  output/memories/{YYYY}/{MM}/Snap_Memory_{UUID}_overlay.png  (if burned)
```

#### Stories Lane

```
Phase 3 (Enrich):
  enrich_display_names() — who posted the story
  enrich_output_paths()  — output/stories/ paths
  enrich_exif_tags()     — metadata with story ID, creator, date

Phase 4 (Export):
  copy_files()           — copies story media files
  write_exif()           — embeds EXIF metadata
  (skips) burn_overlays()    — stories do not have overlay pairs
  (skips) export_chat_text() — not applicable
  (skips) export_chat_png()  — not applicable

Output structure:
  output/stories/Snap_Story_{UUID}.jpg
```

#### Chats Lane

```
Phase 3 (Enrich):
  enrich_display_names() — chat participant display names
  enrich_output_paths()  — output/chat/{CONVERSATION}/Media/ paths
  enrich_exif_tags()     — creator, direction (sent/received), conversation name

Phase 4 (Export):
  copy_files()           — copies chat media files
  write_exif()           — embeds EXIF metadata
  export_chat_text()     — transcript .txt files per conversation
  export_chat_png()      — Snapchat-style PNG screenshots (via ChatRenderer)
  (skips) burn_overlays()    — chats do not have overlay pairs

Output structure:
  output/chat/{CONVERSATION}/Media/Snap_Chat_{UUID}.jpg
  output/chat/{CONVERSATION}/Transcripts/{CONVERSATION}.txt
  output/chat/{CONVERSATION}/Saved Chat Screenshots/page-1.png
  output/chat/{CONVERSATION}/Saved Chat Screenshots/page-2.png  (if multi-page)
```

---

## Code Examples

### Lane Controller — run_all Implementation

```python
class LaneController:
    def run_all(self, **kwargs) -> dict:
        """Run all three lanes sequentially."""
        t0 = time.time()
        results = {}

        for lane_name in ['memories', 'stories', 'chats']:
            if self.progress_cb:
                self.progress_cb(f"Starting {lane_name} lane...")
            result = self.run_lane(lane_name, **kwargs)
            results[lane_name] = result

        return {
            'memories': results['memories'],
            'stories': results['stories'],
            'chats': results['chats'],
            'total_elapsed': time.time() - t0
        }
```

### Clear Phase Data — Phase 3 with Lane Filter

```python
def clear_phase_data(db: sqlite3.Connection, phase: int, lane: str | None = None) -> dict:
    """Clear phase data for reprocessing."""
    if phase not in (2, 3, 4):
        raise ValueError(f"phase must be 2, 3, or 4; got {phase}")

    # Build lane WHERE clause for joins
    lane_where = ""
    if lane == 'memories':
        lane_where = "a.asset_type IN ('memory_main', 'memory_overlay')"
    elif lane == 'stories':
        lane_where = "a.asset_type = 'story'"
    elif lane == 'chats':
        lane_where = "a.asset_type = 'chat'"

    if phase == 3:
        if lane_where:
            sql = f"""
                UPDATE matches SET
                    matched_lat=NULL, matched_lon=NULL, gps_source=NULL,
                    display_name=NULL, creator_str=NULL, direction=NULL, conversation=NULL,
                    output_subdir=NULL, output_filename=NULL, exif_tags_json=NULL
                WHERE id IN (
                    SELECT m.id FROM matches m
                    JOIN assets a ON m.asset_id = a.id
                    WHERE {lane_where}
                )
            """
        else:
            sql = """
                UPDATE matches SET
                    matched_lat=NULL, matched_lon=NULL, gps_source=NULL,
                    display_name=NULL, creator_str=NULL, direction=NULL, conversation=NULL,
                    output_subdir=NULL, output_filename=NULL, exif_tags_json=NULL
            """
        cursor = db.execute(sql)
        db.commit()
        return {'rows_affected': cursor.rowcount, 'phase': phase, 'lane': lane}

    elif phase == 4:
        if lane_where:
            sql = f"""
                UPDATE assets SET output_path=NULL, output_sha256=NULL,
                                  exif_written=NULL, exif_error=NULL
                WHERE {lane_where.replace('a.', '')}
            """
        else:
            sql = """
                UPDATE assets SET output_path=NULL, output_sha256=NULL,
                                  exif_written=NULL, exif_error=NULL
            """
        cursor = db.execute(sql)
        db.commit()
        return {'rows_affected': cursor.rowcount, 'phase': phase, 'lane': lane}

    elif phase == 2:
        cursor = db.execute("DELETE FROM matches")
        db.execute("UPDATE assets SET is_best=0")
        db.commit()
        return {'rows_affected': cursor.rowcount, 'phase': phase, 'lane': None}
```

### Reprocess — Main Logic

```python
def reprocess(db, project_dir, config, mode, lane=None, clear=True, progress_cb=None) -> dict:
    """Main reprocessing engine."""
    t0 = time.time()

    # Normalize mode
    if isinstance(mode, str):
        mode = ReprocessMode(mode)

    # Validate preconditions
    is_valid, reason = validate_reprocess(db, mode, lane)
    if not is_valid:
        return {
            'mode': str(mode),
            'lane': lane,
            'cleared': False,
            'phase_results': {},
            'success': False,
            'errors': [reason],
            'elapsed': 0.0
        }

    results = {}

    # Clear phase data before re-running (safe default)
    if clear:
        if mode in (ReprocessMode.MATCH, ReprocessMode.ALL):
            clear_phase_data(db, 2, lane)
        if mode in (ReprocessMode.ENRICH, ReprocessMode.LANE, ReprocessMode.ALL):
            clear_phase_data(db, 3, lane)
        if mode in (ReprocessMode.EXPORT, ReprocessMode.LANE, ReprocessMode.ALL):
            clear_phase_data(db, 4, lane)

    # Execute phases
    if mode in (ReprocessMode.MATCH, ReprocessMode.ALL):
        results['2'] = match.phase_match(db, config)

    if mode in (ReprocessMode.ENRICH, ReprocessMode.LANE, ReprocessMode.ALL):
        results['3'] = enrich.phase_enrich(db, project_dir, config, lane_filter=lane)

    if mode in (ReprocessMode.EXPORT, ReprocessMode.LANE, ReprocessMode.ALL):
        results['4'] = export.phase_export(db, project_dir, config, lane_filter=lane)

    if mode == ReprocessMode.CHAT:
        results['chat'] = export.export_chat_text(db, project_dir, config)
        results['chat_png'] = export.export_chat_png(db, project_dir, config)

    if mode == ReprocessMode.XMP:
        results['xmp'] = export.write_xmp_sidecars(db, project_dir, config)

    return {
        'mode': mode.value,
        'lane': lane,
        'cleared': clear,
        'phase_results': results,
        'success': True,
        'errors': [],
        'elapsed': time.time() - t0
    }
```

---

## Reprocessing Use Cases

### Use Case 1: Fix Matching (False Positives)

User notices some false positives in Phase 2 matching and wants to re-run with adjusted thresholds:

```python
# Re-run Phase 2 (clears old matches first)
reprocess(db, project_dir, config, mode='match', clear=True)

# Re-run Phase 3 with new matches
reprocess(db, project_dir, config, mode='enrich', clear=True)

# Re-run Phase 4 to update output files
reprocess(db, project_dir, config, mode='export', clear=True)
```

### Use Case 2: Re-export Chat Screenshots with Dark Mode

User wants better chat PNG renderings with `dark_mode=True`. No need to re-ingest or re-match:

```python
config.lanes.chats.dark_mode = True
reprocess(db, project_dir, config, mode='chat')
# clear=True is default but chat mode only clears chat export data
```

### Use Case 3: Memories-Only Export

Processing is complete but user needs to re-export memories only (stories/chats already done):

```python
lane_ctrl = LaneController(db, project_dir, config)
result = lane_ctrl.run_memories(phases=[3, 4])  # Just enrich + export, memories only
```

### Use Case 4: Fix EXIF Metadata Tags

User discovers EXIF tags were built incorrectly. They update `enrich.py` then:

```python
# Re-enrich Phase 3 (just EXIF tag building, no GPS re-lookup needed)
reprocess(db, project_dir, config, mode='enrich', clear=True)

# Re-export Phase 4 with fresh tags (clear=True overwrites output files)
reprocess(db, project_dir, config, mode='export', clear=True)
```

### Use Case 5: Full Reprocess (Preserve Ingest)

User wants to redo everything except re-parsing the ZIP (Phase 1 is expensive):

```python
# Clears phases 2, 3, 4 data; re-runs match → enrich → export
reprocess(db, project_dir, config, mode='all', clear=True)
```

---

## Acceptance Criteria

### Lane Controller

- [ ] `Lane` enum values are `memories`, `stories`, `chats`, `all`
- [ ] `get_lane_asset_filter()` returns correct SQL for each lane
- [ ] `count_assets_in_lane()` counts only best-matched assets
- [ ] `run_all()` executes memories, stories, chats sequentially
- [ ] Each lane produces correct output directory structure
- [ ] Progress callback invoked at lane start and key milestones
- [ ] Return dict includes `lane`, `assets_processed`, `phase_results`, `elapsed`
- [ ] Lane filter correctly excludes other asset types

### Reprocessing Engine

- [ ] `validate_reprocess()` returns `(False, reason)` when Phase 1 data is missing
- [ ] `validate_reprocess()` returns `(False, reason)` when Phase 2 data missing and mode requires it
- [ ] `clear_phase_data()` correctly clears phase 2, 3, and 4 data
- [ ] Lane-filtered clearing only affects that lane's assets
- [ ] Phase 2 re-run works without Phase 1 re-run
- [ ] Phase 3 re-run works without Phase 2 re-run (uses existing matches)
- [ ] Phase 4 re-run works without Phase 3 re-run (uses existing enrich data)
- [ ] CHAT mode only runs `export_chat_text()` and `export_chat_png()`
- [ ] XMP mode only runs `write_xmp_sidecars()`
- [ ] `clear=False` does not delete existing data before re-running
- [ ] Errors during reprocess are caught and returned in `errors` list
- [ ] Database is never left in corrupted state on failure

---

## Implementation Notes

### Lane Independence

Lanes in v3.0 run **sequentially**, not in parallel. This is correct because:
- SQLite does not support concurrent writes
- Users typically want to export one lane at a time
- Parallel lane support can be added in v3.1 if needed (separate SQLite connections or PostgreSQL migration)

### Reprocessing Safety

The reprocessing system is conservative by design:
- Default `clear=True` removes old phase data before re-running (prevents stale data accumulation)
- `clear=False` is power-user mode: assumes the caller knows what they're doing
- `validate_reprocess()` prevents invalid operations (e.g., re-enriching when no matches exist)
- Database transactions are used; partial failures roll back cleanly

### Export Path Conflicts

When re-exporting Phase 4 with `clear=False`, existing output files are overwritten if Phase 3 computed the same output path. This is intentional: re-export should produce the latest version of each file.

### Phase 2 Lane Filtering

Phase 2 (matching) always operates on all asset types. Lane filtering is not applied to Phase 2 because matching uses the full set of JSON metadata across all asset types to find best matches. Filtering Phase 2 by lane would break cross-asset-type matching (e.g., a memory_main and its associated memory_overlay are matched together).
