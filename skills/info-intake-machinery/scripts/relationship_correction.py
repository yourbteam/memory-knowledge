#!/usr/bin/env python3
"""Create auditable correction proposals for independently rejected relationships."""

from __future__ import annotations

import argparse
from collections.abc import Callable
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


CONTRACT = 1


class CorrectionError(ValueError):
    """The correction journal or one of its frozen inputs is invalid."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_json(path: Path, expected_sha256: str, label: str) -> dict[str, Any]:
    try:
        content = path.read_bytes()
        value = json.loads(content)
    except (OSError, json.JSONDecodeError) as error:
        raise CorrectionError(f"correction-{label}-unavailable") from error
    if _digest(content) != expected_sha256 or not isinstance(value, dict):
        raise CorrectionError(f"correction-{label}-changed")
    return value


def _inputs(
    candidate_path: Path,
    candidate_sha256: str,
    verification_path: Path,
    verification_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any], list[tuple[dict[str, Any], dict[str, Any]]]]:
    candidate = _load_json(candidate_path, candidate_sha256, "candidate")
    verification = _load_json(verification_path, verification_sha256, "verification")
    relationships = candidate.get("relationships")
    elements = candidate.get("elements")
    verdicts = verification.get("verdicts")
    if not isinstance(relationships, list) or not isinstance(elements, list):
        raise CorrectionError("correction-candidate-shape-invalid")
    if verification.get("candidate_sha256") != candidate_sha256 or not isinstance(verdicts, list):
        raise CorrectionError("correction-verification-binding-invalid")
    readable_relationships = [
        relationship for relationship in relationships
        if isinstance(relationship, dict) and relationship.get("status") == "readable"
    ]
    if len(verdicts) != len(readable_relationships):
        raise CorrectionError("correction-verdict-coverage-invalid")
    rejected: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for relationship, verdict in zip(readable_relationships, verdicts, strict=True):
        if not isinstance(relationship, dict) or not isinstance(verdict, dict):
            raise CorrectionError("correction-input-shape-invalid")
        if verdict.get("relationship_id") != relationship.get("id"):
            raise CorrectionError("correction-verdict-order-invalid")
        if verdict.get("verdict") not in {"supported", "not_supported", "unreadable"}:
            raise CorrectionError("correction-verdict-value-invalid")
        if verdict["verdict"] != "supported":
            rejected.append((relationship, verdict))
    return candidate, verification, rejected


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
            raise CorrectionError(f"correction-journal-json-invalid:{sequence}") from error
        claimed = raw.pop("entry_sha256", None)
        actual = _digest(_canonical(raw))
        raw["entry_sha256"] = claimed
        if raw.get("sequence") != sequence or raw.get("previous_entry_sha256") != previous:
            raise CorrectionError(f"correction-journal-chain-invalid:{sequence}")
        if claimed != actual:
            raise CorrectionError(f"correction-journal-entry-changed:{sequence}")
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


def _context(relationship: dict[str, Any], verdict: dict[str, Any]) -> dict[str, object]:
    return {
        "original_relationship_id": relationship["id"],
        "original_from_id": relationship["from_id"],
        "original_to_id": relationship["to_id"],
        "original_kind": relationship["kind"],
        "original_description": relationship["description"],
        "independent_verdict": verdict["verdict"],
        "independent_reason": verdict["reason"],
    }


def _question(
    candidate: dict[str, Any],
    rejected: list[tuple[dict[str, Any], dict[str, Any]]],
    state: dict[str, Any],
) -> dict[str, object] | None:
    if not state["model"]:
        return {"id": "corrector_model", "prompt": "Which fresh model is proposing relationship corrections?", "type": "string", "required": True}
    if not state["harness"]:
        return {"id": "corrector_harness", "prompt": "Which harness is running the correction interview?", "type": "string", "required": True}
    if state["index"] >= len(rejected):
        return None
    relationship, verdict = rejected[state["index"]]
    draft = state["draft"]
    common = {"relationship_id": relationship["id"], "rejection": _context(relationship, verdict)}
    if not draft.get("action"):
        return {**common, "id": "correction_action", "prompt": "Can a faithful visible endpoint replace the rejected participant?", "type": "choice", "required": True, "choices": ["propose_replacement_endpoint", "preserve_gap"]}
    if draft["action"] == "preserve_gap":
        return {**common, "id": "correction_gap_reason", "prompt": "Why can no faithful visible endpoint be recorded?", "type": "string", "required": True}
    if not draft.get("role"):
        return {**common, "id": "replacement_role", "prompt": "Which rejected participant must be replaced?", "type": "choice", "required": True, "choices": ["origin", "target"]}
    if not draft.get("source"):
        return {**common, "id": "replacement_source", "prompt": "Is the faithful endpoint already a recorded element or must it be recorded now?", "type": "choice", "required": True, "choices": ["use_recorded_element", "record_visible_element"]}
    if draft["source"] == "use_recorded_element" and not draft.get("element_id"):
        original_id = relationship[
            "from_id" if draft["role"] == "origin" else "to_id"
        ]
        choices = [
            element["id"] for element in candidate["elements"]
            if element.get("status") == "readable" and element.get("id") != original_id
        ]
        if not choices:
            raise CorrectionError(f"correction-no-recorded-replacement:{relationship['id']}")
        return {
            **common,
            "id": "replacement_element_id",
            "prompt": "Which recorded readable element is the faithful replacement endpoint?",
            "type": "choice",
            "required": True,
            "choices": choices,
            "choice_evidence": {
                element["id"]: {
                    "kind": element.get("kind"),
                    "content": element.get("content"),
                    "region": element.get("region"),
                }
                for element in candidate["elements"] if element.get("id") in choices
            },
        }
    if draft["source"] == "record_visible_element":
        fields = [
            ("replacement_kind", "What kind of visible element is the replacement endpoint?", "string"),
            ("replacement_left", "Replacement element left bound (0-1000)?", "integer"),
            ("replacement_top", "Replacement element top bound (0-1000)?", "integer"),
            ("replacement_right", "Replacement element right bound (0-1000)?", "integer"),
            ("replacement_bottom", "Replacement element bottom bound (0-1000)?", "integer"),
            ("replacement_content", "What readable content is visibly present in the replacement endpoint?", "string"),
        ]
        for field, prompt, answer_type in fields:
            if field not in draft:
                return {**common, "id": field, "prompt": prompt, "type": answer_type, "required": True}
    point_fields = [
        ("replacement_x", "Visible replacement endpoint x-coordinate (0-1000)?"),
        ("replacement_y", "Visible replacement endpoint y-coordinate (0-1000)?"),
    ]
    for field, prompt in point_fields:
        if field not in draft:
            return {**common, "id": field, "prompt": prompt, "type": "integer", "required": True}
    if "description" not in draft:
        return {**common, "id": "corrected_relationship_description", "prompt": "What does the corrected visible relationship mean for the intake purpose?", "type": "string", "required": True}
    raise CorrectionError("correction-state-invalid")


def _contains(region: object, x: int, y: int) -> bool:
    return (
        isinstance(region, list)
        and len(region) == 4
        and all(isinstance(value, int) for value in region)
        and region[0] <= x <= region[2]
        and region[1] <= y <= region[3]
    )


def _existing_endpoint(candidate: dict[str, Any], x: int, y: int) -> dict[str, Any] | None:
    matches = [
        element for element in candidate["elements"]
        if element.get("status") == "readable" and _contains(element.get("region"), x, y)
    ]
    return matches[0] if len(matches) == 1 else None


def _parse(
    question: dict[str, object], raw: str, candidate: dict[str, Any], state: dict[str, Any]
) -> tuple[str | int | None, str | None]:
    value = raw.strip()
    if not value or "\n" in value or "\r" in value:
        return None, f"{question['id']}: answer one non-empty field at a time"
    if question["type"] == "choice" and value not in question["choices"]:
        return None, f"{question['id']}: choose one of: {', '.join(question['choices'])}"
    if question["type"] == "integer":
        try:
            parsed = int(value)
        except ValueError:
            return None, f"{question['id']}: enter one integer from 0 through 1000"
        if not 0 <= parsed <= 1000:
            return None, f"{question['id']}: enter one integer from 0 through 1000"
        draft = state["draft"]
        if question["id"] == "replacement_right" and parsed <= draft["replacement_left"]:
            return None, "replacement_right: must be greater than replacement_left"
        if question["id"] == "replacement_bottom" and parsed <= draft["replacement_top"]:
            return None, "replacement_bottom: must be greater than replacement_top"
        if question["id"] == "replacement_y":
            x = draft["replacement_x"]
            if draft["source"] == "use_recorded_element":
                endpoint = next(
                    element for element in candidate["elements"]
                    if element["id"] == draft["element_id"]
                )
                if not _contains(endpoint.get("region"), x, parsed):
                    return None, "replacement_y: point must fall inside the selected recorded element"
            else:
                region = [draft["replacement_left"], draft["replacement_top"], draft["replacement_right"], draft["replacement_bottom"]]
                if not _contains(region, x, parsed):
                    return None, "replacement_y: point must fall inside the new replacement element"
        return parsed, None
    return value, None


def _complete_draft(candidate: dict[str, Any], state: dict[str, Any], original: dict[str, Any]) -> dict[str, Any]:
    draft = state["draft"]
    if draft["action"] == "preserve_gap":
        return {
            "original_relationship_id": original["id"],
            "action": "preserve_gap",
            "gap_reason": draft["gap_reason"],
        }
    replacement_number = 1 + sum(
        item.get("replacement_element", {}).get("created_by_correction") is True
        for item in state["corrections"]
    )
    if draft["source"] == "use_recorded_element":
        replacement = next(
            element for element in candidate["elements"]
            if element["id"] == draft["element_id"]
        )
        replacement_element = {"id": replacement["id"], "created_by_correction": False}
    else:
        replacement = {
            "id": f"correction-element-{replacement_number:06d}",
            "kind": draft["replacement_kind"],
            "region": [draft["replacement_left"], draft["replacement_top"], draft["replacement_right"], draft["replacement_bottom"]],
            "status": "readable",
            "content": draft["replacement_content"],
            "gap_reason": "",
            "capture_scope": "relationship_correction_endpoint",
        }
        replacement_element = {**replacement, "created_by_correction": True}
    role_key = "from_id" if draft["role"] == "origin" else "to_id"
    point_key = "origin_point" if draft["role"] == "origin" else "target_point"
    if replacement["id"] == original[role_key]:
        raise CorrectionError(f"correction-replacement-unchanged:{original['id']}")
    corrected = {
        **original,
        "id": f"{original['id']}-correction-000001",
        "correction_of": original["id"],
        role_key: replacement["id"],
        point_key: [draft["replacement_x"], draft["replacement_y"]],
        "description": draft["description"],
        "status": "readable",
        "gap_reason": "",
        "binding_method": "correction_selected_identity_and_containment",
    }
    corrected.pop("independent_visual_verification", None)
    corrected.pop("visual_verification", None)
    corrected.pop("verification_issue", None)
    return {
        "original_relationship_id": original["id"],
        "action": "propose_replacement_endpoint",
        "replacement_role": draft["role"],
        "replacement_source": draft["source"],
        "replacement_element": replacement_element,
        "corrected_relationship": corrected,
    }


def _apply_answer(
    candidate: dict[str, Any], rejected: list[tuple[dict[str, Any], dict[str, Any]]],
    state: dict[str, Any], question_id: str, value: str | int,
) -> None:
    if question_id == "corrector_model":
        state["model"] = value
    elif question_id == "corrector_harness":
        state["harness"] = value
    else:
        draft = state["draft"]
        keys = {
            "correction_action": "action", "correction_gap_reason": "gap_reason",
            "replacement_role": "role", "replacement_source": "source",
            "replacement_element_id": "element_id",
            "corrected_relationship_description": "description",
        }
        draft[keys.get(question_id, question_id)] = value
        finished = draft.get("gap_reason") if draft.get("action") == "preserve_gap" else draft.get("description")
        if finished:
            original, _verdict = rejected[state["index"]]
            state["corrections"].append(_complete_draft(candidate, state, original))
            state["index"] += 1
            state["draft"] = {}


def _replay(
    entries: list[dict[str, object]], candidate: dict[str, Any],
    rejected: list[tuple[dict[str, Any], dict[str, Any]]],
) -> tuple[dict[str, Any], dict[str, object] | None, bool]:
    state: dict[str, Any] = {"model": "", "harness": "", "index": 0, "draft": {}, "corrections": []}
    pending: dict[str, object] | None = None
    completed = False
    for entry in entries:
        if entry["event"] == "question_asked":
            expected = _question(candidate, rejected, state)
            if pending is not None or expected != entry.get("question"):
                raise CorrectionError(f"correction-question-invalid:{entry['sequence']}")
            pending = expected
        elif entry["event"] == "answer_recorded":
            if pending is None or entry.get("question_id") != pending["id"]:
                raise CorrectionError(f"correction-answer-unbound:{entry['sequence']}")
            if entry.get("accepted"):
                _apply_answer(candidate, rejected, state, str(pending["id"]), entry["parsed"])
            pending = None
        elif entry["event"] == "correction_completed":
            if pending is not None or _question(candidate, rejected, state) is not None:
                raise CorrectionError(f"correction-completion-invalid:{entry['sequence']}")
            completed = True
        else:
            raise CorrectionError(f"correction-event-unsupported:{entry['sequence']}")
    return state, pending, completed


def _verification_candidate(candidate: dict[str, Any], corrections: list[dict[str, Any]]) -> dict[str, object]:
    new_elements = [
        {key: value for key, value in item["replacement_element"].items() if key != "created_by_correction"}
        for item in corrections
        if item["action"] == "propose_replacement_endpoint"
        and item["replacement_element"]["created_by_correction"] is True
    ]
    return {
        "schema_version": CONTRACT,
        "source_sha256": candidate.get("source_sha256"),
        "elements": [*candidate["elements"], *new_elements],
        "relationships": [
            item["corrected_relationship"]
            for item in corrections if item["action"] == "propose_replacement_endpoint"
        ],
    }


def _prompt(question: dict[str, object], purpose: str) -> str:
    lines = [f"Intake purpose: {purpose}"]
    if "rejection" in question:
        lines.append("Frozen rejected proposal: " + json.dumps(question["rejection"], sort_keys=True))
    lines.extend([f"Question: {question['prompt']}", f"Answer type: {question['type']}"])
    if question["type"] == "choice":
        lines.append("Allowed values: " + ", ".join(question["choices"]))
    if "choice_evidence" in question:
        lines.append("Allowed-value evidence: " + json.dumps(question["choice_evidence"], sort_keys=True))
    lines.append("Answer: ")
    return "\n".join(lines)


def _terminal_input(prompt: str) -> str:
    print(prompt, end="", file=sys.stderr, flush=True)
    value = sys.stdin.readline()
    if value == "":
        raise CorrectionError("correction-input-ended")
    return value.rstrip("\n")


def run(
    attempt_dir: Path, *, candidate_path: Path, candidate_sha256: str,
    verification_path: Path, verification_sha256: str, purpose: str,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> dict[str, object]:
    candidate, _verification, rejected = _inputs(
        candidate_path, candidate_sha256, verification_path, verification_sha256
    )
    attempt_dir.mkdir(parents=True, exist_ok=True)
    journal_path = attempt_dir / "interview.jsonl"
    result_path = attempt_dir / "corrections.json"
    verification_candidate_path = attempt_dir / "verification-candidate.json"
    read = input_fn or _terminal_input
    write = output_fn or (lambda message: print(message, file=sys.stderr))
    while True:
        state, pending, completed = _replay(_read_journal(journal_path), candidate, rejected)
        verification_candidate = _verification_candidate(candidate, state["corrections"])
        verification_candidate_bytes = json.dumps(verification_candidate, indent=2, sort_keys=True).encode() + b"\n"
        result = {
            "schema_version": CONTRACT,
            "candidate_sha256": candidate_sha256,
            "verification_sha256": verification_sha256,
            "corrector": {"model": state["model"], "harness": state["harness"]},
            "corrections": state["corrections"],
            "verification_candidate_sha256": _digest(verification_candidate_bytes),
        }
        result_bytes = json.dumps(result, indent=2, sort_keys=True).encode() + b"\n"
        if completed:
            if not result_path.exists():
                result_path.write_bytes(result_bytes)
                verification_candidate_path.write_bytes(verification_candidate_bytes)
            if result_path.read_bytes() != result_bytes or verification_candidate_path.read_bytes() != verification_candidate_bytes:
                raise CorrectionError("correction-result-changed")
            return result
        question = pending or _question(candidate, rejected, state)
        if question is None:
            _append(journal_path, "correction_completed", {"result_sha256": _digest(result_bytes)})
            result_path.write_bytes(result_bytes)
            verification_candidate_path.write_bytes(verification_candidate_bytes)
            continue
        if pending is None:
            _append(journal_path, "question_asked", {"question": question})
        raw = read(_prompt(question, purpose))
        parsed, error = _parse(question, raw, candidate, state)
        _append(journal_path, "answer_recorded", {
            "question_id": question["id"], "raw": raw, "accepted": error is None,
            "parsed": parsed, "error": error,
        })
        if error:
            write(f"Invalid answer: {error}.")


def validate(
    attempt_dir: Path, *, candidate_path: Path, candidate_sha256: str,
    verification_path: Path, verification_sha256: str, purpose: str,
) -> tuple[dict[str, object], str, str, str]:
    result = run(
        attempt_dir, candidate_path=candidate_path, candidate_sha256=candidate_sha256,
        verification_path=verification_path, verification_sha256=verification_sha256,
        purpose=purpose,
        input_fn=lambda _prompt: (_ for _ in ()).throw(CorrectionError("correction-not-complete")),
        output_fn=lambda _message: None,
    )
    return (
        result,
        _digest((attempt_dir / "interview.jsonl").read_bytes()),
        _digest((attempt_dir / "corrections.json").read_bytes()),
        _digest((attempt_dir / "verification-candidate.json").read_bytes()),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--candidate-sha256", required=True)
    parser.add_argument("--verification", type=Path, required=True)
    parser.add_argument("--verification-sha256", required=True)
    parser.add_argument("--purpose", required=True)
    args = parser.parse_args()
    try:
        result = run(
            args.attempt, candidate_path=args.candidate,
            candidate_sha256=args.candidate_sha256,
            verification_path=args.verification,
            verification_sha256=args.verification_sha256,
            purpose=args.purpose,
        )
    except CorrectionError as error:
        print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
        return 3
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
