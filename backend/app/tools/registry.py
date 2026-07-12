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
        self.mcp_tools_map: Dict[str, str] = {}  # tool_name -> server_name
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

        # Locate our mock calculator script dynamically
        current_dir = os.path.dirname(os.path.abspath(__file__))
        calculator_script = os.path.join(current_dir, "mcp_calculator_server.py")
        python_exe = sys.executable or "python"

        mcp_configs = {
            "calculator": {
                "command": python_exe,
                "args": [calculator_script]
            }
        }

        for server_name, cfg in mcp_configs.items():
            try:
                client = McpStdioClient(command=cfg["command"], args=cfg["args"])
                await client.connect()
                self.mcp_clients[server_name] = client
                
                # Fetch tools list
                tools = await client.list_tools()
                for tool in tools:
                    t_name = tool["name"]
                    self.mcp_tools_map[t_name] = server_name
                    self.mcp_tools_schemas[t_name] = {
                        "description": tool.get("description", ""),
                        "schema": tool.get("inputSchema", {"type": "object"})
                    }
                    logger.info(f"Registered MCP tool '{t_name}' from server '{server_name}'")
            except Exception as e:
                logger.error(f"Failed to initialize MCP server '{server_name}': {str(e)}")

        self.is_initialized = True
        logger.info("ToolRegistry initialization complete.")

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """
        Formats all registered tools as Gemini-compliant tool declarations.
        """
        declarations = []
        
        # Local tools
        for name, info in self.local_tools.items():
            declarations.append({
                "name": name,
                "description": info["description"],
                "parameters": info["schema"]
            })
            
        # MCP tools
        for name, info in self.mcp_tools_schemas.items():
            declarations.append({
                "name": name,
                "description": info["description"],
                "parameters": info["schema"]
            })
            
        return declarations

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        """
        Routes the tool invocation to the correct local handler or MCP server.
        """
        # Ensure initialization has completed
        if not self.is_initialized:
            await self.initialize()

        # 1. Route to local tool
        if name in self.local_tools:
            logger.info(f"Invoking local tool '{name}' with arguments: {arguments}")
            try:
                func = self.local_tools[name]["func"]
                # Resolve argument keyword names
                return await func(**arguments)
            except Exception as e:
                logger.error(f"Error executing local tool '{name}': {str(e)}")
                return f"Error executing tool '{name}': {str(e)}"

        # 2. Route to MCP tool
        elif name in self.mcp_tools_map:
            server_name = self.mcp_tools_map[name]
            client = self.mcp_clients[server_name]
            logger.info(f"Invoking MCP tool '{name}' on server '{server_name}' with arguments: {arguments}")
            try:
                return await client.call_tool(name, arguments)
            except Exception as e:
                logger.error(f"Error calling MCP tool '{name}' on server '{server_name}': {str(e)}")
                return f"Error calling tool '{name}' on server '{server_name}': {str(e)}"

        else:
            logger.error(f"Tool '{name}' is not registered.")
            return f"Error: Tool '{name}' is not registered."

    async def shutdown(self):
        """
        Gracefully terminates all active MCP subprocess connections.
        """
        logger.info("Shutting down MCP clients in ToolRegistry...")
        for server_name, client in list(self.mcp_clients.items()):
            try:
                await client.close()
            except Exception as e:
                logger.error(f"Error shutting down MCP server '{server_name}': {str(e)}")
        self.mcp_clients.clear()
        self.mcp_tools_map.clear()
        self.mcp_tools_schemas.clear()
        self.is_initialized = False
