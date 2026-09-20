"""
app/evaluation/evaluator.py — Unified GenAI evaluation abstraction.

Provides a single entry point for evaluating any generated response.
Combines:
  1. Deterministic checks (always available, zero cost)
  2. RAGAS evaluation (requires LLM key, async, may be skipped)
  3. Existing evidence checker verdict (from agent state)

All evaluation results are structured and persisted to the eval store.
The system NEVER fakes scores — if evaluation fails, it says "unavailable".
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from app.evaluation.deterministic_checks import run_all_checks

logger = logging.getLogger("app.evaluation.evaluator")

# Evaluation framework version — increment when eval logic changes
EVAL_VERSION = "1.0.0"


class EvaluationResult:
    """Complete evaluation result for a single response."""

    def __init__(
        self,
        eval_id: str,
        request_id: str,
        question: str,
        response: str,
        retrieved_chunks: List[Dict[str, Any]],
        graph_evidence: Optional[List[Dict[str, Any]]] = None,
        evidence_checker_verdict: Optional[str] = None,
        answer_confidence: float = 1.0,
        model_used: str = "",
        latency_ms: float = 0.0,
        token_estimate: int = 0,
    ):
        self.eval_id = eval_id
        self.request_id = request_id
        self.question = question
        self.response = response
        self.retrieved_chunks = retrieved_chunks
        self.graph_evidence = graph_evidence or []
        self.evidence_checker_verdict = evidence_checker_verdict
        self.answer_confidence = answer_confidence
        self.model_used = model_used
        self.latency_ms = latency_ms
        self.token_estimate = token_estimate
        self.eval_version = EVAL_VERSION
        self.timestamp = time.time()

        # Will be populated by evaluate()
        self.deterministic: Optional[Dict[str, Any]] = None
        self.ragas: Optional[Dict[str, Any]] = None
        self.overall_score: float = 0.0
        self.hallucination_risk: str = "unknown"
        self.quality_gate: str = "PENDING"  # "PASS" | "WARN" | "FAIL"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "eval_id": self.eval_id,
            "request_id": self.request_id,
            "question": self.question[:500],
            "response": self.response[:1000],
            "model_used": self.model_used,
            "latency_ms": self.latency_ms,
            "token_estimate": self.token_estimate,
            "answer_confidence": self.answer_confidence,
            "evidence_checker_verdict": self.evidence_checker_verdict,
            "deterministic": self.deterministic,
            "ragas": self.ragas,
            "overall_score": self.overall_score,
            "hallucination_risk": self.hallucination_risk,
            "quality_gate": self.quality_gate,
            "eval_version": self.eval_version,
            "timestamp": self.timestamp,
            "chunk_count": len(self.retrieved_chunks),
            "graph_evidence_count": len(self.graph_evidence),
        }


async def evaluate_response(
    question: str,
    response: str,
    retrieved_chunks: List[Dict[str, Any]],
    request_id: str = "",
    graph_evidence: Optional[List[Dict[str, Any]]] = None,
    evidence_checker_verdict: Optional[str] = None,
    answer_confidence: float = 1.0,
    model_used: str = "",
    latency_ms: float = 0.0,
    token_estimate: int = 0,
    run_ragas: bool = False,  # RAGAS is async and costly — opt-in
) -> EvaluationResult:
    """
    Evaluate a generated response.

    Args:
        question: Original user question
        response: Generated response text
        retrieved_chunks: Chunks used for generation
        request_id: Correlation ID for tracing
        graph_evidence: Graph evidence items (for GraphRAG)
        evidence_checker_verdict: "PASS"/"WARN"/"FAIL" from evidence checker node
        answer_confidence: 0.0-1.0 from evidence checker
        model_used: Model that generated the response
        latency_ms: End-to-end latency
        token_estimate: Estimated total tokens
        run_ragas: Whether to run RAGAS evaluation (costs LLM calls)

    Returns:
        EvaluationResult with all scores populated
    """
    eval_id = str(uuid.uuid4())
    result = EvaluationResult(
        eval_id=eval_id,
        request_id=request_id,
        question=question,
        response=response,
        retrieved_chunks=retrieved_chunks,
        graph_evidence=graph_evidence,
        evidence_checker_verdict=evidence_checker_verdict,
        answer_confidence=answer_confidence,
        model_used=model_used,
        latency_ms=latency_ms,
        token_estimate=token_estimate,
    )

    # ── Step 1: Deterministic checks (always run) ─────────────────────────────
    try:
        result.deterministic = run_all_checks(question, response, retrieved_chunks)
    except Exception as e:
        logger.warning(f"[Evaluator] Deterministic checks failed: {e}")
        result.deterministic = {"error": str(e), "aggregate_score": 0.5}

    # ── Step 2: RAGAS evaluation (optional, LLM-dependent) ───────────────────
    if run_ragas:
        try:
            from app.evaluation.ragas_evaluator import run_ragas_evaluation
            result.ragas = await run_ragas_evaluation(
                question=question,
                response=response,
                retrieved_chunks=retrieved_chunks,
            )
        except Exception as e:
            logger.warning(f"[Evaluator] RAGAS evaluation failed: {e}")
            result.ragas = {"available": False, "error": str(e)}

    # ── Step 3: Compute overall score ─────────────────────────────────────────
    scores = []
    weights = []

    # Deterministic aggregate score (weight: 0.4)
    if result.deterministic:
        det_score = result.deterministic.get("aggregate_score", 0.5)
        scores.append(det_score)
        weights.append(0.4)

    # Answer confidence from evidence checker (weight: 0.35)
    scores.append(answer_confidence)
    weights.append(0.35)

    # RAGAS faithfulness if available (weight: 0.25)
    if result.ragas and result.ragas.get("available") and "faithfulness" in result.ragas:
        scores.append(result.ragas["faithfulness"])
        weights.append(0.25)

    if scores:
        total_weight = sum(weights)
        result.overall_score = round(
            sum(s * w for s, w in zip(scores, weights)) / total_weight, 3
        )
    else:
        result.overall_score = 0.5

    # ── Step 4: Hallucination risk classification ─────────────────────────────
    if evidence_checker_verdict == "FAIL" or answer_confidence < 0.4:
        result.hallucination_risk = "high"
    elif evidence_checker_verdict == "WARN" or answer_confidence < 0.65:
        result.hallucination_risk = "medium"
    else:
        result.hallucination_risk = "low"

    # ── Step 5: Quality gate decision ─────────────────────────────────────────
    if result.overall_score >= 0.70 and result.hallucination_risk == "low":
        result.quality_gate = "PASS"
    elif result.overall_score >= 0.50 and result.hallucination_risk != "high":
        result.quality_gate = "WARN"
    else:
        result.quality_gate = "FAIL"

    logger.info(
        f"[Evaluator] eval_id={eval_id} | score={result.overall_score:.2f} | "
        f"gate={result.quality_gate} | hallucination={result.hallucination_risk}"
    )
    return result
