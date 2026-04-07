"""Job queue management and SSE streaming for processing pipelines.

Manages the lifecycle of processing jobs: create, run (4-phase pipeline),
update status, emit events, stream progress via Server-Sent Events, and cancel.
"""

import asyncio
import json
import logging
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator

import asyncpg

from snatched.db import update_job, emit_event, get_events_after

logger = logging.getLogger("snatched.jobs")

# Active job tasks for cancellation support
_job_tasks: dict[int, asyncio.Task] = {}


def _rewrite_procdb_paths(db_path: Path, old_prefix: str, new_prefix: str) -> int:
    """Rewrite absolute paths in proc.db after ramdisk→disk migration.

    Replaces all occurrences of old_prefix with new_prefix in the
    assets.path column so that export/copy functions find the files
    at their new disk location.

    Returns the number of rows updated.
    """
    import sqlite3
    db = sqlite3.connect(str(db_path))
    try:
        cur = db.execute(
            "UPDATE assets SET path = REPLACE(path, ?, ?) WHERE path LIKE ?",
            (old_prefix, new_prefix, old_prefix + "%"),
        )
        updated = cur.rowcount
        db.commit()
        return updated
    finally:
        db.close()


@dataclass
class JobStatus:
    """Snapshot of a processing job's current state."""
    id: int
    user_id: int
    status: str           # pending | running | completed | failed | cancelled
    progress_pct: int
    current_phase: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


async def create_processing_job(
    pool: asyncpg.Pool,
    user_id: int,
    upload_filename: str,
    upload_size_bytes: int,
    phases_requested: list[str],
    lanes_requested: list[str],
    processing_mode: str = "speed_run",
    job_group_id: str | None = None,
) -> int:
    """Insert a new processing job record in PostgreSQL.

    Args:
        processing_mode: 'speed_run' | 'power_user' | 'quick_rescue'
        job_group_id: Optional group ID for linking bulk uploads.

    Returns:
        New job ID (integer).
    """
    if processing_mode not in ("speed_run", "power_user", "quick_rescue"):
        processing_mode = "speed_run"

    async with pool.acquire() as conn:
        job_id = await conn.fetchval(
            """
            INSERT INTO processing_jobs
                (user_id, upload_filename, upload_size_bytes,
                 phases_requested, lanes_requested, processing_mode,
                 job_group_id, status)
            VALUES ($1, $2, $3, $4, $5, $6, $7, 'pending')
            RETURNING id
            """,
            user_id, upload_filename, upload_size_bytes,
            phases_requested, lanes_requested, processing_mode,
            job_group_id,
        )
    logger.info(f"Created job {job_id} for user_id {user_id}")
    return job_id


async def _migrate_legacy_data(data_dir: Path, username: str, job_id: int) -> None:
    """Move pre-isolation data from /data/{user}/ to /data/{user}/jobs/{job_id}/ if needed.

    Detects the legacy flat layout (proc.db sitting directly under the user dir)
    and relocates it to the per-job directory so existing single-job users are
    seamlessly upgraded.  Only runs when job_id == 1 and the jobs/ directory does
    not yet exist.
    """
    user_dir = data_dir / username
    legacy_proc = user_dir / "proc.db"
    jobs_dir = user_dir / "jobs"
    job_dir = jobs_dir / str(job_id)

    # Only migrate if legacy layout exists AND the target job dir was just created
    # (i.e. jobs/ didn't exist before this run) AND we're job 1.
    if not legacy_proc.exists() or job_id != 1:
        return
    # If job_dir already has a proc.db we already migrated — skip.
    if (job_dir / "proc.db").exists():
        return

    logger.info(f"Migrating legacy user data for '{username}' to per-job layout (job 1)")
    job_dir.mkdir(parents=True, exist_ok=True)

    for item in ["proc.db", "extracted", "output", "output.zip", ".snatched"]:
        source = user_dir / item
        if source.exists():
            target = job_dir / item
            try:
                shutil.move(str(source), str(target))
                logger.info(f"Migrated {source} -> {target}")
            except Exception as exc:
                logger.warning(f"Failed to migrate {source}: {exc}")

    # Also move any export-*.zip files produced by the split-ZIP export phase
    for zip_file in user_dir.glob("export-*.zip"):
        try:
            shutil.move(str(zip_file), str(job_dir / zip_file.name))
            logger.info(f"Migrated {zip_file} -> {job_dir / zip_file.name}")
        except Exception as exc:
            logger.warning(f"Failed to migrate {zip_file}: {exc}")


