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
) -> int:
    """Insert a new processing job record in PostgreSQL.

    Args:
        processing_mode: 'speed_run' (fast, sane defaults) or 'power_user' (all knobs exposed)

    Returns:
        New job ID (integer).
    """
    if processing_mode not in ("speed_run", "power_user"):
        processing_mode = "speed_run"

    async with pool.acquire() as conn:
        job_id = await conn.fetchval(
            """
            INSERT INTO processing_jobs
                (user_id, upload_filename, upload_size_bytes,
                 phases_requested, lanes_requested, processing_mode, status)
            VALUES ($1, $2, $3, $4, $5, $6, 'pending')
            RETURNING id
            """,
            user_id, upload_filename, upload_size_bytes,
            phases_requested, lanes_requested, processing_mode,
        )
    logger.info(f"Created job {job_id} for user_id {user_id}")
    return job_id


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

    from snatched.processing import enrich, export, ingest, match
    from snatched.processing.sqlite import open_database
    from snatched.config import LaneConfig, ExifConfig

    data_dir = Path(str(config.server.data_dir)) / username
    db_path = data_dir / "proc.db"
    project_dir = data_dir
    loop = asyncio.get_running_loop()

    sqlite_db = None
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE processing_jobs SET status='running', started_at=NOW() WHERE id=$1",
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

        # Read phases_requested and lanes_requested from job record
        async with pool.acquire() as conn:
            job_row = await conn.fetchrow(
                "SELECT phases_requested, lanes_requested FROM processing_jobs WHERE id=$1",
                job_id,
            )
        requested_phases = set(job_row["phases_requested"] or ["ingest", "match", "enrich", "export"])
        job_lanes = job_row["lanes_requested"] or ["memories", "chats", "stories"]

        # Calculate progress increments based on active phases
        active_phases = [p for p in ["ingest", "match", "enrich", "export"] if p in requested_phases]
        phase_pct = 100 // max(len(active_phases), 1)
        cumulative_pct = 0

        # Determine input directory: extract from staging if chunked upload
        if staging_dir:
            staging_path = Path(staging_dir)
            work_dir = data_dir / "extracted"
            work_dir.mkdir(parents=True, exist_ok=True)
            await emit_event(pool, job_id, "progress", "Extracting uploaded files...", {"phase": "ingest", "progress_pct": 0})
            await loop.run_in_executor(
                None, ingest.merge_multipart_zips, staging_path, work_dir, progress_cb
            )
            input_dir = work_dir
        else:
            input_dir = project_dir

        # json_dir = same as input_dir (Snapchat exports bundle JSON + media together)
        json_dir = input_dir

        # Collect stats from each phase for the results page
        all_stats = {"phase_durations": {}}

        # Phase 1: Ingest (always runs — data must be loaded)
        if "ingest" in requested_phases:
            pipeline_config = None  # v3 app doesn't use scan_siblings
            await emit_event(pool, job_id, "phase_start", "Ingesting export data...", {"phase": "ingest", "progress_pct": cumulative_pct})
            ingest_stats = await loop.run_in_executor(
                None, ingest.phase1_ingest, sqlite_db, str(input_dir), str(json_dir), pipeline_config, progress_cb
            )
            cumulative_pct += phase_pct
            await update_job(pool, job_id, current_phase="ingest", progress_pct=cumulative_pct)
            await emit_event(pool, job_id, "progress", "Ingest complete", {"phase": "ingest", "progress_pct": cumulative_pct})
            if isinstance(ingest_stats, dict):
                all_stats["total_assets"] = ingest_stats.get("assets", 0)
                all_stats["total_memories"] = ingest_stats.get("memories", 0)
                all_stats["total_locations"] = ingest_stats.get("locations", 0)

        # Phase 2: Match
        if "match" in requested_phases:
            await emit_event(pool, job_id, "phase_start", "Running match cascade...", {"phase": "match", "progress_pct": cumulative_pct})
            match_stats = await loop.run_in_executor(
                None, match.phase2_match, sqlite_db, progress_cb
            )
            cumulative_pct += phase_pct
            await update_job(pool, job_id, current_phase="match", progress_pct=cumulative_pct)
            await emit_event(pool, job_id, "progress", "Match complete", {"phase": "match", "progress_pct": cumulative_pct})
            if isinstance(match_stats, dict):
                all_stats["total_matches"] = match_stats.get("total_matched", 0)
                all_stats["match_rate"] = match_stats.get("match_rate", 0)
                all_stats["true_orphans"] = match_stats.get("true_orphans", 0)
                all_stats["phase_durations"]["match"] = match_stats.get("elapsed", 0)

        # --- Living Canvas: Match-only pause ---
        # If match was requested but export is not (and enrich is not), pause at 'matched'.
        # This lets the user review match results before continuing.
        # Covers: phases == {"ingest", "match"} or {"match"}
        if "match" in requested_phases and "enrich" not in requested_phases and "export" not in requested_phases:
            await update_job(pool, job_id, status="matched", progress_pct=100, stats_json=all_stats)
            await emit_event(pool, job_id, "matched", "Matching complete — ready to review", {"progress_pct": 100})
            logger.info(f"Job {job_id} match complete (status: matched)")
            return

        # Phase 3: Enrich
        if "enrich" in requested_phases:
            await emit_event(pool, job_id, "phase_start", "Enriching metadata...", {"phase": "enrich", "progress_pct": cumulative_pct})
            enrich_stats = await loop.run_in_executor(
                None, enrich.phase3_enrich, sqlite_db, project_dir, config, progress_cb
            )
            cumulative_pct += phase_pct
            await update_job(pool, job_id, current_phase="enrich", progress_pct=cumulative_pct)
            await emit_event(pool, job_id, "progress", "Enrich complete", {"phase": "enrich", "progress_pct": cumulative_pct})
            if isinstance(enrich_stats, dict):
                gps_total = enrich_stats.get("gps_metadata", 0) + enrich_stats.get("gps_location_history", 0)
                total = enrich_stats.get("total", 1)
                all_stats["gps_coverage"] = round((gps_total / total) * 100, 1) if total > 0 else 0
                all_stats["phase_durations"]["enrich"] = enrich_stats.get("elapsed", 0)

        # --- Living Canvas: Enrich-only pause ---
        # If enrich was requested but export is not, pause at 'enriched'.
        # This lets the user inspect enriched metadata before committing the export.
        if "enrich" in requested_phases and "export" not in requested_phases:
            await update_job(pool, job_id, status="enriched", progress_pct=100, stats_json=all_stats)
            await emit_event(pool, job_id, "enriched", "Enrichment complete — ready to review", {"progress_pct": 100})
            logger.info(f"Job {job_id} enrich complete (status: enriched)")
            return

        # Phase 4: Export
        if "export" in requested_phases:
            await emit_event(pool, job_id, "phase_start", "Exporting files...", {"phase": "export", "progress_pct": cumulative_pct})
            export_stats = await loop.run_in_executor(
                None, export.phase4_export, sqlite_db, project_dir, config, job_lanes, progress_cb
            )
            if isinstance(export_stats, dict):
                all_stats["files_exported"] = export_stats.get("copied", 0)
                all_stats["exif_written"] = export_stats.get("exif_written", 0)
                all_stats["phase_durations"]["export"] = export_stats.get("elapsed", 0)

        # --- STORY-2: Ingest-only scan status ---
        # If only ingest was requested, set status to 'scanned' instead of 'completed'
        # This allows user to configure lanes/options before running remaining phases
        if requested_phases == {"ingest"}:
            await update_job(pool, job_id, status="scanned", progress_pct=100, stats_json=all_stats)
            await emit_event(pool, job_id, "scanned", "Scan complete — ready to configure", {"progress_pct": 100})
            logger.info(f"Job {job_id} ingest scan complete (status: scanned)")
        else:
            await update_job(pool, job_id, status="completed", progress_pct=100, stats_json=all_stats)
            logger.info(f"Job {job_id} completed successfully")

    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}", exc_info=True)
        await update_job(pool, job_id, status="failed", error_message=str(e))
        await emit_event(pool, job_id, "error", str(e))

    finally:
        if sqlite_db:
            sqlite_db.close()
        # Clean up staging directory after pipeline completes (success or failure)
        if staging_dir:
            try:
                staging_path = Path(staging_dir)
                if staging_path.exists():
                    shutil.rmtree(staging_path)
                    logger.info(f"Cleaned up staging directory: {staging_dir}")
            except Exception as cleanup_err:
                logger.warning(f"Failed to clean up staging dir {staging_dir}: {cleanup_err}")
        _job_tasks.pop(job_id, None)


def _make_progress_cb(pool: asyncpg.Pool, job_id: int, loop: asyncio.AbstractEventLoop):
    """Create a synchronous progress callback that emits async events.

    The pipeline phases are synchronous (SQLite) and run in a thread executor,
    so there is no running event loop in the thread. The main event loop is
    captured before entering the executor and passed in here, then used via
    asyncio.run_coroutine_threadsafe() to safely schedule the broadcast.
    """
    def cb(message: str) -> None:
        asyncio.run_coroutine_threadsafe(
            emit_event(pool, job_id, "progress", message), loop
        )

    return cb


async def is_job_complete(pool: asyncpg.Pool, job_id: int) -> bool:
    """Return True if job has reached a terminal state."""
    async with pool.acquire() as conn:
        status = await conn.fetchval(
            "SELECT status FROM processing_jobs WHERE id=$1",
            job_id,
        )
    return status in ("completed", "failed", "cancelled", "scanned", "matched", "enriched")


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
    Terminates when job reaches terminal state.
    """
    last_id = 0

    while True:
        events = await get_events_after(pool, job_id, last_id)

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
