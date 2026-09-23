"""`GET /api/progress` — M10: topic mastery and due-item counts, the whole course, not
scoped by week (the milestone doesn't ask for that). Owner-only: personal study data,
locked like Sources/Review/Quizzes per `design/synapse`'s `SiteNav`.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.core.db import get_session
from apps.api.core.deps import get_current_user_id, require_owner
from apps.api.routers.study import STUDYABLE_STATUSES
from apps.api.schemas.progress import DueCounts, ProgressResponse
from apps.api.services.mastery import latest_attempts_for_items, mastery_by_topic, topic_labels
from packages.db.models import Item, ReviewState, Source

router = APIRouter(
    prefix="/api/progress", tags=["progress"], dependencies=[Depends(require_owner)]
)


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

    latest_attempts = await latest_attempts_for_items(
        session, user_id=user_id, item_ids=studyable_ids
    )
    latest_scores = {item_id: attempt.score for item_id, attempt in latest_attempts.items()}
    topics = mastery_by_topic(studyable_items, latest_scores, topic_labels())

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
