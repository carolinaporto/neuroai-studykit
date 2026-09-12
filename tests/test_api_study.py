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

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.api.core.db import get_session
from apps.api.core.deps import get_llm_client
from apps.api.main import app
from apps.api.services.grading import compute_score
from packages.core.llm import FakeLLM, LLMClient
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
) -> tuple[uuid.UUID, uuid.UUID]:
    """Creates User (if missing) + Source + Chunk + Item rows for one test. Returns
    (item_id, source_id) — deleting the source cascades to chunk/item/attempt."""
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
            type=ItemType.free_recall,
            prompt="Explain what determines whether repeated neural activity leads to a "
            "lasting change in connection strength.",
            reference_answer="A presynaptic neuron repeatedly helping drive a postsynaptic "
            "neuron to fire strengthens their connection; a brief high-frequency burst can "
            "produce this kind of lasting increase in synaptic strength.",
            rubric=RUBRIC,
            difficulty=2,
            bloom=ItemBloom.understand,
            topics=["hebbian-plasticity"],
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
            await session.delete(source)  # cascades to Chunk/Item/Attempt
            await session.commit()


@asynccontextmanager
async def _test_client(
    session_factory: async_sessionmaker, llm: LLMClient | None = None
) -> AsyncIterator[httpx.AsyncClient]:
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    if llm is not None:
        app.dependency_overrides[get_llm_client] = lambda: llm
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_session, None)
        if llm is not None:
            app.dependency_overrides.pop(get_llm_client, None)


@pytest.mark.asyncio
async def test_compute_score_is_deterministic() -> None:
    """Pure function, called repeatedly with the same input — CLAUDE.md invariant 2."""
    covered = {"p1": True, "p2": False}
    scores = [compute_score(RUBRIC, covered) for _ in range(5)]
    assert scores == [1.0 / 3.0] * 5


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
