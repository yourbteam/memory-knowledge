#!/usr/bin/env python3
"""Closed, typed argv adapters for the frozen prevention owner registry."""

from __future__ import annotations

import json
import hmac
import secrets
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

try:
    from scripts import sequence_candidate_contract, work_memory
    from scripts.prevention_contract import (
        ActionIntent, BindingKind, BindingReceipt, ParameterTag, canonical_bytes,
        resolve_repository_source_path, sha256_bytes,
    )
except ModuleNotFoundError:  # direct script execution
    import sequence_candidate_contract
    import work_memory
    from prevention_contract import (
        ActionIntent, BindingKind, BindingReceipt, ParameterTag, canonical_bytes,
        resolve_repository_source_path, sha256_bytes,
    )


class AdapterError(ValueError):
    """Fail-closed owner adapter error; never falls back to reconstructed shell."""


_POLICY_EVIDENCE_KEY = secrets.token_bytes(32)
ROOT = Path(__file__).resolve().parents[1]
CANONICAL_ROOT = Path.home() / "memory-knowledge"


@dataclass(frozen=True)
class InvocationPlan:
    sequence_id: str
    argv: tuple[str, ...]
    owner_contract_sha256: str
    implementation_source_sha256: str
    parameter_schema_sha256: str
    resolved_parameters: Mapping[str, Any]
    root_bindings: Mapping[str, str]
    binding_receipts: Mapping[str, BindingReceipt]
    effect_context_binding: str = "UNAVAILABLE"
    preparation_context_binding: str = "UNAVAILABLE"


@dataclass(frozen=True)
class ResolvedParameters:
    values: Mapping[str, Any]
    argv_values: Mapping[str, Any]
    schema_sha256: str
    root_bindings: Mapping[str, str]
    binding_receipts: Mapping[str, BindingReceipt]


@dataclass(frozen=True)
class BindingRequest:
    intent: ActionIntent
    owner_sequence_id: str
    owner_contract_sha256: str
    parameter_name: str
    parameter_type: str
    provider_id: str
    key_or_resource_id: str
    version_id: str | None
    expected_scope_sha256: str
    consumable: bool


@dataclass(frozen=True)
class BindingResolution:
    receipt: BindingReceipt
    execution_value: Any


class BindingProvider(Protocol):
    def resolve(self, request: BindingRequest) -> BindingResolution: ...


class ObservationTransport(Protocol):
    def query(self, request: Mapping[str, Any]) -> Mapping[str, Any]: ...


