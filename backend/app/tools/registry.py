import os
import sys
import logging
from typing import Dict, Any, List, Optional
from app.tools.local_tools import tavily_search, python_sandbox
from app.tools.mcp_client import McpStdioClient, McpHttpClient

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

        self.mcp_clients: Dict[str, Any] = {}
        self.mcp_tools_map: Dict[str, str] = {}          # tool_name -> server_name
        self.mcp_tools_schemas: Dict[str, Dict[str, Any]] = {}
        self.is_initialized = False

    async def register_remote_server(self, name: str, url: str, auth_header: Optional[str] = None, transport_type: str = "http_jsonrpc") -> List[Dict[str, Any]]:
        """
        Connects to a remote MCP server by URL, registers its tools in the live registry.
        """
        server_key = f"remote_{name.replace(' ', '_').lower()}"
        client = McpHttpClient(url=url, auth_header=auth_header, transport_type=transport_type)
        await client.connect()
        self.mcp_clients[server_key] = client

        tools = await client.list_tools()
        registered_tools = []
        for tool in tools:
            t_name = tool["name"]
            self.mcp_tools_map[t_name] = server_key
            schema_info = {
                "description": tool.get("description", ""),
                "schema": tool.get("inputSchema", {"type": "object"})
            }
            self.mcp_tools_schemas[t_name] = schema_info
            registered_tools.append({"name": t_name, **schema_info})
            logger.info(f"Registered Remote MCP tool '{t_name}' from '{url}'")
        return registered_tools

    async def initialize(self):
        """
        Connects to all configured local & remote MCP servers, fetches tool capabilities,
        and builds the routing table.
        """
        if self.is_initialized:
            return

        logger.info("Initializing ToolRegistry and MCP servers...")

        current_dir       = os.path.dirname(os.path.abspath(__file__))
        calculator_script = os.path.join(current_dir, "mcp_calculator_server.py")
        web_mcp_script    = os.path.join(current_dir, "mcp_web_server.py")
        python_exe        = sys.executable or "python"

        mcp_configs = {
            "calculator": {
                "command": python_exe,
                "args":    [calculator_script]
            },
            "web_mcp": {
                "command": python_exe,
                "args":    [web_mcp_script]
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

        # Load enabled Remote MCP Servers from database
        try:
            from app.core.database import AsyncSessionLocal
            from app.models.mcp_server import RemoteMcpServer
            from sqlalchemy import select

            async with AsyncSessionLocal() as session:
                res = await session.execute(select(RemoteMcpServer).where(RemoteMcpServer.is_enabled == True))
                db_servers = res.scalars().all()
                for r_server in db_servers:
                    try:
                        await self.register_remote_server(
                            name=r_server.name,
                            url=r_server.url,
                            auth_header=r_server.auth_header,
                            transport_type=r_server.transport_type
                        )
                    except Exception as exc:
                        logger.error(f"Failed to initialize remote MCP server '{r_server.name}' ({r_server.url}): {exc}")
        except Exception as db_exc:
            logger.warning(f"Could not load remote MCP servers from DB: {db_exc}")

        self.is_initialized = True
        logger.info("ToolRegistry initialization complete.")


    def get_all_mcp_tool_names(self) -> List[str]:
        """Returns list of all currently registered MCP tool names."""
        return list(self.mcp_tools_schemas.keys())

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
        whitelist. An empty whitelist → returns [] (no tools offered to LLM).

        Args:
            allowed_tools: list of tool names whitelisted for this turn

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

    async def get_semantically_relevant_tools(
        self,
        query: str,
        allowed_tools: List[str],
        top_k: int = 5,
        min_threshold: float = 0.20,
        api_key: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves declarations for allowed tools and filters/ranks them using SemanticToolRouter.
        """
        all_allowed_declarations = self.get_tool_schemas_for_intent(allowed_tools)
        if not all_allowed_declarations or not query:
            return all_allowed_declarations

        from app.tools.semantic_router import semantic_router
        return await semantic_router.select_relevant_tools(
            query=query,
            tool_declarations=all_allowed_declarations,
            top_k=top_k,
            min_threshold=min_threshold,
            api_key=api_key
        )

    async def call_tool(
        self,
        name: str,
        arguments: Dict[str, Any],
        api_keys: Optional[Dict[str, Any]] = None,
    ) -> str:
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
                if name == "tavily_search":
                    kwargs = dict(arguments or {})
                    if "api_keys" not in kwargs and api_keys:
                        kwargs["api_keys"] = api_keys
                    result_str = await func(**kwargs)
                else:
                    result_str = await func(**(arguments or {}))
            except Exception as e:
                status_label = "error"
                err_msg = str(e)
                logger.error(f"Error executing local tool '{name}': {str(e)}")
                result_str = f"Tool execution failed. Server returned: {str(e)}"

        # 2. Route to MCP tool
        elif name in self.mcp_tools_map:
            server_name = self.mcp_tools_map[name]
            client      = self.mcp_clients[server_name]
            logger.info(
                f"Invoking MCP tool '{name}' on server '{server_name}' "
                f"with arguments: {arguments}"
            )
            try:
                result_str = await client.call_tool(name, arguments or {})
            except Exception as e:
                status_label = "error"
                err_msg = str(e)
                logger.error(
                    f"Error calling MCP tool '{name}' on server '{server_name}': {str(e)}"
                )
                result_str = f"Tool execution failed. Server returned: {str(e)}"

        else:
            status_label = "error"
            err_msg = f"Tool '{name}' is not registered"
            logger.error(f"Tool '{name}' is not registered.")
            result_str = f"Tool execution failed. Server returned: Tool '{name}' is not registered."

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
