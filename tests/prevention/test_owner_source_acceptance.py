from __future__ import annotations

import inspect
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import (
    prevention_controller,
    prevention_contract,
    prevention_contract_materializer,
    prevention_owner_acceptance,
    prevention_owner_acceptance_cases,
    prevention_owner_acceptance_fixtures,
    prevention_owner_acceptance_producer,
    prevention_source_probes,
)


def test_discovery_promotion_fixture_task_identity_binds_ephemeral_root(
    tmp_path: Path,
):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    profile = "correct"
    first_identity = prevention_owner_acceptance_fixtures._discovery_promotion_task_id(
        first, profile,
    )
    assert first_identity == (
        prevention_owner_acceptance_fixtures._discovery_promotion_task_id(
            first, profile,
        )
    )
    assert first_identity != (
        prevention_owner_acceptance_fixtures._discovery_promotion_task_id(
            second, profile,
        )
    )


def test_acceptance_repository_binding_returns_canonical_root_through_symlink(
    tmp_path: Path,
):
    actual_root = tmp_path / "actual"
    actual_root.mkdir()
    linked_root = tmp_path / "linked"
    linked_root.symlink_to(actual_root, target_is_directory=True)
    provider = prevention_owner_acceptance_fixtures.AcceptanceBindingProvider(
        linked_root,
    )

    resolution = provider.resolve(SimpleNamespace(
        consumable=False,
        parameter_type="ENUM_FROM_REGISTRY",
        owner_sequence_id="commit-push-main",
        parameter_name="repository_key",
        key_or_resource_id="acceptance",
        expected_scope_sha256="a" * 64,
        provider_id="repository-registry",
        version_id=None,
    ))

    assert resolution.execution_value == str(
        (actual_root / "git-repository").resolve()
    )


class _CapturedEdge:
    def __init__(self):
        self.requests = []

    def capture(self, request):
        self.requests.append(dict(request))
        identity = prevention_contract.sha256_bytes(
            prevention_contract.canonical_bytes({
                "effect_id": request["effect_id"],
                "owner_sequence_id": request["owner_sequence_id"],
                "profile": request["profile"],
            })
        )
        return prevention_source_probes.SourceProbeCapture(
            identity=prevention_source_probes.SourceHashFact(
                observed_sha256=identity,
                known=True,
            ),
            ownership={
                "effect_id": request["effect_id"],
                "owner_sequence_id": request["owner_sequence_id"],
                "preparation_artifact_sha256": request[
                    "preparation_artifact_sha256"
                ],
            },
            prestate=prevention_source_probes.SourceHashFact(
                observed_sha256=None,
                known=True,
            ),
            receipt=prevention_source_probes.SourceReceiptFact(
                present=False, known=True, effect_id=None,
                preparation_artifact_sha256=None,
            ),
            work_state=prevention_source_probes.SourceWorkStateFact(
                terminal=False, detached=True,
            ),
            probes={
                probe: prevention_source_probes.SourceProbeFact(
                    observed_sha256=None, known=True, absent=True,
                )
                for probe in request["probe_ids"]
            },
        )


def _registry(edge):
    return prevention_source_probes.SourceEdgeRegistry(
        local_state=edge,
        git=edge,
        docker=edge,
        credential=edge,
        operator=edge,
    )


def _preparation(owner, profile):
    return {
        "owner_sequence_id": owner["owner_sequence_id"],
        "owner_contract_sha256": owner["owner_contract_sha256"],
        "resolved_parameters": {"command": profile},
        "observation_targets": {"target": "a" * 64},
        "prepared_prestate_identities": {"source": "b" * 64},
        "prepared_receipt_identities": {},
    }


def test_production_provider_map_is_immutable_and_complete_for_all_profiles():
    owners = prevention_contract_materializer.materialize()["owners"]
    expected = {
        (owner["owner_sequence_id"], spec["profile"])
        for owner in owners
        for spec in owner["reconciliation_contract"]["observables"]
    }
    assert len({owner_id for owner_id, _profile in expected}) == 10
    assert len(expected) == 44
    assert set(prevention_source_probes.PROVIDER_FACTORIES) == expected
    assert set(prevention_source_probes.PROVIDER_SPECS) == expected
    with pytest.raises(TypeError):
        prevention_source_probes.PROVIDER_FACTORIES[("caller", "selected")] = object()


