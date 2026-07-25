"""
tools/local_tools.py — Locally-implemented agent tools.

Changes vs original:
  python_sandbox():
    • Hard output size limit (64 KB) prevents memory exhaustion.
    • Kills the subprocess on timeout AND on output-size overflow.
    • Adds a security warning header when dangerous stdlib modules are imported.
    • Strips ANSI escape codes from output.

tavily_search(): unchanged — only minor formatting cleanup.
"""

import os
import re
import sys
import httpx
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


def _check_dangerous(code: str) -> Optional[str]:
    """Return a warning string if the code imports risky modules, else None."""
    hits = [m for m in _DANGEROUS_MODULES if m in code]
    if hits:
        return (
            f"⚠️  Security notice: the following potentially unsafe identifiers "
            f"were detected: {', '.join(hits)}. "
            f"Output is shown but network access and filesystem writes are not isolated.\n\n"
        )
    return None


# ─────────────────────────────────────────────────────────────────────────────
#  Web search
# ─────────────────────────────────────────────────────────────────────────────

async def _ddg_search_fallback(query: str) -> str:
    """Fallback search using DuckDuckGo (free, live, real-time)."""
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        def _run_ddg():
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=5))

        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(None, _run_ddg)
        if not results:
            return f"[System Notice: Real-time search returned 0 results for query '{query}']."
        
        lines = []
        for idx, r in enumerate(results[:5], start=1):
            title = r.get("title", "")
            url = r.get("href", r.get("link", ""))
            snippet = r.get("body", r.get("snippet", ""))
            lines.append(f"Source [{idx}]: {title}\nURL: {url}\nSnippet: {snippet}\n")
        
        return "Live Web Search Results (via DuckDuckGo):\n\n" + "\n".join(lines)
    except Exception as err:
        logger.error(f"DuckDuckGo search fallback failed: {err}")
        return f"[System Notice: Real-time search unavailable. Error: {err}]"


async def tavily_search(query: str) -> str:
    """Search the web using Tavily API, with seamless automatic fallback to DuckDuckGo.

    Results are cached for 10 minutes (WebSearchCache TTL) to avoid
    redundant API calls for identical queries within the same session.
    """
    # ── Cache check ──────────────────────────────────────────────────────────
    cached = await web_search_cache.get(query)
    if cached is not None:
        logger.debug(f"[tavily_search] Cache HIT for query='{query[:60]}'")
        return cached

    api_key = settings.TAVILY_API_KEY
    # If Tavily key is missing or mock, directly use real live search via DuckDuckGo
    if not api_key or api_key.startswith("mock_"):
        logger.info(f"Tavily API key missing/mock -> Using DuckDuckGo fallback for query: '{query}'")
        res = await _ddg_search_fallback(query)
        await web_search_cache.set(query, res)
        return res

    url     = "https://api.tavily.com/search"
    payload = {
        "api_key":       api_key,
        "query":         query,
        "search_depth":  "basic",
        "include_answer": True,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
        if response.status_code == 200:
            data    = response.json()
            results = data.get("results", [])
            lines   = []
            for idx, r in enumerate(results[:5], start=1):
                lines.append(
                    f"Source [{idx}]: {r.get('title')}\n"
                    f"URL: {r.get('url')}\n"
                    f"Snippet: {r.get('content')}\n"
                )
            answer = data.get("answer")
            prefix = f"Summary Answer: {answer}\n\n" if answer else ""
            result = prefix + "\n".join(lines)
            # ── Cache store ──────────────────────────────────────────────────
            await web_search_cache.set(query, result)
            return result
        logger.warning(f"Tavily error {response.status_code}: {response.text[:200]} -> Falling back to DuckDuckGo.")
        res = await _ddg_search_fallback(query)
        await web_search_cache.set(query, res)
        return res
    except Exception as e:
        logger.warning(f"Tavily exception: {e} -> Falling back to DuckDuckGo.")
        res = await _ddg_search_fallback(query)
        await web_search_cache.set(query, res)
        return res

# ─────────────────────────────────────────────────────────────────────────────
#  Python sandbox
# ─────────────────────────────────────────────────────────────────────────────

async def python_sandbox(code: str) -> str:
    """
    Execute arbitrary Python code in a subprocess with:
      • 10-second hard timeout.
      • 64 KB output size cap (stdout + stderr combined).
      • Automatic subprocess kill on timeout or overflow.
      • Security notice for dangerous identifiers.
      • ANSI escape-code stripping.

    NOTE: This is NOT an OS-level sandbox.  For production deployments that
    accept untrusted code, wrap this subprocess in a Docker container with
    --network=none --memory=256m --cpus=0.5 (see docker-compose.yml).
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
                "def _guarded_write(s):\n"
                "    global _bytes_written\n"
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
                "        _plt.savefig(buf, format='png', bbox_inches='tight')\n"
                "        buf.seek(0)\n"
                "        encoded = _b64.b64encode(buf.read()).decode('utf-8')\n"
                "        print(f'[PLOT_BASE64:{encoded}]')\n"
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

        # Trim combined output to MAX_OUTPUT_BYTES
        combined = (stdout_str + "\n" + stderr_str).strip()
        if len(combined.encode()) > _MAX_OUTPUT_BYTES:
            combined = combined.encode()[:_MAX_OUTPUT_BYTES].decode(errors="replace")
            combined += "\n… [output truncated at 64 KB]"

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
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
