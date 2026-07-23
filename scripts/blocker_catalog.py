#!/usr/bin/env python3
"""Canonical blocker operations backed by the work-memory event ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import uuid
from typing import Any, Sequence

try:
    from scripts import work_memory
except ImportError:  # direct script execution
    import work_memory  # type: ignore


def normalize_error_signature(value: str) -> str:
    text = value.lower()
    text = re.sub(r"\b\d{4}-\d{2}-\d{2}t\d{2}:\d{2}:\d{2}(?:\.\d+)?z?\b", "<timestamp>", text)
    text = re.sub(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", "<uuid>", text)
    text = re.sub(r"\b[0-9a-f]{32,}\b", "<hash>", text)
    text = re.sub(r"(?:/private)?/tmp/[^\s:]+", "<tmp-path>", text)
    text = re.sub(r"\b(?:attempt|retry|line)\s*[#:=]?\s*\d+\b", lambda m: re.sub(r"\d+", "<n>", m.group()), text)
    return " ".join(text.split())


def fingerprint(surface: str, lineage_id: str, step_id: str, signature: str) -> str:
    payload = {"surface": surface, "lineage_id": lineage_id, "step_id": step_id,
               "error_signature": normalize_error_signature(signature)}
    return hashlib.sha256(work_memory.canonical_bytes(payload)).hexdigest()


def _run(events: list[dict[str, Any]], run_id: str) -> dict[str, Any]:
    event = next((item for item in events if item["event_type"] == "run_started" and item["run_id"] == run_id), None)
    if event is None:
        raise work_memory.WorkMemoryError("run-not-found", 3)
    return event


def _pre_run_identity(
    events: list[dict[str, Any]], task_id: str, ownership_event_id: str,
) -> dict[str, str]:
    ownership = next((
        item for item in events
        if item.get("event_id") == ownership_event_id
        and item.get("event_type") in work_memory.OWNERSHIP_EVENT_TYPES
    ), None)
    if ownership is None:
        raise work_memory.WorkMemoryError("ownership-event-not-found", 3)
    if ownership.get("task_id") != task_id:
        raise work_memory.WorkMemoryError("ownership-event-task-mismatch", 3)
    tasks, _ = work_memory._ownership_snapshot(events)
    current = tasks.get(task_id)
    if current is None or current["ownership_event_id"] != ownership_event_id:
        raise work_memory.WorkMemoryError("ownership-event-not-current", 3)
    return {"subject_id": task_id, "lineage_id": task_id}


def cmd_open(args: argparse.Namespace) -> dict[str, Any]:
    events, _ = work_memory.load_ledger()
    run_route = args.run_id is not None or args.subject_id is not None
    pre_run_route = args.task_id is not None or args.ownership_event_id is not None
    if run_route == pre_run_route:
        raise work_memory.WorkMemoryError("exactly-one-blocker-authority-required", 2)
    if run_route:
        if args.run_id is None or args.subject_id is None:
            raise work_memory.WorkMemoryError("incomplete-run-blocker-authority", 2)
        run = _run(events, args.run_id)
        if run["subject_id"] != args.subject_id:
            raise work_memory.WorkMemoryError("subject-run-mismatch", 3)
        identity = {"subject_id": run["subject_id"], "lineage_id": run["lineage_id"]}
    else:
        if args.task_id is None or args.ownership_event_id is None:
            raise work_memory.WorkMemoryError("incomplete-pre-run-blocker-authority", 2)
        identity = _pre_run_identity(events, args.task_id, args.ownership_event_id)
    digest = fingerprint(args.surface, identity["lineage_id"], args.step_id, args.error_signature)
    blocker_id = "blk-" + digest[:24]
    occurrence_id = args.occurrence_id or str(uuid.uuid4())
    previous_status = None
    for event in events:
        if event["event_type"] in {"blocker_opened", "pre_run_blocker_opened"} and event["blocker_id"] == blocker_id:
            previous_status = "open"
        elif event["event_type"] in {"blocker_transitioned", "pre_run_blocker_transitioned"} and event["blocker_id"] == blocker_id:
            previous_status = event["to_status"]
        elif event["event_type"] == "blocker_recurred" and event["blocker_id"] == blocker_id:
            previous_status = "open"
    if previous_status is None:
        authority = (
            {"run_id": args.run_id}
            if run_route else {
                "task_id": args.task_id,
                "ownership_event_id": args.ownership_event_id,
            }
        )
        event = work_memory._event(
            "blocker_opened" if run_route else "pre_run_blocker_opened",
            args.event_id, **authority, blocker_id=blocker_id,
            occurrence_id=occurrence_id, fingerprint=digest,
            subject_id=identity["subject_id"], lineage_id=identity["lineage_id"],
            step_id=args.step_id, surface=args.surface,
            symptom=args.symptom, evidence=args.evidence, impact=args.impact,
            boundary=args.boundary, status="open",
        )
    elif previous_status == "closed":
        event = work_memory._event(
            "blocker_recurred", args.event_id, run_id=args.run_id, blocker_id=blocker_id,
            occurrence_id=occurrence_id, previous_status="closed", status="open",
            evidence=args.evidence,
        )
    else:
        raise work_memory.WorkMemoryError("blocker-already-active", 3)
    result = work_memory.transact({"schema_version": 1, "expected_ledger_hash": None, "events": [event]})
    return {**result, "fingerprint": digest, "blocker_id": blocker_id,
            "occurrence_id": occurrence_id, "event_id": event["event_id"],
            "event_type": event["event_type"]}


def _pre_run_context(
    events: list[dict[str, Any]], task_id: str, ownership_event_id: str,
    blocker_id: str, occurrence_id: str,
) -> tuple[dict[str, Any], str]:
    _pre_run_identity(events, task_id, ownership_event_id)
    opened = next((
        item for item in events
        if item["event_type"] == "pre_run_blocker_opened"
        and item["blocker_id"] == blocker_id
    ), None)
    if (
        opened is None or opened["task_id"] != task_id
        or opened["ownership_event_id"] != ownership_event_id
        or opened["occurrence_id"] != occurrence_id
    ):
        raise work_memory.WorkMemoryError("pre-run-blocker-context-mismatch", 3)
    status = "open"
    for item in events:
        if (
            item["event_type"] == "pre_run_blocker_transitioned"
            and item["blocker_id"] == blocker_id
        ):
            status = item["to_status"]
    return opened, status


def cmd_pre_run_correct(args: argparse.Namespace) -> dict[str, Any]:
    events, _ = work_memory.load_ledger()
    opened, status = _pre_run_context(
        events, args.task_id, args.ownership_event_id,
        args.blocker_id, args.occurrence_id,
    )
    if status != "open":
        raise work_memory.WorkMemoryError("pre-run-blocker-not-open", 3)
    artifacts, hashes = work_memory._artifact_hashes(args.changed_artifact)
    correction_id = args.correction_id or str(uuid.uuid4())
    correction = work_memory._event(
        "pre_run_correction_recorded", args.event_id,
        task_id=args.task_id, ownership_event_id=args.ownership_event_id,
        blocker_id=args.blocker_id, occurrence_id=args.occurrence_id,
        correction_id=correction_id, step_id=opened["step_id"],
        changed_artifacts=artifacts, changed_artifact_hashes=hashes,
        solution=args.solution,
        reusable_behavior_changed=args.reusable_behavior_changed == "yes",
    )
    transition = work_memory._event(
        "pre_run_blocker_transitioned", args.transition_event_id,
        task_id=args.task_id, ownership_event_id=args.ownership_event_id,
        blocker_id=args.blocker_id, occurrence_id=args.occurrence_id,
        from_status="open", to_status="fixed-awaiting-verification",
    )
    result = work_memory.transact({
        "schema_version": 1, "expected_ledger_hash": None,
        "events": [correction, transition],
    })
    return {
        **result, "blocker_id": args.blocker_id, "occurrence_id": args.occurrence_id,
        "correction_id": correction_id, "event_id": correction["event_id"],
        "transition_event_id": transition["event_id"],
        "changed_artifact_hashes": hashes,
    }


def cmd_pre_run_verify(args: argparse.Namespace) -> dict[str, Any]:
    events, _ = work_memory.load_ledger()
    _, status = _pre_run_context(
        events, args.task_id, args.ownership_event_id,
        args.blocker_id, args.occurrence_id,
    )
    if status != "fixed-awaiting-verification":
        raise work_memory.WorkMemoryError("pre-run-blocker-not-fixed", 3)
    correction = next((
        item for item in events
        if item["event_type"] == "pre_run_correction_recorded"
        and item["correction_id"] == args.correction_id
        and item["blocker_id"] == args.blocker_id
    ), None)
    if correction is None:
        raise work_memory.WorkMemoryError("pre-run-correction-not-found", 3)
    verification = work_memory._event(
        "pre_run_verification_recorded", args.event_id,
        task_id=args.task_id, ownership_event_id=args.ownership_event_id,
        blocker_id=args.blocker_id, occurrence_id=args.occurrence_id,
        correction_id=args.correction_id, verification_command=args.command,
        outcome="passed", quality="same-command", evidence=args.evidence,
        changed_artifact_hashes=correction["changed_artifact_hashes"],
    )
    result = work_memory.transact({
        "schema_version": 1, "expected_ledger_hash": None, "events": [verification],
    })
    return {**result, "verification_event_id": verification["event_id"]}


def cmd_pre_run_transition(args: argparse.Namespace) -> dict[str, Any]:
    events, _ = work_memory.load_ledger()
    _, status = _pre_run_context(
        events, args.task_id, args.ownership_event_id,
        args.blocker_id, args.occurrence_id,
    )
    expected = {"verified": "fixed-awaiting-verification", "closed": "verified"}
    if status != expected[args.to_status]:
        raise work_memory.WorkMemoryError("pre-run-blocker-status-mismatch", 3)
    extra = {"verification_event_id": args.verification_event_id}
    if args.to_status == "closed":
        extra["remaining_work"] = args.remaining_work
    transition = work_memory._event(
        "pre_run_blocker_transitioned", args.event_id,
        task_id=args.task_id, ownership_event_id=args.ownership_event_id,
        blocker_id=args.blocker_id, occurrence_id=args.occurrence_id,
        from_status=status, to_status=args.to_status, **extra,
    )
    result = work_memory.transact({
        "schema_version": 1, "expected_ledger_hash": None, "events": [transition],
    })
    return {**result, "event_id": transition["event_id"], "to_status": args.to_status}


def cmd_transition(args: argparse.Namespace) -> dict[str, Any]:
    events, _ = work_memory.load_ledger()
    _run(events, args.run_id)
    status = None
    for item in events:
        if item["event_type"] == "blocker_opened" and item["blocker_id"] == args.blocker_id:
            status = "open"
        elif item["event_type"] == "blocker_recurred" and item["blocker_id"] == args.blocker_id:
            status = "open"
        elif item["event_type"] == "blocker_transitioned" and item["blocker_id"] == args.blocker_id:
            status = item["to_status"]
    if status is None:
        raise work_memory.WorkMemoryError("blocker-not-found", 3)
    extra: dict[str, Any] = {}
    if args.to_status in {"verified", "closed"}:
        if not args.verification_event_id:
            raise work_memory.WorkMemoryError("verification-event-id-required", 2)
        extra["verification_event_id"] = args.verification_event_id
    if args.to_status == "closed":
        extra["remaining_work"] = args.remaining_work
    elif args.to_status == "open":
        if not args.reopen_evidence:
            raise work_memory.WorkMemoryError("reopen-evidence-required", 2)
        extra["reopen_evidence"] = args.reopen_evidence
    elif args.to_status == "superseded":
        extra["supersession_evidence"] = args.supersession_evidence
    elif args.to_status == "non-gap":
        extra["non_gap_evidence"] = args.non_gap_evidence
    event = work_memory._event(
        "blocker_transitioned", args.event_id, run_id=args.run_id,
        blocker_id=args.blocker_id, from_status=status, to_status=args.to_status, **extra,
    )
    result = work_memory.transact({"schema_version": 1, "expected_ledger_hash": None, "events": [event]})
    return {**result, "blocker_id": args.blocker_id, "from_status": status,
            "to_status": args.to_status, "event_id": event["event_id"]}


def cmd_recover(args: argparse.Namespace) -> dict[str, Any]:
    events, _ = work_memory.load_ledger()
    _run(events, args.run_id)
    status = None
    for item in events:
        if item["event_type"] == "blocker_opened" and item["blocker_id"] == args.blocker_id:
            status = "open"
        elif item["event_type"] == "blocker_recurred" and item["blocker_id"] == args.blocker_id:
            status = "open"
        elif item["event_type"] == "blocker_transitioned" and item["blocker_id"] == args.blocker_id:
            status = item["to_status"]
    if status is None:
        raise work_memory.WorkMemoryError("blocker-not-found", 3)
    event = work_memory._event(
        "blocker_transitioned", args.event_id, run_id=args.run_id,
        blocker_id=args.blocker_id, from_status=status, to_status="open",
        recovery_evidence=args.reopen_evidence,
    )
    result = work_memory.transact(
        {"schema_version": 1, "expected_ledger_hash": None, "events": [event]}
    )
    return {
        **result,
        "event_type": event["event_type"],
        "event_id": event["event_id"],
        "run_id": args.run_id,
        "blocker_id": args.blocker_id,
        "from_status": status,
        "to_status": "open",
        "recovery_evidence": args.reopen_evidence,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    opened = sub.add_parser("open")
    for flag in ("step-id", "surface", "error-signature", "symptom", "evidence",
                 "impact", "boundary"):
        opened.add_argument(f"--{flag}", required=True)
    opened.add_argument("--run-id"); opened.add_argument("--subject-id")
    opened.add_argument("--task-id"); opened.add_argument("--ownership-event-id")
    opened.add_argument("--occurrence-id"); opened.add_argument("--event-id")
    opened.set_defaults(func=cmd_open)
    pre_correct = sub.add_parser("pre-run-correct")
    for flag in ("task-id", "ownership-event-id", "blocker-id", "occurrence-id",
                 "solution"):
        pre_correct.add_argument(f"--{flag}", required=True)
    pre_correct.add_argument("--reusable-behavior-changed", required=True, choices=["yes", "no"])
    pre_correct.add_argument("--changed-artifact", action="append", required=True)
    pre_correct.add_argument("--correction-id"); pre_correct.add_argument("--event-id")
    pre_correct.add_argument("--transition-event-id")
    pre_correct.set_defaults(func=cmd_pre_run_correct)
    pre_verify = sub.add_parser("pre-run-verify")
    for flag in ("task-id", "ownership-event-id", "blocker-id", "occurrence-id",
                 "correction-id", "command", "evidence"):
        pre_verify.add_argument(f"--{flag}", required=True)
    pre_verify.add_argument("--event-id")
    pre_verify.set_defaults(func=cmd_pre_run_verify)
    pre_transition = sub.add_parser("pre-run-transition")
    for flag in ("task-id", "ownership-event-id", "blocker-id", "occurrence-id",
                 "verification-event-id"):
        pre_transition.add_argument(f"--{flag}", required=True)
    pre_transition.add_argument("--to-status", required=True, choices=["verified", "closed"])
    pre_transition.add_argument("--remaining-work", default="none")
    pre_transition.add_argument("--event-id")
    pre_transition.set_defaults(func=cmd_pre_run_transition)
    transition = sub.add_parser("transition")
    transition.add_argument("--run-id", required=True); transition.add_argument("--blocker-id", required=True)
    transition.add_argument("--to-status", required=True, choices=["open", "fixed-awaiting-verification", "verified", "closed", "superseded", "non-gap"])
    transition.add_argument("--verification-event-id"); transition.add_argument("--remaining-work", default="none")
    transition.add_argument("--supersession-evidence"); transition.add_argument("--non-gap-evidence"); transition.add_argument("--reopen-evidence"); transition.add_argument("--event-id")
    transition.set_defaults(func=cmd_transition)
    recover = sub.add_parser("recover")
    recover.add_argument("--run-id", required=True)
    recover.add_argument("--blocker-id", required=True)
    recover.add_argument("--reopen-evidence", required=True)
    recover.add_argument("--event-id")
    recover.set_defaults(func=cmd_recover)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        print(json.dumps(args.func(args), sort_keys=True))
        return 0
    except work_memory.WorkMemoryError as exc:
        print(json.dumps({"ok": False, "error": exc.code}, sort_keys=True), file=sys.stderr)
        return exc.exit_code
    except OSError as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__}, sort_keys=True), file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
