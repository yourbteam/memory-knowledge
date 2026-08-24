#!/usr/bin/env python3
"""Resume an assessment package through an append-only evidence-return interview."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

CONTRACT = 1
ACTION_CHOICES = ["add-source", "unavailable", "finish"]
_SCRIPT_DIR = Path(__file__).resolve().parent


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"{name} is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


journal = _load_module("assessment_return_journal", _SCRIPT_DIR / "projection_interview.py")
package_contract = _load_module("assessment_return_package", _SCRIPT_DIR / "assessment_package.py")
projection_qualifier = _load_module(
    "assessment_return_projection_qualifier",
    _SCRIPT_DIR / "source_projection_qualification.py",
)
sufficiency_contract = _load_module(
    "assessment_return_sufficiency",
    _SCRIPT_DIR / "assessment_sufficiency.py",
)
evidence_contract = _load_module(
    "assessment_return_evidence",
    _SCRIPT_DIR / "assessment_evidence.py",
)


class AssessmentReturnError(RuntimeError):
    """The prior assessment or its append-only return state is invalid."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _load(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as error:
        raise AssessmentReturnError(f"{label} is unavailable or invalid JSON: {error}") from error
    if not isinstance(value, dict):
        raise AssessmentReturnError(f"{label} must contain one object")
    return value, raw


def _verified_package(path: Path) -> tuple[dict[str, Any], dict[str, object]]:
    path = path.resolve()
    try:
        candidate, _raw = _load(path, "assessment package")
        if candidate.get("artifact_type") == "info-intake-assessment-successor-package":
            package = verify_successor_package(path)
        else:
            package = package_contract.verify(path)
    except Exception as error:
        raise AssessmentReturnError(f"assessment package verification failed: {error}") from error
    _value, raw = _load(path, "assessment package")
    return package, {
        "path": str(path),
        "sha256": _digest(raw),
        "artifact_sha256": package.get("artifact_sha256"),
    }


def _request_bindings(package: dict[str, Any]) -> list[dict[str, object]]:
    requests = package.get("unresolved_source_requests")
    if not isinstance(requests, list) or not requests:
        raise AssessmentReturnError("assessment package has no unresolved source requests")
    bindings: list[dict[str, object]] = []
    seen_requests: set[str] = set()
    seen_gaps: set[str] = set()
    for index, request in enumerate(requests, start=1):
        if not isinstance(request, dict):
            raise AssessmentReturnError(f"source request {index} is not an object")
        request_id = request.get("request_id")
        gap_ids = request.get("gap_ids")
        if not isinstance(request_id, str) or not request_id or request_id in seen_requests:
            raise AssessmentReturnError(f"source request {index} has an invalid or duplicate identity")
        if (
            not isinstance(gap_ids, list)
            or not gap_ids
            or any(not isinstance(item, str) or not item for item in gap_ids)
            or len(set(gap_ids)) != len(gap_ids)
        ):
            raise AssessmentReturnError(f"source request {request_id} has invalid gap identities")
        overlap = seen_gaps.intersection(gap_ids)
        if overlap:
            raise AssessmentReturnError(
                f"source request {request_id} repeats gaps {sorted(overlap)!r}"
            )
        seen_requests.add(request_id)
        seen_gaps.update(gap_ids)
        bindings.append({
            "request_id": request_id,
            "request_sha256": _digest(_canonical(request)),
            "role": request.get("role"),
            "gap_ids": list(gap_ids),
            "unit_ids": list(request.get("unit_ids", [])),
            "question": request.get("question"),
            "missing_evidence": list(request.get("missing_evidence", [])),
        })
    return bindings


