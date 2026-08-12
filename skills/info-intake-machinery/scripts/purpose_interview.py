#!/usr/bin/env python3
"""Run a code-controlled intake-purpose assessment interview."""

from __future__ import annotations

from collections.abc import Callable
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any


CONTRACT = 1

_JOURNAL_SPEC = importlib.util.spec_from_file_location(
    "info_intake_interview_journal",
    Path(__file__).resolve().with_name("projection_interview.py"),
)
if _JOURNAL_SPEC is None or _JOURNAL_SPEC.loader is None:
    raise RuntimeError("interview journal is unavailable")
journal = importlib.util.module_from_spec(_JOURNAL_SPEC)
_JOURNAL_SPEC.loader.exec_module(journal)
InterviewError = journal.InterviewError


def _initial_state() -> dict[str, Any]:
    return {"stage": "reader_model", "reader": {}, "answers": {}}


def _question(state: dict[str, Any]) -> dict[str, object] | None:
    stage = state["stage"]
    if stage == "complete":
        return None
    if stage == "reader_model":
        return journal._field("reader_model", "Which model is assessing the preserved purpose?", "string")
    if stage == "reader_harness":
        return journal._field("reader_harness", "Which harness is running this interview?", "string")
    if stage == "sufficient":
        return journal._field(
            "sufficient",
            "Does the purpose identify what information, distinctions, or relationships must survive conversion clearly enough to request the first source?",
            "choice",
            choices=["yes", "no"],
        )
    if stage == "reason":
        return journal._field("reason", "What evidence in the preserved purpose supports that choice?", "string")
    if stage == "quote":
        return journal._field("quote", "What exact words from the preserved purpose establish what must survive?", "string")
    if stage == "clarifying_question":
        return journal._field(
            "clarifying_question",
            "What one short question would supply the earliest missing boundary?",
            "string",
        )
    raise InterviewError(f"purpose-interview-stage-unsupported:{stage}")


def _parse(
    question: dict[str, object], raw: str, state: dict[str, Any], purpose: str
) -> tuple[object | None, str | None]:
    parsed, error = journal._parse(question, raw, {"elements": []})
    if error:
        return parsed, error
    field_id = question["id"]
    if field_id == "quote" and str(parsed) not in purpose:
        return None, "quote: answer with an exact non-empty passage from the preserved purpose"
    if field_id == "clarifying_question":
        value = str(parsed)
        if len(value) > 240 or value.count("?") != 1 or not value.endswith("?"):
            return None, "clarifying_question: answer with exactly one short question ending in ?"
    return parsed, None


def _advance(state: dict[str, Any], field_id: str, value: object) -> None:
    if field_id == "reader_model":
        state["reader"]["model"] = value
        state["stage"] = "reader_harness"
    elif field_id == "reader_harness":
        state["reader"]["harness"] = value
        state["stage"] = "sufficient"
    elif field_id == "sufficient":
        state["answers"]["sufficient"] = value
        state["stage"] = "reason"
    elif field_id == "reason":
        state["answers"]["reason"] = value
        state["stage"] = "quote" if state["answers"]["sufficient"] == "yes" else "clarifying_question"
    elif field_id == "quote":
        state["answers"]["quote"] = value
        state["answers"]["clarifying_question"] = ""
        state["stage"] = "complete"
    elif field_id == "clarifying_question":
        state["answers"]["quote"] = ""
        state["answers"]["clarifying_question"] = value
        state["stage"] = "complete"
    else:
        raise InterviewError(f"purpose-interview-field-unsupported:{field_id}")


def _replay(
    entries: list[dict[str, object]], purpose: str
) -> tuple[dict[str, Any], dict[str, object] | None, bool]:
    state = _initial_state()
    pending: dict[str, object] | None = None
    completed = False
    for entry in entries:
        event = entry.get("event")
        if event == "question_asked":
            expected = _question(state)
            if pending is not None or expected is None or entry.get("question") != expected:
                raise InterviewError(f"purpose-interview-question-invalid:{entry['sequence']}")
            pending = expected
        elif event == "answer_recorded":
            if pending is None or entry.get("question_id") != pending["id"]:
                raise InterviewError(f"purpose-interview-answer-unbound:{entry['sequence']}")
            raw = entry.get("raw")
            if not isinstance(raw, str):
                raise InterviewError(f"purpose-interview-answer-invalid:{entry['sequence']}")
            parsed, error = _parse(pending, raw, state, purpose)
            accepted = error is None
            if (
                entry.get("accepted") is not accepted
                or entry.get("error") != error
                or entry.get("parsed") != parsed
            ):
                raise InterviewError(f"purpose-interview-answer-changed:{entry['sequence']}")
            if accepted:
                _advance(state, str(pending["id"]), parsed)
            pending = None
        elif event == "interview_completed":
            if pending is not None or _question(state) is not None or completed:
                raise InterviewError(f"purpose-interview-completion-invalid:{entry['sequence']}")
            completed = True
        else:
            raise InterviewError(f"purpose-interview-event-unsupported:{entry['sequence']}")
    return state, pending, completed


