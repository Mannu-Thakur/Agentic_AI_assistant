"""
benchmarks/scorers/__init__.py — Registry of capability scorers.
"""

from __future__ import annotations

from typing import Any, Callable

from benchmarks.scorers.llm_scorer import score_llm_qa
from benchmarks.scorers.mcp_scorer import score_mcp_tool
from benchmarks.scorers.rag_scorer import score_rag
from benchmarks.scorers.self_rag_scorer import score_self_rag
from benchmarks.scorers.crag_scorer import score_crag
from benchmarks.scorers.web_search_scorer import score_web_search
from benchmarks.scorers.agentic_scorer import score_agentic

SCORER_REGISTRY: dict[str, Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]] = {
    "llm":      score_llm_qa,
    "mcp":      score_mcp_tool,
    "rag":      score_rag,
    "self_rag": score_self_rag,
    "crag":     score_crag,
    "web":      score_web_search,
    "agentic":  score_agentic,
}

__all__ = [
    "SCORER_REGISTRY",
    "score_llm_qa",
    "score_mcp_tool",
    "score_rag",
    "score_self_rag",
    "score_crag",
    "score_web_search",
    "score_agentic",
]
