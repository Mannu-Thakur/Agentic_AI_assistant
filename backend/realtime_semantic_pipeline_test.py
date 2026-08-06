"""
realtime_semantic_pipeline_test.py — Real-time test of Semantic Tool Routing & Agent Execution Pipeline
"""

import sys
import json
import requests
import time

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

BASE_URL = "http://127.0.0.1:8000"

def run_realtime_test(query: str, test_name: str, model_name: str = "gemini-1.5-flash"):
    print("\n" + "=" * 80)
    print(f" TEST SUITE: {test_name.upper()}")
    print(f" QUERY: '{query}'")
    print(f" MODEL: '{model_name}'")
    print("=" * 80)

    # 1. Login
    auth_payload = {"email": "test_user_realtime@example.com", "password": "Password123!"}
    
    r = requests.post(f"{BASE_URL}/api/v1/auth/login", json=auth_payload, timeout=10)
    if r.status_code != 200:
        print(f"[ERROR] Auth failed: {r.status_code} {r.text}")
        return False

    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("  [OK] Authenticated successfully as test_user_realtime@example.com. JWT token acquired.")

    # 2. Create Chat Session
    r_chat = requests.post(
        f"{BASE_URL}/api/v1/chats",
        headers=headers,
        json={"title": f"Realtime Test - {test_name}"},
        timeout=10
    )
    if r_chat.status_code not in (200, 201):
        print(f"[ERROR] Failed to create chat: {r_chat.status_code} {r_chat.text}")
        return False

    chat_id = r_chat.json()["id"]
    print(f"  [OK] Chat session created. Chat ID: {chat_id}")

    # 3. Stream query execution from agent pipeline
    print(f"\n  --> Streaming real-time pipeline execution...\n")
    print("-" * 70)

    msg_payload = {
        "content": query,
        "model": model_name
    }

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
                    print(f"\n[AGENT PIPELINE STEP] {step_msg}")
                elif event_type == "chunk":
                    chunk_text = data_obj.get("text", "")
                    full_response += chunk_text
                    sys.stdout.write(chunk_text)
                    sys.stdout.flush()
                elif event_type == "metrics":
                    print(f"\n[METRICS] {data_obj.get('metrics')}")
                elif event_type == "error":
                    print(f"\n[ERROR] {data_obj.get('detail')}")
                else:
                    sys.stdout.write(raw_data)
                    sys.stdout.flush()

            except json.JSONDecodeError:
                sys.stdout.write(raw_data)
                sys.stdout.flush()

    print("\n" + "-" * 70)
    print(f"  [SUMMARY] Total response length: {len(full_response)} characters")
    print(f"  [STEPS EXECUTED] {steps_received}")
    return len(full_response) > 0


if __name__ == "__main__":
    print("\n==========================================================================")
    print("      REAL-TIME END-TO-END PIPELINE & SEMANTIC ROUTER TEST      ")
    print("==========================================================================")

    # Test 1: Expense logging (Semantic Tool Selection -> add_expense)
    q1 = "I spent $42.50 on a team lunch at Chipotle today. Please log this expense."
    t1 = run_realtime_test(q1, "Expense Logging (Semantic Tool Routing)", model_name="gemini-1.5-flash")

    # Test 2: Math calculation (Semantic Tool Selection -> calculate)
    q2 = "Calculate 2^16 + 500 * 12.5 and give me the exact result."
    t2 = run_realtime_test(q2, "Math Computation (Semantic Tool Routing)", model_name="gemini-1.5-flash")

    print("\n==========================================================================")
    print(f" OVERALL REAL-TIME TEST RESULT: {'PASSED [SUCCESS]' if (t1 and t2) else 'FAILED'}")
    print("==========================================================================\n")
