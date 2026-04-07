"""Phase 3: Enrich all best matches with GPS, display names, output paths, and EXIF tags.

Ported from snatched.py v2 lines 1652-2288 with v3 adaptations:
- print() → logger / progress_cb
- GPS_WINDOW constant → gps_window parameter
- args object → Config
- Returns dicts instead of tuples
"""

import json
import logging
import sqlite3
import time
from bisect import bisect_left
from pathlib import Path
from typing import Callable

from snatched.config import Config
from snatched.utils import (
    UUID_RE,
    VERSION,
    date_tags,
    format_chat_date,
    gps_tags,
    parse_iso_dt,
    parse_snap_date,
    sanitize_filename,
)

logger = logging.getLogger(__name__)

BATCH_SIZE = 500


# ── GPS Enrichment ──────────────────────────────────────────────────────────


def load_location_timeline(
    db: sqlite3.Connection,
) -> tuple[list[int], list[float], list[float]]:
    """Load all location breadcrumbs sorted by timestamp_unix.

    Returns three parallel lists for binary search:
        (timestamps_unix, latitudes, longitudes)

    Returns empty lists if no location data exists.
    """
    rows = db.execute(
        "SELECT timestamp_unix, lat, lon FROM locations "
        "ORDER BY timestamp_unix ASC"
    ).fetchall()
    if not rows:
        return [], [], []
    timestamps = [r[0] for r in rows]
    lats = [r[1] for r in rows]
    lons = [r[2] for r in rows]
    return timestamps, lats, lons


def find_nearest_location(
    target_unix: int,
    timestamps: list[int],
    lats: list[float],
    lons: list[float],
    gps_window: int = 300,
) -> tuple[float, float] | None:
    """Binary search for nearest GPS location within time window.

    Uses bisect_left to find insertion point, then checks ±1 neighbors.

    Args:
        target_unix: Target timestamp (seconds since epoch)
        timestamps: Sorted list of GPS timestamps
        lats: Parallel list of latitudes
        lons: Parallel list of longitudes
        gps_window: Maximum allowed time difference in seconds (default 300)

    Returns:
        (lat, lon) if a match within window is found, None otherwise.
    """
    if not timestamps:
        return None
    idx = bisect_left(timestamps, target_unix)
    best_dist = gps_window + 1
    best_idx = None
    for i in (idx - 1, idx):
        if 0 <= i < len(timestamps):
            dist = abs(timestamps[i] - target_unix)
            if dist < best_dist:
                best_dist = dist
                best_idx = i
    if best_idx is not None and best_dist <= gps_window:
        return lats[best_idx], lons[best_idx]
    return None


