"""Utility functions for snatched v3.

Ported from snatched.py (v2 monolith) with type hints, logging, and docstrings.
Includes regex patterns, magic byte constants, and core helpers for:
- Date/time parsing (Snapchat formats)
- Location extraction
- File format detection and validation
- Filename sanitization
- EXIF tag generation for photos/videos
"""

import re
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)

# ── Compiled Regex Patterns ──────────────────────────────────────────────────

MEMORY_RE = re.compile(
    r'^(\d{4}-\d{2}-\d{2})_(.+?)-(main|overlay)\.([^.]+)$')
"""Memory filename pattern: YYYY-MM-DD_<name>-{main|overlay}.<ext>"""

CHAT_FILE_RE = re.compile(r'^(\d{4}-\d{2}-\d{2})_(.+)\.([^.]+)$')
"""Chat filename pattern: YYYY-MM-DD_<name>.<ext>"""

LOCATION_RE = re.compile(
    r'Latitude,\s*Longitude:\s*([\d.eE+-]+),\s*([\d.eE+-]+)')
"""GPS location pattern: 'Latitude, Longitude: lat, lon'"""

LOCATION_UNCERTAINTY_RE = re.compile(
    r'([\d.eE+-]+)\s*±\s*[\d.eE+-]+\s*,\s*([\d.eE+-]+)\s*±\s*[\d.eE+-]+')
"""GPS location pattern with uncertainty: 'lat ± accuracy, lon ± accuracy'"""

UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
"""UUID v4 validation pattern (lowercase, no braces)"""

UNSAFE_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
"""Characters illegal in filenames (Windows + Linux safe)"""

# ── Magic Bytes ──────────────────────────────────────────────────────────────

RIFF_MAGIC = b'RIFF'
"""RIFF container magic (WebP, WAV, AVI)"""

FMP4_STYP = b'styp'
"""Fragmented MP4 segment type box marker"""

# ── File Extensions ──────────────────────────────────────────────────────────

VIDEO_EXTS = {'.mp4', '.mov', '.m4v', '.3gp', '.avi', '.webm'}
"""Recognized video file extensions"""

VERSION = '3.0'
"""Snatched version string (embedded in EXIF Software tag)"""


# ── Date/Time Parsing ────────────────────────────────────────────────────────

