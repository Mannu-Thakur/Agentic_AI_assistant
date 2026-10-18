"""Stable model capability profiles used by routing and cost telemetry.

Model availability belongs to the provider registry and deployment settings.
This module deliberately contains only models offered by the application UI or
the configured fallback chain. Token prices default to ``0`` because provider
prices and account discounts change; operators can set PRICING_OVERRIDE_JSON to
obtain cost estimates without silently reporting stale billing data.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, replace
from typing import Any, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ModelProfile:
    """Capability and optional pricing metadata for one executable model ID."""

    model_id: str
    provider: str
    tier: str
    display_name: str
    context_window: int
    max_output_tokens: int
    supports_vision: bool
    supports_tools: bool
    supports_streaming: bool
    cost_input_per_1m: float = 0.0
    cost_output_per_1m: float = 0.0
    latency_tier: str = "medium"
    capability_score: float = 0.75
    recommended_for: List[str] | None = None

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Return an estimate only when deployment pricing has been configured."""
        return (
            (max(input_tokens, 0) / 1_000_000) * self.cost_input_per_1m
            + (max(output_tokens, 0) / 1_000_000) * self.cost_output_per_1m
        )

    @property
    def cost_per_1k_tokens(self) -> float:
        """Legacy compatibility for callers that estimate input-only spend."""
        return self.cost_input_per_1m / 1_000.0


def _profile(
    model_id: str,
    provider: str,
    tier: str,
    display_name: str,
    *,
    vision: bool = False,
    context_window: int = 128_000,
    max_output_tokens: int = 8_192,
    latency: str = "medium",
    score: float = 0.75,
    recommended_for: Optional[List[str]] = None,
) -> ModelProfile:
    return ModelProfile(
        model_id=model_id,
        provider=provider,
        tier=tier,
        display_name=display_name,
        context_window=context_window,
        max_output_tokens=max_output_tokens,
        supports_vision=vision,
        supports_tools=True,
        supports_streaming=True,
        latency_tier=latency,
        capability_score=score,
        recommended_for=recommended_for or ["NORMAL_CHAT"],
    )


# Keep this set synchronized with app.providers.registry.KNOWN_MODELS and the
# selectable frontend models. Do not insert historical aliases here: aliases
# are normalized by the provider registry before a provider call is made.
MODEL_PROFILES: Dict[str, ModelProfile] = {
    "gemini-3.5-flash-lite": _profile(
        "gemini-3.5-flash-lite", "gemini", "slm", "Gemini 3.5 Flash Lite",
        vision=True, context_window=1_000_000, latency="fast", score=0.62,
        recommended_for=["NORMAL_CHAT", "VISION", "SIMPLE_QA", "MEMORY_WRITE"],
    ),
    "gemini-3.6-flash": _profile(
        "gemini-3.6-flash", "gemini", "llm-medium", "Gemini 3.6 Flash",
        vision=True, context_window=1_000_000, latency="fast", score=0.80,
        recommended_for=["DOCUMENT_QA", "VISION", "WEB_SEARCH", "AGENT"],
    ),
    "gemini-3.8-flash": _profile(
        "gemini-3.8-flash", "gemini", "llm-strong", "Gemini 3.8 Flash",
        vision=True, context_window=1_000_000, latency="medium", score=0.90,
        recommended_for=["COMPLEX", "DOCUMENT_QA", "VISION", "REASONING"],
    ),
    "openai/gpt-oss-20b": _profile(
        "openai/gpt-oss-20b", "groq", "llm-medium", "GPT-OSS 20B (Groq)",
        latency="fast", score=0.78,
        recommended_for=["NORMAL_CHAT", "SIMPLE_QA", "DOCUMENT_QA", "WEB_SEARCH", "TOOLS", "CODE"],
    ),
    "openai/gpt-oss-120b": _profile(
        "openai/gpt-oss-120b", "groq", "llm-strong", "GPT-OSS 120B (Groq)",
        latency="slow", score=0.90,
        recommended_for=["COMPLEX", "CODE", "REASONING", "ANALYSIS"],
    ),
    "gpt-4o-mini": _profile(
        "gpt-4o-mini", "openai", "slm", "GPT-4o Mini", vision=True,
        max_output_tokens=16_384, latency="fast", score=0.65,
        recommended_for=["NORMAL_CHAT", "SIMPLE_QA", "TOOLS", "VISION"],
    ),
    "gpt-4o": _profile(
        "gpt-4o", "openai", "llm-strong", "GPT-4o", vision=True,
        max_output_tokens=16_384, latency="medium", score=0.90,
        recommended_for=["COMPLEX", "VISION", "REASONING", "TOOLS"],
    ),
    "openrouter/auto": _profile(
        "openrouter/auto", "openrouter", "llm-medium", "OpenRouter Auto",
        vision=True, latency="medium", score=0.78,
        recommended_for=["NORMAL_CHAT", "WEB_SEARCH", "TOOLS", "REASONING"],
    ),
}


