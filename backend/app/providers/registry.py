"""
app/providers/registry.py — Centralized Provider Registry.

Responsibilities
────────────────
1. Provider metadata      — supported model IDs, capabilities, priority order,
                            deprecated model aliases.
2. Startup validation     — lightweight API ping per configured provider with
                            clear diagnostic logging (READY / KEY_MISSING /
                            KEY_INVALID / UNREACHABLE). Never blocks startup.
3. Model availability     — marks specific model IDs as unavailable at runtime
                            when HTTP 400/404 is received, preventing duplicate
                            failures for the same bad model ID.
4. Deprecated model remap — maps obsolete model names to current equivalents
                            so providers never see invalid IDs.
5. Provider availability  — single is_available(name) check used by providers
                            before making API calls.

Scope constraints
─────────────────
• nodes.py is NOT modified. Its own model_aliases dict and fallback chain
  continue to work exactly as before.
• This registry is additive — providers consult it, but it does not replace
  any existing routing or fallback logic.
"""

import asyncio
import logging
import os
import time
from typing import Dict, List, Optional, Set

import httpx

from app.core.config import settings

logger = logging.getLogger("app.providers.registry")

# ── Deprecated model aliases ──────────────────────────────────────────────────
# Maps known-bad / deprecated model IDs to their supported replacement.
# Providers call remap_model() before constructing the API request URL.
DEPRECATED_MODELS: Dict[str, str] = {
    # ── Gemini — retired / restricted models ─────────────────────────────────
    # gemini-2.5-flash was retired for non-allowlisted accounts (HTTP 404).
    # gemini-2.0-flash is the current stable replacement.
    "gemini-2.5-flash":                    "gemini-2.0-flash",
    "gemini-2.5-pro":                      "gemini-2.0-flash",
    "gemini-2.5-flash-preview":            "gemini-2.0-flash",
    "gemini-1.5-flash":                    "gemini-2.0-flash",
    "gemini-1.5-pro":                      "gemini-2.0-flash",
    "gemini-1.0-pro":                      "gemini-2.0-flash",
    "gemini-3.5-flash":                    "gemini-2.0-flash",
    "gemini-pro":                          "gemini-2.0-flash",
    # ── Groq — deprecated model IDs ──────────────────────────────────────────
    "llama-4-scout-17b-16e-instruct":      "llama-3.3-70b-versatile",  # deprecated July 2026
    "meta-llama/llama-4-scout-17b-16e-instruct": "llama-3.3-70b-versatile",
    "llama2-70b-4096":                     "llama-3.3-70b-versatile",
    "mixtral-8x7b-32768":                  "llama-3.3-70b-versatile",
    # ── OpenRouter — retired Gemini aliases ───────────────────────────────────
    "openrouter/google/gemini-flash-1.5":  "openrouter/google/gemini-2.0-flash",
    "openrouter/google/gemini-pro-1.5":    "openrouter/google/gemini-2.0-flash",
    "openrouter/google/gemini-3.5-flash":  "openrouter/google/gemini-2.0-flash",
    "openrouter/google/gemini-2.5-flash":  "openrouter/google/gemini-2.0-flash",
    "openrouter/google/gemini-2.5-pro":    "openrouter/google/gemini-2.0-flash",
    "google/gemini-flash-1.5":             "google/gemini-2.0-flash",
    "google/gemini-pro-1.5":               "google/gemini-2.0-flash",
    "google/gemini-2.5-flash":             "google/gemini-2.0-flash",
    "google/gemini-2.5-pro":               "google/gemini-2.0-flash",
}

# ── Known-good model sets per provider ────────────────────────────────────────
# These are static fallback lists used when the live API is not reachable at
# startup.  The live API response is authoritative when available.
KNOWN_MODELS: Dict[str, List[str]] = {
    "gemini": [
        # gemini-2.0-flash is the current stable model (gemini-2.5-flash retired for some accounts)
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-2.5-flash",   # kept for accounts that still have access
        "gemini-2.5-pro",
    ],
    "groq": [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "llama-3.1-70b-versatile",
        "gemma2-9b-it",
        "llama-3.2-11b-vision-preview",
        "llama-3.2-90b-vision-preview",
        "deepseek-r1-distill-llama-70b",
    ],
    "openrouter": [],   # dynamic — accepts any valid model ID via routing
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4.1",
        "gpt-4.1-mini",
        "gpt-4-turbo",
        "o1",
        "o1-mini",
        "o3",
        "o4-mini",
    ],
}