def enrich_gps(
    db: sqlite3.Connection,
    timestamps: list[int],
    lats: list[float],
    lons: list[float],
    gps_window: int = 300,
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    """Enrich GPS for all best matches using two-pass strategy.

    Pass 1: Copy GPS from memory metadata (memories.lat/lon → matches).
    Pass 2: Binary search location timeline for matches still missing GPS.

    Returns:
        {'memory_gps': int, 'location_gps': int, 'no_gps': int, 'elapsed': float}
    """
    t0 = time.time()

    if progress_cb:
        progress_cb("Enriching GPS coordinates...", {
            "verb": "FINDING WHERE YOU WERE", "errors": 0,
        })

    # Pass 1: GPS from memory metadata
    mem_updates = db.execute("""
        SELECT m.id, mem.lat, mem.lon
        FROM matches m
        JOIN memories mem ON m.memory_id = mem.id
        WHERE m.is_best = 1
          AND m.memory_id IS NOT NULL
          AND mem.lat IS NOT NULL
          AND mem.lon IS NOT NULL
          AND NOT (mem.lat = 0.0 AND mem.lon = 0.0)
    """).fetchall()

    mem_gps_count = 0
    batch = []
    for match_id, lat, lon in mem_updates:
        batch.append((lat, lon, 'metadata', match_id))
        mem_gps_count += 1
        if len(batch) >= BATCH_SIZE:
            db.executemany(
                "UPDATE matches SET matched_lat=?, matched_lon=?, gps_source=? "
                "WHERE id=?", batch)
            batch = []
    if batch:
        db.executemany(
            "UPDATE matches SET matched_lat=?, matched_lon=?, gps_source=? "
            "WHERE id=?", batch)
    db.commit()

    # GPS showstopper: emit a sample memory location for the terminal display
    if mem_gps_count > 0 and progress_cb:
        sample = db.execute("""
            SELECT mem.lat, mem.lon, mem.location_raw
            FROM matches m
            JOIN memories mem ON m.memory_id = mem.id
            WHERE m.is_best = 1 AND mem.lat IS NOT NULL
              AND mem.location_raw IS NOT NULL AND mem.location_raw != ''
            LIMIT 1
        """).fetchone()
        if sample:
            progress_cb(f"GPS: {mem_gps_count} from memory metadata", {
                "verb": "FINDING WHERE YOU WERE",
                "gps_lat": sample[0], "gps_lon": sample[1],
                "location_name": sample[2],
                "current": mem_gps_count, "errors": 0,
            })

    # Pass 2: GPS from location history (binary search)
    loc_gps_count = 0
    if timestamps:
        no_gps_rows = db.execute("""
            SELECT m.id, m.matched_date
            FROM matches m
            WHERE m.is_best = 1
              AND m.matched_lat IS NULL
              AND m.matched_date IS NOT NULL
        """).fetchall()

        batch = []
        for match_id, matched_date in no_gps_rows:
            dt = parse_iso_dt(matched_date)
            if not dt:
                continue
            target_unix = dt.timestamp()
            result = find_nearest_location(
                target_unix, timestamps, lats, lons, gps_window)
            if result:
                lat, lon = result
                batch.append((lat, lon, 'location_history', match_id))
                loc_gps_count += 1
                # GPS showstopper: emit coords every 50 finds
                if loc_gps_count % 50 == 0 and progress_cb:
                    progress_cb(f"GPS: {mem_gps_count + loc_gps_count} tagged", {
                        "verb": "FINDING WHERE YOU WERE",
                        "gps_lat": lat, "gps_lon": lon,
                        "current": mem_gps_count + loc_gps_count, "errors": 0,
                    })
                if len(batch) >= BATCH_SIZE:
                    db.executemany(
                        "UPDATE matches SET matched_lat=?, matched_lon=?, "
                        "gps_source=? WHERE id=?", batch)
                    batch = []
        if batch:
            db.executemany(
                "UPDATE matches SET matched_lat=?, matched_lon=?, "
                "gps_source=? WHERE id=?", batch)
        db.commit()

    no_gps = db.execute("""
        SELECT COUNT(*) FROM matches m
        JOIN assets a ON m.asset_id = a.id
        WHERE m.is_best = 1 AND a.asset_type = 'memory_main'
          AND m.matched_lat IS NULL
    """).fetchone()[0]

    elapsed = time.time() - t0
    logger.info(
        f"GPS enrichment: memory={mem_gps_count}, "
        f"location_history={loc_gps_count}, no_gps={no_gps} ({elapsed:.1f}s)"
    )

    if progress_cb:
        total_gps = mem_gps_count + loc_gps_count
        progress_cb(
            f"GPS: {mem_gps_count} from metadata, "
            f"{loc_gps_count} from location history, {no_gps} without",
            {"verb": "FINDING WHERE YOU WERE",
             "current": total_gps, "total": total_gps + no_gps, "errors": 0},
        )

    return {
        'memory_gps': mem_gps_count,
        'location_gps': loc_gps_count,
        'no_gps': no_gps,
        'elapsed': elapsed,
    }


# ── Display Name Resolution ────────────────────────────────────────────────


def resolve_conversation_name(
    conv_title: str | None,
    conv_id: str,
    friends_map: dict[str, str],
    from_user: str | None = None,
) -> str:
    """Determine human-readable conversation name with fallback chain.

    Fallback order:
    1. conv_title if non-empty
    2. friends_map[conv_id] if conv_id is not a UUID
    3. conv_id itself if not a UUID
    4. friends_map[from_user] if from_user is known
    5. from_user as-is if provided
    6. 'Unknown'
    """
    if conv_title and conv_title.strip():
        return sanitize_filename(conv_title.strip())

    if conv_id and not UUID_RE.match(conv_id):
        display = friends_map.get(conv_id)
        if display:
            return sanitize_filename(display)
        return sanitize_filename(conv_id)

    # UUID conv_id with no title: try the partner's display name
    if from_user:
        display = friends_map.get(from_user)
        if display:
            return sanitize_filename(display)
        return sanitize_filename(from_user)

    return 'Unknown'


def build_chat_folder_map(db: sqlite3.Connection) -> dict[str, str]:
    """Build conversation_id → rich folder name mapping.

    For each conversation, determines the best human-readable name
    incorporating display names, partner usernames, and year ranges.
    Deduplicates by appending _2, _3, etc.

    Returns:
        dict: {conversation_id: folder_name}
    """
    friends = {}
    for row in db.execute("SELECT username, display_name FROM friends"):
        friends[row[0]] = row[1] if row[1] else None

    conversations = db.execute("""
        SELECT conversation_id, MAX(conversation_title) AS conversation_title
        FROM (
            SELECT conversation_id, conversation_title FROM chat_messages
            UNION ALL
            SELECT conversation_id, conversation_title FROM snap_messages
        )
        GROUP BY conversation_id
        ORDER BY conversation_id
    """).fetchall()

    used_filenames = set()
    folder_map = {}

    for conv_id, conv_title in conversations:
        messages = db.execute("""
            SELECT from_user, media_type, content, created, created_ms,
                   is_sender, conversation_title
            FROM chat_messages WHERE conversation_id = ?
            UNION ALL
            SELECT from_user, media_type, NULL AS content, created, created_ms,
                   is_sender, conversation_title
            FROM snap_messages WHERE conversation_id = ?
            ORDER BY created_ms ASC NULLS LAST, created ASC
        """, (conv_id, conv_id)).fetchall()

        if not messages:
            continue

        # Try to get a display title from messages if the top-level one is empty
        display_title = conv_title
        if not display_title:
            for msg in messages:
                if msg[6]:  # conversation_title field
                    display_title = msg[6]
                    break

        # Determine partner info
        partner_username = None
        partner_display = None
        has_uuid_id = bool(UUID_RE.match(conv_id))
        if not has_uuid_id:
            partner_username = conv_id
            partner_display = friends.get(conv_id)

        # Collect distinct non-sender participants
        other_users = []
        other_users_set = set()
        for msg in messages:
            u = msg[0]  # from_user
            if u and not msg[5] and u not in other_users_set:  # not is_sender
                other_users_set.add(u)
                other_users.append(u)

        is_group_chat = has_uuid_id and len(other_users) > 1

        if not partner_username and other_users:
            partner_username = other_users[0]
            partner_display = friends.get(other_users[0])

        # Build synthetic group name if needed
        group_synthetic_name = None
        if is_group_chat and not display_title:
            seen = [friends.get(u) or u for u in other_users]
            if seen:
                MAX_NAMES = 3
                if len(seen) <= MAX_NAMES:
                    names_str = ', '.join(seen)
                else:
                    names_str = ', '.join(seen[:MAX_NAMES]) + ', ...'
                group_synthetic_name = 'Group - ' + names_str

        # Compute year range
        first_year = None
        last_year = None
        for msg in messages:
            if msg[3]:  # created
                dt_str = format_chat_date(msg[3])
                if dt_str:
                    if not first_year:
                        first_year = dt_str[:4]
                    last_year = dt_str[:4]

        if first_year and last_year:
            yr_range = f" {first_year}-{last_year}" if first_year != last_year else f" {first_year}"
        else:
            yr_range = ''

        # Build final folder name
        if is_group_chat:
            if display_title:
                safe_name = sanitize_filename(display_title + yr_range)
            elif group_synthetic_name:
                safe_name = sanitize_filename(group_synthetic_name + yr_range)
            else:
                safe_name = sanitize_filename('Group' + yr_range)
        else:
            assigned = display_title.strip() if display_title and display_title.strip() else None
            if not assigned:
                assigned = partner_display
            un = partner_username or ''
            if assigned and un:
                safe_name = sanitize_filename(f"{assigned} - {un}{yr_range}")
            elif assigned:
                safe_name = sanitize_filename(f"{assigned}{yr_range}")
            elif un:
                safe_name = sanitize_filename(f"{un}{yr_range}")
            else:
                safe_name = sanitize_filename('Unknown' + yr_range)

        # Deduplicate
        base_name = safe_name
        if safe_name in used_filenames:
            suffix = 2
            while f"{base_name}_{suffix}" in used_filenames:
                suffix += 1
            safe_name = f"{base_name}_{suffix}"
        used_filenames.add(safe_name)

        folder_map[conv_id] = safe_name

    return folder_map


def enrich_display_names(
    db: sqlite3.Connection,
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    """Resolve display names for chat/snap matches from friends table.

    For each best match linked to a chat_message or snap_message:
    - display_name: friend's display_name, or username fallback
    - creator_str: 'Display Name (@username)' or '@username'
    - direction: 'sent' or 'received'
    - conversation: resolved name from resolve_conversation_name()

    Returns:
        {'resolved': int, 'elapsed': float}
    """
    t0 = time.time()

    if progress_cb:
        progress_cb("Resolving display names...", {
            "verb": "REMEMBERING WHO YOU WERE WITH", "errors": 0,
        })

    friends = {}
    for row in db.execute("SELECT username, display_name FROM friends"):
        friends[row[0]] = row[1] if row[1] else None

    rows = db.execute("""
        SELECT m.id, m.chat_message_id, m.snap_message_id
        FROM matches m
        WHERE m.is_best = 1
          AND (m.chat_message_id IS NOT NULL OR m.snap_message_id IS NOT NULL)
    """).fetchall()

    batch = []
    resolved = 0

    for match_id, chat_msg_id, snap_msg_id in rows:
        from_user = None
        is_sender = 0
        conv_id = None
        conv_title = None

        if chat_msg_id is not None:
            msg = db.execute(
                "SELECT from_user, is_sender, conversation_id, "
                "conversation_title FROM chat_messages WHERE id=?",
                (chat_msg_id,)).fetchone()
            if msg:
                from_user, is_sender, conv_id, conv_title = msg

        elif snap_msg_id is not None:
            msg = db.execute(
                "SELECT from_user, is_sender, conversation_id, "
                "conversation_title FROM snap_messages WHERE id=?",
                (snap_msg_id,)).fetchone()
            if msg:
                from_user, is_sender, conv_id, conv_title = msg

        if not from_user:
            continue

        display = friends.get(from_user)
        display_name = display if display else from_user

        if display:
            creator_str = f"{display} (@{from_user})"
        else:
            creator_str = f"@{from_user}"

        direction = 'sent' if is_sender else 'received'

        conversation = resolve_conversation_name(
            conv_title, conv_id, friends, from_user=from_user)

        batch.append((
            display_name, creator_str, direction, conversation, match_id))
        resolved += 1

        if len(batch) >= BATCH_SIZE:
            db.executemany(
                "UPDATE matches SET display_name=?, creator_str=?, "
                "direction=?, conversation=? WHERE id=?", batch)
            batch = []

    if batch:
        db.executemany(
            "UPDATE matches SET display_name=?, creator_str=?, "
            "direction=?, conversation=? WHERE id=?", batch)
    db.commit()

    elapsed = time.time() - t0
    logger.info(f"Display names: {resolved} resolved ({elapsed:.1f}s)")

    if progress_cb:
        progress_cb(f"Display names: {resolved} files matched to contact names", {
            "verb": "REMEMBERING WHO YOU WERE WITH",
            "current": resolved, "total": resolved, "errors": 0,
        })

    return {'resolved': resolved, 'elapsed': elapsed}


# ── Output Path Computation ─────────────────────────────────────────────────


def enrich_output_paths(
    db: sqlite3.Connection,
    config: Config,
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    """Compute output_subdir and output_filename for every best match.

    Path structure by asset type:
    - memory_main/overlay: memories/{YYYY}/{MM}/Snap_Memory_{date}_{time}{ext}
    - chat: chat/{CONVERSATION}/Media/Snap_Chat_{date}_{time}{ext}
    - story: stories/Snap_Story_{date}_{time}{ext}
    - unmatched: unmatched/Snap_{type}_{stem}{ext}

    Returns:
        {'computed': int, 'elapsed': float}
    """
    t0 = time.time()

    if progress_cb:
        progress_cb("Computing output paths...", {
            "verb": "ORGANIZING YOUR MEMORIES", "errors": 0,
        })

    # Determine folder style from config
    mem_lane = config.lanes.get('memories')
    folder_style = mem_lane.folder_pattern if mem_lane else 'year_month'
    if folder_style not in ('year_month', 'year', 'flat', 'type'):
        folder_style = 'year_month'

    # Build conversation folder map for chat assets
    chat_folder_map = build_chat_folder_map(db)

    # Build reverse lookup: message_id → conversation_id
    _conv_id_cache = {}
    for row in db.execute(
            "SELECT id, conversation_id FROM chat_messages"):
        _conv_id_cache[('chat', row[0])] = row[1]
    for row in db.execute(
            "SELECT id, conversation_id FROM snap_messages"):
        _conv_id_cache[('snap', row[0])] = row[1]

    rows = db.execute("""
        SELECT m.id, m.matched_date, m.conversation, m.memory_id,
               m.chat_message_id, m.snap_message_id, m.story_id,
               a.asset_type, a.ext, a.real_ext, a.filename, a.file_id,
               a.memory_uuid
        FROM matches m
        JOIN assets a ON m.asset_id = a.id
        WHERE m.is_best = 1
    """).fetchall()

    used_names = {}
    batch = []
    computed = 0

    for row in rows:
        (match_id, matched_date, conversation, memory_id,
         chat_msg_id, snap_msg_id, story_id,
         asset_type, ext, real_ext, orig_filename, file_id,
         memory_uuid) = row

        out_ext = real_ext if real_ext else ext

        dt = parse_iso_dt(matched_date)
        if dt:
            yyyy = dt.strftime('%Y')
            mm = dt.strftime('%m')
            time_str = dt.strftime('%H%M%S')
            date_str = dt.strftime('%Y-%m-%d')
        else:
            yyyy = 'Unknown'
            mm = '00'
            time_str = '000000'
            date_str = 'Unknown'

        if asset_type in ('memory_main', 'memory_overlay'):
            if folder_style == 'flat':
                subdir = "memories"
            elif folder_style == 'year':
                subdir = f"memories/{yyyy}"
            elif folder_style == 'type':
                subdir = "memories/Photos" if not (real_ext and real_ext.lower() in ('.mp4', '.mov', '.avi')) else "memories/Videos"
            else:  # year_month
                subdir = f"memories/{yyyy}/{mm}"
            base = f"Snap_Memory_{date_str}_{time_str}"

        elif asset_type == 'chat':
            if matched_date and (chat_msg_id or snap_msg_id):
                # Look up conversation_id, then use the rich folder map
                cid = None
                if chat_msg_id is not None:
                    cid = _conv_id_cache.get(('chat', chat_msg_id))
                if cid is None and snap_msg_id is not None:
                    cid = _conv_id_cache.get(('snap', snap_msg_id))
                conv_name = chat_folder_map.get(cid) if cid else None
                if not conv_name:
                    conv_name = conversation if conversation else 'Unknown'
                subdir = f"chat/{conv_name}/Media"
                base = f"Snap_Chat_{date_str}_{time_str}"
            elif matched_date:
                subdir = "chat/Unmatched/Media"
                base = f"Snap_Chat_{date_str}_{time_str}"
            else:
                subdir = "chat/Unmatched/Media"
                base = f"Snap_Chat_{orig_filename.rsplit('.', 1)[0]}"

        elif asset_type == 'story':
            if folder_style == 'year_month':
                subdir = f"stories/{yyyy}/{mm}"
            elif folder_style == 'year':
                subdir = f"stories/{yyyy}"
            elif folder_style == 'type':
                subdir = "stories"
            else:  # flat
                subdir = "stories"
            base = f"Snap_Story_{date_str}_{time_str}"

        else:
            subdir = "unmatched"
            stem = orig_filename.rsplit('.', 1)[0] if '.' in orig_filename \
                else orig_filename
            base = f"Snap_{asset_type}_{stem}"

        # Handle filename collisions
        filename = f"{base}{out_ext}"
        if subdir not in used_names:
            used_names[subdir] = set()

        if filename in used_names[subdir]:
            suffix = 2
            while f"{base}_{suffix}{out_ext}" in used_names[subdir]:
                suffix += 1
            filename = f"{base}_{suffix}{out_ext}"

        used_names[subdir].add(filename)

        batch.append((subdir, filename, match_id))
        computed += 1

        if len(batch) >= BATCH_SIZE:
            db.executemany(
                "UPDATE matches SET output_subdir=?, output_filename=? "
                "WHERE id=?", batch)
            batch = []

    if batch:
        db.executemany(
            "UPDATE matches SET output_subdir=?, output_filename=? "
            "WHERE id=?", batch)
    db.commit()

    elapsed = time.time() - t0
    logger.info(f"Output paths: {computed} computed ({elapsed:.1f}s)")

    if progress_cb:
        progress_cb(f"Output paths: {computed} computed", {
            "verb": "ORGANIZING YOUR MEMORIES",
            "current": computed, "total": computed, "errors": 0,
        })

    return {'computed': computed, 'elapsed': elapsed}


# ── EXIF Tag Building ───────────────────────────────────────────────────────


def enrich_exif_tags(
    db: sqlite3.Connection,
    config: Config,
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    """Build exif_tags_json for every best match.

    Constructs EXIF tag dict combining date, GPS, creator, conversation,
    and identification tags. Stores as JSON in matches.exif_tags_json.

    Returns:
        {'built': int, 'with_gps': int, 'with_date': int, 'elapsed': float}
    """
    t0 = time.time()

    if progress_cb:
        progress_cb("Building EXIF metadata tags...", {
            "verb": "STAMPING YOUR MEMORIES", "errors": 0,
        })

    # Read GPS precision and hide_sent_to from config
    _any_lane = config.lanes.get('memories') or config.lanes.get('chats') or config.lanes.get('stories')
    gps_precision = _any_lane.gps_precision if _any_lane else 'exact'
    hide_sent_to = _any_lane.hide_sent_to if _any_lane else False

    rows = db.execute("""
        SELECT m.id, m.matched_date, m.matched_lat, m.matched_lon,
               m.gps_source, m.display_name, m.creator_str, m.direction,
               m.conversation, m.memory_id, m.chat_message_id,
               m.snap_message_id, m.story_id,
               a.asset_type, a.is_video, a.ext, a.real_ext,
               a.memory_uuid, a.file_id,
               mem.location_raw
        FROM matches m
        JOIN assets a ON m.asset_id = a.id
        LEFT JOIN memories mem ON m.memory_id = mem.id
        WHERE m.is_best = 1
    """).fetchall()

    # Build accuracy cache: for location_history GPS, find nearest accuracy_m
    accuracy_cache = {}
    try:
        acc_rows = db.execute(
            "SELECT timestamp_unix, accuracy_m FROM locations "
            "WHERE accuracy_m IS NOT NULL ORDER BY timestamp_unix"
        ).fetchall()
        if acc_rows:
            _acc_ts = [r[0] for r in acc_rows]
            _acc_vals = [r[1] for r in acc_rows]
            accuracy_cache = {'ts': _acc_ts, 'vals': _acc_vals}
    except Exception:
        pass

    # Caches for subsecond lookups
    chat_us_cache = {}
    snap_us_cache = {}

    batch = []
    built = 0

    for row in rows:
        (match_id, matched_date, matched_lat, matched_lon,
         gps_source, display_name, creator_str, direction,
         conversation, memory_id, chat_msg_id, snap_msg_id, story_id,
         asset_type, is_video_flag, ext, real_ext, memory_uuid, file_id,
         location_raw) = row

        vid = bool(is_video_flag)
        tags = {}

        tags['Software'] = f'Snatched v{VERSION}'

        if asset_type in ('memory_main', 'memory_overlay'):
            tags['ImageDescription'] = 'Snapchat Memory'
        elif asset_type == 'chat':
            tags['ImageDescription'] = 'Snapchat Chat'
        elif asset_type == 'story':
            tags['ImageDescription'] = 'Snapchat Shared Story'
        else:
            tags['ImageDescription'] = 'Snapchat Media'

        # Date tags with subsecond precision
        dt = parse_iso_dt(matched_date)
        if dt:
            subsec_ms = None
            if chat_msg_id:
                if chat_msg_id not in chat_us_cache:
                    r = db.execute(
                        "SELECT created_ms FROM chat_messages WHERE id=?",
                        (chat_msg_id,)).fetchone()
                    chat_us_cache[chat_msg_id] = r[0] if r else None
                us = chat_us_cache[chat_msg_id]
                if us is not None:
                    subsec_ms = (us // 1000) % 1000
            elif snap_msg_id:
                if snap_msg_id not in snap_us_cache:
                    r = db.execute(
                        "SELECT created_ms FROM snap_messages WHERE id=?",
                        (snap_msg_id,)).fetchone()
                    snap_us_cache[snap_msg_id] = r[0] if r else None
                us = snap_us_cache[snap_msg_id]
                if us is not None:
                    subsec_ms = (us // 1000) % 1000

            tags.update(date_tags(dt, is_video=vid, subsec_ms=subsec_ms))

        # GPS tags
        if matched_lat is not None and matched_lon is not None and gps_precision != 'none':
            _lat = matched_lat
            _lon = matched_lon
            if gps_precision == 'city':
                _lat = round(matched_lat, 2)
                _lon = round(matched_lon, 2)
            tags.update(gps_tags(_lat, _lon, is_video=vid, dt=dt))

            # GPS accuracy (from location_history source)
            if gps_source == 'location_history' and accuracy_cache and dt:
                target_unix = dt.timestamp()
                _ts = accuracy_cache['ts']
                idx = bisect_left(_ts, target_unix)
                best_acc = None
                for ci in (idx - 1, idx):
                    if 0 <= ci < len(_ts):
                        if abs(_ts[ci] - target_unix) <= 300:
                            acc = accuracy_cache['vals'][ci]
                            if best_acc is None or abs(_ts[ci] - target_unix) < abs(_ts[best_acc[1]] - target_unix):
                                best_acc = (acc, ci)
                if best_acc:
                    tags['GPSHPositioningError'] = str(best_acc[0])

            # Location name (human-readable place from Snapchat)
            if location_raw:
                tags['IPTC:City'] = location_raw
                tags['XMP-photoshop:City'] = location_raw
        else:
            tags['UserComment'] = 'GPS: no coordinates found in Snapchat location history'

        # Chat-specific tags
        if asset_type == 'chat' and (chat_msg_id or snap_msg_id):
            if creator_str and not hide_sent_to:
                tags['XMP:Creator'] = creator_str
            if direction and not hide_sent_to:
                desc = 'Sent' if direction == 'sent' else 'Received'
                tags['XMP:Description'] = desc
            if conversation and not hide_sent_to:
                tags['XMP:Subject'] = conversation
            if file_id:
                tags['ImageUniqueID'] = file_id

        # Memory-specific tags
        if asset_type in ('memory_main', 'memory_overlay'):
            if memory_uuid:
                tags['ImageUniqueID'] = memory_uuid
            if vid:
                tags['XMP:Software'] = f'Snatched v{VERSION}'

        # Story-specific tags
        if asset_type == 'story' and file_id:
            tags['ImageUniqueID'] = file_id

        batch.append((json.dumps(tags, ensure_ascii=False), match_id))
        built += 1

        if len(batch) >= BATCH_SIZE:
            db.executemany(
                "UPDATE matches SET exif_tags_json=? WHERE id=?", batch)
            batch = []

    if batch:
        db.executemany(
            "UPDATE matches SET exif_tags_json=? WHERE id=?", batch)
    db.commit()

    elapsed = time.time() - t0

    with_gps = db.execute(
        "SELECT COUNT(*) FROM matches WHERE is_best=1 AND matched_lat IS NOT NULL"
    ).fetchone()[0]
    with_date = db.execute(
        "SELECT COUNT(*) FROM matches WHERE is_best=1 AND matched_date IS NOT NULL"
    ).fetchone()[0]

    logger.info(
        f"EXIF tags: {built} built, {with_gps} with GPS, "
        f"{with_date} with date ({elapsed:.1f}s)"
    )

    if progress_cb:
        progress_cb(f"EXIF tags: {built} prepared ({with_gps} with GPS)", {
            "verb": "STAMPING YOUR MEMORIES",
            "current": built, "total": built, "errors": 0,
        })

    return {
        'built': built,
        'with_gps': with_gps,
        'with_date': with_date,
        'elapsed': elapsed,
    }


# ── Phase 3 Orchestrator ───────────────────────────────────────────────────


def phase3_enrich(
    db: sqlite3.Connection,
    project_dir: Path,
    config: Config,
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    """Phase 3 orchestrator: Enrich all best matches.

    Sequentially calls:
    1. load_location_timeline()
    2. enrich_gps()
    3. enrich_display_names()
    4. enrich_output_paths()
    5. enrich_exif_tags()

    Returns combined stats dict.
    """
    t0 = time.time()

    if progress_cb:
        progress_cb("Starting Phase 3: Enrich...")

    total_best = db.execute(
        "SELECT COUNT(*) FROM matches WHERE is_best = 1").fetchone()[0]
    if total_best == 0:
        logger.warning("No best matches found. Run Phase 2 first.")
        if progress_cb:
            progress_cb("Phase 3: No best matches found")
        return {'total': 0}

    logger.info(f"Phase 3: {total_best} best matches to enrich")

    gps_window = config.pipeline.gps_window_seconds

    timestamps, loc_lats, loc_lons = load_location_timeline(db)
    gps_stats = enrich_gps(
        db, timestamps, loc_lats, loc_lons, gps_window, progress_cb)

    name_stats = enrich_display_names(db, progress_cb)

    path_stats = enrich_output_paths(db, config, progress_cb)

    tag_stats = enrich_exif_tags(db, config, progress_cb)

    elapsed = time.time() - t0

    stats = {
        'total': total_best,
        'gps_metadata': gps_stats['memory_gps'],
        'gps_location_history': gps_stats['location_gps'],
        'gps_none': gps_stats['no_gps'],
        'names_resolved': name_stats['resolved'],
        'paths_computed': path_stats['computed'],
        'tags_built': tag_stats['built'],
        'elapsed': elapsed,
    }

    logger.info(
        f"Phase 3 complete in {elapsed:.1f}s: "
        f"GPS meta={gps_stats['memory_gps']}, "
        f"GPS loc={gps_stats['location_gps']}, "
        f"names={name_stats['resolved']}, "
        f"paths={path_stats['computed']}, "
        f"tags={tag_stats['built']}"
    )

    if progress_cb:
        progress_cb(f"Phase 3 complete: {total_best} matches enriched in {elapsed:.1f}s")

    return stats
