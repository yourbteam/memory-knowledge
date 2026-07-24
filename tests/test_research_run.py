from __future__ import annotations

import fcntl
import importlib.util
import json
import os
import signal
import sys
from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "skills/research-playbook/scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("research_run", SCRIPTS / "research_run.py")
assert SPEC is not None and SPEC.loader is not None
research_run = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = research_run
SPEC.loader.exec_module(research_run)
controller = research_run.controller


def requirement() -> dict:
    return {
        "id": "R1",
        "text": "Produce grounded research.",
        "source": "fixture:R1",
        "operational_maturity": "CURRENT_RUNTIME",
        "evidence_availability": "AVAILABLE",
        "acceptance_intent": "The research value is grounded.",
        "scope_id": "fixture",
        "research_value_type": "string",
        "planner_obligations": [],
    }


def charter() -> dict:
    return {
        "objective": "Test the deterministic driver.",
        "budget": {
            "maximum_candidate_rounds": 2,
            "maximum_agent_spawn_attempts": 10,
            "maximum_elapsed_minutes": 45,
            "maximum_retries_per_role": 1,
        },
    }


def candidate() -> dict:
    return {
        "research_markdown": "# Grounded research\n",
        "evidence_index": [],
        "requirement_statuses": [
            {"requirement_id": "R1", "research_value": "grounded", "evidence_ids": []}
        ],
        "material_gaps": [],
        "planner_readiness_constraints": [],
    }


def raw_finding(lens: str = "INTERNAL_READINESS") -> dict:
    return {
        "id": "finding-1",
        "fingerprint": "reported-fingerprint-1",
        "lens": lens,
        "originating_stage": "RESEARCH",
        "requirement_ids": ["R1"],
        "type": "FACT_GAP",
        "materiality": "BLOCKER",
        "practical_consequence": "The candidate must be corrected before planning.",
        "evidence": "fixture:evidence",
        "proposed_disposition": "FIX_IN_RESEARCH",
        "status": "OPEN",
    }


def passing_results() -> list[dict]:
    return [
        {"role": "CORE_RESEARCHER", "result": candidate()},
        {"role": "INTERNAL_READINESS", "result": {"verdict": "PASS", "findings": []}},
        {"role": "REQUIREMENTS_COVERAGE", "result": {"verdict": "PASS", "findings": []}},
        {"role": "REQUIREMENTS_SATISFACTION", "result": {"verdict": "PASS", "findings": []}},
        {"role": "ADJUDICATOR", "result": []},
    ]


def write_json(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def args(tmp_path: Path, fixture: Path) -> Namespace:
    return Namespace(
        command="drive",
        run_dir=str(tmp_path / "run"),
        charter=str(write_json(tmp_path / "charter.json", charter())),
        requirements=str(write_json(tmp_path / "requirements.json", [requirement()])),
        operational_maturity="CURRENT_RUNTIME",
        evidence_availability=str(write_json(tmp_path / "evidence.json", {"source": "AVAILABLE"})),
        repository_root=str(ROOT),
        output_directory=str(tmp_path / "package"),
        runtime_adapter="fake",
        resume_token="stable-token",
        role_timeout_seconds=600,
        termination_grace_seconds=5,
        codex_executable="codex",
        model=None,
        fixture=str(fixture),
    )


def test_operation_registry_is_closed() -> None:
    assert {item.value for item in research_run.Operation} == {
        "INITIALIZE_SCOPE",
        "ADMIT_ROUND",
        "LAUNCH_ROLE",
        "ACCEPT_ROLE_RESULT",
        "REGISTER_CANDIDATE",
        "ACCEPT_LENS_RESULT",
        "ACCEPT_ADJUDICATION",
        "APPLY_CANDIDATE_CORRECTION",
        "FINALIZE_ROUND",
        "EMIT_PACKAGE",
        "TERMINATE",
    }


def test_candidate_correction_is_structured_and_hash_bound() -> None:
    base = candidate()
    corrected = research_run.apply_candidate_correction(
        base,
        {
            "base_candidate_hash": controller.canonical_hash(base),
            "replacements": {"research_markdown": "# Corrected\n"},
        },
    )
    assert corrected["research_markdown"] == "# Corrected\n"
    assert base["research_markdown"] != corrected["research_markdown"]
    with pytest.raises(research_run.KernelError, match="forbidden"):
        research_run.apply_candidate_correction(
            base,
            {
                "base_candidate_hash": controller.canonical_hash(base),
                "replacements": {"/research_markdown": "raw patch"},
            },
        )


def test_whole_round_admission_is_non_mutating() -> None:
    started = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)
    state = controller.create_state(
        charter(), [requirement()], "CURRENT_RUNTIME", {"source": "AVAILABLE"}, started_at=started
    )
    before = controller.canonical_hash(state)
    rejected = research_run.admit_round(
        state,
        round_number=1,
        role_timeout_seconds=3500,
        termination_grace_seconds=101,
        now_epoch=started.timestamp(),
    )
    assert rejected["admitted"] is False
    assert rejected["reason"] == "TIME_BUDGET"
    assert controller.canonical_hash(state) == before == rejected["state_hash"]


def test_codex_argv_is_registry_owned() -> None:
    config = {
        "codex_executable": "/opt/bin/codex",
        "repository_root": "/repo",
        "model": "gpt-test",
    }
    argv = research_run.build_codex_argv(config, Path("/tmp/schema.json"), Path("/tmp/result.json"))
    assert argv == [
        "/opt/bin/codex",
        "exec",
        "--ephemeral",
        "--sandbox",
        "read-only",
        "--color",
        "never",
        "--cd",
        "/repo",
        "--output-schema",
        "/tmp/schema.json",
        "--output-last-message",
        "/tmp/result.json",
        "--model",
        "gpt-test",
        "-",
    ]


def test_metrics_union_concurrent_roles_and_reject_persisted_overlap() -> None:
    state = {"metrics": {"mechanical_intervals": [[0.0, 1.0]], "role_intervals": [[2.0, 5.0], [3.0, 7.0]]}}
    summary = research_run.Metrics(state).summarize()
    assert summary == {
        "mechanical_seconds": 1.0,
        "role_active_seconds": 5.0,
        "total_seconds": 6.0,
        "mechanical_ratio": pytest.approx(1 / 6),
    }
    state["metrics"] = {"mechanical_intervals": [[3.0, 4.0]], "role_intervals": [[2.0, 5.0]]}
    with pytest.raises(research_run.KernelError, match="overlap"):
        research_run.Metrics(state).summarize()
    state["metrics"] = {"mechanical_intervals": [[3.0, 4.0]], "role_intervals": [], "events": []}
    metrics = research_run.Metrics(state)
    metrics.role_interval(2.0, 5.0)
    assert metrics.summarize() == {
        "mechanical_seconds": 0.0,
        "role_active_seconds": 3.0,
        "total_seconds": 3.0,
        "mechanical_ratio": 0.0,
    }


