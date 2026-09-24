"""Tests for `ingest.cli.generate_for_week`'s M7-part-2 dedup step. Runs against the real
dev Postgres (`docker compose up` must be running), with `FakeLLM`/`FakeEmbeddingClient` —
CLAUDE.md invariant 5's spirit extended to the embedding provider too.

Uses week 0 — topics.yaml's u03 ("hebbian-plasticity" among its topics) is parked there,
not taught this semester, but its vocabulary is still real and `topics_for_week`
(packages/ingest/topics.py) raises for any week with no `topics.yaml` unit at all, so a
synthetic week number isn't an option here (same constraint
tests/test_api_sources_upload.py's own generate test already documents). Week 0 can never
collide with real content — no real Source.week is ever 0.
"""

import json
import uuid

import pytest
from ingest.cli import EXTRACTION_PROMPT_PATH, _spent_today_by_owner, generate_for_week
from ingest.generator import prompt_version_hash
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from packages.core.embeddings import FakeEmbeddingClient
from packages.core.llm import FakeLLM
from packages.db.models import (
    Chunk,
    Item,
    ItemBloom,
    ItemStatus,
    ItemType,
    Source,
    SourceKind,
    SourceStatus,
    User,
)
from packages.db.session import DbSettings, make_session_factory

WEEK = 0

CHUNK_TEXT = (
    "Hebbian plasticity is often summarized as cells that fire together wire together. "
    "Long-term potentiation is a persistent increase in synaptic strength."
)

DIM = 1536


def _basis(index: int) -> list[float]:
    vector = [0.0] * DIM
    vector[index] = 1.0
    return vector


def _item_json(prompt: str) -> dict:
    return {
        "type": "free_recall",
        "prompt": prompt,
        "reference_answer": "A presynaptic neuron repeatedly driving a postsynaptic neuron "
        "to fire strengthens their connection.",
        "rubric": [
            {
                "point": "Repeated joint activity strengthens the connection.",
                "weight": 1.0,
                "support_quote": "Hebbian plasticity is often summarized as cells that fire "
                "together wire together.",
            },
            {
                "point": "A brief burst can produce a lasting increase in synaptic strength.",
                "weight": 1.0,
                "support_quote": "Long-term potentiation is a persistent increase in "
                "synaptic strength.",
            },
        ],
        "difficulty": 2,
        "bloom": "understand",
        "topics": ["hebbian-plasticity"],
        "proposed_topics": [],
    }


async def _make_chunk(session_factory: async_sessionmaker) -> tuple[uuid.UUID, uuid.UUID]:
    """A fresh, uncovered Source+Chunk under WEEK — returns (chunk_id, source_id)."""
    settings = DbSettings()
    async with session_factory() as session:
        if await session.get(User, settings.dev_owner_id) is None:
            session.add(User(id=settings.dev_owner_id, email="owner@studykit.local"))
            await session.flush()

        source = Source(
            owner_id=settings.dev_owner_id,
            week=WEEK,
            title="generate-for-week-dedup-test",
            kind=SourceKind.lecture_pdf,
            storage_uri="test://dedup-generate",
            sha256=uuid.uuid4().hex + uuid.uuid4().hex,
            status=SourceStatus.ingested,
        )
        session.add(source)
        await session.flush()

        chunk = Chunk(
            source_id=source.id, ordinal=0, text=CHUNK_TEXT, locators=[{"page": 1}],
            token_count=40,
        )
        session.add(chunk)
        await session.commit()
        return chunk.id, source.id


async def _make_source_with_chunks(
    session_factory: async_sessionmaker, texts: list[str]
) -> tuple[list[uuid.UUID], uuid.UUID]:
    """A fresh, uncovered Source with one Chunk per entry in `texts`, in order — returns
    (chunk_ids, source_id). Used by the extraction tests, which need to control exactly what
    each chunk's own text contains (for the anchor-to-a-single-chunk check)."""
    settings = DbSettings()
    async with session_factory() as session:
        if await session.get(User, settings.dev_owner_id) is None:
            session.add(User(id=settings.dev_owner_id, email="owner@studykit.local"))
            await session.flush()

        source = Source(
            owner_id=settings.dev_owner_id,
            week=WEEK,
            title="generate-for-week-extraction-test",
            kind=SourceKind.lecture_pdf,
            storage_uri="test://extraction-generate",
            sha256=uuid.uuid4().hex + uuid.uuid4().hex,
            status=SourceStatus.ingested,
        )
        session.add(source)
        await session.flush()

        chunk_ids: list[uuid.UUID] = []
        for ordinal, text in enumerate(texts):
            chunk = Chunk(
                source_id=source.id,
                ordinal=ordinal,
                text=text,
                locators=[{"page": ordinal + 1}],
                token_count=40,
            )
            session.add(chunk)
            await session.flush()
            chunk_ids.append(chunk.id)
        await session.commit()
        return chunk_ids, source.id


