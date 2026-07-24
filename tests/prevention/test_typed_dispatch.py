from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from scripts import prevention_contract as contract
from scripts import prevention_adapters, prevention_budget, prevention_controller, prevention_journal
from scripts import prevention_owner_runtime, prevention_source_probes


TASK_ID = "task-123"
RUN_ID = "4f642f31-f326-4b2c-92e4-753826ecad9f"


class _BindingProvider:
    def resolve(self, request):
        execution_value = (
            "opaque-test-secret"
            if request.parameter_type == "SECRET_HANDLE"
            else f"resolved-{request.key_or_resource_id}"
        )
        binding_kind = (
            contract.BindingKind.SECRET
            if request.parameter_type == "SECRET_HANDLE"
            else contract.BindingKind.RESOURCE
        )
        return prevention_adapters.BindingResolution(
            receipt=contract.BindingReceipt(
                receipt_id=contract.sha256_bytes(contract.canonical_bytes({
                    "scope": request.expected_scope_sha256,
                    "key": request.key_or_resource_id,
                })),
                binding_kind=binding_kind,
                provider_id=request.provider_id,
                key_or_resource_id=request.key_or_resource_id,
                version_id="v1", scope_sha256=request.expected_scope_sha256,
                value_fingerprint_sha256=contract.sha256_bytes(
                    contract.canonical_bytes(execution_value)
                ),
                consumable=False,
            ),
            execution_value=execution_value,
        )


class _ObservationTransport:
    def query(self, request):
        ownership = {
            "effect_id": request["effect_id"],
            "owner_sequence_id": request["owner_sequence_id"],
            "preparation_artifact_sha256": request["preparation_artifact_sha256"],
        }
        now = prevention_owner_runtime.work_memory.utc_now()
        if request["provider_symbol"].endswith("_reconciliation"):
            return {
                "identity": "MATCH", "observed_at_utc": now,
                "ownership": ownership, "prestate": "MATCH",
                "probes": {probe: "ABSENT" for probe in request["probe_ids"]},
                "receipt": "ABSENT",
                "source_evidence_sha256": request["source_evidence_sha256"],
                "work_state": "DETACHED",
            }
        return {
            "identity": "MATCH", "observed_at_utc": now,
            "ownership": ownership, "prestate": "CHANGED",
            "probes": {probe: "SATISFIED" for probe in request["probe_ids"]},
            "receipt": "PRESENT",
            "source_evidence_sha256": request["source_evidence_sha256"],
            "work_state": "TERMINAL",
        }


class _SourceEdge:
    def capture(self, request):
        terminal = request["provider_symbol"].endswith("_terminal")
        identity_sha256 = contract.sha256_bytes(contract.canonical_bytes({
            "effect_id": request["effect_id"],
            "owner_sequence_id": request["owner_sequence_id"],
            "profile": request["profile"],
        }))
        return prevention_source_probes.SourceProbeCapture(
            identity=prevention_source_probes.SourceHashFact(
                observed_sha256=identity_sha256,
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
                observed_sha256=(
                    "2" * 64 if terminal else contract.sha256_bytes(
                        contract.canonical_bytes({
                            "effect_id": request["effect_id"],
                            "owner_sequence_id": request["owner_sequence_id"],
                            "profile": request["profile"],
                            "source_status": "ABSENT",
                        })
                    )
                ),
                known=True,
            ),
            receipt=prevention_source_probes.SourceReceiptFact(
                present=terminal, known=True,
                effect_id=request["effect_id"] if terminal else None,
                preparation_artifact_sha256=(
                    request["preparation_artifact_sha256"] if terminal else None
                ),
            ),
            work_state=prevention_source_probes.SourceWorkStateFact(
                terminal=terminal, detached=not terminal,
            ),
            probes={
                probe: prevention_source_probes.SourceProbeFact(
                    observed_sha256=(
                        contract.sha256_bytes(contract.canonical_bytes({
                            "effect_id": request["effect_id"],
                            "owner_sequence_id": request["owner_sequence_id"],
                            "profile": request["profile"],
                            "probe_id": probe,
                            "source_status": "SATISFIED",
                        }))
                        if terminal else None
                    ),
                    known=True,
                    absent=not terminal,
                )
                for probe in request["probe_ids"]
            },
        )


