#!/usr/bin/env python3
"""Build, verify, and execute one immutable development-probe candidate bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path, PurePath, PurePosixPath
from typing import Any

from development_probe_manifest import ManifestError, validate_manifest

CONTRACT = 1
PROTOCOL = "experiment-result-v1"
IDENTITY = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
PLACEHOLDERS = {
    "{python}",
    "{candidate-entrypoint}",
    "{frozen-input}",
    "{result-path}",
    "{telemetry-path}",
}
SHELL_MARKERS = (";", "&", "|", "<", ">", "$", "`", "\n", "\r")
BUNDLE_ENTRIES = {"bundle.json", "development-manifest.json", "source"}


class CandidateError(RuntimeError):
    """The candidate bundle cannot be trusted or executed."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _document(value: object) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _exact(value: object, label: str, fields: set[str]) -> dict[str, Any]:
    if type(value) is not dict:
        raise CandidateError(
            f"{label} is {type(value).__name__}; provide an object with fields {sorted(fields)}"
        )
    missing = sorted(fields - value.keys())
    extra = sorted(value.keys() - fields)
    if missing or extra:
        raise CandidateError(
            f"{label} has missing fields {missing} and unexpected fields {extra}; "
            "add missing fields and remove unexpected fields"
        )
    return value


def _identifier(value: object, label: str) -> str:
    if type(value) is not str or not IDENTITY.fullmatch(value):
        raise CandidateError(
            f"{label} is {value!r}; use lowercase letters, digits, and single hyphens"
        )
    return value


def _digest_field(value: object, label: str) -> str:
    if type(value) is not str or not SHA256.fullmatch(value):
        raise CandidateError(f"{label} must be 64 lowercase hexadecimal characters")
    return value


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CandidateError(f"{label} is unavailable or invalid JSON: {error}") from None
    if type(value) is not dict:
        raise CandidateError(f"{label} must contain one JSON object")
    return value


def _load_canonical_json(path: Path, label: str) -> dict[str, Any]:
    value = _load_json(path, label)
    if path.read_bytes() != _document(value):
        raise CandidateError(f"{label} changed from its canonical recorded bytes")
    return value


