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
        """
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
        """
        params = {
            "name": name,
            "arguments": arguments
        }
        result = await self.send_request("tools/call", params)
        content_items = result.get("content", [])
        
        text_responses = []
        for item in content_items:
            if item.get("type") == "text":
                text_responses.append(item.get("text", ""))
        return "\n".join(text_responses)

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
