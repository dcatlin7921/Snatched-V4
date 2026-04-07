# Agent B Stories — Unified Roadmap Mapping

**How Agent B's 20 Original Stories Map to the Unified Top 15 + Backlog**

---

## TIER 1: Critical Foundation (Top 15)

### B-1: Dashboard as Command Center ✅ RANK #2
- **Status**: In unified top 15
- **Priority**: P1
- **Effort**: MEDIUM (redesign, quick-action menus, progress bars)
- **Impact**: HIGH (core power user experience)
- **Synergy**: Enables B-3, B-5, B-7, B-9
- **Dependencies**: None
- **Design Notes**:
  - Quick-action dropdown menu on each job card
  - Download button visible on completed jobs
  - Sticky footer for bulk select (B-3)
  - Inline progress bars for running jobs
  - Consolidate 11 Results buttons into organized sections

---

### B-2: Keyboard-First Navigation ✅ RANK #5
- **Status**: In unified top 15
- **Priority**: P1
- **Effort**: MEDIUM (event listeners, help modal, overlay)
- **Impact**: HIGH (power user efficiency)
- **Synergy**: Unlocks B-6 (Ctrl+Right/Left for wizard), B-20 (arrow keys in tables), B-15 (saved searches)
- **Dependencies**: None
- **Design Notes**:
  - Global shortcuts: U (upload), D (dashboard), R (results), J (jump to job), C (corrections), ? (help)
  - Page-specific: Ctrl+D (download), Shift+N (new job), Ctrl+A (select all)
  - Visible help overlay when ? is pressed
  - Shortcuts only active when not typing in text field (context-aware)

---

### B-5: One-Click Download from Dashboard ✅ RANK #6
- **Status**: In unified top 15
- **Priority**: P1
- **Effort**: LOW (button + API endpoint)
- **Impact**: HIGH (saves 2+ clicks per job)
- **Synergy**: Works with B-1 (dashboard redesign)
- **Dependencies**: B-1 (Dashboard)
- **Design Notes**:
  - Download button on completed job cards
  - Overlay menu: Download ZIP | Download Metadata | Copy Link
  - Download progress indicator on card
  - API: GET /api/download/{job_id}?format=zip|metadata

---

## TIER 2: Power User Consolidation (Top 15)

### B-3: Batch Operations ✅ RANK #8
- **Status**: In unified top 15
- **Priority**: P2
- **Effort**: HIGH (checkbox infrastructure, sticky footer, state management)
- **Impact**: HIGH (time savings at scale)
- **Synergy**: Works with B-7 (Job Groups respect bulk select), B-16 (asset bulk select)
- **Dependencies**: B-1 (Dashboard redesign)
- **Design Notes**:
  - Checkbox column on dashboard job cards
  - Sticky footer: "X jobs selected | [Reprocess] [Download All] [Delete] [Clear]"
  - Keyboard: Ctrl+A (select all), Shift+Click (toggle)
  - Reprocess modal: "Select phases/lanes for all selected jobs"
  - Download All creates ZIP archive of all selected job outputs
  - Sorting/filtering on dashboard (Status | Date | Size | Match %)

---

### B-6: Correction Workflow as Pipeline ✅ RANK #9
- **Status**: In unified top 15
- **Priority**: P2
- **Effort**: HIGH (new page, state management, UX flow)
- **Impact**: HIGH (eliminates context switching)
- **Synergy**: Works with B-2 (Ctrl+Right/Left navigation), A-20 (contextual help)
- **Dependencies**: B-2 (Keyboard shortcuts)
- **Design Notes**:
  - New `/corrections/{job_id}` wizard page
  - Left sidebar: Step indicator (1. GPS | 2. Timestamps | 3. Redact | 4. Match Config | Done)
  - Main area: Current correction step form
  - Navigation: [← Previous] [Next →] buttons
  - All corrections saved to temp state; "Publish Corrections" applies all at once
  - Progress indicator: "2/4 steps complete"
  - Keyboard: Tab through fields, Ctrl+Right/Left (next/previous step)
  - Preview changes before committing

---

### B-4: Upload Presets ✅ RANK #12
- **Status**: In unified top 15
- **Priority**: P2
- **Effort**: MEDIUM (settings page, dropdown, API)
- **Impact**: MEDIUM-HIGH (time savings, especially for batch power users)
- **Synergy**: Works with B-3 (batch operations use same preset)
- **Dependencies**: None (but works well with B-3)
- **Design Notes**:
  - New `/settings/presets` page
  - Define presets: Name | Phases | Lanes | EXIF options
  - Upload page: "Use Preset: [Standard ▼]" dropdown
  - Keyboard: Ctrl+S (save current config as preset)
  - API: GET /api/presets, POST /api/presets, DELETE
  - Preset export/import as JSON for team sharing

