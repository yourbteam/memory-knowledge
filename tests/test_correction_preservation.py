from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import work_memory


WRITER_A = "019f75a9-fd91-7650-a43f-d20de5e3ae16"
WRITER_B = "019ee569-0b44-7292-b806-a19fc34c09a2"


def _event(kind: str, **fields):
    return {
        "schema_version": 1,
        "event_id": str(uuid.uuid4()),
        "event_type": kind,
        "recorded_at_utc": fields.pop("recorded_at_utc", "2026-01-01T00:00:00Z"),
        **fields,
    }


@pytest.fixture(autouse=True)
def _isolated_boundary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CODEX_THREAD_ID", WRITER_A)
    monkeypatch.setattr(work_memory, "ROOT", tmp_path)
    monkeypatch.setattr(work_memory, "LEDGER", tmp_path / "work-memory/events.jsonl")
    monkeypatch.setattr(work_memory, "BLOCKER_VIEW", tmp_path / "blockers/BLOCKERS.md")
    monkeypatch.setattr(work_memory, "RECEIPT_ROOT", tmp_path / "receipts")


def _flow(tmp_path: Path) -> dict[str, object]:
    preserved_task = "original-correction-task"
    target_task = "preservation-remediation-task"
    preserved_state = work_memory._claim_task_writer(preserved_task)
    target_state = work_memory._claim_task_writer(target_task)
    subject = lineage = "discovery-real-topology"
    paths = [
        "operations/sequences/discovery/2026-07-17-prevention-owner-runtime-five-defect-convergence.md",
        "src/workflow_orch/mcp_server.py",
        "scripts/sequence_guard.py",
        "operations/sequences/discovery/2026-07-17-prevention-owner-runtime-five-defect-convergence.dependencies.json",
        "tests/test_discovery_bootstrap.py",
        "scripts/work_memory.py",
    ]
    files = [tmp_path / path for path in paths]
    for file in files:
        file.parent.mkdir(parents=True, exist_ok=True)
    old_bytes = [
        b"old sequence document\n", b"unchanged mcp server\n",
        b"unchanged sequence guard\n", b"unchanged dependencies\n",
        b"unchanged discovery test\n", b"old controller\n",
    ]
    current_bytes = [
        b"new sequence document\n", *old_bytes[1:5], b"new controller\n",
    ]
    for file, data in zip(files, current_bytes, strict=True):
        file.write_bytes(data)
    old_hashes = [work_memory.sha256_bytes(data) for data in old_bytes]
    current_hashes = [work_memory.sha256_bytes(data) for data in current_bytes]
    preserved_run, target_run, verify_run = (str(uuid.uuid4()) for _ in range(3))
    preserved_ids = [
        "6c843653-5f6e-5c75-8ece-731abc4085fc",
        "e3cf9723-0ba4-580c-a6b9-07e05794f185",
        "1019dab6-5280-5d22-be98-1406f9664b24",
    ]
    target_id = str(uuid.uuid4())
    preserved_blockers = ["blk-" + str(index) * 24 for index in range(1, 4)]
    target_blocker = "blk-" + "4" * 24
    old_bundle_hash, intermediate_hash, target_hash = (
        "a" * 64, "b" * 64, "c" * 64,
    )
    final_bundle = [
        {"repository_key": "memory-knowledge", "path": path, "sha256": digest}
        for path, digest in zip(paths, current_hashes, strict=True)
    ]
    preserved_owner = work_memory._ownership_receipt_fields(
        preserved_task, preserved_state,
    )
    target_owner = work_memory._ownership_receipt_fields(target_task, target_state)
    rows = [_event(
        "run_started", run_id=preserved_run, subject_id=subject, lineage_id=lineage,
        mode="discovery", operation_kind="other", source_bundle=[],
        source_bundle_hash=old_bundle_hash, classification_receipt_hash="1" * 64,
        selection_receipt_hash="2" * 64, started_at_utc="2026-01-01T00:00:00Z",
        task_id=preserved_task, repository_roots={"memory-knowledge": str(tmp_path)},
        **preserved_owner,
    )]
    artifacts = [
        (
            [paths[0], paths[1], paths[2], paths[5]],
            [old_hashes[0], old_hashes[1], old_hashes[2], old_hashes[5]],
        ),
        (
            [paths[0], paths[1], paths[2], paths[5]],
            [old_hashes[0], old_hashes[1], old_hashes[2], old_hashes[5]],
        ),
        (
            [paths[0], paths[3], paths[4]],
            [old_hashes[0], old_hashes[3], old_hashes[4]],
        ),
    ]
    for index, (correction_id, blocker_id, artifact_pair) in enumerate(zip(
        preserved_ids, preserved_blockers, artifacts, strict=True,
    )):
        occurrence = str(uuid.uuid4())
        rows.extend([
            _event(
                "blocker_opened", run_id=preserved_run, blocker_id=blocker_id,
                occurrence_id=occurrence, fingerprint=str(index + 1) * 64,
                subject_id=subject, lineage_id=lineage, step_id=f"old-{index}",
                surface="controller", symptom="old defect", evidence="captured",
                impact="blocked", boundary="correction", status="open",
            ),
            _event(
                "correction_recorded", run_id=preserved_run, blocker_id=blocker_id,
                occurrence_id=occurrence, correction_id=correction_id,
                subject_id=subject, lineage_id=lineage, step_id=f"old-{index}",
                changed_artifacts=artifact_pair[0],
                changed_artifact_hashes=artifact_pair[1],
                reusable_behavior_changed=True, solution=f"old fix {index}",
            ),
            _event(
                "blocker_transitioned", run_id=preserved_run, blocker_id=blocker_id,
                from_status="open", to_status="fixed-awaiting-verification",
            ),
        ])
    rows.extend([
        _event(
            "bundle_transition_recorded", lineage_id=lineage,
            old_bundle_hash=old_bundle_hash, new_bundle_hash=intermediate_hash,
            transition_reason="correction", run_id=preserved_run,
            correction_ids=preserved_ids,
            changed_artifacts=paths, changed_artifact_hashes=old_hashes,
        ),
        _event(
            "run_closed", run_id=preserved_run, subject_id=subject, lineage_id=lineage,
            result="failed", completed_at_utc="2026-01-01T00:01:00Z",
            correction_count=3, blocker_ids=preserved_blockers,
            sequence_updated=True, verification_quality="none",
        ),
        _event(
            "run_started", run_id=target_run, subject_id=subject, lineage_id=lineage,
            mode="discovery", operation_kind="other", source_bundle=[],
            source_bundle_hash=intermediate_hash, classification_receipt_hash="3" * 64,
            selection_receipt_hash="4" * 64, started_at_utc="2026-01-01T00:02:00Z",
            task_id=target_task, repository_roots={"memory-knowledge": str(tmp_path)},
            **target_owner,
        ),
    ])
    target_occurrence = str(uuid.uuid4())
    rows.extend([
        _event(
            "blocker_opened", run_id=target_run, blocker_id=target_blocker,
            occurrence_id=target_occurrence, fingerprint="4" * 64,
            subject_id=subject, lineage_id=lineage, step_id="preservation-contract",
            surface="controller", symptom="cannot preserve", evidence="captured",
            impact="blocked", boundary="preservation", status="open",
        ),
        _event(
            "correction_recorded", run_id=target_run, blocker_id=target_blocker,
            occurrence_id=target_occurrence, correction_id=target_id,
            subject_id=subject, lineage_id=lineage, step_id="preservation-contract",
            changed_artifacts=[paths[0], paths[5]],
            changed_artifact_hashes=[current_hashes[0], current_hashes[5]],
            reusable_behavior_changed=True, solution="explicit preservation contract",
        ),
    ])
    target_transition = _event(
        "bundle_transition_recorded", lineage_id=lineage,
        old_bundle_hash=intermediate_hash, new_bundle_hash=target_hash,
        transition_reason="correction", run_id=target_run, correction_ids=[target_id],
        changed_artifacts=[paths[0], paths[5]],
        changed_artifact_hashes=[current_hashes[0], current_hashes[5]],
    )
    rows.extend([
        target_transition,
        _event(
            "blocker_transitioned", run_id=target_run, blocker_id=target_blocker,
            from_status="open", to_status="fixed-awaiting-verification",
        ),
        _event(
            "run_closed", run_id=target_run, subject_id=subject, lineage_id=lineage,
            result="failed", completed_at_utc="2026-01-01T00:03:00Z",
            correction_count=1, blocker_ids=[target_blocker], sequence_updated=True,
            verification_quality="none",
        ),
        _event(
            "run_started", run_id=verify_run, subject_id=subject, lineage_id=lineage,
            mode="discovery", operation_kind="other", source_bundle=final_bundle,
            source_bundle_hash=target_hash, classification_receipt_hash="5" * 64,
            selection_receipt_hash="6" * 64, started_at_utc="2026-01-01T00:04:00Z",
            predecessor_run_id=target_run, verifies_correction_ids=[target_id],
            task_id=target_task, repository_roots={"memory-knowledge": str(tmp_path)},
            **target_owner,
        ),
    ])
    verification = _event(
        "verification_recorded", run_id=verify_run, subject_id=subject,
        lineage_id=lineage, source_bundle_hash=target_hash, outcome="passed",
        quality="same-path", evidence="target passed", blocker_ids=[target_blocker],
        correction_ids=[target_id],
        changed_artifact_hashes=[current_hashes[0], current_hashes[5]],
    )
    rows.extend([
        verification,
        _event(
            "blocker_transitioned", run_id=verify_run, blocker_id=target_blocker,
            from_status="fixed-awaiting-verification", to_status="verified",
            verification_event_id=verification["event_id"],
        ),
        _event(
            "blocker_transitioned", run_id=verify_run, blocker_id=target_blocker,
            from_status="verified", to_status="closed",
            verification_event_id=verification["event_id"], remaining_work="none",
        ),
        _event(
            "run_closed", run_id=verify_run, subject_id=subject, lineage_id=lineage,
            result="passed", completed_at_utc="2026-01-01T00:05:00Z",
            correction_count=0, blocker_ids=[target_blocker], sequence_updated=False,
            verification_quality="same-path",
        ),
    ])
    work_memory.transact({"schema_version": 1, "expected_ledger_hash": None, "events": rows})
    args = SimpleNamespace(
        task_id=target_task, preserved_task_id=preserved_task,
        target_correction_id=target_id,
        target_verification_event_id=verification["event_id"],
        preserved_correction_id=preserved_ids, event_id=None,
        authenticated_source_bundle=final_bundle,
        authenticated_source_bundle_hash=target_hash,
    )
    return {
        "args": args, "files": files, "preserved_run": preserved_run,
        "preserved_ids": preserved_ids, "target_id": target_id,
        "target_hash": target_hash, "final_bundle": final_bundle,
        "lineage": lineage,
    }


