"""
Audit Test Suite: Execution Trace & Dev HUD Observability Verification
Run this script with pytest or python directly to verify 100% working pipeline observability.
"""

import sys
import os
import asyncio
import time
import unittest

# Add backend directory to sys.path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.agent.state import AgentState
from app.agent.nodes import (
    init_execution_trace,
    record_node_execution,
    validate_execution_trace,
    classify_intent_node,
    memory_write_node,
    check_retrieval_node,
    execute_web_search_node,
    retrieve_context_node,
)
from app.agent.graph import agent_graph


def create_test_state() -> AgentState:
    state: AgentState = {
        "messages": [],
        "active_model": "gemini-2.0-flash",
        "user_id": "test_user_123",
        "chat_id": "test_chat",
        "retrieved_documents": [],
        "metrics": {},
        "response_text": "",
        "tool_calls": [],
        "steps": [],
        "intent": "NORMAL_CHAT",
        "allowed_tools": [],
        "is_private_doc_query": False,
        "no_doc_answer": False,
        "memory_write_content": None,
        "memory_write_category": None,
        "uploaded_file_paths": [],
        "plan": None,
        "current_plan_step": 0,
        "needs_retrieval": False,
        "document_relevance": "ungraded",
        "retrieval_confidence": 1.0,
        "retrieval_retry_count": 0,
        "max_retrieval_retries": 2,
        "is_ambiguous": False,
        "clarification_question": None,
        "original_query": None,
        "resolved_query": None,
        "sub_questions": [],
        "tool_dag": None,
        "tool_execution_results": None,
        "ux_stage": "idle",
        "reflection_passed": True,
        "reflection_feedback": None,
        "iteration_count": 0,
        "detected_language": None,
        "language_mode": None,
        "generation_mode": None,
        "source_documents": [],
        "images": [],
        "execution_trace": [],
        "semantic_status": {
            "retrieval_status": "RETRIEVAL NOT NEEDED",
            "embedding_executed": False,
            "vector_search_executed": False,
            "rag_chunks": 0,
            "graded_chunks": 0,
        },
        "memory_status": {
            "lookup_status": "MEMORY NOT CHECKED",
            "memory_hits": 0,
            "injected_into_prompt": False,
            "write_executed": False,
            "persisted_content": None,
        },
        "web_status": {
            "executed": False,
            "reason": None,
            "results_count": 0,
            "accepted_sources_count": 0,
            "used_in_final_answer": False,
            "queries": [],
            "sources": [],
        },
        "inconsistencies": [],
    }
    init_execution_trace(state)
    return state


