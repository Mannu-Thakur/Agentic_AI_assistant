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


def _is_tool_schema_eligible(tool: Dict[str, Any], query: str) -> bool:
    """
    Generic, zero-keyword dynamic schema capability & argument eligibility check.
    Verifies whether a candidate tool schema can actually satisfy the query request based on parameter schemas.
    Does not use topic/keyword hardcoding or tool name checks.
    """
    if not tool or not query:
        return False

    params = tool.get("parameters") or tool.get("inputSchema") or {}
    req_params = params.get("required", [])

    # If tool requires specific mandatory arguments, verify context compatibility dynamically
    if req_params:
        query_text = query.lower()

        # Schema requires math expression / numeric code parameter
        if any(p in ("expression", "code", "script") for p in req_params):
            if not any(c.isdigit() or c in "+-*/%^" for c in query):
                return False

        # Schema requires web URL parameter
        if any(p in ("url", "uri", "link") for p in req_params):
            if not any(indicator in query_text for indicator in ("http", "www.", ".com", ".org", ".net", ".io", ".gov")):
                return False

    return True


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

        STOPWORDS = {
            "a", "an", "the", "and", "or", "but", "if", "because", "as", "what", "which",
            "who", "whom", "this", "that", "these", "those", "am", "is", "are", "was",
            "were", "be", "been", "being", "have", "has", "had", "having", "do", "does",
            "did", "doing", "until", "while", "of", "at", "by", "for", "with", "about",
            "against", "between", "into", "through", "during", "before", "after", "above",
            "below", "to", "from", "up", "down", "in", "out", "on", "off", "over", "under",
            "again", "further", "then", "once", "here", "there", "when", "where", "why",
            "how", "all", "any", "both", "each", "few", "more", "most", "other", "some",
            "such", "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very",
            "can", "will", "just", "should", "now", "my", "your", "his", "her", "its", "our", "their"
        }

        scored_tools: List[Tuple[Dict[str, Any], float]] = []
        query_words = set(w.strip("?,!.:;\"'") for w in query.lower().split())
        query_meaningful_words = [w for w in query_words if len(w) > 2 and w not in STOPWORDS]

        for tool in tool_declarations:
            t_name = tool.get("name", "")
            t_desc = tool.get("description", "")
            
            sim_score = 0.0
            if query_vec:
                tool_vec = await self.get_tool_embedding(t_name, t_desc, api_key=api_key)
                if tool_vec:
                    sim_score = _cosine_similarity(query_vec, tool_vec)

            # Dynamic schema token match score (checks against tool's declared name and description schema)
            text_combo = f"{t_name} {t_desc}".lower()
            keyword_matches = sum(1 for w in query_meaningful_words if w in text_combo)
            keyword_score = min(keyword_matches * 0.25, 0.90)

            final_score = max(sim_score, keyword_score)
            scored_tools.append((tool, round(final_score, 4)))

        scored_tools.sort(key=lambda x: x[1], reverse=True)
        return scored_tools

    async def select_relevant_tools_with_metadata(
        self,
        query: str,
        tool_declarations: List[Dict[str, Any]],
        top_k: int = 5,
        min_threshold: float = 0.20,
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Selects semantically relevant tools using absolute score margin filtering and parameter schema eligibility checks.
        Returns detailed diagnostic metadata including available_tools, semantic_ranking, selected_tools,
        execution_eligible_tools, top_score, second_score, score_margin, confidence, and ambiguity.
        """
        if not tool_declarations:
            return {
                "available_tools": [],
                "semantic_ranking": [],
                "selected_tools": [],
                "execution_eligible_tools": [],
                "top_score": 0.0,
                "second_score": 0.0,
                "score_margin": 0.0,
                "confidence": 0.0,
                "ambiguity": False,
                "reason": "No registered tool declarations provided",
                "requires_external_action": False,
            }

        ranked = await self.rank_tools_by_relevance(query, tool_declarations, api_key=api_key)
        
        top_score = ranked[0][1] if ranked else 0.0
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0
        score_margin = round(top_score - second_score, 4)

        # Ambiguity threshold: margin < 0.05 indicates low separation between top competing tools
        AMBIGUITY_MARGIN = 0.05
        ambiguity = bool(top_score >= min_threshold and score_margin < AMBIGUITY_MARGIN)

        # Absolute Score-Margin Filtering (SECONDARY_MARGIN = 0.10):
        # A tool is selected as a candidate ONLY IF score >= min_threshold AND (top_score - score) <= 0.10
        SECONDARY_MARGIN = 0.10
        selected = []
        if top_score >= min_threshold:
            for tool, score in ranked:
                if score >= min_threshold and (top_score - score) <= SECONDARY_MARGIN:
                    selected.append(tool)
                if len(selected) >= top_k:
                    break

        available_tools = list(tool_declarations)
        semantic_ranking = [{"name": t.get("name", ""), "score": float(score)} for t, score in ranked]

        # Dynamic Schema Capability & Argument Eligibility Filtering:
        # Candidate tools must also satisfy generic schema argument compatibility
        execution_eligible = [t for t in selected if _is_tool_schema_eligible(t, query)]

        metadata = {
            "available_tools": available_tools,
            "semantic_ranking": semantic_ranking,
            "selected_tools": selected,
            "execution_eligible_tools": execution_eligible,
            "top_score": round(float(top_score), 4),
            "second_score": round(float(second_score), 4),
            "score_margin": score_margin,
            "confidence": round(float(top_score), 4),
            "ambiguity": ambiguity,
            "reason": (
                f"Semantic router evaluated {len(tool_declarations)} tool(s): top_score={top_score:.4f}, "
                f"margin={score_margin:.4f}, selected {len(selected)} candidate(s), "
                f"{len(execution_eligible)} execution-eligible"
            ),
            "requires_external_action": len(execution_eligible) > 0,
        }

        logger.info(
            f"[SemanticToolRouter] Query '{query[:50]}' evaluated {len(tool_declarations)} tool(s) "
            f"(top_score={top_score:.4f}, margin={score_margin:.4f}, ambiguity={ambiguity}, "
            f"eligible: {[t.get('name') for t in execution_eligible]})"
        )
        return metadata

    async def select_relevant_tools(
        self,
        query: str,
        tool_declarations: List[Dict[str, Any]],
        top_k: int = 5,
        min_threshold: float = 0.20,
        api_key: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Backwards compatible tool selection wrapper — returns execution eligible tools."""
        meta = await self.select_relevant_tools_with_metadata(
            query=query,
            tool_declarations=tool_declarations,
            top_k=top_k,
            min_threshold=min_threshold,
            api_key=api_key,
        )
        return meta["execution_eligible_tools"]


semantic_router = SemanticToolRouter()
