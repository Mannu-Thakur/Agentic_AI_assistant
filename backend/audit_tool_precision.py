"""
backend/audit_tool_precision.py — Forensic Tool Selection Precision & Margin Audit.
"""

import asyncio
import json
import logging
import math
import os
import sys
from typing import Dict, Any, List, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("precision_audit")

from app.tools.registry import ToolRegistry
from app.tools.semantic_router import semantic_router, _cosine_similarity
from app.embeddings.embedding_service import EmbeddingService
from unittest.mock import AsyncMock, patch
import hashlib


def make_deterministic_unit_vector(text: str, dim: int = 768) -> List[float]:
    seed_bytes = hashlib.sha256((text or "").encode("utf-8")).digest()
    state = int.from_bytes(seed_bytes[:4], "big")
    vec = []
    for _ in range(dim):
        state = (state * 1103515245 + 12345) & 0x7fffffff
        val = (state / 0x7fffffff) - 0.5
        vec.append(val)
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm > 0 else [0.0] * dim


# 30 Unseen Audit Queries
AUDIT_QUERIES = [
    # General Knowledge / Conversational (No Tool)
    {"id": 1, "query": "Explain the concept of polymorphism in object-oriented programming.", "intent": "General Knowledge", "target_tools": []},
    {"id": 2, "query": "Write a short creative poem about stars in the night sky.", "intent": "Creative Writing", "target_tools": []},
    {"id": 3, "query": "What is the difference between TCP and UDP?", "intent": "General Knowledge", "target_tools": []},
    
    # Calculation
    {"id": 4, "query": "Calculate 100 * 20", "intent": "Calculation", "target_tools": ["calculate"]},
    {"id": 5, "query": "Compute (450 + 350) / 4", "intent": "Calculation", "target_tools": ["calculate"]},
    
    # Expense Operations
    {"id": 6, "query": "Record a dinner expense of $65.", "intent": "Add Expense", "target_tools": ["add_expense"]},
    {"id": 7, "query": "What are my total expenses for this month?", "intent": "Query Expenses", "target_tools": ["get_expenses", "summarize_expenses"]},
    {"id": 8, "query": "Log an expense of $120 for taxi under Travel category.", "intent": "Add Expense", "target_tools": ["add_expense"]},
    
    # Web Search & Web Fetch
    {"id": 9, "query": "Search for the latest stock price of NVIDIA online.", "intent": "Web Search", "target_tools": ["tavily_search", "web_search"]},
    {"id": 10, "query": "Fetch webpage content from https://example.org and extract text", "intent": "Web Fetch", "target_tools": ["web_fetch", "web_extract"]},
    {"id": 11, "query": "Find recent news updates on Mars rover discoveries", "intent": "Web Search", "target_tools": ["tavily_search", "web_search"]},

    # RAG Document Queries
    {"id": 12, "query": "According to the uploaded document, what is the primary architecture layer?", "intent": "RAG Document QA", "target_tools": []},

    # MCP Actions
    {"id": 13, "query": "Create a reminder for team sync tomorrow at 10 AM.", "intent": "Create Reminder", "target_tools": ["create_reminder"]},
    {"id": 14, "query": "Send an email to john@example.com with meeting notes.", "intent": "Send Email", "target_tools": ["send_email"]},

    # Multi-Tool Requests
    {"id": 15, "query": "Calculate 500 * 12 and search for latest interest rate online", "intent": "Multi-Tool (Calc + Web)", "target_tools": ["calculate", "tavily_search", "web_search"]},
    {"id": 16, "query": "Record a meal expense of $30 and create a reminder to check receipt tomorrow.", "intent": "Multi-Tool (Expense + Reminder)", "target_tools": ["add_expense", "create_reminder"]},

    # Ambiguous / Edge Requests
    {"id": 17, "query": "I need some information on finance and budget planning.", "intent": "Ambiguous Info", "target_tools": []},
    {"id": 18, "query": "Check if there are any updates or notes regarding expenses.", "intent": "Ambiguous Expense", "target_tools": ["get_expenses", "summarize_expenses"]},
    
    # Unseen Niche Topics
    {"id": 19, "query": "What is the thermal conductivity of Graphene at room temperature?", "intent": "Unseen Science", "target_tools": ["tavily_search", "web_search"]},
    {"id": 20, "query": "How do quantum key distribution protocols ensure confidentiality?", "intent": "Unseen Science", "target_tools": []},

    # 10 NEW UNSEEN QUERIES FOR PRECISION RE-AUDIT
    {"id": 21, "query": "Calculate 2 ** 16 + 500", "intent": "Calculation", "target_tools": ["calculate"]},
    {"id": 22, "query": "Log an expense of $45 for groceries", "intent": "Add Expense", "target_tools": ["add_expense"]},
    {"id": 23, "query": "Search web for recent advances in fusion energy research", "intent": "Web Search", "target_tools": ["tavily_search", "web_search"]},
    {"id": 24, "query": "Fetch URL https://python.org and extract documentation", "intent": "Web Fetch", "target_tools": ["web_fetch", "web_extract"]},
    {"id": 25, "query": "Summarize my recorded expenses for food", "intent": "Summarize Expenses", "target_tools": ["summarize_expenses", "get_expenses"]},
    {"id": 26, "query": "Write a short 4-line poem about autumn leaves falling", "intent": "Creative Writing", "target_tools": []},
    {"id": 27, "query": "Calculate 15 * 84 and search online for currency conversion rate", "intent": "Multi-Tool (Calc + Web)", "target_tools": ["calculate", "tavily_search", "web_search"]},
    {"id": 28, "query": "What are the core differences between REST and GraphQL?", "intent": "General Knowledge", "target_tools": []},
    {"id": 29, "query": "Create a reminder to check server backup logs at 5 PM", "intent": "Create Reminder", "target_tools": ["create_reminder"]},
    {"id": 30, "query": "Send an email to team@company.com with project updates", "intent": "Send Email", "target_tools": ["send_email"]},
]


