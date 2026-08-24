from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import discovery_promotion_lifecycle as lifecycle
from scripts import prevention_source_receipt


def test_registered_document_grounds_protected_correction_commands() -> None:
    document = (
        Path(__file__).parents[1]
        / "operations/sequences/discovery-promotion-lifecycle/sequence.md"
    ).read_text()
    assert "python3 scripts/work_memory_bootstrap_launcher.py correct" in document
    assert "python3 scripts/work_memory_bootstrap.py correct" in document


def discovery(path: Path, *, status: str = "discovery") -> Path:
    path.write_text(f"""# Sequence Discovery Log: example

DiscoveryId: discovery-example
Status: {status}
CreatedAtUtc: 2026-07-15T00:00:00Z
RegisteredSequenceMatch: none

## Intended Outcome

Example.

## Why This Looks Repeatable

It recurs.

## Required Inputs, Auth, Or Environment

- input

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| verify-automation | uv run pytest tests/test_example.py | passed | exact path |

## Failure Handling

Stop.

## Verified Path

- Passed.

## Promotion Readiness

- [x] Commands are stable enough to script or document.
- [x] Required inputs are known.
- [x] Failure handling is known.
- [x] Verification evidence is known.
- [x] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
""")
    return path


def test_verification_command_is_extracted_without_shell(tmp_path: Path) -> None:
    path = discovery(tmp_path / "discovery.md")
    assert lifecycle._verification_command(path) == "uv run pytest tests/test_example.py"


def test_verification_command_rejects_runtime_placeholders(tmp_path: Path) -> None:
    path = discovery(tmp_path / "discovery.md")
    path.write_text(path.read_text().replace("tests/test_example.py", "<test-path>"))
    with pytest.raises(lifecycle.LifecycleError, match="verification-command-has-placeholders"):
        lifecycle._verification_command(path)


def test_drive_follows_qualification_promotion_registered_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = discovery(tmp_path / "discovery.md")
    stages = iter(["qualification", "qualification", "promotion", "registered-verification", "complete"])
    monkeypatch.setattr(lifecycle, "cmd_status", lambda args: {
        "stage": next(stages), "state": {"discovery_id": "discovery-example"},
    })
    qualified = []
    monkeypatch.setattr(lifecycle, "_qualify_once", lambda args, state: qualified.append(state) or {"run_id": str(len(qualified))})
    promoted = []
    monkeypatch.setattr(lifecycle, "_promote", lambda args, root: promoted.append(args.sequence_id) or {})
    registered = []
    monkeypatch.setattr(lifecycle, "_verify_registered", lambda args, root: registered.append(args.sequence_id) or {})
    args = lifecycle.build_parser().parse_args([
        "drive", "--file", str(path), "--sequence-id", "example",
        "--use-when", "example", "--operation-kind", "other",
        "--automation-display", "controller", "--pass-signal", "PASS",
        "--root", str(tmp_path),
    ])
    result = lifecycle.cmd_drive(args)
    assert result["stage"] == "complete"
    assert len(qualified) == 2 and promoted == ["example"] and registered == ["example"]


def test_drive_persists_source_owned_effect_identity_before_lifecycle_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = discovery(tmp_path / "discovery.md")
    stages = iter(["promotion", "complete"])
    monkeypatch.setattr(lifecycle, "cmd_status", lambda args: {
        "stage": next(stages), "state": {"discovery_id": "discovery-example"},
    })
    monkeypatch.setattr(lifecycle, "_promote", lambda args, root: {})
    monkeypatch.setattr(prevention_source_receipt, "ROOT", tmp_path / "receipts")

    returncode = lifecycle.main([
        "drive", "--file", str(path), "--sequence-id", "example",
        "--use-when", "example", "--operation-kind", "other",
        "--automation-display", "controller", "--pass-signal", "PASS",
        "--root", str(tmp_path),
        "--prevention-effect-id", "e" * 64,
        "--prevention-preparation-sha256", "f" * 64,
    ])

    result = json.loads(capsys.readouterr().out)
    receipt = json.loads(
        prevention_source_receipt.receipt_path("e" * 64).read_text(encoding="utf-8")
    )
    assert returncode == 0
    assert receipt["status"] == "APPLIED"
    assert receipt["profile_id"] == "drive"
    assert receipt["result_identity"]["stage"] == "complete"
    assert "next_stage" not in receipt["result_identity"]
    assert result["preventionSourceReceiptSha256"] == (
        prevention_source_receipt.receipt_sha256(receipt)
    )


