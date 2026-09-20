"""
app/models/telemetry.py — SQLAlchemy model for persisted request telemetry.

Persists key telemetry fields from RequestTelemetry so the analytics dashboard
can query real historical data rather than only reading in-memory Prometheus counters.

Every completed agent request writes one TelemetryRecord.
"""
from __future__ import annotations

import time
from sqlalchemy import Column, String, Float, Integer, Text, Boolean, Index
from app.core.database import Base


class TelemetryRecord(Base):
    __tablename__ = "telemetry_records"

    request_id = Column(String, primary_key=True)
    user_id = Column(String, index=True, nullable=False, default="")
    chat_id = Column(String, index=True, nullable=False, default="")

    # Routing
    intent = Column(String, nullable=True)
    model_used = Column(String, nullable=True)
    provider = Column(String, nullable=True)
    model_tier = Column(String, nullable=True)       # slm / llm-medium / llm-strong
    routing_version = Column(String, nullable=True)
    user_override = Column(Boolean, nullable=True, default=False)
    complexity_score = Column(Float, nullable=True)

    # Retrieval
    needs_retrieval = Column(Boolean, nullable=True)
    chunks_retrieved = Column(Integer, nullable=True, default=0)
    graph_evidence_count = Column(Integer, nullable=True, default=0)
    retrieval_confidence = Column(Float, nullable=True)
    retrieval_retries = Column(Integer, nullable=True, default=0)

    # LLM
    llm_latency_ms = Column(Float, nullable=True)
    total_latency_ms = Column(Float, nullable=True)
    token_estimate = Column(Integer, nullable=True)
    estimated_cost_usd = Column(Float, nullable=True)

    # Quality
    answer_confidence = Column(Float, nullable=True)
    hallucination_risk = Column(String, nullable=True)   # low / medium / high
    evidence_verdict = Column(String, nullable=True)      # PASS / WARN / FAIL
    reflection_passed = Column(Boolean, nullable=True)

    # Source
    generation_mode = Column(String, nullable=True)  # normal_rag / web_fallback / model_knowledge
    is_fallback = Column(Boolean, nullable=True, default=False)

    # Versioning
    prompt_version = Column(String, nullable=True)
    embedding_version = Column(String, nullable=True)

    created_at = Column(Float, nullable=False, default=time.time)

    __table_args__ = (
        Index("ix_telemetry_created_at", "created_at"),
        Index("ix_telemetry_intent", "intent"),
        Index("ix_telemetry_model_tier", "model_tier"),
        Index("ix_telemetry_hallucination", "hallucination_risk"),
    )
