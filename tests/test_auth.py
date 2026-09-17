"""Tests for the single-owner cookie session (apps/api/core/auth.py) and the
/api/auth/{login,logout,session} endpoints, plus require_owner gating GET /api/sources.
"""

import time

import httpx
import pytest

from apps.api.core.auth import (
    _signature,
    check_password,
    create_session_token,
    verify_session_token,
)
from apps.api.core.config import settings as api_settings
from apps.api.main import app

SECRET = "test-session-secret"


def test_verify_session_token_accepts_a_freshly_created_token() -> None:
    token = create_session_token(SECRET)
    assert verify_session_token(token, SECRET) is True


def test_verify_session_token_rejects_wrong_secret() -> None:
    token = create_session_token(SECRET)
    assert verify_session_token(token, "a-different-secret") is False


def test_verify_session_token_rejects_tampered_signature() -> None:
    token = create_session_token(SECRET)
    issued_at, _, signature = token.partition(".")
    tampered = f"{issued_at}.{signature[:-1]}f"
    assert verify_session_token(tampered, SECRET) is False


def test_verify_session_token_rejects_expired_token() -> None:
    past = str(int(time.time()) - 1000)
    stale = f"{past}.{_signature(past, SECRET)}"
    assert verify_session_token(stale, SECRET, ttl_seconds=100) is False


def test_verify_session_token_rejects_malformed_token() -> None:
    assert verify_session_token("not-a-real-token", SECRET) is False
    assert verify_session_token("", SECRET) is False


def test_check_password_rejects_when_expected_is_unconfigured() -> None:
    assert check_password("anything", "") is False


def test_check_password_matches_only_the_exact_password() -> None:
    assert check_password("correct-horse", "correct-horse") is True
    assert check_password("wrong", "correct-horse") is False


@pytest.mark.asyncio
async def test_login_rejects_when_unconfigured(monkeypatch) -> None:
    monkeypatch.setattr(api_settings, "owner_password", "")
    monkeypatch.setattr(api_settings, "session_secret", "")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/auth/login", json={"password": "whatever"})
        assert resp.status_code == 503


@pytest.mark.asyncio
async def test_login_wrong_password_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(api_settings, "owner_password", "correct-horse")
    monkeypatch.setattr(api_settings, "session_secret", SECRET)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/auth/login", json={"password": "wrong"})
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_logout_and_session_status_round_trip(monkeypatch) -> None:
    monkeypatch.setattr(api_settings, "owner_password", "correct-horse")
    monkeypatch.setattr(api_settings, "session_secret", SECRET)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        before = await client.get("/api/auth/session")
        assert before.json() == {"signed_in": False}

        login = await client.post("/api/auth/login", json={"password": "correct-horse"})
        assert login.status_code == 200
        assert login.json() == {"signed_in": True}
        assert "studykit_session" in login.cookies

        after_login = await client.get("/api/auth/session")
        assert after_login.json() == {"signed_in": True}

        logout = await client.post("/api/auth/logout")
        assert logout.json() == {"signed_in": False}

        after_logout = await client.get("/api/auth/session")
        assert after_logout.json() == {"signed_in": False}


@pytest.mark.asyncio
async def test_sources_requires_owner_session(monkeypatch) -> None:
    monkeypatch.setattr(api_settings, "owner_password", "correct-horse")
    monkeypatch.setattr(api_settings, "session_secret", SECRET)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        anon = await client.get("/api/sources")
        assert anon.status_code == 401

        await client.post("/api/auth/login", json={"password": "correct-horse"})
        signed_in = await client.get("/api/sources")
        assert signed_in.status_code == 200
