from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
import json

import pytest

from scripts import prevention_budget, prevention_contract, prevention_journal, prevention_registry


TASK_ID = "task-123"
RUN_ID = "4f642f31-f326-4b2c-92e4-753826ecad9f"


def journal(tmp_path: Path) -> prevention_journal.PreventionJournal:
    return prevention_journal.PreventionJournal(
        tmp_path / "run",
        prevention_journal.JournalOwnership(
            task_id=TASK_ID,
            run_id=RUN_ID,
            branch_ref=f"task/{TASK_ID}",
            worktree_id="a" * 64,
        ),
    )


def full_research_budget(*, owner: str = "research-playbook") -> prevention_budget.UnitBudget:
    return prevention_budget.UnitBudget(
        owner_sequence_id=owner,
        productive_milliseconds=10,
        mandatory_role_milliseconds={
            prevention_contract.BudgetRoleId.CORE: 10,
            prevention_contract.BudgetRoleId.INTERNAL_READINESS: 10,
            prevention_contract.BudgetRoleId.REQUIREMENTS_COVERAGE: 10,
            prevention_contract.BudgetRoleId.REQUIREMENTS_SATISFACTION: 10,
        },
        adjudication_milliseconds=10,
        materialization_milliseconds=10,
        terminal_milliseconds=10,
        retry_milliseconds=10,
    )


def greenfield_frontier_task(*, task_id: str) -> dict[str, object]:
    return {"task_id": task_id, "task_kind": "FEATURE"}


def test_full_research_unit_sum_and_exact_boundary(tmp_path: Path):
    budget = full_research_budget()
    authority = prevention_budget.BudgetAuthority(
        journal(tmp_path), {"duration_milliseconds": 90}
    )

    reservation = authority.admit(budget)

    assert budget.duration_milliseconds == 90
    assert reservation is not None
    assert reservation.remaining_vector_after == {"duration_milliseconds": 0}


def test_one_unit_below_rejects_before_admission(tmp_path: Path):
    governed_journal = journal(tmp_path)
    authority = prevention_budget.BudgetAuthority(
        governed_journal, {"duration_milliseconds": 89}
    )

    assert authority.admit(full_research_budget()) is None

    events, _ = governed_journal.replay()
    assert [event["event_type"] for event in events] == ["budget_rejected"]
    assert events[0]["failed_dimensions"] == ["duration_milliseconds"]
    assert not authority.state_path.exists()


def test_optional_dimensions_are_all_supported_or_all_absent(tmp_path: Path):
    with pytest.raises(prevention_budget.BudgetError, match="partial-optional-budget"):
        prevention_budget.UnitBudget(
            **{**full_research_budget().__dict__, "token_units": 5}
        )
    with pytest.raises(prevention_budget.BudgetError, match="partial-optional-capacity"):
        prevention_budget.BudgetAuthority(
            journal(tmp_path), {"duration_milliseconds": 80, "token_units": 5}
        )


def test_concurrent_duplicate_admission_returns_one_reservation(tmp_path: Path):
    governed_journal = journal(tmp_path)
    authority = prevention_budget.BudgetAuthority(
        governed_journal, {"duration_milliseconds": 90}
    )
    budget = full_research_budget()

    with ThreadPoolExecutor(max_workers=2) as pool:
        reservations = list(pool.map(lambda _: authority.admit(budget), range(2)))

    assert reservations[0] is not None
    assert reservations[0].reservation_id == reservations[1].reservation_id
    events, _ = governed_journal.replay()
    assert [event["event_type"] for event in events] == ["budget_admitted"]


def test_release_is_idempotent_and_expiry_is_reconciled_after_restart(tmp_path: Path):
    governed_journal = journal(tmp_path)
    started = datetime(2026, 7, 17, 10, 0, tzinfo=UTC)
    authority = prevention_budget.BudgetAuthority(
        governed_journal, {"duration_milliseconds": 180}, lease_milliseconds=1_000
    )
    first = authority.admit(full_research_budget(), now=started)
    assert first is not None

    released = authority.release(first.reservation_id)
    assert authority.release(first.reservation_id) == released

    second = authority.admit(
        full_research_budget(owner="discovery-bootstrap"), now=started
    )
    assert second is not None
    restarted = prevention_budget.BudgetAuthority(
        governed_journal, {"duration_milliseconds": 180}, lease_milliseconds=1_000
    )
    reconciled = restarted.reconcile_expired(now=started + timedelta(seconds=2))

    assert [item.reservation_id for item in reconciled] == [second.reservation_id]
    replacement = restarted.admit(
        full_research_budget(owner="discovery-promotion-lifecycle"),
        now=started + timedelta(seconds=2),
    )
    assert replacement is not None


