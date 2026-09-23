"""add clerk_user_id to user

Revision ID: 3a52ba6df55f
Revises: 8c8ef550c274
Create Date: 2026-09-22 23:25:25.861724

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '3a52ba6df55f'
down_revision: str | Sequence[str] | None = '8c8ef550c274'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT_NAME = 'uq_user_clerk_user_id'


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('user', sa.Column('clerk_user_id', sa.String(), nullable=True))
    op.create_unique_constraint(CONSTRAINT_NAME, 'user', ['clerk_user_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(CONSTRAINT_NAME, 'user', type_='unique')
    op.drop_column('user', 'clerk_user_id')
