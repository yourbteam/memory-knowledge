#!/usr/bin/env python3
"""Assess bound evidence sufficiency one exact unit at a time."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

CONTRACT = 1
VERDICTS = ("sufficient", "insufficient", "cannot-assess")
_SCRIPT_DIR = Path(__file__).resolve().parent


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"{name} is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


journal = _load_module(
    "assessment_sufficiency_journal", _SCRIPT_DIR / "projection_interview.py"
)
charter_contract = _load_module(
    "assessment_sufficiency_charter", _SCRIPT_DIR / "assessment_charter.py"
)
evidence_contract = _load_module(
    "assessment_sufficiency_evidence", _SCRIPT_DIR / "assessment_evidence.py"
)


class AssessmentSufficiencyError(RuntimeError):
    """Raised when the interview or source-bound assessment is invalid."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as error:
        raise AssessmentSufficiencyError(
            f"{label} is unavailable or invalid JSON: {error}"
        ) from error
    if not isinstance(value, dict):
        raise AssessmentSufficiencyError(f"{label} must contain one object")
    return value, raw


def _ref(path: Path, raw: bytes, value: dict[str, Any]) -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "sha256": _digest(raw),
        "artifact_sha256": value.get("artifact_sha256"),
    }


def _verify_sources(
    charter_path: Path, evidence_path: Path
) -> tuple[dict[str, Any], bytes, dict[str, Any], bytes]:
    try:
        charter_contract.verify(charter_path)
        evidence_contract.verify(evidence_path)
    except (charter_contract.AssessmentCharterError, evidence_contract.AssessmentEvidenceError) as error:
        raise AssessmentSufficiencyError(str(error)) from error
    charter, charter_raw = _load(charter_path, "assessment charter")
    evidence, evidence_raw = _load(evidence_path, "assessment evidence")
    if not isinstance(charter.get("assessment"), dict):
        raise AssessmentSufficiencyError("assessment charter purpose is unavailable")
    units = evidence.get("units")
    if not isinstance(units, list) or not units:
        raise AssessmentSufficiencyError(
            "assessment evidence must contain one non-empty units list"
        )
    for unit in units:
        for obligation in unit.get("obligations", []):
            for item in obligation.get("evidence", []):
                source = item.get("source")
                if not isinstance(source, dict):
                    raise AssessmentSufficiencyError(
                        "bound evidence source identity is invalid"
                    )
                source_path = Path(str(source.get("path")))
                try:
                    source_raw = source_path.read_bytes()
                except OSError as error:
                    raise AssessmentSufficiencyError(
                        f"bound evidence source is unavailable: {error}"
                    ) from error
                actual_sha = _digest(source_raw)
                if actual_sha != source.get("sha256"):
                    raise AssessmentSufficiencyError(
                        f"bound evidence source digest changed for {item.get('evidence_id')!r}"
                    )
                try:
                    representation = evidence_contract._resolve(
                        source_raw, item.get("locator")
                    )
                except evidence_contract.AssessmentEvidenceError as error:
                    raise AssessmentSufficiencyError(str(error)) from error
                if (
                    representation != item.get("representation")
                    or _digest(_canonical(representation))
                    != item.get("representation_sha256")
                ):
                    raise AssessmentSufficiencyError(
                        f"bound evidence representation changed for {item.get('evidence_id')!r}"
                    )
    return charter, charter_raw, evidence, evidence_raw


def _question(
    charter: dict[str, Any], evidence: dict[str, Any], index: int
) -> dict[str, object]:
    unit = evidence["units"][index]
    obligations = []
    for obligation in unit["obligations"]:
        bound = obligation.get("evidence")
        if not isinstance(bound, list):
            raise AssessmentSufficiencyError(
                f"unit {unit.get('unit_id')!r} obligation evidence is invalid"
            )
        obligations.append(
            {
                "obligation_id": obligation["id"],
                "role": obligation["role"],
                "question": obligation["question"],
                "bound_status": obligation["status"],
                "evidence": [
                    {
                        "evidence_id": item["evidence_id"],
                        "locator": item["locator"],
                        "representation": item["representation"],
                        "representation_sha256": item["representation_sha256"],
                    }
                    for item in bound
                ],
            }
        )
    return {
        "schema_version": CONTRACT,
        "question_type": "assessment-evidence-sufficiency",
        "purpose": charter["assessment"]["purpose"],
        "decision": charter["assessment"]["decision"],
        "unit": {
            "sequence": unit["sequence"],
            "unit_id": unit["unit_id"],
            "label": unit["label"],
            "subject": unit["subject"],
        },
        "allowed_verdicts": list(VERDICTS),
        "obligations": obligations,
    }


