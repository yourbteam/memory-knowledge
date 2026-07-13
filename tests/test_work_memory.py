from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts import work_memory


def event(kind: str, **fields):
    return {
        "schema_version": 1, "event_id": str(uuid.uuid4()), "event_type": kind,
        "recorded_at_utc": fields.pop("recorded_at_utc", "2026-01-01T00:00:00Z"), **fields,
    }


def run_events(index: int, *, result: str = "passed", duration: int = 10, bundle: str = "a" * 64):
    run_id = str(uuid.uuid4())
    started = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=index)
    start = event(
        "run_started", run_id=run_id, subject_id="sequence", lineage_id="lineage",
        mode="registered", operation_kind="other", source_bundle=[], source_bundle_hash=bundle,
        classification_receipt_hash="b" * 64, selection_receipt_hash="c" * 64,
        started_at_utc=started.isoformat(), recorded_at_utc=started.isoformat(),
    )
    verification = event(
        "verification_recorded", run_id=run_id, subject_id="sequence", lineage_id="lineage",
        source_bundle_hash=bundle, outcome=result, quality="same-path", evidence="test passed",
        blocker_ids=[], correction_ids=[], changed_artifact_hashes=[],
        recorded_at_utc=(started + timedelta(seconds=duration - 1)).isoformat(),
    )
    close = event(
        "run_closed", run_id=run_id, subject_id="sequence", lineage_id="lineage", result=result,
        completed_at_utc=(started + timedelta(seconds=duration)).isoformat(), correction_count=0,
        blocker_ids=[], sequence_updated=False, verification_quality="same-path",
        recorded_at_utc=(started + timedelta(seconds=duration)).isoformat(),
    )
    return [start, verification, close]


def corrected_successor_events():
    run_a, run_b = str(uuid.uuid4()), str(uuid.uuid4())
    occurrence, correction_id = str(uuid.uuid4()), str(uuid.uuid4())
    blocker_id, fingerprint = "blk-" + "1" * 24, "1" * 64
    bundle_a, bundle_b = "a" * 64, "b" * 64
    start_a = event(
        "run_started", run_id=run_a, subject_id="sequence", lineage_id="lineage",
        mode="registered", operation_kind="deploy", source_bundle=[], source_bundle_hash=bundle_a,
        classification_receipt_hash="c" * 64, selection_receipt_hash="d" * 64,
        started_at_utc="2026-01-01T00:00:00Z",
    )
    opened = event(
        "blocker_opened", run_id=run_a, blocker_id=blocker_id, occurrence_id=occurrence,
        fingerprint=fingerprint, subject_id="sequence", lineage_id="lineage", step_id="deploy",
        surface="deploy", symptom="failed", evidence="exit 1", impact="blocked",
        boundary="script", status="open",
    )
    correction = event(
        "correction_recorded", run_id=run_a, blocker_id=blocker_id, occurrence_id=occurrence,
        correction_id=correction_id, subject_id="sequence", lineage_id="lineage", step_id="deploy",
        changed_artifacts=["scripts/deploy.sh"], changed_artifact_hashes=["e" * 64],
        reusable_behavior_changed=True, solution="use the corrected flag",
    )
    transition = event(
        "bundle_transition_recorded", lineage_id="lineage", old_bundle_hash=bundle_a,
        new_bundle_hash=bundle_b, transition_reason="correction", run_id=run_a,
        correction_ids=[correction_id], changed_artifacts=["scripts/deploy.sh"],
        changed_artifact_hashes=["e" * 64],
    )
    awaiting = event(
        "blocker_transitioned", run_id=run_a, blocker_id=blocker_id,
        from_status="open", to_status="fixed-awaiting-verification",
    )
    close_a = event(
        "run_closed", run_id=run_a, subject_id="sequence", lineage_id="lineage", result="failed",
        completed_at_utc="2026-01-01T00:01:00Z", correction_count=1,
        blocker_ids=[blocker_id], sequence_updated=True, verification_quality="none",
    )
    start_b = event(
        "run_started", run_id=run_b, subject_id="sequence", lineage_id="lineage",
        mode="registered", operation_kind="deploy", source_bundle=[], source_bundle_hash=bundle_b,
        classification_receipt_hash="f" * 64, selection_receipt_hash="0" * 64,
        started_at_utc="2026-01-01T00:02:00Z", predecessor_run_id=run_a,
        verifies_correction_ids=[correction_id],
    )
    verification = event(
        "verification_recorded", run_id=run_b, subject_id="sequence", lineage_id="lineage",
        source_bundle_hash=bundle_b, outcome="passed", quality="same-path", evidence="same path passed",
        blocker_ids=[blocker_id], correction_ids=[correction_id],
        changed_artifact_hashes=["e" * 64],
    )
    verified = event(
        "blocker_transitioned", run_id=run_b, blocker_id=blocker_id,
        from_status="fixed-awaiting-verification", to_status="verified",
        verification_event_id=verification["event_id"],
    )
    closed = event(
        "blocker_transitioned", run_id=run_b, blocker_id=blocker_id,
        from_status="verified", to_status="closed", verification_event_id=verification["event_id"],
        remaining_work="none",
    )
    close_b = event(
        "run_closed", run_id=run_b, subject_id="sequence", lineage_id="lineage", result="passed",
        completed_at_utc="2026-01-01T00:03:00Z", correction_count=0,
        blocker_ids=[blocker_id], sequence_updated=False, verification_quality="same-path",
    )
    return [start_a, opened, correction, transition, awaiting, close_a,
            start_b, verification, verified, closed, close_b]


