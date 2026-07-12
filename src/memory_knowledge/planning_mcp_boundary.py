from __future__ import annotations

import uuid
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent

from memory_knowledge.workflows.base import WorkflowResult


PLANNING_SCHEMAS: dict[str, dict[str, Any]] = {
    "create_task": {
        "type": "object", "additionalProperties": False,
        "required": ["title", "repository_key"],
        "properties": {
            "title": {"type": "string", "minLength": 1, "maxLength": 255},
            "repository_key": {"type": "string", "minLength": 1},
            "project_key": {"type": ["string", "null"]},
            "project_external_system": {"type": ["string", "null"]},
            "project_external_id": {"type": ["string", "null"]},
            "description": {"type": ["string", "null"]},
            "feature_key": {"type": ["string", "null"]},
            "feature_external_system": {"type": ["string", "null"]},
            "feature_external_id": {"type": ["string", "null"]},
            "task_status_code": {"type": "string", "default": "TASK_TODO"},
            "priority_code": {"type": "string", "default": "PRIO_MEDIUM"},
            "correlation_id": {"type": ["string", "null"]},
            "task_type": {"type": ["string", "null"], "maxLength": 100},
            "parent_task_key": {"type": ["string", "null"]},
            "feature_task_key": {"type": ["string", "null"]},
            "graph_node_id": {"type": ["string", "null"], "maxLength": 255},
            "depends_on_task_keys": {"type": "array", "items": {"type": "string"}, "uniqueItems": True, "default": []},
            "blocked_by_task_keys": {"type": "array", "items": {"type": "string"}, "uniqueItems": True, "default": []},
            "coordination_task_keys": {"type": "array", "items": {"type": "string"}, "uniqueItems": True, "default": []},
            "related_repository_keys": {"type": "array", "items": {"type": "string"}, "uniqueItems": True, "default": []},
            "is_runnable": {"type": "boolean", "default": True},
            "task_metadata": {"type": "object", "default": {}},
            "legacy_task_key": {"type": ["string", "null"]},
        },
    },
    "update_task": {
        "type": "object", "additionalProperties": False, "required": ["task_key", "patch"],
        "properties": {
            "task_key": {"type": "string", "minLength": 1},
            "patch": {"type": "object", "minProperties": 1, "additionalProperties": False,
                      "properties": {
                          "title": {"type": "string", "minLength": 1, "maxLength": 255},
                          "description": {"type": ["string", "null"]},
                          "task_type": {"type": ["string", "null"], "maxLength": 100},
                          "parent_task_key": {"type": ["string", "null"]},
                          "feature_task_key": {"type": ["string", "null"]},
                          "depends_on_task_keys": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
                          "blocked_by_task_keys": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
                          "coordination_task_keys": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
                          "related_repository_keys": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
                          "is_runnable": {"type": "boolean"}, "task_metadata": {"type": "object"},
                      }},
            "correlation_id": {"type": ["string", "null"]},
        },
    },
    "list_tasks": {
        "type": "object", "additionalProperties": False,
        "properties": {key: {"type": ["string", "null"]} for key in (
            "project_key", "feature_key", "repository_key", "task_status_code",
            "project_external_system", "project_external_id", "feature_external_system",
            "feature_external_id", "correlation_id", "graph_node_id")},
    },
}


def _validate(name: str, arguments: Any) -> tuple[str, str] | None:
    if not isinstance(arguments, dict):
        return ("$", "arguments must be an object")
    schema = PLANNING_SCHEMAS[name]
    properties = schema["properties"]
    for required in schema.get("required", []):
        if required not in arguments:
            return (required, f"{required} is required")
    def validate_value(path: str, value: Any, spec: dict[str, Any]) -> tuple[str, str] | None:
        types = spec.get("type")
        types = types if isinstance(types, list) else [types]
        valid = value is None and "null" in types
        valid = valid or ("string" in types and isinstance(value, str))
        valid = valid or ("boolean" in types and isinstance(value, bool))
        valid = valid or ("object" in types and isinstance(value, dict))
        valid = valid or ("array" in types and isinstance(value, list))
        if not valid:
            return (path, f"{path} has the wrong type")
        if isinstance(value, str):
            if spec.get("minLength", 0) and not value.strip():
                return (path, f"{path} must not be empty")
            if len(value) > spec.get("maxLength", 10**9):
                return (path, f"{path} is too long")
        if isinstance(value, list):
            item_spec = spec.get("items", {})
            for item in value:
                defect = validate_value(path, item, item_spec)
                if defect:
                    return defect
            if spec.get("uniqueItems") and len(value) != len(set(value)):
                return (path, f"{path} must contain unique values")
        if isinstance(value, dict) and spec.get("properties") is not None:
            nested = spec["properties"]
            for nested_name in nested:
                if nested_name in value:
                    defect = validate_value(f"{path}.{nested_name}", value[nested_name], nested[nested_name])
                    if defect:
                        return defect
            unknown_nested = sorted(set(value) - set(nested))
            if spec.get("additionalProperties") is False and unknown_nested:
                return (f"{path}.{unknown_nested[0]}", f"unknown property: {unknown_nested[0]}")
            if len(value) < spec.get("minProperties", 0):
                return (path, f"{path} must be a non-empty object")
        return None

    # Validate in schema order, then report unknown keys in lexical order.  This
    # keeps first-error behavior independent of JSON object insertion order.
    for field in properties:
        if field not in arguments:
            continue
        value = arguments[field]
        spec = properties[field]
        defect = validate_value(field, value, spec)
        if defect:
            return defect
    unknown = sorted(set(arguments) - set(properties))
    if unknown:
        return (unknown[0], f"unknown property: {unknown[0]}")
    for left, right in (("project_external_system", "project_external_id"),
                        ("feature_external_system", "feature_external_id")):
        left_present = arguments.get(left) is not None
        right_present = arguments.get(right) is not None
        if left_present != right_present:
            return (left, f"{left} and {right} must be supplied together")
    if name == "create_task":
        if not arguments.get("project_key") and not arguments.get("project_external_system"):
            return ("project_key", "a project identity is required")
        if arguments.get("graph_node_id") and not (arguments.get("feature_key") or arguments.get("feature_external_system")):
            return ("feature_key", "graph_node_id requires a feature identity")
        if arguments.get("legacy_task_key") and not arguments.get("graph_node_id"):
            return ("legacy_task_key", "legacy_task_key requires graph_node_id")
    if name == "update_task":
        patch = arguments.get("patch")
        if not isinstance(patch, dict) or not patch:
            return ("patch", "patch must be a non-empty object")
        # The patch is a closed, recursively validated object, not an escape
        # hatch around the create contract.
        patch_spec = properties["patch"]
        defect = validate_value("patch", patch, patch_spec)
        if defect:
            return defect
    return None


class PlanningFastMCP(FastMCP):
    async def list_tools(self):  # type: ignore[override]
        tools = await super().list_tools()
        return [tool.model_copy(update={"inputSchema": PLANNING_SCHEMAS[tool.name]})
                if tool.name in PLANNING_SCHEMAS else tool for tool in tools]

    async def call_tool(self, name: str, arguments: dict[str, Any]):  # type: ignore[override]
        if name in PLANNING_SCHEMAS:
            invalid = _validate(name, arguments)
            if invalid:
                field, message = invalid
                payload = WorkflowResult(
                    run_id=str(uuid.uuid4()), tool_name=name, status="error", error=message,
                    data={"error_code": "INVALID_ARGS", "field": field},
                ).model_dump_json()
                return [TextContent(type="text", text=payload)]
        return await super().call_tool(name, arguments)
