"""
Tool context generation for system prompts.

Builds tool descriptions to include in the system message so the LLM
knows what tools are available and how to request their use.
"""

import logging
from typing import List, Dict, Any, Optional


logger = logging.getLogger(__name__)


def generate_tool_context(mcp_manager) -> str:
    """
    Generate tool availability context for system prompt.

    This tells the LLM what tools are available and how to request them.

    Args:
        mcp_manager: MCPManager instance with running servers

    Returns:
        Tool context string to append to system prompt
    """
    if not mcp_manager:
        return ""

    # Get all running servers and their tools
    available_tools = []

    for server in mcp_manager.list_servers():
        if server.status == "running" and server.client:
            try:
                tools = server.client._tools
                for tool in tools:
                    available_tools.append({
                        "server": server.name,
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters
                    })
            except Exception as e:
                logger.warning(f"Failed to get tools from {server.name}: {e}")

    if not available_tools:
        return ""

    return _build_english_tool_context(available_tools)


def _build_english_tool_context(tools: List[Dict[str, Any]]) -> str:
    """Build English tool context."""
    lines = [
        "",
        "## Available Tools",
        "",
        "You have access to the following tools. To request a tool, instruct the user to use the slash command format.",
        ""
    ]

    # Group by server
    tools_by_server: Dict[str, List[Dict]] = {}
    for tool in tools:
        server = tool["server"]
        if server not in tools_by_server:
            tools_by_server[server] = []
        tools_by_server[server].append(tool)

    # Format each server's tools
    for server_name, server_tools in tools_by_server.items():
        lines.append(f"### {server_name.capitalize()} Server")
        lines.append("")

        for tool in server_tools:
            # Map tool names to slash commands
            slash_cmd = _tool_to_slash_command(tool["name"])

            lines.append(f"**{slash_cmd}** - {tool['description']}")

            # Add parameter info if available
            if tool["parameters"] and "properties" in tool["parameters"]:
                props = tool["parameters"]["properties"]
                required = tool["parameters"].get("required", [])

                param_desc = []
                for param_name, param_info in props.items():
                    is_required = param_name in required
                    req_marker = " (required)" if is_required else " (optional)"
                    param_desc.append(f"  - `{param_name}`: {param_info.get('description', '')}{req_marker}")

                if param_desc:
                    lines.append("  Parameters:")
                    lines.extend(param_desc)

            lines.append("")

    lines.append("**How to use:** When the user needs a tool, suggest they use the appropriate slash command.")
    lines.append("Example: \"You can use `/read filename.txt` to read that file.\"")
    lines.append("")

    return "\n".join(lines)





def _tool_to_slash_command(tool_name: str) -> str:
    """
    Convert MCP tool name to slash command.

    Maps MCP tool names to user-facing slash commands.

    Args:
        tool_name: MCP tool name (e.g., "read_file")

    Returns:
        Slash command (e.g., "/read")
    """
    # Mapping from MCP tool names to slash commands
    mapping = {
        "read_file": "/read",
        "write_file": "/write",
        "list_directory": "/list",
        "execute_command": "/run",
        "search_web": "/search",
        "http_get": "/get",
        "http_post": "/post",
    }

    return mapping.get(tool_name, f"/{tool_name}")


def get_tool_list_for_display(mcp_manager) -> List[str]:
    """
    Get simple list of available slash commands for UI display.

    Args:
        mcp_manager: MCPManager instance

    Returns:
        List of slash commands (e.g., ["/read", "/write", "/list"])
    """
    if not mcp_manager:
        return []

    commands = set()

    for server in mcp_manager.list_servers():
        if server.status == "running" and server.client:
            try:
                tools = server.client._tools
                for tool in tools:
                    slash_cmd = _tool_to_slash_command(tool.name)
                    commands.add(slash_cmd)
            except Exception:
                pass

    return sorted(commands)