---

## TIER 3: Medium-Priority Features (Backlog, P2-P3)

### B-7: Job Groups ⏳ BACKLOG (P2)
- **Status**: NOT in top 15 (valuable but lower priority than core power user features)
- **Priority**: P2
- **Effort**: MEDIUM (grouping logic, UI, API)
- **Impact**: MEDIUM (valuable for team/pro users with 20+ jobs)
- **Synergy**: Works with B-1 (dashboard), B-3 (bulk select respects groups)
- **Dependencies**: B-1, B-3
- **Design Notes**:
  - Create Job Group option on Upload page (optional modal)
  - Dashboard: Group headers with expand/collapse
  - Group-level actions: Download All, Archive, Delete
  - Group stats: Aggregate matched / total, avg confidence
  - API: POST /api/job-groups with {name, jobs}
  - Pro/Team tier feature

---

### B-8: Advanced Match Configuration ⏳ BACKLOG (P2)
- **Status**: NOT in top 15 (valuable but specialized, can ship later)
- **Priority**: P2
- **Effort**: MEDIUM (UI, tuning algorithm, preview)
- **Impact**: MEDIUM (valuable for users chasing better matches)
- **Synergy**: Works with B-1 (results page), B-15 (saved search strategies)
- **Dependencies**: None
- **Design Notes**:
  - `/results/{job_id}/match-config` page or modal
  - 6 strategies with toggles + weight sliders
  - Confidence threshold slider
  - Preview: "New results if applied: X matches"
  - Buttons: [Apply & Reprocess] [Reset] [Save as Preset]
  - API: POST /api/jobs/{job_id}/reprocess-match

---

### B-9: API Keys & Automation Visibility ⏳ BACKLOG (P2)
- **Status**: NOT in top 15 (valuable but not core MVP)
- **Priority**: P2
- **Effort**: MEDIUM (dashboard card, quick-access)
- **Impact**: MEDIUM (reduces Settings navigation)
- **Synergy**: Works with B-1 (dashboard card), B-17 (webhooks)
- **Dependencies**: B-1 (Dashboard)
- **Design Notes**:
  - Automation quick-access card on Dashboard (pinned, optional)
  - Show: API keys count | Webhooks count | Schedules count
  - Expand to show: First key (truncated), first webhook, active schedules
  - Quick-create buttons: [+ New API Key] [+ New Webhook]
  - Display last 5 API calls

---

### B-10: Data Density (Compact View) ⏳ BACKLOG (P2)
- **Status**: NOT in top 15 (valuable but can ship with NEW 1)
- **Priority**: P2
- **Effort**: MEDIUM (toggle, column customization, CSS)
- **Impact**: MEDIUM (scanning large result sets)
- **Synergy**: Works with NEW 1 (Lazy-load tables)
- **Dependencies**: None
- **Design Notes**:
  - Compact View toggle in Results header
  - 100 rows per page (vs. 20 default)
  - Hide/abbreviate columns, smaller font (0.875rem)
  - Columns menu: Checkboxes for visibility
  - Export as CSV
  - Secondary sort (Ctrl+Click)
  - Right-click context menu on rows

---

### B-12: Selective Reprocessing ⏳ BACKLOG (P2)
- **Status**: NOT in top 15 (valuable but not core MVP)
- **Priority**: P2
- **Effort**: MEDIUM (modal, phase selection, time estimate)
- **Impact**: MEDIUM (time savings when fixing specific phases)
- **Synergy**: Works with B-1 (results page), B-8 (match config)
- **Dependencies**: None (but useful with B-8)
- **Design Notes**:
  - Reprocess modal with phase checkboxes
  - Sub-options: Refresh scores, re-fetch GPS, rebuild chat PNGs, burn overlays
  - Time estimate: "This will take ~5 minutes"
  - Creates new job with selected phases only
  - API: POST /api/jobs/{job_id}/reprocess

---

### B-13: Export Metadata ⏳ BACKLOG (P3)
- **Status**: NOT in top 15 (valuable for integrations)
- **Priority**: P3
- **Effort**: MEDIUM (export formats, PDF rendering)
- **Impact**: MEDIUM (power users building integrations)
- **Synergy**: Works with A-19 (post-download guides)
- **Dependencies**: None
- **Design Notes**:
  - Export button on Results page
  - Formats: JSON | CSV | PDF summary report
  - Exports include: Matches, assets, metadata, stats
  - API: GET /api/jobs/{job_id}/export?format=json|csv&type=matches|assets|summary

