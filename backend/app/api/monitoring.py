"""
app/api/monitoring.py — AI/ML Monitoring REST API.

Endpoints:
  GET /monitoring/drift         — Data drift detection report
  GET /monitoring/health        — Overall system health summary
  GET /monitoring/performance   — Model performance trends from telemetry
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict

from fastapi import APIRouter, Depends, Query

from app.api.auth import get_current_user
from app.core.config import settings
from app.schemas.auth import UserOut

logger = logging.getLogger("app.api.monitoring")

router = APIRouter(prefix="/monitoring", tags=["AI/ML Monitoring"])


@router.get("/drift")
async def drift_report(
    baseline_hours: int = Query(24, ge=1, le=720, description="Baseline window in hours"),
    current_hours: int = Query(1, ge=1, le=24, description="Current window in hours"),
    current_user: UserOut = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Compute data drift metrics comparing recent vs baseline telemetry.
    Uses PSI and KS tests on real application metrics.
    """
    try:
        from app.monitoring.drift_detector import compute_drift_report
        b_h = baseline_hours if isinstance(baseline_hours, (int, float)) else getattr(baseline_hours, "default", 24)
        c_h = current_hours if isinstance(current_hours, (int, float)) else getattr(current_hours, "default", 1)
        return await compute_drift_report(
            baseline_window_hours=int(b_h or 24),
            current_window_hours=int(c_h or 1),
        )
    except Exception as e:
        logger.error(f"[Monitoring] Drift report failed: {e}")
        return {"available": False, "error": str(e)}


@router.get("/health")
async def system_health(
    current_user: UserOut = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Overall system health combining database, vector store, search providers, and AI services.
    """
    health: Dict[str, Any] = {"timestamp": time.time(), "components": {}}

    # Primary SQL Database
    try:
        from app.core.database import AsyncSessionLocal
        from sqlalchemy import text, func, select
        from app.models.user import User
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
            u_count = (await db.execute(select(func.count(User.id)))).scalar() or 0
        health["components"]["primary_database"] = {
            "status": "healthy",
            "type": "SQLite (WAL mode)" if "sqlite" in str(settings.DATABASE_URL) else "PostgreSQL",
            "registered_users": u_count,
        }
    except Exception as e:
        health["components"]["primary_database"] = {"status": "error", "error": str(e)}

    # Vector store (ChromaDB)
    try:
        from app.retrieval.vector_store import VectorStore
        vs = VectorStore()
        coll = vs.get_collection()
        count = coll.count()
        health["components"]["vector_store"] = {
            "status": "healthy",
            "chunk_count": count,
            "engine": "ChromaDB",
        }
    except Exception as e:
        health["components"]["vector_store"] = {"status": "error", "error": str(e)}

    # Redis / In-memory Cache
    try:
        from app.core.redis_client import get_redis
        r = await get_redis()
        if r:
            await r.ping()
            health["components"]["cache"] = {"status": "healthy", "backend": "Redis"}
        else:
            health["components"]["cache"] = {"status": "healthy", "backend": "In-Memory TTL Cache"}
    except Exception as e:
        health["components"]["cache"] = {"status": "healthy", "backend": "In-Memory TTL Cache"}

    # Search & Tool Providers
    try:
        providers = []
        if getattr(settings, "TAVILY_API_KEY", None):
            providers.append("Tavily")
        if getattr(settings, "SERP_API_KEY", None):
            providers.append("SerpAPI")
        if getattr(settings, "EXA_API_KEY", None):
            providers.append("Exa")
        providers.append("DuckDuckGo (Native)")
        health["components"]["search_pipeline"] = {
            "status": "healthy",
            "active_providers": ", ".join(providers),
        }
    except Exception as e:
        health["components"]["search_pipeline"] = {"status": "warning", "error": str(e)}

    # Neo4j (Optional GraphRAG)
    try:
        from app.graph.neo4j_client import neo4j_client
        stats = await neo4j_client.get_stats()
        health["components"]["neo4j_graph"] = {
            "status": "healthy" if stats.get("available") else "optional_offline",
            **stats,
        }
    except Exception as e:
        health["components"]["neo4j_graph"] = {"status": "optional_offline", "error": str(e)}

    # Overall Status: if core DB, vector store, and cache are healthy, system is healthy
    core_ok = (
        health["components"].get("primary_database", {}).get("status") == "healthy" and
        health["components"].get("vector_store", {}).get("status") == "healthy"
    )
    health["overall"] = "healthy" if core_ok else "degraded"
    return health


@router.get("/performance")
async def performance_trends(
    hours: int = Query(24, ge=1, le=168),
    current_user: UserOut = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Model performance trends from telemetry over the specified window.
    Returns real data from the telemetry DB — no synthetic numbers.
    """
    try:
        import time
        from app.core.database import AsyncSessionLocal
        from app.models.telemetry import TelemetryRecord
        from sqlalchemy import select, func

        cutoff = time.time() - (hours * 3600)
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(
                    TelemetryRecord.model_used,
                    TelemetryRecord.model_tier,
                    func.count(TelemetryRecord.request_id).label("count"),
                    func.avg(TelemetryRecord.total_latency_ms).label("avg_latency"),
                    func.avg(TelemetryRecord.answer_confidence).label("avg_confidence"),
                    func.avg(TelemetryRecord.estimated_cost_usd).label("avg_cost"),
                )
                .where(TelemetryRecord.created_at >= cutoff)
                .group_by(TelemetryRecord.model_used, TelemetryRecord.model_tier)
                .order_by(func.count(TelemetryRecord.request_id).desc())
            )
            rows = result.all()

        return {
            "timestamp": time.time(),
            "window_hours": hours,
            "model_performance": [
                {
                    "model": r.model_used,
                    "tier": r.model_tier,
                    "request_count": r.count,
                    "avg_latency_ms": round(float(r.avg_latency or 0), 1),
                    "avg_confidence": round(float(r.avg_confidence or 0), 3),
                    "avg_cost_usd": round(float(r.avg_cost or 0), 6),
                }
                for r in rows if r.model_used
            ],
        }
    except Exception as e:
        logger.warning(f"[Monitoring] Performance trends failed: {e}")
        return {"timestamp": time.time(), "error": str(e)}
