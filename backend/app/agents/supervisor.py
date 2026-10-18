"""
app/agents/supervisor.py — Supervisor + Planner LangGraph Orchestrator

This is the top-level multi-agent orchestrator. It wraps the existing
single-agent graph with a Supervisor layer that can:

  1. Understand complex intent (Mission Mode)
  2. Decompose into a subtask DAG with agent assignments
  3. Dispatch tasks to specialized sub-agents (fan-out)
  4. Collect and merge results (fan-in)
  5. Run the Critic agent for quality verification
  6. Gate risky actions through HITL (human-in-the-loop)
  7. Synthesize the final response
  8. Persist state via SQLite checkpointer

For simple intents, the Supervisor passes through to the existing
`agent_graph` unchanged (backward-compatible).

Architecture
------------
  START
    │
    ▼
  supervisor_classify             ← Intent + complexity check
    │
    ├─ SIMPLE ──────────────────▶ delegate_to_agent_graph ──▶ END
    │                              (existing Phase 3 graph)
    │
    └─ COMPLEX / MISSION ───────▶ mission_planner
                                       │
                                       ▼
                                  parallel_dispatch   ← asyncio fan-out
                                       │
                                  result_collector
                                       │
                                  critic_verification  ← CriticAgent
                                       │
                                  hitl_gate ?          ← interrupt_before
                                       │
                                  synthesizer
                                       │
                                      END

Checkpointing
-------------
  Uses SqliteSaver so conversation state persists across server restarts.
  Thread ID = user_id:chat_id for per-conversation isolation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Annotated
from typing_extensions import TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END

from langgraph.checkpoint.sqlite import SqliteSaver

from app.agents.registry import agent_registry, AgentTask, AgentResult
from app.agents.artifacts import artifact_store

logger = logging.getLogger("agents.supervisor")

# ── Import all agents so they self-register ───────────────────────────────────
try:
    import app.agents.code_agent          # noqa: F401
    import app.agents.web_research_agent  # noqa: F401
    import app.agents.critic_agent        # noqa: F401
    import app.agents.document_agent      # noqa: F401
    import app.agents.data_analysis_agent # noqa: F401
    import app.agents.rag_agent           # noqa: F401
    import app.agents.vision_agent        # noqa: F401
except ImportError as e:
    logger.warning(f"[Supervisor] Agent import warning: {e}")


# ─────────────────────────────────────────────────────────────────────────────
#  Supervisor State
# ─────────────────────────────────────────────────────────────────────────────

class MissionState(TypedDict, total=False):
    """Extended state for the Supervisor / Mission graph."""

    # ── Core inputs ───────────────────────────────────────────────────────────
    query: str
    user_id: str
    session_id: str          # = chat_id for conversation persistence
    active_model: str
    api_keys: Dict[str, Any]
    messages: List[Dict]

    # ── Routing ───────────────────────────────────────────────────────────────
    is_mission: bool          # True → use multi-agent path
    mission_id: str
    mission_goal: str

    # ── Planning ──────────────────────────────────────────────────────────────
    agent_tasks: List[Dict]   # serialized AgentTask list
    selected_agents: List[str]
    plan_reasoning: str

    # ── Execution results ─────────────────────────────────────────────────────
    agent_results: Dict[str, Dict]   # agent_name → AgentResult.to_dict()
    merged_content: str

    # ── Critic ────────────────────────────────────────────────────────────────
    critic_score: float
    critic_passes: bool
    critic_feedback: str

    # ── HITL ──────────────────────────────────────────────────────────────────
    requires_approval: bool
    approval_reason: str
    approval_status: str      # "pending" | "approved" | "rejected"

    # ── Artifacts ─────────────────────────────────────────────────────────────
    artifacts: List[Dict]

    # ── Retry / quality loop ───────────────────────────────────────────────────
    retry_count: int             # how many critic-retry cycles have run
    critic_retry_hint: str       # feedback injected back into planner on retry

    # ── Final output ──────────────────────────────────────────────────────────
    final_response: str
    sources: List[Dict]

    # ── Trace ─────────────────────────────────────────────────────────────────
    supervisor_trace: List[Dict]   # [{node, status, duration_ms, ...}]


# ─────────────────────────────────────────────────────────────────────────────
#  Planner prompt
# ─────────────────────────────────────────────────────────────────────────────

PLANNER_SYSTEM = """You are an expert multi-agent orchestration planner for a production AI workspace.

Your job: Analyze the user's request and decide the optimal execution strategy.

## Decision Rules

