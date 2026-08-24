from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/info-intake-machinery/scripts/assessment_charter.py"


def _module():
    spec = importlib.util.spec_from_file_location("assessment_charter", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _intake(path: Path) -> Path:
    path.write_text('{"intake_id":"intake-one","status":"terminal"}\n', encoding="utf-8")
    return path


def _answers() -> list[str]:
    return [
        "Assess whether each required value reaches its consumer.",
        "Identify aligned, misaligned, and incomplete units.",
        "One purpose-relevant consumer value.",
        "all-purpose-relevant-units",
        "allow-incomplete-verdict",
        "Send confirmed misalignments to implementation machinery.",
    ]


def test_code_controlled_interview_is_immutable_and_verifiable(tmp_path: Path) -> None:
    module = _module()
    intake = _intake(tmp_path / "intake.json")
    answers = iter(_answers())
    work = tmp_path / "work"

    charter = module.run(intake, work, input_fn=lambda _prompt: next(answers))

    assert charter["status"] == "charter-ready"
    assert charter["assessment"]["completion_policy"] == "all-purpose-relevant-units"
    assert module.verify(work / "charter.json") == charter
    assert module.run(intake, work, input_fn=lambda _prompt: pytest.fail("must replay")) == charter
    entries = [json.loads(line) for line in (work / "interview.jsonl").read_text().splitlines()]
    assert [entry["event"] for entry in entries].count("question_asked") == 6
    assert entries[-1]["event"] == "assessment_charter_completed"


def test_invalid_choice_is_refused_actionably_then_corrected(tmp_path: Path) -> None:
    module = _module()
    intake = _intake(tmp_path / "intake.json")
    answers = iter([
        *_answers()[:3],
        "some-units",
        "all-purpose-relevant-units",
        *_answers()[4:],
    ])
    messages: list[str] = []

    charter = module.run(
        intake,
        tmp_path / "work",
        input_fn=lambda _prompt: next(answers),
        output_fn=messages.append,
    )

    assert charter["status"] == "charter-ready"
    assert messages == [
        "Invalid answer: completion_policy: choose one of: all-purpose-relevant-units."
    ]


def test_partial_interview_resumes_at_exact_pending_question(tmp_path: Path) -> None:
    module = _module()
    intake = _intake(tmp_path / "intake.json")
    work = tmp_path / "work"
    first = iter(_answers()[:2])
    with pytest.raises(StopIteration):
        module.run(intake, work, input_fn=lambda _prompt: next(first))
    prompts: list[str] = []
    remainder = iter(_answers()[2:])

    charter = module.run(
        intake,
        work,
        input_fn=lambda prompt: prompts.append(prompt) or next(remainder),
    )

    assert charter["status"] == "charter-ready"
    assert "independently assessed unit" in prompts[0]


def test_verify_refuses_changed_intake_source(tmp_path: Path) -> None:
    module = _module()
    intake = _intake(tmp_path / "intake.json")
    answers = iter(_answers())
    work = tmp_path / "work"
    module.run(intake, work, input_fn=lambda _prompt: next(answers))
    intake.write_text('{"intake_id":"intake-one","status":"changed"}\n', encoding="utf-8")

    with pytest.raises(module.AssessmentCharterError, match="source changed"):
        module.verify(work / "charter.json")
