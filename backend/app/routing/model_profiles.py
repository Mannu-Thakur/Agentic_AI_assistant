"""
app/routing/model_profiles.py — Model profile registry for intelligent routing.

Defines SLM, LLM-MEDIUM, and LLM-STRONG tiers with real capability metadata.
Model pricing is configurable so cost tracking reflects actual provider rates.

IMPORTANT: This router is DETERMINISTIC based on complexity rules.
It is NOT an ML model. Future ML routing can be slotted in via the
MLModelRouter subclass once sufficient query-quality training data is available.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class ModelProfile:
    """Metadata for a single LLM/SLM model profile."""
    model_id: str
    provider: str
    tier: str                    # "slm" | "llm-medium" | "llm-strong"
    display_name: str
    context_window: int          # tokens
    max_output_tokens: int
    supports_vision: bool
    supports_tools: bool
    supports_streaming: bool
    cost_input_per_1m: float     # USD per 1M input tokens
    cost_output_per_1m: float    # USD per 1M output tokens
    latency_tier: str            # "fast" | "medium" | "slow"
    capability_score: float      # 0.0-1.0 relative reasoning capability
    recommended_for: List[str]   # intent types this model handles well

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Estimate USD cost for a given token usage."""
        return (
            (input_tokens / 1_000_000) * self.cost_input_per_1m +
            (output_tokens / 1_000_000) * self.cost_output_per_1m
        )


# ── Model Profile Registry ────────────────────────────────────────────────────
# Prices as of 2024 (approximate). Update via PRICING_OVERRIDES in config.

MODEL_PROFILES: Dict[str, ModelProfile] = {
    # ── Tier 1: SLM (fast, cheap, simple tasks) ───────────────────────────────
    "llama-3.1-8b-instant": ModelProfile(
        model_id="llama-3.1-8b-instant",
        provider="groq",
        tier="slm",
        display_name="Llama 3.1 8B (Groq)",
        context_window=128_000,
        max_output_tokens=8_192,
        supports_vision=False,
        supports_tools=True,
        supports_streaming=True,
        cost_input_per_1m=0.05,
        cost_output_per_1m=0.08,
        latency_tier="fast",
        capability_score=0.55,
        recommended_for=["NORMAL_CHAT", "MEMORY_WRITE", "MATH", "SIMPLE_QA"],
    ),
    "gemini-2.0-flash-lite": ModelProfile(
        model_id="gemini-2.0-flash-lite",
        provider="gemini",
        tier="slm",
        display_name="Gemini 2.0 Flash Lite",
        context_window=1_000_000,
        max_output_tokens=8_192,
        supports_vision=True,
        supports_tools=True,
        supports_streaming=True,
        cost_input_per_1m=0.075,
        cost_output_per_1m=0.30,
        latency_tier="fast",
        capability_score=0.58,
        recommended_for=["NORMAL_CHAT", "VISION", "SIMPLE_QA"],
    ),

    # ── Tier 2: LLM-MEDIUM (balanced, document QA, moderate reasoning) ─────────
    "llama-3.3-70b-versatile": ModelProfile(
        model_id="llama-3.3-70b-versatile",
        provider="groq",
        tier="llm-medium",
        display_name="Llama 3.3 70B (Groq)",
        context_window=128_000,
        max_output_tokens=32_768,
        supports_vision=False,
        supports_tools=True,
        supports_streaming=True,
        cost_input_per_1m=0.59,
        cost_output_per_1m=0.79,
        latency_tier="medium",
        capability_score=0.78,
        recommended_for=["DOCUMENT_QA", "WEB_SEARCH", "CODE_EXECUTION", "NEWS"],
    ),
    "gemini-2.0-flash": ModelProfile(
        model_id="gemini-2.0-flash",
        provider="gemini",
        tier="llm-medium",
        display_name="Gemini 2.0 Flash",
        context_window=1_000_000,
        max_output_tokens=8_192,
        supports_vision=True,
        supports_tools=True,
        supports_streaming=True,
        cost_input_per_1m=0.075,
        cost_output_per_1m=0.30,
        latency_tier="medium",
        capability_score=0.80,
        recommended_for=["DOCUMENT_QA", "VISION", "WEB_SEARCH"],
    ),

    # ── Tier 3: LLM-STRONG (complex analysis, multi-step reasoning, GraphRAG) ──
    "deepseek-r1-distill-llama-70b": ModelProfile(
        model_id="deepseek-r1-distill-llama-70b",
        provider="groq",
        tier="llm-strong",
        display_name="DeepSeek R1 Distill 70B (Groq)",
        context_window=128_000,
        max_output_tokens=32_768,
        supports_vision=False,
        supports_tools=True,
        supports_streaming=True,
        cost_input_per_1m=0.75,
        cost_output_per_1m=0.99,
        latency_tier="slow",
        capability_score=0.92,
        recommended_for=["COMPLEX", "MCP_TOOL", "FINANCE", "ANALYSIS"],
    ),
    "gemini-1.5-pro": ModelProfile(
        model_id="gemini-1.5-pro",
        provider="gemini",
        tier="llm-strong",
        display_name="Gemini 1.5 Pro",
        context_window=2_000_000,
        max_output_tokens=8_192,
        supports_vision=True,
        supports_tools=True,
        supports_streaming=True,
        cost_input_per_1m=1.25,
        cost_output_per_1m=5.00,
        latency_tier="slow",
        capability_score=0.90,
        recommended_for=["COMPLEX", "VISION", "LONG_DOCUMENT"],
    ),
}


def get_profile(model_id: str) -> Optional[ModelProfile]:
    """Get model profile by model ID. Returns None if not found."""
    return MODEL_PROFILES.get(model_id)


def get_profiles_by_tier(tier: str) -> List[ModelProfile]:
    """Get all profiles for a given tier."""
    return [p for p in MODEL_PROFILES.values() if p.tier == tier]


def get_all_profiles() -> Dict[str, Any]:
    """Return all profiles as dicts for API serialization."""
    return {
        model_id: {
            "model_id": p.model_id,
            "provider": p.provider,
            "tier": p.tier,
            "display_name": p.display_name,
            "capability_score": p.capability_score,
            "cost_input_per_1m": p.cost_input_per_1m,
            "cost_output_per_1m": p.cost_output_per_1m,
            "latency_tier": p.latency_tier,
            "supports_vision": p.supports_vision,
            "supports_tools": p.supports_tools,
        }
        for model_id, p in MODEL_PROFILES.items()
    }
