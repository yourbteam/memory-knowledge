#!/usr/bin/env python3
"""Deterministic pre-action owner selection and corrected-path activation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

try:
    from scripts.prevention_contract import (
        ActionIntent,
        DecisionKind,
        OperationSignature,
        ParameterSpec,
        ParameterTag,
        ParameterType,
        ParameterValue,
    )
except ModuleNotFoundError:  # direct script execution
    from prevention_contract import (
        ActionIntent,
        DecisionKind,
        OperationSignature,
        ParameterSpec,
        ParameterTag,
        ParameterType,
        ParameterValue,
    )


class SelectionError(ValueError):
    """Raised when a corrected path is not provably compatible."""


@dataclass(frozen=True)
class DispatchDecision:
    decision_id: str
    intent_id: str
    kind: DecisionKind
    reason_code: str
    effective_sequence_id: str | None = None
    effective_implementation_id: str | None = None
    owner_contract_sha256: str | None = None

    def event_payload(self, *, selector_milliseconds: int) -> tuple[str, dict[str, Any]]:
        base = {
            "intent_id": self.intent_id,
            "decision_id": self.decision_id,
            "decision_kind": self.kind.value,
            "reason_code": self.reason_code,
            "selector_milliseconds": selector_milliseconds,
        }
        if self.kind == DecisionKind.REJECT:
            return "dispatch_rejected", base
        return "dispatch_selected", {
            **base,
            "effective_sequence_id": self.effective_sequence_id,
            "effective_implementation_id": self.effective_implementation_id,
            "selected_owner_sequence_id": self.effective_sequence_id,
            "selected_owner_contract_sha256": self.owner_contract_sha256,
        }


def _tag_for_spec(spec: ParameterSpec) -> ParameterTag:
    if spec.secret:
        return ParameterTag.SECRET_HANDLE
    return ParameterTag(spec.type.value)


def validate_parameter_value(spec: ParameterSpec, value: ParameterValue) -> None:
    if value.tag != _tag_for_spec(spec):
        raise SelectionError(f"parameter-type-mismatch:{spec.name}")
    if spec.type == ParameterType.ENUM and value.value not in spec.enum_values:
        raise SelectionError(f"parameter-enum-mismatch:{spec.name}")


def map_successor_parameters(
    predecessor: Mapping[str, ParameterValue],
    successor_specs: Sequence[ParameterSpec],
    *,
    versioned_defaults: Mapping[str, ParameterValue] | None = None,
) -> dict[str, ParameterValue]:
    defaults = dict(versioned_defaults or {})
    specs = {spec.name: spec for spec in successor_specs}
    if len(specs) != len(successor_specs):
        raise SelectionError("duplicate-successor-parameter-spec")
    unknown = set(predecessor) - set(specs)
    if unknown:
        raise SelectionError("successor-removed-parameter:" + ",".join(sorted(unknown)))
    mapped: dict[str, ParameterValue] = {}
    for name, spec in specs.items():
        if name in predecessor:
            value = predecessor[name]
        elif name in defaults:
            value = defaults[name]
        elif spec.required:
            raise SelectionError(f"successor-missing-required-parameter:{name}")
        else:
            continue
        validate_parameter_value(spec, value)
        mapped[name] = value
    if set(defaults) - set(specs):
        raise SelectionError("default-for-unknown-successor-parameter")
    return mapped


def validate_successor_activation(
    *,
    intent: ActionIntent,
    predecessor_signature: OperationSignature,
    successor_signature: OperationSignature,
    successor_specs: Sequence[ParameterSpec],
    versioned_defaults: Mapping[str, ParameterValue] | None = None,
) -> dict[str, ParameterValue]:
    if predecessor_signature.operation_kind != successor_signature.operation_kind:
        raise SelectionError("successor-operation-kind-mismatch")
    if predecessor_signature.effect_class != successor_signature.effect_class:
        raise SelectionError("successor-effect-class-mismatch")
    if (
        predecessor_signature.verification_contract_sha256
        != successor_signature.verification_contract_sha256
    ):
        raise SelectionError("successor-verification-contract-mismatch")
    if predecessor_signature.action_class != successor_signature.action_class:
        raise SelectionError("successor-action-class-mismatch")
    mapped = map_successor_parameters(
        intent.parameter_map(), successor_specs, versioned_defaults=versioned_defaults
    )
    predecessor_key = predecessor_signature.compatibility_key(intent.parameter_map())
    successor_key = successor_signature.compatibility_key({
        name: mapped[name] for name in intent.parameter_map()
    })
    if intent.compatibility_key != predecessor_key or successor_key != predecessor_key:
        raise SelectionError("successor-compatibility-key-mismatch")
    return mapped


class Selector:
    def __init__(self, registry_rows: Sequence[Mapping[str, Any]], events: Sequence[Mapping[str, Any]]):
        self.registry = {str(row["sequence_id"]): row for row in registry_rows}
        self.prohibitions = [
            event for event in events if event.get("event_type") == "predecessor_prohibited"
        ]

    def select(self, intent: ActionIntent) -> DispatchDecision:
        matching = [
            event for event in self.prohibitions
            if event["predecessor_implementation_id"] == intent.requested_implementation_id
            and event["compatibility_key"] == intent.compatibility_key
        ]
        if matching:
            prohibition = matching[-1]
            successor_id = prohibition["successor_sequence_id"]
            successor = self.registry.get(successor_id)
            if successor is None:
                return self._reject(intent, "PROHIBITED_WITHOUT_REGISTERED_SUCCESSOR")
            if successor.get("availability_policy") != "AVAILABLE" or not successor.get("owner_contract_sha256"):
                return self._reject(intent, "PROHIBITED_SUCCESSOR_UNAVAILABLE")
            if intent.action_class.value not in successor.get("registered_host_action_classes", ()):
                return self._reject(intent, "UNREGISTERED_ACTION_CLASS")
            return DispatchDecision(
                decision_id=str(uuid.uuid4()),
                intent_id=intent.intent_id,
                kind=DecisionKind.SELECT_SUCCESSOR,
                reason_code="MANDATORY_VERIFIED_SUCCESSOR",
                effective_sequence_id=successor_id,
                effective_implementation_id=prohibition["successor_implementation_id"],
                owner_contract_sha256=str(successor["owner_contract_sha256"]),
            )
        owner = self.registry.get(intent.requested_sequence_id)
        if owner is None:
            return self._reject(intent, "NO_REGISTERED_IMPLEMENTATION")
        availability = owner.get("availability_policy")
        if availability != "AVAILABLE" or not owner.get("owner_contract_sha256"):
            return self._reject(intent, str(availability or "OWNER_CONTRACT_UNRESOLVED"))
        if intent.action_class.value not in owner.get("registered_host_action_classes", ()):
            return self._reject(intent, "UNREGISTERED_ACTION_CLASS")
        return DispatchDecision(
            decision_id=str(uuid.uuid4()),
            intent_id=intent.intent_id,
            kind=DecisionKind.SELECT_REGISTERED,
            reason_code="CANONICAL_REGISTERED_OWNER",
            effective_sequence_id=intent.requested_sequence_id,
            effective_implementation_id=intent.requested_implementation_id,
            owner_contract_sha256=str(owner["owner_contract_sha256"]),
        )

    @staticmethod
    def _reject(intent: ActionIntent, reason: str) -> DispatchDecision:
        return DispatchDecision(
            decision_id=str(uuid.uuid4()),
            intent_id=intent.intent_id,
            kind=DecisionKind.REJECT,
            reason_code=reason,
        )
