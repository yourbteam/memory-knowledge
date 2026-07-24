#!/usr/bin/env python3
"""Materialize source-bound observable schemas and finite fixture specifications.

This artifact is evidence for owner-runtime admission; it does not itself make an
owner executable.  Provider implementation and same-source-path verification are
separate admission gates.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any, Mapping

try:
    from scripts import prevention_contract_materializer
    from scripts.prevention_contract import canonical_bytes, sha256_bytes
except ModuleNotFoundError:  # direct script execution
    import prevention_contract_materializer
    from prevention_contract import canonical_bytes, sha256_bytes


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "Tasks/prevention-system-completion/owner-observable-evidence.json"


class ObservableMaterializationError(ValueError):
    """The approved source cannot support a complete observable evidence row."""


# This is deliberately exhaustive.  The values are stable source-state names,
# not prose interpreted at runtime.
PROFILE_PROBES: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    "claude-auth-token-refresh": {
        "status": ("host-status", "container-status", "vault-status"),
        "mint": ("instruction-set", "credential-source-unread"),
        "seed-local": ("container-identity", "credential-fingerprint", "local-auth-probe"),
        "seed-host": ("host-slot", "credential-fingerprint", "host-auth-probe"),
        "push-kv": ("vault-resource", "credential-version", "config-version"),
        "reseed-azure": ("reseed-request", "remote-credential-version", "remote-auth-status"),
        "verify": ("selected-target-set", "target-auth-markers"),
        "all": ("ordered-child-graph", "child-terminal-set", "temporary-material-absent"),
    },
    "commit-push-main": {
        "dry-run": ("repository-identity", "index-empty", "manifest-content-hash"),
        "publish": ("local-effect-commit", "manifest-tree-delta", "remote-branch-head"),
        "resume-push": ("effect-marked-head", "index-empty", "remote-branch-head"),
        "integrate-remote-and-resume": ("rebase-state", "effect-lineage", "remote-branch-head"),
        "isolated-integrate-and-resume": ("source-snapshot", "isolated-effect-commit", "remote-branch-head"),
        "isolated-reconcile-and-resume": ("source-snapshot", "canonical-ledger-union", "generated-blocker-view", "remote-branch-head"),
    },
    "convergence-checkpoint-run": {
        "default": ("baseline-state-hash", "checkpoint-event", "child-terminal", "final-state-status"),
    },
    "convergence-state-review-cycle": {
        "dry-run": ("request-hash", "ordered-command-plan", "state-unchanged"),
        "apply": ("request-hash", "operation-receipts", "final-check", "final-status"),
    },
    "discovery-bootstrap": {
        "start": ("candidate-identity", "discovery-document", "dependency-manifest", "selection-receipt"),
    },
    "discovery-candidate-reconciliation": {
        "audit": ("candidate-inventory", "registry-snapshot", "audit-artifact"),
        "validate": ("approved-manifest-hash", "candidate-content-hashes", "registry-snapshot"),
        "execute": ("approved-manifest-hash", "candidate-checkpoint-set", "active-index"),
        "execute-rolling": ("rolling-policy-hash", "attempt-checkpoints", "stable-post-audit"),
        "drive": ("verification-child", "rolling-execution", "live-run-terminal"),
    },
    "discovery-promotion-lifecycle": {
        "status": ("candidate-lineage", "lifecycle-stage", "open-blocker-set"),
        "drive": ("candidate-lineage", "qualification-runs", "promotion-event", "registered-verification"),
        "correct": ("blocker-correction", "changed-artifact-manifest", "successor-run"),
        "correct-registered": ("registered-blocker-correction", "root-snapshot", "successor-run"),
    },
    "greenfield-full-drive": {
        "start-from-spec": ("spec-hash", "program-identity", "durable-frontier", "remote-head"),
        "create-program": ("decomposition-run", "program-created", "durable-frontier", "remote-head"),
        "resume-program": ("program-identity", "lease-takeover", "durable-frontier", "remote-head"),
        "validate-fresh": (
            "program-identity", "lease-takeover", "fresh-validation-smoke", "remote-head",
        ),
    },
    "local-workflow-orch-image": {
        "build": ("image-tag", "image-effect-label", "build-context-hash"),
        "run": ("container-identity", "container-effect-label", "image-and-port-binding"),
        "health": ("resolved-port", "health-status"),
        "copy-code-project": ("container-identity", "source-hash", "copy-receipt", "git-safe-directory"),
        "logs": ("container-identity", "log-byte-hash"),
        "stop": ("prepared-container-identity", "container-absence"),
        "seed-codex-auth": ("container-identity", "credential-file-state", "codex-auth-marker"),
        "seed-git-auth": ("container-identity", "git-config-state", "health-status", "authenticated-url-probe"),
        "probe-codex": ("no-tool-marker", "tool-marker"),
        "require-real-memory-knowledge": ("real-memory-knowledge-flag",),
    },
    "mawf-playbook-blocker-reentry": {
        "resume": ("parent-delegation", "original-run-identity", "post-control-state"),
        "restart-workflow": ("parent-delegation", "child-run-identity", "task-lineage"),
        "start-over": ("parent-delegation", "research-run-identity", "task-lineage"),
    },
}


SOURCE_ANCHORS: Mapping[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "claude-auth-token-refresh": ((
        "/Users/kamenkamenov/mcp-agents-workflow/scripts/claude_auth_refresh.sh",
        ("cmd_status()", "cmd_seed_local()", "cmd_push_kv()", "cmd_reseed_azure()", "cmd_verify_local()"),
    ),),
    "commit-push-main": ((
        "/Users/kamenkamenov/memory-knowledge/scripts/scoped_git_publish.py",
        ("def publish(", "def isolated_reconcile_and_resume(", "def resume_push("),
    ),),
    "convergence-checkpoint-run": ((
        "/Users/kamenkamenov/memory-knowledge/scripts/convergence_checkpoint_run.py",
        ("PASS_SIGNAL", "def main("),
    ),),
    "convergence-state-review-cycle": ((
        "/Users/kamenkamenov/memory-knowledge/scripts/convergence_state_review_cycle.py",
        ("def build_commands(", "def apply_request("),
    ),),
    "discovery-bootstrap": ((
        "/Users/kamenkamenov/memory-knowledge/scripts/discovery_bootstrap.py",
        ("def bootstrap(", "candidate_identity", "selection"),
    ),),
    "discovery-candidate-reconciliation": ((
        "/Users/kamenkamenov/memory-knowledge/scripts/discovery_candidate_reconciliation.py",
        ("def cmd_audit(", "def cmd_validate(", "def cmd_execute(", "def cmd_execute_rolling(", "def cmd_drive("),
    ),),
    "discovery-promotion-lifecycle": ((
        "/Users/kamenkamenov/memory-knowledge/scripts/discovery_promotion_lifecycle.py",
        ("def cmd_status(", "def cmd_drive(", "def cmd_correct(", "def cmd_correct_registered("),
    ),),
    "greenfield-full-drive": ((
        "/Users/kamenkamenov/mcp-agents-workflow/src/workflow_orch/greenfield_program_state.py",
        ("program_completed", "validation_terminal_settled", "terminalVerdict"),
    ), (
        "/Users/kamenkamenov/mcp-agents-workflow/scripts/greenfield_drive_dag.py",
        ("driveDag", "validateFresh", "detached"),
    ), (
        "/Users/kamenkamenov/mcp-agents-workflow/src/workflow_orch/mcp_server.py",
        ("validateFresh", "validate_fresh", "validation_terminal_settled"),
    )),
    "local-workflow-orch-image": ((
        "/Users/kamenkamenov/mcp-agents-workflow/scripts/local_workflow_orch_image_harness.py",
        ("def cmd_build(", "def cmd_run(", "def cmd_health(", "def cmd_seed_codex_auth(", "def cmd_seed_git_auth("),
    ),),
    "mawf-playbook-blocker-reentry": ((
        "/Users/kamenkamenov/mcp-agents-workflow/scripts/mawf_playbook_test_sequence.py",
        ("def cmd_reenter(", "targetRunId", "finalOk"),
    ),),
}


SOURCE_TESTS: Mapping[str, tuple[str, ...]] = {
    "claude-auth-token-refresh": (),
    "commit-push-main": ("/Users/kamenkamenov/memory-knowledge/tests/test_scoped_git_publish.py",),
    "convergence-checkpoint-run": ("/Users/kamenkamenov/memory-knowledge/tests/test_convergence_checkpoint_run.py",),
    "convergence-state-review-cycle": ("/Users/kamenkamenov/memory-knowledge/tests/test_convergence_state_review_cycle.py",),
    "discovery-bootstrap": ("/Users/kamenkamenov/memory-knowledge/tests/test_discovery_bootstrap.py",),
    "discovery-candidate-reconciliation": ("/Users/kamenkamenov/memory-knowledge/tests/test_discovery_candidate_reconciliation.py",),
    "discovery-promotion-lifecycle": ("/Users/kamenkamenov/memory-knowledge/tests/test_discovery_promotion_lifecycle.py",),
    "greenfield-full-drive": (
        "/Users/kamenkamenov/mcp-agents-workflow/tests/test_greenfield_resume_durability.py",
        "/Users/kamenkamenov/mcp-agents-workflow/tests/test_greenfield_post_harvest_checkpoint.py",
        "/Users/kamenkamenov/mcp-agents-workflow/tests/test_greenfield_live_validation.py",
    ),
    "local-workflow-orch-image": ("/Users/kamenkamenov/mcp-agents-workflow/tests/test_local_workflow_orch_image_harness.py",),
    "mawf-playbook-blocker-reentry": ("/Users/kamenkamenov/mcp-agents-workflow/tests/test_mawf_playbook_test_sequence.py",),
}


def _source_row(path_text: str, anchors: tuple[str, ...]) -> dict[str, Any]:
    path = Path(path_text)
    if not path.is_file():
        raise ObservableMaterializationError(f"observable-source-missing:{path}")
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    missing = [anchor for anchor in anchors if anchor not in text]
    if missing:
        raise ObservableMaterializationError(
            f"observable-source-anchor-missing:{path}:{missing[0]}"
        )
    return {
        "path": str(path),
        "sha256": sha256_bytes(raw),
        "anchors": list(anchors),
    }


def _test_row(path_text: str) -> dict[str, Any]:
    path = Path(path_text)
    if not path.is_file():
        raise ObservableMaterializationError(f"observable-test-missing:{path}")
    raw = path.read_bytes()
    try:
        tree = ast.parse(raw.decode("utf-8"), filename=str(path))
    except SyntaxError as exc:
        raise ObservableMaterializationError(f"observable-test-invalid:{path}") from exc
    tests = sorted(
        node.name for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    )
    if not tests:
        raise ObservableMaterializationError(f"observable-test-empty:{path}")
    return {"path": str(path), "sha256": sha256_bytes(raw), "test_ids": tests}


def _fixture_specs(probes: tuple[str, ...]) -> list[dict[str, Any]]:
    satisfied = {probe: "SATISFIED" for probe in probes}
    absent = {probe: "ABSENT" for probe in probes}
    return [
        {
            "fixture_id": "applied",
            "capture": {"identity": "MATCH", "prestate": "CHANGED", "receipt": "PRESENT", "work_state": "TERMINAL", "probes": satisfied, "observed_age_seconds": 0},
            "expected_reconciliation": "ALREADY_APPLIED",
            "expected_terminal": "PASS",
        },
        {
            "fixture_id": "absent",
            "capture": {"identity": "MATCH", "prestate": "MATCH", "receipt": "ABSENT", "work_state": "DETACHED", "probes": absent, "observed_age_seconds": 0},
            "expected_reconciliation": "NOT_APPLIED",
            "expected_terminal": "FAIL",
        },
        {
            "fixture_id": "conflicting",
            "capture": {"identity": "CONFLICT", "prestate": "UNKNOWN", "receipt": "CONFLICT", "work_state": "DETACHED", "probes": {**absent, probes[0]: "CONFLICT"}, "observed_age_seconds": 0},
            "expected_reconciliation": "INDETERMINATE",
            "expected_terminal": "FAIL",
        },
        {
            "fixture_id": "malformed",
            "capture": {"identity": "MATCH", "prestate": "MATCH", "receipt": "ABSENT", "work_state": "DETACHED", "probes": {key: value for key, value in absent.items() if key != probes[0]}, "observed_age_seconds": 0},
            "expected_error": "OBSERVABLE_SCHEMA_INVALID",
        },
        {
            "fixture_id": "stale",
            "capture": {"identity": "MATCH", "prestate": "CHANGED", "receipt": "PRESENT", "work_state": "TERMINAL", "probes": satisfied, "observed_age_seconds": 301},
            "expected_error": "OBSERVATION_STALE",
        },
    ]


def materialize() -> dict[str, Any]:
    proposals = prevention_contract_materializer.materialize()["owners"]
    owner_ids = {row["owner_sequence_id"] for row in proposals}
    if set(PROFILE_PROBES) != owner_ids or set(SOURCE_ANCHORS) != owner_ids or set(SOURCE_TESTS) != owner_ids:
        raise ObservableMaterializationError("observable-owner-map-incomplete")
    owners = []
    for owner in proposals:
        owner_id = owner["owner_sequence_id"]
        contract_profiles = {
            spec["profile"] for spec in owner["reconciliation_contract"]["observables"]
        }
        if set(PROFILE_PROBES[owner_id]) != contract_profiles:
            raise ObservableMaterializationError(f"observable-profile-map-incomplete:{owner_id}")
        sources = [_source_row(path, anchors) for path, anchors in SOURCE_ANCHORS[owner_id]]
        tests = [_test_row(path) for path in SOURCE_TESTS[owner_id]]
        profiles = []
        for profile in sorted(PROFILE_PROBES[owner_id]):
            probes = PROFILE_PROBES[owner_id][profile]
            profiles.append({
                "profile": profile,
                "provider_symbol_prefix": f"observe_{owner_id.replace('-', '_')}_{profile.replace('-', '_')}",
                "maximum_age_seconds": 300,
                "capture_schema": {
                    "closed": True,
                    "identity": ["MATCH", "CONFLICT"],
                    "prestate": ["MATCH", "CHANGED", "UNKNOWN"],
                    "receipt": ["PRESENT", "ABSENT", "CONFLICT", "UNKNOWN"],
                    "work_state": ["TERMINAL", "DETACHED"],
                    "probe_ids": list(probes),
                    "probe_result": ["SATISFIED", "ABSENT", "CONFLICT", "UNKNOWN"],
                    "observed_age_seconds": {"type": "INTEGER", "minimum": 0},
                },
                "fixture_specs": _fixture_specs(probes),
            })
        row = {
            "owner_sequence_id": owner_id,
            "approved_proposal_sha256": owner["approved_proposal_sha256"],
            "parameter_policy_sha256": owner["parameter_contract"]["policy_sha256"],
            "reconciliation_policy_sha256": owner["reconciliation_contract"]["policy_sha256"],
            "terminal_policy_sha256": owner["terminal_contract"]["policy_sha256"],
            "sources": sources,
            "source_tests": tests,
            "profiles": profiles,
        }
        row["evidence_sha256"] = sha256_bytes(canonical_bytes(row))
        owners.append(row)
    return {
        "schema_version": 1,
        "admission_effect": "PROVIDER_IMPLEMENTED_SOURCE_PATH_UNVERIFIED",
        "provider_implementation": _source_row(
            str(ROOT / "scripts/prevention_source_probes.py"),
            (
                "class ProductionSourceProbeBackend:",
                "PROVIDER_FACTORIES:",
                "def build_production_transport(",
            ),
        ),
        "owners": owners,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = canonical_bytes(materialize())
    if args.check:
        if not args.output.is_file() or args.output.read_bytes() != payload:
            raise SystemExit("owner-observable-evidence-drift")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(payload)
    print(json.dumps({
        "ok": True,
        "output": str(args.output),
        "sha256": sha256_bytes(payload),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
