#!/usr/bin/env python3
"""Compare grounded setups for Info Intake's final relationship decision."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tarfile
import time
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

CONTRACT = 1


class ProbeError(RuntimeError):
    """Raised when the adapter contract or target path is invalid."""


class AnswerLimitReached(RuntimeError):
    """Stops a variant after its one controlled model decision."""


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
    name = f"experiment_projection_terminal_{_digest(str(path).encode())[:12]}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ProbeError(f"Info Intake target script cannot be loaded: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _extract_frozen_input(archive_path: Path, destination: Path) -> None:
    destination.mkdir()
    seen: set[str] = set()
    try:
        archive = tarfile.open(fileobj=BytesIO(archive_path.read_bytes()), mode="r:*")
    except (OSError, tarfile.TarError) as error:
        raise ProbeError(f"frozen input is not a readable archive: {error}") from error
    with archive:
        for member in archive.getmembers():
            relative = Path(member.name)
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or relative.as_posix() in seen
                or not (member.isdir() or member.isfile())
            ):
                raise ProbeError(f"frozen input contains an unsafe member: {member.name}")
            seen.add(relative.as_posix())
            target = destination / relative
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            extracted = archive.extractfile(member)
            if extracted is None:
                raise ProbeError(f"frozen input member is unreadable: {member.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(extracted.read())


def _model_prompt(
    production_prompt: str,
    context_mode: str,
    completion_context: dict[str, object],
) -> str:
    lines = [
        "Act only as the semantic reader inside a code-controlled Info Intake interview.",
        "Inspect the attached immutable source and answer the exact production question below.",
        "Do not use tools or inspect files; all permitted recorded-projection evidence is in this prompt.",
        production_prompt,
    ]
    if context_mode == "complete-index":
        lines.extend([
            "Complete code-generated recorded-relationship index:",
            json.dumps(completion_context, sort_keys=True),
        ])
    lines.extend([
        "Return one JSON object matching the supplied schema.",
        "List every recorded relationship id actually compared in compared_relationship_ids.",
        "Choose yes only when the source shows a purpose-relevant relationship absent from the index, and describe it.",
        "Choose no only after comparing the source against every relationship the prompt makes available.",
    ])
    return "\n".join(lines)


def _response_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "answer": {"type": "string", "enum": ["yes", "no"]},
            "compared_relationship_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
            "decision_basis": {"type": "string"},
            "unrecorded_relationship_description": {
                "type": ["string", "null"]
            },
        },
        "required": [
            "answer",
            "compared_relationship_ids",
            "decision_basis",
            "unrecorded_relationship_description",
        ],
        "additionalProperties": False,
    }


def _controlled_citations(value: object) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ProbeError("model response contains an invalid relationship citation")
    if len(set(value)) != len(value):
        raise ProbeError("model response contains duplicate relationship citations")
    return value


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
    if not target_entrypoint:
        raise ProbeError("EXPERIMENT_TARGET_ENTRYPOINT is required")
    target_script = (target_path / target_entrypoint).resolve()
    if target_path not in target_script.parents:
        raise ProbeError("EXPERIMENT_TARGET_ENTRYPOINT points outside EXPERIMENT_TARGET_PATH")

    variant = _load_object(variant_path, "variant configuration")
    if set(variant) != {"schema_version", "variant_id", "configuration"}:
        raise ProbeError("variant configuration has unexpected fields")
    if variant["schema_version"] != CONTRACT or variant["variant_id"] != variant_id:
        raise ProbeError("variant configuration identity does not match the runner environment")
    configuration = variant["configuration"]
    if not isinstance(configuration, dict) or set(configuration) != {
        "context_mode", "model", "model_executable"
    }:
        raise ProbeError("configuration must define context_mode, model, and model_executable")
    context_mode = configuration["context_mode"]
    if context_mode not in {"production", "complete-index"}:
        raise ProbeError("context_mode must be production or complete-index")
    model = configuration["model"]
    executable = Path(str(configuration["model_executable"])).resolve()
    if not isinstance(model, str) or not model or not executable.is_file():
        raise ProbeError("the configured model or model executable is invalid")

    telemetry = Telemetry(telemetry_path, variant_id)
    started_ns = time.monotonic_ns()
    telemetry.append("phase_started", {
        "machinery": "info-intake-machinery",
        "phase": "projection-terminal-relationship-decision",
        "frozen_input_sha256": _digest(input_path.read_bytes()),
        "target_script_sha256": _digest(target_script.read_bytes()),
        "context_mode": context_mode,
        "model": model,
    })

    frozen_root = work / "frozen"
    _extract_frozen_input(input_path, frozen_root)
    manifest = _load_object(frozen_root / "manifest.json", "frozen manifest")
    expected_manifest_fields = {
        "schema_version", "attempt_path", "journal_sha256", "purpose",
        "source_path", "source_sha256", "expected_question_id",
    }
    if set(manifest) != expected_manifest_fields or manifest["schema_version"] != CONTRACT:
        raise ProbeError("frozen manifest contract is invalid")
    attempt = (frozen_root / str(manifest["attempt_path"])).resolve()
    source = (frozen_root / str(manifest["source_path"])).resolve()
    if frozen_root not in attempt.parents or frozen_root not in source.parents:
        raise ProbeError("frozen manifest paths escape the extracted input")
    journal = attempt / "interview.jsonl"
    if _digest(journal.read_bytes()) != manifest["journal_sha256"]:
        raise ProbeError("frozen journal changed")
    if _digest(source.read_bytes()) != manifest["source_sha256"]:
        raise ProbeError("frozen source changed")

    target = _load_target(target_script)
    purpose = str(manifest["purpose"])
    state, pending, completed = target.prepare_resume(attempt, purpose=purpose)
    question = pending or target._question(state, purpose=purpose, contract=target.CONTRACT)
    if completed or not isinstance(question, dict):
        raise ProbeError("frozen intake is not waiting for a terminal relationship decision")
    if (
        question.get("id") != manifest["expected_question_id"]
        or question.get("type") != "choice"
        or question.get("choices") != ["yes", "no"]
    ):
        raise ProbeError("frozen intake terminal question does not match the code contract")

    completion_context = target._relationship_completion_context(state)
    production_prompt = target._prompt(question, state)
    prompt = _model_prompt(production_prompt, context_mode, completion_context)
    schema_path = work / "model-response-schema.json"
    response_path = work / "model-response.json"
    schema_path.write_bytes(
        json.dumps(_response_schema(), indent=2, sort_keys=True).encode("utf-8") + b"\n"
    )
    model_work = work / "model-work"
    model_work.mkdir()
    command = [
        str(executable), "exec", "--ignore-user-config", "--ignore-rules",
        "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only",
        "--cd", str(model_work), "--image", str(source), "--model", model,
        "--output-schema", str(schema_path), "--output-last-message", str(response_path),
        "--color", "never", "--", prompt,
    ]
    telemetry.append("model_requested", {
        "prompt_sha256": _digest(prompt.encode("utf-8")),
        "relationship_count": completion_context["recorded_relationship_count"],
    })
    completed_model = subprocess.run(
        command, text=True, capture_output=True, check=False, timeout=300,
    )
    telemetry.append("model_finished", {
        "exit_code": completed_model.returncode,
        "stdout_sha256": _digest(completed_model.stdout.encode("utf-8")),
        "stderr_sha256": _digest(completed_model.stderr.encode("utf-8")),
    })
    if completed_model.returncode != 0:
        raise ProbeError(
            "model invocation failed: " + completed_model.stderr.strip()[-1000:]
        )
    response = _load_object(response_path, "model response")
    if set(response) != {
        "answer", "compared_relationship_ids", "decision_basis",
        "unrecorded_relationship_description",
    }:
        raise ProbeError("model response has unexpected fields")
    answer = response["answer"]
    citations = _controlled_citations(response["compared_relationship_ids"])
    if answer not in {"yes", "no"}:
        raise ProbeError("model response violates the controlled answer contract")

    supplied = False
    rejections: list[str] = []

    def provide(_prompt: str) -> str:
        nonlocal supplied
        if supplied:
            raise AnswerLimitReached("one controlled terminal decision was consumed")
        supplied = True
        return str(answer)

    try:
        target.run(
            attempt,
            source_sha256=str(manifest["source_sha256"]),
            purpose=purpose,
            input_fn=provide,
            output_fn=rejections.append,
        )
    except AnswerLimitReached:
        pass
    state_after, pending_after, completed_after = target.prepare_resume(
        attempt, purpose=purpose,
    )
    if completed_after:
        target.validate(
            attempt,
            source_sha256=str(manifest["source_sha256"]),
            purpose=purpose,
        )

    relationship_ids = {
        str(item["relationship_id"])
        for item in completion_context["recorded_relationships"]
    }
    cited_ids = set(citations)
    valid_citations = cited_ids & relationship_ids
    invalid_citations = cited_ids - relationship_ids
    decision_grounded = int(
        cited_ids == relationship_ids
        and (
            answer == "no"
            or isinstance(response["unrecorded_relationship_description"], str)
            and bool(response["unrecorded_relationship_description"].strip())
        )
    )
    coverage = (
        1000 * len(valid_citations) // len(relationship_ids)
        if relationship_ids else 1000
    )
    next_question = pending_after or target._question(
        state_after, purpose=purpose, contract=target.CONTRACT,
    )
    metrics = {
        "grounded-decision": decision_grounded,
        "relationship-index-coverage": coverage,
        "invalid-citation-count": len(invalid_citations),
        "terminal-projection-created": int(
            completed_after and (attempt / "projection.json").is_file()
        ),
        "rejected-answer-count": len(rejections),
    }
    telemetry.append("phase_finished", {
        "answer": answer,
        "completed": completed_after,
        "metrics": metrics,
        "elapsed_ms": (time.monotonic_ns() - started_ns) // 1_000_000,
    })
    _write_result(result_path, {
        "schema_version": CONTRACT,
        "variant_id": variant_id,
        "status": "completed",
        "outcome": {
            "answer": answer,
            "decision_basis": response["decision_basis"],
            "unrecorded_relationship_description": response[
                "unrecorded_relationship_description"
            ],
            "compared_relationship_ids": citations,
            "next_question_id": (
                next_question.get("id") if isinstance(next_question, dict) else None
            ),
            "projection_sha256": (
                _digest((attempt / "projection.json").read_bytes())
                if (attempt / "projection.json").is_file() else None
            ),
        },
        "metrics": metrics,
        "error": None,
    })
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    result_path_value = os.environ.get("EXPERIMENT_RESULT_PATH")
    telemetry_path_value = os.environ.get("EXPERIMENT_TELEMETRY_PATH")
    variant_id = os.environ.get("EXPERIMENT_VARIANT_ID", "unknown")
    try:
        return run()
    except Exception as error:  # noqa: BLE001 - preserve the process-boundary failure
        if telemetry_path_value:
            try:
                Telemetry(Path(telemetry_path_value), variant_id).append(
                    "phase_failed", {"error": f"{type(error).__name__}: {error}"}
                )
            except OSError:
                pass
        if result_path_value and not Path(result_path_value).exists():
            try:
                _write_result(Path(result_path_value), {
                    "schema_version": CONTRACT,
                    "variant_id": variant_id,
                    "status": "failed",
                    "outcome": {},
                    "metrics": {},
                    "error": f"{type(error).__name__}: {error}",
                })
            except OSError:
                pass
        print(
            f"Intake projection terminal probe failed: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
