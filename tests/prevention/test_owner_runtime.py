from __future__ import annotations

import uuid
from copy import deepcopy
from pathlib import Path

import pytest

from scripts import prevention_adapters, prevention_contract, prevention_journal, prevention_owner_runtime
from scripts import prevention_registry


class _BindingProvider:
    def resolve(self, request):
        kind = (
            prevention_contract.BindingKind.APPROVAL if request.consumable
            else prevention_contract.BindingKind.SECRET
            if request.parameter_type == "SECRET_HANDLE"
            else prevention_contract.BindingKind.RESOURCE
            if request.parameter_type == "RESOURCE_KEY"
            else prevention_contract.BindingKind.REPOSITORY
        )
        execution_value = (
            str(Path(__file__).resolve().parents[2])
            if kind == prevention_contract.BindingKind.REPOSITORY
            and request.parameter_name == "repository_key"
            else request.key_or_resource_id
            if request.consumable or request.parameter_name == "remote_key"
            else f"resolved-{request.key_or_resource_id}"
        )
        fingerprint = prevention_contract.sha256_bytes(
            prevention_contract.canonical_bytes(execution_value)
        )
        receipt_id = "fixed-approval-receipt" if request.consumable else prevention_contract.sha256_bytes(
            prevention_contract.canonical_bytes({
                "scope": request.expected_scope_sha256,
                "key": request.key_or_resource_id,
            })
        )
        return prevention_adapters.BindingResolution(
            receipt=prevention_contract.BindingReceipt(
                receipt_id=receipt_id, binding_kind=kind,
                provider_id=request.provider_id,
                key_or_resource_id=request.key_or_resource_id,
                version_id=request.version_id or "v1",
                scope_sha256=request.expected_scope_sha256,
                value_fingerprint_sha256=fingerprint,
                consumable=request.consumable,
            ),
            execution_value=execution_value,
        )


class _ObservationTransport:
    def __init__(self, reconciliation="NOT_APPLIED", *, terminal_pass=True, on_query=None):
        self.reconciliation = reconciliation
        self.terminal_pass = terminal_pass
        self.on_query = on_query

    def query(self, request):
        if self.on_query is not None:
            self.on_query(request)
        ownership = {
            "effect_id": request["effect_id"],
            "owner_sequence_id": request["owner_sequence_id"],
            "preparation_artifact_sha256": request["preparation_artifact_sha256"],
        }
        now = prevention_owner_runtime.work_memory.utc_now()
        values = {
            probe: (
                "SATISFIED" if self.reconciliation == "ALREADY_APPLIED"
                else "CONFLICT" if self.reconciliation == "INDETERMINATE"
                else "ABSENT"
            )
            for probe in request["probe_ids"]
        }
        if request["provider_symbol"].endswith("_reconciliation"):
            return {
                "identity": "CONFLICT" if self.reconciliation == "INDETERMINATE" else "MATCH",
                "observed_at_utc": now, "ownership": ownership,
                "prestate": "MATCH" if self.reconciliation == "NOT_APPLIED" else "CHANGED",
                "probes": values,
                "receipt": "ABSENT" if self.reconciliation == "NOT_APPLIED" else "PRESENT",
                "source_evidence_sha256": request["source_evidence_sha256"],
                "work_state": "TERMINAL" if self.reconciliation == "ALREADY_APPLIED" else "DETACHED",
            }
        return {
            "identity": "MATCH", "observed_at_utc": now, "ownership": ownership,
            "prestate": "CHANGED",
            "probes": {
                probe: "SATISFIED" if self.terminal_pass else "ABSENT"
                for probe in request["probe_ids"]
            },
            "receipt": "PRESENT",
            "source_evidence_sha256": request["source_evidence_sha256"],
            "work_state": "TERMINAL",
        }


def _runtime(
    journal,
    *,
    observation_transport=None,
    **kwargs,
):
    return prevention_owner_runtime.OwnerRuntime.for_test(
        journal,
        observation_transport=observation_transport or _ObservationTransport(),
        **kwargs,
    )


