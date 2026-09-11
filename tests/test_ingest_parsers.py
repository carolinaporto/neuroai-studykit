from pathlib import Path

from ingest.parsers.pdf import parse_pdf
from ingest.parsers.pptx import parse_pptx
from ingest.parsers.transcript import parse_transcript

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
