"""Admit one model answer against the active formula assessment question."""

from __future__ import annotations


_FIELDS = {
    "question_id",
    "claim_id",
    "packet_sha256",
    "verdict",
    "reason",
    "evidence_pointers",
}


def admit_answer(
    question: dict[str, object], response: object
) -> dict[str, object]:
    if not isinstance(response, dict) or set(response) != _FIELDS:
        raise ValueError(
            "answer must contain exactly question_id, claim_id, packet_sha256, "
            "verdict, reason, and evidence_pointers"
        )
    for field in ("question_id", "claim_id", "packet_sha256"):
        if response[field] != question.get(field):
            raise ValueError(
                f"answer {field} {response[field]!r} differs from active question {question.get(field)!r}"
            )
    allowed = question.get("allowed_verdicts")
    if not isinstance(allowed, list) or response["verdict"] not in allowed:
        raise ValueError(
            f"answer verdict {response['verdict']!r} is not one of {allowed!r}"
        )
    if not isinstance(response["reason"], str) or not response["reason"].strip():
        raise ValueError("answer reason must be nonempty")
    pointers = response["evidence_pointers"]
    if not isinstance(pointers, list) or any(
        not isinstance(value, str) for value in pointers
    ):
        raise ValueError("answer evidence_pointers must be a string list")
    catalog = question.get("evidence_catalog")
    if not isinstance(catalog, list):
        raise ValueError("active question has no evidence catalog")
    allowed_pointers = {
        item["id"]
        for item in catalog
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    unknown = sorted(set(pointers) - allowed_pointers)
    if unknown:
        raise ValueError(
            f"answer cites evidence not presented for this question: {unknown}"
        )
    if len(pointers) != len(set(pointers)):
        raise ValueError("answer evidence_pointers contain duplicates")
    return {
        "question_id": response["question_id"],
        "claim_id": response["claim_id"],
        "packet_sha256": response["packet_sha256"],
        "verdict": response["verdict"],
        "reason": response["reason"].strip(),
        "evidence_pointers": pointers,
    }