def _journal(tmp_path: Path) -> prevention_journal.PreventionJournal:
    run_id = str(uuid.uuid4())
    ownership = prevention_journal.JournalOwnership(
        task_id="owner-runtime-test", run_id=run_id,
        branch_ref="task/owner-runtime-test", worktree_id="a" * 64,
    )
    return prevention_journal.PreventionJournal(tmp_path / "run", ownership)


def _intent(run_id: str) -> prevention_contract.ActionIntent:
    return prevention_contract.ActionIntent(
        intent_id=str(uuid.uuid4()), task_id="owner-runtime-test", run_id=run_id,
        requested_sequence_id="claude-auth-token-refresh",
        requested_implementation_id="b" * 64, compatibility_key="c" * 64,
        action_class=prevention_contract.ActionClass.BASH,
        parameters=(
            prevention_contract.TypedParameter(
                name="command", value=prevention_contract.ParameterValue(
                    prevention_contract.ParameterTag.ENUM, "status"
                ),
            ),
            prevention_contract.TypedParameter(
                name="container_key", value=prevention_contract.ParameterValue(
                    prevention_contract.ParameterTag.RESOURCE_KEY, "workflow-orch-local"
                ),
            ),
            prevention_contract.TypedParameter(
                name="vault_key", value=prevention_contract.ParameterValue(
                    prevention_contract.ParameterTag.RESOURCE_KEY, "workflow-orch-vault"
                ),
            ),
        ),
    )


def test_owner_runtime_persists_transitions_and_resume_does_not_repeat_effect(tmp_path: Path):
    journal = _journal(tmp_path)
    owner = next(
        row for row in prevention_registry.load_typed_registry()[0]
        if row["sequence_id"] == "claude-auth-token-refresh"
    )
    calls: list[tuple[str, ...]] = []

    def runner(argv):
        calls.append(tuple(argv))
        return prevention_owner_runtime.ExecutionResult(0, '{"ok":true}', "")

    runtime = _runtime(
        journal,
        runner=runner,
        observation_transport=_ObservationTransport(),
        binding_provider=_BindingProvider(),
    )
    intent = _intent(journal.ownership.run_id)
    first = runtime.run(intent, owner)
    resumed = runtime.run(intent, owner)

    assert first["status"] == resumed["status"] == "TERMINAL"
    assert first["observation_transport_kind"] == "TEST_TRANSPORT"
    assert "argv" not in first
    assert len(calls) == 1
    events, _ = journal.replay()
    assert [event["event_type"] for event in events] == [
        "transition_prepared", "owner_binding_recorded", "owner_binding_recorded",
        "effect_prepared", "effect_reconciled",
        "effect_execution_authorized", "effect_execution_started", "effect_committed",
        "owner_terminal",
    ]


def test_started_effect_fails_closed_without_repeating_unknown_external_effect(tmp_path: Path):
    journal = _journal(tmp_path)
    owner = next(
        row for row in prevention_registry.load_typed_registry()[0]
        if row["sequence_id"] == "claude-auth-token-refresh"
    )
    runtime = _runtime(
        journal, binding_provider=_BindingProvider(),
        observation_transport=_ObservationTransport("INDETERMINATE"),
    )
    intent = _intent(journal.ownership.run_id)
    _, state = runtime.prepare(intent, owner)
    path = runtime._effect_path(state["effect_id"])
    runtime._write_state(path, {**state, "status": "STARTED"})

    with pytest.raises(prevention_owner_runtime.OwnerRuntimeError, match="indeterminate"):
        runtime.run(intent, owner)
    events, _ = journal.replay()
    assert events[-1]["event_type"] == "effect_reconciled"
    assert events[-1]["reconciliation"] == "INDETERMINATE"


