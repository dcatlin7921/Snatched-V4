# Phase 1 Implementation Guide — Consensus Stories 1-8

**Quick reference for developers.**
**All stories use existing features; just reorganize visibility/layout.**

---

## Story 1: Simplify Dashboard

### Current State
- Sticky header has 13 buttons: Reprocess, GPS Correction, Timestamps, Redact, Match Config, Browse, Chats, Timeline, Map, Duplicates, Albums, Reports, Download

### Changes
1. **Sticky header buttons**: Keep only [View Results] and [Download]
2. **Add hamburger menu** (⋯) in top-right of sticky header
3. **Menu items**: Group buttons under sections:
   - **Corrections**: Reprocess, GPS Correction, Timestamps, Redact, Match Config
   - **Diagnostics**: Browse, Chats, Timeline, Map
   - **Export**: Duplicates, Albums, Reports, Download
4. **Hide hamburger** if `job.status != 'completed'`
5. **Show hamburger** only if `user.export_count >= 1`

### Code Changes
```python
# routes/pages.py
@app.get("/results/{job_id}")
def get_results(job_id: int, user: User):
    job = get_job(job_id, user)
    show_advanced_menu = user.export_count >= 1  # Show hamburger after first export
    return templates.TemplateResponse("results.html", {
        "job": job,
        "show_advanced_menu": show_advanced_menu,
    })
```

```html
<!-- templates/results.html -->
<div class="sticky-header">
  <button onclick="location.href='/results/{{ job.id }}'">View Results</button>
  <button onclick="location.href='/download/{{ job.id }}'">Download</button>

  {% if show_advanced_menu %}
  <div class="menu-dropdown">
    <button onclick="toggleMenu()" title="Advanced options">⋯</button>
    <div id="advanced-menu" class="dropdown-content">
      <h4>Corrections</h4>
      <button onclick="reprocess()">Reprocess</button>
      <button onclick="toggleTab('corrections')">GPS Correction</button>
      <!-- ... etc -->
    </div>
  </div>
  {% endif %}
</div>
```

---

## Story 2: Hide Advanced Upload Options

### Current State
- Upload form shows all checkboxes and sliders

### Changes
1. **Hide by default**: Phase checkboxes, GPS window slider, dry-run toggle, lanes
2. **Add toggle**: [⚙️ Advanced Settings] collapse control below form
3. **Default behavior**: All phases enabled (no UI choices needed)
4. **Persistence**: Store toggle state in localStorage

### Code Changes
```html
<!-- templates/upload.html -->
<form id="upload-form">
  <input type="file" accept=".zip" required />
  <button type="submit">Upload & Process</button>

  <details id="advanced-settings">
    <summary>⚙️ Advanced Settings</summary>

    <fieldset>
      <legend>Processing Phases</legend>
      <label><input type="checkbox" name="phase" value="ingest" checked /> Ingest</label>
      <label><input type="checkbox" name="phase" value="match" checked /> Match</label>
      <label><input type="checkbox" name="phase" value="enrich" checked /> Enrich</label>
      <label><input type="checkbox" name="phase" value="export" checked /> Export</label>
    </fieldset>

    <fieldset>
      <legend>GPS Window</legend>
      <input type="range" name="gps_window_seconds" min="30" max="1800" value="300" />
      <output id="gps-value">300s</output>
    </fieldset>
  </details>
</form>

<script>
// Restore toggle state from localStorage
const advancedSettings = document.getElementById('advanced-settings');
const savedOpen = localStorage.getItem('upload_show_advanced');
if (savedOpen === 'true') advancedSettings.open = true;

// Persist state on change
advancedSettings.addEventListener('toggle', () => {
  localStorage.setItem('upload_show_advanced', advancedSettings.open);
});
</script>
```

---

## Story 3: Results Page Walkthrough

### Current State
- Results page shows tabs with no introduction to concepts like "matches" or "confidence"

### Changes
1. **First visit**: Show optional 4-card tour (overlay, non-blocking)
2. **Tour cards**:
   - "What are matches?" → explains file-to-memory matching strategy
   - "Confidence score" → 0–100%, what it means, when to trust
   - "Assets vs. Metadata" → photos/videos vs. dates/locations
   - "Ready to download?" → CTA to Download button
3. **Skippable**: [Next] [Skip] or auto-skip after 5 seconds of no interaction
4. **Repeatable**: [?] help icon in header re-shows tour
5. **Track**: Store in `user_preferences.results_tour_seen`

