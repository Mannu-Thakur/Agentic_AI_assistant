"""
tests/test_entity_search_followup.py

Targeted tests for the entity search follow-up / constraint-merging fix.

Tests verify:
1. classify_intent_node detects entity search follow-up correctly
2. entity_search_task is populated and constraints accumulated
3. intent is forced to WEB_SEARCH for constraint refinements
4. execute_web_search_node uses entity context to rewrite query
5. No hardcoded entity data — all detection is from conversation context
6. Bare constraint message is NOT treated as independent query
"""

import pytest
from unittest.mock import AsyncMock, patch
from langchain_core.messages import HumanMessage, AIMessage

from app.agent.prompts import INTENT_WEB_SEARCH, INTENT_NORMAL_CHAT


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
        "original_query": "",
        "sub_questions": [],
        "entity_search_task": None,
        "execution_trace": [],
        "semantic_status": {},
        "memory_status": {},
        "web_status": {},
        "inconsistencies": [],
        "images": [],
        "is_ambiguous": False,
        "clarification_question": None,
        "retrieval_retry_count": 0,
        "max_retrieval_retries": 2,
        "retrieval_confidence": 1.0,
        "language_mode": None,
        "detected_language": None,
    }
    base.update(kwargs)
    return base


# ─────────────────────────────────────────────────────────────────────────────
#  1. classify_intent_node: entity follow-up detection
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_classify_detects_entity_followup_and_forces_web_search():
    """
    When Turn 1 fetched a person and Turn 2 adds a constraint,
    classify_intent_node MUST:
    - Detect it as a follow-up refinement
    - Force intent to WEB_SEARCH
    - Populate entity_search_task with entity + constraints
    """
    from app.agent.nodes import classify_intent_node

    turn1_user = HumanMessage(content="fetch Mannu kumar thakur linkedin")
    turn1_ai = AIMessage(content="Here is the LinkedIn profile I found: [Wrong Person from Kolkata]...")
    turn2_user = HumanMessage(content="Education must be BTech from IIT Bhubaneswar")

    # LLM judge: entity follow-up
    followup_result = {
        "is_followup_refinement": True,
        "entity": "Mannu Kumar Thakur",
        "platform": "LinkedIn",
        "constraints": ["BTech", "IIT Bhubaneswar"],
        "rejected_description": "Person from Kolkata at PN Singh Degree College",
    }
    # Intent classifier: for the bare constraint text it might say NORMAL_CHAT
    intent_result = {
        "intent": "NORMAL_CHAT",
        "is_private_doc_query": False,
        "memory_content": None,
        "memory_category": None,
        "detected_language": "English",
        "tool_hints": [],
    }

    call_count = {"judge": 0}

    async def mock_judge(prompt: str, config: dict):
        call_count["judge"] += 1
        # First call is entity follow-up detection, subsequent calls are intent/ambiguity
        if "is_followup_refinement" in prompt or "ENTITY/PERSON SEARCH" in prompt:
            return followup_result
        return intent_result

    with patch("app.agent.nodes._call_llm_judge", new=mock_judge), \
         patch("app.agent.nodes._call_llm_text", new=AsyncMock(return_value=None)):

        state = _make_state(
            messages=[turn1_user, turn1_ai, turn2_user],
        )
        result = await classify_intent_node(state, config={})

    # Intent MUST be WEB_SEARCH (forced by follow-up detection)
    assert result["intent"] == INTENT_WEB_SEARCH, (
        f"Expected INTENT_WEB_SEARCH, got '{result['intent']}' — "
        f"follow-up constraint was not recognized as entity search refinement"
    )

    # entity_search_task MUST be populated
    est = result.get("entity_search_task")
    assert est is not None, "entity_search_task must be set after follow-up detection"
    assert est.get("entity") == "Mannu Kumar Thakur", (
        f"Expected entity='Mannu Kumar Thakur', got '{est.get('entity')}'"
    )
    assert "BTech" in est.get("constraints", []) or "IIT Bhubaneswar" in " ".join(est.get("constraints", [])), (
        f"BTech or IIT Bhubaneswar constraint not found in {est.get('constraints')}"
    )
    assert est.get("platform") == "LinkedIn"


@pytest.mark.anyio
async def test_classify_no_followup_for_independent_query():
    """
    When there is no prior entity search, a WEB_SEARCH query
    should NOT be treated as a follow-up.
    """
    from app.agent.nodes import classify_intent_node

    state = _make_state(
        messages=[HumanMessage(content="What is the capital of France?")],
    )

    followup_result = {
        "is_followup_refinement": False,
        "entity": None,
        "platform": None,
        "constraints": [],
        "rejected_description": None,
    }
    intent_result = {
        "intent": "WEB_SEARCH",
        "is_private_doc_query": False,
        "memory_content": None,
        "memory_category": None,
        "detected_language": "English",
        "tool_hints": [],
    }

    async def mock_judge(prompt: str, config: dict):
        if "is_followup_refinement" in prompt or "ENTITY/PERSON SEARCH" in prompt:
            return followup_result
        return intent_result

    with patch("app.agent.nodes._call_llm_judge", new=mock_judge), \
         patch("app.agent.nodes._call_llm_text", new=AsyncMock(return_value=None)):
        result = await classify_intent_node(state, config={})

    # Should be WEB_SEARCH but with empty entity_search_task (fresh init)
    assert result["intent"] == INTENT_WEB_SEARCH
    est = result.get("entity_search_task")
    # entity_search_task may be initialized with entity=None for first WEB_SEARCH
    if est is not None:
        assert est.get("entity") is None, (
            "Independent query should not populate entity in entity_search_task"
        )


