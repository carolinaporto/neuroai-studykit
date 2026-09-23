"""`GET /api/checkin/draft?week=N` — M11: a starting point for the weekly check-in this
course actually requires, built from your own real stats (`ARCHITECTURE.md`: `Attempt`
keeps the raw response text, so it's "material para o check-in semanal"). Owner-only.

The draft is plain Python templating over your own numbers — never an LLM call. This is
graded coursework; having a model *compose the reflection itself*, even labeled "draft",
edges toward writing it for you, a different thing from summarizing your own data (which is
squarely CLAUDE.md invariant 2's spirit: compute in Python, never ask a model for the
substance). It hands you real numbers and a spot to write your own two sentences, not prose
pretending to be your reflection.

A week with no items yet, or none attempted, is a valid empty draft (200), not a 404 —
"draft me this week's check-in" is a query, same spirit as `list_sources` treating "nothing
yet" as an empty case rather than an error.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.core.db import get_session
from apps.api.core.deps import get_current_user_id, require_owner
from apps.api.routers.study import STUDYABLE_STATUSES
from apps.api.schemas.checkin import CheckinDraft
from apps.api.services.mastery import latest_attempts_for_items, mastery_by_topic, topic_labels
from packages.db.models import Item, Source
from packages.ingest.topics import load_topics

router = APIRouter(
    prefix="/api/checkin", tags=["checkin"], dependencies=[Depends(require_owner)]
)


def _dedupe_in_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def _render_markdown(
    *,
    week: int,
    title: str | None,
    items_total: int,
    items_attempted: int,
    avg_score: float | None,
    topics: list,
    misconceptions: list[str],
) -> str:
    heading = f"Week {week}" + (f": {title}" if title else "")
    lines = [f"## {heading}", ""]

    if items_total == 0:
        lines.append("No practice questions for this week yet.")
        return "\n".join(lines)

    accuracy_clause = (
        f", averaging {round(avg_score * 100)}% recall accuracy." if avg_score is not None else "."
    )
    lines.append(
        f"I answered {items_attempted}/{items_total} practice questions this week{accuracy_clause}"
    )
    lines.append("")

    attempted_topics = [t for t in topics if t.attempted_count > 0]
    if attempted_topics:
        strongest = attempted_topics[-1]
        weakest = attempted_topics[0]
        lines.append(f"**Where I'm solid:** {strongest.label or strongest.slug}")
        lines.append(f"**Where I need more work:** {weakest.label or weakest.slug}")
        lines.append("")

    lines.append("**Misconceptions I ran into:**")
    if misconceptions:
        lines.extend(f"- {m}" for m in misconceptions)
    else:
        lines.append("- None recorded this week.")
    lines.append("")
    lines.append(
        "[Write 2-3 sentences here about what this tells you about your own understanding.]"
    )
    return "\n".join(lines)


@router.get("/draft", response_model=CheckinDraft)
async def get_checkin_draft(
    week: int,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> CheckinDraft:
    item_rows = (
        await session.execute(
            select(Item.id, Item.topics)
            .join(Source, Source.id == Item.source_id)
            .where(Item.status.in_(STUDYABLE_STATUSES), Source.week == week)
        )
    ).all()
    item_ids = [row[0] for row in item_rows]

    latest_attempts = await latest_attempts_for_items(
        session, user_id=user_id, item_ids=item_ids
    )
    latest_scores = {item_id: attempt.score for item_id, attempt in latest_attempts.items()}
    topics = mastery_by_topic(item_rows, latest_scores, topic_labels())

    misconceptions = _dedupe_in_order(
        [m for _item_id, attempt in latest_attempts.items() for m in attempt.misconceptions]
    )

    avg_score = (
        sum(latest_scores.values()) / len(latest_scores) if latest_scores else None
    )
    title = load_topics().title_for_week(week)

    draft_markdown = _render_markdown(
        week=week,
        title=title,
        items_total=len(item_ids),
        items_attempted=len(latest_scores),
        avg_score=avg_score,
        topics=topics,
        misconceptions=misconceptions,
    )

    return CheckinDraft(
        week=week,
        title=title,
        items_total=len(item_ids),
        items_attempted=len(latest_scores),
        avg_score=avg_score,
        topics=topics,
        misconceptions=misconceptions,
        draft_markdown=draft_markdown,
    )