async def run_job(
    pool: asyncpg.Pool,
    job_id: int,
    username: str,
    config: "Config",
    staging_dir: str | None = None,
) -> None:
    """Execute the 4-phase processing pipeline as a background asyncio task.

    Runs ingest → match → enrich → export, updating job status and
    emitting events at each phase boundary.

    Args:
        staging_dir: Path to chunked upload staging directory containing .part files.
                     If provided, files are extracted before ingest. Cleaned up after pipeline.
    """
    _job_tasks[job_id] = asyncio.current_task()

    from snatched.processing import enrich, ingest, match
    from snatched.processing.sqlite import open_database
    from snatched.config import LaneConfig, ExifConfig

    data_dir = Path(str(config.server.data_dir)) / username / "jobs" / str(job_id)
    data_dir.mkdir(parents=True, exist_ok=True)
    loop = asyncio.get_running_loop()

    # RAM drive paths for processing (fast I/O during ingest/match/enrich)
    ramdisk_base = Path("/ramdisk/jobs") / str(job_id)
    use_ramdisk = Path("/ramdisk").exists()

    if use_ramdisk:
        ramdisk_base.mkdir(parents=True, exist_ok=True)
        work_dir = ramdisk_base  # processing happens in RAM
        logger.info(f"Job {job_id}: using RAM drive at {ramdisk_base}")
    else:
        work_dir = data_dir  # fallback: process on disk
        logger.info(f"Job {job_id}: RAM drive not available, using disk at {data_dir}")

    db_path = work_dir / "proc.db"
    project_dir = data_dir  # export always reads/writes disk

    # Migrate legacy data (pre-isolation layout) if this is job 1
    await _migrate_legacy_data(Path(str(config.server.data_dir)), username, job_id)

    export_info = None

    # Acquire per-user advisory lock via PostgreSQL (cross-process safe)
    lock_conn = await pool.acquire()
    try:
        # Use user_id hash as advisory lock key (stable across restarts)
        async with lock_conn.transaction():
            user_row = await lock_conn.fetchrow(
                "SELECT id FROM users WHERE username = $1", username
            )
            lock_key = user_row["id"] if user_row else hash(username) & 0x7FFFFFFF
        # pg_advisory_lock blocks until acquired (waits for previous job to finish)
        await lock_conn.execute("SELECT pg_advisory_lock($1)", lock_key)
        logger.info(f"Job {job_id} acquired DB advisory lock for user {username} (key={lock_key})")
    except Exception as e:
        logger.error(f"Job {job_id} failed to acquire lock: {e}")
        await pool.release(lock_conn)
        raise

    try:
        sqlite_db = None
        job_succeeded = False
        snap_uid = None
        snap_username = None
        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE processing_jobs SET status='running', started_at=NOW() WHERE id=$1 AND status != 'running'",
                    job_id,
                )

            # Deep copy config to avoid mutation race between concurrent jobs
            config = config.model_copy(deep=True)

            # Read user preferences and apply to config for this job
            async with pool.acquire() as conn:
                prefs = await conn.fetchrow(
                    """
                    SELECT burn_overlays, dark_mode_pngs, exif_enabled,
                           xmp_enabled, gps_window_seconds
                    FROM user_preferences up
                    JOIN users u ON up.user_id = u.id
                    WHERE u.username = $1
                    """,
                    username,
                )

            if prefs:
                config.exif.enabled = prefs["exif_enabled"]
                config.xmp.enabled = prefs["xmp_enabled"]
                config.pipeline.gps_window_seconds = prefs["gps_window_seconds"]
                config.lanes["memories"] = LaneConfig(
                    burn_overlays=prefs["burn_overlays"],
                )
                config.lanes["chats"] = LaneConfig(
                    dark_mode=prefs["dark_mode_pngs"],
                )
                logger.info(
                    f"Job {job_id} user prefs applied: exif={prefs['exif_enabled']}, "
                    f"xmp={prefs['xmp_enabled']}, "
                    f"burn={prefs['burn_overlays']}, dark={prefs['dark_mode_pngs']}, "
                    f"gps_window={prefs['gps_window_seconds']}s"
                )

            sqlite_db = open_database(str(db_path))
            progress_cb = _make_progress_cb(pool, job_id, loop)

            # Read phases_requested, lanes_requested, processing_mode, and user_id from job record
            async with pool.acquire() as conn:
                job_row = await conn.fetchrow(
                    "SELECT phases_requested, lanes_requested, processing_mode, user_id FROM processing_jobs WHERE id=$1",
                    job_id,
                )
            requested_phases = set(job_row["phases_requested"] or ["ingest", "match", "enrich", "export"])
            job_lanes = job_row["lanes_requested"] or ["memories", "chats", "stories"]

            # Read upload_type from the upload session linked to this job (if any)
            async with pool.acquire() as conn:
                session_opts_row = await conn.fetchrow(
                    "SELECT options_json FROM upload_sessions WHERE job_id=$1",
                    job_id,
                )
            if session_opts_row:
                raw_opts = session_opts_row["options_json"]
                # Handle double-encoded JSON (string wrapping a JSON string)
                parsed = json.loads(raw_opts) if isinstance(raw_opts, str) else raw_opts
                if isinstance(parsed, str):
                    parsed = json.loads(parsed)
                session_opts = parsed or {}
            else:
                session_opts = {}
            upload_type = session_opts.get("upload_type", "zip")

            # Mode-specific overrides (applied AFTER user_preferences load).
            processing_mode = job_row.get("processing_mode", "speed_run")
            if processing_mode == "quick_rescue":
                # Quick Rescue: memories only, fast, no sidecars.
                config.xmp.enabled = False
                config.exif.enabled = True
                config.lanes["memories"] = LaneConfig(burn_overlays=True)
                logger.info(f"Job {job_id}: Quick Rescue mode — XMP off, EXIF on, burn_overlays on")
            elif processing_mode == "speed_run":
                # Speed Run: full export, everything on — give me the works.
                config.xmp.enabled = True
                config.exif.enabled = True
                config.lanes.setdefault("memories", LaneConfig())
                config.lanes["memories"].burn_overlays = True
                logger.info(f"Job {job_id}: Speed Run mode — XMP on, EXIF on, burn_overlays on")

            # Calculate progress increments based on active phases
            active_phases = [p for p in ["ingest", "match", "enrich", "export"] if p in requested_phases]
            phase_pct = 100 // max(len(active_phases), 1)
            cumulative_pct = 0

            # Determine input directory: extract from staging if chunked upload
            if staging_dir:
                staging_path = Path(staging_dir)
                extracted_dir = work_dir / "extracted"
                extracted_dir.mkdir(parents=True, exist_ok=True)

                if upload_type == "folder":
                    # Folder upload: files already reconstructed by verify endpoint into
                    # staging_dir (which IS the extracted directory).  No ZIP extraction needed.
                    logger.info(f"Job {job_id}: folder upload — skipping ZIP extraction")
                    input_dir = staging_path
                else:
                    # ZIP upload: merge/extract .part files into extracted_dir as usual
                    await emit_event(pool, job_id, "progress", "Extracting uploaded files...", {"phase": "ingest", "progress_pct": 0})
                    await loop.run_in_executor(
                        None, ingest.merge_multipart_zips, staging_path, extracted_dir, progress_cb
                    )
                    input_dir = extracted_dir
            else:
                input_dir = work_dir

            # Snapchat exports put JSON metadata in a json/ subdirectory
            _discovered = ingest.discover_export(input_dir)
            if _discovered:
                json_dir = _discovered['json_dir']
                input_dir = _discovered['primary']
            else:
                # Fallback: try json/ subdir, then input_dir itself
                json_sub = input_dir / 'json'
                json_dir = json_sub if json_sub.is_dir() else input_dir

            # Collect stats from each phase for the results page
            all_stats = {"phase_durations": {}}

            # Phase 1: Ingest (always runs — data must be loaded)
            if "ingest" in requested_phases:
                pipeline_config = None  # v3 app doesn't use scan_siblings
                await emit_event(pool, job_id, "phase_start", "Ingesting export data...", {"phase": "ingest", "progress_pct": cumulative_pct, "verb": "READING YOUR MEMORIES"})
                import time as _time
                _t_ingest = _time.time()
                ingest_stats = await loop.run_in_executor(
                    None, ingest.phase1_ingest, sqlite_db, str(input_dir), str(json_dir), pipeline_config, progress_cb
                )
                all_stats["phase_durations"]["ingest"] = _time.time() - _t_ingest
                cumulative_pct += phase_pct
                await update_job(pool, job_id, current_phase="ingest", progress_pct=cumulative_pct)
                if isinstance(ingest_stats, dict):
                    all_stats["total_assets"] = ingest_stats.get("assets", 0)
                    all_stats["total_memories"] = ingest_stats.get("memories", 0)
                    all_stats["total_locations"] = ingest_stats.get("locations", 0)
                    all_stats["chat_count"] = ingest_stats.get("chat_messages", 0)
                    all_stats["story_count"] = ingest_stats.get("stories", 0)
                    all_stats["snap_count"] = ingest_stats.get("snap_messages", 0)
                    all_stats["friend_count"] = ingest_stats.get("friends", 0)
                    # Query conversation count + file breakdown from proc.db
                    try:
                        import sqlite3 as _sqlite3
                        _db = _sqlite3.connect(str(sqlite_db))
                        try:
                            conv_row = _db.execute("SELECT COUNT(DISTINCT conversation_id) FROM chat_messages").fetchone()
                            all_stats["conversation_count"] = conv_row[0] if conv_row else 0
                            # Photo / video / overlay breakdown
                            all_stats["photo_count"] = _db.execute(
                                "SELECT COUNT(*) FROM assets WHERE is_video = 0 AND asset_type NOT LIKE '%overlay%'"
                            ).fetchone()[0]
                            all_stats["video_count"] = _db.execute(
                                "SELECT COUNT(*) FROM assets WHERE is_video = 1"
                            ).fetchone()[0]
                            all_stats["overlay_count"] = _db.execute(
                                "SELECT COUNT(*) FROM assets WHERE asset_type LIKE '%overlay%' AND is_video = 0"
                            ).fetchone()[0]
                        finally:
                            _db.close()
                    except Exception:
                        all_stats.setdefault("conversation_count", 0)
                # Completeness check: compare metadata entries vs actual media files.
                # Only warn on genuinely large holes, not small discrepancies.
                _partial_warnings = []
                _memories = all_stats.get("total_memories", 0)
                _assets = all_stats.get("total_assets", 0)

                if _assets == 0 and _memories == 0:
                    _partial_warnings.append("No data found in upload")
                elif _assets == 0 and _memories > 0:
                    _partial_warnings.append(
                        f"Metadata found ({_memories:,} memories) but no media files — "
                        "media ZIP may be missing"
                    )
                elif _memories == 0 and _assets > 0:
                    _partial_warnings.append(
                        f"Media files found ({_assets:,}) but no metadata JSON — "
                        "metadata ZIP may be missing"
                    )
                else:
                    # Both exist — check if media files are significantly fewer
                    # than metadata entries (suggests missing media ZIPs).
                    # Only warn if >25% of expected media is missing.
                    if _memories > 0 and _assets < _memories * 0.75:
                        pct_found = round(_assets / _memories * 100)
                        _partial_warnings.append(
                            f"Only {pct_found}% of expected media found "
                            f"({_assets:,} of {_memories:,}) — some ZIPs may be missing"
                        )

                all_stats["partial_warnings"] = _partial_warnings

                # Emit with stats so SSE feeds the Intelligence Report live
                await emit_event(pool, job_id, "progress", "Ingest complete", {
                    "phase": "ingest", "progress_pct": cumulative_pct,
                    "total_files": all_stats.get("total_assets", 0),
                    "total_memories": all_stats.get("total_memories", 0),
                    "total_locations": all_stats.get("total_locations", 0),
                    "photo_count": all_stats.get("photo_count", 0),
                    "video_count": all_stats.get("video_count", 0),
                    "overlay_count": all_stats.get("overlay_count", 0),
                    "story_count": all_stats.get("story_count", 0),
                    "conversation_count": all_stats.get("conversation_count", 0),
                    "phase_elapsed": all_stats["phase_durations"].get("ingest", 0),
                    "partial_warnings": _partial_warnings,
                })

                # ── Extract Snapchat account fingerprint ────────────────────────
                try:
                    import sqlite3 as _sqlite3
                    from urllib.parse import urlparse, parse_qs
                    _fp_db = _sqlite3.connect(str(db_path))
                    try:
                        # Trail 1: UID from memories download links
                        _links = _fp_db.execute(
                            "SELECT download_link FROM memories WHERE download_link IS NOT NULL AND download_link != '' LIMIT 10"
                        ).fetchall()
                        for _link_row in _links:
                            _params = parse_qs(urlparse(_link_row[0]).query)
                            _uid_list = _params.get("uid", [])
                            if _uid_list and _uid_list[0]:
                                snap_uid = _uid_list[0]
                                break

                        if not snap_uid:
                            # Distinguish "no memories" from "memories but no uid in links"
                            _mem_count = _fp_db.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
                            if _mem_count > 0:
                                logger.info("Job %d: no uid in download links (%d memories examined)", job_id, _mem_count)
                            else:
                                logger.info("Job %d: no memories for fingerprint (media-only export)", job_id)

                        # Trail 2: Username from chat sender
                        _sender = _fp_db.execute(
                            "SELECT DISTINCT from_user FROM chat_messages WHERE is_sender = 1 LIMIT 1"
                        ).fetchone()
                        if not _sender:
                            _sender = _fp_db.execute(
                                "SELECT DISTINCT from_user FROM snap_messages WHERE is_sender = 1 LIMIT 1"
                            ).fetchone()
                        if _sender:
                            snap_username = _sender[0]
                        else:
                            logger.info("Job %d: no sender data for username fingerprint", job_id)
                    finally:
                        _fp_db.close()
                except Exception as _fp_err:
                    logger.warning("Job %d: fingerprint extraction failed: %s", job_id, _fp_err, exc_info=True)

                # Store fingerprint status in stats
                all_stats["fingerprint_status"] = "extracted" if (snap_uid or snap_username) else "no_data"

                # Store fingerprint on job record
                if snap_uid or snap_username:
                    try:
                        async with pool.acquire() as conn:
                            await conn.execute(
                                """UPDATE processing_jobs
                                   SET snap_account_uid = $1, snap_username = $2
                                   WHERE id = $3""",
                                snap_uid, snap_username, job_id,
                            )
                        logger.info(f"Job {job_id}: fingerprint extracted — uid={snap_uid}, username={snap_username}")
                    except Exception as _fp_store_err:
                        # Column might not exist yet if schema migration hasn't run — non-fatal
                        logger.warning(f"Job {job_id}: failed to store fingerprint: {_fp_store_err}")

                all_stats["snap_account_uid"] = snap_uid
                all_stats["snap_username"] = snap_username

            # Phase 2: Match
            if "match" in requested_phases:
                await emit_event(pool, job_id, "phase_start", "Running match cascade...", {"phase": "match", "progress_pct": cumulative_pct, "verb": "MATCHING YOUR MOMENTS"})
                match_stats = await loop.run_in_executor(
                    None, match.phase2_match, sqlite_db, progress_cb
                )
                cumulative_pct += phase_pct
                await update_job(pool, job_id, current_phase="match", progress_pct=cumulative_pct)
                if isinstance(match_stats, dict):
                    all_stats["total_matches"] = match_stats.get("total_matched", 0)
                    all_stats["matched_count"] = match_stats.get("total_matched", 0)
                    all_stats["match_rate"] = match_stats.get("match_rate", 0)
                    all_stats["true_orphans"] = match_stats.get("true_orphans", 0)
                    all_stats["phase_durations"]["match"] = match_stats.get("elapsed", 0)
                await emit_event(pool, job_id, "progress", "Match complete", {
                    "phase": "match", "progress_pct": cumulative_pct,
                    "matched_count": all_stats.get("matched_count", 0),
                    "match_rate": all_stats.get("match_rate", 0),
                    "true_orphans": all_stats.get("true_orphans", 0),
                    "total_files": all_stats.get("total_assets", 0),
                    "phase_elapsed": all_stats["phase_durations"].get("match", 0),
                })

            # --- Living Canvas: Match-only pause ---
            # If match was requested but export is not (and enrich is not), pause at 'matched'.
            # This lets the user review match results before continuing.
            # Covers: phases == {"ingest", "match"} or {"match"}
            if "match" in requested_phases and "enrich" not in requested_phases and "export" not in requested_phases:
                # Move RAM data to disk before pausing so it survives the pause
                if use_ramdisk and ramdisk_base.exists():
                    logger.info(f"Job {job_id}: moving processed data from RAM to disk (match pause)")
                    ram_db = ramdisk_base / "proc.db"
                    disk_db = data_dir / "proc.db"
                    if ram_db.exists():
                        data_dir.mkdir(parents=True, exist_ok=True)
                        await asyncio.to_thread(shutil.move, str(ram_db), str(disk_db))
                    ram_extracted = ramdisk_base / "extracted"
                    disk_extracted = data_dir / "extracted"
                    if ram_extracted.exists():
                        if disk_extracted.exists():
                            await asyncio.to_thread(shutil.rmtree, str(disk_extracted))
                        await asyncio.to_thread(shutil.move, str(ram_extracted), str(disk_extracted))
                    for item in ramdisk_base.iterdir():
                        if item.exists():
                            target = data_dir / item.name
                            await asyncio.to_thread(shutil.move, str(item), str(target))
                    await asyncio.to_thread(shutil.rmtree, str(ramdisk_base), True)
                    # Rewrite ramdisk paths in proc.db to disk paths
                    rewritten = await asyncio.to_thread(
                        _rewrite_procdb_paths, data_dir / "proc.db",
                        str(ramdisk_base), str(data_dir),
                    )
                    logger.info(f"Job {job_id}: RAM -> disk move complete (match pause), {rewritten} paths rewritten")
                await update_job(pool, job_id, status="matched", progress_pct=100, stats_json=all_stats)
                await emit_event(pool, job_id, "matched", "Matching complete — ready to review", {"progress_pct": 100})
                logger.info(f"Job {job_id} match complete (status: matched)")
                return

            # Phase 3: Enrich
            if "enrich" in requested_phases:
                await emit_event(pool, job_id, "phase_start", "Enriching metadata...", {"phase": "enrich", "progress_pct": cumulative_pct, "verb": "REBUILDING YOUR STORY"})
                enrich_stats = await loop.run_in_executor(
                    None, enrich.phase3_enrich, sqlite_db, work_dir, config, progress_cb
                )
                cumulative_pct += phase_pct
                await update_job(pool, job_id, current_phase="enrich", progress_pct=cumulative_pct)
                if isinstance(enrich_stats, dict):
                    gps_total = enrich_stats.get("gps_metadata", 0) + enrich_stats.get("gps_location_history", 0)
                    total = enrich_stats.get("total", 1)
                    all_stats["gps_coverage"] = round((gps_total / total) * 100, 1) if total > 0 else 0
                    all_stats["gps_count"] = gps_total
                    all_stats["phase_durations"]["enrich"] = enrich_stats.get("elapsed", 0)
                # Query date range from proc.db for Intelligence Report
                try:
                    import sqlite3 as _sqlite3
                    _db = _sqlite3.connect(str(sqlite_db))
                    try:
                        row = _db.execute(
                            "SELECT MIN(matched_date) AS min_date, MAX(matched_date) AS max_date "
                            "FROM matches WHERE is_best = 1 AND matched_date IS NOT NULL"
                        ).fetchone()
                        all_stats["min_date"] = row[0] if row else None
                        all_stats["max_date"] = row[1] if row else None
                    finally:
                        _db.close()
                except Exception:
                    all_stats.setdefault("min_date", None)
                    all_stats.setdefault("max_date", None)
                await emit_event(pool, job_id, "progress", "Enrich complete", {
                    "phase": "enrich", "progress_pct": cumulative_pct,
                    "gps_count": all_stats.get("gps_count", 0),
                    "gps_coverage": all_stats.get("gps_coverage", 0),
                    "true_orphans": all_stats.get("true_orphans", 0),
                    "total_files": all_stats.get("total_assets", 0),
                    "matched_count": all_stats.get("matched_count", 0),
                    "min_date": all_stats.get("min_date"),
                    "max_date": all_stats.get("max_date"),
                    "phase_elapsed": all_stats["phase_durations"].get("enrich", 0),
                })

            # Phase A: Move proc.db + misc to SSD, but KEEP extracted/ on ramdisk.
            # The export worker reads assets from ramdisk at ~10GB/s instead of SSD.
            # Phase B (after export) will clean up extracted/ from ramdisk.
            _ramdisk_had_extracted = False
            if use_ramdisk and ramdisk_base.exists():
                logger.info(f"Job {job_id}: Phase A — moving proc.db + misc to SSD (keeping extracted/ on ramdisk)")

                # Move proc.db to SSD (export_worker looks for it at job_dir/proc.db)
                ram_db = ramdisk_base / "proc.db"
                disk_db = data_dir / "proc.db"
                if ram_db.exists():
                    data_dir.mkdir(parents=True, exist_ok=True)
                    await asyncio.to_thread(shutil.move, str(ram_db), str(disk_db))

                # Move misc files (.snatched/, etc.) but NOT extracted/
                ram_extracted = ramdisk_base / "extracted"
                _ramdisk_had_extracted = ram_extracted.exists()
                for item in ramdisk_base.iterdir():
                    if item.name == "extracted":
                        continue  # keep on ramdisk for fast export reads
                    if item.exists():
                        target = data_dir / item.name
                        await asyncio.to_thread(shutil.move, str(item), str(target))

                # DO NOT rewrite assets.path — paths still point to ramdisk (correct, files are there)
                logger.info(f"Job {job_id}: Phase A complete — proc.db on SSD, extracted/ still on ramdisk")

            # --- Living Canvas: Enrich-only pause ---
            # If enrich was requested but export is not, pause at 'enriched'.
            # Phase A only moved proc.db+misc — move extracted/ to SSD too since no export coming.
            if "enrich" in requested_phases and "export" not in requested_phases:
                if use_ramdisk and _ramdisk_had_extracted:
                    ram_extracted = ramdisk_base / "extracted"
                    if ram_extracted.exists():
                        disk_extracted = data_dir / "extracted"
                        if disk_extracted.exists():
                            await asyncio.to_thread(shutil.rmtree, str(disk_extracted))
                        await asyncio.to_thread(shutil.move, str(ram_extracted), str(disk_extracted))
                    rewritten = await asyncio.to_thread(
                        _rewrite_procdb_paths, data_dir / "proc.db",
                        str(ramdisk_base), str(data_dir),
                    )
                    await asyncio.to_thread(shutil.rmtree, str(ramdisk_base), True)
                    logger.info(f"Job {job_id}: enriched pause — moved extracted/ to SSD, {rewritten} paths rewritten")
                await update_job(pool, job_id, status="enriched", progress_pct=100, stats_json=all_stats)
                await emit_event(pool, job_id, "enriched", "Enrichment complete — ready to review", {"progress_pct": 100})
                logger.info(f"Job {job_id} enrich complete (status: enriched)")
                return

            # Phase 4: Export — handled post-completion via export_worker.
            # All modes now create an export record and launch run_export()
            # instead of calling phase4_export() synchronously inline.

            # For ingest-only (scanned) path, enrich never ran so the RAM-to-disk move
            # block above was skipped. Move RAM data to disk now so it survives the pause.
            if "enrich" not in requested_phases and use_ramdisk and ramdisk_base.exists():
                logger.info(f"Job {job_id}: moving processed data from RAM to disk (pre-scanned)")
                ram_db = ramdisk_base / "proc.db"
                disk_db = data_dir / "proc.db"
                if ram_db.exists():
                    data_dir.mkdir(parents=True, exist_ok=True)
                    await asyncio.to_thread(shutil.move, str(ram_db), str(disk_db))
                ram_extracted = ramdisk_base / "extracted"
                disk_extracted = data_dir / "extracted"
                if ram_extracted.exists():
                    if disk_extracted.exists():
                        await asyncio.to_thread(shutil.rmtree, str(disk_extracted))
                    await asyncio.to_thread(shutil.move, str(ram_extracted), str(disk_extracted))
                for item in ramdisk_base.iterdir():
                    if item.exists():
                        target = data_dir / item.name
                        await asyncio.to_thread(shutil.move, str(item), str(target))
                await asyncio.to_thread(shutil.rmtree, str(ramdisk_base), True)
                # Rewrite ramdisk paths in proc.db to disk paths
                rewritten = await asyncio.to_thread(
                    _rewrite_procdb_paths, data_dir / "proc.db",
                    str(ramdisk_base), str(data_dir),
                )
                logger.info(f"Job {job_id}: RAM -> disk move complete (pre-scanned), {rewritten} paths rewritten")

            # --- STORY-2: Ingest-only scan status ---
            # If only ingest was requested, set status to 'scanned' instead of 'completed'
            # This allows user to configure lanes/options before running remaining phases
            # NOTE: emit_event BEFORE update_job so SSE stream delivers the event
            # before the status change closes the stream.
            if requested_phases == {"ingest"}:
                await emit_event(pool, job_id, "scanned", "Scan complete — ready to configure", {"progress_pct": 100})
                await update_job(pool, job_id, status="scanned", progress_pct=100, stats_json=all_stats)
                # Set 72h TTL for unconfigured scans — cron will expire them
                async with pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE processing_jobs SET retention_expires_at = NOW() + INTERVAL '72 hours' WHERE id = $1",
                        job_id,
                    )
                logger.info(f"Job {job_id} ingest scan complete (status: scanned, TTL: 72h)")
            else:
                await emit_event(pool, job_id, "complete", "Processing complete", {"progress_pct": 100})
                await update_job(pool, job_id, status="completed", progress_pct=100, stats_json=all_stats)
                logger.info(f"Job {job_id} completed successfully")

                # Vault merge is now user-gated (manual via vault management UI)
                logger.info(f"Job {job_id} completed — vault merge available (user-gated)")

                # Auto-export: create export record — dispatch happens OUTSIDE user_lock.
                processing_mode = job_row.get("processing_mode", "speed_run")
                try:
                    from snatched.db import create_export

                    user_id = job_row["user_id"]

                    if processing_mode == "quick_rescue":
                        _export_type = "quick_rescue"
                        _lanes = ["memories"]
                        _chat_text = False
                        _chat_png = False
                    else:
                        _export_type = "full"
                        _lanes = list(job_lanes) if job_lanes else ["memories", "chats", "stories"]
                        _chat_text = True
                        _chat_png = True

                    _mem_lane = config.lanes.get("memories", LaneConfig())
                    _chat_lane = config.lanes.get("chats", LaneConfig())
                    export_id = await create_export(
                        pool, job_id, user_id,
                        export_type=_export_type,
                        lanes=_lanes,
                        exif_enabled=config.exif.enabled,
                        xmp_enabled=config.xmp.enabled,
                        burn_overlays=_mem_lane.burn_overlays,
                        chat_text=_chat_text,
                        chat_png=_chat_png,
                        dark_mode_pngs=_chat_lane.dark_mode,
                        folder_style=_mem_lane.folder_pattern,
                        gps_precision=_mem_lane.gps_precision,
                        hide_sent_to=_mem_lane.hide_sent_to,
                        chat_timestamps=_chat_lane.chat_timestamps,
                        chat_cover_pages=_chat_lane.chat_cover_pages,
                    )
                    logger.info(f"Job {job_id}: auto-created export {export_id} ({_export_type})")

                    # Save for deferred dispatch outside the user lock
                    export_info = {
                        "export_id": export_id,
                        "config": config,
                    }
                except Exception as e:
                    logger.error(f"Job {job_id}: Failed to auto-create export: {e}")

            job_succeeded = True

        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}", exc_info=True)
            try:
                await update_job(pool, job_id, status="failed", error_message=str(e))
            except Exception as update_err:
                logger.error(f"Job {job_id}: failed to mark as failed: {update_err}")
            try:
                await emit_event(pool, job_id, "error", str(e))
            except Exception as emit_err:
                logger.error(f"Job {job_id}: failed to emit error event: {emit_err}")

        finally:
            if sqlite_db:
                sqlite_db.close()
            # Clean up ramdisk on FAILURE only — success path defers to Phase B
            if not job_succeeded and use_ramdisk and ramdisk_base.exists():
                try:
                    await asyncio.to_thread(shutil.rmtree, str(ramdisk_base), True)
                    logger.info(f"Job {job_id}: cleaned up RAM drive after failure")
                except Exception:
                    pass
            # Clean up staging directory only on success — on failure, keep files
            # so the user doesn't have to re-upload. Expired session cleanup
            # handles stale staging dirs eventually.
            if staging_dir and job_succeeded:
                try:
                    staging_path = Path(staging_dir)
                    if staging_path.exists():
                        shutil.rmtree(staging_path)
                        logger.info(f"Cleaned up staging directory: {staging_dir}")
                except Exception as cleanup_err:
                    logger.warning(f"Failed to clean up staging dir {staging_dir}: {cleanup_err}")
            _job_tasks.pop(job_id, None)
    finally:
        # Release the per-user advisory lock so other jobs for this user can proceed
        try:
            await lock_conn.execute("SELECT pg_advisory_unlock($1)", lock_key)
            logger.info(f"Job {job_id}: released DB advisory lock (key={lock_key})")
        except Exception:
            pass
        await pool.release(lock_conn)

    # ── Outside user lock: run export + Phase B ──────────────────────────────
    # Export reads from ramdisk (fast) while lock is released for other jobs.
    if export_info:
        from snatched.processing.export_worker import run_export
        _eid = export_info["export_id"]
        _ecfg = export_info["config"]

        try:
            await emit_event(pool, job_id, "progress",
                            "Building your download...",
                            {"export_id": _eid})
            await run_export(pool, _eid, job_id, username, _ecfg)
        except Exception as e:
            logger.error(f"Job {job_id}: export {_eid} failed: {e}", exc_info=True)

        # Phase B: clean up extracted/ from ramdisk (or SSD)
        try:
            async with pool.acquire() as conn:
                pending = await conn.fetchval(
                    "SELECT COUNT(*) FROM exports WHERE job_id=$1 AND status NOT IN ('completed','failed','cancelled')",
                    job_id,
                )

            if pending == 0:
                if use_ramdisk and _ramdisk_had_extracted:
                    # Delete extracted/ directly from ramdisk — saves 30GB SSD write!
                    ram_extracted = ramdisk_base / "extracted"
                    if ram_extracted.exists():
                        await asyncio.to_thread(shutil.rmtree, str(ram_extracted), True)
                        logger.info(f"Job {job_id}: Phase B — deleted extracted/ from ramdisk (skipped SSD)")
                else:
                    # Non-ramdisk or extracted/ already on SSD: clean from SSD
                    disk_extracted = data_dir / "extracted"
                    if disk_extracted.exists():
                        await asyncio.to_thread(shutil.rmtree, str(disk_extracted), True)
                        logger.info(f"Job {job_id}: Phase B — deleted extracted/ from SSD")
            else:
                # Other exports pending — move extracted/ to SSD so they can find it
                if use_ramdisk and _ramdisk_had_extracted:
                    ram_extracted = ramdisk_base / "extracted"
                    if ram_extracted.exists():
                        disk_extracted = data_dir / "extracted"
                        if disk_extracted.exists():
                            await asyncio.to_thread(shutil.rmtree, str(disk_extracted))
                        await asyncio.to_thread(shutil.move, str(ram_extracted), str(disk_extracted))
                        rewritten = await asyncio.to_thread(
                            _rewrite_procdb_paths, data_dir / "proc.db",
                            str(ramdisk_base), str(data_dir),
                        )
                        logger.info(f"Job {job_id}: Phase B — moved extracted/ to SSD ({rewritten} paths rewritten, {pending} exports pending)")
        except Exception as phase_b_err:
            logger.warning(f"Job {job_id}: Phase B cleanup error (non-fatal): {phase_b_err}")

    # Final ramdisk cleanup — always clean up whatever remains
    if use_ramdisk and ramdisk_base.exists():
        try:
            await asyncio.to_thread(shutil.rmtree, str(ramdisk_base), True)
            logger.info(f"Job {job_id}: final ramdisk cleanup")
        except Exception:
            pass


