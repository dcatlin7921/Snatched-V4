# Snatched v3 — Production Queue & Worker System Plan

**Date:** 2026-03-19
**Status:** PLANNED — Not yet implemented
**Source:** 3-agent Review Panel (Foreman, Concierge, Inspector)

---

## Executive Summary

Snatched v3 currently uses fire-and-forget `asyncio.create_task()` for job processing. This works for 2 users but breaks under concurrent multi-user load. This plan covers the full production upgrade: ARQ worker queue, UX for long-running jobs, and 15 production readiness fixes.

---

## Architecture: ARQ + Redis

**Decision:** ARQ (async Redis queue) using existing `immich-redis` on DB index 1.

```
┌─────────────────────────────────────────────────────┐
│  Docker Container: snatched                         │
│                                                     │
│  ┌─────────────────┐    ┌─────────────────────┐    │
│  │  uvicorn (HTTP)  │    │  ARQ Worker         │    │
│  │  - uploads       │───▶│  - run_job()        │    │
│  │  - auth/SSE      │    │  - run_export()     │    │
│  │  - admin         │    │  max_jobs=4         │    │
│  └─────────────────┘    └─────────────────────┘    │
│           │                        │                │
│           └──────────┬─────────────┘                │
│                      ▼                              │
│              Redis DB 1 (ARQ queue)                 │
│              PostgreSQL (job state)                  │
│              /ramdisk 64GB tmpfs                    │
└─────────────────────────────────────────────────────┘
```

**Why ARQ over Celery:** ARQ is async-native (matches existing codebase), 300 lines of library vs Celery's framework weight, supports async job functions directly, uses Redis (already running).

**Why not DB polling:** Adds latency, hammers PostgreSQL, harder to implement priority queues.

---

## Job Lifecycle State Machine

```
pending → queued → running → exporting → completed/failed/cancelled
```

**New states:** `queued` (in Redis, not yet running), `exporting` (long export phase, separate from processing).

**Key change:** `run_job()` and `run_export()` become separate ARQ jobs. When processing completes, it enqueues the export as a new job and frees its slot.

---

## Concurrency Control

| Control | Current | New |
|---------|---------|-----|
| Per-user serialization | In-memory asyncio.Lock (broken) | PostgreSQL advisory lock per user_id |
| Global job cap | TOCTOU SELECT COUNT (racey) | ARQ max_jobs=4 (hard enforcement) |
| Queue depth | None | DB check: reject if >20 queued |
| Ramdisk reservation | None | `ramdisk_reserved_bytes` column, check before admit |

---

## Priority System

- `high` queue — Pro tier users
- `default` queue — Free tier users
- ARQ worker polls `high` first. FIFO within tier.

---

## UX Changes for Long-Running Jobs

### Queue Position Banner (snatchedmemories.html)
- Shows "#3 in queue · Est. wait ~14 min"
- Email capture: "Notify me when done"
- Polled via htmx every 30s

### "Come Back Later" Nudge
- Appears after 90s on progress page if ETA > 5 min
- Not a modal — collapsible bar with email capture
- "Go to Dashboard" (job continues in background)

### Upload Acknowledgment Screen
- New interstitial: `/jobs/{id}/confirm`
- Shows file count, "what happens next" steps, email capture
- Auto-redirects to progress in 10s

### Email Notifications
- "Your processing has started" (when job leaves queue)
- "Your memories are ready" (on completion)
- Plain text, Rebellion voice, transactional only

### Dashboard Job Cards
- Status badges: QUEUED / PROCESSING / PACKAGING / SNATCHED / FAILED
- Mini progress bar on running cards
- Expiry warning at 7 days before retention

### ETA Display Rules
- >60 min: "over an hour"
- 11-60 min: "~N min" (round to 5)
- 5-10 min: "~N min" (round to 1)
- <5 min: "almost done"
- Update max once per 30s (prevent anxiety from fluctuating ETAs)

---

## Production Readiness Fixes (15 Findings)

### CRITICAL (fix before any public traffic)
| # | Finding | Fix | Effort |
|---|---------|-----|--------|
| C1 | `SNATCHED_DEV_MODE=1` in production compose | Set to 0, generate real JWT secret | 5 min |
| C2 | In-memory queue broken with 4 workers | ARQ + DB advisory locks (main project) | 3 days |

### HIGH (fix before SaaS launch)
| # | Finding | Fix | Effort |
|---|---------|-----|--------|
| H1 | No ramdisk free-space check at write time | `shutil.disk_usage()` gate in chunk upload | 2 hrs |
| H2 | No login brute-force protection | Track attempts per username+IP, lockout after 5 | 1 day |
| H3 | No disk space check before export | Check free space >= 1.5x estimated export | 2 hrs |
| H4 | SIGTERM doesn't drain running jobs | Iterate _job_tasks, await with 30s timeout | 1 day |
| H5 | Unbounded status query parameter | Validate against allowlist, cap at 10 values | 30 min |
| H6 | ZIP bomb not defended at extraction | Track extracted bytes, abort at 2x upload size | 4 hrs |
| H7 | DB pool can exhaust/hang indefinitely | Set pool timeout=30, return 503 on exhaustion | 1 hr |

