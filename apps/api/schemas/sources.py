"""Response models for `GET /api/sources` — feeds Synapse's `WeekHeader` + `SourceItem`
(design/synapse). Read-only: there is no upload-via-API yet, ingestion is CLI-only in Fase 1
per ARCHITECTURE.md."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    title: str
    page_count: int | None
    duration_seconds: float | None
    ingested_at: datetime | None


class WeekSources(BaseModel):
    week: int
    title: str | None
    sources: list[SourceOut]
