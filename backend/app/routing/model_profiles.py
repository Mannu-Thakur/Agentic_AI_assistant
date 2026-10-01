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
# Real-world provider rates per 1M tokens. Configurable via PRICING_OVERRIDES.

MODEL_PROFILES: Dict[str, ModelProfile] = {
    # ── Tier 1: SLM (fast, lightweight, highly cost-effective) ───────────────
    "gemini-3.5-flash-lite": ModelProfile(
        model_id="gemini-3.5-flash-lite",
        provider="gemini",
        tier="slm",
        display_name="Gemini 3.5 Flash Lite",
        context_window=1_000_000,
        max_output_tokens=8_192,
        supports_vision=True,
        supports_tools=True,
        supports_streaming=True,
        cost_input_per_1m=0.075,
        cost_output_per_1m=0.30,
        latency_tier="fast",
        capability_score=0.62,
        recommended_for=["NORMAL_CHAT", "VISION", "SIMPLE_QA", "MEMORY_WRITE"],
    ),
    "gemini-2.5-flash": ModelProfile(
        model_id="gemini-2.5-flash",
        provider="gemini",
        tier="slm",
        display_name="Gemini 2.5 Flash",
        context_window=1_000_000,
        max_output_tokens=8_192,
        supports_vision=True,
        supports_tools=True,
        supports_streaming=True,
        cost_input_per_1m=0.075,
        cost_output_per_1m=0.30,
        latency_tier="fast",
        capability_score=0.68,
        recommended_for=["NORMAL_CHAT", "VISION", "SIMPLE_QA"],
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
    "gpt-4o-mini": ModelProfile(
        model_id="gpt-4o-mini",
        provider="openai",
        tier="slm",
        display_name="GPT-4o Mini",
        context_window=128_000,
        max_output_tokens=16_384,
        supports_vision=True,
        supports_tools=True,
        supports_streaming=True,
        cost_input_per_1m=0.15,
        cost_output_per_1m=0.60,
        latency_tier="fast",
        capability_score=0.65,
        recommended_for=["NORMAL_CHAT", "SIMPLE_QA", "TOOLS"],
    ),
    "claude-3-5-haiku": ModelProfile(
        model_id="claude-3-5-haiku",
        provider="anthropic",
        tier="slm",
        display_name="Claude 3.5 Haiku",
        context_window=200_000,
        max_output_tokens=8_192,
        supports_vision=False,
        supports_tools=True,
        supports_streaming=True,
        cost_input_per_1m=0.80,
        cost_output_per_1m=4.00,
        latency_tier="fast",
        capability_score=0.72,
        recommended_for=["NORMAL_CHAT", "CODE", "ANALYSIS"],
    ),

    # ── Tier 2: LLM-MEDIUM (balanced, document QA, high precision) ───────────
    "gemini-3.5-flash": ModelProfile(
        model_id="gemini-3.5-flash",
        provider="gemini",
        tier="llm-medium",
        display_name="Gemini 3.5 Flash",
        context_window=1_000_000,
        max_output_tokens=8_192,
        supports_vision=True,
        supports_tools=True,
        supports_streaming=True,
        cost_input_per_1m=0.10,
        cost_output_per_1m=0.40,
        latency_tier="medium",
        capability_score=0.82,
        recommended_for=["DOCUMENT_QA", "VISION", "WEB_SEARCH", "AGENT"],
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
    "meta-llama/llama-4-scout-17b-16e-instruct": ModelProfile(
        model_id="meta-llama/llama-4-scout-17b-16e-instruct",
        provider="groq",
        tier="llm-medium",
        display_name="Llama 4 Scout 17B (Groq)",
        context_window=128_000,
        max_output_tokens=16_384,
        supports_vision=False,
        supports_tools=True,
        supports_streaming=True,
        cost_input_per_1m=0.30,
        cost_output_per_1m=0.50,
        latency_tier="medium",
        capability_score=0.79,
        recommended_for=["DOCUMENT_QA", "WEB_SEARCH", "TOOLS"],
    ),
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
        recommended_for=["DOCUMENT_QA", "WEB_SEARCH", "CODE_EXECUTION"],
    ),

    # ── Tier 3: LLM-STRONG (complex reasoning, synthesis, deep research) ──────
    "gemini-2.5-pro": ModelProfile(
        model_id="gemini-2.5-pro",
        provider="gemini",
        tier="llm-strong",
        display_name="Gemini 2.5 Pro",
        context_window=2_000_000,
        max_output_tokens=8_192,
        supports_vision=True,
        supports_tools=True,
        supports_streaming=True,
        cost_input_per_1m=1.25,
        cost_output_per_1m=5.00,
        latency_tier="slow",
        capability_score=0.92,
        recommended_for=["COMPLEX", "DOCUMENT_QA", "LONG_CONTEXT", "REASONING"],
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
    "gpt-4o": ModelProfile(
        model_id="gpt-4o",
        provider="openai",
        tier="llm-strong",
        display_name="GPT-4o",
        context_window=128_000,
        max_output_tokens=16_384,
        supports_vision=True,
        supports_tools=True,
        supports_streaming=True,
        cost_input_per_1m=2.50,
        cost_output_per_1m=10.00,
        latency_tier="medium",
        capability_score=0.93,
        recommended_for=["COMPLEX", "VISION", "REASONING", "TOOLS"],
    ),
    "claude-3-5-sonnet": ModelProfile(
        model_id="claude-3-5-sonnet",
        provider="anthropic",
        tier="llm-strong",
        display_name="Claude 3.5 Sonnet",
        context_window=200_000,
        max_output_tokens=8_192,
        supports_vision=True,
        supports_tools=True,
        supports_streaming=True,
        cost_input_per_1m=3.00,
        cost_output_per_1m=15.00,
        latency_tier="medium",
        capability_score=0.95,
        recommended_for=["COMPLEX", "CODE", "REASONING", "ANALYSIS"],
    ),
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
}


def resolve_model_tier(model_id: str) -> str:
    """Intelligently determine the tier ('slm', 'llm-medium', 'llm-strong') for any model."""
    if not model_id:
        return "llm-medium"
    mid = model_id.lower().strip()
    if mid in MODEL_PROFILES:
        return MODEL_PROFILES[mid].tier

    # Check common heuristics
    if any(k in mid for k in ["pro", "opus", "sonnet", "r1", "o1", "o3", "strong", "gpt-4o", "70b"]):
        return "llm-strong"
    if any(k in mid for k in ["lite", "mini", "8b", "haiku", "slm", "small", "flash-lite", "scout"]):
        return "slm"
    if "flash" in mid:
        return "slm"
    return "llm-medium"


def get_profile(model_id: str) -> Optional[ModelProfile]:
    """Get model profile by model ID with aliases and dynamic fallback."""
    if not model_id:
        return None
    mid = model_id.lower().strip()
    # Strip provider prefix if present, e.g. "google/gemini-2.5-flash" -> "gemini-2.5-flash"
    clean_id = mid.split("/")[-1] if "/" in mid and mid not in MODEL_PROFILES else mid

    if mid in MODEL_PROFILES:
        return MODEL_PROFILES[mid]
    if clean_id in MODEL_PROFILES:
        return MODEL_PROFILES[clean_id]

    # Synthesize a reliable dynamic profile so costs & tiers are never lost
    tier = resolve_model_tier(mid)
    provider = "google" if "gemini" in mid else ("openai" if "gpt" in mid or "o1" in mid else ("anthropic" if "claude" in mid else "groq"))
    if tier == "slm":
        cin, cout = 0.08, 0.30
    elif tier == "llm-strong":
        cin, cout = 1.50, 6.00
    else:
        cin, cout = 0.30, 0.60

    return ModelProfile(
        model_id=model_id,
        provider=provider,
        tier=tier,
        display_name=model_id,
        context_window=128_000,
        max_output_tokens=8_192,
        supports_vision="vision" in mid or "flash" in mid or "gpt-4" in mid,
        supports_tools=True,
        supports_streaming=True,
        cost_input_per_1m=cin,
        cost_output_per_1m=cout,
        latency_tier="fast" if tier == "slm" else ("slow" if tier == "llm-strong" else "medium"),
        capability_score=0.6 if tier == "slm" else (0.9 if tier == "llm-strong" else 0.8),
        recommended_for=["NORMAL_CHAT"],
    )


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
