# Snatched v3 — Power User Experience Stories
## Agent B: The Power User Champion

**Agent Role**: Represents power users, photographers, data hoarders, multi-account users, and technical users who demand efficiency, control, and minimal hand-holding.

**Value Drivers**: One-click operations, keyboard shortcuts, batch processing, data density, reusable configurations, automation-friendly APIs.

---

## Story 1: Dashboard as Command Center
**As a** data hoarder managing 20+ Snapchat exports annually
**I want to** see job status, latest results, and next actions in a single view without navigation fatigue
**So that** I can stay in control and unblock myself quickly without clicking through results/download pages

**Current state**: Dashboard shows 3 stat cards and a list of job cards. Each job requires a "View Results" click to see summary; download is buried on a separate page.

**Proposed fix**:
- Add a compact 4th column to job cards (desktop): Quick stats badge showing "X matched / Y total | GPS: Z%"
- Add a "Download Latest" button on completed job cards (right-align, secondary style)
- Implement quick-action dropdown menu on each card (three dots): "View Results | Reprocess | Download | Delete"
- Show progress inline on running jobs: progress bar + "Phase 2/4 | 35%" instead of separate phase page
- Add a "Bulk Select" checkbox and a sticky footer action bar for batch operations (see Story 3)

**Priority**: P1 (high)

---

## Story 2: Keyboard-First Navigation
**As a** power user who lives in my keyboard
**I want to** navigate every major action via keyboard shortcuts without reaching for the mouse
**So that** I can process multiple exports in rapid succession without context-switching friction

**Current state**: Keyboard shortcuts exist for `?`, `/`, `D`, `R` in the design spec, but no shortcuts for upload, download, reprocess, or quick-access to recent jobs.

