"""add_is_verified_to_api_keys

Revision ID: a1b2c3d4e5f6
Revises: 376ee6949ed8
Create Date: 2026-07-19 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '376ee6949ed8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add is_verified column to api_keys table.

    Existing rows are backfilled to True because every key stored in the DB
    was already verified by the live provider check at the time it was saved.
    New rows default to False and must pass a live check before being set True.
    """
    # Add the column with a server default of 0 (False) for new rows
    op.add_column(
        'api_keys',
        sa.Column('is_verified', sa.Boolean(), nullable=False, server_default=sa.text('0'))
    )
    # Backfill all existing rows to True — they were verified at insert time
    op.execute("UPDATE api_keys SET is_verified = 1 WHERE is_verified = 0")


def downgrade() -> None:
    """Remove is_verified column from api_keys table."""
    op.drop_column('api_keys', 'is_verified')
