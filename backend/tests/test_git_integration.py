import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.models.user import User

@pytest.fixture
def test_user():
    return User(id="test-git-user-uuid", email="git_test@example.com", is_active=True)

@pytest.mark.anyio
async def test_git_status_endpoint(test_user):
    from app.api.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/git/status")
            assert resp.status_code == 200
            data = resp.json()
            assert "git_installed" in data
            assert "is_repo" in data
            if data["git_installed"] and data["is_repo"]:
                assert "branch" in data
                assert "is_clean" in data
    finally:
        app.dependency_overrides.pop(get_current_user, None)

@pytest.mark.anyio
async def test_git_commit_suggestion_endpoint(test_user):
    from app.api.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v1/git/commit-suggestion")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert "suggested_message" in data
            assert isinstance(data["suggested_message"], str)
            assert len(data["suggested_message"]) > 0
    finally:
        app.dependency_overrides.pop(get_current_user, None)
