from __future__ import annotations

import copy

import pytest

from scripts import sequence_candidate_contract as contract


def context():
    return {
        "intended_outcome": "Deploy the service safely.",
        "repeatability_reason": "The deployment recurs.",
        "repeatability_evidence_ids": ["event-1"],
        "required_inputs": ["target environment"],
        "dependencies": [{"repository_key": "app", "path": "scripts/deploy.py"}],
        "failure_handling": [{"fingerprint": "a" * 64, "symptom": "exit nonzero", "response": "stop"}],
        "verification_contract": {
            "quality": "same-path", "expected_outcome": "passed", "success_evidence": "DEPLOY OK",
        },
        "effect_class": "external-reversible",
        "environment_annotations": ["requires target environment"],
        "semantic_flag_annotations": [{"step_ordinal": 0, "arg_index": 1}],
        "volatility_annotations": [{"step_ordinal": 0, "arg_index": 2, "kind": "task_id"}],
    }


def steps(task_id="task-a"):
    return [{
        "step_ordinal": 0, "step_id": "deploy", "argv": ["python3", "--target", task_id],
        "command_source": "script",
        "source_ref": {"repository_key": "app", "path": "scripts/deploy.py"},
        "operation_kind": "deploy",
    }]


def test_candidate_identity_normalizes_only_declared_volatility():
    first, first_hash = contract.build_candidate_identity(context(), steps("task-a"))
    second, second_hash = contract.build_candidate_identity(context(), steps("task-b"))

    assert first == second
    assert first_hash == second_hash
    assert first["steps"][0]["argv"][-1] == "<task_id>"


def test_candidate_identity_changes_for_semantic_command_or_effect_change():
    _, baseline = contract.build_candidate_identity(context(), steps())
    changed_steps = steps()
    changed_steps[0]["argv"][1] = "--region"
    _, command_changed = contract.build_candidate_identity(context(), changed_steps)
    changed_context = copy.deepcopy(context())
    changed_context["effect_class"] = "external-irreversible"
    _, effect_changed = contract.build_candidate_identity(changed_context, steps())

    assert command_changed != baseline
    assert effect_changed != baseline


def test_candidate_identity_rejects_unsupported_provenance_and_incomplete_order():
    invalid = steps()
    invalid[0]["command_source"] = "conversation"
    with pytest.raises(contract.CandidateContractError, match="invalid-command-source"):
        contract.build_candidate_identity(context(), invalid)
    invalid = steps()
    invalid[0]["step_ordinal"] = 1
    with pytest.raises(contract.CandidateContractError, match="noncontiguous-candidate-steps"):
        contract.build_candidate_identity(context(), invalid)


def test_final_effective_verification_uses_last_exact_bundle_event():
    base = {
        "event_type": "verification_recorded", "run_id": "run", "lineage_id": "lineage",
        "source_bundle_hash": "a" * 64, "quality": "same-path",
    }
    passed = {
        **base, "event_id": "pass", "outcome": "passed",
        "recorded_at_utc": "2026-07-16T00:00:00Z",
    }
    failed = {
        **base, "event_id": "fail", "outcome": "failed",
        "recorded_at_utc": "2026-07-16T00:01:00Z",
    }
    passed_later = {
        **passed, "event_id": "pass-later",
        "recorded_at_utc": "2026-07-16T00:02:00Z",
    }

    assert contract.final_effective_verification(
        [passed, failed], run_id="run", lineage_id="lineage", source_bundle_hash="a" * 64,
    ) is None
    assert contract.final_effective_verification(
        [failed, passed_later], run_id="run", lineage_id="lineage", source_bundle_hash="a" * 64,
    ) == passed_later
    assert contract.final_effective_verification(
        [passed], run_id="run", lineage_id="lineage", source_bundle_hash="b" * 64,
    ) is None


def test_operation_context_is_closed_and_requires_effect_attestation():
    missing = context()
    del missing["effect_class"]
    with pytest.raises(contract.CandidateContractError, match="invalid-operation-context-fields"):
        contract.normalize_operation_context(missing)
    unknown = context()
    unknown["extra"] = "not allowed"
    with pytest.raises(contract.CandidateContractError, match="invalid-operation-context-fields"):
        contract.normalize_operation_context(unknown)