def test_one_drive_request_emits_package_and_replays_terminal(tmp_path: Path) -> None:
    fixture = write_json(
        tmp_path / "fixture.json",
        {
            "results": [
                {"role": "CORE_RESEARCHER", "result": candidate()},
                {"role": "INTERNAL_READINESS", "result": {"verdict": "PASS", "findings": []}},
                {"role": "REQUIREMENTS_COVERAGE", "result": {"verdict": "PASS", "findings": []}},
                {"role": "REQUIREMENTS_SATISFACTION", "result": {"verdict": "PASS", "findings": []}},
                {"role": "ADJUDICATOR", "result": []},
            ]
        },
    )
    options = args(tmp_path, fixture)
    first = research_run.ResearchDriver(options).run()
    assert first["verdict"] == "PASS"
    assert (tmp_path / "package/manifest.json").is_file()
    first_hash = controller.canonical_hash(first)
    replay = research_run.ResearchDriver(options).run()
    assert controller.canonical_hash(replay) == first_hash
    slots = json.loads((tmp_path / "run/agent-slots.json").read_text(encoding="utf-8"))
    assert all(slot["state"] == "released" for slot in slots["slots"])


def test_resume_from_live_result_does_not_launch_duplicate_role(tmp_path: Path) -> None:
    fixture = write_json(tmp_path / "fixture.json", {"results": passing_results()})
    options = args(tmp_path, fixture)
    interrupted = research_run.ResearchDriver(options)
    interrupted._dispatch(research_run.Operation.INITIALIZE_SCOPE)
    interrupted._dispatch(research_run.Operation.ADMIT_ROUND)
    interrupted._dispatch(research_run.Operation.LAUNCH_ROLE)
    assert interrupted.state["next_operation"] == research_run.Operation.ACCEPT_ROLE_RESULT.value
    assert interrupted.state["fake_cursor"] == 1

    result = research_run.ResearchDriver(options).run()
    resumed_state = json.loads((tmp_path / "run/driver-state.json").read_text(encoding="utf-8"))
    assert result["verdict"] == "PASS"
    assert resumed_state["fake_cursor"] == 5
    assert len(resumed_state["leases"]) == 5


def test_crash_inside_launch_recovers_bound_lease_without_duplicate(tmp_path: Path) -> None:
    fixture = write_json(tmp_path / "fixture.json", {"results": passing_results()})
    options = args(tmp_path, fixture)
    interrupted = research_run.ResearchDriver(options)
    interrupted._dispatch(research_run.Operation.INITIALIZE_SCOPE)
    interrupted._dispatch(research_run.Operation.ADMIT_ROUND)
    interrupted._start_role("CORE_RESEARCHER")
    persisted = json.loads(interrupted.state_path.read_text(encoding="utf-8"))
    assert persisted["next_operation"] == research_run.Operation.ACCEPT_ROLE_RESULT.value
    assert persisted["context"]["pending_lease"] in persisted["leases"]

    result = research_run.ResearchDriver(options).run()
    resumed = json.loads(interrupted.state_path.read_text(encoding="utf-8"))
    assert result["verdict"] == "PASS"
    assert resumed["fake_cursor"] == 5
    assert len(resumed["leases"]) == 5


def test_prepared_candidate_effect_reconciles_without_duplicate_mutation(tmp_path: Path) -> None:
    fixture = write_json(tmp_path / "fixture.json", {"results": passing_results()})
    options = args(tmp_path, fixture)
    interrupted = research_run.ResearchDriver(options)
    for operation in (
        research_run.Operation.INITIALIZE_SCOPE,
        research_run.Operation.ADMIT_ROUND,
        research_run.Operation.LAUNCH_ROLE,
        research_run.Operation.ACCEPT_ROLE_RESULT,
    ):
        interrupted._dispatch(operation)
    context = interrupted.state["context"]
    candidate_hash = controller.canonical_hash(context["core_output"])
    envelope_hash = controller.canonical_hash(context["envelope"])
    key = f"candidate:{candidate_hash}:{envelope_hash}"
    expected = {
        "kind": "candidate",
        "candidate_hash": candidate_hash,
        "envelope_hash": envelope_hash,
        "candidate_payload": context["core_output"],
        "envelope_payload": context["envelope"],
        "evidence_availability": controller.load_state(interrupted.controller_path)[
            "evidence_availability"
        ],
    }
    interrupted.state["journal"][key] = {
        "status": "PREPARED",
        "before_hash": research_run._file_hash(interrupted.controller_path),
        "expected": expected,
    }
    interrupted.persist()
    controller.mutate_file(
        interrupted.controller_path,
        lambda state: controller.record_candidate(
            state,
            context["core_output"],
            context["envelope"],
            evidence_availability=state["evidence_availability"],
        ),
    )

    result = research_run.ResearchDriver(options).run()
    controller_state = controller.load_state(interrupted.controller_path)
    resumed_state = json.loads(interrupted.state_path.read_text(encoding="utf-8"))
    assert result["verdict"] == "PASS"
    assert len(controller_state["candidates"]) == 1
    assert resumed_state["journal"][key]["reconciled"] is True
    assert any(
        event["event"] == "checkpoint_resume" and event["effect"] == key
        for event in resumed_state["metrics"]["events"]
    )


def test_prepared_controller_effect_rejects_changed_pre_state(tmp_path: Path) -> None:
    fixture = write_json(tmp_path / "fixture.json", {"results": passing_results()})
    options = args(tmp_path, fixture)
    driver = research_run.ResearchDriver(options)
    for operation in (
        research_run.Operation.INITIALIZE_SCOPE,
        research_run.Operation.ADMIT_ROUND,
        research_run.Operation.LAUNCH_ROLE,
        research_run.Operation.ACCEPT_ROLE_RESULT,
    ):
        driver._dispatch(operation)
    context = driver.state["context"]
    candidate_hash = controller.canonical_hash(context["core_output"])
    envelope_hash = controller.canonical_hash(context["envelope"])
    key = f"candidate:{candidate_hash}:{envelope_hash}"
    driver.state["journal"][key] = {
        "status": "PREPARED",
        "before_hash": research_run._file_hash(driver.controller_path),
        "expected": {
            "kind": "candidate",
            "candidate_hash": candidate_hash,
            "envelope_hash": envelope_hash,
            "candidate_payload": context["core_output"],
            "envelope_payload": context["envelope"],
            "evidence_availability": controller.load_state(driver.controller_path)[
                "evidence_availability"
            ],
        },
    }
    driver.persist()
    controller.mutate_file(
        driver.controller_path,
        lambda state: controller._touch(state, "2027-01-01T00:00:00Z"),
    )
    with pytest.raises(research_run.KernelError, match="conflicting pre-state"):
        research_run.ResearchDriver(options).run()


