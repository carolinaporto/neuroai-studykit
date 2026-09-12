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


class Base(DeclarativeBase):
    pass


class UUIDPkMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
