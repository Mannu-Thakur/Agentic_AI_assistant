import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.sql import func

from app.core.database import Base


class ToolApproval(Base):
    """One-time authorization for a potentially mutating remote MCP call."""

    __tablename__ = "tool_approvals"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    chat_id = Column(String(36), ForeignKey("chats.id", ondelete="CASCADE"), nullable=True, index=True)
    tool_name = Column(String(255), nullable=False)
    arguments = Column(JSON, nullable=False)
    server_name = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False, default="pending", index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    result = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
