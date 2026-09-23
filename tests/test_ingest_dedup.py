"""Tests for `packages.ingest.dedup.find_duplicate_item` — real Postgres+pgvector (the
cosine-distance operator itself is what's under test, not something to fake). Runs against
the dev database, same assumption as tests/test_ingest_sync.py.

Vectors are exact basis/mixed unit vectors, not anything fuzzy: cosine similarity between
`_basis(a)` and `_mix(a, b, w)` is exactly `w`, so the 0.92 threshold gets a precise
boundary test instead of an approximate one.
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

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
from packages.ingest.dedup import DEDUP_COSINE_THRESHOLD, find_duplicate_item

DIM = 1536


def _basis(index: int) -> list[float]:
    vector = [0.0] * DIM
    vector[index] = 1.0
    return vector


def _mix(a: int, b: int, weight_a: float) -> list[float]:
    weight_b = (1 - weight_a**2) ** 0.5
    vector = [0.0] * DIM
    vector[a] = weight_a
    vector[b] = weight_b
    return vector


async def _make_item(
    session_factory: async_sessionmaker, *, week: int, embedding: list[float] | None
) -> tuple[uuid.UUID, uuid.UUID]:
    settings = DbSettings()
    async with session_factory() as session:
        if await session.get(User, settings.dev_owner_id) is None:
            session.add(User(id=settings.dev_owner_id, email="owner@studykit.local"))
            await session.flush()

        source = Source(
            owner_id=settings.dev_owner_id,
            week=week,
            title="dedup-test-source",
            kind=SourceKind.lecture_pdf,
            storage_uri="test://dedup",
            sha256=uuid.uuid4().hex + uuid.uuid4().hex,
            status=SourceStatus.ingested,
        )
        session.add(source)
        await session.flush()

        chunk = Chunk(
            source_id=source.id, ordinal=0, text="chunk text", locators=[{"page": 1}],
            token_count=5,
        )
        session.add(chunk)
        await session.flush()

        item = Item(
            source_id=source.id,
            chunk_ids=[chunk.id],
            type=ItemType.free_recall,
            prompt="A prompt.",
            reference_answer="A reference answer.",
            rubric=[{"id": "p1", "point": "x", "weight": 1.0, "support_quote": "chunk text"}],
            difficulty=1,
            bloom=ItemBloom.recall,
            topics=[],
            status=ItemStatus.draft,
            gen_model="test",
            gen_prompt_version="test",
            embedding=embedding,
        )
        session.add(item)
        await session.commit()
        return item.id, source.id


async def _cleanup(session_factory: async_sessionmaker, source_ids: list[uuid.UUID]) -> None:
    async with session_factory() as session:
        for source_id in source_ids:
            source = await session.get(Source, source_id)
            if source is not None:
                await session.delete(source)
        await session.commit()


@pytest.mark.asyncio
async def test_identical_embedding_is_found_as_a_duplicate() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    week = 8401
    existing_id, source_id = await _make_item(session_factory, week=week, embedding=_basis(0))

    try:
        async with session_factory() as session:
            match = await find_duplicate_item(session, week=week, embedding=_basis(0))
        assert match == existing_id
    finally:
        await _cleanup(session_factory, [source_id])


@pytest.mark.asyncio
async def test_orthogonal_embedding_is_not_a_duplicate() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    week = 8402
    _existing_id, source_id = await _make_item(session_factory, week=week, embedding=_basis(0))

    try:
        async with session_factory() as session:
            match = await find_duplicate_item(session, week=week, embedding=_basis(1))
        assert match is None
    finally:
        await _cleanup(session_factory, [source_id])


@pytest.mark.asyncio
async def test_a_match_in_a_different_week_is_never_returned() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    _existing_id, source_id = await _make_item(session_factory, week=8403, embedding=_basis(0))

    try:
        async with session_factory() as session:
            match = await find_duplicate_item(session, week=8404, embedding=_basis(0))
        assert match is None
    finally:
        await _cleanup(session_factory, [source_id])


@pytest.mark.asyncio
async def test_similarity_boundary_is_exclusive_at_the_threshold() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    week = 8405
    existing_id, source_id = await _make_item(session_factory, week=week, embedding=_basis(0))

    try:
        async with session_factory() as session:
            above = await find_duplicate_item(
                session, week=week, embedding=_mix(0, 1, DEDUP_COSINE_THRESHOLD + 0.02)
            )
            below = await find_duplicate_item(
                session, week=week, embedding=_mix(0, 1, DEDUP_COSINE_THRESHOLD - 0.02)
            )
        assert above == existing_id
        assert below is None
    finally:
        await _cleanup(session_factory, [source_id])


@pytest.mark.asyncio
async def test_items_with_no_embedding_are_never_matched() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    week = 8406
    _existing_id, source_id = await _make_item(session_factory, week=week, embedding=None)

    try:
        async with session_factory() as session:
            match = await find_duplicate_item(session, week=week, embedding=_basis(0))
        assert match is None
    finally:
        await _cleanup(session_factory, [source_id])
