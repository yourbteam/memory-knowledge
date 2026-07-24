from __future__ import annotations

import ast
import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import sequence_observer, work_memory


def _uuid() -> str:
    return str(uuid.uuid4())


def _events(tmp_path: Path, *, include_return: bool = True, terminal_result: str = "passed"):
    run_id = _uuid()
    lineage = "discovery-observer-test"
    bundle_hash = "a" * 64
    start = work_memory._event(
        "run_started", run_id=run_id, subject_id=lineage, lineage_id=lineage,
        mode="discovery", operation_kind="workflow-drive", source_bundle=[],
        source_bundle_hash=bundle_hash, classification_receipt_hash="b" * 64,
        selection_receipt_hash="c" * 64, started_at_utc="2026-07-16T00:00:00Z",
        repository_roots={"memory-knowledge": str(tmp_path)},
    )
    context_id = str(uuid.uuid5(
        uuid.NAMESPACE_URL, f"memory-knowledge:observer:context:{run_id}:{bundle_hash}",
    ))
    context = work_memory._event(
        "operation_context_recorded",
        str(uuid.uuid5(uuid.NAMESPACE_URL, f"context:{context_id}")),
        context_id=context_id, run_id=run_id, subject_id=lineage, lineage_id=lineage,
        source_bundle_hash=bundle_hash, repository_roots_hash=work_memory.sha256_bytes(
            work_memory.canonical_bytes({"memory-knowledge": str(tmp_path)})
        ), intended_outcome="Repeat the governed workflow safely.",
        repeatability_reason="The workflow recurs across tasks.",
        repeatability_evidence_ids=["prior-task-one", "prior-task-two"],
        required_inputs=["checked-out repository"],
        dependencies=[{"repository_key": "memory-knowledge", "path": "scripts/tool.py"}],
        failure_handling=[{
            "fingerprint": "d" * 64, "symptom": "tool exits nonzero", "response": "stop",
        }], verification_contract={
            "quality": "same-path", "expected_outcome": "passed",
            "success_evidence": "the exact focused command exits zero",
        }, effect_class="idempotent-local", environment_annotations=[],
        semantic_flag_annotations=[], volatility_annotations=[],
    )
    rows = [start, context]
    for ordinal in range(3):
        argv = ["python3", "scripts/tool.py", f"--step-{ordinal}"]
        command_hash = work_memory.sha256_bytes(work_memory.canonical_bytes(argv))
        execution_id = str(uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"memory-knowledge:observer:execution:{context_id}:{ordinal}:{command_hash}",
        ))
        claim = work_memory._event(
            "execution_claimed",
            str(uuid.uuid5(uuid.NAMESPACE_URL, f"claim:{execution_id}")),
            execution_id=execution_id, context_id=context_id, run_id=run_id,
            subject_id=lineage, lineage_id=lineage, source_bundle_hash=bundle_hash,
            step_ordinal=ordinal,
            step_id="verify-automation" if ordinal == 2 else f"step-{ordinal}", argv=argv,
            command_sha256=command_hash, command_source="script",
            source_ref={"repository_key": "memory-knowledge", "path": "scripts/tool.py"},
            repository_roots_hash=context["repository_roots_hash"],
            operation_kind="workflow-drive", effect_class="idempotent-local",
            claimed_at_utc=f"2026-07-16T00:0{ordinal + 1}:00Z",
        )
        rows.append(claim)
        if include_return:
            rows.append(work_memory._event(
                "execution_returned",
                str(uuid.uuid5(uuid.NAMESPACE_URL, f"return:{execution_id}")),
                execution_id=execution_id, context_id=context_id, run_id=run_id,
                subject_id=lineage, lineage_id=lineage, source_bundle_hash=bundle_hash,
                exit_code=0, result="passed", returned_at_utc=f"2026-07-16T00:0{ordinal + 1}:30Z",
            ))
    verification = work_memory._event(
        "verification_recorded", run_id=run_id, subject_id=lineage, lineage_id=lineage,
        source_bundle_hash=bundle_hash, outcome="passed", quality="same-path",
        evidence=context["verification_contract"]["success_evidence"],
        blocker_ids=[], correction_ids=[],
        changed_artifact_hashes=[],
    )
    terminal = work_memory._event(
        "run_closed", run_id=run_id, subject_id=lineage, lineage_id=lineage,
        result=terminal_result, completed_at_utc="2026-07-16T00:30:00Z",
        correction_count=0, blocker_ids=[], sequence_updated=False,
        verification_quality="same-path",
    )
    rows.extend([verification, terminal])
    return rows, start, context, terminal