def test_proof_scan_selects_current_successor_and_preserves_stale_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    owner = next(
        item for item in prevention_contract_materializer.materialize()["owners"]
        if item["owner_sequence_id"] == "greenfield-full-drive"
    )
    current_sha = "a" * 64
    stale_sha = "b" * 64
    for value in (current_sha, stale_sha):
        (tmp_path / f"{value}.json").touch()
    base = {
        "owner_sequence_id": owner["owner_sequence_id"],
        "profile_id": "validate-fresh",
        "proof_kind": "controller_runtime_positive",
        "case_id": "greenfield-full-drive/validate-fresh/v1",
        "acceptance_contract_sha256": owner["acceptance_contract_sha256"],
        "parameter_policy_sha256": owner["parameter_contract"]["policy_sha256"],
        "reconciliation_policy_sha256": owner["reconciliation_contract"]["policy_sha256"],
        "terminal_policy_sha256": owner["terminal_contract"]["policy_sha256"],
        "provider_implementation_sha256": "c" * 64,
        "source_bindings": owner["implementation_sources"],
        "test_bindings": [
            {
                "path": str(path),
                "sha256": prevention_contract.sha256_bytes(path.read_bytes()),
            }
            for path in (
                prevention_owner_acceptance.PRODUCER_PATH,
                prevention_owner_acceptance.FIXTURES_PATH,
            )
        ],
    }
    traces = {
        current_sha: base,
        stale_sha: {**base, "provider_implementation_sha256": "d" * 64},
    }
    monkeypatch.setattr(prevention_owner_acceptance, "TRACE_DIR", tmp_path)
    monkeypatch.setattr(
        prevention_owner_acceptance,
        "_load_trace",
        lambda trace_sha256, **_kwargs: traces[trace_sha256],
    )

    assert prevention_owner_acceptance._scan_traces(
        [owner], "c" * 64,
    ) == {
        (
            "greenfield-full-drive",
            "validate-fresh",
            "controller_runtime_positive",
        ): current_sha,
    }


def test_proof_scan_chooses_stable_representative_for_two_current_successors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    owner = next(
        item for item in prevention_contract_materializer.materialize()["owners"]
        if item["owner_sequence_id"] == "greenfield-full-drive"
    )
    trace = {
        "owner_sequence_id": owner["owner_sequence_id"],
        "profile_id": "validate-fresh",
        "proof_kind": "controller_runtime_positive",
        "case_id": "greenfield-full-drive/validate-fresh/v1",
        "acceptance_contract_sha256": owner["acceptance_contract_sha256"],
        "parameter_policy_sha256": owner["parameter_contract"]["policy_sha256"],
        "reconciliation_policy_sha256": owner["reconciliation_contract"]["policy_sha256"],
        "terminal_policy_sha256": owner["terminal_contract"]["policy_sha256"],
        "provider_implementation_sha256": "c" * 64,
        "source_bindings": owner["implementation_sources"],
        "test_bindings": [
            {
                "path": str(path),
                "sha256": prevention_contract.sha256_bytes(path.read_bytes()),
            }
            for path in (
                prevention_owner_acceptance.PRODUCER_PATH,
                prevention_owner_acceptance.FIXTURES_PATH,
            )
        ],
    }
    for value in ("a" * 64, "b" * 64):
        (tmp_path / f"{value}.json").touch()
    monkeypatch.setattr(prevention_owner_acceptance, "TRACE_DIR", tmp_path)
    monkeypatch.setattr(
        prevention_owner_acceptance, "_load_trace",
        lambda _trace_sha256, **_kwargs: trace,
    )

    assert prevention_owner_acceptance._scan_traces([owner], "c" * 64) == {
        (
            "greenfield-full-drive",
            "validate-fresh",
            "controller_runtime_positive",
        ): "a" * 64,
    }


