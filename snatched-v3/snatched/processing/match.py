"""Phase 2: Match assets to metadata via 6-strategy priority cascade.

Each strategy assigns a confidence score, and the highest-confidence
match per asset is marked is_best=1. All strategy SQL is a direct port
from snatched.py v2 lines 1249-1647 with no algorithmic changes.

Confidence scores:
  1.0  exact_media_id   — chat file_id = message Media ID
  1.0  memory_uuid      — memory filename UUID = memories.mid
  0.9  story_id         — ordered pairing (0.5 if counts differ)
  0.9  memory_uuid_zip  — UUID from overlay~zip filename
  0.8  timestamp_type   — unique date + media type on both sides
  0.7  date_type_count  — count-aligned ordered pairing
  0.3  date_only        — any asset with a date_str (fallback)
"""

import sqlite3
import logging
import time
from typing import Any, Callable

from snatched.utils import UUID_RE

logger = logging.getLogger(__name__)


# ── Helper ───────────────────────────────────────────────────────────────────


def _matched_asset_ids(db: sqlite3.Connection) -> set[int]:
    """Return set of asset IDs that already have at least one match row."""
    rows = db.execute("SELECT DISTINCT asset_id FROM matches").fetchall()
    return {r[0] for r in rows}


# ── Strategy 1: Exact Media ID (Confidence 1.0) ─────────────────────────────


def _strategy1_exact_media_id(db: sqlite3.Connection) -> int:
    """Match chat assets via file_id = chat_media_ids.media_id.

    Zero false positives — the most accurate match strategy.
    """
    sql = """
        INSERT INTO matches (asset_id, strategy, confidence, chat_message_id, matched_date)
        SELECT a.id, 'exact_media_id', 1.0, cm.id, cm.created_dt
        FROM assets a
        JOIN chat_media_ids cmi ON a.file_id = cmi.media_id
        JOIN chat_messages cm ON cmi.chat_message_id = cm.id
        WHERE a.asset_type = 'chat'
        AND a.id NOT IN (SELECT DISTINCT asset_id FROM matches)
    """
    db.execute(sql)
    db.commit()
    count = db.execute(
        "SELECT COUNT(*) FROM matches WHERE strategy = 'exact_media_id'"
    ).fetchone()[0]
    return count


# ── Strategy 2: Memory UUID (Confidence 1.0) ────────────────────────────────


def _strategy2_memory_uuid(db: sqlite3.Connection) -> int:
    """Match memory_main assets via filename UUID = memories.mid.

    Also captures GPS (lat/lon) from memory metadata when available.
    """
    sql = """
        INSERT INTO matches (asset_id, strategy, confidence, memory_id, matched_date,
                             matched_lat, matched_lon, gps_source)
        SELECT a.id, 'memory_uuid', 1.0, m.id, m.date_dt,
               m.lat, m.lon,
               CASE WHEN m.lat IS NOT NULL THEN 'metadata' ELSE NULL END
        FROM assets a
        JOIN memories m ON a.memory_uuid = m.mid
        WHERE a.asset_type = 'memory_main'
        AND a.id NOT IN (SELECT DISTINCT asset_id FROM matches)
    """
    db.execute(sql)
    db.commit()
    count = db.execute(
        "SELECT COUNT(*) FROM matches WHERE strategy = 'memory_uuid'"
    ).fetchone()[0]
    return count


# ── Strategy 3: Story ID (Confidence 0.9 or 0.5) ───────────────────────────


