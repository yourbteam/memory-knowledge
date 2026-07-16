#!/usr/bin/env python3
"""Atomically create, select, activate, and start a missing-sequence discovery."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shlex
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

try:
    from scripts import sequence_discovery_log, sequence_guard, work_memory
except ImportError:
    import sequence_discovery_log  # type: ignore
    import sequence_guard  # type: ignore
    import work_memory  # type: ignore


LOCK_PATH = Path("/private/tmp/work-memory/.discovery-bootstrap.lock")
SPEC_KEYS = {
    "schema_version", "task_id", "operation_kind", "date", "sequence_name",
    "outcome", "why_repeatable", "steps", "inputs", "failure_handling",
    "verified_path", "dependencies",
}
REQUIRED_SPEC_KEYS = {
    "schema_version", "task_id", "operation_kind", "date", "sequence_name",
    "outcome", "why_repeatable", "steps",
}
STEP_KEYS = {"step", "command", "result", "note"}
DEPENDENCY_KEYS = {"kind", "repository_key", "path_or_sequence_id"}
BOOTSTRAP_NAMESPACE = uuid.UUID("59080b26-4fd4-43bf-993e-4a988c95b223")


def _load_json(value: str) -> Any:
    candidate = Path(value)
    raw = candidate.read_text(encoding="utf-8") if candidate.is_file() else value
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise work_memory.WorkMemoryError("invalid-bootstrap-spec-json", 2) from exc


def _text(value: Any, field: str, *, forbid_tbd: bool = False) -> str:
    if not isinstance(value, str):
        raise work_memory.WorkMemoryError(f"invalid-bootstrap-{field}", 2)
    normalized = value.strip()
    if not normalized or "\r" in normalized or "\n" in normalized:
        raise work_memory.WorkMemoryError(f"invalid-bootstrap-{field}", 2)
    if forbid_tbd and "TBD" in normalized.upper():
        raise work_memory.WorkMemoryError(f"invalid-bootstrap-{field}", 2)
    return normalized


def _validate_placeholders(command: str) -> None:
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        raise work_memory.WorkMemoryError("invalid-bootstrap-command", 2) from exc
    placeholder_tokens = {token for token in tokens if token.startswith("<") or token.endswith(">")}
    if any(not re.fullmatch(r"<[A-Za-z0-9_.:-]+>", token) for token in placeholder_tokens):
        raise work_memory.WorkMemoryError("invalid-bootstrap-command-placeholder", 2)
    scrubbed = " ".join(tokens)
    if ("<" in scrubbed or ">" in scrubbed) and not placeholder_tokens:
        raise work_memory.WorkMemoryError("invalid-bootstrap-command-placeholder", 2)


def normalize_spec(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) - SPEC_KEYS or REQUIRED_SPEC_KEYS - set(raw):
        raise work_memory.WorkMemoryError("invalid-bootstrap-spec-shape", 2)
    if raw.get("schema_version") != 1 or isinstance(raw.get("schema_version"), bool):
        raise work_memory.WorkMemoryError("unsupported-bootstrap-spec-version", 2)
    task_id = work_memory.require_id(raw.get("task_id"), "task-id")
    operation_kind = raw.get("operation_kind")
    if operation_kind not in work_memory.OPERATION_KINDS:
        raise work_memory.WorkMemoryError("invalid-bootstrap-operation-kind", 2)
    date_text = _text(raw.get("date"), "date")
    try:
        if datetime.strptime(date_text, "%Y-%m-%d").strftime("%Y-%m-%d") != date_text:
            raise ValueError
    except ValueError as exc:
        raise work_memory.WorkMemoryError("invalid-bootstrap-date", 2) from exc

    steps_raw = raw.get("steps")
    if not isinstance(steps_raw, list) or not steps_raw:
        raise work_memory.WorkMemoryError("invalid-bootstrap-steps", 2)
    steps: list[dict[str, str]] = []
    labels: set[str] = set()
    for item in steps_raw:
        if not isinstance(item, dict) or set(item) != STEP_KEYS:
            raise work_memory.WorkMemoryError("invalid-bootstrap-step-shape", 2)
        row = {key: _text(item.get(key), f"step-{key}") for key in STEP_KEYS}
        if any("|" in value for value in row.values()) or row["step"] in labels:
            raise work_memory.WorkMemoryError("invalid-bootstrap-step-row", 2)
        _validate_placeholders(row["command"])
        labels.add(row["step"])
        steps.append(row)

    inputs: list[str] | None = None
    if "inputs" in raw:
        if not isinstance(raw["inputs"], list):
            raise work_memory.WorkMemoryError("invalid-bootstrap-inputs", 2)
        inputs = [_text(item, "input", forbid_tbd=True) for item in raw["inputs"]]
        if len(inputs) != len(set(inputs)):
            raise work_memory.WorkMemoryError("duplicate-bootstrap-input", 2)

    dependencies_raw = raw.get("dependencies", [])
    if not isinstance(dependencies_raw, list):
        raise work_memory.WorkMemoryError("invalid-bootstrap-dependencies", 2)
    dependencies: list[dict[str, str]] = []
    for item in dependencies_raw:
        if not isinstance(item, dict) or set(item) != DEPENDENCY_KEYS:
            raise work_memory.WorkMemoryError("invalid-dependency-entry", 2)
        dependency = {key: _text(item.get(key), f"dependency-{key}") for key in DEPENDENCY_KEYS}
        if dependency["kind"] not in {"file", "glob", "sequence"}:
            raise work_memory.WorkMemoryError("invalid-dependency-kind", 2)
        dependencies.append(dependency)

    normalized = {
        "schema_version": 1,
        "task_id": task_id,
        "operation_kind": operation_kind,
        "date": date_text,
        "sequence_name": _text(raw.get("sequence_name"), "sequence-name"),
        "outcome": _text(raw.get("outcome"), "outcome"),
        "why_repeatable": _text(raw.get("why_repeatable"), "why-repeatable"),
        "steps": steps,
        "dependencies": dependencies,
    }
    if inputs is not None:
        normalized["inputs"] = inputs
    if "failure_handling" in raw:
        normalized["failure_handling"] = _text(
            raw["failure_handling"], "failure-handling", forbid_tbd=True,
        )
    if "verified_path" in raw:
        normalized["verified_path"] = _text(
            raw["verified_path"], "verified-path", forbid_tbd=True,
        )
    work_memory._validate_work_only(normalized)
    return normalized


def _validate_dependencies(
    dependencies: Sequence[dict[str, str]], repo_roots_file: str | None,
) -> None:
    roots = work_memory._repo_roots(repo_roots_file)
    for dependency in dependencies:
        kind = dependency["kind"]
        repository_key = dependency["repository_key"]
        value = dependency["path_or_sequence_id"]
        if kind == "sequence":
            document = work_memory.ROOT / "operations/sequences" / value / "sequence.md"
            work_memory.resolve_bundle(
                mode="registered", subject_id=value, document=document,
                manifest=document.with_name("dependencies.json"),
                repo_roots_file=repo_roots_file,
            )
            continue
        if repository_key not in roots:
            raise work_memory.WorkMemoryError("missing-repository-root", 3)
        if kind == "file":
            work_memory._safe_file(roots[repository_key], value)
        else:
            matches = sorted(roots[repository_key].glob(value))
            if not matches or any(not path.is_file() for path in matches):
                raise work_memory.WorkMemoryError("unmatched-dependency-glob", 3)


def _read_json(path: Path, error: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise work_memory.WorkMemoryError(error, 4) from exc
    if not isinstance(value, dict):
        raise work_memory.WorkMemoryError(error, 4)
    return value


def _receipt_hash(path: Path) -> str:
    return work_memory.sha256_bytes(path.read_bytes())


def _matching_run(
    event_id: str, expected: dict[str, Any], *, fail_if_mismatch: bool = True,
) -> dict[str, Any] | None:
    events, _ = work_memory.load_ledger()
    event = next((item for item in events if item.get("event_id") == event_id), None)
    if event is None:
        return None
    if event.get("event_type") != "run_started" or any(
        event.get(key) != value for key, value in expected.items()
    ):
        if fail_if_mismatch:
            raise work_memory.WorkMemoryError("bootstrap-run-event-conflict", 4)
        return None
    return event


def _cleanup(created: Sequence[Path], task_dir: Path) -> None:
    retained: list[str] = []
    for path in reversed(created):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            retained.append(str(path))
    try:
        task_dir.rmdir()
    except OSError:
        pass
    if retained:
        raise work_memory.WorkMemoryError(
            "bootstrap-partial-state-retained:" + ",".join(sorted(retained)), 5,
        )


def bootstrap(spec: dict[str, Any], *, root: Path, repo_roots_file: str | None) -> dict[str, Any]:
    work_memory.configure_root(root)
    resolved_roots_file = str(Path(repo_roots_file).expanduser().resolve()) if repo_roots_file else None
    _validate_dependencies(spec["dependencies"], resolved_roots_file)
    request = {"spec": spec, "repo_roots_file": resolved_roots_file}
    request_digest = work_memory.sha256_bytes(work_memory.canonical_bytes(request))
    task_id = spec["task_id"]
    task_dir = work_memory.RECEIPT_ROOT / task_id
    created: list[Path] = []
    run_id = str(uuid.uuid5(BOOTSTRAP_NAMESPACE, f"run:{request_digest}"))
    event_id = str(uuid.uuid5(BOOTSTRAP_NAMESPACE, f"event:{request_digest}"))

    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        document_path = (
            root / sequence_discovery_log.DISCOVERY_DIR
            / f"{spec['date']}-{sequence_discovery_log._slug(spec['sequence_name'])}.md"
        )
        manifest_path = document_path.with_suffix(".dependencies.json")
        created_at = work_memory.utc_now()
        if document_path.is_file():
            existing = document_path.read_text(encoding="utf-8")
            created_at = sequence_discovery_log._metadata(existing, "CreatedAtUtc") or ""
            if not created_at:
                raise work_memory.WorkMemoryError("bootstrap-discovery-conflict", 4)
        document_path, expected_text, manifest = sequence_discovery_log.render_discovery_bundle(
            root=root,
            date_text=spec["date"],
            sequence_name=spec["sequence_name"],
            outcome=spec["outcome"],
            why_repeatable=spec["why_repeatable"],
            created_at_utc=created_at,
            steps=spec["steps"],
            inputs=spec.get("inputs"),
            failure_handling=spec.get("failure_handling"),
            verified_path=spec.get("verified_path"),
            dependencies=spec["dependencies"],
            bootstrap_request_sha256=request_digest,
        )

        if document_path.exists():
            if document_path.read_text(encoding="utf-8") != expected_text:
                raise work_memory.WorkMemoryError("bootstrap-discovery-conflict", 4)
        elif manifest_path.exists():
            raise work_memory.WorkMemoryError("bootstrap-discovery-conflict", 4)
        else:
            sequence_discovery_log._atomic(document_path, expected_text.encode())
            created.append(document_path)

        if manifest_path.exists():
            if _read_json(manifest_path, "bootstrap-discovery-conflict") != manifest:
                raise work_memory.WorkMemoryError("bootstrap-discovery-conflict", 4)
        else:
            sequence_discovery_log._write_json(manifest_path, manifest)
            created.append(manifest_path)

        receipt_paths = {
            name: work_memory.receipt_path(task_id, name)
            for name in ("classification", "selection", "active")
        }
        try:
            meaningful_steps = max(3, len(spec["steps"]))
            classification_path = receipt_paths["classification"]
            if classification_path.exists():
                classification, class_hash, _ = work_memory.load_receipt(task_id, "classification")
                expected_class = {
                    "task_id": task_id, "operation_kind": spec["operation_kind"],
                    "repeatable": True, "meaningful_steps": meaningful_steps,
                    "verdict": "operational",
                }
                if any(classification.get(key) != value for key, value in expected_class.items()):
                    raise work_memory.WorkMemoryError("bootstrap-classification-conflict", 4)
            else:
                classification = work_memory.cmd_classify(argparse.Namespace(
                    task_id=task_id, operation_kind=spec["operation_kind"],
                    repeatable="yes", meaningful_steps=meaningful_steps,
                ))
                created.append(classification_path)
                class_hash = classification["classification_receipt_hash"]

            bundle, bundle_hash, lineage = work_memory.resolve_bundle(
                mode="discovery", subject_id=manifest["lineage_id"],
                document=document_path, manifest=manifest_path,
                repo_roots_file=resolved_roots_file,
                include_bootstrap_trust_anchors=True,
            )
            selection_path = receipt_paths["selection"]
            if selection_path.exists():
                selection, selection_hash, _ = work_memory.load_receipt(task_id, "selection")
                expected_selection = {
                    "mode": "discovery", "subject_id": manifest["lineage_id"],
                    "lineage_id": lineage, "document": str(document_path),
                    "manifest": str(manifest_path), "source_bundle": bundle,
                    "source_bundle_hash": bundle_hash,
                    "classification_receipt_hash": class_hash,
                    "repository_roots_file": resolved_roots_file,
                }
                if any(selection.get(key) != value for key, value in expected_selection.items()):
                    raise work_memory.WorkMemoryError("bootstrap-selection-conflict", 4)
            else:
                selection = work_memory.cmd_select(argparse.Namespace(
                    task_id=task_id, sequence_id=None, discovery_log=str(document_path),
                    fingerprint=None, verification_successor_of=None,
                    verifies_correction_id=None, repo_roots_file=resolved_roots_file,
                ))
                created.append(selection_path)
                selection_hash = selection["selection_receipt_hash"]

            active_path = receipt_paths["active"]
            if active_path.exists():
                active = _read_json(active_path, "bootstrap-active-state-conflict")
                expected_active = {
                    "task_id": task_id, "mode": "discovery",
                    "subject_id": manifest["lineage_id"], "lineage_id": lineage,
                    "document": str(document_path),
                    "classification_receipt_hash": class_hash,
                    "selection_receipt_hash": selection_hash,
                    "source_bundle_hash": bundle_hash,
                }
                if any(active.get(key) != value for key, value in expected_active.items()):
                    raise work_memory.WorkMemoryError("bootstrap-active-state-conflict", 4)
            else:
                directive_state = os.environ.get(
                    "MK_DIRECTIVE_STATE_PATH", str(sequence_guard.DEFAULT_DIRECTIVE_STATE_PATH),
                )
                sequence_guard.cmd_activate(argparse.Namespace(
                    task_id=task_id, root=str(root), state=None, sequence_doc=None,
                    discovery_log=str(document_path), sequence_id=None,
                    directives_path=str(root / "working-agreement/DIRECTIVES.md"),
                    directive_state=directive_state,
                    directive_max_age_minutes=sequence_guard.DEFAULT_MAX_AGE_MINUTES,
                ))
                created.append(active_path)

            repository_roots = {
                key: str(path)
                for key, path in work_memory._repo_roots(resolved_roots_file).items()
            }
            expected_run = {
                "run_id": run_id, "subject_id": manifest["lineage_id"],
                "lineage_id": lineage, "mode": "discovery",
                "operation_kind": spec["operation_kind"], "source_bundle": bundle,
                "source_bundle_hash": bundle_hash, "repository_roots": repository_roots,
                "classification_receipt_hash": class_hash,
                "selection_receipt_hash": selection_hash,
            }
            existing_run = _matching_run(event_id, expected_run)
            recovered = existing_run is not None
            if existing_run is None:
                try:
                    work_memory.cmd_run_start(argparse.Namespace(
                        task_id=task_id, run_id=run_id, event_id=event_id,
                    ))
                except work_memory.WorkMemoryError:
                    if _matching_run(event_id, expected_run, fail_if_mismatch=False) is None:
                        raise
                    recovered = True

            return {
                "ok": True, "bootstrap_request_sha256": request_digest,
                "discovery_path": str(document_path), "discovery_id": manifest["lineage_id"],
                "manifest_path": str(manifest_path), "task_id": task_id,
                "classification_receipt_hash": class_hash,
                "selection_receipt_hash": selection_hash,
                "source_bundle_hash": bundle_hash, "run_id": run_id,
                "event_id": event_id, "recovered": recovered,
            }
        except Exception:
            if _matching_run(event_id, {}, fail_if_mismatch=False) is None:
                for name, path in receipt_paths.items():
                    if path.exists() and path not in created and name in {"classification", "selection", "active"}:
                        continue
                _cleanup(created, task_dir)
            raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start")
    start.add_argument("--spec", required=True)
    start.add_argument("--root")
    start.add_argument("--repo-roots-file")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        spec = normalize_spec(_load_json(args.spec))
        root = Path(args.root or ".").expanduser().resolve()
        print(json.dumps(
            bootstrap(spec, root=root, repo_roots_file=args.repo_roots_file), sort_keys=True,
        ))
        return 0
    except work_memory.WorkMemoryError as exc:
        print(json.dumps({"ok": False, "error": exc.code}, sort_keys=True), file=sys.stderr)
        return exc.exit_code
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__}, sort_keys=True), file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
