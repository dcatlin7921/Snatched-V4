# Snatched v3 UX Fixes — Prioritized Checklist
**2026-02-26 | Real-user polish work**

---

## SPRINT 1: QUICK WINS (1-2 hours) — Do first

These are 5-10 minute CSS tweaks or copy changes. **Huge ROI on user experience.**

### [ ] 1.1 Form Focus States (5 min)
**File**: `static/style.css`
**What**: Add snap-yellow focus ring to all input fields.
**Why**: Login, register, settings forms don't feel rebellion-themed. Default blue/grey browser focus is generic.

```css
/* Add to style.css around line 400 (after button styles) */
input[type="text"]:focus,
input[type="password"]:focus,
input[type="email"]:focus,
input[type="search"]:focus,
textarea:focus,
select:focus {
    outline: none !important;
    border-color: var(--snap-yellow) !important;
    box-shadow: 0 0 0 3px rgba(255, 252, 0, 0.15) !important;
}
```

**Test**: Visit login page, click username field, verify snap-yellow ring appears.

---

### [ ] 1.2 Upload Drag Zone Visual Feedback (8 min)
**File**: `static/style.css`
**Current**: `.upload-zone` has minimal styling. On hover, background barely changes.
**What**: Add visible dashed border + icon feedback.

```css
/* Find .upload-zone (around line 836) and update */
.upload-zone {
    border: 2px dashed var(--snap-yellow);
    border-radius: 6px;
    background: rgba(255, 252, 0, 0.02);
    transition: all 0.2s ease;
    padding: 3rem 2rem;
    text-align: center;
    cursor: pointer;
    position: relative;
}

.upload-zone:hover,
.upload-zone.highlight {
    background: rgba(255, 252, 0, 0.08);
    border-color: var(--snap-yellow);
    box-shadow: inset 0 0 20px rgba(255, 252, 0, 0.1);
}

.upload-zone .upload-icon {
    font-size: 3rem;
    color: var(--snap-yellow);
    margin-bottom: 1rem;
}
```

**Test**: Visit /upload, verify dashed yellow border is visible, background changes on hover.

---

### [ ] 1.3 Disabled Tool Links Styling (5 min)
**File**: `static/style.css`
**Current**: Disabled tools have `disabled` class but no visual styling.
**What**: Grey out disabled tools, prevent clicking.

```css
/* Add after .tool-link styles (around line 1400) */
.tool-link.disabled,
.tool-link:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    pointer-events: none;
    color: var(--text-dim) !important;
}
```

**Test**: Visit /job/{id} during ingest, check Tools sidebar — GPS and Albums should be greyed out (available after Enrich).

---

### [ ] 1.4 Table Row Hover (3 min)
**File**: `static/style.css`
**Current**: No row hover feedback in file tables.
**What**: Add subtle row highlight on hover.

```css
/* Find `table tbody tr:hover` (around line 979) and update */
table tbody tr:hover {
    background: rgba(255, 252, 0, 0.05);
    transition: background 0.1s;
}
```

**Test**: Visit /upload page, hover over file rows in table — subtle yellow tint appears.

---

### [ ] 1.5 Download Page Hero Count (10 min)
**File**: `download.html`
**Current**: Rescue count is in small stat card (Stats Grid). Spec says it should be hero-sized.
**What**: Move/add large snap-yellow count to hero section.

**In `download.html`, find the hero section (lines 4-8) and update:**

```html
<!-- Hero -->
<div class="text-center download-hero">
    <h1 class="download-hero-title">
        <span style="color: var(--snap-yellow); font-size: 1.4em;">{{ file_count }}</span><br>
        Memories Rescued
    </h1>
    <p class="text-muted download-hero-subtitle">Your files are ready for pickup.</p>
</div>
```

**CSS tweak** in `style.css`:

```css
.download-hero-title {
    font-size: 2.5rem;
    font-weight: 900;
    margin-bottom: 1rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
```

