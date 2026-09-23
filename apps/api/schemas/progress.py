"""Response models for `apps/api/routers/progress.py` — M10."""

from pydantic import BaseModel


class TopicMastery(BaseModel):
    slug: str
    label: str | None
    item_count: int
    attempted_count: int
    # None for a topic with items but no attempts yet — never studied is not the same as
    # weak, and CLAUDE.md invariant 2's spirit (never invent a number) applies here too:
    # there's no honest average of zero attempts.
    avg_score: float | None


class DueCounts(BaseModel):
    """Calendar-date buckets (UTC) against a studyable item's `ReviewState`, or its absence.
    `never_reviewed + overdue + due_today + upcoming` always equals the total studyable
    item count."""

    never_reviewed: int
    overdue: int
    due_today: int
    upcoming: int


class ProgressResponse(BaseModel):
    topics: list[TopicMastery]
    due: DueCounts
