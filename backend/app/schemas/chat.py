from typing import Optional, List, Any, Dict
from pydantic import BaseModel, ConfigDict
from datetime import datetime

class ToolCallSchema(BaseModel):
  name: str
  args: Dict[str, Any]
  result: Optional[str] = None
  status: str  # running, completed, failed

class DeveloperMetricsSchema(BaseModel):
  model_used: str
  latency_ms: int
  tokens_input: int
  tokens_output: int
  cost_estimate: float
  confidence_score: float
  memory_hits: int
  search_queries: Optional[List[str]] = None
  chunks_used: Optional[int] = None

class MessageCreate(BaseModel):
  content: str
  model: str
  parent_message_id: Optional[str] = None

class MessageOut(BaseModel):
  id: str
  chat_id: str
  parent_id: Optional[str] = None
  role: str
  content: str
  tool_calls: Optional[List[ToolCallSchema]] = None
  developer_metrics: Optional[DeveloperMetricsSchema] = None
  created_at: datetime

  model_config = ConfigDict(from_attributes=True)

class ChatCreate(BaseModel):
  title: Optional[str] = "New Chat"

class ChatOut(BaseModel):
  id: str
  user_id: str
  title: str
  is_pinned: bool
  is_favorite: bool
  is_shared: bool
  share_id: Optional[str] = None
  created_at: datetime
  updated_at: datetime

  model_config = ConfigDict(from_attributes=True)

class ChatShareUpdate(BaseModel):
  is_shared: bool

class SharedMessageOut(BaseModel):
  id: str
  role: str
  content: str
  created_at: datetime

  model_config = ConfigDict(from_attributes=True)

class SharedChatOut(BaseModel):
  id: str
  title: str
  messages: List[SharedMessageOut]

