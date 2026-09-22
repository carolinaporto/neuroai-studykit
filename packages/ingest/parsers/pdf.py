"""PDF parser: one ParsedBlock per page, locator {"page": n} (1-indexed).

Also detects *scanned* pages (a page that is one big image — handwritten notes, a phone scan)
and renders them to PNG so `transcribe.py` can have a vision model read them. Embedded text
on such a page is OCR junk from whatever produced the scan, so `parse_pdf` can skip it.
"""

from collections.abc import Collection

import pymupdf

from ..models import Locator, ParsedBlock

# A page counts as scanned when it has almost no real text, a single image covers most of it,
# AND it has no vector drawing. All three must hold: a slide with a small diagram and a caption
# has an image but real text; a title slide has little text but no page-sized image; and an
# image-heavy slide (a photo with a title on it) has both — but a slide export always carries
# at least its background as a vector drawing, which a scanner or phone-scan app never adds.
# Checked on real decks: without the drawings test, ~20% of ordinary slide pages were flagged.
SCANNED_MAX_TEXT_CHARS = 200
SCANNED_MIN_IMAGE_COVERAGE = 0.8

RENDER_DPI = 150


def parse_pdf(data: bytes, *, exclude_pages: Collection[int] = ()) -> list[ParsedBlock]:
    """`exclude_pages` are 1-indexed page numbers to skip — the scanned ones, whose embedded
    text is junk and is replaced by a transcription."""
    blocks: list[ParsedBlock] = []
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        for page in doc:
            if page.number + 1 in exclude_pages:
                continue
            text = page.get_text().strip()
            if not text:
                continue
            blocks.append(ParsedBlock(text=text, locator=Locator(page=page.number + 1)))
    return blocks


def _is_scanned(page: pymupdf.Page) -> bool:
    if len(page.get_text().strip()) >= SCANNED_MAX_TEXT_CHARS:
        return False
    page_area = page.rect.get_area()
    if page_area <= 0:
        return False
    if page.get_drawings():
        return False
    for info in page.get_image_info():
        visible = pymupdf.Rect(info["bbox"]) & page.rect
        if visible.get_area() / page_area >= SCANNED_MIN_IMAGE_COVERAGE:
            return True
    return False


def scanned_page_numbers(data: bytes) -> list[int]:
    """1-indexed numbers of the pages that are scans, in order."""
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        return [page.number + 1 for page in doc if _is_scanned(page)]


def render_page_png(data: bytes, page_number: int, *, dpi: int = RENDER_DPI) -> bytes:
    """Renders one page (1-indexed) to PNG bytes."""
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        return doc[page_number - 1].get_pixmap(dpi=dpi).tobytes("png")
