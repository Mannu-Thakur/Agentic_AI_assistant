import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.database import get_db
from app.services.auth_service import AuthService
from app.schemas.auth import UserRegister
from app.core.security import store_reset_token, verify_reset_token, verify_and_consume_reset_token

@pytest.mark.anyio
async def test_forgot_password_and_reset_flow(db_session):
    async def _get_test_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_test_db

    try:
        # 1. Register a test user
        user_schema = UserRegister(
            email="reset_test@example.com",
            password="OldPassword123!",
            full_name="Reset Tester"
        )
        user = await AuthService.create_user(db_session, user_schema)
        assert user.id is not None

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # 2. Request forgot password with custom origin header
            forgot_res = await client.post(
                "/api/v1/auth/forgot-password",
                json={"email": "reset_test@example.com"},
                headers={"Origin": "http://localhost:5174"}
            )
            assert forgot_res.status_code == 200
            assert "If an account exists" in forgot_res.json()["detail"]

            # 3. Test generic response for non-existent email (prevents enumeration)
            unknown_res = await client.post(
                "/api/v1/auth/forgot-password",
                json={"email": "nonexistent_email_12345@example.com"}
            )
            assert unknown_res.status_code == 200
            assert "If an account exists" in unknown_res.json()["detail"]

            # 4. Store a token and test real-time token pre-validation endpoint (/verify-reset-token)
            token = "test_reset_token_xyz_123"
            await store_reset_token(token, user.id, 900)

            # Valid token check
            verify_valid_res = await client.get(f"/api/v1/auth/verify-reset-token?token={token}")
            assert verify_valid_res.status_code == 200
            assert verify_valid_res.json()["valid"] is True

            # Invalid token check
            verify_invalid_res = await client.get("/api/v1/auth/verify-reset-token?token=non_existent_token_999")
            assert verify_invalid_res.status_code == 400

            # 5. Reset with weak password should fail
            weak_res = await client.post(
                "/api/v1/auth/reset-password",
                json={"token": token, "new_password": "short"}
            )
            assert weak_res.status_code == 400

            # 6. Reset with valid new password should succeed
            reset_res = await client.post(
                "/api/v1/auth/reset-password",
                json={"token": token, "new_password": "NewSecurePassword456!"}
            )
            assert reset_res.status_code == 200
            assert "successfully" in reset_res.json()["detail"]

            # 7. Token pre-validation should now fail since token was single-use consumed
            verify_consumed_res = await client.get(f"/api/v1/auth/verify-reset-token?token={token}")
            assert verify_consumed_res.status_code == 400

            # 8. Trying to reset again with the consumed token should fail
            reuse_res = await client.post(
                "/api/v1/auth/reset-password",
                json={"token": token, "new_password": "AnotherPassword789!"}
            )
            assert reuse_res.status_code == 400
            assert "Invalid or expired" in reuse_res.json()["detail"]

            # 9. Verify user can now log in with the new password
            login_res = await client.post(
                "/api/v1/auth/login",
                json={"email": "reset_test@example.com", "password": "NewSecurePassword456!"}
            )
            assert login_res.status_code == 200
            assert "access_token" in login_res.json()
    finally:
        app.dependency_overrides.clear()
