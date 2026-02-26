# Spec 11 — Chunked Multi-File Upload System

**Status**: Planning
**Date**: 2026-02-24
**Replaces**: Single-shot upload in `uploads.py` + `upload.html`
**Dependencies**: spec-08 (web app), spec-03 (ingest)

---

## Problem

Snapchat exports arrive as **multiple 2GB ZIP parts** (e.g., `mydata~1.zip`, `mydata~2.zip`, ..., `mydata~7.zip`). A typical user has 10–20 GB across 5–10 parts.

The current upload system:
- Reads entire file into RAM (`await file.read()`) — OOMs on 2GB+
- Accepts only one file per job
- No resume — connection drop = full re-upload
- No per-file progress — just a spinner
- 5GB hard cap

**This is the #1 blocker for real-world use.**

---

## Solution Overview

```
┌─────────────────────────────────────────────────────────────┐
│  BROWSER                                                     │
│                                                              │
│  1. User drops N files into upload zone                      │
│  2. Client computes SHA-256 of each file (streaming)         │
│  3. POST /api/upload/init → gets session_id                  │
│  4. For each file, upload in 5MB chunks:                     │
│     PUT /api/upload/chunk/{session_id}/{file_idx}/{offset}   │
│  5. After each file completes, server verifies SHA-256       │
│  6. When all files verified → pipeline starts                │
│                                                              │
│  UI: per-file progress bars, overall %, resume button        │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│  SERVER                                                      │
│                                                              │
│  /api/upload/init     → create upload session, allocate dirs │
│  /api/upload/chunk    → write chunk to disk, track offset    │
│  /api/upload/verify   → SHA-256 check, mark file complete    │
│  /api/upload/status   → return progress for resume           │
│  /api/upload/abort    → cleanup incomplete session           │
│                                                              │
│  Storage: /data/{user}/staging/{session_id}/                 │
│  Tracking: PostgreSQL upload_sessions + upload_files tables  │
└─────────────────────────────────────────────────────────────┘
```

---

## Design Decisions

### Chunk Size: 5 MB
- A 2GB file = 400 chunks = 400 HTTP requests
- Small enough to retry quickly on failure
- Large enough to avoid excessive overhead
- With HTTP/2 pipelining, throughput stays high
- Configurable via `upload.chunk_size_bytes` in snatched.toml

### Integrity: SHA-256 (end-to-end)
- Client computes SHA-256 of entire file using Web Crypto API (streaming, not RAM-bound)
- Sends hash with init request
- Server computes SHA-256 of assembled file after all chunks arrive
- Mismatch → reject file, client re-uploads
- Per-chunk CRC32 optional (future) — SHA-256 on the full file is sufficient

### Resume: Server Tracks Offsets
- Each file has a `bytes_received` counter in the DB
- Client can call `GET /api/upload/status/{session_id}` to get current state
- If browser closes mid-upload, user returns to upload page, sees "Resume upload" with progress
- Session TTL: 24 hours (configurable), after which incomplete uploads are cleaned up

### Multi-Part ZIP Merge
- Snapchat exports use naming: `mydata~1.zip`, `mydata~2.zip`, etc.
- After all files uploaded, ingest phase extracts each ZIP into a shared working directory
- Overlapping directory structures are merged (Snap uses consistent paths across parts)
- If user uploads a single large ZIP, it works identically (just one file in the session)

### No tus Protocol
- tus adds complexity (custom headers, protocol negotiation, HEAD requests for resume)
- We control both client and server — custom protocol is simpler and more maintainable
- Same resume/integrity guarantees without the abstraction layer

---

## Database Schema

### PostgreSQL: New Tables

