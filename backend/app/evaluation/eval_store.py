"""
app/evaluation/eval_store.py — Persist evaluation results to the database.

Stores each evaluation result so the analytics dashboard can:
  - Show historical quality trends
  - Track hallucination rates over time
  - Compare models by quality
  - Identify low-quality response patterns
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.evaluation.evaluator import EvaluationResult

logger = logging.getLogger("app.evaluation.eval_store")


async def persist_eval_result(
    db: AsyncSession,
    result: EvaluationResult,
) -> bool:
    """
    Persist an evaluation result to the database.
    Returns True on success, False on failure.
    """
    try:
        from app.models.evaluation import EvalResult as EvalResultModel
        record = EvalResultModel(
            eval_id=result.eval_id,
            request_id=result.request_id,
            question=result.question[:500],
            response=result.response[:2000],
            model_used=result.model_used,
            latency_ms=result.latency_ms,
            token_estimate=result.token_estimate,
            answer_confidence=result.answer_confidence,
            evidence_verdict=result.evidence_checker_verdict,
            deterministic_score=result.deterministic.get("aggregate_score", 0.0) if result.deterministic else None,
            ragas_faithfulness=result.ragas.get("faithfulness") if result.ragas and result.ragas.get("available") else None,
            ragas_relevancy=result.ragas.get("answer_relevancy") if result.ragas and result.ragas.get("available") else None,
            overall_score=result.overall_score,
            hallucination_risk=result.hallucination_risk,
            quality_gate=result.quality_gate,
            eval_version=result.eval_version,
            chunk_count=len(result.retrieved_chunks),
            graph_evidence_count=len(result.graph_evidence),
            details_json=json.dumps(result.to_dict()),
        )
        db.add(record)
        await db.commit()
        return True
    except Exception as e:
        logger.warning(f"[EvalStore] Failed to persist eval {result.eval_id}: {e}")
        await db.rollback()
        return False


async def get_eval_summary(db: AsyncSession, limit: int = 1000) -> Dict[str, Any]:
    """
    Compute aggregate evaluation statistics for the analytics dashboard.
    Returns real metrics from the database.
    """
    try:
        from app.models.evaluation import EvalResult as EvalResultModel
        from sqlalchemy import func, case

        result = await db.execute(
            select(
                func.count(EvalResultModel.eval_id).label("total"),
                func.avg(EvalResultModel.overall_score).label("avg_score"),
                func.avg(EvalResultModel.answer_confidence).label("avg_confidence"),
                func.avg(EvalResultModel.latency_ms).label("avg_latency_ms"),
                func.avg(EvalResultModel.ragas_faithfulness).label("avg_faithfulness"),
                func.avg(EvalResultModel.ragas_relevancy).label("avg_relevancy"),
                func.sum(
                    case((EvalResultModel.hallucination_risk == "high", 1), else_=0)
                ).label("high_risk_count"),
                func.sum(
                    case((EvalResultModel.quality_gate == "PASS", 1), else_=0)
                ).label("pass_count"),
                func.sum(
                    case((EvalResultModel.quality_gate == "FAIL", 1), else_=0)
                ).label("fail_count"),
            ).limit(limit)
        )
        row = result.first()
        if not row or not row.total:
            return {"total_evaluations": 0, "message": "No evaluations yet"}

        total = row.total or 0
        return {
            "total_evaluations": total,
            "avg_overall_score": round(float(row.avg_score or 0), 3),
            "avg_confidence": round(float(row.avg_confidence or 0), 3),
            "avg_latency_ms": round(float(row.avg_latency_ms or 0), 1),
            "avg_faithfulness": round(float(row.avg_faithfulness or 0), 3) if row.avg_faithfulness else None,
            "avg_relevancy": round(float(row.avg_relevancy or 0), 3) if row.avg_relevancy else None,
            "hallucination_rate": round((row.high_risk_count or 0) / max(total, 1), 3),
            "pass_rate": round((row.pass_count or 0) / max(total, 1), 3),
            "fail_rate": round((row.fail_count or 0) / max(total, 1), 3),
        }
    except Exception as e:
        logger.warning(f"[EvalStore] Summary query failed: {e}")
        return {"error": str(e)}
