"""Exercise Info Intake's real purpose-assessment seam as one experiment variant."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTRACT = 1


class ProbeError(RuntimeError):
    """Raised when the adapter contract or target path is invalid."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProbeError(f"{label} is unavailable or invalid JSON: {error}") from error
    if not isinstance(value, dict):
        raise ProbeError(f"{label} must contain one object")
    return value


def _path_from_env(name: str) -> Path:
    value = os.environ.get(name)
    if not value:
        raise ProbeError(f"{name} is required")
    return Path(value).resolve()


class Telemetry:
    def __init__(self, path: Path, variant_id: str) -> None:
        self.path = path
        self.variant_id = variant_id
        self.sequence = 0
        self.previous: str | None = None
        if path.is_file() and path.stat().st_size:
            try:
                last = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
            except (OSError, json.JSONDecodeError, IndexError) as error:
                raise ProbeError(f"existing telemetry cannot be resumed: {error}") from error
            if (
                not isinstance(last, dict)
                or not isinstance(last.get("sequence"), int)
                or not isinstance(last.get("entry_sha256"), str)
                or last.get("variant_id") != variant_id
            ):
                raise ProbeError("existing telemetry tail is invalid or belongs to another variant")
            self.sequence = last["sequence"]
            self.previous = last["entry_sha256"]

    def append(self, event: str, fields: dict[str, object]) -> None:
        self.sequence += 1
        record: dict[str, object] = {
            "schema_version": CONTRACT,
            "sequence": self.sequence,
            "event": event,
            "recorded_at": datetime.now(UTC).isoformat(),
            "variant_id": self.variant_id,
            "previous_entry_sha256": self.previous,
            **fields,
        }
        record["entry_sha256"] = _digest(_canonical(record))
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        self.previous = str(record["entry_sha256"])


