#!/usr/bin/env python3
"""Publish the terminal code-grounded formula map and unresolved questions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from formula_operator_question_plan import admit_plan
from formula_terminal_replay import replay
from reporting_v3_column_index import _canonical, _read_object, _sha, _validate_formula_ledger


def publish(work: Path, question_plan_path: Path) -> dict[str, object]:
    work = work.resolve()
    formula_root = work / "formula-map"
    packets_path = formula_root / "assessment-packets.json"
    context_path = formula_root / "assessment-shared-context.json"
    journal_path = formula_root / "assessment-interview-v2-ledger.jsonl"
    packets_bytes = packets_path.read_bytes()
    context_bytes = context_path.read_bytes()
    journal_bytes = journal_path.read_bytes()
    packets_value = _read_object(packets_path, "assessment packets")
    context_value = _read_object(context_path, "assessment shared context")
    entries = _validate_formula_ledger(formula_root / "ledger.jsonl")
    if (
        len(entries) < 6
        or entries[4].get("assessment_packets_sha256") != _sha(packets_bytes)
        or entries[5].get("shared_context_sha256") != _sha(context_bytes)
    ):
        raise ValueError("terminal formula inputs differ from formula-map ledger evidence")
    packets = packets_value.get("packets")
    shared = context_value.get("shared_code_evidence")
    if not isinstance(packets, list) or not isinstance(shared, list):
        raise ValueError("terminal formula inputs have invalid item lists")
    answers, assessment_entries = replay(
        packets, shared, journal_path, _sha(packets_bytes), _sha(context_bytes)
    )
    plan_value = json.loads(question_plan_path.read_text())
    plan = admit_plan(answers, plan_value)
    claims = []
    for packet, answer in zip(packets, answers):
        assert isinstance(packet, dict)
        claim = packet.get("claim")
        assert isinstance(claim, dict)
        claims.append(
            {
                "claim_id": answer["claim_id"],
                "statement": claim.get("statement"),
                "packet_sha256": answer["packet_sha256"],
                "verdict": answer["verdict"],
                "reason": answer["reason"],
                "evidence_pointers": answer["evidence_pointers"],
            }
        )
    counts = {
        verdict: sum(claim["verdict"] == verdict for claim in claims)
        for verdict in ("confirmed", "contradicted", "unresolved")
    }
    terminal = {
        "schema_version": 1,
        "status": "terminal",
        "intake_id": packets_value.get("intake_id"),
        "assessment_packets_sha256": _sha(packets_bytes),
        "shared_context_sha256": _sha(context_bytes),
        "assessment_journal_sha256": _sha(journal_bytes),
        "assessment_journal_tail_sha256": assessment_entries[-1]["entry_sha256"],
        "claim_count": len(claims),
        "verdict_counts": counts,
        "claims": claims,
    }
    questions = {
        "schema_version": 1,
        "status": "operator_input_required" if plan["questions"] else "complete",
        "unresolved_claim_count": counts["unresolved"],
        "question_count": len(plan["questions"]),
        "questions": plan["questions"],
    }
    terminal_bytes = json.dumps(terminal, indent=2, sort_keys=True).encode() + b"\n"
    questions_bytes = json.dumps(questions, indent=2, sort_keys=True).encode() + b"\n"
    terminal_path = formula_root / "terminal-formula-map.json"
    questions_path = formula_root / "operator-questions.json"
    for path, data, label in [
        (terminal_path, terminal_bytes, "terminal formula map"),
        (questions_path, questions_bytes, "operator questions"),
    ]:
        if path.exists():
            if path.read_bytes() != data:
                raise ValueError(f"{label} exists with different immutable bytes")
        else:
            with path.open("xb") as handle:
                handle.write(data)
    event = {
        "schema_version": 1,
        "sequence": 7,
        "event": "terminal_formula_map_recorded",
        "previous_entry_sha256": entries[5]["entry_sha256"],
        "intake_id": packets_value.get("intake_id"),
        "terminal_map_path": str(terminal_path.relative_to(work)),
        "terminal_map_sha256": _sha(terminal_bytes),
        "operator_questions_path": str(questions_path.relative_to(work)),
        "operator_questions_sha256": _sha(questions_bytes),
        "claim_count": len(claims),
        "verdict_counts": counts,
        "operator_question_count": len(plan["questions"]),
    }
    event["entry_sha256"] = _sha(_canonical(event))
    event_bytes = _canonical(event) + b"\n"
    ledger_path = formula_root / "ledger.jsonl"
    if len(entries) == 6:
        with ledger_path.open("ab") as handle:
            handle.write(event_bytes)
    elif len(entries) != 7 or _canonical(entries[6]) + b"\n" != event_bytes:
        raise ValueError("formula-map ledger contains a different terminal event")
    return {
        "status": "terminal_formula_map_recorded",
        "claim_count": len(claims),
        "verdict_counts": counts,
        "operator_question_count": len(plan["questions"]),
        "terminal_map": str(terminal_path),
        "operator_questions": str(questions_path),
        "ledger_tail_sha256": event["entry_sha256"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--question-plan", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = publish(args.work, args.question_plan)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "refused", "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
