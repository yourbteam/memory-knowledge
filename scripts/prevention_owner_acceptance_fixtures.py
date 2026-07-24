#!/usr/bin/env python3
"""Contract-derived typed fixtures for the closed owner acceptance matrix."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any, Mapping

try:
    from scripts import prevention_adapters, sequence_candidate_contract, work_memory
    from scripts.directive_guard import write_directive_read_state
    from scripts.prevention_contract import (
        ActionClass, ActionIntent, BindingKind, BindingReceipt, ParameterTag,
        ParameterValue, TypedParameter, canonical_bytes, sha256_bytes,
    )
except ModuleNotFoundError:  # direct script execution
    import prevention_adapters
    import sequence_candidate_contract
    import work_memory
    from directive_guard import write_directive_read_state
    from prevention_contract import (
        ActionClass, ActionIntent, BindingKind, BindingReceipt, ParameterTag,
        ParameterValue, TypedParameter, canonical_bytes, sha256_bytes,
    )


ACCEPTANCE_THREAD_ID = "00000000-0000-4000-8000-000000000001"


class AcceptanceBindingProvider:
    """Finite non-secret provider used only by deterministic contract acceptance."""

    def __init__(self, root: Path):
        self.root = root
        self.secret_file = root / "acceptance.env"
        self.secret_file.write_text("ACCEPTANCE_FAKE_EDGE=1\n", encoding="utf-8")

    def resolve(self, request):
        if request.consumable:
            kind = BindingKind.APPROVAL
        elif request.parameter_type == "SECRET_HANDLE":
            kind = BindingKind.SECRET
        elif request.parameter_type == "RESOURCE_KEY":
            kind = BindingKind.RESOURCE
        else:
            kind = BindingKind.REPOSITORY
        if request.parameter_type == "SECRET_HANDLE":
            if request.owner_sequence_id == "claude-auth-token-refresh":
                self.secret_file.write_bytes(canonical_bytes({
                    "claudeAiOauth": {
                        "accessToken": "acceptance-access-token",
                        "refreshToken": "acceptance-refresh-token",
                        "expiresAt": 4102444800000,
                        "scopes": ["user:inference"],
                        "subscriptionType": "acceptance",
                    },
                }))
            execution_value = str(self.secret_file)
        elif request.parameter_name == "repository_key":
            execution_value = (
                "/workspaces/acceptance-repository"
                if request.owner_sequence_id == "greenfield-full-drive"
                else str((self.root / "git-repository").resolve())
            )
        elif request.parameter_name == "remote_key":
            execution_value = "origin"
        elif (
            request.owner_sequence_id == "claude-auth-token-refresh"
            and request.parameter_name == "deployment_key"
        ):
            execution_value = "https://acceptance.invalid"
        else:
            execution_value = f"acceptance-{request.key_or_resource_id}"
        fingerprint = sha256_bytes(canonical_bytes(execution_value))
        return prevention_adapters.BindingResolution(
            receipt=BindingReceipt(
                receipt_id=sha256_bytes(canonical_bytes({
                    "scope": request.expected_scope_sha256,
                    "key": request.key_or_resource_id,
                    "provider": request.provider_id,
                })),
                binding_kind=kind,
                provider_id=request.provider_id,
                key_or_resource_id=request.key_or_resource_id,
                version_id=request.version_id or "acceptance-v1",
                scope_sha256=request.expected_scope_sha256,
                value_fingerprint_sha256=fingerprint,
                consumable=request.consumable,
            ),
            execution_value=execution_value,
        )


def _owner_id(owner: Mapping[str, Any]) -> str:
    value = owner.get("sequence_id", owner.get("owner_sequence_id"))
    if not isinstance(value, str) or not value:
        raise ValueError("owner-acceptance-owner-id-invalid")
    return value


def _ensure_git_repository(root: Path) -> str:
    repository = root / "git-repository"
    remote = root / "git-remote.git"
    source = repository / "scripts/prevention_owner_acceptance.py"
    if not (repository / ".git").is_dir():
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("# owner acceptance base\n", encoding="utf-8")
        subprocess.run(["git", "init", "-b", "main", str(repository)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repository), "config", "user.email", "acceptance@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(repository), "config", "user.name", "Owner Acceptance"], check=True)
        subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repository), "remote", "add", "origin", str(remote)], check=True)
        subprocess.run(["git", "-C", str(repository), "add", source.relative_to(repository).as_posix()], check=True)
        subprocess.run(["git", "-C", str(repository), "commit", "-m", "owner acceptance base"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repository), "push", "-u", "origin", "main"], check=True, capture_output=True)
        source.write_text(source.read_text(encoding="utf-8") + "# owner acceptance change\n", encoding="utf-8")
    return subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True, text=True, capture_output=True,
    ).stdout.strip()


def ensure_memory_mirror(root: Path) -> Path:
    """Create the isolated local-state edge used by real memory source scripts."""
    mirror = root / "memory-knowledge"
    if mirror.is_dir():
        return mirror
    source_root = Path(__file__).resolve().parents[1]
    (mirror / "scripts").mkdir(parents=True)
    (mirror / "working-agreement").mkdir(parents=True)
    (mirror / "operations/sequences/discovery").mkdir(parents=True)
    (mirror / "operations/work-memory").mkdir(parents=True)
    (mirror / "operations/blockers").mkdir(parents=True)
    acceptance_discovery = (
        mirror / "operations/sequences/discovery/owner-acceptance-discovery.md"
    )
    acceptance_discovery.write_text("""# Sequence Discovery Log: owner acceptance

