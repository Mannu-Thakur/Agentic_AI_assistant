import pytest
import json
from unittest.mock import AsyncMock
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.models.user import User
from app.api.auth import get_current_user

@pytest.fixture
def auth_user():
    return User(id="smoke-test-user-id", email="smoke@example.com", is_active=True)

@pytest.mark.anyio
async def test_smoke_health_and_readiness():
    """Verify health and readiness endpoints respond 200."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "healthy" or "status" in data

        readiness_resp = await client.get("/api/v1/health/readiness")
        assert readiness_resp.status_code in (200, 503)  # 200 ready, or 503 if redis optional down


@pytest.mark.anyio
async def test_provider_health_checks_configured_openai(monkeypatch):
    """The provider health matrix must include OpenAI and surface degraded status."""
    from app.api import health as health_api

    class RateLimitedResponse:
        status_code = 429

    class MockAsyncClient:
        def __init__(self, timeout):
            assert timeout == health_api._TIMEOUT

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, headers):
            assert url == "https://api.openai.com/v1/models"
            assert headers == {"Authorization": "Bearer configured-test-key"}
            return RateLimitedResponse()

    monkeypatch.setattr(health_api.settings, "GEMINI_API_KEY", None)
    monkeypatch.setattr(health_api.settings, "GROQ_API_KEY", None)
    monkeypatch.setattr(health_api.settings, "OPENAI_API_KEY", "configured-test-key")
    monkeypatch.setattr(health_api.settings, "OPENROUTER_API_KEY", None)
    monkeypatch.setattr(health_api.httpx, "AsyncClient", MockAsyncClient)
    monkeypatch.setattr(
        health_api,
        "_check_redis",
        AsyncMock(return_value={"status": "unconfigured"}),
    )

    result = await health_api.provider_health()

    assert result["providers"]["openai"]["status"] == "degraded"
    assert result["providers"]["openai"]["http_status"] == 429
    assert result["overall"] == "degraded"


@pytest.mark.anyio
async def test_smoke_workspace_usage_metrics(auth_user):
    """Verify workspace usage metrics return valid counts."""
    app.dependency_overrides[get_current_user] = lambda: auth_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/metrics/usage")
            assert resp.status_code == 200
            data = resp.json()
            assert "total_conversations" in data
            assert "total_messages" in data
            assert "total_documents" in data
            assert isinstance(data["total_conversations"], int)
            assert isinstance(data["total_messages"], int)
            assert isinstance(data["total_documents"], int)
    finally:
        app.dependency_overrides.pop(get_current_user, None)

@pytest.mark.anyio
async def test_smoke_git_endpoints(auth_user):
    """Verify public deployment does not expose host Git state to ordinary users."""
    app.dependency_overrides[get_current_user] = lambda: auth_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            status_resp = await client.get("/api/v1/git/status")
            assert status_resp.status_code == 403

            commit_resp = await client.post("/api/v1/git/commit-suggestion")
            assert commit_resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)

@pytest.mark.anyio
async def test_smoke_chat_with_search_modes(auth_user):
    """Verify chat session creation and message posting with search_mode parameters."""
    app.dependency_overrides[get_current_user] = lambda: auth_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Create a chat session
            create_resp = await client.post(
                "/api/v1/chats",
                json={"title": "Smoke Test Search Modes"}
            )
            assert create_resp.status_code in (200, 201)
            chat_id = create_resp.json()["id"]

            # 2. Test sending a message with search_mode='web'
            web_msg_resp = await client.post(
                f"/api/v1/chats/{chat_id}/messages",
                json={
                    "content": "What is the latest quantum computing breakthrough?",
                    "model": "openai/gpt-oss-120b",
                    "search_mode": "web"
                },
                headers={"x-api-keys": json.dumps({"groq": "mock_groq_key"})}
            )
            # Response is a streaming event stream or error stream, but HTTP status must be 200
            assert web_msg_resp.status_code == 200

            # 3. Test sending a message with search_mode='kb'
            kb_msg_resp = await client.post(
                f"/api/v1/chats/{chat_id}/messages",
                json={
                    "content": "Summarize key points from my documents",
                    "model": "openai/gpt-oss-120b",
                    "search_mode": "kb"
                },
                headers={"x-api-keys": json.dumps({"groq": "mock_groq_key"})}
            )
            assert kb_msg_resp.status_code == 200

            # 4. Test sending a message with search_mode='hybrid'
            hybrid_msg_resp = await client.post(
                f"/api/v1/chats/{chat_id}/messages",
                json={
                    "content": "Compare quantum computing trends with my notes",
                    "model": "openai/gpt-oss-120b",
                    "search_mode": "hybrid"
                },
                headers={"x-api-keys": json.dumps({"groq": "mock_groq_key"})}
            )
            assert hybrid_msg_resp.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
@pytest.mark.anyio
async def test_smoke_pin_and_star_chat(auth_user):
    """Verify PATCH /chats/{id} correctly updates is_pinned and is_favorite fields."""
    app.dependency_overrides[get_current_user] = lambda: auth_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Create a chat
            create_resp = await client.post("/api/v1/chats", json={"title": "Pin Test Chat"})
            assert create_resp.status_code in (200, 201)
            chat_id = create_resp.json()["id"]

            # Pin the chat
            pin_resp = await client.patch(f"/api/v1/chats/{chat_id}", json={"is_pinned": True})
            assert pin_resp.status_code == 200
            assert pin_resp.json()["is_pinned"] is True
            assert pin_resp.json()["id"] == chat_id

            # Star (favorite) the chat
            star_resp = await client.patch(f"/api/v1/chats/{chat_id}", json={"is_favorite": True})
            assert star_resp.status_code == 200
            assert star_resp.json()["is_favorite"] is True

            # Unpin the chat
            unpin_resp = await client.patch(f"/api/v1/chats/{chat_id}", json={"is_pinned": False})
            assert unpin_resp.status_code == 200
            assert unpin_resp.json()["is_pinned"] is False

            # Combined update: title + pin
            combo_resp = await client.patch(
                f"/api/v1/chats/{chat_id}",
                json={"title": "Renamed & Pinned", "is_pinned": True}
            )
            assert combo_resp.status_code == 200
            assert combo_resp.json()["title"] == "Renamed & Pinned"
            assert combo_resp.json()["is_pinned"] is True

            # 404 for non-existent chat
            missing_resp = await client.patch(
                "/api/v1/chats/nonexistent-chat-id",
                json={"is_pinned": True}
            )
            assert missing_resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.anyio
async def test_api_prefix_normalization_and_mission_endpoints(auth_user, monkeypatch):
    """Verify ASGI normalizer transparently rewrites duplicate /api/v1 prefixes and mission routes work."""
    from app.api.mission import job_queue
    monkeypatch.setattr(job_queue, "user_jobs", AsyncMock(return_value=[]))
    app.dependency_overrides[get_current_user] = lambda: auth_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Normal health check
            r1 = await client.get("/api/v1/health")
            assert r1.status_code == 200

            # 2. Duplicate prefix normalized transparently (not 404!)
            r2 = await client.get("/api/v1/api/v1/health")
            assert r2.status_code == 200
            assert r2.json()["status"] == r1.json()["status"]

            # 3. Mission list endpoint with normal prefix
            r3 = await client.get("/api/v1/mission/")
            assert r3.status_code == 200
            assert "missions" in r3.json()

            # 4. Mission list endpoint with duplicate prefix normalized
            r4 = await client.get("/api/v1/api/v1/mission/")
            assert r4.status_code == 200
            assert r4.json() == r3.json()
    finally:
        app.dependency_overrides.pop(get_current_user, None)

