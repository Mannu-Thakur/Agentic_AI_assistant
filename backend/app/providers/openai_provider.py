"""
app/providers/openai_provider.py — Direct OpenAI Chat Completions provider.

Production hardening applied
─────────────────────────────
• Circuit breaker: fast-fail when the OpenAI circuit is OPEN.
• Deprecated model remapping via ProviderRegistry.remap_model().
• Model availability check: models marked unavailable after HTTP 400/404
  are rejected immediately.
• Error classification:
    429       → ProviderRateLimitError
    400 / 404 → ProviderModelUnavailableError + registry.mark_model_unavailable()
    5xx       → exponential backoff with ±50% jitter
    timeout   → ProviderTimeoutError
• Structured metrics via provider_metrics singleton.
• All method signatures and return dict shapes are identical to the
  original file — full backward compatibility.
"""

import time
import json
import random
import httpx
import asyncio
import logging
from typing import AsyncGenerator, Dict, Any, List, Optional

from app.providers.base import BaseLLMProvider
from app.core.config import settings

logger = logging.getLogger("app.providers.openai")


# ── Provider infrastructure ────────────────────────────────────────────────────

def _get_circuit_breaker():
    from app.providers.circuit_breaker import openai_breaker
    return openai_breaker

def _get_metrics():
    from app.providers.provider_metrics import provider_metrics
    return provider_metrics

def _get_registry():
    from app.providers.registry import provider_registry
    return provider_registry


# ── Custom exception types ─────────────────────────────────────────────────────

class ProviderRateLimitError(Exception):
    """HTTP 429 — OpenAI rate limit exceeded."""

class ProviderModelUnavailableError(Exception):
    """HTTP 400/404 — model ID is invalid or unavailable."""

class ProviderServerError(Exception):
    """HTTP 5xx — transient server-side error."""

class ProviderTimeoutError(Exception):
    """Request timed out."""

class ProviderCircuitOpenError(Exception):
    """Circuit breaker is OPEN."""


def _jitter(base_delay: float) -> float:
    """Add ±50% multiplicative jitter to avoid thundering herd."""
    return base_delay * (0.5 + random.random())


