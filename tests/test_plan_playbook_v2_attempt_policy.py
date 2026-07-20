from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
HELPERS_PATH = ROOT / "tests/test_plan_playbook_v2.py"
SPEC = importlib.util.spec_from_file_location("plan_v2_attempt_policy_helpers", HELPERS_PATH)
assert SPEC is not None and SPEC.loader is not None
HELPERS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HELPERS)

canonical_bytes = HELPERS.canonical_bytes
drafted_workspace = HELPERS.drafted_workspace
role_input = HELPERS.role_input
run_controller = HELPERS.run_controller
slot_ledger = HELPERS.slot_ledger
write_json = HELPERS.write_json


def _state(workspace: dict) -> dict:
    return json.loads(workspace["state"].read_text(encoding="utf-8"))


def _prepare(
    tmp_path: Path,
    workspace: dict,
    *,
    role: str,
    sequence: int,
    round_number: int = 1,
    verification_iteration: int = 1,
    ok: bool = True,
) -> tuple[Path, dict]:
    state = _state(workspace)
    workspace["source_snapshot"] = state["source_snapshots"][0]
    input_path = write_json(
        tmp_path / f"input-{sequence}.json",
        role_input(state, workspace, role),
    )
    if verification_iteration != 1:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        payload["verification_iteration"] = verification_iteration
        input_path.write_bytes(canonical_bytes(payload))
    slots = slot_ledger(
        tmp_path / f"slots-{sequence}.json", state="reserved", agent_id=None
    )
    token = tmp_path / f"token-{sequence}.json"
    args: list[object] = [
        "prepare-attempt",
        workspace["state"],
        "--round",
        round_number,
        "--role",
        role,
        "--verification-iteration",
        verification_iteration,
    ]
    if role.startswith("VERIFY_PLAN"):
        args.extend(
            [
                "--assigned-coverage-id",
                "C01",
                "--assigned-obligation-id",
                "P1",
            ]
        )
    args.extend(
        [
            "--slot-id",
            "s1",
            "--slot-ledger",
            slots,
            "--input-envelope",
            input_path,
            "--out",
            token,
        ]
    )
    _result, response = run_controller(*args, ok=ok)
    return token, response


def _finalize_spawn_failed(tmp_path: Path, workspace: dict, token: Path, sequence: int) -> None:
    released = slot_ledger(
        tmp_path / f"released-{sequence}.json", state="released", agent_id=None
    )
    run_controller(
        "finalize-attempt",
        workspace["state"],
        "--attempt-token",
        token,
        "--slot-ledger",
        released,
        "--status",
        "SPAWN_FAILED",
    )


def test_role_order_and_single_prepared_attempt_are_fail_closed(tmp_path: Path) -> None:
    workspace, _ = drafted_workspace(tmp_path)
    before = workspace["state"].read_bytes()
    _token, rejected = _prepare(
        tmp_path, workspace, role="INTERNAL_READINESS", sequence=1, ok=False
    )
    assert rejected["code"] == "ROLE_ORDER_VIOLATION"
    assert workspace["state"].read_bytes() == before

    _prepare(tmp_path, workspace, role="VERIFY_PLAN_VERIFIER", sequence=2)
    prepared = workspace["state"].read_bytes()
    _token, rejected = _prepare(
        tmp_path, workspace, role="VERIFY_PLAN_VERIFIER", sequence=3, ok=False
    )
    assert rejected["code"] == "ATTEMPT_IN_PROGRESS"
    assert workspace["state"].read_bytes() == prepared


def test_one_retry_is_allowed_and_attempt_accounting_is_monotonic(tmp_path: Path) -> None:
    workspace, _ = drafted_workspace(tmp_path)
    first, _ = _prepare(tmp_path, workspace, role="VERIFY_PLAN_VERIFIER", sequence=1)
    _finalize_spawn_failed(tmp_path, workspace, first, 1)
    retry, _ = _prepare(tmp_path, workspace, role="VERIFY_PLAN_VERIFIER", sequence=2)
    _finalize_spawn_failed(tmp_path, workspace, retry, 2)

    before = workspace["state"].read_bytes()
    _token, rejected = _prepare(
        tmp_path, workspace, role="VERIFY_PLAN_VERIFIER", sequence=3, ok=False
    )
    assert rejected["code"] == "RETRY_LIMIT"
    assert workspace["state"].read_bytes() == before
    state = _state(workspace)
    assert [item["attempt_sequence"] for item in state["attempts"]] == [1, 2]
    assert state["budgets"]["used_agent_attempts"] == 2


def test_verify_plan_preserves_three_later_gate_attempts(tmp_path: Path) -> None:
    workspace, state = drafted_workspace(tmp_path)
    state["budgets"]["max_agent_attempts"] = 3
    workspace["state"].write_bytes(canonical_bytes(state))

    token, rejected = _prepare(
        tmp_path, workspace, role="VERIFY_PLAN_VERIFIER", sequence=1, ok=False
    )
    assert rejected["code"] == "AGENT_ATTEMPT_LIMIT"
    assert not token.exists()
    capped = _state(workspace)
    assert capped["status"] == "CAP_REACHED"
    assert capped["cap_reason"] == "AGENT_ATTEMPT_LIMIT"
    assert capped["cap_stage"] == "VERIFY_PLAN"
    assert capped["cap_completed_verification_iteration"] == 0
    assert capped["budgets"]["used_agent_attempts"] == 0


def test_verify_plan_iteration_overflow_records_exact_cap(tmp_path: Path) -> None:
    workspace, _ = drafted_workspace(tmp_path)
    token, rejected = _prepare(
        tmp_path,
        workspace,
        role="VERIFY_PLAN_VERIFIER",
        sequence=1,
        verification_iteration=11,
        ok=False,
    )
    assert rejected["code"] == "VERIFY_PLAN_ITERATION_LIMIT"
    assert not token.exists()
    capped = _state(workspace)
    assert capped["status"] == "CAP_REACHED"
    assert capped["cap_reason"] == "VERIFY_PLAN_ITERATION_LIMIT"
    assert capped["cap_stage"] == "VERIFY_PLAN"
    assert capped["cap_completed_verification_iteration"] == 0


def test_round_overflow_records_exact_cap_without_consuming_attempt(tmp_path: Path) -> None:
    workspace, _ = drafted_workspace(tmp_path)
    token, rejected = _prepare(
        tmp_path,
        workspace,
        role="VERIFY_PLAN_VERIFIER",
        sequence=1,
        round_number=4,
        ok=False,
    )
    assert rejected["code"] == "ROUND_LIMIT"
    assert not token.exists()
    capped = _state(workspace)
    assert capped["status"] == "CAP_REACHED"
    assert capped["cap_reason"] == "ROUND_LIMIT"
    assert capped["cap_stage"] == "VERIFY_PLAN"
    assert capped["cap_completed_verification_iteration"] == 0
    assert capped["attempts"] == []
