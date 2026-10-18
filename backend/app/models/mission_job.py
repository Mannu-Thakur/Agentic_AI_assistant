"""Durable state for long-running multi-agent missions.

The work itself remains in the application worker, but the job envelope,
progress stream, terminal outcome, and any temporary provider credentials are
persisted.  Credentials are encrypted before this model is written.
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.sql import func

from app.core.database import Base


class MissionJob(Base):
    __tablename__ = "mission_jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(String(128), nullable=False, index=True)
    query = Column(Text, nullable=False)
    model = Column(String(200), nullable=False)
    force_mission = Column(Boolean, nullable=False, default=False, server_default="false")
    encrypted_api_keys = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="queued", index=True)
    events = Column(JSON, nullable=False, default=list)
    result = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
