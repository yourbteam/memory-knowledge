from __future__ import annotations

import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest

from scripts import (
    blocker_backlog_reconciliation,
    context_edit_guard,
    convergence_checkpoint_run,
    convergence_state_review_cycle,
    discovery_bootstrap,
    discovery_candidate_reconciliation,
    discovery_promotion_lifecycle,
    sequence_intake_launch,
)


def _verified(sequence_id: str) -> dict:
    return {
        "mode": "registered",
        "subject_id": sequence_id,
        "selection": {
            "repository_roots": {
                "taggable-api": "/repos/taggable-api",
                "memory-knowledge": "/repos/memory",
            },
        },
    }


def test_prepare_active_sequence_collects_semantics_without_dispatch(
    monkeypatch,
):
    prompts = []
    answers = iter(["taggable-api", "yes"])
    monkeypatch.setattr(
        sequence_intake_launch.sequence_guard,
        "verify_receipts",
        lambda _task_id, _active_path: _verified("taggable-api-deploy"),
    )

    result = sequence_intake_launch.prepare_active_sequence(
        "task-123",
        input_fn=lambda prompt: prompts.append(prompt) or next(answers),
        output_fn=lambda _message: None,
    )

    assert result["dispatch_status"] == "PREPARED_NOT_AUTHORIZED"
    assert result["prepared"]["argv"] == [
        "bash", "/repos/taggable-api/scripts/deploy-api.sh",
    ]
    assert result["prepared"]["authorization"]["effectful"] is True
    assert all("Response format:" in prompt for prompt in prompts)
    assert all("Example:" in prompt for prompt in prompts)
    assert all("Constraints:" in prompt for prompt in prompts)


def test_stale_registry_still_allows_intake_from_exact_active_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    task_id = "task-123"
    selection = {
        "mode": "registered",
        "subject_id": "taggable-api-deploy",
        "lineage_id": "lineage",
        "document": str(tmp_path / "sequence.md"),
        "source_bundle_hash": "a" * 64,
        "repository_roots": {"taggable-api": "/repos/taggable-api"},
    }
    active_path = tmp_path / "active.json"
    active_path.write_text(json.dumps({
        "task_id": task_id,
        "mode": "registered",
        "subject_id": "taggable-api-deploy",
        "lineage_id": "lineage",
        "document": str(tmp_path / "sequence.md"),
        "source_bundle_hash": "a" * 64,
        "selection_receipt_hash": "b" * 64,
    }), encoding="utf-8")
    monkeypatch.setattr(
        sequence_intake_launch.sequence_guard,
        "verify_receipts",
        lambda *_args: (_ for _ in ()).throw(
            sequence_intake_launch.work_memory.WorkMemoryError(
                "stale-registry-receipt", 4,
            )
        ),
    )
    monkeypatch.setattr(
        sequence_intake_launch.work_memory,
        "load_receipt",
        lambda *_args: (selection, "b" * 64, active_path),
    )

    verified = sequence_intake_launch._active_selection_for_intake(
        task_id, active_path,
    )

    assert verified["subject_id"] == "taggable-api-deploy"
    assert verified["stale_registry_receipt"] is True