def _source_edges():
    edge = _SourceEdge()
    return prevention_source_probes.SourceEdgeRegistry(
        local_state=edge, git=edge, docker=edge, credential=edge, operator=edge,
    )


def executable_intent() -> contract.ActionIntent:
    return contract.ActionIntent(
        **{**intent(sequence_id="claude-auth-token-refresh").__dict__, "parameters": (
            contract.TypedParameter(
                "command", contract.ParameterValue(contract.ParameterTag.ENUM, "status")
            ),
            contract.TypedParameter(
                "container_key", contract.ParameterValue(contract.ParameterTag.RESOURCE_KEY, "container")
            ),
            contract.TypedParameter(
                "vault_key", contract.ParameterValue(contract.ParameterTag.RESOURCE_KEY, "vault")
            ),
        )}
    )


def blocker_reentry_intent(
    *, intent_id: str | None = None, delegation_id: str | None = None,
    mode: str = "resume",
) -> contract.ActionIntent:
    return contract.ActionIntent(
        **{
            **intent(
                intent_id=intent_id,
                sequence_id="mawf-playbook-blocker-reentry",
            ).__dict__,
            "parameters": (
                contract.TypedParameter(
                    "delegation_id",
                    contract.ParameterValue(
                        contract.ParameterTag.UUID,
                        delegation_id or str(uuid.uuid4()),
                    ),
                ),
                contract.TypedParameter(
                    "mode", contract.ParameterValue(contract.ParameterTag.ENUM, mode)
                ),
                contract.TypedParameter(
                    "task_guid",
                    contract.ParameterValue(contract.ParameterTag.STRING, "task-1"),
                ),
                contract.TypedParameter(
                    "workflow_name",
                    contract.ParameterValue(
                        contract.ParameterTag.ENUM, "research-workflow"
                    ),
                ),
                contract.TypedParameter(
                    "run_id",
                    contract.ParameterValue(contract.ParameterTag.UUID, str(uuid.uuid4())),
                ),
            ),
        }
    )


def append_started_parent_and_delegation(
    governed: prevention_controller.PreventionController,
    requested: contract.ActionIntent,
    parent_owner_sequence_id: str,
) -> dict:
    journal = governed.journal
    parent_effect_id = contract.sha256_bytes(
        contract.canonical_bytes({"parent": parent_owner_sequence_id})
    )
    owner_contract_sha256 = "d" * 64
    reconciler_sha256 = "e" * 64
    preparation_artifact_sha256 = "f" * 64
    transition = journal.append("transition_prepared", {
        "journal_id": "parent-journal",
        "transition": "EFFECT_PREPARED",
        "state_hash": "1" * 64,
    })
    prepared = journal.append("effect_prepared", {
        "journal_id": "parent-journal",
        "effect_id": parent_effect_id,
        "idempotency_key": "2" * 64,
        "effect_kind": "OWNER_INVOCATION",
        "owner_sequence_id": parent_owner_sequence_id,
        "implementation_id": "3" * 64,
        "effect_task_id": journal.ownership.task_id,
        "effect_run_id": journal.ownership.run_id,
        "effect_branch_ref": journal.ownership.branch_ref,
        "effect_worktree_id": journal.ownership.worktree_id,
        "transition_prepared_event_id": transition["event_id"],
        "owner_contract_sha256": owner_contract_sha256,
        "reconciler_sha256": reconciler_sha256,
        "preparation_artifact_sha256": preparation_artifact_sha256,
    })
    reconciled = journal.append("effect_reconciled", {
        "journal_id": "parent-journal",
        "effect_id": parent_effect_id,
        "prepared_event_id": prepared["event_id"],
        "attempt_generation": 0,
        "owner_contract_sha256": owner_contract_sha256,
        "reconciler_sha256": reconciler_sha256,
        "preparation_artifact_sha256": preparation_artifact_sha256,
        "reconciliation": "NOT_APPLIED",
        "reconciliation_artifact_sha256": "4" * 64,
        "observable_ownership_sha256": "5" * 64,
        "evidence_sha256": "6" * 64,
    })
    authorized = journal.append("effect_execution_authorized", {
        "journal_id": "parent-journal",
        "effect_id": parent_effect_id,
        "attempt_generation": 1,
        "prior_generation": 0,
        "not_applied_reconciliation_event_id": reconciled["event_id"],
        "owner_contract_sha256": owner_contract_sha256,
        "authorization_sha256": "7" * 64,
    })
    journal.append("effect_execution_started", {
        "journal_id": "parent-journal",
        "effect_id": parent_effect_id,
        "attempt_generation": 1,
        "execution_authorized_event_id": authorized["event_id"],
        "owner_contract_sha256": owner_contract_sha256,
    })
    delegation_id = requested.parameter_map()["delegation_id"].value
    result = journal.append("child_delegation_recorded", {
        "delegation_id": delegation_id,
        "parent_effect_id": parent_effect_id,
        "parent_owner_sequence_id": parent_owner_sequence_id,
        "child_owner_sequence_id": requested.requested_sequence_id,
        "child_intent_id": requested.intent_id,
        "blocker_id": "blk-test-parent-delegation",
        "verification_event_id": str(uuid.uuid4()),
        "mode": requested.parameter_map()["mode"].value,
    })
    return next(
        event for event in journal.replay()[0]
        if event["event_id"] == result["event_id"]
    )


