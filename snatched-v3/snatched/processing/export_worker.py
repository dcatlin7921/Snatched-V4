"""Export worker — builds configured export packages from completed jobs.

Each export is an async entity with its own config (lanes, options).
Multiple exports can be created per job, running in parallel without
interfering with each other because each export gets its own working
directory under job_dir/exports/{export_id}/work/.

The proc.db is opened read-only (PRAGMA query_only) so concurrent
exports against the same job are safe.

Directory layout produced per export:
    job_dir/exports/{export_id}/
        work/               ← functions write output/ and .snatched/ here
            output/         ← copied/tagged media files
            .snatched/      ← report.txt, report.json
        {username}-{type}-{date}-Job{id}-1.zip
        {username}-{type}-{date}-Job{id}-2.zip
        ...
"""

import asyncio
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def _friendly_zip_prefix(username: str, export_type: str, job_id: int) -> str:
    """Build a human-readable ZIP filename prefix.

    Examples:
        dave-Memories Only-Feb27-Job9
        dave-Full Export-Feb27-Job9
    """
    label = "Memories Only" if export_type == "quick_rescue" else "Full Export"
    date_str = datetime.now(timezone.utc).strftime("%b%d")
    return f"{username}-{label}-{date_str}-Job{job_id}"


def _build_config_for_export(base_config, export_row: dict):
    """Build a Config object from base app config + per-export overrides.

    Constructs lane settings from the export record's boolean flags so
    the underlying export functions see proper LaneConfig objects.

    Args:
        base_config: App-level Config object (provides defaults/system settings).
        export_row: Row dict from the exports table.

    Returns:
        A deep-copied Config with exif/xmp/lane settings overridden from
        the export record.
    """
    from snatched.config import LaneConfig

    # Deep-copy so per-export overrides don't bleed into the shared app config.
    config = base_config.model_copy(deep=True)

    # Apply EXIF/XMP toggles from the export record.
    config.exif.enabled = bool(export_row.get("exif_enabled", True))
    config.xmp.enabled = bool(export_row.get("xmp_enabled", False))

    # Build LaneConfig objects — only enable lanes listed in the export record.
    enabled_lanes = set(export_row.get("lanes") or ["memories"])

    _folder_style = str(export_row.get("folder_style", "year_month") or "year_month")
    _gps_precision = str(export_row.get("gps_precision", "exact") or "exact")
    _hide_sent_to = bool(export_row.get("hide_sent_to", False))

    config.lanes["memories"] = LaneConfig(
        enabled="memories" in enabled_lanes,
        burn_overlays=bool(export_row.get("burn_overlays", True)),
        folder_pattern=_folder_style,
        gps_precision=_gps_precision,
        hide_sent_to=_hide_sent_to,
    )
    config.lanes["chats"] = LaneConfig(
        enabled="chats" in enabled_lanes,
        export_text=bool(export_row.get("chat_text", True)),
        export_png=bool(export_row.get("chat_png", True)),
        dark_mode=bool(export_row.get("dark_mode_pngs", False)),
        folder_pattern=_folder_style,
        gps_precision=_gps_precision,
        hide_sent_to=_hide_sent_to,
        chat_timestamps=bool(export_row.get("chat_timestamps", True)),
        chat_cover_pages=bool(export_row.get("chat_cover_pages", True)),
    )
    config.lanes["stories"] = LaneConfig(
        enabled="stories" in enabled_lanes,
        folder_pattern=_folder_style,
        gps_precision=_gps_precision,
    )

    return config


