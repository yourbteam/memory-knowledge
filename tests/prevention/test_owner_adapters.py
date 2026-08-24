from __future__ import annotations

import importlib
import json
import uuid
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from scripts import (
    prevention_adapters, prevention_contract, prevention_contract_materializer,
    prevention_registry,
    sequence_candidate_contract,
)


def _parameter(
    name: str, value: object, *, tag: prevention_contract.ParameterTag | None = None,
) -> prevention_contract.TypedParameter:
    if tag is not None:
        selected_tag = tag
    elif isinstance(value, bool):
        selected_tag = prevention_contract.ParameterTag.BOOLEAN
    elif isinstance(value, int):
        selected_tag = prevention_contract.ParameterTag.INTEGER
    else:
        selected_tag = prevention_contract.ParameterTag.STRING
    return prevention_contract.TypedParameter(
        name=name, value=prevention_contract.ParameterValue(tag=selected_tag, value=value)
    )


def _intent(sequence_id: str, values: list[prevention_contract.TypedParameter]):
    return prevention_contract.ActionIntent(
        intent_id=str(uuid.uuid4()), task_id="adapter-test", run_id=str(uuid.uuid4()),
        requested_sequence_id=sequence_id, requested_implementation_id="a" * 64,
        compatibility_key="b" * 64, action_class=prevention_contract.ActionClass.BASH,
        parameters=tuple(values),
    )


class _BindingProvider:
    def resolve(self, request):
        if request.consumable:
            kind = prevention_contract.BindingKind.APPROVAL
        elif request.parameter_type == "SECRET_HANDLE":
            kind = prevention_contract.BindingKind.SECRET
        elif request.parameter_type == "RESOURCE_KEY":
            kind = prevention_contract.BindingKind.RESOURCE
        else:
            kind = prevention_contract.BindingKind.REPOSITORY
        execution_value = (
            str(Path(__file__).resolve().parents[2])
            if kind == prevention_contract.BindingKind.REPOSITORY
            and request.parameter_name == "repository_key"
            else f"resolved-{request.key_or_resource_id}"
        )
        fingerprint = prevention_contract.sha256_bytes(
            prevention_contract.canonical_bytes(execution_value)
        )
        return prevention_adapters.BindingResolution(
            receipt=prevention_contract.BindingReceipt(
                receipt_id=prevention_contract.sha256_bytes(
                    prevention_contract.canonical_bytes({
                        "scope": request.expected_scope_sha256,
                        "key": request.key_or_resource_id,
                    })
                ),
                binding_kind=kind, provider_id=request.provider_id,
                key_or_resource_id=request.key_or_resource_id,
                version_id=request.version_id or "v1",
                scope_sha256=request.expected_scope_sha256,
                value_fingerprint_sha256=fingerprint,
                consumable=request.consumable,
            ),
            execution_value=execution_value,
        )


def _path(name, value):
    return _parameter(name, value, tag=prevention_contract.ParameterTag.PATH)


def _enum(name, value):
    return _parameter(name, value, tag=prevention_contract.ParameterTag.ENUM)


def _resource(name, value):
    return _parameter(name, value, tag=prevention_contract.ParameterTag.RESOURCE_KEY)


def _uuid(name):
    return _parameter(name, str(uuid.uuid4()), tag=prevention_contract.ParameterTag.UUID)


