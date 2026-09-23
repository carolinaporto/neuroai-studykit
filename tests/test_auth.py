"""Tests for M12's real auth: `apps/api/core/deps.py`'s `get_current_user_id`/
`require_owner`, and `GET /api/auth/session`. Runs against the real dev Postgres, same
assumption as the other `test_api_*` files.

Never talks to Clerk for real (CLAUDE.md invariant 5's spirit, extended to every external
provider this project uses — Anthropic, OpenAI, now Clerk): `verify_request`
(`apps/api/core/auth.py`) is the one function that would, so every test here monkeypatches
it with a fake `RequestState` instead. It's a monkeypatch rather than an injected protocol
(the way `FakeLLM`/`FakeEmbeddingClient` work) because Clerk's SDK is a plain module
function this app didn't define an interface for — the role is the same: nothing here ever
reaches Clerk's real API.

Deliberately does **not** override `require_owner`/`get_current_user_id` the way every
other test file does — this file's whole job is exercising the real versions of both.
"""

import uuid

import httpx
import pytest
from clerk_backend_api.security.types import AuthStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

import apps.api.core.deps as deps
from apps.api.core.config import settings as api_settings
from apps.api.core.db import get_session
from apps.api.main import app
from packages.db.models import User, UserRole
from packages.db.session import DbSettings, make_session_factory


class _FakeRequestState:
    def __init__(self, status: AuthStatus, payload: dict | None = None) -> None:
        self.status = status
        self.payload = payload


def _signed_in(clerk_user_id: str, email: str) -> _FakeRequestState:
    return _FakeRequestState(AuthStatus.SIGNED_IN, {"sub": clerk_user_id, "email": email})


def _signed_out() -> _FakeRequestState:
    return _FakeRequestState(AuthStatus.SIGNED_OUT, None)


async def _client(
    session_factory: async_sessionmaker, monkeypatch: pytest.MonkeyPatch, state: _FakeRequestState
) -> httpx.AsyncClient:
    monkeypatch.setattr(deps, "verify_request", lambda request, secret_key: state)

    async def override_get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _cleanup_by_email(session_factory: async_sessionmaker, *emails: str) -> None:
    async with session_factory() as session:
        for email in emails:
            user = await session.scalar(select(User).where(User.email == email))
            if user is not None:
                await session.delete(user)
        await session.commit()


@pytest.fixture(autouse=True)
def _reset_dependency_overrides():
    yield
    app.dependency_overrides.pop(get_session, None)


@pytest.mark.asyncio
async def test_session_reports_signed_out_with_no_token(monkeypatch) -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    async with await _client(session_factory, monkeypatch, _signed_out()) as client:
        resp = await client.get("/api/auth/session")
        assert resp.status_code == 200
        assert resp.json() == {"signed_in": False, "role": None}


@pytest.mark.asyncio
async def test_session_rejects_an_email_not_on_the_allowlist(monkeypatch) -> None:
    monkeypatch.setattr(api_settings, "allowed_emails", "allowed@studykit.test")
    session_factory = make_session_factory(DbSettings().database_url)
    state = _signed_in("clerk_not_allowed", "not-allowed@studykit.test")

    async with await _client(session_factory, monkeypatch, state) as client:
        resp = await client.get("/api/auth/session")
        assert resp.json() == {"signed_in": False, "role": None}

    async with session_factory() as session:
        assert await session.scalar(
            select(User).where(User.email == "not-allowed@studykit.test")
        ) is None


@pytest.mark.asyncio
async def test_a_new_allowed_email_becomes_a_student_by_default(monkeypatch) -> None:
    email = "new-student@studykit.test"
    monkeypatch.setattr(api_settings, "allowed_emails", email)
    monkeypatch.setattr(api_settings, "owner_email", "someone-else@studykit.test")
    session_factory = make_session_factory(DbSettings().database_url)

    try:
        async with await _client(
            session_factory, monkeypatch, _signed_in("clerk_new_student", email)
        ) as client:
            resp = await client.get("/api/auth/session")
            assert resp.json() == {"signed_in": True, "role": "student"}

        async with session_factory() as session:
            user = await session.scalar(select(User).where(User.email == email))
            assert user is not None
            assert user.role == UserRole.student
            assert user.clerk_user_id == "clerk_new_student"
    finally:
        await _cleanup_by_email(session_factory, email)


