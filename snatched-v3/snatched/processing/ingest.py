"""Phase 1: Ingest all Snapchat export data into the per-user SQLite database.

Parses 8 JSON source files and discovers all media files on disk.
Each function is independently testable. Progress is reported via optional callback.

Ported from snatched.py v2 lines 501-1247, 3534-3773.
"""

import json
import logging
import re
import time
import zipfile
from pathlib import Path
from typing import Callable
import sqlite3

from snatched.utils import (
    MEMORY_RE, CHAT_FILE_RE,
    parse_snap_date, parse_snap_date_iso, parse_snap_date_dateonly,
    parse_location, extract_mid, is_video,
    detect_real_format, is_fragmented_mp4, sha256_file,
)
from snatched.processing.sqlite import BATCH_SIZE

logger = logging.getLogger(__name__)


# ── JSON Ingest Functions ────────────────────────────────────────────────────


def ingest_memories(
    db: sqlite3.Connection,
    json_dir: Path,
    progress_cb: Callable[[str], None] | None = None,
) -> int:
    """Parse memories_history.json -> memories table.

    Extracts mid from Download Link URL query parameter.
    Returns count of memories in the table after insert.
    """
    path = json_dir / 'memories_history.json'
    if not path.exists():
        logger.warning("memories_history.json not found in %s", json_dir)
        return 0

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    entries = data.get('Saved Media', [])
    rows = []
    skipped = 0

    for entry in entries:
        dl_link = entry.get('Download Link', '')
        mid = extract_mid(dl_link)
        if not mid:
            mid = extract_mid(entry.get('Media Download Url', ''))
        if not mid:
            skipped += 1
            continue

        date_raw = entry.get('Date', '')
        date_dt = parse_snap_date_iso(date_raw)
        media_type = entry.get('Media Type', '')
        location_raw = entry.get('Location', '')
        loc = parse_location(location_raw)
        lat = loc[0] if loc else None
        lon = loc[1] if loc else None

        rows.append((
            mid, date_raw, date_dt, media_type,
            location_raw, lat, lon, dl_link
        ))

    # Batch insert
    sql = """INSERT OR IGNORE INTO memories
             (mid, date, date_dt, media_type, location_raw, lat, lon, download_link)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?)"""
    count_before = db.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        db.executemany(sql, batch)
    db.commit()

    count = db.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    gps_count = db.execute(
        "SELECT COUNT(*) FROM memories WHERE lat IS NOT NULL"
    ).fetchone()[0]

    if progress_cb:
        progress_cb(f"{count:,} memories ingested ({gps_count:,} with GPS)")
    logger.info("%d memories ingested (%d with GPS)", count, gps_count)
    if skipped:
        logger.warning("%d entries skipped (no mid)", skipped)
    return count


