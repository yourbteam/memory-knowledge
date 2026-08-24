"""Code-own the operator disposition for one qualification obligation."""

from __future__ import annotations


ACTIONS = ("provide_answer", "preserve_gap")


def prepare(question: object) -> dict[str, object]:
    if not isinstance(question, dict):
        return {
            "prepared": False,
            "why": f"qualification question received {question!r}; provide its exact object",
        }
    question_id = question.get("id")
    obligation = question.get("answers_obligation")
    evidence_sha256 = question.get("evidence_sha256")
    if (
        not isinstance(question_id, str)
        or not question_id.startswith("qualification-clarification-answer-")
        or not isinstance(obligation, dict)
        or not isinstance(obligation.get("id"), str)
        or not isinstance(evidence_sha256, str)
        or len(evidence_sha256) != 64
    ):
        return {
            "prepared": False,
            "why": (
                f"qualification question identity received {question!r}; preserve its exact "
                "question, obligation, and evidence digest"
            ),
        }
    return {
        "prepared": True,
        "question": {
            "id": f"{question_id}-disposition",
            "asks": "Do you want to provide the requested information or preserve it as an unresolved gap?",
            "answer_type": "enum",
            "allowed_values": list(ACTIONS),
            "qualification_question_id": question_id,
            "obligation_id": obligation["id"],
            "evidence_sha256": evidence_sha256,
        },
    }


def admit(question: object, action: object) -> dict[str, object]:
    prepared = prepare(question)
    if prepared.get("prepared") is not True:
        return prepared
    if action not in ACTIONS:
        return {
            "accepted": False,
            "why": (
                f"qualification disposition received {action!r}; choose exactly "
                + ", ".join(ACTIONS)
            ),
        }
    assert isinstance(question, dict)
    obligation = question["answers_obligation"]
    assert isinstance(obligation, dict)
    return {
        "accepted": True,
        "action": action,
        "question_id": question["id"],
        "obligation_id": obligation["id"],
        "evidence_sha256": question["evidence_sha256"],
    }