def test_stage_batch_is_atomic_and_exact_retry_is_idempotent():
    events = run_events(0)
    request = {"schema_version": 1, "expected_ledger_hash": work_memory.sha256_bytes(b""), "events": events}
    ledger, view, first = work_memory.stage_event_batch(b"", request)
    retry = {"schema_version": 1, "expected_ledger_hash": work_memory.sha256_bytes(ledger), "events": events}
    ledger2, view2, second = work_memory.stage_event_batch(ledger, retry)
    assert ledger2 == ledger and view2 == view
    assert second["idempotent_event_ids"] == [item["event_id"] for item in events]
    assert first["ledger_hash"] == work_memory.sha256_bytes(ledger)


def test_event_id_collision_rejects_without_output():
    events = run_events(0)
    ledger, _, _ = work_memory.stage_event_batch(
        b"", {"schema_version": 1, "expected_ledger_hash": work_memory.sha256_bytes(b""), "events": events}
    )
    conflict = dict(events[0]); conflict["operation_kind"] = "deploy"
    with pytest.raises(work_memory.WorkMemoryError, match="event-id-conflict"):
        work_memory.stage_event_batch(
            ledger, {"schema_version": 1, "expected_ledger_hash": None, "events": [conflict]}
        )


def test_closed_schema_rejects_unknown_and_personal_fields():
    bad = run_events(0)[0]; bad["diary"] = "today"
    with pytest.raises(work_memory.WorkMemoryError, match="unknown-event-fields"):
        work_memory.stage_event_batch(
            b"", {"schema_version": 1, "expected_ledger_hash": None, "events": [bad]}
        )


def test_event_after_terminal_fails():
    events = run_events(0)
    events.append(event(
        "verification_recorded", run_id=events[0]["run_id"], subject_id="sequence",
        lineage_id="lineage", source_bundle_hash="a" * 64, outcome="passed", quality="same-path",
        evidence="late", blocker_ids=[], correction_ids=[], changed_artifact_hashes=[],
    ))
    with pytest.raises(work_memory.WorkMemoryError, match="event-after-terminal"):
        work_memory.stage_event_batch(
            b"", {"schema_version": 1, "expected_ledger_hash": None, "events": events}
        )


def test_only_exact_same_path_successor_can_close_blocker():
    valid = corrected_successor_events()
    work_memory.stage_event_batch(
        b"", {"schema_version": 1, "expected_ledger_hash": None, "events": valid}
    )
    unrelated = run_events(9)
    forged = valid[:8] + unrelated[:-1]
    forged_verification = unrelated[1]
    forged.extend([
        {**valid[8], "event_id": str(uuid.uuid4()), "run_id": unrelated[0]["run_id"],
         "verification_event_id": forged_verification["event_id"]},
    ])
    with pytest.raises(work_memory.WorkMemoryError, match="invalid-transition-verification"):
        work_memory.stage_event_batch(
            b"", {"schema_version": 1, "expected_ledger_hash": None, "events": forged}
        )


