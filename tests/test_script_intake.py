from __future__ import annotations

import pytest

from scripts import script_intake


SPEC = {
    "schema_version": 1,
    "fields": [
        {
            "id": "action",
            "prompt": "Action",
            "response_format": "One action name.",
            "example": "read",
            "constraints": "Use exactly one allowed value.",
            "type": "choice",
            "choices": ["read", "check"],
            "required": True,
        },
        {
            "id": "mode",
            "prompt": "Mode",
            "response_format": "One mode identifier.",
            "example": "prototype-intake",
            "constraints": "Do not add quotes or JSON.",
            "type": "string",
            "required": True,
            "when": {"field": "action", "equals": "read"},
        },
        {
            "id": "max_age",
            "prompt": "Maximum age",
            "response_format": "One positive whole number.",
            "example": "60",
            "constraints": "Value must be at least 1.",
            "type": "integer",
            "default": 1440,
            "minimum": 1,
            "when": {"field": "action", "equals": "check"},
        },
    ],
}


def _answers(*values: str):
    remaining = iter(values)
    return lambda prompt: next(remaining)


def test_collect_returns_only_active_typed_answers():
    assert script_intake.collect(
        SPEC, input_fn=_answers("check", ""), output_fn=lambda message: None,
    ) == {"action": "check", "max_age": 1440}


def test_collect_retries_invalid_choice_without_advancing():
    messages = []

    result = script_intake.collect(
        SPEC,
        input_fn=_answers("inspect", "read", "prototype-intake"),
        output_fn=messages.append,
    )

    assert result == {"action": "read", "mode": "prototype-intake"}
    assert messages == ["Invalid answer: choose one of: read, check."]


def test_numbered_selection_lists_options_maps_number_and_rejects_prose():
    spec = {
        "schema_version": 1,
        "fields": [{
            "id": "action",
            "prompt": "Action",
            "response_format": "One selection number.",
            "example": "1",
            "constraints": "Choose one numbered action.",
            "type": "choice",
            "choices": ["read", "check"],
            "numbered_selection": True,
            "required": True,
        }],
    }
    prompts = []
    messages = []
    answers = iter(["read", "3", "2"])

    result = script_intake.collect(
        spec,
        input_fn=lambda prompt: prompts.append(prompt) or next(answers),
        output_fn=messages.append,
    )

    assert result == {"action": "check"}
    assert "Selection options:\n1. read\n2. check" in prompts[0]
    assert "Choose one selection number." in prompts[0]
    assert "Allowed values:" not in prompts[0]
    assert messages == [
        "Invalid answer: choose a selection number from 1 to 2.",
        "Invalid answer: choose a selection number from 1 to 2.",
    ]


def test_collect_reports_invalid_integer_and_retries():
    messages = []

    result = script_intake.collect(
        SPEC,
        input_fn=_answers("check", "zero", "0", "5"),
        output_fn=messages.append,
    )

    assert result == {"action": "check", "max_age": 5}
    assert messages == [
        "Invalid answer: enter a whole number.",
        "Invalid answer: enter a value of at least 1.",
    ]


def test_collect_converts_boolean_answers():
    spec = {
        "schema_version": 1,
        "fields": [
            {
                "id": "confirm",
                "prompt": "Continue",
                "response_format": "One yes or no answer.",
                "example": "yes",
                "constraints": "Use exactly one allowed value.",
                "type": "boolean",
                "required": True,
            },
        ],
    }

    assert script_intake.collect(
        spec, input_fn=_answers("yes"), output_fn=lambda message: None,
    ) == {"confirm": True}


def test_collect_fails_closed_when_input_ends():
    with pytest.raises(script_intake.IntakeCancelled, match="intake-cancelled"):
        script_intake.collect(
            SPEC,
            input_fn=lambda prompt: (_ for _ in ()).throw(EOFError),
            output_fn=lambda message: None,
        )


def test_terminal_prompts_and_validation_stay_off_stdout(monkeypatch, capsys):
    answers = iter(["inspect\n", "read\n", "prototype-intake\n"])
    monkeypatch.setattr(script_intake.sys.stdin, "readline", lambda: next(answers))

    assert script_intake.collect(SPEC) == {
        "action": "read",
        "mode": "prototype-intake",
    }
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Question: Action" in captured.err
    assert "Response format: One action name." in captured.err
    assert "Example: read" in captured.err
    assert "Constraints: Use exactly one allowed value." in captured.err
    assert "Allowed values: read, check" in captured.err
    assert "Invalid answer: choose one of: read, check." in captured.err
    assert captured.err.count("Question: Action") == 2


