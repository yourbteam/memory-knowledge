#!/usr/bin/env python3
"""Adapt an Info Intake source return into runtime alignment admission."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
INFO_HANDOFF = HERE.parent.parent / "info-intake-machinery/scripts/source_handoff.py"
EVIDENCE_PACKAGE = HERE / "evidence_package.py"


class IntakeHandoffAdapterError(RuntimeError):
    pass


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise IntakeHandoffAdapterError(f"required adapter is unavailable: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


source_handoff = _load_module("system_alignment_source_handoff", INFO_HANDOFF)
evidence_package = _load_module("system_alignment_evidence_package", EVIDENCE_PACKAGE)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _artifact_digest(value: dict) -> str:
    return hashlib.sha256(
        _canonical({key: item for key, item in value.items() if key != "artifact_sha256"})
    ).hexdigest()


def _load(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IntakeHandoffAdapterError(f"{label} is unavailable or invalid JSON: {error}") from None
    if type(value) is not dict:
        raise IntakeHandoffAdapterError(f"{label} must contain one JSON object")
    return value


def _ref(path: Path) -> dict[str, str]:
    return {"path": str(path.resolve()), "sha256": _sha(path)}


def _dedupe_refs(items: list[dict[str, str]]) -> list[dict[str, str]]:
    recorded: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        identity = (item["path"], item["sha256"])
        if identity not in seen:
            seen.add(identity)
            recorded.append(item)
    return recorded


def adapt(handoff_path: Path, bindings_path: Path) -> dict:
    try:
        handoff = source_handoff.verify_return(handoff_path)
    except source_handoff.SourceHandoffError as error:
        raise IntakeHandoffAdapterError(f"Info Intake handoff is invalid: {error}") from None
    bindings = _load(bindings_path, "alignment bindings")
    expected = {"schema_version", "package_id", "subjects"}
    if set(bindings) != expected or bindings.get("schema_version") != 1:
        raise IntakeHandoffAdapterError(
            f"alignment bindings must use schema_version 1 and exactly {sorted(expected)}"
        )
    request_path = Path(handoff["request"]["path"])
    request = source_handoff.verify_request(request_path)
    items = {item["item_id"]: item for item in handoff["evidence_items"]}
    subjects = bindings["subjects"]
    if type(subjects) is not list or not subjects:
        raise IntakeHandoffAdapterError("alignment bindings subjects must be a nonempty list")
    admitted_subjects: list[dict] = []
    gaps: list[dict] = []
    all_refs = [_ref(handoff_path), _ref(request_path), _ref(bindings_path)]
    seen_subjects: set[str] = set()
    for index, raw in enumerate(subjects, start=1):
        fields = {
            "subject_id", "sequence", "label", "intent", "evidence_item_ids",
            "validation_cases",
        }
        if type(raw) is not dict or set(raw) != fields:
            raise IntakeHandoffAdapterError(
                f"subject {index} must contain exactly {sorted(fields)}"
            )
        subject_id = raw["subject_id"]
        if type(subject_id) is not str or not subject_id or subject_id in seen_subjects:
            raise IntakeHandoffAdapterError(f"subject {index} identity must be unique and nonempty")
        seen_subjects.add(subject_id)
        if raw["sequence"] != index:
            raise IntakeHandoffAdapterError(f"subject {subject_id} sequence must be {index}")
        item_ids = raw["evidence_item_ids"]
        if type(item_ids) is not list or not item_ids or any(type(item) is not str for item in item_ids):
            raise IntakeHandoffAdapterError(f"subject {subject_id} evidence_item_ids must be nonempty strings")
        if len(item_ids) != len(set(item_ids)):
            raise IntakeHandoffAdapterError(f"subject {subject_id} evidence_item_ids repeat")
        unknown = [item_id for item_id in item_ids if item_id not in items]
        if unknown:
            raise IntakeHandoffAdapterError(
                f"subject {subject_id} names unknown Info Intake evidence items {unknown}"
            )
        supporting: list[dict[str, str]] = []
        for item_id in item_ids:
            item = items[item_id]
            refs = [item["immutable_source"], item["readable_projection"], {
                "path": item["intake_ledger"]["path"],
                "sha256": item["intake_ledger"]["sha256"],
            }]
            supporting.extend(refs)
            all_refs.extend(refs)
        cases = raw["validation_cases"]
        if type(cases) is not list:
            raise IntakeHandoffAdapterError(f"subject {subject_id} validation_cases must be a list")
        if not cases:
            gaps.append({
                "subject_id": subject_id,
                "request": (
                    "Provide at least one frozen input plus runnable actual and reference adapters "
                    "for this subject; Info Intake projections alone cannot prove runtime alignment."
                ),
                "evidence_item_ids": item_ids,
            })
        admitted_subjects.append({
            "subject_id": subject_id,
            "sequence": index,
            "label": raw["label"],
            "intent": raw["intent"],
            "supporting_evidence": _dedupe_refs(supporting),
            "validation_cases": cases,
        })
    if gaps:
        result = {
            "schema_version": 1,
            "artifact_type": "system-alignment-intake-admission-gaps",
            "status": "validation-bindings-required",
            "package_id": bindings["package_id"],
            "purpose": request["purpose"],
            "info_intake_handoff": _ref(handoff_path),
            "alignment_bindings": _ref(bindings_path),
            "requests": gaps,
        }
        result["artifact_sha256"] = _artifact_digest(result)
        return result
    spec = {
        "schema_version": 1,
        "package_id": bindings["package_id"],
        "purpose": request["purpose"],
        "sources": _dedupe_refs(all_refs),
        "subjects": admitted_subjects,
    }
    return evidence_package.admit(spec)


def verify(path: Path) -> dict:
    value = _load(path, "adapted admission")
    if value.get("artifact_type") == "system-alignment-evidence-package":
        return evidence_package.verify(path)
    if value.get("artifact_type") != "system-alignment-intake-admission-gaps":
        raise IntakeHandoffAdapterError("adapted admission artifact type is unknown")
    if value.get("artifact_sha256") != _artifact_digest(value):
        raise IntakeHandoffAdapterError("adapted admission artifact digest changed")
    rebuilt = adapt(
        Path(value["info_intake_handoff"]["path"]),
        Path(value["alignment_bindings"]["path"]),
    )
    if rebuilt != value:
        raise IntakeHandoffAdapterError("adapted admission no longer matches current handoff inputs")
    return value


def _write_once(value: dict, output: Path) -> None:
    if output.exists():
        raise IntakeHandoffAdapterError(f"output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def development_probe(case_path: Path, result_path: Path, telemetry_path: Path) -> int:
    case = _load(case_path, "development case")
    value = adapt(Path(case["handoff"]), Path(case["bindings"]))
    expected_status = case["expected_status"]
    evidence_grounded = (
        value.get("status") == "assessment-ready"
        and value.get("artifact_type") == "system-alignment-evidence-package"
    ) or (
        value.get("status") == "validation-bindings-required"
        and bool(value.get("requests"))
    )
    outcome = {
        "status_correct": value.get("status") == expected_status,
        "evidence_grounded": evidence_grounded,
    }
    result_path.write_text(json.dumps({
        "schema_version": 1,
        "variant_id": os.environ["EXPERIMENT_VARIANT_ID"],
        "status": "completed",
        "outcome": outcome,
        "metrics": {
            "correct-admission": int(all(outcome.values())),
            "no-invented-runtime-evidence": int(evidence_grounded),
        },
        "error": None,
    }))
    telemetry_path.write_text(json.dumps({
        "event": "info-intake-handoff-adapted",
        "observed_status": value.get("status"),
        "outcome": outcome,
    }) + "\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    if len(sys.argv) == 4 and sys.argv[1] not in {"create", "verify"}:
        return development_probe(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--handoff", required=True, type=Path)
    create.add_argument("--bindings", required=True, type=Path)
    create.add_argument("--output", required=True, type=Path)
    check = sub.add_parser("verify")
    check.add_argument("artifact", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            value = adapt(args.handoff, args.bindings)
            _write_once(value, args.output)
        else:
            value = verify(args.artifact)
    except (
        IntakeHandoffAdapterError,
        evidence_package.EvidencePackageError,
        source_handoff.SourceHandoffError,
        OSError,
        json.JSONDecodeError,
    ) as error:
        print(f"Info Intake admission refused: {error}", file=sys.stderr)
        return 2
    print(json.dumps({
        "status": value["status"],
        "package_id": value["package_id"],
        "artifact_sha256": value["artifact_sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
