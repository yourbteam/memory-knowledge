#!/usr/bin/env python3
"""Shared verification ledger helper for verify-* skills.

The helper intentionally validates a small common ledger contract used by
verify-analysis, verify-plan, and verify-work without forcing every skill to
share identical domain-specific fields.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VALID_KINDS = {"analysis", "plan", "work"}
VALID_COVERAGE_STATUSES = {
    "unverified",
    "checked",
    "fixed",
    "out_of_scope",
    "deferred_by_critic",
    "deferred",
    "pending",
}
ACTIONABLE_CLASSIFICATIONS = {"FIX NOW", "IMPLEMENT LATER"}
RESOLVED_STATUSES = {
    "resolved",
    "fixed",
    "dismissed",
    "acknowledged",
    "checked",
    "out_of_scope",
    "deferred_by_critic",
    "deferred",
}


def _empty_ledger(kind: str, target: str | None = None) -> dict[str, Any]:
    return {
        "kind": kind,
        "target": target or "",
        "iteration": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "coverage_queue": [],
        "findings": [],
        "iteration_log": [],
    }


def _load(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [f"ledger not found: {path}"]
    except json.JSONDecodeError as exc:
        return None, [f"ledger is not valid JSON: {exc}"]
    if not isinstance(data, dict):
        return None, ["ledger root must be an object"]
    return data, []


def _validate_common(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    kind = data.get("kind")
    if kind not in VALID_KINDS:
        errors.append(f"kind must be one of {sorted(VALID_KINDS)}")
    if "target" not in data:
        errors.append("target is required")
    if not isinstance(data.get("iteration", 0), int):
        errors.append("iteration must be an integer")

    coverage = data.get("coverage_queue")
    if not isinstance(coverage, list):
        errors.append("coverage_queue must be an array")
    else:
        seen_ids: set[str] = set()
        for idx, item in enumerate(coverage):
            prefix = f"coverage_queue[{idx}]"
            if not isinstance(item, dict):
                errors.append(f"{prefix} must be an object")
                continue
            item_id = str(item.get("id") or "").strip()
            if not item_id:
                errors.append(f"{prefix}.id is required")
            elif item_id in seen_ids:
                errors.append(f"{prefix}.id is duplicated: {item_id}")
            seen_ids.add(item_id)
            if not str(item.get("summary") or "").strip():
                errors.append(f"{prefix}.summary is required")
            if str(item.get("risk") or "").strip() not in {"high", "medium", "low"}:
                errors.append(f"{prefix}.risk must be high, medium, or low")
            if str(item.get("status") or "").strip() not in VALID_COVERAGE_STATUSES:
                errors.append(f"{prefix}.status must be one of {sorted(VALID_COVERAGE_STATUSES)}")
            evidence = item.get("evidence_to_inspect", [])
            if evidence is not None and not isinstance(evidence, list):
                errors.append(f"{prefix}.evidence_to_inspect must be an array when present")

    findings = data.get("findings")
    if not isinstance(findings, list):
        errors.append("findings must be an array")
    else:
        seen_finding_ids: set[str] = set()
        for idx, finding in enumerate(findings):
            prefix = f"findings[{idx}]"
            if not isinstance(finding, dict):
                errors.append(f"{prefix} must be an object")
                continue
            finding_id = str(finding.get("id") or "").strip()
            if not finding_id:
                errors.append(f"{prefix}.id is required")
            elif finding_id in seen_finding_ids:
                errors.append(f"{prefix}.id is duplicated: {finding_id}")
            seen_finding_ids.add(finding_id)
            if "iteration_first_seen" in finding and not isinstance(finding["iteration_first_seen"], int):
                errors.append(f"{prefix}.iteration_first_seen must be an integer")

    if not isinstance(data.get("iteration_log"), list):
        errors.append("iteration_log must be an array")
    return errors


def _can_stop_errors(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for item in data.get("coverage_queue", []):
        if not isinstance(item, dict):
            continue
        risk = str(item.get("risk") or "").strip()
        status = str(item.get("status") or "").strip()
        if risk in {"high", "medium"} and status == "unverified":
            errors.append(f"coverage item remains unverified: {item.get('id')}")

    for finding in data.get("findings", []):
        if not isinstance(finding, dict):
            continue
        classification = str(finding.get("classification") or "").strip()
        status = str(finding.get("status") or "").strip()
        if classification in ACTIONABLE_CLASSIFICATIONS and status not in RESOLVED_STATUSES:
            errors.append(f"actionable finding remains unresolved: {finding.get('id')}")
    return errors


def cmd_init(args: argparse.Namespace) -> int:
    ledger = _empty_ledger(args.kind, args.target)
    output = json.dumps(ledger, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    path = Path(args.ledger)
    data, errors = _load(path)
    if data is not None:
        errors.extend(_validate_common(data))
        if args.can_stop:
            errors.extend(_can_stop_errors(data))

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    if args.can_stop:
        print("OK: ledger can stop")
    else:
        print("OK: ledger valid")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create an empty verification ledger")
    init.add_argument("--kind", required=True, choices=sorted(VALID_KINDS))
    init.add_argument("--target", default="")
    init.add_argument("--output", "-o")
    init.set_defaults(func=cmd_init)

    check = sub.add_parser("check", help="Validate a verification ledger")
    check.add_argument("ledger")
    check.add_argument("--can-stop", action="store_true")
    check.set_defaults(func=cmd_check)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