class TestExecutionTraceAudit(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.state = create_test_state()

    def test_trace_initialization_and_reset(self):
        """Test Case 1: Trace resets cleanly at start of request."""
        state = create_test_state()
        state["execution_trace"] = [{"name": "old_node", "status": "EXECUTED"}]
        init_execution_trace(state)
        self.assertEqual(len(state["execution_trace"]), 0)
        self.assertEqual(state["semantic_status"]["retrieval_status"], "RETRIEVAL NOT NEEDED")
        self.assertEqual(state["memory_status"]["lookup_status"], "MEMORY NOT CHECKED")
        self.assertFalse(state["web_status"]["executed"])

    async def test_simple_conversational_query(self):
        """Test Case 2: Simple conversational query bypasses RAG and tools."""
        state = create_test_state()
        state["messages"] = [{"type": "user", "content": "Hi, how are you?"}]
        
        res = await classify_intent_node(state, {})
        state.update(res)

        self.assertEqual(state["intent"], "NORMAL_CHAT")
        
        check_res = await check_retrieval_node(state, {})
        state.update(check_res)

        self.assertFalse(state["needs_retrieval"])

        trace_nodes = {t["name"]: t["status"] for t in state["execution_trace"]}
        self.assertEqual(trace_nodes.get("classify_intent"), "EXECUTED")
        self.assertEqual(trace_nodes.get("check_retrieval"), "EXECUTED")
        self.assertEqual(trace_nodes.get("retrieve_context"), "BYPASSED")
        self.assertEqual(state["semantic_status"]["retrieval_status"], "RETRIEVAL NOT NEEDED")

    async def test_temporal_current_info_query(self):
        """Test Case 3: Current-information query triggers freshness & web search."""
        state = create_test_state()
        state["messages"] = [{"type": "user", "content": "Who is the current education minister of India?"}]
        
        res = await classify_intent_node(state, {})
        state.update(res)

        self.assertEqual(state["intent"], "CURRENT_EVENTS")
        self.assertTrue(state["execution_trace"][0]["metadata"].get("freshness_required"))

    async def test_memory_write_query(self):
        """Test Case 4: Memory write query persists fact and bypasses downstream nodes."""
        state = create_test_state()
        state["messages"] = [{"type": "user", "content": "Remember that my favorite chess player is Magnus Carlsen."}]
        state["user_id"] = "test_user_123"

        res = await classify_intent_node(state, {})
        state.update(res)

        self.assertEqual(state["intent"], "MEMORY_WRITE")
        self.assertIn("Magnus Carlsen", state["memory_write_content"])

        cfg = {"configurable": {"user_id": "test_user_123"}}
        mem_res = await memory_write_node(state, cfg)
        state.update(mem_res)

        self.assertTrue(state["memory_status"]["write_executed"])
        self.assertIn("Magnus Carlsen", state["memory_status"]["persisted_content"])

        trace_nodes = {t["name"]: t["status"] for t in state["execution_trace"]}
        self.assertEqual(trace_nodes.get("memory_write"), "EXECUTED")
        self.assertEqual(trace_nodes.get("check_retrieval"), "BYPASSED")
        self.assertEqual(trace_nodes.get("retrieve_context"), "BYPASSED")
        self.assertEqual(trace_nodes.get("grade_documents"), "BYPASSED")
        self.assertEqual(trace_nodes.get("generate_response"), "BYPASSED")

    async def test_memory_read_status(self):
        """Test Case 5: Memory health correctly reports hits when memories present in config."""
        state = create_test_state()
        state["messages"] = [{"type": "user", "content": "What is my favorite chess player?"}]
        config = {"configurable": {"memories": [{"content": "favorite chess player is Magnus Carlsen"}]}}

        res = await classify_intent_node(state, config)
        state.update(res)

        self.assertEqual(state["memory_status"]["lookup_status"], "MEMORY CHECKED → 1 HITS")
        self.assertTrue(state["memory_status"]["injected_into_prompt"])

    async def test_private_doc_query_no_docs(self):
        """Test Case 6: Private document query with 0 chunks reports 0 RESULTS and blocks web fallback."""
        state = create_test_state()
        state["messages"] = [{"type": "user", "content": "What is mentioned in my project documentation file project_documentation_part1.md?"}]
        state["user_id"] = "test_user_123"

        res = await classify_intent_node(state, {})
        state.update(res)

        check_res = await check_retrieval_node(state, {})
        state.update(check_res)

        self.assertTrue(state["needs_retrieval"])

        ret_res = await retrieve_context_node(state, {})
        state.update(ret_res)

        self.assertEqual(state["semantic_status"]["retrieval_status"], "RETRIEVAL NEEDED BUT 0 RESULTS")

    def test_system_inconsistency_detection(self):
        """Test Case 7: Invalid trace combinations trigger SYSTEM INCONSISTENCY."""
        state = create_test_state()
        state["execution_trace"] = [
            {"name": "classify_intent", "status": "EXECUTED"},
            {"name": "check_retrieval", "status": "BYPASSED"},
            {"name": "retrieve_context", "status": "EXECUTED"},
        ]
        
        inconsistencies = validate_execution_trace(state)
        self.assertTrue(len(inconsistencies) > 0)
        self.assertIn("INCONSISTENCY: Node 'retrieve_context' EXECUTED but prerequisite 'check_retrieval' was BYPASSED", inconsistencies[0])

    async def test_compound_query_decomposition(self):
        """Test Case 8: Compound entity query generates sub-questions."""
        state = create_test_state()
        state["messages"] = [{"type": "user", "content": "Who is the current education minister of India and Bihar?"}]

        res = await classify_intent_node(state, {})
        state.update(res)

        self.assertGreaterEqual(len(state["sub_questions"]), 2)
        self.assertIn("India", state["sub_questions"][0])
        self.assertIn("Bihar", state["sub_questions"][1])

    def test_full_graph_compilation(self):
        """Test Case 9: LangGraph compiles cleanly with trace architecture."""
        self.assertIsNotNone(agent_graph)

    async def test_trace_reset_on_next_turn(self):
        """Test Case 10: Multi-turn trace reset avoids carrying over prior states."""
        state = create_test_state()
        record_node_execution(state, "old_node_turn_1", "EXECUTED", "Turn 1 action")
        
        # New turn starts
        init_execution_trace(state)
        self.assertEqual(len(state["execution_trace"]), 0)


if __name__ == "__main__":
    unittest.main()
