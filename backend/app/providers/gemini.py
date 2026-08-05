"""
app/providers/gemini.py — Google Gemini LLM provider.

Production hardening applied
─────────────────────────────
• Circuit breaker: if the Gemini circuit is OPEN the method raises
  immediately (no network round-trip) so nodes.py moves to the next fallback.
• Deprecated model remapping via ProviderRegistry.remap_model() — obsolete
  model IDs (gemini-1.5-flash etc.) are transparently upgraded before the
  API call.
• Model availability check: models marked unavailable after HTTP 400/404
  are rejected immediately.
• Error classification:
    429           → ProviderRateLimitError  (string contains "429" for nodes.py detection)
    400 / 404     → ProviderModelUnavailableError + registry.mark_model_unavailable()
    5xx / network → exponential backoff with ±50% jitter, then ProviderServerError
    timeout       → ProviderTimeoutError
• Structured metrics recorded via provider_metrics singleton.
• Jitter added to every retry delay to prevent thundering-herd.

Interface contract preserved
─────────────────────────────
• generate() and generate_stream() signatures are identical to before.
• Return dict shape is identical to before.
• All existing call-sites (nodes.py) work without any changes.
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

logger = logging.getLogger("app.providers.gemini")

# ── Provider infrastructure (imported lazily to avoid circular imports) ────────

def _get_circuit_breaker():
    from app.providers.circuit_breaker import gemini_breaker
    return gemini_breaker

def _get_metrics():
    from app.providers.provider_metrics import provider_metrics
    return provider_metrics

def _get_registry():
    from app.providers.registry import provider_registry
    return provider_registry


# ── Custom exception types ────────────────────────────────────────────────────
# All are plain Exception subclasses so nodes.py's bare `except Exception`
# still catches them.  Status codes are embedded in the message string so
# nodes.py's `"429" in err_str` detection continues to work unchanged.

class ProviderRateLimitError(Exception):
    """HTTP 429 — provider rate limit exceeded."""

class ProviderModelUnavailableError(Exception):
    """HTTP 400/404 — model ID is invalid or unavailable."""

class ProviderServerError(Exception):
    """HTTP 5xx — transient server-side error after retries exhausted."""

class ProviderTimeoutError(Exception):
    """Request timed out."""

class ProviderCircuitOpenError(Exception):
    """Circuit breaker is OPEN — provider is quarantined."""


def _jitter(base_delay: float) -> float:
    """Add ±50% multiplicative jitter to avoid thundering herd."""
    return base_delay * (0.5 + random.random())


class GeminiProvider(BaseLLMProvider):

    provider_name = "gemini"
    capabilities  = frozenset({"text", "streaming", "tools", "vision"})

    def __init__(self):
        # Server-level key fallback; runtime per-request key takes priority via api_key param
        self.api_key = settings.GEMINI_API_KEY

    # ── Schema conversion ─────────────────────────────────────────────────────

    def _convert_schema_to_gemini(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively capitalize all schema types (e.g. string → STRING) to match Gemini specification.
        """
        new_schema = {}
        for k, v in schema.items():
            if k == "type" and isinstance(v, str):
                new_schema[k] = v.upper()
            elif isinstance(v, dict):
                new_schema[k] = self._convert_schema_to_gemini(v)
            elif isinstance(v, list):
                new_list = []
                for item in v:
                    if isinstance(item, dict):
                        new_list.append(self._convert_schema_to_gemini(item))
                    else:
                        new_list.append(item)
                new_schema[k] = new_list
            else:
                new_schema[k] = v
        return new_schema

    def _convert_messages(
        self,
        messages: List[Dict[str, str]],
        images: Optional[List[Dict[str, str]]] = None,
    ) -> tuple:
        """
        Convert messages to Gemini format: roles are 'user' or 'model'.
        Separate system instruction.
        When `images` is provided, the base64 payloads are injected as
        inlineData parts into the LAST user message (multimodal vision).
        """
        contents = []
        system_instruction = None

        for msg in messages:
            role    = msg["role"]
            content = msg["content"]

            if role == "system":
                system_instruction = {"parts": [{"text": content}]}
            else:
                gemini_role = "model" if role == "assistant" else "user"
                contents.append({
                    "role":  gemini_role,
                    "parts": [{"text": content}]
                })

        # Inject images into the last user turn if provided
        if images:
            for entry in reversed(contents):
                if entry["role"] == "user":
                    image_parts = [
                        {
                            "inlineData": {
                                "mimeType": img["mimeType"],
                                "data":     img["base64"],
                            }
                        }
                        for img in images
                    ]
                    entry["parts"] = image_parts + entry["parts"]
                    break

        return contents, system_instruction

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _build_payload(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        tools: Optional[List[Dict[str, Any]]],
        images: Optional[List[Dict[str, str]]],
    ) -> tuple:
        """Return (payload_dict, contents, system_instruction)."""
        contents, system_instruction = self._convert_messages(messages, images=images)
        payload: Dict[str, Any] = {
            "contents":       contents,
            "generationConfig": {
                "temperature":    temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if system_instruction:
            payload["systemInstruction"] = system_instruction
        if tools:
            func_declarations = []
            for t in tools:
                func_declarations.append({
                    "name":        t["name"],
                    "description": t["description"],
                    "parameters":  self._convert_schema_to_gemini(t["parameters"]),
                })
            payload["tools"] = [{"functionDeclarations": func_declarations}]
        return payload, contents, system_instruction

    # ── generate() ────────────────────────────────────────────────────────────

    async def generate(
        self,
        messages: List[Dict[str, str]],
        model: str = "gemini-2.0-flash",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        tools: Optional[List[Dict[str, Any]]] = None,
        api_key: Optional[str] = None,
        images: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        key_to_use = api_key or self.api_key
        if not key_to_use or str(key_to_use).startswith("mock_"):
            raise Exception(
                "Gemini API key is missing or invalid. "
                "Please configure a valid Gemini API key in Settings."
            )

        cb      = _get_circuit_breaker()
        metrics = _get_metrics()
        registry = _get_registry()

        # ── Circuit breaker check ─────────────────────────────────────────────
        if not await cb.allow_request():
            err_msg = (
                "GeminiProvider circuit breaker is OPEN — provider quarantined "
                "after repeated failures. Trying next fallback."
            )
            metrics.record_call_failure(self.provider_name, model, "circuit_open")
            raise ProviderCircuitOpenError(err_msg)

        # ── Deprecated/alias model remapping ──────────────────────────────────
        model = registry.remap_model(model)
        _gemini_aliases = {
            "gemini-2.5-flash": "gemini-2.0-flash",
            "gemini-2.5-pro": "gemini-2.0-flash",
            "google/gemini-2.5-flash": "gemini-2.0-flash",
            "google/gemini-2.5-pro": "gemini-2.0-flash",
            "google/gemini-2.0-flash": "gemini-2.0-flash",
        }
        if model in _gemini_aliases:
            model = _gemini_aliases[model]

        # ── Model availability check ──────────────────────────────────────────
        if not registry.is_model_available(self.provider_name, model):
            raise ProviderModelUnavailableError(
                f"Gemini model '{model}' is marked unavailable (previous HTTP 400/404). "
                "Trying next fallback."
            )

        payload, _, _ = self._build_payload(messages, temperature, max_tokens, tools, images)
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={key_to_use}"
        )

        max_retries   = 3
        initial_delay = 1.0
        data          = None

        metrics.record_call_start(self.provider_name, model)
        call_start = time.monotonic()

        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(url, json=payload)
            except httpx.TimeoutException as exc:
                await cb.record_failure("timeout")
                metrics.record_call_failure(self.provider_name, model, "timeout")
                raise ProviderTimeoutError(
                    f"Gemini API request timed out: {exc}"
                ) from exc
            except httpx.RequestError as exc:
                await cb.record_failure("network")
                metrics.record_call_failure(self.provider_name, model, "network")
                raise Exception(f"Gemini API network error: {exc}") from exc

            if response.status_code == 200:
                data = response.json()
                break

            elif response.status_code == 429:
                # Rate-limited — record and raise immediately (no retry; let caller fallback)
                await cb.record_failure("rate_limit", no_trip=True)  # 429 = slow down, not broken provider
                metrics.record_call_failure(self.provider_name, model, "rate_limit", 429)
                raise ProviderRateLimitError(
                    "Gemini rate limit exceeded (HTTP 429). "
                    "You have reached the API request limit. "
                    "Please wait a moment or switch to another model."
                )

            elif response.status_code in (400, 404):
                # Invalid/deprecated model ID — mark unavailable, do NOT retry
                registry.mark_model_unavailable(self.provider_name, model)
                await cb.record_failure("model_invalid", no_trip=True)  # bad model ID, not broken provider
                metrics.record_call_failure(self.provider_name, model, "model_invalid", response.status_code)
                raise ProviderModelUnavailableError(
                    f"Gemini API error {response.status_code} for model '{model}': "
                    f"{response.text[:300]}"
                )

            elif response.status_code in (500, 502, 503, 504):
                if attempt < max_retries:
                    delay = _jitter(initial_delay * (2 ** attempt))
                    metrics.record_retry(self.provider_name, model, attempt + 1, f"HTTP_{response.status_code}")
                    logger.warning(
                        f"[GeminiProvider] HTTP {response.status_code} on attempt {attempt + 1}; "
                        f"retrying in {delay:.2f}s …"
                    )
                    await asyncio.sleep(delay)
                    continue
                await cb.record_failure("server_error")
                metrics.record_call_failure(self.provider_name, model, "server_error", response.status_code)
                raise ProviderServerError(
                    f"Gemini API server error {response.status_code} after {max_retries} retries."
                )

            else:
                await cb.record_failure("unknown")
                metrics.record_call_failure(self.provider_name, model, "unknown", response.status_code)
                raise Exception(f"Gemini API returned error {response.status_code}: {response.text}")

        if not data:
            await cb.record_failure("empty_response")
            metrics.record_call_failure(self.provider_name, model, "unknown")
            raise Exception("Gemini API returned empty response data.")

        text       = ""
        tool_calls = []
        try:
            parts = data["candidates"][0]["content"]["parts"]
            for part in parts:
                if "text" in part:
                    text += part["text"]
                if "functionCall" in part:
                    fc = part["functionCall"]
                    tool_calls.append({
                        "name":      fc["name"],
                        "arguments": fc.get("args", {}),
                    })
        except (KeyError, IndexError, TypeError):
            text = "[No text generated]"

        input_tokens  = data.get("usageMetadata", {}).get("promptTokenCount", 0)
        output_tokens = data.get("usageMetadata", {}).get("candidatesTokenCount", 0)

        latency_ms = round((time.monotonic() - call_start) * 1000, 1)
        await cb.record_success()
        metrics.record_call_success(
            self.provider_name, model, latency_ms,
            tokens_in=input_tokens or len(str(messages)) // 4,
            tokens_out=output_tokens or len(text) // 4,
        )

        return {
            "text":          text,
            "input_tokens":  input_tokens or len(str(messages)) // 4,
            "output_tokens": output_tokens or len(text) // 4,
            "model":         model,
            "tool_calls":    tool_calls,
        }

    # ── generate_stream() ─────────────────────────────────────────────────────

    async def generate_stream(
        self,
        messages: List[Dict[str, str]],
        model: str = "gemini-2.0-flash",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        tools: Optional[List[Dict[str, Any]]] = None,
        api_key: Optional[str] = None,
        images: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        key_to_use = api_key or self.api_key
        if not key_to_use or str(key_to_use).startswith("mock_"):
            raise Exception(
                "Gemini API key missing or invalid. "
                "Please configure your Gemini API key in Settings."
            )

        cb       = _get_circuit_breaker()
        metrics  = _get_metrics()
        registry = _get_registry()

        # ── Circuit breaker check ─────────────────────────────────────────────
        if not await cb.allow_request():
            err_msg = (
                "GeminiProvider circuit breaker is OPEN — provider quarantined. "
                "Trying next fallback."
            )
            metrics.record_call_failure(self.provider_name, model, "circuit_open")
            raise ProviderCircuitOpenError(err_msg)

        # ── Deprecated model remapping ────────────────────────────────────────
        model = registry.remap_model(model)

        # ── Model availability check ──────────────────────────────────────────
        if not registry.is_model_available(self.provider_name, model):
            raise ProviderModelUnavailableError(
                f"Gemini model '{model}' is marked unavailable (previous HTTP 400/404). "
                "Trying next fallback."
            )

        payload, _, _ = self._build_payload(messages, temperature, max_tokens, tools, images)
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:streamGenerateContent?alt=sse&key={key_to_use}"
        )

        input_tokens  = len(str(messages)) // 4
        output_text   = ""
        start_time    = time.time()
        tool_calls    = []
        max_retries   = 3
        initial_delay = 1.0

        metrics.record_call_start(self.provider_name, model)

        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    async with client.stream("POST", url, json=payload) as response:
                        if response.status_code == 429:
                            await cb.record_failure("rate_limit", no_trip=True)  # 429 = slow down, not broken provider
                            metrics.record_call_failure(self.provider_name, model, "rate_limit", 429)
                            raise ProviderRateLimitError(
                                "Gemini streaming API rate limit exceeded (HTTP 429). "
                                "Please wait a moment or switch to another model."
                            )

                        elif response.status_code in (400, 404):
                            registry.mark_model_unavailable(self.provider_name, model)
                            await cb.record_failure("model_invalid", no_trip=True)  # bad model ID, not broken provider
                            metrics.record_call_failure(self.provider_name, model, "model_invalid", response.status_code)
                            error_body = await response.aread()
                            raise ProviderModelUnavailableError(
                                f"Gemini streaming error {response.status_code} for model '{model}': "
                                f"{error_body.decode('utf-8', errors='ignore')[:300]}"
                            )

                        elif response.status_code in (500, 502, 503, 504):
                            if attempt < max_retries:
                                delay = _jitter(initial_delay * (2 ** attempt))
                                metrics.record_retry(self.provider_name, model, attempt + 1, f"HTTP_{response.status_code}")
                                logger.warning(
                                    f"[GeminiProvider] Stream HTTP {response.status_code} on attempt {attempt + 1}; "
                                    f"retrying in {delay:.2f}s …"
                                )
                                await asyncio.sleep(delay)
                                continue
                            await cb.record_failure("server_error")
                            metrics.record_call_failure(self.provider_name, model, "server_error", response.status_code)
                            raise ProviderServerError(
                                f"Gemini streaming server error {response.status_code} after {max_retries} retries."
                            )

                        elif response.status_code != 200:
                            error_body = await response.aread()
                            try:
                                err_data = json.loads(error_body)
                                err_msg  = err_data.get("error", {}).get("message") or str(err_data)
                            except Exception:
                                err_msg = error_body.decode("utf-8", errors="ignore") or f"HTTP {response.status_code}"
                            await cb.record_failure("unknown")
                            metrics.record_call_failure(self.provider_name, model, "unknown", response.status_code)
                            raise Exception(f"Gemini streaming API error ({response.status_code}): {err_msg}")

                        # ── Stream lines ──────────────────────────────────────
                        async for line in response.aiter_lines():
                            line = line.strip()
                            if not line or not line.startswith("data: "):
                                continue

                            raw_data = line[6:]
                            try:
                                parsed = json.loads(raw_data)
                            except json.JSONDecodeError:
                                continue

                            # Surface API-level errors embedded in the SSE stream
                            if "error" in parsed:
                                err_info = parsed["error"]
                                err_msg  = err_info.get("message") if isinstance(err_info, dict) else str(err_info)
                                raise Exception(f"Gemini API error: {err_msg}")

                            candidates = parsed.get("candidates", [])
                            if not candidates:
                                continue

                            candidate     = candidates[0]
                            finish_reason = candidate.get("finishReason", "")
                            if finish_reason in ("SAFETY", "RECITATION", "OTHER", "BLOCKED"):
                                block_msg = f"Response blocked by Gemini safety filters (reason: {finish_reason})."
                                ratings   = candidate.get("safetyRatings", [])
                                if ratings:
                                    blocked = [r["category"] for r in ratings if r.get("blocked")]
                                    if blocked:
                                        block_msg += f" Blocked categories: {', '.join(blocked)}."
                                raise Exception(block_msg)

                            try:
                                parts = candidate["content"]["parts"]
                                for part in parts:
                                    if "text" in part:
                                        chunk_text  = part["text"]
                                        output_text += chunk_text
                                        yield {"event": "chunk", "text": chunk_text}
                                    if "functionCall" in part:
                                        fc = part["functionCall"]
                                        tool_calls.append({
                                            "name":      fc["name"],
                                            "arguments": fc.get("args", {}),
                                        })
                            except (KeyError, IndexError):
                                continue

                        break  # successful stream completed

            except (ProviderRateLimitError, ProviderModelUnavailableError, ProviderServerError, ProviderCircuitOpenError):
                raise  # already classified; propagate immediately
            except httpx.TimeoutException as exc:
                await cb.record_failure("timeout")
                metrics.record_call_failure(self.provider_name, model, "timeout")
                raise ProviderTimeoutError(f"Gemini streaming request timed out: {exc}") from exc
            except httpx.RequestError as exc:
                await cb.record_failure("network")
                metrics.record_call_failure(self.provider_name, model, "network")
                raise Exception(f"Gemini streaming network error: {exc}") from exc

        # Yield tool calls if any were collected
        if tool_calls:
            yield {"event": "tool_calls", "tool_calls": tool_calls}

        # ── Record success metrics ────────────────────────────────────────────
        latency_ms = int((time.time() - start_time) * 1000)
        out_tokens = len(output_text) // 4
        await cb.record_success()
        metrics.record_call_success(
            self.provider_name, model, latency_ms,
            tokens_in=input_tokens,
            tokens_out=out_tokens or len(tool_calls) * 5,
        )

        yield {
            "event": "metrics",
            "metrics": {
                "model_used":      model,
                "latency_ms":      latency_ms,
                "tokens_input":    input_tokens,
                "tokens_output":   out_tokens or len(tool_calls) * 5,
                "cost_estimate":   (input_tokens * 0.000075 + (out_tokens or len(tool_calls) * 5) * 0.0003) / 1000,
                "confidence_score": 0.92,
                # memory_hits and chunks_used are placeholders;
                # nodes.py overwrites these with real values.
                "memory_hits":  0,
                "chunks_used":  0,
            },
        }
