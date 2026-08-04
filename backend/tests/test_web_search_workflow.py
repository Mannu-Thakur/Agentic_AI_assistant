"""
tests/test_web_search_workflow.py

Production-grade tests for the web search workflow fixes:
  1. DDG fallback fires correctly when TAVILY_API_KEY is absent/mock
  2. DDG fallback fires when Tavily returns a non-200 HTTP error
  3. No Paris weather mock string ever leaks into responses
  4. News / political queries route to INTENT_WEB_SEARCH
  5. Resignation keywords route to INTENT_WEB_SEARCH
  6. grade_documents_node triggers web fallback for WEB_SEARCH intent
  7. False breaking-news claims are NOT confirmed when search finds nothing
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from langchain_core.messages import HumanMessage, AIMessage

from app.tools.local_tools import tavily_search, _ddg_search_fallback
from app.services.web_search import SearchResult
from app.agent.prompts import INTENT_WEB_SEARCH, INTENT_NORMAL_CHAT, INTENT_DOCUMENT_QA


# ─────────────────────────────────────────────────────────────────────────────
#  Helper: build a minimal AgentState-like dict
# ─────────────────────────────────────────────────────────────────────────────

def _make_state(**kwargs) -> dict:
    base = {
        "messages": [],
        "retrieved_documents": [],
        "source_documents": [],
        "intent": INTENT_NORMAL_CHAT,
        "is_private_doc_query": False,
        "allowed_tools": [],
        "steps": [],
        "resolved_query": "",
    }
    base.update(kwargs)
    return base


# ─────────────────────────────────────────────────────────────────────────────
#  1. DDG fallback — no Tavily key → live DDG results returned
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_tavily_search_no_key_uses_ddg_fallback(monkeypatch):
    """When TAVILY_API_KEY is absent, tavily_search() MUST call DDG and return
    real-looking results, NOT the old static Paris weather mock string."""
    monkeypatch.setattr("app.tools.local_tools.settings.TAVILY_API_KEY", None)
    monkeypatch.setattr("app.services.web_search.settings.TAVILY_API_KEY", None)
    monkeypatch.setattr("app.services.web_search.settings.SERP_API_KEY", None)
    monkeypatch.setattr("app.services.web_search.settings.EXA_API_KEY", None)

    fake_ddg_result = [
        SearchResult(
            title="India News - Minister Update",
            url="https://example.com/india-news",
            snippet="Latest updates on Indian cabinet ministers.",
            source="duckduckgo"
        )
    ]

    mock_cache = MagicMock()
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock(return_value=None)
    monkeypatch.setattr("app.tools.local_tools.web_search_cache", mock_cache)

    with patch(
        "app.services.web_search.search_duckduckgo",
        new=AsyncMock(return_value=fake_ddg_result),
    ) as mock_ddg:
        result = await tavily_search("current news of India")
        mock_ddg.assert_called_once()

    assert "Paris weather" not in result
    assert "India News" in result or "Source" in result or "Web Search Results" in result


@pytest.mark.anyio
async def test_tavily_search_mock_key_uses_ddg_fallback(monkeypatch):
    """When TAVILY_API_KEY is a mock key, DDG fallback is used."""
    monkeypatch.setattr("app.tools.local_tools.settings.TAVILY_API_KEY", "mock_key_123")
    monkeypatch.setattr("app.services.web_search.settings.TAVILY_API_KEY", "mock_key_123")
    monkeypatch.setattr("app.services.web_search.settings.SERP_API_KEY", None)
    monkeypatch.setattr("app.services.web_search.settings.EXA_API_KEY", None)

    fake_ddg_result = [
        SearchResult(
            title="India minister resignation",
            url="https://example.com/news",
            snippet="DDG: India news results",
            source="duckduckgo"
        )
    ]

    mock_cache = MagicMock()
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock(return_value=None)
    monkeypatch.setattr("app.tools.local_tools.web_search_cache", mock_cache)

    with patch(
        "app.services.web_search.search_duckduckgo",
        new=AsyncMock(return_value=fake_ddg_result),
    ) as mock_ddg:
        result = await tavily_search("India minister resignation")
        mock_ddg.assert_called_once()

    assert "Paris weather" not in result
    assert "India" in result


@pytest.mark.anyio
async def test_tavily_search_http_error_falls_back_to_ddg(monkeypatch):
    """When Tavily returns HTTP 429/500, DDG fallback is used automatically."""
    monkeypatch.setattr("app.tools.local_tools.settings.TAVILY_API_KEY", "real_looking_key_abc")
    monkeypatch.setattr("app.services.web_search.settings.TAVILY_API_KEY", "real_looking_key_abc")
    monkeypatch.setattr("app.services.web_search.settings.SERP_API_KEY", None)
    monkeypatch.setattr("app.services.web_search.settings.EXA_API_KEY", None)

    fake_ddg_result = [
        SearchResult(
            title="DDG fallback result",
            url="https://example.com",
            snippet="DDG fallback result for rate-limited query",
            source="duckduckgo"
        )
    ]

    mock_cache = MagicMock()
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock(return_value=None)
    monkeypatch.setattr("app.tools.local_tools.web_search_cache", mock_cache)

    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.text = "Rate limit exceeded"

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        with patch(
            "app.services.web_search.search_duckduckgo",
            new=AsyncMock(return_value=fake_ddg_result),
        ) as mock_ddg:
            result = await tavily_search("India news today")
            mock_ddg.assert_called_once()

    assert "Paris weather" not in result
    assert "DDG fallback" in result or "India" in result or "Web Search Results" in result


@pytest.mark.anyio
async def test_tavily_search_exception_falls_back_to_ddg(monkeypatch):
    """When Tavily raises a network exception, DDG fallback is used."""
    monkeypatch.setattr("app.tools.local_tools.settings.TAVILY_API_KEY", "real_key")
    monkeypatch.setattr("app.services.web_search.settings.TAVILY_API_KEY", "real_key")
    monkeypatch.setattr("app.services.web_search.settings.SERP_API_KEY", None)
    monkeypatch.setattr("app.services.web_search.settings.EXA_API_KEY", None)

    fake_ddg_result = [
        SearchResult(
            title="DDG offline fallback",
            url="https://example.com",
            snippet="DDG offline fallback snippet",
            source="duckduckgo"
        )
    ]

    mock_cache = MagicMock()
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock(return_value=None)
    monkeypatch.setattr("app.tools.local_tools.web_search_cache", mock_cache)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=ConnectionError("Network unreachable"))
        mock_client_cls.return_value = mock_client

        with patch(
            "app.services.web_search.search_duckduckgo",
            new=AsyncMock(return_value=fake_ddg_result),
        ) as mock_ddg:
            result = await tavily_search("current India news")
            mock_ddg.assert_called_once()

    assert "DDG offline fallback" in result


# ─────────────────────────────────────────────────────────────────────────────
#  2. Cache hit — DDG / Tavily should NOT be called when cache is warm
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_tavily_search_cache_hit_skips_network(monkeypatch):
    """A warm cache should be returned immediately without any network calls."""
    cached_value = "Cached India news result"

    mock_cache = MagicMock()
    mock_cache.get = AsyncMock(return_value=cached_value)
    mock_cache.set = AsyncMock(return_value=None)
    monkeypatch.setattr("app.tools.local_tools.web_search_cache", mock_cache)

    with patch("app.tools.local_tools._ddg_search_fallback") as mock_ddg, \
         patch("httpx.AsyncClient") as mock_http:
        result = await tavily_search("India news")
        mock_ddg.assert_not_called()
        mock_http.assert_not_called()

    assert result == cached_value


# ─────────────────────────────────────────────────────────────────────────────
#  3. Intent classification — news & resignation queries → WEB_SEARCH
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_classify_intent_news_query_routes_to_web_search(monkeypatch):
    """'Tell me the current news of INDIA' must classify as INTENT_WEB_SEARCH."""
    from app.agent.nodes import classify_intent_node
    from app.agent.prompts import INTENT_WEB_SEARCH

    # Patch LLM judge to return WEB_SEARCH
    with patch("app.agent.nodes._call_llm_judge", new=AsyncMock(return_value={
        "intent": "WEB_SEARCH",
        "is_private_doc_query": False,
        "is_ambiguous": False,
    })), patch("app.agent.nodes._call_llm_text", new=AsyncMock(return_value=None)):
        state = _make_state(
            messages=[HumanMessage(content="Tell me the current news of INDIA")],
        )
        result = await classify_intent_node(state, config={})

    assert result["intent"] == INTENT_WEB_SEARCH, (
        f"Expected INTENT_WEB_SEARCH, got '{result['intent']}'"
    )
    assert "tavily_search" in result.get("allowed_tools", []), (
        "tavily_search must be in allowed_tools for WEB_SEARCH intent"
    )


@pytest.mark.anyio
async def test_classify_intent_resignation_query_routes_to_web_search(monkeypatch):
    """'Any news related to the resignation of serving ministers?' → WEB_SEARCH.
    
    The LLM judge is the primary classifier in the new LLM-first design.
    This test mocks the LLM to return WEB_SEARCH (as it would in production)
    and verifies the pipeline correctly routes to WEB_SEARCH.
    """
    from app.agent.nodes import classify_intent_node

    with patch("app.agent.nodes._call_llm_judge", new=AsyncMock(return_value={
        "intent": "WEB_SEARCH",
        "is_private_doc_query": False,
        "memory_content": None,
        "memory_category": None,
    })), patch("app.agent.nodes._call_llm_text", new=AsyncMock(return_value=None)):
        state = _make_state(
            messages=[HumanMessage(
                content="Any news related to the resignation of any current serving ministers?"
            )],
        )
        result = await classify_intent_node(state, config={})

    assert result["intent"] == INTENT_WEB_SEARCH, (
        f"LLM-first classification should route 'resignation'+'news' → WEB_SEARCH, got '{result['intent']}'"
    )


@pytest.mark.anyio
async def test_classify_intent_minister_keyword_routes_to_web_search(monkeypatch):
    """Queries about current officials route to WEB_SEARCH via LLM-first classification."""
    from app.agent.nodes import classify_intent_node

    with patch("app.agent.nodes._call_llm_judge", new=AsyncMock(return_value={
        "intent": "WEB_SEARCH",
        "is_private_doc_query": False,
        "memory_content": None,
        "memory_category": None,
    })), patch("app.agent.nodes._call_llm_text", new=AsyncMock(return_value=None)):
        state = _make_state(
            messages=[HumanMessage(content="Who is the education minister of India?")],
        )
        result = await classify_intent_node(state, config={})

    assert result["intent"] == INTENT_WEB_SEARCH


# ─────────────────────────────────────────────────────────────────────────────
#  4. grade_documents_node — WEB_SEARCH intent triggers web fallback
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_grade_documents_triggers_web_search_for_web_intent(monkeypatch):
    """grade_documents_node must call unified_web_search for INTENT_WEB_SEARCH
    even when the vector DB returns zero chunks (early-exit path fixed)."""
    from app.agent.nodes import grade_documents_node

    fake_doc = SearchResult(title="India news today", url="https://news.example.com", snippet="India news today", source="tavily", score=1.0)

    with patch("app.agent.nodes.unified_web_search", new=AsyncMock(return_value=[fake_doc])) as mock_ws, \
         patch("app.agent.nodes._call_llm_judge", new=AsyncMock(return_value=None)):
        state = _make_state(
            intent=INTENT_WEB_SEARCH,
            resolved_query="current news of India",
            retrieved_documents=[],  # Empty vector DB — forces early-exit web fallback
            messages=[HumanMessage(content="current news of India")],
        )
        result = await grade_documents_node(state, config={})
        mock_ws.assert_called_once_with("current news of India", {})

    # Web results should be injected into retrieved documents
    assert result.get("document_relevance") == "web_fallback", (
        f"Expected 'web_fallback', got '{result.get('document_relevance')}'"
    )


# ─────────────────────────────────────────────────────────────────────────────
#  5. Sycophancy guard — false claims not hallucinated
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_false_breaking_news_claim_not_in_web_results(monkeypatch):
    """When web search returns results that do NOT mention the user's claim
    about a minister resigning, the verified_response must NOT confirm the claim."""
    from app.agent.nodes import evidence_checker_node

    # Web search returned real results that don't mention the resignation
    web_search_result = {
        "type": "chunk",
        "content": "Indian cabinet is stable. No minister resignations reported. PM Modi held cabinet meeting.",
        "filename": "Web Search Results",
        "distance": 0.0,
    }

    hallucinated_response = (
        "Breaking News: As of today, Dharmendra Pradhan, the Education Minister of India, "
        "has resigned from his position amidst NEET paper leak protests."
    )

    with patch("app.agent.nodes._call_llm_judge", new=AsyncMock(return_value={
        "verdict": "NEEDS_CORRECTION",
        "confidence": 0.3,
        "hallucination_risk": "high",
        "unsupported_claims": ["Dharmendra Pradhan resigned"],
        "corrected_answer": (
            "I searched live news sources but could not find any verified report of this event. "
            "I cannot confirm this claim. Please check a trusted news source directly."
        ),
    })):
        state = _make_state(
            intent=INTENT_WEB_SEARCH,
            resolved_query="Dharmendra Pradhan resigned today",
            retrieved_documents=[web_search_result],
            messages=[
                HumanMessage(content="Dharmendra Pradhan resigned today"),
                AIMessage(content=hallucinated_response),
            ],
        )
        result = await evidence_checker_node(state, config={})

    verified = result.get("verified_response", "")
    assert "Breaking News" not in verified, (
        "Hallucinated 'Breaking News' should have been corrected by evidence_checker"
    )
    assert result.get("has_hallucination_risk") is True
    assert result.get("unsupported_claims_count", 0) > 0


@pytest.mark.anyio
async def test_ddg_fallback_returns_live_results_structure():
    """_ddg_search_fallback must return structured results (not empty, not error)
    for a basic real-world news query using mocked DDG (no live network calls)."""
    from app.services.web_search import SearchResult

    fake_results = [
        SearchResult(title="India News Today", url="https://example.com/news", snippet="Top headlines from India.", source="duckduckgo"),
        SearchResult(title="Cabinet Update", url="https://example.com/cabinet", snippet="No resignations reported.", source="duckduckgo"),
    ]

    with patch("app.services.web_search.search_duckduckgo", new=AsyncMock(return_value=fake_results)):
        result = await _ddg_search_fallback("India news")

    assert result  # non-empty
    assert "India News Today" in result or "Cabinet Update" in result
    assert "Paris weather" not in result
