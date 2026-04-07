# Snatched v3.0 — Architecture & Requirements Plan

> **Version:** 3.0 (Planning Draft)  
> **Date:** 2026-02-23  
> **Authors:** Dave + Cascade  
> **Status:** PRE-DEVELOPMENT — Non-destructive. v2.0 remains the running system.

---

## Table of Contents

- [1. Vision](#1-vision)
- [2. V2 Codebase Audit](#2-v2-codebase-audit)
  - [2.1 File Inventory](#21-file-inventory)
  - [2.2 Function Map — snatched.py](#22-function-map--snatchedpy)
  - [2.3 Function Map — chat_renderer.py](#23-function-map--chat_rendererpy)
  - [2.4 SQLite Schema (12 Tables)](#24-sqlite-schema-12-tables)
  - [2.5 What Works Well (Keep)](#25-what-works-well-keep)
  - [2.6 What's Broken or Missing](#26-whats-broken-or-missing)
- [3. V3 Architecture](#3-v3-architecture)
  - [3.1 Module Decomposition](#31-module-decomposition)
  - [3.2 Three-Lane Export System](#32-three-lane-export-system)
  - [3.3 Reprocessing Engine](#33-reprocessing-engine)
  - [3.4 XMP Sidecar System](#34-xmp-sidecar-system)
  - [3.5 Web-Based GUI](#35-web-based-gui)
  - [3.6 Configuration System](#36-configuration-system)
- [4. Module Specifications](#4-module-specifications)
  - [4.1 snatched.py — Entry Point](#41-snatchedpy--entry-point)
  - [4.2 config.py — Configuration](#42-configpy--configuration)
  - [4.3 db.py — Database Layer](#43-dbpy--database-layer)
  - [4.4 schema.sql — Schema Definition](#44-schemasql--schema-definition)
  - [4.5 ingest.py — Phase 1: Ingest](#45-ingestpy--phase-1-ingest)
  - [4.6 match.py — Phase 2: Match](#46-matchpy--phase-2-match)
  - [4.7 enrich.py — Phase 3: Enrich](#47-enrichpy--phase-3-enrich)
  - [4.8 export.py — Phase 4: Export](#48-exportpy--phase-4-export)
  - [4.9 lanes.py — Three-Lane Controller](#49-lanespy--three-lane-controller)
  - [4.10 xmp.py — XMP Sidecar Engine](#410-xmppy--xmp-sidecar-engine)
  - [4.11 reprocess.py — Reprocessing Engine](#411-reprocesspy--reprocessing-engine)
  - [4.12 wizard.py — Guided Mode / CLI Wizard](#412-wizardpy--guided-mode--cli-wizard)
  - [4.13 report.py — Reporting & Banner](#413-reportpy--reporting--banner)
  - [4.14 chat_renderer.py — Chat PNG Engine](#414-chat_rendererpy--chat-png-engine)
  - [4.15 web/ — Web GUI Package](#415-web--web-gui-package)
  - [4.16 utils.py — Shared Utilities](#416-utilspy--shared-utilities)
- [5. Requirements](#5-requirements)
  - [5.1 Functional Requirements](#51-functional-requirements)
  - [5.2 Non-Functional Requirements](#52-non-functional-requirements)
  - [5.3 Dependencies](#53-dependencies)
- [6. Migration Strategy](#6-migration-strategy)
- [7. Implementation Order](#7-implementation-order)
- [8. Open Questions](#8-open-questions)

---

## 1. Vision

Snatched v3.0 is a **full modular rewrite** of the Snapchat data export processor. The 4,814-line monolith is decomposed into focused modules, each handling one responsibility.

**New Features:**
- **Reprocessing** — Re-run any phase without re-extracting ZIPs or re-ingesting raw data
- **XMP Sidecars** — Generate `.xmp` sidecar files alongside (or instead of) embedded EXIF
- **Web GUI** — Browser-based dashboard for monitoring, reviewing matches, and triggering runs
- **Three Export Lanes** — Memories, Stories, and Chats operate as independent pipelines sharing the same database

The monoblock personality, terminal art, and guided wizard are preserved. The SQLite-first architecture is non-negotiable.

---

## 2. V2 Codebase Audit

### 2.1 File Inventory

| File | Lines | Size | Role |
|------|-------|------|------|
| `snatched.py` | 4,814 | 180 KB | Main pipeline — all 4 phases, wizard, CLI, reporting, banner |
| `chat_renderer.py` | 1,101 | 39 KB | Pillow-based chat PNG rendering engine |
| `snapfix.py` | 1,871 | 72 KB | v1 pipeline — archived, not used |
| `README.md` | 413 | 14 KB | Documentation |
| `DEV_TRACKER.md` | 160 | 7 KB | Development log and refactor roadmap |
| `BUGS.md` | 155 | 8 KB | Bug tracker and Snapchat quirks |
| `SNAPCHAT-EXPORT.md` | ~1,200 | 46 KB | Anatomy of Snapchat's 22 JSON files |

### 2.2 Function Map — snatched.py (Every Function by Section)

#### Constants & Globals (Lines 1–65)

| Symbol | Line | Description | V3 Target |
|--------|------|-------------|-----------|
| `VERSION` | 41 | Version string "2.0" | `config.py` |
| `INPUT_BASE` | 42 | Hardcoded `/mnt/nas-pool/snapchat-input` | `config.py` |
| `OUTPUT_BASE` | 43 | Hardcoded `/mnt/nas-pool/snapchat-output` | `config.py` |
| `MEMORY_RE` | 45 | Regex for memory filenames | `utils.py` |
| `CHAT_FILE_RE` | 47 | Regex for chat filenames | `utils.py` |
| `LOCATION_RE` | 48 | Regex for GPS coordinates | `utils.py` |
| `VIDEO_EXTS` | 51 | Set of video extensions | `utils.py` |
| `GPS_WINDOW` | 52 | ±5 min GPS cross-reference window | `config.py` |
| `UUID_RE` | 53 | UUID validation regex | `utils.py` |
| `RIFF_MAGIC` / `FMP4_STYP` | 56-57 | Magic bytes for format detection | `utils.py` |
| `BATCH_SIZE` | 59 | SQLite batch insert size (500) | `config.py` |
| `UNSAFE_FILENAME_RE` | 62 | Filename sanitization regex | `utils.py` |
| `DAVE_USERNAME` | 64 | Hardcoded username | `config.py` |

#### Terminal Colors (Lines 67–83)

| Function | Line | Description | V3 Target |
|----------|------|-------------|-----------|
| `_colors()` | 69 | ANSI escape code dict | `utils.py` |

#### Utility Functions (Lines 86–265)

| Function | Line | Description | V3 Target |
|----------|------|-------------|-----------|
| `die(msg)` | 88 | Print error and exit | `utils.py` |
| `warn(msg)` | 94 | Print warning to stderr | `utils.py` |
| `is_video(path)` | 98 | Check if path has video extension | `utils.py` |
| `parse_snap_date(s)` | 102 | Parse Snapchat date string → datetime | `utils.py` |
| `parse_snap_date_iso(s)` | 113 | Snapchat date → ISO 8601 | `utils.py` |
| `parse_snap_date_dateonly(s)` | 120 | Snapchat date → YYYY-MM-DD | `utils.py` |
| `parse_location(s)` | 129 | GPS coordinate string → (lat, lon) | `utils.py` |
| `extract_mid(url)` | 142 | Extract `mid=` param from URL | `utils.py` |
| `detect_real_format(path)` | 152 | Magic byte format mismatch detection | `utils.py` |
| `is_fragmented_mp4(path)` | 167 | fMP4 container detection | `utils.py` |
| `sha256_file(path)` | 177 | SHA-256 hex digest | `utils.py` |
| `sanitize_filename(name)` | 189 | Filesystem-safe string | `utils.py` |
| `parse_iso_dt(s)` | 202 | ISO 8601 → datetime | `utils.py` |
| `exif_dt(dt)` | 214 | Format datetime for EXIF | `utils.py` |
| `gps_tags(lat, lon, ...)` | 219 | Build GPS EXIF tag dict | `xmp.py` |
| `date_tags(dt, ...)` | 239 | Build date EXIF tag dict | `xmp.py` |
| `_format_chat_date(s)` | 263 | Strip " UTC" from date string | `utils.py` |

#### Schema (Lines 270–498)

| Symbol | Line | Description | V3 Target |
|--------|------|-------------|-----------|
| `SCHEMA_SQL` | 272 | Full DDL for 12 tables + indexes | `schema.sql` |
| `create_schema(db)` | 474 | Execute schema, verify tables | `db.py` |

#### Phase 1: Ingest (Lines 501–1247)

| Function | Line | Description | V3 Target |
|----------|------|-------------|-----------|
| `ingest_memories(db, json_dir)` | 503 | Parse `memories_history.json` → `memories` | `ingest.py` |
| `ingest_chat(db, json_dir)` | 562 | Parse `chat_history.json` → `chat_messages` + `chat_media_ids` | `ingest.py` |
| `ingest_snaps(db, json_dir)` | 662 | Parse `snap_history.json` → `snap_messages` | `ingest.py` |
| `ingest_stories(db, json_dir)` | 738 | Parse `shared_story.json` → `stories` | `ingest.py` |
| `ingest_friends(db, json_dir)` | 776 | Parse `friends.json` → `friends` (dedup by priority) | `ingest.py` |
| `ingest_locations(db, json_dir)` | 840 | Parse `location_history.json` → `locations` | `ingest.py` |
| `ingest_places(db, json_dir)` | 922 | Parse `snap_map_places.json` → `places` | `ingest.py` |
| `ingest_snap_pro(db, json_dir)` | 1004 | Parse `snap_pro.json` → `snap_pro` | `ingest.py` |
| `scan_assets(db, input_dir, ...)` | 1052 | Scan media dirs → `assets` | `ingest.py` |
| `phase1_ingest(db, input_dir, json_dir, args)` | 1200 | Phase 1 orchestrator | `ingest.py` |

#### Phase 2: Match (Lines 1249–1647)

| Function | Line | Description | V3 Target |
|----------|------|-------------|-----------|
| `_matched_asset_ids(db)` | 1251 | Set of already-matched asset IDs | `match.py` |
| `_strategy1_exact_media_id(db)` | 1257 | Chat file_id = message Media ID (conf 1.0) | `match.py` |
| `_strategy2_memory_uuid(db)` | 1277 | Memory UUID = `mid` URL param (conf 1.0) | `match.py` |
| `_strategy3_story_id(db)` | 1299 | Story ordered pairing by type (conf 0.9/0.5) | `match.py` |
| `_strategy4_timestamp_type(db)` | 1353 | Unique date+type match (conf 0.8) | `match.py` |
| `_strategy5_date_type_count(db)` | 1391 | Date+type+count ordered pairing (conf 0.7) | `match.py` |
| `_strategy6_date_only(db)` | 1443 | Date-only fallback (conf 0.3) | `match.py` |
| `_match_overlay_and_media_zips(db)` | 1462 | Handle `overlay~zip` patterns | `match.py` |
| `_set_best_matches(db)` | 1517 | Set `is_best=1` per asset | `match.py` |
| `phase2_match(db)` | 1558 | Phase 2 orchestrator | `match.py` |

#### Phase 3: Enrich (Lines 1650–2288)

| Function | Line | Description | V3 Target |
|----------|------|-------------|-----------|
| `_load_location_timeline(db)` | 1652 | Load GPS breadcrumbs for binary search | `enrich.py` |
| `_find_nearest_location(...)` | 1667 | Binary search for nearest GPS within window | `enrich.py` |
| `enrich_gps(db, ...)` | 1686 | GPS from metadata + location history | `enrich.py` |
| `_resolve_conversation_name(...)` | 1769 | Human-readable conversation name fallback | `enrich.py` |
| `_build_chat_folder_map(db)` | 1794 | Map conversation_id → folder name | `enrich.py` |
| `enrich_display_names(db)` | 1918 | Resolve display names from friends | `enrich.py` |
| `enrich_output_paths(db)` | 1997 | Compute output_subdir + output_filename | `enrich.py` |
| `enrich_exif_tags(db)` | 2116 | Build exif_tags_json for best matches | `enrich.py` |
| `phase3_enrich(db, project_dir)` | 2236 | Phase 3 orchestrator | `enrich.py` |

#### Phase 4: Export (Lines 2291–3457)

| Function | Line | Description | V3 Target |
|----------|------|-------------|-----------|
| `_copy_files(db, project_dir, args)` | 2293 | Copy/remux files to output paths | `export.py` |
| `_write_exif(db, project_dir, args)` | 2448 | Embed EXIF via exiftool batch | `export.py` |
| `_burn_overlays(db, project_dir, args)` | 2592 | Composite overlay PNGs onto main files | `export.py` |
| `_export_text(db, project_dir, args)` | 2710 | Export chat transcripts + PNG renders | `export.py` |
| `_write_reports(db, project_dir, args, stats)` | 3007 | Write report.txt + report.json | `report.py` |
| `phase4_export(db, project_dir, args)` | 3370 | Phase 4 orchestrator | `export.py` |

#### CLI & Discovery (Lines 3460–3773)

| Function | Line | Description | V3 Target |
|----------|------|-------------|-----------|
| `parse_args(argv)` | 3462 | argparse CLI argument parser | `snatched.py` |
| `extract_zips(input_path, scratch_dir, ...)` | 3534 | ZIP extraction with path-traversal protection | `ingest.py` |
| `discover_export(base_dir)` | 3590 | Find export structure in directory tree | `ingest.py` |
| `list_exports(root)` | 3695 | Scan input dir for exports (dirs + ZIPs) | `ingest.py` |

#### Guided Mode & Banner (Lines 3776–4404)

| Function | Line | Description | V3 Target |
|----------|------|-------------|-----------|
| `guided_mode()` | 3778 | Interactive 6-step setup wizard | `wizard.py` |
| `print_banner(db, elapsed, project_dir, ...)` | 4140 | Final results banner with accounting | `report.py` |

#### Subcommand Handlers (Lines 4407–4514)

| Function | Line | Description | V3 Target |
|----------|------|-------------|-----------|
| `handle_query(args)` | 4409 | `snatched query` — run SQL against DB | `snatched.py` |
| `handle_stats(args)` | 4448 | `snatched stats` — print summary from DB | `snatched.py` |
| `handle_chat(args)` | 4473 | `snatched chat` — re-render chat exports | `snatched.py` |

#### Main Entry (Lines 4516–4814)

| Function | Line | Description | V3 Target |
|----------|------|-------------|-----------|
| `progress(cur, total, t0, ...)` | 4521 | Progress bar with ETA | `utils.py` |
| `open_database(db_path)` | 4553 | Open/create SQLite DB, apply schema | `db.py` |
| `main()` | 4579 | CLI entry — dispatch, orchestrate all phases | `snatched.py` |

### 2.3 Function Map — chat_renderer.py

| Symbol | Line | Description | V3 Target |
|--------|------|-------------|-----------|
| `ChatMessage` | 34 | Single chat message dataclass | `chat_renderer.py` |
| `DateDivider` | 46 | Date separator element | `chat_renderer.py` |
| `Page` | 52 | Rendered page container | `chat_renderer.py` |
| Layout constants | 63-98 | Canvas dimensions, spacing, padding | `chat_renderer.py` |
| `COLORS_LIGHT` / `COLORS_DARK` | 101-131 | Theme color palettes | `chat_renderer.py` |
| `_find_font_path()` | 166 | Find first existing font file | `chat_renderer.py` |
| `_resolve_fonts()` | 174 | Resolve + cache font paths | `chat_renderer.py` |
| `get_font(size, bold)` | 183 | Load font with caching | `chat_renderer.py` |
| `ChatRenderer` class | ~205+ | Full rendering engine | `chat_renderer.py` |

### 2.4 SQLite Schema (12 Tables)

| Table | Purpose |
|-------|---------|
| `assets` | Every media file on disk (path, hash, type, format) |
| `memories` | Parsed from `memories_history.json` |
| `chat_messages` | Parsed from `chat_history.json` |
| `chat_media_ids` | Exploded pipe-separated media IDs |
| `snap_messages` | Parsed from `snap_history.json` (deduped) |
| `stories` | Parsed from `shared_story.json` |
| `snap_pro` | Parsed from `snap_pro.json` |
| `friends` | Username → display name mapping |
| `locations` | GPS breadcrumbs from `location_history.json` |
| `places` | Snap Map places |
| `matches` | Join table: asset ↔ metadata with strategy + confidence |
| `run_log` | Execution audit trail |

### 2.5 What Works Well (Keep)

- **SQLite-first architecture** — queryable, auditable, resumable
- **6-strategy match cascade** with confidence scores
- **4-phase pipeline** (Ingest → Match → Enrich → Export)
- **Zero pip deps** for core pipeline (stdlib only)
- **Guided wizard** personality and terminal art
- **SHA-256 checksums** for integrity verification
- **exiftool stay_open batch mode** for EXIF embedding
- **Chat PNG rendering** with Snapchat-style layout
- **Format detection** (WebP-as-PNG, fMP4)
- **Overlay burning** (ImageMagick + ffmpeg)
- **Accounting system** in banner (everything adds up)

### 2.6 What's Broken or Missing

| Issue | Severity | Description |
|-------|----------|-------------|
| **Monolith** | High | 4,814 lines in one file — unmaintainable |
| **No reprocessing** | High | Must re-extract ZIPs and re-ingest to re-run |
| **No XMP sidecars** | Medium | Only embedded EXIF; no sidecar option |
| **No GUI** | Medium | CLI-only; no visual review |
| **Hardcoded paths** | Medium | `INPUT_BASE`, `OUTPUT_BASE`, `DAVE_USERNAME` |
| **No config file** | Medium | All settings via CLI flags or hardcoded |
| **No logging** | Medium | `print()` everywhere; no log levels |
| **No tests** | Medium | Zero test coverage |
| **Single export lane** | Medium | Memories, chats, stories all coupled |
| **No progress API** | Low | Progress is terminal-only; no structured events for GUI |

---

## 3. V3 Architecture

### 3.1 Module Decomposition

```
snatched/
├── snatched.py          # Entry point — CLI dispatch, subcommands
├── config.py            # Configuration: paths, constants, TOML/JSON config
├── db.py                # Database layer: open, migrate, schema, helpers
├── schema.sql           # Pure SQL schema definition
├── ingest.py            # Phase 1: Parse JSON + scan assets → SQLite
├── match.py             # Phase 2: 6-strategy match cascade
├── enrich.py            # Phase 3: GPS, names, paths, EXIF tag building
├── export.py            # Phase 4: Copy, EXIF embed, overlays, chat export
├── lanes.py             # Three-lane controller (memories/stories/chats)
├── xmp.py               # XMP sidecar generation + EXIF tag building
├── reprocess.py         # Reprocessing engine (re-run phases from existing DB)
├── wizard.py            # Guided mode interactive wizard
├── report.py            # Report generation + summary banner
├── chat_renderer.py     # Chat PNG rendering engine (Pillow)
├── utils.py             # Shared utilities: parsing, hashing, colors
├── web/                 # Web GUI package
│   ├── __init__.py
│   ├── server.py        # Flask/FastAPI web server
│   ├── api.py           # REST API endpoints
│   ├── static/          # CSS, JS, assets
│   └── templates/       # HTML templates (Jinja2)
└── tests/               # Test suite
```

### 3.2 Three-Lane Export System

Each lane operates **independently** but shares the same SQLite database.

```
                    ┌─────────────────────────────┐
                    │   SHARED CORE               │
                    │   ┌─────────┐ ┌──────────┐  │
                    │   │ Ingest  │ │  Match   │  │
                    │   └────┬────┘ └────┬─────┘  │
                    │        │           │         │
                    │   ┌────┴───────────┴─────┐  │
                    │   │      SQLite DB        │  │
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
| GPS enrichment | ✓ | ✗ | ✗ |
| Overlay burning | ✓ | ✗ | ✗ |
| Display name resolution | ✗ | ✓ | ✗ |
| Text transcript export | ✗ | ✓ | ✗ |
| PNG chat rendering | ✗ | ✓ | ✗ |
| EXIF embedding | ✓ | ✓ | ✓ |
| XMP sidecars | ✓ | ✓ | ✓ |
| Folder structure | `memories/{YYYY}/{MM}/` | `chat/{ConvName}/` | `stories/` |
| fMP4 remuxing | ✓ | ✓ | ✓ |

### 3.3 Reprocessing Engine

Re-run any phase without re-extracting ZIPs or re-ingesting raw data.

#### Reprocess Modes

| Mode | What It Does | Use Case |
|------|-------------|----------|
| `reprocess match` | Clear matches, re-run Phase 2 | Tweaked matching strategy |
| `reprocess enrich` | Re-run Phase 3 from existing matches | Changed GPS window |
| `reprocess export` | Re-run Phase 4 from existing enrichment | Changed output paths |
| `reprocess chat` | Re-render chat exports only | Changed theme or format |
| `reprocess xmp` | Regenerate XMP sidecars only | Changed XMP template |
| `reprocess lane <name>` | Re-run a specific lane | Lane config changed |
| `reprocess all` | Re-run Phases 2-4 | Full re-process |

#### CLI

```bash
snatched reprocess /mnt/nas-pool/snapchat-output/dave --phases match,enrich,export
snatched reprocess /mnt/nas-pool/snapchat-output/dave --chat-only --dark-mode
snatched reprocess /mnt/nas-pool/snapchat-output/dave --xmp-only
snatched reprocess /mnt/nas-pool/snapchat-output/dave --lane memories
```

### 3.4 XMP Sidecar System

XMP sidecars are `.xmp` files placed alongside each exported media file.

#### Why XMP Sidecars?

- **Non-destructive** — original file bytes never modified
- **Immich/Lightroom/darktable** — all support sidecar import
- **Auditable** — XML is human-readable
- **Reversible** — delete `.xmp` and original is untouched
- **Complementary** — can be used alongside embedded EXIF

#### Sidecar Format

```xml
<?xml version="1.0" encoding="UTF-8"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:Description
      xmlns:dc="http://purl.org/dc/elements/1.1/"
      xmlns:xmp="http://ns.adobe.com/xap/1.0/"
      xmlns:exif="http://ns.adobe.com/exif/1.0/"
      xmlns:tiff="http://ns.adobe.com/tiff/1.0/"
      xmlns:photoshop="http://ns.adobe.com/photoshop/1.0/"
      xmlns:snatched="http://snatched.local/ns/1.0/"
      xmp:CreateDate="2024-07-15T14:32:00+00:00"
      xmp:ModifyDate="2024-07-15T14:32:00+00:00"
      exif:DateTimeOriginal="2024-07-15T14:32:00+00:00"
      exif:GPSLatitude="39.501"
      exif:GPSLongitude="-89.766"
      tiff:Software="Snatched v3.0"
      photoshop:Credit="Shannon (@savannacloyd)"
      dc:description="Received"
      dc:subject="Shannon - savannacloyd 2023-2025"
      snatched:MatchStrategy="exact_media_id"
      snatched:MatchConfidence="1.0"
      snatched:SourceSHA256="a1b2c3d4..."
      snatched:AssetType="chat"
    />
  </rdf:RDF>
</x:xmpmeta>
```

#### Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `xmp_enabled` | `false` | Generate XMP sidecars |
| `xmp_alongside_exif` | `true` | Generate sidecars even when EXIF embedded |
| `xmp_only` | `false` | Generate sidecars instead of embedding EXIF |
| `xmp_include_snatched_ns` | `true` | Include Snatched-specific metadata |
| `xmp_template` | `default` | XMP template name |

#### Expanded Snap Metadata Tag Set (v3+)

Snatched v3 should emit an "extended" sidecar profile so we capture as much Snapchat context as possible now, while staying compatible with tools that only read standard namespaces.

| Category | Example XMP Tags | Source |
|----------|------------------|--------|
| Core capture | `xmp:CreateDate`, `exif:DateTimeOriginal`, `exif:GPSLatitude`, `exif:GPSLongitude` | memories/chat timestamps + location history |
| Identity | `dc:creator`, `photoshop:Credit`, `snatched:FromUser`, `snatched:ToUser`, `snatched:ConversationId` | chat/snap metadata |
| Match provenance | `snatched:MatchStrategy`, `snatched:MatchConfidence`, `snatched:SourceSHA256`, `snatched:RunId` | match + run_log tables |
| Collection/Album | `snatched:CollectionName`, `snatched:CollectionId`, `snatched:CollectionType`, `snatched:CollectionOrder` | stories/shared_story + future album-like groupings |
| Message context | `snatched:MessageType`, `snatched:MediaKind`, `snatched:IsReply`, `snatched:ThreadHint` | chat_messages + snap_messages |
| Location context | `Iptc4xmpCore:Location`, `photoshop:City`, `photoshop:State`, `Iptc4xmpExt:LocationShown` | places + reverse lookup |
| Export lineage | `snatched:Lane`, `snatched:ExportProfile`, `snatched:SidecarProfileVersion` | lane controller + config |

#### Namespace and Forward-Compatibility Rules

- Use **standard namespaces first** (`dc`, `xmp`, `exif`, `tiff`, `photoshop`, IPTC) when a field maps cleanly.
- Put Snapchat-specific and experimental fields under `snatched:*` namespace.
- Persist unknown Snapchat keys as `snatched:Raw_<field_name>` (sanitized) instead of dropping them.
- Include `snatched:SidecarProfileVersion` (start at `1`) so future parsers can migrate safely.
- Include optional `snatched:SchemaHints` JSON blob (string field) for emerging metadata not yet standardized.

### 3.5 Web-Based GUI

Technology stack: Flask + Jinja2 + Vanilla JS (no build step, keeps zero-dep spirit).

#### Pages

| Page | URL | Description |
|------|-----|-------------|
| Dashboard | `/` | Overview: run history, asset counts, match rates |
| Assets | `/assets` | Browsable asset list with filters |
| Matches | `/matches` | Match review with strategy + confidence |
| Conversations | `/conversations` | Chat conversation list |
| Conversation Detail | `/conversations/<id>` | Single conversation with messages |
| Memories | `/memories` | Memory browser by year/month with thumbnails |
| Map | `/map` | GPS-tagged memories on Leaflet.js map |
| Reports | `/reports` | View report.txt and report.json |
| Reprocess | `/reprocess` | Trigger reprocessing with selection |
| Logs | `/logs` | Live pipeline output (SSE stream) |

#### API Endpoints (JSON)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/summary` | GET | Pipeline metrics + status |
| `/api/assets` | GET | Paginated asset list with filters |
| `/api/matches` | GET | Match list with confidence and strategy |
| `/api/matches/<id>` | GET | Match detail |
| `/api/conversations` | GET | Conversation index |
| `/api/conversations/<id>` | GET | Conversation with messages |
| `/api/memories` | GET | Memory list |
| `/api/map/points` | GET | GPS points for map rendering |
| `/api/reprocess` | POST | Trigger reprocessing |
| `/api/logs/stream` | GET (SSE) | Live event stream |

#### Launch

```bash
snatched web /mnt/nas-pool/snapchat-output/dave --port 8080
snatched web . --port 8080
```

### 3.6 Configuration System

#### Config File: `snatched.toml`

```toml
[paths]
input_base = "/mnt/nas-pool/snapchat-input"
output_base = "/mnt/nas-pool/snapchat-output"

[pipeline]
batch_size = 500
gps_window_seconds = 300
scan_siblings = false

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

[web]
port = 8080
host = "127.0.0.1"
```

#### Config Precedence (highest → lowest)

1. CLI flags (`--no-exif`, `--dark-mode`, etc.)
2. Environment variables (`SNATCHED_INPUT_BASE`, etc.)
3. Project config file (`<project>/.snatched/snatched.toml`)
4. User config file (`~/.config/snatched/snatched.toml`)
5. Built-in defaults

---

## 4. Module Specifications

### 4.1 snatched.py — Entry Point

**Functions:**
- `parse_args(argv)` — argparse with subcommands: `run`, `query`, `stats`, `chat`, `reprocess`, `web`
- `handle_run(args)` — main pipeline orchestration (Phases 1-4)
- `handle_query(args)` — SQL query against existing DB
- `handle_stats(args)` — print summary from existing DB
- `handle_chat(args)` — re-render chat exports
- `handle_reprocess(args)` — delegate to `reprocess.py`
- `handle_web(args)` — launch web GUI
- `main()` — entry point

**Size estimate:** ~200 lines

### 4.2 config.py — Configuration

**Functions:**
- `load_config(project_dir, cli_args)` — load + merge config from all sources
- `get_default_config()` — built-in defaults dict
- `Config` class — typed access to all settings

**Migrated from v2:** Lines 41-64 (constants), hardcoded paths, `BATCH_SIZE`, `GPS_WINDOW`, `DAVE_USERNAME`

**Size estimate:** ~150 lines

### 4.3 db.py — Database Layer

**Functions:**
- `open_database(db_path)` — open SQLite, apply schema, run migrations
- `create_schema(db)` — execute `schema.sql`, verify tables
- `migrate(db)` — apply pending migrations (ALTER TABLE)
- `log_run(db, version, person, input_path, flags)` — insert into `run_log`
- `update_run(db, run_id, **kwargs)` — update `run_log` entry
- `batch_insert(db, table, columns, rows)` — batched `executemany` helper
- `batch_update(db, sql, rows)` — batched update helper

**Migrated from v2:** Lines 474-498, 4553-4575

**Size estimate:** ~200 lines

### 4.4 schema.sql — Schema Definition

**Contents:** 12 `CREATE TABLE` statements, all indexes, pragma settings.

**V3 additions:**
- `lane` column on `matches` table
- `xmp_written` and `xmp_path` columns on `assets`
- `reprocess_log` table (tracks reprocessing runs)
- `lane_config` table (per-lane settings snapshot)

**Migrated from v2:** Lines 272-471

**Size estimate:** ~120 lines SQL

### 4.5 ingest.py — Phase 1: Ingest

**Functions:**
- `phase1_ingest(db, input_dir, json_dir, config)` — orchestrator
- `ingest_memories(db, json_dir)` — `memories_history.json` → `memories`
- `ingest_chat(db, json_dir)` — `chat_history.json` → tables
- `ingest_snaps(db, json_dir)` — `snap_history.json` → `snap_messages`
- `ingest_stories(db, json_dir)` — `shared_story.json` → `stories`
- `ingest_friends(db, json_dir)` — `friends.json` → `friends`
- `ingest_locations(db, json_dir)` — `location_history.json` → `locations`
- `ingest_places(db, json_dir)` — `snap_map_places.json` → `places`
- `ingest_snap_pro(db, json_dir)` — `snap_pro.json` → `snap_pro`
- `scan_assets(db, input_dir, config)` — scan media dirs → `assets`
- `extract_zips(input_path, scratch_dir, source_filter)` — ZIP extraction
- `discover_export(base_dir)` — find export structure
- `list_exports(root)` — scan for available exports

**Migrated from v2:** Lines 501-1247, 3534-3773

**Size estimate:** ~800 lines

### 4.6 match.py — Phase 2: Match

**Functions:**
- `phase2_match(db)` — orchestrator
- `strategy1_exact_media_id(db)` — confidence 1.0
- `strategy2_memory_uuid(db)` — confidence 1.0
- `strategy3_story_id(db)` — confidence 0.9/0.5
- `strategy4_timestamp_type(db)` — confidence 0.8
- `strategy5_date_type_count(db)` — confidence 0.7
- `strategy6_date_only(db)` — confidence 0.3
- `match_overlay_and_media_zips(db)` — `overlay~zip` patterns
- `set_best_matches(db)` — set `is_best=1` per asset
- `matched_asset_ids(db)` — helper: set of matched IDs

**Migrated from v2:** Lines 1249-1647

**Size estimate:** ~400 lines

### 4.7 enrich.py — Phase 3: Enrich

**Functions:**
- `phase3_enrich(db, project_dir, config)` — orchestrator
- `load_location_timeline(db)` — load GPS breadcrumbs
- `find_nearest_location(target_unix, timestamps, lats, lons)` — binary search
- `enrich_gps(db, timestamps, lats, lons)` — GPS from metadata + location history
- `enrich_display_names(db)` — resolve from friends table
- `enrich_output_paths(db, config)` — compute subdir + filename (lane-aware)
- `enrich_exif_tags(db, config)` — build `exif_tags_json`
- `resolve_conversation_name(conv_title, conv_id, friends, from_user)` — name fallback chain
- `build_chat_folder_map(db)` — conversation_id → folder name

**Migrated from v2:** Lines 1650-2288

**Size estimate:** ~650 lines

### 4.8 export.py — Phase 4: Export

**Functions:**
- `phase4_export(db, project_dir, config, lanes)` — orchestrator
- `copy_files(db, project_dir, config)` — copy/remux to output paths
- `write_exif(db, project_dir, config)` — exiftool stay_open batch
- `burn_overlays(db, project_dir, config)` — ImageMagick/ffmpeg compositing
- `export_chat_text(db, project_dir, config)` — text transcripts
- `export_chat_png(db, project_dir, config)` — PNG rendering

**Migrated from v2:** Lines 2291-3457

**Size estimate:** ~700 lines

### 4.9 lanes.py — Three-Lane Controller

**Classes:**
- `LaneController` — manages lane configs and execution
  - `get_lane(name)` — return lane config
  - `enabled_lanes()` — list enabled lane names
  - `run_lane(name, db, project_dir)` — execute single lane
  - `run_all(db, project_dir)` — execute all enabled lanes
- `MemoriesLane` — memories-specific enrichment + export
- `ChatsLane` — chats-specific enrichment + export
- `StoriesLane` — stories-specific enrichment + export

**New in v3.**

**Size estimate:** ~300 lines

### 4.10 xmp.py — XMP Sidecar Engine

**Functions:**
- `generate_xmp_sidecar(match_row, config)` — generate `.xmp` XML string
- `write_xmp_sidecars(db, project_dir, config)` — batch write all sidecars
- `gps_tags(lat, lon, vid, dt)` — build GPS EXIF tag dict
- `date_tags(dt, vid, subsec_ms)` — build date EXIF tag dict
- `build_xmp_xml(tags, snatched_meta)` — render XML from tag dict
- `map_snap_fields_to_xmp(row, profile)` — normalize Snap data into standard + `snatched:*` namespaces
- `emit_collection_tags(row)` — produce album/collection-oriented metadata fields
- `preserve_unknown_fields(raw_obj)` — preserve unmapped keys as `snatched:Raw_*`
- `XMP_TEMPLATE` — XML template string
- `XMP_PROFILE_VERSION` — integer profile version for compatibility

**Migrated from v2:** Lines 219, 239, 214

**Size estimate:** ~250 lines

### 4.11 reprocess.py — Reprocessing Engine

**Functions:**
- `reprocess(db, project_dir, config, phases, lanes)` — main entry
- `reprocess_match(db)` — clear matches, re-run Phase 2
- `reprocess_enrich(db, project_dir, config)` — re-run Phase 3
- `reprocess_export(db, project_dir, config, lanes)` — re-run Phase 4
- `reprocess_chat(db, project_dir, config)` — re-render chat exports
- `reprocess_xmp(db, project_dir, config)` — regenerate XMP sidecars
- `reprocess_lane(db, project_dir, config, lane_name)` — re-run single lane
- `validate_reprocess(db)` — check DB has required data

**New in v3.**

**Size estimate:** ~200 lines

### 4.12 wizard.py — Guided Mode / CLI Wizard

**Functions:**
- `guided_mode(config)` — the full 6+ step wizard
- `step(num, total, title)` — step header display
- `opt(n, text, detail)` — option display
- `prompt(label)` — input prompt

**V3 additions:**
- Step for lane configuration
- Step for XMP sidecar toggle
- Step for reprocessing mode selection
- Step for sibling scan toggle (`scan_siblings`)

**Migrated from v2:** Lines 3776-4135

**Size estimate:** ~400 lines

### 4.13 report.py — Reporting & Banner

**Functions:**
- `write_reports(db, project_dir, config, phase_stats)` — generate report.txt + report.json
- `print_banner(db, elapsed, project_dir, config)` — terminal summary
- `query_report_stats(db)` — gather stats for reporting

**Migrated from v2:** Lines 3007-3367, 4140-4404

**Size estimate:** ~500 lines

### 4.14 chat_renderer.py — Chat PNG Engine

**Changes for v3:**
- Accept a `config` object instead of hardcoded constants
- Expose canvas dimensions as configurable
- Add progress callback for GUI integration

**Migrated from v2:** Entire file (1,101 lines)

**Size estimate:** ~1,100 lines (mostly unchanged)

### 4.15 web/ — Web GUI Package

**Files:**
- `web/__init__.py` — package init
- `web/server.py` — Flask app, route registration, static file serving
- `web/api.py` — REST API endpoints (JSON responses)
- `web/templates/` — Jinja2 HTML templates
- `web/static/` — CSS, JS, favicon

**New in v3.**

**Size estimate:** ~800 lines (Python) + ~500 lines (HTML/CSS/JS)

### 4.16 utils.py — Shared Utilities

**Functions:**
- `die(msg)`, `warn(msg)` — error handling
- `colors()` — ANSI escape codes
- `is_video(path)` — video extension check
- `parse_snap_date(s)`, `parse_snap_date_iso(s)`, `parse_snap_date_dateonly(s)` — date parsing
- `parse_iso_dt(s)` — ISO datetime parsing
- `parse_location(s)` — GPS coordinate parsing
- `extract_mid(url)` — extract `mid=` from URL
- `detect_real_format(path)` — magic byte detection
- `is_fragmented_mp4(path)` — fMP4 detection
- `sha256_file(path)` — SHA-256 digest
- `sanitize_filename(name)` — filesystem-safe names
- `format_chat_date(s)` — strip " UTC"
- `exif_dt(dt)` — format datetime for EXIF
- `progress(cur, total, t0, prefix, item_name)` — progress bar with ETA

**Constants:** `MEMORY_RE`, `CHAT_FILE_RE`, `LOCATION_RE`, `UUID_RE`, `UNSAFE_FILENAME_RE`, `VIDEO_EXTS`, `RIFF_MAGIC`, `FMP4_STYP`

**Migrated from v2:** Lines 45-200, 263-268, 4521-4548

**Size estimate:** ~300 lines

---

## 5. Requirements

### 5.1 Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01 | Decompose monolith into ≥12 focused modules | Critical |
| FR-02 | Three independent export lanes (memories, chats, stories) | Critical |
| FR-03 | Reprocessing without re-extraction or re-ingestion | Critical |
| FR-04 | XMP sidecar generation for all exported files | High |
| FR-05 | Web-based GUI for monitoring and review | High |
| FR-06 | Configuration file support (TOML) | High |
| FR-07 | Preserve all v2 matching strategies (6-level cascade) | Critical |
| FR-08 | Preserve all v2 EXIF embedding behavior | Critical |
| FR-09 | Preserve guided wizard personality and terminal art | High |
| FR-10 | Preserve SQLite-first architecture | Critical |
| FR-11 | Preserve SHA-256 checksums and audit trail | Critical |
| FR-12 | Preserve overlay burning (ImageMagick + ffmpeg) | High |
| FR-13 | Preserve chat PNG rendering (Pillow) | High |
| FR-14 | Preserve format detection (WebP-as-PNG, fMP4) | High |
| FR-15 | Preserve resume support (`--resume`) | High |
| FR-16 | Preserve dry run mode (`--dry-run`) | High |
| FR-17 | Preserve test modes (`--test N`, `--test-video N`) | Medium |
| FR-18 | Preserve query/stats subcommands | High |
| FR-19 | `snatched reprocess` subcommand with phase/lane selection | Critical |
| FR-20 | `snatched web` subcommand to launch GUI | High |
| FR-21 | Per-lane enable/disable and configuration | High |
| FR-22 | XMP sidecars alongside or instead of embedded EXIF | High |
| FR-23 | Map view of GPS-tagged memories in web GUI | Medium |
| FR-24 | Match review interface in web GUI | Medium |
| FR-25 | Progress events for GUI integration | Medium |
| FR-26 | Configurable output folder patterns per lane | Medium |
| FR-27 | Proper Python logging (replace all `print()`) | Medium |
| FR-28 | Type hints on all public functions | Low |
| FR-29 | Unit tests for matching strategies | Medium |
| FR-30 | Unit tests for ingest parsers | Medium |
| FR-31 | Emit extended Snap metadata in XMP (collections/albums, lineage, context) | High |
| FR-32 | Preserve unknown Snapchat keys in `snatched:Raw_*` tags for future compatibility | High |
| FR-33 | Version sidecar schema with `snatched:SidecarProfileVersion` | High |

### 5.2 Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-01 | Zero pip dependencies for core pipeline |
| NFR-02 | Python 3.8+ compatibility |
| NFR-03 | Process 5,000+ assets in under 10 minutes |
| NFR-04 | Database file under 5 MB for typical exports |
| NFR-05 | Web GUI loads in under 2 seconds |
| NFR-06 | No data loss during reprocessing |
| NFR-07 | Backward-compatible with v2 databases |
| NFR-08 | All file deletions use `trash-put` |
| NFR-09 | XMP sidecars remain parseable by standard DAM tools even with custom tags |

### 5.3 Dependencies

#### Core Pipeline (stdlib only)

- Python 3.8+, sqlite3, json, pathlib, argparse, hashlib, subprocess, re, zipfile
- tomllib (3.11+) or tomli backport for 3.8-3.10

#### Optional Dependencies

| Package | Required For |
|---------|--------------|
| exiftool | `--exif` (default on) |
| ImageMagick | `--burn-overlays` |
| ffmpeg | Video overlay + fMP4 remux |
| Pillow | Chat screenshots |
| Flask | `snatched web` |

---

## 6. Migration Strategy

V3 development is **non-destructive** to the running v2 system.

### Phase 1: Parallel Development
1. Create `snatched3/` directory alongside existing files
2. Build modules one at a time, testing against v2's database output
3. v2 continues running in production

### Phase 2: Validation
1. Run v3 against same input data as v2
2. Compare: match counts, GPS counts, EXIF tags, output file hashes
3. Diff `report.json` between v2 and v3 runs
4. Zero regression = green light

### Phase 3: Cutover
1. Rename `snatched.py` → `snatched_v2.py` (archived)
2. `snatched3/` becomes new `snatched/` package
3. Entry point: `python -m snatched` or `python snatched/snatched.py`

### Database Migration

V3 databases are backward-compatible with v2. New columns/tables added via `ALTER TABLE` migrations.

**New columns:**
- `assets.xmp_written` (BOOLEAN DEFAULT 0)
- `assets.xmp_path` (TEXT)
- `matches.lane` (TEXT: 'memories', 'chats', 'stories')

**New tables:**
- `reprocess_log` — tracks reprocessing runs
- `lane_config` — per-lane settings snapshot

---

## 7. Implementation Order

| Step | Module | Estimated Lines |
|------|--------|-----------------|
| 1 | `utils.py` | 300 |
| 2 | `config.py` | 150 |
| 3 | `schema.sql` | 120 |
| 4 | `db.py` | 200 |
| 5 | `ingest.py` | 800 |
| 6 | `match.py` | 400 |
| 7 | `enrich.py` | 650 |
| 8 | `xmp.py` | 250 |
| 9 | `export.py` | 700 |
| 10 | `lanes.py` | 300 |
| 11 | `report.py` | 500 |
| 12 | `reprocess.py` | 200 |
| 13 | `wizard.py` | 400 |
| 14 | `snatched.py` (entry) | 200 |
| 15 | `chat_renderer.py` | 1,100 |
| 16 | `web/` | 1,300 |
| 17 | `tests/` | 800 |
| | **TOTAL** | **~8,370** |

---

## 8. Open Questions

| # | Question | Leaning |
|---|----------|---------|
| 1 | Web GUI as separate pip package or bundled? | Bundled |
| 2 | Require `tomllib` (3.11+) or support `tomli` backport? | Support backport |
| 3 | XMP sidecars: Adobe namespace or custom `snatched:` namespace? | Both |
| 4 | GUI: read-only or allow editing matches? | Read-only for v3.0 |
| 5 | Lanes: shared output dir or each get their own root? | Shared, lane = subdir |
| 6 | Reprocessing: preserve old output or overwrite? | Overwrite with backup |
| 7 | Progress system for GUI: SSE/WebSocket/polling? | SSE |
| 8 | v3: process multiple people in one run? | No, keep single-person |

---

*This document is the blueprint. The baby is gone, the blow is out, we're stabbing GPL-1s, and it's time for our mommy job.*
