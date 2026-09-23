"""Integration tests for M4: POST /api/study/session, POST /api/study/answer,
PATCH /api/items/{id}. Runs against the real dev Postgres (same assumption as
tests/test_health.py and tests/test_ingest_sync.py — `docker compose up` must be running).
Each test creates and cleans up its own rows so runs stay repeatable. CLAUDE.md invariant
5: no test here ever calls the real Anthropic API — the LLM dependency is always overridden
with `FakeLLM`.

Every test overrides `get_session` with a factory built inside that test, rather than
letting requests use `apps.api.core.db`'s module-level engine: pytest-asyncio gives each
test its own event loop, and an asyncpg connection pool created in one loop breaks when
reused from another, which is exactly what happens if two tests share one app-level engine.
"""

import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.api.core.config import settings as api_settings
from apps.api.core.db import get_session
from apps.api.core.deps import get_current_user_id, get_llm_client, require_owner
from apps.api.main import app
from apps.api.services.budget import estimate_call_tokens
from apps.api.services.grading import compute_score, grade_exact_match
from packages.core.llm import FakeLLM, LLMClient
from packages.db.models import (
    Attempt,
    Chunk,
    Item,
    ItemBloom,
    ItemStatus,
    ItemType,
    QuizAttempt,
    ReviewState,
    Source,
    SourceKind,
    SourceStatus,
    User,
)
from packages.db.session import DbSettings, make_session_factory

RUBRIC = [
    {
        "id": "p1",
        "point": "Repeated joint activity of two connected neurons strengthens their "
        "connection.",
        "weight": 1.0,
        "support_quote": "cells that fire together wire together",
    },
    {
        "id": "p2",
        "point": "A brief high-frequency burst can produce a lasting increase in synaptic "
        "strength.",
        "weight": 2.0,
        "support_quote": "a persistent increase in synaptic strength",
    },
]

CHUNK_TEXT = (
    "Hebbian plasticity is often summarized as cells that fire together wire together. "
    "Long-term potentiation is a persistent increase in synaptic strength."
)


