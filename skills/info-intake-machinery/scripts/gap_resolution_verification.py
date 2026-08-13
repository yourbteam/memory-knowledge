#!/usr/bin/env python3
"""Independently verify one proposed relationship against image and operator answer."""

from __future__ import annotations

import argparse
from collections.abc import Callable
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


CONTRACT = 1


class ResolutionVerificationError(ValueError):
    """The independent resolution-verification evidence is invalid."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_json(path: Path, expected_sha256: str, label: str) -> dict[str, Any]:
    try:
        content = path.read_bytes()
        value = json.loads(content)
    except (OSError, json.JSONDecodeError) as error:
        raise ResolutionVerificationError(
            f"resolution-verification-{label}-unavailable"
        ) from error
    if _digest(content) != expected_sha256 or not isinstance(value, dict):
        raise ResolutionVerificationError(
            f"resolution-verification-{label}-changed"
        )
    return value


def _load_answer(path: Path, expected_sha256: str) -> str:
    try:
        content = path.read_bytes()
    except OSError as error:
        raise ResolutionVerificationError(
            "resolution-verification-answer-unavailable"
        ) from error
    if _digest(content) != expected_sha256:
        raise ResolutionVerificationError("resolution-verification-answer-changed")
    try:
        answer = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ResolutionVerificationError(
            "resolution-verification-answer-not-utf8"
        ) from error
    return answer


def _inputs(
    candidate_path: Path,
    candidate_sha256: str,
    resolution_path: Path,
    resolution_sha256: str,
    clarification_path: Path,
    clarification_sha256: str,
    answer_path: Path,
    answer_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]:
    candidate = _load_json(candidate_path, candidate_sha256, "candidate")
    resolution = _load_json(resolution_path, resolution_sha256, "resolution")
    clarification = _load_json(
        clarification_path, clarification_sha256, "clarification"
    )
    answer = _load_answer(answer_path, answer_sha256)
    relationships = candidate.get("relationships")
    elements = candidate.get("elements")
    if (
        resolution.get("verdict") != "resolves_gap"
        or resolution.get("verification_candidate_sha256") != candidate_sha256
        or resolution.get("clarification_sha256") != clarification_sha256
        or resolution.get("operator_answer_source_sha256") != answer_sha256
        or not isinstance(relationships, list)
        or len(relationships) != 1
        or not isinstance(elements, list)
    ):
        raise ResolutionVerificationError(
            "resolution-verification-input-binding-invalid"
        )
    relationship = relationships[0]
    if (
        not isinstance(relationship, dict)
        or relationship.get("status") != "readable"
        or relationship.get("resolution_of") != resolution.get("gap_id")
    ):
        raise ResolutionVerificationError(
            "resolution-verification-relationship-invalid"
        )
    return candidate, resolution, clarification, answer


def _entry(
    sequence: int, event: str, payload: dict[str, object], previous: str | None
) -> dict[str, object]:
    result: dict[str, object] = {
        "sequence": sequence,
        "event": event,
        "previous_entry_sha256": previous,
        **payload,
    }
    result["entry_sha256"] = _digest(_canonical(result))
    return result


def _read_journal(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    entries: list[dict[str, object]] = []
    previous: str | None = None
    for sequence, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as error:
            raise ResolutionVerificationError(
                f"resolution-verification-journal-json-invalid:{sequence}"
            ) from error
        claimed = raw.pop("entry_sha256", None)
        actual = _digest(_canonical(raw))
        raw["entry_sha256"] = claimed
        if raw.get("sequence") != sequence or raw.get("previous_entry_sha256") != previous:
            raise ResolutionVerificationError(
                f"resolution-verification-journal-chain-invalid:{sequence}"
            )
        if claimed != actual:
            raise ResolutionVerificationError(
                f"resolution-verification-journal-entry-changed:{sequence}"
            )
        previous = str(claimed)
        entries.append(raw)
    return entries


def _append(path: Path, event: str, payload: dict[str, object]) -> None:
    entries = _read_journal(path)
    result = _entry(
        len(entries) + 1,
        event,
        payload,
        str(entries[-1]["entry_sha256"]) if entries else None,
    )
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(result, sort_keys=True) + "\n")


def _participant(
    candidate: dict[str, Any], relationship: dict[str, Any], role: str
) -> dict[str, object]:
    element_id = relationship[f"{role}_id"]
    element = next(
        (
            item
            for item in candidate["elements"]
            if isinstance(item, dict) and item.get("id") == element_id
        ),
        None,
    )
    if element is None:
        raise ResolutionVerificationError(
            f"resolution-verification-{role}-element-{element_id}-missing"
        )
    return {
        "element_id": element_id,
        "point": relationship["origin_point" if role == "from" else "target_point"],
        "bounds": element.get("region"),
        "kind": element.get("kind"),
        "content": element.get("content"),
    }


def _question(
    candidate: dict[str, Any],
    clarification: dict[str, Any],
    answer: str,
    state: dict[str, str],
) -> dict[str, object] | None:
    if not state["model"]:
        return {
            "id": "verifier_model",
            "prompt": "Which fresh model is independently checking this proposed resolution?",
            "type": "string",
            "required": True,
        }
    if not state["harness"]:
        return {
            "id": "verifier_harness",
            "prompt": "Which harness is running the independent resolution check?",
            "type": "string",
            "required": True,
        }
    relationship = candidate["relationships"][0]
    evidence = {
        "operator_question": clarification["question"]["asks"],
        "operator_answer": answer,
        "proposed_relationship": {
            "kind": relationship["kind"],
            "description": relationship["description"],
            "from": _participant(candidate, relationship, "from"),
            "to": _participant(candidate, relationship, "to"),
        },
    }
    if not state["verdict"]:
        gap_record = clarification.get("gap", {}).get("record", {})
        verdict_prompt = (
            "Does the preserved operator answer select the proposed ambiguous participant, and does the frozen image visibly support the complete proposed relationship?"
            if isinstance(gap_record, dict)
            and isinstance(gap_record.get("binding_issue"), dict)
            else "Does the preserved operator answer support the locked known participant, and does the frozen image visibly support the exact missing participant and complete proposed relationship?"
        )
        return {
            "id": "resolution_verification_verdict",
            "prompt": verdict_prompt,
            "type": "choice",
            "required": True,
            "choices": ["supported", "not_supported", "unreadable"],
            "evidence": evidence,
        }
    if not state["reason"]:
        return {
            "id": "resolution_verification_reason",
            "prompt": "What exact answer and visible conditions support this independent verdict?",
            "type": "string",
            "required": True,
            "evidence": evidence,
        }
    return None


def _parse(question: dict[str, object], raw: str) -> tuple[str | None, str | None]:
    value = raw.strip()
    if not value or "\n" in value or "\r" in value:
        return None, f"{question['id']}: answer one non-empty field at a time"
    if question["type"] == "choice" and value not in question["choices"]:
        return None, (
            f"{question['id']}: received {value!r}; choose one of: "
            + ", ".join(question["choices"])
        )
    return value, None


def _replay(
    entries: list[dict[str, object]],
    candidate: dict[str, Any],
    clarification: dict[str, Any],
    answer: str,
) -> tuple[dict[str, str], dict[str, object] | None, bool]:
    state = {"model": "", "harness": "", "verdict": "", "reason": ""}
    pending: dict[str, object] | None = None
    completed = False
    for entry in entries:
        if entry["event"] == "question_asked":
            expected = _question(candidate, clarification, answer, state)
            if pending is not None or expected != entry.get("question"):
                raise ResolutionVerificationError(
                    f"resolution-verification-question-invalid:{entry['sequence']}"
                )
            pending = expected
        elif entry["event"] == "answer_recorded":
            if pending is None or entry.get("question_id") != pending["id"]:
                raise ResolutionVerificationError(
                    f"resolution-verification-answer-unbound:{entry['sequence']}"
                )
            if entry.get("accepted"):
                field = {
                    "verifier_model": "model",
                    "verifier_harness": "harness",
                    "resolution_verification_verdict": "verdict",
                    "resolution_verification_reason": "reason",
                }[str(pending["id"])]
                state[field] = str(entry["parsed"])
            pending = None
        elif entry["event"] == "verification_completed":
            if pending is not None or _question(
                candidate, clarification, answer, state
            ) is not None:
                raise ResolutionVerificationError(
                    f"resolution-verification-completion-invalid:{entry['sequence']}"
                )
            completed = True
        else:
            raise ResolutionVerificationError(
                f"resolution-verification-event-unsupported:{entry['sequence']}"
            )
    return state, pending, completed


def _prompt(question: dict[str, object], purpose: str) -> str:
    lines = [f"Intake purpose: {purpose}"]
    if "evidence" in question:
        lines.append("Bound resolution evidence: " + json.dumps(question["evidence"], sort_keys=True))
    lines.extend([f"Question: {question['prompt']}", f"Answer type: {question['type']}"])
    if question["type"] == "choice":
        lines.append("Allowed values: " + ", ".join(question["choices"]))
    lines.append("Answer: ")
    return "\n".join(lines)


def _terminal_input(prompt: str) -> str:
    print(prompt, end="", file=sys.stderr, flush=True)
    value = sys.stdin.readline()
    if value == "":
        raise ResolutionVerificationError("resolution-verification-input-ended")
    return value.rstrip("\n")


def run(
    attempt_dir: Path,
    *,
    candidate_path: Path,
    candidate_sha256: str,
    resolution_path: Path,
    resolution_sha256: str,
    clarification_path: Path,
    clarification_sha256: str,
    answer_path: Path,
    answer_sha256: str,
    purpose: str,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> dict[str, object]:
    candidate, _resolution, clarification, answer = _inputs(
        candidate_path,
        candidate_sha256,
        resolution_path,
        resolution_sha256,
        clarification_path,
        clarification_sha256,
        answer_path,
        answer_sha256,
    )
    attempt_dir.mkdir(parents=True, exist_ok=True)
    journal_path = attempt_dir / "interview.jsonl"
    result_path = attempt_dir / "verification.json"
    read = input_fn or _terminal_input
    write = output_fn or (lambda message: print(message, file=sys.stderr))
    while True:
        state, pending, completed = _replay(
            _read_journal(journal_path), candidate, clarification, answer
        )
        result = {
            "schema_version": CONTRACT,
            "candidate_sha256": candidate_sha256,
            "resolution_sha256": resolution_sha256,
            "clarification_sha256": clarification_sha256,
            "operator_answer_source_sha256": answer_sha256,
            "reader": {"model": state["model"], "harness": state["harness"]},
            "verdict": state["verdict"],
            "reason": state["reason"],
        }
        result_bytes = json.dumps(result, indent=2, sort_keys=True).encode() + b"\n"
        if completed:
            if not result_path.exists():
                result_path.write_bytes(result_bytes)
            if result_path.read_bytes() != result_bytes:
                raise ResolutionVerificationError(
                    "resolution-verification-result-changed"
                )
            return result
        question = pending or _question(candidate, clarification, answer, state)
        if question is None:
            _append(journal_path, "verification_completed", {"result_sha256": _digest(result_bytes)})
            result_path.write_bytes(result_bytes)
            continue
        if pending is None:
            _append(journal_path, "question_asked", {"question": question})
        raw = read(_prompt(question, purpose))
        parsed, error = _parse(question, raw)
        _append(journal_path, "answer_recorded", {
            "question_id": question["id"],
            "raw": raw,
            "accepted": error is None,
            "parsed": parsed,
            "error": error,
        })
        if error:
            write(f"Invalid answer: {error}.")


def validate(
    attempt_dir: Path, **kwargs: Any
) -> tuple[dict[str, object], str, str]:
    result = run(
        attempt_dir,
        **kwargs,
        input_fn=lambda _prompt: (_ for _ in ()).throw(
            ResolutionVerificationError("resolution-verification-not-complete")
        ),
        output_fn=lambda _message: None,
    )
    return (
        result,
        _digest((attempt_dir / "interview.jsonl").read_bytes()),
        _digest((attempt_dir / "verification.json").read_bytes()),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--candidate-sha256", required=True)
    parser.add_argument("--resolution", type=Path, required=True)
    parser.add_argument("--resolution-sha256", required=True)
    parser.add_argument("--clarification", type=Path, required=True)
    parser.add_argument("--clarification-sha256", required=True)
    parser.add_argument("--answer", type=Path, required=True)
    parser.add_argument("--answer-sha256", required=True)
    parser.add_argument("--purpose", required=True)
    args = parser.parse_args()
    try:
        result = run(
            args.attempt,
            candidate_path=args.candidate,
            candidate_sha256=args.candidate_sha256,
            resolution_path=args.resolution,
            resolution_sha256=args.resolution_sha256,
            clarification_path=args.clarification,
            clarification_sha256=args.clarification_sha256,
            answer_path=args.answer,
            answer_sha256=args.answer_sha256,
            purpose=args.purpose,
        )
    except ResolutionVerificationError as error:
        print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
        return 3
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
