#!/usr/bin/env python3
"""Assess every qualification answer through a code-controlled model interview."""

from __future__ import annotations

from collections.abc import Callable
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


CONTRACT = 1
VERDICTS = ["resolves_obligation", "does_not_resolve_obligation"]


class AssessmentError(ValueError):
    """The qualification-assessment journal or one binding is invalid."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _validate_bindings(bindings: list[dict[str, object]]) -> None:
    if not bindings:
        raise AssessmentError("answer-assessment-bindings-empty")
    for index, binding in enumerate(bindings, 1):
        question = binding.get("question")
        obligation = binding.get("obligation")
        source = binding.get("answer_source")
        projection = binding.get("answer_projection")
        readable_projection = binding.get("readable_projection")
        if (
            binding.get("position") != index
            or not isinstance(question, dict)
            or not isinstance(obligation, dict)
            or not isinstance(source, dict)
            or not isinstance(projection, dict)
            or not isinstance(readable_projection, str)
            or not readable_projection.strip()
        ):
            raise AssessmentError(f"qualification-answer-assessment-binding-invalid:{index}")
        if (
            question.get("answers_obligation") != obligation
            or not isinstance(question.get("evidence_sha256"), str)
            or not isinstance(obligation.get("id"), str)
            or not isinstance(source.get("id"), str)
            or not isinstance(source.get("sha256"), str)
            or projection.get("source_id") != source.get("id")
            or not isinstance(projection.get("id"), str)
            or not isinstance(projection.get("sha256"), str)
        ):
            raise AssessmentError(f"qualification-answer-assessment-binding-changed:{index}")


def identities(bindings: list[dict[str, object]]) -> list[dict[str, object]]:
    _validate_bindings(bindings)
    return [
        {
            "position": index,
            "question": binding["question"],
            "obligation": binding["obligation"],
            "answer_source": binding["answer_source"],
            "answer_projection": binding["answer_projection"],
        }
        for index, binding in enumerate(bindings, 1)
    ]


def _assessment_identity(binding: dict[str, object]) -> dict[str, object]:
    obligation = binding["obligation"]
    source = binding["answer_source"]
    projection = binding["answer_projection"]
    question = binding["question"]
    assert all(isinstance(item, dict) for item in (obligation, source, projection, question))
    return {
        "position": binding["position"],
        "question_id": question["id"],
        "obligation_id": obligation["id"],
        "evidence_sha256": question["evidence_sha256"],
        "answer_source_id": source["id"],
        "answer_source_sha256": source["sha256"],
        "answer_projection_id": projection["id"],
        "answer_projection_sha256": projection["sha256"],
    }


def _entry(sequence: int, event: str, payload: dict[str, object], previous: str | None) -> dict[str, object]:
    result: dict[str, object] = {
        "sequence": sequence,
        "event": event,
        "previous_entry_sha256": previous,
        **payload,
    }
    result["entry_sha256"] = _digest(_canonical(result))
    return result


def _read_journal(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    entries: list[dict[str, object]] = []
    previous: str | None = None
    for sequence, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as error:
            raise AssessmentError(f"answer-assessment-journal-json-invalid:{sequence}") from error
        claimed = raw.pop("entry_sha256", None)
        actual = _digest(_canonical(raw))
        raw["entry_sha256"] = claimed
        if raw.get("sequence") != sequence or raw.get("previous_entry_sha256") != previous:
            raise AssessmentError(f"answer-assessment-journal-chain-invalid:{sequence}")
        if claimed != actual:
            raise AssessmentError(f"answer-assessment-journal-entry-changed:{sequence}")
        previous = str(claimed)
        entries.append(raw)
    return entries


def _append(path: Path, event: str, payload: dict[str, object]) -> None:
    entries = _read_journal(path)
    result = _entry(
        len(entries) + 1,
        event,
        payload,
        str(entries[-1]["entry_sha256"]) if entries else None,
    )
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(result, sort_keys=True) + "\n")


def _question(state: dict[str, Any], bindings: list[dict[str, object]]) -> dict[str, object] | None:
    if not state["model"]:
        return {
            "id": "assessor_model",
            "prompt": "Which fresh model is assessing the preserved qualification answers?",
            "type": "string",
            "required": True,
        }
    if not state["harness"]:
        return {
            "id": "assessor_harness",
            "prompt": "Which harness is running this qualification-answer assessment?",
            "type": "string",
            "required": True,
        }
    index = len(state["assessments"])
    if index >= len(bindings):
        return None
    binding = bindings[index]
    if "verdict" not in state["draft"]:
        return {
            "id": f"assessment_verdict_{index + 1:06d}",
            "prompt": "Does this preserved answer resolve the exact qualification obligation it was requested for?",
            "type": "choice",
            "required": True,
            "choices": VERDICTS,
            "binding": binding,
        }
    return {
        "id": f"assessment_reason_{index + 1:06d}",
        "prompt": "Why does this answer resolve or fail to resolve that exact qualification obligation?",
        "type": "string",
        "required": True,
        "binding": binding,
        "verdict": state["draft"]["verdict"],
    }


def _parse(question: dict[str, object], raw: str) -> tuple[str | None, str | None]:
    value = raw.strip()
    if not value or "\n" in value or "\r" in value:
        return None, f"{question['id']}: answer one non-empty field at a time"
    choices = question.get("choices")
    if isinstance(choices, list) and value not in choices:
        return None, f"{question['id']}: got {value!r}; choose one of {choices}"
    return value, None


def _replay(
    entries: list[dict[str, object]], bindings: list[dict[str, object]]
) -> tuple[dict[str, Any], dict[str, object] | None, bool]:
    state: dict[str, Any] = {"model": "", "harness": "", "assessments": [], "draft": {}}
    pending: dict[str, object] | None = None
    completed = False
    for entry in entries:
        if entry["event"] == "question_asked":
            expected = _question(state, bindings)
            if pending is not None or expected != entry.get("question"):
                raise AssessmentError(f"answer-assessment-question-invalid:{entry['sequence']}")
            pending = expected
        elif entry["event"] == "answer_recorded":
            if pending is None or entry.get("question_id") != pending["id"]:
                raise AssessmentError(f"answer-assessment-answer-unbound:{entry['sequence']}")
            if entry.get("accepted"):
                question_id = str(pending["id"])
                parsed = str(entry["parsed"])
                if question_id == "assessor_model":
                    state["model"] = parsed
                elif question_id == "assessor_harness":
                    state["harness"] = parsed
                elif question_id.startswith("assessment_verdict_"):
                    state["draft"]["verdict"] = parsed
                elif question_id.startswith("assessment_reason_"):
                    index = len(state["assessments"])
                    state["assessments"].append(
                        {
                            **_assessment_identity(bindings[index]),
                            "verdict": state["draft"]["verdict"],
                            "reason": parsed,
                        }
                    )
                    state["draft"] = {}
                else:
                    raise AssessmentError(f"answer-assessment-question-unsupported:{entry['sequence']}")
            pending = None
        elif entry["event"] == "assessment_completed":
            if pending is not None or _question(state, bindings) is not None:
                raise AssessmentError(f"answer-assessment-completion-invalid:{entry['sequence']}")
            completed = True
        else:
            raise AssessmentError(f"answer-assessment-event-unsupported:{entry['sequence']}")
    return state, pending, completed


def _prompt(question: dict[str, object], purpose: str) -> str:
    parts = [f"Intake purpose: {purpose}"]
    if "binding" in question:
        parts.append("Code-bound answer context: " + json.dumps(question["binding"], sort_keys=True))
    parts.extend(
        [
            f"Question: {question['prompt']}",
            "Allowed answers: " + json.dumps(question["choices"]) if "choices" in question else "Answer type: string",
            "Answer: ",
        ]
    )
    return "\n".join(parts)


def _terminal_input(prompt: str) -> str:
    print(prompt, end="", file=sys.stderr, flush=True)
    value = sys.stdin.readline()
    if value == "":
        raise AssessmentError("answer-assessment-input-ended")
    return value.rstrip("\n")


def run(
    round_dir: Path,
    *,
    bindings: list[dict[str, object]],
    purpose: str,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> dict[str, object]:
    _validate_bindings(bindings)
    round_dir.mkdir(parents=True, exist_ok=True)
    journal_path = round_dir / "interview.jsonl"
    result_path = round_dir / "assessment.json"
    read = input_fn or _terminal_input
    write = output_fn or (lambda message: print(message, file=sys.stderr))
    while True:
        state, pending, completed = _replay(_read_journal(journal_path), bindings)
        result = {
            "schema_version": CONTRACT,
            "assessor": {"model": state["model"], "harness": state["harness"]},
            "assessment_count": len(bindings),
            "assessments": state["assessments"],
        }
        result_bytes = json.dumps(result, indent=2, sort_keys=True).encode() + b"\n"
        if completed:
            if not result_path.exists():
                result_path.write_bytes(result_bytes)
            if result_path.read_bytes() != result_bytes:
                raise AssessmentError("answer-assessment-result-changed")
            return result
        question = pending or _question(state, bindings)
        if question is None:
            _append(
                journal_path,
                "assessment_completed",
                {"result_sha256": _digest(result_bytes), "assessment_count": len(bindings)},
            )
            result_path.write_bytes(result_bytes)
            continue
        if pending is None:
            _append(journal_path, "question_asked", {"question": question})
        raw = read(_prompt(question, purpose))
        parsed, error = _parse(question, raw)
        _append(
            journal_path,
            "answer_recorded",
            {
                "question_id": question["id"],
                "raw": raw,
                "accepted": error is None,
                "parsed": parsed,
                "error": error,
            },
        )
        if error:
            write(f"Invalid answer: {error}.")


def validate(
    round_dir: Path,
    *,
    bindings: list[dict[str, object]],
    purpose: str,
) -> tuple[dict[str, object], str, str]:
    result = run(
        round_dir,
        bindings=bindings,
        purpose=purpose,
        input_fn=lambda _prompt: (_ for _ in ()).throw(AssessmentError("answer-assessment-not-complete")),
        output_fn=lambda _message: None,
    )
    return (
        result,
        _digest((round_dir / "interview.jsonl").read_bytes()),
        _digest((round_dir / "assessment.json").read_bytes()),
    )
