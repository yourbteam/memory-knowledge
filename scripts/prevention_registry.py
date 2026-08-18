#!/usr/bin/env python3
"""Validated sequence-owner registry with a Markdown compatibility projection."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

try:
    from scripts import prevention_adapters
    from scripts.prevention_contract import (
        AvailabilityPolicy,
        OwnerRegistry,
        RecurrencePolicy,
        canonical_bytes,
        require_exact_keys,
        require_id,
        require_sha256,
        sha256_bytes,
    )
except ModuleNotFoundError:  # direct script execution
    import prevention_adapters
    from prevention_contract import (
        AvailabilityPolicy,
        OwnerRegistry,
        RecurrencePolicy,
        canonical_bytes,
        require_exact_keys,
        require_id,
        require_sha256,
        sha256_bytes,
    )


ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_REGISTRY = ROOT / "operations/sequences/SEQUENCES.md"
MIGRATION_MANIFEST = ROOT / "Tasks/prevention-system-completion/owner-migration-manifest.json"
OWNER_CONTRACTS = ROOT / "Tasks/prevention-system-completion/owner-contracts.json"
EXECUTABLE_OWNER_CONTRACTS = (
    ROOT / "Tasks/prevention-system-completion/owner-executable-contracts.json"
)
OWNER_CONTRACT_PROPOSALS = (
    ROOT / "Tasks/prevention-system-completion/owner-contract-proposals"
)
TERMINAL_RESEARCH_CANDIDATE_SHA256 = "b01a93931fc4b67edc97dced6ecbb8d3e86ac08f3df0e9feae41eaf67633f1a6"
TERMINAL_AVAILABLE_CONTRACT_MAP_SHA256 = "a87b2b76d50f5aecd0a0d4085efd08361215746efa5d4bd8366313ade7bc426c"
TERMINAL_OWNER_STATES = {
    AvailabilityPolicy.AVAILABLE: frozenset({
        "claude-auth-token-refresh", "commit-push-main", "convergence-checkpoint-run",
        "convergence-state-review-cycle", "discovery-bootstrap",
        "discovery-candidate-reconciliation", "discovery-promotion-lifecycle",
        "greenfield-full-drive", "local-workflow-orch-image", "mawf-playbook-blocker-reentry",
    }),
    AvailabilityPolicy.CUSTODIAN_EVIDENCE_REQUIRED: frozenset({
        "callcenter-harness-provision-verify", "github-app-repos-refresh",
        "mawf-playbook-full-test", "mawf-playbook-speed-test",
        "remote-mcp-user-onboarding", "scoped-context-edit",
    }),
    AvailabilityPolicy.UNAVAILABLE: frozenset({
        "airgapped-llm-judge", "airgapped-local-bulgarian-stt", "airgapped-redaction-stack",
        "callcenter-harness-engine-invariants", "secure-landing-seed", "taggable-admin-spa-deploy",
        "taggable-api-deploy", "taggable-media-worker-deploy", "taggable-source-reload",
    }),
}
# The available implementations are all invoked through the intercepted Bash
# host boundary. This is deliberately per-owner and closed: no owner-kind
# fallback may silently make a new action class eligible.
REGISTERED_HOST_ACTION_CLASSES = {
    sequence_id: frozenset({"BASH"})
    for sequence_id in TERMINAL_OWNER_STATES[AvailabilityPolicy.AVAILABLE]
}
RESEARCH_CONTRACT_FIELDS = {
    "parameter_schema", "canonical_call", "action_class", "full_unit_budget",
    "effect_identity", "reconciliation_rule", "terminal_schema", "recurrence_policy",
    "availability_policy", "implementation_source_sha256", "evidence_id",
}
AVAILABLE_CONTRACT_KEYS = {
    "sequence_id", "owner_sequence_id", "owner_contract_sha256", "implementation_source",
    "implementation_source_sha256", "parameter_schema", "canonical_call", "action_class",
    "full_unit_budget", "effect_identity", "reconciliation_rule", "terminal_schema",
    "recurrence_policy", "availability_policy", "evidence_id",
}
UNAVAILABLE_CONTRACT_KEYS = {
    "sequence_id", "availability_policy", "implementation_source_status",
    "implementation_source", "implementation_source_sha256", "evidence_id", "reason",
}


class RegistryError(ValueError):
    """Raised when the typed registry and its human projection diverge."""


def _source_validation_path(path: str, sequence_id: str) -> Path:
    source = Path(path)
    source_root = os.environ.get("MK_PREVENTION_SOURCE_ROOT")
    canonical_root = os.environ.get("MK_PREVENTION_CANONICAL_ROOT")
    selected = frozenset(
        value for value in os.environ.get(
            "MK_PREVENTION_SOURCE_ROOT_OWNER_IDS", ""
        ).split(",") if value
    )
    if source_root and canonical_root and (not selected or sequence_id in selected):
        try:
            return Path(source_root) / source.relative_to(Path(canonical_root))
        except ValueError:
            pass
    return source


def load_executable_owner_contracts(
    path: Path = EXECUTABLE_OWNER_CONTRACTS,
    *,
    proposals_dir: Path = OWNER_CONTRACT_PROPOSALS,
    source_validation_owner_ids: frozenset[str] | None = None,
) -> tuple[dict[str, dict[str, Any]], str]:
    """Load the ten approved execution contracts without changing availability."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistryError("invalid-executable-owner-contracts-document") from exc
    require_exact_keys(
        raw, {"schema_version", "owners"}, label="executable-owner-contracts"
    )
    if raw["schema_version"] != 1 or not isinstance(raw["owners"], list):
        raise RegistryError("invalid-executable-owner-contracts-version-or-rows")
    if len(raw["owners"]) != 10:
        raise RegistryError("executable-owner-contract-cardinality")
    result: dict[str, dict[str, Any]] = {}
    for value in raw["owners"]:
        if not isinstance(value, Mapping):
            raise RegistryError("executable-owner-contract-row-not-object")
        sequence_id = require_id(value.get("owner_sequence_id"), label="owner-sequence-id")
        if sequence_id in result:
            raise RegistryError("duplicate-executable-owner-contract-row")
        if (
            sequence_id not in TERMINAL_OWNER_STATES[AvailabilityPolicy.AVAILABLE]
            or value.get("availability_policy") != AvailabilityPolicy.AVAILABLE.value
        ):
            raise RegistryError(f"executable-owner-availability-drift:{sequence_id}")
        stored_hash = require_sha256(
            value.get("owner_contract_sha256"), label="executable-owner-contract-sha256"
        )
        payload = {key: item for key, item in value.items() if key != "owner_contract_sha256"}
        if sha256_bytes(canonical_bytes(payload)) != stored_hash:
            raise RegistryError(f"executable-owner-contract-hash-drift:{sequence_id}")
        proposal_path = proposals_dir / f"{sequence_id}.json"
        try:
            proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RegistryError(f"executable-owner-proposal-invalid:{sequence_id}") from exc
        if sha256_bytes(canonical_bytes(proposal)) != require_sha256(
            value.get("approved_proposal_sha256"), label="approved-proposal-sha256"
        ):
            raise RegistryError(f"executable-owner-proposal-hash-drift:{sequence_id}")
        sources = value.get("implementation_sources")
        if not isinstance(sources, list) or not sources:
            raise RegistryError(f"executable-owner-source-binding-missing:{sequence_id}")
        for source in sources:
            if not isinstance(source, Mapping) or set(source) not in (
                {"path", "sha256"},
                {
                    "path", "sha256", "approved_pre_correction_sha256",
                    "approved_post_correction_sha256", "source_correction_decision_id",
                },
            ):
                raise RegistryError(f"executable-owner-source-binding-invalid:{sequence_id}")
            if "approved_pre_correction_sha256" in source:
                require_sha256(
                    source["approved_pre_correction_sha256"],
                    label="approved-pre-correction-source-sha256",
                )
                if source["approved_post_correction_sha256"] != source["sha256"]:
                    raise RegistryError(
                        f"executable-owner-source-correction-drift:{sequence_id}"
                    )
                require_sha256(
                    source["approved_post_correction_sha256"],
                    label="approved-post-correction-source-sha256",
                )
                if source["source_correction_decision_id"] not in value.get(
                    "authority_decision_ids", []
                ):
                    raise RegistryError(
                        f"executable-owner-source-correction-unapproved:{sequence_id}"
                    )
            if (
                source_validation_owner_ids is None
                or sequence_id in source_validation_owner_ids
            ):
                source_path = _source_validation_path(
                    str(source["path"]), sequence_id
                )
                if (
                    not source_path.is_file()
                    or sha256_bytes(source_path.read_bytes())
                    != require_sha256(
                        source["sha256"], label="implementation-source-sha256"
                    )
                ):
                    raise RegistryError(
                        f"executable-owner-source-hash-drift:{sequence_id}"
                    )
        for contract_name in (
            "budget_contract", "parameter_contract", "reconciliation_contract",
            "terminal_contract", "trusted_roots",
        ):
            if not isinstance(value.get(contract_name), Mapping):
                raise RegistryError(
                    f"executable-owner-contract-section-missing:{sequence_id}:{contract_name}"
                )
        reconciler = value["reconciliation_contract"].get("handler")
        if not isinstance(reconciler, str) or not callable(
            prevention_adapters.__dict__.get(reconciler)
        ):
            raise RegistryError(f"executable-owner-reconciler-missing:{sequence_id}")
        terminal_verifier = value["terminal_contract"].get("handler")
        if not isinstance(terminal_verifier, str) or not callable(
            prevention_adapters.__dict__.get(terminal_verifier)
        ):
            raise RegistryError(f"executable-owner-terminal-verifier-missing:{sequence_id}")
        result[sequence_id] = dict(value)
    if set(result) != TERMINAL_OWNER_STATES[AvailabilityPolicy.AVAILABLE]:
        raise RegistryError("executable-owner-contract-membership-drift")
    return result, sha256_bytes(canonical_bytes(raw))


