# Snatched v3 — Polish & Finishing Touches

**Created**: 2026-03-04
**Status**: Living document — ideas tracked here before implementation
**Scope**: Final polish items, UX tweaks, and small features to ship v3 solid

---

## P-1: Duplicate Asset Detection (Premium)

**Priority**: Medium | **Effort**: Low | **Tier**: Premium only

### Problem
Snapchat exports ship duplicate files under different IDs. Example: a story reply DM
has two `Media IDs` separated by `|` — Snapchat puts two identical files in the zip
(`b~EiASFW...jpg` and `3db19b5...jpg`, same SHA-256, same bytes). Both get ingested
as separate assets, both get matched, both get copied to output. Multiplied across
all conversations.

**Measured scope** (job 30 — 3,814 assets):
- 200 duplicate groups, 271 redundant files
- Mostly overlay reuse (same sticker on multiple snaps)
- Some chat media duplication (story replies, like the Shelby case)
- Detection query: **9.8ms** — effectively free

### Design
- **When**: Run once at end of ingest (after scan, before match)
- **What**: `GROUP BY sha256 HAVING COUNT(*) > 1` on assets table
- **Storage**: Add `dup_of INTEGER REFERENCES assets(id)` column to assets
  - NULL = primary (canonical copy)
  - Set = duplicate, points to the primary asset in the group
  - Primary selection: lowest asset ID in each SHA group (first scanned = winner)
- **Match phase**: Duplicates still get matched normally (both file_ids exist in
  chat_media_ids, both get `exact_media_id` matches). No change to matching.
- **Export phase (premium)**: Skip copying files where `dup_of IS NOT NULL`.
  Merge EXIF tags from both matches onto the primary copy (both media IDs in metadata).
  Report shows "N duplicates detected, M bytes saved."
- **Export phase (free)**: Ignore `dup_of`, copy everything as-is (current behavior).
- **Reports**: Dedup summary in Intelligence Report — count, bytes saved, groups.

### Implementation notes
- SHA-256 already computed during scan — zero additional I/O
- Column migration: `ALTER TABLE assets ADD COLUMN dup_of INTEGER`
- Single pass after `scan_media()` returns, before `run_matching()` starts
- No changes to chat_media_ids, matches, or match strategies
- Export `copy_files()` adds `AND a.dup_of IS NULL` to its query when premium

---

## P-2: Step Descriptions on Export Progress

**Priority**: Low | **Effort**: Done | **Tier**: All

Added 2026-03-04. Each of the 8 export phases now shows a brief description
below the label (e.g. "Saving originals with integrity verification" under
"Copying files"). Helps users understand the 10+ minute wait.

**File**: `snatched/templates/snatchedmemories.html` — CSS + JS only.

---

## P-3: JWT Secret Warning

**Priority**: High | **Effort**: Trivial | **Tier**: All

`SNATCHED_JWT_SECRET` is 17 bytes — security warning on every container startup.
Generate a proper 256-bit secret and store in `~/docker/secrets/snatched_jwt_secret`.

---

## P-4: Orphaned Export Work Directories

**Priority**: Low | **Effort**: Trivial | **Tier**: All

Old deleted exports may leave `work/` directories on disk. Add a cleanup sweep to
the retention/cron cycle, or a button in admin panel.

Known orphans: `/data/dave/jobs/16/exports/{9,10,11,12,13}/`

---

## P-5: Immich Port Binding

**Priority**: High | **Effort**: Trivial | **Tier**: N/A (infra)

Manyfold still binds `0.0.0.0:3214` — needs `127.0.0.1:3214` before any external
exposure via Step 9. Immich was fixed 2026-03-03.

---

## P-6: Chat Media Embed — Multiple Images per Message

**Priority**: Low | **Effort**: Medium | **Tier**: All

Currently `media_path_map[msg_id]` stores only the FIRST resolved path (due to
`if mid not in media_path_map` guard). Messages with multiple media IDs (like the
Shelby story reply with 2 images) only embed one thumbnail in the chat PNG.

With P-1 dedup, most of these are identical files anyway. But if Snapchat ever
ships a message with genuinely different multiple attachments, only the first shows.

**Fix**: Change `media_path_map` from `dict[int, str]` to `dict[int, list[str]]`.
Renderer would need to handle a media strip/grid for multi-image messages.

Low priority — dedup makes this cosmetic for the known cases.

---

## P-7: Container Log Noise Cleanup

**Priority**: Low | **Effort**: Low | **Tier**: All

Review container logs for recurring warnings that can be silenced or fixed:
- JWT secret warning (covered by P-3)
- Any exiftool warnings on specific file types
- SQLite WAL/journal messages during concurrent reads

---

## Completed Items

| ID | Description | Date |
|----|-------------|------|
| P-2 | Step descriptions on export progress UI | 2026-03-04 |

---

## Decision Log

| Date | Decision | Context |
|------|----------|---------|
| 2026-03-04 | Dedup is premium-only, ingest-time detection, export-time skip | Compute cost is ~10ms, zero new I/O. Free tier keeps all copies (safe default). Premium skips redundant copies and merges EXIF. |
| 2026-03-04 | `dup_of` column approach over separate table | Simpler query in export — just `AND a.dup_of IS NULL`. No join needed. |
