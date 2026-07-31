import json
import asyncio
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class McpStdioClient:
    def __init__(self, command: str, args: Optional[List[str]] = None, env: Optional[Dict[str, str]] = None):
        self.command = command
        self.args = args or []
        self.env = env
        self.proc: Optional[asyncio.subprocess.Process] = None
        self.pending_requests: Dict[int, asyncio.Future] = {}
        self.next_request_id = 1
        self.reader_task: Optional[asyncio.Task] = None
        self.is_connected = False

    async def connect(self):
        """
        Spawns the MCP server subprocess and starts the background reader.
        """
        logger.info(f"Connecting to MCP Stdio server: {self.command} with args {self.args}")
        try:
            self.proc = await asyncio.create_subprocess_exec(
                self.command,
                *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self.env
            )
            self.is_connected = True
            
            # Start background reader task
            self.reader_task = asyncio.create_task(self._read_stdout_loop())
            
            # Perform initial handshake
            await self._handshake()
            logger.info("MCP Stdio server handshake successful.")
        except Exception as e:
            logger.error(f"Failed to connect to MCP server: {str(e)}")
            await self.close()
            raise e

    async def _read_stdout_loop(self):
        """
        Continuously reads lines from the server's stdout, parses JSON-RPC,
        and resolves pending request futures.
        """
        if not self.proc or not self.proc.stdout:
            return

        while self.is_connected:
            try:
                line_bytes = await self.proc.stdout.readline()
                if not line_bytes:
                    logger.warning("MCP server stdout closed.")
                    break

                line = line_bytes.decode("utf-8").strip()
                if not line:
                    continue

                logger.debug(f"Received from MCP server: {line}")
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning(f"Ignored non-JSON line from MCP server: {line}")
                    continue

                if "id" in message:
                    msg_id = message["id"]
                    future = self.pending_requests.pop(msg_id, None)
                    if future and not future.done():
                        if "error" in message:
                            future.set_exception(Exception(message["error"].get("message", "Unknown error")))
                        else:
                            future.set_result(message.get("result"))
                else:
                    # Ignore notifications/requests from server for simplicity
                    pass
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in MCP client stdout reader loop: {str(e)}")
                break

        self.is_connected = False

    async def send_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """
        Sends a JSON-RPC 2.0 request to the MCP server and awaits the response.
        Auto-reconnects if the connection or process is down.
        """
        # Auto-reconnect if process died or is not running
        if not self.is_connected or not self.proc or self.proc.returncode is not None:
            logger.info("MCP server is not connected or process died. Attempting to reconnect...")
            try:
                await self.connect()
            except Exception as e:
                raise Exception(f"MCP server reconnect failed: {e}")

        if not self.is_connected or not self.proc or not self.proc.stdin:
            raise Exception("MCP client is not connected to server.")

        req_id = self.next_request_id
        self.next_request_id += 1

        request = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
        }
        if params is not None:
            request["params"] = params

        # Register the future
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self.pending_requests[req_id] = future

        # Send message
        payload = json.dumps(request) + "\n"
        self.proc.stdin.write(payload.encode("utf-8"))
        await self.proc.stdin.drain()
        logger.debug(f"Sent request to MCP server: {payload.strip()}")

        # Await with a 10s timeout
        try:
            return await asyncio.wait_for(future, timeout=10.0)
        except asyncio.TimeoutError:
            self.pending_requests.pop(req_id, None)
            raise TimeoutError(f"MCP request '{method}' timed out after 10 seconds.")

    async def send_notification(self, method: str, params: Optional[Dict[str, Any]] = None):
        """
        Sends a JSON-RPC 2.0 notification (no response expected).
        """
        if not self.is_connected or not self.proc or not self.proc.stdin:
            raise Exception("MCP client is not connected.")

        notification = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params is not None:
            notification["params"] = params

        payload = json.dumps(notification) + "\n"
        self.proc.stdin.write(payload.encode("utf-8"))
        await self.proc.stdin.drain()
        logger.debug(f"Sent notification: {payload.strip()}")

    async def _handshake(self):
        """
        Execute the Model Context Protocol handshake.
        """
        # 1. Initialize request
        init_params = {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "FlagshipAgentWorkspace",
                "version": "1.0.0"
            }
        }
        await self.send_request("initialize", init_params)
        
        # 2. Initialized notification
        await self.send_notification("notifications/initialized")

    async def list_tools(self) -> List[Dict[str, Any]]:
        """
        Retrieves the list of tools exposed by the MCP server.
        """
        result = await self.send_request("tools/list")
        return result.get("tools", [])

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        """
        Calls a tool on the MCP server. Returns the textual result representation.
        Supports up to 3 exponential backoff retries on failure.
        """
        params = {
            "name": name,
            "arguments": arguments
        }
        
        max_retries = 3
        backoff = 1.0
        for attempt in range(1, max_retries + 1):
            try:
                result = await self.send_request("tools/call", params)
                content_items = result.get("content", [])
                
                text_responses = []
                for item in content_items:
                    if item.get("type") == "text":
                        text_responses.append(item.get("text", ""))
                return "\n".join(text_responses)
            except Exception as e:
                logger.warning(f"MCP tool call '{name}' attempt {attempt} failed: {e}")
                if attempt == max_retries:
                    raise e
                await asyncio.sleep(backoff)
                backoff *= 2.0

    async def close(self):
        """
        Cleans up reader loop and terminates the subprocess.
        """
        logger.info("Closing MCP Stdio connection.")
        self.is_connected = False
        
        if self.reader_task:
            self.reader_task.cancel()
            try:
                await self.reader_task
            except asyncio.CancelledError:
                pass
                
        # Resolve any leftover futures
        for future in self.pending_requests.values():
            if not future.done():
                future.set_exception(Exception("Connection closed."))
        self.pending_requests.clear()

        if self.proc:
            try:
                self.proc.terminate()
                # Wait briefly for process to exit
                await asyncio.wait_for(self.proc.wait(), timeout=2.0)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None


