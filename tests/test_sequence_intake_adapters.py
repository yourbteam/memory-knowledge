from __future__ import annotations

import hashlib
import json
import os
import tempfile
from types import SimpleNamespace
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
            "client_answers_path": None,
            "debrief_feedback_path": None,
            "final_brief_feedback_path": None,
            "gate_approvals_path": None,
            "corrected_topic_policies_path": None,
            "step11_writer_input_path": None,
            "step11_writer_call_budget_path": None,
            "step11_writer_call_limit": None,
            "step11_writer_call_extension_from": None,
            "step9_rehearsal_task_dir": None,
            "step9_native_writer_call_limit": None,
            "step9_native_writer_continuation": None,
            "step9_native_writer_extend_to": None,
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


def _step11_resume_answers() -> dict:
    return {
        "repository_key": "united-partners",
        "client": "vivacom",
        "source_run_id": "up-run-123",
        "first_unfinished_phase": "compose-annual-review",
        "reopen_completed_phase": False,
        "client_answers_path": None,
        "debrief_feedback_path": None,
        "final_brief_feedback_path": None,
        "gate_approvals_path": None,
        "corrected_topic_policies_path": None,
        "step11_writer_input_path": "/runs/source/step11-input.json",
        "step11_writer_call_budget_path": "/runs/shared/writer-budget.json",
        "step11_writer_call_limit": 12,
        "step11_writer_call_extension_from": None,
        "step9_rehearsal_task_dir": None,
        "step9_native_writer_call_limit": None,
        "step9_native_writer_continuation": None,
        "step9_native_writer_extend_to": None,
    }

def test_recorded_step11_route_uses_current_copy_and_spoken_hold(tmp_path, monkeypatch):
    repository = tmp_path / "united-partners"
    target = repository / "Tasks/bteam-step11-clean-20261002"
    route = {"status": "held", "run_id": "up-run-317105ac557e",
             "source_run_id": "up-run-e92f828d648d", "phase": "annual-review-gate",
             "task_dir": str(target), "copy_dir": str(target)}

    def selected(argv, **_kwargs):
        assert "--resolve-recorded-route" in argv
        return SimpleNamespace(returncode=0, stdout=json.dumps(route))

    monkeypatch.setattr(sequence_intake_adapters.subprocess, "run", selected)
    answers = _step11_resume_answers()
    answers.update({"client": "bteam", "source_run_id": sequence_intake_adapters.STEP11_RECORDED_SOURCE,
                    "step11_writer_input_path": None, "step11_writer_call_budget_path": None,
                    "step11_writer_call_limit": None})
    roots = {"united-partners": str(repository)}

    def prepare():
        return sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots=roots)

    prepared = prepare()
    assert prepared["argv"][-3:] == ["-m", "up_harness.step11_maria_package", "--close-recorded"]
    assert prepared["environment"] == {"PYTHONPATH": "src:."}
    answers["step11_held_by"] = "Kamen Kamenov"
    with pytest.raises(sequence_intake_adapters.AdapterError, match="hold is due only"):
        prepare()
    route["status"] = "awaiting-human"
    prepared = prepare()
    assert prepared["argv"][-3:] == ["--held-by", "Kamen Kamenov", "--confirmed-held"]
    route["copy_dir"] = str(repository / "Tasks/vivacom-step11-clean-20261002")
    with pytest.raises(sequence_intake_adapters.AdapterError, match="wrong source or copy identity"):
        prepare()

def test_recorded_step11_route_refuses_unfinished_feedback_before_zip(tmp_path, monkeypatch):
    repository = tmp_path / "united-partners"
    target = repository / "Tasks/bteam-step11-clean-20261002"
    route = {"status": "feedback-pending", "run_id": "up-run-317105ac557e",
             "source_run_id": "up-run-e92f828d648d", "phase": "annual-review-gate",
             "task_dir": str(target), "copy_dir": str(target),
             "feedback_state": [{"note_sha256": "a" * 64,
                                 "needs_routing": ["REVIEW:0"],
                                 "needs_approval": ["ONEPAGER:1"],
                                 "needs_other_work": []}]}
    monkeypatch.setattr(sequence_intake_adapters.subprocess, "run", lambda *_a, **_k:
                        SimpleNamespace(returncode=0, stdout=json.dumps(route)))
    answers = _step11_resume_answers()
    answers.update({"client": "bteam", "source_run_id": sequence_intake_adapters.STEP11_RECORDED_SOURCE,
                    "step11_writer_input_path": None, "step11_writer_call_budget_path": None,
                    "step11_writer_call_limit": None})
    def prepare():
        return sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots={"united-partners": str(repository)})

    with pytest.raises(sequence_intake_adapters.AdapterError,
                       match="route REVIEW:0; approve ONEPAGER:1.*before resume or ZIP closeout"):
        prepare()
    route["feedback_state"] = []
    with pytest.raises(sequence_intake_adapters.AdapterError, match="feedback state is invalid"):
        prepare()

def test_recorded_step11_feedback_budget_needs_explicit_higher_limit(tmp_path, monkeypatch):
    repository = tmp_path / "united-partners"
    target = repository / "Tasks/bteam-step11-clean-20261002"
    route = {"status": "awaiting-writer-budget", "run_id": "up-run-317105ac557e",
             "source_run_id": "up-run-e92f828d648d", "phase": "compose-annual-review",
             "task_dir": str(target), "copy_dir": str(target),
             "feedback": {"note_sha256": "a" * 64},
             "writer_call_budget": {"limit": 150, "reserved_calls": 150}}
    monkeypatch.setattr(sequence_intake_adapters.subprocess, "run", lambda *_a, **_k:
                        SimpleNamespace(returncode=0, stdout=json.dumps(route)))
    answers = _step11_resume_answers()
    answers.update({"client": "bteam", "source_run_id": sequence_intake_adapters.STEP11_RECORDED_SOURCE,
                    "step11_writer_input_path": None, "step11_writer_call_budget_path": None,
                    "step11_writer_call_limit": None})
    def prepare():
        return sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots={"united-partners": str(repository)})

    with pytest.raises(sequence_intake_adapters.AdapterError, match="150/150.*higher"):
        prepare()
    answers["step11_writer_call_limit"] = 150
    with pytest.raises(sequence_intake_adapters.AdapterError, match="150/150.*higher"):
        prepare()
    answers["step11_writer_call_limit"] = 170
    prepared = prepare()
    assert prepared["argv"][-2:] == ["--writer-call-limit", "170"]
    route["status"] = "held"
    with pytest.raises(sequence_intake_adapters.AdapterError, match="due only for exhausted"):
        prepare()

def test_recorded_step11_route_records_only_explicit_step10_holder(tmp_path, monkeypatch):
    repository = tmp_path / "united-partners"
    target = repository / "Tasks/bteam-step11-clean-987a48b570f9"
    route = {"status": "awaiting-step10-hold", "run_id": "up-run-97151ae196f2",
             "source_run_id": "up-run-e92f828d648d", "phase": "measurement-gate",
             "task_dir": str(target), "copy_dir": str(target)}
    monkeypatch.setattr(sequence_intake_adapters.subprocess, "run", lambda *_a, **_k:
                        SimpleNamespace(returncode=0, stdout=json.dumps(route)))
    answers = _step11_resume_answers()
    answers.update({"client": "bteam", "source_run_id": sequence_intake_adapters.STEP11_RECORDED_SOURCE,
                    "step11_writer_input_path": None, "step11_writer_call_budget_path": None,
                    "step11_writer_call_limit": None})
    roots = {"united-partners": str(repository)}

    def prepare():
        return sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots=roots)

    with pytest.raises(sequence_intake_adapters.AdapterError, match="explicit named holder and reason"):
        prepare()
    answers.update({"step10_held_by": "Kamen Kamenov", "step10_hold_reason": "requirements met"})
    prepared = prepare()
    assert prepared["argv"][-7:] == ["--client", "bteam", "--held-by", "Kamen Kamenov",
                                    "--reason", "requirements met", "--confirmed-held"]
    assert prepared["environment"] == {"PYTHONPATH": "src:."}
    route["status"] = "ready"
    with pytest.raises(sequence_intake_adapters.AdapterError, match="due only at the measurement gate"):
        prepare()

def test_registered_step10_route_selects_exact_held_step9_child_and_measurement_boundary(tmp_path, monkeypatch):
    repository = tmp_path / "united-partners"
    tasks = repository / "Tasks"
    target = tasks / "bteam-step9-clean-a291af445ac4"
    route = {"status": "ready", "source_run_id": "up-run-46b07687775f",
             "step8_root_run_id": "up-run-a291af445ac4",
             "run_id": "up-run-46b07687775f", "phase": "compose-measurement-framework",
             "task_dir": str(target), "copy_dir": str(target)}

    def selected(argv, **_kwargs):
        assert "--resolve-step10-route" in argv
        return SimpleNamespace(returncode=0, stdout=json.dumps(route))

    monkeypatch.setattr(sequence_intake_adapters.subprocess, "run", selected)
    answers = _step11_resume_answers()
    answers.update({"client": "bteam", "source_run_id": sequence_intake_adapters.STEP10_RECORDED_SOURCE,
                    "first_unfinished_phase": "compose-measurement-framework",
                    "reopen_completed_phase": False,
                    "step11_writer_input_path": None, "step11_writer_call_budget_path": None,
                    "step11_writer_call_limit": None})
    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation", answers,
        artifact_paths={}, repository_roots={"united-partners": str(repository)})
    assert prepared["argv"][prepared["argv"].index("--resume-run") + 1] == route["run_id"]
    assert prepared["argv"][prepared["argv"].index("--from-phase") + 1] == route["phase"]
    assert prepared["argv"][-2:] == ["--task-dir", str(target)]
    assert "--rerun-completed" not in prepared["argv"]
    assert prepared["environment"]["UP_HARNESS_AGENT_COMMAND"].endswith(
        "scripts/codex_role_command.py"
    )
    assert prepared["environment"]["UP_HARNESS_AGENT_MAX_ATTEMPTS"] == "1"
    assert prepared["environment"]["UP_HARNESS_AGENT_TIMEOUT_SECONDS"] == "600"
    assert prepared["environment"]["UP_HARNESS_CODEX_TIMEOUT_SECONDS"] == "600"
    assert prepared["environment"]["UP_HARNESS_GOOGLE_DRIVE_ROOT"] == str(target / "drive-staging")
    assert prepared["environment"]["UP_HARNESS_GOOGLE_DRIVE_ACCESS_TOKEN"] == ""
    assert prepared["environment"]["UP_HARNESS_GOOGLE_DRIVE_PARENT_ID"] == ""

    route.update(run_id="up-run-eeeeeeeeeeee", phase="measurement-gate")
    gate = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation", answers,
        artifact_paths={}, repository_roots={"united-partners": str(repository)})
    assert gate["argv"][gate["argv"].index("--from-phase") + 1] == "measurement-gate"
    assert gate["environment"] == prepared["environment"]

def test_recorded_step9_route_selects_current_step8_hold_and_package(tmp_path, monkeypatch):
    repository = tmp_path / "united-partners"
    tasks = repository / "Tasks"
    source = tasks / "bteam-step8-clean-b2224d839ce5"
    target = tasks / "bteam-step9-clean-a291af445ac4"
    target.joinpath("record").mkdir(parents=True)
    route = {"status": "ready", "source_run_id": "up-run-a291af445ac4",
             "run_id": "up-run-a291af445ac4", "phase": "compose-execution-toolkit",
             "task_dir": str(source), "copy_dir": str(target)}

    recorded_events = {"available": False}

    def selected(argv, **_kwargs):
        if "--admit-decision-reopen" in argv:
            return SimpleNamespace(returncode=0, stdout=json.dumps({
                "mode": "reopen" if route["phase"] == "toolkit-ship-gate" else "resume",
                "recorded_events": ({"newsroom_model": "a", "earned_led_resourcing": "b"}
                                    if recorded_events["available"] else {})}))
        if argv[-1] == "vivacom":
            other = {"status": "held", "source_run_id": "up-run-6f77e6806f8c",
                     "run_id": "up-run-cccccccccccc", "phase": "toolkit-ship-gate",
                     "task_dir": str(tasks / "vivacom-step9-clean-6f77e6806f8c"),
                     "copy_dir": str(tasks / "vivacom-step9-clean-6f77e6806f8c")}
            return SimpleNamespace(returncode=0, stdout=json.dumps(other))
        return SimpleNamespace(returncode=0, stdout=json.dumps(route))

    monkeypatch.setattr(sequence_intake_adapters.subprocess, "run", selected)
    answers = _step11_resume_answers()
    answers.update({"client": "bteam", "source_run_id": sequence_intake_adapters.STEP9_RECORDED_SOURCE,
                    "first_unfinished_phase": "compose-execution-toolkit",
                    "step11_writer_input_path": None, "step11_writer_call_budget_path": None,
                    "step11_writer_call_limit": None})
    roots = {"united-partners": str(repository)}

    def prepare():
        return sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots=roots)

    ready = prepare()
    assert ready["argv"][-2:] == ["--task-dir", str(source)]
    assert ready["environment"]["UP_HARNESS_GOOGLE_DRIVE_ROOT"] == str(target / "drive-staging")
    questions = []

    def answer(question):
        label = question.splitlines()[0].removeprefix("Question: ")
        questions.append(label)
        return {"United Partners repository": "united-partners",
                "Client configuration key": "bteam",
                "Persisted source run identity": sequence_intake_adapters.STEP9_RECORDED_SOURCE,
                "Step 9 reviewer holding this toolkit": "",
                "Step 9 toolkit altitude holder check": "",
                "Step 9 newsroom model decision": "",
                "Step 9 earned-pipeline decision": "",
                "Person making both Step 9 operating decisions": ""}[label]

    collected = sequence_intake_adapters.collect_and_prepare(
        "workflow-resume-from-phase-live-confirmation", artifact_paths={},
        repository_roots=roots, input_fn=answer, output_fn=lambda _: None)
    assert collected["argv"] == ready["argv"] and len(questions) == 8
    route.update(status="ready", run_id="up-run-bbbbbbbbbbbb",
                 phase="toolkit-ship-gate", task_dir=str(target))
    answers["step9_newsroom_model"] = "A phased build that stands the newsroom up before the platform leans on it"
    answers["step9_earned_pipeline"] = "United Partners produces a weekly earned pipeline"
    answers["step9_decided_by"] = "Kamen Kamenov"
    deciding = prepare()
    assert deciding["argv"][deciding["argv"].index("--from-phase") + 1] == "compose-execution-toolkit"
    assert "--rerun-completed" in deciding["argv"]
    assert "--step9-earned-pipeline" in deciding["argv"]
    route.update(phase="compose-execution-toolkit")
    early = prepare()
    assert early["argv"][early["argv"].index("--from-phase") + 1] == "compose-execution-toolkit"
    assert "--rerun-completed" not in early["argv"]
    route.update(phase="toolkit-ship-gate")
    answers["step9_newsroom_model"] = None
    answers["step9_earned_pipeline"] = None
    answers["step9_decided_by"] = None
    recorded_events["available"] = True
    carried = prepare()
    assert "--step9-use-recorded-decisions" in carried["argv"]
    assert "--rerun-completed" in carried["argv"]
    assert "--step9-newsroom-model" not in carried["argv"]
    route.update(phase="compose-execution-toolkit")
    early_carried = prepare()
    assert "--step9-use-recorded-decisions" in early_carried["argv"]
    assert "--rerun-completed" not in early_carried["argv"]
    recorded_events["available"] = False
    route.update(phase="toolkit-ship-gate")
    check = target / "record/toolkit-altitude-check.json"
    check.write_text("{}")
    answers["step9_altitude_check_path"] = str(check)
    gated = prepare()
    assert gated["argv"][-2:] == ["--task-dir", str(target)]
    altitude_index = gated["argv"].index("--altitude-check-file")
    assert gated["argv"][altitude_index:altitude_index + 2] == ["--altitude-check-file", str(check)]
    answers["step9_altitude_check_path"] = None
    route["status"] = "awaiting-human"
    answers["step9_held_by"] = "Kamen"
    assert "up_harness.step9_review_hold" in prepare()["argv"]
    answers["step9_held_by"] = None
    with pytest.raises(sequence_intake_adapters.AdapterError, match="explicit named hold"):
        prepare()
    route["status"] = "held"
    assert "up_harness.step9_maria_package" in prepare()["argv"]
    route["copy_dir"] = str(tasks / "bteam-step9-clean-wrong")
    with pytest.raises(sequence_intake_adapters.AdapterError, match="wrong identity"):
        prepare()