def test_report_assembly_fails_closed_without_current_trace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    owner = next(
        item for item in prevention_contract_materializer.materialize()["owners"]
        if item["owner_sequence_id"] == "greenfield-full-drive"
    )
    contracts = tmp_path / "contracts.json"
    contracts.write_bytes(prevention_contract.canonical_bytes({"owners": [owner]}))
    traces = tmp_path / "traces"
    traces.mkdir()
    monkeypatch.setattr(prevention_owner_acceptance, "TRACE_DIR", traces)

    with pytest.raises(
        prevention_owner_acceptance.AcceptanceError,
        match="owner-proof-current-trace-missing",
    ):
        prevention_owner_acceptance.assemble_report(contracts)


def test_zero_input_batch_derives_every_profile_and_scenario(
    monkeypatch: pytest.MonkeyPatch,
):
    owners = [
        {
            "owner_sequence_id": "owner-b",
            "reconciliation_contract": {
                "observables": [{"profile": "two"}, {"profile": "one"}],
            },
        },
        {
            "owner_sequence_id": "owner-a",
            "reconciliation_contract": {"observables": [{"profile": "only"}]},
        },
    ]
    observed = []
    monkeypatch.setattr(
        prevention_owner_acceptance_producer,
        "materialize",
        lambda: {"owners": owners},
    )
    monkeypatch.setattr(
        prevention_owner_acceptance_producer,
        "write_positive_traces",
        lambda owner, profile: observed.append((owner, profile, "positive"))
        or ["positive-1", "positive-2", "positive-3"],
    )
    monkeypatch.setattr(
        prevention_owner_acceptance_producer,
        "write_negative_trace",
        lambda owner, profile: observed.append((owner, profile, "negative"))
        or "negative",
    )
    monkeypatch.setattr(
        prevention_owner_acceptance_producer,
        "write_crash_traces",
        lambda owner, profile: observed.append((owner, profile, "crash"))
        or ["crash-1", "crash-2"],
    )

    assert prevention_owner_acceptance_producer.main(["--all-current"]) == 0
    assert observed == [
        ("owner-b", "one", "positive"),
        ("owner-b", "one", "negative"),
        ("owner-b", "one", "crash"),
        ("owner-b", "two", "positive"),
        ("owner-b", "two", "negative"),
        ("owner-b", "two", "crash"),
        ("owner-a", "only", "positive"),
        ("owner-a", "only", "negative"),
        ("owner-a", "only", "crash"),
    ]


def test_every_contract_profile_builds_only_its_closed_production_provider():
    edge = _CapturedEdge()
    for owner in prevention_contract_materializer.materialize()["owners"]:
        profiles = {
            spec["profile"]
            for spec in owner["reconciliation_contract"]["observables"]
        }
        assert profiles == {
            spec["profile"] for spec in owner["terminal_contract"]["observables"]
        }
        for profile in profiles:
            transport = prevention_source_probes.build_production_transport(
                owner, _preparation(owner, profile), _registry(edge)
            )
            spec = prevention_source_probes.PROVIDER_SPECS[
                (owner["owner_sequence_id"], profile)
            ]
            request = {
                "effect_id": "e" * 64,
                "owner_sequence_id": owner["owner_sequence_id"],
                "preparation_artifact_sha256": "f" * 64,
                "observation_targets": {
                    "identity_expected_sha256": "1" * 64,
                    "prestate_expected_sha256": "2" * 64,
                    "probe_expected_sha256s": {"probe": "3" * 64},
                },
                "prepared_prestate_identities": {"source": "b" * 64},
                "prepared_receipt_identities": {},
                "profile": profile,
                "probe_ids": ["probe"],
                "provider_symbol": spec.reconciliation_provider_symbol,
                "source_evidence_sha256": "c" * 64,
            }
            capture = transport.query(request)
            raw = capture["raw_source_facts"]
            assert raw["ownership"]["effect_id"] == request["effect_id"]
            assert raw["probes"]["probe"]["absent"] is True