def _strategy3_story_id(db: sqlite3.Connection) -> int:
    """Pair story assets with story metadata by media type (IMAGE vs VIDEO).

    Both sides sorted and paired positionally. Confidence 0.9 if counts
    match perfectly, 0.5 if counts differ (partial coverage).
    """
    story_assets = db.execute("""
        SELECT id, filename, is_video FROM assets
        WHERE asset_type = 'story'
        AND id NOT IN (SELECT DISTINCT asset_id FROM matches)
        ORDER BY filename
    """).fetchall()

    if not story_assets:
        return 0

    img_assets = [(r[0], r[1]) for r in story_assets if not r[2]]
    vid_assets = [(r[0], r[1]) for r in story_assets if r[2]]

    img_stories = db.execute("""
        SELECT id, created_dt FROM stories
        WHERE content_type = 'IMAGE'
        ORDER BY created_dt
    """).fetchall()
    vid_stories = db.execute("""
        SELECT id, created_dt FROM stories
        WHERE content_type = 'VIDEO'
        ORDER BY created_dt
    """).fetchall()

    count = 0
    for assets_group, stories_group, type_label in [
        (img_assets, img_stories, 'IMAGE'),
        (vid_assets, vid_stories, 'VIDEO'),
    ]:
        if not assets_group or not stories_group:
            continue

        confidence = 0.9 if len(assets_group) == len(stories_group) else 0.5

        pairs = min(len(assets_group), len(stories_group))
        for i in range(pairs):
            asset_id = assets_group[i][0]
            story_db_id = stories_group[i][0]
            story_date = stories_group[i][1]

            db.execute("""
                INSERT INTO matches (asset_id, strategy, confidence, story_id, matched_date)
                VALUES (?, 'story_id', ?, ?, ?)
            """, (asset_id, confidence, story_db_id, story_date))
            count += 1

    db.commit()
    return count


# ── Strategy 4: Timestamp + Type (Confidence 0.8) ───────────────────────────


def _strategy4_timestamp_type(db: sqlite3.Connection) -> int:
    """Match when exactly ONE asset and ONE snap share date + media type.

    Uniqueness on BOTH sides prevents false positives.
    """
    sql = """
        INSERT INTO matches (asset_id, strategy, confidence, snap_message_id, matched_date)
        SELECT a.id, 'timestamp_type', 0.8, sm.id, sm.created_dt
        FROM assets a
        JOIN snap_messages sm
            ON a.date_str = sm.created_date
            AND (
                (a.is_video = 1 AND sm.media_type = 'VIDEO')
                OR (a.is_video = 0 AND sm.media_type = 'IMAGE')
            )
        WHERE a.asset_type = 'chat'
        AND a.id NOT IN (SELECT DISTINCT asset_id FROM matches)
        AND (
            SELECT COUNT(*) FROM assets a2
            WHERE a2.asset_type = 'chat'
            AND a2.date_str = a.date_str
            AND a2.is_video = a.is_video
            AND a2.id NOT IN (SELECT DISTINCT asset_id FROM matches)
        ) = 1
        AND (
            SELECT COUNT(*) FROM snap_messages sm2
            WHERE sm2.created_date = a.date_str
            AND sm2.media_type = sm.media_type
            AND sm2.id NOT IN (SELECT snap_message_id FROM matches
                               WHERE snap_message_id IS NOT NULL)
        ) = 1
    """
    db.execute(sql)
    db.commit()
    count = db.execute(
        "SELECT COUNT(*) FROM matches WHERE strategy = 'timestamp_type'"
    ).fetchone()[0]
    return count


# ── Strategy 5: Date + Type + Count (Confidence 0.7) ────────────────────────


def _strategy5_date_type_count(db: sqlite3.Connection) -> int:
    """Pair assets with snaps when counts align per date + type group.

    For each (date_str, is_video) group of unmatched chat assets,
    fetch unmatched snaps with same date + type. If counts match,
    pair i-th asset with i-th snap (both sorted).
    """
    unmatched = db.execute("""
        SELECT id, date_str, is_video, filename FROM assets
        WHERE asset_type = 'chat'
        AND date_str IS NOT NULL
        AND id NOT IN (SELECT DISTINCT asset_id FROM matches)
        ORDER BY date_str, is_video, filename
    """).fetchall()

    if not unmatched:
        return 0

    # Group assets by (date_str, is_video)
    asset_groups: dict[tuple, list] = {}
    for row in unmatched:
        key = (row[1], row[2])
        asset_groups.setdefault(key, []).append(row)

    count = 0
    for (date_str, is_vid), assets_in_group in asset_groups.items():
        snap_type = 'VIDEO' if is_vid else 'IMAGE'

        snaps = db.execute("""
            SELECT id, created_dt FROM snap_messages
            WHERE created_date = ?
            AND media_type = ?
            AND id NOT IN (SELECT snap_message_id FROM matches
                           WHERE snap_message_id IS NOT NULL)
            ORDER BY created_ms, created_dt
        """, (date_str, snap_type)).fetchall()

        if len(snaps) != len(assets_in_group) or len(snaps) == 0:
            continue

        for i in range(len(assets_in_group)):
            asset_id = assets_in_group[i][0]
            snap_id = snaps[i][0]
            snap_date = snaps[i][1]

            db.execute("""
                INSERT INTO matches (asset_id, strategy, confidence,
                                     snap_message_id, matched_date)
                VALUES (?, 'date_type_count', 0.7, ?, ?)
            """, (asset_id, snap_id, snap_date))
            count += 1

    db.commit()
    return count


