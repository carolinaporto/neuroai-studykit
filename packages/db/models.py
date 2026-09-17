"""ORM models for ARCHITECTURE.md §3 — through M3: User, Source, Chunk, IngestJob, Item.

Table names are singular (`user`, `source`, `chunk`, `ingest_job`, `item`) to match the fixed
vocabulary used across the docs and the M2 acceptance check (`select count(*) from chunk`).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, CreatedAtMixin, UUIDPkMixin, Vector


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


class HomeworkStatus(enum.StrEnum):
    """No `retired` here on purpose: `draft` already keeps an entry off the public list
    (see `apps/api/routers/homework.py`), and there is no private state to fall back to —
    HomeworkCard's README is explicit that a homework entry never gets a private variant; an
    entry that must stay unlisted permanently belongs in Notes & Insights, not this table."""

    draft = "draft"
    published = "published"


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
    # For a CLI-synced source (`ingest sync`), the original file's real path on the user's
    # own machine — never copied, `content/` is gitignored on purpose (ARCHITECTURE.md §8).
    # For a web-uploaded source, just the original filename, kept for reference only — the
    # actual bytes live in `file_data` below, not on any disk this app manages, per the
    # user's explicit choice over paying for S3/R2: no new external service, no local-disk
    # durability risk either.
    storage_uri: Mapped[str] = mapped_column(Text)
    file_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    file_media_type: Mapped[str | None] = mapped_column(String, nullable=True)
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
    # Mapped with the DDL-only `Vector` stand-in (see packages/db/base.py) so alembic
    # autogenerate recognizes the column instead of proposing to drop it. Nothing reads or
    # writes this yet — the real `pgvector` package is a new dependency we only add once
    # something actually writes embeddings (M7).
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)


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


class QuizAttemptStatus(enum.StrEnum):
    in_progress = "in_progress"
    completed = "completed"


class QuizAttempt(UUIDPkMixin, CreatedAtMixin, Base):
    """One pass through a week's recall check — design/synapse's `QuizCard`. Deliberately
    *not* one-per-week: a week can have any number of attempts (retries, later review), each
    independent, each with its own frozen item set and score.

    `item_ids` is frozen at creation from whatever Items existed for the week at that
    moment — like `Item.chunk_ids`, a plain array rather than a join table, since it's fixed
    for the attempt's whole life and never queried from the item side.
    """

    __tablename__ = "quiz_attempt"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"), index=True)
    week: Mapped[int] = mapped_column(Integer, index=True)
    item_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(PgUUID(as_uuid=True)))
    status: Mapped[QuizAttemptStatus] = mapped_column(
        SqlEnum(QuizAttemptStatus, name="quiz_attempt_status"),
        default=QuizAttemptStatus.in_progress,
    )
    # Mean of each item's Attempt.score once every item has one — see
    # apps/api/routers/study.py's completion check. NULL while in_progress: never a guessed
    # partial number, per CLAUDE.md invariant 2 ("nota é calculada em Python").
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Attempt(UUIDPkMixin, CreatedAtMixin, Base):
    __tablename__ = "attempt"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"), index=True)
    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("item.id", ondelete="CASCADE"), index=True
    )
    # NULL for a standalone answer outside any quiz (the original M4 flow, still used
    # as-is). Set when the answer was submitted as part of a QuizAttempt — see
    # apps/api/routers/study.py's `answer()` — so "review answers" can list exactly this
    # attempt's per-item results.
    quiz_attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("quiz_attempt.id", ondelete="CASCADE"), nullable=True, index=True
    )
    response_text: Mapped[str] = mapped_column(Text)
    # sha256(item_id + normalized response) — see apps/api/services/grading.py. Indexed,
    # not unique: a duplicate row from a rare race is harmless, so no need to guard it.
    response_hash: Mapped[str] = mapped_column(String(64), index=True)
    score: Mapped[float] = mapped_column(Float)
    rubric_hits: Mapped[list[dict]] = mapped_column(JSONB)
    misconceptions: Mapped[list[str]] = mapped_column(ARRAY(String))
    feedback_md: Mapped[str] = mapped_column(Text)
    grader_model: Mapped[str] = mapped_column(String)
    latency_ms: Mapped[int] = mapped_column(Integer)
    # Conservative worst-case estimate of this call's cost (prompt + max possible output),
    # not metered usage — see apps/api/services/budget.py. Summed over a rolling 24h window
    # to enforce DAILY_TOKEN_BUDGET; a circuit breaker against a runaway loop, not billing.
    tokens_used: Mapped[int] = mapped_column(Integer)


class Homework(UUIDPkMixin, CreatedAtMixin, Base):
    """A portfolio entry in the public Homework section — design/synapse's `HomeworkCard`.
    Deliberately thin: each homework is its own separate project (a write-up, a new page, an
    interactive subsite entirely outside this app), so this table stores only the card's
    metadata and outbound links, never the homework's actual content."""

    __tablename__ = "homework"

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    week: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    # Free-form ARRAY(String), validated at the Pydantic layer (apps/api/schemas/homework.py)
    # against the course's three lenses — same shape as Item.topics, which validates against
    # topics.yaml at the ingest layer instead. Not a Postgres enum: adding a fourth lens
    # later shouldn't need a migration.
    disciplines: Mapped[list[str]] = mapped_column(ARRAY(String))
    code_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    live_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[HomeworkStatus] = mapped_column(
        SqlEnum(HomeworkStatus, name="homework_status"), default=HomeworkStatus.draft
    )


class Note(UUIDPkMixin, CreatedAtMixin, Base):
    """A personal note or "aha moment" — design/synapse's `InsightNote`. Unlike Homework,
    private is the default here (`is_public=False`): a note referencing locked lecture
    content usually shouldn't be public, per the InsightNote README.

    `url` is an optional outbound link (Google Drive, Docs, Notion — anything) to the actual
    document: the user's own call that a note surviving the app going away someday matters
    more than keeping every word of it in this database. `body` stays a short excerpt shown
    on the card, not required to carry the full text — a note can be link-only, text-only,
    or both, but not neither (enforced at the API layer, not here)."""

    __tablename__ = "note"

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    title: Mapped[str] = mapped_column(String)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    disciplines: Mapped[list[str]] = mapped_column(ARRAY(String))
    # Both optional and independent: a note can float free of any week/source, reference a
    # week in general, or point at one specific Source — never inferred from one another.
    week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source.id", ondelete="SET NULL"), nullable=True
    )
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
