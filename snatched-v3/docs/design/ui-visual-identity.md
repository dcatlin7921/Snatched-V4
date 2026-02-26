# Snatched Online — Visual Identity & Refined Design Spec
# Source: Stitch mockups (rebellion theme) + UX debate team consensus
# Date: 2026-02-24
# Status: APPROVED — Ready for Jinja2 template implementation

---

## Design DNA

**Brand position**: Snatched is a data rescue tool that restores what Snapchat strips.
The visual identity is rebellious and edgy — Snapchat's own yellow turned against them —
but the COPY stays grounded in what the tool actually does. No fake hacker movie nonsense.

**The line**: "Rescue mission" YES. "Hacking Snapchat's servers" NO.

---

## Color System

```css
:root {
  /* Brand */
  --snap-yellow: #FFFC00;    /* Snapchat yellow, weaponized as our accent */
  --deep-black: #0a0a0a;     /* Page background */
  --charcoal: #141414;        /* Card/surface background */
  --charcoal-alt: #1a1a1a;   /* Alternating table rows */

  /* Functional */
  --success: #00aa00;         /* Completed, matched */
  --danger: #cc0000;          /* Failed, errors */
  --warning: #ffaa00;         /* Caution states */
  --hacker-green: #00FF41;    /* Terminal/log text */

  /* Text */
  --text-primary: #f0f0f0;   /* Body text */
  --text-muted: #888888;     /* Secondary text */
  --text-dim: #666666;        /* Tertiary/disabled */
  --border-dark: #2d2d2d;    /* Subtle borders */
}
```

## Typography

```css
/* Display: Inter — all headings, labels, buttons */
font-family: 'Inter', sans-serif;

/* Mono: JetBrains Mono — terminal, timestamps, stats, tables */
font-family: 'JetBrains Mono', monospace;

/* Icons: Material Symbols Outlined (filled variant) */
font-variation-settings: 'FILL' 1, 'wght' 400;
```

**Weight scale**: 400 (body), 700 (bold), 800 (extrabold labels), 900 (black — headings, buttons, logo)

**Headings**: Uppercase, italic, tight tracking (tracking-tighter). Font-weight 900.

**Labels**: Uppercase, letter-spaced (tracking-widest or tracking-[0.2em]). Font-weight 800. Size 10-12px.

**Body**: 14-16px, font-weight 400-500.

## Spacing & Grid

- Max-width: 1200px
- Page padding: px-6
- Card padding: p-6 to p-8
- Section gaps: space-y-10 or mb-12 to mb-16
- Grid: 12-column (Tailwind grid-cols-12 for file trees)

## Background Texture

Subtle diagonal caution-stripe pattern at 3% opacity on all pages:

```css
body {
  background-color: #0a0a0a;
  background-image: repeating-linear-gradient(
    45deg,
    transparent,
    transparent 40px,
    rgba(255, 252, 0, 0.03) 40px,
    rgba(255, 252, 0, 0.03) 80px
  );
}
```

---

## Component Patterns (extracted from Stitch)

### Navigation Bar
- Sticky, backdrop-blur, bg-deep-black/80
- Left: SNATCHED logo (font-black, italic, uppercase, tracking-tighter)
- Logo icon: `heart_broken` Material Symbol in snap-yellow (broken heart = broken ghost metaphor)
- Below nav: 2px caution-tape stripe (animated diagonal yellow/black)
- Right: nav links (uppercase, tracking-widest, text-xs) + user avatar (square, yellow border)

```css
.caution-tape {
  background: repeating-linear-gradient(
    -45deg, #FFFC00, #FFFC00 10px, #000 10px, #000 20px
  );
  height: 2px;
}
```

### Stat Cards
- bg-charcoal, border-t-[3px] border-snap-yellow
- Label: mono, text-[10px], uppercase, tracking-widest, text-muted
- Value: text-4xl, font-black, tracking-tighter
- Value color: snap-yellow (primary), success green (good), white (neutral)

