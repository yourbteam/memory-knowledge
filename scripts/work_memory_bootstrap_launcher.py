#!/usr/bin/env python3
"""Execute an activated, authenticated bootstrap snapshot through an immutable launcher."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import tempfile
import types
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER_PATH = Path(__file__).resolve()
RECEIPT_ROOT = Path("/private/tmp/work-memory")
LAUNCHER_LOGICAL_PATH = "scripts/work_memory_bootstrap_launcher.py"
BOOTSTRAP_LOGICAL_PATH = "scripts/work_memory_bootstrap.py"


class LauncherError(Exception):
    def __init__(self, code: str, exit_code: int = 4):
        super().__init__(code)
        self.code = code
        self.exit_code = exit_code


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_json(path: Path, error: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise LauncherError(error) from exc
    if not isinstance(value, dict):
        raise LauncherError(error)
    return value


def _load_snapshot(argv: Sequence[str]) -> tuple[types.ModuleType, Path]:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("command")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--state")
    known, _ = parser.parse_known_args(argv)
    state_path = (
        Path(known.state).resolve()
        if known.state else RECEIPT_ROOT / known.task_id / "active.json"
    )
    selection_path = RECEIPT_ROOT / known.task_id / "selection.json"
    state = _read_json(state_path, "launcher-invalid-active-state")
    selection = _read_json(selection_path, "launcher-invalid-selection-receipt")
    selected = {
        (item["repository_key"], item["path"]): item["sha256"]
        for item in selection.get("source_bundle", [])
    }
    launcher_hash = selected.get(("memory-knowledge", LAUNCHER_LOGICAL_PATH))
    bootstrap_hash = selected.get(("memory-knowledge", BOOTSTRAP_LOGICAL_PATH))
    if (
        launcher_hash is None
        or bootstrap_hash is None
        or state.get("bootstrap_launcher_sha256") != launcher_hash
        or state.get("bootstrap_sha256") != bootstrap_hash
        or _sha256(LAUNCHER_PATH.read_bytes()) != launcher_hash
    ):
        raise LauncherError("launcher-trust-mismatch")
    try:
        bootstrap_bytes = base64.b64decode(state["sealed_bootstrap_b64"], validate=True)
    except (KeyError, ValueError) as exc:
        raise LauncherError("launcher-invalid-sealed-bootstrap") from exc
    if _sha256(bootstrap_bytes) != bootstrap_hash:
        raise LauncherError("launcher-bootstrap-snapshot-mismatch")
    module = types.ModuleType("_sealed_work_memory_bootstrap")
    module.__file__ = str(ROOT / BOOTSTRAP_LOGICAL_PATH)
    module.__package__ = ""
    try:
        exec(compile(bootstrap_bytes, module.__file__, "exec"), module.__dict__)
    except Exception as exc:
        raise LauncherError("launcher-bootstrap-load-failed") from exc
    handle = tempfile.NamedTemporaryFile(prefix="sealed-work-memory-bootstrap-", delete=False)
    try:
        handle.write(bootstrap_bytes)
        handle.flush()
    finally:
        handle.close()
    sealed_path = Path(handle.name)
    module.BOOTSTRAP_PATH = sealed_path
    module.RECEIPT_ROOT = RECEIPT_ROOT
    return module, sealed_path


def main(argv: Sequence[str] | None = None) -> int:
    values = list(argv if argv is not None else sys.argv[1:])
    sealed_path: Path | None = None
    try:
        module, sealed_path = _load_snapshot(values)
        return int(module.main(values))
    except LauncherError as exc:
        print(json.dumps({"ok": False, "error": exc.code}, sort_keys=True), file=sys.stderr)
        return exc.exit_code
    except (OSError, TypeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__}, sort_keys=True), file=sys.stderr)
        return 5
    finally:
        if sealed_path is not None:
            sealed_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