**Use SIMPLE (is_mission=false) when:**
- Conversational: greetings, clarifications, opinions, follow-ups
- Factual one-liners answerable from LLM knowledge (< 2 sentences)
- Single-step tasks: translate X, summarize this text, fix this bug

**Use MISSION (is_mission=true) when:**
- Requires external data: "research", "find current", "latest news about"
- Multi-step: "research AND write", "analyze AND generate report"
- Document/artifact creation: "create a presentation", "write a full report"
- Code + explanation together: "build X and explain how it works"
- Data analysis: "analyze this dataset and find insights"
- Multiple domains: needs web search + code + document generation together

## Available Agents
{agents_desc}

## Agent Selection Rules
- web_research: ALWAYS use for anything needing current/external information
- rag: use when user asks about uploaded documents / their knowledge base
- code: use for any coding, scripting, implementation requests
- data_analysis: use for CSV/data files, statistics, charts, pattern finding
- document: use when output should be a formatted PPTX, DOCX, or PDF
- vision: ONLY use when an image is explicitly provided
- critic: DO NOT include in tasks — it runs automatically after all others

## Output Format
Respond ONLY with valid JSON (no markdown fences):
{{
  "is_mission": true,
  "reason": "Needs web research for current data + code implementation",
  "selected_agents": ["web_research", "code"],
  "tasks": [
    {{
      "agent": "web_research",
      "query": "Specific focused sub-query for this agent — NOT the full user query",
      "priority": 1
    }},
    {{
      "agent": "code",
      "query": "Specific coding task description — what exactly to implement",
      "priority": 2
    }}
  ]
}}

