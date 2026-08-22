"""Admit assessed qualification answers to their exact missing-unit obligations."""

from __future__ import annotations


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
VERDICTS = {"resolves_obligation", "does_not_resolve_obligation"}


def _identity(binding: dict[str, object]) -> dict[str, object]:
    question = binding["question"]
    obligation = binding["obligation"]
    source = binding["answer_source"]
    projection = binding["answer_projection"]
    assert all(
        isinstance(item, dict)
        for item in (question, obligation, source, projection)
    )
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


def admit(binding: object, assessment: object) -> dict[str, object]:
    if not isinstance(binding, dict) or not isinstance(assessment, dict):
        return {
            "accepted": False,
            "why": (
                f"binding/assessment received {binding!r}/{assessment!r}; "
                "provide one exact assessed qualification answer"
            ),
        }
    try:
        expected = _identity(binding)
    except (AssertionError, KeyError, TypeError) as error:
        return {
            "accepted": False,
            "why": f"qualification binding received {binding!r}; provide its complete lineage ({error})",
        }
    issues = [
        f"{field} received {assessment.get(field)!r}; provide {value!r}"
        for field, value in expected.items()
        if assessment.get(field) != value
    ]
    verdict = assessment.get("verdict")
    if verdict not in VERDICTS:
        issues.append(
            f"verdict received {verdict!r}; provide one declared assessment verdict"
        )
    reason = assessment.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        issues.append(
            f"reason received {reason!r}; provide the preserved assessment reason"
        )
    if issues:
        return {"accepted": False, "why": "; ".join(issues)}
    return {
        "accepted": True,
        "route": (
            "resolution_admitted"
            if verdict == "resolves_obligation"
            else "follow_up_required"
        ),
        **expected,
        "verdict": verdict,
        "reason": reason,
    }


def admit_all(bindings: object, assessments: object) -> dict[str, object]:
    if (
        not isinstance(bindings, list)
        or not bindings
        or not isinstance(assessments, list)
        or len(bindings) != len(assessments)
    ):
        return {
            "complete": False,
            "why": (
                f"binding/assessment counts received {bindings!r}/{assessments!r}; "
                "provide one assessment for every qualification binding"
            ),
        }
    outcomes = [
        admit(binding, assessment)
        for binding, assessment in zip(bindings, assessments, strict=True)
    ]
    refused = [item for item in outcomes if item.get("accepted") is not True]
    if refused:
        return {
            "complete": False,
            "why": "; ".join(str(item.get("why")) for item in refused),
        }
    resolutions = [
        item for item in outcomes if item.get("route") == "resolution_admitted"
    ]
    follow_ups = [
        item for item in outcomes if item.get("route") == "follow_up_required"
    ]
    return {
        "complete": True,
        "resolution_count": len(resolutions),
        "follow_up_count": len(follow_ups),
        "resolutions": resolutions,
        "follow_ups": follow_ups,
    }
