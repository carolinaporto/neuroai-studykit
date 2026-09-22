"""The `LLMClient` protocol (CLAUDE.md invariant 5): every call to an LLM anywhere in this
codebase goes through this interface, so tests can inject `FakeLLM` and never touch the
Anthropic API. `AnthropicLLMClient` is the only implementation that does.
"""

import base64
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

    async def complete_vision(self, *, system: str, user: str, images: list[bytes]) -> str:
        """Same contract as `complete_json` but with PNG page images attached to the user
        turn — used to transcribe scanned pages. Returns plain text, not JSON."""
        ...


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

    async def complete_vision(self, *, system: str, user: str, images: list[bytes]) -> str:
        content: list[dict] = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64.b64encode(image).decode("ascii"),
                },
            }
            for image in images
        ]
        content.append({"type": "text", "text": user})
        response = await self._client.messages.create(
            model=self.model_name,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=system,
            messages=[{"role": "user", "content": content}],
        )
        return "".join(block.text for block in response.content if block.type == "text")


class FakeLLM:
    """Test double: returns queued responses in order, one per call.

    Queue `[bad_json, good_json]` to simulate one retry then success, or `[bad, bad]` to
    simulate a retry that still fails. `calls` records every (system, user) pair sent, so
    tests can assert on the rendered prompt too.

    `complete_vision` draws from its own queue (`vision_responses`) and records into
    `vision_calls` (system, user, image count), so a test can queue text and vision replies
    independently. An entry may be an `Exception` instance, which is raised instead of
    returned — to simulate the API failing mid-transcription.
    """

    def __init__(
        self,
        responses: list[str],
        *,
        vision_responses: list[str | Exception] | None = None,
        model_name: str = "fake-llm",
    ) -> None:
        self.model_name = model_name
        self._responses = list(responses)
        self._vision_responses = list(vision_responses or [])
        self.calls: list[dict[str, str]] = []
        self.vision_calls: list[dict[str, object]] = []

    async def complete_json(self, *, system: str, user: str) -> str:
        self.calls.append({"system": system, "user": user})
        if not self._responses:
            raise AssertionError("FakeLLM queue exhausted: too many calls for this test")
        return self._responses.pop(0)

    async def complete_vision(self, *, system: str, user: str, images: list[bytes]) -> str:
        self.vision_calls.append({"system": system, "user": user, "image_count": len(images)})
        if not self._vision_responses:
            raise AssertionError("FakeLLM vision queue exhausted: too many calls for this test")
        response = self._vision_responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response