async def _make_item(
    session_factory: async_sessionmaker,
    *,
    status: ItemStatus = ItemStatus.approved,
    item_type: ItemType = ItemType.free_recall,
    prompt: str | None = None,
    reference_answer: str | None = None,
    rubric: list[dict] | None = None,
    choices: dict | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Creates User (if missing) + Source + Chunk + Item rows for one test. Returns
    (item_id, source_id) — deleting the source cascades to chunk/item/attempt.

    `status` defaults to `approved`, not the model's own `draft` default: most of these
    tests exercise `/api/study/*`, and since M6 that only serves studyable items (see
    `STUDYABLE_STATUSES` in `apps/api/routers/study.py`) — pass `status=ItemStatus.draft`
    explicitly for a test that means to exercise the gate itself.

    `item_type`/`rubric`/`choices` default to a `free_recall` item with the 2-point
    `RUBRIC` — M7's cloze/mcq tests pass a 1-point rubric and the matching type instead."""
    settings = DbSettings()
    async with session_factory() as session:
        if await session.get(User, settings.dev_owner_id) is None:
            session.add(User(id=settings.dev_owner_id, email="owner@studykit.local"))
            await session.flush()

        source = Source(
            owner_id=settings.dev_owner_id,
            week=999,
            title="m4-test-source",
            kind=SourceKind.lecture_pdf,
            storage_uri="test://m4",
            sha256=uuid.uuid4().hex + uuid.uuid4().hex,  # 64 chars, unique per test run
            status=SourceStatus.ingested,
        )
        session.add(source)
        await session.flush()

        chunk = Chunk(
            source_id=source.id,
            ordinal=0,
            text=CHUNK_TEXT,
            locators=[{"page": 7}],
            token_count=40,
        )
        session.add(chunk)
        await session.flush()

        item = Item(
            source_id=source.id,
            chunk_ids=[chunk.id],
            type=item_type,
            prompt=prompt
            or "Explain what determines whether repeated neural activity leads to a "
            "lasting change in connection strength.",
            reference_answer=reference_answer
            or "A presynaptic neuron repeatedly helping drive a postsynaptic "
            "neuron to fire strengthens their connection; a brief high-frequency burst can "
            "produce this kind of lasting increase in synaptic strength.",
            rubric=rubric if rubric is not None else RUBRIC,
            choices=choices,
            difficulty=2,
            bloom=ItemBloom.understand,
            topics=["hebbian-plasticity"],
            status=status,
            gen_model="test",
            gen_prompt_version="test",
        )
        session.add(item)
        await session.commit()
        return item.id, source.id


async def _make_items_for_week(
    session_factory: async_sessionmaker,
    week: int,
    count: int = 2,
    *,
    status: ItemStatus = ItemStatus.approved,
) -> tuple[list[uuid.UUID], uuid.UUID]:
    """Like `_make_item` but creates `count` items under one Source/Chunk for a given
    week — what the quiz flow needs (a single item can't exercise "does the attempt
    complete once every item is answered"). Same `status` default and rationale."""
    settings = DbSettings()
    async with session_factory() as session:
        if await session.get(User, settings.dev_owner_id) is None:
            session.add(User(id=settings.dev_owner_id, email="owner@studykit.local"))
            await session.flush()

        source = Source(
            owner_id=settings.dev_owner_id,
            week=week,
            title="quiz-test-source",
            kind=SourceKind.lecture_pdf,
            storage_uri="test://quiz",
            sha256=uuid.uuid4().hex + uuid.uuid4().hex,
            status=SourceStatus.ingested,
        )
        session.add(source)
        await session.flush()

        chunk = Chunk(
            source_id=source.id, ordinal=0, text=CHUNK_TEXT, locators=[{"page": 1}], token_count=40
        )
        session.add(chunk)
        await session.flush()

        item_ids = []
        for i in range(count):
            item = Item(
                source_id=source.id,
                chunk_ids=[chunk.id],
                type=ItemType.free_recall,
                prompt=f"Quiz question {i}",
                reference_answer="A reference answer.",
                rubric=RUBRIC,
                difficulty=2,
                bloom=ItemBloom.understand,
                topics=["hebbian-plasticity"],
                status=status,
                gen_model="test",
                gen_prompt_version="test",
            )
            session.add(item)
            await session.flush()
            item_ids.append(item.id)

        await session.commit()
        return item_ids, source.id


async def _cleanup(session_factory: async_sessionmaker, source_id: uuid.UUID) -> None:
    async with session_factory() as session:
        source = await session.get(Source, source_id)
        if source is not None:
            await session.delete(source)  # cascades to Chunk/Item/Attempt
            await session.commit()


async def _cleanup_quiz_attempts(session_factory: async_sessionmaker, week: int) -> None:
    """QuizAttempt has no FK to Source (it's linked by `week`, a plain int — see its
    docstring), so `_cleanup`'s cascade-via-Source never touches it. Every quiz test must
    call this too, or its rows leak into the next run and inflate per-week attempt counts."""
    async with session_factory() as session:
        attempts = (
            await session.scalars(select(QuizAttempt).where(QuizAttempt.week == week))
        ).all()
        for attempt in attempts:
            await session.delete(attempt)
        await session.commit()


@asynccontextmanager
async def _test_client(
    session_factory: async_sessionmaker, llm: LLMClient | None = None
) -> AsyncIterator[httpx.AsyncClient]:
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[require_owner] = lambda: None
    app.dependency_overrides[get_current_user_id] = lambda: DbSettings().dev_owner_id
    if llm is not None:
        app.dependency_overrides[get_llm_client] = lambda: llm
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(require_owner, None)
        app.dependency_overrides.pop(get_current_user_id, None)
        if llm is not None:
            app.dependency_overrides.pop(get_llm_client, None)


@pytest.mark.asyncio
async def test_compute_score_is_deterministic() -> None:
    """Pure function, called repeatedly with the same input — CLAUDE.md invariant 2."""
    covered = {"p1": True, "p2": False}
    scores = [compute_score(RUBRIC, covered) for _ in range(5)]
    assert scores == [1.0 / 3.0] * 5


_SINGLE_POINT_RUBRIC = [RUBRIC[0]]


@pytest.mark.asyncio
async def test_grade_exact_match_is_a_pure_match_check() -> None:
    """M7: cloze/mcq's whole grading logic, no LLM, no ORM object — see
    apps/api/services/grading.py's docstring for why one function covers both types."""
    covered, feedback = grade_exact_match(
        rubric=_SINGLE_POINT_RUBRIC,
        reference_answer="Hebbian plasticity",
        response_text="Hebbian plasticity",
    )
    assert covered == {"p1": True}
    assert feedback == "Correct."

    covered, feedback = grade_exact_match(
        rubric=_SINGLE_POINT_RUBRIC,
        reference_answer="Hebbian plasticity",
        response_text="  HEBBIAN   plasticity  ",  # normalize_response_text's job
    )
    assert covered == {"p1": True}

    covered, feedback = grade_exact_match(
        rubric=_SINGLE_POINT_RUBRIC,
        reference_answer="Hebbian plasticity",
        response_text="Long-term potentiation",
    )
    assert covered == {"p1": False}
    assert "Hebbian plasticity" in feedback


@pytest.mark.asyncio
async def test_answer_is_deterministic_cached_and_carries_source() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    item_id, source_id = await _make_item(session_factory)

    graded_json = json.dumps(
        {
            "points": [
                {"point_id": "p1", "covered": True, "evidence": "fire together wire together"},
                {"point_id": "p2", "covered": False, "evidence": "not mentioned"},
            ],
            "misconceptions": [],
            "feedback_md": "Good start, but you missed the LTP detail.",
        }
    )
    fake_llm = FakeLLM([graded_json])

    try:
        async with _test_client(session_factory, fake_llm) as client:
            first = await client.post(
                "/api/study/answer",
                json={
                    "item_id": str(item_id),
                    "response_text": "cells that fire together wire together",
                },
            )
            assert first.status_code == 200
            body1 = first.json()
            assert body1["cached"] is False
            assert body1["score"] == pytest.approx(1.0 / 3.0)
            assert body1["source"][0]["locator"] == {"page": 7}
            assert body1["source"][0]["quote"] == RUBRIC[0]["support_quote"]
            assert len(fake_llm.calls) == 1

            # Identical (item_id, response_text) again. FakeLLM has no more queued
            # responses, so a second real LLM call would raise AssertionError inside it —
            # the endpoint must serve this from the cache instead.
            second = await client.post(
                "/api/study/answer",
                json={
                    "item_id": str(item_id),
                    "response_text": "cells that fire together wire together",
                },
            )
            assert second.status_code == 200
            body2 = second.json()
            assert body2["cached"] is True
            assert body2["score"] == body1["score"]
            assert len(fake_llm.calls) == 1  # unchanged: no new LLM call was made
    finally:
        await _cleanup(session_factory, source_id)


@pytest.mark.asyncio
async def test_grading_retries_once_then_succeeds() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    item_id, source_id = await _make_item(session_factory)

    good_json = json.dumps(
        {
            "points": [
                {"point_id": "p1", "covered": True, "evidence": "..."},
                {"point_id": "p2", "covered": True, "evidence": "..."},
            ],
            "misconceptions": [],
            "feedback_md": "Great answer.",
        }
    )
    fake_llm = FakeLLM(["not json at all", good_json])

    try:
        async with _test_client(session_factory, fake_llm) as client:
            resp = await client.post(
                "/api/study/answer",
                json={"item_id": str(item_id), "response_text": "a completely different answer"},
            )
            assert resp.status_code == 200
            assert resp.json()["score"] == pytest.approx(1.0)
            assert len(fake_llm.calls) == 2
    finally:
        await _cleanup(session_factory, source_id)


@pytest.mark.asyncio
async def test_session_returns_queue_without_rubric_or_reference_answer() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    item_id, source_id = await _make_item(session_factory)

    try:
        async with _test_client(session_factory) as client:
            resp = await client.post("/api/study/session", json={"week": 999, "limit": 10})
            assert resp.status_code == 200
            rows = resp.json()
            ids = [row["id"] for row in rows]
            assert str(item_id) in ids
            row = next(r for r in rows if r["id"] == str(item_id))
            assert "rubric" not in row
            assert "reference_answer" not in row
    finally:
        await _cleanup(session_factory, source_id)


@pytest.mark.asyncio
async def test_get_item_source_returns_chunk_text_without_gabarito() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    item_id, source_id = await _make_item(session_factory)

    try:
        async with _test_client(session_factory) as client:
            resp = await client.get(f"/api/study/items/{item_id}/source")
            assert resp.status_code == 200
            body = resp.json()
            assert body["locator"] == {"page": 7}
            assert body["text"] == CHUNK_TEXT
            assert "rubric" not in body
            assert "reference_answer" not in body
    finally:
        await _cleanup(session_factory, source_id)


@pytest.mark.asyncio
async def test_get_item_source_404_for_unknown_item() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    async with _test_client(session_factory) as client:
        resp = await client.get(f"/api/study/items/{uuid.uuid4()}/source")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_item_updates_status() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    item_id, source_id = await _make_item(session_factory)

    try:
        async with _test_client(session_factory) as client:
            resp = await client.patch(f"/api/items/{item_id}", json={"status": "approved"})
            assert resp.status_code == 200
            assert resp.json()["status"] == "approved"

        async with session_factory() as session:
            item = await session.get(Item, item_id)
            assert item.status == ItemStatus.approved
    finally:
        await _cleanup(session_factory, source_id)


@pytest.mark.asyncio
async def test_answer_records_estimated_tokens_used() -> None:
    """A successful grading call stores the same worst-case estimate the budget guard
    checked against — see apps/api/services/budget.py — not metered usage."""
    session_factory = make_session_factory(DbSettings().database_url)
    item_id, source_id = await _make_item(session_factory)

    graded_json = json.dumps(
        {
            "points": [
                {"point_id": "p1", "covered": True, "evidence": "..."},
                {"point_id": "p2", "covered": True, "evidence": "..."},
            ],
            "misconceptions": [],
            "feedback_md": "Great answer.",
        }
    )
    fake_llm = FakeLLM([graded_json])
    response_text = "cells that fire together wire together, and LTP makes it lasting"

    try:
        async with _test_client(session_factory, fake_llm) as client:
            resp = await client.post(
                "/api/study/answer",
                json={"item_id": str(item_id), "response_text": response_text},
            )
            assert resp.status_code == 200

        async with session_factory() as session:
            item = await session.get(Item, item_id)
            attempt = await session.scalar(select(Attempt).where(Attempt.item_id == item_id))
            expected_tokens = estimate_call_tokens(
                item.prompt, json.dumps(item.rubric), response_text
            )
            assert attempt.tokens_used == expected_tokens
            assert attempt.tokens_used > 0
    finally:
        await _cleanup(session_factory, source_id)


@pytest.mark.asyncio
async def test_answer_rejects_when_daily_grading_limit_reached(monkeypatch) -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    item_id, source_id = await _make_item(session_factory)

    async with session_factory() as session:
        session.add(
            Attempt(
                user_id=DbSettings().dev_owner_id,
                item_id=item_id,
                response_text="an earlier answer",
                response_hash="unrelated-hash",
                score=1.0,
                rubric_hits=[],
                misconceptions=[],
                feedback_md="",
                grader_model="test",
                latency_ms=1,
                tokens_used=10,
            )
        )
        await session.commit()

    monkeypatch.setattr(api_settings, "max_gradings_per_day", 1)
    # Never queued a response: if the endpoint called the LLM despite the cap, FakeLLM
    # itself would raise on the empty queue.
    fake_llm = FakeLLM([])

    try:
        async with _test_client(session_factory, fake_llm) as client:
            resp = await client.post(
                "/api/study/answer",
                json={"item_id": str(item_id), "response_text": "a brand new answer text"},
            )
            assert resp.status_code == 429
            assert fake_llm.calls == []
    finally:
        await _cleanup(session_factory, source_id)


@pytest.mark.asyncio
async def test_answer_rejects_when_token_budget_would_be_exceeded(monkeypatch) -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    item_id, source_id = await _make_item(session_factory)

    monkeypatch.setattr(api_settings, "daily_token_budget", 1)
    fake_llm = FakeLLM([])

    try:
        async with _test_client(session_factory, fake_llm) as client:
            resp = await client.post(
                "/api/study/answer",
                json={"item_id": str(item_id), "response_text": "any answer at all"},
            )
            assert resp.status_code == 429
            assert fake_llm.calls == []
    finally:
        await _cleanup(session_factory, source_id)


@pytest.mark.asyncio
async def test_patch_item_rejects_rubric_with_invented_quote() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    item_id, source_id = await _make_item(session_factory)

    bad_rubric = [
        {**RUBRIC[0], "support_quote": "this sentence does not appear in the chunk at all"},
        RUBRIC[1],
    ]
    try:
        async with _test_client(session_factory) as client:
            resp = await client.patch(f"/api/items/{item_id}", json={"rubric": bad_rubric})
            assert resp.status_code == 422

        async with session_factory() as session:
            item = await session.get(Item, item_id)
            assert item.rubric == RUBRIC  # unchanged
    finally:
        await _cleanup(session_factory, source_id)


@pytest.mark.asyncio
async def test_patch_item_rejects_rubric_with_too_few_points() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    item_id, source_id = await _make_item(session_factory)

    try:
        async with _test_client(session_factory) as client:
            resp = await client.patch(f"/api/items/{item_id}", json={"rubric": [RUBRIC[0]]})
            assert resp.status_code == 422
    finally:
        await _cleanup(session_factory, source_id)


@pytest.mark.asyncio
async def test_patch_item_rejects_rubric_with_non_positive_weight() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    item_id, source_id = await _make_item(session_factory)

    bad_rubric = [{**RUBRIC[0], "weight": 0}, RUBRIC[1]]
    try:
        async with _test_client(session_factory) as client:
            resp = await client.patch(f"/api/items/{item_id}", json={"rubric": bad_rubric})
            assert resp.status_code == 422
    finally:
        await _cleanup(session_factory, source_id)


@pytest.mark.asyncio
async def test_patch_item_accepts_valid_rubric_edit() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    item_id, source_id = await _make_item(session_factory, status=ItemStatus.draft)

    edited_rubric = [
        {**RUBRIC[0], "point": "Edited wording of the same rubric point."},
        RUBRIC[1],
    ]
    try:
        async with _test_client(session_factory) as client:
            resp = await client.patch(f"/api/items/{item_id}", json={"rubric": edited_rubric})
            assert resp.status_code == 200
            assert resp.json()["rubric"][0]["point"] == "Edited wording of the same rubric point."

        async with session_factory() as session:
            item = await session.get(Item, item_id)
            assert item.status == ItemStatus.draft  # editing rubric alone doesn't change status
    finally:
        await _cleanup(session_factory, source_id)


def _graded_json(point_ids_covered: list[str]) -> str:
    return json.dumps(
        {
            "points": [
                {"point_id": pid, "covered": True, "evidence": "..."} for pid in point_ids_covered
            ],
            "misconceptions": [],
            "feedback_md": "Feedback.",
        }
    )


@pytest.mark.asyncio
async def test_start_quiz_fails_when_week_has_no_items() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    async with _test_client(session_factory) as client:
        resp = await client.post("/api/study/quiz", json={"week": 123456, "limit": 10})
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_start_quiz_returns_items_without_gabarito() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    item_ids, source_id = await _make_items_for_week(session_factory, week=7001, count=2)

    try:
        async with _test_client(session_factory) as client:
            resp = await client.post("/api/study/quiz", json={"week": 7001, "limit": 10})
            assert resp.status_code == 200
            body = resp.json()
            assert body["week"] == 7001
            returned_ids = {item["id"] for item in body["items"]}
            assert returned_ids == {str(i) for i in item_ids}
            for item in body["items"]:
                assert "rubric" not in item
                assert "reference_answer" not in item
    finally:
        await _cleanup(session_factory, source_id)
        await _cleanup_quiz_attempts(session_factory, 7001)


@pytest.mark.asyncio
async def test_multiple_quiz_attempts_allowed_for_same_week() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    item_ids, source_id = await _make_items_for_week(session_factory, week=7002, count=1)

    try:
        async with _test_client(session_factory) as client:
            first = await client.post("/api/study/quiz", json={"week": 7002, "limit": 10})
            second = await client.post("/api/study/quiz", json={"week": 7002, "limit": 10})
            assert first.json()["quiz_attempt_id"] != second.json()["quiz_attempt_id"]

            weeks = await client.get("/api/study/weeks")
            week_entry = next(w for w in weeks.json() if w["week"] == 7002)
            assert week_entry["item_count"] == 1
            assert len(week_entry["attempts"]) == 2
            assert {a["status"] for a in week_entry["attempts"]} == {"in_progress"}
    finally:
        await _cleanup(session_factory, source_id)
        await _cleanup_quiz_attempts(session_factory, 7002)


@pytest.mark.asyncio
async def test_quiz_completes_and_scores_once_every_item_is_answered() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    item_ids, source_id = await _make_items_for_week(session_factory, week=7003, count=2)
    fake_llm = FakeLLM([_graded_json(["p1", "p2"]), _graded_json(["p1"])])

    try:
        async with _test_client(session_factory, fake_llm) as client:
            start = await client.post("/api/study/quiz", json={"week": 7003, "limit": 10})
            quiz_attempt_id = start.json()["quiz_attempt_id"]

            first = await client.post(
                "/api/study/answer",
                json={
                    "item_id": str(item_ids[0]),
                    "response_text": "full answer",
                    "quiz_attempt_id": quiz_attempt_id,
                },
            )
            assert first.status_code == 200

            mid_review = await client.get(f"/api/study/quiz/{quiz_attempt_id}")
            assert mid_review.json()["quiz_attempt"]["status"] == "in_progress"
            assert mid_review.json()["quiz_attempt"]["score"] is None
            assert len(mid_review.json()["results"]) == 1
            # `items` always lists the full frozen set, even mid-attempt — a client
            # resuming an in_progress attempt needs this to know what's left to answer.
            assert {i["id"] for i in mid_review.json()["items"]} == {str(i) for i in item_ids}

            second = await client.post(
                "/api/study/answer",
                json={
                    "item_id": str(item_ids[1]),
                    "response_text": "partial answer",
                    "quiz_attempt_id": quiz_attempt_id,
                },
            )
            assert second.status_code == 200

            final = await client.get(f"/api/study/quiz/{quiz_attempt_id}")
            attempt_out = final.json()["quiz_attempt"]
            assert attempt_out["status"] == "completed"
            # item 0: both points covered -> 1.0; item 1: only p1 (weight 1) of 3 -> 1/3.
            assert attempt_out["score"] == pytest.approx((1.0 + 1 / 3) / 2)
            assert len(final.json()["results"]) == 2
    finally:
        await _cleanup(session_factory, source_id)
        await _cleanup_quiz_attempts(session_factory, 7003)


@pytest.mark.asyncio
async def test_answer_rejects_item_not_in_quiz_attempt() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    item_ids_a, source_id_a = await _make_items_for_week(session_factory, week=7004, count=1)
    item_ids_b, source_id_b = await _make_items_for_week(session_factory, week=7005, count=1)

    try:
        async with _test_client(session_factory) as client:
            start = await client.post("/api/study/quiz", json={"week": 7004, "limit": 10})
            quiz_attempt_id = start.json()["quiz_attempt_id"]

            resp = await client.post(
                "/api/study/answer",
                json={
                    "item_id": str(item_ids_b[0]),
                    "response_text": "wrong quiz's item",
                    "quiz_attempt_id": quiz_attempt_id,
                },
            )
            assert resp.status_code == 422
    finally:
        await _cleanup(session_factory, source_id_a)
        await _cleanup(session_factory, source_id_b)
        await _cleanup_quiz_attempts(session_factory, 7004)


@pytest.mark.asyncio
async def test_answer_rejects_once_quiz_attempt_is_completed() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    item_ids, source_id = await _make_items_for_week(session_factory, week=7006, count=1)
    fake_llm = FakeLLM([_graded_json(["p1", "p2"])])

    try:
        async with _test_client(session_factory, fake_llm) as client:
            start = await client.post("/api/study/quiz", json={"week": 7006, "limit": 10})
            quiz_attempt_id = start.json()["quiz_attempt_id"]

            first = await client.post(
                "/api/study/answer",
                json={
                    "item_id": str(item_ids[0]),
                    "response_text": "the answer",
                    "quiz_attempt_id": quiz_attempt_id,
                },
            )
            assert first.status_code == 200

            again = await client.post(
                "/api/study/answer",
                json={
                    "item_id": str(item_ids[0]),
                    "response_text": "a different answer this time",
                    "quiz_attempt_id": quiz_attempt_id,
                },
            )
            assert again.status_code == 409
    finally:
        await _cleanup(session_factory, source_id)
        await _cleanup_quiz_attempts(session_factory, 7006)


@pytest.mark.asyncio
async def test_draft_item_is_invisible_to_the_study_queue_and_the_quiz() -> None:
    """M6's gate: a `draft` item never reaches a student, only `approved`/`edited` do —
    only the review queue's own `PATCH /api/items/{id}` (tested in tests/test_api_items.py)
    is a door into either of those statuses."""
    session_factory = make_session_factory(DbSettings().database_url)
    item_id, source_id = await _make_item(session_factory, status=ItemStatus.draft)
    item_ids, week_source_id = await _make_items_for_week(
        session_factory, week=7007, count=1, status=ItemStatus.draft
    )

    try:
        async with _test_client(session_factory) as client:
            session_resp = await client.post("/api/study/session", json={"limit": 50})
            assert str(item_id) not in {row["id"] for row in session_resp.json()}

            weeks = await client.get("/api/study/weeks")
            assert all(w["week"] != 7007 for w in weeks.json())

            quiz_resp = await client.post("/api/study/quiz", json={"week": 7007, "limit": 10})
            assert quiz_resp.status_code == 404
    finally:
        await _cleanup(session_factory, source_id)
        await _cleanup(session_factory, week_source_id)
        assert item_ids  # keep the created ids referenced for clarity


@pytest.mark.asyncio
async def test_mcq_is_graded_deterministically_with_zero_llm_calls() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    item_id, source_id = await _make_item(
        session_factory,
        item_type=ItemType.mcq,
        prompt="Which mechanism is described as cells that fire together wiring together?",
        reference_answer="Hebbian plasticity",
        rubric=_SINGLE_POINT_RUBRIC,
        choices={"options": ["Hebbian plasticity", "Long-term depression", "Apoptosis"]},
    )
    fake_llm = FakeLLM([])  # any LLM call at all raises inside the fake — the proof

    try:
        async with _test_client(session_factory, fake_llm) as client:
            resp = await client.post(
                "/api/study/answer",
                json={"item_id": str(item_id), "response_text": "Hebbian plasticity"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["score"] == pytest.approx(1.0)
            assert body["rubric_hits"][0]["covered"] is True
            assert fake_llm.calls == []

        async with session_factory() as session:
            attempt = await session.scalar(select(Attempt).where(Attempt.item_id == item_id))
            assert attempt.tokens_used == 0
            assert attempt.grader_model == "deterministic"
    finally:
        await _cleanup(session_factory, source_id)


@pytest.mark.asyncio
async def test_mcq_wrong_option_scores_zero() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    item_id, source_id = await _make_item(
        session_factory,
        item_type=ItemType.mcq,
        reference_answer="Hebbian plasticity",
        rubric=_SINGLE_POINT_RUBRIC,
        choices={"options": ["Hebbian plasticity", "Long-term depression", "Apoptosis"]},
    )
    fake_llm = FakeLLM([])

    try:
        async with _test_client(session_factory, fake_llm) as client:
            resp = await client.post(
                "/api/study/answer",
                json={"item_id": str(item_id), "response_text": "Apoptosis"},
            )
            assert resp.status_code == 200
            assert resp.json()["score"] == pytest.approx(0.0)
            assert fake_llm.calls == []
    finally:
        await _cleanup(session_factory, source_id)


@pytest.mark.asyncio
async def test_cloze_is_graded_deterministically_with_zero_llm_calls() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    item_id, source_id = await _make_item(
        session_factory,
        item_type=ItemType.cloze,
        prompt="_____ is often summarized as cells that fire together wire together.",
        reference_answer="Hebbian plasticity",
        rubric=_SINGLE_POINT_RUBRIC,
    )
    fake_llm = FakeLLM([])

    try:
        async with _test_client(session_factory, fake_llm) as client:
            wrong = await client.post(
                "/api/study/answer",
                json={"item_id": str(item_id), "response_text": "Long-term potentiation"},
            )
            assert wrong.status_code == 200
            assert wrong.json()["score"] == pytest.approx(0.0)

            correct = await client.post(
                "/api/study/answer",
                json={"item_id": str(item_id), "response_text": "hebbian   PLASTICITY"},
            )
            assert correct.status_code == 200
            assert correct.json()["score"] == pytest.approx(1.0)
            assert fake_llm.calls == []
    finally:
        await _cleanup(session_factory, source_id)


@pytest.mark.asyncio
async def test_quiz_queue_includes_choices_only_for_mcq_items() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    mcq_id, mcq_source = await _make_item(
        session_factory,
        item_type=ItemType.mcq,
        reference_answer="Hebbian plasticity",
        rubric=_SINGLE_POINT_RUBRIC,
        choices={"options": ["Hebbian plasticity", "Long-term depression", "Apoptosis"]},
    )
    free_id, free_source = await _make_item(session_factory)

    try:
        async with _test_client(session_factory) as client:
            resp = await client.post("/api/study/session", json={"week": 999, "limit": 50})
            rows = {row["id"]: row for row in resp.json()}
            assert rows[str(mcq_id)]["choices"] is not None
            assert set(rows[str(mcq_id)]["choices"]["options"]) == {
                "Hebbian plasticity",
                "Long-term depression",
                "Apoptosis",
            }
            assert rows[str(free_id)]["choices"] is None
    finally:
        await _cleanup(session_factory, mcq_source)
        await _cleanup(session_factory, free_source)


@pytest.mark.asyncio
async def test_answering_leaves_a_review_state_row_behind() -> None:
    """M9: both grading paths (LLM and M7's deterministic one) must feed the scheduler."""
    session_factory = make_session_factory(DbSettings().database_url)
    owner_id = DbSettings().dev_owner_id
    llm_item_id, llm_source = await _make_item(session_factory)
    mcq_item_id, mcq_source = await _make_item(
        session_factory,
        item_type=ItemType.mcq,
        reference_answer="Hebbian plasticity",
        rubric=_SINGLE_POINT_RUBRIC,
        choices={"options": ["Hebbian plasticity", "Long-term depression", "Apoptosis"]},
    )
    graded_json = json.dumps(
        {
            "points": [
                {"point_id": "p1", "covered": True, "evidence": "..."},
                {"point_id": "p2", "covered": True, "evidence": "..."},
            ],
            "misconceptions": [],
            "feedback_md": "Great answer.",
        }
    )
    fake_llm = FakeLLM([graded_json])

    try:
        async with _test_client(session_factory, fake_llm) as client:
            llm_resp = await client.post(
                "/api/study/answer",
                json={"item_id": str(llm_item_id), "response_text": "a full answer"},
            )
            assert llm_resp.status_code == 200

            mcq_resp = await client.post(
                "/api/study/answer",
                json={"item_id": str(mcq_item_id), "response_text": "Hebbian plasticity"},
            )
            assert mcq_resp.status_code == 200

        async with session_factory() as session:
            for item_id in (llm_item_id, mcq_item_id):
                state = await session.scalar(
                    select(ReviewState).where(
                        ReviewState.user_id == owner_id, ReviewState.item_id == item_id
                    )
                )
                assert state is not None
                assert state.reps == 1
                assert state.last_grade == "good"
                assert state.due_at is not None
    finally:
        await _cleanup(session_factory, llm_source)
        await _cleanup(session_factory, mcq_source)


@pytest.mark.asyncio
async def test_session_due_only_excludes_a_not_yet_due_item() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    owner_id = DbSettings().dev_owner_id
    not_due_id, not_due_source = await _make_item(session_factory, prompt="not due yet")
    never_reviewed_id, never_reviewed_source = await _make_item(
        session_factory, prompt="never reviewed"
    )
    overdue_id, overdue_source = await _make_item(session_factory, prompt="overdue")

    async with session_factory() as session:
        now = datetime.now(UTC)
        session.add_all(
            [
                ReviewState(
                    user_id=owner_id,
                    item_id=not_due_id,
                    stability=5.0,
                    difficulty=5.0,
                    due_at=now + timedelta(days=10),
                    reps=1,
                    lapses=0,
                    last_grade="good",
                    last_reviewed_at=now,
                    fsrs_card={},
                ),
                ReviewState(
                    user_id=owner_id,
                    item_id=overdue_id,
                    stability=5.0,
                    difficulty=5.0,
                    due_at=now - timedelta(days=1),
                    reps=1,
                    lapses=0,
                    last_grade="hard",
                    last_reviewed_at=now - timedelta(days=5),
                    fsrs_card={},
                ),
            ]
        )
        await session.commit()

    try:
        async with _test_client(session_factory) as client:
            resp = await client.post(
                "/api/study/session", json={"week": 999, "limit": 50, "due_only": True}
            )
            assert resp.status_code == 200
            ids = {row["id"] for row in resp.json()}
            assert str(not_due_id) not in ids
            assert str(never_reviewed_id) in ids
            assert str(overdue_id) in ids
    finally:
        await _cleanup(session_factory, not_due_source)
        await _cleanup(session_factory, never_reviewed_source)
        await _cleanup(session_factory, overdue_source)
