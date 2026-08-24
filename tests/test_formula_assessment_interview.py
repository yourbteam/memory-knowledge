from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/info-intake-machinery/scripts"


def _module(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def _packet() -> dict[str, object]:
    return {
        "packet_sha256": "a" * 64,
        "claim": {
            "id": "claim-000001",
            "statement": "Column AF is the displayed metric.",
            "origin": {"content": "Column AF"},
            "target": {"content": "$8,100"},
            "relationship_id": "relationship-000001",
            "relationship_sha256": "b" * 64,
        },
        "column_evidence": [
            {
                "excel_column": "AF",
                "root": "netOperatorPayout",
                "writer_line_number": 10,
                "column_record_sha256": "c" * 64,
                "provenance_spans": [
                    {"kind": "local_definition", "start_line": 5, "end_line": 5}
                ],
            }
        ],
    }


def test_question_is_one_packet_with_exact_enum_and_evidence() -> None:
    module = _module("formula_assessment_question")

    question = module.render_question([_packet()], 0)

    assert question["question_id"] == "assessment-000001"
    assert question["allowed_verdicts"] == [
        "confirmed", "contradicted", "unresolved"
    ]
    assert [item["id"] for item in question["evidence_catalog"]] == [
        "claim", "origin", "target", "relationship",
        "column:AF:writer", "column:AF:provenance:1",
    ]
    with pytest.raises(ValueError, match="outside"):
        module.render_question([_packet()], -1)


def test_answer_admission_enforces_active_identity_enum_and_evidence() -> None:
    questions = _module("formula_assessment_question")
    answers = _module("formula_assessment_answer")
    question = questions.render_question([_packet()], 0)
    response = {
        "question_id": question["question_id"],
        "claim_id": question["claim_id"],
        "packet_sha256": question["packet_sha256"],
        "verdict": "confirmed",
        "reason": "The writer and definition support it.",
        "evidence_pointers": ["column:AF:writer", "column:AF:provenance:1"],
    }

    assert answers.admit_answer(question, response)["verdict"] == "confirmed"
    bad = dict(response, verdict="maybe")
    with pytest.raises(ValueError, match="not one of"):
        answers.admit_answer(question, bad)
    bad = dict(response, evidence_pointers=["invented"])
    with pytest.raises(ValueError, match="not presented"):
        answers.admit_answer(question, bad)


def test_live_questions_render_all_27_in_order() -> None:
    module = _module("formula_assessment_question")
    path = Path(
        "/Users/kamenkamenov/InfoIntakes/operator-dashboard-formula-map-2026-08-22/"
        "formula-map/assessment-packets.json"
    )
    if not path.is_file():
        pytest.skip("captured live assessment packets are unavailable")
    import json

    packets = json.loads(path.read_text())["packets"]
    questions = [module.render_question(packets, index) for index in range(len(packets))]

    assert len(questions) == 27
    assert [question["claim_id"] for question in questions] == [
        f"claim-{number:06d}" for number in range(1, 28)
    ]
    assert all(question["allowed_verdicts"] == ["confirmed", "contradicted", "unresolved"] for question in questions)
