"""Run one frozen-input, isolated, parallel machinery experiment."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import re
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTRACT = 1
SPEC_CONTRACT = 2
_IDENTITY = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ExperimentError(RuntimeError):
    """Raised when an experiment boundary is invalid."""


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


def _validate_adapter(value: object, command: list[str], spec_path: Path, label: str) -> dict[str, Any]:
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
        raise ExperimentError(f"{label}.path must name one regular adapter file")
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
    if command_adapter.resolve(strict=False) != path:
        raise ExperimentError(
            f"{label}.path resolves to {path}, but command[1] launches "
            f"{command_adapter.resolve(strict=False)}"
        )
    actual = _digest_file(path)
    if actual != expected:
        raise ExperimentError(
            f"{label} changed: recorded {expected}, current {actual}; update the frozen "
            "specification intentionally before running this adapter"
        )
    return {"path": path, "sha256": expected, "bytes": path.read_bytes()}


def _validate_spec(
    spec: dict[str, Any], spec_path: Path
) -> tuple[bytes, str, dict[str, bytes], str, dict[str, dict[str, Any]]]:
    _require_exact_keys(
        spec,
        {
            "schema_version",
            "experiment_id",
            "hypothesis",
            "target",
            "frozen_input",
            "variants",
            "evaluation",
        },
        "experiment specification",
    )
    if spec["schema_version"] != SPEC_CONTRACT:
        raise ExperimentError(
            f"experiment specification schema_version is {spec['schema_version']!r}; expected "
            f"{SPEC_CONTRACT}, whose variants bind adapter path and sha256"
        )
    _require_identity(spec["experiment_id"], "experiment_id")
    if not isinstance(spec["hypothesis"], str) or not spec["hypothesis"].strip():
        raise ExperimentError("hypothesis must be a non-empty string")

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
    _require_exact_keys(evaluation, {"metrics"}, "evaluation")
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
    return input_bytes, input_sha256, source_files, source_sha256, adapters


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
    declared_metrics: list[dict[str, str]],
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

    metrics = result.get("metrics", {}) if result is not None else {}
    metric_values: dict[str, float] = {}
    if isinstance(metrics, dict):
        for metric in declared_metrics:
            name = metric["name"]
            numeric = _metric_value(metrics.get(name))
            if numeric is None:
                errors.append(f"declared metric {name!r} is missing, non-numeric, or non-finite")
            else:
                metric_values[name] = numeric
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
        "metrics": metric_values,
        "outcome": result.get("outcome", {}) if result is not None else {},
        "error": result.get("error") if result is not None else None,
        "integrity_errors": errors,
        "result_sha256": result_sha256,
    }


async def _execute(
    spec: dict[str, Any],
    output: Path,
    frozen_root: Path,
    input_sha256: str,
    target_files: dict[str, bytes],
    target_sha256: str,
    adapters: dict[str, dict[str, Any]],
    ledger: Ledger,
) -> list[dict[str, Any]]:
    variants_root = output / "variants"
    variants_root.mkdir()
    for variant in spec["variants"]:
        variant_id = variant["id"]
        adapter = adapters[variant_id]
        current_adapter_sha256 = _digest_file(adapter["path"])
        if current_adapter_sha256 != adapter["sha256"]:
            raise ExperimentError(
                f"variant {variant_id!r} adapter changed before any variant launch: recorded "
                f"{adapter['sha256']}, current {current_adapter_sha256}; restore the frozen "
                "adapter or write a new specification"
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
        adapter_snapshot = work / "adapter.py"
        _write_exclusive_bytes(adapter_snapshot, adapter["bytes"])
        adapter_snapshot.chmod(0o444)
        launch_command = [
            str(Path(sys.executable).resolve()),
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
        handle: tuple[dict[str, Any], Path, Path, str, Path, Any, int, dict[str, Any], Path]
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
        stdout, stderr = await process.communicate()
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
            spec["evaluation"]["metrics"],
        )
        current_adapter_sha256 = _digest_file(adapter["path"])
        if current_adapter_sha256 != adapter["sha256"]:
            record["integrity_errors"].append(
                f"adapter changed during variant {variant['id']!r}: recorded "
                f"{adapter['sha256']}, current {current_adapter_sha256}"
            )
            record["eligible"] = False
        snapshot_sha256 = _digest_file(adapter_snapshot)
        if snapshot_sha256 != adapter["sha256"]:
            record["integrity_errors"].append(
                f"executed adapter snapshot changed during variant {variant['id']!r}: recorded "
                f"{adapter['sha256']}, current {snapshot_sha256}"
            )
            record["eligible"] = False
        telemetry = work / "telemetry.jsonl"
        record.update(
            {
                "exit_code": int(process.returncode),
                "duration_ms": duration_ms,
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
                        "exit_code",
                        "duration_ms",
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


def _evaluate(
    spec: dict[str, Any], results: list[dict[str, Any]]
) -> tuple[str | None, list[dict[str, Any]]]:
    metrics = spec["evaluation"]["metrics"]

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
    input_bytes, input_sha256, target_files, target_sha256, adapters = _validate_spec(
        spec, spec_path
    )
    _prepare_output(output)
    frozen_root = output / "frozen-input.bin"
    _write_exclusive_bytes(frozen_root, input_bytes)
    frozen_root.chmod(0o444)
    spec_copy = output / "experiment-spec.json"
    _write_exclusive_bytes(spec_copy, spec_bytes)
    spec_copy.chmod(0o444)
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
            "evaluation": spec["evaluation"],
            "variant_ids": [variant["id"] for variant in spec["variants"]],
            "adapters": [
                {"variant_id": variant["id"], "path": str(adapters[variant["id"]]["path"]),
                 "sha256": adapters[variant["id"]]["sha256"]}
                for variant in spec["variants"]
            ],
        },
    )
    results = await _execute(
        spec,
        output,
        frozen_root,
        input_sha256,
        target_files,
        target_sha256,
        adapters,
        ledger,
    )
    if _digest_file(frozen_root) != input_sha256:
        raise ExperimentError("the root frozen input changed during the experiment")
    champion, ranking = _evaluate(spec, results)
    summary = {
        "schema_version": CONTRACT,
        "experiment_id": spec["experiment_id"],
        "hypothesis": spec["hypothesis"],
        "target": spec["target"],
        "target_source_sha256": target_sha256,
        "frozen_input_sha256": input_sha256,
        "evaluation": spec["evaluation"],
        "status": "completed" if champion is not None else "no-eligible-variant",
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