@pytest.mark.parametrize("client,code,name", [
    ("bteam", "BTM", "The B Team"),
    ("vivacom", "VIV", "Vivacom"),
])
def test_step1_signed_review_routes_only_matching_copy_and_source(tmp_path, client, code, name):
    repository = tmp_path / "united-partners"
    copy = repository / "Tasks" / f"{client}-step1-clean-demo"
    (copy / "state").mkdir(parents=True)
    (copy / "record").mkdir()
    source = {
        "run_id": "up-run-step1", "status": "blocked",
        "context": {"inputs": {
            "client_code": code, "client_name": name,
            "stop_after_phase": "operator-review-of-pre-engagement-pack",
        }},
        "phases": {"operator-review-of-pre-engagement-pack": {"status": "completed"}},
    }
    state_path = copy / "state" / "up-run-step1.json"
    state_path.write_text(json.dumps(source), encoding="utf-8")
    reply = tmp_path / f"{client}-signed.docx"
    reply.write_bytes(b"signed reply fixture")
    answers = _step11_resume_answers()
    answers.update({
        "client": client, "source_run_id": "up-run-step1",
        "first_unfinished_phase": "operator-review-of-pre-engagement-pack",
        "reopen_completed_phase": True,
        "step1_clean_task_dir": str(copy), "step1_signed_reply_path": str(reply),
        "step11_writer_input_path": None, "step11_writer_call_budget_path": None,
        "step11_writer_call_limit": None,
    })
    roots = {"united-partners": str(repository)}

    def prepare():
        return sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots=roots,
        )

    prepared = prepare()
    assert prepared["argv"][-4:] == [
        "--task-dir", str(copy.resolve()), "--operator-review-reply-file", str(reply.resolve()),
    ]
    assert "--rerun-completed" in prepared["argv"]
    assert prepared["environment"]["UP_HARNESS_GOOGLE_DRIVE_ROOT"] == str(copy.resolve() / "drive-staging")
    assert prepared["environment"]["UP_HARNESS_GOOGLE_DRIVE_ACCESS_TOKEN"] == ""
    assert prepared["environment"]["UP_HARNESS_AGENT_MAX_ATTEMPTS"] == "2"

    answers["first_unfinished_phase"] = "pre-engagement-gate"
    with pytest.raises(sequence_intake_adapters.AdapterError, match="completed-review-reopen"):
        prepare()
    answers["first_unfinished_phase"] = "operator-review-of-pre-engagement-pack"
    answers["client"] = "vivacom" if client == "bteam" else "bteam"
    with pytest.raises(sequence_intake_adapters.AdapterError, match="copy-mismatch"):
        prepare()
    answers["client"] = client
    source["context"]["inputs"]["client_code"] = "VIV" if client == "bteam" else "BTM"
    state_path.write_text(json.dumps(source), encoding="utf-8")
    with pytest.raises(sequence_intake_adapters.AdapterError, match="source-mismatch"):
        prepare()

def test_step7_clean_copy_routes_exact_manifest_and_refuses_changed_source(tmp_path):
    repository = tmp_path / "united-partners"
    copy = repository / "Tasks" / "bteam-step7-clean-20261006"
    (copy / "state").mkdir(parents=True)
    (copy / "record").mkdir()
    hold = {"verdict": "held", "run_id": "up-run-step6"}
    hold_sha = hashlib.sha256((json.dumps(hold, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")) + "\n").encode()).hexdigest()
    state = {"run_id": "up-run-step6", "context": {"inputs": {
        "stop_after_phase": "narrative-gate", "step7_writer_call_limit": 60,
        "step7_source_admission": {"schema": "step7-held-step6-source/v1",
            "source_run_id": "up-run-step6", "source_state_sha256": "a" * 64,
            "step6_hold_sha256": hold_sha}},
        "up": {"cd_s_002": {"step6_review_hold": hold}}},
        "phases": {"strategy-approach-gate": {
            "status": "completed", "ledger": {"status": "passed"}}}}
    state_bytes = (json.dumps(state, indent=2) + "\n").encode()
    (copy / "state/up-run-step6.json").write_bytes(state_bytes)
    manifest = {"schema": "step7-clean-copy/v1", "client": "bteam",
        "source_run_id": "up-run-step6", "source_state_sha256": "a" * 64,
        "clean_state_sha256": hashlib.sha256(state_bytes).hexdigest(),
        "first_phase": "compose-big-idea", "stop_after_phase": "narrative-gate",
        "writer_call_limit": 60, "source_review_hold_sha256": hold_sha}
    (copy / "record/step7-clean-copy.json").write_text(json.dumps(manifest))
    answers = _step11_resume_answers()
    answers.update({"client": "bteam", "source_run_id": "up-run-step6",
        "first_unfinished_phase": "compose-big-idea", "step7_clean_task_dir": str(copy),
        "step11_writer_input_path": None, "step11_writer_call_budget_path": None,
        "step11_writer_call_limit": None})
    roots = {"united-partners": str(repository)}
    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation", answers,
        artifact_paths={}, repository_roots=roots)
    assert prepared["argv"][-2:] == ["--task-dir", str(copy)]
    assert prepared["environment"]["UP_HARNESS_GOOGLE_DRIVE_ROOT"] == str(copy / "drive-staging")
    manifest["clean_state_sha256"] = "b" * 64
    (copy / "record/step7-clean-copy.json").write_text(json.dumps(manifest))
    with pytest.raises(sequence_intake_adapters.AdapterError, match="step7-clean-copy-manifest-mismatch"):
        sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots=roots)

def test_step7_recorded_route_selects_current_source_and_holds_without_paths(
    tmp_path, monkeypatch,
):
    repository = tmp_path / "united-partners"
    tasks = repository / "Tasks"
    source_id = "up-run-03060ad9afb1"
    route = {"status": "ready", "source_run_id": source_id, "run_id": source_id,
             "phase": "compose-big-idea",
             "task_dir": str(tasks / "bteam-step6-clean-2cae4503e585"),
             "copy_dir": str(tasks / "bteam-step7-clean-03060ad9afb1")}
    calls = []

    def selected(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout=json.dumps(route))

    monkeypatch.setattr(sequence_intake_adapters.subprocess, "run", selected)
    answers = _step11_resume_answers()
    answers.update({"client": "bteam",
                    "source_run_id": sequence_intake_adapters.STEP7_RECORDED_SOURCE,
                    "first_unfinished_phase": "compose-big-idea",
                    "step11_writer_input_path": None,
                    "step11_writer_call_budget_path": None,
                    "step11_writer_call_limit": None})
    roots = {"united-partners": str(repository)}

    def prepare():
        return sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots=roots)

    ready = prepare()
    assert ready["argv"][-2:] == ["--task-dir", route["task_dir"]]
    assert ready["argv"][ready["argv"].index("--resume-run") + 1] == source_id
    assert ready["environment"]["UP_HARNESS_GOOGLE_DRIVE_ROOT"] == (
        route["copy_dir"] + "/drive-staging")
    assert calls[-1][-3:] == ["--resolve-recorded-route", "--client", "bteam"]

    route.update(run_id="up-run-111111111111", phase="compose-message-architecture",
                 task_dir=route["copy_dir"], reopen_completed_phase=True)
    resumed = prepare()
    assert "--rerun-completed" in resumed["argv"]
    assert resumed["argv"][resumed["argv"].index("--from-phase") + 1] == (
        "compose-message-architecture")
    route["phase"] = "compose-big-idea"
    with pytest.raises(sequence_intake_adapters.AdapterError,
                       match="completed-phase route is invalid"):
        prepare()
    route.pop("reopen_completed_phase")

    route.update(status="awaiting-human", run_id="up-run-111111111111",
                 phase="narrative-gate", task_dir=route["copy_dir"])
    answers["step7_held_by"] = "Kamen"
    hold = prepare()
    assert hold["argv"][-1] == "--confirmed-held"
    assert "up_harness.step7_review_hold" in hold["argv"]
    answers["step7_held_by"] = None
    with pytest.raises(sequence_intake_adapters.AdapterError, match="explicit named hold"):
        prepare()

    route["status"] = "held"
    close = prepare()
    assert close["argv"][-1] == "--close-recorded"
    assert "up_harness.step7_maria_package" in close["argv"]
    route["copy_dir"] = str(tasks / "bteam-step7-clean-wrong")
    with pytest.raises(sequence_intake_adapters.AdapterError, match="wrong identity"):
        prepare()

def test_step8_recorded_route_selects_current_source_hold_and_package(tmp_path, monkeypatch):
    repository = tmp_path / "united-partners"
    tasks = repository / "Tasks"
    source_id = "up-run-b2224d839ce5"
    route = {"status": "ready", "source_run_id": source_id, "run_id": source_id,
             "phase": "compose-communications-platform",
             "task_dir": str(tasks / "bteam-step7-clean-03060ad9afb1"),
             "copy_dir": str(tasks / "bteam-step8-clean-b2224d839ce5")}

    def selected(argv, **_kwargs):
        if argv[-1] == "vivacom":
            other = {"status": "held", "source_run_id": "up-run-3f28ccaa98fb",
                     "run_id": "up-run-cccccccccccc", "phase": "platform-architecture-gate",
                     "task_dir": str(tasks / "vivacom-step8-clean-3f28ccaa98fb"),
                     "copy_dir": str(tasks / "vivacom-step8-clean-3f28ccaa98fb")}
            return SimpleNamespace(returncode=0, stdout=json.dumps(other))
        return SimpleNamespace(returncode=0, stdout=json.dumps(route))

    monkeypatch.setattr(sequence_intake_adapters.subprocess, "run", selected)
    answers = _step11_resume_answers()
    answers.update({"client": "bteam",
                    "source_run_id": sequence_intake_adapters.STEP8_RECORDED_SOURCE,
                    "first_unfinished_phase": "compose-communications-platform",
                    "step11_writer_input_path": None,
                    "step11_writer_call_budget_path": None,
                    "step11_writer_call_limit": None})
    roots = {"united-partners": str(repository)}

    def prepare():
        return sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots=roots)

    ready = prepare()
    assert ready["argv"][-2:] == ["--task-dir", route["task_dir"]]
    assert ready["environment"]["UP_HARNESS_GOOGLE_DRIVE_ROOT"] == (
        route["copy_dir"] + "/drive-staging")
    questions = []
    reviewer = {"answer": ""}

    def answer(question):
        label = question.splitlines()[0].removeprefix("Question: ")
        questions.append(label)
        return {"United Partners repository": "united-partners",
                "Client configuration key": "bteam",
                "Persisted source run identity": sequence_intake_adapters.STEP8_RECORDED_SOURCE,
                "Step 8 reviewer holding this page": reviewer["answer"]}[label]

    collected = sequence_intake_adapters.collect_and_prepare(
        "workflow-resume-from-phase-live-confirmation",
        artifact_paths={}, repository_roots=roots,
        input_fn=answer, output_fn=lambda _: None,
    )
    assert collected["argv"] == ready["argv"]
    assert len(questions) == 4
    assert "Step 8 reviewer holding this page" in questions
    route.update(run_id="up-run-aaaaaaaaaaaa", phase="compose-communications-platform",
                 task_dir=route["copy_dir"], reopen_completed_phase=True)
    assert "--rerun-completed" in prepare()["argv"]
    route.pop("reopen_completed_phase")
    route.update(status="awaiting-human", run_id="up-run-aaaaaaaaaaaa",
                 phase="platform-architecture-gate", task_dir=route["copy_dir"])
    answers["step8_held_by"] = "Kamen"
    held = prepare()
    assert "up_harness.step8_review_hold" in held["argv"]
    reviewer["answer"] = "Kamen"
    questions.clear()
    collected_hold = sequence_intake_adapters.collect_and_prepare(
        "workflow-resume-from-phase-live-confirmation",
        artifact_paths={}, repository_roots=roots,
        input_fn=answer, output_fn=lambda _: None,
    )
    assert collected_hold["argv"] == held["argv"] and len(questions) == 4
    answers["step8_held_by"] = None
    with pytest.raises(sequence_intake_adapters.AdapterError, match="explicit named hold"):
        prepare()
    route["status"] = "held"
    closed = prepare()
    assert "up_harness.step8_maria_package" in closed["argv"]
    reviewer["answer"] = ""
    questions.clear()
    collected_close = sequence_intake_adapters.collect_and_prepare(
        "workflow-resume-from-phase-live-confirmation",
        artifact_paths={}, repository_roots=roots,
        input_fn=answer, output_fn=lambda _: None,
    )
    assert collected_close["argv"] == closed["argv"] and len(questions) == 4
    route["copy_dir"] = str(tasks / "bteam-step8-clean-wrong")
    with pytest.raises(sequence_intake_adapters.AdapterError, match="wrong identity"):
        prepare()