DiscoveryId: discovery-owner-acceptance
Status: discovery
CreatedAtUtc: 2026-07-19T00:00:00Z
RegisteredSequenceMatch: none

## Intended Outcome

Exercise the real discovery promotion lifecycle in an isolated repository.

## Why This Looks Repeatable

The owner acceptance suite repeats this lifecycle proof.

## Required Inputs, Auth, Or Environment

- isolated memory repository

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| verify-automation | python3 scripts/work_memory.py --help | command exits zero | exact source path |

## Failure Handling

Stop on the first rejected lifecycle transition.

## Verified Path

- The exact guarded command exits zero.

## Promotion Readiness

- [x] Commands are stable enough to script or document.
- [x] Required inputs are known.
- [x] Failure handling is known.
- [x] Verification evidence is known.
- [x] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
""", encoding="utf-8")
    (acceptance_discovery.with_suffix(".dependencies.json")).write_bytes(
        canonical_bytes({
            "schema_version": 1,
            "lineage_id": "discovery-owner-acceptance",
            "dependencies": [{
                "kind": "file",
                "repository_key": "memory-knowledge",
                "path_or_sequence_id": "scripts/work_memory.py",
            }],
        })
    )
    shutil.copy2(
        source_root / "working-agreement/DIRECTIVES.md",
        mirror / "working-agreement/DIRECTIVES.md",
    )
    shutil.copy2(
        source_root / "operations/sequences/SEQUENCES.md",
        mirror / "operations/sequences/SEQUENCES.md",
    )
    discovery_source = source_root / "operations/sequences/discovery"
    discovery_target = mirror / "operations/sequences/discovery"
    policy_source = discovery_source / "reconciliation-policy.json"
    policy = json.loads(policy_source.read_text(encoding="utf-8"))
    for row in policy["candidates"]:
        relative = Path(row["path"])
        shutil.copy2(source_root / relative, mirror / relative)
    shutil.copy2(
        policy_source,
        discovery_target / "reconciliation-policy.json",
    )
    for sequence_id in (
        "discovery-candidate-reconciliation",
        "discovery-promotion-lifecycle",
    ):
        shutil.copytree(
            source_root / "operations/sequences" / sequence_id,
            mirror / "operations/sequences" / sequence_id,
            dirs_exist_ok=True,
        )
        document = source_root / "operations/sequences" / sequence_id / "sequence.md"
        entries, _, _ = work_memory.resolve_bundle(
            mode="registered", subject_id=sequence_id, document=document,
            manifest=document.with_name("dependencies.json"),
            repo_roots_file=None, include_bootstrap_trust_anchors=True,
        )
        for entry in entries:
            if entry["repository_key"] != "memory-knowledge":
                continue
            relative = Path(entry["path"])
            target = mirror / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_root / relative, target)
    lifecycle_discovery = (
        source_root / "operations/sequences/discovery/"
        "2026-07-16-legacy-discovery-recovery-v1.md"
    )
    lifecycle_manifest = lifecycle_discovery.with_suffix(".dependencies.json")
    for source in (lifecycle_discovery, lifecycle_manifest):
        target = mirror / source.relative_to(source_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    lifecycle_entries, _, _ = work_memory.resolve_bundle(
        mode="discovery",
        subject_id="discovery-0f54a98b-4b75-536b-b8d6-6b2d8c8ab98e",
        document=lifecycle_discovery,
        manifest=lifecycle_manifest,
        repo_roots_file=None,
        include_bootstrap_trust_anchors=True,
    )
    for entry in lifecycle_entries:
        if entry["repository_key"] != "memory-knowledge":
            continue
        relative = Path(entry["path"])
        target = mirror / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_root / relative, target)
    owner_root = mirror / "Tasks/prevention-system-completion"
    owner_root.mkdir(parents=True, exist_ok=True)
    for name in (
        "owner-migration-manifest.json",
        "owner-descriptors.json",
        "owner-contracts.json",
        "owner-executable-contracts.json",
    ):
        shutil.copy2(
            source_root / "Tasks/prevention-system-completion" / name,
            owner_root / name,
        )
    shutil.copytree(
        source_root / "Tasks/prevention-system-completion/owner-contract-proposals",
        owner_root / "owner-contract-proposals",
        dirs_exist_ok=True,
    )
    (mirror / "operations/work-memory/events.jsonl").write_text("", encoding="utf-8")
    (mirror / "operations/blockers/BLOCKERS.md").write_text(
        "# Blocker Catalog\n", encoding="utf-8"
    )
    (mirror / "operations/sequences/discovery/ACTIVE.md").write_text(
        "# Generated active index\n", encoding="utf-8"
    )
    (mirror / "scripts/prevention_owner_acceptance.py").write_bytes(
        (source_root / "scripts/prevention_owner_acceptance.py").read_bytes()
    )
    for relative in work_memory.BOOTSTRAP_TRUST_ANCHORS:
        target = mirror / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        source = source_root / relative
        if source.is_file():
            target.write_bytes(source.read_bytes())
        elif not target.exists():
            target.write_text(f"# acceptance trust anchor: {relative}\n", encoding="utf-8")
    write_directive_read_state(
        directives_path=mirror / "working-agreement/DIRECTIVES.md",
        state_path=root / "directive-state.json",
        mode="owner-acceptance",
    )
    subprocess.run(
        ["git", "init", "-b", "main", str(mirror)],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(mirror), "config", "user.email", "acceptance@example.invalid"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(mirror), "config", "user.name", "Owner Acceptance"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(mirror), "add", "."], check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(mirror), "commit", "-m", "owner acceptance mirror"],
        check=True, capture_output=True,
    )
    return mirror


def _discovery_promotion_task_id(root: Path, profile: str) -> str:
    # Writer receipts are process-global under /private/tmp, while every acceptance
    # execution gets a new ephemeral repository. Bind the fixture task identity to
    # that repository so a receipt from an earlier execution cannot authorize or
    # block a later one.
    root_identity = sha256_bytes(str(root.resolve()).encode())[:16]
    return f"owner-acceptance-{profile}-{root_identity}"


def _seed_discovery_promotion_correction(root: Path, profile: str) -> None:
    mirror = ensure_memory_mirror(root)
    task_id = _discovery_promotion_task_id(root, profile)
    repository_registry = (
        mirror / "operations/sequences/discovery/"
        "2026-07-14-up-harness-cd-s-002-live-verification.repositories.json"
    )
    repository_registry.write_bytes(canonical_bytes({
        "memory-knowledge": str(mirror),
        "mcp-agents-workflow": "/Users/kamenkamenov/mcp-agents-workflow",
    }))
    discovery = (
        mirror / "operations/sequences/discovery/"
        "2026-07-16-legacy-discovery-recovery-v1.md"
    )
    # Versioned client identity: explicit codex kind with the legacy thread session
    # (schema-v1 writer). Ambient claude/session identity must not leak into acceptance.
    environment = {
        **os.environ,
        "MK_CLIENT_KIND": "codex",
        "CODEX_THREAD_ID": ACCEPTANCE_THREAD_ID,
    }
    environment.pop("MK_CLIENT_SESSION_ID", None)
    environment.pop("CLAUDE_SESSION_ID", None)

    def invoke(command: list[str]) -> dict[str, Any]:
        completed = subprocess.run(
            command, cwd=mirror, env=environment, text=True,
            capture_output=True, check=False,
        )
        stream = completed.stdout if completed.returncode == 0 else completed.stderr
        lines = [line for line in stream.splitlines() if line.strip()]
        if completed.returncode != 0 or not lines:
            raise RuntimeError(
                f"acceptance-correction-seed-failed:{command}:{completed.stderr}"
            )
        return json.loads(lines[-1])

    operation_kind = "workflow-drive" if profile == "correct-registered" else "other"
    invoke([
        "python3", "scripts/work_memory.py", "classify", "--task-id", task_id,
        "--operation-kind", operation_kind, "--repeatable", "yes",
        "--meaningful-steps", "8",
    ])
    if profile == "correct-registered":
        invoke([
            "python3", "scripts/work_memory.py", "select", "--task-id", task_id,
            "--sequence-id", "discovery-promotion-lifecycle",
            "--repo-roots-file", str(repository_registry),
        ])
        activate_source = [
            "--sequence-doc",
            str(mirror / "operations/sequences/discovery-promotion-lifecycle/sequence.md"),
        ]
        subject_id = "discovery-promotion-lifecycle"
    else:
        invoke([
            "python3", "scripts/work_memory.py", "select", "--task-id", task_id,
            "--discovery-log", str(discovery),
            "--repo-roots-file", str(repository_registry),
        ])
        activate_source = ["--discovery-log", str(discovery)]
        subject_id = "discovery-0f54a98b-4b75-536b-b8d6-6b2d8c8ab98e"
    invoke([
        "python3", "scripts/sequence_guard.py", "activate", "--task-id", task_id,
        "--root", str(mirror), *activate_source,
    ])
    started = invoke([
        "python3", "scripts/work_memory.py", "run-start", "--task-id", task_id,
    ])
    invoke([
        "python3", "scripts/blocker_catalog.py", "open",
        "--run-id", started["run_id"], "--subject-id", subject_id,
        "--step-id", "owner-acceptance-correction", "--surface", profile,
        "--error-signature", "owner-acceptance-correction",
        "--symptom", "The acceptance predecessor requires correction.",
        "--evidence", "The isolated predecessor contains one controlled drift.",
        "--impact", "Correction cannot complete until the drift is recorded.",
        "--boundary", "The selected bundle correction lifecycle.",
    ])
    changed = mirror / "tests/fixtures/captured_prevention_v4_trust_anchors.json"
    changed.write_bytes(changed.read_bytes() + b"\n")


def _runtime_temp_relative(root: Path, name: str) -> str:
    return f"owner-acceptance/{root.name}/{name}"


def _runtime_temp_path(root: Path, name: str) -> Path:
    return Path("/private/tmp") / _runtime_temp_relative(root, name)


def _ensure_convergence_state(root: Path) -> Path:
    mirror = ensure_memory_mirror(root)
    state = _runtime_temp_path(root, "state.json")
    requirements = _runtime_temp_path(root, "requirements.json")
    requirements.parent.mkdir(parents=True, exist_ok=True)
    requirements.write_bytes(canonical_bytes({"requirements": [{
        "id": "owner-acceptance",
        "text": "Prove typed checkpoint child composition.",
        "source": "owner-acceptance",
    }]}))
    helper = Path.home() / ".codex/skills/_shared/convergence_state.py"
    commands = (
        ["python3", str(helper), "init", str(state), "--source", str(requirements),
         "--objective", "Owner acceptance", "--requirements-file", str(requirements)],
        ["python3", str(helper), "init-baseline", str(state), "--repository", str(mirror),
         "--allowed-path", str(mirror / "operations/work-memory/events.jsonl"),
         "--allowed-path", str(mirror / "operations/blockers/BLOCKERS.md")],
        ["python3", str(helper), "grant-approval", str(state), "--id", "acceptance",
         "--kind", "autonomy", "--operations", '["accept-baseline"]',
         "--repository-roots", json.dumps([str(mirror)]),
         "--allowed-paths", json.dumps([
             str(mirror / "operations/work-memory/events.jsonl"),
             str(mirror / "operations/blockers/BLOCKERS.md"),
         ]), "--stage", "implementation", "--evidence", "owner acceptance fixture"],
    )
    for command in commands:
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        if completed.returncode:
            raise RuntimeError("owner-acceptance-convergence-state-failed:" + completed.stderr)
    return state


def _ensure_candidate_manifest(root: Path) -> None:
    mirror = ensure_memory_mirror(root)
    manifest = _runtime_temp_path(root, "manifest.json")
    manifest.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run([
        "python3",
        str(Path(__file__).resolve().parent / "discovery_candidate_reconciliation.py"),
        "--root", str(mirror), "audit", "--output", str(manifest),
    ], check=False, text=True, capture_output=True)
    if completed.returncode != 0:
        raise RuntimeError(
            "owner-acceptance-candidate-manifest-failed:" + completed.stderr
        )
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    for row in payload["candidates"]:
        row["disposition"] = (
            "remain-discovery"
            if row["suggested_disposition"] == "remain-discovery"
            else "quarantine"
        )
        row["decision_reason"] = (
            "Acceptance retains the source-observed active candidate."
            if row["disposition"] == "remain-discovery"
            else "Acceptance quarantines the candidate without invoking a child lifecycle."
        )
        row["target_sequence_id"] = None
        row["promotion"] = None
    payload["approval"] = {
        "approved": True, "approved_by": "owner-acceptance",
        "approved_at_utc": "2026-07-18T00:00:00Z",
    }
    manifest.write_bytes(canonical_bytes(payload))


def ensure_rolling_policy(root: Path) -> Path:
    mirror = ensure_memory_mirror(root)
    audit_path = _runtime_temp_path(root, "rolling-audit.json")
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run([
        "python3",
        str(Path(__file__).resolve().parent / "discovery_candidate_reconciliation.py"),
        "--root", str(mirror), "audit", "--output", str(audit_path),
    ], check=False, text=True, capture_output=True)
    if completed.returncode != 0:
        raise RuntimeError(
            "owner-acceptance-rolling-policy-failed:" + completed.stderr
        )
    payload = json.loads(audit_path.read_text(encoding="utf-8"))
    for row in payload["candidates"]:
        row["disposition"] = (
            "remain-discovery"
            if row["suggested_disposition"] == "remain-discovery"
            else "quarantine"
        )
    payload["approval"] = {
        "approved": True,
        "approved_by": "owner-acceptance",
        "approved_at_utc": "2026-07-18T00:00:00Z",
        "policy": "rolling-retain-only",
        "terminal_allowlist": [],
    }
    policy = mirror / "operations/sequences/discovery/reconciliation-policy.json"
    policy.write_bytes(canonical_bytes(payload))
    return policy


def _tag(type_name: str) -> ParameterTag:
    return {
        "BOOLEAN": ParameterTag.BOOLEAN,
        "INTEGER": ParameterTag.INTEGER,
        "NUMBER": ParameterTag.NUMBER,
        "PATH": ParameterTag.PATH,
        "REPOSITORY_RELATIVE_FILE_PATH": ParameterTag.PATH,
        "ENUM": ParameterTag.ENUM,
        "ENUM_FROM_REGISTRY": ParameterTag.RESOURCE_KEY,
        "ENUM_FROM_REPOSITORY": ParameterTag.RESOURCE_KEY,
        "REPOSITORY_KEY": ParameterTag.RESOURCE_KEY,
        "RESOURCE_KEY": ParameterTag.RESOURCE_KEY,
        "FULL_GIT_OBJECT_ID": ParameterTag.SHA1,
        "UUID": ParameterTag.UUID,
        "SHA256": ParameterTag.SHA256,
        "SET": ParameterTag.SET,
        "NONEMPTY_SET": ParameterTag.SET,
        "SET_ENUM": ParameterTag.SET,
        "SET_UUID": ParameterTag.SET,
        "NONEMPTY_LIST": ParameterTag.LIST,
        "EXACT_OBJECT": ParameterTag.EXACT_OBJECT,
        "TAGGED_UNION": ParameterTag.TAGGED_UNION,
        "SECRET_HANDLE": ParameterTag.SECRET_HANDLE,
        "STRING": ParameterTag.STRING,
        "GIT_BRANCH_NAME": ParameterTag.STRING,
    }[type_name]


def _candidate_spec(root: Path) -> dict[str, Any]:
    task_id = "owner-acceptance-" + sha256_bytes(str(root).encode("utf-8"))[:16]
    context = {
        "intended_outcome": "Exercise the real owner acceptance source.",
        "repeatability_reason": "The owner profile is part of the closed corpus.",
        "repeatability_evidence_ids": ["owner-acceptance-v1"],
        "required_inputs": ["typed acceptance fixture"],
        "dependencies": [{
            "repository_key": "memory-knowledge",
            "path": "scripts/prevention_owner_acceptance.py",
        }],
        "failure_handling": [{
            "fingerprint": "a" * 64, "symptom": "source rejected fixture",
            "response": "fail the acceptance case",
        }],
        "verification_contract": {
            "quality": "same-path", "expected_outcome": "passed",
            "success_evidence": "the real source returns its typed success envelope",
        },
        "effect_class": "idempotent-local", "environment_annotations": [],
        "semantic_flag_annotations": [], "volatility_annotations": [],
    }
    steps = [{
        "step_ordinal": 0, "step_id": "acceptance-source",
        "argv": ["python3", "scripts/prevention_owner_acceptance.py", "--check"],
        "command_source": "script",
        "source_ref": {
            "repository_key": "memory-knowledge",
            "path": "scripts/prevention_owner_acceptance.py",
        },
        "operation_kind": "single-test",
    }]
    identity, fingerprint = sequence_candidate_contract.build_candidate_identity(
        context, steps
    )
    return {
        "schema_version": 1,
        "task_id": task_id,
        "operation_kind": "single-test",
        "date": "2026-07-18",
        "sequence_name": "Owner Acceptance Source",
        "outcome": context["intended_outcome"],
        "why_repeatable": context["repeatability_reason"],
        "steps": [{
            "step": "acceptance-source",
            "command": "python3 scripts/prevention_owner_acceptance.py --check",
            "result": "passed", "note": "exact typed source path",
        }],
        "dependencies": [{
            "kind": "file", "repository_key": "memory-knowledge",
            "path_or_sequence_id": "scripts/prevention_owner_acceptance.py",
        }],
        "candidate_identity": identity,
        "candidate_fingerprint": fingerprint,
        "observer_provenance": {
            "decision_id": str(uuid.uuid5(uuid.NAMESPACE_URL, "owner-acceptance")),
            "observer_version": 1, "rule_version": 1,
        },
    }


def _special_object(
    owner_id: str, name: str, root: Path,
    executable_contracts: Mapping[str, Mapping[str, Any]],
) -> Any:
    if owner_id == "discovery-bootstrap" and name == "spec":
        return _candidate_spec(root)
    if owner_id == "convergence-checkpoint-run" and name == "child_intent":
        child = executable_contracts.get("claude-auth-token-refresh")
        if not isinstance(child, Mapping):
            raise ValueError("acceptance-child-contract-unavailable")
        child_parameters = [
            {"name": item.name, "value": item.value.canonical_json()}
            for item in parameters_for({
                "sequence_id": child["owner_sequence_id"],
                "executable_contract": child,
            }, "status", root, executable_contracts=executable_contracts)
        ]
        return {
            "child_owner_sequence_id": "claude-auth-token-refresh",
            "child_contract_sha256": child["owner_contract_sha256"],
            "child_intent_id": str(uuid.uuid5(uuid.NAMESPACE_URL, "acceptance-child")),
            "child_parameters": child_parameters,
            "guard_receipt_id": str(uuid.uuid5(uuid.NAMESPACE_URL, "acceptance-guard")),
        }
    if owner_id == "convergence-state-review-cycle" and name == "request":
        state = _ensure_convergence_state(root)
        state_payload = json.loads(state.read_text(encoding="utf-8"))
        return {
            "schema_version": 2,
            "request_id": str(uuid.uuid5(uuid.NAMESPACE_URL, "acceptance-review")),
            "state": "runtime-temp/" + str(state.relative_to("/private/tmp")),
            "initial_state_sha256": sha256_bytes(state.read_bytes()),
            "expected_final_status": state_payload["status"],
            "operations": [{
                "operation_id": str(uuid.uuid5(uuid.NAMESPACE_URL, "acceptance-op")),
                "kind": "status",
            }],
        }
    return None


def _sample_path(name: str, spec: Mapping[str, Any], root: Path) -> str:
    if name == "state":
        state = _ensure_convergence_state(root)
        return "runtime-temp/" + str(state.relative_to("/private/tmp"))
    if name == "spec":
        return "scripts/prevention_owner_acceptance.py"
    if name == "repo_roots_file":
        mirror = ensure_memory_mirror(root)
        relative = Path(
            "operations/sequences/discovery/"
            "2026-07-14-up-harness-cd-s-002-live-verification.repositories.json"
        )
        target = mirror / relative
        target.write_bytes(canonical_bytes({
            "memory-knowledge": str(mirror),
            "mcp-agents-workflow": "/Users/kamenkamenov/mcp-agents-workflow",
        }))
        return relative.name
    if name == "prompt_file":
        target = _runtime_temp_path(root, "prompt.txt")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("owner acceptance prompt\n", encoding="utf-8")
        return _runtime_temp_relative(root, "prompt.txt")
    roots = spec.get("trusted_roots")
    if isinstance(roots, list):
        selected = "runtime-temp" if "runtime-temp" in roots else str(roots[0])
        relative = _runtime_temp_relative(root, f"{name}.json")
        target = _runtime_temp_path(root, f"{name}.json") if selected == "runtime-temp" else None
        if target is not None:
            if "DIRECTORY" in str(spec.get("mode", "")):
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists() and "DIRECTORY" not in str(spec.get("mode", "")):
                target.write_text("{}", encoding="utf-8")
        return f"{selected}/{relative}"
    root_key = spec.get("trusted_root") or spec.get("fixed_root")
    if root_key == "runtime-temp":
        target = _runtime_temp_path(root, f"{name}.json")
        if "DIRECTORY" in str(spec.get("mode", "")):
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
        if str(spec.get("mode", "")).startswith("READ") and not target.exists():
            target.write_text("{}", encoding="utf-8")
        return _runtime_temp_relative(root, f"{name}.json")
    if root_key == "discovery-root":
        return "2026-07-17-prevention-owner-runtime-five-defect-convergence.md"
    if root_key == "task-artifact-root":
        return "prevention-system-completion/plan.md"
    if root_key in {"memory-knowledge", "mcp-agents-workflow"}:
        return "."
    if spec.get("trusted_root_from"):
        return "."
    return "."


def _sample(
    owner_id: str, name: str, spec: Mapping[str, Any], root: Path,
    executable_contracts: Mapping[str, Mapping[str, Any]],
) -> Any:
    type_name = str(spec["type"])
    special = _special_object(
        owner_id, name, root, executable_contracts,
    )
    if special is not None:
        return special
    if owner_id == "discovery-promotion-lifecycle" and name == "changed_artifacts":
        return [{
            "repository_key": "memory-knowledge",
            "path": "tests/fixtures/captured_prevention_v4_trust_anchors.json",
        }]
    if type_name == "BOOLEAN":
        return bool(spec.get("fixed", spec.get("default", False)))
    if type_name in {"INTEGER", "NUMBER"}:
        return spec.get("fixed", spec.get("default", max(1, spec.get("minimum", 1))))
    if type_name == "PATH" or type_name == "REPOSITORY_RELATIVE_FILE_PATH":
        return _sample_path(name, spec, root)
    if type_name == "ENUM":
        if name == "prompt_root_key":
            return "runtime-temp"
        return spec.get("values", ["acceptance"])[0]
    if type_name in {"ENUM_FROM_REGISTRY", "ENUM_FROM_REPOSITORY", "REPOSITORY_KEY", "RESOURCE_KEY"}:
        return "acceptance-resource"
    if type_name == "UUID":
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"owner-acceptance:{owner_id}:{name}"))
    if type_name == "FULL_GIT_OBJECT_ID":
        return _ensure_git_repository(root)
    if type_name == "SHA256":
        return "e" * 64
    if type_name in {"SET", "NONEMPTY_SET", "NONEMPTY_LIST"}:
        return ["scripts/prevention_owner_acceptance.py"]
    if type_name == "SET_ENUM":
        return ["host"] if "host" in spec["values"] else [spec["values"][0]]
    if type_name == "SET_UUID":
        return [str(uuid.uuid5(uuid.NAMESPACE_URL, f"owner-acceptance:{name}"))]
    if type_name == "SECRET_HANDLE":
        provider = str(spec.get("provider") or "acceptance-secret-provider")
        return {"provider_id": provider, "key_id": name, "version_id": "v1"}
    if type_name == "TAGGED_UNION":
        variants = spec["variants"]
        tag = "host_credential" if "host_credential" in variants else next(iter(variants))
        variant = variants[tag]
        if "handle_type" in variant:
            payload = {
                "provider_id": variant["provider"], "key_id": name,
                "version_id": "v1",
            }
        else:
            payload = f"owner-acceptance/{name}.json"
        return {"tag": tag, "payload": payload}
    if type_name == "EXACT_OBJECT":
        fields = spec.get("object_fields", spec.get("fields", []))
        if isinstance(fields, list):
            return {field: [] if field.endswith("parameters") else "acceptance" for field in fields}
        if isinstance(fields, Mapping):
            return {
                field: _sample(
                    owner_id, f"{name}.{field}", child, root,
                    executable_contracts,
                )
                if isinstance(child, Mapping) and "type" in child else child
                for field, child in fields.items()
                if not isinstance(child, Mapping) or child.get("required") is not False
            }
    if name == "branch":
        return "main"
    if name == "task_id":
        return "acceptance-" + sha256_bytes(str(root).encode("utf-8"))[:16]
    return "acceptance"


def parameters_for(
    owner: Mapping[str, Any], profile: str, root: Path, *,
    executable_contracts: Mapping[str, Mapping[str, Any]],
) -> tuple[TypedParameter, ...]:
    owner_id = _owner_id(owner)
    if owner_id == "commit-push-main":
        _ensure_git_repository(root)
        if profile in {"resume-push", "integrate-remote-and-resume"}:
            repository = root / "git-repository"
            subprocess.run(
                ["git", "-C", str(repository), "add", "scripts/prevention_owner_acceptance.py"],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(repository), "commit", "-m", "owner acceptance local commit"],
                check=True, capture_output=True,
            )
    if owner_id == "discovery-candidate-reconciliation" and profile in {
        "validate", "execute",
    }:
        _ensure_candidate_manifest(root)
    if owner_id == "discovery-candidate-reconciliation" and profile in {
        "execute-rolling", "drive",
    }:
        ensure_rolling_policy(root)
    discriminator = (
        "mode" if owner_id in {
            "commit-push-main", "greenfield-full-drive",
            "mawf-playbook-blocker-reentry",
        } else "command"
    )
    raw: dict[str, Any] = {} if profile == "default" else {discriminator: profile}
    specs, _ = prevention_adapters._applicable_schema(owner, raw)
    values = dict(raw)
    if owner_id == "local-workflow-orch-image" and profile in {
        "health", "seed-git-auth",
    }:
        values["port"] = 18080
    if owner_id == "discovery-promotion-lifecycle":
        ensure_memory_mirror(root)
        if profile in {"correct", "correct-registered"}:
            _seed_discovery_promotion_correction(root, profile)
        values["file"] = "2026-07-16-legacy-discovery-recovery-v1.md"
        if profile == "correct-registered":
            values["subject_id"] = "discovery-promotion-lifecycle"
        values["repo_roots_file"] = _sample_path(
            "repo_roots_file", specs["repo_roots_file"], root
        )
    materializers = {
        str(spec["materializes"]): name
        for name, spec in specs.items() if isinstance(spec.get("materializes"), str)
    }
    required_targets = {
        name for name, spec in specs.items()
        if prevention_adapters._predicate_requirements(name, spec, values, raw)[0]
    }
    required_materializer_files = {
        file_name for target, file_name in materializers.items()
        if target in required_targets
    }
    for name, spec in specs.items():
        if name in values or name in materializers:
            continue
        if "fixed" in spec or "default" in spec or "fixed_root" in spec:
            continue
        required, forbidden = prevention_adapters._predicate_requirements(
            name, spec, values, raw
        )
        if (
            forbidden or spec.get("derived_from")
            or (not required and name not in required_materializer_files)
        ):
            continue
        values[name] = _sample(
            owner_id, name, spec, root, executable_contracts,
        )
    for target, file_name in materializers.items():
        if file_name not in values:
            continue
        target_spec = specs[target]
        payload = _sample(
            owner_id, target, target_spec, root, executable_contracts,
        )
        file_value = str(values[file_name])
        relative = Path(file_value)
        if relative.parts and relative.parts[0] == "runtime-temp":
            relative = Path(*relative.parts[1:])
        path = Path("/private/tmp") / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical_bytes(payload))
    result = []
    for name, value in values.items():
        result.append(TypedParameter(
            name=name,
            value=ParameterValue(_tag(str(specs[name]["type"])), value),
        ))
    return tuple(result)


def intent_for(
    owner: Mapping[str, Any], profile: str, root: Path, *, proof_kind: str,
    executable_contracts: Mapping[str, Mapping[str, Any]],
) -> ActionIntent:
    owner_id = _owner_id(owner)
    run_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"owner-acceptance-run:{owner_id}:{profile}:{proof_kind}"))
    return ActionIntent(
        intent_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"owner-acceptance-intent:{owner_id}:{profile}:{proof_kind}")),
        task_id=f"owner-acceptance-{owner_id}", run_id=run_id,
        requested_sequence_id=owner_id,
        requested_implementation_id=sha256_bytes(canonical_bytes({"owner": owner_id})),
        compatibility_key=sha256_bytes(canonical_bytes({"profile": profile})),
        action_class=ActionClass.BASH,
        parameters=parameters_for(
            owner, profile, root, executable_contracts=executable_contracts,
        ),
    )
