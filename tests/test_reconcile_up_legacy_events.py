from __future__ import annotations

import gzip
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import reconcile_up_legacy_events as reconcile


def _row(event_id: str, event_type: str, **fields) -> bytes:
    return (json.dumps({"event_id": event_id, "event_type": event_type,
                        "recorded_at_utc": "2026-10-18T00:00:00Z", **fields},
                       sort_keys=True) + "\n").encode()


def test_capture_keeps_exact_up_run_and_task_events_but_not_other_work(tmp_path, monkeypatch):
    monkeypatch.setattr(reconcile, "DIRECTORY", tmp_path / "archive")
    monkeypatch.setattr(reconcile, "ARCHIVE", tmp_path / "archive/events.jsonl.gz")
    monkeypatch.setattr(reconcile, "MANIFEST", tmp_path / "archive/manifest.json")
    monkeypatch.setattr(reconcile, "ACTIVE", tmp_path / "events.jsonl")
    start = _row("a", "run_started", run_id="up", repository_roots={"united-partners": "/repo"})
    closed = _row("b", "run_closed", run_id="up")
    task = _row("c", "task_writer_claimed", task_id="united-partners-prep")
    other = _row("d", "run_closed", run_id="other")
    source = tmp_path / "legacy.jsonl"
    source.write_bytes(start + closed + task + other)
    reconcile.ACTIVE.write_bytes(start)
    reconcile.create(source)
    assert gzip.decompress(reconcile.ARCHIVE.read_bytes()) == closed + task
    reconcile.verify(source)
    reconcile.ARCHIVE.write_bytes(reconcile.ARCHIVE.read_bytes() + b"changed")
    with pytest.raises((ValueError, gzip.BadGzipFile, EOFError)):
        reconcile.verify()


def test_same_event_id_with_different_content_refuses_before_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(reconcile, "DIRECTORY", tmp_path / "archive")
    monkeypatch.setattr(reconcile, "ARCHIVE", tmp_path / "archive/events.jsonl.gz")
    monkeypatch.setattr(reconcile, "MANIFEST", tmp_path / "archive/manifest.json")
    monkeypatch.setattr(reconcile, "ACTIVE", tmp_path / "events.jsonl")
    source = tmp_path / "legacy.jsonl"
    source.write_bytes(_row("a", "run_started", run_id="up",
                            repository_roots={"united-partners": "/repo"}))
    reconcile.ACTIVE.write_bytes(_row("a", "run_started", run_id="other"))
    with pytest.raises(ValueError, match="conflicts with main"):
        reconcile.create(source)
    assert not reconcile.ARCHIVE.exists()


def _write_status_archive(directory: Path, active: bytes, events: list[bytes]) -> tuple[Path, Path, Path]:
    directory.mkdir()
    active_path = directory / "active.jsonl"
    archive_path = directory / "events.jsonl.gz"
    manifest_path = directory / "manifest.json"
    active_path.write_bytes(active)
    raw = b"".join(events)
    with archive_path.open("wb") as stream:
        with gzip.GzipFile(fileobj=stream, mode="wb", filename="", mtime=0) as zipped:
            zipped.write(raw)
    manifest_path.write_text(json.dumps({
        "schema": "legacy-up-events/v1",
        "status": "read-only-historical",
        "source_event_count": len(events),
        "source_ledger_sha256": "a" * 64,
        "active_ledger_at_capture_sha256": hashlib.sha256(active).hexdigest(),
        "active_ledger_event_count_at_capture": len(active.splitlines()),
        "archive_sha256": hashlib.sha256(raw).hexdigest(),
        "event_count": len(events),
    }))
    return active_path, archive_path, manifest_path


