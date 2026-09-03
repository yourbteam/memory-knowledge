#!/usr/bin/env python3
"""Canonical blocker operations backed by the work-memory event ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import uuid
from pathlib import Path
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


ATOM_BINDING_FIELDS = (
    "atomic_step_id", "atom_request_sha256", "atom_run_id", "atom_attempt",
)


def atom_identity(atom_run: Path) -> dict[str, Any]:
    run = atom_run.resolve()
    if run.is_symlink() or not run.is_dir():
        raise work_memory.WorkMemoryError("atom-run-not-found", 3)
    request_path = run / "inputs" / "atom-request.json"
    ledger_path = run / "ledger.jsonl"
    try:
        request_bytes = request_path.read_bytes()
        request = json.loads(request_bytes)
        lines = ledger_path.read_bytes().splitlines(keepends=True)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise work_memory.WorkMemoryError("invalid-atom-run", 3) from exc
    if not lines or not isinstance(request, dict):
        raise work_memory.WorkMemoryError("invalid-atom-run", 3)
    records = []
    previous = None
    for sequence, line in enumerate(lines, start=1):
        try:
            record = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise work_memory.WorkMemoryError("invalid-atom-run-ledger", 3) from exc
        if (
            not isinstance(record, dict)
            or record.get("sequence") != sequence
            or record.get("previous_event_sha256") != previous
            or not isinstance(record.get("payload"), dict)
        ):
            raise work_memory.WorkMemoryError("invalid-atom-run-ledger", 3)
        records.append(record)
        previous = hashlib.sha256(line).hexdigest()
    first = records[0]
    request_sha256 = hashlib.sha256(request_bytes).hexdigest()
    if (
        first.get("event") != "atom-started"
        or first["payload"].get("atomic_step_id") != request.get("atomic_step_id")
        or first["payload"].get("request_sha256") != request_sha256
    ):
        raise work_memory.WorkMemoryError("atom-run-identity-mismatch", 3)
    experiments = [item for item in records if item.get("event") == "experiment-recorded"]
    attempt = len(experiments)
    if not experiments or experiments[-1]["payload"].get("verdict") != "passed":
        attempt += 1
    return {
        "atomic_step_id": work_memory.require_id(request["atomic_step_id"], "atomic-step-id"),
        "atom_request_sha256": request_sha256,
        "atom_run_id": hashlib.sha256(lines[0]).hexdigest(),
        "atom_attempt": max(1, attempt),
        "atom_run_path": str(run),
        "repository_root": first["payload"].get("repository_root"),
    }


def _atom_binding(atom_run: str | None) -> dict[str, Any]:
    if atom_run is None:
        return {}
    identity = atom_identity(Path(atom_run))
    return {field: identity[field] for field in ATOM_BINDING_FIELDS}


def atom_closeout(atom_run: Path) -> dict[str, Any]:
    identity = atom_identity(atom_run)
    repository_root = identity["repository_root"]
    if not isinstance(repository_root, str) or not Path(repository_root).is_absolute():
        raise work_memory.WorkMemoryError("atom-repository-root-unavailable", 3)
    work_memory.configure_root(Path(repository_root))
    events, ledger_sha256 = work_memory.load_ledger()
    linked: dict[tuple[str, str], dict[str, Any]] = {}
    current: dict[str, str] = {}
    for index, event in enumerate(events, start=1):
        kind = event["event_type"]
        blocker_id = event.get("blocker_id")
        if kind in {"blocker_opened", "pre_run_blocker_opened", "blocker_recurred"}:
            occurrence_id = event["occurrence_id"]
            current[blocker_id] = occurrence_id
            if all(event.get(field) == identity[field] for field in ATOM_BINDING_FIELDS[:3]):
                linked[(blocker_id, occurrence_id)] = {
                    "blocker_id": blocker_id,
                    "occurrence_id": occurrence_id,
                    "atom_attempt": event["atom_attempt"],
                    "status": "open",
                    "classification": "deliverable-blocker",
                    "opened_event_id": event["event_id"],
                    "opened_sequence": index,
                }
            continue
        if blocker_id is None or blocker_id not in current:
            continue
        key = (blocker_id, current[blocker_id])
        row = linked.get(key)
        if row is None:
            continue
        if kind in {"blocker_transitioned", "pre_run_blocker_transitioned"}:
            row["status"] = event["to_status"]
            row["transition_event_id"] = event["event_id"]
            for field in (
                "remaining_work", "non_gap_evidence", "supersession_evidence",
                "superseded_by_blocker_id", "superseded_by_occurrence_id",
            ):
                if field in event:
                    row[field] = event[field]
        elif kind == "blocker_assigned_downstream":
            row["classification"] = event["classification"]
            row["downstream_owner"] = event["downstream_owner"]
            row["assignment_event_id"] = event["event_id"]

    dispositions = []
    blocking = []
    for key, row in sorted(linked.items(), key=lambda item: item[1]["opened_sequence"]):
        status = row["status"]
        reason = None
        disposition = None
        if status == "closed" and row.get("remaining_work") == "none":
            disposition = "closed"
        elif status == "non-gap" and isinstance(row.get("non_gap_evidence"), str) and row["non_gap_evidence"].strip():
            disposition = "non-gap"
        elif status == "open" and (
            row.get("classification") == "incidental-system-defect"
            and isinstance(row.get("downstream_owner"), str)
            and row["downstream_owner"].strip()
        ):
            disposition = "assigned-downstream"
        elif status == "superseded":
            successor = (
                row.get("superseded_by_blocker_id"),
                row.get("superseded_by_occurrence_id"),
            )
            if successor in linked and successor != key:
                disposition = "superseded"
            else:
                reason = "supersession-successor-invalid"
        elif status in {"open", "fixed-awaiting-verification", "verified"}:
            reason = f"deliverable-blocker-{status}"
        else:
            reason = "undispositioned-blocker"
        result = {**row, "disposition": disposition, "blocking_reason": reason}
        dispositions.append(result)
        if reason is not None:
            blocking.append({
                "blocker_id": row["blocker_id"],
                "occurrence_id": row["occurrence_id"],
                "reason": reason,
            })
    return {
        "schema_version": 1,
        "atomic_step_id": identity["atomic_step_id"],
        "atom_request_sha256": identity["atom_request_sha256"],
        "atom_run_id": identity["atom_run_id"],
        "work_memory_ledger_sha256": ledger_sha256,
        "clear": not blocking,
        "linked_occurrence_count": len(dispositions),
        "blocking_occurrence_count": len(blocking),
        "blocking_occurrences": blocking,
        "dispositions": dispositions,
    }


def cmd_atom_closeout(args: argparse.Namespace) -> dict[str, Any]:
    return atom_closeout(Path(args.atom_run))


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
    atom_fields = _atom_binding(getattr(args, "atom_run", None))
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
            **atom_fields,
        )
    elif previous_status == "closed":
        event = work_memory._event(
            "blocker_recurred", args.event_id, run_id=args.run_id, blocker_id=blocker_id,
            occurrence_id=occurrence_id, previous_status="closed", status="open",
            evidence=args.evidence,
            **atom_fields,
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
    if status not in {"open", "fixed-awaiting-verification"}:
        raise work_memory.WorkMemoryError("pre-run-blocker-not-open", 3)
    declared_artifacts = args.changed_artifact or []
    declared_environment = args.changed_environment_artifact or []
    artifacts, hashes = work_memory._artifact_hashes(declared_artifacts)
    environment_artifacts, environment_hashes = (
        work_memory._environment_artifact_hashes(declared_environment)
    )
    if not artifacts and not environment_artifacts:
        raise work_memory.WorkMemoryError(
            "pre-run-correction-declares-no-artifact", 2,
        )
    environment_fields = (
        {
            "environment_artifacts": environment_artifacts,
            "environment_artifact_hashes": environment_hashes,
        }
        if environment_artifacts else {}
    )
    correction_id = args.correction_id or str(uuid.uuid4())
    superseded_ids = {
        item["supersedes_correction_id"] for item in events
        if item["event_type"] == "pre_run_correction_recorded"
        and "supersedes_correction_id" in item
    }
    active = [
        item for item in events
        if item["event_type"] == "pre_run_correction_recorded"
        and item["blocker_id"] == args.blocker_id
        and item["occurrence_id"] == args.occurrence_id
        and item["correction_id"] not in superseded_ids
    ]
    if status == "fixed-awaiting-verification" and len(active) != 1:
        raise work_memory.WorkMemoryError(
            "pre-run-active-correction-ambiguous", 3,
        )
    supersedes_id = (
        active[0]["correction_id"]
        if status == "fixed-awaiting-verification" else None
    )
    correction_fields = {}
    if supersedes_id is not None:
        correction_fields["supersedes_correction_id"] = supersedes_id
    correction = work_memory._event(
        "pre_run_correction_recorded", args.event_id,
        task_id=args.task_id, ownership_event_id=args.ownership_event_id,
        blocker_id=args.blocker_id, occurrence_id=args.occurrence_id,
        correction_id=correction_id, step_id=opened["step_id"],
        changed_artifacts=artifacts, changed_artifact_hashes=hashes,
        solution=args.solution,
        reusable_behavior_changed=args.reusable_behavior_changed == "yes",
        **environment_fields, **correction_fields,
    )
    transition = None
    requested_events = [correction]
    if status == "open":
        transition = work_memory._event(
            "pre_run_blocker_transitioned", args.transition_event_id,
            task_id=args.task_id,
            ownership_event_id=args.ownership_event_id,
            blocker_id=args.blocker_id,
            occurrence_id=args.occurrence_id,
            from_status="open",
            to_status="fixed-awaiting-verification",
        )
        requested_events.append(transition)
    result = work_memory.transact({
        "schema_version": 1, "expected_ledger_hash": None,
        "events": requested_events,
    })
    return {
        **result, "blocker_id": args.blocker_id, "occurrence_id": args.occurrence_id,
        "correction_id": correction_id, "event_id": correction["event_id"],
        "transition_event_id": (
            transition["event_id"] if transition is not None else None
        ),
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
    superseded_ids = {
        item["supersedes_correction_id"] for item in events
        if item["event_type"] == "pre_run_correction_recorded"
        and "supersedes_correction_id" in item
    }
    if correction["correction_id"] in superseded_ids:
        raise work_memory.WorkMemoryError(
            "pre-run-correction-superseded", 3,
        )
    current_artifacts, current_hashes = work_memory._rehash_recorded_artifacts(
        correction["changed_artifacts"],
    )
    current_environment, current_environment_hashes = (
        work_memory._rehash_recorded_environment_artifacts(
            correction.get("environment_artifacts", []),
        )
    )
    if (
        current_artifacts != correction["changed_artifacts"]
        or current_hashes != correction["changed_artifact_hashes"]
        or current_environment != correction.get("environment_artifacts", [])
        or current_environment_hashes
        != correction.get("environment_artifact_hashes", [])
    ):
        raise work_memory.WorkMemoryError(
            "pre-run-correction-artifact-hash-mismatch", 3,
        )
    verification = work_memory._event(
        "pre_run_verification_recorded", args.event_id,
        task_id=args.task_id, ownership_event_id=args.ownership_event_id,
        blocker_id=args.blocker_id, occurrence_id=args.occurrence_id,
        correction_id=args.correction_id, verification_command=args.command,
        outcome="passed", quality="same-command", evidence=args.evidence,
        changed_artifact_hashes=correction["changed_artifact_hashes"],
        **(
            {
                "environment_artifact_hashes": correction[
                    "environment_artifact_hashes"
                ],
            }
            if correction.get("environment_artifact_hashes") else {}
        ),
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
    if args.to_status in {"verified", "closed", "non-gap"}:
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
        superseded_by_blocker_id = getattr(args, "superseded_by_blocker_id", None)
        superseded_by_occurrence_id = getattr(args, "superseded_by_occurrence_id", None)
        if not superseded_by_blocker_id or not superseded_by_occurrence_id:
            raise work_memory.WorkMemoryError("superseding-blocker-occurrence-required", 2)
        current_occurrences: dict[str, dict[str, Any]] = {}
        for item in events:
            if item["event_type"] in {"blocker_opened", "blocker_recurred"}:
                current_occurrences[item["blocker_id"]] = item
        successor = current_occurrences.get(superseded_by_blocker_id)
        source = current_occurrences.get(args.blocker_id)
        if (
            successor is None or source is None
            or successor["occurrence_id"] != superseded_by_occurrence_id
            or successor["blocker_id"] == source["blocker_id"]
            or any(source.get(field) != successor.get(field) for field in ATOM_BINDING_FIELDS[:3])
        ):
            raise work_memory.WorkMemoryError("invalid-superseding-blocker-occurrence", 3)
        extra["superseded_by_blocker_id"] = superseded_by_blocker_id
        extra["superseded_by_occurrence_id"] = superseded_by_occurrence_id
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


def cmd_assign_downstream(args: argparse.Namespace) -> dict[str, Any]:
    events, _ = work_memory.load_ledger()
    _run(events, args.run_id)
    occurrence_id = None
    for item in events:
        if (
            item["event_type"] in {"blocker_opened", "blocker_recurred"}
            and item["blocker_id"] == args.blocker_id
        ):
            occurrence_id = item["occurrence_id"]
    if occurrence_id is None:
        raise work_memory.WorkMemoryError("blocker-not-found", 3)
    event = work_memory._event(
        "blocker_assigned_downstream", args.event_id,
        run_id=args.run_id, blocker_id=args.blocker_id,
        occurrence_id=occurrence_id,
        classification="incidental-system-defect",
        downstream_owner=args.downstream_owner,
        evidence=args.evidence,
    )
    result = work_memory.transact({
        "schema_version": 1, "expected_ledger_hash": None, "events": [event],
    })
    return {
        **result, "event_id": event["event_id"],
        "blocker_id": args.blocker_id,
        "classification": event["classification"],
        "downstream_owner": args.downstream_owner,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    opened = sub.add_parser("open")
    for flag in ("step-id", "surface", "error-signature", "symptom", "evidence",
                 "impact", "boundary"):
        opened.add_argument(f"--{flag}", required=True)
    opened.add_argument("--run-id"); opened.add_argument("--subject-id")
    opened.add_argument("--task-id"); opened.add_argument("--ownership-event-id")
    opened.add_argument("--occurrence-id"); opened.add_argument("--event-id")
    opened.add_argument("--atom-run")
    opened.set_defaults(func=cmd_open)
    pre_correct = sub.add_parser("pre-run-correct")
    for flag in ("task-id", "ownership-event-id", "blocker-id", "occurrence-id",
                 "solution"):
        pre_correct.add_argument(f"--{flag}", required=True)
    pre_correct.add_argument("--reusable-behavior-changed", required=True, choices=["yes", "no"])
    pre_correct.add_argument("--changed-artifact", action="append")
    pre_correct.add_argument("--changed-environment-artifact", action="append")
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
    transition.add_argument("--superseded-by-blocker-id")
    transition.add_argument("--superseded-by-occurrence-id")
    transition.set_defaults(func=cmd_transition)
    recover = sub.add_parser("recover")
    recover.add_argument("--run-id", required=True)
    recover.add_argument("--blocker-id", required=True)
    recover.add_argument("--reopen-evidence", required=True)
    recover.add_argument("--event-id")
    recover.set_defaults(func=cmd_recover)
    assign = sub.add_parser("assign-downstream")
    assign.add_argument("--run-id", required=True)
    assign.add_argument("--blocker-id", required=True)
    assign.add_argument("--downstream-owner", required=True)
    assign.add_argument("--evidence", required=True)
    assign.add_argument("--event-id")
    assign.set_defaults(func=cmd_assign_downstream)
    closeout = sub.add_parser("atom-closeout")
    closeout.add_argument("--atom-run", required=True)
    closeout.set_defaults(func=cmd_atom_closeout)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        if args.root is not None:
            work_memory.configure_root(args.root)
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
