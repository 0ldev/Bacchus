"""
MCP Client for Bacchus.

Handles JSON-RPC communication with MCP servers via stdio.
"""

import json
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from threading import Lock
import logging

logger = logging.getLogger(__name__)


@dataclass
class MCPCall:
    """Record of an MCP tool call."""
    server: str
    tool: str
    params: Dict[str, Any]
    result: Optional[str] = None
    success: bool = False
    error: Optional[str] = None
    duration_ms: int = 0


@dataclass
class MCPTool:
    """Definition of an MCP tool."""
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)


class MCPClient:
    """
    Client for communicating with an MCP server.

    Handles JSON-RPC 2.0 protocol over stdin/stdout.
    """

    def __init__(self, process: subprocess.Popen, server_name: str):
        """
        Initialize MCP client.

        Args:
            process: Running server process with stdin/stdout pipes
            server_name: Name of the server for logging
        """
        self.process = process
        self.server_name = server_name
        self._request_id = 0
        self._lock = Lock()
        self._tools: List[MCPTool] = []

    def _next_id(self) -> int:
        """Get next request ID."""
        with self._lock:
            self._request_id += 1
            return self._request_id

    def _send_request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = 30.0
    ) -> Dict[str, Any]:
        """
        Send a JSON-RPC request to the server.

        Args:
            method: RPC method name
            params: Optional parameters
            timeout: Request timeout in seconds

        Returns:
            Response result or raises exception

        Raises:
            TimeoutError: If request times out
            RuntimeError: If server returns an error
        """
        request_id = self._next_id()
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params:
            request["params"] = params

        # Send request
        request_line = json.dumps(request) + "\n"
        self.process.stdin.write(request_line)
        self.process.stdin.flush()

        # Read response (simple blocking read)
        # In production, this would use select() or async I/O
        import select
        import sys

        if sys.platform == 'win32':
            # Windows doesn't support select on pipes
            # Use simple blocking read with thread timeout
            response_line = self.process.stdout.readline()
        else:
            # Unix can use select
            ready, _, _ = select.select([self.process.stdout], [], [], timeout)
            if not ready:
                raise TimeoutError(f"MCP request timed out after {timeout}s")
            response_line = self.process.stdout.readline()

        if not response_line:
            raise RuntimeError("Server closed connection")

        response = json.loads(response_line)

        if "error" in response:
            error = response["error"]
            raise RuntimeError(f"MCP error: {error.get('message', 'Unknown error')}")

        return response.get("result", {})

    def initialize(self) -> bool:
        """
        Initialize connection with server.

        Returns:
            True if successful
        """
        try:
            result = self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "Bacchus",
                    "version": "0.1.0"
                }
            })
            return True
        except Exception:
            return False

    def list_tools(self) -> List[MCPTool]:
        """
        Get list of available tools from server.

        Returns:
            List of MCPTool definitions
        """
        try:
            result = self._send_request("tools/list")
            tools = []
            for tool_data in result.get("tools", []):
                tools.append(MCPTool(
                    name=tool_data.get("name", ""),
                    description=tool_data.get("description", ""),
                    parameters=tool_data.get("inputSchema", {})
                ))
            self._tools = tools
            return tools
        except Exception:
            return []

    def _validate_arguments(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> None:
        """
        Validate tool arguments against JSON schema.

        This is CRITICAL for safety with small models that may produce
        malformed JSON or hallucinate arguments.

        Args:
            tool_name: Name of the tool
            arguments: Arguments to validate

        Raises:
            ValueError: If validation fails
        """
        # Find the tool schema
        tool = None
        for t in self._tools:
            if t.name == tool_name:
                tool = t
                break

        if not tool:
            raise ValueError(f"Tool '{tool_name}' not found in server '{self.server_name}'")

        if not tool.parameters:
            # No schema defined, skip validation
            return

        try:
            from jsonschema import validate, ValidationError

            # Validate arguments against the schema
            validate(instance=arguments, schema=tool.parameters)

        except ImportError:
            # jsonschema not installed, log warning but continue
            logger.warning("jsonschema not installed - skipping argument validation")
            logger.warning("Install with: pip install jsonschema")
            return

        except ValidationError as e:
            # Schema validation failed - this is a safety-critical error
            error_msg = f"Invalid arguments for tool '{tool_name}': {e.message}"

            # Add helpful context about what was expected
            if hasattr(e, 'schema'):
                required = e.schema.get('required', [])
                if required:
                    error_msg += f"\n  Required fields: {', '.join(required)}"

            logger.error(error_msg)
            raise ValueError(error_msg)

        except Exception as e:
            # Other validation errors
            logger.error(f"Unexpected error validating arguments for '{tool_name}': {e}")
            raise ValueError(f"Argument validation failed: {e}")

    def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        timeout: float = 30.0
    ) -> MCPCall:
        """
        Call a tool on the server.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments
            timeout: Request timeout in seconds

        Returns:
            MCPCall with result or error
        """
        import time
        start_time = time.time()

        call = MCPCall(
            server=self.server_name,
            tool=tool_name,
            params=arguments
        )

        try:
            # CRITICAL: Validate arguments against schema BEFORE calling server
            # This protects against malformed JSON from small models
            self._validate_arguments(tool_name, arguments)

            result = self._send_request(
                "tools/call",
                {"name": tool_name, "arguments": arguments},
                timeout=timeout
            )

            # Extract text content from result
            content = result.get("content", [])
            if content and isinstance(content, list):
                text_parts = [
                    c.get("text", "")
                    for c in content
                    if c.get("type") == "text"
                ]
                call.result = "\n".join(text_parts)
            else:
                call.result = str(result)

            call.success = True

        except TimeoutError as e:
            call.error = f"Timeout: {e}"
            call.success = False
        except Exception as e:
            call.error = str(e)
            call.success = False

        call.duration_ms = int((time.time() - start_time) * 1000)
        return call

    def shutdown(self) -> None:
        """Gracefully shut down the connection."""
        try:
            self._send_request("shutdown", timeout=5.0)
        except Exception:
            pass  # Ignore shutdown errors

    def is_alive(self) -> bool:
        """Check if the server process is still running."""
        return self.process.poll() is None
