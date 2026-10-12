import pytest
import json
from unittest.mock import AsyncMock, patch

from app.providers.registry import is_quota_exhaustion, DEPRECATED_MODELS, provider_registry
from app.agent.nodes import generate_response_node, groq_provider, gemini_provider, openai_provider



def test_is_quota_exhaustion_detection():
    """Verify is_quota_exhaustion accurately differentiates account quota from per-model rate limits."""
    # Account / project level quota exhaustion
    assert is_quota_exhaustion("RESOURCE_EXHAUSTED: Quota exceeded for quota metric 'Generate Content API requests per day'")
    assert is_quota_exhaustion("Error 429: You exceeded your current quota, please check your plan and billing details.")
    assert is_quota_exhaustion("HTTP 429: insufficient_quota for organization org-12345")
    assert is_quota_exhaustion("Daily limit reached for requests per day (RPD)")
    assert is_quota_exhaustion("402 Payment Required: insufficient credits")
    assert is_quota_exhaustion("Free tier limit reached for the day")

    # Transient per-model RPM / TPM rate limits (should NOT be marked as whole-account exhaustion)
    assert not is_quota_exhaustion("429 Rate limit reached for model `llama-3.3-70b-versatile` on tokens per minute (TPM): Limit 6000, Used 5800")
    assert not is_quota_exhaustion("Gemini streaming API rate limit exceeded (HTTP 429). Please wait a moment")
    assert not is_quota_exhaustion("Rate limit exceeded (15 requests per minute). Try again in 4s.")
    assert not is_quota_exhaustion("")
    assert not is_quota_exhaustion(None)


def test_deprecated_models_preserves_valid_gemini_models():
    """Verify modern Gemini models are active and obsolete ones are remapped to gemini-3.5-flash."""
    assert "gemini-3.5-flash" not in DEPRECATED_MODELS
    assert "gemini-3.5-flash-lite" not in DEPRECATED_MODELS

    # Truly retired models and legacy aliases are remapped
    assert DEPRECATED_MODELS.get("gemini-1.0-pro") == "gemini-3.5-flash"
    assert DEPRECATED_MODELS.get("gemini-pro") == "gemini-3.5-flash"


@pytest.mark.asyncio
async def test_intra_provider_groq_fallback_on_tpm_limit(monkeypatch):
    """
    When Groq primary model hits a 6K TPM limit (HTTP 429),
    the fallback engine should seamlessly fall back to llama-3.1-8b-instant
    on the exact same key and succeed.
    """
    calls = []

    async def mock_groq_stream(*args, **kwargs):
        model = kwargs.get("model")
        calls.append(model)
        if model == "meta-llama/llama-4-scout-17b-16e-instruct":
            if False:
                yield {}
            raise Exception("429 Rate limit reached on tokens per minute (TPM): Limit 6000")
        elif model == "llama-3.1-8b-instant":
            yield {"event": "chunk", "text": "Response from Llama 3.1 8B."}
            yield {"event": "metrics", "metrics": {"total_tokens": 25, "model_used": "llama-3.1-8b-instant"}}

    monkeypatch.setattr(groq_provider, "generate_stream", mock_groq_stream)

    state = {
        "messages": [{"role": "user", "content": "Explain quantum computing."}],
        "active_model": "meta-llama/llama-4-scout-17b-16e-instruct",
        "intent": "NORMAL_CHAT",
        "allowed_tools": [],
        "source_documents": [],
        "retrieved_documents": [],
        "steps": [],
    }
    config = {
        "configurable": {
            "api_keys": {"groq": "gsk_test_key_valid_12345"},
            "groq_api_key": "gsk_test_key_valid_12345",
        }
    }

    result = await generate_response_node(state, config)
    assert "meta-llama/llama-4-scout-17b-16e-instruct" in calls
    assert "llama-3.1-8b-instant" in calls
    assert "Response from Llama 3.1 8B." in result["response_text"]
    assert "Note: Selected model" in result["response_text"]
    assert "llama-3.1-8b-instant" in result["response_text"]


