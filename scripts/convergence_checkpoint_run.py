#!/usr/bin/env python3
"""Apply one shared-ledger-safe checkpoint for a typed child owner intent."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence

try:
    from scripts import prevention_source_receipt, work_memory
except ModuleNotFoundError:  # direct script execution
    import prevention_source_receipt
    import work_memory

LEDGER_PATH = work_memory.LEDGER.relative_to(work_memory.ROOT)
BLOCKER_VIEW_PATH = work_memory.BLOCKER_VIEW.relative_to(work_memory.ROOT)
PASS_SIGNAL = "CONVERGENCE CHECKPOINT APPLIED"


class CheckpointError(RuntimeError):
    def __init__(self, message: str, exit_code: int = 2) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def _regular_file(raw: str, label: str) -> Path:
    path = Path(raw).expanduser().resolve()
    if not path.is_file():
        raise CheckpointError(f"{label}-is-not-a-file")
    return path


def _child_intent(raw: str) -> dict[str, Any]:
    try:
        payload: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CheckpointError("invalid-child-intent-json") from exc
    required = {
        "child_owner_sequence_id", "child_contract_sha256", "child_intent_id",
        "child_parameters", "guard_receipt_id",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise CheckpointError("invalid-child-intent-fields")
    if not all(isinstance(payload[name], str) and payload[name] for name in (
        "child_owner_sequence_id", "child_contract_sha256", "child_intent_id",
        "guard_receipt_id",
    )) or not isinstance(payload["child_parameters"], list):
        raise CheckpointError("invalid-child-intent-values")
    return payload


def _acquire(handle: Any, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            if time.monotonic() >= deadline:
                raise CheckpointError("shared-ledger-lock-timeout", 4)
            time.sleep(0.05)


def _run_helper(argv: list[str]) -> dict[str, Any]:
    result = subprocess.run(argv, capture_output=True, text=True, check=False)
    if result.returncode:
        if result.stdout:
            sys.stderr.write(result.stdout)
        if result.stderr:
            sys.stderr.write(result.stderr)
        raise CheckpointError("convergence-checkpoint-rejected", result.returncode)
    return {
        "argv_sha256": hashlib.sha256(
            json.dumps(argv, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "stdout_sha256": hashlib.sha256(result.stdout.encode("utf-8")).hexdigest(),
        "stderr_sha256": hashlib.sha256(result.stderr.encode("utf-8")).hexdigest(),
        "returncode": result.returncode,
    }


def run(args: argparse.Namespace) -> int:
    repository = Path(args.repo).expanduser().resolve()
    if not repository.is_dir():
        raise CheckpointError("repository-is-not-a-directory")
    state = _regular_file(args.state, "state")
    helper = _regular_file(args.helper, "helper")
    child_intent = _child_intent(args.child_intent_json)
    if not args.approval_id.strip():
        raise CheckpointError("approval-id-is-empty")

    prevention_effect_id = getattr(args, "prevention_effect_id", None)
    prevention_preparation_sha256 = getattr(
        args, "prevention_preparation_sha256", None
    )
    source_identity = {
        "repository_path_sha256": hashlib.sha256(
            str(repository).encode("utf-8")
        ).hexdigest(),
        "state_sha256": hashlib.sha256(state.read_bytes()).hexdigest(),
        "helper_sha256": hashlib.sha256(helper.read_bytes()).hexdigest(),
        "child_intent_sha256": hashlib.sha256(
            (json.dumps(child_intent, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        ).hexdigest(),
        "approval_id_sha256": hashlib.sha256(
            args.approval_id.encode("utf-8")
        ).hexdigest(),
        "stage": args.stage,
    }
    if prevention_effect_id or prevention_preparation_sha256:
        prevention_source_receipt.prepare(
            owner_sequence_id="convergence-checkpoint-run",
            profile_id="default",
            effect_id=prevention_effect_id,
            preparation_artifact_sha256=prevention_preparation_sha256,
            source_identity=source_identity,
        )

    ledger = repository / LEDGER_PATH
    blocker_view = repository / BLOCKER_VIEW_PATH
    if not ledger.is_file() or not blocker_view.is_file():
        raise CheckpointError("canonical-shared-ledger-pair-is-missing")
    lock_path = ledger.with_suffix(ledger.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    accept = [
        sys.executable,
        str(helper),
        "accept-baseline",
        str(state),
        "--path",
        str(repository),
        "--changed-path",
        str(repository / BLOCKER_VIEW_PATH),
        "--changed-path",
        str(repository / LEDGER_PATH),
        "--approval-id",
        args.approval_id,
        "--stage",
        args.stage,
        "--accept-generated-overlap",
    ]
    guard = [sys.executable, str(helper), "guard-baseline", str(state)]

    with lock_path.open("a+b") as handle:
        _acquire(handle, args.lock_timeout_seconds)
        state_before_sha256 = hashlib.sha256(state.read_bytes()).hexdigest()
        accept_receipt = _run_helper(accept)
        state_after_accept_sha256 = hashlib.sha256(state.read_bytes()).hexdigest()
        guard_receipt = _run_helper(guard)
        state_after_guard_sha256 = hashlib.sha256(state.read_bytes()).hexdigest()

    checkpoint = {
        "schema_version": 1,
        "verdict": "CHECKPOINT_APPLIED",
        "approval_id_sha256": source_identity["approval_id_sha256"],
        "stage": args.stage,
        "outer_iteration": json.loads(state.read_text(encoding="utf-8")).get(
            "outer_iteration", 0
        ),
        "repository_path_sha256": source_identity["repository_path_sha256"],
        "helper_sha256": source_identity["helper_sha256"],
        "child_intent_sha256": source_identity["child_intent_sha256"],
        "guard_receipt_id": child_intent["guard_receipt_id"],
        "state_before_sha256": state_before_sha256,
        "state_after_accept_sha256": state_after_accept_sha256,
        "state_after_guard_sha256": state_after_guard_sha256,
        "accept_receipt": accept_receipt,
        "guard_receipt": guard_receipt,
    }
    if args.prevention_effect_id:
        receipt = prevention_source_receipt.complete(
            owner_sequence_id="convergence-checkpoint-run",
            profile_id="default",
            effect_id=prevention_effect_id,
            preparation_artifact_sha256=prevention_preparation_sha256,
            source_identity=source_identity,
            result_identity=checkpoint,
        )
        print(json.dumps({
            "ok": True, "verdict": "CHECKPOINT_APPLIED",
            "passSignal": PASS_SIGNAL,
            "checkpoint": checkpoint,
            "preventionEffectId": args.prevention_effect_id,
            "preventionPreparationSha256": args.prevention_preparation_sha256,
            "preventionSourceReceiptSha256": (
                prevention_source_receipt.receipt_sha256(receipt)
            ),
        }, sort_keys=True))
    else:
        print(PASS_SIGNAL)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--approval-id", required=True)
    parser.add_argument("--child-intent-json", required=True)
    parser.add_argument(
        "--helper",
        default=str(Path(__file__).resolve().parents[1] / "skills/_shared/convergence_state.py"),
    )
    parser.add_argument("--stage", default="implementation")
    parser.add_argument("--lock-timeout-seconds", type=float, default=30.0)
    parser.add_argument("--prevention-effect-id")
    parser.add_argument("--prevention-preparation-sha256")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if not values:
        try:
            from scripts import sequence_intake_launch
        except ModuleNotFoundError:
            import sequence_intake_launch  # type: ignore
        return sequence_intake_launch.main_for_sequence(
            "convergence-checkpoint-run", [],
        )
    try:
        return run(build_parser().parse_args(values))
    except CheckpointError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
