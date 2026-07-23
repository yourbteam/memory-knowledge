from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import prevention_adapters, prevention_contract_materializer, prevention_registry
from scripts.prevention_contract import canonical_bytes, sha256_bytes


def _policy_evidence(owner_id, contract, *, kind, probe_result="SATISFIED"):
    profile = contract["observables"][0]["profile"]
    source = prevention_adapters._source_observable_evidence_for_owner(
        owner_id, profile
    )
    probes = source["profile"]["capture_schema"]["probe_ids"]
    probe_results = {probe: probe_result for probe in probes}
    plan = prevention_adapters.InvocationPlan(
        sequence_id=owner_id,
        argv=(),
        owner_contract_sha256="a" * 64,
        implementation_source_sha256="b" * 64,
        parameter_schema_sha256="c" * 64,
        resolved_parameters={},
        root_bindings={},
        binding_receipts={},
    )
    return prevention_adapters._evaluate_owner_profile_predicate(
        plan, contract, source, {"probes": probe_results}, kind=kind
    )


def test_materialized_executable_contracts_are_byte_stable_and_complete():
    expected = prevention_contract_materializer.materialize()
    path = prevention_contract_materializer.OUTPUT

    assert path.read_bytes() == canonical_bytes(expected)
    assert len(expected["owners"]) == 10
    assert {row["owner_sequence_id"] for row in expected["owners"]} == (
        prevention_registry.TERMINAL_OWNER_STATES[
            prevention_registry.AvailabilityPolicy.AVAILABLE
        ]
    )
    for row in expected["owners"]:
        stored = row["owner_contract_sha256"]
        payload = {key: value for key, value in row.items() if key != "owner_contract_sha256"}
        assert sha256_bytes(canonical_bytes(payload)) == stored
        assert row["clause_coverage"]
        assert row["authority_decision_ids"]
        proposal = json.loads(
            (prevention_contract_materializer.PROPOSALS / f"{row['owner_sequence_id']}.json")
            .read_text(encoding="utf-8")
        )
        covered = [item["proposal_pointer"] for item in row["clause_coverage"]]
        assert covered == sorted(
            prevention_contract_materializer._json_pointers(proposal, "")
        )
        assert len(covered) == len(set(covered))


def test_selected_owner_materialization_ignores_unrelated_source_drift(
    tmp_path: Path,
):
    proposals = tmp_path / "proposals"
    proposals.mkdir()
    for source in prevention_contract_materializer.PROPOSALS.glob("*.json"):
        (proposals / source.name).write_bytes(source.read_bytes())
    unrelated = proposals / "greenfield-full-drive.json"
    value = json.loads(unrelated.read_text(encoding="utf-8"))
    value["proposal_status"] = "PROPOSED"
    unrelated.write_text(json.dumps(value), encoding="utf-8")

    selected = prevention_contract_materializer.materialize(
        proposals, owner_ids=("commit-push-main",)
    )
    current = json.loads(
        prevention_contract_materializer.OUTPUT.read_text(encoding="utf-8")
    )
    merged = prevention_contract_materializer.merge_selected_owner(
        current, selected["owners"][0]
    )

    assert len(merged["owners"]) == len(prevention_contract_materializer.OWNER_IDS)
    assert next(
        row for row in merged["owners"]
        if row["owner_sequence_id"] == "commit-push-main"
    ) == selected["owners"][0]


def test_selected_owner_registry_validation_ignores_unrelated_source_drift(
    tmp_path: Path,
):
    proposals = tmp_path / "proposals"
    proposals.mkdir()
    for source in prevention_contract_materializer.PROPOSALS.glob("*.json"):
        (proposals / source.name).write_bytes(source.read_bytes())
    document = json.loads(
        prevention_contract_materializer.OUTPUT.read_text(encoding="utf-8")
    )
    owner = next(
        row for row in document["owners"]
        if row["owner_sequence_id"] == "greenfield-full-drive"
    )
    source = next(
        item for item in owner["implementation_sources"]
        if item["path"].endswith("mcp_server.py")
    )
    drifted_source = tmp_path / "unrelated-mcp-server.py"
    drifted_source.write_text("concurrent unrelated edit\n", encoding="utf-8")
    old_path = source["path"]
    source["path"] = str(drifted_source)

    proposal_path = proposals / "greenfield-full-drive.json"
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    proposal_source = next(
        item for item in proposal["sources"] if item["path"] == old_path
    )
    proposal_source["path"] = str(drifted_source)
    proposal_path.write_text(json.dumps(proposal), encoding="utf-8")
    owner["approved_proposal_sha256"] = sha256_bytes(canonical_bytes(proposal))
    base = {
        key: value for key, value in owner.items()
        if key not in {
            "acceptance_contract_sha256", "execution_admission",
            "owner_contract_sha256",
        }
    }
    owner["acceptance_contract_sha256"] = sha256_bytes(canonical_bytes(base))
    owner["owner_contract_sha256"] = sha256_bytes(canonical_bytes({
        key: value for key, value in owner.items()
        if key != "owner_contract_sha256"
    }))
    executable = tmp_path / "owner-executable-contracts.json"
    executable.write_bytes(canonical_bytes(document))

    selected, _ = prevention_registry.load_executable_owner_contracts(
        executable,
        proposals_dir=proposals,
        source_validation_owner_ids=frozenset({"commit-push-main"}),
    )
    assert "commit-push-main" in selected
    with pytest.raises(
        prevention_registry.RegistryError,
        match="source-hash-drift:greenfield-full-drive",
    ):
        prevention_registry.load_executable_owner_contracts(
            executable, proposals_dir=proposals
        )


