from typing import TypedDict, List, Dict, Any, Optional
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
  messages: List[BaseMessage]
  active_model: str
  user_id: str
  chat_id: str
  retrieved_documents: List[Dict[str, Any]]
  metrics: Dict[str, Any]
  response_text: str
  tool_calls: Optional[List[Dict[str, Any]]]
  steps: List[str]

