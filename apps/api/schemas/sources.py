"""Response models for `apps/api/routers/sources.py` — Synapse's `WeekHeader` +
`SourceItem`, plus the upload and question-generation actions the Sources page drives."""

import uuid
from datetime import datetime
from typing import Literal

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


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ordinal: int
    text: str
    locators: list[dict]
    token_count: int


class SourceDetail(SourceOut):
    """`SourceOut` plus its chunks, in order — the click-to-preview panel's data. Chunk text
    is what the app actually extracted, which is the honest thing to preview for a type
    (`.pptx`, `.vtt`/`.srt`) the browser can't render natively; a `.pdf` gets the real file
    via `GET /api/sources/{id}/file` instead, this is just backup/context for it too."""

    chunks: list[ChunkOut]


class UploadResult(BaseModel):
    filename: str
    status: Literal["ingested", "duplicate", "unsupported", "too_large", "failed"]
    chunk_count: int | None = None
    error: str | None = None


class UploadSourcesResponse(BaseModel):
    results: list[UploadResult]


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    week: int
    # Re-generate chunks that already have items too, instead of skipping them — see
    # packages/ingest/cli.py's generate_for_week docstring. Off by default so an accidental
    # second click of "Generate" is nearly free, not a second paid pass over everything.
    force: bool = False


class GenerateResponse(BaseModel):
    chunks_processed: int
    items_saved: int
    items_rejected: int
    items_deduped: int
    chunks_failed: int
    proposed_topics: list[str]