def ingest_chat(
    db: sqlite3.Connection,
    json_dir: Path,
    progress_cb: Callable[[str], None] | None = None,
) -> int:
    """Parse chat_history.json -> chat_messages + chat_media_ids tables.

    Ingests ALL message types (not just MEDIA -- fixes v1 bug).
    Explodes pipe-separated Media IDs into chat_media_ids for Phase 2.
    """
    path = json_dir / 'chat_history.json'
    if not path.exists():
        logger.warning("chat_history.json not found in %s", json_dir)
        return 0

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    msg_rows = []
    total_convs = 0

    for conv_id, messages in data.items():
        if not isinstance(messages, list):
            continue
        total_convs += 1

        for msg in messages:
            created_raw = msg.get('Created', '')
            created_dt = parse_snap_date_iso(created_raw)
            created_date = parse_snap_date_dateonly(created_raw)
            created_ms = msg.get('Created(microseconds)')

            is_sender_raw = msg.get('IsSender', False)
            is_sender = 1 if is_sender_raw in (True, 'true', 'True', 1) else 0

            # Media IDs: sometimes pipe-separated string, sometimes JSON array
            raw_mids = msg.get('Media IDs', '')
            if isinstance(raw_mids, list):
                raw_mids = ' | '.join(str(m) for m in raw_mids if m)

            msg_rows.append((
                conv_id,
                msg.get('From', ''),
                msg.get('Media Type', ''),
                raw_mids,
                msg.get('Content', ''),
                created_raw,
                created_ms,
                is_sender,
                msg.get('Conversation Title', ''),
                created_dt,
                created_date,
            ))

    # Batch insert messages
    sql = """INSERT INTO chat_messages
             (conversation_id, from_user, media_type, media_ids, content,
              created, created_ms, is_sender, conversation_title,
              created_dt, created_date)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
    for i in range(0, len(msg_rows), BATCH_SIZE):
        batch = msg_rows[i:i + BATCH_SIZE]
        db.executemany(sql, batch)
    db.commit()

    # Explode pipe-separated Media IDs into chat_media_ids
    cursor = db.execute(
        "SELECT id, media_ids FROM chat_messages "
        "WHERE media_ids IS NOT NULL AND media_ids != ''"
    )
    mid_rows = []
    for row in cursor.fetchall():
        msg_id, media_ids_str = row
        for mid in media_ids_str.split('|'):
            mid = mid.strip()
            if mid:
                mid_rows.append((msg_id, mid))

    mid_sql = "INSERT INTO chat_media_ids (chat_message_id, media_id) VALUES (?, ?)"
    for i in range(0, len(mid_rows), BATCH_SIZE):
        batch = mid_rows[i:i + BATCH_SIZE]
        db.executemany(mid_sql, batch)
    db.commit()

    msg_count = db.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0]
    mid_count = db.execute("SELECT COUNT(*) FROM chat_media_ids").fetchone()[0]
    media_msgs = db.execute(
        "SELECT COUNT(*) FROM chat_messages "
        "WHERE media_ids IS NOT NULL AND media_ids != ''"
    ).fetchone()[0]

    if progress_cb:
        progress_cb(
            f"{msg_count:,} messages from {total_convs} conversations, "
            f"{mid_count:,} media IDs exploded"
        )
    logger.info(
        "%d messages from %d conversations, %d media IDs exploded",
        msg_count, total_convs, mid_count,
    )
    return msg_count


def ingest_snaps(
    db: sqlite3.Connection,
    json_dir: Path,
    progress_cb: Callable[[str], None] | None = None,
) -> int:
    """Parse snap_history.json -> snap_messages table.

    Filters to IMAGE/VIDEO only. Deduplicates multi-recipient snaps
    using composite key: (timestamp_ms // 100) | sender | media_type.
    """
    path = json_dir / 'snap_history.json'
    if not path.exists():
        logger.warning("snap_history.json not found in %s", json_dir)
        return 0

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    rows = []

    for conv_id, messages in data.items():
        if not isinstance(messages, list):
            continue

        for msg in messages:
            created_raw = msg.get('Created', '')
            created_ms = msg.get('Created(microseconds)')
            mtype = msg.get('Media Type', '').upper()
            from_user = msg.get('From', '')

            if mtype not in ('IMAGE', 'VIDEO'):
                continue

            if created_ms is not None:
                bucket = created_ms // 100
                dedup_key = f"{bucket}|{from_user}|{mtype}"
            else:
                dedup_key = f"{created_raw}|{from_user}|{mtype}"

            created_dt = parse_snap_date_iso(created_raw)
            created_date = parse_snap_date_dateonly(created_raw)
            is_sender_raw = msg.get('IsSender', False)
            is_sender = 1 if is_sender_raw in (True, 'true', 'True', 1) else 0

            rows.append((
                conv_id,
                from_user,
                mtype,
                created_raw,
                created_ms,
                is_sender,
                msg.get('Conversation Title', ''),
                created_dt,
                created_date,
                dedup_key,
            ))

    # Batch insert (INSERT OR IGNORE handles dedup via UNIQUE dedup_key)
    sql = """INSERT OR IGNORE INTO snap_messages
             (conversation_id, from_user, media_type, created, created_ms,
              is_sender, conversation_title, created_dt, created_date, dedup_key)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        db.executemany(sql, batch)
    db.commit()

    count = db.execute("SELECT COUNT(*) FROM snap_messages").fetchone()[0]
    total_raw = len(rows)
    dupes = total_raw - count
    img_count = db.execute(
        "SELECT COUNT(*) FROM snap_messages WHERE media_type='IMAGE'"
    ).fetchone()[0]
    vid_count = db.execute(
        "SELECT COUNT(*) FROM snap_messages WHERE media_type='VIDEO'"
    ).fetchone()[0]

    if progress_cb:
        progress_cb(f"{count:,} snap messages ({img_count:,} images, {vid_count:,} videos)")
    logger.info("%d snap messages (%d images, %d videos)", count, img_count, vid_count)
    if dupes:
        logger.info("%d duplicates suppressed (multi-recipient)", dupes)
    return count


def ingest_stories(
    db: sqlite3.Connection,
    json_dir: Path,
    progress_cb: Callable[[str], None] | None = None,
) -> int:
    """Parse shared_story.json -> stories table."""
    path = json_dir / 'shared_story.json'
    if not path.exists():
        logger.warning("shared_story.json not found in %s", json_dir)
        return 0

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    entries = data.get('Shared Story', [])
    rows = []

    for entry in entries:
        created_raw = entry.get('Created', '')
        created_dt = parse_snap_date_iso(created_raw)
        content_type = entry.get('Content', '').upper()

        rows.append((
            entry.get('Story Id', ''),
            created_raw,
            created_dt,
            content_type,
        ))

    sql = "INSERT INTO stories (story_id, created, created_dt, content_type) VALUES (?, ?, ?, ?)"
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        db.executemany(sql, batch)
    db.commit()

    count = db.execute("SELECT COUNT(*) FROM stories").fetchone()[0]
    if progress_cb:
        progress_cb(f"{count:,} shared stories ingested")
    logger.info("%d shared stories ingested", count)
    return count


def ingest_friends(
    db: sqlite3.Connection,
    json_dir: Path,
    progress_cb: Callable[[str], None] | None = None,
) -> int:
    """Parse friends.json -> friends table.

    Deduplicates by username: prefers non-empty display_name,
    then lowest category priority (Friends=0, ..., Ignored=4).
    """
    path = json_dir / 'friends.json'
    if not path.exists():
        logger.warning("friends.json not found in %s", json_dir)
        return 0

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    CAT_PRIORITY = {
        'Friends': 0, 'Shortcuts': 1, 'Deleted Friends': 2,
        'Blocked Users': 3, 'Ignored Snapchatters': 4,
    }
    candidates: dict[str, list[tuple]] = {}
    cat_counts: dict[str, int] = {}

    for category_name, category_list in data.items():
        if not isinstance(category_list, list):
            continue

        cat_count = 0
        for entry in category_list:
            if not isinstance(entry, dict):
                continue
            username = entry.get('Username', '')
            if not username:
                continue
            display_name = entry.get('Display Name', '')
            priority = CAT_PRIORITY.get(category_name, 99)
            candidates.setdefault(username, []).append(
                (display_name, category_name, priority))
            cat_count += 1

        if cat_count:
            cat_counts[category_name] = cat_count

    # Pick best candidate per username
    rows = []
    for username, entries in candidates.items():
        entries.sort(key=lambda e: (0 if e[0] else 1, e[2]))
        best = entries[0]
        rows.append((username, best[0], best[1]))

    sql = "INSERT OR IGNORE INTO friends (username, display_name, category) VALUES (?, ?, ?)"
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        db.executemany(sql, batch)
    db.commit()

    count = db.execute("SELECT COUNT(*) FROM friends").fetchone()[0]
    cat_str = ", ".join(f"{k}: {v}" for k, v in sorted(cat_counts.items()))

    if progress_cb:
        progress_cb(f"{count:,} friends ingested (deduplicated)")
    logger.info("%d friends ingested (deduplicated)", count)
    if cat_str:
        logger.info("Categories: %s", cat_str)
    return count


def ingest_locations(
    db: sqlite3.Connection,
    json_dir: Path,
    progress_cb: Callable[[str], None] | None = None,
) -> int:
    """Parse location_history.json -> locations table.

    Handles '39.66 +/- 14.22, -89.65 +/- 14.22' uncertainty format.
    """
    path = json_dir / 'location_history.json'
    if not path.exists():
        logger.warning("location_history.json not found in %s", json_dir)
        return 0

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    entries = data.get('Location History', [])
    rows = []
    bad = 0

    for entry in entries:
        if not isinstance(entry, list) or len(entry) < 2:
            bad += 1
            continue

        ts_str = entry[0]
        dt = parse_snap_date(ts_str)
        if not dt:
            bad += 1
            continue

        coords = entry[1]
        parts = coords.split(',')
        if len(parts) < 2:
            bad += 1
            continue

        try:
            lat_str = parts[0].strip()
            lon_str = parts[1].strip()
            accuracy = None

            if '±' in lat_str:
                lat_pieces = lat_str.split('±')
                lat_str = lat_pieces[0].strip()
                acc_str = lat_pieces[1].strip()
                # Extract numeric accuracy: "39.66 meters" -> 39.66
                acc_match = re.match(r'([\d.]+)', acc_str)
                if acc_match:
                    accuracy = float(acc_match.group(1))

            if '±' in lon_str:
                lon_str = lon_str.split('±')[0].strip()

            lat = float(lat_str)
            lon = float(lon_str)
        except ValueError:
            bad += 1
            continue

        rows.append((ts_str, dt.timestamp(), lat, lon, accuracy))

    rows.sort(key=lambda x: x[1])

    sql = "INSERT INTO locations (timestamp, timestamp_unix, lat, lon, accuracy_m) VALUES (?, ?, ?, ?, ?)"
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        db.executemany(sql, batch)
    db.commit()

    count = db.execute("SELECT COUNT(*) FROM locations").fetchone()[0]
    if count:
        first = db.execute(
            "SELECT timestamp FROM locations ORDER BY timestamp_unix ASC LIMIT 1"
        ).fetchone()[0]
        last = db.execute(
            "SELECT timestamp FROM locations ORDER BY timestamp_unix DESC LIMIT 1"
        ).fetchone()[0]
        if progress_cb:
            progress_cb(f"{count:,} location breadcrumbs ({first} to {last})")
        logger.info("%d location breadcrumbs (%s to %s)", count, first, last)
    else:
        if progress_cb:
            progress_cb("0 location breadcrumbs")
        logger.info("0 location breadcrumbs")
    if bad:
        logger.warning("%d entries skipped (bad format)", bad)
    return count


def ingest_places(
    db: sqlite3.Connection,
    json_dir: Path,
    progress_cb: Callable[[str], None] | None = None,
) -> int:
    """Parse snap_map_places.json -> places table.

    Handles multiple JSON structures (Snapchat varies across exports).
    """
    path = json_dir / 'snap_map_places.json'
    if not path.exists():
        logger.warning("snap_map_places.json not found in %s", json_dir)
        return 0

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Detect structure: list, dict with known key, or nested dict
    entries = data
    if isinstance(data, dict):
        for key in ('Snap Map Places', 'Places', 'places'):
            if key in data:
                entries = data[key]
                break
        if isinstance(entries, dict):
            for v in entries.values():
                if isinstance(v, list):
                    entries = v
                    break

    if not isinstance(entries, list):
        logger.warning("Could not find places list in snap_map_places.json")
        return 0

    rows = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue

        name = entry.get('Name', '') or entry.get('name', '')
        lat = None
        lon = None
        address = entry.get('Address', '') or entry.get('address', '')

        if 'Latitude' in entry:
            try:
                lat = float(entry['Latitude'])
            except (ValueError, TypeError):
                pass
        if 'Longitude' in entry:
            try:
                lon = float(entry['Longitude'])
            except (ValueError, TypeError):
                pass

        # Fallback: parse 'Location' string as "lat,lon"
        loc = entry.get('Location', entry.get('location', ''))
        if isinstance(loc, str) and ',' in loc and lat is None:
            loc_parts = loc.split(',')
            if len(loc_parts) >= 2:
                try:
                    lat = float(loc_parts[0].strip())
                    lon = float(loc_parts[1].strip())
                except ValueError:
                    pass

        visit_count = entry.get('Number of Visits', entry.get('visit_count'))
        if visit_count is not None:
            try:
                visit_count = int(visit_count)
            except (ValueError, TypeError):
                visit_count = None

        rows.append((name, lat, lon, address, visit_count))

    sql = "INSERT INTO places (name, lat, lon, address, visit_count) VALUES (?, ?, ?, ?, ?)"
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        db.executemany(sql, batch)
    db.commit()

    count = db.execute("SELECT COUNT(*) FROM places").fetchone()[0]
    if progress_cb:
        progress_cb(f"{count:,} places ingested")
    logger.info("%d places ingested", count)
    return count


def ingest_snap_pro(
    db: sqlite3.Connection,
    json_dir: Path,
    progress_cb: Callable[[str], None] | None = None,
) -> int:
    """Parse snap_pro.json -> snap_pro table (optional file)."""
    path = json_dir / 'snap_pro.json'
    if not path.exists():
        logger.info("snap_pro.json not found in %s (optional, skipping)", json_dir)
        return 0

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Flexible structure detection (same approach as places)
    entries = data
    if isinstance(data, dict):
        for key in ('Snap Pro', 'Stories', 'Saved Stories', 'snap_pro'):
            if key in data:
                entries = data[key]
                break
        if isinstance(entries, dict):
            for v in entries.values():
                if isinstance(v, list):
                    entries = v
                    break

    if not isinstance(entries, list):
        logger.warning("Could not find entries in snap_pro.json")
        return 0

    rows = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        url = entry.get('URL', '') or entry.get('url', '') or entry.get('Download Link', '')
        created_raw = entry.get('Created', '') or entry.get('Date', '')
        created_dt = parse_snap_date_iso(created_raw)
        title = entry.get('Title', '') or entry.get('title', '')
        rows.append((url, created_raw, created_dt, title))

    sql = "INSERT INTO snap_pro (url, created, created_dt, title) VALUES (?, ?, ?, ?)"
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        db.executemany(sql, batch)
    db.commit()

    count = db.execute("SELECT COUNT(*) FROM snap_pro").fetchone()[0]
    if progress_cb:
        progress_cb(f"{count:,} snap pro entries ingested")
    logger.info("%d snap pro entries ingested", count)
    return count


# ── Asset Discovery ──────────────────────────────────────────────────────────


def scan_assets(
    db: sqlite3.Connection,
    input_dir: Path,
    config: dict | None = None,
    progress_cb: Callable[[str], None] | None = None,
) -> int:
    """Scan memories/, chat_media/, shared_story/ for media files.

    Detects file format via magic bytes, computes SHA-256, classifies
    asset type from filename patterns.
    """
    input_dir = Path(input_dir)
    t0 = time.time()

    scan_targets = []

    mem_dir = input_dir / 'memories'
    if mem_dir.is_dir():
        scan_targets.append((mem_dir, 'memory'))

    chat_dir = input_dir / 'chat_media'
    if chat_dir.is_dir():
        scan_targets.append((chat_dir, 'chat'))

    story_dir = input_dir / 'shared_story'
    if story_dir.is_dir():
        scan_targets.append((story_dir, 'story'))

    # Optionally scan sibling directories' memories/ folders
    if config and config.get('scan_siblings'):
        parent = input_dir.parent
        if parent.is_dir():
            try:
                for sibling in parent.iterdir():
                    if sibling == input_dir or not sibling.is_dir():
                        continue
                    sib_mem = sibling / 'memories'
                    if sib_mem.is_dir():
                        scan_targets.append((sib_mem, 'memory'))
                        logger.info("Including sibling: %s", sib_mem)
            except PermissionError:
                pass

    rows = []
    total_files = 0
    total_size = 0

    for scan_dir, type_prefix in scan_targets:
        try:
            files = sorted(f for f in scan_dir.iterdir() if f.is_file())
        except PermissionError:
            logger.warning("Permission denied: %s", scan_dir)
            continue

        for fp in files:
            total_files += 1
            filename = fp.name
            ext = fp.suffix.lower()
            date_str = None
            file_id = None
            memory_uuid = None
            asset_type = type_prefix

            if type_prefix == 'memory':
                m = MEMORY_RE.match(filename)
                if m:
                    date_str = m.group(1)
                    memory_uuid = m.group(2)
                    ftype = m.group(3)
                    asset_type = f'memory_{ftype}'
                    file_id = memory_uuid
                else:
                    asset_type = 'memory_main'
            elif type_prefix == 'chat':
                m = CHAT_FILE_RE.match(filename)
                if m:
                    date_str = m.group(1)
                    file_id = m.group(2)
                if 'overlay~' in filename:
                    asset_type = 'chat_overlay'
                elif 'thumbnail~' in filename:
                    asset_type = 'chat_thumbnail'
                else:
                    asset_type = 'chat'
            elif type_prefix == 'story':
                m = CHAT_FILE_RE.match(filename)
                if m:
                    date_str = m.group(1)
                    file_id = m.group(2)
                asset_type = 'story'

            vid = is_video(fp)
            file_size = fp.stat().st_size
            total_size += file_size

            real_ext = detect_real_format(fp)
            fmp4 = is_fragmented_mp4(fp) if vid else False
            sha = sha256_file(fp)

            rows.append((
                str(fp), filename, date_str, file_id, ext, real_ext,
                asset_type, 1 if vid else 0, 1 if fmp4 else 0,
                memory_uuid, file_size, sha,
            ))

            if total_files % 100 == 0 and progress_cb:
                elapsed = time.time() - t0
                rate = total_files / elapsed if elapsed > 0 else 0
                progress_cb(
                    f"{total_files:,} files | "
                    f"{total_size / 1048576:.0f} MB | "
                    f"{rate:.0f} files/s"
                )

    elapsed = time.time() - t0

    # Batch insert with INSERT OR IGNORE (path is UNIQUE)
    sql = """INSERT OR IGNORE INTO assets
             (path, filename, date_str, file_id, ext, real_ext,
              asset_type, is_video, is_fmp4, memory_uuid, file_size, sha256)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        db.executemany(sql, batch)
    db.commit()

    # Query summary stats
    count = db.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
    type_counts = db.execute(
        "SELECT asset_type, COUNT(*) FROM assets "
        "GROUP BY asset_type ORDER BY COUNT(*) DESC"
    ).fetchall()
    type_str = ", ".join(f"{t}: {c:,}" for t, c in type_counts)

    vid_count = db.execute(
        "SELECT COUNT(*) FROM assets WHERE is_video = 1"
    ).fetchone()[0]
    fmp4_count = db.execute(
        "SELECT COUNT(*) FROM assets WHERE is_fmp4 = 1"
    ).fetchone()[0]
    mismatch_count = db.execute(
        "SELECT COUNT(*) FROM assets WHERE real_ext IS NOT NULL"
    ).fetchone()[0]

    if progress_cb:
        progress_cb(f"{count:,} assets scanned ({total_size / 1048576:.0f} MB, {elapsed:.1f}s)")
    logger.info("%d assets scanned (%d MB, %.1fs)", count, total_size // 1048576, elapsed)
    logger.info("Types: %s", type_str)
    logger.info("Videos: %d | fMP4 needing remux: %d", vid_count, fmp4_count)
    if mismatch_count:
        logger.warning("%d format mismatches detected", mismatch_count)

    return count


# ── ZIP Handling and Export Discovery ────────────────────────────────────────


def merge_multipart_zips(
    staging_dir: Path,
    work_dir: Path,
    progress_cb: Callable[[str], None] | None = None,
) -> int:
    """Extract multiple ZIP parts from a staging directory into a merged work directory.

    Multi-part ZIP uploads from the chunked upload system arrive as file_0.part, file_1.part, etc.
    Each .part file IS a valid ZIP file (renamed from mydata~1.zip, mydata~2.zip, etc.).
    This function extracts all of them into work_dir, merging their contents.

    Args:
        staging_dir: Directory containing file_N.part files (uploaded ZIP parts).
        work_dir: Target directory for merged extraction.
        progress_cb: Optional callback for logging per-file extraction.

    Returns:
        int: Number of ZIP parts successfully extracted.

    Raises:
        ValueError: If any .part file is not a valid ZIP.
    """
    staging_dir = Path(staging_dir).resolve()
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    # Find all file_N.part files, sorted by index
    part_files = []
    try:
        for item in staging_dir.iterdir():
            if item.is_file() and item.name.startswith('file_') and item.name.endswith('.part'):
                # Extract index from file_N.part
                try:
                    idx_str = item.name[5:-5]  # Remove 'file_' prefix and '.part' suffix
                    idx = int(idx_str)
                    part_files.append((idx, item))
                except ValueError:
                    logger.warning("Skipping malformed part file: %s", item.name)
    except PermissionError:
        logger.warning("Permission denied reading staging directory: %s", staging_dir)
        return 0

    # Sort by index to extract in order
    part_files.sort()

    if not part_files:
        logger.warning("No .part files found in staging directory: %s", staging_dir)
        return 0

    extracted_count = 0
    for idx, part_path in part_files:
        # Validate it's a ZIP
        if not zipfile.is_zipfile(str(part_path)):
            logger.error("Part file is not a valid ZIP: %s", part_path.name)
            continue

        file_size_mb = part_path.stat().st_size / (1024 * 1024)
        logger.info("Extracting [%d/%d] %s (%.0f MB)", idx + 1, len(part_files), part_path.name, file_size_mb)

        try:
            with zipfile.ZipFile(str(part_path), 'r') as zf:
                # Validate ALL members before extracting
                for member in zf.namelist():
                    if member.startswith('/'):
                        raise ValueError(f"Unsafe path in ZIP part {part_path.name}: {member}")
                    if '..' in member.split('/'):
                        raise ValueError(f"Path traversal in ZIP part {part_path.name}: {member}")
                    target = (work_dir / member).resolve()
                    if not str(target).startswith(str(work_dir.resolve())):
                        raise ValueError(f"Path traversal detected in ZIP part {part_path.name}: {member}")

                # All members validated — extract everything
                zf.extractall(work_dir)
                extracted_count += 1

                file_count = len(zf.namelist())
                if progress_cb:
                    progress_cb(f"Extracted {part_path.name}: {file_count:,} files")
                logger.info("Successfully extracted part %d: %d files", idx, file_count)
        except Exception as e:
            logger.error("Failed to extract part %d (%s): %s", idx, part_path.name, str(e))
            # Continue with next part — don't crash the whole job

    if extracted_count == 0:
        logger.error("No part files were successfully extracted from %s", staging_dir)
        raise ValueError(f"Failed to extract any ZIP parts from staging directory: {staging_dir}")

    logger.info("Multi-part ZIP merge complete: %d parts extracted", extracted_count)
    return extracted_count


def extract_zips(
    input_path: Path,
    scratch_dir: Path,
    source_filter: str | None = None,
) -> Path:
    """Extract Snapchat export ZIP file(s) with path traversal protection.

    Supports:
    - Single ZIP file → extract to scratch_dir
    - Directory of .zip files → extract all to scratch_dir
    - Staging directory of .part files (multi-part upload) → merge extract to scratch_dir
    - Directory without ZIPs → return as-is (already extracted)

    Args:
        input_path: Path to a single ZIP, directory containing ZIPs, or staging directory with .part files.
        scratch_dir: Target directory for extraction.
        source_filter: Optional comma-separated export IDs to include (only for .zip files).

    Returns:
        scratch_dir after extraction.

    Raises:
        ValueError: If input not found, not a ZIP, or contains unsafe paths.
    """
    input_path = Path(input_path).resolve()
    scratch_dir = Path(scratch_dir)

    # Parse source filter
    filter_ids = None
    if source_filter:
        filter_ids = set(s.strip() for s in source_filter.split(',') if s.strip())

    if input_path.is_file():
        if not zipfile.is_zipfile(str(input_path)):
            raise ValueError(f"Not a ZIP file: {input_path}")
        zips = [input_path]
    elif input_path.is_dir():
        # Check if this is a multi-part staging directory (contains file_N.part files)
        part_files = [f for f in input_path.iterdir()
                     if f.is_file() and f.name.startswith('file_') and f.name.endswith('.part')]

        if part_files:
            # Multi-part upload staging directory
            logger.info("Detected multi-part ZIP staging directory with %d part files", len(part_files))
            merge_multipart_zips(input_path, scratch_dir)
            return scratch_dir

        # Otherwise, look for regular .zip files
        zips = sorted(
            f for f in input_path.iterdir()
            if f.is_file() and f.name.lower().endswith('.zip')
            and zipfile.is_zipfile(str(f))
        )
        if not zips:
            return input_path
    else:
        raise ValueError(f"Input not found: {input_path}")

    # Apply source filter
    if filter_ids:
        filtered = [z for z in zips if any(fid in z.name for fid in filter_ids)]
        if not filtered:
            raise ValueError(f"No ZIPs match source filter: {source_filter}")
        skipped = len(zips) - len(filtered)
        if skipped:
            logger.info(
                "Source filter: extracting %d of %d ZIPs (skipping %d)",
                len(filtered), len(zips), skipped,
            )
        zips = filtered

    scratch_dir.mkdir(parents=True, exist_ok=True)

    for i, zp in enumerate(zips, 1):
        sz = zp.stat().st_size / (1024 * 1024)
        logger.info("Extracting [%d/%d] %s (%.0f MB)", i, len(zips), zp.name, sz)

        with zipfile.ZipFile(str(zp), 'r') as zf:
            # Validate ALL members before extracting
            for member in zf.namelist():
                if member.startswith('/'):
                    raise ValueError(f"Unsafe path in ZIP: {member}")
                if '..' in member.split('/'):
                    raise ValueError(f"Path traversal in ZIP: {member}")
                target = (scratch_dir / member).resolve()
                if not str(target).startswith(str(scratch_dir.resolve())):
                    raise ValueError(f"Path traversal detected in ZIP: {member}")
            # All members validated — extract everything
            zf.extractall(scratch_dir)

    return scratch_dir


def discover_export(
    base_dir: Path,
) -> dict | None:
    """Find Snapchat export directory structure within base_dir.

    Returns dict with keys: primary, secondaries, overlays_dir, json_dir,
    memories_dirs, chat_dir, story_dir, html_dir. Or None if not found.
    """
    base_dir = Path(base_dir)

    def _check_dir(d: Path) -> bool:
        return (d / 'json' / 'memories_history.json').exists()

    def _is_secondary(d: Path) -> bool:
        return (d / 'memories').is_dir() and not (d / 'json').is_dir()

    def _build_result(
        primary: Path,
        secondaries: list[Path],
        overlays_dir: Path | None,
    ) -> dict:
        memories_dirs = []
        mem_dir = primary / 'memories'
        if mem_dir.is_dir():
            memories_dirs.append(mem_dir)
        for sd in secondaries:
            sd_mem = sd / 'memories'
            if sd_mem.is_dir():
                memories_dirs.append(sd_mem)

        chat_dir = primary / 'chat_media'
        story_dir = primary / 'shared_story'
        html_dir = primary / 'html'

        return {
            'primary': primary,
            'secondaries': secondaries,
            'overlays_dir': overlays_dir,
            'json_dir': primary / 'json',
            'memories_dirs': memories_dirs,
            'chat_dir': chat_dir if chat_dir.is_dir() else None,
            'story_dir': story_dir if story_dir.is_dir() else None,
            'html_dir': html_dir if html_dir.is_dir() else None,
        }

    # Check if base_dir itself is primary
    if _check_dir(base_dir):
        ov = base_dir.parent / 'overlays-merged'
        return _build_result(base_dir, [], ov if ov.is_dir() else None)

    # Scan base_dir children
    primary = None
    secondaries = []
    overlays_dir = None
    try:
        children = sorted(base_dir.iterdir())
    except PermissionError:
        logger.warning("Permission denied reading: %s", base_dir)
        return None

    for d in children:
        if not d.is_dir():
            continue
        if d.name == 'overlays-merged':
            overlays_dir = d
        elif _check_dir(d):
            primary = d
        elif _is_secondary(d):
            secondaries.append(d)

    if primary:
        return _build_result(primary, secondaries, overlays_dir)

    # Recurse one level deeper
    for subdir in children:
        if not subdir.is_dir():
            continue
        inner_primary = None
        inner_secondaries = []
        inner_overlays = None
        try:
            inner_children = sorted(subdir.iterdir())
        except PermissionError:
            continue
        for d in inner_children:
            if not d.is_dir():
                continue
            if d.name == 'overlays-merged':
                inner_overlays = d
            elif _check_dir(d):
                inner_primary = d
            elif _is_secondary(d):
                inner_secondaries.append(d)
        if inner_primary:
            return _build_result(inner_primary, inner_secondaries, inner_overlays)

    # Not found — log directory listing for debugging
    logger.warning("No Snapchat export found in %s", base_dir)
    try:
        for item in sorted(base_dir.iterdir()):
            marker = "dir" if item.is_dir() else "file"
            logger.debug("  [%s] %s", marker, item.name)
    except PermissionError:
        logger.debug("  (permission denied reading directory)")

    return None


def list_exports(
    root: Path,
) -> list[dict]:
    """Scan root directory for all Snapchat exports (dirs and ZIPs).

    Returns list of dicts with: path, export_id, name, type, is_zip,
    mem_count, chat_count, story_count, (size_mb for ZIPs).
    """
    root = Path(root)
    exports = []

    try:
        children = sorted(root.iterdir())
    except PermissionError:
        logger.warning("Permission denied reading: %s", root)
        return exports

    def count_files(p: Path) -> int:
        try:
            return sum(1 for f in p.iterdir() if f.is_file()) if p.is_dir() else 0
        except PermissionError:
            return -1

    # Scan directories
    for d in children:
        if not d.is_dir() or d.name == 'overlays-merged':
            continue
        has_json = (d / 'json' / 'memories_history.json').exists()
        has_memories = (d / 'memories').is_dir()
        if not has_json and not has_memories:
            continue

        parts = d.name.split('~')
        export_id = parts[-1] if len(parts) > 1 else d.name

        exports.append({
            'path': d,
            'export_id': export_id,
            'name': d.name,
            'type': 'full' if has_json else 'memories-only',
            'is_zip': False,
            'mem_count': count_files(d / 'memories') if has_memories else 0,
            'chat_count': count_files(d / 'chat_media') if (d / 'chat_media').is_dir() else 0,
            'story_count': count_files(d / 'shared_story') if (d / 'shared_story').is_dir() else 0,
        })

    # Scan ZIP files
    for f in children:
        if not f.is_file() or not f.name.lower().endswith('.zip'):
            continue
        if not zipfile.is_zipfile(str(f)):
            continue

        stem = f.stem
        parts = stem.split('~')
        export_id = parts[-1] if len(parts) > 1 else stem

        try:
            with zipfile.ZipFile(str(f), 'r') as zf:
                names = zf.namelist()
                has_json = any('memories_history.json' in n for n in names)
                has_memories = any('/memories/' in n or n.startswith('memories/') for n in names)
                mem_n = sum(1 for n in names if '/memories/' in n or n.startswith('memories/'))
                chat_n = sum(1 for n in names if '/chat_media/' in n or n.startswith('chat_media/'))
                story_n = sum(1 for n in names if '/shared_story/' in n or n.startswith('shared_story/'))
        except Exception:
            has_json = False
            has_memories = False
            mem_n = chat_n = story_n = 0

        if not has_json and not has_memories:
            continue

        size_mb = f.stat().st_size / (1024 * 1024)
        exports.append({
            'path': f,
            'export_id': export_id,
            'name': f.name,
            'type': 'full' if has_json else 'memories-only',
            'is_zip': True,
            'size_mb': size_mb,
            'mem_count': mem_n,
            'chat_count': chat_n,
            'story_count': story_n,
        })

    return exports


# ── Orchestrator ─────────────────────────────────────────────────────────────


def phase1_ingest(
    db: sqlite3.Connection,
    input_dir: Path,
    json_dir: Path,
    config: dict | None = None,
    progress_cb: Callable[[str], None] | None = None,
) -> dict[str, int]:
    """Phase 1 orchestrator: Ingest all Snapchat data sources into SQLite.

    Calls all 9 ingest functions in order, reports progress after each.
    Returns per-source count dict.
    """
    input_dir = Path(input_dir)
    json_dir = Path(json_dir)

    t0 = time.time()
    stats: dict[str, int] = {}

    stats['memories'] = ingest_memories(db, json_dir, progress_cb)
    stats['chat_messages'] = ingest_chat(db, json_dir, progress_cb)
    stats['snap_messages'] = ingest_snaps(db, json_dir, progress_cb)
    stats['stories'] = ingest_stories(db, json_dir, progress_cb)
    stats['friends'] = ingest_friends(db, json_dir, progress_cb)
    stats['locations'] = ingest_locations(db, json_dir, progress_cb)
    stats['places'] = ingest_places(db, json_dir, progress_cb)
    stats['snap_pro'] = ingest_snap_pro(db, json_dir, progress_cb)
    stats['assets'] = scan_assets(db, input_dir, config, progress_cb)

    elapsed = time.time() - t0

    total_rows = sum(stats.values())
    logger.info("Phase 1 complete (%.1fs)", elapsed)
    logger.info("Total rows ingested: %d", total_rows)
    for table, count in stats.items():
        if count > 0:
            logger.info("  %-30s %6d", table, count)

    # Log database file size
    db_info = db.execute("PRAGMA database_list").fetchone()
    if db_info and db_info[2]:
        try:
            db_size = Path(db_info[2]).stat().st_size
            logger.info("Database size: %d KB", db_size // 1024)
        except OSError:
            pass

    if progress_cb:
        progress_cb(f"Phase 1 complete: {total_rows:,} rows in {elapsed:.1f}s")

    return stats
