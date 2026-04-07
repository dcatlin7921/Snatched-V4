"""ARQ worker settings for Snatched job processing.

This module defines the ARQ worker that pulls jobs from Redis and executes
the processing pipeline. It runs as a separate process alongside uvicorn.

Usage:
    arq snatched.worker.WorkerSettings
"""

import asyncio
import logging
import os

from arq.connections import RedisSettings

logger = logging.getLogger("snatched.worker")

# Redis connection — reuses immich-redis on DB index 1
REDIS_HOST = os.getenv("SNATCHED_REDIS_HOST", "immich-redis")
REDIS_PORT = int(os.getenv("SNATCHED_REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("SNATCHED_REDIS_DB", "1"))

# Max concurrent jobs the worker will run
MAX_CONCURRENT_JOBS = int(os.getenv("SNATCHED_MAX_WORKER_JOBS", "4"))

# Job timeout: 4 hours max (covers large exports with video overlays)
JOB_TIMEOUT = int(os.getenv("SNATCHED_JOB_TIMEOUT", "14400"))


async def startup(ctx: dict) -> None:
    """Called once when the ARQ worker starts. Sets up shared resources."""
    from snatched.config import load_config
    from snatched.db import get_pool

    config = load_config()

    # Create asyncpg pool using the same connection logic as the web app
    pool = await get_pool(
        config.database.postgres_url,
        min_size=2,
        max_size=10,
    )
    ctx["pool"] = pool
    ctx["config"] = config
    logger.info(
        "ARQ worker started: max_jobs=%d, redis=%s:%d/db%d",
        MAX_CONCURRENT_JOBS, REDIS_HOST, REDIS_PORT, REDIS_DB,
    )


async def shutdown(ctx: dict) -> None:
    """Called when the ARQ worker shuts down. Closes shared resources."""
    pool = ctx.get("pool")
    if pool:
        await pool.close()
    logger.info("ARQ worker shut down.")


async def process_job(ctx: dict, job_id: int, username: str, staging_dir: str | None = None) -> dict:
    """ARQ job function: run the 4-phase processing pipeline.

    This replaces the old asyncio.create_task(run_job(...)) pattern.
    Called by the ARQ worker when a job is dequeued from Redis.
    """
    pool = ctx["pool"]
    config = ctx["config"]

    from snatched.jobs import run_job
    from snatched.db import update_job, emit_event

    logger.info("Worker picked up job %d for user %s", job_id, username)

    # Update status from 'queued' to 'running'
    await update_job(pool, job_id, status="running")
    await emit_event(pool, job_id, "progress", "Processing started")

    try:
        await run_job(pool, job_id, username, config, staging_dir=staging_dir)
        return {"status": "completed", "job_id": job_id}
    except asyncio.CancelledError:
        logger.warning("Job %d was cancelled", job_id)
        await update_job(pool, job_id, status="cancelled")
        await emit_event(pool, job_id, "error", "Job was cancelled")
        return {"status": "cancelled", "job_id": job_id}
    except Exception as e:
        logger.error("Job %d failed: %s", job_id, e, exc_info=True)
        # run_job handles its own error state, but catch anything unexpected
        try:
            await update_job(pool, job_id, status="failed", error_message=str(e)[:500])
            await emit_event(pool, job_id, "error", "Processing failed. Please retry or contact support.")
        except Exception:
            pass
        return {"status": "failed", "job_id": job_id, "error": str(e)[:200]}


async def run_remaining_phases(ctx: dict, job_id: int, username: str, phases: list[str]) -> dict:
    """ARQ job function: run remaining phases (match→enrich→export) for a scanned job.

    Called after the user selects a tier on the configure page.
    The ingest phase already ran — this picks up from match onward.
    """
    pool = ctx["pool"]
    config = ctx["config"]

    from snatched.routes.api import _run_remaining_phases
    from snatched.db import update_job, emit_event

    logger.info("Worker picked up remaining phases for job %d: %s", job_id, phases)

    await update_job(pool, job_id, status="running")
    await emit_event(pool, job_id, "progress", "Processing started")

    try:
        await _run_remaining_phases(pool, job_id, username, config, phases)
        return {"status": "completed", "job_id": job_id}
    except asyncio.CancelledError:
        logger.warning("Job %d was cancelled", job_id)
        await update_job(pool, job_id, status="cancelled")
        await emit_event(pool, job_id, "error", "Job was cancelled")
        return {"status": "cancelled", "job_id": job_id}
    except Exception as e:
        logger.error("Job %d remaining phases failed: %s", job_id, e, exc_info=True)
        try:
            await update_job(pool, job_id, status="failed", error_message=str(e)[:500])
            await emit_event(pool, job_id, "error", "Processing failed. Please retry or contact support.")
        except Exception:
            pass
        return {"status": "failed", "job_id": job_id, "error": str(e)[:200]}


class WorkerSettings:
    """ARQ worker configuration."""

    functions = [process_job, run_remaining_phases]
    on_startup = startup
    on_shutdown = shutdown

    redis_settings = RedisSettings(
        host=REDIS_HOST,
        port=REDIS_PORT,
        database=REDIS_DB,
    )

    max_jobs = MAX_CONCURRENT_JOBS
    job_timeout = JOB_TIMEOUT  # 4 hours
    max_tries = 1  # No automatic retry — jobs are too expensive
    health_check_interval = 30  # seconds

    # Queue names — worker listens to both, high priority first
    queue_name = "snatched:default"
