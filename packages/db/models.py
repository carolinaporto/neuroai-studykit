"""ORM models for ARCHITECTURE.md §3 — through M3: User, Source, Chunk, IngestJob, Item.

Table names are singular (`user`, `source`, `chunk`, `ingest_job`, `item`) to match the fixed
vocabulary used across the docs and the M2 acceptance check (`select count(*) from chunk`).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import ARRAY, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, CreatedAtMixin, UUIDPkMixin


class UserRole(enum.StrEnum):
    owner = "owner"
    student = "student"
    demo = "demo"


class SourceKind(enum.StrEnum):
    lecture_pdf = "lecture_pdf"
    slides = "slides"
    transcript = "transcript"
    paper = "paper"
    notes = "notes"


class SourceStatus(enum.StrEnum):
    pending = "pending"
    ingested = "ingested"
    failed = "failed"


class IngestJobKind(enum.StrEnum):
    parse_and_chunk = "parse_and_chunk"
    generate = "generate"


class IngestJobStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class ItemType(enum.StrEnum):
    """Full type set from ARCHITECTURE.md §3. M3's generator only ever emits `free_recall`
    and `term_def` (Fase 1 scope); `cloze`/`mcq`/`compare`/`application` are here because the
    column's contract is fixed by the architecture doc, not because this milestone writes
    them."""

    free_recall = "free_recall"
    term_def = "term_def"
    cloze = "cloze"
    mcq = "mcq"
    compare = "compare"
    application = "application"


class ItemBloom(enum.StrEnum):
    recall = "recall"
    understand = "understand"
    apply = "apply"
    analyze = "analyze"


class ItemStatus(enum.StrEnum):
    draft = "draft"
    approved = "approved"
    edited = "edited"
    retired = "retired"


class User(UUIDPkMixin, CreatedAtMixin, Base):
    __tablename__ = "user"

    email: Mapped[str] = mapped_column(String, unique=True)
    role: Mapped[UserRole] = mapped_column(
        SqlEnum(UserRole, name="user_role"), default=UserRole.owner
    )


class Source(UUIDPkMixin, CreatedAtMixin, Base):
    __tablename__ = "source"

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String)
    kind: Mapped[SourceKind] = mapped_column(SqlEnum(SourceKind, name="source_kind"))
    storage_uri: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(nullable=True)
    status: Mapped[SourceStatus] = mapped_column(
        SqlEnum(SourceStatus, name="source_status"), default=SourceStatus.pending
    )
    ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Chunk(UUIDPkMixin, Base):
    __tablename__ = "chunk"
    __table_args__ = (UniqueConstraint("source_id", "ordinal", name="uq_chunk_source_ordinal"),)

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    locators: Mapped[list[dict]] = mapped_column(JSONB)
    token_count: Mapped[int] = mapped_column(Integer)
    # `embedding vector(1536)` is added via raw DDL in the migration, not mapped here yet:
    # the `pgvector` Python package is a new dependency we only add once something actually
    # writes embeddings (M3/M7) — see CLAUDE.md "pergunte antes de adicionar dependência".


class IngestJob(UUIDPkMixin, CreatedAtMixin, Base):
    __tablename__ = "ingest_job"

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[IngestJobKind] = mapped_column(SqlEnum(IngestJobKind, name="ingest_job_kind"))
    status: Mapped[IngestJobStatus] = mapped_column(
        SqlEnum(IngestJobStatus, name="ingest_job_status")
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String, nullable=True)


class Item(UUIDPkMixin, CreatedAtMixin, Base):
    __tablename__ = "item"

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source.id", ondelete="CASCADE"), index=True
    )
    # uuid[] rather than a join table: an item's anchor chunks are fixed at generation time
    # and never queried from the chunk side, so a real relationship table buys nothing here.
    chunk_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(PgUUID(as_uuid=True)))
    type: Mapped[ItemType] = mapped_column(SqlEnum(ItemType, name="item_type"))
    prompt: Mapped[str] = mapped_column(Text)
    reference_answer: Mapped[str] = mapped_column(Text)
    rubric: Mapped[list[dict]] = mapped_column(JSONB)
    choices: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    difficulty: Mapped[int] = mapped_column(Integer)
    bloom: Mapped[ItemBloom] = mapped_column(SqlEnum(ItemBloom, name="item_bloom"))
    topics: Mapped[list[str]] = mapped_column(ARRAY(String))
    status: Mapped[ItemStatus] = mapped_column(
        SqlEnum(ItemStatus, name="item_status"), default=ItemStatus.draft
    )
    gen_model: Mapped[str] = mapped_column(String)
    gen_prompt_version: Mapped[str] = mapped_column(String)
