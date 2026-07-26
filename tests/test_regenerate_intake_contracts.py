"""Tests for the intake-contract regeneration entry point.

The dispatch gate refuses every sequence once the shared adapter changes, and the handoff
documents regenerating the binding as the way through. That step had no implementation:
`build_intake_contracts` was reachable only from `check_intake_contracts` and the tests,
so extending the adapter was a dead end for any operator.

These tests hold the two halves that make regeneration safe rather than a bypass: benign
drift (new entries, plus existing entries re-hashed because they all carry the shared
adapter's sha) is classified as benign, and a changed caller interface is not.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "regenerate_intake_contracts", ROOT / "scripts" / "regenerate_intake_contracts.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

import sequence_intake_adapters  # noqa: E402


def _stored() -> dict:
    path = ROOT / sequence_intake_adapters.INTAKE_CONTRACTS_PATH
    return json.loads(path.read_text(encoding="utf-8"))


def test_committed_binding_is_current():
    assert sequence_intake_adapters.check_intake_contracts(ROOT) == []


def test_a_new_sequence_alone_is_benign_drift():
    stored = _stored()
    rebuilt = copy.deepcopy(stored)
    without_new = [row for row in stored["entries"] if row["sequence_id"] != "x-new"]
    stored["entries"] = without_new
    rebuilt["entries"] = without_new + [
        {**without_new[0], "sequence_id": "x-new"}
    ]

    added, interface_changes = MODULE._classify(stored, rebuilt)

    assert added == ["x-new"]
    assert interface_changes == {}


def test_shared_adapter_rehash_alone_is_benign_drift():
    stored = _stored()
    rebuilt = copy.deepcopy(stored)
    rebuilt["adapter_source_sha256"] = "0" * 64
    for row in rebuilt["entries"]:
        row["adapter_source_sha256"] = "0" * 64

    added, interface_changes = MODULE._classify(stored, rebuilt)

    # Every entry carries the shared adapter's hash, so editing that one file re-hashes
    # all of them. That must not read as 29 interface changes.
    assert added == []
    assert interface_changes == {}


def test_changed_caller_interface_is_not_benign():
    stored = _stored()
    rebuilt = copy.deepcopy(stored)
    target = next(row for row in rebuilt["entries"] if row["required_inputs"])
    target["required_inputs"] = target["required_inputs"][1:]

    _, interface_changes = MODULE._classify(stored, rebuilt)

    assert interface_changes[target["sequence_id"]] == ["required_inputs"]


def test_sequence_dropped_from_the_registry_is_not_benign():
    stored = _stored()
    rebuilt = copy.deepcopy(stored)
    gone = rebuilt["entries"].pop(0)["sequence_id"]

    _, interface_changes = MODULE._classify(stored, rebuilt)

    assert interface_changes[gone] == ["removed-from-registry"]


def test_changed_non_runnable_set_is_not_benign():
    stored = _stored()
    rebuilt = copy.deepcopy(stored)
    rebuilt["non_runnable"] = list(rebuilt["non_runnable"]) + [
        {"sequence_id": "x-composed", "reason": "composition only"}
    ]

    _, interface_changes = MODULE._classify(stored, rebuilt)

    assert interface_changes["<non-runnable-set>"] == ["non_runnable"]


def test_report_mode_reports_without_writing(capsys, monkeypatch):
    path = ROOT / sequence_intake_adapters.INTAKE_CONTRACTS_PATH
    before = path.read_bytes()
    rebuilt = sequence_intake_adapters.build_intake_contracts(ROOT)
    drifted = copy.deepcopy(rebuilt)
    drifted["entries"] = drifted["entries"][1:]
    monkeypatch.setattr(MODULE.json, "loads", lambda _text: drifted)

    status = MODULE.main([])

    assert status == 1
    assert "report only" in capsys.readouterr().out
    assert path.read_bytes() == before


def test_write_refuses_an_unacknowledged_interface_change(capsys, monkeypatch):
    path = ROOT / sequence_intake_adapters.INTAKE_CONTRACTS_PATH
    before = path.read_bytes()
    rebuilt = sequence_intake_adapters.build_intake_contracts(ROOT)
    drifted = copy.deepcopy(rebuilt)
    target = next(row for row in drifted["entries"] if row["required_inputs"])
    target["required_inputs"] = target["required_inputs"] + ["invented_input"]
    monkeypatch.setattr(MODULE.json, "loads", lambda _text: drifted)

    status = MODULE.main(["--write"])

    assert status == 3
    assert "refusing to write" in capsys.readouterr().err
    # The gate exists so an adapter edit cannot silently rewrite another sequence's
    # caller interface. Refusing must leave the committed binding untouched.
    assert path.read_bytes() == before