def test_provider_contract_mismatch_and_missing_typed_edge_fail_closed():
    owner = prevention_contract_materializer.materialize()["owners"][0]
    profile = owner["reconciliation_contract"]["observables"][0]["profile"]
    drifted = {
        **owner,
        "reconciliation_contract": {
            **owner["reconciliation_contract"],
            "observables": [
                {
                    **item,
                    "provider_symbol": "caller_selected_provider",
                }
                if item["profile"] == profile else item
                for item in owner["reconciliation_contract"]["observables"]
            ],
        },
    }
    with pytest.raises(
        prevention_source_probes.SourceProbeError,
        match="provider-contract-mismatch",
    ):
        prevention_source_probes.build_production_transport(
            drifted, _preparation(drifted, profile), _registry(_CapturedEdge())
        )
    with pytest.raises(
        prevention_source_probes.SourceProbeError,
        match="production-source-edge-unavailable",
    ):
        prevention_source_probes.build_production_transport(
            owner,
            _preparation(owner, profile),
            prevention_source_probes.SourceEdgeRegistry(),
        )


def test_missing_factory_row_fails_before_the_source_edge_is_read(monkeypatch):
    owner = prevention_contract_materializer.materialize()["owners"][0]
    profile = owner["reconciliation_contract"]["observables"][0]["profile"]
    edge = _CapturedEdge()
    key = (owner["owner_sequence_id"], profile)
    monkeypatch.setattr(
        prevention_source_probes,
        "PROVIDER_FACTORIES",
        {name: factory for name, factory in prevention_source_probes.PROVIDER_FACTORIES.items()
         if name != key},
    )
    with pytest.raises(
        prevention_source_probes.SourceProbeError,
        match="production-source-provider-unavailable",
    ):
        prevention_source_probes.build_production_transport(
            owner, _preparation(owner, profile), _registry(edge)
        )
    assert edge.requests == []


def test_production_controller_has_no_transport_backend_or_factory_injection():
    parameters = inspect.signature(prevention_controller.PreventionController).parameters
    assert "owner_source_edges" in parameters
    assert "owner_observation_transport" not in parameters
    assert "observation_backend" not in parameters
    assert "provider_factory" not in parameters


def test_checkpoint_acceptance_uses_materialized_child_contracts_in_memory(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        prevention_owner_acceptance_producer.prevention_registry,
        "load_typed_registry",
        lambda: (_ for _ in ()).throw(AssertionError("stale disk registry used")),
    )

    result = prevention_owner_acceptance_producer.execute_case(
        "convergence-checkpoint-run", "default", scenario="positive",
    )

    assert result["result"]["status"] == "TERMINAL"


def test_credential_acceptance_all_is_hermetic_and_terminal():
    result = prevention_owner_acceptance_producer.execute_case(
        "claude-auth-token-refresh", "all", scenario="positive",
    )
    assert result["result"]["status"] == "TERMINAL"
    assert result["executed_commands"][0][1] == (
        "/Users/kamenkamenov/mcp-agents-workflow/scripts/claude_auth_refresh.sh"
    )
    assert result["credential_os_operations"] == [
        "SecKeychainFindGenericPassword",
        "SecKeychainAddGenericPassword",
    ]


def test_drive_receipt_requires_its_declared_complete_stage():
    receipt = {
        "owner_sequence_id": "discovery-candidate-reconciliation",
        "profile_id": "drive",
        "status": "APPLIED",
        "source_identity": {"sequence_id": "discovery-candidate-reconciliation"},
        "result_identity": {
            "ok": True,
            "stage": "complete",
            "result_sha256": "a" * 64,
        },
    }

    assert prevention_owner_acceptance_producer.AcceptanceSourceEdge._receipt_semantic_success(
        "discovery-candidate-reconciliation", "drive", receipt,
    )
    receipt["result_identity"]["stage"] = "drive"
    assert not prevention_owner_acceptance_producer.AcceptanceSourceEdge._receipt_semantic_success(
        "discovery-candidate-reconciliation", "drive", receipt,
    )


