# Snatched Online — UI/UX Design Spec (2026-02-24)
# Produced by 3-agent debate team: Wordsmith (copy), Pixel (layout), Flow (UX)
# All conflicts resolved unanimously after 3 rounds of debate.

---

## Design System

**Grid & Layout:**
- Max-width: 1200px (expanded from 900px for data density)
- 12-column fluid grid
- Breakpoints: <768px (mobile) | 768-1024px (tablet) | 1024px+ (desktop)

**Colors:** Pico CSS defaults + 4 semantic colors
- Primary: #0066cc (actions)
- Success: #00aa00 (completion)
- Warning: #ffaa00 (caution)
- Danger: #cc0000 (errors)

**Typography:**
- Pico semantic HTML (h1-h6 auto-scaling)
- Monospace for logs/tables
- No custom font loading (performance)
- h1: 2rem, h2: 1.5rem, h3: 1.25rem, body: 1rem, mono: 0.875rem

**Spacing Scale:** 0.5rem, 1rem, 1.5rem, 2rem, 4rem

**Dark Mode:** Pico v2 built-in (browser prefers-color-scheme), no manual toggle in MVP

---

## SCREEN 1: LANDING PAGE

### Layout
- Hero section: full-width, centered, max-width 1200px
- Feature grid: 3-col (desktop) -> 1-col (mobile), cards with icons
- Process timeline: 4-step horizontal flow
- Footer: CTA + secondary nav links

### Copy
- **H1:** "Rescue your Snapchat memories"
- **Subtitle:** "Snapchat deletes exports after 30 days. Snatched finds and organizes them--with GPS, dates, and names restored."
- **Primary CTA:** "Upload Your Export"
- **Secondary CTA:** "View My Jobs"
- **Feature cards (3):**
  1. Target icon | "Match" | "We match media files to metadata using 6 strategies, from exact matches to educated guesses."
  2. Pin icon | "Enrich" | "Add GPS locations, dates, and friend names from Snapchat's servers."
  3. Download icon | "Export" | "Get organized folders with EXIF metadata embedded, ready for Immich or Apple Photos."
- **Process timeline:** Export -> Upload -> Process -> Download
- **Footer:** "Ready? Upload your first export to get started."
- **First-time empty state:** "Welcome to Snatched! Snapchat deletes exports after 30 days. We find and organize them--with dates, locations, and names restored."

### Interactions
- Authenticated user: Show "Welcome, [username]" at top
- First-time visitor: Subtle pulse animation on Upload CTA
- Both CTAs have hover states (slight elevation, darker shade)
- Features grid: Informational only, no click-through
- Responsive: Stack to single column < 768px
- WCAG: Semantic headings, skip link to main content, keyboard navigation

---

## SCREEN 2: UPLOAD PAGE

### Layout
- Single-column layout (simpler than 2-col, stacks naturally on mobile)
- Section 1: Hero (h2)
- Section 2: Drag-drop zone (prominent, dashed border, 200px height)
- Section 3: File info box (max size, processing time estimate)
- Submit button below form
- NO checkboxes in MVP (hidden, re-add phased when backend ships)

### Copy
- **H1:** "Upload your Snapchat export"
- **Helper text:** "Usually 1-5 GB. Drag here or select a file. Max: 5 GB."
- **Dropzone text:** "Drag and drop your ZIP file here, or [Choose File]"
- **File info box:**
  - "Max upload size: 5 GB"
  - "Typical processing time: 10-30 minutes depending on file size"
  - "Need help? [View export instructions]"
- **Submit button:** "Upload & Process"
- **Future checkbox labels (when re-added):**
  - "Embed location & date in files" (EXIF)
  - "Add timestamp overlays"
  - "Dark mode chat exports"

### Error Messages (inline, below dropzone)
- Wrong format: "Only ZIP files. Please export directly from Snapchat Settings > My Data."
- Too large: "File is X.X GB--over the 5 GB limit. Try splitting into smaller batches."
- Corrupted ZIP: "This ZIP file is damaged. Try exporting again from Snapchat."
- Invalid content: "This doesn't look like a Snapchat export. Check Settings > My Data to export."
- Network timeout: Toast notification with [Retry] action
- Success: Toast "Job queued! [View Progress]" + redirect to dashboard