@pytest.mark.asyncio
async def test_the_owner_email_gets_owner_role(monkeypatch) -> None:
    email = "owner@studykit.test"
    monkeypatch.setattr(api_settings, "allowed_emails", email)
    monkeypatch.setattr(api_settings, "owner_email", email)
    session_factory = make_session_factory(DbSettings().database_url)

    try:
        async with await _client(
            session_factory, monkeypatch, _signed_in("clerk_owner", email)
        ) as client:
            resp = await client.get("/api/auth/session")
            assert resp.json() == {"signed_in": True, "role": "owner"}
    finally:
        await _cleanup_by_email(session_factory, email)


@pytest.mark.asyncio
async def test_a_second_login_reuses_the_same_user_by_clerk_id(monkeypatch) -> None:
    email = "repeat@studykit.test"
    monkeypatch.setattr(api_settings, "allowed_emails", email)
    monkeypatch.setattr(api_settings, "owner_email", "")
    session_factory = make_session_factory(DbSettings().database_url)
    state = _signed_in("clerk_repeat", email)

    try:
        async with await _client(session_factory, monkeypatch, state) as client:
            await client.get("/api/auth/session")
        async with await _client(session_factory, monkeypatch, state) as client:
            await client.get("/api/auth/session")

        async with session_factory() as session:
            users = (
                await session.scalars(select(User).where(User.email == email))
            ).all()
            assert len(users) == 1
    finally:
        await _cleanup_by_email(session_factory, email)


@pytest.mark.asyncio
async def test_first_login_matches_an_existing_hand_seeded_row_by_email(monkeypatch) -> None:
    """A dev/test fixture row created by _ensure_owner (packages/ingest/cli.py) has no
    clerk_user_id yet. The first real login with that same email must adopt that row —
    backfilling clerk_user_id — not create a duplicate."""
    email = "hand-seeded@studykit.test"
    monkeypatch.setattr(api_settings, "allowed_emails", email)
    monkeypatch.setattr(api_settings, "owner_email", "")
    session_factory = make_session_factory(DbSettings().database_url)

    async with session_factory() as session:
        seeded = User(id=uuid.uuid4(), email=email, role=UserRole.owner)
        session.add(seeded)
        await session.commit()
        seeded_id = seeded.id

    try:
        async with await _client(
            session_factory, monkeypatch, _signed_in("clerk_adopts_seeded", email)
        ) as client:
            await client.get("/api/auth/session")

        async with session_factory() as session:
            users = (
                await session.scalars(select(User).where(User.email == email))
            ).all()
            assert len(users) == 1
            assert users[0].id == seeded_id
            assert users[0].clerk_user_id == "clerk_adopts_seeded"
            assert users[0].role == UserRole.owner  # unchanged — login doesn't reassign it
    finally:
        await _cleanup_by_email(session_factory, email)


@pytest.mark.asyncio
async def test_require_owner_blocks_a_student_but_allows_an_owner(monkeypatch) -> None:
    student_email = "gate-student@studykit.test"
    owner_email = "gate-owner@studykit.test"
    session_factory = make_session_factory(DbSettings().database_url)

    try:
        monkeypatch.setattr(api_settings, "allowed_emails", f"{student_email},{owner_email}")
        monkeypatch.setattr(api_settings, "owner_email", owner_email)

        async with await _client(
            session_factory, monkeypatch, _signed_in("clerk_gate_student", student_email)
        ) as client:
            resp = await client.get("/api/sources")
            assert resp.status_code == 403

        async with await _client(
            session_factory, monkeypatch, _signed_in("clerk_gate_owner", owner_email)
        ) as client:
            resp = await client.get("/api/sources")
            assert resp.status_code == 200
    finally:
        await _cleanup_by_email(session_factory, student_email, owner_email)


@pytest.mark.asyncio
async def test_sources_requires_a_signed_in_session(monkeypatch) -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    async with await _client(session_factory, monkeypatch, _signed_out()) as client:
        resp = await client.get("/api/sources")
        assert resp.status_code == 401
