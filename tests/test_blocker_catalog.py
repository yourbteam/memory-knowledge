import uuid
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


def _pre_run_open_args(task_id: str, ownership_event_id: str):
    return blocker_catalog.build_parser().parse_args([
        "open", "--task-id", task_id, "--ownership-event-id", ownership_event_id,
        "--step-id", "select", "--surface", "registry",
        "--error-signature", "source-hash-drift", "--symptom", "selection blocked",
        "--evidence", "exact selector error", "--impact", "no run can start",
        "--boundary", "owner source binding",
    ])


def test_open_pre_run_blocker_requires_current_real_ownership_event(monkeypatch):
    task_id = "selection-blocked-task"
    ownership_event_id = str(uuid.uuid4())
    writer_thread_id = str(uuid.uuid4())
    events = [{
        "event_type": "task_writer_claimed", "event_id": ownership_event_id,
        "task_id": task_id, "writer_thread_id": writer_thread_id,
        "ownership_generation": 1,
    }]
    captured = {}
    monkeypatch.setattr(blocker_catalog.work_memory, "load_ledger", lambda: (events, "0" * 64))

    def capture(request):
        captured["request"] = request
        return {"ok": True}

    monkeypatch.setattr(blocker_catalog.work_memory, "transact", capture)

    result = _pre_run_open_args(task_id, ownership_event_id).func(
        _pre_run_open_args(task_id, ownership_event_id)
    )

    opened = captured["request"]["events"][0]
    assert opened["event_type"] == "pre_run_blocker_opened"
    assert opened["task_id"] == task_id
    assert opened["ownership_event_id"] == ownership_event_id
    assert opened["subject_id"] == opened["lineage_id"] == task_id
    assert result["event_type"] == "pre_run_blocker_opened"


def test_open_pre_run_blocker_rejects_nonexistent_ownership_event(monkeypatch):
    ownership_event_id = str(uuid.uuid4())
    monkeypatch.setattr(blocker_catalog.work_memory, "load_ledger", lambda: ([], "0" * 64))
    args = _pre_run_open_args("selection-blocked-task", ownership_event_id)
    with pytest.raises(work_memory.WorkMemoryError, match="ownership-event-not-found"):
        args.func(args)


def test_open_pre_run_blocker_rejects_stale_ownership_event(monkeypatch):
    task_id = "selection-blocked-task"
    first_event_id = str(uuid.uuid4())
    first_writer = str(uuid.uuid4())
    second_writer = str(uuid.uuid4())
    events = [
        {"event_type": "task_writer_claimed", "event_id": first_event_id,
         "task_id": task_id, "writer_thread_id": first_writer, "ownership_generation": 1},
        {"event_type": "task_writer_handoff_recorded", "event_id": str(uuid.uuid4()),
         "task_id": task_id, "from_writer_thread_id": first_writer,
         "to_writer_thread_id": second_writer, "ownership_generation": 2,
         "previous_ownership_event_id": first_event_id},
    ]
    monkeypatch.setattr(blocker_catalog.work_memory, "load_ledger", lambda: (events, "0" * 64))
    args = _pre_run_open_args(task_id, first_event_id)
    with pytest.raises(work_memory.WorkMemoryError, match="ownership-event-not-current"):
        args.func(args)


