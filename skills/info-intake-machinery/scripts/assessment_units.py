#!/usr/bin/env python3
"""Compile complete purpose-relevant assessment units from source-bound plans."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

CONTRACT = 1


class AssessmentUnitsError(RuntimeError):
    """Raised when assessment-unit identity or coverage is invalid."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as error:
        raise AssessmentUnitsError(f"{label} is unavailable or invalid JSON: {error}") from error
    if not isinstance(value, dict):
        raise AssessmentUnitsError(f"{label} must contain one object")
    return value, raw


def _ref(path: Path, raw: bytes, value: dict[str, Any]) -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "sha256": _digest(raw),
        "artifact_sha256": value.get("artifact_sha256"),
    }


def relationship_target_plan(packets_path: Path) -> dict[str, object]:
    packets, raw = _load(packets_path, "assessment packets")
    rows = packets.get("packets")
    if not isinstance(rows, list) or not rows:
        raise AssessmentUnitsError("assessment packets must contain one non-empty packets list")
    grouped: dict[str, dict[str, object]] = {}
    order: list[str] = []
    for position, packet in enumerate(rows, start=1):
        if not isinstance(packet, dict) or not isinstance(packet.get("claim"), dict):
            raise AssessmentUnitsError(f"assessment packet {position} claim is invalid")
        claim = packet["claim"]
        target = claim.get("target")
        claim_id = claim.get("id")
        packet_sha = packet.get("packet_sha256")
        if not isinstance(target, dict) or not all(
            isinstance(target.get(field), str) and target[field]
            for field in ("element_id", "element_sha256", "content", "kind")
        ):
            raise AssessmentUnitsError(
                f"assessment packet {position} target received {target!r}; provide exact element identity, digest, content, and kind"
            )
        if not isinstance(claim_id, str) or not claim_id or not isinstance(packet_sha, str) or len(packet_sha) != 64:
            raise AssessmentUnitsError(f"assessment packet {position} claim identity or packet digest is invalid")
        identity = target["element_id"]
        if identity not in grouped:
            order.append(identity)
            grouped[identity] = {
                "id": f"unit-{len(order):06d}",
                "label": target["content"],
                "source_claim_ids": [],
                "subject": {
                    "identity": identity,
                    "kind": target["kind"],
                    "evidence_sha256": target["element_sha256"],
                },
            }
        unit = grouped[identity]
        if unit["subject"]["evidence_sha256"] != target["element_sha256"]:
            raise AssessmentUnitsError(
                f"target {identity!r} digest received {target['element_sha256']!r}; keep one immutable subject identity"
            )
        unit["source_claim_ids"].append(claim_id)
    return {
        "schema_version": CONTRACT,
        "basis": "relationship-target",
        "source": {"path": str(packets_path.resolve()), "sha256": _digest(raw)},
        "units": [grouped[identity] for identity in order],
    }


