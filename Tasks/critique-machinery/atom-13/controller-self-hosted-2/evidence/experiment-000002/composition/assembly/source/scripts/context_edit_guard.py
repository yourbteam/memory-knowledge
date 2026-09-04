#!/usr/bin/env python3
"""Guard one exact-context repository edit with a tamper-evident receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence


SCHEMA_VERSION = 1
PREPARED_SIGNAL = "SCOPED CONTEXT EDIT PREPARED"
CURRENT_SIGNAL = "SCOPED CONTEXT EDIT CURRENT"
VERIFIED_SIGNAL = "SCOPED CONTEXT EDIT VERIFIED"
CANCELLED_SIGNAL = "SCOPED CONTEXT EDIT CANCELLED"
SELF_CHECK_SIGNAL = "SCOPED CONTEXT EDIT OK"
ACTIVE_STATES = {"prepared", "checked"}
TERMINAL_STATES = {"verified", "cancelled"}
RECEIPT_KEYS = {
    "schema_version",
    "state",
    "repo_root",
    "target",
    "allowed_paths",
    "target_sha256",
    "snapshot",
    "anchor",
    "required_after",
    "forbidden_after",
    "whitespace_fingerprints",
    "receipt_sha256",
}


class GuardError(RuntimeError):
    """A fail-closed guard rejection."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")


def _git(
    repo: Path, *args: str, allowed_codes: tuple[int, ...] = (0,),
) -> subprocess.CompletedProcess[bytes]:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, check=False,
    )
    if completed.returncode not in allowed_codes:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise GuardError(f"git-command-failed:{args[0]}:{detail or completed.returncode}")
    return completed


def _repo_root(value: str) -> Path:
    candidate = Path(value).expanduser().resolve()
    if not candidate.is_dir():
        raise GuardError("repository-root-not-found")
    completed = _git(candidate, "rev-parse", "--show-toplevel")
    try:
        root = Path(completed.stdout.decode("utf-8").strip()).resolve()
    except UnicodeDecodeError as exc:
        raise GuardError("repository-root-not-utf8") from exc
    if root != candidate:
        raise GuardError("repository-root-must-be-top-level")
    return root


def _relative(value: str, *, repo: Path, label: str, allow_missing: bool) -> str:
    raw = Path(value)
    if raw.is_absolute() or value in {"", "."}:
        raise GuardError(f"invalid-{label}-path")
    resolved = (repo / raw).resolve(strict=False)
    try:
        relative = resolved.relative_to(repo)
    except ValueError as exc:
        raise GuardError(f"{label}-path-escapes-repository") from exc
    normalized = relative.as_posix()
    if normalized == ".git" or normalized.startswith(".git/"):
        raise GuardError(f"invalid-{label}-path")
    if not allow_missing and not resolved.exists():
        raise GuardError(f"{label}-path-not-found")
    return normalized


def _receipt_path(value: str) -> Path:
    raw = Path(value).expanduser()
    if not raw.is_absolute():
        raise GuardError("receipt-path-must-be-absolute")
    return raw.resolve(strict=False)


def _under(relative: str, allowed: str) -> bool:
    return relative == allowed or relative.startswith(f"{allowed}/")


