# Snatched v3 UX Consensus — Final Implementation Stories

**Status**: ✅ CONSENSUS COMPLETE (Agent A, B, C Aligned)
**Date**: 2026-02-24
**Scope**: Phase 1 (MVP) simplification — 5-8 core stories reorganizing existing pages
**No new features. No new pages. Reorganize to make 4-click happy path obvious.**

---

## Executive Summary

After debating 60 user stories across 3 personas (Power User, New User, Product Strategist), all agents align on a single principle:

> **Hide power features until users feel core value. Then unlock them.**

The app already has all the buttons, modals, and configuration options. This consensus reorganizes them into a **progressive disclosure** model:
- **Phase 1 (Weeks 1-3)**: Clean, guided happy path (Upload → Process → Download)
- **Phase 2 (Weeks 4-6)**: Power user features revealed (Keyboard shortcuts, batch operations, presets)
- **Phase 3 (Weeks 7+)**: Advanced features and monetization (Automation, filtering, team features)

These 6 stories are ALL the changes needed to Phase 1. Everything else remains; it just moves or becomes conditional.

---

## Story 1: Simplify Dashboard for New Users

**Page**: `/dashboard`
**Problem**: Dashboard shows 13 sticky header buttons (Reprocess, GPS, Timestamps, Redact, Match Config, Browse, Chats, Timeline, Map, Duplicates, Albums, Reports, Download) overwhelming new users who just want to see results.

**Change**:
- **Sticky header shows only**: Status badge, Job title, [View Results] button, [Download] button
- **Advanced options move to**: Secondary menu (hamburger icon ⋯) under "Tools" — only visible *after* first export
- **For new jobs**: Hide hamburger entirely until job completes
- **Tab structure preserved**: Keep "Summary | Matches | Assets | Timeline | Map" tabs; add new "Corrections" tab (hidden by default)

**Power user access**: Hamburger menu reveals all 13 buttons grouped as: "Corrections", "Diagnostics", "Export", "Browse". Keyboard shortcut `?` shows shortcut cheat sheet.

**Implementation notes**:
- No database changes; no API changes
- Pure frontend conditional visibility (check `job.user_export_count < 1`)
- Tab visibility controlled via template flag `show_advanced_tabs`

---

## Story 2: Hide Advanced Upload Options Behind "Advanced Settings"

**Page**: `/upload`
**Problem**: Upload form exposes phase checkboxes (Ingest/Match/Enrich/Export), GPS window slider (30s–1800s), dry-run toggle — all visible to a user who has never processed a job before.

**Change**:
- **New user sees only**: Single ZIP input, "Upload & Process" button, help text linking to export instructions
- **Advanced settings collapse**: New [⚙️ Advanced Settings] toggle (below submit button)
- **When toggled**: Reveals phases, GPS window, dry-run, match lanes
- **Default behavior**: All four phases enabled (no user choice needed)
- **Persistence**: Store toggle state in localStorage so returning users see expanded form

**Power user access**: [⚙️ Advanced Settings] expands inline; keyboard shortcut `A` toggles it.

**Implementation notes**:
- No database changes
- Pure frontend checkbox + collapse/expand
- localStorage key: `upload_show_advanced_{username}`

---

## Story 3: Make Results Page Walkthrough Optional & Skippable

**Page**: `/results/{job_id}`
**Problem**: New user lands on Results page with 13 buttons but doesn't understand what "matches" or "confidence" or "assets" means.

**Change**:
- **First visit to Results page**: Show optional 4-card tour (non-blocking overlay)
  - Card 1: "What are matches?" (explains file-to-memory matching)
  - Card 2: "Confidence score" (0–100%, what it means, when to trust)
  - Card 3: "Assets vs. Metadata" (photos/videos vs. dates/locations)
  - Card 4: "Ready to download?" (CTA to Download button)
- **Tour is skippable**: [Next] [Skip] buttons; auto-skip if user clicks any tab after 5 seconds
- **Tour state**: Stored in database (`user_preferences.results_tour_seen`)
- **Repeatable**: [?] help icon in header re-shows tour
- **Not shown again**: Once user completes tour, never shows unless explicitly requested

**Power user access**: [?] icon in top-right always shows tour; keyboard shortcut `?` toggles help.

**Implementation notes**:
- Add `results_tour_seen` boolean to `user_preferences` table
- Tour overlay component (non-modal, allow background interaction)
- Track via localStorage + DB for multi-device consistency

