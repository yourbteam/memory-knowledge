#!/usr/bin/env python3
"""Create and verify exact evidence obligations for every assessment unit."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

CONTRACT = 1
ROLES = (
    (
        "criterion",
        "What evidence establishes what should be true for this unit?",
    ),
    (
        "observation",
        "What evidence establishes what is actually true for this unit?",
    ),
    (
        "context",
        "What evidence establishes that the criterion and observation are comparable?",
    ),
)


class AssessmentObligationsError(RuntimeError):
    """Raised when obligation coverage or immutable evidence is invalid."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as error:
        raise AssessmentObligationsError(
            f"{label} is unavailable or invalid JSON: {error}"
        ) from error
    if not isinstance(value, dict):
        raise AssessmentObligationsError(f"{label} must contain one object")
    return value, raw


def _units(value: dict[str, Any]) -> list[dict[str, Any]]:
    if (
        value.get("artifact_type") != "info-intake-assessment-units"
        or value.get("status") != "units-ready"
    ):
        raise AssessmentObligationsError("assessment units type or status is invalid")
    rows = value.get("units")
    if not isinstance(rows, list) or not rows:
        raise AssessmentObligationsError(
            "assessment units must contain one non-empty units list"
        )
    if value.get("unit_count") != len(rows):
        raise AssessmentObligationsError("assessment unit count changed")
    seen: set[str] = set()
    expected_sequence = 1
    for row in rows:
        unit_id = row.get("id") if isinstance(row, dict) else None
        sequence = row.get("sequence") if isinstance(row, dict) else None
        if not isinstance(unit_id, str) or not unit_id or unit_id in seen:
            raise AssessmentObligationsError(
                f"assessment unit identity received {unit_id!r}; provide unique non-empty ids"
            )
        if sequence != expected_sequence:
            raise AssessmentObligationsError(
                f"assessment unit {unit_id!r} sequence received {sequence!r}; expected {expected_sequence}"
            )
        seen.add(unit_id)
        expected_sequence += 1
    return rows


def _obligations(unit_id: str) -> list[dict[str, object]]:
    return [
        {
            "id": f"{unit_id}:{role}",
            "role": role,
            "required": True,
            "question": question,
            "status": "unfulfilled",
            "evidence_refs": [],
        }
        for role, question in ROLES
    ]


def compile_obligations(units_path: Path, output_path: Path) -> dict[str, object]:
    units_value, units_raw = _load(units_path, "assessment units")
    units = _units(units_value)
    result: dict[str, object] = {
        "schema_version": CONTRACT,
        "artifact_type": "info-intake-assessment-obligations",
        "status": "obligations-ready",
        "units_source": {
            "path": str(units_path.resolve()),
            "sha256": _digest(units_raw),
            "artifact_sha256": units_value.get("artifact_sha256"),
        },
        "unit_count": len(units),
        "obligation_count": len(units) * len(ROLES),
        "units": [
            {
                "sequence": unit["sequence"],
                "unit_id": unit["id"],
                "label": unit.get("label"),
                "subject": unit.get("subject"),
                "obligations": _obligations(unit["id"]),
            }
            for unit in units
        ],
    }
    result["artifact_sha256"] = _digest(_canonical(result))
    payload = json.dumps(result, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    if output_path.exists():
        if output_path.read_bytes() != payload:
            raise AssessmentObligationsError(
                "assessment obligations output already exists with different bytes"
            )
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(payload)
    return result


def verify(path: Path) -> dict[str, object]:
    value, _raw = _load(path, "assessment obligations")
    if set(value) != {
        "schema_version",
        "artifact_type",
        "status",
        "units_source",
        "unit_count",
        "obligation_count",
        "units",
        "artifact_sha256",
    }:
        raise AssessmentObligationsError(
            "assessment obligations artifact fields changed"
        )
    if (
        value.get("schema_version") != CONTRACT
        or value.get("artifact_type") != "info-intake-assessment-obligations"
        or value.get("status") != "obligations-ready"
    ):
        raise AssessmentObligationsError(
            "assessment obligations type, version, or status is invalid"
        )
    claimed = value.get("artifact_sha256")
    body = {key: item for key, item in value.items() if key != "artifact_sha256"}
    if claimed != _digest(_canonical(body)):
        raise AssessmentObligationsError(
            "assessment obligations artifact digest changed"
        )
    source = value.get("units_source")
    if not isinstance(source, dict) or set(source) != {
        "path",
        "sha256",
        "artifact_sha256",
    }:
        raise AssessmentObligationsError("assessment units source reference is invalid")
    source_path = Path(str(source["path"]))
    source_value, source_raw = _load(source_path, "assessment units source")
    if _digest(source_raw) != source["sha256"]:
        raise AssessmentObligationsError("assessment units source changed")
    if source_value.get("artifact_sha256") != source["artifact_sha256"]:
        raise AssessmentObligationsError(
            "assessment units artifact identity changed"
        )
    source_units = _units(source_value)
    rows = value.get("units")
    if not isinstance(rows, list) or value.get("unit_count") != len(rows):
        raise AssessmentObligationsError("assessment obligation unit count changed")
    if len(rows) != len(source_units):
        raise AssessmentObligationsError(
            "assessment obligations no longer cover every source unit"
        )
    if value.get("obligation_count") != len(rows) * len(ROLES):
        raise AssessmentObligationsError("assessment obligation count changed")
    for source_unit, row in zip(source_units, rows, strict=True):
        expected = {
            "sequence": source_unit["sequence"],
            "unit_id": source_unit["id"],
            "label": source_unit.get("label"),
            "subject": source_unit.get("subject"),
            "obligations": _obligations(source_unit["id"]),
        }
        if row != expected:
            raise AssessmentObligationsError(
                f"assessment obligations for unit {source_unit['id']!r} changed; restore the exact criterion, observation, and context roles"
            )
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    compile_parser = commands.add_parser("compile")
    compile_parser.add_argument("--units", type=Path, required=True)
    compile_parser.add_argument("--output", type=Path, required=True)
    check = commands.add_parser("verify")
    check.add_argument("artifact", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "compile":
            result = compile_obligations(args.units, args.output)
        else:
            result = verify(args.artifact)
    except AssessmentObligationsError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
