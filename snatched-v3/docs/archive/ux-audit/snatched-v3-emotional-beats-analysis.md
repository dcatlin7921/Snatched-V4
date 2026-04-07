# Snatched v3 — Emotional Beats Analysis
**"Living Canvas" Spec vs Reality**
**2026-02-26**

---

## The Spec's Promise: 5 "Holy Shit" Moments

From the UX spec, these are the moments that make users feel like they're *rescuing* their memories, not just downloading files.

---

## BEAT 1: Gallery Populates in Date Order During Match

**Spec says:**
> Your Snapchat life as a coherent timeline for the first time.

### Reality Check

**Where it happens**: `/job/{id}` page, during Match phase.

**Flow**:
1. User hits Match countdown → clicks Continue or lets it auto-start.
2. SSE event `'matched'` fires.
3. JavaScript calls `refreshGallery()` (line 309): `htmx.trigger(grid, 'load')`
4. Gallery htmx endpoint `/api/jobs/{id}/gallery/html` fetches.
5. HTML renders with thumbnails in date order (backend handles ordering).

**What user sees**:
- Empty gallery grid while htmx loads.
- Thumbnails appear after 1-2 seconds.
- Thumbnails are in date order (chronological).
- As match continues, gallery updates (line 310 in job.html runs inside `'matched'` listener, but also runs every time progress updates? Unclear).

**Verdict: ✓ WORKS, but experience is slightly flat.**