def _atomic_receipt(path: Path, receipt: dict[str, Any]) -> None:
    payload = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    receipt = {**payload, "receipt_sha256": _sha256(_canonical(payload))}
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(raw)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(_canonical(receipt) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _load_receipt(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise GuardError("receipt-not-found")
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GuardError("invalid-receipt-json") from exc
    if not isinstance(receipt, dict) or set(receipt) != RECEIPT_KEYS:
        raise GuardError("invalid-receipt-shape")
    if receipt.get("schema_version") != SCHEMA_VERSION:
        raise GuardError("unsupported-receipt-version")
    expected = receipt.get("receipt_sha256")
    payload = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    if not isinstance(expected, str) or expected != _sha256(_canonical(payload)):
        raise GuardError("receipt-authentication-failed")
    if receipt.get("state") not in ACTIVE_STATES | TERMINAL_STATES:
        raise GuardError("invalid-receipt-state")
    return receipt


def _git_paths(repo: Path, *args: str) -> list[str]:
    raw = _git(repo, *args, "-z").stdout
    values: list[str] = []
    for item in raw.split(b"\0"):
        if not item:
            continue
        try:
            values.append(item.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise GuardError("non-utf8-git-path") from exc
    return values


def _file_identity(path: Path) -> dict[str, Any]:
    info = path.lstat()
    mode = stat.S_IMODE(info.st_mode)
    if stat.S_ISLNK(info.st_mode):
        return {
            "kind": "symlink",
            "mode": mode,
            "sha256": _sha256(os.readlink(path).encode("utf-8")),
        }
    if stat.S_ISREG(info.st_mode):
        return {"kind": "file", "mode": mode, "sha256": _sha256(path.read_bytes())}
    return {"kind": "other", "mode": mode, "sha256": ""}


def _snapshot(repo: Path) -> dict[str, Any]:
    head_result = _git(repo, "rev-parse", "--verify", "HEAD", allowed_codes=(0, 128))
    head = (
        head_result.stdout.decode("ascii").strip()
        if head_result.returncode == 0 else "UNBORN"
    )
    index = _git(repo, "ls-files", "--stage", "-z").stdout
    tracked = set(_git_paths(repo, "ls-files", "--cached"))
    untracked = set(_git_paths(repo, "ls-files", "--others", "--exclude-standard"))
    working: dict[str, dict[str, Any]] = {}
    missing_tracked: list[str] = []
    for relative in sorted(tracked | untracked):
        path = repo / relative
        if not os.path.lexists(path):
            if relative in tracked:
                missing_tracked.append(relative)
            continue
        working[relative] = _file_identity(path)
    return {
        "head": head,
        "index_sha256": _sha256(index),
        "working": working,
        "missing_tracked": missing_tracked,
    }


def _literal_fingerprint(value: str, label: str) -> dict[str, Any]:
    if not value:
        raise GuardError(f"empty-{label}")
    raw = value.encode("utf-8")
    return {"length": len(raw), "sha256": _sha256(raw)}


def _literal_fingerprints(values: list[str] | None, label: str) -> list[dict[str, Any]]:
    values = values or []
    if len(values) != len(set(values)):
        raise GuardError(f"duplicate-{label}")
    return [_literal_fingerprint(value, label) for value in values]


def _contains_fingerprint(content: bytes, fingerprint: dict[str, Any]) -> bool:
    length = fingerprint.get("length")
    digest = fingerprint.get("sha256")
    if not isinstance(length, int) or length <= 0 or not isinstance(digest, str):
        raise GuardError("invalid-assertion-fingerprint")
    if length > len(content):
        return False
    return any(
        _sha256(content[index:index + length]) == digest
        for index in range(0, len(content) - length + 1)
    )


def _diagnostic_fingerprint(path: str, message: str, line: bytes) -> str:
    return _sha256(_canonical({
        "path": path,
        "message": message,
        "line_sha256": _sha256(line),
    }))


def _custom_whitespace(repo: Path, allowed: list[str]) -> set[str]:
    fingerprints: set[str] = set()
    for relative in sorted(_snapshot(repo)["working"]):
        if not any(_under(relative, item) for item in allowed):
            continue
        path = repo / relative
        if not path.is_file() or path.is_symlink():
            continue
        for number, line in enumerate(path.read_bytes().splitlines(), start=1):
            if line.endswith((b" ", b"\t")):
                fingerprints.add(_diagnostic_fingerprint(
                    relative, "trailing whitespace", line,
                ))
            if b" \t" in line:
                fingerprints.add(_diagnostic_fingerprint(
                    relative, "space before tab", line,
                ))
    return fingerprints


def _whitespace_fingerprints(repo: Path, allowed: list[str]) -> list[str]:
    completed = _git(repo, "diff", "--check", "--", *allowed, allowed_codes=(0, 1, 2))
    if completed.returncode not in {0, 1, 2}:
        raise GuardError("git-diff-check-failed")
    fingerprints = _custom_whitespace(repo, allowed)
    for raw in completed.stdout.splitlines():
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise GuardError("non-utf8-diff-diagnostic") from exc
        parts = text.rsplit(":", 2)
        if len(parts) != 3 or not parts[1].isdigit():
            continue
        relative, line_number, message = parts
        path = repo / relative
        lines = path.read_bytes().splitlines() if path.is_file() else []
        number = int(line_number)
        line = lines[number - 1] if 0 < number <= len(lines) else b""
        fingerprints.add(_diagnostic_fingerprint(relative, message.strip(), line))
    return sorted(fingerprints)


def _changed_working_paths(before: dict[str, Any], after: dict[str, Any]) -> set[str]:
    changed = {
        path for path in set(before["working"]) | set(after["working"])
        if before["working"].get(path) != after["working"].get(path)
    }
    changed.update(set(before["missing_tracked"]) ^ set(after["missing_tracked"]))
    return changed


def _validate_receipt_repository(receipt_path: Path, receipt: dict[str, Any]) -> Path:
    repo = Path(receipt["repo_root"]).resolve()
    if not repo.is_dir():
        raise GuardError("receipt-repository-not-found")
    try:
        receipt_path.relative_to(repo)
    except ValueError:
        return repo
    raise GuardError("receipt-path-inside-repository")


def prepare(args: argparse.Namespace, *, emit: bool = True) -> dict[str, Any]:
    repo = _repo_root(args.repo_root)
    target = _relative(args.target, repo=repo, label="target", allow_missing=False)
    target_path = repo / target
    if not target_path.is_file() or target_path.is_symlink():
        raise GuardError("target-must-be-regular-file")
    allowed = sorted({
        _relative(value, repo=repo, label="allowed", allow_missing=True)
        for value in args.allow
    })
    if len(allowed) != len(args.allow):
        raise GuardError("duplicate-allowed-path")
    if not any(_under(target, item) for item in allowed):
        raise GuardError("target-outside-allowed-paths")
    receipt_path = _receipt_path(args.receipt)
    try:
        receipt_path.relative_to(repo)
    except ValueError:
        pass
    else:
        raise GuardError("receipt-path-inside-repository")
    if receipt_path.exists():
        existing = _load_receipt(receipt_path)
        if existing["state"] not in TERMINAL_STATES:
            raise GuardError("active-receipt-already-exists")
    if args.anchor_count <= 0:
        raise GuardError("invalid-anchor-count")
    anchor = args.anchor.encode("utf-8")
    if not anchor:
        raise GuardError("empty-anchor")
    content = target_path.read_bytes()
    actual_count = content.count(anchor)
    if actual_count != args.anchor_count:
        raise GuardError(f"anchor-count-mismatch:{actual_count}")
    snapshot = _snapshot(repo)
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "state": "prepared",
        "repo_root": str(repo),
        "target": target,
        "allowed_paths": allowed,
        "target_sha256": _sha256(content),
        "snapshot": snapshot,
        "anchor": {**_literal_fingerprint(args.anchor, "anchor"), "count": args.anchor_count},
        "required_after": _literal_fingerprints(args.require_after, "required-after"),
        "forbidden_after": _literal_fingerprints(args.forbid_after, "forbidden-after"),
        "whitespace_fingerprints": _whitespace_fingerprints(repo, allowed),
        "receipt_sha256": "",
    }
    _atomic_receipt(receipt_path, receipt)
    if emit:
        print(PREPARED_SIGNAL)
    return _load_receipt(receipt_path)


def check(args: argparse.Namespace, *, emit: bool = True) -> dict[str, Any]:
    receipt_path = _receipt_path(args.receipt)
    receipt = _load_receipt(receipt_path)
    repo = _validate_receipt_repository(receipt_path, receipt)
    if receipt["state"] not in {"prepared", "checked"}:
        raise GuardError("receipt-not-current-checkable")
    try:
        current = _snapshot(repo)
        target = repo / receipt["target"]
        if current != receipt["snapshot"] or not target.is_file():
            raise GuardError("stale-edit-context")
        if _sha256(target.read_bytes()) != receipt["target_sha256"]:
            raise GuardError("stale-target-content")
    except GuardError:
        receipt["state"] = "cancelled"
        _atomic_receipt(receipt_path, receipt)
        raise
    if receipt["state"] == "prepared":
        receipt["state"] = "checked"
        _atomic_receipt(receipt_path, receipt)
        receipt = _load_receipt(receipt_path)
    if emit:
        print(CURRENT_SIGNAL)
    return receipt


def verify(args: argparse.Namespace, *, emit: bool = True) -> dict[str, Any]:
    receipt_path = _receipt_path(args.receipt)
    receipt = _load_receipt(receipt_path)
    repo = _validate_receipt_repository(receipt_path, receipt)
    if receipt["state"] != "checked":
        raise GuardError("receipt-not-checked")
    try:
        current = _snapshot(repo)
        before = receipt["snapshot"]
        if current["head"] != before["head"]:
            raise GuardError("head-changed-after-check")
        if current["index_sha256"] != before["index_sha256"]:
            raise GuardError("index-changed-after-check")
        changed = _changed_working_paths(before, current)
        target = receipt["target"]
        if target not in changed:
            raise GuardError("target-was-not-edited")
        outside = sorted(
            path for path in changed
            if not any(_under(path, item) for item in receipt["allowed_paths"])
        )
        if outside:
            raise GuardError("outside-scope-change:" + ",".join(outside))
        target_path = repo / target
        if not target_path.is_file() or target_path.is_symlink():
            raise GuardError("target-no-longer-regular-file")
        content = target_path.read_bytes()
        if _sha256(content) == receipt["target_sha256"]:
            raise GuardError("target-content-unchanged")
        if any(not _contains_fingerprint(content, item) for item in receipt["required_after"]):
            raise GuardError("required-postcondition-missing")
        if any(_contains_fingerprint(content, item) for item in receipt["forbidden_after"]):
            raise GuardError("forbidden-postcondition-present")
        current_whitespace = set(_whitespace_fingerprints(repo, receipt["allowed_paths"]))
        new_whitespace = current_whitespace - set(receipt["whitespace_fingerprints"])
        if new_whitespace:
            raise GuardError("new-whitespace-defect")
    except GuardError:
        receipt["state"] = "cancelled"
        _atomic_receipt(receipt_path, receipt)
        raise
    receipt["state"] = "verified"
    _atomic_receipt(receipt_path, receipt)
    receipt = _load_receipt(receipt_path)
    if emit:
        print(VERIFIED_SIGNAL)
    return receipt


def cancel(args: argparse.Namespace, *, emit: bool = True) -> dict[str, Any]:
    receipt_path = _receipt_path(args.receipt)
    receipt = _load_receipt(receipt_path)
    _validate_receipt_repository(receipt_path, receipt)
    if receipt["state"] == "verified":
        raise GuardError("verified-receipt-is-terminal")
    if receipt["state"] != "cancelled":
        receipt["state"] = "cancelled"
        _atomic_receipt(receipt_path, receipt)
        receipt = _load_receipt(receipt_path)
    if emit:
        print(CANCELLED_SIGNAL)
    return receipt


def self_check(*, emit: bool = True) -> None:
    with tempfile.TemporaryDirectory(prefix="context-edit-guard-") as raw:
        root = Path(raw)
        repo = root / "repo"
        repo.mkdir()
        _git(repo, "init", "-q")
        target = repo / "target.txt"
        outside = repo / "outside.txt"
        target.write_text("anchor old\n", encoding="utf-8")
        outside.write_text("outside\n", encoding="utf-8")
        _git(repo, "add", "--", "target.txt", "outside.txt")

        receipt = root / "success.json"
        prepare(argparse.Namespace(
            repo_root=str(repo), target="target.txt", anchor="anchor old",
            anchor_count=1, receipt=str(receipt), allow=["target.txt"],
            require_after=["anchor new"], forbid_after=["anchor old"],
        ), emit=False)
        check(argparse.Namespace(receipt=str(receipt)), emit=False)
        target.write_text("anchor new\n", encoding="utf-8")
        verify(argparse.Namespace(receipt=str(receipt)), emit=False)

        stale = root / "stale.json"
        prepare(argparse.Namespace(
            repo_root=str(repo), target="target.txt", anchor="anchor new",
            anchor_count=1, receipt=str(stale), allow=["target.txt"],
            require_after=[], forbid_after=[],
        ), emit=False)
        outside.write_text("outside changed\n", encoding="utf-8")
        try:
            check(argparse.Namespace(receipt=str(stale)), emit=False)
        except GuardError as exc:
            if str(exc) != "stale-edit-context":
                raise
        else:
            raise GuardError("self-check-stale-context-was-accepted")

        scoped = root / "scoped.json"
        prepare(argparse.Namespace(
            repo_root=str(repo), target="target.txt", anchor="anchor new",
            anchor_count=1, receipt=str(scoped), allow=["target.txt"],
            require_after=[], forbid_after=[],
        ), emit=False)
        check(argparse.Namespace(receipt=str(scoped)), emit=False)
        target.write_text("anchor final\n", encoding="utf-8")
        outside.write_text("outside changed again\n", encoding="utf-8")
        try:
            verify(argparse.Namespace(receipt=str(scoped)), emit=False)
        except GuardError as exc:
            if not str(exc).startswith("outside-scope-change:"):
                raise
        else:
            raise GuardError("self-check-outside-scope-change-was-accepted")
    if emit:
        print(SELF_CHECK_SIGNAL)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--repo-root", required=True)
    prepare_parser.add_argument("--target", required=True)
    prepare_parser.add_argument("--anchor", required=True)
    prepare_parser.add_argument("--anchor-count", required=True, type=int)
    prepare_parser.add_argument("--receipt", required=True)
    prepare_parser.add_argument("--allow", required=True, action="append")
    prepare_parser.add_argument("--require-after", action="append")
    prepare_parser.add_argument("--forbid-after", action="append")
    prepare_parser.set_defaults(handler=prepare)

    for name, handler in (("check", check), ("verify", verify), ("cancel", cancel)):
        command = sub.add_parser(name)
        command.add_argument("--receipt", required=True)
        command.set_defaults(handler=handler)

    self_parser = sub.add_parser("self-check")
    self_parser.set_defaults(handler=lambda args: self_check())
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if not values:
        try:
            from scripts import sequence_intake_launch
        except ModuleNotFoundError:
            import sequence_intake_launch  # type: ignore
        return sequence_intake_launch.main_for_sequence(
            "scoped-context-edit", [],
        )
    parser = build_parser()
    args = parser.parse_args(values)
    try:
        args.handler(args)
    except GuardError as exc:
        print(f"context-edit-guard: {exc}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