def _cases(tmp_path: Path):
    candidate_context = {
        "intended_outcome": "Run the test sequence.",
        "repeatability_reason": "The sequence recurs.",
        "repeatability_evidence_ids": ["event-1"],
        "required_inputs": ["test input"],
        "dependencies": [{"repository_key": "memory-knowledge", "path": "scripts/run_pytest.sh"}],
        "failure_handling": [{"fingerprint": "a" * 64, "symptom": "failed", "response": "stop"}],
        "verification_contract": {"quality": "same-path", "expected_outcome": "passed", "success_evidence": "tests pass"},
        "effect_class": "external-reversible",
        "environment_annotations": [], "semantic_flag_annotations": [],
        "volatility_annotations": [],
    }
    candidate_steps = [{
        "step_ordinal": 0, "step_id": "test", "argv": ["scripts/run_pytest.sh"],
        "command_source": "script",
        "source_ref": {"repository_key": "memory-knowledge", "path": "scripts/run_pytest.sh"},
        "operation_kind": "single-test",
    }]
    candidate_identity, candidate_fingerprint = sequence_candidate_contract.build_candidate_identity(
        candidate_context, candidate_steps
    )
    (tmp_path / "spec.json").write_text(json.dumps({
        "schema_version": 1, "task_id": "task-1", "operation_kind": "workflow-drive",
        "date": "2026-07-18", "sequence_name": "test-sequence",
        "outcome": "Run tests", "why_repeatable": "Tests recur",
        "steps": [{"step": "test", "command": "scripts/run_pytest.sh", "result": "passed", "note": "same path"}],
        "dependencies": [],
        "candidate_identity": candidate_identity,
        "candidate_fingerprint": candidate_fingerprint,
        "observer_provenance": {
            "decision_id": str(uuid.uuid4()), "observer_version": 1, "rule_version": 1,
        },
    }), encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        '["scripts/scoped_git_publish.py"]', encoding="utf-8"
    )
    (tmp_path / "state.json").write_text("{}", encoding="utf-8")
    (tmp_path / "child.json").write_text(json.dumps({
        "child_owner_sequence_id": "owner", "child_contract_sha256": "a" * 64,
        "child_intent_id": str(uuid.uuid4()), "child_parameters": [],
        "guard_receipt_id": str(uuid.uuid4()),
    }), encoding="utf-8")
    (tmp_path / "request.json").write_text(json.dumps({
        "schema_version": 2, "request_id": str(uuid.uuid4()),
        "state": "runtime-temp/state.json", "initial_state_sha256": "a" * 64,
        "expected_final_status": "complete", "operations": [{"operation_id": str(uuid.uuid4()), "kind": "status"}],
    }), encoding="utf-8")
    secret = {"provider_id": "test-secret-provider", "key_id": "env", "version_id": "v1"}
    return {
        "local-workflow-orch-image": [_enum("command", "build"), _parameter("tag", "test")],
        "greenfield-full-drive": [
            _enum("mode", "start-from-spec"), _resource("repository_key", "repo"),
            _parameter("env_file", secret, tag=prevention_contract.ParameterTag.SECRET_HANDLE),
            _parameter("keyvault_name", "vault"), _enum("spec_root_key", "memory-knowledge"),
            _path("spec", "tests/prevention/test_owner_adapters.py"),
        ],
        "mawf-playbook-blocker-reentry": [
            _uuid("delegation_id"), _enum("mode", "resume"), _parameter("task_guid", "task-1"),
            _enum("workflow_name", "research-workflow"), _uuid("run_id"),
        ],
        "claude-auth-token-refresh": [
            _enum("command", "status"), _resource("container_key", "container"),
            _resource("vault_key", "vault"),
        ],
        "discovery-promotion-lifecycle": [
            _enum("command", "status"),
            _path("file", "2026-07-17-prevention-owner-runtime-five-defect-convergence.md"),
            _parameter("sequence_id", "candidate"),
        ],
        "commit-push-main": [
            _enum("mode", "dry-run"), _resource("repository_key", "memory-knowledge"),
            _parameter("branch", "main"), _resource("remote_key", "origin"),
            _path("manifest_file", "runtime-temp/manifest.json"),
            _uuid("authorization_receipt_id"),
        ],
        "discovery-bootstrap": [
            _enum("command", "start"), _path("spec_file", "runtime-temp/spec.json"),
        ],
        "discovery-candidate-reconciliation": [
            _enum("command", "audit"), _path("output", "runtime-temp/audit.json"),
        ],
        "convergence-checkpoint-run": [
            _path("state", "runtime-temp/state.json"), _parameter("approval_id", "approval-1"),
            _path("child_intent_file", "runtime-temp/child.json"),
        ],
        "convergence-state-review-cycle": [
            _enum("command", "apply"), _path("request_file", "runtime-temp/request.json"),
        ],
    }