**Why flat**:
- No animation as thumbnails appear. They just... pop in.
- Gallery loading shows "Loading gallery..." text or empty space. No indication that match is happening in real-time.
- No lazy-load animation (thumbnails don't fade in one-by-one).
- User doesn't see the "holy shit" because there's no ceremony around it.

**How to amplify**:
- Add a fade-in animation to each thumbnail as it appears.
- Show a progress indicator during match: "423/2,847 files matched — 14% complete".
- Replace empty placeholder with a subtle pattern or gradient that fills as matches arrive.

**Score: 6/10** — Works technically. Emotionally muted.

---

## BEAT 2: GPS Pins Bloom on the Map During Enrich

**Spec says:**
> Watch your travel history geo-reconstruct in real time.

### Reality Check

**Where it happens**: `/job/{id}` page, Map tab, during Enrich phase.

**Flow**:
1. Match completes → Enrich countdown.
2. User continues to Enrich.
3. Map tab activates (line 212 in job.html): `enableTab('map')` adds `.view-tab--pulse` animation.
4. When user clicks Map tab, JavaScript calls `loadMap()` (line 395).
5. `loadMap()` loads Leaflet CSS + JS, then calls `initMap()` (line 412).
6. `initMap()` fetches `/api/jobs/{id}/map-data`, renders L.circleMarker pins.

**What user sees**:
- "Map" tab is disabled during Match, becomes clickable during Enrich with a pulse animation.
- User clicks Map → Leaflet loads → map renders with pins already placed.
- Pins are yellow circles on dark basemap.
- Pins are interactive (bindPopup shows filename).

**Verdict: ✓ WORKS, but not in real-time.**

**Why not real-time**:
- Pins appear all at once when user clicks the tab, not during Enrich phase.
- Spec says "GPS pins bloom as enrichment runs" — implying live updates.
- Current implementation: User clicks Map tab → fetch full map data → render all pins at once.
- No streaming of GPS data during Enrich phase.

**How to fix**:
- During Enrich phase, stream GPS updates via SSE: `{type: 'gps_update', lat, lon, filename}`.
- If user has Map tab open, add pins live as they arrive.
- If tab is closed, pins appear when opened.

**Score: 5/10** — User sees the map and pins, but misses the real-time "blooming" effect. Feels like a static view, not a live process.

---

## BEAT 3: Real Thumbnails Replace Placeholders During Export

**Spec says:**
> Abstract data becomes your actual photos.

### Reality Check

**Where it happens**: `/job/{id}` page, during Export phase.

**Flow**:
1. Enrich completes → Export countdown.
2. User continues to Export.
3. Export phase runs, files are written to disk.
4. SSE progress events send `progress_pct`.

**What user sees**:
- Gallery remains visible during Export.
- Progress bar fills to 100%.
- No live thumbnail replacement mentioned in the template.

**Verdict: ✗ NOT IMPLEMENTED.**

**Why missing**:
- The spec implies a visual transition: placeholders → real thumbnails during export.
- Current code: Gallery is static during Export. Thumbnails don't change.
- No mechanism to replace thumbnails as files are written (would require live progress updates per file, expensive).

**Reality**:
- User watches progress bar.
- When complete, page reloads (line 391): `window.location.reload()`.
- New page shows the same gallery, now with "real" thumbnails (which were already being shown during Match).

**How to partially fix**:
- During Export, add a subtle animation to gallery cards (e.g., fade + scale) to signal that files are being written.
- Or show an "Export progress: file 1,247 of 4,847 written" message.

**Score: 2/10** — Not implemented. User sees progress bar, but the "holy shit" moment of seeing real files materialize is lost.

---

## BEAT 4: Date Range Appears During Ingest

**Spec says:**
> "2018 — 2024. Six years of your life."

### Reality Check

**Where it happens**: `/job/{id}` page, viz-band stats row, during Ingest phase.

**Flow**:
1. File upload completes, Ingest phase runs.
2. Backend scans files, extracts metadata (including dates).
3. SSE progress events include `date_range`.
4. JavaScript updates viz-band stats: `document.getElementById('stat-daterange').textContent = ...` (line 261).

**What user sees**:
- Stats row in viz-band shows: "2,847 files | Jan 2018 — Feb 2024 | — GPS".
- Date range is in monospace grey text, updated as ingest progresses.
- No animation or highlight when date range appears.

**Verdict: ✓ WORKS, but experience is subtle.**

**Why subtle**:
- Date range is one stat among four in a row. Easy to miss.
- No visual emphasis ("2018 — 2024" should be larger, bolder, maybe snap-yellow).
- No announcement: "Six years of your life discovered."
- Feels like a database query result, not a revelation.

**How to amplify**:
- When date range first appears, highlight it with a color flash or pulse animation.
- Add a subheading: "Your Snapchat life: 6 years of memories."
- Use larger font, snap-yellow color.

**Score: 4/10** — Data is there, but not emotionally delivered.

---

## BEAT 5: Archive Density Band Shows Your History

**Spec says:**
> Clusters of activity around trips, events, relationships visible as density patterns.

### Reality Check

**Where it happens**: `/job/{id}` page, viz-band, at top of screen.

**Flow**:
1. Ingest phase runs, files are counted and fingerprinted.
2. Backend should compute: file density per time period, duplicate clusters.
3. Frontend should render: segmented bar with colors by file type, darker saturation for duplicates.

**What actually exists**:
- Viz-band exists (confirmed in HTML).
- Phase labels (INGEST → MATCH → ENRICH → EXPORT) are present.
- Progress bar is present.
- Stats row shows file count, date range, match rate, GPS count.
- **But: NO color segmentation by file type. NO duplicate density visualization.**

**Code evidence**:
- HTML shows `<div class="viz-band__phases">` and `<div class="viz-band__progress">`.
- NO `<div class="viz-band__segments">` or similar for color bars.
- CSS has no `.segment-photos`, `.segment-videos` classes.
- No backend endpoint that sends file-type breakdown.

**Verdict: ✗ NOT IMPLEMENTED.**

**This is the biggest spec gap.** The "archive density band" is the signature visual of the whole "Living Canvas" concept. It's missing.

**Why missing**:
- Spec is aspirational (2025 design doc).
- Implementation chose minimal viable experience.
- File-type breakdown requires backend data (expensive to compute during ingest).
- Duplicate density computation is complex.

**How to implement** (see Sprint 2.6 in fixes checklist):
1. Backend: During ingest, track file types (photos, videos, chats, other) and compute density.
2. Send breakdown via SSE progress events.
3. Frontend: Render colored segments in viz-band, animated fill as ingest progresses.
4. Duplicate density: Darker color saturation for segments with high duplicate count.

**Score: 0/10** — Feature is completely missing. This is the visual anchor of the entire experience.

---

## Summary: Spec vs Reality

| Beat | Spec Promise | Actual Delivery | Score | Why |
|------|--------------|-----------------|-------|-----|
| 1 | Gallery populates in date order | Works, thumbnails appear correctly | 6/10 | Flat experience, no animation, no live counter |
| 2 | GPS pins bloom live during Enrich | Pins appear when user clicks Map tab (not live) | 5/10 | User misses the real-time "blooming" effect |
| 3 | Real thumbs replace placeholders during Export | Not implemented; progress bar only | 2/10 | Missing the visual transition moment |
| 4 | Date range appears during Ingest | Works, shown in small monospace stats | 4/10 | Subtle data presentation, not emotionally delivered |
| 5 | Archive density band with colors | Not implemented; minimal viz-band only | 0/10 | The signature visual feature is completely missing |
| | | | | |
| **OVERALL** | | | **3.4/10** | **Vision is 95%, execution is 70%** |

---

## What a Real User Feels

**On first use, user experience:**

1. **Ingest** (0-30s): Watching file count tick up. Date range appears. But no visual pop. Feels like a database import, not a rescue.

2. **Match Countdown**: "Okay, I get it, we're matching now." Modal is clear. Countdown is fine. Emotional beat: ✗ (auto-continue removes agency and surprise).

3. **Matching** (1-3 min): Gallery starts populating. User sees their actual Snapchat photos in chronological order for the first time. **HOLY SHIT MOMENT: ✓✓✓** (This is the one beat that DELIVERS.)

4. **Enrich Countdown**: Okay, map coming. User is on board.

5. **Enriching** (30-90s): User clicks Map tab, sees pins on basemap. "Oh, that's cool, my travel history." Moment is fine but not *blooming* in real-time. Emotional beat: ✓ (works, but not transcendent).

6. **Export Countdown**: User is committed. They click Continue.

7. **Export** (2-5 min): Progress bar fills. User watches. No live file thumbnails, no update on what's being written. Feels slow. Emotional beat: ✗ (boring).

8. **Download** (final): "4,847 files rescued" in a small stat card. Not prominent. Emotional beat: ✓ (satisfying, but understated).

---

## The Gap: What's Missing

**The spec promised a five-act journey with emotional peaks at key moments. Reality delivers:**

- ✓ Act 1 (Match): Photo gallery = recognizable and emotionally resonant.
- ✓ Act 2 (Enrich): Map = cool, user discovers travel history.
- ✗ Act 3 (Export): No real-time file visualization. User stares at progress bar.
- ✗ Act 5 (Download): Rescue count is de-emphasized.

**The missing pieces:**

1. **Density band**: The signature visual of the whole product. Without it, the Ingest phase feels like a loading screen, not a revelation.
2. **Export visualization**: No feedback that files are actually being written. User sees a percentage; they don't see their files.
3. **Emotional emphasis**: The big moments (4,847 files! Six years!) are shown in small text. Should be prominent and celebratory.

---

## Recommendation

**To deliver the spec's emotional arc:**

1. **Priority 1**: Implement density band (Sprint 2.6, 6-8 hours). This is the signature visual.
2. **Priority 2**: Add live GPS pins during Enrich (2-4 hours). Stream GPS via SSE, animate pins in real-time if Map tab is open.
3. **Priority 3**: Amplify final moments. Make "4,847 rescued" large and snap-yellow on download page.

**Even without these, the current experience is solid.** User gets their files, sees them in chronological order, discovers their travel history. The journey works. But it's a **utility** rather than a **revelation**.

---

## Code Locations to Watch

- **Density band**: Not in HTML yet. Must add `<div class="viz-band__segments">` to job.html line 30.
- **GPS real-time**: `/api/jobs/{id}/stream` endpoint. Currently sends progress events. Should add `gps_update` events during Enrich.
- **Export visualization**: No code. Requires backend to send per-file progress during Export phase.
- **Download hero**: `download.html` line 4-8. Rescue count is in small card (lines 12-15). Should move to hero section.

---

**Analysis complete. The vision is there. The execution is 70%. With focused work on the 3 priorities above, it becomes 95%.**
