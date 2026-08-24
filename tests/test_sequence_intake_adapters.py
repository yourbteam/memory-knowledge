from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from scripts import prevention_registry, script_intake, sequence_intake_adapters


def test_registry_covers_every_canonical_sequence_identity():
    rows = prevention_registry.parse_markdown_projection(
        prevention_registry.MARKDOWN_REGISTRY,
    )
    expected = {row["sequence_id"] for row in rows}

    assert set(sequence_intake_adapters.ADAPTER_REGISTRY) == expected


def test_commit_push_collects_semantic_answers_then_derives_payload():
    prompts = []
    answers = iter([
        "1",
        "2",
        "scripts/script_intake.py",
        "yes",
        "tests/test_script_intake.py",
        "no",
        # The commit message is multi-line: subject, blank line, body, then the closing marker.
        "Add deterministic sequence intake",
        "",
        "It replaces hand-built invocations with derived, authorized input.",
        ".",
        "",
        "",
    ])

    prepared = sequence_intake_adapters.collect_and_prepare(
        "commit-push-main",
        artifact_paths={
            "approved_paths": "/private/tmp/intake-approved-paths.txt",
        },
        repository_roots={
            "mcp-agents-workflow": "/Users/kamenkamenov/mcp-agents-workflow",
            "memory-knowledge": "/Users/kamenkamenov/memory-knowledge",
        },
        input_fn=lambda prompt: prompts.append(prompt) or next(answers),
        output_fn=lambda message: None,
    )

    assert prepared["profile"] == "dry-run"
    assert prepared["argv"][:2] == [
        "python3", sequence_intake_adapters.SCOPED_GIT_PUBLISH_SCRIPT,
    ]
    assert prepared["artifacts"]["approved_paths"]["content"] == (
        "scripts/script_intake.py\ntests/test_script_intake.py\n"
    )
    assert prepared["argv"][prepared["argv"].index("--message") + 1] == (
        "Add deterministic sequence intake\n\n"
        "It replaces hand-built invocations with derived, authorized input."
    )
    # Continuation lines of a multi-line answer are read with an empty prompt; every prompt that
    # is shown must still be fully specified.
    shown = [prompt for prompt in prompts if prompt]
    assert all("Question:" in prompt for prompt in shown)
    assert all("Response format:" in prompt for prompt in shown)
    assert all("Example:" in prompt for prompt in shown)
    assert all("Constraints:" in prompt for prompt in shown)
    assert "Selection options:" in shown[0]
    assert "1. dry-run" in shown[0]
    assert "Choose one selection number." in shown[0]
    assert "Selection options:" in shown[1]
    assert "Example: 1" in shown[1]
    assert "1. mcp-agents-workflow" in shown[1]
    assert "2. memory-knowledge" in shown[1]


def test_commit_push_dry_run_derives_exact_argv_and_manifest():
    prepared = sequence_intake_adapters.prepare(
        "commit-push-main",
        {
            "operation": "dry-run",
            "repository_key": "memory-knowledge",
            "approved_paths": [
                "scripts/script_intake.py",
                "tests/test_script_intake.py",
            ],
            "message": "Add deterministic sequence intake",
            "branch": "main",
            "remote": "origin",
        },
        artifact_paths={"approved_paths": "/private/tmp/intake-approved-paths.txt"},
        repository_roots={
            "memory-knowledge": "/Users/kamenkamenov/memory-knowledge",
        },
    )

    assert prepared == {
        "schema_version": 1,
        "sequence_id": "commit-push-main",
        "profile": "dry-run",
        "artifacts": {
            "approved_paths": {
                "content": (
                    "scripts/script_intake.py\n"
                    "tests/test_script_intake.py\n"
                ),
                "path": "/private/tmp/intake-approved-paths.txt",
            },
        },
        "argv": [
            "python3",
            sequence_intake_adapters.SCOPED_GIT_PUBLISH_SCRIPT,
            "--repo",
            "/Users/kamenkamenov/memory-knowledge",
            "--repository-key",
            "memory-knowledge",
            "--manifest",
            "/private/tmp/intake-approved-paths.txt",
            "--message",
            "Add deterministic sequence intake",
            "--branch",
            "main",
            "--remote",
            "origin",
        ],
        "repository": {
            "key": "memory-knowledge",
            "root": "/Users/kamenkamenov/memory-knowledge",
        },
        "authorization": {
            "effectful": False,
            "required": False,
            "operation": "dry-run",
        },
    }


def test_goal_declaration_derives_one_authorized_answers_artifact(tmp_path: Path):
    repository = tmp_path / "target"
    (repository / "scripts").mkdir(parents=True)
    (repository / "scripts/measure.py").write_text("print('{}')\n")
    answers = {
        "repository_key": "target",
        "statement": "make every generated document sendable",
        "set_by": "Kamen",
        "supersede_reason": "none",
        "kpis": [{
            "id": "sendable-documents",
            "question": "how many generated documents are sendable",
            "producer": "scripts/measure.py",
            "deterministic": True,
            "direction": "up",
        }],
    }

    prepared = sequence_intake_adapters.prepare(
        "goal-declaration",
        answers,
        artifact_paths={"goal_answers": "/private/tmp/goal-answers.json"},
        repository_roots={
            "memory-knowledge": "/repos/memory",
            "target": str(repository),
        },
    )

    assert prepared["argv"] == [
        "python3", "/repos/memory/scripts/goal_tracker.py",
        "--repo", str(repository.resolve()), "set",
        "--answers-file", "/private/tmp/goal-answers.json",
    ]
    assert json.loads(prepared["artifacts"]["goal_answers"]["content"]) == {
        key: value for key, value in answers.items() if key != "repository_key"
    }
    assert prepared["authorization"] == {
        "effectful": True,
        "required": True,
        "operation": "set",
    }


def test_goal_declaration_repository_is_a_numbered_selection(tmp_path: Path):
    repository = tmp_path / "target"
    (repository / "scripts").mkdir(parents=True)
    (repository / "scripts/measure.py").write_text("print('{}')\n")
    prompts = []
    answers = iter([
        "2",
        "make every generated document sendable", ".",
        "Kamen",
        "none",
        "sendable-documents",
        "how many generated documents are sendable", ".",
        "scripts/measure.py",
        "yes",
        "1",
        "no",
    ])

    prepared = sequence_intake_adapters.collect_and_prepare(
        "goal-declaration",
        artifact_paths={"goal_answers": "/private/tmp/goal-answers.json"},
        repository_roots={
            "memory-knowledge": "/repos/memory",
            "target": str(repository),
        },
        input_fn=lambda prompt: prompts.append(prompt) or next(answers),
        output_fn=lambda _message: None,
    )

    assert prepared["repository"]["key"] == "target"
    assert "1. memory-knowledge" in prompts[0]
    assert "2. target" in prompts[0]


