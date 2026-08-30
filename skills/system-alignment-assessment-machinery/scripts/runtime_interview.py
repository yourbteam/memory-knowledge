#!/usr/bin/env python3
"""Conduct a code-controlled one-question runtime alignment interview."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

VERDICTS = {"aligned", "misaligned", "cannot-assess"}


class RuntimeInterviewError(RuntimeError):
    pass


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def document(value: object) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True).encode() + b"\n"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_bytes())
    except Exception as error:
        raise RuntimeInterviewError(f"{label} unavailable or invalid: {error}") from None
    if type(value) is not dict:
        raise RuntimeInterviewError(f"{label} must be one object")
    return value


def replay(path: Path) -> list[dict]:
    previous = None
    events = []
    for sequence, line in enumerate(path.read_text().splitlines(), start=1):
        event = json.loads(line)
        claimed = event.get("entry_sha256")
        base = {key: value for key, value in event.items() if key != "entry_sha256"}
        if event.get("sequence") != sequence or event.get("previous_entry_sha256") != previous or claimed != hashlib.sha256(canonical(base)).hexdigest():
            raise RuntimeInterviewError(f"ledger changed at entry {sequence}")
        previous = claimed
        events.append(event)
    return events


def append(path: Path, payload: dict) -> None:
    events = replay(path) if path.exists() else []
    base = {"sequence": len(events) + 1, "previous_entry_sha256": events[-1]["entry_sha256"] if events else None, **payload}
    event = {**base, "entry_sha256": hashlib.sha256(canonical(base)).hexdigest()}
    with path.open("ab") as stream:
        stream.write(json.dumps(event, sort_keys=True).encode() + b"\n")


def verify_catalog(path: Path) -> dict:
    catalog = load(path, "catalog")
    if catalog.get("artifact_type") != "system-alignment-runtime-question-catalog" or catalog.get("status") != "questions-ready" or catalog.get("interview_mode") != "one-question-at-a-time":
        raise RuntimeInterviewError("catalog identity changed")
    observed = hashlib.sha256(canonical({key: value for key, value in catalog.items() if key != "artifact_sha256"})).hexdigest()
    if catalog.get("artifact_sha256") != observed:
        raise RuntimeInterviewError("catalog artifact digest changed")
    for question in catalog["questions"]:
        for evidence in question["evidence"]:
            evidence_path = Path(evidence["path"])
            if sha(evidence_path) != evidence["sha256"]:
                raise RuntimeInterviewError(f"question evidence changed for {question['question_id']}")
    return catalog


def context(work: Path) -> tuple[dict, list[dict], list[dict]]:
    session = load(work / "session.json", "session")
    catalog_path = Path(session["catalog"]["path"])
    if sha(catalog_path) != session["catalog"]["sha256"]:
        raise RuntimeInterviewError("catalog bytes changed")
    catalog = verify_catalog(catalog_path)
    events = replay(work / "ledger.jsonl")
    answers = [event for event in events if event["event"] == "answer_recorded"]
    return catalog, events, answers


def current(work: Path) -> dict:
    catalog, events, answers = context(work)
    done = any(event["event"] == "interview_completed" for event in events)
    return {"status": "completed" if done else "needs-model-answer", "answered_count": len(answers), "question_count": catalog["question_count"], "question": None if done else catalog["questions"][len(answers)]}


def prepare(catalog_path: Path, work: Path) -> dict:
    if work.exists():
        raise RuntimeInterviewError(f"work exists: {work}")
    catalog = verify_catalog(catalog_path)
    if catalog["question_count"] == 0:
        raise RuntimeInterviewError("catalog has no model questions; its cannot-assess dispositions are already terminal")
    work.mkdir(parents=True)
    (work / "answers").mkdir()
    session = {"schema_version": 1, "catalog": {"path": str(catalog_path.resolve()), "sha256": sha(catalog_path), "artifact_sha256": catalog["artifact_sha256"]}}
    session["artifact_sha256"] = hashlib.sha256(canonical(session)).hexdigest()
    (work / "session.json").write_bytes(document(session))
    append(work / "ledger.jsonl", {"event": "interview_started"})
    append(work / "ledger.jsonl", {"event": "question_asked", "question_id": catalog["questions"][0]["question_id"], "position": 1})
    return current(work)


def validate(question: dict, response: dict) -> dict:
    fields = {"schema_version", "question_id", "verdict", "measure", "reason", "evidence_ids"}
    if type(response) is not dict or set(response) != fields or response["schema_version"] != 1 or response["question_id"] != question["question_id"] or response["verdict"] not in VERDICTS or response["verdict"] not in question["allowed_verdicts"]:
        raise RuntimeInterviewError("response shape, identity, or verdict is outside the presented choices")
    measure = response["measure"]
    if type(measure) is not dict or set(measure) != {"kind", "expected", "actual"}:
        raise RuntimeInterviewError("measure must contain exactly kind, expected, and actual")
    if response["verdict"] == "cannot-assess":
        if measure != {"kind": "none", "expected": "", "actual": ""}:
            raise RuntimeInterviewError("cannot-assess must use the empty none measure")
    elif measure["kind"] not in question["allowed_measures"] or any(type(measure[field]) is not str or not measure[field] for field in ("expected", "actual")):
        raise RuntimeInterviewError("measure must use a presented kind with expected and actual values")
    allowed = {item["evidence_id"] for item in question["evidence"]}
    evidence_ids = response["evidence_ids"]
    if type(evidence_ids) is not list or not evidence_ids or len(evidence_ids) != len(set(evidence_ids)) or any(item not in allowed for item in evidence_ids):
        raise RuntimeInterviewError("evidence_ids must be unique ids presented with this question")
    if type(response["reason"]) is not str or not response["reason"].strip():
        raise RuntimeInterviewError("reason is required")
    return response


def answer(work: Path, response_path: Path) -> dict:
    catalog, events, answers = context(work)
    if any(event["event"] == "interview_completed" for event in events):
        raise RuntimeInterviewError("interview completed")
    question = catalog["questions"][len(answers)]
    response = validate(question, load(response_path, "response"))
    position = len(answers) + 1
    target = work / "answers" / f"answer-{position:06d}.json"
    if target.exists():
        raise RuntimeInterviewError(f"answer source already exists: {target}")
    target.write_bytes(document(response))
    append(work / "ledger.jsonl", {"event": "answer_recorded", "question_id": question["question_id"], "position": position, "answer_source": {"path": str(target), "sha256": sha(target)}, "verdict": response["verdict"]})
    if position == catalog["question_count"]:
        append(work / "ledger.jsonl", {"event": "interview_completed", "answer_count": position})
        result = {"schema_version": 1, "artifact_type": "system-alignment-runtime-results", "status": "runtime-assessment-complete", "catalog_artifact_sha256": catalog["artifact_sha256"], "results": [load(work / "answers" / f"answer-{index:06d}.json", f"answer {index}") for index in range(1, position + 1)], "dispositions": catalog["dispositions"]}
        result["artifact_sha256"] = hashlib.sha256(canonical(result)).hexdigest()
        (work / "runtime-results.json").write_bytes(document(result))
    else:
        append(work / "ledger.jsonl", {"event": "question_asked", "question_id": catalog["questions"][position]["question_id"], "position": position + 1})
    return current(work)


def development_probe(case_path: Path, result_path: Path, telemetry_path: Path) -> int:
    case = json.loads(case_path.read_text())
    work = result_path.parent / "interview"
    accepted = False
    persisted = False
    error = None
    try:
        prepare(Path(case["catalog"]), work)
        response_path = result_path.parent / "response.json"
        response_path.write_text(json.dumps(case["response"], indent=2, sort_keys=True) + "\n")
        answer(work, response_path)
        accepted = True
        persisted = (work / "runtime-results.json").is_file()
    except RuntimeInterviewError as exc:
        error = str(exc)
    correct = accepted is case["expected_accepted"]
    outcome = {"accepted": accepted, "expected_accepted": case["expected_accepted"], "correct": correct, "persisted": persisted, "error": error}
    result_path.write_text(json.dumps({"schema_version": 1, "variant_id": os.environ["EXPERIMENT_VARIANT_ID"], "status": "completed", "outcome": outcome, "metrics": {"correct-admission": int(correct), "immutable-persistence": int(persisted) if accepted else int(not case["expected_accepted"])}, "error": None}))
    telemetry_path.write_text(json.dumps({"event": "runtime-interview-probed", "outcome": outcome}) + "\n")
    return 0


def main() -> int:
    if len(sys.argv) == 4 and sys.argv[1] not in {"prepare", "next", "answer"}:
        return development_probe(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("prepare"); start.add_argument("--catalog", required=True, type=Path); start.add_argument("--work", required=True, type=Path)
    next_question = sub.add_parser("next"); next_question.add_argument("--work", required=True, type=Path)
    submit = sub.add_parser("answer"); submit.add_argument("--work", required=True, type=Path); submit.add_argument("--response", required=True, type=Path)
    args = parser.parse_args()
    try:
        value = prepare(args.catalog, args.work) if args.command == "prepare" else current(args.work) if args.command == "next" else answer(args.work, args.response)
    except RuntimeInterviewError as error:
        print(f"Runtime interview refused: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
