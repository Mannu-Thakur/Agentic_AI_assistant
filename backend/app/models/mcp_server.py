import uuid
from sqlalchemy import Column, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from app.core.database import Base

class RemoteMcpServer(Base):
    __tablename__ = "remote_mcp_servers"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    name = Column(String(255), nullable=False)
    url = Column(String(512), nullable=False)
    transport_type = Column(String(50), default="http_jsonrpc")  # http_jsonrpc | http_sse
    auth_header = Column(Text, nullable=True)  # Optional Bearer token or Custom auth header value
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
