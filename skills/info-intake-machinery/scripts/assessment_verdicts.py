#!/usr/bin/env python3
"""Produce grounded per-unit assessment verdicts from sufficient evidence."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

CONTRACT = 1
MODEL_VERDICTS = ("aligned", "misaligned")
ALL_VERDICTS = (*MODEL_VERDICTS, "incomplete")
RESPONSE_FIELDS = {"unit_id", "verdict", "measure", "reason", "evidence_ids"}
_SCRIPT_DIR = Path(__file__).resolve().parent


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"{name} is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


journal = _load_module("assessment_verdict_journal", _SCRIPT_DIR / "projection_interview.py")
evidence_contract = _load_module("assessment_verdict_evidence", _SCRIPT_DIR / "assessment_evidence.py")
sufficiency_contract = _load_module("assessment_verdict_sufficiency", _SCRIPT_DIR / "assessment_sufficiency.py")


class AssessmentVerdictError(RuntimeError):
    """Raised when verdict evidence, response, or append-only state is invalid."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as error:
        raise AssessmentVerdictError(f"{label} is unavailable or invalid JSON: {error}") from error
    if not isinstance(value, dict):
        raise AssessmentVerdictError(f"{label} must contain one object")
    return value, raw


def _ref(path: Path, raw: bytes, value: dict[str, Any]) -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "sha256": _digest(raw),
        "artifact_sha256": value.get("artifact_sha256"),
    }


def _verify_sources(evidence_path: Path, sufficiency_path: Path):
    try:
        evidence_contract.verify(evidence_path)
        sufficiency_contract.verify(sufficiency_path)
    except Exception as error:
        raise AssessmentVerdictError(str(error)) from error
    evidence, evidence_raw = _load(evidence_path, "assessment evidence")
    sufficiency, sufficiency_raw = _load(sufficiency_path, "assessment sufficiency")
    if sufficiency.get("evidence_source") != _ref(evidence_path, evidence_raw, evidence):
        raise AssessmentVerdictError("assessment sufficiency is bound to different evidence")
    charter_ref = sufficiency.get("charter_source")
    if not isinstance(charter_ref, dict):
        raise AssessmentVerdictError("assessment sufficiency charter reference is invalid")
    charter_path = Path(str(charter_ref.get("path")))
    charter, charter_raw = _load(charter_path, "assessment charter")
    if charter_ref != _ref(charter_path, charter_raw, charter):
        raise AssessmentVerdictError("assessment charter binding changed")
    evidence_units = evidence.get("units")
    sufficiency_units = sufficiency.get("units")
    if not isinstance(evidence_units, list) or not isinstance(sufficiency_units, list):
        raise AssessmentVerdictError("assessment unit sources are invalid")
    if [item.get("unit_id") for item in evidence_units] != [item.get("unit_id") for item in sufficiency_units]:
        raise AssessmentVerdictError("assessment evidence and sufficiency unit order changed")
    return charter, evidence, sufficiency, _ref(evidence_path, evidence_raw, evidence), _ref(sufficiency_path, sufficiency_raw, sufficiency)


def _gaps_for(sufficiency: dict[str, Any], unit_id: str) -> list[dict[str, object]]:
    return [dict(gap) for gap in sufficiency["gaps"] if gap["unit_id"] == unit_id]


def _complete(assessment: dict[str, Any]) -> bool:
    return all(item.get("verdict") == "sufficient" for item in assessment["assessments"])


def _incomplete_result(sufficiency: dict[str, Any], index: int) -> dict[str, object]:
    assessment = sufficiency["units"][index]
    gaps = _gaps_for(sufficiency, assessment["unit_id"])
    return {
        "unit_id": assessment["unit_id"],
        "verdict": "incomplete",
        "measure": None,
        "reason": "Evidence is incomplete for " + ", ".join(gap["obligation_id"] for gap in gaps) + ".",
        "evidence_ids": [evidence_id for item in assessment["assessments"] for evidence_id in item["evidence_ids"]],
        "gap_ids": [gap["gap_id"] for gap in gaps],
        "missing_evidence": [gap["missing_evidence"] for gap in gaps],
        "model_used": False,
    }