def test_step2_clean_copy_routes_ordinary_resume_and_gate_approval(tmp_path):
    repository = tmp_path / "united-partners"
    copy = repository / "Tasks" / "bteam-step2-clean-20261004"
    (copy / "state").mkdir(parents=True)
    (copy / "record").mkdir()
    answers = _step11_resume_answers()
    answers.update({
        "client": "bteam", "source_run_id": "up-run-step1",
        "first_unfinished_phase": "prepare-controlled-topic-policy-inputs",
        "step2_clean_task_dir": str(copy),
        "step11_writer_input_path": None,
        "step11_writer_call_budget_path": None,
        "step11_writer_call_limit": None,
    })
    roots = {"united-partners": str(repository)}
    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation", answers,
        artifact_paths={}, repository_roots=roots,
    )
    assert prepared["argv"][-2:] == ["--task-dir", str(copy.resolve())]
    assert prepared["environment"]["UP_HARNESS_GOOGLE_DRIVE_ROOT"] == str(copy.resolve() / "drive-staging")
    assert prepared["environment"]["UP_HARNESS_GOOGLE_DRIVE_ACCESS_TOKEN"] == ""
    assert prepared["environment"]["UP_HARNESS_AGENT_MAX_ATTEMPTS"] == "1"

    approval = copy / "record" / "debrief-approval.json"
    approval.write_text("[]", encoding="utf-8")
    answers["first_unfinished_phase"] = "debrief-gate"
    answers["gate_approvals_path"] = str(approval)
    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation", answers,
        artifact_paths={}, repository_roots=roots,
    )
    assert prepared["argv"][prepared["argv"].index("--gate-approvals-file") + 1] == str(approval)

def test_step2_clean_copy_refuses_wrong_client_phase_and_external_input(tmp_path):
    repository = tmp_path / "united-partners"
    copy = repository / "Tasks" / "bteam-step2-clean-20261004"
    (copy / "state").mkdir(parents=True)
    (copy / "record").mkdir()
    answers = _step11_resume_answers()
    answers.update({
        "client": "bteam", "first_unfinished_phase": "prepare-controlled-topic-policy-inputs",
        "step2_clean_task_dir": str(copy),
        "step11_writer_input_path": None,
        "step11_writer_call_budget_path": None,
        "step11_writer_call_limit": None,
    })
    roots = {"united-partners": str(repository)}

    def refused(issue):
        with pytest.raises(sequence_intake_adapters.AdapterError, match=issue):
            sequence_intake_adapters.prepare(
                "workflow-resume-from-phase-live-confirmation", answers,
                artifact_paths={}, repository_roots=roots,
            )

    answers["client"] = "vivacom"
    refused("step2-clean-copy-missing-or-mismatched")
    answers["client"] = "bteam"
    answers["first_unfinished_phase"] = "compose-final-brief"
    refused("step2-clean-copy-phase-outside-step2")
    answers["first_unfinished_phase"] = "debrief-gate"
    external = repository / "elsewhere.json"
    external.write_text("[]", encoding="utf-8")
    answers["gate_approvals_path"] = str(external)
    refused("step2-clean-copy-input-must-be-in-record")

def test_step2_current_source_copy_admits_first_resume_and_checks_manifest(tmp_path):
    repository = tmp_path / "united-partners"
    run_id = "up-run-aaaaaaaaaaaa"
    source = repository / "Tasks" / "bteam-step1-clean-demo"
    source_state = source / "state" / f"{run_id}.json"
    source_state.parent.mkdir(parents=True)
    state_bytes = b'{"run_id":"up-run-aaaaaaaaaaaa"}'
    source_state.write_bytes(state_bytes)
    copy = repository / "Tasks" / "bteam-step2-clean-aaaaaaaaaaaa"
    answers = _step11_resume_answers()
    answers.update({
        "client": "bteam", "source_run_id": run_id,
        "first_unfinished_phase": "prepare-controlled-topic-policy-inputs",
        "step2_clean_task_dir": str(copy),
        "step11_writer_input_path": None,
        "step11_writer_call_budget_path": None,
        "step11_writer_call_limit": None,
    })
    roots = {"united-partners": str(repository)}

    def route():
        return sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots=roots,
        )

    # The ordinary first resume is allowed to create its copy inside the harness.
    assert route()["argv"][-2:] == ["--task-dir", str(copy)]
    answers["first_unfinished_phase"] = "debrief-gate"
    with pytest.raises(sequence_intake_adapters.AdapterError,
                       match="step2-clean-copy-missing-before-later-phase"):
        route()
    answers["first_unfinished_phase"] = "prepare-controlled-topic-policy-inputs"

    copied_state = copy / "state" / f"{run_id}.json"
    copied_state.parent.mkdir(parents=True)
    copied_state.write_bytes(state_bytes)
    (copy / "record").mkdir()
    manifest_path = copy / "record" / "step2-clean-copy.json"
    manifest = {
        "schema": "step2-clean-copy/v2", "client": "bteam",
        "source_task_dir": str(source.resolve()), "source_run_id": run_id,
        "source_run_sha256": hashlib.sha256(state_bytes).hexdigest(),
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert route()["argv"][-2:] == ["--task-dir", str(copy)]
    manifest["source_run_sha256"] = "b" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(sequence_intake_adapters.AdapterError,
                       match="step2-clean-copy-manifest-mismatch"):
        route()
    manifest["source_run_sha256"] = hashlib.sha256(state_bytes).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    answers["client"] = "vivacom"
    with pytest.raises(sequence_intake_adapters.AdapterError,
                       match="step2-clean-copy-missing-or-mismatched"):
        route()

def _step2_registered_child_fixture(tmp_path):
    repository = tmp_path / "united-partners"
    root_id = "up-run-6488d9e38431"
    child_id = "up-run-c71f6ca4437e"
    source = repository / "Tasks" / "bteam-step1-clean-demo"
    source_state = source / "state" / f"{root_id}.json"
    source_state.parent.mkdir(parents=True)
    root_bytes = json.dumps({"run_id": root_id, "status": "blocked"}).encode()
    source_state.write_bytes(root_bytes)

    copy = repository / "Tasks" / "bteam-step2-clean-6488d9e38431"
    copied_root = copy / "state" / f"{root_id}.json"
    copied_root.parent.mkdir(parents=True)
    copied_root.write_bytes(root_bytes)
    (copy / "record").mkdir()
    manifest = {
        "schema": "step2-clean-copy/v2", "client": "bteam",
        "source_task_dir": str(source.resolve()), "source_run_id": root_id,
        "source_run_sha256": hashlib.sha256(root_bytes).hexdigest(),
    }
    manifest_path = copy / "record" / "step2-clean-copy.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    answers = _step11_resume_answers()
    answers.update({
        "client": "bteam", "source_run_id": child_id,
        "first_unfinished_phase": "debrief-gate",
        "step2_clean_task_dir": str(copy),
        "step11_writer_input_path": None,
        "step11_writer_call_budget_path": None,
        "step11_writer_call_limit": None,
    })
    roots = {"united-partners": str(repository)}

    def route():
        return sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots=roots,
        )

    return root_id, child_id, source_state, copied_root, copy, answers, route

def test_step2_registered_copy_admits_child_resume_and_keeps_selected_run(tmp_path):
    root_id, child_id, _, _, copy, _, route = _step2_registered_child_fixture(tmp_path)
    (copy / "state" / f"{child_id}.json").write_text(json.dumps({
        "run_id": child_id, "parent_run_id": root_id, "status": "blocked",
    }), encoding="utf-8")

    prepared = route()

    assert prepared["argv"][prepared["argv"].index("--resume-run") + 1] == child_id
    assert prepared["argv"][prepared["argv"].index("--task-dir") + 1] == str(copy)

def test_step2_registered_copy_admits_multihop_child_lineage(tmp_path):
    root_id, child_id, _, _, copy, _, route = _step2_registered_child_fixture(tmp_path)
    middle_id = "up-run-middle"
    (copy / "state" / f"{child_id}.json").write_text(json.dumps({
        "run_id": child_id, "parent_run_id": middle_id, "status": "blocked",
    }), encoding="utf-8")
    (copy / "state" / f"{middle_id}.json").write_text(json.dumps({
        "run_id": middle_id, "parent_run_id": root_id,
    }), encoding="utf-8")

    prepared = route()

    assert prepared["argv"][prepared["argv"].index("--resume-run") + 1] == child_id

def test_step2_registered_copy_refuses_state_directory_symlink_escape(tmp_path):
    _, _, _, copied_root, copy, _, route = _step2_registered_child_fixture(tmp_path)
    outside = tmp_path / "outside-state"
    outside.mkdir()
    (outside / copied_root.name).write_bytes(copied_root.read_bytes())
    copied_root.unlink()
    (copy / "state").rmdir()
    (copy / "state").symlink_to(outside, target_is_directory=True)

    with pytest.raises(sequence_intake_adapters.AdapterError,
                       match="step2-clean-copy-state-outside-copy"):
        route()

def test_step2_registered_copy_refuses_state_file_symlink_escape(tmp_path):
    root_id, child_id, _, _, copy, _, route = _step2_registered_child_fixture(tmp_path)
    outside = tmp_path / f"{child_id}.json"
    outside.write_text(json.dumps({
        "run_id": child_id, "parent_run_id": root_id,
    }), encoding="utf-8")
    (copy / "state" / f"{child_id}.json").symlink_to(outside)

    with pytest.raises(sequence_intake_adapters.AdapterError,
                       match="step2-clean-copy-lineage-mismatch"):
        route()

@pytest.mark.parametrize("lineage", ["unrelated", "spoofed", "missing", "cycle", "unsafe"])
def test_step2_registered_copy_rejects_invalid_child_lineage(tmp_path, lineage):
    root_id, child_id, _, _, copy, _, route = _step2_registered_child_fixture(tmp_path)
    states = copy / "state"
    child = {"run_id": child_id, "parent_run_id": root_id, "status": "blocked"}
    if lineage == "unrelated":
        child["parent_run_id"] = "up-run-unrelated"
        (states / "up-run-unrelated.json").write_text(json.dumps({
            "run_id": "up-run-unrelated", "parent_run_id": "up-run-otherroot",
        }), encoding="utf-8")
        (states / "up-run-otherroot.json").write_text(json.dumps({
            "run_id": "up-run-otherroot",
        }), encoding="utf-8")
    elif lineage == "spoofed":
        child["run_id"] = "up-run-other-child"
    elif lineage == "missing":
        child["parent_run_id"] = "up-run-missing"
    elif lineage == "cycle":
        child["parent_run_id"] = "up-run-cycle"
        (states / "up-run-cycle.json").write_text(json.dumps({
            "run_id": "up-run-cycle", "parent_run_id": child_id,
        }), encoding="utf-8")
    else:
        child["parent_run_id"] = "../outside"
    (states / f"{child_id}.json").write_text(json.dumps(child), encoding="utf-8")

    with pytest.raises(sequence_intake_adapters.AdapterError,
                       match="step2-clean-copy-lineage-mismatch"):
        route()

def test_step2_registered_copy_rejects_changed_original_or_copied_root_hash(tmp_path):
    _, _, source_state, copied_root, _, _, route = _step2_registered_child_fixture(tmp_path)
    source_state.write_bytes(source_state.read_bytes() + b" ")
    with pytest.raises(sequence_intake_adapters.AdapterError,
                       match="step2-clean-copy-manifest-mismatch"):
        route()

    source_state.write_bytes(source_state.read_bytes()[:-1])
    copied_root.write_bytes(copied_root.read_bytes() + b" ")
    with pytest.raises(sequence_intake_adapters.AdapterError,
                       match="step2-clean-copy-manifest-mismatch"):
        route()

def test_step3_clean_copy_routes_only_step3_and_its_own_gate_inputs(tmp_path):
    repository = tmp_path / "united-partners"
    copy = repository / "Tasks" / "bteam-step3-clean-20261005"
    (copy / "state").mkdir(parents=True)
    (copy / "record").mkdir()
    (copy / "record" / "step3-clean-copy.json").write_text("{}", encoding="utf-8")
    answers = _step11_resume_answers()
    answers.update({
        "client": "bteam", "source_run_id": "up-run-step2",
        "first_unfinished_phase": "final-brief-gate",
        "step3_clean_task_dir": str(copy),
        "step11_writer_input_path": None,
        "step11_writer_call_budget_path": None,
        "step11_writer_call_limit": None,
    })
    roots = {"united-partners": str(repository)}
    answers["first_unfinished_phase"] = "compose-final-brief"
    with pytest.raises(sequence_intake_adapters.AdapterError, match="old-source-cannot-start-new-compose"):
        sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots=roots,
        )
    answers["first_unfinished_phase"] = "final-brief-gate"
    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation", answers,
        artifact_paths={}, repository_roots=roots,
    )
    assert prepared["argv"][-2:] == ["--task-dir", str(copy.resolve())]
    assert prepared["environment"]["UP_HARNESS_GOOGLE_DRIVE_ROOT"] == str(copy / "drive-staging")
    answers["first_unfinished_phase"] = "compose-annual-review"
    with pytest.raises(sequence_intake_adapters.AdapterError, match="step3-clean-copy-phase-outside-step3"):
        sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots=roots,
        )
    answers["first_unfinished_phase"] = "final-brief-gate"
    approval = copy / "record" / "step3-approval.json"
    approval.write_text("[]", encoding="utf-8")
    answers["gate_approvals_path"] = str(approval)
    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation", answers,
        artifact_paths={}, repository_roots=roots,
    )
    assert "--gate-approvals-file" in prepared["argv"]