def test_materializer_compiles_cross_field_prose_to_closed_predicates():
    owners = {
        row["owner_sequence_id"]: row
        for row in prevention_contract_materializer.materialize()["owners"]
    }
    auth_nodes = owners["claude-auth-token-refresh"]["parameter_contract"][
        "normalized_nodes"
    ]
    container = next(
        item for item in auth_nodes
        if item["source_pointer"] == "/parameter_contract/container_key"
    )
    assert all(
        "credential_source is approved_container_credential" not in json.dumps(predicate)
        for predicate in container["predicate"]["predicates"]
    )
    assert any(
        predicate["op"] == "REQUIRED_IF"
        and predicate.get("condition", {}).get("op") == "ANY"
        for predicate in container["predicate"]["predicates"]
    )


def test_materializer_rejects_changed_cross_field_prose(tmp_path: Path):
    proposals = tmp_path / "proposals"
    proposals.mkdir()
    for source in prevention_contract_materializer.PROPOSALS.glob("*.json"):
        (proposals / source.name).write_bytes(source.read_bytes())
    target = proposals / "discovery-bootstrap.json"
    value = json.loads(target.read_text(encoding="utf-8"))
    value["parameter_contract"]["repo_roots_file"]["required_when"] = "some other rule"
    target.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(
        prevention_contract_materializer.MaterializationError,
        match="unmapped-cross-field-condition",
    ):
        prevention_contract_materializer.materialize(proposals)


def test_every_budget_formula_is_a_closed_derivation_tree():
    allowed = {"CONST", "VAR", "ADD", "MULTIPLY", "SUM"}

    def assert_closed(node):
        assert node["op"] in allowed
        for operand in node.get("operands", []):
            assert_closed(operand)
        if "expression" in node:
            assert_closed(node["expression"])

    for owner in prevention_contract_materializer.materialize()["owners"]:
        budget = owner["budget_contract"]
        if "derivation_ast" in budget:
            assert_closed(budget["derivation_ast"])
        else:
            assert budget["profiles"]
            for profile in budget["profiles"].values():
                assert_closed(profile["productive_task_count_ast"])
                assert len(profile["source_sha256"]) == 64


def test_registry_separates_availability_from_executable_admission():
    rows, _ = prevention_registry.load_typed_registry()
    available = [row for row in rows if row["availability_policy"] == "AVAILABLE"]
    blocked = [row for row in rows if row["availability_policy"] != "AVAILABLE"]

    assert len(available) == 10
    assert len(blocked) == 15
    assert all(row["executable_contract"] is not None for row in available)
    assert all(row["executable_contract"] is None for row in blocked)
    assert all(
        row["owner_contract_sha256"] == row["executable_contract_sha256"]
        for row in available
    )
    assert all(
        row["executable_contract"]["execution_admission"]["contract_verification"]
        == "VERIFIED"
        for row in available
    )
    assert sum(
        row["executable_contract"]["execution_admission"]["dispatch_admission"]
        == "STANDALONE"
        for row in available
    ) == 9
    parent_gated = next(
        row for row in available
        if row["owner_sequence_id"] == "mawf-playbook-blocker-reentry"
    )
    assert parent_gated["executable_contract"]["execution_admission"][
        "dispatch_admission"
    ] == "PARENT_GATED"


