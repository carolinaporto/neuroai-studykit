"""Tests for `GET /api/checkin/draft` — M11. Runs against the real dev Postgres, same
assumption as tests/test_api_progress.py. Unlike that file, this endpoint *is* scoped by
`week`, so a synthetic week number fully isolates each test — no baseline/delta needed.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.api.core.db import get_session
from apps.api.core.deps import require_owner
from apps.api.main import app
from packages.db.models import (
    Attempt,
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

RUBRIC = [
    {"id": "p1", "point": "a point", "weight": 1.0, "support_quote": "chunk text"},
    {"id": "p2", "point": "another point", "weight": 1.0, "support_quote": "chunk text"},
]
CHUNK_TEXT = "Some chunk text for M11 checkin tests."


@asynccontextmanager
async def _test_client(session_factory: async_sessionmaker) -> AsyncIterator[httpx.AsyncClient]:
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[require_owner] = lambda: None
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(require_owner, None)


async def _make_item(
    session_factory: async_sessionmaker,
    *,
    week: int,
    topics: list[str],
    status: ItemStatus = ItemStatus.approved,
) -> tuple[uuid.UUID, uuid.UUID]:
    settings = DbSettings()
    async with session_factory() as session:
        if await session.get(User, settings.dev_owner_id) is None:
            session.add(User(id=settings.dev_owner_id, email="owner@studykit.local"))
            await session.flush()

        source = Source(
            owner_id=settings.dev_owner_id,
            week=week,
            title="m11-test-source",
            kind=SourceKind.lecture_pdf,
            storage_uri="test://m11",
            sha256=uuid.uuid4().hex + uuid.uuid4().hex,
            status=SourceStatus.ingested,
        )
        session.add(source)
        await session.flush()

        chunk = Chunk(
            source_id=source.id, ordinal=0, text=CHUNK_TEXT, locators=[{"page": 1}],
            token_count=10,
        )
        session.add(chunk)
        await session.flush()

        item = Item(
            source_id=source.id,
            chunk_ids=[chunk.id],
            type=ItemType.free_recall,
            prompt="A prompt.",
            reference_answer="A reference answer.",
            rubric=RUBRIC,
            difficulty=2,
            bloom=ItemBloom.understand,
            topics=topics,
            status=status,
            gen_model="test",
            gen_prompt_version="test",
        )
        session.add(item)
        await session.commit()
        return item.id, source.id


async def _make_attempt(
    session_factory: async_sessionmaker,
    *,
    item_id: uuid.UUID,
    score: float,
    created_at: datetime,
    misconceptions: list[str] | None = None,
) -> None:
    settings = DbSettings()
    async with session_factory() as session:
        session.add(
            Attempt(
                user_id=settings.dev_owner_id,
                item_id=item_id,
                response_text="an answer",
                response_hash=uuid.uuid4().hex,
                score=score,
                rubric_hits=[],
                misconceptions=misconceptions or [],
                feedback_md="",
                grader_model="test",
                latency_ms=1,
                tokens_used=0,
                created_at=created_at,
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
async def test_draft_reports_avg_score_and_weakest_first_topics() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    week = 8301
    now = datetime.now(UTC)
    weak_id, weak_source = await _make_item(session_factory, week=week, topics=["weak-topic"])
    strong_id, strong_source = await _make_item(
        session_factory, week=week, topics=["strong-topic"]
    )

    try:
        await _make_attempt(session_factory, item_id=weak_id, score=0.2, created_at=now)
        await _make_attempt(session_factory, item_id=strong_id, score=0.9, created_at=now)

        async with _test_client(session_factory) as client:
            resp = await client.get("/api/checkin/draft", params={"week": week})
            assert resp.status_code == 200
            body = resp.json()

            assert body["week"] == week
            assert body["items_total"] == 2
            assert body["items_attempted"] == 2
            assert body["avg_score"] == pytest.approx(0.55)
            assert [t["slug"] for t in body["topics"]] == ["weak-topic", "strong-topic"]

            markdown = body["draft_markdown"]
            assert "1/2" not in markdown  # sanity: not a stale/miscomputed fraction
            assert "2/2" in markdown
            assert "55%" in markdown
            assert "weak-topic" in markdown or "strong-topic" in markdown
    finally:
        await _cleanup(session_factory, [weak_source, strong_source])


@pytest.mark.asyncio
async def test_misconceptions_come_only_from_the_latest_attempt() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    week = 8302
    now = datetime.now(UTC)
    item_id, source_id = await _make_item(session_factory, week=week, topics=["a-topic"])

    try:
        await _make_attempt(
            session_factory,
            item_id=item_id,
            score=0.1,
            created_at=now,
            misconceptions=["confused X with Y"],
        )
        await _make_attempt(
            session_factory,
            item_id=item_id,
            score=1.0,
            created_at=now + timedelta(minutes=1),
            misconceptions=["a fresher, different note"],
        )

        async with _test_client(session_factory) as client:
            resp = await client.get("/api/checkin/draft", params={"week": week})
            body = resp.json()
            assert body["misconceptions"] == ["a fresher, different note"]
            assert "confused X with Y" not in body["draft_markdown"]
    finally:
        await _cleanup(session_factory, [source_id])


@pytest.mark.asyncio
async def test_week_with_items_but_no_attempts_is_a_valid_empty_draft() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    week = 8303
    item_id, source_id = await _make_item(session_factory, week=week, topics=["untried"])

    try:
        async with _test_client(session_factory) as client:
            resp = await client.get("/api/checkin/draft", params={"week": week})
            assert resp.status_code == 200
            body = resp.json()
            assert body["items_total"] == 1
            assert body["items_attempted"] == 0
            assert body["avg_score"] is None
            assert body["misconceptions"] == []
            assert "0/1" in body["draft_markdown"]
        assert item_id  # referenced for clarity
    finally:
        await _cleanup(session_factory, [source_id])


@pytest.mark.asyncio
async def test_week_with_no_items_at_all_is_a_valid_empty_draft_not_a_404() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    week = 8304  # nothing ever created for this week

    async with _test_client(session_factory) as client:
        resp = await client.get("/api/checkin/draft", params={"week": week})
        assert resp.status_code == 200
        body = resp.json()
        assert body["items_total"] == 0
        assert body["items_attempted"] == 0
        assert body["topics"] == []
        assert "No practice questions" in body["draft_markdown"]


@pytest.mark.asyncio
async def test_draft_and_retired_items_are_excluded() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    week = 8305
    draft_id, draft_source = await _make_item(
        session_factory, week=week, topics=["x"], status=ItemStatus.draft
    )
    retired_id, retired_source = await _make_item(
        session_factory, week=week, topics=["x"], status=ItemStatus.retired
    )

    try:
        async with _test_client(session_factory) as client:
            resp = await client.get("/api/checkin/draft", params={"week": week})
            body = resp.json()
            assert body["items_total"] == 0
        assert draft_id and retired_id  # referenced for clarity
    finally:
        await _cleanup(session_factory, [draft_source, retired_source])
