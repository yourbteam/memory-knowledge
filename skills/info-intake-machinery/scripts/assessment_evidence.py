#!/usr/bin/env python3
"""Bind freshly verified source evidence to assessment obligations."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

CONTRACT = 1


class AssessmentEvidenceError(RuntimeError):
    """Raised when evidence identity, source bytes, or locators are invalid."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as error:
        raise AssessmentEvidenceError(
            f"{label} is unavailable or invalid JSON: {error}"
        ) from error
    if not isinstance(value, dict):
        raise AssessmentEvidenceError(f"{label} must contain one object")
    return value, raw


def _artifact_ref(path: Path, raw: bytes, value: dict[str, Any]) -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "sha256": _digest(raw),
        "artifact_sha256": value.get("artifact_sha256"),
    }


def _obligation_rows(value: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    if (
        value.get("artifact_type") != "info-intake-assessment-obligations"
        or value.get("status") != "obligations-ready"
    ):
        raise AssessmentEvidenceError("assessment obligations type or status is invalid")
    units = value.get("units")
    if not isinstance(units, list) or not units:
        raise AssessmentEvidenceError(
            "assessment obligations must contain one non-empty units list"
        )
    obligation_ids: list[str] = []
    seen: set[str] = set()
    for expected_sequence, unit in enumerate(units, start=1):
        unit_id = unit.get("unit_id") if isinstance(unit, dict) else None
        obligations = unit.get("obligations") if isinstance(unit, dict) else None
        if unit.get("sequence") != expected_sequence or not isinstance(unit_id, str):
            raise AssessmentEvidenceError(
                f"assessment obligation unit {expected_sequence} identity or order changed"
            )
        if not isinstance(obligations, list) or not obligations:
            raise AssessmentEvidenceError(
                f"assessment obligation unit {unit_id!r} has no obligations"
            )
        for obligation in obligations:
            obligation_id = obligation.get("id") if isinstance(obligation, dict) else None
            if (
                not isinstance(obligation_id, str)
                or not obligation_id
                or obligation_id in seen
            ):
                raise AssessmentEvidenceError(
                    f"assessment obligation identity received {obligation_id!r}; provide unique ids"
                )
            seen.add(obligation_id)
            obligation_ids.append(obligation_id)
    if value.get("unit_count") != len(units):
        raise AssessmentEvidenceError("assessment obligation unit count changed")
    if value.get("obligation_count") != len(obligation_ids):
        raise AssessmentEvidenceError("assessment obligation count changed")
    return units, obligation_ids


def _json_pointer(raw: bytes, pointer: object) -> object:
    if not isinstance(pointer, str) or (pointer and not pointer.startswith("/")):
        raise AssessmentEvidenceError(
            f"JSON pointer received {pointer!r}; provide an empty pointer or one beginning with /"
        )
    try:
        value: object = json.loads(raw)
        if not pointer:
            return value
        for encoded in pointer[1:].split("/"):
            token = encoded.replace("~1", "/").replace("~0", "~")
            if isinstance(value, list):
                value = value[int(token)]
            elif isinstance(value, dict):
                value = value[token]
            else:
                raise KeyError(token)
        return value
    except (json.JSONDecodeError, KeyError, IndexError, ValueError) as error:
        raise AssessmentEvidenceError(
            f"JSON pointer {pointer!r} does not resolve in the source: {error}"
        ) from error


def _line_range(raw: bytes, locator: dict[str, Any]) -> str:
    start = locator.get("start")
    end = locator.get("end")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise AssessmentEvidenceError(
            "line-range evidence source is not UTF-8 text"
        ) from error
    if (
        not isinstance(start, int)
        or isinstance(start, bool)
        or not isinstance(end, int)
        or isinstance(end, bool)
        or start < 1
        or end < start
        or end > len(lines)
    ):
        raise AssessmentEvidenceError(
            f"line range received {start!r}..{end!r}; provide a range within 1..{len(lines)}"
        )
    return "\n".join(lines[start - 1 : end])


def _resolve(raw: bytes, locator: object) -> object:
    if not isinstance(locator, dict) or not isinstance(locator.get("kind"), str):
        raise AssessmentEvidenceError(
            f"evidence locator received {locator!r}; provide one locator object"
        )
    if locator["kind"] == "json-pointer":
        if set(locator) != {"kind", "pointer"}:
            raise AssessmentEvidenceError(
                "JSON pointer locator must contain exactly kind and pointer"
            )
        return _json_pointer(raw, locator["pointer"])
    if locator["kind"] == "line-range":
        if set(locator) != {"kind", "start", "end"}:
            raise AssessmentEvidenceError(
                "line-range locator must contain exactly kind, start, and end"
            )
        return _line_range(raw, locator)
    raise AssessmentEvidenceError(
        f"evidence locator kind received {locator['kind']!r}; use json-pointer or line-range"
    )


def _admit(
    plan: dict[str, Any], obligation_ids: list[str]
) -> tuple[dict[str, list[dict[str, object]]], list[str]]:
    rows = plan.get("evidence")
    if not isinstance(rows, list):
        raise AssessmentEvidenceError("evidence plan evidence must be one list")
    known = set(obligation_ids)
    grouped: dict[str, list[dict[str, object]]] = {
        obligation_id: [] for obligation_id in obligation_ids
    }
    errors: list[str] = []
    seen_evidence: set[str] = set()
    for position, row in enumerate(rows, start=1):
        if not isinstance(row, dict) or set(row) != {
            "evidence_id",
            "obligation_id",
            "source",
            "locator",
        }:
            errors.append(
                f"evidence {position} received {row!r}; provide exactly evidence_id, obligation_id, source, and locator"
            )
            continue
        evidence_id = row["evidence_id"]
        obligation_id = row["obligation_id"]
        if (
            not isinstance(evidence_id, str)
            or not evidence_id
            or evidence_id in seen_evidence
        ):
            errors.append(
                f"evidence {position} id received {evidence_id!r}; provide one unique non-empty id"
            )
            continue
        seen_evidence.add(evidence_id)
        if obligation_id not in known:
            errors.append(
                f"evidence {evidence_id!r} obligation received {obligation_id!r}; use one declared obligation id"
            )
            continue
        source = row["source"]
        if not isinstance(source, dict) or set(source) != {"path", "sha256"}:
            errors.append(
                f"evidence {evidence_id!r} source received {source!r}; provide exact path and sha256"
            )
            continue
        path_value = source["path"]
        expected_sha = source["sha256"]
        if not isinstance(path_value, str) or not path_value or not isinstance(expected_sha, str):
            errors.append(
                f"evidence {evidence_id!r} source identity is invalid"
            )
            continue
        source_path = Path(path_value)
        try:
            source_raw = source_path.read_bytes()
        except OSError as error:
            errors.append(
                f"evidence {evidence_id!r} source is unavailable: {error}"
            )
            continue
        actual_sha = _digest(source_raw)
        if expected_sha != actual_sha:
            errors.append(
                f"evidence {evidence_id!r} source digest received {expected_sha!r}; current bytes are {actual_sha!r}"
            )
            continue
        try:
            representation = _resolve(source_raw, row["locator"])
        except AssessmentEvidenceError as error:
            errors.append(f"evidence {evidence_id!r} locator refused: {error}")
            continue
        grouped[str(obligation_id)].append(
            {
                "evidence_id": evidence_id,
                "source": {
                    "path": str(source_path.resolve()),
                    "sha256": actual_sha,
                },
                "locator": row["locator"],
                "representation": representation,
                "representation_sha256": _digest(_canonical(representation)),
            }
        )
    if errors:
        raise AssessmentEvidenceError("; ".join(errors))
    missing = [obligation_id for obligation_id in obligation_ids if not grouped[obligation_id]]
    return grouped, missing


def build(obligations_path: Path, plan_path: Path) -> dict[str, object]:
    obligations, obligations_raw = _load(
        obligations_path, "assessment obligations"
    )
    plan, plan_raw = _load(plan_path, "assessment evidence plan")
    units, obligation_ids = _obligation_rows(obligations)
    if set(plan) != {"schema_version", "obligations", "evidence"}:
        raise AssessmentEvidenceError(
            "evidence plan must contain exactly schema_version, obligations, and evidence"
        )
    if plan.get("schema_version") != CONTRACT:
        raise AssessmentEvidenceError("evidence plan schema_version is invalid")
    expected_ref = _artifact_ref(obligations_path, obligations_raw, obligations)
    if plan.get("obligations") != expected_ref:
        raise AssessmentEvidenceError(
            "evidence plan is not bound to the current assessment obligations"
        )
    grouped, unbound = _admit(plan, obligation_ids)
    output_units: list[dict[str, object]] = []
    for unit in units:
        output_obligations = []
        for obligation in unit["obligations"]:
            evidence = grouped[obligation["id"]]
            output_obligations.append(
                {
                    "id": obligation["id"],
                    "role": obligation["role"],
                    "required": obligation["required"],
                    "question": obligation["question"],
                    "status": "bound" if evidence else "unbound",
                    "evidence": evidence,
                }
            )
        output_units.append(
            {
                "sequence": unit["sequence"],
                "unit_id": unit["unit_id"],
                "label": unit["label"],
                "subject": unit["subject"],
                "obligations": output_obligations,
            }
        )
    result: dict[str, object] = {
        "schema_version": CONTRACT,
        "artifact_type": "info-intake-assessment-evidence",
        "status": "evidence-state-ready",
        "obligations_source": expected_ref,
        "plan_source": _artifact_ref(plan_path, plan_raw, plan),
        "unit_count": len(units),
        "obligation_count": len(obligation_ids),
        "bound_count": len(obligation_ids) - len(unbound),
        "unbound_count": len(unbound),
        "unbound_obligation_ids": unbound,
        "units": output_units,
    }
    result["artifact_sha256"] = _digest(_canonical(result))
    return result


def compile_evidence(
    obligations_path: Path, plan_path: Path, output_path: Path
) -> dict[str, object]:
    result = build(obligations_path, plan_path)
    payload = json.dumps(result, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    if output_path.exists():
        if output_path.read_bytes() != payload:
            raise AssessmentEvidenceError(
                "assessment evidence output already exists with different bytes"
            )
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(payload)
    return result


def relationship_packet_plan(
    obligations_path: Path,
    units_path: Path,
    packets_path: Path,
) -> dict[str, object]:
    obligations, obligations_raw = _load(
        obligations_path, "assessment obligations"
    )
    units, _units_raw = _load(units_path, "assessment units")
    packets, packets_raw = _load(packets_path, "assessment packets")
    obligation_units, _obligation_ids = _obligation_rows(obligations)
    unit_rows = units.get("units")
    packet_rows = packets.get("packets")
    if not isinstance(unit_rows, list) or not isinstance(packet_rows, list):
        raise AssessmentEvidenceError(
            "relationship packet planning requires units and packets lists"
        )
    packet_indexes: dict[str, int] = {}
    for index, packet in enumerate(packet_rows):
        claim_id = (
            packet.get("claim", {}).get("id")
            if isinstance(packet, dict) and isinstance(packet.get("claim"), dict)
            else None
        )
        if not isinstance(claim_id, str) or claim_id in packet_indexes:
            raise AssessmentEvidenceError(
                f"assessment packet {index + 1} claim identity is invalid or duplicated"
            )
        packet_indexes[claim_id] = index
    if [unit.get("id") for unit in unit_rows] != [
        unit.get("unit_id") for unit in obligation_units
    ]:
        raise AssessmentEvidenceError(
            "assessment units and obligations do not have the same ordered identities"
        )
    packet_source = {"path": str(packets_path.resolve()), "sha256": _digest(packets_raw)}
    evidence: list[dict[str, object]] = []
    for unit in unit_rows:
        refs = unit.get("source_claim_ids")
        if not isinstance(refs, list) or not refs:
            raise AssessmentEvidenceError(
                f"assessment unit {unit.get('id')!r} has no source claim ids"
            )
        for claim_sequence, claim_id in enumerate(refs, start=1):
            if claim_id not in packet_indexes:
                raise AssessmentEvidenceError(
                    f"assessment unit {unit['id']!r} claim {claim_id!r} has no packet"
                )
            packet_index = packet_indexes[claim_id]
            for role, suffix in (
                ("criterion", ""),
                ("observation", "/claim/target"),
                ("context", "/claim"),
            ):
                evidence.append(
                    {
                        "evidence_id": f"{unit['id']}:{role}:claim-{claim_sequence:03d}",
                        "obligation_id": f"{unit['id']}:{role}",
                        "source": packet_source,
                        "locator": {
                            "kind": "json-pointer",
                            "pointer": f"/packets/{packet_index}{suffix}",
                        },
                    }
                )
    return {
        "schema_version": CONTRACT,
        "obligations": _artifact_ref(
            obligations_path, obligations_raw, obligations
        ),
        "evidence": evidence,
    }


def _write_create_only(path: Path, value: object, label: str) -> None:
    payload = json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    if path.exists() and path.read_bytes() != payload:
        raise AssessmentEvidenceError(f"{label} already exists with different bytes")
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)


def verify(path: Path) -> dict[str, object]:
    value, _raw = _load(path, "assessment evidence")
    if (
        value.get("artifact_type") != "info-intake-assessment-evidence"
        or value.get("status") != "evidence-state-ready"
    ):
        raise AssessmentEvidenceError("assessment evidence type or status is invalid")
    claimed = value.get("artifact_sha256")
    body = {key: item for key, item in value.items() if key != "artifact_sha256"}
    if claimed != _digest(_canonical(body)):
        raise AssessmentEvidenceError("assessment evidence artifact digest changed")
    obligations_ref = value.get("obligations_source")
    plan_ref = value.get("plan_source")
    if not isinstance(obligations_ref, dict) or not isinstance(plan_ref, dict):
        raise AssessmentEvidenceError("assessment evidence source references are invalid")
    rebuilt = build(Path(str(obligations_ref.get("path"))), Path(str(plan_ref.get("path"))))
    if rebuilt != value:
        raise AssessmentEvidenceError(
            "assessment evidence no longer matches its obligations, plan, or source bytes"
        )
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan-relationship-packets")
    plan.add_argument("--obligations", type=Path, required=True)
    plan.add_argument("--units", type=Path, required=True)
    plan.add_argument("--packets", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    compile_parser = commands.add_parser("compile")
    compile_parser.add_argument("--obligations", type=Path, required=True)
    compile_parser.add_argument("--plan", type=Path, required=True)
    compile_parser.add_argument("--output", type=Path, required=True)
    check = commands.add_parser("verify")
    check.add_argument("artifact", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "plan-relationship-packets":
            result = relationship_packet_plan(
                args.obligations, args.units, args.packets
            )
            _write_create_only(args.output, result, "assessment evidence plan")
        elif args.command == "compile":
            result = compile_evidence(
                args.obligations, args.plan, args.output
            )
        else:
            result = verify(args.artifact)
    except AssessmentEvidenceError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