def _validate_response(
    question: dict[str, Any], response: object
) -> tuple[dict[str, object] | None, str | None]:
    if not isinstance(response, dict) or set(response) != {"unit_id", "assessments"}:
        return None, "response must contain exactly unit_id and assessments"
    unit_id = question["unit"]["unit_id"]
    errors: list[str] = []
    if response["unit_id"] != unit_id:
        errors.append(f"unit_id received {response['unit_id']!r}; use {unit_id!r}")
    rows = response["assessments"]
    if not isinstance(rows, list):
        return None, "; ".join(errors + ["assessments must be one list"])
    expected = question["obligations"]
    expected_ids = [item["obligation_id"] for item in expected]
    received_ids = [
        item.get("obligation_id") if isinstance(item, dict) else None
        for item in rows
    ]
    if received_ids != expected_ids:
        errors.append(
            f"obligations received {received_ids!r}; provide exactly {expected_ids!r} in order"
        )
    normalized: list[dict[str, object]] = []
    expected_by_id = {item["obligation_id"]: item for item in expected}
    for position, row in enumerate(rows, start=1):
        if not isinstance(row, dict) or set(row) != {
            "obligation_id",
            "verdict",
            "reason",
            "evidence_ids",
            "missing_evidence",
        }:
            errors.append(
                f"assessment {position} must contain exactly obligation_id, verdict, reason, evidence_ids, and missing_evidence"
            )
            continue
        obligation_id = row["obligation_id"]
        expected_obligation = expected_by_id.get(obligation_id)
        if expected_obligation is None:
            continue
        verdict = row["verdict"]
        reason = row["reason"]
        evidence_ids = row["evidence_ids"]
        missing = row["missing_evidence"]
        allowed_evidence = [
            item["evidence_id"] for item in expected_obligation["evidence"]
        ]
        if verdict not in VERDICTS:
            errors.append(
                f"{obligation_id} verdict received {verdict!r}; choose one of {list(VERDICTS)!r}"
            )
        if not isinstance(reason, str) or not reason.strip():
            errors.append(f"{obligation_id} reason must be one non-empty string")
        if (
            not isinstance(evidence_ids, list)
            or len(evidence_ids) != len(set(evidence_ids))
            or any(item not in allowed_evidence for item in evidence_ids)
        ):
            errors.append(
                f"{obligation_id} evidence_ids received {evidence_ids!r}; choose unique ids only from {allowed_evidence!r}"
            )
        if verdict == "sufficient":
            if not evidence_ids:
                errors.append(f"{obligation_id} sufficient requires selected evidence")
            if missing is not None:
                errors.append(
                    f"{obligation_id} sufficient requires null missing_evidence"
                )
        elif verdict in VERDICTS and (
            not isinstance(missing, str) or not missing.strip()
        ):
            errors.append(
                f"{obligation_id} {verdict} requires one concrete missing_evidence string"
            )
        normalized.append(
            {
                "obligation_id": obligation_id,
                "verdict": verdict,
                "reason": reason.strip() if isinstance(reason, str) else reason,
                "evidence_ids": list(evidence_ids) if isinstance(evidence_ids, list) else evidence_ids,
                "missing_evidence": missing.strip() if isinstance(missing, str) else missing,
            }
        )
    if errors:
        return None, "; ".join(errors)
    return {"unit_id": unit_id, "assessments": normalized}, None