def _plan_units(plan: dict[str, Any], declared: list[str]) -> list[dict[str, object]]:
    if set(plan) - {"schema_version", "basis", "source", "units"}:
        raise AssessmentUnitsError("assessment unit plan contains unsupported fields")
    if plan.get("schema_version") != CONTRACT or not isinstance(plan.get("basis"), str) or not plan["basis"]:
        raise AssessmentUnitsError("assessment unit plan schema_version or basis is invalid")
    rows = plan.get("units")
    if not isinstance(rows, list) or not rows:
        raise AssessmentUnitsError("assessment unit plan units must be one non-empty list")
    errors: list[str] = []
    counts: Counter[str] = Counter()
    seen_ids: set[str] = set()
    normalized: list[dict[str, object]] = []
    for position, row in enumerate(rows, start=1):
        if not isinstance(row, dict) or set(row) != {"id", "label", "source_claim_ids", "subject"}:
            errors.append(f"unit {position} received {row!r}; provide exactly id, label, source_claim_ids, and subject")
            continue
        unit_id = row["id"]
        label = row["label"]
        refs = row["source_claim_ids"]
        subject = row["subject"]
        if not isinstance(unit_id, str) or not unit_id or unit_id in seen_ids:
            errors.append(f"unit {position} id received {unit_id!r}; provide one unique non-empty id")
        else:
            seen_ids.add(unit_id)
        if not isinstance(label, str) or not label.strip():
            errors.append(f"unit {unit_id!r} label received {label!r}; provide one non-empty label")
        if not isinstance(refs, list) or not refs or any(not isinstance(ref, str) or not ref for ref in refs):
            errors.append(f"unit {unit_id!r} source_claim_ids received {refs!r}; provide one non-empty string list")
            continue
        if not isinstance(subject, dict) or set(subject) != {"identity", "kind", "evidence_sha256"} or not all(
            isinstance(subject[field], str) and subject[field] for field in subject
        ):
            errors.append(f"unit {unit_id!r} subject received {subject!r}; provide exact identity, kind, and evidence_sha256")
            continue
        counts.update(refs)
        normalized.append({
            "id": unit_id,
            "label": label.strip(),
            "source_claim_ids": list(refs),
            "subject": dict(subject),
        })
    declared_set = set(declared)
    missing = [claim_id for claim_id in declared if counts[claim_id] == 0]
    duplicate = [claim_id for claim_id in declared if counts[claim_id] > 1]
    unknown = sorted(claim_id for claim_id in counts if claim_id not in declared_set)
    if missing:
        errors.append(f"source coverage missing {missing!r}; include every declared claim exactly once")
    if duplicate:
        errors.append(f"source coverage duplicated {duplicate!r}; bind each declared claim once")
    if unknown:
        errors.append(f"source coverage unknown {unknown!r}; use only declared claim ids")
    if errors:
        raise AssessmentUnitsError("; ".join(errors))
    order = {claim_id: index for index, claim_id in enumerate(declared)}
    return sorted(normalized, key=lambda row: min(order[claim_id] for claim_id in row["source_claim_ids"]))


