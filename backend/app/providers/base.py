from abc import ABC, abstractmethod
from typing import AsyncGenerator, Dict, Any, List, Optional

class BaseLLMProvider(ABC):
  @abstractmethod
  async def generate(
      self,
      messages: List[Dict[str, str]],
      model: str,
      temperature: float = 0.7,
      max_tokens: int = 2048,
      tools: Optional[List[Dict[str, Any]]] = None,
      api_key: Optional[str] = None,
  ) -> Dict[str, Any]:
    """
    Generate a complete text response.
    Returns a dict with keys: 'text', 'input_tokens', 'output_tokens', 'model', 'tool_calls'
    """
    pass

  @abstractmethod
  async def generate_stream(
      self,
      messages: List[Dict[str, str]],
      model: str,
      temperature: float = 0.7,
      max_tokens: int = 2048,
      tools: Optional[List[Dict[str, Any]]] = None,
      api_key: Optional[str] = None,
  ) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Stream the response.
    Yields dicts with keys: 'event' ('chunk' or 'metrics'), 'text' (only for chunk), 'metrics' (only for metrics)
    """
    pass
