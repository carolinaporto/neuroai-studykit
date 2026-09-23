"""Tests for `GET/POST /api/notes` and `PATCH /api/notes/{id}` — the locked Notes & Insights
section. Runs against the real dev Postgres, same assumption as tests/test_api_homework.py.
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
from packages.db.models import Note, Source, SourceKind, SourceStatus, User
from packages.db.session import DbSettings, make_session_factory


@asynccontextmanager
async def _test_client(
    session_factory: async_sessionmaker, *, signed_in: bool = True
) -> AsyncIterator[httpx.AsyncClient]:
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    if signed_in:
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


async def _ensure_owner(session: AsyncSession, owner_id: uuid.UUID) -> None:
    if await session.get(User, owner_id) is None:
        session.add(User(id=owner_id, email="owner@studykit.local"))
        await session.flush()


async def _cleanup(session_factory: async_sessionmaker, note_ids: list[uuid.UUID]) -> None:
    async with session_factory() as session:
        for note_id in note_ids:
            row = await session.get(Note, note_id)
            if row is not None:
                await session.delete(row)
        await session.commit()


@pytest.mark.asyncio
async def test_notes_require_owner_session() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    async with _test_client(session_factory, signed_in=False) as client:
        resp = await client.get("/api/notes")
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_note_defaults_to_private() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    owner_id = DbSettings().dev_owner_id
    note_ids: list[uuid.UUID] = []

    async with session_factory() as session:
        await _ensure_owner(session, owner_id)
        await session.commit()

    body = {
        "title": "Synaptic pruning ≈ dropout",
        "body": "Both remove weak connections to improve generalization.",
        "disciplines": ["Neuroscience", "Computer Science"],
        "week": 5,
    }

    try:
        async with _test_client(session_factory) as client:
            resp = await client.post("/api/notes", json=body)
            assert resp.status_code == 200
            created = resp.json()
            assert created["is_public"] is False
            note_ids.append(uuid.UUID(created["id"]))
    finally:
        await _cleanup(session_factory, note_ids)


@pytest.mark.asyncio
async def test_patch_note_can_make_it_public() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    owner_id = DbSettings().dev_owner_id
    note_ids: list[uuid.UUID] = []

    async with session_factory() as session:
        await _ensure_owner(session, owner_id)
        note = Note(
            owner_id=owner_id,
            title="A private thought",
            body="...",
            disciplines=["Psychology"],
        )
        session.add(note)
        await session.commit()
        note_ids = [note.id]
        note_id = note.id

    try:
        async with _test_client(session_factory) as client:
            resp = await client.patch(f"/api/notes/{note_id}", json={"is_public": True})
            assert resp.status_code == 200
            assert resp.json()["is_public"] is True
    finally:
        await _cleanup(session_factory, note_ids)


@pytest.mark.asyncio
async def test_create_note_rejects_unknown_source_id() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    owner_id = DbSettings().dev_owner_id

    async with session_factory() as session:
        await _ensure_owner(session, owner_id)
        await session.commit()

    body = {
        "title": "Linked to a source that doesn't exist",
        "body": "...",
        "disciplines": ["Neuroscience"],
        "source_id": str(uuid.uuid4()),
    }
    async with _test_client(session_factory) as client:
        resp = await client.post("/api/notes", json=body)
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_note_accepts_a_real_source_id() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    owner_id = DbSettings().dev_owner_id
    note_ids: list[uuid.UUID] = []
    source_id: uuid.UUID | None = None

    async with session_factory() as session:
        await _ensure_owner(session, owner_id)
        source = Source(
            owner_id=owner_id,
            week=5,
            title="Lecture 05 slides",
            kind=SourceKind.slides,
            storage_uri="test://slides",
            sha256=uuid.uuid4().hex + uuid.uuid4().hex,
            status=SourceStatus.ingested,
        )
        session.add(source)
        await session.commit()
        source_id = source.id

    body = {
        "title": "Linked to a real source",
        "body": "...",
        "disciplines": ["Neuroscience"],
        "source_id": str(source_id),
    }
    try:
        async with _test_client(session_factory) as client:
            resp = await client.post("/api/notes", json=body)
            assert resp.status_code == 200
            note_ids.append(uuid.UUID(resp.json()["id"]))
    finally:
        await _cleanup(session_factory, note_ids)
        async with session_factory() as session:
            source = await session.get(Source, source_id)
            if source is not None:
                await session.delete(source)
            await session.commit()


@pytest.mark.asyncio
async def test_create_note_rejects_unknown_discipline() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    owner_id = DbSettings().dev_owner_id

    async with session_factory() as session:
        await _ensure_owner(session, owner_id)
        await session.commit()

    body = {"title": "Bad discipline", "body": "...", "disciplines": ["Astrology"]}
    async with _test_client(session_factory) as client:
        resp = await client.post("/api/notes", json=body)
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_note_accepts_url_only_no_body() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    owner_id = DbSettings().dev_owner_id
    note_ids: list[uuid.UUID] = []

    async with session_factory() as session:
        await _ensure_owner(session, owner_id)
        await session.commit()

    body = {
        "title": "Full write-up lives in Drive",
        "url": "https://docs.google.com/document/d/abc123",
        "disciplines": ["Psychology"],
    }
    try:
        async with _test_client(session_factory) as client:
            resp = await client.post("/api/notes", json=body)
            assert resp.status_code == 200
            created = resp.json()
            assert created["url"] == body["url"]
            assert created["body"] is None
            note_ids.append(uuid.UUID(created["id"]))
    finally:
        await _cleanup(session_factory, note_ids)


@pytest.mark.asyncio
async def test_create_note_rejects_neither_body_nor_url() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    owner_id = DbSettings().dev_owner_id

    async with session_factory() as session:
        await _ensure_owner(session, owner_id)
        await session.commit()

    body = {"title": "Empty note", "disciplines": ["Neuroscience"]}
    async with _test_client(session_factory) as client:
        resp = await client.post("/api/notes", json=body)
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_note_rejects_clearing_body_and_url_together() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    owner_id = DbSettings().dev_owner_id
    note_ids: list[uuid.UUID] = []

    async with session_factory() as session:
        await _ensure_owner(session, owner_id)
        note = Note(
            owner_id=owner_id,
            title="Has only a body",
            body="Some text.",
            url=None,
            disciplines=["Psychology"],
        )
        session.add(note)
        await session.commit()
        note_ids = [note.id]
        note_id = note.id

    try:
        async with _test_client(session_factory) as client:
            resp = await client.patch(f"/api/notes/{note_id}", json={"body": None})
            assert resp.status_code == 422
    finally:
        await _cleanup(session_factory, note_ids)


@pytest.mark.asyncio
async def test_patch_note_404s_on_a_note_owned_by_someone_else() -> None:
    """Security fix: patch_note() used to fetch by note_id alone, with no owner_id check —
    any owner-role account could edit or flip is_public on another user's note by id."""
    session_factory = make_session_factory(DbSettings().database_url)
    other_owner_id = uuid.uuid4()
    note_ids: list[uuid.UUID] = []

    async with session_factory() as session:
        session.add(User(id=other_owner_id, email="someone-else@studykit.local"))
        await session.flush()
        note = Note(
            owner_id=other_owner_id,
            title="Not yours",
            body="private thought",
            disciplines=["Psychology"],
        )
        session.add(note)
        await session.commit()
        note_ids = [note.id]
        note_id = note.id

    try:
        async with _test_client(session_factory) as client:
            resp = await client.patch(f"/api/notes/{note_id}", json={"is_public": True})
            assert resp.status_code == 404
    finally:
        await _cleanup(session_factory, note_ids)
        async with session_factory() as session:
            other_user = await session.get(User, other_owner_id)
            if other_user is not None:
                await session.delete(other_user)
            await session.commit()
