"""Selective reprocessing engine for re-running phases without full re-ingest.

New in v3 — allows re-running any pipeline phase (match, enrich, export)
or targeted operations (chat export, XMP sidecars) without destroying the
Phase 1 ingest data. Supports lane-scoped reprocessing.
"""

import logging
import sqlite3
import time
from enum import Enum
from pathlib import Path
from typing import Callable

from snatched.config import Config
from snatched.processing import enrich, export, match
from snatched.processing.xmp import write_xmp_sidecars

logger = logging.getLogger(__name__)


class ReprocessMode(Enum):
    """Reprocessing modes for selective phase re-runs."""
    MATCH = "match"        # Re-run Phase 2 only
    ENRICH = "enrich"      # Re-run Phase 3 only
    EXPORT = "export"      # Re-run Phase 4 only
    CHAT = "chat"          # Re-run chat export only
    XMP = "xmp"            # Re-run XMP sidecar generation only
    LANE = "lane"          # Re-run enrich+export for a lane
    ALL = "all"            # Re-run phases 2-4


# Lane → SQL WHERE clause fragments
LANE_ASSET_FILTERS = {
    'memories': "a.asset_type IN ('memory_main', 'memory_overlay')",
    'stories': "a.asset_type = 'story'",
    'chats': "a.asset_type = 'chat'",
}

# Same filters without the 'a.' prefix (for direct assets table queries)
LANE_ASSET_FILTERS_DIRECT = {
    'memories': "asset_type IN ('memory_main', 'memory_overlay')",
    'stories': "asset_type = 'story'",
    'chats': "asset_type = 'chat'",
}


def validate_reprocess(
    db: sqlite3.Connection,
    mode: ReprocessMode | str,
    lane: str | None = None,
) -> tuple[bool, str]:
    """Validate that reprocessing is safe and prerequisite data exists.

    Args:
        db: SQLite database connection
        mode: Reprocessing mode
        lane: Optional lane filter

    Returns:
        (is_valid, reason) — reason is empty string if valid.
    """
    if isinstance(mode, str):
        try:
            mode = ReprocessMode(mode)
        except ValueError:
            return False, f"Unknown reprocess mode: '{mode}'"

    # Check Phase 1 data exists (required for all modes)
    asset_count = db.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
    if asset_count == 0:
        return False, "No assets found. Run Phase 1 (ingest) first."

    # Modes that require Phase 2 data
    needs_matches = mode in (
        ReprocessMode.ENRICH, ReprocessMode.EXPORT,
        ReprocessMode.CHAT, ReprocessMode.XMP, ReprocessMode.LANE,
    )
    if needs_matches:
        match_count = db.execute(
            "SELECT COUNT(*) FROM matches WHERE is_best = 1"
        ).fetchone()[0]
        if match_count == 0:
            return False, "No best matches found. Run Phase 2 (match) first."

    # LANE mode requires a lane parameter
    if mode == ReprocessMode.LANE and not lane:
        return False, "LANE mode requires a lane parameter ('memories', 'stories', or 'chats')."

    # Validate lane name
    if lane and lane not in LANE_ASSET_FILTERS:
        return False, f"Unknown lane '{lane}'. Must be: memories, stories, or chats."

    return True, ""


