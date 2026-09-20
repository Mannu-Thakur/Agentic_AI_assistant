"""
app/routing/model_router.py — Intelligent LLM/SLM routing engine.

Routing strategy (deterministic, rule-based):
  1. If user explicitly selected a model → respect their choice
  2. If intent is VISION → force vision-capable model
  3. Otherwise → analyze complexity and select from available providers

The router is designed so an ML-based complexity scorer can be dropped in
later by replacing the ComplexityAnalyzer call without changing the router API.

All routing decisions are logged for future ML training data collection.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.routing.complexity_analyzer import analyze_complexity, ComplexityScore
from app.routing.model_profiles import (
    MODEL_PROFILES, ModelProfile, get_profiles_by_tier, get_profile
)

logger = logging.getLogger("app.routing.model_router")

# Routing version — increment when routing logic changes
ROUTING_VERSION = "1.0.0"


@dataclass
class RoutingDecision:
    """Result of the routing engine."""
    selected_model: str
    selected_provider: str
    selected_tier: str
    complexity_score: ComplexityScore
    reason: str
    user_override: bool          # True if user explicitly chose the model
    routing_version: str
    estimated_cost_usd: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "selected_model": self.selected_model,
            "selected_provider": self.selected_provider,
            "selected_tier": self.selected_tier,
            "complexity_score": self.complexity_score.complexity_score,
            "recommended_tier": self.complexity_score.recommended_tier,
            "reason": self.reason,
            "user_override": self.user_override,
            "routing_version": self.routing_version,
            "signals": self.complexity_score.signals,
            "needs_graph": self.complexity_score.needs_graph,
            "needs_vision": self.complexity_score.needs_vision,
        }


_PROVIDER_PREFERENCE_ORDER = ["groq", "gemini", "openrouter", "openai"]


def _is_provider_configured(provider: str) -> bool:
    """Check if a provider has an API key configured."""
    key_map = {
        "groq": settings.GROQ_API_KEY,
        "gemini": settings.GEMINI_API_KEY,
        "openai": settings.OPENAI_API_KEY,
        "openrouter": settings.OPENROUTER_API_KEY,
    }
    key = key_map.get(provider)
    return bool(key and not key.startswith("mock_"))


def _select_from_tier(tier: str, needs_vision: bool = False) -> Optional[ModelProfile]:
    """
    Select the best available model profile for a given tier.
    Respects provider availability and vision requirements.
    """
    candidates = [
        p for p in get_profiles_by_tier(tier)
        if _is_provider_configured(p.provider)
        and (not needs_vision or p.supports_vision)
    ]
    if not candidates:
        return None
    # Sort by provider preference order
    pref_map = {p: i for i, p in enumerate(_PROVIDER_PREFERENCE_ORDER)}
    candidates.sort(key=lambda p: pref_map.get(p.provider, 99))
    return candidates[0]


def route_query(
    query: str,
    user_selected_model: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
) -> RoutingDecision:
    """
    Route a query to the most appropriate model.

    Args:
        query: User's question
        user_selected_model: If set, use this model (user override)
        context: Optional context dict passed to complexity analyzer

    Returns:
        RoutingDecision with selected model and routing explanation
    """
    # ── User override ──────────────────────────────────────────────────────────
    if user_selected_model:
        profile = get_profile(user_selected_model)
        if profile and _is_provider_configured(profile.provider):
            complexity = analyze_complexity(query, context)
            logger.info(
                f"[Router v{ROUTING_VERSION}] User override: {user_selected_model} | "
                f"complexity={complexity.complexity_score:.2f}"
            )
            return RoutingDecision(
                selected_model=user_selected_model,
                selected_provider=profile.provider,
                selected_tier=profile.tier,
                complexity_score=complexity,
                reason=f"User-selected model: {user_selected_model}",
                user_override=True,
                routing_version=ROUTING_VERSION,
            )
        # If user selected model has no profile, fall through to auto-routing
        # (handles custom OpenRouter models etc.)

    # ── Auto-routing based on complexity ──────────────────────────────────────
    complexity = analyze_complexity(query, context)
    tier = complexity.recommended_tier
    needs_vision = complexity.needs_vision

    selected = _select_from_tier(tier, needs_vision)

    # Tier fallback: if recommended tier has no available model, try adjacent tiers
    if selected is None:
        fallback_order = {
            "slm": ["llm-medium", "llm-strong"],
            "llm-medium": ["slm", "llm-strong"],
            "llm-strong": ["llm-medium", "slm"],
        }
        for fallback_tier in fallback_order.get(tier, []):
            selected = _select_from_tier(fallback_tier, needs_vision)
            if selected:
                tier = fallback_tier
                break

    if selected is None:
        # Absolute fallback — return whatever user_selected_model was, or a hardcoded default
        fallback_model = user_selected_model or "llama-3.3-70b-versatile"
        logger.warning(f"[Router] No available profile for tier={tier}. Using fallback: {fallback_model}")
        return RoutingDecision(
            selected_model=fallback_model,
            selected_provider="groq",
            selected_tier="llm-medium",
            complexity_score=complexity,
            reason="Fallback: no provider available for recommended tier",
            user_override=False,
            routing_version=ROUTING_VERSION,
        )

    logger.info(
        f"[Router v{ROUTING_VERSION}] Selected: {selected.model_id} ({selected.tier}) | "
        f"complexity={complexity.complexity_score:.2f} | "
        f"signals={complexity.signals}"
    )

    return RoutingDecision(
        selected_model=selected.model_id,
        selected_provider=selected.provider,
        selected_tier=selected.tier,
        complexity_score=complexity,
        reason=complexity.reasoning,
        user_override=False,
        routing_version=ROUTING_VERSION,
    )
