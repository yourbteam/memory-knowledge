from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/info-intake-machinery/scripts"
LIVE = Path(
    "/Users/kamenkamenov/InfoIntakes/operator-dashboard-formula-map-2026-08-22"
)


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


def _answer(question_id: str, choice: str = "confirmed_ah_mapping") -> dict[str, str]:
    return {
        "question_id": question_id,
        "raw_answer": "Yes, that is what it means",
        "choice": choice,
        "reason": (
            "The operator explicitly confirmed the proposed Column AH / "
            "row.UniqueVisitors mapping."
        ),
    }


def _live_fixture(tmp_path: Path) -> Path:
    if not (LIVE / "formula-map/terminal-formula-map.json").is_file():
        pytest.skip("captured live formula map is unavailable")
    work = tmp_path / "intake"
    (work / "formula-map").mkdir(parents=True)
    (work / "sources").mkdir()
    for name in (
        "terminal-formula-map.json",
        "operator-questions.json",
        "reporting-v3-column-index.json",
    ):
        shutil.copy2(LIVE / "formula-map" / name, work / "formula-map" / name)
    ledger_lines = (LIVE / "formula-map/ledger.jsonl").read_text().splitlines()
    assert len(ledger_lines) >= 7
    (work / "formula-map/ledger.jsonl").write_text("\n".join(ledger_lines[:7]) + "\n")
    shutil.copy2(LIVE / "sources/source-000010", work / "sources/source-000010")
    return work


def test_answer_binding_requires_exact_question_and_enum() -> None:
    module = _module("formula_operator_answer_binding")
    question = {
        "id": "q1",
        "claim_ids": ["a", "b"],
        "question": "Does guest count mean AH?",
        "reason": "The source identity is missing.",
    }
    bound = module.bind_answer(
        question,
        _answer("q1"),
        ("confirmed_ah_mapping", "rejected_ah_mapping", "needs_clarification"),
        "confirmed_ah_mapping",
    )

    assert bound["raw_answer"] == "Yes, that is what it means"
    assert bound["bound_claim_ids"] == ["a", "b"]
    assert len(bound["bound_question_sha256"]) == 64
    with pytest.raises(ValueError, match="not one of"):
        module.bind_answer(question, _answer("q1", "maybe"), ("yes", "no"))


def test_live_ah_evidence_captures_complete_assignment() -> None:
    module = _module("reporting_v3_column_calculation_evidence")
    if not (LIVE / "sources/source-000010").is_file():
        pytest.skip("captured live Reporting V3 source is unavailable")
    index = json.loads((LIVE / "formula-map/reporting-v3-column-index.json").read_text())
    evidence = module.capture_column_evidence(
        index,
        (LIVE / "sources/source-000010").read_text(),
        excel_column="AH",
        expected_header="Sessions with Visitor Info Collected",
        expected_root="row.UniqueVisitors",
    )

    assert evidence["column_record"]["writer"]["expression"] == "row.UniqueVisitors"
    assert evidence["provenance_spans"] == [
        {
            "kind": "row_mutation",
            "start_line": 1342,
            "end_line": 1347,
            "source": (
                "row.UniqueVisitors = tourGroup "
                ".SelectMany(x => imageToUsers.TryGetValue(x.ProductImageId, out var users) "
                "? users : Enumerable.Empty<long>()) "
                ".Where(uid => validVisitorIds.Contains(uid)) .Distinct() .Count();"
            ),
        }
    ]


def test_live_publish_creates_append_only_complete_successor(tmp_path: Path) -> None:
    module = _module("formula_clarification_publish")
    work = _live_fixture(tmp_path)
    original_terminal = (work / "formula-map/terminal-formula-map.json").read_bytes()
    original_questions = (work / "formula-map/operator-questions.json").read_bytes()
    question = json.loads(original_questions)["questions"][0]
    answer_path = tmp_path / "answer.json"
    answer_path.write_text(json.dumps(_answer(question["id"])))

    first = module.publish(work, answer_path)
    second = module.publish(work, answer_path)
    successor = json.loads(
        (work / "formula-map/terminal-formula-map-v2.json").read_text()
    )
    questions = json.loads((work / "formula-map/operator-questions-v2.json").read_text())
    entries = module._validate_formula_ledger(work / "formula-map/ledger.jsonl")

    assert first == second
    assert successor["verdict_counts"] == {
        "confirmed": 27,
        "contradicted": 0,
        "unresolved": 0,
    }
    assert successor["resolution"]["resolved_claim_ids"] == question["claim_ids"]
    assert questions["status"] == "complete"
    assert questions["questions"] == []
    assert len(entries) == 10
    assert [entry["event"] for entry in entries[-3:]] == [
        "operator_clarification_answer_recorded",
        "reporting_v3_guest_count_evidence_recorded",
        "successor_terminal_formula_map_recorded",
    ]
    assert (work / "formula-map/terminal-formula-map.json").read_bytes() == original_terminal
    assert (work / "formula-map/operator-questions.json").read_bytes() == original_questions


def test_publish_refuses_an_uncontrolled_answer(tmp_path: Path) -> None:
    module = _module("formula_clarification_publish")
    work = _live_fixture(tmp_path)
    question = json.loads(
        (work / "formula-map/operator-questions.json").read_text()
    )["questions"][0]
    answer_path = tmp_path / "answer.json"
    answer_path.write_text(json.dumps(_answer(question["id"], "maybe")))

    with pytest.raises(ValueError, match="not one of"):
        module.publish(work, answer_path)
    assert not (work / "formula-map/operator-answer-000001.json").exists()
    assert len(module._validate_formula_ledger(work / "formula-map/ledger.jsonl")) == 7
