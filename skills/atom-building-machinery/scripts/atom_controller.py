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
EVIDENCE_FIELDS = {"case_id", "path", "sha256"}
FILE_REFERENCE_FIELDS = {"path", "sha256"}
BASELINE_FIELDS = {"schema_version", "atomic_step_id", "repository_root", "allowed_paths", "files"}
SNAPSHOT_FILE_FIELDS = {"path", "sha256", "size", "mode"}
CHANGE_SURFACE_FIELDS = {
    "schema_version",
    "atomic_step_id",
    "repository_root",
    "baseline_sha256",
    "changes",
}
REVIEW_FIELDS = {
    "schema_version",
    "status",
    "verdict",
    "change_surface_sha256",
    "blocking_findings",
}
FINAL_FIELDS = {
    "schema_version",
    "status",
    "atomic_step_id",
    "assembly_sha256",
    "verdict",
    "cases",
    "promotion_applied",
}
EXPERIMENT_CASE_FIELDS = {"case_id", "verdict", "reason", "evidence_pointers"}
VALIDATION_CASE_FIELDS = {"case_id", "verdict", "reason", "evidence"}
CASE_EVIDENCE_FIELDS = {"case_id", "evidence"}
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
LEGACY_PROMOTION_FIELDS = {
    "schema_version",
    "status",
    "atomic_step_id",
    "controller",
    "experiment_event_sha256",
    "experiment_assembly_sha256",
    "changed_paths",
    "evidence",
}
PROMOTION_FIELDS = LEGACY_PROMOTION_FIELDS | {"change_surface", "review"}
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
LEGACY_PROMOTION_EVENT_FIELDS = {
    "receipt_path",
    "receipt_sha256",
    "experiment_event_sha256",
    "assembly_sha256",
    "changed_paths",
    "evidence",
}
PROMOTION_EVENT_FIELDS = LEGACY_PROMOTION_EVENT_FIELDS | {"change_surface", "review"}
VALIDATION_EVENT_FIELDS = {
    "receipt_path",
    "receipt_sha256",
    "promotion_event_sha256",
    "verdict",
    "case_evidence",
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


def _evidence(
    value: object,
    label: str,
    stage: str,
    case_ids: set[str],
    *,
    base: Path | None = None,
    required_case_id: str | None = None,
) -> list[dict[str, str]]:
    if type(value) is not list or not value:
        raise AtomError(stage, f"{label} is {value!r}; provide one nonempty ordered evidence list")
    normalized = []
    identities = []
    for index, raw in enumerate(value):
        item_label = f"{label}[{index}]"
        item = _exact(raw, item_label, EVIDENCE_FIELDS, stage)
        case_id = _nonempty(item["case_id"], f"{item_label}.case_id", stage)
        if case_id not in case_ids:
            raise AtomError(stage, f"{item_label}.case_id is {case_id!r}; require one declared captured case")
        if required_case_id is not None and case_id != required_case_id:
            raise AtomError(stage, f"{item_label}.case_id is {case_id!r}; require {required_case_id!r}")
        path_text = _nonempty(item["path"], f"{item_label}.path", stage)
        path = Path(path_text)
        if not path.is_absolute():
            if base is None:
                raise AtomError(stage, f"{item_label}.path is relative; restore the recorded absolute evidence path")
            path = base / path
        path = path.absolute()
        expected = _sha(item["sha256"], f"{item_label}.sha256", stage)
        if path.is_symlink() or not path.is_file():
            raise AtomError(stage, f"{label} is unavailable or linked at {path}; provide the recorded regular file")
        actual = _digest(path.read_bytes())
        if actual != expected:
            raise AtomError(stage, f"{label} has SHA-256 {actual} at {path}; require recorded {expected}")
        identity = (case_id, str(path))
        if identity in identities:
            raise AtomError(stage, f"{label} repeats case {case_id!r} path {str(path)!r}; keep each proof once")
        identities.append(identity)
        normalized.append({"case_id": case_id, "path": str(path), "sha256": expected})
    return normalized


def _case_evidence(
    value: object,
    label: str,
    stage: str,
    declared_case_ids: list[str],
) -> list[dict[str, object]]:
    if type(value) is not list:
        raise AtomError(stage, f"{label} is not one ordered list")
    normalized = []
    observed = []
    case_ids = set(declared_case_ids)
    for index, raw in enumerate(value):
        item = _exact(raw, f"{label}[{index}]", CASE_EVIDENCE_FIELDS, stage)
        case_id = _nonempty(item["case_id"], f"{label}[{index}].case_id", stage)
        observed.append(case_id)
        normalized.append(
            {
                "case_id": case_id,
                "evidence": _evidence(
                    item["evidence"],
                    f"{label}[{index}].evidence",
                    stage,
                    case_ids,
                    required_case_id=case_id,
                ),
            }
        )
    if observed != declared_case_ids:
        raise AtomError(stage, f"{label} cases are {observed!r}; require exact order {declared_case_ids!r}")
    return normalized


def _relative_path(value: str, label: str, stage: str) -> str:
    path = Path(value)
    if path.is_absolute() or value in {"", "."} or ".." in path.parts:
        raise AtomError(stage, f"{label} is {value!r}; provide one safe repository-relative path")
    return path.as_posix().rstrip("/")


def _snapshot(repository_root: Path, allowed_paths: list[str], stage: str) -> list[dict[str, object]]:
    files: dict[str, dict[str, object]] = {}
    for boundary in allowed_paths:
        target = repository_root / boundary
        if not target.exists():
            continue
        if target.is_symlink():
            raise AtomError(stage, f"allowed path {boundary!r} is linked; require repository-owned regular files")
        if target.is_file():
            candidates = [target]
        elif target.is_dir():
            candidates = sorted(target.rglob("*"))
        else:
            raise AtomError(stage, f"allowed path {boundary!r} has an unsupported file type")
        for candidate in candidates:
            relative = candidate.relative_to(repository_root).as_posix()
            if candidate.is_symlink():
                raise AtomError(stage, f"allowed path contains linked entry {relative!r}; require regular files")
            if candidate.is_dir():
                continue
            if not candidate.is_file():
                raise AtomError(stage, f"allowed path contains unsupported entry {relative!r}")
            payload = candidate.read_bytes()
            files[relative] = {
                "path": relative,
                "sha256": _digest(payload),
                "size": len(payload),
                "mode": candidate.stat().st_mode & 0o777,
            }
    return [files[path] for path in sorted(files)]


def _baseline_document(request: dict[str, Any], repository_root: Path) -> dict[str, object]:
    return {
        "schema_version": CONTRACT,
        "atomic_step_id": request["atomic_step_id"],
        "repository_root": str(repository_root),
        "allowed_paths": request["allowed_paths"],
        "files": _snapshot(repository_root, request["allowed_paths"], "start"),
    }


def _validate_snapshot_files(value: object, label: str, stage: str) -> list[dict[str, object]]:
    if type(value) is not list:
        raise AtomError(stage, f"{label} is not one ordered list")
    normalized = []
    paths = []
    for index, raw in enumerate(value):
        item = _exact(raw, f"{label}[{index}]", SNAPSHOT_FILE_FIELDS, stage)
        path = _relative_path(_nonempty(item["path"], f"{label}[{index}].path", stage), f"{label}[{index}].path", stage)
        sha256 = _sha(item["sha256"], f"{label}[{index}].sha256", stage)
        size = item["size"]
        if type(size) is not int or size < 0:
            raise AtomError(stage, f"{label}[{index}].size is {size!r}; provide one nonnegative integer")
        mode = item["mode"]
        if type(mode) is not int or not 0 <= mode <= 0o777:
            raise AtomError(stage, f"{label}[{index}].mode is {mode!r}; provide one permission-mode integer")
        paths.append(path)
        normalized.append({"path": path, "sha256": sha256, "size": size, "mode": mode})
    if paths != sorted(set(paths)):
        raise AtomError(stage, f"{label} paths are not unique lexical order; restore the controller-written snapshot")
    return normalized


def _baseline(run: Path, request: dict[str, Any]) -> tuple[dict[str, Any], str] | None:
    records, _ = _read_ledger(run)
    root = records[0]["payload"]
    legacy_fields = {"atomic_step_id", "request_sha256"}
    current_fields = legacy_fields | {"baseline_sha256", "repository_root"}
    if set(root) == legacy_fields:
        return None
    root = _exact(root, "atom-started payload", current_fields, "load-run")
    baseline_path = run / "inputs" / "change-baseline.json"
    _unchanged(baseline_path, root["baseline_sha256"], "recorded change baseline")
    value = _exact(_load(baseline_path, "recorded change baseline", "load-run"), "change baseline", BASELINE_FIELDS, "load-run")
    if value["schema_version"] != CONTRACT or type(value["schema_version"]) is not int:
        raise AtomError("load-run", f"change baseline schema_version is {value['schema_version']!r}; require integer 1")
    if value["atomic_step_id"] != request["atomic_step_id"]:
        raise AtomError("load-run", "change baseline atomic_step_id differs from the preserved atom request")
    repository_root = _nonempty(value["repository_root"], "change baseline repository_root", "load-run")
    if repository_root != root["repository_root"] or not Path(repository_root).is_absolute():
        raise AtomError("load-run", "change baseline repository_root differs from the atom-started boundary")
    if value["allowed_paths"] != request["allowed_paths"]:
        raise AtomError("load-run", "change baseline allowed_paths differ from the preserved atom request")
    value["files"] = _validate_snapshot_files(value["files"], "change baseline files", "load-run")
    return value, root["baseline_sha256"]


def _derive_change_surface(run: Path, request: dict[str, Any]) -> dict[str, object]:
    context = _baseline(run, request)
    if context is None:
        raise AtomError("change-surface", "this run predates change baselines; start a fresh run with the upgraded controller")
    baseline, baseline_sha256 = context
    repository_root = Path(baseline["repository_root"])
    current = _snapshot(repository_root, request["allowed_paths"], "change-surface")
    before = {item["path"]: item for item in baseline["files"]}
    after = {item["path"]: item for item in current}
    changes = []
    for path in sorted(set(before) | set(after)):
        prior = before.get(path)
        present = after.get(path)
        if (
            prior is not None
            and present is not None
            and prior["sha256"] == present["sha256"]
            and prior["mode"] == present["mode"]
        ):
            continue
        kind = "added" if prior is None else "deleted" if present is None else "changed"
        changes.append(
            {
                "path": path,
                "kind": kind,
                "before_sha256": None if prior is None else prior["sha256"],
                "after_sha256": None if present is None else present["sha256"],
                "before_mode": None if prior is None else prior["mode"],
                "after_mode": None if present is None else present["mode"],
            }
        )
    return {
        "schema_version": CONTRACT,
        "atomic_step_id": request["atomic_step_id"],
        "repository_root": str(repository_root),
        "baseline_sha256": baseline_sha256,
        "changes": changes,
    }


def _file_reference(value: object, label: str, stage: str, *, base: Path | None = None) -> dict[str, str]:
    item = _exact(value, label, FILE_REFERENCE_FIELDS, stage)
    path_text = _nonempty(item["path"], f"{label}.path", stage)
    path = Path(path_text)
    if not path.is_absolute():
        if base is None:
            raise AtomError(stage, f"{label}.path is relative; restore the recorded absolute path")
        path = base / path
    path = path.absolute()
    expected = _sha(item["sha256"], f"{label}.sha256", stage)
    if path.is_symlink() or not path.is_file():
        raise AtomError(stage, f"{label} is unavailable or linked at {path}; provide the recorded regular file")
    actual = _digest(path.read_bytes())
    if actual != expected:
        raise AtomError(stage, f"{label} has SHA-256 {actual} at {path}; require recorded {expected}")
    return {"path": str(path), "sha256": expected}


def _validate_review(path: Path, surface_sha256: str, label: str, stage: str) -> None:
    review = _exact(_load(path, label, stage), label, REVIEW_FIELDS, stage)
    if review["schema_version"] != CONTRACT or type(review["schema_version"]) is not int:
        raise AtomError(stage, f"{label} schema_version is {review['schema_version']!r}; require integer 1")
    if review["status"] != "completed" or review["verdict"] != "passed":
        raise AtomError(stage, f"{label} status/verdict is {review['status']!r}/{review['verdict']!r}; require completed/passed")
    if review["change_surface_sha256"] != surface_sha256:
        raise AtomError(
            stage,
            f"{label} change_surface_sha256 is {review['change_surface_sha256']!r}; require {surface_sha256!r}",
        )
    if review["blocking_findings"] != []:
        raise AtomError(stage, f"{label} blocking_findings is {review['blocking_findings']!r}; resolve every finding")


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
    root = records[0]["payload"]
    legacy_fields = {"atomic_step_id", "request_sha256"}
    current_fields = legacy_fields | {"baseline_sha256", "repository_root"}
    if frozenset(root) not in {frozenset(legacy_fields), frozenset(current_fields)}:
        _exact(root, "atom-started payload", current_fields, "load-run")
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
    _baseline(run, value)
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
    next_skill = "prototype-driven-implementation"
    required_capability = "experiment-machinery"
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
                required_capability = "promotion"
                current_experiment = {**payload, "event_sha256": event_sha256}
                current_promotion = None
            else:
                stage = "experiment"
                next_skill = "prototype-driven-implementation"
                required_capability = "experiment-machinery"
                current_experiment = None
                current_promotion = None
        elif record["event"] == "promotion-recorded":
            if stage != "promotion" or current_experiment is None:
                raise AtomError("load-run", f"promotion-recorded appears during {stage!r}; restore the valid event order")
            baseline = _baseline(run, request)
            event_fields = LEGACY_PROMOTION_EVENT_FIELDS if baseline is None else PROMOTION_EVENT_FIELDS
            payload = _exact(record["payload"], "promotion-recorded payload", event_fields, "load-run")
            _unchanged(payload["receipt_path"], payload["receipt_sha256"], "recorded promotion receipt")
            if payload["experiment_event_sha256"] != current_experiment["event_sha256"]:
                raise AtomError("load-run", "promotion receipt is not bound to the current passed experiment event")
            if payload["assembly_sha256"] != current_experiment["assembly_sha256"]:
                raise AtomError("load-run", "promotion receipt is not bound to the current proven assembly")
            _evidence(
                payload["evidence"],
                "recorded promotion evidence",
                "load-run",
                {case["case_id"] for case in request["captured_cases"]},
            )
            if baseline is not None:
                surface = _file_reference(payload["change_surface"], "recorded promotion change surface", "load-run")
                review = _file_reference(payload["review"], "recorded promotion review", "load-run")
                _validate_review(
                    Path(review["path"]),
                    surface["sha256"],
                    "recorded promotion review",
                    "load-run",
                )
            stage = "validation"
            next_skill = "prototype-driven-implementation"
            required_capability = "real-path-validation"
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
            _case_evidence(
                payload["case_evidence"],
                "recorded validation evidence",
                "load-run",
                [case["case_id"] for case in request["captured_cases"]],
            )
            if payload["verdict"] == "passed":
                stage = "complete"
                next_skill = None
                required_capability = None
            else:
                stage = "experiment"
                next_skill = "prototype-driven-implementation"
                required_capability = "experiment-machinery"
                current_experiment = None
                current_promotion = None
        else:
            raise AtomError("load-run", f"unknown ledger event {record['event']!r}; restore a controller-written event")
    return {
        "schema_version": CONTRACT,
        "atomic_step_id": request["atomic_step_id"],
        "stage": stage,
        "next_skill": next_skill,
        "required_capability": required_capability,
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
    repository_root = Path.cwd().resolve()
    baseline = _baseline_document(request, repository_root)
    run.mkdir(parents=True, exist_ok=True)
    request_sha256 = _write_new(run / "inputs" / "atom-request.json", _document(request))
    baseline_sha256 = _write_new(run / "inputs" / "change-baseline.json", _document(baseline))
    first = {
        "sequence": 1,
        "event": "atom-started",
        "previous_event_sha256": None,
        "payload": {
            "atomic_step_id": request["atomic_step_id"],
            "request_sha256": request_sha256,
            "baseline_sha256": baseline_sha256,
            "repository_root": str(repository_root),
        },
    }
    _write_new(run / "ledger.jsonl", json.dumps(first, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n")
    return _state(run)


def change_surface(run: Path, output: Path) -> dict[str, Any]:
    run = run.absolute()
    output = output.absolute()
    request = _request(run)
    surface = _derive_change_surface(run, request)
    sha256 = _write_new(output, _document(surface))
    return {
        "schema_version": CONTRACT,
        "atomic_step_id": request["atomic_step_id"],
        "change_surface": {"path": str(output), "sha256": sha256},
        "changed_paths": [item["path"] for item in surface["changes"]],
    }


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
        case = _exact(raw, f"final verdict cases[{index}]", EXPERIMENT_CASE_FIELDS, "record-experiment")
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
    baseline = _baseline(run, request)
    receipt_path = receipt_path.absolute()
    receipt_fields = LEGACY_PROMOTION_FIELDS if baseline is None else PROMOTION_FIELDS
    receipt = _exact(
        _load(receipt_path, "promotion receipt", "record-promotion"),
        "promotion receipt",
        receipt_fields,
        "record-promotion",
    )
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
    evidence = _evidence(
        receipt["evidence"],
        "evidence",
        "record-promotion",
        {case["case_id"] for case in request["captured_cases"]},
        base=receipt_path.parent,
    )
    surface = None
    review = None
    if baseline is not None:
        surface = _file_reference(
            receipt["change_surface"],
            "change surface",
            "record-promotion",
            base=receipt_path.parent,
        )
        recorded_surface = _exact(
            _load(Path(surface["path"]), "change surface", "record-promotion"),
            "change surface",
            CHANGE_SURFACE_FIELDS,
            "record-promotion",
        )
        actual_surface = _derive_change_surface(run, request)
        if recorded_surface != actual_surface:
            problems.append("change surface is stale or substituted; regenerate it from the current allowed paths")
        actual_paths = [item["path"] for item in actual_surface["changes"]]
        if normalized != actual_paths:
            problems.append(
                f"changed_paths are {normalized!r}; require exact derived change surface {actual_paths!r}"
            )
        review = _file_reference(
            receipt["review"],
            "review",
            "record-promotion",
            base=receipt_path.parent,
        )
        _validate_review(Path(review["path"]), surface["sha256"], "review", "record-promotion")
    if problems:
        raise AtomError("record-promotion", "; ".join(problems))
    payload = {
        "receipt_path": str(receipt_path),
        "receipt_sha256": _digest(receipt_path.read_bytes()),
        "experiment_event_sha256": current["event_sha256"],
        "assembly_sha256": current["assembly_sha256"],
        "changed_paths": normalized,
        "evidence": evidence,
    }
    if surface is not None and review is not None:
        payload["change_surface"] = surface
        payload["review"] = review
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
    case_evidence = []
    declared_case_set = set(declared_ids)
    for index, raw in enumerate(cases):
        case = _exact(raw, f"cases[{index}]", VALIDATION_CASE_FIELDS, "record-validation")
        case_id = _nonempty(case["case_id"], f"cases[{index}].case_id", "record-validation")
        observed_ids.append(case_id)
        if case["verdict"] not in CASE_VERDICTS:
            problems.append(f"case {case_id!r} verdict must be one of {sorted(CASE_VERDICTS)!r}")
        statuses.append(case["verdict"])
        _nonempty(case["reason"], f"case {case_id!r} reason", "record-validation")
        case_evidence.append(
            {
                "case_id": case_id,
                "evidence": _evidence(
                    case["evidence"],
                    f"case {case_id!r} evidence",
                    "record-validation",
                    declared_case_set,
                    base=receipt_path.parent,
                    required_case_id=case_id,
                ),
            }
        )
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
        "case_evidence": case_evidence,
    }
    _append(run, "validation-recorded", payload)
    return _state(run)


def authorize_next(run: Path) -> dict[str, Any]:
    state = _state(run.absolute())
    if state["stage"] != "complete":
        raise AtomError(
            "authorize-next",
            f"current stage is {state['stage']!r}; finish the reported required_capability before selecting another atom",
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
    surface_parser = commands.add_parser("change-surface")
    surface_parser.add_argument("run", type=Path)
    surface_parser.add_argument("output", type=Path)
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
        elif args.command == "change-surface":
            result = change_surface(args.run, args.output)
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