**Proposed fix**:
- Add global shortcuts:
  - `U` = Jump to /upload (from any page)
  - `Ctrl+Enter` = Submit upload form
  - `?` = Help modal (already spec'd, implement it)
  - `1/2/3` = Switch tabs on Results page (instead of Left/Right arrows)
  - `Ctrl+D` = Download latest results (from Dashboard)
  - `Shift+N` = New job (same as `U`)
- On Dashboard: `J` → Jump to job by typing ID (fuzzy search overlay)
- On Results: `K` = Open keyboard help modal
- Implement visible overlay when ? is pressed showing all active shortcuts
- Add accessibility annotation: all interactive elements show tooltip on hover (`[Alt+?]` style)

**Priority**: P1 (high)

---

## Story 3: Batch Operations Across Multiple Jobs
**As a** power user with a team plan running 10+ concurrent jobs
**I want to** select multiple jobs and perform bulk actions (reprocess, delete, download all)
**So that** I don't have to repeat the same operation 10 times

**Current state**: Each job is a separate card with individual action buttons. No multi-select capability.

**Proposed fix**:
- Add checkbox at the top-left of each job card (visible on desktop, toggle via `Shift+Click`)
- Implement sticky footer action bar when 1+ jobs selected:
  - "X jobs selected | [Reprocess Selected] [Download All] [Delete] [Clear Selection]"
  - Reprocess triggers a modal: "Select phases/lanes for all selected jobs" (dropdown: ingest/match/enrich/export)
  - Download All: Creates a ZIP archive of all selected job outputs
- Keyboard shortcut: `Ctrl+A` = Select all visible jobs on Dashboard
- Sorting on Dashboard: Click column headers to sort by: Name | Status | Date | Size | Match %
- Add a filter bar above job list: `[Status ▼] [Date Range ▼] [Min Match % ▼] [Clear Filters]`

**Priority**: P1 (high)

---

## Story 4: Upload Presets & Configuration Reuse
**As a** power user running the same pipeline 20 times a year (same phases, lanes, settings)
**I want to** save and recall upload configurations (phases, lane selection, EXIF options, GPS window)
**So that** I don't have to re-select the same options every time

**Current state**: Upload checkboxes are hidden in MVP. Users can't customize phases/lanes. No preset system.

**Proposed fix**:
- Create a new `Settings > Upload Presets` page
- Let users define presets with:
  - Name: "Memories + EXIF (Standard)" | "Full Pipeline" | "Chat-Only" | etc.
  - Phases: [Ingest] [Match] [Enrich] [Export] (checkboxes)
  - Lanes: [Memories] [Chats] [Stories] [Snap Pro] (checkboxes)
  - EXIF options: Burn overlays | Dark mode PNGs | XMP sidecars | GPS window (seconds)
- On Upload page: Add dropdown "Use Preset: [Standard] ▼" with quick-select buttons
- Allow preset export/import as JSON for team sharing
- Add preset list to /api endpoint for automation (/api/presets)
- Keyboard: `Ctrl+S` on upload page = Save current config as new preset

**Priority**: P2 (medium) — requires backend phase/lane selection feature first

---

## Story 5: One-Click Download from Dashboard
**As a** power user who just wants the output files, not the details
**I want to** download completed job results directly from the Dashboard job card
**So that** I skip the Results page entirely on subsequent processes

**Current state**: Download is only available from the Download page (/download/{job_id}), which requires Results page navigation first.

**Proposed fix**:
- Add a "Download" action button on completed job cards (primary color, right side of card)
- Clicking "Download" triggers a small overlay menu:
  - "Download Files as ZIP" (Downloads all output files)
  - "Download Metadata Only" (JSON/CSV summary)
  - "Copy Download Link" (Copies /api/download/{job_id} URL to clipboard)
- If already on Results page: Add a "Download Files" button in the sticky header (right side, after stat cards)
- Add Download progress to Dashboard: Show "Downloading..." state with progress bar overlay on card
- API endpoint: `GET /api/download/{job_id}?format=zip|metadata` (stream or redirect)

**Priority**: P1 (high)

---

## Story 6: The Correction Workflow as a Pipeline, Not Islands
**As a** power user correcting GPS, timestamps, or redacting sensitive data
**I want to** move sequentially through correction phases (GPS → Timestamps → Redact → Match Config) without returning to Results page each time
**So that** I stay in flow state and don't lose context between corrections

**Current state**: Results page lists 11 buttons (Reprocess, GPS Correction, Timestamps, Redact, Match Config, Browse, Chats, Timeline, Map, Duplicates, Albums). Each correction takes you to a separate page; to move to the next correction, you must go back to Results.

**Proposed fix**:
- Create a new `/corrections/{job_id}` wizard page with:
  - Left sidebar: Step indicator (1. GPS | 2. Timestamps | 3. Redact | 4. Match Config | Done)
  - Main area: Current correction step form
  - Navigation: [← Previous] [Next →] buttons (enabled/disabled based on current step)
  - All corrections saved to temp state; "Publish Corrections" applies all at once
- Each step shows progress (1/4, 2/4, etc.)
- Keyboard: `Tab` through form fields, `Ctrl+Right/Left` = Next/Previous step
- Add "Skip This Step" button for optional corrections
- Results page: Replace individual correction buttons with single "Open Corrections Wizard" button (or keyboard shortcut `C`)
- Each correction step should show a preview of changes before commit

**Priority**: P2 (medium)

---

## Story 7: Job Groups for Bulk Upload Batches
**As a** team/pro user uploading 5 related Snapchat exports (e.g., "Trip to Japan" = 5 people's exports)
**I want to** group them together and see their progress as a unit, with aggregate stats
**So that** I can manage related jobs as a project, not scattered cards

**Current state**: Each upload creates a separate job. No grouping concept exists.

**Proposed fix**:
- Add "Create Job Group" option on Upload page: modal asking "Group name?" (optional)
- If group name provided, subsequent uploads within same session auto-join the group
- Dashboard: Display group headers with expanded/collapsed state:
  - "Trip to Japan (5 jobs) | 4 completed, 1 running | Start date: Feb 24"
  - Click to expand: Show 5 job cards as sub-items
- Group-level actions: "Download All (as separate ZIPs)" | "Download as Single Archive" | "Archive Group" | "Delete Group"
- Group stats: Show aggregate "Total Matched: 1,234 / 2,500" and "Avg Match Confidence: 87%"
- API: `POST /api/job-groups` with `{"name": "...", "jobs": [ids]}`
- Bulk select (Story 3) respects groups: selecting a group header selects all jobs in it

**Priority**: P2 (medium) — pro/team tier feature

---

## Story 8: Advanced Match Configuration in Results
**As a** power user who knows the 6 match strategies and wants to tweak matching behavior
**I want to** re-run matching with different strategy weights or exclude certain strategies
**So that** I can chase better matches without re-ingesting or re-enriching

**Current state**: "Match Config" button on Results page exists in spec but details are unclear. No UI for strategy tuning.

**Proposed fix**:
- Create `/results/{job_id}/match-config` page (or modal overlay)
- Show 6 strategies with toggles + weight sliders:
  - Exact Hash (always on)
  - Filename Similarity (0-100% weight)
  - EXIF Date Match (0-100%)
  - GPS Proximity (0-100%)
  - Chat Context (0-100%)
  - ML Similarity (0-100%, if available)
- Add "Confidence Threshold" slider (only include matches above %)
- Show a preview table: "New results if applied: X matches recovered"
- Buttons: [Apply & Reprocess] [Reset to Defaults] [Save as Preset]
- Advanced: Collapsible section "Match Window Tolerances" (seconds for timestamps, meters for GPS)
- API: `POST /api/jobs/{job_id}/reprocess-match` with `{"strategies": {...}, "threshold": 75}`

**Priority**: P2 (medium)

---

## Story 9: API Keys and Automation Integration Visibility
**As a** power user building automation (Zapier, Make.com, home server cron job)
**I want to** easily see and manage API keys + webhook endpoints from the Dashboard
**So that** I don't have to bury myself in Settings and remember endpoints

**Current state**: API keys and webhooks are in Settings > API Keys and Settings > Webhooks (nested pages). Not visible from main Dashboard.

**Proposed fix**:
- Add an "Automation" quick-access card on Dashboard (pinned, optional):
  - "API Keys: [Show] | Webhooks: [Configure] | Schedules: [View]"
  - Show badge count: "3 keys" | "2 webhooks" | "1 schedule active"
- Add a tooltip/info panel: Click to expand showing:
  - First API key (truncated): "sk_live_abc123...def456" [Copy] [Rotate]
  - First webhook URL: "https://example.com/snatched" [Copy] [Test]
  - Scheduled jobs: "Every Sunday 2 AM (backup)" [Edit]
- Quick-create: `[+ New API Key]` [+ New Webhook]` buttons (links to Settings)
- Add an `/api/webhooks/test` endpoint for webhook testing
- Display last 5 API calls in card: "Last call: 2 hours ago | Result: Success"

**Priority**: P2 (medium)

---

## Story 10: Data Density in Results Tabs (Compact Mode)
**As a** power user with 5,000 matches, 8,000 assets, and 500 chats
**I want to** display more rows per page and customize columns shown
**So that** I can scan and find issues faster

**Current state**: Results Matches/Assets tabs show ~20 items per page. Columns are fixed. No way to show more data at once.

**Proposed fix**:
- Add a "Compact View" toggle in Results header (right side): [List View] [Compact View]
- Compact View:
  - Matches: Show 100 rows per page, hide confidence color (keep %), collapse Type column into icon
  - Assets: Show 100 rows per page, hide Size column, abbreviate file paths
  - Font size: 0.875rem (slightly smaller, still readable)
- Add "Columns" menu (gear icon):
  - Checkboxes for Snapchat | Confidence | Date | Type | Strategy (for debugging) | Size
  - Save column preference to user_preferences table
- Add "Export Results as CSV" link (exports current view or all rows)
- Sorting: Add secondary sort (Ctrl+Click column header = 2nd sort level)
- Row context menu (right-click): "Download This File | View in Browser | Copy Path"

**Priority**: P2 (medium)

---

## Story 11: Rapid Job Status from Dashboard Polling
**As a** power user monitoring 10 jobs, I want Dashboard to refresh job status faster (every 1s instead of 2s)
**I want to** jump directly to a specific job's progress page with a keyboard shortcut
**So that** I don't miss job completion notifications or phase changes

**Current state**: Dashboard polls every 2s. No way to jump directly to job progress.

**Proposed fix**:
- Add a Settings toggle: "Dashboard refresh interval" [0.5s] [1s] [2s] [5s] (power users often want faster)
- Add a "Desktop notifications" opt-in: Notify when job completes, fails, or reaches phase milestone
- Add "Jump to Job" overlay (keyboard `J`):
  - Shows searchable list of recent jobs (sortable by ID, date, status)
  - Pressing `J` + typing "123" jumps to /jobs/123/progress
  - Enter = Go | Escape = Close
- Add a "Notifications" badge on navbar (bell icon) showing unread job status changes
- API: `GET /api/jobs/{job_id}/progress?detailed=true` returns current phase, progress %, elapsed time

**Priority**: P3 (nice-to-have)

---

## Story 12: Reprocess Selective Lanes or Phases Without Full Reingestion
**As a** power user who wants to fix enrichment without waiting for re-match
**I want to** reprocess only specific phases (e.g., re-enrich and re-export, skip ingest+match)
**So that** I save time and only recompute what's needed

**Current state**: Reprocess button on Results page, but unclear if partial reprocessing is supported.

**Proposed fix**:
- Results page "Reprocess" button opens a modal:
  - Checkboxes: [x] Ingest | [x] Match | [x] Enrich | [x] Export
  - Default: All unchecked (show "What do you want to reprocess?")
  - Sub-option under Match: [x] Refresh match confidence scores
  - Sub-option under Enrich: [x] Re-fetch GPS | [x] Refresh display names
  - Sub-option under Export: [x] Rebuild chat PNGs | [x] Burn overlays
  - [Start Reprocess] button creates new job with selected phases only
- API: `POST /api/jobs/{job_id}/reprocess` with `{"phases": ["match", "enrich"], "lanes": ["memories"]}`
- Show time estimate: "This will take ~5 minutes" (based on historical job duration)

**Priority**: P2 (medium)

---

## Story 13: Export Results and Metadata in Multiple Formats
**As a** power user integrating with Immich, Nextcloud, or custom scripts
**I want to** export match results and metadata in JSON, CSV, or sidecar format
**So that** I can integrate the data into my own workflows

**Current state**: Download page shows file tree. No export of metadata results separately.

**Proposed fix**:
- Results page: Add "Export Data" button (in header, near Download Results):
  - Opens menu: "Export Matches as JSON | CSV | Export Assets as JSON | CSV | Export Summary Report as PDF"
  - "Matches as JSON": Includes all match data, confidence, strategies, GPS, dates
  - "Matches as CSV": Flattened table with headers
  - "Summary Report as PDF": Styled report with stats, charts, processing timeline
- Each export shows a toast with download status
- API: `GET /api/jobs/{job_id}/export?format=json|csv&type=matches|assets|summary`
- Add to Settings: "Default export format" preference (JSON / CSV)

**Priority**: P3 (nice-to-have) — valuable for power users building integrations

---

## Story 14: Correction History and Undo
**As a** power user who made a mistake in GPS corrections or redactions
**I want to** view a history of corrections and undo specific changes
**So that** I don't have to restart the entire job

**Current state**: No history of corrections. Once applied, changes are permanent.

**Proposed fix**:
- Create `/results/{job_id}/history` page showing:
  - Timeline of all corrections applied (GPS | Timestamps | Redact | Match Config)
  - Each entry: "Feb 24, 2:15 PM | GPS Correction | 234 locations updated | [View] [Undo]"
  - Clicking [View] shows the exact changes made
  - Clicking [Undo] reverts that specific correction (creates a note: "Undone Feb 24, 3:00 PM")
- Database: Add `corrections` table tracking each correction operation
  - Columns: job_id, correction_type, timestamp, user, changes_json, reverted_at
- API: `POST /api/jobs/{job_id}/corrections/{correction_id}/undo`
- Keyboard shortcut on Results: `Ctrl+Z` = Undo last correction
- Limit history to last 10 corrections per job

**Priority**: P3 (nice-to-have)

---

## Story 15: Smart Filtering and Saved Searches in Results
**As a** power user with 5,000 matches who wants to find problematic matches quickly
**I want to** filter by confidence level, strategy, date range, or missing data
**I want to** save these filters as named searches for future jobs
**So that** I can quickly spot and fix issues without scanning thousands of rows

**Current state**: Matches tab has sort and pagination, but no filtering.

**Proposed fix**:
- Add filter bar above Matches table:
  - [Confidence: ▼] → [50-60%] [60-70%] [70-80%] [80-90%] [90-100%] [Any]
  - [Strategy: ▼] → [Exact Hash] [Filename] [EXIF Date] [GPS] [Chat] [ML]
  - [Date Range: ▼] → Date picker
  - [Missing: ▼] → [GPS only] [Date only] [Both] [Any]
  - [Search: ________] → Fuzzy search on file names
- Filters are client-side if <100 items, server-side for pagination
- Add [+ Save Search] button:
  - Dialog: "Search name: Low confidence matches [Save]"
  - Saved searches appear in a dropdown: "My Searches: [Low confidence matches ▼]"
- Results table shows highlighted rows matching current filters
- Keyboard: `Ctrl+F` = Focus search box
- API: `GET /api/jobs/{job_id}/matches?filter={"confidence": [50, 60], "strategy": "filename"}`
- Saved searches stored in PostgreSQL (user_saved_searches table)

**Priority**: P2 (medium)

---

## Story 16: Multi-Format Asset Download and Preview
**As a** power user working with diverse file types (MP4, PNG, PDF chat exports)
**I want to** preview or download individual assets directly from Results
**I want to** bulk-select assets and download them as a ZIP
**So that** I don't have to download the entire output and extract manually

**Current state**: Download page shows file tree; individual downloads work, but no bulk asset selection.

**Proposed fix**:
- Results Assets tab: Add checkbox column (left of File ID)
- Bulk select: `[Select All on Page] [Select All (X rows)] [Clear Selection]` buttons appear when 1+ items selected
- Sticky footer (when items selected): "X assets selected | [Download Selected as ZIP] [Copy Paths]"
- Preview: Clicking an asset row (non-checkbox area) opens a modal:
  - Shows thumbnail (images) or metadata (for videos/docs)
  - Displays EXIF data if available
  - [Download] button
  - [Next / Previous] arrows to browse assets
- Right-click context menu on asset row: "Download | Preview | Copy Path | Open in New Tab"
- API: `POST /api/jobs/{job_id}/assets/download` with `{"asset_ids": [123, 124, 125]}`

**Priority**: P2 (medium)

---

## Story 17: Webhook Triggers and Scheduled Reprocessing
**As a** power user with automated backup workflows or integration with downstream systems
**I want to** define webhooks that fire when a job completes, and schedule automatic reprocessing
**So that** I can trigger actions in Zapier, a home server, or my backup system without manual intervention

**Current state**: Webhooks are spec'd but implementation details unclear.

**Proposed fix**:
- Create `/settings/webhooks` page:
  - List of configured webhooks with test buttons
  - Add webhook form:
    - URL: `https://example.com/snatched-webhook`
    - Events: [Job Completed] [Job Failed] [Phase Complete] (checkboxes)
    - Headers: Custom headers for auth (e.g., `Authorization: Bearer token`)
    - [Test Webhook] button: Sends test event
  - Recent webhook calls: Log showing timestamp, event, status, response
- Create `/settings/schedules` page:
  - Define recurring reprocessing schedules
  - Form: "Every [1 day / 1 week / Custom ▼] | Reprocess phases: [Ingest] [Match] [Enrich] [Export]"
  - Apply to: "All jobs | Jobs tagged: [Development ▼]"
  - [Save Schedule] → Creates cron job
- API: `POST /api/webhooks` | `GET /api/webhooks` | `DELETE /api/webhooks/{id}`
- API: `POST /api/schedules` | `GET /api/schedules` | `PUT /api/schedules/{id}`
- Webhook payload includes job details: `{"event": "job_completed", "job_id": 123, "stats": {...}}`

**Priority**: P2 (medium) — pro/team tier feature

---

## Story 18: Tagging and Metadata Organization for Job Management
**As a** power user running 50+ jobs per year across different Snapchat accounts and contexts
**I want to** tag jobs with metadata (person, trip, year, project) and filter Dashboard by tags
**So that** I can organize and find related batches without relying on date sorting

**Current state**: Dashboard shows jobs sorted by date. No tagging or metadata organization.

**Proposed fix**:
- Add tag system to each job:
  - Editable tags on job cards (click to edit, press Enter to save)
  - Pre-defined tag categories (optional):
    - Person: [Dave] [Ashley] [Sarah] [+New]
    - Context: [Personal] [Trip] [Work] [Archive] [+New]
    - Year: [2024] [2025] [2026] [+New]
  - Tags stored in PostgreSQL (job_tags table)
- Dashboard filters: Add [Tags: ▼] filter button next to status filter
  - Multi-select: "Show jobs tagged with: [Dave ☑] [Trip ☑]" (AND logic)
- Stat cards update based on active filters
- Search Dashboard with `Ctrl+T` = Tag search overlay
- Keyboard shortcut on job card: `T` = Add/edit tags
- API: `PATCH /api/jobs/{job_id}/tags` with `{"tags": ["dave", "2025", "trip"]}`
- Export/share: "Share filtered view" generates a unique dashboard link

**Priority**: P3 (nice-to-have) — valuable for long-term users

---

## Story 19: Comparative Analysis Across Multiple Jobs
**As a** power user comparing matches from 3 different uploads of the same Snapchat account
**I want to** view results side-by-side or merged
**So that** I can spot which matching strategy worked best or if re-processing improved results

**Current state**: Results page shows one job at a time. No comparison capability.

**Proposed fix**:
- Create `/compare` page accessible from Dashboard:
  - "Select up to 3 jobs to compare:" with checkboxes (extends bulk select feature)
  - Once 2-3 jobs selected, show comparison view:
    - Merged match table: Asset Name | Job 1 Confidence | Job 2 Confidence | Job 3 Confidence | Difference
    - Stat cards show comparison: "Job 1: 87% avg | Job 2: 91% avg | Job 3: 89% avg"
    - Highlight differences: Green if improved, red if degraded
    - Filter options: "Show only assets with different confidence" | "Show only matches in Job 1 but not Job 2"
  - Download comparison as CSV or PDF report
- Use case: User re-processes same upload with different match strategies and compares results
- API: `GET /api/compare?jobs=123,124,125`

**Priority**: P3 (nice-to-have)

---

## Story 20: Keyboard-Navigable Results Table and Smart Scrolling
**As a** power user scanning 5,000 matches for issues
**I want to** navigate the Matches table with arrow keys and jump to rows by index
**So that** I stay on the keyboard and don't fatigue from mouse scrolling

**Current state**: Matches table is scrollable but requires mouse. No keyboard navigation beyond Tab through links.

**Proposed fix**:
- Implement keyboard navigation in Matches/Assets tables:
  - Arrow Up/Down: Move between rows
  - Ctrl+Home / Ctrl+End: Jump to first/last row
  - Ctrl+G (Go): Prompt "Go to row: [___]" → Jump to that index
  - `/` (while in table): Enter search mode to filter table
  - `I` = Invert filter (show only rows NOT matching current filter)
  - Selected row is highlighted (blue border) and kept in viewport
  - Ctrl+C = Copy row data to clipboard (JSON or TSV format)
- Add "Jump to row" bar at top of table:
  - "Go to row: [1-5000 ▼]" with autocomplete (start typing asset name)
- Smart scrolling: Virtual scrolling if >1000 rows (only render visible rows)
- Accessibility: Announce "Row X of Y" when row focus changes

**Priority**: P3 (nice-to-have)

---

## Summary: Power User Priorities

| Priority | Stories | Theme |
|----------|---------|-------|
| **P0 (Critical)** | 1, 2, 5 | Dashboard efficiency, keyboard shortcuts, one-click download |
| **P1 (High)** | 3, 6 | Batch operations, correction workflow as pipeline |
| **P2 (Medium)** | 4, 7, 8, 10, 12, 13, 15, 17 | Presets, job groups, match tuning, data density, webhooks, filtering |
| **P3 (Nice-to-Have)** | 9, 11, 14, 16, 18, 19, 20 | API visibility, job status polling, correction history, asset management, tagging, comparison, table keyboard nav |

---

## Cross-Cutting Themes Addressed

1. **Workflow Efficiency**: Stories 1, 2, 5, 6, 11 reduce clicks and context-switching
2. **Batch Processing**: Stories 3, 7, 16, 17 enable handling multiple jobs/assets at scale
3. **Customization & Reuse**: Stories 4, 10, 15, 18 let users configure and remember preferences
4. **Data Density**: Stories 10, 20 pack more information per page without cognitive overload
5. **Automation Integration**: Stories 9, 17 expose APIs and webhooks for power users
6. **Correction Workflow**: Story 6 transforms isolated correction pages into a coherent pipeline
7. **Advanced Search/Filter**: Stories 15, 19, 20 help find and compare results quickly
8. **Developer-Friendly**: Stories 4, 9, 13, 17 provide APIs, exports, and webhooks for integration

---

## Implementation Recommendations for Team

1. **Start with P0 & P1** (Stories 1-6): Core power user experience
   - Dashboard redesign
   - Keyboard shortcut system
   - Batch select infrastructure
   - Correction wizard

2. **Next Phase (P2)**: Medium-complexity features that build on P0
   - Upload presets (requires backend phases/lanes UI)
   - Job groups and filtering
   - Advanced match configuration
   - Data export formats

3. **Polish Phase (P3)**: Nice-to-have quality-of-life features
   - Webhooks and automation
   - Tagging and comparison
   - Advanced table navigation

All stories assume the **existing Results page consolidation** (11 buttons → focused action buttons + action menus) to reduce visual noise and improve scannability.
