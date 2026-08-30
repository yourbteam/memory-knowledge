#!/usr/bin/env python3
"""Run or resume the complete runtime System Alignment assessment path."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


class AssessmentRunError(RuntimeError):
    pass


def _load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise AssessmentRunError(f"required assessment component is unavailable: {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


evidence_package = _load_module("evidence_package", "evidence_package.py")
intake_adapter = _load_module("system_alignment_intake_adapter", "intake_handoff_adapter.py")
validation_experiment = _load_module("system_alignment_validation_experiment", "validation_experiment.py")
runtime_questions = _load_module("system_alignment_runtime_questions", "runtime_questions.py")
runtime_interview = _load_module("system_alignment_runtime_interview", "runtime_interview.py")
runtime_terminal = _load_module("system_alignment_runtime_terminal", "runtime_terminal.py")


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def document(value: object) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True).encode() + b"\n"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(path: Path) -> dict[str, str]:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def load(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AssessmentRunError(f"{label} is unavailable or invalid JSON: {error}") from None
    if type(value) is not dict:
        raise AssessmentRunError(f"{label} must contain one JSON object")
    return value


def replay(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    previous = None
    events = []
    for sequence, line in enumerate(path.read_text().splitlines(), start=1):
        event = json.loads(line)
        recorded = event.get("entry_sha256")
        body = {key: item for key, item in event.items() if key != "entry_sha256"}
        if (
            event.get("sequence") != sequence
            or event.get("previous_entry_sha256") != previous
            or recorded != hashlib.sha256(canonical(body)).hexdigest()
        ):
            raise AssessmentRunError(f"assessment ledger changed at entry {sequence}")
        previous = recorded
        events.append(event)
    return events


def append(work: Path, payload: dict) -> None:
    ledger = work / "ledger.jsonl"
    events = replay(ledger)
    body = {
        "sequence": len(events) + 1,
        "previous_entry_sha256": events[-1]["entry_sha256"] if events else None,
        **payload,
    }
    event = {**body, "entry_sha256": hashlib.sha256(canonical(body)).hexdigest()}
    with ledger.open("ab") as stream:
        stream.write(json.dumps(event, sort_keys=True).encode() + b"\n")


def _write_once(path: Path, value: dict) -> None:
    if path.exists():
        raise AssessmentRunError(f"artifact already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(document(value))


def _terminal(work: Path, catalog_path: Path, results_path: Path | None) -> dict:
    spec = {
        "schema_version": 1,
        "catalog": ref(catalog_path),
        "runtime_results": None if results_path is None else ref(results_path),
    }
    value = runtime_terminal.create(spec)
    output = work / "runtime-assessment.json"
    runtime_terminal.write_once(value, output)
    result = {
        "status": value["status"],
        "overall_verdict": value["summary"]["overall_verdict"],
        "assessment": ref(output),
        "summary": value["summary"],
    }
    append(work, {"event": "assessment_completed", "result": result})
    return result


def start(
    *, work: Path, experiment_runner: Path, package_path: Path | None = None,
    handoff_path: Path | None = None, bindings_path: Path | None = None,
) -> dict:
    if work.exists():
        raise AssessmentRunError(f"work already exists: {work}")
    if (package_path is None) == (handoff_path is None):
        raise AssessmentRunError("provide exactly one standalone package or Info Intake handoff")
    if (handoff_path is None) != (bindings_path is None):
        raise AssessmentRunError("Info Intake handoff and alignment bindings are required together")
    if not experiment_runner.is_absolute() or not experiment_runner.is_file():
        raise AssessmentRunError("experiment runner must be an absolute regular file")
    work.mkdir(parents=True)
    append(work, {"event": "assessment_started", "source_mode": "standalone" if package_path else "info-intake"})
    if handoff_path is not None and bindings_path is not None:
        admission = intake_adapter.adapt(handoff_path, bindings_path)
        admission_path = work / "admission.json"
        intake_adapter._write_once(admission, admission_path)
        if admission["status"] == "validation-bindings-required":
            result = {
                "status": "needs-validation-bindings",
                "requests": admission["requests"],
                "admission": ref(admission_path),
            }
            append(work, {"event": "validation_bindings_required", "result": result})
            return result
        package_path = admission_path
    assert package_path is not None
    package = evidence_package.verify(package_path)
    executions = []
    for subject in package["subjects"]:
        for case in subject["validation_cases"]:
            output = work / "executions" / f"{subject['sequence']:06d}-{case['sequence']:06d}"
            validation_experiment.run(
                package_path, subject["subject_id"], case["case_id"], experiment_runner, output,
            )
            executions.append(ref(output / "validation-execution.json"))
    append(work, {"event": "validation_experiments_completed", "execution_count": len(executions)})
    question_spec = {
        "schema_version": 1,
        "evidence_package": ref(package_path),
        "executions": executions,
    }
    catalog = runtime_questions.create(question_spec)
    catalog_path = work / "runtime-question-catalog.json"
    runtime_questions.write_once(catalog, catalog_path)
    session = {
        "schema_version": 1,
        "package": ref(package_path),
        "experiment_runner": ref(experiment_runner),
        "catalog": ref(catalog_path),
        "execution_count": len(executions),
    }
    session["artifact_sha256"] = hashlib.sha256(canonical(session)).hexdigest()
    _write_once(work / "session.json", session)
    append(work, {
        "event": "runtime_questions_prepared",
        "question_count": catalog["question_count"],
        "disposition_count": catalog["disposition_count"],
    })
    if catalog["question_count"] == 0:
        return _terminal(work, catalog_path, None)
    current = runtime_interview.prepare(catalog_path, work / "interview")
    result = {"status": "needs-model-answer", **current}
    append(work, {"event": "model_question_presented", "question_id": current["question"]["question_id"]})
    return result


def _session(work: Path) -> dict:
    session = load(work / "session.json", "assessment session")
    recorded = session.get("artifact_sha256")
    if recorded != hashlib.sha256(canonical({key: item for key, item in session.items() if key != "artifact_sha256"})).hexdigest():
        raise AssessmentRunError("assessment session digest changed")
    for label in ("package", "experiment_runner", "catalog"):
        item = session[label]
        path = Path(item["path"])
        if sha(path) != item["sha256"]:
            raise AssessmentRunError(f"assessment session {label} bytes changed")
    evidence_package.verify(Path(session["package"]["path"]))
    replay(work / "ledger.jsonl")
    return session


def resume(work: Path, response_path: Path) -> dict:
    session = _session(work)
    if (work / "runtime-assessment.json").exists():
        raise AssessmentRunError("assessment already completed")
    before = runtime_interview.current(work / "interview")
    if before["status"] != "needs-model-answer":
        raise AssessmentRunError("assessment has no current model question")
    after = runtime_interview.answer(work / "interview", response_path)
    append(work, {"event": "model_answer_accepted", "question_id": before["question"]["question_id"], "response": ref(response_path)})
    if after["status"] == "completed":
        return _terminal(
            work,
            Path(session["catalog"]["path"]),
            work / "interview" / "runtime-results.json",
        )
    result = {"status": "needs-model-answer", **after}
    append(work, {"event": "model_question_presented", "question_id": after["question"]["question_id"]})
    return result


def status(work: Path) -> dict:
    events = replay(work / "ledger.jsonl")
    if not events:
        raise AssessmentRunError("assessment work has no events")
    latest = events[-1]
    if latest["event"] in {"assessment_completed", "validation_bindings_required"}:
        return latest["result"]
    _session(work)
    current = runtime_interview.current(work / "interview")
    return {"status": "needs-model-answer", **current}


def development_probe(case_path: Path, result_path: Path, telemetry_path: Path) -> int:
    case = load(case_path, "development case")
    work = result_path.parent / "assessment-work"
    if case["mode"] == "standalone":
        first = start(
            work=work,
            experiment_runner=Path(case["experiment_runner"]),
            package_path=Path(case["package"]),
        )
        reached_question = first.get("status") == "needs-model-answer"
        terminal = None
        if reached_question:
            question = first["question"]
            response = result_path.parent / "response.json"
            response.write_text(json.dumps({
                "schema_version": 1,
                "question_id": question["question_id"],
                "verdict": "aligned",
                "measure": {"kind": "exact-match", "expected": "42", "actual": "42"},
                "reason": "The executed actual and reference prototype outcomes match.",
                "evidence_ids": [question["evidence"][0]["evidence_id"]],
            }) + "\n")
            terminal = resume(work, response)
        correct = bool(
            reached_question
            and terminal
            and terminal.get("status") == "assessment-complete"
            and terminal.get("overall_verdict") == "aligned"
        )
        outcome = {
            "experiment_boundary_correct": (work / "executions" / "000001-000001" / "validation-execution.json").is_file(),
            "one_question_presented": reached_question,
            "terminal_correct": correct,
        }
    else:
        first = start(
            work=work,
            experiment_runner=Path(case["experiment_runner"]),
            handoff_path=Path(case["handoff"]),
            bindings_path=Path(case["bindings"]),
        )
        outcome = {
            "experiment_boundary_correct": not (work / "executions").exists(),
            "one_question_presented": first.get("status") == "needs-validation-bindings",
            "terminal_correct": bool(first.get("requests")),
        }
    result_path.write_text(json.dumps({
        "schema_version": 1,
        "variant_id": os.environ["EXPERIMENT_VARIANT_ID"],
        "status": "completed",
        "outcome": outcome,
        "metrics": {
            "real-experiment-path": int(outcome["experiment_boundary_correct"]),
            "code-controlled-boundary": int(outcome["one_question_presented"]),
            "terminal-outcome": int(outcome["terminal_correct"]),
        },
        "error": None,
    }))
    telemetry_path.write_text(json.dumps({
        "event": "complete-assessment-path-probed",
        "mode": case["mode"],
        "outcome": outcome,
    }) + "\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    if len(sys.argv) == 4 and sys.argv[1] not in {"start", "resume", "status"}:
        return development_probe(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    begin = sub.add_parser("start")
    begin.add_argument("--work", required=True, type=Path)
    begin.add_argument("--experiment-runner", required=True, type=Path)
    source = begin.add_mutually_exclusive_group(required=True)
    source.add_argument("--package", type=Path)
    source.add_argument("--handoff", type=Path)
    begin.add_argument("--bindings", type=Path)
    advance = sub.add_parser("resume")
    advance.add_argument("--work", required=True, type=Path)
    advance.add_argument("--response", required=True, type=Path)
    inspect = sub.add_parser("status")
    inspect.add_argument("--work", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "start":
            value = start(
                work=args.work, experiment_runner=args.experiment_runner,
                package_path=args.package, handoff_path=args.handoff,
                bindings_path=args.bindings,
            )
        elif args.command == "resume":
            value = resume(args.work, args.response)
        else:
            value = status(args.work)
    except (
        AssessmentRunError,
        evidence_package.EvidencePackageError,
        intake_adapter.IntakeHandoffAdapterError,
        validation_experiment.ValidationExperimentError,
        runtime_questions.RuntimeQuestionsError,
        runtime_interview.RuntimeInterviewError,
        runtime_terminal.RuntimeTerminalError,
        OSError,
        KeyError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        print(f"Assessment run refused: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