def test_step3_current_copy_binds_package_receipt_and_source(tmp_path):
    repository = tmp_path / "united-partners"
    tasks = repository / "Tasks"
    source_id = "up-run-3f239e371b7a"
    source = tasks / "bteam-step2-clean-6488d9e38431"
    (source / "state").mkdir(parents=True)
    source_bytes = b'{"run_id":"up-run-3f239e371b7a"}'
    (source / "state" / f"{source_id}.json").write_bytes(source_bytes)
    receipt_dir = tasks / "step2-rule-controller"
    receipt_dir.mkdir()
    receipt_name = "maria-step2-pack-776af17f5786085f-receipt.json"
    receipt_bytes = json.dumps({"runs": {"bteam": source_id},
                                "page_pair_sha256": {"bteam": "pair"}}).encode()
    (receipt_dir / receipt_name).write_bytes(receipt_bytes)
    copy = tasks / "bteam-step3-clean-3f239e371b7a"
    (copy / "state").mkdir(parents=True)
    (copy / "record").mkdir()
    manifest = {
        "schema": "step3-clean-copy/v3", "client": "bteam", "source_run_id": source_id,
        "source_task_dir": str(source.relative_to(repository)),
        "source_run_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "step2_package_receipt": receipt_name,
        "step2_package_receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
        "step2_page_pair_sha256": "pair",
    }
    (copy / "record" / "step3-clean-copy.json").write_text(json.dumps(manifest))
    answers = _step11_resume_answers()
    answers.update({"client": "bteam", "source_run_id": source_id,
                    "first_unfinished_phase": "compose-final-brief",
                    "step3_clean_task_dir": str(copy),
                    "step11_writer_input_path": None,
                    "step11_writer_call_budget_path": None,
                    "step11_writer_call_limit": None})
    roots = {"united-partners": str(repository)}
    pending = tasks / "bteam-step3-clean-3f239e371b7a"
    # The registered resume may dispatch before the driver creates the copy.
    saved = copy.rename(tasks / "bteam-step3-clean-f3f92d1c8fd6")
    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation", answers,
        artifact_paths={}, repository_roots=roots,
    )
    assert prepared["argv"][-2:] == ["--task-dir", str(pending.resolve())]
    (pending / "drive-staging").mkdir(parents=True)
    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation", answers,
        artifact_paths={}, repository_roots=roots,
    )
    assert prepared["argv"][-2:] == ["--task-dir", str(pending.resolve())]
    (pending / "unrelated.txt").write_text("no")
    with pytest.raises(sequence_intake_adapters.AdapterError, match="needs-state-and-record"):
        sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots=roots,
        )
    (pending / "unrelated.txt").unlink()
    (pending / "drive-staging").rmdir()
    pending.rmdir()
    saved.rename(copy)
    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation", answers,
        artifact_paths={}, repository_roots=roots,
    )
    assert prepared["argv"][-2:] == ["--task-dir", str(copy.resolve())]
    child_id = "up-run-b7720114018e"
    child_path = copy / "state" / f"{child_id}.json"
    child_path.write_text(json.dumps({"run_id": child_id, "parent_run_id": source_id}))
    approval = copy / "record" / "step3-draft-approval.json"
    approval.write_text("[]", encoding="utf-8")
    answers.update({"source_run_id": child_id,
                    "first_unfinished_phase": "final-brief-gate",
                    "gate_approvals_path": str(approval)})
    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation", answers,
        artifact_paths={}, repository_roots=roots,
    )
    assert prepared["argv"][prepared["argv"].index("--task-dir") + 1] == str(copy.resolve())
    assert prepared["argv"][-2:] == ["--gate-approvals-file", str(approval)]
    child_path.write_text(json.dumps({"run_id": child_id,
                                      "parent_run_id": "up-run-000000000000"}))
    with pytest.raises(sequence_intake_adapters.AdapterError,
                       match="step3-clean-copy-child-lineage-mismatch"):
        sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots=roots,
        )
    answers.update({"source_run_id": source_id,
                    "first_unfinished_phase": "compose-final-brief",
                    "gate_approvals_path": None})
    manifest["source_run_sha256"] = "0" * 64
    (copy / "record" / "step3-clean-copy.json").write_text(json.dumps(manifest))
    with pytest.raises(sequence_intake_adapters.AdapterError, match="source-or-receipt-mismatch"):
        sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots=roots,
        )

def test_step4_clean_copy_requires_manifest_and_isolates_drive(tmp_path):
    import hashlib

    repository = tmp_path / "united-partners"
    source_id = "up-run-91d7941f46dd"
    copy = repository / "Tasks" / "bteam-step4-clean-91d7941f46dd"
    source_dir = repository / "Tasks" / "bteam-step3-clean-3f239e371b7a"
    (source_dir / "state").mkdir(parents=True)
    (source_dir / "record").mkdir()
    source_bytes = (json.dumps({"run_id": source_id}) + "\n").encode()
    (source_dir / "state" / f"{source_id}.json").write_bytes(source_bytes)
    step3_manifest_bytes = b"{}\n"
    (source_dir / "record" / "step3-clean-copy.json").write_bytes(step3_manifest_bytes)
    (copy / "state").mkdir(parents=True)
    (copy / "record").mkdir()
    state = {
        "run_id": source_id,
        "workflow_name": "cd-s-002-corporate-communications-strategy",
        "context": {"inputs": {"client_name": "The B Team", "client_code": "BTM",
                               "stop_after_phase": "research-gate"}},
        "phases": {"final-brief-gate": {"status": "completed"}},
    }
    state_bytes = (json.dumps(state) + "\n").encode()
    (copy / "state" / f"{source_id}.json").write_bytes(state_bytes)
    manifest = {
        "schema": "step4-clean-copy/v2", "client": "bteam",
        "source_run_id": source_id,
        "source_task_dir": str(source_dir.relative_to(repository)),
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "step3_manifest_sha256": hashlib.sha256(step3_manifest_bytes).hexdigest(),
        "first_step4_phase": "compose-research-insight-pack",
        "stop_after_phase": "research-gate",
        "clean_state_sha256": hashlib.sha256(state_bytes).hexdigest(),
    }
    (copy / "record" / "step4-clean-copy.json").write_text(json.dumps(manifest))
    answers = _step11_resume_answers()
    answers.update({
        "client": "bteam", "source_run_id": source_id,
        "first_unfinished_phase": "compose-research-insight-pack",
        "step4_clean_task_dir": str(copy),
        "step11_writer_input_path": None,
        "step11_writer_call_budget_path": None,
        "step11_writer_call_limit": None,
    })
    roots = {"united-partners": str(repository)}
    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation", answers,
        artifact_paths={}, repository_roots=roots,
    )
    assert prepared["argv"][-2:] == ["--task-dir", str(copy)]
    assert prepared["environment"]["UP_HARNESS_GOOGLE_DRIVE_ROOT"] == str(copy / "drive-staging")
    assert prepared["environment"]["UP_HARNESS_GOOGLE_DRIVE_ACCESS_TOKEN"] == ""
    assert prepared["environment"]["PYTHONPATH"] == "src:."
    late_id = "up-run-aabbccddeeff"
    late_child = {
        "run_id": late_id, "parent_run_id": source_id, "status": "blocked",
        "phases": {
            "compose-research-insight-pack": {"status": "completed"},
            "research-gate": {
                "status": "blocked",
                "output": "Refused: the standard-enterprise engagement requires conducted primary_research",
            },
        },
        "context": {"inputs": {"engagement_tier": "standard-enterprise"},
                    "up": {"cd_s_002": {
            "research_pack": {"step4_contract_version": 3,
                              "depth": "standard-enterprise"},
            "step4_part_ledger": {
                "version": 1, "writer_calls_used": 14, "writer_call_limit": 60,
                "parts": {part: {"status": "passed"}
                          for part in sequence_intake_adapters.STEP4_NATIVE_PARTS},
                "document_check": {"status": "passed"},
            },
        }}},
    }
    (copy / "state" / f"{late_id}.json").write_text(json.dumps(late_child))
    evidence_path = copy / "record" / f"primary-research-{late_id}.json"
    evidence_path.write_text(json.dumps({"dipstick": [
        {"stakeholder": f"TEST ONLY stakeholder {index}",
         "verbatim": f"TEST ONLY statement {index}",
         "source": f"TEST ONLY interview record {index}",
         "date": "2026-10-15", "confidence": "low"}
        for index in range(1, 6)
    ]}))
    tier_file = repository / "Tasks" / "bteam-corporate-demo" / "engagement-tier.json"
    tier_file.parent.mkdir(parents=True)
    tier_file.write_text(json.dumps({"engagement_tier": "standard"}))
    answers.update({
        "source_run_id": late_id,
        "reopen_completed_phase": True,
        "step4_primary_research_path": str(evidence_path),
    })
    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation", answers,
        artifact_paths={}, repository_roots=roots,
    )
    assert "--rerun-completed" in prepared["argv"]
    assert prepared["argv"][-2:] == ["--step4-primary-research-file", str(evidence_path)]
    # A saved, completed draft blocked only by the old primary-research rule
    # reopens through the ordinary route without inventing interview evidence.
    (copy / "state" / f"{late_id}.json").write_text(json.dumps(late_child))
    answers["step4_primary_research_path"] = None
    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation", answers,
        artifact_paths={}, repository_roots=roots,
    )
    assert prepared["argv"][-4:] == [
        "--engagement-tier", "standard", "--task-dir", str(copy),
    ]
    tier_file.write_text(json.dumps({"engagement_tier": "enterprise"}))
    with pytest.raises(sequence_intake_adapters.AdapterError,
                       match="step4-standard-tier-ruling-mismatch"):
        sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots=roots,
        )
    tier_file.write_text(json.dumps({"engagement_tier": "standard"}))
    answers["step4_primary_research_path"] = str(copy / "record" / "wrong.json")
    with pytest.raises(sequence_intake_adapters.AdapterError,
                       match="step4-primary-evidence-file-must-bind-to-source"):
        sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots=roots,
        )
    answers["step4_primary_research_path"] = str(evidence_path)
    late_child["phases"]["research-gate"]["output"] = "Refused: no human review"
    (copy / "state" / f"{late_id}.json").write_text(json.dumps(late_child))
    with pytest.raises(sequence_intake_adapters.AdapterError,
                       match="step4-primary-evidence-source-not-reviewable"):
        sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots=roots,
        )
    late_child["context"]["up"]["cd_s_002"]["research_pack"]["step4_contract_version"] = 4
    late_child["context"]["up"]["cd_s_002"]["research_pack"]["depth"] = "enterprise"
    late_child["context"]["inputs"]["engagement_tier"] = "enterprise"
    late_child["phases"]["research-gate"]["ledger"] = {
        "primary_research_status": "pending",
    }
    (copy / "state" / f"{late_id}.json").write_text(json.dumps(late_child))
    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation", answers,
        artifact_paths={}, repository_roots=roots,
    )
    assert prepared["argv"][-2:] == ["--step4-primary-research-file", str(evidence_path)]
    answers.update({
        "source_run_id": source_id,
        "reopen_completed_phase": False,
        "step4_primary_research_path": None,
    })
    compose_id = "up-run-compose-child"
    compose_child = {
        "run_id": compose_id, "parent_run_id": source_id, "status": "failed",
        "phases": {"compose-research-insight-pack": {"status": "failed"}},
        "context": {"up": {"cd_s_002": {"step4_part_ledger": {
            "version": 1, "writer_calls_used": 2, "writer_call_limit": 60,
            "parts": {"buckets": {"status": "passed"},
                      "personas": {"status": "inflight"}},
        }}}},
    }
    (copy / "state" / f"{compose_id}.json").write_text(json.dumps(compose_child))
    answers["source_run_id"] = compose_id
    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation", answers,
        artifact_paths={}, repository_roots=roots,
    )
    assert prepared["argv"][prepared["argv"].index("--resume-run") + 1] == compose_id
    compose_child["status"] = "blocked"
    compose_child["phases"]["compose-research-insight-pack"]["status"] = "blocked"
    (copy / "state" / f"{compose_id}.json").write_text(json.dumps(compose_child))
    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation", answers,
        artifact_paths={}, repository_roots=roots,
    )
    assert prepared["argv"][prepared["argv"].index("--resume-run") + 1] == compose_id
    compose_child["parent_run_id"] = "up-run-wrong-root"
    (copy / "state" / f"{compose_id}.json").write_text(json.dumps(compose_child))
    with pytest.raises(sequence_intake_adapters.AdapterError,
                       match="step4-clean-copy-compose-lineage-mismatch"):
        sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots=roots,
        )
    compose_child["parent_run_id"] = source_id
    compose_child["context"] = {}
    (copy / "state" / f"{compose_id}.json").write_text(json.dumps(compose_child))
    with pytest.raises(sequence_intake_adapters.AdapterError,
                       match="step4-clean-copy-compose-source-not-resumable"):
        sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots=roots,
        )
    child = {
        "run_id": "up-run-step4", "parent_run_id": source_id, "status": "blocked",
        "phases": {"research-gate": {"status": "blocked"}},
    }
    (copy / "state" / "up-run-step4.json").write_text(json.dumps(child))
    answers.update({
        "source_run_id": "up-run-step4", "first_unfinished_phase": "research-gate",
    })
    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation", answers,
        artifact_paths={}, repository_roots=roots,
    )
    assert prepared["argv"][-2:] == ["--task-dir", str(copy)]
    failed = {
        "run_id": "up-run-step4-failed", "parent_run_id": "up-run-step4",
        "status": "failed", "phases": {"research-gate": {"status": "failed"}},
        "context": {"up": {"cd_s_002": {"step4_part_ledger": {
            "version": 1, "parts": {"buckets": {"status": "inflight"}},
        }}}},
    }
    (copy / "state" / "up-run-step4-failed.json").write_text(json.dumps(failed))
    answers["source_run_id"] = "up-run-step4-failed"
    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation", answers,
        artifact_paths={}, repository_roots=roots,
    )
    assert prepared["argv"][prepared["argv"].index("--resume-run") + 1] == "up-run-step4-failed"
    failed["context"] = {}
    (copy / "state" / "up-run-step4-failed.json").write_text(json.dumps(failed))
    with pytest.raises(sequence_intake_adapters.AdapterError, match="step4-clean-copy-gate-source-not-blocked-at-gate"):
        sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots=roots,
        )
    answers["client"] = "vivacom"
    with pytest.raises(sequence_intake_adapters.AdapterError, match="step4-clean-copy-missing-or-mismatched"):
        sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots=roots,
        )
    answers["client"] = "bteam"
    answers.update({
        "source_run_id": source_id,
        "first_unfinished_phase": "compose-research-insight-pack",
    })
    (copy / "state" / f"{source_id}.json").write_text("{}")
    with pytest.raises(sequence_intake_adapters.AdapterError, match="step4-clean-copy-manifest-mismatch"):
        sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots=roots,
        )
    (copy / "state" / f"{source_id}.json").write_bytes(state_bytes)
    manifest["source_task_dir"] = None
    (copy / "record" / "step4-clean-copy.json").write_text(json.dumps(manifest))
    with pytest.raises(sequence_intake_adapters.AdapterError, match="step4-clean-copy-manifest-mismatch"):
        sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots=roots,
        )