def test_historical_status_reports_recorded_standing_and_exact_lineage(tmp_path):
    start = _row("start", "run_started", run_id="run-1", recorded_at_utc="2026-10-17T23:59:59Z")
    events = [
        _row("opened", "blocker_opened", run_id="run-1", blocker_id="blocker-1", status="open"),
        _row("fixed", "blocker_transitioned", run_id="run-1", blocker_id="blocker-1",
             from_status="open", to_status="fixed-awaiting-verification"),
        _row("closed", "run_closed", run_id="run-1", result="failed"),
    ]
    active_path, archive_path, manifest_path = _write_status_archive(tmp_path / "state", start, events)
    result = reconcile.historical_status(
        active_path=active_path, archive_path=archive_path, manifest_path=manifest_path,
        run_id="run-1",
    )
    assert result["recorded_standing"] == "failed"
    assert result["authority"] == "historical-record-only"
    assert result["currently_proven_active_authority"] is False
    assert [item["event_id"] for item in result["event_lineage"]] == ["start", "opened", "fixed", "closed"]
    assert result["event_lineage"][-1]["recorded_result"] == "failed"

    blocker = reconcile.historical_status(
        active_path=active_path, archive_path=archive_path, manifest_path=manifest_path,
        blocker_id="blocker-1",
    )
    assert blocker["recorded_standing"] == "fixed-awaiting-verification"
    assert [item["event_id"] for item in blocker["event_lineage"]] == ["opened", "fixed"]


def test_historical_status_refuses_corrupt_archive_or_conflicting_active_id(tmp_path):
    event = _row("event-1", "run_started", run_id="run-1")
    active_path, archive_path, manifest_path = _write_status_archive(tmp_path / "state", b"", [event])
    archive_path.write_bytes(archive_path.read_bytes() + b"tampered")
    with pytest.raises((ValueError, gzip.BadGzipFile, EOFError)):
        reconcile.historical_status(
            active_path=active_path, archive_path=archive_path, manifest_path=manifest_path,
            run_id="run-1",
        )

    active = _row("event-1", "run_started", run_id="different-run")
    active_path, archive_path, manifest_path = _write_status_archive(
        tmp_path / "conflict", active, [event],
    )
    with pytest.raises(ValueError, match="conflicts with active ledger"):
        reconcile.historical_status(
            active_path=active_path, archive_path=archive_path, manifest_path=manifest_path,
            run_id="run-1",
        )


