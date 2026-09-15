"""
benchmarks/scorers/crag_scorer.py — Scorer for Corrective RAG (CRAG) capability.

Evaluates:
  - Document Relevance Grading Accuracy ('relevant' / 'irrelevant' / 'mixed' / 'no_docs')
  - Web Fallback Precision: did it trigger web search when documents were irrelevant?
  - No-Hallucination Compliance: did it politely state information is not in private documents?
  - Grounding Alignment
"""

from __future__ import annotations

from typing import Any


def score_crag(case: dict[str, Any], response_data: dict[str, Any]) -> dict[str, Any]:
    """
    Score a CRAG document grading and corrective action test case.
    """
    exp_relevance = case.get("expected_document_relevance", "relevant")
    exp_web_fallback = case.get("expected_web_fallback", False)
    exp_no_halluc = case.get("expected_no_hallucination_response", False)

    actual_relevance = response_data.get("document_relevance", "")
    web_status = response_data.get("web_status", {}) or {}
    actual_web_executed = bool(web_status.get("executed", False))
    resp_text = response_data.get("response_text", "").lower()
    answer_conf = float(response_data.get("answer_confidence", 0.0) or 0.0)

    # 1. Grading accuracy
    # Normalize relevance strings
    grading_correct = (actual_relevance == exp_relevance)
    if not grading_correct and exp_relevance == "relevant" and actual_relevance in ("relevant", "mixed"):
        grading_score = 0.8
    elif not grading_correct and exp_relevance == "irrelevant" and actual_relevance in ("irrelevant", "no_docs"):
        grading_score = 0.85
    elif grading_correct:
        grading_score = 1.0
    else:
        grading_score = 0.0

    # 2. Web fallback precision
    if exp_web_fallback:
        web_fallback_correct = actual_web_executed or ("web_fallback" in response_data.get("generation_mode", ""))
        web_score = 1.0 if web_fallback_correct else 0.0
    else:
        web_fallback_correct = not actual_web_executed
        web_score = 1.0 if web_fallback_correct else 0.3

    # 3. No-hallucination compliance (for private docs with no match)
    no_halluc_ok = True
    no_halluc_score = 1.0
    if exp_no_halluc:
        refusal_phrases = [
            "not found", "cannot find", "do not have", "don't have",
            "no document", "not mentioned", "not contained", "no information",
            "couldn't find", "unable to find", "does not contain"
        ]
        has_refusal = any(phrase in resp_text for phrase in refusal_phrases)
        no_halluc_ok = has_refusal
        no_halluc_score = 1.0 if has_refusal else 0.1

    # 4. Confidence alignment
    if exp_relevance == "relevant":
        conf_align = answer_conf if answer_conf > 0 else 0.85
    else:
        conf_align = (1.0 - answer_conf) if answer_conf > 0 else 0.8

    # Composite score
    score = (
        0.40 * grading_score
        + 0.30 * web_score
        + 0.20 * no_halluc_score
        + 0.10 * conf_align
    )
    score = min(max(score, 0.0), 1.0)

    return {
        "score": round(score, 4),
        "raw_metrics": {
            "grading_correct": grading_correct,
            "grading_score": round(grading_score, 3),
            "expected_relevance": exp_relevance,
            "actual_relevance": actual_relevance,
            "web_fallback_correct": web_fallback_correct,
            "actual_web_executed": actual_web_executed,
            "no_halluc_ok": no_halluc_ok,
            "confidence_alignment": round(conf_align, 3),
            "answer_confidence": round(answer_conf, 3),
        },
    }
