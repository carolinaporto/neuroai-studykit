import uuid

from pydantic import BaseModel, ConfigDict


class ItemPatchRequest(BaseModel):
    """All fields optional: only what's provided gets applied. Covers the
    approve/edit/retire workflow sketched in docs/ARCHITECTURE.md §6 — the review UI itself
    is M6, this only exposes the endpoint."""

    model_config = ConfigDict(extra="forbid")

    status: str | None = None
    prompt: str | None = None
    reference_answer: str | None = None
    rubric: list[dict] | None = None
    difficulty: int | None = None
    bloom: str | None = None
    topics: list[str] | None = None
    choices: dict | None = None


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: uuid.UUID
    chunk_ids: list[uuid.UUID]
    type: str
    prompt: str
    reference_answer: str
    rubric: list[dict]
    choices: dict | None
    difficulty: int
    bloom: str
    topics: list[str]
    status: str
