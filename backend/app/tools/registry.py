import asyncio
import logging
import re
from typing import Dict, Any, List, Optional
from app.tools.local_tools import tavily_search, python_sandbox, calculate
from app.tools.advanced_tools import (
    translate_text,
    summarize_text,
    list_tables,
    describe_table,
    execute_sql,
    search_documents,
    chunk_and_analyze,
)
from app.tools.mcp_client import McpHttpClient
from app.tools.network_safety import assert_public_dns_resolution
from app.core.config import settings


# Module-level imports for DB/audit/metrics — kept here (not inline) so that
# unit tests can patch them via `app.tools.registry.AsyncSessionLocal`, etc.
try:
    from app.core.database import AsyncSessionLocal
    from app.services.audit_service import AuditService
    from app.core.metrics import metrics_collector
except ImportError:  # pragma: no cover — tolerate missing deps in isolated envs
    AsyncSessionLocal = None  # type: ignore[assignment,misc]
    AuditService = None       # type: ignore[assignment]
    metrics_collector = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

_ADMIN_DATABASE_TOOLS = frozenset({"list_tables", "describe_table", "execute_sql"})


def remote_server_key(name: str) -> str:
    """Create a stable, non-ambiguous internal key for a validated server name."""
    normalized = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")
    if not normalized:
        raise ValueError("Remote MCP server name must contain letters or numbers.")
    return f"remote_{normalized}"
def tool_requires_confirmation(name: str, is_remote_mcp: bool) -> bool:
    """Require a user gesture for every third-party remote MCP invocation.

    A tool name such as ``list_*`` or ``get_*`` is not a trustworthy security
    contract: an arbitrary MCP server can make a side effect behind any name.
    Native, tenant-scoped read tools remain automatic; remote servers always
    receive a durable, one-time approval before the outbound tool call.
    """
    return bool(is_remote_mcp)


_SENSITIVE_ARGUMENT_KEYS = {
    "code", "api_key", "apikey", "token", "authorization", "password",
    "secret", "credential",
}