@pytest.mark.asyncio
async def test_intra_provider_gemini_fallback_on_rpm_limit(monkeypatch):
    """
    When Gemini 3.5 Flash encounters a transient 15 RPM rate limit (HTTP 429),
    the engine should fall back to gemini-3.5-flash-lite on the same key.
    """
    calls = []

    async def mock_gemini_stream(*args, **kwargs):
        model = kwargs.get("model")
        calls.append(model)
        if model == "gemini-3.5-flash":
            if False:
                yield {}
            raise Exception("Gemini streaming API rate limit exceeded (HTTP 429). 15 RPM reached.")
        elif model == "gemini-3.5-flash-lite":
            yield {"event": "chunk", "text": "Response from Gemini 3.5 Flash Lite."}
            yield {"event": "metrics", "metrics": {"total_tokens": 30, "model_used": "gemini-3.5-flash-lite"}}

    monkeypatch.setattr(gemini_provider, "generate_stream", mock_gemini_stream)

    state = {
        "messages": [{"role": "user", "content": "Hello!"}],
        "active_model": "gemini-3.5-flash",
        "intent": "NORMAL_CHAT",
        "allowed_tools": [],
        "source_documents": [],
        "retrieved_documents": [],
        "steps": [],
    }
    config = {
        "configurable": {
            "api_keys": {"gemini": "AIzaSyTestGeminiKey12345"},
            "gemini_api_key": "AIzaSyTestGeminiKey12345",
        }
    }

    result = await generate_response_node(state, config)
    assert "gemini-3.5-flash" in calls
    assert "gemini-3.5-flash-lite" in calls
    assert "Response from Gemini 3.5 Flash Lite." in result["response_text"]


@pytest.mark.asyncio
async def test_cross_provider_fallback_on_account_quota_exhaustion(monkeypatch):
    """
    When Gemini returns RESOURCE_EXHAUSTED (daily request quota on the key is finished),
    the system must SKIP all remaining models for Gemini and immediately fall back
    to Groq without wasting calls on dead Gemini endpoints.
    """
    gemini_calls = []
    groq_calls = []

    async def mock_gemini_stream(*args, **kwargs):
        model = kwargs.get("model")
        gemini_calls.append(model)
        if False:
            yield {}
        raise Exception("RESOURCE_EXHAUSTED: Quota exceeded for quota metric 'Generate Content API requests per day'")

    async def mock_groq_stream(*args, **kwargs):
        model = kwargs.get("model")
        groq_calls.append(model)
        yield {"event": "chunk", "text": "Cross-provider rescue response from Groq!"}
        yield {"event": "metrics", "metrics": {"total_tokens": 15, "model_used": model}}

    monkeypatch.setattr(gemini_provider, "generate_stream", mock_gemini_stream)
    monkeypatch.setattr(groq_provider, "generate_stream", mock_groq_stream)

    state = {
        "messages": [{"role": "user", "content": "Tell me a fun fact."}],
        "active_model": "gemini-3.5-flash",
        "intent": "NORMAL_CHAT",
        "allowed_tools": [],
        "source_documents": [],
        "retrieved_documents": [],
        "steps": [],
    }
    config = {
        "configurable": {
            "api_keys": {
                "gemini": "AIzaSyExhaustedKey",
                "groq": "gsk_healthy_groq_key_999",
            },
            "gemini_api_key": "AIzaSyExhaustedKey",
            "groq_api_key": "gsk_healthy_groq_key_999",
        }
    }

    result = await generate_response_node(state, config)
    # Gemini was called once, saw daily quota exhausted, and skipped remaining Gemini models
    assert len(gemini_calls) == 1
    assert "gemini-3.5-flash" in gemini_calls
    assert "gemini-3.5-flash-lite" not in gemini_calls  # Smart skip in action!
    assert len(groq_calls) >= 1
    assert "Cross-provider rescue response from Groq!" in result["response_text"]


@pytest.mark.asyncio
async def test_all_providers_failed_generates_detailed_diagnostic(monkeypatch):
    """
    When all providers fail, the system must NOT falsely claim only 'active model quota reached'.
    It must provide a clear bulleted breakdown of what was attempted and failed.
    """
    async def mock_gemini_fail(*args, **kwargs):
        if False:
            yield {}
        raise Exception("RESOURCE_EXHAUSTED: Daily request limit reached")

    async def mock_groq_fail(*args, **kwargs):
        if False:
            yield {}
        raise Exception("429 Rate limit reached for model `llama-3.3-70b-versatile` on TPM limit")

    monkeypatch.setattr(gemini_provider, "generate_stream", mock_gemini_fail)
    monkeypatch.setattr(groq_provider, "generate_stream", mock_groq_fail)

    state = {
        "messages": [{"role": "user", "content": "Help me."}],
        "active_model": "gemini-3.5-flash",
        "intent": "NORMAL_CHAT",
        "allowed_tools": [],
        "source_documents": [],
        "retrieved_documents": [],
        "steps": [],
    }
    config = {
        "configurable": {
            "api_keys": {
                "gemini": "AIzaSyExhaustedKey",
                "groq": "gsk_limited_groq_key",
            },
            "gemini_api_key": "AIzaSyExhaustedKey",
            "groq_api_key": "gsk_limited_groq_key",
        }
    }

    result = await generate_response_node(state, config)
    text = result["response_text"]
    assert "Service Temporarily Busy" in text or "Rate Limit" in text
    assert "Google Gemini" in text or "Gemini" in text
    assert "Groq" in text
    assert "Rate limit or quota" in text or "Rate limit" in text
    assert "Quick fix:" in text or "How to resolve:" in text


