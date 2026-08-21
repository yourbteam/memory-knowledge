#!/usr/bin/env python3
"""Assemble verified mini-probe winners into one immutable runnable candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from development_probe_candidate import (
    CandidateError,
    _check_execution,
    _snapshot_source,
    verify_bundle,
)
from development_probe_manifest import ManifestError, validate_manifest

CONTRACT = 1
ASSEMBLY_ENTRIES = {
    "assembly.json",
    "development-manifest.json",
    "inputs",
    "source",
}
RESULT_FIELDS = {"schema_version", "variant_id", "status", "outcome", "metrics", "error"}


class CompositionError(RuntimeError):
    """The selected candidates cannot form a trusted runnable assembly."""

    def __init__(self, stage: str, message: str):
        super().__init__(message)
        self.stage = stage


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _document(value: object) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _exact(value: object, label: str, fields: set[str], stage: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise CompositionError(stage, f"{label} must be one object with fields {sorted(fields)}")
    missing = sorted(fields - value.keys())
    extra = sorted(value.keys() - fields)
    if missing or extra:
        raise CompositionError(
            stage,
            f"{label} has missing fields {missing} and unexpected fields {extra}",
        )
    return value


def _load(path: Path, label: str, stage: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CompositionError(stage, f"{label} is unavailable or invalid JSON: {error}") from None
    if type(value) is not dict:
        raise CompositionError(stage, f"{label} must contain one JSON object")
    return value


def _resolve(value: object, base: Path, label: str, stage: str) -> Path:
    if type(value) is not str or not value:
        raise CompositionError(stage, f"{label} must be a nonempty path")
    path = Path(value)
    return (path if path.is_absolute() else base / path).absolute()


def _write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    path.chmod(0o444)


def _write_json(path: Path, value: object) -> str:
    payload = _document(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return _digest(payload)


def _make_read_only(root: Path) -> None:
    for directory in sorted(
        [root, *(path for path in root.rglob("*") if path.is_dir())],
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        directory.chmod(0o555)


def _restore_writable(root: Path) -> None:
    if not root.exists():
        return
    for path in [root, *root.rglob("*")]:
        try:
            path.chmod(0o755 if path.is_dir() else 0o644)
        except OSError:
            pass


def _prepare_output(output: Path) -> None:
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise CompositionError("prepare-output", f"output must be a new or empty directory: {output}")
    output.mkdir(parents=True, exist_ok=True)


def _manifest(path: Path) -> dict[str, Any]:
    try:
        return validate_manifest(_load(path, "development manifest", "verify-inputs"))
    except ManifestError as error:
        raise CompositionError("verify-inputs", f"development manifest is invalid: {error}") from None


def _candidate_set(path: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    value = _exact(
        _load(path, "promotion candidates", "verify-inputs"),
        "promotion candidates",
        {
            "schema_version",
            "status",
            "atomic_step_id",
            "candidates",
            "candidate_count",
            "promotion_applied",
        },
        "verify-inputs",
    )
    if value["schema_version"] != CONTRACT or type(value["schema_version"]) is not int:
        raise CompositionError("verify-inputs", "promotion candidates schema_version must be integer 1")
    if value["status"] != "candidates-ready":
        raise CompositionError("verify-inputs", "promotion candidates must have candidates-ready status")
    if value["atomic_step_id"] != manifest["atomic_step"]["id"]:
        raise CompositionError("verify-inputs", "promotion candidates belong to a different atomic step")
    if value["promotion_applied"] is not False:
        raise CompositionError("verify-inputs", "promotion candidates must remain unpromoted")
    candidates = value["candidates"]
    if type(candidates) is not list or value["candidate_count"] != len(candidates):
        raise CompositionError("verify-inputs", "candidate_count must equal the candidate list length")

    consumes = manifest["composition"]["consumes"]
    by_probe: dict[str, list[dict[str, Any]]] = {}
    for index, raw in enumerate(candidates):
        item = _exact(
            raw,
            f"promotion candidates[{index}]",
            {
                "probe_id",
                "artifact",
                "approach_id",
                "bundle",
                "bundle_sha256",
                "case_ids",
                "recommendation",
            },
            "verify-inputs",
        )
        probe_id = item["probe_id"]
        if type(probe_id) is not str:
            raise CompositionError("verify-inputs", f"promotion candidates[{index}].probe_id must be text")
        by_probe.setdefault(probe_id, []).append(item)
    declared = [item["probe_id"] for item in consumes]
    missing = [probe_id for probe_id in declared if probe_id not in by_probe]
    duplicates = sorted(probe_id for probe_id, rows in by_probe.items() if len(rows) != 1)
    unknown = sorted(probe_id for probe_id in by_probe if probe_id not in declared)
    if missing or duplicates or unknown:
        raise CompositionError(
            "verify-inputs",
            f"candidate coverage has missing {missing}, duplicate {duplicates}, unknown {unknown}",
        )
    ordered = [by_probe[probe_id][0] for probe_id in declared]
    for consume, item in zip(consumes, ordered, strict=True):
        if item["artifact"] != consume["artifact"]:
            raise CompositionError(
                "verify-inputs",
                f"probe {consume['probe_id']!r} supplies artifact {item['artifact']!r}; "
                f"require {consume['artifact']!r}",
            )
    return ordered


def _verified_winners(
    candidates_path: Path,
    candidates: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    winners = []
    for item in candidates:
        probe_id = item["probe_id"]
        bundle_path = _resolve(item["bundle"], candidates_path.parent, f"probe {probe_id!r} bundle", "verify-inputs")
        try:
            bundle, bundled_manifest, fresh_digest = verify_bundle(bundle_path)
        except (CandidateError, OSError) as error:
            raise CompositionError("verify-inputs", f"probe {probe_id!r} bundle verification failed: {error}") from None
        identity = bundle["identity"]
        problems = []
        if fresh_digest != item["bundle_sha256"]:
            problems.append(f"digest changed from {item['bundle_sha256']!r} to {fresh_digest!r}")
        if identity["atomic_step_id"] != manifest["atomic_step"]["id"]:
            problems.append("atomic-step identity differs")
        if identity["probe_id"] != probe_id:
            problems.append(f"bundle probe identity is {identity['probe_id']!r}")
        if identity["approach_id"] != item["approach_id"]:
            problems.append(f"bundle approach identity is {identity['approach_id']!r}")
        if bundled_manifest != manifest:
            problems.append("bundled development manifest differs")
        probe = next(probe for probe in manifest["mini_probes"] if probe["id"] == probe_id)
        expected_cases = [row["case_id"] for row in probe["inputs"]]
        if item["case_ids"] != expected_cases:
            problems.append(f"candidate cases are {item['case_ids']!r}, require {expected_cases!r}")
        if problems:
            raise CompositionError("verify-inputs", f"probe {probe_id!r} candidate is invalid: " + "; ".join(problems))
        payloads, _, candidate_sha256 = _snapshot_source(
            bundle_path / bundle["source"]["root"], f"probe {probe_id!r} candidate source"
        )
        if candidate_sha256 != bundle["source"]["candidate_sha256"]:
            raise CompositionError("verify-inputs", f"probe {probe_id!r} candidate source changed")
        winners.append(
            {
                "probe_id": probe_id,
                "artifact": item["artifact"],
                "approach_id": item["approach_id"],
                "bundle_sha256": fresh_digest,
                "bundle": bundle,
                "payloads": payloads,
            }
        )
    return winners


def _recover_operations(
    baseline_payloads: dict[str, bytes], baseline_sha256: str, winners: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    recovered = []
    for winner in winners:
        recorded_baseline = winner["bundle"]["source"]["baseline_sha256"]
        if recorded_baseline != baseline_sha256:
            raise CompositionError(
                "verify-inputs",
                f"probe {winner['probe_id']!r} baseline changed: recorded "
                f"{recorded_baseline}, actual {baseline_sha256}",
            )
        operations = []
        candidate_payloads = winner["payloads"]
        for relative in sorted(baseline_payloads.keys() | candidate_payloads.keys()):
            if relative not in baseline_payloads:
                action = "add"
            elif relative not in candidate_payloads:
                action = "delete"
            elif baseline_payloads[relative] != candidate_payloads[relative]:
                action = "change"
            else:
                continue
            payload = candidate_payloads.get(relative)
            operations.append(
                {
                    "path": relative,
                    "action": action,
                    "payload": payload,
                    "sha256": None if payload is None else _digest(payload),
                    "size": None if payload is None else len(payload),
                }
            )
        recovered.append({**winner, "operations": operations})
    return recovered


def _merge_operations(winners: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for winner in winners:
        for operation in winner["operations"]:
            indexed.setdefault(operation["path"], []).append((winner["probe_id"], operation))
    merged = []
    conflicts = []
    for relative in sorted(indexed):
        contributions = indexed[relative]
        signatures = {(operation["action"], operation["payload"]) for _, operation in contributions}
        contributors = sorted({probe_id for probe_id, _ in contributions})
        if len(signatures) != 1:
            conflicts.append(f"{relative} from {', '.join(contributors)}")
            continue
        operation = contributions[0][1]
        merged.append({**operation, "contributors": contributors})
    if conflicts:
        raise CompositionError("merge-winners", "incompatible winner operations: " + "; ".join(conflicts))
    return merged


def _bind_execution(winners: list[dict[str, Any]]) -> tuple[dict[str, Any], str]:
    expected = _canonical(winners[0]["bundle"]["execution"])
    entrypoint = winners[0]["bundle"]["source"]["entrypoint"]
    disagreements = []
    for winner in winners[1:]:
        if _canonical(winner["bundle"]["execution"]) != expected:
            disagreements.append(winner["probe_id"])
        if winner["bundle"]["source"]["entrypoint"] != entrypoint:
            disagreements.append(winner["probe_id"])
    if disagreements:
        raise CompositionError(
            "bind-execution",
            f"execution contracts differ for probes {sorted(set(disagreements))}; "
            "all independently proven winners must expose one exact runnable contract",
        )
    return winners[0]["bundle"]["execution"], entrypoint


def _captured_inputs(manifest: dict[str, Any], manifest_path: Path) -> tuple[dict[str, bytes], list[dict[str, Any]]]:
    payloads = {}
    records = []
    for case in manifest["atomic_step"]["captured_cases"]:
        source = _resolve(case["source"], manifest_path.parent, f"captured case {case['id']!r}", "verify-inputs")
        try:
            payload = source.read_bytes()
        except OSError as error:
            raise CompositionError("verify-inputs", f"captured case {case['id']!r} is unavailable: {error}") from None
        actual = _digest(payload)
        if actual != case["sha256"]:
            raise CompositionError(
                "verify-inputs",
                f"captured case {case['id']!r} changed: expected {case['sha256']}, actual {actual}",
            )
        relative = f"{case['id']}.input"
        payloads[relative] = payload
        records.append({"case_id": case["id"], "path": relative, "sha256": actual, "size": len(payload)})
    return payloads, records


def _assembly_digest(assembly: dict[str, Any], manifest: dict[str, Any]) -> str:
    return _digest(_canonical({"assembly": assembly, "development_manifest": manifest}))


def verify_assembly(root: Path) -> tuple[dict[str, Any], dict[str, Any], str]:
    root = root.absolute()
    if root.is_symlink() or not root.is_dir():
        raise CompositionError("verify-assembly", f"assembly is not a stable directory: {root}")
    linked = [path.relative_to(root) for path in root.rglob("*") if path.is_symlink()]
    if linked:
        raise CompositionError("verify-assembly", f"assembly contains symbolic links: {linked}")
    entries = {path.name for path in root.iterdir()}
    if entries != ASSEMBLY_ENTRIES:
        raise CompositionError(
            "verify-assembly", f"assembly entries are {sorted(entries)}; expected {sorted(ASSEMBLY_ENTRIES)}"
        )
    manifest_path = root / "development-manifest.json"
    manifest = _manifest(manifest_path)
    if manifest_path.read_bytes() != _document(manifest):
        raise CompositionError("verify-assembly", "development manifest changed from canonical bytes")
    assembly_path = root / "assembly.json"
    assembly = _load(assembly_path, "assembly manifest", "verify-assembly")
    if assembly_path.read_bytes() != _document(assembly):
        raise CompositionError("verify-assembly", "assembly manifest changed from canonical bytes")
    assembly = _exact(
        assembly,
        "assembly manifest",
        {
            "schema_version",
            "status",
            "identity",
            "baseline_sha256",
            "source",
            "inputs",
            "execution",
            "candidates",
            "operations",
            "promotion_applied",
        },
        "verify-assembly",
    )
    if assembly["schema_version"] != CONTRACT or assembly["status"] != "assembled":
        raise CompositionError("verify-assembly", "assembly must have schema_version 1 and assembled status")
    if assembly["promotion_applied"] is not False:
        raise CompositionError("verify-assembly", "assembly cannot record automatic promotion")
    identity = _exact(
        assembly["identity"],
        "assembly identity",
        {"atomic_step_id", "development_manifest_sha256"},
        "verify-assembly",
    )
    expected_manifest = _digest(_canonical(manifest))
    if identity != {
        "atomic_step_id": manifest["atomic_step"]["id"],
        "development_manifest_sha256": expected_manifest,
    }:
        raise CompositionError("verify-assembly", "assembly identity differs from its manifest")
    source = _exact(
        assembly["source"],
        "assembly source",
        {"root", "entrypoint", "sha256", "files"},
        "verify-assembly",
    )
    if source["root"] != "source":
        raise CompositionError("verify-assembly", "assembly source root must be exactly 'source'")
    _, files, source_sha256 = _snapshot_source(root / "source", "assembled source")
    if source["files"] != files or source["sha256"] != source_sha256:
        raise CompositionError("verify-assembly", "assembled source changed from its recorded digest")
    entrypoint = source["entrypoint"]
    if type(entrypoint) is not str or entrypoint not in {item["path"] for item in files}:
        raise CompositionError("verify-assembly", "assembled entrypoint is missing")
    try:
        _check_execution(assembly["execution"])
    except CandidateError as error:
        raise CompositionError("verify-assembly", f"assembly execution contract is invalid: {error}") from None
    input_files = {}
    for path in sorted((root / "inputs").iterdir()):
        if path.is_dir():
            raise CompositionError("verify-assembly", "assembly inputs must contain only files")
        payload = path.read_bytes()
        input_files[path.name] = {"sha256": _digest(payload), "size": len(payload)}
    recorded_inputs = assembly["inputs"]
    if type(recorded_inputs) is not list:
        raise CompositionError("verify-assembly", "assembly inputs must be a list")
    declared_cases = [item["id"] for item in manifest["atomic_step"]["captured_cases"]]
    recorded_cases = []
    for index, raw in enumerate(recorded_inputs):
        item = _exact(
            raw,
            f"assembly inputs[{index}]",
            {"case_id", "path", "sha256", "size"},
            "verify-assembly",
        )
        recorded_cases.append(item["case_id"])
        if input_files.get(item["path"]) != {"sha256": item["sha256"], "size": item["size"]}:
            raise CompositionError("verify-assembly", f"assembled input changed for {item['case_id']!r}")
    if recorded_cases != declared_cases:
        raise CompositionError("verify-assembly", "assembled inputs differ from declared case order")
    if set(input_files) != {item["path"] for item in recorded_inputs}:
        raise CompositionError("verify-assembly", "assembled input set changed")
    consumes = manifest["composition"]["consumes"]
    candidate_records = assembly["candidates"]
    if type(candidate_records) is not list or len(candidate_records) != len(consumes):
        raise CompositionError("verify-assembly", "assembly candidate set is incomplete")
    for index, (raw, consume) in enumerate(zip(candidate_records, consumes, strict=True)):
        item = _exact(
            raw,
            f"assembly candidates[{index}]",
            {"probe_id", "artifact", "approach_id", "bundle_sha256"},
            "verify-assembly",
        )
        if item["probe_id"] != consume["probe_id"] or item["artifact"] != consume["artifact"]:
            raise CompositionError("verify-assembly", "assembly candidate identity differs from composition")
        if type(item["approach_id"]) is not str or type(item["bundle_sha256"]) is not str:
            raise CompositionError("verify-assembly", "assembly candidate identity fields must be text")
    operations = assembly["operations"]
    if type(operations) is not list:
        raise CompositionError("verify-assembly", "assembly operations must be a list")
    operation_paths = []
    declared_probes = {item["probe_id"] for item in consumes}
    for index, raw in enumerate(operations):
        operation = _exact(
            raw,
            f"assembly operations[{index}]",
            {"path", "action", "sha256", "size", "contributors"},
            "verify-assembly",
        )
        operation_paths.append(operation["path"])
        if operation["action"] not in {"add", "change", "delete"}:
            raise CompositionError("verify-assembly", f"assembly operation has invalid action {operation['action']!r}")
        contributors = operation["contributors"]
        if (
            type(contributors) is not list
            or contributors != sorted(set(contributors))
            or not contributors
            or not set(contributors) <= declared_probes
        ):
            raise CompositionError("verify-assembly", "assembly operation contributors are invalid")
        if operation["action"] == "delete":
            if operation["sha256"] is not None or operation["size"] is not None:
                raise CompositionError("verify-assembly", "delete operations cannot record content")
        elif type(operation["sha256"]) is not str or type(operation["size"]) is not int:
            raise CompositionError("verify-assembly", "add/change operations require content hash and size")
    if operation_paths != sorted(set(operation_paths)):
        raise CompositionError("verify-assembly", "assembly operations must have unique sorted paths")
    for path in [root, *root.rglob("*")]:
        if path.stat().st_mode & 0o222:
            raise CompositionError("verify-assembly", f"assembly entry is writable: {path.relative_to(root)}")
    return assembly, manifest, _assembly_digest(assembly, manifest)


def compose(request_path: Path, output: Path) -> dict[str, Any]:
    request_path = request_path.absolute()
    request = _exact(
        _load(request_path, "composition request", "verify-inputs"),
        "composition request",
        {"schema_version", "development_manifest", "baseline", "promotion_candidates"},
        "verify-inputs",
    )
    if request["schema_version"] != CONTRACT or type(request["schema_version"]) is not int:
        raise CompositionError("verify-inputs", "composition request schema_version must be integer 1")
    output = output.absolute()
    _prepare_output(output)
    _write_json(output / "composition-request.json", request)
    manifest_path = _resolve(
        request["development_manifest"], request_path.parent, "development_manifest", "verify-inputs"
    )
    candidates_path = _resolve(
        request["promotion_candidates"], request_path.parent, "promotion_candidates", "verify-inputs"
    )
    baseline_path = _resolve(request["baseline"], request_path.parent, "baseline", "verify-inputs")
    manifest = _manifest(manifest_path)
    candidates = _candidate_set(candidates_path, manifest)
    winners = _verified_winners(candidates_path, candidates, manifest)
    try:
        baseline_payloads, _, baseline_sha256 = _snapshot_source(baseline_path, "baseline source")
    except CandidateError as error:
        raise CompositionError("verify-inputs", str(error)) from None
    recovered = _recover_operations(baseline_payloads, baseline_sha256, winners)
    merged = _merge_operations(recovered)
    execution, entrypoint = _bind_execution(recovered)
    composed_payloads = dict(baseline_payloads)
    for operation in merged:
        relative = operation["path"]
        if operation["action"] == "add":
            if relative in composed_payloads:
                raise CompositionError("merge-winners", f"add operation targets existing path {relative}")
            composed_payloads[relative] = operation["payload"]
        elif operation["action"] == "change":
            if relative not in composed_payloads:
                raise CompositionError("merge-winners", f"change operation targets absent path {relative}")
            composed_payloads[relative] = operation["payload"]
        else:
            if relative not in composed_payloads:
                raise CompositionError("merge-winners", f"delete operation targets absent path {relative}")
            del composed_payloads[relative]
    if entrypoint not in composed_payloads:
        raise CompositionError("bind-execution", f"assembled entrypoint is missing: {entrypoint!r}")
    files = [
        {"path": relative, "sha256": _digest(payload), "size": len(payload)}
        for relative, payload in sorted(composed_payloads.items())
    ]
    source_sha256 = _digest(_canonical(files))
    input_payloads, input_records = _captured_inputs(manifest, manifest_path)
    recorded_operations = [
        {
            "path": item["path"],
            "action": item["action"],
            "sha256": item["sha256"],
            "size": item["size"],
            "contributors": item["contributors"],
        }
        for item in merged
    ]
    candidate_records = [
        {
            "probe_id": winner["probe_id"],
            "artifact": winner["artifact"],
            "approach_id": winner["approach_id"],
            "bundle_sha256": winner["bundle_sha256"],
        }
        for winner in recovered
    ]
    assembly = {
        "schema_version": CONTRACT,
        "status": "assembled",
        "identity": {
            "atomic_step_id": manifest["atomic_step"]["id"],
            "development_manifest_sha256": _digest(_canonical(manifest)),
        },
        "baseline_sha256": baseline_sha256,
        "source": {
            "root": "source",
            "entrypoint": entrypoint,
            "sha256": source_sha256,
            "files": files,
        },
        "inputs": input_records,
        "execution": execution,
        "candidates": candidate_records,
        "operations": recorded_operations,
        "promotion_applied": False,
    }
    assembly_root = output / "assembly"
    temporary = Path(tempfile.mkdtemp(prefix=".assembly-", dir=output))
    try:
        _write(temporary / "development-manifest.json", _document(manifest))
        _write(temporary / "assembly.json", _document(assembly))
        for relative, payload in sorted(composed_payloads.items()):
            _write(temporary / "source" / relative, payload)
        for relative, payload in sorted(input_payloads.items()):
            _write(temporary / "inputs" / relative, payload)
        _make_read_only(temporary)
        temporary.rename(assembly_root)
    except Exception:
        _restore_writable(temporary)
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    verified, _, assembly_sha256 = verify_assembly(assembly_root)
    _write_json(
        output / "composition-summary.json",
        {
            "schema_version": CONTRACT,
            "status": "completed",
            "atomic_step_id": manifest["atomic_step"]["id"],
            "assembly_sha256": assembly_sha256,
            "source_sha256": verified["source"]["sha256"],
            "promotion_applied": False,
        },
    )
    return verified


def execute(root: Path, case_id: str, output: Path) -> dict[str, Any]:
    assembly, manifest, before_sha256 = verify_assembly(root)
    matches = [item for item in assembly["inputs"] if item["case_id"] == case_id]
    if len(matches) != 1:
        raise CompositionError("execute", f"case_id {case_id!r} is not declared exactly once")
    output = output.absolute()
    _prepare_output(output)
    input_path = root.absolute() / "inputs" / matches[0]["path"]
    result_path = output / "result.json"
    telemetry_path = output / "telemetry.jsonl"
    work_dir = output / "work"
    work_dir.mkdir()
    replacements = {
        "{python}": sys.executable,
        "{candidate-entrypoint}": str(root.absolute() / "source" / assembly["source"]["entrypoint"]),
        "{frozen-input}": str(input_path),
        "{result-path}": str(result_path),
        "{telemetry-path}": str(telemetry_path),
    }
    command = [replacements.get(argument, argument) for argument in assembly["execution"]["command"]]
    environment = os.environ.copy()
    environment.update(
        {
            "EXPERIMENT_VARIANT_ID": "assembly",
            "EXPERIMENT_INPUT_PATH": str(input_path),
            "EXPERIMENT_RESULT_PATH": str(result_path),
            "EXPERIMENT_TELEMETRY_PATH": str(telemetry_path),
            "EXPERIMENT_WORK_DIR": str(work_dir),
        }
    )
    completed = subprocess.run(
        command,
        cwd=work_dir,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    (output / "stdout.txt").write_text(completed.stdout, encoding="utf-8")
    (output / "stderr.txt").write_text(completed.stderr, encoding="utf-8")
    _, _, after_sha256 = verify_assembly(root)
    if before_sha256 != after_sha256:
        raise CompositionError("execute", "assembly changed during execution")
    if completed.returncode != 0:
        raise CompositionError(
            "execute", completed.stderr.strip() or f"assembled candidate exited {completed.returncode}"
        )
    result = _exact(_load(result_path, "assembled result", "execute"), "assembled result", RESULT_FIELDS, "execute")
    if result["schema_version"] != CONTRACT or result["variant_id"] != "assembly":
        raise CompositionError("execute", "assembled result has the wrong schema or variant identity")
    if result["status"] != "completed" or result["error"] is not None:
        raise CompositionError("execute", "assembled result did not complete cleanly")
    if type(result["outcome"]) is not dict or type(result["metrics"]) is not dict:
        raise CompositionError("execute", "assembled result outcome and metrics must be objects")
    _write_json(
        output / "execution-summary.json",
        {
            "schema_version": CONTRACT,
            "status": "completed",
            "atomic_step_id": manifest["atomic_step"]["id"],
            "case_id": case_id,
            "assembly_sha256": after_sha256,
        },
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="assemble the verified winners")
    run_parser.add_argument("request", type=Path)
    run_parser.add_argument("output", type=Path)
    verify_parser = subparsers.add_parser("verify", help="verify one immutable assembly")
    verify_parser.add_argument("assembly", type=Path)
    execute_parser = subparsers.add_parser("execute", help="execute one captured case")
    execute_parser.add_argument("assembly", type=Path)
    execute_parser.add_argument("case_id")
    execute_parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = getattr(args, "output", None)
    try:
        if args.command == "run":
            result = compose(args.request, args.output)
        elif args.command == "verify":
            assembly, _, assembly_sha256 = verify_assembly(args.assembly)
            result = {
                "status": "verified",
                "atomic_step_id": assembly["identity"]["atomic_step_id"],
                "assembly_sha256": assembly_sha256,
                "promotion_applied": False,
            }
        else:
            result = execute(args.assembly, args.case_id, args.output)
    except (CompositionError, OSError, subprocess.SubprocessError) as error:
        stage = error.stage if isinstance(error, CompositionError) else "runtime"
        run_started = (
            output is not None
            and output.is_dir()
            and (
                (args.command == "run" and (output / "composition-request.json").is_file())
                or (args.command == "execute" and (output / "work").is_dir())
            )
        )
        if run_started:
            try:
                summary = output / "composition-summary.json"
                if not summary.exists():
                    _write_json(
                        summary,
                        {
                            "schema_version": CONTRACT,
                            "status": "failed",
                            "stage": stage,
                            "error": str(error),
                            "promotion_applied": False,
                        },
                    )
            except OSError:
                pass
        print(f"Development-probe composition refused at {stage}: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
