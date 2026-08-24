#!/usr/bin/env python3
"""Create and verify required actual/reference path inventories."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

CONTRACT = 1
ARTIFACT_TYPE = "system-alignment-path-inventory"
UNIT_TYPE = "system-alignment-assessment-units"
ROLES = {"actual", "reference"}
KINDS = {"observable", "transformation", "transport", "service", "reference"}


class PathInventoryError(RuntimeError):
    """The required alignment paths are not exactly bound."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _document(value: object) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PathInventoryError(f"{label} is unavailable or invalid JSON: {error}") from None
    if type(value) is not dict:
        raise PathInventoryError(f"{label} must contain one JSON object")
    return value


def _nonempty(value: object, label: str) -> str:
    if type(value) is not str or not value:
        raise PathInventoryError(f"{label} must be a nonempty string")
    return value


def _units_reference(ref: object) -> dict[str, str]:
    if type(ref) is not dict or set(ref) != {"path", "sha256", "artifact_sha256"}:
        raise PathInventoryError("units_package must contain exact path, sha256, and artifact_sha256")
    path = Path(_nonempty(ref["path"], "units_package path"))
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise PathInventoryError(f"units_package must be an absolute regular file: {path}")
    observed = _sha(path)
    if observed != ref["sha256"]:
        raise PathInventoryError(
            f"units_package bytes changed: expected {ref['sha256']}, observed {observed}"
        )
    units = _load(path, "units_package")
    if (
        units.get("artifact_type") != UNIT_TYPE
        or units.get("artifact_sha256") != ref["artifact_sha256"]
        or units.get("status") != "units-admitted"
    ):
        raise PathInventoryError("units_package identity or status changed")
    return {"path": str(path), "sha256": observed, "artifact_sha256": ref["artifact_sha256"]}


def _paths(value: object) -> tuple[list[dict[str, Any]], dict[str, str]]:
    if type(value) is not list or len(value) != 2:
        raise PathInventoryError("paths must contain exactly one actual and one reference path")
    roles: set[str] = set()
    path_ids: set[str] = set()
    stage_roles: dict[str, str] = {}
    recorded: list[dict[str, Any]] = []
    for path in value:
        if type(path) is not dict or set(path) != {"path_id", "role", "stages"}:
            raise PathInventoryError("path fields changed from the exact contract")
        path_id = _nonempty(path["path_id"], "path_id")
        if path_id in path_ids:
            raise PathInventoryError(f"path_id is duplicated: {path_id}")
        path_ids.add(path_id)
        role = path["role"]
        if role not in ROLES or role in roles:
            raise PathInventoryError("path roles must be unique actual and reference values")
        roles.add(role)
        stages = path["stages"]
        if type(stages) is not list or not stages:
            raise PathInventoryError(f"path {path_id} must contain stages")
        for position, stage in enumerate(stages, start=1):
            if type(stage) is not dict or set(stage) != {
                "stage_id",
                "sequence",
                "kind",
                "purpose",
            }:
                raise PathInventoryError(f"path {path_id} stage {position} fields changed")
            stage_id = _nonempty(stage["stage_id"], f"path {path_id} stage_id")
            if stage_id in stage_roles:
                raise PathInventoryError(f"stage_id is duplicated: {stage_id}")
            if stage["sequence"] != position:
                raise PathInventoryError(
                    f"stage {stage_id} sequence must be {position}, received {stage['sequence']!r}"
                )
            if stage["kind"] not in KINDS:
                raise PathInventoryError(
                    f"stage {stage_id} kind must be one of {sorted(KINDS)}, received {stage['kind']!r}"
                )
            _nonempty(stage["purpose"], f"stage {stage_id} purpose")
            stage_roles[stage_id] = role
        recorded.append(deepcopy(path))
    if roles != ROLES:
        raise PathInventoryError("path roles must be exactly actual and reference")
    return recorded, stage_roles


def create(spec_path: Path) -> dict[str, Any]:
    spec = _load(spec_path, "path inventory specification")
    if set(spec) != {"schema_version", "units_package", "paths", "comparison"}:
        raise PathInventoryError("path inventory specification fields changed from the exact contract")
    if spec["schema_version"] != CONTRACT:
        raise PathInventoryError(f"path inventory schema_version must be {CONTRACT}")
    units_ref = _units_reference(spec["units_package"])
    paths, stage_roles = _paths(spec["paths"])
    comparison = spec["comparison"]
    if type(comparison) is not dict or set(comparison) != {
        "actual_stage_id",
        "reference_stage_id",
        "purpose",
    }:
        raise PathInventoryError("comparison fields changed from the exact contract")
    if stage_roles.get(comparison["actual_stage_id"]) != "actual":
        raise PathInventoryError("comparison actual_stage_id must name an actual path stage")
    if stage_roles.get(comparison["reference_stage_id"]) != "reference":
        raise PathInventoryError("comparison reference_stage_id must name a reference path stage")
    _nonempty(comparison["purpose"], "comparison purpose")
    body: dict[str, Any] = {
        "schema_version": CONTRACT,
        "artifact_type": ARTIFACT_TYPE,
        "units_package": units_ref,
        "paths": paths,
        "comparison": deepcopy(comparison),
        "status": "path-inventory-ready",
    }
    return {**body, "artifact_sha256": hashlib.sha256(_canonical(body)).hexdigest()}


def _write_once(value: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("xb") as stream:
            stream.write(_document(value))
    except FileExistsError:
        raise PathInventoryError(f"path inventory already exists: {output}") from None


def verify(path: Path) -> dict[str, Any]:
    value = _load(path, "path inventory")
    if path.read_bytes() != _document(value):
        raise PathInventoryError("path inventory bytes are not canonical")
    expected = {
        "schema_version", "artifact_type", "units_package", "paths",
        "comparison", "status", "artifact_sha256",
    }
    if set(value) != expected:
        raise PathInventoryError("path inventory fields changed from the exact contract")
    if value["artifact_type"] != ARTIFACT_TYPE or value["status"] != "path-inventory-ready":
        raise PathInventoryError("path inventory identity or status changed")
    rebuilt_spec = {
        "schema_version": value["schema_version"],
        "units_package": value["units_package"],
        "paths": value["paths"],
        "comparison": value["comparison"],
    }
    temporary = create_from_value(rebuilt_spec)
    if temporary != value:
        raise PathInventoryError("path inventory no longer matches live bound inputs")
    return value


def create_from_value(spec: dict[str, Any]) -> dict[str, Any]:
    units_ref = _units_reference(spec["units_package"])
    paths, stage_roles = _paths(spec["paths"])
    comparison = spec["comparison"]
    if stage_roles.get(comparison.get("actual_stage_id")) != "actual" or stage_roles.get(
        comparison.get("reference_stage_id")
    ) != "reference":
        raise PathInventoryError("comparison endpoints changed")
    _nonempty(comparison.get("purpose"), "comparison purpose")
    body = {
        "schema_version": CONTRACT,
        "artifact_type": ARTIFACT_TYPE,
        "units_package": units_ref,
        "paths": paths,
        "comparison": deepcopy(comparison),
        "status": "path-inventory-ready",
    }
    return {**body, "artifact_sha256": hashlib.sha256(_canonical(body)).hexdigest()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create_parser = sub.add_parser("create")
    create_parser.add_argument("--spec", required=True, type=Path)
    create_parser.add_argument("--output", required=True, type=Path)
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("inventory", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            value = create(args.spec)
            _write_once(value, args.output)
        else:
            value = verify(args.inventory)
    except PathInventoryError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps({"artifact_sha256": value["artifact_sha256"], "path_count": len(value["paths"]), "status": value["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
