from __future__ import annotations

import importlib.util
import io
from pathlib import Path

import pytest

MODULE = (
    Path(__file__).resolve().parents[1]
    / "working-agreement"
    / "auto_capture_interview.py"
)
SPEC = importlib.util.spec_from_file_location("auto_capture_interview", MODULE)
assert SPEC is not None and SPEC.loader is not None
interview = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(interview)


def test_probe_proves_all_numbered_selection_contexts() -> None:
    result = interview.run_probe()

    assert result == {
        "ok": True,
        "numbered_selection_contexts": 5,
        "prose_rejections": [
            "capture",
            "content-kind",
            "evidence-kind",
            "evidence-continuation",
            "lesson-continuation",
        ],
        "normalized_lessons": 2,
        "zero_capture": True,
    }


def test_prompt_presents_every_numbered_menu_and_forbids_prose_labels() -> None:
    prompt = interview.SYSTEM_PROMPT

    assert "Capture selection options:\n1. capture nothing\n2. capture durable lessons" in prompt
    assert "Content-kind selection options:" in prompt
    assert "Evidence-kind selection options:" in prompt
    assert "Continuation selection options" in prompt
    assert "never send the option label as prose" in prompt


def test_output_schema_uses_strict_exact_object_shapes() -> None:
    def assert_strict_objects(node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False
                assert set(node.get("required", [])) == set(node.get("properties", {}))
            for value in node.values():
                assert_strict_objects(value)
        elif isinstance(node, list):
            for value in node:
                assert_strict_objects(value)

    assert_strict_objects(interview.INTERVIEW_OUTPUT_SCHEMA)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("capture_selection", "capture durable lessons", "capture selection returned"),
        ("capture_selection", 3, "choose one selection number"),
    ],
)
def test_capture_selection_rejects_prose_and_out_of_range_numbers(
    field: str, value: object, message: str,
) -> None:
    raw = {"capture_selection": 1, "lessons": []}
    raw[field] = value

    with pytest.raises(interview.InterviewError, match=message):
        interview.parse_interview(raw)


def test_valid_numbers_map_to_canonical_candidate_fields() -> None:
    normalized = interview.parse_interview(interview._valid_probe_answer())

    assert normalized[0]["content_kind"] == "corrected-approach"
    assert normalized[0]["evidence_refs"] == [
        {
            "kind": "file",
            "file_path": "scripts/minimal_git_publish.py",
            "revision_commit": "a" * 40,
        },
        {"kind": "revision", "revision_commit": "b" * 40},
    ]
    assert normalized[1]["content_kind"] == "repository-decision"
    assert normalized[1]["evidence_refs"][0]["kind"] == "entity"


def test_prose_selector_fields_are_rejected_instead_of_normalized() -> None:
    raw = interview._valid_probe_answer()
    raw["lessons"][0]["content_kind"] = "corrected-approach"

    with pytest.raises(interview.InterviewError, match="extra=.+content_kind"):
        interview.parse_interview(raw)


def test_interactive_path_reprompts_all_five_prose_selection_contexts() -> None:
    answers = iter([
        "memory-knowledge",
        "capture durable lessons", "2",
        "Use numeric menus", "Code owns every finite choice.",
        "corrected-approach", "2",
        "file", "3",
        "working-agreement/auto_capture.py", "a" * 40,
        "finish", "1",
        "finish", "1",
    ])
    output = io.StringIO()

    repository_key, lessons = interview.collect_interactive(
        read=lambda prompt: next(answers),
        output=output,
    )

    assert repository_key == "memory-knowledge"
    assert lessons == [{
        "title": "Use numeric menus",
        "body": "Code owns every finite choice.",
        "content_kind": "corrected-approach",
        "evidence_refs": [{
            "kind": "file",
            "file_path": "working-agreement/auto_capture.py",
            "revision_commit": "a" * 40,
        }],
    }]
    rendered = output.getvalue()
    assert rendered.count("prose labels are not accepted") == 5
    assert "1. capture nothing\n2. capture durable lessons" in rendered
    assert "1. root-cause\n2. corrected-approach" in rendered
    assert "1. entity\n2. revision\n3. file" in rendered
    assert "1. finish\n2. add another" in rendered
