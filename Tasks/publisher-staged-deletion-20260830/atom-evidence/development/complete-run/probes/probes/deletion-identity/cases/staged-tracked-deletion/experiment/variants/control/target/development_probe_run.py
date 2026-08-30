#!/usr/bin/env python3
"""Run one complete Development-Probe process from experiments to verdict."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

from development_probe_candidate import CandidateError, _snapshot_source
from development_probe_compose import CompositionError, verify_assembly
from development_probe_final_validation import FinalValidationError, _assessment_contract
from development_probe_manifest import ManifestError, validate_manifest

CONTRACT = 1
STAGES = ["run-probes", "compose-winners", "final-validation"]
BASE_STAGE_TIMEOUT_MS = {
    "run-probes": 2_700_000,
    "compose-winners": 600_000,
    "final-validation": 2_700_000,
}
STAGE_CONCURRENCY = 4
TERMINATION_GRACE_SECONDS = 0.25
VERDICTS = {"passed", "failed", "inconclusive"}
FINAL_FIELDS = {
    "schema_version",
    "status",
    "atomic_step_id",
    "assembly_sha256",
    "verdict",
    "cases",
    "promotion_applied",
}


class DevelopmentProbeRunError(RuntimeError):
    """The complete Development-Probe process cannot safely continue."""

    def __init__(self, stage: str, message: str, receipt: str | None = None) -> None:
        super().__init__(message)
        self.stage = stage
        self.receipt = receipt


def _document(value: object) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _load(path: Path, label: str, stage: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DevelopmentProbeRunError(stage, f"{label} is unavailable or invalid JSON: {error}") from None
    if type(value) is not dict:
        raise DevelopmentProbeRunError(stage, f"{label} is {type(value).__name__}; provide one JSON object")
    return value


def _exact(value: object, label: str, fields: set[str], stage: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise DevelopmentProbeRunError(
            stage,
            f"{label} is {type(value).__name__}; provide one object with fields {sorted(fields)}",
        )
    missing = sorted(fields - value.keys())
    extra = sorted(value.keys() - fields)
    if missing or extra:
        raise DevelopmentProbeRunError(
            stage,
            f"{label} has missing fields {missing} and unexpected fields {extra}; "
            "add the missing fields and remove the unexpected fields",
        )
    return value


def _write_json(path: Path, value: object) -> str:
    payload = _document(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return _digest(payload)


def _write_bytes(path: Path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return _digest(payload)


def _resolve(value: object, base: Path, label: str) -> Path:
    if type(value) is not str or not value:
        raise DevelopmentProbeRunError("validate-request", f"{label} is {value!r}; provide one nonempty path")
    path = Path(value)
    return (path if path.is_absolute() else base / path).absolute()


def _file_record(value: object, base: Path, label: str) -> tuple[Path, dict[str, str]]:
    item = _exact(value, label, {"path", "sha256"}, "validate-request")
    path = _resolve(item["path"], base, f"{label}.path")
    expected = item["sha256"]
    if (
        type(expected) is not str
        or len(expected) != 64
        or any(character not in "0123456789abcdef" for character in expected)
    ):
        raise DevelopmentProbeRunError(
            "validate-request",
            f"{label}.sha256 is {expected!r}; provide 64 lowercase hexadecimal characters",
        )
    if path.is_symlink() or not path.is_file():
        raise DevelopmentProbeRunError("validate-request", f"{label}.path is {path}; provide one stable regular file")
    actual = _digest(path.read_bytes())
    if actual != expected:
        raise DevelopmentProbeRunError(
            "validate-request",
            f"{label} at {path} has SHA-256 {actual}; update the request to {actual} "
            "or restore the expected immutable bytes",
        )
    return path, {"path": str(path), "sha256": actual}


def _baseline_record(value: object, base: Path) -> tuple[Path, dict[str, str]]:
    item = _exact(value, "baseline", {"path", "sha256"}, "validate-request")
    path = _resolve(item["path"], base, "baseline.path")
    expected = item["sha256"]
    if type(expected) is not str:
        raise DevelopmentProbeRunError(
            "validate-request", f"baseline.sha256 is {expected!r}; provide the source-tree SHA-256"
        )
    try:
        _, _, actual = _snapshot_source(path, "baseline")
    except CandidateError as error:
        raise DevelopmentProbeRunError("validate-request", str(error)) from None
    if actual != expected:
        raise DevelopmentProbeRunError(
            "validate-request",
            f"baseline at {path} has source-tree SHA-256 {actual}; update the request to {actual} "
            "or restore the expected immutable source",
        )
    return path, {"path": str(path), "sha256": actual}


def _stage_timeouts(manifest: dict[str, Any]) -> dict[str, int]:
    probe_waves = max(1, (len(manifest["mini_probes"]) + STAGE_CONCURRENCY - 1) // STAGE_CONCURRENCY)
    largest_probe_case_count = max(len(probe["inputs"]) for probe in manifest["mini_probes"])
    probe_case_waves = max(1, (largest_probe_case_count + STAGE_CONCURRENCY - 1) // STAGE_CONCURRENCY)
    final_case_count = len(manifest["composition"]["final_validation"]["case_ids"])
    final_case_waves = max(1, (final_case_count + STAGE_CONCURRENCY - 1) // STAGE_CONCURRENCY)
    return {
        "run-probes": BASE_STAGE_TIMEOUT_MS["run-probes"] * probe_waves * probe_case_waves,
        "compose-winners": BASE_STAGE_TIMEOUT_MS["compose-winners"],
        "final-validation": BASE_STAGE_TIMEOUT_MS["final-validation"] * final_case_waves,
    }


def _normalize_request(request_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    request = _exact(
        _load(request_path, "development-probe request", "validate-request"),
        "development-probe request",
        {
            "schema_version",
            "development_manifest",
            "baseline",
            "probe_requests",
            "assessment",
        },
        "validate-request",
    )
    if request["schema_version"] != CONTRACT or type(request["schema_version"]) is not int:
        raise DevelopmentProbeRunError("validate-request", "development-probe request schema_version must be integer 1")
    base = request_path.parent
    manifest_path, manifest_record = _file_record(request["development_manifest"], base, "development_manifest")
    try:
        manifest = validate_manifest(_load(manifest_path, "development manifest", "validate-request"))
    except ManifestError as error:
        raise DevelopmentProbeRunError("validate-request", f"development manifest is invalid: {error}") from None
    baseline_path, baseline_record = _baseline_record(request["baseline"], base)
    supplied = request["probe_requests"]
    if type(supplied) is not list:
        raise DevelopmentProbeRunError(
            "validate-request",
            f"probe_requests is {type(supplied).__name__}; provide one list with exactly one request per probe",
        )
    accepted = []
    for index, raw in enumerate(supplied):
        item = _exact(
            raw,
            f"probe_requests[{index}]",
            {"probe_id", "request", "request_sha256"},
            "validate-request",
        )
        probe_id = item["probe_id"]
        if type(probe_id) is not str or not probe_id:
            raise DevelopmentProbeRunError(
                "validate-request",
                f"probe_requests[{index}].probe_id is {probe_id!r}; provide a declared nonempty probe id",
            )
        request_file, record = _file_record(
            {"path": item["request"], "sha256": item["request_sha256"]},
            base,
            f"probe_requests[{index}].request",
        )
        accepted.append({"probe_id": probe_id, "request": request_file, **record})
    declared = [probe["id"] for probe in manifest["mini_probes"]]
    counts = Counter(item["probe_id"] for item in accepted)
    missing = [probe_id for probe_id in declared if counts[probe_id] == 0]
    duplicate = sorted(probe_id for probe_id, count in counts.items() if count > 1)
    unknown = sorted(probe_id for probe_id in counts if probe_id not in set(declared))
    problems = []
    if missing:
        problems.append(f"missing probe ids {missing!r}; add exactly one request for each")
    if duplicate:
        problems.append(f"duplicate probe ids {duplicate!r}; keep exactly one request for each")
    if unknown:
        problems.append(f"unknown probe ids {unknown!r}; remove them; declared ids are {declared!r}")
    if problems:
        raise DevelopmentProbeRunError("validate-request", "probe_requests " + "; ".join(problems))
    indexed = {item["probe_id"]: item for item in accepted}
    assessment = _exact(request["assessment"], "assessment", {"adapter", "command"}, "validate-request")
    adapter_path, adapter_record = _file_record(assessment["adapter"], base, "assessment.adapter")
    command = assessment["command"]
    try:
        _, normalized_command, adapter_sha256 = _assessment_contract(
            {"adapter": str(adapter_path), "command": command}, base
        )
    except FinalValidationError as error:
        raise DevelopmentProbeRunError("validate-request", str(error)) from None
    if normalized_command[:2] != ["{python}", "{assessment-adapter}"]:
        raise DevelopmentProbeRunError(
            "validate-request",
            f"assessment.command begins {normalized_command[:2]!r}; begin with "
            "['{python}', '{assessment-adapter}'] so code controls model invocation",
        )
    if adapter_sha256 != adapter_record["sha256"]:
        raise DevelopmentProbeRunError(
            "validate-request", "assessment.adapter changed while its request was being normalized"
        )
    ordered_probes = [
        {
            "probe_id": probe_id,
            "request": str(indexed[probe_id]["request"]),
            "request_sha256": indexed[probe_id]["sha256"],
        }
        for probe_id in declared
    ]
    normalized = {
        "schema_version": CONTRACT,
        "atomic_step_id": manifest["atomic_step"]["id"],
        "development_manifest": manifest_record,
        "baseline": baseline_record,
        "probe_requests": ordered_probes,
        "assessment": {
            "adapter": adapter_record,
            "command": normalized_command,
        },
        "promotion_applied": False,
    }
    paths = {
        "manifest": manifest_path,
        "baseline": baseline_path,
        "adapter": adapter_path,
        "stage_timeouts": _stage_timeouts(manifest),
    }
    return normalized, paths


def _prepare_output(output: Path) -> None:
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise DevelopmentProbeRunError("prepare-output", f"output must be a new or empty directory: {output}")
    output.mkdir(parents=True, exist_ok=True)


def _stage_paths(output: Path, stage: str) -> tuple[Path, Path, Path]:
    if stage == "run-probes":
        return (
            output / "probes",
            output / "probes" / "all-probes-summary.json",
            output / "probes" / "promotion-candidates.json",
        )
    if stage == "compose-winners":
        return (
            output / "composition",
            output / "composition" / "composition-summary.json",
            output / "composition" / "assembly" / "assembly.json",
        )
    return (
        output / "validation",
        output / "validation" / "final-validation-summary.json",
        output / "validation" / "final-verdict.json",
    )


def _signal_process_group(process: subprocess.Popen[str], selected_signal: signal.Signals) -> None:
    try:
        os.killpg(process.pid, selected_signal)
    except (ProcessLookupError, PermissionError):
        if process.poll() is None:
            if selected_signal == signal.SIGTERM:
                process.terminate()
            else:
                process.kill()


def _merge_partial(partial: str | bytes | None, complete: str) -> str:
    value = partial.decode() if isinstance(partial, bytes) else (partial or "")
    return complete if not value or value in complete else value + complete


def _run_stage(
    output: Path,
    stage: str,
    command: list[str],
    timeout_ms: int | None = None,
) -> dict[str, Any]:
    stage_output, evidence_path, result_path = _stage_paths(output, stage)
    deadline_ms = BASE_STAGE_TIMEOUT_MS[stage] if timeout_ms is None else timeout_ms
    if type(deadline_ms) is not int or deadline_ms <= 0:
        raise DevelopmentProbeRunError(
            stage,
            f"stage {stage!r} timeout is {deadline_ms!r}; require one positive integer millisecond deadline",
        )
    started_ns = time.monotonic_ns()
    process = subprocess.Popen(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=deadline_ms / 1000)
    except subprocess.TimeoutExpired as error:
        timed_out = True
        _signal_process_group(process, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=TERMINATION_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            _signal_process_group(process, signal.SIGKILL)
            stdout, stderr = process.communicate()
        stdout = _merge_partial(error.stdout, stdout)
        stderr = _merge_partial(error.stderr, stderr)
    duration_ms = (time.monotonic_ns() - started_ns) // 1_000_000
    receipt_root = output / "stage-receipts" / stage
    stdout_path = receipt_root / "stdout.txt"
    stderr_path = receipt_root / "stderr.txt"
    stdout_sha256 = _write_bytes(stdout_path, stdout.encode("utf-8"))
    stderr_sha256 = _write_bytes(stderr_path, stderr.encode("utf-8"))
    evidence_sha256 = _digest(evidence_path.read_bytes()) if evidence_path.is_file() else None
    result_sha256 = _digest(result_path.read_bytes()) if result_path.is_file() else None
    timeout_path = receipt_root / "timeout.json"
    timeout_sha256 = None
    if timed_out:
        timeout_sha256 = _write_json(
            timeout_path,
            {
                "schema_version": CONTRACT,
                "stage": stage,
                "status": "timed-out",
                "timeout_ms": deadline_ms,
                "duration_ms": duration_ms,
                "exit_code": process.returncode,
                "stdout_sha256": stdout_sha256,
                "stderr_sha256": stderr_sha256,
            },
        )
    receipt = {
        "schema_version": CONTRACT,
        "stage": stage,
        "status": "timed-out" if timed_out else ("completed" if process.returncode == 0 else "failed"),
        "exit_code": process.returncode,
        "duration_ms": duration_ms,
        "timeout_ms": deadline_ms,
        "timed_out": timed_out,
        "output": str(stage_output.relative_to(output)),
        "evidence": str(evidence_path.relative_to(output)) if evidence_sha256 else None,
        "evidence_sha256": evidence_sha256,
        "result": str(result_path.relative_to(output)) if result_sha256 else None,
        "result_sha256": result_sha256,
        "stdout_sha256": stdout_sha256,
        "stderr_sha256": stderr_sha256,
        "timeout": str(timeout_path.relative_to(output)) if timeout_sha256 else None,
        "timeout_sha256": timeout_sha256,
        "promotion_applied": False,
    }
    receipt_path = receipt_root / "receipt.json"
    _write_json(receipt_path, receipt)
    if timed_out:
        relative_receipt = str(receipt_path.relative_to(output))
        raise DevelopmentProbeRunError(
            stage,
            f"stage {stage!r} exceeded its controller-owned {deadline_ms} ms deadline; "
            f"inspect {relative_receipt}",
            relative_receipt,
        )
    if process.returncode != 0:
        detail = stderr.strip() or stdout.strip() or "stage returned no diagnostic"
        relative_receipt = str(receipt_path.relative_to(output))
        raise DevelopmentProbeRunError(
            stage,
            f"stage {stage!r} failed: {detail}; inspect {relative_receipt}",
            relative_receipt,
        )
    if evidence_sha256 is None or result_sha256 is None:
        relative_receipt = str(receipt_path.relative_to(output))
        raise DevelopmentProbeRunError(
            stage,
            f"stage {stage!r} exited successfully but omitted its evidence or result; inspect {relative_receipt}",
            relative_receipt,
        )
    evidence = _load(evidence_path, f"{stage} evidence", stage)
    if evidence.get("status") != "completed" or evidence.get("promotion_applied") is not False:
        relative_receipt = str(receipt_path.relative_to(output))
        raise DevelopmentProbeRunError(
            stage,
            f"stage {stage!r} evidence reports status {evidence.get('status')!r} and "
            f"promotion_applied {evidence.get('promotion_applied')!r}; require completed and false; "
            f"inspect {relative_receipt}",
            relative_receipt,
        )
    return receipt


def _bind_final_result(output: Path, normalized: dict[str, Any], final_receipt: dict[str, Any]) -> dict[str, Any]:
    result_path = output / final_receipt["result"]
    payload = result_path.read_bytes()
    actual = _digest(payload)
    expected = final_receipt["result_sha256"]
    if actual != expected:
        raise DevelopmentProbeRunError(
            "bind-verdict",
            f"final verdict artifact has SHA-256 {actual}; require recorded {expected}; "
            "restore the exact final-validation result",
        )
    verdict = _exact(
        _load(result_path, "final verdict artifact", "bind-verdict"),
        "final verdict artifact",
        FINAL_FIELDS,
        "bind-verdict",
    )
    try:
        assembly, _, assembly_sha256 = verify_assembly(output / "composition" / "assembly")
    except (CompositionError, OSError) as error:
        raise DevelopmentProbeRunError("bind-verdict", f"assembled candidate no longer verifies: {error}") from None
    problems = []
    if verdict["schema_version"] != CONTRACT or type(verdict["schema_version"]) is not int:
        problems.append(f"schema_version is {verdict['schema_version']!r}; require integer 1")
    if verdict["status"] != "completed":
        problems.append(f"status is {verdict['status']!r}; require 'completed'")
    if verdict["atomic_step_id"] != normalized["atomic_step_id"]:
        problems.append(f"atomic_step_id is {verdict['atomic_step_id']!r}; require {normalized['atomic_step_id']!r}")
    if verdict["atomic_step_id"] != assembly["identity"]["atomic_step_id"]:
        problems.append("atomic_step_id does not match the freshly verified assembly")
    if verdict["assembly_sha256"] != assembly_sha256:
        problems.append(f"assembly_sha256 is {verdict['assembly_sha256']!r}; require verified {assembly_sha256!r}")
    if verdict["verdict"] not in VERDICTS:
        problems.append(f"verdict is {verdict['verdict']!r}; require one of {sorted(VERDICTS)}")
    if type(verdict["cases"]) is not list:
        problems.append(f"cases is {type(verdict['cases']).__name__}; require one ordered list")
    if verdict["promotion_applied"] is not False:
        problems.append(
            f"promotion_applied is {verdict['promotion_applied']!r}; require false because this launcher never promotes"
        )
    if problems:
        raise DevelopmentProbeRunError("bind-verdict", "final verdict " + "; ".join(problems))
    if _digest(result_path.read_bytes()) != expected:
        raise DevelopmentProbeRunError(
            "bind-verdict", "final verdict artifact changed while its identity was being bound"
        )
    _write_bytes(output / "final-verdict.json", payload)
    return verdict


def _receipts(output: Path) -> list[dict[str, Any]]:
    records = []
    for stage in STAGES:
        path = output / "stage-receipts" / stage / "receipt.json"
        if path.is_file():
            records.append(_load(path, f"{stage} receipt", "record-summary"))
    return records


def run(request_path: Path, output: Path) -> dict[str, Any]:
    request_path = request_path.absolute()
    output = output.absolute()
    _prepare_output(output)
    normalized, paths = _normalize_request(request_path)
    _write_json(output / "development-probe-request.json", normalized)
    request_root = output / "stage-requests"
    all_probe_request = {
        "schema_version": CONTRACT,
        "development_manifest": str(paths["manifest"]),
        "probe_requests": [
            {"probe_id": item["probe_id"], "request": item["request"]} for item in normalized["probe_requests"]
        ],
    }
    all_probe_path = request_root / "all-probes.json"
    _write_json(all_probe_path, all_probe_request)
    composition_path = request_root / "composition.json"
    _write_json(
        composition_path,
        {
            "schema_version": CONTRACT,
            "development_manifest": str(paths["manifest"]),
            "baseline": str(paths["baseline"]),
            "promotion_candidates": str(output / "probes" / "promotion-candidates.json"),
        },
    )
    final_path = request_root / "final-validation.json"
    _write_json(
        final_path,
        {
            "schema_version": CONTRACT,
            "assembly": str(output / "composition" / "assembly"),
            "assessment": {
                "adapter": str(paths["adapter"]),
                "command": normalized["assessment"]["command"],
            },
        },
    )
    scripts = Path(__file__).parent
    _run_stage(
        output,
        "run-probes",
        [
            sys.executable,
            str(scripts / "development_probe_all_probes.py"),
            "run",
            str(all_probe_path),
            str(output / "probes"),
        ],
        timeout_ms=paths["stage_timeouts"]["run-probes"],
    )
    _run_stage(
        output,
        "compose-winners",
        [
            sys.executable,
            str(scripts / "development_probe_compose.py"),
            "run",
            str(composition_path),
            str(output / "composition"),
        ],
        timeout_ms=paths["stage_timeouts"]["compose-winners"],
    )
    final_receipt = _run_stage(
        output,
        "final-validation",
        [
            sys.executable,
            str(scripts / "development_probe_final_validation.py"),
            "run",
            str(final_path),
            str(output / "validation"),
        ],
        timeout_ms=paths["stage_timeouts"]["final-validation"],
    )
    verdict = _bind_final_result(output, normalized, final_receipt)
    _write_json(
        output / "development-probe-summary.json",
        {
            "schema_version": CONTRACT,
            "status": "completed",
            "atomic_step_id": normalized["atomic_step_id"],
            "verdict": verdict["verdict"],
            "final_verdict_sha256": final_receipt["result_sha256"],
            "stages": _receipts(output),
            "promotion_applied": False,
        },
    )
    return verdict


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="run the complete Development-Probe process")
    run_parser.add_argument("request", type=Path)
    run_parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = args.output.absolute()
    try:
        verdict = run(args.request, output)
    except (DevelopmentProbeRunError, OSError, subprocess.SubprocessError) as error:
        stage = error.stage if isinstance(error, DevelopmentProbeRunError) else "runtime"
        receipt = error.receipt if isinstance(error, DevelopmentProbeRunError) else None
        if stage != "prepare-output" and output.is_dir() and not (output / "development-probe-summary.json").exists():
            try:
                _write_json(
                    output / "development-probe-summary.json",
                    {
                        "schema_version": CONTRACT,
                        "status": "failed",
                        "stage": stage,
                        "error": str(error),
                        "receipt": receipt,
                        "stages": _receipts(output),
                        "promotion_applied": False,
                    },
                )
            except OSError:
                pass
        print(f"Complete Development-Probe run refused at {stage}: {error}", file=sys.stderr)
        return 2
    print(json.dumps(verdict, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