def controller(tmp_path: Path) -> prevention_controller.PreventionController:
    ownership = prevention_journal.JournalOwnership(
        task_id=TASK_ID,
        run_id=RUN_ID,
        branch_ref=f"task/{TASK_ID}",
        worktree_id="a" * 64,
    )
    return prevention_controller.PreventionController.for_test(
        prevention_journal.PreventionJournal(tmp_path / "run", ownership),
        owner_source_edges=_source_edges(),
    )


def test_production_controller_rejects_caller_supplied_source_edges(tmp_path: Path):
    governed = controller(tmp_path)
    with pytest.raises(
        prevention_controller.ControllerError,
        match="caller-source-edge-registry-prohibited",
    ):
        prevention_controller.PreventionController(
            governed.journal, owner_source_edges=_source_edges()
        )


def enable_contract_test_admission(
    governed: prevention_controller.PreventionController, sequence_id: str,
) -> None:
    """Open only the in-memory unit fixture; generated production admission stays closed."""
    governed.registry_by_id[sequence_id]["executable_contract"][
        "execution_admission"
    ] = {
        "contract_verification": "VERIFIED",
        "dispatch_admission": (
            "PARENT_GATED"
            if sequence_id == "mawf-playbook-blocker-reentry"
            else "STANDALONE"
        ),
        "reason_code": "CONTRACT_TEST_ONLY",
    }


def intent(
    *, intent_id: str | None = None, task_id: str = TASK_ID,
    sequence_id: str = "discovery-bootstrap",
    action_class: contract.ActionClass = contract.ActionClass.BASH,
) -> contract.ActionIntent:
    return contract.ActionIntent(
        intent_id=intent_id or str(uuid.uuid4()),
        task_id=task_id,
        run_id=RUN_ID,
        requested_sequence_id=sequence_id,
        requested_implementation_id="b" * 64,
        compatibility_key="c" * 64,
        action_class=action_class,
        parameters=(),
    )


def test_controller_rejects_raw_mapping_and_foreign_ownership(tmp_path: Path):
    governed = controller(tmp_path)

    with pytest.raises(prevention_controller.ControllerError, match="typed-action-intent-required"):
        governed.register_intent({"intent_id": "raw"})  # type: ignore[arg-type]
    with pytest.raises(prevention_controller.ControllerError, match="ownership-mismatch"):
        governed.register_intent(intent(task_id="foreign-task"))


