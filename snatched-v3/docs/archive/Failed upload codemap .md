Snatched V3: Complete User Upload Experience for Rescue Memories & Failed Re-upload System
Codemap ID: Snatched_V3__Complete_User_Upload_Experience_for_Rescue_Memories___Failed_Re-upload_System_20260226_191823
Description: Maps the end-to-end flow from Quick Rescue upload initiation through chunked file transfer, SHA-256 verification, resume/re-upload on failure, and automatic job processing. The re-upload system allows users to recover from browser crashes, network failures, or hash mismatches by resuming from their last checkpoint. Key entry points: Quick Rescue button [1a], resume detection [3a], verification failure [4b], and auto-export trigger [5f].

Trace 1 — Quick Rescue Upload Initiation
Quick Rescue Upload Initiation Flow
│
├── User Interface (upload.html)
│   ├── "Rescue My Memories" button click <-- 1a
│   ├── selectProduct('quick_rescue') handler <-- upload.html:399
│   │   └── Set quick_rescue radio checked <-- 1b
│   └── Upload button click handler <-- upload.html:1280
│       ├── computeHashes() on files <-- 1c
│       └── Build file manifest <-- upload.html:1299
│           └── Attach processing_mode <-- 1d
│
├── HTTP POST /api/upload/init <-- uploads.py:112
│   └── init_upload() in uploads.py <-- uploads.py:113
│       ├── Extract processing_mode <-- 1e
│       ├── Validate files & quota <-- uploads.py:178
│       └── INSERT INTO upload_sessions <-- 1f
│           └── options_json contains <-- uploads.py:267
│               processing_mode='quick_rescue'
│
└── Response: session_id + chunk_size <-- uploads.py:346
    └── Client stores in localStorage <-- upload.html:896

Location 1a — Quick Rescue Button
Path: /home/dave/CascadeProjects/snatched-v3/snatched/templates/upload.html:140
Description: User clicks to select rescue memories mode

Location 1b — Mode Selection
Path: /home/dave/CascadeProjects/snatched-v3/snatched/templates/upload.html:419
Description: Sets quick_rescue radio input as checked, hides full export options

Location 1c — SHA-256 Hash Computation
Path: /home/dave/CascadeProjects/snatched-v3/snatched/templates/upload.html:1296
Description: Client computes file hashes for integrity verification

Location 1d — Mode Attached to Manifest
Path: /home/dave/CascadeProjects/snatched-v3/snatched/templates/upload.html:1305
Description: quick_rescue mode included in upload session initialization

Location 1e — Server Receives Mode
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/uploads.py:160
Description: Upload init endpoint extracts processing_mode from request

Location 1f — Session Created
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/uploads.py:287
Description: upload_sessions record created with quick_rescue in options_json

Trace 2 — Chunked File Upload & Verification
Chunked File Upload & Verification Flow
├── Client: ChunkedUploader.uploadFile() <-- upload.html:936
│   └── Sends chunk via PUT request <-- upload.html:954
│       └── /api/upload/chunk/{session}/{index} <-- uploads.py:366
│           ├── receive_chunk() handler <-- uploads.py:367
│           │   ├── Validate offset matches <-- uploads.py:450
│           │   ├── Stream to .part file <-- 2a
│           │   └── Update progress in DB <-- 2b
│           └── Client: verifyFile() called <-- upload.html:970
│               └── POST /api/upload/verify <-- uploads.py:553
│                   ├── verify_file() handler <-- uploads.py:554
│                   │   ├── Compute SHA-256 in thread <-- 2c
│                   │   ├── Compare hashes <-- 2d
│                   │   └── Advisory lock check <-- uploads.py:725
│                   │       ├── All files complete? <-- 2e
│                   │       ├── Create job record <-- 2f
│                   │       └── Launch background task <-- 2g
│                   └── Return verification result <-- uploads.py:898

Location 2a — Chunk Write to Disk
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/uploads.py:484
Description: Streams incoming chunk to file_N.part at specified offset

Location 2b — Progress Tracked
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/uploads.py:520
Description: Database updated with bytes received for resume capability

Location 2c — Server Hash Computation
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/uploads.py:663
Description: SHA-256 computed on assembled .part file in thread pool

Location 2d — Hash Verification
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/uploads.py:671
Description: Compares server hash with client-provided expected hash

Location 2e — All Files Complete Check
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/uploads.py:742
Description: Advisory lock prevents race condition when last file verifies

Location 2f — Job Creation
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/uploads.py:836
Description: processing_jobs record created with phases=['ingest'] for initial scan

Location 2g — Job Launched
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/uploads.py:872
Description: Background task started to process uploaded files

