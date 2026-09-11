"""Pydantic types shared by parsers, chunker and CLI.

Invariant (CLAUDE.md #4): these are plain data types with no ORM, no db session, no app
config. Locators use the fixed jsonb shapes from CLAUDE.md: {"page": 7}, {"slide": 12},
{"t0": 872, "t1": 965}.
"""

from pydantic import BaseModel, ConfigDict, model_validator


class Locator(BaseModel):
    """Anchor into one source block, in exactly one of the fixed shapes."""

    model_config = ConfigDict(extra="forbid")

    page: int | None = None
    slide: int | None = None
    has_notes: bool | None = None
    t0: float | None = None
    t1: float | None = None

    @model_validator(mode="after")
    def _exactly_one_shape(self) -> "Locator":
        has_time = self.t0 is not None or self.t1 is not None
        shapes = [self.page is not None, self.slide is not None, has_time]
        if sum(shapes) != 1:
            raise ValueError("locator must set exactly one of: page, slide, or t0/t1")
        if self.t0 is not None and self.t1 is None:
            raise ValueError("transcript locator needs both t0 and t1")
        if self.t1 is not None and self.t0 is None:
            raise ValueError("transcript locator needs both t0 and t1")
        return self

    def as_dict(self) -> dict[str, int | float | bool]:
        return self.model_dump(exclude_none=True)


class ParsedBlock(BaseModel):
    """One unit of text straight out of a parser, before chunking."""

    text: str
    locator: Locator


class Chunk(BaseModel):
    """A chunk ready for embedding/generation: text plus the locator(s) that justify it."""

    ordinal: int
    text: str
    token_count: int
    locators: list[Locator]

    @model_validator(mode="after")
    def _non_empty(self) -> "Chunk":
        if not self.text.strip():
            raise ValueError("chunk text must not be empty")
        if not self.locators:
            raise ValueError("chunk must have at least one locator")
        return self