def test_drive_declares_bootstrap_readiness_before_qualification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = discovery(tmp_path / "discovery.md")
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "CreatedAtUtc: 2026-07-15T00:00:00Z\n",
        "CreatedAtUtc: 2026-07-15T00:00:00Z\nBootstrapRequestSha256: " + "a" * 64 + "\n",
    ).replace("- [x]", "- [ ]")
    path.write_text(text, encoding="utf-8")
    statuses = iter([
        {
            "stage": "qualification",
            "state": {
                "discovery_id": "discovery-example",
                "unmet_predicates": ["two-same-path-successes", "readiness"],
            },
        },
        {
            "stage": "qualification",
            "state": {
                "discovery_id": "discovery-example",
                "unmet_predicates": ["two-same-path-successes"],
            },
        },
        {"stage": "promotion", "state": {"discovery_id": "discovery-example"}},
        {"stage": "registered-verification", "state": {"discovery_id": "discovery-example"}},
        {"stage": "complete", "state": {"discovery_id": "discovery-example"}},
    ])
    monkeypatch.setattr(lifecycle, "cmd_status", lambda args: next(statuses))
    commands = []
    monkeypatch.setattr(
        lifecycle, "_json_command",
        lambda command, *, root: commands.append(command) or {"ok": True},
    )
    qualified = []
    monkeypatch.setattr(
        lifecycle, "_qualify_once",
        lambda args, state: qualified.append(state) or {"run_id": "run-one"},
    )
    monkeypatch.setattr(lifecycle, "_promote", lambda args, root: {})
    monkeypatch.setattr(lifecycle, "_verify_registered", lambda args, root: {})
    args = lifecycle.build_parser().parse_args([
        "drive", "--file", str(path), "--sequence-id", "example",
        "--use-when", "example", "--operation-kind", "other",
        "--automation-display", "controller", "--pass-signal", "PASS",
        "--root", str(tmp_path),
    ])

    assert lifecycle.cmd_drive(args)["stage"] == "complete"
    readiness_commands = [command for command in commands if "set-readiness" in command]
    assert len(readiness_commands) == len(lifecycle.sequence_discovery_log.READINESS)
    assert [command[command.index("--item") + 1] for command in readiness_commands] == sorted(
        lifecycle.sequence_discovery_log.READINESS
    )
    assert len(qualified) == 1


def test_readiness_declaration_requires_bootstrap_proven_discovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = discovery(tmp_path / "discovery.md")
    commands = []
    monkeypatch.setattr(
        lifecycle, "_json_command",
        lambda command, *, root: commands.append(command) or {"ok": True},
    )
    args = lifecycle.build_parser().parse_args([
        "drive", "--file", str(path), "--sequence-id", "example",
        "--use-when", "example", "--operation-kind", "other",
        "--automation-display", "controller", "--pass-signal", "PASS",
        "--root", str(tmp_path),
    ])

    assert lifecycle._declare_bootstrap_readiness(
        args,
        {"unmet_predicates": ["two-same-path-successes", "readiness"]},
        root=tmp_path,
    ) is False
    assert commands == []


def test_readiness_declaration_rejects_other_structural_gaps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = discovery(tmp_path / "discovery.md")
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "CreatedAtUtc: 2026-07-15T00:00:00Z\n",
            "CreatedAtUtc: 2026-07-15T00:00:00Z\nBootstrapRequestSha256: " + "a" * 64 + "\n",
        ),
        encoding="utf-8",
    )
    commands = []
    monkeypatch.setattr(
        lifecycle, "_json_command",
        lambda command, *, root: commands.append(command) or {"ok": True},
    )
    args = lifecycle.build_parser().parse_args([
        "drive", "--file", str(path), "--sequence-id", "example",
        "--use-when", "example", "--operation-kind", "other",
        "--automation-display", "controller", "--pass-signal", "PASS",
        "--root", str(tmp_path),
    ])

    assert lifecycle._declare_bootstrap_readiness(
        args,
        {"unmet_predicates": ["inputs", "readiness"]},
        root=tmp_path,
    ) is False
    assert commands == []


def test_registered_verification_uses_selection_trust_anchor_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path
    document = root / "operations/sequences/example/sequence.md"
    document.parent.mkdir(parents=True)
    document.write_text("# example\n", encoding="utf-8")
    document.with_name("dependencies.json").write_text("{}\n", encoding="utf-8")
    captured = {}
    monkeypatch.setattr(lifecycle.work_memory, "ROOT", root)

    def resolve_bundle(**kwargs):
        captured.update(kwargs)
        return [], "a" * 64, "lineage-example"

    monkeypatch.setattr(lifecycle.work_memory, "resolve_bundle", resolve_bundle)
    monkeypatch.setattr(lifecycle.work_memory, "load_ledger", lambda: ([], "b" * 64))

    assert lifecycle._registered_verified("example", repo_roots_file=None) is False
    assert captured["include_bootstrap_trust_anchors"] is True


