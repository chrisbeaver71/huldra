"""Huldra V1 Tool Invocation Bridge.

Provides:
- Tool schema registration with argument validation
- Structured output handling (JSON extraction from model responses)
- Tool dispatch for local assistant use
- Schema/argument validation before execution

Reuses Hermes tool schemas where available; adds V1-specific validation.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class ToolSchema:
    """Schema for a single tool."""
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema for arguments
    handler: Optional[Callable] = None  # Python callable that executes the tool

    def to_openai_tool(self) -> dict[str, Any]:
        """Convert to OpenAI function-calling tool format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def validate_args(self, args: dict[str, Any]) -> list[str]:
        """Validate arguments against the schema. Returns list of errors (empty = valid)."""
        errors = []
        required = self.parameters.get("required", [])
        properties = self.parameters.get("properties", {})

        for field_name in required:
            if field_name not in args:
                errors.append(f"Missing required argument: {field_name}")

        for key, value in args.items():
            if key in properties:
                prop = properties[key]
                expected_type = prop.get("type")
                if expected_type and not self._type_check(value, expected_type):
                    errors.append(
                        f"Argument '{key}' expected type '{expected_type}', "
                        f"got '{type(value).__name__}'"
                    )
            elif not self.parameters.get("additionalProperties", True):
                errors.append(f"Unexpected argument: {key}")

        return errors

    @staticmethod
    def _type_check(value: Any, expected: str) -> bool:
        type_map = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        python_type = type_map.get(expected)
        if python_type is None:
            return True  # Unknown type, pass validation
        return isinstance(value, python_type)


class ToolRegistry:
    """Registry of available tools with schema validation."""

    def __init__(self):
        self._tools: dict[str, ToolSchema] = {}

    def register(self, schema: ToolSchema) -> None:
        """Register a tool schema."""
        self._tools[schema.name] = schema
        logger.debug("Registered tool: %s", schema.name)

    def register_simple(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        handler: Optional[Callable] = None,
    ) -> None:
        """Convenience method to register a tool from basic parts."""
        self.register(ToolSchema(
            name=name,
            description=description,
            parameters=parameters,
            handler=handler,
        ))

    def get(self, name: str) -> Optional[ToolSchema]:
        return self._tools.get(name)

    def get_schemas(self) -> list[dict[str, Any]]:
        """Return all tool schemas in OpenAI format."""
        return [t.to_openai_tool() for t in self._tools.values()]

    def get_names(self) -> list[str]:
        return list(self._tools.keys())

    def has(self, name: str) -> bool:
        return name in self._tools

    def validate_tool_call(self, name: str, args: dict[str, Any]) -> list[str]:
        """Validate a tool call's arguments. Returns errors or empty list."""
        schema = self._tools.get(name)
        if not schema:
            return [f"Unknown tool: {name}"]
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                return [f"Invalid JSON arguments for tool '{name}'"]
        return schema.validate_args(args)

    def execute_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Validate and execute a tool call. Returns result dict."""
        errors = self.validate_tool_call(name, args)
        if errors:
            return {
                "success": False,
                "error": "; ".join(errors),
                "tool": name,
            }

        schema = self._tools[name]
        if schema.handler is None:
            return {
                "success": False,
                "error": f"Tool '{name}' has no handler registered",
                "tool": name,
            }

        try:
            result = schema.handler(**args)
            return {
                "success": True,
                "result": result,
                "tool": name,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "tool": name,
            }


def extract_tool_calls_from_response(
    response: dict[str, Any],
) -> list[dict[str, Any]]:
    """Extract tool calls from an OpenAI-compatible response.

    Returns list of {name, arguments, id} dicts.
    """
    tool_calls = []
    choices = response.get("choices", [])
    if not choices:
        return tool_calls

    message = choices[0].get("message", {})
    raw_calls = message.get("tool_calls", [])
    for tc in raw_calls:
        func = tc.get("function", {})
        name = func.get("name", "")
        args_raw = func.get("arguments", "{}")
        if isinstance(args_raw, str):
            try:
                args = json.loads(args_raw)
            except json.JSONDecodeError:
                logger.warning("Failed to parse tool arguments: %s", args_raw[:200])
                args = {}
        else:
            args = args_raw

        tool_calls.append({
            "id": tc.get("id", ""),
            "name": name,
            "arguments": args,
        })

    return tool_calls


def format_tool_result_for_model(
    tool_call_id: str,
    content: str,
) -> dict[str, Any]:
    """Format a tool result as a message for the next API call."""
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": content,
    }


# Built-in V1 tool schemas

def register_v1_tools(registry: ToolRegistry) -> None:
    """Register the standard V1 tool set."""

    registry.register_simple(
        name="read_file",
        description="Read a text file with line numbers. Returns content of the file.",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative path to the file",
                },
            },
            "required": ["path"],
        },
    )

    registry.register_simple(
        name="write_file",
        description="Write content to a file, completely replacing existing content.",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative path to the file",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write",
                },
            },
            "required": ["path", "content"],
        },
    )

    registry.register_simple(
        name="search_files",
        description="Search file contents or find files by name.",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern or glob pattern",
                },
                "path": {
                    "type": "string",
                    "description": "Directory to search in (default: current)",
                },
            },
            "required": ["pattern"],
        },
    )

    registry.register_simple(
        name="terminal",
        description="Execute a shell command and return output.",
        parameters={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute",
                },
            },
            "required": ["command"],
        },
    )

    registry.register_simple(
        name="patch",
        description="Find and replace text in a file.",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path to edit",
                },
                "old_string": {
                    "type": "string",
                    "description": "Exact text to find and replace",
                },
                "new_string": {
                    "type": "string",
                    "description": "Replacement text",
                },
            },
            "required": ["path", "old_string", "new_string"],
        },
    )
