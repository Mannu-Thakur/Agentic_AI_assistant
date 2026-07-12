import pytest
import httpx
from httpx import AsyncClient
from app.main import app
from app.core.database import get_db

@pytest.mark.anyio
async def test_register_and_login_flow(override_get_db):
    # Override database dependency in FastAPI
    app.dependency_overrides[get_db] = override_get_db

    transport = httpx.ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Register a user
        reg_payload = {
            "email": "testuser@example.com",
            "password": "strongpassword123",
            "full_name": "Test User"
        }
        res_reg = await ac.post("/api/v1/auth/register", json=reg_payload)
        assert res_reg.status_code == 201
        data_reg = res_reg.json()
        assert data_reg["email"] == "testuser@example.com"
        assert data_reg["full_name"] == "Test User"
        assert "id" in data_reg

        # 2. Register again (should fail)
        res_dup = await ac.post("/api/v1/auth/register", json=reg_payload)
        assert res_dup.status_code == 400
        assert res_dup.json()["detail"] == "Email already registered"

        # 3. Login
        login_payload = {
            "email": "testuser@example.com",
            "password": "strongpassword123"
        }
        res_login = await ac.post("/api/v1/auth/login", json=login_payload)
        assert res_login.status_code == 200
        data_login = res_login.json()
        assert "access_token" in data_login
        assert data_login["token_type"] == "bearer"
        
        # Check refresh token cookie is set
        assert "refresh_token" in res_login.cookies
        
        # 4. Get Current User profile (authorized)
        token = data_login["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        res_me = await ac.get("/api/v1/auth/me", headers=headers)
        assert res_me.status_code == 200
        assert res_me.json()["email"] == "testuser@example.com"

        # 5. Get Profile with invalid token (should fail)
        headers_invalid = {"Authorization": "Bearer invalidtoken"}
        res_me_fail = await ac.get("/api/v1/auth/me", headers=headers_invalid)
        assert res_me_fail.status_code == 401

    # Clean up overrides
    app.dependency_overrides.clear()