def test_drive_stops_when_correction_is_required(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = discovery(tmp_path / "discovery.md")
    monkeypatch.setattr(lifecycle, "cmd_status", lambda args: {
        "stage": "correction-required", "state": {"open_blocker_ids": ["blk-one"]},
    })
    args = lifecycle.build_parser().parse_args([
        "drive", "--file", str(path), "--sequence-id", "example",
        "--use-when", "example", "--operation-kind", "other",
        "--automation-display", "controller", "--pass-signal", "PASS",
        "--root", str(tmp_path),
    ])
    with pytest.raises(lifecycle.LifecycleError, match="correction-required") as exc:
        lifecycle.cmd_drive(args)
    assert exc.value.details["open_blocker_ids"] == ["blk-one"]


def test_promoted_registered_blocker_takes_precedence_over_prior_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = discovery(tmp_path / "discovery.md", status="promoted")
    monkeypatch.setattr(lifecycle.sequence_discovery_log, "discovery_state", lambda *args, **kwargs: {
        "status": "promoted", "discovery_id": "discovery-example", "open_blocker_ids": [],
    })
    monkeypatch.setattr(
        lifecycle, "_pending_correction",
        lambda subject_id: lifecycle.PendingCorrection(
            blocker_id="blk-old", correction_id="correction-old",
            predecessor_run_id="run-old", task_id="task-old",
        ),
    )
    monkeypatch.setattr(lifecycle, "_open_blocker_ids", lambda subject_id: ["blk-registered"])
    monkeypatch.setattr(lifecycle, "_registered_verified", lambda *args, **kwargs: True)
    args = lifecycle.build_parser().parse_args([
        "status", "--file", str(path), "--sequence-id", "example",
    ])

    result = lifecycle.cmd_status(args)

    assert result["stage"] == "correction-required"
    assert result["state"]["open_blocker_ids"] == ["blk-registered"]


def test_registered_pending_correction_routes_to_registered_successor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = discovery(tmp_path / "discovery.md")
    stages = iter(["registered-successor-verification", "complete"])
    monkeypatch.setattr(lifecycle, "cmd_status", lambda args: {
        "stage": next(stages), "state": {"discovery_id": "discovery-example"},
    })
    registered = []
    monkeypatch.setattr(
        lifecycle, "_verify_registered",
        lambda args, root: registered.append(args.sequence_id) or {},
    )
    monkeypatch.setattr(
        lifecycle, "_qualify_once",
        lambda *args, **kwargs: pytest.fail("discovery qualifier must not run"),
    )
    args = lifecycle.build_parser().parse_args([
        "drive", "--file", str(path), "--sequence-id", "example",
        "--use-when", "example", "--operation-kind", "other",
        "--automation-display", "controller", "--pass-signal", "PASS",
        "--root", str(tmp_path),
    ])

    assert lifecycle.cmd_drive(args)["stage"] == "complete"
    assert registered == ["example"]


def test_registered_successor_reuses_pending_correction_task_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    sequence = tmp_path / "operations/sequences/example/sequence.md"
    sequence.parent.mkdir(parents=True)
    sequence.write_text(
        "| verify-automation | python3 -m pytest | passed | exact |\n"
    )
    pending = lifecycle.PendingCorrection(
        blocker_id="blk-one", correction_id="correction-one",
        predecessor_run_id="run-old", task_id="correction-task",
    )
    monkeypatch.setattr(lifecycle, "_registered_verified", lambda *args, **kwargs: False)
    monkeypatch.setattr(lifecycle, "_pending_correction", lambda subject_id: pending)
    classified = []
    selected = {}
    monkeypatch.setattr(
        lifecycle, "_classify",
        lambda task_id, **kwargs: classified.append(task_id),
    )
    monkeypatch.setattr(
        lifecycle, "_select_and_start",
        lambda **kwargs: selected.update(kwargs) or ("run-new", {
            "verifies_correction_ids": ["correction-one"],
            "relevant_blocker_ids": ["blk-one"],
        }),
    )
    monkeypatch.setattr(
        lifecycle, "_verify_run",
        lambda **kwargs: {"run_id": kwargs["run_id"]},
    )
    args = lifecycle.build_parser().parse_args([
        "drive", "--file", str(tmp_path / "discovery.md"),
        "--sequence-id", "example", "--use-when", "example",
        "--operation-kind", "workflow-drive",
        "--automation-display", "controller", "--pass-signal", "PASS",
        "--root", str(tmp_path),
    ])

    lifecycle._verify_registered(args, root=tmp_path)

    assert classified == ["correction-task"]
    assert selected["task_id"] == "correction-task"
    assert selected["pending"] == pending


def test_status_allows_controller_to_bootstrap_an_unbound_discovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = discovery(tmp_path / "discovery.md")
    observed = {}

    def state(document, **kwargs):
        observed.update(kwargs)
        return {
            "status": "discovery", "discovery_id": "discovery-example",
            "open_blocker_ids": [],
        }

    monkeypatch.setattr(lifecycle.sequence_discovery_log, "discovery_state", state)
    monkeypatch.setattr(lifecycle, "_pending_correction", lambda discovery_id: None)
    args = lifecycle.build_parser().parse_args([
        "status", "--file", str(path), "--sequence-id", "example",
    ])

    assert lifecycle.cmd_status(args)["stage"] == "qualification"
    assert observed["require_bound"] is False


def test_pending_correction_folds_transition_events_without_subject_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = [
        {
            "event_type": "run_started", "subject_id": "legacy-sequence",
            "lineage_id": "legacy-lineage", "run_id": "legacy-run",
        },
        {
            "event_type": "run_started", "subject_id": "discovery-example",
            "lineage_id": "discovery-example", "run_id": "run-one",
            "task_id": "task-one",
        },
        {
            "event_type": "blocker_opened", "subject_id": "discovery-example",
            "lineage_id": "discovery-example", "blocker_id": "blk-one",
            "run_id": "run-one",
        },
        {
            "event_type": "correction_recorded", "subject_id": "discovery-example",
            "lineage_id": "discovery-example", "blocker_id": "blk-one",
            "run_id": "run-one", "correction_id": "correction-one",
        },
        {
            "event_type": "blocker_transitioned", "blocker_id": "blk-one",
            "run_id": "run-one", "to_status": "fixed-awaiting-verification",
        },
    ]
    monkeypatch.setattr(lifecycle.work_memory, "load_ledger", lambda: (events, "a" * 64))

    assert lifecycle._pending_correction("discovery-example") == lifecycle.PendingCorrection(
        blocker_id="blk-one", correction_id="correction-one",
        predecessor_run_id="run-one", task_id="task-one",
    )


def test_pending_correction_ignores_correction_with_passed_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = [
        {
            "event_type": "run_started", "subject_id": "discovery-example",
            "lineage_id": "discovery-example", "run_id": "legacy-run",
        },
        {
            "event_type": "blocker_opened", "subject_id": "discovery-example",
            "lineage_id": "discovery-example", "blocker_id": "blk-one",
            "run_id": "legacy-run",
        },
        {
            "event_type": "correction_recorded", "subject_id": "discovery-example",
            "lineage_id": "discovery-example", "blocker_id": "blk-one",
            "run_id": "legacy-run", "correction_id": "correction-one",
        },
        {
            "event_type": "blocker_transitioned", "blocker_id": "blk-one",
            "run_id": "legacy-run", "to_status": "fixed-awaiting-verification",
        },
        {
            "event_type": "verification_recorded", "subject_id": "discovery-example",
            "lineage_id": "discovery-example", "run_id": "successor-run",
            "correction_ids": ["correction-one"], "outcome": "passed",
            "quality": "same-path",
        },
    ]
    monkeypatch.setattr(lifecycle.work_memory, "load_ledger", lambda: (events, "a" * 64))

    assert lifecycle._pending_correction("discovery-example") is None


def test_pending_correction_groups_same_predecessor_co_corrections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = [{
        "event_type": "run_started", "subject_id": "discovery-example",
        "lineage_id": "discovery-example", "run_id": "run-one",
        "task_id": "task-one",
    }]
    for blocker_id, correction_id in (
        ("blk-one", "correction-one"),
        ("blk-two", "correction-two"),
    ):
        events.extend([
            {
                "event_type": "blocker_opened",
                "subject_id": "discovery-example",
                "lineage_id": "discovery-example",
                "blocker_id": blocker_id, "run_id": "run-one",
            },
            {
                "event_type": "correction_recorded",
                "subject_id": "discovery-example",
                "lineage_id": "discovery-example",
                "blocker_id": blocker_id, "run_id": "run-one",
                "correction_id": correction_id,
            },
            {
                "event_type": "blocker_transitioned",
                "blocker_id": blocker_id, "run_id": "run-one",
                "to_status": "fixed-awaiting-verification",
            },
        ])
    monkeypatch.setattr(lifecycle.work_memory, "load_ledger", lambda: (events, "a" * 64))

    pending = lifecycle._pending_correction("discovery-example")

    assert pending is not None
    assert pending.pairs == (
        ("blk-one", "correction-one"),
        ("blk-two", "correction-two"),
    )


def test_successor_verification_records_and_closes_complete_correction_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = tmp_path / "sequence.md"
    document.write_text("# sequence\n")
    pending = lifecycle.PendingCorrection(
        blocker_id="blk-one", correction_id="correction-one",
        predecessor_run_id="run-old", task_id="task-one",
        co_corrections=(("blk-two", "correction-two"),),
    )
    monkeypatch.setattr(
        lifecycle, "_guard_and_verify",
        lambda **kwargs: type("Completed", (), {"returncode": 0})(),
    )
    monkeypatch.setattr(lifecycle, "_pending_correction", lambda subject_id: pending)
    commands = []

    def run(command, *, root):
        commands.append(command)
        return {"event_id": "verification-one"} if "verify" in command else {"ok": True}

    monkeypatch.setattr(lifecycle, "_json_command", run)

    lifecycle._verify_run(
        run_id="run-new",
        receipt={
            "verifies_correction_ids": ["correction-two", "correction-one"],
            "relevant_blocker_ids": ["blk-one", "blk-two"],
        },
        document=document,
        task_id="task-one",
        root=tmp_path,
        command="python3 -m pytest",
        source="sequence_doc",
        subject_id="discovery-example",
    )

    verify = commands[0]
    assert [
        verify[index + 1]
        for index, token in enumerate(verify[:-1])
        if token == "--blocker-id"
    ] == ["blk-one", "blk-two"]
    assert [
        verify[index + 1]
        for index, token in enumerate(verify[:-1])
        if token == "--correction-id"
    ] == ["correction-one", "correction-two"]
    transitions = [
        command for command in commands
        if "scripts/blocker_catalog.py" in command
    ]
    assert len(transitions) == 4
    assert all(
        "--remaining-work" in command
        for command in transitions
        if command[command.index("--to-status") + 1] == "closed"
    )


def test_qualification_reuses_pending_correction_task_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = discovery(tmp_path / "discovery.md")
    pending = lifecycle.PendingCorrection(
        blocker_id="blk-one", correction_id="correction-one",
        predecessor_run_id="run-one", task_id="bootstrap-task",
    )
    classified = []
    selected = {}
    monkeypatch.setattr(lifecycle, "_pending_correction", lambda subject_id: pending)
    monkeypatch.setattr(
        lifecycle, "_classify",
        lambda task_id, **kwargs: classified.append(task_id),
    )
    monkeypatch.setattr(
        lifecycle, "_select_and_start",
        lambda **kwargs: selected.update(kwargs) or ("run-two", {}),
    )
    monkeypatch.setattr(lifecycle, "_verify_run", lambda **kwargs: {"run_id": "run-two"})
    args = lifecycle.build_parser().parse_args([
        "drive", "--file", str(path), "--sequence-id", "example",
        "--use-when", "example", "--operation-kind", "other",
        "--automation-display", "controller", "--pass-signal", "PASS",
        "--root", str(tmp_path),
    ])

    assert lifecycle._qualify_once(
        args, {"discovery_id": "discovery-example"},
    ) == {"run_id": "run-two"}
    assert classified == ["bootstrap-task"]
    assert selected["task_id"] == "bootstrap-task"
    assert selected["pending"] == pending


def test_ordinary_qualification_keeps_generated_task_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = discovery(tmp_path / "discovery.md")
    selected = {}
    monkeypatch.setattr(lifecycle, "_pending_correction", lambda subject_id: None)
    monkeypatch.setattr(lifecycle, "_classify", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        lifecycle, "_select_and_start",
        lambda **kwargs: selected.update(kwargs) or ("run-one", {}),
    )
    monkeypatch.setattr(lifecycle, "_verify_run", lambda **kwargs: {"run_id": "run-one"})
    args = lifecycle.build_parser().parse_args([
        "drive", "--file", str(path), "--sequence-id", "example",
        "--use-when", "example", "--operation-kind", "other",
        "--automation-display", "controller", "--pass-signal", "PASS",
        "--root", str(tmp_path),
    ])

    lifecycle._qualify_once(args, {"discovery_id": "discovery-example"})

    assert selected["task_id"] == "discovery-promote-example-other"
    assert selected["pending"] is None


def test_pending_correction_ignores_explicitly_superseded_blocker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = [
        {
            "event_type": "blocker_opened", "subject_id": "discovery-example",
            "lineage_id": "discovery-example", "blocker_id": "blk-old",
            "run_id": "run-old",
        },
        {
            "event_type": "correction_recorded", "subject_id": "discovery-example",
            "lineage_id": "discovery-example", "blocker_id": "blk-old",
            "run_id": "run-old", "correction_id": "correction-old",
        },
        {
            "event_type": "blocker_transitioned", "blocker_id": "blk-old",
            "run_id": "run-new", "to_status": "superseded",
        },
    ]
    monkeypatch.setattr(lifecycle.work_memory, "load_ledger", lambda: (events, "a" * 64))
    assert lifecycle._pending_correction("discovery-example") is None


def test_correct_accepts_one_stable_artifact_manifest_argument(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lifecycle.work_memory, "ROOT", tmp_path)
    path = discovery(tmp_path / "discovery.md")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "scripts/one.py").write_text("# one\n")
    (tmp_path / "tests/test_one.py").write_text("# one\n")
    artifact_file = tmp_path / "artifacts.json"
    artifact_file.write_text(json.dumps([
        {"repository_key": "memory-knowledge", "path": "scripts/one.py"},
        {"repository_key": "memory-knowledge", "path": "tests/test_one.py"},
    ]))
    roots_file = tmp_path / "roots.json"
    roots_file.write_text(json.dumps({"memory-knowledge": str(tmp_path)}))
    events = [{
        "event_type": "blocker_opened", "subject_id": "discovery-example",
        "blocker_id": "blk-one", "occurrence_id": "occ-one", "run_id": "run-one",
        "step_id": "verify-automation",
    }]
    monkeypatch.setattr(lifecycle.work_memory, "load_ledger", lambda: (events, "a" * 64))
    commands = []

    def run(command, *, root):
        commands.append(command)
        if "correct" in command:
            return {"correction_id": "correction-one"}
        return {"ok": True}

    monkeypatch.setattr(lifecycle, "_json_command", run)
    args = lifecycle.build_parser().parse_args([
        "correct", "--file", str(path), "--sequence-id", "example",
        "--solution", "stable fix", "--changed-artifacts-file", str(artifact_file),
        "--reusable-behavior-changed", "yes", "--root", str(tmp_path),
        "--repo-roots-file", str(roots_file),
    ])

    assert lifecycle.cmd_correct(args)["next_stage"] == "successor-verification"
    correction = commands[0]
    assert correction.count("--changed-artifact") == 2
    assert str(tmp_path / "scripts/one.py") in correction
    assert str(tmp_path / "tests/test_one.py") in correction
    assert "--finalize-failed-run" in correction
    assert "--correction-id" in correction


