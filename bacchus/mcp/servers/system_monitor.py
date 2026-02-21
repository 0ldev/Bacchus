"""
System Monitor MCP Server.

Provides system information: CPU, memory, disk, processes.
All tools work offline with no arguments needed.
"""

import json
import logging
import sys
import psutil
from typing import Any, Dict

logger = logging.getLogger(__name__)


class SystemMonitorServer:
    """
    MCP server for system monitoring.

    Provides tools to get CPU, memory, disk, and process information.
    """

    def __init__(self):
        """Initialize system monitor server."""
        self.name = "system-monitor"

    def get_tools(self) -> list[Dict[str, Any]]:
        """
        Get list of available tools.

        Returns:
            List of tool definitions in MCP format
        """
        return [
            {
                "name": "get_cpu_usage",
                "description": "Get current CPU usage percentage",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "get_memory_info",
                "description": "Get memory usage information (RAM)",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "get_disk_usage",
                "description": "Get disk space usage for all drives",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "list_processes",
                "description": "List running processes with CPU and memory usage",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "number",
                            "description": "Maximum number of processes to return (default: 10)"
                        }
                    },
                    "required": []
                }
            },
            {
                "name": "get_system_info",
                "description": "Get system information (OS, platform, uptime)",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        ]

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool.

        Args:
            tool_name: Name of tool to execute
            arguments: Tool arguments

        Returns:
            Tool result
        """
        try:
            if tool_name == "get_cpu_usage":
                return self._get_cpu_usage()
            elif tool_name == "get_memory_info":
                return self._get_memory_info()
            elif tool_name == "get_disk_usage":
                return self._get_disk_usage()
            elif tool_name == "list_processes":
                limit = arguments.get("limit", 10)
                return self._list_processes(limit)
            elif tool_name == "get_system_info":
                return self._get_system_info()
            else:
                return {
                    "error": f"Unknown tool: {tool_name}"
                }

        except Exception as e:
            logger.error(f"Error executing {tool_name}: {e}", exc_info=True)
            return {
                "error": str(e)
            }

    def _get_cpu_usage(self) -> Dict[str, Any]:
        """Get CPU usage."""
        # Get overall CPU percentage
        cpu_percent = psutil.cpu_percent(interval=0.5)

        # Get per-core percentages
        per_cpu = psutil.cpu_percent(interval=0.5, percpu=True)

        return {
            "cpu_percent": cpu_percent,
            "cpu_count": psutil.cpu_count(),
            "per_cpu_percent": per_cpu
        }

    def _get_memory_info(self) -> Dict[str, Any]:
        """Get memory information."""
        mem = psutil.virtual_memory()

        return {
            "total_gb": round(mem.total / (1024**3), 2),
            "used_gb": round(mem.used / (1024**3), 2),
            "available_gb": round(mem.available / (1024**3), 2),
            "percent": mem.percent
        }

    def _get_disk_usage(self) -> Dict[str, Any]:
        """Get disk usage for all partitions."""
        partitions = []

        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                partitions.append({
                    "device": partition.device,
                    "mountpoint": partition.mountpoint,
                    "total_gb": round(usage.total / (1024**3), 2),
                    "used_gb": round(usage.used / (1024**3), 2),
                    "free_gb": round(usage.free / (1024**3), 2),
                    "percent": usage.percent
                })
            except PermissionError:
                # Skip partitions we can't access
                continue

        return {
            "partitions": partitions
        }

    def _list_processes(self, limit: int = 10) -> Dict[str, Any]:
        """List top processes by CPU usage."""
        processes = []

        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                info = proc.info
                processes.append({
                    "pid": info['pid'],
                    "name": info['name'],
                    "cpu_percent": info['cpu_percent'] or 0.0,
                    "memory_percent": round(info['memory_percent'] or 0.0, 2)
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Sort by CPU usage descending
        processes.sort(key=lambda x: x['cpu_percent'], reverse=True)

        return {
            "processes": processes[:limit]
        }

    def _get_system_info(self) -> Dict[str, Any]:
        """Get system information."""
        import platform
        from datetime import datetime, timedelta

        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot_time

        return {
            "platform": platform.system(),
            "platform_release": platform.release(),
            "platform_version": platform.version(),
            "architecture": platform.machine(),
            "processor": platform.processor(),
            "python_version": sys.version,
            "boot_time": boot_time.isoformat(),
            "uptime_seconds": int(uptime.total_seconds()),
            "uptime_human": str(uptime).split('.')[0]  # Remove microseconds
        }


def main():
    """
    Run system monitor as standalone MCP server (stdio mode).

    Reads JSON-RPC requests from stdin, writes responses to stdout.
    """
    server = SystemMonitorServer()

    # Read line by line from stdin
    for line in sys.stdin:
        try:
            request = json.loads(line)

            # Handle tools/list
            if request.get("method") == "tools/list":
                response = {
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "result": {
                        "tools": server.get_tools()
                    }
                }

            # Handle tools/call
            elif request.get("method") == "tools/call":
                params = request.get("params", {})
                tool_name = params.get("name")
                arguments = params.get("arguments", {})

                result = server.call_tool(tool_name, arguments)

                response = {
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "result": result
                }

            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {request.get('method')}"
                    }
                }

            # Write response
            print(json.dumps(response), flush=True)

        except Exception as e:
            logger.error(f"Error handling request: {e}", exc_info=True)
            error_response = {
                "jsonrpc": "2.0",
                "id": request.get("id") if 'request' in locals() else None,
                "error": {
                    "code": -32603,
                    "message": str(e)
                }
            }
            print(json.dumps(error_response), flush=True)


if __name__ == "__main__":
    main()
