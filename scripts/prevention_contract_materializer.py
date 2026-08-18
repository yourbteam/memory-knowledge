#!/usr/bin/env python3
"""Materialize approved owner proposals into closed executable contracts."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping

try:
    from scripts import prevention_owner_acceptance
    from scripts.prevention_contract import canonical_bytes, sha256_bytes
except ModuleNotFoundError:  # direct script execution
    import prevention_owner_acceptance
    from prevention_contract import canonical_bytes, sha256_bytes


ROOT = Path(__file__).resolve().parents[1]
PROPOSALS = ROOT / "Tasks/prevention-system-completion/owner-contract-proposals"
OUTPUT = ROOT / "Tasks/prevention-system-completion/owner-executable-contracts.json"
SOURCE_VERIFICATION = ROOT / "Tasks/prevention-system-completion/owner-source-verification.json"

OWNER_IDS = (
    "claude-auth-token-refresh",
    "commit-push-main",
    "convergence-checkpoint-run",
    "convergence-state-review-cycle",
    "discovery-bootstrap",
    "discovery-candidate-reconciliation",
    "discovery-promotion-lifecycle",
    "greenfield-full-drive",
    "local-workflow-orch-image",
    "mawf-playbook-blocker-reentry",
)

ACCEPTANCE_PROOF_KINDS = (
    "controller_runtime_positive",
    "controller_runtime_semantic_negative",
    "crash_reconciliation",
    "terminal_semantics",
    "effect_identity_source_binding",
    "production_source_probe_backend",
)

# These are the only proposal clauses that prove a profile has no source
# mutation to reconcile.  The materializer validates every pointer and binds
# the exact approved clause bytes; callers cannot relabel a profile.
NON_MUTATING_PROFILE_CLAUSES = {
    ("claude-auth-token-refresh", "status"):
        "/effect_and_reconciliation_contract/command_effects/status/effect_class",
    ("claude-auth-token-refresh", "mint"):
        "/effect_and_reconciliation_contract/command_effects/mint/effect_class",
    ("claude-auth-token-refresh", "verify"):
        "/effect_and_reconciliation_contract/command_effects/verify/effect_class",
    ("commit-push-main", "dry-run"):
        "/effect_and_reconciliation_contract/dry-run/effect_class",
    ("convergence-state-review-cycle", "dry-run"):
        "/effect_and_reconciliation_contract/dry_run_rule",
    ("discovery-candidate-reconciliation", "validate"):
        "/effect_and_reconciliation_contract/validate/effect_class",
    ("discovery-promotion-lifecycle", "status"):
        "/effect_and_reconciliation_contract/status/effect_class",
    ("local-workflow-orch-image", "health"):
        "/effect_and_reconciliation_contract/health/effect_identity",
    ("local-workflow-orch-image", "logs"):
        "/effect_and_reconciliation_contract/logs/effect_identity",
    ("local-workflow-orch-image", "probe-codex"):
        "/effect_and_reconciliation_contract/probe-codex/effect_identity",
    ("local-workflow-orch-image", "require-real-memory-knowledge"):
        "/effect_and_reconciliation_contract/require-real-memory-knowledge/effect_identity",
}

PARAMETER_TYPES = frozenset({
    "APPROVAL_RECEIPT_ID", "BOOLEAN", "ENUM", "ENUM_FROM_REGISTRY",
    "ENUM_FROM_REPOSITORY", "EXACT_OBJECT", "FULL_GIT_OBJECT_ID",
    "GIT_BRANCH_NAME", "INTEGER", "ISO_DATE", "LIST", "NONEMPTY_LIST",
    "NONEMPTY_SET", "NUMBER",
    "PATH", "REPOSITORY_KEY", "REPOSITORY_RELATIVE_FILE_PATH", "RESOURCE_KEY",
    "REPOSITORY_RELATIVE_PATH", "REPOSITORY_RELATIVE_PATH_OR_SEQUENCE_ID",
    "SECRET_HANDLE", "SET", "SET_ENUM", "SET_UUID", "SHA256", "STRING",
    "TAGGED_UNION", "UNIQUE_LIST_STRING", "UUID",
})

PARAMETER_METADATA_KEYS = frozenset({
    "admission_rules", "bootstrap_spec_v2", "by_command", "by_mode", "common",
    "field_authority", "operation_schemas", "path_rules", "promotion_metadata",
    "review_cycle_request_v2", "validation_boundary",
})


class MaterializationError(ValueError):
    """An approved proposal cannot be represented without inference."""


def _source_verification_admission(
    owner_contract: Mapping[str, Any],
) -> dict[str, Any]:
    if not SOURCE_VERIFICATION.is_file():
        return {
            "contract_verification": "UNVERIFIED",
            "dispatch_admission": "CLOSED",
            "reason_code": "OWNER_PROOF_REPORT_UNAVAILABLE",
        }
    try:
        report = json.loads(SOURCE_VERIFICATION.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "contract_verification": "UNVERIFIED",
            "dispatch_admission": "CLOSED",
            "reason_code": "OWNER_PROOF_REPORT_INVALID",
        }
    if not isinstance(report, Mapping):
        return {
            "contract_verification": "UNVERIFIED",
            "dispatch_admission": "CLOSED",
            "reason_code": "OWNER_PROOF_REPORT_INVALID",
        }
    try:
        return dict(prevention_owner_acceptance.verify_owner_report(
            report, owner_contract
        ))
    except prevention_owner_acceptance.AcceptanceError as exc:
        return {
            "contract_verification": "UNVERIFIED",
            "dispatch_admission": "CLOSED",
            "reason_code": f"OWNER_PROOF_UNVERIFIED:{exc}",
        }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MaterializationError(f"invalid-json:{path}") from exc
    if not isinstance(value, dict):
        raise MaterializationError(f"object-required:{path}")
    return value


def _source_bindings(
    proposal: Mapping[str, Any], *, source_root: Path | None = None
) -> list[dict[str, str]]:
    raw_sources = proposal.get("sources")
    if raw_sources is None:
        source = proposal.get("source")
        if not isinstance(source, Mapping):
            raise MaterializationError("source-binding-required")
        if "path" in source:
            raw_sources = [source]
        else:
            raw_sources = []
            for key, value in source.items():
                if not key.endswith("_path"):
                    continue
                prefix = key[:-5]
                expected = source.get(f"{prefix}_sha256")
                if expected is None:
                    continue
                raw_sources.append({
                    "path": value,
                    "sha256": expected,
                    "approved_post_correction_sha256": source.get(
                        f"{prefix}_approved_post_correction_sha256"
                    ),
                    "source_correction_decision_id": source.get(
                        f"{prefix}_source_correction_decision_id"
                    ),
                })
    elif isinstance(raw_sources, Mapping):
        raw_sources = list(raw_sources.values())
    if not isinstance(raw_sources, list) or not raw_sources:
        raise MaterializationError("source-binding-required")
    result: list[dict[str, str]] = []
    for raw in raw_sources:
        if not isinstance(raw, Mapping):
            raise MaterializationError("invalid-source-binding")
        path_value = raw.get("path")
        expected = raw.get("sha256")
        if isinstance(path_value, str) and expected is None:
            continue
        if not isinstance(path_value, str) or not isinstance(expected, str):
            raise MaterializationError("invalid-source-binding")
        path = Path(path_value)
        read_path = path
        if source_root is not None:
            trusted_roots = proposal.get("trusted_roots")
            canonical_root_value = (
                trusted_roots.get("memory-knowledge")
                if isinstance(trusted_roots, Mapping)
                else None
            )
            if not isinstance(canonical_root_value, str):
                raise MaterializationError("memory-knowledge-root-required")
            canonical_root = Path(canonical_root_value)
            try:
                read_path = source_root / path.relative_to(canonical_root)
            except ValueError:
                pass
        if not read_path.is_file():
            raise MaterializationError(f"source-missing:{read_path}")
        actual = sha256_bytes(read_path.read_bytes())
        binding = {"path": str(path), "sha256": actual}
        if actual != expected:
            approved_post = raw.get("approved_post_correction_sha256")
            decision_id = raw.get("source_correction_decision_id")
            approved_decisions = {
                item.get("decision_id")
                for item in proposal.get("authority_approvals", {}).values()
                if isinstance(item, Mapping) and item.get("status") == "APPROVED"
            }
            if actual != approved_post or decision_id not in approved_decisions:
                raise MaterializationError(f"source-correction-not-approved:{path}")
            binding["approved_pre_correction_sha256"] = expected
            binding["approved_post_correction_sha256"] = approved_post
            binding["source_correction_decision_id"] = decision_id
        result.append(binding)
    if not result:
        raise MaterializationError("source-binding-required")
    return sorted(result, key=lambda item: item["path"])


def _normalized_budget(proposal: Mapping[str, Any]) -> dict[str, Any]:
    raw = proposal.get("unit_budget")
    if raw is None:
        raw = proposal.get("budget_contract")
    if not isinstance(raw, Mapping):
        raise MaterializationError("budget-contract-required")
    mode = raw.get("reservation_mode")
    if proposal["owner_sequence_id"] == "greenfield-full-drive":
        kind = "ATOMIC_FRONTIER"
    elif mode == "OWNER_DERIVED_CHILD_COMPOSITION":
        kind = "CHILD_COMPOSITION"
    elif mode in {
        "OWNER_DERIVED_PROGRESSIVE", "OWNER_DERIVED_ORDERED_OPERATIONS",
        "OWNER_DERIVED_ATOMIC_FRONTIER",
    }:
        kind = (
            "ATOMIC_FRONTIER"
            if mode == "OWNER_DERIVED_ATOMIC_FRONTIER"
            else "PROFILED_PROGRESSIVE"
        )
    elif "duration_milliseconds" in raw:
        kind = "FIXED_UNIT"
    else:
        raise MaterializationError(f"unsupported-budget-shape:{proposal['owner_sequence_id']}")
    result = {
        "kind": kind,
        "owner_sequence_id": proposal["owner_sequence_id"],
        "atomic_task_cap_milliseconds": int(raw.get("atomic_task_cap_milliseconds", 3_600_000)),
        "contract": dict(raw),
    }
    owner = str(proposal["owner_sequence_id"])
    if kind == "FIXED_UNIT":
        result["derivation_ast"] = {
            "op": "CONST", "unit_budget": {
                key: raw.get(key)
                for key in (
                    "schema_version", "owner_sequence_id", "productive_milliseconds",
                    "mandatory_role_milliseconds", "adjudication_milliseconds",
                    "materialization_milliseconds", "terminal_milliseconds",
                    "retry_milliseconds", "token_units", "monetary_micros",
                    "duration_milliseconds",
                )
                if key in raw
            },
        }
    elif kind == "CHILD_COMPOSITION":
        expected = "28800000 + CHILD_DURATION_MILLISECONDS"
        if raw.get("duration_formula_milliseconds") != expected:
            raise MaterializationError(f"child-budget-formula-drift:{owner}")
        result["derivation_ast"] = {
            "op": "ADD",
            "operands": [
                {"op": "CONST", "value": 28_800_000},
                {"op": "VAR", "name": "CHILD_DURATION_MILLISECONDS", "producer": "content-addressed-child-unit-budget"},
            ],
        }
    elif kind == "ATOMIC_FRONTIER":
        result["derivation_ast"] = {
            "op": "SUM", "index": "task", "list_var": "NEXT_DURABLE_FRONTIER",
            "producer": "durable-program-state-next-frontier",
            "maximum_cardinality": int(raw.get("maximum_features", 20)),
            "expression": {"op": "VAR", "name": "task.duration_milliseconds"},
        }
    else:
        profiles = raw.get("mode_profiles", raw.get("command_profiles"))
        if not isinstance(profiles, Mapping) or not profiles:
            raise MaterializationError(f"budget-profiles-required:{owner}")
        normalized_profiles: dict[str, Any] = {}
        dynamic_task_ast: dict[tuple[str, str], dict[str, Any]] = {
            ("convergence-state-review-cycle", "apply"): {
                "op": "ADD", "operands": [{"op": "VAR", "name": "M"}, {"op": "CONST", "value": 2}],
            },
            ("discovery-candidate-reconciliation", "execute"): {
                "op": "ADD", "operands": [
                    {"op": "CONST", "value": 2}, {"op": "VAR", "name": "N"},
                    {"op": "MULTIPLY", "operands": [{"op": "CONST", "value": 15}, {"op": "VAR", "name": "P"}]},
                ],
            },
            ("discovery-candidate-reconciliation", "execute-rolling"): {
                "op": "SUM", "index": "attempt", "list_var": "ATTEMPTS", "maximum_cardinality": 6,
                "expression": {"op": "ADD", "operands": [
                    {"op": "CONST", "value": 4}, {"op": "VAR", "name": "attempt.N"},
                    {"op": "MULTIPLY", "operands": [{"op": "CONST", "value": 15}, {"op": "VAR", "name": "attempt.P"}]},
                ]},
            },
            ("discovery-candidate-reconciliation", "drive"): {
                "op": "ADD", "operands": [
                    {"op": "CONST", "value": 8},
                    {"op": "SUM", "index": "attempt", "list_var": "ATTEMPTS", "maximum_cardinality": 6,
                     "expression": {"op": "ADD", "operands": [
                         {"op": "CONST", "value": 4}, {"op": "VAR", "name": "attempt.N"},
                         {"op": "MULTIPLY", "operands": [{"op": "CONST", "value": 15}, {"op": "VAR", "name": "attempt.P"}]},
                     ]}},
                ],
            },
        }
        for profile_name, profile in sorted(profiles.items()):
            if not isinstance(profile, Mapping):
                raise MaterializationError(f"invalid-budget-profile:{owner}:{profile_name}")
            if "productive_task_count" in profile:
                expression = {"op": "CONST", "value": int(profile["productive_task_count"])}
            else:
                expression = dynamic_task_ast.get((owner, str(profile_name)))
                if expression is None:
                    raise MaterializationError(f"unmapped-budget-formula:{owner}:{profile_name}")
            normalized_profiles[str(profile_name)] = {
                "productive_task_count_ast": expression,
                "source_sha256": sha256_bytes(canonical_bytes(profile)),
            }
        result["profiles"] = normalized_profiles
    return result


EXPLICIT_CONDITIONS: dict[tuple[str, str, str], dict[str, Any]] = {
    ("commit-push-main", "manifest", "required_unless"): {
        "op": "NE", "left": {"field": "mode"}, "right": {"literal": "resume-push"},
    },
    ("commit-push-main", "authorization_receipt_id", "required_unless"): {
        "op": "NE", "left": {"field": "mode"}, "right": {"literal": "dry-run"},
    },
    ("greenfield-full-drive", "keyvault_name", "required_unless"): {
        "op": "NE", "left": {"field": "skip_auth"}, "right": {"literal": True},
    },
    ("local-workflow-orch-image", "port", "required_unless"): {
        "op": "ABSENT", "field": "port_file",
    },
    ("local-workflow-orch-image", "port_file", "required_unless"): {
        "op": "ABSENT", "field": "port",
    },
    ("mawf-playbook-blocker-reentry", "workflow_name", "required_unless"): {
        "op": "NE", "left": {"field": "mode"}, "right": {"literal": "start-over"},
    },
    ("commit-push-main", "ledger_path", "required_when"): {
        "op": "RESOLVES", "field": "manifest", "producer": "work-memory-ledger-membership-v1",
    },
    ("discovery-promotion-lifecycle", "task_id", "required_when"): {
        "op": "RESOLVES", "field": "changed_artifacts", "producer": "protected-artifact-detector-v1",
    },
    ("discovery-bootstrap", "repo_roots_file", "required_when"): {
        "op": "RESOLVES", "field": "spec", "producer": "non-default-repository-dependency-detector-v1",
    },
    ("claude-auth-token-refresh", "container_key", "also_required_when"): {
        "op": "ANY", "predicates": [
            {"op": "EQ", "left": {"field": "credential_source.tag"}, "right": {"literal": "approved_container_credential"}},
            {"op": "IN", "value": {"literal": "local-container"}, "collection": {"field": "verify_targets"}},
        ],
    },
    ("claude-auth-token-refresh", "deployment_key", "also_required_when"): {
        "op": "IN", "value": {"literal": "remote-claude"}, "collection": {"field": "verify_targets"},
    },
}

EXPLICIT_CONDITION_TEXT: dict[tuple[str, str, str], Any] = {
    ("commit-push-main", "manifest", "required_unless"): "resume-push",
    ("commit-push-main", "authorization_receipt_id", "required_unless"): "dry-run",
    ("greenfield-full-drive", "keyvault_name", "required_unless"): "skip_auth",
    ("local-workflow-orch-image", "port", "required_unless"): "port_file",
    ("local-workflow-orch-image", "port_file", "required_unless"): "port",
    ("mawf-playbook-blocker-reentry", "workflow_name", "required_unless"): "start-over",
    ("commit-push-main", "ledger_path", "required_when"):
        "isolated-reconcile-and-resume includes the work-memory ledger",
    ("discovery-promotion-lifecycle", "task_id", "required_when"):
        "a protected correction artifact is present",
    ("discovery-bootstrap", "repo_roots_file", "required_when"):
        "a dependency uses a non-default repository key",
    ("claude-auth-token-refresh", "container_key", "also_required_when"):
        "credential_source is approved_container_credential or verify_targets contains local-container",
    ("claude-auth-token-refresh", "deployment_key", "also_required_when"):
        "verify_targets contains remote-claude",
}


def _predicate_ast(
    owner_sequence_id: str, name: str, spec: Mapping[str, Any],
) -> dict[str, Any]:
    predicates: list[dict[str, Any]] = []
    if spec.get("required") is True:
        predicates.append({"op": "PRESENT", "field": name})
    if "required_for" in spec:
        key = "required_for"
        op = "REQUIRED_IF"
        values = spec[key] if isinstance(spec[key], list) else [spec[key]]
        predicates.append({"op": op, "field": name, "modes": values})
    for key in ("required_unless", "required_when", "also_required_when"):
        if key in spec:
            condition = EXPLICIT_CONDITIONS.get((owner_sequence_id, name, key))
            expected_text = EXPLICIT_CONDITION_TEXT.get((owner_sequence_id, name, key))
            if condition is None or spec[key] != expected_text:
                raise MaterializationError(
                    f"unmapped-cross-field-condition:{owner_sequence_id}:{name}:{key}"
                )
            predicates.append({"op": "REQUIRED_IF", "field": name, "condition": condition})
    if "minimum" in spec or "maximum" in spec:
        predicates.append({
            "op": "RANGE", "field": name,
            "minimum": spec.get("minimum"), "maximum": spec.get("maximum"),
        })
    if "minimum_length" in spec:
        predicates.append({"op": "LENGTH", "field": name, "minimum": spec["minimum_length"]})
    if "maximum_length" in spec:
        predicates.append({"op": "LENGTH", "field": name, "maximum": spec["maximum_length"]})
    if "minimum_items" in spec or "maximum_items" in spec:
        predicates.append({
            "op": "LENGTH", "field": name,
            "minimum": spec.get("minimum_items"), "maximum": spec.get("maximum_items"),
        })
    if "pattern" in spec:
        predicates.append({"op": "MATCHES", "field": name, "pattern": spec["pattern"]})
    if "values" in spec:
        predicates.append({"op": "IN", "field": name, "values": spec["values"]})
    if "fixed" in spec:
        predicates.append({"op": "EQ", "field": name, "value": spec["fixed"]})
    if "derived_from" in spec:
        predicates.append({"op": "RESOLVES", "field": name, "producer": spec["derived_from"]})
        predicates.append({"op": "ABSENT", "field": name, "source": "CALLER"})
    if spec.get("caller_supplied") is False:
        predicates.append({"op": "ABSENT", "field": name, "source": "CALLER"})
    if "required_with" in spec:
        predicates.append({
            "op": "IMPLIES",
            "if": {"op": "PRESENT", "field": spec["required_with"]},
            "then": {"op": "PRESENT", "field": name},
        })
    for key in ("materializes", "cross_check", "must_equal", "derived_for"):
        if key in spec:
            predicates.append({
                "op": "RESOLVES", "field": name,
                "producer": f"{key}:{spec[key]}",
            })
            if key == "derived_for":
                predicates.append({
                    "op": "ABSENT", "field": name, "source": "CALLER",
                    "modes": [spec[key]],
                })
    return {"op": "ALL", "predicates": predicates}


def _normalized_parameters(proposal: Mapping[str, Any]) -> dict[str, Any]:
    raw = proposal.get("parameter_contract")
    if not isinstance(raw, Mapping):
        raise MaterializationError("parameter-contract-required")
    owner_sequence_id = str(proposal["owner_sequence_id"])
    result: list[dict[str, Any]] = []
    normalized_nodes: list[dict[str, Any]] = []
    schema_rules: dict[str, Any] = {}
    for name, spec in sorted(raw.items()):
        if not isinstance(spec, Mapping) or spec.get("type") is None:
            if name not in PARAMETER_METADATA_KEYS:
                raise MaterializationError(f"unknown-parameter-metadata:{name}")
            if name not in {"field_authority", "validation_boundary"}:
                schema_rules[name] = spec
            continue
        source_type = spec.get("type")
        if source_type not in PARAMETER_TYPES:
            raise MaterializationError(f"unsupported-parameter-type:{name}:{source_type}")
        result.append({
            "name": name,
            "type": source_type,
            "predicate": _predicate_ast(owner_sequence_id, name, spec),
            "schema": dict(spec),
        })
    def collect(value: Any, pointer: str) -> None:
        if isinstance(value, Mapping):
            if "type" in value:
                source_type = value["type"]
                if source_type not in PARAMETER_TYPES:
                    raise MaterializationError(
                        f"unsupported-parameter-type:{pointer}:{source_type}"
                    )
                normalized_nodes.append({
                    "source_pointer": pointer,
                    "name": pointer.rsplit("/", 1)[-1],
                    "type": source_type,
                    "predicate": _predicate_ast(
                        owner_sequence_id, pointer.rsplit("/", 1)[-1], value
                    ),
                    "schema_sha256": sha256_bytes(canonical_bytes(value)),
                })
            for key, item in sorted(value.items()):
                escaped = str(key).replace("~", "~0").replace("/", "~1")
                collect(item, f"{pointer}/{escaped}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                collect(item, f"{pointer}/{index}")
    collect(raw, "/parameter_contract")
    return {
        "parameters": result,
        "schema_rules": schema_rules,
        "normalized_nodes": normalized_nodes,
        "policy_sha256": sha256_bytes(canonical_bytes(raw)),
    }


def _json_pointers(value: Any, prefix: str) -> list[str]:
    if isinstance(value, Mapping):
        result: list[str] = []
        for key, item in sorted(value.items()):
            escaped = str(key).replace("~", "~0").replace("/", "~1")
            result.extend(_json_pointers(item, f"{prefix}/{escaped}"))
        return result or [prefix]
    if isinstance(value, list):
        result = []
        for index, item in enumerate(value):
            result.extend(_json_pointers(item, f"{prefix}/{index}"))
        return result or [prefix]
    return [prefix]


def _clause_coverage(proposal: Mapping[str, Any]) -> list[dict[str, str]]:
    section_nodes = {
        "parameter_contract": "/parameter_contract/normalized_nodes",
        "unit_budget": "/budget_contract",
        "budget_contract": "/budget_contract",
        "effect_and_reconciliation_contract": "/reconciliation_contract",
        "terminal_contract": "/terminal_contract",
        "trusted_roots": "/trusted_roots",
        "source": "/implementation_sources",
        "sources": "/implementation_sources",
        "authority_approvals": "/authority_decision_ids",
        "allowed_parent_sequence_ids": "/allowed_parent_sequence_ids",
        "standalone": "/standalone",
    }
    result: list[dict[str, str]] = []
    for pointer in _json_pointers(proposal, ""):
        top = pointer.split("/", 2)[1] if pointer.startswith("/") else pointer
        node = section_nodes.get(top, f"/{top}")
        result.append({"proposal_pointer": pointer, "contract_node": node})
    pointers = [item["proposal_pointer"] for item in result]
    if len(pointers) != len(set(pointers)):
        raise MaterializationError("duplicate-clause-coverage")
    return sorted(result, key=lambda item: item["proposal_pointer"])


def _authority_decision_ids(proposal: Mapping[str, Any]) -> list[str]:
    result: list[str] = []
    for item in proposal.get("authority_approvals", {}).values():
        if not isinstance(item, Mapping) or item.get("status") != "APPROVED":
            continue
        if isinstance(item.get("decision_id"), str):
            result.append(item["decision_id"])
        elif (
            isinstance(item.get("decision_ids"), list)
            and item["decision_ids"]
            and all(isinstance(value, str) and value for value in item["decision_ids"])
        ):
            result.extend(item["decision_ids"])
        else:
            raise MaterializationError("approved-authority-decision-id-required")
    if not result or len(result) != len(set(result)):
        raise MaterializationError("invalid-authority-decision-ids")
    return sorted(result)


def _runtime_policy_clause_ids(policy: Mapping[str, Any]) -> list[str]:
    """Content-address every approved runtime clause; source fixes are build-time gates."""
    result: list[str] = []

    def walk(value: Any, pointer: str) -> None:
        if isinstance(value, Mapping):
            for key in sorted(value):
                escaped = str(key).replace("~", "~0").replace("/", "~1")
                walk(value[key], f"{pointer}/{escaped}")
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{pointer}/{index}")
            return
        top = pointer.split("/", 2)[1] if pointer.startswith("/") else pointer
        if top in {"source_correction", "source_corrections"}:
            return
        if not isinstance(value, str) or not value.strip():
            raise MaterializationError(f"runtime-policy-clause-invalid:{pointer}")
        result.append(sha256_bytes(canonical_bytes({
            "pointer": pointer,
            "requirement": value,
        })))

    walk(policy, "")
    if not result or len(result) != len(set(result)):
        raise MaterializationError("runtime-policy-clause-coverage-invalid")
    return sorted(result)


def _owner_profiles(proposal: Mapping[str, Any]) -> list[str]:
    parameters = proposal.get("parameter_contract", {})
    for name in ("command", "mode"):
        spec = parameters.get(name) if isinstance(parameters, Mapping) else None
        if isinstance(spec, Mapping) and isinstance(spec.get("values"), list):
            values = spec["values"]
            if values and all(isinstance(value, str) and value for value in values):
                return sorted(values)
    by_command = parameters.get("by_command") if isinstance(parameters, Mapping) else None
    if isinstance(by_command, Mapping) and by_command:
        return sorted(str(value) for value in by_command)
    return ["default"]


def _observable_specs(owner_id: str, proposal: Mapping[str, Any], kind: str) -> list[dict[str, Any]]:
    result = []
    for profile in _owner_profiles(proposal):
        profile_symbol = profile.replace("-", "_")
        result.append({
            "observable_id": f"{owner_id}/{profile}/{kind}",
            "provider_symbol": (
                f"observe_{owner_id.replace('-', '_')}_{profile_symbol}_{kind}"
            ),
            "profile": profile,
            "read_only": True,
            "maximum_age_seconds": 300,
            "request_fields": [
                "effect_id", "owner_sequence_id", "preparation_artifact_sha256",
                "observation_targets", "prepared_prestate_identities",
                "prepared_receipt_identities",
                "profile", "probe_ids", "provider_symbol",
                "source_evidence_sha256",
            ],
            "ownership_fields": [
                "effect_id", "owner_sequence_id", "preparation_artifact_sha256",
            ],
            "result_fields": [
                "identity", "observed_at_utc", "ownership", "prestate",
                "probes", "receipt", "source_evidence_sha256", "work_state",
            ],
        })
    return result


def _pointer_value(document: Mapping[str, Any], pointer: str) -> Any:
    value: Any = document
    for raw_part in pointer.lstrip("/").split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(value, Mapping) or part not in value:
            raise MaterializationError(
                f"acceptance-applicability-clause-missing:{pointer}"
            )
        value = value[part]
    return value


def _acceptance_proofs(
    owner_id: str, proposal: Mapping[str, Any],
) -> list[dict[str, Any]]:
    profiles = _owner_profiles(proposal)
    unknown = sorted(
        profile for mapped_owner, profile in NON_MUTATING_PROFILE_CLAUSES
        if mapped_owner == owner_id and profile not in profiles
    )
    if unknown:
        raise MaterializationError(
            f"acceptance-applicability-profile-unknown:{owner_id}:{','.join(unknown)}"
        )
    result = []
    for profile in profiles:
        pointer = NON_MUTATING_PROFILE_CLAUSES.get((owner_id, profile))
        clause_sha256 = None
        if pointer is not None:
            clause = _pointer_value(proposal, pointer)
            clause_text = str(clause).upper()
            if not (
                clause in {"OBSERVATION", "OPERATOR_INSTRUCTION"}
                or "NO STATE MUTATION" in clause_text
                or "NO CREDENTIAL READ OR MUTATION" in clause_text
                or ("DOES NOT" in clause_text and "UNCHANGED" in clause_text)
                or clause_text.startswith("NONE;")
            ):
                raise MaterializationError(
                    f"acceptance-non-mutating-clause-invalid:{owner_id}:{profile}"
                )
            clause_sha256 = sha256_bytes(canonical_bytes({
                "pointer": pointer,
                "clause": clause,
            }))
        proofs = []
        for proof_kind in ACCEPTANCE_PROOF_KINDS:
            not_applicable = pointer is not None and proof_kind in {
                "crash_reconciliation", "effect_identity_source_binding",
            }
            proof = {
                "proof_kind": proof_kind,
                "applicability": (
                    "NOT_APPLICABLE" if not_applicable else "REQUIRED"
                ),
            }
            if not_applicable:
                proof.update({
                    "contract_clause_pointer": pointer,
                    "contract_clause_sha256": clause_sha256,
                })
            proofs.append(proof)
        result.append({"profile_id": profile, "proofs": proofs})
    return result


def materialize(
    proposals_dir: Path = PROPOSALS,
    owner_ids: tuple[str, ...] = OWNER_IDS,
    *,
    source_root: Path | None = None,
    source_root_owner_ids: frozenset[str] | None = None,
) -> dict[str, Any]:
    if source_root is None and (configured := os.environ.get(
        "MK_PREVENTION_SOURCE_ROOT"
    )):
        source_root = Path(configured)
    if source_root_owner_ids is None and (configured_owners := os.environ.get(
        "MK_PREVENTION_SOURCE_ROOT_OWNER_IDS"
    )):
        source_root_owner_ids = frozenset(
            value for value in configured_owners.split(",") if value
        )
    if source_root_owner_ids is not None and not source_root_owner_ids.issubset(
        OWNER_IDS
    ):
        raise MaterializationError("invalid-source-root-owner-selection")
    if (
        not owner_ids
        or len(owner_ids) != len(set(owner_ids))
        or not set(owner_ids).issubset(OWNER_IDS)
    ):
        raise MaterializationError("invalid-owner-selection")
    rows: list[dict[str, Any]] = []
    for owner_id in owner_ids:
        proposal_path = proposals_dir / f"{owner_id}.json"
        proposal = _read_json(proposal_path)
        if (
            proposal.get("schema_version") != 1
            or proposal.get("proposal_status") != "APPROVED"
            or proposal.get("availability_policy") != "AVAILABLE"
            or proposal.get("owner_sequence_id") != owner_id
            or proposal.get("authority_decisions_required") != []
        ):
            raise MaterializationError(f"proposal-not-executable:{owner_id}")
        proposal_hash = sha256_bytes(canonical_bytes(proposal))
        reconciliation = proposal.get("effect_and_reconciliation_contract")
        terminal = proposal.get("terminal_contract")
        roots = proposal.get("trusted_roots")
        if not all(isinstance(item, Mapping) for item in (reconciliation, terminal, roots)):
            raise MaterializationError(f"incomplete-owner-contract:{owner_id}")
        parameter_contract = _normalized_parameters(proposal)
        reconciliation_policy_sha256 = sha256_bytes(canonical_bytes(reconciliation))
        terminal_policy_sha256 = sha256_bytes(canonical_bytes(terminal))
        row: dict[str, Any] = {
            "schema_version": 1,
            "owner_sequence_id": owner_id,
            "availability_policy": "AVAILABLE",
            "standalone": bool(proposal.get("standalone", owner_id != "mawf-playbook-blocker-reentry")),
            "allowed_parent_sequence_ids": sorted(proposal.get("allowed_parent_sequence_ids", [])),
            "approved_proposal_sha256": proposal_hash,
            "authority_decision_ids": _authority_decision_ids(proposal),
            "implementation_sources": _source_bindings(
                proposal,
                source_root=(
                    source_root
                    if source_root_owner_ids is None
                    or owner_id in source_root_owner_ids
                    else None
                ),
            ),
            "budget_contract": _normalized_budget(proposal),
            "parameter_contract": parameter_contract,
            "trusted_roots": dict(roots),
            "acceptance_proofs": _acceptance_proofs(owner_id, proposal),
            "reconciliation_contract": {
                "handler": f"reconcile_{owner_id.replace('-', '_')}",
                "policy_sha256": reconciliation_policy_sha256,
                "required_clause_ids": _runtime_policy_clause_ids(reconciliation),
                "observables": _observable_specs(owner_id, proposal, "reconciliation"),
                "classification_priority": ["INDETERMINATE_ON_CONFLICT", "ALREADY_APPLIED", "NOT_APPLIED", "INDETERMINATE"],
                "policy": dict(reconciliation),
            },
            "terminal_contract": {
                "handler": f"verify_{owner_id.replace('-', '_')}",
                "policy_sha256": terminal_policy_sha256,
                "result_kinds": ["EXECUTED_RESULT", "RECOVERED_RESULT"],
                "branches": {
                    "EXECUTED_RESULT": {
                        "required_result_fields": [
                            "returncode", "result_envelope", "stderr_sha256",
                            "stdout_encoding", "stdout_sha256",
                        ],
                        "forbidden_result_fields": [
                            "reconciliation_artifact_sha256",
                            "reconciliation_event_id",
                        ],
                    },
                    "RECOVERED_RESULT": {
                        "required_result_fields": [
                            "effect_id", "reconciliation_artifact_sha256",
                            "reconciliation_event_id",
                        ],
                        "forbidden_result_fields": [
                            "returncode", "result_envelope", "stderr_sha256",
                            "stdout_encoding", "stdout_sha256",
                        ],
                    },
                },
                "semantic_observation_fields": [
                    "effect_id", "evidence", "observed_at_utc", "owner_sequence_id",
                    "preparation_artifact_sha256", "provider_id", "raw_result",
                    "result_kind", "terminal_policy_sha256",
                ],
                "required_clause_ids": _runtime_policy_clause_ids(terminal),
                "observables": _observable_specs(owner_id, proposal, "terminal"),
                "policy": dict(terminal),
            },
            "clause_coverage": _clause_coverage(proposal),
        }
        row["acceptance_contract_sha256"] = sha256_bytes(canonical_bytes(row))
        row["execution_admission"] = _source_verification_admission(row)
        row["owner_contract_sha256"] = sha256_bytes(canonical_bytes(row))
        rows.append(row)
    return {"schema_version": 1, "owners": rows}


def merge_selected_owner(
    current: Mapping[str, Any], replacement: Mapping[str, Any]
) -> dict[str, Any]:
    if current.get("schema_version") != 1 or not isinstance(
        current.get("owners"), list
    ):
        raise MaterializationError("invalid-existing-output")
    current_ids = [
        row.get("owner_sequence_id")
        for row in current["owners"]
        if isinstance(row, Mapping)
    ]
    if tuple(current_ids) != OWNER_IDS:
        raise MaterializationError("invalid-existing-owner-set")
    owner_id = replacement.get("owner_sequence_id")
    if owner_id not in OWNER_IDS:
        raise MaterializationError("invalid-replacement-owner")
    return {
        "schema_version": 1,
        "owners": [
            dict(replacement) if row["owner_sequence_id"] == owner_id else dict(row)
            for row in current["owners"]
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--owner", choices=OWNER_IDS,
        help="Refresh only this owner while preserving all other generated rows.",
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        help=(
            "Read memory-knowledge implementation sources from this checkout "
            "while preserving their canonical contract paths."
        ),
    )
    args = parser.parse_args()
    if args.owner:
        current = _read_json(args.output)
        replacement = materialize(
            owner_ids=(args.owner,), source_root=args.source_root
        )["owners"][0]
        document = merge_selected_owner(current, replacement)
    else:
        document = materialize(source_root=args.source_root)
    payload = canonical_bytes(document)
    if args.check:
        if not args.output.is_file() or args.output.read_bytes() != payload:
            raise SystemExit("owner-executable-contracts-drift")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(payload)
    print(json.dumps({
        "ok": True,
        "owners": len(document["owners"]),
        "sha256": sha256_bytes(payload),
        "output": str(args.output),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
