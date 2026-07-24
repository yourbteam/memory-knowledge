#!/usr/bin/env python3
"""Rebind a Plan Playbook verification ledger to its current controller snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def digest(value: Any) -> str:
    payload = value if isinstance(value, bytes) else canonical_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-ledger", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--source-snapshot-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    run_root = args.run_root.resolve(strict=True)
    ledger = json.loads(args.source_ledger.read_text(encoding="utf-8"))
    verification = ledger["plan_verification"]
    active = next(
        item
        for item in verification["inventories"]
        if item["inventory_sha256"] == verification["inventory_sha256"]
    )

    plan_rel = f"snapshots/plan/{args.plan_sha256}.md"
    plan_path = run_root / plan_rel
    plan_bytes = plan_path.read_bytes()
    if digest(plan_bytes) != args.plan_sha256:
        raise SystemExit("current plan snapshot hash mismatch")
    active["plan_sha256"] = args.plan_sha256
    active["plan_sections"] = [{
        "id": "PLAN-COMPLETE",
        "path": plan_rel,
        "start_line": 1,
        "end_line": len(plan_bytes.decode("utf-8").splitlines()),
        "content_sha256": args.plan_sha256,
    }]

    source_prefix = f"source-snapshots/{args.source_snapshot_id}/tree/"
    for record in active["dependencies"]:
        old_path = record["source_ref"]["path"]
        marker = "/tree/"
        if marker not in old_path:
            raise SystemExit(f"unexpected dependency path: {old_path}")
        repository_relative = old_path.split(marker, 1)[1]
        record["source_ref"]["path"] = source_prefix + repository_relative
        source_path = run_root / record["source_ref"]["path"]
        if digest(source_path.read_bytes()) != record["content_sha256"]:
            raise SystemExit(f"dependency content mismatch: {record['id']}")

    for record in active["evidence_items"]:
        evidence_path = run_root / record["source_ref"]["path"]
        if not evidence_path.is_file():
            raise SystemExit(f"missing evidence record source: {record['id']}")

    active["evidence_revision_sha256"] = digest({
        "evidence_items": active["evidence_items"],
        "dependencies": active["dependencies"],
    })

    sections = {item["id"]: item for item in active["plan_sections"]}
    evidence = {item["id"]: item for item in active["evidence_items"]}
    dependencies = {item["id"]: item for item in active["dependencies"]}
    for obligation in active["obligations"]:
        projection = {
            "id": obligation["id"],
            "coverage_id": obligation["coverage_id"],
            "claim": obligation["claim"],
            "plan_sections": [sections[item] for item in obligation["plan_section_refs"]],
            "evidence_items": [evidence[item] for item in obligation["evidence_refs"]],
            "dependencies": [dependencies[item] for item in obligation["dependency_refs"]],
        }
        obligation["binding_sha256"] = digest(projection)

    active["completeness_approval"] = None
    active["completeness_approval_ref"] = None
    inventory_projection = {
        "contract_version": 1,
        "plan_sha256": active["plan_sha256"],
        "evidence_revision_sha256": active["evidence_revision_sha256"],
        "plan_sections": active["plan_sections"],
        "evidence_items": active["evidence_items"],
        "dependencies": active["dependencies"],
        "obligations": active["obligations"],
    }
    active["inventory_sha256"] = digest(inventory_projection)

    verification["plan_sha256"] = args.plan_sha256
    verification["evidence_revision_sha256"] = active["evidence_revision_sha256"]
    verification["inventory_sha256"] = active["inventory_sha256"]
    verification["inventories"] = [active]
    verification["assignments"] = []
    verification["obligation_assessments"] = []
    verification["critic_outputs"] = []
    verification["coverage_exclusion_approvals"] = []

    ledger["active_plan_sha256"] = args.plan_sha256
    repository_root = run_root.parents[2]
    ledger["target"] = plan_path.relative_to(repository_root).as_posix()
    ledger["iteration"] = 0
    ledger["findings"] = []
    ledger["iteration_log"] = []
    for coverage in ledger["coverage_queue"]:
        coverage["status"] = "unverified"

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(ledger) + b"\n")
    print(json.dumps({
        "ok": True,
        "output": str(args.output),
        "ledger_sha256": digest(canonical_bytes(ledger)),
        "inventory_sha256": active["inventory_sha256"],
        "evidence_revision_sha256": active["evidence_revision_sha256"],
        "obligations": len(active["obligations"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
