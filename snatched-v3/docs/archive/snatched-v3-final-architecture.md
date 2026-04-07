# Snatched v3 — Final Architecture Plan

**2026-02-26 | Two products, one pipeline, multi-user ready**

---

## The Core Insight

The pipeline has two halves that should be decoupled:

```
PROCESSING (shared, runs once per upload):
  Ingest → Match → Enrich
  Produces: proc.db with all assets matched, GPS resolved,
  timestamps normalized, friends mapped. This is the expensive work.

EXPORT (separate entity, many per job, async):
  Each export is a configured output package.
  User picks what they want → system builds ZIP → user downloads when ready.
```

---

## The Data Model

### Current (monolith)
```
Job = Upload + Ingest + Match + Enrich + Export (one thing)
Output = /data/{username}/output/ (shared, stomps across jobs)
```

### New (decoupled)
```
Job = Upload + Ingest + Match + Enrich (processing only)
Export = configured output package (many per job, async)
Output = /data/{username}/jobs/{job_id}/exports/{export_id}/ (isolated)
```

### New DB Schema

```sql
-- Existing table, but export phase REMOVED from job lifecycle
-- processing_jobs stays as-is, but phases_requested only ever
-- contains ["ingest", "match", "enrich"]. Never "export".
-- Final job status after processing: "completed" (not "exported")

-- NEW TABLE
CREATE TABLE exports (
    id              SERIAL PRIMARY KEY,
    job_id          INTEGER NOT NULL REFERENCES processing_jobs(id),
    user_id         INTEGER NOT NULL REFERENCES users(id),
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending','building','completed','failed')),
    export_type     TEXT NOT NULL DEFAULT 'full'
                    CHECK(export_type IN ('quick_rescue','full')),
    -- What to include
    lanes           TEXT[] NOT NULL DEFAULT '{"memories"}',
    -- Options
    exif_enabled    BOOLEAN NOT NULL DEFAULT TRUE,
    xmp_enabled     BOOLEAN NOT NULL DEFAULT FALSE,
    burn_overlays   BOOLEAN NOT NULL DEFAULT TRUE,
    chat_text       BOOLEAN NOT NULL DEFAULT TRUE,
    chat_png        BOOLEAN NOT NULL DEFAULT TRUE,
    -- Output
    output_dir      TEXT,          -- /data/{user}/jobs/{job_id}/exports/{export_id}/
    zip_path        TEXT,          -- /data/{user}/jobs/{job_id}/exports/{export_id}.zip
    zip_size_bytes  BIGINT,
    file_count      INTEGER,
    -- Lifecycle
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    error_message   TEXT,
    stats_json      JSONB
);
```

### New Filesystem Layout

```
/data/{username}/jobs/{job_id}/
    proc.db                          # per-job SQLite (processing data)
    extracted/                       # per-job extracted media from ZIP
    staging/                         # upload staging area
    .snatched/report.json            # processing report
    exports/
        1/                           # export ID 1 (Quick Rescue)
            memories/
                2017/
                2018/
                ...
        1.zip                        # pre-built ZIP for export 1
        2/                           # export ID 2 (Full — chats + stories)
            memories/
            chat/
            stories/
        2.zip
```

---

## The Two Products

### Product 1: Quick Rescue ($free / default)

**What the user sees:**

```
Upload page → "Rescue My Memories" button
              (no options, no lane picker, no mode selector)
                    ↓
Job page → progress bar, stats ticking up
           "Processing your archive..."
           Ingest → Match → Enrich → auto-export (memories only)
                    ↓
Download page → "Your memories are ready"
                Big ZIP button, file count, size
                Stats: files rescued, GPS coverage, date range
                    ↓
                Upsell card:
                "Want your chats and stories too?
                 Upgrade to Full Export to unlock conversations,
                 story recovery, and advanced tools."
                 [Unlock Full Export →]
```

**What happens under the hood:**
1. Upload creates job with `processing_mode = 'quick_rescue'`
2. Pipeline runs: ingest → match → enrich (all 3 phases, full data)
3. On enrich completion, system AUTO-CREATES an export:
   - `export_type = 'quick_rescue'`
   - `lanes = ["memories"]`
   - `exif_enabled = true, xmp_enabled = false, burn_overlays = true`
   - `chat_text = false, chat_png = false`
