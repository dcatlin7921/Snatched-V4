# Snatched v3 Online

**They took your memories. We take them back.**

Snatched is a web-based Snapchat data export processor. Upload your Snapchat export ZIP and get back organized photos, chats, and stories with dates, GPS locations, and friend names automatically restored via EXIF metadata embedding.

---

## Status

**Deployed** on Dave's server at `snatched.local` (LAN) / `172.20.1.30:8000`.

- Container: `snatched` (FastAPI + uvicorn, 4 workers)
- Database: PostgreSQL 16 on `memory-store` (172.20.6.10)
- Networks: `dashboard-net` (172.20.1.30) + `memory-net` (172.20.6.21)
- Auth: Authelia header delegation (via Traefik reverse proxy)
- UI: Rebellion theme (snap-yellow on deep-black, Pico CSS + htmx)

---

## How It Works

1. **Upload** your Snapchat data export ZIP (up to 5 GB)
2. **Ingest** parses 8 JSON metadata files and scans all media assets
3. **Match** runs a 6-strategy cascade to pair media with metadata (100%--30% confidence)
4. **Enrich** cross-references GPS breadcrumbs, resolves friend names, builds EXIF tags
5. **Export** copies files, embeds EXIF, burns overlays, renders chat PNGs, generates reports
6. **Download** your organized archive with full metadata intact

---

## Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.12, FastAPI, uvicorn |
| Frontend | Jinja2 templates, htmx 2.x, Pico CSS v2 |
| Database | PostgreSQL 16 (app state) + per-user SQLite (processing) |
| Auth | Authelia header delegation via Traefik |
| Container | Docker (Alpine Linux), 2 GB RAM / 4 CPU |
| Config | TOML (`snatched.toml`) |

---

## Pipeline

```
ZIP Upload --> Ingest --> Match --> Enrich --> Export --> Download
               |          |         |          |
               v          v         v          v
            Parse JSON   6-strat   GPS xref   EXIF embed
            Scan media   cascade   Friends    Overlay burn
            SHA-256      Score     Paths      Chat PNGs
            Classify     Rank      Tags       XMP sidecars
```

### Match Strategies (in cascade order)
| # | Strategy | Confidence |
|---|----------|------------|
| 1 | exact_media_id | 100% |
| 2 | memory_uuid | 100% |
| 3 | memory_uuid_zip | 90% |
| 4 | story_id | 90% |
| 5 | timestamp_type | 80% |
| 6 | date_type_count | 70% |
| 7 | date_only | 30% |

### Export Lanes
- **Memories** -- Photos and videos with full EXIF metadata
- **Chats** -- Rendered conversation PNGs (Snapchat-style, 2880x5120px, 600 DPI) + text transcripts
- **Stories** -- Story media with metadata

---

## Project Structure

```
snatched-v3/
  README.md
  docs/
    pro-features-roadmap.md       # Premium feature roadmap (36 features)
    planning/                     # Architecture & requirements
      SNATCHED-V3-PLAN-v2.md       # Current architecture (post-debate)
      SNATCHED-V3-PLAN-v1-RESTORED.md  # Original plan (historical)
    design/                       # UI/UX design system
      ui-visual-identity.md         # Visual identity spec
      ui-design-spec.md             # Component design system
      copy-deck.md                  # User-facing copy
      stitch-mockups/               # HTML prototypes (6 pages)
    build-specs/                  # Technical implementation specs
      spec-00-overview.md           # Project overview
      spec-01-foundation.md         # Foundation layer
      spec-02-database-layer.md     # Two-tier database
      spec-03-ingest.md             # Phase 1: Ingest
      spec-04-match.md              # Phase 2: Match
      spec-05-enrich-export.md      # Phases 3-4: Enrich + Export
      spec-06-lanes-reprocess.md    # Lanes + reprocessing
      spec-07-chat-renderer.md      # Chat PNG rendering
      spec-08-web-app.md            # FastAPI web application
      spec-09-templates-static.md   # Templates + static assets
      spec-10-docker-infra.md       # Docker infrastructure
  snatched/                       # Python source (8,350 LOC)
    app.py                          # FastAPI application factory
    auth.py                         # Authelia auth integration
    config.py                       # TOML config + Pydantic settings
    db.py                           # PostgreSQL connection pool
    jobs.py                         # Job queue management
    models.py                       # Request/response schemas
    utils.py                        # Shared utilities
    processing/                   # Core pipeline (5,500+ LOC)
      ingest.py                     # Phase 1
      match.py                      # Phase 2
      enrich.py                     # Phase 3
      export.py                     # Phase 4
      lanes.py                      # Three-lane controller
      reprocess.py                  # Selective reprocessing
      chat_renderer.py              # Pillow chat PNG renderer
      xmp.py                        # XMP sidecar generation
      sqlite.py                     # Per-user SQLite management
      schema.sql                    # 12-table SQLite schema
    routes/                       # Web routes (930+ LOC)
      pages.py                      # HTML page routes
      api.py                        # JSON API endpoints
      uploads.py                    # File upload handling
    templates/                    # Jinja2 HTML templates (11 files)
    static/                       # CSS + htmx.min.js
    tests/                        # (empty -- needs tests)
```

