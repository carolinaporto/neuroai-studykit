"""The `LLMClient` protocol (CLAUDE.md invariant 5): every call to an LLM anywhere in this
codebase goes through this interface, so tests can inject `FakeLLM` and never touch the
Anthropic API. `AnthropicLLMClient` is the only implementation that does.
"""

from typing import Protocol

from pydantic_settings import BaseSettings, SettingsConfigDict

# Shared with apps/api/services/budget.py: the daily token budget's worst-case estimate for
# one call is (prompt tokens) + MAX_OUTPUT_TOKENS, so the two must agree with what
# AnthropicLLMClient actually asks the API for.
MAX_OUTPUT_TOKENS = 4096


class LLMClient(Protocol):
    """A chat completion that is expected to return JSON as plain text.

    Callers own prompt construction and JSON parsing/validation; this protocol's only job
    is "send these two strings, get text back" so it can be swapped for a fake in tests.
    """

    model_name: str

    async def complete_json(self, *, system: str, user: str) -> str: ...


class LLMSettings(BaseSettings):
    """Reads the `.env.example`-defined LLM vars directly, mirroring
    `packages/db/session.py`'s `DbSettings`: `packages/ingest` cannot import
    `apps.api.core.config` (invariant 4), so it needs its own settings model.

    Two separate model vars, not one: generation (this milestone) and grading (M4) are
    different jobs and will likely want different models/cost tradeoffs, per `.env.example`.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    llm_model_generate: str = "claude-sonnet-5"
    llm_model_grade: str = "claude-sonnet-5"


class AnthropicLLMClient:
    """Real `LLMClient` backed by the Anthropic Messages API."""

    def __init__(self, api_key: str, model: str) -> None:
        from anthropic import AsyncAnthropic

        self.model_name = model
        self._client = AsyncAnthropic(api_key=api_key)

    async def complete_json(self, *, system: str, user: str) -> str:
        response = await self._client.messages.create(
            model=self.model_name,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in response.content if block.type == "text")


class FakeLLM:
    """Test double: returns queued responses in order, one per call.

    Queue `[bad_json, good_json]` to simulate one retry then success, or `[bad, bad]` to
    simulate a retry that still fails. `calls` records every (system, user) pair sent, so
    tests can assert on the rendered prompt too.
    """

    def __init__(self, responses: list[str], *, model_name: str = "fake-llm") -> None:
        self.model_name = model_name
        self._responses = list(responses)
        self.calls: list[dict[str, str]] = []

    async def complete_json(self, *, system: str, user: str) -> str:
        self.calls.append({"system": system, "user": user})
        if not self._responses:
            raise AssertionError("FakeLLM queue exhausted: too many calls for this test")
        return self._responses.pop(0)