def parse_snap_date(s: str) -> datetime | None:
    """Parse Snapchat date string to timezone-aware UTC datetime.

    Handles format: '2026-02-20 08:17:52 UTC'
    Returns None for None input or unparseable strings.

    Args:
        s: Snapchat date string

    Returns:
        datetime with tzinfo=UTC, or None
    """
    if not s:
        return None
    try:
        return datetime.strptime(s.replace(' UTC', '').strip(),
                                 "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return None


def parse_snap_date_iso(s: str) -> str | None:
    """Parse Snapchat date string to ISO 8601 format.

    Returns: '2026-02-20T08:17:52+00:00' or None
    """
    dt = parse_snap_date(s)
    if dt:
        return dt.isoformat()
    return None


def parse_snap_date_dateonly(s: str) -> str | None:
    """Parse Snapchat date string, return date portion only.

    Returns: 'YYYY-MM-DD' or None
    """
    dt = parse_snap_date(s)
    if dt:
        return dt.strftime('%Y-%m-%d')
    return None


def parse_iso_dt(s: str) -> datetime | None:
    """Parse ISO 8601 string to timezone-aware datetime.

    Args:
        s: ISO 8601 date string

    Returns:
        datetime with UTC tzinfo, or None
    """
    if not s:
        return None
    try:
        s = s.replace('+00:00', '').replace('Z', '')
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S").replace(
            tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return None


def exif_dt(dt: datetime) -> str:
    """Format datetime for EXIF tag value.

    Returns:
        String in EXIF format: '2026:02:20 08:17:52'
    """
    return dt.strftime("%Y:%m:%d %H:%M:%S")


def format_chat_date(s: str) -> str | None:
    """Format a Snapchat date string for chat transcript display.

    Args:
        s: Snapchat date string ('2026-02-20 08:17:52 UTC')

    Returns:
        Display string ('2026-02-20 08:17:52')
    """
    if not s:
        return None
    return s.replace(' UTC', '').strip()


# ── Location Parsing ────────────────────────────────────────────────────────

def parse_location(s: str) -> tuple[float, float] | None:
    """Parse Snapchat location string to (lat, lon).

    Handles formats:
    - 'Latitude, Longitude: 39.56, -89.65'
    - '39.56 ± 10.5, -89.65 ± 10.5'

    Returns:
        (lat, lon) float tuple, or None if unparseable
    """
    if not s:
        return None
    # Try "Latitude, Longitude: lat, lon" format first
    m = LOCATION_RE.search(s)
    if not m:
        # Try "lat ± accuracy, lon ± accuracy" format
        m = LOCATION_UNCERTAINTY_RE.search(s)
    if not m:
        return None
    lat, lon = float(m.group(1)), float(m.group(2))
    if lat == 0.0 and lon == 0.0:
        return None
    return (lat, lon)


# ── URL/ID Extraction ────────────────────────────────────────────────────────

def extract_mid(url: str) -> str | None:
    """Extract 'mid' query parameter from Snapchat download URL.

    Args:
        url: Full download URL from memories_history.json

    Returns:
        UUID string, or None if not found
    """
    if not url:
        return None
    try:
        return parse_qs(urlparse(url).query).get('mid', [None])[0]
    except Exception:
        return None


# ── File Format Detection ────────────────────────────────────────────────────

def detect_real_format(path: Path) -> str | None:
    """Detect actual file format by reading magic bytes.

    Checks if file's extension matches actual format.
    Returns corrected extension if mismatched (e.g., '.webp' for a renamed .jpg).
    Returns None if extension matches actual format.

    Args:
        path: Path to file to inspect

    Returns:
        Corrected extension string (e.g., '.webp'), or None
    """
    try:
        with open(path, 'rb') as f:
            header = f.read(12)
    except (OSError, IOError):
        return None
    ext = Path(path).suffix.lower()
    if header[:4] == RIFF_MAGIC and len(header) >= 12 and header[8:12] == b'WEBP':
        if ext != '.webp':
            return '.webp'
    return None


def is_fragmented_mp4(path: Path) -> bool:
    """Check if MP4 uses fragmented (fMP4) container.

    fMP4 files require ffmpeg remux before EXIF embedding works correctly.

    Args:
        path: Path to MP4 file

    Returns:
        True if file uses fragmented MP4 container
    """
    try:
        with open(path, 'rb') as f:
            data = f.read(4096)
    except (OSError, IOError):
        return False
    return FMP4_STYP in data or b'moof' in data


def is_video(path: Path) -> bool:
    """Check if path has a recognized video extension.

    Args:
        path: File path to check

    Returns:
        True if extension is in VIDEO_EXTS
    """
    return Path(path).suffix.lower() in VIDEO_EXTS


# ── File Hashing ────────────────────────────────────────────────────────────

def sha256_file(path: Path) -> str | None:
    """Compute SHA-256 hex digest of a file.

    Reads in 64KB chunks to avoid loading large files into memory.

    Args:
        path: Path to file

    Returns:
        64-character lowercase hex string, or None on read error
    """
    h = hashlib.sha256()
    try:
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                h.update(chunk)
        return h.hexdigest()
    except (OSError, IOError):
        return None


# ── Filename Sanitization ────────────────────────────────────────────────────

def sanitize_filename(name: str) -> str:
    """Sanitize a string for safe use as a filename or directory component.

    Replaces illegal characters, collapses multiple underscores,
    strips leading/trailing whitespace and dots.

    Args:
        name: Arbitrary string

    Returns:
        Filesystem-safe string (no special characters)
    """
    if not name:
        return 'Unknown'
    name = UNSAFE_FILENAME_RE.sub('_', name)
    name = name.strip('. ')
    if not name:
        return 'Unknown'
    if len(name) > 120:
        name = name[:120]
    return name


def safe_user_path(base_dir: Path, user_path: str) -> Path:
    """Resolve user_path relative to base_dir, validate it stays within base_dir.

    Prevents path traversal attacks (e.g., '../../etc/passwd').

    Args:
        base_dir: Trusted base directory (e.g., Path('/data'))
        user_path: Untrusted path component (e.g., 'dave/proc.db')

    Returns:
        Resolved absolute Path within base_dir

    Raises:
        ValueError: If resolved path escapes base_dir
    """
    base_dir = Path(base_dir).resolve()
    resolved = (base_dir / user_path).resolve()

    # Ensure resolved path is within base_dir
    try:
        resolved.relative_to(base_dir)
    except ValueError:
        raise ValueError(
            f"Path traversal detected: {user_path} escapes {base_dir}"
        )

    return resolved


# ── EXIF Tag Generation ──────────────────────────────────────────────────────

def gps_tags(lat: float, lon: float, is_video: bool, dt: datetime | None = None) -> dict:
    """Build GPS EXIF tag dict for photos or videos.

    Args:
        lat: Latitude in decimal degrees
        lon: Longitude in decimal degrees
        is_video: True if file is video (uses different tag names)
        dt: Optional datetime for GPS timestamp tags

    Returns:
        Dict of {exif_tag_name: value, ...}
    """
    if is_video:
        return {
            'Keys:GPSCoordinates': f"{lat} {lon}",
            'XMP:GPSLatitude': str(lat),
            'XMP:GPSLongitude': str(lon),
        }
    tags = {
        'GPSLatitude': str(abs(lat)),
        'GPSLatitudeRef': 'N' if lat >= 0 else 'S',
        'GPSLongitude': str(abs(lon)),
        'GPSLongitudeRef': 'E' if lon >= 0 else 'W',
    }
    if dt:
        tags['GPSDateStamp'] = dt.strftime("%Y:%m:%d")
        tags['GPSTimeStamp'] = dt.strftime("%H:%M:%S")
    return tags


def date_tags(dt: datetime, is_video: bool, subsec_ms: int | None = None) -> dict:
    """Build date/time EXIF tag dict for photos or videos.

    Args:
        dt: Datetime to embed
        is_video: True if file is video
        subsec_ms: Optional subsecond millisecond value

    Returns:
        Dict of {exif_tag_name: value, ...}
    """
    ed = exif_dt(dt)
    if is_video:
        xd = ed + "+00:00"
        return {
            'QuickTime:CreateDate': ed,
            'QuickTime:ModifyDate': ed,
            'XMP:DateTimeOriginal': xd,
            'XMP:CreateDate': xd,
        }
    tags = {
        'DateTimeOriginal': ed,
        'CreateDate': ed,
        'ModifyDate': ed,
        'OffsetTimeOriginal': '+00:00',
    }
    if subsec_ms is not None:
        tags['SubSecDateTimeOriginal'] = f"{ed}.{subsec_ms:03d}"
    else:
        tags['SubSecDateTimeOriginal'] = f"{ed}.000"
    return tags
