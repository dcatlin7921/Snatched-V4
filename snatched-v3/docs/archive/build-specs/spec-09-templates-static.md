# SPEC-09: Templates & Static Files

**Status:** Final
**Version:** 3.0
**Date:** 2026-02-23

---

## Module Overview

Spec-09 defines the front-end layer: 8 Jinja2 HTML templates and minimal static CSS/JS. The design is **server-rendered with htmx** — no SPA, no build step, no custom JavaScript beyond what htmx and minimal inline scripts provide.

**Stack:**
- **HTML/Templates:** Jinja2 (rendered server-side by FastAPI)
- **CSS:** Pico CSS (~10 KB, classless framework) loaded from CDN + custom overrides (~2 KB)
- **JavaScript:** htmx 2.x (~14 KB, vendored) — the ONLY JS dependency
- **Progressive Enhancement:** Forms work without JS; htmx adds AJAX interactivity

**Philosophy:**
- Server renders all HTML; no client-side routing
- htmx handles: file uploads with indicator, SSE streaming, pagination, polling
- No React, Vue, or other SPA framework
- Fast page loads; graceful degradation if JS disabled

**V2 source file:** `/home/dave/tools/snapfix/snatched.py`
The banner/results printing (lines 4140–4404) is replicated in the `results.html` template.

---

## Files to Create

```
snatched/
├── templates/
│   ├── base.html              # Layout shell (nav, CSS/JS includes, flash messages)
│   ├── landing.html           # Welcome page
│   ├── upload.html            # Drag-drop file upload form
│   ├── dashboard.html         # Job cards + progress polling
│   ├── job_progress.html      # Real-time SSE progress page
│   ├── results.html           # Results browser (tabs: summary, matches, assets)
│   ├── download.html          # Download manager (file tree, ZIP export)
│   └── error.html             # Error display page
└── static/
    ├── style.css              # Pico CSS overrides + custom component styles
    └── htmx.min.js            # Vendored htmx 2.0+ (DO NOT EDIT)
```

---

## Dependencies

**Built after:**
- spec-08 (FastAPI routes define context variables passed to templates)

**Jinja2 context variables** are defined by the route handlers in `snatched/routes/pages.py` and `snatched/routes/api.py` (spec-08). Each template section below documents the exact context expected.

**Pico CSS:** Loaded from CDN (`https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css`). For offline/air-gapped deployments, vendor this file into `snatched/static/pico.min.css` and update the `<link>` in `base.html`.

**htmx:** Vendored from `https://unpkg.com/htmx.org@2.0.0/dist/htmx.min.js`. Download once and commit to the repo. Do not load from CDN at runtime.

---

## V2 Source Reference

N/A — Templates are new in v3 (v2 was CLI-only). However, the **results/stats display** is informed by v2's terminal banner output at `/home/dave/tools/snapfix/snatched.py` lines 4140-4404. The `print_banner()` function renders match counts, GPS coverage, phase timings, and per-strategy breakdowns — the `results.html` template replicates this layout in HTML.

---

## Function Signatures

N/A — Templates are Jinja2 HTML files, not Python modules. They have no callable functions. The Jinja2 context variables each template expects are documented in the template descriptions below.

---

## Multi-User Adaptation

All templates are multi-user safe by design:

