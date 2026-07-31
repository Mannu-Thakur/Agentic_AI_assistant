import json
import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
import httpx
from httpx import Response

from app.tools.mcp_client import McpHttpClient
from app.tools.registry import ToolRegistry
from app.agent.nodes import classify_intent_node, generate_response_node, execute_tools_node
from app.agent.prompts import INTENT_MCP_TOOL, INTENT_TOOL_WHITELIST
from langchain_core.messages import HumanMessage, AIMessage


# Mock Remote MCP Server responses
MOCK_DISCOVERED_TOOLS = [
    {
        "name": "add_expense",
        "description": "Add a new expense",
        "inputSchema": {
            "type": "object",
            "properties": {
                "amount": {"type": "number"},
                "category": {"type": "string"},
                "merchant": {"type": "string"},
                "date": {"type": "string"}
            },
            "required": ["amount", "category"]
        }
    },
    {
        "name": "list_expenses",
        "description": "List all recorded expenses",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "update_expense",
        "description": "Update an expense by ID",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "integer"}, "amount": {"type": "number"}},
            "required": ["id"]
        }
    },
    {
        "name": "delete_expense",
        "description": "Delete an expense by ID",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "integer"}},
            "required": ["id"]
        }
    },
    {
        "name": "search_expenses",
        "description": "Search expenses by keyword",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"]
        }
    },
    {
        "name": "monthly_summary",
        "description": "Get monthly spending summary",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "category_summary",
        "description": "Get category-wise spending summary",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "top_merchants",
        "description": "Get top merchants by spending",
        "inputSchema": {"type": "object", "properties": {}}
    }
]


@pytest.mark.anyio
async def test_mcp_http_client_full_rpc_cycle():
    """
    Verify initialize -> tools/list -> tools/call RPC pipeline with mcp-session-id handling.
    """
    mock_url = "https://mock-mcp-server.example.com/mcp"
    client = McpHttpClient(url=mock_url)

    request_history = []

    async def mock_post(url, json=None, headers=None):
        nonlocal request_history
        request_history.append({"url": str(url), "json": json, "headers": headers})
        method = json.get("method")
        req_id = json.get("id")

        resp_headers = {"mcp-session-id": "sess-xyz-12345"}
        req_obj = httpx.Request("POST", str(url))

        if method == "initialize":
            body = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "TestExpenseServer", "version": "1.0.0"}
                }
            }
        elif method == "notifications/initialized":
            body = {}
        elif method == "tools/list":
            body = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": MOCK_DISCOVERED_TOOLS}
            }
        elif method == "tools/call":
            tool_name = json.get("params", {}).get("name")
            args = json.get("params", {}).get("arguments")

            if tool_name == "add_expense":
                res_content = [{"type": "text", "text": f"Successfully added expense ₹{args.get('amount')} for {args.get('category')} at {args.get('merchant', 'store')}."}]
            elif tool_name == "list_expenses":
                res_content = [{"type": "text", "text": "ID 1 | ₹500 | Groceries | D-Mart | 2026-07-29"}]
            elif tool_name == "search_expenses":
                res_content = [{"type": "text", "text": "Found 1 matching expense: ID 1 Groceries ₹500"}]
            elif tool_name == "monthly_summary":
                res_content = [{"type": "text", "text": "Total spent this month: ₹500 across 1 transaction."}]
            elif tool_name == "top_merchants":
                res_content = [{"type": "text", "text": "1. D-Mart: ₹500"}]
            elif tool_name == "update_expense":
                res_content = [{"type": "text", "text": f"Successfully updated expense ID {args.get('id')}."}]
            elif tool_name == "delete_expense":
                res_content = [{"type": "text", "text": f"Successfully deleted expense ID {args.get('id')}."}]
            else:
                res_content = [{"type": "text", "text": "OK"}]

            body = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": res_content, "isError": False}
            }
        else:
            body = {"jsonrpc": "2.0", "id": req_id, "result": {}}

        return Response(status_code=200, json=body, headers=resp_headers, request=req_obj)

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        # 1. Connect (initialize + notifications/initialized)
        await client.connect()
        assert client.session_id == "sess-xyz-12345"

        # 2. List tools
        tools = await client.list_tools()
        assert len(tools) == 8
        tool_names = [t["name"] for t in tools]
        assert "add_expense" in tool_names
        assert "list_expenses" in tool_names
        assert "top_merchants" in tool_names

        # 3. Call tool
        add_res = await client.call_tool("add_expense", {"amount": 500, "category": "Groceries", "merchant": "D-Mart"})
        assert "Successfully added expense ₹500" in add_res

        list_res = await client.call_tool("list_expenses", {})
        assert "D-Mart" in list_res

        # Verify mcp-session-id header was included in call_tool request
        call_req = [r for r in request_history if r["json"].get("method") == "tools/call"][0]
        assert call_req["headers"].get("mcp-session-id") == "sess-xyz-12345"

        await client.close()


