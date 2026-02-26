"""XMP sidecar file generation for exported media assets.

New in v3 — generates XMP sidecar files as an alternative to (or alongside)
embedded EXIF metadata. Useful for photo management apps like Immich that
can read XMP sidecars.
"""

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Callable
from xml.sax.saxutils import escape as escape_xml

from snatched.config import Config
from snatched.utils import VERSION

logger = logging.getLogger(__name__)


def generate_xmp(match_row: dict, config: Config) -> str:
    """Generate a complete XMP XML document for a single match.

    Combines date/time, GPS, creator, conversation, and Snatched
    namespace metadata into valid XMP 1.0 document.

    Args:
        match_row: Dict with keys from matches JOIN assets query.
        config: Config object for version string.

    Returns:
        Complete XMP XML string.
    """
    tags = {}

    # Date tags
    matched_date = match_row.get('matched_date')
    if matched_date:
        tags['exif:DateTimeOriginal'] = matched_date
        tags['xmp:CreateDate'] = matched_date

    # GPS tags
    lat = match_row.get('matched_lat')
    lon = match_row.get('matched_lon')
    if lat is not None and lon is not None:
        tags['exif:GPSLatitude'] = str(lat)
        tags['exif:GPSLongitude'] = str(lon)

    # Creator / contributor
    creator_str = match_row.get('creator_str')
    if creator_str:
        tags['dc:creator'] = creator_str

    # Conversation
    conversation = match_row.get('conversation')
    if conversation:
        tags['dc:subject'] = conversation

    # Direction
    direction = match_row.get('direction')
    if direction:
        tags['dc:description'] = 'Sent' if direction == 'sent' else 'Received'

    # Display name
    display_name = match_row.get('display_name')
    if display_name:
        tags['xmp:Creator'] = display_name

    # Snatched metadata
    snatched_meta = {
        'version': VERSION,
        'strategy': match_row.get('strategy', ''),
        'confidence': match_row.get('confidence', 0.0),
        'source_type': 'snapchat',
        'file_id': match_row.get('file_id') or match_row.get('memory_uuid') or '',
    }

    return build_xmp_xml(tags, snatched_meta)


def build_xmp_xml(tags: dict, snatched_meta: dict) -> str:
    """Render XMP XML from a tag dictionary.

    Generates valid XMP 1.0 document with proper namespace declarations.

    Args:
        tags: Dict of {tag_name: value}
        snatched_meta: Dict with version, strategy, confidence, source_type, file_id

    Returns:
        Properly formatted XMP XML string with all values XML-escaped.
    """
    tags_xml = '\n'.join(
        f'      <{k}>{escape_xml(str(v))}</{k}>'
        for k, v in tags.items()
    )

    file_id = escape_xml(str(snatched_meta.get('file_id', 'unknown')))
    version = escape_xml(str(snatched_meta.get('version', VERSION)))
    strategy = escape_xml(str(snatched_meta.get('strategy', '')))
    confidence = snatched_meta.get('confidence', 0.0)
    source_type = escape_xml(str(snatched_meta.get('source_type', 'snapchat')))

    include_ns = True  # Always include snatched namespace for provenance

    snatched_xml = ""
    if include_ns:
        snatched_xml = (
            f'\n      <snatched:version>{version}</snatched:version>'
            f'\n      <snatched:strategy>{strategy}</snatched:strategy>'
            f'\n      <snatched:confidence>{confidence:.2f}</snatched:confidence>'
            f'\n      <snatched:sourceType>{source_type}</snatched:sourceType>'
        )

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="Snatched v{version}">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:Description rdf:about=""
        xmlns:dc="http://purl.org/dc/elements/1.1/"
        xmlns:exif="http://ns.adobe.com/exif/1.0/"
        xmlns:xmp="http://ns.adobe.com/xap/1.0/"
        xmlns:xmpMM="http://ns.adobe.com/xap/1.0/mm/"
        xmlns:snatched="http://snatched.app/ns/1.0/">
{tags_xml}
      <xmpMM:DocumentID>snatched://{file_id}</xmpMM:DocumentID>{snatched_xml}
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>'''


def write_xmp_sidecars(
    db: sqlite3.Connection,
    project_dir: Path,
    config: Config,
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    """Write XMP sidecar files for all exported assets.

    Sidecar naming: {output_path}.xmp (appended, not replaced).
    Example: Snap_Memory_2025-01-15_143022.jpg.xmp

    Skips assets with no output_path.

    Returns:
        {'written': int, 'skipped': int, 'errors': int, 'elapsed': float}
    """
    t0 = time.time()

    if progress_cb:
        progress_cb("Writing XMP sidecar files...")

    rows = db.execute("""
        SELECT
            m.id as match_id,
            m.matched_date, m.matched_lat, m.matched_lon, m.gps_source,
            m.display_name, m.creator_str, m.direction, m.conversation,
            m.strategy, m.confidence,
            a.id as asset_id, a.output_path, a.file_id, a.memory_uuid
        FROM matches m
        JOIN assets a ON m.asset_id = a.id
        WHERE m.is_best = 1
    """).fetchall()

    written = 0
    skipped = 0
    errors = 0

    for row in rows:
        (match_id, matched_date, matched_lat, matched_lon, gps_source,
         display_name, creator_str, direction, conversation,
         strategy, confidence,
         asset_id, output_path, file_id, memory_uuid) = row

        if not output_path:
            skipped += 1
            continue

        output_p = Path(output_path)
        if not output_p.exists():
            skipped += 1
            continue

        match_row = {
            'matched_date': matched_date,
            'matched_lat': matched_lat,
            'matched_lon': matched_lon,
            'gps_source': gps_source,
            'display_name': display_name,
            'creator_str': creator_str,
            'direction': direction,
            'conversation': conversation,
            'strategy': strategy,
            'confidence': confidence,
            'file_id': file_id,
            'memory_uuid': memory_uuid,
        }

        try:
            xmp_content = generate_xmp(match_row, config)
            xmp_path = Path(str(output_path) + '.xmp')
            xmp_path.write_text(xmp_content, encoding='utf-8')

            db.execute(
                "UPDATE assets SET xmp_written=1, xmp_path=? WHERE id=?",
                (str(xmp_path), asset_id))
            written += 1

        except Exception:
            logger.exception(f"Failed to write XMP for {output_path}")
            errors += 1

        if written % 100 == 0 and written > 0 and progress_cb:
            progress_cb(f"XMP sidecars: {written} written...")

    db.commit()

    elapsed = time.time() - t0
    logger.info(
        f"XMP sidecars: {written} written, {skipped} skipped, "
        f"{errors} errors ({elapsed:.1f}s)"
    )

    if progress_cb:
        progress_cb(f"XMP sidecars: {written} written ({errors} errors)")

    return {
        'written': written,
        'skipped': skipped,
        'errors': errors,
        'elapsed': elapsed,
    }
