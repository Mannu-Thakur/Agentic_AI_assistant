"""add document ingestion progress fields

Revision ID: c7a9e3d1b5f2
Revises: a1b2c3d4e5f6
Create Date: 2026-10-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c7a9e3d1b5f2"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("stage", sa.String(length=40), nullable=False, server_default="queued"),
    )
    op.add_column(
        "documents",
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "documents",
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "documents",
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "processing_started_at")
    op.drop_column("documents", "chunk_count")
    op.drop_column("documents", "progress")
    op.drop_column("documents", "stage")
