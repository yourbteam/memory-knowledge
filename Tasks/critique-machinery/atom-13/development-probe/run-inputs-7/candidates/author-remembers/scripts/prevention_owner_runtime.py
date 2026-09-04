#!/usr/bin/env python3
"""Durable effect runtime for typed prevention owner invocations."""

from __future__ import annotations

import json
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

try:
    from scripts import prevention_adapters, prevention_source_probes, work_memory
    from scripts.prevention_contract import ActionIntent, canonical_bytes, sha256_bytes
    from scripts.prevention_journal import PreventionJournal
except ModuleNotFoundError:  # direct script execution
    import prevention_adapters
    import prevention_source_probes
    import work_memory
    from prevention_contract import ActionIntent, canonical_bytes, sha256_bytes
    from prevention_journal import PreventionJournal


class OwnerRuntimeError(RuntimeError):
    """Stable fail-closed owner lifecycle error."""


@dataclass(frozen=True)
class ExecutionResult:
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[Sequence[str]], ExecutionResult]
def subprocess_runner(argv: Sequence[str]) -> ExecutionResult:
    completed = subprocess.run(
        list(argv), shell=False, check=False, text=True, capture_output=True
    )
    return ExecutionResult(completed.returncode, completed.stdout, completed.stderr)


class OwnerRuntime:
    """Prepare, execute, verify, terminalize, and resume one durable effect."""

    def __init__(
        self,
        journal: PreventionJournal,
        *,
        runner: Runner = subprocess_runner,
        source_edges: prevention_source_probes.SourceEdgeRegistry | None = None,
        delegation: Mapping[str, Any] | None = None,
        binding_provider: prevention_adapters.BindingProvider | None = None,
        recovered_runner: Runner | None = None,
        _test_transport: prevention_adapters.ObservationTransport | None = None,
    ):
        self.journal = journal
        self.runner = runner
        self.source_edges = source_edges
        self._test_transport = _test_transport
        self._observation_transports: dict[
            str, prevention_adapters.ObservationTransport
        ] = {}
        self.delegation = dict(delegation) if delegation is not None else None
        self.binding_provider = binding_provider
        self.recovered_runner = recovered_runner
        self.effects_dir = journal.prevention_dir / "effects"
        self.artifacts_dir = journal.prevention_dir / "artifacts"

    @classmethod
    def for_test(
        cls,
        journal: PreventionJournal,
        *,
        observation_transport: prevention_adapters.ObservationTransport,
        runner: Runner = subprocess_runner,
        delegation: Mapping[str, Any] | None = None,
        binding_provider: prevention_adapters.BindingProvider | None = None,
    ) -> "OwnerRuntime":
        """Explicit non-production constructor; its traces are never admissible."""
        if observation_transport is None:
            raise OwnerRuntimeError("test-observation-transport-required")
        return cls(
            journal,
            runner=runner,
            delegation=delegation,
            binding_provider=binding_provider,
            _test_transport=observation_transport,
        )

    def _effect_path(self, effect_id: str) -> Path:
        return self.effects_dir / f"{effect_id}.json"

    def _write_state(self, path: Path, state: Mapping[str, Any]) -> None:
        work_memory._atomic_write(path, canonical_bytes(dict(state)))

    def _write_artifact(self, value: Mapping[str, Any]) -> tuple[str, Path]:
        payload = canonical_bytes(dict(value))
        artifact_hash = sha256_bytes(payload)
        path = self.artifacts_dir / f"{artifact_hash}.json"
        if path.is_file():
            if path.read_bytes() != payload:
                raise OwnerRuntimeError("content-addressed-artifact-conflict")
        else:
            work_memory._atomic_write(path, payload)
        return artifact_hash, path

    def _load_state(self, path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise OwnerRuntimeError("effect-state-invalid") from exc
        if not isinstance(value, dict) or value.get("schema_version") != 1:
            raise OwnerRuntimeError("effect-state-invalid")
        return value

    def _append_once(
        self, event_type: str, payload: Mapping[str, Any], *, identity: tuple[str, str],
    ) -> dict[str, Any]:
        field, value = identity
        events, _ = self.journal.replay()
        matching = [
            event for event in events
            if event["event_type"] == event_type and event.get(field) == value
        ]
        if len(matching) > 1:
            raise OwnerRuntimeError(f"duplicate-{event_type}")
        if matching:
            existing = matching[0]
            if any(existing.get(key) != item for key, item in payload.items()):
                raise OwnerRuntimeError(f"conflicting-{event_type}")
            return existing
        result = self.journal.append(event_type, payload)
        events, _ = self.journal.replay()
        return next(event for event in events if event["event_id"] == result["event_id"])

    def _identity(
        self, intent: ActionIntent, owner: Mapping[str, Any],
        plan: prevention_adapters.InvocationPlan | None = None,
    ) -> tuple[prevention_adapters.InvocationPlan, str, str]:
        if plan is None:
            plan = self.initialize(intent, owner)
        executable = owner.get("executable_contract")
        if (
            plan.sequence_id != intent.requested_sequence_id
            or not isinstance(executable, Mapping)
            or plan.owner_contract_sha256 != executable.get("owner_contract_sha256")
        ):
            raise OwnerRuntimeError("initialized-plan-owner-mismatch")
        journal_id = sha256_bytes(canonical_bytes({
            "task_id": intent.task_id, "run_id": intent.run_id, "intent_id": intent.intent_id,
            "owner_sequence_id": plan.sequence_id,
        }))
        effect_id = sha256_bytes(canonical_bytes({
            "journal_id": journal_id,
            "intent_id": intent.intent_id,
            "implementation_id": intent.requested_implementation_id,
            "owner_contract_sha256": plan.owner_contract_sha256,
            "parameter_schema_sha256": plan.parameter_schema_sha256,
            "resolved_parameters": dict(plan.resolved_parameters),
            "root_bindings": dict(plan.root_bindings),
            "binding_receipt_sha256s": sorted(
                receipt.receipt_sha256 for receipt in plan.binding_receipts.values()
            ),
        }))
        return plan, journal_id, effect_id

    def initialize(
        self, intent: ActionIntent, owner: Mapping[str, Any],
    ) -> prevention_adapters.InvocationPlan:
        """Validate/materialize parameters and bindings without preparing an effect."""
        return prevention_adapters.build_invocation(
            intent, owner, binding_provider=self.binding_provider
        )

    def completed_state(
        self, intent: ActionIntent, owner: Mapping[str, Any],
        *, plan: prevention_adapters.InvocationPlan | None = None,
    ) -> dict[str, Any] | None:
        """Read a terminal checkpoint without preparing or reserving new work."""
        _, _, effect_id = self._identity(intent, owner, plan)
        state = self._load_state(self._effect_path(effect_id))
        if state is not None and state.get("status") == "TERMINAL":
            return state
        return None

    def prepare(
        self, intent: ActionIntent, owner: Mapping[str, Any],
        *, plan: prevention_adapters.InvocationPlan | None = None,
    ) -> tuple[prevention_adapters.InvocationPlan, dict[str, Any]]:
        plan, journal_id, effect_id = self._identity(intent, owner, plan)
        plan = prevention_adapters.bind_effect_context(plan, effect_id)
        executable = owner.get("executable_contract")
        if not isinstance(executable, Mapping):
            raise OwnerRuntimeError("owner-executable-contract-unavailable")
        reconciler = executable.get("reconciliation_contract")
        if not isinstance(reconciler, Mapping):
            raise OwnerRuntimeError("owner-reconciler-contract-unavailable")
        reconciler_sha256 = str(reconciler.get("policy_sha256", ""))
        reconciler_handler = str(reconciler.get("handler", ""))
        if not callable(prevention_adapters.__dict__.get(reconciler_handler)):
            raise OwnerRuntimeError("owner-reconciler-handler-unavailable")
        terminal_contract = executable.get("terminal_contract")
        if not isinstance(terminal_contract, Mapping):
            raise OwnerRuntimeError("owner-terminal-contract-unavailable")
        terminal_handler = str(terminal_contract.get("handler", ""))
        if not callable(prevention_adapters.__dict__.get(terminal_handler)):
            raise OwnerRuntimeError("owner-terminal-handler-unavailable")
        terminal_policy_sha256 = str(terminal_contract.get("policy_sha256", ""))
        parameter_identities = {
            name: sha256_bytes(canonical_bytes(value))
            for name, value in sorted(plan.resolved_parameters.items())
            if name not in plan.binding_receipts
        }
        receipt_identities = {
            name: {
                "binding_receipt_sha256": receipt.receipt_sha256,
                "provider_id": receipt.provider_id,
                "key_or_resource_id": receipt.key_or_resource_id,
                "version_id": receipt.version_id,
                "value_fingerprint_sha256": receipt.value_fingerprint_sha256,
            }
            for name, receipt in sorted(plan.binding_receipts.items())
        }
        profile = plan.resolved_parameters.get(
            "command", plan.resolved_parameters.get("mode", "default")
        )
        try:
            observable_evidence = prevention_adapters._source_observable_evidence(
                plan, str(profile)
            )
            probe_ids = observable_evidence["profile"]["capture_schema"]["probe_ids"]
        except prevention_adapters.AdapterError as exc:
            raise OwnerRuntimeError(f"preparation-observable-profile-invalid:{exc}") from exc
        identity_expected_sha256 = sha256_bytes(canonical_bytes({
            "effect_id": effect_id,
            "owner_sequence_id": plan.sequence_id,
            "profile": profile,
        }))
        observation_targets = {
            "implementation_source_sha256": plan.implementation_source_sha256,
            "identity_expected_sha256": identity_expected_sha256,
            "parameter_identity_sha256s": parameter_identities,
            "root_binding_sha256s": {
                name: sha256_bytes(canonical_bytes(value))
                for name, value in sorted(plan.root_bindings.items())
            },
        }
        prepared_prestate_identities = {
            "owner_contract_sha256": plan.owner_contract_sha256,
            "implementation_source_sha256": plan.implementation_source_sha256,
            "parameter_schema_sha256": plan.parameter_schema_sha256,
        }
        observation_targets["prestate_expected_sha256"] = sha256_bytes(canonical_bytes({
            "effect_id": effect_id,
            "owner_sequence_id": plan.sequence_id,
            "profile": profile,
            "source_status": "ABSENT",
        }))
        observation_targets["probe_expected_sha256s"] = {
            probe_id: sha256_bytes(canonical_bytes({
                "effect_id": effect_id,
                "owner_sequence_id": plan.sequence_id,
                "profile": profile,
                "probe_id": probe_id,
                "source_status": "SATISFIED",
            }))
            for probe_id in probe_ids
        }
        observation_transport_kind = (
            "TEST_TRANSPORT"
            if self._test_transport is not None
            else "PRODUCTION_SOURCE_PROBE"
        )
        preparation_artifact = {
            "schema_version": 1,
            "effect_id": effect_id,
            "journal_id": journal_id,
            "owner_sequence_id": plan.sequence_id,
            "owner_contract_sha256": plan.owner_contract_sha256,
            "reconciler_sha256": reconciler_sha256,
            "reconciliation_handler": reconciler_handler,
            "reconciliation_contract": dict(reconciler),
            "terminal_handler": terminal_handler,
            "terminal_policy_sha256": terminal_policy_sha256,
            "terminal_contract": dict(terminal_contract),
            "parameter_schema_sha256": plan.parameter_schema_sha256,
            "resolved_parameters": dict(plan.resolved_parameters),
            "root_bindings": dict(plan.root_bindings),
            "binding_receipts": {
                name: receipt.canonical_json()
                for name, receipt in sorted(plan.binding_receipts.items())
            },
            "effect_context_binding": plan.effect_context_binding,
            "observation_targets": observation_targets,
            "prepared_prestate_identities": prepared_prestate_identities,
            "prepared_receipt_identities": receipt_identities,
            "observation_transport_kind": observation_transport_kind,
        }
        preparation_artifact_sha256, preparation_path = self._write_artifact(
            preparation_artifact
        )
        plan = prevention_adapters.bind_preparation_context(
            plan, effect_id, preparation_artifact_sha256
        )
        preparation_bytes = preparation_path.read_bytes()
        if sha256_bytes(preparation_bytes) != preparation_artifact_sha256:
            raise OwnerRuntimeError("preparation-artifact-hash-verification-failed")
        try:
            verified_preparation = json.loads(preparation_bytes)
        except json.JSONDecodeError as exc:
            raise OwnerRuntimeError("preparation-artifact-invalid") from exc
        if verified_preparation != preparation_artifact:
            raise OwnerRuntimeError("preparation-artifact-canonical-roundtrip-failed")
        if self._test_transport is not None:
            transport = self._test_transport
        else:
            if self.source_edges is None:
                raise OwnerRuntimeError("production-source-edge-registry-required")
            try:
                transport = prevention_source_probes.build_production_transport(
                    executable, verified_preparation, self.source_edges
                )
            except prevention_source_probes.SourceProbeError as exc:
                raise OwnerRuntimeError(f"production-source-probe-unavailable:{exc}") from exc
        self._observation_transports[effect_id] = transport
        state_hash = sha256_bytes(canonical_bytes({
            "transition": "EFFECT_PREPARED", "effect_id": effect_id,
        }))
        transition = self._append_once(
            "transition_prepared",
            {"journal_id": journal_id, "transition": "EFFECT_PREPARED", "state_hash": state_hash},
            identity=("journal_id", journal_id),
        )
        for parameter_name, receipt in sorted(plan.binding_receipts.items()):
            binding_payload = {
                "intent_id": intent.intent_id,
                "effect_id": effect_id,
                "owner_sequence_id": plan.sequence_id,
                "owner_contract_sha256": plan.owner_contract_sha256,
                "parameter_name": parameter_name,
                **receipt.canonical_json(),
                "binding_receipt_sha256": receipt.receipt_sha256,
            }
            self.journal.append_unique(
                "owner_binding_recorded",
                binding_payload,
                identity={"effect_id": effect_id, "parameter_name": parameter_name},
            )
        effect_payload = {
            "journal_id": journal_id,
            "effect_id": effect_id,
            "idempotency_key": sha256_bytes(canonical_bytes({
                "effect_id": effect_id,
                "compatibility_key": intent.compatibility_key,
            })),
            "effect_kind": "OWNER_INVOCATION",
            "owner_sequence_id": plan.sequence_id,
            "implementation_id": intent.requested_implementation_id,
            "effect_task_id": self.journal.ownership.task_id,
            "effect_run_id": self.journal.ownership.run_id,
            "effect_branch_ref": self.journal.ownership.branch_ref,
            "effect_worktree_id": self.journal.ownership.worktree_id,
            "transition_prepared_event_id": transition["event_id"],
            "owner_contract_sha256": plan.owner_contract_sha256,
            "reconciler_sha256": reconciler_sha256,
            "preparation_artifact_sha256": preparation_artifact_sha256,
        }
        prepared_event_id = str(uuid.uuid5(
            uuid.NAMESPACE_URL, f"prevention-effect-prepared:{effect_id}"
        ))
        grouped_events: list[
            tuple[str, Mapping[str, Any], Mapping[str, Any]]
        ] = [
            ("effect_prepared", effect_payload, {"effect_id": effect_id})
        ]
        grouped_event_ids = [prepared_event_id]
        for receipt in plan.binding_receipts.values():
            if not receipt.consumable:
                continue
            grouped_events.append((
                "authorization_receipt_consumed", {
                    "receipt_id": receipt.receipt_id,
                    "provider_id": receipt.provider_id,
                    "version_id": receipt.version_id,
                    "scope_sha256": receipt.scope_sha256,
                    "intent_id": intent.intent_id,
                    "effect_id": effect_id,
                    "owner_sequence_id": plan.sequence_id,
                    "owner_contract_sha256": plan.owner_contract_sha256,
                    "effect_prepared_event_id": prepared_event_id,
                },
                {"receipt_id": receipt.receipt_id},
            ))
            grouped_event_ids.append(str(uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"prevention-receipt-consumed:{receipt.receipt_id}",
            )))
        if self.delegation is not None:
            if (
                self.delegation.get("child_owner_sequence_id") != plan.sequence_id
                or self.delegation.get("child_intent_id") != intent.intent_id
            ):
                raise OwnerRuntimeError("delegation-child-identity-mismatch")
            grouped_events.append((
                "child_delegation_consumed", {
                    "delegation_id": self.delegation["delegation_id"],
                    "parent_effect_id": self.delegation["parent_effect_id"],
                    "child_effect_id": effect_id,
                    "child_intent_id": intent.intent_id,
                    "effect_prepared_event_id": prepared_event_id,
                },
                {"delegation_id": self.delegation["delegation_id"]},
            ))
            grouped_event_ids.append(str(uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"prevention-delegation-consumed:{self.delegation['delegation_id']}",
            )))
        prepared = self.journal.append_unique_group(
            grouped_events, event_ids=grouped_event_ids
        )[0]
        path = self._effect_path(effect_id)
        state = self._load_state(path)
        expected = {
            "schema_version": 1, "effect_id": effect_id, "journal_id": journal_id,
            "owner_sequence_id": plan.sequence_id, "status": "PREPARED",
            "prepared_event_id": prepared["event_id"],
            "owner_contract_sha256": plan.owner_contract_sha256,
            "reconciler_sha256": reconciler_sha256,
            "preparation_artifact_sha256": preparation_artifact_sha256,
            "terminal_policy_sha256": terminal_policy_sha256,
            "effect_context_binding": plan.effect_context_binding,
            "preparation_context_binding": plan.preparation_context_binding,
            "observation_targets": observation_targets,
            "prepared_prestate_identities": prepared_prestate_identities,
            "prepared_receipt_identities": receipt_identities,
            "observation_transport_kind": observation_transport_kind,
            "attempt_generation": 0,
        }
        if state is None:
            self._write_state(path, expected)
            state = expected
        elif any(
            state.get(key) != expected[key]
            for key in (
                "schema_version", "effect_id", "journal_id", "owner_sequence_id",
                "prepared_event_id", "owner_contract_sha256", "reconciler_sha256",
                "preparation_artifact_sha256", "terminal_policy_sha256",
                "effect_context_binding",
                "preparation_context_binding",
                "observation_transport_kind",
            )
        ):
            raise OwnerRuntimeError("effect-state-identity-mismatch")
        state = self._synchronize_state_from_journal(state)
        self._write_state(path, state)
        return plan, state

    def _synchronize_state_from_journal(
        self, state: Mapping[str, Any],
    ) -> dict[str, Any]:
        events, _ = self.journal.replay()
        terminal = [
            event for event in events
            if event["event_type"] == "owner_terminal"
            and event["effect_id"] == state["effect_id"]
        ]
        if len(terminal) > 1:
            raise OwnerRuntimeError("duplicate-owner_terminal")
        if terminal:
            event = terminal[0]
            artifact_path = self.artifacts_dir / f"{event['terminal_artifact_sha256']}.json"
            if (
                not artifact_path.is_file()
                or sha256_bytes(artifact_path.read_bytes())
                != event["terminal_artifact_sha256"]
            ):
                raise OwnerRuntimeError("terminal-artifact-missing-or-drifted")
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            for field in (
                "effect_id", "owner_sequence_id", "owner_contract_sha256",
                "result_kind", "result_hash", "terminal_evidence_sha256",
                "semantic_verdict",
            ):
                if artifact.get(field) != event.get(field):
                    raise OwnerRuntimeError("terminal-event-artifact-conflict")
            return {
                **dict(state),
                "status": "TERMINAL",
                "result_kind": event["result_kind"],
                "result_hash": event["result_hash"],
                "terminal_path": str(artifact_path),
                "terminal_event_id": event["event_id"],
                "terminal_artifact_sha256": event["terminal_artifact_sha256"],
            }
        if state.get("status") == "TERMINAL":
            raise OwnerRuntimeError("terminal-state-without-authority-event")
        committed = [
            event for event in events
            if event["event_type"] == "effect_committed"
            and event["effect_id"] == state["effect_id"]
        ]
        if len(committed) > 1:
            raise OwnerRuntimeError("multiple-committed-effect-generations")
        if committed:
            event = committed[0]
            artifact_path = self.artifacts_dir / f"{event['result_hash']}.json"
            if (
                not artifact_path.is_file()
                or sha256_bytes(artifact_path.read_bytes()) != event["result_hash"]
            ):
                raise OwnerRuntimeError("committed-result-artifact-missing-or-drifted")
            result = json.loads(artifact_path.read_text(encoding="utf-8"))
            if result.get("returncode") != event["exit_status"]:
                raise OwnerRuntimeError("committed-result-exit-status-conflict")
            return {
                **dict(state),
                "status": "EXECUTED",
                "attempt_generation": event["attempt_generation"],
                "execution_started_event_id": event["execution_started_event_id"],
                "effect_committed_event_id": event["event_id"],
                "result": result,
                "result_hash": event["result_hash"],
            }
        started = [
            event for event in events
            if event["event_type"] == "effect_execution_started"
            and event["effect_id"] == state["effect_id"]
        ]
        if not started:
            return dict(state)
        latest = max(started, key=lambda event: event["attempt_generation"])
        if latest["attempt_generation"] < int(state.get("attempt_generation", 0)):
            raise OwnerRuntimeError("effect-state-generation-ahead-of-journal")
        if (
            latest["attempt_generation"] == int(state.get("attempt_generation", 0))
            and state.get("status") != "PREPARED"
        ):
            return dict(state)
        return {
            **dict(state), "status": "STARTED",
            "attempt_generation": latest["attempt_generation"],
            "execution_started_event_id": latest["event_id"],
        }

    def _observe(
        self,
        plan: prevention_adapters.InvocationPlan,
        state: Mapping[str, Any],
        preparation: Mapping[str, Any],
    ) -> prevention_adapters.ReconciliationObservation:
        reconciliation_contract = preparation.get("reconciliation_contract")
        if not isinstance(reconciliation_contract, Mapping):
            raise OwnerRuntimeError("reconciliation-contract-missing-from-preparation")
        spec = prevention_adapters._profile_observable(
            plan, reconciliation_contract, "reconciliation"
        )
        transport = self._observation_transports.get(str(state["effect_id"]))
        if transport is None:
            raise OwnerRuntimeError("owner-observation-transport-not-built")
        provider = prevention_adapters.__dict__.get(spec["provider_symbol"])
        if not callable(provider):
            raise OwnerRuntimeError("owner-reconciliation-provider-unavailable")
        observation = provider(plan, state, preparation, transport)
        if type(observation) is not prevention_adapters.ReconciliationObservation:
            raise OwnerRuntimeError("typed-reconciliation-observation-required")
        if (
            observation.effect_id != state["effect_id"]
            or observation.owner_sequence_id != plan.sequence_id
            or observation.preparation_artifact_sha256
            != state["preparation_artifact_sha256"]
        ):
            raise OwnerRuntimeError("reconciliation-observation-identity-mismatch")
        return observation

    def _reconcile_generation(
        self,
        plan: prevention_adapters.InvocationPlan,
        state: Mapping[str, Any],
    ) -> tuple[prevention_adapters.ReconciliationDecision, dict[str, Any]]:
        events, _ = self.journal.replay()
        existing = [
            event for event in events
            if event["event_type"] == "effect_reconciled"
            and event["effect_id"] == state["effect_id"]
            and event["attempt_generation"] == state["attempt_generation"]
        ]
        if len(existing) > 1:
            raise OwnerRuntimeError("duplicate-effect_reconciled")
        if existing:
            event = existing[0]
            artifact_path = self.artifacts_dir / f"{event['reconciliation_artifact_sha256']}.json"
            if not artifact_path.is_file() or sha256_bytes(artifact_path.read_bytes()) != event["reconciliation_artifact_sha256"]:
                raise OwnerRuntimeError("reconciliation-artifact-missing-or-drifted")
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            decision = prevention_adapters.ReconciliationDecision(
                classification=event["reconciliation"],
                observable_ownership_sha256=event["observable_ownership_sha256"],
                evidence_sha256=event["evidence_sha256"], artifact=artifact,
            )
            return decision, {**dict(state), "last_reconciliation_event_id": event["event_id"]}
        preparation_path = self.artifacts_dir / f"{state['preparation_artifact_sha256']}.json"
        if not preparation_path.is_file():
            raise OwnerRuntimeError("preparation-artifact-missing")
        preparation = json.loads(preparation_path.read_text(encoding="utf-8"))
        executable_handler = preparation.get("reconciliation_handler")
        if not isinstance(executable_handler, str):
            executable_handler = f"reconcile_{plan.sequence_id.replace('-', '_')}"
        handler = prevention_adapters.__dict__.get(executable_handler)
        if not callable(handler):
            raise OwnerRuntimeError("owner-reconciler-handler-unavailable")
        reconciliation_contract = preparation.get("reconciliation_contract")
        if not isinstance(reconciliation_contract, Mapping):
            raise OwnerRuntimeError("reconciliation-contract-missing-from-preparation")
        decision = handler(
            self._observe(plan, state, preparation),
            reconciliation_contract=reconciliation_contract,
        )
        artifact = {
            **dict(decision.artifact),
            "effect_id": state["effect_id"],
            "attempt_generation": state["attempt_generation"],
            "owner_contract_sha256": state["owner_contract_sha256"],
            "reconciler_sha256": state["reconciler_sha256"],
            "preparation_artifact_sha256": state["preparation_artifact_sha256"],
        }
        artifact_hash, _ = self._write_artifact(artifact)
        prior = state.get("last_reconciliation_event_id")
        payload = {
            "journal_id": state["journal_id"],
            "effect_id": state["effect_id"],
            "prepared_event_id": state["prepared_event_id"],
            "attempt_generation": state["attempt_generation"],
            "owner_contract_sha256": state["owner_contract_sha256"],
            "reconciler_sha256": state["reconciler_sha256"],
            "preparation_artifact_sha256": state["preparation_artifact_sha256"],
            "reconciliation": decision.classification,
            "reconciliation_artifact_sha256": artifact_hash,
            "observable_ownership_sha256": decision.observable_ownership_sha256,
            "evidence_sha256": decision.evidence_sha256,
        }
        if prior is not None:
            payload["prior_reconciliation_event_id"] = prior
        result = self.journal.append_unique(
            "effect_reconciled",
            payload,
            identity={
                "effect_id": state["effect_id"],
                "attempt_generation": state["attempt_generation"],
            },
        )
        persisted_decision = prevention_adapters.ReconciliationDecision(
            classification=decision.classification,
            observable_ownership_sha256=decision.observable_ownership_sha256,
            evidence_sha256=decision.evidence_sha256,
            artifact=artifact,
        )
        return persisted_decision, {
            **dict(state), "last_reconciliation_event_id": result["event_id"]
        }

    @staticmethod
    def _safe_result(result: ExecutionResult) -> dict[str, Any]:
        stdout_sha256 = sha256_bytes(result.stdout.encode("utf-8"))
        stderr_sha256 = sha256_bytes(result.stderr.encode("utf-8"))
        try:
            envelope = json.loads(result.stdout)
        except json.JSONDecodeError:
            envelope = None
            encoding = "INVALID_JSON"
        else:
            encoding = "JSON_OBJECT" if isinstance(envelope, Mapping) else "JSON_NON_OBJECT"
        if isinstance(envelope, Mapping):
            forbidden = {
                "password", "secret", "token", "api_key", "access_token",
                "refresh_token", "private_key", "credential", "credentials",
            }

            def contains_forbidden_key(value: Any) -> bool:
                if isinstance(value, Mapping):
                    return any(
                        str(key).lower() in forbidden or contains_forbidden_key(item)
                        for key, item in value.items()
                    )
                if isinstance(value, list):
                    return any(contains_forbidden_key(item) for item in value)
                return False

            if contains_forbidden_key(envelope):
                raise OwnerRuntimeError("owner-result-secret-field-forbidden")
        return {
            "returncode": result.returncode,
            "stdout_encoding": encoding,
            "stdout_sha256": stdout_sha256,
            "stderr_sha256": stderr_sha256,
            "result_envelope": dict(envelope) if isinstance(envelope, Mapping) else None,
        }

    def _commit_execution_result(
        self, path: Path, state: Mapping[str, Any], result: ExecutionResult,
    ) -> dict[str, Any]:
        safe_result = self._safe_result(result)
        result_hash, _ = self._write_artifact(safe_result)
        generation = int(state["attempt_generation"])
        committed = self.journal.append_unique(
            "effect_committed",
            {
                "journal_id": state["journal_id"],
                "effect_id": state["effect_id"],
                "prepared_event_id": state["prepared_event_id"],
                "attempt_generation": generation,
                "execution_started_event_id": state["execution_started_event_id"],
                "result_hash": result_hash,
                "exit_status": result.returncode,
            },
            identity={"effect_id": state["effect_id"], "attempt_generation": generation},
        )
        executed = {
            **dict(state),
            "status": "EXECUTED",
            "result": safe_result,
            "result_hash": result_hash,
            "effect_committed_event_id": committed["event_id"],
        }
        self._write_state(path, executed)
        return executed

    def run(
        self, intent: ActionIntent, owner: Mapping[str, Any],
        *, plan: prevention_adapters.InvocationPlan | None = None,
    ) -> dict[str, Any]:
        plan, state = self.prepare(intent, owner, plan=plan)
        path = self._effect_path(str(state["effect_id"]))
        status = state["status"]
        if status in {"PREPARED", "STARTED"}:
            decision, state = self._reconcile_generation(plan, state)
            if decision.classification == "INDETERMINATE":
                self._write_state(path, {**state, "status": "STARTED"})
                raise OwnerRuntimeError("effect-indeterminate-manual-reconciliation-required")
            execution_runner: Runner | None = None
            if decision.classification == "ALREADY_APPLIED" and self.recovered_runner is None:
                state = {**state, "status": "RECOVERED"}
                self._write_state(path, state)
            elif decision.classification == "ALREADY_APPLIED":
                if state.get("status") != "STARTED" or not state.get(
                    "execution_started_event_id"
                ):
                    raise OwnerRuntimeError("recovered-continuation-requires-started-attempt")
                state = self._commit_execution_result(
                    path, state, self.recovered_runner(plan.argv)
                )
            else:
                execution_runner = self.runner
                next_generation = int(state["attempt_generation"]) + 1
                authorization_payload = {
                    "journal_id": state["journal_id"],
                    "effect_id": state["effect_id"],
                    "attempt_generation": next_generation,
                    "prior_generation": state["attempt_generation"],
                    "not_applied_reconciliation_event_id": state["last_reconciliation_event_id"],
                    "owner_contract_sha256": state["owner_contract_sha256"],
                    "authorization_sha256": sha256_bytes(canonical_bytes({
                        "effect_id": state["effect_id"],
                        "attempt_generation": next_generation,
                        "reconciliation_event_id": state["last_reconciliation_event_id"],
                    })),
                }
                authorization = self.journal.append_unique(
                    "effect_execution_authorized",
                    authorization_payload,
                    identity={"effect_id": state["effect_id"], "attempt_generation": next_generation},
                )
                started = self.journal.append_unique(
                    "effect_execution_started",
                    {
                        "journal_id": state["journal_id"],
                        "effect_id": state["effect_id"],
                        "attempt_generation": next_generation,
                        "execution_authorized_event_id": authorization["event_id"],
                        "owner_contract_sha256": state["owner_contract_sha256"],
                    },
                    identity={"effect_id": state["effect_id"], "attempt_generation": next_generation},
                )
                state = {
                    **state,
                    "status": "STARTED",
                    "attempt_generation": next_generation,
                    "execution_started_event_id": started["event_id"],
                }
                self._write_state(path, state)
                if execution_runner is None:
                    raise OwnerRuntimeError("owner-execution-runner-unavailable")
                result = execution_runner(plan.argv)
                state = self._commit_execution_result(path, state, result)
        if state["status"] in {"EXECUTED", "RECOVERED"}:
            result_kind = (
                "EXECUTED_RESULT" if state["status"] == "EXECUTED" else "RECOVERED_RESULT"
            )
            if result_kind == "EXECUTED_RESULT":
                result_payload = dict(state["result"])
            else:
                events, _ = self.journal.replay()
                reconciliation = next(
                    event for event in events
                    if event["event_id"] == state["last_reconciliation_event_id"]
                )
                result_payload = {
                    "effect_id": state["effect_id"],
                    "reconciliation_event_id": state["last_reconciliation_event_id"],
                    "reconciliation_artifact_sha256": reconciliation[
                        "reconciliation_artifact_sha256"
                    ],
                }
            preparation_path = self.artifacts_dir / f"{state['preparation_artifact_sha256']}.json"
            if not preparation_path.is_file():
                raise OwnerRuntimeError("preparation-artifact-missing")
            preparation = json.loads(preparation_path.read_text(encoding="utf-8"))
            terminal_contract = preparation.get("terminal_contract")
            if not isinstance(terminal_contract, Mapping):
                raise OwnerRuntimeError("terminal-contract-missing-from-preparation")
            branch = terminal_contract.get("branches", {}).get(result_kind)
            if not isinstance(branch, Mapping):
                raise OwnerRuntimeError("terminal-result-branch-unavailable")
            required = set(branch.get("required_result_fields", []))
            forbidden = set(branch.get("forbidden_result_fields", []))
            if set(result_payload) != required or forbidden & set(result_payload):
                raise OwnerRuntimeError("terminal-result-branch-schema-invalid")
            observation_transport = self._observation_transports.get(
                str(state["effect_id"])
            )
            if observation_transport is None:
                raise OwnerRuntimeError("owner-terminal-semantic-observer-unavailable")
            terminal_spec = prevention_adapters._profile_observable(
                plan, terminal_contract, "terminal"
            )
            terminal_provider = prevention_adapters.__dict__.get(
                terminal_spec["provider_symbol"]
            )
            if not callable(terminal_provider):
                raise OwnerRuntimeError("owner-terminal-provider-unavailable")
            semantic = terminal_provider(
                plan, state, result_kind, terminal_contract,
                observation_transport,
            )
            if (
                type(semantic) is not prevention_adapters.TerminalObservation
                or semantic.effect_id != state["effect_id"]
                or semantic.owner_sequence_id != plan.sequence_id
                or semantic.terminal_policy_sha256 != state["terminal_policy_sha256"]
                or semantic.preparation_artifact_sha256
                != state["preparation_artifact_sha256"]
            ):
                raise OwnerRuntimeError("owner-terminal-observation-identity-mismatch")
            terminal_handler_name = preparation.get("terminal_handler")
            terminal_handler = prevention_adapters.__dict__.get(terminal_handler_name)
            if not callable(terminal_handler):
                raise OwnerRuntimeError("owner-terminal-handler-unavailable")
            try:
                terminal_evidence = terminal_handler(
                    result_kind=result_kind,
                    result=result_payload,
                    semantic_observation=semantic,
                    terminal_contract=terminal_contract,
                )
            except prevention_adapters.AdapterError as exc:
                raise OwnerRuntimeError(f"owner-terminal-verification-failed:{exc}") from exc
            terminal_evidence_hash, _ = self._write_artifact(terminal_evidence)
            canonical_result = {
                "result_kind": result_kind,
                "effect_id": state["effect_id"],
                "evidence_sha256": terminal_evidence_hash,
            }
            if result_kind == "EXECUTED_RESULT":
                canonical_result["effect_committed_event_id"] = state[
                    "effect_committed_event_id"
                ]
                canonical_result["process_result_sha256"] = state["result_hash"]
            else:
                canonical_result["reconciliation_event_id"] = state[
                    "last_reconciliation_event_id"
                ]
                canonical_result["reconciliation_artifact_sha256"] = result_payload[
                    "reconciliation_artifact_sha256"
                ]
            result_hash = sha256_bytes(canonical_bytes(canonical_result))
            terminal = {
                "schema_version": 1,
                "effect_id": state["effect_id"],
                "owner_sequence_id": state["owner_sequence_id"],
                "owner_contract_sha256": state["owner_contract_sha256"],
                "terminal_policy_sha256": state["terminal_policy_sha256"],
                "status": "TERMINAL",
                "result_kind": result_kind,
                "result_hash": result_hash,
                "result_provenance": canonical_result,
                "terminal_evidence_sha256": terminal_evidence_hash,
                "semantic_verdict": "PASS",
            }
            terminal_artifact_hash, terminal_path = self._write_artifact(terminal)
            terminal_payload = {
                "effect_id": state["effect_id"],
                "owner_sequence_id": state["owner_sequence_id"],
                "owner_contract_sha256": state["owner_contract_sha256"],
                "result_kind": result_kind,
                "result_hash": result_hash,
                "terminal_evidence_sha256": terminal_evidence_hash,
                "terminal_artifact_sha256": terminal_artifact_hash,
                "semantic_verdict": "PASS",
            }
            if result_kind == "EXECUTED_RESULT":
                terminal_payload.update({
                    "effect_committed_event_id": state["effect_committed_event_id"],
                    "attempt_generation": state["attempt_generation"],
                    "execution_started_event_id": state["execution_started_event_id"],
                })
            else:
                events, _ = self.journal.replay()
                reconciliation = next(
                    event for event in events
                    if event["event_id"] == state["last_reconciliation_event_id"]
                )
                terminal_payload.update({
                    "reconciliation_event_id": reconciliation["event_id"],
                    "reconciliation_artifact_sha256": reconciliation["reconciliation_artifact_sha256"],
                })
            terminal_event = self.journal.append_unique(
                "owner_terminal", terminal_payload, identity={"effect_id": state["effect_id"]}
            )
            state = {
                **state,
                "status": "TERMINAL",
                "result_kind": result_kind,
                "terminal_path": str(terminal_path),
                "terminal_event_id": terminal_event["event_id"],
                "terminal_artifact_sha256": terminal_artifact_hash,
            }
            self._write_state(path, state)
        return dict(state)