def test_fixed_awaiting_blocker_can_reopen_for_missing_correction():
    events = corrected_successor_events()
    start, opened, correction, _bundle_transition, awaiting = events[:5]
    reopened = event(
        "blocker_transitioned", run_id=start["run_id"], blocker_id=opened["blocker_id"],
        from_status="fixed-awaiting-verification", to_status="open",
        reopen_evidence="The status advanced before its correction event was recorded.",
    )
    replacement = {
        **correction,
        "event_id": str(uuid.uuid4()),
        "correction_id": str(uuid.uuid4()),
    }
    work_memory.stage_event_batch(
        b"", {"schema_version": 1, "expected_ledger_hash": None,
             "events": [start, opened, awaiting, reopened, replacement]}
    )


def test_reopen_transition_requires_evidence():
    events = corrected_successor_events()[:5]
    events.append(event(
        "blocker_transitioned", run_id=events[0]["run_id"], blocker_id=events[1]["blocker_id"],
        from_status="fixed-awaiting-verification", to_status="open",
    ))
    with pytest.raises(work_memory.WorkMemoryError, match="invalid-blocker-transition-fields"):
        work_memory.stage_event_batch(
            b"", {"schema_version": 1, "expected_ledger_hash": None, "events": events}
        )


def test_one_successor_verification_can_close_two_corrected_blockers():
    base = corrected_successor_events()
    start_a, opened_a, correction_a, transition_a, awaiting_a, close_a = base[:6]
    start_b, verification, verified_a, closed_a, close_b = base[6:]
    blocker_b = "blk-" + "2" * 24
    occurrence_b, correction_b_id = str(uuid.uuid4()), str(uuid.uuid4())
    opened_b = {
        **opened_a, "event_id": str(uuid.uuid4()), "blocker_id": blocker_b,
        "occurrence_id": occurrence_b, "fingerprint": "2" * 64,
    }
    correction_b = {
        **correction_a, "event_id": str(uuid.uuid4()), "blocker_id": blocker_b,
        "occurrence_id": occurrence_b, "correction_id": correction_b_id,
    }
    transition_b = {
        **transition_a, "event_id": str(uuid.uuid4()), "correction_ids": [correction_b_id],
    }
    awaiting_b = {
        **awaiting_a, "event_id": str(uuid.uuid4()), "blocker_id": blocker_b,
    }
    verification = {
        **verification,
        "blocker_ids": [opened_a["blocker_id"], blocker_b],
        "correction_ids": [correction_a["correction_id"], correction_b_id],
        "changed_artifact_hashes": ["e" * 64, "e" * 64],
    }
    start_b = {
        **start_b,
        "verifies_correction_ids": [correction_a["correction_id"], correction_b_id],
    }
    verified_b = {
        **verified_a, "event_id": str(uuid.uuid4()), "blocker_id": blocker_b,
        "verification_event_id": verification["event_id"],
    }
    closed_b = {
        **closed_a, "event_id": str(uuid.uuid4()), "blocker_id": blocker_b,
        "verification_event_id": verification["event_id"],
    }
    close_a = {**close_a, "correction_count": 2, "blocker_ids": [opened_a["blocker_id"], blocker_b]}
    close_b = {**close_b, "blocker_ids": [opened_a["blocker_id"], blocker_b]}

    events = [
        start_a, opened_a, correction_a, transition_a, awaiting_a,
        opened_b, correction_b, transition_b, awaiting_b, close_a,
        start_b, verification, verified_a, closed_a, verified_b, closed_b, close_b,
    ]
    work_memory.stage_event_batch(
        b"", {"schema_version": 1, "expected_ledger_hash": None, "events": events}
    )


