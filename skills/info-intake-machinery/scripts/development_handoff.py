#!/usr/bin/env python3
"""Assemble and verify the root Info Intake development handoff."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import development_prototype_handoff
import development_target_set

CONTRACT = 1
ARTIFACT_TYPE = "info-intake-development-handoff"
SCRIPTS = Path(__file__).resolve().parent
MANIFEST_SCRIPT = SCRIPTS.parent.parent / "experiment-machinery/scripts/development_probe_manifest.py"


class DevelopmentHandoffError(RuntimeError):
    """The completed intake cannot safely enter downstream development machinery."""


def _manifest_module():
    spec = importlib.util.spec_from_file_location("development_probe_manifest", MANIFEST_SCRIPT)
    if spec is None or spec.loader is None:
        raise DevelopmentHandoffError("Experiment Machinery manifest validator is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
        raise DevelopmentHandoffError(f"{label} is unavailable or invalid JSON: {error}") from None
    if type(value) is not dict:
        raise DevelopmentHandoffError(f"{label} must contain one JSON object")
    return value


def _validate_case_lineage(
    manifest: dict[str, Any], selected_criterion_ids: set[str]
) -> list[dict[str, object]]:
    recorded: list[dict[str, object]] = []
    kinds: set[str] = set()
    for case in manifest["atomic_step"]["captured_cases"]:
        path = Path(case["source"])
        if _sha(path) != case["sha256"]:
            raise DevelopmentHandoffError(f"captured case bytes changed: {case['id']}")
        value = _load(path, f"captured case {case['id']}")
        if value.get("case_id") != case["id"]:
            raise DevelopmentHandoffError(f"captured case identity changed: {case['id']}")
        criterion_id = value.get("source_criterion_id")
        if criterion_id not in selected_criterion_ids:
            raise DevelopmentHandoffError(
                f"captured case {case['id']} is not grounded in Prototype 0 criteria"
            )
        kinds.add(case["kind"])
        recorded.append({
            "case_id": case["id"], "kind": case["kind"], "path": str(path.resolve()),
            "sha256": case["sha256"], "criterion_id": criterion_id,
        })
    if kinds != {"success", "failure"}:
        raise DevelopmentHandoffError("captured cases must include success and failure evidence")
    return recorded


def assemble(
    *, target_set_path: Path, prototype_handoff_path: Path, manifest_path: Path
) -> dict[str, object]:
    try:
        target_set = development_target_set.verify_target_set(target_set_path)
    except development_target_set.TargetSetError as error:
        raise DevelopmentHandoffError(f"target set is invalid: {error}") from None
    try:
        prototype = development_prototype_handoff.verify_handoff(prototype_handoff_path)
    except development_prototype_handoff.HandoffError as error:
        raise DevelopmentHandoffError(f"Prototype 0 handoff is invalid: {error}") from None
    manifest_value = _load(manifest_path, "development manifest")
    manifest_module = _manifest_module()
    try:
        manifest = manifest_module.validate_manifest(manifest_value)
    except manifest_module.ManifestError as error:
        raise DevelopmentHandoffError(f"Experiment Machinery rejected the manifest: {error}") from None
    objective_path = Path(str(prototype["development_objective"]["path"]))
    objective = _load(objective_path, "development objective")
    binding_path = Path(str(objective["target_binding"]["path"]))
    binding = _load(binding_path, "objective target binding")
    member_repositories = {item["repository"] for item in target_set["members"]}
    if binding["target"]["repository"] not in member_repositories:
        raise DevelopmentHandoffError("Prototype 0 target is absent from the target set")
    if binding["intake"]["intake_id"] != target_set["intake_id"]:
        raise DevelopmentHandoffError("Prototype 0 and target set belong to different intakes")
    selected_ids = {
        item["claim_id"] for item in prototype["prototype_zero"]["selected_criteria"]
    }
    cases = _validate_case_lineage(manifest, selected_ids)
    body: dict[str, object] = {
        "schema_version": CONTRACT,
        "artifact_type": ARTIFACT_TYPE,
        "intake_id": target_set["intake_id"],
        "target_set": {
            "path": str(target_set_path.resolve()),
            "sha256": _sha(target_set_path),
            "artifact_sha256": target_set["artifact_sha256"],
        },
        "prototype_driven_implementation": {
            "status": "contract-ready",
            "path": str(prototype_handoff_path.resolve()),
            "sha256": _sha(prototype_handoff_path),
            "artifact_sha256": prototype["artifact_sha256"],
            "authorization_status": prototype["prototype_envelope"]["authorization_status"],
            "prototype_zero_verdict": prototype["prototype_zero"]["verdict"],
        },
        "experiment_machinery": {
            "status": "manifest-accepted",
            "path": str(manifest_path.resolve()),
            "sha256": _sha(manifest_path),
            "atomic_step_id": manifest["atomic_step"]["id"],
            "mini_probe_ids": [item["id"] for item in manifest["mini_probes"]],
            "captured_cases": cases,
            "promotion_applied": False,
        },
        "next_commands": {
            "verify_pdi_handoff": [
                sys.executable, str(SCRIPTS / "development_prototype_handoff.py"),
                "verify", str(prototype_handoff_path.resolve()),
            ],
            "validate_experiment_manifest": [
                sys.executable, str(MANIFEST_SCRIPT), "validate", str(manifest_path.resolve()),
            ],
        },
        "status": "downstream-handoff-ready",
    }
    return {**body, "artifact_sha256": _sha_bytes(_canonical(body))}


def write_handoff(value: dict[str, object], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("xb") as stream:
            stream.write(_document(value))
    except FileExistsError:
        raise DevelopmentHandoffError(f"root handoff already exists: {output}") from None


def verify(path: Path) -> dict[str, object]:
    value = _load(path, "root handoff")
    if path.read_bytes() != _document(value):
        raise DevelopmentHandoffError("root handoff bytes are not canonical")
    expected = {
        "schema_version", "artifact_type", "intake_id", "target_set",
        "prototype_driven_implementation", "experiment_machinery", "next_commands",
        "status", "artifact_sha256",
    }
    if set(value) != expected:
        raise DevelopmentHandoffError("root handoff fields changed from the exact contract")
    body = {key: value[key] for key in expected if key != "artifact_sha256"}
    if value["artifact_sha256"] != _sha_bytes(_canonical(body)):
        raise DevelopmentHandoffError("root handoff artifact digest changed")
    rebuilt = assemble(
        target_set_path=Path(value["target_set"]["path"]),
        prototype_handoff_path=Path(value["prototype_driven_implementation"]["path"]),
        manifest_path=Path(value["experiment_machinery"]["path"]),
    )
    if rebuilt != value:
        raise DevelopmentHandoffError("live downstream inputs changed from the root handoff")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--target-set", required=True, type=Path)
    create.add_argument("--prototype-handoff", required=True, type=Path)
    create.add_argument("--development-manifest", required=True, type=Path)
    create.add_argument("--output", required=True, type=Path)
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("handoff", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "create":
            value = assemble(
                target_set_path=args.target_set,
                prototype_handoff_path=args.prototype_handoff,
                manifest_path=args.development_manifest,
            )
            write_handoff(value, args.output)
        else:
            value = verify(args.handoff)
    except DevelopmentHandoffError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps({
        "status": value["status"],
        "artifact_sha256": value["artifact_sha256"],
        "repository_count": len(development_target_set.verify_target_set(Path(value["target_set"]["path"]))["members"]),
        "mini_probe_count": len(value["experiment_machinery"]["mini_probe_ids"]),
        "captured_case_count": len(value["experiment_machinery"]["captured_cases"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