---

## Story 4: Collapse Settings Into Account & Safety Zones

**Page**: `/settings`
**Problem**: Settings page is a full SaaS admin panel: API keys, webhooks, scheduled exports, export config, tier tables, processing preferences, danger zone — all on one page. New users see this and think they need to configure everything before uploading.

**Change**:
- **Hide everything from new users**: Settings page shows only [Account] tab until user completes 2+ exports
- **Account tab includes**: Profile picture, email, storage meter, tier indicator (moved from dashboard), "Help & FAQ" link
- **Advanced tabs appear conditionally**:
  - After 2+ exports: [Advanced Processing], [Webhooks & Automation], [Export Templates]
  - After Pro signup: [API Keys], [Team Management], [Scheduled Jobs]
  - Always available: [Danger Zone] (collapsible, requires password confirm to expand)
- **Danger Zone**: Moved to bottom, collapsed by default, contains "Delete account", "Clear all jobs", "Export data"

**Power user access**: All tabs visible immediately for users with `tier == pro` or `jobs_count > 5`.

**Implementation notes**:
- Add feature flag: `user_preferences.show_advanced_settings`
- Compute visibility: `show if tier==pro OR job_count >= 2`
- No data model changes; purely view-layer conditional rendering

---

## Story 5: Make Corrections Workflow Optional, Not Mandatory

**Page**: `/results/{job_id}` → New "Corrections" tab (optional)
**Problem**: 13-button Results header includes separate buttons for GPS Correction, Timestamps, Redact, Match Config — scattered controls that feel overwhelming to new users.

**Change**:
- **Remove from sticky header**: Delete individual buttons for GPS/Timestamps/Redact/Match Config
- **Add new Results tab**: [Summary | Matches | Assets | Corrections*] (* tab only shows when needed)
- **Corrections tab content**:
  - Grouped into a wizard-like interface: 4 sections (GPS Window → Timestamps → Redact → Match Config)
  - Each section is collapsible; user works through them sequentially or skips any
  - Submit button: "Reprocess with corrections" (single button, bottom)
- **Visibility**: Tab only appears if:
  - User has already viewed Results page *and* wants to refine (not shown until they interact with Matches tab)
  - OR user clicks [Refine Results] button in Summary tab
- **For new users**: This workflow is optional and discovery-based, not mandatory

**Power user access**: Corrections wizard is always accessible via keyboard shortcut `R` (refine). Batch operations (Story 6 Phase 2) apply corrections across multiple jobs.

**Implementation notes**:
- Rename current correction buttons to single "Corrections" tab template
- Add boolean to job model: `has_viewed_matches` (set when user clicks Matches tab)
- Tab visibility: `show if has_viewed_matches OR clicks_refine_button`

---

## Story 6: Progressive Disclosure of Nav & Feature Gates

**Page**: Global navigation (all pages)
**Problem**: Navigation bar has 8 links (Upload, Dashboard, Friends, Presets, Schemas, Export, Settings, Quota), and every power feature is always visible with "Pro Lock" badges, overwhelming new users.

**Change**:
- **Default nav for new users** (< 2 exports): [Dashboard] [Upload] [Settings] [Help]
- **After 2+ exports, reveal**:
  - [Presets] — reusable upload configurations
  - [Teams] — shared jobs (if tier == pro)
  - [Automation] — webhooks, scheduled exports (if tier == pro)
- **Pro feature badges**:
  - Remove yellow "lock" teasing from basic page
  - Show gray disabled state only when user clicks a Pro-gated feature
  - Modal appears: "This is a Pro feature" + [Upgrade] CTA (no banner or constant reminder)
- **Quota indicator**: Move from nav to Settings > Account > "Storage" meter (not nav noise)

**Power user access**: All nav links visible if `tier == pro` or `job_count > 10`. Keyboard shortcut `N` opens nav menu on mobile.

**Implementation notes**:
- Add `user_preferences.nav_visibility_level` ('basic' | 'intermediate' | 'advanced')
- Compute based on: `tier` + `export_count` + `first_seen_date`
- Update nav template to use `{{ user.nav_visibility_level }}`

---

## Story 7: One-Click Download from Dashboard (With Direct Download Option)

**Page**: `/dashboard` and `/results/{job_id}`
**Problem**: Happy path is too long: Dashboard → View Results (13 buttons) → Find Download button → Download. New user wonders "Where are my files?"

