"""`GET /api/auth/session` — M12: reports whether the request carries a valid Clerk
session and this app's own mapped role, so the frontend has one source of truth for both
instead of reading Clerk's client state for "signed in" and asking the backend separately
for "which role." Sign-in/out happen entirely through Clerk's own components on the
frontend now — this router no longer accepts a password (see `apps/api/core/auth.py`).
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.core.db import get_session
from apps.api.core.deps import get_current_user_id
from apps.api.schemas.auth import SessionStatus
from packages.db.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/session", response_model=SessionStatus)
async def session_status(
    request: Request, session: AsyncSession = Depends(get_session)
) -> SessionStatus:
    # Called directly (not via Depends) so a missing/invalid/not-allowed token yields a
    # plain "not signed in" response instead of this endpoint itself 401/403ing — a
    # signed-out visitor checking status is the normal case, not an error.
    try:
        user_id = await get_current_user_id(request, session)
    except HTTPException:
        return SessionStatus(signed_in=False)

    user = await session.get(User, user_id)
    return SessionStatus(signed_in=True, role=user.role if user else None)
