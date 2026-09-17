"""Request/response models for `apps/api/routers/notes.py` — design/synapse's `InsightNote`.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from apps.api.schemas.common import Discipline


class NoteCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    body: str
    disciplines: list[Discipline] = Field(min_length=1, max_length=3)
    week: int | None = None
    source_id: uuid.UUID | None = None
    is_public: bool = False


class NotePatchRequest(BaseModel):
    """All fields optional: only what's provided gets applied — same shape as
    `ItemPatchRequest`/`HomeworkPatchRequest`."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    body: str | None = None
    disciplines: list[Discipline] | None = Field(default=None, min_length=1, max_length=3)
    week: int | None = None
    source_id: uuid.UUID | None = None
    is_public: bool | None = None


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    body: str
    disciplines: list[str]
    week: int | None
    source_id: uuid.UUID | None
    is_public: bool
    created_at: datetime
