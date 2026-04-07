# SPEC-07: Chat Renderer

**Status:** Final
**Version:** 3.0
**Date:** 2026-02-23

---

## Module Overview

The chat renderer is a **near-verbatim port** of v2's `chat_renderer.py` into v3 with minimal modifications.

**V2 source file:** `/home/dave/tools/snapfix/chat_renderer.py` (1,101 lines)

This module generates Snapchat-style chat conversation screenshots as PNG images. The design emphasizes:
- **Flat left-aligned text** with colored left border lines (NOT iMessage-style bubbles)
- **Snapchat color scheme:** light blue (sender self) and red (sender friend)
- **High-resolution output:** 2880×5120 px canvas, saved at 600 DPI
- **Pagination:** Messages split across pages if they exceed max height
- **Oversized message splitting:** Text that exceeds page height is split across multiple pages with 2-line overlap for reading context

The module is used by `snatched/processing/export.py` in Phase 4 to render chat PNG exports.

---

## Files to Create

```
snatched/
└── processing/
    └── chat_renderer.py       # Snapchat-style chat PNG renderer
```

---

## Dependencies

**External packages:**
- `Pillow` — `PIL.Image`, `PIL.ImageDraw`, `PIL.ImageFont`

**System fonts** (searched in priority order at runtime):
- Public Sans (preferred — Snapchat's font)
- DejaVu Sans (Linux standard fallback)
- Liberation Sans (Linux fallback)
- Arial (Windows fallback)
- Pillow default bitmap font (last resort, no size control)

**Docker packages required** (from spec-10 Dockerfile):
```dockerfile
RUN apt-get install -y \
    fonts-dejavu-core \
    fonts-liberation
```

**Specs that build on this:**
- `spec-05-enrich-export.md` — `processing/export.py` imports `ChatRenderer` in Phase 4

---

## V2 Source Reference

**Full source:** `/home/dave/tools/snapfix/chat_renderer.py` (lines 1–1101)

All classes, constants, and functions are ported from v2. Zero algorithmic changes.

| Component | V2 Lines | Description |
|-----------|----------|-------------|
| `ChatMessage` dataclass | 34–42 | Single chat message + metadata |
| `DateDivider` dataclass | 46–48 | Date separator between message groups |
| `Page` dataclass | 52–56 | One rendered page + page numbering |
| `_MeasuredElement` dataclass | 326–330 | Internal: element + pre-calculated height |
| Layout constants | 63–99 | Canvas size, padding, spacing values |
| Color dictionaries | 101–131 | `COLORS_LIGHT` and `COLORS_DARK` |
| `_font_cache`, `_FONT_SEARCH`, `_BOLD_FONT_SEARCH` | 138–161 | Font search paths + cache |
| `_find_font_path()` | 166–171 | Find first existing font from list |
| `_resolve_fonts()` | 174–181 | Resolve + cache font paths once |
| `get_font()` | 183–202 | Load TrueType font at size, with caching |
| `_get_measure_draw()` | 218–224 | Reusable scratch ImageDraw for measurement |
| `_font_line_height()` | 227–237 | ascent + descent from font metrics |
| `_get_line_height()` | 243–248 | Cached `_font_line_height()` |
| `text_height()` | 251–262 | Pixel height of word-wrapped text |
| `_wrap_text()` | 265–318 | Word-wrap with char-split fallback |
| `ContentMeasurer` class | 332–560 | Pre-measures elements, paginates |
| `ChatRenderer` class | 567–979 | Main rendering engine |
| `_demo()` | 985–1100 | Standalone test (not ported to v3) |

---

## Data Structures

### ChatMessage

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class ChatMessage:
    """A single chat message in the conversation."""
    sender: str                           # display name
    text: str                             # message content (may be empty for media-only)
    timestamp: float                      # unix timestamp (seconds since epoch)
    is_self: bool                         # True = exporter (self), False = friend
    media_path: str | None = None         # path to media thumbnail if exists on disk
    media_type: str | None = None         # "photo", "video", "snap"
    media_duration: str | None = None     # "0:12" for videos
```

### DateDivider

```python
@dataclass
class DateDivider:
    """A date separator between message groups."""
    date_str: str  # e.g. "February 14, 2024"
```

### Page

```python
from typing import Union

@dataclass
class Page:
    """A single rendered page of the conversation."""
    elements: list[Union[ChatMessage, DateDivider]]  # Messages + dividers on this page
    page_num: int                                    # 1-indexed page number
    total_pages: int                                 # Total pages in conversation
```

---

## Layout Constants

These constants are identical to v2 and must not be changed:

```python
# Canvas dimensions
CANVAS_WIDTH          = 2880           # Width (px) at 2x scale for hi-res output
MAX_PAGE_HEIGHT       = 5120           # Max height (px) per page

# Header
HEADER_HEIGHT         = 240            # Header bar height (2x scale)
HEADER_SEPARATOR_H    = 2              # Separator line below header

# Footer
FOOTER_HEIGHT         = 110            # Footer bar height (2x scale)
FOOTER_WATERMARK_H    = 48             # Watermark text height below footer
TOTAL_FOOTER_HEIGHT   = FOOTER_HEIGHT + FOOTER_WATERMARK_H  # = 158

# Date divider
DATE_DIVIDER_HEIGHT   = 120            # Date separator height

# Message layout
MSG_LEFT_PAD          = 40             # Left padding before colored border
MSG_BORDER_WIDTH      = 6              # Left border thickness
MSG_CONTENT_PAD       = 24             # Gap between border and text
MSG_RIGHT_PAD         = 50             # Right padding
MSG_TEXT_LEFT         = MSG_LEFT_PAD + MSG_BORDER_WIDTH + MSG_CONTENT_PAD  # = 70
MSG_MAX_TEXT_WIDTH    = CANVAS_WIDTH - MSG_TEXT_LEFT - MSG_RIGHT_PAD        # = 2760

# Message spacing
SPACING_SAME_SENDER   = 12             # Vertical gap (consecutive messages, same sender)
SPACING_DIFF_SENDER   = 32             # Vertical gap (different sender)

# Sender name
SENDER_NAME_PAD_BTM   = 8              # Below sender name, above message text

# Media thumbnails
MEDIA_WIDTH           = 1120           # Thumbnail max width
MEDIA_HEIGHT          = 800            # Thumbnail max height
MEDIA_LABEL_HEIGHT    = 80             # Label text below thumbnail
MEDIA_PAD_TOP         = 12             # Gap above thumbnail
MEDIA_PAD_BOTTOM      = 8             # Gap below label

# Text measurement
LINE_SPACING          = 8              # Pixels between wrapped lines
```

---

## Color Schemes

### Light Mode

```python
COLORS_LIGHT = {
    "bg":                "#FFFFFF",       # White background
    "header_bg":         "#0EADFF",       # Snapchat blue header
    "header_text":       "#FFFFFF",
    "header_sep":        "#CCCCCC",       # Header bottom separator
    "date_text":         "#999999",
    "msg_text":          "#1A1A1A",       # Near-black message text
    "sender_self":       "#0EADFF",       # Self sender name + border (blue)
    "sender_friend":     "#FF4444",       # Friend sender name + border (red)
    "media_placeholder": "#DDDDDD",
    "media_label":       "#999999",
    "footer_text":       "#999999",
    "watermark_text":    "#CCCCCC",
    "avatar_bg":         "#BBBBBB",
}
```

### Dark Mode

```python
COLORS_DARK = {
    "bg":                "#1A1A1A",       # Dark background
    "header_bg":         "#0B8EC4",       # Darker Snapchat blue
    "header_text":       "#FFFFFF",
    "header_sep":        "#444444",
    "date_text":         "#666666",
    "msg_text":          "#E0E0E0",       # Light gray message text
    "sender_self":       "#0EADFF",       # Self sender (same blue)
    "sender_friend":     "#FF4444",       # Friend sender (same red)
    "media_placeholder": "#2A2A2A",
    "media_label":       "#666666",
    "footer_text":       "#555555",
    "watermark_text":    "#333333",
    "avatar_bg":         "#555555",
}
```

---

## Function Signatures

### Font Management

```python
_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}
_resolved_regular: str | None = None
_resolved_bold: str | None = None