---

### B-15: Smart Filtering & Saved Searches ⏳ BACKLOG (P2)
- **Status**: NOT in top 15 (valuable but specialized)
- **Priority**: P2
- **Effort**: MEDIUM (filter UI, saved searches table, API)
- **Impact**: MEDIUM (finding problematic matches quickly)
- **Synergy**: Works with B-2 (Ctrl+F shortcut), B-10 (compact view + filtering)
- **Dependencies**: None
- **Design Notes**:
  - Filter bar above Matches table
  - Filters: Confidence | Strategy | Date Range | Missing Data | Search
  - Save searches by name
  - Client-side if <100 items, server-side with pagination
  - Saved searches dropdown
  - API: GET /api/jobs/{job_id}/matches?filter={...}

---

### B-17: Webhooks & Scheduled Reprocessing ⏳ BACKLOG (P2, Pro Feature)
- **Status**: NOT in top 15 (valuable but tier-gated)
- **Priority**: P2
- **Effort**: HIGH (webhook system, cron scheduling, logging)
- **Impact**: MEDIUM (for power users building automation)
- **Synergy**: Works with C-3 (Pro feature badge), B-9 (automation visibility)
- **Dependencies**: None
- **Design Notes**:
  - `/settings/webhooks` page with list, add form, test button
  - Events: Job Completed | Job Failed | Phase Complete
  - Custom headers for auth
  - `/settings/schedules` page
  - Cron-like scheduling: Every 1 day/week/custom
  - Recent webhook calls log
  - API: POST/GET/DELETE /api/webhooks, POST/GET/PUT /api/schedules
  - Pro/Team tier feature

---

### B-16: Multi-Format Asset Download ⏳ BACKLOG (P2)
- **Status**: NOT in top 15 (valuable but specialized)
- **Priority**: P2
- **Effort**: MEDIUM (bulk select, preview modal, ZIP generation)
- **Impact**: MEDIUM (users working with diverse file types)
- **Synergy**: Works with B-1 (results page), B-3 (bulk select pattern)
- **Dependencies**: B-3 (bulk select infrastructure)
- **Design Notes**:
  - Checkbox column on Assets tab
  - Bulk select buttons: [Select All on Page] [Select All (X)] [Clear]
  - Sticky footer: "X assets selected | [Download as ZIP] [Copy Paths]"
  - Preview modal: Thumbnail/metadata, EXIF data, Next/Previous browse
  - Right-click context menu: Download | Preview | Copy | Open
  - API: POST /api/jobs/{job_id}/assets/download

---

### B-18: Tagging & Organization ⏳ BACKLOG (P3)
- **Status**: NOT in top 15 (valuable for long-term users)
- **Priority**: P3
- **Effort**: MEDIUM (tag system, filter, API)
- **Impact**: MEDIUM (organization at scale, 50+ jobs/year)
- **Synergy**: Works with B-1 (dashboard), B-3 (bulk select by tags)
- **Dependencies**: None
- **Design Notes**:
  - Editable tags on job cards
  - Pre-defined tag categories: Person | Context | Year
  - Dashboard filter: [Tags: ▼] multi-select
  - Tag search: Ctrl+T overlay
  - Keyboard on card: T (add/edit tags)
  - Shared dashboard links with tag filters
  - API: PATCH /api/jobs/{job_id}/tags

---

### B-19: Comparative Analysis ⏳ BACKLOG (P3)
- **Status**: NOT in top 15 (specialized use case)
- **Priority**: P3
- **Effort**: MEDIUM (comparison UI, merged tables)
- **Impact**: MEDIUM (debugging match strategies)
- **Synergy**: Works with B-1 (accessible from dashboard)
- **Dependencies**: None
- **Design Notes**:
  - `/compare` page
  - Select up to 3 jobs to compare
  - Merged table: Asset | Job 1 Confidence | Job 2 | Job 3 | Difference
  - Stat comparison: "Job 1: 87% avg | Job 2: 91% avg"
  - Filters: Show only differences, show only in Job 1 but not Job 2
  - Export as CSV or PDF report
  - API: GET /api/compare?jobs=123,124,125

---

