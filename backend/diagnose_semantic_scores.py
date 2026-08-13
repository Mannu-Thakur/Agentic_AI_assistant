"""
backend/diagnose_semantic_scores.py — Diagnostic Script for Raw Tool Relevance Scores.

Calculates real mathematical cosine similarity and schema match scores across
competing tools for ambiguous, related, and completely unrelated queries.
"""

import math
import asyncio
import hashlib

def _pseudo_embedding(text: str, dim: int = 128) -> list[float]:
    """Generates a deterministic pseudo-vector based on text content hash for diagnostic tracing."""
    vec = []
    text_lower = text.lower()
    for i in range(dim):
        h = hashlib.sha256(f"{text_lower}:{i}".encode('utf-8')).hexdigest()
        val = (int(h[:8], 16) / 0xFFFFFFFF) * 2.0 - 1.0
        vec.append(val)
    # Normalize vector to unit length
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec]

def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot = sum(a * b for a, b in zip(vec1, vec2))
    return dot  # vectors are unit normalized

TOOLS = [
    {
        "name": "calculate",
        "description": "Evaluates mathematical expressions and performs numerical calculations."
    },
    {
        "name": "web_search",
        "description": "Searches the web for real-time news, current events, and live information."
    },
    {
        "name": "web_fetch",
        "description": "Fetches raw HTML content from a target URL web page."
    },
    {
        "name": "add_expense",
        "description": "Logs financial expense transactions into user budget database."
    },
    {
        "name": "send_email",
        "description": "Sends email messages to specified recipient address."
    }
]

TEST_QUERIES = [
    ("Please calculate 4096 * 16 - 350", "Specific Math Query"),
    ("What is the latest score of the World Championship?", "Web Search Query"),
    ("I spent $45 on lunch today", "Expense Query"),
    ("Write a 4-line poem about the ocean breeze", "Unrelated Creative Query"),
    ("Fetch the webpage https://example.com and send an email summary", "Ambiguous Multi-Tool Query"),
]

def score_query(query: str):
    print("\n" + "="*70)
    print(f" QUERY: \"{query}\"")
    print("="*70)

    q_vec = _pseudo_embedding(query)
    query_words = set(w.strip("?,!.:;") for w in query.lower().split())

    scored = []
    for tool in TOOLS:
        t_name = tool["name"]
        t_desc = tool["description"]
        t_vec = _pseudo_embedding(f"Tool: {t_name}. Description: {t_desc}")

        sim = _cosine_similarity(q_vec, t_vec)
        
        # Schema token overlap score
        text_combo = f"{t_name} {t_desc}".lower()
        keyword_matches = sum(1 for w in query_words if len(w) > 2 and w in text_combo)
        keyword_score = min(keyword_matches * 0.25, 0.90)

        final_score = max(sim, keyword_score)
        scored.append((t_name, round(sim, 4), round(keyword_score, 4), round(final_score, 4)))

    scored.sort(key=lambda x: x[3], reverse=True)

    print(f" {'Tool Name':<20} | {'Cosine Sim':<12} | {'Token Match':<12} | {'Final Score':<12}")
    print(" " + "-"*62)
    for t_name, sim, kw_score, final_score in scored:
        print(f" {t_name:<20} | {sim:<12.4f} | {kw_score:<12.4f} | {final_score:<12.4f}")

    top_tool, top_sim, top_kw, confidence = scored[0]
    print(" " + "-"*62)
    print(f" Selected Tool: {top_tool}")
    print(f" Confidence Score: {confidence:.4f}")

if __name__ == "__main__":
    for q, desc in TEST_QUERIES:
        score_query(q)