def test_discovery_reconciliation_drive_is_hermetic_and_terminal():
    result = prevention_owner_acceptance_producer.execute_case(
        "discovery-candidate-reconciliation", "drive", scenario="positive",
    )

    assert result["result"]["status"] == "TERMINAL"
    assert result["executed_commands"][0][1] == (
        "/Users/kamenkamenov/memory-knowledge/scripts/"
        "discovery_candidate_reconciliation.py"
    )


def test_discovery_promotion_correction_fixture_is_hermetic_and_terminal():
    result = prevention_owner_acceptance_producer.execute_case(
        "discovery-promotion-lifecycle", "correct", scenario="positive",
    )

    assert result["result"]["status"] == "TERMINAL"


def test_promotion_drive_receipt_requires_its_declared_complete_stage():
    receipt = {
        "owner_sequence_id": "discovery-promotion-lifecycle",
        "profile_id": "drive",
        "status": "APPLIED",
        "source_identity": {"sequence_id": "discovery-promotion-lifecycle"},
        "result_identity": {
            "ok": True,
            "stage": "complete",
            "result_sha256": "a" * 64,
        },
    }

    assert prevention_owner_acceptance_producer.AcceptanceSourceEdge._receipt_semantic_success(
        "discovery-promotion-lifecycle", "drive", receipt,
    )
    receipt["result_identity"] = {
        "ok": True,
        "next_stage": "successor-verification",
        "result_sha256": "a" * 64,
    }
    assert not prevention_owner_acceptance_producer.AcceptanceSourceEdge._receipt_semantic_success(
        "discovery-promotion-lifecycle", "drive", receipt,
    )


@pytest.mark.parametrize(
    ("profile", "driver"),
    [
        ("create-program", "greenfield_drive_dag.py"),
        ("resume-program", "greenfield_drive_dag.py"),
        ("start-from-spec", "greenfield_evaluation_drive.py"),
        ("validate-fresh", "greenfield_drive_dag.py"),
    ],
)
def test_greenfield_acceptance_executes_historical_shell_and_checked_in_python(
    profile: str, driver: str,
):
    result = prevention_owner_acceptance_producer.execute_case(
        "greenfield-full-drive", profile, scenario="positive",
    )
    assert result["result"]["status"] == "TERMINAL"
    assert result["executed_commands"][0][1] == (
        "/Users/kamenkamenov/mcp-agents-workflow/scripts/greenfield_full_drive.sh"
    )
    assert result["delegated_python_paths"] == [
        "/Users/kamenkamenov/mcp-agents-workflow/scripts/local_workflow_orch_image_harness.py",
        "/Users/kamenkamenov/mcp-agents-workflow/scripts/local_workflow_orch_image_harness.py",
        "/Users/kamenkamenov/mcp-agents-workflow/scripts/local_workflow_orch_image_harness.py",
        "/Users/kamenkamenov/mcp-agents-workflow/scripts/local_workflow_orch_image_harness.py",
        "/Users/kamenkamenov/mcp-agents-workflow/scripts/ensure_local_operator_env.py",
        f"/Users/kamenkamenov/mcp-agents-workflow/scripts/{driver}",
    ]
    assert result["delegated_pytest_commands"] == [[
        "tests/test_local_workflow_orch_image_harness.py",
        "tests/test_local_image_harness_build_gate.py",
        "-q",
    ]]


def test_local_image_build_acceptance_runs_mandatory_real_test_preflight():
    result = prevention_owner_acceptance_producer.execute_case(
        "local-workflow-orch-image", "build", scenario="positive",
    )

    assert result["result"]["status"] == "TERMINAL"
    assert result["delegated_pytest_commands"] == [[
        "tests/test_local_workflow_orch_image_harness.py",
        "tests/test_local_image_harness_build_gate.py",
        "-q",
    ]]