```sql
-- Upload sessions (one per upload attempt)
CREATE TABLE upload_sessions (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT NOT NULL REFERENCES users(id),
    session_token   TEXT NOT NULL UNIQUE,          -- UUID, used in URLs
    status          TEXT NOT NULL DEFAULT 'active', -- active | completed | expired | aborted
    file_count      INT NOT NULL,                   -- expected number of files
    total_bytes     BIGINT NOT NULL,                -- sum of all file sizes
    bytes_received  BIGINT NOT NULL DEFAULT 0,      -- sum across all files
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ NOT NULL,           -- created_at + 24h
    completed_at    TIMESTAMPTZ,
    job_id          BIGINT REFERENCES processing_jobs(id)  -- set when pipeline starts
);

-- Individual files within a session
CREATE TABLE upload_files (
    id              BIGSERIAL PRIMARY KEY,
    session_id      BIGINT NOT NULL REFERENCES upload_sessions(id) ON DELETE CASCADE,
    file_index      INT NOT NULL,                   -- 0-based position
    filename        TEXT NOT NULL,                   -- original filename
    file_size       BIGINT NOT NULL,                -- expected size in bytes
    sha256_expected TEXT NOT NULL,                   -- client-provided hash
    sha256_actual   TEXT,                            -- server-computed after assembly
    bytes_received  BIGINT NOT NULL DEFAULT 0,      -- chunks received so far
    status          TEXT NOT NULL DEFAULT 'pending', -- pending | uploading | verifying | complete | failed
    completed_at    TIMESTAMPTZ,
    UNIQUE(session_id, file_index)
);

CREATE INDEX idx_upload_sessions_user ON upload_sessions(user_id);
CREATE INDEX idx_upload_sessions_token ON upload_sessions(session_token);
CREATE INDEX idx_upload_sessions_expires ON upload_sessions(expires_at) WHERE status = 'active';
CREATE INDEX idx_upload_files_session ON upload_files(session_id);
```

---

## API Endpoints

### POST /api/upload/init

Initialize an upload session.

**Request:**
```json
{
    "files": [
        {"filename": "mydata~1.zip", "size": 2147483648, "sha256": "a1b2c3..."},
        {"filename": "mydata~2.zip", "size": 2147483648, "sha256": "d4e5f6..."},
        {"filename": "mydata~3.zip", "size": 1073741824, "sha256": "g7h8i9..."}
    ]
}
```

**Validation:**
- All files must be `.zip`
- Total size must not exceed `upload.max_total_bytes` (default 25 GB)
- Individual file size must not exceed `upload.max_file_bytes` (default 5 GB)
- User quota check: `used + total_new <= user.storage_quota_bytes`
- Max concurrent active sessions per user: 1

**Response (201):**
```json
{
    "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "expires_at": "2026-02-25T14:30:00Z",
    "chunk_size": 5242880,
    "files": [
        {"index": 0, "filename": "mydata~1.zip", "status": "pending", "bytes_received": 0},
        {"index": 1, "filename": "mydata~2.zip", "status": "pending", "bytes_received": 0},
        {"index": 2, "filename": "mydata~3.zip", "status": "pending", "bytes_received": 0}
    ]
}
```

**Storage:** Creates `/data/{username}/staging/{session_id}/`

---

### PUT /api/upload/chunk/{session_id}/{file_index}

Upload a single chunk.

**Headers:**
```
Content-Type: application/octet-stream
X-Chunk-Offset: 0          (byte offset within the file)
Content-Length: 5242880     (chunk size, last chunk may be smaller)
```

**Body:** Raw bytes (the chunk data)

**Server behavior:**
1. Validate session exists, is active, not expired
2. Validate file_index is in range
3. Validate offset matches `bytes_received` for this file (no gaps, no duplicates)
4. **Stream chunk directly to disk** — no RAM buffering of the full file
5. Update `upload_files.bytes_received += chunk_size`
6. Update `upload_sessions.bytes_received += chunk_size`
7. If `bytes_received == file_size` → trigger verification

**Response (200):**
```json
{
    "file_index": 0,
    "bytes_received": 5242880,
    "file_size": 2147483648,
    "complete": false
}
```

