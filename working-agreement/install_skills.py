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


TERMINAL_ROW_STATUSES = {"shared-identical", "generated-projection", "client-not-applicable"}


def _projection_module():
    import importlib.util
    tool = Path(__file__).with_name("project_client_skills.py")
    spec = importlib.util.spec_from_file_location("project_client_skills", tool)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def reconciliation_errors(path: Path, source: Path, manifest: Path, selected: list[str]) -> list[str]:
    """A Claude-targeting install requires one complete, current decision per managed skill."""
    data = json.loads(path.read_text())
    if isinstance(data.get("entries"), dict):
        pcs = _projection_module()
        managed = names(manifest)
        errors = pcs.structural_errors(data["entries"], managed)
        errors += pcs.currency_errors(source, data["entries"], selected)
        errors += [f"{name}: disposition BLOCKED refuses installation"
                   for name in selected if data["entries"].get(name, {}).get("disposition") == "BLOCKED"]
        return errors
    rows = {row.get("name"): row for row in data.get("rows", [])}
    errors = []
    missing = sorted(set(selected) - set(rows))
    if missing: errors.append("reconciliation lacks a decision for: " + ", ".join(missing))
    for name in selected:
        status = rows.get(name, {}).get("status")
        if name in rows and status not in TERMINAL_ROW_STATUSES:
            errors.append(f"{name}: status {status!r} is not a terminal reconciliation decision")
    return errors


def selected_names(manifest: Path, only: list[str] | None = None) -> list[str]:
    managed = names(manifest)
    if only is None:
        return managed
    if not only or len(only) != len(set(only)):
        raise SystemExit("--only values must be non-empty and unique")
    unknown = sorted(set(only) - set(managed))
    if unknown:
        raise SystemExit("--only names are not managed: " + ", ".join(unknown))
    selected = set(only)
    return [name for name in managed if name in selected]


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


def install(source: Path, manifest: Path, destinations: list[Path], state_dir: Path,
            hold: float = 0, only: list[str] | None = None) -> None:
    install_names = selected_names(manifest, only)
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
        managed = set(names(manifest))
        for destination_index, destination_root in enumerate(destinations):
            destination_root.mkdir(parents=True, exist_ok=True)
            unmanaged = sorted(p.name for p in destination_root.iterdir() if p.is_dir() and p.name not in managed)
            if unmanaged:
                print(f"unmanaged preserved in {destination_root}: " + ", ".join(unmanaged))
            for name in install_names:
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
    ap.add_argument("--only", action="append", help="Install only this manifest-managed skill; repeatable")
    ap.add_argument("--hold-lock", type=float, default=0, help=argparse.SUPPRESS); args = ap.parse_args()
    if args.target == "both" and not args.accept_cross_client:
        raise SystemExit("--target both requires --accept-cross-client")
    if args.target in ("claude", "both"):
        if not args.reconciliation:
            raise SystemExit(f"--target {args.target} mutates the Claude root and requires --reconciliation")
        selected = selected_names(args.manifest.resolve(), args.only)
        errors = reconciliation_errors(args.reconciliation, args.source.resolve(), args.manifest.resolve(), selected)
        if errors: raise SystemExit("reconciliation refused:\n" + "\n".join(errors))
    destinations = [args.codex_root] if args.target == "codex" else [args.claude_root] if args.target == "claude" else [args.codex_root, args.claude_root]
    install(args.source.resolve(), args.manifest.resolve(), destinations, args.state_dir.resolve(), args.hold_lock, args.only); return 0


if __name__ == "__main__": raise SystemExit(main())
