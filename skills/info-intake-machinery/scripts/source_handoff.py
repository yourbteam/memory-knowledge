#!/usr/bin/env python3
"""Create and verify source-only request/return handoffs for Info Intake."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

CONTRACT = 1
REQUEST_TYPE = "info-intake-source-request"
RETURN_TYPE = "info-intake-source-return-package"
QUALIFICATION = "readable_projection_complete"
FORBIDDEN_SEMANTIC_FIELDS = {
    "verdict",
    "aligned",
    "misaligned",
    "resolves_gap",
    "gap_assessment",
}


class SourceHandoffError(RuntimeError):
    """The source-only handoff contract was not satisfied."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _document(value: object) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _artifact_sha(value: dict[str, Any]) -> str:
    body = deepcopy(value)
    body.pop("artifact_sha256", None)
    return _sha_bytes(_canonical(body))


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SourceHandoffError(f"{label} is unavailable or invalid JSON: {error}") from None
    if type(value) is not dict:
        raise SourceHandoffError(f"{label} must contain one JSON object")
    return value


def _exact_nonempty_strings(value: object, label: str, *, allow_empty: bool = False) -> list[str]:
    if type(value) is not list or (not value and not allow_empty):
        suffix = "a list" if allow_empty else "a nonempty list"
        raise SourceHandoffError(f"{label} must be {suffix}")
    if any(type(item) is not str or not item for item in value):
        raise SourceHandoffError(f"every {label} item must be a nonempty string")
    if len(value) != len(set(value)):
        raise SourceHandoffError(f"{label} items must be unique")
    return list(value)