def _extraction_item_json(prompt: str, quotes: list[str]) -> dict:
    return {
        "type": "free_recall",
        "prompt": prompt,
        "reference_answer": "A full-sentence model answer covering both rubric points.",
        "rubric": [
            {"point": f"Point {i + 1} about {prompt[:20]!r}", "weight": 1.0, "support_quote": q}
            for i, q in enumerate(quotes)
        ],
        "difficulty": 3,
        "bloom": "understand",
        "topics": [],
        "proposed_topics": [],
    }


async def _make_existing_item_with_embedding(
    session_factory: async_sessionmaker, *, chunk_id: uuid.UUID, source_id: uuid.UUID
) -> None:
    """A pre-existing item in WEEK with a stored embedding — the thing the first chunk's
    duplicate should be caught against."""
    async with session_factory() as session:
        session.add(
            Item(
                source_id=source_id,
                chunk_ids=[chunk_id],
                type=ItemType.free_recall,
                prompt="An older, already-generated question.",
                reference_answer="An answer.",
                rubric=[
                    {"id": "p1", "point": "x", "weight": 1.0, "support_quote": CHUNK_TEXT}
                ],
                difficulty=2,
                bloom=ItemBloom.understand,
                topics=["hebbian-plasticity"],
                status=ItemStatus.approved,
                gen_model="test",
                gen_prompt_version="test",
                embedding=_basis(0),
            )
        )
        await session.commit()


async def _cleanup(session_factory: async_sessionmaker, source_ids: list[uuid.UUID]) -> None:
    async with session_factory() as session:
        for source_id in source_ids:
            source = await session.get(Source, source_id)
            if source is not None:
                await session.delete(source)
        await session.commit()


@pytest.mark.asyncio
async def test_dedup_catches_a_match_against_an_existing_item_and_against_this_same_run() -> (
    None
):
    session_factory = make_session_factory(DbSettings().database_url)

    # A pre-existing item already carrying embedding _basis(0) — chunk1's "item_dup" below
    # will be generated with that same vector and must be caught against it.
    existing_chunk_id, existing_source_id = await _make_chunk(session_factory)
    await _make_existing_item_with_embedding(
        session_factory, chunk_id=existing_chunk_id, source_id=existing_source_id
    )

    chunk1_id, chunk1_source = await _make_chunk(session_factory)
    chunk2_id, chunk2_source = await _make_chunk(session_factory)

    # chunk1: two items — one duplicates the pre-existing item, one is fresh.
    chunk1_response = json.dumps(
        {
            "items": [
                _item_json("A duplicate of the pre-existing question."),
                _item_json("A genuinely new question about LTP."),
            ]
        }
    )
    # chunk2: one item, embedded identically to chunk1's *fresh* item — must be caught
    # against what chunk1 saved earlier in this same run, not anything pre-existing.
    chunk2_response = json.dumps({"items": [_item_json("A near-duplicate of the LTP one.")]})

    fake_llm = FakeLLM([chunk1_response, chunk2_response])
    fake_embeddings = FakeEmbeddingClient(
        [
            [_basis(0), _basis(1)],  # chunk1: [duplicate-of-existing, fresh]
            [_basis(1)],  # chunk2: duplicate of chunk1's fresh item
        ]
    )

    try:
        result = await generate_for_week(
            WEEK,
            session_factory,
            fake_llm,
            fake_embeddings,
            force=False,
            daily_token_budget=1_000_000,
            max_calls_per_day=1000,
        )

        assert result["chunks_processed"] == 2
        assert result["items_saved"] == 1
        assert result["items_deduped"] == 2
        assert result["items_rejected"] == 0
        assert result["chunks_failed"] == 0

        async with session_factory() as session:
            saved = (
                await session.scalars(
                    select(Item).where(Item.source_id.in_([chunk1_source, chunk2_source]))
                )
            ).all()
        # Only chunk1's fresh item survived — neither the within-chunk duplicate nor
        # chunk2's cross-chunk duplicate was ever persisted.
        assert len(saved) == 1
    finally:
        await _cleanup(session_factory, [existing_source_id, chunk1_source, chunk2_source])