def _executable(owner_id: str):
    return next(
        row["executable_contract"] for row in prevention_registry.load_typed_registry()[0]
        if row["sequence_id"] == owner_id
    )


def test_dynamic_budget_rejects_without_durable_owner_producer():
    executable = _executable("convergence-state-review-cycle")
    with pytest.raises(prevention_budget.BudgetError, match="durable-profile-producer"):
        prevention_budget.derive_owner_unit_budget(
            executable, {"command": "apply"}
        )

    with pytest.raises(prevention_budget.BudgetError, match="durable-child-producer"):
        prevention_budget.derive_owner_unit_budget(
            _executable("convergence-checkpoint-run"), {}
        )
    with pytest.raises(prevention_budget.BudgetError, match="durable-frontier-producer"):
        prevention_budget.derive_owner_unit_budget(
            _executable("greenfield-full-drive"), {}
        )


def test_source_owner_budget_producer_derives_materialized_profile_counts(
    tmp_path: Path,
):
    producer = prevention_budget.SourceOwnerBudgetProducer()
    review = prevention_budget.derive_owner_unit_budget(
        _executable("convergence-state-review-cycle"),
        {"command": "apply", "request": {"operations": [{}, {}, {}]}},
        budget_producer=producer,
    )
    assert review.productive_milliseconds == 5 * 3_600_000
    assert review.duration_milliseconds == 12 * 3_600_000

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "candidates": [
            {"disposition": "promote"},
            {"disposition": "remain-discovery"},
        ]
    }), encoding="utf-8")
    execute = prevention_budget.derive_owner_unit_budget(
        _executable("discovery-candidate-reconciliation"),
        {"command": "execute", "manifest": str(manifest)},
        budget_producer=producer,
    )
    assert execute.productive_milliseconds == 19 * 3_600_000
    assert execute.duration_milliseconds == 26 * 3_600_000
    rolling = prevention_budget.derive_owner_unit_budget(
        _executable("discovery-candidate-reconciliation"),
        {"command": "execute-rolling", "baseline": str(manifest)},
        budget_producer=producer,
    )
    assert rolling.productive_milliseconds == 21 * 3_600_000


def test_child_composition_loads_exact_content_addressed_child_budget():
    child = _executable("claude-auth-token-refresh")
    producer = prevention_budget.SourceOwnerBudgetProducer(
        executable_contracts={"claude-auth-token-refresh": child}
    )
    budget = prevention_budget.derive_owner_unit_budget(
        _executable("convergence-checkpoint-run"),
        {
            "child_intent": {
                "child_owner_sequence_id": "claude-auth-token-refresh",
                "child_contract_sha256": child["owner_contract_sha256"],
                "child_intent_id": "child-1",
                "child_parameters": {},
                "guard_receipt_id": "guard-1",
            }
        },
        budget_producer=producer,
    )
    assert budget.duration_milliseconds == 16 * 3_600_000


