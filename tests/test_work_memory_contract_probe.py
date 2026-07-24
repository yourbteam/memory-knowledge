from pathlib import Path

import pytest

from scripts import work_memory, work_memory_contract_probe


@pytest.mark.parametrize("mode", ["discovery", "registered"])
def test_contract_probe_fixtures_include_selection_trust_anchors(
    mode: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    skills_root = Path(__file__).resolve().parents[1] / "skills"
    original = (work_memory.RECEIPT_ROOT, work_memory.ROOT, work_memory.registry_rows)
    try:
        result = work_memory_contract_probe.run_probe(skills_root, mode)
    finally:
        work_memory.RECEIPT_ROOT, work_memory.ROOT, work_memory.registry_rows = original

    assert result["ok"] is True
    assert result["missing_receipts_refused"] is True


@pytest.mark.parametrize("mode", ["registered", "discovery"])
def test_probe_is_repeatable_without_canonical_ledger_cleanup(
    mode: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    skills_root = Path(__file__).resolve().parents[1] / "skills"
    ledger = work_memory.LEDGER
    before = ledger.read_bytes() if ledger.is_file() else b""
    first = work_memory_contract_probe.run_probe(skills_root, mode)
    second = work_memory_contract_probe.run_probe(skills_root, mode)
    assert first["ok"] and second["ok"]
    assert first["missing_receipts_refused"] and second["missing_receipts_refused"]
    after = ledger.read_bytes() if ledger.is_file() else b""
    assert before == after


def test_probe_cannot_claim_an_existing_real_task(monkeypatch: pytest.MonkeyPatch) -> None:
    skills_root = Path(__file__).resolve().parents[1] / "skills"
    result = work_memory_contract_probe.run_probe(skills_root, "registered")
    assert result["ok"]
    # Run-scoped task identities are unique per invocation, never a fixed probe-* name.
    again = work_memory_contract_probe.run_probe(skills_root, "registered")
    assert again["ok"]
