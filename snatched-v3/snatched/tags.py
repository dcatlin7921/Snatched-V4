"""Tag reading and writing utilities using exiftool.

All operations are async-safe via run_in_executor.
Exiftool is the sole EXIF/XMP backend — no Python EXIF libraries.
"""

import asyncio
import json
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger("snatched.tags")


async def read_tags(file_path: str) -> dict:
    """Read all EXIF/XMP/IPTC tags from a file using exiftool -json.

    Returns a flat dict of GroupName:TagName -> value.
    Uses -G (group names) and -n (numeric values for GPS etc).
    """
    loop = asyncio.get_running_loop()

    def _read():
        try:
            result = subprocess.run(
                ["exiftool", "-json", "-G", "-n", str(file_path)],
                capture_output=True, text=True, timeout=30,
            )
        except FileNotFoundError:
            logger.error("exiftool not found on PATH")
            return {}
        except subprocess.TimeoutExpired:
            logger.error(f"exiftool read timed out for {file_path}")
            return {}

        if result.returncode != 0:
            logger.warning(f"exiftool read failed for {file_path}: {result.stderr}")
            return {}

        try:
            data = json.loads(result.stdout)
            return data[0] if data else {}
        except json.JSONDecodeError:
            logger.error(f"exiftool returned invalid JSON for {file_path}")
            return {}

    return await loop.run_in_executor(None, _read)


async def write_tags(file_path: str, edits: dict[str, str | None]) -> dict:
    """Write tag edits to a file using exiftool.

    Args:
        file_path: Absolute path to the file to edit.
        edits: Dict of TagName -> new_value. None deletes the tag.

    Returns:
        Dict with 'success' (bool), 'message' (str), and 'warnings' (list).
    """
    if not edits:
        return {"success": True, "message": "No edits to apply", "warnings": []}

    loop = asyncio.get_running_loop()

    def _write():
        args = ["exiftool", "-overwrite_original"]
        for tag, value in edits.items():
            if value is None:
                args.append(f"-{tag}=")
            else:
                args.append(f"-{tag}={value}")
        args.append(str(file_path))

        try:
            result = subprocess.run(
                args, capture_output=True, text=True, timeout=30,
            )
        except FileNotFoundError:
            return {"success": False, "message": "exiftool not found", "warnings": []}
        except subprocess.TimeoutExpired:
            return {"success": False, "message": "exiftool write timed out", "warnings": []}

        warnings = [
            line for line in result.stderr.strip().split("\n")
            if line.startswith("Warning:")
        ]
        if result.returncode != 0:
            return {
                "success": False,
                "message": result.stderr.strip(),
                "warnings": warnings,
            }
        return {
            "success": True,
            "message": result.stdout.strip(),
            "warnings": warnings,
        }

    return await loop.run_in_executor(None, _write)


async def read_tags_before_edit(file_path: str, tag_names: list[str]) -> dict:
    """Read specific tags from a file — used to capture old values for audit trail.

    Returns dict of tag_name -> current_value (or None if not present).
    """
    all_tags = await read_tags(file_path)
    result = {}
    for name in tag_names:
        # Try exact match first, then with common group prefixes
        if name in all_tags:
            result[name] = str(all_tags[name])
        else:
            # Search across groups (e.g. "DateTimeOriginal" matches "EXIF:DateTimeOriginal")
            found = False
            for key, val in all_tags.items():
                if key.split(":")[-1] == name:
                    result[name] = str(val)
                    found = True
                    break
            if not found:
                result[name] = None
    return result


async def read_xmp_sidecar(xmp_path: str) -> str | None:
    """Read an XMP sidecar file and return its XML content."""
    path = Path(xmp_path)
    if not path.exists():
        return None

    loop = asyncio.get_running_loop()

    def _read():
        return path.read_text(encoding="utf-8")

    return await loop.run_in_executor(None, _read)


async def write_xmp_sidecar(xmp_path: str, content: str) -> None:
    """Write content to an XMP sidecar file."""
    loop = asyncio.get_running_loop()

    def _write():
        Path(xmp_path).write_text(content, encoding="utf-8")

    await loop.run_in_executor(None, _write)


# Tag grouping for the UI — organizes raw exiftool output into sections
TAG_GROUPS = {
    "Date & Time": [
        "EXIF:DateTimeOriginal", "EXIF:CreateDate", "EXIF:ModifyDate",
        "EXIF:SubSecDateTimeOriginal", "XMP:DateTimeOriginal", "XMP:CreateDate",
        "QuickTime:CreateDate", "QuickTime:ModifyDate",
    ],
    "GPS": [
        "EXIF:GPSLatitude", "EXIF:GPSLongitude", "EXIF:GPSLatitudeRef",
        "EXIF:GPSLongitudeRef", "EXIF:GPSAltitude", "EXIF:GPSDateStamp",
        "EXIF:GPSTimeStamp", "XMP:GPSLatitude", "XMP:GPSLongitude",
        "Composite:GPSPosition",
    ],
    "Description": [
        "EXIF:ImageDescription", "XMP:Description", "XMP:Title",
        "XMP:Subject", "IPTC:Caption-Abstract", "IPTC:ObjectName",
    ],
    "Creator": [
        "XMP:Creator", "EXIF:Artist", "IPTC:By-line",
        "XMP:Rights", "EXIF:Copyright",
    ],
    "Camera": [
        "EXIF:Make", "EXIF:Model", "EXIF:Software",
        "EXIF:LensModel", "EXIF:FocalLength",
    ],
    "Snatched": [
        "XMP:ImageUniqueID", "EXIF:ImageUniqueID",
    ],
}


def group_tags(flat_tags: dict) -> dict[str, dict]:
    """Organize flat exiftool output into UI-friendly groups.

    Returns {group_name: {tag_key: value, ...}, ...}
    plus an "Other" group for uncategorized tags.
    """
    # Build reverse lookup: tag_key -> group_name
    tag_to_group = {}
    for group, keys in TAG_GROUPS.items():
        for k in keys:
            tag_to_group[k] = group

    grouped = {g: {} for g in TAG_GROUPS}
    grouped["Other"] = {}

    # Skip internal/binary tags
    skip_prefixes = ("SourceFile", "File:", "ExifTool:")

    for key, val in flat_tags.items():
        if any(key.startswith(p) for p in skip_prefixes):
            continue
        if key in tag_to_group:
            grouped[tag_to_group[key]][key] = val
        else:
            grouped["Other"][key] = val

    # Remove empty groups
    return {g: tags for g, tags in grouped.items() if tags}
