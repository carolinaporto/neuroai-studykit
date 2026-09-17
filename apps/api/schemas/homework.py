"""Request/response models for `apps/api/routers/homework.py`."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from apps.api.schemas.common import Discipline

Status = Literal["draft", "published"]


class HomeworkCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    week: int
    title: str
    description: str
    disciplines: list[Discipline] = Field(min_length=1, max_length=3)
    code_url: str | None = None
    live_url: str | None = None


class HomeworkPatchRequest(BaseModel):
    """All fields optional: only what's provided gets applied — same shape as
    `ItemPatchRequest`. Publishing is just `{"status": "published"}`."""

    model_config = ConfigDict(extra="forbid")

    week: int | None = None
    title: str | None = None
    description: str | None = None
    disciplines: list[Discipline] | None = Field(default=None, min_length=1, max_length=3)
    code_url: str | None = None
    live_url: str | None = None
    status: Status | None = None


class HomeworkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    week: int
    title: str
    description: str
    disciplines: list[str]
    code_url: str | None
    live_url: str | None
    status: str
    created_at: datetime
