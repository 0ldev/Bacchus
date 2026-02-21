"""
Decision schema for structured generation.

Forces the model to decide: tool call or direct response?
This replaces prompt-based tool calling entirely.
"""

import json
import logging
from typing import Any, Dict, List, Optional
import openvino_genai as ov_genai

logger = logging.getLogger(__name__)


def build_decision_schema(available_tools: List[str]) -> Dict[str, Any]:
    """
    Build JSONSchema that forces model to decide: use tool or respond directly?

    Uses oneOf to make the two branches mutually exclusive:
    - tool_call branch: {"action": "tool_call", "tool": "...", "arguments": {...}}
    - respond branch:   {"action": "respond", "response": "..."}

    additionalProperties: false prevents the model from writing both a tool call
    AND a response field simultaneously (which caused 12-minute hallucination loops).

    Args:
        available_tools: List of available tool names

    Returns:
        JSONSchema for decision
    """
    schema = {
        "oneOf": [
            {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["tool_call"]},
                    "tool": {"type": "string", "enum": available_tools},
                    "arguments": {"type": "object"}
                },
                "required": ["action", "tool", "arguments"],
                "additionalProperties": False
            },
            {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["respond"]},
                    "response": {"type": "string"}
                },
                "required": ["action", "response"],
                "additionalProperties": False
            }
        ]
    }

    return schema


def create_decision_config(
    available_tools: List[str],
    max_tokens: int = 512
) -> ov_genai.GenerationConfig:
    """
    Create GenerationConfig with decision schema.

    Args:
        available_tools: List of available tool names
        max_tokens: Maximum tokens to generate

    Returns:
        GenerationConfig for structured decision
    """
    schema = build_decision_schema(available_tools)

    config = ov_genai.GenerationConfig()
    config.max_new_tokens = max_tokens
    config.temperature = 0.3  # Lower temp for structured decisions

    # Create StructuredOutputConfig and set json_schema property
    structured_config = ov_genai.StructuredOutputConfig()
    schema_json = json.dumps(schema)
    structured_config.json_schema = schema_json
    config.structured_output_config = structured_config

    logger.info(f"Created decision schema with {len(available_tools)} tools")
    logger.debug(f"Schema: {schema_json[:200]}...")

    return config


def parse_decision(output: str) -> Dict[str, Any]:
    """
    Parse decision output from structured generation.

    Args:
        output: JSON output from model

    Returns:
        Parsed decision with action, tool, arguments, or response
    """
    # Strip markdown code fences if model wrapped the JSON
    cleaned = output.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first line (```json or ```) and last line (```)
        inner_lines = lines[1:]
        if inner_lines and inner_lines[-1].strip() == "```":
            inner_lines = inner_lines[:-1]
        cleaned = "\n".join(inner_lines).strip()

    try:
        data = json.loads(cleaned)

        if "action" not in data:
            logger.error("Missing 'action' field in decision output")
            return {"action": "respond", "response": output}

        action = data["action"]

        if action == "tool_call":
            if "tool" not in data or "arguments" not in data:
                logger.error("tool_call action missing tool or arguments")
                return {"action": "respond", "response": output}

            return {
                "action": "tool_call",
                "tool": data["tool"],
                "arguments": data["arguments"]
            }

        elif action == "respond":
            response = data.get("response", "")
            return {
                "action": "respond",
                "response": response
            }

        else:
            logger.error(f"Unknown action: {action}")
            return {"action": "respond", "response": output}

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse decision output: {e}")
        # Fallback: treat as direct response
        return {"action": "respond", "response": output}
