#!/usr/bin/env python3
"""Create and verify immutable System Alignment assessment units."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

CONTRACT = 1
ARTIFACT_TYPE = "system-alignment-assessment-units"
FORBIDDEN_RESULT_FIELDS = {
    "verdict",
    "measure",
    "aligned",
    "misaligned",
    "gap_assessment",
}


class AlignmentUnitError(RuntimeError):
    """The proposed alignment units are not exactly grounded."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _document(value: object) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AlignmentUnitError(f"{label} is unavailable or invalid JSON: {error}") from None
    if type(value) is not dict:
        raise AlignmentUnitError(f"{label} must contain one JSON object")
    return value


def _contains(value: object, needle: str) -> bool:
    if value == needle:
        return True
    if type(value) is dict:
        return any(_contains(item, needle) for item in value.values())
    if type(value) is list:
        return any(_contains(item, needle) for item in value)
    return False


def _source(ref: object) -> tuple[dict[str, str], dict[str, Any]]:
    if type(ref) is not dict or set(ref) != {"path", "sha256"}:
        raise AlignmentUnitError("source_artifact must contain exact path and sha256")
    if type(ref["path"]) is not str or not ref["path"]:
        raise AlignmentUnitError("source_artifact path must be a nonempty string")
    path = Path(ref["path"])
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise AlignmentUnitError(f"source_artifact must be an absolute regular file: {path}")
    observed = _sha(path)
    if type(ref["sha256"]) is not str or observed != ref["sha256"]:
        raise AlignmentUnitError(
            f"source_artifact bytes changed: expected {ref.get('sha256')}, observed {observed}"
        )
    return {"path": str(path), "sha256": observed}, _load(path, "source_artifact")


def _nonempty(value: object, label: str) -> str:
    if type(value) is not str or not value:
        raise AlignmentUnitError(f"{label} must be a nonempty string")
    return value


def _validated_units(value: object, source: dict[str, Any]) -> list[dict[str, Any]]:
    if type(value) is not list or not value:
        raise AlignmentUnitError("units must be a nonempty list")
    unit_ids: set[str] = set()
    subject_ids: set[str] = set()
    recorded: list[dict[str, Any]] = []
    for position, unit in enumerate(value, start=1):
        if type(unit) is not dict or set(unit) != {
            "unit_id",
            "sequence",
            "label",
            "subject",
            "intent_statements",
        }:
            raise AlignmentUnitError(f"unit {position} fields changed from the exact contract")
        if FORBIDDEN_RESULT_FIELDS.intersection(unit):
            raise AlignmentUnitError(f"unit {position} cannot contain result fields")
        unit_id = _nonempty(unit["unit_id"], f"unit {position} unit_id")
        if unit_id in unit_ids:
            raise AlignmentUnitError(f"unit_id is duplicated: {unit_id}")
        unit_ids.add(unit_id)
        if unit["sequence"] != position:
            raise AlignmentUnitError(
                f"unit {unit_id} sequence must be {position}, received {unit['sequence']!r}"
            )
        _nonempty(unit["label"], f"unit {unit_id} label")
        subject = unit["subject"]
        if type(subject) is not dict or set(subject) != {
            "identity",
            "kind",
            "evidence_sha256",
        }:
            raise AlignmentUnitError(f"unit {unit_id} subject fields changed")
        for field in ("identity", "kind", "evidence_sha256"):
            _nonempty(subject[field], f"unit {unit_id} subject {field}")
        if subject["identity"] in subject_ids:
            raise AlignmentUnitError(f"subject identity is duplicated: {subject['identity']}")
        subject_ids.add(subject["identity"])
        if not _contains(source, subject["identity"]) or not _contains(
            source, subject["evidence_sha256"]
        ):
            raise AlignmentUnitError(f"unit {unit_id} subject evidence is unbound")
        statements = unit["intent_statements"]
        if type(statements) is not list or not statements:
            raise AlignmentUnitError(f"unit {unit_id} needs at least one intent statement")
        statement_ids: set[str] = set()
        for statement in statements:
            if type(statement) is not dict or set(statement) != {
                "statement_id",
                "text",
                "evidence_sha256",
            }:
                raise AlignmentUnitError(f"unit {unit_id} intent statement fields changed")
            for field in ("statement_id", "text", "evidence_sha256"):
                _nonempty(statement[field], f"unit {unit_id} intent {field}")
            if statement["statement_id"] in statement_ids:
                raise AlignmentUnitError(
                    f"unit {unit_id} statement_id is duplicated: {statement['statement_id']}"
                )
            statement_ids.add(statement["statement_id"])
            if any(
                not _contains(source, statement[field])
                for field in ("statement_id", "text", "evidence_sha256")
            ):
                raise AlignmentUnitError(
                    f"unit {unit_id} intent evidence is unbound: {statement['statement_id']}"
                )
        recorded.append(deepcopy(unit))
    return recorded


def create(spec_path: Path) -> dict[str, Any]:
    spec = _load(spec_path, "alignment unit specification")
    if set(spec) != {"schema_version", "source_artifact", "units"}:
        raise AlignmentUnitError("alignment unit specification fields changed from the exact contract")
    if spec["schema_version"] != CONTRACT:
        raise AlignmentUnitError(f"alignment unit schema_version must be {CONTRACT}")
    source_ref, source = _source(spec["source_artifact"])
    units = _validated_units(spec["units"], source)
    body: dict[str, Any] = {
        "schema_version": CONTRACT,
        "artifact_type": ARTIFACT_TYPE,
        "source_artifact": source_ref,
        "unit_count": len(units),
        "units": units,
        "status": "units-admitted",
    }
    return {**body, "artifact_sha256": _sha_bytes(_canonical(body))}


def _write_once(value: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("xb") as stream:
            stream.write(_document(value))
    except FileExistsError:
        raise AlignmentUnitError(f"alignment unit package already exists: {output}") from None


def verify(path: Path) -> dict[str, Any]:
    value = _load(path, "alignment unit package")
    if path.read_bytes() != _document(value):
        raise AlignmentUnitError("alignment unit package bytes are not canonical")
    expected = {
        "schema_version",
        "artifact_type",
        "source_artifact",
        "unit_count",
        "units",
        "status",
        "artifact_sha256",
    }
    if set(value) != expected:
        raise AlignmentUnitError("alignment unit package fields changed from the exact contract")
    if value["schema_version"] != CONTRACT or value["artifact_type"] != ARTIFACT_TYPE:
        raise AlignmentUnitError("alignment unit package identity changed")
    if value["status"] != "units-admitted":
        raise AlignmentUnitError("alignment unit package status changed")
    source_ref, source = _source(value["source_artifact"])
    units = _validated_units(value["units"], source)
    if value["unit_count"] != len(units):
        raise AlignmentUnitError("alignment unit_count changed")
    body = {key: value[key] for key in expected if key != "artifact_sha256"}
    if value["artifact_sha256"] != _sha_bytes(_canonical(body)):
        raise AlignmentUnitError("alignment unit package artifact digest changed")
    if source_ref != value["source_artifact"]:
        raise AlignmentUnitError("alignment unit source reference changed")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create_parser = sub.add_parser("create")
    create_parser.add_argument("--spec", required=True, type=Path)
    create_parser.add_argument("--output", required=True, type=Path)
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("package", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "create":
            value = create(args.spec)
            _write_once(value, args.output)
        else:
            value = verify(args.package)
    except AlignmentUnitError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps({
        "artifact_sha256": value["artifact_sha256"],
        "status": value["status"],
        "unit_count": value["unit_count"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
