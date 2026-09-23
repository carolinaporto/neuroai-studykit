"""FastAPI dependencies shared by routers.

`get_current_user_id` (M12): verifies the request's Clerk session token, finds-or-creates
this app's own `User` row for it, and returns its id — every query that should be scoped
to "the current user" takes this dependency (CLAUDE.md invariant 8).

`require_owner` is separate on purpose: it answers "is this request allowed to see the
locked sections at all" (now: signed in *and* `role == owner`), not "which user's rows to
query." A route can need one, the other, or both.
"""

import uuid

from clerk_backend_api.security.types import AuthStatus
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.core.embeddings import EmbeddingClient, EmbeddingSettings, OpenAIEmbeddingClient
from packages.core.llm import AnthropicLLMClient, LLMClient, LLMSettings
from packages.db.models import User, UserRole

from .auth import verify_request
from .config import settings
from .db import get_session

_llm_settings = LLMSettings()
_embedding_settings = EmbeddingSettings()


async def get_current_user_id(
    request: Request, session: AsyncSession = Depends(get_session)
) -> uuid.UUID:
    state = verify_request(request, settings.clerk_secret_key)
    if state.status != AuthStatus.SIGNED_IN or state.payload is None:
        raise HTTPException(status_code=401, detail="sign-in required")

    clerk_user_id = state.payload.get("sub")
    email = (state.payload.get("email") or "").strip().lower()
    if not clerk_user_id or not email:
        raise HTTPException(status_code=401, detail="invalid session token")
    if email not in settings.allowed_email_set:
        # ARCHITECTURE.md's own framing of ALLOWED_EMAILS: enforced here, before a User
        # row ever exists for this address — Clerk let them sign in, this app doesn't let
        # them in.
        raise HTTPException(status_code=403, detail="this email is not allowed")

    user = await session.scalar(select(User).where(User.clerk_user_id == clerk_user_id))
    if user is None:
        # First login for this Clerk identity: match an existing hand-seeded row by email
        # (e.g. a dev/test fixture) instead of creating a duplicate; otherwise make a new
        # one. Role is always assigned explicitly here — never left to User.role's column
        # default, which would hand out `owner` to every new signup.
        user = await session.scalar(select(User).where(User.email == email))
        if user is None:
            is_owner = email == settings.owner_email.strip().lower()
            role = UserRole.owner if is_owner else UserRole.student
            user = User(email=email, clerk_user_id=clerk_user_id, role=role)
            session.add(user)
        else:
            user.clerk_user_id = clerk_user_id
        await session.commit()

    return user.id


async def require_owner(
    user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Apply to any route in a section `design/synapse`'s `SiteNav` marks locked (Sources,
    Review, Quizzes, Progress, Check-in, Notes & Insights) — never to Overview or Homework,
    which stay open to a signed-out visitor by design."""
    user = await session.get(User, user_id)
    if user is None or user.role != UserRole.owner:
        raise HTTPException(status_code=403, detail="owner access required")


def get_llm_client() -> LLMClient:
    return AnthropicLLMClient(
        api_key=_llm_settings.anthropic_api_key, model=_llm_settings.llm_model_grade
    )


def get_embedding_client() -> EmbeddingClient:
    return OpenAIEmbeddingClient(
        api_key=_embedding_settings.openai_api_key,
        model=_embedding_settings.openai_embedding_model,
    )