def test_unresolved_dynamic_owner_budget_is_inadmissible_before_selection(
    tmp_path: Path,
):
    governed = controller(tmp_path)
    enable_contract_test_admission(governed, "convergence-state-review-cycle")
    result = governed.execute(
        intent(sequence_id="convergence-state-review-cycle")
    )

    assert result["status"] == "EXECUTION_INADMISSIBLE"
    assert result["reason"].startswith("owner-unit-budget-derivation-failed:")
    events, _ = governed.journal.replay()
    assert not any(event["event_type"] == "dispatch_selected" for event in events)


def test_dispatch_requires_one_durably_recorded_intent(tmp_path: Path):
    governed = controller(tmp_path)

    with pytest.raises(prevention_controller.ControllerError, match="recorded-exactly-once"):
        governed.dispatch(intent())


def test_registered_dispatch_is_recorded_and_registration_is_idempotent(tmp_path: Path):
    governed = controller(tmp_path)
    requested = intent()

    first = governed.register_intent(requested)
    replay = governed.register_intent(requested)
    decision = governed.dispatch(requested)

    assert replay["replayed"] is True
    assert replay["event_id"] == first["event_id"]
    assert decision.kind == contract.DecisionKind.SELECT_REGISTERED
    events, _ = governed.journal.replay()
    assert [event["event_type"] for event in events] == [
        "action_intent_recorded",
        "action_eligibility_recorded",
        "dispatch_selected",
    ]
    assert events[1]["eligibility"] is True
    assert events[1]["ineligible_reason_code"] is None
    assert events[2]["selected_owner_contract_sha256"] == events[1]["owner_contract_sha256"]
    assert events[-1]["decision_id"] == decision.decision_id


def test_mandatory_successor_records_prevented_failure(tmp_path: Path):
    governed = controller(tmp_path)
    requested = intent()
    governed.register_intent(requested)
    prohibition = governed.journal.append("predecessor_prohibited", {
        "compatibility_key": requested.compatibility_key,
        "failure_fingerprint": "d" * 64,
        "predecessor_sequence_id": requested.requested_sequence_id,
        "predecessor_implementation_id": requested.requested_implementation_id,
        "successor_sequence_id": "discovery-promotion-lifecycle",
        "successor_implementation_id": "e" * 64,
        "verification_event_id": str(uuid.uuid4()),
    })

    decision = governed.dispatch(requested)

    assert decision.kind == contract.DecisionKind.SELECT_SUCCESSOR
    events, _ = governed.journal.replay()
    prevented = events[-1]
    assert prevented["event_type"] == "prevented_failure_recorded"
    assert prevented["prohibition_event_id"] == prohibition["event_id"]
    assert prevented["successor_implementation_id"] == "e" * 64


@pytest.mark.parametrize(
    ("sequence_id", "availability", "reason"),
    [
        ("taggable-source-reload", "UNAVAILABLE", "AVAILABILITY_UNAVAILABLE"),
        (
            "remote-mcp-user-onboarding",
            "CUSTODIAN_EVIDENCE_REQUIRED",
            "AVAILABILITY_CUSTODIAN_EVIDENCE_REQUIRED",
        ),
    ],
)
def test_non_available_owner_is_recorded_ineligible_and_cannot_dispatch(
    tmp_path: Path, sequence_id: str, availability: str, reason: str,
):
    governed = controller(tmp_path)
    requested = intent(sequence_id=sequence_id)

    governed.register_intent(requested)
    decision = governed.dispatch(requested)

    assert decision.kind == contract.DecisionKind.REJECT
    events, _ = governed.journal.replay()
    eligibility = next(event for event in events if event["event_type"] == "action_eligibility_recorded")
    assert eligibility["availability_policy"] == availability
    assert eligibility["eligibility"] is False
    assert eligibility["ineligible_reason_code"] == reason
    assert not any(event["event_type"] == "dispatch_selected" for event in events)


