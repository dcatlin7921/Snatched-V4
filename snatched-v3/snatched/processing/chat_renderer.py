"""Snapchat-style chat conversation renderer.

Ported from v2 chat_renderer.py (1,101 lines) with minimal changes:
- Footer text: "Snatched v3" (was v2)
- Added progress_cb parameter to render_conversation()
- Python 3.12 type hints (str | None, not Optional[str])
- Removed _demo() / __main__ block

Renders flat left-aligned text with colored left border lines (NOT
iMessage-style bubbles). Snapchat blue (self) and red (friend).
High-resolution output: 2880x5120 px canvas, saved at 600 DPI.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
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


@dataclass
class DateDivider:
    """A date separator between message groups."""
    date_str: str  # e.g. "February 14, 2024"


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
MAX_PAGE_HEIGHT       = 5120   # 2x phone screen (portrait), scaled for 2880w

# Header
HEADER_HEIGHT         = 240    # 2x for hi-res canvas
HEADER_SEPARATOR_H    = 2

# Footer
FOOTER_HEIGHT         = 110    # 2x for hi-res canvas
FOOTER_WATERMARK_H    = 48     # 2x for hi-res canvas
TOTAL_FOOTER_HEIGHT   = FOOTER_HEIGHT + FOOTER_WATERMARK_H

# Date divider
DATE_DIVIDER_HEIGHT   = 120    # 2x for hi-res canvas

# Message layout
MSG_LEFT_PAD          = 40
MSG_BORDER_WIDTH      = 6
MSG_CONTENT_PAD       = 24     # gap between border and text
MSG_RIGHT_PAD         = 50
MSG_TEXT_LEFT          = MSG_LEFT_PAD + MSG_BORDER_WIDTH + MSG_CONTENT_PAD
MSG_MAX_TEXT_WIDTH     = CANVAS_WIDTH - MSG_TEXT_LEFT - MSG_RIGHT_PAD

# Message spacing
SPACING_SAME_SENDER   = 12
SPACING_DIFF_SENDER   = 32

# Sender name line
SENDER_NAME_PAD_BTM   = 8

# Media thumbnails
MEDIA_WIDTH           = 1120
MEDIA_HEIGHT          = 800
MEDIA_LABEL_HEIGHT    = 80
MEDIA_PAD_TOP         = 12
MEDIA_PAD_BOTTOM      = 8

# Text measurement
LINE_SPACING          = 8      # pixels between wrapped lines


# ---------------------------------------------------------------------------
# Color Schemes
# ---------------------------------------------------------------------------

COLORS_LIGHT = {
    "bg":               "#FFFFFF",
    "header_bg":        "#0EADFF",
    "header_text":      "#FFFFFF",
    "header_sep":       "#CCCCCC",
    "date_text":        "#999999",
    "msg_text":         "#1A1A1A",
    "sender_self":      "#0EADFF",
    "sender_friend":    "#FF4444",
    "media_placeholder": "#DDDDDD",
    "media_label":      "#999999",
    "footer_text":      "#999999",
    "watermark_text":   "#CCCCCC",
    "avatar_bg":        "#BBBBBB",
}

COLORS_DARK = {
    "bg":               "#1A1A1A",
    "header_bg":        "#0B8EC4",
    "header_text":      "#FFFFFF",
    "header_sep":       "#444444",
    "date_text":        "#666666",
    "msg_text":         "#E0E0E0",
    "sender_self":      "#0EADFF",
    "sender_friend":    "#FF4444",
    "media_placeholder": "#2A2A2A",
    "media_label":      "#666666",
    "footer_text":      "#555555",
    "watermark_text":   "#333333",
    "avatar_bg":        "#555555",
}


# ---------------------------------------------------------------------------
# Font Loader (cached)
# ---------------------------------------------------------------------------

_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}

# Font search paths in priority order
_FONT_SEARCH = [
    # Public Sans (Snapchat Sans alternative)
    "/usr/share/fonts/truetype/public-sans/PublicSans-Regular.ttf",
    "/usr/share/fonts/opentype/public-sans/PublicSans-Regular.otf",
    "/usr/local/share/fonts/PublicSans-Regular.ttf",
    # DejaVu Sans (good fallback)
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    # Arial
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

_resolved_regular: str | None = None
_resolved_bold: str | None = None


def _find_font_path(search_list: list[str]) -> str | None:
    """Find the first existing font file from the search list."""
    for path in search_list:
        if Path(path).is_file():
            return path
    return None


def _resolve_fonts() -> None:
    """Resolve font paths once, cache the result."""
    global _resolved_regular, _resolved_bold
    if _resolved_regular is None:
        _resolved_regular = _find_font_path(_FONT_SEARCH) or ""
    if _resolved_bold is None:
        _resolved_bold = _find_font_path(_BOLD_FONT_SEARCH) or ""


def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Load a font at the given size, with caching."""
    _resolve_fonts()
    key = ("bold" if bold else "regular", size)
    if key in _font_cache:
        return _font_cache[key]

    path = _resolved_bold if bold else _resolved_regular
    if path:
        try:
            font = ImageFont.truetype(path, size)
            _font_cache[key] = font
            return font
        except (OSError, IOError):
            pass

    # Ultimate fallback: Pillow default (bitmap font, limited sizes)
    font = ImageFont.load_default()
    _font_cache[key] = font
    return font


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
        # Load fonts once so both measure and render share them
        # Sizes 2x for high-clarity text on 2880px canvas
        self.font_msg = get_font(112)
        self.font_sender = get_font(84, bold=True)
        self.font_date = get_font(100)
        self.font_media_label = get_font(84)
        self.draw = _get_measure_draw()

    def measure_message(
        self,
        msg: ChatMessage,
        prev_sender: str | None,
    ) -> int:
        """Return the pixel height of a message block (spacing + name + text + media)."""
        h = 0

        # Inter-message spacing
        if prev_sender is not None:
            h += SPACING_SAME_SENDER if msg.sender == prev_sender else SPACING_DIFF_SENDER
        else:
            h += SPACING_DIFF_SENDER  # first message on page gets full gap

        # Sender name — use font metrics for consistency with render pass
        h += _get_line_height(self.font_sender) + SENDER_NAME_PAD_BTM

        # Message text
        if msg.text:
            h += text_height(msg.text, self.font_msg, MSG_MAX_TEXT_WIDTH)

        # Media thumbnail — only when an actual file exists on disk
        if msg.media_path and Path(msg.media_path).is_file():
            h += MEDIA_PAD_TOP + MEDIA_HEIGHT + MEDIA_PAD_BOTTOM + MEDIA_LABEL_HEIGHT

        # Bottom padding
        h += 4

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

        Each chunk becomes a separate ChatMessage.  Continuation chunks get
        a '(continued)' prefix on the sender name.  2 lines of overlap
        between chunks preserve reading context across page breaks.

        If first_chunk_budget is provided and positive, the first chunk is
        sized to fit within that pixel budget (remaining space on the current
        page).  Subsequent chunks use the full usable_h.
        """
        draw = _get_measure_draw()
        lines = _wrap_text(msg.text, self.font_msg, MSG_MAX_TEXT_WIDTH, draw)
        if not lines:
            return [msg]

        lh = _get_line_height(self.font_msg)
        # Fixed overhead per chunk: spacing + sender name + bottom padding
        overhead = SPACING_DIFF_SENDER + _get_line_height(self.font_sender) + SENDER_NAME_PAD_BTM + 4
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
                sender=msg.sender if not chunks else f"{msg.sender} (continued)",
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
    ) -> list[Page]:
        """Split elements into pages that fit within MAX_PAGE_HEIGHT.

        Each page reserves space for header + footer.  No element is ever
        split across a page boundary.
        """
        if not elements:
            return []

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

        total = len(pages_raw)
        pages: list[Page] = []
        for i, raw in enumerate(pages_raw):
            pages.append(Page(
                elements=[m.element for m in raw],
                page_num=i + 1,
                total_pages=total,
            ))

        return pages


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
        self.font_watermark = get_font(68)

        self.measurer = ContentMeasurer(dark_mode=dark_mode)

    # ---- public API -------------------------------------------------------

    def render_conversation(
        self,
        messages: list[ChatMessage],
        output_dir: Path,
        progress_cb: Callable[[str], None] | None = None,
    ) -> list[Path]:
        """Render full conversation to PNG files.

        Returns list of output file paths (page-1.png, page-2.png, ...).
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Build the element list with date dividers inserted
        elements = self._build_elements(messages)

        # Paginate
        pages = self.measurer.paginate(elements)

        if not pages:
            # Empty conversation: render a single empty page
            pages = [Page(elements=[], page_num=1, total_pages=1)]

        output_paths: list[Path] = []
        for page in pages:
            img = self.render_single_page(page, self.username)
            path = output_dir / f"page-{page.page_num}.png"
            img.save(str(path), "PNG", optimize=True, dpi=(600, 600))
            output_paths.append(path)

            if progress_cb:
                progress_cb(
                    f"Rendered page {page.page_num} of {page.total_pages}"
                )

        return output_paths

    def render_single_page(self, page: Page, username: str) -> Image.Image:
        """Render a single page to a PIL Image."""
        # All pages use the same fixed height for uniform dimensions.
        total_h = MAX_PAGE_HEIGHT

        img = Image.new("RGB", (CANVAS_WIDTH, total_h), self.colors["bg"])
        draw = ImageDraw.Draw(img)

        # Draw header
        self._draw_header(draw, username)

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
        self._draw_footer(draw, page, total_h)

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
                elements.append(DateDivider(date_str=date_str))
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

    def _draw_header(self, draw: ImageDraw.ImageDraw, username: str) -> None:
        """Draw the Snapchat-style header bar."""
        # Background
        draw.rectangle(
            [0, 0, CANVAS_WIDTH, HEADER_HEIGHT],
            fill=self.colors["header_bg"],
        )

        # Back chevron (<)
        chev_x, chev_y = 40, HEADER_HEIGHT // 2
        chev_size = 24
        draw.line(
            [(chev_x + chev_size, chev_y - chev_size),
             (chev_x, chev_y),
             (chev_x + chev_size, chev_y + chev_size)],
            fill=self.colors["header_text"],
            width=6,
        )

        # Avatar circle (placeholder)
        avatar_x = 112
        avatar_y = HEADER_HEIGHT // 2
        avatar_r = 40
        draw.ellipse(
            [avatar_x - avatar_r, avatar_y - avatar_r,
             avatar_x + avatar_r, avatar_y + avatar_r],
            fill=self.colors["avatar_bg"],
        )

        # Username text
        name_x = avatar_x + avatar_r + 28
        name_bbox = draw.textbbox((0, 0), username, font=self.font_header_name)
        name_h = name_bbox[3] - name_bbox[1]
        name_y = (HEADER_HEIGHT // 2) - name_h - 4
        draw.text(
            (name_x, name_y),
            username,
            fill=self.colors["header_text"],
            font=self.font_header_name,
        )

        # "Active" status
        status_y = name_y + name_h + 8
        draw.text(
            (name_x, status_y),
            "Active",
            fill=self.colors["header_text"],
            font=self.font_header_status,
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
        """Draw a centered date divider. Returns new y position."""
        bbox = draw.textbbox((0, 0), divider.date_str, font=self.font_date)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        text_x = (CANVAS_WIDTH - text_w) // 2
        text_y = y + (DATE_DIVIDER_HEIGHT - text_h) // 2

        draw.text(
            (text_x, text_y),
            divider.date_str,
            fill=self.colors["date_text"],
            font=self.font_date,
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
        """Draw a single message block. Returns new y position."""

        # Spacing
        if prev_sender is not None:
            y += SPACING_SAME_SENDER if msg.sender == prev_sender else SPACING_DIFF_SENDER
        else:
            y += SPACING_DIFF_SENDER

        block_start_y = y

        # Sender color
        sender_color = self.colors["sender_self"] if msg.is_self else self.colors["sender_friend"]

        # Sender name (uppercase, bold, in sender color)
        sender_text = msg.sender.upper()
        sender_lh = _get_line_height(self.font_sender)

        draw.text(
            (MSG_TEXT_LEFT, y),
            sender_text,
            fill=sender_color,
            font=self.font_sender,
        )
        y += sender_lh + SENDER_NAME_PAD_BTM

        # Message text (word-wrapped)
        if msg.text:
            msg_lh = _get_line_height(self.font_msg)
            lines = _wrap_text(msg.text, self.font_msg, MSG_MAX_TEXT_WIDTH, draw)
            for i, line in enumerate(lines):
                draw.text(
                    (MSG_TEXT_LEFT, y),
                    line,
                    fill=self.colors["msg_text"],
                    font=self.font_msg,
                )
                y += msg_lh
                if i < len(lines) - 1:
                    y += LINE_SPACING

        # Media thumbnail — only when an actual file exists on disk
        if msg.media_path and Path(msg.media_path).is_file():
            y += MEDIA_PAD_TOP
            y = self._draw_media(draw, img, msg, y)
            y += MEDIA_PAD_BOTTOM

        # Bottom padding
        y += 4

        # Draw the left border line (6px wide, full height of message block)
        border_x = MSG_LEFT_PAD
        draw.rectangle(
            [border_x, block_start_y, border_x + MSG_BORDER_WIDTH - 1, y],
            fill=sender_color,
        )

        return y

    def _draw_media(
        self,
        draw: ImageDraw.ImageDraw,
        img: Image.Image,
        msg: ChatMessage,
        y: int,
    ) -> int:
        """Draw a media thumbnail or placeholder. Returns new y after media + label."""
        media_x = MSG_TEXT_LEFT

        if msg.media_path and Path(msg.media_path).is_file():
            # Load actual thumbnail
            try:
                thumb = Image.open(msg.media_path)
                thumb.thumbnail((MEDIA_WIDTH, MEDIA_HEIGHT), Image.Resampling.LANCZOS)
                # Center the thumbnail in the allocated space
                paste_x = media_x
                paste_y = y
                img.paste(thumb, (paste_x, paste_y))
                thumb_w, thumb_h = thumb.size
            except Exception:
                # Fall back to placeholder
                thumb_w, thumb_h = MEDIA_WIDTH, MEDIA_HEIGHT
                self._draw_media_placeholder(draw, media_x, y, thumb_w, thumb_h)
        else:
            # Placeholder rectangle
            thumb_w, thumb_h = MEDIA_WIDTH, MEDIA_HEIGHT
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
    ) -> None:
        """Draw page footer and watermark."""
        # Main footer text
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

        # Watermark
        wm_text = "Vibes together by Claude \u2014 Anthropic"
        wm_bbox = draw.textbbox((0, 0), wm_text, font=self.font_watermark)
        wm_w = wm_bbox[2] - wm_bbox[0]
        wm_x = (CANVAS_WIDTH - wm_w) // 2
        wm_y = footer_y + FOOTER_HEIGHT + 2

        draw.text(
            (wm_x, wm_y),
            wm_text,
            fill=self.colors["watermark_text"],
            font=self.font_watermark,
        )
