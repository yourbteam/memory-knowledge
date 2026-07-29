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
    assert argv[argv.index("--task-id") + 1] == task_id
    assert argv[argv.index("--step-id") + 1] == "verify"
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


def test_workflow_resume_dispatch_requires_controller_owned_preflight() -> None:
    prepared = {
        "sequence_id": "workflow-resume-from-phase-live-confirmation",
        "argv": ["python3", "/repos/up/scripts/run_client_regeneration.py"],
        "repository": {"root": "/repos/up"},
        "environment": {},
        "profile": "resume",
        "artifacts": {},
    }

    with pytest.raises(
        sequence_intake_launch.SequenceLaunchError,
        match="workflow-resume-preflight-required",
    ):
        sequence_intake_launch._dispatch_prepared("task-123", prepared)


def test_workflow_resume_controller_derives_identity_roots_and_proof() -> None:
    prepared = sequence_intake_launch._with_controller_preflight(
        "task-123",
        "workflow-resume-from-phase-live-confirmation",
        {
            "sequence_id": "workflow-resume-from-phase-live-confirmation",
            "repository": {
                "key": "united-partners",
                "root": "/repos/up",
            },
        },
        {
            "united-partners": "/repos/up",
            "memory-knowledge": str(sequence_intake_launch.work_memory.ROOT),
        },
    )

    assert prepared["controller_context"] == {
        "task_id": "task-123",
        "repository_roots": {
            "united-partners": "/repos/up",
            "memory-knowledge": str(sequence_intake_launch.work_memory.ROOT),
        },
        "guard_source": "sequence_doc",
        "guard_step": "verify-automation",
    }
    assert prepared["preflight"]["proof_kind"] == "same-public-entrypoint"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("task_id", "different-successor-task"),
        ("guard_source", "script"),
        ("guard_step", "wrong-step"),
        ("repository_roots", {"united-partners": "relative/repo"}),
    ],
)
def test_workflow_resume_rejects_drifted_controller_context(
    field,
    value,
) -> None:
    prepared = sequence_intake_launch._with_controller_preflight(
        "task-123",
        "workflow-resume-from-phase-live-confirmation",
        {
            "sequence_id": "workflow-resume-from-phase-live-confirmation",
            "repository": {
                "key": "united-partners",
                "root": "/repos/up",
            },
        },
        {"united-partners": "/repos/up"},
    )
    prepared["controller_context"][field] = value

    with pytest.raises(
        sequence_intake_launch.SequenceLaunchError,
        match="workflow-resume-controller-context-invalid",
    ):
        sequence_intake_launch._guard_preflight("task-123", prepared)


def test_workflow_resume_guard_provenance_is_controller_owned(
    monkeypatch,
) -> None:
    prepared = sequence_intake_launch._with_controller_preflight(
        "task-123",
        "workflow-resume-from-phase-live-confirmation",
        {
            "sequence_id": "workflow-resume-from-phase-live-confirmation",
            "repository": {
                "key": "united-partners",
                "root": "/repos/up",
            },
        },
        {
            "united-partners": "/repos/up",
            "memory-knowledge": str(sequence_intake_launch.work_memory.ROOT),
        },
    )
    observed = {}
    monkeypatch.setattr(
        sequence_intake_launch.work_memory,
        "load_receipt",
        lambda *_args: (
            {
                "subject_id":
                    "workflow-resume-from-phase-live-confirmation",
                "document":
                    "/repos/memory/operations/sequences/resume/sequence.md",
                    "repository_roots": {
                        "united-partners": "/repos/up",
                        "memory-knowledge":
                            str(sequence_intake_launch.work_memory.ROOT),
                    },
            },
            "a" * 64,
            Path("/private/tmp/selection.json"),
        ),
    )
    monkeypatch.setattr(
        sequence_intake_launch.sequence_guard,
        "cmd_guard",
        lambda args: observed.update(vars(args)),
    )

    sequence_intake_launch._guard_preflight("task-123", prepared)

    assert observed["task_id"] == "task-123"
    assert observed["step"] == "verify-automation"
    assert observed["source"] == "sequence_doc"
    assert observed["source_ref"].endswith("/resume/sequence.md")


