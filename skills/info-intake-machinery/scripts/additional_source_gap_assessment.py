#!/usr/bin/env python3
"""Assess one projected additional source against its exact originating gap."""

from __future__ import annotations

from collections.abc import Callable
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


CONTRACT = 1
VERDICTS = ["resolves_gap", "does_not_resolve_gap"]
NO_MORE_EVIDENCE = "no_more_evidence"


class AssessmentError(ValueError):
    """The additional-source assessment or one of its bindings is invalid."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _gap_identity(gap: dict[str, object]) -> dict[str, object]:
    try:
        return {
            key: gap[key]
            for key in (
                "projection_sha256",
                "collection",
                "kind",
                "id",
                "record_sha256",
            )
        }
    except KeyError as error:
        raise AssessmentError(
            f"additional-source-gap lost required identity field {error.args[0]!r}"
        ) from error


def _validate_binding(binding: dict[str, object]) -> None:
    gap = binding.get("gap")
    question = binding.get("question")
    source = binding.get("additional_source")
    additional_projection = binding.get("additional_projection")
    original_projection = binding.get("original_projection")
    current_projection = binding.get("current_projection")
    evidence = binding.get("evidence")
    if not all(
        isinstance(item, dict)
        for item in (
            gap,
            question,
            source,
            additional_projection,
            original_projection,
            current_projection,
        )
    ) or not isinstance(evidence, list):
        raise AssessmentError(
            "additional-source binding must contain one gap, question, source, "
            "three projection identities, and an evidence list"
        )
    assert isinstance(gap, dict)
    assert isinstance(question, dict)
    assert isinstance(source, dict)
    assert isinstance(additional_projection, dict)
    assert isinstance(original_projection, dict)
    assert isinstance(current_projection, dict)
    gap_record = gap.get("record")
    if (
        not isinstance(gap_record, dict)
        or gap.get("record_sha256") != _digest(_canonical(gap_record))
        or question.get("answers_gap") != _gap_identity(gap)
    ):
        raise AssessmentError(
            "additional-source gap record, hash, or question binding changed"
        )
    for label, projection in (
        ("original", original_projection),
        ("current", current_projection),
        ("additional", additional_projection),
    ):
        if not isinstance(projection.get("id"), str) or not isinstance(
            projection.get("sha256"), str
        ):
            raise AssessmentError(
                f"{label} projection must retain its identity and sha256"
            )
    if (
        original_projection.get("sha256") != gap.get("projection_sha256")
        or source.get("id") != additional_projection.get("source_id")
    ):
        raise AssessmentError(
            "additional-source assessment no longer points from the original gap "
            "to the projected source"
        )
    seen: set[str] = set()
    for index, item in enumerate(evidence, 1):
        if not isinstance(item, dict):
            raise AssessmentError(
                f"additional-source evidence {index} is not one record"
            )
        evidence_id = item.get("evidence_id")
        record = item.get("item")
        expected_id = f"evidence-{index:06d}"
        if (
            evidence_id != expected_id
            or evidence_id in seen
            or not isinstance(record, dict)
            or item.get("item_sha256") != _digest(_canonical(record))
            or item.get("projection_id") != additional_projection.get("id")
            or item.get("projection_sha256")
            != additional_projection.get("sha256")
            or not isinstance(item.get("collection"), str)
            or not isinstance(item.get("item_id"), str)
        ):
            raise AssessmentError(
                f"additional-source evidence {index} changed or lost its exact projection binding"
            )
        seen.add(evidence_id)


def _entry(
    sequence: int, event: str, payload: dict[str, object], previous: str | None
) -> dict[str, object]:
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
            raise AssessmentError(
                f"additional-source assessment journal line {sequence} is invalid JSON"
            ) from error
        claimed = raw.pop("entry_sha256", None)
        actual = _digest(_canonical(raw))
        raw["entry_sha256"] = claimed
        if (
            raw.get("sequence") != sequence
            or raw.get("previous_entry_sha256") != previous
            or claimed != actual
        ):
            raise AssessmentError(
                f"additional-source assessment journal entry {sequence} changed"
            )
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


def _question(
    state: dict[str, Any], binding: dict[str, object]
) -> dict[str, object] | None:
    if not state["model"]:
        return {
            "id": "assessor_model",
            "prompt": "Which fresh model is assessing the projected additional source?",
            "type": "string",
            "required": True,
        }
    if not state["harness"]:
        return {
            "id": "assessor_harness",
            "prompt": "Which harness is running this additional-source assessment?",
            "type": "string",
            "required": True,
        }
    if not state["verdict"]:
        evidence = binding["evidence"]
        assert isinstance(evidence, list)
        return {
            "id": "assessment_verdict",
            "prompt": "Does this projected additional source resolve the exact original gap?",
            "type": "choice",
            "required": True,
            "choices": VERDICTS if evidence else ["does_not_resolve_gap"],
            "binding": binding,
        }
    if state["verdict"] == "resolves_gap" and not state["evidence_complete"]:
        selected = set(state["selected_evidence_ids"])
        candidates = [
            item
            for item in binding["evidence"]
            if item["evidence_id"] not in selected
        ]
        choices = [str(item["evidence_id"]) for item in candidates]
        if state["selected_evidence_ids"]:
            choices.append(NO_MORE_EVIDENCE)
        return {
            "id": f"evidence_selection_{len(state['selected_evidence_ids']) + 1:06d}",
            "prompt": (
                "Select one exact recorded evidence item that supports resolution. "
                "After selecting every supporting item, choose no_more_evidence."
            ),
            "type": "choice",
            "required": True,
            "choices": choices,
            "evidence": candidates,
        }
    if not state["reason"]:
        return {
            "id": "assessment_reason",
            "prompt": "Why does the selected evidence resolve, or fail to resolve, that exact gap?",
            "type": "string",
            "required": True,
            "binding": binding,
            "verdict": state["verdict"],
            "selected_evidence_ids": state["selected_evidence_ids"],
        }
    return None


def _parse(question: dict[str, object], raw: str) -> tuple[str | None, str | None]:
    value = raw.strip()
    if not value or "\n" in value or "\r" in value:
        return None, f"{question['id']}: answer one non-empty field at a time"
    choices = question.get("choices")
    if isinstance(choices, list) and value not in choices:
        return None, f"{question['id']}: got {value!r}; choose one of {choices}"
    return value, None


def _assembled_assessment(
    state: dict[str, Any], binding: dict[str, object]
) -> dict[str, object] | None:
    if not state["reason"]:
        return None
    selected = set(state["selected_evidence_ids"])
    return {
        "gap": binding["gap"],
        "question": binding["question"],
        "original_projection": binding["original_projection"],
        "current_projection": binding["current_projection"],
        "additional_source": binding["additional_source"],
        "additional_projection": binding["additional_projection"],
        "verdict": state["verdict"],
        "evidence": [
            item for item in binding["evidence"] if item["evidence_id"] in selected
        ],
        "reason": state["reason"],
    }


def _replay(
    entries: list[dict[str, object]], binding: dict[str, object]
) -> tuple[dict[str, Any], dict[str, object] | None, bool]:
    state: dict[str, Any] = {
        "model": "",
        "harness": "",
        "verdict": "",
        "selected_evidence_ids": [],
        "evidence_complete": False,
        "reason": "",
    }
    pending: dict[str, object] | None = None
    completed = False
    for entry in entries:
        if entry["event"] == "question_asked":
            expected = _question(state, binding)
            if pending is not None or expected != entry.get("question"):
                raise AssessmentError(
                    f"additional-source assessment question at entry {entry['sequence']} changed"
                )
            pending = expected
        elif entry["event"] == "answer_recorded":
            if pending is None or entry.get("question_id") != pending["id"]:
                raise AssessmentError(
                    f"additional-source assessment answer at entry {entry['sequence']} is unbound"
                )
            if entry.get("accepted"):
                question_id = str(pending["id"])
                parsed = str(entry["parsed"])
                if question_id == "assessor_model":
                    state["model"] = parsed
                elif question_id == "assessor_harness":
                    state["harness"] = parsed
                elif question_id == "assessment_verdict":
                    state["verdict"] = parsed
                    if parsed == "does_not_resolve_gap":
                        state["evidence_complete"] = True
                elif question_id.startswith("evidence_selection_"):
                    if parsed == NO_MORE_EVIDENCE:
                        state["evidence_complete"] = True
                    else:
                        state["selected_evidence_ids"].append(parsed)
                elif question_id == "assessment_reason":
                    state["reason"] = parsed
                else:
                    raise AssessmentError(
                        f"additional-source assessment question {question_id!r} is unsupported"
                    )
            pending = None
        elif entry["event"] == "assessment_completed":
            if pending is not None or _question(state, binding) is not None:
                raise AssessmentError(
                    f"additional-source assessment completed early at entry {entry['sequence']}"
                )
            completed = True
        else:
            raise AssessmentError(
                f"additional-source assessment event {entry['event']!r} is unsupported"
            )
    return state, pending, completed


def _prompt(question: dict[str, object], purpose: str) -> str:
    parts = [f"Intake purpose: {purpose}"]
    if "binding" in question:
        parts.append(
            "Code-bound assessment context: "
            + json.dumps(question["binding"], sort_keys=True)
        )
    if "evidence" in question:
        parts.append(
            "Code-listed evidence choices: "
            + json.dumps(question["evidence"], sort_keys=True)
        )
    parts.extend([
        f"Question: {question['prompt']}",
        (
            "Allowed answers: " + json.dumps(question["choices"])
            if "choices" in question
            else "Answer type: string"
        ),
        "Answer: ",
    ])
    return "\n".join(parts)


def _terminal_input(prompt: str) -> str:
    print(prompt, end="", file=sys.stderr, flush=True)
    value = sys.stdin.readline()
    if value == "":
        raise AssessmentError("additional-source assessment input ended")
    return value.rstrip("\n")


def run(
    assessment_dir: Path,
    *,
    binding: dict[str, object],
    purpose: str,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> dict[str, object]:
    _validate_binding(binding)
    assessment_dir.mkdir(parents=True, exist_ok=True)
    journal_path = assessment_dir / "interview.jsonl"
    result_path = assessment_dir / "assessment.json"
    read = input_fn or _terminal_input
    write = output_fn or (lambda message: print(message, file=sys.stderr))
    while True:
        state, pending, completed = _replay(_read_journal(journal_path), binding)
        result = {
            "schema_version": CONTRACT,
            "assessor": {"model": state["model"], "harness": state["harness"]},
            "assessment": _assembled_assessment(state, binding),
        }
        result_bytes = json.dumps(result, indent=2, sort_keys=True).encode() + b"\n"
        if completed:
            if not result_path.exists():
                result_path.write_bytes(result_bytes)
            if result_path.read_bytes() != result_bytes:
                raise AssessmentError("additional-source assessment result changed")
            return result
        question = pending or _question(state, binding)
        if question is None:
            _append(
                journal_path,
                "assessment_completed",
                {"result_sha256": _digest(result_bytes)},
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
    assessment_dir: Path,
    *,
    binding: dict[str, object],
    purpose: str,
) -> tuple[dict[str, object], str, str]:
    result = run(
        assessment_dir,
        binding=binding,
        purpose=purpose,
        input_fn=lambda _prompt: (_ for _ in ()).throw(
            AssessmentError("additional-source assessment is not complete")
        ),
        output_fn=lambda _message: None,
    )
    return (
        result,
        _digest((assessment_dir / "interview.jsonl").read_bytes()),
        _digest((assessment_dir / "assessment.json").read_bytes()),
    )