def _prompt(question: dict[str, object]) -> str:
    schema = {
        "unit_id": question["unit"]["unit_id"],
        "assessments": [
            {
                "obligation_id": item["obligation_id"],
                "verdict": "sufficient|insufficient|cannot-assess",
                "reason": "non-empty evidence-grounded reason",
                "evidence_ids": ["only ids listed for this obligation"],
                "missing_evidence": "null when sufficient; concrete need otherwise",
            }
            for item in question["obligations"]
        ],
    }
    return (
        "Assess whether the bound evidence is sufficient for this exact unit and purpose.\n"
        + "Question:\n"
        + json.dumps(question, indent=2, sort_keys=True)
        + "\nRespond with one single-line JSON object matching this code-validated shape:\n"
        + json.dumps(schema, sort_keys=True)
        + "\nAnswer: "
    )


def response_schema(question: dict[str, Any]) -> dict[str, object]:
    """Return a provider-supported envelope for one code-bound response.

    The provider schema constrains the answer to declared identities and enums.
    ``_validate_response`` remains authoritative for exact count, order,
    obligation-to-evidence binding, uniqueness, and non-empty explanations.
    """
    obligation_ids = [
        obligation["obligation_id"] for obligation in question["obligations"]
    ]
    allowed_evidence = [
        item["evidence_id"]
        for obligation in question["obligations"]
        for item in obligation["evidence"]
    ]
    evidence_item_schema: dict[str, object] = {"type": "string"}
    if allowed_evidence:
        evidence_item_schema["enum"] = allowed_evidence
    assessment_item_schema = {
        "type": "object",
        "properties": {
            "obligation_id": {
                "type": "string",
                "enum": obligation_ids,
            },
            "verdict": {
                "type": "string",
                "enum": list(VERDICTS),
            },
            "reason": {"type": "string"},
            "evidence_ids": {
                "type": "array",
                "items": evidence_item_schema,
            },
            "missing_evidence": {
                "anyOf": [
                    {"type": "string"},
                    {"type": "null"},
                ]
            },
        },
        "required": [
            "obligation_id",
            "verdict",
            "reason",
            "evidence_ids",
            "missing_evidence",
        ],
        "additionalProperties": False,
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "unit_id": {
                "type": "string",
                "enum": [question["unit"]["unit_id"]],
            },
            "assessments": {
                "type": "array",
                "items": assessment_item_schema,
            },
        },
        "required": ["unit_id", "assessments"],
        "additionalProperties": False,
    }


def _terminal_input(prompt: str) -> str:
    print(prompt, end="", file=sys.stderr, flush=True)
    raw = sys.stdin.readline()
    if raw == "":
        raise AssessmentSufficiencyError("assessment sufficiency input ended")
    return raw.rstrip("\n")


def _replay(
    entries: list[dict[str, object]],
    charter_ref: dict[str, object],
    evidence_ref: dict[str, object],
    charter: dict[str, Any],
    evidence: dict[str, Any],
) -> tuple[list[dict[str, object]], dict[str, object] | None, bool]:
    if not entries:
        return [], None, False
    if entries[0].get("event") != "assessment_sufficiency_started" or entries[0].get("charter") != charter_ref or entries[0].get("evidence") != evidence_ref:
        raise AssessmentSufficiencyError(
            "assessment sufficiency source binding changed"
        )
    accepted: list[dict[str, object]] = []
    pending: dict[str, object] | None = None
    completed = False
    for entry in entries[1:]:
        event = entry.get("event")
        if event == "unit_question_asked":
            if completed or pending is not None or len(accepted) >= len(evidence["units"]):
                raise AssessmentSufficiencyError(
                    f"assessment sufficiency question is invalid at sequence {entry['sequence']}"
                )
            expected = _question(charter, evidence, len(accepted))
            if entry.get("question") != expected:
                raise AssessmentSufficiencyError(
                    f"assessment sufficiency question changed at sequence {entry['sequence']}"
                )
            pending = expected
        elif event == "unit_answer_recorded":
            if pending is None:
                raise AssessmentSufficiencyError(
                    f"assessment sufficiency answer is unbound at sequence {entry['sequence']}"
                )
            raw = entry.get("raw")
            try:
                response = json.loads(raw) if isinstance(raw, str) else None
            except json.JSONDecodeError:
                response = None
            parsed, error = _validate_response(pending, response)
            if entry.get("accepted") is not (error is None) or entry.get("parsed") != parsed or entry.get("error") != error:
                raise AssessmentSufficiencyError(
                    f"assessment sufficiency answer changed at sequence {entry['sequence']}"
                )
            if parsed is not None:
                accepted.append(parsed)
            pending = None
        elif event == "assessment_sufficiency_completed":
            if completed or pending is not None or len(accepted) != len(evidence["units"]):
                raise AssessmentSufficiencyError(
                    f"assessment sufficiency completion is invalid at sequence {entry['sequence']}"
                )
            completed = True
        else:
            raise AssessmentSufficiencyError(
                f"assessment sufficiency event is unsupported at sequence {entry['sequence']}"
            )
    return accepted, pending, completed