def _apply_pricing_overrides() -> None:
    """Load only well-formed operator prices; otherwise expose $0 estimates."""
    raw = (getattr(settings, "PRICING_OVERRIDE_JSON", "") or "").strip()
    if not raw:
        return
    try:
        overrides = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        logger.warning("Ignoring invalid PRICING_OVERRIDE_JSON")
        return
    if not isinstance(overrides, dict):
        logger.warning("Ignoring PRICING_OVERRIDE_JSON because it is not an object")
        return
    for model_id, values in overrides.items():
        profile = MODEL_PROFILES.get(str(model_id).lower())
        if profile is None or not isinstance(values, dict):
            continue
        try:
            input_price = float(values.get("input_per_1m", profile.cost_input_per_1m))
            output_price = float(values.get("output_per_1m", profile.cost_output_per_1m))
            if input_price < 0 or output_price < 0:
                raise ValueError("negative pricing")
        except (TypeError, ValueError):
            logger.warning("Ignoring invalid pricing override for model=%s", model_id)
            continue
        profile.cost_input_per_1m = input_price
        profile.cost_output_per_1m = output_price


_apply_pricing_overrides()


def resolve_model_tier(model_id: str) -> str:
    """Return a safe tier for a known or custom model identifier."""
    if not model_id:
        return "llm-medium"
    normalized = model_id.lower().strip()
    existing = MODEL_PROFILES.get(normalized)
    if existing:
        return existing.tier
    if any(token in normalized for token in ("120b", "70b", "pro", "opus", "sonnet", "o1", "o3", "reasoning")):
        return "llm-strong"
    if any(token in normalized for token in ("lite", "mini", "8b", "small", "flash-lite")):
        return "slm"
    return "llm-medium"


def _provider_for_model(model_id: str) -> str:
    normalized = model_id.lower().strip()
    if normalized.startswith("openrouter/"):
        return "openrouter"
    if "gemini" in normalized or normalized.startswith("google/"):
        return "gemini"
    if normalized in {"openai/gpt-oss-20b", "openai/gpt-oss-120b"} or "llama" in normalized or normalized.startswith("groq/"):
        return "groq"
    if normalized.startswith(("gpt", "o1", "o3", "o4")):
        return "openai"
    return "openrouter"


def get_profile(model_id: str) -> Optional[ModelProfile]:
    """Return a profile for a known model, including OpenRouter-prefixed forms."""
    if not model_id:
        return None
    normalized = model_id.lower().strip()
    profile = MODEL_PROFILES.get(normalized)
    if profile:
        return profile

    if normalized.startswith("openrouter/"):
        underlying = normalized.removeprefix("openrouter/")
        profile = MODEL_PROFILES.get(underlying)
        if profile:
            return replace(profile, model_id=model_id, provider="openrouter", display_name=model_id)

    tier = resolve_model_tier(normalized)
    return ModelProfile(
        model_id=model_id,
        provider=_provider_for_model(normalized),
        tier=tier,
        display_name=model_id,
        context_window=128_000,
        max_output_tokens=8_192,
        supports_vision=any(token in normalized for token in ("gemini", "gpt-4", "vision", "llama-4", "-vl")),
        supports_tools=True,
        supports_streaming=True,
        latency_tier="fast" if tier == "slm" else ("slow" if tier == "llm-strong" else "medium"),
        capability_score=0.60 if tier == "slm" else (0.90 if tier == "llm-strong" else 0.78),
        recommended_for=["NORMAL_CHAT"],
    )


def get_profile_for_model(model_id: str) -> Optional[ModelProfile]:
    """Compatibility alias retained for telemetry and older API callers."""
    return get_profile(model_id)


def get_profiles_by_tier(tier: str) -> List[ModelProfile]:
    return [profile for profile in MODEL_PROFILES.values() if profile.tier == tier]


def get_all_profiles() -> Dict[str, Any]:
    return {
        model_id: {
            "model_id": profile.model_id,
            "provider": profile.provider,
            "tier": profile.tier,
            "display_name": profile.display_name,
            "capability_score": profile.capability_score,
            "cost_input_per_1m": profile.cost_input_per_1m,
            "cost_output_per_1m": profile.cost_output_per_1m,
            "latency_tier": profile.latency_tier,
            "supports_vision": profile.supports_vision,
            "supports_tools": profile.supports_tools,
        }
        for model_id, profile in MODEL_PROFILES.items()
    }
