"""
app/providers/groq.py — Groq LLM provider.

Production hardening applied
─────────────────────────────
BUG FIX: `logger` was used on lines 177 and 297 of the original file but
  was never defined in module scope — causing `NameError` crashes whenever
  HTTP 400/404 occurred.  Fixed by defining `logger` at module level.

• Circuit breaker: fast-fail when the Groq circuit is OPEN.
• Deprecated model remapping via ProviderRegistry.remap_model().
• Model availability check: models marked unavailable after HTTP 400/404
  are rejected immediately without an API round-trip.
• Error classification:
    429       → ProviderRateLimitError
    400 / 404 → ProviderModelUnavailableError + registry.mark_model_unavailable()
    413       → emergency payload trim (existing logic preserved)
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

# ── BUG FIX: logger was undefined in original groq.py ─────────────────────────
logger = logging.getLogger("app.providers.groq")


# ── Provider infrastructure ────────────────────────────────────────────────────

def _get_circuit_breaker():
    from app.providers.circuit_breaker import groq_breaker
    return groq_breaker

def _get_metrics():
    from app.providers.provider_metrics import provider_metrics
    return provider_metrics

def _get_registry():
    from app.providers.registry import provider_registry
    return provider_registry


# ── Custom exception types (string-compatible with nodes.py detection) ─────────

class ProviderRateLimitError(Exception):
    """HTTP 429 — Groq rate limit exceeded."""

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


# ── Message utility ───────────────────────────────────────────────────────────

def _trim_messages_for_token_budget(messages: List[Dict[str, str]], max_chars: int = 16000) -> List[Dict[str, str]]:
    """
    Ensures total message payload stays within Groq's payload & token limit (~16k chars).
    Preserves system instruction at [0] and the latest user turn at [-1].
    Trims middle messages if payload exceeds max_chars.

    System prompt is capped at 60% of max_chars to guarantee room for conversation
    history — this prevents RAG chunks embedded in the system prompt from eating
    the entire budget and triggering HTTP 413 errors.
    """
    if not messages:
        return []

    def _content_len(m: Dict) -> int:
        c = m.get("content", "")
        if isinstance(c, list):  # multimodal (vision) content array
            return sum(len(p.get("text", "")) if p.get("type") == "text" else 500 for p in c)
        return len(c or "")

    total_len = sum(_content_len(m) for m in messages)
    if total_len <= max_chars:
        return messages

    sys_msg = [m for m in messages if m.get("role") == "system"]
    non_sys = [m for m in messages if m.get("role") != "system"]

    # Cap the system prompt at 60% of max_chars
    sys_budget = int(max_chars * 0.60)
    if sys_msg:
        sys_content = sys_msg[0].get("content", "")
        if isinstance(sys_content, str) and len(sys_content) > sys_budget:
            sys_msg = [{
                **sys_msg[0],
                "content": sys_content[:sys_budget] + "\n[System Context Truncated to fit token budget]"
            }]

    if not non_sys:
        return sys_msg

    last_user_msg = non_sys[-1]
    middle_msgs   = non_sys[:-1]

    sys_used      = sum(_content_len(m) for m in sys_msg)
    last_user_len = _content_len(last_user_msg)
    budget        = max_chars - sys_used - last_user_len

    kept_middle  = []
    current_size = 0
    for m in reversed(middle_msgs):
        m_len = _content_len(m)
        if budget > 0 and current_size + m_len <= budget:
            kept_middle.insert(0, m)
            current_size += m_len
        else:
            break

    return sys_msg + kept_middle + [last_user_msg]


class GroqProvider(BaseLLMProvider):

    provider_name = "groq"
    capabilities  = frozenset({"text", "streaming", "tools", "vision"})

    def __init__(self):
        # Server-level key fallback; runtime per-request key takes priority via api_key param
        self.api_key = settings.GROQ_API_KEY

    # ── Vision helper ─────────────────────────────────────────────────────────

    def _inject_images_into_messages(
        self,
        messages: List[Dict[str, Any]],
        images: Optional[List[Dict[str, str]]],
    ) -> List[Dict[str, Any]]:
        """
        Convert the last user message into an OpenAI-compatible multimodal content
        array so that Groq vision models can see images.
        Each image dict must have 'base64' and 'mimeType' keys.
        """
        if not images:
            return messages
        messages = [dict(m) for m in messages]  # shallow copy
        for i in reversed(range(len(messages))):
            if messages[i].get("role") == "user":
                existing_text = messages[i].get("content", "") or ""
                if isinstance(existing_text, list):
                    parts = existing_text
                else:
                    parts: List[Dict[str, Any]] = [{"type": "text", "text": existing_text}]
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
        model: str = "llama-3.1-8b-instant",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        tools: Optional[List[Dict[str, Any]]] = None,
        api_key: Optional[str] = None,
        images: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        key_to_use = api_key or self.api_key
        if not key_to_use or str(key_to_use).startswith("mock_"):
            raise Exception(
                "Groq API key is missing or invalid. "
                "Please configure a valid Groq API key in Settings."
            )

        cb       = _get_circuit_breaker()
        metrics  = _get_metrics()
        registry = _get_registry()

        # ── Circuit breaker check ─────────────────────────────────────────────
        if not await cb.allow_request():
            metrics.record_call_failure(self.provider_name, model, "circuit_open")
            raise ProviderCircuitOpenError(
                "GroqProvider circuit breaker is OPEN — provider quarantined. "
                "Trying next fallback."
            )

        # ── Deprecated model remapping ────────────────────────────────────────
        model = registry.remap_model(model)

        # ── Model availability check ──────────────────────────────────────────
        if not registry.is_model_available(self.provider_name, model):
            raise ProviderModelUnavailableError(
                f"Groq model '{model}' is marked unavailable (previous HTTP 400/404). "
                "Trying next fallback."
            )

        # Inject images for vision models before trimming
        messages         = self._inject_images_into_messages(messages, images)
        trimmed_messages = _trim_messages_for_token_budget(messages, max_chars=16000)

        payload = {
            "model":       model,
            "messages":    trimmed_messages,
            "temperature": temperature,
            "max_tokens":  max_tokens,
            "stream":      False,
        }

        if tools:
            formatted_tools = []
            for t in tools:
                formatted_tools.append({
                    "type": "function",
                    "function": {
                        "name":        t["name"],
                        "description": t["description"],
                        "parameters":  t["parameters"],
                    },
                })
            payload["tools"] = formatted_tools

        url     = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {key_to_use}",
            "Content-Type":  "application/json",
        }

        max_retries   = 3
        initial_delay = 1.0
        data          = None

        metrics.record_call_start(self.provider_name, model)
        call_start = time.monotonic()

        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(url, json=payload, headers=headers)
            except httpx.TimeoutException as exc:
                await cb.record_failure("timeout")
                metrics.record_call_failure(self.provider_name, model, "timeout")
                raise ProviderTimeoutError(f"Groq API request timed out: {exc}") from exc
            except httpx.RequestError as exc:
                await cb.record_failure("network")
                metrics.record_call_failure(self.provider_name, model, "network")
                raise Exception(f"Groq API network error: {exc}") from exc

            if response.status_code == 200:
                data = response.json()
                break

            elif response.status_code == 413:
                # Payload too large — trim progressively and retry
                if attempt < max_retries:
                    emergency_budget = 6000 - (attempt * 1000)
                    payload["messages"] = _trim_messages_for_token_budget(
                        trimmed_messages, max_chars=max(emergency_budget, 3000)
                    )
                    metrics.record_retry(self.provider_name, model, attempt + 1, "HTTP_413_payload_too_large")
                    await asyncio.sleep(0.5)
                    continue
                raise Exception("Request payload size exceeded Groq context limit (HTTP 413). Please start a new chat session.")

            elif response.status_code == 429:
                await cb.record_failure("rate_limit", no_trip=True)  # 429 = slow down, not broken
                metrics.record_call_failure(self.provider_name, model, "rate_limit", 429)
                raise ProviderRateLimitError(
                    "Groq rate limit exceeded (HTTP 429). "
                    "You have reached the API request limit. "
                    "Please wait a moment or switch to another model."
                )

            elif response.status_code in (400, 404):
                # BUG FIX: logger was undefined here in the original file (caused NameError crash)
                logger.warning(
                    f"[GroqProvider] Model '{payload['model']}' returned HTTP {response.status_code}. "
                    "Marking model unavailable and routing to fallback."
                )
                registry.mark_model_unavailable(self.provider_name, model)
                await cb.record_failure("model_invalid", no_trip=True)  # bad model ID, not broken provider
                metrics.record_call_failure(self.provider_name, model, "model_invalid", response.status_code)
                raise ProviderModelUnavailableError(
                    f"Groq API error {response.status_code} for model '{model}': "
                    f"{response.text[:300]}"
                )

            elif response.status_code in (500, 502, 503, 504):
                if attempt < max_retries:
                    delay = _jitter(initial_delay * (2 ** attempt))
                    metrics.record_retry(self.provider_name, model, attempt + 1, f"HTTP_{response.status_code}")
                    logger.warning(
                        f"[GroqProvider] HTTP {response.status_code} on attempt {attempt + 1}; "
                        f"retrying in {delay:.2f}s …"
                    )
                    await asyncio.sleep(delay)
                    continue
                await cb.record_failure("server_error")
                metrics.record_call_failure(self.provider_name, model, "server_error", response.status_code)
                raise ProviderServerError(
                    f"Groq API server error {response.status_code} after {max_retries} retries."
                )

            else:
                await cb.record_failure("unknown")
                metrics.record_call_failure(self.provider_name, model, "unknown", response.status_code)
                raise Exception(f"Groq API returned error {response.status_code}: {response.text}")

        if not data:
            await cb.record_failure("empty_response")
            raise Exception("Groq API returned empty response data.")

        choice = data["choices"][0]["message"]
        text   = choice.get("content") or ""

        tool_calls     = []
        raw_tool_calls = choice.get("tool_calls", [])
        for rtc in raw_tool_calls:
            if rtc.get("type") == "function":
                func = rtc.get("function", {})
                try:
                    args = json.loads(func.get("arguments", "{}"))
                except Exception:
                    args = {}
                tool_calls.append({"name": func.get("name"), "arguments": args})

        input_tokens  = data.get("usage", {}).get("prompt_tokens", 0)
        output_tokens = data.get("usage", {}).get("completion_tokens", 0)

        latency_ms = round((time.monotonic() - call_start) * 1000, 1)
        await cb.record_success()
        metrics.record_call_success(self.provider_name, model, latency_ms,
                                    tokens_in=input_tokens, tokens_out=output_tokens)

        return {
            "text":          text,
            "input_tokens":  input_tokens,
            "output_tokens": output_tokens,
            "model":         model,
            "tool_calls":    tool_calls,
        }

    # ── generate_stream() ─────────────────────────────────────────────────────

    async def generate_stream(
        self,
        messages: List[Dict[str, Any]],
        model: str = "llama-3.1-8b-instant",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        tools: Optional[List[Dict[str, Any]]] = None,
        api_key: Optional[str] = None,
        images: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        key_to_use = api_key or self.api_key
        if not key_to_use or str(key_to_use).startswith("mock_"):
            raise Exception(
                "Groq API key missing or invalid. "
                "Please configure your Groq API key in Settings."
            )

        cb       = _get_circuit_breaker()
        metrics  = _get_metrics()
        registry = _get_registry()

        # ── Circuit breaker check ─────────────────────────────────────────────
        if not await cb.allow_request():
            metrics.record_call_failure(self.provider_name, model, "circuit_open")
            raise ProviderCircuitOpenError(
                "GroqProvider circuit breaker is OPEN — provider quarantined. "
                "Trying next fallback."
            )

        # ── Deprecated model remapping ────────────────────────────────────────
        model = registry.remap_model(model)

        # ── Model availability check ──────────────────────────────────────────
        if not registry.is_model_available(self.provider_name, model):
            raise ProviderModelUnavailableError(
                f"Groq model '{model}' is marked unavailable (previous HTTP 400/404). "
                "Trying next fallback."
            )

        # Inject images for vision models before trimming
        messages         = self._inject_images_into_messages(messages, images)
        trimmed_messages = _trim_messages_for_token_budget(messages, max_chars=16000)

        payload = {
            "model":       model,
            "messages":    trimmed_messages,
            "temperature": temperature,
            "max_tokens":  max_tokens,
            "stream":      True,
        }

        if tools:
            formatted_tools = []
            for t in tools:
                formatted_tools.append({
                    "type": "function",
                    "function": {
                        "name":        t["name"],
                        "description": t["description"],
                        "parameters":  t["parameters"],
                    },
                })
            payload["tools"] = formatted_tools

        url     = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {key_to_use}",
            "Content-Type":  "application/json",
        }

        input_tokens           = len(str(trimmed_messages)) // 4
        output_text            = ""
        start_time             = time.time()
        accumulated_tool_calls: Dict[int, dict] = {}
        max_retries            = 3
        initial_delay          = 1.0

        metrics.record_call_start(self.provider_name, model)

        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    async with client.stream("POST", url, json=payload, headers=headers) as response:
                        if response.status_code == 413:
                            if attempt < max_retries:
                                emergency_budget = 6000 - (attempt * 1000)
                                payload["messages"] = _trim_messages_for_token_budget(
                                    trimmed_messages, max_chars=max(emergency_budget, 3000)
                                )
                                metrics.record_retry(self.provider_name, model, attempt + 1, "HTTP_413_payload_too_large")
                                await asyncio.sleep(0.5)
                                continue
                            raise Exception("Request payload size exceeded Groq context limit (HTTP 413). Please start a new chat session.")

                        elif response.status_code == 429:
                            await cb.record_failure("rate_limit", no_trip=True)  # 429 = slow down, not broken
                            metrics.record_call_failure(self.provider_name, model, "rate_limit", 429)
                            raise ProviderRateLimitError(
                                "Groq streaming API rate limit exceeded (HTTP 429). "
                                "Please wait a moment or switch to another model."
                            )

                        elif response.status_code in (400, 404):
                            # BUG FIX: logger was undefined here in the original file
                            logger.warning(
                                f"[GroqProvider] Streaming model '{payload['model']}' "
                                f"returned HTTP {response.status_code}. "
                                "Marking model unavailable and routing to fallback."
                            )
                            registry.mark_model_unavailable(self.provider_name, model)
                            await cb.record_failure("model_invalid", no_trip=True)  # bad model ID, not broken provider
                            metrics.record_call_failure(self.provider_name, model, "model_invalid", response.status_code)
                            raise ProviderModelUnavailableError(
                                f"Groq streaming error {response.status_code} for model '{model}'."
                            )

                        elif response.status_code in (500, 502, 503, 504):
                            if attempt < max_retries:
                                delay = _jitter(initial_delay * (2 ** attempt))
                                metrics.record_retry(self.provider_name, model, attempt + 1, f"HTTP_{response.status_code}")
                                logger.warning(
                                    f"[GroqProvider] Stream HTTP {response.status_code} on attempt {attempt + 1}; "
                                    f"retrying in {delay:.2f}s …"
                                )
                                await asyncio.sleep(delay)
                                continue
                            await cb.record_failure("server_error")
                            metrics.record_call_failure(self.provider_name, model, "server_error", response.status_code)
                            raise ProviderServerError(
                                f"Groq streaming server error {response.status_code} after {max_retries} retries."
                            )

                        elif response.status_code != 200:
                            await cb.record_failure("unknown")
                            metrics.record_call_failure(self.provider_name, model, "unknown", response.status_code)
                            raise Exception(f"Groq streaming API returned error {response.status_code}")

                        async for line in response.aiter_lines():
                            line = line.strip()
                            if not line:
                                continue

                            if line.startswith("data: "):
                                raw_data = line[6:]
                                if raw_data == "[DONE]":
                                    break

                                try:
                                    parsed = json.loads(raw_data)
                                    delta  = parsed["choices"][0]["delta"]

                                    chunk_text = delta.get("content", "")
                                    if chunk_text:
                                        output_text += chunk_text
                                        yield {"event": "chunk", "text": chunk_text}

                                    tool_calls_delta = delta.get("tool_calls", [])
                                    for tc in tool_calls_delta:
                                        idx = tc.get("index", 0)
                                        if idx not in accumulated_tool_calls:
                                            accumulated_tool_calls[idx] = {"name": "", "arguments": ""}
                                        func_delta = tc.get("function", {})
                                        if "name" in func_delta:
                                            accumulated_tool_calls[idx]["name"] = func_delta["name"]
                                        if "arguments" in func_delta:
                                            accumulated_tool_calls[idx]["arguments"] += func_delta["arguments"]
                                except (KeyError, IndexError, json.JSONDecodeError):
                                    continue

                        break  # successful stream

            except (ProviderRateLimitError, ProviderModelUnavailableError, ProviderServerError, ProviderCircuitOpenError):
                raise
            except httpx.TimeoutException as exc:
                await cb.record_failure("timeout")
                metrics.record_call_failure(self.provider_name, model, "timeout")
                raise ProviderTimeoutError(f"Groq streaming request timed out: {exc}") from exc
            except httpx.RequestError as exc:
                await cb.record_failure("network")
                metrics.record_call_failure(self.provider_name, model, "network")
                raise Exception(f"Groq streaming network error: {exc}") from exc

        # Yield parsed tool calls
        tool_calls_out = []
        for tc in accumulated_tool_calls.values():
            try:
                args = json.loads(tc["arguments"]) if tc["arguments"] else {}
            except Exception:
                args = {}
            tool_calls_out.append({"name": tc["name"], "arguments": args})

        if tool_calls_out:
            yield {"event": "tool_calls", "tool_calls": tool_calls_out}

        # ── Record success metrics ────────────────────────────────────────────
        latency_ms = int((time.time() - start_time) * 1000)
        out_tokens = len(output_text) or len(tool_calls_out) * 5
        await cb.record_success()
        metrics.record_call_success(self.provider_name, model, latency_ms,
                                    tokens_in=input_tokens, tokens_out=out_tokens)

        yield {
            "event": "metrics",
            "metrics": {
                "model_used":       model,
                "latency_ms":       latency_ms,
                "tokens_input":     input_tokens,
                "tokens_output":    out_tokens,
                "cost_estimate":    (input_tokens * 0.00005 + out_tokens * 0.00015) / 1000,
                "confidence_score": 0.85,
                # memory_hits and chunks_used are placeholders;
                # nodes.py overwrites these with real values.
                "memory_hits":  0,
                "chunks_used":  0,
            },
        }
