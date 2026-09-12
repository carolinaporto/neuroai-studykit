"""Pydantic types for the generator's LLM-facing schema and its validated output.

`Generated*` is exactly what we ask the model for (see `prompts/generate_v1.md`) and is
validated per-item, not per-batch: one bad item must never sink the good ones in the same
response (each retry costs money). `Validated*` is the persisted shape, after
`validators.py` has checked quotes and topics and our own code has assigned rubric ids.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ItemType = Literal["free_recall", "term_def"]
Bloom = Literal["recall", "understand", "apply", "analyze"]


class GeneratedRubricPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    point: str
    weight: float = Field(gt=0)
    support_quote: str


class GeneratedItem(BaseModel):
    """What we ask the model to return for one item. No `id`s anywhere: those are ours to
    assign after validation, never the model's to invent (invariant 2)."""

    model_config = ConfigDict(extra="forbid")

    type: ItemType
    prompt: str
    reference_answer: str
    rubric: list[GeneratedRubricPoint] = Field(min_length=2, max_length=5)
    difficulty: int = Field(ge=1, le=5)
    bloom: Bloom
    topics: list[str] = Field(min_length=1)
    proposed_topics: list[str] = Field(default_factory=list)


class ValidatedRubricPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    point: str
    weight: float
    support_quote: str


class ValidatedItem(BaseModel):
    """The persisted shape: same content as `GeneratedItem` minus `proposed_topics` (which
    never reaches the db — it only feeds the M6 vocabulary review), plus rubric point ids."""

    model_config = ConfigDict(extra="forbid")

    type: ItemType
    prompt: str
    reference_answer: str
    rubric: list[ValidatedRubricPoint]
    difficulty: int
    bloom: Bloom
    topics: list[str]


class RejectedItem(BaseModel):
    """A raw item dict that failed schema or business validation, kept for the generation
    job's record — never silently dropped."""

    model_config = ConfigDict(extra="forbid")

    reason: str
    raw: dict
