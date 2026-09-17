"""Tests for `GET /api/sources` — groups ingested Sources by week for Synapse's `WeekHeader`
+ `SourceItem`. Runs against the real dev Postgres, same assumption as
tests/test_api_study.py (`docker compose up` must be running); each test creates and cleans
up its own rows.
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
from packages.db.models import Source, SourceKind, SourceStatus, User
from packages.db.session import DbSettings, make_session_factory


@asynccontextmanager
async def _test_client(session_factory: async_sessionmaker) -> AsyncIterator[httpx.AsyncClient]:
    """Overrides `require_owner` too: this file tests the sources-grouping logic, not auth
    (that's tests/test_auth.py's job) — see test_sources_requires_owner_session there for the
    401 behavior itself."""

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


async def _ensure_owner(session: AsyncSession, owner_id: uuid.UUID) -> None:
    if await session.get(User, owner_id) is None:
        session.add(User(id=owner_id, email="owner@studykit.local"))
        await session.flush()


async def _cleanup(session_factory: async_sessionmaker, source_ids: list[uuid.UUID]) -> None:
    async with session_factory() as session:
        for source_id in source_ids:
            source = await session.get(Source, source_id)
            if source is not None:
                await session.delete(source)
        await session.commit()


@pytest.mark.asyncio
async def test_list_sources_groups_by_week_with_title_from_topics_yaml() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    owner_id = DbSettings().dev_owner_id
    source_ids: list[uuid.UUID] = []

    async with session_factory() as session:
        await _ensure_owner(session, owner_id)
        slides = Source(
            owner_id=owner_id,
            week=3,
            title="Lecture 05 — Hebbian Learning slides",
            kind=SourceKind.slides,
            storage_uri="test://slides",
            sha256=uuid.uuid4().hex + uuid.uuid4().hex,
            page_count=38,
            status=SourceStatus.ingested,
        )
        reading = Source(
            owner_id=owner_id,
            week=3,
            title="Hebb (1949) — The first stage of perception",
            kind=SourceKind.paper,
            storage_uri="test://reading",
            sha256=uuid.uuid4().hex + uuid.uuid4().hex,
            page_count=14,
            status=SourceStatus.ingested,
        )
        session.add_all([slides, reading])
        await session.commit()
        source_ids = [slides.id, reading.id]

    try:
        async with _test_client(session_factory) as client:
            resp = await client.get("/api/sources")
            assert resp.status_code == 200
            body = resp.json()
            week3 = next(w for w in body if w["week"] == 3)
            assert week3["title"] == "Learning, development, and the growth of intelligence"
            titles = {s["title"] for s in week3["sources"]}
            assert titles == {
                "Lecture 05 — Hebbian Learning slides",
                "Hebb (1949) — The first stage of perception",
            }
            slides_row = next(s for s in week3["sources"] if s["kind"] == "slides")
            assert slides_row["page_count"] == 38
    finally:
        await _cleanup(session_factory, source_ids)


@pytest.mark.asyncio
async def test_list_sources_excludes_pending_and_weekless_rows() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    owner_id = DbSettings().dev_owner_id
    source_ids: list[uuid.UUID] = []

    async with session_factory() as session:
        await _ensure_owner(session, owner_id)
        pending = Source(
            owner_id=owner_id,
            week=5,
            title="not yet processed",
            kind=SourceKind.lecture_pdf,
            storage_uri="test://pending",
            sha256=uuid.uuid4().hex + uuid.uuid4().hex,
            status=SourceStatus.pending,
        )
        weekless = Source(
            owner_id=owner_id,
            week=None,
            title="calibration-style fixture",
            kind=SourceKind.slides,
            storage_uri="test://weekless",
            sha256=uuid.uuid4().hex + uuid.uuid4().hex,
            status=SourceStatus.ingested,
        )
        session.add_all([pending, weekless])
        await session.commit()
        source_ids = [pending.id, weekless.id]

    try:
        async with _test_client(session_factory) as client:
            resp = await client.get("/api/sources")
            assert resp.status_code == 200
            all_titles = {s["title"] for week in resp.json() for s in week["sources"]}
            assert "not yet processed" not in all_titles
            assert "calibration-style fixture" not in all_titles
    finally:
        await _cleanup(session_factory, source_ids)