def test_correct_carries_other_open_blockers_from_same_run_as_co_blockers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = discovery(tmp_path / "discovery.md")
    artifact = tmp_path / "fix.py"
    artifact.write_text("# fix\n")
    events = [
        {
            "event_type": "blocker_opened", "subject_id": "discovery-example",
            "blocker_id": "blk-primary", "occurrence_id": "occ-primary",
            "run_id": "run-one", "step_id": "verify-automation",
        },
        {
            "event_type": "blocker_opened", "subject_id": "discovery-example",
            "blocker_id": "blk-secondary", "occurrence_id": "occ-secondary",
            "run_id": "run-one", "step_id": "record-correction",
        },
    ]
    monkeypatch.setattr(lifecycle.work_memory, "load_ledger", lambda: (events, "a" * 64))
    commands = []
    monkeypatch.setattr(
        lifecycle, "_json_command",
        lambda command, *, root: commands.append(command) or {
            "correction_id": "correction-one",
        },
    )
    args = lifecycle.build_parser().parse_args([
        "correct", "--file", str(path), "--sequence-id", "example",
        "--solution", "stable fix", "--changed-artifact", str(artifact),
        "--reusable-behavior-changed", "yes", "--root", str(tmp_path),
    ])

    lifecycle.cmd_correct(args)

    command = commands[0]
    assert command[command.index("--blocker-id") + 1] == "blk-primary"
    assert command[command.index("--co-blocker-id") + 1] == "blk-secondary"