def _find_font_path(search_list: list[str]) -> str | None:
    """Find the first existing font file from the search list.

    Args:
        search_list: Ordered list of absolute font file paths

    Returns:
        First path that exists on disk, or None if none found
    """
    ...


def _resolve_fonts() -> None:
    """Resolve font paths once on first use; cache in module globals.

    Sets _resolved_regular and _resolved_bold to the first found path
    (or empty string if not found). Subsequent calls are no-ops.
    """
    ...


def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Load a TrueType font at the given size with module-level caching.

    Font search order (regular):
    1. /usr/share/fonts/truetype/public-sans/PublicSans-Regular.ttf
    2. /usr/share/fonts/opentype/public-sans/PublicSans-Regular.otf
    3. /usr/local/share/fonts/PublicSans-Regular.ttf
    4. /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf
    5. /usr/share/fonts/truetype/msttcorefonts/Arial.ttf
    6. /usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf
    7. Pillow default bitmap font (last resort)

    Font search order (bold):
    1. /usr/share/fonts/truetype/public-sans/PublicSans-Bold.ttf
    2. /usr/share/fonts/opentype/public-sans/PublicSans-Bold.otf
    3. /usr/local/share/fonts/PublicSans-Bold.ttf
    4. /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf
    5. /usr/share/fonts/truetype/msttcorefonts/Arial_Bold.ttf
    6. /usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf
    7. Pillow default bitmap font (last resort)

    Font sizes used in renderer (2x scale for 2880px canvas):
    - Message text:    112px
    - Sender name:     84px bold
    - Date divider:    100px
    - Media label:     84px
    - Header name:     168px bold
    - Header status:   100px
    - Footer:          84px
    - Watermark:       68px

    Args:
        size: Font size in pixels
        bold: Load bold variant if True

    Returns:
        Cached PIL ImageFont.FreeTypeFont instance
    """
    ...
```

### Text Measurement

```python
_measure_img: Image.Image | None = None
_measure_draw: ImageDraw.ImageDraw | None = None


def _get_measure_draw() -> ImageDraw.ImageDraw:
    """Return a reusable scratch ImageDraw for text measurement.

    Creates a 1x1 RGB image once and reuses it. Avoids allocating
    throwaway images during the measurement pass.
    """
    ...


def _font_line_height(font: ImageFont.FreeTypeFont) -> int:
    """Return the proper line height for a font (ascent + descent).

    Uses font.getmetrics() to match the actual vertical space consumed
    when Pillow renders text, not just the tight glyph bounding box.

    Args:
        font: PIL ImageFont

    Returns:
        Pixel height (ascent + descent)
    """
    ...


_line_height_cache: dict[int, int] = {}


def _get_line_height(font: ImageFont.FreeTypeFont) -> int:
    """Cached wrapper around _font_line_height.

    Keyed by id(font) since font objects are module-level singletons.
    """
    ...


def text_height(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> int:
    """Measure pixel height of word-wrapped text.

    Wraps text to fit within max_width, then calculates total height
    using LINE_SPACING between lines. Uses font metrics (ascent + descent)
    for each line height, matching actual rendered output exactly.

    Args:
        text: Text to measure
        font: PIL ImageFont to use for measurement
        max_width: Maximum line width in pixels

    Returns:
        Total height in pixels (0 for empty text)
    """
    ...


def _wrap_text(
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    draw: ImageDraw.ImageDraw,
) -> list[str]:
    """Word-wrap text to fit within max_width pixels.

    Algorithm:
    1. Split by explicit newlines (preserve paragraphs)
    2. For each paragraph, split by whitespace
    3. Build lines word-by-word; when next word exceeds max_width, start new line
    4. If a single word exceeds max_width, split character-by-character

    Args:
        text: Text to wrap
        font: PIL ImageFont for measurement
        max_width: Maximum line width in pixels
        draw: PIL ImageDraw for textbbox() measurement calls

    Returns:
        list[str] of wrapped lines (may be empty for empty text)
    """
    ...
```

### Content Measurer

```python
from dataclasses import dataclass
from typing import Union

@dataclass
class _MeasuredElement:
    """Internal: an element with its pre-calculated pixel height."""
    element: Union[ChatMessage, DateDivider]
    height: int  # total height including spacing above


class ContentMeasurer:
    """Pre-measures all chat elements and splits them into pages.

    Measurement uses the EXACT same fonts and wrapping logic as ChatRenderer,
    guaranteeing zero drift between measure and render passes:
    - Both use _wrap_text() (same function)
    - Both use _get_line_height() (same function)
    - Both use the same font objects (loaded by get_font())
    """

    def __init__(self, dark_mode: bool = False) -> None:
        """Initialize measurer with fonts and color mode.

        Loads all fonts once. Fonts are shared with ChatRenderer to
        guarantee measurement-render synchronization.

        Args:
            dark_mode: Select dark color scheme if True
        """
        self.dark_mode = dark_mode
        # Font sizes are 2x for high-clarity text on 2880px canvas
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
        """Return pixel height of a message block.

        Includes (in order):
        1. Inter-message spacing (SPACING_SAME_SENDER or SPACING_DIFF_SENDER)
        2. Sender name line (bold, line height from font metrics)
        3. SENDER_NAME_PAD_BTM gap
        4. Message text (word-wrapped, LINE_SPACING between lines)
        5. Media thumbnail block (MEDIA_PAD_TOP + MEDIA_HEIGHT + MEDIA_PAD_BOTTOM + MEDIA_LABEL_HEIGHT)
           — only if media_path exists on disk
        6. 4px bottom padding

        Args:
            msg: Message to measure
            prev_sender: Previous message sender (None for first message on page)

        Returns:
            Height in pixels
        """
        ...

    def measure_date_divider(self) -> int:
        """Return pixel height of a date divider.

        Always returns DATE_DIVIDER_HEIGHT (120px).
        """
        return DATE_DIVIDER_HEIGHT

    def _split_oversized_message(
        self,
        msg: ChatMessage,
        usable_h: int,
        first_chunk_budget: int = 0,
    ) -> list[ChatMessage]:
        """Split a message whose text exceeds page height into chunks.

        Each chunk becomes a separate ChatMessage:
        - First chunk: sender name unchanged
        - Continuation chunks: sender name gets " (continued)" suffix
        - Media (thumbnail) attached ONLY to the last chunk
        - 2-line overlap between chunks for reading context across page breaks

        If first_chunk_budget is provided and positive, the first chunk is
        sized to fit within that budget (remaining space on the current page).
        Subsequent chunks use the full usable_h.

        Args:
            msg: Message to split (must have text)
            usable_h: Usable height per full page (MAX_PAGE_HEIGHT - header - footer)
            first_chunk_budget: Remaining space on current page (0 = use full page)

        Returns:
            list[ChatMessage] of chunks (at least one element)
        """
        ...

    def paginate(
        self,
        elements: list[Union[ChatMessage, DateDivider]],
    ) -> list[Page]:
        """Split elements into pages fitting within MAX_PAGE_HEIGHT.

        Each page reserves space for:
        - HEADER_HEIGHT + HEADER_SEPARATOR_H (top)
        - TOTAL_FOOTER_HEIGHT (bottom)
        - Content in the middle

        When a single element exceeds available space:
        - DateDivider: placed on its own page
        - ChatMessage with text: split via _split_oversized_message()
        - ChatMessage without text (media-only): placed on its own page

        Args:
            elements: list[ChatMessage | DateDivider]

        Returns:
            list[Page] with page_num and total_pages set correctly (1-indexed)
        """
        ...
```

### Chat Renderer

```python
class ChatRenderer:
    """Renders Snapchat-style chat conversation pages as PNG images.

    Architecture:
    - ContentMeasurer pre-measures all elements and paginates
    - ChatRenderer renders each page to a PIL Image and saves as PNG
    - Measure and render use identical fonts/logic → zero drift
    """

    def __init__(self, username: str, dark_mode: bool = False) -> None:
        """Initialize renderer.

        Args:
            username: Name to show in header (contact's display name)
            dark_mode: Use dark color scheme if True
        """
        self.username = username
        self.dark_mode = dark_mode
        self.colors = COLORS_DARK if dark_mode else COLORS_LIGHT

        # Font sizes 2x for high-clarity text on 2880px canvas
        self.font_header_name   = get_font(168, bold=True)
        self.font_header_status = get_font(100)
        self.font_msg           = get_font(112)
        self.font_sender        = get_font(84, bold=True)
        self.font_date          = get_font(100)
        self.font_media_label   = get_font(84)
        self.font_footer        = get_font(84)
        self.font_watermark     = get_font(68)

        self.measurer = ContentMeasurer(dark_mode=dark_mode)

    def render_conversation(
        self,
        messages: list[ChatMessage],
        output_dir: Path,
        progress_cb: "Callable[[str], None] | None" = None,
    ) -> list[Path]:
        """Render full conversation to PNG files.

        Process:
        1. Insert DateDividers between messages on different calendar days
        2. Paginate elements using ContentMeasurer
        3. Render each page to PIL Image
        4. Save as PNG at 600 DPI

        Output filenames: page-1.png, page-2.png, ...

        An empty conversation renders as a single blank page (page-1.png).

        Args:
            messages: List of ChatMessage objects (may be empty)
            output_dir: Directory to write PNGs to (created if missing)
            progress_cb: Optional callback invoked per page (v3 addition)

        Returns:
            list[Path] of output PNG files in page order
        """
        ...

    def render_single_page(self, page: Page, username: str) -> Image.Image:
        """Render a single page to a PIL Image.

        Image dimensions: CANVAS_WIDTH × MAX_PAGE_HEIGHT (2880×5120 px, fixed).
        All pages use the same fixed height for uniform dimensions.

        Args:
            page: Page object with elements
            username: Header username (contact's display name)

        Returns:
            PIL Image (RGB, CANVAS_WIDTH × MAX_PAGE_HEIGHT)
        """
        ...

    def _build_elements(
        self,
        messages: list[ChatMessage],
    ) -> list[Union[ChatMessage, DateDivider]]:
        """Insert DateDividers between messages on different calendar days.

        Messages with timestamp <= 86400 (1 day since epoch) are treated as
        "unknown date" and grouped under a single "Unknown date" divider
        placed before any timestamped messages.

        Timestamped messages are sorted by timestamp ascending, then
        DateDividers are inserted when the calendar date changes.

        Args:
            messages: List of ChatMessage objects (unsorted)

        Returns:
            list[ChatMessage | DateDivider] with dividers inserted
        """
        ...

    def _measure_page_content(self, page: Page) -> int:
        """Measure total content height for a page (excluding header/footer).

        Delegates to self.measurer for element heights.
        """
        ...

    def _draw_header(self, draw: ImageDraw.ImageDraw, username: str) -> None:
        """Draw Snapchat-style header bar.

        Layout (left to right):
        - Back chevron (<) at left edge
        - Avatar circle placeholder
        - Username (bold)
        - "Active" status text below username
        - Bottom separator line

        Background: COLORS['header_bg'] (Snapchat blue)
        """
        ...

    def _draw_date_divider(
        self,
        draw: ImageDraw.ImageDraw,
        divider: DateDivider,
        y: int,
    ) -> int:
        """Draw a centered date divider. Returns new y position after divider."""
        ...

    def _draw_message(
        self,
        draw: ImageDraw.ImageDraw,
        img: Image.Image,
        msg: ChatMessage,
        y: int,
        prev_sender: str | None,
    ) -> int:
        """Draw a single message block. Returns new y position.

        Layout (top to bottom):
        1. Vertical spacing (SPACING_SAME_SENDER or SPACING_DIFF_SENDER)
        2. Sender name (uppercase, bold, sender color)
        3. SENDER_NAME_PAD_BTM gap
        4. Message text (word-wrapped, msg color)
        5. Media thumbnail or placeholder (if media_path)
        6. 4px bottom padding
        7. Left border line (colored by sender, full block height)

        Args:
            draw: PIL ImageDraw
            img: PIL Image (for media paste)
            msg: ChatMessage to draw
            y: Current y position
            prev_sender: Previous message sender (None for first message on page)

        Returns:
            New y position after message block
        """
        ...

    def _draw_media(
        self,
        draw: ImageDraw.ImageDraw,
        img: Image.Image,
        msg: ChatMessage,
        y: int,
    ) -> int:
        """Draw a media thumbnail or placeholder. Returns new y after media + label.

        If media_path exists on disk: load + thumbnail + paste
        Otherwise: draw placeholder rectangle with [camera] icon text

        Args:
            draw: PIL ImageDraw
            img: PIL Image (for paste)
            msg: ChatMessage
            y: Current y

        Returns:
            New y position after thumbnail + label
        """
        ...

    def _draw_media_placeholder(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        w: int,
        h: int,
    ) -> None:
        """Draw a gray placeholder rectangle with centered [camera] icon."""
        ...

    @staticmethod
    def _media_label(msg: ChatMessage) -> str:
        """Build the label string for a media item.

        Examples: "Photo", "Video 0:42", "Snap"
        """
        ...

    def _draw_footer(
        self,
        draw: ImageDraw.ImageDraw,
        page: Page,
        total_h: int,
    ) -> None:
        """Draw page footer and watermark.

        Footer text: "Page {N} of {total} — Snatched v3"
        Watermark:   "Vibes together by Claude — Anthropic"

        Both centered horizontally.
        Footer positioned at total_h - TOTAL_FOOTER_HEIGHT.
        """
        ...
```

---

## Database Schema

N/A — The chat renderer does not interact with the database directly. It receives a list of `ChatMessage` objects from the calling code (`export.py`). The caller queries the per-user SQLite database and constructs the message list.

The relevant query (executed by `export.py`, not this module) that produces the input data:

```sql
SELECT cm.from_user, cm.content, cm.created_ms, cm.media_type, cm.is_sender,
       f.display_name
FROM chat_messages cm
LEFT JOIN friends f ON cm.from_user = f.username
WHERE cm.conversation_id = ?
ORDER BY cm.created_ms ASC;
```

---

## Key SQL Queries

N/A — This module executes no SQL. It is a pure rendering engine that takes structured data in and writes PNG files out.

---

## Multi-User Adaptation

Minimal changes required. The chat renderer is stateless — it takes messages in and writes PNGs out. Multi-user implications:

1. **Output paths** — The `output_dir` parameter is already per-call. In v3, callers pass `/data/{username}/output/chat/{ConvName}/` instead of a hardcoded path.
2. **Font caching** — The module-level `_font_cache` is shared across all users within the same process. This is safe because fonts are read-only system resources.
3. **No user-specific state** — No configuration, preferences, or data is stored between calls.
4. **Concurrent safety** — Multiple users can render simultaneously as long as they write to different output directories (guaranteed by per-user path isolation).

---

## V3 Modifications from V2

The following changes are made when porting from `/home/dave/tools/snapfix/chat_renderer.py`:

### 1. Footer Text Version Bump

V2 footer:
```python
footer_text = f"Page {page.page_num} of {page.total_pages} \u2014 Snatched v2"
```

V3 footer:
```python
footer_text = f"Page {page.page_num} of {page.total_pages} \u2014 Snatched v3"
```

### 2. Progress Callback Parameter

V2 `render_conversation()`:
```python
def render_conversation(self, messages: list[ChatMessage], output_dir: Path) -> list[Path]:
```

V3 adds optional `progress_cb`:
```python
def render_conversation(
    self,
    messages: list[ChatMessage],
    output_dir: Path,
    progress_cb: Callable[[str], None] | None = None,
) -> list[Path]:
```

The callback is invoked per page: `progress_cb(f"Rendering page {page.page_num} of {total_pages}...")`. This allows the web GUI (spec-08/09) to stream rendering progress.

### 3. Python 3.12 Type Hints

V2 uses `Optional[str]` from `typing`. V3 uses `str | None` throughout (Python 3.12 syntax). The `Union` type hint is retained where needed for `list[Union[ChatMessage, DateDivider]]` for clarity; `ChatMessage | DateDivider` is equally valid.

### 4. Demo Function

V2 includes a `_demo()` / `if __name__ == "__main__"` block (lines 985–1101). This is **not ported** to v3 — the web interface replaces standalone testing. Unit tests cover rendering correctness.

---

## System Requirements

### Font Search Paths

**Regular weight (searched in order):**
1. `/usr/share/fonts/truetype/public-sans/PublicSans-Regular.ttf`
2. `/usr/share/fonts/opentype/public-sans/PublicSans-Regular.otf`
3. `/usr/local/share/fonts/PublicSans-Regular.ttf`
4. `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`
5. `/usr/share/fonts/truetype/msttcorefonts/Arial.ttf`
6. `/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf`
7. Pillow default (last resort)

**Bold weight (searched in order):**
1. `/usr/share/fonts/truetype/public-sans/PublicSans-Bold.ttf`
2. `/usr/share/fonts/opentype/public-sans/PublicSans-Bold.otf`
3. `/usr/local/share/fonts/PublicSans-Bold.ttf`
4. `/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf`
5. `/usr/share/fonts/truetype/msttcorefonts/Arial_Bold.ttf`
6. `/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf`
7. Pillow default (last resort)

### Docker

In the Dockerfile (spec-10), these packages are required:

```dockerfile
RUN apt-get install -y --no-install-recommends \
    fonts-dejavu-core \
    fonts-liberation \
    python3-pil
```

`Pillow` itself is installed via `requirements.txt` (not system packages).

---

## Code Examples

### Rendering a Conversation

```python
from pathlib import Path
from processing.chat_renderer import ChatRenderer, ChatMessage

# Build message list from database records
messages = [
    ChatMessage(
        sender="Alex",
        text="Happy Valentine's Day!",
        timestamp=1739491200.0,  # 2025-02-14 12:00:00
        is_self=False,
    ),
    ChatMessage(
        sender="Dave",
        text="Thanks! You too",
        timestamp=1739491320.0,
        is_self=True,
    ),
]

# Render (light mode, default)
renderer = ChatRenderer(username="Alex", dark_mode=False)
output_paths = renderer.render_conversation(
    messages,
    output_dir=Path("/data/dave/output/chat/Alex/Saved Chat Screenshots"),
    progress_cb=lambda msg: print(msg),
)
# output_paths = [Path("...page-1.png")]

# Render (dark mode)
renderer_dark = ChatRenderer(username="Alex", dark_mode=True)
output_paths_dark = renderer_dark.render_conversation(
    messages,
    output_dir=Path("/data/dave/output/chat/Alex/Dark Screenshots"),
)
```

### Integration in export.py (Phase 4)

```python
# In processing/export.py
from processing.chat_renderer import ChatRenderer, ChatMessage

def export_chat_png(db, project_dir, config):
    """Render chat PNG screenshots for all conversations."""
    conversations = get_chat_conversations(db)

    for conv_name, messages_rows in conversations.items():
        # Convert DB rows to ChatMessage objects
        messages = [
            ChatMessage(
                sender=row['display_name'],
                text=row['message_text'] or '',
                timestamp=row['created_at'],
                is_self=(row['direction'] == 'sent'),
                media_path=row['media_path'],
                media_type=row['media_type'],
            )
            for row in messages_rows
        ]

        output_dir = project_dir / 'output' / 'chat' / conv_name / 'Saved Chat Screenshots'
        renderer = ChatRenderer(
            username=conv_name,
            dark_mode=config.lanes.chats.dark_mode
        )
        renderer.render_conversation(messages, output_dir)
```

---

## Acceptance Criteria

- [ ] `ChatMessage`, `DateDivider`, `Page` dataclasses defined with correct fields and Python 3.12 type hints (`str | None`, not `Optional[str]`)
- [ ] Font loading searches in documented priority order
- [ ] Font cache prevents duplicate loads across multiple `render_conversation()` calls
- [ ] Pillow default font used gracefully when no TrueType font found (no exception)
- [ ] `text_height()` matches actual rendered height exactly (zero drift between measure and render)
- [ ] Word wrapping handles long words via character-splitting
- [ ] Messages exceeding page height are split with 2-line overlap between chunks
- [ ] Continuation chunks show " (continued)" suffix on sender name
- [ ] Media attached only to last chunk of split messages
- [ ] Pagination correctly fits content within `MAX_PAGE_HEIGHT - header - footer`
- [ ] Light mode produces white background with blue/red sender colors
- [ ] Dark mode produces dark background with same sender colors
- [ ] Header renders: back chevron, avatar circle, username bold, "Active" status
- [ ] Date dividers centered, correct text color per mode
- [ ] Messages render: sender name, wrapped text, left border line, spacing
- [ ] Media thumbnails loaded and pasted from disk when `media_path` exists
- [ ] Media placeholder shown (gray rectangle + `[camera]` icon) when file missing
- [ ] Footer text: "Page N of M — Snatched v3" (not v2)
- [ ] Watermark: "Vibes together by Claude — Anthropic"
- [ ] Output PNG files are valid RGB images at 2880×5120 px, 600 DPI
- [ ] Empty conversation renders as single blank page (`page-1.png`)
- [ ] Progress callback invoked once per rendered page
- [ ] `output_dir` created if it does not exist

---

## Implementation Notes

### Font Caching

The module-level `_font_cache` persists across all `render_conversation()` calls within a process. This is intentional: TrueType font loading is expensive (~50–100ms per font). The cache is keyed by `("bold"/"regular", size)`.

### Measure-Render Synchronization

The `ContentMeasurer` uses the **exact same** font objects and `_wrap_text()` function as `ChatRenderer`. This is the most important correctness invariant in this module. Any change to font sizes or wrapping logic must be applied to both.

### High-Resolution Output

Canvas is 2880×5120 px saved at 600 DPI. This is designed for printing or high-quality display. On a standard 1440p screen (~100 DPI), a page renders visually at ~1440×2560 px — matching a phone screenshot at double resolution.

### Timestamp Handling

Messages with `timestamp <= 86400` (within 1 day of Unix epoch) are treated as having no valid date. This threshold catches near-zero values from malformed export data. They are grouped under a single "Unknown date" divider placed before all timestamped messages.

### Sender Name Display

Sender names are rendered in UPPERCASE (`msg.sender.upper()`) using the bold font, in the sender's color. This matches Snapchat's chat UI.
