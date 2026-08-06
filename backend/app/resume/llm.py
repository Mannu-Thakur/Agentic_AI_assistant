"""
app/resume/llm.py — LLM interface for the Resume Builder.

Wraps the existing ProviderRegistry. Reuses BYOK keys.
Does NOT create any new provider connections.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("app.resume.llm")

# Default model for resume operations — lightweight and fast
_DEFAULT_MODEL = "gemini-2.0-flash"
_FALLBACK_MODELS = ["llama-3.3-70b-versatile", "gpt-4o-mini"]


def _extract_json(text: str) -> Dict[str, Any]:
    """
    Robustly extract JSON from LLM output.
    Handles markdown code blocks, leading text, trailing garbage.
    """
    # Strip markdown code fences
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find first { ... } or [ ... ] block
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start = text.find(start_char)
        if start == -1:
            continue
        # Find matching close
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == start_char:
                depth += 1
            elif ch == end_char:
                depth -= 1
                if depth == 0:
                    candidate = text[start:i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break

    raise ValueError(f"Could not extract valid JSON from LLM response: {text[:200]}")


async def call_llm_json(
    system: str,
    user: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: int = 4096,
    temperature: float = 0.3,
) -> Dict[str, Any]:
    """
    Call the best available LLM provider and return parsed JSON.

    Uses the existing ProviderRegistry — no new API connections.
    Tries providers in priority order until one succeeds.
    """
    from app.providers.gemini import GeminiProvider
    from app.providers.groq import GroqProvider
    from app.providers.openai_provider import OpenAIProvider
    from app.core.config import settings

    messages = [
        {"role": "user", "content": user},
    ]

    target_model = model or _DEFAULT_MODEL

    # Build candidate (provider, model, key) triples in priority order
    candidates = []

    # Handle explicit user BYOK key if provided
    if api_key:
        k_upper = api_key.upper()
        if api_key.startswith("gsk_") or "GROQ" in k_upper:
            candidates.append((GroqProvider(), "llama-3.3-70b-versatile", api_key))
        elif api_key.startswith("sk-or-") or "OPENROUTER" in k_upper:
            from app.providers.openrouter import OpenRouterProvider
            candidates.append((OpenRouterProvider(), "google/gemini-2.0-flash-001", api_key))
        elif api_key.startswith("sk-proj") or (api_key.startswith("sk-") and not api_key.startswith("sk-or")):
            candidates.append((OpenAIProvider(), "gpt-4o-mini", api_key))
        elif api_key.startswith("AIzaSy") or "GEMINI" in k_upper:
            candidates.append((GeminiProvider(), target_model if target_model.startswith("gemini") else "gemini-2.0-flash", api_key))
        else:
            # Generic fallback: try Gemini first with user key
            candidates.append((GeminiProvider(), target_model if target_model.startswith("gemini") else "gemini-2.0-flash", api_key))

    # Environment key fallbacks
    if settings.GEMINI_API_KEY and (not api_key or "AIzaSy" not in api_key):
        gemini_model = target_model if target_model.startswith("gemini") else "gemini-2.0-flash"
        candidates.append((GeminiProvider(), gemini_model, settings.GEMINI_API_KEY))

    if settings.GROQ_API_KEY and (not api_key or not api_key.startswith("gsk_")):
        candidates.append((GroqProvider(), "llama-3.3-70b-versatile", settings.GROQ_API_KEY))

    if getattr(settings, "OPENROUTER_API_KEY", None):
        from app.providers.openrouter import OpenRouterProvider
        candidates.append((OpenRouterProvider(), "google/gemini-2.0-flash-001", settings.OPENROUTER_API_KEY))

    if settings.OPENAI_API_KEY and (not api_key or not api_key.startswith("sk-proj")):
        candidates.append((OpenAIProvider(), "gpt-4o-mini", settings.OPENAI_API_KEY))

    if not candidates:
        raise RuntimeError(
            "No LLM provider configured. Please add GEMINI_API_KEY or GROQ_API_KEY to your .env"
        )

    last_error = None
    for provider, pmodel, pkey in candidates:
        try:
            logger.info(f"[ResumeLLM] Calling {pmodel} for JSON generation")
            result = await provider.generate(
                messages=[{"role": "system", "content": system}, *messages],
                model=pmodel,
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=pkey,
            )
            raw_text = result.get("text", "")
            parsed = _extract_json(raw_text)
            logger.info(f"[ResumeLLM] Successfully parsed JSON from {pmodel}")
            return parsed
        except Exception as e:
            logger.warning(f"[ResumeLLM] Provider {pmodel} failed: {e}")
            last_error = e
            continue

    raise RuntimeError(f"All LLM providers failed. Last error: {last_error}")


async def call_llm_text(
    system: str,
    user: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: int = 2048,
    temperature: float = 0.5,
) -> str:
    """
    Call LLM and return raw text (for explanations, not JSON).
    """
    from app.providers.gemini import GeminiProvider
    from app.core.config import settings

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    gemini_key = api_key or settings.GEMINI_API_KEY
    target_model = model or _DEFAULT_MODEL

    if gemini_key:
        try:
            provider = GeminiProvider()
            result = await provider.generate(
                messages=messages,
                model=target_model if target_model.startswith("gemini") else "gemini-2.0-flash",
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=gemini_key,
            )
            return result.get("text", "")
        except Exception as e:
            logger.warning(f"[ResumeLLM] Text call failed: {e}")

    return ""