4. Export runs async: copy files → embed EXIF → build ZIP
5. Job page polls export status, shows download when ready

**What Quick Rescue does NOT include in export:**
- No chat media, no chat PNGs, no chat text files
- No story reconstruction
- No XMP sidecars
- No manual tools (GPS correction, timestamp fixes, etc.)

**Important:** The pipeline STILL ingests chat/story JSON during processing (it's part of the shared ingest phase and costs nothing extra). This means the proc.db knows exactly how many chats and stories exist. Quick Rescue just doesn't EXPORT them.

**What Quick Rescue tells the user:**
- "Your memories have been rescued."
- Upsell card: "We also found **719 chat messages** and **7 stories** in your archive. Unlock Full Export to get everything."
- Upgrade is instant — no re-upload, no re-processing, proc.db already has the data

**Upgrade path:**
- User clicks "Unlock Full Export" → taken to export configuration page
- Processing is ALREADY DONE (proc.db has everything)
- User just configures a new export with more lanes/options
- No re-upload, no re-processing

---

### Product 2: Full Export ($paid tier / power user)

**What the user sees:**

```
Upload page → "Full Export" button (or upgrade from Quick Rescue)
              Lane picker: [x] Memories  [x] Chats  [x] Stories
              Mode: Speed Run / Power User
                    ↓
Job page → Living Canvas (current flow)
           Ingest → [countdown] → Match → [countdown] → Enrich
           Gallery, Timeline, Map, Conversations tabs
           Tools sidebar: Friends, GPS, Timestamps, etc.
                    ↓
Export Config page → Pick what to export:
                     [x] Memories (sorted by year, EXIF embedded)
                     [x] Chats (text + PNG renders)
                     [x] Stories (video + image)
                     Options:
                       [x] Burn overlays
                       [ ] XMP sidecars
                       [x] EXIF metadata
                       [ ] Dark mode chat PNGs
                     [Generate Export →]
                    ↓
Job page shows export card:
  "Building your export... 2,408 memories + 719 chats + 7 stories"
  Progress bar → "Export ready" → Download button
                    ↓
User can create ANOTHER export with different settings:
  "Export just 2024 memories with XMP sidecars" → queue it
  "Export just chats as text only" → queue it
  Each one appears as a card with status + download
```

**What happens under the hood:**
1. Upload creates job with `processing_mode = 'full'`
2. Pipeline runs same as Quick Rescue: ingest → match → enrich
3. On completion, user is taken to export configuration (NOT auto-export)
4. User configures export → creates export record → async build
5. User can create multiple exports against same job
6. Each export produces its own directory + ZIP

---

## What Stays, What Goes, What Changes

### STAYS LIVE (both products)

| Feature | Route | Notes |
|---------|-------|-------|
| Upload | `/upload` | Two buttons: Quick Rescue / Full Export |
| Dashboard | `/dashboard` | Shows jobs + their exports |
| Job (Living Canvas) | `/job/{id}` | Simplified for Quick Rescue, full for Full Export |
| Login | `/login` | As-is, add register link |
| Register | `/register` | Wire from login page |
| Settings | `/settings` | As-is |
| Landing | `/` | As-is |
| Download | `/download/{id}` | Reworked: shows export cards, not raw file tree |

### STAYS LIVE (Full Export only, hidden for Quick Rescue)

| Feature | Route | Notes |
|---------|-------|-------|
| Gallery tab | `/api/jobs/{id}/gallery/html` | View tab on job page |
| Timeline tab | `/api/jobs/{id}/timeline-data` | View tab on job page |
| Map tab | `/api/jobs/{id}/map-data` | View tab on job page |
| Conversations tab | `/api/jobs/{id}/conversations/html` | View tab on job page |
| Friends | `/friends` | Tool sidebar |
| GPS Correction | `/gps/{id}` | Tool sidebar |
| Timestamps | `/timestamps/{id}` | Tool sidebar |
| Duplicates | `/duplicates/{id}` | Tool sidebar |
| Albums | `/albums/{id}` | Tool sidebar |
| Tag Presets | `/presets` | Tool sidebar |
| Export Config | `/export-config` | Reworked: creates export records |
| Match Config | `/match-config/{id}` | Results tools |
| Redaction | `/redact/{id}` | Results tools + add to sidebar |
| Browse Files | `/browse/{id}` | Results tools |
| Dry Run | `/dry-run/{id}` | Results tools |
| Results | `/results/{id}` | Full tools dropdown |
| Asset Detail | `/assets/{job_id}/{asset_id}` | Gallery click-through |
| Quota | `/quota` | Settings link |

### REWORKED

| Feature | What Changes |
|---------|-------------|
| **Upload page** | Two clear entry points: Quick Rescue (one button) vs Full Export (lane picker + options) |
| **Job page** | Quick Rescue: progress only, no tools/tabs. Full: current Living Canvas. Both show export cards when processing done. |
| **Download page** | Becomes export-centric: list of export cards with status/download buttons. No raw file tree for Quick Rescue. |
| **Export Config** | Reworked to CREATE export records instead of setting global prefs. Each config submission queues an async export. |
| **Pipeline** | Export phase removed from job lifecycle. Jobs end at "completed" after enrich. Exports are separate. |
| **Data layout** | Per-job directories under `/data/{user}/jobs/{job_id}/`. Per-export output under `exports/{export_id}/`. |

### CUT (hide behind admin flag, don't delete)

| Feature | Lines | Why |
|---------|-------|-----|
| Webhooks | 794 template, 5 API routes | No execution engine. No users. |
| Scheduled Exports | 517 template, 4 API routes | Schedules never fire. |
| Custom XMP Schemas | 530 template, 4 API routes | Not consumed by pipeline. |
| Pipeline Configs | 3 API routes | Unused. |
| API Keys | 390 template, 3 API routes | No external consumers. |
| Configure page | 303 template | Replaced by auto-configure (Quick Rescue) or export config (Full). |
| Job Progress (legacy) | 212 template | Already 301-redirects to Living Canvas. Delete. |

**Total cut: ~2,746 lines of templates, 19 API routes**

### NEW (must build)

| Feature | What | Effort |
|---------|------|--------|
| `exports` table | DB schema + migrations | 1 hour |
| Export worker | Async function that runs phase4_export against a job's proc.db with export-specific config, writes to export dir, builds ZIP | 4-6 hours |
| Export API | `POST /api/exports` (create), `GET /api/exports` (list), `GET /api/exports/{id}` (status), `DELETE /api/exports/{id}` | 2-3 hours |
| Export cards UI | htmx component showing export status + download button, embedded in job page and download page | 2-3 hours |
| Per-job data isolation | Refactor all path references from `/data/{user}/` to `/data/{user}/jobs/{job_id}/` | 4-6 hours |
| Per-user job queue | Mutex/semaphore preventing concurrent processing for same user | 2-3 hours |
| Quick Rescue auto-export | On enrich complete, auto-create memories-only export | 1 hour |
| Upsell card | "Chats and stories detected" card on Quick Rescue download page | 1 hour |
| Upload page rework | Two entry points instead of mode/lane pickers | 2-3 hours |

---

## RAM Drive Processing

With 64GB allocated to the snatched container, upload processing should happen entirely in RAM to eliminate disk I/O during the heavy phases.

### How it works

```
Docker compose mount:
  tmpfs:
    - /ramdisk:exec,size=32G    # half of 64GB allocation

Upload flow:
  1. Chunks stream to /ramdisk/jobs/{job_id}/staging/    (RAM)
  2. ZIP verified via SHA-256                             (RAM)
  3. ZIP extracted to /ramdisk/jobs/{job_id}/extracted/   (RAM)
  4. proc.db created at /ramdisk/jobs/{job_id}/proc.db    (RAM)
  5. Ingest, Match, Enrich all run against RAM paths      (RAM)
  6. On completion: proc.db + extracted/ moved to disk     (disk)
  7. Export reads from disk, writes output + ZIP to disk   (disk)
  8. RAM cleaned up                                        (RAM freed)
```

### Why this matters

- **5.7GB ZIP + ~8GB extracted = ~14GB in RAM** — well within 32GB tmpfs
- Ingest parses 8 JSON files + scans 3,814 assets: **all random I/O, all in RAM**
- Match runs 6 strategies against SQLite: **WAL journal writes in RAM**
- Enrich cross-references GPS/locations: **more SQLite reads, all RAM**
- Only the final proc.db (8MB) and exports touch the SSD
- **Estimated speedup: 3-5x** for processing phases (SSD latency eliminated)
- If container crashes mid-processing: no partial files on disk, RAM just vanishes, job marked failed, user re-uploads

### Compose config change

```yaml
snatched:
  tmpfs:
    - /ramdisk:exec,size=32G
```

### Code change

Pipeline path resolution checks for `/ramdisk/jobs/{job_id}/` first during processing. After enrich completes, `shutil.move()` the proc.db and extracted dir to the persistent `/data/{user}/jobs/{job_id}/` path. Exports always read from and write to disk.

---

## Silent Archive (Admin Only)

Every uploaded ZIP is silently preserved for Dave's reprocessing and testing.

### How it works

```
After upload verification (SHA-256 confirmed):
  1. Copy original ZIP to archive location
  2. Write audit metadata alongside it
  3. User never sees this — no UI, no API exposure

Archive location:
  /mnt/nas-pool/snatched-archive/{username}/{job_id}/
      original.zip              # exact copy of uploaded file
      manifest.json             # audit metadata

manifest.json:
  {
    "job_id": 42,
    "username": "alice",
    "upload_filename": "my_data-2026-02-26.zip",
    "upload_size_bytes": 5708220459,
    "sha256": "abc123...",
    "uploaded_at": "2026-02-26T05:38:37Z",
    "source_ip": "10.0.0.167",
    "archived_at": "2026-02-26T06:18:10Z"
  }
```

### Security

- Archive dir: `chmod 700 /mnt/nas-pool/snatched-archive/` — only dave owns it
- Container mounts it write-only: `/mnt/nas-pool/snatched-archive:/archive:rw`
- No API endpoint exposes the archive — not in routes, not in templates
- No user-facing reference to archiving anywhere
- Archive copy happens in background after upload verify, doesn't block the user
- If archive write fails (NAS offline, disk full), log warning and continue — never fail the job

### Compose config change

```yaml
snatched:
  volumes:
    - /mnt/nas-pool/snatched-archive:/archive
```

### Code change

In `uploads.py` after SHA-256 verification succeeds, spawn a background task:

```python
async def _archive_upload(username, job_id, source_path, metadata):
    """Silently copy upload to admin archive. Fire-and-forget."""
    archive_dir = Path("/archive") / username / str(job_id)
    archive_dir.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(shutil.copy2, source_path, archive_dir / "original.zip")
    (archive_dir / "manifest.json").write_text(json.dumps(metadata, indent=2))
```

### Retention

Archives live on the NAS RAID (20TB, mirrored). No automatic cleanup — Dave decides when to prune. At ~5GB per upload, the NAS holds ~1,800 archives before filling.

---

## Split ZIP Exports

Export ZIPs exceeding 2GB are split into multiple standalone valid ZIP archives, matching Snapchat's own multi-part export pattern.

### How it works

```
Export worker builds output files → measures total size:
  If total < 2GB: single export-1.zip
  If total > 2GB: split into export-1.zip, export-2.zip, ... (each ≤ 2GB)

Algorithm:
  1. Collect all output files as (arcname, path, size) tuples
  2. Sort by directory then filename (keeps related files together)
  3. Iterate, accumulating size per part
  4. When adding next file would exceed 2GB → close current ZIP, start new
  5. Single file > 2GB → own part (edge case: large video, logged as warning)
  6. Each part is a standalone valid ZIP — independently extractable

Output:
  /data/{user}/jobs/{job_id}/exports/{export_id}/
      export-1.zip    (≤ 2 GB)
      export-2.zip    (≤ 2 GB)
      ...
```

### Why 2GB

- Matches Snapchat's own export split boundary
- Stays well under ZIP32 4GB limit
- Avoids browser download timeout issues
- Each part finishes faster → better UX on slow connections
- Compatible with all extraction tools (no special reassembly needed)

### Database

`exports` table stores:
- `zip_dir TEXT` — directory containing the export-N.zip parts
- `zip_part_count INTEGER DEFAULT 1` — how many parts
- `zip_total_bytes BIGINT` — sum of all parts
- `stats_json` includes per-part metadata:
```json
{
    "zip_parts": [
        {"part": 1, "filename": "export-1.zip", "files": 847, "size_bytes": 1998000000},
        {"part": 2, "filename": "export-2.zip", "files": 312, "size_bytes": 1450000000}
    ]
}
```

### Download UI

Multi-part exports show one button per part:
```
Download Parts (2 parts, 3.3 GB total)
  [Part 1 · 847 files · 1.9 GB]
  [Part 2 · 312 files · 1.4 GB]
```

Single-part exports show the standard single download button.

---

## Folder Upload (No ZIP Required)

Users who already unzipped their Snapchat export (on phone, or combined multiple exports into one folder) can upload the raw folder structure directly.

### How it works

```
Upload page: mode toggle — "ZIP Upload" / "Folder Upload"

Folder Upload flow:
  1. User clicks "Folder Upload" toggle
  2. Browser shows folder picker (<input webkitdirectory>)
  3. Client-side JS validates Snapchat structure:
     - Checks for json/ directory with memories_history.json
     - Checks for memories/ directory with matching file patterns
     - Counts files, warns if structure looks incomplete
  4. Files uploaded individually through existing chunked system
     - Each file has relative_path metadata preserved
     - 3-4 concurrent upload streams for speed
     - No per-file SHA-256 (too slow for 3,800+ files)
  5. Server reconstructs directory structure after all files verified
  6. Ingest phase skips ZIP extraction, goes straight to discover_export()
```

### Client-side validation

```javascript
// Checks before uploading
- Has json/memories_history.json → primary export (best accuracy)
- Has memories/ with date_uuid pattern files → secondary export (media only)
- Has chat_media/ → chat data available
- Warning if no json/ → "Metadata will be limited, accuracy reduced"
```

### Expected Snapchat folder structure

```
snapchat-export/
├── json/
│   ├── memories_history.json     (required for full accuracy)
│   ├── chat_history.json
│   ├── snap_history.json
│   ├── shared_story.json
│   ├── friends.json
│   ├── location_history.json
│   └── snap_map_places.json
├── memories/                      (required: at least json/ or memories/)
│   ├── YYYY-MM-DD_{uuid}-main.jpg
│   ├── YYYY-MM-DD_{uuid}-overlay.png
│   └── ...
├── chat_media/                    (optional)
│   ├── YYYY-MM-DD_{file_id}.jpg
│   └── ...
└── shared_story/                  (optional)
    └── ...
```

### Database changes

```sql
-- upload_files table addition
ALTER TABLE upload_files ADD COLUMN IF NOT EXISTS relative_path TEXT;

-- upload_sessions options_json now includes:
-- { "upload_type": "zip" }   -- or "folder"
```

### Limitations & warnings

- **Browser compatibility**: Chrome, Firefox, Edge only. NOT Safari iOS.
- **Accuracy warning**: "Folder uploads may be less accurate than ZIP uploads. Some metadata may be missing if files were renamed or moved."
- **Performance**: 3,800+ individual file uploads is slower than one 5GB ZIP. Mitigated by concurrent upload streams (3-4 parallel).
- **No per-file integrity**: SHA-256 hashing skipped for individual files (too slow). Session-level integrity only.
- **Renamed files**: If user renamed files from Snapchat's naming convention, UUID matching will fail for those files.

---

## Multi-User Readiness Checklist

| Item | Status | Blocks |
|------|--------|--------|
| Per-job data isolation | **NOT DONE** | Everything |
| Per-user job queue | **NOT DONE** | Multi-user safety |
| RAM drive (tmpfs) for processing | **NOT DONE** | Performance |
| Silent archive to NAS | **NOT DONE** | Admin reprocessing |
| `exports` table + worker | **NOT DONE** | Export decoupling |
| Split ZIP exports (2GB parts) | **NOT DONE** | Large export downloads |
| Folder upload support | **NOT DONE** | Users with unzipped exports |
| Registration wired | **NOT DONE** | New users |
| JWT secret >= 32 bytes | **NOT DONE** | Session security |
| Port bindings → 127.0.0.1 | **NOT DONE** | Network security |
| Atomic state transitions | **DONE** | — |
| Delete job safety | **DONE** | — |
| Partial chunk rejection | **DONE** | — |
| Reprocess validation | **DONE** | — |
| Pre-built ZIP | **DONE** | — |
| SSE event ordering | **DONE** | — |

---

## Build Order

### Phase 1: Foundation (blocks everything else)
1. Per-job data isolation — refactor all paths to `/data/{user}/jobs/{job_id}/`
2. RAM drive (tmpfs 32GB) — upload + processing in RAM, move to disk after enrich
3. Silent archive — copy verified uploads to `/mnt/nas-pool/snatched-archive/`
4. Per-user job queue — prevent concurrent processing stomping
5. `exports` table + migration (includes `upload_files.relative_path` for folder upload)
6. Export worker (runs export against job's proc.db with export-specific config)
7. Export API endpoints (CRUD + status + download parts)
8. `build_split_zips()` — split exports at 2GB boundary into standalone ZIP parts

### Phase 2: Quick Rescue + Upload Enhancements (ship first)
9. Upload page: "Rescue My Memories" button + "Full Export" button
10. Folder upload: client-side UI, validation, webkitdirectory input
11. Folder upload: backend (init + verify + reconstruct + skip ZIP extraction)
12. Folder upload: client JS upload flow (concurrent streams, progress)
13. Auto-export on enrich complete (memories only)
14. Simplified job page (no tools, no tabs)
15. Download page with export cards, split ZIP parts, upsell ("chats & stories detected")
16. Wire registration from login

### Phase 3: Full Export (layer on top)
17. Export config page reworked to create export records
18. Export cards on job page and download page
19. Multiple exports per job
20. CSS quick wins (form focus, upload zone, download hero)

### Phase 4: Cleanup
21. Hide orphaned features behind admin flag
22. Delete dead code (job_progress.html)
23. JWT secret fix
24. Port binding lockdown

---

## The User Journeys (final)

### Quick Rescue Journey
```
Landing → "Rescue My Memories" →
Upload ZIP (or select folder) → progress bar →
"Processing... 3,814 files found" →
"Matching... 99.9% matched" →
"Enriching... GPS resolved for 76% of files" →
"Building your export..." →
"3,134 memories rescued. 2017-2026. 76% GPS tagged."
[DOWNLOAD ZIP]                    ← single part if < 2GB
[Part 1 · 1.9 GB] [Part 2 · 1.4 GB]  ← split if > 2GB

"We also found 719 chat messages and 7 stories.
 Unlock Full Export to get everything."
 [Unlock Full Export → $X]
```

### Full Export Journey
```
Landing → "Full Export" →
Upload ZIP (or select folder) → Living Canvas →
Ingest → Match (gallery populates) → Enrich (map lights up) →
"Processing complete. Ready to export."

Export Config:
  [x] Memories (2,408 files, sorted by year)
  [x] Chats (94 conversations, 719 media files)
  [x] Stories (7 stories)
  [x] Burn overlays  [ ] XMP sidecars
  [Generate Export →]

"Building export... come back when it's ready."
  Export 1: Full package — building... 45% →
  Export 1: Full package — ready! 3.3 GB (2 parts)
    [Part 1 · 847 files · 1.9 GB]
    [Part 2 · 312 files · 1.4 GB]

Want a different package?
  [Create Another Export →]
```

### Folder Upload Journey
```
Upload page → toggle "Folder Upload" →
Browser folder picker appears →
Select unzipped Snapchat export folder →
Client validates: "Found json/ + 3,814 memory files + 719 chat files" →
Upload files (3-4 concurrent streams, progress bar) →
Same pipeline as ZIP: Ingest → Match → Enrich → Export

⚠️ Warning shown: "Folder uploads may be less accurate.
   Files renamed from Snapchat's naming convention won't match."
```

---

## Revenue Model Hook

Quick Rescue = free (or low tier). Gets people in the door.
Full Export = paid tier. They already see what's in their archive (chat counts, story counts). The data is processed. They just need to pay to unlock the export.

No re-upload. No re-processing. Instant upgrade. The proc.db already has everything.
