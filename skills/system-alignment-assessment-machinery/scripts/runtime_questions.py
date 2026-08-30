#!/usr/bin/env python3
"""Prepare evidence-bound runtime comparison questions and deterministic gaps."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from evidence_package import verify as verify_package


class RuntimeQuestionsError(RuntimeError):
    pass


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest_without_artifact(value: dict) -> str:
    return hashlib.sha256(canonical({key: item for key, item in value.items() if key != "artifact_sha256"})).hexdigest()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_ref(ref: dict, label: str) -> tuple[Path, dict]:
    if type(ref) is not dict or set(ref) != {"path", "sha256"}:
        raise RuntimeQuestionsError(f"{label} must contain exactly path and sha256")
    path = Path(ref["path"])
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise RuntimeQuestionsError(f"{label}.path must be an absolute regular file")
    observed = sha(path)
    if observed != ref["sha256"]:
        raise RuntimeQuestionsError(f"{label} bytes changed: expected {ref['sha256']}, observed {observed}")
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeQuestionsError(f"{label} is invalid JSON: {error}") from None
    return path, value


def verify_ledger(path: Path) -> None:
    previous = None
    for sequence, line in enumerate(path.read_text().splitlines(), start=1):
        record = json.loads(line)
        claimed = record.pop("entry_sha256")
        if record.get("sequence") != sequence or record.get("previous_entry_sha256") != previous:
            raise RuntimeQuestionsError("experiment ledger order or previous hash is invalid")
        observed = hashlib.sha256(canonical(record)).hexdigest()
        if observed != claimed:
            raise RuntimeQuestionsError("experiment ledger entry digest is invalid")
        previous = claimed


def execution(ref: dict, package_path: Path, package: dict, label: str) -> dict:
    path, value = load_ref(ref, label)
    if value.get("artifact_type") != "system-alignment-validation-execution" or value.get("status") != "execution-complete":
        raise RuntimeQuestionsError(f"{label} is not a complete validation execution")
    if value.get("artifact_sha256") != digest_without_artifact(value):
        raise RuntimeQuestionsError(f"{label} artifact digest is invalid")
    if value.get("package") != {"path": str(package_path), "sha256": sha(package_path), "artifact_sha256": package["artifact_sha256"]}:
        raise RuntimeQuestionsError(f"{label} is bound to a different evidence package")
    artifacts = {}
    for name in ("spec", "summary", "ledger"):
        artifact_path = Path(value["experiment"][name]["path"])
        if sha(artifact_path) != value["experiment"][name]["sha256"]:
            raise RuntimeQuestionsError(f"{label} experiment {name} bytes changed")
        artifacts[name] = artifact_path
    verify_ledger(artifacts["ledger"])
    summary = json.loads(artifacts["summary"].read_text())
    variants = {item["variant_id"]: item for item in summary["variants"]}
    if set(variants) != {"control", "reference"}:
        raise RuntimeQuestionsError(f"{label} must contain exactly actual control and reference lanes")
    if summary["frozen_input_sha256"] != value["frozen_input_sha256"]:
        raise RuntimeQuestionsError(f"{label} summary used a different frozen input")
    return {"path": path, "value": value, "summary": summary, "variants": {"actual": variants["control"], "reference": variants["reference"]}}


def create(spec: dict) -> dict:
    if type(spec) is not dict or set(spec) != {"schema_version", "evidence_package", "executions"} or spec.get("schema_version") != 1:
        raise RuntimeQuestionsError("spec must contain exactly schema_version 1, evidence_package, and executions")
    package_path, _ = load_ref(spec["evidence_package"], "evidence_package")
    package = verify_package(package_path)
    refs = spec["executions"]
    if type(refs) is not list:
        raise RuntimeQuestionsError("executions must be an ordered list")
    bound = [execution(ref, package_path, package, f"executions[{index}]") for index, ref in enumerate(refs)]
    by_identity = {}
    for item in bound:
        identity = (item["value"]["subject_id"], item["value"]["case_id"])
        if identity in by_identity:
            raise RuntimeQuestionsError(f"duplicate validation execution {identity}")
        by_identity[identity] = item
    required = [(subject["subject_id"], case["case_id"]) for subject in package["subjects"] for case in subject["validation_cases"]]
    if set(by_identity) != set(required):
        missing = sorted(set(required) - set(by_identity))
        extra = sorted(set(by_identity) - set(required))
        raise RuntimeQuestionsError(f"executions must cover every case exactly once; missing {missing}, extra {extra}")
    questions = []
    dispositions = []
    sequence = 0
    subjects = {item["subject_id"]: item for item in package["subjects"]}
    for subject_id, case_id in required:
        item = by_identity[(subject_id, case_id)]
        lanes = item["variants"]
        incomplete = [role for role in ("actual", "reference") if lanes[role]["status"] != "completed" or not lanes[role]["eligible"]]
        if incomplete:
            dispositions.append({"subject_id": subject_id, "case_id": case_id, "verdict": "cannot-assess", "reason": "Real validation did not complete for every lane.", "missing_evidence": [{"lane": role, "request": f"Provide or repair a runnable {role} prototype for this frozen case, then rerun the experiment."} for role in incomplete], "execution_evidence": {"path": str(item["path"]), "sha256": sha(item["path"])}})
            continue
        sequence += 1
        questions.append({"question_id": f"runtime:{subject_id}:{case_id}", "sequence": sequence, "subject_id": subject_id, "case_id": case_id, "intent": subjects[subject_id]["intent"], "frozen_input_sha256": item["value"]["frozen_input_sha256"], "actual_outcome": lanes["actual"]["outcome"], "reference_outcome": lanes["reference"]["outcome"], "allowed_verdicts": ["aligned", "misaligned", "cannot-assess"], "allowed_measures": ["exact-match", "numeric-delta", "structural-equivalence", "semantic-equivalence"], "evidence": [{"evidence_id": f"execution:{subject_id}:{case_id}", "path": str(item["path"]), "sha256": sha(item["path"])}]})
    result = {"schema_version": 1, "artifact_type": "system-alignment-runtime-question-catalog", "status": "questions-ready", "evidence_package": {"path": str(package_path), "sha256": sha(package_path), "artifact_sha256": package["artifact_sha256"]}, "question_count": len(questions), "disposition_count": len(dispositions), "questions": questions, "dispositions": dispositions, "interview_mode": "one-question-at-a-time"}
    result["artifact_sha256"] = digest_without_artifact(result)
    return result


def write_once(value: dict, output: Path) -> None:
    if output.exists():
        raise RuntimeQuestionsError(f"output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def development_probe(case_path: Path, result_path: Path, telemetry_path: Path) -> int:
    case = json.loads(case_path.read_text())
    catalog = create(case["spec"])
    question = catalog["question_count"] == case["expected_questions"]
    disposition = catalog["disposition_count"] == case["expected_dispositions"]
    gap = not case["expect_gap"] or bool(catalog["dispositions"] and catalog["dispositions"][0]["missing_evidence"])
    outcome = {"question_count_correct": question, "disposition_count_correct": disposition, "gap_grounded": gap}
    result_path.write_text(json.dumps({"schema_version": 1, "variant_id": os.environ["EXPERIMENT_VARIANT_ID"], "status": "completed", "outcome": outcome, "metrics": {"correct-partition": int(question and disposition), "grounded-gap": int(gap)}, "error": None}))
    telemetry_path.write_text(json.dumps({"event": "runtime-questions-probed", "outcome": outcome}) + "\n")
    return 0


def main() -> int:
    if len(sys.argv) == 4 and sys.argv[1] not in {"create"}:
        return development_probe(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("create")
    command.add_argument("--spec", required=True, type=Path)
    command.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        value = create(json.loads(args.spec.read_text()))
        write_once(value, args.output)
    except (RuntimeQuestionsError, OSError, KeyError, ValueError, json.JSONDecodeError) as error:
        print(f"Runtime questions refused: {error}", file=sys.stderr)
        return 2
    print(json.dumps({"status": value["status"], "question_count": value["question_count"], "disposition_count": value["disposition_count"], "artifact_sha256": value["artifact_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