class SourceProbeBackend(Protocol):
    """Trusted read-only edge used by the finite source observation transport."""

    def observe_identity(self, request: Mapping[str, Any]) -> str: ...
    def observe_ownership(self, request: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def observe_prestate(self, request: Mapping[str, Any]) -> str: ...
    def observe_receipt(self, request: Mapping[str, Any]) -> str: ...
    def observe_work_state(self, request: Mapping[str, Any]) -> str: ...
    def observe_probe(self, request: Mapping[str, Any], probe_id: str) -> str: ...


class SourceObservationTransport:
    """Explicit test transport for already-classified fixture captures."""

    def __init__(self, backend: SourceProbeBackend):
        self.backend = backend

    def query(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        required = {
            "effect_id", "owner_sequence_id", "preparation_artifact_sha256",
            "observation_targets", "prepared_prestate_identities",
            "prepared_receipt_identities",
            "profile", "probe_ids", "provider_symbol", "source_evidence_sha256",
        }
        if not isinstance(request, Mapping) or set(request) != required:
            raise AdapterError("source-observation-request-fields-invalid")
        probes = request.get("probe_ids")
        if (
            not isinstance(probes, list) or not probes
            or any(not isinstance(probe, str) or not probe for probe in probes)
            or len(probes) != len(set(probes))
        ):
            raise AdapterError("source-observation-probe-set-invalid")
        capture = {
            "identity": self.backend.observe_identity(request),
            "observed_at_utc": datetime.now(UTC).isoformat(),
            "ownership": self.backend.observe_ownership(request),
            "prestate": self.backend.observe_prestate(request),
            "probes": {
                probe: self.backend.observe_probe(request, probe) for probe in probes
            },
            "receipt": self.backend.observe_receipt(request),
            "source_evidence_sha256": request["source_evidence_sha256"],
            "work_state": self.backend.observe_work_state(request),
        }
        # Timestamp, evidence hash, and probe ids are transport-owned. Ownership is
        # backend-supplied so the observer must prove it from the source state.
        return capture


def _normalize_production_capture(
    capture: Mapping[str, Any], *, request: Mapping[str, Any], label: str,
) -> Mapping[str, Any]:
    if set(capture) != {
        "schema_version", "transport_kind", "observed_at_utc",
        "raw_source_facts", "source_evidence_sha256",
    } or capture.get("schema_version") != 1 or capture.get(
        "transport_kind"
    ) != "PRODUCTION_SOURCE_PROBE":
        raise AdapterError(f"{label}-production-capture-envelope-invalid")
    raw = capture.get("raw_source_facts")
    if not isinstance(raw, Mapping) or set(raw) != {
        "identity", "ownership", "prestate", "probes", "receipt", "work_state",
    }:
        raise AdapterError(f"{label}-production-source-facts-invalid")

    def hash_fact(name: str, *, allow_absent: bool = False) -> str:
        fact = raw.get(name)
        expected = {"expected_sha256", "observed_sha256", "known"}
        if allow_absent:
            expected.add("absent")
        if not isinstance(fact, Mapping) or set(fact) != expected:
            raise AdapterError(f"{label}-production-{name}-fact-invalid")
        if fact.get("known") is not True:
            return "UNKNOWN"
        if allow_absent and fact.get("absent") is True:
            return "ABSENT"
        expected_hash = fact.get("expected_sha256")
        observed_hash = fact.get("observed_sha256")
        if (
            not isinstance(expected_hash, str) or len(expected_hash) != 64
            or not isinstance(observed_hash, str) or len(observed_hash) != 64
        ):
            raise AdapterError(f"{label}-production-{name}-hash-invalid")
        return "SATISFIED" if expected_hash == observed_hash else "CONFLICT"

    identity_result = hash_fact("identity")
    prestate_result = hash_fact("prestate")
    receipt = raw.get("receipt")
    if not isinstance(receipt, Mapping) or set(receipt) != {
        "present", "known", "effect_id", "preparation_artifact_sha256",
    }:
        raise AdapterError(f"{label}-production-receipt-fact-invalid")
    if receipt.get("known") is not True:
        receipt_result = "UNKNOWN"
    elif receipt.get("present") is False:
        receipt_result = "ABSENT"
    elif receipt.get("present") is True and (
        receipt.get("effect_id") == request["effect_id"]
        and receipt.get("preparation_artifact_sha256")
        == request["preparation_artifact_sha256"]
    ):
        receipt_result = "PRESENT"
    else:
        receipt_result = "CONFLICT"
    work = raw.get("work_state")
    if (
        not isinstance(work, Mapping) or set(work) != {"terminal", "detached"}
        or type(work.get("terminal")) is not bool
        or type(work.get("detached")) is not bool
        or work["terminal"] == work["detached"]
    ):
        raise AdapterError(f"{label}-production-work-state-fact-invalid")
    probes = raw.get("probes")
    if not isinstance(probes, Mapping) or set(probes) != set(request["probe_ids"]):
        raise AdapterError(f"{label}-production-probe-facts-invalid")
    normalized_probes = {}
    for probe_id, fact in probes.items():
        if not isinstance(fact, Mapping):
            raise AdapterError(f"{label}-production-probe-fact-invalid:{probe_id}")
        normalized_probes[probe_id] = hash_fact_from_value(
            fact, label=label, probe_id=probe_id
        )
    return {
        "identity": "MATCH" if identity_result == "SATISFIED" else "CONFLICT",
        "observed_at_utc": capture["observed_at_utc"],
        "ownership": raw["ownership"],
        "prestate": (
            "MATCH" if prestate_result == "SATISFIED"
            else "CHANGED" if prestate_result == "CONFLICT" else "UNKNOWN"
        ),
        "probes": normalized_probes,
        "receipt": receipt_result,
        "source_evidence_sha256": capture["source_evidence_sha256"],
        "work_state": "TERMINAL" if work["terminal"] else "DETACHED",
        "production_raw_source_facts_sha256": sha256_bytes(canonical_bytes(raw)),
    }


def hash_fact_from_value(
    fact: Mapping[str, Any], *, label: str, probe_id: str,
) -> str:
    if set(fact) != {"expected_sha256", "observed_sha256", "known", "absent"}:
        raise AdapterError(f"{label}-production-probe-fact-invalid:{probe_id}")
    if fact.get("known") is not True:
        return "UNKNOWN"
    if fact.get("absent") is True:
        return "ABSENT"
    expected = fact.get("expected_sha256")
    observed = fact.get("observed_sha256")
    if (
        not isinstance(expected, str) or len(expected) != 64
        or not isinstance(observed, str) or len(observed) != 64
    ):
        raise AdapterError(f"{label}-production-probe-hash-invalid:{probe_id}")
    return "SATISFIED" if expected == observed else "CONFLICT"


OBSERVABLE_EVIDENCE = (
    Path(__file__).resolve().parents[1]
    / "Tasks/prevention-system-completion/owner-observable-evidence.json"
)


class TrustedBindingProvider:
    """Closed resolver registry: local repositories plus declared external providers."""

    def __init__(
        self, *, repository_roots: Mapping[str, str] | None = None,
        external: BindingProvider | None = None,
    ):
        self.repository_roots = dict(repository_roots) if repository_roots is not None else None
        self.external = external

    def resolve(self, request: BindingRequest) -> BindingResolution:
        if (
            request.provider_id == "repository-registry"
            and request.parameter_name == "repository_key"
            and request.parameter_type in {"ENUM_FROM_REGISTRY", "REPOSITORY_KEY"}
        ):
            try:
                roots = work_memory._repo_roots(snapshot=self.repository_roots)
            except (OSError, ValueError, work_memory.WorkMemoryError) as exc:
                raise AdapterError("local-repository-registry-invalid") from exc
            root = roots.get(request.key_or_resource_id)
            if root is None:
                raise AdapterError(
                    f"local-repository-key-unregistered:{request.key_or_resource_id}"
                )
            resolved = str(root.resolve())
            version = sha256_bytes(canonical_bytes({
                key: str(value.resolve()) for key, value in sorted(roots.items())
            }))
            fingerprint = sha256_bytes(canonical_bytes(resolved))
            receipt_id = sha256_bytes(canonical_bytes({
                "provider_id": request.provider_id,
                "key": request.key_or_resource_id,
                "version_id": version,
                "scope_sha256": request.expected_scope_sha256,
            }))
            return BindingResolution(
                receipt=BindingReceipt(
                    receipt_id=receipt_id, binding_kind=BindingKind.REPOSITORY,
                    provider_id=request.provider_id,
                    key_or_resource_id=request.key_or_resource_id,
                    version_id=version, scope_sha256=request.expected_scope_sha256,
                    value_fingerprint_sha256=fingerprint, consumable=False,
                ),
                execution_value=resolved,
            )
        if self.external is None:
            raise AdapterError(f"binding-provider-required:{request.parameter_name}")
        return self.external.resolve(request)


@dataclass(frozen=True)
class ReconciliationObservation:
    owner_sequence_id: str
    effect_id: str
    reconciliation_policy_sha256: str
    preparation_artifact_sha256: str
    provider_id: str
    observed_at_utc: str
    raw_result: Mapping[str, str]
    observable_ownership: Mapping[str, Any]
    evidence: Mapping[str, Any]


@dataclass(frozen=True)
class ReconciliationDecision:
    classification: str
    observable_ownership_sha256: str
    evidence_sha256: str
    artifact: Mapping[str, Any]


@dataclass(frozen=True)
class TerminalObservation:
    owner_sequence_id: str
    effect_id: str
    result_kind: str
    terminal_policy_sha256: str
    preparation_artifact_sha256: str
    provider_id: str
    observed_at_utc: str
    raw_result: Mapping[str, str]
    evidence: Mapping[str, Any]


def _validate_raw_observation(
    *, provider_id: str, observed_at_utc: str, raw_result: Mapping[str, str],
    observable_spec: Any, label: str,
) -> None:
    if not isinstance(observable_spec, Mapping) or observable_spec.get("read_only") is not True:
        raise AdapterError(f"{label}-observable-contract-invalid")
    if provider_id != observable_spec.get("provider_symbol"):
        raise AdapterError(f"{label}-observable-provider-mismatch")
    fields = (
        {"identity": ["MATCH", "CONFLICT"],
         "postcondition": ["APPLIED", "NOT_APPLIED"],
         "prepared_prestate": ["UNCHANGED", "CHANGED"],
         "mutation_receipt": ["PRESENT", "ABSENT"]}
        if label == "reconciliation" else
        {"semantic": ["PASS", "FAIL"], "output_schema": ["VALID", "INVALID"],
         "identity": ["MATCH", "CONFLICT"],
         "work_state": ["TERMINAL", "DETACHED"]}
    )
    if not isinstance(raw_result, Mapping):
        raise AdapterError(f"{label}-observable-result-schema-invalid")
    if set(raw_result) != set(fields):
        raise AdapterError(f"{label}-observable-result-fields-invalid")
    if any(
        not isinstance(allowed, list) or raw_result[name] not in allowed
        for name, allowed in fields.items()
    ):
        raise AdapterError(f"{label}-observable-result-enum-invalid")
    try:
        observed = datetime.fromisoformat(observed_at_utc.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise AdapterError(f"{label}-observation-time-invalid") from exc
    if observed.tzinfo is None:
        raise AdapterError(f"{label}-observation-time-invalid")
    age = (datetime.now(UTC) - observed.astimezone(UTC)).total_seconds()
    maximum_age = observable_spec.get("maximum_age_seconds")
    if not isinstance(maximum_age, int) or age < -5 or age > maximum_age:
        raise AdapterError(f"{label}-observation-stale")


def _profile_observable(
    plan: InvocationPlan, contract: Mapping[str, Any], kind: str,
) -> Mapping[str, Any]:
    profile = plan.resolved_parameters.get("command", plan.resolved_parameters.get("mode", "default"))
    matches = [
        item for item in contract.get("observables", [])
        if isinstance(item, Mapping) and item.get("profile") == profile
    ]
    if len(matches) != 1 or not str(matches[0].get("observable_id", "")).endswith(f"/{kind}"):
        raise AdapterError(f"{kind}-observable-profile-unavailable")
    return matches[0]


def _source_observable_evidence_for_owner(
    owner_sequence_id: str, profile: str,
) -> Mapping[str, Any]:
    try:
        document = json.loads(OBSERVABLE_EVIDENCE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AdapterError("source-observable-evidence-unavailable") from exc
    if (
        not isinstance(document, Mapping)
        or document.get("schema_version") != 1
        or document.get("admission_effect")
        != "PROVIDER_IMPLEMENTED_SOURCE_PATH_UNVERIFIED"
    ):
        raise AdapterError("source-observable-evidence-invalid")
    provider = document.get("provider_implementation")
    if not isinstance(provider, Mapping) or not isinstance(provider.get("path"), str):
        raise AdapterError("source-observable-provider-binding-invalid")
    try:
        provider_bytes = resolve_repository_source_path(
            provider["path"],
            repository_root=ROOT,
            canonical_repository_root=CANONICAL_ROOT,
        ).read_bytes()
    except OSError as exc:
        raise AdapterError("source-observable-provider-unavailable") from exc
    if sha256_bytes(provider_bytes) != provider.get("sha256"):
        raise AdapterError("source-observable-provider-drift")
    owners = [
        row for row in document.get("owners", [])
        if isinstance(row, Mapping)
        and row.get("owner_sequence_id") == owner_sequence_id
    ]
    if len(owners) != 1:
        raise AdapterError("source-observable-owner-evidence-unavailable")
    owner = owners[0]
    stored_hash = owner.get("evidence_sha256")
    owner_payload = {key: value for key, value in owner.items() if key != "evidence_sha256"}
    if stored_hash != sha256_bytes(canonical_bytes(owner_payload)):
        raise AdapterError("source-observable-evidence-hash-drift")
    for source in owner.get("sources", []):
        if not isinstance(source, Mapping) or not isinstance(source.get("path"), str):
            raise AdapterError("source-observable-source-binding-invalid")
        path = resolve_repository_source_path(
            source["path"],
            repository_root=ROOT,
            canonical_repository_root=CANONICAL_ROOT,
        )
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise AdapterError("source-observable-source-unavailable") from exc
        if sha256_bytes(raw) != source.get("sha256"):
            raise AdapterError("source-observable-source-drift")
    profiles = [
        row for row in owner.get("profiles", [])
        if isinstance(row, Mapping) and row.get("profile") == profile
    ]
    if len(profiles) != 1:
        raise AdapterError("source-observable-profile-evidence-unavailable")
    return {"owner": owner, "profile": profiles[0]}


def _source_observable_evidence(
    plan: InvocationPlan, profile: str,
) -> Mapping[str, Any]:
    return _source_observable_evidence_for_owner(plan.sequence_id, profile)


def _evaluate_owner_profile_predicate(
    plan: InvocationPlan, contract: Mapping[str, Any], evidence: Mapping[str, Any],
    capture: Mapping[str, Any], *, kind: str,
) -> dict[str, Any]:
    """Bind generic transport facts to one exact materialized owner/profile policy."""
    profile = evidence["profile"].get("profile")
    required_probes = evidence["profile"].get("capture_schema", {}).get("probe_ids")
    clause_ids = contract.get("required_clause_ids")
    probe_results = capture.get("probes") if isinstance(capture, Mapping) else None
    if (
        not isinstance(profile, str) or not profile
        or not isinstance(required_probes, list) or not required_probes
        or any(not isinstance(item, str) or not item for item in required_probes)
        or not isinstance(probe_results, Mapping)
        or set(probe_results) != set(required_probes)
        or not isinstance(clause_ids, list) or not clause_ids
        or any(
            not isinstance(item, str) or len(item) != 64
            for item in clause_ids
        )
    ):
        raise AdapterError(f"{kind}-owner-semantic-predicate-invalid")
    predicate = {
        "owner_sequence_id": plan.sequence_id,
        "profile": profile,
        "kind": kind,
        "required_probe_ids": list(required_probes),
        "required_clause_ids": list(clause_ids),
        "source_evidence_sha256": evidence["owner"]["evidence_sha256"],
        "capture_sha256": sha256_bytes(canonical_bytes(capture)),
        "probe_results_sha256": sha256_bytes(canonical_bytes(probe_results)),
    }
    clause_evaluations = {
        clause_id: sha256_bytes(canonical_bytes({
            "owner_sequence_id": plan.sequence_id,
            "profile": profile,
            "kind": kind,
            "clause_id": clause_id,
            "probe_results": dict(probe_results),
        }))
        for clause_id in clause_ids
    }
    policy_evidence = {
        "profile": profile,
        "owner_semantic_predicate_sha256": sha256_bytes(canonical_bytes(predicate)),
        "evaluated_clause_ids": list(clause_ids),
        "evaluated_probe_ids": list(required_probes),
        "probe_results": dict(probe_results),
        "clause_evaluations": clause_evaluations,
        "capture": dict(capture),
        "source_evidence_sha256": evidence["owner"]["evidence_sha256"],
        "capture_sha256": sha256_bytes(canonical_bytes(capture)),
        "probe_results_sha256": sha256_bytes(canonical_bytes(probe_results)),
    }
    return {
        **policy_evidence,
        "policy_evidence_mac": hmac.new(
            _POLICY_EVIDENCE_KEY, canonical_bytes(policy_evidence), "sha256"
        ).hexdigest(),
    }


def _validate_source_capture(
    capture: Any, *, request: Mapping[str, Any], evidence: Mapping[str, Any],
    label: str,
) -> Mapping[str, Any]:
    production_raw_hash = None
    if isinstance(capture, Mapping) and capture.get("transport_kind") == "PRODUCTION_SOURCE_PROBE":
        capture = _normalize_production_capture(
            capture, request=request, label=label
        )
        production_raw_hash = capture.pop("production_raw_source_facts_sha256")
    profile = evidence["profile"]
    schema = profile.get("capture_schema")
    if not isinstance(schema, Mapping) or schema.get("closed") is not True:
        raise AdapterError(f"{label}-source-capture-schema-invalid")
    expected_fields = {
        "identity", "observed_at_utc", "ownership", "prestate", "probes",
        "receipt", "source_evidence_sha256", "work_state",
    }
    if not isinstance(capture, Mapping) or set(capture) != expected_fields:
        raise AdapterError(f"{label}-capture-fields-invalid")
    if capture.get("source_evidence_sha256") != request["source_evidence_sha256"]:
        raise AdapterError(f"{label}-source-evidence-mismatch")
    for name in ("identity", "prestate", "receipt", "work_state"):
        allowed = schema.get(name)
        if not isinstance(allowed, list) or capture.get(name) not in allowed:
            raise AdapterError(f"{label}-capture-enum-invalid:{name}")
    ownership = capture.get("ownership")
    if (
        not isinstance(ownership, Mapping)
        or set(ownership) != {
            "effect_id", "owner_sequence_id", "preparation_artifact_sha256",
        }
        or any(not isinstance(value, str) or not value for value in ownership.values())
    ):
        raise AdapterError(f"{label}-capture-ownership-invalid")
    probes = capture.get("probes")
    probe_ids = schema.get("probe_ids")
    if (
        not isinstance(probes, Mapping)
        or not isinstance(probe_ids, list)
        or set(probes) != set(probe_ids)
        or any(value not in schema.get("probe_result", []) for value in probes.values())
    ):
        raise AdapterError(f"{label}-capture-probes-invalid")
    if production_raw_hash is None:
        return capture
    return {**capture, "production_raw_source_facts_sha256": production_raw_hash}


def acquire_reconciliation_observation(
    plan: InvocationPlan, state: Mapping[str, Any], preparation: Mapping[str, Any],
    transport: ObservationTransport,
) -> ReconciliationObservation:
    contract = preparation["reconciliation_contract"]
    spec = _profile_observable(plan, contract, "reconciliation")
    profile_name = str(spec["profile"])
    evidence = _source_observable_evidence(plan, profile_name)
    probe_ids = evidence["profile"]["capture_schema"]["probe_ids"]
    request = {
        "effect_id": state["effect_id"], "owner_sequence_id": plan.sequence_id,
        "preparation_artifact_sha256": state["preparation_artifact_sha256"],
        "observation_targets": preparation["observation_targets"],
        "prepared_prestate_identities": preparation["prepared_prestate_identities"],
        "prepared_receipt_identities": preparation["prepared_receipt_identities"],
        "profile": profile_name, "probe_ids": list(probe_ids),
        "provider_symbol": spec["provider_symbol"],
        "source_evidence_sha256": evidence["owner"]["evidence_sha256"],
    }
    capture = _validate_source_capture(
        transport.query(request), request=request, evidence=evidence,
        label="reconciliation",
    )
    ownership = capture.get("ownership")
    expected_ownership = {
        field: request[field] for field in spec["ownership_fields"]
    }
    identity_match = (
        ownership == expected_ownership and capture["identity"] == "MATCH"
    )
    effect_id = state["effect_id"]
    probe_values = set(capture["probes"].values())
    all_satisfied = probe_values == {"SATISFIED"}
    all_absent = probe_values == {"ABSENT"}
    conflict = not (all_satisfied or all_absent)
    raw = {
        "identity": "MATCH" if identity_match and not conflict else "CONFLICT",
        "postcondition": "APPLIED" if all_satisfied else "NOT_APPLIED",
        "prepared_prestate": (
            "UNCHANGED" if capture["prestate"] == "MATCH" else "CHANGED"
        ),
        "mutation_receipt": (
            "ABSENT" if capture["receipt"] == "ABSENT" else "PRESENT"
        ),
    }
    predicate_evidence = _evaluate_owner_profile_predicate(
        plan, contract, evidence, capture, kind="reconciliation"
    )
    return ReconciliationObservation(
        owner_sequence_id=plan.sequence_id, effect_id=effect_id,
        reconciliation_policy_sha256=contract["policy_sha256"],
        preparation_artifact_sha256=state["preparation_artifact_sha256"],
        provider_id=spec["provider_symbol"], observed_at_utc=str(capture["observed_at_utc"]),
        raw_result=raw, observable_ownership=dict(ownership) if isinstance(ownership, Mapping) else {},
        evidence={
            **predicate_evidence,
            **({"production_raw_source_facts_sha256": capture[
                "production_raw_source_facts_sha256"
            ]} if "production_raw_source_facts_sha256" in capture else {}),
        },
    )


def acquire_terminal_observation(
    plan: InvocationPlan, state: Mapping[str, Any], result_kind: str,
    terminal_contract: Mapping[str, Any], transport: ObservationTransport,
) -> TerminalObservation:
    spec = _profile_observable(plan, terminal_contract, "terminal")
    profile_name = str(spec["profile"])
    evidence = _source_observable_evidence(plan, profile_name)
    probe_ids = evidence["profile"]["capture_schema"]["probe_ids"]
    request = {
        "effect_id": state["effect_id"], "owner_sequence_id": plan.sequence_id,
        "preparation_artifact_sha256": state["preparation_artifact_sha256"],
        "observation_targets": state["observation_targets"],
        "prepared_prestate_identities": state["prepared_prestate_identities"],
        "prepared_receipt_identities": state["prepared_receipt_identities"],
        "profile": profile_name, "probe_ids": list(probe_ids),
        "provider_symbol": spec["provider_symbol"],
        "source_evidence_sha256": evidence["owner"]["evidence_sha256"],
    }
    capture = _validate_source_capture(
        transport.query(request), request=request, evidence=evidence,
        label="terminal",
    )
    ownership = capture.get("ownership")
    expected_ownership = {field: request[field] for field in spec["ownership_fields"]}
    effect_id = state["effect_id"]
    semantic_pass = set(capture["probes"].values()) == {"SATISFIED"}
    raw = {
        "semantic": "PASS" if semantic_pass else "FAIL",
        "output_schema": "VALID",
        "identity": (
            "MATCH" if ownership == expected_ownership and capture["identity"] == "MATCH"
            else "CONFLICT"
        ),
        "work_state": capture["work_state"],
    }
    predicate_evidence = _evaluate_owner_profile_predicate(
        plan, terminal_contract, evidence, capture, kind="terminal"
    )
    return TerminalObservation(
        owner_sequence_id=plan.sequence_id, effect_id=effect_id,
        result_kind=result_kind,
        terminal_policy_sha256=terminal_contract["policy_sha256"],
        preparation_artifact_sha256=state["preparation_artifact_sha256"],
        provider_id=spec["provider_symbol"], observed_at_utc=str(capture["observed_at_utc"]),
        raw_result=raw,
        evidence={
            **predicate_evidence,
            **({"production_raw_source_facts_sha256": capture[
                "production_raw_source_facts_sha256"
            ]} if "production_raw_source_facts_sha256" in capture else {}),
        },
    )


_OWNER_OBSERVABLE_PROFILES: Mapping[str, tuple[str, ...]] = {
    "claude-auth-token-refresh": ("all", "mint", "push-kv", "reseed-azure", "seed-host", "seed-local", "status", "verify"),
    "commit-push-main": ("dry-run", "integrate-remote-and-resume", "isolated-integrate-and-resume", "isolated-reconcile-and-resume", "publish", "resume-push"),
    "convergence-checkpoint-run": ("default",),
    "convergence-state-review-cycle": ("apply", "dry-run"),
    "discovery-bootstrap": ("start",),
    "discovery-candidate-reconciliation": ("audit", "drive", "execute", "execute-rolling", "validate"),
    "discovery-promotion-lifecycle": ("correct", "correct-registered", "drive", "status"),
    "greenfield-full-drive": (
        "create-program", "resume-program", "start-from-spec", "validate-fresh",
    ),
    "local-workflow-orch-image": ("build", "copy-code-project", "health", "logs", "probe-codex", "require-real-memory-knowledge", "run", "seed-codex-auth", "seed-git-auth", "stop"),
    "mawf-playbook-blocker-reentry": ("restart-workflow", "resume", "start-over"),
}


def _install_owner_observation_providers() -> None:
    def make_reconciliation(owner_id: str, profile: str):
        def provider(plan, state, preparation, transport):
            actual = plan.resolved_parameters.get(
                "command", plan.resolved_parameters.get("mode", "default")
            )
            if plan.sequence_id != owner_id or actual != profile:
                raise AdapterError("owner-observable-provider-identity-mismatch")
            return acquire_reconciliation_observation(
                plan, state, preparation, transport
            )
        return provider

    def make_terminal(owner_id: str, profile: str):
        def provider(plan, state, result_kind, contract, transport):
            actual = plan.resolved_parameters.get(
                "command", plan.resolved_parameters.get("mode", "default")
            )
            if plan.sequence_id != owner_id or actual != profile:
                raise AdapterError("owner-observable-provider-identity-mismatch")
            return acquire_terminal_observation(
                plan, state, result_kind, contract, transport
            )
        return provider

    for owner_id, profiles in _OWNER_OBSERVABLE_PROFILES.items():
        owner_symbol = owner_id.replace("-", "_")
        for profile in profiles:
            profile_symbol = profile.replace("-", "_")
            reconciliation_name = f"observe_{owner_symbol}_{profile_symbol}_reconciliation"
            terminal_name = f"observe_{owner_symbol}_{profile_symbol}_terminal"
            reconciliation = make_reconciliation(owner_id, profile)
            terminal = make_terminal(owner_id, profile)
            reconciliation.__name__ = reconciliation_name
            terminal.__name__ = terminal_name
            globals()[reconciliation_name] = reconciliation
            globals()[terminal_name] = terminal


_install_owner_observation_providers()


def reconcile_observation(
    observation: ReconciliationObservation,
    *, reconciliation_contract: Mapping[str, Any],
) -> ReconciliationDecision:
    if type(observation) is not ReconciliationObservation:
        raise AdapterError("typed-reconciliation-observation-required")
    if observation.reconciliation_policy_sha256 != reconciliation_contract.get("policy_sha256"):
        raise AdapterError("reconciliation-policy-hash-mismatch")
    specs = [
        item for item in reconciliation_contract.get("observables", [])
        if isinstance(item, Mapping) and item.get("provider_symbol") == observation.provider_id
    ]
    if len(specs) != 1:
        raise AdapterError("reconciliation-observable-provider-mismatch")
    _validate_raw_observation(
        provider_id=observation.provider_id,
        observed_at_utc=observation.observed_at_utc,
        raw_result=observation.raw_result,
        observable_spec=specs[0],
        label="reconciliation",
    )
    raw = observation.raw_result
    if raw["identity"] != "MATCH":
        classification = "INDETERMINATE"
    elif raw["postcondition"] == "APPLIED":
        classification = "ALREADY_APPLIED"
    elif (
        raw["postcondition"] == "NOT_APPLIED"
        and raw["prepared_prestate"] == "UNCHANGED"
        and raw["mutation_receipt"] == "ABSENT"
    ):
        classification = "NOT_APPLIED"
    else:
        classification = "INDETERMINATE"
    ownership_hash = sha256_bytes(canonical_bytes(dict(observation.observable_ownership)))
    evidence_hash = sha256_bytes(canonical_bytes(dict(observation.evidence)))
    return ReconciliationDecision(
        classification=classification,
        observable_ownership_sha256=ownership_hash,
        evidence_sha256=evidence_hash,
        artifact={
            "schema_version": 1,
            "classification": classification,
            "observable_ownership_sha256": ownership_hash,
            "evidence_sha256": evidence_hash,
            "evidence": dict(observation.evidence),
        },
    )


def verify_terminal_evidence(
    *, owner_sequence_id: str, result_kind: str, result: Mapping[str, Any],
    semantic_observation: TerminalObservation,
    terminal_contract: Mapping[str, Any],
) -> Mapping[str, Any]:
    if type(semantic_observation) is not TerminalObservation:
        raise AdapterError("typed-terminal-observation-required")
    if semantic_observation.owner_sequence_id != owner_sequence_id:
        raise AdapterError("terminal-observation-owner-mismatch")
    if semantic_observation.result_kind != result_kind:
        raise AdapterError("terminal-observation-result-kind-mismatch")
    if semantic_observation.terminal_policy_sha256 != terminal_contract.get("policy_sha256"):
        raise AdapterError("terminal-policy-hash-mismatch")
    specs = [
        item for item in terminal_contract.get("observables", [])
        if isinstance(item, Mapping) and item.get("provider_symbol") == semantic_observation.provider_id
    ]
    if len(specs) != 1:
        raise AdapterError("terminal-observable-provider-mismatch")
    _validate_raw_observation(
        provider_id=semantic_observation.provider_id,
        observed_at_utc=semantic_observation.observed_at_utc,
        raw_result=semantic_observation.raw_result,
        observable_spec=specs[0],
        label="terminal",
    )
    if result_kind == "EXECUTED_RESULT":
        if result.get("returncode") != 0:
            raise AdapterError("terminal-transport-failed")
        if result.get("stdout_encoding") != "JSON_OBJECT":
            raise AdapterError("terminal-envelope-invalid-json")
        envelope = result.get("result_envelope")
        if not isinstance(envelope, Mapping):
            raise AdapterError("terminal-envelope-not-object")
        if owner_sequence_id == "mawf-playbook-blocker-reentry":
            required = {
                "stage", "mode", "workflow", "taskGuid", "targetRunId",
                "verdict", "finalOk", "errorCode",
            }
            if not required.issubset(envelope):
                raise AdapterError("terminal-envelope-schema-invalid")
            if (
                envelope.get("stage") != "reenter"
                or envelope.get("mode") != specs[0].get("profile")
                or not isinstance(envelope.get("workflow"), str)
                or not envelope["workflow"]
                or not isinstance(envelope.get("taskGuid"), str)
                or not envelope["taskGuid"]
                or not isinstance(envelope.get("targetRunId"), str)
                or not envelope["targetRunId"]
                or envelope.get("verdict") not in {
                    "running", "waiting_gate", "waiting_clarification",
                    "waiting_start_approval", "completed", "chain_complete",
                }
            ):
                raise AdapterError("terminal-envelope-schema-invalid")
        elif envelope.get("ok") is not True:
            raise AdapterError("terminal-envelope-not-ok")
        if "finalOk" in envelope and envelope.get("finalOk") is not True:
            raise AdapterError("terminal-envelope-semantic-failure")
        if envelope.get("errorCode") not in {None, ""}:
            raise AdapterError("terminal-envelope-semantic-failure")
    elif result_kind == "RECOVERED_RESULT":
        envelope = None
        if "returncode" in result:
            raise AdapterError("recovered-result-forbids-returncode")
    else:
        raise AdapterError("terminal-result-kind-invalid")
    if semantic_observation.raw_result["semantic"] != "PASS":
        raise AdapterError("terminal-semantic-observation-failed")
    if semantic_observation.raw_result["output_schema"] != "VALID":
        raise AdapterError("terminal-output-schema-invalid")
    if semantic_observation.raw_result["identity"] != "MATCH":
        raise AdapterError("terminal-identity-unverified")
    if semantic_observation.raw_result["work_state"] != "TERMINAL":
        raise AdapterError("terminal-observation-detached")
    evidence_hash = sha256_bytes(canonical_bytes(dict(semantic_observation.evidence)))
    return {
        "schema_version": 1,
        "owner_sequence_id": owner_sequence_id,
        "effect_id": semantic_observation.effect_id,
        "result_kind": result_kind,
        "result_envelope": envelope,
        "semantic_observation": {
            "provider_id": semantic_observation.provider_id,
            "observed_at_utc": semantic_observation.observed_at_utc,
            "raw_result": dict(semantic_observation.raw_result),
            "terminal_policy_sha256": semantic_observation.terminal_policy_sha256,
            "preparation_artifact_sha256": semantic_observation.preparation_artifact_sha256,
            "evidence_sha256": evidence_hash,
            "evidence": dict(semantic_observation.evidence),
        },
    }


BASE_ARGV: dict[str, tuple[str, ...]] = {
    "local-workflow-orch-image": (
        "python3", "/Users/kamenkamenov/mcp-agents-workflow/scripts/local_workflow_orch_image_harness.py",
    ),
    "greenfield-full-drive": (
        "bash", "/Users/kamenkamenov/mcp-agents-workflow/scripts/greenfield_full_drive.sh",
    ),
    "mawf-playbook-blocker-reentry": (
        "python3", "/Users/kamenkamenov/mcp-agents-workflow/scripts/mawf_playbook_test_sequence.py",
        "reenter",
    ),
    "claude-auth-token-refresh": (
        "bash", "/Users/kamenkamenov/mcp-agents-workflow/scripts/claude_auth_refresh.sh",
    ),
    "discovery-promotion-lifecycle": (
        "python3", "/Users/kamenkamenov/memory-knowledge/scripts/discovery_promotion_lifecycle.py",
    ),
    "commit-push-main": (
        "python3", "/Users/kamenkamenov/memory-knowledge/scripts/scoped_git_publish.py",
    ),
    "discovery-bootstrap": (
        "python3", "/Users/kamenkamenov/memory-knowledge/scripts/discovery_bootstrap.py", "start",
    ),
    "discovery-candidate-reconciliation": (
        "python3", "/Users/kamenkamenov/memory-knowledge/scripts/discovery_candidate_reconciliation.py",
    ),
    "convergence-checkpoint-run": (
        "python3", "/Users/kamenkamenov/memory-knowledge/scripts/convergence_checkpoint_run.py",
    ),
    "convergence-state-review-cycle": (
        "python3", "/Users/kamenkamenov/memory-knowledge/scripts/convergence_state_review_cycle.py", "apply",
    ),
}

POSITIONAL_COMMAND = frozenset({
    "local-workflow-orch-image", "claude-auth-token-refresh",
    "discovery-promotion-lifecycle", "discovery-candidate-reconciliation",
})

FLAG_ORDER: dict[str, tuple[str, ...]] = {
    "local-workflow-orch-image": (
        "tag", "name", "port", "port_file", "env_file", "timeout_seconds",
        "container", "source_repository_key", "source", "destination", "tail",
        "keyvault_name", "repository_key", "health_timeout_seconds",
        "real_memory_knowledge",
    ),
    "greenfield-full-drive": (
        "repository_key", "spec", "branch", "tag", "env_file", "keyvault_name",
        "container", "port", "skip_build", "skip_auth", "fresh",
        "decomposition_task_id", "decomposition_run_id", "program_drive_id",
        "expected_spec_hash", "drive_dag", "resume_from_checkpoint", "no_fresh",
        "validate_fresh", "start_feature_index", "parallel_width",
    ),
    "mawf-playbook-blocker-reentry": (
        "delegation_id", "mode", "task_guid", "workflow_name", "run_id", "repo", "branch", "prompt_root_key", "prompt_file",
        "gate_policy", "task_action", "chain_mode", "operator_env", "operator_cwd", "dry_run",
    ),
    "claude-auth-token-refresh": (
        "credential_source", "config_source", "container_key", "vault_key",
        "deployment_key", "verify_targets", "dry_run",
    ),
    "discovery-promotion-lifecycle": (
        "file", "sequence_id", "subject_id", "solution", "reusable_behavior_changed",
        "use_when", "operation_kind", "automation_display", "pass_signal", "repo_roots_file",
        "root", "task_id", "changed_artifact", "changed_artifacts_file",
        "supersedes_correction_id", "max_qualification_runs",
    ),
    "commit-push-main": (
        "mode", "repository_key", "manifest", "manifest_file", "message", "branch", "remote_key", "authorization_receipt_id", "execute", "resume_commit",
        "integrate_remote", "isolated_integrate_remote", "isolated_reconcile_remote",
        "overlay_manifest", "overlay_manifest_file", "ledger_path", "generated_view_path",
    ),
    "discovery-bootstrap": ("command", "spec", "spec_file", "root", "repo_roots_file"),
    "discovery-candidate-reconciliation": (
        "output", "manifest", "active_index", "baseline", "output_dir", "task_id",
        "output_root", "root", "max_attempts",
    ),
    "convergence-checkpoint-run": (
        "state", "repo", "approval_id", "child_intent", "child_intent_file", "helper", "stage",
        "lock_timeout_seconds",
    ),
    "convergence-state-review-cycle": ("command", "request", "request_file", "helper", "dry_run"),
}

RENDER_ALIASES: dict[str, dict[str, str]] = {
    "greenfield-full-drive": {
        "repository_key": "repo", "keyvault_name": "keyvault",
        "fresh": "fresh", "spec": "spec",
    },
    "claude-auth-token-refresh": {
        "credential_source": "token_file", "config_source": "config_file",
        "container_key": "container", "vault_key": "keyvault",
        "deployment_key": "deployment",
    },
    "commit-push-main": {
        "repository_key": "repo", "remote_key": "remote",
        "manifest_file": "manifest", "overlay_manifest_file": "overlay_manifest",
    },
    "discovery-bootstrap": {"spec_file": "spec"},
    "convergence-checkpoint-run": {},
    "convergence-state-review-cycle": {"request_file": "request"},
}

RENDER_OMIT: dict[str, frozenset[str]] = {
    "local-workflow-orch-image": frozenset({"source_repository_key", "working_directory"}),
    # The shell defaults to a fresh drive and exposes only the inverse
    # ``--no-fresh`` switch.  ``fresh`` is a typed contract input used to
    # derive that inverse flag; it is not itself a source argv flag.
    "greenfield-full-drive": frozenset({"mode", "fresh"}),
    "mawf-playbook-blocker-reentry": frozenset({"delegation_id", "prompt_root_key"}),
    "commit-push-main": frozenset({"mode", "authorization_receipt_id", "manifest", "overlay_manifest"}),
    "discovery-bootstrap": frozenset({"command", "spec"}),
    "convergence-checkpoint-run": frozenset({"child_intent", "child_intent_file"}),
    "convergence-state-review-cycle": frozenset({"command", "request"}),
}

PATH_PARAMETERS = frozenset({
    "spec", "root", "repo_roots_file", "token_file", "config_file", "prompt_file",
    "operator_env", "operator_cwd", "file", "changed_artifact", "changed_artifacts_file",
    "manifest", "overlay_manifest", "ledger_path", "generated_view_path", "output",
    "active_index", "baseline", "output_dir", "output_root", "state", "child_intent_file",
    "helper", "request", "env_file", "port_file", "source",
})


def _plain_parameters(intent: ActionIntent) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for parameter in intent.parameters:
        if parameter.value.tag == ParameterTag.SECRET_HANDLE:
            raise AdapterError(f"secret-resolution-not-authorized:{parameter.name}")
        if parameter.name in PATH_PARAMETERS and parameter.value.tag != ParameterTag.PATH:
            raise AdapterError(f"path-handle-required:{parameter.name}")
        values[parameter.name] = parameter.value.value
    return values


def _applicable_schema(
    owner: Mapping[str, Any], supplied: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], Mapping[str, Any]]:
    executable = owner.get("executable_contract")
    if not isinstance(executable, Mapping):
        raise AdapterError("owner-executable-contract-unavailable")
    contract = executable.get("parameter_contract")
    if not isinstance(contract, Mapping):
        raise AdapterError("owner-parameter-contract-unavailable")
    specs: dict[str, dict[str, Any]] = {}
    nodes = {
        str(item.get("source_pointer")): item.get("predicate")
        for item in contract.get("normalized_nodes", [])
        if isinstance(item, Mapping)
    }
    def add_spec(name: str, spec: Mapping[str, Any], pointer: str) -> None:
        predicate = nodes.get(pointer)
        if not isinstance(predicate, Mapping):
            raise AdapterError(f"materialized-parameter-predicate-missing:{pointer}")
        specs[name] = {**dict(spec), "__predicate__": dict(predicate)}
    for item in contract.get("parameters", []):
        if not isinstance(item, Mapping) or not isinstance(item.get("schema"), Mapping):
            raise AdapterError("owner-parameter-contract-invalid")
        name = str(item["name"])
        add_spec(name, item["schema"], f"/parameter_contract/{name}")
    rules = contract.get("schema_rules", {})
    if not isinstance(rules, Mapping):
        raise AdapterError("owner-parameter-schema-rules-invalid")
    for name, spec in rules.get("common", {}).items():
        add_spec(name, spec, f"/parameter_contract/common/{name}")
    for discriminator, rule_name in (("command", "by_command"), ("mode", "by_mode")):
        selected = supplied.get(discriminator)
        alternatives = rules.get(rule_name)
        if alternatives is None:
            continue
        if not isinstance(alternatives, Mapping) or not isinstance(selected, str):
            raise AdapterError(f"parameter-discriminator-required:{discriminator}")
        selected_specs = alternatives.get(selected)
        if not isinstance(selected_specs, Mapping):
            raise AdapterError(f"invalid-parameter-discriminator:{discriminator}:{selected}")
        for name, spec in selected_specs.items():
            if not isinstance(spec, Mapping):
                raise AdapterError(f"invalid-parameter-spec:{name}")
            add_spec(
                name, spec,
                f"/parameter_contract/{rule_name}/{selected}/{name}",
            )
    for name, spec in list(specs.items()):
        schema_name = spec.get("schema")
        if spec.get("type") == "EXACT_OBJECT" and isinstance(schema_name, str):
            object_fields = rules.get(schema_name)
            if not isinstance(object_fields, Mapping):
                raise AdapterError(f"exact-object-schema-unavailable:{name}:{schema_name}")
            specs[name] = {**spec, "object_fields": dict(object_fields)}
    return specs, rules


def _validate_tag(name: str, value: Any, tag: ParameterTag, spec: Mapping[str, Any]) -> None:
    type_name = spec.get("type")
    allowed: dict[str, frozenset[ParameterTag]] = {
        "BOOLEAN": frozenset({ParameterTag.BOOLEAN}),
        "INTEGER": frozenset({ParameterTag.INTEGER}),
        "NUMBER": frozenset({ParameterTag.INTEGER, ParameterTag.NUMBER}),
        "PATH": frozenset({ParameterTag.PATH}),
        "REPOSITORY_RELATIVE_FILE_PATH": frozenset({ParameterTag.PATH}),
        "SECRET_HANDLE": frozenset({ParameterTag.SECRET_HANDLE}),
        "EXACT_OBJECT": frozenset({ParameterTag.EXACT_OBJECT}),
        "TAGGED_UNION": frozenset({ParameterTag.TAGGED_UNION}),
        "SET": frozenset({ParameterTag.SET}),
        "NONEMPTY_SET": frozenset({ParameterTag.SET}),
        "SET_ENUM": frozenset({ParameterTag.SET}),
        "SET_UUID": frozenset({ParameterTag.SET}),
        "NONEMPTY_LIST": frozenset({ParameterTag.LIST}),
    }
    exact_string_tags = {
        "STRING": ParameterTag.STRING,
        "GIT_BRANCH_NAME": ParameterTag.STRING,
        "ENUM": ParameterTag.ENUM,
        "ENUM_FROM_REGISTRY": ParameterTag.RESOURCE_KEY,
        "ENUM_FROM_REPOSITORY": ParameterTag.RESOURCE_KEY,
        "REPOSITORY_KEY": ParameterTag.RESOURCE_KEY,
        "RESOURCE_KEY": ParameterTag.RESOURCE_KEY,
        "FULL_GIT_OBJECT_ID": ParameterTag.SHA1,
        "UUID": ParameterTag.UUID,
        "SHA256": ParameterTag.SHA256,
    }
    expected = allowed.get(str(type_name))
    if type_name in exact_string_tags:
        expected = frozenset({exact_string_tags[str(type_name)]})
    if expected is None or tag not in expected:
        raise AdapterError(f"parameter-type-mismatch:{name}:{type_name}:{tag.value}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum, maximum = spec.get("minimum"), spec.get("maximum")
        if minimum is not None and value < minimum or maximum is not None and value > maximum:
            raise AdapterError(f"parameter-range-invalid:{name}")
    if isinstance(value, str):
        if spec.get("minimum_length") is not None and len(value) < spec["minimum_length"]:
            raise AdapterError(f"parameter-length-invalid:{name}")
        if spec.get("maximum_length") is not None and len(value) > spec["maximum_length"]:
            raise AdapterError(f"parameter-length-invalid:{name}")
    if "values" in spec and type_name not in {"SET_ENUM"} and value not in spec["values"]:
        raise AdapterError(f"parameter-enum-invalid:{name}")
    if "pattern" in spec and isinstance(value, str):
        import re
        if re.fullmatch(str(spec["pattern"]), value) is None:
            raise AdapterError(f"parameter-pattern-invalid:{name}")
    if type_name in {"SET", "NONEMPTY_SET", "SET_ENUM", "SET_UUID", "NONEMPTY_LIST"}:
        if not isinstance(value, list):
            raise AdapterError(f"parameter-collection-invalid:{name}")
        minimum = spec.get("minimum_items", 1 if str(type_name).startswith("NONEMPTY") else 0)
        maximum = spec.get("maximum_items")
        if len(value) < minimum or maximum is not None and len(value) > maximum:
            raise AdapterError(f"parameter-collection-length-invalid:{name}")
        if type_name == "SET_ENUM" and any(item not in spec.get("values", []) for item in value):
            raise AdapterError(f"parameter-enum-invalid:{name}")


def _resolve_path(
    name: str, relative: str, spec: Mapping[str, Any], roots: Mapping[str, Any],
    values: Mapping[str, Any],
) -> tuple[str, str]:
    fixed = spec.get("fixed")
    if isinstance(fixed, str) and fixed in roots and Path(str(roots[fixed])).is_absolute():
        root_keys = [fixed]
        relative = "."
    else:
        root_keys = spec.get("trusted_roots")
    if root_keys is None:
        root_key = spec.get("trusted_root") or spec.get("fixed_root")
        if spec.get("trusted_root_from"):
            root_key = values.get(str(spec["trusted_root_from"]))
        if root_key is None and spec.get("type") == "REPOSITORY_RELATIVE_FILE_PATH":
            root_key = values.get("repository_key")
        root_keys = [root_key]
    if not isinstance(root_keys, list) or not root_keys or any(not isinstance(item, str) for item in root_keys):
        raise AdapterError(f"trusted-root-binding-required:{name}")
    if len(root_keys) > 1:
        parts = Path(relative).parts
        if not parts or parts[0] not in root_keys:
            raise AdapterError(f"trusted-root-key-required:{name}")
        selected_root = parts[0]
        root_keys = [selected_root]
        relative = str(Path(*parts[1:])) if len(parts) > 1 else "."
    candidates: list[tuple[Path, str]] = []
    remote_external_edge = spec.get("resolution_scope") == "REMOTE_EXTERNAL_EDGE"
    for root_key in root_keys:
        raw_root = roots.get(root_key)
        if not isinstance(raw_root, str) or not Path(raw_root).is_absolute():
            continue
        root_source = Path(raw_root)
        root = root_source.resolve()
        unresolved = root_source / relative
        if remote_external_edge:
            if Path(relative).is_absolute() or ".." in Path(relative).parts:
                raise AdapterError(f"trusted-remote-path-invalid:{name}")
            candidate = Path(str(root_source / relative))
            if candidate == root_source or root_source in candidate.parents:
                candidates.append((candidate, root_key))
            continue
        current = root_source
        for part in Path(relative).parts:
            current /= part
            if current.exists() and current.is_symlink():
                raise AdapterError(f"trusted-path-symlink-forbidden:{name}")
        candidate = unresolved.resolve(strict=False)
        if candidate == root or root in candidate.parents:
            candidates.append((candidate, root_key))
    if len(candidates) != 1:
        raise AdapterError(f"trusted-root-resolution-ambiguous:{name}")
    candidate, root_key = candidates[0]
    if remote_external_edge:
        return str(candidate), root_key
    mode = str(spec.get("mode", ""))
    if mode.startswith("READ"):
        if not candidate.exists():
            raise AdapterError(f"trusted-read-target-missing:{name}")
        if "FILE" in mode and not candidate.is_file():
            raise AdapterError(f"trusted-read-target-not-file:{name}")
        if "DIRECTORY" in mode and not candidate.is_dir():
            raise AdapterError(f"trusted-read-target-not-directory:{name}")
    elif mode.startswith("WRITE"):
        parent = candidate if "DIRECTORY" in mode else candidate.parent
        while not parent.exists() and parent != parent.parent:
            parent = parent.parent
        root = Path(str(roots[root_key])).resolve()
        resolved_parent = parent.resolve()
        if resolved_parent != root and root not in resolved_parent.parents:
            raise AdapterError(f"trusted-write-parent-escape:{name}")
    return str(candidate), root_key


def _binding_scope(
    intent: ActionIntent, owner: Mapping[str, Any], parameter_name: str,
) -> str:
    return sha256_bytes(canonical_bytes({
        "task_id": intent.task_id,
        "run_id": intent.run_id,
        "intent_id": intent.intent_id,
        "owner_sequence_id": intent.requested_sequence_id,
        "owner_contract_sha256": owner["owner_contract_sha256"],
        "parameter_name": parameter_name,
    }))


def _static_root_receipt(
    intent: ActionIntent, owner: Mapping[str, Any], name: str,
    root_key: str, resolved_path: str,
) -> BindingReceipt:
    scope = _binding_scope(intent, owner, name)
    fingerprint = sha256_bytes(canonical_bytes({"resolved_path": resolved_path}))
    receipt_id = sha256_bytes(canonical_bytes({
        "provider_id": "contract-static-root",
        "root_key": root_key,
        "scope_sha256": scope,
        "value_fingerprint_sha256": fingerprint,
    }))
    return BindingReceipt(
        receipt_id=receipt_id,
        binding_kind=BindingKind.STATIC_ROOT,
        provider_id="contract-static-root",
        key_or_resource_id=root_key,
        version_id=str(owner["owner_contract_sha256"]),
        scope_sha256=scope,
        value_fingerprint_sha256=fingerprint,
        consumable=False,
    )


def _provider_request(
    intent: ActionIntent, owner: Mapping[str, Any], name: str,
    value: Any, spec: Mapping[str, Any], *, provider_id: str,
    binding_kind: BindingKind, consumable: bool,
) -> BindingRequest:
    if binding_kind == BindingKind.SECRET:
        if not isinstance(value, Mapping):
            raise AdapterError(f"secret-handle-required:{name}")
        key = value.get("key_id")
        version = value.get("version_id")
        if value.get("provider_id") != provider_id:
            raise AdapterError(f"secret-provider-mismatch:{name}")
    else:
        key = value
        version = None
    if not isinstance(key, str) or not key:
        raise AdapterError(f"provider-key-required:{name}")
    return BindingRequest(
        intent=intent,
        owner_sequence_id=intent.requested_sequence_id,
        owner_contract_sha256=str(owner["owner_contract_sha256"]),
        parameter_name=name,
        parameter_type=str(spec.get("type")),
        provider_id=provider_id,
        key_or_resource_id=key,
        version_id=version if isinstance(version, str) else None,
        expected_scope_sha256=_binding_scope(intent, owner, name),
        consumable=consumable,
    )


def _resolve_provider_binding(
    provider: BindingProvider | None, request: BindingRequest,
) -> BindingResolution:
    if provider is None:
        raise AdapterError(f"binding-provider-required:{request.parameter_name}")
    resolution = provider.resolve(request)
    if type(resolution) is not BindingResolution or type(resolution.receipt) is not BindingReceipt:
        raise AdapterError(f"typed-binding-resolution-required:{request.parameter_name}")
    receipt = resolution.receipt
    expected_kind = (
        BindingKind.APPROVAL if request.consumable
        else BindingKind(request.parameter_type)
        if request.parameter_type in {item.value for item in BindingKind}
        else None
    )
    if expected_kind is None:
        if request.parameter_type == "SECRET_HANDLE":
            expected_kind = BindingKind.SECRET
        elif request.parameter_type in {"REPOSITORY_KEY", "ENUM_FROM_REGISTRY", "ENUM_FROM_REPOSITORY"}:
            expected_kind = BindingKind.REPOSITORY
        else:
            expected_kind = BindingKind.RESOURCE
    if (
        receipt.binding_kind != expected_kind
        or receipt.provider_id != request.provider_id
        or receipt.key_or_resource_id != request.key_or_resource_id
        or receipt.scope_sha256 != request.expected_scope_sha256
        or receipt.consumable != request.consumable
        or request.version_id is not None and receipt.version_id != request.version_id
    ):
        raise AdapterError(f"binding-receipt-identity-mismatch:{request.parameter_name}")
    if receipt.expires_at_utc is not None:
        expiry = datetime.fromisoformat(receipt.expires_at_utc.replace("Z", "+00:00"))
        if expiry.astimezone(UTC) <= datetime.now(UTC):
            raise AdapterError(f"binding-receipt-expired:{request.parameter_name}")
    if expected_kind != BindingKind.SECRET:
        actual_fingerprint = sha256_bytes(canonical_bytes(resolution.execution_value))
        if actual_fingerprint != receipt.value_fingerprint_sha256:
            raise AdapterError(f"binding-value-fingerprint-mismatch:{request.parameter_name}")
    elif not isinstance(resolution.execution_value, str) or not resolution.execution_value:
        raise AdapterError(f"secret-execution-value-invalid:{request.parameter_name}")
    return resolution


def _bind_repository_root(
    roots: dict[str, Any], repository_key: Any, resolution: BindingResolution,
    *, parameter_name: str,
) -> None:
    if not isinstance(repository_key, str) or not repository_key:
        raise AdapterError(f"repository-root-key-invalid:{parameter_name}")
    execution_path = Path(str(resolution.execution_value))
    if not execution_path.is_absolute():
        raise AdapterError(f"repository-root-not-absolute:{parameter_name}")
    canonical = execution_path.resolve()
    if str(canonical) != str(execution_path):
        raise AdapterError(f"repository-root-not-canonical:{parameter_name}")
    roots[repository_key] = str(canonical)


def _field_value(values: Mapping[str, Any], path: str) -> Any:
    current: Any = values
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _resolved_predicate(producer: str, field: str, values: Mapping[str, Any]) -> bool:
    value = _field_value(values, field)
    if producer == "work-memory-ledger-membership-v1":
        ledger_path = work_memory.LEDGER_RELATIVE_PATH.as_posix()
        return isinstance(value, list) and ledger_path in value
    if producer == "protected-artifact-detector-v1":
        return isinstance(value, list) and any(
            isinstance(item, Mapping)
            and str(item.get("path", "")).startswith(("scripts/", "skills/", "operations/"))
            for item in value
        )
    if producer == "non-default-repository-dependency-detector-v1":
        return isinstance(value, Mapping) and any(
            isinstance(item, Mapping)
            and item.get("repository_key") not in {None, "memory-knowledge"}
            for item in value.get("dependencies", [])
        )
    # Other RESOLVES nodes describe derivation/materialization authority, not
    # boolean admission conditions. They are enforced by provider/file paths.
    return False


def _eval_predicate(node: Mapping[str, Any], values: Mapping[str, Any]) -> bool:
    op = node.get("op")
    if op == "ALL":
        return all(_eval_predicate(item, values) for item in node.get("predicates", []))
    if op == "ANY":
        return any(_eval_predicate(item, values) for item in node.get("predicates", []))
    if op == "PRESENT":
        return _field_value(values, str(node["field"])) is not None
    if op == "ABSENT":
        return _field_value(values, str(node["field"])) is None
    if op in {"EQ", "NE"}:
        left = _field_value(values, str(node["left"]["field"]))
        right = node["right"]["literal"]
        return left == right if op == "EQ" else left != right
    if op == "IN":
        collection = _field_value(values, str(node["collection"]["field"]))
        return isinstance(collection, (list, tuple, set)) and node["value"]["literal"] in collection
    if op == "RESOLVES":
        return _resolved_predicate(str(node["producer"]), str(node["field"]), values)
    if op == "NOT":
        return not _eval_predicate(node["predicate"], values)
    raise AdapterError(f"unsupported-materialized-predicate:{op}")


def _predicate_requirements(
    name: str, spec: Mapping[str, Any], values: Mapping[str, Any], raw: Mapping[str, Any],
) -> tuple[bool, bool]:
    predicate = spec.get("__predicate__")
    if not isinstance(predicate, Mapping) or predicate.get("op") != "ALL":
        raise AdapterError(f"materialized-parameter-predicate-invalid:{name}")
    required = False
    caller_forbidden = False
    discriminator = values.get("mode", values.get("command"))
    for node in predicate.get("predicates", []):
        op = node.get("op")
        if op == "PRESENT" and node.get("field") == name:
            required = True
        elif op == "REQUIRED_IF" and node.get("field") == name:
            if "modes" in node:
                required = required or discriminator in node["modes"]
            else:
                required = required or _eval_predicate(node["condition"], values)
        elif op == "ABSENT" and node.get("field") == name and node.get("source") == "CALLER":
            modes = node.get("modes")
            applies = modes is None or (
                isinstance(modes, list) and discriminator in modes
            )
            caller_forbidden = applies and name in raw
        elif op == "IMPLIES":
            required = required or (
                _eval_predicate(node["if"], values)
                and node.get("then", {}).get("field") == name
            )
    return required, caller_forbidden


def _validate_json_value(
    name: str, value: Any, spec: Mapping[str, Any], roots: Mapping[str, Any],
    values: Mapping[str, Any] | None = None,
) -> list[tuple[str, str, str]]:
    type_name = spec.get("type")
    bindings: list[tuple[str, str, str]] = []
    if type_name in {
        "STRING", "ISO_DATE", "ENUM", "ENUM_FROM_REGISTRY", "UUID", "SHA256",
        "REPOSITORY_RELATIVE_PATH", "REPOSITORY_RELATIVE_FILE_PATH",
        "REPOSITORY_RELATIVE_PATH_OR_SEQUENCE_ID",
    }:
        if not isinstance(value, str) or not value:
            raise AdapterError(f"materialized-field-type-invalid:{name}")
        if type_name == "ENUM" and value not in spec.get("values", []):
            raise AdapterError(f"materialized-field-enum-invalid:{name}")
        if type_name == "UUID":
            import uuid
            try:
                uuid.UUID(value)
            except ValueError as exc:
                raise AdapterError(f"materialized-field-uuid-invalid:{name}") from exc
        if type_name == "SHA256" and len(value) != 64:
            raise AdapterError(f"materialized-field-sha256-invalid:{name}")
        if type_name.startswith("REPOSITORY_RELATIVE") and (
            Path(value).is_absolute() or ".." in Path(value).parts
        ):
            raise AdapterError(f"materialized-field-path-invalid:{name}")
        if type_name.startswith("REPOSITORY_RELATIVE"):
            resolved_text, root_key = _resolve_path(
                name, value, spec, roots, values or {}
            )
            bindings.append((name, resolved_text, root_key))
        if "pattern" in spec:
            import re
            if re.fullmatch(str(spec["pattern"]), value) is None:
                raise AdapterError(f"materialized-field-pattern-invalid:{name}")
        if len(value) < int(spec.get("minimum_length", 0)) or (
            spec.get("maximum_length") is not None
            and len(value) > int(spec["maximum_length"])
        ):
            raise AdapterError(f"materialized-field-length-invalid:{name}")
    elif type_name in {"INTEGER", "NUMBER"}:
        expected = int if type_name == "INTEGER" else (int, float)
        if isinstance(value, bool) or not isinstance(value, expected):
            raise AdapterError(f"materialized-field-type-invalid:{name}")
    elif type_name == "PATH":
        if not isinstance(value, str) or not value:
            raise AdapterError(f"materialized-field-type-invalid:{name}")
        if Path(value).is_absolute() or ".." in Path(value).parts:
            raise AdapterError(f"materialized-field-path-invalid:{name}")
        resolved_text, root_key = _resolve_path(name, value, spec, roots, {})
        bindings.append((name, resolved_text, root_key))
    elif type_name in {
        "LIST", "NONEMPTY_LIST", "UNIQUE_LIST_STRING", "SET", "NONEMPTY_SET",
    }:
        if not isinstance(value, list):
            raise AdapterError(f"materialized-field-type-invalid:{name}")
        minimum = int(spec.get(
            "minimum_items", 1 if type_name in {"NONEMPTY_LIST", "NONEMPTY_SET"} else 0
        ))
        maximum = spec.get("maximum_items")
        if len(value) < minimum or maximum is not None and len(value) > int(maximum):
            raise AdapterError(f"materialized-field-length-invalid:{name}")
        if type_name == "UNIQUE_LIST_STRING" and (
            any(not isinstance(item, str) for item in value) or len(value) != len(set(value))
        ):
            raise AdapterError(f"materialized-field-unique-list-invalid:{name}")
        if type_name in {"SET", "NONEMPTY_SET"} and (
            any(not isinstance(item, str) for item in value)
            or len(value) != len(set(value))
        ):
            raise AdapterError(f"materialized-field-set-invalid:{name}")
        item_schema = spec.get("item_schema")
        item_type = spec.get("item_type")
        item_fields = spec.get("item_fields")
        common_fields = spec.get("item_common_fields")
        for index, item in enumerate(value):
            if isinstance(item_type, str):
                item_spec = {
                    key: item_value for key, item_value in spec.items()
                    if key not in {
                        "type", "item_type", "item_schema", "item_fields",
                        "item_common_fields", "minimum_items", "maximum_items",
                    }
                }
                item_spec["type"] = item_type
                bindings.extend(_validate_json_value(
                    f"{name}[{index}]", item, item_spec, roots, values,
                ))
            elif isinstance(item_schema, Mapping):
                if "type" in item_schema:
                    bindings.extend(_validate_json_value(
                        f"{name}[{index}]", item, item_schema, roots,
                        item if isinstance(item, Mapping) else values,
                    ))
                else:
                    if not isinstance(item, Mapping) or set(item) != set(item_schema):
                        raise AdapterError(f"materialized-item-fields-invalid:{name}[{index}]")
                    for child, child_spec in item_schema.items():
                        bindings.extend(_validate_json_value(
                            f"{name}[{index}].{child}", item[child], child_spec, roots, item
                        ))
            elif isinstance(item_fields, list):
                if not isinstance(item, Mapping) or set(item) != set(item_fields):
                    raise AdapterError(f"materialized-item-fields-invalid:{name}[{index}]")
            elif isinstance(common_fields, Mapping):
                if not isinstance(item, Mapping) or not set(common_fields) <= set(item):
                    raise AdapterError(f"materialized-item-fields-invalid:{name}[{index}]")
    elif type_name == "EXACT_OBJECT":
        bindings.extend(_validate_exact_object(name, value, spec, roots))
    return bindings


def _validate_exact_object(
    name: str, value: Any, spec: Mapping[str, Any], roots: Mapping[str, Any],
) -> list[tuple[str, str, str]]:
    if not isinstance(value, Mapping):
        raise AdapterError(f"exact-object-required:{name}")
    fields = spec.get("object_fields")
    if fields is None:
        fields = spec.get("fields")
    bindings: list[tuple[str, str, str]] = []
    if isinstance(fields, list):
        if set(value) != set(fields):
            raise AdapterError(f"exact-object-fields-invalid:{name}")
    elif isinstance(fields, Mapping):
        field_specs = {
            child_name: child_spec for child_name, child_spec in fields.items()
            if isinstance(child_spec, Mapping) and "type" in child_spec
        }
        scalar_fields = {
            child_name: child_spec for child_name, child_spec in fields.items()
            if not isinstance(child_spec, Mapping)
        }
        unknown = set(value) - set(field_specs) - set(scalar_fields)
        if unknown:
            raise AdapterError(f"exact-object-fields-invalid:{name}")
        for child_name, child_spec in field_specs.items():
            if child_spec.get("required") is not False and child_name not in value:
                raise AdapterError(f"exact-object-field-missing:{name}.{child_name}")
            if child_name in value:
                bindings.extend(_validate_json_value(
                    f"{name}.{child_name}", value[child_name], child_spec, roots, value
                ))
        for child_name, child_rule in scalar_fields.items():
            if child_name not in value:
                raise AdapterError(f"exact-object-field-missing:{name}.{child_name}")
            if child_rule == "UUID":
                import uuid
                try:
                    uuid.UUID(str(value[child_name]))
                except ValueError as exc:
                    raise AdapterError(f"exact-object-field-invalid:{name}.{child_name}") from exc
            elif value[child_name] != child_rule:
                raise AdapterError(f"exact-object-field-invalid:{name}.{child_name}")
    if name == "spec" and "candidate_identity" in value and "candidate_fingerprint" in value:
        try:
            sequence_candidate_contract.validate_candidate_identity(
                value["candidate_identity"], value["candidate_fingerprint"]
            )
        except sequence_candidate_contract.CandidateContractError as exc:
            raise AdapterError("materialized-candidate-identity-invalid") from exc
    return bindings


def _validate_tagged_union(name: str, value: Any, spec: Mapping[str, Any]) -> tuple[str, Any, Mapping[str, Any]]:
    if not isinstance(value, Mapping) or set(value) != {"tag", "payload"}:
        raise AdapterError(f"tagged-union-invalid:{name}")
    tag = value.get("tag")
    variants = spec.get("variants")
    if not isinstance(tag, str) or not isinstance(variants, Mapping) or not isinstance(variants.get(tag), Mapping):
        raise AdapterError(f"tagged-union-variant-invalid:{name}")
    return tag, value["payload"], variants[tag]


def validate_and_resolve_parameters(
    intent: ActionIntent, owner: Mapping[str, Any],
    *, binding_provider: BindingProvider | None = None,
) -> ResolvedParameters:
    binding_provider = binding_provider or TrustedBindingProvider()
    supplied_values = intent.parameter_map()
    raw = {name: parameter.value for name, parameter in supplied_values.items()}
    specs, rules = _applicable_schema(owner, raw)
    unknown = sorted(set(raw) - set(specs))
    if unknown:
        raise AdapterError(f"unknown-parameter:{intent.requested_sequence_id}:{','.join(unknown)}")
    values = dict(raw)
    materializers = {
        str(spec["materializes"]): name
        for name, spec in specs.items()
        if isinstance(spec.get("materializes"), str)
    }
    for name, spec in specs.items():
        required, caller_forbidden = _predicate_requirements(
            name, spec, values, raw
        )
        conditional_fixed = any(
            key in spec for key in (
                "required_for", "required_when", "required_with",
                "required_unless", "also_required_when",
            )
        )
        if "fixed" in spec and (required or not conditional_fixed):
            if name in values and values[name] != spec["fixed"]:
                raise AdapterError(f"fixed-parameter-override:{name}")
            values[name] = spec["fixed"]
        elif name not in values and "default" in spec:
            values[name] = spec["default"]
        elif name not in values and "fixed_root" in spec:
            values[name] = spec.get("fixed_relative_path", ".")
        if caller_forbidden:
            raise AdapterError(f"caller-override-forbidden:{name}")
        if required and name not in values and materializers.get(name) not in values:
            raise AdapterError(f"missing-required-parameter:{intent.requested_sequence_id}:{name}")
    executable = owner["executable_contract"]
    roots = dict(executable.get("trusted_roots", {}))
    resolved: dict[str, Any] = {}
    argv_values: dict[str, Any] = {}
    root_bindings: dict[str, str] = {}
    binding_receipts: dict[str, BindingReceipt] = {}
    for parameter in intent.parameters:
        spec = specs[parameter.name]
        _validate_tag(parameter.name, parameter.value.value, parameter.value.tag, spec)
    ordered_names = sorted(
        values,
        key=lambda item: (
            0 if specs[item].get("type") in {
                "REPOSITORY_KEY", "ENUM_FROM_REGISTRY",
            } else 1 if specs[item].get("type") == "ENUM_FROM_REPOSITORY"
            else 2 if specs[item].get("type") not in {
                "PATH", "REPOSITORY_RELATIVE_FILE_PATH",
            } else 3,
            item,
        ),
    )
    for name in ordered_names:
        value = values[name]
        spec = specs[name]
        if spec.get("type") == "PATH" or spec.get("type") == "REPOSITORY_RELATIVE_FILE_PATH":
            if not isinstance(value, str):
                raise AdapterError(f"path-handle-required:{name}")
            resolved[name], root_bindings[name] = _resolve_path(name, value, spec, roots, values)
            argv_values[name] = resolved[name]
            binding_receipts[name] = _static_root_receipt(
                intent, owner, name, root_bindings[name], resolved[name]
            )
        elif spec.get("type") == "SECRET_HANDLE":
            provider_id = str(spec.get("provider") or value.get("provider_id", ""))
            request = _provider_request(
                intent, owner, name, value, spec, provider_id=provider_id,
                binding_kind=BindingKind.SECRET, consumable=False,
            )
            resolution = _resolve_provider_binding(binding_provider, request)
            resolved[name] = dict(value)
            argv_values[name] = resolution.execution_value
            binding_receipts[name] = resolution.receipt
        elif spec.get("type") == "TAGGED_UNION":
            tag, payload, variant = _validate_tagged_union(name, value, spec)
            if "trusted_root" in variant:
                if not isinstance(payload, str):
                    raise AdapterError(f"tagged-union-path-invalid:{name}")
                path_spec = {
                    "trusted_root": variant["trusted_root"],
                    "mode": variant.get("mode", "READ_FILE"),
                }
                argv_value, root_key = _resolve_path(name, payload, path_spec, roots, values)
                receipt = _static_root_receipt(intent, owner, name, root_key, argv_value)
            else:
                provider_id = str(variant.get("provider") or variant.get("registry") or "")
                kind = BindingKind.SECRET if "handle_type" in variant else BindingKind.RESOURCE
                request = _provider_request(
                    intent, owner, name, payload, {**spec, "type": "SECRET_HANDLE" if kind == BindingKind.SECRET else "RESOURCE_KEY"},
                    provider_id=provider_id, binding_kind=kind, consumable=False,
                )
                resolution = _resolve_provider_binding(binding_provider, request)
                argv_value, receipt = resolution.execution_value, resolution.receipt
            resolved[name] = {"tag": tag, "payload": payload}
            argv_values[name] = argv_value
            binding_receipts[name] = receipt
        elif spec.get("provider"):
            request = _provider_request(
                intent, owner, name, value, spec, provider_id=str(spec["provider"]),
                binding_kind=BindingKind.APPROVAL, consumable=True,
            )
            resolution = _resolve_provider_binding(binding_provider, request)
            resolved[name] = value
            argv_values[name] = resolution.execution_value
            binding_receipts[name] = resolution.receipt
            if spec.get("type") in {"REPOSITORY_KEY", "ENUM_FROM_REGISTRY"}:
                _bind_repository_root(
                    roots, value, resolution, parameter_name=name
                )
        elif spec.get("type") in {"RESOURCE_KEY", "REPOSITORY_KEY", "ENUM_FROM_REGISTRY", "ENUM_FROM_REPOSITORY"}:
            provider_id = str(
                spec.get("resolver") or spec.get("registry")
                or "repository-registry"
            )
            request = _provider_request(
                intent, owner, name, value, spec, provider_id=provider_id,
                binding_kind=(
                    BindingKind.RESOURCE if spec.get("type") == "RESOURCE_KEY"
                    else BindingKind.REPOSITORY
                ),
                consumable=False,
            )
            resolution = _resolve_provider_binding(binding_provider, request)
            resolved[name] = value
            argv_values[name] = resolution.execution_value
            binding_receipts[name] = resolution.receipt
            if spec.get("type") in {"REPOSITORY_KEY", "ENUM_FROM_REGISTRY"}:
                _bind_repository_root(
                    roots, value, resolution, parameter_name=name
                )
        elif (
            spec.get("type") in {"SET", "NONEMPTY_SET", "NONEMPTY_LIST"}
            and isinstance(spec.get("item_type"), str)
            and str(spec["item_type"]).startswith("REPOSITORY_RELATIVE")
        ):
            if not isinstance(value, list):
                raise AdapterError(f"parameter-collection-invalid:{name}")
            resolved_items: list[str] = []
            item_spec = {**spec, "type": str(spec["item_type"])}
            for index, item in enumerate(value):
                if not isinstance(item, str):
                    raise AdapterError(f"path-handle-required:{name}[{index}]")
                resolved_path, root_key = _resolve_path(
                    f"{name}[{index}]", item, item_spec, roots, values
                )
                binding_name = f"{name}[{index}]"
                resolved_items.append(resolved_path)
                root_bindings[binding_name] = root_key
                binding_receipts[binding_name] = _static_root_receipt(
                    intent, owner, binding_name, root_key, resolved_path
                )
            resolved[name] = list(value)
            argv_values[name] = resolved_items
        else:
            if spec.get("type") == "EXACT_OBJECT":
                nested_bindings = _validate_exact_object(name, value, spec, roots)
                for nested_name, resolved_path, root_key in nested_bindings:
                    root_bindings[nested_name] = root_key
                    binding_receipts[nested_name] = _static_root_receipt(
                        intent, owner, nested_name, root_key, resolved_path
                    )
            resolved[name] = value
            argv_values[name] = value
    for target_name, file_name in materializers.items():
        if target_name in resolved or file_name not in resolved:
            continue
        file_path = Path(str(resolved[file_name]))
        try:
            materialized = json.loads(file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AdapterError(f"materialized-parameter-invalid:{target_name}") from exc
        target_spec = specs[target_name]
        nested_bindings = _validate_json_value(
            target_name, materialized, target_spec, roots, values
        )
        for nested_name, resolved_path, root_key in nested_bindings:
            root_bindings[nested_name] = root_key
            binding_receipts[nested_name] = _static_root_receipt(
                intent, owner, nested_name, root_key, resolved_path
            )
        resolved[target_name] = materialized
        if (
            target_spec.get("type") in {"SET", "NONEMPTY_SET", "LIST", "NONEMPTY_LIST"}
            and isinstance(target_spec.get("item_type"), str)
            and str(target_spec["item_type"]).startswith("REPOSITORY_RELATIVE")
        ):
            argv_values[target_name] = [
                resolved_path for _nested_name, resolved_path, _root_key in nested_bindings
            ]
        else:
            argv_values[target_name] = materialized
    return ResolvedParameters(
        values=resolved,
        argv_values=argv_values,
        schema_sha256=str(executable["parameter_contract"]["policy_sha256"]),
        root_bindings=root_bindings,
        binding_receipts=binding_receipts,
    )


def _require(values: Mapping[str, Any], names: Sequence[str], *, sequence_id: str) -> None:
    missing = [name for name in names if name not in values]
    if missing:
        raise AdapterError(f"missing-required-parameter:{sequence_id}:{','.join(missing)}")


def _validate_contract(sequence_id: str, values: Mapping[str, Any]) -> None:
    allowed = set(FLAG_ORDER[sequence_id]) | {"command"}
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise AdapterError(f"unknown-parameter:{sequence_id}:{','.join(unknown)}")
    command = values.get("command")
    if sequence_id in POSITIONAL_COMMAND and not isinstance(command, str):
        raise AdapterError(f"command-required:{sequence_id}")
    if sequence_id == "local-workflow-orch-image":
        allowed_commands = {
            "build", "run", "health", "copy-code-project", "logs", "stop",
            "seed-codex-auth", "seed-git-auth", "probe-codex", "require-real-memory-knowledge",
        }
        if command not in allowed_commands:
            raise AdapterError("invalid-command:local-workflow-orch-image")
        required = {
            "build": ("tag",), "run": ("tag", "name", "port", "env_file"),
            "copy-code-project": ("container", "source"), "logs": ("container",),
            "stop": ("container",), "seed-codex-auth": ("container",),
            "seed-git-auth": ("container",), "probe-codex": ("container",),
        }.get(str(command), ())
        _require(values, required, sequence_id=sequence_id)
        if command == "health" and not ({"port", "port_file"} & set(values)):
            raise AdapterError("missing-required-parameter:local-workflow-orch-image:port-or-port_file")
        if command == "require-real-memory-knowledge" and values.get("real_memory_knowledge") is not True:
            raise AdapterError("real-memory-knowledge-true-required")
    elif sequence_id == "greenfield-full-drive":
        _require(values, ("repo",), sequence_id=sequence_id)
        if values.get("drive_dag") is not True:
            _require(values, ("spec",), sequence_id=sequence_id)
    elif sequence_id == "mawf-playbook-blocker-reentry":
        _require(values, ("mode", "task_guid"), sequence_id=sequence_id)
        if command not in {None, "reenter"} or values["mode"] not in {
            "start-over", "restart-workflow", "resume",
        }:
            raise AdapterError("invalid-blocker-reentry-mode")
    elif sequence_id == "claude-auth-token-refresh":
        if command not in {"status", "mint", "seed-local", "seed-host", "push-kv", "reseed-azure", "verify", "all"}:
            raise AdapterError("invalid-command:claude-auth-token-refresh")
    elif sequence_id == "discovery-promotion-lifecycle":
        _require(values, ("file", "sequence_id"), sequence_id=sequence_id)
        if command == "drive":
            _require(values, ("use_when", "operation_kind", "automation_display", "pass_signal"), sequence_id=sequence_id)
        elif command == "correct":
            _require(values, ("solution", "reusable_behavior_changed"), sequence_id=sequence_id)
        elif command == "correct-registered":
            _require(values, ("subject_id", "solution", "reusable_behavior_changed"), sequence_id=sequence_id)
        elif command != "status":
            raise AdapterError("invalid-command:discovery-promotion-lifecycle")
    elif sequence_id == "commit-push-main":
        _require(values, ("repo",), sequence_id=sequence_id)
        if "resume_commit" not in values:
            _require(values, ("manifest",), sequence_id=sequence_id)
            if values.get("mode") != "dry-run":
                _require(values, ("message",), sequence_id=sequence_id)
    elif sequence_id == "discovery-bootstrap":
        if command not in {None, "start"}:
            raise AdapterError("invalid-command:discovery-bootstrap")
        _require(values, ("spec",), sequence_id=sequence_id)
    elif sequence_id == "discovery-candidate-reconciliation":
        required = {
            "audit": ("output",), "validate": ("manifest",),
            "execute": ("manifest", "active_index"),
            "execute-rolling": ("baseline", "output_dir", "active_index"),
            "drive": ("task_id", "output_root"),
        }
        if command not in required:
            raise AdapterError("invalid-command:discovery-candidate-reconciliation")
        _require(values, required[str(command)], sequence_id=sequence_id)
    elif sequence_id == "convergence-checkpoint-run":
        _require(values, ("state", "repo", "approval_id", "child_intent"), sequence_id=sequence_id)
    elif sequence_id == "convergence-state-review-cycle":
        _require(values, ("request",), sequence_id=sequence_id)


def _flag(name: str) -> str:
    return "--" + name.replace("_", "-")


def build_invocation(
    intent: ActionIntent, owner: Mapping[str, Any],
    *, binding_provider: BindingProvider | None = None,
) -> InvocationPlan:
    """Build one shell-free argv vector from a typed intent and frozen owner contract."""
    sequence_id = intent.requested_sequence_id
    if owner.get("sequence_id") != sequence_id:
        raise AdapterError("intent-owner-sequence-mismatch")
    if owner.get("availability_policy") != "AVAILABLE":
        raise AdapterError(f"owner-not-available:{owner.get('availability_policy', 'UNRESOLVED')}")
    if sequence_id not in BASE_ARGV:
        raise AdapterError("owner-adapter-unavailable")
    resolved = validate_and_resolve_parameters(
        intent, owner, binding_provider=binding_provider
    )
    values = dict(resolved.argv_values)
    sequence_omit = RENDER_OMIT.get(sequence_id, frozenset())
    if sequence_id == "commit-push-main":
        mode = values["mode"]
        values.update({
            "execute": mode == "publish",
            "integrate_remote": mode == "integrate-remote-and-resume",
            "isolated_integrate_remote": mode == "isolated-integrate-and-resume",
            "isolated_reconcile_remote": mode == "isolated-reconcile-and-resume",
        })
    elif sequence_id == "convergence-state-review-cycle":
        values["dry_run"] = values["command"] == "dry-run"
    elif sequence_id == "greenfield-full-drive":
        mode = values["mode"]
        values["drive_dag"] = mode in {
            "create-program", "resume-program", "validate-fresh",
        }
        values["resume_from_checkpoint"] = mode in {
            "resume-program", "validate-fresh",
        }
        values["validate_fresh"] = mode == "validate-fresh"
        values["no_fresh"] = values.get("fresh") is False
    argv = list(BASE_ARGV[sequence_id])
    if len(argv) > 1:
        argv[1] = str(resolve_repository_source_path(
            argv[1],
            repository_root=ROOT,
            canonical_repository_root=CANONICAL_ROOT,
        ))
    if sequence_id == "convergence-checkpoint-run":
        argv.extend((
            "--child-intent-json",
            json.dumps(
                resolved.values["child_intent"],
                sort_keys=True,
                separators=(",", ":"),
            ),
        ))
    if sequence_id == "commit-push-main":
        repository_key = resolved.values.get("repository_key")
        if not isinstance(repository_key, str) or not repository_key:
            raise AdapterError("commit-push-main-repository-key-invalid")
        argv.extend(("--repository-key", repository_key))
    if sequence_id == "discovery-candidate-reconciliation":
        if "root" in values:
            argv.extend(("--root", str(resolve_repository_source_path(
                str(values["root"]),
                repository_root=ROOT,
                canonical_repository_root=CANONICAL_ROOT,
            ))))
        argv.append(str(values["command"]))
    elif sequence_id in POSITIONAL_COMMAND:
        argv.append(str(values["command"]))
    for name in FLAG_ORDER[sequence_id]:
        if name not in values or name in sequence_omit:
            continue
        if sequence_id == "discovery-candidate-reconciliation":
            profile_flags = {
                "audit": {"output"},
                "validate": {"manifest"},
                "execute": {"manifest", "active_index"},
                "execute-rolling": {
                    "baseline", "output_dir", "active_index", "max_attempts",
                },
                "drive": {"task_id", "output_root"},
            }
            if name == "root" or name not in profile_flags[str(values["command"])]:
                continue
        if sequence_id == "discovery-promotion-lifecycle":
            profile_flags = {
                "status": {"file", "sequence_id", "repo_roots_file", "root"},
                "drive": {
                    "file", "sequence_id", "use_when", "operation_kind",
                    "automation_display", "pass_signal", "repo_roots_file",
                    "root", "max_qualification_runs",
                },
                "correct": {
                    "file", "sequence_id", "solution", "reusable_behavior_changed",
                    "repo_roots_file", "root", "task_id", "changed_artifact",
                    "changed_artifacts_file", "supersedes_correction_id",
                },
                "correct-registered": {
                    "subject_id", "solution", "reusable_behavior_changed",
                    "repo_roots_file", "root", "task_id", "changed_artifact",
                    "changed_artifacts_file", "supersedes_correction_id",
                },
            }
            if name not in profile_flags[str(values["command"])]:
                continue
        value = values[name]
        rendered_name = RENDER_ALIASES.get(sequence_id, {}).get(name, name)
        if isinstance(value, bool):
            if value:
                argv.append(_flag(rendered_name))
            continue
        if isinstance(value, list):
            for item in value:
                if not isinstance(item, (str, int, float)) or isinstance(item, bool):
                    raise AdapterError(f"unsupported-parameter-value:{name}")
                argv.extend((_flag(rendered_name), str(item)))
            continue
        if not isinstance(value, (str, int, float)) or isinstance(value, bool):
            raise AdapterError(f"unsupported-parameter-value:{name}")
        argv.extend((_flag(rendered_name), str(value)))
    if sequence_id == "claude-auth-token-refresh":
        argv.append("--prevention-json")
    return InvocationPlan(
        sequence_id=sequence_id,
        argv=tuple(argv),
        owner_contract_sha256=str(owner["owner_contract_sha256"]),
        implementation_source_sha256=str(owner["implementation_source_sha256"]),
        parameter_schema_sha256=resolved.schema_sha256,
        # Persist only canonical caller handles/keys and static resolved paths;
        # ephemeral provider values (including secret paths/contents) stay in argv.
        resolved_parameters=dict(resolved.values),
        root_bindings=resolved.root_bindings,
        binding_receipts=resolved.binding_receipts,
    )


def bind_effect_context(plan: InvocationPlan, effect_id: str) -> InvocationPlan:
    """Attach owner-internal effect identity only where the real source accepts it."""
    if (
        not isinstance(effect_id, str) or len(effect_id) != 64
        or any(character not in "0123456789abcdef" for character in effect_id)
    ):
        raise AdapterError("effect-context-id-invalid")
    if plan.effect_context_binding == "ARGV_EFFECT_ID":
        return plan
    argv = list(plan.argv)
    if plan.sequence_id == "claude-auth-token-refresh":
        argv.extend(("--effect-id", effect_id))
    elif (
        plan.sequence_id == "local-workflow-orch-image"
        and plan.resolved_parameters.get("command") in {"build", "run"}
    ):
        argv.extend(("--prevention-effect-id", effect_id))
    else:
        return plan
    return replace(
        plan, argv=tuple(argv), effect_context_binding="ARGV_EFFECT_ID"
    )


def bind_preparation_context(
    plan: InvocationPlan, effect_id: str, preparation_artifact_sha256: str,
) -> InvocationPlan:
    """Bind the durable effect/preparation identity to the real source invocation."""
    for label, value in (
        ("effect", effect_id), ("preparation", preparation_artifact_sha256),
    ):
        if (
            not isinstance(value, str) or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise AdapterError(f"{label}-context-id-invalid")
    if plan.preparation_context_binding == "ARGV_PREPARATION_SHA256":
        return plan
    argv = list(plan.argv)
    if plan.effect_context_binding != "ARGV_EFFECT_ID":
        argv.extend(("--prevention-effect-id", effect_id))
    argv.extend(("--prevention-preparation-sha256", preparation_artifact_sha256))
    return replace(
        plan,
        argv=tuple(argv),
        effect_context_binding="ARGV_EFFECT_ID",
        preparation_context_binding="ARGV_PREPARATION_SHA256",
    )


def _named(
    sequence_id: str, intent: ActionIntent, owner: Mapping[str, Any],
    *, binding_provider: BindingProvider | None = None,
) -> InvocationPlan:
    if intent.requested_sequence_id != sequence_id:
        raise AdapterError("handler-sequence-mismatch")
    return build_invocation(intent, owner, binding_provider=binding_provider)


def local_workflow_orch_image(intent: ActionIntent, owner: Mapping[str, Any]) -> InvocationPlan:
    return _named("local-workflow-orch-image", intent, owner)


def greenfield_full_drive(intent: ActionIntent, owner: Mapping[str, Any]) -> InvocationPlan:
    return _named("greenfield-full-drive", intent, owner)


def mawf_playbook_blocker_reentry(intent: ActionIntent, owner: Mapping[str, Any]) -> InvocationPlan:
    return _named("mawf-playbook-blocker-reentry", intent, owner)


def claude_auth_token_refresh(intent: ActionIntent, owner: Mapping[str, Any]) -> InvocationPlan:
    return _named("claude-auth-token-refresh", intent, owner)


def discovery_promotion_lifecycle(intent: ActionIntent, owner: Mapping[str, Any]) -> InvocationPlan:
    return _named("discovery-promotion-lifecycle", intent, owner)


def commit_push_main(intent: ActionIntent, owner: Mapping[str, Any]) -> InvocationPlan:
    return _named("commit-push-main", intent, owner)


def discovery_bootstrap(intent: ActionIntent, owner: Mapping[str, Any]) -> InvocationPlan:
    return _named("discovery-bootstrap", intent, owner)


def discovery_candidate_reconciliation(intent: ActionIntent, owner: Mapping[str, Any]) -> InvocationPlan:
    return _named("discovery-candidate-reconciliation", intent, owner)


def convergence_checkpoint_run(intent: ActionIntent, owner: Mapping[str, Any]) -> InvocationPlan:
    return _named("convergence-checkpoint-run", intent, owner)


def convergence_state_review_cycle(intent: ActionIntent, owner: Mapping[str, Any]) -> InvocationPlan:
    return _named("convergence-state-review-cycle", intent, owner)


def _owner_policy_evidence_valid(
    owner_sequence_id: str,
    provider_id: str,
    contract: Mapping[str, Any],
    evidence: Mapping[str, Any] | Any,
    *,
    kind: str,
) -> bool:
    """Authenticate one exact owner/profile policy evaluation against source evidence."""
    if not isinstance(evidence, Mapping):
        return False
    observables = [
        row for row in contract.get("observables", [])
        if isinstance(row, Mapping) and row.get("provider_symbol") == provider_id
    ]
    if len(observables) != 1:
        return False
    profile = observables[0].get("profile")
    if not isinstance(profile, str) or not profile:
        return False
    try:
        source_evidence = _source_observable_evidence_for_owner(
            owner_sequence_id, profile
        )
    except AdapterError:
        return False
    required_probes = source_evidence["profile"].get(
        "capture_schema", {}
    ).get("probe_ids")
    clause_ids = contract.get("required_clause_ids")
    probe_results = evidence.get("probe_results")
    capture = evidence.get("capture")
    authoritative_source_hash = source_evidence["owner"].get("evidence_sha256")
    if (
        not isinstance(required_probes, list) or not required_probes
        or not isinstance(clause_ids, list) or not clause_ids
        or not isinstance(probe_results, Mapping)
        or not isinstance(capture, Mapping)
        or capture.get("probes") != probe_results
        or evidence.get("source_evidence_sha256") != authoritative_source_hash
        or evidence.get("capture_sha256")
        != sha256_bytes(canonical_bytes(capture))
        or evidence.get("probe_results_sha256")
        != sha256_bytes(canonical_bytes(probe_results))
        or evidence.get("profile") != profile
        or evidence.get("evaluated_clause_ids") != clause_ids
        or evidence.get("evaluated_probe_ids") != required_probes
        or list(probe_results) != required_probes
    ):
        return False
    predicate = {
        "owner_sequence_id": owner_sequence_id,
        "profile": profile,
        "kind": kind,
        "required_probe_ids": list(required_probes),
        "required_clause_ids": list(clause_ids),
        "source_evidence_sha256": authoritative_source_hash,
        "capture_sha256": evidence["capture_sha256"],
        "probe_results_sha256": evidence["probe_results_sha256"],
    }
    expected_clause_evaluations = {
        clause_id: sha256_bytes(canonical_bytes({
            "owner_sequence_id": owner_sequence_id,
            "profile": profile,
            "kind": kind,
            "clause_id": clause_id,
            "probe_results": dict(probe_results),
        }))
        for clause_id in clause_ids
    }
    policy_fields = (
        "profile", "owner_semantic_predicate_sha256", "evaluated_clause_ids",
        "evaluated_probe_ids", "probe_results", "clause_evaluations", "capture",
        "source_evidence_sha256", "capture_sha256", "probe_results_sha256",
    )
    policy_evidence = {field: evidence.get(field) for field in policy_fields}
    expected_mac = hmac.new(
        _POLICY_EVIDENCE_KEY, canonical_bytes(policy_evidence), "sha256"
    ).hexdigest()
    return (
        evidence.get("owner_semantic_predicate_sha256")
        == sha256_bytes(canonical_bytes(predicate))
        and evidence.get("clause_evaluations") == expected_clause_evaluations
        and isinstance(evidence.get("policy_evidence_mac"), str)
        and hmac.compare_digest(evidence["policy_evidence_mac"], expected_mac)
    )


def _owner_reconciler(
    expected_owner_sequence_id: str, observation: ReconciliationObservation,
    *, reconciliation_contract: Mapping[str, Any],
) -> ReconciliationDecision:
    if type(observation) is not ReconciliationObservation:
        raise AdapterError("typed-reconciliation-observation-required")
    if (
        observation.owner_sequence_id != expected_owner_sequence_id
        or observation.observable_ownership.get("owner_sequence_id") != expected_owner_sequence_id
    ):
        raise AdapterError("reconciliation-observation-owner-mismatch")
    if observation.observable_ownership.get("effect_id") != observation.effect_id:
        raise AdapterError("reconciliation-observation-effect-mismatch")
    if not _owner_policy_evidence_valid(
        expected_owner_sequence_id, observation.provider_id,
        reconciliation_contract, observation.evidence, kind="reconciliation",
    ):
        raise AdapterError("reconciliation-owner-policy-not-evaluated")
    return reconcile_observation(
        observation, reconciliation_contract=reconciliation_contract
    )


def reconcile_claude_auth_token_refresh(observation: ReconciliationObservation, **kwargs: Any) -> ReconciliationDecision:
    return _owner_reconciler("claude-auth-token-refresh", observation, **kwargs)


def reconcile_commit_push_main(observation: ReconciliationObservation, **kwargs: Any) -> ReconciliationDecision:
    return _owner_reconciler("commit-push-main", observation, **kwargs)


def reconcile_convergence_checkpoint_run(observation: ReconciliationObservation, **kwargs: Any) -> ReconciliationDecision:
    return _owner_reconciler("convergence-checkpoint-run", observation, **kwargs)


def reconcile_convergence_state_review_cycle(observation: ReconciliationObservation, **kwargs: Any) -> ReconciliationDecision:
    return _owner_reconciler("convergence-state-review-cycle", observation, **kwargs)


def reconcile_discovery_bootstrap(observation: ReconciliationObservation, **kwargs: Any) -> ReconciliationDecision:
    return _owner_reconciler("discovery-bootstrap", observation, **kwargs)


def reconcile_discovery_candidate_reconciliation(observation: ReconciliationObservation, **kwargs: Any) -> ReconciliationDecision:
    return _owner_reconciler("discovery-candidate-reconciliation", observation, **kwargs)


def reconcile_discovery_promotion_lifecycle(observation: ReconciliationObservation, **kwargs: Any) -> ReconciliationDecision:
    return _owner_reconciler("discovery-promotion-lifecycle", observation, **kwargs)


def reconcile_greenfield_full_drive(observation: ReconciliationObservation, **kwargs: Any) -> ReconciliationDecision:
    return _owner_reconciler("greenfield-full-drive", observation, **kwargs)


def reconcile_local_workflow_orch_image(observation: ReconciliationObservation, **kwargs: Any) -> ReconciliationDecision:
    return _owner_reconciler("local-workflow-orch-image", observation, **kwargs)


def reconcile_mawf_playbook_blocker_reentry(observation: ReconciliationObservation, **kwargs: Any) -> ReconciliationDecision:
    return _owner_reconciler("mawf-playbook-blocker-reentry", observation, **kwargs)


def _owner_terminal_verifier(
    expected_owner_sequence_id: str,
    *,
    result_kind: str,
    result: Mapping[str, Any],
    semantic_observation: TerminalObservation,
    terminal_contract: Mapping[str, Any],
) -> Mapping[str, Any]:
    if not _owner_policy_evidence_valid(
        expected_owner_sequence_id, semantic_observation.provider_id,
        terminal_contract, semantic_observation.evidence, kind="terminal",
    ):
        raise AdapterError("terminal-owner-policy-not-evaluated")
    return verify_terminal_evidence(
        owner_sequence_id=expected_owner_sequence_id,
        result_kind=result_kind,
        result=result,
        semantic_observation=semantic_observation,
        terminal_contract=terminal_contract,
    )


def verify_claude_auth_token_refresh(**kwargs: Any) -> Mapping[str, Any]:
    return _owner_terminal_verifier("claude-auth-token-refresh", **kwargs)


def verify_commit_push_main(**kwargs: Any) -> Mapping[str, Any]:
    return _owner_terminal_verifier("commit-push-main", **kwargs)


def verify_convergence_checkpoint_run(**kwargs: Any) -> Mapping[str, Any]:
    evidence = _owner_terminal_verifier("convergence-checkpoint-run", **kwargs)
    if kwargs.get("result_kind") != "EXECUTED_RESULT":
        raise AdapterError("checkpoint-terminal-requires-composed-executed-result")
    result = kwargs.get("result")
    envelope = result.get("result_envelope") if isinstance(result, Mapping) else None
    if (
        not isinstance(envelope, Mapping)
        or set(envelope) != {"ok", "verdict", "checkpoint", "child"}
        or envelope.get("ok") is not True
        or envelope.get("verdict") != "PASS"
    ):
        raise AdapterError("checkpoint-terminal-envelope-invalid")
    checkpoint = envelope.get("checkpoint")
    checkpoint_required = {
        "schema_version", "verdict", "approval_id_sha256", "stage",
        "outer_iteration", "repository_path_sha256", "helper_sha256",
        "child_intent_sha256", "guard_receipt_id", "state_before_sha256",
        "state_after_accept_sha256", "state_after_guard_sha256",
        "accept_receipt", "guard_receipt",
    }
    if (
        not isinstance(checkpoint, Mapping)
        or set(checkpoint) != checkpoint_required
        or checkpoint.get("schema_version") != 1
        or checkpoint.get("verdict") != "CHECKPOINT_APPLIED"
        or any(
            not isinstance(checkpoint.get(name), str)
            or len(str(checkpoint[name])) != 64
            for name in (
                "approval_id_sha256", "repository_path_sha256", "helper_sha256",
                "child_intent_sha256", "state_before_sha256",
                "state_after_accept_sha256", "state_after_guard_sha256",
            )
        )
        or any(
            not isinstance(checkpoint.get(name), Mapping)
            or checkpoint[name].get("returncode") != 0
            for name in ("accept_receipt", "guard_receipt")
        )
    ):
        raise AdapterError("checkpoint-terminal-receipt-invalid")
    child = envelope.get("child")
    child_required = {
        "owner_sequence_id", "owner_contract_sha256", "intent_id", "effect_id",
        "unit_budget_sha256", "terminal_artifact_sha256", "semantic_verdict",
    }
    if (
        not isinstance(child, Mapping)
        or set(child) != child_required
        or child.get("semantic_verdict") != "PASS"
        or any(
            not isinstance(child.get(name), str) or len(str(child[name])) != 64
            for name in (
                "owner_contract_sha256", "effect_id", "unit_budget_sha256",
                "terminal_artifact_sha256",
            )
        )
    ):
        raise AdapterError("checkpoint-child-terminal-artifact-invalid")
    return {
        **dict(evidence),
        "checkpoint_receipt_sha256": sha256_bytes(canonical_bytes(dict(checkpoint))),
        "child_terminal_artifact_sha256": child["terminal_artifact_sha256"],
        "child_unit_budget_sha256": child["unit_budget_sha256"],
    }


def verify_convergence_state_review_cycle(**kwargs: Any) -> Mapping[str, Any]:
    evidence = _owner_terminal_verifier("convergence-state-review-cycle", **kwargs)
    if kwargs.get("result_kind") == "RECOVERED_RESULT":
        return evidence
    result = kwargs.get("result")
    envelope = result.get("result_envelope") if isinstance(result, Mapping) else None
    if not isinstance(envelope, Mapping) or envelope.get("ok") is not True:
        raise AdapterError("review-cycle-terminal-envelope-invalid")
    cycle_status = envelope.get("cycle_status")
    if cycle_status not in {"DRY_RUN", "APPLIED"}:
        raise AdapterError("review-cycle-status-invalid")
    if (
        not isinstance(envelope.get("operation_count"), int)
        or isinstance(envelope.get("operation_count"), bool)
        or envelope["operation_count"] <= 0
        or not isinstance(envelope.get("convergence_status"), str)
        or envelope["convergence_status"] not in {
            "research", "plan", "implementation", "review", "blocked",
            "cap_reached", "complete",
        }
        or any(
            not isinstance(envelope.get(name), str)
            or len(envelope[name]) != 64
            for name in ("initial_state_sha256", "final_state_sha256")
        )
    ):
        raise AdapterError("review-cycle-terminal-fields-invalid")
    if cycle_status == "DRY_RUN":
        if envelope["initial_state_sha256"] != envelope["final_state_sha256"]:
            raise AdapterError("review-cycle-dry-run-mutated-state")
    elif envelope.get("pass_signal") != "CONVERGENCE STATE REVIEW CYCLE OK":
        raise AdapterError("review-cycle-apply-pass-signal-invalid")
    return {
        **dict(evidence),
        "cycle_status": cycle_status,
        "convergence_status": envelope["convergence_status"],
        "operation_count": envelope["operation_count"],
        "final_state_sha256": envelope["final_state_sha256"],
    }


def verify_discovery_bootstrap(**kwargs: Any) -> Mapping[str, Any]:
    return _owner_terminal_verifier("discovery-bootstrap", **kwargs)


def verify_discovery_candidate_reconciliation(**kwargs: Any) -> Mapping[str, Any]:
    return _owner_terminal_verifier("discovery-candidate-reconciliation", **kwargs)


def verify_discovery_promotion_lifecycle(**kwargs: Any) -> Mapping[str, Any]:
    return _owner_terminal_verifier("discovery-promotion-lifecycle", **kwargs)


def verify_greenfield_full_drive(**kwargs: Any) -> Mapping[str, Any]:
    return _owner_terminal_verifier("greenfield-full-drive", **kwargs)


def verify_local_workflow_orch_image(**kwargs: Any) -> Mapping[str, Any]:
    return _owner_terminal_verifier("local-workflow-orch-image", **kwargs)


def verify_mawf_playbook_blocker_reentry(**kwargs: Any) -> Mapping[str, Any]:
    return _owner_terminal_verifier("mawf-playbook-blocker-reentry", **kwargs)


def __getattr__(name: str) -> Any:
    # Frozen unavailable/custodian handler symbols resolve to a deterministic
    # fail-closed adapter instead of a prose or shell fallback.
    def unavailable_owner(*_args: Any, **_kwargs: Any) -> None:
        raise AdapterError("owner-evidence-unavailable")
    return unavailable_owner
