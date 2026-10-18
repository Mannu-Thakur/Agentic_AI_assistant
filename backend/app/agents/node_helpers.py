"""
app/agents/node_helpers.py — Shared LLM utilities for all sub-agents

Uses the same provider instances already initialised in nodes.py
to avoid re-instantiating and to reuse existing connection pooling.
Safe lazy import prevents circular import at module load time.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("agents.helpers")


def _default_model() -> str:
    from app.core.config import settings
    return settings.GEMINI_MODEL


def _get_provider_and_key(model: str, api_keys: Dict[str, str]):
    """
    Resolve provider + API key using the same logic as nodes.get_provider().
    Lazy import prevents circular dependency at startup.
    """
    from app.agent.nodes import get_provider  # safe: lazy import

    provider = get_provider(model)

    m = model.lower()
    # Pick the right env-var key name
    if "gemini" in m or "google" in m:
        env_key = os.getenv("GOOGLE_API_KEY", "")
        user_key = api_keys.get("google") or api_keys.get("gemini") or env_key
    elif "gpt" in m or "o1-" in m or "o3" in m or "o4" in m:
        env_key = os.getenv("OPENAI_API_KEY", "")
        user_key = api_keys.get("openai") or env_key
    elif "claude" in m:
        env_key = os.getenv("ANTHROPIC_API_KEY", "")
        user_key = api_keys.get("anthropic") or api_keys.get("openrouter") or env_key
    elif "openrouter/" in m:
        env_key = os.getenv("OPENROUTER_API_KEY", "")
        user_key = api_keys.get("openrouter") or env_key
    elif any(x in m for x in ("llama", "mixtral", "groq", "gemma", "qwen")):
        env_key = os.getenv("GROQ_API_KEY", "")
        user_key = api_keys.get("groq") or env_key
    else:
        env_key = os.getenv("GOOGLE_API_KEY", "")
        user_key = (
            api_keys.get("google")
            or api_keys.get("gemini")
            or env_key
        )

    return provider, user_key or ""


async def call_llm_simple(
    prompt: str,
    model: Optional[str] = None,
    api_keys: Optional[Dict[str, str]] = None,
    system: str = "You are a helpful AI assistant.",
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> str:
    """Call any supported LLM provider with a prompt, return text."""
    from langchain_core.messages import HumanMessage, SystemMessage

    model = model or _default_model()
    keys = api_keys or {}
    provider, api_key = _get_provider_and_key(model, keys)

    messages = [
        SystemMessage(content=system),
        HumanMessage(content=prompt),
    ]

    resp = await provider.generate(
        messages=messages,
        model=model,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        tools=[],
    )

    if hasattr(resp, "content"):
        content = resp.content
    elif isinstance(resp, dict):
        content = resp.get("content", str(resp))
    else:
        content = str(resp)

    # Handle list content blocks (Anthropic format)
    if isinstance(content, list):
        content = "".join(
            p.get("text", "") if isinstance(p, dict) else str(p)
            for p in content
        )

    return content.strip()


async def call_llm_json(
    prompt: str,
    model: Optional[str] = None,
    api_keys: Optional[Dict[str, str]] = None,
    system: str = "Respond ONLY with valid JSON. No explanation, no markdown fences.",
    temperature: float = 0.0,
) -> Dict[str, Any]:
    """Call LLM and return parsed JSON. Returns {} on failure."""
    raw = await call_llm_simple(
        prompt=prompt,
        model=model,
        api_keys=api_keys,
        system=system,
        temperature=temperature,
    )
    # Strip markdown code fences if present
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.warning(f"[call_llm_json] JSON parse failed: {exc} | raw={raw[:300]!r}")
        # Try to extract JSON object from surrounding text
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
        return {}
