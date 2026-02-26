"""Lane controller managing three independent export pipelines.

New in v3 — generalizes v2's single-pass pipeline into three independent
pipelines (Memories, Stories, Chats) that share the same SQLite database.
Lanes run sequentially (SQLite doesn't support concurrent writes).
"""

import logging
import sqlite3
import time
from enum import Enum
from pathlib import Path
from typing import Callable

from snatched.config import Config
from snatched.processing import enrich, export
from snatched.processing.xmp import write_xmp_sidecars

logger = logging.getLogger(__name__)


class Lane(Enum):
    """Export lane identifiers."""
    MEMORIES = "memories"
    STORIES = "stories"
    CHATS = "chats"
    ALL = "all"


# Lane → SQL WHERE clause for asset_type filtering
LANE_FILTERS = {
    'memories': "a.asset_type IN ('memory_main', 'memory_overlay')",
    'stories': "a.asset_type = 'story'",
    'chats': "a.asset_type = 'chat'",
}


class LaneController:
    """Manages lane-specific export orchestration.

    Each lane processes a subset of assets (by asset_type) through
    Phase 3 (enrich) and Phase 4 (export) using shared pipeline functions.
    """

    def __init__(
        self,
        db: sqlite3.Connection,
        project_dir: Path,
        config: Config,
        progress_cb: Callable[[str], None] | None = None,
    ) -> None:
        """Initialize lane controller.

        Args:
            db: SQLite database connection (per-user proc.db)
            project_dir: Project root directory
            config: Configuration object
            progress_cb: Optional callback for progress messages
        """
        self.db = db
        self.project_dir = project_dir
        self.config = config
        self.progress_cb = progress_cb

    def get_lane_asset_filter(self, lane: Lane | str) -> str:
        """Return SQL WHERE clause fragment for lane asset filtering.

        Args:
            lane: Lane identifier (Lane enum or string name)

        Returns:
            SQL fragment for WHERE clause

        Raises:
            ValueError: If lane is not recognized
        """
        if isinstance(lane, Lane):
            lane = lane.value

        if lane == 'all':
            return "1=1"  # No filtering

        if lane not in LANE_FILTERS:
            raise ValueError(
                f"Unknown lane '{lane}'. Must be one of: "
                f"{', '.join(LANE_FILTERS.keys())}, all"
            )
        return LANE_FILTERS[lane]

    def count_assets_in_lane(self, lane: Lane | str) -> int:
        """Count best-matched assets eligible for export in lane.

        Args:
            lane: Lane identifier

        Returns:
            Integer count of assets eligible for export
        """
        if isinstance(lane, Lane):
            lane = lane.value

        lane_filter = self.get_lane_asset_filter(lane)
        count = self.db.execute(f"""
            SELECT COUNT(*)
            FROM assets a
            JOIN matches m ON a.id = m.asset_id
            WHERE m.is_best = 1 AND {lane_filter}
        """).fetchone()[0]
        return count

    def run_lane(
        self,
        lane: Lane | str,
        phases: list[int] | None = None,
        skip_phase: list[int] | None = None,
    ) -> dict:
        """Run enrich + export for a specific lane.

        Phases 1 and 2 are not lane-filtered (they operate on all assets).
        Phases 3 and 4 apply lane filters.

        Args:
            lane: Lane to run ('memories', 'stories', 'chats', or 'all')
            phases: Phases to run (default: [3, 4])
            skip_phase: Phases to skip

        Returns:
            {'lane': str, 'assets_processed': int, 'phase_results': dict, 'elapsed': float}
        """
        t0 = time.time()

        if isinstance(lane, Lane):
            lane = lane.value

        if phases is None:
            phases = [3, 4]
        if skip_phase:
            phases = [p for p in phases if p not in skip_phase]

        lane_name = lane
        asset_count = self.count_assets_in_lane(lane)

        logger.info(f"Running lane '{lane_name}': {asset_count} assets, phases {phases}")
        if self.progress_cb:
            self.progress_cb(f"Lane '{lane_name}': {asset_count} assets")

        phase_results = {}

        # Phase 1 and 2: not lane-filtered (operate on all asset types)
        if 1 in phases:
            # Phase 1 needs input_dir and json_dir which aren't available here.
            # Callers should run phase1_ingest() directly when needed.
            logger.warning(
                "Phase 1 cannot be run via lane controller (requires input_dir/json_dir). "
                "Use phase1_ingest() directly."
            )

        if 2 in phases:
            from snatched.processing.match import phase2_match
            phase_results['2'] = phase2_match(self.db, self.progress_cb)

        # Phase 3: enrich (processes all best-matched assets — no lane filter.
        # Enrichment is cheap and idempotent so filtering isn't needed.)
        if 3 in phases:
            phase_results['3'] = enrich.phase3_enrich(
                self.db, self.project_dir, self.config, self.progress_cb)

        # Phase 4: export (lane-filtered)
        if 4 in phases:
            lanes_list = [lane] if lane != 'all' else None
            phase_results['4'] = export.phase4_export(
                self.db, self.project_dir, self.config,
                lanes=lanes_list, progress_cb=self.progress_cb)

            # XMP sidecars if enabled
            if self.config.xmp.enabled:
                phase_results['xmp'] = write_xmp_sidecars(
                    self.db, self.project_dir, self.config, self.progress_cb)

        elapsed = time.time() - t0

        logger.info(f"Lane '{lane_name}' complete in {elapsed:.1f}s")
        if self.progress_cb:
            self.progress_cb(f"Lane '{lane_name}' complete ({elapsed:.1f}s)")

        return {
            'lane': lane_name,
            'assets_processed': asset_count,
            'phase_results': phase_results,
            'elapsed': elapsed,
        }

    def run_memories(self, **kwargs) -> dict:
        """Shortcut: run_lane(Lane.MEMORIES, **kwargs)"""
        return self.run_lane(Lane.MEMORIES, **kwargs)

    def run_stories(self, **kwargs) -> dict:
        """Shortcut: run_lane(Lane.STORIES, **kwargs)"""
        return self.run_lane(Lane.STORIES, **kwargs)

    def run_chats(self, **kwargs) -> dict:
        """Shortcut: run_lane(Lane.CHATS, **kwargs)"""
        return self.run_lane(Lane.CHATS, **kwargs)

    def run_all(self, **kwargs) -> dict:
        """Run all three lanes sequentially.

        Returns:
            {'memories': dict, 'stories': dict, 'chats': dict, 'total_elapsed': float}
        """
        t0 = time.time()
        results = {}

        for lane_name in ['memories', 'stories', 'chats']:
            if self.progress_cb:
                self.progress_cb(f"Starting {lane_name} lane...")
            result = self.run_lane(lane_name, **kwargs)
            results[lane_name] = result

        return {
            'memories': results['memories'],
            'stories': results['stories'],
            'chats': results['chats'],
            'total_elapsed': time.time() - t0,
        }
