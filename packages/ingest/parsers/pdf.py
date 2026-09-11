"""PDF parser: one ParsedBlock per page, locator {"page": n} (1-indexed)."""

import pymupdf

from ..models import Locator, ParsedBlock


def parse_pdf(data: bytes) -> list[ParsedBlock]:
    blocks: list[ParsedBlock] = []
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        for page in doc:
            text = page.get_text().strip()
            if not text:
                continue
            blocks.append(ParsedBlock(text=text, locator=Locator(page=page.number + 1)))
    return blocks