def load_owner_contracts(path: Path = OWNER_CONTRACTS) -> tuple[dict[str, dict[str, Any]], str]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistryError("invalid-owner-contracts-document") from exc
    if not isinstance(raw, Mapping):
        raise RegistryError("owner-contracts-not-object")
    require_exact_keys(raw, {"schema_version", "research_candidate_sha256", "owners"}, label="owner-contracts")
    if raw["schema_version"] != 1 or not isinstance(raw["owners"], list):
        raise RegistryError("invalid-owner-contracts-version-or-rows")
    require_sha256(raw["research_candidate_sha256"], label="research-candidate-sha256")
    if raw["research_candidate_sha256"] != TERMINAL_RESEARCH_CANDIDATE_SHA256:
        raise RegistryError("research-candidate-hash-drift")
    if len(raw["owners"]) != 25:
        raise RegistryError("owner-contract-state-cardinality")
    result: dict[str, dict[str, Any]] = {}
    counts = {policy.value: 0 for policy in AvailabilityPolicy}
    for value in raw["owners"]:
        if not isinstance(value, Mapping):
            raise RegistryError("owner-contract-row-not-object")
        sequence_id = require_id(value.get("sequence_id"), label="sequence-id")
        if sequence_id in result:
            raise RegistryError("duplicate-owner-contract-row")
        try:
            availability = AvailabilityPolicy(value.get("availability_policy"))
        except ValueError as exc:
            raise RegistryError(f"invalid-owner-availability:{sequence_id}") from exc
        counts[availability.value] += 1
        if availability == AvailabilityPolicy.AVAILABLE:
            require_exact_keys(value, AVAILABLE_CONTRACT_KEYS, label=f"available-owner:{sequence_id}")
            if value["owner_sequence_id"] != sequence_id:
                raise RegistryError(f"owner-sequence-id-drift:{sequence_id}")
            if RecurrencePolicy(value["recurrence_policy"]) != RecurrencePolicy.RECURRENT:
                raise RegistryError(f"available-owner-not-recurrent:{sequence_id}")
            for field in (
                "implementation_source", "canonical_call", "action_class", "full_unit_budget",
                "effect_identity", "reconciliation_rule", "evidence_id",
            ):
                if not isinstance(value[field], str) or not value[field]:
                    raise RegistryError(f"invalid-materialized-field:{sequence_id}:{field}")
            if not isinstance(value["parameter_schema"], Mapping) or not isinstance(value["terminal_schema"], Mapping):
                raise RegistryError(f"invalid-materialized-schema:{sequence_id}")
            # This document is the immutable availability decision, not the
            # executable-admission contract.  Preserve and validate its
            # historical source identity here; the materialized executable
            # contract below binds and verifies the current source bytes.
            require_sha256(
                value["implementation_source_sha256"],
                label="availability-implementation-source-sha256",
            )
            stored_contract_hash = require_sha256(value["owner_contract_sha256"], label="owner-contract-sha256")
            contract_payload = {key: item for key, item in value.items() if key != "owner_contract_sha256"}
            if sha256_bytes(canonical_bytes(contract_payload)) != stored_contract_hash:
                raise RegistryError(f"owner-contract-hash-drift:{sequence_id}")
        else:
            require_exact_keys(value, UNAVAILABLE_CONTRACT_KEYS, label=f"unavailable-owner:{sequence_id}")
            if not isinstance(value["reason"], str) or not value["reason"]:
                raise RegistryError(f"missing-unavailable-reason:{sequence_id}")
        result[sequence_id] = dict(value)
    if counts != {"AVAILABLE": 10, "UNAVAILABLE": 9, "CUSTODIAN_EVIDENCE_REQUIRED": 6}:
        raise RegistryError(f"owner-contract-state-count-drift:{counts}")
    actual_states = {
        policy: frozenset(
            sequence_id for sequence_id, row in result.items()
            if row["availability_policy"] == policy.value
        )
        for policy in AvailabilityPolicy
    }
    if actual_states != TERMINAL_OWNER_STATES:
        raise RegistryError("owner-contract-state-membership-drift")
    available_contract_map = {
        sequence_id: {key: row[key] for key in RESEARCH_CONTRACT_FIELDS}
        for sequence_id, row in result.items()
        if row["availability_policy"] == AvailabilityPolicy.AVAILABLE.value
    }
    if sha256_bytes(canonical_bytes(available_contract_map)) != TERMINAL_AVAILABLE_CONTRACT_MAP_SHA256:
        raise RegistryError("available-owner-contract-research-drift")
    return result, sha256_bytes(canonical_bytes(raw))


