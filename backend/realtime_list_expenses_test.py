"""
realtime_list_expenses_test.py — Test asking for all spends / expense summary
"""

import sys
import json
import requests

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

BASE_URL = "http://127.0.0.1:8000"

def test_get_all_spends():
    print("=" * 80)
    print("       REAL-TIME TEST: RETRIEVING ALL RECORDED SPENDS & EXPENSES       ")
    print("=" * 80)

    # 1. Login
    auth_payload = {"email": "test_user_realtime@example.com", "password": "Password123!"}
    r = requests.post(f"{BASE_URL}/api/v1/auth/login", json=auth_payload, timeout=10)
    if r.status_code != 200:
        print(f"[ERROR] Auth failed: {r.status_code} {r.text}")
        return False

    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("  [1/3] [OK] Authenticated as test_user_realtime@example.com.")

    # 2. Create Chat
    r_chat = requests.post(
        f"{BASE_URL}/api/v1/chats",
        headers=headers,
        json={"title": "List All Spends Test"},
        timeout=10
    )
    chat_id = r_chat.json()["id"]
    print(f"  [2/3] [OK] Chat session created. ID: {chat_id}")

    # 3. Post Query asking for all spends
    query = "Show me all my recorded spends and expenses, and give me a category breakdown."
    print(f"\n  [3/3] Querying: '{query}'\n")
    print("-" * 75)

    msg_payload = {"content": query, "model": "gemini-1.5-flash"}
    s = requests.Session()
    resp = s.post(
        f"{BASE_URL}/api/v1/chats/{chat_id}/messages",
        headers=headers,
        json=msg_payload,
        stream=True,
        timeout=90
    )

    if resp.status_code != 200:
        print(f"[ERROR] HTTP {resp.status_code}: {resp.text}")
        return False

    full_response = ""
    for line in resp.iter_lines(decode_unicode=True):
        if not line:
            continue
        if line.startswith("data:"):
            raw_data = line[5:].strip()
            if raw_data == "[DONE]":
                break
            try:
                data_obj = json.loads(raw_data)
                event_type = data_obj.get("event")
                if event_type == "step":
                    print(f"\n[PIPELINE STEP] {data_obj.get('step')}")
                elif event_type == "chunk":
                    text = data_obj.get("text", "")
                    full_response += text
                    sys.stdout.write(text)
                    sys.stdout.flush()
                elif event_type == "metrics":
                    print(f"\n\n[METRICS] {data_obj.get('metrics')}")
            except Exception:
                pass

    print("\n" + "-" * 75)
    print(f"\n[TOTAL RESPONSE LENGTH] {len(full_response)} characters")
    return len(full_response) > 0

if __name__ == "__main__":
    test_get_all_spends()
