"""
agent/graph.py — Full LangGraph state machine (Phase 3 update).

Updated flow with Phase 3 Tool Planner, Parallel Execution, and Evidence Checker:

  START
    │
    ▼
  classify_intent_node
    │
    ├─ is_ambiguous=True ─────────────▶ clarification_node ──────────▶ END
    ├─ intent=MEMORY_WRITE ───────────▶ memory_write_node ───────────▶ END
    └─ all other intents ─────────────▶ plan_node
                                           │
                                           ▼
                                     tool_planner_node  ← NEW (Phase 3)
                                           │
                                           ▼
                                   parallel_tool_execution_node  ← NEW (Phase 3)
                                           │
                                           ▼
                                     check_retrieval_node
                                           │
                               ┌───────────┴──────────────┐
                         needs_retrieval=True         needs_retrieval=False
                               │                           │
                         retrieve_context_node             │
                               │                           │
                         grade_documents_node  ◄───────────┘
                               │
                               ├─ confidence<0.5 & retries left ──▶ retrieve_context (Self-RAG retry)
                               │
                         generate_response_node
                               │
                   ┌───────────┴────────────┐
             has tool_calls?          no tool_calls
                   │                        │
           execute_tools_node        evidence_checker_node  ← NEW (Phase 3)
                   │                        │
                   └──────────┬─────────────┘
                              ▼
                         reflect_node
                              │
                   ┌──────────┴──────────┐
             NEEDS_IMPROVEMENT         PASS
                   │                    │
           generate_response_node      END

MAX_ITERATIONS = 1 caps the reflection loop.
"""

from langgraph.graph import StateGraph, END
from app.agent.state import AgentState
from app.agent.nodes import (
    classify_intent_node,
    memory_write_node,
    plan_node,
    check_retrieval_node,
    retrieve_context_node,
    grade_documents_node,
    generate_response_node,
    execute_tools_node,
    reflect_node,
    clarification_node,
    # Phase 3
    tool_planner_node,
    parallel_tool_execution_node,
    evidence_checker_node,
    query_rewriter_node,
)
from app.agent.prompts import (
    INTENT_MEMORY_WRITE,
    INTENT_NORMAL_CHAT,
    INTENT_DOCUMENT_QA,
)

MAX_ITERATIONS = 1  # maximum reflection-driven regeneration passes


# ─────────────────────────────────────────────────────────────────────────────
#  Conditional edge functions
# ─────────────────────────────────────────────────────────────────────────────

def route_after_classify(state: AgentState) -> str:
    """
    After intent classification:
      is_ambiguous=True → clarification
      MEMORY_WRITE → memory_write (short-circuits the full pipeline)
      NORMAL_CHAT | DOCUMENT_QA → check_retrieval (bypasses tool planning for fast single-turn path)
      Everything else (COMPLEX, MCP_TOOL, CODE_EXECUTION, etc.) → plan
    """
    if state.get("is_ambiguous", False):
        return "clarification"
    intent = state.get("intent", INTENT_NORMAL_CHAT)
    if intent == INTENT_MEMORY_WRITE:
        return "memory_write"
    if intent in (INTENT_NORMAL_CHAT, INTENT_DOCUMENT_QA):
        return "check_retrieval"
    return "plan"


def route_retrieval(state: AgentState) -> str:
    """Self-RAG router: skip or execute retrieval."""
    if state.get("needs_retrieval", True):
        return "retrieve_context"
    return "grade_documents"


def route_after_grading(state: AgentState) -> str:
    """
    After grading: if retrieval confidence is low and we have remaining retries,
    loop back to retrieve_context. Otherwise, proceed to generate_response.
    """
    confidence   = state.get("retrieval_confidence", 1.0)
    retry_count  = state.get("retrieval_retry_count", 0)
    max_retries  = state.get("max_retrieval_retries", 2)
    needs_retrieval = state.get("needs_retrieval", True)

    if needs_retrieval and confidence < 0.5 and retry_count <= max_retries:
        return "retrieve_context"
    return "generate_response"


