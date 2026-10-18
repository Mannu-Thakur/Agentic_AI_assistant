"""Repair missing document-ingestion progress columns.

Some deployed databases can report the prior revision as applied while still
missing one or more columns (for example after a partial/manual schema repair).
This revision reconciles only the missing columns and preserves existing data.

Revision ID: d90af0c41b27
Revises: c7a9e3d1b5f2
Create Date: 2026-10-18 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d90af0c41b27"
down_revision: Union[str, Sequence[str], None] = "c7a9e3d1b5f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("documents"):
        raise RuntimeError("Cannot repair document progress columns: documents table is missing")

    existing_columns = {column["name"] for column in inspector.get_columns("documents")}
    missing_columns = (
        ("stage", sa.Column("stage", sa.String(length=40), nullable=False, server_default="queued")),
        ("progress", sa.Column("progress", sa.Integer(), nullable=False, server_default="0")),
        ("chunk_count", sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0")),
        ("processing_started_at", sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True)),
    )

    for name, column in missing_columns:
        if name not in existing_columns:
            op.add_column("documents", column)


def downgrade() -> None:
    # The parent revision owns these columns. Dropping any of them here could
    # remove data from a database that already had the repaired schema.
    pass