def _write_once(value: dict[str, Any], output: Path, label: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("xb") as stream:
            stream.write(_document(value))
    except FileExistsError:
        raise SourceHandoffError(f"{label} already exists: {output}") from None


def _bound_file(path_value: object, label: str, *, utf8: bool = False) -> dict[str, str]:
    if type(path_value) is not str or not path_value:
        raise SourceHandoffError(f"{label} path must be a nonempty string")
    path = Path(path_value)
    if not path.is_absolute():
        raise SourceHandoffError(f"{label} path must be absolute: {path}")
    if path.is_symlink() or not path.is_file():
        raise SourceHandoffError(f"{label} must be a regular non-symbolic-link file: {path}")
    if utf8:
        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise SourceHandoffError(f"{label} is not a readable UTF-8 projection: {error}") from None
    return {"path": str(path), "sha256": _sha(path)}


def create_request(spec_path: Path) -> dict[str, Any]:
    spec = _load(spec_path, "source request specification")
    expected = {
        "schema_version",
        "request_id",
        "purpose",
        "requested_evidence",
        "related_unit_ids",
        "requester_path",
    }
    if set(spec) != expected:
        raise SourceHandoffError("source request specification fields changed from the exact contract")
    if spec["schema_version"] != CONTRACT:
        raise SourceHandoffError(f"source request schema_version must be {CONTRACT}")
    if type(spec["request_id"]) is not str or not spec["request_id"]:
        raise SourceHandoffError("request_id must be a nonempty string")
    if type(spec["purpose"]) is not str or not spec["purpose"]:
        raise SourceHandoffError("purpose must be a nonempty string")
    evidence = _exact_nonempty_strings(spec["requested_evidence"], "requested_evidence")
    unit_ids = _exact_nonempty_strings(spec["related_unit_ids"], "related_unit_ids", allow_empty=True)
    requester = _bound_file(spec["requester_path"], "requester artifact")
    body: dict[str, Any] = {
        "schema_version": CONTRACT,
        "artifact_type": REQUEST_TYPE,
        "request_id": spec["request_id"],
        "purpose": spec["purpose"],
        "requested_evidence": evidence,
        "related_unit_ids": unit_ids,
        "requester": {
            "artifact_path": requester["path"],
            "file_sha256": requester["sha256"],
        },
    }
    return {**body, "artifact_sha256": _sha_bytes(_canonical(body))}


def verify_request(path: Path) -> dict[str, Any]:
    value = _load(path, "source request")
    if path.read_bytes() != _document(value):
        raise SourceHandoffError("source request bytes are not canonical")
    expected = {
        "schema_version",
        "artifact_type",
        "request_id",
        "purpose",
        "requested_evidence",
        "related_unit_ids",
        "requester",
        "artifact_sha256",
    }
    if set(value) != expected:
        raise SourceHandoffError("source request fields changed from the exact contract")
    if value["schema_version"] != CONTRACT or value["artifact_type"] != REQUEST_TYPE:
        raise SourceHandoffError("source request identity changed")
    if FORBIDDEN_SEMANTIC_FIELDS.intersection(value):
        raise SourceHandoffError("source request cannot contain semantic verdict fields")
    _exact_nonempty_strings(value["requested_evidence"], "requested_evidence")
    _exact_nonempty_strings(value["related_unit_ids"], "related_unit_ids", allow_empty=True)
    if type(value["request_id"]) is not str or not value["request_id"]:
        raise SourceHandoffError("request_id must be a nonempty string")
    if type(value["purpose"]) is not str or not value["purpose"]:
        raise SourceHandoffError("purpose must be a nonempty string")
    requester = value["requester"]
    if type(requester) is not dict or set(requester) != {"artifact_path", "file_sha256"}:
        raise SourceHandoffError("requester must contain exact artifact_path and file_sha256")
    observed_requester = _bound_file(requester["artifact_path"], "requester artifact")
    if observed_requester["sha256"] != requester["file_sha256"]:
        raise SourceHandoffError("requester artifact bytes changed from the source request")
    if value["artifact_sha256"] != _artifact_sha(value):
        raise SourceHandoffError("source request artifact digest changed")
    return value


def _contains(value: object, needle: str) -> bool:
    if value == needle:
        return True
    if type(value) is dict:
        return any(_contains(item, needle) for item in value.values())
    if type(value) is list:
        return any(_contains(item, needle) for item in value)
    return False


def _verify_ledger(path_value: object, required_values: list[str]) -> dict[str, Any]:
    if type(path_value) is not str or not path_value:
        raise SourceHandoffError("intake ledger path must be a nonempty string")
    path = Path(path_value)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise SourceHandoffError(f"intake ledger must be an absolute regular file: {path}")
    previous: str | None = None
    entries: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise SourceHandoffError(f"intake ledger is not UTF-8: {error}") from None
    if not lines:
        raise SourceHandoffError("intake ledger is empty")
    for sequence, line in enumerate(lines, start=1):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as error:
            raise SourceHandoffError(f"intake ledger entry {sequence} is invalid JSON: {error}") from None
        if type(entry) is not dict:
            raise SourceHandoffError(f"intake ledger entry {sequence} must be one object")
        recorded = entry.get("entry_sha256")
        body = {key: item for key, item in entry.items() if key != "entry_sha256"}
        if entry.get("sequence") != sequence:
            raise SourceHandoffError(f"intake ledger sequence changed at entry {sequence}")
        if entry.get("previous_entry_sha256") != previous:
            raise SourceHandoffError(f"intake ledger predecessor changed at entry {sequence}")
        if recorded != _sha_bytes(_canonical(body)):
            raise SourceHandoffError(f"intake ledger digest changed at entry {sequence}")
        previous = recorded
        entries.append(entry)
    for required in required_values:
        if not any(_contains(entry, required) for entry in entries):
            raise SourceHandoffError(f"intake ledger does not bind required value {required}")
    return {
        "path": str(path),
        "sha256": _sha(path),
        "entry_count": len(entries),
        "tail_entry_sha256": previous,
    }


def create_return(request_path: Path, spec_path: Path) -> dict[str, Any]:
    request = verify_request(request_path)
    spec = _load(spec_path, "source return specification")
    if set(spec) != {"schema_version", "evidence_items"}:
        raise SourceHandoffError("source return specification fields changed from the exact contract")
    if spec["schema_version"] != CONTRACT:
        raise SourceHandoffError(f"source return schema_version must be {CONTRACT}")
    items = spec["evidence_items"]
    if type(items) is not list or not items:
        raise SourceHandoffError("evidence_items must be a nonempty list")
    recorded: list[dict[str, Any]] = []
    ids: set[str] = set()
    for position, item in enumerate(items, start=1):
        if type(item) is not dict or set(item) != {
            "item_id",
            "immutable_source_path",
            "readable_projection_path",
            "intake_ledger_path",
            "qualification",
        }:
            raise SourceHandoffError(f"evidence item {position} fields changed from the exact contract")
        item_id = item["item_id"]
        if type(item_id) is not str or not item_id or item_id in ids:
            raise SourceHandoffError(f"evidence item {position} must have a unique nonempty item_id")
        ids.add(item_id)
        if item["qualification"] != QUALIFICATION:
            raise SourceHandoffError(f"evidence item {item_id} qualification must be {QUALIFICATION}")
        source = _bound_file(item["immutable_source_path"], f"evidence item {item_id} immutable source")
        projection = _bound_file(
            item["readable_projection_path"],
            f"evidence item {item_id} readable projection",
            utf8=True,
        )
        ledger = _verify_ledger(
            item["intake_ledger_path"],
            [request["request_id"], source["sha256"], projection["sha256"]],
        )
        recorded.append({
            "item_id": item_id,
            "immutable_source": source,
            "readable_projection": projection,
            "intake_ledger": ledger,
            "qualification": QUALIFICATION,
        })
    request_ref = {
        "path": str(request_path.resolve()),
        "file_sha256": _sha(request_path),
        "artifact_sha256": request["artifact_sha256"],
        "request_id": request["request_id"],
    }
    body: dict[str, Any] = {
        "schema_version": CONTRACT,
        "artifact_type": RETURN_TYPE,
        "request": request_ref,
        "evidence_items": recorded,
        "status": "source-return-complete",
    }
    return {**body, "artifact_sha256": _sha_bytes(_canonical(body))}


def verify_return(path: Path) -> dict[str, Any]:
    value = _load(path, "source return package")
    if path.read_bytes() != _document(value):
        raise SourceHandoffError("source return package bytes are not canonical")
    expected = {
        "schema_version",
        "artifact_type",
        "request",
        "evidence_items",
        "status",
        "artifact_sha256",
    }
    if set(value) != expected:
        raise SourceHandoffError("source return package fields changed from the exact contract")
    if value["schema_version"] != CONTRACT or value["artifact_type"] != RETURN_TYPE:
        raise SourceHandoffError("source return package identity changed")
    if value["status"] != "source-return-complete":
        raise SourceHandoffError("source return package status changed")
    if FORBIDDEN_SEMANTIC_FIELDS.intersection(value):
        raise SourceHandoffError("source return package cannot contain semantic verdict fields")
    request_ref = value["request"]
    if type(request_ref) is not dict or set(request_ref) != {
        "path",
        "file_sha256",
        "artifact_sha256",
        "request_id",
    }:
        raise SourceHandoffError("source return request reference changed")
    request_path = Path(request_ref["path"])
    request = verify_request(request_path)
    if _sha(request_path) != request_ref["file_sha256"]:
        raise SourceHandoffError("source request file bytes changed from the return package")
    if request["artifact_sha256"] != request_ref["artifact_sha256"]:
        raise SourceHandoffError("source request artifact changed from the return package")
    if request["request_id"] != request_ref["request_id"]:
        raise SourceHandoffError("source request identity changed from the return package")
    items = value["evidence_items"]
    if type(items) is not list or not items:
        raise SourceHandoffError("source return evidence_items must be nonempty")
    ids: set[str] = set()
    for position, item in enumerate(items, start=1):
        if type(item) is not dict or set(item) != {
            "item_id",
            "immutable_source",
            "readable_projection",
            "intake_ledger",
            "qualification",
        }:
            raise SourceHandoffError(f"source return evidence item {position} changed")
        item_id = item["item_id"]
        if type(item_id) is not str or not item_id or item_id in ids:
            raise SourceHandoffError(f"source return evidence item {position} identity changed")
        ids.add(item_id)
        if item["qualification"] != QUALIFICATION:
            raise SourceHandoffError(f"source return evidence item {item_id} qualification changed")
        for field, readable in (("immutable_source", False), ("readable_projection", True)):
            ref = item[field]
            if type(ref) is not dict or set(ref) != {"path", "sha256"}:
                raise SourceHandoffError(f"source return {field} reference changed for {item_id}")
            observed = _bound_file(ref["path"], f"source return {field} for {item_id}", utf8=readable)
            if observed != ref:
                raise SourceHandoffError(f"source return {field} bytes changed for {item_id}")
        ledger_ref = item["intake_ledger"]
        if type(ledger_ref) is not dict or set(ledger_ref) != {
            "path",
            "sha256",
            "entry_count",
            "tail_entry_sha256",
        }:
            raise SourceHandoffError(f"source return intake ledger reference changed for {item_id}")
        observed_ledger = _verify_ledger(
            ledger_ref["path"],
            [request["request_id"], item["immutable_source"]["sha256"], item["readable_projection"]["sha256"]],
        )
        if observed_ledger != ledger_ref:
            raise SourceHandoffError(f"source return intake ledger changed for {item_id}")
    if value["artifact_sha256"] != _artifact_sha(value):
        raise SourceHandoffError("source return package artifact digest changed")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create_request_parser = sub.add_parser("create-request")
    create_request_parser.add_argument("--spec", required=True, type=Path)
    create_request_parser.add_argument("--output", required=True, type=Path)
    verify_request_parser = sub.add_parser("verify-request")
    verify_request_parser.add_argument("request", type=Path)
    create_return_parser = sub.add_parser("create-return")
    create_return_parser.add_argument("--request", required=True, type=Path)
    create_return_parser.add_argument("--spec", required=True, type=Path)
    create_return_parser.add_argument("--output", required=True, type=Path)
    verify_return_parser = sub.add_parser("verify-return")
    verify_return_parser.add_argument("package", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "create-request":
            value = create_request(args.spec)
            _write_once(value, args.output, "source request")
        elif args.command == "verify-request":
            value = verify_request(args.request)
        elif args.command == "create-return":
            value = create_return(args.request, args.spec)
            _write_once(value, args.output, "source return package")
        else:
            value = verify_return(args.package)
    except SourceHandoffError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps({
        "artifact_sha256": value["artifact_sha256"],
        "artifact_type": value["artifact_type"],
        "request_id": value["request_id"] if value["artifact_type"] == REQUEST_TYPE else value["request"]["request_id"],
        "status": "valid",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