def test_agent_heartbeat_derives_only_fixed_template_probes():
    prepared = sequence_intake_adapters.prepare(
        "agent-heartbeat",
        {
            "source_repository_key": "memory-knowledge",
            "seconds": 270,
            "label": "feature 11 live drive",
            "probes": [
                {"type": "file-tail", "path": "/private/tmp/run/result.json", "lines": 80},
                {
                    "type": "container-logs",
                    "container": "workflow-orch-local",
                    "lookback_seconds": 300,
                    "lines": 120,
                },
            ],
        },
        artifact_paths={},
        repository_roots={"memory-knowledge": "/repos/memory"},
    )

    assert prepared["argv"] == [
        "bash", "/repos/memory/scripts/agent_heartbeat.sh",
        "--seconds", "270",
        "--label", "feature 11 live drive",
        "--probe", "tail -n 80 -- /private/tmp/run/result.json",
        "--probe", "docker logs --since 300s workflow-orch-local 2>&1 | tail -n 120",
    ]
    assert prepared["authorization"]["required"] is True


def test_agent_heartbeat_rejects_shell_and_untrusted_paths():
    base = {
        "source_repository_key": "memory-knowledge",
        "seconds": 270,
        "label": "live drive",
    }
    roots = {"memory-knowledge": "/repos/memory"}

    with pytest.raises(sequence_intake_adapters.AdapterError, match="probe-contract-invalid"):
        sequence_intake_adapters.prepare(
            "agent-heartbeat",
            {**base, "probes": [{"type": "raw-shell", "command": "curl secret"}]},
            artifact_paths={}, repository_roots=roots,
        )
    with pytest.raises(sequence_intake_adapters.AdapterError, match="outside-trusted-roots"):
        sequence_intake_adapters.prepare(
            "agent-heartbeat",
            {**base, "probes": [{"type": "file-metadata", "path": "/etc/passwd"}]},
            artifact_paths={}, repository_roots=roots,
        )


def test_commit_push_publish_derives_execute_without_operator_authored_flag():
    answers = {
        "operation": "publish",
        "repository_key": "repo",
        "approved_paths": ["one.txt"],
        "message": "Publish one file",
        "branch": "main",
        "remote": "origin",
    }

    prepared = sequence_intake_adapters.prepare(
        "commit-push-main",
        answers,
        artifact_paths={"approved_paths": "/tmp/manifest.txt"},
        repository_roots={"repo": "/repo"},
    )

    assert prepared["argv"][-1] == "--execute"
    assert prepared["authorization"] == {
        "effectful": True,
        "required": True,
        "operation": "publish",
    }
    assert prepared["host_capabilities"] == [
        "repository-git-metadata-write",
    ]


def test_commit_push_resume_does_not_ask_for_or_emit_manifest_or_message():
    prepared = sequence_intake_adapters.prepare(
        "commit-push-main",
        {
            "operation": "resume-push",
            "repository_key": "repo",
            "branch": "main",
            "remote": "origin",
            "resume_commit": "a" * 40,
        },
        artifact_paths={},
        repository_roots={"repo": "/repo"},
    )

    assert prepared["artifacts"] == {}
    assert prepared["argv"] == [
        "python3",
        sequence_intake_adapters.SCOPED_GIT_PUBLISH_SCRIPT,
            "--repo",
            "/repo",
            "--repository-key",
            "repo",
            "--branch",
        "main",
        "--remote",
        "origin",
        "--resume-commit",
        "a" * 40,
    ]


@pytest.mark.parametrize(
    ("sequence_id", "repository_key", "script"),
    [
        ("taggable-api-deploy", "taggable-api", "deploy-api.sh"),
        (
            "taggable-media-worker-deploy",
            "taggable-api",
            "deploy-media-worker.sh",
        ),
    ],
)
def test_deploy_adapter_derives_verified_script_invocation(
    sequence_id: str, repository_key: str, script: str, monkeypatch,
):
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    prepared = sequence_intake_adapters.prepare(
        sequence_id,
        {"repository_key": repository_key, "verify": True},
        artifact_paths={},
        repository_roots={repository_key: f"/repos/{repository_key}"},
    )

    assert prepared["argv"] == [
        "bash", f"/repos/{repository_key}/scripts/{script}",
    ]
    assert prepared["profile"] == "verified"
    assert prepared["authorization"]["operation"] == "deploy"
    assert prepared["environment"]["PATH"] == (
        f"{Path.home() / '.dotnet'}{os.pathsep}/usr/bin:/bin"
    )


def test_admin_deploy_derives_api_base_and_skip_verification_flags():
    prepared = sequence_intake_adapters.prepare(
        "taggable-admin-spa-deploy",
        {
            "repository_key": "taggable-admin-spa",
            "api_base": "https://api.example.test/api",
            "verify": False,
        },
        artifact_paths={},
        repository_roots={"taggable-admin-spa": "/repos/admin"},
    )

    assert prepared["argv"] == [
        "bash",
        "/repos/admin/scripts/deploy-admin-spa.sh",
        "--api-base",
        "https://api.example.test/api",
        "--no-verify",
    ]
    assert prepared["profile"] == "no-verify"
    assert "environment" not in prepared


def test_deploy_intake_asks_semantics_and_emits_no_caller_authored_flags():
    prompts = []
    answers = iter(["taggable-admin-spa", "", "yes"])

    prepared = sequence_intake_adapters.collect_and_prepare(
        "taggable-admin-spa-deploy",
        artifact_paths={},
        repository_roots={"taggable-admin-spa": "/repos/admin"},
        input_fn=lambda prompt: prompts.append(prompt) or next(answers),
        output_fn=lambda _message: None,
    )

    assert prepared["argv"][-2:] == [
        "--api-base", "https://taggable-api-dev.azurewebsites.net/api",
    ]
    assert all("Response format:" in prompt for prompt in prompts)
    assert all("Example:" in prompt for prompt in prompts)
    assert all("Constraints:" in prompt for prompt in prompts)