**Test**: Visit /download/{id}, verify large snap-yellow number appears at top of page.

---

### [ ] 1.6 Login Error Styling (5 min)
**File**: `static/style.css`
**Current**: Error message appears but with unclear styling (could be red, could be grey).
**What**: Make error obvious with red border + background.

```css
/* Add after .auth-card styles (around line 1750) */
.auth-error {
    background: rgba(231, 76, 60, 0.2);
    border-left: 3px solid var(--danger);
    color: var(--danger);
    padding: 1rem;
    margin-bottom: 1rem;
    border-radius: 4px;
    font-weight: 600;
    font-size: 0.9rem;
}
```

**Test**: Visit /login, enter wrong password, verify red-left border + background appears.

---

## SPRINT 2: MEDIUM EFFORT (4-8 hours) — High impact

### [ ] 2.1 Dashboard htmx Loading Spinner
**File**: `dashboard.html`
**Current**: Text "Loading active jobs..." with no visual indicator.
**What**: Add spinning animation while htmx fetches content.

**In `dashboard.html`, replace the htmx divs:**

```html
<!-- Active Jobs -->
<section>
    <h2>Active Jobs</h2>
    <div id="active-jobs" class="htmx-container">
        <div class="htmx-loading">
            <div class="spinner"></div>
            <p class="text-muted">Loading active jobs...</p>
        </div>
        <div hx-get="/api/jobs/html?status=running,pending,scanned"
             hx-trigger="load, every 2s"
             hx-target="this"
             hx-swap="innerHTML"></div>
    </div>
</section>
```

**CSS for spinner:**

```css
.htmx-loading {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1rem;
    padding: 2rem;
}

.spinner {
    width: 24px;
    height: 24px;
    border: 2px solid rgba(255, 252, 0, 0.3);
    border-top-color: var(--snap-yellow);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
}

@keyframes spin {
    to { transform: rotate(360deg); }
}

.htmx-request .htmx-loading {
    display: flex;
}

.htmx-request .htmx-content {
    display: none;
}
```

**JavaScript to toggle spinner:**

```javascript
// In dashboard.html <script> block
document.body.addEventListener('htmx:xhr:loadstart', function(evt) {
    var loader = evt.detail.xhr.target.querySelector('.htmx-loading');
    if (loader) loader.style.display = 'flex';
});

document.body.addEventListener('htmx:afterSettle', function(evt) {
    var loader = evt.detail.target.querySelector('.htmx-loading');
    if (loader) loader.style.display = 'none';
});
```

**Test**: Visit /dashboard, verify spinner appears while jobs load, disappears when content arrives.

---

### [ ] 2.2 Job Gallery Loading State
**File**: `job.html`
**Current**: Empty grid `<div id="gallery-grid" ...>` while htmx loads. No visual feedback.
**What**: Show placeholder thumbnails or spinner while gallery htmx endpoint responds.

**In `job.html`, update the gallery div (lines 84-93):**

```html
<div id="view-gallery" class="view-panel">
    <div id="gallery-grid" class="gallery-grid">
        {% if phase_idx < 2 %}
        <div class="empty-state">
            <p>Gallery will populate during matching...</p>
        </div>
        {% else %}
        <!-- Loading state with htmx placeholder -->
        <div class="gallery-loading">
            <div class="spinner"></div>
            <p class="text-muted">Loading gallery...</p>
        </div>
        {% endif %}
    </div>
</div>

<!-- Add htmx trigger after DOMContentLoaded -->
<script>
document.addEventListener('DOMContentLoaded', () => {
    const grid = document.getElementById('gallery-grid');
    if (grid && phase_idx >= 2) {
        grid.innerHTML = `<div class="spinner"></div><p class="text-muted">Loading gallery...</p>`;
        htmx.ajax('GET', '/api/jobs/' + JOB_ID + '/gallery/html', '#gallery-grid');
    }
});
</script>
```