@pytest.mark.parametrize(
    ("profile", "operator_action", "control_action"),
    [
        ("restart-workflow", "playbook-start", "start_over"),
        ("resume", "control", "resume"),
        ("start-over", "playbook-start", "start_over"),
    ],
)
def test_parent_gated_reentry_executes_historical_launcher_and_operator_edge(
    profile: str, operator_action: str, control_action: str,
):
    result = prevention_owner_acceptance_producer.execute_case(
        "mawf-playbook-blocker-reentry", profile, scenario="positive",
    )
    assert result["result"]["status"] == "TERMINAL"
    assert result["executed_commands"][0][1] == (
        "/Users/kamenkamenov/mcp-agents-workflow/scripts/mawf_playbook_test_sequence.py"
    )
    assert len(result["operator_commands"]) == 1
    operator = result["operator_commands"][0]
    assert operator[0] == (
        "/Users/kamenkamenov/mcp-agents-workflow/dist/remote-mcp-operator/run.sh"
    )
    assert operator[operator.index("--agent-action") + 1] == operator_action
    if operator_action == "control":
        assert operator[operator.index("--control-action") + 1] == control_action
    else:
        assert operator[operator.index("--selected-task-action") + 1] == control_action


def test_materializer_derives_verified_admission_only_from_complete_trace_corpus(
    tmp_path: Path, monkeypatch,
):
    owner = deepcopy(prevention_contract_materializer.materialize()["owners"][0])
    profile = owner["reconciliation_contract"]["observables"][0]["profile"]
    owner["reconciliation_contract"]["observables"] = [
        owner["reconciliation_contract"]["observables"][0]
    ]
    owner["terminal_contract"]["observables"] = [
        next(
            row for row in owner["terminal_contract"]["observables"]
            if row["profile"] == profile
        )
    ]
    owner["acceptance_proofs"] = [
        row for row in owner["acceptance_proofs"]
        if row["profile_id"] == profile
    ]
    trace_dir = tmp_path / "traces"
    trace_dir.mkdir()
    monkeypatch.setattr(prevention_owner_acceptance, "TRACE_DIR", trace_dir)
    provider = Path(prevention_source_probes.__file__)
    test = Path(__file__).resolve()
    bindings = lambda path: {
        "path": str(path), "sha256": prevention_contract.sha256_bytes(path.read_bytes())
    }
    references = []
    for proof in prevention_owner_acceptance.PROOF_KINDS:
        effect_id = "e" * 64
        preparation_payload = {
            "effect_id": effect_id,
            "owner_sequence_id": owner["owner_sequence_id"],
        }
        preparation_sha256 = prevention_contract.sha256_bytes(
            prevention_contract.canonical_bytes(preparation_payload)
        )
        prepared = {
            "event_type": "effect_prepared", "effect_id": effect_id,
            "owner_sequence_id": owner["owner_sequence_id"],
        }
        started = {
            "event_type": "effect_execution_started", "effect_id": effect_id,
        }
        committed = {
            "event_type": "effect_committed", "effect_id": effect_id,
        }
        executed_terminal = {
            "event_type": "owner_terminal", "effect_id": effect_id,
            "result_kind": "EXECUTED_RESULT",
        }
        recovered_terminal = {
            "event_type": "owner_terminal", "effect_id": effect_id,
            "result_kind": "RECOVERED_RESULT",
        }
        if proof == "controller_runtime_positive":
            events = [prepared, started, committed, executed_terminal]
        elif proof == "controller_runtime_semantic_negative":
            events = [prepared, started, committed]
        elif proof == "crash_reconciliation":
            events = [
                prepared,
                {"event_type": "effect_reconciled", "effect_id": effect_id,
                 "reconciliation": "NOT_APPLIED"},
                started,
                {"event_type": "effect_reconciled", "effect_id": effect_id,
                 "reconciliation": "ALREADY_APPLIED"},
                recovered_terminal,
            ]
        elif proof == "terminal_semantics":
            events = [prepared, executed_terminal]
        else:
            events = []
        artifacts = {
            name: {"applicable": False}
            for name in prevention_owner_acceptance.ARTIFACT_KINDS
        }
        if proof in {
            "controller_runtime_positive", "controller_runtime_semantic_negative",
            "crash_reconciliation", "effect_identity_source_binding",
        }:
            payload = preparation_payload
            artifacts["preparation"] = {
                "applicable": True,
                "sha256": prevention_contract.sha256_bytes(
                    prevention_contract.canonical_bytes(payload)
                ),
                "payload": payload,
            }
        if proof in {
            "controller_runtime_positive", "crash_reconciliation",
            "terminal_semantics",
        }:
            payload = {"semantic_verdict": "PASS", "effect_id": effect_id}
            artifacts["terminal"] = {
                "applicable": True,
                "sha256": prevention_contract.sha256_bytes(
                    prevention_contract.canonical_bytes(payload)
                ),
                "payload": payload,
            }
        if proof in {
            "controller_runtime_semantic_negative", "effect_identity_source_binding",
            "production_source_probe_backend",
        }:
            payload = {
                "transport_kind": "PRODUCTION_SOURCE_PROBE",
                "preparation_artifact_sha256": preparation_sha256,
                "raw_source_facts": {
                    "identity": {
                        "observed_sha256": prevention_contract.sha256_bytes(
                            prevention_contract.canonical_bytes({
                                "effect_id": effect_id,
                                "owner_sequence_id": owner["owner_sequence_id"],
                                "profile": profile,
                            })
                        )
                    },
                    "ownership": {
                        "effect_id": effect_id,
                        "owner_sequence_id": owner["owner_sequence_id"],
                        "preparation_artifact_sha256": preparation_sha256,
                    },
                },
            }
            artifacts["source_capture"] = {
                "applicable": True,
                "sha256": prevention_contract.sha256_bytes(
                    prevention_contract.canonical_bytes(payload)
                ),
                "payload": payload,
            }
        trace = {
            "schema_version": 1,
            "owner_sequence_id": owner["owner_sequence_id"],
            "profile_id": profile,
            "proof_kind": proof,
                "case_id": f"{owner['owner_sequence_id']}/{profile}/v1",
            "applicability": "REQUIRED",
            "acceptance_contract_sha256": owner["acceptance_contract_sha256"],
            "parameter_policy_sha256": owner["parameter_contract"]["policy_sha256"],
            "reconciliation_policy_sha256": owner["reconciliation_contract"]["policy_sha256"],
            "terminal_policy_sha256": owner["terminal_contract"]["policy_sha256"],
            "source_bindings": [
                {"path": item["path"], "sha256": item["sha256"]}
                for item in owner["implementation_sources"]
            ],
            "test_bindings": [
                bindings(prevention_owner_acceptance.PRODUCER_PATH),
                bindings(prevention_owner_acceptance.FIXTURES_PATH),
            ],
            "provider_implementation_sha256": bindings(provider)["sha256"],
            "production_backend_id": "PRODUCTION_SOURCE_PROBE_V1",
            "source_edge_kind": "CREDENTIAL",
            "runner_command_sha256": "a" * 64,
            "journal_events": events,
            "journal_events_sha256": prevention_contract.sha256_bytes(
                prevention_contract.canonical_bytes(events)
            ),
            "artifacts": artifacts,
            "expected_outcome": prevention_owner_acceptance.PROOF_OUTCOMES[proof],
            "observed_outcome": prevention_owner_acceptance.PROOF_OUTCOMES[proof],
        }
        trace_hash = prevention_owner_acceptance.write_trace(trace, trace_dir)
        references.append({
            "profile_id": profile,
            "proof_kind": proof,
            "applicability": "REQUIRED",
            "trace_sha256": trace_hash,
        })
    report = {
        "schema_version": 2,
        "provider_implementation": bindings(provider),
        "owners": [{
            "owner_sequence_id": owner["owner_sequence_id"],
            "required_profile_ids": [profile],
            "required_profile_set_sha256": prevention_owner_acceptance.required_profile_set_sha256(owner),
            "proof_references": references,
        }],
    }
    admission = prevention_owner_acceptance.verify_owner_report(report, owner)
    assert admission["contract_verification"] == "VERIFIED"
    assert admission["dispatch_admission"] == "STANDALONE"

    first = trace_dir / f"{references[0]['trace_sha256']}.json"
    first.write_bytes(first.read_bytes() + b" ")
    with pytest.raises(
        prevention_owner_acceptance.AcceptanceError,
        match="content-address-invalid",
    ):
        prevention_owner_acceptance.verify_owner_report(report, owner)