def _question(charter: dict[str, Any], evidence: dict[str, Any], sufficiency: dict[str, Any], index: int) -> dict[str, object]:
    unit = evidence["units"][index]
    assessment = sufficiency["units"][index]
    if not _complete(assessment):
        raise AssessmentVerdictError(f"unit {unit['unit_id']!r} lacks sufficient evidence")
    assessment_by_id = {item["obligation_id"]: item for item in assessment["assessments"]}
    roles = []
    for obligation in unit["obligations"]:
        sufficiency_item = assessment_by_id[obligation["id"]]
        selected = set(sufficiency_item["evidence_ids"])
        roles.append({
            "role": obligation["role"],
            "obligation_id": obligation["id"],
            "evidence": [
                {
                    "evidence_id": item["evidence_id"],
                    "representation": item["representation"],
                    "representation_sha256": item["representation_sha256"],
                }
                for item in obligation["evidence"]
                if item["evidence_id"] in selected
            ],
        })
    return {
        "schema_version": CONTRACT,
        "question_type": "assessment-grounded-unit-verdict",
        "purpose": charter["assessment"]["purpose"],
        "decision": charter["assessment"]["decision"],
        "unit": {key: unit[key] for key in ("sequence", "unit_id", "label", "subject")},
        "allowed_verdicts": list(MODEL_VERDICTS),
        "roles": roles,
    }


def _allowed_by_role(question: dict[str, Any]) -> dict[str, list[str]]:
    return {
        item["role"]: [evidence["evidence_id"] for evidence in item["evidence"]]
        for item in question["roles"]
    }


def _validate_response(question: dict[str, Any], response: object):
    if not isinstance(response, dict) or set(response) != RESPONSE_FIELDS:
        received = sorted(response) if isinstance(response, dict) else response
        return None, f"response fields received {received!r}; provide exactly {sorted(RESPONSE_FIELDS)!r}"
    errors: list[str] = []
    unit_id = question["unit"]["unit_id"]
    if response["unit_id"] != unit_id:
        errors.append(f"unit_id received {response['unit_id']!r}; provide {unit_id!r}")
    if response["verdict"] not in MODEL_VERDICTS:
        errors.append(f"verdict received {response['verdict']!r}; provide aligned or misaligned")
    for field in ("measure", "reason"):
        if not isinstance(response[field], str) or not response[field].strip():
            errors.append(f"{field} received {response[field]!r}; provide one non-empty grounded string")
    allowed_by_role = _allowed_by_role(question)
    allowed = {item for values in allowed_by_role.values() for item in values}
    evidence_ids = response["evidence_ids"]
    if not isinstance(evidence_ids, list):
        errors.append(f"evidence_ids received {evidence_ids!r}; provide one list using only {sorted(allowed)!r}")
    else:
        unknown = [item for item in evidence_ids if item not in allowed]
        if unknown:
            errors.append(f"evidence_ids contain unknown {unknown!r}; use only {sorted(allowed)!r}")
        if len(evidence_ids) != len(set(evidence_ids)):
            errors.append(f"evidence_ids received duplicates {evidence_ids!r}; choose unique ids")
        for role, role_ids in allowed_by_role.items():
            if not any(item in role_ids for item in evidence_ids):
                errors.append(f"evidence_ids omit {role}; include at least one of {role_ids!r}")
    if errors:
        return None, "; ".join(errors)
    return {
        "unit_id": unit_id,
        "verdict": response["verdict"],
        "measure": response["measure"].strip(),
        "reason": response["reason"].strip(),
        "evidence_ids": list(evidence_ids),
        "gap_ids": [],
        "missing_evidence": [],
        "model_used": True,
    }, None


def response_schema(question: dict[str, Any]) -> dict[str, object]:
    allowed = [item for values in _allowed_by_role(question).values() for item in values]
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "unit_id": {"type": "string", "enum": [question["unit"]["unit_id"]]},
            "verdict": {"type": "string", "enum": list(MODEL_VERDICTS)},
            "measure": {"type": "string"},
            "reason": {"type": "string"},
            "evidence_ids": {"type": "array", "items": {"type": "string", "enum": allowed}},
        },
        "required": ["unit_id", "verdict", "measure", "reason", "evidence_ids"],
        "additionalProperties": False,
    }