Trace 3 — Upload Resume After Browser Crash/Network Failure
Upload Resume System (Trace 3)
├── Page Load
│   └── window.addEventListener('load') <-- 3a
│       └── checkExistingSession() <-- upload.html:1492
│           ├── localStorage.getItem() <-- upload.html:1494
│           └── fetch('/api/upload/status') <-- 3b
│               └── GET /api/upload/status <-- uploads.py:905
│                   └── SELECT session + files query <-- 3c
│                       └── return status dict <-- uploads.py:980
├── Resume UI Display
│   └── enterResumeMode(data, savedSession) <-- 3d
│       ├── Show paused banner <-- upload.html:1537
│       ├── Pre-fill progress bars <-- upload.html:1553
│       └── Show file picker <-- upload.html:1540
└── User Re-selects Files
    └── resumeFileInput change listener <-- upload.html:1577
        └── handleResumeFileSelection(files) <-- upload.html:1598
            ├── Match files by name+size <-- 3e
            ├── new ChunkedUploader(matched) <-- upload.html:1632
            └── uploader.resumeAll() <-- 3f
                └── for each file <-- upload.html:918
                    ├── Calculate startOffset <-- 3g
                    └── uploadFile(i, startOffset) <-- upload.html:929

Location 3a — Resume Detection on Load
Path: /home/dave/CascadeProjects/snatched-v3/snatched/templates/upload.html:1648
Description: Page load triggers check for incomplete upload session

Location 3b — Session Status Fetch
Path: /home/dave/CascadeProjects/snatched-v3/snatched/templates/upload.html:1498
Description: Retrieves server state for session stored in localStorage

Location 3c — Status Endpoint Query
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/uploads.py:936
Description: Returns session progress including per-file bytes_received

Location 3d — Resume UI Activated
Path: /home/dave/CascadeProjects/snatched-v3/snatched/templates/upload.html:1512
Description: Shows paused upload screen with progress bars pre-filled from server

Location 3e — File Matching
Path: /home/dave/CascadeProjects/snatched-v3/snatched/templates/upload.html:1606
Description: User re-selects files; matched by name+size to server session

Location 3f — Resume Upload
Path: /home/dave/CascadeProjects/snatched-v3/snatched/templates/upload.html:1640
Description: Skips complete files, resumes partial files from bytes_received offset

Location 3g — Offset Calculation
Path: /home/dave/CascadeProjects/snatched-v3/snatched/templates/upload.html:928
Description: Each file resumes from its last successfully written byte

Trace 4 — Verification Failure & Re-upload Requirement
Verification Failure & Re-upload Flow
├── Server-side verification
│   ├── SHA-256 hash computed on .part file <-- uploads.py:663
│   ├── Hash comparison check <-- 4a
│   ├── File marked as failed in DB <-- 4b
│   └── 409 response with action payload <-- 4c
│       └── {"action": "re-upload", ...} <-- uploads.py:684
├── Client-side error handling
│   ├── ChunkedUploader.verifyFile() <-- upload.html:1006
│   │   ├── fetch(/api/upload/verify/...) <-- upload.html:1007
│   │   ├── response.json() parsed <-- upload.html:1024
│   │   └── Error thrown on mismatch <-- 4d
│   └── handleUploadError() <-- upload.html:1462
│       └── UI shows failure message <-- upload.html:1472
└── Subsequent upload attempts blocked
    └── receive_chunk() endpoint <-- uploads.py:366
        └── Rejects chunks for failed files <-- 4e

Location 4a — Hash Mismatch Detected
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/uploads.py:671
Description: Server-computed SHA-256 doesn't match client-provided hash

Location 4b — File Marked Failed
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/uploads.py:680
Description: Database records file as failed, preventing job creation

Location 4c — Re-upload Action Returned
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/uploads.py:691
Description: 409 response instructs client to re-upload corrupted file

Location 4d — Client Error Thrown
Path: /home/dave/CascadeProjects/snatched-v3/snatched/templates/upload.html:1027
Description: ChunkedUploader throws error on verification failure

Location 4e — Failed File Blocks Chunks
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/uploads.py:447
Description: Subsequent chunk uploads rejected for failed files