def test_step4_clean_copy_can_be_prepared_by_ordinary_driver(tmp_path):
    repository = tmp_path / "united-partners"
    source_id = "up-run-91d7941f46dd"
    copy = repository / "Tasks" / "bteam-step4-clean-91d7941f46dd"
    answers = _step11_resume_answers()
    answers.update({
        "client": "bteam", "source_run_id": source_id,
        "first_unfinished_phase": "compose-research-insight-pack",
        "step4_clean_task_dir": str(copy),
        "step11_writer_input_path": None,
        "step11_writer_call_budget_path": None,
        "step11_writer_call_limit": None,
    })
    roots = {"united-partners": str(repository)}
    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation", answers,
        artifact_paths={}, repository_roots=roots,
    )
    assert prepared["argv"][-2:] == ["--task-dir", str(copy)]
    assert prepared["environment"]["UP_HARNESS_GOOGLE_DRIVE_ROOT"] == str(copy / "drive-staging")
    answers["step4_clean_task_dir"] = str(repository / "Tasks" / "bteam-step4-clean-20261005")
    with pytest.raises(sequence_intake_adapters.AdapterError, match="step4-clean-copy-missing-or-mismatched"):
        sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots=roots,
        )

def test_step4_historical_copy_remains_available_at_its_research_gate(tmp_path):
    import hashlib

    repository = tmp_path / "united-partners"
    copy = repository / "Tasks" / "bteam-step4-clean-20261005"
    (copy / "state").mkdir(parents=True)
    (copy / "record").mkdir()
    root_id = "up-run-91d7941f46dd"
    child_id = "up-run-338d448864ad"
    root = {
        "run_id": root_id,
        "workflow_name": "cd-s-002-corporate-communications-strategy",
        "context": {"inputs": {"client_name": "The B Team", "client_code": "BTM",
                               "stop_after_phase": "research-gate"}},
        "phases": {"final-brief-gate": {"status": "completed"}},
    }
    root_bytes = (json.dumps(root) + "\n").encode()
    (copy / "state" / f"{root_id}.json").write_bytes(root_bytes)
    (copy / "state" / f"{child_id}.json").write_text(json.dumps({
        "run_id": child_id, "parent_run_id": root_id,
        "status": "blocked", "phases": {"research-gate": {"status": "blocked"}},
    }))
    (copy / "record" / "step4-clean-copy.json").write_text(json.dumps({
        "schema": "step4-clean-copy/v1", "client": "bteam",
        "source_run_id": root_id,
        "first_step4_phase": "compose-research-insight-pack",
        "stop_after_phase": "research-gate",
        "clean_state_sha256": hashlib.sha256(root_bytes).hexdigest(),
    }))
    answers = _step11_resume_answers()
    answers.update({
        "client": "bteam", "source_run_id": child_id,
        "first_unfinished_phase": "research-gate",
        "step4_clean_task_dir": str(copy),
        "step11_writer_input_path": None,
        "step11_writer_call_budget_path": None,
        "step11_writer_call_limit": None,
    })
    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation", answers,
        artifact_paths={}, repository_roots={"united-partners": str(repository)},
    )
    assert prepared["argv"][-2:] == ["--task-dir", str(copy)]
    answers.update({"source_run_id": root_id,
                    "first_unfinished_phase": "compose-research-insight-pack"})
    with pytest.raises(sequence_intake_adapters.AdapterError,
                       match="step4-clean-copy-old-source-cannot-start-new-compose"):
        sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots={"united-partners": str(repository)},
        )

@pytest.mark.parametrize("client,source_id", [
    ("bteam", "up-run-2cae4503e585"),
    ("vivacom", "up-run-2cf5cea3c636"),
])
def test_recorded_step6_route_selects_current_held_step5_and_human_closeout(
    client, source_id, monkeypatch, tmp_path,
):
    import subprocess

    repository = tmp_path / "united-partners"
    route_status = "ready"
    source_ids = {"bteam": "up-run-2cae4503e585",
                  "vivacom": "up-run-2cf5cea3c636"}
    step5_suffixes = {"bteam": "c7475afdb640",
                      "vivacom": "fad2194da342"}

    def recorded_route(argv, **kwargs):
        route_client = argv[-1]
        route_source = source_ids[route_client]
        target = repository / "Tasks" / f"{route_client}-step6-clean-{route_source.removeprefix('up-run-')}"
        ready_task = repository / "Tasks" / f"{route_client}-step5-clean-{step5_suffixes[route_client]}"
        route = {"status": route_status, "run_id": route_source,
                 "source_run_id": route_source,
                 "phase": "compose-strategy-one-pager" if route_status == "ready" else "strategy-approach-gate",
                 "task_dir": str(ready_task if route_status == "ready" else target),
                 "copy_dir": str(target)}
        return subprocess.CompletedProcess(argv, 0, json.dumps(route), "")

    monkeypatch.setattr(sequence_intake_adapters.subprocess, "run", recorded_route)
    answers = _step11_resume_answers()
    answers.update({"client": client,
                    "source_run_id": sequence_intake_adapters.STEP6_RECORDED_SOURCE,
                    "first_unfinished_phase": "compose-strategy-one-pager",
                    "reopen_completed_phase": False,
                    "step11_writer_input_path": None,
                    "step11_writer_call_budget_path": None,
                    "step11_writer_call_limit": None})
    roots = {"united-partners": str(repository)}

    def prepare():
        return sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots=roots,
        )

    first = prepare()
    assert first["argv"][4:8] == [
        "--resume-run", source_id, "--from-phase", "compose-strategy-one-pager",
    ]
    assert first["argv"][-2:] == [
        "--task-dir", str(repository / "Tasks" /
                             (f"{client}-step5-clean-" +
                              {"bteam": "c7475afdb640", "vivacom": "fad2194da342"}[client])),
    ]
    assert first["environment"]["UP_HARNESS_GOOGLE_DRIVE_ROOT"] == str(
        repository / "Tasks" / f"{client}-step6-clean-{source_id.removeprefix('up-run-')}" /
        "drive-staging"
    )
    route_status = "awaiting-human"
    with pytest.raises(sequence_intake_adapters.AdapterError, match="explicit named hold"):
        prepare()
    answers["step6_held_by"] = "Kamen"
    hold = prepare()
    assert hold["argv"][-8:] == ["-m", "up_harness.step6_review_hold", "--recorded",
                                 "--client", client, "--held-by", "Kamen", "--confirmed-held"]
    answers["step6_held_by"] = None
    route_status = "held"
    close = prepare()
    assert close["argv"][-3:] == ["-m", "up_harness.step6_maria_package", "--close-recorded"]

@pytest.mark.parametrize("client,source_suffix", [
    ("bteam", "c7475afdb640"),
    ("vivacom", "fad2194da342"),
])
def test_recorded_step5_start_selects_exact_source_without_operator_run_id(
    client, source_suffix, monkeypatch,
):
    import subprocess

    repository = Path("/Users/kamenkamenov/united-partners")
    answers = _step11_resume_answers()
    answers.update({
        "client": client,
        "source_run_id": sequence_intake_adapters.STEP5_RECORDED_SOURCE,
        "first_unfinished_phase": "compose-insight-cards",
        "reopen_completed_phase": False,
        "step11_writer_input_path": None,
        "step11_writer_call_budget_path": None,
        "step11_writer_call_limit": None,
    })
    roots = {"united-partners": str(repository)}

    def prepare():
        return sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots=roots,
        )

    closeout = prepare()
    assert closeout["argv"][-3:] == [
        "-m", "up_harness.step5_maria_package", "--close-recorded",
    ]
    assert "--resume-run" not in closeout["argv"]
    assert closeout["environment"]["UP_HARNESS_GOOGLE_DRIVE_ACCESS_TOKEN"] == ""
    completed = subprocess.run(
        closeout["argv"], cwd=repository,
        env={**os.environ, **closeout["environment"]},
        capture_output=True, text=True, timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    packaged = json.loads(completed.stdout)
    assert packaged["status"] == "verified"
    assert packaged["runs"][client] == "up-run-" + {
        "bteam": "2cae4503e585", "vivacom": "2cf5cea3c636",
    }[client]
    held_only = {
        "status": "held", "source_run_id": f"up-run-{source_suffix}",
        "run_id": packaged["runs"][client], "phase": "insight-gate",
        "task_dir": str(repository / "Tasks" / f"{client}-step5-clean-{source_suffix}"),
        "copy_dir": str(repository / "Tasks" / f"{client}-step5-clean-{source_suffix}"),
    }
    def one_hold(argv, **kwargs):
        status = held_only if argv[-1] == client else {"status": "ready"}
        return subprocess.CompletedProcess(argv, 0, json.dumps(status), "")
    monkeypatch.setattr(sequence_intake_adapters.subprocess, "run", one_hold)
    with pytest.raises(sequence_intake_adapters.AdapterError, match="both holds are needed"):
        prepare()
    target = repository / "Tasks" / f"{client}-step5-clean-{source_suffix}"
    starting = {
        "status": "ready", "source_run_id": f"up-run-{source_suffix}",
        "run_id": f"up-run-{source_suffix}", "phase": "compose-insight-cards",
        "task_dir": str(repository / "Tasks" / f"{client}-corporate-demo"),
        "copy_dir": str(target), "source_kind": "historical",
    }
    monkeypatch.setattr(
        sequence_intake_adapters.subprocess, "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, json.dumps(starting), ""),
    )
    prepared = prepare()
    expected_run = f"up-run-{source_suffix}"
    assert prepared["argv"][4:8] == [
        "--resume-run", expected_run, "--from-phase", "compose-insight-cards",
    ]
    assert prepared["argv"][-2:] == [
        "--task-dir", str(repository / "Tasks" / f"{client}-corporate-demo"),
    ]
    assert prepared["environment"]["UP_HARNESS_GOOGLE_DRIVE_ROOT"] == str(
        repository / "Tasks" / f"{client}-step5-clean-{source_suffix}" / "drive-staging"
    )
    assert prepared["environment"]["UP_HARNESS_AGENT_MAX_ATTEMPTS"] == "1"

    saved = {**starting, "run_id": "up-run-123456789abc",
             "phase": "insight-mini-board-gate", "task_dir": str(target)}
    monkeypatch.setattr(
        sequence_intake_adapters.subprocess, "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, json.dumps(saved), ""),
    )
    continued = prepare()
    assert continued["argv"][4:8] == [
        "--resume-run", saved["run_id"], "--from-phase", saved["phase"],
    ]
    assert continued["argv"][-2:] == ["--task-dir", str(target)]

    answers["client_answers_path"] = "/tmp/unrelated.json"
    with pytest.raises(sequence_intake_adapters.AdapterError, match="no other route inputs"):
        prepare()
    answers["client_answers_path"] = None
    monkeypatch.setattr(
        sequence_intake_adapters.subprocess, "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 2, "", "source changed"),
    )
    with pytest.raises(sequence_intake_adapters.AdapterError, match="could not be selected"):
        prepare()
    monkeypatch.setattr(
        sequence_intake_adapters.subprocess, "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired(args[0], 30)),
    )
    with pytest.raises(sequence_intake_adapters.AdapterError, match="check could not run"):
        prepare()

def test_registered_step4_to_step5_handoff_selects_passed_descendants_without_model_dispatch():
    repository = Path("/Users/kamenkamenov/united-partners")
    for client, source_id, step4_copy in (
        ("bteam", "up-run-e043d1eed718", "Tasks/bteam-step4-clean-453b83f9cdf1"),
        ("vivacom", "up-run-3d3b70a2f645", "Tasks/vivacom-step4-clean-ace8371a0179"),
    ):
        answers = _step11_resume_answers()
        answers.update({
            "client": client, "source_run_id": source_id,
            "first_unfinished_phase": "compose-insight-cards",
            "reopen_completed_phase": False,
            "step4_clean_task_dir": str(repository / step4_copy),
            "step11_writer_input_path": None,
            "step11_writer_call_budget_path": None,
            "step11_writer_call_limit": None,
        })
        prepared = sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots={"united-partners": str(repository)},
        )
        assert prepared["argv"][prepared["argv"].index("--resume-run") + 1] == source_id
        assert prepared["argv"][prepared["argv"].index("--from-phase") + 1] == "compose-insight-cards"
        assert prepared["argv"][-2:] == ["--task-dir", str(repository / step4_copy)]
        assert prepared["environment"]["UP_HARNESS_GOOGLE_DRIVE_ROOT"] == str(
            repository / "Tasks" / f"{client}-step5-clean-{source_id.removeprefix('up-run-')}" / "drive-staging"
        )
        assert "--dry-run" not in prepared["argv"]

    # A different passed descendant in the same admitted Step 4 copy is selected by
    # its registered run id and gets its own source-run-named Step 5 copy.
    import shutil
    repository_copy = Path(tempfile.mkdtemp()) / "united-partners"
    actual_step4 = repository / "Tasks/bteam-step4-clean-453b83f9cdf1"
    copied_step4 = repository_copy / "Tasks/bteam-step4-clean-453b83f9cdf1"
    shutil.copytree(actual_step4, copied_step4)
    step3_relative = json.loads((actual_step4 / "record/step4-clean-copy.json").read_text())["source_task_dir"]
    shutil.copytree(repository / step3_relative, repository_copy / step3_relative)
    alternate_id = "up-run-d1d2d3d4d5d6"
    alternate = json.loads((copied_step4 / "state/up-run-e043d1eed718.json").read_text())
    alternate["run_id"] = alternate_id
    alternate["parent_run_id"] = "up-run-453b83f9cdf1"
    (copied_step4 / "state" / f"{alternate_id}.json").write_text(json.dumps(alternate))
    answers = _step11_resume_answers()
    answers.update({
        "client": "bteam", "source_run_id": alternate_id,
        "first_unfinished_phase": "compose-insight-cards",
        "reopen_completed_phase": False,
        "step4_clean_task_dir": str(copied_step4),
        "step11_writer_input_path": None,
        "step11_writer_call_budget_path": None,
        "step11_writer_call_limit": None,
    })
    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation", answers,
        artifact_paths={}, repository_roots={"united-partners": str(repository_copy)},
    )
    assert prepared["argv"][prepared["argv"].index("--resume-run") + 1] == alternate_id
    assert Path(prepared["environment"]["UP_HARNESS_GOOGLE_DRIVE_ROOT"]).resolve() == (
        repository_copy / "Tasks" / f"bteam-step5-clean-{alternate_id.removeprefix('up-run-')}" / "drive-staging"
    ).resolve()
    unrelated_id = "up-run-e2e3e4e5e6e7"
    unrelated = json.loads(json.dumps(alternate))
    unrelated["run_id"] = unrelated_id
    unrelated.pop("parent_run_id", None)
    (copied_step4 / "state" / f"{unrelated_id}.json").write_text(json.dumps(unrelated))
    answers["source_run_id"] = unrelated_id
    with pytest.raises(sequence_intake_adapters.AdapterError,
                       match="step5-clean-copy-source-lineage-mismatch"):
        sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots={"united-partners": str(repository_copy)},
        )
    answers["source_run_id"] = alternate_id
    alternate["phases"]["research-gate"]["ledger"]["status"] = "blocked"
    (copied_step4 / "state" / f"{alternate_id}.json").write_text(json.dumps(alternate))
    with pytest.raises(sequence_intake_adapters.AdapterError,
                       match="step5-clean-copy-source-not-passed-for-client"):
        sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots={"united-partners": str(repository_copy)},
        )

    wrong = _step11_resume_answers()
    wrong.update({
        "client": "bteam", "source_run_id": "up-run-3d3b70a2f645",
        "first_unfinished_phase": "compose-insight-cards",
        "reopen_completed_phase": False,
        "step4_clean_task_dir": str(repository / "Tasks/vivacom-step4-clean-ace8371a0179"),
        "step11_writer_input_path": None,
        "step11_writer_call_budget_path": None,
        "step11_writer_call_limit": None,
    })
    with pytest.raises(sequence_intake_adapters.AdapterError,
                       match="step4-clean-copy-missing-or-mismatched"):
        sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", wrong,
            artifact_paths={}, repository_roots={"united-partners": str(repository)},
        )