def test_lens_acceptance_resumes_after_attempt_commit_without_missing_payload(tmp_path: Path) -> None:
    fixture = write_json(tmp_path / "fixture.json", {"results": passing_results()})
    options = args(tmp_path, fixture)
    driver = research_run.ResearchDriver(options)
    for operation in (
        research_run.Operation.INITIALIZE_SCOPE,
        research_run.Operation.ADMIT_ROUND,
        research_run.Operation.LAUNCH_ROLE,
        research_run.Operation.ACCEPT_ROLE_RESULT,
        research_run.Operation.REGISTER_CANDIDATE,
        research_run.Operation.LAUNCH_ROLE,
        research_run.Operation.LAUNCH_ROLE,
        research_run.Operation.LAUNCH_ROLE,
        research_run.Operation.ACCEPT_ROLE_RESULT,
    ):
        driver._dispatch(operation)
    context = driver.state["context"]
    role = context["pending_lens_role"]
    output = context["pending_lens_output"]
    handle = driver._role_handle(context["lens_leases"][role])
    driver._complete_role_success(handle)
    driver._record_attempt(handle, context["candidate_hash"], context["envelope_hash"], output)
    driver.persist()

    result = research_run.ResearchDriver(options).run()
    state = controller.load_state(driver.controller_path)
    assert result["verdict"] == "PASS"
    assert len([item for item in state["attempts"] if item["runtime_agent_id"] == handle.runtime_agent_id]) == 1


def test_failed_launch_releases_slot_retries_and_supersedes_fingerprint(tmp_path: Path) -> None:
    results = passing_results()
    results.insert(0, {"role": "CORE_RESEARCHER", "error": "captured launch failure"})
    fixture = write_json(tmp_path / "fixture.json", {"results": results})
    options = args(tmp_path, fixture)

    result = research_run.ResearchDriver(options).run()
    driver_state = json.loads((tmp_path / "run/driver-state.json").read_text(encoding="utf-8"))
    controller_state = controller.load_state(tmp_path / "run/controller-state.json")
    core_attempts = [item for item in controller_state["attempts"] if item["role"] == "CORE_RESEARCHER"]
    failure = next(iter(driver_state["mechanical_failures"].values()))
    slots = json.loads((tmp_path / "run/agent-slots.json").read_text(encoding="utf-8"))

    assert result["verdict"] == "PASS"
    assert [item["status"] for item in core_attempts] == ["FAILED", "SUCCEEDED"]
    assert failure["status"] == "SUPERSEDED_PERMANENTLY"
    assert failure["successor_fingerprint"]
    assert driver_state["fake_cursor"] == 6
    assert all(slot["state"] == "released" for slot in slots["slots"])


def test_invalid_typed_output_is_failed_before_success_and_retried(tmp_path: Path) -> None:
    results = passing_results()
    results.insert(0, {"role": "CORE_RESEARCHER", "result": {"research_markdown": "incomplete"}})
    fixture = write_json(tmp_path / "fixture.json", {"results": results})
    result = research_run.ResearchDriver(args(tmp_path, fixture)).run()
    state = controller.load_state(tmp_path / "run/controller-state.json")
    core_attempts = [item for item in state["attempts"] if item["role"] == "CORE_RESEARCHER"]
    assert result["verdict"] == "PASS"
    assert [item["status"] for item in core_attempts] == ["FAILED", "SUCCEEDED"]


def test_retry_cannot_consume_attempts_reserved_for_mandatory_round_remainder(tmp_path: Path) -> None:
    fixture = write_json(
        tmp_path / "fixture.json",
        {"results": [{"role": "CORE_RESEARCHER", "error": "first attempt failed"}]},
    )
    options = args(tmp_path, fixture)
    limited = charter()
    limited["budget"]["maximum_agent_spawn_attempts"] = 5
    write_json(Path(options.charter), limited)
    result = research_run.ResearchDriver(options).run()
    state = json.loads((tmp_path / "run/driver-state.json").read_text(encoding="utf-8"))
    assert result["verdict"] == "CAP_REACHED"
    assert result["reason"] == "ATTEMPT_BUDGET"
    assert state["fake_cursor"] == 1


def test_preloaded_failed_fingerprint_is_rejected_before_slot_or_launch(tmp_path: Path) -> None:
    fixture = write_json(tmp_path / "fixture.json", {"results": []})
    driver = research_run.ResearchDriver(args(tmp_path, fixture))
    driver._dispatch(research_run.Operation.INITIALIZE_SCOPE)
    driver._dispatch(research_run.Operation.ADMIT_ROUND)
    payload = {"role": "CORE_RESEARCHER", "round": 1, "attempt": 1, "candidate_hash": None}
    fingerprint = research_run.mechanical_operation_fingerprint(
        research_run.Operation.LAUNCH_ROLE,
        payload,
        state_version=driver.state["schema_version"],
        role="CORE_RESEARCHER",
        bundle_identity=driver.state["run_id"],
    )
    driver.state["mechanical_failures"][fingerprint] = {
        "status": "SUPERSEDED_PERMANENTLY",
        "round": 1,
        "role": "CORE_RESEARCHER",
    }
    driver.persist()
    with pytest.raises(research_run.KernelError, match="superseded"):
        driver._start_role("CORE_RESEARCHER")
    assert driver.state["leases"] == {}
    assert any(event["event"] == "superseded_prevention" for event in driver.state["metrics"]["events"])


def test_fix_in_research_round_applies_structured_correction_and_converges(tmp_path: Path) -> None:
    finding = raw_finding()
    base = candidate()
    corrected_markdown = "# Corrected grounded research\n"
    results = [
        {"role": "CORE_RESEARCHER", "result": base},
        {"role": "INTERNAL_READINESS", "result": {"verdict": "GAPS", "findings": [finding]}},
        {"role": "REQUIREMENTS_COVERAGE", "result": {"verdict": "PASS", "findings": []}},
        {"role": "REQUIREMENTS_SATISFACTION", "result": {"verdict": "PASS", "findings": []}},
        {
            "role": "ADJUDICATOR",
            "result": [{
                "raw_finding": finding,
                "finding_type": "FACT_GAP",
                "materiality": "BLOCKER",
                "disposition": "FIX_IN_RESEARCH",
            }],
        },
        {
            "role": "CORE_RESEARCHER",
            "result": {
                "base_candidate_hash": controller.canonical_hash(base),
                "replacements": {"research_markdown": corrected_markdown},
            },
        },
        {"role": "INTERNAL_READINESS", "result": {"verdict": "PASS", "findings": []}},
        {"role": "REQUIREMENTS_COVERAGE", "result": {"verdict": "PASS", "findings": []}},
        {"role": "REQUIREMENTS_SATISFACTION", "result": {"verdict": "PASS", "findings": []}},
        {"role": "ADJUDICATOR", "result": []},
    ]
    fixture = write_json(tmp_path / "fixture.json", {"results": results})

    result = research_run.ResearchDriver(args(tmp_path, fixture)).run()
    controller_state = controller.load_state(tmp_path / "run/controller-state.json")
    assert result["verdict"] == "PASS"
    assert len(controller_state["rounds"]) == 2
    assert len(controller_state["candidates"]) == 2
    assert (tmp_path / "package/research.md").read_text(encoding="utf-8") == corrected_markdown
    driver_state = json.loads((tmp_path / "run/driver-state.json").read_text(encoding="utf-8"))
    assert len(driver_state["research_finding_closures"]) == 1
    closure = next(iter(driver_state["research_finding_closures"].values()))
    assert closure["status"] == "VERIFIED_CLOSED"
    assert closure["replacement_candidate_hash"] == closure["verification_candidate_hash"]


