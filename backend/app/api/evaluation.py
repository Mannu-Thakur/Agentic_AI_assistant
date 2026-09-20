"""
app/api/evaluation.py — GenAI Evaluation REST API.

Endpoints:
  GET /evaluation/summary      — Aggregate evaluation statistics
  GET /evaluation/recent       — Recent evaluation records
  POST /evaluation/evaluate    — On-demand response evaluation
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.evaluation.evaluator import evaluate_response
from app.evaluation.eval_store import get_eval_summary, persist_eval_result
from app.schemas.auth import UserOut

logger = logging.getLogger("app.api.evaluation")

router = APIRouter(prefix="/evaluation", tags=["GenAI Evaluation"])


class EvalRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    response: str = Field(..., min_length=1, max_length=10000)
    retrieved_chunks: List[Dict[str, Any]] = Field(default_factory=list)
    request_id: str = Field(default="")
    model_used: str = Field(default="")
    latency_ms: float = Field(default=0.0)
    token_estimate: int = Field(default=0)
    answer_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence_verdict: Optional[str] = Field(default=None)
    run_ragas: bool = Field(default=False, description="Enable RAGAS evaluation (uses LLM calls)")


@router.get("/summary")
async def evaluation_summary(
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get aggregate evaluation statistics from the database."""
    return await get_eval_summary(db)


@router.get("/recent")
async def recent_evaluations(
    limit: int = 20,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get recent evaluation records."""
    try:
        from app.models.evaluation import EvalResult
        from sqlalchemy import select, desc
        result = await db.execute(
            select(EvalResult)
            .order_by(desc(EvalResult.created_at))
            .limit(min(limit, 100))
        )
        records = result.scalars().all()
        return {
            "evaluations": [
                {
                    "eval_id": r.eval_id,
                    "question": r.question[:200],
                    "model_used": r.model_used,
                    "overall_score": r.overall_score,
                    "quality_gate": r.quality_gate,
                    "hallucination_risk": r.hallucination_risk,
                    "latency_ms": r.latency_ms,
                    "created_at": r.created_at,
                }
                for r in records
            ],
            "count": len(records),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/evaluate")
async def evaluate(
    payload: EvalRequest,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Evaluate a response on demand and persist the result."""
    try:
        result = await evaluate_response(
            question=payload.question,
            response=payload.response,
            retrieved_chunks=payload.retrieved_chunks,
            request_id=payload.request_id,
            evidence_checker_verdict=payload.evidence_verdict,
            answer_confidence=payload.answer_confidence,
            model_used=payload.model_used,
            latency_ms=payload.latency_ms,
            token_estimate=payload.token_estimate,
            run_ragas=payload.run_ragas,
        )
        await persist_eval_result(db, result)
        return result.to_dict()
    except Exception as e:
        logger.error(f"[EvalAPI] Evaluation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
