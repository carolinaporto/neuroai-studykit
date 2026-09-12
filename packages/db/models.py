"""ORM models for ARCHITECTURE.md §3 — M2 scope only: User, Source, Chunk, IngestJob.

Table names are singular (`user`, `source`, `chunk`, `ingest_job`) to match the fixed
vocabulary used across the docs and the M2 acceptance check (`select count(*) from chunk`).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB
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


class IngestJobStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


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
