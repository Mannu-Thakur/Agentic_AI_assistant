"""
benchmarks/scorers/web_search_scorer.py — Scorer for Web Search capability.

Evaluates:
  - Answer Coverage (% of expected query-relevant entities present)
  - Web Search Execution (verified via execution_trace and web_status)
  - Intent Classifier Accuracy (WEB_SEARCH, NEWS, or CURRENT_EVENTS)
  - Source Citation Count & Provider Attribution
"""

from __future__ import annotations

from typing import Any


def score_web_search(case: dict[str, Any], response_data: dict[str, Any]) -> dict[str, Any]:
    """
    Score a live Web Search query against coverage criteria and execution state.
    """
    expected_contains = case.get("expected_answer_contains", [])
    resp_text = response_data.get("response_text", "").lower()
    intent = response_data.get("intent", "").upper()
    web_status = response_data.get("web_status", {}) or {}

    # 1. Web search execution check
    trace = response_data.get("execution_trace", [])
    web_executed = bool(web_status.get("executed", False))
    if not web_executed:
        for step in trace:
            sname = step.get("name", "")
            if sname in ("execute_web_search", "web_search") and step.get("status") == "EXECUTED":
                web_executed = True
                break

    # 2. Intent accuracy check
    valid_web_intents = {"WEB_SEARCH", "NEWS", "CURRENT_EVENTS", "COMPLEX"}
    intent_accuracy = 1.0 if intent in valid_web_intents else 0.0

    # 3. Answer coverage
    if expected_contains:
        matched = sum(1 for term in expected_contains if term.lower() in resp_text)
        answer_coverage = matched / len(expected_contains)
    else:
        answer_coverage = 1.0 if len(resp_text) > 100 else 0.5

    # 4. Source citation count
    results_count = int(web_status.get("results_count", 0) or 0)
    if results_count == 0 and web_executed:
        # Check citations in telemetry
        telemetry = response_data.get("telemetry", {}) or {}
        results_count = len(telemetry.get("citations", [])) or (3 if len(resp_text) > 150 else 0)
    source_score = min(results_count / 3.0, 1.0) if results_count > 0 else (0.7 if web_executed else 0.0)

    # 5. Response length and substantive quality
    quality_score = 1.0 if len(resp_text) >= 120 else (len(resp_text) / 120.0)

    # Composite score
    score = (
        0.35 * answer_coverage
        + 0.30 * (1.0 if web_executed else 0.0)
        + 0.15 * intent_accuracy
        + 0.10 * source_score
        + 0.10 * quality_score
    )
    score = min(max(score, 0.0), 1.0)

    return {
        "score": round(score, 4),
        "raw_metrics": {
            "answer_coverage": round(answer_coverage, 3),
            "web_executed": web_executed,
            "intent_accuracy": round(intent_accuracy, 3),
            "source_count": results_count,
            "provider_used": web_status.get("provider", "waterfall"),
            "response_length": len(resp_text),
        },
    }
