#!/usr/bin/env python3
"""Formulate one auditable operator question round for frozen projection gaps."""

from __future__ import annotations

import argparse
from collections.abc import Callable
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


CONTRACT = 1
ROUND_CONTRACT = 1


class ClarificationError(ValueError):
    """The clarification journal or its frozen projection is invalid."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_projection(path: Path, expected_sha256: str) -> dict[str, Any]:
    try:
        content = path.read_bytes()
        projection = json.loads(content)
    except (OSError, json.JSONDecodeError) as error:
        raise ClarificationError("clarification-projection-unavailable") from error
    if _digest(content) != expected_sha256 or not isinstance(projection, dict):
        raise ClarificationError("clarification-projection-changed")
    return projection


def select_gaps(
    projection: dict[str, Any], projection_sha256: str
) -> list[dict[str, object]]:
    """Return every explicit gap in canonical projection order."""
    gaps: list[dict[str, object]] = []
    for collection, kind in (
        ("scan_regions", "scan_region"),
        ("elements", "element"),
        ("relationships", "relationship"),
    ):
        items = projection.get(collection, [])
        if not isinstance(items, list):
            raise ClarificationError(f"clarification-{collection}-invalid")
        for item in items:
            if not isinstance(item, dict):
                raise ClarificationError(f"clarification-{collection}-invalid")
            if item.get("status") != "gap":
                continue
            gap_id = item.get("id")
            reason = item.get("gap_reason")
            if not isinstance(gap_id, str) or not gap_id or not isinstance(reason, str) or not reason:
                raise ClarificationError("clarification-gap-identity-invalid")
            context: list[dict[str, Any]] = []
            if collection == "relationships":
                participant_ids = {item.get("from_id"), item.get("to_id")}
                context = [
                    element for element in projection.get("elements", [])
                    if isinstance(element, dict) and element.get("id") in participant_ids
                ]
            gaps.append({
                "projection_sha256": projection_sha256,
                "collection": collection,
                "kind": kind,
                "id": gap_id,
                "record_sha256": _digest(_canonical(item)),
                "record": item,
                "recorded_context": context,
            })
    if not gaps:
        raise ClarificationError("clarification-no-gap")
    return gaps


def select_gap(projection: dict[str, Any], projection_sha256: str) -> dict[str, object]:
    """Select the first explicit gap for legacy single-gap intakes."""
    return select_gaps(projection, projection_sha256)[0]


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
            raise ClarificationError(f"clarification-journal-json-invalid:{sequence}") from error
        claimed = raw.pop("entry_sha256", None)
        actual = _digest(_canonical(raw))
        raw["entry_sha256"] = claimed
        if raw.get("sequence") != sequence or raw.get("previous_entry_sha256") != previous:
            raise ClarificationError(f"clarification-journal-chain-invalid:{sequence}")
        if claimed != actual:
            raise ClarificationError(f"clarification-journal-entry-changed:{sequence}")
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


def _question(state: dict[str, str], gap: dict[str, object]) -> dict[str, object] | None:
    if not state["model"]:
        return {
            "id": "questioner_model",
            "prompt": "Which fresh model is formulating the operator clarification?",
            "type": "string",
            "required": True,
        }
    if not state["harness"]:
        return {
            "id": "questioner_harness",
            "prompt": "Which harness is running the clarification interview?",
            "type": "string",
            "required": True,
        }
    if not state["question"]:
        return {
            "id": "operator_question",
            "prompt": "What one focused question should the operator answer to supply the information missing from this exact gap?",
            "type": "string",
            "required": True,
            "bound_gap": gap,
        }
    return None


def _parse(question: dict[str, object], raw: str) -> tuple[str | None, str | None]:
    value = raw.strip()
    if not value or "\n" in value or "\r" in value:
        return None, f"{question['id']}: answer one non-empty field at a time"
    if str(question["id"]).startswith("operator_question") and (
        len(value) > 300 or value.count("?") != 1 or not value.endswith("?")
    ):
        return None, "operator_question: provide exactly one focused question ending in ?"
    return value, None


def _replay(
    entries: list[dict[str, object]], gap: dict[str, object]
) -> tuple[dict[str, str], dict[str, object] | None, bool]:
    state = {"model": "", "harness": "", "question": ""}
    pending: dict[str, object] | None = None
    completed = False
    for entry in entries:
        if entry["event"] == "question_asked":
            expected = _question(state, gap)
            if pending is not None or expected != entry.get("question"):
                raise ClarificationError(f"clarification-question-invalid:{entry['sequence']}")
            pending = expected
        elif entry["event"] == "answer_recorded":
            if pending is None or entry.get("question_id") != pending["id"]:
                raise ClarificationError(f"clarification-answer-unbound:{entry['sequence']}")
            if entry.get("accepted"):
                field = {
                    "questioner_model": "model",
                    "questioner_harness": "harness",
                    "operator_question": "question",
                }[str(pending["id"])]
                state[field] = str(entry["parsed"])
            pending = None
        elif entry["event"] == "clarification_completed":
            if pending is not None or _question(state, gap) is not None:
                raise ClarificationError(f"clarification-completion-invalid:{entry['sequence']}")
            completed = True
        else:
            raise ClarificationError(f"clarification-event-unsupported:{entry['sequence']}")
    return state, pending, completed


def _prompt(question: dict[str, object], purpose: str, gap: dict[str, object]) -> str:
    return "\n".join([
        f"Intake purpose: {purpose}",
        "Frozen unresolved gap: " + json.dumps(gap, sort_keys=True),
        f"Question: {question['prompt']}",
        "Answer type: string",
        "Answer: ",
    ])


def _terminal_input(prompt: str) -> str:
    print(prompt, end="", file=sys.stderr, flush=True)
    value = sys.stdin.readline()
    if value == "":
        raise ClarificationError("clarification-input-ended")
    return value.rstrip("\n")


def run(
    attempt_dir: Path,
    *,
    projection_path: Path,
    projection_sha256: str,
    purpose: str,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> dict[str, object]:
    projection = _load_projection(projection_path, projection_sha256)
    gap = select_gap(projection, projection_sha256)
    attempt_dir.mkdir(parents=True, exist_ok=True)
    journal_path = attempt_dir / "interview.jsonl"
    result_path = attempt_dir / "clarification.json"
    read = input_fn or _terminal_input
    write = output_fn or (lambda message: print(message, file=sys.stderr))
    while True:
        state, pending, completed = _replay(_read_journal(journal_path), gap)
        result = {
            "schema_version": CONTRACT,
            "projection_sha256": projection_sha256,
            "gap": gap,
            "questioner": {"model": state["model"], "harness": state["harness"]},
            "question": {
                "id": "gap-clarification-answer-000001",
                "asks": state["question"],
                "answers_gap": {
                    key: gap[key]
                    for key in ("projection_sha256", "collection", "kind", "id", "record_sha256")
                },
            },
        }
        result_bytes = json.dumps(result, indent=2, sort_keys=True).encode() + b"\n"
        if completed:
            if not result_path.exists():
                result_path.write_bytes(result_bytes)
            if result_path.read_bytes() != result_bytes:
                raise ClarificationError("clarification-result-changed")
            return result
        question = pending or _question(state, gap)
        if question is None:
            _append(journal_path, "clarification_completed", {"result_sha256": _digest(result_bytes)})
            result_path.write_bytes(result_bytes)
            continue
        if pending is None:
            _append(journal_path, "question_asked", {"question": question})
        raw = read(_prompt(question, purpose, gap))
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
    attempt_dir: Path,
    *,
    projection_path: Path,
    projection_sha256: str,
    purpose: str,
) -> tuple[dict[str, object], str, str]:
    result = run(
        attempt_dir,
        projection_path=projection_path,
        projection_sha256=projection_sha256,
        purpose=purpose,
        input_fn=lambda _prompt: (_ for _ in ()).throw(
            ClarificationError("clarification-not-complete")
        ),
        output_fn=lambda _message: None,
    )
    return (
        result,
        _digest((attempt_dir / "interview.jsonl").read_bytes()),
        _digest((attempt_dir / "clarification.json").read_bytes()),
    )


def _round_question(
    state: dict[str, Any], gaps: list[dict[str, object]], *, round_number: int = 1
) -> dict[str, object] | None:
    if not state["model"]:
        return {
            "id": "questioner_model",
            "prompt": "Which fresh model is formulating this operator question round?",
            "type": "string",
            "required": True,
        }
    if not state["harness"]:
        return {
            "id": "questioner_harness",
            "prompt": "Which harness is running this clarification round?",
            "type": "string",
            "required": True,
        }
    index = len(state["questions"])
    if index >= len(gaps):
        return None
    return {
        "id": f"operator_question_{index + 1:06d}",
        "prompt": (
            "What one new focused question should the operator answer to supply "
            "the still-missing information identified by the prior failed "
            "clarification?"
            if round_number > 1
            else "What one focused question should the operator answer to supply "
            "the information missing from this exact gap?"
        ),
        "type": "string",
        "required": True,
        "gap_index": index,
        "bound_gap": gaps[index],
    }


def _round_replay(
    entries: list[dict[str, object]], gaps: list[dict[str, object]], *, round_number: int = 1
) -> tuple[dict[str, Any], dict[str, object] | None, bool]:
    state: dict[str, Any] = {"model": "", "harness": "", "questions": []}
    pending: dict[str, object] | None = None
    completed = False
    for entry in entries:
        if entry["event"] == "question_asked":
            expected = _round_question(state, gaps, round_number=round_number)
            if pending is not None or expected != entry.get("question"):
                raise ClarificationError(
                    f"clarification-round-question-invalid:{entry['sequence']}"
                )
            pending = expected
        elif entry["event"] == "answer_recorded":
            if pending is None or entry.get("question_id") != pending["id"]:
                raise ClarificationError(
                    f"clarification-round-answer-unbound:{entry['sequence']}"
                )
            if entry.get("accepted"):
                question_id = str(pending["id"])
                if question_id == "questioner_model":
                    state["model"] = str(entry["parsed"])
                elif question_id == "questioner_harness":
                    state["harness"] = str(entry["parsed"])
                else:
                    expected_id = f"operator_question_{len(state['questions']) + 1:06d}"
                    if question_id != expected_id:
                        raise ClarificationError(
                            f"clarification-round-order-invalid:{entry['sequence']}"
                        )
                    state["questions"].append(str(entry["parsed"]))
            pending = None
        elif entry["event"] == "clarification_round_completed":
            if (
                pending is not None
                or _round_question(state, gaps, round_number=round_number) is not None
            ):
                raise ClarificationError(
                    f"clarification-round-completion-invalid:{entry['sequence']}"
                )
            completed = True
        else:
            raise ClarificationError(
                f"clarification-round-event-unsupported:{entry['sequence']}"
            )
    return state, pending, completed


def _round_result(
    projection_sha256: str,
    gaps: list[dict[str, object]],
    state: dict[str, Any],
    *,
    round_number: int = 1,
) -> dict[str, object]:
    questions = []
    for index, gap in enumerate(gaps):
        asks = state["questions"][index] if index < len(state["questions"]) else ""
        questions.append({
            "id": (
                f"gap-clarification-answer-{index + 1:06d}"
                if round_number == 1
                else f"gap-clarification-round-{round_number:06d}-question-{index + 1:06d}"
            ),
            "asks": asks,
            "answers_gap": {
                key: gap[key]
                for key in (
                    "projection_sha256", "collection", "kind", "id", "record_sha256"
                )
            },
        })
    result: dict[str, object] = {
        "schema_version": ROUND_CONTRACT,
        "projection_sha256": projection_sha256,
        "gaps": gaps,
        "questioner": {"model": state["model"], "harness": state["harness"]},
        "questions": questions,
    }
    if round_number > 1:
        result["round"] = round_number
    return result


def _validate_bound_gaps(
    projection: dict[str, Any],
    projection_sha256: str,
    gaps: list[dict[str, object]],
) -> None:
    current = {
        (item["collection"], item["id"]): item
        for item in select_gaps(projection, projection_sha256)
    }
    if not gaps:
        raise ClarificationError("clarification-follow-up-no-gap")
    for gap in gaps:
        if not isinstance(gap, dict):
            raise ClarificationError("clarification-follow-up-gap-invalid")
        key = (gap.get("collection"), gap.get("id"))
        selected = current.get(key)
        if selected is None:
            raise ClarificationError("clarification-follow-up-gap-not-current")
        for field in (
            "projection_sha256", "collection", "kind", "id", "record_sha256",
            "record", "recorded_context",
        ):
            if gap.get(field) != selected.get(field):
                raise ClarificationError("clarification-follow-up-gap-changed")
        follow_up = gap.get("follow_up_of")
        if not isinstance(follow_up, dict):
            raise ClarificationError("clarification-follow-up-context-missing")


def run_round(
    round_dir: Path,
    *,
    projection_path: Path,
    projection_sha256: str,
    purpose: str,
    gaps: list[dict[str, object]] | None = None,
    round_number: int = 1,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> dict[str, object]:
    projection = _load_projection(projection_path, projection_sha256)
    if gaps is None:
        gaps = select_gaps(projection, projection_sha256)
    else:
        _validate_bound_gaps(projection, projection_sha256, gaps)
    round_dir.mkdir(parents=True, exist_ok=True)
    journal_path = round_dir / "interview.jsonl"
    result_path = round_dir / "clarification-round.json"
    read = input_fn or _terminal_input
    write = output_fn or (lambda message: print(message, file=sys.stderr))
    while True:
        state, pending, completed = _round_replay(
            _read_journal(journal_path), gaps, round_number=round_number
        )
        result = _round_result(
            projection_sha256, gaps, state, round_number=round_number
        )
        result_bytes = json.dumps(result, indent=2, sort_keys=True).encode() + b"\n"
        if completed:
            if not result_path.exists():
                result_path.write_bytes(result_bytes)
            if result_path.read_bytes() != result_bytes:
                raise ClarificationError("clarification-round-result-changed")
            return result
        question = pending or _round_question(
            state, gaps, round_number=round_number
        )
        if question is None:
            _append(
                journal_path,
                "clarification_round_completed",
                {"result_sha256": _digest(result_bytes), "gap_count": len(gaps)},
            )
            result_path.write_bytes(result_bytes)
            continue
        if pending is None:
            _append(journal_path, "question_asked", {"question": question})
        gap = (
            gaps[int(question["gap_index"])]
            if "gap_index" in question
            else {"round_gap_count": len(gaps)}
        )
        raw = read(_prompt(question, purpose, gap))
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


def validate_round(
    round_dir: Path,
    *,
    projection_path: Path,
    projection_sha256: str,
    purpose: str,
    gaps: list[dict[str, object]] | None = None,
    round_number: int = 1,
) -> tuple[dict[str, object], str, str]:
    result = run_round(
        round_dir,
        projection_path=projection_path,
        projection_sha256=projection_sha256,
        purpose=purpose,
        gaps=gaps,
        round_number=round_number,
        input_fn=lambda _prompt: (_ for _ in ()).throw(
            ClarificationError("clarification-round-not-complete")
        ),
        output_fn=lambda _message: None,
    )
    return (
        result,
        _digest((round_dir / "interview.jsonl").read_bytes()),
        _digest((round_dir / "clarification-round.json").read_bytes()),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt", type=Path, required=True)
    parser.add_argument("--projection", type=Path, required=True)
    parser.add_argument("--projection-sha256", required=True)
    parser.add_argument("--purpose", required=True)
    args = parser.parse_args()
    try:
        result = run(
            args.attempt,
            projection_path=args.projection,
            projection_sha256=args.projection_sha256,
            purpose=args.purpose,
        )
    except ClarificationError as error:
        print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
        return 3
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
