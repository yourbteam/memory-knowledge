#!/usr/bin/env python3
"""Run the append-only, resumable formula assessment interview."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from formula_assessment_answer import admit_answer
from formula_assessment_question import render_question
from reporting_v3_column_index import _canonical, _read_object, _sha, _validate_formula_ledger


class FormulaAssessmentInterviewError(ValueError):
    """The formula assessment interview cannot continue safely."""


_JOURNAL_NAME = "assessment-interview-v2-ledger.jsonl"
_SUPERSEDED_JOURNAL_NAME = "assessment-interview-ledger.jsonl"


def _journal(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    entries: list[dict[str, object]] = []
    previous: str | None = None
    for sequence, line in enumerate(path.read_text().splitlines(), start=1):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise FormulaAssessmentInterviewError(
                f"assessment journal entry {sequence} is invalid JSON"
            ) from exc
        if not isinstance(entry, dict):
            raise FormulaAssessmentInterviewError(
                f"assessment journal entry {sequence} is not an object"
            )
        claimed = entry.pop("entry_sha256", None)
        actual = _sha(_canonical(entry))
        entry["entry_sha256"] = claimed
        if (
            entry.get("sequence") != sequence
            or entry.get("previous_entry_sha256") != previous
            or claimed != actual
        ):
            raise FormulaAssessmentInterviewError(
                f"assessment journal entry {sequence} fails its hash chain"
            )
        entries.append(entry)
        previous = str(claimed)
    return entries


def _append(path: Path, event: dict[str, object], entries: list[dict[str, object]]) -> None:
    event["sequence"] = len(entries) + 1
    event["previous_entry_sha256"] = (
        entries[-1]["entry_sha256"] if entries else None
    )
    event["entry_sha256"] = _sha(_canonical(event))
    with path.open("ab") as handle:
        handle.write(_canonical(event) + b"\n")


def _packets(work: Path) -> tuple[dict[str, object], bytes]:
    path = work / "formula-map/assessment-packets.json"
    data = path.read_bytes()
    value = _read_object(path, "formula assessment packets")
    ledger = _validate_formula_ledger(work / "formula-map/ledger.jsonl")
    if (
        len(ledger) < 5
        or ledger[4].get("event") != "formula_assessment_packets_recorded"
        or ledger[4].get("assessment_packets_sha256") != _sha(data)
    ):
        raise FormulaAssessmentInterviewError(
            "assessment packets differ from formula-map ledger evidence"
        )
    return value, data


def _context(work: Path) -> tuple[dict[str, object], bytes]:
    path = work / "formula-map/assessment-shared-context.json"
    data = path.read_bytes()
    value = _read_object(path, "formula assessment shared context")
    ledger = _validate_formula_ledger(work / "formula-map/ledger.jsonl")
    if (
        len(ledger) < 6
        or ledger[5].get("event") != "formula_assessment_shared_context_recorded"
        or ledger[5].get("shared_context_sha256") != _sha(data)
    ):
        raise FormulaAssessmentInterviewError(
            "assessment shared context differs from formula-map ledger evidence"
        )
    return value, data


def start(work: Path) -> dict[str, object]:
    work = work.resolve()
    packets_value, packets_bytes = _packets(work)
    context_value, context_bytes = _context(work)
    packets = packets_value.get("packets")
    if not isinstance(packets, list) or not packets:
        raise FormulaAssessmentInterviewError("assessment packet list is empty")
    prior_path = work / f"formula-map/{_SUPERSEDED_JOURNAL_NAME}"
    prior_entries = _journal(prior_path)
    if not prior_entries or prior_entries[-1].get("event") != "assessment_question_asked":
        raise FormulaAssessmentInterviewError(
            "the preserved prior interview must stop at its unanswered question"
        )
    path = work / f"formula-map/{_JOURNAL_NAME}"
    entries = _journal(path)
    event = {
        "schema_version": 1,
        "event": "assessment_interview_started",
        "intake_id": packets_value.get("intake_id"),
        "assessment_packets_sha256": _sha(packets_bytes),
        "shared_context_sha256": _sha(context_bytes),
        "claim_count": len(packets),
        "supersedes": {
            "journal_path": f"formula-map/{_SUPERSEDED_JOURNAL_NAME}",
            "journal_tail_sha256": prior_entries[-1]["entry_sha256"],
        },
    }
    if not entries:
        _append(path, event, entries)
        entries = _journal(path)
    elif len(entries) < 1 or any(
        entries[0].get(key) != value for key, value in event.items()
    ):
        raise FormulaAssessmentInterviewError(
            "assessment interview already exists for different immutable packets"
        )
    return status(work)


def _replay(work: Path) -> tuple[list[dict[str, object]], list[object], list[dict[str, object]]]:
    packets_value, packets_bytes = _packets(work)
    context_value, context_bytes = _context(work)
    shared = context_value.get("shared_code_evidence")
    if not isinstance(shared, list):
        raise FormulaAssessmentInterviewError("assessment shared code evidence is invalid")
    packets = packets_value.get("packets")
    if not isinstance(packets, list):
        raise FormulaAssessmentInterviewError("assessment packet list is invalid")
    entries = _journal(work / f"formula-map/{_JOURNAL_NAME}")
    if not entries:
        raise FormulaAssessmentInterviewError("assessment interview has not been started")
    if (
        entries[0].get("event") != "assessment_interview_started"
        or entries[0].get("assessment_packets_sha256") != _sha(packets_bytes)
        or entries[0].get("shared_context_sha256") != _sha(context_bytes)
        or entries[0].get("claim_count") != len(packets)
    ):
        raise FormulaAssessmentInterviewError(
            "assessment interview start does not bind the current packets"
        )
    answers: list[dict[str, object]] = []
    pending: dict[str, object] | None = None
    for entry in entries[1:]:
        event = entry.get("event")
        if event == "assessment_question_asked":
            if pending is not None:
                raise FormulaAssessmentInterviewError(
                    "assessment journal asks another question before recording the active answer"
                )
            question = entry.get("question")
            if not isinstance(question, dict):
                raise FormulaAssessmentInterviewError("question event has no question object")
            expected = render_question(packets, len(answers), shared)
            if question != expected:
                raise FormulaAssessmentInterviewError(
                    f"question {question.get('question_id')!r} differs from deterministic packet order"
                )
            pending = question
        elif event == "assessment_answer_recorded":
            if pending is None:
                raise FormulaAssessmentInterviewError(
                    "assessment journal records an answer without an active question"
                )
            answer = admit_answer(pending, entry.get("answer"))
            answers.append(answer)
            pending = None
        else:
            raise FormulaAssessmentInterviewError(
                f"assessment journal contains unsupported event {event!r}"
            )
    return entries, packets, answers if pending is None else [*answers, {"_pending": pending}]


def next_question(work: Path) -> dict[str, object]:
    work = work.resolve()
    entries, packets, replayed = _replay(work)
    pending = replayed[-1].get("_pending") if replayed and "_pending" in replayed[-1] else None
    answers = replayed[:-1] if pending is not None else replayed
    if pending is not None:
        return {"status": "awaiting_answer", "question": pending}
    if len(answers) == len(packets):
        return {"status": "assessment_interview_complete", "answered": len(answers)}
    context_value, _ = _context(work)
    shared = context_value.get("shared_code_evidence")
    assert isinstance(shared, list)
    question = render_question(packets, len(answers), shared)
    _append(
        work / f"formula-map/{_JOURNAL_NAME}",
        {"schema_version": 1, "event": "assessment_question_asked", "question": question},
        entries,
    )
    return {"status": "awaiting_answer", "question": question}


def answer(work: Path, response_path: Path) -> dict[str, object]:
    work = work.resolve()
    entries, packets, replayed = _replay(work)
    pending = replayed[-1].get("_pending") if replayed and "_pending" in replayed[-1] else None
    if not isinstance(pending, dict):
        raise FormulaAssessmentInterviewError("there is no active assessment question")
    response = json.loads(response_path.read_text())
    admitted = admit_answer(pending, response)
    _append(
        work / f"formula-map/{_JOURNAL_NAME}",
        {"schema_version": 1, "event": "assessment_answer_recorded", "answer": admitted},
        entries,
    )
    return {
        "status": "answer_recorded",
        "claim_id": admitted["claim_id"],
        "verdict": admitted["verdict"],
        "answered": len(replayed),
        "remaining": len(packets) - len(replayed),
    }


def status(work: Path) -> dict[str, object]:
    work = work.resolve()
    entries, packets, replayed = _replay(work)
    pending = replayed[-1].get("_pending") if replayed and "_pending" in replayed[-1] else None
    answers = replayed[:-1] if pending is not None else replayed
    counts = {verdict: 0 for verdict in ("confirmed", "contradicted", "unresolved")}
    for answer_value in answers:
        counts[str(answer_value["verdict"])] += 1
    return {
        "status": (
            "assessment_interview_complete"
            if len(answers) == len(packets) and pending is None
            else "assessment_interview_active"
        ),
        "claim_count": len(packets),
        "answered": len(answers),
        "remaining": len(packets) - len(answers),
        "pending_question_id": pending.get("question_id") if isinstance(pending, dict) else None,
        "verdict_counts": counts,
        "journal_entries": len(entries),
        "journal_tail_sha256": entries[-1]["entry_sha256"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("start", "next", "status"):
        command = subparsers.add_parser(name)
        command.add_argument("--work", type=Path, required=True)
    answer_parser = subparsers.add_parser("answer")
    answer_parser.add_argument("--work", type=Path, required=True)
    answer_parser.add_argument("--response", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "start":
            result = start(args.work)
        elif args.command == "next":
            result = next_question(args.work)
        elif args.command == "answer":
            result = answer(args.work, args.response)
        else:
            result = status(args.work)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "refused", "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
