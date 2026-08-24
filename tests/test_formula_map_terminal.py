from __future__ import annotations

import importlib.util
import json
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


def test_question_plan_covers_all_and_only_unresolved_once() -> None:
    module = _module("formula_operator_question_plan")
    answers = [
        {"claim_id": "a", "verdict": "confirmed"},
        {"claim_id": "b", "verdict": "unresolved"},
        {"claim_id": "c", "verdict": "unresolved"},
    ]
    plan = {
        "schema_version": 1,
        "questions": [
            {"id": "q1", "claim_ids": ["b", "c"], "question": "Source?", "reason": "Missing."}
        ],
    }

    assert module.admit_plan(answers, plan) == plan
    bad = json.loads(json.dumps(plan))
    bad["questions"][0]["claim_ids"].append("a")
    with pytest.raises(ValueError, match="unknown=.*a"):
        module.admit_plan(answers, bad)


def test_live_terminal_replay_has_27_answers_and_expected_counts() -> None:
    module = _module("formula_terminal_replay")
    root = Path(
        "/Users/kamenkamenov/InfoIntakes/operator-dashboard-formula-map-2026-08-22/"
        "formula-map"
    )
    journal = root / "assessment-interview-v2-ledger.jsonl"
    if not journal.is_file():
        pytest.skip("captured live assessment journal is unavailable")
    packets_bytes = (root / "assessment-packets.json").read_bytes()
    context_bytes = (root / "assessment-shared-context.json").read_bytes()
    packets = json.loads(packets_bytes)["packets"]
    context = json.loads(context_bytes)["shared_code_evidence"]
    import hashlib

    answers, entries = module.replay(
        packets,
        context,
        journal,
        hashlib.sha256(packets_bytes).hexdigest(),
        hashlib.sha256(context_bytes).hexdigest(),
    )

    assert len(answers) == 27
    assert sum(answer["verdict"] == "confirmed" for answer in answers) == 23
    assert sum(answer["verdict"] == "unresolved" for answer in answers) == 4
    assert len(entries) == 55
