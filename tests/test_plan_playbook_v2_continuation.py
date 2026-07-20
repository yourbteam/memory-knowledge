from __future__ import annotations

import importlib.util
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).parents[1]
SHARED = ROOT / "skills/_shared/convergence_state.py"
HELPERS_PATH = ROOT / "tests/test_plan_playbook_v2_authority.py"
SPEC = importlib.util.spec_from_file_location("plan_v2_continuation_helpers", HELPERS_PATH)
assert SPEC is not None and SPEC.loader is not None
HELPERS = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(HELPERS)


def test_convergence_continuation_round_trip_is_bound_and_replay_safe(tmp_path: Path) -> None:
    workspace = HELPERS._workspace(tmp_path)
    workspace["charter"]["change_characteristics"] = ["ROLLOUT"]
    HELPERS.write_json(workspace["charter_path"], workspace["charter"])
    outer_dir = tmp_path / "outer"; outer_dir.mkdir()
    outer_path = HELPERS.write_json(outer_dir / "state.json", HELPERS._outer_state(workspace))
    state = HELPERS._draft(workspace, convergence_state=outer_path)
    assert state["profile"] == "SUBSTANTIAL"

    state.update(
        status="CAP_REACHED", cap_reason="VERIFY_PLAN_ITERATION_LIMIT",
        cap_reached_at_utc=state["started_at_utc"], cap_stage="VERIFY_PLAN",
        cap_completed_verification_iteration=10,
    )
    workspace["state"].write_bytes(HELPERS.canonical_bytes(state))
    inner_sha = HELPERS.sha256_bytes(workspace["state"].read_bytes())

    outer = json.loads(outer_path.read_text())
    outer.update(status="cap_reached", cap_stage="plan", cap_attempt=1, cap_from_status="plan")
    outer_path.write_text(json.dumps(outer), encoding="utf-8")
    approval_id = "continue-plan"
    subprocess.run(
        ["python3", str(SHARED), "grant-plan-continuation", str(outer_path), "--id", approval_id,
         "--plan-package-id", state["package_id"], "--inner-state-sha256", inner_sha,
         "--plan-sha256", state["plan_sha256"], "--approved-from-iteration", "10",
         "--approved-through-iteration", "20", "--approval-evidence", "bounded convergence approval"],
        check=True, capture_output=True, text=True,
    )
    subprocess.run(
        ["python3", str(SHARED), "continue-stage", str(outer_path), "--stage", "plan",
         "--approval-id", approval_id, "--operation-id", "continue-operation"],
        check=True, capture_output=True, text=True,
    )

    approval_path = Path(state["run_root"]) / "approvals/verify-plan-continuation-i10.json"
    args = (
        "prepare-continuation-approval", workspace["state"], "--convergence-state", outer_path,
        "--outer-approval-id", approval_id, "--outer-operation-id", "continue-operation",
        "--out", approval_path,
    )
    HELPERS.run_controller(*args)
    approval_bytes = approval_path.read_bytes()
    provenance_bytes = approval_path.with_suffix(".provenance.json").read_bytes()
    HELPERS.run_controller(*args)
    assert approval_path.read_bytes() == approval_bytes
    assert approval_path.with_suffix(".provenance.json").read_bytes() == provenance_bytes

    HELPERS.run_controller("continue-hardening", workspace["state"], "--approval", approval_path)
    continued = json.loads(workspace["state"].read_text())
    assert continued["status"] == "HARDENING"
    assert continued["budgets"]["verify_plan_iteration_limit"] == 20
    assert continued["budgets"]["max_agent_attempts"] == 43
    assert continued["budgets"]["continuation_approval_sha256"] == HELPERS.sha256_bytes(approval_bytes)
    stable = workspace["state"].read_bytes()
    HELPERS.run_controller("continue-hardening", workspace["state"], "--approval", approval_path)
    assert workspace["state"].read_bytes() == stable