**Streaming write (critical):**
```python
# Write chunk directly to disk — never hold full file in RAM
chunk_path = staging_dir / f"{file_index}.part"
async with aiofiles.open(chunk_path, "ab") as f:
    while True:
        data = await request.body()  # Already limited by Content-Length
        if not data:
            break
        await f.write(data)
```

---

### POST /api/upload/verify/{session_id}/{file_index}

Trigger integrity verification after all chunks received.

**Server behavior:**
1. Compute SHA-256 of assembled file on disk (streaming, 64KB blocks)
2. Compare to `sha256_expected`
3. Match → status = `complete`
4. Mismatch → status = `failed`, delete file, return error with mismatch details

**Response (200):**
```json
{
    "file_index": 0,
    "verified": true,
    "sha256": "a1b2c3..."
}
```

**Response (409 on mismatch):**
```json
{
    "file_index": 0,
    "verified": false,
    "expected": "a1b2c3...",
    "actual": "x9y8z7...",
    "action": "re-upload"
}
```

**Auto-trigger pipeline:** When the LAST file in the session is verified:
1. Set `upload_sessions.status = 'completed'`
2. Create `processing_jobs` record
3. Launch `run_job()` as background task
4. Return job_id in response for redirect

---

### GET /api/upload/status/{session_id}

Resume endpoint — returns current state of all files.

**Response (200):**
```json
{
    "session_id": "a1b2c3d4-...",
    "status": "active",
    "expires_at": "2026-02-25T14:30:00Z",
    "total_bytes": 5368709120,
    "bytes_received": 3221225472,
    "percent": 60.0,
    "files": [
        {"index": 0, "filename": "mydata~1.zip", "status": "complete", "bytes_received": 2147483648, "file_size": 2147483648},
        {"index": 1, "filename": "mydata~2.zip", "status": "uploading", "bytes_received": 926941184, "file_size": 2147483648},
        {"index": 2, "filename": "mydata~3.zip", "status": "pending", "bytes_received": 0, "file_size": 1073741824}
    ]
}
```

Used by the client on page load to detect and resume interrupted uploads.

---

### DELETE /api/upload/abort/{session_id}

Cancel and clean up an upload session.

- Sets status = `aborted`
- Deletes staging directory
- Frees quota reservation

---

## Frontend: upload.html Rebuild

### File Selection
```
┌─────────────────────────────────────────────────────┐
│                                                       │
│          ╔═══════════════════════════════╗            │
│          ║   Drop your Snapchat export   ║            │
│          ║        files here             ║            │
│          ║                               ║            │
│          ║   📁 Select Files             ║            │
│          ╚═══════════════════════════════╝            │
│                                                       │
│   Multiple .zip files supported (2GB parts)           │
│   Max total: 25 GB                                    │
│                                                       │
│   ┌─ Files ─────────────────────────────────┐        │
│   │ ✓ mydata~1.zip        2.0 GB   ██████░ │        │
│   │ ⟳ mydata~2.zip        2.0 GB   ████░░░ │        │
│   │ ◻ mydata~3.zip        1.0 GB   ░░░░░░░ │        │
│   │                                          │        │
│   │ Total: 5.0 GB  ·  3 files               │        │
│   └──────────────────────────────────────────┘        │
│                                                       │
│   [ ▶ UPLOAD & PROCESS ]         overall: 48%        │
│                                                       │
│   ☐ Burn overlays  ☐ Dark mode  ☐ EXIF embed         │
│                                                       │
└─────────────────────────────────────────────────────┘
```