Trace 5 — Quick Rescue Job Processing & Auto-Export
Quick Rescue Job Processing Pipeline
├── Job Launch (after upload complete)
│   └── run_job() background task <-- 5a
│       ├── ZIP Extraction Phase
│       │   ├── merge_multipart_zips() called <-- jobs.py:285
│       │   │   └── zf.extractall(work_dir) <-- 5b
│       │   └── Validates path traversal safety <-- ingest.py:863
│       ├── Phase 1: Ingest
│       │   ├── phase1_ingest() orchestrator <-- 5c
│       │   │   ├── ingest_memories() <-- ingest.py:1197
│       │   │   ├── ingest_chat() <-- ingest.py:1198
│       │   │   └── scan_assets() <-- 5d
│       │   └── Populates SQLite proc.db
│       └── Job Status Update
│           └── status="scanned" <-- 5e
└── Auto-Export for Quick Rescue
    ├── Check processing_mode <-- 5f
    ├── create_export() <-- 5g
    │   └── export_type="quick_rescue" <-- jobs.py:489
    │       └── lanes=["memories"] <-- jobs.py:490
    └── run_export() worker launched <-- 5h
        └── Packages ZIP for download

Location 5a — ZIP Parts Merged
Path: /home/dave/CascadeProjects/snatched-v3/snatched/jobs.py:285
Description: file_N.part files extracted and merged into work directory

Location 5b — ZIP Extraction
Path: /home/dave/CascadeProjects/snatched-v3/snatched/processing/ingest.py:867
Description: Each .part file validated for path traversal then extracted

Location 5c — Ingest Phase
Path: /home/dave/CascadeProjects/snatched-v3/snatched/jobs.py:309
Description: Scans memories_history.json and discovers all media files

Location 5d — Asset Discovery
Path: /home/dave/CascadeProjects/snatched-v3/snatched/processing/ingest.py:1205
Description: All photos/videos discovered and inserted into assets table

Location 5e — Job Status: Scanned
Path: /home/dave/CascadeProjects/snatched-v3/snatched/jobs.py:472
Description: Ingest-only job completes with scanned status for quick_rescue

Location 5f — Auto-Export Trigger
Path: /home/dave/CascadeProjects/snatched-v3/snatched/jobs.py:481
Description: Quick Rescue mode automatically creates export without user action

Location 5g — Export Created
Path: /home/dave/CascadeProjects/snatched-v3/snatched/jobs.py:489
Description: Memories-only export with EXIF enabled, overlays burned

Location 5h — Export Worker Launched
Path: /home/dave/CascadeProjects/snatched-v3/snatched/jobs.py:500
Description: Background task packages rescued memories into downloadable ZIP

Trace 6 — Folder Upload Alternative Path
Folder Upload Alternative Path (Trace 6)

Client-Side: Folder Selection & Validation
├── User selects folder with webkitdirectory <-- 6a
├── validateSnapchatFolder() checks structure <-- upload.html:470
│   └── Check for memories_history.json <-- 6b
└── FolderUploader.start() prepares manifest <-- upload.html:634
    └── Store relative_path for each file <-- 6c

Server-Side: Session Initialization
└── POST /api/upload/init endpoint <-- uploads.py:112
    └── Create session with upload_type <-- 6d

Client-Side: Parallel File Upload
└── FolderUploader uploads all files <-- upload.html:668
    └── Each file uploaded as file_N.part <-- upload.html:694
        └── (same chunked upload as ZIP mode)

Server-Side: Verification & Reconstruction
└── POST /api/upload/verify (last file) <-- uploads.py:553
    ├── All files verified complete <-- uploads.py:742
    └── Folder reconstruction begins <-- 6e
        └── Move each .part to original path <-- 6f

Job Processing Pipeline
└── run_job() receives extracted_dir <-- jobs.py:147
    └── Skip ZIP extraction step <-- 6g
        └── Proceed directly to ingest phase <-- jobs.py:280

Location 6a — Folder Input
Path: /home/dave/CascadeProjects/snatched-v3/snatched/templates/upload.html:199
Description: User selects unzipped Snapchat export folder with webkitdirectory

Location 6b — Folder Validation
Path: /home/dave/CascadeProjects/snatched-v3/snatched/templates/upload.html:494
Description: Checks for memories_history.json and Snapchat directory structure

Location 6c — Relative Paths Preserved
Path: /home/dave/CascadeProjects/snatched-v3/snatched/templates/upload.html:638
Description: Each file's path stored for server-side tree reconstruction

Location 6d — Folder Mode Init
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/uploads.py:646
Description: Session created with upload_type='folder' instead of 'zip'

Location 6e — Tree Reconstruction
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/uploads.py:774
Description: After verification, .part files moved to original relative paths

Location 6f — Files Moved
Path: /home/dave/CascadeProjects/snatched-v3/snatched/routes/uploads.py:826
Description: Each file_N.part moved to extracted/session_id/original/path.jpg

Location 6g — Skip ZIP Extraction
Path: /home/dave/CascadeProjects/snatched-v3/snatched/jobs.py:279
Description: Pipeline receives pre-extracted directory, skips merge_multipart_zips