def _artifact(package_ref: dict[str, object], bindings: list[dict[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": CONTRACT,
        "artifact_type": "info-intake-assessment-return",
        "status": "awaiting-operator",
        "package_source": package_ref,
        "request_count": len(bindings),
        "gap_count": sum(len(item["gap_ids"]) for item in bindings),
        "requests": bindings,
        "current_request_id": bindings[0]["request_id"],
    }
    value["artifact_sha256"] = _digest(_canonical(value))
    return value


def verify(path: Path) -> dict[str, Any]:
    value, _raw = _load(path, "assessment return")
    if (
        value.get("schema_version") != CONTRACT
        or value.get("artifact_type") != "info-intake-assessment-return"
        or value.get("status") != "awaiting-operator"
    ):
        raise AssessmentReturnError("assessment return type, version, or status is invalid")
    package_ref = value.get("package_source")
    if not isinstance(package_ref, dict) or not isinstance(package_ref.get("path"), str):
        raise AssessmentReturnError("assessment return package binding is invalid")
    package, fresh_ref = _verified_package(Path(package_ref["path"]))
    bindings = _request_bindings(package)
    expected = _artifact(fresh_ref, bindings)
    if value != expected:
        raise AssessmentReturnError("assessment return or its source bindings changed")
    ledger_path = path.parent / "ledger.jsonl"
    try:
        entries = journal._read_journal(ledger_path)
    except Exception as error:
        raise AssessmentReturnError(str(error)) from error
    if len(entries) < 2:
        raise AssessmentReturnError("assessment return ledger is incomplete")
    if entries[0].get("event") != "assessment_return_started":
        raise AssessmentReturnError("assessment return ledger start event is invalid")
    if entries[1].get("event") != "assessment_return_admitted":
        raise AssessmentReturnError("assessment return ledger admission event is invalid")
    if entries[0].get("package_source") != fresh_ref:
        raise AssessmentReturnError("assessment return ledger package binding changed")
    if entries[1].get("artifact_sha256") != value["artifact_sha256"]:
        raise AssessmentReturnError("assessment return ledger artifact binding changed")
    return value


def _work_artifact(work_dir: Path) -> Path:
    return work_dir / "assessment-return.json"


def _request_by_id(artifact: dict[str, Any], request_id: str) -> dict[str, Any]:
    matches = [item for item in artifact["requests"] if item.get("request_id") == request_id]
    if len(matches) != 1:
        raise AssessmentReturnError(f"assessment return request {request_id!r} is not unique")
    return matches[0]


def _action_question(request: dict[str, Any], occurrence: int) -> dict[str, object]:
    return {
        "id": (
            f"{request['request_id']}:action"
            if occurrence == 1
            else f"{request['request_id']}:action:{occurrence}"
        ),
        "type": "choice",
        "request_id": request["request_id"],
        "choices": list(ACTION_CHOICES),
        "prompt": "What can you provide for this source request?",
        "request": request,
    }


def prepare(work_dir: Path) -> dict[str, Any]:
    artifact = verify(_work_artifact(work_dir))
    try:
        entries = journal._read_journal(work_dir / "ledger.jsonl")
    except Exception as error:
        raise AssessmentReturnError(str(error)) from error
    completed: set[str] = set()
    awaiting_source: str | None = None
    asked_ids: set[str] = set()
    answered_ids: set[str] = set()
    action_counts: dict[str, int] = {}
    bound_sources: list[dict[str, Any]] = []
    projections: list[dict[str, Any]] = []
    for entry in entries[2:]:
        event = entry.get("event")
        if event == "assessment_return_question_asked":
            question = entry.get("question")
            if not isinstance(question, dict) or not isinstance(question.get("id"), str):
                raise AssessmentReturnError("assessment return asked-question event is invalid")
            if question["id"] in asked_ids:
                raise AssessmentReturnError("assessment return question was asked more than once")
            asked_ids.add(question["id"])
        elif event == "assessment_return_answer_recorded":
            request_id = entry.get("request_id")
            question_id = entry.get("question_id")
            answer = entry.get("answer")
            if (
                not isinstance(request_id, str)
                or question_id != f"{request_id}:action"
                and not str(question_id).startswith(f"{request_id}:action:")
                or question_id not in asked_ids
                or question_id in answered_ids
                or answer not in ACTION_CHOICES
            ):
                raise AssessmentReturnError("assessment return answer event is invalid")
            _request_by_id(artifact, request_id)
            answered_ids.add(str(question_id))
            action_counts[request_id] = action_counts.get(request_id, 0) + 1
            if answer == "add-source":
                if awaiting_source is not None:
                    raise AssessmentReturnError("assessment return action order is invalid")
                awaiting_source = request_id
            else:
                if awaiting_source is not None:
                    raise AssessmentReturnError("assessment return cannot advance while a source is pending")
                completed.add(request_id)
        elif event == "assessment_return_source_bound":
            source = entry.get("source")
            if not isinstance(source, dict) or source.get("request_id") != awaiting_source:
                raise AssessmentReturnError("assessment return source binding order is invalid")
            stored_path = source.get("stored_path")
            claimed_sha = source.get("sha256")
            claimed_size = source.get("size_bytes")
            if (
                not isinstance(stored_path, str)
                or not isinstance(claimed_sha, str)
                or not isinstance(claimed_size, int)
            ):
                raise AssessmentReturnError("assessment return source binding is invalid")
            path = (work_dir / stored_path).resolve()
            if work_dir.resolve() not in path.parents:
                raise AssessmentReturnError("assessment return source binding escapes its work directory")
            try:
                raw = path.read_bytes()
            except OSError as error:
                raise AssessmentReturnError(f"assessment return source is unavailable: {error}") from error
            if _digest(raw) != claimed_sha or len(raw) != claimed_size:
                raise AssessmentReturnError("assessment return stored source changed")
            bound_sources.append(source)
            awaiting_source = None
        elif event == "assessment_return_projection_bound":
            projection = entry.get("projection")
            if not isinstance(projection, dict):
                raise AssessmentReturnError("assessment return projection binding is invalid")
            source_id = projection.get("source_id")
            matches = [item for item in bound_sources if item.get("source_id") == source_id]
            if len(matches) != 1 or any(item.get("source_id") == source_id for item in projections):
                raise AssessmentReturnError("assessment return projection source identity is invalid")
            stored_path = projection.get("stored_path")
            if not isinstance(stored_path, str):
                raise AssessmentReturnError("assessment return projection path is invalid")
            path = (work_dir / stored_path).resolve()
            if work_dir.resolve() not in path.parents:
                raise AssessmentReturnError("assessment return projection escapes its work directory")
            try:
                raw = path.read_bytes()
            except OSError as error:
                raise AssessmentReturnError(f"assessment return projection is unavailable: {error}") from error
            if _digest(raw) != projection.get("sha256"):
                raise AssessmentReturnError("assessment return projection changed")
            source = matches[0]
            item = {
                "source_id": source_id,
                "source_sha256": source["sha256"],
                "outcome": "projected",
                "record": {
                    "id": projection.get("projection_id"),
                    "method": projection.get("method"),
                    "sha256": projection.get("sha256"),
                    "coverage": projection.get("coverage"),
                },
            }
            qualified = projection_qualifier.qualify(item, raw, str(projection.get("sha256")))
            qualification = qualified.get("qualification")
            if (
                qualified.get("complete") is not True
                or not isinstance(qualification, dict)
                or qualification.get("qualification") != "readable_projection_complete"
                or qualification != projection.get("qualification")
            ):
                raise AssessmentReturnError("assessment return projection terminal is not complete")
            projections.append(projection)
        elif event in {
            "assessment_return_gap_question_asked",
            "assessment_return_gap_answer_recorded",
            "assessment_return_gap_assessment_completed",
            "assessment_return_gap_assessment_corrected",
            "assessment_return_evidence_version_created",
            "assessment_return_reassessment_created",
            "assessment_return_reassessment_corrected",
            "assessment_return_successor_package_created",
        }:
            continue
        else:
            raise AssessmentReturnError(f"assessment return ledger event {event!r} is unsupported")
    if awaiting_source is not None:
        return {
            "stage": "source-input",
            "current_request_id": awaiting_source,
            "question": None,
            "completed_request_ids": [item["request_id"] for item in artifact["requests"] if item["request_id"] in completed],
            "bound_sources": bound_sources,
            "projections": projections,
        }
    current = next((item for item in artifact["requests"] if item["request_id"] not in completed), None)
    if current is None:
        return {
            "stage": "requests-reviewed",
            "current_request_id": None,
            "question": None,
            "completed_request_ids": [item["request_id"] for item in artifact["requests"]],
            "bound_sources": bound_sources,
            "projections": projections,
        }
    return {
        "stage": "request-action",
        "current_request_id": current["request_id"],
        "question": _action_question(current, action_counts.get(current["request_id"], 0) + 1),
        "completed_request_ids": [item["request_id"] for item in artifact["requests"] if item["request_id"] in completed],
        "bound_sources": bound_sources,
        "projections": projections,
    }


def answer_action(work_dir: Path, request_id: str, answer: object) -> dict[str, Any]:
    state = prepare(work_dir)
    if state["stage"] != "request-action" or state["current_request_id"] != request_id:
        raise AssessmentReturnError(
            f"assessment return expects request {state['current_request_id']!r} at stage {state['stage']!r}"
        )
    if not isinstance(answer, str) or answer not in ACTION_CHOICES:
        raise AssessmentReturnError(
            f"assessment return action {answer!r} is invalid; choose one of {ACTION_CHOICES!r}"
        )
    question = state["question"]
    ledger_path = work_dir / "ledger.jsonl"
    journal._append(ledger_path, "assessment_return_question_asked", {"question": question})
    journal._append(ledger_path, "assessment_return_answer_recorded", {
        "question_id": question["id"],
        "request_id": request_id,
        "answer": answer,
    })
    return prepare(work_dir)


def bind_source(work_dir: Path, request_id: str, source_path: Path) -> dict[str, Any]:
    state = prepare(work_dir)
    if state["stage"] != "source-input" or state["current_request_id"] != request_id:
        raise AssessmentReturnError(
            f"assessment return expects source input for {state['current_request_id']!r} at stage {state['stage']!r}"
        )
    source_path = source_path.resolve()
    try:
        raw = source_path.read_bytes()
    except OSError as error:
        raise AssessmentReturnError(f"supplied source is unavailable: {error}") from error
    source_number = len(state["bound_sources"]) + 1
    source_id = f"return-source-{source_number:06d}"
    relative = Path("sources") / source_id
    stored_path = work_dir / relative
    stored_path.parent.mkdir(parents=True, exist_ok=True)
    if stored_path.exists():
        if stored_path.read_bytes() != raw:
            raise AssessmentReturnError(f"stored source {source_id} already exists with different bytes")
    else:
        stored_path.write_bytes(raw)
    source = {
        "source_id": source_id,
        "request_id": request_id,
        "original_path": str(source_path),
        "stored_path": relative.as_posix(),
        "sha256": _digest(raw),
        "size_bytes": len(raw),
    }
    journal._append(work_dir / "ledger.jsonl", "assessment_return_source_bound", {"source": source})
    return prepare(work_dir)


def bind_verbatim_projection(
    work_dir: Path, source_id: str, projection_path: Path,
) -> dict[str, Any]:
    state = prepare(work_dir)
    matches = [item for item in state["bound_sources"] if item.get("source_id") == source_id]
    if len(matches) != 1:
        raise AssessmentReturnError(f"bound source {source_id!r} is unavailable")
    if any(item.get("source_id") == source_id for item in state["projections"]):
        raise AssessmentReturnError(f"bound source {source_id!r} already has a projection")
    projection_path = projection_path.resolve()
    try:
        raw = projection_path.read_bytes()
    except OSError as error:
        raise AssessmentReturnError(f"supplied projection is unavailable: {error}") from error
    projection_number = len(state["projections"]) + 1
    projection_id = f"return-projection-{projection_number:06d}"
    relative = Path("projections") / f"{projection_id}.txt"
    stored_path = work_dir / relative
    stored_path.parent.mkdir(parents=True, exist_ok=True)
    if stored_path.exists():
        if stored_path.read_bytes() != raw:
            raise AssessmentReturnError(
                f"stored projection {projection_id} already exists with different bytes"
            )
    else:
        stored_path.write_bytes(raw)
    source = matches[0]
    projection_sha = _digest(raw)
    coverage = {"status": "complete", "source_units": 1, "represented_units": 1, "gaps": []}
    item = {
        "source_id": source_id,
        "source_sha256": source["sha256"],
        "outcome": "projected",
        "record": {
            "id": projection_id,
            "method": "verbatim_utf8",
            "sha256": projection_sha,
            "coverage": coverage,
        },
    }
    qualified = projection_qualifier.qualify(item, raw, projection_sha)
    qualification = qualified.get("qualification")
    if (
        qualified.get("complete") is not True
        or not isinstance(qualification, dict)
        or qualification.get("qualification") != "readable_projection_complete"
    ):
        raise AssessmentReturnError(
            f"supplied projection is not a complete verbatim representation: {qualified.get('why') or qualification}"
        )
    projection = {
        "projection_id": projection_id,
        "source_id": source_id,
        "original_path": str(projection_path),
        "stored_path": relative.as_posix(),
        "sha256": projection_sha,
        "method": "verbatim_utf8",
        "coverage": coverage,
        "qualification": qualification,
    }
    journal._append(work_dir / "ledger.jsonl", "assessment_return_projection_bound", {"projection": projection})
    return prepare(work_dir)


def _gap_queue(work_dir: Path, artifact: dict[str, Any], state: dict[str, Any]) -> list[dict[str, Any]]:
    package, _ref = _verified_package(Path(artifact["package_source"]["path"]))
    request_by_id = {item["request_id"]: item for item in artifact["requests"]}
    projections_by_request: dict[str, list[dict[str, Any]]] = {}
    source_by_id = {item["source_id"]: item for item in state["bound_sources"]}
    for projection in state["projections"]:
        source = source_by_id[projection["source_id"]]
        projections_by_request.setdefault(source["request_id"], []).append(projection)
    queue: list[dict[str, Any]] = []
    for request in package["unresolved_source_requests"]:
        request_id = request["request_id"]
        projections = projections_by_request.get(request_id, [])
        if not projections:
            continue
        bound_request = request_by_id[request_id]
        for position, gap_id in enumerate(bound_request["gap_ids"]):
            evidence = []
            for projection in projections:
                evidence.append({
                    "evidence_id": f"{projection['projection_id']}:{gap_id}",
                    "projection_id": projection["projection_id"],
                    "source_id": projection["source_id"],
                    "path": str((work_dir / projection["stored_path"]).resolve()),
                    "sha256": projection["sha256"],
                    "method": projection["method"],
                })
            queue.append({
                "schema_version": CONTRACT,
                "question_type": "assessment-return-gap",
                "purpose": package["purpose"],
                "decision": package["decision"],
                "unit": {
                    "sequence": len(queue) + 1,
                    "unit_id": gap_id,
                    "label": f"Returned evidence for {gap_id}",
                    "subject": {
                        "request_id": request_id,
                        "unit_ids": bound_request["unit_ids"],
                    },
                },
                "allowed_verdicts": list(sufficiency_contract.VERDICTS),
                "obligations": [{
                    "obligation_id": gap_id,
                    "role": bound_request["role"],
                    "question": bound_request["missing_evidence"][position],
                    "bound_status": "bound",
                    "evidence": evidence,
                }],
            })
    return queue


def _gap_replay(
    work_dir: Path, queue: list[dict[str, Any]], entries: list[dict[str, object]],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, bool]:
    accepted: list[dict[str, Any]] = []
    pending: dict[str, Any] | None = None
    completed = False
    for entry in entries[2:]:
        event = entry.get("event")
        if event in {
            "assessment_return_question_asked",
            "assessment_return_answer_recorded",
            "assessment_return_source_bound",
            "assessment_return_projection_bound",
            "assessment_return_evidence_version_created",
            "assessment_return_reassessment_created",
            "assessment_return_reassessment_corrected",
            "assessment_return_successor_package_created",
        }:
            continue
        if event == "assessment_return_gap_question_asked":
            if completed or pending is not None or len(accepted) >= len(queue):
                raise AssessmentReturnError("assessment return gap question order is invalid")
            expected = queue[len(accepted)]
            if entry.get("question") != expected:
                raise AssessmentReturnError("assessment return gap question changed")
            pending = expected
        elif event == "assessment_return_gap_answer_recorded":
            if pending is None:
                raise AssessmentReturnError("assessment return gap answer is unbound")
            raw = entry.get("raw")
            try:
                response = json.loads(raw) if isinstance(raw, str) else None
            except json.JSONDecodeError:
                response = None
            parsed, error = sufficiency_contract._validate_response(pending, response)
            if (
                entry.get("accepted") is not (error is None)
                or entry.get("parsed") != parsed
                or entry.get("error") != error
            ):
                raise AssessmentReturnError("assessment return gap answer changed")
            if parsed is not None:
                accepted.append(parsed)
            pending = None
        elif event == "assessment_return_gap_assessment_completed":
            if completed or pending is not None or len(accepted) != len(queue):
                raise AssessmentReturnError("assessment return gap completion is invalid")
            completed = True
        elif event == "assessment_return_gap_assessment_corrected":
            if not completed:
                raise AssessmentReturnError("assessment return gap correction precedes completion")
        else:
            raise AssessmentReturnError(f"assessment return gap event {event!r} is unsupported")
    return accepted, pending, completed


def _gap_artifact(
    work_dir: Path,
    artifact: dict[str, Any],
    state: dict[str, Any],
    assessments: list[dict[str, Any]],
) -> dict[str, Any]:
    return_path = _work_artifact(work_dir).resolve()
    value: dict[str, Any] = {
        "schema_version": CONTRACT,
        "artifact_type": "info-intake-assessment-return-gap-assessments",
        "status": "gap-assessment-ready",
        "assessment_return_source": {
            "path": str(return_path),
            "sha256": _digest(return_path.read_bytes()),
            "artifact_sha256": artifact["artifact_sha256"],
        },
        "projection_count": len(state["projections"]),
        "gap_count": len(assessments),
        "verdict_counts": {
            verdict: sum(
                row["verdict"] == verdict
                for item in assessments
                for row in item["assessments"]
            )
            for verdict in sufficiency_contract.VERDICTS
        },
        "assessments": assessments,
    }
    value["artifact_sha256"] = _digest(_canonical(value))
    return value


def prepare_gap_question(work_dir: Path) -> dict[str, Any]:
    artifact = verify(_work_artifact(work_dir))
    state = prepare(work_dir)
    queue = _gap_queue(work_dir, artifact, state)
    if not queue:
        raise AssessmentReturnError("assessment return has no projected gaps to assess")
    entries = journal._read_journal(work_dir / "ledger.jsonl")
    accepted, pending, completed = _gap_replay(work_dir, queue, entries)
    artifact_path = work_dir / "gap-assessments.json"
    if completed:
        value, _raw = _load(artifact_path, "assessment return gap assessments")
        expected = _gap_artifact(work_dir, artifact, state, accepted)
        if value == expected:
            return {"status": "complete", "artifact": str(artifact_path.resolve()), "result": value}
        legacy_source = value.get("assessment_return_source")
        legacy_expected = {
            "path": str(Path(artifact["package_source"]["path"]).resolve()),
            "artifact_sha256": artifact["artifact_sha256"],
        }
        if legacy_source != legacy_expected:
            raise AssessmentReturnError("assessment return gap assessment artifact changed")
        corrected_path = work_dir / "gap-assessments-v2.json"
        corrected_payload = json.dumps(expected, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        correction_entries = [
            entry for entry in entries
            if entry.get("event") == "assessment_return_gap_assessment_corrected"
        ]
        if corrected_path.exists():
            if corrected_path.read_bytes() != corrected_payload or len(correction_entries) != 1:
                raise AssessmentReturnError("assessment return corrected gap artifact changed")
        else:
            if correction_entries:
                raise AssessmentReturnError("assessment return gap correction lost its artifact")
            journal._append(work_dir / "ledger.jsonl", "assessment_return_gap_assessment_corrected", {
                "superseded_artifact_path": "gap-assessments.json",
                "artifact_path": "gap-assessments-v2.json",
                "artifact_sha256": _digest(corrected_payload),
                "reason": "assessment return source path corrected to match its bound artifact digest",
            })
            corrected_path.write_bytes(corrected_payload)
        return {"status": "complete", "artifact": str(corrected_path.resolve()), "result": expected}
    if len(accepted) == len(queue):
        value = _gap_artifact(work_dir, artifact, state, accepted)
        payload = json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        journal._append(work_dir / "ledger.jsonl", "assessment_return_gap_assessment_completed", {
            "artifact_path": "gap-assessments.json",
            "artifact_sha256": _digest(payload),
        })
        if artifact_path.exists() and artifact_path.read_bytes() != payload:
            raise AssessmentReturnError("gap assessment artifact already exists with different bytes")
        if not artifact_path.exists():
            artifact_path.write_bytes(payload)
        return {"status": "complete", "artifact": str(artifact_path.resolve()), "result": value}
    if pending is None:
        pending = queue[len(accepted)]
        journal._append(work_dir / "ledger.jsonl", "assessment_return_gap_question_asked", {"question": pending})
    return {
        "status": "question",
        "question": pending,
        "response_schema": sufficiency_contract.response_schema(pending),
        "accepted_gap_count": len(accepted),
        "total_gap_count": len(queue),
    }


def submit_gap_response(work_dir: Path, raw: str) -> dict[str, Any]:
    prepared = prepare_gap_question(work_dir)
    if prepared["status"] != "question":
        return prepared
    question = prepared["question"]
    try:
        response = json.loads(raw)
    except json.JSONDecodeError:
        response = None
    parsed, error = sufficiency_contract._validate_response(question, response)
    journal._append(work_dir / "ledger.jsonl", "assessment_return_gap_answer_recorded", {
        "raw": raw,
        "accepted": error is None,
        "parsed": parsed,
        "error": error,
    })
    if error is not None:
        return {"status": "rejected", "error": error}
    return prepare_gap_question(work_dir)


def build_evidence_version(
    work_dir: Path, prior_evidence_path: Path, sufficiency_path: Path,
) -> dict[str, Any]:
    state = prepare(work_dir)
    completed = prepare_gap_question(work_dir)
    if completed["status"] != "complete":
        raise AssessmentReturnError("assessment return gap assessment is incomplete")
    try:
        prior = evidence_contract.verify(prior_evidence_path.resolve())
        sufficiency = sufficiency_contract.verify(sufficiency_path.resolve())
    except Exception as error:
        raise AssessmentReturnError(f"assessment predecessor verification failed: {error}") from error
    prior_raw = prior_evidence_path.resolve().read_bytes()
    prior_ref = {
        "path": str(prior_evidence_path.resolve()),
        "sha256": _digest(prior_raw),
        "artifact_sha256": prior.get("artifact_sha256"),
    }
    plan_ref = prior.get("plan_source")
    obligations_ref = prior.get("obligations_source")
    if not isinstance(plan_ref, dict) or not isinstance(obligations_ref, dict):
        raise AssessmentReturnError("assessment predecessor evidence bindings are invalid")
    plan, _plan_raw = _load(Path(str(plan_ref.get("path"))), "assessment evidence plan")
    if plan.get("obligations") != obligations_ref or not isinstance(plan.get("evidence"), list):
        raise AssessmentReturnError("assessment predecessor evidence plan changed")
    gap_by_id = {item["gap_id"]: item for item in sufficiency.get("gaps", [])}
    projection_by_id = {item["projection_id"]: item for item in state["projections"]}
    additions: list[dict[str, object]] = []
    seen_ids = {item.get("evidence_id") for item in plan["evidence"] if isinstance(item, dict)}
    for response in completed["result"]["assessments"]:
        gap_id = response["unit_id"]
        gap = gap_by_id.get(gap_id)
        if not isinstance(gap, dict):
            raise AssessmentReturnError(f"returned gap {gap_id!r} is absent from the predecessor sufficiency")
        for assessment in response["assessments"]:
            for returned_id in assessment["evidence_ids"]:
                projection_id, separator, bound_gap = returned_id.partition(":")
                projection = projection_by_id.get(projection_id)
                if not separator or bound_gap != gap_id or not isinstance(projection, dict):
                    raise AssessmentReturnError(f"returned evidence identity {returned_id!r} is invalid")
                projection_path = (work_dir / projection["stored_path"]).resolve()
                try:
                    line_count = len(projection_path.read_text(encoding="utf-8").splitlines())
                except (OSError, UnicodeDecodeError) as error:
                    raise AssessmentReturnError(f"returned projection is not UTF-8 text: {error}") from error
                evidence_id = f"{gap['obligation_id']}:return:{projection_id}"
                if evidence_id in seen_ids:
                    continue
                seen_ids.add(evidence_id)
                additions.append({
                    "evidence_id": evidence_id,
                    "obligation_id": gap["obligation_id"],
                    "source": {"path": str(projection_path), "sha256": projection["sha256"]},
                    "locator": {"kind": "line-range", "start": 1, "end": line_count},
                })
    if not additions:
        raise AssessmentReturnError("assessment return produced no new evidence bindings")
    successor_plan = {
        "schema_version": plan["schema_version"],
        "obligations": plan["obligations"],
        "evidence": [*plan["evidence"], *additions],
    }
    version_dir = work_dir / "evidence-v3"
    plan_path = version_dir / "evidence-plan.json"
    output_path = version_dir / "evidence.json"
    plan_payload = json.dumps(successor_plan, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    if plan_path.exists() and plan_path.read_bytes() != plan_payload:
        raise AssessmentReturnError("assessment successor evidence plan already exists with different bytes")
    if not plan_path.exists():
        version_dir.mkdir(parents=True, exist_ok=True)
        plan_path.write_bytes(plan_payload)
    try:
        successor = evidence_contract.compile_evidence(
            Path(str(obligations_ref["path"])), plan_path, output_path,
        )
        evidence_contract.verify(output_path)
    except Exception as error:
        raise AssessmentReturnError(f"assessment successor evidence verification failed: {error}") from error
    if _digest(prior_evidence_path.resolve().read_bytes()) != prior_ref["sha256"]:
        raise AssessmentReturnError("assessment predecessor evidence changed during versioning")
    successor_ref = {
        "path": str(output_path.resolve()),
        "sha256": _digest(output_path.read_bytes()),
        "artifact_sha256": successor.get("artifact_sha256"),
    }
    entries = journal._read_journal(work_dir / "ledger.jsonl")
    version_events = [entry for entry in entries if entry.get("event") == "assessment_return_evidence_version_created"]
    event_payload = {
        "predecessor": prior_ref,
        "successor": successor_ref,
        "added_evidence_ids": [item["evidence_id"] for item in additions],
    }
    if version_events:
        if len(version_events) != 1 or any(version_events[0].get(key) != value for key, value in event_payload.items()):
            raise AssessmentReturnError("assessment evidence version ledger binding changed")
    else:
        journal._append(work_dir / "ledger.jsonl", "assessment_return_evidence_version_created", event_payload)
    return {"status": "complete", **event_payload}


def _reassessed_findings(
    findings: list[dict[str, Any]],
    gap_by_id: dict[str, dict[str, Any]],
    gap_assessments: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str], list[str], list[str]]:
    resolved = [
        item["unit_id"]
        for item in gap_assessments["assessments"]
        if item["assessments"][0]["verdict"] == "sufficient"
    ]
    assessed = [item["unit_id"] for item in gap_assessments["assessments"]]
    if len(set(assessed)) != len(assessed) or any(gap_id not in gap_by_id for gap_id in assessed):
        raise AssessmentReturnError("assessment return gap assessment identities are invalid")
    result = deepcopy(findings)
    finding_by_unit = {item["unit_id"]: item for item in result}
    changed: list[str] = []
    for gap_id in resolved:
        gap = gap_by_id[gap_id]
        unit_id = gap["unit_id"]
        finding = finding_by_unit.get(unit_id)
        if not isinstance(finding, dict) or gap_id not in finding.get("gap_ids", []):
            raise AssessmentReturnError(f"resolved gap {gap_id!r} is not bound to its predecessor finding")
        index = finding["gap_ids"].index(gap_id)
        finding["gap_ids"].pop(index)
        finding["missing_evidence"].pop(index)
        if finding["verdict"] == "incomplete" and not finding["gap_ids"]:
            raise AssessmentReturnError(
                f"unit {unit_id!r} became evidence-complete and requires a full verdict reassessment"
            )
        if finding["verdict"] == "incomplete":
            obligations = []
            for remaining_gap_id in finding["gap_ids"]:
                obligation_id = gap_by_id[remaining_gap_id]["obligation_id"]
                if obligation_id not in obligations:
                    obligations.append(obligation_id)
            finding["reason"] = f"Evidence is incomplete for {', '.join(obligations)}."
        if unit_id not in changed:
            changed.append(unit_id)
    unchanged = [item["unit_id"] for item in findings if item["unit_id"] not in changed]
    return result, resolved, changed, unchanged


def build_reassessment(work_dir: Path) -> dict[str, Any]:
    return_artifact = verify(_work_artifact(work_dir))
    package, package_ref = _verified_package(Path(return_artifact["package_source"]["path"]))
    gap_result = prepare_gap_question(work_dir)
    if gap_result["status"] != "complete":
        raise AssessmentReturnError("assessment return gap assessment is incomplete")
    sufficiency_path = Path(_sufficiency_ref(package)["path"])
    try:
        sufficiency = sufficiency_contract.verify(sufficiency_path)
    except Exception as error:
        raise AssessmentReturnError(f"predecessor sufficiency verification failed: {error}") from error
    gap_by_id = {item["gap_id"]: item for item in sufficiency["gaps"]}
    findings, resolved, changed, unchanged = _reassessed_findings(
        package["findings"], gap_by_id, gap_result["result"],
    )
    entries = journal._read_journal(work_dir / "ledger.jsonl")
    evidence_events = [entry for entry in entries if entry.get("event") == "assessment_return_evidence_version_created"]
    if len(evidence_events) != 1:
        raise AssessmentReturnError("assessment successor evidence version is unavailable")
    evidence_ref = evidence_events[0].get("successor")
    if not isinstance(evidence_ref, dict):
        raise AssessmentReturnError("assessment successor evidence binding is invalid")
    evidence_path = Path(str(evidence_ref.get("path")))
    try:
        evidence_contract.verify(evidence_path)
    except Exception as error:
        raise AssessmentReturnError(f"assessment successor evidence verification failed: {error}") from error
    affected = []
    for item in gap_result["result"]["assessments"]:
        unit_id = gap_by_id[item["unit_id"]]["unit_id"]
        if unit_id not in affected:
            affected.append(unit_id)
    before_by_id = {item["unit_id"]: item for item in package["findings"]}
    after_by_id = {item["unit_id"]: item for item in findings}
    preservation = {
        unit_id: {
            "before_sha256": _digest(_canonical(before_by_id[unit_id])),
            "after_sha256": _digest(_canonical(after_by_id[unit_id])),
        }
        for unit_id in unchanged
    }
    if any(item["before_sha256"] != item["after_sha256"] for item in preservation.values()):
        raise AssessmentReturnError("assessment unrelated finding preservation failed")
    gap_path = Path(gap_result["artifact"])
    value: dict[str, Any] = {
        "schema_version": CONTRACT,
        "artifact_type": "info-intake-assessment-reassessment",
        "status": "reassessment-ready",
        "predecessor_package": package_ref,
        "successor_evidence": evidence_ref,
        "gap_assessments": {
            "path": str(gap_path.resolve()),
            "sha256": _digest(gap_path.read_bytes()),
            "artifact_sha256": gap_result["result"]["artifact_sha256"],
        },
        "unit_count": len(findings),
        "affected_unit_ids": affected,
        "changed_unit_ids": changed,
        "unchanged_unit_ids": unchanged,
        "resolved_gap_ids": resolved,
        "remaining_gap_ids": [
            gap_id for finding in findings for gap_id in finding["gap_ids"]
        ],
        "unchanged_finding_sha256": preservation,
        "findings": findings,
    }
    value["artifact_sha256"] = _digest(_canonical(value))
    payload = json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    primary = work_dir / "reassessment-v1.json"
    output = primary
    correction = False
    if primary.exists() and primary.read_bytes() != payload:
        output = work_dir / "reassessment-v2.json"
        correction = True
    if output.exists() and output.read_bytes() != payload:
        raise AssessmentReturnError("assessment reassessment already exists with different bytes")
    event_payload = {
        "artifact_path": output.name,
        "artifact_sha256": _digest(payload),
        "changed_unit_ids": changed,
        "resolved_gap_ids": resolved,
    }
    event_name = (
        "assessment_return_reassessment_corrected"
        if correction
        else "assessment_return_reassessment_created"
    )
    if correction:
        event_payload["superseded_artifact_path"] = "reassessment-v1.json"
        event_payload["reason"] = "changed finding reason rebuilt from remaining exact gap obligations"
    events = [entry for entry in entries if entry.get("event") == event_name]
    if events:
        if len(events) != 1 or any(events[0].get(key) != item for key, item in event_payload.items()):
            raise AssessmentReturnError("assessment reassessment ledger binding changed")
    else:
        journal._append(work_dir / "ledger.jsonl", event_name, event_payload)
    if not output.exists():
        output.write_bytes(payload)
    return {"status": "complete", "artifact": str(output.resolve()), "result": value}


def _artifact_ref(path: Path, value: dict[str, Any]) -> dict[str, object]:
    raw = path.read_bytes()
    return {
        "path": str(path.resolve()),
        "sha256": _digest(raw),
        "artifact_sha256": value.get("artifact_sha256"),
    }


def _sufficiency_ref(package: dict[str, Any]) -> dict[str, Any]:
    sources = package.get("sources")
    if not isinstance(sources, dict):
        raise AssessmentReturnError("assessment package sources are invalid")
    ref = sources.get("sufficiency_catalog", sources.get("sufficiency"))
    if not isinstance(ref, dict) or not isinstance(ref.get("path"), str):
        raise AssessmentReturnError("assessment package sufficiency source is invalid")
    return ref


def _remaining_requests(
    requests: list[dict[str, Any]],
    gap_by_id: dict[str, dict[str, Any]],
    remaining_gap_ids: list[str],
) -> list[dict[str, Any]]:
    remaining = set(remaining_gap_ids)
    if len(remaining) != len(remaining_gap_ids) or any(item not in gap_by_id for item in remaining):
        raise AssessmentReturnError("successor package remaining gap identities are invalid")
    result: list[dict[str, Any]] = []
    covered: list[str] = []
    for request in requests:
        gap_ids = request.get("gap_ids", [])
        missing = request.get("missing_evidence", [])
        if len(gap_ids) != len(missing):
            raise AssessmentReturnError(
                f"source request {request.get('request_id')!r} gap and evidence counts differ"
            )
        kept = [(gap_id, detail) for gap_id, detail in zip(gap_ids, missing) if gap_id in remaining]
        if not kept:
            continue
        unit_ids: list[str] = []
        for gap_id, _detail in kept:
            unit_id = gap_by_id[gap_id].get("unit_id")
            if not isinstance(unit_id, str) or not unit_id:
                raise AssessmentReturnError(f"remaining gap {gap_id!r} has no unit identity")
            if unit_id not in unit_ids:
                unit_ids.append(unit_id)
        successor = deepcopy(request)
        successor["gap_ids"] = [item[0] for item in kept]
        successor["missing_evidence"] = [item[1] for item in kept]
        successor["unit_ids"] = unit_ids
        result.append(successor)
        covered.extend(successor["gap_ids"])
    missing_ids = sorted(remaining - set(covered))
    duplicate_ids = sorted({item for item in covered if covered.count(item) > 1})
    unknown_ids = sorted(set(covered) - remaining)
    if missing_ids or duplicate_ids or unknown_ids:
        raise AssessmentReturnError(
            "successor source requests do not exactly cover remaining gaps: "
            f"missing={missing_ids!r}, duplicate={duplicate_ids!r}, unknown={unknown_ids!r}"
        )
    return result


def _successor_package_value(work_dir: Path) -> dict[str, Any]:
    return_artifact = verify(_work_artifact(work_dir))
    reassessment_result = build_reassessment(work_dir)
    reassessment = reassessment_result["result"]
    reassessment_path = Path(reassessment_result["artifact"])
    package, package_ref = _verified_package(Path(return_artifact["package_source"]["path"]))
    sufficiency_source = _sufficiency_ref(package)
    sufficiency_path = Path(sufficiency_source["path"])
    try:
        sufficiency = sufficiency_contract.verify(sufficiency_path)
    except Exception as error:
        raise AssessmentReturnError(f"predecessor sufficiency verification failed: {error}") from error
    gap_by_id = {item["gap_id"]: item for item in sufficiency["gaps"]}
    requests = _remaining_requests(
        package["unresolved_source_requests"], gap_by_id, reassessment["remaining_gap_ids"]
    )
    findings = reassessment["findings"]
    verdict_counts: dict[str, int] = {}
    for finding in findings:
        verdict = finding["verdict"]
        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
    misaligned = [item for item in findings if item["verdict"] == "misaligned"]
    incomplete = [item for item in findings if item["verdict"] == "incomplete"]
    assessment_return_path = _work_artifact(work_dir)
    gap_path = Path(reassessment["gap_assessments"]["path"])
    evidence_path = Path(reassessment["successor_evidence"]["path"])
    value: dict[str, Any] = {
        "schema_version": CONTRACT,
        "artifact_type": "info-intake-assessment-successor-package",
        "status": "assessment-ready",
        "lineage": {
            "predecessor_package": package_ref,
            "assessment_return": _artifact_ref(assessment_return_path, return_artifact),
            "successor_evidence": _artifact_ref(evidence_path, evidence_contract.verify(evidence_path)),
            "gap_assessments": _artifact_ref(gap_path, json.loads(gap_path.read_text())),
            "reassessment": _artifact_ref(reassessment_path, reassessment),
        },
        "sources": {
            "charter": package["sources"]["charter"],
            "evidence": reassessment["successor_evidence"],
            "sufficiency_catalog": sufficiency_source,
        },
        "purpose": package["purpose"],
        "decision": package["decision"],
        "summary": {
            "unit_count": len(findings),
            "verdict_counts": verdict_counts,
            "confirmed_misalignment_count": len(misaligned),
            "incomplete_unit_count": len(incomplete),
            "prior_gap_count": sum(len(item["gap_ids"]) for item in package["findings"]),
            "resolved_gap_count": len(reassessment["resolved_gap_ids"]),
            "gap_count": len(reassessment["remaining_gap_ids"]),
            "changed_unit_count": len(reassessment["changed_unit_ids"]),
            "unchanged_unit_count": len(reassessment["unchanged_unit_ids"]),
            "source_request_count": len(requests),
        },
        "findings": findings,
        "confirmed_misalignments": misaligned,
        "unresolved_source_requests": requests,
        "assessment_return_handoff": {
            "status": "ready" if requests else "complete",
            "recommended_skill": "info-intake-machinery",
            "next_request_id": requests[0]["request_id"] if requests else None,
            "resolved_gap_ids": reassessment["resolved_gap_ids"],
        },
        "prototype_handoff": {
            "status": "ready" if misaligned else "no-confirmed-misalignment",
            "recommended_skill": "prototype-driven-implementation",
            "objective": "Resolve each confirmed misalignment without weakening incomplete findings.",
            "captured_cases": [
                {
                    "case_id": f"assessment-{item['unit_id']}",
                    "unit_id": item["unit_id"],
                    "verdict": item["verdict"],
                    "measure": item["measure"],
                    "evidence_ids": item["evidence_ids"],
                }
                for item in misaligned
            ],
        },
        "experiment_handoff": {
            "status": "ready" if misaligned else "not-needed",
            "recommended_skill": "experiment-machinery",
            "candidate_case_ids": [f"assessment-{item['unit_id']}" for item in misaligned],
            "evaluation": (
                "A candidate must correct the measured misalignment and preserve all other findings."
            ),
        },
    }
    value["artifact_sha256"] = _digest(_canonical(value))
    return value


def verify_successor_package(path: Path) -> dict[str, Any]:
    path = path.resolve()
    value, _raw = _load(path, "assessment successor package")
    if (
        value.get("schema_version") != CONTRACT
        or value.get("artifact_type") != "info-intake-assessment-successor-package"
        or value.get("status") != "assessment-ready"
    ):
        raise AssessmentReturnError("assessment successor package type, version, or status is invalid")
    lineage = value.get("lineage")
    if not isinstance(lineage, dict):
        raise AssessmentReturnError("assessment successor package lineage is invalid")
    return_ref = lineage.get("assessment_return")
    if not isinstance(return_ref, dict) or not isinstance(return_ref.get("path"), str):
        raise AssessmentReturnError("assessment successor package return binding is invalid")
    work_dir = Path(return_ref["path"]).resolve().parent
    expected = _successor_package_value(work_dir)
    if value != expected:
        raise AssessmentReturnError("assessment successor package or its source bindings changed")
    events = [
        entry for entry in journal._read_journal(work_dir / "ledger.jsonl")
        if entry.get("event") == "assessment_return_successor_package_created"
    ]
    try:
        artifact_path = str(path.relative_to(work_dir))
    except ValueError as error:
        raise AssessmentReturnError(
            "assessment successor package escapes its assessment return directory"
        ) from error
    event_payload = {
        "artifact_path": artifact_path,
        "artifact_sha256": _digest(path.read_bytes()),
        "resolved_gap_ids": value["assessment_return_handoff"]["resolved_gap_ids"],
        "next_request_id": value["assessment_return_handoff"]["next_request_id"],
    }
    if len(events) != 1 or any(events[0].get(key) != item for key, item in event_payload.items()):
        raise AssessmentReturnError("assessment successor package ledger binding changed")
    return value


def build_successor_package(work_dir: Path) -> dict[str, Any]:
    value = _successor_package_value(work_dir)
    output = work_dir / "successor-package-v1" / "assessment-package.json"
    payload = json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    if output.exists() and output.read_bytes() != payload:
        raise AssessmentReturnError("assessment successor package already exists with different bytes")
    output.parent.mkdir(parents=True, exist_ok=True)
    if not output.exists():
        output.write_bytes(payload)
    entries = journal._read_journal(work_dir / "ledger.jsonl")
    event_payload = {
        "artifact_path": str(output.relative_to(work_dir)),
        "artifact_sha256": _digest(payload),
        "resolved_gap_ids": value["assessment_return_handoff"]["resolved_gap_ids"],
        "next_request_id": value["assessment_return_handoff"]["next_request_id"],
    }
    events = [
        entry for entry in entries
        if entry.get("event") == "assessment_return_successor_package_created"
    ]
    if events:
        if len(events) != 1 or any(events[0].get(key) != item for key, item in event_payload.items()):
            raise AssessmentReturnError("assessment successor package ledger binding changed")
    else:
        journal._append(
            work_dir / "ledger.jsonl", "assessment_return_successor_package_created", event_payload
        )
    return verify_successor_package(output)


def start(package_path: Path, work_dir: Path) -> dict[str, Any]:
    package, package_ref = _verified_package(package_path)
    bindings = _request_bindings(package)
    artifact = _artifact(package_ref, bindings)
    payload = json.dumps(artifact, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    work_dir.mkdir(parents=True, exist_ok=True)
    path = work_dir / "assessment-return.json"
    ledger_path = work_dir / "ledger.jsonl"
    if path.exists():
        if path.read_bytes() != payload:
            raise AssessmentReturnError("assessment return already exists with different bytes")
        return verify(path)
    if ledger_path.exists():
        raise AssessmentReturnError("assessment return ledger exists without its artifact")
    journal._append(ledger_path, "assessment_return_started", {"package_source": package_ref})
    journal._append(ledger_path, "assessment_return_admitted", {
        "artifact_sha256": artifact["artifact_sha256"],
        "request_ids": [item["request_id"] for item in bindings],
        "gap_count": artifact["gap_count"],
    })
    path.write_bytes(payload)
    return verify(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("start")
    create.add_argument("--package", type=Path, required=True)
    create.add_argument("--work", type=Path, required=True)
    check = commands.add_parser("verify")
    check.add_argument("artifact", type=Path)
    next_question = commands.add_parser("next")
    next_question.add_argument("--work", type=Path, required=True)
    answer = commands.add_parser("answer")
    answer.add_argument("--work", type=Path, required=True)
    answer.add_argument("--request-id", required=True)
    answer.add_argument("--action", required=True)
    bind = commands.add_parser("bind-source")
    bind.add_argument("--work", type=Path, required=True)
    bind.add_argument("--request-id", required=True)
    bind.add_argument("--source", type=Path, required=True)
    projection = commands.add_parser("bind-verbatim-projection")
    projection.add_argument("--work", type=Path, required=True)
    projection.add_argument("--source-id", required=True)
    projection.add_argument("--projection", type=Path, required=True)
    gap_next = commands.add_parser("next-gap")
    gap_next.add_argument("--work", type=Path, required=True)
    gap_submit = commands.add_parser("submit-gap")
    gap_submit.add_argument("--work", type=Path, required=True)
    gap_submit.add_argument("--response", required=True)
    evidence = commands.add_parser("build-evidence")
    evidence.add_argument("--work", type=Path, required=True)
    evidence.add_argument("--prior-evidence", type=Path, required=True)
    evidence.add_argument("--sufficiency", type=Path, required=True)
    reassess = commands.add_parser("reassess")
    reassess.add_argument("--work", type=Path, required=True)
    successor = commands.add_parser("build-successor")
    successor.add_argument("--work", type=Path, required=True)
    successor_check = commands.add_parser("verify-successor")
    successor_check.add_argument("artifact", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "start":
            result = start(args.package, args.work)
        elif args.command == "verify":
            result = verify(args.artifact)
        elif args.command == "next":
            result = prepare(args.work)
        elif args.command == "answer":
            result = answer_action(args.work, args.request_id, args.action)
        elif args.command == "bind-source":
            result = bind_source(args.work, args.request_id, args.source)
        elif args.command == "bind-verbatim-projection":
            result = bind_verbatim_projection(args.work, args.source_id, args.projection)
        elif args.command == "next-gap":
            result = prepare_gap_question(args.work)
        elif args.command == "submit-gap":
            result = submit_gap_response(args.work, args.response)
        elif args.command == "build-evidence":
            result = build_evidence_version(args.work, args.prior_evidence, args.sufficiency)
        elif args.command == "reassess":
            result = build_reassessment(args.work)
        elif args.command == "build-successor":
            result = build_successor_package(args.work)
        else:
            result = verify_successor_package(args.artifact)
    except AssessmentReturnError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
