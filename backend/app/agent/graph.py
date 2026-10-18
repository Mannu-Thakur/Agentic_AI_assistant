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
    execute_web_search_node,
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
    INTENT_VISION,
    INTENT_WEB_SEARCH,
    INTENT_CODE_EXECUTION,
    INTENT_MCP_TOOL,
    INTENT_COMPLEX,
    INTENT_PROGRAMMING,
    INTENT_MATH,
    INTENT_FINANCE,
    INTENT_NEWS,
    INTENT_CURRENT_EVENTS,
    INTENT_PDF_QA,
    INTENT_DATABASE,
    INTENT_SUMMARIZATION,
    INTENT_TRANSLATION,
    INTENT_REASONING,
    INTENT_LONG_CONTEXT,
    INTENT_MULTI_STEP,
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
      WEB_SEARCH | NEWS | CURRENT_EVENTS (not private doc) → execute_web_search (direct web search tool execution)
      NORMAL_CHAT | DOCUMENT_QA | VISION → check_retrieval (bypasses tool planning for fast single-turn path)
      Everything else (COMPLEX, MCP_TOOL, CODE_EXECUTION, etc.) → planner
    """
    # classify_intent_node records the selected stage in state and emits the
    # same safe routing summary to the client.  Prefer it so the UI and graph
    # cannot diverge; retain the explicit logic below as a backward-compatible
    # fallback for callers that construct state by hand.
    announced_stage = state.get("routing_next_step")
    if announced_stage in {"clarification", "memory_write", "execute_web_search", "check_retrieval", "planner"}:
        return announced_stage

    if state.get("is_ambiguous", False):
        return "clarification"
    intent = state.get("intent", INTENT_NORMAL_CHAT)
    is_private = state.get("is_private_doc_query", False)
    images = state.get("images") or []
    if intent == INTENT_MEMORY_WRITE:
        return "memory_write"
    # If images are present and intent is WEB_SEARCH, do not execute text-only search directly
    # because the entity name/context is inside the image. Routing through check_retrieval ->
    # generate_response allows the vision LLM to inspect the image and call tavily_search dynamically.
    if intent in (INTENT_WEB_SEARCH, INTENT_NEWS, INTENT_CURRENT_EVENTS) and not is_private and not images:
        return "execute_web_search"
    if intent in (
        INTENT_NORMAL_CHAT,
        INTENT_DOCUMENT_QA,
        INTENT_VISION,
        INTENT_PDF_QA,
        INTENT_SUMMARIZATION,
        INTENT_TRANSLATION,
        INTENT_DATABASE,
        INTENT_LONG_CONTEXT,
    ) or (images and intent in (INTENT_WEB_SEARCH, INTENT_NEWS, INTENT_CURRENT_EVENTS)):
        return "check_retrieval"
    return "planner"


def route_retrieval(state: AgentState) -> str:
    """Self-RAG router: skip or execute retrieval."""
    if state.get("needs_retrieval", False):
        return "retrieve_context"
    return "generate_response"


def route_after_grading(state: AgentState) -> str:
    """
    After grading: if retrieval confidence is low and we have remaining retries,
    loop back to retrieve_context. Otherwise, proceed to generate_response.
    """
    confidence   = state.get("retrieval_confidence", 1.0)
    retry_count  = state.get("retrieval_retry_count", 0)
    max_retries  = state.get("max_retrieval_retries", 2)
    needs_retrieval = state.get("needs_retrieval", True)

    if needs_retrieval and confidence < 0.5 and retry_count < max_retries:
        return "retrieve_context"
    return "generate_response"


def route_after_generation(state: AgentState) -> str:
    """After generate_response: run tools, check evidence, or reflect."""
    tool_calls = state.get("tool_calls", [])
    steps = state.get("steps", [])
    MAX_TOOL_CYCLES = 4
    iteration = state.get('iteration_count', 0)
    if tool_calls and 'execute_web_search' not in steps and iteration < MAX_TOOL_CYCLES:
        return 'execute_tools'
    return 'evidence_checker'


def route_after_evidence_checker(state: AgentState) -> str:
    """After evidence checking always go to reflect."""
    return "reflect"


def route_after_reflection(state: AgentState) -> str:
    """After reflection: regenerate if quality is insufficient, else finish."""
    intent = state.get("intent", INTENT_NORMAL_CHAT)
    if intent in (INTENT_VISION, INTENT_MEMORY_WRITE, INTENT_NORMAL_CHAT, INTENT_DOCUMENT_QA):
        return END
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
workflow.add_node("planner",                    plan_node)
workflow.add_node("tool_planner",              tool_planner_node)           # Phase 3
workflow.add_node("parallel_tool_execution",   parallel_tool_execution_node)  # Phase 3
workflow.add_node("query_rewriter",            query_rewriter_node)
workflow.add_node("check_retrieval",           check_retrieval_node)
workflow.add_node("retrieve_context",          retrieve_context_node)
workflow.add_node("grade_documents",           grade_documents_node)
workflow.add_node("execute_web_search",        execute_web_search_node)
workflow.add_node("generate_response",         generate_response_node)
workflow.add_node("execute_tools",             execute_tools_node)
workflow.add_node("evidence_checker",          evidence_checker_node)       # Phase 3
workflow.add_node("reflect",                   reflect_node)

# Entry point → intent classifier
workflow.set_entry_point("classify_intent")

# Rewrite contextual follow-ups before selecting the fast path or planner path.
# Previously direct chat/document turns bypassed query_rewriter entirely.
workflow.add_edge("classify_intent", "query_rewriter")

workflow.add_conditional_edges(
    "query_rewriter",
    route_after_classify,
    {
        "memory_write":       "memory_write",
        "clarification":      "clarification",
        "execute_web_search": "execute_web_search",
        "check_retrieval":    "check_retrieval",
        "planner":            "planner",
    },
)

# Direct web search execution → generate_response
workflow.add_edge("execute_web_search", "generate_response")

# Terminals for short-circuits
workflow.add_edge("memory_write",  END)
workflow.add_edge("clarification", END)

# planner → tool_planner (Phase 3)
workflow.add_edge("planner", "tool_planner")

# tool_planner → parallel_tool_execution (Phase 3)
workflow.add_edge("tool_planner", "parallel_tool_execution")

# parallel_tool_execution → check_retrieval
workflow.add_edge("parallel_tool_execution", "check_retrieval")

# check_retrieval → retrieve_context OR generate_response (Self-RAG)
workflow.add_conditional_edges(
    "check_retrieval",
    route_retrieval,
    {
        "retrieve_context":  "retrieve_context",
        "generate_response": "generate_response",
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

# ── Persistent SQLite Checkpointer ───────────────────────────────────────────
# Conversations are now persisted across server restarts.
# Thread ID = "{user_id}:{chat_id}" for per-conversation isolation.
# Falls back to in-memory (no checkpointing) if SQLite is unavailable.
import os
from pathlib import Path

_AGENT_CHECKPOINT_DB = os.getenv(
    "AGENT_CHECKPOINT_DB",
    str(Path("data") / "agent_checkpoints.db")
)

def _build_agent_graph():
    """
    Compile the agent workflow with the best available checkpointer.
    langgraph-checkpoint-sqlite v3.x requires AsyncSqliteSaver inside
    a running event loop, so we use MemorySaver here for module-level init.
    """
    import logging
    _log = logging.getLogger("agent.graph")
    try:
        from langgraph.checkpoint.memory import MemorySaver
        Path(_AGENT_CHECKPOINT_DB).parent.mkdir(parents=True, exist_ok=True)
        memory   = MemorySaver()
        compiled = workflow.compile(checkpointer=memory)
        _log.info("[AgentGraph] Compiled with MemorySaver (per-process persistence).")

        _orig_ainvoke = compiled.ainvoke
        _orig_invoke = compiled.invoke

        async def _safe_ainvoke(input, config=None, **kwargs):
            if config is None:
                config = {}
            else:
                config = dict(config)
            cfg = dict(config.get("configurable") or {})
            if "thread_id" not in cfg:
                cfg["thread_id"] = str(cfg.get("chat_id") or "default_thread")
            config["configurable"] = cfg
            return await _orig_ainvoke(input, config, **kwargs)

        def _safe_invoke(input, config=None, **kwargs):
            if config is None:
                config = {}
            else:
                config = dict(config)
            cfg = dict(config.get("configurable") or {})
            if "thread_id" not in cfg:
                cfg["thread_id"] = str(cfg.get("chat_id") or "default_thread")
            config["configurable"] = cfg
            return _orig_invoke(input, config, **kwargs)

        compiled.ainvoke = _safe_ainvoke
        compiled.invoke = _safe_invoke
        return compiled
    except Exception as exc:
        _log.warning(f"[AgentGraph] MemorySaver unavailable ({exc}), compiling stateless.")
        return workflow.compile()

agent_graph = _build_agent_graph()

