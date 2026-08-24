#!/usr/bin/env python3
"""Atomically preserve one completed information-intake run in the repository."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile


CONTRACT = "info-intake-terminal-run-archive-v1"
INTAKE_ID = re.compile(r"intake-[0-9a-f]{32}")
DEFAULT_ARCHIVE_ROOT = (
    Path(__file__).resolve().parents[3] / "operations" / "info-intake-runs"
)


class ArchiveError(ValueError):
    """The terminal run cannot be preserved without losing audit fidelity."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_state(work: Path) -> dict[str, object]:
    ledger_path = work / "ledger.jsonl"
    if not ledger_path.is_file() or ledger_path.is_symlink():
        raise ArchiveError("terminal intake ledger is unavailable or is not a regular file")
    try:
        state = json.loads((work / "intake-state.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ArchiveError(f"terminal intake state is unavailable or invalid: {error}") from error
    if not isinstance(state, dict):
        raise ArchiveError("terminal intake state must contain one object")
    intake_id = state.get("intake_id")
    if not isinstance(intake_id, str) or INTAKE_ID.fullmatch(intake_id) is None:
        raise ArchiveError(f"terminal intake id is invalid: {intake_id!r}")
    if state.get("status") not in {
        "first_layer_complete",
        "first_layer_complete_with_preserved_gaps",
    } or state.get("phase") != "effective_first_layer_terminal_recorded":
        raise ArchiveError(
            "intake is not terminal: expected effective_first_layer_terminal_recorded "
            f"with a first-layer completion status, received status={state.get('status')!r} "
            f"phase={state.get('phase')!r}"
        )
    terminal = state.get("effective_first_layer_terminal")
    if not isinstance(terminal, dict):
        raise ArchiveError("terminal intake state has no effective first-layer terminal evidence")
    return state


def _inventory(root: Path) -> list[dict[str, object]]:
    if not root.is_dir():
        raise ArchiveError(f"run directory is unavailable: {root}")
    files: list[dict[str, object]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise ArchiveError(f"run artifact must not be a symbolic link: {relative}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ArchiveError(f"run artifact must be a regular file: {relative}")
        files.append({
            "path": relative,
            "size": path.stat().st_size,
            "sha256": _sha256(path),
        })
    if not files:
        raise ArchiveError("terminal run contains no artifacts")
    return files


def _manifest(
    *, state: dict[str, object], files: list[dict[str, object]]
) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": 1,
        "artifact_type": CONTRACT,
        "intake_id": state["intake_id"],
        "terminal_status": state["status"],
        "terminal_phase": state["phase"],
        "file_count": len(files),
        "total_bytes": sum(int(item["size"]) for item in files),
        "files": files,
    }
    value["archive_sha256"] = hashlib.sha256(_canonical(value)).hexdigest()
    return value


def _read_manifest(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ArchiveError(f"archive manifest is unavailable or invalid: {error}") from error
    if not isinstance(value, dict):
        raise ArchiveError("archive manifest must contain one object")
    digest = value.get("archive_sha256")
    unsigned = {key: item for key, item in value.items() if key != "archive_sha256"}
    expected = hashlib.sha256(_canonical(unsigned)).hexdigest()
    if digest != expected:
        raise ArchiveError(
            f"archive manifest digest mismatch: received {digest!r}, expected {expected!r}"
        )
    return value


def _validate_existing(
    target: Path,
    *,
    state: dict[str, object],
    source_files: list[dict[str, object]],
) -> dict[str, object]:
    manifest = _read_manifest(target / "archive-manifest.json")
    expected = _manifest(state=state, files=source_files)
    if manifest != expected:
        raise ArchiveError(
            "existing archive does not match the completed run; preserve both versions "
            "under distinct intake identities rather than overwriting"
        )
    archived_files = _inventory(target / "run")
    if archived_files != source_files:
        raise ArchiveError("existing archive bytes no longer match its completed run manifest")
    return {
        "status": "archive_reused",
        "intake_id": state["intake_id"],
        "archive": str(target),
        "manifest": str(target / "archive-manifest.json"),
        "archive_sha256": manifest["archive_sha256"],
        "file_count": manifest["file_count"],
        "total_bytes": manifest["total_bytes"],
    }


def archive_terminal_run(
    work: Path, *, archive_root: Path = DEFAULT_ARCHIVE_ROOT
) -> dict[str, object]:
    work = work.expanduser().resolve()
    archive_root = archive_root.expanduser().resolve()
    if archive_root == work or archive_root.is_relative_to(work):
        raise ArchiveError(
            "archive root must be outside the source run directory to prevent recursive copying"
        )
    state = _read_state(work)
    source_files = _inventory(work)
    intake_id = str(state["intake_id"])
    target = archive_root / intake_id
    if target.exists():
        return _validate_existing(target, state=state, source_files=source_files)

    archive_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{intake_id}.", dir=archive_root))
    try:
        copied = staging / "run"
        shutil.copytree(work, copied)
        after_copy_source = _inventory(work)
        copied_files = _inventory(copied)
        if after_copy_source != source_files:
            raise ArchiveError("source run changed while it was being archived")
        if copied_files != source_files:
            raise ArchiveError("copied archive bytes do not match the source run")
        manifest = _manifest(state=state, files=source_files)
        manifest_path = staging / "archive-manifest.json"
        manifest_path.write_bytes(_canonical(manifest) + b"\n")
        if _read_manifest(manifest_path) != manifest:
            raise ArchiveError("written archive manifest failed immediate verification")
        os.replace(staging, target)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return {
        "status": "archive_created",
        "intake_id": intake_id,
        "archive": str(target),
        "manifest": str(target / "archive-manifest.json"),
        "archive_sha256": manifest["archive_sha256"],
        "file_count": manifest["file_count"],
        "total_bytes": manifest["total_bytes"],
    }


def archive_if_terminal(
    work: Path, *, archive_root: Path = DEFAULT_ARCHIVE_ROOT
) -> dict[str, object] | None:
    state_path = work.expanduser().resolve() / "intake-state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ArchiveError(f"intake state is unavailable or invalid: {error}") from error
    if not isinstance(state, dict):
        raise ArchiveError("intake state must contain one object")
    terminal_status = state.get("status") in {
        "first_layer_complete",
        "first_layer_complete_with_preserved_gaps",
    }
    terminal_phase = state.get("phase") == "effective_first_layer_terminal_recorded"
    if not terminal_status and not terminal_phase:
        return None
    if terminal_status != terminal_phase:
        raise ArchiveError(
            "intake terminal status and phase disagree: "
            f"status={state.get('status')!r}, phase={state.get('phase')!r}"
        )
    return archive_terminal_run(work, archive_root=archive_root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--archive-root", type=Path, default=DEFAULT_ARCHIVE_ROOT)
    args = parser.parse_args()
    try:
        result = archive_terminal_run(args.work, archive_root=args.archive_root)
    except ArchiveError as error:
        print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
        return 3
    print(json.dumps({"ok": True, **result}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
