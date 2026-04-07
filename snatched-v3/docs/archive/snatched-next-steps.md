## Snatched v3 — Next Steps (Post-Compaction Reference)

### What Just Happened (2026-02-28 sessions)

**15 post-deploy audit items fixed** (W-1 through W-5, B-1 through B-6, C-1):
- JSON double-encoding (db.py, uploads.py, export_worker.py)
- Export pipeline wiring (dark_mode_pngs, auto-export event, polling, redirect loop)
- Error handling + cleanup (jobs.py finally blocks, staging cleanup guard)
- Container restart recovery (advisory lock + proc.db detection)

**Readonly export fix** — 5 functions in export.py + xmp.py got `readonly: bool = False` param. export_worker.py passes `True`. Paths resolved from `matches.output_subdir/output_filename` instead of `assets.output_path`.

**Logging fix** — `logging.basicConfig()` added to app.py. All `snatched.*` loggers now emit to container logs. Previously 100% silent.

**Task exception logging** — `task.add_done_callback()` added to export `asyncio.create_task` in api.py so fire-and-forget crashes get logged.

**Intelligence Report redesign** — `_query_proc_db_stats()` in pages.py, two-mode display in snatchedmemories.html (processing vs completed).

**Failed export visibility** — snatchedmemories.html now shows failed exports with error message + "Try again" link.

**Verified working**: Export 14 (stories+chats, full options) — 1,079 files, 1 ZIP, 950 MB, zero errors.

### Files Modified (all synced to CascadeProjects)

| File | Key Changes |
|------|-------------|
| `app.py` | `logging.basicConfig()` |
| `api.py` | Export task done callback, `_require_admin()`, admin gating |
| `pages.py` | `_load_tier_info()`, `_query_proc_db_stats()`, hardcoded dict removals |
| `export.py` | `readonly` flag on `copy_files`, `write_exif`, `burn_overlays`, `export_chat_png` |
| `export_worker.py` | `readonly=True` to all calls, `_build_config_for_export`, dark_mode_pngs |
| `xmp.py` | `readonly` flag on `write_xmp_sidecars` |
| `snatchedmemories.html` | Intel Report redesign, failed export display |
| `jobs.py` | `_job_tasks` registration, finally cleanup, auto-export emit_event |
| `uploads.py` | `job_succeeded` staging cleanup guard |
| `db.py` | `is_admin` + `dark_mode_pngs` migrations |

### Audit Checklist (for next session)

1. **Rebuild container** and verify clean startup logs
2. **Test Quick Rescue flow end-to-end** — upload → process → auto-export → download
3. **Test Full Export from Quick Rescue** — "Create Full Export" button → configure → build → download
4. **Test direct Full Export flow** — upload with Full Export selected → all lanes
5. **Verify failed export display** — check snatchedmemories.html shows error for any failures
6. **Verify Intelligence Report** — both processing mode (during job) and completed mode (after)
7. **Verify admin gating** — non-admin user gets 403 on `/admin/*` pages
8. **Check container logs** — confirm `snatched.processing.*` loggers visible during export

### Known Cleanup Items

- Exports 9, 10 deleted. Exports 11, 12 force-marked failed + deleted. Export 13 (test) deleted. Only 8 + 14 remain.
- Orphaned work directories may exist at `/data/dave/jobs/16/exports/{9,10,11,12,13}/` — can be cleaned up
- `SNATCHED_JWT_SECRET` is 17 bytes — security warning on every startup. Needs proper secret for production.

### Queued Feature Work (not started)

- **Centralized Tier/Limits** — plan exists at `~/.claude/plans/imperative-chasing-gadget.md`. DB-backed tier_plans table, system_config circuit breakers, admin editor pages. Not yet implemented.
