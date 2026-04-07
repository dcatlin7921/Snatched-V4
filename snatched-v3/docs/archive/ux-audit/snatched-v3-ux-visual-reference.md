# Snatched v3 UX — Visual Reference & Component Inventory
**What a user actually sees at each step**
**2026-02-26**

---

## FLOW DIAGRAM: User Journey & Page Structure

```
LOGIN (login.html)
    ↓
DASHBOARD (dashboard.html)
    ↓ [Click "New Upload" or "Start New Job"]
UPLOAD (upload.html) → FILE SELECT → CONFIGURE MODE → START JOB
    ↓
JOB PAGE (job.html) ← MAIN EXPERIENCE, stays on this page for entire process
    ├─ INGEST phase
    ├─ [Countdown Modal 1]
    ├─ MATCH phase + Gallery view
    ├─ [Countdown Modal 2]
    ├─ ENRICH phase + Map/Timeline/Conversations views
    ├─ [Countdown Modal 3]
    ├─ EXPORT phase
    ├─ Review bar appears
    └─ Download button
         ↓ [Click Download]
DOWNLOAD (download.html) ← FINAL PAGE
    ↓
RESULTS (results.html) ← OPTIONAL, user can click "View Results" from download page
```

---

## COMPONENT VISUAL INVENTORY

### 1. LOGIN PAGE

**File**: `login.html` (47 lines)

**Layout**:
```
┌─────────────────────────────────────┐
│                                     │
│  ❤️ SNATCHED                        │
│                                     │
│  ┌──────────────────────────────┐  │
│  │ Sign In                      │  │
│  │                              │  │
│  │ [Username Field]             │  │
│  │ [Password Field]             │  │
│  │ [Log In Button - Yellow]     │  │
│  │                              │  │
│  │ Don't have an account?       │  │
│  │ Create one                   │  │
│  └──────────────────────────────┘  │
│                                     │
│ They took your memories.            │
│ We take them back.                  │
│                                     │
└─────────────────────────────────────┘
```

**Issues**:
- Form fields have default browser focus (blue ring), not snap-yellow.
- Error message (if present) lacks color coding.
- Password reset link is missing.
- On mobile (480px), tagline is below form, not above.

**What's right**:
- Clean centering.
- Heart-broken icon is immediately understood.
- Form is standard HTML (good autocomplete support).

---

### 2. DASHBOARD PAGE

**File**: `dashboard.html` (134 lines)

**Layout**:
```
NAV BAR
┌─────────────────────────────────────────────────┐
│ ❤️ SNATCHED     Dashboard | Upload | Settings   │
│                 User | [Pro Badge] | Logout     │
└─────────────────────────────────────────────────┘
CAUTION TAPE DIVIDER

MAIN CONTENT
┌──────────────────────────────────────────────────┐
│                                                  │
│  Your Jobs          [New Upload ➕ Button]      │
│                                                  │
│  ┌───────────┬───────────┬──────────────┐       │
│  │ Total: 5  │ Done: 3   │ Storage: 2GB │       │
│  └───────────┴───────────┴──────────────┘       │
│                                                  │
│  ┌──────────────────────────────────────┐       │
│  │ Processing Slots: 2/3 in use [Pro]  │       │
│  │ ⚫ ⚫ ○                               │       │
│  │ 1 job queued — position: #1          │       │
│  └──────────────────────────────────────┘       │
│                                                  │
│  ────── MISSION REGISTRY ──────                 │
│                                                  │
│  ACTIVE JOBS:                                   │
│  [Loading active jobs...]  (spinner?)           │
│                                                  │
│  ────── JOB HISTORY ──────                      │
│                                                  │
│  JOB HISTORY:                                   │
│  [Loading job history...]   (spinner?)          │
│                                                  │
└──────────────────────────────────────────────────┘

FOOTER
```

**Issues**:
- No spinner while htmx loads job lists. Text "Loading..." with no animation.
- "New Upload" button is in header, not sticky. On mobile, easy to miss.
- Tier info doesn't explain what limits apply to tier.
- Job cards are loaded via htmx (structure unknown without reading endpoint).

**What's right**:
- Stat cards are clear and prominent.
- Processing slots visualization (dots) is excellent UX.
- Queue position is shown to user (transparent resource allocation).
- Sections are labeled and separated clearly.