def test_every_executable_owner_has_an_explicit_finite_reconciler():
    owners = prevention_contract_materializer.materialize()["owners"]

    assert len(owners) == 10
    for owner in owners:
        handler_name = owner["reconciliation_contract"]["handler"]
        assert handler_name == (
            f"reconcile_{owner['owner_sequence_id'].replace('-', '_')}"
        )
        assert callable(prevention_adapters.__dict__.get(handler_name))


def test_every_owner_reconciler_requires_full_policy_bound_evidence():
    for owner in prevention_contract_materializer.materialize()["owners"]:
        owner_id = owner["owner_sequence_id"]
        policy = owner["reconciliation_contract"]
        handler = prevention_adapters.__dict__[policy["handler"]]

        def observation(classification: str, **overrides):
            raw_result = {
                "identity": "CONFLICT" if classification == "INDETERMINATE" else "MATCH",
                "postcondition": (
                    "APPLIED" if classification == "ALREADY_APPLIED"
                    else "NOT_APPLIED" if classification == "NOT_APPLIED"
                    else "NOT_APPLIED"
                ),
                "prepared_prestate": (
                    "UNCHANGED" if classification == "NOT_APPLIED" else "CHANGED"
                ),
                "mutation_receipt": (
                    "ABSENT" if classification == "NOT_APPLIED" else "PRESENT"
                ),
            }
            values = {
                "owner_sequence_id": owner_id,
                "effect_id": "e" * 64,
                "reconciliation_policy_sha256": policy["policy_sha256"],
                "preparation_artifact_sha256": "f" * 64,
                "provider_id": policy["observables"][0]["provider_symbol"],
                "observed_at_utc": prevention_adapters.datetime.now(
                    prevention_adapters.UTC
                ).isoformat(),
                "raw_result": raw_result,
                "observable_ownership": {
                    "owner_sequence_id": owner_id,
                    "effect_id": "e" * 64,
                },
                "evidence": {
                    "raw_observables": [{"fixture": owner_id}],
                    **_policy_evidence(
                        owner_id, policy, kind="reconciliation"
                    ),
                },
            }
            values.update(overrides)
            return prevention_adapters.ReconciliationObservation(**values)

        for classification in (
            "ALREADY_APPLIED", "NOT_APPLIED", "INDETERMINATE"
        ):
            assert handler(
                observation(classification), reconciliation_contract=policy
            ).classification == classification
        valid = observation("ALREADY_APPLIED")
        with pytest.raises(
            prevention_adapters.AdapterError,
            match="reconciliation-owner-policy-not-evaluated",
        ):
            handler(
                prevention_adapters.ReconciliationObservation(**{
                    **valid.__dict__,
                    "evidence": {
                        **valid.evidence,
                        "owner_semantic_predicate_sha256": "0" * 64,
                    },
                }),
                reconciliation_contract=policy,
            )
        with pytest.raises(prevention_adapters.AdapterError, match="stale"):
            handler(
                observation("ALREADY_APPLIED", observed_at_utc="2000-01-01T00:00:00Z"),
                reconciliation_contract=policy,
            )
        with pytest.raises(
            prevention_adapters.AdapterError, match="result-fields-invalid"
        ):
            handler(
                observation("ALREADY_APPLIED", raw_result={}),
                reconciliation_contract=policy,
            )
        with pytest.raises(
            prevention_adapters.AdapterError, match="policy-hash-mismatch"
        ):
            handler(
                observation(
                    "ALREADY_APPLIED", reconciliation_policy_sha256="0" * 64
                ),
                reconciliation_contract=policy,
            )