@pytest.mark.anyio
async def test_mcp_client_error_handling():
    """
    Verify that when tools/call returns an error (isError: true or JSON-RPC error),
    McpHttpClient raises or surfaces the exact error message instead of returning fake success.
    """
    client = McpHttpClient(url="https://mock-mcp-server.example.com/mcp")

    async def mock_post_err(url, json=None, headers=None):
        return Response(
            status_code=200,
            json={
                "jsonrpc": "2.0",
                "id": json.get("id"),
                "result": {
                    "content": [{"type": "text", "text": "PostgreSQL connection failed: Database unreachable"}],
                    "isError": True
                }
            },
            request=httpx.Request("POST", str(url))
        )

    with patch("httpx.AsyncClient.post", side_effect=mock_post_err):
        with pytest.raises(Exception) as exc_info:
            await client.call_tool("add_expense", {"amount": 500})
        assert "PostgreSQL connection failed" in str(exc_info.value)

    await client.close()


@pytest.mark.anyio
async def test_tool_registry_remote_server_registration():
    """
    Verify ToolRegistry registers remote MCP tools and routes calls cleanly.
    """
    registry = ToolRegistry()
    registry.is_initialized = False

    async def mock_post(url, json=None, headers=None):
        method = json.get("method")
        req_id = json.get("id")
        req_obj = httpx.Request("POST", str(url))
        if method == "tools/list":
            return Response(status_code=200, json={"jsonrpc": "2.0", "id": req_id, "result": {"tools": MOCK_DISCOVERED_TOOLS}}, request=req_obj)
        elif method == "tools/call":
            return Response(status_code=200, json={"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": "Execution Success"}]}}, request=req_obj)
        return Response(status_code=200, json={"jsonrpc": "2.0", "id": req_id, "result": {}}, request=req_obj)

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        reg_tools = await registry.register_remote_server("ExpenseServer", "https://mock-expense.com/mcp")
        assert len(reg_tools) == 8

        all_names = registry.get_all_mcp_tool_names()
        assert "add_expense" in all_names
        assert "list_expenses" in all_names
        assert "top_merchants" in all_names

        # Call tool through registry
        res = await registry.call_tool("list_expenses", {})
        assert res == "Execution Success"

    await registry.shutdown()


@pytest.mark.anyio
async def test_acceptance_criteria_prompts_intent_and_whitelisting():
    """
    Test all 7 acceptance criteria prompts:
    1. Add an expense of ₹500 for Groceries at D-Mart today.
    2. List all expenses.
    3. Search groceries.
    4. Monthly summary.
    5. Top merchants.
    6. Update expense ID 1.
    7. Delete expense ID 1.

    Verify each is classified as MCP_TOOL and includes all remote MCP tools in allowed_tools.
    """
    prompts = [
        ("Add an expense of ₹500 for Groceries at D-Mart today.", "add_expense"),
        ("List all expenses.", "list_expenses"),
        ("Search groceries.", "search_expenses"),
        ("Monthly summary.", "monthly_summary"),
        ("Top merchants.", "top_merchants"),
        ("Update expense ID 1.", "update_expense"),
        ("Delete expense ID 1.", "delete_expense"),
    ]

    registry = ToolRegistry()

    # Pre-register mock expense server
    async def mock_post(url, json=None, headers=None):
        method = json.get("method")
        req_id = json.get("id")
        req_obj = httpx.Request("POST", str(url))
        if method == "tools/list":
            return Response(status_code=200, json={"jsonrpc": "2.0", "id": req_id, "result": {"tools": MOCK_DISCOVERED_TOOLS}}, request=req_obj)
        return Response(status_code=200, json={"jsonrpc": "2.0", "id": req_id, "result": {}}, request=req_obj)

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        with patch("app.agent.nodes._call_llm_judge", new=AsyncMock(return_value={"intent": "MCP_TOOL"})):
            await registry.register_remote_server("ExpenseServer", "https://mock-expense.com/mcp")

            for user_prompt, expected_tool in prompts:
                state = {
                    "messages": [HumanMessage(content=user_prompt)],
                    "images": [],
                    "uploaded_file_paths": [],
                    "is_ambiguous": False,
                }
                res = await classify_intent_node(state)
                assert res["intent"] == INTENT_MCP_TOOL, f"Failed intent classification for prompt: {user_prompt}"
                assert expected_tool in res["allowed_tools"], f"Expected {expected_tool} in allowed_tools for prompt: {user_prompt}"

    await registry.shutdown()