**CSS:**

```css
.gallery-loading {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 1rem;
    padding: 4rem 2rem;
    min-height: 300px;
}
```

**Test**: Visit /job/{id}, switch to Timeline or Map tabs, verify spinner appears while loading.

---

### [ ] 2.3 Countdown Modal Mobile Breakpoint
**File**: `static/style.css`
**Current**: Countdown modal + export config panel don't have mobile-specific rules.
**What**: Stack content vertically on mobile (480px), adjust font sizes.

```css
/* Add at end of file, before last closing brace */
@media (max-width: 480px) {
    .countdown-modal__content {
        padding: 1.5rem 1rem;
        border-radius: 8px;
        max-height: 90vh;
        overflow-y: auto;
    }

    .countdown-modal__timer {
        font-size: 3rem;
        margin-bottom: 0.5rem;
    }

    .countdown-modal__phase {
        font-size: 0.9rem;
    }

    #export-config-panel {
        margin: 0.75rem 0;
        padding: 0.75rem;
    }

    #export-config-panel label {
        font-size: 0.8rem;
        margin-bottom: 0.5rem;
    }

    .btn-yellow.btn-large {
        width: 100%;
        padding: 0.75rem 1rem;
        font-size: 0.9rem;
    }

    .btn-secondary {
        width: 100%;
        padding: 0.75rem 1rem;
        font-size: 0.9rem;
    }
}
```

**Test**: Resize browser to 480px, visit /job/{id}, wait for countdown modal, verify everything fits and is readable.

---

### [ ] 2.4 Results Page Report Consolidation
**File**: `results.html`
**Current**: Reports shown in sticky header dropdown AND in Summary tab section. Redundant.
**What**: Remove duplicate "Download Reports" section from Summary tab.

**In `results.html`, find line 258 ("Download Reports" section) and DELETE:**

```html
<!-- DELETE THIS SECTION (lines 258-264) -->
<section class="results-section">
    <h3 class="results-section-title">Download Reports</h3>
    <div class="gap-row">
        <a href="/api/jobs/{{ job_id }}/report?format=json" class="btn-outline btn-sm">JSON Report</a>
        <a href="/api/jobs/{{ job_id }}/report?format=csv" class="btn-outline btn-sm">CSV Report</a>
    </div>
</section>
```

**Why**: User already has Reports button in sticky header. Redundancy is confusing.

**Test**: Visit /results/{id}, Summary tab, verify "Download Reports" section is gone. Check sticky header still has Reports button.

---

### [ ] 2.5 Tools Sidebar Mobile Drawer
**File**: `job.html` + `static/style.css`
**Current**: Tools sidebar is hidden on mobile (not responsive).
**What**: Add toggle button (hamburger) to show/hide sidebar on mobile.

**In `job.html`, add before the tools-sidebar div (line 119):**

```html
<!-- Tools Sidebar Toggle (mobile only) -->
<button id="tools-toggle" class="tools-toggle hidden-desktop" onclick="toggleToolsSidebar()" title="Open tools menu">
    <span class="material-symbols-outlined">build</span>
</button>
```

**Update the tools-sidebar (line 120):**

```html
<div id="tools-sidebar" class="tools-sidebar {% if job.status not in ('matched', 'enriched', 'completed') %}hidden{% endif %}">
    <button class="tools-close hidden-mobile" onclick="toggleToolsSidebar()" title="Close">
        <span class="material-symbols-outlined">close</span>
    </button>
    <h3>Tools</h3>
    ...
</div>
```

**CSS in `style.css`:**

