#!/usr/bin/env python3
"""Closed production source-probe selection for executable prevention owners.

The production caller supplies only true external edges.  Owner/profile routing,
provider identity, and transport construction are immutable runtime authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, Callable, Mapping, Protocol

try:
    from scripts import prevention_adapters
except ModuleNotFoundError:  # direct script execution
    import prevention_adapters


class SourceProbeError(ValueError):
    """Fail-closed production source-probe construction or capture error."""


class SourceEdgeKind(str, Enum):
    LOCAL_STATE = "LOCAL_STATE"
    GIT = "GIT"
    DOCKER = "DOCKER"
    CREDENTIAL = "CREDENTIAL"
    OPERATOR = "OPERATOR"


@dataclass(frozen=True)
class SourceProbeCapture:
    """Raw typed source facts returned by exactly one true external edge read."""

    identity: "SourceHashFact"
    ownership: Mapping[str, Any]
    prestate: "SourceHashFact"
    receipt: "SourceReceiptFact"
    work_state: "SourceWorkStateFact"
    probes: Mapping[str, "SourceProbeFact"]


@dataclass(frozen=True)
class SourceHashFact:
    observed_sha256: str | None
    known: bool


@dataclass(frozen=True)
class SourceReceiptFact:
    present: bool
    known: bool
    effect_id: str | None
    preparation_artifact_sha256: str | None


@dataclass(frozen=True)
class SourceWorkStateFact:
    terminal: bool
    detached: bool


@dataclass(frozen=True)
class SourceProbeFact:
    observed_sha256: str | None
    known: bool
    absent: bool


class SourceProbeEdge(Protocol):
    """A read-only true external edge; it does not select an owner provider."""

    def capture(self, request: Mapping[str, Any]) -> SourceProbeCapture: ...


class GreenfieldFrontierTransport:
    """Owner-selected durable Greenfield frontier reader over the operator edge."""

    def __init__(self, edge: SourceProbeEdge):
        query = getattr(edge, "query_greenfield_frontier", None)
        if not callable(query):
            raise SourceProbeError("greenfield-frontier-edge-unavailable")
        self._query = query

    def query(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        if request.get("owner_sequence_id") != "greenfield-full-drive":
            raise SourceProbeError("greenfield-frontier-owner-mismatch")
        result = self._query(dict(request))
        if not isinstance(result, Mapping):
            raise SourceProbeError("greenfield-frontier-capture-invalid")
        return result


@dataclass(frozen=True)
class SourceEdgeRegistry:
    """Typed external-edge registry accepted by the production controller."""

    local_state: SourceProbeEdge | None = None
    git: SourceProbeEdge | None = None
    docker: SourceProbeEdge | None = None
    credential: SourceProbeEdge | None = None
    operator: SourceProbeEdge | None = None

    def require(self, kind: SourceEdgeKind) -> SourceProbeEdge:
        edge = {
            SourceEdgeKind.LOCAL_STATE: self.local_state,
            SourceEdgeKind.GIT: self.git,
            SourceEdgeKind.DOCKER: self.docker,
            SourceEdgeKind.CREDENTIAL: self.credential,
            SourceEdgeKind.OPERATOR: self.operator,
        }[kind]
        if edge is None:
            raise SourceProbeError(f"production-source-edge-unavailable:{kind.value}")
        capture = getattr(edge, "capture", None)
        if not callable(capture):
            raise SourceProbeError(f"production-source-edge-invalid:{kind.value}")
        return edge


@dataclass(frozen=True)
class ProviderSpec:
    owner_sequence_id: str
    profile_id: str
    edge_kind: SourceEdgeKind
    reconciliation_provider_symbol: str
    terminal_provider_symbol: str


class ProductionSourceProbeBackend:
    """Closed backend bound to one immutable owner/profile provider row."""

    backend_id = "PRODUCTION_SOURCE_PROBE_V1"

    def __init__(self, spec: ProviderSpec, edge: SourceProbeEdge):
        self.spec = spec
        self.edge = edge
        self._cached_request: Mapping[str, Any] | None = None
        self._cached_capture: SourceProbeCapture | None = None

    def _capture(self, request: Mapping[str, Any]) -> SourceProbeCapture:
        if (
            request.get("owner_sequence_id") != self.spec.owner_sequence_id
            or request.get("profile") != self.spec.profile_id
            or request.get("provider_symbol") not in {
                self.spec.reconciliation_provider_symbol,
                self.spec.terminal_provider_symbol,
            }
        ):
            raise SourceProbeError("production-source-provider-identity-mismatch")
        if self._cached_request == request and self._cached_capture is not None:
            return self._cached_capture
        source_request = {
            field: request[field] for field in (
                "effect_id", "owner_sequence_id", "preparation_artifact_sha256",
                "profile", "probe_ids", "provider_symbol",
                "source_evidence_sha256",
            )
        }
        capture = self.edge.capture(source_request)
        if type(capture) is not SourceProbeCapture:
            raise SourceProbeError("typed-source-probe-capture-required")
        self._cached_request = dict(request)
        self._cached_capture = capture
        return capture

    def capture_raw(self, request: Mapping[str, Any]) -> SourceProbeCapture:
        return self._capture(request)


class ProductionObservationTransport:
    """Production transport preserving raw facts for adapter-owned classification."""

    def __init__(self, backend: ProductionSourceProbeBackend):
        self.backend = backend

    def query(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        required = {
            "effect_id", "owner_sequence_id", "preparation_artifact_sha256",
            "observation_targets", "prepared_prestate_identities",
            "prepared_receipt_identities", "profile", "probe_ids",
            "provider_symbol", "source_evidence_sha256",
        }
        if not isinstance(request, Mapping) or set(request) != required:
            raise SourceProbeError("production-source-observation-request-invalid")
        capture = self.backend.capture_raw(request)
        targets = request.get("observation_targets")
        if not isinstance(targets, Mapping):
            raise SourceProbeError("production-observation-targets-invalid")
        identity_expected = targets.get("identity_expected_sha256")
        prestate_expected = targets.get("prestate_expected_sha256")
        probe_expected = targets.get("probe_expected_sha256s")
        if (
            not isinstance(identity_expected, str)
            or not isinstance(prestate_expected, str)
            or not isinstance(probe_expected, Mapping)
            or set(probe_expected) != set(request["probe_ids"])
        ):
            raise SourceProbeError("production-observation-expectations-invalid")
        envelope = production_capture_envelope(
            request, capture, observed_at_utc=datetime.now(UTC).isoformat()
        )
        recorder = getattr(self.backend.edge, "record_observation_envelope", None)
        if callable(recorder):
            recorder(request, envelope)
        return envelope


def production_capture_envelope(
    request: Mapping[str, Any], capture: SourceProbeCapture,
    *, observed_at_utc: str,
) -> Mapping[str, Any]:
    """Canonical raw envelope shared by runtime transport and trace producer."""
    targets = request["observation_targets"]
    identity_expected = targets["identity_expected_sha256"]
    prestate_expected = targets["prestate_expected_sha256"]
    probe_expected = targets["probe_expected_sha256s"]
    return {
            "schema_version": 1,
            "transport_kind": "PRODUCTION_SOURCE_PROBE",
            "observed_at_utc": observed_at_utc,
            "raw_source_facts": {
                "identity": {
                    "expected_sha256": identity_expected,
                    **asdict(capture.identity),
                },
                "ownership": dict(capture.ownership),
                "prestate": {
                    "expected_sha256": prestate_expected,
                    **asdict(capture.prestate),
                },
                "receipt": asdict(capture.receipt),
                "work_state": asdict(capture.work_state),
                "probes": {
                    name: {
                        "expected_sha256": probe_expected[name],
                        **asdict(fact),
                    }
                    for name, fact in capture.probes.items()
                },
            },
            "source_evidence_sha256": request["source_evidence_sha256"],
        }


ProviderFactory = Callable[[SourceProbeEdge], ProductionSourceProbeBackend]


_OWNER_PROFILES: Mapping[str, tuple[str, ...]] = {
    "claude-auth-token-refresh": (
        "all", "mint", "push-kv", "reseed-azure", "seed-host", "seed-local",
        "status", "verify",
    ),
    "commit-push-main": (
        "dry-run", "integrate-remote-and-resume", "isolated-integrate-and-resume",
        "isolated-reconcile-and-resume", "publish", "resume-push",
    ),
    "convergence-checkpoint-run": ("default",),
    "convergence-state-review-cycle": ("apply", "dry-run"),
    "discovery-bootstrap": ("start",),
    "discovery-candidate-reconciliation": (
        "audit", "drive", "execute", "execute-rolling", "validate",
    ),
    "discovery-promotion-lifecycle": (
        "correct", "correct-registered", "drive", "status",
    ),
    "greenfield-full-drive": (
        "create-program", "resume-program", "start-from-spec", "validate-fresh",
    ),
    "local-workflow-orch-image": (
        "build", "copy-code-project", "health", "logs", "probe-codex",
        "require-real-memory-knowledge", "run", "seed-codex-auth",
        "seed-git-auth", "stop",
    ),
    "mawf-playbook-blocker-reentry": ("restart-workflow", "resume", "start-over"),
}


_OWNER_EDGE_KIND: Mapping[str, SourceEdgeKind] = {
    "claude-auth-token-refresh": SourceEdgeKind.CREDENTIAL,
    "commit-push-main": SourceEdgeKind.GIT,
    "convergence-checkpoint-run": SourceEdgeKind.LOCAL_STATE,
    "convergence-state-review-cycle": SourceEdgeKind.LOCAL_STATE,
    "discovery-bootstrap": SourceEdgeKind.LOCAL_STATE,
    "discovery-candidate-reconciliation": SourceEdgeKind.LOCAL_STATE,
    "discovery-promotion-lifecycle": SourceEdgeKind.LOCAL_STATE,
    "greenfield-full-drive": SourceEdgeKind.OPERATOR,
    "local-workflow-orch-image": SourceEdgeKind.DOCKER,
    "mawf-playbook-blocker-reentry": SourceEdgeKind.OPERATOR,
}


def _provider_symbol(owner_id: str, profile_id: str, kind: str) -> str:
    return (
        f"observe_{owner_id.replace('-', '_')}_{profile_id.replace('-', '_')}_{kind}"
    )


def _factory(spec: ProviderSpec) -> ProviderFactory:
    def build(edge: SourceProbeEdge) -> ProductionSourceProbeBackend:
        return ProductionSourceProbeBackend(spec, edge)
    return build


_provider_specs = {
    (owner_id, profile_id): ProviderSpec(
        owner_sequence_id=owner_id,
        profile_id=profile_id,
        edge_kind=_OWNER_EDGE_KIND[owner_id],
        reconciliation_provider_symbol=_provider_symbol(
            owner_id, profile_id, "reconciliation"
        ),
        terminal_provider_symbol=_provider_symbol(owner_id, profile_id, "terminal"),
    )
    for owner_id, profiles in _OWNER_PROFILES.items()
    for profile_id in profiles
}
PROVIDER_SPECS: Mapping[tuple[str, str], ProviderSpec] = MappingProxyType(
    _provider_specs
)
PROVIDER_FACTORIES: Mapping[tuple[str, str], ProviderFactory] = MappingProxyType({
    key: _factory(spec) for key, spec in _provider_specs.items()
})


def _profile(preparation_artifact: Mapping[str, Any]) -> str:
    resolved = preparation_artifact.get("resolved_parameters")
    if not isinstance(resolved, Mapping):
        raise SourceProbeError("prepared-resolved-parameters-invalid")
    profile = resolved.get("command", resolved.get("mode", "default"))
    if not isinstance(profile, str) or not profile:
        raise SourceProbeError("prepared-source-profile-invalid")
    return profile


def build_production_transport(
    executable_contract: Mapping[str, Any],
    preparation_artifact: Mapping[str, Any],
    source_edges: SourceEdgeRegistry,
) -> ProductionObservationTransport:
    """Build the sole production transport from closed owner/profile authority."""
    if type(source_edges) is not SourceEdgeRegistry:
        raise SourceProbeError("typed-source-edge-registry-required")
    owner_id = preparation_artifact.get("owner_sequence_id")
    if not isinstance(owner_id, str) or not owner_id:
        raise SourceProbeError("prepared-owner-sequence-id-invalid")
    if executable_contract.get("owner_contract_sha256") != preparation_artifact.get(
        "owner_contract_sha256"
    ):
        raise SourceProbeError("prepared-owner-contract-mismatch")
    profile_id = _profile(preparation_artifact)
    key = (owner_id, profile_id)
    spec = PROVIDER_SPECS.get(key)
    factory = PROVIDER_FACTORIES.get(key)
    if spec is None or factory is None:
        raise SourceProbeError(f"production-source-provider-unavailable:{owner_id}:{profile_id}")
    for contract_name, expected_symbol in (
        ("reconciliation_contract", spec.reconciliation_provider_symbol),
        ("terminal_contract", spec.terminal_provider_symbol),
    ):
        contract = executable_contract.get(contract_name)
        if not isinstance(contract, Mapping):
            raise SourceProbeError(f"production-source-{contract_name}-invalid")
        matches = [
            item for item in contract.get("observables", [])
            if isinstance(item, Mapping) and item.get("profile") == profile_id
        ]
        if len(matches) != 1 or matches[0].get("provider_symbol") != expected_symbol:
            raise SourceProbeError("production-source-provider-contract-mismatch")
    edge = source_edges.require(spec.edge_kind)
    return ProductionObservationTransport(factory(edge))


def build_greenfield_frontier_transport(
    source_edges: SourceEdgeRegistry,
) -> GreenfieldFrontierTransport:
    """Construct the non-caller-selectable frontier reader from the closed edge row."""
    if type(source_edges) is not SourceEdgeRegistry:
        raise SourceProbeError("typed-source-edge-registry-required")
    return GreenfieldFrontierTransport(source_edges.require(SourceEdgeKind.OPERATOR))
