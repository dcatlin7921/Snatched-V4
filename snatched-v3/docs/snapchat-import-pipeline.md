# Snapchat Import Pipeline — Full Procedure

## Status: IN PROGRESS
- **Export 1** (Memories only): Downloaded, 2,406 memories, `memories_history.json` present
- **Export 2** (My Data only): Downloaded, 759 chat media + 21 JSON metadata files
- **Export 3** (FULL — all options): Pending tomorrow (maxed out daily requests 2026-02-19)
- **CDN Link Timer**: 72 hours from export generation (countdown visible in Snapchat dashboard)
- **Deadline**: September 2026 — Snapchat deletes excess Memories over 5GB (NEWEST first)

---

## Snapchat Download Options (as of Feb 2026)

Portal: `accounts.snapchat.com` > My Data

### Special Toggles (TOP — always enable both)
- [x] **Export your Memories** — produces `memories/` folder + `memories_history.json`
- [x] **Export JSON Files** — produces `json/` folder with all metadata (REQUIRED for Snatch)

### Data Categories (10 total — select ALL for full export)
1. **User Information** — Login, Snapchat+, User Profile, Public Profile, Account History, Friends, Bitmoji, Connected Apps
2. **Chat History** — Snap History, Chat History, Talk History, Communities
3. **Spotlight** — Shared Story & Spotlight, Spotlight Replies, Story History
4. **Shopping** — Purchase History, Subscriptions, Orders, Shopping Fav, Payments, Snap Tokens
5. **Support History** — Support History, Terms History, In-app Surveys, Reported Content, Email Campaign History
6. **Ranking And Location** — Statistics & Ranking, **Location**, Ads Manager, Snap Map Places
7. **Other Media** — My Sounds, My Custom Stickers
8. **Other** — Search History, My Lenses, My Selfie & Cameos, Payouts, Snap AI, Countdowns
9. **My AI** — My AI, AI Features
10. **Export Shared Stories** — (separate toggle)

### Bottom Toggles
- [x] **Export Chat Media** — produces `chat_media/` folder with DM photos/videos

### Critical Selections for Maximum Metadata
At minimum, ALWAYS enable:
- **Export your Memories** (the photos/videos + CDN links)
- **Export JSON Files** (all metadata including `memories_history.json`)
- **Chat History** (produces `snap_history.json` with microsecond timestamps)
- **Ranking And Location** (produces `location_history.json` with GPS breadcrumbs)
- **Export Chat Media** (the actual DM media files)
- **Export Shared Stories** (shared story media files)

For a complete backup, select ALL 10 categories + all toggles.

---

## Current Data Inventory

### Export 1: Memories Only (`mydata~1771467850740`, 3 ZIPs, ~4.9GB)
- `json/memories_history.json` — 2,406 entries (1,439 images + 967 videos)
- `memories/` — 3,045 files across 3 ZIPs (includes ~636 overlay PNGs)
- **100% have GPS coordinates**
- **Date range**: July 2016 → Feb 2026 (nearly 10 years)

### Export 2: My Data Only (`mydata~1771508820169`, 1 ZIP, ~787MB)
- `json/` — 21 metadata JSON files (NO `memories_history.json`)
- `chat_media/` — 759 files (607 images, 134 videos, 18 overlays)
- `shared_story/` — 8 files
- `location_history.json` — 2,125 timestamped GPS entries
- `snap_history.json` — snap send/receive log with microsecond timestamps

### Export 3: FULL (Pending Tomorrow)
- Select ALL options + ALL toggles
- Should produce BOTH `memories_history.json` AND all metadata JSONs AND chat_media
- **Test plan**: Download Dec 21-27 2025 date range first to verify combined export works
- If confirmed: download full all-time export

---

## Pipeline — Phase 1: Memories (Snatch)

### Step 1: Merge Overlays into Single Directory
Snatch only reads ONE overlay directory. Must merge all 3:
```bash
mkdir -p /mnt/nas-pool/media/photos/snapchat-import/overlays-merged/
cp mydata~1771467850740/memories/*-overlay.* overlays-merged/
cp mydata~1771467850740-2/memories/*-overlay.* overlays-merged/
cp mydata~1771467850740-3/memories/*-overlay.* overlays-merged/
```

### Step 2: Run Snatch
```bash
/home/dave/.cargo/bin/snatch \
  /mnt/nas-pool/media/photos/snapchat-import/mydata~1771467850740/json/memories_history.json \
  -o /mnt/nas-pool/media/photos/snapchat-processed/ \
  --overlays-dir /mnt/nas-pool/media/photos/snapchat-import/overlays-merged/ \
  -c 20 \
  --workers 16
```

What Snatch does:
1. Reads `memories_history.json` (Date, Location, Download Link per memory)
2. POSTs to Snapchat CDN API → gets direct download URL → downloads file
3. Burns overlay PNGs onto base images (stickers, text, drawings)
4. Embeds EXIF: DateTimeOriginal, CreateDate, ModifyDate, GPS coordinates
5. Fixes MP4 metadata via FFmpeg (creation_time, location)
6. Sets file system timestamps to match capture date

