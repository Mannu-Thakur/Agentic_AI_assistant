import pytest
import json
from unittest.mock import AsyncMock, patch

from app.providers.registry import is_quota_exhaustion, DEPRECATED_MODELS
from app.agent.nodes import generate_response_node, groq_provider, gemini_provider, openai_provider
from app.tools.registry import ToolRegistry

# Mark ToolRegistry as initialized so unit tests don't try to connect to the DB
ToolRegistry().is_initialized = True


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
    """Verify that modern Gemini models (2.5, 2.0, 1.5) are NOT prematurely remapped or collapsed."""
    assert "gemini-2.5-flash" not in DEPRECATED_MODELS
    assert "gemini-2.5-pro" not in DEPRECATED_MODELS
    assert "gemini-2.0-flash" not in DEPRECATED_MODELS
    assert "gemini-2.0-flash-lite" not in DEPRECATED_MODELS
    assert "gemini-1.5-flash" not in DEPRECATED_MODELS

    # Truly retired models are remapped
    assert DEPRECATED_MODELS.get("gemini-1.0-pro") == "gemini-2.0-flash"
    assert DEPRECATED_MODELS.get("gemini-pro") == "gemini-2.0-flash"


@pytest.mark.asyncio
async def test_intra_provider_groq_fallback_on_tpm_limit(monkeypatch):
    """
    When Groq llama-3.3-70b-versatile hits a 6K TPM limit (HTTP 429),
    the fallback engine should seamlessly fall back to llama-3.1-8b-instant (30K TPM)
    on the exact same key and succeed.
    """
    calls = []

    async def mock_groq_stream(*args, **kwargs):
        model = kwargs.get("model")
        calls.append(model)
        if model == "llama-3.3-70b-versatile":
            if False:
                yield {}
            raise Exception("429 Rate limit reached for model `llama-3.3-70b-versatile` on tokens per minute (TPM): Limit 6000")
        elif model == "llama-3.1-8b-instant":
            yield {"event": "chunk", "text": "Response from Llama 3.1 8B Instant."}
            yield {"event": "metrics", "metrics": {"total_tokens": 25, "model_used": "llama-3.1-8b-instant"}}

    monkeypatch.setattr(groq_provider, "generate_stream", mock_groq_stream)

    state = {
        "messages": [{"role": "user", "content": "Explain quantum computing."}],
        "active_model": "llama-3.3-70b-versatile",
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
    assert "llama-3.3-70b-versatile" in calls
    assert "llama-3.1-8b-instant" in calls
    assert "Response from Llama 3.1 8B Instant." in result["response_text"]
    assert "Note: Selected model" in result["response_text"]
    assert "llama-3.1-8b-instant" in result["response_text"]


@pytest.mark.asyncio
async def test_intra_provider_gemini_fallback_on_rpm_limit(monkeypatch):
    """
    When Gemini 2.0 Flash encounters a transient 15 RPM rate limit (HTTP 429),
    the engine should fall back to gemini-2.0-flash-lite (30 RPM) on the same key.
    """
    calls = []

    async def mock_gemini_stream(*args, **kwargs):
        model = kwargs.get("model")
        calls.append(model)
        if model == "gemini-2.0-flash":
            if False:
                yield {}
            raise Exception("Gemini streaming API rate limit exceeded (HTTP 429). 15 RPM reached.")
        elif model == "gemini-2.0-flash-lite":
            yield {"event": "chunk", "text": "Response from Gemini 2.0 Flash Lite."}
            yield {"event": "metrics", "metrics": {"total_tokens": 30, "model_used": "gemini-2.0-flash-lite"}}

    monkeypatch.setattr(gemini_provider, "generate_stream", mock_gemini_stream)

    state = {
        "messages": [{"role": "user", "content": "Hello!"}],
        "active_model": "gemini-2.0-flash",
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
    assert "gemini-2.0-flash" in calls
    assert "gemini-2.0-flash-lite" in calls
    assert "Response from Gemini 2.0 Flash Lite." in result["response_text"]


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
        "active_model": "gemini-2.0-flash",
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
    assert "gemini-2.0-flash" in gemini_calls
    assert "gemini-2.0-flash-lite" not in gemini_calls  # Smart skip in action!
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
        "active_model": "gemini-2.0-flash",
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
    assert "API Rate Limit / Quota Exceeded" in text
    assert "GEMINI" in text
    assert "GROQ" in text
    assert "Account daily quota" in text or "Rate limit" in text
    assert "How to resolve:" in text


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
        elif model == "google/gemini-2.0-flash":
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
    assert "google/gemini-2.0-flash" in calls

    # 2. Result state correctness
    assert "OpenRouter Gemini Flash response." in result["response_text"]
    assert result["model_used"] == "google/gemini-2.0-flash"
    assert result["active_model"] == "google/gemini-2.0-flash"
    assert result["provider_used"] == "openrouter"

    # 3. provider_metrics recorded the fallback
    recent_fallbacks = [fb for fb in provider_metrics._fallback_log if fb.get("to_model") == "google/gemini-2.0-flash"]
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
async def test_judge_prefers_llama_8b_instant(monkeypatch):
    """
    Verify _call_llm_judge tries llama-3.1-8b-instant first for fast,
    high-TPM headroom query evaluations.
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
