"""Admit operator questions covering all and only unresolved formula claims."""

from __future__ import annotations


def admit_plan(
    answers: list[dict[str, object]], plan: object
) -> dict[str, object]:
    if (
        not isinstance(plan, dict)
        or set(plan) != {"schema_version", "questions"}
        or plan.get("schema_version") != 1
        or not isinstance(plan.get("questions"), list)
    ):
        raise ValueError("operator question plan has invalid exact shape")
    unresolved = {
        str(answer["claim_id"])
        for answer in answers
        if answer.get("verdict") == "unresolved"
    }
    questions = plan["questions"]
    assert isinstance(questions, list)
    seen: list[str] = []
    ids: set[str] = set()
    for position, question in enumerate(questions):
        if not isinstance(question, dict) or set(question) != {
            "id", "claim_ids", "question", "reason"
        }:
            raise ValueError(f"operator question {position} has invalid exact shape")
        identity = question["id"]
        if not isinstance(identity, str) or not identity or identity in ids:
            raise ValueError(f"operator question {position} has invalid or duplicate id")
        ids.add(identity)
        if not isinstance(question["question"], str) or not question["question"].strip():
            raise ValueError(f"operator question {position} has no question text")
        if not isinstance(question["reason"], str) or not question["reason"].strip():
            raise ValueError(f"operator question {position} has no reason")
        claim_ids = question["claim_ids"]
        if not isinstance(claim_ids, list) or not claim_ids or any(
            not isinstance(value, str) for value in claim_ids
        ):
            raise ValueError(f"operator question {position} has invalid claim_ids")
        seen.extend(claim_ids)
    duplicates = sorted({value for value in seen if seen.count(value) > 1})
    missing = sorted(unresolved - set(seen))
    unknown = sorted(set(seen) - unresolved)
    if duplicates or missing or unknown:
        raise ValueError(
            f"unresolved coverage differs: missing={missing}, duplicate={duplicates}, unknown={unknown}"
        )
    if bool(unresolved) != bool(questions):
        raise ValueError("operator question presence differs from unresolved claims")
    return plan
