"""Response model for `apps/api/routers/checkin.py` — M11."""

from pydantic import BaseModel

from apps.api.schemas.progress import TopicMastery


class CheckinDraft(BaseModel):
    week: int
    title: str | None
    items_total: int
    items_attempted: int
    avg_score: float | None
    topics: list[TopicMastery]
    misconceptions: list[str]
    # Plain Python templating from the fields above, never model-authored: see the
    # router's docstring for why an LLM never writes this.
    draft_markdown: str