# ── Strategy 6: Date Only (Confidence 0.3) ──────────────────────────────────


def _strategy6_date_only(db: sqlite3.Connection) -> int:
    """Fallback: any unmatched chat/story asset with a date gets a match.

    matched_date is set to date_str + ' 00:00:00' (midnight).
    Ensures every asset gets at least a timestamp for EXIF embedding.
    """
    sql = """
        INSERT INTO matches (asset_id, strategy, confidence, matched_date)
        SELECT id, 'date_only', 0.3, date_str || ' 00:00:00'
        FROM assets
        WHERE asset_type IN ('chat', 'story')
        AND date_str IS NOT NULL
        AND id NOT IN (SELECT DISTINCT asset_id FROM matches)
    """
    db.execute(sql)
    db.commit()
    count = db.execute(
        "SELECT COUNT(*) FROM matches WHERE strategy = 'date_only'"
    ).fetchone()[0]
    return count


# ── Bonus: Overlay / ZIP UUID (Confidence 0.9) ──────────────────────────────


def _match_overlay_and_media_zips(db: sqlite3.Connection) -> int:
    """Extract UUID from overlay~zip / media~zip filenames, match to memories.

    Files with names like 'overlay~{uuid}~zip' contain a UUID that maps
    to memories.mid. Confidence 0.9 (below exact but above date-based).
    """
    candidates = db.execute("""
        SELECT id, file_id FROM assets
        WHERE file_id IS NOT NULL
        AND (file_id LIKE '%~zip%' OR file_id LIKE 'overlay~%' OR file_id LIKE 'media~%')
        AND id NOT IN (SELECT DISTINCT asset_id FROM matches)
    """).fetchall()

    if not candidates:
        return 0

    count = 0
    for asset_id, file_id in candidates:
        parts = file_id.split('~')
        uuid_candidate = None

        # Port of v2 lines 1479-1493: try each part, then remainder
        for part in parts:
            clean = part.split('-')[0] if '-' in part else part
            if UUID_RE.match(part):
                uuid_candidate = part
                break
            if UUID_RE.match(clean):
                uuid_candidate = clean
                break
            # Try joining parts[1:] with suffixes stripped
            if len(parts) > 1:
                remainder = '~'.join(parts[1:])
                for suffix in ['-overlay', '-main', '.zip']:
                    remainder = remainder.replace(suffix, '')
                if UUID_RE.match(remainder):
                    uuid_candidate = remainder
                    break

        if not uuid_candidate:
            continue

        mem = db.execute(
            "SELECT id, date_dt, lat, lon FROM memories WHERE mid = ?",
            (uuid_candidate,)
        ).fetchone()

        if mem:
            db.execute("""
                INSERT INTO matches (asset_id, strategy, confidence, memory_id,
                                     matched_date, matched_lat, matched_lon, gps_source)
                VALUES (?, 'memory_uuid_zip', 0.9, ?, ?, ?, ?,
                        CASE WHEN ? IS NOT NULL THEN 'metadata' ELSE NULL END)
            """, (asset_id, mem[0], mem[1], mem[2], mem[3], mem[2]))
            count += 1

    db.commit()
    return count


# ── Back-fill chat_message_id ────────────────────────────────────────────────

BACKFILL_WINDOW_MS = 60_000  # 60 seconds


