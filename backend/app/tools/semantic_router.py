"""
app/tools/semantic_router.py — Semantic Tool Router & Tool Selection Engine.

Computes semantic vector similarity between user queries and registered tool descriptions
(local tools, Web MCP tools, remote MCP tools). Filters and ranks tools deterministically
to maximize tool-selection accuracy and eliminate tool-call hallucinations.
"""

import math
import logging
from typing import Dict, Any, List, Optional, Tuple
from app.embeddings.embedding_service import EmbeddingService

logger = logging.getLogger("app.tools.semantic_router")


def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Computes cosine similarity between two float vectors."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot / (norm1 * norm2)


# Domain-specific intent & keyword heuristics for fallback matching
_SYNONYM_MAP = {
    "weather": ["tavily_search", "web_search"],
    "news": ["tavily_search", "web_search"],
    "search": ["tavily_search", "web_search"],
    "today": ["tavily_search", "web_search"],
    "calculate": ["calculate", "python_sandbox"],
    "math": ["calculate", "python_sandbox"],
    "compute": ["calculate", "python_sandbox"],
    "fetch": ["web_fetch", "web_extract"],
    "webpage": ["web_fetch", "web_extract"],
    "url": ["web_fetch", "web_extract"],
    "link": ["web_fetch", "web_extract"],
    "spent": ["add_expense", "get_expenses"],
    "lunch": ["add_expense", "get_expenses"],
    "dinner": ["add_expense", "get_expenses"],
    "expense": ["add_expense", "get_expenses", "summarize_expenses"],
    "record": ["add_expense", "create_reminder"],
}


class SemanticToolRouter:
    """
    Semantic Tool Selection Engine.
    Maintains cached embeddings for registered tool descriptions and performs
    real-time vector similarity scoring against user queries.
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(SemanticToolRouter, cls).__new__(cls, *args, **kwargs)
            cls._instance._tool_embeddings_cache: Dict[str, List[float]] = {}
        return cls._instance

    async def get_tool_embedding(self, tool_name: str, tool_description: str, api_key: Optional[str] = None) -> List[float]:
        """
        Retrieves or generates vector embedding for a tool description.
        """
        cache_key = f"{tool_name}:{tool_description}"
        if cache_key in self._tool_embeddings_cache:
            return self._tool_embeddings_cache[cache_key]

        text_to_embed = f"Tool: {tool_name}. Description: {tool_description}"
        try:
            vec = await EmbeddingService.get_embedding(text_to_embed, api_key=api_key)
            if vec and isinstance(vec, list):
                self._tool_embeddings_cache[cache_key] = vec
                return vec
        except Exception as exc:
            logger.warning(f"[SemanticToolRouter] Failed to get embedding for tool '{tool_name}': {exc}")

        return []

    async def rank_tools_by_relevance(
        self,
        query: str,
        tool_declarations: List[Dict[str, Any]],
        api_key: Optional[str] = None,
    ) -> List[Tuple[Dict[str, Any], float]]:
        """
        Ranks tool declarations by semantic relevance score against the query.
        Returns a list of (tool_declaration, score) tuples sorted in descending order of score.
        """
        if not query or not tool_declarations:
            return []

        try:
            query_vec = await EmbeddingService.get_embedding(query, api_key=api_key)
        except Exception as exc:
            logger.warning(f"[SemanticToolRouter] Failed to embed query '{query[:40]}': {exc}")
            query_vec = []

        scored_tools: List[Tuple[Dict[str, Any], float]] = []
        query_words = set(w.strip("?,!.:;") for w in query.lower().split())

        for tool in tool_declarations:
            t_name = tool.get("name", "")
            t_desc = tool.get("description", "")
            
            sim_score = 0.0
            if query_vec:
                tool_vec = await self.get_tool_embedding(t_name, t_desc, api_key=api_key)
                if tool_vec:
                    sim_score = _cosine_similarity(query_vec, tool_vec)

            # Domain keyword & synonym score calculation
            text_combo = f"{t_name} {t_desc}".lower()
            keyword_matches = sum(1 for w in query_words if len(w) > 2 and w in text_combo)
            synonym_matches = 0
            for w in query_words:
                if w in _SYNONYM_MAP and t_name in _SYNONYM_MAP[w]:
                    synonym_matches += 1

            keyword_score = min(keyword_matches * 0.20 + synonym_matches * 0.40, 0.90)

            final_score = max(sim_score, keyword_score)
            scored_tools.append((tool, round(final_score, 4)))

        scored_tools.sort(key=lambda x: x[1], reverse=True)
        return scored_tools

    async def select_relevant_tools(
        self,
        query: str,
        tool_declarations: List[Dict[str, Any]],
        top_k: int = 5,
        min_threshold: float = 0.15,
        api_key: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Selects top-k semantically relevant tool declarations meeting the minimum similarity threshold.
        """
        if not tool_declarations:
            return []

        ranked = await self.rank_tools_by_relevance(query, tool_declarations, api_key=api_key)
        
        filtered = [t for t, score in ranked if score >= min_threshold]
        if not filtered and ranked:
            filtered = [ranked[0][0]]

        selected = filtered[:top_k]
        logger.info(
            f"[SemanticToolRouter] Query '{query[:50]}' matched {len(selected)}/{len(tool_declarations)} tools "
            f"(top: {[t['name'] for t in selected]})"
        )
        return selected


semantic_router = SemanticToolRouter()