def test_all_manifest_handlers_resolve_and_only_researched_available_owners_build_argv(tmp_path: Path):
    rows, _ = prevention_registry.load_typed_registry()
    cases = _cases(tmp_path)
    assert len(rows) == 25
    for row in rows:
        module_name, symbol = row["handler"].split(":", 1)
        handler = getattr(importlib.import_module(f"scripts.{module_name}"), symbol)
        assert callable(handler)
        if row["availability_policy"] == "AVAILABLE":
            owner = deepcopy(row)
            owner["executable_contract"]["trusted_roots"]["runtime-temp"] = str(tmp_path)
            plan = prevention_adapters.build_invocation(
                _intent(row["sequence_id"], cases[row["sequence_id"]]), owner,
                binding_provider=prevention_adapters.TrustedBindingProvider(
                    repository_roots={"memory-knowledge": str(Path(__file__).resolve().parents[2])},
                    external=_BindingProvider(),
                ),
            )
            assert plan.sequence_id == row["sequence_id"]
            assert plan.argv[0] in {"python3", "bash"}
            assert all(isinstance(token, str) and token for token in plan.argv)
        else:
            with pytest.raises(prevention_adapters.AdapterError, match="evidence-unavailable"):
                handler(None, row)


def test_effect_context_is_bound_only_for_source_supported_mutations(tmp_path: Path):
    rows, _ = prevention_registry.load_typed_registry()
    local = deepcopy(next(
        row for row in rows if row["sequence_id"] == "local-workflow-orch-image"
    ))
    local["executable_contract"]["trusted_roots"]["runtime-temp"] = str(tmp_path)
    effect_id = "e" * 64

    build_plan = prevention_adapters.build_invocation(
        _intent("local-workflow-orch-image", [
            _enum("command", "build"), _parameter("tag", "test"),
        ]),
        local,
    )
    bound_build = prevention_adapters.bind_effect_context(build_plan, effect_id)
    assert bound_build.argv[-2:] == ("--prevention-effect-id", effect_id)
    assert bound_build.effect_context_binding == "ARGV_EFFECT_ID"

    health_plan = prevention_adapters.build_invocation(
        _intent("local-workflow-orch-image", [
            _enum("command", "health"), _parameter("port", 18082),
        ]),
        local,
    )
    assert prevention_adapters.bind_effect_context(
        health_plan, effect_id
    ) == health_plan

    with pytest.raises(prevention_adapters.AdapterError, match="effect-context-id-invalid"):
        prevention_adapters.bind_effect_context(build_plan, "caller-effect")


def test_preparation_context_binds_every_executable_owner_source_invocation():
    effect_id = "e" * 64
    preparation_sha256 = "f" * 64
    for owner_id in prevention_contract_materializer.OWNER_IDS:
        plan = prevention_adapters.InvocationPlan(
            sequence_id=owner_id,
            argv=("python3", "owner.py", "status"),
            owner_contract_sha256="a" * 64,
            implementation_source_sha256="b" * 64,
            parameter_schema_sha256="c" * 64,
            resolved_parameters={},
            root_bindings={},
            binding_receipts={},
        )
        bound = prevention_adapters.bind_preparation_context(
            prevention_adapters.bind_effect_context(plan, effect_id),
            effect_id,
            preparation_sha256,
        )
        assert bound.effect_context_binding == "ARGV_EFFECT_ID"
        assert bound.preparation_context_binding == "ARGV_PREPARATION_SHA256"
        assert bound.argv[-2:] == (
            "--prevention-preparation-sha256", preparation_sha256,
        )
        assert effect_id in bound.argv


def test_adapter_rejects_unknown_raw_parameter_and_non_path_payload_before_argv():
    rows, _ = prevention_registry.load_typed_registry()
    owner = next(row for row in rows if row["sequence_id"] == "discovery-bootstrap")
    with pytest.raises(prevention_adapters.AdapterError, match="missing-required-parameter"):
        prevention_adapters.discovery_bootstrap(
            _intent("discovery-bootstrap", [_parameter("spec", '{"raw":true}')]), owner
        )
    with pytest.raises(prevention_adapters.AdapterError, match="unknown-parameter"):
        prevention_adapters.discovery_bootstrap(
            _intent("discovery-bootstrap", [
                _enum("command", "start"), _parameter("argv", "rm -rf"),
            ]), owner
        )