### Code Changes
```python
# models.py
class UserPreferences(Base):
    __tablename__ = "user_preferences"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    results_tour_seen = Column(Boolean, default=False)  # NEW

# routes/pages.py
@app.get("/results/{job_id}")
def get_results(job_id: int, user: User):
    job = get_job(job_id, user)
    prefs = db.query(UserPreferences).filter_by(user_id=user.id).first()
    show_tour = not prefs.results_tour_seen  # First visit only
    return templates.TemplateResponse("results.html", {
        "job": job,
        "show_tour": show_tour,
    })

# routes/api.py
@app.post("/api/preferences/tour-seen")
def mark_tour_seen(user: User):
    prefs = db.query(UserPreferences).filter_by(user_id=user.id).first()
    prefs.results_tour_seen = True
    db.commit()
    return {"status": "ok"}
```

```html
<!-- templates/results.html -->
{% if show_tour %}
<div id="tour-overlay" class="tour-modal" onclick="skipTour()">
  <div class="tour-card" onclick="event.stopPropagation()">
    <h2 id="tour-title">What are matches?</h2>
    <p id="tour-text">We match your photos/videos to Snapchat metadata using 6 strategies...</p>
    <div class="tour-actions">
      <button onclick="prevTour()" id="prev-btn" style="display:none">Previous</button>
      <button onclick="nextTour()" id="next-btn">Next</button>
      <button onclick="skipTour()" class="secondary">Skip</button>
    </div>
  </div>
</div>

<script>
const tourCards = [
  { title: "What are matches?", text: "..." },
  { title: "Confidence score", text: "..." },
  { title: "Assets vs. Metadata", text: "..." },
  { title: "Ready to download?", text: "..." },
];
let tourStep = 0;

function nextTour() {
  tourStep++;
  if (tourStep >= tourCards.length) skipTour();
  else updateTourCard();
}

function skipTour() {
  document.getElementById('tour-overlay').style.display = 'none';
  fetch('/api/preferences/tour-seen', { method: 'POST' });
}

// Auto-skip after 5 seconds
setTimeout(skipTour, 5000);
</script>
{% endif %}
```

---

## Story 4: Collapse Settings Into Zones

### Current State
- Single Settings page with all tabs visible (API, Webhooks, Danger Zone, etc.)

### Changes
1. **New users** (< 2 exports): Show only [Account] tab
2. **After 2+ exports**: Reveal [Advanced], [Webhooks], [Automation] tabs
3. **After Pro signup**: Reveal [API Keys], [Team], [Scheduled]
4. **Always available**: [Danger Zone] (collapsed, password-protected)

### Code Changes
```python
# routes/pages.py
@app.get("/settings")
def get_settings(user: User):
    export_count = db.query(ProcessingJob).filter_by(user_id=user.id).count()
    show_advanced = export_count >= 2 or user.tier == "pro"
    show_api = user.tier == "pro" or export_count >= 10

    return templates.TemplateResponse("settings.html", {
        "user": user,
        "show_advanced": show_advanced,
        "show_api": show_api,
        "show_team": user.tier == "pro",
    })
```

```html
<!-- templates/settings.html -->
<div class="tabs">
  <button class="tab-button active" onclick="switchTab('account')">Account</button>
  {% if show_advanced %}
    <button class="tab-button" onclick="switchTab('advanced')">Advanced</button>
    <button class="tab-button" onclick="switchTab('webhooks')">Webhooks & Automation</button>
  {% endif %}
  {% if show_api %}
    <button class="tab-button" onclick="switchTab('api')">API Keys</button>
  {% endif %}
  {% if show_team %}
    <button class="tab-button" onclick="switchTab('team')">Team</button>
  {% endif %}
  <button class="tab-button" onclick="switchTab('danger')">Danger Zone</button>
</div>

<div id="account" class="tab-content active">
  <!-- Profile, storage meter, tier info -->
</div>

{% if show_advanced %}
<div id="advanced" class="tab-content">
  <!-- Advanced processing options -->
</div>
{% endif %}

<div id="danger" class="tab-content">
  <details>
    <summary>⚠️ Danger Zone (requires confirmation)</summary>
    <button onclick="confirmDelete()">Delete Account</button>
  </details>
</div>
```

---

## Story 5: Corrections Tab (Instead of Buttons)

### Current State
- Sticky header has individual buttons: GPS Correction, Timestamps, Redact, Match Config