def test_consumable_provider_receipt_is_bound_once_before_mutation(tmp_path: Path):
    journal = _journal(tmp_path)
    owner = deepcopy(next(
        row for row in prevention_registry.load_typed_registry()[0]
        if row["sequence_id"] == "commit-push-main"
    ))
    owner["executable_contract"]["trusted_roots"]["runtime-temp"] = str(tmp_path)
    manifest = tmp_path / "manifest.json"
    manifest.write_text('["scripts/prevention_adapters.py"]', encoding="utf-8")

    def make_intent():
        return prevention_contract.ActionIntent(
            intent_id=str(uuid.uuid4()), task_id=journal.ownership.task_id,
            run_id=journal.ownership.run_id, requested_sequence_id="commit-push-main",
            requested_implementation_id="b" * 64, compatibility_key="c" * 64,
            action_class=prevention_contract.ActionClass.BASH,
            parameters=(
                prevention_contract.TypedParameter("mode", prevention_contract.ParameterValue(prevention_contract.ParameterTag.ENUM, "dry-run")),
                prevention_contract.TypedParameter("repository_key", prevention_contract.ParameterValue(prevention_contract.ParameterTag.RESOURCE_KEY, "memory-knowledge")),
                prevention_contract.TypedParameter("branch", prevention_contract.ParameterValue(prevention_contract.ParameterTag.STRING, "main")),
                prevention_contract.TypedParameter("remote_key", prevention_contract.ParameterValue(prevention_contract.ParameterTag.RESOURCE_KEY, "origin")),
                prevention_contract.TypedParameter("manifest_file", prevention_contract.ParameterValue(prevention_contract.ParameterTag.PATH, "runtime-temp/manifest.json")),
                prevention_contract.TypedParameter("authorization_receipt_id", prevention_contract.ParameterValue(prevention_contract.ParameterTag.UUID, str(uuid.uuid4()))),
            ),
        )

    calls = []
    runtime = _runtime(
        journal, binding_provider=_BindingProvider(),
        runner=lambda argv: calls.append(tuple(argv)) or prevention_owner_runtime.ExecutionResult(0, '{"ok":true}', ""),
        observation_transport=_ObservationTransport(),
    )
    first = runtime.run(make_intent(), owner)
    assert first["status"] == "TERMINAL"
    with pytest.raises(Exception, match="conflicting-authorization_receipt_consumed"):
        runtime.run(make_intent(), owner)
    events, _ = journal.replay()
    consumed = [
        event for event in events
        if event["event_type"] == "authorization_receipt_consumed"
    ]
    prepared = [event for event in events if event["event_type"] == "effect_prepared"]
    assert len(consumed) == len(prepared) == 1
    assert consumed[0]["effect_prepared_event_id"] == prepared[0]["event_id"]
    assert consumed[0]["recorded_at_utc"] == prepared[0]["recorded_at_utc"]
    assert len(calls) == 1


def test_provider_secret_value_is_ephemeral_across_state_artifacts_and_events(
    tmp_path: Path,
):
    journal = _journal(tmp_path)
    owner = next(
        row for row in prevention_registry.load_typed_registry()[0]
        if row["sequence_id"] == "greenfield-full-drive"
    )
    intent = prevention_contract.ActionIntent(
        intent_id=str(uuid.uuid4()),
        task_id=journal.ownership.task_id,
        run_id=journal.ownership.run_id,
        requested_sequence_id="greenfield-full-drive",
        requested_implementation_id="b" * 64,
        compatibility_key="c" * 64,
        action_class=prevention_contract.ActionClass.BASH,
        parameters=(
            prevention_contract.TypedParameter(
                "mode", prevention_contract.ParameterValue(
                    prevention_contract.ParameterTag.ENUM, "start-from-spec"
                )
            ),
            prevention_contract.TypedParameter(
                "repository_key", prevention_contract.ParameterValue(
                    prevention_contract.ParameterTag.RESOURCE_KEY, "repo"
                )
            ),
            prevention_contract.TypedParameter(
                "env_file", prevention_contract.ParameterValue(
                    prevention_contract.ParameterTag.SECRET_HANDLE,
                    {"provider_id": "secret-provider", "key_id": "env", "version_id": "v1"},
                )
            ),
            prevention_contract.TypedParameter(
                "keyvault_name", prevention_contract.ParameterValue(
                    prevention_contract.ParameterTag.STRING, "vault"
                )
            ),
            prevention_contract.TypedParameter(
                "spec_root_key", prevention_contract.ParameterValue(
                    prevention_contract.ParameterTag.ENUM, "memory-knowledge"
                )
            ),
            prevention_contract.TypedParameter(
                "spec", prevention_contract.ParameterValue(
                    prevention_contract.ParameterTag.PATH,
                    "tests/prevention/test_owner_runtime.py",
                )
            ),
        ),
    )
    state = _runtime(
        journal,
        runner=lambda argv: (
            pytest.fail("secret was not rendered ephemerally")
            if "resolved-env" not in argv
            else prevention_owner_runtime.ExecutionResult(0, '{"ok":true}', "")
        ),
        observation_transport=_ObservationTransport(),
        binding_provider=_BindingProvider(),
    ).run(intent, owner)

    assert state["status"] == "TERMINAL"
    durable_bytes = b"\n".join(
        path.read_bytes()
        for path in journal.prevention_dir.rglob("*")
        if path.is_file()
    )
    assert b"resolved-env" not in durable_bytes