@pytest.mark.asyncio
async def test_generate_for_week_stops_before_the_llm_call_once_the_daily_budget_is_hit() -> None:
    """Security/correctness fix: the daily budget circuit breaker used to only guard
    grading — a stuck retry loop hitting /api/sources/generate had nothing stopping it.
    max_calls_per_day=0 means the very first chunk is already over budget, so the LLM must
    never be called at all (fake_llm.calls stays empty), and that chunk is counted as
    failed rather than silently skipped."""
    session_factory = make_session_factory(DbSettings().database_url)
    chunk_id, source_id = await _make_chunk(session_factory)

    fake_llm = FakeLLM([])  # any call at all is a bug — the queue is deliberately empty
    fake_embeddings = FakeEmbeddingClient([])

    try:
        result = await generate_for_week(
            WEEK,
            session_factory,
            fake_llm,
            fake_embeddings,
            force=False,
            daily_token_budget=1_000_000,
            max_calls_per_day=0,
        )

        assert result["chunks_failed"] == 1
        assert result["items_saved"] == 0
        assert fake_llm.calls == []
        assert chunk_id  # referenced for clarity — no item exists for it either way
    finally:
        await _cleanup(session_factory, [source_id])


@pytest.mark.asyncio
async def test_a_budget_rejected_chunk_does_not_count_against_a_later_check() -> None:
    """A rejected chunk still logs a real (failed) IngestJob for the audit trail, but must
    not count as a "call" the next time the budget is checked — same as grading, where a
    rejected request never creates an Attempt either. Without this, one rejection would
    tighten the call limit for the rest of the rolling window despite spending nothing.

    Baseline-then-delta (not an absolute count): this runs against the real dev Postgres,
    same as every test in this file, so other tests' rows under the same dev_owner_id are
    real and expected — see tests/test_api_progress.py's docstring for the same pattern.
    """
    session_factory = make_session_factory(DbSettings().database_url)
    settings = DbSettings()
    async with session_factory() as session:
        calls_before, tokens_before = await _spent_today_by_owner(
            session, owner_id=settings.dev_owner_id
        )

    _, source_id = await _make_chunk(session_factory)
    try:
        result = await generate_for_week(
            WEEK,
            session_factory,
            FakeLLM([]),
            FakeEmbeddingClient([]),
            force=False,
            daily_token_budget=1,  # impossibly low: any real estimate exceeds it
            max_calls_per_day=1000,
        )
        assert result["chunks_failed"] == 1

        async with session_factory() as session:
            calls_after, tokens_after = await _spent_today_by_owner(
                session, owner_id=settings.dev_owner_id
            )
        assert calls_after == calls_before
        assert tokens_after == tokens_before
    finally:
        await _cleanup(session_factory, [source_id])


