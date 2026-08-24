"""Build a predecessor-bound successor after one formula clarification."""

from __future__ import annotations

import copy
import hashlib
import json
import re


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def build_successor(
    terminal: object,
    questions: object,
    answer: object,
    evidence: object,
    *,
    required_choice: str,
    resolution_reason: str,
    predecessor_sha256: str | None = None,
    answer_sha256: str | None = None,
    evidence_sha256: str | None = None,
) -> dict[str, object]:
    if not isinstance(terminal, dict) or terminal.get("status") != "terminal":
        raise ValueError("predecessor terminal formula map is invalid")
    claims = terminal.get("claims")
    if not isinstance(claims, list) or terminal.get("claim_count") != len(claims):
        raise ValueError("predecessor terminal formula claims are incomplete")
    if (
        not isinstance(questions, dict)
        or questions.get("status") != "operator_input_required"
        or questions.get("question_count") != 1
        or not isinstance(questions.get("questions"), list)
        or len(questions["questions"]) != 1
    ):
        raise ValueError("predecessor operator question set must contain one active question")
    question = questions["questions"][0]
    unresolved = [
        claim.get("claim_id")
        for claim in claims
        if isinstance(claim, dict) and claim.get("verdict") == "unresolved"
    ]
    if question.get("claim_ids") != unresolved:
        raise ValueError(
            f"active question claim_ids {question.get('claim_ids')!r} differ from "
            f"unresolved claims {unresolved!r}"
        )
    if not isinstance(answer, dict):
        raise ValueError("bound operator answer must be an object")
    if (
        answer.get("question_id") != question.get("id")
        or answer.get("choice") != required_choice
        or answer.get("bound_claim_ids") != unresolved
        or answer.get("bound_question_sha256")
        != hashlib.sha256(_canonical(question)).hexdigest()
    ):
        raise ValueError("bound operator answer does not resolve the active question")
    if not isinstance(evidence, dict) or len(str(evidence.get("record_sha256", ""))) != 64:
        raise ValueError("clarification evidence is incomplete")
    if not isinstance(resolution_reason, str) or not resolution_reason.strip():
        raise ValueError("resolution reason must be nonempty text")

    result = copy.deepcopy(terminal)
    predecessor_sha256 = predecessor_sha256 or hashlib.sha256(
        _canonical(terminal)
    ).hexdigest()
    answer_sha256 = answer_sha256 or hashlib.sha256(_canonical(answer)).hexdigest()
    evidence_sha256 = evidence_sha256 or hashlib.sha256(_canonical(evidence)).hexdigest()
    for label, value in (
        ("predecessor", predecessor_sha256),
        ("operator answer", answer_sha256),
        ("calculation evidence", evidence_sha256),
    ):
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError(f"{label} artifact sha256 is invalid")
    affected = set(unresolved)
    for claim in result["claims"]:
        if claim["claim_id"] not in affected:
            continue
        if claim.get("verdict") != "unresolved":
            raise ValueError(f"affected claim {claim['claim_id']!r} is not unresolved")
        claim["verdict"] = "confirmed"
        claim["reason"] = resolution_reason
        claim["resolution_evidence"] = {
            "operator_answer_sha256": answer_sha256,
            "calculation_evidence_sha256": evidence_sha256,
        }
    result["schema_version"] = int(terminal.get("schema_version", 0)) + 1
    result["supersedes_terminal_map_sha256"] = predecessor_sha256
    result["resolution"] = {
        "question_id": question["id"],
        "operator_answer_sha256": answer_sha256,
        "calculation_evidence_sha256": evidence_sha256,
        "resolved_claim_ids": unresolved,
    }
    result["verdict_counts"] = {
        verdict: sum(claim.get("verdict") == verdict for claim in result["claims"])
        for verdict in ("confirmed", "contradicted", "unresolved")
    }
    if result["verdict_counts"]["unresolved"] != 0:
        raise ValueError(f"successor still has unresolved claims: {result['verdict_counts']!r}")
    return result
