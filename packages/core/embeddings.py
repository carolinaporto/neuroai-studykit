"""The `EmbeddingClient` protocol for M7 part 2's item dedup (`packages/ingest/dedup.py`).

Same shape as `packages/core/llm.py`'s `LLMClient`/`FakeLLM` split, for the same reason:
every call to an embedding provider goes through this interface, so tests inject
`FakeEmbeddingClient` and never touch a real API (extending CLAUDE.md invariant 5's spirit
— "nenhum teste chama a API do Anthropic" — to the second external provider this project
now has).
"""

from typing import Protocol

from pydantic_settings import BaseSettings, SettingsConfigDict


class EmbeddingClient(Protocol):
    """Turns text into vectors. Callers own batching (one call per chunk's worth of
    prompts, not one call per item) — this protocol's only job is "send these strings, get
    vectors back" so it can be swapped for a fake in tests."""

    model_name: str

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class EmbeddingSettings(BaseSettings):
    """Own settings model, same reason `LLMSettings` has one: `packages/ingest` cannot
    import `apps.api.core.config` (invariant 4)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-small"


class OpenAIEmbeddingClient:
    """Real `EmbeddingClient` backed by the OpenAI embeddings endpoint."""

    def __init__(self, api_key: str, model: str) -> None:
        from openai import AsyncOpenAI

        self.model_name = model
        self._client = AsyncOpenAI(api_key=api_key)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self._client.embeddings.create(model=self.model_name, input=texts)
        return [item.embedding for item in response.data]


class FakeEmbeddingClient:
    """Test double: returns queued vector batches in order, one batch per call — same
    queue/`calls`/exhaustion-raises shape as `packages.core.llm.FakeLLM`.

    Tests hand-craft vectors with a known, exact cosine similarity (e.g. two identical
    basis vectors -> similarity 1.0; two orthogonal ones -> 0.0) rather than anything fuzzy,
    so `packages/ingest/dedup.py`'s 0.92 threshold itself gets a real, precise test.
    """

    def __init__(
        self, responses: list[list[list[float]]], *, model_name: str = "fake-embeddings"
    ) -> None:
        self.model_name = model_name
        self._responses = list(responses)
        self.calls: list[list[str]] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        if not self._responses:
            raise AssertionError(
                "FakeEmbeddingClient queue exhausted: too many calls for this test"
            )
        return self._responses.pop(0)
