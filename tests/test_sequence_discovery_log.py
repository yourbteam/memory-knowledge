from __future__ import annotations

import json
from pathlib import Path
import uuid

import pytest

from scripts import sequence_discovery_log, work_memory
from scripts.sequence_discovery_log import main


def test_start_creates_discovery_log_with_stable_name(tmp_path: Path) -> None:
    result = main(
        [
            "start",
            "--sequence-name",
            "Missing Sequence Smoke",
            "--outcome",
            "Prove the missing-sequence branch records a file.",
            "--why-repeatable",
            "This is the path used when no registered sequence matches.",
            "--root",
            str(tmp_path),
            "--date",
            "2026-06-22",
        ]
    )

    assert result == 0
    log_path = tmp_path / "operations/sequences/discovery/2026-06-22-missing-sequence-smoke.md"
    text = log_path.read_text(encoding="utf-8")
    assert "RegisteredSequenceMatch: none" in text
    assert "Prove the missing-sequence branch records a file." in text
    assert "This is the path used when no registered sequence matches." in text
    assert "python3 scripts/work_memory.py correct" in text
    assert "python3 scripts/work_memory_bootstrap.py correct" in text
    assert "python3 scripts/work_memory_bootstrap_launcher.py correct" in text


def test_renderer_injects_each_canonical_recovery_row_once(tmp_path: Path) -> None:
    _, text, _ = sequence_discovery_log.render_discovery_bundle(
        root=tmp_path,
        date_text="2026-07-16",
        sequence_name="Recovery Contract",
        outcome="Remain recoverable after selected-bundle drift.",
        why_repeatable="Every generated discovery may need correction.",
        created_at_utc="2026-07-16T00:00:00Z",
        steps=[dict(sequence_discovery_log.RECOVERY_STEPS[0])],
    )

    for row in sequence_discovery_log.RECOVERY_STEPS:
        assert text.count(row["command"]) == 1


def test_start_legacy_output_matches_reusable_renderer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(work_memory, "utc_now", lambda: "2026-07-15T00:00:00Z")
    assert main([
        "start", "--sequence-name", "Legacy Bytes", "--outcome", "Stay compatible.",
        "--why-repeatable", "Existing callers depend on this output.",
        "--root", str(tmp_path), "--date", "2026-07-15",
    ]) == 0
    path = tmp_path / "operations/sequences/discovery/2026-07-15-legacy-bytes.md"
    _, expected, manifest = sequence_discovery_log.render_discovery_bundle(
        root=tmp_path, date_text="2026-07-15", sequence_name="Legacy Bytes",
        outcome="Stay compatible.",
        why_repeatable="Existing callers depend on this output.",
        created_at_utc="2026-07-15T00:00:00Z",
    )
    assert path.read_bytes() == expected.encode()
    assert json.loads(path.with_suffix(".dependencies.json").read_text()) == manifest


def test_first_metadata_insert_preserves_semantic_discovery_bytes(tmp_path: Path) -> None:
    main([
        "start", "--sequence-name", "Metadata Insert", "--outcome", "Stay stable.",
        "--why-repeatable", "Readiness metadata is refreshed repeatedly.",
        "--root", str(tmp_path), "--date", "2026-07-15",
    ])
    path = tmp_path / "operations/sequences/discovery/2026-07-15-metadata-insert.md"
    before = work_memory.semantic_discovery_bytes(path)

    text = sequence_discovery_log._replace_metadata(
        path.read_text(encoding="utf-8"), "ReadyAtUtc", "2026-07-15T00:00:00Z",
    )
    path.write_text(text, encoding="utf-8")

    assert work_memory.semantic_discovery_bytes(path) == before


def test_discovery_state_bundle_includes_selection_trust_anchors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert main([
        "start", "--sequence-name", "Bundle Contract", "--outcome", "Match selection.",
        "--why-repeatable", "Readiness must count selected runs.",
        "--root", str(tmp_path), "--date", "2026-07-15",
    ]) == 0
    path = tmp_path / "operations/sequences/discovery/2026-07-15-bundle-contract.md"
    captured: dict[str, object] = {}

    def resolve_bundle(**kwargs):
        captured.update(kwargs)
        return [], "a" * 64, "discovery-example"

    monkeypatch.setattr(work_memory, "resolve_bundle", resolve_bundle)
    sequence_discovery_log._bundle(path)

    assert captured["include_bootstrap_trust_anchors"] is True


def test_append_step_records_command_result(tmp_path: Path) -> None:
    main(
        [
            "start",
            "--sequence-name",
            "Missing Sequence Smoke",
            "--outcome",
            "Prove the missing-sequence branch records a file.",
            "--why-repeatable",
            "This is the path used when no registered sequence matches.",
            "--root",
            str(tmp_path),
            "--date",
            "2026-06-22",
        ]
    )
    log_path = tmp_path / "operations/sequences/discovery/2026-06-22-missing-sequence-smoke.md"

    result = main(
        [
            "append-step",
            "--file",
            str(log_path),
            "--step",
            "Confirm registry",
            "--command",
            "test -f operations/sequences/SEQUENCES.md",
            "--result",
            "passed",
            "--note",
            "registry exists",
        ]
    )

    assert result == 0
    text = log_path.read_text(encoding="utf-8")
    assert "| Confirm registry | test -f operations/sequences/SEQUENCES.md | passed | registry exists |" in text


