"""Request/response models for the study routes. Kept separate from the ORM models
(`packages/db/models.py`) per CLAUDE.md convention — routers never return ORM objects
directly.
"""

import uuid
from datetime import datetime

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
    """Invariant 7: only `item_id` + the student's raw text, never a prompt.
    `quiz_attempt_id` is optional — set when this answer is one item of a `QuizAttempt`
    (see `POST /api/study/quiz`); omitted, it's a standalone answer outside any quiz."""

    model_config = ConfigDict(extra="forbid")

    item_id: uuid.UUID
    response_text: str
    quiz_attempt_id: uuid.UUID | None = None


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


class StartQuizRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    week: int
    limit: int = Field(default=10, ge=1, le=50)


class StartQuizResponse(BaseModel):
    quiz_attempt_id: uuid.UUID
    week: int
    items: list[StudyQueueItem]


class QuizAttemptOut(BaseModel):
    id: uuid.UUID
    week: int
    status: str
    score: float | None
    item_count: int
    started_at: datetime
    completed_at: datetime | None


class WeekQuizzes(BaseModel):
    """One entry per week that has at least one Item — a week with none simply doesn't
    appear, same convention as `WeekSources`. The frontend treats "not listed" as locked."""

    week: int
    item_count: int
    attempts: list[QuizAttemptOut]


class QuizReviewItem(BaseModel):
    """One item's full result inside a completed (or in-progress) QuizAttempt — the
    "Review answers" screen. Flat rather than nesting `StudyQueueItem` + `StudyAnswerResponse`
    because the review view needs both at once, keyed by item, not two separate lookups."""

    item_id: uuid.UUID
    prompt: str
    response_text: str
    score: float
    rubric_hits: list[RubricHit]
    misconceptions: list[str]
    feedback_md: str
    reference_answer: str
    source: list[SourceExcerpt]


class QuizReviewResponse(BaseModel):
    quiz_attempt: QuizAttemptOut
    results: list[QuizReviewItem]
