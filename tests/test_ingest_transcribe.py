"""Tests for `ingest.transcribe` against `FakeLLM` (CLAUDE.md invariant 5: no test calls the
real Anthropic API). PDFs are built in memory by `tests/pdf_builders.py`."""

import pytest
from ingest.transcribe import (
    MAX_TRANSCRIBED_PAGES,
    TranscriptionFailedError,
    parse_pdf_with_scans,
)

from packages.core.llm import FakeLLM
from tests.pdf_builders import JUNK_TEXT, LONG_TEXT, build_pdf, scanned_page, text_page


@pytest.mark.asyncio
async def test_ordinary_pdf_makes_no_llm_call() -> None:
    llm = FakeLLM([])

    blocks, transcribed = await parse_pdf_with_scans(build_pdf(text_page, text_page), llm)

    assert [b.locator.page for b in blocks] == [1, 2]
    assert transcribed == []
    assert llm.vision_calls == []


@pytest.mark.asyncio
async def test_scanned_page_becomes_a_block_in_page_order_and_its_junk_text_is_dropped() -> None:
    llm = FakeLLM([], vision_responses=["Hebbian: cells that fire together wire together"])

    blocks, transcribed = await parse_pdf_with_scans(
        build_pdf(text_page, scanned_page, text_page), llm
    )

    assert transcribed == [2]
    assert [b.locator.page for b in blocks] == [1, 2, 3]
    assert blocks[1].text == "Hebbian: cells that fire together wire together"
    assert all(JUNK_TEXT not in b.text for b in blocks)
    assert blocks[0].text.startswith(LONG_TEXT[:30])
    assert len(llm.vision_calls) == 1
    assert llm.vision_calls[0]["image_count"] == 1


@pytest.mark.asyncio
async def test_a_failed_call_is_retried_once() -> None:
    llm = FakeLLM([], vision_responses=[RuntimeError("overloaded"), "notes text"])

    blocks, _ = await parse_pdf_with_scans(build_pdf(scanned_page), llm)

    assert [b.text for b in blocks] == ["notes text"]
    assert len(llm.vision_calls) == 2


@pytest.mark.asyncio
async def test_two_failed_calls_fail_with_the_page_and_reason() -> None:
    llm = FakeLLM([], vision_responses=[RuntimeError("overloaded"), RuntimeError("overloaded")])

    with pytest.raises(TranscriptionFailedError) as exc:
        await parse_pdf_with_scans(build_pdf(text_page, scanned_page), llm)

    assert "page 2" in str(exc.value)
    assert "overloaded" in str(exc.value)
    assert len(llm.vision_calls) == 2


@pytest.mark.asyncio
async def test_too_many_scanned_pages_fails_before_spending_anything() -> None:
    llm = FakeLLM([])

    with pytest.raises(TranscriptionFailedError) as exc:
        await parse_pdf_with_scans(build_pdf(*[scanned_page] * (MAX_TRANSCRIBED_PAGES + 1)), llm)

    assert "limit" in str(exc.value)
    assert llm.vision_calls == []


@pytest.mark.asyncio
async def test_a_page_the_model_reports_blank_yields_no_block_but_is_still_listed() -> None:
    llm = FakeLLM([], vision_responses=[""])

    blocks, transcribed = await parse_pdf_with_scans(build_pdf(text_page, scanned_page), llm)

    assert [b.locator.page for b in blocks] == [1]
    assert transcribed == [2]