@pytest.mark.parametrize(
    "sequence_id",
    [
        "local-workflow-orch-image",
        "greenfield-full-drive",
        "claude-auth-token-refresh",
    ],
)
def test_operational_intake_specs_are_valid_and_never_request_invocation_syntax(
    sequence_id: str,
):
    spec = sequence_intake_adapters.intake_spec(
        sequence_id,
        repository_roots={
            "mcp-agents-workflow": "/repos/mawf",
            "memory-knowledge": "/repos/memory",
        },
    )

    fields = script_intake._validate_spec(spec)
    assert fields
    assert not {
        "argv", "command", "flags", "shell_command",
    } & {field["id"] for field in fields}


def test_scoped_context_prepare_derives_guard_contract_from_semantics():
    prepared = sequence_intake_adapters.prepare(
        "scoped-context-edit",
        {
            "operation": "prepare",
            "source_repository_key": "memory-knowledge",
            "receipt": "/private/tmp/context-edit-receipt.json",
            "target_repository_key": "product",
            "target": "scripts/example.py",
            "anchor": "def target_function():",
            "allowed_paths": [
                "scripts/example.py",
                "tests/test_example.py",
            ],
            "required_after": "return verified",
            "forbidden_after": None,
        },
        artifact_paths={},
        repository_roots={
            "memory-knowledge": "/repos/memory",
            "product": "/repos/product",
        },
    )

    assert prepared["argv"] == [
        "python3",
        "/repos/memory/scripts/context_edit_guard.py",
        "prepare",
        "--repo-root", "/repos/product",
        "--target", "scripts/example.py",
        "--anchor", "def target_function():",
        "--anchor-count", "1",
        "--receipt", "/private/tmp/context-edit-receipt.json",
        "--allow", "scripts/example.py",
        "--allow", "tests/test_example.py",
        "--require-after", "return verified",
    ]


def test_discovery_reconciliation_rolling_uses_controller_owned_constants():
    prepared = sequence_intake_adapters.prepare(
        "discovery-candidate-reconciliation",
        {
            "operation": "execute-rolling",
            "source_repository_key": "memory-knowledge",
            "output_directory": "/private/tmp/reconciliation-runs",
        },
        artifact_paths={},
        repository_roots={"memory-knowledge": "/repos/memory"},
    )

    assert prepared["argv"] == [
        "python3",
        "/repos/memory/scripts/discovery_candidate_reconciliation.py",
        "--root", "/repos/memory",
        "execute-rolling",
        "--baseline",
        "/repos/memory/operations/sequences/discovery/reconciliation-policy.json",
        "--output-dir", "/private/tmp/reconciliation-runs",
        "--active-index",
        "/repos/memory/operations/sequences/discovery/ACTIVE.md",
        "--max-attempts", "6",
    ]


def test_blocker_backlog_execute_derives_controller_owned_index_and_run():
    prepared = sequence_intake_adapters.prepare(
        "blocker-backlog-reconciliation",
        {
            "operation": "execute",
            "source_repository_key": "memory-knowledge",
            "manifest": "/private/tmp/blockers.json",
            "run_id": "run-123",
        },
        artifact_paths={},
        repository_roots={"memory-knowledge": "/repos/memory"},
    )

    assert prepared["argv"] == [
        "python3",
        "/repos/memory/scripts/blocker_backlog_reconciliation.py",
        "--root", "/repos/memory",
        "execute",
        "--manifest", "/private/tmp/blockers.json",
        "--run-id", "run-123",
        "--active-index", "/repos/memory/operations/blockers/ACTIVE.md",
    ]
    assert prepared["authorization"] == {
        "effectful": True,
        "operation": "execute",
        "required": True,
    }


def test_discovery_promotion_drive_derives_repeated_operation_kind_flags():
    prepared = sequence_intake_adapters.prepare(
        "discovery-promotion-lifecycle",
        {
            "operation": "drive",
            "source_repository_key": "memory-knowledge",
            "repo_roots_file": None,
            "discovery_file": "operations/sequences/discovery/example.md",
            "sequence_id": "example-sequence",
            "use_when": "Deploy the API to development.",
            "operation_kinds": ["deploy", "remote-operator"],
            "automation_display": "product:scripts/deploy.sh",
            "pass_signal": "DEPLOYMENT VERIFIED",
        },
        artifact_paths={},
        repository_roots={"memory-knowledge": "/repos/memory"},
    )

    assert prepared["argv"][-12:] == [
        "--use-when", "Deploy the API to development.",
        "--operation-kind", "deploy",
        "--operation-kind", "remote-operator",
        "--automation-display", "product:scripts/deploy.sh",
        "--pass-signal", "DEPLOYMENT VERIFIED",
        "--max-qualification-runs", "3",
    ]


def test_discovery_correction_builds_canonical_changed_artifacts_json():
    prepared = sequence_intake_adapters.prepare(
        "discovery-promotion-lifecycle",
        {
            "operation": "correct",
            "source_repository_key": "memory-knowledge",
            "repo_roots_file": None,
            "discovery_file": "operations/sequences/discovery/example.md",
            "sequence_id": "example-sequence",
            "task_id": "task-123",
            "solution": "Bind the missing runtime dependency.",
            "changed_artifacts": [{
                "repository_key": "memory-knowledge",
                "path": "scripts/example.py",
            }],
            "reusable_behavior_changed": True,
            "superseding": False,
        },
        artifact_paths={
            "changed_artifacts": "/private/tmp/changed-artifacts.json",
        },
        repository_roots={"memory-knowledge": "/repos/memory"},
    )

    assert prepared["artifacts"]["changed_artifacts"] == {
        "path": "/private/tmp/changed-artifacts.json",
        "content": (
            '[{"path":"scripts/example.py",'
            '"repository_key":"memory-knowledge"}]\n'
        ),
    }
    assert prepared["argv"][-6:] == [
        "--solution", "Bind the missing runtime dependency.",
        "--changed-artifacts-file", "/private/tmp/changed-artifacts.json",
        "--reusable-behavior-changed", "yes",
    ]


