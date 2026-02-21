"""
Tool calling support for Bacchus.

Handles slash command parsing and MCP tool execution.
Adapters are generated from MCP metadata - no LLM reasoning involved.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from bacchus.mcp.client import MCPTool


logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    """Parsed tool call from slash command."""
    tool_name: str
    arguments: Dict[str, Any]
    server_name: str = ""


# Slash command mappings to MCP tools
SLASH_COMMANDS = {
    "read": ("filesystem", "read_file"),
    "write": ("filesystem", "write_file"),
    "list": ("filesystem", "list_directory"),
    "run": ("cmd", "execute_command"),
}


def parse_slash_command(message: str) -> Optional[ToolCall]:
    """
    Parse a slash command from user input.

    Supported commands:
        /read <path>     - Read file contents
        /write <path>    - Write to file (content from next message)
        /list <path>     - List directory contents
        /run <command>   - Execute shell command

    Args:
        message: User input text

    Returns:
        ToolCall if valid slash command, None otherwise
    """
    if not message.startswith("/"):
        return None

    parts = message[1:].split(maxsplit=1)
    if not parts:
        return None

    command = parts[0].lower()
    argument = parts[1] if len(parts) > 1 else ""

    if command not in SLASH_COMMANDS:
        return None

    server_name, tool_name = SLASH_COMMANDS[command]

    # Build arguments based on command type
    if command == "read":
        if not argument:
            logger.warning("read command requires a path")
            return None
        arguments = {"path": argument.strip()}

    elif command == "write":
        if not argument:
            logger.warning("write command requires a path")
            return None
        # Content will be provided separately or in a dialog
        arguments = {"path": argument.strip(), "content": ""}

    elif command == "list":
        # Default to current directory if no path
        arguments = {"path": argument.strip() if argument else "."}

    elif command == "run":
        if not argument:
            logger.warning("run command requires a command string")
            return None
        arguments = {"command": argument.strip()}

    else:
        return None

    return ToolCall(
        tool_name=tool_name,
        arguments=arguments,
        server_name=server_name
    )


def generate_capability_schema(tool: MCPTool, server_name: str) -> Dict[str, Any]:
    """
    Generate a capability schema from MCP tool metadata.

    This is pure metadata transformation - no AI involved.

    Args:
        tool: MCP tool definition
        server_name: Name of the MCP server

    Returns:
        Canonical capability schema
    """
    # Extract fields from JSON schema
    fields = []
    params = tool.parameters or {}
    properties = params.get("properties", {})
    required = params.get("required", [])

    for name, prop in properties.items():
        field = {
            "name": name,
            "source": name,
            "type": prop.get("type", "string"),
            "required": name in required,
            "description": prop.get("description", "")
        }
        fields.append(field)

    # Generate keywords from name and description
    keywords = _extract_keywords(tool.name, tool.description)

    return {
        "capability_id": f"{server_name}.{tool.name}",
        "server": server_name,
        "tool": tool.name,
        "description": tool.description,
        "keywords": keywords,
        "fields": fields,
        "output": {
            "max_chars": 2000
        }
    }


def _extract_keywords(name: str, description: str) -> List[str]:
    """
    Extract keywords from tool name and description.

    Simple rules-based extraction - no AI.

    Args:
        name: Tool name
        description: Tool description

    Returns:
        List of keywords
    """
    # Split name on underscores and hyphens
    name_words = name.replace("_", " ").replace("-", " ").lower().split()

    # Extract key words from description
    desc_words = description.lower().split()

    # Common stop words to filter
    stop_words = {
        "a", "an", "the", "is", "are", "was", "were", "be", "been",
        "to", "of", "in", "for", "on", "with", "at", "by", "from",
        "this", "that", "these", "those", "it", "its"
    }

    # Combine and filter
    all_words = set(name_words + desc_words)
    keywords = [w for w in all_words if w not in stop_words and len(w) > 2]

    return keywords[:10]  # Limit to 10 keywords


def format_tool_result(tool_name: str, result: str, success: bool = True) -> str:
    """
    Format a tool result for display in the conversation.

    Args:
        tool_name: Name of the tool that was called
        result: Result text from tool execution
        success: Whether the tool call succeeded

    Returns:
        Formatted result string
    """
    if success:
        return f"[{tool_name}]: {result}"
    else:
        return f"[{tool_name}] Error: {result}"


def get_running_servers(mcp_manager) -> List[str]:
    """
    Get list of running MCP servers.

    Args:
        mcp_manager: MCPManager instance

    Returns:
        List of server names
    """
    if not mcp_manager:
        return []

    running = []
    for server in mcp_manager.list_servers():
        if server.status == "running":
            running.append(server.name)

    return running


def get_available_commands() -> List[str]:
    """
    Get list of available slash commands.

    Returns:
        List of command names (without slash prefix)
    """
    return list(SLASH_COMMANDS.keys())