def _write_result(path: Path, value: dict[str, object]) -> None:
    payload = json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _load_target(path: Path) -> Any:
    if not path.is_file():
        raise ProbeError(f"Info Intake target script does not exist: {path}")
    module_name = f"experiment_info_intake_{_digest(str(path).encode())[:12]}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ProbeError(f"Info Intake target script cannot be loaded: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _completed_event(work: Path) -> dict[str, Any]:
    try:
        records = [
            json.loads(line)
            for line in (work / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as error:
        raise ProbeError(f"Info Intake ledger is unavailable or invalid: {error}") from error
    completed = [record for record in records if record.get("event") == "model_assessment_completed"]
    if len(completed) != 1:
        raise ProbeError(
            f"Info Intake must record exactly one completed purpose assessment; found {len(completed)}"
        )
    return completed[0]


def run() -> int:
    variant_id = os.environ.get("EXPERIMENT_VARIANT_ID", "")
    if not variant_id:
        raise ProbeError("EXPERIMENT_VARIANT_ID is required")
    work = _path_from_env("EXPERIMENT_WORK_DIR")
    input_path = _path_from_env("EXPERIMENT_INPUT_PATH")
    variant_path = _path_from_env("EXPERIMENT_VARIANT_PATH")
    target_path = _path_from_env("EXPERIMENT_TARGET_PATH")
    target_entrypoint = os.environ.get("EXPERIMENT_TARGET_ENTRYPOINT", "")
    result_path = _path_from_env("EXPERIMENT_RESULT_PATH")
    telemetry_path = _path_from_env("EXPERIMENT_TELEMETRY_PATH")
    for path, label in ((result_path, "result"), (telemetry_path, "telemetry")):
        if path.parent != work:
            raise ProbeError(f"{label} path must be directly inside EXPERIMENT_WORK_DIR")
    if not target_entrypoint:
        raise ProbeError("EXPERIMENT_TARGET_ENTRYPOINT is required")
    target_script = (target_path / target_entrypoint).resolve()
    if target_path not in target_script.parents:
        raise ProbeError("EXPERIMENT_TARGET_ENTRYPOINT points outside EXPERIMENT_TARGET_PATH")

    frozen = _load_object(input_path, "frozen input")
    if set(frozen) != {"schema_version", "opening", "purpose", "expected_boundary"}:
        raise ProbeError(
            "frozen input must contain exactly schema_version, opening, purpose, and expected_boundary"
        )
    if frozen["schema_version"] != CONTRACT:
        raise ProbeError(f"frozen input schema_version must be {CONTRACT}")
    for field in ("opening", "purpose", "expected_boundary"):
        if not isinstance(frozen[field], str) or not frozen[field].strip():
            raise ProbeError(f"frozen input {field} must be a non-empty string")

    variant = _load_object(variant_path, "variant configuration")
    if set(variant) != {"schema_version", "variant_id", "configuration"}:
        raise ProbeError(
            "variant configuration must contain exactly schema_version, variant_id, and configuration"
        )
    if variant["schema_version"] != CONTRACT or variant["variant_id"] != variant_id:
        raise ProbeError("variant configuration identity does not match the runner environment")
    configuration = variant["configuration"]
    if not isinstance(configuration, dict) or set(configuration) != {"answers"}:
        raise ProbeError("configuration must contain exactly one answers array")
    answers = configuration["answers"]
    if not isinstance(answers, list) or not answers or any(not isinstance(row, str) for row in answers):
        raise ProbeError("configuration.answers must be a non-empty array of strings")

    telemetry = Telemetry(telemetry_path, variant_id)
    started_ns = time.monotonic_ns()
    telemetry.append(
        "phase_started",
        {
            "machinery": "info-intake-machinery",
            "phase": "assess_intake_purpose",
            "frozen_input_sha256": _digest(input_path.read_bytes()),
            "target_script_sha256": _digest(target_script.read_bytes()),
        },
    )
    target = _load_target(target_script)
    target_work = work / "target-work"
    remaining = iter(enumerate(answers, start=1))
    supplied_count = 0
    rejected: list[str] = []

    def provide(prompt: str) -> str:
        nonlocal supplied_count
        try:
            ordinal, answer = next(remaining)
        except StopIteration as error:
            raise ProbeError(
                "the answer setup ended before Info Intake completed its typed interview"
            ) from error
        supplied_count += 1
        telemetry.append(
            "answer_supplied",
            {"answer_ordinal": ordinal, "prompt_sha256": _digest(prompt.encode("utf-8"))},
        )
        return answer

    def record_rejection(message: str) -> None:
        rejected.append(message)
        telemetry.append("answer_rejected", {"message": message})

    first = target.drive(target_work, frozen["opening"])
    if first.get("stopped") != "awaiting_intake_purpose":
        raise ProbeError(
            "Info Intake did not reach its purpose question; "
            f"received status={first.get('status')!r}, stopped={first.get('stopped')!r}"
        )
    requested = target.drive(target_work, frozen["opening"], frozen["purpose"])
    if requested.get("status") != "waiting_for_model" or requested.get("stopped") != "assessing_intake_purpose":
        raise ProbeError(
            "Info Intake did not request purpose assessment; "
            f"received status={requested.get('status')!r}, stopped={requested.get('stopped')!r}"
        )
    outcome = target.run_purpose_interview(
        target_work,
        input_fn=provide,
        output_fn=record_rejection,
    )
    completed = _completed_event(target_work)
    stopped = outcome.get("stopped")
    metrics = {
        "reached-expected-boundary": int(stopped == frozen["expected_boundary"]),
        "rejected-answer-count": int(completed.get("rejected_answer_count", len(rejected))),
        "answer-count": int(completed.get("answer_count", supplied_count)),
    }
    telemetry.append(
        "phase_finished",
        {
            "status": outcome.get("status"),
            "stopped": stopped,
            "metrics": metrics,
            "elapsed_ms": (time.monotonic_ns() - started_ns) // 1_000_000,
        },
    )
    _write_result(
        result_path,
        {
            "schema_version": CONTRACT,
            "variant_id": variant_id,
            "status": "completed",
            "outcome": {
                "status": outcome.get("status"),
                "stopped": stopped,
                "question": outcome.get("question"),
                "target_ledger_sha256": _digest((target_work / "ledger.jsonl").read_bytes()),
            },
            "metrics": metrics,
            "error": None,
        },
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    result_path_value = os.environ.get("EXPERIMENT_RESULT_PATH")
    telemetry_path_value = os.environ.get("EXPERIMENT_TELEMETRY_PATH")
    variant_id = os.environ.get("EXPERIMENT_VARIANT_ID", "unknown")
    try:
        return run()
    except Exception as error:  # noqa: BLE001 - preserve every process-boundary failure
        if telemetry_path_value:
            telemetry_path = Path(telemetry_path_value)
            try:
                Telemetry(telemetry_path, variant_id).append(
                    "phase_failed", {"error": f"{type(error).__name__}: {error}"}
                )
            except OSError:
                pass
        if result_path_value:
            result_path = Path(result_path_value)
            if not result_path.exists():
                try:
                    _write_result(
                        result_path,
                        {
                            "schema_version": CONTRACT,
                            "variant_id": variant_id,
                            "status": "failed",
                            "outcome": {},
                            "metrics": {},
                            "error": f"{type(error).__name__}: {error}",
                        },
                    )
                except OSError:
                    pass
        print(f"Intake purpose probe failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
