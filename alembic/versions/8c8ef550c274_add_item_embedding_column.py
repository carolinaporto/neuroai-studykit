"""add item embedding column

Revision ID: 8c8ef550c274
Revises: f1da6e62b4db
Create Date: 2026-09-22 22:37:23.473541

"""
from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '8c8ef550c274'
down_revision: str | Sequence[str] | None = 'f1da6e62b4db'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('item', sa.Column('embedding', pgvector.sqlalchemy.Vector(1536), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('item', 'embedding')
