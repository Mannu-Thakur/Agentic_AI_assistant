"""
app/providers/base.py — Abstract base class for all LLM provider adapters.

All concrete providers (GeminiProvider, GroqProvider, OpenRouterProvider,
OpenAIProvider) must implement generate() and generate_stream().

Backward compatibility
───────────────────────
provider_name and capabilities are provided as class-level attributes with
sensible defaults so that any existing provider subclass that does not
override them continues to work without modification.
"""

from abc import ABC, abstractmethod
from typing import AsyncGenerator, Dict, Any, List, Optional, Set


class BaseLLMProvider(ABC):

    # ── Optional class-level metadata ─────────────────────────────────────────
    # Subclasses should override these.  Defaults are safe no-ops.
    provider_name: str       = "unknown"
    capabilities:  Set[str]  = frozenset({"text", "streaming"})

    # ── Core abstract interface ───────────────────────────────────────────────

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

        Returns a dict with keys:
          text         : str       — generated text
          input_tokens : int       — prompt token count
          output_tokens: int       — completion token count
          model        : str       — model ID used
          tool_calls   : list[dict]— parsed tool calls (empty list if none)
        """

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
        Stream the response as an async generator.

        Yields dicts with keys:
          event : "chunk"      → text : str
          event : "tool_calls" → tool_calls : list[dict]
          event : "metrics"    → metrics : dict
        """
