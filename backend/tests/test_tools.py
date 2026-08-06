import sys
import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from app.tools.local_tools import python_sandbox, tavily_search
from app.tools.mcp_client import McpStdioClient
from app.tools.registry import ToolRegistry
from app.agent.graph import agent_graph
from langchain_core.messages import HumanMessage

@pytest.mark.anyio
async def test_python_sandbox_executor():
    """
    Verify that the Python executor sandbox runs code successfully and handles timeouts.
    """
    # Success case
    code = "print(10 + 20)"
    result = await python_sandbox(code)
    assert result == "30"

    # Timeout case
    timeout_code = "import time\ntime.sleep(20)\nprint('done')"
    timeout_result = await python_sandbox(timeout_code)
    assert "Timeout" in timeout_result

@pytest.mark.anyio
async def test_tavily_search_mock(monkeypatch):
    """
    Verify web search returns content results.
    """
    from unittest.mock import patch, AsyncMock
    from app.services.web_search import SearchResult
    monkeypatch.setattr("app.tools.local_tools.settings.TAVILY_API_KEY", "mock_key")
    fake_res = [SearchResult(title="FastAPI Best Practices", url="https://example.com", snippet="FastAPI tips", source="duckduckgo")]
    with patch("app.services.web_search.search_duckduckgo", new=AsyncMock(return_value=fake_res)):
        result = await tavily_search("fastapi best practices")
    assert any(k in result for k in ("Result", "FastAPI", "DuckDuckGo", "Search", "Source"))

@pytest.mark.anyio
async def test_mcp_client_and_calculator_server():
    """
    Verify that our custom Stdio MCP client can spawn our calculator server,
    perform the handshake, query tools, execute math, and terminate cleanly.
    """
    import os
    current_dir = os.path.dirname(os.path.abspath(__file__))
    calculator_script = os.path.join(current_dir, "..", "app", "tools", "mcp_calculator_server.py")
    python_exe = sys.executable or "python"

    client = McpStdioClient(command=python_exe, args=[calculator_script])
    await client.connect()

    # 1. List tools — 7 tools (calculate + add_expense + get_expenses + summarize_expenses + create_reminder + get_reminders + send_email)
    tools = await client.list_tools()
    tool_names = [t["name"] for t in tools]
    assert len(tools) == 7
    assert "calculate" in tool_names
    assert "add_expense" in tool_names
    assert "get_expenses" in tool_names
    assert "summarize_expenses" in tool_names
    assert "create_reminder" in tool_names
    assert "get_reminders" in tool_names
    assert "send_email" in tool_names

    # 2. Call tool calculate
    result = await client.call_tool("calculate", {"expression": "12 * 12"})
    assert result == "144"

    # 3. Call tool with sin
    result_sin = await client.call_tool("calculate", {"expression": "sin(pi/2)"})
    assert abs(float(result_sin) - 1.0) < 0.01

    # 4. Test add_expense
    result_exp = await client.call_tool("add_expense", {"amount": 500, "description": "lunch", "category": "food"})
    assert "Added expense" in result_exp or "Successfully added" in result_exp

    # 5. Test get_expenses & summarize_expenses
    result_get = await client.call_tool("get_expenses", {"category": "food"})
    assert "lunch" in result_get or "food" in result_get.lower()

    result_sum = await client.call_tool("summarize_expenses", {})
    assert "Expense Summary" in result_sum

    # 6. Test create_reminder
    result_rem = await client.call_tool("create_reminder", {"time": "tomorrow 10 AM", "text": "Meeting"})
    assert "Successfully created" in result_rem or "Reminder set" in result_rem

    # 7. Test send_email
    result_email = await client.call_tool("send_email", {"to": "test@example.com", "subject": "Test", "body": "Test body"})
    assert "Successfully sent" in result_email or "Email sent" in result_email

    # 8. Clean up subprocess
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

    # Route local execution
    res_py = await registry.call_tool("python_sandbox", {"code": "print(12345)"})
    assert res_py == "12345"

    # Route MCP execution
    res_mcp = await registry.call_tool("calculate", {"expression": "3 * 3 * 3"})
    assert res_mcp == "27"

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
        "active_model":          "gemini-3.5-flash",
        "user_id":               "test-user",
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