```css
.tools-toggle {
    display: none;
    position: fixed;
    bottom: 2rem;
    right: 2rem;
    width: 56px;
    height: 56px;
    border-radius: 50%;
    background: var(--snap-yellow);
    color: #000;
    border: none;
    cursor: pointer;
    z-index: 999;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    font-size: 1.5rem;
}

.tools-toggle:hover {
    background: #ffff00;
    transform: scale(1.1);
}

@media (max-width: 768px) {
    .tools-toggle {
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .tools-sidebar {
        position: fixed;
        top: 0;
        right: 0;
        width: 100%;
        max-width: 300px;
        height: 100vh;
        background: var(--charcoal);
        border-left: 1px solid var(--border-dark);
        padding: 1rem;
        z-index: 998;
        transform: translateX(100%);
        transition: transform 0.3s ease;
    }

    .tools-sidebar.visible {
        transform: translateX(0);
    }

    .tools-close {
        display: block;
        position: absolute;
        top: 1rem;
        right: 1rem;
        background: none;
        border: none;
        color: var(--text-primary);
        cursor: pointer;
        font-size: 1.5rem;
    }
}

.hidden-mobile { display: none; }
.hidden-desktop { display: none; }

@media (max-width: 768px) {
    .hidden-mobile { display: none !important; }
    .hidden-desktop { display: block !important; }
}
```

**JavaScript in `job.html` <script>:**

```javascript
function toggleToolsSidebar() {
    const sidebar = document.getElementById('tools-sidebar');
    const toggle = document.getElementById('tools-toggle');
    if (sidebar) {
        sidebar.classList.toggle('visible');
    }
}
```

**Test**: Resize to mobile (480px), visit /job/{id}, click tools button, verify drawer slides in from right.

---

### [ ] 2.6 Viz-Band Density Visualization (6-8 hours)
**File**: `job.html` + `static/style.css` + backend API
**Current**: Viz-band shows phase labels and stats. No file-type segmentation or duplicate density.
**What**: Rebuild viz-band to show:
  - Colored segments by file type (photos warm white, videos amber, chats steel blue, other grey)
  - Duplicate density as darker saturation
  - Animated fill as files are counted

**This requires backend data first.** The `/api/jobs/{id}/stream` endpoint needs to send file-type breakdown and duplicate info.

**For now, create the frontend placeholder:**

**In `job.html`, replace the viz-band (lines 5-30) with:**

```html
<!-- DATA VIZ BAND — pinned to top -->
<div id="viz-band" class="viz-band">
    <div class="viz-band__header">
        <div class="viz-band__phases">
            <span class="viz-phase {% if phase_idx >= 1 %}viz-phase--done{% elif phase_idx == 0 %}viz-phase--active{% endif %}" data-phase="ingest">INGEST</span>
            <span class="viz-phase-arrow">▸</span>
            <span class="viz-phase {% if phase_idx >= 2 %}viz-phase--done{% elif phase_idx == 1 %}viz-phase--active{% endif %}" data-phase="match">MATCH</span>
            <span class="viz-phase-arrow">▸</span>
            <span class="viz-phase {% if phase_idx >= 3 %}viz-phase--done{% elif phase_idx == 2 %}viz-phase--active{% endif %}" data-phase="enrich">ENRICH</span>
            <span class="viz-phase-arrow">▸</span>
            <span class="viz-phase {% if phase_idx >= 4 %}viz-phase--done{% elif phase_idx == 3 %}viz-phase--active{% endif %}" data-phase="export">EXPORT</span>
        </div>
        <div class="viz-band__stats" id="viz-stats">
            <span id="stat-files">{{ stats.total_assets or '—' }} files</span>
            <span id="stat-daterange">{{ stats.date_range or '' }}</span>
            <span id="stat-matchrate" class="{% if stats.match_rate is not none %}{% if stats.match_rate >= 0.85 %}text-green{% elif stats.match_rate >= 0.60 %}text-warning{% else %}text-danger{% endif %}{% endif %}">
                {% if stats.match_rate is not none %}{{ (stats.match_rate * 100) | round(1) }}% matched{% endif %}
            </span>
            <span id="stat-gps">{% if stats.gps_count %}{{ stats.gps_count }} GPS{% endif %}</span>
        </div>
    </div>

    <!-- File-type segmented bar -->
    <div class="viz-band__segments" id="viz-segments">
        <div class="segment segment-photos" style="flex: 0;"></div>
        <div class="segment segment-videos" style="flex: 0;"></div>
        <div class="segment segment-chats" style="flex: 0;"></div>
        <div class="segment segment-other" style="flex: 0;"></div>
    </div>

    <!-- Main progress bar (below segments) -->
    <div class="viz-band__progress">
        <div class="progress-bar">
            <div class="progress-fill" id="phase-progress" style="width: {{ job.progress_pct or 0 }}%"></div>
        </div>
        <span class="mono" id="progress-eta"></span>
    </div>
</div>
```

