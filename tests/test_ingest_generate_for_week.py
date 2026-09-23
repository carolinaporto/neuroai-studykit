"""Tests for `ingest.cli.generate_for_week`'s M7-part-2 dedup step. Runs against the real
dev Postgres (`docker compose up` must be running), with `FakeLLM`/`FakeEmbeddingClient` —
CLAUDE.md invariant 5's spirit extended to the embedding provider too.

Uses week 3, a real syllabus week — `topics_for_week` (packages/ingest/topics.py) raises
for any week with no `topics.yaml` unit, and `generate_for_week` doesn't take a vocabulary
override, so a synthetic week number isn't an option here (same constraint
tests/test_api_sources_upload.py's own generate test already documents). This is safe
against the dev database's real week-3 content: every pre-existing item there has
`embedding = NULL` (the column is brand new), and `find_duplicate_item` only ever compares
against non-NULL embeddings — so nothing this test creates can collide with real content,
and nothing real can be mistaken for one of this test's duplicates.
"""

import json
import uuid

import pytest
from ingest.cli import _spent_today_by_owner, generate_for_week
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

WEEK = 3

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