def test_unregistered_action_class_is_recorded_ineligible_and_cannot_dispatch(tmp_path: Path):
    governed = controller(tmp_path)
    requested = intent(action_class=contract.ActionClass.MCP)

    governed.register_intent(requested)
    decision = governed.dispatch(requested)

    assert decision.kind == contract.DecisionKind.REJECT
    events, _ = governed.journal.replay()
    eligibility = next(event for event in events if event["event_type"] == "action_eligibility_recorded")
    assert eligibility["eligibility"] is False
    assert eligibility["ineligible_reason_code"] == "UNREGISTERED_ACTION_CLASS"
    assert not any(event["event_type"] == "dispatch_selected" for event in events)


def test_source_verified_owner_executes_once_and_replays_terminal(tmp_path: Path):
    governed = controller(tmp_path)
    enable_contract_test_admission(governed, "claude-auth-token-refresh")
    authority = prevention_budget.BudgetAuthority(
        governed.journal, {"duration_milliseconds": 28_800_000}
    )
    calls = []

    def runner(argv):
        calls.append(tuple(argv))
        return prevention_owner_runtime.ExecutionResult(0, '{"ok":true}', "")

    governed.budget_authority = authority
    governed.owner_runner = runner
    governed.owner_binding_provider = _BindingProvider()
    requested = executable_intent()

    first = governed.execute(requested)
    resumed = governed.execute(requested)

    assert first["status"] == resumed["status"] == "TERMINAL"
    assert first["effect"]["observation_transport_kind"] == "PRODUCTION_SOURCE_PROBE"
    assert len(calls) == 1
    effect_id = first["effect"]["effect_id"]
    assert ("--effect-id", effect_id) == calls[0][
        calls[0].index("--effect-id"):calls[0].index("--effect-id") + 2
    ]
    assert calls[0][-2:] == (
        "--prevention-preparation-sha256",
        first["effect"]["preparation_artifact_sha256"],
    )
    assert first["effect"]["terminal_event_id"] == resumed["effect"]["terminal_event_id"]
    events, _ = governed.journal.replay()
    assert len([event for event in events if event["event_type"] == "dispatch_selected"]) == 1
    assert len([event for event in events if event["event_type"] == "budget_admitted"]) == 1


def test_contract_acceptance_authority_opens_only_its_exact_case_without_persisting_admission(
    tmp_path: Path,
):
    base = controller(tmp_path)
    requested = executable_intent()
    owner = base.registry_by_id[requested.requested_sequence_id]
    admission_before = dict(owner["executable_contract"]["execution_admission"])
    authority = prevention_controller.ContractAcceptanceAuthority(
        task_id=requested.task_id,
        run_id=requested.run_id,
        intent_id=requested.intent_id,
        owner_sequence_id=requested.requested_sequence_id,
        owner_contract_sha256=owner["owner_contract_sha256"],
        profile_id="status",
        proof_kind="controller_runtime_positive",
        case_registry_sha256="f" * 64,
    )
    governed = prevention_controller.PreventionController.for_contract_acceptance(
        base.journal,
        authority,
        registry_rows=base.registry_rows,
        owner_source_edges=_source_edges(),
    )
    governed.budget_authority = prevention_budget.BudgetAuthority(
        governed.journal, {"duration_milliseconds": 28_800_000}
    )
    governed.owner_binding_provider = _BindingProvider()
    governed.owner_runner = lambda _argv: prevention_owner_runtime.ExecutionResult(
        0, '{"ok":true}', ""
    )

    result = governed.execute(requested)

    assert result["status"] == "TERMINAL"
    admission = governed.registry_by_id[requested.requested_sequence_id][
        "executable_contract"
    ]["execution_admission"]
    assert admission == admission_before
    assert admission["contract_verification"] == "VERIFIED"
    assert admission["dispatch_admission"] == "STANDALONE"


