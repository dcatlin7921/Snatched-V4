# Snatched v3 — Two Paths to Ship

**2026-02-26 | Gravity-grounded, multi-user ready**

---

## The Inventory (what exists today)

152 routes. 40 templates. 14,530 lines of templates. 34+ features.

**Wired and working (the core):**
- Upload (chunked, resumable, SHA-256 verified)
- 4-phase pipeline (ingest → match → enrich → export)
- Living Canvas job page (SSE, auto-continue for speed_run)
- Dashboard, Results, Download
- Login/auth, Settings, Preferences

**Wired tools (power user):**
- Friends/aliases, GPS correction, Timestamp correction
- Duplicates, Albums, Tag presets, Export config
- Match config, Redaction, Dry run, Browse/Gallery/Timeline/Map/Conversations

**Orphaned (built, no entry point):**
- API Keys (390 lines), Webhooks (794 lines), Schedules (517 lines)
- Custom XMP Schemas (530 lines), Register page, Job Groups
- Configure page (bypassed by Living Canvas auto-configure)
- Pipeline configs (API-only, no UI)

**Dead weight for multi-user shipping:**
- Webhooks, Schedules, Custom Schemas, Pipeline Configs — these serve zero users today
- 2,231 lines of templates nobody can reach

---

## The Two Paths

### PATH 1: Quick Memory Fixer (the "just get my photos back" path)

**Target user:** Someone who just wants their Snapchat memories rescued. No fiddling. Upload, wait, download.

**What it does:**
1. Upload Snapchat export ZIP
2. Full ingest (parse all JSON, scan all media)
3. Full match cascade (6 strategies)
4. Enrich: GPS from metadata + location history, timestamps, filenames
5. Export: sorted by date into `memories/{year}/`, EXIF embedded (date, GPS, description), no XMP sidecars
6. Pre-built ZIP, one-click download

**What it does NOT do:**
- No chat export
- No story export
- No overlay burning
- No chat PNG rendering
- No sidecar files
- No manual corrections (GPS, timestamps, friends)
- No albums, duplicates, redaction, presets, match config
- No dry run

**Lanes:** `memories` only
**Phases:** All 4, no pauses
**UI flow:** Upload → auto-process → Download. That's it.

**What stays live:**
- `/upload` — simplified, no mode picker, no lane checkboxes
- `/job/{id}` — progress bar + stats only, no tools sidebar, no view tabs
- `/download/{id}` — big ZIP button, no file tree
- `/dashboard` — job cards with status
- `/login`, `/settings` — as-is

**What gets hidden (not deleted):**
- Tools sidebar on job page
- View tabs (gallery, timeline, map, conversations)
- Results page tools dropdown
- All power-user features
- Configure page
- All orphaned pages

**Implementation:** This is mostly template changes — conditional rendering based on a `quick_mode` flag or the `processing_mode` field. The pipeline already supports lane filtering. The speed_run auto-continue already works.

**Estimated work:** 4-6 hours
- Template conditionals for simplified UI
- Force lanes=["memories"] when quick mode
- Skip overlay burning, chat PNG, XMP in export config
- Simplified download page (ZIP only, no tree)
- Hide all tools/views

---

### PATH 2: Full Path (the "I want everything" path)

**Target user:** Someone who wants full control. Memories, chats, stories. Manual corrections. Browse before downloading.

**What it does:**
1. Upload Snapchat export ZIP
2. Full ingest
3. Full match cascade
4. Enrich with all metadata sources
5. Export all lanes: memories (sorted by year), chats (sorted by conversation), stories
6. Overlay burning, chat PNG rendering, XMP sidecars (optional)
7. Pre-built ZIP download + individual file browser
8. Full tool access: GPS, timestamps, friends, albums, duplicates, presets, export config

**Lanes:** memories + chats + stories
**Phases:** All 4, with optional pause points (power_user mode)

**UI flow:** Upload → Living Canvas (current flow) → Tools → Download

**What stays live (everything currently wired):**
- Full Living Canvas job page with tabs and tools
- Results page with full tools dropdown
- Download page with file tree (power_user) or ZIP-only (speed_run)
- All 7 tool sidebar links
- All 4 view tabs
- All results tools

**What gets cleaned up:**
- Remove orphaned pages from codebase (or gate behind admin flag)
- Wire `/register` from login page
- Fix duplicate resolve (currently silent no-op)
- Add redaction link to job.html sidebar (currently only in results dropdown)

**Estimated work:** 8-12 hours
- Clean up orphaned features (hide or wire)
- Fix duplicate resolve
- Wire register from login
- Add redaction to sidebar
- Polish CSS (form focus, upload zone, download hero — the quick wins)
- Per-job data isolation (the architectural fix for multi-user)

---

## What Gets Cut (Both Paths)

These features don't serve either path today:

| Feature | Lines | Verdict |
|---------|-------|---------|
| Webhooks | 794 template + 5 API routes | Cut. No execution engine. No users. |
| Scheduled Exports | 517 template + 4 API routes | Cut. Schedules never fire. |
| Custom XMP Schemas | 530 template + 4 API routes | Cut. Schemas not consumed by pipeline. |
| Pipeline Configs | 3 API routes, no UI | Cut. Unused. |
| API Keys | 390 template + 3 API routes | Cut. No external API consumers. |
| Job Groups UI | 110 template | Keep wiring (job_group_id fixed), hide page until bulk upload ships. |

**Total cut: 2,231 lines of templates, 19 API routes**

---

## Multi-User Readiness Checklist

These must land before opening to other users:

| Item | Status | Path 1 | Path 2 |
|------|--------|--------|--------|
| Per-job data isolation (`/data/{user}/jobs/{id}/`) | NOT DONE | Required | Required |
| Per-user job queue (no concurrent stomping) | NOT DONE | Required | Required |
| Registration page wired | NOT DONE | Required | Required |
| JWT secret >= 32 bytes | NOT DONE | Required | Required |
| Delete job safety (last-job guard) | DONE | Done | Done |
| Atomic state transitions | DONE | Done | Done |
| Partial chunk rejection | DONE | Done | Done |
| Input validation on reprocess | DONE | Done | Done |
| Pre-built ZIP (no OOM on download) | DONE | Done | Done |
| Port bindings locked to 127.0.0.1 | NOT DONE | Required | Required |

---

## Recommended Order

1. **Per-job data isolation** — This blocks everything. Without it, multi-user is unsafe.
2. **Per-user job queue** — Prevents concurrent jobs from stomping shared state.
3. **Path 1 (Quick Memory Fixer)** — Ship the simple path first. Get it in people's hands.
4. **Path 2 (Full Path)** — Layer on top. Everything Path 1 does, plus tools and options.
5. **CSS polish** — 33 minutes of quick wins, do alongside any path.
6. **Cut dead weight** — Hide/remove orphaned features to reduce cognitive load.

---

## The Architecture for Both Paths

```
/data/{username}/jobs/{job_id}/
    proc.db              # per-job SQLite
    extracted/           # per-job extracted media
    output/              # per-job output
        memories/
            2024/
            2025/
        chat/            # (Path 2 only)
        stories/         # (Path 2 only)
    output.zip           # pre-built ZIP
    staging/             # upload staging
    .snatched/
        report.json
        report.txt
```

Upload page offers two buttons:
- **Quick Rescue** → lanes=["memories"], mode="speed_run", no options
- **Full Export** → lane picker, mode picker, all options

Job page detects which path and shows appropriate UI:
- Quick: progress bar + stats → download
- Full: Living Canvas with tabs, tools, countdowns

Same pipeline. Same codebase. Different UI surface area.