async def run_precision_audit():
    print("\n" + "="*85)
    print("      FORENSIC AUDIT: TOOL-SELECTION PRECISION & MARGIN ANALYSIS (30 QUERIES)")
    print("="*85)

    with patch.object(EmbeddingService, "get_embedding", new_callable=AsyncMock) as mock_emb, \
         patch.object(EmbeddingService, "get_embeddings", new_callable=AsyncMock) as mock_embs:

        mock_emb.side_effect = lambda t, **kw: make_deterministic_unit_vector(t or "")
        mock_embs.side_effect = lambda ts, **kw: [make_deterministic_unit_vector(t or "") for t in ts]

        registry = ToolRegistry()
        await registry.initialize()
        all_schemas = registry.get_all_registered_tool_schemas()

        total_queries = len(AUDIT_QUERIES)
        true_positives = 0
        false_positives = 0
        false_negatives = 0
        true_negatives = 0
        ambiguity_count = 0
        total_selected_count = 0
        total_executed_count = 0

        multi_tool_queries = 0
        multi_tool_successes = 0

        for q_item in AUDIT_QUERIES:
            q_id = q_item["id"]
            q_text = q_item["query"]
            q_target = q_item["target_tools"]

            meta = await semantic_router.select_relevant_tools_with_metadata(
                query=q_text,
                tool_declarations=all_schemas,
                top_k=5,
                min_threshold=0.20
            )

            top_score = meta["top_score"]
            second_score = meta["second_score"]
            margin = meta["score_margin"]
            is_ambiguous = meta["ambiguity"]

            if is_ambiguous:
                ambiguity_count += 1

            selected_candidates = [t["name"] for t in meta["selected_tools"]]
            execution_eligible = [t["name"] for t in meta["execution_eligible_tools"]]

            total_selected_count += len(selected_candidates)
            total_executed_count += len(execution_eligible)

            # Check multi-tool evaluation
            if len(q_target) > 1:
                multi_tool_queries += 1
                if any(t in execution_eligible for t in q_target):
                    multi_tool_successes += 1

            # Classification based on EXECUTION-ELIGIBLE tools
            if not q_target:  # No tool expected
                if len(execution_eligible) == 0:
                    true_negatives += 1
                else:
                    false_positives += len(execution_eligible)
            else:
                for target in q_target:
                    if target in execution_eligible:
                        true_positives += 1
                    else:
                        false_negatives += 1
                for el in execution_eligible:
                    if el not in q_target:
                        false_positives += 1

            fp_tools = [t for t in execution_eligible if q_target and t not in q_target]

            print(f"\n[{q_id:02d}] Query: \"{q_text}\"")
            print(f"     Target Tools:       {q_target}")
            print(f"     Top/2nd/Margin:     {top_score:.4f} / {second_score:.4f} / {margin:.4f} (Ambiguous: {is_ambiguous})")
            print(f"     Selected Candidate: {selected_candidates}")
            print(f"     Execution-Eligible: {execution_eligible}")
            print(f"     False Positives:    {fp_tools}")

        precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 1.0
        recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 1.0
        fp_rate = false_positives / (false_positives + true_negatives) if (false_positives + true_negatives) > 0 else 0.0
        avg_selected = total_selected_count / total_queries
        avg_executed = total_executed_count / total_queries
        multi_tool_rate = (multi_tool_successes / multi_tool_queries * 100) if multi_tool_queries > 0 else 100.0

        print("\n" + "="*85)
        print(" FORENSIC STATISTICAL SUMMARY (AFTER REMEDIATION)")
        print("="*85)
        print(f"  Total Queries Evaluated:    {total_queries}")
        print(f"  True Positives:             {true_positives}")
        print(f"  False Positives:            {false_positives}")
        print(f"  False Negatives:            {false_negatives}")
        print(f"  True Negatives:             {true_negatives}")
        print(f"  Precision:                  {precision * 100:.2f}%")
        print(f"  Recall:                     {recall * 100:.2f}%")
        print(f"  False Pos Rate:             {fp_rate * 100:.2f}%")
        print(f"  Avg Selected per Query:     {avg_selected:.2f}")
        print(f"  Avg Executed per Query:     {avg_executed:.2f}")
        print(f"  Ambiguous Query Count:      {ambiguity_count}")
        print(f"  Multi-Tool Success Rate:    {multi_tool_rate:.2f}%")
        print("="*85)

        await registry.shutdown()

if __name__ == "__main__":
    asyncio.run(run_precision_audit())

if __name__ == "__main__":
    asyncio.run(run_precision_audit())