def test_trace_writer_rejects_self_declared_positive_without_runtime_events(
    tmp_path: Path,
):
    source = Path(__file__).resolve().parents[2] / "scripts/prevention_adapters.py"
    binding = lambda path: {
        "path": str(path),
        "sha256": prevention_contract.sha256_bytes(path.read_bytes()),
    }
    trace = {
        "schema_version": 1,
        "owner_sequence_id": "discovery-bootstrap",
        "profile_id": "start",
        "proof_kind": "controller_runtime_positive",
        "case_id": "self-declared-only",
        "applicability": "REQUIRED",
        "acceptance_contract_sha256": "a" * 64,
        "parameter_policy_sha256": "b" * 64,
        "reconciliation_policy_sha256": "c" * 64,
        "terminal_policy_sha256": "d" * 64,
        "source_bindings": [binding(source)],
        "test_bindings": [
            binding(prevention_owner_acceptance.PRODUCER_PATH),
            binding(prevention_owner_acceptance.FIXTURES_PATH),
        ],
        "provider_implementation_sha256": binding(
            Path(prevention_source_probes.__file__)
        )["sha256"],
        "production_backend_id": "PRODUCTION_SOURCE_PROBE_V1",
        "source_edge_kind": "LOCAL_STATE",
        "runner_command_sha256": "e" * 64,
        "journal_events": [],
        "journal_events_sha256": prevention_contract.sha256_bytes(
            prevention_contract.canonical_bytes([])
        ),
        "artifacts": {
            name: {"applicable": False}
            for name in prevention_owner_acceptance.ARTIFACT_KINDS
        },
        "expected_outcome": "TERMINAL",
        "observed_outcome": "TERMINAL",
    }
    with pytest.raises(
        prevention_owner_acceptance.AcceptanceError,
        match="positive-path-invalid",
    ):
        prevention_owner_acceptance.write_trace(trace, tmp_path)
    assert list(tmp_path.glob("*.json")) == []


