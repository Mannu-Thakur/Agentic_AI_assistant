import uuid
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

# ─────────────────────────────────────────────────────────────────────────────
#  Memory categories — Phase 3 multi-category upgrade
#
#  user_profile  — name, age, occupation, location, background facts
#  preference    — technology, language, style, or workflow preferences
#  goal          — current objectives the user is working toward
#  long_term     — durable facts that persist across sessions indefinitely
#  short_term    — temporary info relevant only in the current project scope
#  session       — ephemeral facts captured this session (low TTL)
#  project       — project-scoped information (multi-tenant workspace facts)
#  topic         — interests and knowledge domains
#  fact          — catch-all for any other factual statement
# ─────────────────────────────────────────────────────────────────────────────

MEMORY_CATEGORIES = frozenset({
    "user_profile",
    "preference",
    "goal",
    "long_term",
    "short_term",
    "session",
    "project",
    "topic",
    "fact",
})


class Memory(Base):
    __tablename__ = "memories"

    id               = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id          = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Phase 1/2 fields (backward compatible)
    category         = Column(String(50), nullable=False, default="fact")
    content          = Column(Text, nullable=False)
    importance_score = Column(Integer, default=5)       # 1–10
    created_at       = Column(DateTime(timezone=True), server_default=func.now())
    updated_at       = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    # Phase 3 additions
    expires_at       = Column(DateTime(timezone=True), nullable=True)   # null = never expires
    project_id       = Column(String(128), nullable=True, index=True)   # workspace isolation
    session_id       = Column(String(128), nullable=True, index=True)   # session scoping
    confidence       = Column(Float, default=1.0)                       # 0.0–1.0 extraction confidence

    # Relationships
    user = relationship("User", back_populates="memories")
