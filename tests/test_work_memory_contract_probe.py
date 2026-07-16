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
