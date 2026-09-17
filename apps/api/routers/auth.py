"""`POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/session` — the whole
sign-in surface for the single-owner cookie session in `apps/api/core/auth.py`.
"""

from fastapi import APIRouter, HTTPException, Request, Response

from apps.api.core.auth import (
    SESSION_COOKIE_NAME,
    SESSION_TTL_SECONDS,
    check_password,
    create_session_token,
    verify_session_token,
)
from apps.api.core.config import settings
from apps.api.schemas.auth import LoginRequest, SessionStatus

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=settings.env == "production",
        path="/",
    )


@router.post("/login", response_model=SessionStatus)
async def login(body: LoginRequest, response: Response) -> SessionStatus:
    if not settings.owner_password or not settings.session_secret:
        raise HTTPException(
            status_code=503, detail="OWNER_PASSWORD/SESSION_SECRET not configured"
        )
    if not check_password(body.password, settings.owner_password):
        raise HTTPException(status_code=401, detail="wrong password")

    _set_session_cookie(response, create_session_token(settings.session_secret))
    return SessionStatus(signed_in=True)


@router.post("/logout", response_model=SessionStatus)
async def logout(response: Response) -> SessionStatus:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return SessionStatus(signed_in=False)


@router.get("/session", response_model=SessionStatus)
async def session_status(request: Request) -> SessionStatus:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    signed_in = token is not None and verify_session_token(token, settings.session_secret)
    return SessionStatus(signed_in=signed_in)