def test_started_crash_reconciles_already_applied_without_second_execution(tmp_path: Path):
    journal = _journal(tmp_path)
    owner = next(
        row for row in prevention_registry.load_typed_registry()[0]
        if row["sequence_id"] == "claude-auth-token-refresh"
    )
    requested = _intent(journal.ownership.run_id)
    calls = []

    def crashing_runner(argv):
        calls.append(tuple(argv))
        raise RuntimeError("simulated-process-boundary-crash")

    first = _runtime(
        journal, runner=crashing_runner, binding_provider=_BindingProvider()
    )
    with pytest.raises(RuntimeError, match="simulated-process-boundary-crash"):
        first.run(requested, owner)

    recovered = _runtime(
        journal, runner=lambda _argv: pytest.fail("recovered effect must not execute"),
        binding_provider=_BindingProvider(),
        observation_transport=_ObservationTransport("ALREADY_APPLIED"),
    ).run(requested, owner)

    assert recovered["status"] == "TERMINAL"
    assert recovered["result_kind"] == "RECOVERED_RESULT"
    assert len(calls) == 1
    events, _ = journal.replay()
    assert [event["attempt_generation"] for event in events if event["event_type"] == "effect_execution_started"] == [1]


def test_journal_started_generation_overrides_stale_prepared_state(tmp_path: Path):
    journal = _journal(tmp_path)
    owner = next(
        row for row in prevention_registry.load_typed_registry()[0]
        if row["sequence_id"] == "claude-auth-token-refresh"
    )
    requested = _intent(journal.ownership.run_id)
    first = _runtime(
        journal,
        runner=lambda _argv: (_ for _ in ()).throw(RuntimeError("crash")),
        binding_provider=_BindingProvider(),
    )
    with pytest.raises(RuntimeError, match="crash"):
        first.run(requested, owner)

    _, crashed = first.prepare(requested, owner)
    first._write_state(first._effect_path(crashed["effect_id"]), {
        **crashed,
        "status": "PREPARED",
        "attempt_generation": 0,
    })

    recovered = _runtime(
        journal,
        runner=lambda _argv: pytest.fail("journal-started generation must not re-execute"),
        binding_provider=_BindingProvider(),
        observation_transport=_ObservationTransport("ALREADY_APPLIED"),
    ).run(requested, owner)

    assert recovered["status"] == "TERMINAL"
    assert recovered["attempt_generation"] == 1
    events, _ = journal.replay()
    assert len([
        event for event in events if event["event_type"] == "effect_execution_started"
    ]) == 1