### Job Cards
- bg-charcoal, border-l-4 colored by status
- Active: border-snap-yellow + pulsing glow (box-shadow animation)
- Completed: border-success (#00aa00)
- Failed: border-danger (#cc0000)
- Status badge: inline, font-black, text-[10px], uppercase, colored bg
- Actions: snap-yellow solid buttons + outline buttons

```css
.pulsing-glow {
  box-shadow: 0 0 15px rgba(255, 252, 0, 0.3);
  animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}
```

### Phase Cards (Job Progress)
- 4-column grid (1-col mobile)
- Completed: border-l-4 border-hacker-green, green checkmark, "Done"
- Active: border-l-4 border-snap-yellow, pulsing glow, mini progress bar, "Active XX%"
- Pending: border-l-4 border-slate-700, opacity-50, grayscale, lock icon, "Waiting"

### Log Terminal
- bg-black, border-2 border-snap-yellow, yellow glow shadow
- Header: "LIVE FEED" in snap-yellow mono, blinking yellow dot indicator
- Content: JetBrains Mono, hacker-green text (#00FF41), yellow timestamps
- Blinking cursor at bottom
- Max-height 400px with overflow scroll

### Buttons
- Primary: bg-snap-yellow text-black font-black uppercase, yellow glow on hover
- Secondary/outline: border-2 border-snap-yellow text-snap-yellow, fill on hover
- Danger: bg-red-600 text-white, red glow shadow
- All: no border-radius (sharp corners), tracking-widest

### Glitch Logo Effect (optional, use on progress page)
```css
.glitch-logo {
  text-shadow: 0.05em 0 0 rgba(255, 0, 0, 0.75),
               -0.025em -0.05em 0 rgba(0, 255, 0, 0.75),
               0.025em 0.05em 0 rgba(0, 0, 255, 0.75);
  animation: glitch 500ms infinite;
}
```

### Tables
- Monospace font
- Header row: snap-yellow text, uppercase, tracking-widest
- Alternating rows: #141414 / #1a1a1a
- Hover: bg-white/5
- GPS/confidence colors: green >80%, orange 50-79%, yellow for everything else

### Dropzone (Upload)
- Yellow dashed SVG border (2px)
- 240px height, bg-charcoal
- Large yellow upload icon center
- "Choose File" outline button

### File Tree (Download)
- Native `<details>` + `<summary>` for folders
- 12-column grid (path | size | action)
- Yellow folder icons, white file icons
- Yellow "Download" links
- Expand chevron rotates on open

### Selection Highlight
```css
body { selection:bg-[#FFFC00] selection:text-black; }
```

---

## Screen-by-Screen Refined Copy

### SCREEN 1: Landing Page

**Nav**: SNATCHED logo | Upload | Dashboard (links)

**Tagline** (under logo): "They took your memories. We take them back."

**Badge**: "Operation: Memory Extraction" (pulsing border, snap-yellow)

**H1**: "Snapchat stripped your metadata. We're putting it back."

**Subtitle**: "They delete your exports after 30 days. Snatched finds everything they tried to hide. No more nameless files. No more lost locations."

**Primary CTA**: "RESCUE YOUR MEMORIES" (snap-yellow, glow)

**Secondary CTA**: "VIEW MY JOBS" (outline)

**Feature Cards** (3-col, yellow left border):
1. `radar` icon | **MATCH** | "6 matching strategies, from exact hits to educated guesses. We find what Snapchat buried."
2. `encrypted` icon | **ENRICH** | "GPS coordinates, timestamps, and friend names. Everything they stripped, restored."
3. `ios_share` icon | **EXPORT** | "EXIF-embedded files ready for Immich, Apple Photos, or any photo library. Your metadata, your files."

**How It Works** (4-step timeline, yellow connecting lines):
1. "Export from Snap" — "Go to Settings > My Data"
2. "Upload ZIP" — "Drop your export file"
3. "We Process" — "Match, enrich, organize"
4. "Download Everything" — "Get your files back"

**Footer CTA section** (dashed yellow border card):
- "Ready to rescue your memories?"
- "Snapchat gives you 30 days. Clock's ticking."
- "START RECOVERY" button

**Footer**: Links + "© 2026 Snatched. Not affiliated with Snap Inc."

---

### SCREEN 2: Upload Page

**H1**: "Upload your Snapchat export" (yellow left border accent)

**Subtitle**: "Drop your ZIP. We'll find what they tried to delete."

**Dropzone**: Yellow dashed border, upload icon, "Drag and drop your ZIP file here", "Choose File" button

**Info card** (yellow left border):
- "Before you upload:"
- Max upload: 5 GB
- Processing time: 10-30 minutes depending on size
- ZIP files only — export from Snapchat Settings > My Data
- "Need help? View export instructions" (yellow link)

**Submit**: "UPLOAD & PROCESS" (full-width snap-yellow, glow blur behind)

**Below submit**: "Your files are processed securely and never shared." (small, muted)

**Errors** (inline, red border):
- Wrong format: "Only ZIP files. Export from Snapchat Settings > My Data."
- Too large: "Over the 5 GB limit. Try splitting into smaller batches."
- Corrupted: "This ZIP is damaged. Try exporting again from Snapchat."

---

### SCREEN 3: Dashboard

**Header**: "Your Jobs" H1 + "New Upload" snap-yellow button (right)

**Stat Cards** (3-col, yellow top border):
- "Total Memories" — value in snap-yellow
- "Avg Match Rate" — value in green
- "Storage Usage" — value in white + thin yellow progress bar

**Section header**: "Job History" with horizontal rule

**Job Cards**:
- Active: yellow left border, pulsing glow, "Processing..." badge with spinner, progress bar, percentage, "Cancel" outline button
- Completed: green left border, "Done" green badge, stats line, "View Results" + "Download" buttons
- Failed: red left border, "Failed" red badge, error message, "Retry" + "Delete" buttons

**Pagination**: "Load More" snap-yellow outline button

**Empty state**: "No jobs yet. Ready to rescue your memories?" + "UPLOAD YOUR FIRST EXPORT" CTA

---

### SCREEN 4: Job Progress (SSE)

**Breadcrumb**: "Dashboard > Job #{{ job_id }}" (mono, yellow separator)

**H1**: "Rescuing your memories..." (italic, uppercase)

**Progress subtitle**: "Phase 2 of 4 | 35% complete | Started 5 minutes ago" (snap-yellow, mono)

**Progress bar**: Full-width, snap-yellow fill with animated caution-stripe pattern, "Extraction in progress" overlay text

**Phase Cards** (4-col grid):
- Phase 1 INGEST — completed (green border, checkmark, "Done")
- Phase 2 MATCH — active (yellow border, pulsing glow, mini bar, "Active 62%")
- Phase 3 ENRICH — pending (gray border, lock icon, "Waiting")
- Phase 4 EXPORT — pending (gray border, lock icon, "Waiting")

**Log Terminal** (yellow border, yellow glow):
- Header: "LIVE FEED" + blinking yellow dot
- Content in hacker-green with yellow timestamps:
```
[14:23:01] Scanning export archive... 3.2 GB
[14:23:03] Found 4,312 media files
[14:23:04] Phase 1 complete: 4,312 assets ingested
[14:23:05] Starting match phase...
[14:23:08] Strategy: exact_media_id — 2,100 matches (100% confidence)
[14:23:12] Strategy: memory_uuid — 412 matches (100% confidence)
[14:23:15] Strategy: timestamp_type — processing...
```
- Blinking cursor at end

**Bottom bar**:
- Left: "Back to Dashboard" (yellow outline)
- Right: "ABORT MISSION" (red bg, danger icon, red glow)

---

### SCREEN 5: Results (3 Tabs)

**Nav status**: "Status: Complete" with green pulse dot

**Sticky header**: "Mission Complete." H1 + "DOWNLOAD RESULTS" snap-yellow button

**Subtitle**: "Completed: Feb 24, 2026 at 14:47" (mono, muted)

**Section label**: "After-Action Report" (centered, ruled lines)

**Tabs**: Summary | Matches (1,243) | Assets (2,100)
- Active: yellow underline (4px), white text
- Inactive: gray text
- Count badges: snap-yellow circles with black numbers

**Summary Tab**:
- 4 stat cards (yellow top border): Snapchats Found | Successfully Matched | Match Confidence | Locations Recovered
- Breakdown table: "Organized by type" — columns: Type | Found | Matched | GPS Coverage — GPS color-coded
- Timeline table: "Processing timeline" — Phase | Duration — caution-tape separator before Total row

**Footer**: "Ready to get your files?" + "GO TO DOWNLOAD" button

---

### SCREEN 6: Download Page

**H1**: "Extraction Complete." (centered, massive)

**Subtitle**: "Your files are ready for pickup."

**Download card** (yellow border, glow):
- Large download icon in yellow
- "DOWNLOAD EVERYTHING AS ZIP" (full-width snap-yellow button, glow shadow)
- File size below

**File tree**: "Or grab individual files"
- Expandable `<details>` folders: memories/, chats/, stories/, metadata/
- 12-col grid: path | size | Download link
- Yellow folder icons, file icons

**Info card** (yellow left border):
- "What's Next"
- "Your files have GPS, dates, and creator metadata embedded. Import the memories/ folder into Immich, Apple Photos, or Google Photos."
- Guide links in snap-yellow

**Footer links**: "View Results" | "Back to Dashboard"

**Parting shot**: "Files available for 30 days. Unlike Snapchat, we'll warn you first."

---

## What NOT to Include (Stitch went too far)

These elements appeared in the Stitch mockups but should NOT be in production:

| Element | Why it's cut |
|---------|-------------|
| "Breach System" / "Breach their settings" | We're not breaching anything |
| "Infiltrator ID: snap_rebel_alpha-6" | Cringe |
| "Bypassing legacy cloud gateways" | Fake hacker movie |
| "Decryption keys injected" | We don't decrypt anything |
| "Tunneling through segment_0x442" | Meaningless |
| "SECURE_CHANNEL_READY" | Unnecessary |
| "SNATCHED_OS_V2.0" watermark | Over-designed |
| "COORD: 34.0195° N" watermark | Random GPS coords in UI |
| "Proprietary Rebel Protocol" | Trying too hard |
| "Security Clearance: Level 4" | Not a spy movie |
| "Terms of Siege" | Cute but unusable for real T&C |
| "Privacy Breach Policy" | Same |
| "Injection Protocol" | Sounds like malware |
| "weaponized with EXIF metadata" | We embed metadata, not weapons |
| "End-to-end extraction enabled" | Implies more security than exists |
| "No traces left behind" | Sounds like evidence destruction |
| Random stock photo avatars | Will be replaced with user initials |
| © 2024 | Wrong year (2026) |
| rounded-2xl on download card | All other cards are sharp corners |
| rounded-full on user avatar | Dashboard uses square; be consistent |

---

## Production Notes

### Pico CSS vs Tailwind
The Stitch mockups use Tailwind CDN. Production uses Pico CSS v2.
Translation approach:
- Pico handles base typography, dark mode, form elements
- Custom CSS in `static/style.css` handles rebellion-specific styles (caution tape, glow, glitch)
- CSS variables map 1:1 (Pico uses data-theme, we add our color vars)
- No Tailwind in production — convert utility classes to semantic CSS

### Font Loading
- Inter: Google Fonts (or self-host for performance)
- JetBrains Mono: Google Fonts (terminal/mono only)
- Material Symbols Outlined: Google Fonts
- Pico handles fallbacks

### htmx Integration
- All templates are Jinja2 with htmx attributes
- Partial templates (_job_cards.html, _match_rows.html, _asset_rows.html) return HTML fragments
- SSE via htmx hx-sse for job progress
- Tab switching is client-side (no reload)

### Accessibility (WCAG 2.1 AA)
- Snap yellow on deep-black passes 4.5:1 contrast
- Hacker green on black passes
- All status indicators use color + text + icon (not color alone)
- aria-live on phase status changes
- aria-live="off" on log terminal (errors only)
- Skip links, semantic headings, keyboard navigation
- Touch targets 44px+ on mobile
