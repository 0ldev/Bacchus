"""
Autonomous tool calling for LLMs.

The LLM decides when to use tools and the system executes them automatically.
No slash commands needed - the AI determines tool usage autonomously.
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple


logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    """Parsed tool call from LLM output."""
    tool_name: str
    arguments: Dict[str, Any]
    server_name: Optional[str] = None
    raw_text: str = ""


def build_tool_system_prompt(mcp_manager) -> str:
    """
    Build system prompt section that describes available tools.

    The LLM will see this and know what tools it can use.

    Args:
        mcp_manager: MCPManager instance

    Returns:
        Tool description for system prompt
    """
    if not mcp_manager:
        return ""

    # Collect all available tools
    tools = []
    for server in mcp_manager.list_servers():
        if server.status == "running" and server.client:
            try:
                for tool in server.client._tools:
                    tools.append({
                        "server": server.name,
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters
                    })
            except Exception as e:
                logger.warning(f"Failed to get tools from {server.name}: {e}")

    if not tools:
        return ""

    return _build_english_system_prompt(tools)


def _build_english_system_prompt(tools: List[Dict[str, Any]]) -> str:
    """Build English system prompt with tool descriptions (for structured generation)."""
    lines = [
        "",
        "# Tools",
        "",
        "You have real-time access to the following tools. You MUST use them when the user's request requires it.",
        "",
        "**When to use `search_web`:**",
        "- User asks about news, current events, recent releases, prices, live data",
        "- NEVER use search_web for math, algorithms, or anything computable",
        "- NEVER repeat the same search_web query if it already returned no results — try a different approach",
        "- NEVER invent or guess URLs — only use URLs that appeared in actual search results",
        "",
        "**When to use `execute_command`:**",
        "- User asks to calculate, compute, or find a mathematical result → write Python code and run it",
        "- User asks to create, run, or test a script",
        "- User asks to check system info (disk, processes, etc.)",
        "- A previous execute_command failed → fix the code and try again, do NOT fall back to search_web",
        "",
        "**When to use `write_file` / `read_file` / `create_directory`:**",
        "- User asks to create, edit, or read a file or folder",
        "",
        "**When to output action=respond (no tool):**",
        "- User is asking a general knowledge question you can answer directly",
        "- User is chatting or asking about your capabilities",
        "",
        "**Example — user asks to calculate something — write script then run it:**",
        '{"action": "tool_call", "tool": "write_file", "arguments": {"path": "C:\\\\Users\\\\B3T0\\\\calc.py", "content": "a,b=0,1\\nfor _ in range(834):\\n    a,b=b,a+b\\nprint(b)"}}',
        "then: " + '{"action": "tool_call", "tool": "execute_command", "arguments": {"command": "python C:\\\\Users\\\\B3T0\\\\calc.py"}}',
        "",
        "**Example — user asks 'search for iphone 17':**",
        '{"action": "tool_call", "tool": "search_web", "arguments": {"query": "iphone 17"}}',
        "",
        "**Example — search returned a URL, user wants details:**",
        '{"action": "tool_call", "tool": "fetch_webpage", "arguments": {"url": "https://en.wikipedia.org/wiki/iPhone_17"}}',
        "",
        "**Example — user asks 'what is 2+2':**",
        '{"action": "respond", "response": "4"}',
        "",
        "**Available tools:**",
        ""
    ]

    for tool in tools:
        params = tool.get("parameters", {}).get("properties", {})
        param_list = ", ".join(f"`{p}`" for p in params) if params else ""
        desc = f"{tool['description']}"
        if param_list:
            desc += f" (params: {param_list})"
        lines.append(f"- **{tool['name']}**: {desc}")

    lines.append("")

    return "\n".join(lines)


def parse_tool_call(llm_output: str) -> Optional[ToolCall]:
    """
    Parse LLM output to detect tool calls.

    Looks for JSON blocks with tool calls in the format:
    ```json
    {
      "tool": "tool_name",
      "arguments": {...}
    }
    ```

    Args:
        llm_output: Raw output from the LLM

    Returns:
        ToolCall if found, None otherwise
    """
    # Look for JSON code blocks (with or without 'json' tag)
    # Try ```json first, then plain ```
    for pattern in [r'```json\s*\n(.*?)\n```', r'```\s*\n(.*?)\n```']:
        matches = re.findall(pattern, llm_output, re.DOTALL)

        for match in matches:
            try:
                data = json.loads(match)

                if "tool" in data and "arguments" in data:
                    return ToolCall(
                        tool_name=data["tool"],
                        arguments=data["arguments"],
                        raw_text=match
                    )
            except json.JSONDecodeError:
                continue

    # Also try to find raw JSON (without code blocks)
    try:
        # Find anything that looks like {"tool": ...}
        # More permissive pattern to handle nested objects
        json_pattern_raw = r'\{\s*"tool"\s*:\s*"[^"]+"\s*,\s*"arguments"\s*:\s*\{.*?\}\s*\}'
        match = re.search(json_pattern_raw, llm_output, re.DOTALL)

        if match:
            data = json.loads(match.group(0))
            return ToolCall(
                tool_name=data["tool"],
                arguments=data["arguments"],
                raw_text=match.group(0)
            )
    except (json.JSONDecodeError, AttributeError):
        pass

    return None


def execute_tool_call(tool_call: ToolCall, mcp_manager) -> Tuple[bool, str]:
    """
    Execute a tool call through MCP.

    Args:
        tool_call: Parsed tool call
        mcp_manager: MCPManager instance

    Returns:
        (success, result_text)
    """
    if not mcp_manager:
        return False, "Error: No MCP manager available"

    # Find which server provides this tool
    server_name = None
    for server in mcp_manager.list_servers():
        if server.status == "running" and server.client:
            try:
                for tool in server.client._tools:
                    if tool.name == tool_call.tool_name:
                        server_name = server.name
                        break
            except Exception:
                pass

        if server_name:
            break

    if not server_name:
        return False, f"Error: Tool '{tool_call.tool_name}' not found"

    # Get the client
    client = mcp_manager.get_client(server_name)
    if not client:
        return False, f"Error: Server '{server_name}' not available"

    # Get timeout from server config (allows per-server configuration in mcp_servers.yaml)
    timeout = 30.0
    try:
        server_obj = mcp_manager.get_server(server_name)
        if server_obj and server_obj.config:
            timeout = float(server_obj.config.get("timeout", 30.0))
    except Exception:
        pass

    # Execute the tool
    try:
        result = client.call_tool(
            tool_call.tool_name,
            tool_call.arguments,
            timeout=timeout
        )

        if result.success:
            return True, result.result or ""
        else:
            return False, f"Error: {result.error}"

    except Exception as e:
        logger.error(f"Tool execution failed: {e}")
        return False, f"Error: {str(e)}"


def format_tool_result(tool_name: str, success: bool, result: str) -> str:
    """
    Format tool result for injection back into LLM context.

    Args:
        tool_name: Name of tool that was called
        success: Whether execution succeeded
        result: Result text

    Returns:
        Formatted message for LLM
    """
    if success:
        return f"[Tool: {tool_name}]\n{result}"
    else:
        return f"[Tool: {tool_name} - Failed]\n{result}"


def should_use_tools(message: str, conversation_history: List[Dict]) -> bool:
    """
    Heuristic to determine if this conversation might benefit from tools.

    This is optional - just helps avoid tool overhead for simple chats.

    Args:
        message: Current user message
        conversation_history: Previous messages

    Returns:
        True if tools might be useful
    """
    # Keywords that suggest tool usage
    tool_indicators = [
        "search", "find", "look up", "check", "read", "write",
        "execute", "run", "fetch", "get", "download",
        "buscar", "procurar", "ler", "escrever", "executar"
    ]

    message_lower = message.lower()

    # Check if message contains tool indicators
    for indicator in tool_indicators:
        if indicator in message_lower:
            return True

    # Check if previous message used tools
    if conversation_history:
        last_msg = conversation_history[-1].get("content", "")
        if "[Tool:" in last_msg:
            return True  # Continue tool usage

    return False


# Example tool definitions for testing
EXAMPLE_TOOLS = [
    {
        "server": "filesystem",
        "name": "read_file",
        "description": "Read the contents of a file",
        "parameters": {
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
        "server": "web_search",
        "name": "search_web",
        "description": "Search the internet for information",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query"
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return (default 5)"
                }
            },
            "required": ["query"]
        }
    },
    {
        "server": "web_request",
        "name": "http_get",
        "description": "Perform HTTP GET request to an API or website",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to fetch"
                },
                "headers": {
                    "type": "object",
                    "description": "Optional HTTP headers"
                }
            },
            "required": ["url"]
        }
    }
]