@pytest.mark.asyncio
async def test_openrouter_model_normalization_and_fallback_metrics(monkeypatch):
    """
    Verify:
    1. OpenRouter model names are normalized without double prefixing.
    2. Fallback transitions are recorded in provider_metrics.
    3. Returned state contains active_model, model_used, and provider_used.
    """
    from app.agent.nodes import openrouter_provider
    from app.providers.provider_metrics import provider_metrics

    calls = []

    async def mock_openrouter_stream(*args, **kwargs):
        model = kwargs.get("model")
        calls.append(model)
        if model == "anthropic/claude-3.5-sonnet":
            if False:
                yield {}
            raise Exception("429 Rate limit exceeded on claude-3.5-sonnet")
        elif model == "google/gemini-2.0-flash-001":
            yield {"event": "chunk", "text": "OpenRouter Gemini Flash response."}
            yield {"event": "metrics", "metrics": {"total_tokens": 40, "model_used": model}}

    monkeypatch.setattr(openrouter_provider, "generate_stream", mock_openrouter_stream)

    state = {
        "messages": [{"role": "user", "content": "Write Python code."}],
        "active_model": "openrouter/anthropic/claude-3.5-sonnet",
        "intent": "NORMAL_CHAT",
        "allowed_tools": [],
        "source_documents": [],
        "retrieved_documents": [],
        "steps": [],
    }
    config = {
        "configurable": {
            "api_keys": {"openrouter": "sk-or-v1-valid-test-key"},
            "openrouter_api_key": "sk-or-v1-valid-test-key",
        }
    }

    result = await generate_response_node(state, config)

    # 1. No double prefixing like anthropic/anthropic/...
    assert "anthropic/anthropic/claude-3.5-sonnet" not in calls
    assert "anthropic/claude-3.5-sonnet" in calls
    assert "google/gemini-2.0-flash-001" in calls

    # 2. Result state correctness
    assert "OpenRouter Gemini Flash response." in result["response_text"]
    assert result["model_used"] == "google/gemini-2.0-flash-001"
    assert result["active_model"] == "google/gemini-2.0-flash-001"
    assert result["provider_used"] == "openrouter"

    # 3. provider_metrics recorded the fallback
    recent_fallbacks = [fb for fb in provider_metrics._fallback_log if fb.get("to_model") == "google/gemini-2.0-flash-001"]
    assert len(recent_fallbacks) >= 1


@pytest.mark.asyncio
async def test_stream_interruption_handles_gracefully(monkeypatch):
    """
    If a stream yields partial tokens and then crashes mid-turn,
    the system must NOT raise an unhandled exception. It should append
    an inline notice, preserve what was streamed, and exit gracefully.
    """
    async def mock_crashing_stream(*args, **kwargs):
        yield {"event": "chunk", "text": "Here is the beginning of the story..."}
        raise Exception("Connection reset by peer mid-stream")

    monkeypatch.setattr(gemini_provider, "generate_stream", mock_crashing_stream)

    state = {
        "messages": [{"role": "user", "content": "Tell a story."}],
        "active_model": "gemini-2.0-flash",
        "intent": "NORMAL_CHAT",
        "allowed_tools": [],
        "source_documents": [],
        "retrieved_documents": [],
        "steps": [],
    }
    config = {
        "configurable": {
            "api_keys": {"gemini": "AIzaSyValidKey"},
            "gemini_api_key": "AIzaSyValidKey",
        }
    }

    result = await generate_response_node(state, config)
    resp = result["response_text"]
    assert "Here is the beginning of the story..." in resp
    assert "Response interrupted:" in resp
    assert "Connection reset by peer" in resp


@pytest.mark.asyncio
async def test_judge_prefers_fast_groq_model(monkeypatch):
    """
    Verify _call_llm_judge tries llama-3.1-8b-instant first for fast,
    high-TPM headroom query evaluations on Groq.
    """
    from app.agent.nodes import _call_llm_judge

    called_models = []

    async def mock_groq_gen(*args, **kwargs):
        model = kwargs.get("model")
        called_models.append(model)
        return {"text": '{"verdict": "PASS"}'}

    monkeypatch.setattr(groq_provider, "generate", mock_groq_gen)

    config = {
        "configurable": {
            "api_keys": {"groq": "gsk_valid_key"},
            "groq_api_key": "gsk_valid_key",
        }
    }

    res = await _call_llm_judge("Is this valid?", config)
    assert res == {"verdict": "PASS"}
    assert called_models[0] == "llama-3.1-8b-instant"


def test_enhanced_quota_exhaustion_indicators():
    """Verify tpd, tokens per day, and out of credits are recognized."""
    assert is_quota_exhaustion("Rate limit reached for tokens per day (TPD)")
    assert is_quota_exhaustion("TPD limit exceeded")
    assert is_quota_exhaustion("Account is out of credits")