def test_correction_intake_prepares_sealed_bootstrap_with_same_run_co_blockers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    task_id = "task-123"
    run_id = "11111111-1111-4111-8111-111111111111"
    primary_occurrence = "22222222-2222-4222-8222-222222222222"
    repository = tmp_path / "memory"
    (repository / "scripts").mkdir(parents=True)
    (repository / "scripts/one.py").write_text("# changed\n")
    prepared = {
        "profile": "correct-registered",
        "argv": [
            "python3", str(repository / "scripts/discovery_promotion_lifecycle.py"),
            "correct-registered", "--task-id", task_id,
            "--solution", "Stable correction.",
            "--reusable-behavior-changed", "yes",
            "--supersedes-correction-id",
            "33333333-3333-4333-8333-333333333333",
        ],
        "artifacts": {
            "changed_artifacts": {
                "path": "/private/tmp/sequence-intake/task-123/example/changed_artifacts.json",
                "content": json.dumps([{
                    "repository_key": "memory-knowledge",
                    "path": "scripts/one.py",
                }]),
            },
        },
    }
    selection = {
        "subject_id": "discovery-promotion-lifecycle",
        "lineage_id": "lineage-one",
    }
    events = [
        {
            "event_type": "run_started", "task_id": task_id,
            "subject_id": selection["subject_id"],
            "lineage_id": selection["lineage_id"], "run_id": run_id,
        },
        {
            "event_type": "blocker_opened", "blocker_id": "blk-primary",
            "subject_id": selection["subject_id"],
            "lineage_id": selection["lineage_id"], "run_id": run_id,
            "occurrence_id": primary_occurrence, "step_id": "verify",
        },
        {
            "event_type": "blocker_opened", "blocker_id": "blk-secondary",
            "subject_id": selection["subject_id"],
            "lineage_id": selection["lineage_id"], "run_id": run_id,
            "occurrence_id": "44444444-4444-4444-8444-444444444444",
            "step_id": "dispatch",
        },
    ]
    monkeypatch.setattr(
        sequence_intake_launch.work_memory,
        "load_ledger",
        lambda: (events, "a" * 64),
    )

    result = sequence_intake_launch._prepare_correction_bootstrap(
        task_id,
        prepared,
        selection,
        {"memory-knowledge": str(repository)},
    )

    argv = result["argv"]
    assert Path(argv[1]).name == "work_memory_bootstrap_launcher.py"
    assert argv[2] == "correct"
    assert argv[argv.index("--blocker-id") + 1] == "blk-primary"
    assert argv[argv.index("--co-blocker-id") + 1] == "blk-secondary"
    assert argv[argv.index("--correction-id") + 1] == str(uuid5(
        NAMESPACE_URL,
        f"memory-knowledge:{run_id}:blk-primary:{primary_occurrence}",
    ))
    assert argv[argv.index("--changed-artifact") + 1] == str(
        repository / "scripts/one.py"
    )


def test_prepare_active_sequence_builds_artifacts_in_memory_only(
    monkeypatch,
):
    monkeypatch.setattr(
        sequence_intake_launch.sequence_guard,
        "verify_receipts",
        lambda _task_id, _active_path: _verified("commit-push-main"),
    )
    answers = iter([
        "dry-run",
        "memory-knowledge",
        "scripts/example.py",
        "no",
        "Prepare semantic intake",
        "",
        "",
    ])

    result = sequence_intake_launch.prepare_active_sequence(
        "task-123",
        input_fn=lambda _prompt: next(answers),
        output_fn=lambda _message: None,
    )

    artifact = result["prepared"]["artifacts"]["approved_paths"]
    assert artifact["content"] == "scripts/example.py\n"
    assert artifact["path"].startswith(
        "/private/tmp/sequence-intake/task-123/commit-push-main/"
    )
    assert not Path(artifact["path"]).exists()


def test_main_rejects_operator_arguments(capsys):
    assert sequence_intake_launch.main(["commit-push-main"]) == 2

    error = json.loads(capsys.readouterr().err)
    assert error["error"] == "no-argument-entrypoint-required"


def test_invoked_script_resolves_machine_relative_script_from_repository():
    prepared = {
        "argv": ["python3", "scripts/scoped_git_publish.py"],
        "repository": {"root": "/repos/memory"},
    }

    assert sequence_intake_launch._invoked_script(prepared) == Path(
        "/repos/memory/scripts/scoped_git_publish.py"
    )


def test_invoked_script_ignores_script_shaped_argument_values():
    prepared = {
        "argv": [
            "python3",
            "scripts/discovery_promotion_lifecycle.py",
            "--automation-display",
            "memory-knowledge:scripts/blocker_backlog_reconciliation.py",
        ],
        "repository": {"root": "/repos/memory"},
    }

    assert sequence_intake_launch._invoked_script(prepared) == Path(
        "/repos/memory/scripts/discovery_promotion_lifecycle.py"
    )