def test_discovery_correction_rejects_unregistered_artifact_repository():
    with pytest.raises(
        sequence_intake_adapters.AdapterError,
        match="repository-key-unregistered:unknown",
    ):
        sequence_intake_adapters.prepare(
            "discovery-promotion-lifecycle",
            {
                "operation": "correct",
                "source_repository_key": "memory-knowledge",
                "repo_roots_file": None,
                "discovery_file": "discovery.md",
                "sequence_id": "example-sequence",
                "task_id": None,
                "solution": "Correct it.",
                "changed_artifacts": [{
                    "repository_key": "unknown",
                    "path": "scripts/example.py",
                }],
                "reusable_behavior_changed": False,
                "superseding": False,
            },
            artifact_paths={
                "changed_artifacts": "/private/tmp/changed-artifacts.json",
            },
            repository_roots={"memory-knowledge": "/repos/memory"},
        )


def test_convergence_checkpoint_serializes_prepared_child_intent(
    tmp_path,
):
    child_intent_file = tmp_path / "child-intent.json"
    child_intent_file.write_text(json.dumps({
        "guard_receipt_id": "guard-1",
        "child_parameters": [],
        "child_intent_id": "child-1",
        "child_contract_sha256": "a" * 64,
        "child_owner_sequence_id": "claude-auth-token-refresh",
    }), encoding="utf-8")

    prepared = sequence_intake_adapters.prepare(
        "convergence-checkpoint-run",
        {
            "source_repository_key": "memory-knowledge",
            "state": "/private/tmp/state.json",
            "approval_id": "approval-123",
            "child_intent_file": str(child_intent_file),
            "stage": "implementation",
        },
        artifact_paths={},
        repository_roots={"memory-knowledge": "/repos/memory"},
    )

    child_index = prepared["argv"].index("--child-intent-json") + 1
    assert json.loads(prepared["argv"][child_index]) == json.loads(
        child_intent_file.read_text(encoding="utf-8")
    )
    assert prepared["argv"][-4:] == [
        "--stage", "implementation", "--lock-timeout-seconds", "30",
    ]


def test_convergence_review_builds_ids_hash_and_request_json(
    tmp_path, monkeypatch,
):
    state = tmp_path / "state.json"
    state.write_text('{"status":"review"}\n', encoding="utf-8")
    monkeypatch.setattr(
        sequence_intake_adapters,
        "_review_state_path",
        lambda _reference, _repository: state,
    )
    answers = {
        "operation": "dry-run",
        "source_repository_key": "memory-knowledge",
        "state": "runtime-temp/state.json",
        "expected_final_status": "review",
        "operations": [
            {"kind": "status"},
            {
                "kind": "record-gap",
                "id": "gap-1",
                "requirement_ids": ["REQ-1"],
                "source_stage": "review",
                "impact": "The outcome is not verified.",
                "evidence": "The final check failed.",
            },
        ],
    }

    prepared = sequence_intake_adapters.prepare(
        "convergence-state-review-cycle",
        answers,
        artifact_paths={"request": "/private/tmp/review-request.json"},
        repository_roots={"memory-knowledge": "/repos/memory"},
    )
    request = json.loads(prepared["artifacts"]["request"]["content"])

    assert request["initial_state_sha256"] == hashlib.sha256(
        state.read_bytes()
    ).hexdigest()
    assert request["state"] == "runtime-temp/state.json"
    assert len({item["operation_id"] for item in request["operations"]}) == 2
    assert all(
        len(item["operation_id"]) == 36 for item in request["operations"]
    )
    assert prepared["argv"] == [
        "python3",
        "/repos/memory/scripts/convergence_state_review_cycle.py",
        "apply", "--request", "/private/tmp/review-request.json",
        "--dry-run",
    ]
    repeated = sequence_intake_adapters.prepare(
        "convergence-state-review-cycle",
        answers,
        artifact_paths={"request": "/private/tmp/review-request.json"},
        repository_roots={"memory-knowledge": "/repos/memory"},
    )
    assert repeated["artifacts"]["request"] == prepared["artifacts"]["request"]


@pytest.mark.parametrize(
    "sequence_id",
    ["convergence-checkpoint-run", "convergence-state-review-cycle"],
)
def test_convergence_intakes_request_no_json_or_invocation_syntax(sequence_id):
    spec = sequence_intake_adapters.intake_spec(
        sequence_id,
        repository_roots={"memory-knowledge": "/repos/memory"},
    )
    fields = script_intake._validate_spec(spec)

    assert fields
    assert not {"json", "argv", "command", "flags"} & {
        field["id"] for field in fields
    }


def test_taggable_reload_derives_optional_safety_flags():
    prepared = sequence_intake_adapters.prepare(
        "taggable-source-reload",
        {
            "repository_key": "taggable-api",
            "export_directory": "/private/tmp/app.csv",
            "source_record_id": 3,
            "webjob_missing": True,
            "manage_database_tier": False,
        },
        artifact_paths={},
        repository_roots={"taggable-api": "/repos/taggable-api"},
    )

    assert prepared["argv"] == [
        "bash",
        (
            "/repos/taggable-api/tools/Taggable.MigrationRunner/"
            "scripts/reload-source.sh"
        ),
        "--export-dir", "/private/tmp/app.csv",
        "--srid", "3",
        "--redeploy-webjob",
        "--no-scale",
    ]


def test_github_refresh_derives_durable_dry_run_without_local_override():
    prepared = sequence_intake_adapters.prepare(
        "github-app-repos-refresh",
        {
            "repository_key": "mcp-agents-workflow",
            "server_url": "wss://workflow.example.test/ws",
            "operator_env": "/private/tmp/admin.env",
            "actor_email": "admin@example.com",
            "durability": "durable",
            "operation": "dry-run",
        },
        artifact_paths={},
        repository_roots={"mcp-agents-workflow": "/repos/mawf"},
    )

    assert prepared["argv"] == [
        "python3", "/repos/mawf/scripts/github_app_repos_refresh.py",
        "--server-url", "wss://workflow.example.test/ws",
        "--operator-env", "/private/tmp/admin.env",
        "--actor-email", "admin@example.com",
        "--auth-auto-refresh", "--no-interactive", "--dry-run",
    ]
    assert "--allow-local-only" not in prepared["argv"]