def test_not_applied_after_crash_authorizes_exactly_next_generation(tmp_path: Path):
    journal = _journal(tmp_path)
    owner = next(
        row for row in prevention_registry.load_typed_registry()[0]
        if row["sequence_id"] == "claude-auth-token-refresh"
    )
    requested = _intent(journal.ownership.run_id)
    with pytest.raises(RuntimeError, match="crash"):
        _runtime(
            journal, runner=lambda _argv: (_ for _ in ()).throw(RuntimeError("crash")),
            binding_provider=_BindingProvider(),
        ).run(requested, owner)

    calls = []
    completed = _runtime(
        journal,
        runner=lambda argv: calls.append(tuple(argv)) or prevention_owner_runtime.ExecutionResult(0, '{"ok":true}', ""),
        binding_provider=_BindingProvider(),
        observation_transport=_ObservationTransport(),
    ).run(requested, owner)

    assert completed["status"] == "TERMINAL"
    assert len(calls) == 1
    events, _ = journal.replay()
    assert [event["attempt_generation"] for event in events if event["event_type"] == "effect_execution_started"] == [1, 2]
    assert [event["prior_generation"] for event in events if event["event_type"] == "effect_execution_authorized"] == [0, 1]


def test_reconciliation_event_replay_does_not_reobserve_same_generation(tmp_path: Path):
    journal = _journal(tmp_path)
    owner = next(
        row for row in prevention_registry.load_typed_registry()[0]
        if row["sequence_id"] == "claude-auth-token-refresh"
    )
    requested = _intent(journal.ownership.run_id)
    calls = []
    runtime = _runtime(
        journal, binding_provider=_BindingProvider(),
        observation_transport=_ObservationTransport(
            on_query=lambda request: calls.append("observed")
            if request["provider_symbol"].endswith("_reconciliation") else None
        ),
    )
    plan, state = runtime.prepare(requested, owner)
    started_state = {**state, "status": "STARTED", "attempt_generation": 1}
    first, updated = runtime._reconcile_generation(plan, started_state)
    second, replayed = runtime._reconcile_generation(plan, started_state)

    assert first == second
    assert updated["last_reconciliation_event_id"] == replayed["last_reconciliation_event_id"]
    assert calls == ["observed"]


@pytest.mark.parametrize(
    ("stdout", "failure"),
    [
        ("not-json", "terminal-envelope-invalid-json"),
        ('{"ok":false}', "terminal-envelope-not-ok"),
        ('{"ok":true,"finalOk":false}', "terminal-envelope-semantic-failure"),
    ],
)
def test_zero_exit_without_valid_semantic_envelope_never_terminalizes(
    tmp_path: Path, stdout: str, failure: str,
):
    journal = _journal(tmp_path)
    owner = next(
        row for row in prevention_registry.load_typed_registry()[0]
        if row["sequence_id"] == "claude-auth-token-refresh"
    )
    requested = _intent(journal.ownership.run_id)
    calls = []
    runtime = _runtime(
        journal,
        runner=lambda argv: calls.append(tuple(argv))
        or prevention_owner_runtime.ExecutionResult(0, stdout, ""),
        binding_provider=_BindingProvider(),
        observation_transport=_ObservationTransport(),
    )

    with pytest.raises(prevention_owner_runtime.OwnerRuntimeError, match=failure):
        runtime.run(requested, owner)
    with pytest.raises(prevention_owner_runtime.OwnerRuntimeError, match=failure):
        _runtime(
            journal,
            runner=lambda _argv: pytest.fail("committed result must be replayed"),
            binding_provider=_BindingProvider(),
        observation_transport=_ObservationTransport(),
        ).run(requested, owner)

    assert len(calls) == 1
    events, _ = journal.replay()
    assert len([event for event in events if event["event_type"] == "effect_committed"]) == 1
    assert not any(event["event_type"] == "owner_terminal" for event in events)


def test_semantic_reobservation_failure_never_terminalizes(tmp_path: Path):
    journal = _journal(tmp_path)
    owner = next(
        row for row in prevention_registry.load_typed_registry()[0]
        if row["sequence_id"] == "claude-auth-token-refresh"
    )
    with pytest.raises(
        prevention_owner_runtime.OwnerRuntimeError,
        match="terminal-semantic-observation-failed",
    ):
        _runtime(
            journal,
            runner=lambda _argv: prevention_owner_runtime.ExecutionResult(
                0, '{"ok":true}', ""
            ),
            binding_provider=_BindingProvider(),
            observation_transport=_ObservationTransport(terminal_pass=False),
        ).run(_intent(journal.ownership.run_id), owner)
    assert not any(
        event["event_type"] == "owner_terminal" for event in journal.replay()[0]
    )


