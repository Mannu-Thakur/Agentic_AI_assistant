"""
realtime_complex_test.py — Real-time test of Complex, Ambiguous, and Mixed Statement Query Execution
"""

import sys
import json
import requests
import time

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

BASE_URL = "http://127.0.0.1:8000"

def test_complex_mixed_query():
    print("=" * 85)
    print("      REAL-TIME COMPLEX, AMBIGUOUS & MIXED QUERY PIPELINE VERIFICATION      ")
    print("=" * 85)

    # 1. Login with test user (which has verified API keys configured)
    auth_payload = {"email": "test_user_realtime@example.com", "password": "Password123!"}
    
    r = requests.post(f"{BASE_URL}/api/v1/auth/login", json=auth_payload, timeout=10)
    if r.status_code != 200:
        print(f"[ERROR] Auth failed: {r.status_code} {r.text}")
        return False

    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("  [1/4] [OK] Authenticated successfully as test_user_realtime@example.com.")

    # 2. Create Chat Session
    r_chat = requests.post(
        f"{BASE_URL}/api/v1/chats",
        headers=headers,
        json={"title": "Complex Ambiguous Mixed Query Test"},
        timeout=10
    )
    if r_chat.status_code not in (200, 201):
        print(f"[ERROR] Failed to create chat: {r_chat.status_code} {r_chat.text}")
        return False

    chat_id = r_chat.json()["id"]
    print(f"  [2/4] [OK] Chat session created. ID: {chat_id}")

    # 3. Post Complex Mixed Query
    complex_query = (
        "Hey! Just so you know, I am launching a new product called 'NovaAI' in October. "
        "Also, I bought some server gear at BestBuy for $249.99 today—can you record this expense? "
        "If my monthly cloud budget is $800, calculate how much budget I have left after this purchase. "
        "And finally, search online for what new features were added to Python in recent releases and summarize them."
    )

    print(f"\n  [3/4] Posting Complex Multi-Intent Query:")
    print(f"        \"{complex_query}\"\n")
    print("  [4/4] Streaming Agent Execution Pipeline (SSE Event Stream)...")
    print("-" * 75)

    msg_payload = {
        "content": complex_query,
        "model": "gemini-1.5-flash"
    }

    s = requests.Session()
    resp = s.post(
        f"{BASE_URL}/api/v1/chats/{chat_id}/messages",
        headers=headers,
        json=msg_payload,
        stream=True,
        timeout=120
    )

    if resp.status_code != 200:
        print(f"[ERROR] HTTP {resp.status_code}: {resp.text}")
        return False

    full_response = ""
    steps_received = []

    for line in resp.iter_lines(decode_unicode=True):
        if not line:
            continue

        if line.startswith("data:"):
            raw_data = line[5:].strip()
            if raw_data == "[DONE]":
                print("\n\n[SSE STREAM COMPLETED: [DONE]]")
                break

            try:
                data_obj = json.loads(raw_data)
                event_type = data_obj.get("event")

                if event_type == "step":
                    step_msg = data_obj.get("step", "")
                    steps_received.append(step_msg)
                    print(f"\n[PIPELINE STEP] {step_msg}")
                elif event_type == "chunk":
                    chunk_text = data_obj.get("text", "")
                    full_response += chunk_text
                    sys.stdout.write(chunk_text)
                    sys.stdout.flush()
                elif event_type == "metrics":
                    metrics = data_obj.get("metrics", {})
                    print(f"\n\n[TELEMETRY & METRICS]")
                    print(f"   Model Used    : {metrics.get('model_used')}")
                    print(f"   Latency       : {metrics.get('latency_ms')} ms")
                    print(f"   Steps Executed: {metrics.get('steps')}")
                elif event_type == "error":
                    print(f"\n[ERROR] {data_obj.get('detail')}")
                else:
                    sys.stdout.write(raw_data)
                    sys.stdout.flush()

            except json.JSONDecodeError:
                sys.stdout.write(raw_data)
                sys.stdout.flush()

    print("\n" + "-" * 75)
    print(f"\n[RESULT SUMMARY]")
    print(f"  Total Generated Text : {len(full_response)} characters")
    print(f"  Pipeline Steps Count : {len(steps_received)}")
    print(f"  Steps History        : {steps_received}")

    # Check user memories to see if the implicit memory was saved to DB
    r_mem = requests.get(f"{BASE_URL}/api/v1/memories", headers=headers, timeout=10)
    if r_mem.status_code == 200:
        memories = r_mem.json()
        print(f"\n[PERSISTED USER MEMORIES IN DB] ({len(memories)} items found)")
        for m in memories:
            print(f"   • Category: {m.get('category')} | Content: {m.get('content')}")

    return len(full_response) > 0


if __name__ == "__main__":
    success = test_complex_mixed_query()
    print("\n" + "=" * 85)
    print(f" COMPLEX PIPELINE TEST: {'PASSED [SUCCESS]' if success else 'FAILED'}")
    print("=" * 85 + "\n")
