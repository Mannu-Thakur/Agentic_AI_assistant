"""
benchmarks/scorers/self_rag_scorer.py — Scorer for Self-RAG routing capability.

Evaluates:
  - Routing Accuracy: did needs_retrieval match expected_needs_retrieval?
  - Generation Mode Agreement: did generation_mode match expected mode?
  - Calibration Score: is retrieval_confidence aligned with retrieval decision?
"""

from __future__ import annotations

from typing import Any


def score_self_rag(case: dict[str, Any], response_data: dict[str, Any]) -> dict[str, Any]:
    """
    Score a Self-RAG routing test case against the live graph execution.
    """
    exp_retrieval = case.get("expected_needs_retrieval", True)
    exp_mode = case.get("expected_generation_mode", "normal_rag")

    actual_retrieval = response_data.get("needs_retrieval", False)
    actual_mode = response_data.get("generation_mode", "")
    retrieval_conf = float(response_data.get("retrieval_confidence", 0.0) or 0.0)

    # Check execution trace to verify if retrieve_context actually ran or was bypassed
    trace = response_data.get("execution_trace", [])
    executed_retrieval = False
    for step in trace:
        if step.get("name") == "retrieve_context" and step.get("status") == "EXECUTED":
            executed_retrieval = True
            break
        if step.get("name") == "retrieve_context" and step.get("status") == "BYPASSED":
            executed_retrieval = False

    # Actual decision considers both flag and execution trace
    effective_retrieval = actual_retrieval or executed_retrieval

    # 1. Routing accuracy (primary metric)
    routing_correct = (effective_retrieval == exp_retrieval)
    routing_acc = 1.0 if routing_correct else 0.0

    # 2. Generation mode agreement
    mode_correct = False
    if exp_mode == "normal_rag":
        mode_correct = (actual_mode in ("normal_rag", "model_knowledge") if not effective_retrieval else actual_mode == "normal_rag")
    elif exp_mode == "model_knowledge":
        mode_correct = (actual_mode in ("model_knowledge", "") or not effective_retrieval)
    mode_score = 1.0 if mode_correct else 0.0

    # 3. Calibration score
    # If retrieval was needed: confidence should be >= 0.5
    # If retrieval was NOT needed: confidence should be low or 0.0
    if exp_retrieval:
        calibration_score = 1.0 if retrieval_conf >= 0.4 else (retrieval_conf / 0.4)
    else:
        calibration_score = 1.0 if retrieval_conf < 0.6 else (1.0 - (retrieval_conf - 0.6))
    calibration_score = min(max(calibration_score, 0.0), 1.0)

    # 4. Response validity
    resp_text = response_data.get("response_text", "")
    resp_ok = 1.0 if len(resp_text) > 30 and "error" not in resp_text.lower() else 0.5

    # Composite score
    score = (
        0.45 * routing_acc
        + 0.30 * mode_score
        + 0.15 * calibration_score
        + 0.10 * resp_ok
    )
    score = min(max(score, 0.0), 1.0)

    return {
        "score": round(score, 4),
        "raw_metrics": {
            "routing_correct": routing_correct,
            "mode_correct": mode_correct,
            "expected_retrieval": exp_retrieval,
            "actual_retrieval": effective_retrieval,
            "expected_mode": exp_mode,
            "actual_mode": actual_mode,
            "retrieval_confidence": round(retrieval_conf, 3),
            "calibration_score": round(calibration_score, 3),
        },
    }
