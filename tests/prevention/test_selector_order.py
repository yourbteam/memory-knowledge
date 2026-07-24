from __future__ import annotations

import pytest

from scripts import prevention_contract as contract
from scripts import prevention_registry, prevention_selector


def value(tag: contract.ParameterTag, raw):
    return contract.ParameterValue(tag=tag, value=raw)


def signature(*, implementation: str, effect: str = "local-reversible", verify: str = "1" * 64):
    return contract.OperationSignature(
        operation_kind="workflow-drive",
        effect_class=effect,
        verification_contract_sha256=verify,
        parameter_schema_sha256="2" * 64,
        action_class=contract.ActionClass.BASH,
        owner_implementation_id=implementation,
        source_bundle_sha256="3" * 64,
        repository_roots_sha256="4" * 64,
    )


def intent(parameters: tuple[contract.TypedParameter, ...], sig: contract.OperationSignature):
    mapping = {parameter.name: parameter.value for parameter in parameters}
    return contract.ActionIntent(
        intent_id="intent-1",
        task_id="task-1",
        run_id="run-1",
        requested_sequence_id="discovery-bootstrap",
        requested_implementation_id=sig.owner_implementation_id,
        compatibility_key=sig.compatibility_key(mapping),
        action_class=contract.ActionClass.BASH,
        parameters=parameters,
    )


def test_exact_parameter_mapping_allows_successor_activation():
    predecessor = signature(implementation="a" * 64)
    successor = signature(implementation="b" * 64)
    requested = intent((contract.TypedParameter("spec", value(contract.ParameterTag.PATH, "spec.json")),), predecessor)

    mapped = prevention_selector.validate_successor_activation(
        intent=requested,
        predecessor_signature=predecessor,
        successor_signature=successor,
        successor_specs=(contract.ParameterSpec("spec", contract.ParameterType.PATH, required=True),),
    )

    assert mapped == {"spec": value(contract.ParameterTag.PATH, "spec.json")}


def test_versioned_default_allows_compatible_added_parameter():
    predecessor = signature(implementation="a" * 64)
    successor = signature(implementation="b" * 64)
    requested = intent((contract.TypedParameter("spec", value(contract.ParameterTag.PATH, "spec.json")),), predecessor)
    default = value(contract.ParameterTag.BOOLEAN, False)

    mapped = prevention_selector.validate_successor_activation(
        intent=requested,
        predecessor_signature=predecessor,
        successor_signature=successor,
        successor_specs=(
            contract.ParameterSpec("spec", contract.ParameterType.PATH, required=True),
            contract.ParameterSpec("dry_run", contract.ParameterType.BOOLEAN, required=True),
        ),
        versioned_defaults={"dry_run": default},
    )

    assert mapped["dry_run"] == default


@pytest.mark.parametrize(
    ("parameters", "specs", "error"),
    [
        ((), (contract.ParameterSpec("spec", contract.ParameterType.PATH, required=True),), "missing-required"),
        (
            (contract.TypedParameter("spec", value(contract.ParameterTag.STRING, "wrong")),),
            (contract.ParameterSpec("spec", contract.ParameterType.PATH, required=True),),
            "type-mismatch",
        ),
        (
            (contract.TypedParameter("mode", value(contract.ParameterTag.ENUM, "fast")),),
            (contract.ParameterSpec("mode", contract.ParameterType.ENUM, required=True, enum_values=("full", "speed")),),
            "enum-mismatch",
        ),
    ],
)
def test_missing_type_and_enum_mappings_fail(parameters, specs, error):
    with pytest.raises(prevention_selector.SelectionError, match=error):
        prevention_selector.map_successor_parameters(dict((p.name, p.value) for p in parameters), specs)


@pytest.mark.parametrize(
    "successor",
    [
        signature(implementation="b" * 64, effect="external-reversible"),
        signature(implementation="b" * 64, verify="9" * 64),
    ],
)
def test_effect_or_verification_mismatch_cannot_activate_successor(successor):
    predecessor = signature(implementation="a" * 64)
    requested = intent((contract.TypedParameter("spec", value(contract.ParameterTag.PATH, "spec.json")),), predecessor)
    with pytest.raises(prevention_selector.SelectionError):
        prevention_selector.validate_successor_activation(
            intent=requested,
            predecessor_signature=predecessor,
            successor_signature=successor,
            successor_specs=(contract.ParameterSpec("spec", contract.ParameterType.PATH, required=True),),
        )


def test_selector_uses_mandatory_successor_before_registered_owner():
    rows, _ = prevention_registry.load_typed_registry()
    requested = contract.ActionIntent(
        intent_id="intent-1",
        task_id="task-1",
        run_id="run-1",
        requested_sequence_id="discovery-bootstrap",
        requested_implementation_id="a" * 64,
        compatibility_key="c" * 64,
        action_class=contract.ActionClass.BASH,
        parameters=(),
    )
    events = [{
        "event_type": "predecessor_prohibited",
        "predecessor_implementation_id": "a" * 64,
        "successor_implementation_id": "b" * 64,
        "successor_sequence_id": "discovery-promotion-lifecycle",
        "compatibility_key": "c" * 64,
    }]

    decision = prevention_selector.Selector(rows, events).select(requested)

    assert decision.kind == contract.DecisionKind.SELECT_SUCCESSOR
    assert decision.effective_implementation_id == "b" * 64


def test_selector_rejects_unknown_owner_without_fallback():
    rows, _ = prevention_registry.load_typed_registry()
    requested = contract.ActionIntent(
        intent_id="intent-1",
        task_id="task-1",
        run_id="run-1",
        requested_sequence_id="not-registered",
        requested_implementation_id="a" * 64,
        compatibility_key="c" * 64,
        action_class=contract.ActionClass.BASH,
        parameters=(),
    )

    decision = prevention_selector.Selector(rows, []).select(requested)

    assert decision.kind == contract.DecisionKind.REJECT
    assert decision.reason_code == "NO_REGISTERED_IMPLEMENTATION"