def test_contract_acceptance_authority_rejects_a_different_profile_before_source(
    tmp_path: Path,
):
    base = controller(tmp_path)
    requested = executable_intent()
    owner = base.registry_by_id[requested.requested_sequence_id]
    authority = prevention_controller.ContractAcceptanceAuthority(
        task_id=requested.task_id,
        run_id=requested.run_id,
        intent_id=requested.intent_id,
        owner_sequence_id=requested.requested_sequence_id,
        owner_contract_sha256=owner["owner_contract_sha256"],
        profile_id="verify",
        proof_kind="controller_runtime_positive",
        case_registry_sha256="f" * 64,
    )
    governed = prevention_controller.PreventionController.for_contract_acceptance(
        base.journal,
        authority,
        registry_rows=base.registry_rows,
        owner_source_edges=_source_edges(),
    )
    governed.owner_runner = lambda _argv: pytest.fail("source must not execute")

    result = governed.execute(requested)

    assert result["status"] == "EXECUTION_INADMISSIBLE"


def test_controller_rejects_insufficient_budget_before_owner_runner(tmp_path: Path):
    governed = controller(tmp_path)
    enable_contract_test_admission(governed, "claude-auth-token-refresh")
    governed.budget_authority = prevention_budget.BudgetAuthority(
        governed.journal, {"duration_milliseconds": 28_799_999}
    )
    governed.owner_runner = lambda _argv: pytest.fail("runner must not start")
    governed.owner_binding_provider = _BindingProvider()
    requested = executable_intent()

    result = governed.execute(requested)

    assert result["status"] == "BUDGET_REJECTED"


def test_blocker_reentry_rejects_direct_execution_before_budget(tmp_path: Path):
    governed = controller(tmp_path)
    requested = blocker_reentry_intent()

    with pytest.raises(
        prevention_controller.ControllerError, match="active-parent-delegation-required"
    ):
        governed.execute(requested)

    events, _ = governed.journal.replay()
    assert not any(event["event_type"] == "budget_admitted" for event in events)
    assert not any(event["event_type"] == "effect_prepared" for event in events)


@pytest.mark.parametrize(
    "parent_owner_sequence_id",
    ["mawf-playbook-full-test", "mawf-playbook-speed-test"],
)
def test_blocker_reentry_accepts_only_active_verified_allowed_parent_fixture(
    tmp_path: Path, parent_owner_sequence_id: str,
):
    governed = controller(tmp_path)
    governed.delegation_verifier = lambda _verification_id, _blocker_id: True
    requested = blocker_reentry_intent()
    recorded = append_started_parent_and_delegation(
        governed, requested, parent_owner_sequence_id
    )
    owner = governed.registry_by_id["mawf-playbook-blocker-reentry"]

    accepted = governed._require_parent_delegation(requested, owner)

    assert accepted is not None
    assert accepted["event_id"] == recorded["event_id"]
    assert accepted["parent_owner_sequence_id"] == parent_owner_sequence_id


def test_blocker_reentry_rejects_forged_child_binding_and_unverified_delegation(
    tmp_path: Path,
):
    governed = controller(tmp_path)
    requested = blocker_reentry_intent()
    append_started_parent_and_delegation(
        governed, requested, "mawf-playbook-full-test"
    )
    owner = governed.registry_by_id["mawf-playbook-blocker-reentry"]
    forged = blocker_reentry_intent(
        intent_id=requested.intent_id,
        delegation_id=requested.parameter_map()["delegation_id"].value,
        mode="restart-workflow",
    )

    with pytest.raises(
        prevention_controller.ControllerError,
        match="delegation-child-parameter-binding-mismatch",
    ):
        governed._require_parent_delegation(forged, owner)
    with pytest.raises(
        prevention_controller.ControllerError,
        match="delegation-blocker-verification-invalid",
    ):
        governed._require_parent_delegation(requested, owner)


def test_blocker_reentry_parent_owners_remain_nonexecutable_custodian_state(
    tmp_path: Path,
):
    governed = controller(tmp_path)

    for sequence_id in ("mawf-playbook-full-test", "mawf-playbook-speed-test"):
        parent = governed.registry_by_id[sequence_id]
        assert parent["availability_policy"] == "CUSTODIAN_EVIDENCE_REQUIRED"
        assert parent["executable_contract"] is None


