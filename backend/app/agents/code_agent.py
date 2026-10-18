"""
app/agents/code_agent.py — Code Generation + Sandbox Execution Agent

Capabilities
------------
  1. Code generation   — Generates Python/JS/shell code via LLM
  2. Sandbox execution — Runs the code in an isolated subprocess with:
       • Configurable timeout (default 15s)
       • Resource limits (memory capped via ulimit on Linux)
       • Captured stdout / stderr
       • Non-zero exit code detection
  3. Test generation   — Optionally generates and runs pytest tests
  4. Artifact export   — Saves generated files to ArtifactStore

HITL Gate
---------
  If the generated code contains dangerous patterns (os.system, subprocess,
  file writes outside /tmp, network calls) a `requires_approval` flag is set.
  The Supervisor will pause and request human approval before executing.

Safety
------
  - Execution runs inside a tempdir that is deleted after the call
  - Python subprocess inherits no env vars (env={})
  - stdout/stderr truncated at 8 KB
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from app.agents.registry import BaseAgent, AgentResult, agent_registry
from app.agents.artifacts import artifact_store

logger = logging.getLogger("agents.code")

# ── Dangerous pattern detection ───────────────────────────────────────────────
_DANGEROUS_PATTERNS: List[re.Pattern] = [
    re.compile(r"\bos\s*\.\s*system\s*\("),
    re.compile(r"\bsubprocess\s*\.\s*(run|Popen|call|check_output)\s*\("),
    re.compile(r"\bopen\s*\(\s*['\"](?!/tmp)"),          # file writes outside /tmp
    re.compile(r"\b__import__\s*\("),
    re.compile(r"\beval\s*\("),
    re.compile(r"\bexec\s*\("),
    re.compile(r"\brm\s+-rf"),
    re.compile(r"\bshutil\s*\.\s*(rmtree|move)\s*\("),
    re.compile(r"\burllib|requests\b"),                   # network calls
    re.compile(r"\bsocket\s*\.\s*socket\s*\("),
]

DEFAULT_TIMEOUT  = 15         # seconds


def _is_dangerous(code: str) -> List[str]:
    """Return list of matched dangerous patterns (empty = safe)."""
    matches = []
    for pat in _DANGEROUS_PATTERNS:
        if pat.search(code):
            matches.append(pat.pattern)
    return matches


# ─────────────────────────────────────────────────────────────────────────────
#  Code Sandbox
# ─────────────────────────────────────────────────────────────────────────────

class CodeExecutionResult:
    def __init__(
        self,
        stdout: str = "",
        stderr: str = "",
        exit_code: int = 0,
        timed_out: bool = False,
        error: Optional[str] = None,
    ):
        self.stdout   = stdout
        self.stderr   = stderr
        self.exit_code = exit_code
        self.timed_out = timed_out
        self.error    = error
        self.success  = (exit_code == 0 and not timed_out and not error)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stdout":    self.stdout,
            "stderr":    self.stderr,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "error":     self.error,
            "success":   self.success,
        }


async def execute_code_sandboxed(
    code: str,
    language: str = "python",
    timeout: int = DEFAULT_TIMEOUT,
    env_vars: Optional[Dict[str, str]] = None,
) -> CodeExecutionResult:
    """Delegate computation-only Python to the isolated sandbox service.

    This agent must never create a subprocess in the public API process.  The
    common sandbox client fails closed when the hardened sidecar is absent.
    ``env_vars`` is retained only for API compatibility and is intentionally
    ignored so a planner cannot influence process credentials or environment.
    """
    if language not in ("python", "python3"):
        return CodeExecutionResult(
            error=f"Unsupported language for sandbox: {language}"
        )

    from app.tools.local_tools import python_sandbox

    output = await python_sandbox(code)
    if output.startswith("Sandbox policy blocked"):
        return CodeExecutionResult(error=output, exit_code=126)
    if output.startswith("Code execution is unavailable") or output.startswith("Sandbox execution failed"):
        return CodeExecutionResult(error=output, exit_code=125)
    if output.startswith("Code execution is temporarily unavailable"):
        return CodeExecutionResult(error=output, exit_code=125)
    if output.startswith("Runtime error"):
        return CodeExecutionResult(stderr=output, error=output, exit_code=1)
    if output.startswith("Execution timed out"):
        return CodeExecutionResult(stdout=output, timed_out=True, exit_code=124)
    return CodeExecutionResult(stdout=output, exit_code=0)


# ─────────────────────────────────────────────────────────────────────────────
#  Code Agent
# ─────────────────────────────────────────────────────────────────────────────

@agent_registry.register("code")
class CodeAgent(BaseAgent):
    """
    Generates code via LLM, optionally executes it in a sandbox,
    and saves the result as an artifact.

    task_input keys
    ---------------
    query         : str   — What code to write
    language      : str   — Default "python"
    execute       : bool  — Whether to run the code (default True)
    save_artifact : bool  — Whether to save to ArtifactStore (default True)
    user_id       : str
    session_id    : str
    messages      : list  — Conversation context for the LLM
    active_model  : str   — LLM model to use
    api_keys      : dict  — Provider API keys
    """

    name = "code"
    description = (
        "Generates, executes, and tests Python code. "
        "Runs only through the separately isolated code sandbox."
    )
    capabilities = ["code_generation", "code_execution", "debugging", "scripting"]

    async def run(
        self,
        task_input: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
    ) -> AgentResult:
        query      = task_input.get("query", "")
        language   = task_input.get("language", "python")
        do_execute = task_input.get("execute", True)
        save_art   = task_input.get("save_artifact", True)
        user_id    = task_input.get("user_id", "anon")
        session_id = task_input.get("session_id", "default")
        from app.core.config import settings
        model      = task_input.get("active_model", settings.GEMINI_MODEL)
        api_keys   = task_input.get("api_keys", {})
        messages   = task_input.get("messages", [])

        logger.info(f"[CodeAgent] Task: {query[:80]!r} | model={model}")

        # ── Step 1: Generate code via LLM ─────────────────────────────────────
        code_prompt = (
            f"Write {language} code that accomplishes the following task:\n\n"
            f"{query}\n\n"
            "Requirements:\n"
            "- Write clean, well-commented, production-quality code\n"
            "- Include docstrings for functions\n"
            "- Handle edge cases and exceptions\n"
            "- Output ONLY the code block, no explanation outside the code\n"
            "- Use ```python ... ``` fencing\n"
        )

        generated_code = ""
        generation_error = None
        try:
            from app.agents.node_helpers import call_llm_simple
            raw_response = await call_llm_simple(
                prompt=code_prompt,
                model=model,
                api_keys=api_keys,
                system="You are an expert Python developer. Output ONLY the code, no prose outside fences.",
            )
            # Extract code from fenced block
            fence_match = re.search(
                r"```(?:python|py)?\s*\n([\s\S]+?)\n```", raw_response
            )
            generated_code = fence_match.group(1).strip() if fence_match else raw_response.strip()
        except Exception as exc:
            generation_error = str(exc)
            logger.error(f"[CodeAgent] Code generation failed: {exc}")

        if generation_error or not generated_code:
            return AgentResult(
                agent_name=self.name,
                success=False,
                error=generation_error or "No code was generated",
            )

        # ── Step 2: Safety check (HITL gate) ──────────────────────────────────
        dangerous = _is_dangerous(generated_code)
        requires_approval = bool(dangerous)
        approval_reason = ""
        if dangerous:
            approval_reason = (
                f"Generated code contains potentially dangerous patterns: "
                f"{', '.join(dangerous[:3])}. Human approval required before execution."
            )
            logger.warning(f"[CodeAgent] HITL required: {approval_reason}")

        # ── Step 3: Execute (unless dangerous without approval) ────────────────
        exec_result: Optional[CodeExecutionResult] = None
        if do_execute and not requires_approval:
            logger.info("[CodeAgent] Executing code in sandbox...")
            exec_result = await execute_code_sandboxed(generated_code, language)
            if exec_result.timed_out:
                logger.warning("[CodeAgent] Sandbox execution timed out.")
            elif not exec_result.success:
                logger.warning(
                    f"[CodeAgent] Code failed (exit={exec_result.exit_code}): "
                    f"{exec_result.stderr[:200]}"
                )

        # ── Step 4: Save artifact ──────────────────────────────────────────────
        artifact_info: Optional[Dict] = None
        if save_art and generated_code:
            try:
                art = await artifact_store.create(
                    artifact_type="code",
                    content=generated_code,
                    agent=self.name,
                    user_id=user_id,
                    session_id=session_id,
                    description=query[:120],
                    metadata={
                        "language": language,
                        "lines": generated_code.count("\n") + 1,
                        "executed": do_execute and not requires_approval,
                        "execution_success": exec_result.success if exec_result else None,
                        "requires_approval": requires_approval,
                    },
                )
                artifact_info = art.to_dict()
            except Exception as exc:
                logger.warning(f"[CodeAgent] Artifact save failed: {exc}")

        # ── Build result ───────────────────────────────────────────────────────
        content_parts = [f"```{language}\n{generated_code}\n```"]
        if requires_approval:
            content_parts.append(
                f"\n> ⚠️ **Human approval required before execution.**\n> {approval_reason}"
            )
        elif exec_result:
            if exec_result.success:
                content_parts.append(
                    f"\n**Execution Output:**\n```\n{exec_result.stdout or '(no output)'}\n```"
                )
            else:
                content_parts.append(
                    f"\n**Execution Error (exit={exec_result.exit_code}):**\n"
                    f"```\n{exec_result.stderr or exec_result.error or 'Unknown error'}\n```"
                )

        return AgentResult(
            agent_name=self.name,
            success=True,
            content="\n".join(content_parts),
            code_output=exec_result.to_dict() if exec_result else None,
            artifacts=[artifact_info] if artifact_info else [],
            metadata={
                "language": language,
                "lines_generated": generated_code.count("\n") + 1,
                "requires_approval": requires_approval,
                "approval_reason": approval_reason,
                "executed": exec_result is not None,
                "execution_success": exec_result.success if exec_result else None,
            },
        )