def test_collect_preserves_semantic_free_text_without_interpreting_shell_syntax():
    spec = {
        "schema_version": 1,
        "fields": [
            {
                "id": "message",
                "prompt": "Commit message",
                "response_format": "One plain-text description of the approved change.",
                "example": "Add deterministic sequence intake",
                "constraints": "Describe the change; do not provide an invocation.",
                "type": "string",
                "semantic": True,
                "required": True,
            },
        ],
    }

    assert script_intake.collect(
        spec, input_fn=_answers("Update `src/memory_knowledge/db/health.py`."),
        output_fn=lambda message: None,
    ) == {"message": "Update `src/memory_knowledge/db/health.py`."}


@pytest.mark.parametrize(
    ("spec", "error"),
    [
        ({"schema_version": 2, "fields": []}, "unsupported-schema-version"),
        (
            {
                "schema_version": 1,
                "fields": [
                    {
                        "id": "same", "prompt": "First", "type": "string",
                        "response_format": "One value.", "example": "first",
                        "constraints": "Plain text only.",
                    },
                    {
                        "id": "same", "prompt": "Second", "type": "string",
                        "response_format": "One value.", "example": "second",
                        "constraints": "Plain text only.",
                    },
                ],
            },
            "duplicate-field-id:same",
        ),
        (
            {
                "schema_version": 1,
                "fields": [
                    {
                        "id": "later",
                        "prompt": "Later",
                        "response_format": "One value.",
                        "example": "value",
                        "constraints": "Plain text only.",
                        "type": "string",
                        "when": {"field": "missing", "equals": "yes"},
                    },
                ],
            },
            "field-condition-invalid:later",
        ),
        (
            {
                "schema_version": 1,
                "fields": [
                    {
                        "id": "age",
                        "prompt": "Age",
                        "response_format": "One whole number.",
                        "example": "60",
                        "constraints": "Digits only.",
                        "type": "integer",
                        "default": "1440",
                    },
                ],
            },
            "field-default-invalid:age",
        ),
        (
            {
                "schema_version": 1,
                "fields": [
                    {
                        "id": "unguided",
                        "prompt": "Unguided",
                        "type": "string",
                        "example": "value",
                        "constraints": "Plain text only.",
                    },
                ],
            },
            "field-response-format-required:unguided",
        ),
        (
            {
                "schema_version": 1,
                "fields": [
                    {
                        "id": "command",
                        "prompt": "Command executable",
                        "response_format": "One executable.",
                        "example": "python3",
                        "constraints": "Plain text only.",
                        "type": "argv",
                    },
                ],
            },
            "unsupported-field-type:command",
        ),
        (
            {
                "schema_version": 1,
                "fields": [
                    {
                        "id": "command",
                        "prompt": "Command executable",
                        "response_format": "One executable.",
                        "example": "python3",
                        "constraints": "Plain text only.",
                        "type": "string",
                        "semantic": True,
                    },
                ],
            },
            "field-requests-invocation-syntax:command",
        ),
    ],
)
def test_collect_rejects_noncanonical_specs(spec, error):
    with pytest.raises(script_intake.IntakeSpecError, match=error):
        script_intake.collect(spec, input_fn=_answers(), output_fn=lambda message: None)


def test_object_list_collects_semantic_subfields_and_builds_objects():
    spec = {
        "schema_version": 1,
        "fields": [{
            "id": "dependencies",
            "prompt": "Sequence dependency",
            "response_format": "One dependency at a time.",
            "example": "a file dependency",
            "constraints": "Answer each displayed subquestion.",
            "type": "object_list",
            "item_fields": [
                {
                    "id": "kind",
                    "prompt": "Dependency kind",
                    "response_format": "One kind name.",
                    "example": "file",
                    "constraints": "Choose one allowed value.",
                    "type": "choice",
                    "choices": ["file", "sequence"],
                    "required": True,
                },
                {
                    "id": "repository_key",
                    "prompt": "Dependency repository",
                    "response_format": "One repository name.",
                    "example": "memory-knowledge",
                    "constraints": "Use a registered repository.",
                    "type": "string",
                    "required": True,
                },
                {
                    "id": "path_or_sequence_id",
                    "prompt": "Dependency identity",
                    "response_format": "One relative path or sequence identity.",
                    "example": "scripts/example.py",
                    "constraints": "Do not add quotes.",
                    "type": "string",
                    "required": True,
                },
            ],
        }],
    }
    answers = iter([
        "file", "memory-knowledge", "scripts/example.py", "yes",
        "sequence", "memory-knowledge", "commit-push-main", "no",
    ])

    result = script_intake.collect(
        spec,
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )

    assert result == {
        "dependencies": [
            {
                "kind": "file",
                "repository_key": "memory-knowledge",
                "path_or_sequence_id": "scripts/example.py",
            },
            {
                "kind": "sequence",
                "repository_key": "memory-knowledge",
                "path_or_sequence_id": "commit-push-main",
            },
        ],
    }