def test_real_topology_preserves_only_original_task_corrections(
    tmp_path: Path,
) -> None:
    flow = _flow(tmp_path)
    result = work_memory.cmd_preserve_corrections(flow["args"])
    events, _ = work_memory.load_ledger()

    work_memory._validate_successor_corrections(
        events, lineage_id=flow["lineage"], source_bundle=flow["final_bundle"],
        predecessor_run_id=flow["preserved_run"], correction_ids=flow["preserved_ids"],
        repository_roots={"memory-knowledge": str(tmp_path)},
        source_bundle_hash=flow["target_hash"],
    )

    assert result["preserved_correction_ids"] == flow["preserved_ids"]
    assert events[-1]["target_verification_event_id"] == flow["args"].target_verification_event_id
    with pytest.raises(
        work_memory.WorkMemoryError, match="successor-correction-preservation-mismatch",
    ):
        work_memory._validate_successor_corrections(
            events, lineage_id=flow["lineage"], source_bundle=flow["final_bundle"],
            predecessor_run_id=flow["preserved_run"],
            correction_ids=[*flow["preserved_ids"], flow["target_id"]],
            repository_roots={"memory-knowledge": str(tmp_path)},
            source_bundle_hash=flow["target_hash"],
        )


@pytest.mark.parametrize(
    ("file_index", "error"), [
        (0, "preservation-target-artifact-hash-mismatch"),
        (1, "preservation-overwrite-not-declared"),
    ],
)
def test_preservation_rejects_changed_or_uncovered_artifact(
    tmp_path: Path, file_index: int, error: str,
) -> None:
    flow = _flow(tmp_path)
    flow["files"][file_index].write_text("tampered\n")

    with pytest.raises(work_memory.WorkMemoryError, match=error):
        work_memory.cmd_preserve_corrections(flow["args"])


