"""
app/api/analytics.py — Enterprise Analytics REST API.

Provides queryable, real metrics from the database and in-memory trackers
for the analytics dashboard. All numbers come from actual application data.

Endpoints:
  GET /analytics/overview        — System-wide summary
  GET /analytics/quality         — GenAI quality metrics from eval store
  GET /analytics/routing         — Model routing distribution and costs
  GET /analytics/retrieval       — RAG retrieval statistics
  GET /analytics/graph           — Knowledge graph analytics
  GET /analytics/telemetry       — Recent telemetry records
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy import select, func, case, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.core.metrics import metrics_collector
from app.schemas.auth import UserOut

logger = logging.getLogger("app.api.analytics")

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/overview")
async def analytics_overview(
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    System-wide overview metrics.
    All numbers are real — derived from DB records and in-memory metrics.
    """
    # HTTP request metrics from Prometheus collector
    prom_data = metrics_collector.request_counter
    total_requests = sum(prom_data.values())
    successful = sum(v for (_, _, status), v in prom_data.items() if 200 <= status < 400)
    failed = sum(v for (_, _, status), v in prom_data.items() if status >= 400)

    durations = metrics_collector.request_durations
    avg_latency = round(sum(durations) / len(durations), 1) if durations else 0.0
    p95_latency = 0.0
    if durations:
        sorted_dur = sorted(durations)
        p95_idx = int(len(sorted_dur) * 0.95)
        p95_latency = round(sorted_dur[p95_idx], 1)

    # DB-level counts
    try:
        from app.models.telemetry import TelemetryRecord
        tel_count = await db.execute(select(func.count(TelemetryRecord.request_id)))
        telemetry_total = tel_count.scalar() or 0

        fallback_count = await db.execute(
            select(func.count(TelemetryRecord.request_id))
            .where(TelemetryRecord.is_fallback == True)
        )
        fallback_total = fallback_count.scalar() or 0

        avg_tel = await db.execute(
            select(
                func.avg(TelemetryRecord.total_latency_ms).label("avg_lat"),
                func.avg(TelemetryRecord.estimated_cost_usd).label("avg_cost"),
                func.sum(TelemetryRecord.estimated_cost_usd).label("total_cost"),
            )
        )
        tel_row = avg_tel.first()
    except Exception as e:
        logger.warning(f"[Analytics] DB query failed: {e}")
        telemetry_total = 0
        fallback_total = 0
        tel_row = None

    # Cost tracker
    try:
        from app.routing.cost_tracker import cost_tracker
        cost_summary = cost_tracker.get_summary()
    except Exception:
        cost_summary = {}

    return {
        "timestamp": time.time(),
        "http_metrics": {
            "total_requests": total_requests,
            "successful_requests": successful,
            "failed_requests": failed,
            "avg_latency_ms": avg_latency,
            "p95_latency_ms": p95_latency,
        },
        "agent_metrics": {
            "total_agent_requests": telemetry_total,
            "fallback_requests": fallback_total,
            "fallback_rate": round(fallback_total / max(telemetry_total, 1), 3),
            "avg_agent_latency_ms": round(float(tel_row.avg_lat or 0), 1) if tel_row else 0.0,
        },
        "cost": {
            "total_estimated_usd": round(float(tel_row.total_cost or 0), 6) if tel_row else 0.0,
            "avg_cost_per_request_usd": round(float(tel_row.avg_cost or 0), 6) if tel_row else 0.0,
            **cost_summary.get("routing_distribution", {}),
        },
    }


