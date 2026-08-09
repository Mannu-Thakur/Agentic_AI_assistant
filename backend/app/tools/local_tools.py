"""
tools/local_tools.py — Locally-implemented agent tools.

tavily_search():
  • Now delegates to app.services.web_search.unified_web_search
  • Waterfall: Tavily → SerpAPI → Exa AI → DuckDuckGo (free fallback)
  • BM25-ranks results before returning
  • api_keys dict accepted so user-supplied keys override .env

python_sandbox():
  • Hard output size limit (64 KB) prevents memory exhaustion.
  • Kills the subprocess on timeout AND on output-size overflow.
  • Adds a security warning header when dangerous stdlib modules are imported.
  • Strips ANSI escape codes from output.
"""

import os
import re
import sys
import json
import asyncio
import logging
import tempfile
from typing import Optional
from app.core.config import settings


from app.core.cache_service import web_search_cache

logger = logging.getLogger(__name__)

# ── Safety constants ───────────────────────────────────────────────────────────
_SANDBOX_TIMEOUT   = 10.0        # seconds
_MAX_OUTPUT_BYTES  = 65_536      # 64 KB output cap
_DANGEROUS_MODULES = frozenset([
    "subprocess", "os.system", "socket", "shutil", "ctypes",
    "importlib", "__import__", "eval", "exec", "compile",
])
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


import ast


def _check_dangerous(code: str) -> Optional[str]:
    """AST-level analysis to detect obfuscated dynamic imports, dangerous reflection, and system calls."""
    hits = set()
    for m in _DANGEROUS_MODULES:
        if m in code:
            hits.add(m)
    try:
        parsed = ast.parse(code)
        for node in ast.walk(parsed):
            # Detect dynamic imports & dangerous calls like getattr/eval/exec
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in ("eval", "exec", "__import__", "getattr", "compile", "globals", "locals"):
                        hits.add(f"reflection:{node.func.id}")
            elif isinstance(node, ast.Attribute):
                if node.attr in ("__subclasses__", "__bases__", "__mro__", "__globals__", "__builtins__"):
                    hits.add(f"dunder:{node.attr}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if any(d in alias.name for d in ("os", "subprocess", "sys", "shutil", "socket", "ctypes", "pty")):
                        hits.add(f"import:{alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module and any(d in node.module for d in ("os", "subprocess", "sys", "shutil", "socket", "ctypes", "pty")):
                    hits.add(f"import:{node.module}")
    except Exception:
        pass

    if hits:
        return (
            f"⚠️ Security notice: potentially unsafe operations or identifiers detected: {', '.join(sorted(hits))}. "
            f"Execution is monitored and output is controlled.\n\n"
        )
    return None


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
#  Python sandbox
# ─────────────────────────────────────────────────────────────────────────────

async def python_sandbox(code: str) -> str:
    """
    Execute arbitrary Python code in a subprocess with:
      • 10-second hard timeout.
      • 64 KB text output cap + 512 KB plot output cap.
      • Automatic subprocess kill on timeout or overflow.
      • Security notice for dangerous identifiers and AST structures.
      • ANSI escape-code stripping.
      • Matplotlib plot capture with output overflow cap.
    """
    warning = _check_dangerous(code)

    fd, temp_path = tempfile.mkstemp(suffix=".py", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            # Inject output-size guard + matplotlib plot capture header
            header = (
                "import sys as _sys\n"
                "_orig_write = _sys.stdout.write\n"
                "_bytes_written = 0\n"
                "_plot_bytes_written = 0\n"
                "def _guarded_write(s):\n"
                "    global _bytes_written, _plot_bytes_written\n"
                "    if '[PLOT_BASE64:' in s or s.startswith('[PLOT_BASE64:'):\n"
                "        _plot_bytes_written += len(s.encode('utf-8', errors='replace'))\n"
                "        if _plot_bytes_written > 524288:\n"
                "            _sys.stdout = _sys.__stdout__\n"
                "            raise RuntimeError('Plot output size limit exceeded (512 KB cap).')\n"
                "        return _orig_write(s)\n"
                "    _bytes_written += len(s.encode('utf-8', errors='replace'))\n"
                f"    if _bytes_written > {_MAX_OUTPUT_BYTES}:\n"
                "        _sys.stdout = _sys.__stdout__\n"
                "        raise RuntimeError('Output size limit exceeded (64 KB).')\n"
                "    return _orig_write(s)\n"
                "_sys.stdout.write = _guarded_write\n\n"
                "# Matplotlib plot-capture shim: intercepts plt.show() and prints base64\n"
                "try:\n"
                "    import matplotlib\n"
                "    matplotlib.use('Agg')  # headless non-interactive backend\n"
                "    import matplotlib.pyplot as _plt\n"
                "    import io as _io, base64 as _b64\n"
                "    _orig_show = _plt.show\n"
                "    def _capture_show(*args, **kwargs):\n"
                "        buf = _io.BytesIO()\n"
                "        _plt.savefig(buf, format='png', dpi=80, bbox_inches='tight')\n"
                "        buf.seek(0)\n"
                "        encoded = _b64.b64encode(buf.read()).decode('utf-8')\n"
                "        _orig_write(f'[PLOT_BASE64:{encoded}]\\n')\n"
                "        _plt.close('all')\n"
                "    _plt.show = _capture_show\n"
                "except ImportError:\n"
                "    pass  # matplotlib not installed, skip shim\n\n"
            )
            f.write(header + code)

        python_exe = sys.executable or "python"
        proc = await asyncio.create_subprocess_exec(
            python_exe,
            temp_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=_SANDBOX_TIMEOUT
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            return (
                f"{warning or ''}"
                f"⏱  Execution Timeout: code ran longer than {_SANDBOX_TIMEOUT}s and was killed."
            )

        stdout_str = _strip_ansi(stdout_bytes.decode("utf-8", errors="replace").strip())
        stderr_str = _strip_ansi(stderr_bytes.decode("utf-8", errors="replace").strip())

        # Cap stdout and stderr cleanly to _MAX_OUTPUT_BYTES
        if len(stdout_str.encode("utf-8")) > _MAX_OUTPUT_BYTES:
            stdout_str = stdout_str.encode("utf-8")[:_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace") + "\n… [Truncated: stdout exceeded 64 KB cap]"

        if len(stderr_str.encode("utf-8")) > _MAX_OUTPUT_BYTES:
            stderr_str = stderr_str.encode("utf-8")[:_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace") + "\n… [Truncated: stderr exceeded 64 KB cap]"

        prefix = warning or ""
        if proc.returncode == 0:
            return prefix + (stdout_str or "[Execution completed with no output]")
        return (
            prefix
            + f"Runtime Error (exit {proc.returncode}):\n"
            + (f"STDOUT:\n{stdout_str}\n" if stdout_str else "")
            + (f"STDERR:\n{stderr_str}" if stderr_str else "")
        ).strip()

    except Exception as e:
        logger.error(f"Python sandbox exception: {e}")
        return f"Sandbox execution failed: {e}"
    finally:
        if 'proc' in locals() and proc is not None:
            try:
                if proc.returncode is None:
                    proc.kill()
                    await proc.wait()
            except Exception:
                pass
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

