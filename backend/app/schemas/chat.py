from typing import Optional, List, Any, Dict
from pydantic import BaseModel, ConfigDict
from datetime import datetime

class ToolCallSchema(BaseModel):
  name: str
  args: Dict[str, Any]
  result: Optional[str] = None
  status: str  # running, completed, failed

class DeveloperMetricsSchema(BaseModel):
  model_used: Optional[str] = "gemini-2.5-flash"
  latency_ms: Optional[int] = 0
  tokens_input: Optional[int] = 0
  tokens_output: Optional[int] = 0
  cost_estimate: Optional[float] = 0.0
  confidence_score: Optional[float] = 1.0
  memory_hits: Optional[int] = 0
  search_queries: Optional[List[str]] = None
  chunks_used: Optional[int] = None
  steps: Optional[List[str]] = None
  retrieved_context: Optional[List[Dict[str, Any]]] = None
  source_documents: Optional[List[Dict[str, Any]]] = None

  model_config = ConfigDict(extra="allow", from_attributes=True)

class ImageAttachment(BaseModel):
  """Inline base64-encoded image from the frontend."""
  base64: str
  mimeType: str

class MessageCreate(BaseModel):
  content: str
  model: str
  parent_message_id: Optional[str] = None
  images: Optional[List['ImageAttachment']] = []

class MessageOut(BaseModel):
  id: str
  chat_id: str
  parent_id: Optional[str] = None
  role: str
  content: str
  tool_calls: Optional[List[ToolCallSchema]] = None
  developer_metrics: Optional[DeveloperMetricsSchema] = None
  images: Optional[List[ImageAttachment]] = None  # Persisted inline images
  created_at: datetime

  model_config = ConfigDict(from_attributes=True)

class ChatCreate(BaseModel):
  title: Optional[str] = "New Chat"

class ChatUpdate(BaseModel):
  title: Optional[str] = None

class ChatOut(BaseModel):
  id: str
  user_id: str
  title: str
  is_pinned: bool
  is_favorite: bool
  is_shared: bool
  share_id: Optional[str] = None
  is_live_share: bool = False
  created_at: datetime
  updated_at: datetime

  model_config = ConfigDict(from_attributes=True)

class ChatShareUpdate(BaseModel):
  is_shared: bool
  is_live: Optional[bool] = False

class SharedMessageOut(BaseModel):
  id: str
  role: str
  content: str
  created_at: datetime

  model_config = ConfigDict(from_attributes=True)

class SharedChatOut(BaseModel):
  id: str
  title: str
  is_live_share: bool = False
  messages: List[SharedMessageOut]