def parse_markdown_projection(
    path: Path, *, allow_empty_legacy_fixture: bool = False
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 7:
            if allow_empty_legacy_fixture:
                continue
            raise RegistryError("invalid-markdown-registry-row")
        rows.append({
            "sequence_id": cells[0].strip("`"),
            "use_when": cells[1],
            "folder": cells[2].strip("`"),
            "automation": cells[3],
            "pass_signal": cells[4],
            "operation_kinds": cells[5].strip("`"),
            "lineage_id": cells[6].strip("`"),
        })
    if (not rows and not allow_empty_legacy_fixture) or len({row["sequence_id"] for row in rows}) != len(rows):
        raise RegistryError("invalid-markdown-registry-cardinality")
    return rows


def load_typed_registry(
    *, root: Path = ROOT, manifest_path: Path | None = None, markdown_path: Path | None = None,
    source_validation_owner_ids: frozenset[str] | None = None,
) -> tuple[list[dict[str, Any]], str]:
    manifest_path = manifest_path or root / MIGRATION_MANIFEST.relative_to(ROOT)
    markdown_path = markdown_path or root / MARKDOWN_REGISTRY.relative_to(ROOT)
    owners = OwnerRegistry.load(manifest_path, repository_root=root)
    contract_path = root / OWNER_CONTRACTS.relative_to(ROOT)
    contracts, contracts_hash = load_owner_contracts(contract_path)
    executable_contracts, executable_contracts_hash = load_executable_owner_contracts(
        root / EXECUTABLE_OWNER_CONTRACTS.relative_to(ROOT),
        proposals_dir=root / OWNER_CONTRACT_PROPOSALS.relative_to(ROOT),
        source_validation_owner_ids=source_validation_owner_ids,
    )
    if set(contracts) != {owner.sequence_id for owner in owners.rows}:
        raise RegistryError("owner-contract-manifest-sequence-set-drift")
    projection = parse_markdown_projection(markdown_path)
    projected_by_id = {row["sequence_id"]: row for row in projection}
    owner_ids = {owner.sequence_id for owner in owners.rows}
    if not owner_ids.issubset(projected_by_id):
        raise RegistryError("typed-markdown-sequence-set-drift")
    rows: list[dict[str, Any]] = []
    for owner in owners.rows:
        human = projected_by_id[owner.sequence_id]
        lineage_id = owners.lineage_ids[owner.sequence_id]
        materialized = dict(contracts[owner.sequence_id])
        executable = executable_contracts.get(owner.sequence_id)
        # Every row in this registry describes a repeatable operational sequence.
        # Availability is independent: unavailable rows remain recurrent but fail closed.
        materialized.setdefault("recurrence_policy", RecurrencePolicy.RECURRENT.value)
        materialized["registered_host_action_classes"] = sorted(
            REGISTERED_HOST_ACTION_CLASSES.get(owner.sequence_id, frozenset())
        )
        if human["lineage_id"] != lineage_id:
            raise RegistryError(f"lineage-drift:{owner.sequence_id}")
        if executable is not None:
            materialized["availability_contract_sha256"] = materialized["owner_contract_sha256"]
            materialized["owner_contract_sha256"] = executable["owner_contract_sha256"]
            materialized["executable_contract"] = executable
            materialized["executable_contract_sha256"] = executable["owner_contract_sha256"]
        else:
            materialized["executable_contract"] = None
            materialized["executable_contract_sha256"] = None
        rows.append({
            **human,
            "schema_version": 1,
            "owner_kind": owner.owner_kind.value,
            "handler": owner.handler,
            "parameter_contract": owner.parameter_contract,
            "argv_contract": owner.argv_contract,
            "effect_identity_contract": owner.effect_identity_contract,
            "effect_reconciler": owner.reconciler,
            "terminal_contract": owner.terminal_contract,
            "repository_keys": list(owner.repository_keys),
            "standalone": owner.standalone,
            "parent_sequence_ids": list(owner.parent_sequence_ids),
            "evidence_pointer": owner.evidence_pointer,
            "source_inventory_sha256": owners.source_inventory_sha256,
            **materialized,
        })
    registry_hash = sha256_bytes(canonical_bytes({
        "schema_version": 1,
        "owner_contracts_sha256": contracts_hash,
        "executable_owner_contracts_sha256": executable_contracts_hash,
        "rows": rows,
    }))
    return rows, registry_hash


def _merge_runtime_projection(
    typed_rows: list[dict[str, Any]], projection: list[dict[str, str]],
    typed_registry_hash: str,
) -> tuple[list[dict[str, Any]], str]:
    """Keep owner admission typed while retaining promoted non-owner sequences."""
    owner_ids = {row["sequence_id"] for row in typed_rows}
    promoted_rows = [row for row in projection if row["sequence_id"] not in owner_ids]
    rows = [*typed_rows, *promoted_rows]
    return rows, sha256_bytes(canonical_bytes({
        "schema_version": 1,
        "typed_owner_registry_sha256": typed_registry_hash,
        "promoted_sequence_rows": promoted_rows,
    }))


def legacy_fixture_rows(
    path: Path, *, governance_level: str,
) -> tuple[list[dict[str, Any]], str]:
    """Explicit, non-runtime adapter for isolated legacy test/diagnostic fixtures."""
    if governance_level != "UNGOVERNED_DIAGNOSTIC":
        raise RegistryError("legacy-registry-requires-ungoverned-diagnostic-capability")
    rows = parse_markdown_projection(path, allow_empty_legacy_fixture=True)
    return rows, sha256_bytes(path.read_bytes())


def registry_rows(
    path: Path | None = None, *, selected_sequence_id: str | None = None
) -> tuple[list[dict[str, Any]], str]:
    """Return typed owners plus validated promoted non-owner sequence rows."""
    if path is None:
        selected = MARKDOWN_REGISTRY
        repository_root = ROOT
    else:
        selected = path.resolve()
        expected_suffix = Path("operations/sequences/SEQUENCES.md")
        if tuple(selected.parts[-len(expected_suffix.parts):]) != expected_suffix.parts:
            raise RegistryError("explicit-markdown-registry-prohibited")
        repository_root = selected.parents[2]
    typed_rows, typed_hash = load_typed_registry(
        root=repository_root, markdown_path=selected,
        source_validation_owner_ids=(
            frozenset({selected_sequence_id}) if selected_sequence_id else None
        ),
    )
    return _merge_runtime_projection(
        typed_rows, parse_markdown_projection(selected), typed_hash,
    )


def runtime_registry_document(*, root: Path = ROOT) -> dict[str, Any]:
    rows, registry_hash = load_typed_registry(root=root)
    return {"schema_version": 1, "registry_sha256": registry_hash, "rows": rows}


def main() -> int:
    print(json.dumps(runtime_registry_document(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