def _replay(entries, evidence_ref, sufficiency_ref, charter, evidence, sufficiency):
    if not entries or entries[0].get("event") != "assessment_verdicts_started" or entries[0].get("evidence") != evidence_ref or entries[0].get("sufficiency") != sufficiency_ref:
        raise AssessmentVerdictError("assessment verdict journal source binding changed")
    results = []
    pending = None
    completed = False
    for entry in entries[1:]:
        event = entry.get("event")
        if event == "incomplete_verdict_recorded":
            if pending is not None or len(results) >= len(evidence["units"]):
                raise AssessmentVerdictError(f"incomplete verdict is out of order at sequence {entry['sequence']}")
            expected = _incomplete_result(sufficiency, len(results))
            if entry.get("result") != expected:
                raise AssessmentVerdictError(f"incomplete verdict changed at sequence {entry['sequence']}")
            results.append(expected)
        elif event == "unit_question_asked":
            if pending is not None or len(results) >= len(evidence["units"]):
                raise AssessmentVerdictError(f"unit verdict question is out of order at sequence {entry['sequence']}")
            expected = _question(charter, evidence, sufficiency, len(results))
            if entry.get("question") != expected:
                raise AssessmentVerdictError(f"unit verdict question changed at sequence {entry['sequence']}")
            pending = expected
        elif event == "unit_answer_recorded":
            if pending is None:
                raise AssessmentVerdictError(f"unit verdict answer has no question at sequence {entry['sequence']}")
            parsed, error = _validate_response(pending, entry.get("parsed") if entry.get("accepted") else None)
            if entry.get("accepted") is not (error is None) or (error is None and parsed != entry.get("parsed")):
                raise AssessmentVerdictError(f"unit verdict answer changed at sequence {entry['sequence']}")
            if error is None:
                results.append(parsed)
                pending = None
        elif event == "assessment_verdicts_completed":
            if pending is not None or len(results) != len(evidence["units"]) or completed:
                raise AssessmentVerdictError(f"assessment verdict completion is invalid at sequence {entry['sequence']}")
            completed = True
        else:
            raise AssessmentVerdictError(f"unsupported assessment verdict event at sequence {entry['sequence']}")
    return results, pending, completed


def _artifact(evidence_ref, sufficiency_ref, results):
    counts = Counter(item["verdict"] for item in results)
    value: dict[str, object] = {
        "schema_version": CONTRACT,
        "artifact_type": "info-intake-assessment-verdicts",
        "status": "verdicts-ready",
        "evidence_source": evidence_ref,
        "sufficiency_source": sufficiency_ref,
        "unit_count": len(results),
        "verdict_counts": {verdict: counts[verdict] for verdict in ALL_VERDICTS},
        "actionable_misalignment_count": counts["misaligned"],
        "actionable_misalignment_unit_ids": [item["unit_id"] for item in results if item["verdict"] == "misaligned"],
        "units": results,
    }
    value["artifact_sha256"] = _digest(_canonical(value))
    return value


def _context(evidence_path: Path, sufficiency_path: Path, work_dir: Path):
    charter, evidence, sufficiency, evidence_ref, sufficiency_ref = _verify_sources(evidence_path, sufficiency_path)
    work_dir.mkdir(parents=True, exist_ok=True)
    journal_path = work_dir / "interview.jsonl"
    artifact_path = work_dir / "verdicts.json"
    if not journal_path.exists():
        journal._append(journal_path, "assessment_verdicts_started", {"evidence": evidence_ref, "sufficiency": sufficiency_ref})
    return charter, evidence, sufficiency, evidence_ref, sufficiency_ref, journal_path, artifact_path


def _publish(journal_path, artifact_path, evidence_ref, sufficiency_ref, results):
    artifact = _artifact(evidence_ref, sufficiency_ref, results)
    payload = json.dumps(artifact, indent=2, sort_keys=True).encode() + b"\n"
    if artifact_path.exists() and artifact_path.read_bytes() != payload:
        raise AssessmentVerdictError("assessment verdict artifact already exists with different bytes")
    if not artifact_path.exists():
        journal._append(journal_path, "assessment_verdicts_completed", {"artifact_path": "verdicts.json", "artifact_sha256": _digest(payload)})
        artifact_path.write_bytes(payload)
    return artifact


