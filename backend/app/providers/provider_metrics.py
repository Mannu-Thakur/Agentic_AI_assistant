"""
app/providers/provider_metrics.py — Structured provider metrics collector.

Records every provider interaction in a thread-safe in-memory store.
Metrics are exposed via get_summary() which can be consumed by the
/health/providers endpoint or any monitoring integration.

Tracked dimensions
──────────────────
• Provider selection  — which provider was chosen and why
• Call latency        — per-provider p50 / p95 latency (ms)
• Retry counts        — how many retries occurred per provider
• Fallback events     — from-provider / to-provider / reason
• Failure types       — rate_limit (429), model_unavailable (400/404),
                        server_error (5xx), timeout, network
• Token usage         — cumulative input + output tokens per provider
• Health checks       — last result per provider from background probe
• Circuit breaker     — history of state transitions (last 20 events)

Thread safety
─────────────
All writes are protected by threading.Lock.  Latency lists are bounded
to 1 000 entries per provider (ring-buffer eviction) to prevent unbounded
memory growth.
"""

import threading
import time
import logging
from collections import defaultdict
from typing import Dict, List, Optional

logger = logging.getLogger("app.providers.provider_metrics")


class ProviderMetricsCollector:
    """Thread-safe, in-process provider metrics store."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

        # Call counters
        self._calls:              Dict[str, int]        = defaultdict(int)
        self._successes:          Dict[str, int]        = defaultdict(int)
        self._failures:           Dict[str, int]        = defaultdict(int)
        self._retries:            Dict[str, int]        = defaultdict(int)
        self._fallback_used:      Dict[str, int]        = defaultdict(int)

        # Failure sub-types
        self._rate_limit_hits:    Dict[str, int]        = defaultdict(int)
        self._model_invalid_hits: Dict[str, int]        = defaultdict(int)
        self._server_error_hits:  Dict[str, int]        = defaultdict(int)
        self._timeout_hits:       Dict[str, int]        = defaultdict(int)
        self._network_error_hits: Dict[str, int]        = defaultdict(int)

        # Latency tracking (bounded ring buffer per provider)
        self._latencies:          Dict[str, List[float]] = defaultdict(list)
        _MAX_LATENCY_SAMPLES = 1_000
        self._max_latency_samples = _MAX_LATENCY_SAMPLES

        # Token usage
        self._tokens_in:          Dict[str, int]        = defaultdict(int)
        self._tokens_out:         Dict[str, int]        = defaultdict(int)

        # Event logs (bounded)
        self._fallback_log:       List[dict]            = []   # last 50
        self._circuit_event_log:  List[dict]            = []   # last 20
        self._health_results:     Dict[str, dict]       = {}

    # ── Recording API ─────────────────────────────────────────────────────────

    def record_call_start(self, provider: str, model: str) -> None:
        """Call when a provider attempt begins."""
        with self._lock:
            self._calls[provider] += 1
        logger.debug(f"[ProviderMetrics] call_start provider={provider} model={model}")

    def record_call_success(
        self,
        provider: str,
        model: str,
        latency_ms: float,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> None:
        """Call after a fully successful provider response."""
        with self._lock:
            self._successes[provider] += 1
            buf = self._latencies[provider]
            buf.append(latency_ms)
            if len(buf) > self._max_latency_samples:
                # Evict oldest half to amortise the cost of eviction
                self._latencies[provider] = buf[-(self._max_latency_samples // 2):]
            self._tokens_in[provider]  += tokens_in
            self._tokens_out[provider] += tokens_out
        logger.info(
            f"[ProviderMetrics] call_success provider={provider} model={model} "
            f"latency_ms={latency_ms:.1f} tokens_in={tokens_in} tokens_out={tokens_out}"
        )

    def record_call_failure(
        self,
        provider: str,
        model: str,
        error_type: str,
        status_code: Optional[int] = None,
    ) -> None:
        """
        Call after an unrecoverable provider error.

        error_type should be one of:
          "rate_limit", "model_invalid", "server_error", "timeout", "network", "circuit_open"
        """
        with self._lock:
            self._failures[provider] += 1
            if error_type == "rate_limit" or status_code == 429:
                self._rate_limit_hits[provider] += 1
            elif error_type == "model_invalid" or status_code in (400, 404):
                self._model_invalid_hits[provider] += 1
            elif error_type == "server_error" or (status_code and status_code >= 500):
                self._server_error_hits[provider] += 1
            elif error_type == "timeout":
                self._timeout_hits[provider] += 1
            elif error_type == "network":
                self._network_error_hits[provider] += 1
        logger.warning(
            f"[ProviderMetrics] call_failure provider={provider} model={model} "
            f"error_type={error_type} status_code={status_code}"
        )

    def record_retry(
        self,
        provider: str,
        model: str,
        attempt: int,
        reason: str,
    ) -> None:
        """Call each time a provider retries a transient error internally."""
        with self._lock:
            self._retries[provider] += 1
        logger.debug(
            f"[ProviderMetrics] retry provider={provider} model={model} "
            f"attempt={attempt} reason={reason}"
        )

    def record_fallback(
        self,
        from_provider: str,
        to_provider: str,
        to_model: str,
        reason: str,
    ) -> None:
        """Call when the outer fallback chain switches providers."""
        with self._lock:
            self._fallback_used[to_provider] += 1
            entry = {
                "from_provider": from_provider,
                "to_provider":   to_provider,
                "to_model":      to_model,
                "reason":        reason,
                "timestamp":     time.time(),
            }
            self._fallback_log.append(entry)
            if len(self._fallback_log) > 50:
                self._fallback_log = self._fallback_log[-50:]
        logger.info(
            f"[ProviderMetrics] fallback from={from_provider} "
            f"to={to_provider}/{to_model} reason={reason}"
        )

    def record_health_check(
        self,
        provider: str,
        status: str,
        latency_ms: Optional[float] = None,
    ) -> None:
        """Call from the background health-check worker after each probe."""
        with self._lock:
            self._health_results[provider] = {
                "status":     status,
                "latency_ms": latency_ms,
                "timestamp":  time.time(),
            }

    def record_circuit_state_change(
        self,
        provider: str,
        old_state: str,
        new_state: str,
        reason: str,
    ) -> None:
        """Call whenever a circuit breaker transitions state."""
        with self._lock:
            self._circuit_event_log.append({
                "provider":  provider,
                "old_state": old_state,
                "new_state": new_state,
                "reason":    reason,
                "timestamp": time.time(),
            })
            if len(self._circuit_event_log) > 20:
                self._circuit_event_log = self._circuit_event_log[-20:]

    # ── Query API ─────────────────────────────────────────────────────────────

    def get_summary(self) -> dict:
        """
        Return a complete metrics summary suitable for JSON serialisation.
        Used by /health/providers and any monitoring integration.
        """
        with self._lock:
            all_providers = set(
                list(self._calls)   + list(self._successes) +
                list(self._failures)+ list(self._latencies)
            )
            providers_out: Dict[str, dict] = {}
            for p in sorted(all_providers):
                lats = self._latencies.get(p, [])
                sorted_lats = sorted(lats)
                n = len(sorted_lats)
                providers_out[p] = {
                    "total_calls":          self._calls.get(p, 0),
                    "successes":            self._successes.get(p, 0),
                    "failures":             self._failures.get(p, 0),
                    "retries":              self._retries.get(p, 0),
                    "fallback_times_used":  self._fallback_used.get(p, 0),
                    "rate_limit_hits":      self._rate_limit_hits.get(p, 0),
                    "model_invalid_hits":   self._model_invalid_hits.get(p, 0),
                    "server_error_hits":    self._server_error_hits.get(p, 0),
                    "timeout_hits":         self._timeout_hits.get(p, 0),
                    "network_error_hits":   self._network_error_hits.get(p, 0),
                    "avg_latency_ms":       round(sum(sorted_lats) / n, 1) if n else None,
                    "p95_latency_ms":       round(sorted_lats[int(n * 0.95)], 1) if n >= 20 else None,
                    "total_tokens_in":      self._tokens_in.get(p, 0),
                    "total_tokens_out":     self._tokens_out.get(p, 0),
                    "last_health_check":    self._health_results.get(p),
                }
            return {
                "providers":              providers_out,
                "recent_fallbacks":       list(self._fallback_log[-10:]),
                "recent_circuit_events":  list(self._circuit_event_log[-10:]),
            }


# ── Module-level singleton ─────────────────────────────────────────────────────
provider_metrics = ProviderMetricsCollector()
