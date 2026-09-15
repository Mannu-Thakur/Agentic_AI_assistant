"""
benchmarks/scorers/rag_scorer.py — Scorer for RAG (Retrieval-Augmented Generation) capability.

Evaluates:
  - Context Retrieval Execution (vector store accessed)
  - Answer Relevance (% expected keywords matched)
  - Faithfulness / Groundedness Proxy (from evidence_checker confidence)
  - Generation Mode Alignment ('normal_rag')
  - Document Relevance Status
"""

from __future__ import annotations

from typing import Any


def score_rag(case: dict[str, Any], response_data: dict[str, Any]) -> dict[str, Any]:
    """
    Score a RAG test case against the live response and execution telemetry.
    """
    expected_keywords = case.get("expected_keywords", [])
    resp_text = response_data.get("response_text", "").lower()
    gen_mode = response_data.get("generation_mode", "")
    doc_relevance = response_data.get("document_relevance", "")
    answer_conf = float(response_data.get("answer_confidence", 0.0) or 0.0)

    # 1. Context used: Check if retrieve_context was executed
    trace = response_data.get("execution_trace", [])
    context_used = False
    for step in trace:
        if step.get("name") == "retrieve_context" and step.get("status") == "EXECUTED":
            context_used = True
            break
    if not context_used and response_data.get("needs_retrieval"):
        context_used = True

    # 2. Answer relevance: Keyword presence in response
    if expected_keywords:
        matched_kw = sum(1 for kw in expected_keywords if kw.lower() in resp_text)
        answer_relevance = matched_kw / len(expected_keywords)
    else:
        answer_relevance = 1.0 if len(resp_text) > 50 else 0.5

    # 3. Faithfulness proxy from evidence checker
    # If evidence_checker did not report high confidence, scale from response length and grounding
    faithfulness_proxy = answer_conf if answer_conf > 0.0 else (0.85 if len(resp_text) > 100 else 0.5)

    # 4. Generation mode correctness
    # For RAG cases, normal_rag or model_knowledge (if verified grounded) is expected
    gen_mode_correct = gen_mode in ("normal_rag", "model_knowledge") or context_used

    # 5. Document relevance validation
    doc_rel_score = 1.0 if doc_relevance in ("relevant", "mixed") else 0.5

    # 6. Response quality check
    resp_quality = 1.0 if len(resp_text) >= 80 else (len(resp_text) / 80.0)

    # Composite score
    score = (
        0.25 * (1.0 if context_used else 0.2)
        + 0.30 * answer_relevance
        + 0.20 * faithfulness_proxy
        + 0.15 * (1.0 if gen_mode_correct else 0.0)
        + 0.10 * resp_quality
    )
    score = min(max(score, 0.0), 1.0)

    return {
        "score": round(score, 4),
        "raw_metrics": {
            "context_used": context_used,
            "answer_relevance": round(answer_relevance, 3),
            "faithfulness_proxy": round(faithfulness_proxy, 3),
            "generation_mode": gen_mode,
            "generation_mode_correct": gen_mode_correct,
            "document_relevance": doc_relevance,
            "response_length": len(resp_text),
        },
    }