def test_registered_correction_forwards_repository_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "external"
    (repository / "scripts").mkdir(parents=True)
    (repository / "scripts/fix.py").write_text("# fix\n")
    artifact_file = tmp_path / "artifacts.json"
    artifact_file.write_text(json.dumps([
        {"repository_key": "external", "path": "scripts/fix.py"},
    ]))
    roots_file = tmp_path / "roots.json"
    roots_file.write_text(json.dumps({"external": str(repository)}))
    events = [{
        "event_type": "blocker_opened", "subject_id": "example",
        "blocker_id": "blk-one", "occurrence_id": "occ-one", "run_id": "run-one",
        "step_id": "verify-automation",
    }]
    monkeypatch.setattr(lifecycle.work_memory, "load_ledger", lambda: (events, "a" * 64))
    commands = []
    monkeypatch.setattr(
        lifecycle, "_json_command",
        lambda command, *, root: commands.append(command) or {"correction_id": "correction-one"},
    )
    args = lifecycle.build_parser().parse_args([
        "correct-registered", "--subject-id", "example", "--solution", "stable fix",
        "--changed-artifacts-file", str(artifact_file),
        "--reusable-behavior-changed", "yes", "--repo-roots-file", str(roots_file),
        "--root", str(tmp_path),
    ])

    lifecycle.cmd_correct_registered(args)

    command = commands[0]
    assert command[command.index("--repo-roots-file") + 1] == str(roots_file)