**CSS in `style.css` (add around line 1000):**

```css
.viz-band {
    background: var(--charcoal);
    border-bottom: 1px solid var(--border-dark);
    padding: 1.5rem;
    margin-bottom: 2rem;
}

.viz-band__header {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 2rem;
    margin-bottom: 1rem;
}

.viz-band__phases {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.9rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}

.viz-phase {
    padding: 0.5rem 1rem;
    border-radius: 4px;
    background: rgba(255, 255, 255, 0.05);
    color: var(--text-dim);
    transition: all 0.3s ease;
}

.viz-phase--active {
    background: rgba(255, 252, 0, 0.2);
    color: var(--snap-yellow);
    box-shadow: 0 0 12px rgba(255, 252, 0, 0.3);
}

.viz-phase--done {
    background: rgba(76, 175, 80, 0.2);
    color: var(--success);
}

.viz-phase-arrow {
    color: var(--text-dim);
    font-size: 0.8rem;
    margin: 0 0.25rem;
}

.viz-band__stats {
    display: flex;
    gap: 1.5rem;
    align-items: center;
    font-size: 0.85rem;
    color: var(--text-muted);
    text-align: right;
}

.viz-band__segments {
    display: flex;
    gap: 2px;
    height: 12px;
    margin-bottom: 1rem;
    border-radius: 4px;
    overflow: hidden;
    background: rgba(0, 0, 0, 0.2);
}

.segment {
    flex: 1;
    transition: flex 0.3s ease, opacity 0.3s ease;
}

.segment-photos {
    background: linear-gradient(90deg, #fff8dc, #ffd700);
}

.segment-videos {
    background: linear-gradient(90deg, #ff9500, #ff6d00);
}

.segment-chats {
    background: linear-gradient(90deg, #64b5f6, #1976d2);
}

.segment-other {
    background: linear-gradient(90deg, #9e9e9e, #616161);
}

.viz-band__progress {
    display: flex;
    align-items: center;
    gap: 1rem;
}

.progress-bar {
    flex: 1;
    height: 8px;
    background: rgba(255, 252, 0, 0.1);
    border-radius: 4px;
    overflow: hidden;
}

.progress-fill {
    height: 100%;
    background: var(--snap-yellow);
    transition: width 0.2s ease;
    box-shadow: 0 0 8px rgba(255, 252, 0, 0.5);
}

.progress-eta {
    font-size: 0.8rem;
    color: var(--text-muted);
    white-space: nowrap;
}
```

**Backend change needed:** The `/api/jobs/{id}/stream` progress events should include file-type breakdown:

```json
{
  "type": "progress",
  "progress_pct": 45,
  "message": "~2 minutes remaining",
  "segments": {
    "photos": 2400,
    "videos": 1200,
    "chats": 300,
    "other": 150
  }
}
```

Then update JavaScript in `job.html` to animate segments:

```javascript
function updateSegments(data) {
    if (!data.segments) return;
    const total = Object.values(data.segments).reduce((a, b) => a + b, 0);
    const band = document.getElementById('viz-segments');
    if (band) {
        band.querySelectorAll('.segment').forEach((seg, i) => {
            const type = ['photos', 'videos', 'chats', 'other'][i];
            const count = data.segments[type] || 0;
            seg.style.flex = Math.max(0.5, count / total * 100);
        });
    }
}
```

