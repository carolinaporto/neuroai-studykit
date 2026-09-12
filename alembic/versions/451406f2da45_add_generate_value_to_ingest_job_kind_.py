"""add generate value to ingest_job_kind enum

Revision ID: 451406f2da45
Revises: 8cef87849693
Create Date: 2026-09-12 10:30:19.923422

M3 added `IngestJobKind.generate` in Python but never migrated the Postgres enum type —
autogenerate does not detect values added to an existing enum, so this had to be written
by hand. Confirmed by an audit comparing every enum in packages/db/models.py against
`pg_enum` on the running db: `ingest_job_kind` was the only mismatch (missing 'generate');
`ingest_job_status`, `user_role`, `source_kind`, `source_status`, `item_type`, `item_bloom`,
and `item_status` all matched.
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '451406f2da45'
down_revision: str | Sequence[str] | None = '8cef87849693'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE ingest_job_kind ADD VALUE IF NOT EXISTS 'generate'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE; removing an enum value requires rebuilding
    # the type (rename, create new, cast every column, drop old) and it's not worth the risk
    # for a downgrade path nothing currently relies on. No-op, same as accepted practice for
    # this exact situation.
    pass