async def run_export(pool, export_id: int, job_id: int, username: str, config) -> dict:
    """Run an export against a completed job's proc.db.

    Orchestrates the full export pipeline for one export record:
      1. copy_files      — copy matched assets to work/output/
      2. burn_overlays   — composite overlay PNGs (if enabled, memories lane)
      3. write_exif      — embed EXIF via exiftool (if enabled)
      4. write_xmp       — write XMP sidecars (if enabled)
      5. export_chat_text — write plain-text transcripts (if enabled, chats lane)
      6. export_chat_png  — render chat screenshot PNGs (if enabled, chats lane)
      7. write_reports   — write audit report.txt / report.json
      8. build_split_zips — produce split ZIP archive(s) from work/output/

    All CPU-bound functions run via asyncio.to_thread so the event loop
    stays unblocked while the pipeline executes.

    Args:
        pool: asyncpg connection pool.
        export_id: ID from the exports table.
        job_id: ID of the completed processing job.
        username: Job owner's username (used to locate job_dir).
        config: App config object (has config.server.data_dir).

    Returns:
        dict with export stats: {
            'export_id': int,
            'file_count': int,
            'zip_parts': list[dict],
            'zip_total_bytes': int,
            'stats': dict,
        }
        On failure returns {'error': str}.
    """
    from snatched.processing.export import (
        build_manifest,
        build_split_zips,
        burn_overlays,
        compute_zip_part_size,
        copy_files,
        export_chat_png,
        export_chat_text,
        write_exif,
        write_reports,
    )
    from snatched.db import get_export, update_export

    # ── Fetch export record ──────────────────────────────────────────────────
    export_row = await get_export(pool, export_id)
    if not export_row:
        raise ValueError(f"Export {export_id} not found")

    # ── Resolve paths ────────────────────────────────────────────────────────
    data_dir = Path(str(config.server.data_dir))
    job_dir = data_dir / username / "jobs" / str(job_id)
    proc_db_path = job_dir / "proc.db"

    # Per-export working directory acts as project_dir for export functions.
    # Each export's output/ tree is isolated here so parallel exports don't
    # overwrite each other's files.
    export_work_dir = job_dir / "exports" / str(export_id) / "work"
    export_work_dir.mkdir(parents=True, exist_ok=True)

    # ZIP parts land in the export's root (alongside work/).
    zip_base_dir = job_dir / "exports" / str(export_id)

    if not proc_db_path.exists():
        await update_export(
            pool, export_id,
            status="failed",
            error_message="Job proc.db not found",
            completed_at=datetime.now(timezone.utc),
        )
        return {"error": "proc.db not found"}

    # ── Mark export as building ──────────────────────────────────────────────
    started_iso = datetime.now(timezone.utc).isoformat()
    await update_export(
        pool, export_id,
        status="building",
        started_at=datetime.now(timezone.utc),
    )

    try:
        stats: dict = {}

        # Build a Config object with this export's specific overrides.
        export_config = _build_config_for_export(config, export_row)

        lanes = list(export_row.get("lanes") or ["memories"])
        exif_enabled = bool(export_row.get("exif_enabled", True))
        xmp_enabled = bool(export_row.get("xmp_enabled", False))
        do_burn_overlays = bool(export_row.get("burn_overlays", True))
        do_chat_text = bool(export_row.get("chat_text", True))
        do_chat_png = bool(export_row.get("chat_png", True))

        # ── Build planned steps list for frontend progress tracking ───────
        planned_steps = ["copy"]
        if do_burn_overlays and "memories" in lanes:
            planned_steps.append("overlays")
        if exif_enabled:
            planned_steps.append("exif")
        if xmp_enabled:
            planned_steps.append("xmp")
        if do_chat_text and "chats" in lanes:
            planned_steps.append("chat_text")
        if do_chat_png and "chats" in lanes:
            planned_steps.append("chat_png")
        planned_steps.append("reports")
        planned_steps.append("zips")

        # Persist initial progress state so frontend can render step list
        await update_export(pool, export_id, stats_json={
            "current_step": "copy",
            "steps_completed": [],
            "planned_steps": planned_steps,
            "started_at_iso": started_iso,
        })

        # ── Progress helper — updates DB + emits SSE event after each step ─
        _completed_steps: list[str] = []

        async def _emit_export_event(event_type: str, message: str, data: dict | None = None):
            """Emit an SSE event for this export via the job_events table."""
            try:
                from snatched.db import emit_event
                event_data = {"export_id": export_id, **(data or {})}
                await emit_event(pool, job_id, event_type, message, event_data)
            except Exception:
                pass  # Non-critical — SSE is best-effort

        async def _progress(step_key: str):
            _completed_steps.append(step_key)
            idx = planned_steps.index(step_key) if step_key in planned_steps else -1
            next_step = planned_steps[idx + 1] if idx + 1 < len(planned_steps) else None
            stats_snapshot = {
                "current_step": next_step,
                "steps_completed": list(_completed_steps),
                "planned_steps": planned_steps,
                "started_at_iso": started_iso,
                **{k: v for k, v in stats.items() if isinstance(v, dict)},
            }
            await update_export(pool, export_id, stats_json=stats_snapshot)
            await _emit_export_event(
                "export_step",
                f"Export step '{step_key}' complete",
                {"step": step_key, "stats": stats_snapshot},
            )

        # Thread-safe callback for long-running steps (chat_png) to emit
        # intermediate progress without blocking the event loop.
        _loop = asyncio.get_running_loop()

        def _threadsafe_progress_cb(msg: str, data: dict | None = None):
            """Called from worker threads to push SSE updates."""
            try:
                coro = _emit_export_event("export_progress", msg, data)
                asyncio.run_coroutine_threadsafe(coro, _loop)
            except Exception:
                pass

        # Open proc.db read-only to allow concurrent exports against the same job.
        db = sqlite3.connect(
            f"file:{proc_db_path}?mode=ro",
            uri=True,
            check_same_thread=False,
        )
        db.row_factory = sqlite3.Row

        try:
            # ── Step 1: Copy files ───────────────────────────────────────────
            logger.info(
                "Export %d: copying files for lanes %s", export_id, lanes
            )
            copy_stats = await asyncio.to_thread(
                copy_files,
                db,
                export_work_dir,   # project_dir — functions write to work/output/
                export_config,
                lanes,
                None,              # progress_cb
                True,              # readonly — proc.db opened read-only
            )
            stats["copy"] = copy_stats or {}
            await _progress("copy")

            files_copied = copy_stats.get("copied", 0) if copy_stats else 0

            # ── Step 2: Burn overlays ────────────────────────────────────────
            if do_burn_overlays and "memories" in lanes and files_copied > 0:
                logger.info("Export %d: burning overlays", export_id)
                overlay_stats = await asyncio.to_thread(
                    burn_overlays,
                    db,
                    export_work_dir,
                    export_config,
                    None,
                    True,              # readonly
                )
                stats["overlays"] = overlay_stats or {}
                await _progress("overlays")
            else:
                stats["overlays"] = {"burned": 0, "errors": 0, "elapsed": 0.0, "skipped": True}
                if "overlays" in planned_steps:
                    await _progress("overlays")

            # ── Step 3: Write EXIF ───────────────────────────────────────────
            if exif_enabled and files_copied > 0:
                logger.info("Export %d: writing EXIF metadata", export_id)
                exif_stats = await asyncio.to_thread(
                    write_exif,
                    db,
                    export_work_dir,
                    export_config,
                    None,
                    True,              # readonly
                )
                stats["exif"] = exif_stats or {}
                await _progress("exif")
            else:
                stats["exif"] = {
                    "written": 0, "errors": 0, "elapsed": 0.0,
                    "skipped": True,
                }
                if "exif" in planned_steps:
                    await _progress("exif")

            # ── Step 4: XMP sidecars (optional) ─────────────────────────────
            if xmp_enabled and files_copied > 0:
                try:
                    from snatched.processing.xmp import write_xmp_sidecars

                    logger.info("Export %d: writing XMP sidecars", export_id)
                    xmp_stats = await asyncio.to_thread(
                        write_xmp_sidecars,
                        db,
                        export_work_dir,
                        export_config,
                        None,
                        True,              # readonly
                    )
                    stats["xmp"] = xmp_stats or {}
                except ImportError:
                    logger.warning(
                        "Export %d: XMP module not available, skipping", export_id
                    )
                    stats["xmp"] = {"written": 0, "skipped": True}
                except Exception as xmp_err:
                    logger.error(
                        "Export %d: XMP sidecar generation failed: %s",
                        export_id, xmp_err,
                    )
                    stats["xmp"] = {"error": str(xmp_err)}
                if "xmp" in planned_steps:
                    await _progress("xmp")

            # ── Step 5: Chat text export ─────────────────────────────────────
            if do_chat_text and "chats" in lanes:
                logger.info("Export %d: exporting chat text", export_id)
                chat_text_stats = await asyncio.to_thread(
                    export_chat_text,
                    db,
                    export_work_dir,
                    export_config,
                    None,
                )
                stats["chat_text"] = chat_text_stats or {}
                await _progress("chat_text")
            else:
                stats["chat_text"] = {
                    "conversations": 0, "messages": 0, "elapsed": 0.0,
                    "skipped": True,
                }
                if "chat_text" in planned_steps:
                    await _progress("chat_text")

            # ── Step 6: Chat PNG export ──────────────────────────────────────
            if do_chat_png and "chats" in lanes:
                logger.info("Export %d: rendering chat PNGs", export_id)

                def _chat_png_progress(msg, extra=None):
                    _threadsafe_progress_cb(msg, {"step": "chat_png", **(extra or {})})

                chat_png_stats = await asyncio.to_thread(
                    export_chat_png,
                    db,
                    export_work_dir,
                    export_config,
                    _chat_png_progress,
                    True,              # readonly
                )
                stats["chat_png"] = chat_png_stats or {}
                await _progress("chat_png")
            else:
                stats["chat_png"] = {
                    "conversations": 0, "pages": 0, "elapsed": 0.0,
                    "skipped": True,
                }
                if "chat_png" in planned_steps:
                    await _progress("chat_png")

            # ── Step 7: Write reports ────────────────────────────────────────
            logger.info("Export %d: writing reports", export_id)
            report_stats = await asyncio.to_thread(
                write_reports,
                db,
                export_work_dir,
                export_config,
                stats,
                None,
            )
            stats["reports"] = report_stats or {}
            await _progress("reports")

        finally:
            db.close()

        # ── Free tier README — explains what's included and what's available ──
        async with pool.acquire() as conn:
            _job_tier = await conn.fetchval(
                "SELECT job_tier FROM processing_jobs WHERE id=$1", job_id
            )
        if (_job_tier or "free") == "free":
            readme_path = export_work_dir / "output" / "README.txt"
            readme_path.parent.mkdir(parents=True, exist_ok=True)
            readme_path.write_text(
                "SNATCHED — Free Export\n"
                "======================\n\n"
                "This export includes your Snapchat Memories with recovered dates.\n"
                "Files are organized by date so they sort correctly in your camera roll.\n\n"
                "WHAT'S INCLUDED:\n"
                "  - Memories (photos & videos) with original dates in filenames\n"
                "  - Date recovery via 6-level matching cascade\n\n"
                "WHAT'S AVAILABLE WITH PAID TIERS:\n"
                "  - GPS coordinates embedded in EXIF ($4.99 Memory Rescue)\n"
                "  - Snapchat overlays composited onto photos ($4.99 Memory Rescue)\n"
                "  - Chat transcripts + dark mode PNGs ($9.99 Complete Archive)\n"
                "  - Story archive with dates preserved ($9.99 Complete Archive)\n"
                "  - XMP sidecar files for Lightroom ($9.99 Complete Archive)\n\n"
                "Visit snatched.app to upgrade and get the full experience.\n",
                encoding="utf-8",
            )
            logger.info("Export %d: wrote free-tier README.txt", export_id)

        # ── Step 8: Build manifest (no pre-built ZIPs) ────────────────────────
        # Instead of writing ZIP archives to SSD, build a file manifest that
        # the download endpoint uses to stream ZIPs on-the-fly.
        output_dir = export_work_dir / "output"
        if not output_dir.exists():
            logger.warning(
                "Export %d: output dir missing after copy step — "
                "no files to ZIP",
                export_id,
            )
            output_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Export %d: building file manifest", export_id)
        manifest_parts = await asyncio.to_thread(build_manifest, output_dir)

        # ── Collect final metrics ─────────────────────────────────────────────
        file_count = sum(len(part) for part in manifest_parts)
        output_total_bytes = sum(
            entry["size_bytes"] for part in manifest_parts for entry in part
        )
        stats["zips"] = {"parts": len(manifest_parts), "total_bytes": output_total_bytes}

        # ── Persist results ───────────────────────────────────────────────────
        _completed_steps.append("zips")
        await update_export(
            pool, export_id,
            status="completed",
            completed_at=datetime.now(timezone.utc),
            zip_dir=str(output_dir),              # repurposed: points to output/ for streaming
            zip_part_count=len(manifest_parts),
            zip_total_bytes=output_total_bytes,
            file_count=file_count,
            stats_json={
                "manifest_parts": manifest_parts,
                "current_step": None,
                "steps_completed": list(planned_steps),
                "planned_steps": planned_steps,
                "started_at_iso": started_iso,
                **stats,
            },
        )

        logger.info(
            "Export %d complete: %d files, %d manifest part(s), %d bytes",
            export_id, file_count, len(manifest_parts), output_total_bytes,
        )

        # Emit SSE event so polling UI can detect completion faster
        try:
            from snatched.db import emit_event
            await emit_event(
                pool, job_id, "export_complete",
                f"Export {export_id} ready for download",
                {"export_id": export_id, "file_count": file_count,
                 "zip_parts": len(manifest_parts), "zip_total_bytes": output_total_bytes},
            )
        except Exception:
            pass  # Non-critical — polling fallback will catch it

        # Change 4: clean up extracted/ if no more exports pending
        try:
            async with pool.acquire() as conn:
                pending = await conn.fetchval(
                    "SELECT COUNT(*) FROM exports WHERE job_id=$1 AND status NOT IN ('completed','failed','cancelled')",
                    job_id,
                )
            if pending == 0:
                extracted_dir = job_dir / "extracted"
                if extracted_dir.exists():
                    import shutil
                    await asyncio.to_thread(shutil.rmtree, str(extracted_dir), True)
                    logger.info("Export %d: deleted extracted/ from SSD (no pending exports)", export_id)
        except Exception as cleanup_err:
            logger.debug("Export %d: extracted/ cleanup skipped: %s", export_id, cleanup_err)

        return {
            "export_id": export_id,
            "file_count": file_count,
            "manifest_parts": manifest_parts,
            "output_total_bytes": output_total_bytes,
            "stats": stats,
        }

    except Exception as exc:
        logger.error(
            "Export %d failed: %s", export_id, exc, exc_info=True
        )
        await update_export(
            pool, export_id,
            status="failed",
            error_message=str(exc),
            completed_at=datetime.now(timezone.utc),
        )
        return {"error": str(exc)}
