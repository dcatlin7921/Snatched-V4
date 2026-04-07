UI_Architecture__Request_Flow___Data_Wiring_20260226_140428
Description: Maps the complete UI request flow from authentication through job processing to data visualization, showing how FastAPI routes wire together HTML templates, PostgreSQL user data, per-job SQLite databases, and htmx dynamic updates. Key entry points: upload flow [1b], job canvas rendering [3a], dashboard polling [4d], and asset tag editing [6c].

Trace 1 — Upload Flow: File Upload → Job Creation → Processing Start
Upload Flow: File → Job → Processing
├── HTTP GET /upload <-- 1a
│   ├── Load user preferences from PostgreSQL <-- pages.py:269
│   ├── Load tier limits (max_upload_bytes) <-- pages.py:288
│   └── Render upload.html template <-- 1b
│       └── Client-side JS handles file selection
│
├── HTTP POST /api/upload/session
│   ├── Generate UUID session_id <-- 1c
│   ├── Insert upload_sessions row (PostgreSQL) <-- uploads.py:95
│   └── Return session_id to client <-- uploads.py:108
│
├── HTTP POST /api/upload/chunk (multiple)
│   └── Append chunks to temp file <-- uploads.py:150
│
├── HTTP POST /api/upload/finalize
│   ├── Verify all chunks received <-- uploads.py:240
│   ├── Move temp file to final location <-- uploads.py:253
│   ├── create_processing_job() <-- 1d
│   │   └── INSERT INTO processing_jobs <-- jobs.py:90
│   └── asyncio.create_task() <-- 1e
│       └── run_job() background task <-- 1f
│           ├── Update status to 'running' <-- jobs.py:220
│           ├── Execute ingest phase <-- jobs.py:245
│           ├── Execute match phase <-- jobs.py:260
│           ├── Execute enrich phase <-- jobs.py:275
│           └── Execute export phase <-- jobs.py:290

Location 1a — Upload Page Route
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/pages.py:248
Description: Entry point: renders upload.html with user preferences and tier limits

Location 1b — Template Response
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/pages.py:298
Description: Passes tier_info, prefs, max_upload_bytes to upload.html for client-side validation

Location 1c — Upload Session Creation
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/uploads.py:89
Description: POST /api/upload/session creates unique session ID for chunked upload tracking

Location 1d — Job Creation
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/uploads.py:263
Description: Finalize endpoint creates processing_jobs row in PostgreSQL with phases_requested

Location 1e — Async Job Start
Path: /home/dave/CascadeProjects/snatched-v3/snatched/jobs.py:356
Description: Fire-and-forget task launches run_job for background processing

Location 1f — Job Execution
Path: /home/dave/CascadeProjects/snatched-v3/snatched/jobs.py:357
Description: Main orchestrator executes ingest/match/enrich/export phases sequentially

Trace 2 — Job Processing Pipeline: Phase Execution & Status Updates
Job Processing Pipeline
└── run_job() orchestrator <-- 2a
    ├── Status: pending → running <-- 2b
    ├── Progress callback factory <-- 2c
    ├── Phase 1: Ingest
    │   └── ingest_worker.run_ingest() <-- 2d
    │       └── Extract ZIP → SQLite assets table
    ├── Phase 2: Match
    │   └── match_worker.run_match() <-- 2e
    │       └── Correlate assets → SQLite matches
    ├── Phase 3: Enrich
    │   └── enrich_worker.run_enrich() <-- 2f
    │       └── Add GPS/timestamps via EXIF/XMP
    ├── Phase 4: Export
    │   └── export_worker.run_export() <-- 2g
    │       └── Generate output files + ZIP
    └── Status: running → completed <-- 2h
        └── Trigger UI refresh

Location 2a — Job Orchestrator
Path: /home/dave/CascadeProjects/snatched-v3/snatched/jobs.py:194
Description: Main async function that coordinates all processing phases

Location 2b — Status Update to Running
Path: /home/dave/CascadeProjects/snatched-v3/snatched/jobs.py:220
Description: Updates PostgreSQL processing_jobs.status and current_phase for UI polling