@pytest.mark.parametrize("schema", ["step5-clean-copy/v3", "step5-clean-copy/v4"])
def test_step5_accepted_copy_uses_harness_admission_contract(tmp_path, monkeypatch, schema):
    import subprocess

    repository = tmp_path / "united-partners"
    copy = repository / "Tasks/bteam-step5-clean-c7475afdb640"
    (copy / "state").mkdir(parents=True)
    (copy / "record").mkdir()
    root_id = "up-run-c7475afdb640"
    state = {
        "run_id": root_id,
        "context": {"inputs": {
            "client_name": "The B Team", "client_code": "BTM",
            "stop_after_phase": "insight-gate", "step5_writer_call_limit": 60,
        }},
        "phases": {"research-gate": {
            "status": "completed", "ledger": {"status": "passed"},
        }},
    }
    raw = (json.dumps(state, sort_keys=True) + "\n").encode()
    (copy / "state" / f"{root_id}.json").write_bytes(raw)
    manifest = {
        "schema": schema, "client": "bteam",
        "source_run_id": root_id, "first_phase": "compose-insight-cards",
        "stop_after_phase": "insight-gate", "writer_call_limit": 60,
        "clean_state_sha256": hashlib.sha256(raw).hexdigest(),
        "source_admission": "passed",
    }
    (copy / "record/step5-clean-copy.json").write_text(json.dumps(manifest))
    answers = _step11_resume_answers()
    answers.update({
        "client": "bteam", "source_run_id": root_id,
        "first_unfinished_phase": "compose-insight-cards",
        "reopen_completed_phase": False,
        "step5_clean_task_dir": str(copy),
        "step11_writer_input_path": None,
        "step11_writer_call_budget_path": None,
        "step11_writer_call_limit": None,
    })
    seen = []

    def verify(argv, **kwargs):
        seen.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="admitted", stderr="")

    monkeypatch.setattr(sequence_intake_adapters.subprocess, "run", verify)
    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation", answers,
        artifact_paths={}, repository_roots={"united-partners": str(repository)},
    )
    assert prepared["argv"][-2:] == ["--task-dir", str(copy)]
    assert seen[0][-4:] == ["--client", "bteam", "--verify-copy", str(copy)]

    def refuse(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="refused")

    monkeypatch.setattr(sequence_intake_adapters.subprocess, "run", refuse)
    with pytest.raises(sequence_intake_adapters.AdapterError,
                       match="step5-clean-copy-accepted-admission-refused"):
        sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots={"united-partners": str(repository)},
        )

def test_step5_current_copy_resumes_only_valid_client_descendants_with_shared_budget(tmp_path):
    actual_repo = Path("/Users/kamenkamenov/united-partners")
    repository = tmp_path / "united-partners"
    client = "bteam"
    step4_relative = Path("Tasks/bteam-step4-clean-453b83f9cdf1")
    source_id = "up-run-e043d1eed718"
    root_id = source_id
    step4_source_relative = step4_relative / "state" / f"{source_id}.json"
    relative_source = step4_source_relative.as_posix()
    step4_copy = repository / step4_relative
    source_dir = actual_repo / step4_relative
    import shutil
    shutil.copytree(source_dir, step4_copy)
    source_path = repository / step4_source_relative
    source_bytes = source_path.read_bytes()
    source = json.loads(source_bytes)
    step3_dir = json.loads((source_dir / "record/step4-clean-copy.json").read_text())["source_task_dir"]
    shutil.copytree(actual_repo / step3_dir, repository / step3_dir)
    step4_manifest_bytes = (step4_copy / "record/step4-clean-copy.json").read_bytes()
    root = json.loads(source_bytes)
    inputs = root["context"]["inputs"]
    inputs.update({"stop_after_phase": "insight-gate", "step5_writer_call_limit": 60})
    root_bytes = (json.dumps(root, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    copy = repository / "Tasks" / f"bteam-step5-clean-{source_id.removeprefix('up-run-')}"
    (copy / "state").mkdir(parents=True)
    (copy / "record").mkdir()
    (copy / "state" / f"{root_id}.json").write_bytes(root_bytes)
    manifest = {
        "schema": "step5-clean-copy/v2", "client": client,
        "source_run_id": source_id, "source_state_path": relative_source,
        "source_task_dir": str(Path(relative_source).parent.parent),
        "step4_manifest_sha256": hashlib.sha256(step4_manifest_bytes).hexdigest(),
        "source_state_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "clean_state_sha256": hashlib.sha256(root_bytes).hexdigest(),
        "first_phase": "compose-insight-cards", "stop_after_phase": "insight-gate",
        "writer_call_limit": 60, "source_admission": "passed",
        "source_review_hold_sha256": None,
    }
    (copy / "record" / "step5-clean-copy.json").write_text(json.dumps(manifest))
    child_id = "up-run-c1c2c3c4c5c6"
    child = {
        "run_id": child_id, "parent_run_id": source_id, "status": "blocked",
        "context": {
            "inputs": {"client_name": "The B Team", "client_code": "BTM"},
            "up": {"cd_s_002": {
                "step5_part_ledger": {"writer_calls_used": 35, "writer_call_limit": 60,
                                        "inflight": {"call": 35}},
                "step5_mini_board_ledger": {"writer_calls_used": 25},
            }},
        },
        "phases": {"compose-insight-cards": {"status": "blocked"}},
    }
    (copy / "state" / f"{child_id}.json").write_text(json.dumps(child))
    answers = _step11_resume_answers()
    answers.update({
        "client": client, "source_run_id": child_id,
        "first_unfinished_phase": "compose-insight-cards",
        "reopen_completed_phase": False,
        "step5_clean_task_dir": str(copy),
        "step11_writer_input_path": None,
        "step11_writer_call_budget_path": None,
        "step11_writer_call_limit": None,
    })
    roots = {"united-partners": str(repository)}
    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation", answers,
        artifact_paths={}, repository_roots=roots,
    )
    assert prepared["argv"][prepared["argv"].index("--resume-run") + 1] == child_id
    assert prepared["argv"][prepared["argv"].index("--task-dir") + 1] == str(copy)
    assert prepared["environment"]["UP_HARNESS_GOOGLE_DRIVE_ROOT"] == str(copy / "drive-staging")
    source_path.write_bytes(source_bytes + b"\n")
    with pytest.raises(sequence_intake_adapters.AdapterError,
                       match="step5-clean-copy-manifest-mismatch"):
        sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots=roots,
        )
    source_path.write_bytes(source_bytes)
    child["context"]["inputs"]["client_code"] = "VIV"
    (copy / "state" / f"{child_id}.json").write_text(json.dumps(child))
    with pytest.raises(sequence_intake_adapters.AdapterError,
                       match="step5-clean-copy-lineage-mismatch"):
        sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots=roots,
        )
    source_path.write_bytes(source_bytes)
    root_path = copy / "state" / f"{source_id}.json"
    root_path.write_bytes(root_bytes + b"\n")
    with pytest.raises(sequence_intake_adapters.AdapterError,
                       match="step5-clean-copy-manifest-mismatch"):
        sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots=roots,
        )
    root_path.write_bytes(root_bytes)
    manifest["source_state_path"] = "Tasks/bteam-corporate-demo/state/up-run-e043d1eed718.json"
    (copy / "record" / "step5-clean-copy.json").write_text(json.dumps(manifest))
    with pytest.raises(sequence_intake_adapters.AdapterError,
                       match="step5-clean-copy-manifest-mismatch"):
        sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots=roots,
        )
    manifest["source_state_path"] = relative_source
    (copy / "record" / "step5-clean-copy.json").write_text(json.dumps(manifest))
    child["context"]["inputs"]["client_code"] = "BTM"
    child["context"]["up"]["cd_s_002"]["step5_mini_board_ledger"]["writer_calls_used"] = 26
    (copy / "state" / f"{child_id}.json").write_text(json.dumps(child))
    with pytest.raises(sequence_intake_adapters.AdapterError,
                       match="step5-clean-copy-call-budget-invalid"):
        sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots=roots,
        )

def test_step5_clean_copy_requires_exact_held_source_and_isolates_drive(tmp_path):
    import hashlib

    repository = tmp_path / "united-partners"
    copy = repository / "Tasks" / "bteam-step5-clean-20261005"
    (copy / "state").mkdir(parents=True)
    (copy / "record").mkdir()
    hold = {
        "schema": "step4-step5-source-hold/v1", "client": "bteam",
        "run_id": "up-run-step4", "verdict": "held",
        "reviewer": "Kamen Kamenov",
    }
    state = {
        "run_id": "up-run-step4",
        "context": {
            "inputs": {"stop_after_phase": "insight-gate", "step5_writer_call_limit": 60},
            "up": {"cd_s_002": {"step4_review_hold": hold}},
        },
        "phases": {"research-gate": {
            "status": "completed", "ledger": {"status": "held"},
        }},
    }
    state_bytes = (json.dumps(state, sort_keys=True, indent=2) + "\n").encode()
    (copy / "state" / "up-run-step4.json").write_bytes(state_bytes)
    hold_sha = hashlib.sha256(
        (json.dumps(hold, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":")) + "\n").encode()
    ).hexdigest()
    manifest = {
        "schema": "step5-clean-copy/v1", "client": "bteam",
        "source_run_id": "up-run-step4", "first_phase": "compose-insight-cards",
        "stop_after_phase": "insight-gate", "writer_call_limit": 60,
        "source_admission": "held", "source_review_hold_sha256": hold_sha,
        "clean_state_sha256": hashlib.sha256(state_bytes).hexdigest(),
    }
    (copy / "record" / "step5-clean-copy.json").write_text(json.dumps(manifest))
    answers = _step11_resume_answers()
    answers.update({
        "client": "bteam", "source_run_id": "up-run-step4",
        "first_unfinished_phase": "compose-insight-cards",
        "step5_clean_task_dir": str(copy),
        "step11_writer_input_path": None,
        "step11_writer_call_budget_path": None,
        "step11_writer_call_limit": None,
    })
    roots = {"united-partners": str(repository)}
    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation", answers,
        artifact_paths={}, repository_roots=roots,
    )
    assert prepared["argv"][-2:] == ["--task-dir", str(copy)]
    assert prepared["environment"]["UP_HARNESS_GOOGLE_DRIVE_ROOT"] == str(copy / "drive-staging")
    assert prepared["environment"]["UP_HARNESS_GOOGLE_DRIVE_ACCESS_TOKEN"] == ""
    repaired = {
        "run_id": "up-run-step5-repaired", "parent_run_id": "up-run-step4",
        "status": "blocked",
        "phases": {
            "insight-mini-board-gate": {"status": "completed"},
            "insight-gate": {"status": "blocked"},
        },
    }
    (copy / "state" / "up-run-step5-repaired.json").write_text(json.dumps(repaired))
    answers.update({
        "source_run_id": "up-run-step5-repaired",
        "first_unfinished_phase": "insight-mini-board-gate",
        "reopen_completed_phase": True,
    })
    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation", answers,
        artifact_paths={}, repository_roots=roots,
    )
    assert "--rerun-completed" in prepared["argv"]
    assert prepared["argv"][-2:] == ["--task-dir", str(copy)]
    manifest["source_review_hold_sha256"] = "0" * 64
    (copy / "record" / "step5-clean-copy.json").write_text(json.dumps(manifest))
    with pytest.raises(sequence_intake_adapters.AdapterError, match="step5-clean-copy-manifest-mismatch"):
        sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots=roots,
        )

def test_workflow_phase_resume_step9_rehearsal_stays_in_copy():
    answers = _step11_resume_answers()
    answers.update({
        "client": "vivacom",
        "first_unfinished_phase": "compose-execution-toolkit",
        "reopen_completed_phase": True,
        "step11_writer_input_path": None,
        "step11_writer_call_budget_path": None,
        "step11_writer_call_limit": None,
        "step9_rehearsal_task_dir": "Tasks/vivacom-rehearsal-demo",
        "step9_native_writer_call_limit": 60,
        "step9_native_writer_continuation": None,
        "step9_native_writer_extend_to": None,
    })
    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation",
        answers, artifact_paths={},
        repository_roots={"united-partners": "/repos/united-partners"},
    )
    assert prepared["argv"][-5:] == [
        "--rerun-completed", "--task-dir",
        "/repos/united-partners/Tasks/vivacom-rehearsal-demo",
        "--step9-native-writer-call-limit", "60",
    ]
    assert prepared["environment"]["UP_HARNESS_AGENT_MAX_ATTEMPTS"] == "1"
    assert prepared["environment"]["UP_HARNESS_GOOGLE_DRIVE_ACCESS_TOKEN"] == ""
    assert prepared["environment"]["UP_HARNESS_GOOGLE_DRIVE_ROOT"] == (
        "/repos/united-partners/Tasks/vivacom-rehearsal-demo/drive-staging"
    )
    answers["step9_native_writer_call_limit"] = 150
    approved = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation", answers, artifact_paths={},
        repository_roots={"united-partners": "/repos/united-partners"},
    )
    assert approved["argv"][-1] == "150"
    answers["step9_rehearsal_task_dir"] = "Tasks/vivacom-corporate-demo"
    with pytest.raises(sequence_intake_adapters.AdapterError, match="copy-folder-mismatch"):
        sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={},
            repository_roots={"united-partners": "/repos/united-partners"},
        )

