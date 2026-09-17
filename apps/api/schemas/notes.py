"""Request/response models for `apps/api/routers/notes.py` — design/synapse's `InsightNote`.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from apps.api.schemas.common import Discipline


class NoteCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    body: str | None = None
    url: str | None = None
    disciplines: list[Discipline] = Field(min_length=1, max_length=3)
    week: int | None = None
    source_id: uuid.UUID | None = None
    is_public: bool = False

    @model_validator(mode="after")
    def _require_body_or_url(self) -> "NoteCreateRequest":
        if not self.body and not self.url:
            raise ValueError("a note needs at least one of body or url")
        return self


class NotePatchRequest(BaseModel):
    """All fields optional: only what's provided gets applied — same shape as
    `ItemPatchRequest`/`HomeworkPatchRequest`. The body-or-url requirement is checked in the
    router, not here, since a patch validly touching only `week` must not be forced to also
    know about that rule."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    body: str | None = None
    url: str | None = None
    disciplines: list[Discipline] | None = Field(default=None, min_length=1, max_length=3)
    week: int | None = None
    source_id: uuid.UUID | None = None
    is_public: bool | None = None


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    body: str | None
    url: str | None
    disciplines: list[str]
    week: int | None
    source_id: uuid.UUID | None
    is_public: bool
    created_at: datetime
