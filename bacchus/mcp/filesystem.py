"""
Built-in filesystem MCP server for Bacchus.

Provides tools for reading, writing, and listing files.
Enforces security restrictions via allowed_paths configuration.

Run as: python -m bacchus.mcp.filesystem
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List


class FilesystemServer:
    """MCP server for filesystem operations."""

    def __init__(self, allowed_paths: List[str]):
        """
        Initialize filesystem server.

        Args:
            allowed_paths: List of allowed directory paths
        """
        # Expand environment variables in allowed paths
        self.allowed_paths = [
            Path(self._expand_path(p)).resolve() for p in allowed_paths
        ]

    @staticmethod
    def _expand_path(path: str) -> str:
        """Expand environment variables in path."""
        import re
        
        def replace_windows_var(match):
            var_name = match.group(1)
            return os.environ.get(var_name, match.group(0))
        
        result = re.sub(r'%([^%]+)%', replace_windows_var, path)
        result = os.path.expandvars(result)
        return result

    def _is_path_allowed(self, path: str) -> bool:
        """
        Check if a path is within allowed directories.

        Args:
            path: Path to check

        Returns:
            True if path is allowed
        """
        try:
            resolved_path = Path(path).resolve()
            
            for allowed in self.allowed_paths:
                try:
                    resolved_path.relative_to(allowed)
                    return True
                except ValueError:
                    continue
            
            return False
        except Exception:
            return False

    def read_file(self, path: str) -> Dict[str, Any]:
        """
        Read file contents.

        Args:
            path: Path to file

        Returns:
            Result with file contents or error
        """
        if not self._is_path_allowed(path):
            return {
                "content": [{
                    "type": "text",
                    "text": f"Error: Access denied. Path '{path}' is outside allowed directories."
                }]
            }

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            
            return {
                "content": [{
                    "type": "text",
                    "text": content
                }]
            }
        except FileNotFoundError:
            return {
                "content": [{
                    "type": "text",
                    "text": f"Error: File not found: {path}"
                }]
            }
        except Exception as e:
            return {
                "content": [{
                    "type": "text",
                    "text": f"Error reading file: {str(e)}"
                }]
            }

    def write_file(self, path: str, content: str) -> Dict[str, Any]:
        """
        Write content to file.

        Args:
            path: Path to file
            content: Content to write

        Returns:
            Result with success message or error
        """
        if not self._is_path_allowed(path):
            return {
                "content": [{
                    "type": "text",
                    "text": f"Error: Access denied. Path '{path}' is outside allowed directories."
                }]
            }

        try:
            # Create parent directories if needed
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            
            return {
                "content": [{
                    "type": "text",
                    "text": f"Successfully wrote {len(content)} bytes to {path}"
                }]
            }
        except Exception as e:
            return {
                "content": [{
                    "type": "text",
                    "text": f"Error writing file: {str(e)}"
                }]
            }

    def create_directory(self, path: str) -> Dict[str, Any]:
        """
        Create a directory (and any missing parents).

        Args:
            path: Path of the directory to create

        Returns:
            Result with success message or error
        """
        if not self._is_path_allowed(path):
            return {
                "content": [{
                    "type": "text",
                    "text": f"Error: Access denied. Path '{path}' is outside allowed directories."
                }]
            }

        try:
            Path(path).mkdir(parents=True, exist_ok=True)
            return {
                "content": [{
                    "type": "text",
                    "text": f"Directory created: {path}"
                }]
            }
        except Exception as e:
            return {
                "content": [{
                    "type": "text",
                    "text": f"Error creating directory: {str(e)}"
                }]
            }

    def edit_file(self, path: str, old_str: str, new_str: str) -> Dict[str, Any]:
        """
        Edit a file by replacing an exact string occurrence.

        Args:
            path: Path to the file
            old_str: Exact string to find and replace
            new_str: String to replace it with

        Returns:
            Result with success message or error
        """
        if not self._is_path_allowed(path):
            return {
                "content": [{
                    "type": "text",
                    "text": f"Error: Access denied. Path '{path}' is outside allowed directories."
                }]
            }

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            if old_str not in content:
                return {
                    "content": [{
                        "type": "text",
                        "text": f"Error: String not found in {path}. Check exact whitespace and characters."
                    }]
                }

            count = content.count(old_str)
            if count > 1:
                return {
                    "content": [{
                        "type": "text",
                        "text": f"Error: String found {count} times in {path}. Add more context to make it unique."
                    }]
                }

            new_content = content.replace(old_str, new_str, 1)

            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)

            return {
                "content": [{
                    "type": "text",
                    "text": f"Successfully edited {path}"
                }]
            }
        except FileNotFoundError:
            return {
                "content": [{
                    "type": "text",
                    "text": f"Error: File not found: {path}"
                }]
            }
        except Exception as e:
            return {
                "content": [{
                    "type": "text",
                    "text": f"Error editing file: {str(e)}"
                }]
            }

    def list_directory(self, path: str) -> Dict[str, Any]:
        """
        List directory contents.

        Args:
            path: Path to directory

        Returns:
            Result with directory listing or error
        """
        if not self._is_path_allowed(path):
            return {
                "content": [{
                    "type": "text",
                    "text": f"Error: Access denied. Path '{path}' is outside allowed directories."
                }]
            }

        try:
            entries = []
            for entry in sorted(Path(path).iterdir()):
                entry_type = "dir" if entry.is_dir() else "file"
                entries.append(f"{entry_type}: {entry.name}")
            
            listing = "\n".join(entries) if entries else "(empty directory)"
            
            return {
                "content": [{
                    "type": "text",
                    "text": listing
                }]
            }
        except FileNotFoundError:
            return {
                "content": [{
                    "type": "text",
                    "text": f"Error: Directory not found: {path}"
                }]
            }
        except Exception as e:
            return {
                "content": [{
                    "type": "text",
                    "text": f"Error listing directory: {str(e)}"
                }]
            }

    def get_tools(self) -> List[Dict[str, Any]]:
        """Get list of available tools."""
        return [
            {
                "name": "read_file",
                "description": "Read the contents of a file",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the file to read"
                        }
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "write_file",
                "description": "Write content to a file",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the file to write"
                        },
                        "content": {
                            "type": "string",
                            "description": "Content to write to the file"
                        }
                    },
                    "required": ["path", "content"]
                }
            },
            {
                "name": "list_directory",
                "description": "List the contents of a directory",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the directory to list"
                        }
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "create_directory",
                "description": "Create a new directory (and any missing parent directories)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Full path of the directory to create"
                        }
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "edit_file",
                "description": (
                    "Edit a file by replacing an exact string with new content. "
                    "The old_str must match exactly (including whitespace). "
                    "Fails if old_str is not found or appears more than once."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the file to edit"
                        },
                        "old_str": {
                            "type": "string",
                            "description": "Exact string to find and replace"
                        },
                        "new_str": {
                            "type": "string",
                            "description": "String to replace old_str with"
                        }
                    },
                    "required": ["path", "old_str", "new_str"]
                }
            }
        ]


def run_server():
    """Run the filesystem MCP server."""
    # Try to load config from environment, otherwise use defaults
    config_json = os.environ.get("BACCHUS_MCP_CONFIG", "{}")
    
    try:
        config = json.loads(config_json)
        allowed_paths = config.get("allowed_paths", [
            "%USERPROFILE%/Documents",
            "%USERPROFILE%/Desktop"
        ])
    except json.JSONDecodeError:
        # Fallback to defaults
        allowed_paths = [
            "%USERPROFILE%/Documents",
            "%USERPROFILE%/Desktop"
        ]
    
    server = FilesystemServer(allowed_paths)
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
                            "name": "filesystem",
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

                if tool_name == "read_file":
                    result = server.read_file(arguments.get("path", ""))
                elif tool_name == "write_file":
                    result = server.write_file(
                        arguments.get("path", ""),
                        arguments.get("content", "")
                    )
                elif tool_name == "list_directory":
                    result = server.list_directory(arguments.get("path", ""))
                elif tool_name == "create_directory":
                    result = server.create_directory(arguments.get("path", ""))
                elif tool_name == "edit_file":
                    result = server.edit_file(
                        arguments.get("path", ""),
                        arguments.get("old_str", ""),
                        arguments.get("new_str", "")
                    )
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