1. **User-scoped data** — Route handlers filter all queries by the authenticated user before passing context to templates. Templates never see other users' data.
2. **Username display** — `base.html` displays the current username from `{{ username }}` context variable (extracted from Authelia's `X-Remote-User` header).
3. **Job isolation** — Dashboard and results pages only show jobs belonging to the current user. Job IDs in URLs are validated server-side.
4. **No client-side secrets** — Templates never render API keys, database passwords, or internal paths. All sensitive data stays server-side.

---

## Code Examples

### htmx Upload with Progress

```html
<!-- upload.html: drag-drop file upload with htmx -->
<form hx-post="/api/upload"
      hx-encoding="multipart/form-data"
      hx-target="#upload-result"
      hx-indicator="#upload-spinner">
  <input type="file" name="export_zip" accept=".zip" required>
  <button type="submit">Upload & Process</button>
  <span id="upload-spinner" class="htmx-indicator">Uploading...</span>
</form>
<div id="upload-result"></div>
```

### SSE Job Progress

```html
<!-- job_progress.html: real-time progress via SSE -->
<div hx-ext="sse" sse-connect="/api/jobs/{{ job.id }}/stream">
  <div sse-swap="progress">Waiting for updates...</div>
  <div sse-swap="phase_start" hx-swap="innerHTML">
    <span>Starting...</span>
  </div>
  <div sse-swap="complete">
    <a href="/results/{{ job.id }}">View Results</a>
  </div>
</div>
```

### Paginated Table

```html
<!-- results.html: paginated match table -->
<div id="matches-table"
     hx-get="/api/matches/{{ job.id }}?page=1"
     hx-trigger="load"
     hx-swap="innerHTML">
  Loading matches...
</div>
```

---

## Database Schema

Templates do not interact with the database directly. All data is passed as Jinja2 context variables from route handlers in `snatched/routes/pages.py`.

For reference, the key data shapes templates receive:

```python
# Job object shape (from processing_jobs table):
{
    "id": 42,
    "status": "completed",           # pending | running | completed | failed | cancelled
    "progress_pct": 100,
    "current_phase": "export",
    "created_at": datetime,
    "started_at": datetime | None,
    "completed_at": datetime | None,
    "error_message": str | None,
    "stats_json": {                  # populated on completion
        "total_assets": 12847,
        "total_matches": 9284,
        "gps_coverage": 67.3,
        "by_lane": {
            "memories": {"assets": 8000, "matched": 7200, "gps": 5400},
            "chats":    {"assets": 4000, "matched": 3800, "gps": 0},
            "stories":  {"assets": 847,  "matched": 284,  "gps": 184},
        },
        "phase_durations": {
            "ingest": 45.2,
            "match": 120.8,
            "enrich": 38.1,
            "export": 210.5,
        }
    }
}
```

---

## Templates (8 Files)

### 1. `snatched/templates/base.html` — Layout Shell

**Purpose:** Root template. All other templates extend this via `{% extends "base.html" %}`.

**Context variables:**
- `request` — FastAPI/Starlette Request object (required by Jinja2)
- `username` — Authenticated username (str)
- `title` — Page title (str, optional; default: "Snatched v3")
- `flash_messages` — `list[tuple[str, str]]` of (category, message) (optional)

**htmx attributes:** None (shell only)

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title or "Snatched v3" }}</title>

    <!-- Pico CSS: classless semantic framework -->
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css">

    <!-- Custom styles -->
    <link rel="stylesheet" href="{{ url_for('static', path='style.css') }}">

    <!-- htmx 2.x (vendored, do not edit) -->
    <script src="{{ url_for('static', path='htmx.min.js') }}" defer></script>
</head>
<body>
    <!-- Navigation bar -->
    <nav class="navbar">
        <div class="nav-container">
            <h2><a href="/">Snatched v3</a></h2>
            <ul class="nav-menu">
                <li><a href="/dashboard">Dashboard</a></li>
                <li><a href="/upload">Upload</a></li>
                <li><span class="user-info">{{ username }}</span></li>
            </ul>
        </div>
    </nav>

    <!-- Main content -->
    <main class="container">
        <!-- Flash messages -->
        {% if flash_messages %}
            {% for category, message in flash_messages %}
                <div class="alert alert-{{ category }}">
                    {{ message }}
                    <button aria-label="Close" onclick="this.parentElement.style.display='none';">x</button>
                </div>
            {% endfor %}
        {% endif %}

        {% block content %}{% endblock %}
    </main>

    <!-- Footer -->
    <footer>
        <p>Snatched v3 — Snapchat Export Processor</p>
    </footer>

    <!-- htmx global config -->
    <script>
        htmx.config.timeout = 30000;
        htmx.config.historyEnabled = false;
        htmx.config.refreshOnHistoryMiss = true;
    </script>
</body>
</html>
```

---

### 2. `snatched/templates/landing.html` — Welcome Page

**Purpose:** Entry point for authenticated users. Links to /upload and /dashboard.

**Context variables:**
- `username` — Authenticated username

**htmx attributes:** None

```html
{% extends "base.html" %}