def test_provider_bindings_fail_closed_on_missing_mismatched_or_expired_receipt():
    owner = next(
        row for row in prevention_registry.load_typed_registry()[0]
        if row["sequence_id"] == "claude-auth-token-refresh"
    )
    requested = _intent("claude-auth-token-refresh", [
        _enum("command", "status"), _resource("container_key", "container"),
        _resource("vault_key", "vault"),
    ])
    with pytest.raises(prevention_adapters.AdapterError, match="binding-provider-required"):
        prevention_adapters.build_invocation(requested, owner)

    class BadProvider(_BindingProvider):
        def resolve(self, request):
            result = super().resolve(request)
            return replace(
                result,
                receipt=replace(result.receipt, scope_sha256="f" * 64),
            )

    with pytest.raises(prevention_adapters.AdapterError, match="identity-mismatch"):
        prevention_adapters.build_invocation(
            requested, owner, binding_provider=BadProvider()
        )

    class ExpiredProvider(_BindingProvider):
        def resolve(self, request):
            result = super().resolve(request)
            return replace(
                result,
                receipt=replace(result.receipt, expires_at_utc="2000-01-01T00:00:00Z"),
            )

    with pytest.raises(prevention_adapters.AdapterError, match="expired"):
        prevention_adapters.build_invocation(
            requested, owner, binding_provider=ExpiredProvider()
        )


def test_profile_scoped_derived_field_forbids_only_the_deriving_profile():
    owner = next(
        row for row in prevention_registry.load_typed_registry()[0]
        if row["sequence_id"] == "claude-auth-token-refresh"
    )
    provider = _BindingProvider()
    verified = prevention_adapters.build_invocation(
        _intent("claude-auth-token-refresh", [
            _enum("command", "verify"),
            _parameter(
                "verify_targets", ["host"],
                tag=prevention_contract.ParameterTag.SET,
            ),
        ]),
        owner,
        binding_provider=provider,
    )
    assert verified.resolved_parameters["verify_targets"] == ["host"]

    with pytest.raises(
        prevention_adapters.AdapterError, match="caller-override-forbidden:verify_targets"
    ):
        prevention_adapters.build_invocation(
            _intent("claude-auth-token-refresh", [
                _enum("command", "all"),
                _parameter(
                    "verify_targets", ["host"],
                    tag=prevention_contract.ParameterTag.SET,
                ),
                _resource("container_key", "container"),
                _resource("vault_key", "vault"),
                _resource("deployment_key", "deployment"),
                _parameter(
                    "credential_source",
                    {"tag": "runtime_temp_file", "payload": "credential.json"},
                    tag=prevention_contract.ParameterTag.TAGGED_UNION,
                ),
            ]),
            owner,
            binding_provider=provider,
        )


def test_path_binding_rejects_ambiguous_root_and_symlink(tmp_path: Path):
    rows, _ = prevention_registry.load_typed_registry()
    reconciliation = deepcopy(next(
        row for row in rows if row["sequence_id"] == "discovery-candidate-reconciliation"
    ))
    reconciliation["executable_contract"]["trusted_roots"]["runtime-temp"] = str(tmp_path)
    with pytest.raises(prevention_adapters.AdapterError, match="trusted-root-key-required"):
        prevention_adapters.build_invocation(
            _intent("discovery-candidate-reconciliation", [
                _enum("command", "audit"), _path("output", "audit.json"),
            ]), reconciliation,
        )

    target = tmp_path / "port.txt"
    target.write_text("18082", encoding="utf-8")
    (tmp_path / "port-link").symlink_to(target)
    local = deepcopy(next(
        row for row in rows if row["sequence_id"] == "local-workflow-orch-image"
    ))
    local["executable_contract"]["trusted_roots"]["runtime-temp"] = str(tmp_path)
    with pytest.raises(prevention_adapters.AdapterError, match="symlink-forbidden"):
        prevention_adapters.build_invocation(
            _intent("local-workflow-orch-image", [
                _enum("command", "health"), _path("port_file", "port-link"),
            ]), local,
        )


def test_secret_handle_identity_is_persistable_but_provider_value_is_not():
    owner = next(
        row for row in prevention_registry.load_typed_registry()[0]
        if row["sequence_id"] == "greenfield-full-drive"
    )
    handle = {"provider_id": "secret-provider", "key_id": "env", "version_id": "v1"}
    plan = prevention_adapters.build_invocation(
        _intent("greenfield-full-drive", [
            _enum("mode", "start-from-spec"), _resource("repository_key", "repo"),
            _parameter("env_file", handle, tag=prevention_contract.ParameterTag.SECRET_HANDLE),
            _parameter("keyvault_name", "vault"), _enum("spec_root_key", "memory-knowledge"),
            _path("spec", "tests/prevention/test_owner_adapters.py"),
        ]), owner, binding_provider=_BindingProvider(),
    )
    assert plan.resolved_parameters["env_file"] == handle
    assert "resolved-env" in plan.argv
    assert "resolved-env" not in json.dumps(plan.resolved_parameters, sort_keys=True)


