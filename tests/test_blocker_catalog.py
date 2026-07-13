from argparse import Namespace

import pytest

from scripts import blocker_catalog, work_memory
from scripts.blocker_catalog import fingerprint, normalize_error_signature


def test_fingerprint_normalizes_volatile_values_but_keeps_error_code():
    first = fingerprint(
        "deploy", "lineage", "upload",
        "ERR42 at 2026-01-01T12:00:00Z id 123e4567-e89b-12d3-a456-426614174000 attempt 1",
    )
    second = fingerprint(
        "deploy", "lineage", "upload",
        "ERR42 at 2027-02-02T13:00:00Z id 223e4567-e89b-12d3-a456-426614174999 attempt 9",
    )
    different = fingerprint("deploy", "lineage", "upload", "ERR43 attempt 9")
    assert first == second and first != different
    assert "err42" in normalize_error_signature("ERR42 line 99")


def test_reopen_transition_requires_evidence(monkeypatch: pytest.MonkeyPatch):
    blocker_id = "blk-" + "1" * 24
    monkeypatch.setattr(blocker_catalog.work_memory, "load_ledger", lambda: ([
        {"event_type": "blocker_opened", "blocker_id": blocker_id},
        {"event_type": "blocker_transitioned", "blocker_id": blocker_id,
         "to_status": "fixed-awaiting-verification"},
    ], "a" * 64))
    monkeypatch.setattr(blocker_catalog, "_run", lambda _events, _run_id: {})
    with pytest.raises(work_memory.WorkMemoryError, match="reopen-evidence-required"):
        blocker_catalog.cmd_transition(Namespace(
            run_id="run", blocker_id=blocker_id, to_status="open",
            verification_event_id=None, remaining_work="none", supersession_evidence=None,
            non_gap_evidence=None, reopen_evidence=None, event_id=None,
        ))
