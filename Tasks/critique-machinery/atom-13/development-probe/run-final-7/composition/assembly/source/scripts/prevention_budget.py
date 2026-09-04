#!/usr/bin/env python3
"""Typed, durable, fail-closed admission for complete long-work units."""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

try:
    from scripts import work_memory
    from scripts.prevention_contract import (
        BudgetRoleId, canonical_bytes, require_id, sha256_bytes,
    )
    from scripts.prevention_journal import PreventionJournal
except ModuleNotFoundError:  # direct script execution
    import work_memory
    from prevention_contract import BudgetRoleId, canonical_bytes, require_id, sha256_bytes
    from prevention_journal import PreventionJournal


class BudgetError(ValueError):
    """Raised when a budget or capacity contract is incomplete."""


class ReservationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"
    RECONCILED = "RECONCILED"


class DurableFrontierTransport(Protocol):
    def query(self, request: Mapping[str, Any]) -> Mapping[str, Any]: ...


class OwnerBudgetProducer(Protocol):
    def profile_variables(
        self, owner_sequence_id: str, profile_name: str,
        executable_contract: Mapping[str, Any], parameters: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...

    def child_budget(
        self, executable_contract: Mapping[str, Any], parameters: Mapping[str, Any],
    ) -> "UnitBudget": ...

    def next_frontier(
        self, executable_contract: Mapping[str, Any], parameters: Mapping[str, Any],
    ) -> Sequence[Mapping[str, Any]]: ...


def _nonnegative(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BudgetError(f"invalid-{name}")
    return value


def _utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise BudgetError("invalid-budget-timestamp") from exc
    if parsed.tzinfo is None:
        raise BudgetError("invalid-budget-timestamp")
    return parsed.astimezone(UTC)


def _now_text(now: datetime) -> str:
    return now.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class UnitBudget:
    owner_sequence_id: str
    productive_milliseconds: int
    mandatory_role_milliseconds: Mapping[BudgetRoleId, int]
    adjudication_milliseconds: int
    materialization_milliseconds: int
    terminal_milliseconds: int
    retry_milliseconds: int
    token_units: int | None = None
    monetary_micros: int | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise BudgetError("unsupported-unit-budget-schema")
        require_id(self.owner_sequence_id, label="owner-sequence-id")
        normalized: dict[BudgetRoleId, int] = {}
        for role, value in self.mandatory_role_milliseconds.items():
            try:
                role_id = role if isinstance(role, BudgetRoleId) else BudgetRoleId(role)
            except ValueError as exc:
                raise BudgetError("unknown-budget-role") from exc
            normalized[role_id] = _nonnegative(value, f"role-{role_id.value.lower()}")
        if len(normalized) != len(self.mandatory_role_milliseconds):
            raise BudgetError("duplicate-budget-role")
        complete_roles = {
            BudgetRoleId.CORE,
            BudgetRoleId.INTERNAL_READINESS,
            BudgetRoleId.REQUIREMENTS_COVERAGE,
            BudgetRoleId.REQUIREMENTS_SATISFACTION,
        }
        if set(normalized) != complete_roles:
            raise BudgetError("incomplete-mandatory-role-budget")
        object.__setattr__(self, "mandatory_role_milliseconds", normalized)
        for name in (
            "productive_milliseconds", "adjudication_milliseconds",
            "materialization_milliseconds", "terminal_milliseconds", "retry_milliseconds",
        ):
            _nonnegative(getattr(self, name), name.replace("_", "-"))
        if (self.token_units is None) != (self.monetary_micros is None):
            raise BudgetError("partial-optional-budget-dimensions")
        if self.token_units is not None:
            _nonnegative(self.token_units, "token-units")
            _nonnegative(self.monetary_micros, "monetary-micros")

    @property
    def duration_milliseconds(self) -> int:
        return (
            self.productive_milliseconds
            + sum(self.mandatory_role_milliseconds.values())
            + self.adjudication_milliseconds
            + self.materialization_milliseconds
            + self.terminal_milliseconds
            + self.retry_milliseconds
        )

    def required_vector(self) -> dict[str, int]:
        result = {"duration_milliseconds": self.duration_milliseconds}
        if self.token_units is not None:
            result.update(token_units=self.token_units, monetary_micros=self.monetary_micros)
        return result

    def canonical_json(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "owner_sequence_id": self.owner_sequence_id,
            "productive_milliseconds": self.productive_milliseconds,
            "mandatory_role_milliseconds": {
                role.value: value
                for role, value in sorted(
                    self.mandatory_role_milliseconds.items(), key=lambda item: item[0].value
                )
            },
            "adjudication_milliseconds": self.adjudication_milliseconds,
            "materialization_milliseconds": self.materialization_milliseconds,
            "terminal_milliseconds": self.terminal_milliseconds,
            "retry_milliseconds": self.retry_milliseconds,
            "token_units": self.token_units,
            "monetary_micros": self.monetary_micros,
        }

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> "UnitBudget":
        required = {
            "schema_version", "owner_sequence_id", "productive_milliseconds",
            "mandatory_role_milliseconds", "adjudication_milliseconds",
            "materialization_milliseconds", "terminal_milliseconds",
            "retry_milliseconds",
        }
        optional = {"duration_milliseconds", "token_units", "monetary_micros", "derivation"}
        if not isinstance(value, Mapping) or not required <= set(value) or set(value) - required - optional:
            raise BudgetError("invalid-unit-budget-fields")
        budget = cls(
            schema_version=value["schema_version"],
            owner_sequence_id=value["owner_sequence_id"],
            productive_milliseconds=value["productive_milliseconds"],
            mandatory_role_milliseconds=value["mandatory_role_milliseconds"],
            adjudication_milliseconds=value["adjudication_milliseconds"],
            materialization_milliseconds=value["materialization_milliseconds"],
            terminal_milliseconds=value["terminal_milliseconds"],
            retry_milliseconds=value["retry_milliseconds"],
            token_units=value.get("token_units"),
            monetary_micros=value.get("monetary_micros"),
        )
        declared = value.get("duration_milliseconds")
        if declared is not None and declared != budget.duration_milliseconds:
            raise BudgetError("unit-budget-duration-mismatch")
        return budget


def _profile_name(owner_sequence_id: str, parameters: Mapping[str, Any]) -> str:
    command = parameters.get("command")
    if owner_sequence_id == "commit-push-main":
        mode = parameters.get("mode")
        if isinstance(mode, str) and mode:
            return mode
        if parameters.get("isolated_reconcile_remote") is True:
            return "isolated-reconcile-and-resume"
        if parameters.get("isolated_integrate_remote") is True:
            return "isolated-integrate-and-resume"
        if parameters.get("integrate_remote") is True:
            return "integrate-remote-and-resume"
        if "resume_commit" in parameters:
            return "resume-push"
        return "publish" if parameters.get("execute") is True else "dry-run"
    if owner_sequence_id == "convergence-state-review-cycle":
        if command in {"dry-run", "apply"}:
            return str(command)
        return "dry-run" if parameters.get("dry_run") is True else "apply"
    if isinstance(command, str) and command:
        return command
    if owner_sequence_id == "discovery-bootstrap":
        return "start"
    raise BudgetError(f"owner-budget-profile-unresolved:{owner_sequence_id}")


def _profile_duration_tasks(
    owner_sequence_id: str,
    profile_name: str,
    profile: Mapping[str, Any],
    *,
    variables: Mapping[str, Any] | None,
) -> int:
    if "productive_task_count" in profile:
        return _nonnegative(profile["productive_task_count"], "productive-task-count")
    variables = variables or {}
    if owner_sequence_id == "convergence-state-review-cycle" and profile_name == "apply":
        operations = _nonnegative(variables.get("M"), "operation-count")
        if operations == 0:
            raise BudgetError("zero-operation-count")
        return operations + 2
    if owner_sequence_id == "discovery-candidate-reconciliation":
        if profile_name == "execute":
            count = _nonnegative(variables.get("N"), "candidate-count")
            promote = _nonnegative(variables.get("P"), "promote-count")
            if promote > count:
                raise BudgetError("promote-count-exceeds-candidate-count")
            return 2 + count + 15 * promote
        if profile_name in {"execute-rolling", "drive"}:
            attempts = variables.get("attempts")
            if not isinstance(attempts, Sequence) or isinstance(attempts, (str, bytes)):
                raise BudgetError("attempt-frontier-required")
            if not 1 <= len(attempts) <= 6:
                raise BudgetError("attempt-frontier-cardinality")
            total = 0
            for item in attempts:
                if not isinstance(item, Mapping):
                    raise BudgetError("invalid-attempt-frontier-item")
                count = _nonnegative(item.get("N"), "candidate-count")
                promote = _nonnegative(item.get("P"), "promote-count")
                if promote > count:
                    raise BudgetError("promote-count-exceeds-candidate-count")
                total += 4 + count + 15 * promote
            return total + (8 if profile_name == "drive" else 0)
    raise BudgetError(f"owner-budget-variables-unresolved:{owner_sequence_id}:{profile_name}")


def _read_json_object(path_value: Any, label: str) -> Mapping[str, Any]:
    path = Path(str(path_value))
    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise BudgetError(f"{label}-materialized-file-invalid")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BudgetError(f"{label}-materialized-json-invalid") from exc
    if not isinstance(value, Mapping):
        raise BudgetError(f"{label}-materialized-object-required")
    return value


def _manifest_counts(value: Any) -> tuple[int, int]:
    rows = value.get("candidates") if isinstance(value, Mapping) else value
    if not isinstance(rows, list):
        raise BudgetError("candidate-manifest-list-required")
    if any(not isinstance(row, Mapping) for row in rows):
        raise BudgetError("candidate-manifest-row-invalid")
    promote = sum(row.get("disposition") == "promote" for row in rows)
    return len(rows), promote


def _child_parameter_map(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if not isinstance(value, list):
        raise BudgetError("child-parameters-invalid")
    result: dict[str, Any] = {}
    for row in value:
        if not isinstance(row, Mapping) or set(row) != {"name", "value"}:
            raise BudgetError("child-parameter-row-invalid")
        name = row["name"]
        raw_value = row["value"]
        if not isinstance(name, str) or not name or name in result:
            raise BudgetError("child-parameter-name-invalid")
        if isinstance(raw_value, Mapping) and set(raw_value) == {"tag", "value"}:
            raw_value = raw_value["value"]
        result[name] = raw_value
    return result


class SourceOwnerBudgetProducer:
    """Finite source-owned producers; no budget/count field is accepted from callers."""

    def __init__(
        self, *, executable_contracts: Mapping[str, Mapping[str, Any]] | None = None,
        frontier_transport: DurableFrontierTransport | None = None,
    ):
        self.executable_contracts = (
            dict(executable_contracts) if executable_contracts is not None else None
        )
        self.frontier_transport = frontier_transport

    def profile_variables(
        self, owner_sequence_id: str, profile_name: str,
        executable_contract: Mapping[str, Any], parameters: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if owner_sequence_id == "convergence-state-review-cycle" and profile_name == "apply":
            request = parameters.get("request")
            if not isinstance(request, Mapping):
                request = _read_json_object(parameters.get("request_file"), "review-request")
            operations = request.get("operations")
            if not isinstance(operations, list) or not operations:
                raise BudgetError("review-request-operations-invalid")
            return {"M": len(operations)}
        if owner_sequence_id == "discovery-candidate-reconciliation":
            if profile_name == "execute":
                manifest = _read_json_object(parameters.get("manifest"), "candidate-manifest")
                count, promote = _manifest_counts(manifest)
                return {"N": count, "P": promote}
            if profile_name in {"execute-rolling", "drive"}:
                baseline = _read_json_object(parameters.get("baseline"), "rolling-baseline")
                count, promote = _manifest_counts(baseline)
                return {"attempts": [{"N": count, "P": promote}]}
        raise BudgetError(
            f"owner-budget-source-profile-unavailable:{owner_sequence_id}:{profile_name}"
        )

    def child_budget(
        self, executable_contract: Mapping[str, Any], parameters: Mapping[str, Any],
    ) -> UnitBudget:
        child = parameters.get("child_intent")
        if not isinstance(child, Mapping):
            child = _read_json_object(parameters.get("child_intent_file"), "child-intent")
        required = {
            "child_owner_sequence_id", "child_contract_sha256", "child_intent_id",
            "child_parameters", "guard_receipt_id",
        }
        if set(child) != required:
            raise BudgetError("child-intent-fields-invalid")
        contracts = self.executable_contracts
        if contracts is None:
            try:
                from scripts import prevention_registry
            except ModuleNotFoundError:
                import prevention_registry
            contracts = {
                row["sequence_id"]: row["executable_contract"]
                for row in prevention_registry.load_typed_registry()[0]
                if row.get("executable_contract") is not None
            }
        owner_id = child["child_owner_sequence_id"]
        contract = contracts.get(owner_id)
        if not isinstance(contract, Mapping):
            raise BudgetError("child-owner-contract-unavailable")
        if contract.get("owner_contract_sha256") != child["child_contract_sha256"]:
            raise BudgetError("child-owner-contract-hash-mismatch")
        return derive_owner_unit_budget(
            contract, _child_parameter_map(child["child_parameters"]),
            budget_producer=self,
        )

    def next_frontier(
        self, executable_contract: Mapping[str, Any], parameters: Mapping[str, Any],
    ) -> Sequence[Mapping[str, Any]]:
        mode = parameters.get("mode")
        cap = executable_contract["budget_contract"]["atomic_task_cap_milliseconds"]
        if mode not in {
            "start-from-spec", "create-program", "resume-program", "validate-fresh",
        }:
            raise BudgetError("greenfield-frontier-mode-invalid")
        if self.frontier_transport is None:
            raise BudgetError("greenfield-durable-frontier-unavailable")
        request = {
            "owner_sequence_id": "greenfield-full-drive",
            "owner_contract_sha256": executable_contract["owner_contract_sha256"],
            "mode": mode,
            "spec": parameters.get("spec"),
            "program_drive_id": parameters.get("program_drive_id"),
            "decomposition_task_id": parameters.get("decomposition_task_id"),
            "decomposition_run_id": parameters.get("decomposition_run_id"),
            "expected_spec_hash": parameters.get("expected_spec_hash"),
        }
        capture = self.frontier_transport.query(request)
        expected = {"ownership", "source_state_sha256", "program_counters", "tasks"}
        if not isinstance(capture, Mapping) or set(capture) != expected:
            raise BudgetError("greenfield-frontier-capture-fields-invalid")
        if capture.get("ownership") != request:
            raise BudgetError("greenfield-frontier-ownership-mismatch")
        source_hash = capture.get("source_state_sha256")
        if not isinstance(source_hash, str) or len(source_hash) != 64:
            raise BudgetError("greenfield-frontier-source-hash-invalid")
        counters = capture.get("program_counters")
        counter_fields = {
            "feature_count": "maximum_features",
            "validation_round": "maximum_validation_rounds",
            "distinct_fatal_defects_in_round":
                "maximum_distinct_fatal_defects_per_round",
            "validation_fix_chain_count": "maximum_validation_fix_chains",
        }
        if not isinstance(counters, Mapping) or set(counters) != set(counter_fields):
            raise BudgetError("greenfield-program-counters-invalid")
        budget_policy = executable_contract["budget_contract"].get("contract")
        if not isinstance(budget_policy, Mapping):
            raise BudgetError("greenfield-budget-policy-invalid")
        for field, cap_name in counter_fields.items():
            value = counters[field]
            maximum = budget_policy.get(cap_name)
            if (
                isinstance(value, bool) or not isinstance(value, int)
                or isinstance(maximum, bool) or not isinstance(maximum, int)
                or value < 0 or value > maximum
            ):
                raise BudgetError(f"greenfield-program-cap-exceeded:{field}")
        tasks = capture.get("tasks")
        if not isinstance(tasks, list) or not 1 <= len(tasks) <= 20:
            raise BudgetError("greenfield-frontier-cardinality")
        ids: set[str] = set()
        task_counter_fields = {
            "FEATURE": "feature_count",
            "VALIDATION_ROUND": "validation_round",
            "FATAL_DEFECT": "distinct_fatal_defects_in_round",
            "VALIDATION_FIX_CHAIN": "validation_fix_chain_count",
            "PROGRAM_TERMINAL": None,
        }
        frontier_increments = {field: 0 for field in counter_fields}
        result = []
        for task in tasks:
            if not isinstance(task, Mapping) or set(task) != {"task_id", "task_kind"}:
                raise BudgetError("greenfield-frontier-task-fields-invalid")
            task_id = task["task_id"]
            if not isinstance(task_id, str) or not task_id or task_id in ids:
                raise BudgetError("greenfield-frontier-task-identity-invalid")
            task_kind = task["task_kind"]
            if task_kind not in task_counter_fields:
                raise BudgetError("greenfield-frontier-task-kind-invalid")
            counter_field = task_counter_fields[task_kind]
            if counter_field is not None:
                frontier_increments[counter_field] += 1
            component_floor = 1_000
            owner_component_count = 8
            if cap <= component_floor * owner_component_count:
                raise BudgetError("greenfield-owner-budget-cap-invalid")
            budget = UnitBudget(
                owner_sequence_id="greenfield-full-drive",
                productive_milliseconds=cap - component_floor * owner_component_count,
                mandatory_role_milliseconds={
                    role: component_floor for role in (
                        BudgetRoleId.CORE,
                        BudgetRoleId.INTERNAL_READINESS,
                        BudgetRoleId.REQUIREMENTS_COVERAGE,
                        BudgetRoleId.REQUIREMENTS_SATISFACTION,
                    )
                },
                adjudication_milliseconds=component_floor,
                materialization_milliseconds=component_floor,
                terminal_milliseconds=component_floor,
                retry_milliseconds=component_floor,
            )
            ids.add(task_id)
            result.append({"task_id": task_id, "unit_budget": budget.canonical_json()})
        for field, increment in frontier_increments.items():
            maximum = budget_policy[counter_fields[field]]
            if counters[field] + increment > maximum:
                raise BudgetError(f"greenfield-program-cap-exceeded:{field}")
        return result


def derive_owner_unit_budget(
    executable_contract: Mapping[str, Any],
    parameters: Mapping[str, Any],
    *,
    budget_producer: OwnerBudgetProducer | None = None,
) -> UnitBudget:
    """Derive the complete owner budget; callers cannot supply any budget component."""
    owner_sequence_id = str(executable_contract.get("owner_sequence_id", ""))
    budget_contract = executable_contract.get("budget_contract")
    if not isinstance(budget_contract, Mapping):
        raise BudgetError("owner-budget-contract-unavailable")
    if budget_contract.get("owner_sequence_id") != owner_sequence_id:
        raise BudgetError("owner-budget-contract-identity-mismatch")
    kind = budget_contract.get("kind")
    raw = budget_contract.get("contract")
    if not isinstance(raw, Mapping):
        raise BudgetError("owner-budget-contract-invalid")
    if kind == "FIXED_UNIT":
        return UnitBudget.from_json(raw)
    if kind == "CHILD_COMPOSITION":
        if budget_producer is None:
            raise BudgetError("owner-budget-durable-child-producer-unavailable")
        child = budget_producer.child_budget(executable_contract, parameters)
        return UnitBudget(
            owner_sequence_id=owner_sequence_id,
            productive_milliseconds=(
                _nonnegative(raw.get("parent_productive_milliseconds"), "parent-productive-milliseconds")
                + child.duration_milliseconds
            ),
            mandatory_role_milliseconds=raw.get("mandatory_role_milliseconds", {}),
            adjudication_milliseconds=raw.get("adjudication_milliseconds"),
            materialization_milliseconds=raw.get("materialization_milliseconds"),
            terminal_milliseconds=raw.get("terminal_milliseconds"),
            retry_milliseconds=0,
        )
    if kind == "ATOMIC_FRONTIER":
        if budget_producer is None:
            raise BudgetError("owner-budget-durable-frontier-producer-unavailable")
        frontier = budget_producer.next_frontier(executable_contract, parameters)
        task_budgets = [UnitBudget.from_json(item.get("unit_budget", {})) for item in frontier]
        if not task_budgets:
            raise BudgetError("owner-budget-empty-frontier")
        optional_dimensions = {
            (budget.token_units is not None, budget.monetary_micros is not None)
            for budget in task_budgets
        }
        if len(optional_dimensions) != 1:
            raise BudgetError("frontier-optional-budget-dimensions-mismatch")
        return UnitBudget(
            owner_sequence_id=owner_sequence_id,
            productive_milliseconds=sum(budget.productive_milliseconds for budget in task_budgets),
            mandatory_role_milliseconds={
                role: sum(budget.mandatory_role_milliseconds[role] for budget in task_budgets)
                for role in (
                    BudgetRoleId.CORE,
                    BudgetRoleId.INTERNAL_READINESS,
                    BudgetRoleId.REQUIREMENTS_COVERAGE,
                    BudgetRoleId.REQUIREMENTS_SATISFACTION,
                )
            },
            adjudication_milliseconds=sum(budget.adjudication_milliseconds for budget in task_budgets),
            materialization_milliseconds=sum(budget.materialization_milliseconds for budget in task_budgets),
            terminal_milliseconds=sum(budget.terminal_milliseconds for budget in task_budgets),
            retry_milliseconds=sum(budget.retry_milliseconds for budget in task_budgets),
            token_units=(
                sum(budget.token_units or 0 for budget in task_budgets)
                if task_budgets[0].token_units is not None else None
            ),
            monetary_micros=(
                sum(budget.monetary_micros or 0 for budget in task_budgets)
                if task_budgets[0].monetary_micros is not None else None
            ),
        )
    if kind != "PROFILED_PROGRESSIVE":
        raise BudgetError(f"unsupported-owner-budget-kind:{kind}")
    profile_name = _profile_name(owner_sequence_id, parameters)
    profiles = raw.get("mode_profiles", raw.get("command_profiles"))
    if not isinstance(profiles, Mapping) or not isinstance(profiles.get(profile_name), Mapping):
        raise BudgetError(f"owner-budget-profile-unavailable:{owner_sequence_id}:{profile_name}")
    profile = profiles[profile_name]
    variables = None
    if "productive_task_count" not in profile:
        if budget_producer is None:
            raise BudgetError("owner-budget-durable-profile-producer-unavailable")
        variables = budget_producer.profile_variables(
            owner_sequence_id, profile_name, executable_contract, parameters
        )
    cap = _nonnegative(raw.get("atomic_task_cap_milliseconds"), "atomic-task-cap-milliseconds")
    if cap != 3_600_000:
        raise BudgetError("atomic-task-cap-drift")
    productive_tasks = _profile_duration_tasks(
        owner_sequence_id, profile_name, profile,
        variables=variables,
    )
    budget = UnitBudget(
        owner_sequence_id=owner_sequence_id,
        productive_milliseconds=productive_tasks * cap,
        mandatory_role_milliseconds=raw.get("mandatory_role_milliseconds", {}),
        adjudication_milliseconds=raw.get("adjudication_milliseconds"),
        materialization_milliseconds=raw.get("materialization_milliseconds"),
        terminal_milliseconds=raw.get("terminal_milliseconds"),
        retry_milliseconds=0,
    )
    declared = profile.get("duration_milliseconds")
    if declared is not None and declared != budget.duration_milliseconds:
        raise BudgetError("profile-duration-mismatch")
    return budget


@dataclass(frozen=True)
class BudgetReservation:
    reservation_id: str
    task_id: str
    run_id: str
    owner_sequence_id: str
    required_vector: Mapping[str, int]
    remaining_vector_before: Mapping[str, int]
    remaining_vector_after: Mapping[str, int]
    lease_started_at_utc: str
    lease_expires_at_utc: str
    status: ReservationStatus
    version: int

    def canonical_json(self) -> dict[str, Any]:
        return {
            "reservation_id": self.reservation_id,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "owner_sequence_id": self.owner_sequence_id,
            "required_vector": dict(self.required_vector),
            "remaining_vector_before": dict(self.remaining_vector_before),
            "remaining_vector_after": dict(self.remaining_vector_after),
            "lease_started_at_utc": self.lease_started_at_utc,
            "lease_expires_at_utc": self.lease_expires_at_utc,
            "status": self.status.value,
            "version": self.version,
        }

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> "BudgetReservation":
        return cls(
            reservation_id=str(value["reservation_id"]),
            task_id=str(value["task_id"]),
            run_id=str(value["run_id"]),
            owner_sequence_id=str(value["owner_sequence_id"]),
            required_vector=dict(value["required_vector"]),
            remaining_vector_before=dict(value["remaining_vector_before"]),
            remaining_vector_after=dict(value["remaining_vector_after"]),
            lease_started_at_utc=str(value["lease_started_at_utc"]),
            lease_expires_at_utc=str(value["lease_expires_at_utc"]),
            status=ReservationStatus(value["status"]),
            version=int(value["version"]),
        )


class BudgetAuthority:
    """One process-safe admission authority persisted inside the run's prevention folder."""

    def __init__(
        self,
        journal: PreventionJournal,
        capacity: Mapping[str, int],
        *,
        lease_milliseconds: int = 300_000,
    ):
        self.journal = journal
        self.capacity = {name: _nonnegative(value, f"capacity-{name}") for name, value in capacity.items()}
        if "duration_milliseconds" not in self.capacity:
            raise BudgetError("missing-duration-capacity")
        optional = {"token_units", "monetary_micros"} & set(self.capacity)
        if optional not in (set(), {"token_units", "monetary_micros"}):
            raise BudgetError("partial-optional-capacity-dimensions")
        self.lease_milliseconds = _nonnegative(lease_milliseconds, "lease-milliseconds")
        if self.lease_milliseconds == 0:
            raise BudgetError("zero-lease")
        self.state_path = journal.prevention_dir / "budget-reservations.json"
        self._lock = threading.RLock()

    def _load(self) -> tuple[int, list[BudgetReservation]]:
        if not self.state_path.is_file():
            return 0, []
        value = json.loads(self.state_path.read_text(encoding="utf-8"))
        if set(value) != {"schema_version", "version", "reservations"} or value["schema_version"] != 1:
            raise BudgetError("invalid-budget-state")
        return int(value["version"]), [BudgetReservation.from_json(row) for row in value["reservations"]]

    def _save(self, version: int, reservations: list[BudgetReservation]) -> None:
        work_memory._atomic_write(self.state_path, work_memory.canonical_bytes({
            "schema_version": 1,
            "version": version,
            "reservations": [item.canonical_json() for item in reservations],
        }))

    def _available(self, reservations: list[BudgetReservation], now: datetime) -> dict[str, int]:
        active = [
            item for item in reservations
            if item.status == ReservationStatus.ACTIVE and _utc(item.lease_expires_at_utc) > now
        ]
        return {
            dimension: total - sum(item.required_vector.get(dimension, 0) for item in active)
            for dimension, total in self.capacity.items()
        }

    def admit(self, budget: UnitBudget, *, now: datetime | None = None) -> BudgetReservation | None:
        if budget.owner_sequence_id == "":
            raise BudgetError("missing-owner-sequence-id")
        required = budget.required_vector()
        if set(required) != set(self.capacity):
            raise BudgetError("budget-capacity-dimension-mismatch")
        now = (now or datetime.now(UTC)).astimezone(UTC)
        identity = (
            self.journal.ownership.task_id,
            self.journal.ownership.run_id,
            budget.owner_sequence_id,
        )
        with self._lock:
            version, reservations = self._load()
            existing = next((
                item for item in reservations
                if (item.task_id, item.run_id, item.owner_sequence_id) == identity
                and item.status == ReservationStatus.ACTIVE
                and _utc(item.lease_expires_at_utc) > now
            ), None)
            if existing is not None:
                if dict(existing.required_vector) != required:
                    raise BudgetError("active-reservation-budget-mismatch")
                return existing
            remaining = self._available(reservations, now)
            failed = sorted(name for name, value in required.items() if value > remaining[name])
            if failed:
                self.journal.append("budget_rejected", {
                    "owner_sequence_id": budget.owner_sequence_id,
                    "unit_budget": budget.canonical_json(),
                    "required_vector": required,
                    "remaining_vector": remaining,
                    "failed_dimensions": failed,
                    "reason_code": "INSUFFICIENT_COMPLETE_UNIT_CAPACITY",
                })
                return None
            expires = now + timedelta(milliseconds=self.lease_milliseconds)
            reservation = BudgetReservation(
                reservation_id=str(uuid.uuid4()),
                task_id=identity[0],
                run_id=identity[1],
                owner_sequence_id=identity[2],
                required_vector=required,
                remaining_vector_before=remaining,
                remaining_vector_after={name: remaining[name] - value for name, value in required.items()},
                lease_started_at_utc=_now_text(now),
                lease_expires_at_utc=_now_text(expires),
                status=ReservationStatus.ACTIVE,
                version=version + 1,
            )
            self._save(version + 1, [*reservations, reservation])
            self.journal.append("budget_admitted", {
                "reservation_id": reservation.reservation_id,
                "owner_sequence_id": budget.owner_sequence_id,
                "unit_budget": budget.canonical_json(),
                "reserved_vector": required,
                "remaining_vector_before": remaining,
                "lease_expires_at_utc": reservation.lease_expires_at_utc,
            })
            return reservation

    def release(self, reservation_id: str) -> BudgetReservation:
        with self._lock:
            version, reservations = self._load()
            match = next((item for item in reservations if item.reservation_id == reservation_id), None)
            if match is None:
                raise BudgetError("reservation-not-found")
            if match.status == ReservationStatus.RELEASED:
                return match
            if match.status != ReservationStatus.ACTIVE:
                raise BudgetError("reservation-not-active")
            released = BudgetReservation(**{
                **match.__dict__, "status": ReservationStatus.RELEASED, "version": version + 1,
            })
            updated = [released if item.reservation_id == reservation_id else item for item in reservations]
            self._save(version + 1, updated)
            return released

    def reconcile_expired(self, *, now: datetime | None = None) -> list[BudgetReservation]:
        now = (now or datetime.now(UTC)).astimezone(UTC)
        with self._lock:
            version, reservations = self._load()
            changed: list[BudgetReservation] = []
            updated: list[BudgetReservation] = []
            for item in reservations:
                if item.status == ReservationStatus.ACTIVE and _utc(item.lease_expires_at_utc) <= now:
                    version += 1
                    item = BudgetReservation(**{
                        **item.__dict__, "status": ReservationStatus.RECONCILED, "version": version,
                    })
                    changed.append(item)
                updated.append(item)
            if changed:
                self._save(version, updated)
            return changed