Location 2c — Progress Callback Factory
Path: /home/dave/CascadeProjects/snatched-v3/snatched/jobs.py:235
Description: Creates callback function for phase workers to report progress_pct updates

Location 2d — Ingest Phase
Path: /home/dave/CascadeProjects/snatched-v3/snatched/jobs.py:245
Description: Extracts ZIP, scans files, populates per-job SQLite assets table

Location 2e — Match Phase
Path: /home/dave/CascadeProjects/snatched-v3/snatched/jobs.py:260
Description: Correlates assets with metadata using strategies, writes matches to SQLite

Location 2f — Enrich Phase
Path: /home/dave/CascadeProjects/snatched-v3/snatched/jobs.py:275
Description: Adds GPS, timestamps, creator info to matched assets via EXIF/XMP

Location 2g — Export Phase
Path: /home/dave/CascadeProjects/snatched-v3/snatched/jobs.py:290
Description: Generates output files, creates ZIP archives, updates exports table

Location 2h — Completion Status
Path: /home/dave/CascadeProjects/snatched-v3/snatched/jobs.py:310
Description: Final status update triggers UI refresh and enables download buttons

Trace 3 — Living Canvas: Dynamic Job Page Rendering
Living Canvas Request Flow
├── HTTP GET /job/{job_id}
│   └── @router.get("/job/{job_id}") <-- 3a
│       └── job_canvas(request, job_id, username) <-- pages.py:426
│           ├── Verify ownership & load job data
│           │   └── conn.fetchrow(SELECT pj.*) <-- 3b
│           ├── Compute UI phase index
│           │   ├── phase_map = {...} <-- 3c
│           │   └── if status == 'running' <-- 3d
│           ├── Deserialize stats from JSONB
│           │   └── raw_stats = job["stats_json"] <-- 3e
│           ├── Load tier info helper
│           │   └── await _load_tier_info(pool) <-- pages.py:483
│           └── Render template response
│               └── templates.TemplateResponse() <-- 3f
│                   └── job.html (Jinja2)
│                       ├── {% block content %}
│                       ├── Phase progress indicators
│                       ├── Stats display (conditional)
│                       └── htmx polling (if running)

Location 3a — Job Canvas Route
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/pages.py:425
Description: Single evolving page that replaces separate progress/configure/results pages

Location 3b — Job Data Query
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/pages.py:441
Description: Loads job row from PostgreSQL with status, current_phase, stats_json

Location 3c — Phase Index Mapping
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/pages.py:458
Description: Maps job status to UI phase index (0-4) for progress visualization

Location 3d — Active Phase Detection
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/pages.py:466
Description: Refines phase_idx using current_phase column for real-time progress

Location 3e — Stats Deserialization
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/pages.py:477
Description: Extracts match counts, GPS coverage, file counts from JSONB column

Location 3f — Template Render
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/pages.py:485
Description: Passes job, stats, phase_idx, tier_info to job.html for conditional display

Trace 4 — Dashboard: Real-time Job Monitoring with htmx Polling
Dashboard Request Flow
├── GET /dashboard <-- 4a
│   ├── PostgreSQL queries
│   │   ├── Load user tier (free/pro) <-- 4b
│   │   └── Count active jobs (running+pending) <-- 4c
│   ├── Calculate queue position <-- pages.py:379
│   └── Render dashboard.html with tier_info <-- pages.py:404
│       └── Contains htmx polling directive
│           └── hx-get="/api/jobs/html" every 2s
│
└── htmx Auto-refresh Loop
    └── GET /api/jobs/html <-- 4d
        ├── Query jobs with retention data <-- 4e
        ├── Compute retention_days_remaining <-- api.py:163
        └── Render _job_cards.html fragment <-- 4f
            └── Swapped into #job-list container

Location 4a — Dashboard Route
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/pages.py:307
Description: Main job status page with tier info and slot indicators

Location 4b — Tier Loading
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/pages.py:335
Description: Fetches user tier (free/pro) for concurrent_jobs limit enforcement

Location 4c — Active Jobs Count
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/pages.py:342
Description: Counts running + pending jobs for slot occupancy display

