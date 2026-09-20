"""
app/routing/complexity_analyzer.py — Deterministic query complexity analyzer.

Scores incoming queries on multiple complexity dimensions:
  - Token length (longer = more complex)
  - Multi-question detection
  - Analytical/reasoning keyword density
  - Document-intensive indicators
  - Graph/relationship reasoning needs
  - Code generation indicators
  - Temporal/financial analysis needs

Returns a ComplexityScore with tier recommendation: "slm" | "llm-medium" | "llm-strong"

This is NOT an ML model — it is a transparent, deterministic rule-based scorer.
Routing decisions are logged so they can be used to train an ML router later.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional


# ── Complexity signal keyword sets ────────────────────────────────────────────

_SIMPLE_KEYWORDS = {
    "what is", "define", "explain", "tell me about", "what does",
    "who is", "where is", "when did", "how do you spell", "synonym",
    "capital of", "meaning of",
}

_MEDIUM_KEYWORDS = {
    "compare", "difference between", "summarize", "how does",
    "what are the steps", "explain how", "describe",
    "according to", "based on", "in the document", "from the file",
    "list all", "what are the main", "find all", "search for",
}

_COMPLEX_KEYWORDS = {
    "analyze", "investigate", "identify inconsistencies", "assess",
    "evaluate", "compare and contrast", "what if", "implications of",
    "root cause", "anomaly", "fraud", "risk", "compliance",
    "multi-step", "across multiple", "synthesize", "critically evaluate",
    "calculate", "financial", "forecast", "predict", "model",
    "relationship between", "how are .* connected", "network of",
    "write code", "implement", "debug", "generate a function",
    "investigate the claim", "warranty analysis", "insurance",
}

_GRAPH_KEYWORDS = {
    "who owns", "works for", "relationship", "connected to", "supplier",
    "purchased from", "caused by", "claimed on", "depends on",
    "organization chart", "network", "knowledge graph",
}

_VISION_KEYWORDS = {
    "image", "photo", "picture", "diagram", "chart", "screenshot", "scan",
}


@dataclass
class ComplexityScore:
    """Result of the complexity analysis."""
    query: str
    recommended_tier: str           # "slm" | "llm-medium" | "llm-strong"
    complexity_score: float         # 0.0-1.0
    confidence: float               # 0.0-1.0 in the tier recommendation
    signals: Dict[str, Any]        # individual signal values
    reasoning: str                  # human-readable explanation
    needs_graph: bool               # True if query benefits from GraphRAG
    needs_vision: bool              # True if query involves image reasoning
    estimated_tokens: int           # rough input token estimate


def analyze_complexity(query: str, context: Optional[Dict[str, Any]] = None) -> ComplexityScore:
    """
    Analyze query complexity and recommend a model tier.

    Args:
        query: The user's question
        context: Optional context dict with keys:
            - intent: str (from classify_intent)
            - has_images: bool
            - document_count: int (number of uploaded docs)
            - is_private_doc_query: bool
            - message_history_length: int

    Returns:
        ComplexityScore with tier recommendation
    """
    ctx = context or {}
    query_lower = query.lower()
    signals: Dict[str, Any] = {}

    # ── Signal 1: Query length ────────────────────────────────────────────────
    word_count = len(query.split())
    signals["word_count"] = word_count
    length_score = min(1.0, word_count / 80)  # 80+ words = max complexity

    # ── Signal 2: Multi-question detection ───────────────────────────────────
    question_marks = query.count("?")
    has_multi_question = question_marks > 1 or any(
        kw in query_lower for kw in ["also", "additionally", "furthermore", "and also"]
    )
    signals["multi_question"] = has_multi_question

    # ── Signal 3: Complex keyword density ─────────────────────────────────────
    complex_hits = sum(
        1 for kw in _COMPLEX_KEYWORDS if kw in query_lower
    )
    medium_hits = sum(
        1 for kw in _MEDIUM_KEYWORDS if kw in query_lower
    )
    simple_hits = sum(
        1 for kw in _SIMPLE_KEYWORDS if kw in query_lower
    )
    signals["complex_keywords"] = complex_hits
    signals["medium_keywords"] = medium_hits
    signals["simple_keywords"] = simple_hits

    # ── Signal 4: Graph reasoning need ────────────────────────────────────────
    graph_hits = sum(1 for kw in _GRAPH_KEYWORDS if kw in query_lower)
    needs_graph = graph_hits > 0
    signals["graph_reasoning"] = graph_hits

    # ── Signal 5: Vision ──────────────────────────────────────────────────────
    has_images = ctx.get("has_images", False)
    vision_hits = sum(1 for kw in _VISION_KEYWORDS if kw in query_lower)
    needs_vision = has_images or vision_hits > 0
    signals["vision"] = needs_vision

    # ── Signal 6: Intent-based boosts ─────────────────────────────────────────
    intent = ctx.get("intent", "NORMAL_CHAT")
    intent_complexity = {
        "NORMAL_CHAT": 0.1,
        "MEMORY_WRITE": 0.05,
        "WEB_SEARCH": 0.4,
        "NEWS": 0.3,
        "DOCUMENT_QA": 0.5,
        "VISION": 0.5,
        "CODE_EXECUTION": 0.65,
        "MCP_TOOL": 0.55,
        "FINANCE": 0.75,
        "MATH": 0.6,
        "COMPLEX": 0.85,
    }.get(intent, 0.3)
    signals["intent_complexity"] = intent_complexity

    # ── Signal 7: Document count ───────────────────────────────────────────────
    doc_count = ctx.get("document_count", 0)
    doc_score = min(0.5, doc_count * 0.1)  # more docs = more complex context
    signals["document_count"] = doc_count

    # ── Composite score ───────────────────────────────────────────────────────
    complexity_score = (
        0.15 * length_score +
        0.20 * intent_complexity +
        0.20 * min(1.0, complex_hits / 3) +
        0.10 * min(1.0, medium_hits / 3) +
        0.10 * (1.0 if has_multi_question else 0.0) +
        0.10 * min(1.0, graph_hits / 2) +
        0.10 * doc_score +
        0.05 * (1.0 if needs_vision else 0.0)
    )
    complexity_score = max(0.0, min(1.0, complexity_score))

    # ── Tier recommendation ───────────────────────────────────────────────────
    if complexity_score < 0.30 and not needs_vision:
        recommended_tier = "slm"
        confidence = 0.85
        reasoning = f"Simple query (score={complexity_score:.2f}): short, few keywords, low intent complexity."
    elif complexity_score < 0.60:
        recommended_tier = "llm-medium"
        confidence = 0.80
        reasoning = f"Medium complexity (score={complexity_score:.2f}): document QA, web search, or moderate reasoning."
    else:
        recommended_tier = "llm-strong"
        confidence = 0.82
        reasoning = f"High complexity (score={complexity_score:.2f}): multi-step analysis, graph reasoning, code, or finance."

    # Force vision-capable model for image queries
    if needs_vision and recommended_tier == "slm":
        recommended_tier = "llm-medium"
        reasoning += " Upgraded: vision capability required."

    estimated_tokens = word_count * 4 + 500  # rough estimate with system prompt overhead

    return ComplexityScore(
        query=query,
        recommended_tier=recommended_tier,
        complexity_score=complexity_score,
        confidence=confidence,
        signals=signals,
        reasoning=reasoning,
        needs_graph=needs_graph,
        needs_vision=needs_vision,
        estimated_tokens=estimated_tokens,
    )