def test_unknown_persisted_operation_fails_before_mutation(tmp_path: Path) -> None:
    fixture = write_json(tmp_path / "fixture.json", {"results": []})
    options = args(tmp_path, fixture)
    driver = research_run.ResearchDriver(options)
    driver.state["next_operation"] = "MODEL_AUTHORED_RAW_PATCH"
    driver.persist()
    before = driver.state_path.read_bytes()
    with pytest.raises(research_run.KernelError, match="unregistered persisted operation"):
        research_run.ResearchDriver(options).run()
    assert driver.state_path.read_bytes() == before


def test_single_writer_lock_rejects_concurrent_driver(tmp_path: Path) -> None:
    fixture = write_json(tmp_path / "fixture.json", {"results": passing_results()})
    driver = research_run.ResearchDriver(args(tmp_path, fixture))
    lock_path = tmp_path / "run/driver.lock"
    with lock_path.open("a+b") as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(research_run.KernelError, match="single-writer"):
            driver.run()


def test_terminal_result_is_reconstructed_without_state_mutation(tmp_path: Path) -> None:
    fixture = write_json(tmp_path / "fixture.json", {"results": passing_results()})
    options = args(tmp_path, fixture)
    first = research_run.ResearchDriver(options).run()
    state_path = tmp_path / "run/driver-state.json"
    before = state_path.read_bytes()
    (tmp_path / "run/terminal-result.json").unlink()
    replay = research_run.ResearchDriver(options).run()
    assert replay == first
    assert state_path.read_bytes() == before


def test_terminal_replay_rejects_corrupted_package_artifact(tmp_path: Path) -> None:
    fixture = write_json(tmp_path / "fixture.json", {"results": passing_results()})
    options = args(tmp_path, fixture)
    research_run.ResearchDriver(options).run()
    (tmp_path / "package/research.md").write_text("corrupt", encoding="utf-8")
    with pytest.raises(research_run.KernelError, match="package no longer matches"):
        research_run.ResearchDriver(options).run()


def test_prepared_package_install_reconciles_without_second_write(tmp_path: Path) -> None:
    fixture = write_json(tmp_path / "fixture.json", {"results": passing_results()})
    options = args(tmp_path, fixture)
    driver = research_run.ResearchDriver(options)
    for _ in range(40):
        if driver.state["next_operation"] == research_run.Operation.EMIT_PACKAGE.value:
            break
        driver._dispatch(research_run.Operation(driver.state["next_operation"]))
    else:
        raise AssertionError("driver did not reach package emission")
    context = driver.state["context"]
    candidate_value = context["candidate"]
    key = f"emit:{controller.canonical_hash(candidate_value)}"
    expected_artifacts = driver._expected_artifact_hashes(candidate_value)
    driver.state["journal"][key] = {
        "status": "PREPARED",
        "expected": {
            "target": str(tmp_path / "package"),
            "candidate_hash": controller.canonical_hash(candidate_value),
            "artifact_hashes": expected_artifacts,
        },
    }
    driver.persist()
    controller.emit_package(
        controller.load_state(driver.controller_path),
        tmp_path / "package",
        research_markdown=candidate_value["research_markdown"],
        evidence_index=candidate_value["evidence_index"],
        planner_readiness=candidate_value["planner_readiness_constraints"],
        planner_handoff_markdown=(
            "# Planner handoff\n\n"
            "Implement the validated research findings and readiness obligations exactly.\n"
        ),
    )

    result = research_run.ResearchDriver(options).run()
    state = json.loads(driver.state_path.read_text(encoding="utf-8"))
    assert result["verdict"] == "PASS"
    assert state["journal"][key]["reconciled"] is True


def test_terminal_state_rejects_an_active_slot(tmp_path: Path) -> None:
    fixture = write_json(tmp_path / "fixture.json", {"results": []})
    driver = research_run.ResearchDriver(args(tmp_path, fixture))
    driver._dispatch(research_run.Operation.INITIALIZE_SCOPE)
    terminal = research_run.controller.mutate_file(
        driver.controller_path,
        lambda state: research_run.controller._cap(state, "fixture", None),
    )
    driver._slot_open("held-slot", "held-agent")
    with pytest.raises(research_run.KernelError, match="zero active slots"):
        driver._terminate(terminal)
    close_path = tmp_path / "run/held-close.json"
    controller.atomic_write(close_path, {"status": "failed", "reason": "test cleanup"})
    driver._slot_close("held-slot", "held-agent", close_path, False)


def test_controller_initialization_write_reconciles_after_crash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = write_json(tmp_path / "fixture.json", {"results": []})
    options = args(tmp_path, fixture)
    driver = research_run.ResearchDriver(options)
    initialize = research_run.controller.initialize_file

    def crash_after_write(*values: object, **keywords: object) -> object:
        initialize(*values, **keywords)
        raise RuntimeError("crash after controller write")

    monkeypatch.setattr(research_run.controller, "initialize_file", crash_after_write)
    with pytest.raises(RuntimeError, match="after controller write"):
        driver._dispatch(research_run.Operation.INITIALIZE_SCOPE)
    persisted = json.loads(driver.state_path.read_text(encoding="utf-8"))
    assert persisted["journal"]["initialize:controller"]["status"] == "PREPARED"
    assert driver.controller_path.is_file()

    monkeypatch.setattr(research_run.controller, "initialize_file", initialize)
    resumed = research_run.ResearchDriver(options)
    resumed._dispatch(research_run.Operation.INITIALIZE_SCOPE)
    assert resumed.state["journal"]["initialize:controller"]["status"] == "COMMITTED"
    assert resumed.state["journal"]["initialize:slot-ledger"]["status"] == "COMMITTED"
    assert resumed.state["next_operation"] == research_run.Operation.ADMIT_ROUND.value


def test_slot_ledger_initialization_write_reconciles_after_crash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = write_json(tmp_path / "fixture.json", {"results": []})
    options = args(tmp_path, fixture)
    driver = research_run.ResearchDriver(options)
    run = research_run.subprocess.run

    def crash_after_slot_init(command: list[str], **keywords: object) -> object:
        result = run(command, **keywords)
        if "init" in command and str(driver.slot_path) in command:
            raise RuntimeError("crash after slot-ledger write")
        return result

    monkeypatch.setattr(research_run.subprocess, "run", crash_after_slot_init)
    with pytest.raises(RuntimeError, match="after slot-ledger write"):
        driver._dispatch(research_run.Operation.INITIALIZE_SCOPE)
    persisted = json.loads(driver.state_path.read_text(encoding="utf-8"))
    assert persisted["journal"]["initialize:controller"]["status"] == "COMMITTED"
    assert persisted["journal"]["initialize:slot-ledger"]["status"] == "PREPARED"
    assert driver.slot_path.is_file()

    monkeypatch.setattr(research_run.subprocess, "run", run)
    resumed = research_run.ResearchDriver(options)
    resumed._dispatch(research_run.Operation.INITIALIZE_SCOPE)
    assert resumed.state["journal"]["initialize:slot-ledger"]["status"] == "COMMITTED"
    assert resumed.state["next_operation"] == research_run.Operation.ADMIT_ROUND.value


