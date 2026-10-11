from fastapi import APIRouter, Response, Depends
from app.core.metrics import metrics_collector
from app.api.auth import get_current_user

router = APIRouter(tags=["Observability Metrics"])

@router.get("/metrics")
async def prometheus_metrics():
    """Exposes application performance metrics in Prometheus text format."""
    exposition = metrics_collector.get_prometheus_exposition()
    return Response(content=exposition, media_type="text/plain; version=0.0.4")


@router.get("/metrics/providers")
async def provider_metrics_summary(current_user=Depends(get_current_user)):
    """
    Return per-provider call stats, latency, token usage, and health status.
    Used by the Cost Dashboard UI.
    """
    try:
        from app.providers.provider_metrics import provider_metrics
        return provider_metrics.get_summary()
    except Exception as exc:
        return {
            "providers": {},
            "recent_fallbacks": [],
            "recent_circuit_events": [],
            "error": str(exc),
        }
