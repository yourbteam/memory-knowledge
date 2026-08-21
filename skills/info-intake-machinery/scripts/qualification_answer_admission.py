"""Deterministically admit one answer to the active qualification question."""

from __future__ import annotations


ALLOWED_CHANNELS = {"operator_text", "local_file", "url"}


def admit(
    question: object,
    *,
    channel: object,
    value: object,
) -> dict[str, object]:
    if not isinstance(question, dict):
        return {
            "accepted": False,
            "why": (f"active question received {question!r}; provide the exact prepared qualification question"),
        }
    question_id = question.get("id")
    expected = question.get("answer_type")
    obligation = question.get("answers_obligation")
    evidence_sha256 = question.get("evidence_sha256")
    issues: list[str] = []
    if not isinstance(question_id, str) or not question_id:
        issues.append(f"question id received {question_id!r}; provide one nonempty prepared id")
    if expected not in ALLOWED_CHANNELS:
        issues.append(
            f"question {question_id!r} answer type received {expected!r}; provide "
            "exactly operator_text, local_file, or url"
        )
    if not isinstance(obligation, dict) or not isinstance(obligation.get("id"), str):
        issues.append(
            f"question {question_id!r} obligation received {obligation!r}; provide the exact evidence-bound obligation"
        )
    if not isinstance(evidence_sha256, str) or len(evidence_sha256) != 64:
        issues.append(
            f"question {question_id!r} evidence digest received {evidence_sha256!r}; "
            "provide the exact 64-character evidence digest"
        )
    if channel != expected:
        issues.append(f"question {question_id!r} channel received {channel!r}; provide exactly {expected!r}")
    if not isinstance(value, str) or not value.strip():
        issues.append(f"question {question_id!r} value received {value!r}; provide one nonempty {expected!r} answer")
    if expected == "url" and isinstance(value, str) and value.strip() and not value.startswith(("http://", "https://")):
        issues.append(f"question {question_id!r} URL received {value!r}; provide one public HTTP(S) URL")
    if issues:
        return {"accepted": False, "why": "; ".join(issues)}
    assert isinstance(question_id, str)
    assert isinstance(expected, str)
    assert isinstance(value, str)
    assert isinstance(obligation, dict)
    assert isinstance(evidence_sha256, str)
    return {
        "accepted": True,
        "question_id": question_id,
        "obligation_id": obligation["id"],
        "evidence_sha256": evidence_sha256,
        "channel": expected,
        "value": value,
    }
