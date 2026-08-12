#!/usr/bin/env python3
"""Run an independent code-controlled visual check of proposed relationships."""

from __future__ import annotations

import argparse
from collections.abc import Callable
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


CONTRACT = 1


class VerificationError(ValueError):
    """The verification journal or its bound candidate is invalid."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _entry(sequence: int, event: str, payload: dict[str, object], previous: str | None) -> dict[str, object]:
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
            raise VerificationError(f"verification-journal-json-invalid:{sequence}") from error
        claimed = raw.pop("entry_sha256", None)
        actual = _digest(_canonical(raw))
        raw["entry_sha256"] = claimed
        if raw.get("sequence") != sequence or raw.get("previous_entry_sha256") != previous:
            raise VerificationError(f"verification-journal-chain-invalid:{sequence}")
        if claimed != actual:
            raise VerificationError(f"verification-journal-entry-changed:{sequence}")
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


def _load_candidate(path: Path, expected_sha256: str) -> dict[str, Any]:
    try:
        content = path.read_bytes()
        candidate = json.loads(content)
    except (OSError, json.JSONDecodeError) as error:
        raise VerificationError("verification-candidate-unavailable") from error
    if _digest(content) != expected_sha256 or not isinstance(candidate, dict):
        raise VerificationError("verification-candidate-changed")
    if not isinstance(candidate.get("elements"), list) or not isinstance(candidate.get("relationships"), list):
        raise VerificationError("verification-candidate-shape-invalid")
    return candidate


def _participant(candidate: dict[str, Any], relationship: dict[str, Any], role: str) -> dict[str, Any]:
    element_id = relationship[f"{role}_id"]
    element = next((item for item in candidate["elements"] if item["id"] == element_id), None)
    if element is None:
        raise VerificationError(f"verification-{role}-missing:{relationship['id']}")
    point_key = "origin_point" if role == "from" else "target_point"
    return {
        "element_id": element_id,
        "point": relationship.get(point_key),
        "bounds": element["region"],
        "kind": element["kind"],
        "status": element["status"],
        "content": element["content"],
        "gap_reason": element["gap_reason"],
    }


def _verifiable_relationships(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    relationships = candidate["relationships"]
    if any(
        not isinstance(relationship, dict)
        or relationship.get("status") not in {"readable", "gap"}
        for relationship in relationships
    ):
        raise VerificationError("verification-relationship-status-invalid")
    return [relationship for relationship in relationships if relationship["status"] == "readable"]


def _question(candidate: dict[str, Any], state: dict[str, Any]) -> dict[str, object] | None:
    if not state.get("model"):
        return {"id": "verifier_model", "prompt": "Which fresh model is independently checking the frozen source?", "type": "string", "required": True}
    if not state.get("harness"):
        return {"id": "verifier_harness", "prompt": "Which harness is running this independent check?", "type": "string", "required": True}
    index = int(state["index"])
    relationships = _verifiable_relationships(candidate)
    if index >= len(relationships):
        return None
    relationship = relationships[index]
    if state.get("pending_reason"):
        return {
            "id": "relationship_visual_reason",
            "prompt": "What visible condition supports this independent verdict?",
            "type": "string",
            "required": True,
            "relationship_id": relationship["id"],
        }
    return {
        "id": "relationship_visual_verdict",
        "prompt": "Based only on the frozen source, does the visible relationship terminate at these exact proposed participants?",
        "type": "choice",
        "required": True,
        "choices": ["supported", "not_supported", "unreadable"],
        "relationship_id": relationship["id"],
        "proposed_relationship": {
            "kind": relationship["kind"],
            "from": _participant(candidate, relationship, "from"),
            "to": _participant(candidate, relationship, "to"),
        },
    }


def _parse(question: dict[str, object], raw: str) -> tuple[str | None, str | None]:
    value = raw.strip()
    if not value or "\n" in value or "\r" in value:
        return None, f"{question['id']}: answer one non-empty field at a time"
    if question["type"] == "choice" and value not in question["choices"]:
        return None, f"{question['id']}: choose one of: {', '.join(question['choices'])}"
    return value, None


def _replay(entries: list[dict[str, object]], candidate: dict[str, Any]) -> tuple[dict[str, Any], dict[str, object] | None, bool]:
    state: dict[str, Any] = {"model": "", "harness": "", "index": 0, "pending_reason": "", "verdicts": []}
    pending: dict[str, object] | None = None
    completed = False
    for entry in entries:
        if entry["event"] == "question_asked":
            expected = _question(candidate, state)
            if pending is not None or expected != entry.get("question"):
                raise VerificationError(f"verification-question-invalid:{entry['sequence']}")
            pending = expected
        elif entry["event"] == "answer_recorded":
            if pending is None or entry.get("question_id") != pending["id"]:
                raise VerificationError(f"verification-answer-unbound:{entry['sequence']}")
            if entry.get("accepted"):
                value = str(entry["parsed"])
                if pending["id"] == "verifier_model":
                    state["model"] = value
                elif pending["id"] == "verifier_harness":
                    state["harness"] = value
                elif pending["id"] == "relationship_visual_verdict":
                    state["pending_reason"] = value
                else:
                    relationship = _verifiable_relationships(candidate)[state["index"]]
                    state["verdicts"].append({
                        "relationship_id": relationship["id"],
                        "verdict": state["pending_reason"],
                        "reason": value,
                    })
                    state["index"] += 1
                    state["pending_reason"] = ""
            pending = None
        elif entry["event"] == "verification_completed":
            if pending is not None or _question(candidate, state) is not None:
                raise VerificationError(f"verification-completion-invalid:{entry['sequence']}")
            completed = True
        else:
            raise VerificationError(f"verification-event-unsupported:{entry['sequence']}")
    return state, pending, completed


def _prompt(question: dict[str, object], purpose: str) -> str:
    lines = [f"Intake purpose: {purpose}"]
    proposed = question.get("proposed_relationship")
    if isinstance(proposed, dict):
        lines.append("Proposed exact participants: " + json.dumps(proposed, sort_keys=True))
    lines.extend([f"Question: {question['prompt']}", f"Answer type: {question['type']}"])
    if question["type"] == "choice":
        lines.append("Allowed values: " + ", ".join(question["choices"]))
    lines.append("Answer: ")
    return "\n".join(lines)


def _terminal_input(prompt: str) -> str:
    print(prompt, end="", file=sys.stderr, flush=True)
    value = sys.stdin.readline()
    if value == "":
        raise VerificationError("verification-input-ended")
    return value.rstrip("\n")


def run(
    attempt_dir: Path,
    *,
    candidate_path: Path,
    candidate_sha256: str,
    purpose: str,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> dict[str, object]:
    candidate = _load_candidate(candidate_path, candidate_sha256)
    attempt_dir.mkdir(parents=True, exist_ok=True)
    journal_path = attempt_dir / "interview.jsonl"
    result_path = attempt_dir / "verification.json"
    read = input_fn or _terminal_input
    write = output_fn or (lambda message: print(message, file=sys.stderr))
    while True:
        entries = _read_journal(journal_path)
        state, pending, completed = _replay(entries, candidate)
        result = {
            "schema_version": CONTRACT,
            "candidate_sha256": candidate_sha256,
            "reader": {"model": state["model"], "harness": state["harness"]},
            "verdicts": state["verdicts"],
        }
        result_bytes = json.dumps(result, indent=2, sort_keys=True).encode() + b"\n"
        if completed:
            if not result_path.exists():
                result_path.write_bytes(result_bytes)
            if result_path.read_bytes() != result_bytes:
                raise VerificationError("verification-result-changed")
            return result
        question = pending or _question(candidate, state)
        if question is None:
            _append(journal_path, "verification_completed", {"result_sha256": _digest(result_bytes)})
            result_path.write_bytes(result_bytes)
            continue
        if pending is None:
            _append(journal_path, "question_asked", {"question": question})
        raw = read(_prompt(question, purpose))
        parsed, error = _parse(question, raw)
        _append(journal_path, "answer_recorded", {
            "question_id": question["id"], "raw": raw,
            "accepted": error is None, "parsed": parsed, "error": error,
        })
        if error:
            write(f"Invalid answer: {error}.")


def validate(
    attempt_dir: Path, *, candidate_path: Path, candidate_sha256: str, purpose: str,
) -> tuple[dict[str, object], str, str]:
    result = run(
        attempt_dir,
        candidate_path=candidate_path,
        candidate_sha256=candidate_sha256,
        purpose=purpose,
        input_fn=lambda _prompt: (_ for _ in ()).throw(VerificationError("verification-not-complete")),
        output_fn=lambda _message: None,
    )
    journal = (attempt_dir / "interview.jsonl").read_bytes()
    result_bytes = (attempt_dir / "verification.json").read_bytes()
    return result, _digest(journal), _digest(result_bytes)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--candidate-sha256", required=True)
    parser.add_argument("--purpose", required=True)
    args = parser.parse_args()
    try:
        result = run(
            args.attempt,
            candidate_path=args.candidate,
            candidate_sha256=args.candidate_sha256,
            purpose=args.purpose,
        )
    except VerificationError as error:
        print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
        return 3
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
