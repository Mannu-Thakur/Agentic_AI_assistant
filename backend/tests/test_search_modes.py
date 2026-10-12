import pytest
from unittest.mock import patch, AsyncMock
from langchain_core.messages import HumanMessage
from app.agent.nodes import classify_intent_node
from app.agent.graph import route_after_classify
from app.agent.prompts import INTENT_WEB_SEARCH, INTENT_DOCUMENT_QA, INTENT_COMPLEX

def _make_state(**overrides) -> dict:
    base = {
        "messages": [HumanMessage(content="Hello world")],
        "steps": [],
        "execution_trace": [],
        "memory_status": {},
        "semantic_status": {},
        "web_status": {},
        "retrieved_documents": [],
        "inconsistencies": [],
        "images": None,
        "is_ambiguous": False,
        "clarification_question": None,
        "resolved_query": None,
        "original_query": None,
        "search_mode": None,
    }
    base.update(overrides)
    return base

def _make_config() -> dict:
    return {
        "configurable": {
            "user_id": "test-user",
            "chat_id": "test-chat",
            "memories": [],
            "gemini_api_key": "mock-key",
            "groq_api_key": "mock-key",
            "openrouter_api_key": "mock-key",
        }
    }

@pytest.mark.anyio
async def test_search_mode_web_override():
    """search_mode='web' must force INTENT_WEB_SEARCH and route to execute_web_search."""
    state = _make_state(search_mode="web")
    with patch("app.agent.nodes._call_llm_judge", new_callable=AsyncMock) as mock_judge:
        mock_judge.return_value = {"intent": "NORMAL_CHAT"}
        result = await classify_intent_node(state, _make_config())
    
    assert result["intent"] == INTENT_WEB_SEARCH
    assert result["is_private_doc_query"] is False
    assert route_after_classify(result) == "execute_web_search"

@pytest.mark.anyio
async def test_search_mode_kb_override():
    """search_mode='kb' must force INTENT_DOCUMENT_QA and route to check_retrieval."""
    state = _make_state(search_mode="kb")
    with patch("app.agent.nodes._call_llm_judge", new_callable=AsyncMock) as mock_judge:
        mock_judge.return_value = {"intent": "NORMAL_CHAT"}
        result = await classify_intent_node(state, _make_config())
    
    assert result["intent"] == INTENT_DOCUMENT_QA
    assert result["is_private_doc_query"] is True
    assert route_after_classify(result) == "check_retrieval"

@pytest.mark.anyio
async def test_search_mode_hybrid_override():
    """search_mode='hybrid' must force INTENT_COMPLEX and route to planner."""
    state = _make_state(search_mode="hybrid")
    with patch("app.agent.nodes._call_llm_judge", new_callable=AsyncMock) as mock_judge:
        mock_judge.return_value = {"intent": "NORMAL_CHAT"}
        result = await classify_intent_node(state, _make_config())
    
    assert result["intent"] == INTENT_COMPLEX
    assert result["is_private_doc_query"] is True
    assert route_after_classify(result) == "planner"

@pytest.mark.anyio
async def test_search_mode_deep_research_override():
    """search_mode='deep_research' must force INTENT_COMPLEX and route to planner."""
    state = _make_state(search_mode="deep_research")
    with patch("app.agent.nodes._call_llm_judge", new_callable=AsyncMock) as mock_judge:
        mock_judge.return_value = {"intent": "NORMAL_CHAT"}
        result = await classify_intent_node(state, _make_config())
    
    assert result["intent"] == INTENT_COMPLEX
    assert route_after_classify(result) == "planner"

@pytest.mark.anyio
async def test_search_mode_cache_override():
    """search_mode='cache' must set needs_retrieval=False and route to check_retrieval."""
    state = _make_state(search_mode="cache")
    with patch("app.agent.nodes._call_llm_judge", new_callable=AsyncMock) as mock_judge:
        mock_judge.return_value = {"intent": "NORMAL_CHAT"}
        result = await classify_intent_node(state, _make_config())
    
    assert result["needs_retrieval"] is False
    assert route_after_classify(result) == "check_retrieval"

@pytest.mark.anyio
async def test_search_mode_auto():
    """search_mode='auto' or None must use standard intent classification."""
    state = _make_state(search_mode="auto")
    with patch("app.agent.nodes._call_llm_judge", new_callable=AsyncMock) as mock_judge:
        mock_judge.return_value = {"intent": "NORMAL_CHAT"}
        result = await classify_intent_node(state, _make_config())
    
    assert result["intent"] == "NORMAL_CHAT"
    assert route_after_classify(result) == "check_retrieval"