@pytest.mark.parametrize("phase", ["compose-execution-toolkit", "compose-annual-review"])
def test_workflow_phase_resume_automatic_writer_stays_in_copy_without_override(phase):
    answers = _step11_resume_answers()
    answers.update({
        "client": "bteam",
        "first_unfinished_phase": phase,
        "step11_writer_input_path": None,
        "step11_writer_call_budget_path": None,
        "step11_writer_call_limit": None,
        "step9_rehearsal_task_dir": "Tasks/bteam-rehearsal-demo",
    })
    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation", answers,
        artifact_paths={}, repository_roots={"united-partners": "/repos/united-partners"},
    )
    assert prepared["argv"][-2:] == [
        "--task-dir", "/repos/united-partners/Tasks/bteam-rehearsal-demo",
    ]
    assert "--step9-native-writer-call-limit" not in prepared["argv"]
    assert "--step11-writer-input-file" not in prepared["argv"]
    assert prepared["environment"]["UP_HARNESS_AGENT_MAX_ATTEMPTS"] == "1"
    assert prepared["environment"]["UP_HARNESS_GOOGLE_DRIVE_ACCESS_TOKEN"] == ""
    answers["step9_rehearsal_task_dir"] = "Tasks/bteam-corporate-demo"
    with pytest.raises(sequence_intake_adapters.AdapterError, match="copy-folder-mismatch"):
        sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots={"united-partners": "/repos/united-partners"},
        )

@pytest.mark.parametrize("phase,field,flag,reopen", [
    ("compose-measurement-framework", "step10_admission_path", "--step10-admission-file", True),
    ("measurement-gate", "step10_altitude_check_path", "--altitude-check-file", False),
    ("annual-review-gate", "step11_altitude_check_path", "--altitude-check-file", False),
    ("compose-annual-review", None, None, False),
])
def test_clean_step11_route_uses_new_copy_and_exact_entry(tmp_path, phase, field, flag, reopen):
    repository = tmp_path / "united-partners"
    clean = repository / "Tasks" / "bteam-step11-clean-20261002"
    (clean / "record").mkdir(parents=True)
    answers = _step11_resume_answers()
    answers.update({
        "client": "bteam", "first_unfinished_phase": phase,
        "reopen_completed_phase": reopen,
        "step11_writer_input_path": None,
        "step11_writer_call_budget_path": None,
        "step11_writer_call_limit": None,
        "step11_clean_task_dir": str(clean),
    })
    if field:
        name = {
            "step10_admission_path": "step10-admission.json",
            "step10_altitude_check_path": "measurement-altitude-check.json",
            "step11_altitude_check_path": "annual-review-altitude-check.json",
        }[field]
        path = clean / "record" / name
        path.write_text("{}", encoding="utf-8")
        answers[field] = str(path)
    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation", answers,
        artifact_paths={}, repository_roots={"united-partners": str(repository)},
    )
    argv = prepared["argv"]
    assert argv[argv.index("--task-dir") + 1] == str(clean)
    assert (flag in argv) if flag else ("--step10-admission-file" not in argv and "--altitude-check-file" not in argv)
    assert prepared["environment"]["UP_HARNESS_GOOGLE_DRIVE_ROOT"] == str(clean / "drive-staging")
    answers["step11_clean_task_dir"] = str(repository / "Tasks" / "bteam-corporate-demo")
    with pytest.raises(sequence_intake_adapters.AdapterError, match="copy-folder-mismatch"):
        sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots={"united-partners": str(repository)},
        )

def test_clean_step11_failed_writer_resumes_with_bound_input_and_same_budget(tmp_path):
    repository = tmp_path / "united-partners"
    clean = repository / "Tasks" / "vivacom-step11-clean-20261002"
    (clean / "record").mkdir(parents=True)
    (clean / "state").mkdir()
    source_run = "up-run-saved-failure"
    writer_source = "up-run-original-step11-source"
    input_path = clean / "record" / "step11-writer-input-v3.json"
    budget_path = clean / "state" / f"step11-writer-budget-{writer_source}.json"
    input_path.write_text(json.dumps({"source_run_id": writer_source}), encoding="utf-8")
    budget_path.write_text('{"limit":100,"reserved_calls":2}', encoding="utf-8")
    answers = _step11_resume_answers()
    answers.update({
        "client": "vivacom", "source_run_id": source_run,
        "first_unfinished_phase": "compose-annual-review",
        "reopen_completed_phase": False,
        "step11_clean_task_dir": str(clean),
        "step11_writer_input_path": str(input_path),
        "step11_writer_call_budget_path": str(budget_path),
        "step11_writer_call_limit": 100,
    })
    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation", answers,
        artifact_paths={}, repository_roots={"united-partners": str(repository)},
    )
    argv = prepared["argv"]
    assert argv[argv.index("--task-dir") + 1] == str(clean)
    assert argv[argv.index("--step11-writer-input-file") + 1] == str(input_path)
    assert argv[argv.index("--step11-writer-call-budget-file") + 1] == str(budget_path)
    assert prepared["environment"]["UP_HARNESS_GOOGLE_DRIVE_ROOT"] == str(clean / "drive-staging")
    answers["reopen_completed_phase"] = True
    reopened = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation", answers,
        artifact_paths={}, repository_roots={"united-partners": str(repository)},
    )
    assert "--rerun-completed" in reopened["argv"]
    assert reopened["argv"][reopened["argv"].index("--step11-writer-call-budget-file") + 1] == str(budget_path)
    answers["reopen_completed_phase"] = False
    answers["step11_writer_call_budget_path"] = str(clean / "record" / "different-ledger.json")
    with pytest.raises(sequence_intake_adapters.AdapterError, match="input-or-budget-mismatch"):
        sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots={"united-partners": str(repository)},
        )

def test_workflow_phase_resume_continues_saved_step9_writer_cache():
    answers = _step11_resume_answers()
    answers.update({
        "client": "bteam",
        "source_run_id": "up-run-b41410c16284",
        "first_unfinished_phase": "compose-execution-toolkit",
        "reopen_completed_phase": False,
        "step11_writer_input_path": None,
        "step11_writer_call_budget_path": None,
        "step11_writer_call_limit": None,
        "step9_rehearsal_task_dir": "Tasks/bteam-rehearsal-demo",
        "step9_native_writer_call_limit": None,
        "step9_native_writer_continuation": True,
        "step9_native_writer_extend_to": None,
    })
    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation",
        answers,
        artifact_paths={},
        repository_roots={"united-partners": "/repos/united-partners"},
    )
    assert prepared["argv"][-5:] == [
        "--from-phase", "compose-execution-toolkit",
        "--task-dir", "/repos/united-partners/Tasks/bteam-rehearsal-demo",
        "--step9-native-writer-continue",
    ]
    assert "--rerun-completed" not in prepared["argv"]
    assert "--step9-native-writer-call-limit" not in prepared["argv"]
    assert prepared["environment"]["UP_HARNESS_AGENT_MAX_ATTEMPTS"] == "1"
    assert prepared["environment"]["UP_HARNESS_GOOGLE_DRIVE_ACCESS_TOKEN"] == ""
    assert prepared["environment"]["UP_HARNESS_GOOGLE_DRIVE_PARENT_ID"] == ""
    assert prepared["environment"]["UP_HARNESS_GOOGLE_DRIVE_ROOT"] == (
        "/repos/united-partners/Tasks/bteam-rehearsal-demo/drive-staging"
    )

    for changes, message in (
        ({"reopen_completed_phase": True}, "preserve-blocked-phase"),
        ({"step9_native_writer_call_limit": 30}, "reuse-saved-call-limit"),
        ({"step9_rehearsal_task_dir": "Tasks/bteam-corporate-demo"}, "copy-folder-mismatch"),
    ):
        invalid = dict(answers)
        invalid.update(changes)
        with pytest.raises(sequence_intake_adapters.AdapterError, match=message):
            sequence_intake_adapters.prepare(
                "workflow-resume-from-phase-live-confirmation",
                invalid,
                artifact_paths={},
                repository_roots={"united-partners": "/repos/united-partners"},
            )

def test_workflow_phase_resume_extends_only_approved_failed_bteam_step9_budget():
    answers = _step11_resume_answers()
    answers.update({
        "client": "bteam",
        "source_run_id": "up-run-9e6d9c40be19",
        "first_unfinished_phase": "compose-execution-toolkit",
        "reopen_completed_phase": False,
        "step11_writer_input_path": None,
        "step11_writer_call_budget_path": None,
        "step11_writer_call_limit": None,
        "step9_rehearsal_task_dir": "Tasks/bteam-rehearsal-demo",
        "step9_native_writer_call_limit": None,
        "step9_native_writer_continuation": True,
        "step9_native_writer_extend_to": 60,
    })
    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation",
        answers, artifact_paths={},
        repository_roots={"united-partners": "/repos/united-partners"},
    )
    assert prepared["argv"][-6:] == [
        "compose-execution-toolkit",
        "--task-dir", "/repos/united-partners/Tasks/bteam-rehearsal-demo",
        "--step9-native-writer-continue", "--step9-native-writer-extend-to", "60",
    ]
    assert prepared["environment"]["UP_HARNESS_AGENT_MAX_ATTEMPTS"] == "1"
    assert prepared["environment"]["UP_HARNESS_GOOGLE_DRIVE_ACCESS_TOKEN"] == ""
    assert prepared["environment"]["UP_HARNESS_GOOGLE_DRIVE_ROOT"] == (
        "/repos/united-partners/Tasks/bteam-rehearsal-demo/drive-staging"
    )

    for changes, message in (
        ({"source_run_id": "up-run-some-other-run"}, "selected-run-mismatch"),
        ({"client": "vivacom", "step9_rehearsal_task_dir": "Tasks/vivacom-rehearsal-demo"}, "step9-budget-extension-selected-run-mismatch"),
        ({"step9_native_writer_extend_to": 61}, "selected-run-mismatch"),
        ({"step9_native_writer_call_limit": 60}, "extend-to-only"),
        ({"step9_rehearsal_task_dir": "Tasks/bteam-corporate-demo"}, "copy-folder-mismatch"),
    ):
        invalid = dict(answers)
        invalid.update(changes)
        with pytest.raises(sequence_intake_adapters.AdapterError, match=message):
            sequence_intake_adapters.prepare(
                "workflow-resume-from-phase-live-confirmation", invalid,
                artifact_paths={},
                repository_roots={"united-partners": "/repos/united-partners"},
            )

def test_workflow_phase_resume_extends_latest_exhausted_step9_child_to_150():
    answers = _step11_resume_answers()
    answers.update({
        "client": "bteam", "source_run_id": "up-run-6644b0907f3a",
        "first_unfinished_phase": "compose-execution-toolkit",
        "reopen_completed_phase": False,
        "step11_writer_input_path": None, "step11_writer_call_budget_path": None,
        "step11_writer_call_limit": None,
        "step9_rehearsal_task_dir": "Tasks/bteam-rehearsal-demo",
        "step9_native_writer_call_limit": None,
        "step9_native_writer_continuation": True,
        "step9_native_writer_extend_to": 150,
    })
    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation", answers, artifact_paths={},
        repository_roots={"united-partners": "/repos/united-partners"},
    )
    assert prepared["argv"][-2:] == ["--step9-native-writer-extend-to", "150"]
    answers["step9_native_writer_extend_to"] = 151
    with pytest.raises(sequence_intake_adapters.AdapterError, match="selected-run-mismatch"):
        sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers, artifact_paths={},
            repository_roots={"united-partners": "/repos/united-partners"},
        )

def test_workflow_phase_resume_routes_saved_step9_continuation_generically():
    answers = _step11_resume_answers()
    answers.update({
        "client": "bteam",
        "first_unfinished_phase": "compose-execution-toolkit",
        "reopen_completed_phase": False,
        "step11_writer_input_path": None,
        "step11_writer_call_budget_path": None,
        "step11_writer_call_limit": None,
        "step9_rehearsal_task_dir": "Tasks/bteam-rehearsal-demo",
        "step9_native_writer_call_limit": None,
        "step9_native_writer_continuation": True,
        "step9_native_writer_extend_to": None,
    })
    for source_run_id in (
        "up-run-b41410c16284", "up-run-fb7e1745a0ba", "up-run-81a516b79cb5",
    ):
        answers["source_run_id"] = source_run_id
        prepared = sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation",
            answers, artifact_paths={},
            repository_roots={"united-partners": "/repos/united-partners"},
        )
        assert prepared["argv"][-5:] == [
            "--from-phase", "compose-execution-toolkit",
            "--task-dir", "/repos/united-partners/Tasks/bteam-rehearsal-demo",
            "--step9-native-writer-continue",
        ]
        assert "--rerun-completed" not in prepared["argv"]
        assert "--step9-native-writer-extend-to" not in prepared["argv"]
        assert "--step9-native-writer-call-limit" not in prepared["argv"]

    for changes, message in (
        ({"step9_rehearsal_task_dir": "Tasks/bteam-corporate-demo"}, "copy-folder-mismatch"),
        ({"reopen_completed_phase": True}, "preserve-blocked-phase"),
        ({"step9_native_writer_call_limit": 60}, "reuse-saved-call-limit"),
    ):
        invalid = dict(answers)
        invalid.update(changes)
        with pytest.raises(sequence_intake_adapters.AdapterError, match=message):
            sequence_intake_adapters.prepare(
                "workflow-resume-from-phase-live-confirmation", invalid,
                artifact_paths={},
                repository_roots={"united-partners": "/repos/united-partners"},
            )

