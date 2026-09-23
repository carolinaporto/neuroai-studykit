"""Tests for `GET /api/progress` — M10. Runs against the real dev Postgres, same assumption
as tests/test_api_items.py; each test creates and cleans up its own rows.

This endpoint is deliberately *not* scoped by week (see the router's docstring), so unlike
most other test files here, a synthetic week number doesn't isolate a test from real
content — a topic's aggregate is global. Tests use real `topics.yaml` slugs
(hebbian-plasticity, ltp-ltd: week 3's unit; single-unit-recording: a cross_cutting topic —
same ones tests/test_ingest_generator.py already exercises), verified empty of any real
Item at the time this was written; each test fetches a *baseline* snapshot before adding its
own rows and asserts the *delta*, so a real item tagged with one of these slugs later
doesn't make this flaky the way tests/test_api_sources.py's week-3 test once did.
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
    ReviewState,
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
CHUNK_TEXT = "Some chunk text for M10 progress tests."


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


async def _get_progress(session_factory: async_sessionmaker) -> dict:
    async with _test_client(session_factory) as client:
        resp = await client.get("/api/progress")
        assert resp.status_code == 200
        return resp.json()


def _topic_or_default(body: dict, slug: str) -> dict:
    return next(
        (t for t in body["topics"] if t["slug"] == slug),
        {"slug": slug, "label": None, "item_count": 0, "attempted_count": 0, "avg_score": None},
    )


def _prior_sum(topic: dict) -> float:
    return 0.0 if topic["avg_score"] is None else topic["avg_score"] * topic["attempted_count"]


async def _make_item(
    session_factory: async_sessionmaker,
    *,
    week: int | None,
    topics: list[str],
    status: ItemStatus = ItemStatus.approved,
    prompt: str = "A prompt.",
) -> tuple[uuid.UUID, uuid.UUID]:
    """Returns (item_id, source_id) — deleting the source cascades to chunk/item/attempt/
    review_state."""
    settings = DbSettings()
    async with session_factory() as session:
        if await session.get(User, settings.dev_owner_id) is None:
            session.add(User(id=settings.dev_owner_id, email="owner@studykit.local"))
            await session.flush()

        source = Source(
            owner_id=settings.dev_owner_id,
            week=week,
            title="m10-test-source",
            kind=SourceKind.lecture_pdf,
            storage_uri="test://m10",
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
            prompt=prompt,
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
                misconceptions=[],
                feedback_md="",
                grader_model="test",
                latency_ms=1,
                tokens_used=0,
                created_at=created_at,
            )
        )
        await session.commit()


async def _make_review_state(
    session_factory: async_sessionmaker, *, item_id: uuid.UUID, due_at: datetime
) -> None:
    settings = DbSettings()
    async with session_factory() as session:
        session.add(
            ReviewState(
                user_id=settings.dev_owner_id,
                item_id=item_id,
                stability=5.0,
                difficulty=5.0,
                due_at=due_at,
                reps=1,
                lapses=0,
                last_grade="good",
                last_reviewed_at=due_at - timedelta(days=1),
                fsrs_card={},
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
async def test_mastery_averages_latest_score_across_multi_topic_items_and_sorts_weakest_first() -> (
    None
):
    session_factory = make_session_factory(DbSettings().database_url)
    week = 8201
    now = datetime.now(UTC)

    before = await _get_progress(session_factory)
    hebbian_before = _topic_or_default(before, "hebbian-plasticity")
    ltp_before = _topic_or_default(before, "ltp-ltd")

    a_id, a_source = await _make_item(session_factory, week=week, topics=["hebbian-plasticity"])
    b_id, b_source = await _make_item(
        session_factory, week=week, topics=["hebbian-plasticity", "ltp-ltd"]
    )

    try:
        await _make_attempt(session_factory, item_id=a_id, score=1.0, created_at=now)
        # B's earlier, wrong attempt must not count — only the latest (0.6) should.
        await _make_attempt(session_factory, item_id=b_id, score=0.0, created_at=now)
        await _make_attempt(
            session_factory, item_id=b_id, score=0.6, created_at=now + timedelta(minutes=1)
        )

        body = await _get_progress(session_factory)
        hebbian = _topic_or_default(body, "hebbian-plasticity")
        ltp = _topic_or_default(body, "ltp-ltd")

        assert hebbian["label"] == "Hebbian plasticity"
        assert hebbian["item_count"] == hebbian_before["item_count"] + 2
        assert hebbian["attempted_count"] == hebbian_before["attempted_count"] + 2
        expected_hebbian_avg = (_prior_sum(hebbian_before) + 1.0 + 0.6) / hebbian["attempted_count"]
        assert hebbian["avg_score"] == pytest.approx(expected_hebbian_avg)

        assert ltp["item_count"] == ltp_before["item_count"] + 1
        expected_ltp_avg = (_prior_sum(ltp_before) + 0.6) / ltp["attempted_count"]
        assert ltp["avg_score"] == pytest.approx(expected_ltp_avg)

        if expected_ltp_avg < expected_hebbian_avg:
            slugs = [t["slug"] for t in body["topics"]]
            assert slugs.index("ltp-ltd") < slugs.index("hebbian-plasticity")
    finally:
        await _cleanup(session_factory, [a_source, b_source])


@pytest.mark.asyncio
async def test_topic_with_no_attempts_has_null_avg() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    week = 8202

    before = await _get_progress(session_factory)
    never_before = _topic_or_default(before, "single-unit-recording")

    unattempted_id, unattempted_source = await _make_item(
        session_factory, week=week, topics=["single-unit-recording"]
    )

    try:
        body = await _get_progress(session_factory)
        never_studied = _topic_or_default(body, "single-unit-recording")
        assert never_studied["item_count"] == never_before["item_count"] + 1
        assert never_studied["attempted_count"] == never_before["attempted_count"]
        if never_before["attempted_count"] == 0:
            assert never_studied["avg_score"] is None
        assert unattempted_id  # referenced for clarity
    finally:
        await _cleanup(session_factory, [unattempted_source])


@pytest.mark.asyncio
async def test_draft_retired_and_weekless_items_are_excluded_from_mastery() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    week = 8203

    before = await _get_progress(session_factory)
    hebbian_before = _topic_or_default(before, "hebbian-plasticity")

    draft_id, draft_source = await _make_item(
        session_factory, week=week, topics=["hebbian-plasticity"], status=ItemStatus.draft
    )
    retired_id, retired_source = await _make_item(
        session_factory, week=week, topics=["hebbian-plasticity"], status=ItemStatus.retired
    )
    weekless_id, weekless_source = await _make_item(
        session_factory, week=None, topics=["hebbian-plasticity"]
    )

    try:
        body = await _get_progress(session_factory)
        hebbian = _topic_or_default(body, "hebbian-plasticity")
        # None of draft/retired/weekless contributed — the count is unchanged.
        assert hebbian["item_count"] == hebbian_before["item_count"]
        assert draft_id and retired_id and weekless_id  # referenced for clarity
    finally:
        await _cleanup(session_factory, [draft_source, retired_source, weekless_source])


@pytest.mark.asyncio
async def test_due_counts_bucket_by_calendar_date() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    week = 8204
    now = datetime.now(UTC)
    never_id, never_source = await _make_item(session_factory, week=week, topics=[])
    overdue_id, overdue_source = await _make_item(session_factory, week=week, topics=[])
    today_id, today_source = await _make_item(session_factory, week=week, topics=[])
    upcoming_id, upcoming_source = await _make_item(session_factory, week=week, topics=[])

    before = await _get_progress(session_factory)
    before_due = before["due"]

    try:
        await _make_review_state(
            session_factory, item_id=overdue_id, due_at=now - timedelta(days=2)
        )
        await _make_review_state(session_factory, item_id=today_id, due_at=now)
        await _make_review_state(
            session_factory, item_id=upcoming_id, due_at=now + timedelta(days=7)
        )

        body = await _get_progress(session_factory)
        due = body["due"]
        # `before` was fetched after the 4 items existed but before any ReviewState row, so
        # all 4 (including never_id) were already counted as never_reviewed there. Adding
        # the three ReviewState rows moves exactly those three out of never_reviewed and
        # into their own bucket each — never_id is the one left behind.
        assert due["overdue"] == before_due["overdue"] + 1
        assert due["due_today"] == before_due["due_today"] + 1
        assert due["upcoming"] == before_due["upcoming"] + 1
        assert due["never_reviewed"] == before_due["never_reviewed"] - 3
        assert never_id  # referenced for clarity — no ReviewState created for it on purpose
    finally:
        await _cleanup(
            session_factory, [never_source, overdue_source, today_source, upcoming_source]
        )
