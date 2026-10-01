import pytest
import time
from app.api.analytics import analytics_overview, analytics_quality, analytics_routing, analytics_retrieval, recent_telemetry
from app.api.monitoring import drift_report, system_health
from app.schemas.auth import UserOut
from app.core.database import AsyncSessionLocal

@pytest.fixture
def dummy_user():
    return UserOut(
        id="test-analyst-1",
        email="analyst@example.com",
        is_active=True,
        is_verified=True,
        role="user",
        created_at="2026-01-01T00:00:00"
    )

@pytest.mark.asyncio
async def test_analytics_overview_real_data(dummy_user):
    async with AsyncSessionLocal() as db:
        res = await analytics_overview(current_user=dummy_user, db=db)
        assert "http_metrics" in res
        assert "platform_metrics" in res
        assert "agent_metrics" in res
        assert "cost" in res
        assert res["platform_metrics"]["registered_users"] >= 0
        assert res["platform_metrics"]["indexed_chunks"] >= 0

@pytest.mark.asyncio
async def test_analytics_quality_metrics(dummy_user):
    async with AsyncSessionLocal() as db:
        res = await analytics_quality(current_user=dummy_user, db=db)
        assert "evaluation" in res
        eval_data = res["evaluation"]
        assert eval_data.get("total_evaluations", 0) >= 0

@pytest.mark.asyncio
async def test_analytics_routing_tiers(dummy_user):
    async with AsyncSessionLocal() as db:
        res = await analytics_routing(current_user=dummy_user, db=db)
        assert "cost_summary" in res
        assert "tier_distribution" in res
        assert "intent_distribution" in res
        for item in res["tier_distribution"]:
            assert item["tier"] in ("slm", "llm-medium", "llm-strong")

@pytest.mark.asyncio
async def test_analytics_retrieval_metrics(dummy_user):
    async with AsyncSessionLocal() as db:
        res = await analytics_retrieval(current_user=dummy_user, db=db)
        assert "knowledge_base" in res
        assert res["knowledge_base"]["indexed_chunks"] >= 0
        assert res["empty_retrieval_rate"] <= 1.0

@pytest.mark.asyncio
async def test_system_health(dummy_user):
    res = await system_health(current_user=dummy_user)
    assert "components" in res
    assert "overall" in res
    assert "vector_store" in res["components"]
    assert "primary_database" in res["components"]

@pytest.mark.asyncio
async def test_drift_report(dummy_user):
    res = await drift_report(baseline_hours=24, current_hours=1, current_user=dummy_user)
    assert "available" in res
    if res["available"]:
        assert "dimensions" in res
        assert "overall_status" in res

@pytest.mark.asyncio
async def test_recent_telemetry(dummy_user):
    async with AsyncSessionLocal() as db:
        res = await recent_telemetry(limit=10, current_user=dummy_user, db=db)
        assert "records" in res
        assert isinstance(res["records"], list)
