from __future__ import annotations

import fcntl
import hashlib
import json
import subprocess
import sys
import time
from argparse import Namespace
from multiprocessing import Process
from pathlib import Path

from scripts import convergence_checkpoint_run, prevention_source_receipt


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts/convergence_checkpoint_run.py"
LEDGER = "operations/work-memory/events.jsonl"
VIEW = "operations/blockers/BLOCKERS.md"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_helper(path: Path) -> None:
    path.write_text(
        """from __future__ import annotations
import hashlib
import json
import sys
from pathlib import Path

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

command, state_path = sys.argv[1:3]
state_file = Path(state_path)
state = json.loads(state_file.read_text())
repo = Path(state["repo"])
current = {
    "ledger": digest(repo / "operations/work-memory/events.jsonl"),
    "view": digest(repo / "operations/blockers/BLOCKERS.md"),
    "unrelated": digest(repo / "unrelated.txt"),
}
if command == "accept-baseline":
    state["expected"]["ledger"] = current["ledger"]
    state["expected"]["view"] = current["view"]
    state_file.write_text(json.dumps(state, sort_keys=True))
    print("expected baseline advanced")
elif command == "guard-baseline":
    if current != state["expected"]:
        print(json.dumps({"verdict": "BLOCKED"}))
        raise SystemExit(3)
    print("PASS baseline guard")
else:
    raise SystemExit(2)
"""
    )


def hold_and_append(repo: str, ready: str) -> None:
    root = Path(repo)
    lock = root / f"{LEDGER}.lock"
    with lock.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        Path(ready).write_text("ready")
        time.sleep(0.25)
        (root / LEDGER).write_text("concurrent ledger\n")
        (root / VIEW).write_text("concurrent view\n")


def setup_case(tmp_path: Path) -> dict[str, Path]:
    repo = tmp_path / "repo"
    (repo / Path(LEDGER).parent).mkdir(parents=True)
    (repo / Path(VIEW).parent).mkdir(parents=True)
    (repo / LEDGER).write_text("initial ledger\n")
    (repo / VIEW).write_text("initial view\n")
    (repo / "unrelated.txt").write_text("clean\n")
    helper = tmp_path / "helper.py"
    state = tmp_path / "state.json"
    write_helper(helper)
    state.write_text(json.dumps({
        "repo": str(repo),
        "expected": {
            "ledger": digest(repo / LEDGER),
            "view": digest(repo / VIEW),
            "unrelated": digest(repo / "unrelated.txt"),
        },
    }))
    return {
        "repo": repo,
        "helper": helper,
        "state": state,
    }


def invoke(case: dict[str, Path], *, timeout: float = 5.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--state",
            str(case["state"]),
            "--repo",
            str(case["repo"]),
            "--approval-id",
            "approved-test",
            "--child-intent-json",
            json.dumps({
                "child_owner_sequence_id": "test-child",
                "child_contract_sha256": "a" * 64,
                "child_intent_id": "child-1",
                "child_parameters": [],
                "guard_receipt_id": "guard-1",
            }, sort_keys=True, separators=(",", ":")),
            "--helper",
            str(case["helper"]),
            "--lock-timeout-seconds",
            "2",
        ],
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def test_concurrent_writer_is_serialized_and_checkpoint_applies(tmp_path: Path) -> None:
    case = setup_case(tmp_path)
    ready = tmp_path / "ready"
    writer = Process(target=hold_and_append, args=(str(case["repo"]), str(ready)))
    writer.start()
    deadline = time.monotonic() + 2
    while not ready.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert ready.exists()

    result = invoke(case)
    writer.join(timeout=2)

    assert writer.exitcode == 0
    assert result.returncode == 0, result.stderr
    assert result.stdout.rstrip().endswith("CONVERGENCE CHECKPOINT APPLIED")


def test_unrelated_drift_fails_before_command(tmp_path: Path) -> None:
    case = setup_case(tmp_path)
    (case["repo"] / "unrelated.txt").write_text("drifted\n")

    result = invoke(case)

    assert result.returncode == 3
    assert "convergence-checkpoint-rejected" in result.stderr


def test_checkpoint_returns_without_holding_ledger_lock(tmp_path: Path) -> None:
    case = setup_case(tmp_path)

    result = invoke(case, timeout=3)

    assert result.returncode == 0, result.stderr
    lock = case["repo"] / f"{LEDGER}.lock"
    with lock.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_checkpoint_uses_current_generated_overlap_contract() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert '"--accept-generated-overlap"' in source
    assert '"--accept-approved-dirty-overlap"' not in source


def test_arbitrary_argv_shape_is_rejected_before_checkpoint(tmp_path: Path) -> None:
    case = setup_case(tmp_path)
    command = [
        sys.executable, str(SCRIPT), "--state", str(case["state"]),
        "--repo", str(case["repo"]), "--approval-id", "approved-test",
        "--child-intent-json", '{"schema_version":1,"argv":["echo","bad"]}',
        "--helper", str(case["helper"]),
    ]
    result = subprocess.run(command, text=True, capture_output=True, check=False)

    assert result.returncode == 2
    assert result.stderr.strip() == "invalid-child-intent-fields"


def test_prevention_identity_is_durable_before_child_and_completed_after_success(
    tmp_path: Path, monkeypatch,
) -> None:
    case = setup_case(tmp_path)
    monkeypatch.setattr(prevention_source_receipt, "ROOT", tmp_path / "receipts")

    returncode = convergence_checkpoint_run.run(Namespace(
        state=str(case["state"]), repo=str(case["repo"]),
        approval_id="approved-test", child_intent_json=json.dumps({
            "child_owner_sequence_id": "test-child",
            "child_contract_sha256": "a" * 64,
            "child_intent_id": "child-1", "child_parameters": [],
            "guard_receipt_id": "guard-1",
        }),
        helper=str(case["helper"]), stage="implementation",
        lock_timeout_seconds=2.0, prevention_effect_id="e" * 64,
        prevention_preparation_sha256="f" * 64,
    ))

    receipt = json.loads(
        prevention_source_receipt.receipt_path("e" * 64).read_text(encoding="utf-8")
    )
    assert returncode == 0
    assert receipt["status"] == "APPLIED"
    assert receipt["owner_sequence_id"] == "convergence-checkpoint-run"
    assert receipt["effect_id"] == "e" * 64
    assert receipt["result_identity"]["verdict"] == "CHECKPOINT_APPLIED"
