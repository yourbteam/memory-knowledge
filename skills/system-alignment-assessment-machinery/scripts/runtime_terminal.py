#!/usr/bin/env python3
"""Build the complete runtime alignment result and downstream handoffs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path


class RuntimeTerminalError(RuntimeError):
    pass


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def artifact_digest(value: dict) -> str:
    return hashlib.sha256(canonical({key: item for key, item in value.items() if key != "artifact_sha256"})).hexdigest()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_ref(ref: object, label: str, *, optional: bool = False) -> tuple[Path | None, dict | None]:
    if optional and ref is None:
        return None, None
    if type(ref) is not dict or set(ref) != {"path", "sha256"}:
        raise RuntimeTerminalError(f"{label} must contain exactly path and sha256")
    path = Path(ref["path"])
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise RuntimeTerminalError(f"{label}.path must be an absolute regular file")
    observed = sha(path)
    if observed != ref["sha256"]:
        raise RuntimeTerminalError(f"{label} bytes changed: expected {ref['sha256']}, observed {observed}")
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeTerminalError(f"{label} is invalid JSON: {error}") from None
    return path, value


def create(spec: dict) -> dict:
    if type(spec) is not dict or set(spec) != {"schema_version", "catalog", "runtime_results"} or spec.get("schema_version") != 1:
        raise RuntimeTerminalError("spec must contain exactly schema_version 1, catalog, and runtime_results")
    catalog_path, catalog = load_ref(spec["catalog"], "catalog")
    assert catalog_path is not None and catalog is not None
    if catalog.get("artifact_type") != "system-alignment-runtime-question-catalog" or catalog.get("status") != "questions-ready" or catalog.get("artifact_sha256") != artifact_digest(catalog):
        raise RuntimeTerminalError("catalog identity or artifact digest changed")
    results_path, results = load_ref(spec["runtime_results"], "runtime_results", optional=True)
    if catalog["question_count"]:
        if results is None or results_path is None:
            raise RuntimeTerminalError("runtime_results are required while catalog questions remain")
        if results.get("artifact_type") != "system-alignment-runtime-results" or results.get("status") != "runtime-assessment-complete" or results.get("artifact_sha256") != artifact_digest(results):
            raise RuntimeTerminalError("runtime_results identity or artifact digest changed")
        if results.get("catalog_artifact_sha256") != catalog["artifact_sha256"]:
            raise RuntimeTerminalError("runtime_results answer a different catalog")
        answers = results["results"]
        if [item["question_id"] for item in answers] != [item["question_id"] for item in catalog["questions"]]:
            raise RuntimeTerminalError("runtime_results must answer every catalog question exactly once in order")
    else:
        if results is not None:
            raise RuntimeTerminalError("runtime_results must be null when the catalog has no questions")
        answers = []
    questions = {item["question_id"]: item for item in catalog["questions"]}
    cases = []
    for answer in answers:
        question = questions[answer["question_id"]]
        cases.append({"subject_id": question["subject_id"], "case_id": question["case_id"], "intent": question["intent"], "verdict": answer["verdict"], "measure": answer["measure"], "reason": answer["reason"], "evidence": question["evidence"]})
    for disposition in catalog["dispositions"]:
        cases.append({"subject_id": disposition["subject_id"], "case_id": disposition["case_id"], "intent": next((item["intent"] for item in catalog["questions"] if item["subject_id"] == disposition["subject_id"]), "Runtime validation must complete before comparison."), "verdict": "cannot-assess", "measure": {"kind": "none", "expected": "", "actual": ""}, "reason": disposition["reason"], "evidence": [disposition["execution_evidence"]], "missing_evidence": disposition["missing_evidence"]})
    package_path = Path(catalog["evidence_package"]["path"])
    package = json.loads(package_path.read_text())
    if sha(package_path) != catalog["evidence_package"]["sha256"] or package.get("artifact_sha256") != catalog["evidence_package"]["artifact_sha256"] or package.get("artifact_sha256") != artifact_digest(package):
        raise RuntimeTerminalError("evidence package bytes or artifact digest changed after question preparation")
    required = [(subject["subject_id"], case["case_id"]) for subject in package["subjects"] for case in subject["validation_cases"]]
    observed = [(item["subject_id"], item["case_id"]) for item in cases]
    if sorted(observed) != sorted(required) or len(observed) != len(set(observed)):
        raise RuntimeTerminalError(f"terminal cases must cover every admitted case exactly once; expected {required}, observed {observed}")
    by_subject = {subject["subject_id"]: [] for subject in package["subjects"]}
    for item in cases:
        by_subject[item["subject_id"]].append(item)
    assessments = []
    missing = []
    defects = []
    for subject in package["subjects"]:
        subject_cases = by_subject[subject["subject_id"]]
        verdicts = {item["verdict"] for item in subject_cases}
        verdict = "misaligned" if "misaligned" in verdicts else "cannot-assess" if "cannot-assess" in verdicts else "aligned"
        assessments.append({"subject_id": subject["subject_id"], "label": subject["label"], "intent": subject["intent"], "verdict": verdict, "measures": [item["measure"] for item in subject_cases], "cases": subject_cases})
        for item in subject_cases:
            if item["verdict"] == "cannot-assess":
                missing.append({"subject_id": item["subject_id"], "case_id": item["case_id"], "requests": item.get("missing_evidence", [{"lane": "comparison", "request": item["reason"]}])})
            elif item["verdict"] == "misaligned":
                evidence = item["evidence"]
                defects.append({"candidate_id": f"align-{item['subject_id']}-{item['case_id']}", "status": "requires-owner-envelope", "problem": item["reason"], "desired_outcome": f"Make actual behavior align with the declared intent: {item['intent']}", "practical_value": f"The observable subject {subject['label']} produces the reference-aligned result for this real case.", "stopping_condition": f"Rerunning case {item['case_id']} through System Alignment Assessment Machinery returns aligned.", "captured_case": evidence[0], "required_owner_fields": ["atomic_step_id", "allowed_paths", "approval"]})
    counts = {verdict: sum(item["verdict"] == verdict for item in assessments) for verdict in ("aligned", "misaligned", "cannot-assess")}
    overall = "misaligned" if counts["misaligned"] else "cannot-assess" if counts["cannot-assess"] else "aligned"
    result = {"schema_version": 1, "artifact_type": "system-alignment-runtime-assessment", "status": "assessment-complete" if overall != "cannot-assess" else "assessment-complete-with-gaps", "catalog": {"path": str(catalog_path), "sha256": sha(catalog_path), "artifact_sha256": catalog["artifact_sha256"]}, "runtime_results": None if results_path is None else {"path": str(results_path), "sha256": sha(results_path), "artifact_sha256": results["artifact_sha256"]}, "summary": {"subject_count": len(assessments), **counts, "overall_verdict": overall}, "assessments": assessments, "missing_evidence_requests": missing, "atom_building_candidates": defects}
    result["artifact_sha256"] = artifact_digest(result)
    return result


def write_once(value: dict, output: Path) -> None:
    if output.exists():
        raise RuntimeTerminalError(f"output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def development_probe(case_path: Path, result_path: Path, telemetry_path: Path) -> int:
    case = json.loads(case_path.read_text())
    terminal = create(case["spec"])
    outcome = {"verdict_correct": terminal["summary"]["overall_verdict"] == case["expected_verdict"], "defect_count_correct": len(terminal["atom_building_candidates"]) == case["expected_defects"], "gap_count_correct": len(terminal["missing_evidence_requests"]) == case["expected_gaps"]}
    result_path.write_text(json.dumps({"schema_version": 1, "variant_id": os.environ["EXPERIMENT_VARIANT_ID"], "status": "completed", "outcome": outcome, "metrics": {"complete-coverage": int(all(outcome.values())), "actionable-handoff": int(outcome["defect_count_correct"] and outcome["gap_count_correct"])}, "error": None}))
    telemetry_path.write_text(json.dumps({"event": "runtime-terminal-probed", "outcome": outcome}) + "\n")
    return 0


def main() -> int:
    if len(sys.argv) == 4 and sys.argv[1] not in {"create"}:
        return development_probe(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("create"); command.add_argument("--spec", required=True, type=Path); command.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        value = create(json.loads(args.spec.read_text())); write_once(value, args.output)
    except (RuntimeTerminalError, OSError, KeyError, ValueError, json.JSONDecodeError) as error:
        print(f"Runtime terminal refused: {error}", file=sys.stderr); return 2
    print(json.dumps({"status": value["status"], "overall_verdict": value["summary"]["overall_verdict"], "subject_count": value["summary"]["subject_count"], "artifact_sha256": value["artifact_sha256"]}, sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
