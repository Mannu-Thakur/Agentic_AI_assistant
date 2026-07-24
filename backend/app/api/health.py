"""
api/health.py — Provider health-check endpoints.

GET /health/providers
  Pings each configured LLM provider's cheapest verification endpoint and
  returns a per-provider status.  Useful for dashboards, monitoring scripts,
  and the frontend Settings page.

GET /health
  Lightweight app-level probe (returns 200 immediately).
"""

import time
import logging
import httpx
from fastapi import APIRouter

from app.core.config import settings

logger = logging.getLogger("api.health")

router = APIRouter(prefix="/health", tags=["Health"])

_TIMEOUT = 5.0  # seconds per provider check


async def _check_gemini(api_key: str) -> dict:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models"
        f"?key={api_key}&pageSize=1"
    )
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.get(url)
        ok = r.status_code == 200
        return {"status": "healthy" if ok else "degraded", "latency_ms": None, "http_status": r.status_code}
    except Exception as e:
        return {"status": "unreachable", "error": str(e)}


async def _check_groq(api_key: str) -> dict:
    url = "https://api.groq.com/openai/v1/models"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
        ok = r.status_code == 200
        return {"status": "healthy" if ok else "degraded", "http_status": r.status_code}
    except Exception as e:
        return {"status": "unreachable", "error": str(e)}


async def _check_openrouter(api_key: str) -> dict:
    url = "https://openrouter.ai/api/v1/auth/key"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
        ok = r.status_code == 200
        return {"status": "healthy" if ok else "degraded", "http_status": r.status_code}
    except Exception as e:
        return {"status": "unreachable", "error": str(e)}


async def _check_redis() -> dict:
    try:
        from app.core.redis_client import get_redis
        r = await get_redis()
        if r is None:
            return {"status": "unconfigured"}
        pong = await r.ping()
        return {"status": "healthy" if pong else "degraded"}
    except Exception as e:
        return {"status": "unreachable", "error": str(e)}


@router.get("")
async def health_check():
    """Lightweight app-level health probe."""
    return {
        "status":    "healthy",
        "project":   settings.PROJECT_NAME,
        "timestamp": time.time(),
    }


@router.get("/providers")
async def provider_health():
    """
    Ping every configured LLM provider and Redis.
    Missing keys are reported as 'unconfigured' rather than triggering a real check.
    """
    import asyncio

    results: dict = {}

    async def check(name: str, key: str | None, fn):
        if not key or key.startswith("mock_"):
            results[name] = {"status": "unconfigured"}
            return
        t0 = time.perf_counter()
        r = await fn(key)
        r["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        results[name] = r

    await asyncio.gather(
        check("gemini",      settings.GEMINI_API_KEY,      _check_gemini),
        check("groq",        settings.GROQ_API_KEY,        _check_groq),
        check("openrouter",  settings.OPENROUTER_API_KEY,  _check_openrouter),
    )

    # Redis check (no API key needed)
    t0 = time.perf_counter()
    results["redis"] = await _check_redis()
    results["redis"]["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)

    overall = "healthy" if all(
        v.get("status") in ("healthy", "unconfigured")
        for v in results.values()
    ) else "degraded"

    return {
        "overall":   overall,
        "timestamp": time.time(),
        "providers": results,
    }


# ── Phase 4 Health Probes ─────────────────────────────────────────────────────

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from fastapi.responses import JSONResponse
from app.core.database import get_db

@router.get("/liveness")
async def liveness():
    """Liveness probe. Returns 200 if the process is running."""
    return {"status": "alive", "timestamp": time.time()}

@router.get("/readiness")
async def readiness(db: AsyncSession = Depends(get_db)):
    """
    Readiness probe. Checks if critical dependencies (Database, Redis)
    are reachable. Returns 200 if ready, 503 otherwise.
    """
    db_ok = False
    redis_ok = False
    details = {}

    # Check database
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
        details["database"] = "ready"
    except Exception as e:
        logger.error(f"Readiness check failed for Database: {e}")
        details["database"] = f"error: {str(e)}"

    # Check redis
    try:
        redis_res = await _check_redis()
        redis_status = redis_res.get("status")
        if redis_status in ("healthy", "unconfigured"):
            redis_ok = True
            details["redis"] = "ready"
        else:
            details["redis"] = redis_status or "degraded"
    except Exception as e:
        logger.error(f"Readiness check failed for Redis: {e}")
        details["redis"] = f"error: {str(e)}"

    overall_status = "ready" if (db_ok and redis_ok) else "not_ready"
    status_code = 200 if overall_status == "ready" else 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": overall_status,
            "timestamp": time.time(),
            "dependencies": details
        }
    )
