"""
app/models/evaluation.py — SQLAlchemy model for evaluation results.

Stores per-request evaluation results with all quality metrics.
"""
from __future__ import annotations

import time
from sqlalchemy import Column, String, Float, Integer, Text, Index
from app.core.database import Base


class EvalResult(Base):
    __tablename__ = "eval_results"

    eval_id = Column(String, primary_key=True)
    request_id = Column(String, index=True, nullable=False, default="")
    question = Column(Text, nullable=False, default="")
    response = Column(Text, nullable=False, default="")
    model_used = Column(String, nullable=True)
    latency_ms = Column(Float, nullable=True)
    token_estimate = Column(Integer, nullable=True)
    answer_confidence = Column(Float, nullable=True)
    evidence_verdict = Column(String, nullable=True)   # PASS / WARN / FAIL
    deterministic_score = Column(Float, nullable=True)
    ragas_faithfulness = Column(Float, nullable=True)
    ragas_relevancy = Column(Float, nullable=True)
    overall_score = Column(Float, nullable=True)
    hallucination_risk = Column(String, nullable=True)  # low / medium / high
    quality_gate = Column(String, nullable=True)        # PASS / WARN / FAIL
    eval_version = Column(String, nullable=True)
    chunk_count = Column(Integer, nullable=True, default=0)
    graph_evidence_count = Column(Integer, nullable=True, default=0)
    details_json = Column(Text, nullable=True)  # full EvaluationResult as JSON
    created_at = Column(Float, nullable=False, default=time.time)

    __table_args__ = (
        Index("ix_eval_results_created_at", "created_at"),
        Index("ix_eval_results_quality_gate", "quality_gate"),
        Index("ix_eval_results_hallucination_risk", "hallucination_risk"),
    )