Location 4d — htmx Job Cards Endpoint
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/api.py:116
Description: Returns HTML fragment for dashboard polling (hx-get every 2s)

Location 4e — Job List Query
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/api.py:154
Description: Fetches jobs with retention_expires_at for countdown timers

Location 4f — Job Cards Render
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/api.py:168
Description: Partial template swapped into dashboard via htmx for live updates

Trace 5 — Memory Browser: Lazy-loaded Gallery with htmx
Memory Browser Gallery Flow
├── GET /browse/{job_id} <-- 5a
│   ├── Verify job ownership (PostgreSQL) <-- pages.py:2031
│   ├── Resolve SQLite path <-- 5b
│   │   └── /data/{username}/jobs/{job_id}/proc.db
│   ├── Load initial stats (run_in_executor) <-- pages.py:2084
│   │   ├── COUNT(*) FROM assets <-- 5c
│   │   ├── COUNT(DISTINCT asset_id) FROM matches <-- pages.py:2063
│   │   └── DISTINCT asset_type FROM assets <-- pages.py:2067
│   └── Render memory_browser.html <-- 5d
│       └── Shell page with htmx trigger
│           └── hx-get="/api/assets/html?job_id=X"
│
└── htmx Lazy Load Request
    └── GET /api/assets/html <-- 5e
        ├── Verify job ownership <-- api.py:827
        ├── Query paginated assets (run_in_executor) <-- api.py:854
        │   └── SELECT * FROM assets
        │       LIMIT 50 OFFSET N <-- 5f
        └── Render _asset_rows.html <-- 5g
            └── HTML fragment appended to gallery

Location 5a — Memory Browser Route
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/pages.py:2014
Description: Gallery page for viewing processed memories with filters

Location 5b — SQLite Path Resolution
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/pages.py:2046
Description: Constructs path to per-job proc.db: /data/{username}/jobs/{job_id}/proc.db

Location 5c — Asset Count Query
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/pages.py:2059
Description: Reads total asset count from SQLite for pagination

Location 5d — Initial Page Render
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/pages.py:2086
Description: Renders shell with stats; actual gallery cards loaded via htmx

Location 5e — Asset Cards Endpoint
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/api.py:813
Description: htmx target for lazy-loading paginated asset rows

Location 5f — Paginated Asset Query
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/api.py:850
Description: Fetches 50 assets per page from SQLite for infinite scroll

Location 5g — Asset Rows Fragment
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/api.py:855
Description: Partial template with asset cards appended to gallery via htmx

Trace 6 — Asset Tag Editing: Metadata Modification with Audit Trail
Asset Tag Editing Flow
├── GET /assets/{job_id}/{asset_id} <-- 6a
│   ├── Verify job ownership (PostgreSQL) <-- pages.py:571
│   ├── Load asset from SQLite proc.db <-- pages.py:600
│   ├── Resolve output file path <-- pages.py:606
│   ├── tags_module.read_tags() <-- 6b
│   │   └── exiftool subprocess call
│   ├── tags_module.group_tags() <-- pages.py:619
│   └── Render asset_detail.html with tags <-- pages.py:655
│
└── PUT /api/assets/{asset_id}/tags <-- 6c
    ├── Verify job ownership + get user_id <-- api.py:941
    ├── Load asset from SQLite proc.db <-- api.py:969
    ├── Resolve output file path <-- api.py:973
    ├── read_tags_before_edit() <-- 6d
    │   └── exiftool read for audit
    ├── tags_module.write_tags() <-- 6e
    │   └── exiftool -overwrite_original
    └── Audit logging loop <-- api.py:995
        └── INSERT INTO tag_edits <-- 6f
            └── (user_id, job_id, asset_id,
                 field_name, old_value, new_value)

Location 6a — Asset Detail Route
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/pages.py:553
Description: Individual asset tag viewer & editor page

Location 6b — Tag Reading
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/pages.py:618
Description: Calls exiftool to extract all EXIF/XMP tags from output file

Location 6c — Tag Update Endpoint
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/api.py:919
Description: Accepts edits dict like {'EXIF:DateTimeOriginal': '2024:07:04 14:30:00'}