### Step 3: Fix GPS Longitude Bug (CRITICAL)
**Bug**: Snatch v1.1.0 `decimal_to_dms()` uses N/S logic for BOTH lat AND lon.
Western hemisphere longitudes (negative values like Illinois: -89.xx) get tagged as 'S' instead of 'W'.

**Fix** (requires exiftool):
```bash
sudo apt install libimage-exiftool-perl
exiftool -GPSLongitudeRef=W -overwrite_original /mnt/nas-pool/media/photos/snapchat-processed/*.jpg
```

**Verify** (spot check):
```bash
exiftool -GPSLatitude -GPSLatitudeRef -GPSLongitude -GPSLongitudeRef <sample_file.jpg>
# Expected: GPSLatitudeRef=N, GPSLongitudeRef=W for Illinois coordinates
```

Note: This blanket fix assumes all photos are Western hemisphere. If Dave traveled
internationally (Eastern hemisphere), we need a smarter fix that checks per-file.

### Step 4: Import to Immich
```bash
# Option A: Copy to Immich external library path
cp -r /mnt/nas-pool/media/photos/snapchat-processed/* /mnt/nas-pool/media/photos/

# Option B: Use immich-go CLI for upload with metadata
# immich-go upload --server=http://10.0.0.40:2283 --key=API_KEY /mnt/nas-pool/media/photos/snapchat-processed/
```

Immich reads EXIF natively — DateTimeOriginal + GPS will auto-populate timeline and map.

---

## Pipeline — Phase 2: Chat Media (Custom Script)

Chat media files (759+) are NOT in `memories_history.json`. Snatch cannot process them.

### Available Metadata Sources
- **Filenames**: Date prefix `YYYY-MM-DD_` on most files
- **snap_history.json**: Microsecond timestamps per snap (From, Media Type, Created)
- **location_history.json**: 2,125 timestamped GPS breadcrumbs (hourly when active)

### Approach
1. Parse date from filename → embed as EXIF DateTimeOriginal
2. Cross-reference timestamp against `location_history.json` → find nearest GPS fix
3. Embed GPS if match found within reasonable time window (e.g., ±1 hour)
4. Import to Immich

### Tools Needed
- `exiftool` (apt install libimage-exiftool-perl)
- Custom Python script for cross-referencing timestamps ↔ GPS data

---

## Pipeline — Phase 3: Shared Stories + Remaining

- 8 shared story files (UUID filenames, no dates)
- Cross-reference with `shared_story.json` and `story_history.json` for timestamps
- Lower priority — small count

---

## Known Issues & Bugs

### Snatch v1.1.0 GPS Bug
- **File**: `src/exif.rs`, `decimal_to_dms()` function
- **Issue**: Uses N/S reference for both latitude AND longitude
- **Impact**: Western hemisphere longitudes tagged as 'S' instead of 'W'
- **Workaround**: Post-process with exiftool to fix GPSLongitudeRef
- **Proper fix**: PR to Snatch repo, or fork and fix locally

### CDN Link Expiration
- Links in `memories_history.json` are signed with timestamps
- **72-hour expiration** (matches Snapchat dashboard countdown timer)
- If links expire, must request a new export from Snapchat
- Snapchat limits export requests per day (Dave hit limit 2026-02-19)

### Snapchat Export Quirks
- Official export STRIPS ALL EXIF from media files
- Timestamps and GPS only preserved in JSON metadata
- Large exports split across multiple ZIP files automatically
- Overlay files are separate PNGs (not burned into base images)
- WebP files sometimes disguised as .png (Snatch handles this)

### September 2026 Storage Deadline
- Free Memories capped at 5GB
- 12-month grace period: Sept 2025 → Sept 2026
- After deadline: excess Memories **permanently deleted**
- **Deletes NEWEST first** (preserves oldest under 5GB limit)
- Deleted memories CANNOT be recovered
- Paid plans: $1.99/mo (100GB), $3.99/mo (250GB), $15.99/mo (5TB)

---

## Repeat Task Notes

This pipeline will be needed for Dave's friends. Key variables per person:
- Snapchat username / export location
- Whether they have Memories, Chat Media, or both
- Geographic region (affects GPS longitude fix — W vs E hemisphere)
- Volume of content (affects processing time and storage)

Consider building a dedicated agent or script that automates the full pipeline.

---

## Tool Inventory

| Tool | Location | Purpose |
|------|----------|---------|
| Snatch v1.1.0 | `~/.cargo/bin/snatch` | Download + EXIF embed from memories_history.json |
| exiftool | `apt install libimage-exiftool-perl` | GPS bug fix + verification + chat media tagging |
| immich-go | Not yet installed | Bulk upload to Immich with metadata |
| FFmpeg | In Snatch (bundled?) or apt | Video metadata + overlay burning |
| Python 3 | System | Custom scripts for chat media cross-referencing |

---

## Tomorrow's Action Plan (2026-02-20)

1. Request new full Snapchat export (ALL options, ALL toggles)
2. Start with Dec 21-27 2025 test range (if date filtering available)
3. If test confirms combined export: request full all-time export
4. While waiting for export: merge overlays, install exiftool
5. When export arrives: run Snatch immediately (72-hour CDN window)
6. Fix GPS bug with exiftool
7. Import to Immich
8. Phase 2: chat media script
