"""
benchmarks/scorers/mcp_scorer.py — Scorer for Model Context Protocol (MCP) tool execution.

Evaluates:
  - Tool Selection Accuracy (binary 0/1)
  - Argument Extraction Precision, Recall, and F1
  - End-to-End Success Rate (tool executed without error)
  - Intent Classifier Precision (detected as MCP_TOOL or COMPLEX)
"""

from __future__ import annotations

from typing import Any


def _flatten_args(d: Any, prefix: str = "") -> dict[str, str]:
    """Flatten nested dictionary into key-value strings for comparison."""
    items: dict[str, str] = {}
    if isinstance(d, dict):
        for k, v in d.items():
            new_prefix = f"{prefix}.{k}" if prefix else str(k)
            items.update(_flatten_args(v, new_prefix))
    elif isinstance(d, list):
        for i, v in enumerate(d):
            new_prefix = f"{prefix}[{i}]"
            items.update(_flatten_args(v, new_prefix))
    else:
        items[prefix] = str(d).strip().lower()
    return items


def _compute_arg_f1(expected: dict[str, Any], actual: dict[str, Any]) -> tuple[float, float, float]:
    """Compute argument extraction precision, recall, and F1."""
    if not expected:
        return 1.0, 1.0, 1.0

    exp_flat = _flatten_args(expected)
    act_flat = _flatten_args(actual)

    if not act_flat:
        return 0.0, 0.0, 0.0

    matches = 0
    for exp_k, exp_v in exp_flat.items():
        for act_k, act_v in act_flat.items():
            if exp_k.lower() in act_k.lower() or act_k.lower() in exp_k.lower():
                # Check value fuzzy match
                if exp_v in act_v or act_v in exp_v:
                    matches += 1
                    break

    precision = matches / len(act_flat) if act_flat else 0.0
    recall = matches / len(exp_flat) if exp_flat else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    return precision, recall, f1


def score_mcp_tool(case: dict[str, Any], response_data: dict[str, Any]) -> dict[str, Any]:
    """
    Score an MCP / tool-calling test case against runtime execution results.
    """
    expected_tool = case.get("expected_tool", "").lower()
    expected_args = case.get("expected_args", {})
    expected_pattern = case.get("expected_result_pattern", "").lower()

    tool_results = response_data.get("tool_execution_results", [])
    intent = response_data.get("intent", "").upper()
    resp_text = response_data.get("response_text", "").lower()

    # 1. Intent accuracy
    valid_intents = {"MCP_TOOL", "COMPLEX", "CODE_EXECUTION"}
    intent_accuracy = 1.0 if intent in valid_intents else 0.0

    # 2. Tool selection accuracy & actual args
    tool_selection_accuracy = 0.0
    actual_args: dict[str, Any] = {}
    e2e_success = 0.0
    tools_called: list[str] = []

    for tr in tool_results:
        tname = tr.get("tool", "").lower()
        tools_called.append(tname)
        if expected_tool in tname or tname in expected_tool:
            tool_selection_accuracy = 1.0
            actual_args = tr.get("args", {}) or {}
            # Check execution status
            if tr.get("status") == "success":
                e2e_success = 1.0
            # Also check output pattern if status is not explicitly success
            out = str(tr.get("output", "")).lower()
            if expected_pattern and expected_pattern in out:
                e2e_success = 1.0

    # Also check if tool was called in execution trace
    if tool_selection_accuracy == 0.0:
        trace = response_data.get("execution_trace", [])
        for step in trace:
            sname = step.get("name", "").lower()
            if expected_tool in sname or "execute_tools" in sname:
                if expected_tool in resp_text:
                    tool_selection_accuracy = 0.8

    # 3. Argument extraction F1
    arg_p, arg_r, arg_f1 = _compute_arg_f1(expected_args, actual_args)

    # 4. Check if final response incorporates expected result pattern
    if expected_pattern and expected_pattern in resp_text:
        e2e_success = max(e2e_success, 0.9)

    # Composite score
    score = (
        0.35 * tool_selection_accuracy
        + 0.25 * arg_f1
        + 0.25 * e2e_success
        + 0.15 * intent_accuracy
    )
    score = min(max(score, 0.0), 1.0)

    return {
        "score": round(score, 4),
        "raw_metrics": {
            "tool_selection_accuracy": round(tool_selection_accuracy, 3),
            "arg_precision": round(arg_p, 3),
            "arg_recall": round(arg_r, 3),
            "arg_f1": round(arg_f1, 3),
            "e2e_success": round(e2e_success, 3),
            "intent_accuracy": round(intent_accuracy, 3),
            "tools_called": tools_called,
        },
    }
