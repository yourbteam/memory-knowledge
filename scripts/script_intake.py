#!/usr/bin/env python3
"""Collect and validate typed script inputs from a caller-owned JSON-like specification."""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping
from typing import Any


SCHEMA_VERSION = 1
SUPPORTED_TYPES = frozenset({
    "boolean", "choice", "integer", "object_list", "path", "string",
    "string_list",
})
FORBIDDEN_INVOCATION_FIELD_IDS = frozenset({
    "argv", "command", "command_argv", "command_line", "executable", "flags",
    "shell_command",
})
FORBIDDEN_INVOCATION_PHRASES = (
    "command executable",
    "command argument",
    "literal argv",
    "shell command",
    "shell fragment",
    "flag name",
    "environment assignment",
    "json object",
    "json array",
    "json text",
    "yaml object",
    "yaml text",
)
MISSING = object()


class IntakeSpecError(ValueError):
    """The caller supplied an invalid intake specification."""


class IntakeCancelled(RuntimeError):
    """The intake ended before all required answers were collected."""


def _validate_spec(spec: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    if spec.get("schema_version") != SCHEMA_VERSION:
        raise IntakeSpecError("unsupported-schema-version")
    fields = spec.get("fields")
    if not isinstance(fields, list) or not fields:
        raise IntakeSpecError("fields-must-be-a-non-empty-list")

    seen: set[str] = set()
    validated: list[Mapping[str, Any]] = []
    for raw_field in fields:
        if not isinstance(raw_field, Mapping):
            raise IntakeSpecError("field-must-be-an-object")
        field_id = raw_field.get("id")
        if not isinstance(field_id, str) or not field_id.strip():
            raise IntakeSpecError("field-id-required")
        if field_id in seen:
            raise IntakeSpecError(f"duplicate-field-id:{field_id}")
        field_type = raw_field.get("type")
        if field_type not in SUPPORTED_TYPES:
            raise IntakeSpecError(f"unsupported-field-type:{field_id}")
        prompt = raw_field.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise IntakeSpecError(f"field-prompt-required:{field_id}")
        for key, label in (
            ("response_format", "response-format"),
            ("example", "example"),
            ("constraints", "constraints"),
        ):
            value = raw_field.get(key)
            if not isinstance(value, str) or not value.strip():
                raise IntakeSpecError(f"field-{label}-required:{field_id}")
        request_text = " ".join(str(raw_field[key]).casefold() for key in (
            "prompt", "response_format", "example",
        ))
        if (
            field_id.casefold() in FORBIDDEN_INVOCATION_FIELD_IDS
            or any(phrase in request_text for phrase in FORBIDDEN_INVOCATION_PHRASES)
        ):
            raise IntakeSpecError(f"field-requests-invocation-syntax:{field_id}")

        choices = raw_field.get("choices")
        if field_type == "choice":
            if (
                not isinstance(choices, list)
                or not choices
                or any(not isinstance(choice, str) or not choice for choice in choices)
                or len(set(choices)) != len(choices)
            ):
                raise IntakeSpecError(f"field-choices-invalid:{field_id}")
        if field_type in {"string_list", "object_list"} and "default" in raw_field:
            raise IntakeSpecError(f"field-default-invalid:{field_id}")
        if field_type == "string_list":
            for key, label in (
                ("item_prompt", "item-prompt"),
                ("item_response_format", "item-response-format"),
                ("item_example", "item-example"),
                ("item_constraints", "item-constraints"),
            ):
                value = raw_field.get(key)
                if not isinstance(value, str) or not value.strip():
                    raise IntakeSpecError(f"field-{label}-required:{field_id}")
        if field_type == "object_list":
            item_fields = raw_field.get("item_fields")
            if not isinstance(item_fields, list) or not item_fields:
                raise IntakeSpecError(f"field-item-fields-invalid:{field_id}")
            _validate_spec({
                "schema_version": SCHEMA_VERSION,
                "fields": item_fields,
            })
            minimum_items = raw_field.get("minimum_items", 1)
            maximum_items = raw_field.get("maximum_items")
            if (
                not isinstance(minimum_items, int)
                or isinstance(minimum_items, bool)
                or minimum_items < 1
                or (
                    maximum_items is not None
                    and (
                        not isinstance(maximum_items, int)
                        or isinstance(maximum_items, bool)
                        or maximum_items < minimum_items
                    )
                )
            ):
                raise IntakeSpecError(f"field-item-count-invalid:{field_id}")
        if "default" in raw_field:
            default = raw_field["default"]
            valid_default = (
                (field_type in {"choice", "path", "string"} and isinstance(default, str))
                or (field_type == "boolean" and isinstance(default, bool))
                or (
                    field_type == "integer"
                    and isinstance(default, int)
                    and not isinstance(default, bool)
                )
            )
            if (
                not valid_default
                or (field_type == "choice" and default not in choices)
                or (
                    field_type == "integer"
                    and raw_field.get("minimum") is not None
                    and default < raw_field["minimum"]
                )
                or (
                    field_type == "integer"
                    and raw_field.get("maximum") is not None
                    and default > raw_field["maximum"]
                )
            ):
                raise IntakeSpecError(f"field-default-invalid:{field_id}")

        condition = raw_field.get("when")
        if condition is not None:
            if (
                not isinstance(condition, Mapping)
                or condition.get("field") not in seen
                or set(condition) not in (
                    {"field", "equals"},
                    {"field", "in"},
                )
                or (
                    ("equals" in condition) == ("in" in condition)
                )
                or (
                    "equals" in condition
                    and set(condition) != {"field", "equals"}
                )
                or (
                    "in" in condition
                    and (
                        set(condition) != {"field", "in"}
                        or not isinstance(condition["in"], list)
                        or not condition["in"]
                    )
                )
            ):
                raise IntakeSpecError(f"field-condition-invalid:{field_id}")

        seen.add(field_id)
        validated.append(raw_field)
    return validated


def _is_active(field: Mapping[str, Any], answers: Mapping[str, Any]) -> bool:
    condition = field.get("when")
    if condition is None:
        return True
    value = answers.get(condition["field"], MISSING)
    if "equals" in condition:
        return value == condition["equals"]
    return value in condition["in"]


def _prompt_text(field: Mapping[str, Any]) -> str:
    details = [
        f"Question: {field['prompt']}",
        f"Response format: {field['response_format']}",
        f"Example: {field['example']}",
        f"Constraints: {field['constraints']}",
    ]
    if field["type"] == "choice":
        details.append("Allowed values: " + ", ".join(field["choices"]))
    elif field["type"] == "boolean":
        details.append("Allowed values: yes, no")
    if "default" in field:
        details.append(f"Default: {field['default']}")
    details.append("Answer: ")
    return "\n".join(details)


def _parse_value(field: Mapping[str, Any], raw: str) -> Any:
    value = raw.strip()
    if not value:
        if field.get("allow_empty", False):
            return ""
        if "default" in field:
            return field["default"]
        if field.get("required", False):
            raise ValueError("a value is required")
        return None

    field_type = field["type"]
    if field_type == "choice":
        if value not in field["choices"]:
            raise ValueError("choose one of: " + ", ".join(field["choices"]))
        return value
    if field_type == "boolean":
        normalized = value.casefold()
        if normalized in {"yes", "y", "true"}:
            return True
        if normalized in {"no", "n", "false"}:
            return False
        raise ValueError("enter yes or no")
    if field_type == "integer":
        try:
            parsed = int(value)
        except ValueError as exc:
            raise ValueError("enter a whole number") from exc
        minimum = field.get("minimum")
        maximum = field.get("maximum")
        if minimum is not None and parsed < minimum:
            raise ValueError(f"enter a value of at least {minimum}")
        if maximum is not None and parsed > maximum:
            raise ValueError(f"enter a value no greater than {maximum}")
        return parsed
    return value


def _terminal_input(prompt: str) -> str:
    print(prompt, end="", file=sys.stderr, flush=True)
    value = sys.stdin.readline()
    if value == "":
        raise EOFError
    return value.rstrip("\n")


def _terminal_output(message: str) -> None:
    print(message, file=sys.stderr)


def _ask_field(
    field: Mapping[str, Any],
    *,
    read: Callable[[str], str],
    write: Callable[[str], None],
) -> Any:
    while True:
        try:
            raw = read(_prompt_text(field))
        except (EOFError, KeyboardInterrupt) as exc:
            raise IntakeCancelled("intake-cancelled") from exc
        try:
            return _parse_value(field, raw)
        except ValueError as exc:
            write(f"Invalid answer: {exc}.")


def _collect_string_list(
    field: Mapping[str, Any],
    *,
    read: Callable[[str], str],
    write: Callable[[str], None],
) -> list[str]:
    item_field = {
        "id": f"{field['id']}_item",
        "prompt": field["item_prompt"],
        "response_format": field["item_response_format"],
        "example": field["item_example"],
        "constraints": field["item_constraints"],
        "type": "string",
        "required": True,
    }
    values = [_ask_field(item_field, read=read, write=write)]
    continuation_field = {
        "id": f"{field['id']}_add_item",
        "prompt": f"Add another {field['item_prompt'].lower()}?",
        "response_format": "One yes or no answer.",
        "example": "yes",
        "constraints": "Use exactly yes or no.",
        "type": "boolean",
        "required": True,
    }
    while _ask_field(continuation_field, read=read, write=write):
        values.append(_ask_field(item_field, read=read, write=write))
    return values


def _collect_object_list(
    field: Mapping[str, Any],
    *,
    read: Callable[[str], str],
    write: Callable[[str], None],
) -> list[dict[str, Any]]:
    item_fields = _validate_spec({
        "schema_version": SCHEMA_VERSION,
        "fields": field["item_fields"],
    })
    minimum_items = field.get("minimum_items", 1)
    maximum_items = field.get("maximum_items")
    values: list[dict[str, Any]] = []
    while True:
        item: dict[str, Any] = {}
        for item_field in item_fields:
            if not _is_active(item_field, item):
                continue
            if item_field["type"] == "string_list":
                item[item_field["id"]] = _collect_string_list(
                    item_field, read=read, write=write,
                )
            elif item_field["type"] == "object_list":
                item[item_field["id"]] = _collect_object_list(
                    item_field, read=read, write=write,
                )
            else:
                item[item_field["id"]] = _ask_field(
                    item_field, read=read, write=write,
                )
        values.append(item)
        if maximum_items is not None and len(values) >= maximum_items:
            break
        if len(values) < minimum_items:
            continue
        continuation_field = {
            "id": f"{field['id']}_add_item",
            "prompt": f"Add another {field['prompt'].lower()} item?",
            "response_format": "One yes or no answer.",
            "example": "yes",
            "constraints": "Use exactly yes or no.",
            "type": "boolean",
            "required": True,
        }
        if not _ask_field(continuation_field, read=read, write=write):
            break
    return values


def collect(
    spec: Mapping[str, Any],
    *,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Return canonical typed answers for the active fields in ``spec``."""

    fields = _validate_spec(spec)
    read = input_fn or _terminal_input
    write = output_fn or _terminal_output
    answers: dict[str, Any] = {}
    for field in fields:
        if not _is_active(field, answers):
            continue
        if field["type"] == "string_list":
            answers[field["id"]] = _collect_string_list(
                field, read=read, write=write,
            )
        elif field["type"] == "object_list":
            answers[field["id"]] = _collect_object_list(
                field, read=read, write=write,
            )
        else:
            answers[field["id"]] = _ask_field(field, read=read, write=write)
    return answers