def test_workflow_phase_resume_maps_all_step11_writer_settings():
    spec = sequence_intake_adapters.intake_spec(
        "workflow-resume-from-phase-live-confirmation",
        repository_roots={"united-partners": "/repos/united-partners"},
    )
    call_limit_field = next(
        field for field in spec["fields"]
        if field["id"] == "step11_writer_call_limit"
    )
    assert call_limit_field["type"] == "integer"
    assert call_limit_field["minimum"] == 1
    assert call_limit_field["required"] is False

    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation",
        _step11_resume_answers(),
        artifact_paths={},
        repository_roots={"united-partners": "/repos/united-partners"},
    )

    assert prepared["argv"][-6:] == [
        "--step11-writer-input-file", "/runs/source/step11-input.json",
        "--step11-writer-call-budget-file", "/runs/shared/writer-budget.json",
        "--step11-writer-call-limit", "12",
    ]

def test_workflow_phase_resume_maps_explicit_step11_budget_extension():
    answers = _step11_resume_answers()
    answers["step11_writer_call_limit"] = 100
    answers["step11_writer_call_extension_from"] = 80
    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation",
        answers,
        artifact_paths={},
        repository_roots={"united-partners": "/repos/united-partners"},
    )
    assert prepared["argv"][-2:] == ["--step11-writer-call-extension-from", "80"]

    answers["step11_writer_call_limit"] = 80
    with pytest.raises(sequence_intake_adapters.AdapterError, match="invalid-step11-writer-call-extension"):
        sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation",
            answers,
            artifact_paths={},
            repository_roots={"united-partners": "/repos/united-partners"},
        )

@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        (
            "step11_writer_call_limit", None,
            "step11-writer-input-requires-input-budget-and-limit",
        ),
        (
            "step11_writer_call_budget_path", None,
            "step11-writer-input-requires-input-budget-and-limit",
        ),
        (
            "first_unfinished_phase", "compose-quarterly-review",
            "step11-writer-input-needs-compose-annual-review",
        ),
        (
            "client_answers_path", "/runs/late-answers.json",
            "step11-writer-input-exclusive-with-other-resume-inputs",
        ),
        (
            "debrief_feedback_path", "/runs/debrief.json",
            "step11-writer-input-exclusive-with-other-resume-inputs",
        ),
        (
            "final_brief_feedback_path", "/runs/final-brief.json",
            "step11-writer-input-exclusive-with-other-resume-inputs",
        ),
        (
            "gate_approvals_path", "/runs/gate-approvals.json",
            "step11-writer-input-exclusive-with-other-resume-inputs",
        ),
        (
            "corrected_topic_policies_path", "/runs/topic-policies.json",
            "step11-writer-input-exclusive-with-other-resume-inputs",
        ),
        ("step11_writer_call_limit", 0, "invalid-step11-writer-call-limit"),
        ("step11_writer_call_limit", True, "invalid-step11-writer-call-limit"),
        ("step11_writer_call_extension_from", 12, "invalid-step11-writer-call-extension"),
        ("step11_writer_call_extension_from", True, "invalid-step11-writer-call-extension"),
    ],
)
def test_workflow_phase_resume_rejects_invalid_step11_writer_settings(
    key, value, message,
):
    answers = _step11_resume_answers()
    answers[key] = value

    with pytest.raises(sequence_intake_adapters.AdapterError, match=message):
        sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation",
            answers,
            artifact_paths={},
            repository_roots={"united-partners": "/repos/united-partners"},
        )

def _step12_answers(repository, phase, *, client="bteam", name=None, gate_file=False):
    copy = repository / "Tasks" / (name or f"{client}-step12-20261010")
    (copy / "state").mkdir(parents=True, exist_ok=True)
    (copy / "record").mkdir(parents=True, exist_ok=True)
    answers = _step11_resume_answers()
    answers.update({
        "client": client, "first_unfinished_phase": phase,
        "reopen_completed_phase": False,
        "step11_writer_input_path": None,
        "step11_writer_call_budget_path": None,
        "step11_writer_call_limit": None,
        "step12_task_dir": str(copy),
    })
    if gate_file:
        holder = copy / "record" / "roadmap-altitude-check.json"
        holder.write_text("{}", encoding="utf-8")
        answers["step12_altitude_check_path"] = str(holder)
    return copy, answers

def _prepare_step12(repository, answers):
    return sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation", answers,
        artifact_paths={}, repository_roots={"united-partners": str(repository)},
    )

@pytest.mark.parametrize("client", ["bteam", "vivacom"])
@pytest.mark.parametrize("phase", sequence_intake_adapters.STEP12_ALLOWED_PHASES)
def test_step12_route_accepts_each_allowed_phase_inside_the_copy(tmp_path, client, phase):
    repository = tmp_path / "united-partners"
    copy, answers = _step12_answers(repository, phase, client=client,
                                    gate_file=(phase == "roadmap-gate"))
    prepared = _prepare_step12(repository, answers)
    argv = prepared["argv"]
    assert argv[argv.index("--task-dir") + 1] == str(copy.resolve())
    assert ("--altitude-check-file" in argv) == (phase == "roadmap-gate")
    assert "--rerun-completed" not in argv
    env = prepared["environment"]
    assert env["UP_HARNESS_GOOGLE_DRIVE_ROOT"] == str(copy.resolve() / "drive-staging")
    assert env["UP_HARNESS_GOOGLE_DRIVE_ACCESS_TOKEN"] == ""
    assert env["UP_HARNESS_GOOGLE_DRIVE_PARENT_ID"] == ""

def test_step12_phase_list_matches_the_workflow_definition():
    import yaml
    workflow = Path("/Users/kamenkamenov/united-partners/workflows/cd-s-002-corporate-communications-strategy.yaml")
    if not workflow.is_file():
        pytest.skip("united-partners workflow not present")
    text = workflow.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    phases = data.get("phases") if isinstance(data, dict) else None
    ids = [p.get("id") or p.get("name") for p in phases] if isinstance(phases, list) else []
    if "annual-review-gate" not in ids:
        pytest.skip("cannot read phase ids from workflow file")
    after = ids[ids.index("annual-review-gate") + 1:]
    assert tuple(after[:len(sequence_intake_adapters.STEP12_ALLOWED_PHASES)]) == sequence_intake_adapters.STEP12_ALLOWED_PHASES

def test_step12_route_refusals_are_named(tmp_path):
    repository = tmp_path / "united-partners"

    def refused(answers, match):
        with pytest.raises(sequence_intake_adapters.AdapterError, match=match):
            _prepare_step12(repository, answers)

    # wrong client (folder belongs to the other client)
    _, answers = _step12_answers(repository, "assemble-step-dossier", name="vivacom-step12-20261010")
    refused(answers, "step12-copy-folder-name-mismatch")
    # wrong folder name
    _, answers = _step12_answers(repository, "assemble-step-dossier", name="bteam-step12-draft")
    refused(answers, "step12-copy-folder-name-mismatch")
    _, answers = _step12_answers(repository, "assemble-step-dossier", name="bteam-step11-clean-20261002")
    refused(answers, "step12-copy-folder-name-mismatch")
    # folder outside Tasks/
    outside = tmp_path / "bteam-step12-20261010"
    (outside / "state").mkdir(parents=True)
    (outside / "record").mkdir()
    _, answers = _step12_answers(repository, "assemble-step-dossier")
    answers["step12_task_dir"] = str(outside)
    refused(answers, "step12-copy-folder-outside-tasks")
    # missing folder
    _, answers = _step12_answers(repository, "assemble-step-dossier")
    answers["step12_task_dir"] = str(repository / "Tasks" / "bteam-step12-20261111")
    refused(answers, "step12-copy-folder-missing")
    # folder without state/record
    bare = repository / "Tasks" / "bteam-step12-20261212"
    bare.mkdir(parents=True)
    answers["step12_task_dir"] = str(bare)
    refused(answers, "step12-copy-folder-needs-state-and-record")
    # disallowed phase
    for phase in ("annual-review-gate", "compose-annual-review", "toolkit-ship-gate"):
        _, answers = _step12_answers(repository, phase)
        refused(answers, "step12-phase-not-allowed")
    # reopen of a completed phase
    _, answers = _step12_answers(repository, "compose-tactical-roadmap")
    answers["reopen_completed_phase"] = True
    refused(answers, "step12-must-resume-first-unfinished-phase")
    # gate file at a non-gate phase
    _, answers = _step12_answers(repository, "compose-tactical-roadmap", gate_file=True)
    refused(answers, "step12-holder-check-needs-roadmap-gate")
    # gate file in the wrong place
    copy, answers = _step12_answers(repository, "roadmap-gate")
    wrong = copy / "state" / "roadmap-altitude-check.json"
    wrong.write_text("{}", encoding="utf-8")
    answers["step12_altitude_check_path"] = str(wrong)
    refused(answers, "step12-holder-check-file-mismatch")
    # gate file named but missing
    fresh_copy, answers = _step12_answers(repository, "roadmap-gate", name="bteam-step12-20270101")
    answers["step12_altitude_check_path"] = str(fresh_copy / "record" / "roadmap-altitude-check.json")
    refused(answers, "step12-holder-check-file-mismatch")
    # gate file without the folder answer
    _, answers = _step12_answers(repository, "roadmap-gate", gate_file=True)
    answers["step12_task_dir"] = None
    refused(answers, "step12-requires-its-own-copy-folder")
    # two gate inputs at once
    _, answers = _step12_answers(repository, "roadmap-gate", gate_file=True)
    answers["step11_altitude_check_path"] = answers["step12_altitude_check_path"]
    refused(answers, "step12-one-gate-input-at-a-time")
    # exclusive with other resume inputs
    _, answers = _step12_answers(repository, "roadmap-gate", gate_file=True)
    answers["gate_approvals_path"] = "/x/approvals.json"
    refused(answers, "step12-exclusive-with-other-resume-inputs")
    _, answers = _step12_answers(repository, "assemble-step-dossier")
    answers["step9_rehearsal_task_dir"] = "Tasks/bteam-rehearsal-demo"
    refused(answers, "step12-exclusive-with-other-resume-inputs")
    _, answers = _step12_answers(repository, "assemble-step-dossier")
    answers["step11_clean_task_dir"] = str(repository / "Tasks" / "bteam-step11-clean-20261002")
    refused(answers, "step12-exclusive-with-other-resume-inputs")

def test_step6_clean_copy_requires_exact_held_source_and_isolates_drive(tmp_path):
    import hashlib

    repository = tmp_path / "united-partners"
    copy = repository / "Tasks" / "bteam-step6-clean-20261006"
    (copy / "state").mkdir(parents=True)
    (copy / "record").mkdir()
    hold = {
        "schema": "step5-maria-review-hold/v1", "client": "bteam",
        "run_id": "up-run-step5", "verdict": "held",
        "reviewer": "Kamen Kamenov",
    }
    state = {
        "run_id": "up-run-step5",
        "context": {
            "inputs": {"stop_after_phase": "strategy-approach-gate", "step6_writer_call_limit": 60},
            "up": {"cd_s_002": {"step5_review_hold": hold}},
        },
        "phases": {"insight-gate": {
            "status": "completed", "ledger": {"status": "held"},
        }},
    }
    state_bytes = (json.dumps(state, sort_keys=True, indent=2) + "\n").encode()
    (copy / "state" / "up-run-step5.json").write_bytes(state_bytes)
    hold_sha = hashlib.sha256(
        (json.dumps(hold, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":")) + "\n").encode()
    ).hexdigest()
    manifest = {
        "schema": "step6-clean-copy/v1", "client": "bteam",
        "source_run_id": "up-run-step5", "first_phase": "compose-strategy-one-pager",
        "stop_after_phase": "strategy-approach-gate", "writer_call_limit": 60,
        "source_admission": "held", "source_review_hold_sha256": hold_sha,
        "clean_state_sha256": hashlib.sha256(state_bytes).hexdigest(),
    }
    (copy / "record" / "step6-clean-copy.json").write_text(json.dumps(manifest))
    answers = _step11_resume_answers()
    answers.update({
        "client": "bteam", "source_run_id": "up-run-step5",
        "first_unfinished_phase": "compose-strategy-one-pager",
        "step6_clean_task_dir": str(copy),
        "step11_writer_input_path": None,
        "step11_writer_call_budget_path": None,
        "step11_writer_call_limit": None,
    })
    roots = {"united-partners": str(repository)}
    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation", answers,
        artifact_paths={}, repository_roots=roots,
    )
    assert prepared["argv"][-2:] == ["--task-dir", str(copy)]
    assert prepared["environment"]["UP_HARNESS_GOOGLE_DRIVE_ROOT"] == str(copy / "drive-staging")
    assert prepared["environment"]["UP_HARNESS_GOOGLE_DRIVE_ACCESS_TOKEN"] == ""
    repaired = {
        "run_id": "up-run-step6-repaired", "parent_run_id": "up-run-step5",
        "status": "blocked",
        "phases": {
            "compose-strategy-one-pager": {"status": "completed"},
            "insight-gate": {"status": "blocked"},
        },
    }
    (copy / "state" / "up-run-step6-repaired.json").write_text(json.dumps(repaired))
    answers.update({
        "source_run_id": "up-run-step6-repaired",
        "first_unfinished_phase": "compose-strategy-one-pager",
        "reopen_completed_phase": True,
    })
    prepared = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation", answers,
        artifact_paths={}, repository_roots=roots,
    )
    assert "--rerun-completed" in prepared["argv"]
    assert prepared["argv"][-2:] == ["--task-dir", str(copy)]
    repaired["phases"]["compose-strategy-one-pager"]["status"] = "failed"
    (copy / "state" / "up-run-step6-repaired.json").write_text(json.dumps(repaired))
    answers["reopen_completed_phase"] = False
    continued = sequence_intake_adapters.prepare(
        "workflow-resume-from-phase-live-confirmation", answers,
        artifact_paths={}, repository_roots=roots,
    )
    assert "--rerun-completed" not in continued["argv"]
    assert continued["environment"]["UP_HARNESS_AGENT_MAX_ATTEMPTS"] == "1"
    manifest["source_review_hold_sha256"] = "0" * 64
    (copy / "record" / "step6-clean-copy.json").write_text(json.dumps(manifest))
    with pytest.raises(sequence_intake_adapters.AdapterError, match="step6-clean-copy-manifest-mismatch"):
        sequence_intake_adapters.prepare(
            "workflow-resume-from-phase-live-confirmation", answers,
            artifact_paths={}, repository_roots=roots,
        )