def test_workflow_resume_preflight_is_grounded_in_registered_sequence() -> None:
    python = (
        "/Users/kamenkamenov/.cache/codex-runtimes/"
        "codex-primary-runtime/dependencies/python/bin/python3"
    )
    argv = [
        "env",
        "-C",
        "/Users/kamenkamenov/united-partners",
        "PYTHONPATH=src",
        python,
        "-m",
        "unittest",
        "tests.unit.test_workflow_resume",
        "tests.unit.test_client_regeneration_resume",
        "tests.unit.test_vivacom_phase20_reproduction",
        "tests.unit.test_codex_role_command",
        "tests.unit.test_role_executor_retry",
        "-v",
    ]
    document = (
        sequence_intake_launch.work_memory.ROOT
        / "operations/sequences/"
        "workflow-resume-from-phase-live-confirmation/sequence.md"
    )

    assert sequence_intake_launch.sequence_guard._shape_match(
        sequence_intake_launch.shlex.join(argv),
        document.read_text(encoding="utf-8"),
    )


@pytest.mark.parametrize(
    "invalid_argv",
    [
        ["uv", "run", "pytest", "tests/unit/test_workflow_resume.py"],
        ["python", "-m", "pytest", "tests/unit/test_workflow_resume.py"],
        ["python3", "-m", "pytest", "tests/unit/test_workflow_resume.py"],
    ],
)
def test_workflow_resume_rejects_observed_invalid_test_launchers(
    invalid_argv,
) -> None:
    prepared = {
        "sequence_id": "workflow-resume-from-phase-live-confirmation",
        "argv": ["python3", "/repos/up/scripts/run_client_regeneration.py"],
        "repository": {"key": "united-partners", "root": "/repos/up"},
        "profile": "resume",
        "preflight": {
            "argv": invalid_argv,
            "step": "verify-automation",
            "proof_kind": "same-public-entrypoint",
        },
        "controller_context": {
            "task_id": "task-123",
            "repository_roots": {"united-partners": "/repos/up"},
            "guard_source": "sequence_doc",
            "guard_step": "verify-automation",
        },
    }

    with pytest.raises(
        sequence_intake_launch.SequenceLaunchError,
        match="workflow-resume-preflight-invalid",
    ):
        sequence_intake_launch._guard_preflight("task-123", prepared)


def test_workflow_resume_dispatch_runs_same_path_preflight_before_live(
    monkeypatch,
) -> None:
    python = (
        "/Users/kamenkamenov/.cache/codex-runtimes/"
        "codex-primary-runtime/dependencies/python/bin/python3"
    )
    preflight = [
        "env", "-C", "/repos/up", "PYTHONPATH=src", python,
        "-m", "unittest",
        "tests.unit.test_workflow_resume",
        "tests.unit.test_client_regeneration_resume",
        "tests.unit.test_vivacom_phase20_reproduction",
        "tests.unit.test_codex_role_command",
        "tests.unit.test_role_executor_retry", "-v",
    ]
    live = [
        python, "/repos/up/scripts/run_client_regeneration.py",
        "--client", "vivacom", "--resume-run", "up-run-source",
        "--from-phase", "phase-20",
    ]
    prepared = {
        "sequence_id": "workflow-resume-from-phase-live-confirmation",
        "argv": live,
        "repository": {"key": "united-partners", "root": "/repos/up"},
        "environment": {"PYTHONPATH": "src"},
        "profile": "resume",
        "artifacts": {},
        "preflight": {
            "argv": preflight,
            "step": "verify-automation",
            "proof_kind": "same-public-entrypoint",
        },
        "controller_context": {
            "task_id": "task-123",
            "repository_roots": {"united-partners": "/repos/up"},
            "guard_source": "sequence_doc",
            "guard_step": "verify-automation",
        },
    }
    observed = []
    monkeypatch.setattr(
        sequence_intake_launch,
        "_guard_prepared",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        sequence_intake_launch,
        "_guard_preflight",
        lambda task_id, payload: observed.append(("guard", task_id, payload)),
    )
    monkeypatch.setattr(
        sequence_intake_launch.subprocess,
        "run",
        lambda argv, **_kwargs: (
            observed.append(("run", argv))
            or type("Completed", (), {"returncode": 0})()
        ),
    )

    assert sequence_intake_launch._dispatch_prepared(
        "task-123", prepared,
    ) == 0
    assert observed == [
        ("guard", "task-123", prepared),
        ("run", preflight),
        ("run", live),
    ]


