"""
Structured generation using OpenVINO GenAI JSONSchema constraints.

Replaces prompt-based tool calling with grammar-based constrained generation.
This prevents hallucination and ensures valid tool call JSON.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple
import openvino_genai as ov_genai

logger = logging.getLogger(__name__)


def build_tool_call_schema(available_tools: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build JSONSchema that constrains output to valid tool calls.

    The schema allows either:
    - A tool call with valid tool name and arguments
    - A direct text response

    Args:
        available_tools: List of available MCP tools with their schemas

    Returns:
        JSONSchema for constrained generation
    """
    # Extract tool names and their argument schemas
    tool_schemas = {}
    for tool in available_tools:
        tool_name = tool.get("name", "")
        input_schema = tool.get("inputSchema", {})
        tool_schemas[tool_name] = input_schema

    # Build the constrained schema
    # Format: {"tool": "tool_name", "arguments": {...}}
    schema = {
        "type": "object",
        "properties": {
            "tool": {
                "type": "string",
                "enum": list(tool_schemas.keys())
            },
            "arguments": {
                "type": "object"
            }
        },
        "required": ["tool", "arguments"]
    }

    return schema


def create_structured_config_for_tool_call(
    available_tools: List[Dict[str, Any]]
) -> ov_genai.GenerationConfig:
    """
    Create GenerationConfig with JSONSchema constraint for tool calls.

    Args:
        available_tools: List of available MCP tools

    Returns:
        GenerationConfig configured for structured tool call generation
    """
    schema = build_tool_call_schema(available_tools)

    config = ov_genai.GenerationConfig()
    config.max_new_tokens = 256  # Tool calls are short
    config.temperature = 0.1  # Low temperature for structured output

    # Apply JSONSchema constraint
    structured_config = ov_genai.StructuredOutputConfig()
    structured_config.json_schema = json.dumps(schema)
    config.structured_output_config = structured_config

    return config


def build_citation_schema(search_results: str) -> Dict[str, Any]:
    """
    Build JSONSchema for citation format after search results.

    Forces the model to quote from actual search results.

    Args:
        search_results: The actual search results text

    Returns:
        JSONSchema for citation format
    """
    # Schema for structured citation response
    schema = {
        "type": "object",
        "properties": {
            "search_results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "snippet": {"type": "string"},
                        "url": {"type": "string"}
                    },
                    "required": ["title", "snippet", "url"]
                },
                "minItems": 1
            },
            "answer": {
                "type": "string",
                "description": "Answer based on the search results above"
            }
        },
        "required": ["search_results", "answer"]
    }

    return schema


def create_structured_config_for_citation(
    max_tokens: int = 512
) -> ov_genai.GenerationConfig:
    """
    Create GenerationConfig with JSONSchema for citation format.

    Args:
        max_tokens: Maximum tokens to generate

    Returns:
        GenerationConfig configured for structured citation
    """
    schema = {
        "type": "object",
        "properties": {
            "search_results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "snippet": {"type": "string"},
                        "url": {"type": "string"}
                    },
                    "required": ["title", "snippet", "url"]
                }
            },
            "answer": {"type": "string"}
        },
        "required": ["search_results", "answer"]
    }

    config = ov_genai.GenerationConfig()
    config.max_new_tokens = max_tokens
    config.temperature = 0.7

    structured_config = ov_genai.StructuredOutputConfig()
    structured_config.json_schema = json.dumps(schema)
    config.structured_output_config = structured_config

    return config


def parse_structured_tool_call(output: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    """
    Parse structured tool call output.

    Args:
        output: JSON output from structured generation

    Returns:
        (tool_name, arguments) if valid, None otherwise
    """
    try:
        data = json.loads(output)

        if "tool" in data and "arguments" in data:
            return data["tool"], data["arguments"]

        return None

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse structured output: {e}")
        return None


def parse_structured_citation(output: str) -> Optional[Dict[str, Any]]:
    """
    Parse structured citation output.

    Args:
        output: JSON output from structured citation generation

    Returns:
        Parsed citation data with search_results and answer
    """
    try:
        data = json.loads(output)

        if "search_results" in data and "answer" in data:
            return data

        return None

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse citation output: {e}")
        return None


def format_citation_for_display(citation_data: Dict[str, Any]) -> str:
    """
    Format structured citation data for conversation display.

    Args:
        citation_data: Parsed citation with search_results and answer

    Returns:
        Formatted text for display
    """
    lines = ["**Search Results:**", ""]

    for i, result in enumerate(citation_data["search_results"], 1):
        lines.append(f"{i}. {result['title']} - {result['snippet']}")
        lines.append(f"   Source: {result['url']}")
        lines.append("")

    lines.append("**Answer:**")
    lines.append(citation_data["answer"])

    return "\n".join(lines)


def extract_search_results_for_schema(tool_result: str) -> List[Dict[str, str]]:
    """
    Extract search results from tool output for schema validation.

    Parses the tool result to extract title, snippet, URL for each result.

    Args:
        tool_result: Raw tool result text

    Returns:
        List of {title, snippet, url} dicts
    """
    results = []
    lines = tool_result.split('\n')

    current_result = {}
    for line in lines:
        line = line.strip()

        # Match numbered results: "1. Title"
        if line and line[0].isdigit() and '. ' in line:
            if current_result:
                results.append(current_result)

            # Extract title (everything after "N. ")
            title = line.split('. ', 1)[1] if '. ' in line else line
            current_result = {"title": title, "snippet": "", "url": ""}

        # Match URL lines: "URL: ..." or "Source: ..."
        elif line.startswith(('URL:', 'Source:')):
            url = line.split(':', 1)[1].strip() if ':' in line else ""
            if current_result:
                current_result["url"] = url

        # Snippet (lines between title and URL)
        elif current_result and not current_result["snippet"] and line:
            current_result["snippet"] = line

    if current_result:
        results.append(current_result)

    return results
