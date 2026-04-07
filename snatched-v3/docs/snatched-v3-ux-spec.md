# Snatched v3 — UX Product Specification
## "The Living Canvas" — Progressive Revelation Design

*Produced by GRAVITY vs GRUMPY debate, 2026-02-25*

---

## The User Story

Dave drops a zip file on the upload screen, and the job screen opens immediately
with a live progress band showing his archive being counted and fingerprinted —
file types sorting themselves into colored segments, duplicate clusters appearing
as darker density marks, the date range of his entire Snapchat life materializing
as a span of years. Before he finishes his coffee the ingest completes and a
countdown appears: "Continuing to Match in 10 seconds... [Pause & Review]." He
lets it ride. Matching runs, a gallery of thumbnails appears sorted by date — most
of them correctly placed, a few flagged yellow. He glances at the match rate badge
(94% green), decides it is fine, lets the Enrich phase auto-start. GPS pins bloom
onto the map as location history enrichment runs. He switches to the map view and
watches his last three years of travel populate. Enrich finishes, another countdown,
he lets Export run. Three minutes later the screen reads "4,847 files rescued" with
a download button and a folder breakdown. He clicks download. He is done. Total
active attention: under two minutes.

---

## Design Principles

1. **One evolving screen** — `/job/{id}` transforms through states. URL never changes.
2. **Auto-process with pause points** — Countdown interstitials between phases. Default: continue. Optional: pause & review.
3. **Data viz + browser split** — Abstract data band (always visible, shows full archive pattern) + interactive gallery panel below.
4. **View modes, not pages** — Gallery, Timeline, Map, Conversations are toggles within the same panel.
5. **Progressive revelation** — Data gets richer at each phase. Views unlock as data becomes available.
6. **Agency without obligation** — Every tool is accessible, nothing is forced.
7. **Phase health badges** — Green/yellow/red surfacing of issues at each phase.
8. **ETAs, not just counters** — "~3 minutes remaining" > "2,417/4,312"

---

## Screen States

### STATE: Ingesting

- **Phase**: Ingest running
- **Visual**: Full-width data viz band at top (~120px). Dark background, snap-yellow accent.
  Segmented bar fills left-to-right as files counted — segments colored by type (photos warm
  white, videos amber, chats steel blue, other muted grey). Duplicate density = darker saturation.
  Below: monospace stats row — file count ticking up, size accumulating, date range appearing.
  No gallery panel yet — just stats and subtle spinner.
- **Emotional beat**: Anticipation. "It is reading my life."
- **Interactions**: None required. Watch or walk away.
- **Pause point**: None — ingest is fast and nothing to review yet.
- **Auto-flow**: Completes → Match countdown interstitial.
- **Health badge**: Grey while running. Green on clean completion. Yellow if parse errors skipped (shows count). Red if ingest fails.

### STATE: Match Countdown Interstitial

- **Phase**: Ingest complete, Match not yet started
- **Visual**: Modal overlay. Centered, snap-yellow border, dark bg. Large countdown from 10.
  Primary button (large, snap-yellow fill): "Continue to Match →".
  Secondary (smaller, outline-only): "Pause & Review".
  Three ingest summary stats below: total files, date range, duplicate count.
- **Emotional beat**: "Here we go." Micro-moment of agency without requiring action.
- **Interactions**: Click Continue (start immediately) or Pause & Review (dismiss modal, paused state).
- **Auto-flow**: Countdown expires → Match begins.

### STATE: Matching

