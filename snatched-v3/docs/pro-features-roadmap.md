# Snatched Online — Pro Features Inventory

**Status**: Implemented (all 36 features)
**Date**: 2026-02-24 (written) / 2026-02-25 (audited)
**Audience**: Development reference — pro/premium tier feature catalog
**Tiers**: Free and Pro (2-tier system)

---

## Overview

Snatched v3 ships with 36 pro-tier features spanning pipeline controls, metadata editing, visualization, account management, and automation. All features have backend API endpoints and UI templates. The guiding principle: **give power users full control over their metadata.**

### Remaining Work

- **Payment flow**: Upgrade buttons use `window.alert()` placeholders — no Stripe/payment integration yet
- **Email notifications**: Retention warnings (#30) reference email alerts not yet wired
- **Algorithm depth**: Album clustering (#27) and perceptual hashing (#26) have API scaffolds — algorithm internals need verification
- **Tier gates**: Free users see lock icons + "coming soon" on API Keys (#33) and Schedules (#36)

---

## Group 1: Pipeline Controls (Features #1–7)

Upload form options, lane/phase selectors, and dashboard stats. All wired end-to-end.

### 1. Upload Checkboxes → Pipeline
Form fields (burn_overlays, dark_mode_pngs, exif_enabled, xmp_enabled, gps_window_seconds) are parsed in `uploads.py`, stored in `user_preferences`, read by `jobs.py`, and applied to pipeline config. Full round-trip.

### 2. XMP Sidecar Generation Toggle
Toggle checkbox on upload and configure pages. Flows through `config.xmp.enabled` to `write_xmp_sidecars()` in `processing/xmp.py`. Supports alongside-EXIF, XMP-only, and custom namespace modes.

### 3. GPS Cross-Reference Window Slider
Range slider (30–1800s, step 30) on upload, configure, and settings pages. Value flows to `enrich.py` `find_nearest_location()`. Tighter window = pinpoint accuracy, wider = more matches at lower precision.

### 4. Selective Reprocessing Button
Results page "TOOLS" dropdown opens a modal with phase (match/enrich/export) and lane (memories/chats/stories) checkboxes. Calls `POST /api/jobs/{id}/reprocess`. Creates a new job with selected scope.

### 5. Lane Selector on Upload Form
Three lane checkboxes (memories, chats, stories) on upload form, all pre-checked. Also exposed as lane cards on configure page. Pipeline reads `lanes_requested` from job record.

### 6. Phase Selector (Advanced Mode)
Hidden behind "Advanced" checkbox on upload form, `<details>` accordion on configure page. Phase checkboxes for Match, Enrich, Export (Ingest always runs). Dry Run toggle forces exclusion of Export phase.

### 7. Dashboard Summary Stats
Dashboard page route queries real data: total jobs, completed count, storage bytes. Stat cards populated from DB, not placeholders. Processing Slots section shows active/queued counts.

---

## Group 2: Metadata Power Tools (Features #8–16)

The core pro differentiator. Tag editing, batch operations, GPS/timestamp correction, friend mapping, privacy redaction.

### 8. Individual Tag Viewer & Editor
Asset detail page shows all EXIF/XMP tags via `tags_module.read_tags()`. Inline edit fields with save. Every edit logged to `tag_edits` table with old/new values. Routes: `GET/PUT /api/assets/{id}/tags`, page at `/assets/{job_id}/{asset_id}`.

### 9. Batch Tag Operations
Select multiple files, apply bulk edits. Preview endpoint shows change count before committing. Logged to `tag_edits` with `edit_type='batch'`. Routes: `POST /api/assets/batch-tags/preview`, `POST /api/assets/batch-tags`. Modal included in results page.

### 10. XMP Sidecar Viewer & Editor
Side-by-side view of EXIF tags and XMP sidecar XML. Routes: `GET/PUT /api/assets/{id}/xmp`. Partial template `_xmp_viewer.html` included in asset detail page.

### 11. Custom Metadata Schema / Namespace Editor
Define custom XMP namespaces and fields. CRUD routes: `GET/POST/PUT/DELETE /api/schemas`. Schema builder UI at `/schemas`. Table: `custom_schemas`.

### 12. Tag Template Presets
Reusable tag presets applied to files, selections, or jobs. CRUD routes plus `POST /api/assets/{id}/apply-preset` and `POST /api/assets/batch-apply-preset`. Page at `/presets`. Table: `tag_presets`.

### 13. GPS Correction & Override Tool
Leaflet map with draggable pins. Saved locations with "snap to known location" (50m radius). Routes: `PUT /api/assets/{id}/gps`, `POST /api/assets/batch-gps`, `GET/POST/DELETE /api/saved-locations`, `POST /api/assets/snap-to-location`. Page at `/gps/{job_id}`.

### 14. Timestamp Correction Tool
Bulk timezone shift and absolute overrides. Routes: `GET /api/jobs/{job_id}/timestamps`, `PUT /api/assets/{id}/timestamp`, `POST /api/assets/batch-timeshift`, `POST /api/assets/batch-timezone`. Page at `/timestamps/{job_id}`.

### 15. Friend Name Mapping & Aliases
Name mapping table with aliases, merged contacts, unknown resolution. Routes: `GET /api/friends`, `POST /api/friends/alias`, `DELETE /api/friends/alias/{id}`, `POST /api/friends/apply`, `POST /api/friends/merge`. Page at `/friends`. Table: `friend_aliases`.

### 16. Privacy Redaction Tool
Redaction profiles strip sensitive metadata selectively. Preview before applying. Routes: `GET/POST/PUT/DELETE /api/redaction-profiles`, `POST /api/assets/redact/preview`, `POST /api/assets/redact/apply`. Page at `/redact/{job_id}`.

---

## Group 3: Advanced Pipeline Controls (Features #17–21)

Match tuning, export customization, dry run mode.

### 17. Match Confidence Threshold Slider
Set minimum confidence threshold (30–100%). `user_preferences.match_confidence_min` column. Routes: `GET /api/jobs/{job_id}/match-config`, `PUT /api/match-preferences`. Page at `/match-config/{job_id}`.

### 18. Match Strategy Ordering & Weights
Reorder/disable match strategies. `user_preferences.strategy_weights_json` column. Saveable pipeline configs via `POST/GET/DELETE /api/pipeline-configs`. Same page as #17.

### 19. Custom Output Folder Structure
Define folder patterns using variables (`{YYYY}/{MM}`, `{friend_name}/{type}`). Live preview of output paths. Routes: `GET/PUT /api/export-settings`, `POST /api/export-settings/preview-paths`. `user_preferences.folder_pattern` column. Page at `/export-config`.

### 20. Export Format Controls
JPEG quality, video codec, PNG compression, thumbnail generation. Covered by `export_settings_json` in the export-settings API (#19).

### 21. Dry Run / Preview Mode
Upload form "Dry Run" checkbox skips export phase. Dedicated summary page at `/dry-run/{job_id}`. Promote to full export via `POST /api/jobs/{job_id}/promote`. Results page shows "DRY RUN" banner when export was skipped.

---

## Group 4: Browse & Visualize (Features #22–27)

Gallery, conversations, timeline, map, duplicates, auto-albums.

### 22. Memory Browser Page
Gallery with thumbnails, metadata cards, filtering. Routes: `GET /api/jobs/{job_id}/gallery`, `GET .../gallery/html`. Page at `/browse/{job_id}`. Lazy-loaded via htmx.

### 23. Conversation Browser Page
Chat conversations with PNG previews and transcripts. Filter by friend, date, keyword. Routes: `GET /api/jobs/{job_id}/conversations`, `GET .../conversations/html`, `GET .../conversations/{id}/messages`. Page at `/browse/chats/{job_id}`.

### 24. Timeline Visualization
Interactive timeline with year/month/day drill-down. Color-coded by lane. Route: `GET /api/jobs/{job_id}/timeline-data`. Page at `/timeline/{job_id}`.

### 25. Map Visualization
Leaflet + OpenStreetMap with marker clustering. Filter sidebar. Route: `GET /api/jobs/{job_id}/map-data`. Page at `/map/{job_id}`.

### 26. Duplicate Detection & Merge
SHA-256 + perceptual hashing across jobs. Review and resolve duplicates. Routes: `GET /api/jobs/{job_id}/duplicates`, `POST .../duplicates/resolve`, `GET .../duplicates/html`. Page at `/duplicates/{job_id}`.

### 27. Fuzzy Vacation Album Auto-Creation
DBSCAN clustering on location + timestamp. Auto-name via reverse geocoding. CRUD + generate: `POST /api/jobs/{job_id}/albums/generate`, `GET/PUT/DELETE /api/albums/{id}`, `GET /api/albums/{id}/items`. Page at `/albums/{job_id}`.

---

## Group 5: Account & Quota Management (Features #28–32)

Tier enforcement, storage tracking, retention, slots, bulk upload.

### 28. Storage Quota Dashboard
Disk scan with by-lane breakdown, quota percentage, tier comparison, upsell prompts. Route: `GET /api/quota`. Page at `/quota`. Accessible from settings "VIEW QUOTA DASHBOARD" button. Tiers: Free 10 GB, Pro 50 GB.

### 29. Upload Size Limit Tiers
Free: 5 GB per upload. Pro: 25 GB. Enforced client-side (JS check) and server-side (`uploads.py`). Upload page shows tier badge and limit label. Route: `GET /api/upload-limits`.

### 30. Retention Period Control
Free: 30 days. Pro: 180 days. `retention_expires_at` column on `processing_jobs`. Job cards show color-coded countdown and "EXTEND" button for paid tiers. Routes: `POST /api/jobs/{id}/extend-retention`, `GET /api/jobs/{id}/retention`. Email warnings not yet wired.

### 31. Concurrent Job Slots
Free: 1 slot. Pro: 3 slots. Dashboard shows slot dot indicators, queue position, and tier badge. Route: `GET /api/slots`. Dashboard page computes active/queued counts from live DB queries.

### 32. Bulk Upload Support
Pro-only. Multi-file dropzone and job group badge when `tier_info.bulk_upload` is true. `job_group_id` column on `processing_jobs`. Routes: `GET /api/job-groups/{group_id}`, `GET /api/job-groups`. Page at `/job-group/{group_id}`.

---

## Group 6: Automation & Integration (Features #33–36)

API keys, webhooks, reports, scheduled exports.

### 33. API Access Keys
CRUD for API keys. Free users see lock icon + upgrade prompt. Pro users get full key management. Routes: `POST/GET/DELETE /api/keys`. Page at `/api-keys`. Tier-gated UI.

### 34. Webhook Notifications
Webhook CRUD + test endpoint. Supports Slack, Discord, email, custom HTTP. Routes: `POST/GET/PUT/DELETE /api/webhooks`, `POST /api/webhooks/{id}/test`. Page at `/webhooks`.

### 35. Job Report Downloads
Match report and asset report as JSON/CSV downloads. Results page "REPORTS" panel with three report cards. Routes: `GET /api/jobs/{id}/match-report`, `GET /api/jobs/{id}/asset-report`, `GET /api/jobs/{id}/report`.

### 36. Scheduled / Recurring Exports
Schedule CRUD with tier gate for free users. Routes: `POST/GET/PUT/DELETE /api/schedules`. Page at `/schedules`. Upgrade button is a `window.alert()` placeholder.

---

## Implementation Notes

- All tag editing is non-destructive — originals untouched, edits applied to copies
- Every metadata edit logged to `tag_edits` audit trail (who, when, old → new)
- Sidecar edits validate against XMP spec before writing
- GPS edits validate coordinate ranges
- Batch operations have preview-before-commit pattern
- The metadata power tools (Group 2) are what justify the pro price