{% block content %}
<article>
    <h1>Welcome, {{ username }}</h1>
    <p>Snatched is a Snapchat data export processor. Upload your export ZIP to process memories, chats, and stories.</p>

    <section>
        <h2>Get Started</h2>
        <ul>
            <li><a href="/upload" role="button">Upload Export</a></li>
            <li><a href="/dashboard" role="button" class="secondary">View Jobs</a></li>
        </ul>
    </section>

    <section>
        <h2>What Snatched Does</h2>
        <ul>
            <li><strong>Matches</strong> media files to metadata using 6 cascade strategies</li>
            <li><strong>Enriches</strong> with GPS location data and display names</li>
            <li><strong>Exports</strong> files organized by date and type</li>
            <li><strong>Embeds</strong> EXIF and XMP metadata for import into Immich and other tools</li>
        </ul>
    </section>

    <section>
        <h2>How It Works</h2>
        <ol>
            <li>Export your Snapchat data (Settings &rarr; My Data)</li>
            <li>Upload the ZIP file (usually 1–5 GB)</li>
            <li>Snatched processes in 4 phases (10–30 min depending on size)</li>
            <li>Download your organized memories, chats, and stories</li>
        </ol>
    </section>
</article>
{% endblock %}
```

---

### 3. `snatched/templates/upload.html` — Drag-Drop File Upload

**Purpose:** Upload interface with drag-drop zone, file input, processing options, and progress indicator.

**Context variables:**
- `username` — Authenticated username
- `max_upload_bytes` — Max upload size from config (integer bytes, e.g. 5368709120)

**htmx attributes:**
- `hx-post="/api/upload"` — POST to upload endpoint
- `hx-encoding="multipart/form-data"` — Enable file upload
- `hx-target="#upload-status"` — Replace status div with response
- `hx-indicator="#spinner"` — Show spinner element during upload

```html
{% extends "base.html" %}

{% block content %}
<article>
    <h1>Upload Snapchat Export</h1>
    <p>Upload your Snapchat export ZIP. Max size: {{ (max_upload_bytes / 1024 / 1024 / 1024) | round(1) }} GB</p>

    <form hx-post="/api/upload"
          hx-encoding="multipart/form-data"
          hx-target="#upload-status"
          hx-indicator="#spinner"
          enctype="multipart/form-data">

        <!-- Drag-drop zone -->
        <div class="upload-zone" id="dropzone">
            <p>Drag and drop your ZIP file here, or:</p>
            <input type="file" name="file" accept=".zip" id="fileInput" required>
            <label for="fileInput" role="button">Choose File</label>
        </div>

        <!-- Processing options -->
        <fieldset>
            <legend>Processing Options</legend>

            <label>
                <input type="checkbox" name="burn_overlays" checked>
                Burn date/time overlays on memories
            </label>

            <label>
                <input type="checkbox" name="dark_mode_pngs">
                Export chat PNGs in dark mode
            </label>

            <label>
                <input type="checkbox" name="exif_enabled" checked>
                Embed EXIF metadata in output files
            </label>
        </fieldset>

        <button type="submit">Process Export</button>
    </form>

    <!-- Spinner (shown during upload via htmx-indicator) -->
    <div id="spinner" class="htmx-indicator" style="text-align: center; margin: 2rem 0;">
        <div class="spinner"></div>
        <p>Uploading and validating...</p>
    </div>

    <!-- Upload status (replaced by API response) -->
    <div id="upload-status"></div>
</article>

<!-- Drag-drop JavaScript (vanilla, no htmx needed) -->
<script>
const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('fileInput');

['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    dropzone.addEventListener(eventName, e => { e.preventDefault(); e.stopPropagation(); }, false);
});

['dragenter', 'dragover'].forEach(eventName => {
    dropzone.addEventListener(eventName, () => dropzone.classList.add('highlight'), false);
});

['dragleave', 'drop'].forEach(eventName => {
    dropzone.addEventListener(eventName, () => dropzone.classList.remove('highlight'), false);
});

dropzone.addEventListener('drop', e => {
    const files = e.dataTransfer.files;
    if (files.length > 0) fileInput.files = files;
}, false);
</script>

<style>
#dropzone {
    border: 3px dashed #ccc;
    border-radius: 8px;
    padding: 2rem;
    text-align: center;
    cursor: pointer;
    transition: all 0.3s;
}

#dropzone.highlight {
    border-color: #0066cc;
    background-color: #f0f4ff;
}

