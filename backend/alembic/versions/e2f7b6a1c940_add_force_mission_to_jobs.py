"""Persist the explicit Mission Mode routing choice on queued jobs."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2f7b6a1c940"
down_revision: Union[str, Sequence[str], None] = "d90af0c41b27"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("mission_jobs"):
        # MissionJob was historically created by SQLAlchemy create_all during
        # application startup, not by the initial Alembic revision. Create it
        # here so a fresh Render database can run `alembic upgrade head` before
        # the application process starts.
        op.create_table(
            "mission_jobs",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("session_id", sa.String(length=128), nullable=False),
            sa.Column("query", sa.Text(), nullable=False),
            sa.Column("model", sa.String(length=200), nullable=False),
            sa.Column("encrypted_api_keys", sa.Text(), nullable=True),
            sa.Column("force_mission", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
            sa.Column("events", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("result", sa.Text(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_mission_jobs_user_id", "mission_jobs", ["user_id"], unique=False)
        op.create_index("ix_mission_jobs_session_id", "mission_jobs", ["session_id"], unique=False)
        op.create_index("ix_mission_jobs_status", "mission_jobs", ["status"], unique=False)
    elif "force_mission" not in {column["name"] for column in inspector.get_columns("mission_jobs")}:
        op.add_column(
            "mission_jobs",
            sa.Column("force_mission", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("mission_jobs") and "force_mission" in {
        column["name"] for column in inspector.get_columns("mission_jobs")
    }:
        op.drop_column("mission_jobs", "force_mission")
