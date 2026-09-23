"""FastAPI dependencies shared by routers.

`get_current_user_id` is the multiuser seam (CLAUDE.md invariant 8): every query that
should be scoped to "the current user" takes this dependency, even though it always
resolves to the same fixed owner until M12 adds real accounts.

`require_owner` is separate on purpose: it answers "is this request allowed to see the
locked sections at all" (the single-owner cookie session in `apps/api/core/auth.py`), not
"which user's rows to query." A route can need one, the other, or both.
"""

import uuid

from fastapi import HTTPException, Request

from packages.core.embeddings import EmbeddingClient, EmbeddingSettings, OpenAIEmbeddingClient
from packages.core.llm import AnthropicLLMClient, LLMClient, LLMSettings

from .auth import SESSION_COOKIE_NAME, verify_session_token
from .config import settings

_llm_settings = LLMSettings()
_embedding_settings = EmbeddingSettings()


def get_current_user_id() -> uuid.UUID:
    return settings.dev_owner_id


def require_owner(request: Request) -> None:
    """Raises 401 unless the request carries a valid owner session cookie. Apply to any
    route in a section `design/synapse`'s `SiteNav` marks locked (Sources, Quizzes,
    Notes & Insights) — never to Overview or Homework, which stay open to a signed-out
    visitor by design."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token is None or not verify_session_token(token, settings.session_secret):
        raise HTTPException(status_code=401, detail="sign-in required")


def get_llm_client() -> LLMClient:
    return AnthropicLLMClient(
        api_key=_llm_settings.anthropic_api_key, model=_llm_settings.llm_model_grade
    )


def get_embedding_client() -> EmbeddingClient:
    return OpenAIEmbeddingClient(
        api_key=_embedding_settings.openai_api_key,
        model=_embedding_settings.openai_embedding_model,
    )
