#!/usr/bin/env python3
"""Install managed skills with an exclusive lock and recoverable journal."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def fsync_file(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def fsync_tree(path: Path) -> None:
    items = list(path.rglob("*"))
    for item in items:
        if item.is_file(): fsync_file(item)
    for directory in sorted((item for item in items if item.is_dir()), key=lambda item: len(item.parts), reverse=True):
        fsync_dir(directory)
    fsync_dir(path)


def tree_hash(path: Path) -> str | None:
    if not path.exists(): return None
    h = hashlib.sha256()
    for item in sorted(p for p in path.rglob("*") if p.is_file()):
        h.update(item.relative_to(path).as_posix().encode() + b"\0"); h.update(item.read_bytes())
    return h.hexdigest()


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".install-", dir=path.parent)
    with os.fdopen(fd, "w") as handle:
        json.dump(data, handle, indent=2, sort_keys=True); handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
    os.replace(tmp, path)
    fsync_dir(path.parent)


def names(manifest: Path) -> list[str]:
    return [x.strip() for x in manifest.read_text().splitlines() if x.strip() and not x.lstrip().startswith("#")]


def recover(journal_path: Path) -> None:
    if not journal_path.exists(): return
    journal = json.loads(journal_path.read_text())
    if journal["phase"] == "APPLYING":
        for row in reversed(journal["entries"]):
            if not row.get("mutation_started"): continue
            dest, backup = Path(row["destination"]), Path(row["backup"])
            if backup.exists():
                if dest.exists(): shutil.rmtree(dest)
                os.replace(backup, dest)
                fsync_dir(dest.parent); fsync_dir(backup.parent)
            elif (not row.get("original_exists") and dest.exists()
                  and (row.get("installed") or not Path(row["staged"]).exists())):
                shutil.rmtree(dest)
                fsync_dir(dest.parent)
    for row in journal["entries"]:
        shutil.rmtree(Path(row["staged"]), ignore_errors=True); shutil.rmtree(Path(row["backup"]), ignore_errors=True)
    journal_path.unlink(missing_ok=True); fsync_dir(journal_path.parent)


def install(source: Path, manifest: Path, destinations: list[Path], state_dir: Path, hold: float = 0) -> None:
    validator = Path(__file__).with_name("validate_skills.py")
    checked = subprocess.run(
        [sys.executable, str(validator), "--skills-root", str(source), "--manifest", str(manifest)],
        capture_output=True, text=True,
    )
    if checked.returncode:
        raise RuntimeError("managed skill validation failed:\n" + checked.stderr)
    state_dir.mkdir(parents=True, exist_ok=True)
    lock_path, journal_path = state_dir / "install.lock", state_dir / "transaction.json"
    with lock_path.open("a+") as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise SystemExit("already running")
        recover(journal_path)
        if hold: time.sleep(hold)
        txn = state_dir / f"txn-{os.getpid()}"; txn.mkdir()
        entries = []
        for destination_index, destination_root in enumerate(destinations):
            destination_root.mkdir(parents=True, exist_ok=True)
            for name in names(manifest):
                src, dest = source / name, destination_root / name
                staged = txn / "staged" / str(destination_index) / name
                backup = txn / "backup" / str(destination_index) / name
                staged.parent.mkdir(parents=True, exist_ok=True); shutil.copytree(src, staged)
                fsync_tree(staged); fsync_dir(staged.parent)
                entries.append({"name": name, "source_hash": tree_hash(src), "destination": str(dest),
                                "staged": str(staged), "backup": str(backup),
                                "original_exists": dest.exists(), "mutation_started": False, "installed": False})
        journal = {"transaction_id": str(uuid.uuid4()), "phase": "PREPARED", "entries": entries}; write_json(journal_path, journal)
        journal["phase"] = "APPLYING"; write_json(journal_path, journal)
        try:
            for row in entries:
                dest, staged, backup = Path(row["destination"]), Path(row["staged"]), Path(row["backup"])
                row["mutation_started"] = True; write_json(journal_path, journal)
                if dest.exists():
                    backup.parent.mkdir(parents=True, exist_ok=True); os.replace(dest, backup)
                    fsync_dir(dest.parent); fsync_dir(backup.parent)
                os.replace(staged, dest)
                fsync_dir(staged.parent); fsync_dir(dest.parent)
                row["installed"] = True; write_json(journal_path, journal)
                if tree_hash(dest) != row["source_hash"]: raise RuntimeError(f"post-install hash mismatch: {dest}")
            journal["phase"] = "COMMITTED"; write_json(journal_path, journal)
        except BaseException:
            recover(journal_path); raise
        for row in entries:
            backup = Path(row["backup"]); shutil.rmtree(backup, ignore_errors=True)
            if backup.parent.exists(): fsync_dir(backup.parent)
        journal["phase"] = "CLEANED"; write_json(journal_path, journal)
        shutil.rmtree(txn, ignore_errors=True); fsync_dir(txn.parent)
        journal_path.unlink(); fsync_dir(journal_path.parent)
        for row in entries: print(f"installed {row['name']} -> {row['destination']} {row['source_hash']}")


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--source", type=Path, required=True); ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--target", choices=["codex", "claude", "both"], default="codex"); ap.add_argument("--accept-cross-client", action="store_true")
    ap.add_argument("--codex-root", type=Path, default=Path.home()/".codex/skills"); ap.add_argument("--claude-root", type=Path, default=Path.home()/".claude/skills")
    ap.add_argument("--state-dir", type=Path, default=Path(os.environ.get("XDG_STATE_HOME", Path.home()/".local/state"))/"kamen-managed-skills")
    ap.add_argument("--reconciliation", type=Path)
    ap.add_argument("--hold-lock", type=float, default=0, help=argparse.SUPPRESS); args = ap.parse_args()
    if args.target == "both":
        if not args.accept_cross_client: raise SystemExit("--target both requires --accept-cross-client")
        if not args.reconciliation: raise SystemExit("--target both requires --reconciliation")
        rows = json.loads(args.reconciliation.read_text()).get("rows", [])
        unresolved = [row["name"] for row in rows if row.get("status") == "claude-divergent-preserved"]
        if unresolved: raise SystemExit("cross-client variants are not reconciled: " + ", ".join(unresolved))
    destinations = [args.codex_root] if args.target == "codex" else [args.claude_root] if args.target == "claude" else [args.codex_root, args.claude_root]
    install(args.source.resolve(), args.manifest.resolve(), destinations, args.state_dir.resolve(), args.hold_lock); return 0


if __name__ == "__main__": raise SystemExit(main())