@router.get("/quality")
async def analytics_quality(
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """GenAI quality metrics from the evaluation store."""
    try:
        from app.evaluation.eval_store import get_eval_summary
        summary = await get_eval_summary(db)
        return {"timestamp": time.time(), "evaluation": summary}
    except Exception as e:
        return {"timestamp": time.time(), "evaluation": {"error": str(e)}}


@router.get("/routing")
async def analytics_routing(
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Model routing distribution, costs, and tier breakdown."""
    try:
        from app.routing.cost_tracker import cost_tracker
        from app.routing.model_profiles import get_all_profiles
        from app.models.telemetry import TelemetryRecord

        cost_summary = cost_tracker.get_summary()
        recent_records = cost_tracker.get_recent_records(limit=20)

        # Intent distribution from DB
        intent_dist = await db.execute(
            select(
                TelemetryRecord.intent,
                func.count(TelemetryRecord.request_id).label("count"),
            )
            .group_by(TelemetryRecord.intent)
            .order_by(desc("count"))
        )
        intent_rows = intent_dist.all()

        # Tier distribution from DB
        tier_dist = await db.execute(
            select(
                TelemetryRecord.model_tier,
                func.count(TelemetryRecord.request_id).label("count"),
                func.avg(TelemetryRecord.total_latency_ms).label("avg_latency"),
            )
            .group_by(TelemetryRecord.model_tier)
        )
        tier_rows = tier_dist.all()

        return {
            "timestamp": time.time(),
            "cost_summary": cost_summary,
            "recent_requests": recent_records,
            "intent_distribution": [
                {"intent": r.intent, "count": r.count} for r in intent_rows if r.intent
            ],
            "tier_distribution": [
                {
                    "tier": r.model_tier,
                    "count": r.count,
                    "avg_latency_ms": round(float(r.avg_latency or 0), 1),
                }
                for r in tier_rows if r.model_tier
            ],
            "model_profiles": get_all_profiles(),
        }
    except Exception as e:
        logger.warning(f"[Analytics] Routing query failed: {e}")
        return {"timestamp": time.time(), "error": str(e)}


@router.get("/retrieval")
async def analytics_retrieval(
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """RAG retrieval quality statistics."""
    try:
        from app.models.telemetry import TelemetryRecord

        result = await db.execute(
            select(
                func.count(TelemetryRecord.request_id).label("total"),
                func.sum(
                    case((TelemetryRecord.needs_retrieval == True, 1), else_=0)
                ).label("retrieval_used"),
                func.sum(
                    case((TelemetryRecord.chunks_retrieved == 0, 1), else_=0)
                ).label("empty_retrieval"),
                func.avg(TelemetryRecord.chunks_retrieved).label("avg_chunks"),
                func.avg(TelemetryRecord.retrieval_confidence).label("avg_confidence"),
                func.avg(TelemetryRecord.retrieval_retries).label("avg_retries"),
                func.sum(TelemetryRecord.graph_evidence_count).label("total_graph_evidence"),
            )
        )
        row = result.first()
        total = row.total or 0

        return {
            "timestamp": time.time(),
            "total_requests": total,
            "retrieval_used": row.retrieval_used or 0,
            "retrieval_rate": round((row.retrieval_used or 0) / max(total, 1), 3),
            "empty_retrieval_count": row.empty_retrieval or 0,
            "empty_retrieval_rate": round((row.empty_retrieval or 0) / max(total, 1), 3),
            "avg_chunks_retrieved": round(float(row.avg_chunks or 0), 1),
            "avg_retrieval_confidence": round(float(row.avg_confidence or 0), 3),
            "avg_retrieval_retries": round(float(row.avg_retries or 0), 2),
            "total_graph_evidence_items": row.total_graph_evidence or 0,
        }
    except Exception as e:
        logger.warning(f"[Analytics] Retrieval query failed: {e}")
        return {"timestamp": time.time(), "error": str(e)}


@router.get("/graph")
async def analytics_graph(
    current_user: UserOut = Depends(get_current_user),
) -> Dict[str, Any]:
    """Knowledge graph analytics and quality metrics."""
    try:
        from app.graph.graph_quality import get_graph_quality_report
        quality = await get_graph_quality_report()
        return {"timestamp": time.time(), "graph_quality": quality}
    except Exception as e:
        return {"timestamp": time.time(), "graph_quality": {"available": False, "error": str(e)}}


@router.get("/telemetry")
async def recent_telemetry(
    limit: int = 50,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Get recent telemetry records for the observability view."""
    try:
        from app.models.telemetry import TelemetryRecord
        result = await db.execute(
            select(TelemetryRecord)
            .order_by(desc(TelemetryRecord.created_at))
            .limit(min(limit, 200))
        )
        records = result.scalars().all()
        return {
            "timestamp": time.time(),
            "records": [
                {
                    "request_id": r.request_id,
                    "intent": r.intent,
                    "model_used": r.model_used,
                    "model_tier": r.model_tier,
                    "total_latency_ms": r.total_latency_ms,
                    "chunks_retrieved": r.chunks_retrieved,
                    "graph_evidence_count": r.graph_evidence_count,
                    "hallucination_risk": r.hallucination_risk,
                    "evidence_verdict": r.evidence_verdict,
                    "answer_confidence": r.answer_confidence,
                    "estimated_cost_usd": r.estimated_cost_usd,
                    "is_fallback": r.is_fallback,
                    "generation_mode": r.generation_mode,
                    "created_at": r.created_at,
                }
                for r in records
            ],
            "count": len(records),
        }
    except Exception as e:
        logger.warning(f"[Analytics] Telemetry query failed: {e}")
        return {"timestamp": time.time(), "error": str(e), "records": []}
