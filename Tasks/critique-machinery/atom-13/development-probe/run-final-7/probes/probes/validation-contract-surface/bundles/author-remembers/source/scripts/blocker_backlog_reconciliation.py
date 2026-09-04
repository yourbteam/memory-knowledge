#!/usr/bin/env python3
"""Audit active blockers and validate an explicitly approved resolution manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

try:
    from scripts import work_memory
except ImportError:
    import work_memory  # type: ignore


SCHEMA_VERSION = 1
SEQUENCE_ID = "blocker-backlog-reconciliation"
ACTIVE_STATUSES = {"open", "fixed-awaiting-verification", "verified"}
DISPOSITIONS = {
    "remediate",
    "verify",
    "close",
    "supersede",
    "non-gap",
    "external-wait",
    "retain-investigation",
}
ACTIVE_DISPOSITIONS = {
    "remediate", "verify", "external-wait", "retain-investigation",
}
TERMINAL_DISPOSITIONS = {"close", "supersede", "non-gap"}
PRIORITIES = {"critical", "high", "medium", "low"}
ROUTES = {
    "remediate": "prototype-driven-implementation",
    "verify": "same-path-verification",
    "external-wait": "external-dependency",
    "retain-investigation": "investigation",
}
FACT_FIELDS = {
    "blocker_id",
    "status",
    "subject_id",
    "lineage_id",
    "step_id",
    "surface",
    "symptom",
    "evidence",
    "impact",
    "boundary",
    "opened_at_utc",
    "occurrence_id",
    "originating_run_id",
    "originating_run_terminal",
    "correction_ids",
    "closure_verification_event_id",
}


class ReconciliationError(RuntimeError):
    pass


def _sha(value: Any) -> str:
    return hashlib.sha256(work_memory.canonical_bytes(value)).hexdigest()


def _active_projection(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    runs: dict[str, bool] = {}
    blockers: dict[str, dict[str, Any]] = {}
    corrections: dict[str, list[dict[str, Any]]] = {}
    verifications: dict[str, dict[str, Any]] = {}

    for event in events:
        kind = event["event_type"]
        if kind == "run_started":
            runs[event["run_id"]] = False
        elif kind in {"run_closed", "run_abandoned"}:
            runs[event["run_id"]] = True
        elif kind in {"blocker_opened", "pre_run_blocker_opened"}:
            blockers[event["blocker_id"]] = {
                "blocker_id": event["blocker_id"],
                "status": "open",
                "subject_id": event["subject_id"],
                "lineage_id": event.get("lineage_id", event["subject_id"]),
                "step_id": event["step_id"],
                "surface": event["surface"],
                "symptom": event["symptom"],
                "evidence": event["evidence"],
                "impact": event.get("impact", ""),
                "boundary": event.get("boundary", ""),
                "opened_at_utc": event["recorded_at_utc"],
                "occurrence_id": event["occurrence_id"],
                "originating_run_id": event.get("run_id"),
                "originating_run_terminal": False,
                "correction_ids": [],
                "closure_verification_event_id": None,
            }
        elif kind == "blocker_recurred" and event["blocker_id"] in blockers:
            row = blockers[event["blocker_id"]]
            row.update(
                status="open",
                evidence=event["evidence"],
                occurrence_id=event["occurrence_id"],
                originating_run_id=event["run_id"],
                closure_verification_event_id=None,
            )
        elif kind in {"correction_recorded", "pre_run_correction_recorded"}:
            corrections.setdefault(event["blocker_id"], []).append(event)
        elif kind in {"verification_recorded", "pre_run_verification_recorded"}:
            verifications[event["event_id"]] = event
        elif kind in {
            "blocker_transitioned", "pre_run_blocker_transitioned",
        } and event["blocker_id"] in blockers:
            row = blockers[event["blocker_id"]]
            row["status"] = event["to_status"]
            if event.get("verification_event_id"):
                row["closure_verification_event_id"] = event["verification_event_id"]

    for blocker_id, row in blockers.items():
        run_id = row["originating_run_id"]
        row["originating_run_terminal"] = bool(
            run_id is not None and runs.get(run_id, False)
        )
        occurrence_id = row["occurrence_id"]
        current_corrections = [
            item for item in corrections.get(blocker_id, [])
            if item.get("occurrence_id") == occurrence_id
        ]
        row["correction_ids"] = sorted(
            item["correction_id"] for item in current_corrections
        )
        if (
            row["status"] == "fixed-awaiting-verification"
            and row["closure_verification_event_id"] is None
        ):
            correction_ids = set(row["correction_ids"])
            eligible = [
                event for event in verifications.values()
                if event.get("outcome") == "passed"
                and event.get("quality") in {"same-path", "same-command"}
                and blocker_id in event.get("blocker_ids", [event.get("blocker_id")])
                and correction_ids.intersection(
                    event.get("correction_ids", [event.get("correction_id")])
                )
            ]
            if eligible:
                row["closure_verification_event_id"] = sorted(
                    eligible, key=lambda item: item["recorded_at_utc"],
                )[-1]["event_id"]

    return [
        blockers[blocker_id]
        for blocker_id in sorted(blockers)
        if blockers[blocker_id]["status"] in ACTIVE_STATUSES
    ]


def _suggest(row: dict[str, Any]) -> tuple[str, str]:
    if row["status"] == "verified":
        return "close", "The blocker is verified and needs its terminal close transition."
    if (
        row["status"] == "fixed-awaiting-verification"
        and row["closure_verification_event_id"]
    ):
        return "close", "Passed same-path evidence exists; verify and close the blocker."
    if row["status"] == "fixed-awaiting-verification":
        return "verify", "The correction exists but still needs same-path verification."
    return "remediate", "The blocker remains open and needs a grounded root-fix lane."


def audit(root: Path) -> dict[str, Any]:
    events, ledger_hash = work_memory.load_ledger(
        root / work_memory.LEDGER_RELATIVE_PATH,
    )
    projection = _active_projection(events)
    candidates: list[dict[str, Any]] = []
    for facts in projection:
        suggested, reason = _suggest(facts)
        candidates.append({
            **facts,
            "suggested_disposition": suggested,
            "suggestion_reason": reason,
            "disposition": "pending",
            "decision_reason": None,
            "priority": None,
            "resolution_owner": None,
            "route": None,
            "next_action": None,
            "terminal_evidence": None,
        })
    facts = [{key: row[key] for key in sorted(FACT_FIELDS)} for row in projection]
    return {
        "schema_version": SCHEMA_VERSION,
        "sequence_id": SEQUENCE_ID,
        "created_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "snapshot": {
            "source_ledger_hash": ledger_hash,
            "active_projection_hash": _sha(facts),
            "active_blocker_ids": [row["blocker_id"] for row in projection],
        },
        "approval": {
            "approved": False,
            "approved_by": None,
            "approved_at_utc": None,
        },
        "candidates": candidates,
    }


def _facts(row: dict[str, Any]) -> dict[str, Any]:
    return {key: row.get(key) for key in sorted(FACT_FIELDS)}


def _ledger_path(root: Path) -> Path:
    return root / work_memory.LEDGER_RELATIVE_PATH


def validate_manifest(
    path: Path, root: Path, *, require_approval: bool = True,
) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReconciliationError("invalid-manifest-json") from exc
    if (
        payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("sequence_id") != SEQUENCE_ID
        or not isinstance(payload.get("candidates"), list)
    ):
        raise ReconciliationError("invalid-manifest-schema")

    current = audit(root)
    snapshot = payload.get("snapshot", {})
    if (
        snapshot.get("active_blocker_ids")
        != current["snapshot"]["active_blocker_ids"]
        or snapshot.get("active_projection_hash")
        != current["snapshot"]["active_projection_hash"]
    ):
        raise ReconciliationError("active-blocker-projection-drift")
    current_rows = {
        row["blocker_id"]: _facts(row) for row in current["candidates"]
    }
    rows = payload["candidates"]
    if [row.get("blocker_id") for row in rows] != snapshot["active_blocker_ids"]:
        raise ReconciliationError("manifest-blocker-order-mismatch")
    if any(_facts(row) != current_rows.get(row.get("blocker_id")) for row in rows):
        raise ReconciliationError("manifest-blocker-facts-drift")

    approval = payload.get("approval", {})
    if require_approval and (
        approval.get("approved") is not True
        or not approval.get("approved_by")
        or not approval.get("approved_at_utc")
    ):
        raise ReconciliationError("manifest-not-approved")

    for row in rows:
        blocker_id = row["blocker_id"]
        disposition = row.get("disposition")
        if disposition not in DISPOSITIONS:
            raise ReconciliationError(f"invalid-or-pending-disposition:{blocker_id}")
        if not isinstance(row.get("decision_reason"), str) or not row["decision_reason"].strip():
            raise ReconciliationError(f"decision-reason-required:{blocker_id}")
        if disposition in ACTIVE_DISPOSITIONS:
            if row.get("priority") not in PRIORITIES:
                raise ReconciliationError(f"priority-required:{blocker_id}")
            for field in ("resolution_owner", "next_action"):
                if not isinstance(row.get(field), str) or not row[field].strip():
                    raise ReconciliationError(f"{field}-required:{blocker_id}")
            if row.get("route") != ROUTES[disposition]:
                raise ReconciliationError(f"invalid-resolution-route:{blocker_id}")
        else:
            if not isinstance(row.get("terminal_evidence"), str) or not row["terminal_evidence"].strip():
                raise ReconciliationError(f"terminal-evidence-required:{blocker_id}")
            if disposition == "close":
                if row["status"] not in {"fixed-awaiting-verification", "verified"}:
                    raise ReconciliationError(f"close-status-not-eligible:{blocker_id}")
                if not row.get("closure_verification_event_id"):
                    raise ReconciliationError(f"close-verification-required:{blocker_id}")
            elif disposition == "non-gap":
                if row["status"] != "open":
                    raise ReconciliationError(
                        f"non-gap-status-not-eligible:{blocker_id}"
                    )
                if not row.get("closure_verification_event_id"):
                    raise ReconciliationError(
                        f"non-gap-verification-required:{blocker_id}"
                    )
            elif row["status"] != "open":
                raise ReconciliationError(
                    f"{disposition}-status-not-eligible:{blocker_id}"
                )
    return payload


def cmd_audit(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    output = Path(args.output).resolve()
    payload = audit(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    counts: dict[str, int] = {}
    for row in payload["candidates"]:
        key = row["suggested_disposition"]
        counts[key] = counts.get(key, 0) + 1
    return {
        "ok": True,
        "manifest": str(output),
        "candidate_count": len(payload["candidates"]),
        "suggested_counts": counts,
    }


def cmd_validate(args: argparse.Namespace) -> dict[str, Any]:
    payload = validate_manifest(
        Path(args.manifest).resolve(), Path(args.root).resolve(),
    )
    return {
        "ok": True,
        "candidate_count": len(payload["candidates"]),
        "manifest_hash": _sha(payload),
    }


def _active_reconciliation_run(
    events: list[dict[str, Any]], run_id: str,
) -> None:
    start = next((
        event for event in events
        if event["event_type"] == "run_started" and event["run_id"] == run_id
    ), None)
    if start is None:
        raise ReconciliationError("reconciliation-run-not-found")
    if start["subject_id"] != SEQUENCE_ID:
        raise ReconciliationError("reconciliation-run-subject-mismatch")
    if any(
        event["event_type"] in {"run_closed", "run_abandoned"}
        and event.get("run_id") == run_id
        for event in events
    ):
        raise ReconciliationError("reconciliation-run-terminal")


def _transition_events(
    payload: dict[str, Any], run_id: str,
) -> list[dict[str, Any]]:
    transitions: list[dict[str, Any]] = []
    for row in payload["candidates"]:
        disposition = row["disposition"]
        if disposition == "close":
            verification_id = row["closure_verification_event_id"]
            if row["status"] == "fixed-awaiting-verification":
                transitions.append(work_memory._event(
                    "blocker_transitioned",
                    run_id=run_id,
                    blocker_id=row["blocker_id"],
                    from_status="fixed-awaiting-verification",
                    to_status="verified",
                    verification_event_id=verification_id,
                    reconciliation_basis_event_id=verification_id,
                ))
            transitions.append(work_memory._event(
                "blocker_transitioned",
                run_id=run_id,
                blocker_id=row["blocker_id"],
                from_status="verified",
                to_status="closed",
                verification_event_id=verification_id,
                reconciliation_basis_event_id=verification_id,
                remaining_work="none",
            ))
        elif disposition == "supersede":
            transitions.append(work_memory._event(
                "blocker_transitioned",
                run_id=run_id,
                blocker_id=row["blocker_id"],
                from_status="open",
                to_status="superseded",
                supersession_evidence=row["terminal_evidence"],
            ))
        elif disposition == "non-gap":
            transitions.append(work_memory._event(
                "blocker_transitioned",
                run_id=run_id,
                blocker_id=row["blocker_id"],
                from_status="open",
                to_status="non-gap",
                verification_event_id=row["closure_verification_event_id"],
                non_gap_evidence=row["terminal_evidence"],
            ))
    return transitions


def _safe_index(root: Path, raw: str) -> Path:
    path = Path(raw)
    target = (path if path.is_absolute() else root / path).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ReconciliationError("active-index-outside-repository") from exc
    return target


def _render_active_index(payload: dict[str, Any], manifest_hash: str) -> str:
    active = [
        row for row in payload["candidates"]
        if row["disposition"] in ACTIVE_DISPOSITIONS
    ]
    lines = [
        "# Active Blocker Resolution Queue",
        "",
        f"Manifest-SHA256: `{manifest_hash}`",
        "",
        (
            "Terminal decisions are omitted. The canonical event ledger and "
            "`BLOCKERS.md` retain complete history."
        ),
        "",
        "| blocker | priority | disposition | owner | route | next action | symptom |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in active:
        values = [
            row["blocker_id"],
            row["priority"],
            row["disposition"],
            row["resolution_owner"],
            row["route"],
            row["next_action"],
            row["symptom"],
        ]
        escaped = [str(value).replace("|", "\\|").replace("\n", " ") for value in values]
        lines.append("| " + " | ".join(f"`{value}`" for value in escaped) + " |")
    return "\n".join(lines).rstrip() + "\n"


def cmd_execute(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    manifest = Path(args.manifest).resolve()
    payload = validate_manifest(manifest, root)
    events, ledger_hash = work_memory.load_ledger(_ledger_path(root))
    _active_reconciliation_run(events, args.run_id)
    transitions = _transition_events(payload, args.run_id)
    if transitions:
        work_memory.transact({
            "schema_version": 1,
            "expected_ledger_hash": ledger_hash,
            "events": transitions,
        })
    manifest_hash = _sha(payload)
    active_index = _safe_index(root, args.active_index)
    active_index.parent.mkdir(parents=True, exist_ok=True)
    work_memory._atomic_write(
        active_index,
        _render_active_index(payload, manifest_hash).encode("utf-8"),
    )
    counts: dict[str, int] = {}
    for row in payload["candidates"]:
        counts[row["disposition"]] = counts.get(row["disposition"], 0) + 1
    return {
        "ok": True,
        "manifest_hash": manifest_hash,
        "transition_count": len(transitions),
        "active_count": sum(
            count for disposition, count in counts.items()
            if disposition in ACTIVE_DISPOSITIONS
        ),
        "disposition_counts": counts,
        "active_index": str(active_index),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    subparsers = parser.add_subparsers(dest="command", required=True)
    audit_parser = subparsers.add_parser("audit")
    audit_parser.add_argument("--output", required=True)
    audit_parser.set_defaults(func=cmd_audit)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--manifest", required=True)
    validate_parser.set_defaults(func=cmd_validate)
    execute_parser = subparsers.add_parser("execute")
    execute_parser.add_argument("--manifest", required=True)
    execute_parser.add_argument("--run-id", required=True)
    execute_parser.add_argument("--active-index", required=True)
    execute_parser.set_defaults(func=cmd_execute)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if not values:
        try:
            from scripts import sequence_intake_launch
        except ModuleNotFoundError:
            import sequence_intake_launch  # type: ignore
        return sequence_intake_launch.main_for_sequence(SEQUENCE_ID, [])
    args = build_parser().parse_args(values)
    try:
        result = args.func(args)
    except (ReconciliationError, work_memory.WorkMemoryError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 3
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