def test_restart_recovers_committed_result_artifact_without_rerun(tmp_path: Path):
    journal = _journal(tmp_path)
    owner = next(
        row for row in prevention_registry.load_typed_registry()[0]
        if row["sequence_id"] == "claude-auth-token-refresh"
    )
    requested = _intent(journal.ownership.run_id)
    runtime = _runtime(
        journal,
        runner=lambda _argv: prevention_owner_runtime.ExecutionResult(0, '{"ok":true}', ""),
        binding_provider=_BindingProvider(),
        observation_transport=_ObservationTransport(),
    )
    write_state = runtime._write_state

    def crash_before_executed_checkpoint(path, state):
        if state.get("status") == "EXECUTED":
            raise RuntimeError("crash-after-effect-commit")
        write_state(path, state)

    runtime._write_state = crash_before_executed_checkpoint
    with pytest.raises(RuntimeError, match="crash-after-effect-commit"):
        runtime.run(requested, owner)

    terminal = _runtime(
        journal,
        runner=lambda _argv: pytest.fail("committed process result must not rerun"),
        binding_provider=_BindingProvider(),
        observation_transport=_ObservationTransport(),
    ).run(requested, owner)
    assert terminal["status"] == "TERMINAL"
    events, _ = journal.replay()
    assert len([event for event in events if event["event_type"] == "effect_committed"]) == 1


def test_terminal_event_repairs_crashed_checkpoint_without_reverification(tmp_path: Path):
    journal = _journal(tmp_path)
    owner = next(
        row for row in prevention_registry.load_typed_registry()[0]
        if row["sequence_id"] == "claude-auth-token-refresh"
    )
    requested = _intent(journal.ownership.run_id)
    observations = []

    runtime = _runtime(
        journal,
        runner=lambda _argv: prevention_owner_runtime.ExecutionResult(0, '{"ok":true}', ""),
        binding_provider=_BindingProvider(),
        observation_transport=_ObservationTransport(
            on_query=lambda request: observations.append("EXECUTED_RESULT")
            if request["provider_symbol"].endswith("_terminal") else None
        ),
    )
    write_state = runtime._write_state

    def crash_before_terminal_checkpoint(path, state):
        if state.get("status") == "TERMINAL":
            raise RuntimeError("crash-after-owner-terminal")
        write_state(path, state)

    runtime._write_state = crash_before_terminal_checkpoint
    with pytest.raises(RuntimeError, match="crash-after-owner-terminal"):
        runtime.run(requested, owner)

    repaired = _runtime(
        journal,
        runner=lambda _argv: pytest.fail("terminal effect must not rerun"),
        binding_provider=_BindingProvider(),
        observation_transport=_ObservationTransport(
            on_query=lambda _request: pytest.fail(
                "terminal event must not reverify"
            )
        ),
    ).run(requested, owner)
    assert repaired["status"] == "TERMINAL"
    assert observations == ["EXECUTED_RESULT"]
    events, _ = journal.replay()
    assert len([event for event in events if event["event_type"] == "owner_terminal"]) == 1
    terminal_event = next(event for event in events if event["event_type"] == "owner_terminal")
    artifact = runtime.artifacts_dir / f"{terminal_event['terminal_artifact_sha256']}.json"
    assert artifact.is_file()
    assert prevention_contract.sha256_bytes(artifact.read_bytes()) == terminal_event[
        "terminal_artifact_sha256"
    ]
    payload = {
        key: value for key, value in terminal_event.items()
        if key not in {
            "event_id", "event_type", "recorded_at_utc",
            "task_id", "run_id", "branch_ref", "worktree_id",
        }
    }
    payload["result_hash"] = "f" * 64
    with pytest.raises(Exception, match="conflicting-owner_terminal"):
        journal.append_unique(
            "owner_terminal", payload, identity={"effect_id": terminal_event["effect_id"]}
        )
