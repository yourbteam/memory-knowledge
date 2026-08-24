#!/usr/bin/env python3
"""Turn exact assessment gaps into a small complete source-request set."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

CONTRACT = 1
ROLES = ("criterion", "observation", "context")
_SCRIPT_DIR = Path(__file__).resolve().parent


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"{name} is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


journal = _load_module("assessment_gap_request_journal", _SCRIPT_DIR / "projection_interview.py")
sufficiency_contract = _load_module("assessment_gap_request_sufficiency", _SCRIPT_DIR / "assessment_sufficiency.py")


class AssessmentGapRequestError(RuntimeError):
    """Raised when a request set loses or changes assessment gaps."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as error:
        raise AssessmentGapRequestError(f"{label} is unavailable or invalid JSON: {error}") from error
    if not isinstance(value, dict):
        raise AssessmentGapRequestError(f"{label} must contain one object")
    return value, raw


def _ref(path: Path, raw: bytes, value: dict[str, Any]) -> dict[str, object]:
    return {"path": str(path.resolve()), "sha256": _digest(raw), "artifact_sha256": value.get("artifact_sha256")}


def _requests(gaps: list[dict[str, Any]]) -> list[dict[str, object]]:
    requests = []
    for role in ROLES:
        selected = [gap for gap in gaps if gap["obligation_id"].endswith(":" + role)]
        if not selected:
            continue
        requests.append({
            "request_id": f"request-{len(requests) + 1:06d}",
            "role": role,
            "question": f"Provide one or more immutable sources that collectively establish the listed missing {role} evidence.",
            "gap_ids": [gap["gap_id"] for gap in selected],
            "unit_ids": list(dict.fromkeys(gap["unit_id"] for gap in selected)),
            "missing_evidence": [gap["missing_evidence"] for gap in selected],
        })
    return requests


def _artifact(source_ref: dict[str, object], sufficiency: dict[str, Any]) -> dict[str, object]:
    gaps = sufficiency.get("gaps")
    if not isinstance(gaps, list):
        raise AssessmentGapRequestError(
            f"assessment sufficiency gaps received {gaps!r}; provide one exact gaps list"
        )
    requests = _requests(gaps)
    value: dict[str, object] = {
        "schema_version": CONTRACT,
        "artifact_type": "info-intake-assessment-gap-requests",
        "status": "source-requests-ready",
        "sufficiency_source": source_ref,
        "gap_count": len(gaps),
        "request_count": len(requests),
        "covered_gap_ids": [gap_id for request in requests for gap_id in request["gap_ids"]],
        "requests": requests,
    }
    value["artifact_sha256"] = _digest(_canonical(value))
    return value


def _verify_exact_coverage(value: dict[str, Any], sufficiency: dict[str, Any]) -> None:
    expected = [gap["gap_id"] for gap in sufficiency["gaps"]]
    received = [gap_id for request in value["requests"] for gap_id in request["gap_ids"]]
    if len(received) != len(expected) or sorted(received) != sorted(expected):
        missing = sorted(set(expected) - set(received))
        duplicate = sorted({item for item in received if received.count(item) > 1})
        unknown = sorted(set(received) - set(expected))
        raise AssessmentGapRequestError(f"gap coverage received missing={missing!r}, duplicate={duplicate!r}, unknown={unknown!r}; cover every exact gap once")
    gap_by_id = {gap["gap_id"]: gap for gap in sufficiency["gaps"]}
    for request in value["requests"]:
        for gap_id, missing_evidence in zip(request["gap_ids"], request["missing_evidence"], strict=True):
            if gap_by_id[gap_id]["missing_evidence"] != missing_evidence:
                raise AssessmentGapRequestError(f"request {request['request_id']} changed missing evidence for {gap_id}")


def run(sufficiency_path: Path, work_dir: Path) -> dict[str, object]:
    try:
        sufficiency_contract.verify(sufficiency_path)
    except Exception as error:
        raise AssessmentGapRequestError(str(error)) from error
    sufficiency, raw = _load(sufficiency_path, "assessment sufficiency")
    source_ref = _ref(sufficiency_path, raw, sufficiency)
    work_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = work_dir / "requests.json"
    ledger_path = work_dir / "ledger.jsonl"
    artifact = _artifact(source_ref, sufficiency)
    _verify_exact_coverage(artifact, sufficiency)
    payload = json.dumps(artifact, indent=2, sort_keys=True).encode() + b"\n"
    if artifact_path.exists():
        if artifact_path.read_bytes() != payload:
            raise AssessmentGapRequestError("assessment gap request artifact already exists with different bytes")
        return verify(artifact_path)
    if ledger_path.exists():
        raise AssessmentGapRequestError("assessment gap request ledger exists without its artifact")
    journal._append(ledger_path, "assessment_gap_requests_started", {"sufficiency": source_ref})
    journal._append(ledger_path, "assessment_gap_requests_completed", {"artifact_path": "requests.json", "artifact_sha256": _digest(payload)})
    artifact_path.write_bytes(payload)
    return artifact


def verify(path: Path) -> dict[str, object]:
    value, _raw = _load(path, "assessment gap requests")
    if value.get("artifact_type") != "info-intake-assessment-gap-requests" or value.get("status") != "source-requests-ready":
        raise AssessmentGapRequestError("assessment gap request type or status is invalid")
    source = value.get("sufficiency_source")
    if not isinstance(source, dict):
        raise AssessmentGapRequestError("assessment gap request source is invalid")
    sufficiency_path = Path(str(source.get("path")))
    try:
        sufficiency_contract.verify(sufficiency_path)
    except Exception as error:
        raise AssessmentGapRequestError(str(error)) from error
    sufficiency, source_raw = _load(sufficiency_path, "assessment sufficiency")
    source_ref = _ref(sufficiency_path, source_raw, sufficiency)
    if source != source_ref:
        raise AssessmentGapRequestError("assessment gap request source binding changed")
    _verify_exact_coverage(value, sufficiency)
    if _artifact(source_ref, sufficiency) != value:
        raise AssessmentGapRequestError("assessment gap requests changed")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("run")
    create.add_argument("--sufficiency", type=Path, required=True)
    create.add_argument("--work", type=Path, required=True)
    check = commands.add_parser("verify")
    check.add_argument("artifact", type=Path)
    args = parser.parse_args()
    try:
        result = run(args.sufficiency, args.work) if args.command == "run" else verify(args.artifact)
    except AssessmentGapRequestError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