@pytest.mark.asyncio
async def test_extracts_the_professors_own_questions_verbatim_with_real_rubrics() -> None:
    """Part 2 of the chunking+extraction plan, case (a): a source whose chunk carries both
    "Facts to know" and "Questions to have a thoughtful answer to" sections gets one
    free_recall item per listed question, with the question copied verbatim as `prompt` and
    a real, quote-anchored rubric — extracted via a second, source-level LLM call after the
    ordinary per-chunk one (which finds nothing here and returns no items)."""
    session_factory = make_session_factory(DbSettings().database_url)
    chunk_text = (
        "Facts to know\n"
        "What is intelligence?\n\n"
        "Questions to have a thoughtful answer to\n"
        "Can intelligence be measured by one number?\n\n"
        "Intelligence is the ability to achieve goals in a wide range of environments. "
        "A single test score cannot capture every cognitive ability a person has."
    )
    quote_a = "Intelligence is the ability to achieve goals in a wide range of environments."
    quote_b = "A single test score cannot capture every cognitive ability a person has."
    (chunk_id,), source_id = await _make_source_with_chunks(session_factory, [chunk_text])

    per_chunk_response = json.dumps({"items": []})
    extraction_response = json.dumps(
        {
            "items": [
                _extraction_item_json("What is intelligence?", [quote_a, quote_b]),
                _extraction_item_json(
                    "Can intelligence be measured by one number?", [quote_a, quote_b]
                ),
            ]
        }
    )
    fake_llm = FakeLLM([per_chunk_response, extraction_response])
    fake_embeddings = FakeEmbeddingClient([[_basis(0), _basis(1)]])

    try:
        result = await generate_for_week(
            WEEK,
            session_factory,
            fake_llm,
            fake_embeddings,
            force=False,
            daily_token_budget=1_000_000,
            max_calls_per_day=1000,
        )

        assert result["chunks_processed"] == 1
        assert result["chunks_failed"] == 0
        assert result["items_saved"] == 2
        assert result["questions_extracted"] == 2
        assert len(fake_llm.calls) == 2

        async with session_factory() as session:
            saved = (
                await session.scalars(select(Item).where(Item.source_id == source_id))
            ).all()
        prompts = {item.prompt for item in saved}
        assert prompts == {
            "What is intelligence?",
            "Can intelligence be measured by one number?",
        }
        for item in saved:
            assert item.chunk_ids == [chunk_id]
            assert item.gen_prompt_version == prompt_version_hash(EXTRACTION_PROMPT_PATH)
    finally:
        await _cleanup(session_factory, [source_id])


@pytest.mark.asyncio
async def test_extraction_makes_no_call_when_neither_professor_heading_is_present() -> None:
    """Part 2, case (b): a source with no "Facts to know" / "Questions to have a thoughtful
    answer to" section anywhere triggers no extraction call at all — the cheap pre-check
    must save the LLM call, not just discard an empty result after paying for it."""
    session_factory = make_session_factory(DbSettings().database_url)
    chunk_text = "Neurons communicate via synapses. Action potentials are all-or-nothing events."
    _, source_id = await _make_source_with_chunks(session_factory, [chunk_text])

    per_chunk_response = json.dumps({"items": []})
    fake_llm = FakeLLM([per_chunk_response])  # a second call would be the extraction bug
    fake_embeddings = FakeEmbeddingClient([])

    try:
        result = await generate_for_week(
            WEEK,
            session_factory,
            fake_llm,
            fake_embeddings,
            force=False,
            daily_token_budget=1_000_000,
            max_calls_per_day=1000,
        )

        assert result["questions_extracted"] == 0
        assert result["items_saved"] == 0
        assert len(fake_llm.calls) == 1
    finally:
        await _cleanup(session_factory, [source_id])


@pytest.mark.asyncio
async def test_extracted_item_is_rejected_when_its_quotes_span_more_than_one_chunk() -> None:
    """Part 2, case (c): an extracted item's rubric quotes are validated against the whole
    concatenated source text, so they can each be real and still not share a single Chunk —
    the anchoring step must reject that item rather than guessing a chunk or spanning
    `chunk_ids` across more than one, per the plan's explicit trade-off."""
    session_factory = make_session_factory(DbSettings().database_url)
    quote_a = "Intelligence is the ability to achieve goals in a wide range of environments."
    quote_b = "A single test score cannot capture every cognitive ability a person has."
    chunk1_text = f"Facts to know\nWhat is intelligence?\n\n{quote_a}"
    chunk2_text = quote_b
    _, source_id = await _make_source_with_chunks(session_factory, [chunk1_text, chunk2_text])

    per_chunk_responses = [json.dumps({"items": []}), json.dumps({"items": []})]
    extraction_response = json.dumps(
        {"items": [_extraction_item_json("What is intelligence?", [quote_a, quote_b])]}
    )
    fake_llm = FakeLLM([*per_chunk_responses, extraction_response])
    fake_embeddings = FakeEmbeddingClient([])  # the rejected item must never reach embedding

    try:
        result = await generate_for_week(
            WEEK,
            session_factory,
            fake_llm,
            fake_embeddings,
            force=False,
            daily_token_budget=1_000_000,
            max_calls_per_day=1000,
        )

        assert result["chunks_processed"] == 2
        assert result["questions_extracted"] == 0
        assert result["items_saved"] == 0
        assert result["items_rejected"] == 1

        async with session_factory() as session:
            saved = (
                await session.scalars(select(Item).where(Item.source_id == source_id))
            ).all()
        assert saved == []
    finally:
        await _cleanup(session_factory, [source_id])
