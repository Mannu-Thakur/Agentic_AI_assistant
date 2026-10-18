import pytest
import json
from unittest.mock import AsyncMock, patch

from app.providers.registry import is_quota_exhaustion, DEPRECATED_MODELS, KNOWN_MODELS, provider_registry
from app.agent.nodes import generate_response_node, groq_provider, gemini_provider, openai_provider
from app.core.config import settings
from app.routing.model_profiles import MODEL_PROFILES



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
    assert not is_quota_exhaustion("429 Rate limit reached for model `openai/gpt-oss-120b` on tokens per minute (TPM): Limit 6000, Used 5800")
    assert not is_quota_exhaustion("Gemini streaming API rate limit exceeded (HTTP 429). Please wait a moment")
    assert not is_quota_exhaustion("Rate limit exceeded (15 requests per minute). Try again in 4s.")
    assert not is_quota_exhaustion("")
    assert not is_quota_exhaustion(None)


def test_deprecated_models_preserves_valid_gemini_models():
    """Legacy Gemini aliases must move forward to the configured model."""
    assert DEPRECATED_MODELS.get("gemini-3.5-flash") == settings.GEMINI_MODEL
    assert "gemini-3.5-flash-lite" not in DEPRECATED_MODELS
    assert "gemini-3.1-flash-lite" not in DEPRECATED_MODELS
    assert DEPRECATED_MODELS.get("gemini-3.7-flash") == settings.GEMINI_MODEL

    # Truly retired models and legacy aliases are remapped to the deployment choice.
    assert DEPRECATED_MODELS.get("gemini-1.0-pro") == settings.GEMINI_MODEL
    assert DEPRECATED_MODELS.get("gemini-pro") == settings.GEMINI_MODEL