def test_preservation_foreign_host_leaves_ledger_byte_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    flow = _flow(tmp_path)
    before = work_memory.LEDGER.read_bytes()
    monkeypatch.setenv("CODEX_THREAD_ID", WRITER_B)

    with pytest.raises(
        work_memory.WorkMemoryError, match="correction-preservation-owner-mismatch",
    ):
        work_memory.cmd_preserve_corrections(flow["args"])

    assert work_memory.LEDGER.read_bytes() == before


def test_preservation_is_idempotent_by_event_id_and_rejects_conflicting_second_edge(
    tmp_path: Path,
) -> None:
    flow = _flow(tmp_path)
    flow["args"].event_id = str(uuid.uuid4())
    first = work_memory.cmd_preserve_corrections(flow["args"])
    after_first = work_memory.LEDGER.read_bytes()

    retried = work_memory.cmd_preserve_corrections(flow["args"])

    assert retried["event_id"] == first["event_id"]
    assert work_memory.LEDGER.read_bytes() == after_first
    flow["args"].event_id = str(uuid.uuid4())
    with pytest.raises(
        work_memory.WorkMemoryError, match="conflicting-correction-preservation",
    ):
        work_memory.cmd_preserve_corrections(flow["args"])
    assert work_memory.LEDGER.read_bytes() == after_first


