#!/usr/bin/env python3
"""Admit immutable, source-neutral alignment evidence with executable cases."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

SHA256 = re.compile(r"^[0-9a-f]{64}$")
PLACEHOLDERS = {"{python}", "{adapter}", "{frozen-input}", "{result-path}", "{telemetry-path}"}


class EvidencePackageError(RuntimeError):
    pass


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def artifact_digest(value: dict) -> str:
    return hashlib.sha256(canonical({key: item for key, item in value.items() if key != "artifact_sha256"})).hexdigest()


def exact(value: object, fields: set[str], label: str) -> dict:
    if type(value) is not dict or set(value) != fields:
        raise EvidencePackageError(f"{label} must contain exactly {sorted(fields)}")
    return value


def text(value: object, label: str) -> str:
    if type(value) is not str or not value.strip():
        raise EvidencePackageError(f"{label} must be a nonempty string")
    return value


def file_ref(value: object, label: str) -> dict:
    item = exact(value, {"path", "sha256"}, label)
    path = Path(text(item["path"], f"{label}.path"))
    expected = item["sha256"]
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise EvidencePackageError(f"{label}.path must be an absolute regular file")
    if type(expected) is not str or not SHA256.fullmatch(expected):
        raise EvidencePackageError(f"{label}.sha256 must be 64 lowercase hex characters")
    observed = hashlib.sha256(path.read_bytes()).hexdigest()
    if observed != expected:
        raise EvidencePackageError(f"{label} bytes changed: expected {expected}, observed {observed}")
    return {"path": str(path), "sha256": expected}


def runner(value: object, label: str) -> dict:
    item = exact(value, {"adapter", "command"}, label)
    adapter = file_ref(item["adapter"], f"{label}.adapter")
    command = item["command"]
    if type(command) is not list or not command or any(type(arg) is not str or not arg for arg in command):
        raise EvidencePackageError(f"{label}.command must be a nonempty argument array")
    unknown = [arg for arg in command if ("{" in arg or "}" in arg) and arg not in PLACEHOLDERS]
    if unknown:
        raise EvidencePackageError(f"{label}.command has unknown placeholders {unknown}")
    required = {"{adapter}", "{frozen-input}", "{result-path}", "{telemetry-path}"}
    missing = sorted(required - set(command))
    if missing:
        raise EvidencePackageError(f"{label}.command is not runnable; add placeholders {missing}")
    return {"adapter": adapter, "command": command}


def admit(spec: dict) -> dict:
    root = exact(spec, {"schema_version", "package_id", "purpose", "sources", "subjects"}, "spec")
    if root["schema_version"] != 1 or type(root["schema_version"]) is not int:
        raise EvidencePackageError("schema_version must be integer 1")
    package_id = text(root["package_id"], "package_id")
    purpose = text(root["purpose"], "purpose")
    if type(root["sources"]) is not list or not root["sources"]:
        raise EvidencePackageError("sources must be a nonempty list")
    sources = [file_ref(item, f"sources[{index}]") for index, item in enumerate(root["sources"])]
    if type(root["subjects"]) is not list or not root["subjects"]:
        raise EvidencePackageError("subjects must be a nonempty list")
    subjects = []
    identities = []
    for index, raw in enumerate(root["subjects"]):
        label = f"subjects[{index}]"
        subject = exact(raw, {"subject_id", "sequence", "label", "intent", "supporting_evidence", "validation_cases"}, label)
        subject_id = text(subject["subject_id"], f"{label}.subject_id")
        if subject_id in identities:
            raise EvidencePackageError(f"duplicate subject_id {subject_id!r}")
        identities.append(subject_id)
        if subject["sequence"] != index + 1:
            raise EvidencePackageError(f"{label}.sequence must be {index + 1}")
        evidence = subject["supporting_evidence"]
        if type(evidence) is not list:
            raise EvidencePackageError(f"{label}.supporting_evidence must be a list")
        bound_evidence = [file_ref(item, f"{label}.supporting_evidence[{offset}]") for offset, item in enumerate(evidence)]
        cases = subject["validation_cases"]
        if type(cases) is not list or not cases:
            raise EvidencePackageError(f"{label}.validation_cases must contain at least one runnable actual/reference case")
        bound_cases = []
        case_ids = []
        for offset, raw_case in enumerate(cases):
            case_label = f"{label}.validation_cases[{offset}]"
            case = exact(raw_case, {"case_id", "sequence", "frozen_input", "actual", "reference"}, case_label)
            case_id = text(case["case_id"], f"{case_label}.case_id")
            if case_id in case_ids:
                raise EvidencePackageError(f"{label} repeats case_id {case_id!r}")
            case_ids.append(case_id)
            if case["sequence"] != offset + 1:
                raise EvidencePackageError(f"{case_label}.sequence must be {offset + 1}")
            bound_cases.append({"case_id": case_id, "sequence": offset + 1, "frozen_input": file_ref(case["frozen_input"], f"{case_label}.frozen_input"), "actual": runner(case["actual"], f"{case_label}.actual"), "reference": runner(case["reference"], f"{case_label}.reference")})
        subjects.append({"subject_id": subject_id, "sequence": index + 1, "label": text(subject["label"], f"{label}.label"), "intent": text(subject["intent"], f"{label}.intent"), "supporting_evidence": bound_evidence, "validation_cases": bound_cases})
    result = {"schema_version": 1, "artifact_type": "system-alignment-evidence-package", "status": "assessment-ready", "package_id": package_id, "purpose": purpose, "sources": sources, "subjects": subjects}
    result["artifact_sha256"] = artifact_digest(result)
    return result


def write_once(value: dict, output: Path) -> None:
    if output.exists():
        raise EvidencePackageError(f"output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def verify(path: Path) -> dict:
    value = json.loads(path.read_text())
    if value.get("artifact_type") != "system-alignment-evidence-package" or value.get("status") != "assessment-ready":
        raise EvidencePackageError("artifact identity is not an assessment-ready evidence package")
    if value.get("artifact_sha256") != artifact_digest(value):
        raise EvidencePackageError("artifact digest does not match its content")
    spec = {key: value[key] for key in ("schema_version", "package_id", "purpose", "sources", "subjects")}
    rebuilt = admit(spec)
    if rebuilt != value:
        raise EvidencePackageError("artifact does not rebuild from current evidence bytes")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--spec", required=True, type=Path)
    create.add_argument("--output", required=True, type=Path)
    check = sub.add_parser("verify")
    check.add_argument("artifact", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "create":
            value = admit(json.loads(args.spec.read_text()))
            write_once(value, args.output)
        else:
            value = verify(args.artifact)
    except (EvidencePackageError, OSError, json.JSONDecodeError) as error:
        print(f"Evidence package refused: {error}", file=sys.stderr)
        return 2
    print(json.dumps({"status": value["status"], "package_id": value["package_id"], "subject_count": len(value["subjects"]), "artifact_sha256": value["artifact_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main())
