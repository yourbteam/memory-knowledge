from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import pytest

from scripts import context_edit_guard


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    (root / "target.txt").write_text("anchor old\n", encoding="utf-8")
    (root / "outside.txt").write_text("outside\n", encoding="utf-8")
    _git(root, "add", "--", "target.txt", "outside.txt")
    return root


def _prepare_args(repo: Path, receipt: Path, **overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "repo_root": str(repo),
        "target": "target.txt",
        "anchor": "anchor old",
        "anchor_count": 1,
        "receipt": str(receipt),
        "allow": ["target.txt"],
        "require_after": ["anchor new"],
        "forbid_after": ["anchor old"],
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _receipt(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_prepare_check_verify_preserves_unchanged_dirty_baseline(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    receipt = tmp_path / "receipt.json"
    (repo / "outside.txt").write_text("already dirty\n", encoding="utf-8")

    assert context_edit_guard.main([
        "prepare", "--repo-root", str(repo), "--target", "target.txt",
        "--anchor", "anchor old", "--anchor-count", "1",
        "--receipt", str(receipt), "--allow", "target.txt",
        "--require-after", "anchor new", "--forbid-after", "anchor old",
    ]) == 0
    assert capsys.readouterr().out.strip() == context_edit_guard.PREPARED_SIGNAL
    assert context_edit_guard.main(["check", "--receipt", str(receipt)]) == 0
    assert capsys.readouterr().out.strip() == context_edit_guard.CURRENT_SIGNAL

    (repo / "target.txt").write_text("anchor new\n", encoding="utf-8")
    assert context_edit_guard.main(["verify", "--receipt", str(receipt)]) == 0
    assert capsys.readouterr().out.strip() == context_edit_guard.VERIFIED_SIGNAL
    assert _receipt(receipt)["state"] == "verified"


@pytest.mark.parametrize("count", [0, 2])
def test_prepare_rejects_missing_or_duplicate_anchor(
    repo: Path, tmp_path: Path, count: int,
) -> None:
    if count == 0:
        (repo / "target.txt").write_text("no matching anchor\n", encoding="utf-8")
    else:
        (repo / "target.txt").write_text("anchor old\nanchor old\n", encoding="utf-8")
    with pytest.raises(context_edit_guard.GuardError, match="anchor-count-mismatch"):
        context_edit_guard.prepare(
            _prepare_args(repo, tmp_path / "receipt.json", anchor_count=1),
            emit=False,
        )


@pytest.mark.parametrize("target", ["../outside.txt", "/tmp/outside.txt"])
def test_prepare_rejects_target_path_escape(
    repo: Path, tmp_path: Path, target: str,
) -> None:
    with pytest.raises(context_edit_guard.GuardError, match="target-path"):
        context_edit_guard.prepare(
            _prepare_args(repo, tmp_path / "receipt.json", target=target),
            emit=False,
        )


def test_prepare_rejects_allowed_path_escape(repo: Path, tmp_path: Path) -> None:
    with pytest.raises(context_edit_guard.GuardError, match="allowed-path-escapes"):
        context_edit_guard.prepare(
            _prepare_args(repo, tmp_path / "receipt.json", allow=["../outside"]),
            emit=False,
        )


def test_receipt_tampering_fails_authentication(repo: Path, tmp_path: Path) -> None:
    receipt = tmp_path / "receipt.json"
    context_edit_guard.prepare(_prepare_args(repo, receipt), emit=False)
    value = _receipt(receipt)
    value["state"] = "checked"
    receipt.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(context_edit_guard.GuardError, match="authentication-failed"):
        context_edit_guard.check(argparse.Namespace(receipt=str(receipt)), emit=False)


def test_target_drift_before_check_cancels_receipt(repo: Path, tmp_path: Path) -> None:
    receipt = tmp_path / "receipt.json"
    context_edit_guard.prepare(_prepare_args(repo, receipt), emit=False)
    (repo / "target.txt").write_text("intervening edit\n", encoding="utf-8")

    with pytest.raises(context_edit_guard.GuardError, match="stale-edit-context"):
        context_edit_guard.check(argparse.Namespace(receipt=str(receipt)), emit=False)
    assert _receipt(receipt)["state"] == "cancelled"


def test_cancel_allows_fresh_prepare_at_same_receipt(repo: Path, tmp_path: Path) -> None:
    receipt = tmp_path / "receipt.json"
    args = _prepare_args(repo, receipt)
    context_edit_guard.prepare(args, emit=False)
    context_edit_guard.check(argparse.Namespace(receipt=str(receipt)), emit=False)
    context_edit_guard.cancel(argparse.Namespace(receipt=str(receipt)), emit=False)
    assert _receipt(receipt)["state"] == "cancelled"

    context_edit_guard.prepare(args, emit=False)
    assert _receipt(receipt)["state"] == "prepared"


def test_failed_postcondition_consumes_receipt(repo: Path, tmp_path: Path) -> None:
    receipt = tmp_path / "receipt.json"
    context_edit_guard.prepare(_prepare_args(repo, receipt), emit=False)
    context_edit_guard.check(argparse.Namespace(receipt=str(receipt)), emit=False)
    (repo / "target.txt").write_text("wrong result\n", encoding="utf-8")

    with pytest.raises(context_edit_guard.GuardError, match="required-postcondition"):
        context_edit_guard.verify(argparse.Namespace(receipt=str(receipt)), emit=False)
    assert _receipt(receipt)["state"] == "cancelled"


@pytest.mark.parametrize("outside_change", ["modify", "create"])
def test_verify_rejects_outside_scope_changes(
    repo: Path, tmp_path: Path, outside_change: str,
) -> None:
    receipt = tmp_path / "receipt.json"
    context_edit_guard.prepare(_prepare_args(repo, receipt), emit=False)
    context_edit_guard.check(argparse.Namespace(receipt=str(receipt)), emit=False)
    (repo / "target.txt").write_text("anchor new\n", encoding="utf-8")
    outside = repo / ("outside.txt" if outside_change == "modify" else "new.txt")
    outside.write_text("changed\n", encoding="utf-8")

    with pytest.raises(context_edit_guard.GuardError, match="outside-scope-change"):
        context_edit_guard.verify(argparse.Namespace(receipt=str(receipt)), emit=False)


def test_verify_rejects_change_to_already_dirty_outside_file(
    repo: Path, tmp_path: Path,
) -> None:
    receipt = tmp_path / "receipt.json"
    (repo / "outside.txt").write_text("dirty before\n", encoding="utf-8")
    context_edit_guard.prepare(_prepare_args(repo, receipt), emit=False)
    context_edit_guard.check(argparse.Namespace(receipt=str(receipt)), emit=False)
    (repo / "target.txt").write_text("anchor new\n", encoding="utf-8")
    (repo / "outside.txt").write_text("dirty after\n", encoding="utf-8")

    with pytest.raises(context_edit_guard.GuardError, match="outside-scope-change"):
        context_edit_guard.verify(argparse.Namespace(receipt=str(receipt)), emit=False)


def test_verify_rejects_index_only_change(repo: Path, tmp_path: Path) -> None:
    receipt = tmp_path / "receipt.json"
    (repo / "outside.txt").write_text("dirty working copy\n", encoding="utf-8")
    context_edit_guard.prepare(_prepare_args(repo, receipt), emit=False)
    context_edit_guard.check(argparse.Namespace(receipt=str(receipt)), emit=False)
    _git(repo, "add", "--", "outside.txt")
    (repo / "target.txt").write_text("anchor new\n", encoding="utf-8")

    with pytest.raises(context_edit_guard.GuardError, match="index-changed"):
        context_edit_guard.verify(argparse.Namespace(receipt=str(receipt)), emit=False)


def test_preexisting_whitespace_defect_is_preserved_without_false_failure(
    repo: Path, tmp_path: Path,
) -> None:
    receipt = tmp_path / "receipt.json"
    (repo / "target.txt").write_text("preexisting  \nanchor old\n", encoding="utf-8")
    _git(repo, "add", "--", "target.txt")
    context_edit_guard.prepare(_prepare_args(repo, receipt), emit=False)
    context_edit_guard.check(argparse.Namespace(receipt=str(receipt)), emit=False)
    (repo / "target.txt").write_text("preexisting  \nanchor new\n", encoding="utf-8")

    context_edit_guard.verify(argparse.Namespace(receipt=str(receipt)), emit=False)
    assert _receipt(receipt)["state"] == "verified"


def test_new_whitespace_defect_is_rejected(repo: Path, tmp_path: Path) -> None:
    receipt = tmp_path / "receipt.json"
    context_edit_guard.prepare(_prepare_args(repo, receipt), emit=False)
    context_edit_guard.check(argparse.Namespace(receipt=str(receipt)), emit=False)
    (repo / "target.txt").write_text("anchor new  \n", encoding="utf-8")

    with pytest.raises(context_edit_guard.GuardError, match="new-whitespace-defect"):
        context_edit_guard.verify(argparse.Namespace(receipt=str(receipt)), emit=False)


def test_terminal_receipt_cannot_be_rechecked(repo: Path, tmp_path: Path) -> None:
    receipt = tmp_path / "receipt.json"
    context_edit_guard.prepare(_prepare_args(repo, receipt), emit=False)
    context_edit_guard.check(argparse.Namespace(receipt=str(receipt)), emit=False)
    (repo / "target.txt").write_text("anchor new\n", encoding="utf-8")
    context_edit_guard.verify(argparse.Namespace(receipt=str(receipt)), emit=False)

    with pytest.raises(context_edit_guard.GuardError, match="not-current-checkable"):
        context_edit_guard.check(argparse.Namespace(receipt=str(receipt)), emit=False)


def test_self_check_emits_exact_pass_signal(capsys: pytest.CaptureFixture[str]) -> None:
    assert context_edit_guard.main(["self-check"]) == 0
    captured = capsys.readouterr()
    assert captured.out == f"{context_edit_guard.SELF_CHECK_SIGNAL}\n"
    assert captured.err == ""
