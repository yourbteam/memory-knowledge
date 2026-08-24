from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "scripts" / "publish_boundary_probes.py"


def test_manifest_probe_is_independently_runnable() -> None:
    completed = subprocess.run(
        [sys.executable, str(PROBE), "--probe", "manifest"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    result = json.loads(completed.stdout)
    assert result["ok"] is True
    assert result["probe"] == "manifest"
    assert result["success_case"] is True
    assert result["rejection_case"] is True
    assert result["evidence"] == {
        "manifest_paths": ["approved.txt", "removed.txt"],
        "path_escape_rejected": True,
        "staged_paths": ["approved.txt", "removed.txt"],
        "tracked_deletion_included": True,
        "unrelated_remained_unstaged": True,
    }


def test_verification_probe_is_independently_runnable() -> None:
    completed = subprocess.run(
        [sys.executable, str(PROBE), "--probe", "verification"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    result = json.loads(completed.stdout)
    assert result["ok"] is True
    assert result["probe"] == "verification"
    assert result["success_case"] is True
    assert result["rejection_case"] is True
    assert result["evidence"]["selected_paths"] == ["approved.txt"]
    assert result["evidence"]["unrelated_failure_ignored"] is True
    assert result["evidence"]["selected_success_exit"] == 0
    assert result["evidence"]["selected_failure_exit"] != 0
    assert result["evidence"]["nonzero_blocked"] is True


def test_commit_probe_is_independently_runnable() -> None:
    completed = subprocess.run(
        [sys.executable, str(PROBE), "--probe", "commit"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    result = json.loads(completed.stdout)
    assert result["ok"] is True
    assert result["probe"] == "commit"
    assert result["success_case"] is True
    assert result["rejection_case"] is True
    assert result["evidence"] == {
        "commit_created": True,
        "committed_paths": ["approved.txt"],
        "staging_mismatch_rejected_before_commit": True,
        "unrelated_remained_unstaged": True,
    }


def test_push_probe_is_independently_runnable() -> None:
    completed = subprocess.run(
        [sys.executable, str(PROBE), "--probe", "push"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    result = json.loads(completed.stdout)
    assert result["ok"] is True
    assert result["probe"] == "push"
    assert result["success_case"] is True
    assert result["rejection_case"] is True
    assert result["evidence"]["push_exit"] == 0
    assert result["evidence"]["remote_advanced_to_commit"] is True
    assert result["evidence"]["failed_push_exit"] != 0
    assert result["evidence"]["failed_push_left_remote_unchanged"] is True


def test_confirmation_probe_is_independently_runnable() -> None:
    completed = subprocess.run(
        [sys.executable, str(PROBE), "--probe", "confirmation"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    result = json.loads(completed.stdout)
    assert result["ok"] is True
    assert result["probe"] == "confirmation"
    assert result["success_case"] is True
    assert result["rejection_case"] is True
    assert result["evidence"] == {
        "confirmation_source": "fresh-checkout",
        "independent_checkout_matched_published_commit": True,
        "unpublished_local_commit_rejected": True,
    }
