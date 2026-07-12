import sys
import pytest
import asyncio
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
async def test_tavily_search_mock():
    """
    Verify web search returns content results.
    """
    result = await tavily_search("fastapi best practices")
    assert "Result" in result or "FastAPI" in result

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

    # 1. List tools
    tools = await client.list_tools()
    assert len(tools) == 1
    assert tools[0]["name"] == "calculate"

    # 2. Call tool calculate
    result = await client.call_tool("calculate", {"expression": "12 * 12"})
    assert result == "144"

    # 3. Call tool with sin
    result_sin = await client.call_tool("calculate", {"expression": "sin(pi/2)"})
    assert abs(float(result_sin) - 1.0) < 0.01

    # 4. Clean up subprocess
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
    """
    initial_state = {
        "messages": [HumanMessage(content="calculate 8 * 8")],
        "active_model": "gemini-1.5-flash",
        "user_id": "test-user",
        "chat_id": "test-chat",
        "retrieved_documents": [],
        "metrics": {},
        "response_text": "",
        "tool_calls": []
    }

    config = {
        "configurable": {
            "user_id": "test-user",
            "chat_id": "test-chat"
        }
    }

    # Initialize registry
    registry = ToolRegistry()
    await registry.initialize()

    # Execute graph
    final_state = await agent_graph.ainvoke(initial_state, config)

    # The agent should have loop-routed, executed the tool calculation,
    # and produced the final response in its history.
    messages = final_state.get("messages", [])
    
    # Assert assistant tool announcement is in history
    assert any("Calling tools: calculate" in msg.content for msg in messages)
    # Assert tool output message is in history
    assert any("[Tool Output: calculate] 64" in msg.content for msg in messages)
    
    await registry.shutdown()