### Interactions & States
- **Idle:** Empty form, drag-drop ready, blue dashed border
- **Dragging:** Border solid blue, background light blue (#f0f4ff)
- **Selected:** Show filename + file size, validate type (.zip only) and size (max 5GB)
- **Validating:** Spinner + "Checking file..." (sub-2s)
- **Uploading:** Progress bar with percentage (not spinner)
- **Validating ZIP:** "Validating ZIP structure..."
- **Error:** Inline error card with retry, keep form in place
- **Success:** Toast + redirect to dashboard
- Mobile: Drag-drop degrades to file picker, touch targets 44px+, font 16px minimum
- Accessibility: aria-live="polite" on errors, aria-invalid on fields, skip link to dropzone

---

## SCREEN 3: DASHBOARD

### Layout
- Top bar: "Your Jobs" h2 + "New Upload" CTA button (top-right)
- Stat cards (3-col desktop -> 1-col mobile): Snapchats Found | Match Confidence (Latest) | Storage Used
- Job list: Card layout (not table), 1-col mobile -> 2-col tablet -> 3-col desktop
- Active jobs section: Poll every 2s
- Completed jobs section: Load once, paginated with "Load More"
- Empty state: Centered CTA

### Copy
- **H1:** "Your Jobs"
- **Stat card labels:** "Snapchats Found" | "Match Confidence (Latest)" | "Storage Used"
- **Job card:** "Job #123 | [status badge] | Uploaded: [date] | X.X GB | [count] snapchats | [matched]% matched"
- **Status badges:** "Processing..." (yellow, spinner) | "Done" (green, checkmark) | "Failed" (red, X) | "Cancelled" (gray, stop)
- **Card actions:** "View Results" | "Cancel" (running only) | "Download" (completed) | "Delete" (failed)
- **Empty state:** "No jobs yet. Ready to rescue your Snapchats? [Upload Export]"

### Interactions
- **Loading:** 2-3 skeleton job cards shimmer while fetching
- **Active jobs:** Poll every 2s, show progress bar + "Phase 2 of 4" + elapsed time
- **History:** Load once on page load, "Load More" button (paginated)
- **Job card click:** Navigate to /results/{id}
- **Cancel:** Confirmation modal + POST /api/jobs/{id}/cancel
- **Delete:** Confirmation modal
- Accessibility: Status badges with aria-label, progress bars with aria-valuenow/min/max, keyboard Tab through cards

---

## SCREEN 4: JOB PROGRESS (Real-Time SSE)

### Layout
- Breadcrumb: Dashboard > Job #{{ job_id }}
- Header: h1 + progress subtitle + elapsed time + overall progress bar
- Phase cards (4): 2-col desktop -> 1-col mobile
- Log terminal: Full-width, dark bg (#1a1a1a), monospace, max-height 300px desktop / 50vh mobile
- Bottom action bar: Cancel button + Back to Dashboard

### Copy
- **H1:** "Processing job #{{ job_id }}"
- **Progress subtitle:** "Phase 2 of 4 | 35% complete | Started 5 minutes ago"
- **Phase labels:**
  - "Phase 1: Ingest" | "Reading your export..."
  - "Phase 2: Match" | "Matching files to metadata..."
  - "Phase 3: Enrich" | "Adding locations and dates..."
  - "Phase 4: Export" | "Building your organized files..."
- **Log header:** "Processing log (updates live)"
- **Log placeholder:** "Waiting for events..."
- **Cancel button:** "Stop Processing"
- **Cancel modal:** "Are you sure? Completed work will be saved, but processing will stop. You can restart anytime. [Keep Processing] [Stop Processing]"
- **Completion:** "Done! Your memories are ready to download. [View Results]"

### Phase Card States
- Pending: Gray circle, neutral bg
- Running: Blue circle + pulse animation, blue left border (4px)
- Completed: Green checkmark, light green bg
- Failed: Red X, red left border, error message in card, gray-out downstream phases
- Card height: Auto (content-based, not fixed px)

### SSE Events
- `phase_start`: Update current phase to running
- `phase_complete`: Mark phase done, move to next
- `phase_error`: Mark phase failed, show error in log, gray-out downstream
- `progress`: Update overall progress % + elapsed time
- `log`: Append to terminal, auto-scroll to bottom
- `complete`: All phases green, show "View Results" button

### Interactions
- Log terminal: Auto-scroll, user can scroll up to review (overrides auto-scroll)
- Cancel: Only visible if running, confirmation modal required
- Connection loss: Banner "Connection lost. Reconnecting..." with retry
- Mobile: Phase cards stack 1-col, log expands to 50vh, cancel button sticky at bottom
- Accessibility: aria-live="polite" on phase status changes, aria-live="off" on log terminal (errors only)

---

## SCREEN 5: RESULTS (3 Tabs)

### Layout
- Header (sticky): Job ID + completion time + "Download Results" button (right-aligned)
- Tab navigation (sticky): Summary | Matches (badge count) | Assets (badge count)
- Tab content: Per tab below
- Mobile: Tabs sticky + horizontal scroll, tables collapse to card layout

### Copy
- **H1:** "Your memories are ready"
- **Completion:** "Completed: [timestamp]"
- **Tab labels:** "Summary" | "Matches ([count])" | "Assets ([count])"

### Summary Tab
- **4 stat cards:** "Snapchats Found" | "Successfully Matched" | "Match Confidence" | "Locations Recovered"
- **Breakdown table:** "Organized by type" — columns: Type | Found | Matched | GPS Coverage — rows: Memories | Chats | Stories
- **Processing time table:** Phase | Duration — rows: Ingest | Match | Enrich | Export | Total
- **Footer:** "Ready to download? [Go to Download Page]"
- **Empty state:** "No matches found. This usually means your export was incomplete or corrupted."

### Matches Tab
- **Table columns:** Snapchat | Confidence | Date | Type
- Confidence shown as % with color indicator (green 100%, yellow 80-99%, orange 50-79%, gray <50%)
- Strategy column HIDDEN (show confidence instead — user-facing, not technical)
- Paginated: 20 per page, "Load More" button (desktop) / infinite scroll (mobile)
- Sortable columns (server-side, reset to page 1 on sort)
- Mobile: Card layout per match
- Empty state: "No matches found. Processing may still be running, or all snapchats failed to match."

### Assets Tab
- **Table columns:** File ID | Saved As | Type | Size | Metadata (Embedded / Not Embedded)
- Same pagination and sort behavior as Matches
- Mobile: Card layout per asset
- Empty state: "Export is still running, or no files were produced."

### Interactions
- Tab switching: Client-side, no reload, Left/Right arrow keys
- Lazy loading: Matches/Assets load on first tab click, show skeleton rows
- Sorting: Click column header, shows arrow icon, resets to page 1
- Stat cards: Informational only (no click-through in MVP)
- Accessibility: role="tab"/role="tabpanel", aria-selected, visible focus on keyboard nav, confidence colors + text + icon (not color alone)

---

## SCREEN 6: DOWNLOAD PAGE

### Layout
- Header: h2 "Your files are ready"
- Download All button: Primary, prominent
- File tree: Expandable folders, individual download links, file sizes inline
- Footer: Navigation links

### Copy
- **H1:** "Your files are ready"
- **Download All:** "Download Everything as ZIP" + "All your processed files in one archive."
- **Individual section:** "Or download individual files"
- **File categories:** Chat Conversations | Memories & Stories | Metadata Reports
- **File sizes:** Shown inline "(2.3 MB)"
- **Next steps:** "Next: Import into Immich, Photos, or any photo library."
- **Footer links:** "View Results Summary" | "Back to Dashboard"
- **Error (tree fails):** "Couldn't build your file list. [Retry]"

### Interactions
- Loading: Skeleton tree rows while building file list
- File tree: Expandable folders, click filename to download
- Download All: Streams ZIP from /api/download/all
- Error recovery: Retry button or "Download as ZIP" fallback
- Mobile: Vertical layout, touch targets 44px+, download buttons full-width
- Accessibility: role="tree"/role="treeitem", aria-expanded on folders

---

## SCREEN 7: SETTINGS/ACCOUNT (Future, Post-MVP)

### Layout
- Left sidebar (1/4 desktop): Account | Storage & Quota | Preferences | Danger Zone
- Right content area (3/4 desktop)
- Mobile: Sidebar collapses to top tabs

### Sections
- **Account:** Username, email, joined date
- **Storage:** Progress bar "Used X GB of Y GB", retention info, upgrade CTA
- **Preferences:** Checkboxes (when implemented): Embed location & date | Add timestamp overlays | Dark mode exports | XMP sidecars | GPS window (advanced, collapsed)
- **Danger Zone:** Delete account with "type DELETE to confirm" modal

---

## CROSS-CUTTING FEATURES

### Toast Notifications
- Success (green, 5s auto-dismiss): Upload started, job completed, settings saved
- Error (red, 6s auto-dismiss): Upload failed, network timeout, job failed
- Info (blue, 5s auto-dismiss): General status updates
- Position: Top-right desktop, full-width bottom on mobile
- One toast at a time, queue subsequent
- X button to close immediately

### Error Display Pattern (3-Tier)
| Error Type | Display | Duration | Example |
|-----------|---------|----------|---------|
| Upload validation | Inline below input | Persistent | "Only ZIP files" |
| Job processing | Banner at top + phase highlight | Persistent | "Phase 2 failed" |
| Network/server | Toast notification | 5-6s auto-dismiss | "Connection lost. [Retry]" |
| Form errors (settings) | Inline validation | Persistent | Red label + helper text |

### Keyboard Shortcuts
- `?` = Help modal
- `/` = Jump to /upload
- `D` = Jump to /dashboard
- `R` = Jump to /results (from progress)
- Left/Right arrows = Switch tabs (on Results page)

### Help Modal (triggered by `?`)
- "What is Snatched?" — elevator pitch
- "How matches work" — 6 strategies explained simply
- "Keyboard shortcuts" — list
- "Contact" — support email / GitHub

### Accessibility (WCAG 2.1 AA — All Screens)
- Skip links on every page (hidden until :focus)
- Semantic HTML (h1-h6, labels, lists)
- Keyboard navigation: Tab, Shift+Tab, Enter, Escape
- Focus indicators on all interactive elements
- Color contrast 4.5:1 for text, 3:1 for UI components
- Status badges: aria-label
- Error messages: role="alert", aria-live="polite", aria-invalid
- Log terminal: aria-live="off" (errors announced only)
- Confidence: Color + text + icon (not color alone)
- Touch targets: 44px+ on mobile
- Font size: 16px minimum on inputs (prevents iOS auto-zoom)

### Responsive Breakpoints
- **Mobile (<768px):** 1-col, cards full-width, tables -> card layout, sticky headers, 44px touch targets
- **Tablet (768-1024px):** 2-col layouts, sidebars collapse, 2-col phase cards
- **Desktop (1024px+):** Full grids, sidebars visible, 4-col phase cards, max-width 1200px

### Component Library
1. **Stat Card:** Label + large number + optional subtext/arrow
2. **Phase Card:** Status icon + name + flavor text + mini progress bar + active/done/failed states
3. **Job Card:** Metadata + status badge + action buttons + hover elevation
4. **Toast:** 4 variants (info/success/warning/error) + auto-dismiss + X close
5. **Modal:** Centered overlay (desktop), full-screen (mobile), primary + secondary buttons, Escape to close
6. **Pagination:** "Load More" button (desktop) / infinite scroll (mobile)
7. **Badge:** Status (Processing/Done/Failed) + Count + Confidence level
8. **Skeleton Loader:** Shimmer animation placeholders for cards, table rows, stat values

---

## CONSENSUS DECISIONS (Unanimous)

| Conflict | Decision | Rationale |
|----------|----------|-----------|
| Upload checkboxes | HIDE in MVP, re-add phased | Backend ignores them, removes cognitive load |
| Download page | Separate /download (not 4th tab) | Clear navigation intent, mobile clarity |
| Error display | 3-tier (inline/toast/banner) | Different error types need different UX |
| Loading states | Phase cards + skeletons + flavor text | Different screens, different purposes |
| Match strategies | Hide column, show confidence % + colors | User-focused, not technical |
| Pagination | "Load More" desktop / infinite scroll mobile | Best of both worlds |
| Dark mode | Browser preference (Pico auto) | No toggle in MVP |

---

## READY FOR: Stitch mockup generation (7 screens)
