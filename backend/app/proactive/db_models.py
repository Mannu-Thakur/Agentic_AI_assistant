"""
app/proactive/db_models.py — SQLAlchemy ORM model for persisted proactive alerts.

ProactiveAlertRecord stores every generated alert permanently so:
  1. The frontend can fetch the full unread/history list on load.
  2. Deduplication queries can be run without an in-memory set.
  3. Users can mark alerts as read / dismiss them.

Schema is added via run_schema_migrations() in app/core/database.py on startup
— no manual Alembic migration needed.
"""
from __future__ import annotations

import time
import uuid
from sqlalchemy import Column, String, Float, Boolean, Text, JSON, Index
from app.core.database import Base


class ProactiveAlertRecord(Base):
    """Persisted proactive intelligence alert."""

    __tablename__ = "proactive_alerts"

    id           = Column(String(36),  primary_key=True, default=lambda: str(uuid.uuid4()))
    alert_id     = Column(String(64),  nullable=False, index=True)   # md5 dedup key
    user_id      = Column(String(36),  nullable=False, index=True)
    alert_type   = Column(String(64),  nullable=False)
    severity     = Column(String(20),  nullable=False, default="info")
    title        = Column(String(200), nullable=False)
    message      = Column(Text,        nullable=False)
    confidence   = Column(Float,       nullable=False, default=0.9)
    entity_key   = Column(String(256), nullable=True,  default="")
    source_doc_ids = Column(JSON,      nullable=True,  default=list)
    extra_meta   = Column(JSON,        nullable=True,  default=dict)
    is_read      = Column(Boolean,     nullable=False, default=False)
    created_at   = Column(Float,       nullable=False, default=time.time)

    __table_args__ = (
        Index("ix_proactive_user_created", "user_id", "created_at"),
        Index("ix_proactive_dedup",        "user_id", "alert_id", "created_at"),
        Index("ix_proactive_unread",       "user_id", "is_read"),
    )
