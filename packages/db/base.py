"""Declarative base and shared column mixins for the ORM models in `packages/db/models.py`.

Lives outside `apps/api` on purpose: `packages/ingest/cli.py` (the `sync` command) needs
these models too, and invariant 4 in CLAUDE.md forbids `packages/ingest` from importing
anything under `apps/api`.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import UserDefinedType


class Base(DeclarativeBase):
    pass


class Vector(UserDefinedType):
    """DDL-only stand-in for pgvector's `vector(n)` column type.

    `chunk.embedding` was added via raw DDL in the M2 migration and deliberately left
    unmapped on the ORM model — see the comment that used to live on `Chunk.embedding` —
    because reading/writing embeddings needs the real `pgvector` Python package, a new
    dependency CLAUDE.md says to ask about before adding, and nothing writes embeddings
    until M7. Leaving the column unmapped, though, means `alembic check`/autogenerate sees
    a DB column with no model counterpart and proposes *dropping* it — a real footgun the
    first time someone runs `make migrate` without reading the diff carefully.

    This type exists only to make that column visible to SQLAlchemy's metadata so
    autogenerate stops proposing to remove it. It renders correct DDL (`vector(1536)`) but
    does no value conversion — nothing here reads or writes an embedding, so there is
    nothing to convert. Replace with the real `pgvector` SQLAlchemy type in M7, when
    something actually needs `list[float]` in and out.
    """

    cache_ok = True

    def __init__(self, dim: int) -> None:
        self.dim = dim

    def get_col_spec(self, **kw: object) -> str:
        return f"vector({self.dim})"


class UUIDPkMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
