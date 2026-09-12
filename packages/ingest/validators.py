"""Business validators for a single generated item, applied after it already parses against
the `GeneratedItem` Pydantic schema (see `generator.py`).

CLAUDE.md invariant 1: `support_quote` must appear **literally** in the chunk text — plain
substring comparison, never fuzzy/semantic similarity, no matter how tempting that gets.
"""

from .generated_item import GeneratedItem, ValidatedItem, ValidatedRubricPoint


class ItemRejected(Exception):
    """Raised with a human-readable reason; the caller records it, it never propagates."""


def check_quotes_in_chunk(item: GeneratedItem, chunk_text: str) -> None:
    for point in item.rubric:
        if point.support_quote not in chunk_text:
            raise ItemRejected(
                f"support_quote not found verbatim in chunk: {point.support_quote!r}"
            )


def check_not_self_answerable(item: GeneratedItem) -> None:
    """An item is self-answerable if the very quote that justifies a rubric point is sitting
    inside the question stem — the student would not need to recall anything."""
    for point in item.rubric:
        if point.support_quote in item.prompt:
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
