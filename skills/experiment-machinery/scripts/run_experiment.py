"""Run one frozen-input, isolated, parallel machinery experiment."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import re
import signal
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

CONTRACT = 1
SPEC_CONTRACT = 4
_IDENTITY = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ExperimentError(RuntimeError):
    """Raised when an experiment boundary is invalid."""


class EvaluatorTimeout(ExperimentError):
    """Raised after evaluator deadline evidence has been preserved."""

    def __init__(self, timeout_ms: int, evidence_sha256: str) -> None:
        super().__init__(f"independent evaluator exceeded its declared {timeout_ms} ms deadline")
        self.timeout_ms = timeout_ms
        self.evidence_sha256 = evidence_sha256


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest_file(path: Path) -> str:
    return _digest_bytes(path.read_bytes())


def _snapshot_source(path: Path) -> tuple[dict[str, bytes], str]:
    path = path.resolve()
    if not path.is_dir():
        raise ExperimentError(f"target source must be a directory: {path}")
    files: dict[str, bytes] = {}
    for member in sorted(path.rglob("*")):
        relative = member.relative_to(path)
        if member.is_symlink():
            raise ExperimentError(f"target source contains a symbolic link: {relative}")
        if member.is_dir():
            continue
        if not member.is_file():
            raise ExperimentError(f"target source contains an unsupported entry: {relative}")
        if "__pycache__" in relative.parts or member.suffix in {".pyc", ".pyo"}:
            continue
        files[relative.as_posix()] = member.read_bytes()
    if not files:
        raise ExperimentError(f"target source contains no stable files: {path}")
    manifest = [
        {"path": relative, "sha256": _digest_bytes(payload), "size": len(payload)}
        for relative, payload in sorted(files.items())
    ]
    return files, _digest_bytes(_canonical(manifest))


def _write_source_snapshot(root: Path, files: dict[str, bytes]) -> None:
    root.mkdir()
    directories = {root}
    for relative, payload in sorted(files.items()):
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        directories.update(destination.parents)
        _write_exclusive_bytes(destination, payload)
        destination.chmod(0o444)
    for directory in sorted(
        (path for path in directories if path == root or root in path.parents),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        directory.chmod(0o555)


def _load_object(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        payload = path.read_bytes()
        value = json.loads(payload)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ExperimentError(f"{label} is unavailable or invalid JSON: {error}") from error
    if not isinstance(value, dict):
        raise ExperimentError(f"{label} must be one JSON object")
    return value, payload


def _require_exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise ExperimentError(
            f"{label} fields are {sorted(actual)}; expected exactly {sorted(expected)}"
        )


def _require_identity(value: object, label: str) -> str:
    if not isinstance(value, str) or not _IDENTITY.fullmatch(value):
        raise ExperimentError(
            f"{label} must use 1-64 lowercase letters, digits, or hyphens and start alphanumeric"
        )
    return value


def _require_timeout_ms(value: object, label: str) -> int:
    if type(value) is not int or value < 1 or value > 86_400_000:
        raise ExperimentError(f"{label} must be an integer from 1 through 86400000")
    return value


def _validate_bound_file(value: object, spec_path: Path, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ExperimentError(f"{label} must be an object with path and sha256")
    _require_exact_keys(value, {"path", "sha256"}, label)
    raw_path = value.get("path")
    expected = value.get("sha256")
    if not isinstance(raw_path, str) or not raw_path:
        raise ExperimentError(f"{label}.path must be a non-empty string")
    if not isinstance(expected, str) or not _SHA256.fullmatch(expected):
        raise ExperimentError(f"{label}.sha256 must be 64 lowercase hexadecimal characters")
    path = Path(raw_path)
    if not path.is_absolute():
        path = spec_path.parent / path
    if path.is_symlink():
        raise ExperimentError(f"{label}.path must not be a symbolic link")
    try:
        path = path.resolve(strict=True)
    except OSError as error:
        raise ExperimentError(f"{label}.path is unavailable: {error}") from error
    if not path.is_file():
        raise ExperimentError(f"{label}.path must name one regular file")
    actual = _digest_file(path)
    if actual != expected:
        raise ExperimentError(
            f"{label} changed: recorded {expected}, current {actual}; freeze the current "
            "bytes in a new specification before using them"
        )
    return {"path": path, "sha256": expected, "bytes": path.read_bytes()}


def _validate_adapter(
    value: object, command: list[str], spec_path: Path, label: str
) -> dict[str, Any]:
    adapter = _validate_bound_file(value, spec_path, label)
    if len(command) < 2:
        raise ExperimentError(
            f"{label} requires command [this Python runtime, adapter, optional arguments]"
        )
    launcher = Path(command[0])
    if not launcher.is_absolute():
        launcher = spec_path.parent / launcher
    if launcher.resolve(strict=False) != Path(sys.executable).resolve():
        raise ExperimentError(
            f"{label} command[0] must be this runner's Python runtime {Path(sys.executable).resolve()}"
        )
    command_adapter = Path(command[1])
    if not command_adapter.is_absolute():
        command_adapter = spec_path.parent / command_adapter
    if command_adapter.is_symlink():
        raise ExperimentError(f"{label} command[1] must not be a symbolic link")
    if command_adapter.resolve(strict=False) != adapter["path"]:
        raise ExperimentError(
            f"{label}.path resolves to {adapter['path']}, but command[1] launches "
            f"{command_adapter.resolve(strict=False)}"
        )
    return adapter


def _validate_evaluator(value: object, spec_path: Path) -> dict[str, Any]:
    label = "evaluation.evaluator"
    if not isinstance(value, dict):
        raise ExperimentError(f"{label} must be an object")
    _require_exact_keys(value, {"adapter", "command"}, label)
    command = value["command"]
    if (
        not isinstance(command, list)
        or not command
        or any(not isinstance(argument, str) or not argument for argument in command)
    ):
        raise ExperimentError(f"{label}.command must be a non-empty array of strings")
    required = {
        "{python}": 1,
        "{evaluation-adapter}": 1,
        "{evaluation-request}": 1,
        "{evaluation-response}": 1,
    }
    for placeholder, expected_count in required.items():
        if command.count(placeholder) != expected_count:
            raise ExperimentError(
                f"{label}.command must contain {placeholder!r} exactly {expected_count} time"
            )
    if command[:2] != ["{python}", "{evaluation-adapter}"]:
        raise ExperimentError(
            f"{label}.command must begin ['{{python}}', '{{evaluation-adapter}}'] so code "
            "controls the evaluator invocation"
        )
    allowed = set(required)
    unknown = sorted(
        argument for argument in command if argument.startswith("{") and argument not in allowed
    )
    if unknown:
        raise ExperimentError(f"{label}.command contains unknown placeholders {unknown!r}")
    adapter = _validate_bound_file(value["adapter"], spec_path, f"{label}.adapter")
    return {"adapter": adapter, "command": list(command)}


def _validate_spec(
    spec: dict[str, Any], spec_path: Path
) -> tuple[
    bytes,
    str,
    dict[str, bytes],
    str,
    Path,
    dict[str, dict[str, Any]],
    dict[str, Any],
]:
    _require_exact_keys(
        spec,
        {
            "schema_version",
            "experiment_id",
            "hypothesis",
            "target",
            "frozen_input",
            "execution_limits",
            "variants",
            "evaluation",
        },
        "experiment specification",
    )
    if spec["schema_version"] != SPEC_CONTRACT:
        raise ExperimentError(
            f"experiment specification schema_version is {spec['schema_version']!r}; expected "
            f"{SPEC_CONTRACT}, whose variants and evaluator are hash-bound"
        )
    _require_identity(spec["experiment_id"], "experiment_id")
    if not isinstance(spec["hypothesis"], str) or not spec["hypothesis"].strip():
        raise ExperimentError("hypothesis must be a non-empty string")

    execution_limits = spec["execution_limits"]
    if not isinstance(execution_limits, dict):
        raise ExperimentError("execution_limits must be an object")
    _require_exact_keys(
        execution_limits,
        {"variant_timeout_ms", "evaluator_timeout_ms"},
        "execution_limits",
    )
    _require_timeout_ms(execution_limits["variant_timeout_ms"], "execution_limits.variant_timeout_ms")
    _require_timeout_ms(execution_limits["evaluator_timeout_ms"], "execution_limits.evaluator_timeout_ms")

    target = spec["target"]
    if not isinstance(target, dict):
        raise ExperimentError("target must be an object")
    _require_exact_keys(target, {"machinery", "phase", "source", "entrypoint"}, "target")
    for field in ("machinery", "phase"):
        if not isinstance(target[field], str) or not target[field].strip():
            raise ExperimentError(f"target.{field} must be a non-empty string")
    source = target["source"]
    if not isinstance(source, dict):
        raise ExperimentError("target.source must be an object")
    _require_exact_keys(source, {"path", "sha256"}, "target.source")
    if not isinstance(source["path"], str) or not source["path"]:
        raise ExperimentError("target.source.path must be a non-empty string")
    source_path = Path(source["path"])
    if not source_path.is_absolute():
        source_path = spec_path.parent / source_path
    source_files, source_sha256 = _snapshot_source(source_path)
    if source["sha256"] != source_sha256:
        raise ExperimentError(
            "target.source.sha256 does not match the stable source tree: "
            f"recorded {source['sha256']!r}, actual {source_sha256}"
        )
    entrypoint = target["entrypoint"]
    if not isinstance(entrypoint, str) or not entrypoint:
        raise ExperimentError("target.entrypoint must be a non-empty relative path")
    entrypoint_path = Path(entrypoint)
    if (
        entrypoint_path.is_absolute()
        or ".." in entrypoint_path.parts
        or entrypoint_path.as_posix() != entrypoint
        or entrypoint not in source_files
    ):
        raise ExperimentError(
            "target.entrypoint must name one stable file inside the declared target source"
        )

    frozen = spec["frozen_input"]
    if not isinstance(frozen, dict):
        raise ExperimentError("frozen_input must be an object")
    _require_exact_keys(frozen, {"path", "sha256"}, "frozen_input")
    if not isinstance(frozen["path"], str) or not frozen["path"]:
        raise ExperimentError("frozen_input.path must be a non-empty string")
    input_path = Path(frozen["path"])
    if not input_path.is_absolute():
        input_path = spec_path.parent / input_path
    input_path = input_path.resolve()
    if not input_path.is_file():
        raise ExperimentError(f"frozen input is not a readable file: {input_path}")
    input_bytes = input_path.read_bytes()
    input_sha256 = _digest_bytes(input_bytes)
    if frozen["sha256"] != input_sha256:
        raise ExperimentError(
            "frozen_input.sha256 does not match the exact input bytes: "
            f"recorded {frozen['sha256']!r}, actual {input_sha256}"
        )

    variants = spec["variants"]
    if not isinstance(variants, list) or len(variants) < 2:
        raise ExperimentError("variants must contain a control and at least one variation")
    identities: list[str] = []
    adapters: dict[str, dict[str, Any]] = {}
    for index, variant in enumerate(variants):
        label = f"variants[{index}]"
        if not isinstance(variant, dict):
            raise ExperimentError(f"{label} must be an object")
        _require_exact_keys(variant, {"id", "command", "configuration", "adapter"}, label)
        identity = _require_identity(variant["id"], f"{label}.id")
        identities.append(identity)
        command = variant["command"]
        if (
            not isinstance(command, list)
            or not command
            or any(not isinstance(argument, str) or not argument for argument in command)
        ):
            raise ExperimentError(f"{label}.command must be a non-empty array of strings")
        if not isinstance(variant["configuration"], dict):
            raise ExperimentError(f"{label}.configuration must be an object")
        adapters[identity] = _validate_adapter(
            variant["adapter"], command, spec_path, f"{label}.adapter"
        )
    duplicates = sorted({identity for identity in identities if identities.count(identity) > 1})
    if duplicates:
        raise ExperimentError(f"variant ids must be unique; duplicates: {duplicates}")
    if "control" not in identities:
        raise ExperimentError("one variant id must be exactly 'control'")

    evaluation = spec["evaluation"]
    if not isinstance(evaluation, dict):
        raise ExperimentError("evaluation must be an object")
    _require_exact_keys(evaluation, {"metrics", "evaluator"}, "evaluation")
    metrics = evaluation["metrics"]
    if not isinstance(metrics, list) or not metrics:
        raise ExperimentError("evaluation.metrics must be a non-empty array")
    metric_names: list[str] = []
    for index, metric in enumerate(metrics):
        label = f"evaluation.metrics[{index}]"
        if not isinstance(metric, dict):
            raise ExperimentError(f"{label} must be an object")
        _require_exact_keys(metric, {"name", "direction"}, label)
        name = _require_identity(metric["name"], f"{label}.name")
        metric_names.append(name)
        if metric["direction"] not in {"maximize", "minimize"}:
            raise ExperimentError(f"{label}.direction must be 'maximize' or 'minimize'")
    duplicates = sorted({name for name in metric_names if metric_names.count(name) > 1})
    if duplicates:
        raise ExperimentError(f"evaluation metric names must be unique; duplicates: {duplicates}")
    evaluator = _validate_evaluator(evaluation["evaluator"], spec_path)
    return (
        input_bytes,
        input_sha256,
        source_files,
        source_sha256,
        source_path.resolve(),
        adapters,
        evaluator,
    )


class Ledger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.sequence = 0
        self.previous: str | None = None

    def append(self, event: str, fields: dict[str, object]) -> dict[str, object]:
        self.sequence += 1
        record: dict[str, object] = {
            "schema_version": CONTRACT,
            "sequence": self.sequence,
            "event": event,
            "recorded_at": datetime.now(UTC).isoformat(),
            "previous_entry_sha256": self.previous,
            **fields,
        }
        record["entry_sha256"] = _digest_bytes(_canonical(record))
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        self.previous = str(record["entry_sha256"])
        return record


def _write_exclusive_json(path: Path, value: object) -> str:
    payload = json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    return _write_exclusive_bytes(path, payload)


def _write_exclusive_bytes(path: Path, payload: bytes) -> str:
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return _digest_bytes(payload)


def _prepare_output(output: Path) -> None:
    if output.exists():
        if not output.is_dir():
            raise ExperimentError(f"output exists and is not a directory: {output}")
        if any(output.iterdir()):
            raise ExperimentError(f"output directory must be new or empty: {output}")
    else:
        output.mkdir(parents=True)


def _metric_value(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def _read_variant_result(
    variant_id: str,
    result_path: Path,
    exit_code: int,
    input_path: Path,
    input_sha256: str,
    config_path: Path,
    config_sha256: str,
    target_path: Path,
    target_sha256: str,
) -> dict[str, Any]:
    errors: list[str] = []
    if _digest_file(input_path) != input_sha256:
        errors.append("the variant changed its frozen input")
    if _digest_file(config_path) != config_sha256:
        errors.append("the variant changed its recorded configuration")
    try:
        _, actual_target_sha256 = _snapshot_source(target_path)
    except ExperimentError as error:
        errors.append(f"the variant target snapshot is unreadable: {error}")
    else:
        if actual_target_sha256 != target_sha256:
            errors.append(
                "the variant changed its read-only target snapshot: "
                f"expected {target_sha256}, actual {actual_target_sha256}"
            )
    result: dict[str, Any] | None = None
    result_sha256: str | None = None
    if not result_path.is_file():
        errors.append("the variant did not write result.json")
    else:
        result_sha256 = _digest_file(result_path)
        try:
            loaded = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"result.json is invalid: {error}")
        else:
            if not isinstance(loaded, dict):
                errors.append("result.json must contain one object")
            else:
                result = loaded
    if result is not None:
        expected = {"schema_version", "variant_id", "status", "outcome", "metrics", "error"}
        if set(result) != expected:
            errors.append(
                f"result.json fields are {sorted(result)}; expected exactly {sorted(expected)}"
            )
        if result.get("schema_version") != CONTRACT:
            errors.append(f"result.schema_version must be {CONTRACT}")
        if result.get("variant_id") != variant_id:
            errors.append(f"result.variant_id must be {variant_id!r}")
        if result.get("status") not in {"completed", "failed"}:
            errors.append("result.status must be 'completed' or 'failed'")
        if not isinstance(result.get("outcome"), dict):
            errors.append("result.outcome must be an object")
        if not isinstance(result.get("metrics"), dict):
            errors.append("result.metrics must be an object")
        error = result.get("error")
        if error is not None and (not isinstance(error, str) or not error.strip()):
            errors.append("result.error must be null or a non-empty string")
        if result.get("status") == "completed" and exit_code != 0:
            errors.append(f"completed result exited non-zero ({exit_code})")
        if result.get("status") == "failed" and exit_code == 0:
            errors.append("failed result exited zero")

    reported_metrics = result.get("metrics", {}) if result is not None else {}
    eligible = (
        not errors
        and result is not None
        and result.get("status") == "completed"
        and exit_code == 0
    )
    return {
        "variant_id": variant_id,
        "status": result.get("status") if result is not None else "failed",
        "eligible": eligible,
        "metrics": {},
        "reported_metrics": reported_metrics if isinstance(reported_metrics, dict) else {},
        "outcome": result.get("outcome", {}) if result is not None else {},
        "error": result.get("error") if result is not None else None,
        "integrity_errors": errors,
        "result_sha256": result_sha256,
    }


def _signal_process_group(process: Any, selected_signal: signal.Signals) -> None:
    try:
        os.killpg(process.pid, selected_signal)
    except (ProcessLookupError, PermissionError):
        if process.returncode is None:
            if selected_signal == signal.SIGTERM:
                process.terminate()
            else:
                process.kill()


async def _stop_async_process(process: Any) -> None:
    _signal_process_group(process, signal.SIGTERM)
    try:
        await asyncio.wait_for(process.wait(), timeout=0.25)
    except TimeoutError:
        _signal_process_group(process, signal.SIGKILL)
        await process.wait()


async def _execute(
    spec: dict[str, Any],
    output: Path,
    frozen_root: Path,
    input_sha256: str,
    target_files: dict[str, bytes],
    target_sha256: str,
    target_source_root: Path,
    adapters: dict[str, dict[str, Any]],
    ledger: Ledger,
) -> list[dict[str, Any]]:
    variants_root = output / "variants"
    variants_root.mkdir()
    for variant in spec["variants"]:
        adapter = adapters[variant["id"]]
        if _digest_file(adapter["path"]) != adapter["sha256"]:
            raise ExperimentError(
                f"variant {variant['id']!r} adapter changed before launch; restore its frozen bytes"
            )
    handles: list[
        tuple[dict[str, Any], Path, Path, str, Path, Any, int, dict[str, Any], Path]
    ] = []
    for variant in spec["variants"]:
        variant_id = variant["id"]
        adapter = adapters[variant_id]
        work = variants_root / variant_id
        work.mkdir()
        input_path = work / "frozen-input.bin"
        shutil.copyfile(frozen_root, input_path)
        input_path.chmod(0o444)
        config_path = work / "variant.json"
        config_sha256 = _write_exclusive_json(
            config_path,
            {
                "schema_version": CONTRACT,
                "variant_id": variant_id,
                "configuration": variant["configuration"],
            },
        )
        target_path = work / "target"
        _write_source_snapshot(target_path, target_files)
        try:
            adapter_relative = adapter["path"].relative_to(target_source_root)
        except ValueError:
            adapter_snapshot = work / "adapter.py"
            _write_exclusive_bytes(adapter_snapshot, adapter["bytes"])
            adapter_snapshot.chmod(0o444)
        else:
            adapter_snapshot = target_path / adapter_relative
            if not adapter_snapshot.is_file() or _digest_file(adapter_snapshot) != adapter["sha256"]:
                raise ExperimentError(
                    f"variant {variant_id!r} adapter is not preserved by the target source snapshot"
                )
        launch_command = [
            sys.executable,
            str(adapter_snapshot.resolve()),
            *variant["command"][2:],
        ]
        result_path = work / "result.json"
        telemetry_path = work / "telemetry.jsonl"
        env = os.environ.copy()
        env.update(
            {
                "EXPERIMENT_ID": spec["experiment_id"],
                "EXPERIMENT_VARIANT_ID": variant_id,
                "EXPERIMENT_WORK_DIR": str(work.resolve()),
                "EXPERIMENT_INPUT_PATH": str(input_path.resolve()),
                "EXPERIMENT_VARIANT_PATH": str(config_path.resolve()),
                "EXPERIMENT_TARGET_PATH": str(target_path.resolve()),
                "EXPERIMENT_TARGET_ENTRYPOINT": spec["target"]["entrypoint"],
                "EXPERIMENT_RESULT_PATH": str(result_path.resolve()),
                "EXPERIMENT_TELEMETRY_PATH": str(telemetry_path.resolve()),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        started_ns = time.monotonic_ns()
        try:
            process = await asyncio.create_subprocess_exec(
                *launch_command,
                cwd=work,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
        except OSError as error:
            raise ExperimentError(
                f"variant {variant_id!r} could not start command {launch_command!r}: {error}"
            ) from error
        ledger.append(
            "variant_started",
            {
                "experiment_id": spec["experiment_id"],
                "variant_id": variant_id,
                "work_path": str(work.relative_to(output)),
                "command_sha256": _digest_bytes(_canonical(launch_command)),
                "spec_command_sha256": _digest_bytes(_canonical(variant["command"])),
                "configuration_sha256": config_sha256,
                "frozen_input_sha256": input_sha256,
                "target_source_sha256": target_sha256,
                "adapter_sha256": adapter["sha256"],
                "adapter_snapshot_sha256": _digest_file(adapter_snapshot),
                "adapter_snapshot_path": str(adapter_snapshot.relative_to(output)),
                "process_id": process.pid,
                "timeout_ms": spec["execution_limits"]["variant_timeout_ms"],
            },
        )
        handles.append(
            (
                variant,
                input_path,
                config_path,
                config_sha256,
                target_path,
                process,
                started_ns,
                adapter,
                adapter_snapshot,
            )
        )

    async def finish(
        handle: tuple[
            dict[str, Any], Path, Path, str, Path, Any, int, dict[str, Any], Path
        ]
    ) -> dict[str, Any]:
        (
            variant,
            input_path,
            config_path,
            config_sha256,
            target_path,
            process,
            started_ns,
            adapter,
            adapter_snapshot,
        ) = handle
        stdout_task = asyncio.create_task(process.stdout.read())
        stderr_task = asyncio.create_task(process.stderr.read())
        timed_out = False
        elapsed_seconds = (time.monotonic_ns() - started_ns) / 1_000_000_000
        remaining_seconds = max(
            0.0,
            spec["execution_limits"]["variant_timeout_ms"] / 1000 - elapsed_seconds,
        )
        try:
            if process.returncode is None:
                await asyncio.wait_for(process.wait(), timeout=remaining_seconds)
            else:
                await process.wait()
        except TimeoutError:
            timed_out = True
            await _stop_async_process(process)
        stdout, stderr = await asyncio.gather(stdout_task, stderr_task)
        duration_ms = (time.monotonic_ns() - started_ns) // 1_000_000
        work = input_path.parent
        (work / "stdout.txt").write_bytes(stdout)
        (work / "stderr.txt").write_bytes(stderr)
        record = _read_variant_result(
            variant["id"],
            work / "result.json",
            int(process.returncode),
            input_path,
            input_sha256,
            config_path,
            config_sha256,
            target_path,
            target_sha256,
        )
        if timed_out:
            record["status"] = "failed"
            record["eligible"] = False
            record["error"] = (
                f"variant exceeded its declared "
                f"{spec['execution_limits']['variant_timeout_ms']} ms deadline"
            )
            record["integrity_errors"].append(record["error"])
        if _digest_file(adapter["path"]) != adapter["sha256"]:
            record["integrity_errors"].append(
                f"adapter changed during variant {variant['id']!r}"
            )
            record["eligible"] = False
        if _digest_file(adapter_snapshot) != adapter["sha256"]:
            record["integrity_errors"].append(
                f"executed adapter snapshot changed during variant {variant['id']!r}"
            )
            record["eligible"] = False
        telemetry = work / "telemetry.jsonl"
        record.update(
            {
                "exit_code": int(process.returncode),
                "duration_ms": duration_ms,
                "timeout_ms": spec["execution_limits"]["variant_timeout_ms"],
                "timed_out": timed_out,
                "stdout_sha256": _digest_bytes(stdout),
                "stderr_sha256": _digest_bytes(stderr),
                "telemetry_sha256": _digest_file(telemetry) if telemetry.is_file() else None,
            }
        )
        return record

    results = await asyncio.gather(*(finish(handle) for handle in handles))
    by_id = {result["variant_id"]: result for result in results}
    ordered = [by_id[variant["id"]] for variant in spec["variants"]]
    for result in ordered:
        ledger.append(
            "variant_finished",
            {
                "experiment_id": spec["experiment_id"],
                **{
                    key: result[key]
                    for key in (
                        "variant_id",
                        "status",
                        "eligible",
                        "metrics",
                        "reported_metrics",
                        "exit_code",
                        "duration_ms",
                        "timeout_ms",
                        "timed_out",
                        "result_sha256",
                        "telemetry_sha256",
                        "stdout_sha256",
                        "stderr_sha256",
                        "integrity_errors",
                    )
                },
            },
        )
    return ordered


def _invoke_evaluator(
    spec: dict[str, Any],
    results: list[dict[str, Any]],
    output: Path,
    evaluator: dict[str, Any],
    evaluator_snapshot: Path,
    ledger: Ledger,
) -> dict[str, dict[str, float]]:
    metrics = spec["evaluation"]["metrics"]
    eligible = [row for row in results if row["eligible"]]
    request = {
        "schema_version": CONTRACT,
        "experiment_id": spec["experiment_id"],
        "metrics": metrics,
        "candidates": [
            {
                "variant_id": row["variant_id"],
                "outcome": row["outcome"],
                "result_sha256": row["result_sha256"],
                "evidence": [
                    {
                        "id": evidence_id,
                        "path": str((output / "variants" / row["variant_id"] / filename).resolve()),
                        "sha256": row[digest_key],
                    }
                    for evidence_id, filename, digest_key in (
                        ("stdout", "stdout.txt", "stdout_sha256"),
                        ("stderr", "stderr.txt", "stderr_sha256"),
                        ("telemetry", "telemetry.jsonl", "telemetry_sha256"),
                    )
                    if row[digest_key] is not None
                ],
            }
            for row in eligible
        ],
    }
    evaluation_root = output / "evaluation"
    evaluation_root.mkdir()
    request_path = evaluation_root / "request.json"
    response_path = evaluation_root / "response.json"
    request_sha256 = _write_exclusive_json(request_path, request)
    replacements = {
        "{python}": sys.executable,
        "{evaluation-adapter}": str(evaluator_snapshot.resolve()),
        "{evaluation-request}": str(request_path.resolve()),
        "{evaluation-response}": str(response_path.resolve()),
    }
    command = [replacements.get(argument, argument) for argument in evaluator["command"]]
    ledger.append(
        "evaluator_started",
        {
            "experiment_id": spec["experiment_id"],
            "evaluator_sha256": evaluator["adapter"]["sha256"],
            "request_sha256": request_sha256,
            "candidate_ids": [row["variant_id"] for row in eligible],
            "timeout_ms": spec["execution_limits"]["evaluator_timeout_ms"],
        },
    )
    try:
        process = subprocess.Popen(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as error:
        raise ExperimentError(f"independent evaluator could not start: {error}") from error
    timed_out = False
    try:
        stdout, stderr = process.communicate(
            timeout=spec["execution_limits"]["evaluator_timeout_ms"] / 1000
        )
    except subprocess.TimeoutExpired:
        timed_out = True
        _signal_process_group(process, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=0.25)
        except subprocess.TimeoutExpired:
            _signal_process_group(process, signal.SIGKILL)
            stdout, stderr = process.communicate()
    stdout_sha256 = _write_exclusive_bytes(
        evaluation_root / "stdout.txt", stdout.encode("utf-8")
    )
    stderr_sha256 = _write_exclusive_bytes(
        evaluation_root / "stderr.txt", stderr.encode("utf-8")
    )
    if timed_out:
        timeout_evidence = {
            "schema_version": CONTRACT,
            "status": "timed-out",
            "timeout_ms": spec["execution_limits"]["evaluator_timeout_ms"],
            "exit_code": process.returncode,
            "stdout_sha256": stdout_sha256,
            "stderr_sha256": stderr_sha256,
        }
        evidence_sha256 = _write_exclusive_json(
            evaluation_root / "timeout.json", timeout_evidence
        )
        ledger.append(
            "evaluator_timed_out",
            {
                "experiment_id": spec["experiment_id"],
                **timeout_evidence,
                "evidence_sha256": evidence_sha256,
            },
        )
        raise EvaluatorTimeout(
            spec["execution_limits"]["evaluator_timeout_ms"], evidence_sha256
        )
    adapter = evaluator["adapter"]
    if _digest_file(adapter["path"]) != adapter["sha256"]:
        raise ExperimentError("independent evaluator changed during evaluation; no ranking was produced")
    if _digest_file(evaluator_snapshot) != adapter["sha256"]:
        raise ExperimentError("executed evaluator snapshot changed during evaluation; no ranking was produced")
    for candidate in request["candidates"]:
        for evidence in candidate["evidence"]:
            if _digest_file(Path(evidence["path"])) != evidence["sha256"]:
                raise ExperimentError(
                    f"variant {candidate['variant_id']!r} changed {evidence['id']} evidence "
                    "during evaluation; no ranking was produced"
                )
    if process.returncode != 0:
        raise ExperimentError(
            f"independent evaluator exited {process.returncode}: "
            f"{stderr.strip() or 'no diagnostic'}"
        )
    response, _ = _load_object(response_path, "independent evaluator response")
    _require_exact_keys(response, {"schema_version", "scores"}, "evaluator response")
    if response["schema_version"] != CONTRACT:
        raise ExperimentError(f"evaluator response schema_version must be {CONTRACT}")
    scores = response["scores"]
    if not isinstance(scores, list):
        raise ExperimentError("evaluator response scores must be an array")
    metric_names = [metric["name"] for metric in metrics]
    expected_ids = [row["variant_id"] for row in eligible]
    accepted: dict[str, dict[str, float]] = {}
    for index, raw in enumerate(scores):
        label = f"evaluator response scores[{index}]"
        if not isinstance(raw, dict):
            raise ExperimentError(f"{label} must be an object")
        _require_exact_keys(raw, {"variant_id", "metrics"}, label)
        variant_id = raw["variant_id"]
        if variant_id in accepted:
            raise ExperimentError(f"{label} repeats variant_id {variant_id!r}")
        if variant_id not in expected_ids:
            raise ExperimentError(f"{label} names unknown variant_id {variant_id!r}")
        values = raw["metrics"]
        if not isinstance(values, dict) or set(values) != set(metric_names):
            raise ExperimentError(f"{label}.metrics must contain exactly {metric_names!r}")
        normalized: dict[str, float] = {}
        for name in metric_names:
            numeric = _metric_value(values[name])
            if numeric is None:
                raise ExperimentError(f"{label}.metrics[{name!r}] must be finite and numeric")
            normalized[name] = numeric
        accepted[variant_id] = normalized
    if list(accepted) != expected_ids:
        raise ExperimentError(
            f"evaluator response variant order is {list(accepted)!r}; require {expected_ids!r}"
        )
    response_sha256 = _digest_file(response_path)
    ledger.append(
        "evaluator_finished",
        {
            "experiment_id": spec["experiment_id"],
            "response_sha256": response_sha256,
            "score_count": len(accepted),
        },
    )
    return accepted


def _evaluate(
    spec: dict[str, Any],
    results: list[dict[str, Any]],
    scores: dict[str, dict[str, float]],
) -> tuple[str | None, list[dict[str, Any]]]:
    metrics = spec["evaluation"]["metrics"]
    for result in results:
        if result["variant_id"] in scores:
            result["metrics"] = scores[result["variant_id"]]

    def rank_key(result: dict[str, Any]) -> tuple[object, ...]:
        values: list[object] = []
        for metric in metrics:
            value = result["metrics"][metric["name"]]
            values.append(-value if metric["direction"] == "maximize" else value)
        values.append(result["variant_id"])
        return tuple(values)

    eligible = sorted((row for row in results if row["eligible"]), key=rank_key)
    ranking = [
        {
            "rank": index,
            "variant_id": row["variant_id"],
            "metrics": row["metrics"],
        }
        for index, row in enumerate(eligible, start=1)
    ]
    return (eligible[0]["variant_id"] if eligible else None), ranking


async def run(spec_path: Path, output: Path) -> dict[str, Any]:
    spec_path = spec_path.resolve()
    output = output.resolve()
    spec, spec_bytes = _load_object(spec_path, "experiment specification")
    (
        input_bytes,
        input_sha256,
        target_files,
        target_sha256,
        target_source_root,
        adapters,
        evaluator,
    ) = _validate_spec(spec, spec_path)
    _prepare_output(output)
    frozen_root = output / "frozen-input.bin"
    _write_exclusive_bytes(frozen_root, input_bytes)
    frozen_root.chmod(0o444)
    spec_copy = output / "experiment-spec.json"
    _write_exclusive_bytes(spec_copy, spec_bytes)
    spec_copy.chmod(0o444)
    evaluator_root = output / "evaluator"
    evaluator_root.mkdir()
    evaluator_snapshot = evaluator_root / "adapter.py"
    _write_exclusive_bytes(evaluator_snapshot, evaluator["adapter"]["bytes"])
    evaluator_snapshot.chmod(0o444)
    ledger = Ledger(output / "ledger.jsonl")
    ledger.append(
        "experiment_started",
        {
            "experiment_id": spec["experiment_id"],
            "hypothesis": spec["hypothesis"],
            "target": spec["target"],
            "target_source_sha256": target_sha256,
            "frozen_input_sha256": input_sha256,
            "specification_sha256": _digest_file(spec_copy),
            "execution_limits": spec["execution_limits"],
            "evaluation": spec["evaluation"],
            "variant_ids": [variant["id"] for variant in spec["variants"]],
            "variant_adapters": [
                {"variant_id": variant["id"], "sha256": adapters[variant["id"]]["sha256"]}
                for variant in spec["variants"]
            ],
            "evaluator_sha256": evaluator["adapter"]["sha256"],
        },
    )
    if _digest_file(evaluator["adapter"]["path"]) != evaluator["adapter"]["sha256"]:
        raise ExperimentError(
            "independent evaluator changed before variant execution; no experiment result was produced"
        )
    results = await _execute(
        spec,
        output,
        frozen_root,
        input_sha256,
        target_files,
        target_sha256,
        target_source_root,
        adapters,
        ledger,
    )
    if _digest_file(frozen_root) != input_sha256:
        raise ExperimentError("the root frozen input changed during the experiment")
    if _digest_file(evaluator["adapter"]["path"]) != evaluator["adapter"]["sha256"]:
        raise ExperimentError(
            "independent evaluator changed before scoring; no experiment recommendation was produced"
        )
    eligible = [row for row in results if row["eligible"]]
    evaluation_error = None
    try:
        scores = (
            _invoke_evaluator(spec, results, output, evaluator, evaluator_snapshot, ledger)
            if eligible
            else {}
        )
    except EvaluatorTimeout as error:
        scores = {}
        evaluation_error = {
            "kind": "timeout",
            "message": str(error),
            "timeout_ms": error.timeout_ms,
            "evidence_sha256": error.evidence_sha256,
        }
    champion, ranking = (
        _evaluate(spec, results, scores)
        if evaluation_error is None
        else (None, [])
    )
    status = (
        "evaluator-timeout"
        if evaluation_error is not None
        else ("completed" if champion is not None else "no-eligible-variant")
    )
    summary = {
        "schema_version": CONTRACT,
        "experiment_id": spec["experiment_id"],
        "hypothesis": spec["hypothesis"],
        "target": spec["target"],
        "target_source_sha256": target_sha256,
        "frozen_input_sha256": input_sha256,
        "execution_limits": spec["execution_limits"],
        "evaluation": spec["evaluation"],
        "status": status,
        "evaluation_error": evaluation_error,
        "champion": champion,
        "ranking": ranking,
        "variants": results,
        "promotion_applied": False,
    }
    summary_sha256 = _write_exclusive_json(output / "summary.json", summary)
    ledger.append(
        "evaluation_completed",
        {
            "experiment_id": spec["experiment_id"],
            "champion": champion,
            "status": status,
            "eligible_variant_ids": [row["variant_id"] for row in ranking],
            "summary_sha256": summary_sha256,
            "promotion_applied": False,
        },
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--hash-source",
        type=Path,
        help="print the stable source-tree hash used by target.source.sha256",
    )
    args = parser.parse_args()
    try:
        if args.hash_source is not None:
            if args.spec is not None or args.output is not None:
                raise ExperimentError("use --hash-source by itself")
            _, source_sha256 = _snapshot_source(args.hash_source)
            print(source_sha256)
            return 0
        if args.spec is None or args.output is None:
            raise ExperimentError("--spec and --output are required for an experiment run")
        summary = asyncio.run(run(args.spec, args.output))
    except ExperimentError as error:
        print(f"Experiment refused: {error}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["champion"] is not None else 3


if __name__ == "__main__":
    raise SystemExit(main())