Location 6d — Pre-edit Snapshot
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/api.py:985
Description: Captures old values for audit trail before modification

Location 6e — Tag Writing
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/api.py:988
Description: Calls exiftool to write new tag values to file

Location 6f — Audit Log Insert
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/api.py:999
Description: Records each tag change to PostgreSQL tag_edits table with old/new values

Trace 7 — Authentication Flow: Login → JWT → Dashboard Redirect
Authentication Flow (Trace 7)
├── Browser Request: GET /login
│   └── pages.py: login_page() <-- 7a
│       └── Render login.html form <-- pages.py:111
│
├── User Submits Credentials: POST /login
│   └── pages.py: login_submit() <-- 7b
│       ├── Extract username/password <-- pages.py:121
│       ├── PostgreSQL Query <-- 7c
│       │   └── SELECT password_hash FROM users <-- pages.py:130
│       ├── auth.py: verify_password() <-- 7d
│       ├── auth.py: create_jwt() <-- 7e
│       ├── Set Cookie <-- 7f
│       └── Redirect Response <-- 7g
│
└── Subsequent Requests
    └── Middleware reads auth_token <-- app.py:92
        └── auth.py: get_current_user()
            └── JWT verified → username extracted

Location 7a — Login Page Route
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/pages.py:102
Description: Renders login form; redirects to dashboard if already authenticated

Location 7b — Login Submit Handler
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/pages.py:116
Description: Processes form submission with username and password

Location 7c — User Lookup
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/pages.py:129
Description: Queries PostgreSQL users table for username and password_hash

Location 7d — Password Verification
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/pages.py:136
Description: Compares submitted password against bcrypt hash from database

Location 7e — JWT Generation
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/pages.py:143
Description: Creates signed JWT token with username claim and 24h expiry

Location 7f — Secure Cookie
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/pages.py:145
Description: Sets httponly cookie with JWT for subsequent authenticated requests

Location 7g — Dashboard Redirect
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/pages.py:144
Description: Redirects authenticated user to dashboard with cookie set

Trace 8 — GPS Correction: Interactive Map with Draggable Pins
GPS Correction Page Request Flow
├── GET /gps/{job_id} route handler <-- 8a
│   ├── Verify job ownership (PostgreSQL) <-- pages.py:1108
│   ├── Construct per-job SQLite path <-- pages.py:1124
│   │   └── /data/{username}/jobs/{job_id}/proc.db
│   ├── Load data from SQLite (executor) <-- pages.py:1185
│   │   ├── Query assets with GPS coords <-- 8b
│   │   ├── Query locations breadcrumb trail <-- 8c
│   │   └── Query Snap Map places <-- pages.py:1167
│   ├── Load saved locations (PostgreSQL) <-- 8d
│   ├── Serialize all data to JSON <-- 8e
│   │   ├── assets_json <-- pages.py:1208
│   │   ├── locations_json <-- pages.py:1209
│   │   ├── places_json <-- pages.py:1210
│   │   └── saved_locations_json <-- pages.py:1211
│   └── Render gps_correction.html template <-- 8f
│       └── Inject JSON into Leaflet.js map
└── Client-side map interactions
    ├── Leaflet.js renders markers/polylines
    ├── User drags asset pins
    └── PUT /api/assets/{id}/gps updates coords

Location 8a — GPS Correction Route
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/pages.py:1084
Description: Interactive map tool for correcting asset GPS coordinates

Location 8b — Assets with GPS Query
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/pages.py:1136
Description: Loads assets joined with matches table for matched_lat/matched_lon

Location 8c — GPS Breadcrumb Trail
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/pages.py:1154
Description: Fetches locations table for polyline overlay on map

Location 8d — Saved Locations Query
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/pages.py:1189
Description: Loads user's saved_locations from PostgreSQL for blue circle markers

Location 8e — JSON Serialization
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/pages.py:1208
Description: Converts Python dicts to JSON for JavaScript map initialization

Location 8f — Map Template Render
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/pages.py:1213
Description: Injects assets_json, locations_json into template for Leaflet.js