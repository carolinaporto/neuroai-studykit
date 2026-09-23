"""Pure daily-budget threshold check, shared by every LLM call site — including
`packages/ingest/generator.py`'s per-chunk generation loop, which cannot import
`apps.api.services.budget` (CLAUDE.md invariant 4: `packages/ingest` never imports
`apps/api`). This module has no database dependency at all, so both sides can use it:
`apps/api/services/budget.py` queries `Attempt` for the grading path and calls this;
`packages/ingest/cli.py`'s `generate_for_week` queries `IngestJob` for the generation path
and calls this too. One shared daily pool across every feature that spends real LLM
tokens — ARCHITECTURE.md's "teto diário de tokens por usuário," not a budget per feature.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class BudgetSettings(BaseSettings):
    """Same `DAILY_TOKEN_BUDGET`/`MAX_GRADINGS_PER_DAY` env vars `apps.api.core.config`'s
    `Settings` reads — duplicated, not imported, for the same invariant-4 reason
    `packages/db/session.py`'s `DbSettings` and `packages/core/llm.py`'s `LLMSettings`
    already are. Only `packages/ingest/cli.py`'s CLI entry point uses this directly;
    `apps/api` always passes its own `settings.*` values explicitly instead."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    daily_token_budget: int = 200_000
    max_gradings_per_day: int = 300


class BudgetExceededError(Exception):
    """Raised with a human-readable reason; callers turn this into an HTTP 429 (a live
    request) or a failed IngestJob (a background-style loop like generate_for_week)."""


def check_budget(
    *,
    calls_today: int,
    tokens_today: int,
    estimated_tokens: int,
    daily_token_budget: int,
    max_calls_per_day: int,
) -> None:
    if calls_today >= max_calls_per_day:
        raise BudgetExceededError(
            f"daily LLM call limit reached ({calls_today}/{max_calls_per_day}); "
            "try again later"
        )
    if tokens_today + estimated_tokens > daily_token_budget:
        raise BudgetExceededError(
            f"daily token budget would be exceeded "
            f"({tokens_today} used + {estimated_tokens} estimated > {daily_token_budget}); "
            "try again later"
        )
