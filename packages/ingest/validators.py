"""Business validators for a single generated item, applied after it already parses against
the `GeneratedItem` Pydantic schema (see `generator.py`).

CLAUDE.md invariant 1: `support_quote` must appear **literally** in the chunk text, modulo
exactly one normalization — see `_collapse_whitespace` — and nothing beyond it. Never widen
that to fuzzy/semantic similarity, and never add another normalization here without going
back to CLAUDE.md first: this file is the one place that decision is made, so a future
change here silently redefines what "literal" means for every item ever generated.
"""

import re

from .generated_item import GeneratedItem, ValidatedItem, ValidatedRubricPoint

_WHITESPACE_RUN = re.compile(r"\s+")


def _collapse_whitespace(text: str) -> str:
    """Collapses any run of space/tab/newline to a single space and trims both ends —
    nothing else (no case-folding, no punctuation/quote/unicode normalization).

    Exists because PyMuPDF's PDF text extraction inserts a literal `\\n` wherever the PDF
    renderer wrapped a line, including mid-sentence, and a model quoting that sentence
    normalizes the break to a space the way any human copying it from a page would — that's
    an extraction artifact, not a paraphrase. Comparing the collapsed forms of both sides
    keeps the check exact on content while no longer failing on incidental whitespace.
    """
    return _WHITESPACE_RUN.sub(" ", text).strip()


class ItemRejected(Exception):
    """Raised with a human-readable reason; the caller records it, it never propagates."""


def check_quotes_in_chunk(item: GeneratedItem, chunk_text: str) -> None:
    normalized_chunk = _collapse_whitespace(chunk_text)
    for point in item.rubric:
        if _collapse_whitespace(point.support_quote) not in normalized_chunk:
            raise ItemRejected(
                f"support_quote not found verbatim in chunk: {point.support_quote!r}"
            )


def check_not_self_answerable(item: GeneratedItem) -> None:
    """An item is self-answerable if the very quote that justifies a rubric point is sitting
    inside the question stem — the student would not need to recall anything. Same
    whitespace-collapse rule as `check_quotes_in_chunk`, applied consistently: it's the same
    "does this literal quote appear in this text" comparison, just against `item.prompt`
    instead of the chunk."""
    normalized_prompt = _collapse_whitespace(item.prompt)
    for point in item.rubric:
        if _collapse_whitespace(point.support_quote) in normalized_prompt:
            raise ItemRejected(
                f"item is self-answerable: support_quote leaks into its own prompt: "
                f"{point.support_quote!r}"
            )


def normalize_topics(item: GeneratedItem, allowed_topics: dict[str, str]) -> list[str]:
    """Maps each topic the model returned to its canonical slug via `allowed_topics`
    (lowercased slug/alias -> canonical slug, built from the exact list offered in the
    prompt). Rejects the item if any topic isn't in that map at all — a real gap belongs in
    `proposed_topics`, not a forced near-match in `topics`."""
    canonical: list[str] = []
    for raw in item.topics:
        slug = allowed_topics.get(raw.strip().lower())
        if slug is None:
            raise ItemRejected(
                f"unknown topic {raw!r}: not in the vocabulary offered for this chunk's week"
            )
        if slug not in canonical:
            canonical.append(slug)
    return canonical


def validate_generated_item(
    item: GeneratedItem, *, chunk_text: str, allowed_topics: dict[str, str]
) -> ValidatedItem:
    """Runs every business validator and, if the item survives, returns the persisted form
    with rubric point ids (`p1..pN`) assigned by us — never trusted from the model
    (invariant 2: the model decides content, our code decides identifiers/aggregation)."""
    check_quotes_in_chunk(item, chunk_text)
    check_not_self_answerable(item)
    topics = normalize_topics(item, allowed_topics)

    rubric = [
        ValidatedRubricPoint(
            id=f"p{i}", point=p.point, weight=p.weight, support_quote=p.support_quote
        )
        for i, p in enumerate(item.rubric, start=1)
    ]
    return ValidatedItem(
        type=item.type,
        prompt=item.prompt,
        reference_answer=item.reference_answer,
        rubric=rubric,
        difficulty=item.difficulty,
        bloom=item.bloom,
        topics=topics,
    )