@pytest.mark.parametrize("value", [
    "Bearer abcdefghijklmnopqrstuvwxyz",
    "Bearer%20abcdefghijklmnopqrstuvwxyz",
    "Kamen prefers tea",
])
def test_work_only_event_validator_rejects_secret_and_personal_text(value):
    item = run_events(0)[1]; item["evidence"] = value
    with pytest.raises(work_memory.WorkMemoryError, match="prohibited"):
        work_memory.stage_event_batch(
            b"", {"schema_version": 1, "expected_ledger_hash": None, "events": run_events(0)[:1] + [item]}
        )


def test_transact_commits_ledger_and_generated_view(tmp_path: Path):
    ledger, view = tmp_path / "events.jsonl", tmp_path / "BLOCKERS.md"
    result = work_memory.transact(
        {"schema_version": 1, "expected_ledger_hash": None, "events": run_events(0)}, ledger, view
    )
    assert result["ledger_hash"] == work_memory.sha256_bytes(ledger.read_bytes())
    assert f"Ledger-SHA256: `{result['ledger_hash']}`" in view.read_text()


def test_malformed_ledger_reports_line_number():
    with pytest.raises(work_memory.WorkMemoryError, match="malformed-ledger-line:2"):
        work_memory.parse_ledger_bytes(b'\nnot-json\n')


def test_summary_uses_six_run_equal_windows():
    events = []
    for index in range(6):
        events.extend(run_events(index, duration=30 if index < 3 else 10))
    summary = work_memory.summarize(events, "sequence", "a" * 64)
    assert summary["history_status"] == "sufficient"
    assert summary["trend"]["speed_status"] == "improved"
    assert summary["metrics"]["pass_rate"] == [6, 6]


def test_summary_counts_abandoned_runs_with_active_records_present():
    active = run_events(0)[0]
    abandoned = run_events(1)[0]
    abandoned_close = event(
        "run_abandoned",
        run_id=abandoned["run_id"],
        subject_id="sequence",
        lineage_id="lineage",
    )

    summary = work_memory.summarize([active, abandoned, abandoned_close], "sequence")

    assert summary["abandoned_runs"] == 1


def test_recurrence_counts_as_repeated_blocker():
    first, second = run_events(0), run_events(1)
    blocker_id = "blk-" + "2" * 24
    first.insert(1, {"event_type": "blocker_opened", "run_id": first[0]["run_id"], "blocker_id": blocker_id,
                     "fingerprint": "2" * 64})
    second.insert(1, {"event_type": "blocker_recurred", "run_id": second[0]["run_id"], "blocker_id": blocker_id})
    summary = work_memory.summarize(first + second, "sequence", "a" * 64)
    assert summary["metrics"]["repeated_blocker_count"] == 1


def test_change_effect_keeps_operation_kinds_isolated():
    events = corrected_successor_events()
    for index, bundle in ((-2, "a" * 64), (-1, "a" * 64), (4, "b" * 64), (5, "b" * 64)):
        records = run_events(index, bundle=bundle)
        records[0]["operation_kind"] = "deploy"
        events.extend(records)
    for index, bundle in ((-5, "a" * 64), (-4, "a" * 64), (-3, "a" * 64),
                          (6, "b" * 64), (7, "b" * 64), (8, "b" * 64)):
        records = run_events(index, bundle=bundle)
        records[0]["operation_kind"] = "database"
        events.extend(records)
    effect = work_memory.summarize(events, "sequence")["change_effects"][0]
    assert effect["status"] == "sufficient"
    assert effect["comparison"]["before"]["closed_runs"] == 3
    assert effect["comparison"]["after"]["closed_runs"] == 3


def test_classification_boundary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(work_memory, "RECEIPT_ROOT", tmp_path)
    from argparse import Namespace
    nonop = work_memory.cmd_classify(Namespace(
        task_id="one", operation_kind="single-test", repeatable="no", meaningful_steps=1,
    ))
    operational = work_memory.cmd_classify(Namespace(
        task_id="two", operation_kind="single-test", repeatable="yes", meaningful_steps=1,
    ))
    assert nonop["verdict"] == "non-operational"
    assert operational["verdict"] == "operational"


