#!/usr/bin/env python3
"""Safely reset cloned Codex Remote Control enrollment state on macOS."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


ENVIRONMENT_KEY = "electron-local-remote-control-environment-id"
INSTALLATION_KEY = "electron-local-remote-control-installation-id"
REQUIRED_COLUMNS = {
    "websocket_url",
    "account_id",
    "app_server_client_name",
    "server_id",
    "environment_id",
    "server_name",
    "updated_at",
}


def _app_running() -> bool:
    result = subprocess.run(
        ["/usr/bin/pgrep", "-x", "ChatGPT"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def _wait_for_app_exit(timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    while _app_running():
        if time.monotonic() >= deadline:
            raise RuntimeError("ChatGPT did not exit before the reset timeout")
        time.sleep(0.5)


def _quit_app_after(delay_seconds: int) -> None:
    if delay_seconds < 0:
        raise RuntimeError("Quit delay must be non-negative")
    time.sleep(delay_seconds)
    result = subprocess.run(
        [
            "/usr/bin/osascript",
            "-e",
            'tell application "ChatGPT" to quit',
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Could not quit ChatGPT: {result.stderr.strip()[:300]}")


def _database_paths(codex_home: Path) -> list[Path]:
    return [codex_home / "state_5.sqlite", codex_home / "sqlite" / "state_5.sqlite"]


def _global_state_paths(codex_home: Path) -> list[Path]:
    return [codex_home / ".codex-global-state.json", codex_home / ".codex-global-state.json.bak"]


def _table_columns(db_path: Path) -> set[str]:
    with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as conn:
        return {str(row[1]) for row in conn.execute("PRAGMA table_info(remote_control_enrollments)")}


def _enrollment_count(db_path: Path) -> int:
    with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as conn:
        row = conn.execute("SELECT COUNT(*) FROM remote_control_enrollments").fetchone()
    return int(row[0])


def _load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object: {path}")
    return value


def inspect(codex_home: Path) -> dict:
    installation_path = codex_home / "installation_id"
    if not installation_path.is_file():
        raise RuntimeError(f"Missing installation identity: {installation_path}")
    installation_id = installation_path.read_text(encoding="utf-8")
    if not installation_id.strip():
        raise RuntimeError("Installation identity is empty")

    databases: list[dict] = []
    for path in _database_paths(codex_home):
        if not path.is_file():
            raise RuntimeError(f"Missing Codex state database: {path}")
        columns = _table_columns(path)
        missing = REQUIRED_COLUMNS - columns
        if missing:
            raise RuntimeError(f"Unexpected enrollment schema in {path}; missing={sorted(missing)}")
        databases.append({"path": str(path), "enrollment_count": _enrollment_count(path)})

    states: list[dict] = []
    for path in _global_state_paths(codex_home):
        if not path.exists():
            continue
        value = _load_json(path)
        states.append(
            {
                "path": str(path),
                "environment_key_present": ENVIRONMENT_KEY in value,
                "installation_key_matches": value.get(INSTALLATION_KEY) == installation_id,
            }
        )
    if not states:
        raise RuntimeError("No Codex global-state JSON file found")
    if not all(item["installation_key_matches"] for item in states):
        raise RuntimeError("Global-state installation identity does not match the active installation_id")

    return {"databases": databases, "global_states": states, "app_running": _app_running()}


def _backup(codex_home: Path, backup_dir: Path) -> list[str]:
    backup_dir.mkdir(parents=True, exist_ok=False)
    copied: list[str] = []
    candidates: list[Path] = [codex_home / "installation_id"]
    candidates.extend(_global_state_paths(codex_home))
    for db in _database_paths(codex_home):
        candidates.extend([db, Path(f"{db}-wal"), Path(f"{db}-shm")])
    for source in candidates:
        if not source.exists():
            continue
        relative = source.relative_to(codex_home)
        destination = backup_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append(str(relative))
    return copied


def _clear_database(path: Path) -> int:
    before = _enrollment_count(path)
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM remote_control_enrollments")
        conn.commit()
    if _enrollment_count(path) != 0:
        raise RuntimeError(f"Enrollment rows remain after reset: {path}")
    return before


def _atomic_write_json(path: Path, value: dict) -> None:
    mode = path.stat().st_mode if path.exists() else 0o600
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _clear_global_state(path: Path) -> bool:
    value = _load_json(path)
    removed = ENVIRONMENT_KEY in value
    value.pop(ENVIRONMENT_KEY, None)
    _atomic_write_json(path, value)
    return removed


def reset(
    codex_home: Path,
    backup_root: Path,
    timeout_seconds: int,
    reopen: bool,
    quit_app_after: int | None,
) -> dict:
    before = inspect(codex_home)
    if quit_app_after is not None:
        _quit_app_after(quit_app_after)
    _wait_for_app_exit(timeout_seconds)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = backup_root / f"remote-control-enrollment-reset-{timestamp}"
    copied = _backup(codex_home, backup_dir)

    deleted_rows = {str(path): _clear_database(path) for path in _database_paths(codex_home)}
    cleared_states = {
        str(path): _clear_global_state(path)
        for path in _global_state_paths(codex_home)
        if path.exists()
    }
    after = inspect(codex_home)
    if any(item["enrollment_count"] != 0 for item in after["databases"]):
        raise RuntimeError("Post-reset enrollment verification failed")
    if any(item["environment_key_present"] for item in after["global_states"]):
        raise RuntimeError("Post-reset environment-key verification failed")
    if not all(item["installation_key_matches"] for item in after["global_states"]):
        raise RuntimeError("Post-reset installation identity preservation failed")

    result = {
        "ok": True,
        "backup_dir": str(backup_dir),
        "backup_files": copied,
        "deleted_enrollment_rows": deleted_rows,
        "cleared_environment_keys": cleared_states,
        "installation_identity_preserved": True,
    }
    if reopen:
        launched = subprocess.run(
            ["/usr/bin/open", "-a", "ChatGPT"], check=False, capture_output=True, text=True
        )
        result["reopen_requested"] = launched.returncode == 0
        if launched.returncode != 0:
            result["reopen_error"] = launched.stderr.strip()[:300]
    return result


def _write_receipt(path: Path | None, payload: dict) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(path, payload)


def _schedule_marker_path(receipt: Path) -> Path:
    return Path(f"{receipt}.scheduled")


def _claim_schedule(receipt: Path) -> Path:
    marker = _schedule_marker_path(receipt)
    marker.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise RuntimeError(f"Reset is already scheduled for receipt: {receipt}")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump({"status": "scheduled", "receipt": str(receipt)}, handle, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    return marker


def _schedule_detached(child_argv: list[str], stdout_path: Path, stderr_path: Path) -> int:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    read_fd, write_fd = os.pipe()
    first_pid = os.fork()
    if first_pid > 0:
        os.close(write_fd)
        os.waitpid(first_pid, 0)
        with os.fdopen(read_fd, "r", encoding="utf-8") as handle:
            child_pid_text = handle.read().strip()
        if not child_pid_text:
            raise RuntimeError("Detached reset scheduler did not return a worker pid")
        return int(child_pid_text)

    try:
        os.close(read_fd)
        os.setsid()
        worker_pid = os.fork()
        if worker_pid > 0:
            os.write(write_fd, str(worker_pid).encode("ascii"))
            os.close(write_fd)
            os._exit(0)

        os.close(write_fd)
        stdin_fd = os.open(os.devnull, os.O_RDONLY)
        stdout_fd = os.open(stdout_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        stderr_fd = os.open(stderr_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        os.dup2(stdin_fd, 0)
        os.dup2(stdout_fd, 1)
        os.dup2(stderr_fd, 2)
        for fd in (stdin_fd, stdout_fd, stderr_fd):
            if fd > 2:
                os.close(fd)
        os.execv(sys.executable, [sys.executable, *child_argv])
    except BaseException:
        os._exit(127)
    raise AssertionError("unreachable")


def _reset_child_argv(args: argparse.Namespace) -> list[str]:
    child = [
        str(Path(__file__).resolve()),
        "reset",
        "--codex-home",
        str(args.codex_home),
        "--wait-for-app-exit",
        str(args.wait_for_app_exit),
        "--receipt",
        str(args.receipt),
    ]
    if args.backup_root is not None:
        child.extend(["--backup-root", str(args.backup_root)])
    if args.quit_app_after is not None:
        child.extend(["--quit-app-after", str(args.quit_app_after)])
    if args.reopen:
        child.append("--reopen")
    return child


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("inspect", "reset", "schedule"))
    parser.add_argument("--codex-home", type=Path, default=Path.home() / ".codex")
    parser.add_argument("--backup-root", type=Path)
    parser.add_argument("--wait-for-app-exit", type=int, default=120)
    parser.add_argument("--quit-app-after", type=int)
    parser.add_argument("--reopen", action="store_true")
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--schedule-stdout", type=Path)
    parser.add_argument("--schedule-stderr", type=Path)
    args = parser.parse_args()

    if args.command in {"reset", "schedule"} and args.receipt is None:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "ReceiptRequired",
                    "message": f"{args.command} requires --receipt for at-most-once execution",
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2

    if args.command in {"reset", "schedule"} and args.receipt.exists():
        try:
            existing = _load_json(args.receipt)
            payload = {
                "ok": True,
                "status": "already_attempted",
                "existing_status": existing.get("status", "unknown"),
                "receipt": str(args.receipt),
            }
            print(json.dumps(payload, sort_keys=True))
            return 0
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": type(exc).__name__,
                        "message": f"Existing reset receipt is unreadable: {exc}",
                    },
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
            return 2

    if args.command == "schedule":
        marker = _schedule_marker_path(args.receipt)
        if marker.exists():
            payload = {
                "ok": True,
                "status": "already_scheduled",
                "receipt": str(args.receipt),
                "schedule_marker": str(marker),
            }
            print(json.dumps(payload, sort_keys=True))
            return 0
        stdout_path = args.schedule_stdout or Path(f"{args.receipt}.stdout.log")
        stderr_path = args.schedule_stderr or Path(f"{args.receipt}.stderr.log")
        try:
            marker = _claim_schedule(args.receipt)
            worker_pid = _schedule_detached(
                _reset_child_argv(args), stdout_path, stderr_path
            )
            payload = {
                "ok": True,
                "status": "scheduled",
                "worker_pid": worker_pid,
                "receipt": str(args.receipt),
                "schedule_marker": str(marker),
                "stdout": str(stdout_path),
                "stderr": str(stderr_path),
            }
            print(json.dumps(payload, sort_keys=True))
            return 0
        except Exception as exc:
            payload = {
                "ok": False,
                "status": "schedule_failed",
                "error": type(exc).__name__,
                "message": str(exc),
            }
            print(json.dumps(payload, sort_keys=True), file=sys.stderr)
            return 1

    try:
        if args.command == "inspect":
            payload = {"ok": True, **inspect(args.codex_home)}
        else:
            _write_receipt(
                args.receipt,
                {
                    "ok": False,
                    "status": "started",
                    "receipt": str(args.receipt),
                },
            )
            backup_root = args.backup_root or args.codex_home
            payload = reset(
                args.codex_home,
                backup_root,
                args.wait_for_app_exit,
                args.reopen,
                args.quit_app_after,
            )
            payload["status"] = "complete"
        _write_receipt(args.receipt, payload)
        print(json.dumps(payload, sort_keys=True))
        return 0
    except Exception as exc:
        payload = {
            "ok": False,
            "status": "failed",
            "error": type(exc).__name__,
            "message": str(exc),
        }
        if args.receipt is not None:
            try:
                _write_receipt(args.receipt, payload)
            except Exception as receipt_exc:
                payload["receipt_error"] = (
                    f"{type(receipt_exc).__name__}: {str(receipt_exc)[:300]}"
                )
        print(json.dumps(payload, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