# ─────────────────────────────────────────────────────────────────────────────
#  2. execute_web_search_node: entity query rewriting
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_execute_web_search_rewrites_query_with_entity_constraints():
    """
    When entity_search_task has entity + constraints,
    execute_web_search_node MUST rewrite the query to incorporate them
    rather than using the bare last-message text as the search query.
    """
    from app.agent.nodes import execute_web_search_node
    from app.services.web_search import SearchResult

    # Simulated entity search task from a prior follow-up detection
    entity_task = {
        "entity": "Mannu Kumar Thakur",
        "platform": "LinkedIn",
        "constraints": ["BTech", "IIT Bhubaneswar"],
        "rejected_description": "Person from Kolkata, PN Singh Degree College",
        "last_query": None,
    }

    # The last user message is the bare constraint (which makes a terrible query alone)
    bare_constraint_text = "Education must be BTech from IIT Bhubaneswar"

    # Fake search results
    fake_results = [
        SearchResult(
            title="Mannu Kumar Thakur - LinkedIn",
            url="https://linkedin.com/in/mannu-kumar-thakur-iit",
            snippet="BTech from IIT Bhubaneswar. Software Engineer.",
            source="tavily",
            score=0.95,
        )
    ]

    captured_queries = []

    async def mock_unified_search(query: str, api_keys: dict, **kwargs):
        captured_queries.append(query)
        return fake_results

    # LLM text call returns the optimized query
    async def mock_text(prompt: str, config: dict, max_tokens: int = 256):
        if "search query" in prompt.lower() or "entity to search" in prompt.lower():
            return "Mannu Kumar Thakur BTech IIT Bhubaneswar LinkedIn"
        return None

    state = _make_state(
        messages=[HumanMessage(content=bare_constraint_text)],
        resolved_query=bare_constraint_text,
        entity_search_task=entity_task,
        intent=INTENT_WEB_SEARCH,
    )

    with patch("app.agent.nodes.unified_web_search", new=mock_unified_search), \
         patch("app.agent.nodes._call_llm_text", new=mock_text):
        result = await execute_web_search_node(state, config={"configurable": {"api_keys": {}}})

    # The query used MUST contain entity context, NOT just the bare constraint
    assert len(captured_queries) >= 1, "unified_web_search must have been called"
    actual_query = captured_queries[0]

    assert bare_constraint_text not in actual_query or "Mannu" in actual_query, (
        f"Expected rewritten entity query, but got bare constraint: '{actual_query}'"
    )
    assert "IIT Bhubaneswar" in actual_query or "Mannu" in actual_query, (
        f"Rewritten query should contain entity or constraint context, got: '{actual_query}'"
    )

    # entity_search_task.last_query should be updated
    updated_task = result.get("entity_search_task")
    assert updated_task is not None
    assert updated_task.get("last_query") is not None, "last_query must be set after search"


@pytest.mark.anyio
async def test_execute_web_search_uses_normal_query_without_entity_task():
    """
    When there is no entity_search_task, execute_web_search_node
    should use the normal resolved_query without any rewriting.
    """
    from app.agent.nodes import execute_web_search_node
    from app.services.web_search import SearchResult

    captured_queries = []

    async def mock_unified_search(query: str, api_keys: dict, **kwargs):
        captured_queries.append(query)
        return [SearchResult(title="Result", url="https://example.com", snippet="Result", source="tavily")]

    state = _make_state(
        messages=[HumanMessage(content="What is the capital of France?")],
        resolved_query="What is the capital of France?",
        entity_search_task=None,
        intent=INTENT_WEB_SEARCH,
    )

    with patch("app.agent.nodes.unified_web_search", new=mock_unified_search), \
         patch("app.agent.nodes._call_llm_text", new=AsyncMock(return_value=None)):
        result = await execute_web_search_node(state, config={"configurable": {"api_keys": {}}})

    assert captured_queries[0] == "What is the capital of France?"


# ─────────────────────────────────────────────────────────────────────────────
#  3. No hardcoded entity data — all from conversation context
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_entity_detection_uses_no_hardcoded_names():
    """
    The entity search task detection must work for ANY entity name,
    not just 'Mannu Kumar Thakur'. Validates generalization.
    """
    from app.agent.nodes import classify_intent_node

    # Completely different entity
    turn1 = HumanMessage(content="find John Smith github profile")
    turn1_ai = AIMessage(content="I found a John Smith who is a data scientist...")
    turn2 = HumanMessage(content="He should work at Google, not a data scientist")

    followup_result = {
        "is_followup_refinement": True,
        "entity": "John Smith",
        "platform": "GitHub",
        "constraints": ["works at Google"],
        "rejected_description": "Data scientist John Smith",
    }
    intent_result = {
        "intent": "NORMAL_CHAT",
        "is_private_doc_query": False,
        "memory_content": None,
        "memory_category": None,
        "detected_language": "English",
        "tool_hints": [],
    }

    async def mock_judge(prompt: str, config: dict):
        if "is_followup_refinement" in prompt or "ENTITY/PERSON SEARCH" in prompt:
            return followup_result
        return intent_result

    with patch("app.agent.nodes._call_llm_judge", new=mock_judge), \
         patch("app.agent.nodes._call_llm_text", new=AsyncMock(return_value=None)):
        state = _make_state(messages=[turn1, turn1_ai, turn2])
        result = await classify_intent_node(state, config={})

    assert result["intent"] == INTENT_WEB_SEARCH
    est = result.get("entity_search_task")
    assert est is not None
    assert est.get("entity") == "John Smith"
    assert "GitHub" == est.get("platform")