def _backfill_chat_message_id(db: sqlite3.Connection) -> int:
    """Back-fill chat_message_id on best matches that only have snap_message_id.

    For matches linked to snap_messages (strategies 4/5), find the nearest
    unclaimed MEDIA chat_message in the same conversation within 60 seconds.
    This makes those files visible in chat PNG/text exports.
    """
    candidates = db.execute("""
        SELECT m.id, sm.conversation_id, sm.created_ms
        FROM matches m
        JOIN snap_messages sm ON m.snap_message_id = sm.id
        WHERE m.is_best = 1
          AND m.snap_message_id IS NOT NULL
          AND m.chat_message_id IS NULL
          AND sm.created_ms IS NOT NULL
    """).fetchall()

    if not candidates:
        logger.debug("Back-fill: no candidates (0 snap-only best matches)")
        return 0

    # Pre-load already-claimed chat_message_ids to prevent many-to-one
    already_claimed = set(
        r[0] for r in db.execute(
            "SELECT chat_message_id FROM matches "
            "WHERE chat_message_id IS NOT NULL AND is_best = 1"
        ).fetchall()
    )

    updated = 0
    batch = []

    for match_id, conv_id, snap_ms in candidates:
        row = db.execute("""
            SELECT cm.id, cm.created_ms
            FROM chat_messages cm
            WHERE cm.conversation_id = ?
              AND cm.media_type = 'MEDIA'
              AND cm.created_ms IS NOT NULL
            ORDER BY ABS(cm.created_ms - ?) ASC
            LIMIT 1
        """, (conv_id, snap_ms)).fetchone()

        if row is None:
            continue

        chat_id, chat_ms = row

        # Skip if already claimed by another match (TOCTOU-safe)
        if chat_id in already_claimed:
            continue

        # Enforce 60-second window
        if abs(chat_ms - snap_ms) > BACKFILL_WINDOW_MS:
            continue

        already_claimed.add(chat_id)
        batch.append((chat_id, match_id))
        updated += 1

        if len(batch) >= 500:
            db.executemany(
                "UPDATE matches SET chat_message_id = ? WHERE id = ?", batch)
            batch = []

    if batch:
        db.executemany(
            "UPDATE matches SET chat_message_id = ? WHERE id = ?", batch)
    db.commit()

    return updated


# ── Best Match Selection ─────────────────────────────────────────────────────


def _set_best_matches(db: sqlite3.Connection) -> int:
    """Select the highest-confidence match per asset as is_best=1.

    Ties broken by strategy priority: exact_media_id > memory_uuid >
    memory_uuid_zip > story_id > timestamp_type > date_type_count > date_only.
    """
    db.execute("UPDATE matches SET is_best = 0")

    db.execute("""
        UPDATE matches SET is_best = 1
        WHERE id IN (
            SELECT m.id FROM matches m
            INNER JOIN (
                SELECT asset_id, MAX(confidence) as max_conf
                FROM matches
                GROUP BY asset_id
            ) best ON m.asset_id = best.asset_id AND m.confidence = best.max_conf
            WHERE m.id = (
                SELECT m2.id FROM matches m2
                WHERE m2.asset_id = m.asset_id AND m2.confidence = best.max_conf
                ORDER BY CASE m2.strategy
                    WHEN 'exact_media_id'  THEN 1
                    WHEN 'memory_uuid'     THEN 2
                    WHEN 'memory_uuid_zip' THEN 3
                    WHEN 'story_id'        THEN 4
                    WHEN 'timestamp_type'  THEN 5
                    WHEN 'date_type_count' THEN 6
                    WHEN 'date_only'       THEN 7
                    ELSE 8
                END, m2.id
                LIMIT 1
            )
        )
    """)
    db.commit()

    best_count = db.execute(
        "SELECT COUNT(*) FROM matches WHERE is_best = 1"
    ).fetchone()[0]
    return best_count


# ── Orchestrator ─────────────────────────────────────────────────────────────