def test_every_executable_owner_has_an_explicit_semantic_terminal_verifier():
    owners = prevention_contract_materializer.materialize()["owners"]

    def valid_result_envelope(owner_id: str):
        if owner_id == "mawf-playbook-blocker-reentry":
            return {
                "stage": "reenter",
                "mode": "restart-workflow",
                "workflow": "research-workflow",
                "taskGuid": "acceptance",
                "targetRunId": "22222222-2222-4222-8222-222222222222",
                "verdict": "running",
                "finalOk": True,
                "errorCode": None,
            }
        if owner_id == "convergence-checkpoint-run":
            return {
                "ok": True,
                "verdict": "PASS",
                "checkpoint": {
                    "schema_version": 1,
                    "verdict": "CHECKPOINT_APPLIED",
                    "approval_id_sha256": "1" * 64,
                    "stage": "implementation",
                    "outer_iteration": 1,
                    "repository_path_sha256": "2" * 64,
                    "helper_sha256": "3" * 64,
                    "child_intent_sha256": "4" * 64,
                    "guard_receipt_id": "guard-receipt",
                    "state_before_sha256": "5" * 64,
                    "state_after_accept_sha256": "6" * 64,
                    "state_after_guard_sha256": "7" * 64,
                    "accept_receipt": {"returncode": 0},
                    "guard_receipt": {"returncode": 0},
                },
                "child": {
                    "owner_sequence_id": "child-owner",
                    "owner_contract_sha256": "8" * 64,
                    "intent_id": "child-intent",
                    "effect_id": "9" * 64,
                    "unit_budget_sha256": "a" * 64,
                    "terminal_artifact_sha256": "b" * 64,
                    "semantic_verdict": "PASS",
                },
            }
        if owner_id == "convergence-state-review-cycle":
            return {
                "ok": True,
                "cycle_status": "DRY_RUN",
                "operation_count": 1,
                "convergence_status": "complete",
                "initial_state_sha256": "c" * 64,
                "final_state_sha256": "c" * 64,
            }
        return {"ok": True}

    for owner in owners:
        owner_id = owner["owner_sequence_id"]
        handler_name = owner["terminal_contract"]["handler"]
        handler = prevention_adapters.__dict__.get(handler_name)
        assert handler_name == f"verify_{owner_id.replace('-', '_')}"
        assert callable(handler)
        observation = prevention_adapters.TerminalObservation(
            owner_sequence_id=owner_id,
            effect_id="e" * 64,
            result_kind="EXECUTED_RESULT",
            terminal_policy_sha256=owner["terminal_contract"]["policy_sha256"],
            preparation_artifact_sha256="f" * 64,
            provider_id=owner["terminal_contract"]["observables"][0]["provider_symbol"],
            observed_at_utc=prevention_adapters.datetime.now(
                prevention_adapters.UTC
            ).isoformat(),
            raw_result={
                "semantic": "PASS", "output_schema": "VALID",
                "identity": "MATCH", "work_state": "TERMINAL",
            },
            evidence={
                "fixture": owner_id,
                **_policy_evidence(
                    owner_id, owner["terminal_contract"], kind="terminal"
                ),
            },
        )
        evidence = handler(
            result_kind="EXECUTED_RESULT",
            result={
                "returncode": 0,
                "stdout_encoding": "JSON_OBJECT",
                "stdout_sha256": "a" * 64,
                "stderr_sha256": "b" * 64,
                "result_envelope": valid_result_envelope(owner_id),
            },
            semantic_observation=observation,
            terminal_contract=owner["terminal_contract"],
        )
        assert evidence["owner_sequence_id"] == owner_id
        with pytest.raises(
            prevention_adapters.AdapterError,
            match="terminal-owner-policy-not-evaluated",
        ):
            handler(
                result_kind="EXECUTED_RESULT",
                result={
                    "returncode": 0,
                    "stdout_encoding": "JSON_OBJECT",
                    "stdout_sha256": "a" * 64,
                    "stderr_sha256": "b" * 64,
                    "result_envelope": valid_result_envelope(owner_id),
                },
                semantic_observation=prevention_adapters.TerminalObservation(**{
                    **observation.__dict__,
                    "evidence": {
                        **observation.evidence,
                        "evaluated_probe_ids": ["forged-probe"],
                    },
                }),
                terminal_contract=owner["terminal_contract"],
            )
        with pytest.raises(prevention_adapters.AdapterError, match="semantic-observation-failed"):
            handler(
                result_kind="EXECUTED_RESULT",
                result={
                    "returncode": 0,
                    "stdout_encoding": "JSON_OBJECT",
                    "stdout_sha256": "a" * 64,
                    "stderr_sha256": "b" * 64,
                    "result_envelope": valid_result_envelope(owner_id),
                },
                semantic_observation=prevention_adapters.TerminalObservation(
                    **{
                        **observation.__dict__,
                        "raw_result": {
                            **observation.raw_result, "semantic": "FAIL"
                        },
                    }
                ),
                terminal_contract=owner["terminal_contract"],
            )