def clear_phase_data(
    db: sqlite3.Connection,
    phase: int,
    lane: str | None = None,
) -> dict:
    """Clear all data from a phase to enable safe re-run.

    Phase 2: DELETE FROM matches (lane filtering not supported — always full clear)
    Phase 3: NULL out enrichment columns on matches
    Phase 4: NULL out export columns on assets

    Args:
        db: SQLite database connection
        phase: Phase number to clear (2, 3, or 4)
        lane: Optional lane filter

    Returns:
        {'rows_affected': int, 'phase': int, 'lane': str | None}

    Raises:
        ValueError: If phase is not 2, 3, or 4
    """
    if phase not in (2, 3, 4):
        raise ValueError(f"phase must be 2, 3, or 4; got {phase}")

    # Build lane WHERE clause
    lane_where = LANE_ASSET_FILTERS.get(lane, "") if lane else ""
    lane_where_direct = LANE_ASSET_FILTERS_DIRECT.get(lane, "") if lane else ""

    if phase == 2:
        # Phase 2: delete all matches (lane filtering doesn't apply to matching)
        cursor = db.execute("DELETE FROM matches")
        db.commit()
        rows = cursor.rowcount
        logger.info(f"Cleared phase 2: {rows} matches deleted")
        return {'rows_affected': rows, 'phase': 2, 'lane': None}

    elif phase == 3:
        if lane_where:
            sql = f"""
                UPDATE matches SET
                    matched_lat=NULL, matched_lon=NULL, gps_source=NULL,
                    display_name=NULL, creator_str=NULL, direction=NULL, conversation=NULL,
                    output_subdir=NULL, output_filename=NULL, exif_tags_json=NULL
                WHERE id IN (
                    SELECT m.id FROM matches m
                    JOIN assets a ON m.asset_id = a.id
                    WHERE {lane_where}
                )
            """
        else:
            sql = """
                UPDATE matches SET
                    matched_lat=NULL, matched_lon=NULL, gps_source=NULL,
                    display_name=NULL, creator_str=NULL, direction=NULL, conversation=NULL,
                    output_subdir=NULL, output_filename=NULL, exif_tags_json=NULL
            """
        cursor = db.execute(sql)
        db.commit()
        rows = cursor.rowcount
        logger.info(f"Cleared phase 3: {rows} matches reset (lane={lane})")
        return {'rows_affected': rows, 'phase': 3, 'lane': lane}

    else:  # phase == 4
        # XMP columns (xmp_written, xmp_path) are NOT cleared here —
        # use ReprocessMode.XMP to clear those independently.
        if lane_where_direct:
            sql = f"""
                UPDATE assets SET output_path=NULL, output_sha256=NULL,
                                  exif_written=0, exif_error=NULL
                WHERE {lane_where_direct}
            """
        else:
            sql = """
                UPDATE assets SET output_path=NULL, output_sha256=NULL,
                                  exif_written=0, exif_error=NULL
            """
        cursor = db.execute(sql)
        db.commit()
        rows = cursor.rowcount
        logger.info(f"Cleared phase 4: {rows} assets reset (lane={lane})")
        return {'rows_affected': rows, 'phase': 4, 'lane': lane}


