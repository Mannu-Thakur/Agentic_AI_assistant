"""
benchmarks/scorers/agentic_scorer.py — Scorer for Multi-Step Agentic workflows.

Evaluates:
  - Execution Step Completion Rate (% of expected state graph nodes traversed)
  - Tool Calling Efficiency (adequate tools called without redundant loops)
  - Compound Query Decomposition (sub_questions extracted and answered)
  - Planning Node Execution (plan and tool_planner invoked)
  - Final Synthesis Quality
"""

from __future__ import annotations

from typing import Any


def score_agentic(case: dict[str, Any], response_data: dict[str, Any]) -> dict[str, Any]:
    """
    Score a multi-step / compound agentic workflow test case.
    """
    expected_steps = case.get("expected_steps", [])
    expected_keywords = case.get("expected_answer_keywords", [])
    min_tools = int(case.get("min_tool_calls", 0))

    resp_text = response_data.get("response_text", "").lower()
    trace = response_data.get("execution_trace", [])
    tool_results = response_data.get("tool_execution_results", [])
    sub_questions = response_data.get("sub_questions", [])

    # Extract all node names executed in the trace
    executed_nodes = {
        s.get("name")
        for s in trace
        if s.get("status") in ("EXECUTED", "COMPLETED")
    }

    # 1. Step completion rate
    if expected_steps:
        matched_steps = [s for s in expected_steps if s in executed_nodes]
        step_completion = len(matched_steps) / len(expected_steps)
    else:
        step_completion = 1.0

    # 2. Planning executed
    planning_executed = any(n in executed_nodes for n in ("plan", "tool_planner"))
    planning_score = 1.0 if planning_executed else 0.5

    # 3. Tool efficiency
    actual_tool_count = len(tool_results)
    if min_tools > 0:
        tool_efficiency = min(actual_tool_count / float(min_tools), 1.0)
    else:
        tool_efficiency = 1.0

    # 4. Answer keyword coverage
    if expected_keywords:
        matched_kw = sum(1 for kw in expected_keywords if kw.lower() in resp_text)
        answer_cov = matched_kw / len(expected_keywords)
    else:
        answer_cov = 1.0 if len(resp_text) > 150 else 0.5

    # 5. Compound query sub-question detection
    is_compound = (case.get("test_type") == "compound_query")
    if is_compound:
        sub_q_score = 1.0 if len(sub_questions) >= 2 else (0.7 if len(resp_text) > 200 else 0.4)
    else:
        sub_q_score = 1.0

    # Composite score
    score = (
        0.30 * step_completion
        + 0.25 * answer_cov
        + 0.20 * tool_efficiency
        + 0.15 * planning_score
        + 0.10 * sub_q_score
    )
    score = min(max(score, 0.0), 1.0)

    return {
        "score": round(score, 4),
        "raw_metrics": {
            "step_completion": round(step_completion, 3),
            "steps_found": list(executed_nodes),
            "steps_expected": expected_steps,
            "tool_efficiency": round(tool_efficiency, 3),
            "tools_called_count": actual_tool_count,
            "answer_coverage": round(answer_cov, 3),
            "planning_executed": planning_executed,
            "sub_questions_detected": len(sub_questions),
            "response_length": len(resp_text),
        },
    }
