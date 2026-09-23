"""Tests for `apps.api.services.scheduling` — M9. Runs against the real dev Postgres, same
assumption as tests/test_api_study.py (`docker compose up` must be running); each test
creates and cleans up its own rows.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fsrs import Rating
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from apps.api.services.scheduling import apply_review, score_to_grade
from packages.db.models import (
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


def test_score_to_grade_boundaries() -> None:
    assert score_to_grade(1.0) is Rating.Good
    assert score_to_grade(0.86) is Rating.Good
    assert score_to_grade(0.85) is Rating.Hard
    assert score_to_grade(0.6) is Rating.Hard
    assert score_to_grade(0.59) is Rating.Again
    assert score_to_grade(0.0) is Rating.Again


async def _make_item(session_factory: async_sessionmaker) -> tuple[uuid.UUID, uuid.UUID]:
    settings = DbSettings()
    async with session_factory() as session:
        if await session.get(User, settings.dev_owner_id) is None:
            session.add(User(id=settings.dev_owner_id, email="owner@studykit.local"))
            await session.flush()

        source = Source(
            owner_id=settings.dev_owner_id,
            week=999,
            title="m9-test-source",
            kind=SourceKind.lecture_pdf,
            storage_uri="test://m9",
            sha256=uuid.uuid4().hex + uuid.uuid4().hex,
            status=SourceStatus.ingested,
        )
        session.add(source)
        await session.flush()

        chunk = Chunk(
            source_id=source.id, ordinal=0, text="Some chunk text.", locators=[{"page": 1}],
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
            rubric=[
                {"id": "p1", "point": "a point", "weight": 1.0, "support_quote": "chunk text"}
            ],
            difficulty=2,
            bloom=ItemBloom.understand,
            topics=[],
            status=ItemStatus.approved,
            gen_model="test",
            gen_prompt_version="test",
        )
        session.add(item)
        await session.commit()
        return item.id, source.id


async def _cleanup(session_factory: async_sessionmaker, source_id: uuid.UUID) -> None:
    async with session_factory() as session:
        source = await session.get(Source, source_id)
        if source is not None:
            await session.delete(source)  # cascades to Chunk/Item/ReviewState
        await session.commit()


@pytest.mark.asyncio
async def test_first_review_of_an_unseen_item_creates_a_row_with_a_future_due_date() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    settings = DbSettings()
    item_id, source_id = await _make_item(session_factory)
    now = datetime(2026, 1, 1, tzinfo=UTC)

    try:
        async with session_factory() as session:
            state = await apply_review(
                session, user_id=settings.dev_owner_id, item_id=item_id, score=1.0, now=now
            )
            await session.commit()

            assert state.reps == 1
            assert state.lapses == 0
            assert state.last_grade == "good"
            assert state.due_at > now
    finally:
        await _cleanup(session_factory, source_id)


@pytest.mark.asyncio
async def test_a_failing_score_counts_as_a_lapse() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    settings = DbSettings()
    item_id, source_id = await _make_item(session_factory)
    now = datetime(2026, 1, 1, tzinfo=UTC)

    try:
        async with session_factory() as session:
            state = await apply_review(
                session, user_id=settings.dev_owner_id, item_id=item_id, score=0.2, now=now
            )
            await session.commit()

            assert state.last_grade == "again"
            assert state.lapses == 1
    finally:
        await _cleanup(session_factory, source_id)


@pytest.mark.asyncio
async def test_a_second_review_the_same_day_does_not_reschedule_again() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    settings = DbSettings()
    item_id, source_id = await _make_item(session_factory)
    morning = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
    evening = datetime(2026, 1, 1, 21, 0, tzinfo=UTC)

    try:
        async with session_factory() as session:
            first = await apply_review(
                session, user_id=settings.dev_owner_id, item_id=item_id, score=1.0, now=morning
            )
            await session.commit()
            first_due, first_reps = first.due_at, first.reps

        async with session_factory() as session:
            second = await apply_review(
                session, user_id=settings.dev_owner_id, item_id=item_id, score=0.0, now=evening
            )
            await session.commit()

            # A same-day resubmission — even a failing one — doesn't move the schedule or
            # count as a lapse; only the grading response (unaffected by this function)
            # reflects the real answer.
            assert second.due_at == first_due
            assert second.reps == first_reps
            assert second.last_grade == "good"
    finally:
        await _cleanup(session_factory, source_id)


@pytest.mark.asyncio
async def test_reviews_on_different_days_both_apply() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    settings = DbSettings()
    item_id, source_id = await _make_item(session_factory)
    day1 = datetime(2026, 1, 1, tzinfo=UTC)
    day2 = day1 + timedelta(days=1)

    try:
        async with session_factory() as session:
            await apply_review(
                session, user_id=settings.dev_owner_id, item_id=item_id, score=1.0, now=day1
            )
            await session.commit()

        async with session_factory() as session:
            state = await apply_review(
                session, user_id=settings.dev_owner_id, item_id=item_id, score=1.0, now=day2
            )
            await session.commit()

            assert state.reps == 2
    finally:
        await _cleanup(session_factory, source_id)


@pytest.mark.asyncio
async def test_review_state_round_trips_through_the_fsrs_card_blob() -> None:
    """The persisted fsrs_card must be enough to resume scheduling correctly — not just a
    debugging artifact."""
    session_factory = make_session_factory(DbSettings().database_url)
    settings = DbSettings()
    item_id, source_id = await _make_item(session_factory)
    now = datetime(2026, 1, 1, tzinfo=UTC)

    try:
        async with session_factory() as session:
            await apply_review(
                session, user_id=settings.dev_owner_id, item_id=item_id, score=1.0, now=now
            )
            await session.commit()

        async with session_factory() as session:
            state = await session.scalar(
                select(ReviewState).where(ReviewState.item_id == item_id)
            )
            assert state.fsrs_card["stability"] == pytest.approx(state.stability)
            assert state.fsrs_card["difficulty"] == pytest.approx(state.difficulty)
    finally:
        await _cleanup(session_factory, source_id)
