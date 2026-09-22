"""Reads scanned PDF pages with a vision model, so handwritten notes can be studied from.

CLAUDE.md invariant 5: the only way this module talks to an LLM is through `LLMClient`;
tests inject `FakeLLM`. The prompt is the versioned file `prompts/transcribe_v1.md`.

Invariant 1 caveat: for a scanned page the chunk text *is* the transcription, so a rubric
`support_quote` is checked literally against what the model read, not against the handwriting
itself. A misread word becomes the chunk's truth. That is why the transcription is shown in
the source preview (chunks) for the student to check, and why the prompt forbids "fixing"
anything.

Retry policy mirrors the generator's: one retry per page, then fail with the reason — no
default text for a page we could not read.
"""

from pathlib import Path

from packages.core.llm import LLMClient

from .models import Locator, ParsedBlock
from .parsers.pdf import parse_pdf, render_page_png, scanned_page_numbers

PROMPT_PATH = Path(__file__).parent / "prompts" / "transcribe_v1.md"
MAX_ATTEMPTS = 2  # 1 try + 1 retry, per CLAUDE.md
# Each page is one paid vision call. A cap turns "someone uploaded a 300-page scan" into a
# clear error instead of a surprise bill or a silently partial transcription.
MAX_TRANSCRIBED_PAGES = 30

_USER_PROMPT = "Transcribe the attached page."


class TranscriptionFailedError(Exception):
    """Raised with a human-readable reason; ends up in `IngestJob.error`."""


def load_prompt(path: Path = PROMPT_PATH) -> str:
    return path.read_text(encoding="utf-8")


async def _transcribe_page(data: bytes, page_number: int, llm: LLMClient, system: str) -> str:
    image = render_page_png(data, page_number)
    last_error = "no attempts made"
    for _ in range(MAX_ATTEMPTS):
        try:
            text = await llm.complete_vision(system=system, user=_USER_PROMPT, images=[image])
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            continue
        return text.strip()
    raise TranscriptionFailedError(
        f"could not transcribe page {page_number} after {MAX_ATTEMPTS} attempts: {last_error}"
    )


async def parse_pdf_with_scans(data: bytes, llm: LLMClient) -> tuple[list[ParsedBlock], list[int]]:
    """Blocks for the whole PDF, in page order, plus the 1-indexed pages that were
    transcribed (empty for an ordinary PDF — then no LLM call is made at all).

    A scanned page yields one block with the same `{"page": n}` locator a text page would. A
    scanned page the model reports as blank yields no block (same as a blank text page) but
    is still listed as transcribed.
    """
    scanned = scanned_page_numbers(data)
    if len(scanned) > MAX_TRANSCRIBED_PAGES:
        raise TranscriptionFailedError(
            f"{len(scanned)} scanned pages exceeds the {MAX_TRANSCRIBED_PAGES}-page transcription "
            "limit; split the file and upload it in parts"
        )

    blocks = parse_pdf(data, exclude_pages=scanned)
    if not scanned:
        return blocks, []

    system = load_prompt()
    for page_number in scanned:
        text = await _transcribe_page(data, page_number, llm, system)
        if text:
            blocks.append(ParsedBlock(text=text, locator=Locator(page=page_number)))

    blocks.sort(key=lambda b: b.locator.page or 0)
    return blocks, scanned