def test_supported_blocker_catalog_cli_reads_historical_status_without_ledger_mutation(tmp_path):
    repo = tmp_path / "repo"
    state = repo / "operations/work-memory"
    state.mkdir(parents=True)
    active_path = state / "events.jsonl"
    shutil.copyfile(reconcile.ACTIVE, active_path)
    history = state / "legacy-up-20261018"
    history.mkdir()
    shutil.copyfile(reconcile.ARCHIVE, history / "events.jsonl.gz")
    shutil.copyfile(reconcile.MANIFEST, history / "manifest.json")
    before = hashlib.sha256(active_path.read_bytes()).hexdigest()
    script = Path(reconcile.__file__).resolve().with_name("blocker_catalog.py")
    proc = subprocess.run(
        [sys.executable, str(script), "--root", str(repo), "historical-status", "--run-id",
         "f3370f8a-b27e-4ba1-aa67-5053752f2778"],
        check=True, capture_output=True, text=True,
    )
    result = json.loads(proc.stdout)
    assert result["recorded_standing"] == "failed"
    assert result["currently_proven_active_authority"] is False
    assert [event["event_id"] for event in result["event_lineage"]] == [
        "6d76e809-b256-476c-98ca-b4eaf01708ed",
        "d2fe1e11-a490-4565-b060-5c749b8ab5d2",
        "e75e615a-250a-4b96-bb69-9d5f5241e356",
        "a0864056-3cf9-405e-b311-3417d71e2de5",
        "08ff38f8-0af1-4da2-a818-1288eab3e3fb",
        "bbfeda00-f149-43a8-b541-1db8b4e9c85a",
    ]
    assert not (repo / "source.jsonl").exists()
    assert hashlib.sha256(active_path.read_bytes()).hexdigest() == before
    mixed = subprocess.run(
        [sys.executable, str(script), "--root", str(repo), "historical-status", "--run-id",
         "0af58b5c-48e4-4e6c-ba21-6b88564ef11b"],
        check=True, capture_output=True, text=True,
    )
    mixed_result = json.loads(mixed.stdout)
    assert mixed_result["recorded_standing"] == "passed"
    assert [(item["event_id"], item["source"]) for item in mixed_result["event_lineage"]] == [
        ("d2c73d83-368b-40e3-868d-53dd379a5583", "active-ledger"),
        ("44eddc9f-e54b-4198-a301-3170f7dc3109", "legacy-up-archive"),
        ("625437fc-c2ff-407b-b518-c6d533eaa28a", "legacy-up-archive"),
    ]
    step3 = subprocess.run(
        [sys.executable, str(script), "--root", str(repo), "historical-status", "--blocker-id",
         "blk-9923ee5cbcbfd8e1ccec3923"],
        check=True, capture_output=True, text=True,
    )
    step3_result = json.loads(step3.stdout)
    assert step3_result["recorded_standing"] == "closed"
    assert step3_result["authority"] == "historical-record-only"
    step3_lineage = {item["event_id"]: item for item in step3_result["event_lineage"]}
    assert "acad156c-e043-4d3a-9842-002ec8277536" in step3_lineage
    assert step3_lineage["acad156c-e043-4d3a-9842-002ec8277536"]["target_run_close_event_id"] == (
        "719f7c47-9a18-4d29-ac9c-52387a092270"
    )
    assert step3_lineage["719f7c47-9a18-4d29-ac9c-52387a092270"]["event_type"] == "run_closed"
    assert step3_lineage["719f7c47-9a18-4d29-ac9c-52387a092270"]["recorded_result"] == "passed"
    assert step3_lineage["719f7c47-9a18-4d29-ac9c-52387a092270"]["source"] == "legacy-up-archive"
    assert step3_lineage["acad156c-e043-4d3a-9842-002ec8277536"][
        "recorded_changed_artifact_hashes"
    ] == ["32d231c7fd8710543257b452a8fc34019ca58aefe6121c32bcb205b5e9a14a87"]
    assert step3_lineage["acad156c-e043-4d3a-9842-002ec8277536"][
        "recorded_evidence_artifacts"
    ][0]["sha256"] == "06b3f6827a8a3565f39a98c678676b4d9d0b0f69d3b0711e3fb22a01a1d491c3"
    assert step3_lineage["d0d6a1dd-0b05-4256-b043-42b37138f6f2"][
        "verification_event_id"
    ] == "acad156c-e043-4d3a-9842-002ec8277536"
    assert step3_lineage["9d87b18d-0d6d-4776-a96f-3d33c2e98b54"][
        "verification_event_id"
    ] == "acad156c-e043-4d3a-9842-002ec8277536"
    step2_blockers = [
        "blk-ad2c27b95dc8ce7c21c008a6",
        "blk-8305170ab478d6a1f02dbb4c",
        "blk-a7680a7b05180a268a8749c5",
        "blk-e102e3dacb61a03f5b9a8deb",
    ]
    for blocker_id in step2_blockers:
        prior_step = reconcile.historical_status(
            active_path=active_path,
            archive_path=history / "events.jsonl.gz",
            manifest_path=history / "manifest.json",
            blocker_id=blocker_id,
        )
        assert prior_step["recorded_standing"] == "closed"
        audit = next(
            item for item in prior_step["event_lineage"]
            if item["event_id"] == "595fc73f-4ccc-4792-aa90-7567ef263381"
        )
        assert audit["target_run_close_event_id"] == "1b788950-211f-4824-a84a-52c8fe2588bd"
        run_close = next(
            item for item in prior_step["event_lineage"]
            if item["event_id"] == audit["target_run_close_event_id"]
        )
        assert run_close["event_type"] == "run_closed"
        assert run_close["recorded_result"] == "passed"
        assert run_close["source"] == "legacy-up-archive"
        assert audit["recorded_correction_ids"]
