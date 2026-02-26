"""Phase 4: Export — copy files, embed EXIF, burn overlays, export chats, write reports.

Ported from snatched.py v2 lines 2293-3457 with v3 adaptations:
- print()/sys.stdout.write() → logger / progress_cb
- args object → Config
- shutil.which() checks for graceful degradation
- Returns dicts instead of mixed types
"""

import json
import logging
import shutil
import sqlite3
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from snatched.config import Config
from snatched.utils import (
    UUID_RE,
    VERSION,
    format_chat_date,
    parse_iso_dt,
    parse_snap_date,
    sanitize_filename,
    sha256_file,
)
from snatched.processing.enrich import build_chat_folder_map

logger = logging.getLogger(__name__)

BATCH_SIZE = 500

# Check for optional ChatRenderer (Pillow dependency)
try:
    from snatched.processing.chat_renderer import ChatMessage, ChatRenderer
    HAS_RENDERER = True
except ImportError:
    HAS_RENDERER = False
    logger.debug("ChatRenderer not available (Pillow not installed)")


# ── File Copy + Remux ───────────────────────────────────────────────────────


def copy_files(
    db: sqlite3.Connection,
    project_dir: Path,
    config: Config,
    lanes: list[str] | None = None,
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    """Copy all best-matched assets to their computed output paths.

    For fMP4 files: remux with ffmpeg if available.
    For all others: shutil.copy2() with SHA-256 verification.

    Args:
        db: SQLite connection
        project_dir: Root project directory
        config: Configuration
        lanes: Optional lane filter. None = copy all asset types.
               Supported values: 'memories', 'stories', 'chats'.
        progress_cb: Optional progress callback

    Returns:
        {'copied': int, 'remuxed': int, 'verified': int, 'errors': int, 'elapsed': float}
    """
    t0 = time.time()

    if progress_cb:
        progress_cb("Copying files to output directory...")

    out_dir = project_dir / 'output'

    lane_filter = ""
    if lanes:
        type_conditions = []
        if "memories" in lanes:
            type_conditions.append("a.asset_type IN ('memory_main', 'memory_overlay')")
        if "stories" in lanes:
            type_conditions.append("a.asset_type = 'story'")
        if "chats" in lanes:
            type_conditions.append("a.asset_type = 'chat'")
        if type_conditions:
            lane_filter = " AND (" + " OR ".join(type_conditions) + ")"

    rows = db.execute(f"""
        SELECT m.id, m.asset_id, m.output_subdir, m.output_filename,
               a.path, a.ext, a.real_ext, a.is_fmp4, a.sha256
        FROM matches m
        JOIN assets a ON m.asset_id = a.id
        WHERE m.is_best = 1
          AND m.output_subdir IS NOT NULL
          AND m.output_filename IS NOT NULL{lane_filter}
    """).fetchall()

    if not rows:
        logger.warning("No files to copy (no best matches with output paths)")
        return {'copied': 0, 'remuxed': 0, 'verified': 0, 'errors': 0, 'elapsed': 0.0}

    total = len(rows)
    copied = 0
    remuxed = 0
    verified = 0
    errors = 0
    has_ffmpeg = shutil.which('ffmpeg')

    for i, (match_id, asset_id, subdir, filename, src_path,
            ext, real_ext, is_fmp4, src_sha) in enumerate(rows):

        src = Path(src_path)
        if not src.exists():
            logger.warning(f"Source file missing: {src}")
            errors += 1
            continue

        dst = out_dir / subdir / filename
        dst.parent.mkdir(parents=True, exist_ok=True)

        try:
            if is_fmp4 and has_ffmpeg:
                result = subprocess.run(
                    ['ffmpeg', '-y', '-i', str(src), '-c', 'copy',
                     '-movflags', '+faststart', str(dst)],
                    capture_output=True, timeout=120)
                if result.returncode == 0:
                    remuxed += 1
                else:
                    shutil.copy2(str(src), str(dst))
            else:
                shutil.copy2(str(src), str(dst))

            copied += 1

            # Verify SHA-256 for non-remuxed copies
            dst_sha = sha256_file(dst)
            if is_fmp4 and has_ffmpeg:
                pass  # Remuxed files will have different SHA
            elif dst_sha and src_sha and dst_sha == src_sha:
                verified += 1
            elif dst_sha and src_sha:
                logger.warning(f"SHA-256 mismatch: {filename}")
                errors += 1

            db.execute(
                "UPDATE assets SET output_path=?, output_sha256=? WHERE id=?",
                (str(dst), dst_sha, asset_id))

        except (OSError, IOError, subprocess.TimeoutExpired) as e:
            logger.warning(f"Copy failed for {src.name}: {e}")
            errors += 1
            continue

        if (i + 1) % 100 == 0 and progress_cb:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            progress_cb(f"Copying: {i + 1}/{total} ({rate:.0f} files/s)")

    db.commit()

    elapsed = time.time() - t0
    logger.info(
        f"Copy: {copied} files ({copied - remuxed} copied, "
        f"{remuxed} remuxed, {errors} errors) in {elapsed:.1f}s"
    )

    if progress_cb:
        progress_cb(f"Copy complete: {copied} files ({remuxed} remuxed, {errors} errors)")

    return {
        'copied': copied,
        'remuxed': remuxed,
        'verified': verified,
        'errors': errors,
        'elapsed': elapsed,
    }


# ── EXIF Embedding ──────────────────────────────────────────────────────────


def write_exif(
    db: sqlite3.Connection,
    project_dir: Path,
    config: Config,
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    """Embed EXIF tags into copied files using exiftool stay_open batch mode.

    Uses a single long-running exiftool process for performance.
    Skips gracefully if exiftool not found.

    Returns:
        {'written': int, 'errors': int, 'skipped': int, 'elapsed': float}
    """
    t0 = time.time()

    if progress_cb:
        progress_cb("Embedding EXIF metadata...")

    if not shutil.which('exiftool'):
        logger.warning("exiftool not found -- skipping EXIF embedding")
        return {'written': 0, 'errors': 0, 'skipped': 0, 'elapsed': 0.0}

    rows = db.execute("""
        SELECT m.id, m.asset_id, m.exif_tags_json, a.output_path, a.is_video
        FROM matches m
        JOIN assets a ON m.asset_id = a.id
        WHERE m.is_best = 1
          AND m.exif_tags_json IS NOT NULL
          AND a.output_path IS NOT NULL
    """).fetchall()

    if not rows:
        logger.info("No files to tag")
        return {'written': 0, 'errors': 0, 'skipped': 0, 'elapsed': 0.0}

    # Filter to valid, existing files with parseable tags
    to_tag = []
    skipped = 0
    for match_id, asset_id, tags_json, output_path, is_vid in rows:
        if not output_path or not Path(output_path).exists():
            skipped += 1
            continue
        try:
            tags = json.loads(tags_json)
        except (json.JSONDecodeError, TypeError):
            skipped += 1
            continue
        if not tags:
            skipped += 1
            continue
        to_tag.append((match_id, asset_id, tags, output_path, bool(is_vid)))

    total = len(to_tag)
    logger.info(f"Embedding metadata into {total} files...")

    # Start exiftool in stay_open mode
    proc = subprocess.Popen(
        ['exiftool', '-stay_open', 'True', '-@', '-'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    stdout_lines = []
    stderr_lines = []

    def drain(pipe, dest):
        for line in pipe:
            dest.append(line)
        pipe.close()

    t_out = threading.Thread(target=drain, args=(proc.stdout, stdout_lines), daemon=True)
    t_err = threading.Thread(target=drain, args=(proc.stderr, stderr_lines), daemon=True)
    t_out.start()
    t_err.start()

    written = 0

    for i, (match_id, asset_id, tags, output_path, is_vid) in enumerate(to_tag):
        lines = ['-overwrite_original', '-ignoreMinorErrors']
        if is_vid:
            lines.extend(['-api', 'QuickTimeUTC'])
        for k, v in tags.items():
            lines.append(f'-{k}={str(v).replace(chr(10), " ")}')
        lines.append(str(output_path))
        lines.append('-execute')

        try:
            proc.stdin.write(('\n'.join(lines) + '\n').encode())
        except (BrokenPipeError, OSError):
            logger.warning("exiftool pipe broken")
            break

        written += 1

        if (i + 1) % 50 == 0 or (i + 1) == total:
            try:
                proc.stdin.flush()
            except (BrokenPipeError, OSError):
                pass
            if progress_cb and (i + 1) % 100 == 0:
                progress_cb(f"EXIF: {i + 1}/{total}")

    # Shut down exiftool
    try:
        proc.stdin.write(b'-stay_open\nFalse\n')
        proc.stdin.flush()
        proc.stdin.close()
    except (BrokenPipeError, OSError):
        pass

    t_out.join(timeout=30)
    t_err.join(timeout=30)
    proc.wait(timeout=30)

    # Parse stderr for per-file errors
    error_by_filename = {}
    for raw in stderr_lines:
        line = raw.decode(errors='replace').strip()
        if not line or 'Warning' in line or 'image files read' in line:
            continue
        for match_id, asset_id, tags, output_path, is_vid in to_tag:
            fname = Path(output_path).name
            if fname in line and fname not in error_by_filename:
                error_by_filename[fname] = line

    exif_errors = len(error_by_filename)

    # Update assets table with success/failure
    for match_id, asset_id, tags, output_path, is_vid in to_tag:
        fname = Path(output_path).name
        if fname in error_by_filename:
            db.execute(
                "UPDATE assets SET exif_written=0, exif_error=? WHERE id=?",
                (error_by_filename[fname], asset_id))
        else:
            db.execute(
                "UPDATE assets SET exif_written=1 WHERE id=?", (asset_id,))
    db.commit()

    # Adjust written count to reflect actual successes
    written = max(0, written - exif_errors)

    elapsed = time.time() - t0
    logger.info(
        f"EXIF: {written} tagged ({exif_errors} errors, "
        f"{skipped} skipped) in {elapsed:.1f}s"
    )

    if progress_cb:
        progress_cb(f"EXIF complete: {written} tagged ({exif_errors} errors)")

    return {
        'written': written,
        'errors': exif_errors,
        'skipped': skipped,
        'elapsed': elapsed,
    }


# ── Overlay Burning ─────────────────────────────────────────────────────────


def burn_overlays(
    db: sqlite3.Connection,
    project_dir: Path,
    config: Config,
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    """Burn overlay PNGs onto their corresponding main memory files.

    Uses ImageMagick for images, ffmpeg for videos.
    Re-embeds EXIF on video overlays if exiftool available.
    Skips gracefully if tools not found.

    Returns:
        {'burned': int, 'errors': int, 'elapsed': float}
    """
    t0 = time.time()

    if progress_cb:
        progress_cb("Burning overlays...")

    has_composite = shutil.which('magick') or shutil.which('composite')
    has_ffmpeg = shutil.which('ffmpeg')

    if not has_composite and not has_ffmpeg:
        logger.warning("Overlay burning skipped: ImageMagick and ffmpeg not installed")
        return {'burned': 0, 'errors': 0, 'elapsed': 0.0}

    rows = db.execute("""
        SELECT
            main_a.output_path AS main_output,
            ov_a.path AS overlay_src,
            main_a.is_video,
            main_m.id AS main_match_id,
            main_m.exif_tags_json
        FROM assets main_a
        JOIN matches main_m ON main_a.id = main_m.asset_id AND main_m.is_best = 1
        JOIN assets ov_a ON main_a.memory_uuid = ov_a.memory_uuid
        WHERE main_a.asset_type = 'memory_main'
          AND ov_a.asset_type = 'memory_overlay'
          AND main_a.output_path IS NOT NULL
          AND main_a.memory_uuid IS NOT NULL
    """).fetchall()

    if not rows:
        logger.info("No overlays to burn")
        return {'burned': 0, 'errors': 0, 'elapsed': 0.0}

    # Filter to pairs where both files exist on disk
    pairs = []
    for main_output, overlay_src, is_vid, match_id, exif_json in rows:
        if main_output and overlay_src:
            main_p = Path(main_output)
            ov_p = Path(overlay_src)
            if main_p.exists() and ov_p.exists():
                pairs.append((main_p, ov_p, bool(is_vid), match_id, exif_json))

    total = len(pairs)
    logger.info(f"Found {total} overlay pairs to compose")

    burned = 0
    burn_errors = 0

    for i, (main_dst, ov_src, is_vid, match_id, exif_json) in enumerate(pairs):
        try:
            if is_vid:
                if not has_ffmpeg:
                    continue
                tmp = main_dst.with_suffix('.tmp' + main_dst.suffix)
                result = subprocess.run([
                    'ffmpeg', '-y', '-i', str(main_dst), '-i', str(ov_src),
                    '-filter_complex', 'overlay=0:0', '-c:a', 'copy', str(tmp)
                ], capture_output=True, timeout=120)
                if result.returncode == 0:
                    tmp.replace(main_dst)
                    burned += 1
                    # Re-embed EXIF after video overlay
                    if exif_json and shutil.which('exiftool'):
                        try:
                            tags = json.loads(exif_json)
                            cmd = ['exiftool', '-overwrite_original',
                                   '-ignoreMinorErrors',
                                   '-api', 'QuickTimeUTC']
                            for k, v in tags.items():
                                cmd.append(f'-{k}={v}')
                            cmd.append(str(main_dst))
                            subprocess.run(cmd, capture_output=True, timeout=30)
                        except (json.JSONDecodeError, subprocess.TimeoutExpired):
                            pass
                else:
                    if tmp.exists():
                        try:
                            tmp.unlink()
                        except OSError:
                            pass
                    burn_errors += 1
            else:
                if not has_composite:
                    continue
                if shutil.which('magick'):
                    cmd = ['magick', 'composite']
                else:
                    cmd = ['composite']
                result = subprocess.run(
                    cmd + ['-gravity', 'center',
                           str(ov_src), str(main_dst), str(main_dst)],
                    capture_output=True, timeout=60)
                if result.returncode == 0:
                    burned += 1
                else:
                    burn_errors += 1

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
                OSError) as e:
            logger.warning(f"Overlay failed: {main_dst.name}: {e}")
            burn_errors += 1

        if (i + 1) % 10 == 0 and progress_cb:
            progress_cb(f"Overlays: {i + 1}/{total} ({burned} composed)")

    elapsed = time.time() - t0
    logger.info(f"Overlays: {burned}/{total} composed ({burn_errors} errors) in {elapsed:.1f}s")

    if progress_cb:
        progress_cb(f"Overlays complete: {burned}/{total} composed")

    return {'burned': burned, 'errors': burn_errors, 'elapsed': elapsed}


# ── Chat Text Export ────────────────────────────────────────────────────────


def export_chat_text(
    db: sqlite3.Connection,
    project_dir: Path,
    config: Config,
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    """Export per-conversation chat transcripts as plain text files.

    Output: project_dir/output/chat/{CONVERSATION}/Transcripts/{CONVERSATION}.txt

    Returns:
        {'conversations': int, 'messages': int, 'elapsed': float}
    """
    t0 = time.time()

    if progress_cb:
        progress_cb("Exporting chat transcripts...")

    chat_out_dir = project_dir / 'output' / 'chat'

    # Use shared folder map for consistent naming with Phase 3
    chat_folder_map = build_chat_folder_map(db)

    friends = {}
    for row in db.execute("SELECT username, display_name FROM friends"):
        friends[row[0]] = row[1] if row[1] else None

    conversations = db.execute("""
        SELECT DISTINCT conversation_id, conversation_title
        FROM chat_messages
        ORDER BY conversation_id
    """).fetchall()

    if not conversations:
        logger.info("No chat messages to export")
        return {'conversations': 0, 'messages': 0, 'elapsed': 0.0}

    total_convs = 0
    total_msgs = 0

    for conv_idx, (conv_id, conv_title) in enumerate(conversations):
        messages = db.execute("""
            SELECT from_user, media_type, content, created, created_ms,
                   is_sender, conversation_title, id
            FROM chat_messages
            WHERE conversation_id = ?
            ORDER BY
                CASE WHEN created_ms IS NOT NULL THEN created_ms ELSE 0 END ASC,
                created ASC
        """, (conv_id,)).fetchall()

        if not messages:
            continue

        # Use shared folder map
        safe_name = chat_folder_map.get(conv_id)
        if not safe_name:
            safe_name = sanitize_filename(conv_title or conv_id or 'Unknown')

        # Determine display title
        display_title = conv_title
        if not display_title:
            for msg in messages:
                if msg[6]:
                    display_title = msg[6]
                    break

        # Determine partner info
        partner_username = None
        partner_display = None
        has_uuid_id = bool(UUID_RE.match(conv_id))
        if not has_uuid_id:
            partner_username = conv_id
            partner_display = friends.get(conv_id)

        other_users = []
        other_users_set = set()
        for msg in messages:
            u = msg[0]
            if u and not msg[5] and u not in other_users_set:
                other_users_set.add(u)
                other_users.append(u)

        if not partner_username and other_users:
            partner_username = other_users[0]
            partner_display = friends.get(other_users[0])

        # Compute date range
        first_date = None
        last_date = None
        for msg in messages:
            if msg[3]:
                dt_str = format_chat_date(msg[3])
                if dt_str:
                    if not first_date:
                        first_date = dt_str
                    last_date = dt_str

        # Write transcript file
        transcript_dir = chat_out_dir / safe_name / 'Transcripts'
        transcript_dir.mkdir(parents=True, exist_ok=True)
        txt_path = transcript_dir / f"{safe_name}.txt"

        try:
            with open(txt_path, 'w', encoding='utf-8') as f:
                header_title = display_title or partner_display or partner_username or 'Unknown'
                f.write(f"=== Conversation: {header_title} ===\n")
                if partner_username:
                    pd = f" ({partner_display})" if partner_display else ""
                    f.write(f"Partner: @{partner_username}{pd}\n")
                f.write(f"Messages: {len(messages)}\n")
                if first_date and last_date:
                    f.write(f"Date range: {first_date} to {last_date}\n")
                f.write("=" * 64 + "\n\n")

                for msg in messages:
                    from_user, media_type, content, created, created_ms, \
                        is_sender, msg_conv_title, _msg_id = msg

                    ts = format_chat_date(created) or '????-??-?? ??:??:??'

                    if is_sender:
                        sender = 'Me'
                    elif from_user and friends.get(from_user):
                        sender = friends[from_user]
                    elif from_user:
                        sender = f"@{from_user}"
                    else:
                        sender = 'Unknown'

                    mtype = (media_type or '').upper()
                    if mtype == 'MEDIA' and content:
                        body = content
                    elif mtype == 'MEDIA':
                        body = '[MEDIA: image]'
                    elif mtype == 'STICKER':
                        body = '[STICKER]'
                    elif mtype == 'NOTE':
                        body = content if content else '[NOTE]'
                    elif mtype == 'SHARE':
                        body = content if content else '[SHARE]'
                    elif content:
                        body = content
                    else:
                        body = f'[{mtype}]' if mtype else '[empty]'

                    f.write(f"[{ts}] {sender}: {body}\n")

                total_msgs += len(messages)

        except (OSError, IOError) as e:
            logger.warning(f"Failed to write {txt_path}: {e}")
            continue

        total_convs += 1

        if (conv_idx + 1) % 50 == 0 and progress_cb:
            progress_cb(f"Transcripts: {conv_idx + 1}/{len(conversations)}")

    elapsed = time.time() - t0
    logger.info(f"Chat text: {total_convs} conversations, {total_msgs} messages ({elapsed:.1f}s)")

    if progress_cb:
        progress_cb(f"Chat text: {total_convs} conversations exported")

    return {
        'conversations': total_convs,
        'messages': total_msgs,
        'elapsed': elapsed,
    }


# ── Chat PNG Export ─────────────────────────────────────────────────────────


def export_chat_png(
    db: sqlite3.Connection,
    project_dir: Path,
    config: Config,
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    """Export per-conversation chat as high-resolution PNG screenshots.

    Output: project_dir/output/chat/{CONVERSATION}/Saved Chat Screenshots/page-NNNN.png

    Uses ChatRenderer class (requires Pillow). Skips if not available.

    Returns:
        {'conversations': int, 'pages': int, 'elapsed': float}
    """
    t0 = time.time()

    if not HAS_RENDERER:
        logger.info("Chat PNG export skipped (Pillow not installed)")
        return {'conversations': 0, 'pages': 0, 'elapsed': 0.0}

    if progress_cb:
        progress_cb("Rendering chat screenshots...")

    chat_out_dir = project_dir / 'output' / 'chat'
    chat_folder_map = build_chat_folder_map(db)

    friends = {}
    for row in db.execute("SELECT username, display_name FROM friends"):
        friends[row[0]] = row[1] if row[1] else None

    # Check for dark mode in lane config
    chats_lane = config.lanes.get('chats')
    dark_mode = chats_lane.dark_mode if chats_lane else False

    conversations = db.execute("""
        SELECT DISTINCT conversation_id, conversation_title
        FROM chat_messages
        ORDER BY conversation_id
    """).fetchall()

    if not conversations:
        return {'conversations': 0, 'pages': 0, 'elapsed': 0.0}

    total_convs = 0
    total_pages = 0

    for conv_idx, (conv_id, conv_title) in enumerate(conversations):
        messages = db.execute("""
            SELECT from_user, media_type, content, created, created_ms,
                   is_sender, conversation_title, id
            FROM chat_messages
            WHERE conversation_id = ?
            ORDER BY
                CASE WHEN created_ms IS NOT NULL THEN created_ms ELSE 0 END ASC,
                created ASC
        """, (conv_id,)).fetchall()

        if not messages:
            continue

        safe_name = chat_folder_map.get(conv_id)
        if not safe_name:
            safe_name = sanitize_filename(conv_title or conv_id or 'Unknown')

        # Determine partner info for renderer header
        display_title = conv_title
        if not display_title:
            for msg in messages:
                if msg[6]:
                    display_title = msg[6]
                    break

        partner_username = None
        partner_display = None
        has_uuid_id = bool(UUID_RE.match(conv_id))
        if not has_uuid_id:
            partner_username = conv_id
            partner_display = friends.get(conv_id)

        other_users = []
        other_users_set = set()
        for msg in messages:
            u = msg[0]
            if u and not msg[5] and u not in other_users_set:
                other_users_set.add(u)
                other_users.append(u)

        if not partner_username and other_users:
            partner_username = other_users[0]
            partner_display = friends.get(other_users[0])

        # Build media path map for this conversation
        msg_ids = [row[7] for row in messages if row[7] is not None]
        media_path_map = {}
        if msg_ids:
            _CHUNK = 500
            for _i in range(0, len(msg_ids), _CHUNK):
                _chunk = msg_ids[_i:_i + _CHUNK]
                placeholders = ','.join('?' * len(_chunk))
                path_rows = db.execute(
                    f"""SELECT cmi.chat_message_id, a.output_path
                        FROM chat_media_ids cmi
                        JOIN assets a ON a.file_id = cmi.media_id
                        WHERE cmi.chat_message_id IN ({placeholders})
                          AND a.output_path IS NOT NULL
                          AND a.asset_type IN ('chat', 'chat_overlay', 'chat_thumbnail')""",
                    _chunk
                ).fetchall()
                for mid, opath in path_rows:
                    if mid not in media_path_map:
                        media_path_map[mid] = opath

        # Create renderer
        renderer_name = partner_display or partner_username or display_title or 'Unknown'
        renderer = ChatRenderer(username=renderer_name, dark_mode=dark_mode)

        # Convert DB rows to ChatMessage objects
        chat_messages = []
        for msg_row in messages:
            from_user, media_type, content, created, created_ms, \
                is_sender, msg_conv_title, msg_id = msg_row

            if is_sender:
                display_name = 'Me'
            elif from_user and friends.get(from_user):
                display_name = friends[from_user]
            elif from_user:
                display_name = f"@{from_user}"
            else:
                display_name = 'Unknown'

            # Compute timestamp in seconds from created_ms
            if created_ms:
                ts_sec = created_ms / 1_000
            elif created:
                dt = parse_snap_date(created)
                ts_sec = dt.timestamp() if dt else 0
            else:
                ts_sec = 0

            media_path = media_path_map.get(msg_id) if msg_id is not None else None

            chat_messages.append(ChatMessage(
                sender=display_name,
                text=content or "",
                timestamp=ts_sec,
                is_self=bool(is_sender),
                media_path=media_path,
                media_type=media_type.lower() if media_type else None,
            ))

        # Render to PNG pages
        conv_png_dir = chat_out_dir / safe_name / 'Saved Chat Screenshots'
        conv_png_dir.mkdir(parents=True, exist_ok=True)
        try:
            pages = renderer.render_conversation(chat_messages, conv_png_dir)
            total_pages += len(pages)
        except Exception as e:
            logger.warning(f"Failed to render PNG for {safe_name}: {e}")

        total_convs += 1
        if (conv_idx + 1) % 25 == 0 and progress_cb:
            progress_cb(
                f"Chat screenshots: {conv_idx + 1}/{len(conversations)} "
                f"({total_pages} pages)"
            )

    elapsed = time.time() - t0
    logger.info(f"Chat PNG: {total_convs} conversations, {total_pages} pages ({elapsed:.1f}s)")

    if progress_cb:
        progress_cb(f"Chat screenshots: {total_convs} conversations ({total_pages} pages)")

    return {
        'conversations': total_convs,
        'pages': total_pages,
        'elapsed': elapsed,
    }


# ── Report Generation ───────────────────────────────────────────────────────


def write_reports(
    db: sqlite3.Connection,
    project_dir: Path,
    config: Config,
    stats: dict,
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    """Write human-readable report.txt and machine-readable report.json.

    Reports placed in: project_dir/.snatched/

    Returns:
        {'report_txt': Path, 'report_json': Path, 'elapsed': float}
    """
    t0 = time.time()

    if progress_cb:
        progress_cb("Writing audit reports...")

    snatched_dir = project_dir / '.snatched'
    snatched_dir.mkdir(parents=True, exist_ok=True)

    # Query all report stats
    total_assets = db.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
    total_best = db.execute(
        "SELECT COUNT(*) FROM matches WHERE is_best = 1").fetchone()[0]

    strategy_counts = db.execute("""
        SELECT strategy, COUNT(*), AVG(confidence)
        FROM matches WHERE is_best = 1
        GROUP BY strategy
        ORDER BY AVG(confidence) DESC
    """).fetchall()

    gps_sources = db.execute("""
        SELECT
            COALESCE(gps_source, 'none') as src,
            COUNT(*)
        FROM matches WHERE is_best = 1
        GROUP BY src
    """).fetchall()

    type_counts = db.execute("""
        SELECT a.asset_type, COUNT(*)
        FROM assets a
        GROUP BY a.asset_type
    """).fetchall()

    year_breakdown = db.execute("""
        SELECT
            SUBSTR(m.matched_date, 1, 4) as year,
            COUNT(*)
        FROM matches m
        JOIN assets a ON m.asset_id = a.id
        WHERE m.is_best = 1
          AND a.asset_type = 'memory_main'
          AND m.matched_date IS NOT NULL
        GROUP BY year
        ORDER BY year
    """).fetchall()

    file_type_counts = db.execute("""
        SELECT a.asset_type, a.ext, COUNT(*)
        FROM assets a
        GROUP BY a.asset_type, a.ext
        ORDER BY a.asset_type, COUNT(*) DESC
    """).fetchall()

    overlays_total = db.execute(
        "SELECT COUNT(*) FROM assets WHERE asset_type = 'memory_overlay'"
    ).fetchone()[0]
    orphan_overlays = db.execute("""
        SELECT ov.filename, ov.asset_type, ov.date_str
        FROM assets ov
        WHERE ov.asset_type = 'memory_overlay'
          AND ov.memory_uuid NOT IN (
              SELECT memory_uuid FROM assets
              WHERE asset_type = 'memory_main' AND memory_uuid IS NOT NULL
          )
        ORDER BY ov.filename
    """).fetchall()
    overlays_burned = overlays_total - len(orphan_overlays)

    true_unmatched = db.execute("""
        SELECT a.filename, a.asset_type, a.date_str
        FROM assets a
        LEFT JOIN matches m ON a.id = m.asset_id AND m.is_best = 1
        WHERE m.id IS NULL
          AND a.asset_type NOT IN ('chat_overlay', 'chat_thumbnail', 'memory_overlay')
        ORDER BY a.asset_type, a.filename
    """).fetchall()

    filtered_assets = db.execute(
        "SELECT COUNT(*) FROM assets WHERE asset_type IN ('chat_overlay', 'chat_thumbnail')"
    ).fetchone()[0]

    mem_total = db.execute(
        "SELECT COUNT(*) FROM assets WHERE asset_type = 'memory_main'"
    ).fetchone()[0]
    mem_gps = db.execute("""
        SELECT COUNT(*) FROM matches m
        JOIN assets a ON m.asset_id = a.id
        WHERE m.is_best = 1 AND a.asset_type = 'memory_main'
          AND m.matched_lat IS NOT NULL
    """).fetchone()[0]
    mem_overlays = db.execute(
        "SELECT COUNT(*) FROM assets WHERE asset_type = 'memory_overlay'"
    ).fetchone()[0]

    chat_total = db.execute(
        "SELECT COUNT(*) FROM assets WHERE asset_type = 'chat'"
    ).fetchone()[0]

    story_total = db.execute(
        "SELECT COUNT(*) FROM assets WHERE asset_type = 'story'"
    ).fetchone()[0]
    story_matched = db.execute("""
        SELECT COUNT(*) FROM matches m
        JOIN assets a ON m.asset_id = a.id
        WHERE m.is_best = 1 AND a.asset_type = 'story'
    """).fetchone()[0]

    exif_written = db.execute(
        "SELECT COUNT(*) FROM assets WHERE exif_written = 1"
    ).fetchone()[0]
    exif_errors_count = db.execute(
        "SELECT COUNT(*) FROM assets WHERE exif_error IS NOT NULL"
    ).fetchone()[0]

    conv_count = db.execute(
        "SELECT COUNT(DISTINCT conversation_id) FROM chat_messages"
    ).fetchone()[0]

    elapsed_total = stats.get('total_elapsed', 0)

    # Write report.txt
    report_path = snatched_dir / 'report.txt'
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(f"Snatched v{VERSION} -- Audit Report\n")
        f.write(f"Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
        mins = int(elapsed_total // 60)
        secs = int(elapsed_total % 60)
        ts = f"{mins}m {secs}s" if mins else f"{secs}s"
        f.write(f"Duration: {ts}\n")
        f.write(f"{'=' * 64}\n\n")

        eligible = total_assets - mem_overlays - filtered_assets
        f.write("SUMMARY\n")
        f.write(f"  Total assets:      {total_assets:,}\n")
        f.write(f"  Eligible:          {eligible:,} (assets producing standalone output)\n")
        f.write(f"  Best matches:      {total_best:,}\n")
        f.write(f"  Overlays burned:   {overlays_burned:,} (composited onto parent files)\n")
        if len(orphan_overlays):
            f.write(f"  Orphan overlays:   {len(orphan_overlays):,} (parent deleted by Snapchat)\n")
        if len(true_unmatched):
            f.write(f"  True unmatched:    {len(true_unmatched):,} (no match, not an overlay)\n")
        if filtered_assets:
            f.write(f"  Filtered:          {filtered_assets:,} (chat overlays/thumbnails)\n")
        f.write(f"  ---\n")
        accounted = total_best + overlays_burned + len(orphan_overlays) + len(true_unmatched) + filtered_assets
        f.write(f"  Accounted:         {accounted:,} / {total_assets:,}\n")
        f.write(f"\n")
        f.write(f"  Memories:      {mem_total:,} (GPS: {mem_gps:,}, Overlays: {mem_overlays:,})\n")
        f.write(f"  Chat:          {chat_total:,}\n")
        f.write(f"  Stories:       {story_total:,} (Matched: {story_matched:,})\n\n")

        f.write(f"{'=' * 64}\n")
        f.write("MATCH STRATEGY BREAKDOWN\n")
        for strategy, count, avg_conf in strategy_counts:
            f.write(f"  {strategy:.<35} {count:>6,}  (avg confidence: {avg_conf:.2f})\n")
        f.write(f"\n")

        f.write(f"{'=' * 64}\n")
        f.write("GPS SOURCE BREAKDOWN\n")
        for src, count in gps_sources:
            f.write(f"  {src:.<35} {count:>6,}\n")
        f.write(f"\n")

        f.write(f"{'=' * 64}\n")
        f.write("YEAR BREAKDOWN (memories)\n")
        if year_breakdown:
            for year, count in year_breakdown:
                if year:
                    f.write(f"  {year}: {count:>5,} files\n")
            total_yr = sum(c for _, c in year_breakdown if _)
            f.write(f"  {'─' * 20}\n")
            f.write(f"  Total: {total_yr:>5,}\n")
        else:
            f.write("  (no dated memories)\n")
        f.write(f"\n")

        f.write(f"{'=' * 64}\n")
        f.write("FILE TYPE BREAKDOWN\n")
        current_type = None
        for atype, ext, count in file_type_counts:
            if atype != current_type:
                current_type = atype
                f.write(f"  {atype}:\n")
            f.write(f"    {ext:.<20} {count:>6,}\n")
        f.write(f"\n")

        f.write(f"{'=' * 64}\n")
        f.write("EXIF EMBEDDING\n")
        f.write(f"  Written:  {exif_written:,}\n")
        f.write(f"  Errors:   {exif_errors_count:,}\n")
        f.write(f"\n")

        f.write(f"{'=' * 64}\n")
        f.write("ORPHAN OVERLAYS (parent deleted by Snapchat)\n")
        if orphan_overlays:
            for filename, atype, date_str in orphan_overlays:
                date_info = f" (date: {date_str})" if date_str else ""
                f.write(f"  {filename}{date_info}\n")
        else:
            f.write("  (none)\n")
        f.write(f"\n")

        f.write(f"{'=' * 64}\n")
        f.write("TRUE UNMATCHED FILES (no match, not an overlay)\n")
        if true_unmatched:
            for filename, atype, date_str in true_unmatched:
                date_info = f" (date: {date_str})" if date_str else ""
                f.write(f"  {filename} [{atype}]{date_info}\n")
        else:
            f.write("  (none)\n")
        f.write(f"\n")

        f.write(f"{'=' * 64}\n")
        f.write("WARNINGS\n")
        warnings = []
        no_gps_mems = db.execute("""
            SELECT COUNT(*) FROM matches m
            JOIN assets a ON m.asset_id = a.id
            WHERE m.is_best = 1 AND a.asset_type = 'memory_main'
              AND m.matched_lat IS NULL
        """).fetchone()[0]
        if no_gps_mems:
            msg = f"{no_gps_mems} memories with no GPS coordinates"
            f.write(f"  {msg}\n")
            warnings.append(msg)

        date_only = db.execute(
            "SELECT COUNT(*) FROM matches WHERE is_best = 1 AND strategy = 'date_only'"
        ).fetchone()[0]
        if date_only:
            msg = (f"{date_only} files with date-only timestamp "
                   "(no JSON match, time set to 00:00:00)")
            f.write(f"  {msg}\n")
            warnings.append(msg)

        fmp4_count = db.execute(
            "SELECT COUNT(*) FROM assets WHERE is_fmp4 = 1").fetchone()[0]
        if fmp4_count:
            msg = f"{fmp4_count} fragmented MP4 files detected (remuxed during copy)"
            f.write(f"  {msg}\n")
            warnings.append(msg)

        format_mismatches = db.execute(
            "SELECT COUNT(*) FROM assets WHERE real_ext IS NOT NULL"
        ).fetchone()[0]
        if format_mismatches:
            msg = f"{format_mismatches} format mismatches detected (e.g. .png actually .webp)"
            f.write(f"  {msg}\n")
            warnings.append(msg)

        if not warnings:
            f.write("  (none)\n")

    # Write report.json
    strat_dict = {}
    for strategy, count, avg_conf in strategy_counts:
        strat_dict[strategy] = {
            'count': count,
            'avg_confidence': round(avg_conf, 2),
        }

    chat_strats = {}
    chat_strat_rows = db.execute("""
        SELECT m.strategy, COUNT(*)
        FROM matches m
        JOIN assets a ON m.asset_id = a.id
        WHERE m.is_best = 1 AND a.asset_type = 'chat'
        GROUP BY m.strategy
    """).fetchall()
    for s, c in chat_strat_rows:
        chat_strats[s] = c

    gps_dict = {}
    for src, count in gps_sources:
        gps_dict[src] = count

    year_dict = {}
    for year, count in year_breakdown:
        if year:
            year_dict[year] = count

    mem_matched = db.execute("""
        SELECT COUNT(*) FROM matches m
        JOIN assets a ON m.asset_id = a.id
        WHERE m.is_best = 1 AND a.asset_type = 'memory_main'
    """).fetchone()[0]

    report_json = {
        'version': VERSION,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'elapsed_seconds': round(elapsed_total, 1),
        'output': str(project_dir / 'output'),
        'counts': {
            'total_assets': total_assets,
            'memories': {
                'total': mem_total,
                'matched': mem_matched,
                'gps': mem_gps,
                'overlays': mem_overlays,
            },
            'chat': {
                'total': chat_total,
                **chat_strats,
            },
            'stories': {
                'total': story_total,
                'matched': story_matched,
            },
            'text_conversations': conv_count,
        },
        'match_strategies': strat_dict,
        'gps_sources': gps_dict,
        'year_breakdown': year_dict,
        'exif': {
            'written': exif_written,
            'errors': exif_errors_count,
            'no_exif_needed': max(0, total_best - exif_written - exif_errors_count),
        },
        'accounting': {
            'total_assets': total_assets,
            'matched': total_best,
            'overlays_burned': overlays_burned,
            'orphan_overlays': len(orphan_overlays),
            'true_unmatched': len(true_unmatched),
            'filtered': filtered_assets,
        },
        'warnings': warnings,
    }

    json_path = snatched_dir / 'report.json'
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(report_json, f, indent=2, ensure_ascii=False)

    elapsed = time.time() - t0
    logger.info(f"Reports written in {elapsed:.1f}s")

    if progress_cb:
        progress_cb("Reports written")

    return {
        'report_txt': str(report_path),
        'report_json': str(json_path),
        'elapsed': elapsed,
    }


# ── Phase 4 Orchestrator ───────────────────────────────────────────────────


def phase4_export(
    db: sqlite3.Connection,
    project_dir: Path,
    config: Config,
    lanes: list[str] | None = None,
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    """Phase 4 orchestrator: Export all enriched files.

    Sequentially calls:
    1. copy_files()
    2. burn_overlays()
    3. write_exif()
    4. export_chat_text()
    5. export_chat_png()
    6. write_reports()

    Args:
        db: SQLite connection
        project_dir: Root project directory
        config: Configuration
        lanes: Optional lane filter. None = process all.
        progress_cb: Optional progress callback

    Returns combined stats dict.
    """
    t0 = time.time()

    if progress_cb:
        progress_cb("Starting Phase 4: Export...")

    total_best = db.execute(
        "SELECT COUNT(*) FROM matches WHERE is_best = 1").fetchone()[0]
    if total_best == 0:
        logger.warning("No best matches found. Run Phases 1-3 first.")
        if progress_cb:
            progress_cb("Phase 4: No best matches found")
        return {'total': 0}

    logger.info(f"Phase 4: {total_best} best matches to export")

    stats = {'total': total_best}

    # 1. Copy files
    copy_stats = copy_files(db, project_dir, config, lanes=lanes, progress_cb=progress_cb)
    stats['copy'] = copy_stats

    # 2. Burn overlays (requires files to be copied first)
    memories_lane = config.lanes.get('memories')
    do_overlays = memories_lane.burn_overlays if memories_lane else True
    if do_overlays and copy_stats.get('copied', 0) > 0:
        overlay_stats = burn_overlays(db, project_dir, config, progress_cb)
    else:
        overlay_stats = {'burned': 0, 'errors': 0, 'elapsed': 0.0}
    stats['overlays'] = overlay_stats

    # 3. Write EXIF (after overlays so burned files get re-tagged)
    if config.exif.enabled and copy_stats.get('copied', 0) > 0:
        exif_stats = write_exif(db, project_dir, config, progress_cb)
    else:
        exif_stats = {'written': 0, 'errors': 0, 'skipped': 0, 'elapsed': 0.0}
    stats['exif'] = exif_stats

    # XMP sidecar files
    if config.xmp.enabled and copy_stats.get('copied', 0) > 0:
        try:
            from snatched.processing.xmp import write_xmp_sidecars
            xmp_stats = write_xmp_sidecars(db, project_dir, config, progress_cb)
            stats['xmp'] = xmp_stats
            if progress_cb:
                progress_cb(f"XMP sidecars: {xmp_stats.get('written', 0)} written")
        except ImportError:
            logger.warning("XMP module not available, skipping sidecar generation")
        except Exception as e:
            logger.error(f"XMP sidecar generation failed: {e}")
            stats['xmp'] = {'error': str(e)}

    # 4. Chat text export
    chats_lane = config.lanes.get('chats')
    do_text = chats_lane.export_text if chats_lane else True
    if do_text and (lanes is None or 'chats' in lanes):
        text_stats = export_chat_text(db, project_dir, config, progress_cb)
    else:
        text_stats = {'conversations': 0, 'messages': 0, 'elapsed': 0.0}
    stats['text'] = text_stats

    # 5. Chat PNG export
    do_png = chats_lane.export_png if chats_lane else True
    if do_png and (lanes is None or 'chats' in lanes):
        png_stats = export_chat_png(db, project_dir, config, progress_cb)
    else:
        png_stats = {'conversations': 0, 'pages': 0, 'elapsed': 0.0}
    stats['png'] = png_stats

    elapsed = time.time() - t0
    stats['total_elapsed'] = elapsed

    # 6. Write reports (after everything else)
    report_stats = write_reports(db, project_dir, config, stats, progress_cb)
    stats['reports'] = report_stats

    # Update total elapsed after reports
    elapsed = time.time() - t0
    stats['total_elapsed'] = elapsed

    logger.info(
        f"Phase 4 complete in {elapsed:.1f}s: "
        f"copied={copy_stats.get('copied', 0)}, "
        f"remuxed={copy_stats.get('remuxed', 0)}, "
        f"exif={exif_stats.get('written', 0)}, "
        f"overlays={overlay_stats.get('burned', 0)}, "
        f"chat_convs={text_stats.get('conversations', 0)}, "
        f"chat_pages={png_stats.get('pages', 0)}"
    )

    if progress_cb:
        progress_cb(f"Phase 4 complete in {elapsed:.1f}s")

    return {
        'copied': copy_stats.get('copied', 0),
        'remuxed': copy_stats.get('remuxed', 0),
        'burned': overlay_stats.get('burned', 0),
        'exif_written': exif_stats.get('written', 0),
        'chat_conversations': text_stats.get('conversations', 0),
        'chat_messages': text_stats.get('messages', 0),
        'chat_pages': png_stats.get('pages', 0),
        'elapsed': elapsed,
    }