def _relative(value: object, label: str) -> str:
    if type(value) is not str or not value:
        raise CandidateError(f"{label} must be a nonempty relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise CandidateError(f"{label} must stay inside source; received {value!r}")
    return value


def _resolve_path(value: object, base: Path, label: str) -> Path:
    if type(value) is not str or not value:
        raise CandidateError(f"{label} must be a nonempty path")
    path = Path(value)
    return (path if path.is_absolute() else base / path).absolute()


def _snapshot_source(path: Path, label: str) -> tuple[dict[str, bytes], list[dict[str, object]], str]:
    if path.is_symlink():
        raise CandidateError(f"{label} root must not be a symbolic link")
    path = path.resolve()
    if not path.is_dir():
        raise CandidateError(f"{label} directory is missing: {path}")
    payloads: dict[str, bytes] = {}
    for member in sorted(path.rglob("*")):
        relative = member.relative_to(path)
        if member.is_symlink():
            raise CandidateError(f"{label} contains symbolic link: {relative.as_posix()}")
        if member.is_dir():
            continue
        if not member.is_file():
            raise CandidateError(f"{label} contains unsupported entry: {relative.as_posix()}")
        if "__pycache__" in relative.parts or member.suffix in {".pyc", ".pyo"}:
            continue
        payloads[relative.as_posix()] = member.read_bytes()
    if not payloads:
        raise CandidateError(f"{label} contains no stable files")
    files: list[dict[str, object]] = [
        {"path": relative, "sha256": _digest(payload), "size": len(payload)}
        for relative, payload in sorted(payloads.items())
    ]
    return payloads, files, _digest(_canonical(files))


def _changed_paths(baseline: dict[str, bytes], candidate: dict[str, bytes]) -> list[str]:
    return sorted(
        path
        for path in set(baseline) | set(candidate)
        if baseline.get(path) != candidate.get(path)
    )


def _within(path: str, boundaries: list[str]) -> bool:
    return any(
        path == boundary or path.startswith(boundary + "/")
        for boundary in boundaries
    )


def _check_execution(value: object) -> dict[str, Any]:
    execution = _exact(value, "execution", {"protocol", "command"})
    if execution["protocol"] != PROTOCOL:
        raise CandidateError(
            f"execution.protocol is {execution['protocol']!r}; use exactly {PROTOCOL!r}"
        )
    command = execution["command"]
    if type(command) is not list or not command:
        raise CandidateError("execution.command must be a nonempty argument array")
    for index, argument in enumerate(command):
        if type(argument) is not str or not argument:
            raise CandidateError(
                f"execution.command[{index}] is {argument!r}; use a nonempty string argument"
            )
        if argument in PLACEHOLDERS:
            continue
        if "{" in argument or "}" in argument:
            raise CandidateError(
                f"execution.command[{index}] is {argument!r}; allowed placeholders are "
                f"{sorted(PLACEHOLDERS)} and must be exact whole arguments"
            )
        if PurePath(argument).is_absolute():
            raise CandidateError(
                f"execution.command[{index}] is absolute path {argument!r}; "
                "use an allowed placeholder or safe relative literal"
            )
        marker = next((item for item in SHELL_MARKERS if item in argument), None)
        if marker is not None:
            raise CandidateError(
                f"execution.command[{index}] contains forbidden shell marker {marker!r}; "
                "use separate safe literal arguments"
            )
        if index == 0 and any(character.isspace() for character in argument):
            raise CandidateError(
                f"execution.command[0] is shell-like string {argument!r}; "
                "supply the executable and every argument as separate array items"
            )
    if "{candidate-entrypoint}" not in command:
        raise CandidateError(
            "execution.command omits '{candidate-entrypoint}'; include it as one exact argument"
        )
    return execution


def _find_probe(
    manifest: dict[str, Any], probe_id: str, approach_id: str
) -> dict[str, Any]:
    probe = next(
        (item for item in manifest["mini_probes"] if item["id"] == probe_id),
        None,
    )
    if probe is None:
        raise CandidateError(
            f"probe_id {probe_id!r} is not declared by the development manifest"
        )
    if not any(item["id"] == approach_id for item in probe["approaches"]):
        raise CandidateError(
            f"approach_id {approach_id!r} is not declared by mini-probe {probe_id!r}"
        )
    return probe


def _check_bundle_shape(bundle: object, manifest: dict[str, Any]) -> dict[str, Any]:
    root = _exact(
        bundle,
        "bundle",
        {"schema_version", "identity", "source", "execution", "inputs", "evaluation"},
    )
    if type(root["schema_version"]) is not int or root["schema_version"] != CONTRACT:
        raise CandidateError(f"bundle.schema_version must be integer {CONTRACT}")
    identity = _exact(
        root["identity"],
        "bundle.identity",
        {"atomic_step_id", "probe_id", "approach_id", "development_manifest_sha256"},
    )
    for name in ("atomic_step_id", "probe_id", "approach_id"):
        _identifier(identity[name], f"bundle.identity.{name}")
    _digest_field(
        identity["development_manifest_sha256"],
        "bundle.identity.development_manifest_sha256",
    )
    actual_manifest_digest = _digest(_canonical(manifest))
    if identity["development_manifest_sha256"] != actual_manifest_digest:
        raise CandidateError(
            "bundle identity changed from the supplied development manifest digest"
        )
    if identity["atomic_step_id"] != manifest["atomic_step"]["id"]:
        raise CandidateError("bundle atomic_step_id is not declared by the development manifest")
    probe = _find_probe(manifest, identity["probe_id"], identity["approach_id"])

    source = _exact(
        root["source"],
        "bundle.source",
        {
            "baseline_sha256",
            "candidate_sha256",
            "root",
            "entrypoint",
            "baseline_files",
            "files",
            "changed_paths",
        },
    )
    _digest_field(source["baseline_sha256"], "bundle.source.baseline_sha256")
    _digest_field(source["candidate_sha256"], "bundle.source.candidate_sha256")
    if source["root"] != "source":
        raise CandidateError("bundle.source.root must be exactly 'source'")
    _relative(source["entrypoint"], "bundle.source.entrypoint")
    recorded_paths: dict[str, list[str]] = {}
    for field in ("baseline_files", "files"):
        records = source[field]
        if type(records) is not list or not records:
            raise CandidateError(f"bundle.source.{field} must be a nonempty list")
        paths: list[str] = []
        for index, value in enumerate(records):
            item = _exact(
                value,
                f"bundle.source.{field}[{index}]",
                {"path", "sha256", "size"},
            )
            path = _relative(item["path"], f"bundle.source.{field}[{index}].path")
            if path in paths:
                raise CandidateError(f"bundle.source.{field} repeats path {path!r}")
            paths.append(path)
            _digest_field(item["sha256"], f"bundle.source.{field}[{index}].sha256")
            if type(item["size"]) is not int or item["size"] < 0:
                raise CandidateError(
                    f"bundle.source.{field}[{index}].size must be a nonnegative integer"
                )
        if paths != sorted(paths):
            raise CandidateError(f"bundle.source.{field} must be sorted by path")
        recorded_paths[field] = paths
    paths = recorded_paths["files"]
    if source["entrypoint"] not in paths:
        raise CandidateError("bundle source entrypoint is absent from recorded files")
    baseline_by_path = {item["path"]: item for item in source["baseline_files"]}
    candidate_by_path = {item["path"]: item for item in source["files"]}
    actual_baseline_sha256 = _digest(_canonical(source["baseline_files"]))
    if source["baseline_sha256"] != actual_baseline_sha256:
        raise CandidateError(
            "bundle.source.baseline_files differ from the recorded baseline tree digest"
        )
    derived_changes = sorted(
        path
        for path in set(baseline_by_path) | set(candidate_by_path)
        if baseline_by_path.get(path) != candidate_by_path.get(path)
    )
    changed_paths = source["changed_paths"]
    if type(changed_paths) is not list or changed_paths != derived_changes:
        raise CandidateError(
            f"bundle.source.changed_paths must be exact sorted delta {derived_changes!r}"
        )
    outside = [
        path for path in changed_paths if not _within(path, probe["allowed_paths"])
    ]
    if outside:
        raise CandidateError(
            f"candidate changed paths {outside!r} outside mini-probe "
            f"{identity['probe_id']!r} allowed_paths {probe['allowed_paths']!r}; "
            "change only declared paths"
        )
    _check_execution(root["execution"])

    inputs = _exact(root["inputs"], "bundle.inputs", {"case_ids"})
    if type(inputs["case_ids"]) is not list:
        raise CandidateError("bundle.inputs.case_ids must be a list")
    for index, case_id in enumerate(inputs["case_ids"]):
        _identifier(case_id, f"bundle.inputs.case_ids[{index}]")
    expected_cases = [item["case_id"] for item in probe["inputs"]]
    if inputs["case_ids"] != expected_cases:
        raise CandidateError(
            f"bundle input cases are {inputs['case_ids']!r}; use declared cases {expected_cases!r}"
        )

    evaluation = _exact(root["evaluation"], "bundle.evaluation", {"metrics"})
    if type(evaluation["metrics"]) is not list or not evaluation["metrics"]:
        raise CandidateError("bundle.evaluation.metrics must be a nonempty list")
    for index, value in enumerate(evaluation["metrics"]):
        metric = _exact(value, f"bundle.evaluation.metrics[{index}]", {"name", "direction"})
        _identifier(metric["name"], f"bundle.evaluation.metrics[{index}].name")
        if metric["direction"] not in {"maximize", "minimize"}:
            raise CandidateError(
                f"bundle.evaluation.metrics[{index}].direction must be maximize or minimize"
            )
    if evaluation["metrics"] != probe["evaluation"]["metrics"]:
        raise CandidateError("bundle evaluation metrics differ from the declared ordered metrics")
    return root


def _check_source_integrity(bundle_root: Path, source: dict[str, Any]) -> None:
    source_root = bundle_root / "source"
    if source_root.is_symlink():
        raise CandidateError("candidate source root must not be a symbolic link")
    _, actual, tree_digest = _snapshot_source(source_root, "candidate source")
    recorded = source["files"]
    actual_by_path = {item["path"]: item for item in actual}
    recorded_by_path = {item["path"]: item for item in recorded}
    missing = sorted(set(recorded_by_path) - set(actual_by_path))
    extra = sorted(set(actual_by_path) - set(recorded_by_path))
    if missing:
        raise CandidateError(f"candidate source is missing recorded files: {missing}")
    if extra:
        raise CandidateError(f"candidate source contains extra files: {extra}")
    for path, expected in recorded_by_path.items():
        observed = actual_by_path[path]
        if expected["size"] != observed["size"]:
            raise CandidateError(f"candidate file size changed for {path}")
        if expected["sha256"] != observed["sha256"]:
            raise CandidateError(f"candidate file hash changed for {path}")
    if source["candidate_sha256"] != tree_digest:
        raise CandidateError("candidate source tree digest changed")


def _bundle_digest(bundle: dict[str, Any], manifest: dict[str, Any]) -> str:
    return _digest(_canonical({"bundle": bundle, "development_manifest": manifest}))


def _check_read_only(bundle_root: Path) -> None:
    for path in [bundle_root, *bundle_root.rglob("*")]:
        if path.stat().st_mode & 0o222:
            raise CandidateError(f"candidate bundle entry is writable: {path.relative_to(bundle_root)}")


def verify_bundle(bundle_root: Path) -> tuple[dict[str, Any], dict[str, Any], str]:
    if bundle_root.is_symlink() or not bundle_root.is_dir():
        raise CandidateError(f"candidate bundle is not a stable directory: {bundle_root}")
    linked = [path.relative_to(bundle_root) for path in bundle_root.rglob("*") if path.is_symlink()]
    if linked:
        raise CandidateError(f"candidate bundle contains symbolic links: {linked}")
    actual_entries = {path.name for path in bundle_root.iterdir()}
    if actual_entries != BUNDLE_ENTRIES:
        raise CandidateError(
            f"candidate bundle entries are {sorted(actual_entries)}; expected {sorted(BUNDLE_ENTRIES)}"
        )
    manifest = _load_canonical_json(
        bundle_root / "development-manifest.json", "development manifest copy"
    )
    try:
        manifest = validate_manifest(manifest)
    except ManifestError as error:
        raise CandidateError(f"development manifest copy is invalid: {error}") from None
    bundle = _load_canonical_json(bundle_root / "bundle.json", "bundle manifest")
    bundle = _check_bundle_shape(bundle, manifest)
    _check_source_integrity(bundle_root, bundle["source"])
    _check_read_only(bundle_root)
    return bundle, manifest, _bundle_digest(bundle, manifest)


def _write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    path.chmod(0o444)


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


def build_bundle(request_path: Path, output: Path) -> dict[str, object]:
    request = _exact(
        _load_json(request_path, "candidate build request"),
        "candidate build request",
        {
            "schema_version",
            "development_manifest",
            "probe_id",
            "approach_id",
            "source",
            "execution",
        },
    )
    if type(request["schema_version"]) is not int or request["schema_version"] != CONTRACT:
        raise CandidateError(f"candidate build request schema_version must be integer {CONTRACT}")
    base = request_path.resolve().parent
    manifest_path = _resolve_path(
        request["development_manifest"], base, "development_manifest"
    )
    manifest_value = _load_json(manifest_path, "development manifest")
    try:
        manifest = validate_manifest(manifest_value)
    except ManifestError as error:
        raise CandidateError(f"development manifest is invalid: {error}") from None
    probe_id = _identifier(request["probe_id"], "probe_id")
    approach_id = _identifier(request["approach_id"], "approach_id")
    probe = _find_probe(manifest, probe_id, approach_id)
    source = _exact(
        request["source"],
        "candidate build request source",
        {"baseline", "candidate", "entrypoint"},
    )
    baseline_path = _resolve_path(source["baseline"], base, "source.baseline")
    candidate_path = _resolve_path(source["candidate"], base, "source.candidate")
    entrypoint = _relative(source["entrypoint"], "source.entrypoint")
    baseline_payloads, baseline_files, baseline_sha256 = _snapshot_source(
        baseline_path, "baseline source"
    )
    payloads, files, candidate_sha256 = _snapshot_source(candidate_path, "candidate source")
    changed_paths = _changed_paths(baseline_payloads, payloads)
    outside = [
        path for path in changed_paths if not _within(path, probe["allowed_paths"])
    ]
    if outside:
        raise CandidateError(
            f"candidate changed paths {outside!r} outside mini-probe {probe_id!r} "
            f"allowed_paths {probe['allowed_paths']!r}; change only declared paths"
        )
    if entrypoint not in payloads:
        raise CandidateError(f"source.entrypoint {entrypoint!r} is absent from candidate source")
    execution = _check_execution(request["execution"])
    bundle = {
        "schema_version": CONTRACT,
        "identity": {
            "atomic_step_id": manifest["atomic_step"]["id"],
            "probe_id": probe_id,
            "approach_id": approach_id,
            "development_manifest_sha256": _digest(_canonical(manifest)),
        },
        "source": {
            "baseline_sha256": baseline_sha256,
            "candidate_sha256": candidate_sha256,
            "root": "source",
            "entrypoint": entrypoint,
            "baseline_files": baseline_files,
            "files": files,
            "changed_paths": changed_paths,
        },
        "execution": execution,
        "inputs": {"case_ids": [item["case_id"] for item in probe["inputs"]]},
        "evaluation": {"metrics": probe["evaluation"]["metrics"]},
    }
    _check_bundle_shape(bundle, manifest)
    output = output.resolve()
    if output.exists():
        raise CandidateError(f"candidate bundle output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        _write(temporary / "development-manifest.json", _document(manifest))
        _write(temporary / "bundle.json", _document(bundle))
        source_root = temporary / "source"
        source_root.mkdir()
        for relative, payload in sorted(payloads.items()):
            _write(source_root / relative, payload)
        _make_read_only(temporary)
        temporary.rename(output)
    except Exception:
        _restore_writable(temporary)
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    verified, _, bundle_sha256 = verify_bundle(output)
    return {
        "status": "built",
        "atomic_step_id": verified["identity"]["atomic_step_id"],
        "probe_id": probe_id,
        "approach_id": approach_id,
        "bundle_sha256": bundle_sha256,
    }


def _environment_path(name: str) -> Path:
    value = os.environ.get(name)
    if not value:
        raise CandidateError(f"Experiment Machinery did not provide {name}")
    return Path(value).resolve()


def _append_telemetry(path: Path, bundle_sha256: str, status: str) -> None:
    record = {
        "schema_version": CONTRACT,
        "event": "candidate_bundle_verified",
        "recorded_at": datetime.now(UTC).isoformat(),
        "variant_id": os.environ.get("EXPERIMENT_VARIANT_ID"),
        "bundle_sha256": bundle_sha256,
        "status": status,
    }
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def execute_bundle(bundle_root: Path) -> int:
    bundle_root = bundle_root.absolute()
    bundle, manifest, bundle_sha256 = verify_bundle(bundle_root)
    variant_path = _environment_path("EXPERIMENT_VARIANT_PATH")
    variant = _exact(
        _load_json(variant_path, "experiment variant configuration"),
        "experiment variant configuration",
        {"schema_version", "variant_id", "configuration"},
    )
    if type(variant["schema_version"]) is not int or variant["schema_version"] != CONTRACT:
        raise CandidateError("experiment variant schema_version must be integer 1")
    if variant["variant_id"] != os.environ.get("EXPERIMENT_VARIANT_ID"):
        raise CandidateError("experiment variant identity differs from the active variant")
    configuration = _exact(
        variant["configuration"], "experiment variant configuration.configuration", {"case_id"}
    )
    case_id = _identifier(configuration["case_id"], "configuration.case_id")
    if case_id not in bundle["inputs"]["case_ids"]:
        raise CandidateError(
            f"configuration.case_id {case_id!r} is undeclared for this candidate bundle"
        )
    case = next(
        item for item in manifest["atomic_step"]["captured_cases"] if item["id"] == case_id
    )
    frozen_input = _environment_path("EXPERIMENT_INPUT_PATH")
    if not frozen_input.is_file():
        raise CandidateError(f"Experiment Machinery frozen input is missing: {frozen_input}")
    actual_input_sha256 = _digest(frozen_input.read_bytes())
    if actual_input_sha256 != case["sha256"]:
        raise CandidateError(
            f"frozen input does not match declared case {case_id!r}: "
            f"expected {case['sha256']}, actual {actual_input_sha256}"
        )
    result_path = _environment_path("EXPERIMENT_RESULT_PATH")
    telemetry_path = _environment_path("EXPERIMENT_TELEMETRY_PATH")
    work_dir = _environment_path("EXPERIMENT_WORK_DIR")
    replacements = {
        "{python}": sys.executable,
        "{candidate-entrypoint}": str(
            bundle_root / bundle["source"]["root"] / bundle["source"]["entrypoint"]
        ),
        "{frozen-input}": str(frozen_input),
        "{result-path}": str(result_path),
        "{telemetry-path}": str(telemetry_path),
    }
    command = [replacements.get(argument, argument) for argument in bundle["execution"]["command"]]
    completed = subprocess.run(command, cwd=work_dir, env=os.environ.copy(), check=False)
    try:
        _, _, after_sha256 = verify_bundle(bundle_root)
    except CandidateError:
        _append_telemetry(telemetry_path, bundle_sha256, "changed-during-execution")
        raise
    if after_sha256 != bundle_sha256:
        _append_telemetry(telemetry_path, bundle_sha256, "changed-during-execution")
        raise CandidateError("candidate bundle digest changed during execution")
    _append_telemetry(telemetry_path, bundle_sha256, "unchanged")
    return int(completed.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="create one write-once candidate bundle")
    build.add_argument("request", type=Path)
    build.add_argument("output", type=Path)
    verify = subparsers.add_parser("verify", help="verify one candidate bundle")
    verify.add_argument("bundle", type=Path)
    execute = subparsers.add_parser("execute", help="execute a verified bundle as one variant")
    execute.add_argument("bundle", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "build":
            result = build_bundle(args.request, args.output)
        elif args.command == "verify":
            bundle, _, bundle_sha256 = verify_bundle(args.bundle.absolute())
            result = {
                "status": "verified",
                "atomic_step_id": bundle["identity"]["atomic_step_id"],
                "probe_id": bundle["identity"]["probe_id"],
                "approach_id": bundle["identity"]["approach_id"],
                "bundle_sha256": bundle_sha256,
            }
        else:
            return execute_bundle(args.bundle)
    except (CandidateError, OSError, subprocess.SubprocessError) as error:
        print(f"Development-probe candidate refused: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