def _artifact(
    charter_ref: dict[str, object],
    evidence_ref: dict[str, object],
    responses: list[dict[str, object]],
) -> dict[str, object]:
    counts: Counter[str] = Counter()
    gaps: list[dict[str, object]] = []
    for response in responses:
        for assessment in response["assessments"]:
            counts[assessment["verdict"]] += 1
            if assessment["verdict"] != "sufficient":
                gaps.append(
                    {
                        "gap_id": f"gap-{len(gaps) + 1:06d}",
                        "unit_id": response["unit_id"],
                        "obligation_id": assessment["obligation_id"],
                        "verdict": assessment["verdict"],
                        "reason": assessment["reason"],
                        "evidence_ids": assessment["evidence_ids"],
                        "missing_evidence": assessment["missing_evidence"],
                    }
                )
    result: dict[str, object] = {
        "schema_version": CONTRACT,
        "artifact_type": "info-intake-assessment-sufficiency",
        "status": "sufficiency-ready",
        "charter_source": charter_ref,
        "evidence_source": evidence_ref,
        "unit_count": len(responses),
        "obligation_count": sum(len(response["assessments"]) for response in responses),
        "verdict_counts": {verdict: counts[verdict] for verdict in VERDICTS},
        "gap_count": len(gaps),
        "gaps": gaps,
        "units": responses,
    }
    result["artifact_sha256"] = _digest(_canonical(result))
    return result


def _interview_context(
    charter_path: Path, evidence_path: Path, work_dir: Path
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, object],
    dict[str, object],
    Path,
    Path,
]:
    charter, charter_raw, evidence, evidence_raw = _verify_sources(
        charter_path, evidence_path
    )
    charter_ref = _ref(charter_path, charter_raw, charter)
    evidence_ref = _ref(evidence_path, evidence_raw, evidence)
    work_dir.mkdir(parents=True, exist_ok=True)
    journal_path = work_dir / "interview.jsonl"
    artifact_path = work_dir / "sufficiency.json"
    if not journal_path.exists():
        journal._append(
            journal_path,
            "assessment_sufficiency_started",
            {"charter": charter_ref, "evidence": evidence_ref},
        )
    return (
        charter,
        evidence,
        charter_ref,
        evidence_ref,
        journal_path,
        artifact_path,
    )


