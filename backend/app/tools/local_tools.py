"""
tools/local_tools.py — Locally-implemented agent tools.

tavily_search():
  • Now delegates to app.services.web_search.unified_web_search
  • Waterfall: Tavily → SerpAPI → Exa AI → DuckDuckGo (free fallback)
  • BM25-ranks results before returning
  • api_keys dict accepted so user-supplied keys override .env

python_sandbox():
  • Delegates computation-only code to an isolated, authenticated service.
  • Fails closed when that service is not configured or reachable.
  • Strips ANSI escape codes and caps returned output.
"""

import re
import logging
from typing import Optional
from app.core.config import settings


from app.core.cache_service import web_search_cache

logger = logging.getLogger(__name__)

# ── Safety constants ───────────────────────────────────────────────────────────
_MAX_OUTPUT_BYTES  = 65_536      # 64 KB output cap

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


import ast


# ─────────────────────────────────────────────────────────────────────────────
#  Web search
# ─────────────────────────────────────────────────────────────────────────────

async def _ddg_search_fallback(query: str) -> str:
    from app.services.web_search import search_duckduckgo, format_for_llm
    results = await search_duckduckgo(query)
    return format_for_llm(results)


async def tavily_search(query: str, api_keys: Optional[dict] = None) -> str:
    """
    Unified web search entry point.

    Delegates to app.services.web_search.unified_web_search which tries
    providers in priority order (Tavily → SerpAPI → Exa AI → DuckDuckGo)
    and BM25-ranks results before returning.

    Args:
        query:    The search query (injected context already stripped by nodes.py).
        api_keys: Dict of provider keys from the user session.  Server .env
                  keys are merged automatically inside unified_web_search.

    Returns:
        A formatted markdown string ready for LLM consumption.
    """
    from app.services.web_search import unified_web_search, format_for_llm
    import hashlib
    import json

    keys = dict(api_keys or {})
    key_sig = hashlib.md5(json.dumps(sorted(keys.items()), default=str).encode()).hexdigest()[:12]
    cache_key = f"{query}:{key_sig}"

    # Cache check (query + provider keys signature)
    cached = await web_search_cache.get(cache_key)
    if cached is not None:
        logger.debug(f"[tavily_search] Cache HIT for key='{cache_key[:60]}'")
        return cached

    try:
        results = await unified_web_search(query, keys)
        result_text = format_for_llm(results)
        await web_search_cache.set(cache_key, result_text)
        return result_text
    except Exception as exc:
        logger.error(f"[tavily_search] unified_web_search failed: {exc}")
        return f"Live web search is currently unavailable for this query (error: {exc}). Please inform the user that live internet search could not be completed."


# ─────────────────────────────────────────────────────────────────────────────
#  Stateless calculation
# ─────────────────────────────────────────────────────────────────────────────

_CALC_OPERATORS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a ** b,
}


def _evaluate_expression(node: ast.AST) -> int | float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        operand = _evaluate_expression(node.operand)
        return -operand if isinstance(node.op, ast.USub) else operand
    if isinstance(node, ast.BinOp) and type(node.op) in _CALC_OPERATORS:
        left, right = _evaluate_expression(node.left), _evaluate_expression(node.right)
        if isinstance(node.op, ast.Pow) and (abs(right) > 100 or abs(left) > 1_000_000):
            raise ValueError("exponent is outside the safe calculator range")
        return _CALC_OPERATORS[type(node.op)](left, right)
    raise ValueError("only numeric arithmetic is supported")


async def calculate(expression: str) -> str:
    """Evaluate a basic arithmetic expression without a subprocess or MCP server."""
    if not expression or len(expression) > 256:
        return "Calculation failed: provide an arithmetic expression up to 256 characters."
    try:
        tree = ast.parse(expression, mode="eval")
        result = _evaluate_expression(tree.body)
        if isinstance(result, complex) or (isinstance(result, float) and (result != result or result in (float("inf"), float("-inf")))):
            raise ValueError("result is not a finite real number")
        return str(result)
    except (SyntaxError, ValueError, ZeroDivisionError, OverflowError) as exc:
        return f"Calculation failed: {exc}"


# ─────────────────────────────────────────────────────────────────────────────
#  Python sandbox
# ─────────────────────────────────────────────────────────────────────────────

async def python_sandbox(code: str) -> str:
    """
    Execute computation-only Python through the separate isolated sandbox
    service.  The web process never executes user code on its own host.

    The service accepts a deliberately small Python subset (no imports,
    attributes, files, network, or reflection).  If the service is not wired,
    fail closed with an operator-actionable message rather than falling back to
    a local subprocess.
    """
    if not code or not code.strip():
        return "Sandbox execution failed: no Python code was provided."
    if len(code) > 20_000:
        return "Sandbox execution failed: code exceeds the 20,000 character safety limit."
    if not settings.ENABLE_CODE_EXECUTION:
        return (
            "Code execution is unavailable because this deployment has not enabled "
            "the isolated code sandbox. It was not executed."
        )
    if not settings.CODE_SANDBOX_URL or not settings.SANDBOX_SHARED_SECRET:
        logger.error("Code execution requested without a configured isolated sandbox")
        return "Code execution is unavailable: the isolated sandbox is not configured. It was not executed."

    try:
        import httpx
        timeout = max(1.0, min(float(settings.CODE_SANDBOX_TIMEOUT_SECONDS), 30.0))
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            response = await client.post(
                settings.CODE_SANDBOX_URL.rstrip("/") + "/execute",
                json={"code": code},
                headers={"X-Sandbox-Token": settings.SANDBOX_SHARED_SECRET},
            )
        if response.status_code == 401:
            logger.error("Isolated sandbox rejected backend authentication")
            return "Code execution is temporarily unavailable because sandbox authentication failed. It was not executed."
        if response.status_code == 422:
            detail = response.json().get("detail", "The code violates sandbox policy.")
            return f"Sandbox policy blocked execution: {detail}"
        response.raise_for_status()
        payload = response.json()
        output = _strip_ansi(str(payload.get("output", ""))).strip()
        return output[:_MAX_OUTPUT_BYTES] or "[Execution completed with no output]"
    except Exception as exc:
        logger.error("Isolated sandbox request failed: %s", type(exc).__name__)
        return "Code execution is temporarily unavailable because the isolated sandbox could not be reached. It was not executed."

