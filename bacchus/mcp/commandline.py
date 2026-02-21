"""
Built-in command line MCP server for Bacchus.

Provides tool for executing shell commands with security restrictions.

Run as: python -m bacchus.mcp.commandline
"""

import json
import os
import subprocess
import sys
from typing import Any, Dict, List


class CommandLineServer:
    """MCP server for command line execution."""

    def __init__(self, timeout: int = 30, blocked_commands: List[str] = None):
        """
        Initialize command line server.

        Args:
            timeout: Command execution timeout in seconds
            blocked_commands: List of blocked command names
        """
        self.timeout = timeout
        self.blocked_commands = blocked_commands or []

    def _is_command_blocked(self, command: str) -> bool:
        """
        Check if a command is blocked.

        Args:
            command: Command string to check

        Returns:
            True if command is blocked
        """
        # Get the first word (command name)
        cmd_parts = command.strip().split()
        if not cmd_parts:
            return False

        cmd_name = cmd_parts[0].lower()

        # Check against blocked list
        for blocked in self.blocked_commands:
            if cmd_name == blocked.lower() or cmd_name.endswith(f"\\{blocked.lower()}"):
                return True

        return False

    def execute_command(self, command: str) -> Dict[str, Any]:
        """
        Execute a shell command.

        Args:
            command: Command to execute

        Returns:
            Result with command output or error
        """
        if self._is_command_blocked(command):
            return {
                "content": [{
                    "type": "text",
                    "text": f"Error: Command '{command.split()[0]}' is blocked for security reasons."
                }]
            }

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )

            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]\n{result.stderr}"

            if result.returncode != 0:
                output += f"\n[Exit code: {result.returncode}]"

            return {
                "content": [{
                    "type": "text",
                    "text": output or "(command produced no output)"
                }]
            }

        except subprocess.TimeoutExpired:
            return {
                "content": [{
                    "type": "text",
                    "text": f"Error: Command timed out after {self.timeout} seconds"
                }]
            }
        except Exception as e:
            return {
                "content": [{
                    "type": "text",
                    "text": f"Error executing command: {str(e)}"
                }]
            }

    def get_tools(self) -> List[Dict[str, Any]]:
        """Get list of available tools."""
        return [
            {
                "name": "execute_command",
                "description": "Execute a shell command",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The command to execute"
                        }
                    },
                    "required": ["command"]
                }
            }
        ]


def run_server():
    """Run the command line MCP server."""
    # Try to load config from environment, otherwise use defaults
    config_json = os.environ.get("BACCHUS_MCP_CONFIG", "{}")
    
    try:
        config = json.loads(config_json)
        timeout = config.get("timeout", 30)
        blocked_commands = config.get("blocked_commands", [
            "rm", "rmdir", "del", "format", "shutdown", "reboot"
        ])
    except json.JSONDecodeError:
        # Fallback to defaults
        timeout = 30
        blocked_commands = ["rm", "rmdir", "del", "format", "shutdown", "reboot"]

    server = CommandLineServer(timeout, blocked_commands)
    request_id = 0

    # JSON-RPC 2.0 over stdio
    for line in sys.stdin:
        try:
            request = json.loads(line.strip())
            request_id = request.get("id", 0)
            method = request.get("method", "")
            params = request.get("params", {})

            if method == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {}
                        },
                        "serverInfo": {
                            "name": "cmd",
                            "version": "0.1.0"
                        }
                    }
                }
            elif method == "tools/list":
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "tools": server.get_tools()
                    }
                }
            elif method == "tools/call":
                tool_name = params.get("name", "")
                arguments = params.get("arguments", {})

                if tool_name == "execute_command":
                    result = server.execute_command(arguments.get("command", ""))
                else:
                    result = {
                        "content": [{
                            "type": "text",
                            "text": f"Error: Unknown tool '{tool_name}'"
                        }]
                    }

                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": result
                }
            elif method == "shutdown":
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {}
                }
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
                break
            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}"
                    }
                }

            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()

        except Exception as e:
            error_response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32603,
                    "message": f"Internal error: {str(e)}"
                }
            }
            sys.stdout.write(json.dumps(error_response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    run_server()