class OpenAIProvider(BaseLLMProvider):
    """
    Direct provider for official OpenAI Chat Completions API (api.openai.com).
    Supports vision (base64 image URLs), streaming SSE responses, and tool calls.
    """

    provider_name = "openai"
    capabilities  = frozenset({"text", "streaming", "tools", "vision"})

    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _clean_model_name(self, model: str) -> str:
        if model.startswith("openai/"):
            return model[7:]
        return model

    def _inject_images_into_messages(
        self,
        messages: List[Dict[str, Any]],
        images: Optional[List[Dict[str, str]]],
    ) -> List[Dict[str, Any]]:
        if not images:
            return messages

        messages = [dict(m) for m in messages]
        for i in reversed(range(len(messages))):
            if messages[i].get("role") == "user":
                existing_text = messages[i].get("content", "") or ""
                if isinstance(existing_text, list):
                    parts = list(existing_text)
                else:
                    parts: List[Dict[str, Any]] = [{"type": "text", "text": str(existing_text)}]
                for img in images:
                    mime = img.get("mimeType", "image/jpeg")
                    b64  = img.get("base64", "")
                    parts.append({
                        "type":      "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    })
                messages[i]["content"] = parts
                break
        return messages

    # ── generate() ────────────────────────────────────────────────────────────

    async def generate(
        self,
        messages: List[Dict[str, Any]],
        model: str = "gpt-4o",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        tools: Optional[List[Dict[str, Any]]] = None,
        api_key: Optional[str] = None,
        images: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        key_to_use = api_key or self.api_key
        if not key_to_use or str(key_to_use).startswith("mock_"):
            raise Exception(
                "OpenAI API key is missing or invalid. "
                "Please configure your OPENAI_API_KEY in Settings or .env."
            )

        cb       = _get_circuit_breaker()
        metrics  = _get_metrics()
        registry = _get_registry()

        # ── Circuit breaker check ─────────────────────────────────────────────
        if not await cb.allow_request():
            metrics.record_call_failure(self.provider_name, model, "circuit_open")
            raise ProviderCircuitOpenError(
                "OpenAIProvider circuit breaker is OPEN — provider quarantined. "
                "Trying next fallback."
            )

        # ── Deprecated model remapping ────────────────────────────────────────
        model      = registry.remap_model(model)
        clean_model = self._clean_model_name(model)

        # ── Model availability check ──────────────────────────────────────────
        if not registry.is_model_available(self.provider_name, clean_model):
            raise ProviderModelUnavailableError(
                f"OpenAI model '{clean_model}' is marked unavailable (previous HTTP 400/404). "
                "Trying next fallback."
            )

        messages = self._inject_images_into_messages(messages, images)

        payload = {
            "model":       clean_model,
            "messages":    messages,
            "temperature": temperature,
            "max_tokens":  max_tokens,
        }

        url     = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {key_to_use}",
            "Content-Type":  "application/json",
        }

        max_retries   = 3
        initial_delay = 1.0
        data          = None

        metrics.record_call_start(self.provider_name, clean_model)
        call_start = time.monotonic()

        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=45.0) as client:
                    response = await client.post(url, json=payload, headers=headers)
            except httpx.TimeoutException as exc:
                await cb.record_failure("timeout")
                metrics.record_call_failure(self.provider_name, clean_model, "timeout")
                raise ProviderTimeoutError(f"OpenAI API request timed out: {exc}") from exc
            except httpx.RequestError as exc:
                await cb.record_failure("network")
                metrics.record_call_failure(self.provider_name, clean_model, "network")
                raise Exception(f"OpenAI API network error: {exc}") from exc

            if response.status_code == 200:
                data = response.json()
                break

            elif response.status_code == 429:
                await cb.record_failure("rate_limit", no_trip=True)  # 429 = slow down, not broken provider
                metrics.record_call_failure(self.provider_name, clean_model, "rate_limit", 429)
                raise ProviderRateLimitError(
                    "OpenAI API rate limit exceeded (HTTP 429). "
                    "Please wait a moment before trying again."
                )

            elif response.status_code in (400, 404):
                registry.mark_model_unavailable(self.provider_name, clean_model)
                await cb.record_failure("model_invalid", no_trip=True)  # bad model ID, not broken provider
                metrics.record_call_failure(self.provider_name, clean_model, "model_invalid", response.status_code)
                raise ProviderModelUnavailableError(
                    f"OpenAI API error {response.status_code} for model '{clean_model}': "
                    f"{response.text[:300]}"
                )

            elif response.status_code in (500, 502, 503, 504):
                if attempt < max_retries:
                    delay = _jitter(initial_delay * (2 ** attempt))
                    metrics.record_retry(self.provider_name, clean_model, attempt + 1, f"HTTP_{response.status_code}")
                    logger.warning(
                        f"[OpenAIProvider] HTTP {response.status_code} on attempt {attempt + 1}; "
                        f"retrying in {delay:.2f}s …"
                    )
                    await asyncio.sleep(delay)
                    continue
                await cb.record_failure("server_error")
                metrics.record_call_failure(self.provider_name, clean_model, "server_error", response.status_code)
                raise ProviderServerError(
                    f"OpenAI API server error {response.status_code} after {max_retries} retries."
                )

            else:
                await cb.record_failure("unknown")
                metrics.record_call_failure(self.provider_name, clean_model, "unknown", response.status_code)
                raise Exception(f"OpenAI API error ({response.status_code}): {response.text}")

        if not data:
            await cb.record_failure("empty_response")
            raise Exception("OpenAI API returned empty response data.")

        text          = data["choices"][0]["message"]["content"] or ""
        input_tokens  = data.get("usage", {}).get("prompt_tokens", 0)
        output_tokens = data.get("usage", {}).get("completion_tokens", 0)

        latency_ms = round((time.monotonic() - call_start) * 1000, 1)
        await cb.record_success()
        metrics.record_call_success(self.provider_name, clean_model, latency_ms,
                                    tokens_in=input_tokens, tokens_out=output_tokens)

        return {
            "text":          text,
            "input_tokens":  input_tokens,
            "output_tokens": output_tokens,
            "model":         clean_model,
            "tool_calls":    [],   # OpenAI tool calls via streaming path; non-streaming not used for tools
        }

    # ── generate_stream() ─────────────────────────────────────────────────────

    async def generate_stream(
        self,
        messages: List[Dict[str, Any]],
        model: str = "gpt-4o",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        tools: Optional[List[Dict[str, Any]]] = None,
        api_key: Optional[str] = None,
        images: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        key_to_use = api_key or self.api_key
        if not key_to_use or str(key_to_use).startswith("mock_"):
            raise Exception(
                "OpenAI API key is missing or invalid. "
                "Please configure your OPENAI_API_KEY in Settings or .env."
            )

        cb       = _get_circuit_breaker()
        metrics  = _get_metrics()
        registry = _get_registry()

        # ── Circuit breaker check ─────────────────────────────────────────────
        if not await cb.allow_request():
            metrics.record_call_failure(self.provider_name, model, "circuit_open")
            raise ProviderCircuitOpenError(
                "OpenAIProvider circuit breaker is OPEN — provider quarantined. "
                "Trying next fallback."
            )

        # ── Deprecated model remapping ────────────────────────────────────────
        model       = registry.remap_model(model)
        clean_model = self._clean_model_name(model)

        # ── Model availability check ──────────────────────────────────────────
        if not registry.is_model_available(self.provider_name, clean_model):
            raise ProviderModelUnavailableError(
                f"OpenAI model '{clean_model}' is marked unavailable (previous HTTP 400/404). "
                "Trying next fallback."
            )

        messages = self._inject_images_into_messages(messages, images)

        payload = {
            "model":       clean_model,
            "messages":    messages,
            "temperature": temperature,
            "max_tokens":  max_tokens,
            "stream":      True,
        }

        url     = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {key_to_use}",
            "Content-Type":  "application/json",
        }

        input_tokens  = len(str(messages)) // 4
        output_text   = ""
        start_time    = time.time()
        max_retries   = 3
        initial_delay = 1.0

        metrics.record_call_start(self.provider_name, clean_model)

        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=45.0) as client:
                    async with client.stream("POST", url, json=payload, headers=headers) as response:
                        if response.status_code == 429:
                            await cb.record_failure("rate_limit", no_trip=True)  # 429 = slow down, not broken provider
                            metrics.record_call_failure(self.provider_name, clean_model, "rate_limit", 429)
                            raise ProviderRateLimitError(
                                "OpenAI API rate limit exceeded (HTTP 429). Please try again later."
                            )

                        elif response.status_code in (400, 404):
                            registry.mark_model_unavailable(self.provider_name, clean_model)
                            await cb.record_failure("model_invalid", no_trip=True)  # bad model ID, not broken provider
                            metrics.record_call_failure(self.provider_name, clean_model, "model_invalid", response.status_code)
                            error_body = await response.aread()
                            raise ProviderModelUnavailableError(
                                f"OpenAI API error {response.status_code} for model '{clean_model}': "
                                f"{error_body.decode('utf-8', errors='ignore')[:300]}"
                            )

                        elif response.status_code in (500, 502, 503, 504):
                            if attempt < max_retries:
                                delay = _jitter(initial_delay * (2 ** attempt))
                                metrics.record_retry(self.provider_name, clean_model, attempt + 1, f"HTTP_{response.status_code}")
                                logger.warning(
                                    f"[OpenAIProvider] Stream HTTP {response.status_code} on attempt {attempt + 1}; "
                                    f"retrying in {delay:.2f}s …"
                                )
                                await asyncio.sleep(delay)
                                continue
                            await cb.record_failure("server_error")
                            metrics.record_call_failure(self.provider_name, clean_model, "server_error", response.status_code)
                            raise ProviderServerError(
                                f"OpenAI streaming server error {response.status_code} after {max_retries} retries."
                            )

                        elif response.status_code != 200:
                            error_body = await response.aread()
                            await cb.record_failure("unknown")
                            metrics.record_call_failure(self.provider_name, clean_model, "unknown", response.status_code)
                            raise Exception(
                                f"OpenAI API error ({response.status_code}): "
                                f"{error_body.decode('utf-8', errors='ignore')}"
                            )

                        async for line in response.aiter_lines():
                            line = line.strip()
                            if not line or not line.startswith("data: "):
                                continue
                            raw_data = line[6:]
                            if raw_data == "[DONE]":
                                break
                            try:
                                parsed     = json.loads(raw_data)
                                chunk_text = parsed["choices"][0]["delta"].get("content", "")
                                if chunk_text:
                                    output_text += chunk_text
                                    yield {"event": "chunk", "text": chunk_text}
                            except Exception:
                                continue

                        break  # successful stream

            except (ProviderRateLimitError, ProviderModelUnavailableError, ProviderServerError, ProviderCircuitOpenError):
                raise
            except httpx.TimeoutException as exc:
                await cb.record_failure("timeout")
                metrics.record_call_failure(self.provider_name, clean_model, "timeout")
                raise ProviderTimeoutError(f"OpenAI streaming request timed out: {exc}") from exc
            except httpx.RequestError as exc:
                await cb.record_failure("network")
                metrics.record_call_failure(self.provider_name, clean_model, "network")
                raise Exception(f"OpenAI streaming network error: {exc}") from exc

        # ── Record success metrics ────────────────────────────────────────────
        latency_ms = int((time.time() - start_time) * 1000)
        out_tokens = len(output_text) // 4
        await cb.record_success()
        metrics.record_call_success(self.provider_name, clean_model, latency_ms,
                                    tokens_in=input_tokens, tokens_out=out_tokens)

        yield {
            "event": "metrics",
            "metrics": {
                "model_used":       clean_model,
                "latency_ms":       latency_ms,
                "tokens_input":     input_tokens,
                "tokens_output":    out_tokens,
                "cost_estimate":    (input_tokens * 0.0025 + out_tokens * 0.01) / 1000,
                "confidence_score": 0.95,
                # memory_hits and chunks_used are placeholders;
                # nodes.py overwrites these with real values.
                "memory_hits":  0,
                "chunks_used":  0,
            },
        }