def test_materialized_applicability_is_complete_and_only_contract_non_mutations_skip_crash_and_identity():
    owners = prevention_contract_materializer.materialize()["owners"]
    expected_non_mutating = set(
        prevention_contract_materializer.NON_MUTATING_PROFILE_CLAUSES
    )
    observed_non_mutating = set()
    for owner in owners:
        profiles = {
            row["profile"]
            for row in owner["reconciliation_contract"]["observables"]
        }
        rows = owner["acceptance_proofs"]
        assert {row["profile_id"] for row in rows} == profiles
        for row in rows:
            proofs = {proof["proof_kind"]: proof for proof in row["proofs"]}
            assert set(proofs) == set(prevention_owner_acceptance.PROOF_KINDS)
            key = (owner["owner_sequence_id"], row["profile_id"])
            not_applicable = {
                name for name, proof in proofs.items()
                if proof["applicability"] == "NOT_APPLICABLE"
            }
            if key in expected_non_mutating:
                observed_non_mutating.add(key)
                assert not_applicable == {
                    "crash_reconciliation", "effect_identity_source_binding",
                }
                assert all(
                    len(proofs[name]["contract_clause_sha256"]) == 64
                    and proofs[name]["contract_clause_pointer"].startswith("/")
                    for name in not_applicable
                )
            else:
                assert not not_applicable
    assert observed_non_mutating == expected_non_mutating


def test_checked_acceptance_case_registry_is_exactly_the_44_materialized_profiles():
    owners = prevention_contract_materializer.materialize()["owners"]

    rows, registry_sha256 = prevention_owner_acceptance_cases.load_case_registry(
        owners
    )

    assert len(rows) == 44
    assert len(registry_sha256) == 64
    assert sum(row["effect_class"] == "MUTATION" for row in rows) == 33
    assert sum(row["effect_class"] == "NON_MUTATING" for row in rows) == 11
    assert sum(
        proof["applicability"] == "REQUIRED"
        for row in rows for proof in row["proof_applicability"]
    ) == 242
