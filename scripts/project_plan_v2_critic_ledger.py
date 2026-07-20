#!/usr/bin/env python3
"""Project one finalized Planner v2 critic output into a verification ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode()


def digest(value: Any) -> str:
    payload = value if isinstance(value, bytes) else canonical_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def load_object(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular non-symlink file")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def project(ledger_path: Path, critic_path: Path, output_path: Path) -> None:
    ledger = load_object(ledger_path, "verification ledger")
    critic = load_object(critic_path, "critic output")
    plan = ledger["plan_verification"]
    inventory = next(
        item for item in plan["inventories"]
        if item["inventory_sha256"] == plan["inventory_sha256"]
    )
    dispositions = {item["finding_id"]: item for item in critic["dispositions"]}
    finding_map: dict[str, dict[str, Any]] = {}
    ledger_findings = []
    for finding in critic["findings"]:
        core = {
            "id": finding["id"],
            "classification": dispositions[finding["id"]]["decision"],
            "obligation_ids": finding["obligation_ids"],
            "iteration_first_seen": critic["verification_iteration"],
        }
        projected = {**core, "fingerprint": digest(core), "status": "open"}
        finding_map[finding["id"]] = projected
        ledger_findings.append(projected)

    approval_by_obligation = {
        item["obligation_id"]: item for item in critic["assessment_approvals"]
    }
    pending = []
    snapshot_approvals = []
    for assessment in critic["obligation_assessments"]:
        snapshots = []
        for snapshot in assessment["finding_snapshots"]:
            finding = finding_map[snapshot["id"]]
            snapshots.append({
                "id": finding["id"],
                "fingerprint": finding["fingerprint"],
                "classification": finding["classification"],
                "obligation_ids": finding["obligation_ids"],
                "iteration_first_seen": finding["iteration_first_seen"],
            })
        projection = {
            "iteration": assessment["iteration"],
            "obligation_id": assessment["obligation_id"],
            "binding_sha256": assessment["binding_sha256"],
            "status": assessment["status"],
            "evidence": assessment["evidence"],
            "finding_snapshots": snapshots,
            "blocked_boundary": assessment["blocked_boundary"],
        }
        projection["assessment_fingerprint"] = digest(projection)
        source_approval = approval_by_obligation[assessment["obligation_id"]]
        approval = {
            **source_approval,
            "assessment_fingerprint": projection["assessment_fingerprint"],
        }
        pending.append((projection, approval))
        snapshot_approvals.append(approval)

    attempt_id = critic["attempt_id"]
    snapshot_relative = f".verify-plan/critic-outputs/{attempt_id}.json"
    snapshot = {
        "schema_version": 1,
        "attempt_id": attempt_id,
        "inventory_approval": critic["inventory_approval"],
        "assessment_approvals": sorted(snapshot_approvals, key=digest),
        "coverage_exclusion_approvals": critic["coverage_exclusion_approvals"],
    }
    snapshot_bytes = canonical_bytes(snapshot)
    snapshot_path = ledger_path.parent / snapshot_relative
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_bytes(snapshot_bytes)
    snapshot_sha = digest(snapshot_bytes)

    def approval_ref(approval: dict[str, Any]) -> dict[str, Any]:
        return {
            "critic_attempt_id": attempt_id,
            "critic_snapshot_path": snapshot_relative,
            "critic_snapshot_sha256": snapshot_sha,
            "approval_sha256": digest(approval),
        }

    assignment = {
        "iteration": critic["verification_iteration"],
        "inventory_sha256": plan["inventory_sha256"],
        "assigned_obligation_ids": critic["assigned_obligation_ids"],
    }
    assignment["assignment_sha256"] = digest(assignment)
    inventory["completeness_approval"] = critic["inventory_approval"]
    inventory["completeness_approval_ref"] = approval_ref(
        critic["inventory_approval"],
    )
    plan["assignments"] = sorted(
        [
            item for item in plan["assignments"]
            if item["iteration"] != critic["verification_iteration"]
        ] + [assignment],
        key=lambda item: item["iteration"],
    )
    current_assessments = [
        {**assessment, "approval": approval, "approval_ref": approval_ref(approval)}
        for assessment, approval in pending
    ]
    plan["obligation_assessments"] = sorted(
        [
            item for item in plan["obligation_assessments"]
            if item["iteration"] != critic["verification_iteration"]
        ] + current_assessments,
        key=lambda item: (item["iteration"], item["obligation_id"]),
    )
    current_output = {
        "attempt_id": attempt_id,
        "snapshot_path": snapshot_relative,
        "output_sha256": snapshot_sha,
    }
    plan["critic_outputs"] = sorted(
        [
            item for item in plan["critic_outputs"]
            if item["attempt_id"] != attempt_id
        ] + [current_output],
        key=lambda item: item["attempt_id"],
    )
    assessment_status = {
        assessment["obligation_id"]: assessment["status"]
        for assessment, _approval in pending
    }
    exclusions = {
        item["coverage_id"]: item["approved_status"]
        for item in critic["coverage_exclusion_approvals"]
    }
    inventory_approved = critic["inventory_approval"]["decision"] == "APPROVED"
    for coverage in ledger["coverage_queue"]:
        if coverage["id"] in exclusions:
            coverage["status"] = exclusions[coverage["id"]]
            continue
        owned = [
            obligation["id"] for obligation in inventory["obligations"]
            if obligation["coverage_id"] == coverage["id"]
        ]
        coverage["status"] = (
            "checked"
            if inventory_approved
            and owned
            and all(assessment_status.get(item) == "SUPPORTED" for item in owned)
            else "unverified"
        )
    ledger["iteration"] = critic["verification_iteration"]
    ledger["findings"] = sorted(ledger_findings, key=lambda item: item["id"])
    output_path.write_bytes(canonical_bytes(ledger))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--critic-output", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    project(args.ledger, args.critic_output, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