def test_workflow_resume_stops_before_live_when_preflight_fails(
    monkeypatch,
) -> None:
    python = (
        "/Users/kamenkamenov/.cache/codex-runtimes/"
        "codex-primary-runtime/dependencies/python/bin/python3"
    )
    preflight = [
        "env", "-C", "/repos/up", "PYTHONPATH=src", python,
        "-m", "unittest",
        "tests.unit.test_workflow_resume",
        "tests.unit.test_client_regeneration_resume",
        "tests.unit.test_vivacom_phase20_reproduction",
        "tests.unit.test_codex_role_command",
        "tests.unit.test_role_executor_retry", "-v",
    ]
    live = [python, "/repos/up/scripts/run_client_regeneration.py"]
    prepared = {
        "sequence_id": "workflow-resume-from-phase-live-confirmation",
        "argv": live,
        "repository": {"key": "united-partners", "root": "/repos/up"},
        "environment": {},
        "profile": "resume",
        "artifacts": {},
        "preflight": {
            "argv": preflight,
            "step": "verify-automation",
            "proof_kind": "same-public-entrypoint",
        },
        "controller_context": {
            "task_id": "task-123",
            "repository_roots": {"united-partners": "/repos/up"},
            "guard_source": "sequence_doc",
            "guard_step": "verify-automation",
        },
    }
    observed = []
    monkeypatch.setattr(
        sequence_intake_launch,
        "_guard_prepared",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        sequence_intake_launch,
        "_guard_preflight",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        sequence_intake_launch.subprocess,
        "run",
        lambda argv, **_kwargs: (
            observed.append(argv)
            or type(
                "Completed",
                (),
                {"returncode": 9 if argv == preflight else 0},
            )()
        ),
    )

    assert sequence_intake_launch._dispatch_prepared(
        "task-123", prepared,
    ) == 9
    assert observed == [preflight]


def test_workflow_resume_correct_path_reaches_live_through_public_entrypoint(
    monkeypatch,
) -> None:
    capture = json.loads(
        (
            Path(__file__).parent
            / "fixtures/workflow_resume_phase20_capture.json"
        ).read_text(encoding="utf-8")
    )
    assert capture["capture_source"]["sha256"] == (
        "c19d4511347e38bbe9a3e124b01c46d84ce0ca6e810323c66e3d8d397ae68291"
    )
    assert capture["checkpoint"]["stage"] == "correction_pending"
    python = (
        "/Users/kamenkamenov/.cache/codex-runtimes/"
        "codex-primary-runtime/dependencies/python/bin/python3"
    )
    base = {
        "sequence_id": "workflow-resume-from-phase-live-confirmation",
        "profile": "resume",
        "argv": [
            python, "/repos/up/scripts/run_client_regeneration.py",
            "--client", capture["client"],
            "--resume-run", capture["run_id"],
            "--from-phase", capture["first_unfinished_phase"],
        ],
        "repository": {
            "key": "united-partners",
            "root": "/repos/up",
        },
        "environment": {"PYTHONPATH": "src"},
        "artifacts": {},
    }
    prepared = sequence_intake_launch._with_controller_preflight(
        "task-123",
        "workflow-resume-from-phase-live-confirmation",
        base,
        {"united-partners": "/repos/up"},
    )
    monkeypatch.setattr(
        sequence_intake_launch,
        "_task_and_preparation",
        lambda **_kwargs: {
            "task_id": "task-123",
            "sequence_id": "workflow-resume-from-phase-live-confirmation",
            "dispatch_status": "PREPARED_NOT_AUTHORIZED",
            "prepared": prepared,
        },
    )
    monkeypatch.setattr(
        sequence_intake_launch,
        "_guard_preflight",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        sequence_intake_launch,
        "_guard_prepared",
        lambda *_args: None,
    )
    observed = []

    def run(argv, **kwargs):
        observed.append(argv)
        if argv == prepared["argv"]:
            receipt_path = Path(
                kwargs["env"][sequence_intake_launch.DISPATCH_RECEIPT]
            )
            content = receipt_path.read_bytes()
            receipt = json.loads(content)
            assert receipt["task_id"] == "task-123"
            assert receipt["arguments"] == prepared["argv"][2:]
            assert kwargs["env"][sequence_intake_launch.DISPATCH_MARKER] == (
                sequence_intake_launch.hashlib.sha256(content).hexdigest()
            )
            observed.append(receipt_path)
        return type("Completed", (), {"returncode": 0})()

    monkeypatch.setattr(
        sequence_intake_launch.subprocess,
        "run",
        run,
    )

    assert sequence_intake_launch.main_for_sequence(
        "workflow-resume-from-phase-live-confirmation",
        [],
        input_fn=lambda _prompt: "yes",
        output_fn=lambda _message: None,
    ) == 0
    assert observed[:2] == [
        prepared["preflight"]["argv"],
        prepared["argv"],
    ]
    assert isinstance(observed[2], Path)
    assert not observed[2].exists()
