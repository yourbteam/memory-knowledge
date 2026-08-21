"""Advance an ordered qualification interview by exactly one preserved answer."""

from __future__ import annotations


def advance(
    questions: object,
    answers: object,
    question: object,
    preserved: object,
) -> dict[str, object]:
    if (
        not isinstance(questions, list)
        or not questions
        or any(not isinstance(item, dict) for item in questions)
        or len({item.get("id") for item in questions if isinstance(item, dict)}) != len(questions)
    ):
        return {
            "advanced": False,
            "why": (f"question set received {questions!r}; provide one nonempty ordered set with unique prepared ids"),
        }
    if not isinstance(answers, list) or any(not isinstance(item, dict) for item in answers):
        return {
            "advanced": False,
            "why": (f"preserved answers received {answers!r}; provide the exact ordered append-only answer list"),
        }
    position = len(answers) + 1
    expected = questions[position - 1] if position <= len(questions) else None
    if not isinstance(question, dict) or expected != question:
        return {
            "advanced": False,
            "why": (
                f"current question received position {position!r}/{question!r}; provide "
                f"the exact next prepared question {expected!r}"
            ),
        }
    if not isinstance(preserved, dict) or preserved.get("preserved") is not True:
        return {
            "advanced": False,
            "why": (
                f"answer evidence received {preserved!r}; provide one successfully "
                "preserved answer for the active question"
            ),
        }
    if preserved.get("question_id") != question.get("id") or preserved.get("obligation_id") != question.get(
        "answers_obligation", {}
    ).get("id"):
        return {
            "advanced": False,
            "why": (
                f"answer binding received {preserved.get('question_id')!r}/"
                f"{preserved.get('obligation_id')!r}; provide the exact current "
                "question and obligation"
            ),
        }
    if any(item.get("question_id") == question.get("id") for item in answers):
        return {
            "advanced": False,
            "why": (
                f"question {question.get('id')!r} received a duplicate answer; provide "
                "no second answer for an already preserved question"
            ),
        }
    source = preserved.get("source")
    source_id = source.get("id") if isinstance(source, dict) else None
    if any(isinstance(item.get("source"), dict) and item["source"].get("id") == source_id for item in answers):
        return {
            "advanced": False,
            "why": (f"source id received {source_id!r} twice; provide one unused answer source identity"),
        }
    updated = [*answers, preserved]
    next_question = questions[len(updated)] if len(updated) < len(questions) else None
    return {
        "advanced": True,
        "question_position": position,
        "answers": updated,
        "next_question": next_question,
        "complete": next_question is None,
    }
