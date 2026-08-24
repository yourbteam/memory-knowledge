"""Replay a completed formula assessment journal into terminal answers."""

from __future__ import annotations

import json
from pathlib import Path

from formula_assessment_answer import admit_answer
from formula_assessment_question import render_question
from reporting_v3_column_index import _canonical, _sha


def replay(
    packets: list[object],
    shared_code_evidence: list[object],
    journal_path: Path,
    packets_sha256: str,
    context_sha256: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    entries: list[dict[str, object]] = []
    previous: str | None = None
    answers: list[dict[str, object]] = []
    pending: dict[str, object] | None = None
    for sequence, line in enumerate(journal_path.read_text().splitlines(), start=1):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"assessment journal entry {sequence} is invalid JSON") from exc
        if not isinstance(entry, dict):
            raise ValueError(f"assessment journal entry {sequence} is not an object")
        claimed = entry.pop("entry_sha256", None)
        actual = _sha(_canonical(entry))
        entry["entry_sha256"] = claimed
        if (
            entry.get("sequence") != sequence
            or entry.get("previous_entry_sha256") != previous
            or claimed != actual
        ):
            raise ValueError(f"assessment journal entry {sequence} fails its hash chain")
        previous = str(claimed)
        entries.append(entry)
        if sequence == 1:
            if (
                entry.get("event") != "assessment_interview_started"
                or entry.get("claim_count") != len(packets)
                or entry.get("assessment_packets_sha256") != packets_sha256
                or entry.get("shared_context_sha256") != context_sha256
            ):
                raise ValueError("assessment journal start does not bind its inputs")
            continue
        if entry.get("event") == "assessment_question_asked":
            if pending is not None:
                raise ValueError("assessment journal asks while another question is pending")
            question = entry.get("question")
            expected = render_question(packets, len(answers), shared_code_evidence)
            if question != expected:
                raise ValueError(
                    f"assessment question {sequence} differs from deterministic order"
                )
            pending = expected
        elif entry.get("event") == "assessment_answer_recorded":
            if pending is None:
                raise ValueError("assessment answer has no active question")
            answers.append(admit_answer(pending, entry.get("answer")))
            pending = None
        else:
            raise ValueError(
                f"assessment journal contains unsupported event {entry.get('event')!r}"
            )
    if pending is not None or len(answers) != len(packets):
        raise ValueError(
            f"assessment journal is incomplete: answers={len(answers)}, packets={len(packets)}"
        )
    return answers, entries