def reprocess(
    db: sqlite3.Connection,
    project_dir: Path,
    config: Config,
    mode: ReprocessMode | str,
    lane: str | None = None,
    clear: bool = True,
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    """Main reprocessing engine.

    Selectively re-runs one or more phases without full re-ingest.
    Phase 1 data (assets table) is never touched.

    Args:
        db: SQLite database connection
        project_dir: User's project directory
        config: Configuration object
        mode: Reprocessing mode
        lane: Optional lane filter (required for LANE mode)
        clear: If True, clear phase data before reprocessing
        progress_cb: Optional progress callback

    Returns:
        {'mode': str, 'lane': str|None, 'cleared': bool, 'phase_results': dict,
         'success': bool, 'errors': list[str], 'elapsed': float}
    """
    t0 = time.time()

    # Normalize mode
    if isinstance(mode, str):
        try:
            mode = ReprocessMode(mode)
        except ValueError:
            return {
                'mode': str(mode),
                'lane': lane,
                'cleared': False,
                'phase_results': {},
                'success': False,
                'errors': [f"Unknown reprocess mode: '{mode}'"],
                'elapsed': 0.0,
            }

    # Validate preconditions
    is_valid, reason = validate_reprocess(db, mode, lane)
    if not is_valid:
        logger.warning(f"Reprocess validation failed: {reason}")
        return {
            'mode': mode.value,
            'lane': lane,
            'cleared': False,
            'phase_results': {},
            'success': False,
            'errors': [reason],
            'elapsed': 0.0,
        }

    logger.info(f"Reprocessing: mode={mode.value}, lane={lane}, clear={clear}")
    if progress_cb:
        progress_cb(f"Reprocessing: {mode.value}" + (f" (lane={lane})" if lane else ""))

    results = {}
    errors = []

    # Clear phase data before re-running
    if clear:
        try:
            if mode in (ReprocessMode.MATCH, ReprocessMode.ALL):
                clear_phase_data(db, 2, lane)
            if mode in (ReprocessMode.ENRICH, ReprocessMode.LANE, ReprocessMode.ALL):
                clear_phase_data(db, 3, lane)
            if mode in (ReprocessMode.EXPORT, ReprocessMode.LANE, ReprocessMode.ALL):
                clear_phase_data(db, 4, lane)
            if mode == ReprocessMode.CHAT:
                # Chat mode: only clear chat-related export data
                clear_phase_data(db, 4, 'chats')
            if mode == ReprocessMode.XMP:
                # XMP mode: clear XMP columns only
                db.execute("UPDATE assets SET xmp_written=0, xmp_path=NULL")
                db.commit()
        except Exception as e:
            logger.exception("Failed to clear phase data")
            errors.append(f"Clear failed: {e}")

    # Execute phases
    try:
        if mode in (ReprocessMode.MATCH, ReprocessMode.ALL):
            if progress_cb:
                progress_cb("Re-running Phase 2: Match...")
            results['2'] = match.phase2_match(db, progress_cb)

        if mode in (ReprocessMode.ENRICH, ReprocessMode.LANE, ReprocessMode.ALL):
            if progress_cb:
                progress_cb("Re-running Phase 3: Enrich...")
            results['3'] = enrich.phase3_enrich(
                db, project_dir, config, progress_cb)

        if mode in (ReprocessMode.EXPORT, ReprocessMode.LANE, ReprocessMode.ALL):
            if progress_cb:
                progress_cb("Re-running Phase 4: Export...")
            lanes_list = [lane] if lane else None
            results['4'] = export.phase4_export(
                db, project_dir, config, lanes=lanes_list,
                progress_cb=progress_cb)

        if mode == ReprocessMode.CHAT:
            if progress_cb:
                progress_cb("Re-running chat export...")
            results['chat'] = {
                'text': export.export_chat_text(
                    db, project_dir, config, progress_cb),
                'png': export.export_chat_png(
                    db, project_dir, config, progress_cb),
            }

        if mode == ReprocessMode.XMP:
            if progress_cb:
                progress_cb("Re-generating XMP sidecars...")
            results['xmp'] = write_xmp_sidecars(
                db, project_dir, config, progress_cb)

    except Exception as e:
        logger.exception(f"Reprocess failed during {mode.value}")
        errors.append(str(e))

    elapsed = time.time() - t0
    success = len(errors) == 0

    logger.info(
        f"Reprocess complete: mode={mode.value}, lane={lane}, "
        f"success={success}, elapsed={elapsed:.1f}s"
    )

    if progress_cb:
        status = "complete" if success else f"completed with {len(errors)} errors"
        progress_cb(f"Reprocess {status} ({elapsed:.1f}s)")

    return {
        'mode': mode.value,
        'lane': lane,
        'cleared': clear,
        'phase_results': results,
        'success': success,
        'errors': errors,
        'elapsed': elapsed,
    }


# ── Convenience Wrappers ───────────────────────────────────────────────────


def reprocess_match(
    db: sqlite3.Connection,
    project_dir: Path,
    config: Config,
    **kwargs,
) -> dict:
    """Shortcut: reprocess(mode=ReprocessMode.MATCH)"""
    return reprocess(db, project_dir, config, mode=ReprocessMode.MATCH, **kwargs)


def reprocess_enrich(
    db: sqlite3.Connection,
    project_dir: Path,
    config: Config,
    lane: str | None = None,
    **kwargs,
) -> dict:
    """Shortcut: reprocess(mode=ReprocessMode.ENRICH, lane=lane)"""
    return reprocess(db, project_dir, config, mode=ReprocessMode.ENRICH, lane=lane, **kwargs)


def reprocess_export(
    db: sqlite3.Connection,
    project_dir: Path,
    config: Config,
    lane: str | None = None,
    **kwargs,
) -> dict:
    """Shortcut: reprocess(mode=ReprocessMode.EXPORT, lane=lane)"""
    return reprocess(db, project_dir, config, mode=ReprocessMode.EXPORT, lane=lane, **kwargs)


def reprocess_chat(
    db: sqlite3.Connection,
    project_dir: Path,
    config: Config,
    **kwargs,
) -> dict:
    """Shortcut: reprocess(mode=ReprocessMode.CHAT)"""
    return reprocess(db, project_dir, config, mode=ReprocessMode.CHAT, **kwargs)


def reprocess_xmp(
    db: sqlite3.Connection,
    project_dir: Path,
    config: Config,
    **kwargs,
) -> dict:
    """Shortcut: reprocess(mode=ReprocessMode.XMP)"""
    return reprocess(db, project_dir, config, mode=ReprocessMode.XMP, **kwargs)


def reprocess_lane(
    db: sqlite3.Connection,
    project_dir: Path,
    config: Config,
    lane: str,
    **kwargs,
) -> dict:
    """Shortcut: reprocess(mode=ReprocessMode.LANE, lane=lane)"""
    return reprocess(db, project_dir, config, mode=ReprocessMode.LANE, lane=lane, **kwargs)