@pytest.fixture
def observer_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    rows, start, context, terminal = _events(tmp_path)
    work_memory.validate_lifecycle(rows)
    current = list(rows)

    def load_ledger(path=None):
        raw = b"".join(work_memory.canonical_bytes(event) for event in current)
        return list(current), work_memory.sha256_bytes(raw)

    def transact(request):
        raw = b"".join(work_memory.canonical_bytes(event) for event in current)
        ledger, _, result = work_memory.stage_event_batch(raw, request)
        current[:] = work_memory.parse_ledger_bytes(ledger)
        return result

    monkeypatch.setattr(work_memory, "ROOT", tmp_path)
    monkeypatch.setattr(work_memory, "load_ledger", load_ledger)
    monkeypatch.setattr(work_memory, "transact", transact)
    monkeypatch.setattr(sequence_observer, "_registered_match", lambda *args: (None, [], None))
    monkeypatch.setattr(sequence_observer, "_discovery_match", lambda *args, **kwargs: (None, [], None))
    return current, start, context, terminal


def test_observer_proposes_complete_candidate_and_replays_idempotently(
    observer_store, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    current, start, _, _ = observer_store
    discovery = tmp_path / "operations/sequences/discovery/observed.md"
    manifest = discovery.with_suffix(".dependencies.json")
    discovery.parent.mkdir(parents=True)
    discovery.write_text("# observed\n")
    manifest.write_text("{}\n")
    calls = []

    def bootstrap_double(spec, root, repo_roots_file, repository_roots=None):
        calls.append(spec)
        child_run_id = _uuid()
        current.append(work_memory._event(
            "run_started", run_id=child_run_id, subject_id="discovery-proposed",
            lineage_id="discovery-proposed", mode="discovery", operation_kind="workflow-drive",
            source_bundle=[], source_bundle_hash="e" * 64,
            classification_receipt_hash="f" * 64, selection_receipt_hash="1" * 64,
            repository_roots={"memory-knowledge": str(tmp_path)},
            started_at_utc="2026-07-16T00:31:00Z",
        ))
        return {
            "discovery_id": "discovery-proposed", "run_id": child_run_id,
            "source_bundle_hash": "e" * 64, "discovery_path": str(discovery),
            "manifest_path": str(manifest),
        }

    monkeypatch.setattr(
        sequence_observer.discovery_bootstrap,
        "bootstrap",
        bootstrap_double,
    )

    first = sequence_observer.observe_committed_run(start["run_id"])
    second = sequence_observer.observe_committed_run(start["run_id"])

    assert first["disposition"] == "PROPOSE_DISCOVERY"
    assert first["target_id"] == "discovery-proposed"
    assert second["decision_id"] == first["decision_id"]
    assert len(calls) == 1
    observer_events = [
        event for event in current if event["event_type"].startswith("observer_")
    ]
    assert [event["event_type"] for event in observer_events[-3:]] == [
        "observer_decision_recorded",
        "observer_bootstrap_result_recorded",
        "observer_candidate_linked",
    ]
    decision = observer_events[-3]
    assert decision["eligibility"]["eligible"] is True
    assert sum(item["value"] for item in decision["value_components"]) >= 20
    decision_file = tmp_path / "decision.json"
    decision_file.write_text(json.dumps({
        key: decision[key] for key in work_memory.EVENT_FIELDS["observer_decision_recorded"][0]
    }))
    replay = work_memory.cmd_observer_decision_append(
        SimpleNamespace(decision_file=str(decision_file)),
    )
    assert replay["already_recorded"] is True


def test_observer_missing_return_is_auditable_no_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows, start, _, _ = _events(tmp_path, include_return=False)
    current = list(rows)
    monkeypatch.setattr(work_memory, "ROOT", tmp_path)
    monkeypatch.setattr(
        work_memory, "load_ledger",
        lambda path=None: (list(current), work_memory.sha256_bytes(
            b"".join(work_memory.canonical_bytes(event) for event in current)
        )),
    )

    def transact(request):
        raw = b"".join(work_memory.canonical_bytes(event) for event in current)
        ledger, _, result = work_memory.stage_event_batch(raw, request)
        current[:] = work_memory.parse_ledger_bytes(ledger)
        return result

    monkeypatch.setattr(work_memory, "transact", transact)
    result = sequence_observer.observe_committed_run(start["run_id"])

    assert result["disposition"] == "NO_CANDIDATE"
    assert current[-1]["safe_failure_code"] == "execution-evidence-incomplete"
    assert current[-1]["candidate_identity"] is None


def test_registered_match_precedes_discovery_lookup(observer_store, monkeypatch):
    _, start, _, _ = observer_store
    monkeypatch.setattr(
        sequence_observer, "_registered_match",
        lambda *args: ("existing-sequence", ["existing-sequence"], None),
    )
    monkeypatch.setattr(
        sequence_observer, "_discovery_match",
        lambda *args: pytest.fail("discovery lookup must not run after registered match"),
    )

    result = sequence_observer.observe_committed_run(start["run_id"])

    assert result == {
        "ok": True,
        "status": "OBSERVED",
        "decision_id": result["decision_id"],
        "disposition": "LINK_REGISTERED",
        "target_id": "existing-sequence",
    }


def test_observer_cap_is_no_candidate_with_cursor(observer_store):
    current, start, _, _ = observer_store
    result = sequence_observer.observe_committed_run(
        start["run_id"],
        config=sequence_observer.ObserverConfig(maximum_observation_count=2),
    )

    assert result["status"] == "CAP_REACHED"
    assert result["disposition"] == "NO_CANDIDATE"
    assert current[-1]["safe_failure_code"] == "CAP_REACHED"
    assert current[-1]["cap_cursor"] is not None


def test_observer_run_local_cap_resume_advances_cursor(observer_store):
    _, start, _, _ = observer_store
    config = sequence_observer.ObserverConfig(maximum_observation_count=2)

    first = sequence_observer.observe_committed_run(start["run_id"], config=config)
    second = sequence_observer.observe_committed_run(
        start["run_id"],
        config=sequence_observer.ObserverConfig(
            maximum_observation_count=2,
            cursor_recorded_at_utc=first["cap_cursor"]["recorded_at_utc"],
            cursor_event_id=first["cap_cursor"]["event_id"],
        ),
    )

    assert first["status"] == second["status"] == "CAP_REACHED"
    assert second["cap_cursor"] != first["cap_cursor"]


def test_observer_resume_never_exceeds_count_cap_or_proposes_from_partial_history(
    observer_store, monkeypatch: pytest.MonkeyPatch,
) -> None:
    current, start, _, _ = observer_store
    for minute in (20, 15):
        current.append(work_memory._event(
            "run_started", run_id=_uuid(), subject_id=start["subject_id"],
            lineage_id=start["lineage_id"], mode="discovery",
            operation_kind="workflow-drive", source_bundle=[],
            source_bundle_hash=str(minute % 10) * 64,
            classification_receipt_hash="8" * 64,
            selection_receipt_hash="9" * 64,
            started_at_utc=f"2026-07-16T00:{minute}:00Z",
            recorded_at_utc=f"2026-07-16T00:{minute}:00Z",
        ))
    run_event_count = len([
        event for event in current if event.get("run_id") == start["run_id"]
    ])
    maximum = run_event_count + 1
    first = sequence_observer.observe_committed_run(
        start["run_id"],
        config=sequence_observer.ObserverConfig(maximum_observation_count=maximum),
    )
    seen_counts: list[int] = []
    original = sequence_observer._governed_value_evidence

    def capture(events, *args):
        seen_counts.append(len(events))
        return original(events, *args)

    monkeypatch.setattr(sequence_observer, "_governed_value_evidence", capture)
    resumed = sequence_observer.observe_committed_run(
        start["run_id"],
        config=sequence_observer.ObserverConfig(
            maximum_observation_count=maximum,
            cursor_recorded_at_utc=first["cap_cursor"]["recorded_at_utc"],
            cursor_event_id=first["cap_cursor"]["event_id"],
        ),
    )

    assert first["status"] == "CAP_REACHED"
    assert seen_counts and max(seen_counts) <= maximum
    assert resumed["disposition"] == "NO_CANDIDATE"
    assert current[-1]["safe_failure_code"] == "PAGINATION_INCOMPLETE"


def test_observer_rejects_candidate_outside_configured_repository_surface(observer_store) -> None:
    current, start, _, _ = observer_store

    result = sequence_observer.observe_committed_run(
        start["run_id"],
        config=sequence_observer.ObserverConfig(allowed_repository_keys=("other-repository",)),
    )

    assert result["disposition"] == "NO_CANDIDATE"
    assert current[-1]["safe_failure_code"] == "candidate-surface-not-allowed"


def test_observer_excludes_evidence_older_than_configured_age(
    observer_store, monkeypatch: pytest.MonkeyPatch,
) -> None:
    current, start, _, _ = observer_store
    old = work_memory._event(
        "run_started", run_id=_uuid(), subject_id=start["subject_id"],
        lineage_id=start["lineage_id"], mode="discovery", operation_kind="workflow-drive",
        source_bundle=[], source_bundle_hash="7" * 64,
        classification_receipt_hash="8" * 64, selection_receipt_hash="9" * 64,
        started_at_utc="2025-01-01T00:00:00Z", recorded_at_utc="2025-01-01T00:00:00Z",
    )
    current.append(old)
    seen: set[str] = set()
    original = sequence_observer._governed_value_evidence

    def capture(events, *args):
        seen.update(event["event_id"] for event in events)
        return original(events, *args)

    monkeypatch.setattr(sequence_observer, "_governed_value_evidence", capture)
    monkeypatch.setattr(sequence_observer, "_identity_within_surfaces", lambda *args: False)

    sequence_observer.observe_committed_run(
        start["run_id"],
        config=sequence_observer.ObserverConfig(maximum_evidence_age_days=30),
    )

    assert old["event_id"] not in seen


def test_observer_incomplete_dependency_contract_is_no_candidate(
    observer_store, monkeypatch: pytest.MonkeyPatch,
) -> None:
    current, start, context, _ = observer_store
    context["dependencies"] = []
    monkeypatch.setattr(
        sequence_observer.discovery_bootstrap, "bootstrap",
        lambda *args, **kwargs: pytest.fail("incomplete proposal must not reach bootstrap"),
    )

    result = sequence_observer.observe_committed_run(start["run_id"])

    assert result["disposition"] == "NO_CANDIDATE"
    assert current[-1]["safe_failure_code"] == "missing-command-source-dependency"


def test_tool_help_source_must_be_declared_as_dependency(
    observer_store, monkeypatch: pytest.MonkeyPatch,
) -> None:
    current, start, context, _ = observer_store
    context["dependencies"] = []
    for claim in current:
        if claim["event_type"] == "execution_claimed":
            claim["command_source"] = "tool_help"
    monkeypatch.setattr(
        sequence_observer.discovery_bootstrap, "bootstrap",
        lambda *args, **kwargs: pytest.fail("undeclared tool help must not reach bootstrap"),
    )

    result = sequence_observer.observe_committed_run(start["run_id"])

    assert result["disposition"] == "NO_CANDIDATE"
    assert current[-1]["safe_failure_code"] == "missing-command-source-dependency"


def test_declared_success_evidence_must_match_final_verification(
    observer_store, monkeypatch: pytest.MonkeyPatch,
) -> None:
    current, start, context, _ = observer_store
    context["verification_contract"]["success_evidence"] = "different evidence"
    monkeypatch.setattr(
        sequence_observer.discovery_bootstrap, "bootstrap",
        lambda *args, **kwargs: pytest.fail("mismatched verification must not reach bootstrap"),
    )

    result = sequence_observer.observe_committed_run(start["run_id"])

    assert result["disposition"] == "NO_CANDIDATE"
    assert current[-1]["safe_failure_code"] == "verification-evidence-mismatch"


def test_governed_quarantine_suppresses_unchanged_candidate(
    observer_store, monkeypatch: pytest.MonkeyPatch,
) -> None:
    current, start, _, terminal = observer_store
    monkeypatch.setattr(
        sequence_observer.discovery_candidate_reconciliation,
        "candidate_lifecycle_feedback",
        lambda *args, **kwargs: [{
            "disposition": "quarantine",
            "recorded_at_utc": terminal["completed_at_utc"],
            "discovery_id": "discovery-old", "decision_id": "decision-old",
        }],
    )
    monkeypatch.setattr(
        sequence_observer.discovery_bootstrap, "bootstrap",
        lambda *args, **kwargs: pytest.fail("suppressed candidate must not reach bootstrap"),
    )

    result = sequence_observer.observe_committed_run(start["run_id"])

    assert result["disposition"] == "NO_CANDIDATE"
    decision = current[-1]
    assert decision["safe_failure_code"] == "SUPPRESSED"
    assert decision["suppression"]["reason"] == "governed-quarantine-suppressed"


def test_elapsed_cap_persists_no_candidate_before_bootstrap(
    observer_store, monkeypatch: pytest.MonkeyPatch,
) -> None:
    current, start, _, _ = observer_store
    times = iter((0.0, 3.0))
    monkeypatch.setattr(sequence_observer.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(
        sequence_observer.discovery_bootstrap, "bootstrap",
        lambda *args, **kwargs: pytest.fail("time-capped decision must not reach bootstrap"),
    )

    result = sequence_observer.observe_committed_run(start["run_id"])

    assert result["status"] == "CAP_REACHED"
    assert result["disposition"] == "NO_CANDIDATE"
    assert result["cap_cursor"] is not None
    assert current[-1]["safe_failure_code"] == "CAP_REACHED"
    assert current[-1]["cap_cursor"] == result["cap_cursor"]


def test_registered_match_is_not_overwritten_by_promotion_feedback(
    observer_store, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, start, _, terminal = observer_store
    monkeypatch.setattr(
        sequence_observer, "_registered_match",
        lambda *args: ("existing-sequence", ["existing-sequence"], None),
    )
    monkeypatch.setattr(
        sequence_observer.discovery_candidate_reconciliation,
        "candidate_lifecycle_feedback",
        lambda *args, **kwargs: [{
            "disposition": "promoted", "recorded_at_utc": terminal["completed_at_utc"],
            "discovery_id": "old-discovery", "decision_id": "old-decision",
        }],
    )

    result = sequence_observer.observe_committed_run(start["run_id"])

    assert result["disposition"] == "LINK_REGISTERED"
    assert result["target_id"] == "existing-sequence"


def test_repeated_correction_value_requires_the_same_blocker_fingerprint() -> None:
    first = {"event_id": _uuid(), "blocker_id": _uuid(), "blocker_fingerprint": "a" * 64}
    second_same = {
        "event_id": _uuid(), "blocker_id": _uuid(), "blocker_fingerprint": "a" * 64,
    }
    second_different = {
        "event_id": _uuid(), "blocker_id": _uuid(), "blocker_fingerprint": "b" * 64,
    }

    assert sequence_observer._has_repeated_blocker_fingerprint([first, second_same]) is True
    assert sequence_observer._has_repeated_blocker_fingerprint([first, second_different]) is False


def test_governed_corrections_preserve_exact_blocker_fingerprint_binding() -> None:
    prior_run, successor_run = _uuid(), _uuid()
    blocker_one, blocker_two = _uuid(), _uuid()
    correction_one, correction_two = _uuid(), _uuid()
    prior_terminal_id = _uuid()
    lineage, prior_hash, successor_hash = "lineage", "1" * 64, "2" * 64
    current_start = {"run_id": _uuid()}
    current_terminal = {"event_id": _uuid()}
    candidate_fingerprint = "3" * 64
    events = [
        {"event_type": "observer_decision_recorded", "candidate_fingerprint": candidate_fingerprint,
         "trigger_event_id": prior_terminal_id},
        {"event_type": "run_started", "event_id": _uuid(), "run_id": prior_run,
         "lineage_id": lineage, "source_bundle_hash": prior_hash},
        {"event_type": "verification_recorded", "event_id": _uuid(), "run_id": prior_run,
         "lineage_id": lineage, "source_bundle_hash": prior_hash,
         "outcome": "passed", "quality": "same-path"},
        {"event_type": "run_closed", "event_id": prior_terminal_id, "run_id": prior_run,
         "result": "passed"},
    ]
    for blocker_id, correction_id in (
        (blocker_one, correction_one), (blocker_two, correction_two),
    ):
        events.extend([
            {"event_type": "blocker_opened", "event_id": _uuid(),
             "blocker_id": blocker_id, "fingerprint": "4" * 64, "status": "open"},
            {"event_type": "correction_recorded", "event_id": _uuid(),
             "run_id": prior_run, "lineage_id": lineage, "blocker_id": blocker_id,
             "correction_id": correction_id},
            {"event_type": "blocker_transitioned", "event_id": _uuid(),
             "blocker_id": blocker_id, "to_status": "closed"},
        ])
    events.extend([
        {"event_type": "run_started", "event_id": _uuid(), "run_id": successor_run,
         "lineage_id": lineage, "source_bundle_hash": successor_hash,
         "predecessor_run_id": prior_run,
         "verifies_correction_ids": [correction_one, correction_two]},
        {"event_type": "verification_recorded", "event_id": _uuid(),
         "run_id": successor_run, "lineage_id": lineage,
         "source_bundle_hash": successor_hash, "outcome": "passed", "quality": "same-path"},
        {"event_type": "run_closed", "event_id": _uuid(), "run_id": successor_run,
         "result": "passed"},
    ])

    _, corrections = sequence_observer._governed_value_evidence(
        events, current_start, current_terminal, candidate_fingerprint,
        {"repeatability_evidence_ids": []},
    )

    assert len(corrections) == 2
    assert {item["blocker_fingerprint"] for item in corrections} == {"4" * 64}
    assert sequence_observer._has_repeated_blocker_fingerprint(corrections) is True


def test_fully_explicit_legacy_registered_identity_is_reused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    current, start, _, terminal = _events(tmp_path)
    monkeypatch.setattr(work_memory, "ROOT", tmp_path)
    identity, fingerprint, _, error = sequence_observer._reconstruct(
        current, start, terminal,
    )
    assert error is None
    sequence_id = "legacy-explicit"
    folder = tmp_path / "operations/sequences" / sequence_id
    folder.mkdir(parents=True)
    commands = "\n".join(
        "| {step_id} | {command} | passed | Guard provenance: {source}:{repo}:{path} |".format(
            step_id=step["step_id"], command=sequence_observer.shlex.join(step["argv"]),
            source=step["command_source"], repo=step["source_ref"]["repository_key"],
            path=step["source_ref"]["path"],
        )
        for step in identity["steps"]
    )
    failure = identity["failure_handling"][0]
    (folder / "sequence.md").write_text(
        "# legacy\n\n"
        f"CandidateEffectClass: {identity['effect_class']}\n"
        f"CandidateEnvironmentAnnotations: {json.dumps(identity['environment_annotations'])}\n"
        f"CandidateSemanticFlagAnnotations: {json.dumps(identity['semantic_flag_annotations'])}\n"
        f"CandidateVolatilityPolicy: {json.dumps(identity['volatility_policy'])}\n\n"
        f"## Outcome\n\n{identity['intended_outcome']}\n\n"
        "## Required Inputs\n\n- checked-out repository\n\n"
        "## Commands\n\n| step | command or action | result | correction or note |\n"
        "| --- | --- | --- | --- |\n" + commands + "\n\n"
        f"## Failure Handling\n\n{failure['fingerprint']}: {failure['symptom']} -> {failure['response']}\n\n"
        f"## Verification\n\n- {identity['verification_contract']['success_evidence']}\n",
        encoding="utf-8",
    )
    (folder / "dependencies.json").write_text(json.dumps({
        "schema_version": 1, "lineage_id": "legacy-lineage",
        "dependencies": [{
            "kind": "file", "repository_key": item["repository_key"],
            "path_or_sequence_id": item["path"],
        } for item in identity["dependencies"]],
    }), encoding="utf-8")
    registered_run = _uuid()
    registered_hash = "9" * 64
    current.extend([
        work_memory._event(
            "run_started", run_id=registered_run, subject_id=sequence_id,
            lineage_id="legacy-lineage", mode="registered", operation_kind="workflow-drive",
            source_bundle=[], source_bundle_hash=registered_hash,
            classification_receipt_hash="1" * 64, selection_receipt_hash="2" * 64,
            started_at_utc="2026-07-16T01:00:00Z",
        ),
        work_memory._event(
            "verification_recorded", run_id=registered_run, subject_id=sequence_id,
            lineage_id="legacy-lineage", source_bundle_hash=registered_hash,
            outcome="passed", quality="same-path", evidence="passed",
            blocker_ids=[], correction_ids=[], changed_artifact_hashes=[],
        ),
        work_memory._event(
            "run_closed", run_id=registered_run, subject_id=sequence_id,
            lineage_id="legacy-lineage", result="passed",
            completed_at_utc="2026-07-16T01:10:00Z", correction_count=0,
            blocker_ids=[], sequence_updated=False, verification_quality="same-path",
        ),
    ])
    monkeypatch.setattr(work_memory, "registry_rows", lambda: ([{
        "sequence_id": sequence_id, "operation_kinds": "workflow-drive",
        "automation_display": "python3 scripts/tool.py", "lineage_id": "legacy-lineage",
    }], "a" * 64))
    monkeypatch.setattr(
        work_memory, "resolve_bundle",
        lambda **kwargs: ([], registered_hash, "legacy-lineage"),
    )

    matched, considered, match_error = sequence_observer._registered_match(
        identity, fingerprint, "workflow-drive", current,
    )

    assert (matched, match_error) == (sequence_id, None)
    assert considered == [sequence_id]


def test_observer_source_has_no_execution_or_external_service_path() -> None:
    path = Path(sequence_observer.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    called = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert not ({"subprocess", "socket", "requests", "urllib", "httpx"} & imported)
    assert not ({"run", "Popen", "promote", "register", "deploy"} & called)
