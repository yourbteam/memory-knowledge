from __future__ import annotations

import json
import importlib.util
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
LEDGER = ROOT / "skills/_shared/verification_ledger.py"
CONVERGENCE = ROOT / "skills/_shared/convergence_state.py"
HELPERS_PATH = ROOT / "tests/test_plan_playbook_v2.py"
HELPERS_SPEC = importlib.util.spec_from_file_location("plan_v2_test_helpers", HELPERS_PATH)
assert HELPERS_SPEC is not None and HELPERS_SPEC.loader is not None
HELPERS = importlib.util.module_from_spec(HELPERS_SPEC)
HELPERS_SPEC.loader.exec_module(HELPERS)

PLAN_PACKAGE = HELPERS.PLAN_PACKAGE
SUCCESS_FIELDS = HELPERS.SUCCESS_FIELDS
canonical_bytes = HELPERS.canonical_bytes
behavior_matrix = HELPERS.behavior_matrix
direct_workspace = HELPERS.direct_workspace
init_direct = HELPERS.init_direct
run_controller = HELPERS.run_controller
sha256_bytes = HELPERS.sha256_bytes
write_json = HELPERS.write_json
STAGES = (
    "VERIFY_PLAN",
    "INTERNAL_READINESS",
    "REQUIREMENTS_COVERAGE",
    "REQUIREMENTS_SATISFACTION",
)


def _snapshot(run_root: Path, kind: str, suffix: str, payload: bytes) -> str:
    digest = sha256_bytes(payload)
    target = run_root / "snapshots" / kind / f"{digest}.{suffix}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return digest