def test_greenfield_validate_fresh_is_a_checkpoint_resume_with_fixed_flag():
    owner = next(
        row for row in prevention_registry.load_typed_registry()[0]
        if row["sequence_id"] == "greenfield-full-drive"
    )
    plan = prevention_adapters.build_invocation(
        _intent("greenfield-full-drive", [
            _enum("mode", "validate-fresh"),
            _resource("repository_key", "repo"),
            _parameter(
                "env_file",
                {"provider_id": "secret-provider", "key_id": "env", "version_id": "v1"},
                tag=prevention_contract.ParameterTag.SECRET_HANDLE,
            ),
            _parameter("keyvault_name", "vault"),
            _parameter("decomposition_task_id", "task-1"),
            _parameter("decomposition_run_id", "run-1"),
            _uuid("program_drive_id"),
            _parameter(
                "expected_spec_hash",
                "a" * 64,
                tag=prevention_contract.ParameterTag.SHA256,
            ),
        ]),
        owner,
        binding_provider=_BindingProvider(),
    )
    assert "--drive-dag" in plan.argv
    assert "--resume-from-checkpoint" in plan.argv
    assert "--validate-fresh" in plan.argv
    assert "--create-new-program" not in plan.argv


def test_nested_schema_paths_reject_absolute_traversal_and_symlink_inputs(
    tmp_path: Path,
):
    regular = tmp_path / "input.json"
    regular.write_text("{}", encoding="utf-8")
    link = tmp_path / "input-link.json"
    link.symlink_to(regular)
    path_spec = {
        "type": "PATH",
        "trusted_roots": ["runtime-temp"],
        "mode": "READ_REGULAR_FILE",
    }
    roots = {"runtime-temp": str(tmp_path)}
    object_spec = {
        "type": "EXACT_OBJECT",
        "fields": {"nested_path": path_spec},
    }
    list_spec = {"type": "LIST", "item_schema": path_spec}

    with pytest.raises(prevention_adapters.AdapterError, match="field-path-invalid"):
        prevention_adapters._validate_json_value(
            "request", {"nested_path": str(regular)}, object_spec, roots
        )
    with pytest.raises(prevention_adapters.AdapterError, match="field-path-invalid"):
        prevention_adapters._validate_json_value(
            "request", {"nested_path": "../input.json"}, object_spec, roots
        )
    with pytest.raises(prevention_adapters.AdapterError, match="symlink-forbidden"):
        prevention_adapters._validate_json_value(
            "paths", ["input-link.json"], list_spec, roots
        )


def test_remote_operator_path_is_bound_lexically_without_host_workspace_access():
    rows, _ = prevention_registry.load_typed_registry()
    owner = deepcopy(next(
        row for row in rows
        if row["sequence_id"] == "mawf-playbook-blocker-reentry"
    ))
    repo_spec = next(
        item["schema"]
        for item in owner["executable_contract"]["parameter_contract"]["parameters"]
        if item["name"] == "repo"
    )
    resolved, root_key = prevention_adapters._resolve_path(
        "repo", "acceptance-project", repo_spec,
        owner["executable_contract"]["trusted_roots"], {},
    )

    assert resolved == "/workspaces/acceptance-project"
    assert root_key == "container-workspaces"
    with pytest.raises(prevention_adapters.AdapterError, match="trusted-remote-path-invalid"):
        prevention_adapters._resolve_path(
            "repo", "../escape", repo_spec,
            owner["executable_contract"]["trusted_roots"], {},
        )


