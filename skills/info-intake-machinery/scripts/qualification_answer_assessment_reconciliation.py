"""Reconcile one exact assessment for every qualification answer binding."""

from __future__ import annotations


VERDICTS = {"resolves_obligation", "does_not_resolve_obligation"}
IDENTITY_FIELDS = (
    "position",
    "question_id",
    "obligation_id",
    "evidence_sha256",
    "answer_source_id",
    "answer_source_sha256",
    "answer_projection_id",
    "answer_projection_sha256",
)


def _identity(binding: dict[str, object]) -> dict[str, object]:
    question = binding["question"]
    obligation = binding["obligation"]
    source = binding["answer_source"]
    projection = binding["answer_projection"]
    assert all(isinstance(item, dict) for item in (question, obligation, source, projection))
    return {
        "position": binding["position"],
        "question_id": question["id"],
        "obligation_id": obligation["id"],
        "evidence_sha256": question["evidence_sha256"],
        "answer_source_id": source["id"],
        "answer_source_sha256": source["sha256"],
        "answer_projection_id": projection["id"],
        "answer_projection_sha256": projection["sha256"],
    }


def reconcile(bindings: object, assessments: object) -> dict[str, object]:
    if (
        not isinstance(bindings, list)
        or not bindings
        or any(not isinstance(item, dict) for item in bindings)
        or not isinstance(assessments, list)
        or any(not isinstance(item, dict) for item in assessments)
    ):
        return {
            "complete": False,
            "why": (
                f"qualification bindings/assessments received {bindings!r}/{assessments!r}; provide two ordered object lists"
            ),
        }
    expected = {int(item["position"]): _identity(item) for item in bindings}
    counts: dict[object, int] = {}
    for assessment in assessments:
        position = assessment.get("position")
        counts[position] = counts.get(position, 0) + 1
    duplicate = sorted(position for position, count in counts.items() if isinstance(position, int) and count > 1)
    missing = sorted(position for position in expected if counts.get(position, 0) == 0)
    unknown = sorted(position for position in counts if isinstance(position, int) and position not in expected)
    issues: list[str] = []
    if duplicate:
        issues.append(
            f"duplicate assessment positions received {duplicate!r}; provide exactly one assessment per answer"
        )
    if missing:
        issues.append(f"missing assessment positions received {missing!r}; provide every prepared answer assessment")
    if unknown:
        issues.append(f"unknown assessment positions received {unknown!r}; provide only {sorted(expected)!r}")
    by_position = {int(item["position"]): item for item in assessments if isinstance(item.get("position"), int)}
    ordered: list[dict[str, object]] = []
    for position, identity in expected.items():
        assessment = by_position.get(position)
        if assessment is None:
            continue
        for field in IDENTITY_FIELDS:
            if assessment.get(field) != identity[field]:
                issues.append(
                    f"assessment {position} {field} received {assessment.get(field)!r}; provide {identity[field]!r}"
                )
        verdict = assessment.get("verdict")
        reason = assessment.get("reason")
        if verdict not in VERDICTS:
            issues.append(f"assessment {position} verdict received {verdict!r}; provide one declared verdict")
        if not isinstance(reason, str) or not reason.strip():
            issues.append(f"assessment {position} reason received {reason!r}; provide one nonempty reason")
        ordered.append(assessment)
    if issues:
        return {"complete": False, "why": "; ".join(issues)}
    resolving_count = sum(item["verdict"] == "resolves_obligation" for item in ordered)
    return {
        "complete": True,
        "route": ("ready_for_qualification_admission" if resolving_count else "ready_for_qualification_follow_up"),
        "assessment_count": len(ordered),
        "resolving_count": resolving_count,
        "nonresolving_count": len(ordered) - resolving_count,
        "assessments": ordered,
    }