def _publish_completed(
    journal_path: Path,
    artifact_path: Path,
    charter_ref: dict[str, object],
    evidence_ref: dict[str, object],
    responses: list[dict[str, object]],
) -> dict[str, object]:
    artifact = _artifact(charter_ref, evidence_ref, responses)
    payload = json.dumps(artifact, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    if artifact_path.exists():
        if artifact_path.read_bytes() != payload:
            raise AssessmentSufficiencyError(
                "assessment sufficiency artifact already exists with different bytes"
            )
    else:
        journal._append(
            journal_path,
            "assessment_sufficiency_completed",
            {
                "artifact_path": "sufficiency.json",
                "artifact_sha256": _digest(payload),
            },
        )
        artifact_path.write_bytes(payload)
    return artifact


def prepare_question(
    charter_path: Path, evidence_path: Path, work_dir: Path
) -> dict[str, object]:
    """Prepare or replay exactly one pending code-bound model question."""
    (
        charter,
        evidence,
        charter_ref,
        evidence_ref,
        journal_path,
        artifact_path,
    ) = _interview_context(charter_path, evidence_path, work_dir)
    entries = journal._read_journal(journal_path)
    responses, pending, completed = _replay(
        entries, charter_ref, evidence_ref, charter, evidence
    )
    if completed:
        if not artifact_path.is_file():
            raise AssessmentSufficiencyError(
                "completed assessment sufficiency artifact is missing"
            )
        return {
            "schema_version": CONTRACT,
            "status": "complete",
            "accepted_unit_count": len(responses),
            "artifact": str(artifact_path.resolve()),
        }
    if len(responses) == len(evidence["units"]):
        artifact = _publish_completed(
            journal_path, artifact_path, charter_ref, evidence_ref, responses
        )
        return {
            "schema_version": CONTRACT,
            "status": "complete",
            "accepted_unit_count": len(responses),
            "artifact": str(artifact_path.resolve()),
            "artifact_sha256": artifact["artifact_sha256"],
        }
    question = pending or _question(charter, evidence, len(responses))
    if pending is None:
        journal._append(
            journal_path, "unit_question_asked", {"question": question}
        )
    return {
        "schema_version": CONTRACT,
        "status": "question-ready",
        "accepted_unit_count": len(responses),
        "remaining_unit_count": len(evidence["units"]) - len(responses),
        "question": question,
        "response_schema": response_schema(question),
    }


def submit_response(
    charter_path: Path,
    evidence_path: Path,
    work_dir: Path,
    raw: str,
) -> dict[str, object]:
    """Validate and journal exactly one response to the pending question."""
    (
        charter,
        evidence,
        charter_ref,
        evidence_ref,
        journal_path,
        artifact_path,
    ) = _interview_context(charter_path, evidence_path, work_dir)
    entries = journal._read_journal(journal_path)
    responses, pending, completed = _replay(
        entries, charter_ref, evidence_ref, charter, evidence
    )
    if completed:
        raise AssessmentSufficiencyError(
            "assessment sufficiency is already complete"
        )
    if pending is None:
        raise AssessmentSufficiencyError(
            "assessment sufficiency has no prepared question"
        )
    try:
        response = json.loads(raw)
    except json.JSONDecodeError:
        response = None
    parsed, error = _validate_response(pending, response)
    journal._append(
        journal_path,
        "unit_answer_recorded",
        {
            "raw": raw,
            "accepted": error is None,
            "parsed": parsed,
            "error": error,
        },
    )
    if error is not None:
        return {
            "schema_version": CONTRACT,
            "status": "rejected",
            "accepted_unit_count": len(responses),
            "error": error,
        }
    assert parsed is not None
    responses.append(parsed)
    if len(responses) == len(evidence["units"]):
        artifact = _publish_completed(
            journal_path, artifact_path, charter_ref, evidence_ref, responses
        )
        return {
            "schema_version": CONTRACT,
            "status": "complete",
            "accepted_unit_count": len(responses),
            "artifact": str(artifact_path.resolve()),
            "artifact_sha256": artifact["artifact_sha256"],
        }
    return {
        "schema_version": CONTRACT,
        "status": "accepted",
        "accepted_unit_count": len(responses),
        "remaining_unit_count": len(evidence["units"]) - len(responses),
    }


def run(
    charter_path: Path,
    evidence_path: Path,
    work_dir: Path,
    *,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
    max_units: int | None = None,
) -> dict[str, object]:
    charter, charter_raw, evidence, evidence_raw = _verify_sources(
        charter_path, evidence_path
    )
    if max_units is not None and (
        not isinstance(max_units, int)
        or isinstance(max_units, bool)
        or max_units < 1
    ):
        raise AssessmentSufficiencyError("max_units must be one positive integer")
    charter_ref = _ref(charter_path, charter_raw, charter)
    evidence_ref = _ref(evidence_path, evidence_raw, evidence)
    work_dir.mkdir(parents=True, exist_ok=True)
    journal_path = work_dir / "interview.jsonl"
    artifact_path = work_dir / "sufficiency.json"
    read = input_fn or _terminal_input
    write = output_fn or (lambda message: print(message, file=sys.stderr))
    if not journal_path.exists():
        journal._append(
            journal_path,
            "assessment_sufficiency_started",
            {"charter": charter_ref, "evidence": evidence_ref},
        )
    accepted_this_run = 0
    while True:
        entries = journal._read_journal(journal_path)
        responses, pending, completed = _replay(
            entries, charter_ref, evidence_ref, charter, evidence
        )
        artifact = (
            _artifact(charter_ref, evidence_ref, responses)
            if len(responses) == len(evidence["units"])
            else None
        )
        payload = (
            json.dumps(artifact, indent=2, sort_keys=True).encode("utf-8") + b"\n"
            if artifact is not None
            else None
        )
        if completed:
            assert payload is not None and artifact is not None
            if not artifact_path.is_file() or artifact_path.read_bytes() != payload:
                raise AssessmentSufficiencyError(
                    "completed assessment sufficiency artifact changed or is missing"
                )
            return artifact
        if max_units is not None and accepted_this_run >= max_units:
            return {
                "schema_version": CONTRACT,
                "status": "paused",
                "accepted_unit_count": len(responses),
                "remaining_unit_count": len(evidence["units"]) - len(responses),
                "work_dir": str(work_dir.resolve()),
            }
        if artifact is not None:
            assert payload is not None
            if artifact_path.exists():
                raise AssessmentSufficiencyError(
                    "unbound assessment sufficiency artifact already exists"
                )
            journal._append(
                journal_path,
                "assessment_sufficiency_completed",
                {
                    "artifact_path": "sufficiency.json",
                    "artifact_sha256": _digest(payload),
                },
            )
            artifact_path.write_bytes(payload)
            continue
        question = pending or _question(charter, evidence, len(responses))
        if pending is None:
            journal._append(
                journal_path, "unit_question_asked", {"question": question}
            )
        raw = read(_prompt(question))
        try:
            response = json.loads(raw)
        except json.JSONDecodeError:
            response = None
        parsed, error = _validate_response(question, response)
        journal._append(
            journal_path,
            "unit_answer_recorded",
            {
                "raw": raw,
                "accepted": error is None,
                "parsed": parsed,
                "error": error,
            },
        )
        if error:
            write(f"Invalid answer: {error}.")
        else:
            accepted_this_run += 1


def verify(path: Path) -> dict[str, object]:
    value, _raw = _load(path, "assessment sufficiency")
    if (
        value.get("artifact_type") != "info-intake-assessment-sufficiency"
        or value.get("status") != "sufficiency-ready"
    ):
        raise AssessmentSufficiencyError(
            "assessment sufficiency type or status is invalid"
        )
    claimed = value.get("artifact_sha256")
    body = {key: item for key, item in value.items() if key != "artifact_sha256"}
    if claimed != _digest(_canonical(body)):
        raise AssessmentSufficiencyError(
            "assessment sufficiency artifact digest changed"
        )
    charter_ref = value.get("charter_source")
    evidence_ref = value.get("evidence_source")
    if not isinstance(charter_ref, dict) or not isinstance(evidence_ref, dict):
        raise AssessmentSufficiencyError(
            "assessment sufficiency source references are invalid"
        )
    charter_path = Path(str(charter_ref.get("path")))
    evidence_path = Path(str(evidence_ref.get("path")))
    charter, charter_raw, evidence, evidence_raw = _verify_sources(
        charter_path, evidence_path
    )
    if charter_ref != _ref(charter_path, charter_raw, charter) or evidence_ref != _ref(evidence_path, evidence_raw, evidence):
        raise AssessmentSufficiencyError(
            "assessment sufficiency source binding changed"
        )
    responses = value.get("units")
    if not isinstance(responses, list):
        raise AssessmentSufficiencyError("assessment sufficiency units are invalid")
    for index, response in enumerate(responses):
        parsed, error = _validate_response(_question(charter, evidence, index), response)
        if error is not None or parsed != response:
            raise AssessmentSufficiencyError(
                f"assessment sufficiency unit {index + 1} changed: {error}"
            )
    if _artifact(charter_ref, evidence_ref, responses) != value:
        raise AssessmentSufficiencyError(
            "assessment sufficiency counts, gaps, or ordering changed"
        )
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run")
    run_parser.add_argument("--charter", type=Path, required=True)
    run_parser.add_argument("--evidence", type=Path, required=True)
    run_parser.add_argument("--work", type=Path, required=True)
    run_parser.add_argument("--max-units", type=int)
    check = commands.add_parser("verify")
    check.add_argument("artifact", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "run":
            result = run(
                args.charter,
                args.evidence,
                args.work,
                max_units=args.max_units,
            )
        else:
            result = verify(args.artifact)
    except AssessmentSufficiencyError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
