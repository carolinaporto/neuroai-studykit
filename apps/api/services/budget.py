"""Daily budget guard, shared by grading (`/api/study/answer`, this module's original
scope) and generation (`packages/ingest/cli.py::generate_for_week`, which calls
`packages.core.budget.check_budget` directly instead — see that module's docstring for
why) — ARCHITECTURE.md §7: "teto diário de tokens por usuário... desde a v1", because the
real risk with a private site isn't abuse, it's a bug (a frontend retry loop, a stuck
effect re-submitting) burning the API key overnight.

This is a circuit breaker, not a billing system: `estimate_call_tokens` is a *worst-case*
estimate (prompt tokens, via a cheap word-count heuristic, plus the maximum tokens the
model could possibly return — `MAX_OUTPUT_TOKENS`), checked *before* the LLM call so a
call that would blow the budget never happens. `Attempt.tokens_used` (grading) and
`IngestJob.payload["estimated_tokens"]` (generation) store that same estimate, not metered
usage — good enough to catch a runaway loop, not to reconcile a bill.
"""

import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.core.budget import BudgetExceededError as BudgetExceededError  # re-exported
from packages.core.budget import check_budget
from packages.core.llm import MAX_OUTPUT_TOKENS
from packages.db.models import Attempt, IngestJob, IngestJobKind, Source

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


async def spent_today(session: AsyncSession, *, owner_id: UUID) -> tuple[int, int]:
    """(calls, tokens) across every LLM call site that spends this owner's real budget in
    the rolling 24h window — one shared pool, not a per-feature one (packages.core.budget's
    module docstring). Grading logs into `Attempt` directly; generation logs its own
    estimate into `IngestJob.payload["estimated_tokens"]` (see
    `packages/ingest/cli.py::generate_for_week`), scoped to this owner via `Source` since
    `IngestJob` itself has no `owner_id`."""
    since = datetime.now(UTC) - ROLLING_WINDOW
    grading_calls, grading_tokens = (
        await session.execute(
            select(func.count(Attempt.id), func.coalesce(func.sum(Attempt.tokens_used), 0)).where(
                Attempt.user_id == owner_id, Attempt.created_at >= since
            )
        )
    ).one()

    generate_jobs = (
        await session.scalars(
            select(IngestJob)
            .join(Source, Source.id == IngestJob.source_id)
            .where(
                Source.owner_id == owner_id,
                IngestJob.created_at >= since,
                IngestJob.kind == IngestJobKind.generate,
                # attempts=0 marks a chunk rejected by this same budget check before any
                # LLM call was made (generate_for_week) — excluded, same as grading: a
                # rejected request never creates an Attempt either, so it can't count
                # against a future check. Without this, one rejection would count as a
                # "call" forever (until it ages out of the window), tightening the call
                # limit for no real spend.
                IngestJob.attempts > 0,
            )
        )
    ).all()
    generate_calls = len(generate_jobs)
    generate_tokens = sum(job.payload.get("estimated_tokens", 0) for job in generate_jobs)

    return grading_calls + generate_calls, grading_tokens + generate_tokens


async def enforce_daily_budget(
    session: AsyncSession,
    *,
    user_id: UUID,
    estimated_tokens: int,
    daily_token_budget: int,
    max_gradings_per_day: int,
) -> None:
    calls_today, tokens_today = await spent_today(session, owner_id=user_id)
    check_budget(
        calls_today=calls_today,
        tokens_today=tokens_today,
        estimated_tokens=estimated_tokens,
        daily_token_budget=daily_token_budget,
        max_calls_per_day=max_gradings_per_day,
    )