def test_every_owner_profile_uses_real_transport_capture_before_decision():
    class CaptureTransport:
        def query(self, request):
            ownership = {
                "effect_id": request["effect_id"],
                "owner_sequence_id": request["owner_sequence_id"],
                "preparation_artifact_sha256": request["preparation_artifact_sha256"],
            }
            now = prevention_adapters.datetime.now(prevention_adapters.UTC).isoformat()
            return {
                "identity": "MATCH", "observed_at_utc": now,
                "ownership": ownership, "prestate": "CHANGED",
                "probes": {probe: "SATISFIED" for probe in request["probe_ids"]},
                "receipt": "PRESENT",
                "source_evidence_sha256": request["source_evidence_sha256"],
                "work_state": "TERMINAL",
            }

    for owner in prevention_contract_materializer.materialize()["owners"]:
        for spec in owner["reconciliation_contract"]["observables"]:
            assert callable(prevention_adapters.__dict__.get(spec["provider_symbol"]))
            plan = prevention_adapters.InvocationPlan(
                sequence_id=owner["owner_sequence_id"], argv=("true",),
                owner_contract_sha256=owner["owner_contract_sha256"],
                implementation_source_sha256="b" * 64,
                parameter_schema_sha256="c" * 64,
                resolved_parameters={"command": spec["profile"]},
                root_bindings={}, binding_receipts={},
            )
            state = {
                "effect_id": "e" * 64,
                "preparation_artifact_sha256": "f" * 64,
                "observation_targets": {},
                "prepared_prestate_identities": {},
                "prepared_receipt_identities": {},
            }
            preparation = {
                "reconciliation_contract": owner["reconciliation_contract"],
                "observation_targets": {},
                "prepared_prestate_identities": {},
                "prepared_receipt_identities": {},
            }
            observation = prevention_adapters.acquire_reconciliation_observation(
                plan, state, preparation, CaptureTransport()
            )
            handler = prevention_adapters.__dict__[owner["reconciliation_contract"]["handler"]]
            assert handler(
                observation,
                reconciliation_contract=owner["reconciliation_contract"],
            ).classification == "ALREADY_APPLIED"

        for spec in owner["terminal_contract"]["observables"]:
            assert callable(prevention_adapters.__dict__.get(spec["provider_symbol"]))
            plan = prevention_adapters.InvocationPlan(
                sequence_id=owner["owner_sequence_id"], argv=("true",),
                owner_contract_sha256=owner["owner_contract_sha256"],
                implementation_source_sha256="b" * 64,
                parameter_schema_sha256="c" * 64,
                resolved_parameters={"command": spec["profile"]},
                root_bindings={}, binding_receipts={},
            )
            state = {
                "effect_id": "e" * 64,
                "preparation_artifact_sha256": "f" * 64,
                "observation_targets": {},
                "prepared_prestate_identities": {},
                "prepared_receipt_identities": {},
            }
            observed = prevention_adapters.acquire_terminal_observation(
                plan, state, "EXECUTED_RESULT", owner["terminal_contract"],
                CaptureTransport(),
            )
            assert observed.raw_result == {
                "semantic": "PASS", "output_schema": "VALID",
                "identity": "MATCH", "work_state": "TERMINAL",
            }
def test_executable_contract_loader_rejects_proposal_and_contract_drift(tmp_path: Path):
    document = json.loads(
        prevention_contract_materializer.OUTPUT.read_text(encoding="utf-8")
    )
    document["owners"][0]["budget_contract"]["atomic_task_cap_milliseconds"] -= 1
    drifted = tmp_path / "owner-executable-contracts.json"
    drifted.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(prevention_registry.RegistryError, match="contract-hash-drift"):
        prevention_registry.load_executable_owner_contracts(drifted)


def test_materializer_rejects_unapproved_or_incomplete_proposal(tmp_path: Path):
    proposals = tmp_path / "proposals"
    proposals.mkdir()
    for source in prevention_contract_materializer.PROPOSALS.glob("*.json"):
        (proposals / source.name).write_bytes(source.read_bytes())
    first = proposals / f"{prevention_contract_materializer.OWNER_IDS[0]}.json"
    value = json.loads(first.read_text(encoding="utf-8"))
    value["proposal_status"] = "PROPOSED"
    first.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(
        prevention_contract_materializer.MaterializationError,
        match="proposal-not-executable",
    ):
        prevention_contract_materializer.materialize(proposals)


def test_materializer_rejects_source_correction_not_bound_to_approved_post_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    proposals = tmp_path / "proposals"
    proposals.mkdir()
    for source in prevention_contract_materializer.PROPOSALS.glob("*.json"):
        (proposals / source.name).write_bytes(source.read_bytes())
    target = proposals / "mawf-playbook-blocker-reentry.json"
    value = json.loads(target.read_text(encoding="utf-8"))
    value["source"]["approved_post_correction_sha256"] = "0" * 64
    target.write_text(json.dumps(value), encoding="utf-8")
    monkeypatch.setattr(
        prevention_contract_materializer,
        "SOURCE_VERIFICATION",
        tmp_path / "no-source-verification.json",
    )

    with pytest.raises(
        prevention_contract_materializer.MaterializationError,
        match="source-correction-not-approved",
    ):
        prevention_contract_materializer.materialize(proposals)