### Changes
1. **New Results tab**: [Summary | Matches | Assets | Corrections] (only show if user has viewed Matches)
2. **Tab content**: 4 collapsible sections (GPS → Timestamps → Redact → Match Config)
3. **Single submit**: "Reprocess with corrections" button at bottom
4. **Visibility**: Only show if `job.has_viewed_matches == true`

### Code Changes
```python
# models.py
class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    id = Column(Integer, primary_key=True)
    has_viewed_matches = Column(Boolean, default=False)  # NEW

# routes/api.py
@app.post("/api/jobs/{job_id}/view-matches")
def log_matches_view(job_id: int, user: User):
    job = get_job(job_id, user)
    job.has_viewed_matches = True
    db.commit()
    return {"status": "ok"}

# routes/pages.py
@app.get("/results/{job_id}")
def get_results(job_id: int, user: User):
    job = get_job(job_id, user)
    show_corrections_tab = job.has_viewed_matches or job.status == 'completed'
    return templates.TemplateResponse("results.html", {
        "job": job,
        "show_corrections_tab": show_corrections_tab,
    })
```

```html
<!-- templates/results.html -->
<div class="tabs">
  <button class="tab-button" onclick="switchTab('summary')">Summary</button>
  <button class="tab-button" onclick="switchTab('matches'); markMatchesViewed();">Matches</button>
  <button class="tab-button" onclick="switchTab('assets')">Assets</button>
  {% if show_corrections_tab %}
    <button class="tab-button" onclick="switchTab('corrections')">Corrections</button>
  {% endif %}
</div>

{% if show_corrections_tab %}
<div id="corrections" class="tab-content">
  <h3>Refine Your Results</h3>

  <details open>
    <summary>📍 GPS Window</summary>
    <input type="range" name="gps_window" min="30" max="1800" value="{{ job.gps_window }}" />
  </details>

  <details>
    <summary>⏰ Timestamps</summary>
    <input type="checkbox" name="fix_timestamps" />
  </details>

  <details>
    <summary>🎨 Redaction</summary>
    <select name="redact_mode">
      <option value="none">None</option>
      <option value="faces">Blur faces</option>
      <option value="all">Blur all</option>
    </select>
  </details>

  <details>
    <summary>🔍 Match Strategy</summary>
    <fieldset>
      <label><input type="checkbox" name="strategy_exact" checked /> Exact filename match</label>
      <label><input type="checkbox" name="strategy_fuzzy" checked /> Fuzzy matching</label>
    </fieldset>
  </details>

  <button onclick="submitCorrections()">Reprocess with Corrections</button>
</div>
{% endif %}

<script>
function markMatchesViewed() {
  fetch('/api/jobs/{{ job.id }}/view-matches', { method: 'POST' });
}
</script>
```

---

## Story 6: Progressive Navigation

### Current State
- Nav bar shows: Upload, Dashboard, Friends, Presets, Schemas, Export, Settings, Quota

### Changes
1. **New users** (< 2 exports): [Dashboard] [Upload] [Settings] [Help]
2. **After 2+ exports**: Add [Presets] [Teams]
3. **Pro users**: Show all links
4. **Remove nav clutter**: Quota indicator → Settings > Account

### Code Changes
```html
<!-- templates/base.html -->
<nav>
  <a href="/" class="logo">Snatched</a>

  <ul class="nav-links">
    <li><a href="/dashboard">Dashboard</a></li>
    <li><a href="/upload">Upload</a></li>
    <li><a href="/settings">Settings</a></li>
    <li><a href="/help">Help</a></li>

    {% if user.export_count >= 2 %}
      <li><a href="/presets">Presets</a></li>
      <li><a href="/teams">Teams</a></li>
    {% endif %}

    {% if user.tier == 'pro' %}
      <li><a href="/automation">Automation</a></li>
      <li><a href="/api">API</a></li>
    {% endif %}
  </ul>
</nav>
```

---

## Story 7: Direct Download from Dashboard

### Current State
- Job card only shows [View Results]; must click Results then find Download button

### Changes
1. **Add [Download] button** to job card on Dashboard
2. **Click [Download]** → goes to `/download/{job_id}` (file tree view)
3. **Add floating [Download] button** on Results page (sticky, bottom-right)