def test_run_start_preserves_external_roots_for_later_correction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    from argparse import Namespace

    root = tmp_path / "memory-knowledge"
    external = tmp_path / "codex-skills"
    discovery = root / "operations/sequences/discovery/repair.md"
    manifest = discovery.with_suffix(".dependencies.json")
    helper = external / "_shared/helper.py"
    for path in (discovery, manifest, helper):
        path.parent.mkdir(parents=True, exist_ok=True)
    discovery.write_text("""# Sequence Discovery Log: repair

DiscoveryId: discovery-repair
Status: discovery
CreatedAtUtc: 2026-07-13T00:00:00Z
RegisteredSequenceMatch: none

## Intended Outcome

Repair the captured bundle.

## Why This Looks Repeatable

Corrections can occur after selection.

## Required Inputs, Auth, Or Environment

- External repository root map.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |

## Failure Handling

Stop on bundle errors.

## Verified Path

- Not verified yet.

## Promotion Readiness

- [ ] Not ready.
""")
    helper.write_text("HELPER = True\n")
    manifest.write_text(json.dumps({
        "schema_version": 1,
        "lineage_id": "discovery-repair",
        "dependencies": [{
            "kind": "file",
            "repository_key": "codex-skills",
            "path_or_sequence_id": "_shared/helper.py",
        }],
    }))
    roots_file = tmp_path / "roots.json"
    roots_file.write_text(json.dumps({"codex-skills": str(external)}))

    monkeypatch.setattr(work_memory, "ROOT", root)
    bundle, bundle_hash, _ = work_memory.resolve_bundle(
        mode="discovery", subject_id="discovery-repair", document=discovery,
        manifest=manifest, repo_roots_file=str(roots_file),
    )
    classification_hash = "a" * 64
    selection_hash = "b" * 64
    classification = {"operation_kind": "other"}
    selection = {
        "classification_receipt_hash": classification_hash,
        "mode": "discovery",
        "subject_id": "discovery-repair",
        "lineage_id": "discovery-repair",
        "document": str(discovery),
        "manifest": str(manifest),
        "source_bundle_hash": bundle_hash,
        "repository_roots_file": str(roots_file),
        "predecessor_run_id": None,
        "verifies_correction_ids": [],
    }

    def load_receipt(_task_id: str, kind: str):
        return (
            (classification, classification_hash, tmp_path / "classification.json")
            if kind == "classification"
            else (selection, selection_hash, tmp_path / "selection.json")
        )

    staged: list[dict] = []
    monkeypatch.setattr(work_memory, "load_receipt", load_receipt)
    monkeypatch.setattr(work_memory, "transact", lambda request: staged.append(request) or {"ok": True})
    work_memory.cmd_run_start(Namespace(task_id="repair", run_id=str(uuid.uuid4()), event_id=None))
    start = staged.pop()["events"][0]
    assert start["source_bundle"] == bundle
    assert start["repository_roots"]["codex-skills"] == str(external.resolve())

    roots_file.unlink()
    discovery.write_text(discovery.read_text() + "\nValidated correction step.\n")
    blocker_id = "blk-" + "9" * 24
    occurrence_id = str(uuid.uuid4())
    opened = event(
        "blocker_opened", run_id=start["run_id"], blocker_id=blocker_id,
        occurrence_id=occurrence_id, fingerprint="9" * 64,
        subject_id="discovery-repair", lineage_id="discovery-repair",
        step_id="repair", surface="work-memory", symptom="failed",
        evidence="missing-repository-root", impact="blocked", boundary="repository roots",
        status="open",
    )
    monkeypatch.setattr(work_memory, "load_ledger", lambda path=work_memory.LEDGER: ([start, opened], "c" * 64))
    result = work_memory.cmd_correct(Namespace(
        run_id=start["run_id"], blocker_id=blocker_id, occurrence_id=occurrence_id,
        step_id="repair", changed_artifact=[str(discovery)], solution="preserve roots",
        reusable_behavior_changed="yes", supersedes_correction_id=None,
        correction_id=None, event_id=None, transition_event_id=None,
        repo_roots_file=None,
    ))
    assert result["ok"] is True
    assert staged[-1]["events"][1]["new_bundle_hash"] != bundle_hash


