"""Bind one admitted qualification answer to immutable source evidence."""

from __future__ import annotations


def preserve(
    admitted: object,
    question: object,
    source: object,
    projection: object,
) -> dict[str, object]:
    if not all(isinstance(item, dict) for item in (admitted, question, source, projection)):
        return {
            "preserved": False,
            "why": (
                "answer evidence received a non-object value; provide the admitted answer, "
                "active question, frozen source, and readable projection"
            ),
        }
    assert isinstance(admitted, dict)
    assert isinstance(question, dict)
    assert isinstance(source, dict)
    assert isinstance(projection, dict)
    obligation = question.get("answers_obligation")
    source_id = source.get("id")
    source_sha256 = source.get("sha256")
    expected_projection_id = f"projection-{source_id}-v1"
    issues: list[str] = []
    if (
        admitted.get("question_id") != question.get("id")
        or not isinstance(obligation, dict)
        or admitted.get("obligation_id") != obligation.get("id")
        or admitted.get("evidence_sha256") != question.get("evidence_sha256")
    ):
        issues.append(
            f"answer binding received {admitted!r}; provide the exact active question, obligation, and evidence digest"
        )
    if (
        not isinstance(source_id, str)
        or not isinstance(source_sha256, str)
        or len(source_sha256) != 64
        or source.get("answers_question") != question.get("id")
        or source.get("answers_obligation") != obligation
    ):
        issues.append(
            f"frozen source received {source!r}; provide one immutable source bound to "
            "the exact question and obligation"
        )
    if (
        projection.get("id") != expected_projection_id
        or projection.get("source_id") != source_id
        or not isinstance(projection.get("sha256"), str)
        or len(str(projection.get("sha256"))) != 64
        or not isinstance(projection.get("path"), str)
    ):
        issues.append(
            f"source {source_id!r} projection received {projection!r}; provide "
            f"{expected_projection_id!r} bound to the exact source"
        )
    if issues:
        return {"preserved": False, "why": "; ".join(issues)}
    assert isinstance(obligation, dict)
    return {
        "preserved": True,
        "answer_kind": "qualification_clarification_answer",
        "question": question,
        "submission": {
            "channel": admitted["channel"],
            "value": admitted["value"],
        },
        "source": source,
        "projection": projection,
        "question_id": question["id"],
        "obligation_id": obligation["id"],
        "question_evidence_sha256": question["evidence_sha256"],
    }