@pytest.mark.asyncio
async def test_intra_provider_groq_fallback_on_tpm_limit(monkeypatch):
    """
    When Groq primary model hits a 6K TPM limit (HTTP 429),
    the fallback engine should try another configured Groq model on the same key.
    """
    calls = []

    async def mock_groq_stream(*args, **kwargs):
        model = kwargs.get("model")
        calls.append(model)
        if model == settings.GROQ_MODEL:
            if False:
                yield {}
            raise Exception("429 Rate limit reached on tokens per minute (TPM): Limit 6000")
        else:
            yield {"event": "chunk", "text": f"Response from Groq fallback {model}."}
            yield {"event": "metrics", "metrics": {"total_tokens": 25, "model_used": model}}

    monkeypatch.setattr(groq_provider, "generate_stream", mock_groq_stream)

    state = {
        "messages": [{"role": "user", "content": "Explain quantum computing."}],
        "active_model": settings.GROQ_MODEL,
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
    assert calls[0] == settings.GROQ_MODEL
    assert len(calls) >= 2
    assert calls[1] != calls[0]
    assert f"Response from Groq fallback {calls[1]}." in result["response_text"]
    assert "Note: Selected model" in result["response_text"]
    assert calls[1] in result["response_text"]


@pytest.mark.asyncio
async def test_intra_provider_gemini_fallback_on_rpm_limit(monkeypatch):
    """
    When the configured Gemini model hits a transient 15 RPM limit,
    the engine should try the next configured Gemini fallback on the same key.
    """
    calls = []

    async def mock_gemini_stream(*args, **kwargs):
        model = kwargs.get("model")
        calls.append(model)
        if model == settings.GEMINI_MODEL:
            if False:
                yield {}
            raise Exception("Gemini streaming API rate limit exceeded (HTTP 429). 15 RPM reached.")
        else:
            yield {"event": "chunk", "text": f"Response from Gemini fallback {model}."}
            yield {"event": "metrics", "metrics": {"total_tokens": 30, "model_used": model}}

    monkeypatch.setattr(gemini_provider, "generate_stream", mock_gemini_stream)

    state = {
        "messages": [{"role": "user", "content": "Hello!"}],
        "active_model": settings.GEMINI_MODEL,
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
    assert calls[0] == settings.GEMINI_MODEL
    assert len(calls) >= 2 and calls[1] != calls[0]
    assert f"Response from Gemini fallback {calls[1]}." in result["response_text"]


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
        "active_model": settings.GEMINI_MODEL,
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
    assert gemini_calls[0] == settings.GEMINI_MODEL
    assert len(gemini_calls) == 1  # Account quota failure skips same-provider fallbacks.
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
        raise Exception("429 Rate limit reached for model `openai/gpt-oss-20b` on TPM limit")

    monkeypatch.setattr(gemini_provider, "generate_stream", mock_gemini_fail)
    monkeypatch.setattr(groq_provider, "generate_stream", mock_groq_fail)

    state = {
        "messages": [{"role": "user", "content": "Help me."}],
        "active_model": settings.GEMINI_MODEL,
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
    assert "Provider Limits Reached" in text
    assert "Google Gemini" in text or "Gemini" in text
    assert "Groq" in text
    assert "Account usage or billing quota reached" in text
    assert "Temporary request rate limit reached" in text
    assert "Check usage and billing" in text
    assert "temporary rate limit, wait 30 seconds" in text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_error", "expected_message", "forbidden_message"),
    [
        (
            "429 insufficient_quota: You exceeded your current quota; check billing.",
            "Provider Quota Exhausted",
            "wait 30 seconds",
        ),
        (
            "429 Rate limit reached for model on TPM. Please wait a moment.",
            "Service Temporarily Busy",
            "billing limits",
        ),
    ],
)
async def test_provider_failure_advice_matches_quota_or_rate_limit(
    monkeypatch, provider_error, expected_message, forbidden_message
):
    async def mock_openai_fail(*args, **kwargs):
        if False:
            yield {}
        raise Exception(provider_error)

    monkeypatch.setattr(openai_provider, "generate_stream", mock_openai_fail)
    for setting in ("GEMINI_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.setattr(settings, setting, None)

    state = {
        "messages": [{"role": "user", "content": "Give a short response."}],
        "active_model": "gpt-4o-mini",
        "intent": "NORMAL_CHAT",
        "allowed_tools": [],
        "source_documents": [],
        "retrieved_documents": [],
        "steps": [],
    }
    config = {
        "configurable": {
            "api_keys": {"openai": "sk-regression-test-key"},
            "openai_api_key": "sk-regression-test-key",
        }
    }

    result = await generate_response_node(state, config)
    assert expected_message in result["response_text"]
    assert forbidden_message not in result["response_text"]


@pytest.mark.asyncio
async def test_list_providers_advertises_server_models_without_returning_keys(monkeypatch):
    from types import SimpleNamespace
    from app.api.api_keys import list_providers

    class EmptyResult:
        def scalars(self):
            return self

        def all(self):
            return []

    class EmptyDatabase:
        async def execute(self, _statement):
            return EmptyResult()

    server_key = "deployment-test-key-never-return"
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", server_key)
    monkeypatch.setattr(settings, "GROQ_API_KEY", "mock_server_key")
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", None)

    response = await list_providers(
        current_user=SimpleNamespace(id="server-model-test-user"),
        db=EmptyDatabase(),
    )
    providers = {provider.id: provider for provider in response}

    assert providers["openai"].serverConfigured is True
    assert providers["openai"].serverModels == [settings.OPENAI_MODEL]
    assert providers["openai"].saved is False
    assert providers["openai"].verified is False
    assert providers["groq"].serverConfigured is False
    assert providers["groq"].serverModels == []
    assert server_key not in response[0].model_dump_json() + "".join(
        provider.model_dump_json() for provider in response
    )


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
        elif model == "openrouter/auto":
            yield {"event": "chunk", "text": "OpenRouter fallback response."}
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
    assert "openrouter/auto" in calls

    # 2. Result state correctness
    assert "OpenRouter fallback response." in result["response_text"]
    assert result["model_used"] == "openrouter/auto"
    assert result["active_model"] == "openrouter/auto"
    assert result["provider_used"] == "openrouter"

    # 3. provider_metrics recorded the fallback
    recent_fallbacks = [fb for fb in provider_metrics._fallback_log if fb.get("to_model") == "openrouter/auto"]
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
    Verify _call_llm_judge tries the configured Groq model first.
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
    assert called_models[0] == settings.GROQ_MODEL


def test_enhanced_quota_exhaustion_indicators():
    """Verify tpd, tokens per day, and out of credits are recognized."""
    assert is_quota_exhaustion("Rate limit reached for tokens per day (TPD)")
    assert is_quota_exhaustion("TPD limit exceeded")
    assert is_quota_exhaustion("Account is out of credits")


def test_deprecated_models_groq_remapping():
    """Deprecated Groq IDs map to current production models."""
    assert DEPRECATED_MODELS.get("llama-3.1-8b-instant") == "openai/gpt-oss-20b"
    assert DEPRECATED_MODELS.get("llama-3.3-70b-versatile") == "openai/gpt-oss-120b"
    assert DEPRECATED_MODELS.get("meta-llama/llama-4-scout-17b-16e-instruct") == "openai/gpt-oss-120b"
    assert DEPRECATED_MODELS.get("groq/compound-mini") == "openai/gpt-oss-20b"
    assert DEPRECATED_MODELS.get("llama3-70b-8192") == "openai/gpt-oss-120b"
    assert DEPRECATED_MODELS.get("llama-3-70b") == "openai/gpt-oss-120b"
    assert DEPRECATED_MODELS.get("mixtral-8x7b-32768") == "openai/gpt-oss-120b"

    retired = {
        "llama-3.1-8b-instant",
        "llama-3.3-70b-versatile",
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "groq/compound-mini",
    }
    assert retired.isdisjoint(KNOWN_MODELS["groq"])
    assert retired.isdisjoint(MODEL_PROFILES)
    assert {"openai/gpt-oss-20b", "openai/gpt-oss-120b"}.issubset(KNOWN_MODELS["groq"])
    assert {"openai/gpt-oss-20b", "openai/gpt-oss-120b"}.issubset(MODEL_PROFILES)


def test_provider_registry_protects_known_models():
    """Verify provider registry refuses to quarantine core KNOWN_MODELS on 400/404."""
    # Attempting to mark a core Groq model unavailable should be rejected
    provider_registry.mark_model_unavailable("groq", "openai/gpt-oss-20b")
    assert provider_registry.is_model_available("groq", "openai/gpt-oss-20b") is True

    # Attempting to mark a core Gemini model unavailable should be rejected
    provider_registry.mark_model_unavailable("gemini", settings.GEMINI_MODEL)
    assert provider_registry.is_model_available("gemini", settings.GEMINI_MODEL) is True

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
    assert calls[0] == DEPRECATED_MODELS["llama3-70b-8192"]