def test_protected_correction_routes_through_activated_bootstrap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lifecycle.work_memory, "ROOT", tmp_path)
    protected = tmp_path / "scripts/work_memory.py"
    protected.parent.mkdir()
    protected.write_text("# changed\n")
    artifact_file = tmp_path / "artifacts.json"
    artifact_file.write_text(json.dumps([
        {"repository_key": "memory-knowledge", "path": "scripts/work_memory.py"},
    ]))
    roots_file = tmp_path / "roots.json"
    roots_file.write_text(json.dumps({"memory-knowledge": str(tmp_path)}))
    events = [{
        "event_type": "blocker_opened", "subject_id": "example",
        "blocker_id": "blk-one", "occurrence_id": "occ-one", "run_id": "run-one",
        "step_id": "verify-automation",
    }]
    monkeypatch.setattr(lifecycle.work_memory, "load_ledger", lambda: (events, "a" * 64))
    commands = []
    monkeypatch.setattr(
        lifecycle, "_json_command",
        lambda command, *, root: commands.append(command) or {"correction_id": "correction-one"},
    )
    args = lifecycle.build_parser().parse_args([
        "correct-registered", "--subject-id", "example", "--task-id", "failed-task",
        "--solution", "stable fix", "--changed-artifacts-file", str(artifact_file),
        "--reusable-behavior-changed", "yes", "--root", str(tmp_path),
        "--repo-roots-file", str(roots_file),
    ])

    lifecycle.cmd_correct_registered(args)

    command = commands[0]
    assert command[1:3] == ["scripts/work_memory_bootstrap_launcher.py", "correct"]
    assert command[command.index("--task-id") + 1] == "failed-task"
    assert "--finalize-failed-run" not in command