def phase2_match(
    db: sqlite3.Connection,
    progress_cb: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Phase 2 orchestrator: Match assets to metadata via priority cascade.

    Clears matches table first (safe to rerun). Runs all 7 strategies,
    selects best match per asset, computes summary statistics.
    """
    t0 = time.time()

    asset_count = db.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
    if asset_count == 0:
        logger.warning("No assets found. Run Phase 1 first.")
        return {}

    # Clear previous matches (idempotent rerun)
    db.execute("DELETE FROM matches")
    db.commit()

    # Log asset breakdown
    type_counts = db.execute(
        "SELECT asset_type, COUNT(*) FROM assets "
        "GROUP BY asset_type ORDER BY COUNT(*) DESC"
    ).fetchall()
    type_str = ", ".join(f"{t}: {c:,}" for t, c in type_counts)
    logger.info("Assets to match: %d (%s)", asset_count, type_str)

    stats: dict[str, Any] = {}

    # Run strategies in priority order (highest precision first)
    strategies = [
        ('exact_media_id', _strategy1_exact_media_id),
        ('memory_uuid', _strategy2_memory_uuid),
        ('story_id', _strategy3_story_id),
        ('memory_uuid_zip', _match_overlay_and_media_zips),
        ('timestamp_type', _strategy4_timestamp_type),
        ('date_type_count', _strategy5_date_type_count),
        ('date_only', _strategy6_date_only),
    ]

    for name, func in strategies:
        count = func(db)
        stats[name] = count
        msg = f"Strategy {name}: {count:,} matches"
        logger.info(msg)
        if progress_cb:
            progress_cb(msg, {
                "verb": "MATCHING YOUR MOMENTS",
                "detail": name, "detail_type": "strategy",
                "current": count, "errors": 0,
            })

    # Select best matches
    stats['best'] = _set_best_matches(db)
    logger.info("Best matches selected: %d", stats['best'])

    # Back-fill chat_message_id for snap-matched files
    stats['backfilled'] = _backfill_chat_message_id(db)
    logger.info("Chat message back-fill: %d", stats['backfilled'])
    if progress_cb:
        progress_cb(f"Best matches selected: {stats['best']:,}", {
            "verb": "MATCHING YOUR MOMENTS",
            "current": stats['best'], "total": stats['best'], "errors": 0,
        })

    elapsed = time.time() - t0

    # Compute summary statistics
    total_matched = db.execute(
        "SELECT COUNT(DISTINCT asset_id) FROM matches WHERE is_best = 1"
    ).fetchone()[0]
    overlay_count = db.execute(
        "SELECT COUNT(*) FROM assets WHERE asset_type = 'memory_overlay'"
    ).fetchone()[0]
    filtered_count = db.execute(
        "SELECT COUNT(*) FROM assets WHERE asset_type IN ('chat_overlay', 'chat_thumbnail')"
    ).fetchone()[0]
    eligible = asset_count - overlay_count - filtered_count
    true_orphans = eligible - total_matched
    match_rate = total_matched / eligible if eligible > 0 else 0.0

    # Confidence distribution
    conf_dist = db.execute("""
        SELECT
            CASE
                WHEN confidence >= 1.0 THEN '1.0 (exact)'
                WHEN confidence >= 0.9 THEN '0.9 (high)'
                WHEN confidence >= 0.8 THEN '0.8 (good)'
                WHEN confidence >= 0.7 THEN '0.7 (fair)'
                WHEN confidence >= 0.3 THEN '0.3 (date-only)'
                ELSE '0.0 (none)'
            END as bucket,
            COUNT(*)
        FROM matches WHERE is_best = 1
        GROUP BY bucket
        ORDER BY confidence DESC
    """).fetchall()

    # Log summary
    logger.info("Phase 2 complete (%.1fs)", elapsed)
    logger.info(
        "Matched: %d / %d eligible (%.1f%%)",
        total_matched, eligible, match_rate * 100,
    )
    logger.info("Overlays: %d, Filtered: %d, Orphans: %d",
                overlay_count, filtered_count, true_orphans)
    if conf_dist:
        logger.info("Confidence distribution:")
        for bucket, cnt in conf_dist:
            logger.info("  %-30s %6d", bucket, cnt)

    if progress_cb:
        progress_cb(
            f"Phase 2 complete: {total_matched:,}/{eligible:,} matched "
            f"({match_rate:.1%}) in {elapsed:.1f}s"
        )

    stats['total_matched'] = total_matched
    stats['true_orphans'] = true_orphans
    stats['overlays'] = overlay_count
    stats['filtered'] = filtered_count
    stats['eligible'] = eligible
    stats['match_rate'] = match_rate
    stats['elapsed'] = elapsed

    return stats