def _make_emittable(tmp_path: Path) -> dict:
    workspace = direct_workspace(tmp_path)
    state = init_direct(workspace)
    run_root = Path(state["run_root"])

    plan = b"# Grounded plan\n\nImplement and verify the fixture boundary.\n"
    plan_sha = _snapshot(run_root, "plan", "md", plan)
    surface = {
        "schema_version": 1,
        "items": [
            {
                "id": "S1",
                "requirement_ids": ["R1"],
                "obligation_ids": ["P1"],
                "subsystem": "fixture",
                "files": [{"repository_key": "fixture", "path": "source.txt"}],
                "entry_points": ["source.txt"],
                "contracts": ["fixture source contract"],
                "implementation_steps": ["Update the fixture-owned source boundary."],
                "verification_steps": ["Run the focused fixture test."],
                "risk": "low",
                "evidence_ids": ["E1"],
                "status": "PLANNED",
            }
        ],
        "behavior_matrix": behavior_matrix(),
        "implementation_approval": {
            "granular_changes": [
                {
                    "id": "C1",
                    "repositories": ["fixture"],
                    "allowed_paths": ["source.txt"],
                    "change": "Update the fixture-owned source boundary.",
                }
            ],
            "practical_consequence": {
                "before": "The fixture is unchanged.",
                "after": "The planned fixture behavior is implemented.",
            },
            "estimated_cost": {
                "implementation_effort": "small",
                "verification_effort": "small",
                "complexity": "low",
                "note": "One local source and focused test.",
            },
        },
    }
    decisions = {"schema_version": 1, "decisions": []}
    surface_sha = _snapshot(run_root, "surface-map", "json", canonical_bytes(surface))
    decisions_sha = _snapshot(run_root, "decisions", "json", canonical_bytes(decisions))

    ledger_path = tmp_path / "verification-ledger.json"
    subprocess.run(
        [
            "python3",
            str(LEDGER),
            "init",
            "--kind",
            "plan",
            "--target",
            "plan.md",
            "--plan-sha256",
            plan_sha,
            "--evidence-revision-sha256",
            state["evidence_index_sha256"],
            "--output",
            str(ledger_path),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger_sha = _snapshot(run_root, "verification-ledger", "json", canonical_bytes(ledger))

    revision_basis = {
        "schema_version": 1,
        "package_id": state["package_id"],
        "revision": 1,
        "profile": state["profile"],
        "evidence_index_sha256": state["evidence_index_sha256"],
        "plan_sha256": plan_sha,
        "surface_map_sha256": surface_sha,
        "decisions_sha256": decisions_sha,
        "verification_ledger_sha256": ledger_sha,
    }
    receipt = {
        **revision_basis,
        "plan_snapshot_path": f"snapshots/plan/{plan_sha}.md",
        "revision_basis_sha256": sha256_bytes(canonical_bytes(revision_basis)),
        "predecessor_receipt_sha256": None,
        "published_at_utc": "2026-07-19T00:00:00Z",
    }
    receipt_payload = canonical_bytes(receipt)
    receipt_sha = sha256_bytes(receipt_payload)
    receipt_relative = f"revisions/1-{receipt_sha}.json"
    receipt_path = run_root / receipt_relative
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_bytes(receipt_payload)

    state.update(
        status="READY",
        revision=1,
        plan_sha256=plan_sha,
        surface_map_sha256=surface_sha,
        decisions_sha256=decisions_sha,
        verification_ledger_sha256=ledger_sha,
        stage_results=[
            {
                "round": 1,
                "stage": stage,
                "terminal_verdict": "PASS",
            }
            for stage in STAGES
        ],
        revision_history=[
            {
                "revision": 1,
                "receipt_path": receipt_relative,
                "receipt_sha256": receipt_sha,
            }
        ],
    )
    workspace["state"].write_bytes(canonical_bytes(state))
    workspace.update(
        plan_bytes=plan,
        surface=surface,
        decisions=decisions,
        ledger=ledger,
    )
    return workspace


def _emit(workspace: dict) -> dict:
    _result, payload = run_controller(
        "emit-package", workspace["state"], workspace["task_root"]
    )
    assert set(payload) == SUCCESS_FIELDS
    assert payload["status"] == "EMITTED"
    return json.loads(workspace["state"].read_text(encoding="utf-8"))


def _outer_state(tmp_path: Path, workspace: dict, *, blocked: bool = False) -> Path:
    inner = json.loads(workspace["state"].read_text(encoding="utf-8"))
    requirements = [
        {"id": row["id"], "text": row["text"], "source": row["source"]}
        for row in inner["requirements"]
    ]
    requirements_path = write_json(tmp_path / "outer-requirements.json", requirements)
    source = tmp_path / "outer-source.txt"
    source.write_text("planner-v2 test source\n", encoding="utf-8")
    outer = tmp_path / "outer-state.json"
    base = ["python3", str(CONVERGENCE)]
    subprocess.run(base + ["init", str(outer), "--source", str(source), "--objective", "planner-v2 adapter", "--requirements-file", str(requirements_path)], cwd=ROOT, check=True, capture_output=True, text=True)
    managed = tmp_path / "outer-managed"
    managed.mkdir()
    (managed / "baseline.txt").write_text("baseline\n", encoding="utf-8")
    subprocess.run(base + ["init-baseline", str(outer), "--managed-path", str(managed)], cwd=ROOT, check=True, capture_output=True, text=True)
    subprocess.run(base + ["transition", str(outer), "--to", "plan"], cwd=ROOT, check=True, capture_output=True, text=True)
    if blocked:
        data = json.loads(outer.read_text(encoding="utf-8"))
        data.update(status="blocked", blocked_from_status="plan", blocked_stage="plan")
        outer.write_bytes(canonical_bytes(data))
    return outer


def _adapter(workspace: dict, outer: Path, out: Path) -> dict:
    run_controller(
        "stage-result",
        workspace["state"],
        "--convergence-state",
        outer,
        "--package-directory",
        workspace["task_root"],
        "--out",
        out,
    )
    return json.loads(out.read_text(encoding="utf-8"))


def _record_outer(outer: Path, result: Path) -> dict:
    subprocess.run(
        ["python3", str(CONVERGENCE), "record-stage", str(outer), "--result-file", str(result)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(outer.read_text(encoding="utf-8"))


def _crash_emit(workspace: dict, phase: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PLAN_PLAYBOOK_V2_TEST_CRASH_AFTER"] = phase
    return subprocess.run(
        [
            "python3",
            str(ROOT / "skills/plan-playbook/scripts/plan_package.py"),
            "emit-package",
            str(workspace["state"]),
            str(workspace["task_root"]),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )


def _authorize(workspace: dict) -> Path:
    state = json.loads(workspace["state"].read_text(encoding="utf-8"))
    request = Path(state["run_root"]) / f"authorizations/implementation-request-r{state['revision']}.json"
    run_controller(
        "prepare-implementation-authorization",
        workspace["state"],
        "--out",
        request,
    )
    request_data = json.loads(request.read_text(encoding="utf-8"))
    response = request.with_name("exact-response.txt")
    response.write_text(request_data["required_confirmation"], encoding="utf-8")
    run_controller(
        "record-implementation-authorization",
        workspace["state"],
        "--request",
        request,
        "--approval-response",
        response,
    )
    state = json.loads(workspace["state"].read_text(encoding="utf-8"))
    return Path(state["run_root"]) / state["implementation_authorization_path"]


def test_initial_content_bound_ledger_can_be_recorded_before_first_attempt(
    tmp_path: Path,
) -> None:
    workspace, state = HELPERS.drafted_workspace(tmp_path)
    plan_path = tmp_path / "plan.md"
    plan_path.write_bytes(b"# Plan\n\nGrounded fixture plan.\n")
    ledger_path = tmp_path / "populated-ledger.json"
    subprocess.run(
        [
            "python3",
            str(LEDGER),
            "init",
            "--kind",
            "plan",
            "--target",
            "plan.md",
            "--plan-sha256",
            state["plan_sha256"],
            "--evidence-revision-sha256",
            state["evidence_index_sha256"],
            "--output",
            str(ledger_path),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    _result, payload = run_controller(
        "record-verification-ledger",
        workspace["state"],
        "--ledger",
        ledger_path,
        "--expected-current-sha256",
        state["verification_ledger_sha256"],
    )

    updated = json.loads(workspace["state"].read_text(encoding="utf-8"))
    assert payload["code"] == "VERIFICATION_LEDGER_RECORDED"
    assert updated["status"] == "DRAFTED"
    assert updated["attempts"] == []
    assert updated["budgets"]["used_agent_attempts"] == 0
    assert updated["verification_ledger_sha256"] != state["verification_ledger_sha256"]

    run_controller("show", workspace["state"])
    recorded_state = workspace["state"].read_bytes()
    run_controller(
        "record-verification-ledger",
        workspace["state"],
        "--ledger",
        ledger_path,
        "--expected-current-sha256",
        updated["verification_ledger_sha256"],
    )
    assert workspace["state"].read_bytes() == recorded_state


def test_emit_package_rejects_tamper_and_exact_current_state_replay_is_idempotent(
    tmp_path: Path,
) -> None:
    workspace = _make_emittable(tmp_path)
    emitted = _emit(workspace)
    manifest = workspace["task_root"] / "manifest.json"
    assert manifest.is_file()
    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    assert manifest_data["revision"] == emitted["revision"]
    assert manifest_data["owned_files"]

    plan_path = workspace["task_root"] / "plan.md"
    original_plan = plan_path.read_bytes()
    plan_path.write_bytes(original_plan + b"tamper\n")
    before = workspace["state"].read_bytes()
    _result, rejected = run_controller(
        "validate-package", workspace["task_root"], ok=False
    )
    assert rejected["ok"] is False
    assert workspace["state"].read_bytes() == before
    plan_path.write_bytes(original_plan)

    first_manifest = manifest.read_bytes()
    first_state = workspace["state"].read_bytes()
    _result, replay = run_controller(
        "emit-package", workspace["state"], workspace["task_root"]
    )
    assert replay["code"] == "PACKAGE_EMITTED"
    assert manifest.read_bytes() == first_manifest
    assert workspace["state"].read_bytes() == first_state


def test_validate_package_accepts_hashed_non_reserved_owned_file(
    tmp_path: Path,
) -> None:
    workspace = _make_emittable(tmp_path)
    _emit(workspace)
    portable_asset = workspace["task_root"] / "source-snapshots" / "fixture.txt"
    portable_asset.parent.mkdir(parents=True)
    portable_asset.write_bytes(b"portable evidence\n")

    manifest_path = workspace["task_root"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["owned_files"].append(
        {
            "path": "source-snapshots/fixture.txt",
            "sha256": sha256_bytes(portable_asset.read_bytes()),
        }
    )
    manifest["owned_files"].sort(key=lambda row: row["path"])
    manifest_path.write_bytes(canonical_bytes(manifest))

    _result, validated = run_controller(
        "validate-package", workspace["task_root"]
    )
    assert validated["valid"] is True
    assert validated["owned_files"] == manifest["owned_files"]


def test_emission_transaction_installs_nested_owned_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _make_emittable(tmp_path)
    state = json.loads(workspace["state"].read_text(encoding="utf-8"))
    original_package_files_for = PLAN_PACKAGE.package_files_for

    def package_files_with_nested_asset(state_, task_root_, run_root_):
        files = original_package_files_for(state_, task_root_, run_root_)
        files["source-snapshots/fixture.txt"] = b"portable evidence\n"
        return files

    monkeypatch.setattr(
        PLAN_PACKAGE,
        "package_files_for",
        package_files_with_nested_asset,
    )
    receipt, journal = PLAN_PACKAGE.run_emission_transaction(
        state,
        workspace["task_root"],
        Path(state["run_root"]),
    )

    assert journal["state"] == "MANIFEST_PUBLISHED"
    assert receipt["valid"] is True
    assert (
        workspace["task_root"] / "source-snapshots" / "fixture.txt"
    ).read_bytes() == b"portable evidence\n"


def test_stage_result_direct_pass_binds_current_package_and_real_consumer(tmp_path: Path) -> None:
    workspace = _make_emittable(tmp_path)
    _emit(workspace)
    outer = _outer_state(tmp_path, workspace)
    result = tmp_path / "stage-result.json"
    payload = _adapter(workspace, outer, result)
    assert payload["verdict"] == "PASS"
    assert payload["artifact_paths"] == [str(workspace["task_root"] / "manifest.json")]
    first = _record_outer(outer, result)
    assert first["stages"]["plan:1:1"]["verdict"] == "PASS"
    assert _record_outer(outer, result) == first

    controller = json.loads(workspace["state"].read_text(encoding="utf-8"))
    controller["stage_results"][0]["round"] = 2
    workspace["state"].write_bytes(canonical_bytes(controller))
    _result, rejected = run_controller(
        "stage-result",
        workspace["state"],
        "--convergence-state",
        outer,
        "--package-directory",
        workspace["task_root"],
        "--out",
        tmp_path / "stale-stage-result.json",
        ok=False,
    )
    assert rejected["code"] == "PACKAGE_STATE_MISMATCH"


def test_stage_result_advances_blocked_pass_one_edge_per_real_attempt(tmp_path: Path) -> None:
    workspace = _make_emittable(tmp_path)
    controller = json.loads(workspace["state"].read_text(encoding="utf-8"))
    controller["blockers"] = [{"id":"B1","type":"RUNTIME","practical_impact":"Planning could not complete.","evidence":["controller evidence"],"required_resolution":"Restore the planning boundary.","status":"RESOLVED","resolution":{"receipt":"controller-resolution"}}]
    workspace["state"].write_bytes(canonical_bytes(controller))
    _emit(workspace)
    outer = _outer_state(tmp_path, workspace, blocked=True)
    outer_data = json.loads(outer.read_text(encoding="utf-8"))
    outer_data["blockers"]["B1"] = {"id":"B1","stage":"plan","status":"open","type":"execution","reason":"Planning could not complete.","required_evidence":"Restore the planning boundary."}
    outer.write_bytes(canonical_bytes(outer_data))

    expected = [
        ("fixed-awaiting-verification", "BLOCKED"),
        ("verified", "BLOCKED"),
        ("closed", "PASS"),
    ]
    for attempt, (blocker_status, verdict) in enumerate(expected, start=1):
        result = tmp_path / f"stage-result-{attempt}.json"
        payload = _adapter(workspace, outer, result)
        assert payload["attempt"] == attempt
        assert payload["verdict"] == verdict
        current = _record_outer(outer, result)
        assert current["blockers"]["B1"]["status"] == blocker_status
    assert payload["evidence"][-1] == "resume-anchor:B1"


@pytest.mark.parametrize(
    "phase",
    [
        "PREPARING",
        "PARTIAL_STAGING",
        "PREPARED",
        "OLD_BACKED_UP",
        "NEW_INSTALLED",
        "MANIFEST_PUBLISHING",
        "MANIFEST_PUBLISHED",
        "STATE_COMMITTED",
    ],
)
def test_emit_package_recovers_every_durable_transaction_phase(
    tmp_path: Path, phase: str
) -> None:
    workspace = _make_emittable(tmp_path)
    sibling = workspace["task_root"] / "analysis.md"
    sibling.write_text("caller-owned sibling\n", encoding="utf-8")
    prior_plan = workspace["task_root"] / "plan.md"
    prior_plan.write_text("prior root plan\n", encoding="utf-8")

    crashed = _crash_emit(workspace, phase)
    assert crashed.returncode == 86, (crashed.stdout, crashed.stderr)
    journal_path = workspace["task_root"] / ".plan-package-transaction.json"
    assert journal_path.is_file()
    retained_timestamp = json.loads(journal_path.read_text(encoding="utf-8"))["emitted_at_utc"]

    emitted = _emit(workspace)
    manifest = json.loads((workspace["task_root"] / "manifest.json").read_text(encoding="utf-8"))
    assert emitted["emission_history"][-1]["emitted_at_utc"] == retained_timestamp
    assert manifest["emitted_at_utc"] == retained_timestamp
    assert sibling.read_text(encoding="utf-8") == "caller-owned sibling\n"
    assert not journal_path.exists()
    assert not (workspace["task_root"] / ".plan-package-staging").exists()
    assert not (workspace["task_root"] / ".plan-package-backup").exists()


def test_emit_package_rejects_foreign_partial_staging_without_root_mutation(tmp_path: Path) -> None:
    workspace = _make_emittable(tmp_path)
    prior_plan = workspace["task_root"] / "plan.md"
    prior_plan.write_text("prior root plan\n", encoding="utf-8")
    crashed = _crash_emit(workspace, "PARTIAL_STAGING")
    assert crashed.returncode == 86
    journal = json.loads((workspace["task_root"] / ".plan-package-transaction.json").read_text(encoding="utf-8"))
    staged = workspace["task_root"] / journal["staging_path"]
    (staged / "foreign.txt").write_text("foreign\n", encoding="utf-8")
    before_state = workspace["state"].read_bytes()
    _result, rejected = run_controller(
        "emit-package", workspace["state"], workspace["task_root"], ok=False
    )
    assert rejected["code"] == "EMISSION_STAGING_CONFLICT"
    assert workspace["state"].read_bytes() == before_state
    assert prior_plan.read_text(encoding="utf-8") == "prior root plan\n"


def test_resume_bundle_path_manifest_tamper_and_replay_are_fail_closed(
    tmp_path: Path,
) -> None:
    workspace = direct_workspace(tmp_path)
    state = init_direct(workspace)
    blocker = {
        "id": "blocker-fixture",
        "type": "EVIDENCE",
        "practical_impact": "Planning is paused.",
        "evidence": ["fixture"],
        "required_resolution": "Bind the fixture evidence.",
        "status": "OPEN",
        "resolution": None,
    }
    state.update(status="BLOCKED", blockers=[blocker])
    workspace["state"].write_bytes(canonical_bytes(state))
    blocked_sha = sha256_bytes(workspace["state"].read_bytes())
    bundle = Path(state["run_root"]) / "resume" / blocked_sha / "bundle"
    resolution = write_json(
        tmp_path / "resolution.json",
        {
            "schema_version": 1,
            "blocked_state_sha256": blocked_sha,
            "resolutions": [{"blocker_id": blocker["id"], "type": "EVIDENCE"}],
        },
    )

    run_controller(
        "prepare-resume-bundle",
        workspace["state"],
        "--evidence-index",
        workspace["evidence_path"],
        "--resolution-evidence",
        resolution,
        "--bundle-dir",
        bundle,
    )
    first_tree = {
        p.relative_to(bundle).as_posix(): p.read_bytes()
        for p in bundle.rglob("*")
        if p.is_file()
    }
    replay_result, _replay = run_controller(
        "prepare-resume-bundle",
        workspace["state"],
        "--evidence-index",
        workspace["evidence_path"],
        "--resolution-evidence",
        resolution,
        "--bundle-dir",
        bundle,
        ok=None,
    )
    replay_tree = {
        p.relative_to(bundle).as_posix(): p.read_bytes()
        for p in bundle.rglob("*")
        if p.is_file()
    }

    manifest = bundle / "resume-bundle.json"
    changed = json.loads(manifest.read_text(encoding="utf-8"))
    changed["unknown"] = True
    manifest.write_bytes(canonical_bytes(changed))
    before = workspace["state"].read_bytes()
    resume_result, rejected = run_controller(
        "resume", workspace["state"], "--resume-bundle", bundle, ok=None
    )
    failures = []
    if replay_result.returncode != 0 or replay_tree != first_tree:
        failures.append("exact resume-bundle replay was not byte-identical and successful")
    if resume_result.returncode == 0 or rejected["ok"] is not False:
        failures.append("tampered resume manifest was accepted")
    if workspace["state"].read_bytes() != before:
        failures.append("tampered resume mutated controller state")
    assert not failures, "; ".join(failures)


def test_ordinary_implementation_request_requires_exact_approval_and_denies_ambiguity(
    tmp_path: Path,
) -> None:
    workspace = _make_emittable(tmp_path)
    state = _emit(workspace)
    request = Path(state["run_root"]) / f"authorizations/implementation-request-r{state['revision']}.json"
    run_controller(
        "prepare-implementation-authorization",
        workspace["state"],
        "--out",
        request,
    )
    request_data = json.loads(request.read_text(encoding="utf-8"))
    ambiguous = request.with_name("ambiguous-response.txt")
    ambiguous.write_text("approved", encoding="utf-8")
    before = workspace["state"].read_bytes()
    _result, denied = run_controller(
        "record-implementation-authorization",
        workspace["state"],
        "--request",
        request,
        "--approval-response",
        ambiguous,
        ok=False,
    )
    assert denied["code"] == "APPROVAL_DENIED"
    assert workspace["state"].read_bytes() == before

    exact = request.with_name("exact-response.txt")
    exact.write_text(request_data["required_confirmation"], encoding="utf-8")
    run_controller(
        "record-implementation-authorization",
        workspace["state"],
        "--request",
        request,
        "--approval-response",
        exact,
    )
    authorized = json.loads(workspace["state"].read_text(encoding="utf-8"))
    assert authorized["implementation_approval_status"] == "AUTHORIZED"


def test_revision_invalidates_prior_package_and_implementation_authorization(
    tmp_path: Path,
) -> None:
    workspace = _make_emittable(tmp_path)
    _emit(workspace)
    old_authorization = _authorize(workspace)
    old_manifest = (workspace["task_root"] / "manifest.json").read_bytes()
    state = json.loads(workspace["state"].read_text(encoding="utf-8"))
    proposal = Path(state["run_root"]) / "proposed-revisions" / "2"
    run_controller("prepare-revision", workspace["state"])
    (proposal / "plan.md").write_text(
        "# Revised grounded plan\n\nImplement and verify the corrected boundary.\n",
        encoding="utf-8",
    )
    revised_plan_sha = sha256_bytes((proposal / "plan.md").read_bytes())
    revised_ledger = tmp_path / "revised-verification-ledger.json"
    subprocess.run(
        [
            "python3",
            str(LEDGER),
            "init",
            "--kind",
            "plan",
            "--target",
            "plan.md",
            "--plan-sha256",
            revised_plan_sha,
            "--evidence-revision-sha256",
            state["evidence_index_sha256"],
            "--output",
            str(revised_ledger),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    (proposal / "verification-ledger.json").write_bytes(revised_ledger.read_bytes())
    run_controller("record-revision", workspace["state"], "--proposal", proposal)

    revised = json.loads(workspace["state"].read_text(encoding="utf-8"))
    assert revised["status"] == "DRAFTED"
    assert revised["revision"] == 2
    assert revised["implementation_approval_status"] == "NOT_REQUESTED"
    assert revised["implementation_authorization_path"] is None
    assert (workspace["task_root"] / ".plan-package-invalidated.json").is_file()
    assert (workspace["task_root"] / "manifest.json").read_bytes() == old_manifest

    _result, package_rejected = run_controller(
        "validate-package", workspace["task_root"], ok=False
    )
    assert package_rejected["code"] == "PACKAGE_INVALIDATED"
    _result, authorization_rejected = run_controller(
        "validate-implementation-authorization",
        workspace["state"],
        "--authorization",
        old_authorization,
        ok=False,
    )
    assert authorization_rejected["code"] == "IMPLEMENTATION_NOT_AUTHORIZED"