def _assessment(state: dict[str, Any]) -> dict[str, object]:
    answers = state["answers"]
    return {
        "schema_version": CONTRACT,
        "sufficient": answers["sufficient"],
        "quote": answers["quote"],
        "reason": answers["reason"],
        "clarifying_question": answers["clarifying_question"],
        "reader": state["reader"],
    }


def _prompt(question: dict[str, object], purpose: str) -> str:
    lines = [
        "Preserved purpose: " + purpose,
        f"Question: {question['prompt']}",
        f"Answer type: {question['type']}",
    ]
    if question["type"] == "choice":
        lines.append("Allowed values: " + ", ".join(question["choices"]))
    lines.append("Answer: ")
    return "\n".join(lines)


def _terminal_input(prompt: str) -> str:
    print(prompt, end="", file=sys.stderr, flush=True)
    value = sys.stdin.readline()
    if value == "":
        raise InterviewError("purpose-interview-input-ended")
    return value.rstrip("\n")


def run(
    attempt_dir: Path,
    *,
    purpose: str,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> dict[str, object]:
    attempt_dir.mkdir(parents=True, exist_ok=True)
    journal_path = attempt_dir / "interview.jsonl"
    assessment_path = attempt_dir / "assessment.json"
    read = input_fn or _terminal_input
    write = output_fn or (lambda message: print(message, file=sys.stderr))

    while True:
        entries = journal._read_journal(journal_path)
        state, pending, completed = _replay(entries, purpose)
        assessment = _assessment(state) if state["stage"] == "complete" else None
        assessment_bytes = (
            json.dumps(assessment, indent=2, sort_keys=True).encode("utf-8") + b"\n"
            if assessment is not None else None
        )
        if completed:
            assert assessment_bytes is not None
            completion = entries[-1]
            if (
                completion.get("assessment_path") != "assessment.json"
                or completion.get("assessment_sha256") != journal._digest(assessment_bytes)
            ):
                raise InterviewError("completed-purpose-assessment-record-invalid")
            if not assessment_path.exists():
                assessment_path.write_bytes(assessment_bytes)
            if assessment_path.read_bytes() != assessment_bytes:
                raise InterviewError("completed-purpose-assessment-changed")
            assert assessment is not None
            return assessment

        question = pending or _question(state)
        if question is None:
            assert assessment_bytes is not None
            if assessment_path.exists():
                raise InterviewError("unbound-purpose-assessment-artifact")
            journal._append(journal_path, "interview_completed", {
                "assessment_path": "assessment.json",
                "assessment_sha256": journal._digest(assessment_bytes),
            })
            assessment_path.write_bytes(assessment_bytes)
            continue
        if pending is None:
            journal._append(journal_path, "question_asked", {"question": question})
        raw = read(_prompt(question, purpose))
        parsed, error = _parse(question, raw, state, purpose)
        journal._append(journal_path, "answer_recorded", {
            "question_id": question["id"],
            "raw": raw,
            "accepted": error is None,
            "parsed": parsed,
            "error": error,
        })
        if error:
            write(f"Invalid answer: {error}.")


def validate(attempt_dir: Path, *, purpose: str) -> tuple[dict[str, object], str, str]:
    assessment = run(
        attempt_dir,
        purpose=purpose,
        input_fn=lambda _prompt: (_ for _ in ()).throw(InterviewError("purpose-interview-not-complete")),
        output_fn=lambda _message: None,
    )
    journal_path = attempt_dir / "interview.jsonl"
    assessment_path = attempt_dir / "assessment.json"
    return assessment, journal._digest(journal_path.read_bytes()), journal._digest(assessment_path.read_bytes())