def test_selection_uses_verified_fingerprint_correction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from argparse import Namespace

    events = corrected_successor_events()
    fingerprint = next(item["fingerprint"] for item in events if item["event_type"] == "blocker_opened")
    monkeypatch.setattr(work_memory, "RECEIPT_ROOT", tmp_path)
    monkeypatch.setattr(work_memory, "registry_rows", lambda: ([{
        "sequence_id": "sequence", "folder": "operations/sequences/sequence/",
        "operation_kinds": "deploy", "lineage_id": "lineage",
    }], "9" * 64))
    monkeypatch.setattr(
        work_memory, "resolve_bundle",
        lambda **kwargs: ([], "b" * 64, "lineage"),
    )
    monkeypatch.setattr(work_memory, "load_ledger", lambda path=work_memory.LEDGER: (events, "8" * 64))
    work_memory.cmd_classify(Namespace(
        task_id="selection", operation_kind="deploy", repeatable="yes", meaningful_steps=3,
    ))
    selected = work_memory.cmd_select(Namespace(
        task_id="selection", sequence_id=None, discovery_log=None, fingerprint=fingerprint,
        verification_successor_of=None, verifies_correction_id=None, repo_roots_file=None,
    ))
    assert selected["selection_reason"] == "fingerprint-link"
    assert selected["eligible_corrections"][0]["solution"] == "use the corrected flag"
    assert selected["recent_run_ids"][0] == events[6]["run_id"]


def test_verified_fingerprint_link_precedes_operation_kind_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    from argparse import Namespace

    events = corrected_successor_events()
    fingerprint = next(item["fingerprint"] for item in events if item["event_type"] == "blocker_opened")
    monkeypatch.setattr(work_memory, "RECEIPT_ROOT", tmp_path)
    monkeypatch.setattr(work_memory, "registry_rows", lambda: ([
        {"sequence_id": "sequence", "folder": "operations/sequences/sequence/",
         "operation_kinds": "repair", "lineage_id": "lineage"},
        {"sequence_id": "unrelated-deploy", "folder": "operations/sequences/unrelated-deploy/",
         "operation_kinds": "deploy", "lineage_id": "unrelated"},
    ], "9" * 64))
    monkeypatch.setattr(
        work_memory, "resolve_bundle",
        lambda **kwargs: ([], "b" * 64, kwargs["subject_id"] == "sequence" and "lineage" or "unrelated"),
    )
    monkeypatch.setattr(work_memory, "load_ledger", lambda path=work_memory.LEDGER: (events, "8" * 64))
    work_memory.cmd_classify(Namespace(
        task_id="cross-kind", operation_kind="deploy", repeatable="yes", meaningful_steps=3,
    ))

    selected = work_memory.cmd_select(Namespace(
        task_id="cross-kind", sequence_id=None, discovery_log=None, fingerprint=fingerprint,
        verification_successor_of=None, verifies_correction_id=None, repo_roots_file=None,
    ))

    assert selected["subject_id"] == "sequence"
    assert selected["selection_reason"] == "fingerprint-link"
    assert selected["relevant_blocker_ids"]
    assert selected["eligible_corrections"]


def test_fingerprint_link_rejects_stale_current_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from argparse import Namespace

    events = corrected_successor_events()
    fingerprint = next(item["fingerprint"] for item in events if item["event_type"] == "blocker_opened")
    monkeypatch.setattr(work_memory, "RECEIPT_ROOT", tmp_path)
    monkeypatch.setattr(work_memory, "registry_rows", lambda: ([{
        "sequence_id": "sequence", "folder": "operations/sequences/sequence/",
        "operation_kinds": "deploy", "lineage_id": "lineage",
    }], "9" * 64))
    monkeypatch.setattr(work_memory, "resolve_bundle", lambda **kwargs: ([], "c" * 64, "lineage"))
    monkeypatch.setattr(work_memory, "load_ledger", lambda path=work_memory.LEDGER: (events, "8" * 64))
    work_memory.cmd_classify(Namespace(
        task_id="stale", operation_kind="deploy", repeatable="yes", meaningful_steps=3,
    ))
    with pytest.raises(work_memory.WorkMemoryError, match="fingerprint-linked-sequence-stale"):
        work_memory.cmd_select(Namespace(
            task_id="stale", sequence_id=None, discovery_log=None, fingerprint=fingerprint,
            verification_successor_of=None, verifies_correction_id=None, repo_roots_file=None,
        ))


