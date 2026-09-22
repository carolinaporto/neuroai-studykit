"""Pydantic types for the generator's LLM-facing schema and its validated output.

`Generated*` is exactly what we ask the model for (see `prompts/generate_v1.md`) and is
validated per-item, not per-batch: one bad item must never sink the good ones in the same
response (each retry costs money). `Validated*` is the persisted shape, after
`validators.py` has checked quotes and topics and our own code has assigned rubric ids.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ItemType = Literal["free_recall", "term_def", "cloze", "mcq"]
Bloom = Literal["recall", "understand", "apply", "analyze"]

# `cloze`'s one required blank, in the prompt text. A fixed literal, not user-facing markup —
# kept here (not templated into the prompt file) so the validator and the instructions the
# prompt gives the model can't drift silently the way two independently-edited copies would.
CLOZE_BLANK = "_____"

MIN_MCQ_OPTIONS = 3
MAX_MCQ_OPTIONS = 5

# Types graded deterministically (apps/api/services/grading.py's grade_exact_match) get
# exactly one rubric point — still anchored by a literal support_quote (invariant 1), but
# nothing to weigh-and-sum since grading is binary. Everything else keeps the 2-5 spread.
_SINGLE_POINT_TYPES = {"cloze", "mcq"}
MIN_RUBRIC_POINTS = 2
MAX_RUBRIC_POINTS = 5


class GeneratedRubricPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    point: str
    weight: float = Field(gt=0)
    support_quote: str


class GeneratedChoices(BaseModel):
    """`mcq`'s answer options — no correct-answer marker here or anywhere in this schema.
    Which one is right is `GeneratedItem.reference_answer`, checked by
    `_choices_match_type` to be exactly one of these, verbatim."""

    model_config = ConfigDict(extra="forbid")

    options: list[str] = Field(min_length=MIN_MCQ_OPTIONS, max_length=MAX_MCQ_OPTIONS)


class GeneratedItem(BaseModel):
    """What we ask the model to return for one item. No `id`s anywhere: those are ours to
    assign after validation, never the model's to invent (invariant 2)."""

    model_config = ConfigDict(extra="forbid")

    type: ItemType
    prompt: str
    reference_answer: str
    # Bound relaxed from the old flat 2-5: `_rubric_length_by_type` below enforces the real,
    # type-dependent bound (still 2-5 for free_recall/term_def, exactly 1 for cloze/mcq).
    rubric: list[GeneratedRubricPoint] = Field(min_length=1, max_length=MAX_RUBRIC_POINTS)
    choices: GeneratedChoices | None = None
    difficulty: int = Field(ge=1, le=5)
    bloom: Bloom
    # May be empty: a chunk whose concepts the week's vocabulary doesn't cover puts them in
    # `proposed_topics` instead. An untagged item is still anchored and gradable; rejecting it
    # over a tag threw away good questions (seen on a week whose content drifted from
    # topics.yaml).
    topics: list[str]
    proposed_topics: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _rubric_length_by_type(self) -> "GeneratedItem":
        if self.type in _SINGLE_POINT_TYPES:
            if len(self.rubric) != 1:
                raise ValueError(
                    f"{self.type} items need exactly 1 rubric point, got {len(self.rubric)}"
                )
        elif not (MIN_RUBRIC_POINTS <= len(self.rubric) <= MAX_RUBRIC_POINTS):
            raise ValueError(
                f"{self.type} items need {MIN_RUBRIC_POINTS}-{MAX_RUBRIC_POINTS} rubric "
                f"points, got {len(self.rubric)}"
            )
        return self

    @model_validator(mode="after")
    def _choices_match_type(self) -> "GeneratedItem":
        if self.type == "mcq":
            if self.choices is None:
                raise ValueError("mcq items must include choices")
            options = {option.strip() for option in self.choices.options}
            if self.reference_answer.strip() not in options:
                raise ValueError(
                    "mcq reference_answer must exactly match one of choices.options"
                )
        elif self.choices is not None:
            raise ValueError(f"{self.type} items must not include choices")
        return self

    @model_validator(mode="after")
    def _cloze_has_one_blank(self) -> "GeneratedItem":
        if self.type == "cloze" and self.prompt.count(CLOZE_BLANK) != 1:
            raise ValueError(
                f"cloze prompt must contain exactly one {CLOZE_BLANK!r} blank, "
                f"found {self.prompt.count(CLOZE_BLANK)}"
            )
        return self


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
    choices: dict | None = None
    difficulty: int
    bloom: Bloom
    topics: list[str]


class RejectedItem(BaseModel):
    """A raw item dict that failed schema or business validation, kept for the generation
    job's record — never silently dropped."""

    model_config = ConfigDict(extra="forbid")

    reason: str
    raw: dict