- **Phase**: Match running
- **Visual**: Header shows "Matching" + health badge. Data viz band stable. Match rate indicator
  appears below band — horizontal fill bar, snap-yellow, building. Gallery panel populates —
  thumbnails in date order. Unmatched = grey "?" placeholders. View mode tabs visible:
  Gallery (active), Timeline (dimmed: "Available after Match"), Map (dimmed: "Available after
  Enrich"), Conversations (dimmed: "Available after Enrich").
- **Emotional beat**: Recognition. Your actual photos appearing in chronological order for the first time.
- **Interactions**: Scroll gallery. Click thumbnails for asset detail. Cannot start corrections yet.
- **Health badge**: Green if match rate >85%. Yellow if 60-85%. Red if <60%.
- **Auto-flow**: Completes → Enrich countdown interstitial.

### STATE: Enrich Countdown Interstitial

- **Phase**: Match complete, Enrich not yet started
- **Visual**: Modal. Countdown. Primary: "Continue to Enrich →". Secondary: "Pause & Review".
  Stats: match rate (large, colored by health), total matched, total unmatched.
  Red badge adds: "Match rate below threshold — review recommended."
  Red state changes button to "Continue Anyway →".
- **Emotional beat**: Decision moment. Low match = important. High match = formality.
- **Interactions**: Continue, Pause, or access tools (Friends, Timestamps, Match Config).
- **Auto-flow**: Countdown expires → Enrich begins.

### STATE: Enriching

- **Phase**: Enrich running
- **Visual**: Gallery remains. Map tab activates with pulse animation as GPS pins arrive.
  Timeline tab activates. Conversations tab activates when display names resolve.
  GPS progress shown as secondary thin bar below main band.
- **Emotional beat**: Discovery. Map lighting up is the second major emotional hit.
- **Interactions**: Gallery browsable. Map view shows pins appearing live. Timeline browsable.
  Conversations browsable with resolved names.
- **Health badge**: Green if good GPS coverage. Yellow if low GPS. Red if GPS enrichment fails.
- **Auto-flow**: Completes → Export countdown interstitial.

### STATE: Export Countdown Interstitial

- **Phase**: Enrich complete, Export not yet started
- **Visual**: Modal. Countdown. Primary: "Export Files →". Secondary: "Pause & Review".
  Stats: matched count, GPS-tagged count, estimated export size, estimated time.
  Copy: "Files will be written to disk."
- **Emotional beat**: Commitment. Something permanent is about to happen.
- **Interactions**: Continue, Pause, or access tools (GPS Correction, Export Config, Dry Run, Presets).
- **Auto-flow**: Countdown expires → Export begins.

### STATE: Exporting

- **Phase**: Export running
- **Visual**: Progress bar with ETA. Real thumbnails replace previews as files land.
  Data viz band shows folder breakdown. Download button appears (greyed, "Preparing...").
- **Emotional beat**: Anticipation building to release. Real thumbnails = real files.
- **Interactions**: All views browsable. No pause — interrupting writes is dangerous.
- **Health badge**: Green. Yellow if write failures (count). Red if export aborts (reason + recovery).
- **Auto-flow**: Completes → Review state.

### STATE: Review (Final)

- **Phase**: All complete
- **Visual**: Header: "Rescued" + large count in snap-yellow: "4,847 files."
  Compact stats row. Data viz band fully stable. Download button: large, primary, snap-yellow.
  View modes all active. Folder breakdown accordion. "Start new job" link.
- **Emotional beat**: Satisfaction without fanfare. The rescue is complete.
- **Interactions**: Download. Browse all views. Access any correction tool. Start new job.

---

## "Holy Shit" Moments

1. **Gallery populates in date order during Match** — Your Snapchat life as a coherent timeline for the first time.
2. **GPS pins bloom on the map during Enrich** — Watch your travel history geo-reconstruct in real time.
3. **Real thumbnails replace placeholders during Export** — Abstract data becomes your actual photos.
4. **Date range appears during Ingest** — "2018 — 2024. Six years of your life."
5. **Archive density band shows your history** — Clusters of activity around trips, events, relationships visible as density patterns.

---

## Decision Points

| Decision | When | Why It Matters |
|----------|------|----------------|
| Pause before Match | Match countdown | Review file inventory, check duplicates, configure match settings |
| Pause before Enrich | Enrich countdown | Review match rate, fix friend names, correct timestamps |
| Override low match rate | Enrich countdown (red) | Acknowledge data quality limits |
| Pause before Export | Export countdown | Configure export paths, apply presets, correct GPS, preview dry run |
| View mode selection | Any state after Match | Explore gallery, timeline, map, or conversations |
| Download vs Browse | Review state | Take files or keep exploring |
| Corrections | Any pause point or Review | Higher data quality through manual fixes |

---

## Progressive Revelation Map

| Phase | What Appears | View Change |
|-------|-------------|-------------|
| Ingest running | File type segments, duplicate density, date range, size | Band fills and colors |
| Ingest complete | Health badge. Stats finalize. Countdown modal. | Stats freeze. Modal overlays. |
| Match running | Gallery panel. Thumbnails in date order. Match rate bar. | Empty → populating gallery |
| Match complete | Match rate locks. Timeline tab activates. Countdown. | Gallery complete. Modal. |
| Enrich running | Map tab activates (pulsing). GPS pins live. Names resolve. Conversations tab activates. | Map becomes live. Names replace IDs. |
| Enrich complete | Folder paths computed. Export config actionable. Countdown. | Folder tree appears. Modal. |
| Export running | Progress bar + ETA. Real thumbnails. Folder breakdown. Download button (greyed). | Thumbnails sharpen. Band → output view. |
| Export complete | Download button active. "Rescued" header. Stats finalize. | Download unlocks. Terminal state. |

---

## View Modes

### Gallery (default)
- **Data**: All assets, sorted by matched_date
- **Available**: During Match (populates live)
- **Interactions**: Scroll, click thumbnail → asset detail, filter by type/health/conversation, bulk select, batch edit

### Timeline
- **Data**: Assets grouped by month/year via matched_date
- **Available**: After Match complete
- **Interactions**: Vertical scroll through time, sticky month/year headers, jump-to-year sidebar, zoom (day/week/month/year)

### Map
- **Data**: Assets with GPS coordinates
- **Available**: During Enrich (populates live)
- **Interactions**: Pan/zoom, click pin → asset detail, date range slider, heatmap toggle, "fly to" top locations

### Conversations
- **Data**: Chat assets grouped by conversation with display_name
- **Available**: During Enrich (when display names resolve)
- **Interactions**: Conversation list sidebar, select → filtered asset grid, jump to timeline/gallery filtered

---

## Tools & Corrections

All accessible from pause points and Review state. Separate routes, return to `/job/{id}`.

| Tool | When | Purpose |
|------|------|---------|
| Friends | After Match pause | Map account IDs to human names before Enrich resolves them |
| GPS Correction | After Enrich pause or Review | Manually pin assets to locations |
| Timestamp Correction | After Match pause or Review | Override matched dates on specific assets |
| Duplicates | After Ingest pause or Review | Review SHA-256 clusters, choose what to keep |
| Albums | Review | Organize output into named albums |
| Export Config | After Enrich pause or Review | Set folder structure, naming, format options |
| Presets | After Enrich pause or Review | Save/load export config profiles |
| Match Config | After Ingest pause | Adjust match algorithm parameters (advanced) |
| Dry Run | After Enrich pause | Preview export structure without writing files |

---

## Existing Page Fate Map

| Page | Fate | Reason |
|------|------|--------|
| upload.html | KEEP | Entry point unchanged |
| job_progress.html | REPLACE with `/job/{id}` | Old progress page replaced by evolving screen |
| configure.html | ABSORB into pause points | Config now happens at countdown pauses |
| results.html | REPLACE with Review state | Review state of evolving screen replaces this |
| memory_browser.html | DEPRECATE | Gallery view mode subsumes this |
| timeline.html | ABSORB into Timeline view | View mode within `/job/{id}` |
| map.html | ABSORB into Map view | View mode within `/job/{id}` |
| conversation_browser.html | ABSORB into Conversations view | View mode within `/job/{id}` |
| download.html | ABSORB into Review state | Download is primary CTA in Review |
| asset_detail.html | ABSORB as side panel/modal | Overlay within `/job/{id}` |
| friends.html | KEEP | Tool, separate route |
| gps_correction.html | KEEP | Tool, separate route |
| timestamp_correction.html | KEEP | Tool, separate route |
| duplicates.html | KEEP | Tool, separate route |
| albums.html | KEEP | Tool, separate route |
| presets.html | KEEP | Tool, separate route |
| export_config.html | KEEP | Tool, separate route |
| match_config.html | KEEP | Tool, separate route |
| dry_run.html | KEEP | Tool, separate route |
| dashboard.html | KEEP | Job list, unchanged |
| settings.html | KEEP | App settings, unchanged |
| landing.html | KEEP | Entry page, unchanged |
| login.html | KEEP | Auth, unchanged |
| register.html | KEEP | Auth, unchanged |
| error.html | KEEP | Error boundary, unchanged |
| _job_cards.html | KEEP | HTMX partial for dashboard |
| _asset_rows.html | KEEP | HTMX partial for gallery |
| _match_rows.html | KEEP | HTMX partial for tools |
| _match_stats.html | KEEP | HTMX partial for stats |
| _batch_edit_modal.html | KEEP | HTMX partial for bulk edit |
| _xmp_viewer.html | KEEP | HTMX partial for EXIF display |

---

## Three User Flows

### Speed Run Mode (1 click, walk away)
1. Drop zip → select "Speed Run" → job screen opens
2. All phases run automatically. No countdowns, no gates.
3. User can watch (gallery populates, map fills in) or close the tab entirely
4. Return to find "Rescued — 4,847 files" + Download button
5. Click Download. Done.
- **Active clicks: 2** (upload + mode select). Everything else is automatic.

### Speed Run + Explore (watch while it runs)
1. Drop zip → select "Speed Run" → job screen opens
2. Phases run automatically, but user stays and watches
3. Gallery populates during Match → scroll through, find forgotten photos
4. Map tab pulses during Enrich → switch to Map → watch pins drop
5. Switch to Timeline → scroll through years
6. Export finishes → browse gallery with real thumbnails → Download
- **Active clicks: many, all optional.** Processing never pauses.

### Power User Mode (pause, review, correct, resume)
1. Drop zip → select "Power User" → job screen opens
2. Ingest completes → pauses at Match gate. Review file inventory, check duplicates.
3. Optionally open Match Config to adjust strategy weights.
4. Click "Start Match" → match rate 71% (yellow) → pauses at Enrich gate
5. Open Friends → map 2 account IDs to names. Open Timestamp Correction → fix 47 assets.
6. Click "Start Enrich" → GPS coverage low (yellow) → pauses at Export gate
7. Open GPS Correction → pin 12 assets. Open Export Config → set folder structure, save preset.
8. Selectively choose which items/lanes to export (only memories, skip chat, etc.)
9. Click "Export Files" → wait → Review → Download → verify samples
- **Active pauses: 3, full control over every phase**

---

## Design Decisions (Resolved 2026-02-25)

1. **Gallery: Modern virtual scroll** with stage-specific overlays. Different visual
   treatments per phase state (placeholder → matched → enriched → exported thumbnail).
   Not htmx pagination — proper virtual scroll with DOM recycling.

2. **Re-processing: User's choice, credit-gated.** Two options presented:
   - "Re-export affected files only" (cheaper, fewer credits)
   - "Full re-run from [phase]" (more credits, clean slate)
   Credits system required — reprocessing costs credits based on scope.

3. **Countdown: 10s default, configurable in Settings.** The countdown only appears
   in Speed Run mode. Power User mode pauses at every gate (no countdown).

4. **Data viz band: Pinnable.** Stays fixed at top of viewport while gallery scrolls
   beneath it. Always visible as the contextual anchor of the entire screen.

5. **"Rescued" count: Composite.** Sum of saved + stamped + exportable items.
   Depends on what was processed. Show breakdown: "X saved, Y GPS-tagged, Z exported."

6. **Long-running processing: SSE with resilience.** Real-world benchmarks:
   ~5GB export = ~1 hour processing, ~20GB = ~2 hours. SSE must handle reconnection
   gracefully for these durations. Polling fallback if SSE drops.

7. **Two modes: Speed Run vs Power User.** User picks at upload time:
   - **Speed Run**: One-click operation. All phases auto-run, no countdowns, no gates.
     Process everything. Download when done.
   - **Power User**: Pause at every gate. View options, edit, selectively export.
     Can choose to export only some items/lanes.
   Mode selection is a prominent toggle on the upload screen.
