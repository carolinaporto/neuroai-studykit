"""Tests for `GET/POST /api/homework` and `PATCH /api/homework/{id}` — the public portfolio
section. Runs against the real dev Postgres, same assumption as tests/test_api_sources.py.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.api.core.db import get_session
from apps.api.core.deps import require_owner
from apps.api.main import app
from packages.db.models import Homework, User
from packages.db.session import DbSettings, make_session_factory


@asynccontextmanager
async def _test_client(
    session_factory: async_sessionmaker, *, signed_in: bool
) -> AsyncIterator[httpx.AsyncClient]:
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    if signed_in:
        app.dependency_overrides[require_owner] = lambda: None
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(require_owner, None)


async def _ensure_owner(session: AsyncSession, owner_id: uuid.UUID) -> None:
    if await session.get(User, owner_id) is None:
        session.add(User(id=owner_id, email="owner@studykit.local"))
        await session.flush()


async def _cleanup(session_factory: async_sessionmaker, homework_ids: list[uuid.UUID]) -> None:
    async with session_factory() as session:
        for homework_id in homework_ids:
            row = await session.get(Homework, homework_id)
            if row is not None:
                await session.delete(row)
        await session.commit()


@pytest.mark.asyncio
async def test_list_homework_is_public_and_excludes_drafts() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    owner_id = DbSettings().dev_owner_id
    homework_ids: list[uuid.UUID] = []

    async with session_factory() as session:
        await _ensure_owner(session, owner_id)
        published = Homework(
            owner_id=owner_id,
            week=6,
            title="Research Brief — Predictive Coding in Sensory Cortex",
            description="A short literature review.",
            disciplines=["Neuroscience", "Computer Science"],
            code_url="https://github.com/example/repo",
            live_url="https://example.com",
        )
        draft = Homework(
            owner_id=owner_id,
            week=7,
            title="Not ready yet",
            description="Still writing this one.",
            disciplines=["Psychology"],
        )
        session.add_all([published, draft])
        await session.commit()
        published.status = "published"
        await session.commit()
        homework_ids = [published.id, draft.id]

    try:
        # signed_in=False: no require_owner override, since this endpoint must be reachable
        # by a signed-out visitor without one.
        async with _test_client(session_factory, signed_in=False) as client:
            resp = await client.get("/api/homework")

        assert resp.status_code == 200
        titles = {row["title"] for row in resp.json()}
        assert "Research Brief — Predictive Coding in Sensory Cortex" in titles
        assert "Not ready yet" not in titles
    finally:
        await _cleanup(session_factory, homework_ids)


@pytest.mark.asyncio
async def test_create_homework_requires_owner_and_starts_as_draft() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    owner_id = DbSettings().dev_owner_id
    homework_ids: list[uuid.UUID] = []

    async with session_factory() as session:
        await _ensure_owner(session, owner_id)
        await session.commit()

    body = {
        "week": 8,
        "title": "Interactive demo — attention maps",
        "description": "A small interactive site visualizing attention weights.",
        "disciplines": ["Computer Science"],
        "live_url": "https://example.com/attention-demo",
    }

    try:
        async with _test_client(session_factory, signed_in=False) as client:
            anon = await client.post("/api/homework", json=body)
            assert anon.status_code == 401

        async with _test_client(session_factory, signed_in=True) as client:
            resp = await client.post("/api/homework", json=body)
            assert resp.status_code == 200
            created = resp.json()
            assert created["status"] == "draft"
            homework_ids.append(uuid.UUID(created["id"]))

            listing = await client.get("/api/homework")
            titles = {row["title"] for row in listing.json()}
            assert "Interactive demo — attention maps" not in titles
    finally:
        await _cleanup(session_factory, homework_ids)


@pytest.mark.asyncio
async def test_patch_homework_publishes_it() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    owner_id = DbSettings().dev_owner_id
    homework_ids: list[uuid.UUID] = []

    async with session_factory() as session:
        await _ensure_owner(session, owner_id)
        row = Homework(
            owner_id=owner_id,
            week=9,
            title="Draft entry",
            description="Still cooking.",
            disciplines=["Neuroscience"],
        )
        session.add(row)
        await session.commit()
        homework_ids = [row.id]
        homework_id = row.id

    try:
        async with _test_client(session_factory, signed_in=True) as client:
            resp = await client.patch(
                f"/api/homework/{homework_id}", json={"status": "published"}
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "published"

            listing = await client.get("/api/homework")
            titles = {row["title"] for row in listing.json()}
            assert "Draft entry" in titles
    finally:
        await _cleanup(session_factory, homework_ids)


@pytest.mark.asyncio
async def test_create_homework_rejects_unknown_discipline() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    owner_id = DbSettings().dev_owner_id

    async with session_factory() as session:
        await _ensure_owner(session, owner_id)
        await session.commit()

    body = {
        "week": 8,
        "title": "Bad discipline",
        "description": "...",
        "disciplines": ["Astrology"],
    }
    async with _test_client(session_factory, signed_in=True) as client:
        resp = await client.post("/api/homework", json=body)
        assert resp.status_code == 422