### Upload Progress (replaces file list after start)
```
┌─────────────────────────────────────────────────────┐
│                                                       │
│   UPLOADING — DO NOT CLOSE THIS TAB                  │
│                                                       │
│   Overall: 48%  ████████████░░░░░░░░░░  2.4 / 5.0 GB│
│                                                       │
│   mydata~1.zip   COMPLETE ✓     2.0 / 2.0 GB        │
│   ██████████████████████████████████████████████████  │
│                                                       │
│   mydata~2.zip   UPLOADING      430 / 2048 MB        │
│   ██████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  21%    │
│                                                       │
│   mydata~3.zip   WAITING        0 / 1024 MB          │
│   ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  0%    │
│                                                       │
│   Speed: 12.4 MB/s  ·  ETA: 3m 24s                  │
│                                                       │
│   [ ✕ CANCEL ]                                        │
│                                                       │
└─────────────────────────────────────────────────────┘
```

### JavaScript Architecture

```javascript
class ChunkedUploader {
    constructor(files, options) {
        this.files = files;           // FileList from input
        this.chunkSize = 5 * 1024 * 1024;  // 5MB
        this.sessionId = null;
        this.aborted = false;
        this.onProgress = options.onProgress;   // per-file callback
        this.onFileComplete = options.onFileComplete;
        this.onAllComplete = options.onAllComplete;
        this.onError = options.onError;
    }

    // Phase 1: Compute SHA-256 for all files (Web Crypto API)
    async computeHashes() { ... }

    // Phase 2: Initialize session with server
    async initSession(fileManifest) { ... }

    // Phase 3: Upload all files sequentially (or 2 concurrent)
    async uploadAll() { ... }

    // Upload single file in chunks
    async uploadFile(file, fileIndex) {
        const totalChunks = Math.ceil(file.size / this.chunkSize);
        let offset = this.resumeOffsets[fileIndex] || 0;

        for (let i = Math.floor(offset / this.chunkSize); i < totalChunks; i++) {
            if (this.aborted) throw new Error('Aborted');

            const start = i * this.chunkSize;
            const end = Math.min(start + this.chunkSize, file.size);
            const chunk = file.slice(start, end);

            await this.sendChunk(fileIndex, start, chunk);
            this.onProgress(fileIndex, end, file.size);
        }

        await this.verifyFile(fileIndex);
    }

    // Send single chunk with retry (3 attempts, exponential backoff)
    async sendChunk(fileIndex, offset, chunk, attempt = 0) { ... }

    // Verify file integrity
    async verifyFile(fileIndex) { ... }

    // Resume: query server for current state
    async resume(sessionId) { ... }

    // Abort: cancel and cleanup
    async abort() { ... }
}
```

**Key behaviors:**
- Files upload **sequentially** (one at a time) to avoid saturating the connection
- Each chunk retries **3 times** with exponential backoff (1s, 2s, 4s)
- SHA-256 computed using `crypto.subtle.digest()` with streaming via `ReadableStream`
- Progress callbacks fire per-chunk for smooth progress bars
- Speed calculation: rolling average over last 10 chunks
- ETA: `remaining_bytes / rolling_speed`
- Resume: on page load, check `localStorage` for `snatched_upload_session`, query status endpoint

---

## Server Implementation

### New File: `snatched/routes/uploads.py` (rewrite)

```python
# Key functions:
async def init_upload(request, user) -> UploadSession
async def receive_chunk(session_id, file_index, request, user) -> ChunkResult
async def verify_file(session_id, file_index, user) -> VerifyResult
async def upload_status(session_id, user) -> SessionStatus
async def abort_upload(session_id, user) -> None

# Background task:
async def cleanup_expired_sessions() -> None  # runs every hour
```

### Streaming Disk Write (no RAM buffering)
```python
async def receive_chunk(session_id: str, file_index: int, request: Request):
    # Validate session, file, offset
    chunk_path = staging_dir / f"file_{file_index}.part"

    async with aiofiles.open(chunk_path, "r+b") as f:
        await f.seek(expected_offset)
        # Stream from request body directly to disk
        async for chunk in request.stream():
            await f.write(chunk)
            bytes_written += len(chunk)

    # Update DB counters
    await update_file_progress(session_id, file_index, bytes_written)
```