def test_deprecated_models_groq_remapping():
    """Verify decommissioned Groq models are remapped to active equivalents.
    
    Note: llama-3.3-70b-versatile was decommissioned August 16, 2026 and remapped 
    to meta-llama/llama-4-scout-17b-16e-instruct per provider registry.
    """
    llama4 = "meta-llama/llama-4-scout-17b-16e-instruct"
    assert DEPRECATED_MODELS.get("llama3-70b-8192") == llama4
    assert DEPRECATED_MODELS.get("llama-3-70b") == llama4
    assert DEPRECATED_MODELS.get("llama-3.1-70b-versatile") == llama4
    assert DEPRECATED_MODELS.get("mixtral-8x7b-32768") == llama4


def test_provider_registry_protects_known_models():
    """Verify provider registry refuses to quarantine core KNOWN_MODELS on 400/404."""
    # Attempting to mark a core Groq model unavailable should be rejected
    provider_registry.mark_model_unavailable("groq", "meta-llama/llama-4-scout-17b-16e-instruct")
    assert provider_registry.is_model_available("groq", "meta-llama/llama-4-scout-17b-16e-instruct") is True

    # Attempting to mark a core Gemini model unavailable should be rejected
    provider_registry.mark_model_unavailable("gemini", "gemini-3.5-flash")
    assert provider_registry.is_model_available("gemini", "gemini-3.5-flash") is True

    # An unknown model should be quarantineable
    provider_registry.mark_model_unavailable("groq", "nonexistent-model-xyz")
    assert provider_registry.is_model_available("groq", "nonexistent-model-xyz") is False


@pytest.mark.asyncio
async def test_groq_gemma_omits_tools(monkeypatch):
    """Verify Groq provider omits tools when model is Gemma 2 (which rejects tool calling)."""
    captured_payload = {}

    class MockStreamResponse:
        status_code = 200
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass
        async def aiter_lines(self):
            yield 'data: {"choices": [{"delta": {"content": "Hello from Gemma"}}]}'
            yield 'data: [DONE]'

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        def stream(self, method, url, json=None, headers=None):
            nonlocal captured_payload
            captured_payload = json
            return MockStreamResponse()

    monkeypatch.setattr("httpx.AsyncClient", MockAsyncClient)

    tools = [{
        "name": "search",
        "description": "web search",
        "parameters": {"type": "object", "properties": {}},
    }]
    messages = [{"role": "user", "content": "Hi"}]

    chunks = []
    async for event in groq_provider.generate_stream(
        messages=messages,
        model="gemma2-9b-it",
        api_key="gsk_valid_key",
        tools=tools,
    ):
        chunks.append(event)

    assert "tools" not in captured_payload, "tools should be omitted for Gemma models"
    assert any("Hello from Gemma" in e.get("text", "") for e in chunks if e.get("event") == "chunk")


@pytest.mark.asyncio
async def test_normal_chat_greeting_bypasses_retrieval_and_web_search(monkeypatch):
    """
    Verify a simple conversational greeting ('Hi i am mannu!'):
    1. route_retrieval routes directly to generate_response when needs_retrieval=False
    2. Decommissioned 'llama3-70b-8192' is remapped without error
    3. No web search is triggered
    """
    from app.agent.graph import route_retrieval

    # 1. Router verification
    chat_state = {
        "needs_retrieval": False,
        "intent": "NORMAL_CHAT",
    }
    assert route_retrieval(chat_state) == "generate_response"

    # 2. Decommissioned model requested -> remapped and fulfilled
    calls = []

    async def mock_groq_stream(*args, **kwargs):
        model = kwargs.get("model")
        calls.append(model)
        yield {"event": "chunk", "text": "Hello Mannu! How can I assist you today?"}
        yield {"event": "metrics", "metrics": {"total_tokens": 15, "model_used": model}}

    monkeypatch.setattr(groq_provider, "generate_stream", mock_groq_stream)

    state = {
        "messages": [{"role": "user", "content": "Hi i am mannu!"}],
        "active_model": "llama3-70b-8192",  # User requested decommissioned ID
        "intent": "NORMAL_CHAT",
        "allowed_tools": [],
        "source_documents": [],
        "retrieved_documents": [],
        "steps": [],
        "needs_retrieval": False,
    }
    config = {
        "configurable": {
            "api_keys": {"groq": "gsk_test_key_valid_12345"},
            "groq_api_key": "gsk_test_key_valid_12345",
        }
    }

    result = await generate_response_node(state, config)
    assert "Hello Mannu!" in result["response_text"]
    assert calls[0] == "meta-llama/llama-4-scout-17b-16e-instruct", "llama3-70b-8192 should be remapped to meta-llama/llama-4-scout-17b-16e-instruct"

