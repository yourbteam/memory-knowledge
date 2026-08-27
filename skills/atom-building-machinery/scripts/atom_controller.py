#!/usr/bin/env python3
"""Enforce the evidence-gated lifecycle of one approved implementation atom."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

CONTRACT = 1
SHA256 = re.compile(r"^[0-9a-f]{64}$")
EXPERIMENT_STAGES = ["run-probes", "compose-winners", "final-validation"]
EXPERIMENT_VERDICTS = {"passed", "failed", "inconclusive"}
CASE_VERDICTS = {"satisfied", "not-satisfied", "cannot-assess"}
REQUEST_FIELDS = {
    "schema_version",
    "atomic_step_id",
    "outcome",
    "practical_value",
    "stopping_condition",
    "allowed_paths",
    "captured_cases",
}
CASE_FIELDS = {"case_id", "source_ref", "sha256", "kind", "expected_outcome"}
FINAL_FIELDS = {
    "schema_version",
    "status",
    "atomic_step_id",
    "assembly_sha256",
    "verdict",
    "cases",
    "promotion_applied",
}
FINAL_CASE_FIELDS = {"case_id", "verdict", "reason", "evidence_pointers"}
SUMMARY_FIELDS = {
    "schema_version",
    "status",
    "atomic_step_id",
    "verdict",
    "final_verdict_sha256",
    "stages",
    "promotion_applied",
}
STAGE_FIELDS = {
    "schema_version",
    "stage",
    "status",
    "exit_code",
    "output",
    "evidence",
    "evidence_sha256",
    "result",
    "result_sha256",
    "promotion_applied",
}
PROMOTION_FIELDS = {
    "schema_version",
    "status",
    "atomic_step_id",
    "controller",
    "experiment_event_sha256",
    "experiment_assembly_sha256",
    "changed_paths",
    "evidence_pointers",
}
VALIDATION_FIELDS = {
    "schema_version",
    "status",
    "atomic_step_id",
    "promotion_event_sha256",
    "cases",
}
LEDGER_FIELDS = {"sequence", "event", "previous_event_sha256", "payload"}
EXPERIMENT_EVENT_FIELDS = {
    "experiment_path",
    "summary_sha256",
    "final_verdict_sha256",
    "assembly_sha256",
    "verdict",
}
PROMOTION_EVENT_FIELDS = {
    "receipt_path",
    "receipt_sha256",
    "experiment_event_sha256",
    "assembly_sha256",
    "changed_paths",
}
VALIDATION_EVENT_FIELDS = {
    "receipt_path",
    "receipt_sha256",
    "promotion_event_sha256",
    "verdict",
}


class AtomError(RuntimeError):
    """The atom lifecycle cannot safely advance."""

    def __init__(self, stage: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage


def _document(value: object) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _load(path: Path, label: str, stage: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AtomError(stage, f"{label} is unavailable or invalid JSON: {error}") from None
    if type(value) is not dict:
        raise AtomError(stage, f"{label} is {type(value).__name__}; provide one JSON object")
    return value


def _exact(value: object, label: str, fields: set[str], stage: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise AtomError(stage, f"{label} is {type(value).__name__}; provide one object")
    missing = sorted(fields - value.keys())
    extra = sorted(value.keys() - fields)
    if missing or extra:
        raise AtomError(
            stage,
            f"{label} has missing fields {missing} and unexpected fields {extra}; "
            "add the missing fields and remove the unexpected fields",
        )
    return value


def _nonempty(value: object, label: str, stage: str) -> str:
    if type(value) is not str or not value.strip():
        raise AtomError(stage, f"{label} is {value!r}; provide one nonempty string")
    return value


def _sha(value: object, label: str, stage: str) -> str:
    if type(value) is not str or not SHA256.fullmatch(value):
        raise AtomError(stage, f"{label} is {value!r}; provide 64 lowercase hexadecimal characters")
    return value


def _strings(value: object, label: str, stage: str, *, nonempty: bool = True) -> list[str]:
    if type(value) is not list or (nonempty and not value):
        qualifier = "nonempty " if nonempty else ""
        raise AtomError(stage, f"{label} is {value!r}; provide one {qualifier}ordered list of strings")
    result = []
    for index, item in enumerate(value):
        result.append(_nonempty(item, f"{label}[{index}]", stage))
    if len(set(result)) != len(result):
        raise AtomError(stage, f"{label} contains duplicates; keep every value exactly once")
    return result


def _relative_path(value: str, label: str, stage: str) -> str:
    path = Path(value)
    if path.is_absolute() or value in {"", "."} or ".." in path.parts:
        raise AtomError(stage, f"{label} is {value!r}; provide one safe repository-relative path")
    return path.as_posix().rstrip("/")


def _validate_request(value: object) -> dict[str, Any]:
    stage = "validate-request"
    request = _exact(value, "atom request", REQUEST_FIELDS, stage)
    if request["schema_version"] != CONTRACT or type(request["schema_version"]) is not int:
        raise AtomError(stage, f"schema_version is {request['schema_version']!r}; require integer 1")
    for field in ("atomic_step_id", "outcome", "practical_value", "stopping_condition"):
        _nonempty(request[field], field, stage)
    allowed = _strings(request["allowed_paths"], "allowed_paths", stage)
    normalized_paths = [_relative_path(item, f"allowed_paths[{index}]", stage) for index, item in enumerate(allowed)]
    if len(set(normalized_paths)) != len(normalized_paths):
        raise AtomError(stage, "allowed_paths normalize to duplicates; keep every boundary exactly once")
    cases = request["captured_cases"]
    if type(cases) is not list or not cases:
        raise AtomError(stage, "captured_cases is empty or not a list; provide immutable success and failure cases")
    normalized_cases = []
    case_ids = []
    kinds = []
    for index, raw in enumerate(cases):
        case = _exact(raw, f"captured_cases[{index}]", CASE_FIELDS, stage)
        case_id = _nonempty(case["case_id"], f"captured_cases[{index}].case_id", stage)
        kind = case["kind"]
        if kind not in {"success", "failure"}:
            raise AtomError(stage, f"captured_cases[{index}].kind is {kind!r}; choose 'success' or 'failure'")
        normalized_cases.append(
            {
                "case_id": case_id,
                "source_ref": _nonempty(case["source_ref"], f"captured_cases[{index}].source_ref", stage),
                "sha256": _sha(case["sha256"], f"captured_cases[{index}].sha256", stage),
                "kind": kind,
                "expected_outcome": _nonempty(
                    case["expected_outcome"], f"captured_cases[{index}].expected_outcome", stage
                ),
            }
        )
        case_ids.append(case_id)
        kinds.append(kind)
    if len(set(case_ids)) != len(case_ids):
        raise AtomError(stage, "captured_cases contains duplicate case_id values; keep every case exactly once")
    if set(kinds) != {"success", "failure"}:
        raise AtomError(stage, "captured_cases must include at least one success and one failure case")
    return {**request, "allowed_paths": normalized_paths, "captured_cases": normalized_cases}


def _write_new(path: Path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return _digest(payload)


def _read_ledger(run: Path) -> tuple[list[dict[str, Any]], list[str]]:
    path = run / "ledger.jsonl"
    try:
        lines = path.read_bytes().splitlines(keepends=True)
    except OSError as error:
        raise AtomError("load-run", f"ledger is unavailable: {error}") from None
    records: list[dict[str, Any]] = []
    hashes: list[str] = []
    previous: str | None = None
    for index, line in enumerate(lines):
        try:
            record = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise AtomError("load-run", f"ledger record {index + 1} is invalid JSON: {error}") from None
        record = _exact(record, f"ledger record {index + 1}", LEDGER_FIELDS, "load-run")
        if record["sequence"] != index + 1:
            raise AtomError("load-run", f"ledger record {index + 1} sequence is {record['sequence']!r}; require {index + 1}")
        if record["previous_event_sha256"] != previous:
            raise AtomError(
                "load-run",
                f"ledger record {index + 1} previous_event_sha256 is {record['previous_event_sha256']!r}; "
                f"require {previous!r}",
            )
        if type(record["event"]) is not str or type(record["payload"]) is not dict:
            raise AtomError("load-run", f"ledger record {index + 1} has invalid event or payload types")
        records.append(record)
        hashes.append(_digest(line))
        previous = hashes[-1]
    if not records or records[0]["event"] != "atom-started":
        raise AtomError("load-run", "ledger has no atom-started first record; restore the original run")
    return records, hashes


def _append(run: Path, event: str, payload: dict[str, Any]) -> str:
    records, hashes = _read_ledger(run)
    record = {
        "sequence": len(records) + 1,
        "event": event,
        "previous_event_sha256": hashes[-1],
        "payload": payload,
    }
    line = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    with (run / "ledger.jsonl").open("ab") as stream:
        stream.write(line)
        stream.flush()
        os.fsync(stream.fileno())
    return _digest(line)


def _request(run: Path) -> dict[str, Any]:
    value = _validate_request(_load(run / "inputs" / "atom-request.json", "stored atom request", "load-run"))
    records, _ = _read_ledger(run)
    root = _exact(
        records[0]["payload"],
        "atom-started payload",
        {"atomic_step_id", "request_sha256"},
        "load-run",
    )
    if root["atomic_step_id"] != value["atomic_step_id"]:
        raise AtomError(
            "load-run",
            f"atom-started atomic_step_id is {root['atomic_step_id']!r}; "
            f"require preserved request identity {value['atomic_step_id']!r}",
        )
    expected = _sha(root["request_sha256"], "atom-started request_sha256", "load-run")
    actual = _digest((run / "inputs" / "atom-request.json").read_bytes())
    if actual != expected:
        raise AtomError("load-run", f"stored atom request has SHA-256 {actual}; require recorded {expected}")
    return value


def _unchanged(path_value: object, expected: object, label: str) -> None:
    path_text = str(path_value) if isinstance(path_value, Path) else _nonempty(path_value, f"{label} path", "load-run")
    expected_sha256 = _sha(expected, f"{label} SHA-256", "load-run")
    path = Path(path_text)
    if path.is_symlink() or not path.is_file():
        raise AtomError("load-run", f"{label} is unavailable or linked at {path}; restore the recorded regular file")
    actual = _digest(path.read_bytes())
    if actual != expected_sha256:
        raise AtomError("load-run", f"{label} has SHA-256 {actual}; require recorded {expected_sha256}")


def _state(run: Path) -> dict[str, Any]:
    request = _request(run)
    records, hashes = _read_ledger(run)
    stage = "experiment"
    next_skill = "experiment-machinery"
    current_experiment = None
    current_promotion = None
    for record, event_sha256 in zip(records[1:], hashes[1:]):
        if record["event"] == "experiment-recorded":
            if stage != "experiment":
                raise AtomError("load-run", f"experiment-recorded appears during {stage!r}; restore the valid event order")
            payload = _exact(record["payload"], "experiment-recorded payload", EXPERIMENT_EVENT_FIELDS, "load-run")
            experiment_path = Path(_nonempty(payload["experiment_path"], "experiment_path", "load-run"))
            _unchanged(
                experiment_path / "development-probe-summary.json",
                payload["summary_sha256"],
                "recorded experiment summary",
            )
            _unchanged(
                experiment_path / "final-verdict.json",
                payload["final_verdict_sha256"],
                "recorded experiment verdict",
            )
            _sha(payload["assembly_sha256"], "experiment assembly_sha256", "load-run")
            _verify_assembly(experiment_path, request, payload["assembly_sha256"])
            if payload["verdict"] not in EXPERIMENT_VERDICTS:
                raise AtomError("load-run", f"experiment verdict is {payload['verdict']!r}; restore a declared verdict")
            if payload["verdict"] == "passed":
                stage = "promotion"
                next_skill = "prototype-driven-implementation"
                current_experiment = {**payload, "event_sha256": event_sha256}
                current_promotion = None
            else:
                stage = "experiment"
                next_skill = "experiment-machinery"
                current_experiment = None
                current_promotion = None
        elif record["event"] == "promotion-recorded":
            if stage != "promotion" or current_experiment is None:
                raise AtomError("load-run", f"promotion-recorded appears during {stage!r}; restore the valid event order")
            payload = _exact(record["payload"], "promotion-recorded payload", PROMOTION_EVENT_FIELDS, "load-run")
            _unchanged(payload["receipt_path"], payload["receipt_sha256"], "recorded promotion receipt")
            if payload["experiment_event_sha256"] != current_experiment["event_sha256"]:
                raise AtomError("load-run", "promotion receipt is not bound to the current passed experiment event")
            if payload["assembly_sha256"] != current_experiment["assembly_sha256"]:
                raise AtomError("load-run", "promotion receipt is not bound to the current proven assembly")
            stage = "validation"
            next_skill = "atom-building-machinery"
            current_promotion = {**payload, "event_sha256": event_sha256}
        elif record["event"] == "validation-recorded":
            if stage != "validation" or current_promotion is None:
                raise AtomError("load-run", f"validation-recorded appears during {stage!r}; restore the valid event order")
            payload = _exact(record["payload"], "validation-recorded payload", VALIDATION_EVENT_FIELDS, "load-run")
            _unchanged(payload["receipt_path"], payload["receipt_sha256"], "recorded validation receipt")
            if payload["promotion_event_sha256"] != current_promotion["event_sha256"]:
                raise AtomError("load-run", "validation receipt is not bound to the current promotion event")
            if payload["verdict"] not in {"passed", "failed"}:
                raise AtomError("load-run", f"validation verdict is {payload['verdict']!r}; restore 'passed' or 'failed'")
            if payload["verdict"] == "passed":
                stage = "complete"
                next_skill = None
            else:
                stage = "experiment"
                next_skill = "experiment-machinery"
                current_experiment = None
                current_promotion = None
        else:
            raise AtomError("load-run", f"unknown ledger event {record['event']!r}; restore a controller-written event")
    return {
        "schema_version": CONTRACT,
        "atomic_step_id": request["atomic_step_id"],
        "stage": stage,
        "next_skill": next_skill,
        "event_count": len(records),
        "latest_event_sha256": hashes[-1],
        "current_experiment": current_experiment,
        "current_promotion": current_promotion,
    }


def start(request_path: Path, run: Path) -> dict[str, Any]:
    request_path = request_path.absolute()
    run = run.absolute()
    if run.exists() and (not run.is_dir() or any(run.iterdir())):
        raise AtomError("start", f"run directory must be new or empty: {run}")
    request = _validate_request(_load(request_path, "atom request", "validate-request"))
    run.mkdir(parents=True, exist_ok=True)
    request_sha256 = _write_new(run / "inputs" / "atom-request.json", _document(request))
    first = {
        "sequence": 1,
        "event": "atom-started",
        "previous_event_sha256": None,
        "payload": {"atomic_step_id": request["atomic_step_id"], "request_sha256": request_sha256},
    }
    _write_new(run / "ledger.jsonl", json.dumps(first, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n")
    return _state(run)


def _validate_stage_receipts(value: object) -> None:
    stage = "record-experiment"
    if type(value) is not list or len(value) != len(EXPERIMENT_STAGES):
        raise AtomError(stage, f"stages is not the complete ordered set {EXPERIMENT_STAGES!r}")
    for index, raw in enumerate(value):
        receipt = _exact(raw, f"stages[{index}]", STAGE_FIELDS, stage)
        expected_stage = EXPERIMENT_STAGES[index]
        if receipt["schema_version"] != CONTRACT or receipt["stage"] != expected_stage:
            raise AtomError(stage, f"stages[{index}] does not identify schema 1 stage {expected_stage!r}")
        if receipt["status"] != "completed" or receipt["exit_code"] != 0:
            raise AtomError(stage, f"stage {expected_stage!r} did not complete successfully")
        if receipt["promotion_applied"] is not False:
            raise AtomError(stage, f"stage {expected_stage!r} applied promotion; experiments must remain isolated")
        for field in ("output", "evidence", "evidence_sha256", "result", "result_sha256"):
            if field.endswith("sha256"):
                _sha(receipt[field], f"stages[{index}].{field}", stage)
            else:
                _nonempty(receipt[field], f"stages[{index}].{field}", stage)


def _verify_assembly(experiment: Path, request: dict[str, Any], expected_sha256: str) -> None:
    stage = "record-experiment"
    verifier = (
        Path(__file__).resolve().parents[2]
        / "experiment-machinery"
        / "scripts"
        / "development_probe_compose.py"
    )
    if verifier.is_symlink() or not verifier.is_file():
        raise AtomError(stage, f"Experiment Machinery assembly verifier is unavailable at {verifier}")
    assembly = experiment / "composition" / "assembly"
    completed = subprocess.run(
        [sys.executable, str(verifier), "verify", str(assembly)],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "verifier returned no diagnostic"
        raise AtomError(stage, f"Experiment Machinery refused the recorded assembly: {detail}")
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise AtomError(stage, f"assembly verifier returned invalid JSON: {error}") from None
    expected_result = {
        "status": "verified",
        "atomic_step_id": request["atomic_step_id"],
        "assembly_sha256": expected_sha256,
        "promotion_applied": False,
    }
    if result != expected_result:
        raise AtomError(stage, f"assembly verifier returned {result!r}; require {expected_result!r}")
    manifest = _load(
        assembly / "development-manifest.json",
        "verified assembly development manifest",
        stage,
    )
    atomic_step = manifest.get("atomic_step")
    if type(atomic_step) is not dict:
        raise AtomError(stage, "verified assembly manifest has no atomic_step object")
    captured = atomic_step.get("captured_cases")
    if type(captured) is not list:
        raise AtomError(stage, "verified assembly manifest has no captured_cases list")
    expected_cases = [
        {
            "id": case["case_id"],
            "source": case["source_ref"],
            "sha256": case["sha256"],
            "kind": case["kind"],
            "expected_outcome": case["expected_outcome"],
        }
        for case in request["captured_cases"]
    ]
    expected_atom = {
        "id": request["atomic_step_id"],
        "outcome": request["outcome"],
        "practical_value": request["practical_value"],
        "stopping_condition": request["stopping_condition"],
        "captured_cases": expected_cases,
    }
    if atomic_step != expected_atom:
        raise AtomError(stage, "verified assembly atom contract differs from the approved atom request")


def record_experiment(run: Path, experiment: Path) -> dict[str, Any]:
    run = run.absolute()
    experiment = experiment.absolute()
    state = _state(run)
    if state["stage"] != "experiment":
        raise AtomError("record-experiment", f"current stage is {state['stage']!r}; require 'experiment'")
    request = _request(run)
    summary_path = experiment / "development-probe-summary.json"
    final_path = experiment / "final-verdict.json"
    summary = _exact(_load(summary_path, "development-probe summary", "record-experiment"), "summary", SUMMARY_FIELDS, "record-experiment")
    final = _exact(_load(final_path, "final verdict", "record-experiment"), "final verdict", FINAL_FIELDS, "record-experiment")
    problems = []
    for label, value in (("summary", summary), ("final verdict", final)):
        if value["schema_version"] != CONTRACT or type(value["schema_version"]) is not int:
            problems.append(f"{label} schema_version must be integer 1")
        if value["status"] != "completed":
            problems.append(f"{label} status must be 'completed'")
        if value["atomic_step_id"] != request["atomic_step_id"]:
            problems.append(f"{label} atomic_step_id must be {request['atomic_step_id']!r}")
        if value["promotion_applied"] is not False:
            problems.append(f"{label} promotion_applied must be false")
    if summary["verdict"] not in EXPERIMENT_VERDICTS or final["verdict"] not in EXPERIMENT_VERDICTS:
        problems.append(f"verdict must be one of {sorted(EXPERIMENT_VERDICTS)!r}")
    if summary["verdict"] != final["verdict"]:
        problems.append("summary verdict must equal final verdict")
    final_sha256 = _digest(final_path.read_bytes())
    if summary["final_verdict_sha256"] != final_sha256:
        problems.append(f"summary final_verdict_sha256 must be {final_sha256}")
    _sha(final["assembly_sha256"], "final verdict assembly_sha256", "record-experiment")
    _validate_stage_receipts(summary["stages"])
    _verify_assembly(experiment, request, final["assembly_sha256"])
    cases = final["cases"]
    if type(cases) is not list:
        problems.append("final verdict cases must be one ordered list")
        cases = []
    declared_ids = [item["case_id"] for item in request["captured_cases"]]
    observed_ids = []
    for index, raw in enumerate(cases):
        case = _exact(raw, f"final verdict cases[{index}]", FINAL_CASE_FIELDS, "record-experiment")
        observed_ids.append(case["case_id"])
        if case["verdict"] not in CASE_VERDICTS:
            problems.append(f"case {case['case_id']!r} verdict must be one of {sorted(CASE_VERDICTS)!r}")
        _nonempty(case["reason"], f"case {case['case_id']!r} reason", "record-experiment")
        _strings(case["evidence_pointers"], f"case {case['case_id']!r} evidence_pointers", "record-experiment")
    if observed_ids != declared_ids:
        problems.append(f"final verdict cases are {observed_ids!r}; require exact order {declared_ids!r}")
    if final["verdict"] == "passed" and any(item.get("verdict") != "satisfied" for item in cases):
        problems.append("passed verdict requires every case verdict to be 'satisfied'")
    if problems:
        raise AtomError("record-experiment", "; ".join(problems))
    payload = {
        "experiment_path": str(experiment),
        "summary_sha256": _digest(summary_path.read_bytes()),
        "final_verdict_sha256": final_sha256,
        "assembly_sha256": final["assembly_sha256"],
        "verdict": final["verdict"],
    }
    _append(run, "experiment-recorded", payload)
    return _state(run)


def _within(path: str, allowed: list[str]) -> bool:
    return any(path == boundary or path.startswith(boundary + "/") for boundary in allowed)


def record_promotion(run: Path, receipt_path: Path) -> dict[str, Any]:
    run = run.absolute()
    state = _state(run)
    if state["stage"] != "promotion":
        raise AtomError("record-promotion", f"current stage is {state['stage']!r}; require 'promotion'")
    request = _request(run)
    receipt_path = receipt_path.absolute()
    receipt = _exact(_load(receipt_path, "promotion receipt", "record-promotion"), "promotion receipt", PROMOTION_FIELDS, "record-promotion")
    current = state["current_experiment"]
    problems = []
    if receipt["schema_version"] != CONTRACT or type(receipt["schema_version"]) is not int:
        problems.append("schema_version must be integer 1")
    if receipt["status"] != "promoted":
        problems.append("status must be 'promoted'")
    if receipt["atomic_step_id"] != request["atomic_step_id"]:
        problems.append(f"atomic_step_id must be {request['atomic_step_id']!r}")
    if receipt["controller"] != "prototype-driven-implementation":
        problems.append("controller must be 'prototype-driven-implementation'")
    if receipt["experiment_event_sha256"] != current["event_sha256"]:
        problems.append(f"experiment_event_sha256 must be {current['event_sha256']!r}")
    if receipt["experiment_assembly_sha256"] != current["assembly_sha256"]:
        problems.append(f"experiment_assembly_sha256 must be {current['assembly_sha256']!r}")
    changed = _strings(receipt["changed_paths"], "changed_paths", "record-promotion")
    normalized = [_relative_path(item, f"changed_paths[{index}]", "record-promotion") for index, item in enumerate(changed)]
    outside = [item for item in normalized if not _within(item, request["allowed_paths"])]
    if outside:
        problems.append(f"changed_paths {outside!r} fall outside allowed_paths {request['allowed_paths']!r}")
    _strings(receipt["evidence_pointers"], "evidence_pointers", "record-promotion")
    if problems:
        raise AtomError("record-promotion", "; ".join(problems))
    payload = {
        "receipt_path": str(receipt_path),
        "receipt_sha256": _digest(receipt_path.read_bytes()),
        "experiment_event_sha256": current["event_sha256"],
        "assembly_sha256": current["assembly_sha256"],
        "changed_paths": normalized,
    }
    _append(run, "promotion-recorded", payload)
    return _state(run)


def record_validation(run: Path, receipt_path: Path) -> dict[str, Any]:
    run = run.absolute()
    state = _state(run)
    if state["stage"] != "validation":
        raise AtomError("record-validation", f"current stage is {state['stage']!r}; require 'validation'")
    request = _request(run)
    receipt_path = receipt_path.absolute()
    receipt = _exact(_load(receipt_path, "validation receipt", "record-validation"), "validation receipt", VALIDATION_FIELDS, "record-validation")
    problems = []
    if receipt["schema_version"] != CONTRACT or type(receipt["schema_version"]) is not int:
        problems.append("schema_version must be integer 1")
    if receipt["status"] != "completed":
        problems.append("status must be 'completed'")
    if receipt["atomic_step_id"] != request["atomic_step_id"]:
        problems.append(f"atomic_step_id must be {request['atomic_step_id']!r}")
    promotion = state["current_promotion"]
    if receipt["promotion_event_sha256"] != promotion["event_sha256"]:
        problems.append(f"promotion_event_sha256 must be {promotion['event_sha256']!r}")
    cases = receipt["cases"]
    if type(cases) is not list:
        problems.append("cases must be one ordered list")
        cases = []
    declared_ids = [item["case_id"] for item in request["captured_cases"]]
    observed_ids = []
    statuses = []
    for index, raw in enumerate(cases):
        case = _exact(raw, f"cases[{index}]", FINAL_CASE_FIELDS, "record-validation")
        case_id = _nonempty(case["case_id"], f"cases[{index}].case_id", "record-validation")
        observed_ids.append(case_id)
        if case["verdict"] not in CASE_VERDICTS:
            problems.append(f"case {case_id!r} verdict must be one of {sorted(CASE_VERDICTS)!r}")
        statuses.append(case["verdict"])
        _nonempty(case["reason"], f"case {case_id!r} reason", "record-validation")
        _strings(case["evidence_pointers"], f"case {case_id!r} evidence_pointers", "record-validation")
    if observed_ids != declared_ids:
        problems.append(f"cases are {observed_ids!r}; require exact order {declared_ids!r}")
    if problems:
        raise AtomError("record-validation", "; ".join(problems))
    verdict = "passed" if statuses and all(status == "satisfied" for status in statuses) else "failed"
    payload = {
        "receipt_path": str(receipt_path),
        "receipt_sha256": _digest(receipt_path.read_bytes()),
        "promotion_event_sha256": promotion["event_sha256"],
        "verdict": verdict,
    }
    _append(run, "validation-recorded", payload)
    return _state(run)


def authorize_next(run: Path) -> dict[str, Any]:
    state = _state(run.absolute())
    if state["stage"] != "complete":
        raise AtomError(
            "authorize-next",
            f"current stage is {state['stage']!r}; finish the reported next_skill before selecting another atom",
        )
    return {
        "schema_version": CONTRACT,
        "atomic_step_id": state["atomic_step_id"],
        "authorized": True,
        "proof_event_sha256": state["latest_event_sha256"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    start_parser = commands.add_parser("start")
    start_parser.add_argument("request", type=Path)
    start_parser.add_argument("run", type=Path)
    status_parser = commands.add_parser("status")
    status_parser.add_argument("run", type=Path)
    experiment_parser = commands.add_parser("record-experiment")
    experiment_parser.add_argument("run", type=Path)
    experiment_parser.add_argument("experiment", type=Path)
    promotion_parser = commands.add_parser("record-promotion")
    promotion_parser.add_argument("run", type=Path)
    promotion_parser.add_argument("receipt", type=Path)
    validation_parser = commands.add_parser("record-validation")
    validation_parser.add_argument("run", type=Path)
    validation_parser.add_argument("receipt", type=Path)
    next_parser = commands.add_parser("authorize-next")
    next_parser.add_argument("run", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "start":
            result = start(args.request, args.run)
        elif args.command == "status":
            result = _state(args.run.absolute())
        elif args.command == "record-experiment":
            result = record_experiment(args.run, args.experiment)
        elif args.command == "record-promotion":
            result = record_promotion(args.run, args.receipt)
        elif args.command == "record-validation":
            result = record_validation(args.run, args.receipt)
        else:
            result = authorize_next(args.run)
    except (AtomError, OSError) as error:
        stage = error.stage if isinstance(error, AtomError) else "runtime"
        print(f"Atom Building Machinery refused at {stage}: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