### MEDIUM (fix for production polish)
| # | Finding | Fix | Effort |
|---|---------|-----|--------|
| M1 | Dual admin auth systems | Deprecate header-based, keep DB-based | 2 hrs |
| M2 | Failed job staging stays on ramdisk | Per-user staging cap, purge oldest on overflow | 4 hrs |
| M3 | Exception messages leak paths via SSE | Categorize exceptions, emit user-friendly messages | 4 hrs |
| M4 | Health check misses functional health | Add queue_depth, active_jobs, oldest_job_age | 2 hrs |
| M5 | No deployment drain strategy | `POST /api/admin/drain` maintenance mode endpoint | 4 hrs |

### LOW
| # | Finding | Fix | Effort |
|---|---------|-----|--------|
| L1 | Snatched data not in backup | Add volume + pg_dump to backup agent | 2 hrs |

---

## Implementation Phases

### Phase 0 — Emergency Fixes (Day 1)
- [ ] C1: Set `SNATCHED_DEV_MODE=0`, generate real JWT secret
- [ ] H5: Validate status query params
- [ ] H7: Set DB pool timeout=30

### Phase 1 — ARQ Worker (Days 2-4)
- [ ] Add `arq` dependency
- [ ] Create `snatched/worker.py` with WorkerSettings
- [ ] Modify uploads.py: enqueue to ARQ instead of create_task
- [ ] Modify run_job() for ARQ-compatible signature
- [ ] Add ARQ pool to app.py lifespan
- [ ] Update entrypoint to start uvicorn + arq worker
- [ ] Add `queued` status to DB schema

### Phase 2 — Fix Locking & Ramdisk (Days 5-6)
- [ ] Replace asyncio.Lock with DB advisory locks
- [ ] Delete queue.py module
- [ ] Add `ramdisk_reserved_bytes` column
- [ ] Add ramdisk reservation check at upload finalize
- [ ] Add disk space check before export (H3)
- [ ] Add ramdisk free-space check in chunk upload (H1)

### Phase 3 — Split Export Jobs (Days 7-9)
- [ ] run_job() enqueues run_export() as separate ARQ job
- [ ] Add `exporting` status to state machine
- [ ] Export queue with max_jobs=8 (I/O bound, higher concurrency)
- [ ] Test SSE streaming works across job split

### Phase 4 — UX & Notifications (Days 10-13)
- [ ] Queue position banner on snatchedmemories.html
- [ ] Upload acknowledgment screen (/jobs/{id}/confirm)
- [ ] "Come back later" nudge bar
- [ ] Email notification capture (POST /api/jobs/{id}/notify)
- [ ] Email sending (aiosmtplib)
- [ ] Dashboard job card redesign
- [ ] ETA calculation based on historical averages
- [ ] Priority queues (high/default)

### Phase 5 — Security Hardening (Days 14-16)
- [ ] H2: Login brute-force protection
- [ ] H4: SIGTERM graceful drain
- [ ] H6: ZIP bomb defense
- [ ] M1-M5: Medium findings
- [ ] L1: Add snatched to backup

### Phase 6 — Production Polish (Days 17-18)
- [ ] Error state redesign (user-friendly messages)
- [ ] Mobile CSS fixes
- [ ] Micro-interactions (transitions, animations)
- [ ] Deployment drain endpoint (POST /api/admin/drain)

---

## Key Files to Change

| File | Change |
|------|--------|
| `snatched/worker.py` | NEW: ARQ WorkerSettings |
| `snatched/app.py` | ARQ pool in lifespan, graceful shutdown |
| `snatched/routes/uploads.py` | Enqueue to ARQ, ramdisk checks |
| `snatched/jobs.py` | ARQ-compatible, DB advisory lock |
| `snatched/queue.py` | DELETE (replaced by DB locks) |
| `snatched/routes/api.py` | Status validation, notify endpoint, drain |
| `snatched/routes/pages.py` | Confirm page, rate limiting |
| `snatched/templates/snatchedmemories.html` | Queue banner, nudge bar, ETA |
| `snatched/templates/dashboard.html` | Job card redesign |
| `snatched/templates/confirm.html` | NEW: upload acknowledgment |
| `snatched/static/style.css` | Job badges, nudge bar, mobile fixes |
| `docker-compose.yml` | DEV_MODE=0, JWT secret, entrypoint |
| DB migration | `queued`/`exporting` statuses, `ramdisk_reserved_bytes`, `notification_email` |

---

## Scaling Path

**Single server (now):** One ARQ worker, max_jobs=4, shared Redis/PostgreSQL.
**Multi-server (future):** Add second server with ARQ worker pointing at same Redis. Add `ramdisk_host` column for per-server ramdisk accounting. SSE stays on web server (reads from PostgreSQL). Zero code changes needed in queue layer.