### B-20: Keyboard-Navigable Tables ⏳ BACKLOG (P3)
- **Status**: NOT in top 15 (nice-to-have polish)
- **Priority**: P3
- **Effort**: MEDIUM (keyboard handling, virtual scrolling, ARIA)
- **Impact**: MEDIUM (scanning large result sets without mouse)
- **Synergy**: Works with B-2 (keyboard shortcuts), B-10 (compact view)
- **Dependencies**: None
- **Design Notes**:
  - Arrow Up/Down: Move between rows
  - Ctrl+Home/End: First/last row
  - Ctrl+G: Go to row index
  - `/`: Enter search/filter mode
  - `I`: Invert filter
  - Ctrl+C: Copy row (JSON or TSV)
  - Virtual scrolling for 1000+ rows
  - Announce "Row X of Y" for accessibility

---

### B-11: Smart Dashboard Polling ⏳ BACKLOG (P3)
- **Status**: NOT in top 15 (polish, useful but not core MVP)
- **Priority**: P3
- **Effort**: LOW (settings, notifications, refresh logic)
- **Impact**: LOW-MEDIUM (monitoring, engagement)
- **Synergy**: Works with B-1 (dashboard), NEW 3 (Smart Notifications)
- **Dependencies**: B-1 (Dashboard)
- **Design Notes**:
  - Settings toggle: "Dashboard refresh interval" (0.5s | 1s | 2s | 5s)
  - Desktop notifications opt-in
  - Jump to Job overlay: Keyboard J, fuzzy search
  - Notifications badge (bell icon)
  - API: GET /api/jobs/{job_id}/progress?detailed=true

---

### B-14: Correction History & Undo ⏳ BACKLOG (P3)
- **Status**: NOT in top 15 (safety net, valuable but lower priority)
- **Priority**: P3
- **Effort**: MEDIUM (history table, undo logic, DB schema)
- **Impact**: MEDIUM (safety, mistake recovery)
- **Synergy**: Works with B-6 (corrections pipeline)
- **Dependencies**: B-6 (Corrections)
- **Design Notes**:
  - `/results/{job_id}/history` page
  - Timeline of all corrections: Type | Date | Count | [View] [Undo]
  - [View] shows exact changes, [Undo] reverts specific correction
  - DB: corrections table tracking each operation
  - Keyboard: Ctrl+Z = Undo last correction
  - Limit to last 10 corrections per job

---

## SUMMARY: Agent B's 20 Stories Distribution

| Tier | In Top 15 | In Backlog | Count |
|------|-----------|-----------|-------|
| **P1 (Critical)** | B-1, B-2, B-5 | — | 3 |
| **P2 (Medium)** | B-3, B-6, B-4 | B-7, B-8, B-9, B-10, B-12, B-13, B-15, B-17, B-16 | 3 + 9 = 12 |
| **P3 (Nice-to-Have)** | — | B-11, B-14, B-18, B-19, B-20 | 5 |
| **TOTAL** | 6 | 14 | 20 |

---

## IMPLEMENTATION ROADMAP (Agent B's Perspective)

### Phase 1: Foundation (Weeks 1-3) — WITH B-1, B-2, B-5
- **Stories**: A-1 (First-Time Hero), B-1 (Dashboard), A-2 (Auth), A-3 (Drag-drop), B-2 (Keyboard), B-5 (Download), A-7 (Phase Labels)
- **Outcome**: Power users have efficient dashboard with keyboard shortcuts and one-click download
- **Team size**: 2-3 engineers

### Phase 2: Power User Consolidation (Weeks 4-6) — WITH B-3, B-6, B-4
- **Stories**: B-3 (Batch Ops), B-6 (Correction Pipeline), B-4 (Presets), C-3 (Pro Badges), A-12 (Empty State), A-19 (Guides), A-20 (Help)
- **Outcome**: Power users can batch process, configure presets, and move through corrections without leaving flow state
- **Team size**: 2-3 engineers

### Phase 3: Medium-Priority (Weeks 7-12) — BACKLOG
- **Stories**: B-7 (Groups), B-8 (Match Config), B-10 (Compact View), B-15 (Saved Searches), B-17 (Webhooks), B-16 (Asset Download)
- **Outcome**: Power users have advanced features for enterprise use cases
- **Team size**: 2 engineers (parallel work)

### Phase 4: Polish (Weeks 13+) — BACKLOG
- **Stories**: B-11 (Smart Polling), B-14 (Undo), B-18 (Tagging), B-19 (Comparison), B-20 (Keyboard Table Nav)
- **Outcome**: Refined power user experience with advanced tooling
- **Team size**: 1-2 engineers (QoL improvements)

---

**All Agent B stories map to unified roadmap. Top 15 includes 6 B-stories (Tier 1 + Tier 2 prioritization).**