def test_greenfield_frontier_is_source_owned_bounded_and_exact():
    contract = _executable("greenfield-full-drive")

    class Frontier:
        def __init__(self, tasks):
            self.tasks = tasks

        def query(self, request):
            return {
                "ownership": dict(request),
                "source_state_sha256": "a" * 64,
                "program_counters": {
                    "feature_count": 1,
                    "validation_round": 0,
                    "distinct_fatal_defects_in_round": 0,
                    "validation_fix_chain_count": 0,
                },
                "tasks": self.tasks,
            }

    initial = prevention_budget.derive_owner_unit_budget(
        contract,
        {"mode": "start-from-spec", "spec": "/tmp/spec.md"},
        budget_producer=prevention_budget.SourceOwnerBudgetProducer(
            frontier_transport=Frontier([greenfield_frontier_task(task_id="initial")])
        ),
    )
    assert initial.duration_milliseconds == 3_600_000
    assert initial.productive_milliseconds == 3_592_000
    assert initial.mandatory_role_milliseconds == {
        role: 1_000 for role in (
            prevention_contract.BudgetRoleId.CORE,
            prevention_contract.BudgetRoleId.INTERNAL_READINESS,
            prevention_contract.BudgetRoleId.REQUIREMENTS_COVERAGE,
            prevention_contract.BudgetRoleId.REQUIREMENTS_SATISFACTION,
        )
    }

    resumed = prevention_budget.derive_owner_unit_budget(
        contract,
        {
            "mode": "resume-program", "program_drive_id": "program-1",
            "decomposition_task_id": "task-1", "decomposition_run_id": "run-1",
            "expected_spec_hash": "b" * 64,
        },
        budget_producer=prevention_budget.SourceOwnerBudgetProducer(
            frontier_transport=Frontier([
                greenfield_frontier_task(task_id="feature-1"),
                greenfield_frontier_task(task_id="feature-2"),
            ])
        ),
    )
    assert resumed.productive_milliseconds == 7_184_000
    assert resumed.mandatory_role_milliseconds == {
        role: 2_000 for role in (
            prevention_contract.BudgetRoleId.CORE,
            prevention_contract.BudgetRoleId.INTERNAL_READINESS,
            prevention_contract.BudgetRoleId.REQUIREMENTS_COVERAGE,
            prevention_contract.BudgetRoleId.REQUIREMENTS_SATISFACTION,
        )
    }
    assert resumed.adjudication_milliseconds == 2_000
    assert resumed.materialization_milliseconds == 2_000
    assert resumed.terminal_milliseconds == 2_000
    assert resumed.retry_milliseconds == 2_000
    assert resumed.duration_milliseconds == 7_200_000


def test_greenfield_rejects_caller_unit_budget_or_unbounded_frontier_task():
    contract = _executable("greenfield-full-drive")

    class Frontier:
        def __init__(self, task):
            self.task = task

        def query(self, request):
            return {
                "ownership": dict(request),
                "source_state_sha256": "a" * 64,
                "program_counters": {
                    "feature_count": 1,
                    "validation_round": 0,
                    "distinct_fatal_defects_in_round": 0,
                    "validation_fix_chain_count": 0,
                },
                "tasks": [self.task],
            }

    caller_budget = {"productive_milliseconds": 1}
    with pytest.raises(prevention_budget.BudgetError, match="frontier-task-fields-invalid"):
        prevention_budget.derive_owner_unit_budget(
            contract, {"mode": "start-from-spec", "spec": "/tmp/spec.md"},
            budget_producer=prevention_budget.SourceOwnerBudgetProducer(
                frontier_transport=Frontier({
                    "task_id": "feature-1", "unit_budget": caller_budget,
                })
            ),
        )

    caller_duration = {
        "task_id": "feature-1", "task_kind": "FEATURE",
        "duration_milliseconds": 1,
    }
    with pytest.raises(prevention_budget.BudgetError, match="frontier-task-fields-invalid"):
        prevention_budget.derive_owner_unit_budget(
            contract, {"mode": "start-from-spec", "spec": "/tmp/spec.md"},
            budget_producer=prevention_budget.SourceOwnerBudgetProducer(
                frontier_transport=Frontier(caller_duration)
            ),
        )


@pytest.mark.parametrize(
    ("task_kind", "counter_field", "maximum"),
    [
        ("FEATURE", "feature_count", 20),
        ("VALIDATION_ROUND", "validation_round", 5),
        ("FATAL_DEFECT", "distinct_fatal_defects_in_round", 4),
        ("VALIDATION_FIX_CHAIN", "validation_fix_chain_count", 20),
    ],
)
def test_greenfield_frontier_cannot_advance_any_cumulative_counter_past_cap(
    task_kind: str, counter_field: str, maximum: int,
):
    contract = _executable("greenfield-full-drive")

    class Frontier:
        @staticmethod
        def query(request):
            counters = {
                "feature_count": 0,
                "validation_round": 0,
                "distinct_fatal_defects_in_round": 0,
                "validation_fix_chain_count": 0,
            }
            counters[counter_field] = maximum
            return {
                "ownership": dict(request),
                "source_state_sha256": "a" * 64,
                "program_counters": counters,
                "tasks": [{"task_id": "next", "task_kind": task_kind}],
            }

    with pytest.raises(
        prevention_budget.BudgetError,
        match=f"greenfield-program-cap-exceeded:{counter_field}",
    ):
        prevention_budget.derive_owner_unit_budget(
            contract,
            {"mode": "start-from-spec", "spec": "/tmp/spec.md"},
            budget_producer=prevention_budget.SourceOwnerBudgetProducer(
                frontier_transport=Frontier()
            ),
        )
