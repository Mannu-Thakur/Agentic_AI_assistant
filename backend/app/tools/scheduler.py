"""
app/tools/scheduler.py — Parallel Tool Execution Scheduler (Phase 3).

Design:
  - Accepts a list of ToolTask objects that form a dependency DAG.
  - Executes independent tasks concurrently using asyncio.gather().
  - Injects outputs from upstream tasks into downstream task arguments
    via template variable substitution: "$tc_<id>.<field>".
  - Supports per-task timeouts, partial failure isolation, and retries.
  - Returns a ToolExecutionResult per task with status, output, latency_ms.

Example DAG:
  [
    {"id": "ocr",     "tool": "python_sandbox", "args": {"code": "..."}, "depends_on": []},
    {"id": "expense", "tool": "calculate",       "args": {"expr": "$tc_ocr.total"}, "depends_on": ["ocr"]},
    {"id": "total",   "tool": "python_sandbox", "args": {"code": "..."}, "depends_on": ["ocr"]},
  ]
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("app.tools.scheduler")

# Variable substitution pattern: $tc_<task_id>.<field>
_VAR_PATTERN = re.compile(r"\$tc_(\w+)\.(\w+)")


@dataclass
class ToolTask:
    """Represents a single node in the tool execution DAG."""
    id: str                          # Unique identifier within this DAG
    tool: str                        # Registered tool name
    args: Dict[str, Any]             # Arguments (may contain $tc_... variables)
    depends_on: List[str] = field(default_factory=list)  # IDs of prerequisite tasks
    timeout: float = 30.0            # Per-task timeout in seconds
    retries: int = 1                 # Max retry attempts on transient failure


@dataclass
class ToolResult:
    """Execution result for a single ToolTask."""
    id: str
    tool: str
    status: str          # "success" | "error" | "timeout" | "skipped"
    output: str          # Raw tool output or error message
    latency_ms: float
    attempts: int = 1


class ToolScheduler:
    """
    DAG-based parallel tool execution scheduler.

    Usage:
        registry = ToolRegistry()
        tasks = [ToolTask(...), ToolTask(...)]
        results = await ToolScheduler(registry).run(tasks)
    """

    def __init__(self, registry):
        """
        Args:
            registry: ToolRegistry singleton with an async call_tool() method.
        """
        self._registry = registry

    async def run(self, tasks: List[ToolTask]) -> List[ToolResult]:
        """
        Execute all tasks in topological order, running independent tasks in parallel.

        Returns:
            List of ToolResult in the same order as input tasks.
        """
        if not tasks:
            return []

        # Build task lookup and validate DAG
        task_map: Dict[str, ToolTask] = {t.id: t for t in tasks}
        self._validate_dag(task_map)

        # Track results as they complete
        results: Dict[str, ToolResult] = {}

        # Process in topological levels (BFS)
        pending = set(task_map.keys())
        completed: set[str] = set()

        while pending:
            # Find all tasks whose dependencies are satisfied
            ready = [
                tid for tid in pending
                if all(dep in completed for dep in task_map[tid].depends_on)
            ]

            if not ready:
                # Circular dependency — break remaining tasks as "skipped"
                for tid in pending:
                    results[tid] = ToolResult(
                        id=tid, tool=task_map[tid].tool,
                        status="skipped", output="Circular dependency detected.",
                        latency_ms=0.0
                    )
                break

            # Execute all ready tasks concurrently
            coros = [self._execute_task(task_map[tid], results) for tid in ready]
            batch_results = await asyncio.gather(*coros, return_exceptions=False)

            for res in batch_results:
                results[res.id] = res
                completed.add(res.id)
                pending.discard(res.id)

        # Return results in original task order
        return [results[t.id] for t in tasks if t.id in results]

    async def _execute_task(self, task: ToolTask, prior_results: Dict[str, ToolResult]) -> ToolResult:
        """Execute a single task, resolving variable substitutions and applying retries/timeout."""
        resolved_args = self._resolve_variables(task.args, prior_results)

        # Skip if any dependency failed
        for dep_id in task.depends_on:
            dep = prior_results.get(dep_id)
            if dep and dep.status in ("error", "timeout", "skipped"):
                logger.warning(
                    f"[Scheduler] Skipping task '{task.id}' — dependency '{dep_id}' failed ({dep.status})."
                )
                return ToolResult(
                    id=task.id, tool=task.tool,
                    status="skipped", output=f"Skipped: dependency '{dep_id}' failed.",
                    latency_ms=0.0
                )

        attempts = 0
        last_error = ""
        start = time.monotonic()

        while attempts <= task.retries:
            attempts += 1
            try:
                output = await asyncio.wait_for(
                    self._registry.call_tool(task.tool, resolved_args),
                    timeout=task.timeout,
                )
                latency_ms = round((time.monotonic() - start) * 1000, 1)
                logger.info(
                    f"[Scheduler] '{task.id}' ({task.tool}) SUCCESS in {latency_ms}ms "
                    f"(attempt {attempts})"
                )
                return ToolResult(
                    id=task.id, tool=task.tool,
                    status="success", output=str(output),
                    latency_ms=latency_ms, attempts=attempts,
                )
            except asyncio.TimeoutError:
                last_error = f"Task '{task.id}' timed out after {task.timeout}s."
                logger.warning(f"[Scheduler] TIMEOUT: {last_error}")
                latency_ms = round((time.monotonic() - start) * 1000, 1)
                return ToolResult(
                    id=task.id, tool=task.tool,
                    status="timeout", output=last_error,
                    latency_ms=latency_ms, attempts=attempts,
                )
            except Exception as exc:
                last_error = str(exc)
                logger.warning(
                    f"[Scheduler] ERROR task '{task.id}' attempt {attempts}: {last_error}"
                )
                if attempts > task.retries:
                    break
                await asyncio.sleep(0.5 * attempts)  # exponential backoff

        latency_ms = round((time.monotonic() - start) * 1000, 1)
        return ToolResult(
            id=task.id, tool=task.tool,
            status="error", output=f"Failed after {attempts} attempt(s): {last_error}",
            latency_ms=latency_ms, attempts=attempts,
        )

    @staticmethod
    def _resolve_variables(args: Dict[str, Any], prior_results: Dict[str, ToolResult]) -> Dict[str, Any]:
        """
        Substitute $tc_<task_id>.<field> variables in argument values.

        Example: "$tc_ocr.output" → prior_results["ocr"].output
        Supported fields: output, status
        """
        def _resolve_str(val: str) -> str:
            def replace(m: re.Match) -> str:
                ref_id, attr = m.group(1), m.group(2)
                ref = prior_results.get(ref_id)
                if ref is None:
                    return m.group(0)  # no substitution
                return getattr(ref, attr, m.group(0))
            return _VAR_PATTERN.sub(replace, val)

        resolved: Dict[str, Any] = {}
        for key, val in args.items():
            if isinstance(val, str):
                resolved[key] = _resolve_str(val)
            else:
                resolved[key] = val
        return resolved

    @staticmethod
    def _validate_dag(task_map: Dict[str, ToolTask]) -> None:
        """Validate that all dependency references point to existing tasks."""
        for tid, task in task_map.items():
            for dep in task.depends_on:
                if dep not in task_map:
                    raise ValueError(
                        f"Task '{tid}' depends on unknown task '{dep}'."
                    )
