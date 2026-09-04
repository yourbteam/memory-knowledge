#!/usr/bin/env python3
"""Sole typed entry point for governed intent registration and selection."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

try:
    from scripts import (
        prevention_adapters, prevention_registry, prevention_source_probes,
        prevention_source_receipt, work_memory,
    )
    from scripts.prevention_budget import (
        BudgetAuthority, BudgetError, OwnerBudgetProducer,
        SourceOwnerBudgetProducer, derive_owner_unit_budget,
    )
    from scripts.prevention_contract import (
        ActionIntent,
        ActionClass,
        AvailabilityPolicy,
        DecisionKind,
        IneligibleReasonCode,
        RecurrencePolicy,
        TypedParameter,
        canonical_bytes,
        sha256_bytes,
    )
    from scripts.prevention_journal import PreventionJournal
    from scripts.prevention_owner_runtime import (
        ExecutionResult, OwnerRuntime, OwnerRuntimeError, Runner,
    )
    from scripts.prevention_selector import DispatchDecision, Selector
except ModuleNotFoundError:  # direct script execution
    import prevention_adapters
    import prevention_registry
    import prevention_source_probes
    import prevention_source_receipt
    import work_memory
    from prevention_budget import (
        BudgetAuthority, BudgetError, OwnerBudgetProducer,
        SourceOwnerBudgetProducer, derive_owner_unit_budget,
    )
    from prevention_contract import (
        ActionIntent,
        ActionClass,
        AvailabilityPolicy,
        DecisionKind,
        IneligibleReasonCode,
        RecurrencePolicy,
        TypedParameter,
        canonical_bytes,
        sha256_bytes,
    )
    from prevention_journal import PreventionJournal
    from prevention_owner_runtime import ExecutionResult, OwnerRuntime, OwnerRuntimeError, Runner
    from prevention_selector import DispatchDecision, Selector


class ControllerError(ValueError):
    """Raised when a governed caller crosses the typed controller boundary."""


@dataclass(frozen=True)
class ContractAcceptanceAuthority:
    """One-case pre-admission authority used only to produce contract evidence.

    This does not alter the generated owner contract or production admission.
    It binds one exact journal owner, intent, owner contract, profile, proof, and
    checked case-registry revision to the normal controller/runtime path.
    """

    task_id: str
    run_id: str
    intent_id: str
    owner_sequence_id: str
    owner_contract_sha256: str
    profile_id: str
    proof_kind: str
    case_registry_sha256: str


@dataclass(frozen=True)
class HostSourceEdgeAuthority:
    """Bind source edges to one authenticated host capability journal event."""

    session_id: str
    receipt_sha256: str
    source_edges: prevention_source_probes.SourceEdgeRegistry


_CONTRACT_ACCEPTANCE_PROOF_KINDS = frozenset({
    "controller_runtime_positive",
    "controller_runtime_semantic_negative",
    "crash_reconciliation",
    "terminal_semantics",
    "effect_identity_source_binding",
    "production_source_probe_backend",
})


class PreventionController:
    def __init__(
        self,
        journal: PreventionJournal,
        *,
        registry_rows: Sequence[Mapping[str, Any]] | None = None,
        budget_authority: BudgetAuthority | None = None,
        owner_runner: Runner | None = None,
        owner_source_edges: prevention_source_probes.SourceEdgeRegistry | None = None,
        delegation_verifier: Callable[[str, str], bool] | None = None,
        owner_binding_provider: prevention_adapters.BindingProvider | None = None,
        _contract_acceptance: ContractAcceptanceAuthority | None = None,
        _host_source_authority: HostSourceEdgeAuthority | None = None,
        _test_source_edges: bool = False,
    ):
        self.journal = journal
        if registry_rows is None:
            loaded_rows, registry_sha256 = prevention_registry.load_typed_registry()
            self.registry_rows = list(loaded_rows)
            self.registry_sha256 = registry_sha256
        else:
            self.registry_rows = [dict(row) for row in registry_rows]
            self.registry_sha256 = sha256_bytes(canonical_bytes({"schema_version": 1, "rows": self.registry_rows}))
        self.registry_by_id = {str(row["sequence_id"]): row for row in self.registry_rows}
        self.budget_authority = budget_authority
        self.owner_runner = owner_runner
        if owner_source_edges is not None and type(owner_source_edges) is not prevention_source_probes.SourceEdgeRegistry:
            raise ControllerError("typed-owner-source-edge-registry-required")
        if (
            owner_source_edges is not None
            and _contract_acceptance is None
            and _host_source_authority is None
            and not _test_source_edges
        ):
            raise ControllerError("caller-source-edge-registry-prohibited")
        self.owner_source_edges = owner_source_edges
        self.delegation_verifier = delegation_verifier
        self.owner_binding_provider = owner_binding_provider
        self.owner_budget_producer = SourceOwnerBudgetProducer()
        if (
            _contract_acceptance is not None
            and type(_contract_acceptance) is not ContractAcceptanceAuthority
        ):
            raise ControllerError("typed-contract-acceptance-authority-required")
        self._contract_acceptance = _contract_acceptance

    @classmethod
    def for_test(cls, journal: PreventionJournal, **kwargs: Any) -> "PreventionController":
        """Construct an explicitly non-production controller for isolated unit tests."""
        return cls(journal, _test_source_edges=True, **kwargs)

    @classmethod
    def for_host_runtime(
        cls,
        journal: PreventionJournal,
        authority: HostSourceEdgeAuthority,
        **kwargs: Any,
    ) -> "PreventionController":
        """Attach external edges only after the same journal authenticates the host."""
        if type(authority) is not HostSourceEdgeAuthority:
            raise ControllerError("typed-host-source-edge-authority-required")
        if (
            type(authority.source_edges)
            is not prevention_source_probes.SourceEdgeRegistry
            or not isinstance(authority.session_id, str)
            or not authority.session_id
            or not isinstance(authority.receipt_sha256, str)
            or len(authority.receipt_sha256) != 64
        ):
            raise ControllerError("host-source-edge-authority-invalid")
        events, _ = journal.replay()
        matching = [
            event for event in events
            if event.get("event_type") == "host_capability_recorded"
            and event.get("session_id") == authority.session_id
            and event.get("receipt_sha256") == authority.receipt_sha256
            and event.get("governance_level") == "FULLY_GOVERNED"
        ]
        if len(matching) != 1:
            raise ControllerError("host-source-edge-authority-unverified")
        return cls(
            journal,
            owner_source_edges=authority.source_edges,
            _host_source_authority=authority,
            **kwargs,
        )

    @classmethod
    def for_contract_acceptance(
        cls,
        journal: PreventionJournal,
        authority: ContractAcceptanceAuthority,
        *,
        acceptance_budget_producer: OwnerBudgetProducer | None = None,
        **kwargs: Any,
    ) -> "PreventionController":
        """Construct the normal controller with one non-persisted evidence case."""
        if type(authority) is not ContractAcceptanceAuthority:
            raise ControllerError("typed-contract-acceptance-authority-required")
        if any(
            not isinstance(value, str) or not value
            for value in authority.__dict__.values()
        ):
            raise ControllerError("contract-acceptance-authority-invalid")
        for name in (
            "owner_contract_sha256", "case_registry_sha256",
        ):
            value = getattr(authority, name)
            if len(value) != 64 or any(
                character not in "0123456789abcdef" for character in value
            ):
                raise ControllerError("contract-acceptance-authority-invalid")
        if authority.proof_kind not in _CONTRACT_ACCEPTANCE_PROOF_KINDS:
            raise ControllerError("contract-acceptance-proof-kind-invalid")
        if (
            journal.ownership.task_id != authority.task_id
            or journal.ownership.run_id != authority.run_id
        ):
            raise ControllerError("contract-acceptance-journal-ownership-mismatch")
        controller = cls(journal, _contract_acceptance=authority, **kwargs)
        if acceptance_budget_producer is not None:
            controller.owner_budget_producer = acceptance_budget_producer
        return controller

    def _contract_acceptance_allows(
        self, intent: ActionIntent, owner: Mapping[str, Any],
    ) -> bool:
        authority = self._contract_acceptance
        if authority is None:
            return False
        executable = owner.get("executable_contract")
        if not isinstance(executable, Mapping):
            return False
        parameters = intent.parameter_map()
        discriminator = parameters.get("command") or parameters.get("mode")
        profile = discriminator.value if discriminator is not None else "default"
        profiles = {
            row.get("profile")
            for row in executable.get("reconciliation_contract", {}).get(
                "observables", []
            )
            if isinstance(row, Mapping)
        }
        return bool(
            intent.task_id == authority.task_id
            and intent.run_id == authority.run_id
            and intent.intent_id == authority.intent_id
            and intent.requested_sequence_id == authority.owner_sequence_id
            and owner.get("sequence_id") == authority.owner_sequence_id
            and owner.get("availability_policy") == "AVAILABLE"
            and owner.get("owner_contract_sha256")
            == authority.owner_contract_sha256
            and executable.get("owner_contract_sha256")
            == authority.owner_contract_sha256
            and profile == authority.profile_id
            and profile in profiles
        )

    @staticmethod
    def _require_intent(intent: ActionIntent) -> ActionIntent:
        if type(intent) is not ActionIntent:
            raise ControllerError("typed-action-intent-required")
        return intent

    def _require_owned_intent(self, intent: ActionIntent) -> ActionIntent:
        intent = self._require_intent(intent)
        ownership = self.journal.ownership
        if intent.task_id != ownership.task_id or intent.run_id != ownership.run_id:
            raise ControllerError("action-intent-journal-ownership-mismatch")
        return intent

    @staticmethod
    def _intent_payload(intent: ActionIntent) -> dict[str, Any]:
        return {
            "intent_id": intent.intent_id,
            "requested_sequence_id": intent.requested_sequence_id,
            "requested_implementation_id": intent.requested_implementation_id,
            "compatibility_key": intent.compatibility_key,
            "action_class": intent.action_class.value,
            "parameters": [
                {"name": item.name, "value": item.value.canonical_json()}
                for item in intent.parameters
            ],
        }

    def register_intent(self, intent: ActionIntent) -> dict[str, Any]:
        intent = self._require_owned_intent(intent)
        payload = self._intent_payload(intent)
        events, _ = self.journal.replay()
        matching = [
            event for event in events
            if event.get("intent_id") == intent.intent_id
            and event["event_type"] == "action_intent_recorded"
        ]
        if matching:
            if len(matching) != 1:
                raise ControllerError("intent-id-already-used")
            existing = matching[0]
            if any(existing[key] != value for key, value in payload.items()):
                raise ControllerError("intent-id-payload-mismatch")
            intent_result = {"event_id": existing["event_id"], "replayed": True}
        else:
            intent_result = self.journal.append("action_intent_recorded", payload)

        eligibility_payload = self._eligibility_payload(intent)
        events, _ = self.journal.replay()
        eligibility = [
            event for event in events
            if event.get("intent_id") == intent.intent_id
            and event["event_type"] == "action_eligibility_recorded"
        ]
        if eligibility:
            if len(eligibility) != 1 or any(
                eligibility[0][key] != value for key, value in eligibility_payload.items()
            ):
                raise ControllerError("intent-eligibility-payload-mismatch")
            eligibility_result = {"event_id": eligibility[0]["event_id"], "replayed": True}
        else:
            eligibility_result = self.journal.append("action_eligibility_recorded", eligibility_payload)
        return {
            **intent_result,
            "eligibility_event_id": eligibility_result["event_id"],
            "eligibility_replayed": eligibility_result.get("replayed", False),
            "checkpoint": self.journal.load_checkpoint(),
        }

    def _eligibility_payload(self, intent: ActionIntent) -> dict[str, Any]:
        owner = self.registry_by_id.get(intent.requested_sequence_id)
        if owner is None:
            recurrence = RecurrencePolicy.NOT_APPLICABLE
            availability = AvailabilityPolicy.UNAVAILABLE
            owner_sequence_id = intent.requested_sequence_id
            owner_contract_sha256 = None
            reason = IneligibleReasonCode.OWNER_CONTRACT_UNRESOLVED
        else:
            recurrence = RecurrencePolicy(owner.get("recurrence_policy", RecurrencePolicy.NOT_APPLICABLE.value))
            availability = AvailabilityPolicy(owner.get("availability_policy", AvailabilityPolicy.UNAVAILABLE.value))
            owner_sequence_id = str(owner["sequence_id"])
            owner_contract_sha256 = owner.get("owner_contract_sha256")
            if recurrence == RecurrencePolicy.ONE_SHOT:
                reason = IneligibleReasonCode.RECURRENCE_ONE_SHOT
            elif recurrence == RecurrencePolicy.NOT_APPLICABLE:
                reason = IneligibleReasonCode.RECURRENCE_NOT_APPLICABLE
            elif availability == AvailabilityPolicy.UNAVAILABLE:
                reason = IneligibleReasonCode.AVAILABILITY_UNAVAILABLE
            elif availability == AvailabilityPolicy.CUSTODIAN_EVIDENCE_REQUIRED:
                reason = IneligibleReasonCode.AVAILABILITY_CUSTODIAN_EVIDENCE_REQUIRED
            elif not owner_contract_sha256 or not owner.get("executable_contract"):
                reason = IneligibleReasonCode.OWNER_CONTRACT_UNRESOLVED
            elif intent.action_class.value not in owner.get("registered_host_action_classes", ()):
                reason = IneligibleReasonCode.UNREGISTERED_ACTION_CLASS
            else:
                reason = None
        eligible = reason is None
        return {
            "intent_id": intent.intent_id,
            "registry_sha256": self.registry_sha256,
            "owner_sequence_id": owner_sequence_id,
            "owner_contract_sha256": owner_contract_sha256,
            "recurrence_policy": recurrence.value,
            "availability_policy": availability.value,
            "eligibility": eligible,
            "ineligible_reason_code": reason.value if reason else None,
        }

    def dispatch(self, intent: ActionIntent) -> DispatchDecision:
        intent = self._require_owned_intent(intent)
        events, _ = self.journal.replay()
        matching_intents = [
            event for event in events
            if event["event_type"] == "action_intent_recorded"
            and event["intent_id"] == intent.intent_id
        ]
        if len(matching_intents) != 1:
            raise ControllerError("intent-must-be-recorded-exactly-once")
        matching_eligibility = [
            event for event in events
            if event["event_type"] == "action_eligibility_recorded"
            and event["intent_id"] == intent.intent_id
        ]
        if len(matching_eligibility) != 1:
            raise ControllerError("intent-eligibility-must-be-recorded-exactly-once")
        prior_dispatches = [
            event for event in events
            if event.get("intent_id") == intent.intent_id
            and event["event_type"] in {"dispatch_selected", "dispatch_rejected"}
        ]
        if len(prior_dispatches) > 1:
            raise ControllerError("intent-dispatch-recorded-more-than-once")
        if prior_dispatches:
            event = prior_dispatches[0]
            return DispatchDecision(
                decision_id=event["decision_id"], intent_id=intent.intent_id,
                kind=DecisionKind(event["decision_kind"]), reason_code=event["reason_code"],
                effective_sequence_id=event.get("effective_sequence_id"),
                effective_implementation_id=event.get("effective_implementation_id"),
                owner_contract_sha256=event.get("selected_owner_contract_sha256"),
            )
        started = time.monotonic_ns()
        decision = Selector(self.registry_rows, events).select(intent)
        elapsed_ms = max(0, (time.monotonic_ns() - started) // 1_000_000)
        event_type, payload = decision.event_payload(selector_milliseconds=elapsed_ms)
        self.journal.append(event_type, payload)
        if decision.kind == DecisionKind.SELECT_SUCCESSOR:
            prohibition = next(
                event for event in reversed(events)
                if event["event_type"] == "predecessor_prohibited"
                and event["predecessor_implementation_id"] == intent.requested_implementation_id
                and event["compatibility_key"] == intent.compatibility_key
            )
            self.journal.append("prevented_failure_recorded", {
                "intent_id": intent.intent_id,
                "decision_id": decision.decision_id,
                "compatibility_key": intent.compatibility_key,
                "failure_fingerprint": prohibition["failure_fingerprint"],
                "predecessor_implementation_id": intent.requested_implementation_id,
                "successor_implementation_id": decision.effective_implementation_id,
                "prohibition_event_id": prohibition["event_id"],
            })
        return decision

    def _checkpoint_child_intent(
        self, parent: ActionIntent, plan: prevention_adapters.InvocationPlan,
    ) -> ActionIntent:
        raw = plan.resolved_parameters.get("child_intent")
        required = {
            "child_owner_sequence_id", "child_contract_sha256", "child_intent_id",
            "child_parameters", "guard_receipt_id",
        }
        if not isinstance(raw, Mapping) or set(raw) != required:
            raise ControllerError("checkpoint-child-intent-invalid")
        child_owner_id = raw["child_owner_sequence_id"]
        child_owner = self.registry_by_id.get(str(child_owner_id))
        if (
            child_owner_id == parent.requested_sequence_id
            or not isinstance(child_owner, Mapping)
            or child_owner.get("standalone") is not True
            or child_owner.get("availability_policy") != "AVAILABLE"
            or child_owner.get("owner_contract_sha256") != raw["child_contract_sha256"]
        ):
            raise ControllerError("checkpoint-child-owner-unavailable")
        executable = child_owner.get("executable_contract")
        admission = executable.get("execution_admission") if isinstance(executable, Mapping) else None
        acceptance_composition = bool(
            self._contract_acceptance is not None
            and self._contract_acceptance.owner_sequence_id
            == "convergence-checkpoint-run"
        )
        if (
            not isinstance(admission, Mapping)
            or admission.get("contract_verification") != "VERIFIED"
            or admission.get("dispatch_admission") != "STANDALONE"
        ) and not acceptance_composition:
            raise ControllerError("checkpoint-child-owner-unverified")
        rows = raw["child_parameters"]
        if not isinstance(rows, list):
            raise ControllerError("checkpoint-child-parameters-invalid")
        try:
            parameters = tuple(TypedParameter.from_json(row) for row in rows)
            action_class = ActionClass(child_owner["registered_host_action_classes"][0])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ControllerError("checkpoint-child-parameters-invalid") from exc
        parameter_identity = [
            {"name": item.name, "value": item.value.canonical_json()}
            for item in parameters
        ]
        return ActionIntent(
            intent_id=str(raw["child_intent_id"]),
            task_id=parent.task_id,
            run_id=parent.run_id,
            requested_sequence_id=str(child_owner_id),
            requested_implementation_id=str(child_owner["implementation_source_sha256"]),
            compatibility_key=sha256_bytes(canonical_bytes({
                "child_owner_sequence_id": child_owner_id,
                "child_contract_sha256": raw["child_contract_sha256"],
                "child_parameters": parameter_identity,
                "guard_receipt_id": raw["guard_receipt_id"],
            })),
            action_class=action_class,
            parameters=parameters,
        )

    def _checkpoint_source_result(self, argv: Sequence[str]) -> Mapping[str, Any]:
        try:
            effect_id = argv[list(argv).index("--prevention-effect-id") + 1]
            receipt = json.loads(
                prevention_source_receipt.receipt_path(effect_id).read_text(encoding="utf-8")
            )
            checkpoint = receipt["result_identity"]
        except (ValueError, IndexError, KeyError, OSError, json.JSONDecodeError) as exc:
            raise ControllerError("checkpoint-applied-receipt-unavailable") from exc
        if not isinstance(checkpoint, Mapping) or checkpoint.get("verdict") != "CHECKPOINT_APPLIED":
            raise ControllerError("checkpoint-applied-receipt-invalid")
        return checkpoint

    def _complete_checkpoint_child(
        self, parent: ActionIntent, plan: prevention_adapters.InvocationPlan,
        checkpoint: Mapping[str, Any],
    ) -> ExecutionResult:
        child = self._checkpoint_child_intent(parent, plan)
        child_result = self._execute(child, budget_already_reserved=True)
        child_effect = child_result.get("effect") if isinstance(child_result, Mapping) else None
        if child_result.get("status") != "TERMINAL" or not isinstance(child_effect, Mapping):
            raise ControllerError("checkpoint-child-not-terminal")
        effect_id = child_effect.get("effect_id")
        events, _ = self.journal.replay()
        terminal = [
            event for event in events
            if event["event_type"] == "owner_terminal"
            and event.get("effect_id") == effect_id
            and event.get("owner_sequence_id") == child.requested_sequence_id
        ]
        if len(terminal) != 1 or terminal[0].get("semantic_verdict") != "PASS":
            raise ControllerError("checkpoint-child-terminal-link-invalid")
        child_owner = self.registry_by_id[child.requested_sequence_id]
        child_budget = derive_owner_unit_budget(
            child_owner["executable_contract"],
            {item.name: item.value.value for item in child.parameters},
            budget_producer=self.owner_budget_producer,
        )
        envelope = {
            "ok": True,
            "verdict": "PASS",
            "checkpoint": dict(checkpoint),
            "child": {
                "owner_sequence_id": child.requested_sequence_id,
                "owner_contract_sha256": child_owner["owner_contract_sha256"],
                "intent_id": child.intent_id,
                "effect_id": effect_id,
                "unit_budget_sha256": sha256_bytes(canonical_bytes(child_budget.canonical_json())),
                "terminal_artifact_sha256": terminal[0]["terminal_artifact_sha256"],
                "semantic_verdict": terminal[0]["semantic_verdict"],
            },
        }
        return ExecutionResult(0, json.dumps(envelope, sort_keys=True), "")

    def execute(self, intent: ActionIntent) -> dict[str, Any]:
        """Sole admitted path from typed intent through selection to durable owner effect."""
        return self._execute(intent, budget_already_reserved=False)

    def _execute(
        self, intent: ActionIntent, *, budget_already_reserved: bool,
    ) -> dict[str, Any]:
        self.register_intent(intent)
        requested_owner = self.registry_by_id.get(intent.requested_sequence_id)
        preflight_budget = None
        preflight_delegation = None
        preflight_plan = None
        runtime = None
        if (
            requested_owner is not None
            and requested_owner.get("availability_policy") == "AVAILABLE"
        ):
            preflight_delegation = self._require_parent_delegation(
                intent, requested_owner
            )
            executable_contract = requested_owner.get("executable_contract")
            if not isinstance(executable_contract, Mapping):
                return {
                    "status": "EXECUTION_INADMISSIBLE",
                    "reason": "owner-unit-budget-contract-unavailable",
                }
            admission = executable_contract.get("execution_admission")
            acceptance_composed_child = bool(
                budget_already_reserved
                and self._contract_acceptance is not None
                and self._contract_acceptance.owner_sequence_id
                == "convergence-checkpoint-run"
            )
            if (
                not self._contract_acceptance_allows(intent, requested_owner)
                and not acceptance_composed_child
                and (
                    not isinstance(admission, Mapping)
                    or admission.get("contract_verification") != "VERIFIED"
                    or admission.get("dispatch_admission")
                    not in {"STANDALONE", "PARENT_GATED"}
                )
            ):
                return {
                    "status": "EXECUTION_INADMISSIBLE",
                    "reason": (
                        admission.get("reason_code", "owner-execution-admission-unavailable")
                        if isinstance(admission, Mapping)
                        else "owner-execution-admission-unavailable"
                    ),
                }
            runtime_kwargs: dict[str, Any] = {
                "source_edges": self.owner_source_edges,
                "delegation": preflight_delegation,
                "binding_provider": self.owner_binding_provider,
            }
            if self.owner_runner is not None:
                runtime_kwargs["runner"] = self.owner_runner
            if intent.requested_sequence_id == "convergence-checkpoint-run":
                source_runner = self.owner_runner
                if source_runner is None:
                    from scripts.prevention_owner_runtime import subprocess_runner
                    source_runner = subprocess_runner

                def checkpoint_runner(argv: Sequence[str]) -> ExecutionResult:
                    source_result = source_runner(argv)
                    if source_result.returncode != 0:
                        return source_result
                    try:
                        source_envelope = json.loads(source_result.stdout)
                        checkpoint = source_envelope["checkpoint"]
                    except (json.JSONDecodeError, KeyError, TypeError) as exc:
                        raise ControllerError("checkpoint-source-envelope-invalid") from exc
                    try:
                        return self._complete_checkpoint_child(
                            intent, preflight_plan, checkpoint
                        )
                    except (ControllerError, OwnerRuntimeError) as exc:
                        return ExecutionResult(
                            5,
                            json.dumps({
                                "ok": False,
                                "verdict": "CHILD_NONTERMINAL",
                                "checkpoint": checkpoint,
                            }, sort_keys=True),
                            str(exc),
                        )

                def recovered_checkpoint_runner(argv: Sequence[str]) -> ExecutionResult:
                    return self._complete_checkpoint_child(
                        intent, preflight_plan, self._checkpoint_source_result(argv)
                    )

                runtime_kwargs["runner"] = checkpoint_runner
                runtime_kwargs["recovered_runner"] = recovered_checkpoint_runner
            runtime = OwnerRuntime(self.journal, **runtime_kwargs)
            try:
                preflight_plan = runtime.initialize(intent, requested_owner)
                budget_producer = self.owner_budget_producer
                if (
                    intent.requested_sequence_id == "greenfield-full-drive"
                    and self._contract_acceptance is None
                ):
                    if self.owner_source_edges is None:
                        raise BudgetError("greenfield-durable-frontier-unavailable")
                    try:
                        frontier_transport = (
                            prevention_source_probes.build_greenfield_frontier_transport(
                                self.owner_source_edges
                            )
                        )
                    except prevention_source_probes.SourceProbeError as exc:
                        raise BudgetError(str(exc)) from exc
                    budget_producer = SourceOwnerBudgetProducer(
                        frontier_transport=frontier_transport
                    )
                preflight_budget = derive_owner_unit_budget(
                    executable_contract, preflight_plan.resolved_parameters,
                    budget_producer=budget_producer,
                )
            except (BudgetError, prevention_adapters.AdapterError) as exc:
                return {
                    "status": "EXECUTION_INADMISSIBLE",
                    "reason": f"owner-unit-budget-derivation-failed:{exc}",
                }
        decision = self.dispatch(intent)
        if decision.kind == DecisionKind.REJECT:
            return {"status": "REJECTED", "decision": decision}
        if decision.effective_sequence_id != intent.requested_sequence_id:
            raise ControllerError("verified-successor-parameter-mapping-required")
        owner = self.registry_by_id[decision.effective_sequence_id]
        delegation = preflight_delegation
        if self.owner_source_edges is None:
            raise ControllerError("owner-source-edge-registry-required")
        if self.budget_authority is None:
            raise ControllerError("budget-authority-required-before-owner-execution")
        if preflight_budget is None:
            raise ControllerError("owner-unit-budget-preflight-missing")
        budget = preflight_budget
        if runtime is None or preflight_plan is None:
            raise ControllerError("owner-runtime-preflight-missing")
        completed = runtime.completed_state(intent, owner, plan=preflight_plan)
        if completed is not None:
            return {"status": "TERMINAL", "decision": decision, "effect": completed}
        reservation = None
        if not budget_already_reserved:
            reservation = self.budget_authority.admit(budget)
            if reservation is None:
                return {"status": "BUDGET_REJECTED", "decision": decision}
        state = runtime.run(intent, owner, plan=preflight_plan)
        if state["status"] == "TERMINAL" and reservation is not None:
            self.budget_authority.release(reservation.reservation_id)
        response = {
            "status": state["status"], "decision": decision,
            "effect": state,
        }
        if reservation is not None:
            response["reservation_id"] = reservation.reservation_id
        return response

    def _require_parent_delegation(
        self, intent: ActionIntent, owner: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        if owner.get("standalone") is not False:
            return None
        allowed = set(owner.get("parent_sequence_ids", ()))
        if not allowed:
            raise ControllerError("non-standalone-owner-parent-contract-missing")
        events, _ = self.journal.replay()
        delegations = [
            event for event in events
            if event["event_type"] == "child_delegation_recorded"
            and event["child_owner_sequence_id"] == intent.requested_sequence_id
            and event["child_intent_id"] == intent.intent_id
        ]
        if len(delegations) != 1:
            raise ControllerError("active-parent-delegation-required")
        delegation = delegations[0]
        if delegation["parent_owner_sequence_id"] not in allowed:
            raise ControllerError("delegation-parent-not-allowed")
        child_parameters = {item.name: item.value.value for item in intent.parameters}
        if (
            child_parameters.get("delegation_id") != delegation["delegation_id"]
            or child_parameters.get("mode") != delegation["mode"]
        ):
            raise ControllerError("delegation-child-parameter-binding-mismatch")
        parent_prepared = [
            event for event in events
            if event["event_type"] == "effect_prepared"
            and event["effect_id"] == delegation["parent_effect_id"]
            and event["owner_sequence_id"] == delegation["parent_owner_sequence_id"]
        ]
        parent_started = [
            event for event in events
            if event["event_type"] == "effect_execution_started"
            and event["effect_id"] == delegation["parent_effect_id"]
        ]
        parent_terminal = [
            event for event in events
            if event["event_type"] in {"effect_committed", "owner_terminal"}
            and event["effect_id"] == delegation["parent_effect_id"]
        ]
        if len(parent_prepared) != 1 or len(parent_started) != 1 or parent_terminal:
            raise ControllerError("delegation-parent-not-same-journal-started")
        parent_lifecycle = [
            event for event in events
            if event.get("effect_id") == delegation["parent_effect_id"]
            and event["event_type"] in {
                "effect_reconciled", "effect_execution_authorized",
                "effect_execution_started", "effect_committed", "owner_terminal",
            }
        ]
        if not parent_lifecycle or parent_lifecycle[-1]["event_type"] != "effect_execution_started":
            raise ControllerError("delegation-parent-not-same-journal-started")
        consumed = [
            event for event in events
            if event["event_type"] == "child_delegation_consumed"
            and event["delegation_id"] == delegation["delegation_id"]
        ]
        if len(consumed) > 1:
            raise ControllerError("delegation-consumed-more-than-once")
        if consumed and (
            consumed[0]["parent_effect_id"] != delegation["parent_effect_id"]
            or consumed[0]["child_intent_id"] != intent.intent_id
        ):
            raise ControllerError("delegation-consumption-identity-mismatch")
        if self.delegation_verifier is not None:
            verified = self.delegation_verifier(
                delegation["verification_event_id"], delegation["blocker_id"]
            )
        else:
            global_events, _ = work_memory.load_ledger(work_memory.LEDGER)
            verification = next((
                event for event in global_events
                if event["event_type"] == "verification_recorded"
                and event["event_id"] == delegation["verification_event_id"]
            ), None)
            verified = bool(
                verification is not None
                and verification.get("outcome") == "passed"
                and verification.get("quality") == "same-path"
                and delegation["blocker_id"] in verification.get("blocker_ids", [])
            )
        if not verified:
            raise ControllerError("delegation-blocker-verification-invalid")
        return delegation
