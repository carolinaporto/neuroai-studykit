"""FastAPI dependencies shared by routers.

`get_current_user_id` is the multiuser seam (CLAUDE.md invariant 8): every query that
should be scoped to "the current user" takes this dependency, even though it always
resolves to the same fixed owner until M12 adds auth.
"""

import uuid

from packages.core.llm import AnthropicLLMClient, LLMClient, LLMSettings

from .config import settings

_llm_settings = LLMSettings()


def get_current_user_id() -> uuid.UUID:
    return settings.dev_owner_id


def get_llm_client() -> LLMClient:
    return AnthropicLLMClient(
        api_key=_llm_settings.anthropic_api_key, model=_llm_settings.llm_model_grade
    )
