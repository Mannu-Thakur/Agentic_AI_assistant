import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from app.tools.local_tools import python_sandbox, tavily_search
from app.tools.mcp_client import McpStdioClient
from app.tools.registry import ToolRegistry
from app.agent.graph import agent_graph
from app.core.config import settings
from langchain_core.messages import HumanMessage

@pytest.mark.anyio
async def test_python_sandbox_executor(monkeypatch):
    """
    Verify code execution fails closed unless the isolated service is configured.
    """
    from app.tools.local_tools import settings

    monkeypatch.setattr(settings, "ENABLE_CODE_EXECUTION", False)
    disabled = await python_sandbox("print(10 + 20)")
    assert "not enabled" in disabled
    assert "not executed" in disabled

    monkeypatch.setattr(settings, "ENABLE_CODE_EXECUTION", True)
    monkeypatch.setattr(settings, "CODE_SANDBOX_URL", "https://sandbox.internal")
    monkeypatch.setattr(settings, "SANDBOX_SHARED_SECRET", "test-only-secret")
    captured = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"output": "30", "exit_code": 0}

    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, *, json, headers):
            captured.update(url=url, json=json, headers=headers)
            return FakeResponse()

    with patch("httpx.AsyncClient", FakeAsyncClient):
        result = await python_sandbox("print(10 + 20)")
    assert result == "30"
    assert captured["url"] == "https://sandbox.internal/execute"
    assert captured["json"] == {"code": "print(10 + 20)"}
    assert captured["headers"]["X-Sandbox-Token"] == "test-only-secret"

@pytest.mark.anyio
async def test_tavily_search_mock(monkeypatch):
    """
    Verify web search returns content results.
    """
    from unittest.mock import patch, AsyncMock
    from app.services.web_search import SearchResult
    monkeypatch.setattr("app.tools.local_tools.settings.TAVILY_API_KEY", "mock_key")
    fake_res = [SearchResult(title="FastAPI Best Practices", url="https://example.com", snippet="FastAPI tips", source="duckduckgo")]
    with patch("app.services.web_search.search_duckduckgo", new=AsyncMock(return_value=fake_res)), \
         patch("app.tools.local_tools.web_search_cache.get", new=AsyncMock(return_value=None)):
        result = await tavily_search("fastapi best practices")
    assert any(k in result for k in ("Result", "FastAPI", "DuckDuckGo", "Search", "Source"))

@pytest.mark.anyio
async def test_mcp_client_and_calculator_server():
    """
    Verify the public deployment never launches a local stdio MCP process.
    """
    client = McpStdioClient(command="python", args=["must-not-run.py"])
    with pytest.raises(RuntimeError, match="disabled in the public deployment"):
        await client.connect()
    await client.close()

@pytest.mark.anyio
async def test_tool_registry():
    """
    Verify registry initialization, tool schema format, and routing execution.
    """
    registry = ToolRegistry()
    await registry.initialize()

    # Schemas
    schemas = registry.get_tool_schemas()
    names = [s["name"] for s in schemas]
    assert "tavily_search" in names
    assert "python_sandbox" in names
    assert "calculate" in names

    # The tool stays visible, but fails closed until the isolated sandbox is configured.
    res_py = await registry.call_tool("python_sandbox", {"code": "print(12345)"})
    assert "not enabled" in res_py
    assert "not executed" in res_py

    # Route MCP execution
    res_mcp = await registry.call_tool("calculate", {"expression": "3 * 3 * 3"})
    assert res_mcp == "27"

    with patch("app.tools.registry.metrics_collector") as metrics:
        metrics.record_tool_call = MagicMock()
        failure = await registry.call_tool("calculate", {"expression": "1 / 0"})
        assert failure.startswith("Calculation failed:")
        metrics.record_tool_call.assert_called_with("calculate", "error")

    await registry.shutdown()

@pytest.mark.anyio
async def test_agent_graph_tool_calling_loop():
    """
    Verify that the LangGraph agent graph correctly executes tool-calling loops
    when prompted with a query requiring tool execution (using mock adapter rules).
    The state must supply intent=MCP_TOOL and allowed_tools=['calculate'] so the
    calculator tool schema is offered to the LLM.
    """
    initial_state = {
        "messages":              [HumanMessage(content="calculate 8 * 8")],
        "active_model":          settings.GEMINI_MODEL,
        # This test targets the tool loop; retrieval would send its fake key to
        # the embedding API and exercise an unrelated external dependency.
        "user_id":               None,
        "chat_id":               "test-chat",
        "retrieved_documents":   [],
        "metrics":               {},
        "response_text":         "",
        "tool_calls":            [],
        # Intent gating: supply MCP_TOOL intent so calculate is whitelisted
        "intent":                "MCP_TOOL",
        "allowed_tools":         ["calculate"],
        "is_private_doc_query":  False,
        "no_doc_answer":         False,
        "memory_write_content":  None,
        "memory_write_category": None,
        "uploaded_file_paths":   [],
    }

    config = {
        "configurable": {
            "user_id": "test-user",
            "chat_id": "test-chat",
            "gemini_api_key": "AIzaSyFakeKeyForTest1234567890",
        }
    }

    # Initialize registry
    registry = ToolRegistry()
    await registry.initialize()

    # Mock provider streaming response to simulate tool call on first call and final answer on second call
    call_count = 0

    async def mock_generate_stream(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            yield {"event": "tool_calls", "tool_calls": [{"name": "calculate", "args": {"expression": "8 * 8"}}]}
        else:
            yield {"event": "chunk", "text": "The calculated result is 64."}
            yield {"event": "done"}

    with patch("app.agent.nodes._call_llm_judge", new=AsyncMock(return_value={"intent": "MCP_TOOL"})):
        with patch("app.agent.nodes.gemini_provider.generate_stream", side_effect=mock_generate_stream):
            # Execute graph
            final_state = await agent_graph.ainvoke(initial_state, config)

    # The agent should have loop-routed, executed the tool calculation,
    # and produced the final response in its history.
    messages = final_state.get("messages", [])

    # Assert tool output message is in history (neutral label, no internal name)
    assert any("[Tool Result]" in msg.content for msg in messages), (
        "Expected a [Tool Result] message in history after tool execution.\n"
        f"Messages were: {[m.content for m in messages]}"
    )
    # Assert the result 64 appears somewhere in the conversation
    all_content = " ".join(
        m.content for m in messages if isinstance(m.content, str)
    )
    assert "64" in all_content, (
        f"Expected '64' (8*8) to appear in conversation. Got: {all_content[:500]}"
    )

    await registry.shutdown()

