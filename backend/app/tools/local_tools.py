import os
import sys
import httpx
import asyncio
import logging
import tempfile
from typing import Dict, Any, List
from app.core.config import settings

logger = logging.getLogger(__name__)

async def tavily_search(query: str) -> str:
    """
    Search the web for a query using Tavily API.
    """
    api_key = settings.TAVILY_API_KEY
    if not api_key or api_key.startswith("mock_"):
        logger.info(f"Using mock Tavily search for query: {query}")
        return f"[Mock Web Search Result for '{query}']: Paris weather is currently sunny and 22°C. Flagship AI is performing optimally."

    url = "https://api.tavily.com/search"
    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": "basic",
        "include_answer": True
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])
                formatted_results = []
                for idx, r in enumerate(results[:3]):
                    formatted_results.append(f"Source [{idx+1}]: {r.get('title')}\nURL: {r.get('url')}\nSnippet: {r.get('content')}\n")
                
                answer = data.get("answer")
                prefix = f"Summary Answer: {answer}\n\n" if answer else ""
                return prefix + "\n".join(formatted_results)
            else:
                logger.error(f"Tavily search API failed with code {response.status_code}: {response.text}")
                return f"Web search failed (code {response.status_code})."
    except Exception as e:
        logger.error(f"Error calling Tavily API: {str(e)}")
        return f"Error executing web search: {str(e)}"


async def python_sandbox(code: str) -> str:
    """
    Runs Python code in a subprocess using the current python executable.
    Implements a 10 second timeout and returns stdout/stderr.
    """
    # Create a temporary file to write the user's code to
    fd, temp_path = tempfile.mkstemp(suffix=".py", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(code)

        # Spawns a subprocess using the same python binary as the current interpreter
        python_exe = sys.executable or "python"
        
        proc = await asyncio.create_subprocess_exec(
            python_exe,
            temp_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)
            stdout_str = stdout.decode("utf-8", errors="ignore").strip()
            stderr_str = stderr.decode("utf-8", errors="ignore").strip()

            if proc.returncode == 0:
                return stdout_str or "[Execution completed successfully with no output]"
            else:
                return f"Runtime Error (exit code {proc.returncode}):\nSTDOUT:\n{stdout_str}\nSTDERR:\n{stderr_str}"
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return "Execution Timeout Error: Code took longer than 10.0 seconds to execute."
    except Exception as e:
        logger.error(f"Python sandbox exception: {str(e)}")
        return f"Sandbox execution failed: {str(e)}"
    finally:
        # Clean up temporary file
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as e:
                logger.error(f"Failed to clean up temp file {temp_path}: {str(e)}")
