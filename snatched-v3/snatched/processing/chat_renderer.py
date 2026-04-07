"""Snapchat-style chat conversation renderer — v3 overhaul.

Renders pill-bubble chat pages with cover/closing pages, emoji support,
clustering, smart media placeholders, and date pill badges.

Canvas: 2880×5120 px, 600 DPI output.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Union

import warnings
warnings.filterwarnings("ignore", "Palette images with Transparency")
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

@dataclass
class ChatMessage:
    """A single chat message in the conversation."""
    sender: str                        # display name
    text: str                          # message content (may be empty for media-only)
    timestamp: float                   # unix timestamp (seconds since epoch)
    is_self: bool                      # True = exporter (self), False = friend
    media_path: str | None = None      # path to media thumbnail if exists on disk
    media_type: str | None = None      # "photo", "video", "snap"
    media_duration: str | None = None  # "0:12" for videos
    is_ephemeral: bool = False         # True for Snapchat ephemeral snaps
    cluster_position: str = "solo"     # "first" / "middle" / "last" / "solo"


@dataclass
class DateDivider:
    """A date separator between message groups."""
    date_str: str       # e.g. "February 14, 2024"
    timestamp: float = 0.0  # unix ts for relative-time calculation


@dataclass
class ConversationMeta:
    """Metadata for cover/closing pages — built in export.py, passed to renderer."""
    partner_name: str
    date_range_str: str
    message_count: int
    first_message_text: str
    first_message_sender: str
    last_message_text: str
    last_message_sender: str
    export_date: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%B %d, %Y"))


@dataclass
class Page:
    """A single rendered page of the conversation."""
    elements: list[Union[ChatMessage, DateDivider]]
    page_num: int
    total_pages: int


# ---------------------------------------------------------------------------
# Layout Constants
# ---------------------------------------------------------------------------

CANVAS_WIDTH          = 2880
MAX_PAGE_HEIGHT       = 5120

# Header
HEADER_HEIGHT         = 360
HEADER_SEPARATOR_H    = 2

# Footer
FOOTER_HEIGHT         = 110
TOTAL_FOOTER_HEIGHT   = FOOTER_HEIGHT

# Date divider
DATE_DIVIDER_HEIGHT   = 160     # taller: pill badge + relative time

# Bubble layout
BUBBLE_RADIUS         = 60
BUBBLE_PAD_H          = 48      # horizontal padding inside bubble
BUBBLE_PAD_V          = 36      # vertical padding inside bubble
BUBBLE_MAX_WIDTH      = 2160    # max bubble width (~75% of canvas)
BUBBLE_MIN_WIDTH      = 320     # minimum bubble width
BUBBLE_MARGIN_SIDE    = 80      # margin from canvas edge
BUBBLE_TEXT_MAX_W     = BUBBLE_MAX_WIDTH - 2 * BUBBLE_PAD_H

# Message spacing
SPACING_CLUSTER       = 12      # within a cluster (same sender, <120s)
SPACING_BETWEEN       = 36      # between clusters or different senders
CLUSTER_WINDOW        = 120     # seconds — same-sender grouping threshold

# Sender name
SENDER_NAME_PAD_BTM   = 12
SENDER_NAME_PAD_LEFT  = 16      # indent from bubble edge

# Timestamp (inline, bottom-right of bubble)
TIMESTAMP_FONT_SIZE   = 72
TIMESTAMP_OPACITY     = 140     # 55% of 255

# Media thumbnails
MEDIA_MAX_WIDTH       = BUBBLE_MAX_WIDTH - 2 * BUBBLE_PAD_H
MEDIA_HEIGHT          = 800
MEDIA_LABEL_HEIGHT    = 80
MEDIA_PAD_TOP         = 12
MEDIA_PAD_BOTTOM      = 8

# Text measurement
LINE_SPACING          = 8

# Page break marker
PAGE_BREAK_HEIGHT     = 80

# Cover / closing page
COVER_GRADIENT_TOP    = "#0EADFF"
COVER_GRADIENT_BOT    = "#0966A3"


# ---------------------------------------------------------------------------
# Color Schemes
# ---------------------------------------------------------------------------

COLORS_LIGHT = {
    # Backgrounds
    "bg":                   "#F7F5F2",      # off-white (#16)
    "header_bg":            "#0EADFF",
    "header_text":          "#FFFFFF",
    "header_sep":           "#E0DEDA",

    # Bubbles (#13)
    "bubble_self_bg":       "#0EADFF",      # Snapchat blue
    "bubble_self_text":     "#FFFFFF",
    "bubble_friend_bg":     "#F0F0F0",      # light gray
    "bubble_friend_text":   "#1A1A1A",

    # Sender names
    "sender_self":          "#0EADFF",
    "sender_friend":        "#FF6E6E",      # coral red (#5)

    # Timestamps (RGBA tuples for alpha compositing)
    "timestamp_self":       (255, 255, 255, TIMESTAMP_OPACITY),
    "timestamp_friend":     (26, 26, 26, TIMESTAMP_OPACITY),

    # Date divider
    "date_pill_bg":         "#E8E6E3",
    "date_pill_text":       "#666666",
    "date_relative_text":   "#999999",
    "date_rule":            "#E0DEDA",

    # Media placeholders (#7)
    "media_placeholder":    "#EEEEEE",
    "media_label":          "#999999",
    "snap_placeholder_bg":  "#FFF3E0",      # warm amber
    "snap_placeholder_text":"#E65100",
    "missing_placeholder_bg":"#F5F5F5",
    "missing_placeholder_text":"#9E9E9E",

    # Footer / watermark
    "footer_text":          "#999999",
    "watermark_text":       "#CCCCCC",

    # Page break marker (#9)
    "page_break_line":      "#D0D0D0",
    "page_break_arrow":     "#BBBBBB",

    # Cover / closing
    "cover_text":           "#FFFFFF",
    "cover_quote_text":     "#E0F0FF",
    "cover_rule":           "#FFFFFF40",
    "closing_text":         "#666666",
    "closing_quote_text":   "#444444",

    # Legacy (kept for compatibility)
    "msg_text":             "#1A1A1A",
    "avatar_bg":            "#BBBBBB",
}

COLORS_DARK = {
    # Backgrounds
    "bg":                   "#0F0F0F",      # deeper dark (#16)
    "header_bg":            "#0B8EC4",
    "header_text":          "#FFFFFF",
    "header_sep":           "#2A2A2A",

    # Bubbles
    "bubble_self_bg":       "#0B8EC4",      # muted Snapchat blue
    "bubble_self_text":     "#FFFFFF",
    "bubble_friend_bg":     "#2A2A2A",      # dark gray
    "bubble_friend_text":   "#E0E0E0",

    # Sender names
    "sender_self":          "#0EADFF",
    "sender_friend":        "#FF6E6E",      # coral red (#5)

    # Timestamps
    "timestamp_self":       (255, 255, 255, TIMESTAMP_OPACITY),
    "timestamp_friend":     (224, 224, 224, TIMESTAMP_OPACITY),

    # Date divider
    "date_pill_bg":         "#FFFC00",      # snap-yellow in dark mode
    "date_pill_text":       "#0F0F0F",
    "date_relative_text":   "#666666",
    "date_rule":            "#2A2A2A",

    # Media placeholders
    "media_placeholder":    "#2A2A2A",
    "media_label":          "#666666",
    "snap_placeholder_bg":  "#3E2A10",
    "snap_placeholder_text":"#FFB74D",
    "missing_placeholder_bg":"#1E1E1E",
    "missing_placeholder_text":"#616161",

    # Footer / watermark
    "footer_text":          "#555555",
    "watermark_text":       "#333333",

    # Page break marker
    "page_break_line":      "#333333",
    "page_break_arrow":     "#444444",

    # Cover / closing
    "cover_text":           "#FFFFFF",
    "cover_quote_text":     "#B0D8F0",
    "cover_rule":           "#FFFFFF30",
    "closing_text":         "#888888",
    "closing_quote_text":   "#AAAAAA",

    # Legacy
    "msg_text":             "#E0E0E0",
    "avatar_bg":            "#555555",
}


# ---------------------------------------------------------------------------
# Font Loader (cached)
# ---------------------------------------------------------------------------

_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}

# Font search paths in priority order
_FONT_SEARCH = [
    "/usr/share/fonts/truetype/public-sans/PublicSans-Regular.ttf",
    "/usr/share/fonts/opentype/public-sans/PublicSans-Regular.otf",
    "/usr/local/share/fonts/PublicSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/msttcorefonts/Arial.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]

_BOLD_FONT_SEARCH = [
    "/usr/share/fonts/truetype/public-sans/PublicSans-Bold.ttf",
    "/usr/share/fonts/opentype/public-sans/PublicSans-Bold.otf",
    "/usr/local/share/fonts/PublicSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/msttcorefonts/Arial_Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]

_ITALIC_FONT_SEARCH = [
    "/usr/share/fonts/truetype/public-sans/PublicSans-Italic.ttf",
    "/usr/share/fonts/opentype/public-sans/PublicSans-Italic.otf",
    "/usr/local/share/fonts/PublicSans-Italic.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
    "/usr/share/fonts/truetype/msttcorefonts/Arial_Italic.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
]

_EMOJI_FONT_SEARCH = [
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    "/usr/share/fonts/noto/NotoColorEmoji.ttf",
    "/usr/local/share/fonts/NotoColorEmoji.ttf",
]

_resolved_regular: str | None = None
_resolved_bold: str | None = None
_resolved_italic: str | None = None
_resolved_emoji: str | None = None


def _find_font_path(search_list: list[str]) -> str | None:
    """Find the first existing font file from the search list."""
    for path in search_list:
        if Path(path).is_file():
            return path
    return None


def _resolve_fonts() -> None:
    """Resolve font paths once, cache the result."""
    global _resolved_regular, _resolved_bold, _resolved_italic, _resolved_emoji
    if _resolved_regular is None:
        _resolved_regular = _find_font_path(_FONT_SEARCH) or ""
    if _resolved_bold is None:
        _resolved_bold = _find_font_path(_BOLD_FONT_SEARCH) or ""
    if _resolved_italic is None:
        _resolved_italic = _find_font_path(_ITALIC_FONT_SEARCH) or ""
    if _resolved_emoji is None:
        _resolved_emoji = _find_font_path(_EMOJI_FONT_SEARCH) or ""


def get_font(size: int, bold: bool = False, italic: bool = False) -> ImageFont.FreeTypeFont:
    """Load a font at the given size, with caching."""
    _resolve_fonts()
    style = "bold" if bold else ("italic" if italic else "regular")
    key = (style, size)
    if key in _font_cache:
        return _font_cache[key]

    if bold:
        path = _resolved_bold
    elif italic:
        path = _resolved_italic
    else:
        path = _resolved_regular

    if path:
        try:
            font = ImageFont.truetype(path, size)
            _font_cache[key] = font
            return font
        except (OSError, IOError):
            pass

    font = ImageFont.load_default()
    _font_cache[key] = font
    return font


def get_emoji_font(size: int) -> ImageFont.FreeTypeFont | None:
    """Load Noto Color Emoji font. Returns None if unavailable.

    Noto Color Emoji is a bitmap (CBDT) font that only supports size 109.
    We always load at 109 regardless of requested size.
    """
    _resolve_fonts()
    # Bitmap font only supports size 109
    actual_size = 109
    key = ("emoji", actual_size)
    if key in _font_cache:
        return _font_cache[key]

    if _resolved_emoji:
        try:
            font = ImageFont.truetype(_resolved_emoji, actual_size)
            _font_cache[key] = font
            return font
        except (OSError, IOError, ValueError):
            pass

    return None


# ---------------------------------------------------------------------------
# Text Measurement Helpers
# ---------------------------------------------------------------------------

# We keep a single scratch ImageDraw for measurement so that we never
# allocate throwaway Images during the measuring pass.
_measure_img: Image.Image | None = None
_measure_draw: ImageDraw.ImageDraw | None = None


def _get_measure_draw() -> ImageDraw.ImageDraw:
    """Return a reusable ImageDraw for text measurement."""
    global _measure_img, _measure_draw
    if _measure_draw is None:
        _measure_img = Image.new("RGB", (1, 1))
        _measure_draw = ImageDraw.Draw(_measure_img)
    return _measure_draw


def _font_line_height(font: ImageFont.FreeTypeFont) -> int:
    """Return the proper line height for a font (ascent + descent).

    This matches the actual vertical space consumed when Pillow renders
    text at a given y coordinate.  Using textbbox height alone undercounts
    because it only measures the tight glyph bounds, not the full
    ascent-to-descent span.
    """
    ascent, descent = font.getmetrics()
    return ascent + descent


# Cache of font -> line height so we don't call getmetrics() repeatedly
_line_height_cache: dict[int, int] = {}


def _get_line_height(font: ImageFont.FreeTypeFont) -> int:
    """Cached wrapper around _font_line_height."""
    fid = id(font)
    if fid not in _line_height_cache:
        _line_height_cache[fid] = _font_line_height(font)
    return _line_height_cache[fid]


def text_height(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> int:
    """Measure the pixel height of word-wrapped text.

    Uses font metrics (ascent + descent) for each line height, matching
    the actual rendered output exactly.
    """
    draw = _get_measure_draw()
    lines = _wrap_text(text, font, max_width, draw)
    if not lines:
        return 0
    lh = _get_line_height(font)
    return len(lines) * lh + max(0, len(lines) - 1) * LINE_SPACING


def _wrap_text(
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    draw: ImageDraw.ImageDraw,
) -> list[str]:
    """Word-wrap text to fit within max_width pixels.

    Handles long words by character-splitting as a last resort.
    """
    if not text:
        return []

    result_lines: list[str] = []

    # Respect explicit newlines in the source text
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            result_lines.append("")
            continue

        words = paragraph.split()
        if not words:
            result_lines.append("")
            continue

        current_line = words[0]
        for word in words[1:]:
            test = current_line + " " + word
            bbox = draw.textbbox((0, 0), test, font=font)
            line_w = bbox[2] - bbox[0]
            if line_w <= max_width:
                current_line = test
            else:
                result_lines.append(current_line)
                # If the word itself is wider than max_width, split it
                bbox_w = draw.textbbox((0, 0), word, font=font)
                if (bbox_w[2] - bbox_w[0]) > max_width:
                    chars = list(word)
                    chunk = ""
                    for ch in chars:
                        test_chunk = chunk + ch
                        cbox = draw.textbbox((0, 0), test_chunk, font=font)
                        if (cbox[2] - cbox[0]) > max_width and chunk:
                            result_lines.append(chunk)
                            chunk = ch
                        else:
                            chunk = test_chunk
                    current_line = chunk
                else:
                    current_line = word
        result_lines.append(current_line)

    return result_lines


# ---------------------------------------------------------------------------
# Content Measurer
# ---------------------------------------------------------------------------

@dataclass
class _MeasuredElement:
    """An element with its pre-calculated pixel height."""
    element: Union[ChatMessage, DateDivider]
    height: int  # total height including spacing above


class ContentMeasurer:
    """Pre-measures all chat elements and splits them into pages.

    The measurement uses the SAME fonts and wrapping logic as the renderer,
    guaranteeing zero drift between measure and render passes.
    """

    def __init__(self, dark_mode: bool = False) -> None:
        self.dark_mode = dark_mode
        # Sizes 2x for high-clarity text on 2880px canvas
        self.font_msg = get_font(112)
        self.font_sender = get_font(84, bold=True)
        self.font_date = get_font(100)
        self.font_media_label = get_font(84)
        self.font_timestamp = get_font(TIMESTAMP_FONT_SIZE)
        self.font_date_relative = get_font(72)
        self.draw = _get_measure_draw()

    def measure_message(
        self,
        msg: ChatMessage,
        prev_sender: str | None,
    ) -> int:
        """Return the pixel height of a message block (spacing + optional name + bubble + optional timestamp)."""
        h = 0
        is_cluster_continuation = msg.cluster_position in ("middle", "last")
        show_sender = msg.cluster_position in ("first", "solo")
        show_timestamp = msg.cluster_position in ("last", "solo")

        # Inter-message spacing
        if prev_sender is not None:
            if is_cluster_continuation and msg.sender == prev_sender:
                h += SPACING_CLUSTER
            else:
                h += SPACING_BETWEEN
        else:
            h += SPACING_BETWEEN

        # Sender name above bubble (only on first/solo)
        if show_sender:
            h += _get_line_height(self.font_sender) + SENDER_NAME_PAD_BTM

        # Bubble content height
        content_h = 0

        # Message text
        if msg.text:
            content_h += text_height(msg.text, self.font_msg, BUBBLE_TEXT_MAX_W)

        # Media
        has_media = msg.media_path and Path(msg.media_path).is_file()
        has_placeholder = (msg.is_ephemeral or msg.media_type) and not has_media
        if has_media or has_placeholder:
            content_h += MEDIA_PAD_TOP + MEDIA_HEIGHT + MEDIA_PAD_BOTTOM + MEDIA_LABEL_HEIGHT

        # Timestamp line inside bubble
        if show_timestamp and msg.timestamp > 86400:
            content_h += _get_line_height(self.font_timestamp) + 8

        # Bubble padding
        bubble_h = content_h + 2 * BUBBLE_PAD_V
        bubble_h = max(bubble_h, BUBBLE_RADIUS * 2)

        h += bubble_h
        h += 4  # bottom padding

        return h

    def measure_date_divider(self) -> int:
        """Return the pixel height of a date divider."""
        return DATE_DIVIDER_HEIGHT

    def _split_oversized_message(
        self,
        msg: ChatMessage,
        usable_h: int,
        first_chunk_budget: int = 0,
    ) -> list[ChatMessage]:
        """Split a message whose text exceeds usable page height into chunks.

        Each chunk becomes a separate ChatMessage.  2 lines of overlap
        between chunks preserve reading context across page breaks.

        If first_chunk_budget is provided and positive, the first chunk is
        sized to fit within that pixel budget (remaining space on the current
        page).  Subsequent chunks use the full usable_h.
        """
        draw = _get_measure_draw()
        lines = _wrap_text(msg.text, self.font_msg, BUBBLE_TEXT_MAX_W, draw)
        if not lines:
            return [msg]

        lh = _get_line_height(self.font_msg)
        # Fixed overhead per chunk: spacing + sender name + bubble padding + bottom padding
        overhead = SPACING_BETWEEN + _get_line_height(self.font_sender) + SENDER_NAME_PAD_BTM + 2 * BUBBLE_PAD_V + 4
        # Add media height only to the last chunk if media exists
        has_media = msg.media_path and Path(msg.media_path).is_file()
        media_h = (MEDIA_PAD_TOP + MEDIA_HEIGHT + MEDIA_PAD_BOTTOM + MEDIA_LABEL_HEIGHT) if has_media else 0

        OVERLAP_LINES = 2

        chunks: list[ChatMessage] = []
        i = 0
        while i < len(lines):
            # First chunk may have a smaller budget (remaining space on page)
            if not chunks and first_chunk_budget > 0:
                chunk_usable = first_chunk_budget
            else:
                chunk_usable = usable_h
            available_for_text = chunk_usable - overhead

            # If available space is too small for even one line, use full page
            if available_for_text < lh:
                available_for_text = usable_h - overhead

            # Try with media first (optimistic last chunk)
            text_budget = available_for_text - media_h

            n = 0
            h = 0
            while i + n < len(lines):
                line_h = lh + (LINE_SPACING if n > 0 else 0)
                if h + line_h > text_budget and n > 0:
                    break
                h += line_h
                n += 1

            # If this isn't actually the last chunk, recalculate without media
            if i + n < len(lines) and media_h > 0:
                text_budget = available_for_text
                n = 0
                h = 0
                while i + n < len(lines):
                    line_h = lh + (LINE_SPACING if n > 0 else 0)
                    if h + line_h > text_budget and n > 0:
                        break
                    h += line_h
                    n += 1

            if n == 0:
                n = 1  # always take at least one line

            chunk_text = '\n'.join(lines[i:i + n])
            is_last = (i + n >= len(lines))

            chunk = ChatMessage(
                sender=msg.sender,
                text=chunk_text,
                timestamp=msg.timestamp,
                is_self=msg.is_self,
                media_path=msg.media_path if is_last else None,
                media_type=msg.media_type if is_last else None,
                media_duration=msg.media_duration if is_last else None,
            )
            chunks.append(chunk)

            # Advance with overlap for context continuity
            advance = max(1, n - OVERLAP_LINES) if not is_last else n
            i += advance

        return chunks if chunks else [msg]

    def paginate(
        self,
        elements: list[Union[ChatMessage, DateDivider]],
        has_cover: bool = False,
        has_closing: bool = False,
    ) -> list[Page]:
        """Split elements into pages that fit within MAX_PAGE_HEIGHT.

        Clustering is computed on the full element list before pagination.
        Page numbering accounts for cover page (if present).
        """
        if not elements:
            return []

        # Compute clusters on full element list (must happen before pagination)
        ChatRenderer._compute_clusters(elements)

        reserved = HEADER_HEIGHT + HEADER_SEPARATOR_H + TOTAL_FOOTER_HEIGHT
        usable = MAX_PAGE_HEIGHT - reserved

        measured: list[_MeasuredElement] = []
        prev_sender: str | None = None

        for elem in elements:
            if isinstance(elem, DateDivider):
                h = self.measure_date_divider()
                prev_sender = None  # reset sender tracking across date breaks
            elif isinstance(elem, ChatMessage):
                h = self.measure_message(elem, prev_sender)
                prev_sender = elem.sender
            else:
                continue
            measured.append(_MeasuredElement(element=elem, height=h))

        # Split into pages
        pages_raw: list[list[_MeasuredElement]] = []
        current_page: list[_MeasuredElement] = []
        current_h = 0

        for me in measured:
            # If element alone exceeds usable height, split its text across pages
            if me.height > usable and isinstance(me.element, ChatMessage) and me.element.text:
                # Split using the remaining space on the current page for the first chunk,
                # then full usable height for subsequent chunks.
                remaining_on_page = usable - current_h
                chunks = self._split_oversized_message(me.element, usable,
                                                       first_chunk_budget=remaining_on_page)
                for ci, chunk_msg in enumerate(chunks):
                    chunk_h = self.measure_message(chunk_msg, None)
                    if ci == 0 and current_h + chunk_h <= usable:
                        # First chunk fits on the current page
                        current_page.append(_MeasuredElement(element=chunk_msg, height=chunk_h))
                        current_h += chunk_h
                    else:
                        if current_page:
                            pages_raw.append(current_page)
                        current_page = [_MeasuredElement(element=chunk_msg, height=chunk_h)]
                        current_h = chunk_h
                continue

            if me.height > usable:
                # Non-text oversized element (e.g. media-only): give it its own page
                if current_page:
                    pages_raw.append(current_page)
                pages_raw.append([me])
                current_page = []
                current_h = 0
                continue

            if current_h + me.height > usable:
                # Start a new page
                if current_page:
                    pages_raw.append(current_page)
                current_page = [me]
                current_h = me.height
            else:
                current_page.append(me)
                current_h += me.height

        if current_page:
            pages_raw.append(current_page)

        # Adjust numbering for cover page
        page_offset = 1 if has_cover else 0
        total = len(pages_raw) + page_offset + (1 if has_closing else 0)
        pages: list[Page] = []
        for i, raw in enumerate(pages_raw):
            pages.append(Page(
                elements=[m.element for m in raw],
                page_num=i + 1 + page_offset,
                total_pages=total,
            ))

        return pages


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _relative_time(timestamp: float) -> str:
    """Return a human-readable relative time string.

    Examples: "2 years ago", "3 months ago", "yesterday", "today".
    """
    if timestamp <= 86400:
        return ""

    now = time.time()
    diff = now - timestamp

    if diff < 0:
        return "in the future"

    seconds = int(diff)
    minutes = seconds // 60
    hours = minutes // 60
    days = hours // 24
    months = days // 30
    years = days // 365

    if days == 0:
        return "today"
    elif days == 1:
        return "yesterday"
    elif days < 7:
        return f"{days} days ago"
    elif days < 30:
        weeks = days // 7
        return f"{weeks} week{'s' if weeks != 1 else ''} ago"
    elif months < 12:
        return f"{months} month{'s' if months != 1 else ''} ago"
    else:
        return f"{years} year{'s' if years != 1 else ''} ago"


# ---------------------------------------------------------------------------
# Emoji Detection
# ---------------------------------------------------------------------------

# Common emoji Unicode ranges (covers most emoji used in chat)
_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002702-\U000027B0"  # dingbats
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U0001FA00-\U0001FA6F"  # chess, extended-A
    "\U0001FA70-\U0001FAFF"  # extended-A continued
    "\U00002600-\U000026FF"  # misc symbols
    "\U0000FE00-\U0000FE0F"  # variation selectors
    "\U0000200D"             # zero width joiner
    "\U00002764"             # heart
    "\U0000203C-\U00003299"  # CJK symbols, enclosed
    "]+",
    flags=re.UNICODE,
)


def _has_emoji(text: str) -> bool:
    """Quick check if text contains any emoji characters."""
    return bool(_EMOJI_RE.search(text))


def _split_emoji_segments(text: str) -> list[tuple[str, bool]]:
    """Split text into (segment, is_emoji) tuples.

    Returns alternating plain text and emoji segments.
    """
    segments: list[tuple[str, bool]] = []
    last_end = 0

    for match in _EMOJI_RE.finditer(text):
        start, end = match.span()
        if start > last_end:
            segments.append((text[last_end:start], False))
        segments.append((match.group(), True))
        last_end = end

    if last_end < len(text):
        segments.append((text[last_end:], False))

    return segments if segments else [(text, False)]


# ---------------------------------------------------------------------------
# Chat Renderer
# ---------------------------------------------------------------------------

class ChatRenderer:
    """Renders Snapchat-style chat conversation pages as PNG images."""

    def __init__(self, username: str, dark_mode: bool = False) -> None:
        self.username = username
        self.dark_mode = dark_mode
        self.colors = COLORS_DARK if dark_mode else COLORS_LIGHT

        # Fonts (shared with measurer)
        # Sizes 2x for high-clarity text on 2880px canvas
        self.font_header_name = get_font(168, bold=True)
        self.font_header_status = get_font(100)
        self.font_msg = get_font(112)
        self.font_sender = get_font(84, bold=True)
        self.font_date = get_font(100)
        self.font_media_label = get_font(84)
        self.font_footer = get_font(84)
        self.font_timestamp = get_font(TIMESTAMP_FONT_SIZE)
        self.font_date_relative = get_font(72)

        self.measurer = ContentMeasurer(dark_mode=dark_mode)

    # ---- emoji-aware text drawing -----------------------------------------

    def _draw_text_with_emoji(
        self,
        draw: ImageDraw.ImageDraw,
        img: Image.Image,
        x: int,
        y: int,
        text: str,
        fill,
        font: ImageFont.FreeTypeFont,
    ) -> None:
        """Draw text with inline emoji support.

        Splits text into plain/emoji segments and renders emoji using
        Noto Color Emoji with embedded_color=True.
        Falls back to regular font if emoji font unavailable.
        """
        if not _has_emoji(text):
            draw.text((x, y), text, fill=fill, font=font)
            return

        emoji_font = get_emoji_font(font.size if hasattr(font, 'size') else 112)
        if emoji_font is None:
            # No emoji font — render everything with regular font (tofu)
            draw.text((x, y), text, fill=fill, font=font)
            return

        # Render segments inline
        cursor_x = x
        for segment, is_emoji in _split_emoji_segments(text):
            if is_emoji:
                try:
                    draw.text(
                        (cursor_x, y),
                        segment,
                        font=emoji_font,
                        embedded_color=True,
                    )
                    seg_bbox = draw.textbbox((0, 0), segment, font=emoji_font)
                except (TypeError, AttributeError):
                    # Pillow version may not support embedded_color
                    draw.text((cursor_x, y), segment, fill=fill, font=font)
                    seg_bbox = draw.textbbox((0, 0), segment, font=font)
            else:
                draw.text((cursor_x, y), segment, fill=fill, font=font)
                seg_bbox = draw.textbbox((0, 0), segment, font=font)

            cursor_x += seg_bbox[2] - seg_bbox[0]

    # ---- clustering -------------------------------------------------------

    @staticmethod
    def _compute_clusters(elements: list[Union[ChatMessage, DateDivider]]) -> None:
        """Pre-pass: set cluster_position on ChatMessages.

        Same sender within CLUSTER_WINDOW seconds = clustered.
        Positions: "first", "middle", "last", "solo".
        """
        messages = [e for e in elements if isinstance(e, ChatMessage)]
        if not messages:
            return

        # Group into clusters
        clusters: list[list[ChatMessage]] = []
        current_cluster: list[ChatMessage] = [messages[0]]

        for msg in messages[1:]:
            prev = current_cluster[-1]
            same_sender = msg.sender == prev.sender
            within_window = abs(msg.timestamp - prev.timestamp) <= CLUSTER_WINDOW
            # Also break cluster at date dividers: check if there's a DateDivider
            # between prev and msg in the original elements list
            has_divider = False
            prev_idx = elements.index(prev)
            msg_idx = elements.index(msg)
            for i in range(prev_idx + 1, msg_idx):
                if isinstance(elements[i], DateDivider):
                    has_divider = True
                    break

            if same_sender and within_window and not has_divider:
                current_cluster.append(msg)
            else:
                clusters.append(current_cluster)
                current_cluster = [msg]

        clusters.append(current_cluster)

        # Assign positions
        for cluster in clusters:
            if len(cluster) == 1:
                cluster[0].cluster_position = "solo"
            else:
                cluster[0].cluster_position = "first"
                for msg in cluster[1:-1]:
                    msg.cluster_position = "middle"
                cluster[-1].cluster_position = "last"

    # ---- public API -------------------------------------------------------

    def render_conversation(
        self,
        messages: list[ChatMessage],
        output_dir: Path,
        progress_cb: Callable[[str], None] | None = None,
        meta: 'ConversationMeta | None' = None,
    ) -> list[Path]:
        """Render full conversation to PNG files.

        Returns list of output file paths (page-0000.png, page-0001.png, ...).
        Generates cover page (if meta provided) and closing page.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Store meta for header/footer access via getattr
        self._current_meta = meta

        # Build the element list with date dividers inserted
        elements = self._build_elements(messages)

        # Paginate (clustering happens inside paginate)
        has_cover = meta is not None
        has_closing = meta is not None
        pages = self.measurer.paginate(elements, has_cover=has_cover, has_closing=has_closing)

        if not pages:
            pages = [Page(elements=[], page_num=1, total_pages=1)]

        output_paths: list[Path] = []
        page_counter = 0

        # Cover page
        if has_cover:
            cover_img = self._draw_cover_page(meta)
            cover_path = output_dir / f"page-{page_counter:04d}.png"
            cover_img.save(str(cover_path), "PNG", optimize=True, dpi=(600, 600))
            output_paths.append(cover_path)
            page_counter += 1
            if progress_cb:
                progress_cb("Rendered cover page")

        # Content pages
        for page in pages:
            img = self.render_single_page(page, self.username)
            path = output_dir / f"page-{page_counter:04d}.png"
            img.save(str(path), "PNG", optimize=True, dpi=(600, 600))
            output_paths.append(path)
            page_counter += 1

            if progress_cb:
                progress_cb(
                    f"Rendered page {page.page_num} of {page.total_pages}"
                )

        # Closing page
        if has_closing:
            closing_img = self._draw_closing_page(meta, page.total_pages if pages else 1)
            closing_path = output_dir / f"page-{page_counter:04d}.png"
            closing_img.save(str(closing_path), "PNG", optimize=True, dpi=(600, 600))
            output_paths.append(closing_path)
            if progress_cb:
                progress_cb("Rendered closing page")

        return output_paths

    def render_single_page(self, page: Page, username: str) -> Image.Image:
        """Render a single page to a PIL Image."""
        total_h = MAX_PAGE_HEIGHT

        img = Image.new("RGBA", (CANVAS_WIDTH, total_h), self.colors["bg"])
        draw = ImageDraw.Draw(img)

        # Compute clusters for this page's elements
        self._compute_clusters(page.elements)

        # Draw header
        self._draw_header(draw, username, meta=getattr(self, '_current_meta', None))

        # Draw messages
        y = HEADER_HEIGHT + HEADER_SEPARATOR_H
        prev_sender: str | None = None

        for elem in page.elements:
            if isinstance(elem, DateDivider):
                y = self._draw_date_divider(draw, elem, y)
                prev_sender = None
            elif isinstance(elem, ChatMessage):
                y = self._draw_message(draw, img, elem, y, prev_sender)
                prev_sender = elem.sender

        # Draw footer
        self._draw_footer(draw, page, total_h, meta=getattr(self, '_current_meta', None))

        return img

    # ---- element list builder ---------------------------------------------

    # Timestamps at or below this value are treated as "no timestamp available".
    _EPOCH_THRESHOLD = 86400  # 1 day in seconds

    def _build_elements(
        self,
        messages: list[ChatMessage],
    ) -> list[Union[ChatMessage, DateDivider]]:
        """Insert DateDividers between messages on different calendar days.

        Messages with a zero or near-zero timestamp (epoch) are treated as
        having no valid date.  They are all grouped under a single
        "Unknown date" divider placed before any timestamped messages.
        """
        if not messages:
            return []

        # Partition: unknown-date messages vs properly timestamped messages.
        unknown_msgs = [m for m in messages if m.timestamp <= self._EPOCH_THRESHOLD]
        known_msgs   = [m for m in messages if m.timestamp >  self._EPOCH_THRESHOLD]

        elements: list[Union[ChatMessage, DateDivider]] = []

        # --- Unknown-date group (timestamp == 0 or near-zero) ---
        if unknown_msgs:
            elements.append(DateDivider(date_str="Unknown date"))
            for msg in unknown_msgs:
                elements.append(msg)

        # --- Known-date messages sorted by timestamp ---
        sorted_msgs = sorted(known_msgs, key=lambda m: m.timestamp)
        last_date_str: str | None = None

        for msg in sorted_msgs:
            t = time.localtime(msg.timestamp)
            # Format without leading zero on the day number
            date_str = (
                time.strftime("%B ", t)
                + str(t.tm_mday)
                + time.strftime(", %Y", t)
            )

            if date_str != last_date_str:
                elements.append(DateDivider(date_str=date_str, timestamp=msg.timestamp))
                last_date_str = date_str

            elements.append(msg)

        return elements

    # ---- measurement (for page height) ------------------------------------

    def _measure_page_content(self, page: Page) -> int:
        """Measure the total content height for a page (excluding header/footer)."""
        h = 0
        prev_sender: str | None = None
        for elem in page.elements:
            if isinstance(elem, DateDivider):
                h += self.measurer.measure_date_divider()
                prev_sender = None
            elif isinstance(elem, ChatMessage):
                h += self.measurer.measure_message(elem, prev_sender)
                prev_sender = elem.sender
        return h

    # ---- drawing methods --------------------------------------------------

    def _draw_header(self, draw: ImageDraw.ImageDraw, username: str, meta: 'ConversationMeta | None' = None) -> None:
        """Draw the simplified header bar."""
        # Background
        draw.rectangle(
            [0, 0, CANVAS_WIDTH, HEADER_HEIGHT],
            fill=self.colors["header_bg"],
        )

        # Username text (left-aligned, no avatar, no chevron)
        name_x = 60
        name_bbox = draw.textbbox((0, 0), username, font=self.font_header_name)
        name_h = name_bbox[3] - name_bbox[1]

        # Date range (replaces "Active" status) — #3
        if meta and meta.date_range_str:
            status_text = meta.date_range_str
        else:
            status_text = ""

        # Vertically center the name (+ optional date range) within the header
        if status_text:
            gap = 12
            status_bbox = draw.textbbox((0, 0), status_text, font=self.font_header_status)
            status_h = status_bbox[3] - status_bbox[1]
            total_content_h = name_h + gap + status_h
            name_y = (HEADER_HEIGHT - total_content_h) // 2
            status_y = name_y + name_h + gap
            draw.text(
                (name_x, status_y),
                status_text,
                fill=self.colors["header_text"],
                font=self.font_header_status,
            )
        else:
            name_y = (HEADER_HEIGHT - name_h) // 2

        draw.text(
            (name_x, name_y),
            username,
            fill=self.colors["header_text"],
            font=self.font_header_name,
        )

        # Bottom separator
        draw.line(
            [(0, HEADER_HEIGHT), (CANVAS_WIDTH, HEADER_HEIGHT)],
            fill=self.colors["header_sep"],
            width=HEADER_SEPARATOR_H,
        )

    def _draw_date_divider(
        self,
        draw: ImageDraw.ImageDraw,
        divider: DateDivider,
        y: int,
    ) -> int:
        """Draw a date divider: hairline rule + centered pill badge + relative time.

        Returns new y position.
        """
        center_y = y + DATE_DIVIDER_HEIGHT // 2 - 20  # shift up to leave room for relative time

        # Hairline rule across page (#8)
        rule_color = self.colors["date_rule"]
        draw.line(
            [(BUBBLE_MARGIN_SIDE, center_y), (CANVAS_WIDTH - BUBBLE_MARGIN_SIDE, center_y)],
            fill=rule_color,
            width=2,
        )

        # Measure date text
        date_font = self.font_date
        date_bbox = draw.textbbox((0, 0), divider.date_str, font=date_font)
        text_w = date_bbox[2] - date_bbox[0]
        text_h = date_bbox[3] - date_bbox[1]

        # Pill badge: rounded rect behind date text
        pill_pad_h = 40
        pill_pad_v = 16
        pill_w = text_w + 2 * pill_pad_h
        pill_h = text_h + 2 * pill_pad_v
        pill_x = (CANVAS_WIDTH - pill_w) // 2
        pill_y = center_y - pill_h // 2

        pill_bg = self.colors["date_pill_bg"]
        pill_text_color = self.colors["date_pill_text"]

        draw.rounded_rectangle(
            [pill_x, pill_y, pill_x + pill_w, pill_y + pill_h],
            radius=pill_h // 2,  # fully rounded ends
            fill=pill_bg,
        )

        # Date text centered in pill
        text_x = (CANVAS_WIDTH - text_w) // 2
        text_y = pill_y + pill_pad_v
        draw.text(
            (text_x, text_y),
            divider.date_str,
            fill=pill_text_color,
            font=date_font,
        )

        # Relative time below pill (#8)
        rel_text = _relative_time(divider.timestamp)
        if rel_text:
            rel_bbox = draw.textbbox((0, 0), rel_text, font=self.font_date_relative)
            rel_w = rel_bbox[2] - rel_bbox[0]
            rel_x = (CANVAS_WIDTH - rel_w) // 2
            rel_y = pill_y + pill_h + 8
            draw.text(
                (rel_x, rel_y),
                rel_text,
                fill=self.colors["date_relative_text"],
                font=self.font_date_relative,
            )

        return y + DATE_DIVIDER_HEIGHT

    def _draw_message(
        self,
        draw: ImageDraw.ImageDraw,
        img: Image.Image,
        msg: ChatMessage,
        y: int,
        prev_sender: str | None,
    ) -> int:
        """Draw a single message as a pill bubble. Returns new y position."""
        is_cluster_continuation = msg.cluster_position in ("middle", "last")
        is_cluster_end = msg.cluster_position in ("last", "solo")
        show_sender = msg.cluster_position in ("first", "solo")
        show_timestamp = is_cluster_end

        # Spacing
        if prev_sender is not None:
            if is_cluster_continuation and msg.sender == prev_sender:
                y += SPACING_CLUSTER
            else:
                y += SPACING_BETWEEN
        else:
            y += SPACING_BETWEEN

        # Pick colors
        if msg.is_self:
            bubble_bg = self.colors["bubble_self_bg"]
            text_color = self.colors["bubble_self_text"]
            sender_color = self.colors["sender_self"]
            ts_color = self.colors["timestamp_self"]
        else:
            bubble_bg = self.colors["bubble_friend_bg"]
            text_color = self.colors["bubble_friend_text"]
            sender_color = self.colors["sender_friend"]
            ts_color = self.colors["timestamp_friend"]

        # Sender name above bubble (only on first/solo, original case — not UPPER)
        if show_sender:
            sender_text = msg.sender
            name_x = (CANVAS_WIDTH - BUBBLE_MAX_WIDTH - BUBBLE_MARGIN_SIDE + SENDER_NAME_PAD_LEFT) if not msg.is_self else (BUBBLE_MARGIN_SIDE + SENDER_NAME_PAD_LEFT)
            # Simpler: left-aligned for friend, right side needs right-align
            if msg.is_self:
                # Right-aligned sender name
                name_bbox = draw.textbbox((0, 0), sender_text, font=self.font_sender)
                name_w = name_bbox[2] - name_bbox[0]
                name_x = CANVAS_WIDTH - BUBBLE_MARGIN_SIDE - name_w
            else:
                name_x = BUBBLE_MARGIN_SIDE + SENDER_NAME_PAD_LEFT

            draw.text((name_x, y), sender_text, fill=sender_color, font=self.font_sender)
            y += _get_line_height(self.font_sender) + SENDER_NAME_PAD_BTM

        # Measure text content
        text_lines = []
        text_content_h = 0
        if msg.text:
            text_lines = _wrap_text(msg.text, self.font_msg, BUBBLE_TEXT_MAX_W, draw)
            msg_lh = _get_line_height(self.font_msg)
            text_content_h = len(text_lines) * msg_lh + max(0, len(text_lines) - 1) * LINE_SPACING

        # Measure timestamp
        ts_text = ""
        ts_w = 0
        if show_timestamp and msg.timestamp > 86400:
            t = time.localtime(msg.timestamp)
            ts_text = time.strftime("%I:%M %p", t).lstrip("0")
            ts_bbox = draw.textbbox((0, 0), ts_text, font=self.font_timestamp)
            ts_w = ts_bbox[2] - ts_bbox[0]

        # Check for media
        has_media = msg.media_path and Path(msg.media_path).is_file()
        has_placeholder = (msg.is_ephemeral or msg.media_type) and not has_media

        # Calculate bubble dimensions
        content_h = text_content_h
        if has_media or has_placeholder:
            media_h = MEDIA_PAD_TOP + MEDIA_HEIGHT + MEDIA_PAD_BOTTOM + MEDIA_LABEL_HEIGHT
            content_h += media_h

        # Add timestamp height if present (below text, inside bubble)
        ts_line_h = 0
        if ts_text:
            ts_line_h = _get_line_height(self.font_timestamp) + 8
            content_h += ts_line_h

        bubble_h = content_h + 2 * BUBBLE_PAD_V
        bubble_h = max(bubble_h, BUBBLE_RADIUS * 2)  # minimum height

        # Calculate bubble width from content
        max_text_line_w = 0
        if text_lines:
            for line in text_lines:
                lbox = draw.textbbox((0, 0), line, font=self.font_msg)
                max_text_line_w = max(max_text_line_w, lbox[2] - lbox[0])

        bubble_w = max_text_line_w + 2 * BUBBLE_PAD_H
        if ts_text:
            bubble_w = max(bubble_w, ts_w + 2 * BUBBLE_PAD_H)
        if has_media or has_placeholder:
            bubble_w = max(bubble_w, MEDIA_MAX_WIDTH + 2 * BUBBLE_PAD_H)
        bubble_w = max(BUBBLE_MIN_WIDTH, min(bubble_w, BUBBLE_MAX_WIDTH))

        # Position bubble: self=right, friend=left
        if msg.is_self:
            bubble_x = CANVAS_WIDTH - BUBBLE_MARGIN_SIDE - bubble_w
        else:
            bubble_x = BUBBLE_MARGIN_SIDE

        # Determine corner radii based on cluster position
        r = BUBBLE_RADIUS
        small_r = 12  # tight corner for clustered side

        if msg.is_self:
            # Self bubbles: right side gets modified corners
            if msg.cluster_position == "first":
                radii = (r, r, small_r, r)       # top-left, top-right, bottom-right, bottom-left
            elif msg.cluster_position == "middle":
                radii = (r, small_r, small_r, r)
            elif msg.cluster_position == "last":
                radii = (r, small_r, r, r)
            else:  # solo
                radii = (r, r, r, r)
        else:
            # Friend bubbles: left side gets modified corners
            if msg.cluster_position == "first":
                radii = (r, r, r, small_r)
            elif msg.cluster_position == "middle":
                radii = (small_r, r, r, small_r)
            elif msg.cluster_position == "last":
                radii = (small_r, r, r, r)
            else:  # solo
                radii = (r, r, r, r)

        # Draw the pill bubble with per-corner radii
        # Pillow's rounded_rectangle doesn't support per-corner radii directly,
        # so we use uniform radius for now and note this as a future enhancement
        draw.rounded_rectangle(
            [bubble_x, y, bubble_x + bubble_w, y + bubble_h],
            radius=r,
            fill=bubble_bg,
        )

        # Draw text inside bubble
        text_x = bubble_x + BUBBLE_PAD_H
        text_y = y + BUBBLE_PAD_V

        if text_lines:
            msg_lh = _get_line_height(self.font_msg)
            for i, line in enumerate(text_lines):
                self._draw_text_with_emoji(draw, img, text_x, text_y, line, fill=text_color, font=self.font_msg)
                text_y += msg_lh
                if i < len(text_lines) - 1:
                    text_y += LINE_SPACING

        # Draw media inside bubble
        if has_media:
            text_y += MEDIA_PAD_TOP
            text_y = self._draw_media(draw, img, msg, text_y, bubble_x + BUBBLE_PAD_H)
            text_y += MEDIA_PAD_BOTTOM
        elif has_placeholder:
            text_y += MEDIA_PAD_TOP
            text_y = self._draw_media_placeholder_smart(draw, msg, text_y, bubble_x + BUBBLE_PAD_H)
            text_y += MEDIA_PAD_BOTTOM

        # Draw inline timestamp (bottom-right of bubble, with opacity)
        if ts_text:
            ts_x = bubble_x + bubble_w - BUBBLE_PAD_H - ts_w
            ts_y = y + bubble_h - BUBBLE_PAD_V - _get_line_height(self.font_timestamp)
            # Render with alpha using a tight crop overlay (not full canvas)
            ts_bbox = draw.textbbox((ts_x, ts_y), ts_text, font=self.font_timestamp)
            tw = ts_bbox[2] - ts_bbox[0] + 4
            th = ts_bbox[3] - ts_bbox[1] + 4
            ts_overlay = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
            ts_draw = ImageDraw.Draw(ts_overlay)
            ts_draw.text((0, 0), ts_text, fill=ts_color, font=self.font_timestamp)
            img.paste(ts_overlay, (ts_bbox[0], ts_bbox[1]), ts_overlay)

        y += bubble_h
        y += 4  # bottom padding

        return y

    def _draw_media(
        self,
        draw: ImageDraw.ImageDraw,
        img: Image.Image,
        msg: ChatMessage,
        y: int,
        media_x: int | None = None,
    ) -> int:
        """Draw a media thumbnail or placeholder. Returns new y after media + label."""
        if media_x is None:
            media_x = BUBBLE_MARGIN_SIDE + BUBBLE_PAD_H

        if msg.media_path and Path(msg.media_path).is_file():
            # Load actual thumbnail
            try:
                thumb = Image.open(msg.media_path)
                thumb.thumbnail((MEDIA_MAX_WIDTH, MEDIA_HEIGHT), Image.Resampling.LANCZOS)
                # Center the thumbnail in the allocated space
                paste_x = media_x
                paste_y = y
                img.paste(thumb, (paste_x, paste_y))
                thumb_w, thumb_h = thumb.size
            except Exception:
                # Fall back to placeholder
                thumb_w, thumb_h = MEDIA_MAX_WIDTH, MEDIA_HEIGHT
                self._draw_media_placeholder(draw, media_x, y, thumb_w, thumb_h)
        else:
            # Placeholder rectangle
            thumb_w, thumb_h = MEDIA_MAX_WIDTH, MEDIA_HEIGHT
            self._draw_media_placeholder(draw, media_x, y, thumb_w, thumb_h)

        y += thumb_h

        # Label below thumbnail
        label = self._media_label(msg)
        draw.text(
            (media_x, y + 2),
            label,
            fill=self.colors["media_label"],
            font=self.font_media_label,
        )
        y += MEDIA_LABEL_HEIGHT

        return y

    def _draw_media_placeholder(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        w: int,
        h: int,
    ) -> None:
        """Draw a gray placeholder rectangle with a camera icon."""
        draw.rectangle([x, y, x + w, y + h], fill=self.colors["media_placeholder"])
        # Camera icon: simple text centered in the box
        icon = "[camera]"
        icon_bbox = draw.textbbox((0, 0), icon, font=self.font_media_label)
        icon_w = icon_bbox[2] - icon_bbox[0]
        icon_h = icon_bbox[3] - icon_bbox[1]
        draw.text(
            (x + (w - icon_w) // 2, y + (h - icon_h) // 2),
            icon,
            fill=self.colors["media_label"],
            font=self.font_media_label,
        )

    @staticmethod
    def _draw_ghost_icon(
        draw: ImageDraw.ImageDraw,
        cx: int,
        cy: int,
        size: int,
        fill_color: str,
        bg_color: str,
    ) -> None:
        """Draw a Snapchat-inspired ghost silhouette centered at (cx, cy).

        The ghost is built from simple PIL primitives:
        dome head, straight body, wavy bottom tails, two round eyes.
        """
        # Ghost proportions
        w = int(size * 0.7)
        h = size
        half_w = w // 2

        left = cx - half_w
        right = cx + half_w
        top = cy - h // 2
        bottom = cy + h // 2

        # 1. Head dome — upper ellipse
        dome_h = int(h * 0.55)
        draw.ellipse([left, top, right, top + dome_h], fill=fill_color)

        # 2. Body — rectangle from dome midpoint to bottom
        draw.rectangle([left, top + dome_h // 2, right, bottom], fill=fill_color)

        # 3. Wavy bottom — 3 scalloped tails with 2 notch cutouts
        tail_w = w // 3
        notch_h = int(h * 0.12)
        for i in range(2):
            # Cut semicircular notches between the three tails
            nx = left + tail_w * (i + 1) - tail_w // 4
            draw.ellipse(
                [nx, bottom - notch_h, nx + tail_w // 2, bottom + notch_h],
                fill=bg_color,
            )

        # 4. Rounded tail tips
        tip_r = int(tail_w * 0.35)
        for i in range(3):
            tip_cx = left + tail_w * i + tail_w // 2
            draw.ellipse(
                [tip_cx - tip_r, bottom - tip_r, tip_cx + tip_r, bottom + tip_r],
                fill=fill_color,
            )

        # 5. Eyes — two round dots punched out in bg_color
        eye_r = int(size * 0.06)
        eye_y = top + int(h * 0.35)
        for ex in (cx - int(w * 0.2), cx + int(w * 0.2)):
            draw.ellipse(
                [ex - eye_r, eye_y - eye_r, ex + eye_r, eye_y + eye_r],
                fill=bg_color,
            )

    def _draw_media_placeholder_smart(
        self,
        draw: ImageDraw.ImageDraw,
        msg: ChatMessage,
        y: int,
        media_x: int,
    ) -> int:
        """Draw media placeholder with ghost icon for expired/opened snaps.

        In Snapchat exports, any media without a file on disk is an opened
        snap that expired — the DB stores these as media_type='MEDIA', not
        'SNAP', so we always use the ghost treatment.
        Returns new y after placeholder + label.
        """
        w = MEDIA_MAX_WIDTH
        h = MEDIA_HEIGHT

        bg_color = self.colors["snap_placeholder_bg"]
        text_color = self.colors["snap_placeholder_text"]
        label_text = "Opened snap \u2014 expired"

        # Draw rounded placeholder rectangle
        draw.rounded_rectangle(
            [media_x, y, media_x + w, y + h],
            radius=24,
            fill=bg_color,
        )

        # Ghost silhouette centered in placeholder (shifted up for label)
        icon_cy = y + h // 2 - 40
        ghost_size = int(h * 0.4)
        self._draw_ghost_icon(
            draw,
            cx=media_x + w // 2,
            cy=icon_cy,
            size=ghost_size,
            fill_color=text_color,
            bg_color=bg_color,
        )

        # Subtitle text below icon
        sub_font = get_font(84)
        sub_bbox = draw.textbbox((0, 0), label_text, font=sub_font)
        sub_w = sub_bbox[2] - sub_bbox[0]
        sub_y = y + h // 2 + int(h * 0.15)
        draw.text(
            (media_x + (w - sub_w) // 2, sub_y),
            label_text,
            fill=text_color,
            font=sub_font,
        )

        y += h

        # Type label below placeholder (same as normal media)
        type_label = self._media_label(msg)
        draw.text(
            (media_x, y + 2),
            type_label,
            fill=self.colors["media_label"],
            font=self.font_media_label,
        )
        y += MEDIA_LABEL_HEIGHT

        return y

    @staticmethod
    def _media_label(msg: ChatMessage) -> str:
        """Build the label string for a media item."""
        mtype = (msg.media_type or "photo").capitalize()
        if msg.media_type == "video" and msg.media_duration:
            return f"Video {msg.media_duration}"
        return mtype

    def _draw_footer(
        self,
        draw: ImageDraw.ImageDraw,
        page: Page,
        total_h: int,
        meta: 'ConversationMeta | None' = None,
    ) -> None:
        """Draw page footer."""
        footer_text = f"Page {page.page_num} of {page.total_pages} \u2014 Snatched v3"
        bbox = draw.textbbox((0, 0), footer_text, font=self.font_footer)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        footer_y = total_h - TOTAL_FOOTER_HEIGHT
        text_x = (CANVAS_WIDTH - text_w) // 2
        text_y = footer_y + (FOOTER_HEIGHT - text_h) // 2

        draw.text(
            (text_x, text_y),
            footer_text,
            fill=self.colors["footer_text"],
            font=self.font_footer,
        )

    def _draw_page_break_marker(self, draw: ImageDraw.ImageDraw, y: int) -> int:
        """Draw a page break indicator: dashed line + down arrow. Returns new y."""
        line_y = y + PAGE_BREAK_HEIGHT // 2
        line_color = self.colors["page_break_line"]
        arrow_color = self.colors["page_break_arrow"]

        # Dashed line across the page
        dash_len = 40
        gap_len = 20
        x = BUBBLE_MARGIN_SIDE
        while x < CANVAS_WIDTH - BUBBLE_MARGIN_SIDE:
            end_x = min(x + dash_len, CANVAS_WIDTH - BUBBLE_MARGIN_SIDE)
            draw.line([(x, line_y), (end_x, line_y)], fill=line_color, width=2)
            x += dash_len + gap_len

        # Down arrow in center
        cx = CANVAS_WIDTH // 2
        arrow_size = 20
        draw.polygon(
            [(cx - arrow_size, line_y + 8),
             (cx + arrow_size, line_y + 8),
             (cx, line_y + 8 + arrow_size)],
            fill=arrow_color,
        )

        return y + PAGE_BREAK_HEIGHT

    def _draw_cover_page(self, meta: 'ConversationMeta') -> Image.Image:
        """Render the cover page with gradient background, partner name, and first message quote."""
        img = Image.new("RGBA", (CANVAS_WIDTH, MAX_PAGE_HEIGHT), "#000000")
        draw = ImageDraw.Draw(img)

        # Vertical gradient background (blue top → darker blue bottom)
        top_r, top_g, top_b = int(COVER_GRADIENT_TOP[1:3], 16), int(COVER_GRADIENT_TOP[3:5], 16), int(COVER_GRADIENT_TOP[5:7], 16)
        bot_r, bot_g, bot_b = int(COVER_GRADIENT_BOT[1:3], 16), int(COVER_GRADIENT_BOT[3:5], 16), int(COVER_GRADIENT_BOT[5:7], 16)

        for y_line in range(MAX_PAGE_HEIGHT):
            ratio = y_line / MAX_PAGE_HEIGHT
            r = int(top_r + (bot_r - top_r) * ratio)
            g = int(top_g + (bot_g - top_g) * ratio)
            b = int(top_b + (bot_b - top_b) * ratio)
            draw.line([(0, y_line), (CANVAS_WIDTH, y_line)], fill=(r, g, b))

        # Center content vertically (rough: place partner name at ~35% from top)
        center_x = CANVAS_WIDTH // 2
        y = int(MAX_PAGE_HEIGHT * 0.30)

        # Partner name (large bold, centered)
        font_name = get_font(280, bold=True)
        name_text = meta.partner_name
        name_bbox = draw.textbbox((0, 0), name_text, font=font_name)
        name_w = name_bbox[2] - name_bbox[0]
        name_h = name_bbox[3] - name_bbox[1]
        draw.text(
            (center_x - name_w // 2, y),
            name_text,
            fill=self.colors["cover_text"],
            font=font_name,
        )
        y += name_h + 40

        # Date range (medium, centered)
        font_range = get_font(120)
        range_bbox = draw.textbbox((0, 0), meta.date_range_str, font=font_range)
        range_w = range_bbox[2] - range_bbox[0]
        range_h = range_bbox[3] - range_bbox[1]
        draw.text(
            (center_x - range_w // 2, y),
            meta.date_range_str,
            fill=self.colors["cover_text"],
            font=font_range,
        )
        y += range_h + 20

        # Message count
        count_text = f"{meta.message_count:,} messages"
        count_bbox = draw.textbbox((0, 0), count_text, font=font_range)
        count_w = count_bbox[2] - count_bbox[0]
        count_h = count_bbox[3] - count_bbox[1]
        draw.text(
            (center_x - count_w // 2, y),
            count_text,
            fill=self.colors["cover_text"],
            font=font_range,
        )
        y += count_h + 80

        # Horizontal rule
        rule_margin = 400
        rule_color = self.colors["cover_rule"]
        # cover_rule may be a hex with alpha like "#FFFFFF40"
        # Draw as simple white line with reduced width
        draw.line(
            [(rule_margin, y), (CANVAS_WIDTH - rule_margin, y)],
            fill="#FFFFFF",
            width=2,
        )
        y += 60

        # First message quote (italic, centered, wrapped)
        if meta.first_message_text:
            font_quote = get_font(100, italic=True)
            quote_text = f'"{meta.first_message_text}"'
            # Truncate if too long
            if len(quote_text) > 200:
                quote_text = quote_text[:197] + '..."'

            quote_max_w = CANVAS_WIDTH - 2 * rule_margin
            quote_lines = _wrap_text(quote_text, font_quote, quote_max_w, draw)
            quote_lh = _get_line_height(font_quote)

            for line in quote_lines:
                lbox = draw.textbbox((0, 0), line, font=font_quote)
                lw = lbox[2] - lbox[0]
                draw.text(
                    (center_x - lw // 2, y),
                    line,
                    fill=self.colors["cover_quote_text"],
                    font=font_quote,
                )
                y += quote_lh + LINE_SPACING

            y += 20

            # Attribution
            attr_text = f"— {meta.first_message_sender}"
            font_attr = get_font(84)
            attr_bbox = draw.textbbox((0, 0), attr_text, font=font_attr)
            attr_w = attr_bbox[2] - attr_bbox[0]
            draw.text(
                (center_x - attr_w // 2, y),
                attr_text,
                fill=self.colors["cover_quote_text"],
                font=font_attr,
            )

        # Footer text at bottom
        footer_text = "Cover — Snatched v3"
        font_footer = get_font(72)
        ft_bbox = draw.textbbox((0, 0), footer_text, font=font_footer)
        ft_w = ft_bbox[2] - ft_bbox[0]
        draw.text(
            (center_x - ft_w // 2, MAX_PAGE_HEIGHT - 120),
            footer_text,
            fill=self.colors["cover_text"],
            font=font_footer,
        )

        return img

    def _draw_closing_page(self, meta: 'ConversationMeta', total_pages: int) -> Image.Image:
        """Render the closing page with last message quote and conversation stats."""
        img = Image.new("RGBA", (CANVAS_WIDTH, MAX_PAGE_HEIGHT), self.colors["bg"])
        draw = ImageDraw.Draw(img)

        center_x = CANVAS_WIDTH // 2
        y = int(MAX_PAGE_HEIGHT * 0.30)

        # "End of conversation" title
        font_title = get_font(160, bold=True)
        title_text = "End of conversation"
        title_bbox = draw.textbbox((0, 0), title_text, font=font_title)
        title_w = title_bbox[2] - title_bbox[0]
        title_h = title_bbox[3] - title_bbox[1]
        draw.text(
            (center_x - title_w // 2, y),
            title_text,
            fill=self.colors["closing_text"],
            font=font_title,
        )
        y += title_h + 80

        # Horizontal rule
        rule_margin = 500
        draw.line(
            [(rule_margin, y), (CANVAS_WIDTH - rule_margin, y)],
            fill=self.colors["closing_text"],
            width=2,
        )
        y += 60

        # Last message quote (italic, centered)
        if meta.last_message_text:
            font_quote = get_font(100, italic=True)
            quote_text = f'"{meta.last_message_text}"'
            if len(quote_text) > 200:
                quote_text = quote_text[:197] + '..."'

            quote_max_w = CANVAS_WIDTH - 2 * rule_margin
            quote_lines = _wrap_text(quote_text, font_quote, quote_max_w, draw)
            quote_lh = _get_line_height(font_quote)

            for line in quote_lines:
                lbox = draw.textbbox((0, 0), line, font=font_quote)
                lw = lbox[2] - lbox[0]
                draw.text(
                    (center_x - lw // 2, y),
                    line,
                    fill=self.colors["closing_quote_text"],
                    font=font_quote,
                )
                y += quote_lh + LINE_SPACING

            y += 20

            # Attribution
            attr_text = f"— {meta.last_message_sender}"
            font_attr = get_font(84)
            attr_bbox = draw.textbbox((0, 0), attr_text, font=font_attr)
            attr_w = attr_bbox[2] - attr_bbox[0]
            draw.text(
                (center_x - attr_w // 2, y),
                attr_text,
                fill=self.colors["closing_quote_text"],
                font=font_attr,
            )
            y += _get_line_height(font_attr) + 80

        # Stats block
        font_stats = get_font(100)
        stats_lines = [
            f"{meta.message_count:,} messages",
            meta.date_range_str,
            f"{total_pages} pages",
        ]

        for stat_line in stats_lines:
            stat_bbox = draw.textbbox((0, 0), stat_line, font=font_stats)
            stat_w = stat_bbox[2] - stat_bbox[0]
            stat_h = stat_bbox[3] - stat_bbox[1]
            draw.text(
                (center_x - stat_w // 2, y),
                stat_line,
                fill=self.colors["closing_text"],
                font=font_stats,
            )
            y += stat_h + 16

        # Footer
        footer_text = f"Exported by Snatched v3 — {meta.export_date}"
        font_footer = get_font(72)
        ft_bbox = draw.textbbox((0, 0), footer_text, font=font_footer)
        ft_w = ft_bbox[2] - ft_bbox[0]
        draw.text(
            (center_x - ft_w // 2, MAX_PAGE_HEIGHT - 120),
            footer_text,
            fill=self.colors["closing_text"],
            font=font_footer,
        )

        return img