---

### 3. UPLOAD PAGE (Configuration)

**File**: `upload.html` (starts with file selector, moves to configuration)

**Phase 1: File Selection**

```
┌──────────────────────────────────────┐
│ Upload Your Snapchat Export          │
│                                      │
│ [Pro Tier Badge] Up to 50 GB         │
│                                      │
│ ┌────────────────────────────────┐  │
│ │  ⬇️  Drop files here            │  │
│ │   or click to browse            │  │
│ │                                 │  │
│ │ ⚠️ LARGE FILE EXPECTED 1-50GB   │  │
│ └────────────────────────────────┘  │
│                                      │
│ Files: [File 1] [Remove ❌]          │
│        [File 2] [Remove ❌]          │
│                                      │
│ Total: 12.4 GB                       │
│                                      │
│ [Cancel] [Continue] ➜                │
└──────────────────────────────────────┘
```

**Issue**: Drag zone has minimal visual feedback. Dashed border would help.

**Phase 2: Mode Selection** (after clicking Continue)

```
┌──────────────────────────────────────┐
│ Processing Mode                      │
│                                      │
│ ┌──────────────────────────────────┐ │
│ │ SPEED RUN                        │ │ ← Default
│ │ Let the rescue happen. One zip.  │ │
│ │ ✓ Auto-continue all phases       │ │
│ │ ✓ Single consolidated ZIP        │ │
│ │ ✗ No manual corrections           │ │
│ └──────────────────────────────────┘ │
│                                      │
│ ┌──────────────────────────────────┐ │
│ │ POWER USER                       │ │
│ │ Control every phase. Review.     │ │
│ │ ✓ Pause between phases           │ │
│ │ ✓ Access correction tools        │ │
│ │ ✓ Choose export lanes & options  │ │
│ │ ✗ Requires attention             │ │
│ └──────────────────────────────────┘ │
│                                      │
│ [Choose Speed Run] [Choose Power...] │
└──────────────────────────────────────┘
```

**What's right**: Clear card design, pros/cons listed, mode choice is obvious.

---

### 4. JOB PAGE (The "Living Canvas") — Main Experience

**File**: `job.html` (470 lines)

**Header Section (VIZ BAND)**

```
PHASE PROGRESS BAR (always visible)
┌────────────────────────────────────────────────┐
│ INGEST ▸ MATCH ▸ ENRICH ▸ EXPORT              │
│                                                 │
│ 2,847 files | Jan 2018—Feb 2024 | 94% matched │
│ (stats update live as job progresses)          │
│                                                 │
│ ━━━━━━━━━━━░░░░░░░░░░░░░░░░░░░░░░░░ 42%      │
│ ~6 minutes remaining                           │
│                                                 │
│ [STATUS: Matching in progress]                 │
└────────────────────────────────────────────────┘
```

**Issue**: No color segmentation (file types). No duplicate density. Just plain stats.

**Below VIZ BAND: Countdown Modal (appears at phase gates)**

```
┌────────────────────────────────────────┐
│                                        │
│  ████████████████ 10                   │ ← Countdown timer
│                                        │
│  Continuing to Enrich...               │
│                                        │
│  Match rate: 94%                       │
│  GPS tagged: 1,247                     │
│                                        │
│  [Continue to Enrich →] [Pause & Review]
│                                        │
│  (Export phase shows config options:)  │
│  ☑ Memories   ☑ Chat media             │
│  ☑ Stories    ☑ Embed EXIF             │
│  ☑ Overlays   ☐ XMP sidecars           │
│                                        │
└────────────────────────────────────────┘
```

**What's right**: Countdown is visible, buttons are clear, export config is accessible.
**Issue**: On mobile (480px), modal with config panel might not fit vertically.

**VIEW TABS (below modal)**

```
[Gallery] [Timeline] [Map] [Conversations]
  (active, pulsing)  (greyed during ingest)
```

**Gallery View**

```
┌──────────────────────────────────────────────┐
│  [Thumb] [Thumb] [Thumb] [Thumb]            │
│  [Thumb] [Thumb] [Thumb] [Thumb]            │
│  [Thumb] [Thumb] [Thumb] [Thumb]            │
│  (lazy-loaded from /api/jobs/{id}/gallery)  │
│                                              │
│  Gallery will populate during matching...    │
│  (if phase < match)                          │
└──────────────────────────────────────────────┘
```