### SHA-256 Verification (streaming)
```python
async def verify_file_hash(file_path: Path, expected_hash: str) -> bool:
    sha256 = hashlib.sha256()
    async with aiofiles.open(file_path, "rb") as f:
        while chunk := await f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest() == expected_hash
```

### Multi-Part ZIP Merge (in ingest.py)
```python
async def extract_multipart_zips(staging_dir: Path, work_dir: Path):
    """Extract all ZIP parts into a merged working directory."""
    zip_files = sorted(staging_dir.glob("file_*.part"))
    for zip_path in zip_files:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(work_dir)
    # Snap's directory structure is consistent across parts
    # Later ZIPs overwrite duplicates (if any) — last-write-wins
```

---

## Config Additions (snatched.toml)

```toml
[upload]
chunk_size_bytes = 5242880          # 5 MB per chunk
max_file_bytes = 5368709120         # 5 GB per individual file
max_total_bytes = 26843545600       # 25 GB total per session
session_ttl_hours = 24              # expire incomplete uploads after 24h
max_concurrent_sessions = 1         # per user
cleanup_interval_minutes = 60       # check for expired sessions
```

---

## Migration Path

### What Changes
| Component | Before | After |
|-----------|--------|-------|
| `uploads.py` | 114 lines, `file.read()` | ~300 lines, chunked streaming |
| `upload.html` | Single file input + drag-drop | Multi-file + ChunkedUploader class |
| `api.py` | `POST /api/upload` | 5 new endpoints (init, chunk, verify, status, abort) |
| `jobs.py` | Creates job from upload handler | Creates job from verify handler (last file) |
| `ingest.py` | Opens single ZIP | Extracts multiple ZIPs from staging dir |
| `config.py` | `max_upload_bytes` | New `[upload]` section |
| PostgreSQL | — | 2 new tables (upload_sessions, upload_files) |
| `style.css` | Upload zone styles | + progress bar styles, file list styles |

### What Stays the Same
- All processing pipeline code (match, enrich, export)
- Per-user SQLite schema
- Job progress SSE
- Results, download, dashboard pages
- Auth (Authelia headers)

### Backwards Compatibility
- Old `POST /api/upload` endpoint removed (no external consumers)
- Upload page is the only entry point — UI change is the migration

---

## Concurrent User Considerations

| Concern | Solution |
|---------|----------|
| Disk space during upload | Staging dirs cleaned on completion/expiry/abort |
| RAM usage | Streaming writes — never buffer full file |
| CPU during SHA-256 | Server verification runs in thread pool (non-blocking) |
| DB connections | Upload tracking uses same asyncpg pool |
| Upload bandwidth | Sequential file upload per user limits per-user bandwidth |
| Quota enforcement | Total size reserved at init, released on abort/expiry |
| Cleanup | Background task sweeps expired sessions every hour |

---

## Testing Plan

| Test | Method |
|------|--------|
| Single 100MB file upload | Manual — should work like before but chunked |
| Multi-file (3 x 100MB) | Manual — all three process and merge |
| Connection drop + resume | Kill browser mid-upload, reopen, verify resume |
| SHA-256 mismatch | Corrupt a chunk, verify server rejects |
| Session expiry | Set TTL to 1 minute, verify cleanup |
| Quota exceeded | Set low quota, verify 507 response |
| Concurrent users | Two browser tabs, different users, simultaneous uploads |
| Large file (2GB+) | Real Snapchat export part — verify no OOM |

---

## Implementation Order

1. **Database migration** — Add `upload_sessions` + `upload_files` tables
2. **Config** — Add `[upload]` section to config.py + snatched.toml
3. **Server endpoints** — New upload routes (init, chunk, verify, status, abort)
4. **Ingest update** — Multi-ZIP extraction in `ingest.py`
5. **Frontend** — Rebuild upload.html with ChunkedUploader JS
6. **Cleanup task** — Background expired session sweeper
7. **CSS** — Progress bar and file list styles
8. **Testing** — Manual verification matrix above
9. **Deploy** — Sync to build context, rebuild container
