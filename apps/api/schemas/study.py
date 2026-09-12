"""Request/response models for the study routes. Kept separate from the ORM models
(`packages/db/models.py`) per CLAUDE.md convention — routers never return ORM objects
directly.
"""

import uuid

from pydantic import BaseModel, ConfigDict, Field


class StudySessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    week: int | None = None
    topics: list[str] | None = None
    limit: int = Field(default=10, ge=1, le=50)


class StudyQueueItem(BaseModel):
    """Deliberately omits `rubric`, `reference_answer` and any source quote: the gabarito
    must not reach the client before an answer is submitted."""

    id: uuid.UUID
    type: str
    prompt: str
    difficulty: int
    bloom: str
    topics: list[str]


class StudyAnswerRequest(BaseModel):
    """Invariant 7: only `item_id` + the student's raw text, never a prompt."""

    model_config = ConfigDict(extra="forbid")

    item_id: uuid.UUID
    response_text: str


class RubricHit(BaseModel):
    point_id: str
    point: str
    weight: float
    covered: bool
    evidence: str


class SourceExcerpt(BaseModel):
    locator: dict
    quote: str


class StudyAnswerResponse(BaseModel):
    score: float
    rubric_hits: list[RubricHit]
    misconceptions: list[str]
    feedback_md: str
    reference_answer: str
    source: list[SourceExcerpt]
    cached: bool