def test_initial_admission_rejection_caps_authoritative_controller(tmp_path: Path) -> None:
    fixture = write_json(tmp_path / "fixture.json", {"results": []})
    charter_path = tmp_path / "charter.json"
    bounded = charter()
    bounded["budget"]["maximum_agent_spawn_attempts"] = 4
    options = args(tmp_path, fixture)
    write_json(charter_path, bounded)
    driver = research_run.ResearchDriver(options)
    driver._dispatch(research_run.Operation.INITIALIZE_SCOPE)
    driver._dispatch(research_run.Operation.ADMIT_ROUND)
    controller_state = research_run.controller.load_state(driver.controller_path)
    assert controller_state["verdict"] == "CAP_REACHED"
    assert driver.state["context"]["terminal_result"] == controller_state["result"]
    driver._dispatch(research_run.Operation.TERMINATE)


def test_persisted_terminate_cannot_bypass_controller_lifecycle(tmp_path: Path) -> None:
    fixture = write_json(tmp_path / "fixture.json", {"results": []})
    driver = research_run.ResearchDriver(args(tmp_path, fixture))
    driver._dispatch(research_run.Operation.INITIALIZE_SCOPE)
    driver.state["context"] = {
        "terminal_result": {
            "verdict": "CAP_REACHED",
            "reason": "fabricated",
            "candidate_hash": None,
            "envelope_hash": None,
            "actionable_fingerprints": [],
        }
    }
    with pytest.raises(research_run.KernelError, match="authoritative controller terminal"):
        driver._dispatch(research_run.Operation.TERMINATE)


def test_controller_pass_cannot_terminate_before_package_emission(tmp_path: Path) -> None:
    fixture = write_json(tmp_path / "fixture.json", {"results": passing_results()})
    driver = research_run.ResearchDriver(args(tmp_path, fixture))
    for _ in range(40):
        operation = research_run.Operation(driver.state["next_operation"])
        if operation == research_run.Operation.EMIT_PACKAGE:
            break
        driver._dispatch(operation)
    else:
        raise AssertionError("driver did not reach package emission")
    controller_state = research_run.controller.load_state(driver.controller_path)
    assert controller_state["verdict"] == "PASS"
    driver.state["context"]["terminal_result"] = controller_state["result"]
    with pytest.raises(research_run.KernelError, match="committed verified package emission"):
        driver._dispatch(research_run.Operation.TERMINATE)


def test_admitted_lens_retry_reuses_the_original_task_deadline(tmp_path: Path) -> None:
    role, second, third = research_run.controller.LENSES
    fixture = write_json(
        tmp_path / "fixture.json",
        {
            "results": [
                {"role": "CORE_RESEARCHER", "result": candidate()},
                {"role": role, "error": "first lens failed"},
                {"role": second, "result": {"verdict": "PASS", "findings": []}},
                {"role": third, "result": {"verdict": "PASS", "findings": []}},
                {"role": role, "result": {"verdict": "PASS", "findings": []}},
            ]
        },
    )
    driver = research_run.ResearchDriver(args(tmp_path, fixture))
    driver._dispatch(research_run.Operation.INITIALIZE_SCOPE)
    driver._dispatch(research_run.Operation.ADMIT_ROUND)
    driver._dispatch(research_run.Operation.LAUNCH_ROLE)
    driver._dispatch(research_run.Operation.ACCEPT_ROLE_RESULT)
    driver._dispatch(research_run.Operation.REGISTER_CANDIDATE)
    driver._dispatch(research_run.Operation.LAUNCH_ROLE)
    driver._dispatch(research_run.Operation.LAUNCH_ROLE)
    driver._dispatch(research_run.Operation.LAUNCH_ROLE)
    failed = driver.state["leases"][driver.state["context"]["lens_leases"][role]]
    first_deadline = failed["deadline_epoch"]
    driver._dispatch(research_run.Operation.ACCEPT_ROLE_RESULT)
    assert driver.state["context"]["task_deadline_epochs"][f"1:{role}"] == first_deadline
    driver._dispatch(research_run.Operation.LAUNCH_ROLE)
    retried = driver.state["leases"][driver.state["context"]["lens_leases"][role]]
    assert retried["deadline_epoch"] == first_deadline


def test_codex_dispatch_gate_opens_only_after_running_lease_is_persisted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = write_json(tmp_path / "fixture.json", {"results": []})
    driver = research_run.ResearchDriver(args(tmp_path, fixture))
    adapter = research_run.CodexExecAdapter(driver)
    events: list[tuple[str, object]] = []
    original_persist = driver.persist

    def tracked_persist() -> None:
        events.append(("persist", lease["status"]))
        original_persist()

    lease = {"lease_id": "lease-gated", "status": research_run.LeaseStatus.PRELAUNCH.value}
    monkeypatch.setattr(driver, "persist", tracked_persist)
    monkeypatch.setattr(research_run.os, "pipe", lambda: (10, 11))
    monkeypatch.setattr(research_run.os, "fork", lambda: 123)
    monkeypatch.setattr(research_run.os, "close", lambda fd: events.append(("close", fd)))
    monkeypatch.setattr(research_run.os, "write", lambda fd, value: events.append(("write", value)) or 1)

    adapter.start("CORE_RESEARCHER", Path("prompt"), Path("schema"), Path("result"), lease)
    running_persist = events.index(("persist", research_run.LeaseStatus.RUNNING.value))
    gate_write = events.index(("write", b"1"))
    assert running_persist < gate_write
    assert lease["child_pid"] == lease["expected_pgid"] == 123


def test_timeout_refuses_to_signal_a_mismatched_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = write_json(tmp_path / "fixture.json", {"results": []})
    driver = research_run.ResearchDriver(args(tmp_path, fixture))
    adapter = research_run.CodexExecAdapter(driver)
    claim = write_json(tmp_path / "claim.json", {"lease_id": "wrong", "pid": 321, "pgid": 321})
    lease = {
        "lease_id": "expected",
        "child_pid": 321,
        "expected_pgid": 321,
        "deadline_epoch": 0,
        "claim_path": str(claim),
        "temp_result_path": str(tmp_path / "missing-result.json"),
        "lock_path": str(tmp_path / "generation.lock"),
    }
    handle = research_run.RoleHandle("CORE_RESEARCHER", 1, "runtime", "label", "expected", 0.0)
    signals: list[tuple[int, signal.Signals]] = []
    monkeypatch.setattr(research_run.os, "waitpid", lambda pid, flags: (0, 0))
    monkeypatch.setattr(research_run.time, "time", lambda: 1.0)
    monkeypatch.setattr(research_run.os, "killpg", lambda pid, sig: signals.append((pid, sig)))

    with pytest.raises(research_run.KernelError, match="exact generation"):
        adapter.reconcile(handle, lease)
    assert signals == []