def compile_units(
    intake_path: Path,
    charter_path: Path,
    packets_path: Path,
    plan_path: Path,
    output_path: Path,
) -> dict[str, object]:
    intake, intake_raw = _load(intake_path, "terminal intake")
    charter, charter_raw = _load(charter_path, "assessment charter")
    packets, packets_raw = _load(packets_path, "assessment packets")
    plan, plan_raw = _load(plan_path, "assessment unit plan")
    if intake.get("status") != "terminal" or not isinstance(intake.get("claims"), list) or not intake["claims"]:
        raise AssessmentUnitsError("terminal intake must contain one non-empty confirmed claims list")
    if charter.get("status") != "charter-ready" or charter.get("intake", {}).get("sha256") != _digest(intake_raw):
        raise AssessmentUnitsError("assessment charter is not bound to the terminal intake")
    declared: list[str] = []
    claim_by_id: dict[str, dict[str, Any]] = {}
    for position, claim in enumerate(intake["claims"], start=1):
        claim_id = claim.get("claim_id") if isinstance(claim, dict) else None
        if not isinstance(claim_id, str) or not claim_id or claim_id in claim_by_id:
            raise AssessmentUnitsError(f"terminal claim {position} identity is invalid or duplicated")
        if claim.get("verdict") != "confirmed":
            raise AssessmentUnitsError(f"terminal claim {claim_id!r} must be confirmed before assessment")
        declared.append(claim_id)
        claim_by_id[claim_id] = claim
    packet_rows = packets.get("packets")
    if not isinstance(packet_rows, list):
        raise AssessmentUnitsError("assessment packets list is invalid")
    packet_by_claim = {
        row.get("claim", {}).get("id"): row
        for row in packet_rows
        if isinstance(row, dict) and isinstance(row.get("claim"), dict)
    }
    for claim_id in declared:
        packet = packet_by_claim.get(claim_id)
        if not isinstance(packet, dict) or packet.get("packet_sha256") != claim_by_id[claim_id].get("packet_sha256"):
            raise AssessmentUnitsError(f"source claim {claim_id!r} packet evidence is missing or changed")
    units = _plan_units(plan, declared)
    result: dict[str, object] = {
        "schema_version": CONTRACT,
        "artifact_type": "info-intake-assessment-units",
        "status": "units-ready",
        "intake": _ref(intake_path, intake_raw, intake),
        "charter": _ref(charter_path, charter_raw, charter),
        "packets": {"path": str(packets_path.resolve()), "sha256": _digest(packets_raw)},
        "plan": {"path": str(plan_path.resolve()), "sha256": _digest(plan_raw)},
        "basis": plan["basis"],
        "claim_count": len(declared),
        "unit_count": len(units),
        "units": [
            {
                "sequence": sequence,
                **unit,
                "source_claims": [
                    {
                        "claim_id": claim_id,
                        "statement": claim_by_id[claim_id]["statement"],
                        "packet_sha256": claim_by_id[claim_id]["packet_sha256"],
                    }
                    for claim_id in unit["source_claim_ids"]
                ],
            }
            for sequence, unit in enumerate(units, start=1)
        ],
    }
    result["artifact_sha256"] = _digest(_canonical(result))
    payload = json.dumps(result, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    if output_path.exists():
        if output_path.read_bytes() != payload:
            raise AssessmentUnitsError("assessment units output already exists with different bytes")
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(payload)
    return result


def verify(path: Path) -> dict[str, object]:
    value, _raw = _load(path, "assessment units")
    if value.get("artifact_type") != "info-intake-assessment-units" or value.get("status") != "units-ready":
        raise AssessmentUnitsError("assessment units type or status is invalid")
    claimed = value.pop("artifact_sha256", None)
    actual = _digest(_canonical(value))
    value["artifact_sha256"] = claimed
    if claimed != actual:
        raise AssessmentUnitsError("assessment units artifact digest changed")
    for label in ("intake", "charter", "packets", "plan"):
        ref = value.get(label)
        if not isinstance(ref, dict) or not isinstance(ref.get("path"), str) or not isinstance(ref.get("sha256"), str):
            raise AssessmentUnitsError(f"assessment units {label} reference is invalid")
        source = Path(ref["path"])
        if not source.is_file() or _digest(source.read_bytes()) != ref["sha256"]:
            raise AssessmentUnitsError(f"assessment units {label} source changed")
    if value.get("unit_count") != len(value.get("units", [])):
        raise AssessmentUnitsError("assessment units count changed")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan-relationship-targets")
    plan.add_argument("--packets", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    compile_parser = commands.add_parser("compile")
    compile_parser.add_argument("--intake", type=Path, required=True)
    compile_parser.add_argument("--charter", type=Path, required=True)
    compile_parser.add_argument("--packets", type=Path, required=True)
    compile_parser.add_argument("--plan", type=Path, required=True)
    compile_parser.add_argument("--output", type=Path, required=True)
    check = commands.add_parser("verify")
    check.add_argument("artifact", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "plan-relationship-targets":
            result = relationship_target_plan(args.packets)
            payload = json.dumps(result, indent=2, sort_keys=True).encode("utf-8") + b"\n"
            if args.output.exists() and args.output.read_bytes() != payload:
                raise AssessmentUnitsError("assessment unit plan output already exists with different bytes")
            if not args.output.exists():
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_bytes(payload)
        elif args.command == "compile":
            result = compile_units(args.intake, args.charter, args.packets, args.plan, args.output)
        else:
            result = verify(args.artifact)
    except AssessmentUnitsError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps({
        "status": result.get("status", "plan-ready"),
        "unit_count": len(result.get("units", [])),
        "artifact_sha256": result.get("artifact_sha256"),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
