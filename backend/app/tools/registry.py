import os
import sys
import logging
from typing import Dict, Any, List, Optional
from app.tools.local_tools import tavily_search, python_sandbox
from app.tools.mcp_client import McpStdioClient

logger = logging.getLogger(__name__)


class ToolRegistry:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(ToolRegistry, cls).__new__(cls, *args, **kwargs)
            cls._instance._init_registry()
        return cls._instance

    def _init_registry(self):
        self.local_tools = {
            "tavily_search": {
                "func": tavily_search,
                "description": "Search the web for real-time information, weather, news, etc.",
                "schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query text"
                        }
                    },
                    "required": ["query"]
                }
            },
            "python_sandbox": {
                "func": python_sandbox,
                "description": "Execute arbitrary Python code in a sandboxed environment and capture stdout.",
                "schema": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Complete Python script to execute"
                        }
                    },
                    "required": ["code"]
                }
            }
        }

        self.mcp_clients: Dict[str, McpStdioClient] = {}
        self.mcp_tools_map: Dict[str, str] = {}          # tool_name -> server_name
        self.mcp_tools_schemas: Dict[str, Dict[str, Any]] = {}
        self.is_initialized = False

    async def initialize(self):
        """
        Connects to all configured MCP servers, fetches their tool capabilities,
        and builds the routing table.
        """
        if self.is_initialized:
            return

        logger.info("Initializing ToolRegistry and MCP servers...")

        current_dir       = os.path.dirname(os.path.abspath(__file__))
        calculator_script = os.path.join(current_dir, "mcp_calculator_server.py")
        python_exe        = sys.executable or "python"

        mcp_configs = {
            "calculator": {
                "command": python_exe,
                "args":    [calculator_script]
            }
        }

        for server_name, cfg in mcp_configs.items():
            try:
                client = McpStdioClient(command=cfg["command"], args=cfg["args"])
                await client.connect()
                self.mcp_clients[server_name] = client

                tools = await client.list_tools()
                for tool in tools:
                    t_name = tool["name"]
                    self.mcp_tools_map[t_name]     = server_name
                    self.mcp_tools_schemas[t_name] = {
                        "description": tool.get("description", ""),
                        "schema":      tool.get("inputSchema", {"type": "object"})
                    }
                    logger.info(
                        f"Registered MCP tool '{t_name}' from server '{server_name}'"
                    )
            except Exception as e:
                logger.error(
                    f"Failed to initialize MCP server '{server_name}': {str(e)}"
                )

        self.is_initialized = True
        logger.info("ToolRegistry initialization complete.")

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """
        Returns ALL registered tool schemas.
        Preserved for backward compatibility — prefer get_tool_schemas_for_intent()
        in the agent pipeline.
        """
        declarations = []

        for name, info in self.local_tools.items():
            declarations.append({
                "name":        name,
                "description": info["description"],
                "parameters":  info["schema"],
            })

        for name, info in self.mcp_tools_schemas.items():
            declarations.append({
                "name":        name,
                "description": info["description"],
                "parameters":  info["schema"],
            })

        return declarations

    def get_tool_schemas_for_intent(
        self, allowed_tools: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Intent-gated tool schema injection (P0 fix).

        Returns ONLY the tool schemas whose names appear in the allowed_tools
        whitelist.  An empty whitelist → returns [] (no tools offered to LLM).

        This prevents:
          • python_sandbox being offered on MEMORY_WRITE / NORMAL_CHAT turns.
          • tavily_search being offered on private-document queries.
          • Any tool being offered when the intent does not require it.

        Args:
            allowed_tools: list of tool names whitelisted for this turn
                           (populated from INTENT_TOOL_WHITELIST by
                           classify_intent_node).

        Returns:
            List of Gemini-compliant tool declaration dicts.
        """
        if not allowed_tools:
            return []

        allowed_set  = set(allowed_tools)
        declarations = []

        # Local tools
        for name, info in self.local_tools.items():
            if name in allowed_set:
                declarations.append({
                    "name":        name,
                    "description": info["description"],
                    "parameters":  info["schema"],
                })

        # MCP tools
        for name, info in self.mcp_tools_schemas.items():
            if name in allowed_set:
                declarations.append({
                    "name":        name,
                    "description": info["description"],
                    "parameters":  info["schema"],
                })

        return declarations

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        """
        Routes the tool invocation to the correct local handler or MCP server.
        Records execution status in Prometheus metrics and audit logs.
        """
        if not self.is_initialized:
            await self.initialize()

        from app.core.metrics import metrics_collector
        from app.core.database import AsyncSessionLocal
        from app.services.audit_service import AuditService

        status_label = "success"
        err_msg = None
        result_str = ""

        # 1. Route to local tool
        if name in self.local_tools:
            logger.info(f"Invoking local tool '{name}' with arguments: {arguments}")
            try:
                func = self.local_tools[name]["func"]
                result_str = await func(**arguments)
            except Exception as e:
                status_label = "error"
                err_msg = str(e)
                logger.error(f"Error executing local tool '{name}': {str(e)}")
                result_str = f"Error executing tool: {str(e)}"

        # 2. Route to MCP tool
        elif name in self.mcp_tools_map:
            server_name = self.mcp_tools_map[name]
            client      = self.mcp_clients[server_name]
            logger.info(
                f"Invoking MCP tool '{name}' on server '{server_name}' "
                f"with arguments: {arguments}"
            )
            try:
                result_str = await client.call_tool(name, arguments)
            except Exception as e:
                status_label = "error"
                err_msg = str(e)
                logger.error(
                    f"Error calling MCP tool '{name}' on server '{server_name}': {str(e)}"
                )
                result_str = f"Error calling tool: {str(e)}"

        else:
            status_label = "error"
            err_msg = "Tool not registered"
            logger.error(f"Tool '{name}' is not registered.")
            result_str = f"Error: Tool '{name}' is not registered."

        # Record metrics and log audit events
        metrics_collector.record_tool_call(name, status_label)
        try:
            async with AsyncSessionLocal() as db:
                event_type = "mcp_call" if name in self.mcp_tools_map else "tool_execution"
                await AuditService.log_event(
                    db,
                    None,
                    event_type,
                    {"tool": name, "arguments": arguments, "status": status_label, "error": err_msg}
                )
        except Exception as exc:
            logger.error(f"Failed to log tool execution audit event: {exc}")

        return result_str

    async def shutdown(self):
        """
        Gracefully terminates all active MCP subprocess connections.
        """
        logger.info("Shutting down MCP clients in ToolRegistry...")
        for server_name, client in list(self.mcp_clients.items()):
            try:
                await client.close()
            except Exception as e:
                logger.error(
                    f"Error shutting down MCP server '{server_name}': {str(e)}"
                )
        self.mcp_clients.clear()
        self.mcp_tools_map.clear()
        self.mcp_tools_schemas.clear()
        self.is_initialized = False
