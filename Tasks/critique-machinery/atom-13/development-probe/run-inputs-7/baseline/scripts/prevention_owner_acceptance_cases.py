#!/usr/bin/env python3
"""Closed owner/profile acceptance-case registry and contract validator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

try:
    from scripts import prevention_source_probes
    from scripts.prevention_contract import canonical_bytes, sha256_bytes
except ModuleNotFoundError:  # direct script execution
    import prevention_source_probes
    from prevention_contract import canonical_bytes, sha256_bytes


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "Tasks/prevention-system-completion/owner-acceptance-cases.json"

CASE_FIELDS = {
    "case_id", "owner_sequence_id", "profile_id", "effect_class",
    "typed_parameter_fixture_id", "source_executor_id", "external_edge_kind",
    "external_fixture_ids", "proof_applicability",
}
FIXTURE_FIELDS = {
    "positive", "semantic_negative", "not_applied", "already_applied",
    "conflicting_identity",
}
PROOF_FIELDS = {"proof_kind", "applicability"}


class AcceptanceCaseError(ValueError):
    """The checked case registry is incomplete, stale, or caller-shaped."""


def _read_cases(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        document = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise AcceptanceCaseError("owner-acceptance-case-registry-unavailable") from exc
    if (
        not isinstance(document, dict)
        or set(document) != {"schema_version", "rows"}
        or document.get("schema_version") != 1
        or not isinstance(document.get("rows"), list)
    ):
        raise AcceptanceCaseError("owner-acceptance-case-registry-invalid")
    return document, canonical_bytes(document)


def load_case_registry(
    owners: list[Mapping[str, Any]], path: Path = CASES,
) -> tuple[list[dict[str, Any]], str]:
    document, raw = _read_cases(path)
    contracts = {
        str(owner.get("owner_sequence_id")): owner for owner in owners
        if isinstance(owner, Mapping)
    }
    expected: dict[tuple[str, str], Mapping[str, Any]] = {}
    for owner_id, owner in contracts.items():
        acceptance_rows = owner.get("acceptance_proofs")
        if not isinstance(acceptance_rows, list):
            raise AcceptanceCaseError("owner-acceptance-proof-contract-invalid")
        for row in acceptance_rows:
            if not isinstance(row, Mapping):
                raise AcceptanceCaseError("owner-acceptance-proof-contract-invalid")
            expected[(owner_id, str(row.get("profile_id")))] = row
    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    for raw_row in document["rows"]:
        if not isinstance(raw_row, Mapping) or set(raw_row) != CASE_FIELDS:
            raise AcceptanceCaseError("owner-acceptance-case-row-invalid")
        row = dict(raw_row)
        owner_id = row.get("owner_sequence_id")
        profile_id = row.get("profile_id")
        key = (str(owner_id), str(profile_id))
        if key in indexed or key not in expected:
            raise AcceptanceCaseError("owner-acceptance-case-set-invalid")
        if row.get("case_id") != f"{owner_id}/{profile_id}/v1":
            raise AcceptanceCaseError("owner-acceptance-case-id-invalid")
        if row.get("typed_parameter_fixture_id") != (
            f"{owner_id}/{profile_id}/parameters-v1"
        ) or row.get("source_executor_id") != f"{owner_id}/real-source-v1":
            raise AcceptanceCaseError("owner-acceptance-case-binding-invalid")
        spec = prevention_source_probes.PROVIDER_SPECS.get(key)
        if spec is None or row.get("external_edge_kind") != spec.edge_kind.value:
            raise AcceptanceCaseError("owner-acceptance-case-edge-invalid")
        fixtures = row.get("external_fixture_ids")
        if (
            not isinstance(fixtures, Mapping) or set(fixtures) != FIXTURE_FIELDS
            or any(
                fixtures[name] != f"{owner_id}/{profile_id}/{name.replace('_', '-')}-v1"
                for name in FIXTURE_FIELDS
            )
        ):
            raise AcceptanceCaseError("owner-acceptance-external-fixtures-invalid")
        proofs = row.get("proof_applicability")
        contract_proofs = expected[key].get("proofs")
        if not isinstance(proofs, list) or not isinstance(contract_proofs, list):
            raise AcceptanceCaseError("owner-acceptance-applicability-invalid")
        if any(
            not isinstance(proof, Mapping) or set(proof) != PROOF_FIELDS
            for proof in proofs
        ):
            raise AcceptanceCaseError("owner-acceptance-applicability-invalid")
        actual = {
            (proof["proof_kind"], proof["applicability"]) for proof in proofs
        }
        required = {
            (proof["proof_kind"], proof["applicability"])
            for proof in contract_proofs if isinstance(proof, Mapping)
        }
        if len(actual) != len(proofs) or actual != required:
            raise AcceptanceCaseError("owner-acceptance-applicability-drift")
        non_mutating = any(
            proof["applicability"] == "NOT_APPLICABLE" for proof in proofs
        )
        if row.get("effect_class") != (
            "NON_MUTATING" if non_mutating else "MUTATION"
        ):
            raise AcceptanceCaseError("owner-acceptance-effect-class-drift")
        indexed[key] = row
    if set(indexed) != set(expected) or len(indexed) != 44:
        raise AcceptanceCaseError("owner-acceptance-case-set-incomplete")
    return [indexed[key] for key in sorted(indexed)], sha256_bytes(raw)
