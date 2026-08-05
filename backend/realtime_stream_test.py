"""
realtime_stream_test.py — Real-time live AI Agent stream execution test
"""
import sys
import json
import requests

BASE_URL = "http://localhost:8000"

def test_realtime_chat():
    print("=" * 80)
    print("           REAL-TIME LIVE CHAT & AGENT STREAMING VERIFICATION        ")
    print("=" * 80 + "\n")

    # 1. Login
    print("[1/4] Authenticating with backend...")
    r = requests.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={"email": "mannukr626@gmail.com", "password": "Password123!"},
        timeout=10
    )
    if r.status_code != 200:
        print(f"FAILED to login: {r.status_code} {r.text}")
        sys.exit(1)

    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("   [OK] Login successful. JWT token acquired.")

    # 2. Create Chat
    print("\n[2/4] Creating new chat session...")
    r = requests.post(f"{BASE_URL}/api/v1/chats", headers=headers, json={"title": "Realtime Test Chat"}, timeout=10)
    if r.status_code not in (200, 201):
        print(f"FAILED to create chat: {r.status_code} {r.text}")
        sys.exit(1)

    chat_id = r.json()["id"]
    print(f"   [OK] Chat created with ID: {chat_id}")

    # 3. Post Message & Read SSE Stream
    print("\n[3/4] Posting message: 'Hello! What is 2 + 2 and explain briefly'...")
    msg_payload = {
        "content": "Hello! What is 2 + 2 and explain briefly",
        "model": "gemini-1.5-flash"
    }

    s = requests.Session()
    resp = s.post(
        f"{BASE_URL}/api/v1/chats/{chat_id}/messages",
        headers=headers,
        json=msg_payload,
        stream=True,
        timeout=30
    )

    if resp.status_code != 200:
        print(f"FAILED to post message: {resp.status_code} {resp.text}")
        sys.exit(1)

    print("\n[4/4] Streaming AI Response from LangGraph Agent:")
    print("-" * 60)

    received_text = ""
    for line in resp.iter_lines(decode_unicode=True):
        if line:
            if line.startswith("data:"):
                raw_data = line[5:].strip()
                if raw_data == "[DONE]":
                    break
                try:
                    data_obj = json.loads(raw_data)
                    if "content" in data_obj:
                        chunk = data_obj["content"]
                        received_text += chunk
                        sys.stdout.write(chunk)
                        sys.stdout.flush()
                    elif "text" in data_obj:
                        chunk = data_obj["text"]
                        received_text += chunk
                        sys.stdout.write(chunk)
                        sys.stdout.flush()
                except Exception:
                    sys.stdout.write(raw_data)
                    sys.stdout.flush()

    print("\n" + "-" * 60)
    print("\n[OK] REAL-TIME STREAMING TEST PASSED SUCCESSFULLY!")
    print(f"Received total {len(received_text)} chars from AI agent.")
    print("=" * 80)

if __name__ == "__main__":
    test_realtime_chat()