def test_mawf_speed_gate_policy_is_code_owned():
    prepared = sequence_intake_adapters.prepare(
        "mawf-playbook-speed-test",
        {
            "repository_key": "mcp-agents-workflow",
            "action": "answer-gate",
            "task_guid": "task-123",
            "run_id": "run-123",
            "workflow_name": "research-workflow",
            "dry_run": True,
        },
        artifact_paths={},
        repository_roots={"mcp-agents-workflow": "/repos/mawf"},
    )

    assert prepared["argv"][-3:] == ["--gate-policy", "speed", "--dry-run"]
    assert prepared["authorization"]["effectful"] is False


def test_greenfield_recreate_derives_all_runtime_flags():
    prepared = sequence_intake_adapters.prepare(
        "greenfield-recreate-resume",
        {
            "repository_key": "mcp-agents-workflow",
            "feature_repository": "github:owner/product",
            "program_drive_id": "program-1",
            "decomposition_task_id": "mawf-task-1",
            "rebuild_image": True,
            "container": "workflow-local",
            "image_tag": "workflow:test",
            "port": 18083,
            "keyvault": "hrness",
            "start_feature_index": 2,
            "parallel_width": 1,
            "expected_spec_hash": "a" * 64,
        },
        artifact_paths={},
        repository_roots={"mcp-agents-workflow": "/repos/mawf"},
    )

    assert prepared["argv"][-3:] == [
        "--rebuild", "--expected-spec-hash", "a" * 64,
    ]


def test_workflow_phase_resume_owns_live_runtime_environment():
    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation",
        {
            "repository_key": "united-partners",
            "client": "vivacom",
            "source_run_id": "up-run-123",
            "first_unfinished_phase": "phase-33",
            "reopen_completed_phase": False,
        },
        artifact_paths={},
        repository_roots={"united-partners": "/repos/united-partners"},
    )

    assert prepared["argv"][-6:] == [
        "--client", "vivacom",
        "--resume-run", "up-run-123",
        "--from-phase", "phase-33",
    ]
    assert prepared["environment"]["UP_HARNESS_AGENT_MAX_ATTEMPTS"] == "3"
    assert prepared["environment"]["UP_HARNESS_CODEX_TIMEOUT_SECONDS"] == "600"


def test_remote_onboarding_serializes_confirmation_file(tmp_path):
    confirmation = tmp_path / "confirmation.json"
    confirmation.write_text(
        '{"selectedUserId":"user-1","operation":"create"}',
        encoding="utf-8",
    )
    prepared = sequence_intake_adapters.prepare(
        "remote-mcp-user-onboarding",
        {
            "repository_key": "mcp-agents-workflow",
            "server_url": "wss://workflow.example.test/ws",
            "actor_email": "admin@example.com",
            "action": "create-user-apply",
            "state_file": "/private/tmp/user-admin.json",
            "confirmation_file": str(confirmation),
            "token_output_file": "/private/tmp/user.token",
        },
        artifact_paths={},
        repository_roots={"mcp-agents-workflow": "/repos/mawf"},
    )

    confirmation_index = prepared["argv"].index("--confirmation-json") + 1
    assert prepared["argv"][confirmation_index] == (
        '{"operation":"create","selectedUserId":"user-1"}'
    )
    assert "--token-output-file" in prepared["argv"]


@pytest.mark.parametrize("operation_kind", ["deploy", "workflow-drive", "publish"])
def test_discovery_bootstrap_builds_zero_input_script_spec(operation_kind):
    prepared = sequence_intake_adapters.prepare(
        "discovery-bootstrap",
        {
            "source_repository_key": "memory-knowledge",
            "task_id": "discover-example",
            "operation_kind": operation_kind,
            "date": "2026-07-23",
            "sequence_name": "Example sequence",
            "outcome": "Complete the governed operation.",
            "why_repeatable": "The same operation recurs.",
            "steps": [{
                "step": "run-example",
                "repository_key": "memory-knowledge",
                "script_path": "scripts/example.py",
                "result": "passed",
                "note": "Stops on validation failure.",
            }],
            "has_runtime_dependencies": False,
            "inputs": ["An approved repository checkout."],
            "failure_handling": "Stop and retain failure evidence.",
            "verified_path": "The script passes focused tests.",
            "repo_roots_file": None,
        },
        artifact_paths={"spec": "/private/tmp/bootstrap-spec.json"},
        repository_roots={"memory-knowledge": "/repos/memory"},
    )
    spec = json.loads(prepared["artifacts"]["spec"]["content"])

    assert spec["operation_kind"] == operation_kind
    assert spec["steps"] == [{
        "step": "run-example",
        "command": "python3 scripts/example.py",
        "result": "passed",
        "note": "Stops on validation failure.",
    }]
    assert spec["dependencies"] == [{
        "kind": "file",
        "repository_key": "memory-knowledge",
        "path_or_sequence_id": "scripts/example.py",
    }]


def test_discovery_bootstrap_preserves_non_step_runtime_dependencies():
    prepared = sequence_intake_adapters.prepare(
        "discovery-bootstrap",
        {
            "source_repository_key": "memory-knowledge",
            "task_id": "discover-example",
            "operation_kind": "workflow-drive",
            "date": "2026-08-12",
            "sequence_name": "Example sequence",
            "outcome": "Complete the governed operation.",
            "why_repeatable": "The same operation recurs.",
            "steps": [{
                "step": "run-example",
                "repository_key": "memory-knowledge",
                "script_path": "scripts/example.py",
                "result": "passed",
                "note": "Stops on validation failure.",
            }],
            "has_runtime_dependencies": True,
            "runtime_dependencies": [
                {"repository_key": "memory-knowledge", "path": "scripts/helper.py"},
                {"repository_key": "memory-knowledge", "path": "scripts/example.py"},
            ],
            "inputs": ["An approved repository checkout."],
            "failure_handling": "Stop and retain failure evidence.",
            "verified_path": "The script passes focused tests.",
            "repo_roots_file": None,
        },
        artifact_paths={"spec": "/private/tmp/bootstrap-spec.json"},
        repository_roots={"memory-knowledge": "/repos/memory"},
    )
    spec = json.loads(prepared["artifacts"]["spec"]["content"])

    assert spec["dependencies"] == [
        {
            "kind": "file",
            "repository_key": "memory-knowledge",
            "path_or_sequence_id": "scripts/example.py",
        },
        {
            "kind": "file",
            "repository_key": "memory-knowledge",
            "path_or_sequence_id": "scripts/helper.py",
        },
    ]


