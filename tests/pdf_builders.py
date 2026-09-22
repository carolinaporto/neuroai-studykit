"""Builds tiny PDFs in memory for the scanned-page tests — synthetic, ours (invariant 6), and
no fixture file to keep in sync. A "scan" is a page whose only content is one page-sized
image, plus a few characters of junk embedded text like a real OCR'd scan carries."""

import pymupdf

JUNK_TEXT = "l! 0~ .t1 ool 0. io.tL&"
LONG_TEXT = ("Synaptic strength changes with experience. " * 8).strip()  # well over 200 chars


def _image_pixmap() -> pymupdf.Pixmap:
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 60, 80), False)
    pix.clear_with(180)
    return pix


def text_page(doc: pymupdf.Document, text: str = LONG_TEXT) -> None:
    page = doc.new_page(width=595, height=842)
    page.insert_textbox(pymupdf.Rect(40, 40, 555, 400), text, fontsize=11)


def scanned_page(doc: pymupdf.Document, junk: str = JUNK_TEXT) -> None:
    page = doc.new_page(width=595, height=842)
    page.insert_image(page.rect, pixmap=_image_pixmap())
    page.insert_text((20, 20), junk, fontsize=8)


def slide_with_small_image(doc: pymupdf.Document) -> None:
    """Little text and an image, but the image is a small diagram — not a scan."""
    page = doc.new_page(width=595, height=842)
    page.insert_textbox(pymupdf.Rect(40, 40, 555, 100), "Figure 2: a neuron", fontsize=14)
    page.insert_image(pymupdf.Rect(100, 150, 250, 300), pixmap=_image_pixmap())


def picture_slide(doc: pymupdf.Document) -> None:
    """A full-page photo with a short title on it, like an image-heavy slide: same image and
    text profile as a scan, but the slide's background is a vector drawing."""
    page = doc.new_page(width=595, height=842)
    page.draw_rect(page.rect, color=None, fill=(1, 1, 1))
    page.insert_image(page.rect, pixmap=_image_pixmap())
    page.insert_text((40, 60), "Time Check", fontsize=20)


def full_page_image_with_real_text(doc: pymupdf.Document) -> None:
    """A page-sized background image behind plenty of real text — not a scan."""
    page = doc.new_page(width=595, height=842)
    page.insert_image(page.rect, pixmap=_image_pixmap())
    page.insert_textbox(pymupdf.Rect(40, 40, 555, 400), LONG_TEXT, fontsize=11)


def build_pdf(*page_builders) -> bytes:
    doc = pymupdf.open()
    for builder in page_builders:
        builder(doc)
    data = doc.tobytes()
    doc.close()
    return data
