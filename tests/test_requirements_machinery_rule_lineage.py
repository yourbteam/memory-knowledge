"""Focused proof for chained merge conservation before checkability."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skills" / "requirements-machinery" / "scripts"
REAL_STEP7 = Path(
    "/Users/kamenkamenov/united-partners/Tasks/intake-to-requirements-machinery/"
    "runs/step7-message-architecture-run/coverage.json"
)


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_chained_merge_transfers_every_source_identity_and_wording() -> None:
    lineage = load("rule_lineage")
    source = [
        {"text": "six message types", "pages": ["p1"], "source_rule_ids": [1]},
        {"text": "all messages use six types", "pages": ["p2"], "source_rule_ids": [2]},
        {"text": "messages use exactly six types", "pages": ["p3"], "source_rule_ids": [3]},
    ]

    result = lineage.reduce(source, [(1, 2), (2, 3)])

    assert len(result["items"]) == 1
    terminal = result["items"][0]
    assert terminal["source_rule_ids"] == [1, 2, 3]
    assert set([terminal["text"], *terminal["also_stated_as"]]) == {
        item["text"] for item in source
    }
    assert terminal["pages"] == ["p1", "p2", "p3"]


def test_branched_merge_stays_explicit_for_owner_instead_of_overmerging() -> None:
    lineage = load("rule_lineage")
    source = [
        {"text": "short shared wording", "pages": ["p1"], "source_rule_ids": [1]},
        {"text": "first longer shared wording", "pages": ["p2"], "source_rule_ids": [2]},
        {"text": "second longer shared wording", "pages": ["p3"], "source_rule_ids": [3]},
    ]

    result = lineage.reduce(source, [(1, 2), (1, 3)])

    assert result["ambiguous"] == [
        {"source_rule_id": 1, "possible_terminal_rule_ids": [2, 3]}
    ]
    assert {(item["text"], tuple(item["source_rule_ids"])) for item in result["items"]} == {
        (source[0]["text"], (1,)),
        (source[1]["text"], (2,)),
        (source[2]["text"], (3,)),
    }
    assert (1, 2) in result["owner_pairs"] and (1, 3) in result["owner_pairs"]


def test_conservation_names_loss_duplication_and_unknown_identity() -> None:
    conservation = load("rule_conservation")

    result = conservation.check(3, [{"source_rule_ids": [1, 1]}, {"source_rule_ids": [4]}])

    assert result == {
        "source_count": 3,
        "terminal_count": 2,
        "represented_count": 3,
        "missing": [2, 3],
        "duplicates": [1],
        "unknown": [4],
        "valid": False,
    }


def test_real_step7_chain_is_complete_without_ambiguous_automerge() -> None:
    lineage = load("rule_lineage")
    conservation = load("rule_conservation")
    state = json.loads(REAL_STEP7.read_text(encoding="utf-8"))
    requirement = next(iter(state["requirements"].values()))
    rules = [
        {"text": rule["text"], "pages": [], "kind": "rule", "source_rule_ids": [number]}
        for number, rule in enumerate(requirement["rules_stage"]["rules"], 1)
    ]

    reduction = lineage.reduce(rules, requirement["rule_judgement"]["merged"])
    proof = conservation.check(len(rules), reduction["items"])

    assert proof["valid"] is True
    assert proof["represented_count"] == 35
    six_type_terminal = [
        item for item in reduction["items"] if {11, 27} <= set(item["source_rule_ids"])
    ]
    assert len(six_type_terminal) == 1
    wordings = {six_type_terminal[0]["text"], *six_type_terminal[0].get("also_stated_as", [])}
    assert requirement["rules_stage"]["rules"][10]["text"] in wordings
    assert requirement["rules_stage"]["rules"][26]["text"] in wordings
    for ambiguity in reduction["ambiguous"]:
        source_id = ambiguity["source_rule_id"]
        assert any(item["text"] == rules[source_id - 1]["text"] for item in reduction["items"])


def test_historical_step7_output_is_refused_before_checkability() -> None:
    conservation = load("rule_conservation")
    state = json.loads(REAL_STEP7.read_text(encoding="utf-8"))
    requirement = next(iter(state["requirements"].values()))

    proof = conservation.check(len(requirement["rules_stage"]["rules"]), requirement["items"])

    assert proof["valid"] is False
    assert 11 in proof["missing"]
    assert 27 in proof["missing"]
