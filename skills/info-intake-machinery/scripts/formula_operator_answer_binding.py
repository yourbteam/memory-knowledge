"""Bind one preserved operator answer to one exact formula question."""

from __future__ import annotations

import hashlib
import json


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def bind_answer(
    question: object,
    answer: object,
    allowed_choices: tuple[str, ...],
    required_choice: str | None = None,
) -> dict[str, object]:
    if not isinstance(question, dict) or set(question) != {
        "id",
        "claim_ids",
        "question",
        "reason",
    }:
        raise ValueError("operator question has invalid exact shape")
    claim_ids = question["claim_ids"]
    if (
        not isinstance(claim_ids, list)
        or not claim_ids
        or any(not isinstance(value, str) or not value for value in claim_ids)
        or len(set(claim_ids)) != len(claim_ids)
    ):
        raise ValueError("operator question claim_ids must be unique nonempty strings")
    if not allowed_choices or len(set(allowed_choices)) != len(allowed_choices):
        raise ValueError("allowed answer choices must be unique and nonempty")
    if any(not isinstance(value, str) or not value for value in allowed_choices):
        raise ValueError("allowed answer choices must be unique and nonempty")
    if not isinstance(answer, dict) or set(answer) != {
        "question_id",
        "raw_answer",
        "choice",
        "reason",
    }:
        raise ValueError("operator answer has invalid exact shape")
    if answer["question_id"] != question["id"]:
        raise ValueError(
            f"operator answer question_id {answer['question_id']!r} differs from "
            f"active question {question['id']!r}"
        )
    choice = answer["choice"]
    if choice not in allowed_choices:
        raise ValueError(
            f"operator answer choice {choice!r} is not one of {list(allowed_choices)!r}"
        )
    if required_choice is not None and choice != required_choice:
        raise ValueError(
            f"operator answer choice {choice!r} does not satisfy required choice "
            f"{required_choice!r}"
        )
    if not isinstance(answer["raw_answer"], str) or not answer["raw_answer"].strip():
        raise ValueError("operator raw answer must be preserved as nonempty text")
    if not isinstance(answer["reason"], str) or not answer["reason"].strip():
        raise ValueError("operator answer interpretation requires a nonempty reason")
    return {
        **answer,
        "bound_question_sha256": hashlib.sha256(_canonical(question)).hexdigest(),
        "bound_claim_ids": list(claim_ids),
    }