{retry_hint}"""


# ─────────────────────────────────────────────────────────────────────────────
#  Node: Supervisor Classify
# ─────────────────────────────────────────────────────────────────────────────

async def supervisor_classify_node(state: MissionState, config: RunnableConfig) -> Dict:
    """Classify whether the query needs Mission Mode or simple pass-through."""
    t0 = time.perf_counter()
    query       = state.get("query", "")
    from app.core.config import settings
    model       = state.get("active_model", settings.GEMINI_MODEL)
    api_keys    = state.get("api_keys", {})
    retry_hint  = state.get("critic_retry_hint", "")

    trace = list(state.get("supervisor_trace") or [])

    agents_desc = json.dumps(agent_registry.describe_all(), indent=2)

    # On retry, inject critic feedback into planner so it re-plans better
    retry_section = ""
    if retry_hint:
        retry_section = (
            f"\n\n## RETRY INSTRUCTION\nThe previous agent run was rejected by the Critic "
            f"for the following reason:\n{retry_hint}\n"
            f"Please select different or additional agents to address this gap."
        )

    planner_prompt = PLANNER_SYSTEM.format(
        agents_desc=agents_desc,
        retry_hint=retry_section,
    )

    plan: Dict[str, Any] = {}
    try:
        from app.agents.node_helpers import call_llm_json
        plan = await call_llm_json(
            prompt=f"User query:\n{query}",
            model=model,
            api_keys=api_keys,
            system=planner_prompt,
            temperature=0.0,
        )
    except Exception as exc:
        logger.warning(f"[Supervisor] Classify failed: {exc} — defaulting to simple")
        plan = {"is_mission": False, "reason": str(exc), "selected_agents": [], "tasks": []}

    is_mission     = bool(plan.get("is_mission", False))
    selected       = plan.get("selected_agents", [])
    tasks_raw      = plan.get("tasks", [])
    plan_reasoning = plan.get("reason", "")

    # Build AgentTask list
    agent_tasks = []
    for raw in tasks_raw:
        agent_name = raw.get("agent", "")
        if agent_name and agent_name in agent_registry.list_agents():
            task = AgentTask(
                id=str(uuid.uuid4())[:8],
                agent_name=agent_name,
                input={
                    "query":       raw.get("query", query),
                    "user_id":     state.get("user_id", "anon"),
                    "session_id":  state.get("session_id", "default"),
                    "active_model": model,
                    "api_keys":    api_keys,
                    "messages":    state.get("messages", []),
                },
                metadata={"priority": raw.get("priority", 1)},
            )
            agent_tasks.append(task.to_dict())

    duration_ms = round((time.perf_counter() - t0) * 1000, 2)
    trace.append({
        "node": "supervisor_classify",
        "status": "DONE",
        "is_mission": is_mission,
        "agents_selected": selected,
        "duration_ms": duration_ms,
    })

    logger.info(
        f"[Supervisor] is_mission={is_mission} agents={selected} "
        f"tasks={len(agent_tasks)} reason={plan_reasoning!r:.80}"
    )

    return {
        "is_mission":       is_mission,
        "mission_id":       str(uuid.uuid4()) if is_mission else "",
        "mission_goal":     query if is_mission else "",
        "selected_agents":  selected,
        "agent_tasks":      agent_tasks,
        "plan_reasoning":   plan_reasoning,
        "supervisor_trace": trace,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Node: Parallel Dispatch
# ─────────────────────────────────────────────────────────────────────────────

async def parallel_dispatch_node(state: MissionState, config: RunnableConfig) -> Dict:
    """Fan-out: run all agent tasks concurrently."""
    t0 = time.perf_counter()
    agent_tasks = state.get("agent_tasks", [])
    trace = list(state.get("supervisor_trace") or [])

    if not agent_tasks:
        trace.append({"node": "parallel_dispatch", "status": "SKIPPED", "reason": "No tasks"})
        return {"supervisor_trace": trace, "agent_results": {}}

    async def run_one_task(task_dict: Dict) -> tuple[str, Dict]:
        task = AgentTask(**{
            k: v for k, v in task_dict.items()
            if k in AgentTask.__dataclass_fields__
        })
        agent_name = task.agent_name
        try:
            agent = agent_registry.get(agent_name)
            task.mark_started()
            result: AgentResult = await agent.run(task.input)
            task.mark_done(result.to_dict())
            logger.info(f"[Supervisor] ✓ Agent '{agent_name}' done in {task.duration_ms:.0f}ms")
            return agent_name, result.to_dict()
        except Exception as exc:
            task.mark_failed(str(exc))
            logger.error(f"[Supervisor] ✗ Agent '{agent_name}' failed: {exc}")
            return agent_name, AgentResult(
                agent_name=agent_name, success=False, error=str(exc)
            ).to_dict()

    # Execute all tasks concurrently
    coros = [run_one_task(t) for t in agent_tasks]
    pairs = await asyncio.gather(*coros, return_exceptions=False)
    agent_results = dict(pairs)

    # Collect all artifacts from results
    all_artifacts: List[Dict] = []
    for result_dict in agent_results.values():
        all_artifacts.extend(result_dict.get("artifacts", []))

    duration_ms = round((time.perf_counter() - t0) * 1000, 2)
    trace.append({
        "node":          "parallel_dispatch",
        "status":        "DONE",
        "agents_run":    list(agent_results.keys()),
        "duration_ms":   duration_ms,
    })

    return {
        "agent_results":    agent_results,
        "artifacts":        all_artifacts,
        "supervisor_trace": trace,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Node: Result Collector + Merger
# ─────────────────────────────────────────────────────────────────────────────

async def result_collector_node(state: MissionState, config: RunnableConfig) -> Dict:
    """Merge outputs from all agents into a unified context block."""
    t0 = time.perf_counter()
    agent_results = state.get("agent_results", {})
    trace = list(state.get("supervisor_trace") or [])

    all_content_parts: List[str] = []
    all_sources: List[Dict] = []
    requires_approval = False
    approval_reason   = ""

    for agent_name, result in agent_results.items():
        content = result.get("content", "")
        if content:
            all_content_parts.append(f"### {agent_name.replace('_', ' ').title()} Agent\n\n{content}")

        # Collect sources
        all_sources.extend(result.get("sources", []))

        # Check HITL requirements
        meta = result.get("metadata", {})
        if meta.get("requires_approval"):
            requires_approval = True
            approval_reason   = meta.get("approval_reason", "Approval needed")

    merged_content = "\n\n---\n\n".join(all_content_parts)

    duration_ms = round((time.perf_counter() - t0) * 1000, 2)
    trace.append({
        "node":             "result_collector",
        "status":           "DONE",
        "content_agents":   len(all_content_parts),
        "sources_collected": len(all_sources),
        "requires_approval": requires_approval,
        "duration_ms":      duration_ms,
    })

    return {
        "merged_content":   merged_content,
        "sources":          all_sources,
        "requires_approval": requires_approval,
        "approval_reason":  approval_reason,
        "supervisor_trace": trace,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Node: Critic Verification
# ─────────────────────────────────────────────────────────────────────────────

async def critic_verification_node(state: MissionState, config: RunnableConfig) -> Dict:
    """Run CriticAgent on the merged output."""
    t0 = time.perf_counter()
    merged  = state.get("merged_content", "")
    sources = state.get("sources", [])
    query   = state.get("query", "")
    from app.core.config import settings
    model   = state.get("active_model", settings.GEMINI_MODEL)
    api_keys = state.get("api_keys", {})
    trace   = list(state.get("supervisor_trace") or [])

    critic_score   = 0.8
    critic_passes  = True
    critic_feedback = ""

    try:
        critic_agent = agent_registry.get("critic")
        result = await critic_agent.run({
            "response":    merged,
            "sources":     sources,
            "query":       query,
            "active_model": model,
            "api_keys":    api_keys,
        })
        critic_score   = result.metadata.get("quality_score", 0.8)
        critic_passes  = result.metadata.get("passes", True)
        critic_feedback = result.content
    except Exception as exc:
        logger.warning(f"[Supervisor] Critic failed (non-fatal): {exc}")

    duration_ms = round((time.perf_counter() - t0) * 1000, 2)
    trace.append({
        "node":         "critic_verification",
        "status":       "DONE",
        "score":        critic_score,
        "passes":       critic_passes,
        "duration_ms":  duration_ms,
    })

    current_retries = int(state.get("retry_count", 0))

    return {
        "critic_score":      critic_score,
        "critic_passes":     critic_passes,
        "critic_feedback":   critic_feedback,
        "retry_count":       current_retries + (0 if critic_passes else 1),
        "critic_retry_hint": critic_feedback if not critic_passes else "",
        "supervisor_trace":  trace,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Node: Synthesizer (Final Response)
# ─────────────────────────────────────────────────────────────────────────────

async def synthesizer_node(state: MissionState, config: RunnableConfig) -> Dict:
    """Synthesize the final unified response from all agent outputs."""
    t0 = time.perf_counter()
    merged   = state.get("merged_content", "")
    query    = state.get("query", "")
    from app.core.config import settings
    model    = state.get("active_model", settings.GEMINI_MODEL)
    api_keys = state.get("api_keys", {})
    critic_feedback = state.get("critic_feedback", "")
    trace = list(state.get("supervisor_trace") or [])

    final_response = merged  # fallback

    try:
        from app.agents.node_helpers import call_llm_simple
        synth_prompt = (
            f"You are a synthesis agent. Combine the following multi-agent research "
            f"results into a single coherent, well-structured response to this query:\n\n"
            f"**Query:** {query}\n\n"
            f"**Multi-Agent Results:**\n{merged[:6000]}\n\n"
        )
        if critic_feedback:
            synth_prompt += f"**Critic Feedback to address:**\n{critic_feedback}\n\n"
        synth_prompt += (
            "Write a comprehensive, well-organized final response. "
            "Use Markdown formatting. Preserve all citations and code blocks."
        )

        final_response = await call_llm_simple(
            prompt=synth_prompt,
            model=model,
            api_keys=api_keys,
            system="You are a professional synthesis agent. Produce clean, well-structured Markdown.",
            temperature=0.3,
            max_tokens=6000,
        )
    except Exception as exc:
        logger.warning(f"[Supervisor] Synthesis LLM failed: {exc}, using merged output")

    duration_ms = round((time.perf_counter() - t0) * 1000, 2)
    trace.append({
        "node":        "synthesizer",
        "status":      "DONE",
        "duration_ms": duration_ms,
    })

    return {
        "final_response": final_response,
        "supervisor_trace": trace,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Node: Delegate to existing Agent Graph (simple path)
# ─────────────────────────────────────────────────────────────────────────────

async def delegate_to_agent_graph_node(state: MissionState, config: RunnableConfig) -> Dict:
    """
    Pass-through to the existing Phase 3 agent graph for simple queries.
    This preserves full backward compatibility with all existing functionality.
    """
    trace = list(state.get("supervisor_trace") or [])
    trace.append({"node": "delegate_to_agent_graph", "status": "DELEGATED"})
    # The existing graph will be invoked by the API layer if is_mission=False
    return {
        "final_response": "",   # Signal to API: use existing graph
        "supervisor_trace": trace,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Conditional routing
# ─────────────────────────────────────────────────────────────────────────────

def route_after_classify(state: MissionState) -> str:
    if state.get("is_mission", False) and state.get("agent_tasks"):
        return "parallel_dispatch"
    return "delegate"


MAX_CRITIC_RETRIES = 2   # max re-plan cycles before accepting output anyway
CRITIC_PASS_THRESHOLD = 0.65  # score below this triggers a retry


def route_after_critic(state: MissionState) -> str:
    """
    After critic_verification, decide what to do:
      1. HITL needed → END (graph interrupted, waits for human approval)
      2. Critic failed + retries left → supervisor_classify (re-plan with feedback)
      3. Otherwise → synthesizer (produce final response)
    """
    # 1 — HITL gate (human approval required)
    if state.get("requires_approval") and state.get("approval_status") != "approved":
        return END

    # 2 — Critic retry: low score and we haven't hit the limit
    score     = float(state.get("critic_score", 1.0))
    passes    = bool(state.get("critic_passes", True))
    retries   = int(state.get("retry_count", 0))

    if not passes and score < CRITIC_PASS_THRESHOLD and retries < MAX_CRITIC_RETRIES:
        logger.info(
            f"[Supervisor] Critic retry #{retries+1} triggered "
            f"(score={score:.2f} < {CRITIC_PASS_THRESHOLD})"
        )
        return "supervisor_classify"

    # 3 — Proceed to synthesis
    return "synthesizer"


# ─────────────────────────────────────────────────────────────────────────────
#  Build Supervisor Graph
# ─────────────────────────────────────────────────────────────────────────────

def build_supervisor_graph(checkpointer=None):
    """
    Build and compile the Supervisor LangGraph with critic retry loop.

    Graph flow:
      supervisor_classify → parallel_dispatch → result_collector
        → critic_verification:
            - score OK / max retries → synthesizer → END
            - score low & retries left → supervisor_classify (re-plan)
            - requires HITL → END (HITL interrupt)
    """
    workflow = StateGraph(MissionState)

    workflow.add_node("supervisor_classify", supervisor_classify_node)
    workflow.add_node("parallel_dispatch",   parallel_dispatch_node)
    workflow.add_node("result_collector",    result_collector_node)
    workflow.add_node("critic_verification", critic_verification_node)
    workflow.add_node("synthesizer",         synthesizer_node)
    workflow.add_node("delegate",            delegate_to_agent_graph_node)

    workflow.set_entry_point("supervisor_classify")

    workflow.add_conditional_edges(
        "supervisor_classify",
        route_after_classify,
        {
            "parallel_dispatch": "parallel_dispatch",
            "delegate":          "delegate",
        },
    )

    workflow.add_edge("parallel_dispatch", "result_collector")
    workflow.add_edge("result_collector",  "critic_verification")

    # Critic gate: retry re-plan, HITL, or proceed to synthesizer
    workflow.add_conditional_edges(
        "critic_verification",
        route_after_critic,
        {
            "supervisor_classify": "supervisor_classify",
            "synthesizer":         "synthesizer",
            END:                   END,
        },
    )

    workflow.add_edge("synthesizer", END)
    workflow.add_edge("delegate",    END)

    compile_kwargs: Dict[str, Any] = {}
    if checkpointer:
        compile_kwargs["checkpointer"]    = checkpointer
        compile_kwargs["interrupt_before"] = ["synthesizer"]

    return workflow.compile(**compile_kwargs)



# ─────────────────────────────────────────────────────────────────────────────
#  Module-level singleton with persistent SQLite checkpointer
# ─────────────────────────────────────────────────────────────────────────────

import os
from pathlib import Path

_CHECKPOINT_DB = os.getenv(
    "AGENT_CHECKPOINT_DB",
    str(Path("data") / "agent_checkpoints.db")
)

def _create_supervisor() -> Any:
    """
    Build the supervisor graph with the best available checkpointer.

    langgraph-checkpoint-sqlite v3.x requires AsyncSqliteSaver to be
    entered as an async context manager inside a running event loop, so
    it cannot be used at module import time.  We compile the graph with
    InMemorySaver here (still gives per-conversation isolation) and the
    job queue passes a fresh AsyncSqliteSaver context at execution time
    when a real event loop is available.
    """
    try:
        from langgraph.checkpoint.memory import MemorySaver
        Path(_CHECKPOINT_DB).parent.mkdir(parents=True, exist_ok=True)
        memory = MemorySaver()
        graph  = build_supervisor_graph(checkpointer=memory)
        logger.info("[Supervisor] Compiled with MemorySaver (per-process persistence).")
        return graph
    except Exception as exc:
        logger.warning(f"[Supervisor] MemorySaver unavailable ({exc}), compiling stateless.")
        return build_supervisor_graph(checkpointer=None)


supervisor_graph = _create_supervisor()


async def get_supervisor_with_sqlite():
    """
    Return a supervisor graph compiled with the async SQLite checkpointer.
    Call inside an async context (e.g. from the job queue worker).
    Yields the graph so it can be used as an async context manager.
    """
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    Path(_CHECKPOINT_DB).parent.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(_CHECKPOINT_DB) as saver:
        graph = build_supervisor_graph(checkpointer=saver)
        yield graph