def prepare_question(evidence_path: Path, sufficiency_path: Path, work_dir: Path) -> dict[str, object]:
    charter, evidence, sufficiency, evidence_ref, sufficiency_ref, journal_path, artifact_path = _context(evidence_path, sufficiency_path, work_dir)
    while True:
        results, pending, completed = _replay(journal._read_journal(journal_path), evidence_ref, sufficiency_ref, charter, evidence, sufficiency)
        if completed:
            if not artifact_path.is_file():
                raise AssessmentVerdictError("completed assessment verdict artifact is missing")
            return {"schema_version": CONTRACT, "status": "complete", "recorded_unit_count": len(results), "artifact": str(artifact_path.resolve())}
        if len(results) == len(evidence["units"]):
            artifact = _publish(journal_path, artifact_path, evidence_ref, sufficiency_ref, results)
            return {"schema_version": CONTRACT, "status": "complete", "recorded_unit_count": len(results), "artifact": str(artifact_path.resolve()), "artifact_sha256": artifact["artifact_sha256"]}
        if pending is not None:
            return {"schema_version": CONTRACT, "status": "question-ready", "recorded_unit_count": len(results), "question": pending, "response_schema": response_schema(pending)}
        if not _complete(sufficiency["units"][len(results)]):
            journal._append(journal_path, "incomplete_verdict_recorded", {"result": _incomplete_result(sufficiency, len(results))})
            continue
        question = _question(charter, evidence, sufficiency, len(results))
        journal._append(journal_path, "unit_question_asked", {"question": question})


def submit_response(evidence_path: Path, sufficiency_path: Path, work_dir: Path, raw: str) -> dict[str, object]:
    charter, evidence, sufficiency, evidence_ref, sufficiency_ref, journal_path, artifact_path = _context(evidence_path, sufficiency_path, work_dir)
    results, pending, completed = _replay(journal._read_journal(journal_path), evidence_ref, sufficiency_ref, charter, evidence, sufficiency)
    if completed or pending is None:
        raise AssessmentVerdictError("assessment verdict has no pending model question")
    try:
        response = json.loads(raw)
    except json.JSONDecodeError:
        response = None
    parsed, error = _validate_response(pending, response)
    journal._append(journal_path, "unit_answer_recorded", {"raw": raw, "accepted": error is None, "parsed": parsed, "error": error})
    if error is not None:
        return {"schema_version": CONTRACT, "status": "rejected", "recorded_unit_count": len(results), "error": error}
    results.append(parsed)
    if len(results) == len(evidence["units"]):
        artifact = _publish(journal_path, artifact_path, evidence_ref, sufficiency_ref, results)
        return {"schema_version": CONTRACT, "status": "complete", "recorded_unit_count": len(results), "artifact": str(artifact_path.resolve()), "artifact_sha256": artifact["artifact_sha256"]}
    return {"schema_version": CONTRACT, "status": "accepted", "recorded_unit_count": len(results)}


def verify(path: Path) -> dict[str, object]:
    value, _raw = _load(path, "assessment verdicts")
    if value.get("artifact_type") != "info-intake-assessment-verdicts" or value.get("status") != "verdicts-ready":
        raise AssessmentVerdictError("assessment verdict type or status is invalid")
    evidence_path = Path(str(value.get("evidence_source", {}).get("path")))
    sufficiency_path = Path(str(value.get("sufficiency_source", {}).get("path")))
    _charter, _evidence, _sufficiency, evidence_ref, sufficiency_ref = _verify_sources(evidence_path, sufficiency_path)
    if value["evidence_source"] != evidence_ref or value["sufficiency_source"] != sufficiency_ref:
        raise AssessmentVerdictError("assessment verdict source binding changed")
    claimed = value.get("artifact_sha256")
    body = {key: item for key, item in value.items() if key != "artifact_sha256"}
    if claimed != _digest(_canonical(body)):
        raise AssessmentVerdictError("assessment verdict artifact digest changed")
    if _artifact(evidence_ref, sufficiency_ref, value.get("units")) != value:
        raise AssessmentVerdictError("assessment verdict counts or ordering changed")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args()
    try:
        result = verify(args.artifact)
    except AssessmentVerdictError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