def test_discovery_bootstrap_rejects_runtime_dependency_parent_traversal():
    answers = {
        "source_repository_key": "memory-knowledge",
        "task_id": "discover-example",
        "operation_kind": "workflow-drive",
        "date": "2026-08-12",
        "sequence_name": "Example sequence",
        "outcome": "Complete the governed operation.",
        "why_repeatable": "The same operation recurs.",
        "steps": [{
            "step": "run-example",
            "repository_key": "memory-knowledge",
            "script_path": "scripts/example.py",
            "result": "passed",
            "note": "Stops on validation failure.",
        }],
        "has_runtime_dependencies": True,
        "runtime_dependencies": [{
            "repository_key": "memory-knowledge",
            "path": "../outside.py",
        }],
        "inputs": ["An approved repository checkout."],
        "failure_handling": "Stop and retain failure evidence.",
        "verified_path": "The script passes focused tests.",
        "repo_roots_file": None,
    }

    with pytest.raises(
        sequence_intake_adapters.AdapterError,
        match="invalid-bootstrap-runtime-dependency-path",
    ):
        sequence_intake_adapters.prepare(
            "discovery-bootstrap",
            answers,
            artifact_paths={"spec": "/private/tmp/bootstrap-spec.json"},
            repository_roots={"memory-knowledge": "/repos/memory"},
        )


def test_all_27_intake_specs_validate_with_complete_question_contracts():
    roots = {
        key: f"/repos/{key}" for key in (
            "memory-knowledge", "mcp-agents-workflow", "taggable-api",
            "taggable-admin-spa", "callcenter-harness", "united-partners",
        )
    }

    for sequence_id in sequence_intake_adapters.CANONICAL_SEQUENCE_IDS:
        script_intake._validate_spec(
            sequence_intake_adapters.intake_spec(
                sequence_id, repository_roots=roots,
            )
        )


def test_local_image_health_derives_port_file_invocation():
    prepared = sequence_intake_adapters.prepare(
        "local-workflow-orch-image",
        {
            "operation": "health",
            "source_repository_key": "mcp-agents-workflow",
            "health_location": "port-file",
            "health_port_file": "/private/tmp/workflow-orch.port",
            "timeout_seconds": 180,
        },
        artifact_paths={},
        repository_roots={"mcp-agents-workflow": "/repos/mawf"},
    )

    assert prepared["argv"] == [
        "uv", "run", "python",
        "/repos/mawf/scripts/local_workflow_orch_image_harness.py",
        "health",
        "--port-file", "/private/tmp/workflow-orch.port",
        "--timeout-seconds", "180",
    ]
    assert prepared["authorization"]["effectful"] is False


def test_local_image_seed_git_derives_fixed_restart_health_shape():
    prepared = sequence_intake_adapters.prepare(
        "local-workflow-orch-image",
        {
            "operation": "seed-git-auth",
            "source_repository_key": "mcp-agents-workflow",
            "container": "workflow-orch-local-sequence-check",
            "keyvault_name": "hrness",
            "git_repository_key": "memory-knowledge",
            "seed_port_file": "/private/tmp/workflow-orch.port",
            "seed_timeout_seconds": 180,
        },
        artifact_paths={},
        repository_roots={"mcp-agents-workflow": "/repos/mawf"},
    )

    assert prepared["argv"][-8:] == [
        "--keyvault-name", "hrness",
        "--repository-key", "memory-knowledge",
        "--port-file", "/private/tmp/workflow-orch.port",
        "--health-timeout-seconds", "180",
    ]
    assert prepared["authorization"]["effectful"] is True


def test_greenfield_validate_fresh_derives_checkpoint_resume_contract():
    prepared = sequence_intake_adapters.prepare(
        "greenfield-full-drive",
        {
            "mode": "validate-fresh",
            "source_repository_key": "mcp-agents-workflow",
            "target_repository": "github:owner/repository",
            "branch": "validation",
            "tag": "gf-local",
            "container": "workflow-orch-local-sequence-check",
            "port": 18082,
            "env_file": "/private/tmp/workflow-orch.env",
            "skip_build": False,
            "skip_auth": False,
            "keyvault_name": "hrness",
            "start_feature_index": 0,
            "parallel_width": 1,
            "decomposition_task_id": "task-123",
            "decomposition_run_id": "run-123",
            "program_drive_id": "01234567-89ab-cdef-0123-456789abcdef",
            "expected_spec_hash": "a" * 64,
        },
        artifact_paths={},
        repository_roots={"mcp-agents-workflow": "/repos/mawf"},
    )

    assert prepared["argv"][-10:] == [
        "--decomposition-task-id", "task-123",
        "--decomposition-run-id", "run-123",
        "--resume-from-checkpoint",
        "--program-drive-id", "01234567-89ab-cdef-0123-456789abcdef",
        "--expected-spec-hash", "a" * 64,
        "--validate-fresh",
    ]
    assert prepared["profile"] == "validate-fresh"


def test_greenfield_start_derives_spec_path_from_registered_root():
    prepared = sequence_intake_adapters.prepare(
        "greenfield-full-drive",
        {
            "mode": "start-from-spec",
            "source_repository_key": "mcp-agents-workflow",
            "target_repository": "github:owner/repository",
            "branch": "main",
            "tag": "gf-local",
            "container": "workflow-orch-local-sequence-check",
            "port": 18082,
            "env_file": "/private/tmp/workflow-orch.env",
            "skip_build": True,
            "skip_auth": True,
            "fresh": True,
            "start_feature_index": 0,
            "parallel_width": 1,
            "spec_repository_key": "memory-knowledge",
            "spec_relative_path": "Tasks/example/spec.json",
        },
        artifact_paths={},
        repository_roots={
            "mcp-agents-workflow": "/repos/mawf",
            "memory-knowledge": "/repos/memory",
        },
    )

    assert prepared["argv"][0] == "/repos/mawf/scripts/greenfield_full_drive.sh"
    assert prepared["argv"][-4:] == [
        "--skip-build", "--skip-auth",
        "--spec", "/repos/memory/Tasks/example/spec.json",
    ]