**Change**:
- **From Dashboard job card**: Add prominent [Download] button (green, primary CTA color) next to [View Results]
  - Clicking [Download] goes directly to file tree view (currently at `/download/{job_id}`)
  - No need to click Results first
- **From Results page Summary tab**: Add floating [Download] button (sticky, bottom-right) that's always visible
  - Click → opens file tree in modal or new page
- **File tree UX**: Show organized folder structure with EXIF metadata embedded, total size, archive option
- **One-click archive**: [Download All as ZIP] creates archive on-demand (no pre-zipping)

**Power user access**: Keyboard shortcut `D` downloads current job. Batch download (Story 6 Phase 2) requires selecting multiple jobs.

**Implementation notes**:
- Add button to job card template: `<button onclick="location.href='/download/{job.id}'">Download</button>`
- Floating button via sticky footer on Results page
- Archive generation via background task (store in /tmp, serve via `/api/jobs/{id}/download-zip`)

---

## Story 8: Empty States & Progress Feedback (Reduce Anxiety)

**Page**: `/dashboard`, `/results/{job_id}`, `/upload` (async state)
**Problem**: Users don't know what happens after clicking "Upload & Process". No progress feedback → user leaves thinking it failed.

**Change**:
- **Upload page after submission**:
  - Don't redirect immediately
  - Show overlay: "✓ Upload complete! Processing now..." (non-blocking, can dismiss)
  - Auto-redirect to Dashboard in 3 seconds with [View Progress] link
  - If user dismisses, keeps status message in sticky header
- **Dashboard empty state** (no jobs yet):
  - Large centered CTA: "Welcome! Ready to rescue your Snapchats?" with [Upload Export] button
  - Below: "Takes 10-30 minutes. You'll see progress here."
- **Job progress tracking**:
  - Show "Phase 2 of 4" progress subtitle
  - Show elapsed time + estimated time remaining
  - Log terminal shows live phase updates (existing feature, no change)
- **Results page empty state** (job failed or no matches):
  - Clear error message (plain English, not technical)
  - Next steps: [View Logs], [Retry with Different Settings], [Contact Support]

**Power user access**: Keyboard shortcut `P` goes to job progress page. Settings > Advanced has toggle for "Show progress notifications" (enable for desktop notifications).

**Implementation notes**:
- Add toast notification library (Pico-compatible, no JS framework needed)
- Job progress page already exists; just ensure messages are clear
- Empty state components: reusable `<EmptyState title="" cta="" />`

---

## Implementation Checklist (Phase 1)

| Story | Files to Change | Estimated Effort | Notes |
|-------|-----------------|------------------|-------|
| Story 1: Dashboard | `templates/dashboard.html`, `app/routes/pages.py` | 3 hours | Frontend conditional visibility |
| Story 2: Upload Advanced | `templates/upload.html`, static JS | 2 hours | Collapse/expand toggle + localStorage |
| Story 3: Results Tour | `templates/results.html`, `models.py` add field, `app/routes/api.py` | 4 hours | Tour overlay + DB flag |
| Story 4: Settings Zones | `templates/settings.html`, `app/routes/pages.py` | 2 hours | Tab visibility logic |
| Story 5: Corrections Tab | `templates/results.html`, `app/routes/pages.py` | 3 hours | Move buttons to tab, simplify sticky header |
| Story 6: Progressive Nav | `templates/base.html`, `app/routes/pages.py` | 2 hours | Nav visibility based on user state |
| Story 7: Direct Download | `templates/dashboard.html`, `templates/results.html` | 2 hours | Button routing to `/download/{id}` |
| Story 8: Empty States | `templates/*.html`, static JS | 3 hours | Toast messages + empty state components |
| **Total** | — | **21 hours** | ~3-4 days for one developer |

---

## Metrics for Success (Phase 1)

After implementing these 8 stories, measure:

| Metric | Target | How |
|--------|--------|-----|
| **Time to first download** | <15 min from upload | Analytics event: "download_started" |
| **First-export completion** | 85%+ of signups → successful download | Session funnel: upload → process → download |
| **New user confusion** | <5% report "where are my files?" | Feedback form on Settings > Help |
| **Support ticket rate** | <10% of new users | Zendesk ticket tracking |
| **Corrections workflow discovery** | 30%+ of users find it | Analytics: Results page tab clicks |
| **Keyboard shortcut usage** | (Phase 2 metric, not Phase 1) | — |

---

## Conflicts Resolved (How We Got Here)

