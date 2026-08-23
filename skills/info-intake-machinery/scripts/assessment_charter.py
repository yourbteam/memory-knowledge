#!/usr/bin/env python3
"""Create and verify an immutable purpose-driven assessment charter."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

CONTRACT = 1
_SCRIPT_DIR = Path(__file__).resolve().parent
_JOURNAL_SPEC = importlib.util.spec_from_file_location(
    "assessment_charter_journal", _SCRIPT_DIR / "projection_interview.py"
)
if _JOURNAL_SPEC is None or _JOURNAL_SPEC.loader is None:
    raise RuntimeError("assessment charter journal is unavailable")
journal = importlib.util.module_from_spec(_JOURNAL_SPEC)
_JOURNAL_SPEC.loader.exec_module(journal)


class AssessmentCharterError(RuntimeError):
    """Raised when a charter or its append-only interview is invalid."""


FIELDS = (
    "purpose",
    "decision",
    "unit_definition",
    "completion_policy",
    "unresolved_policy",
    "downstream_use",
)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_intake(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as error:
        raise AssessmentCharterError(f"intake artifact is unavailable or invalid JSON: {error}") from error
    if not isinstance(value, dict):
        raise AssessmentCharterError("intake artifact must contain one object")
    intake_id = value.get("intake_id")
    if not isinstance(intake_id, str) or not intake_id.strip():
        raise AssessmentCharterError("intake artifact intake_id must be one non-empty string")
    return value, raw


def _question(stage: str) -> dict[str, object] | None:
    if stage == "purpose":
        return journal._field("purpose", "What practical question should this intake assess?", "string")
    if stage == "decision":
        return journal._field("decision", "What decision should the completed assessment enable?", "string")
    if stage == "unit_definition":
        return journal._field("unit_definition", "What does one independently assessed unit represent?", "string")
    if stage == "completion_policy":
        return journal._field(
            "completion_policy",
            "Which coverage rule must completion satisfy?",
            "choice",
            choices=["all-purpose-relevant-units"],
        )
    if stage == "unresolved_policy":
        return journal._field(
            "unresolved_policy",
            "How should genuinely missing evidence affect the final result?",
            "choice",
            choices=["block-until-resolved", "allow-incomplete-verdict"],
        )
    if stage == "downstream_use":
        return journal._field("downstream_use", "How will the next machinery use the assessment result?", "string")
    if stage == "complete":
        return None
    raise AssessmentCharterError(f"assessment charter stage is unsupported: {stage}")


def _next_stage(stage: str) -> str:
    index = FIELDS.index(stage)
    return FIELDS[index + 1] if index + 1 < len(FIELDS) else "complete"


def _prompt(question: dict[str, object]) -> str:
    lines = [f"Question: {question['prompt']}", f"Answer type: {question['type']}"]
    if question["type"] == "choice":
        lines.append("Allowed values: " + ", ".join(question["choices"]))
    lines.append("Answer: ")
    return "\n".join(lines)


def _terminal_input(prompt: str) -> str:
    print(prompt, end="", file=sys.stderr, flush=True)
    raw = sys.stdin.readline()
    if raw == "":
        raise AssessmentCharterError("assessment charter input ended")
    return raw.rstrip("\n")


def _replay(
    entries: list[dict[str, object]], intake_ref: dict[str, object]
) -> tuple[str, dict[str, str], dict[str, object] | None, bool]:
    if not entries:
        return "purpose", {}, None, False
    started = entries[0]
    if started.get("event") != "assessment_charter_started" or started.get("intake") != intake_ref:
        raise AssessmentCharterError("assessment charter intake binding changed")
    stage = "purpose"
    answers: dict[str, str] = {}
    pending: dict[str, object] | None = None
    completed = False
    for entry in entries[1:]:
        event = entry.get("event")
        if event == "question_asked":
            expected = _question(stage)
            if completed or pending is not None or expected is None or entry.get("question") != expected:
                raise AssessmentCharterError(f"assessment charter question changed at sequence {entry['sequence']}")
            pending = expected
        elif event == "answer_recorded":
            if pending is None or entry.get("question_id") != pending["id"]:
                raise AssessmentCharterError(f"assessment charter answer is unbound at sequence {entry['sequence']}")
            raw = entry.get("raw")
            if not isinstance(raw, str):
                raise AssessmentCharterError(f"assessment charter answer is invalid at sequence {entry['sequence']}")
            parsed, error = journal._parse(pending, raw, {"elements": []})
            accepted = error is None
            if entry.get("accepted") is not accepted or entry.get("parsed") != parsed or entry.get("error") != error:
                raise AssessmentCharterError(f"assessment charter answer changed at sequence {entry['sequence']}")
            if accepted:
                answers[str(pending["id"])] = str(parsed)
                stage = _next_stage(stage)
            pending = None
        elif event == "assessment_charter_completed":
            if completed or pending is not None or stage != "complete":
                raise AssessmentCharterError(f"assessment charter completion is invalid at sequence {entry['sequence']}")
            completed = True
        else:
            raise AssessmentCharterError(f"assessment charter event is unsupported at sequence {entry['sequence']}")
    return stage, answers, pending, completed


def _charter(intake_ref: dict[str, object], answers: dict[str, str]) -> dict[str, object]:
    result: dict[str, object] = {
        "schema_version": CONTRACT,
        "artifact_type": "info-intake-assessment-charter",
        "status": "charter-ready",
        "intake": intake_ref,
        "assessment": {field: answers[field] for field in FIELDS},
    }
    result["artifact_sha256"] = _digest(_canonical(result))
    return result


def run(
    intake_path: Path,
    work_dir: Path,
    *,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> dict[str, object]:
    intake, intake_bytes = _load_intake(intake_path)
    intake_ref: dict[str, object] = {
        "path": str(intake_path.resolve()),
        "sha256": _digest(intake_bytes),
        "intake_id": intake["intake_id"],
    }
    work_dir.mkdir(parents=True, exist_ok=True)
    journal_path = work_dir / "interview.jsonl"
    charter_path = work_dir / "charter.json"
    read = input_fn or _terminal_input
    write = output_fn or (lambda message: print(message, file=sys.stderr))
    if not journal_path.exists():
        journal._append(journal_path, "assessment_charter_started", {"intake": intake_ref})

    while True:
        entries = journal._read_journal(journal_path)
        stage, answers, pending, completed = _replay(entries, intake_ref)
        charter = _charter(intake_ref, answers) if stage == "complete" else None
        payload = json.dumps(charter, indent=2, sort_keys=True).encode("utf-8") + b"\n" if charter else None
        if completed:
            assert payload is not None
            if not charter_path.is_file() or charter_path.read_bytes() != payload:
                raise AssessmentCharterError("completed assessment charter artifact changed or is missing")
            return charter
        question = pending or _question(stage)
        if question is None:
            assert payload is not None
            if charter_path.exists():
                raise AssessmentCharterError("unbound assessment charter artifact already exists")
            journal._append(journal_path, "assessment_charter_completed", {
                "charter_path": "charter.json",
                "charter_sha256": _digest(payload),
            })
            charter_path.write_bytes(payload)
            continue
        if pending is None:
            journal._append(journal_path, "question_asked", {"question": question})
        raw = read(_prompt(question))
        parsed, error = journal._parse(question, raw, {"elements": []})
        journal._append(journal_path, "answer_recorded", {
            "question_id": question["id"],
            "raw": raw,
            "accepted": error is None,
            "parsed": parsed,
            "error": error,
        })
        if error:
            write(f"Invalid answer: {error}.")


def verify(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AssessmentCharterError(f"assessment charter is unavailable or invalid JSON: {error}") from error
    if not isinstance(value, dict) or value.get("artifact_type") != "info-intake-assessment-charter":
        raise AssessmentCharterError("assessment charter artifact type is invalid")
    claimed = value.pop("artifact_sha256", None)
    actual = _digest(_canonical(value))
    value["artifact_sha256"] = claimed
    if claimed != actual:
        raise AssessmentCharterError("assessment charter artifact digest changed")
    intake = value.get("intake")
    assessment = value.get("assessment")
    if not isinstance(intake, dict) or set(intake) != {"path", "sha256", "intake_id"}:
        raise AssessmentCharterError("assessment charter intake binding is invalid")
    source_path = Path(str(intake["path"]))
    if not source_path.is_file() or _digest(source_path.read_bytes()) != intake["sha256"]:
        raise AssessmentCharterError("assessment charter intake source changed")
    if not isinstance(assessment, dict) or set(assessment) != set(FIELDS):
        raise AssessmentCharterError("assessment charter fields are incomplete")
    if assessment["completion_policy"] != "all-purpose-relevant-units":
        raise AssessmentCharterError("assessment charter completion policy is invalid")
    if assessment["unresolved_policy"] not in {"block-until-resolved", "allow-incomplete-verdict"}:
        raise AssessmentCharterError("assessment charter unresolved policy is invalid")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("run")
    create.add_argument("--intake", type=Path, required=True)
    create.add_argument("--work-dir", type=Path, required=True)
    check = subparsers.add_parser("verify")
    check.add_argument("charter", type=Path)
    args = parser.parse_args()
    try:
        result = run(args.intake, args.work_dir) if args.command == "run" else verify(args.charter)
    except AssessmentCharterError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps({
        "status": result["status"],
        "intake_id": result["intake"]["intake_id"],
        "artifact_sha256": result["artifact_sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