def test_materialized_correction_rejects_unknown_repository_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = discovery(tmp_path / "discovery.md")
    artifact_file = tmp_path / "artifacts.json"
    artifact_file.write_text(json.dumps([
        {"repository_key": "unknown", "path": "scripts/fix.py"},
    ]))
    roots_file = tmp_path / "roots.json"
    roots_file.write_text(json.dumps({"memory-knowledge": str(tmp_path)}))
    events = [{
        "event_type": "blocker_opened", "subject_id": "discovery-example",
        "blocker_id": "blk-one", "occurrence_id": "occ-one", "run_id": "run-one",
        "step_id": "verify-automation",
    }]
    monkeypatch.setattr(lifecycle.work_memory, "load_ledger", lambda: (events, "a" * 64))
    args = lifecycle.build_parser().parse_args([
        "correct", "--file", str(path), "--sequence-id", "example",
        "--solution", "stable fix", "--changed-artifacts-file", str(artifact_file),
        "--reusable-behavior-changed", "yes", "--root", str(tmp_path),
        "--repo-roots-file", str(roots_file),
    ])

    with pytest.raises(lifecycle.LifecycleError, match="invalid-changed-artifact-identity"):
        lifecycle.cmd_correct(args)


def test_protected_correction_requires_failed_run_task_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    protected = tmp_path / "scripts/work_memory.py"
    protected.parent.mkdir()
    protected.write_text("# changed\n")
    events = [{
        "event_type": "blocker_opened", "subject_id": "example",
        "blocker_id": "blk-one", "occurrence_id": "occ-one", "run_id": "run-one",
        "step_id": "verify-automation",
    }]
    monkeypatch.setattr(lifecycle.work_memory, "load_ledger", lambda: (events, "a" * 64))
    args = lifecycle.build_parser().parse_args([
        "correct-registered", "--subject-id", "example", "--solution", "stable fix",
        "--changed-artifact", str(protected), "--reusable-behavior-changed", "yes",
        "--root", str(tmp_path),
    ])

    with pytest.raises(lifecycle.LifecycleError, match="task-id-required-for-protected-correction"):
        lifecycle.cmd_correct_registered(args)


