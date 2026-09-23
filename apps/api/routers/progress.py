"""`GET /api/progress` — M10: topic mastery and due-item counts, the whole course, not
scoped by week (the milestone doesn't ask for that). Owner-only: personal study data,
locked like Sources/Review/Quizzes per `design/synapse`'s `SiteNav`.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.core.db import get_session
from apps.api.core.deps import get_current_user_id, require_owner
from apps.api.routers.study import STUDYABLE_STATUSES
from apps.api.schemas.progress import DueCounts, ProgressResponse, TopicMastery
from packages.db.models import Attempt, Item, ReviewState, Source
from packages.ingest.topics import load_topics

router = APIRouter(
    prefix="/api/progress", tags=["progress"], dependencies=[Depends(require_owner)]
)


def _topic_labels() -> dict[str, str]:
    """Flattens the whole controlled vocabulary to slug -> label. `TopicsVocabulary` has no
    method for this — `topics_for_week` is deliberately week-scoped for the generator's
    prompt — so it's built here, the one caller that needs every topic regardless of week."""
    vocabulary = load_topics()
    labels = {topic.slug: topic.label for topic in vocabulary.cross_cutting}
    for unit in vocabulary.units:
        for topic in unit.topics:
            labels[topic.slug] = topic.label
    return labels


@router.get("", response_model=ProgressResponse)
async def get_progress(
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> ProgressResponse:
    studyable_items = (
        await session.execute(
            select(Item.id, Item.topics)
            .join(Source, Source.id == Item.source_id)
            .where(Item.status.in_(STUDYABLE_STATUSES), Source.week.is_not(None))
        )
    ).all()
    studyable_ids = [row[0] for row in studyable_items]

    # Latest attempt per item, this user only — same "latest wins" convention
    # _maybe_complete_quiz already uses for scoring, so a corrected wrong answer doesn't
    # keep counting against mastery.
    latest_at_per_item = (
        select(Attempt.item_id, func.max(Attempt.created_at).label("latest_at"))
        .where(Attempt.user_id == user_id, Attempt.item_id.in_(studyable_ids))
        .group_by(Attempt.item_id)
        .subquery()
    )
    latest_scores = dict(
        (
            await session.execute(
                select(Attempt.item_id, Attempt.score).join(
                    latest_at_per_item,
                    (Attempt.item_id == latest_at_per_item.c.item_id)
                    & (Attempt.created_at == latest_at_per_item.c.latest_at),
                )
            )
        ).all()
    )

    labels = _topic_labels()
    item_counts: dict[str, int] = {}
    attempted_counts: dict[str, int] = {}
    score_sums: dict[str, float] = {}
    for item_id, topics in studyable_items:
        score = latest_scores.get(item_id)
        for slug in topics:
            item_counts[slug] = item_counts.get(slug, 0) + 1
            if score is not None:
                attempted_counts[slug] = attempted_counts.get(slug, 0) + 1
                score_sums[slug] = score_sums.get(slug, 0.0) + score

    topics = [
        TopicMastery(
            slug=slug,
            label=labels.get(slug),
            item_count=item_counts[slug],
            attempted_count=attempted_counts.get(slug, 0),
            avg_score=(score_sums[slug] / attempted_counts[slug]) if slug in score_sums else None,
        )
        for slug in item_counts
    ]
    # Weakest first; a topic with no attempts yet isn't "weak" — it sorts last, not first.
    def _sort_key(topic: TopicMastery) -> tuple[bool, float]:
        return (topic.avg_score is None, topic.avg_score if topic.avg_score is not None else 0.0)

    topics.sort(key=_sort_key)

    today = datetime.now(UTC).date()
    review_rows = (
        await session.execute(
            select(ReviewState.item_id, ReviewState.due_at).where(
                ReviewState.user_id == user_id, ReviewState.item_id.in_(studyable_ids)
            )
        )
    ).all()
    reviewed_ids = {row[0] for row in review_rows}
    overdue = due_today = upcoming = 0
    for _item_id, due_at in review_rows:
        due_date = due_at.astimezone(UTC).date()
        if due_date < today:
            overdue += 1
        elif due_date == today:
            due_today += 1
        else:
            upcoming += 1

    due = DueCounts(
        never_reviewed=len(studyable_ids) - len(reviewed_ids),
        overdue=overdue,
        due_today=due_today,
        upcoming=upcoming,
    )

    return ProgressResponse(topics=topics, due=due)