**Issue**: No loading spinner while htmx fetches. Empty grid feels broken on slow networks.

**TOOLS SIDEBAR (appears when paused or after match)**

```
┌─────────────────────┐
│ Tools               │
├─────────────────────┤
│ Friends & Aliases   │
│ GPS Correction      │ (greyed during ingest)
│ Timestamp Fixes     │
│ Duplicates          │
│ Albums              │ (greyed during ingest)
│ Export Config       │
│ Tag Presets         │
└─────────────────────┘
```

**Issue**:
- Sidebar is off-screen on mobile (not responsive).
- Disabled tools lack visual "not available" styling.
- Friends link is global, not per-job.

**REVIEW BAR (appears when job.status == 'completed')**

```
┌────────────────────────────────────────────────┐
│  4,847 files rescued        [DOWNLOAD ALL 📦]  │
└────────────────────────────────────────────────┘
```

**Issue**: On mobile (480px), button might wrap or truncate.

---

### 5. RESULTS PAGE (After-Action Report)

**File**: `results.html` (372 lines)

**Sticky Header**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
│ Mission Complete.                             │
│                                              │
│ [DOWNLOAD RESULTS] [REPORTS ▼] [TOOLS ▼]   │
└──────────────────────────────────────────────┘
```

**Reports Dropdown** (hidden by default)

```
┌─────────────────────────────────┐
│ Download Data Reports           │
├─────────────────────────────────┤
│ [Job Summary] [JSON] [CSV]      │
│ [Match Report] [JSON] [CSV]     │
│ [Asset Report] [JSON] [CSV]     │
└─────────────────────────────────┘
```

**Tools Dropdown**

```
┌──────────────────────────┐
│ CORRECTIONS              │
│ • GPS Correction         │
│ • Timestamps             │
│ • Redact                 │
│ • Match Config           │
├──────────────────────────┤
│ EXPLORE                  │
│ • Browse Files           │
│ • Chats                  │
│ • Timeline               │
│ • Map                    │
├──────────────────────────┤
│ ORGANIZE                 │
│ • Duplicates             │
│ • Albums                 │
├──────────────────────────┤
│ ACTIONS                  │
│ • Reprocess              │
└──────────────────────────┘
```

**Stat Cards**

```
┌──────────┬──────────┬──────────┬──────────┐
│ Assets   │ Matched  │ Match    │ GPS      │
│ Found    │ ✓        │ Rate     │ Coverage │
│ 2,847    │ 2,673    │ 94.1%    │ 68%      │
└──────────┴──────────┴──────────┴──────────┘
```

**Tabs**

```
[Summary (active)] [Matches 2,673] [Assets 2,847]
```

**Issues**:
- "After-Action Report" label is jargon-heavy.
- Reports shown in dropdown AND in Summary section (redundant).
- Match report cards don't explain what each report contains.
- Reprocess modal is buried in Tools dropdown.

---

### 6. DOWNLOAD PAGE (Final Experience)

**File**: `download.html` (96 lines)

**Layout**

```
┌────────────────────────────────────────┐
│ Extraction Complete.                   │
│ Your files are ready for pickup.       │
│                                        │
│ ┌────────────┬────────────┬────────┐  │
│ │ Files: 2,847│ Size: 87.3 GB│EXIF:2,673│
│ └────────────┴────────────┴────────┘  │
│                                        │
│  ╔════════════════════════════════════╗│
│  ║  📦                                 ║│
│  ║  Consolidated Intelligence         ║│
│  ║  Every memory, chat, and story      ║│
│  ║  reconstructed with full metadata. ║│
│  ║  One final act of rebellion.        ║│
│  ║                                    ║│
│  ║  [DOWNLOAD EVERYTHING AS ZIP]      ║│
│  ║  2,847 files · 87.3 GB             ║│
│  ╚════════════════════════════════════╝│
│                                        │
│  ────── OR GRAB INDIVIDUAL FILES ──────│
│  (Power user only; shown if not speed-run)
│                                        │
│  [Folder tree htmx-loaded]             │
│                                        │
│  ────── INJECTION PROTOCOL ──────      │
│  Import to Immich, Apple Photos, etc. │
│  Your extracted intelligence has been │
│  weaponized with full EXIF metadata.  │
│                                        │
│  🟢 68% of your files have GPS coords │
│                                        │
│ [View Results] [Back to Dashboard]    │
│                                        │
│ Files available for 30 days.           │
│                                        │
└────────────────────────────────────────┘
```

**Issues**:
- Rescue count (2,847 files) is in small stat card, not prominent.
- "Extraction Complete" headline is generic.
- Speed-run vs power-user mode not explained (why doesn't speed-run user see file tree?).
- Retention notice is at bottom, not sticky.
- "Injection Protocol" copy is good but lacks links to import docs.

**What's right**:
- Large download button is prominent (snap-yellow).
- Hero section is celebratory.
- Guidance about what to do with files is helpful.

---

## Color Palette in Use

**From CSS review**:

- `--snap-yellow`: #FFFC00 — primary action, accents, healthy status
- `--charcoal`: background color for cards and sections
- `--border-dark`: subtle dividers
- `--success`: green, good status (match rate >85%)
- `--warning`: orange/yellow, caution status (match rate 60-85%)
- `--danger`: red, error/problem status (match rate <60%)
- `--text-primary`: main text (white)
- `--text-muted`: secondary text (grey)
- `--text-dim`: disabled/tertiary text (dark grey)

---

## Responsive Breakpoints in CSS

- **768px**: Tablet breakpoint. Sidebar reflows, nav wraps.
- **480px**: Mobile breakpoint. Single-column layout, buttons stack.

**Problem**: Not all components have rules for 480px. Some will look janky on phones.

---

## Hover States Inventory

**Implemented**:
- `.btn-primary:hover` → darker yellow
- `.btn-outline:hover` → border + bg highlight
- `.btn-yellow:hover` → brighter yellow
- `.btn-secondary:hover` → outline highlight
- `.nav-links a:hover` → underline or bg change
- `.tool-link:hover` → highlight (but disabled tools don't have hover prevention)
- `.gallery-card:hover` → subtle scale or glow
- `.view-tab:hover:not(:disabled)` → highlight
- `table tbody tr:hover` → faint background

**Missing**:
- Form input fields don't have snap-yellow focus ring.
- Disabled buttons/links don't have `cursor: not-allowed`.
- Some interactive elements lack hover feedback.

---

## Animation / Motion Elements

**Present**:
- Phase visualization cycles as job progresses.
- Progress bar fills smoothly.
- Tab enable triggers `.view-tab--pulse` animation (3s pulse on tab when activated).
- Countdown timer counts down (1s per update).
- Modals fade in/out via `.visible` class toggle.

**Missing**:
- No loading spinner (most critical).
- No thumbnail fade-in animation (gallery cards just appear).
- No GPS pin bloom animation (map pins appear all at once).
- No file write feedback during export.

---

## Component Maturity Assessment

| Component | Status | Maturity | Notes |
|-----------|--------|----------|-------|
| Nav bar | Complete | 7/10 | Clear, responsive, but no sub-menus |
| Login form | Complete | 6/10 | Works, no password reset, focus states generic |
| Dashboard | Complete | 7/10 | Missing loading spinner |
| Upload | Complete | 8/10 | Minor drag-zone visual polish needed |
| Job page (Viz-band) | Partial | 5/10 | Missing density visualization (big gap) |
| Job page (Tabs) | Complete | 8/10 | Works, good progressive disclosure |
| Job page (Countdown) | Complete | 7/10 | Works, mobile breakpoint needed |
| Tools sidebar | Complete | 6/10 | Works, mobile drawer needed, disabled state missing |
| Gallery | Complete | 7/10 | Works, loading state needed |
| Results page | Complete | 6/10 | Redundant reports, confusing labels |
| Download page | Complete | 6/10 | Rescue count not prominent, retention notice not sticky |
| Error handling | Missing | 1/10 | No error page visible in templates |
| Empty states | Partial | 6/10 | Some present, some missing |

---

## Conclusion

**Maturity overall: 7/10 for usability, 5/10 for polish.**

- Navigation works. Modals work. Data flows. User succeeds.
- But rough edges: missing spinners, unthemed form focus, missing density band, hidden rescue count.
- Top 3 visual improvements: (1) form focus states, (2) loading spinners, (3) density band.

---

**Reference complete.**