def _make_progress_cb(pool: asyncpg.Pool, job_id: int, loop: asyncio.AbstractEventLoop):
    """Create a synchronous progress callback that emits async events.

    The pipeline phases are synchronous (SQLite) and run in a thread executor,
    so there is no running event loop in the thread. The main event loop is
    captured before entering the executor and passed in here, then used via
    asyncio.run_coroutine_threadsafe() to safely schedule the broadcast.

    Accepts an optional data dict for structured progress (verb, counters, GPS, etc.).
    """
    def cb(message: str, data: dict | None = None) -> None:
        asyncio.run_coroutine_threadsafe(
            emit_event(pool, job_id, "progress", message, data_json=data), loop
        )

    return cb


async def is_job_complete(pool: asyncpg.Pool, job_id: int) -> bool:
    """Return True if job has reached a terminal or pause state.

    'scanned', 'matched', 'enriched' are pause points — the SSE stream
    should close so the client can trigger the next phase and reconnect.
    True terminal states are 'completed', 'failed', 'cancelled'.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status, processing_mode FROM processing_jobs WHERE id=$1",
            job_id,
        )
    if not row:
        return True
    status = row["status"]
    mode = row["processing_mode"]

    # True terminal states — always close SSE
    if status in ("completed", "failed", "cancelled"):
        return True

    # Pause states — close SSE for power_user (needs manual continue),
    # but keep streaming for quick_rescue (auto-continues via JS fetch)
    if status in ("scanned", "matched", "enriched"):
        return mode != "quick_rescue"

    return False


async def cancel_job(pool: asyncpg.Pool, job_id: int) -> bool:
    """Request job cancellation.

    Marks job as 'cancelled' in the database. Does not forcefully
    terminate the running asyncio task (graceful shutdown via polling).

    Returns:
        True if job was cancelled, False if already in terminal state.
    """
    async with pool.acquire() as conn:
        current_status = await conn.fetchval(
            "SELECT status FROM processing_jobs WHERE id=$1",
            job_id,
        )

    if current_status in ("completed", "failed", "cancelled"):
        return False

    await update_job(pool, job_id, status="cancelled")
    task = _job_tasks.pop(job_id, None)
    if task and not task.done():
        task.cancel()
    logger.info(f"Job {job_id} cancellation requested")
    return True


async def job_stream(
    pool: asyncpg.Pool,
    job_id: int,
) -> AsyncIterator[str]:
    """Server-Sent Events generator for job progress.

    Polls job_events table every 0.5s. Yields SSE-formatted strings.
    Sends keepalive comments every 15 seconds to prevent proxy timeouts.
    Terminates when job reaches terminal state.
    """
    last_id = 0
    heartbeat_interval = 15  # seconds between keepalive pings
    polls_per_heartbeat = int(heartbeat_interval / 0.5)  # 30 polls
    idle_polls = 0

    while True:
        events = await get_events_after(pool, job_id, last_id)

        if events:
            idle_polls = 0
            for event in events:
                data = {"message": event.get("message", "")}
                raw = event.get("data_json")
                if raw is not None:
                    # Guard against legacy double-encoded rows (stored as a JSON string
                    # rather than a JSON object) which arrive here as a str after the
                    # asyncpg decoder runs json.loads once.
                    if isinstance(raw, str):
                        try:
                            raw = json.loads(raw)
                        except (json.JSONDecodeError, TypeError):
                            raw = None
                    if isinstance(raw, dict):
                        data.update(raw)
                yield f"event: {event['event_type']}\ndata: {json.dumps(data)}\n\n"
                last_id = event["id"]
        else:
            idle_polls += 1
            if idle_polls >= polls_per_heartbeat:
                # SSE comment — keeps proxy connections alive, ignored by EventSource
                yield ": heartbeat\n\n"
                idle_polls = 0

        if await is_job_complete(pool, job_id):
            # scanned / matched / enriched / error events are already emitted by
            # run_job via emit_event() and picked up above via get_events_after.
            # Only emit a synthetic 'complete' event for the normal completed
            # state, which has no dedicated event emitted by run_job.
            async with pool.acquire() as conn:
                final_status = await conn.fetchval(
                    "SELECT status FROM processing_jobs WHERE id=$1", job_id
                )
            if final_status == "cancelled":
                yield f"event: cancelled\ndata: {json.dumps({'message': 'Job cancelled', 'progress_pct': 0})}\n\n"
            elif final_status == "failed":
                yield f"event: error\ndata: {json.dumps({'message': 'Job failed'})}\n\n"
            elif final_status == "completed":
                yield f"event: complete\ndata: {json.dumps({'message': 'done', 'progress_pct': 100})}\n\n"
            # scanned / matched / enriched: already in event stream, no extra emit needed
            break

        await asyncio.sleep(0.5)
