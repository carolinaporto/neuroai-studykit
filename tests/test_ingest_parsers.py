from pathlib import Path

from ingest.parsers.pdf import parse_pdf, render_page_png, scanned_page_numbers
from ingest.parsers.pptx import parse_pptx
from ingest.parsers.transcript import parse_transcript

from tests.pdf_builders import (
    build_pdf,
    full_page_image_with_real_text,
    picture_slide,
    scanned_page,
    slide_with_small_image,
    text_page,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_pdf_one_block_per_page_in_order() -> None:
    blocks = parse_pdf((FIXTURES / "synthetic.pdf").read_bytes())

    assert [b.locator.page for b in blocks] == [1, 2, 3]
    assert all(b.text.strip() for b in blocks)
    assert "Neurons and Membrane Potential" in blocks[0].text
    assert "Synaptic Transmission" in blocks[1].text
    assert "Hebbian Learning and Plasticity" in blocks[2].text


def test_parse_pptx_slide_text_and_notes() -> None:
    blocks = parse_pptx((FIXTURES / "synthetic.pptx").read_bytes())

    assert [b.locator.slide for b in blocks] == [1, 2, 3, 4, 5]
    assert [b.locator.has_notes for b in blocks] == [True, False, True, False, True]
    assert "What Is Machine Learning?" in blocks[0].text
    assert "Notes:" in blocks[0].text
    assert "Notes:" not in blocks[1].text


def test_parse_transcript_cues_have_ordered_time_ranges() -> None:
    blocks = parse_transcript((FIXTURES / "synthetic.vtt").read_bytes())

    assert len(blocks) == 19
    for block in blocks:
        assert block.locator.t1 > block.locator.t0
    starts = [b.locator.t0 for b in blocks]
    assert starts == sorted(starts)
    assert "reinforcement learning" in blocks[0].text


def test_scanned_pages_are_detected_only_for_a_page_sized_image_with_no_text_or_vectors() -> None:
    data = build_pdf(
        text_page,
        scanned_page,
        slide_with_small_image,
        full_page_image_with_real_text,
        picture_slide,
        scanned_page,
    )

    assert scanned_page_numbers(data) == [2, 6]


def test_parse_pdf_can_skip_scanned_pages_so_their_junk_text_never_becomes_a_block() -> None:
    data = build_pdf(text_page, scanned_page)

    with_junk = parse_pdf(data)
    without = parse_pdf(data, exclude_pages=[2])

    assert [b.locator.page for b in with_junk] == [1, 2]
    assert "l! 0~" in with_junk[1].text
    assert [b.locator.page for b in without] == [1]


def test_render_page_png_returns_a_png() -> None:
    png = render_page_png(build_pdf(text_page, scanned_page), 2)

    assert png.startswith(b"\x89PNG\r\n\x1a\n")