def test_fingerprint_tie_break_prefers_higher_success_count_before_lexical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    from argparse import Namespace

    fingerprint = "7" * 64
    events = []
    for subject, successes in (("alpha", 1), ("zeta", 2)):
        blocker = f"blk-{subject}"
        events.extend([
            {"event_type": "blocker_opened", "blocker_id": blocker,
             "fingerprint": fingerprint, "subject_id": subject, "lineage_id": subject},
            {"event_type": "blocker_transitioned", "blocker_id": blocker,
             "to_status": "verified", "recorded_at_utc": "2026-01-01T00:00:00Z"},
        ])
        for index in range(successes):
            run_id = str(uuid.uuid4()); bundle = subject[0] * 64
            events.extend([
                {"event_type": "run_started", "run_id": run_id, "subject_id": subject,
                 "lineage_id": subject, "source_bundle_hash": bundle,
                 "started_at_utc": f"2026-01-01T00:0{index}:00Z"},
                {"event_type": "verification_recorded", "run_id": run_id, "subject_id": subject,
                 "lineage_id": subject, "source_bundle_hash": bundle,
                 "outcome": "passed", "quality": "same-path", "correction_ids": []},
                {"event_type": "run_closed", "run_id": run_id, "subject_id": subject,
                 "result": "passed"},
            ])
    monkeypatch.setattr(work_memory, "RECEIPT_ROOT", tmp_path)
    monkeypatch.setattr(work_memory, "registry_rows", lambda: ([
        {"sequence_id": subject, "folder": f"operations/sequences/{subject}/",
         "operation_kinds": "deploy", "lineage_id": subject}
        for subject in ("alpha", "zeta")
    ], "9" * 64))
    monkeypatch.setattr(work_memory, "resolve_bundle", lambda **kwargs: (
        [], kwargs["subject_id"][0] * 64, kwargs["subject_id"],
    ))
    monkeypatch.setattr(work_memory, "load_ledger", lambda path=work_memory.LEDGER: (events, "8" * 64))
    work_memory.cmd_classify(Namespace(
        task_id="tie", operation_kind="deploy", repeatable="yes", meaningful_steps=3,
    ))
    selected = work_memory.cmd_select(Namespace(
        task_id="tie", sequence_id=None, discovery_log=None, fingerprint=fingerprint,
        verification_successor_of=None, verifies_correction_id=None, repo_roots_file=None,
    ))
    assert selected["subject_id"] == "zeta"


def test_registry_and_manifest_coverage():
    rows, _ = work_memory.registry_rows()
    assert len(rows) == 18
    assert len({row["sequence_id"] for row in rows}) == 18
    for row in rows:
        manifest = work_memory.ROOT / row["folder"] / "dependencies.json"
        data = json.loads(manifest.read_text())
        assert data["schema_version"] == 1
        assert data["lineage_id"] == row["lineage_id"]


def test_no_retired_run_ledger_or_stale_activation_examples():
    assert not (work_memory.ROOT / "scripts/sequence_run_ledger.py").exists()
    tracked = [path for path in (work_memory.ROOT / "operations/sequences").rglob("*.md")]
    tracked.extend((work_memory.ROOT / "skills" / name / "SKILL.md") for name in (
        "working-agreement", "task-intake", "sequence-runner", "blocker-catalog",
    ))
    assert not any("sequence_guard.py activate --sequence-id" in path.read_text() for path in tracked)


def test_only_canonical_scripts_write_event_ledger():
    writers = []
    for path in (work_memory.ROOT / "scripts").glob("*.py"):
        text = path.read_text()
        if "events.jsonl" in text or "stage_event_batch(" in text:
            writers.append(path.name)
    assert sorted(writers) == ["sequence_promote.py", "work_memory.py"]
