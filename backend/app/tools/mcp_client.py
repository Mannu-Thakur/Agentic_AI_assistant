"""Safe remote MCP transport for the public application.

The public API supports only remote HTTP(S) MCP servers. Local stdio MCP
servers used to spawn arbitrary host-side commands, which is not an acceptable
execution boundary for a multi-tenant service. Python execution has its own
isolated sandbox service instead.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.tools.network_safety import (
    PublicAddressNetworkBackend,
    assert_public_dns_resolution,
    normalise_outbound_url,
)

logger = logging.getLogger(__name__)

_HEADER_NAME_RE = re.compile(r"^[A-Za-z0-9-]{1,128}$")
_MAX_DISCOVERED_TOOLS = 128


class McpStdioClient:
    """Compatibility shim that fails closed instead of spawning host commands."""

    def __init__(self, command: str, args: Optional[List[str]] = None, env: Optional[Dict[str, str]] = None):
        self.command = command
        self.args = args or []
        self.env = env or {}

    @staticmethod
    def _disabled() -> RuntimeError:
        return RuntimeError(
            "Local stdio MCP servers are disabled in the public deployment. "
            "Connect a validated remote HTTPS MCP server instead."
        )

    async def connect(self) -> None:
        raise self._disabled()

    async def send_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        raise self._disabled()

    async def send_notification(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        raise self._disabled()

    async def list_tools(self) -> List[Dict[str, Any]]:
        raise self._disabled()

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        raise self._disabled()

    async def close(self) -> None:
        return None


class McpHttpClient:
    """HTTP JSON-RPC client for a user-configured remote MCP server.

    Each outbound request re-resolves the endpoint and rejects private or
    internal addresses. Redirects are disabled. Tool calls intentionally use
    at-most-once delivery: failures are surfaced as indeterminate rather than
    retried, because an MCP tool may have already changed external state.
    """

    def __init__(self, url: str, auth_header: Optional[str] = None, transport_type: str = "http_jsonrpc"):
        import httpx

        allow_http = settings.ENVIRONMENT == "development" and settings.ALLOW_INSECURE_MCP_IN_DEVELOPMENT
        self.url = normalise_outbound_url(url, allow_http=allow_http)
        self.auth_header = self._validate_auth_header(auth_header)
        self.transport_type = transport_type
        self.session_id: Optional[str] = None
        self.is_connected = False
        self._handshake_done = False
        self.next_request_id = 1
        self._client: Optional[httpx.AsyncClient] = None

    @staticmethod
    def _validate_auth_header(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if len(value) > 4096 or "\r" in value or "\n" in value:
            raise ValueError("Invalid remote MCP authorization value")
        if ":" in value and not value.lower().startswith("bearer "):
            header_name, header_value = value.split(":", 1)
            if not _HEADER_NAME_RE.fullmatch(header_name.strip()) or not header_value.strip():
                raise ValueError("Invalid remote MCP authorization header")
        return value

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": "Antigravity-AI-Chatbot-MCP-Client/1.0",
        }
        if self.session_id:
            headers["mcp-session-id"] = self.session_id
        if self.auth_header:
            if self.auth_header.lower().startswith("bearer "):
                headers["Authorization"] = self.auth_header
            elif ":" in self.auth_header:
                name, value = self.auth_header.split(":", 1)
                headers[name.strip()] = value.strip()
            else:
                headers["Authorization"] = f"Bearer {self.auth_header}"
        return headers

    @staticmethod
    def _allow_http() -> bool:
        return settings.ENVIRONMENT == "development" and settings.ALLOW_INSECURE_MCP_IN_DEVELOPMENT

    async def _ensure_client(self) -> None:
        import httpx

        if self._client is None or self._client.is_closed:
            transport = httpx.AsyncHTTPTransport(retries=0)
            # HTTPX does not expose httpcore's network backend on its public
            # transport constructor. Pin it before the pool creates any
            # connections; fail closed if that contract ever changes.
            network_backend = getattr(getattr(transport, "_pool", None), "_network_backend", None)
            if network_backend is None:
                raise RuntimeError("The HTTP transport cannot enforce public-address pinning.")
            transport._pool._network_backend = PublicAddressNetworkBackend()
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                follow_redirects=False,
                trust_env=False,
                transport=transport,
            )
            self.session_id = None
            self.is_connected = False
            self._handshake_done = False

    async def _validate_destination(self) -> None:
        await assert_public_dns_resolution(self.url, allow_http=self._allow_http())

    @staticmethod
    def _extract_session_id(response: Any) -> Optional[str]:
        return (
            response.headers.get("mcp-session-id")
            or response.headers.get("Mcp-Session-Id")
            or response.headers.get("session-id")
        )

    @staticmethod
    def _parse_response(response_text: str) -> Dict[str, Any]:
        text = (response_text or "").strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {"result": parsed}
        except json.JSONDecodeError:
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("data:"):
                    try:
                        parsed = json.loads(line[5:].strip())
                        return parsed if isinstance(parsed, dict) else {"result": parsed}
                    except json.JSONDecodeError as exc:
                        raise ValueError("Remote MCP returned malformed SSE JSON") from exc
        raise ValueError("Remote MCP returned malformed JSON-RPC data")

    async def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        await self._validate_destination()
        await self._ensure_client()
        assert self._client is not None
        response = await self._client.post(self.url, json=payload, headers=self._get_headers())
        response.raise_for_status()
        new_session_id = self._extract_session_id(response)
        if new_session_id:
            self.session_id = new_session_id
        return self._parse_response(response.text)

    async def send_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        if method not in {"initialize", "notifications/initialized"} and not self.is_connected:
            await self.connect()

        request_id = self.next_request_id
        self.next_request_id += 1
        payload: Dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            payload["params"] = params

        try:
            data = await self._post(payload)
        except Exception as exc:
            logger.warning("Remote MCP request failed: method=%s error=%s", method, type(exc).__name__)
            raise

        if "error" in data:
            error = data["error"]
            message = error.get("message", "Remote MCP returned an error") if isinstance(error, dict) else "Remote MCP returned an error"
            raise RuntimeError(f"Remote MCP error for {method}: {message}")
        return data.get("result")

    async def send_notification(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        payload: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        try:
            await self._post(payload)
        except Exception as exc:
            logger.warning("Remote MCP notification failed: method=%s error=%s", method, type(exc).__name__)
            raise

    async def connect(self) -> None:
        if self.is_connected and self._handshake_done:
            return
        await self._ensure_client()
        self._handshake_done = True
        init_params = {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "AntigravityRemoteMcpClient", "version": "1.0.0"},
        }
        try:
            result = await self.send_request("initialize", init_params)
            if not isinstance(result, dict):
                raise ConnectionError("Remote MCP server returned an invalid initialize response")
            await self.send_notification("notifications/initialized")
            self.is_connected = True
        except Exception:
            self.is_connected = False
            self._handshake_done = False
            raise

    async def list_tools(self) -> List[Dict[str, Any]]:
        if not self.is_connected:
            await self.connect()
        result = await self.send_request("tools/list")
        if isinstance(result, dict):
            tools = result.get("tools", [])
        elif isinstance(result, list):
            tools = result
        else:
            raise ValueError("Remote MCP returned an invalid tools/list response")
        if not isinstance(tools, list):
            raise ValueError("Remote MCP returned an invalid tools list")
        valid_tools = [tool for tool in tools if isinstance(tool, dict)]
        if len(valid_tools) > _MAX_DISCOVERED_TOOLS:
            logger.warning("Remote MCP exposed more than %d tools; truncating discovery", _MAX_DISCOVERED_TOOLS)
            valid_tools = valid_tools[:_MAX_DISCOVERED_TOOLS]
        return valid_tools

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        if not isinstance(name, str) or not name:
            raise ValueError("Remote MCP tool name is invalid")
        if not isinstance(arguments, dict):
            raise ValueError("Remote MCP tool arguments must be an object")
        if not self.is_connected:
            await self.connect()

        # Do not retry this request. The caller records an indeterminate result
        # on failure and requires a human to verify the external system.
        result = await self.send_request("tools/call", {"name": name, "arguments": arguments})
        if result is None:
            return "Tool executed with no response content."
        if isinstance(result, dict) and result.get("isError"):
            content = result.get("content", [])
            messages = [
                str(item.get("text", ""))
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ]
            raise RuntimeError("Remote MCP tool returned an error: " + ("\n".join(messages) or "unknown error"))
        if isinstance(result, dict):
            content = result.get("content", [])
            messages = [
                str(item.get("text", ""))
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ]
            if messages:
                return "\n".join(messages)
        return json.dumps(result) if isinstance(result, (dict, list)) else str(result)

    async def close(self) -> None:
        self.is_connected = False
        self._handshake_done = False
        self.session_id = None
        if self._client is not None:
            try:
                await self._client.aclose()
            finally:
                self._client = None
