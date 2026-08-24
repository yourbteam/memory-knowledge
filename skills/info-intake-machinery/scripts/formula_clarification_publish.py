#!/usr/bin/env python3
"""Publish one operator clarification as immutable formula-map successors."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from formula_clarification_successor import build_successor
from formula_operator_answer_binding import bind_answer
from reporting_v3_column_calculation_evidence import capture_column_evidence
from reporting_v3_column_index import _canonical, _read_object, _sha, _validate_formula_ledger


ALLOWED_CHOICES = (
    "confirmed_ah_mapping",
    "rejected_ah_mapping",
    "needs_clarification",
)
REQUIRED_CHOICE = "confirmed_ah_mapping"
EXPECTED_COLUMN = "AH"
EXPECTED_HEADER = "Sessions with Visitor Info Collected"
EXPECTED_ROOT = "row.UniqueVisitors"
RESOLUTION_REASON = (
    "The operator confirmed dashboard guest count is Reporting V3 Column AH, "
    "Sessions with Visitor Info Collected (row.UniqueVisitors); the preserved "
    "code evidence now completes this formula."
)


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True).encode() + b"\n"


def _expect_immutable(path: Path, data: bytes, label: str) -> None:
    if path.exists() and path.read_bytes() != data:
        raise ValueError(f"{label} exists with different immutable bytes")


def _write_once(path: Path, data: bytes) -> None:
    if not path.exists():
        with path.open("xb") as handle:
            handle.write(data)


def _event(
    sequence: int,
    event: str,
    previous: str,
    intake_id: object,
    fields: dict[str, object],
) -> dict[str, object]:
    value = {
        "schema_version": 1,
        "sequence": sequence,
        "event": event,
        "previous_entry_sha256": previous,
        "intake_id": intake_id,
        **fields,
    }
    value["entry_sha256"] = _sha(_canonical(value))
    return value


def publish(work: Path, answer_path: Path) -> dict[str, object]:
    work = work.resolve()
    formula_root = work / "formula-map"
    ledger_path = formula_root / "ledger.jsonl"
    entries = _validate_formula_ledger(ledger_path)
    if len(entries) < 7 or entries[6].get("event") != "terminal_formula_map_recorded":
        raise ValueError("formula-map ledger has no terminal predecessor")

    terminal_path = formula_root / "terminal-formula-map.json"
    questions_path = formula_root / "operator-questions.json"
    index_path = formula_root / "reporting-v3-column-index.json"
    terminal_bytes = terminal_path.read_bytes()
    questions_bytes = questions_path.read_bytes()
    index_bytes = index_path.read_bytes()
    index = _read_object(index_path, "Reporting V3 column index")
    indexed_source = index.get("source")
    if not isinstance(indexed_source, dict) or not isinstance(
        indexed_source.get("path"), str
    ):
        raise ValueError("Reporting V3 column index has no source path")
    source_path = (work / indexed_source["path"]).resolve()
    if source_path.parent != (work / "sources").resolve():
        raise ValueError("Reporting V3 indexed source must be directly under work/sources")
    source_bytes = source_path.read_bytes()
    if (
        entries[6].get("terminal_map_sha256") != _sha(terminal_bytes)
        or entries[6].get("operator_questions_sha256") != _sha(questions_bytes)
    ):
        raise ValueError("terminal predecessor bytes differ from ledger evidence")
    if (
        len(entries) < 2
        or entries[1].get("event") != "reporting_v3_column_index_recorded"
        or entries[1].get("index_sha256") != _sha(index_bytes)
        or entries[1].get("source_sha256") != _sha(source_bytes)
    ):
        raise ValueError("Reporting V3 source or column index differs from ledger evidence")

    terminal = _read_object(terminal_path, "terminal formula map")
    questions = _read_object(questions_path, "operator questions")
    raw_answer = _read_object(answer_path.resolve(), "operator answer")
    question_items = questions.get("questions")
    if not isinstance(question_items, list) or len(question_items) != 1:
        raise ValueError("operator question set must contain exactly one active question")
    bound_answer = bind_answer(
        question_items[0], raw_answer, ALLOWED_CHOICES, REQUIRED_CHOICE
    )
    calculation = capture_column_evidence(
        index,
        source_bytes.decode("utf-8"),
        excel_column=EXPECTED_COLUMN,
        expected_header=EXPECTED_HEADER,
        expected_root=EXPECTED_ROOT,
    )

    answer_artifact_path = formula_root / "operator-answer-000001.json"
    evidence_path = formula_root / "reporting-v3-ah-guest-count-evidence.json"
    answer_bytes = _json_bytes(bound_answer)
    evidence_artifact = {
        "schema_version": 1,
        "intake_id": terminal.get("intake_id"),
        "source": {
            "path": str(source_path.relative_to(work)),
            "sha256": _sha(source_bytes),
        },
        "column_index": {
            "path": str(index_path.relative_to(work)),
            "sha256": _sha(index_bytes),
        },
        "calculation": calculation,
    }
    evidence_bytes = _json_bytes(evidence_artifact)
    successor = build_successor(
        terminal,
        questions,
        bound_answer,
        calculation,
        required_choice=REQUIRED_CHOICE,
        resolution_reason=RESOLUTION_REASON,
        predecessor_sha256=_sha(terminal_bytes),
        answer_sha256=_sha(answer_bytes),
        evidence_sha256=_sha(evidence_bytes),
    )
    successor_path = formula_root / "terminal-formula-map-v2.json"
    successor_bytes = _json_bytes(successor)
    successor_questions = {
        "schema_version": 2,
        "status": "complete",
        "supersedes_operator_questions_sha256": _sha(questions_bytes),
        "resolved_question_ids": [question_items[0]["id"]],
        "unresolved_claim_count": 0,
        "question_count": 0,
        "questions": [],
    }
    successor_questions_path = formula_root / "operator-questions-v2.json"
    successor_questions_bytes = _json_bytes(successor_questions)

    artifacts = (
        (answer_artifact_path, answer_bytes, "operator answer"),
        (evidence_path, evidence_bytes, "guest-count calculation evidence"),
        (successor_path, successor_bytes, "successor terminal formula map"),
        (
            successor_questions_path,
            successor_questions_bytes,
            "successor operator questions",
        ),
    )
    for path, data, label in artifacts:
        _expect_immutable(path, data, label)

    event8 = _event(
        8,
        "operator_clarification_answer_recorded",
        entries[6]["entry_sha256"],
        terminal.get("intake_id"),
        {
            "question_id": question_items[0]["id"],
            "question_claim_ids": question_items[0]["claim_ids"],
            "operator_questions_sha256": _sha(questions_bytes),
            "answer_path": str(answer_artifact_path.relative_to(work)),
            "answer_sha256": _sha(answer_bytes),
            "choice": bound_answer["choice"],
        },
    )
    event9 = _event(
        9,
        "reporting_v3_guest_count_evidence_recorded",
        event8["entry_sha256"],
        terminal.get("intake_id"),
        {
            "source_id": source_path.name,
            "source_sha256": _sha(source_bytes),
            "column_index_sha256": _sha(index_bytes),
            "excel_column": EXPECTED_COLUMN,
            "calculation_root": EXPECTED_ROOT,
            "evidence_path": str(evidence_path.relative_to(work)),
            "evidence_sha256": _sha(evidence_bytes),
        },
    )
    event10 = _event(
        10,
        "successor_terminal_formula_map_recorded",
        event9["entry_sha256"],
        terminal.get("intake_id"),
        {
            "predecessor_terminal_map_sha256": _sha(terminal_bytes),
            "terminal_map_path": str(successor_path.relative_to(work)),
            "terminal_map_sha256": _sha(successor_bytes),
            "predecessor_operator_questions_sha256": _sha(questions_bytes),
            "operator_questions_path": str(successor_questions_path.relative_to(work)),
            "operator_questions_sha256": _sha(successor_questions_bytes),
            "claim_count": successor["claim_count"],
            "verdict_counts": successor["verdict_counts"],
            "operator_question_count": 0,
        },
    )
    expected_events = (event8, event9, event10)
    if len(entries) > 10:
        raise ValueError("formula-map ledger has unexpected entries after clarification")
    for offset, expected in enumerate(expected_events, start=7):
        if len(entries) > offset and entries[offset] != expected:
            raise ValueError(
                f"formula-map ledger sequence {offset + 1} differs from clarification evidence"
            )

    for path, data, _label in artifacts:
        _write_once(path, data)
    with ledger_path.open("ab") as handle:
        for offset, expected in enumerate(expected_events, start=7):
            if len(entries) == offset:
                payload = _canonical(expected) + b"\n"
                handle.write(payload)
                entries.append(expected)

    return {
        "status": "formula_clarification_recorded",
        "claim_count": successor["claim_count"],
        "verdict_counts": successor["verdict_counts"],
        "operator_question_count": 0,
        "terminal_map": str(successor_path),
        "operator_questions": str(successor_questions_path),
        "answer": str(answer_artifact_path),
        "calculation_evidence": str(evidence_path),
        "ledger_tail_sha256": event10["entry_sha256"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--answer", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = publish(args.work, args.answer)
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "refused", "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
