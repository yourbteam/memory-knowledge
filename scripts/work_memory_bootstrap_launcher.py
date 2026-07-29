#!/usr/bin/env python3
"""Execute an activated, authenticated bootstrap snapshot through an immutable launcher."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import sys
import tempfile
import types
from pathlib import Path
from typing import Any, Sequence

try:
    from scripts import work_memory as current_work_memory
    from scripts import work_memory_bootstrap as current_bootstrap
except ModuleNotFoundError:  # direct script execution
    import work_memory as current_work_memory  # type: ignore
    import work_memory_bootstrap as current_bootstrap  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER_PATH = Path(__file__).resolve()
RECEIPT_ROOT = Path("/private/tmp/work-memory")
LAUNCHER_LOGICAL_PATH = "scripts/work_memory_bootstrap_launcher.py"
BOOTSTRAP_LOGICAL_PATH = "scripts/work_memory_bootstrap.py"
CONTROLLER_LOGICAL_PATH = "scripts/work_memory.py"
TRUST_ANCHOR_PATHS = frozenset({
    CONTROLLER_LOGICAL_PATH, BOOTSTRAP_LOGICAL_PATH, LAUNCHER_LOGICAL_PATH,
})


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


def _validate_current_ownership(
    task_id: str, state_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    classification_path = RECEIPT_ROOT / task_id / "classification.json"
    selection_path = RECEIPT_ROOT / task_id / "selection.json"
    classification = _read_json(
        classification_path, "launcher-invalid-classification-receipt",
    )
    selection = _read_json(selection_path, "launcher-invalid-selection-receipt")
    state = _read_json(state_path, "launcher-invalid-active-state")
    try:
        owner_state = current_work_memory.validate_ownership_receipt(
            task_id, classification,
        )
        current_work_memory.validate_ownership_receipt(task_id, selection)
    except current_work_memory.WorkMemoryError as exc:
        raise LauncherError(exc.code, exc.exit_code) from exc
    class_hash = _sha256(current_work_memory.canonical_bytes(classification))
    selection_hash = _sha256(current_work_memory.canonical_bytes(selection))
    expected = {
        "task_id": task_id,
        "classification_receipt_hash": class_hash,
        "selection_receipt_hash": selection_hash,
        **current_work_memory._ownership_receipt_fields(task_id, owner_state),
    }
    if (
        selection.get("classification_receipt_hash") != class_hash
        or any(state.get(key) != value for key, value in expected.items())
    ):
        raise LauncherError("launcher-ownership-receipt-mismatch")
    return state, selection


def _parse_invocation(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("command")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--state")
    parser.add_argument("--run-id")
    parser.add_argument("--changed-artifact", action="append", default=[])
    known, _ = parser.parse_known_args(argv)
    return known


def _decode_snapshot(state: dict[str, Any], field: str, error: str) -> bytes:
    try:
        return base64.b64decode(state[field], validate=True)
    except (KeyError, TypeError, ValueError) as exc:
        raise LauncherError(error) from exc


def _read_head_launcher_blob() -> bytes:
    completed = subprocess.run(
        ["git", "show", f"HEAD:{LAUNCHER_LOGICAL_PATH}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise LauncherError("legacy-launcher-git-blob-unavailable")
    return completed.stdout


def _load_sealed_controller(
    state: dict[str, Any], selection: dict[str, Any],
) -> types.ModuleType:
    selected = {
        (item["repository_key"], item["path"]): item["sha256"]
        for item in selection.get("source_bundle", [])
    }
    controller_hash = selected.get(("memory-knowledge", CONTROLLER_LOGICAL_PATH))
    controller_bytes = _decode_snapshot(
        state, "sealed_controller_b64", "legacy-controller-snapshot-invalid",
    )
    if (
        controller_hash is None
        or state.get("sealed_controller_sha256") != controller_hash
        or _sha256(controller_bytes) != controller_hash
    ):
        raise LauncherError("legacy-controller-snapshot-invalid")
    module = types.ModuleType("_legacy_sealed_work_memory")
    module.__file__ = str(ROOT / CONTROLLER_LOGICAL_PATH)
    module.__package__ = ""
    try:
        exec(compile(controller_bytes, module.__file__, "exec"), module.__dict__)
    except Exception as exc:
        raise LauncherError("legacy-controller-snapshot-load-failed") from exc
    return module


def _artifact_key(value: Any) -> tuple[str, str]:
    if isinstance(value, str):
        return "memory-knowledge", value
    if isinstance(value, dict):
        return value["repository_key"], value["path"]
    raise LauncherError("legacy-rotation-artifact-invalid")


def _validate_legacy_rotation(
    known: argparse.Namespace,
    state: dict[str, Any],
    selection: dict[str, Any],
    launcher_blob: bytes,
) -> None:
    if state.get("sealed_bootstrap_launcher_b64") is not None:
        raise LauncherError("legacy-launcher-recovery-not-applicable")
    if known.command != "correct" or not known.run_id:
        raise LauncherError("legacy-launcher-recovery-command-invalid")
    document = Path(selection.get("document", ""))
    if (
        not document.is_file()
        or "python3 scripts/work_memory_bootstrap_launcher.py correct"
        not in document.read_text()
    ):
        raise LauncherError("legacy-launcher-command-not-grounded")
    selected = {
        (item["repository_key"], item["path"]): item["sha256"]
        for item in selection.get("source_bundle", [])
    }
    launcher_hash = selected.get(("memory-knowledge", LAUNCHER_LOGICAL_PATH))
    if (
        launcher_hash is None
        or state.get("bootstrap_launcher_sha256") != launcher_hash
        or _sha256(launcher_blob) != launcher_hash
    ):
        raise LauncherError("legacy-launcher-git-blob-mismatch")
    bootstrap_hash = selected.get(("memory-knowledge", BOOTSTRAP_LOGICAL_PATH))
    bootstrap_bytes = _decode_snapshot(
        state, "sealed_bootstrap_b64", "legacy-bootstrap-snapshot-invalid",
    )
    if (
        bootstrap_hash is None
        or state.get("bootstrap_sha256") != bootstrap_hash
        or _sha256(bootstrap_bytes) != bootstrap_hash
    ):
        raise LauncherError("legacy-bootstrap-snapshot-invalid")

    controller = _load_sealed_controller(state, selection)
    current_bundle, _, lineage = controller.resolve_bundle(
        mode=selection["mode"], subject_id=selection["subject_id"],
        document=Path(selection["document"]), manifest=Path(selection["manifest"]),
        repo_roots_file=selection.get("repository_roots_file"),
        include_bootstrap_trust_anchors=True,
    )
    if lineage != selection.get("lineage_id"):
        raise LauncherError("legacy-launcher-lineage-mismatch")
    try:
        artifacts, _ = controller._artifact_hashes(
            known.changed_artifact, selection.get("repository_roots_file"),
        )
    except controller.WorkMemoryError as exc:
        raise LauncherError("legacy-rotation-artifact-invalid") from exc
    old_map = {
        (item["repository_key"], item["path"]): item["sha256"]
        for item in selection["source_bundle"]
    }
    current_map = {
        (item["repository_key"], item["path"]): item["sha256"]
        for item in current_bundle
    }
    drifted = {
        key for key in old_map.keys() | current_map.keys()
        if old_map.get(key) != current_map.get(key)
    }
    artifact_keys = {_artifact_key(item) for item in artifacts}
    trust_keys = {("memory-knowledge", path) for path in TRUST_ANCHOR_PATHS}
    if artifact_keys != drifted or not trust_keys <= drifted:
        raise LauncherError("legacy-rotation-artifact-drift-mismatch")


def _install_current_correction_contract(controller: types.ModuleType) -> None:
    """Run the current atomic correction reducer inside sealed controller globals."""
    controller._effective_correction_bundle = (
        current_work_memory._effective_correction_bundle
    )
    current = current_work_memory.cmd_correct
    bridged = types.FunctionType(
        current.__code__, controller.__dict__, current.__name__,
        current.__defaults__, current.__closure__,
    )
    bridged.__kwdefaults__ = current.__kwdefaults__
    controller.cmd_correct = bridged


def _install_current_bootstrap_correction_contract(
    bootstrap_module: types.ModuleType,
) -> None:
    """Run current correction prevalidation inside sealed bootstrap globals."""
    current = current_bootstrap.cmd_correct
    bridged = types.FunctionType(
        current.__code__, bootstrap_module.__dict__, current.__name__,
        current.__defaults__, current.__closure__,
    )
    bridged.__kwdefaults__ = current.__kwdefaults__
    bootstrap_module.cmd_correct = bridged


def _extend_prior_bootstrap_parser(module: types.ModuleType) -> None:
    """Add the explicit co-blocker option to a selected historical bootstrap."""
    original = module.build_parser

    def build_parser():
        parser = original()
        for action in parser._actions:
            choices = getattr(action, "choices", None)
            if not isinstance(choices, dict) or "correct" not in choices:
                continue
            correct = choices["correct"]
            if not any("--co-blocker-id" in item.option_strings for item in correct._actions):
                correct.add_argument("--co-blocker-id", action="append")
            return parser
        raise LauncherError("prior-bootstrap-correct-parser-missing")

    module.build_parser = build_parser


def _govern_prior_launcher(
    module: types.ModuleType,
    known: argparse.Namespace,
    state_path: Path,
) -> None:
    original_load_snapshot = module._load_snapshot

    def governed_snapshot(argv: Sequence[str]):
        _validate_current_ownership(known.task_id, state_path)
        bootstrap_module, sealed_path = original_load_snapshot(argv)
        _extend_prior_bootstrap_parser(bootstrap_module)
        original_load_context = bootstrap_module._load_context

        def governed_context(args: argparse.Namespace):
            _validate_current_ownership(known.task_id, state_path)
            context = original_load_context(args)
            controller = context.get("module") if isinstance(context, dict) else None
            if controller is None:
                raise LauncherError("legacy-bootstrap-context-invalid")
            controller.load_ledger = current_work_memory.load_ledger
            controller.transact = current_work_memory.transact
            _install_current_correction_contract(controller)
            return context

        def governed_run_matches(
            controller: Any, events: list[dict[str, Any]], run_id: str,
            selection: dict[str, Any], state: dict[str, Any],
            classification: dict[str, Any],
        ):
            start, related = controller._run_state(events, run_id)
            expected = {
                "subject_id": selection["subject_id"],
                "lineage_id": selection["lineage_id"],
                "mode": selection["mode"],
                "source_bundle": selection["source_bundle"],
                "source_bundle_hash": selection["source_bundle_hash"],
                "operation_kind": classification["operation_kind"],
            }
            if any(start.get(key) != value for key, value in expected.items()):
                raise bootstrap_module.BootstrapError("bootstrap-run-mismatch")
            try:
                current_work_memory.validate_run_writer_continuity(
                    events, known.task_id, run_id, start, selection,
                )
            except current_work_memory.WorkMemoryError as exc:
                raise bootstrap_module.BootstrapError("bootstrap-run-mismatch") from exc
            return start, related

        bootstrap_module.current_work_memory = current_work_memory
        bootstrap_module._load_context = governed_context
        bootstrap_module._run_matches_selection = governed_run_matches
        _install_current_bootstrap_correction_contract(bootstrap_module)
        return bootstrap_module, sealed_path

    module._load_snapshot = governed_snapshot


def _load_prior_launcher(
    argv: Sequence[str],
) -> tuple[types.ModuleType, Path] | None:
    if LAUNCHER_PATH.resolve() != (ROOT / LAUNCHER_LOGICAL_PATH).resolve():
        raise LauncherError("launcher-path-mismatch")
    known = _parse_invocation(argv)
    state_path = (
        Path(known.state).resolve()
        if known.state else RECEIPT_ROOT / known.task_id / "active.json"
    )
    state, selection = _validate_current_ownership(known.task_id, state_path)
    selected = {
        (item["repository_key"], item["path"]): item["sha256"]
        for item in selection.get("source_bundle", [])
    }
    launcher_hash = selected.get(("memory-knowledge", LAUNCHER_LOGICAL_PATH))
    if launcher_hash is None or state.get("bootstrap_launcher_sha256") != launcher_hash:
        raise LauncherError("launcher-trust-mismatch")
    if _sha256(LAUNCHER_PATH.read_bytes()) == launcher_hash:
        return None

    encoded = state.get("sealed_bootstrap_launcher_b64")
    legacy = encoded is None
    if legacy:
        launcher_blob = _read_head_launcher_blob()
        _validate_legacy_rotation(known, state, selection, launcher_blob)
    else:
        try:
            launcher_blob = base64.b64decode(encoded, validate=True)
        except (TypeError, ValueError) as exc:
            raise LauncherError("launcher-snapshot-invalid") from exc
        if _sha256(launcher_blob) != launcher_hash:
            raise LauncherError("launcher-snapshot-invalid")

    handle = tempfile.NamedTemporaryFile(prefix="sealed-work-memory-launcher-", delete=False)
    try:
        handle.write(launcher_blob)
        handle.flush()
    finally:
        handle.close()
    sealed_path = Path(handle.name)
    module = types.ModuleType("_sealed_work_memory_bootstrap_launcher")
    module.__file__ = str(ROOT / LAUNCHER_LOGICAL_PATH)
    module.__package__ = ""
    try:
        exec(compile(launcher_blob, module.__file__, "exec"), module.__dict__)
    except Exception as exc:
        sealed_path.unlink(missing_ok=True)
        raise LauncherError("launcher-snapshot-load-failed") from exc
    module.ROOT = ROOT
    module.RECEIPT_ROOT = RECEIPT_ROOT
    module.LAUNCHER_PATH = sealed_path
    if hasattr(module, "_load_prior_launcher"):
        module._load_prior_launcher = lambda argv: None
    _govern_prior_launcher(module, known, state_path)
    return module, sealed_path


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
    state, selection = _validate_current_ownership(known.task_id, state_path)
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
    original_load_context = getattr(module, "_load_context", None)
    if not callable(original_load_context):
        sealed_path.unlink(missing_ok=True)
        raise LauncherError("launcher-bootstrap-ownership-bridge-missing")

    def governed_load_context(args: argparse.Namespace):
        _validate_current_ownership(known.task_id, state_path)
        context = original_load_context(args)
        controller = context.get("module") if isinstance(context, dict) else None
        if controller is None:
            raise LauncherError("launcher-bootstrap-context-invalid")
        controller.load_ledger = current_work_memory.load_ledger
        controller.transact = current_work_memory.transact
        _install_current_correction_contract(controller)
        return context

    module.current_work_memory = current_work_memory
    module._load_context = governed_load_context
    _install_current_bootstrap_correction_contract(module)
    return module, sealed_path


def main(argv: Sequence[str] | None = None) -> int:
    values = list(argv if argv is not None else sys.argv[1:])
    sealed_path: Path | None = None
    try:
        prior = _load_prior_launcher(values)
        if prior is not None:
            prior_module, sealed_path = prior
            return int(prior_module.main(values))
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