class McpHttpClient:
    """
    Remote MCP client using HTTP/JSON-RPC 2.0 (or SSE transport).
    Connects to deployed MCP server URLs (e.g. https://my-mcp-tool.vercel.app/mcp).
    """

    def __init__(self, url: str, auth_header: Optional[str] = None, transport_type: str = "http_jsonrpc"):
        import httpx
        self.url = url.strip()
        self.auth_header = auth_header.strip() if auth_header else None
        self.transport_type = transport_type
        self.session_id: Optional[str] = None
        self.is_connected = False
        self._handshake_done = False   # tracks whether MCP initialize was completed
        self.next_request_id = 1
        self._client: Optional[httpx.AsyncClient] = None

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": "Antigravity-AI-Chatbot-MCP-Client/1.0",
        }
        if self.session_id:
            headers["mcp-session-id"] = self.session_id
        if self.auth_header:
            if self.auth_header.startswith("Bearer ") or ":" in self.auth_header:
                if ":" in self.auth_header and not self.auth_header.startswith("Bearer "):
                    k, v = self.auth_header.split(":", 1)
                    headers[k.strip()] = v.strip()
                else:
                    headers["Authorization"] = self.auth_header
            else:
                headers["Authorization"] = f"Bearer {self.auth_header}"
        return headers

    async def _ensure_client(self):
        import httpx
        if self._client is None or self._client.is_closed:
            # Closed client means the TCP connection was dropped.
            # Create a new client AND mark handshake as incomplete so
            # send_request re-runs MCP initialize before the next tool call.
            self._client = httpx.AsyncClient(timeout=15.0, headers=self._get_headers())
            self._handshake_done = False
            self.session_id = None
            logger.info(f"[McpHttpClient] Re-created HTTP client for {self.url}; will re-handshake.")

    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        text = response_text.strip()
        if not text:
            return {}
        if text.startswith("{") and text.endswith("}"):
            return json.loads(text)
        # Parse SSE lines starting with 'data:'
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                data_str = line[5:].strip()
                if data_str:
                    return json.loads(data_str)
        try:
            return json.loads(text)
        except Exception:
            return {"result": text}

    def _extract_session_id(self, res) -> Optional[str]:
        sess_id = (
            res.headers.get("mcp-session-id") or
            res.headers.get("Mcp-Session-Id") or
            res.headers.get("session-id")
        )
        return sess_id

    async def send_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        await self._ensure_client()

        # If the client was re-created (handshake lost), re-initialize before
        # sending any tool/list requests so session_id is valid.
        if not self._handshake_done and method not in ("initialize", "notifications/initialized"):
            logger.info(f"[McpHttpClient] Re-running MCP handshake for {self.url}")
            try:
                init_params = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "AntigravityRemoteMcpClient", "version": "1.0.0"},
                }
                await self.send_request("initialize", init_params)
                await self.send_notification("notifications/initialized")
                self._handshake_done = True
            except Exception as hs_err:
                logger.warning(f"[McpHttpClient] Re-handshake warning: {hs_err}")
                self._handshake_done = True  # proceed anyway; server may not require it

        req_id = self.next_request_id
        self.next_request_id += 1

        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
        }
        if params is not None:
            payload["params"] = params

        headers = self._get_headers()
        logger.info(
            f"[Remote MCP Request] URL: {self.url} | Method: {method} | req_id: {req_id} | "
            f"session_id: {self.session_id} | payload: {json.dumps(payload)}"
        )

        try:
            res = await self._client.post(self.url, json=payload, headers=headers)
            new_session_id = self._extract_session_id(res)
            if new_session_id:
                self.session_id = new_session_id
                logger.info(f"[Remote MCP Session] Received mcp-session-id: {self.session_id}")

            res.raise_for_status()

            data = self._parse_response(res.text)
            logger.info(
                f"[Remote MCP Response] URL: {self.url} | Method: {method} | "
                f"Status: {res.status_code} | response: {json.dumps(data)[:500]}"
            )

            if "error" in data:
                err_info = data["error"]
                err_text = err_info.get("message", str(err_info)) if isinstance(err_info, dict) else str(err_info)
                raise Exception(f"Remote MCP Error ({method}): {err_text}")
            return data.get("result")
        except Exception as e:
            logger.error(f"[Remote MCP Failed] URL: {self.url} | Method: {method} | error: {str(e)}")
            raise e

    async def send_notification(self, method: str, params: Optional[Dict[str, Any]] = None):
        await self._ensure_client()
        payload = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params is not None:
            payload["params"] = params
        try:
            headers = self._get_headers()
            logger.info(f"[Remote MCP Notification] URL: {self.url} | Method: {method}")
            res = await self._client.post(self.url, json=payload, headers=headers)
            new_session_id = self._extract_session_id(res)
            if new_session_id:
                self.session_id = new_session_id
        except Exception as e:
            logger.warning(f"Remote MCP notification error ({self.url}): {str(e)}")

    async def connect(self):
        logger.info(f"[Remote MCP Connect] Initializing connection to URL: {self.url}")
        try:
            init_params = {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "AntigravityRemoteMcpClient",
                    "version": "1.0.0"
                }
            }
            await self._ensure_client()
            try:
                self._handshake_done = True  # prevent re-entrant re-handshake
                await self.send_request("initialize", init_params)
                await self.send_notification("notifications/initialized")
            except Exception as init_err:
                logger.warning(f"[Remote MCP Handshake Warning] Handshake warning for {self.url}: {init_err}")
            self.is_connected = True
            self._handshake_done = True
            logger.info(f"[Remote MCP Handshake Successful] Connected to {self.url} with session_id={self.session_id}")
        except Exception as e:
            self.is_connected = False
            self._handshake_done = False
            logger.error(f"Failed to connect to Remote MCP Server ({self.url}): {e}")
            raise e

    async def list_tools(self) -> List[Dict[str, Any]]:
        logger.info(f"[Remote MCP list_tools] Requesting tools/list from {self.url}")
        result = await self.send_request("tools/list")
        tools = []
        if isinstance(result, dict):
            tools = result.get("tools", [])
        elif isinstance(result, list):
            tools = result

        logger.info(f"[Remote MCP list_tools] Discovered {len(tools)} tools: {[t.get('name') for t in tools]}")
        return tools

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        if arguments is None or not isinstance(arguments, dict):
            logger.warning(f"[Remote MCP call_tool] Normalizing arguments from {type(arguments)} to dict for tool '{name}'")
            arguments = {}

        params = {
            "name": name,
            "arguments": arguments
        }

        logger.info(
            f"[Remote MCP call_tool Request] Tool: {name} | Arguments: {json.dumps(arguments)} | "
            f"Server URL: {self.url} | Session ID: {self.session_id}"
        )

        max_retries = 2
        backoff = 1.0
        for attempt in range(1, max_retries + 1):
            try:
                result = await self.send_request("tools/call", params)
                if not result:
                    return f"Tool '{name}' executed with no response content."

                # Check if result indicates error
                if isinstance(result, dict) and result.get("isError"):
                    content_items = result.get("content", [])
                    err_texts = [item.get("text", "") for item in content_items if isinstance(item, dict) and item.get("type") == "text"]
                    error_msg = "\n".join(err_texts) if err_texts else json.dumps(result)
                    raise Exception(f"Server returned tool error: {error_msg}")

                content_items = result.get("content", []) if isinstance(result, dict) else []
                text_responses = []
                for item in content_items:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text_responses.append(item.get("text", ""))

                if text_responses:
                    final_text = "\n".join(text_responses)
                    logger.info(f"[Remote MCP call_tool Success] Tool: {name} | Result snippet: {final_text[:300]}")
                    return final_text

                res_str = json.dumps(result) if isinstance(result, (dict, list)) else str(result)
                logger.info(f"[Remote MCP call_tool Success] Tool: {name} | Result: {res_str[:300]}")
                return res_str
            except Exception as e:
                logger.warning(f"Remote MCP tool call '{name}' attempt {attempt}/{max_retries} failed: {e}")
                if attempt == max_retries:
                    raise
                await asyncio.sleep(backoff)
                backoff *= 2.0  # exponential backoff: 1s → 2s

    async def close(self):
        self.is_connected = False
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None