def route_after_generation(state: AgentState) -> str:
    """After generate_response: run tools, check evidence, or reflect."""
    tool_calls = state.get("tool_calls", [])
    if tool_calls:
        return "execute_tools"
    return "evidence_checker"


def route_after_evidence_checker(state: AgentState) -> str:
    """After evidence checking always go to reflect."""
    return "reflect"


def route_after_reflection(state: AgentState) -> str:
    """After reflection: regenerate if quality is insufficient, else finish."""
    passed    = state.get("reflection_passed", True)
    iteration = state.get("iteration_count", 0)
    if not passed and iteration <= MAX_ITERATIONS:
        return "generate_response"
    return END


# ─────────────────────────────────────────────────────────────────────────────
#  Build the graph
# ─────────────────────────────────────────────────────────────────────────────

workflow = StateGraph(AgentState)

# Register all nodes
workflow.add_node("classify_intent",           classify_intent_node)
workflow.add_node("memory_write",              memory_write_node)
workflow.add_node("clarification",             clarification_node)
workflow.add_node("plan",                      plan_node)
workflow.add_node("tool_planner",              tool_planner_node)           # Phase 3
workflow.add_node("parallel_tool_execution",   parallel_tool_execution_node)  # Phase 3
workflow.add_node("query_rewriter",            query_rewriter_node)
workflow.add_node("check_retrieval",           check_retrieval_node)
workflow.add_node("retrieve_context",          retrieve_context_node)
workflow.add_node("grade_documents",           grade_documents_node)
workflow.add_node("generate_response",         generate_response_node)
workflow.add_node("execute_tools",             execute_tools_node)
workflow.add_node("evidence_checker",          evidence_checker_node)       # Phase 3
workflow.add_node("reflect",                   reflect_node)

# Entry point → intent classifier
workflow.set_entry_point("classify_intent")

# classify_intent → memory_write | clarification | check_retrieval | plan
workflow.add_conditional_edges(
    "classify_intent",
    route_after_classify,
    {
        "memory_write":    "memory_write",
        "clarification":   "clarification",
        "check_retrieval": "check_retrieval",
        "plan":            "plan",
    },
)

# Terminals for short-circuits
workflow.add_edge("memory_write",  END)
workflow.add_edge("clarification", END)

# plan → tool_planner (Phase 3)
workflow.add_edge("plan", "tool_planner")

# tool_planner → parallel_tool_execution (Phase 3)
workflow.add_edge("tool_planner", "parallel_tool_execution")

# parallel_tool_execution → query_rewriter
workflow.add_edge("parallel_tool_execution", "query_rewriter")

# query_rewriter → check_retrieval
workflow.add_edge("query_rewriter", "check_retrieval")

# check_retrieval → retrieve_context OR grade_documents (Self-RAG)
workflow.add_conditional_edges(
    "check_retrieval",
    route_retrieval,
    {
        "retrieve_context": "retrieve_context",
        "grade_documents":  "grade_documents",
    },
)

# retrieve_context → grade_documents (CRAG)
workflow.add_edge("retrieve_context", "grade_documents")

# grade_documents → retrieve_context (retry) OR generate_response
workflow.add_conditional_edges(
    "grade_documents",
    route_after_grading,
    {
        "retrieve_context": "retrieve_context",
        "generate_response": "generate_response",
    },
)

# generate_response → execute_tools OR evidence_checker (Phase 3)
workflow.add_conditional_edges(
    "generate_response",
    route_after_generation,
    {
        "execute_tools":    "execute_tools",
        "evidence_checker": "evidence_checker",
    },
)

# execute_tools → generate_response (tool-call loop)
workflow.add_edge("execute_tools", "generate_response")

# evidence_checker → reflect (always)
workflow.add_conditional_edges(
    "evidence_checker",
    route_after_evidence_checker,
    {
        "reflect": "reflect",
    },
)

# reflect → generate_response (re-draft) OR END
workflow.add_conditional_edges(
    "reflect",
    route_after_reflection,
    {
        "generate_response": "generate_response",
        END:                 END,
    },
)

# Compile
agent_graph = workflow.compile()