---

## Configuration

Main config: `snatched.toml` (mounted at `/app/snatched.toml` in container)

Key settings:
- `server.data_dir` -- Upload and processing storage path
- `pipeline.gps_window_seconds` -- GPS cross-reference time window (default 300s)
- `pipeline.batch_size` -- SQLite commit batch size (default 500)
- `export.xmp_sidecars` -- Enable XMP sidecar generation (default false)
- `export.burn_overlays` -- Burn Snapchat overlays onto media (default true)
- `export.dark_mode_pngs` -- Generate dark mode chat PNGs (default false)

---

## Docker

Build context: `~/docker/compose/snatched/`

```bash
# Rebuild
sg docker -c "docker compose -f ~/docker/compose/docker-compose.yml build snatched"

# Restart
sg docker -c "docker compose -f ~/docker/compose/docker-compose.yml up -d snatched"

# Health check
sg docker -c "docker exec snatched curl -sf http://127.0.0.1:8000/api/health"

# Logs
sg docker -c "docker logs snatched --tail 50"
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/summary` | Aggregate stats (total jobs, storage) |
| GET | `/api/jobs` | List user's jobs |
| GET | `/api/jobs/{id}` | Job detail |
| GET | `/api/jobs/{id}/stream` | SSE progress stream |
| POST | `/api/jobs/{id}/reprocess` | Selective reprocessing |
| POST | `/api/jobs/{id}/cancel` | Cancel running job |
| GET | `/api/matches/html` | Paginated match rows (htmx partial) |
| GET | `/api/assets/html` | Paginated asset rows (htmx partial) |
| POST | `/upload` | Upload ZIP and start processing |
| GET | `/download/{id}` | Download results ZIP |
| GET | `/download/{id}/file` | Download individual file |

---

## Roadmap

See [docs/pro-features-roadmap.md](docs/pro-features-roadmap.md) for the full 36-feature premium tier roadmap across 6 tiers:

- **P0** -- Wire existing hidden features (upload checkboxes, stats, reprocessing)
- **P1** -- Metadata power tools (tag viewer/editor, batch ops, XMP editor)
- **P2** -- Correction tools (GPS, timestamps, friend names, privacy redaction)
- **P3** -- Advanced pipeline controls (confidence thresholds, output formats)
- **P4** -- Browse & visualize (memory browser, map view, timeline, vacation albums)
- **P5** -- Account & quota management
- **P6** -- Automation & integration (API keys, webhooks, scheduled exports)

---

## Background

Snatched started as SnapFix v1 (1,871-line Python script), grew into v2 (4,813-line monolith + 1,101-line chat renderer), and was rebuilt as v3 -- a proper multi-user web application. The architecture was designed through two rounds of 5-agent debate and refined through a 3-agent code review that produced 15 findings.

**Why it exists:** Snapchat's data export gives you a pile of unnamed files and separate JSON metadata. Snatched reunites them -- matching media to metadata, embedding EXIF tags, rendering chat conversations as images, and organizing everything into a browsable archive. As of September 2026, Snapchat will cap free storage at 5 GB and delete your newest memories first.

---

*Not affiliated with Snap Inc.*