def test_main_asks_for_task_reviews_payload_then_requires_authorization(
    monkeypatch, capsys,
):
    prompts = []
    answers = iter(["task-123", "taggable-api", "yes", "no"])
    monkeypatch.setattr(
        sequence_intake_launch.sequence_guard,
        "verify_receipts",
        lambda _task_id, _active_path: _verified("taggable-api-deploy"),
    )

    exit_code = sequence_intake_launch.main(
        [],
        input_fn=lambda prompt: prompts.append(prompt) or next(answers),
        output_fn=lambda _message: None,
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    prepared = json.loads(captured.err)
    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["task_id"] == "task-123"
    assert payload["sequence_id"] == "taggable-api-deploy"
    assert payload["dispatch_status"] == "DECLINED"
    assert prepared["dispatch_status"] == "PREPARED_NOT_AUTHORIZED"
    assert prompts[0].startswith("Question: Active governed task identity")


@pytest.mark.parametrize(
    ("module", "sequence_id"),
    [
        (discovery_bootstrap, "discovery-bootstrap"),
        (
            discovery_candidate_reconciliation,
            "discovery-candidate-reconciliation",
        ),
        (
            blocker_backlog_reconciliation,
            "blocker-backlog-reconciliation",
        ),
        (discovery_promotion_lifecycle, "discovery-promotion-lifecycle"),
        (convergence_checkpoint_run, "convergence-checkpoint-run"),
        (context_edit_guard, "scoped-context-edit"),
        (
            convergence_state_review_cycle,
            "convergence-state-review-cycle",
        ),
    ],
)
def test_memory_knowledge_entrypoints_route_bare_launch_to_intake(
    monkeypatch, module, sequence_id,
):
    observed = []
    monkeypatch.setattr(
        sequence_intake_launch,
        "main_for_sequence",
        lambda actual, argv: observed.append((actual, argv)) or 17,
    )

    assert module.main([]) == 17
    assert observed == [(sequence_id, [])]


def test_sequence_entrypoint_reviews_then_declines_without_dispatch(
    monkeypatch, capsys,
):
    prepared = {
        "task_id": "task-123",
        "sequence_id": "taggable-api-deploy",
        "dispatch_status": "PREPARED_NOT_AUTHORIZED",
        "prepared": {"argv": ["bash", "/repos/api/scripts/deploy-api.sh"]},
    }
    monkeypatch.setattr(
        sequence_intake_launch,
        "_task_and_preparation",
        lambda **_kwargs: prepared,
    )
    monkeypatch.setattr(
        sequence_intake_launch,
        "_dispatch_prepared",
        lambda *_args: (_ for _ in ()).throw(AssertionError("dispatched")),
    )

    exit_code = sequence_intake_launch.main_for_sequence(
        "taggable-api-deploy",
        [],
        input_fn=lambda _prompt: "no",
        output_fn=lambda _message: None,
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out)["dispatch_status"] == "DECLINED"
    assert "PREPARED_NOT_AUTHORIZED" in captured.err


def test_sequence_entrypoint_dispatches_only_after_explicit_yes(
    monkeypatch,
):
    prepared = {
        "task_id": "task-123",
        "sequence_id": "taggable-api-deploy",
        "dispatch_status": "PREPARED_NOT_AUTHORIZED",
        "prepared": {"argv": ["bash", "/repos/api/scripts/deploy-api.sh"]},
    }
    observed = []
    monkeypatch.setattr(
        sequence_intake_launch,
        "_task_and_preparation",
        lambda **_kwargs: prepared,
    )
    monkeypatch.setattr(
        sequence_intake_launch,
        "_dispatch_prepared",
        lambda task_id, payload: observed.append((task_id, payload)) or 23,
    )

    exit_code = sequence_intake_launch.main_for_sequence(
        "taggable-api-deploy",
        [],
        input_fn=lambda _prompt: "yes",
        output_fn=lambda _message: None,
    )

    assert exit_code == 23
    assert observed == [("task-123", prepared["prepared"])]


def test_dispatch_marks_zero_argument_child_as_prepared(
    monkeypatch,
):
    observed = {}
    prepared = {
        "argv": ["python3", "scripts/test_engine_upgrades.py"],
        "repository": {"root": "/repos/callcenter"},
        "environment": {},
        "profile": "test",
        "artifacts": {},
    }
    monkeypatch.setattr(
        sequence_intake_launch,
        "_guard_prepared",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        sequence_intake_launch.subprocess,
        "run",
        lambda argv, **kwargs: (
            observed.update(argv=argv, **kwargs)
            or type("Completed", (), {"returncode": 0})()
        ),
    )

    assert sequence_intake_launch._dispatch_prepared(
        "task-123", prepared,
    ) == 0
    assert observed["env"][
        sequence_intake_launch.DISPATCH_MARKER
    ] == "1"
