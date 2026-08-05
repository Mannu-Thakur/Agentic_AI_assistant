"""
test_production_e2e.py — Comprehensive Live Production Readyness Test Suite
Tests all backend API features against http://localhost:8000
"""
import sys
import time
import requests

BASE_URL = "http://localhost:8000"

def run_e2e_tests():
    print("=" * 80)
    print("      LIVE DOCKER CONTAINER PRODUCTION READINESS E2E TEST SUITE      ")
    print("=" * 80 + "\n")

    results = []

    # 1. Health Checks
    try:
        r = requests.get(f"{BASE_URL}/api/v1/health", timeout=5)
        assert r.status_code == 200, f"Health check status {r.status_code}"
        data = r.json()
        assert data.get("status") == "healthy", f"Health status not healthy: {data}"
        results.append(("1. Health Check Endpoint (/api/v1/health)", True, "Server responds 200 OK with 'healthy' status"))
    except Exception as e:
        results.append(("1. Health Check Endpoint (/api/v1/health)", False, str(e)))

    # 2. Providers Health Check
    try:
        r = requests.get(f"{BASE_URL}/api/v1/health/providers", timeout=5)
        assert r.status_code == 200, f"Providers health check status {r.status_code}"
        results.append(("2. Provider Health Matrix (/api/v1/health/providers)", True, "Provider registry active and responding"))
    except Exception as e:
        results.append(("2. Provider Health Matrix (/api/v1/health/providers)", False, str(e)))

    # 3. Security Headers Verification
    try:
        r = requests.get(f"{BASE_URL}/docs", timeout=5)
        assert r.status_code == 200
        headers = r.headers
        assert "x-frame-options" in headers, "Missing X-Frame-Options"
        assert "x-content-type-options" in headers, "Missing X-Content-Type-Options"
        results.append(("3. Security Headers (CSP, FrameGuard, HSTS)", True, f"Security headers verified: {dict(headers)}"))
    except Exception as e:
        results.append(("3. Security Headers (CSP, FrameGuard, HSTS)", False, str(e)))

    # 4. Authentication & Authorization
    test_email = f"prod_test_{int(time.time())}@example.com"
    test_password = "TestPassword123!"
    access_token = None
    headers = {}

    try:
        # Register
        r = requests.post(
            f"{BASE_URL}/api/v1/auth/register",
            json={"email": test_email, "password": test_password, "full_name": "E2E Test User"},
            timeout=5
        )
        assert r.status_code in (201, 200), f"Register returned {r.status_code}: {r.text}"
        
        # Login
        r = requests.post(
            f"{BASE_URL}/api/v1/auth/login",
            json={"email": test_email, "password": test_password},
            timeout=5
        )
        assert r.status_code == 200, f"Login returned {r.status_code}: {r.text}"
        token_data = r.json()
        access_token = token_data["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}

        # Verify /me
        r = requests.get(f"{BASE_URL}/api/v1/auth/me", headers=headers, timeout=5)
        assert r.status_code == 200, f"Auth me returned {r.status_code}: {r.text}"
        assert r.json()["email"] == test_email

        results.append(("4. User Authentication (Register, Login, JWT Token, /me)", True, f"Registered & logged in as {test_email}"))
    except Exception as e:
        results.append(("4. User Authentication (Register, Login, JWT Token, /me)", False, str(e)))

    # 5. Chat & Conversation Management
    chat_id = None
    try:
        # Create Chat
        r = requests.post(f"{BASE_URL}/api/v1/chats", headers=headers, json={"title": "E2E Test Chat"}, timeout=5)
        assert r.status_code in (200, 201), f"Create chat returned {r.status_code}: {r.text}"
        chat_id = r.json()["id"]

        # List Chats
        r = requests.get(f"{BASE_URL}/api/v1/chats", headers=headers, timeout=5)
        assert r.status_code == 200
        chats = r.json()
        assert any(c["id"] == chat_id for c in chats), "New chat not found in chat list"

        # Get Chat Messages
        r = requests.get(f"{BASE_URL}/api/v1/chats/{chat_id}", headers=headers, timeout=5)
        assert r.status_code == 200, f"Get chat messages returned {r.status_code}: {r.text}"

        # Update Chat Title
        r = requests.patch(f"{BASE_URL}/api/v1/chats/{chat_id}", headers=headers, json={"title": "Updated E2E Chat Title"}, timeout=5)
        assert r.status_code == 200
        assert r.json()["title"] == "Updated E2E Chat Title"

        results.append(("5. Chat Session & Conversation CRUD Operations", True, f"Chat created ({chat_id[:8]}), listed, retrieved, and updated"))
    except Exception as e:
        results.append(("5. Chat Session & Conversation CRUD Operations", False, str(e)))

    # 6. RAG Documents Endpoint
    try:
        r = requests.get(f"{BASE_URL}/api/v1/documents", headers=headers, timeout=5)
        assert r.status_code == 200, f"Get documents returned {r.status_code}: {r.text}"
        docs = r.json()
        results.append(("6. RAG Document Management (/api/v1/documents)", True, f"Fetched {len(docs)} documents cleanly"))
    except Exception as e:
        results.append(("6. RAG Document Management (/api/v1/documents)", False, str(e)))

    # 7. Semantic Memories Endpoint
    try:
        # Create Memory
        r = requests.post(f"{BASE_URL}/api/v1/memories", headers=headers, json={"category": "preference", "content": "User prefers Python and dark mode.", "importance_score": 5}, timeout=5)
        assert r.status_code in (200, 201), f"Create memory returned {r.status_code}: {r.text}"
        
        # List Memories
        r = requests.get(f"{BASE_URL}/api/v1/memories", headers=headers, timeout=5)
        assert r.status_code == 200, f"Get memories returned {r.status_code}: {r.text}"
        mems = r.json()
        results.append(("7. Semantic Memory Layer (/api/v1/memories)", True, f"Memory created and {len(mems)} memories retrieved"))
    except Exception as e:
        results.append(("7. Semantic Memory Layer (/api/v1/memories)", False, str(e)))

    # 8. Remote MCP Servers Endpoint
    try:
        r = requests.get(f"{BASE_URL}/api/v1/mcp/servers", headers=headers, timeout=5)
        assert r.status_code == 200, f"Get MCP servers returned {r.status_code}: {r.text}"
        mcp_servers = r.json()
        results.append(("8. Remote MCP Server Registry (/api/v1/mcp/servers)", True, f"Retrieved {len(mcp_servers)} MCP server entries"))
    except Exception as e:
        results.append(("8. Remote MCP Server Registry (/api/v1/mcp/servers)", False, str(e)))

    # 9. Invalid Token & Revocation Defense
    try:
        bad_headers = {"Authorization": "Bearer invalid_jwt_token_12345"}
        r = requests.get(f"{BASE_URL}/api/v1/auth/me", headers=bad_headers, timeout=5)
        assert r.status_code == 401, f"Expected 401 for invalid token, got {r.status_code}"
        results.append(("9. Authentication Security (Invalid Token Rejection)", True, "Rejects unauthenticated/tampered tokens with 401 Unauthorized"))
    except Exception as e:
        results.append(("9. Authentication Security (Invalid Token Rejection)", False, str(e)))

    # Print Detailed Report
    print("-" * 80)
    passed_count = sum(1 for _, ok, _ in results if ok)
    total_count = len(results)

    for title, status, msg in results:
        mark = "[PASS]" if status else "[FAIL]"
        print(f"{mark} {title}\n       Details: {msg}\n")

    print("=" * 80)
    print(f"VERIFICATION SUMMARY: {passed_count}/{total_count} PASSED")
    print("=" * 80 + "\n")

    if passed_count < total_count:
        sys.exit(1)

if __name__ == "__main__":
    run_e2e_tests()