def test_claude_verify_derives_repeated_target_flags():
    prepared = sequence_intake_adapters.prepare(
        "claude-auth-token-refresh",
        {
            "operation": "verify",
            "source_repository_key": "mcp-agents-workflow",
            "container": "workflow-orch-local-sequence-check",
            "keyvault_name": "hrness",
            "deployment": "https://workflow.example.test",
            "verify_targets": ["local-container", "remote-claude"],
            "dry_run": False,
        },
        artifact_paths={},
        repository_roots={"mcp-agents-workflow": "/repos/mawf"},
    )

    assert prepared["argv"][-4:] == [
        "--verify-targets", "local-container",
        "--verify-targets", "remote-claude",
    ]
    assert prepared["authorization"]["effectful"] is False


def test_claude_all_uses_credential_path_without_credential_contents():
    prepared = sequence_intake_adapters.prepare(
        "claude-auth-token-refresh",
        {
            "operation": "all",
            "source_repository_key": "mcp-agents-workflow",
            "credential_source": "runtime-temp-file",
            "token_file": "/private/tmp/claude-oat.txt",
            "config_source": "none",
            "container": "workflow-orch-local-sequence-check",
            "keyvault_name": "hrness",
            "deployment": "https://workflow.example.test",
            "dry_run": False,
        },
        artifact_paths={},
        repository_roots={"mcp-agents-workflow": "/repos/mawf"},
    )

    assert "--token-file" in prepared["argv"]
    assert prepared["argv"][
        prepared["argv"].index("--token-file") + 1
    ] == "/private/tmp/claude-oat.txt"
    assert prepared["authorization"]["effectful"] is True


def test_airgapped_stt_derives_model_environment_and_audio_position():
    prepared = sequence_intake_adapters.prepare(
        "airgapped-local-bulgarian-stt",
        {
            "operation": "verify",
            "source_repository_key": "callcenter-harness",
            "model": "small",
            "audio": "/recordings/call.wav",
        },
        artifact_paths={},
        repository_roots={"callcenter-harness": "/repos/callcenter"},
    )

    assert prepared["argv"] == [
        "/repos/callcenter/scripts/setup_airgapped_stt.sh",
        "verify",
        "/recordings/call.wav",
    ]
    assert prepared["environment"] == {"STT_MODEL": "small"}


def test_airgapped_judge_smoke_derives_private_environment_contract():
    prepared = sequence_intake_adapters.prepare(
        "airgapped-llm-judge",
        {
            "operation": "smoke",
            "source_repository_key": "callcenter-harness",
            "model": "qwen2.5:32b",
            "audio": "/recordings/call.wav",
        },
        artifact_paths={},
        repository_roots={"callcenter-harness": "/repos/callcenter"},
    )

    assert prepared["argv"][-2:] == [
        "/repos/callcenter/scripts/cc_command_eval_smoke.py",
        "/recordings/call.wav",
    ]
    assert prepared["environment"]["CC_HARNESS_AGENT_COMMAND"] == (
        "python3 /repos/callcenter/scripts/judge_ollama.py "
        "--model qwen2.5:32b"
    )
    assert prepared["environment"]["HF_HUB_OFFLINE"] == "1"


