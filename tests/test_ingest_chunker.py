from pathlib import Path

from ingest.chunker import MAX_CHUNK_TOKENS, chunk_blocks, estimate_tokens
from ingest.models import Locator, ParsedBlock
from ingest.parsers.pdf import parse_pdf
from ingest.parsers.pptx import parse_pptx
from ingest.parsers.transcript import parse_transcript

FIXTURES = Path(__file__).parent / "fixtures"


def test_estimate_tokens_grows_with_length() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("one two three") > 0
    assert estimate_tokens("one two three four five six") > estimate_tokens("one two three")


def test_chunk_blocks_empty_input() -> None:
    assert chunk_blocks([]) == []


def test_pdf_fixture_chunks_stay_under_ceiling_and_have_plausible_count() -> None:
    blocks = parse_pdf((FIXTURES / "synthetic.pdf").read_bytes())
    chunks = chunk_blocks(blocks)

    assert len(chunks) >= 2
    for chunk in chunks:
        assert chunk.token_count <= MAX_CHUNK_TOKENS
        assert chunk.locators


def test_pdf_fixture_consecutive_chunks_overlap() -> None:
    blocks = parse_pdf((FIXTURES / "synthetic.pdf").read_bytes())
    chunks = chunk_blocks(blocks)

    shared = {loc.as_dict()["page"] for loc in chunks[0].locators} & {
        loc.as_dict()["page"] for loc in chunks[1].locators
    }
    assert shared, "consecutive chunks should share at least one page locator"


def test_every_chunk_locator_traces_back_to_a_real_parsed_block() -> None:
    for parser, path in [
        (parse_pdf, "synthetic.pdf"),
        (parse_pptx, "synthetic.pptx"),
        (parse_transcript, "synthetic.vtt"),
    ]:
        blocks = parser((FIXTURES / path).read_bytes())
        known_locators = {tuple(sorted(b.locator.as_dict().items())) for b in blocks}
        chunks = chunk_blocks(blocks)

        for chunk in chunks:
            for locator in chunk.locators:
                key = tuple(sorted(locator.as_dict().items()))
                message = f"locator {locator.as_dict()} in {path} not traceable to a source block"
                assert key in known_locators, message


def test_short_slide_never_stands_alone_in_a_chunk() -> None:
    blocks = parse_pptx((FIXTURES / "synthetic.pptx").read_bytes())
    # Force small chunks so the merge behavior (rather than "everything fits in one chunk
    # anyway") is what's actually being exercised.
    chunks = chunk_blocks(
        blocks, min_tokens=50, max_tokens=150, overlap_ratio=0.15, short_block_tokens=120
    )

    for chunk in chunks:
        slides = [loc.slide for loc in chunk.locators if loc.slide is not None]
        if 4 in slides:
            assert len(slides) > 1, "the short 'Backpropagation' slide must merge with a neighbor"


def test_oversized_single_block_is_split_on_sentence_boundaries() -> None:
    long_text = " ".join(f"This is sentence number {i} about neurons." for i in range(200))
    blocks = [ParsedBlock(text=long_text, locator=Locator(page=1))]

    chunks = chunk_blocks(blocks)

    assert len(chunks) >= 2
    for chunk in chunks:
        assert chunk.token_count <= MAX_CHUNK_TOKENS
        assert chunk.text.strip().endswith(".")