def test_resumed_non_parent_commits_valid_result_before_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = write_json(tmp_path / "fixture.json", {"results": []})
    driver = research_run.ResearchDriver(args(tmp_path, fixture))
    adapter = research_run.CodexExecAdapter(driver)
    result_path = write_json(tmp_path / "result.json", candidate())
    exact = {
        "lease_id": "lease",
        "pid": 222,
        "pgid": 222,
        "role": "CORE_RESEARCHER",
        "runtime_agent_id": "runtime",
        "slot_id": "s1",
        "prompt_hash": "p" * 64,
        "schema_hash": "s" * 64,
        "argv_hash": "a" * 64,
    }
    claim_path = write_json(tmp_path / "claim.json", exact)
    lock_path = tmp_path / "generation.lock"
    lock_path.touch()
    lease = {
        "lease_id": "lease",
        "child_pid": 222,
        "expected_pgid": 222,
        "deadline_epoch": 10_000,
        "claim_path": str(claim_path),
        "temp_result_path": str(result_path),
        "lock_path": str(lock_path),
        "role": "CORE_RESEARCHER",
        "runtime_agent_id": "runtime",
        "slot_id": "s1",
        "prompt_hash": "p" * 64,
        "schema_hash": "s" * 64,
        "argv_hash": "a" * 64,
    }
    handle = research_run.RoleHandle("CORE_RESEARCHER", 1, "runtime", "label", "lease", 0.0)
    monkeypatch.setattr(
        research_run.os,
        "waitpid",
        lambda pid, flags: (_ for _ in ()).throw(ChildProcessError()),
    )
    assert adapter.reconcile(handle, lease) == candidate()


def test_resumed_preauthorization_crash_becomes_safe_retryable_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = write_json(tmp_path / "fixture.json", {"results": []})
    driver = research_run.ResearchDriver(args(tmp_path, fixture))
    adapter = research_run.CodexExecAdapter(driver)
    lock_path = tmp_path / "generation.lock"
    lock_path.touch()
    lease = {
        "lease_id": "preauth",
        "child_pid": 333,
        "expected_pgid": 333,
        "deadline_epoch": 10_000,
        "claim_path": str(tmp_path / "missing-claim.json"),
        "temp_result_path": str(tmp_path / "missing-result.json"),
        "lock_path": str(lock_path),
        "role": "CORE_RESEARCHER",
        "runtime_agent_id": "runtime",
        "slot_id": "s1",
        "prompt_hash": "p" * 64,
        "schema_hash": "s" * 64,
        "argv_hash": "a" * 64,
    }
    driver.state["journal"]["launch:preauth"] = {"status": "PREPARED"}
    handle = research_run.RoleHandle("CORE_RESEARCHER", 1, "runtime", "label", "preauth", 0.0)
    monkeypatch.setattr(
        research_run.os,
        "waitpid",
        lambda pid, flags: (_ for _ in ()).throw(ChildProcessError()),
    )
    monkeypatch.setattr(
        research_run.os,
        "kill",
        lambda pid, sig: (_ for _ in ()).throw(ProcessLookupError()),
    )
    with pytest.raises(research_run.KernelError, match="before model invocation"):
        adapter.reconcile(handle, lease)


def test_all_running_lenses_are_enforced_against_one_shared_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = write_json(tmp_path / "fixture.json", {"results": []})
    driver = research_run.ResearchDriver(args(tmp_path, fixture))
    adapter = research_run.CodexExecAdapter(driver)
    leases = {}
    for index, role in enumerate(research_run.controller.LENSES[:2], start=1):
        lease_id = f"lens-{index}"
        identity = {
            "lease_id": lease_id,
            "pid": 400 + index,
            "pgid": 400 + index,
            "role": role,
            "runtime_agent_id": f"runtime-{index}",
            "slot_id": f"s{index}",
            "prompt_hash": f"p{index}",
            "schema_hash": f"schema-{index}",
            "argv_hash": f"argv-{index}",
        }
        claim = write_json(tmp_path / f"claim-{index}.json", identity)
        lease = {
            **{key: value for key, value in identity.items() if key not in {"pid", "pgid"}},
            "child_pid": identity["pid"],
            "expected_pgid": identity["pgid"],
            "status": research_run.LeaseStatus.RUNNING.value,
            "deadline_epoch": 1.0,
            "claim_path": str(claim),
            "lock_path": str(tmp_path / f"lock-{index}"),
        }
        leases[lease_id] = lease
    driver.state["leases"].update(leases)
    driver.state["context"] = {
        "lens_leases": {lease["role"]: lease_id for lease_id, lease in leases.items()}
    }
    signals: list[tuple[int, signal.Signals]] = []
    monkeypatch.setattr(adapter, "_lock_is_held", lambda lease: True)
    monkeypatch.setattr(research_run.os, "killpg", lambda pid, sig: signals.append((pid, sig)))
    adapter._enforce_lens_window(10.0)
    assert signals == [
        (401, signal.SIGTERM),
        (401, signal.SIGKILL),
        (402, signal.SIGTERM),
        (402, signal.SIGKILL),
    ]
    assert all(lease["term_sent_epoch"] == lease["kill_sent_epoch"] == 10.0 for lease in leases.values())


def test_lens_launches_have_independent_task_deadlines(tmp_path: Path) -> None:
    selected = research_run.controller.LENSES[:2]
    fixture = write_json(
        tmp_path / "fixture.json",
        {
            "results": [
                {"role": role, "result": {"verdict": "PASS", "findings": []}}
                for role in selected
            ]
        },
    )
    driver = research_run.ResearchDriver(args(tmp_path, fixture))
    driver._dispatch(research_run.Operation.INITIALIZE_SCOPE)
    driver._dispatch(research_run.Operation.ADMIT_ROUND)
    driver.state["context"]["phase"] = "LENSES"
    handles = [driver._start_role(role) for role in selected]
    deadlines = {
        handle.role: driver.state["leases"][handle.lease_id]["deadline_epoch"]
        for handle in handles
    }
    assert deadlines == {
        role: driver.state["context"]["task_deadline_epochs"][f"1:{role}"]
        for role in selected
    }
    assert set(driver.state["context"]["task_deadline_epochs"]) == {
        f"1:{role}" for role in selected
    }


def test_real_fork_lock_claim_and_exec_path_runs_each_generation_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = tmp_path / "fake-codex"
    candidate_json = json.dumps(candidate())
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "if '--help' in sys.argv:\n"
        "    print('--ephemeral --sandbox --cd --output-schema --output-last-message')\n"
        "    raise SystemExit(0)\n"
        "outer = json.load(sys.stdin)\n"
        "prompt = json.loads(outer['prompt'])\n"
        "role = prompt['role']\n"
        f"candidate = json.loads({candidate_json!r})\n"
        "result = candidate if role == 'CORE_RESEARCHER' else [] if role == 'ADJUDICATOR' "
        "else {'verdict': 'PASS', 'findings': []}\n"
        "count = Path(os.environ['RESEARCH_FAKE_COUNT_DIR']) / role\n"
        "with count.open('a', encoding='utf-8') as handle:\n"
        "    handle.write('1\\n')\n"
        "output = Path(sys.argv[sys.argv.index('--output-last-message') + 1])\n"
        "output.write_text(json.dumps(result), encoding='utf-8')\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    counts = tmp_path / "counts"
    counts.mkdir()
    monkeypatch.setenv("RESEARCH_FAKE_COUNT_DIR", str(counts))
    fixture = write_json(tmp_path / "unused-fixture.json", {"results": []})
    options = args(tmp_path, fixture)
    options.runtime_adapter = "codex"
    options.fixture = None
    options.codex_executable = str(executable)
    options.role_timeout_seconds = 5
    options.termination_grace_seconds = 1

    result = research_run.ResearchDriver(options).run()
    assert result["verdict"] == "PASS"
    assert {path.name: path.read_text(encoding="utf-8") for path in counts.iterdir()} == {
        role: "1\n" for role in research_run.MANDATORY_ROLES
    }
    slots = json.loads((tmp_path / "run/agent-slots.json").read_text(encoding="utf-8"))
    assert all(slot["state"] == "released" for slot in slots["slots"])


