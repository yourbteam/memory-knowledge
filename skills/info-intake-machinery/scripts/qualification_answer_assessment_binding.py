"""Bind preserved qualification answers to their exact immutable evidence."""

from __future__ import annotations

import hashlib
from pathlib import Path


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def bind(
    work: Path,
    questions: object,
    answers: object,
) -> dict[str, object]:
    if (
        not isinstance(questions, list)
        or not questions
        or any(not isinstance(item, dict) for item in questions)
        or not isinstance(answers, list)
        or any(not isinstance(item, dict) for item in answers)
    ):
        return {
            "complete": False,
            "why": (
                f"qualification questions/answers received {questions!r}/{answers!r}; "
                "provide one complete ordered prepared round"
            ),
        }
    if len(questions) != len(answers):
        return {
            "complete": False,
            "why": (
                f"qualification answer count received {len(answers)!r}; provide exactly {len(questions)!r} answers"
            ),
        }
    bindings: list[dict[str, object]] = []
    issues: list[str] = []
    for position, (question, answer) in enumerate(zip(questions, answers, strict=True), 1):
        assert isinstance(question, dict) and isinstance(answer, dict)
        obligation = question.get("answers_obligation")
        source = answer.get("source")
        projection = answer.get("projection")
        submission = answer.get("submission")
        if not all(isinstance(item, dict) for item in (obligation, source, projection)):
            issues.append(
                f"answer {position} evidence received {answer!r}; provide its exact obligation, source, and projection"
            )
            continue
        if (
            not isinstance(submission, dict)
            or submission.get("channel")
            not in {"operator_text", "local_file", "url", "preserve_gap"}
            or not isinstance(submission.get("value"), str)
            or not submission["value"].strip()
        ):
            issues.append(
                f"answer {position} submission received {submission!r}; preserve its exact admitted channel and value"
            )
            continue
        assert isinstance(obligation, dict)
        assert isinstance(source, dict)
        assert isinstance(projection, dict)
        if (
            answer.get("question") != question
            or answer.get("question_id") != question.get("id")
            or answer.get("obligation_id") != obligation.get("id")
            or answer.get("question_evidence_sha256") != question.get("evidence_sha256")
            or source.get("answers_question") != question.get("id")
            or source.get("answers_obligation") != obligation
            or projection.get("source_id") != source.get("id")
        ):
            issues.append(
                f"answer {position} obligation binding received {answer.get('question_id')!r}/{answer.get('obligation_id')!r}; provide the exact prepared question and obligation"
            )
            continue
        source_path_value = source.get("stored_path", source.get("path"))
        projection_path_value = projection.get("path")
        if not isinstance(source_path_value, str) or not isinstance(projection_path_value, str):
            issues.append(
                f"answer {position} artifact paths received {source_path_value!r}/{projection_path_value!r}; provide both immutable paths"
            )
            continue
        source_path = (work / source_path_value).resolve()
        projection_path = (work / projection_path_value).resolve()
        try:
            source_path.relative_to(work.resolve())
            projection_path.relative_to(work.resolve())
            source_bytes = source_path.read_bytes()
            projection_bytes = projection_path.read_bytes()
            readable_projection = projection_bytes.decode("utf-8")
        except (OSError, UnicodeError, ValueError) as error:
            issues.append(
                f"answer {position} readable evidence received {str(error)!r}; provide unchanged in-intake source and UTF-8 projection artifacts"
            )
            continue
        if source.get("sha256") != _digest(source_bytes):
            issues.append(
                f"answer {position} observed source digest received {_digest(source_bytes)!r}; provide the exact immutable source bytes matching {source.get('sha256')!r}"
            )
        if projection.get("sha256") != _digest(projection_bytes):
            issues.append(
                f"answer {position} observed projection digest received {_digest(projection_bytes)!r}; provide the exact readable projection bytes matching {projection.get('sha256')!r}"
            )
        bindings.append(
            {
                "position": position,
                "question": question,
                "obligation": obligation,
                "answer_source": {
                    "id": source["id"],
                    "path": source_path_value,
                    "sha256": source["sha256"],
                },
                "answer_projection": {
                    "id": projection["id"],
                    "source_id": projection["source_id"],
                    "path": projection_path_value,
                    "sha256": projection["sha256"],
                },
                "submission": submission,
                "readable_projection": readable_projection,
            }
        )
    if issues:
        return {"complete": False, "why": "; ".join(issues)}
    return {"complete": True, "bindings": bindings}