def test_blocker_reentry_rejects_disallowed_or_no_longer_started_parent(tmp_path: Path):
    governed = controller(tmp_path)
    governed.delegation_verifier = lambda _verification_id, _blocker_id: True
    requested = blocker_reentry_intent()
    owner = governed.registry_by_id["mawf-playbook-blocker-reentry"]
    append_started_parent_and_delegation(governed, requested, "foreign-parent")

    with pytest.raises(
        prevention_controller.ControllerError, match="delegation-parent-not-allowed"
    ):
        governed._require_parent_delegation(requested, owner)

    second = controller(tmp_path / "second")
    second.delegation_verifier = lambda _verification_id, _blocker_id: True
    requested = blocker_reentry_intent()
    recorded = append_started_parent_and_delegation(
        second, requested, "mawf-playbook-full-test"
    )
    events, _ = second.journal.replay()
    prepared = next(
        event for event in events
        if event["event_type"] == "effect_prepared"
        and event["effect_id"] == recorded["parent_effect_id"]
    )
    second.journal.append("effect_reconciled", {
        "journal_id": prepared["journal_id"],
        "effect_id": prepared["effect_id"],
        "prepared_event_id": prepared["event_id"],
        "attempt_generation": 1,
        "owner_contract_sha256": prepared["owner_contract_sha256"],
        "reconciler_sha256": prepared["reconciler_sha256"],
        "preparation_artifact_sha256": prepared["preparation_artifact_sha256"],
        "reconciliation": "INDETERMINATE",
        "reconciliation_artifact_sha256": "8" * 64,
        "observable_ownership_sha256": "9" * 64,
        "evidence_sha256": "a" * 64,
    })

    with pytest.raises(
        prevention_controller.ControllerError,
        match="delegation-parent-not-same-journal-started",
    ):
        second._require_parent_delegation(requested, owner)


def test_delegation_record_requires_unique_identity(tmp_path: Path):
    governed = controller(tmp_path)
    requested = blocker_reentry_intent()
    recorded = append_started_parent_and_delegation(
        governed, requested, "mawf-playbook-full-test"
    )
    payload = {
        key: value for key, value in recorded.items()
        if key not in {
            "event_id", "event_type", "recorded_at_utc",
            "task_id", "run_id", "branch_ref", "worktree_id",
        }
    }

    with pytest.raises(Exception, match="duplicate-child-delegation"):
        governed.journal.append("child_delegation_recorded", payload)


def test_valid_delegation_executes_verified_child_once_and_replays_terminal(tmp_path: Path):
    governed = controller(tmp_path)
    enable_contract_test_admission(governed, "mawf-playbook-blocker-reentry")
    governed.delegation_verifier = lambda _verification_id, _blocker_id: True
    governed.budget_authority = prevention_budget.BudgetAuthority(
        governed.journal, {"duration_milliseconds": 28_800_000}
    )
    governed.owner_binding_provider = _BindingProvider()
    calls = []
    governed.owner_runner = lambda argv: calls.append(tuple(argv)) or (
        prevention_owner_runtime.ExecutionResult(
            0,
            '{"stage":"reenter","mode":"resume",'
            '"workflow":"research-workflow","taskGuid":"task-1",'
            '"targetRunId":"22222222-2222-4222-8222-222222222222",'
            '"verdict":"running","finalOk":true,"errorCode":null}',
            "",
        )
    )
    requested = blocker_reentry_intent()
    append_started_parent_and_delegation(
        governed, requested, "mawf-playbook-full-test"
    )

    first = governed.execute(requested)
    replay = governed.execute(requested)

    assert first["status"] == replay["status"] == "TERMINAL"
    assert len(calls) == 1
    events, _ = governed.journal.replay()
    assert len([
        event for event in events
        if event["event_type"] == "child_delegation_consumed"
    ]) == 1