def test_term_resistant_worker_and_descendant_are_killed_before_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = tmp_path / "term-resistant-codex"
    candidate_json = json.dumps(candidate())
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, signal, sys, time\n"
        "from pathlib import Path\n"
        "if '--help' in sys.argv:\n"
        "    print('--ephemeral --sandbox --cd --output-schema --output-last-message')\n"
        "    raise SystemExit(0)\n"
        "outer = json.load(sys.stdin)\n"
        "prompt = json.loads(outer['prompt'])\n"
        "role = prompt['role']\n"
        "count = Path(os.environ['RESEARCH_FAKE_COUNT_DIR']) / role\n"
        "attempt = len(count.read_text(encoding='utf-8').splitlines()) + 1 if count.exists() else 1\n"
        "with count.open('a', encoding='utf-8') as handle:\n"
        "    handle.write('1\\n')\n"
        "if role == 'CORE_RESEARCHER' and attempt == 1:\n"
        "    signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "    child = os.fork()\n"
        "    if child == 0:\n"
        "        signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "        while True: time.sleep(1)\n"
        "    while True: time.sleep(1)\n"
        f"candidate = json.loads({candidate_json!r})\n"
        "result = candidate if role == 'CORE_RESEARCHER' else [] if role == 'ADJUDICATOR' "
        "else {'verdict': 'PASS', 'findings': []}\n"
        "output = Path(sys.argv[sys.argv.index('--output-last-message') + 1])\n"
        "output.write_text(json.dumps(result), encoding='utf-8')\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    counts = tmp_path / "counts"
    counts.mkdir()
    monkeypatch.setenv("RESEARCH_FAKE_COUNT_DIR", str(counts))
    fixture = write_json(tmp_path / "unused-fixture.json", {"results": []})
    options = args(tmp_path, fixture)
    options.runtime_adapter = "codex"
    options.fixture = None
    options.codex_executable = str(executable)
    options.role_timeout_seconds = 1
    options.termination_grace_seconds = 1

    result = research_run.ResearchDriver(options).run()
    state = controller.load_state(tmp_path / "run/controller-state.json")
    core_attempts = [item for item in state["attempts"] if item["role"] == "CORE_RESEARCHER"]
    assert result["verdict"] == "CAP_REACHED"
    assert result["reason"] == "TIME_BUDGET"
    assert [item["status"] for item in core_attempts] == ["FAILED"]
    assert (counts / "CORE_RESEARCHER").read_text(encoding="utf-8") == "1\n"