### Code Changes
```html
<!-- templates/dashboard.html -->
<div class="job-card">
  <h3>Job #{{ job.id }}</h3>
  <p>Status: {{ job.status }}</p>

  {% if job.status == 'completed' %}
    <a href="/results/{{ job.id }}" class="button secondary">View Results</a>
    <a href="/download/{{ job.id }}" class="button primary">Download</a>
  {% else %}
    <a href="/results/{{ job.id }}" class="button primary">View Progress</a>
  {% endif %}
</div>

<!-- templates/results.html -->
{% if job.status == 'completed' %}
<div class="sticky-download">
  <a href="/download/{{ job.id }}" class="button primary">Download Results</a>
</div>
{% endif %}
```

---

## Story 8: Empty States & Progress Feedback

### Current State
- Upload redirects immediately; no confirmation message
- Dashboard shows empty state with confusing "No jobs" message
- Job progress page exists but might not be reached

### Changes
1. **After upload**: Show non-blocking overlay "✓ Upload complete! Processing now..." → auto-redirect in 3s
2. **Dashboard empty state**: "Welcome! Ready to rescue your Snapchats? [Upload Export]"
3. **Progress page**: Ensure "Phase 2 of 4" and elapsed time are visible
4. **Job failed**: Show error in plain English + [Retry], [View Logs], [Contact Support]

### Code Changes
```python
# routes/pages.py
@app.post("/api/jobs/upload")
def upload_job(file: UploadFile, user: User):
    job = create_job(file, user)
    return {
        "status": "success",
        "job_id": job.id,
        "message": "Upload complete! Processing now...",
        "redirect_url": f"/results/{job.id}",  # Progress page
    }
```

```html
<!-- templates/upload.html (after form submission) -->
<div id="upload-success" style="display:none">
  <div class="notification success">
    <h3>✓ Upload Complete!</h3>
    <p>Processing your Snapchat export now...</p>
    <p>Redirecting to progress page in <span id="countdown">3</span> seconds...</p>
    <a href="" id="progress-link">View Progress Now</a>
  </div>
</div>

<script>
// After form submission
if (response.status === 'success') {
  document.getElementById('upload-success').style.display = 'block';
  document.getElementById('progress-link').href = response.redirect_url;

  let count = 3;
  const interval = setInterval(() => {
    count--;
    document.getElementById('countdown').textContent = count;
    if (count === 0) {
      clearInterval(interval);
      location.href = response.redirect_url;
    }
  }, 1000);
}
</script>

<!-- templates/dashboard.html (empty state) -->
{% if not user_jobs %}
<div class="empty-state">
  <h2>Welcome to Snatched!</h2>
  <p>Snapchat deletes exports after 30 days. We find and organize them—with dates, locations, and names restored.</p>
  <p>Your processing typically takes 10–30 minutes.</p>
  <a href="/upload" class="button primary">Upload Your First Export</a>
</div>
{% endif %}

<!-- templates/results.html (progress subtitle) -->
<div class="job-header">
  <h1>Processing job #{{ job.id }}</h1>
  <p class="progress-subtitle">
    Phase {{ job.current_phase_number }} of 4 |
    {{ job.progress_pct }}% complete |
    Started {{ job.started_at | timesince }} ago
  </p>
  <progress value="{{ job.progress_pct }}" max="100"></progress>
</div>
```

---

## Testing Checklist

- [ ] **Story 1**: Hamburger menu hides/shows based on `export_count`; all 13 buttons still accessible
- [ ] **Story 2**: Advanced Settings toggle persists in localStorage; all phases default to enabled
- [ ] **Story 3**: Tour shows on first Results visit; can be skipped; doesn't show again; repeatable via [?]
- [ ] **Story 4**: Settings tabs hide/show based on `export_count` and tier; Danger Zone requires password
- [ ] **Story 5**: Corrections tab only appears after viewing Matches; all 4 sections collapsible; single submit button
- [ ] **Story 6**: Nav links show/hide based on user state; no "Quota" in nav; visible in Settings > Account
- [ ] **Story 7**: [Download] button on Dashboard card; [Download] sticky button on Results; both go to `/download/{id}`
- [ ] **Story 8**: Upload success message shows, auto-redirect works; Dashboard empty state is friendly; Progress page shows phase + elapsed time

---

## Deployment Order

1. **Deploy Stories 2, 4, 6** first (no database changes, pure frontend)
2. **Deploy Story 8** (frontend + minimal API)
3. **Deploy Story 3** (requires new DB field; backward-compatible default)
4. **Deploy Story 5** (requires new DB field; tab only shows if true)
5. **Deploy Stories 1, 7** last (affect job card + sticky header)

**Total deployment risk**: Low (all changes are additive, feature-flagged, or conditional on user state)

---
