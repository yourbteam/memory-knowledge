#!/usr/bin/env python3
"""Validate one assembled atomic step across every declared operator-path case."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path, PurePath
from typing import Any

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

from development_probe_compose import verify_assembly

CONTRACT = 1
MAX_WORKERS = 4
ALLOWED_VERDICTS = ["satisfied", "not-satisfied", "cannot-assess"]
ASSESSMENT_FIELDS = {"case_id", "verdict", "reason", "evidence_pointers"}
BOUND_ASSESSMENT_FIELDS = {
    "case_id",
    "atomic_step_id",
    "assembly_sha256",
    "status",
    "reason",
    "evidence_pointers",
}
PLACEHOLDERS = {
    "{python}",
    "{assessment-adapter}",
    "{assessment-request}",
    "{assessment-response}",
}
REQUIRED_PLACEHOLDERS = {
    "{assessment-adapter}",
    "{assessment-request}",
    "{assessment-response}",
}
SHELL_MARKERS = (";", "&", "|", "<", ">", "$", "`", "\n", "\r")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class FinalValidationError(RuntimeError):
    """The complete atomic-step verdict cannot be grounded."""

    def __init__(self, stage: str, message: str):
        super().__init__(message)
        self.stage = stage


def _document(value: object) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _exact(value: object, label: str, fields: set[str], stage: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise FinalValidationError(
            stage,
            f"{label} must be one object; received {type(value).__name__}",
        )
    missing = sorted(fields - value.keys())
    extra = sorted(value.keys() - fields)
    if missing or extra:
        raise FinalValidationError(
            stage,
            f"{label} has missing fields {missing} and unexpected fields {extra}; use exactly {sorted(fields)}",
        )
    return value


def _load(path: Path, label: str, stage: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FinalValidationError(stage, f"{label} is unavailable or invalid JSON: {error}") from None
    if type(value) is not dict:
        raise FinalValidationError(stage, f"{label} must contain one object; received {type(value).__name__}")
    return value


def _write_json(path: Path, value: object) -> str:
    payload = _document(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return _digest(payload)


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(value)


def _resolve(value: object, base: Path, label: str, stage: str) -> Path:
    if type(value) is not str or not value:
        raise FinalValidationError(stage, f"{label} must be a nonempty path")
    path = Path(value)
    return (path if path.is_absolute() else base / path).absolute()


def _prepare_output(output: Path) -> None:
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise FinalValidationError("prepare-output", f"output must be a new or empty directory: {output}")
    output.mkdir(parents=True, exist_ok=True)


def _assessment_contract(value: object, request_base: Path) -> tuple[Path, list[str], str]:
    assessment = _exact(
        value,
        "assessment",
        {"adapter", "command"},
        "validate-request",
    )
    adapter = _resolve(assessment["adapter"], request_base, "assessment.adapter", "validate-request")
    if adapter.is_symlink() or not adapter.is_file():
        raise FinalValidationError(
            "validate-request",
            f"assessment.adapter must be one stable regular file; received {adapter}",
        )
    command = assessment["command"]
    if type(command) is not list or not command:
        raise FinalValidationError("validate-request", "assessment.command must be a nonempty argument list")
    for index, argument in enumerate(command):
        if type(argument) is not str or not argument:
            raise FinalValidationError(
                "validate-request",
                f"assessment.command[{index}] is {argument!r}; use a nonempty string",
            )
        if argument in PLACEHOLDERS:
            continue
        if "{" in argument or "}" in argument:
            raise FinalValidationError(
                "validate-request",
                f"assessment.command[{index}] is {argument!r}; allowed placeholders are "
                f"{sorted(PLACEHOLDERS)} as exact whole arguments",
            )
        if PurePath(argument).is_absolute():
            raise FinalValidationError(
                "validate-request",
                f"assessment.command[{index}] is absolute path {argument!r}; use a placeholder",
            )
        marker = next((item for item in SHELL_MARKERS if item in argument), None)
        if marker is not None:
            raise FinalValidationError(
                "validate-request",
                f"assessment.command[{index}] contains shell marker {marker!r}; use separate literal arguments",
            )
    for placeholder in sorted(REQUIRED_PLACEHOLDERS):
        count = command.count(placeholder)
        if count != 1:
            raise FinalValidationError(
                "validate-request",
                f"assessment.command contains {count} copies of {placeholder!r}; use exactly one",
            )
    if command.count("{python}") > 1:
        raise FinalValidationError("validate-request", "assessment.command may contain at most one '{python}'")
    return adapter, command, _digest(adapter.read_bytes())


def _run_case(assembly: Path, case_id: str, execution_root: Path) -> dict[str, Any]:
    composer = Path(__file__).with_name("development_probe_compose.py")
    completed = subprocess.run(
        [
            sys.executable,
            str(composer),
            "execute",
            str(assembly),
            case_id,
            str(execution_root),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    result = None
    status = "completed" if completed.returncode == 0 else "refused"
    error = None
    if completed.returncode == 0:
        try:
            result = json.loads(completed.stdout)
        except (json.JSONDecodeError, TypeError) as parse_error:
            status = "incomplete"
            error = f"case {case_id!r} returned invalid result JSON: {parse_error}"
    else:
        error = completed.stderr.strip() or (
            f"case {case_id!r} execution exited {completed.returncode} without diagnostics"
        )
    evidence = []
    for evidence_id, filename in (
        ("candidate-stdout", "stdout.txt"),
        ("candidate-stderr", "stderr.txt"),
        ("candidate-telemetry", "telemetry.jsonl"),
    ):
        path = execution_root / filename
        if path.is_file():
            evidence.append(
                {"id": evidence_id, "path": str(path.resolve()), "sha256": _digest(path.read_bytes())}
            )
    return {
        "case_id": case_id,
        "status": status,
        "returncode": completed.returncode,
        "result": result,
        "error": error,
        "output": str(execution_root),
        "evidence": evidence,
    }


def _run_all_cases(output: Path, assembly: Path, case_ids: list[str]) -> list[dict[str, Any]]:
    indexed: dict[int, dict[str, Any]] = {}
    completion_order = []
    workers = min(MAX_WORKERS, len(case_ids))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _run_case,
                assembly,
                case_id,
                output / "executions" / case_id,
            ): (index, case_id)
            for index, case_id in enumerate(case_ids)
        }
        for future in as_completed(futures):
            index, case_id = futures[future]
            completion_order.append(case_id)
            try:
                indexed[index] = future.result()
            except Exception as error:
                indexed[index] = {
                    "case_id": case_id,
                    "status": "incomplete",
                    "returncode": 2,
                    "result": None,
                    "error": f"case {case_id!r} execution failed: {error}",
                    "output": str(output / "executions" / case_id),
                }
    outcomes = [indexed[index] for index in range(len(case_ids))]
    if [item["case_id"] for item in outcomes] != case_ids:
        raise FinalValidationError(
            "execute-cases",
            f"execution outcomes are {[item['case_id'] for item in outcomes]!r}; "
            f"require exactly declared order {case_ids!r}",
        )
    recorded = []
    for item in outcomes:
        copied = dict(item)
        copied["output"] = str(Path(item["output"]).relative_to(output))
        recorded.append(copied)
    _write_json(
        output / "case-results.json",
        {
            "schema_version": CONTRACT,
            "results": recorded,
            "completion_order": completion_order,
        },
    )
    return outcomes


def _question(
    manifest: dict[str, Any],
    assembly_sha256: str,
    case: dict[str, Any],
    execution: dict[str, Any],
) -> dict[str, Any]:
    final = manifest["composition"]["final_validation"]
    criterion = final["success_criterion"] if case["kind"] == "success" else final["failure_criterion"]
    evidence = [
        {"id": "execution-status", "value": execution["status"]},
        {"id": "execution-returncode", "value": execution["returncode"]},
    ]
    evidence.extend(execution.get("evidence", []))
    if execution["error"] is not None:
        evidence.append({"id": "execution-error", "value": execution["error"]})
    allowed_verdicts = ["not-satisfied", "cannot-assess"] if execution["status"] == "incomplete" else ALLOWED_VERDICTS
    return {
        "schema_version": CONTRACT,
        "atomic_step_id": manifest["atomic_step"]["id"],
        "assembly_sha256": assembly_sha256,
        "atomic_outcome": manifest["atomic_step"]["outcome"],
        "operator_path": final["operator_path"],
        "case_id": case["id"],
        "case_kind": case["kind"],
        "expected_outcome": case["expected_outcome"],
        "overall_criterion": criterion,
        "execution_evidence": evidence,
        "allowed_verdicts": allowed_verdicts,
    }


def _validate_response(raw: object, question: dict[str, Any]) -> dict[str, Any]:
    response = _exact(
        raw,
        f"assessment response for case {question['case_id']!r}",
        ASSESSMENT_FIELDS,
        "assess-cases",
    )
    problems = []
    if response["case_id"] != question["case_id"]:
        problems.append(
            f"case identity {response['case_id']!r} does not match presented "
            f"{question['case_id']!r}; use {question['case_id']!r}"
        )
    allowed_verdicts = question["allowed_verdicts"]
    if response["verdict"] not in allowed_verdicts:
        problems.append(
            f"verdict {response['verdict']!r} is not in allowed verdicts {allowed_verdicts!r}; choose one exact value"
        )
    reason = response["reason"]
    if type(reason) is not str or not reason.strip():
        problems.append(f"reason {reason!r} is empty; provide one nonempty reason for this verdict")
    pointers = response["evidence_pointers"]
    if (
        type(pointers) is not list
        or not pointers
        or any(type(pointer) is not str or not pointer for pointer in pointers)
    ):
        problems.append(
            f"evidence_pointers {pointers!r} is missing or empty; cite at least one presented execution evidence id"
        )
        pointers = []
    grounded = {item["id"] for item in question["execution_evidence"]}
    unknown = sorted(set(pointers) - grounded)
    if unknown:
        problems.append(
            f"evidence pointers {unknown!r} are not grounded for case "
            f"{question['case_id']!r}; use only {sorted(grounded)!r}"
        )
    for item in question["execution_evidence"]:
        if "path" not in item:
            continue
        path = Path(item["path"])
        if not path.is_file() or _digest(path.read_bytes()) != item.get("sha256"):
            problems.append(f"execution evidence {item['id']!r} is missing or changed")
    if response["verdict"] == "satisfied":
        execution_status = next(
            item["value"] for item in question["execution_evidence"] if item["id"] == "execution-status"
        )
        required_evidence = "candidate-telemetry" if execution_status == "completed" else "execution-error"
        if required_evidence not in pointers:
            problems.append(
                f"satisfied verdict cites {pointers!r}; cite {required_evidence!r} "
                f"for the presented {execution_status!r} execution"
            )
    if problems:
        raise FinalValidationError("assess-cases", "; ".join(problems))
    return {
        "case_id": response["case_id"],
        "verdict": response["verdict"],
        "reason": reason.strip(),
        "evidence_pointers": pointers,
    }


def _run_assessment(
    output: Path,
    case_id: str,
    question: dict[str, Any],
    adapter: Path,
    command: list[str],
) -> dict[str, Any]:
    assessment_root = output / "assessments" / case_id
    question_path = assessment_root / "question.json"
    _write_json(question_path, question)
    assessment_root.mkdir(parents=True, exist_ok=True)
    response_handle = tempfile.NamedTemporaryFile(
        prefix=f".{case_id}-response-", suffix=".json", dir=assessment_root, delete=False
    )
    response_handle.close()
    response_path = Path(response_handle.name)
    response_path.unlink()
    replacements = {
        "{python}": sys.executable,
        "{assessment-adapter}": str(adapter),
        "{assessment-request}": str(question_path),
        "{assessment-response}": str(response_path),
    }
    arguments = [replacements.get(argument, argument) for argument in command]
    try:
        completed = subprocess.run(
            arguments,
            cwd=assessment_root,
            text=True,
            capture_output=True,
            check=False,
        )
        _write_text(assessment_root / "stdout.txt", completed.stdout)
        _write_text(assessment_root / "stderr.txt", completed.stderr)
        if completed.returncode != 0:
            raise FinalValidationError(
                "assess-cases",
                f"case {case_id!r} assessment exited {completed.returncode}: "
                f"{completed.stderr.strip() or 'no diagnostic returned'}",
            )
        raw = _load(response_path, f"assessment response for case {case_id!r}", "assess-cases")
        accepted = _validate_response(raw, question)
        _write_json(assessment_root / "response.json", accepted)
        return {
            "case_id": case_id,
            "status": "accepted",
            "assessment": {
                "case_id": accepted["case_id"],
                "atomic_step_id": question["atomic_step_id"],
                "assembly_sha256": question["assembly_sha256"],
                "status": accepted["verdict"],
                "reason": accepted["reason"],
                "evidence_pointers": accepted["evidence_pointers"],
            },
        }
    finally:
        response_path.unlink(missing_ok=True)


def _assess_all_cases(
    output: Path,
    manifest: dict[str, Any],
    assembly_sha256: str,
    executions: list[dict[str, Any]],
    adapter: Path,
    command: list[str],
) -> list[dict[str, Any]]:
    cases_by_id = {case["id"]: case for case in manifest["atomic_step"]["captured_cases"]}
    case_ids = manifest["composition"]["final_validation"]["case_ids"]
    execution_by_id = {item["case_id"]: item for item in executions}
    indexed: dict[int, dict[str, Any]] = {}
    workers = min(MAX_WORKERS, len(case_ids))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {}
        for index, case_id in enumerate(case_ids):
            question = _question(
                manifest,
                assembly_sha256,
                cases_by_id[case_id],
                execution_by_id[case_id],
            )
            future = pool.submit(
                _run_assessment,
                output,
                case_id,
                question,
                adapter,
                command,
            )
            futures[future] = (index, case_id)
        for future in as_completed(futures):
            index, case_id = futures[future]
            try:
                indexed[index] = future.result()
            except Exception as error:
                indexed[index] = {
                    "case_id": case_id,
                    "status": "refused",
                    "error": str(error),
                }
    results = [indexed[index] for index in range(len(case_ids))]
    _write_json(
        output / "assessment-results.json",
        {"schema_version": CONTRACT, "results": results},
    )
    failures = [item for item in results if item["status"] != "accepted"]
    if failures:
        raise FinalValidationError(
            "assess-cases",
            "one or more case assessments were refused: "
            + "; ".join(f"{item['case_id']}: {item['error']}" for item in failures),
        )
    return [item["assessment"] for item in results]


def _terminal_verdict(
    manifest: dict[str, Any], assembly_sha256: str, assessments: list[dict[str, Any]]
) -> dict[str, Any]:
    atomic_step_id = manifest["atomic_step"]["id"]
    declared = manifest["composition"]["final_validation"]["case_ids"]
    indexed: dict[str, list[dict[str, Any]]] = {}
    issues = []
    if not SHA256.fullmatch(assembly_sha256):
        issues.append(f"verified assembly identity {assembly_sha256!r} is not one SHA-256 digest")
    for index, assessment in enumerate(assessments):
        if type(assessment) is not dict:
            issues.append(f"assessment {index} is {type(assessment).__name__}; use one bound object")
            continue
        if set(assessment) != BOUND_ASSESSMENT_FIELDS:
            issues.append(
                f"assessment {index} fields are {sorted(assessment)}; use exactly {sorted(BOUND_ASSESSMENT_FIELDS)}"
            )
        record = assessment
        case_id = record.get("case_id")
        if type(case_id) is not str:
            issues.append(f"assessment {index} case_id is {case_id!r}; use one declared case id")
            continue
        indexed.setdefault(case_id, []).append(record)
        if record.get("atomic_step_id") != atomic_step_id:
            issues.append(
                f"assessment {case_id!r} atomic_step_id is {record.get('atomic_step_id')!r}; use {atomic_step_id!r}"
            )
        if record.get("assembly_sha256") != assembly_sha256:
            issues.append(
                f"assessment {case_id!r} assembly_sha256 is "
                f"{record.get('assembly_sha256')!r}; use verified {assembly_sha256!r}"
            )
        if record.get("status") not in ALLOWED_VERDICTS:
            issues.append(f"assessment {case_id!r} status is {record['status']!r}; use one of {ALLOWED_VERDICTS!r}")
    missing = [case_id for case_id in declared if case_id not in indexed]
    duplicates = sorted(case_id for case_id, rows in indexed.items() if len(rows) != 1)
    unknown = sorted(case_id for case_id in indexed if case_id not in declared)
    if missing:
        issues.append(f"missing assessments {missing!r}; assess every declared case")
    if duplicates:
        issues.append(f"duplicate assessments {duplicates!r}; keep exactly one per case")
    if unknown:
        issues.append(f"unknown assessments {unknown!r}; remove undeclared cases")
    if issues:
        raise FinalValidationError("bind-verdict", "; ".join(issues))
    ordered = [indexed[case_id][0] for case_id in declared]
    statuses = [item["status"] for item in ordered]
    if "not-satisfied" in statuses:
        verdict = "failed"
    elif "cannot-assess" in statuses:
        verdict = "inconclusive"
    else:
        verdict = "passed"
    return {
        "schema_version": CONTRACT,
        "status": "completed",
        "atomic_step_id": atomic_step_id,
        "assembly_sha256": assembly_sha256,
        "verdict": verdict,
        "cases": [
            {
                "case_id": item["case_id"],
                "verdict": item["status"],
                "reason": item["reason"],
                "evidence_pointers": item["evidence_pointers"],
            }
            for item in ordered
        ],
        "promotion_applied": False,
    }


def run(request_path: Path, output: Path) -> dict[str, Any]:
    request_path = request_path.absolute()
    request = _exact(
        _load(request_path, "final-validation request", "validate-request"),
        "final-validation request",
        {"schema_version", "assembly", "assessment"},
        "validate-request",
    )
    if request["schema_version"] != CONTRACT or type(request["schema_version"]) is not int:
        raise FinalValidationError("validate-request", "final-validation request schema_version must be integer 1")
    output = output.absolute()
    _prepare_output(output)
    _write_json(output / "final-validation-request.json", request)
    assembly_path = _resolve(request["assembly"], request_path.parent, "assembly", "validate-request")
    adapter, command, adapter_sha256 = _assessment_contract(request["assessment"], request_path.parent)
    try:
        assembly, manifest, assembly_sha256 = verify_assembly(assembly_path)
    except Exception as error:
        raise FinalValidationError("validate-request", f"assembly verification failed: {error}") from None
    case_ids = manifest["composition"]["final_validation"]["case_ids"]
    executions = _run_all_cases(output, assembly_path, case_ids)
    try:
        _, _, after_execution_sha256 = verify_assembly(assembly_path)
    except Exception as error:
        raise FinalValidationError("execute-cases", f"assembly verification after execution failed: {error}") from None
    if after_execution_sha256 != assembly_sha256:
        raise FinalValidationError(
            "execute-cases",
            f"assembly digest changed from {assembly_sha256} to {after_execution_sha256}",
        )
    assessments = _assess_all_cases(
        output,
        manifest,
        assembly_sha256,
        executions,
        adapter,
        command,
    )
    current_adapter_sha256 = _digest(adapter.read_bytes())
    if current_adapter_sha256 != adapter_sha256:
        raise FinalValidationError(
            "assess-cases",
            f"assessment adapter changed from {adapter_sha256} to {current_adapter_sha256}",
        )
    try:
        _, _, final_assembly_sha256 = verify_assembly(assembly_path)
    except Exception as error:
        raise FinalValidationError("bind-verdict", f"assembly verification before verdict failed: {error}") from None
    if final_assembly_sha256 != assembly_sha256:
        raise FinalValidationError(
            "bind-verdict",
            f"assembly digest changed from {assembly_sha256} to {final_assembly_sha256}",
        )
    verdict = _terminal_verdict(manifest, assembly_sha256, assessments)
    _write_json(output / "final-verdict.json", verdict)
    _write_json(
        output / "final-validation-summary.json",
        {
            "schema_version": CONTRACT,
            "status": "completed",
            "atomic_step_id": assembly["identity"]["atomic_step_id"],
            "assembly_sha256": assembly_sha256,
            "assessment_adapter_sha256": adapter_sha256,
            "verdict": verdict["verdict"],
            "promotion_applied": False,
        },
    )
    return verdict


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="run complete final validation")
    run_parser.add_argument("request", type=Path)
    run_parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = args.output.absolute()
    try:
        result = run(args.request, output)
    except (FinalValidationError, OSError, subprocess.SubprocessError) as error:
        stage = error.stage if isinstance(error, FinalValidationError) else "runtime"
        run_started = output.is_dir() and (output / "final-validation-request.json").is_file()
        if run_started:
            try:
                summary = output / "final-validation-summary.json"
                if not summary.exists():
                    _write_json(
                        summary,
                        {
                            "schema_version": CONTRACT,
                            "status": "failed",
                            "stage": stage,
                            "error": str(error),
                            "promotion_applied": False,
                        },
                    )
            except OSError:
                pass
        print(
            f"Development-probe final validation refused at {stage}: {error}",
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