def _audit_safe_arguments(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Avoid persisting raw code, credentials, and unbounded nested payloads."""
    def scrub(value: Any, depth: int = 0) -> Any:
        if depth >= 4:
            return "[truncated nested value]"
        if isinstance(value, str):
            return value[:500] + "… [truncated]" if len(value) > 500 else value
        if isinstance(value, dict):
            safe_dict: Dict[str, Any] = {}
            for index, (key, nested_value) in enumerate(value.items()):
                if index >= 30:
                    safe_dict["[remaining]"] = "[truncated]"
                    break
                key_text = str(key)
                if key_text.lower() in _SENSITIVE_ARGUMENT_KEYS:
                    safe_dict[key_text] = "[redacted]"
                else:
                    safe_dict[key_text] = scrub(nested_value, depth + 1)
            return safe_dict
        if isinstance(value, (list, tuple)):
            result = [scrub(item, depth + 1) for item in value[:30]]
            if len(value) > 30:
                result.append("[truncated]")
            return result
        return value if isinstance(value, (int, float, bool, type(None))) else str(value)[:500]

    return scrub(arguments or {})


def _tool_result_is_failure(result: Any) -> bool:
    """Recognize explicit error prefixes used by built-in and MCP tools."""
    if not isinstance(result, str):
        return False
    normalized = result.lstrip().casefold()
    return normalized.startswith((
        "error:", "error ", "sql error:", "calculation failed:",
        "sandbox execution failed:", "code execution is unavailable",
        "code execution is temporarily unavailable",
        "live web search is currently unavailable", "web search error:",
        "failed to ",
    ))

class ToolRegistry:
    """A request-scoped tool registry.

    Remote MCP connections and schemas carry a user-owned credential and must
    never live in a process-global singleton.  Each graph invocation receives
    one registry via its runtime config; direct callers get an isolated one.
    """

    def __init__(self):
        self._init_registry()

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
            },
            "calculate": {
                "func": calculate,
                "description": "Evaluate a basic numeric arithmetic expression without executing code.",
                "schema": {
                    "type": "object",
                    "properties": {
                        "expression": {"type": "string", "description": "Numeric expression such as (25 * 49) + 120"}
                    },
                    "required": ["expression"]
                }
            },
            "translate_text": {
                "func": translate_text,
                "description": "Translate text from one language to another using Google Translate or LLM fallback.",
                "schema": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "The text to translate"},
                        "target_language": {"type": "string", "description": "Target language name or ISO 639-1 code (e.g. 'French', 'fr')"},
                        "source_language": {"type": "string", "description": "Source language or 'auto' for auto-detection", "default": "auto"}
                    },
                    "required": ["text", "target_language"]
                }
            },
            "summarize_text": {
                "func": summarize_text,
                "description": "Summarize text in bullet, paragraph, or tldr style using an LLM.",
                "schema": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "The text to summarize"},
                        "style": {"type": "string", "description": "Summary style: 'bullet', 'paragraph', or 'tldr'", "default": "bullet"},
                        "max_length": {"type": "integer", "description": "Approximate max words in summary", "default": 500}
                    },
                    "required": ["text"]
                }
            },
            "list_tables": {
                "func": list_tables,
                "description": "List all tables in the application SQLite database.",
                "schema": {
                    "type": "object",
                    "properties": {
                        "db_path": {"type": "string", "description": "Optional path to SQLite database file"}
                    },
                    "required": []
                }
            },
            "describe_table": {
                "func": describe_table,
                "description": "Describe the schema (columns, types, nullability) of a specific database table.",
                "schema": {
                    "type": "object",
                    "properties": {
                        "table_name": {"type": "string", "description": "Name of the table to describe"},
                        "db_path": {"type": "string", "description": "Optional path to SQLite database file"}
                    },
                    "required": ["table_name"]
                }
            },
            "execute_sql": {
                "func": execute_sql,
                "description": "Execute a read-only SQL SELECT query against the application database and return results as a markdown table.",
                "schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "SQL SELECT query to execute (read-only, no INSERT/UPDATE/DELETE)"},
                        "max_rows": {"type": "integer", "description": "Maximum rows to return (default 50, max 200)", "default": 50}
                    },
                    "required": ["query"]
                }
            },
            "search_documents": {
                "func": search_documents,
                "description": "Search the user's uploaded documents using vector similarity (RAG). Returns the most relevant document chunks.",
                "schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query to find relevant document chunks"},
                        "user_id": {"type": "string", "description": "Optional user ID to scope the search"},
                        "file_type": {"type": "string", "description": "Optional filter by file type (e.g. 'pdf', 'docx')"},
                        "k": {"type": "integer", "description": "Number of top chunks to retrieve (default 5)", "default": 5}
                    },
                    "required": ["query"]
                }
            },
            "chunk_and_analyze": {
                "func": chunk_and_analyze,
                "description": "Analyze a long text relative to a specific question by splitting it into chunks and synthesizing a comprehensive answer.",
                "schema": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "The long text to analyze"},
                        "question": {"type": "string", "description": "The question or task to answer from the text"},
                        "chunk_size": {"type": "integer", "description": "Approximate character count per chunk (default 2000)", "default": 2000}
                    },
                    "required": ["text", "question"]
                }
            }
        }

        self.mcp_clients: Dict[str, Any] = {}
        # Public tool names are server-namespaced to prevent one remote server
        # from shadowing another server's common tool name (e.g. `search`).
        self.mcp_tools_map: Dict[str, str] = {}          # public_tool_name -> server_name
        self.mcp_tool_original_names: Dict[str, str] = {}  # public_tool_name -> remote name
        self.mcp_tools_schemas: Dict[str, Dict[str, Any]] = {}
        self.is_initialized = False
        self._local_initialized = False
        self._sync_lock: Optional[asyncio.Lock] = None

    def _get_lock(self) -> Optional[asyncio.Lock]:
        # T-H2 FIX: Create asyncio.Lock lazily only when an event loop is running
        if self._sync_lock is None:
            try:
                asyncio.get_running_loop()
                self._sync_lock = asyncio.Lock()
            except RuntimeError:
                pass
        return self._sync_lock


    async def register_remote_server(self, name: str, url: str, auth_header: Optional[str] = None, transport_type: str = "http_jsonrpc") -> List[Dict[str, Any]]:
        """
        Connects to a remote MCP server by URL, registers its tools in the live registry.
        """
        allow_http = settings.ENVIRONMENT == "development" and settings.ALLOW_INSECURE_MCP_IN_DEVELOPMENT
        url = await assert_public_dns_resolution(url, allow_http=allow_http)
        server_key = remote_server_key(name)
        client = McpHttpClient(url=url, auth_header=auth_header, transport_type=transport_type)
        try:
            await asyncio.wait_for(client.connect(), timeout=7.0)
            tools = await asyncio.wait_for(client.list_tools(), timeout=7.0)
        except Exception as conn_err:
            try:
                await client.close()
            except Exception:
                pass
            raise conn_err

        # If previous client existed for this server_key, close it cleanly
        old_client = self.mcp_clients.get(server_key)
        if old_client and old_client is not client:
            try:
                await old_client.close()
            except Exception:
                pass

        self.mcp_clients[server_key] = client

        # Remove previous tools mapped to this server
        for t_name, s_key in list(self.mcp_tools_map.items()):
            if s_key == server_key:
                self.mcp_tools_map.pop(t_name, None)
                self.mcp_tools_schemas.pop(t_name, None)
                self.mcp_tool_original_names.pop(t_name, None)

        registered_tools = []
        for tool in tools:
            raw_name = tool.get("name")
            if not isinstance(raw_name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,127}", raw_name.strip()):
                logger.warning("Skipping malformed remote tool name from MCP server '%s'", server_key)
                continue
            t_name = f"{server_key}__{raw_name.strip()}"
            self.mcp_tools_map[t_name] = server_key
            self.mcp_tool_original_names[t_name] = raw_name.strip()
            schema_info = {
                "description": tool.get("description", ""),
                "schema": tool.get("inputSchema", {"type": "object"})
            }
            self.mcp_tools_schemas[t_name] = schema_info
            registered_tools.append({"name": t_name, **schema_info})
            logger.info("Registered remote MCP tool '%s' as '%s'", raw_name, t_name)
        return registered_tools

    async def unregister_remote_server(self, server_key: str):
        """Unregisters tools and closes connection for a remote MCP server."""
        client = self.mcp_clients.pop(server_key, None)
        if client:
            try:
                await client.close()
            except Exception as e:
                logger.warning(f"Error closing client for {server_key}: {e}")
        for t_name, s_key in list(self.mcp_tools_map.items()):
            if s_key == server_key:
                self.mcp_tools_map.pop(t_name, None)
                self.mcp_tools_schemas.pop(t_name, None)
                self.mcp_tool_original_names.pop(t_name, None)
                logger.info(f"Unregistered MCP tool '{t_name}' from server '{server_key}'")

    async def _init_local_mcp_servers(self):
        """Retire unsafe local stdio servers from the public runtime.

        Calculation and web search are native stateless tools.  The old process
        hosts mixed those read operations with a shared on-disk expense store,
        reminders, and email actions, which cannot be tenant-safe in a public
        multi-user service.
        """
        if self._local_initialized:
            return
        self._local_initialized = True

    async def sync_remote_servers(self, user_id: Optional[str] = None):
        """
        Synchronizes active remote MCP servers from DB with the in-memory registry.
        Safely connects new/enabled servers, drops disabled/deleted ones, and
        never blocks forever if a server is offline.
        """
        # Always create the lock in async context (event loop is guaranteed running here)
        if self._sync_lock is None:
            self._sync_lock = asyncio.Lock()
        async with self._sync_lock:
            await self._init_local_mcp_servers()

            # There is no safe "all users" remote registry in a public
            # multi-tenant process.  The caller must provide an authenticated
            # user identity before any remote endpoint is loaded.
            if not user_id:
                self.is_initialized = True
                return

            try:
                from app.models.mcp_server import RemoteMcpServer
                from sqlalchemy import select

                async with AsyncSessionLocal() as session:
                    stmt = select(RemoteMcpServer).where(
                        RemoteMcpServer.is_enabled == True,
                        (RemoteMcpServer.user_id == str(user_id)) | (RemoteMcpServer.user_id.is_(None)),
                    )
                    res = await session.execute(stmt)
                    db_servers = res.scalars().all()

                active_server_keys = set()
                for r_server in db_servers:
                    server_key = remote_server_key(r_server.name)
                    active_server_keys.add(server_key)

                    # If already connected and has tools, skip reconnect
                    has_tools = any(s == server_key for s in self.mcp_tools_map.values())
                    if server_key in self.mcp_clients and has_tools:
                        continue

                    try:
                        logger.info("Syncing configured remote MCP server '%s'", r_server.name)
                        from app.core.security import decrypt_api_key
                        auth_header = r_server.auth_header
                        if auth_header:
                            try:
                                auth_header = decrypt_api_key(auth_header)
                            except Exception:
                                # Backward compatibility for records created before
                                # encrypted MCP credentials.  Startup migration will
                                # re-encrypt them; do not log the raw value.
                                logger.warning("Migrating legacy plaintext MCP credential for server '%s'", r_server.name)
                        await self.register_remote_server(
                            name=r_server.name,
                            url=r_server.url,
                            auth_header=auth_header,
                            transport_type=r_server.transport_type
                        )
                    except Exception as exc:
                        logger.warning(f"Failed to sync remote MCP server '{r_server.name}' ({r_server.url}): {exc}")

                # This instance is scoped to one request/user, so drop stale
                # endpoints eagerly instead of retaining another tenant's tools.
                for s_key in list(self.mcp_clients.keys()):
                    if s_key.startswith("remote_") and s_key not in active_server_keys:
                        logger.info(f"Cleaning up disabled/removed remote MCP server '{s_key}'")
                        await self.unregister_remote_server(s_key)

                self.is_initialized = True
            except Exception as db_exc:
                logger.warning(f"Could not load remote MCP servers from DB: {db_exc}")
                self.is_initialized = True

    async def initialize(self, user_id: Optional[str] = None):
        """
        Connects to all configured local & remote MCP servers, fetches tool capabilities,
        and builds the routing table.
        """
        await self.sync_remote_servers(user_id)
        logger.info("ToolRegistry initialization complete.")


    def get_all_mcp_tool_names(self) -> List[str]:
        """Returns list of all currently registered MCP tool names."""
        return list(self.mcp_tools_schemas.keys())

    def get_all_registered_tool_schemas(self) -> List[Dict[str, Any]]:
        """
        Returns ALL registered tool schemas across local and MCP tools.
        Acts as the single source of truth for semantic routing and tool discovery.
        """
        return self.get_tool_schemas()

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
        allowed_tools: Optional[List[str]] = None,
        top_k: int = 5,
        min_threshold: float = 0.20,
        api_key: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves declarations for allowed tools (or ALL registered tools if allowed_tools is None)
        and filters/ranks them using SemanticToolRouter.
        """
        if allowed_tools is not None:
            all_declarations = self.get_tool_schemas_for_intent(allowed_tools)
        else:
            all_declarations = self.get_all_registered_tool_schemas()

        if not all_declarations or not query:
            return all_declarations

        from app.tools.semantic_router import semantic_router
        return await semantic_router.select_relevant_tools(
            query=query,
            tool_declarations=all_declarations,
            top_k=top_k,
            min_threshold=min_threshold,
            api_key=api_key
        )

    async def call_tool(
        self,
        name: str,
        arguments: Dict[str, Any],
        api_keys: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        is_admin: bool = False,
        approved: bool = False,
        raise_on_error: bool = False,
    ) -> str:
        """
        Routes the tool invocation to the correct local handler or MCP server.
        Records execution status in Prometheus metrics and audit logs.
        """
        # M-1 FIX: Double-checked locking on lazy initialization
        if not self.is_initialized:
            lock = self._get_lock()
            if lock is not None:
                async with lock:
                    if not self.is_initialized:
                        await self.initialize()
            else:
                await self.initialize()


        status_label = "success"
        err_msg = None
        result_str = ""
        execution_error: Exception | None = None

        if name in _ADMIN_DATABASE_TOOLS and (not is_admin or not settings.ENABLE_ADMIN_DATABASE_INSPECTOR):
            status_label = "blocked"
            err_msg = "Administrative database inspector is disabled or requires an administrator"
            result_str = "Administrative database access is disabled for this request."
        # 1. Route to local tool
        elif name in self.local_tools:
            logger.info("Invoking local tool '%s' with arguments: %s", name, _audit_safe_arguments(arguments))
            try:
                func = self.local_tools[name]["func"]
                kwargs = dict(arguments or {})
                if name == "tavily_search":
                    # Normalize query parameter aliases
                    if "query" not in kwargs:
                        for alias in ("query_text", "search_query", "q", "text"):
                            if alias in kwargs:
                                kwargs["query"] = kwargs.pop(alias)
                                break
                    if "api_keys" not in kwargs and api_keys:
                        kwargs["api_keys"] = api_keys
                    result_str = await func(**kwargs)
                elif name == "python_sandbox":
                    # Normalize code parameter aliases
                    if "code" not in kwargs:
                        for alias in ("python_code", "script", "command", "source"):
                            if alias in kwargs:
                                kwargs["code"] = kwargs.pop(alias)
                                break
                    result_str = await func(**kwargs)
                else:
                    if name in {"translate_text", "summarize_text", "chunk_and_analyze", "search_documents"} and "api_keys" not in kwargs:
                        kwargs["api_keys"] = api_keys or {}
                    if name == "search_documents":
                        # Tenant scoping comes from authenticated request context,
                        # never from a model-selected argument.
                        kwargs["user_id"] = user_id
                    result_str = await func(**kwargs)
            except Exception as e:
                status_label = "error"
                err_msg = str(e)
                logger.error(f"Error executing local tool '{name}': {str(e)}")
                result_str = f"Tool execution failed. Server returned: {str(e)}"

        # 2. Route to MCP tool
        elif name in self.mcp_tools_map:
            server_name = self.mcp_tools_map[name]
            if tool_requires_confirmation(name, server_name.startswith("remote_")) and not approved:
                status_label = "approval_required"
                err_msg = "Explicit user confirmation is required for a potentially mutating remote MCP tool"
                result_str = (
                    "This external action requires your explicit confirmation before it can run. "
                    "No change was made."
                )
                logger.info("Blocked unapproved remote MCP action '%s' for user=%s", name, user_id)
            # KeyError guard: client may have been removed after shutdown/unregister
            client = self.mcp_clients.get(server_name)
            if not approved and tool_requires_confirmation(name, server_name.startswith("remote_")):
                client = None
            if client is None and not result_str:
                status_label = "error"
                err_msg = f"MCP client for server '{server_name}' is no longer connected"
                logger.error(f"[ToolRegistry] {err_msg} (tool='{name}')")
                result_str = f"Tool execution failed: {err_msg}"
                if raise_on_error:
                    execution_error = RuntimeError(err_msg)
            elif not result_str:
                logger.info(
                    "Invoking approved MCP tool '%s' on server '%s' with arguments: %s",
                    name,
                    server_name,
                    _audit_safe_arguments(arguments),
                )
                try:
                    remote_name = self.mcp_tool_original_names.get(name, name)
                    result_str = await client.call_tool(remote_name, arguments or {})
                except Exception as e:
                    # The remote tool may have completed its side effect before
                    # the network failed.  Never retry an approved external
                    # action automatically, because that could duplicate it.
                    status_label = "error"
                    err_msg = type(e).__name__
                    logger.error(
                        "MCP tool '%s' on '%s' returned an indeterminate failure (%s)",
                        name,
                        server_name,
                        type(e).__name__,
                    )
                    result_str = (
                        "Tool execution failed and was not retried because its completion "
                        "state is unknown. Please verify the external system before trying again."
                    )
                    if raise_on_error:
                        execution_error = RuntimeError(result_str)
                        execution_error.__cause__ = e

        else:
            status_label = "error"
            err_msg = f"Tool '{name}' is not registered"
            logger.error(f"Tool '{name}' is not registered.")
            result_str = f"Tool execution failed. Server returned: Tool '{name}' is not registered."

        if _tool_result_is_failure(result_str):
            status_label = "error"
            err_msg = result_str[:512]
            if raise_on_error and execution_error is None:
                execution_error = RuntimeError("Tool returned an explicit failure result.")

        # Record metrics and log audit events (best-effort, 5s timeout to prevent
        # indefinite hang when DB pool is unavailable, e.g. during tests)
        metrics_collector.record_tool_call(name, status_label)
        try:
            async def _do_audit():
                async with AsyncSessionLocal() as db:
                    event_type = "mcp_call" if name in self.mcp_tools_map else "tool_execution"
                    await AuditService.log_event(
                        db,
                        None,
                        event_type,
                        {"tool": name, "arguments": _audit_safe_arguments(arguments), "status": status_label, "error": err_msg, "user_id": user_id}
                    )
            await asyncio.wait_for(_do_audit(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning(f"Audit log for tool '{name}' timed out after 5s — skipping")
        except Exception as exc:
            logger.error(f"Failed to log tool execution audit event: {exc}")

        if execution_error is not None:
            raise execution_error
        return result_str

    async def shutdown(self):
        """
        Gracefully closes all active remote MCP connections.
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
        self.mcp_tool_original_names.clear()
        self.is_initialized = False
        self._local_initialized = False
        self._sync_lock = None

