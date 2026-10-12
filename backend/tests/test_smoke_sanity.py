import pytest
import json
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
    """Verify git status inspection and commit assistant endpoints."""
    app.dependency_overrides[get_current_user] = lambda: auth_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            status_resp = await client.get("/api/v1/git/status")
            assert status_resp.status_code == 200
            status_data = status_resp.json()
            assert status_data["git_installed"] is True
            assert status_data["is_repo"] is True
            assert status_data["branch"] is not None

            commit_resp = await client.post("/api/v1/git/commit-suggestion")
            assert commit_resp.status_code == 200
            commit_data = commit_resp.json()
            assert commit_data["success"] is True
            assert "suggested_message" in commit_data
            assert len(commit_data["suggested_message"]) > 0
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
                    "model": "llama-3.3-70b-versatile",
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
                    "model": "llama-3.3-70b-versatile",
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
                    "model": "llama-3.3-70b-versatile",
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
