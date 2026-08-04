"""
app/providers/circuit_breaker.py — Per-provider async circuit breaker.

States
──────
CLOSED    Normal operation; all requests pass through.
OPEN      Provider quarantined; requests raise ProviderCircuitOpenError
          immediately so the caller's fallback chain can move to the
          next healthy provider without an expensive network round-trip.
HALF_OPEN After cooldown_seconds the breaker allows one trial request.
          Success → CLOSED (recovered).
          Failure → OPEN   (cooldown restarted).

Thread / coroutine safety
──────────────────────────
All state mutations are protected by asyncio.Lock so this is safe
for concurrent async requests within a single process.

Integration with nodes.py
──────────────────────────
nodes.py's generate_response_node() fallback loop catches ALL exceptions
and advances to the next (provider, model, key) attempt.  When the
circuit is OPEN, the provider method raises ProviderCircuitOpenError
(a plain Exception subclass) which nodes.py catches automatically —
no changes to nodes.py are required.
"""

import asyncio
import time
import logging
from enum import Enum
from typing import Optional

logger = logging.getLogger("app.providers.circuit_breaker")


class CircuitState(str, Enum):
    CLOSED    = "closed"
    OPEN      = "open"
    HALF_OPEN = "half_open"


class ProviderCircuitOpenError(Exception):
    """Raised when a request is fast-failed because the circuit is OPEN."""


class CircuitBreaker:
    """
    Async circuit breaker for a single named provider.

    Parameters
    ----------
    provider_name      : Human-readable name used in log messages.
    failure_threshold  : Consecutive failures before opening (default 5).
    cooldown_seconds   : Quarantine duration before moving to HALF_OPEN (default 60 s).
    half_open_trials   : Number of trial requests allowed in HALF_OPEN (default 1).
    """

    def __init__(
        self,
        provider_name: str,
        failure_threshold: int = 5,
        cooldown_seconds: float = 60.0,
        half_open_trials: int = 1,
    ) -> None:
        self.provider_name     = provider_name
        self.failure_threshold = failure_threshold
        self.cooldown_seconds  = cooldown_seconds
        self.half_open_trials  = half_open_trials

        self._state: CircuitState              = CircuitState.CLOSED
        self._failure_count: int               = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_in_flight: int         = 0
        self._lock                             = asyncio.Lock()

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def state(self) -> CircuitState:
        return self._state

    async def allow_request(self) -> bool:
        """
        Return True if the request should be allowed through.
        Return False (never raises) so callers can decide to skip or raise.

        Automatically advances OPEN → HALF_OPEN when cooldown elapses.
        """
        async with self._lock:
            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                elapsed = (
                    time.monotonic() - self._last_failure_time
                    if self._last_failure_time is not None
                    else float("inf")
                )
                if elapsed >= self.cooldown_seconds:
                    self._transition(CircuitState.HALF_OPEN, "cooldown_elapsed")
                    self._half_open_in_flight = 0
                    return True
                return False

            # HALF_OPEN — allow up to half_open_trials concurrent trial requests
            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_in_flight < self.half_open_trials:
                    self._half_open_in_flight += 1
                    return True
                return False

        return True  # unreachable, satisfies mypy

    async def record_success(self) -> None:
        """Call after a successful provider response."""
        async with self._lock:
            prev = self._state
            if self._state != CircuitState.CLOSED:
                self._transition(CircuitState.CLOSED, f"recovery_from_{self._state}")
            self._failure_count       = 0
            self._half_open_in_flight = 0
            if prev != CircuitState.CLOSED:
                logger.info(
                    f"[CircuitBreaker] {self.provider_name}: "
                    f"{prev} → CLOSED (provider recovered)"
                )

    async def record_failure(self, error_type: str = "unknown", no_trip: bool = False) -> None:
        """
        Call after a provider error.

        Parameters
        ----------
        error_type : str
            Human-readable label for the failure (e.g. "rate_limit", "timeout").
        no_trip : bool
            When True the failure is recorded for logging/metrics but does NOT
            count toward the failure_threshold counter and cannot open the circuit.
            Use this for transient, caller-side errors that do not indicate a
            broken provider (e.g. HTTP 429 rate-limit, HTTP 400/404 invalid model).
        """
        async with self._lock:
            self._last_failure_time = time.monotonic()

            if no_trip:
                # Log so the caller can see the event, but do not touch _failure_count
                # and never open/keep-open the circuit for these error types.
                logger.debug(
                    f"[CircuitBreaker] {self.provider_name}: "
                    f"non-tripping failure recorded (error: {error_type}) — "
                    f"circuit state unchanged ({self._state})"
                )
                return

            self._failure_count += 1

            if self._state == CircuitState.HALF_OPEN:
                self._transition(CircuitState.OPEN, f"trial_failed:{error_type}")
                self._half_open_in_flight = 0
                logger.warning(
                    f"[CircuitBreaker] {self.provider_name}: "
                    f"HALF_OPEN → OPEN (trial request failed: {error_type}). "
                    f"Cooldown restarted for {self.cooldown_seconds}s."
                )

            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    self._transition(CircuitState.OPEN, f"threshold_reached:{error_type}")
                    logger.warning(
                        f"[CircuitBreaker] {self.provider_name}: "
                        f"CLOSED → OPEN after {self._failure_count} failures "
                        f"(latest: {error_type}). "
                        f"Provider quarantined for {self.cooldown_seconds}s."
                    )
                else:
                    logger.debug(
                        f"[CircuitBreaker] {self.provider_name}: "
                        f"failure #{self._failure_count}/{self.failure_threshold} "
                        f"(error: {error_type})"
                    )

    def get_status(self) -> dict:
        """Return a snapshot of the circuit's current state for diagnostics."""
        return {
            "provider":         self.provider_name,
            "state":            self._state.value,
            "failure_count":    self._failure_count,
            "failure_threshold": self.failure_threshold,
            "cooldown_seconds": self.cooldown_seconds,
            "last_failure_ago": (
                round(time.monotonic() - self._last_failure_time, 1)
                if self._last_failure_time is not None else None
            ),
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _transition(self, new_state: CircuitState, reason: str) -> None:
        """Mutate state and emit a structured log (must be called inside the lock)."""
        import json
        old = self._state
        self._state = new_state
        logger.info(json.dumps({
            "event":      "circuit_state_change",
            "provider":   self.provider_name,
            "old_state":  old.value,
            "new_state":  new_state.value,
            "reason":     reason,
            "failures":   self._failure_count,
        }))


# ── Module-level breaker instances (one per provider) ─────────────────────────
# These singletons are imported by each provider module.  All requests to the
# same provider share the same circuit state across the process lifetime.

gemini_breaker     = CircuitBreaker("gemini",     failure_threshold=5, cooldown_seconds=30)
groq_breaker       = CircuitBreaker("groq",       failure_threshold=5, cooldown_seconds=30)
openrouter_breaker = CircuitBreaker("openrouter", failure_threshold=5, cooldown_seconds=30)
openai_breaker     = CircuitBreaker("openai",     failure_threshold=5, cooldown_seconds=30)
