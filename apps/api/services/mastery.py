"""Topic-mastery aggregation shared by `apps/api/routers/progress.py` (M10, every
studyable item) and `apps/api/routers/checkin.py` (M11, one week's items only) — the exact
same "latest attempt per item, fan out by topic" computation, just over a different item
set, so it lives here once instead of copy-pasted twice.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.schemas.progress import TopicMastery
from packages.db.models import Attempt
from packages.ingest.topics import load_topics


def topic_labels() -> dict[str, str]:
    """Flattens the whole controlled vocabulary to slug -> label. `TopicsVocabulary` has no
    method for this — `topics_for_week` is deliberately week-scoped for the generator's
    prompt — so it's built here, the one place that needs every topic regardless of week."""
    vocabulary = load_topics()
    labels = {topic.slug: topic.label for topic in vocabulary.cross_cutting}
    for unit in vocabulary.units:
        for topic in unit.topics:
            labels[topic.slug] = topic.label
    return labels


async def latest_attempts_for_items(
    session: AsyncSession, *, user_id: uuid.UUID, item_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, Attempt]:
    """This user's latest `Attempt` per item — same "latest wins" convention
    `_maybe_complete_quiz` (apps/api/routers/study.py) already uses for scoring, so a
    corrected wrong answer (or its misconceptions — see checkin.py) doesn't keep counting
    once a later attempt supersedes it."""
    latest_at_per_item = (
        select(Attempt.item_id, func.max(Attempt.created_at).label("latest_at"))
        .where(Attempt.user_id == user_id, Attempt.item_id.in_(item_ids))
        .group_by(Attempt.item_id)
        .subquery()
    )
    attempts = (
        await session.scalars(
            select(Attempt).join(
                latest_at_per_item,
                (Attempt.item_id == latest_at_per_item.c.item_id)
                & (Attempt.created_at == latest_at_per_item.c.latest_at),
            )
        )
    ).all()
    return {attempt.item_id: attempt for attempt in attempts}


def mastery_by_topic(
    item_topics: Sequence[tuple[uuid.UUID, list[str]]],
    latest_scores: dict[uuid.UUID, float],
    labels: dict[str, str],
) -> list[TopicMastery]:
    """Pure aggregation, no database: fans each item's latest score out across every topic
    it's tagged with, averages per topic, sorted weakest-first — a topic with items but no
    attempts yet isn't "weak," so it sorts last, not first."""
    item_counts: dict[str, int] = {}
    attempted_counts: dict[str, int] = {}
    score_sums: dict[str, float] = {}
    for item_id, topics in item_topics:
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

    def _sort_key(topic: TopicMastery) -> tuple[bool, float]:
        return (topic.avg_score is None, topic.avg_score if topic.avg_score is not None else 0.0)

    topics.sort(key=_sort_key)
    return topics