### Conflict 1: Sticky Header Overload
- **Agent B (Power User)** wanted all 13 buttons always visible for keyboard + quick access
- **Agent A (New User)** wanted only Download visible, hide the rest
- **Resolution**: Hide by default, show in hamburger menu after first export (timing compromise)

### Conflict 2: Settings Complexity
- **Agent C (Product Strategist)** wanted pricing gates and tier info on Settings immediately
- **Agent A** wanted Settings invisible to new users
- **Resolution**: Show only Account tab until 2 exports, then progressively reveal (progressive disclosure)

### Conflict 3: Results Page Guidance
- **Agent B** wanted optional correction wizard built into Results workflow
- **Agent A** wanted guided tour explaining what "matches" means first
- **Resolution**: Add tour (Story 3) first, then optional corrections tab (Story 5) when user is ready

### Conflict 4: Feature Visibility Timing
- **Agent C** wanted Pro teasing and monetization on first page
- **Agent A** wanted zero monetization pressure until user feels value
- **Resolution**: Show Pro features only after 2 exports; gentle pitch with gray disable (not yellow tease)

### Conflict 5: Power User Efficiency
- **Agent B** wanted batch operations, keyboard shortcuts, presets from day 1
- **Agent A** wanted them hidden until user is ready
- **Resolution**: Build them now (they're in the code), hide them until Phase 2 feature flag

---

## Key Design Principles Applied

1. **Progressive Disclosure**: Features hidden by default, revealed as user capability increases
2. **Value Before Ask**: User must download successfully before seeing pricing or advanced options
3. **One Path to Success**: For new users, the happy path should be obvious (Upload → Process → Download)
4. **Honesty Over Manipulation**: Gray disable instead of yellow tease; no fear-based messaging
5. **Timing Beats Tone**: Same feature works if timed right, fails if premature
6. **Reduce Cognitive Load**: Sticky header shows 2 buttons, not 13; Settings has 1 tab, not 8

---

## What's NOT in These Stories (Intentional)

- No new features or pages (all existing, just reorganized)
- No database schema changes (use `user_preferences` for flags)
- No new dependencies or libraries (use Pico CSS + vanilla JS)
- No monetization copy changes (handled in Story 6, deferred to Phase 2)
- No accessibility rework (maintain WCAG 2.1 AA from original spec)

---

## Next Steps

1. **Designer review** (1 day): Wireframe Stories 1, 3, 4, 7 (visual changes)
2. **Copy review** (0.5 day): Error messages, empty states, tour text (Story 8, existing voice)
3. **Dev kickoff** (0.5 day): Sprint planning, backend API review, localStorage keys
4. **Implementation** (3–4 days): One developer, parallel Stories 1-8
5. **QA & testing** (1 day): New user funnel test, empty state verification, conditional visibility audit
6. **Launch Phase 1** (Feb 28): Deploy and track metrics
7. **Phase 2 kickoff** (March 3): Unlock power features based on Phase 1 success

---

## Questions Before Implementation?

- **Story 2 (Advanced Settings)**: Should default state show all phases enabled, or let user choose? → Recommend: All enabled by default, hide choices.
- **Story 3 (Results Tour)**: Should tour auto-skip after 5 seconds, or require [Skip]? → Recommend: Auto-skip; [Next]/[Prev] for manual control.
- **Story 4 (Settings)**: Should Danger Zone require double-confirmation, or password? → Recommend: Password + 3-second delay before button enables.
- **Story 6 (Pro Features)**: Should gray-disabled features show a tooltip on hover? → Recommend: Yes, [Learn More] link goes to landing page Pro section.
- **Story 7 (Download)**: Should file tree default to organized folders or flat list? → Recommend: Organized (matches original export structure), with flat toggle.

---

## Sign-Off

**Agent A (New User Advocate)**: ✅ Confirms these stories prioritize new user confidence and reduce abandonment
**Agent B (Power User Champion)**: ✅ Confirms power features remain accessible via keyboard shortcuts and hamburger menus
**Agent C (Product Strategist)**: ✅ Confirms monetization is timed for post-value, not pre-value; conversion moments preserved

**All three agents agree**: These 8 stories, implemented in Phase 1, set up the foundation for power user unlock (Phase 2) and monetization success (Phase 3).

---

**Approved by**: Consensus team (A, B, C)
**Date**: 2026-02-24
**Ready for implementation**: 2026-02-25
**Phase 1 target ship date**: 2026-03-01

---
