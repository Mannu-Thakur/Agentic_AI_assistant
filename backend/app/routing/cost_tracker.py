"""
app/routing/cost_tracker.py — Per-request LLM inference cost tracking.

Tracks:
  - Input and output token counts per request
  - Estimated USD cost using configurable model pricing
  - Cost by model, by provider, by intent
  - Running totals for the analytics dashboard

Pricing data is taken from model_profiles.py and can be overridden
by setting PRICING_OVERRIDE_JSON in .env.

IMPORTANT: These are estimates, not exact billing amounts.
Actual costs may differ based on provider billing details.
"""
from __future__ import annotations

import json
import logging
import threading
from collections import defaultdict
from typing import Any, Dict, List, Optional

from app.routing.model_profiles import MODEL_PROFILES, get_profile

logger = logging.getLogger("app.routing.cost_tracker")


class CostTracker:
    """Thread-safe in-memory cost tracker with aggregate statistics."""

    def __init__(self):
        self._lock = threading.Lock()
        self._total_requests = 0
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_cost_usd = 0.0
        self._cost_by_model: Dict[str, float] = defaultdict(float)
        self._cost_by_provider: Dict[str, float] = defaultdict(float)
        self._cost_by_tier: Dict[str, float] = defaultdict(float)
        self._cost_by_intent: Dict[str, float] = defaultdict(float)
        self._slm_requests = 0
        self._llm_medium_requests = 0
        self._llm_strong_requests = 0
        self._recent_records: List[Dict[str, Any]] = []  # last 100 records

    def record_request(
        self,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        intent: str = "UNKNOWN",
        request_id: str = "",
    ) -> float:
        """
        Record a request and return the estimated cost in USD.
        """
        profile = get_profile(model_id)
        if profile:
            cost = profile.estimate_cost(input_tokens, output_tokens)
            provider = profile.provider
            tier = profile.tier
        else:
            # Unknown model — use zero cost (we don't want to fake numbers)
            cost = 0.0
            provider = "unknown"
            tier = "unknown"
            logger.debug(f"[CostTracker] No pricing profile for model: {model_id}")

        with self._lock:
            self._total_requests += 1
            self._total_input_tokens += input_tokens
            self._total_output_tokens += output_tokens
            self._total_cost_usd += cost
            self._cost_by_model[model_id] += cost
            self._cost_by_provider[provider] += cost
            self._cost_by_tier[tier] += cost
            self._cost_by_intent[intent] += cost

            if tier == "slm":
                self._slm_requests += 1
            elif tier == "llm-medium":
                self._llm_medium_requests += 1
            elif tier == "llm-strong":
                self._llm_strong_requests += 1

            self._recent_records.append({
                "model": model_id,
                "provider": provider,
                "tier": tier,
                "intent": intent,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": round(cost, 6),
                "request_id": request_id,
            })
            # Keep only last 100 records in memory
            if len(self._recent_records) > 100:
                self._recent_records = self._recent_records[-100:]

        return cost

    def record(
        self,
        model: str = "",
        tier: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: float = 0.0,
        intent: str = "UNKNOWN",
        request_id: str = "",
    ) -> float:
        """
        Convenience alias for record_request used by agent nodes.

        Args:
            model: Model identifier
            tier: Model tier (slm, llm-medium, llm-strong)
            input_tokens: Number of prompt/input tokens
            output_tokens: Number of completion/output tokens
            latency_ms: Wall-clock latency in milliseconds
            intent: Classified query intent
            request_id: Unique request identifier

        Returns:
            Estimated request cost in USD.
        """
        return self.record_request(
            model_id=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            intent=intent,
            request_id=request_id,
        )

    def get_summary(self) -> Dict[str, Any]:
        """Return aggregated cost statistics for the analytics dashboard."""
        with self._lock:
            total_tier_requests = max(1, self._slm_requests + self._llm_medium_requests + self._llm_strong_requests)
            return {
                "total_requests": self._total_requests,
                "total_input_tokens": self._total_input_tokens,
                "total_output_tokens": self._total_output_tokens,
                "total_cost_usd": round(self._total_cost_usd, 6),
                "avg_cost_per_request_usd": round(
                    self._total_cost_usd / max(1, self._total_requests), 6
                ),
                "cost_by_model": dict(self._cost_by_model),
                "cost_by_provider": dict(self._cost_by_provider),
                "cost_by_tier": dict(self._cost_by_tier),
                "cost_by_intent": dict(self._cost_by_intent),
                "routing_distribution": {
                    "slm": self._slm_requests,
                    "slm_pct": round(100 * self._slm_requests / total_tier_requests, 1),
                    "llm_medium": self._llm_medium_requests,
                    "llm_medium_pct": round(100 * self._llm_medium_requests / total_tier_requests, 1),
                    "llm_strong": self._llm_strong_requests,
                    "llm_strong_pct": round(100 * self._llm_strong_requests / total_tier_requests, 1),
                },
            }

    def get_recent_records(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            return list(reversed(self._recent_records[-limit:]))


# Global singleton
cost_tracker = CostTracker()