def test_stale_worker_exits_before_claim_or_exec(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = write_json(tmp_path / "fixture.json", {"results": []})
    driver = research_run.ResearchDriver(args(tmp_path, fixture))
    role_dir = tmp_path / "run/roles/stale"
    role_dir.mkdir(parents=True)
    lease = {
        "lease_id": "stale",
        "status": research_run.LeaseStatus.CANCELLED.value,
        "lock_path": str(role_dir / "generation.lock"),
        "claim_path": str(role_dir / "claim.json"),
    }
    driver.state["leases"]["stale"] = lease
    driver.persist()
    exits: list[int] = []

    def stop(code: int) -> None:
        exits.append(code)
        raise SystemExit(code)

    monkeypatch.setattr(research_run.os, "_exit", stop)
    with pytest.raises(SystemExit):
        driver.worker_exec("CORE_RESEARCHER", role_dir / "prompt", role_dir / "schema", role_dir / "result", "stale")
    assert exits == [78]
    assert not Path(lease["claim_path"]).exists()


def test_duplicate_worker_lock_exits_before_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = write_json(tmp_path / "fixture.json", {"results": []})
    driver = research_run.ResearchDriver(args(tmp_path, fixture))
    role_dir = tmp_path / "run/roles/duplicate"
    role_dir.mkdir(parents=True)
    lock_path = role_dir / "generation.lock"
    lock_path.touch()
    lease = {
        "lease_id": "duplicate",
        "status": research_run.LeaseStatus.RUNNING.value,
        "lock_path": str(lock_path),
        "claim_path": str(role_dir / "claim.json"),
    }
    driver.state["leases"]["duplicate"] = lease
    driver.persist()
    exits: list[int] = []

    def stop(code: int) -> None:
        exits.append(code)
        raise SystemExit(code)

    monkeypatch.setattr(research_run.os, "_exit", stop)
    with lock_path.open("r+b") as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(SystemExit):
            driver.worker_exec(
                "CORE_RESEARCHER",
                role_dir / "prompt",
                role_dir / "schema",
                role_dir / "result",
                "duplicate",
            )
    assert exits == [77]
    assert not Path(lease["claim_path"]).exists()


def test_worker_rejects_launch_journal_identity_drift_before_claim_or_exec(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = write_json(
        tmp_path / "fixture.json",
        {"results": [{"role": "CORE_RESEARCHER", "result": candidate()}]},
    )
    driver = research_run.ResearchDriver(args(tmp_path, fixture))
    driver._dispatch(research_run.Operation.INITIALIZE_SCOPE)
    driver._dispatch(research_run.Operation.ADMIT_ROUND)
    handle = driver._start_role("CORE_RESEARCHER")
    lease = driver.state["leases"][handle.lease_id]
    driver.state["journal"][f"launch:{handle.lease_id}"]["prompt_hash"] = "drifted"
    driver.persist()
    exits: list[int] = []

    def stop(code: int) -> None:
        exits.append(code)
        raise SystemExit(code)

    monkeypatch.setattr(research_run.os, "_exit", stop)
    role_dir = Path(lease["temp_result_path"]).parent
    with pytest.raises(SystemExit):
        driver.worker_exec(
            "CORE_RESEARCHER",
            role_dir / "prompt.json",
            role_dir / "schema.json",
            role_dir / "result.json",
            handle.lease_id,
        )
    assert exits == [78]
    assert not Path(lease["claim_path"]).exists()


def test_slot_write_before_driver_commit_reconciles_without_duplicate(tmp_path: Path) -> None:
    fixture = write_json(tmp_path / "fixture.json", {"results": []})
    driver = research_run.ResearchDriver(args(tmp_path, fixture))
    driver._dispatch(research_run.Operation.INITIALIZE_SCOPE)
    label = "prepared-slot"
    completed = research_run.subprocess.run(
        [
            sys.executable,
            str(driver.slot_script),
            "acquire",
            str(driver.slot_path),
            "--label",
            label,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    slot_id = completed.stdout.strip().split()[1]
    key = f"slot:{label}:acquire:reserved"
    driver.state["journal"][key] = {
        "status": "PREPARED",
        "operation": "acquire",
        "label": label,
    }
    driver.persist()
    assert driver.slots.transition("acquire", label=label, expected="reserved") == slot_id
    status = driver.slots._status()
    assert len([slot for slot in status["slots"] if slot["label"] == label]) == 1
    close = tmp_path / "run/prepared-slot-close.json"
    controller.atomic_write(close, {"status": "abandoned", "reason": "test cleanup"})
    research_run.subprocess.run(
        [
            sys.executable,
            str(driver.slot_script),
            "abandon",
            str(driver.slot_path),
            "--label",
            label,
            "--reason",
            "test cleanup",
        ],
        check=True,
    )
    research_run.subprocess.run(
        [sys.executable, str(driver.slot_script), "release", str(driver.slot_path), "--label", label],
        check=True,
    )


def test_committed_slot_transitions_validate_exact_binding_and_allow_successor_replay(
    tmp_path: Path,
) -> None:
    fixture = write_json(tmp_path / "fixture.json", {"results": []})
    driver = research_run.ResearchDriver(args(tmp_path, fixture))
    driver._dispatch(research_run.Operation.INITIALIZE_SCOPE)
    label = "replay-slot"
    runtime_id = "replay-agent"
    driver._slot_open(label, runtime_id)
    close = tmp_path / "run/replay-close.json"
    research_run.controller.atomic_write(close, {"status": "completed"})
    driver._slot_close(label, runtime_id, close, True)
    driver._slot_close(label, runtime_id, close, True)
    ledger = json.loads(driver.slot_path.read_text(encoding="utf-8"))
    ledger["slots"][0]["agent_id"] = "different-agent"
    research_run.controller.atomic_write(driver.slot_path, ledger)
    with pytest.raises(research_run.KernelError, match="different runtime agent"):
        driver.slots.transition(
            "release",
            label=label,
            expected="released",
            runtime_agent_id=runtime_id,
        )


def test_prepared_slot_transition_rejects_conflicting_ledger_state(tmp_path: Path) -> None:
    fixture = write_json(tmp_path / "fixture.json", {"results": []})
    driver = research_run.ResearchDriver(args(tmp_path, fixture))
    driver._dispatch(research_run.Operation.INITIALIZE_SCOPE)
    label = "conflict-slot"
    driver.slots.transition("acquire", label=label, expected="reserved")
    driver.state["journal"][f"slot:{label}:release:released"] = {
        "status": "PREPARED",
        "operation": "release",
        "label": label,
        "expected": "released",
        "runtime_agent_id": None,
    }
    driver.persist()
    with pytest.raises(research_run.KernelError, match="conflicting pre-state"):
        driver.slots.transition("release", label=label, expected="released")


def test_prompt_uses_frozen_controller_inputs_after_source_files_change(tmp_path: Path) -> None:
    fixture = write_json(tmp_path / "fixture.json", {"results": []})
    options = args(tmp_path, fixture)
    driver = research_run.ResearchDriver(options)
    driver._dispatch(research_run.Operation.INITIALIZE_SCOPE)
    driver._dispatch(research_run.Operation.ADMIT_ROUND)
    frozen = research_run.controller.load_state(driver.controller_path)["charter"]
    write_json(Path(options.charter), {"objective": "mutated after admission"})
    prompt = json.loads(
        driver._prompt_for("CORE_RESEARCHER", 1, None, [])
    )
    assert prompt["charter"] == frozen


def test_successful_result_timestamp_excludes_resume_downtime_from_role_metric(tmp_path: Path) -> None:
    fixture = write_json(tmp_path / "fixture.json", {"results": []})
    driver = research_run.ResearchDriver(args(tmp_path, fixture), clock=lambda: 10_000.0)
    result = write_json(tmp_path / "result.json", candidate())
    os.utime(result, (105.0, 105.0))
    lease = {
        "role": "CORE_RESEARCHER",
        "round": 1,
        "temp_result_path": str(result),
        "started_monotonic": 10.0,
        "started_epoch": 100.0,
    }
    driver._close_role_interval(lease)
    assert driver.state["metrics"]["role_intervals"] == [[10.0, 15.0]]


def test_controlled_effectiveness_fixture_persists_ratio_at_or_below_ten_percent(
    tmp_path: Path,
) -> None:
    class Clock:
        def __init__(self) -> None:
            self.value = 0.0

        def __call__(self) -> float:
            return self.value

        def advance(self, seconds: float) -> None:
            self.value += seconds

    fixture = write_json(tmp_path / "fixture.json", {"results": passing_results()})
    clock = Clock()
    driver = research_run.ResearchDriver(args(tmp_path, fixture), clock=clock)
    original_reconcile = driver.adapter.reconcile

    def reconcile(handle: object, lease: object) -> object:
        clock.advance(100.0)
        return original_reconcile(handle, lease)

    driver.adapter.reconcile = reconcile
    result = driver.run()
    metrics = json.loads(Path(result["metrics_path"]).read_text(encoding="utf-8"))
    assert metrics["mechanical_seconds"] >= 0
    assert metrics["total_seconds"] == metrics["mechanical_seconds"] + metrics["role_active_seconds"]
    assert metrics["mechanical_ratio"] <= 0.10
    assert {
        "registered_dispatch",
        "role_duration",
        "mechanical_duration",
        "run_completion",
    } <= {event["event"] for event in metrics["events"]}


def test_frozen_resume_token_rejects_mismatch_before_mutation(tmp_path: Path) -> None:
    fixture = write_json(tmp_path / "fixture.json", {"results": []})
    options = args(tmp_path, fixture)
    research_run.ResearchDriver(options)
    before = (tmp_path / "run/driver-state.json").read_bytes()
    options.resume_token = "different"
    with pytest.raises(research_run.KernelError, match="frozen run"):
        research_run.ResearchDriver(options)
    assert (tmp_path / "run/driver-state.json").read_bytes() == before


@pytest.mark.parametrize(
    ("field", "changed"),
    [
        ("model", "different-model"),
        ("role_timeout_seconds", 601),
        ("termination_grace_seconds", 6),
        ("output_directory", "different-package"),
    ],
)
def test_frozen_execution_contract_rejects_mismatch_before_mutation(
    tmp_path: Path,
    field: str,
    changed: object,
) -> None:
    fixture = write_json(tmp_path / "fixture.json", {"results": []})
    options = args(tmp_path, fixture)
    research_run.ResearchDriver(options)
    state_path = tmp_path / "run/driver-state.json"
    before = state_path.read_bytes()
    if field == "output_directory":
        changed = str(tmp_path / str(changed))
    setattr(options, field, changed)
    with pytest.raises(research_run.KernelError, match="frozen run"):
        research_run.ResearchDriver(options)
    assert state_path.read_bytes() == before


def test_persisted_adapter_config_tampering_is_rejected(tmp_path: Path) -> None:
    fixture = write_json(tmp_path / "fixture.json", {"results": []})
    options = args(tmp_path, fixture)
    driver = research_run.ResearchDriver(options)
    tampered = json.loads(driver.state_path.read_text(encoding="utf-8"))
    tampered["config"]["model"] = "tampered-model"
    controller.atomic_write(driver.state_path, tampered)
    with pytest.raises(research_run.KernelError, match="frozen run"):
        research_run.ResearchDriver(options)