.spinner {
    border: 4px solid #f3f3f3;
    border-top: 4px solid #0066cc;
    border-radius: 50%;
    width: 40px;
    height: 40px;
    animation: spin 1s linear infinite;
    margin: 0 auto;
}

@keyframes spin {
    0%   { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}
</style>
{% endblock %}
```

---

### 4. `snatched/templates/dashboard.html` — Job Status & History

**Purpose:** List active and completed jobs; show progress with automatic polling.

**Context variables:**
- `username` — Authenticated username

**htmx attributes:**
- `hx-get="/api/jobs?status=running"` — Load active job list
- `hx-trigger="load, every 2s"` — Fetch on load then poll every 2 seconds
- `hx-target="this"` — Replace the container div with response
- `hx-swap="innerHTML"` — Replace inner HTML

```html
{% extends "base.html" %}

{% block content %}
<article>
    <h1>Dashboard</h1>
    <p>Manage your processing jobs.</p>

    <section>
        <h2>Active Jobs</h2>
        <div id="active-jobs"
             hx-get="/api/jobs?status=running"
             hx-trigger="load, every 2s"
             hx-target="this"
             hx-swap="innerHTML">
            <p>Loading active jobs...</p>
        </div>
    </section>

    <section>
        <h2>Job History</h2>
        <div id="job-history"
             hx-get="/api/jobs?status=completed,failed,cancelled"
             hx-trigger="load"
             hx-target="this"
             hx-swap="innerHTML">
            <p>Loading job history...</p>
        </div>
    </section>
</article>

<style>
.job-card {
    border-left: 4px solid #0066cc;
    margin-bottom: 1rem;
    padding: 1.5rem;
}

.job-meta {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1rem;
    margin: 1rem 0;
}

.progress-bar {
    width: 100%;
    height: 24px;
    background-color: #f0f0f0;
    border-radius: 4px;
    overflow: hidden;
    margin: 1rem 0;
}

.progress-fill {
    height: 100%;
    background-color: #0066cc;
    transition: width 0.5s ease;
}

.status-badge {
    display: inline-block;
    padding: 0.25rem 0.75rem;
    border-radius: 4px;
    font-weight: bold;
    font-size: 0.9rem;
}

.status-running    { background-color: #ffffcc; color: #333; }
.status-completed  { background-color: #ccffcc; color: #333; }
.status-failed     { background-color: #ffcccc; color: #333; }
.status-cancelled  { background-color: #eeeeee; color: #666; }

.job-actions {
    display: flex;
    gap: 0.5rem;
    margin-top: 1rem;
}
</style>
{% endblock %}
```

---

### 5. `snatched/templates/job_progress.html` — Real-Time SSE Progress

**Purpose:** Dedicated page showing real-time job progress via Server-Sent Events.

**Context variables:**
- `job_id` — Job ID (integer)
- `job` — Job dict with at least `status` field

**htmx attributes:**
- `hx-ext="sse"` — Enable htmx SSE extension
- `sse-connect="/api/jobs/{job_id}/stream"` — Connect to SSE endpoint
- `sse-swap="log"` — Swap log div on 'log' events

```html
{% extends "base.html" %}

{% block content %}
<article>
    <h1>Processing Job #{{ job_id }}</h1>

    <div class="sse-container" hx-ext="sse" sse-connect="/api/jobs/{{ job_id }}/stream">

        <section>
            <h2>Processing Phases</h2>
            <div class="phases">
                {% for phase_name, phase_label in [
                    ('ingest', 'Phase 1: Ingest'),
                    ('match',  'Phase 2: Match'),
                    ('enrich', 'Phase 3: Enrich'),
                    ('export', 'Phase 4: Export')
                ] %}
                <div class="phase" data-phase="{{ phase_name }}">
                    <div class="phase-header">
                        <h3>{{ phase_label }}</h3>
                        <span class="phase-status">pending</span>
                    </div>
                    <div class="phase-bar">
                        <div class="phase-progress" style="width: 0%"></div>
                    </div>
                    <p class="phase-message"></p>
                </div>
                {% endfor %}
            </div>
        </section>

        <section>
            <h3>Overall Progress</h3>
            <div class="progress-bar">
                <div class="progress-fill" id="overall-progress" style="width: 0%"></div>
            </div>
            <p id="progress-text">0%</p>
        </section>

        <section>
            <h3>Log Output</h3>
            <div id="log-output" class="log-container" sse-swap="log" hx-swap="beforeend">
                <p>Waiting for events...</p>
            </div>
        </section>

        <section id="status-section">
            <p>Job status: <strong id="job-status">{{ job.status }}</strong></p>
        </section>
    </div>

    <div class="action-buttons">
        <a href="/dashboard" role="button" class="secondary">Back to Dashboard</a>
        <a href="/results/{{ job_id }}" role="button" id="results-button" style="display: none;">View Results</a>
    </div>
</article>

<style>
.sse-container { display: grid; gap: 2rem; }

.phases {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1.5rem;
}

.phase {
    border: 1px solid #ddd;
    border-radius: 8px;
    padding: 1.5rem;
    background-color: #fafafa;
}

.phase-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
}

.phase-status {
    display: inline-block;
    padding: 0.25rem 0.75rem;
    border-radius: 4px;
    font-size: 0.85rem;
    font-weight: bold;
}

.phase-status.running   { background-color: #ffffcc; color: #333; }
.phase-status.completed { background-color: #ccffcc; color: #333; }

.phase-bar {
    width: 100%;
    height: 8px;
    background-color: #e0e0e0;
    border-radius: 4px;
    overflow: hidden;
    margin: 1rem 0;
}

.phase-progress {
    height: 100%;
    background-color: #0066cc;
    transition: width 0.5s ease;
}

.log-container {
    background-color: #1e1e1e;
    color: #d4d4d4;
    padding: 1rem;
    border-radius: 4px;
    font-family: monospace;
    font-size: 0.9rem;
    max-height: 300px;
    overflow-y: auto;
    white-space: pre-wrap;
}

.action-buttons { margin-top: 2rem; display: flex; gap: 1rem; }
</style>

<script>
htmx.on('htmx:sseMessage', function(evt) {
    const data = evt.detail.data;

    // Update phase status on phase_start events
    if (evt.detail.type === 'phase_start') {
        const phaseEl = document.querySelector('[data-phase="' + (data.phase || '') + '"]');
        if (phaseEl) {
            const statusEl = phaseEl.querySelector('.phase-status');
            statusEl.textContent = 'running';
            statusEl.classList.add('running');
        }
    }

    // Update overall progress bar
    if (data && data.progress_pct !== undefined) {
        document.getElementById('overall-progress').style.width = data.progress_pct + '%';
        document.getElementById('progress-text').textContent = data.progress_pct + '%';
    }

    // Show results button and update status when complete
    if (evt.detail.type === 'complete') {
        document.getElementById('results-button').style.display = 'inline-block';
        document.getElementById('job-status').textContent = 'completed';
    }
});
</script>
{% endblock %}
```

---

### 6. `snatched/templates/results.html` — Results Browser

**Purpose:** Multi-tab results browser (Summary, Matches, Assets). Replicates the v2 banner output in web form.

**Context variables:**
- `job_id` — Job ID (integer)
- `job` — Job dict including `stats_json` (see Database Schema section above for shape)

**htmx attributes:**
- `hx-get="/api/matches?job_id={job_id}&page=1"` — Load match table
- `hx-trigger="load"` — Load on page load
- `hx-swap="innerHTML"` — Replace table content

```html
{% extends "base.html" %}

{% block content %}
<article>
    <h1>Results &mdash; Job #{{ job_id }}</h1>
    {% if job.completed_at %}
        <p>Completed: {{ job.completed_at.strftime('%Y-%m-%d %H:%M:%S') }}</p>
    {% endif %}

    <!-- Tab Navigation -->
    <nav class="tab-navigation">
        <button class="tab-button active" onclick="openTab(event, 'summary')">Summary</button>
        <button class="tab-button" onclick="openTab(event, 'matches')">Matches</button>
        <button class="tab-button" onclick="openTab(event, 'assets')">Assets</button>
    </nav>

    <!-- Summary Tab -->
    <div id="summary" class="tab-content active">
        <h2>Processing Summary</h2>

        {% if job.stats_json %}
        <div class="stats-grid">
            <div class="stat-card">
                <h3>Total Assets</h3>
                <p class="stat-value">{{ job.stats_json.total_assets | default(0) }}</p>
            </div>
            <div class="stat-card">
                <h3>Matched</h3>
                <p class="stat-value">{{ job.stats_json.total_matches | default(0) }}</p>
            </div>
            <div class="stat-card">
                <h3>Match Rate</h3>
                <p class="stat-value">
                    {% if job.stats_json.total_assets %}
                        {{ ((job.stats_json.total_matches / job.stats_json.total_assets) * 100) | round(1) }}%
                    {% else %}0%{% endif %}
                </p>
            </div>
            <div class="stat-card">
                <h3>GPS Coverage</h3>
                <p class="stat-value">{{ job.stats_json.gps_coverage | default(0) | round(1) }}%</p>
            </div>
        </div>

        <section>
            <h3>Breakdown by Lane</h3>
            <table>
                <thead>
                    <tr><th>Lane</th><th>Assets</th><th>Matched</th><th>GPS</th></tr>
                </thead>
                <tbody>
                    {% for lane, stats in job.stats_json.by_lane.items() %}
                    <tr>
                        <td>{{ lane | title }}</td>
                        <td>{{ stats.assets }}</td>
                        <td>{{ stats.matched }}</td>
                        <td>{{ stats.gps }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </section>

        <section>
            <h3>Processing Time</h3>
            <table>
                <thead>
                    <tr><th>Phase</th><th>Duration</th></tr>
                </thead>
                <tbody>
                    {% for phase, duration in job.stats_json.phase_durations.items() %}
                    <tr>
                        <td>{{ phase | title }}</td>
                        <td>{{ duration | round(1) }}s</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </section>

        <section>
            <a href="/download/{{ job_id }}" role="button">Download Results</a>
        </section>

        {% else %}
        <p>No statistics available for this job.</p>
        {% endif %}
    </div>

    <!-- Matches Tab -->
    <div id="matches" class="tab-content">
        <h2>Matches</h2>
        <div id="matches-table"
             hx-get="/api/matches?job_id={{ job_id }}&page=1"
             hx-trigger="intersect once"
             hx-target="this"
             hx-swap="innerHTML">
            <p>Loading matches...</p>
        </div>
    </div>

    <!-- Assets Tab -->
    <div id="assets" class="tab-content">
        <h2>Exported Assets</h2>
        <div id="assets-list"
             hx-get="/api/assets?job_id={{ job_id }}&page=1"
             hx-trigger="intersect once"
             hx-target="this"
             hx-swap="innerHTML">
            <p>Loading assets...</p>
        </div>
    </div>
</article>

<style>
.tab-navigation {
    display: flex;
    gap: 0;
    margin-bottom: 2rem;
    border-bottom: 2px solid #ddd;
}

.tab-button {
    padding: 0.75rem 1.5rem;
    background: none;
    border: none;
    border-bottom: 3px solid transparent;
    cursor: pointer;
    font-size: 1rem;
    font-weight: 500;
    color: #666;
    margin-bottom: -2px;
}

.tab-button.active { color: #0066cc; border-bottom-color: #0066cc; }

.tab-content { display: none; }
.tab-content.active { display: block; }

.stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 1rem;
    margin: 2rem 0;
}

.stat-card {
    border: 1px solid #ddd;
    border-radius: 8px;
    padding: 1.5rem;
    text-align: center;
}

.stat-value {
    font-size: 2rem;
    font-weight: bold;
    color: #0066cc;
    margin: 0.5rem 0 0;
}

.pagination { display: flex; justify-content: space-between; align-items: center; margin: 2rem 0; }
</style>

<script>
function openTab(evt, tabName) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-button').forEach(el => el.classList.remove('active'));
    document.getElementById(tabName).classList.add('active');
    evt.target.classList.add('active');
}
</script>
{% endblock %}
```

---

### 7. `snatched/templates/download.html` — Download Manager

**Purpose:** File tree and download options for a completed job.

**Context variables:**
- `job_id` — Job ID (integer)

**htmx attributes:**
- `hx-get="/api/download/tree?job_id={job_id}"` — Load file tree on page load

```html
{% extends "base.html" %}

{% block content %}
<article>
    <h1>Download Results &mdash; Job #{{ job_id }}</h1>

    <section>
        <h2>Download All</h2>
        <div class="download-options">
            <a href="/api/download/all?job_id={{ job_id }}" role="button">
                Download All as ZIP
            </a>
            <p>Downloads all processed files as a single ZIP archive.</p>
        </div>
    </section>

    <hr>

    <section>
        <h2>Individual Downloads</h2>
        <div id="file-tree"
             hx-get="/api/download/tree?job_id={{ job_id }}"
             hx-trigger="load"
             hx-target="this"
             hx-swap="innerHTML">
            <p>Loading file tree...</p>
        </div>
    </section>

    <section>
        <ul>
            <li><a href="/results/{{ job_id }}">View Results Summary</a></li>
            <li><a href="/dashboard">Back to Dashboard</a></li>
        </ul>
    </section>
</article>

<style>
.download-options {
    border: 1px solid #ddd;
    border-radius: 8px;
    padding: 1.5rem;
    margin: 1.5rem 0;
}

.file-tree {
    background-color: #f5f5f5;
    padding: 1rem;
    border-radius: 4px;
    font-family: monospace;
    margin: 1rem 0;
}

.file-item { padding: 0.5rem 0; margin-left: 1rem; }
.file-item.folder { font-weight: bold; margin-left: 0; }
</style>
{% endblock %}
```

---

### 8. `snatched/templates/error.html` — Error Display

**Purpose:** Error page. Shows stack trace in dev mode.

**Context variables:**
- `error` — Object/dict with `title` (str), `message` (str), `traceback` (str or None)

**htmx attributes:** None

```html
{% extends "base.html" %}

{% block content %}
<article>
    <h1>Error</h1>

    <div class="error-container">
        <h2>{{ error.title or "Something Went Wrong" }}</h2>
        <p>{{ error.message }}</p>

        {% if error.traceback %}
        <details>
            <summary>Stack Trace (dev mode)</summary>
            <pre>{{ error.traceback }}</pre>
        </details>
        {% endif %}

        <div class="error-actions">
            <a href="/" role="button" class="secondary">Home</a>
            <a href="/dashboard" role="button" class="secondary">Dashboard</a>
        </div>
    </div>
</article>

<style>
.error-container {
    border: 2px solid #cc0000;
    border-radius: 8px;
    padding: 2rem;
    background-color: #fff5f5;
}

h1, h2 { color: #cc0000; }

.error-actions { margin-top: 2rem; display: flex; gap: 1rem; }

pre {
    background-color: #1e1e1e;
    color: #d4d4d4;
    padding: 1rem;
    border-radius: 4px;
    overflow-x: auto;
    font-size: 0.85rem;
}
</style>
{% endblock %}
```

---

## Static Files

### `snatched/static/style.css`

**Purpose:** Custom styles. Pico CSS handles ~90% of styling; this file adds layout and component overrides.

```css
/* Snatched v3 — Custom Styles */
/* Pico CSS classless framework loaded separately in base.html */

:root {
    --primary-color: #0066cc;
    --success-color: #00aa00;
    --warning-color: #ffaa00;
    --danger-color:  #cc0000;
    --light-bg:      #f5f5f5;
}

/* Navigation */
.navbar {
    background-color: #fafafa;
    border-bottom: 1px solid #ddd;
    padding: 1rem 0;
    margin-bottom: 2rem;
}

.nav-container {
    max-width: 900px;
    margin: 0 auto;
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0 1rem;
}

.navbar h2 { margin: 0; }

.nav-menu {
    list-style: none;
    display: flex;
    gap: 2rem;
    margin: 0;
    padding: 0;
}

.nav-menu a { text-decoration: none; color: #333; }
.nav-menu a:hover { color: var(--primary-color); }

.user-info {
    padding: 0.5rem 1rem;
    background-color: var(--primary-color);
    color: white;
    border-radius: 4px;
    font-size: 0.9rem;
}

/* Alert boxes */
.alert {
    padding: 1rem;
    border-radius: 4px;
    margin-bottom: 1rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.alert-info    { background-color: #e3f2fd; border-left: 4px solid #2196f3; color: #1565c0; }
.alert-warning { background-color: #fff3e0; border-left: 4px solid #ff9800; color: #e65100; }
.alert-error   { background-color: #ffebee; border-left: 4px solid #f44336; color: #c62828; }

/* File input: hidden, label acts as button */
input[type="file"] { display: none; }

/* Progress bars */
.progress-bar {
    width: 100%;
    height: 24px;
    background-color: #e0e0e0;
    border-radius: 4px;
    overflow: hidden;
}

.progress-fill {
    height: 100%;
    background-color: var(--primary-color);
    transition: width 0.5s ease;
}

/* Footer */
footer {
    background-color: #fafafa;
    border-top: 1px solid #ddd;
    padding: 2rem;
    margin-top: 4rem;
    text-align: center;
    color: #666;
}

/* Responsive */
@media (max-width: 768px) {
    .nav-menu { flex-direction: column; gap: 1rem; }
    .stats-grid { grid-template-columns: 1fr 1fr; }
    .phases { grid-template-columns: 1fr; }
    .job-meta { grid-template-columns: 1fr; }
}
```

### `snatched/static/htmx.min.js`

**Source:** Download from `https://unpkg.com/htmx.org@2.0.0/dist/htmx.min.js`

**Size:** ~14 KB minified

**Do NOT edit this file.** Vendored as-is. Check in to version control.

To download:
```bash
curl -Lo /home/dave/docker/compose/snatched/snatched/static/htmx.min.js \
  https://unpkg.com/htmx.org@2.0.0/dist/htmx.min.js
```

---

## htmx Patterns Reference

### Pattern 1: File Upload with Indicator

```html
<form hx-post="/api/upload"
      hx-encoding="multipart/form-data"
      hx-target="#status"
      hx-indicator="#spinner">
  <input type="file" name="file">
  <button type="submit">Upload</button>
  <div id="spinner" class="htmx-indicator">Uploading...</div>
</form>
<div id="status"></div>
```

**How it works:** Form submission intercepted by htmx; file sent as multipart; `#spinner` shown while in-flight (via `.htmx-indicator` class + htmx CSS); response replaces `#status`.

### Pattern 2: SSE Progress Streaming

```html
<div hx-ext="sse" sse-connect="/api/jobs/42/stream">
  <div sse-swap="phase_start" hx-swap="beforeend" id="log">
    Waiting...
  </div>
</div>
```

Server sends:
```
event: phase_start
data: Ingesting export data...

event: complete
data: done
```

### Pattern 3: Polling for Updates

```html
<div hx-get="/api/jobs?status=running"
     hx-trigger="load, every 2s"
     hx-target="this"
     hx-swap="innerHTML">
  Loading jobs...
</div>
```

**Triggers:** `load` — fetch immediately; `every 2s` — repeat every 2 seconds.

### Pattern 4: Lazy Tab Loading

```html
<div id="matches"
     hx-get="/api/matches?job_id=42&page=1"
     hx-trigger="intersect once"
     hx-target="this"
     hx-swap="innerHTML">
  Loading...
</div>
```

**`intersect once`** — loads when the element becomes visible (lazy), only once.

### Pattern 5: Paginated API Results

```html
<div id="results">
  <a hx-get="/api/assets?job_id=42&page=2"
     hx-target="#results"
     hx-swap="innerHTML">Next Page</a>
</div>
```

---

## Acceptance Criteria

- [ ] All 8 templates render without Jinja2 errors
- [ ] `base.html` `{% block content %}` extended correctly by all child templates
- [ ] `style.css` loads via `/static/style.css` (200 response)
- [ ] `htmx.min.js` loads via `/static/htmx.min.js` (200 response)
- [ ] `htmx.version` in browser console shows `2.0.x`
- [ ] File upload form: drag-drop zone accepts dropped ZIP files
- [ ] File upload form: `hx-post` submission works with htmx (no page reload)
- [ ] Dashboard polling: active jobs update every 2 seconds
- [ ] SSE streaming: `job_progress.html` receives and displays events
- [ ] Phase status indicators update on `phase_start` events
- [ ] "View Results" button appears on `complete` SSE event
- [ ] Tab switching works (`openTab()` function, all tabs correct)
- [ ] Matches tab loads data when tab is first made visible
- [ ] Summary stats render correctly from `job.stats_json`
- [ ] Download page loads file tree via htmx on page load
- [ ] Error page displays title, message, and optional stack trace
- [ ] Responsive layout: viewport meta tag present; CSS breakpoints applied
- [ ] No browser console JS errors on any template
- [ ] Flash messages display and can be dismissed
- [ ] Landing page has no emojis (removed — use semantic HTML instead)
