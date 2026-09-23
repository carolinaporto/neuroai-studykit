"""Tests for `GET /api/items/review` (M6's review queue) and its interaction with
`PATCH /api/items/{id}` (M4, unchanged by M6). Runs against the real dev Postgres, same
assumption as tests/test_api_sources.py; each test creates and cleans up its own rows.

Uses synthetic week numbers with no `topics.yaml` unit (8101+), not a real syllabus week —
a real week (e.g. 3) can carry actual uploaded content in the dev database, and asserting an
exact item set against it is exactly what broke tests/test_api_sources.py's week-3 test.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.api.core.db import get_session
from apps.api.core.deps import get_current_user_id, require_owner
from apps.api.main import app
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


@asynccontextmanager
async def _test_client(session_factory: async_sessionmaker) -> AsyncIterator[httpx.AsyncClient]:
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[require_owner] = lambda: None
    app.dependency_overrides[get_current_user_id] = lambda: DbSettings().dev_owner_id
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(require_owner, None)
        app.dependency_overrides.pop(get_current_user_id, None)


async def _make_item(
    session_factory: async_sessionmaker,
    *,
    week: int,
    status: ItemStatus,
    prompt: str = "Explain Hebbian plasticity from memory.",
    item_type: ItemType = ItemType.free_recall,
    rubric: list[dict] | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Returns (item_id, source_id) — deleting the source cascades to chunk/item."""
    settings = DbSettings()
    async with session_factory() as session:
        if await session.get(User, settings.dev_owner_id) is None:
            session.add(User(id=settings.dev_owner_id, email="owner@studykit.local"))
            await session.flush()

        source = Source(
            owner_id=settings.dev_owner_id,
            week=week,
            title="m6-test-source",
            kind=SourceKind.lecture_pdf,
            storage_uri="test://m6",
            sha256=uuid.uuid4().hex + uuid.uuid4().hex,
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
            prompt=prompt,
            reference_answer="A reference answer.",
            rubric=rubric if rubric is not None else RUBRIC,
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


async def _cleanup(session_factory: async_sessionmaker, source_ids: list[uuid.UUID]) -> None:
    async with session_factory() as session:
        for source_id in source_ids:
            source = await session.get(Source, source_id)
            if source is not None:
                await session.delete(source)  # cascades to Chunk/Item
        await session.commit()


@pytest.mark.asyncio
async def test_review_queue_groups_by_week_and_embeds_the_anchor_chunk() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    item_id, source_id = await _make_item(session_factory, week=8101, status=ItemStatus.draft)

    try:
        async with _test_client(session_factory) as client:
            resp = await client.get("/api/items/review")
            assert resp.status_code == 200
            week = next(w for w in resp.json() if w["week"] == 8101)
            assert week["title"] is None  # no topics.yaml unit for a synthetic week
            assert [i["id"] for i in week["items"]] == [str(item_id)]
            item = week["items"][0]
            assert item["status"] == "draft"
            assert item["chunk"]["text"] == CHUNK_TEXT
            assert item["chunk"]["locator"] == {"page": 7}
    finally:
        await _cleanup(session_factory, [source_id])


@pytest.mark.asyncio
async def test_review_queue_excludes_approved_and_retired_items() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    draft_id, draft_source = await _make_item(
        session_factory, week=8102, status=ItemStatus.draft, prompt="draft item"
    )
    approved_id, approved_source = await _make_item(
        session_factory, week=8102, status=ItemStatus.approved, prompt="approved item"
    )
    retired_id, retired_source = await _make_item(
        session_factory, week=8102, status=ItemStatus.retired, prompt="retired item"
    )

    try:
        async with _test_client(session_factory) as client:
            resp = await client.get("/api/items/review")
            week = next(w for w in resp.json() if w["week"] == 8102)
            item_ids = {i["id"] for i in week["items"]}
            assert item_ids == {str(draft_id)}
            assert str(approved_id) not in item_ids
            assert str(retired_id) not in item_ids
    finally:
        await _cleanup(session_factory, [draft_source, approved_source, retired_source])


@pytest.mark.asyncio
async def test_review_queue_omits_a_week_with_no_drafts() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    item_id, source_id = await _make_item(session_factory, week=8103, status=ItemStatus.approved)

    try:
        async with _test_client(session_factory) as client:
            resp = await client.get("/api/items/review")
            assert all(w["week"] != 8103 for w in resp.json())
    finally:
        await _cleanup(session_factory, [source_id])


@pytest.mark.asyncio
async def test_item_leaves_the_review_queue_once_approved_or_retired() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    approve_id, approve_source = await _make_item(
        session_factory, week=8104, status=ItemStatus.draft, prompt="to approve"
    )
    retire_id, retire_source = await _make_item(
        session_factory, week=8104, status=ItemStatus.draft, prompt="to retire"
    )

    try:
        async with _test_client(session_factory) as client:
            before = await client.get("/api/items/review")
            week_before = next(w for w in before.json() if w["week"] == 8104)
            assert {i["id"] for i in week_before["items"]} == {str(approve_id), str(retire_id)}

            approve_resp = await client.patch(
                f"/api/items/{approve_id}", json={"status": "approved"}
            )
            assert approve_resp.status_code == 200
            retire_resp = await client.patch(
                f"/api/items/{retire_id}", json={"status": "retired"}
            )
            assert retire_resp.status_code == 200

            after = await client.get("/api/items/review")
            assert all(w["week"] != 8104 for w in after.json())
    finally:
        await _cleanup(session_factory, [approve_source, retire_source])


@pytest.mark.asyncio
async def test_patch_item_404s_on_an_item_owned_by_someone_else() -> None:
    """Security fix: patch_item() used to fetch by item_id alone, with no ownership check
    at all — any owner-role account could edit/approve/retire another user's review-queue
    item by id. source.owner_id must now match the authenticated user (dev_owner_id, per
    _test_client's override) for the PATCH to succeed."""
    session_factory = make_session_factory(DbSettings().database_url)
    other_owner_id = uuid.uuid4()

    async with session_factory() as session:
        session.add(User(id=other_owner_id, email="someone-else@studykit.local"))
        await session.flush()
        source = Source(
            owner_id=other_owner_id,
            week=8105,
            title="not-yours-source",
            kind=SourceKind.lecture_pdf,
            storage_uri="test://m6",
            sha256=uuid.uuid4().hex + uuid.uuid4().hex,
            status=SourceStatus.ingested,
        )
        session.add(source)
        await session.flush()
        chunk = Chunk(
            source_id=source.id, ordinal=0, text=CHUNK_TEXT, locators=[{"page": 7}],
            token_count=40,
        )
        session.add(chunk)
        await session.flush()
        item = Item(
            source_id=source.id,
            chunk_ids=[chunk.id],
            type=ItemType.free_recall,
            prompt="not yours",
            reference_answer="ref",
            rubric=RUBRIC,
            difficulty=2,
            bloom=ItemBloom.understand,
            topics=[],
            status=ItemStatus.draft,
            gen_model="test",
            gen_prompt_version="test",
        )
        session.add(item)
        await session.commit()
        item_id, source_id = item.id, source.id

    try:
        async with _test_client(session_factory) as client:
            resp = await client.patch(f"/api/items/{item_id}", json={"status": "approved"})
            assert resp.status_code == 404
    finally:
        await _cleanup(session_factory, [source_id])
        async with session_factory() as session:
            other_user = await session.get(User, other_owner_id)
            if other_user is not None:
                await session.delete(other_user)
            await session.commit()


@pytest.mark.asyncio
async def test_rubric_edit_bound_is_type_aware() -> None:
    """M7: `_validate_rubric_edit` must apply cloze/mcq's exactly-1-point rule, not the
    free_recall/term_def 2-5 rule, to whichever item is being edited."""
    session_factory = make_session_factory(DbSettings().database_url)
    cloze_id, cloze_source = await _make_item(
        session_factory,
        week=8105,
        status=ItemStatus.draft,
        item_type=ItemType.cloze,
        prompt="_____ is often summarized as cells that fire together wire together.",
        rubric=[RUBRIC[0]],
    )
    free_recall_id, free_recall_source = await _make_item(
        session_factory, week=8105, status=ItemStatus.draft
    )

    try:
        async with _test_client(session_factory) as client:
            # A cloze item's 1-point rubric can be edited (still 1 point) without tripping
            # the old flat "needs 2-5" bound.
            cloze_resp = await client.patch(
                f"/api/items/{cloze_id}",
                json={"rubric": [{**RUBRIC[0], "point": "Edited wording."}]},
            )
            assert cloze_resp.status_code == 200

            # A free_recall item still can't be shrunk to 1 point.
            shrink_resp = await client.patch(
                f"/api/items/{free_recall_id}", json={"rubric": [RUBRIC[0]]}
            )
            assert shrink_resp.status_code == 422
    finally:
        await _cleanup(session_factory, [cloze_source, free_recall_source])
