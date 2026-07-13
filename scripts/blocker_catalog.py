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


def cmd_open(args: argparse.Namespace) -> dict[str, Any]:
    events, _ = work_memory.load_ledger()
    run = _run(events, args.run_id)
    if run["subject_id"] != args.subject_id:
        raise work_memory.WorkMemoryError("subject-run-mismatch", 3)
    digest = fingerprint(args.surface, run["lineage_id"], args.step_id, args.error_signature)
    blocker_id = "blk-" + digest[:24]
    occurrence_id = args.occurrence_id or str(uuid.uuid4())
    previous_status = None
    for event in events:
        if event["event_type"] == "blocker_opened" and event["blocker_id"] == blocker_id:
            previous_status = "open"
        elif event["event_type"] == "blocker_transitioned" and event["blocker_id"] == blocker_id:
            previous_status = event["to_status"]
        elif event["event_type"] == "blocker_recurred" and event["blocker_id"] == blocker_id:
            previous_status = "open"
    if previous_status is None:
        event = work_memory._event(
            "blocker_opened", args.event_id, run_id=args.run_id, blocker_id=blocker_id,
            occurrence_id=occurrence_id, fingerprint=digest, subject_id=run["subject_id"],
            lineage_id=run["lineage_id"], step_id=args.step_id, surface=args.surface,
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    opened = sub.add_parser("open")
    for flag in ("run-id", "subject-id", "step-id", "surface", "error-signature",
                 "symptom", "evidence", "impact", "boundary"):
        opened.add_argument(f"--{flag}", required=True)
    opened.add_argument("--occurrence-id"); opened.add_argument("--event-id")
    opened.set_defaults(func=cmd_open)
    transition = sub.add_parser("transition")
    transition.add_argument("--run-id", required=True); transition.add_argument("--blocker-id", required=True)
    transition.add_argument("--to-status", required=True, choices=["open", "fixed-awaiting-verification", "verified", "closed", "superseded", "non-gap"])
    transition.add_argument("--verification-event-id"); transition.add_argument("--remaining-work", default="none")
    transition.add_argument("--supersession-evidence"); transition.add_argument("--non-gap-evidence"); transition.add_argument("--event-id")
    transition.add_argument("--reopen-evidence")
    transition.set_defaults(func=cmd_transition)
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