# Provider priority (lower number = higher priority).
# Override via PROVIDER_PRIORITY_ORDER env var: "gemini,groq,openrouter,openai"
_DEFAULT_PRIORITY = ["gemini", "groq", "openrouter", "openai"]


def _get_priority_order() -> List[str]:
    env_val = os.environ.get("PROVIDER_PRIORITY_ORDER", "")
    if env_val.strip():
        return [p.strip() for p in env_val.split(",") if p.strip()]
    return _DEFAULT_PRIORITY


# ── Timeout for startup validation pings ──────────────────────────────────────
_STARTUP_PING_TIMEOUT = 8.0


class ProviderRegistry:
    """
    Centralized provider registry.

    Instantiate once at module level (provider_registry singleton below).
    All methods are safe to call from async contexts.
    """

    def __init__(self) -> None:
        self._priority_order: List[str] = _get_priority_order()
        # Runtime model unavailability tracking: provider → set of bad model IDs
        self._unavailable_models: Dict[str, Set[str]] = {p: set() for p in KNOWN_MODELS}
        self._lock = asyncio.Lock()
        # Startup validation results (populated by startup_validate)
        self._startup_status: Dict[str, str] = {}

    # ── Startup validation ────────────────────────────────────────────────────

    async def startup_validate(self) -> None:
        """
        Validate each configured provider at application startup.

        Makes lightweight API calls (model-list endpoints) to confirm keys
        are valid.  Logs a clear diagnostic table.  Never raises — a
        misconfigured provider logs a warning and the app continues to start
        with the remaining healthy providers.
        """
        logger.info("=" * 60)
        logger.info("[ProviderRegistry] Starting provider validation …")
        logger.info("=" * 60)

        checks = [
            ("gemini",      settings.GEMINI_API_KEY,      self._ping_gemini),
            ("groq",        settings.GROQ_API_KEY,        self._ping_groq),
            ("openrouter",  settings.OPENROUTER_API_KEY,  self._ping_openrouter),
            ("openai",      settings.OPENAI_API_KEY,      self._ping_openai),
        ]

        results: Dict[str, dict] = {}

        async def _check(name: str, key: Optional[str], ping_fn) -> None:
            if not key or str(key).startswith("mock_"):
                results[name] = {"status": "KEY_MISSING", "detail": "API key not configured"}
                return
            t0 = time.perf_counter()
            try:
                models = await asyncio.wait_for(ping_fn(key), timeout=_STARTUP_PING_TIMEOUT)
                latency_ms = round((time.perf_counter() - t0) * 1000, 1)
                results[name] = {
                    "status":     "READY",
                    "latency_ms": latency_ms,
                    "models":     len(models),
                    "detail":     f"{len(models)} models available",
                }
                # Also record in provider_metrics
                try:
                    from app.providers.provider_metrics import provider_metrics
                    provider_metrics.record_health_check(name, "healthy", latency_ms)
                except Exception:
                    pass
            except asyncio.TimeoutError:
                results[name] = {"status": "UNREACHABLE", "detail": "Validation timed out"}
            except Exception as exc:
                detail = str(exc)
                status = "KEY_INVALID" if any(
                    kw in detail.lower() for kw in ("invalid", "unauthorized", "forbidden", "401", "403")
                ) else "UNREACHABLE"
                results[name] = {"status": status, "detail": detail[:200]}

        await asyncio.gather(*[_check(n, k, fn) for n, k, fn in checks])

        # Log diagnostic table
        logger.info("[ProviderRegistry] Validation Results:")
        all_ready = True
        for name in self._priority_order:
            r = results.get(name, {"status": "KEY_MISSING", "detail": "Not checked"})
            status = r["status"]
            detail = r.get("detail", "")
            latency = r.get("latency_ms")
            lat_str = f" ({latency}ms)" if latency else ""
            icon    = "✅" if status == "READY" else ("⚠️" if status == "KEY_MISSING" else "❌")
            logger.info(f"  {icon} {name:<12} {status:<14}{lat_str}  {detail}")
            self._startup_status[name] = status
            if status not in ("READY", "KEY_MISSING"):
                all_ready = False

        if all_ready:
            logger.info("[ProviderRegistry] All configured providers are READY.")
        else:
            logger.warning(
                "[ProviderRegistry] One or more providers failed validation. "
                "The application will continue using available providers."
            )
        logger.info("=" * 60)

    # ── Model remapping ───────────────────────────────────────────────────────

    @staticmethod
    def remap_model(model: str) -> str:
        """
        Translate deprecated/invalid model IDs to their current equivalents.
        Returns the model unchanged if it is not in the deprecated list.
        """
        remapped = DEPRECATED_MODELS.get(model, model)
        if remapped != model:
            logger.info(
                f"[ProviderRegistry] Deprecated model remapped: "
                f"'{model}' → '{remapped}'"
            )
        return remapped

    # ── Model availability ────────────────────────────────────────────────────

    def mark_model_unavailable(self, provider: str, model_id: str) -> None:
        """
        Mark a model ID as unavailable for a provider (e.g. after HTTP 400/404).
        Subsequent calls to is_model_available() will return False for this pair.
        """
        self._unavailable_models.setdefault(provider, set()).add(model_id)
        logger.warning(
            f"[ProviderRegistry] Model '{model_id}' marked UNAVAILABLE "
            f"for provider '{provider}' (HTTP 400/404 received)."
        )

    def is_model_available(self, provider: str, model_id: str) -> bool:
        """Return False if this model was previously marked unavailable."""
        return model_id not in self._unavailable_models.get(provider, set())

    # ── Provider availability ─────────────────────────────────────────────────

    def is_available(self, provider: str) -> bool:
        """
        Returns True if the provider is usable — it has a configured key
        and its startup status is not KEY_INVALID.
        (Circuit breaker state is checked by each provider method directly.)
        """
        status = self._startup_status.get(provider, "UNKNOWN")
        return status not in ("KEY_INVALID",)

    def get_startup_status(self) -> dict:
        """Return the startup validation results dict."""
        return dict(self._startup_status)

    # ── Lightweight ping helpers ──────────────────────────────────────────────

    @staticmethod
    async def _ping_gemini(api_key: str) -> List[str]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}&pageSize=5"
        async with httpx.AsyncClient(timeout=_STARTUP_PING_TIMEOUT) as client:
            r = await client.get(url)
        if r.status_code == 200:
            data = r.json()
            return [
                m.get("name", "").replace("models/", "")
                for m in data.get("models", [])
                if "generateContent" in m.get("supportedGenerationMethods", [])
            ]
        raise Exception(f"Gemini ping HTTP {r.status_code}: {r.text[:200]}")

    @staticmethod
    async def _ping_groq(api_key: str) -> List[str]:
        url = "https://api.groq.com/openai/v1/models"
        async with httpx.AsyncClient(timeout=_STARTUP_PING_TIMEOUT) as client:
            r = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
        if r.status_code == 200:
            return [m["id"] for m in r.json().get("data", [])]
        raise Exception(f"Groq ping HTTP {r.status_code}: {r.text[:200]}")

    @staticmethod
    async def _ping_openrouter(api_key: str) -> List[str]:
        url = "https://openrouter.ai/api/v1/auth/key"
        async with httpx.AsyncClient(timeout=_STARTUP_PING_TIMEOUT) as client:
            r = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
        if r.status_code == 200:
            return ["openrouter_ok"]  # OpenRouter is a router, no fixed model list
        raise Exception(f"OpenRouter ping HTTP {r.status_code}: {r.text[:200]}")

    @staticmethod
    async def _ping_openai(api_key: str) -> List[str]:
        if not api_key:
            raise Exception("No OpenAI API key configured")
        url = "https://api.openai.com/v1/models"
        async with httpx.AsyncClient(timeout=_STARTUP_PING_TIMEOUT) as client:
            r = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
        if r.status_code == 200:
            return [m["id"] for m in r.json().get("data", [])]
        raise Exception(f"OpenAI ping HTTP {r.status_code}: {r.text[:200]}")


# ── Module-level singleton ─────────────────────────────────────────────────────
provider_registry = ProviderRegistry()