def test_immutable_launcher_change_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    launcher_path = tmp_path / "scripts/work_memory_bootstrap_launcher.py"
    launcher_path.parent.mkdir()
    launcher_path.write_text("# changed\n")
    events = [{
        "event_type": "blocker_opened", "subject_id": "example",
        "blocker_id": "blk-one", "occurrence_id": "occ-one", "run_id": "run-one",
        "step_id": "verify-automation",
    }]
    monkeypatch.setattr(lifecycle.work_memory, "load_ledger", lambda: (events, "a" * 64))
    args = lifecycle.build_parser().parse_args([
        "correct-registered", "--subject-id", "example", "--task-id", "failed-task",
        "--solution", "launcher edit", "--changed-artifact", str(launcher_path),
        "--reusable-behavior-changed", "yes", "--root", str(tmp_path),
    ])

    with pytest.raises(lifecycle.LifecycleError, match="immutable-bootstrap-launcher-change"):
        lifecycle.cmd_correct_registered(args)


def test_verification_failure_is_cataloged_with_exact_run_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = discovery(tmp_path / "discovery.md")
    monkeypatch.setattr(lifecycle, "_guard_and_verify", lambda **kwargs: type(
        "Completed", (), {"returncode": 7}
    )())
    captured = {}
    monkeypatch.setattr(lifecycle, "_catalog_verification_failure", lambda **kwargs: captured.update(kwargs) or {
        "blocker_id": "blk-one", "occurrence_id": "occ-one",
    })
    with pytest.raises(lifecycle.LifecycleError, match="verification-failed-blocker-cataloged"):
        lifecycle._verify_run(
            run_id="run-one", receipt={}, document=path, task_id="task", root=tmp_path,
            command="uv run pytest tests/test_example.py", source="discovery_log",
            subject_id="discovery-example",
        )
    assert captured == {
        "run_id": "run-one", "discovery_id": "discovery-example",
        "exit_code": 7, "root": tmp_path,
    }


def test_registered_activation_uses_selected_document_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    directive_state = tmp_path / "directive-state.json"
    monkeypatch.setenv("MK_DIRECTIVE_STATE_PATH", str(directive_state))
    commands = []

    def run(command, *, root):
        commands.append(command)
        if "select" in command:
            return {"document": str(tmp_path / "operations/sequences/example/sequence.md")}
        if "run-start" in command:
            return {"run_id": "run-one"}
        return {"ok": True}

    monkeypatch.setattr(lifecycle, "_json_command", run)
    lifecycle._select_and_start(
        task_id="task", discovery=None, sequence_id="example", root=tmp_path,
        repo_roots_file=None,
    )
    activate = next(command for command in commands if "activate" in command)
    assert "--sequence-doc" in activate
    assert "--sequence-id" not in activate
    assert activate[activate.index("--directives-path") + 1] == str(
        tmp_path / "working-agreement/DIRECTIVES.md"
    )
    assert activate[activate.index("--directive-state") + 1] == str(
        directive_state
    )


def test_verification_guard_uses_selected_root_directive_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    directive_state = tmp_path / "directive-state.json"
    monkeypatch.setenv("MK_DIRECTIVE_STATE_PATH", str(directive_state))
    commands = []
    monkeypatch.setattr(
        lifecycle, "_json_command",
        lambda command, *, root: commands.append(command) or {"ok": True},
    )
    monkeypatch.setattr(
        lifecycle.subprocess, "run",
        lambda *args, **kwargs: type("Completed", (), {"returncode": 0})(),
    )

    lifecycle._guard_and_verify(
        task_id="task", root=tmp_path, document=tmp_path / "discovery.md",
        source="discovery_log", command="python3 scripts/verify.py",
    )

    guard = commands[0]
    assert guard[guard.index("--directives-path") + 1] == str(
        tmp_path / "working-agreement/DIRECTIVES.md"
    )
    assert guard[guard.index("--directive-state") + 1] == str(
        directive_state
    )


def test_classification_uses_the_target_operation_kind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands = []
    monkeypatch.setattr(
        lifecycle, "_json_command",
        lambda command, *, root: commands.append(command) or {"ok": True},
    )
    lifecycle._classify("task", root=tmp_path, operation_kind="other")
    assert commands[0][commands[0].index("--operation-kind") + 1] == "other"
