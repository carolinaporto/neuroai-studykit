"""Daily budget guard for `/api/study/answer` — ARCHITECTURE.md §7: "teto diário de tokens
por usuário... desde a v1", because the real risk with a private site isn't abuse, it's a
bug (a frontend retry loop, a stuck effect re-submitting) burning the API key overnight.

This is a circuit breaker, not a billing system: `estimate_call_tokens` is a *worst-case*
estimate (prompt tokens, via a cheap word-count heuristic, plus the maximum tokens the
grader could possibly return — `MAX_OUTPUT_TOKENS`), checked *before* the LLM call so a
call that would blow the budget never happens. `Attempt.tokens_used` stores that same
estimate, not metered usage — good enough to catch a runaway loop, not to reconcile a bill.
"""

import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.core.llm import MAX_OUTPUT_TOKENS
from packages.db.models import Attempt

_WORD_RE = re.compile(r"\S+")

ROLLING_WINDOW = timedelta(hours=24)


def estimate_tokens(text: str) -> int:
    """Cheap word-count heuristic (~1.3 tokens/word for English) — same shape as
    `packages/ingest/chunker.estimate_tokens`, duplicated rather than imported: that one is
    ingest's, this is api's, and invariant 4 keeps the two packages from depending on each
    other in either direction for something this small."""
    words = len(_WORD_RE.findall(text))
    return max(1, round(words * 1.3)) if words else 0


def estimate_call_tokens(*parts: str) -> int:
    """Worst-case token cost of one grading call: every input part plus the maximum the
    model could emit in response."""
    return sum(estimate_tokens(part) for part in parts) + MAX_OUTPUT_TOKENS


class BudgetExceededError(Exception):
    """Raised with a human-readable reason; the router turns this into HTTP 429."""


async def enforce_daily_budget(
    session: AsyncSession,
    *,
    user_id: UUID,
    estimated_tokens: int,
    daily_token_budget: int,
    max_gradings_per_day: int,
) -> None:
    since = datetime.now(UTC) - ROLLING_WINDOW
    gradings_today, tokens_today = (
        await session.execute(
            select(func.count(Attempt.id), func.coalesce(func.sum(Attempt.tokens_used), 0)).where(
                Attempt.user_id == user_id, Attempt.created_at >= since
            )
        )
    ).one()

    if gradings_today >= max_gradings_per_day:
        raise BudgetExceededError(
            f"daily grading limit reached ({gradings_today}/{max_gradings_per_day}); "
            "try again later"
        )
    if tokens_today + estimated_tokens > daily_token_budget:
        raise BudgetExceededError(
            f"daily token budget would be exceeded "
            f"({tokens_today} used + {estimated_tokens} estimated > {daily_token_budget}); "
            "try again later"
        )