def test_recurred_blocker_prevents_discovery_readiness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    main([
        "start", "--sequence-name", "Recurring", "--outcome", "Run safely.",
        "--why-repeatable", "It recurs.", "--root", str(tmp_path), "--date", "2026-01-01",
    ])
    path = tmp_path / "operations/sequences/discovery/2026-01-01-recurring.md"
    discovery_id = next(
        line.split(":", 1)[1].strip() for line in path.read_text().splitlines()
        if line.startswith("DiscoveryId:")
    )
    run_one, run_two = str(uuid.uuid4()), str(uuid.uuid4())
    blocker_id = "blk-" + "1" * 24
    events = [
        {"event_type": "run_started", "run_id": run_one, "mode": "discovery",
         "subject_id": discovery_id, "source_bundle_hash": "a" * 64},
        {"event_type": "blocker_opened", "run_id": run_one, "blocker_id": blocker_id,
         "lineage_id": discovery_id},
        {"event_type": "blocker_transitioned", "run_id": run_one, "blocker_id": blocker_id,
         "to_status": "closed"},
        {"event_type": "run_started", "run_id": run_two, "mode": "discovery",
         "subject_id": discovery_id, "source_bundle_hash": "a" * 64},
        {"event_type": "blocker_recurred", "run_id": run_two, "blocker_id": blocker_id},
    ]
    monkeypatch.setattr(
        sequence_discovery_log,
        "_bundle",
        lambda path, repo_roots_file=None: ([], "a" * 64, discovery_id),
    )
    monkeypatch.setattr(work_memory, "load_ledger", lambda: (events, "b" * 64))
    state = sequence_discovery_log.discovery_state(path)
    assert blocker_id in state["open_blocker_ids"]
    assert "open-blockers" in state["unmet_predicates"]


def test_discovery_commands_resolve_cross_repository_dependencies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    memory_root = tmp_path / "memory-knowledge"
    external_root = tmp_path / "workflow-orch"
    dependency = external_root / "scripts" / "proof.py"
    dependency.parent.mkdir(parents=True)
    dependency.write_text("print('proof')\n", encoding="utf-8")
    roots_file = tmp_path / "repositories.json"
    roots_file.write_text(
        json.dumps({"workflow-orch": str(external_root)}), encoding="utf-8",
    )
    monkeypatch.setattr(work_memory, "ROOT", memory_root)
    for relative in work_memory.BOOTSTRAP_TRUST_ANCHORS:
        anchor = memory_root / relative
        anchor.parent.mkdir(parents=True, exist_ok=True)
        anchor.write_text(f"# {relative}\n", encoding="utf-8")

    assert main([
        "start", "--sequence-name", "Cross Repository", "--outcome", "Resolve dependencies.",
        "--why-repeatable", "The sequence spans repositories.", "--root", str(memory_root),
        "--date", "2026-07-15",
    ]) == 0
    capsys.readouterr()
    path = memory_root / "operations/sequences/discovery/2026-07-15-cross-repository.md"
    discovery_id = next(
        line.split(":", 1)[1].strip() for line in path.read_text().splitlines()
        if line.startswith("DiscoveryId:")
    )
    source_manifest = tmp_path / "dependencies.json"
    source_manifest.write_text(json.dumps({
        "schema_version": 1,
        "lineage_id": discovery_id,
        "dependencies": [{
            "kind": "file",
            "repository_key": "workflow-orch",
            "path_or_sequence_id": "scripts/proof.py",
        }],
    }), encoding="utf-8")

    assert main([
        "set-dependencies", "--file", str(path),
        "--dependencies-json", str(source_manifest),
        "--repo-roots-file", str(roots_file),
    ]) == 0
    set_dependencies = json.loads(capsys.readouterr().out)
    assert set_dependencies["ok"] is True
    _, bundle_hash, _ = sequence_discovery_log._bundle(
        path, repo_roots_file=str(roots_file),
    )
    run_ids = [str(uuid.uuid4())]
    events = []
    for index, run_id in enumerate(run_ids, start=1):
        events.extend([
            {"event_type": "run_started", "run_id": run_id, "mode": "discovery",
             "subject_id": discovery_id, "source_bundle_hash": bundle_hash},
            {"event_type": "verification_recorded", "run_id": run_id,
             "subject_id": discovery_id, "source_bundle_hash": bundle_hash,
             "outcome": "passed", "quality": "same-path"},
            {"event_type": "run_closed", "run_id": run_id,
             "subject_id": discovery_id, "result": "passed",
             "completed_at_utc": f"2026-07-1{index}T00:00:00Z"},
        ])
    monkeypatch.setattr(work_memory, "load_ledger", lambda: (events, "b" * 64))

    for argv in (
        ["check", "--file", str(path), "--repo-roots-file", str(roots_file)],
        ["closeout", "--file", str(path), "--repo-roots-file", str(roots_file)],
        ["backlog", "--root", str(memory_root), "--repo-roots-file", str(roots_file)],
    ):
        assert main(argv) == 0
        result = json.loads(capsys.readouterr().out)
        assert result["ok"] is True
        if argv[0] == "backlog":
            assert result["records"][0]["status"] != "invalid"
