# Snatched v3 — Scan-First Monetization Plan

**Date**: 2026-03-23
**Status**: APPROVED — ready for Sprint 1

---

## User Flow

```
Upload (current system, zero options)
  → Auto-Ingest (scan only, FREE)
  → Intelligence Report page (your actual data counts)
  → Tier Selection + A La Carte
  → Pay (Stripe Checkout) or Download Free
  → Processing (match → enrich → export)
  → Download
```

## Tiers

### FREE — Memories + Dates
- Runs: ingest + match (date recovery)
- Memories lane only
- No GPS, no overlays, no EXIF enrichment beyond dates
- No chats, no stories
- Value prop: "Your 2,151 memories, properly dated"

### $4.99 — Memory Rescue (Dates + GPS + Overlays)
- Everything in Free, plus:
  - GPS coordinates embedded in EXIF
  - Overlays burned onto photos
  - Full EXIF enrichment on memories
- Still memories only — no chats/stories
- Value prop: "Camera-roll ready with locations"

### $9.99 — Complete Archive (Everything)
- All lanes: memories + chats + stories
- Full enrichment: dates, GPS, overlays, EXIF, XMP
- Chat transcripts + dark mode PNGs
- Value prop: "Your complete Snapchat history, preserved"

### A La Carte (individual add-ons, ~$15 total)
| Add-on | Price | What it unlocks |
|--------|-------|-----------------|
| Memories + dates | FREE | Base tier (always included) |
| GPS metadata | $2.99 | GPS coordinates in EXIF |
| Overlay burn | $1.99 | Snapchat overlays composited onto photos |
| Chat export | $3.99 | Chat transcripts + media + dark mode PNGs |
| Story archive | $1.99 | Stories with dates preserved |
| XMP sidecars | $1.99 | Lightroom/Photoshop metadata files |
| **Total a la carte** | **~$14.95** | |

The $9.99 bundle saves ~$5 vs buying everything separately.

## Architecture Notes

### Already Built (~80% of scan-first flow exists)
- `uploads.py:796` — creates ingest-only jobs
- `jobs.py:673` — pauses at "scanned" status
- `GET /configure/{job_id}` — reads scan stats from proc.db
- `POST /api/jobs/{job_id}/configure` — resumes with remaining phases
- `GET /api/jobs/{job_id}/scan-results` — returns memory/chat/story counts

### What's New (~500 lines)
1. Strip product selection from upload.html
2. Add tier/a-la-carte selection UI to configure.html
3. Pass `stats_json` to configure template
4. Stripe Checkout integration (new `routes/payment.py`)
5. Entitlement check in configure endpoint
6. Free tier path: match-only (dates), memories lane, skip GPS/overlays
7. DB migration: `job_tier`, `payment_status`, `add_ons` columns
8. Fix configure endpoint: `asyncio.create_task` → ARQ enqueue
9. Raw README.txt in free export explaining what's missing

### Free Tier Processing Path
- Ingest: full scan (always runs)
- Match: runs (recovers dates via 6-level cascade)
- Enrich: SKIPPED (no GPS, no overlay burn)
- Export: memories lane only, dates in filenames, no EXIF GPS

### Paid Tier Processing Path ($4.99)
- Ingest + Match: same as free
- Enrich: GPS lookup + overlay compositing
- Export: memories lane, full EXIF (dates + GPS + overlays burned)

### Full Tier Processing Path ($9.99)
- All phases, all lanes, all enrichment
- Same as current "Speed Run" mode

## Payment Integration
- Stripe Checkout (hosted page, zero PCI liability)
- Per-job pricing (not subscription)
- Dollars, not credits
- A la carte: individual Stripe line items, or single checkout with itemized receipt

## Deferred (Post-Launch)
- Guest uploads (test registration drop-off first)
- Priority processing queue (no congestion at current scale)
- Tip jar / post-download engagement
- GPS map export (tease in report, build later)
- Reprocess policy (1 free reprocess, $1.99 after)

## Sprint Plan
- **Sprint 1 (days 1-2)**: Upload simplification + configure page + free/paid paths + Stripe
- **Sprint 2 (days 3-5)**: Live Intelligence Report via SSE + scan TTL + polish
- **Sprint 3 (week 2-3)**: A la carte add-ons + priority queue if needed

## Key Metrics to Track
- Scan completion rate (drop-off during ingest wait)
- Free → paid conversion rate
- Tier split ($4.99 vs $9.99)
- A la carte vs bundle purchase ratio
- Registration wall abandonment rate (informs guest upload decision)