def test_pre_run_commands_record_correction_verification_and_close(monkeypatch):
    task_id = "selection-blocked-task"
    ownership_event_id = str(uuid.uuid4())
    blocker_id = "blk-" + "4" * 24
    occurrence_id = str(uuid.uuid4())
    events = [
        {"event_type": "task_writer_claimed", "event_id": ownership_event_id,
         "task_id": task_id, "writer_thread_id": str(uuid.uuid4()),
         "ownership_generation": 1},
        {"event_type": "pre_run_blocker_opened", "event_id": str(uuid.uuid4()),
         "task_id": task_id, "ownership_event_id": ownership_event_id,
         "blocker_id": blocker_id, "occurrence_id": occurrence_id,
         "step_id": "select", "subject_id": task_id, "lineage_id": task_id},
    ]
    monkeypatch.setattr(blocker_catalog.work_memory, "load_ledger", lambda: (events, "0" * 64))
    monkeypatch.setattr(
        blocker_catalog.work_memory, "_artifact_hashes",
        lambda _paths: (["scripts/work_memory.py"], ["6" * 64]),
    )

    def append(request):
        events.extend(request["events"])
        return {"ok": True}

    monkeypatch.setattr(blocker_catalog.work_memory, "transact", append)
    parser = blocker_catalog.build_parser()
    corrected = parser.parse_args([
        "pre-run-correct", "--task-id", task_id,
        "--ownership-event-id", ownership_event_id, "--blocker-id", blocker_id,
        "--occurrence-id", occurrence_id, "--changed-artifact", "scripts/work_memory.py",
        "--solution", "refresh binding", "--reusable-behavior-changed", "yes",
    ]).func(parser.parse_args([
        "pre-run-correct", "--task-id", task_id,
        "--ownership-event-id", ownership_event_id, "--blocker-id", blocker_id,
        "--occurrence-id", occurrence_id, "--changed-artifact", "scripts/work_memory.py",
        "--solution", "refresh binding", "--reusable-behavior-changed", "yes",
    ]))
    command = "python3 scripts/work_memory.py select --task-id selection-blocked-task"
    verified = parser.parse_args([
        "pre-run-verify", "--task-id", task_id,
        "--ownership-event-id", ownership_event_id, "--blocker-id", blocker_id,
        "--occurrence-id", occurrence_id, "--correction-id", corrected["correction_id"],
        "--command", command, "--evidence", "drift cleared; ordinary ambiguity reached",
    ])
    verification = verified.func(verified)
    for status in ("verified", "closed"):
        transition = parser.parse_args([
            "pre-run-transition", "--task-id", task_id,
            "--ownership-event-id", ownership_event_id, "--blocker-id", blocker_id,
            "--occurrence-id", occurrence_id,
            "--verification-event-id", verification["verification_event_id"],
            "--to-status", status,
        ])
        transition.func(transition)

    assert [item["event_type"] for item in events[-5:]] == [
        "pre_run_correction_recorded", "pre_run_blocker_transitioned",
        "pre_run_verification_recorded", "pre_run_blocker_transitioned",
        "pre_run_blocker_transitioned",
    ]
    assert events[-3]["verification_command"] == command
    assert events[-1]["remaining_work"] == "none"


def test_recover_command_emits_canonical_transition(monkeypatch):
    run_id = str(uuid.uuid4())
    blocker_id = "blk-" + "1" * 24
    events = [
        {"event_type": "run_started", "run_id": run_id},
        {"event_type": "blocker_opened", "blocker_id": blocker_id},
        {"event_type": "blocker_transitioned", "blocker_id": blocker_id,
         "to_status": "fixed-awaiting-verification"},
    ]
    captured = {}
    monkeypatch.setattr(blocker_catalog.work_memory, "load_ledger", lambda: (events, "0" * 64))

    def capture(request):
        captured["request"] = request
        return {"ok": True}

    monkeypatch.setattr(blocker_catalog.work_memory, "transact", capture)
    args = blocker_catalog.build_parser().parse_args([
        "recover", "--run-id", run_id, "--blocker-id", blocker_id,
        "--reopen-evidence", "captured event predates correction enforcement",
    ])

    result = args.func(args)

    transition = captured["request"]["events"][0]
    assert transition["event_type"] == "blocker_transitioned"
    assert transition["run_id"] == run_id
    assert transition["blocker_id"] == blocker_id
    assert transition["from_status"] == "fixed-awaiting-verification"
    assert transition["to_status"] == "open"
    assert transition["recovery_evidence"] == "captured event predates correction enforcement"
    assert result["event_id"] == transition["event_id"]


def test_recover_command_preserves_open_status_for_successor_rebinding(monkeypatch):
    old_run_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    blocker_id = "blk-" + "1" * 24
    events = [
        {"event_type": "run_started", "run_id": old_run_id},
        {"event_type": "blocker_opened", "blocker_id": blocker_id},
        {"event_type": "run_started", "run_id": run_id},
    ]
    captured = {}
    monkeypatch.setattr(blocker_catalog.work_memory, "load_ledger", lambda: (events, "0" * 64))

    def capture(request):
        captured["request"] = request
        return {"ok": True}

    monkeypatch.setattr(blocker_catalog.work_memory, "transact", capture)
    args = blocker_catalog.build_parser().parse_args([
        "recover", "--run-id", run_id, "--blocker-id", blocker_id,
        "--reopen-evidence", "carry the open occurrence to its active successor",
    ])

    args.func(args)

    transition = captured["request"]["events"][0]
    assert transition["from_status"] == "open"
    assert transition["to_status"] == "open"
    assert transition["recovery_evidence"] == "carry the open occurrence to its active successor"


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
