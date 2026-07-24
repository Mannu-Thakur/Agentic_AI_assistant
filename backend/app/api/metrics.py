from fastapi import APIRouter, Response
from app.core.metrics import metrics_collector

router = APIRouter(tags=["Observability Metrics"])

@router.get("/metrics")
async def prometheus_metrics():
    """Exposes application performance metrics in Prometheus text format."""
    exposition = metrics_collector.get_prometheus_exposition()
    return Response(content=exposition, media_type="text/plain; version=0.0.4")