def test_local_multimodal_benchmark_derives_spec_from_semantic_inputs(
    tmp_path: Path,
) -> None:
    script_intake._validate_spec(sequence_intake_adapters.intake_spec(
        "local-multimodal-model-benchmark",
        repository_roots={"memory-knowledge": "/repos/memory"},
    ))
    source = tmp_path / "dashboard.png"
    source.write_bytes(b"image")
    schema = tmp_path / "response-schema.json"
    schema.write_text(json.dumps({
        "type": "object",
        "required": ["elements"],
        "properties": {
            "elements": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
    }))
    output = tmp_path / "evidence.json"
    artifact = tmp_path / "benchmark-spec.json"

    prepared = sequence_intake_adapters.prepare(
        "local-multimodal-model-benchmark",
        {
            "source_repository_key": "memory-knowledge",
            "model": "gemma4:26b-mlx",
            "endpoint": "http://127.0.0.1:11434",
            "pull_if_missing": True,
            "thinking_mode": "disabled",
            "timeout_seconds": 600,
            "context_length": 32768,
            "output_path": str(output),
            "cases": [{
                "id": "annotation-map",
                "prompt": "Return the visible annotations.",
                "source_files": [str(source)],
                "response_schema_file": str(schema),
            }],
        },
        artifact_paths={"benchmark_spec": str(artifact)},
        repository_roots={"memory-knowledge": "/repos/memory"},
    )

    spec = json.loads(prepared["artifacts"]["benchmark_spec"]["content"])
    assert spec == {
        "schema_version": 1,
        "model": "gemma4:26b-mlx",
        "endpoint": "http://127.0.0.1:11434",
        "pull_if_missing": True,
        "think": False,
        "timeout_seconds": 600,
        "output_path": str(output),
        "options": {"temperature": 0, "num_ctx": 32768},
        "cases": [{
            "id": "annotation-map",
            "prompt": "Return the visible annotations.",
            "source_files": [str(source)],
            "response_schema": json.loads(schema.read_text()),
        }],
    }
    assert prepared["argv"] == [
        "python3",
        "/repos/memory/scripts/local_multimodal_model_benchmark.py",
        "--spec",
        str(artifact),
    ]
    assert prepared["authorization"] == {
        "effectful": True,
        "required": True,
        "operation": "run",
    }


def test_local_multimodal_benchmark_rejects_non_loopback_endpoint(
    tmp_path: Path,
) -> None:
    source = tmp_path / "dashboard.jpg"
    source.write_bytes(b"image")
    schema = tmp_path / "response-schema.json"
    schema.write_text('{"type":"object"}')

    with pytest.raises(
        sequence_intake_adapters.AdapterError,
        match="local-multimodal-benchmark-invalid:endpoint-not-loopback",
    ):
        sequence_intake_adapters.prepare(
            "local-multimodal-model-benchmark",
            {
                "source_repository_key": "memory-knowledge",
                "model": "gemma4:26b-mlx",
                "endpoint": "https://models.example.com",
                "pull_if_missing": False,
                "thinking_mode": "disabled",
                "timeout_seconds": 60,
                "context_length": 8192,
                "output_path": str(tmp_path / "evidence.json"),
                "cases": [{
                    "id": "case",
                    "prompt": "Read the image.",
                    "source_files": [str(source)],
                    "response_schema_file": str(schema),
                }],
            },
            artifact_paths={"benchmark_spec": str(tmp_path / "spec.json")},
            repository_roots={"memory-knowledge": "/repos/memory"},
        )


def test_local_multimodal_benchmark_collects_one_semantic_answer_at_a_time(
    tmp_path: Path,
) -> None:
    source = tmp_path / "dashboard.png"
    source.write_bytes(b"image")
    schema = tmp_path / "response-schema.json"
    schema.write_text('{"type":"object"}')
    output = tmp_path / "evidence.json"
    prompts: list[str] = []
    answers = iter([
        "memory-knowledge",
        "gemma4:26b-mlx",
        "",  # default loopback endpoint
        "",  # default pull-if-missing
        "disabled",
        "",  # default timeout
        "",  # default context length
        str(output),
        "annotation-map",
        "Read every annotation.",
        ".",
        str(source),
        "no",  # no additional source image
        str(schema),
        "no",  # no additional benchmark case
    ])

    prepared = sequence_intake_adapters.collect_and_prepare(
        "local-multimodal-model-benchmark",
        artifact_paths={"benchmark_spec": str(tmp_path / "spec.json")},
        repository_roots={"memory-knowledge": "/repos/memory"},
        input_fn=lambda prompt: prompts.append(prompt) or next(answers),
        output_fn=lambda _message: None,
    )

    assert prepared["profile"] == "run"
    shown = [prompt for prompt in prompts if prompt]
    assert len(shown) == 14
    assert all("Question:" in prompt for prompt in shown)
    assert all("Response format:" in prompt for prompt in shown)
    assert all("Constraints:" in prompt for prompt in shown)


def test_secure_landing_scrub_derives_fail_closed_retirement_invocation():
    prepared = sequence_intake_adapters.prepare(
        "secure-landing-seed",
        {
            "operation": "scrub",
            "source_repository_key": "callcenter-harness",
            "landing_directory": "/secure/landing",
            "scrub_scope": "one-recording",
            "recording": "call.wav",
        },
        artifact_paths={},
        repository_roots={"callcenter-harness": "/repos/callcenter"},
    )

    assert prepared["argv"][-2:] == [
        "/repos/callcenter/scripts/scrub_and_retire.py",
        "call.wav",
    ]
    assert prepared["environment"]["LANDING"] == "/secure/landing"
    assert prepared["authorization"]["effectful"] is True


def test_engine_invariant_unit_profile_is_read_only():
    prepared = sequence_intake_adapters.prepare(
        "callcenter-harness-engine-invariants",
        {
            "operation": "unit",
            "source_repository_key": "callcenter-harness",
        },
        artifact_paths={},
        repository_roots={"callcenter-harness": "/repos/callcenter"},
    )

    assert prepared["argv"] == [
        "python3", "/repos/callcenter/scripts/test_engine_upgrades.py",
    ]
    assert prepared["environment"]["PYTHONPATH"] == "/repos/callcenter/src"
    assert prepared["authorization"]["effectful"] is False


def test_every_registered_sequence_has_an_adapter_and_intake_spec():
    assert all(
        adapter is not None
        for adapter in sequence_intake_adapters.ADAPTER_REGISTRY.values()
    )
    assert set(sequence_intake_adapters.INTAKE_SPECS) == set(
        sequence_intake_adapters.ADAPTER_REGISTRY
    )


ROOT = Path(__file__).resolve().parent.parent


def _copy_contract_fixture(base: Path) -> list[tuple[str, Path]]:
    (base / "operations/sequences").mkdir(parents=True)
    (base / "operations/sequences/SEQUENCES.md").write_text(
        (ROOT / "operations/sequences/SEQUENCES.md").read_text()
    )
    local_rows = []
    stored = json.loads((ROOT / sequence_intake_adapters.INTAKE_CONTRACTS_PATH).read_text())
    for row in stored["entries"]:
        if row.get("entrypoint_source_sha256"):
            rel = row["entrypoint"].split(":", 1)[1].split()[0]
            target = base / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / rel).read_bytes())
            local_rows.append((row["sequence_id"], target))
    return local_rows


def test_every_runnable_registered_sequence_has_a_current_contract():
    stored = json.loads((ROOT / sequence_intake_adapters.INTAKE_CONTRACTS_PATH).read_text())
    rebuilt = sequence_intake_adapters.build_intake_contracts(ROOT)
    assert stored == rebuilt
    assert sequence_intake_adapters.check_intake_contracts(ROOT) == []
    covered = {row["sequence_id"] for row in stored["entries"]}
    runnable = {
        sequence_id
        for sequence_id, adapter in sequence_intake_adapters.ADAPTER_REGISTRY.items()
        if adapter is not None
    }
    assert covered == runnable
    for row in stored["non_runnable"]:
        assert row["reason"].strip()
    for row in stored["entries"]:
        assert row.get("entrypoint_source_sha256") or row.get("entrypoint_source_receipt"), (
            f"{row['sequence_id']} has no source binding"
        )


def test_changed_required_caller_parameter_fails_closed(tmp_path: Path):
    import copy

    _copy_contract_fixture(tmp_path)
    stored = sequence_intake_adapters.build_intake_contracts(tmp_path)
    path = tmp_path / sequence_intake_adapters.INTAKE_CONTRACTS_PATH
    path.write_text(json.dumps(stored, sort_keys=True))
    assert sequence_intake_adapters.check_intake_contracts(tmp_path) == []
    mutated = copy.deepcopy(stored)
    target_row = next(row for row in mutated["entries"] if row["required_inputs"])
    target_row["required_inputs"] = target_row["required_inputs"][1:]
    path.write_text(json.dumps(mutated, sort_keys=True))
    drift = sequence_intake_adapters.check_intake_contracts(tmp_path)
    assert any(target_row["sequence_id"] in error for error in drift), drift


def test_changed_entrypoint_source_invalidates_contract(tmp_path: Path):
    local_rows = _copy_contract_fixture(tmp_path)
    stored = sequence_intake_adapters.build_intake_contracts(tmp_path)
    path = tmp_path / sequence_intake_adapters.INTAKE_CONTRACTS_PATH
    path.write_text(json.dumps(stored, sort_keys=True))
    assert sequence_intake_adapters.check_intake_contracts(tmp_path) == []
    sequence_id, target = local_rows[0]
    target.write_bytes(target.read_bytes() + b"\n# drifted\n")
    drift = sequence_intake_adapters.check_intake_contracts(tmp_path)
    assert any(sequence_id in error for error in drift), drift