**Test**: During ingest, watch the progress bar fill. Colors should start appearing as files are counted.

---

## SPRINT 3: POLISH (2-4 hours) — Nice-to-have

### [ ] 3.1 Results Page Labels
**File**: `results.html`
**Change**: "After-Action Report" → "Detailed Analysis"
Line 157: Change section label.

---

### [ ] 3.2 Download Page Speed-Run Explanation
**File**: `download.html`
**Add**: Small note explaining why power users see "individual files" section and speed users don't.

```html
{% if not is_speed_run %}
<section class="download-tree-section">
    <div class="section-header download-tree-header">
        <h2 class="mb-0">Or grab individual files</h2>
        <span class="mono text-muted uppercase tracking-wide download-manifest-label">Manifest v1.0</span>
    </div>
    <p class="text-muted" style="font-size: 0.85rem; margin-bottom: 1rem;">
        Download individual folders or files. (Speed-run jobs download as a single ZIP.)
    </p>
    ...
</section>
{% endif %}
```

---

### [ ] 3.3 Retention Warning Modal
**File**: `download.html` + `static/style.css`
**Add**: On first visit to download page, show a modal: "Your files expire in 30 days. Plan accordingly."

```html
<div id="retention-warning" class="modal-overlay">
    <div class="modal-content">
        <h3>Files Available for 30 Days</h3>
        <p>Unlike Snapchat, we'll warn you first. Download your rescued memories before expiration.</p>
        <button class="btn-primary" onclick="dismissRetention()">Got it</button>
    </div>
</div>

<script>
function dismissRetention() {
    document.getElementById('retention-warning').classList.add('hidden');
    localStorage.setItem('retention-warning-seen', '1');
}

window.addEventListener('load', () => {
    if (!localStorage.getItem('retention-warning-seen')) {
        document.getElementById('retention-warning').classList.remove('hidden');
    }
});
</script>
```

---

## Testing Checklist

**After implementing fixes, test:**

- [ ] **Desktop (1920x1080)**: All pages render correctly. Buttons have snap-yellow hover states.
- [ ] **Tablet (768px)**: Sidebar reflows. Countdown modal fits. Gallery is scrollable.
- [ ] **Mobile (480px)**: Tools drawer works. Download page hero count is visible. Form focus states are clear.
- [ ] **Network throttle (3G)**: Spinners appear while htmx loads. User gets feedback that page is working.
- [ ] **Dark mode (default)**: All colors have sufficient contrast. Text is readable.
- [ ] **Keyboard navigation**: All buttons, links, form fields are tab-accessible. Tab order is logical.
- [ ] **Empty states**: Job page shows "Gallery will populate during matching..." — visible and clear.

---

## Priority Matrix

| Fix | Time | Impact | Do When |
|-----|------|--------|---------|
| Form focus states (1.1) | 5 min | High | Sprint 1, first |
| Drag zone border (1.2) | 8 min | Medium | Sprint 1 |
| Disabled tools (1.3) | 5 min | Medium | Sprint 1 |
| Download hero count (1.5) | 10 min | High | Sprint 1 |
| Viz-band density (2.6) | 6-8 hrs | High | Sprint 2, if time allows |
| Tools sidebar mobile (2.5) | 4 hrs | Medium | Sprint 2 |
| Countdown modal mobile (2.3) | 30 min | Medium | Sprint 2 |
| Dashboard spinner (2.1) | 1 hr | Low | Sprint 2 |
| Results consolidation (2.4) | 20 min | Low | Sprint 2 |

**Recommended**: Complete Sprint 1 (1-2 hours), then do Sprint 2 items 2.6 and 2.5.

---

**End checklist.**