@pytest.mark.parametrize(
    ("mutation", "error"), [
        ("duplicate", "duplicate-preserved-correction"),
        ("self", "self-preserved-correction"),
        ("proof", "preservation-target-verification-not-found"),
    ],
)
def test_preservation_rejects_identity_or_proof_defect(
    tmp_path: Path, mutation: str, error: str,
) -> None:
    flow = _flow(tmp_path)
    args = flow["args"]
    if mutation == "duplicate":
        args.preserved_correction_id.append(args.preserved_correction_id[0])
    elif mutation == "self":
        args.preserved_correction_id = [args.target_correction_id]
    else:
        args.target_verification_event_id = str(uuid.uuid4())

    with pytest.raises(work_memory.WorkMemoryError, match=error):
        work_memory.cmd_preserve_corrections(args)


def test_preservation_requires_distinct_target_and_preserved_tasks(
    tmp_path: Path,
) -> None:
    flow = _flow(tmp_path)
    flow["args"].preserved_task_id = flow["args"].task_id

    with pytest.raises(
        work_memory.WorkMemoryError,
        match="correction-preservation-distinct-tasks-required",
    ):
        work_memory.cmd_preserve_corrections(flow["args"])


@pytest.mark.parametrize(
    ("mutation", "error"), [
        ("duplicate-correction", "ambiguous-preservation-target-correction"),
        ("multiple-transitions", "ambiguous-preservation-target-transition"),
        ("bad-order", "correction-preservation-order-mismatch"),
    ],
)
def test_preservation_replay_rejects_ambiguous_domain_or_bad_order(
    tmp_path: Path, mutation: str, error: str,
) -> None:
    flow = _flow(tmp_path)
    flow["args"].event_id = str(uuid.uuid4())
    work_memory.cmd_preserve_corrections(flow["args"])
    events, _ = work_memory.load_ledger()
    preservation_index = next(
        index for index, item in enumerate(events)
        if item["event_type"] == "correction_preservation_recorded"
    )
    target_index = next(
        index for index, item in enumerate(events)
        if item.get("correction_id") == flow["target_id"]
    )
    transition_index = next(
        index for index, item in enumerate(events)
        if flow["target_id"] in item.get("correction_ids", [])
        and item["event_type"] == "bundle_transition_recorded"
    )
    verification_index = next(
        index for index, item in enumerate(events)
        if item["event_type"] == "verification_recorded"
        and flow["target_id"] in item["correction_ids"]
    )
    if mutation == "duplicate-correction":
        duplicate = dict(events[target_index], event_id=str(uuid.uuid4()))
        events.insert(preservation_index, duplicate)
    elif mutation == "multiple-transitions":
        duplicate = dict(events[transition_index], event_id=str(uuid.uuid4()))
        events.insert(preservation_index, duplicate)
    else:
        transition = events.pop(transition_index)
        if transition_index < verification_index:
            verification_index -= 1
        events.insert(verification_index + 1, transition)

    with pytest.raises(work_memory.WorkMemoryError, match=error):
        work_memory._validate_correction_preservation_records(events)


def test_lifecycle_rejects_duplicate_correction_id_globally(
    tmp_path: Path,
) -> None:
    _flow(tmp_path)
    events, _ = work_memory.load_ledger()
    correction_index = next(
        index for index, item in enumerate(events)
        if item["event_type"] == "correction_recorded"
    )
    duplicate = dict(events[correction_index], event_id=str(uuid.uuid4()))
    events.insert(correction_index + 1, duplicate)

    with pytest.raises(work_memory.WorkMemoryError, match="duplicate-correction-id"):
        work_memory.validate_lifecycle(events)