def test_commit_dry_run_adapter_does_not_invent_a_publish_message(tmp_path: Path):
    rows, _ = prevention_registry.load_typed_registry()
    owner = deepcopy(next(
        row for row in rows if row["sequence_id"] == "commit-push-main"
    ))
    owner["executable_contract"]["trusted_roots"]["runtime-temp"] = str(tmp_path)
    manifest = tmp_path / "manifest.json"
    manifest.write_text('["scripts/scoped_git_publish.py"]', encoding="utf-8")
    parameters = [
        _enum("mode", "dry-run"),
        _resource("repository_key", "memory-knowledge"),
        _parameter("branch", "main"),
        _resource("remote_key", "origin"),
        _path("manifest_file", "runtime-temp/manifest.json"),
    ]

    plan = prevention_adapters.build_invocation(
        _intent("commit-push-main", parameters), owner,
        binding_provider=prevention_adapters.TrustedBindingProvider(
            repository_roots={
                "memory-knowledge": str(Path(__file__).resolve().parents[2]),
            },
            external=_BindingProvider(),
        ),
    )

    assert "--message" not in plan.argv
    assert "--execute" not in plan.argv
    assert plan.argv[plan.argv.index("--repository-key") + 1] == "memory-knowledge"
    assert plan.argv[plan.argv.index("--repo") + 1] == str(
        Path(__file__).resolve().parents[2]
    )


def test_repository_provider_root_binds_every_manifest_member_to_dynamic_worktree(
    tmp_path: Path,
):
    rows, _ = prevention_registry.load_typed_registry()
    owner = deepcopy(next(
        row for row in rows if row["sequence_id"] == "commit-push-main"
    ))
    worktree = tmp_path / "alternate-worktree"
    (worktree / "src").mkdir(parents=True)
    (worktree / "src" / "one.py").write_text("one\n", encoding="utf-8")
    (worktree / "src" / "two.py").write_text("two\n", encoding="utf-8")

    class DynamicRootProvider(_BindingProvider):
        def resolve(self, request):
            resolution = super().resolve(request)
            if request.parameter_name != "repository_key":
                return resolution
            execution_value = str(worktree.resolve())
            return replace(
                resolution,
                receipt=replace(
                    resolution.receipt,
                    value_fingerprint_sha256=prevention_contract.sha256_bytes(
                        prevention_contract.canonical_bytes(execution_value)
                    ),
                ),
                execution_value=execution_value,
            )

    parameters = [
        _enum("mode", "dry-run"), _resource("repository_key", "alternate"),
        _parameter("branch", "main"), _resource("remote_key", "origin"),
        _parameter(
            "manifest", ["src/one.py", "src/two.py"],
            tag=prevention_contract.ParameterTag.SET,
        ),
    ]
    resolved = prevention_adapters.validate_and_resolve_parameters(
        _intent("commit-push-main", parameters), owner,
        binding_provider=DynamicRootProvider(),
    )

    assert resolved.argv_values["manifest"] == [
        str((worktree / "src" / "one.py").resolve()),
        str((worktree / "src" / "two.py").resolve()),
    ]
    assert resolved.root_bindings == {
        "manifest[0]": "alternate", "manifest[1]": "alternate",
    }

    escaped = parameters[:-1] + [_parameter(
        "manifest", ["../escape"], tag=prevention_contract.ParameterTag.SET,
    )]
    with pytest.raises(prevention_adapters.AdapterError, match="trusted-root-resolution-ambiguous"):
        prevention_adapters.validate_and_resolve_parameters(
            _intent("commit-push-main", escaped), owner,
            binding_provider=DynamicRootProvider(),
        )

    outside = tmp_path / "outside.py"
    outside.write_text("outside\n", encoding="utf-8")
    (worktree / "src" / "link.py").symlink_to(outside)
    symlinked = parameters[:-1] + [_parameter(
        "manifest", ["src/link.py"], tag=prevention_contract.ParameterTag.SET,
    )]
    with pytest.raises(prevention_adapters.AdapterError, match="trusted-path-symlink"):
        prevention_adapters.validate_and_resolve_parameters(
            _intent("commit-push-main", symlinked), owner,
            binding_provider=DynamicRootProvider(),
        )


def test_candidate_reconciliation_renders_global_root_before_subcommand(tmp_path: Path):
    rows, _ = prevention_registry.load_typed_registry()
    owner = deepcopy(next(
        row for row in rows
        if row["sequence_id"] == "discovery-candidate-reconciliation"
    ))
    owner["executable_contract"]["trusted_roots"]["runtime-temp"] = str(tmp_path)
    plan = prevention_adapters.build_invocation(
        _intent("discovery-candidate-reconciliation", [
            _enum("command", "audit"), _path("output", "runtime-temp/audit.json"),
        ]), owner,
    )

    assert plan.argv[2:5] == (
        "--root", str(Path(__file__).resolve().parents[2]), "audit",
    )
    assert "--max-attempts" not in plan.argv
