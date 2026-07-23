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
from typing import Any, Mapping, Sequence

try:
    from scripts import sequence_candidate_contract, sequence_discovery_log, sequence_guard, work_memory
except ImportError:
    import sequence_candidate_contract  # type: ignore
    import sequence_discovery_log  # type: ignore
    import sequence_guard  # type: ignore
    import work_memory  # type: ignore


LOCK_PATH = Path("/private/tmp/work-memory/.discovery-bootstrap.lock")
SPEC_KEYS = {
    "schema_version", "task_id", "operation_kind", "date", "sequence_name",
    "outcome", "why_repeatable", "steps", "inputs", "failure_handling",
    "verified_path", "dependencies",
    "candidate_identity", "candidate_fingerprint", "observer_provenance",
}
REQUIRED_SPEC_KEYS = {
    "schema_version", "task_id", "operation_kind", "date", "sequence_name",
    "outcome", "why_repeatable", "steps",
}
STEP_KEYS = {"step", "command", "result", "note"}
DEPENDENCY_KEYS = {"kind", "repository_key", "path_or_sequence_id"}
BOOTSTRAP_NAMESPACE = uuid.UUID("59080b26-4fd4-43bf-993e-4a988c95b223")
PREVENTION_ID_RE = re.compile(r"[0-9a-f]{64}")


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
    v2_fields = {"candidate_identity", "candidate_fingerprint", "observer_provenance"}
    present_v2 = v2_fields & set(raw)
    if present_v2 and present_v2 != v2_fields:
        raise work_memory.WorkMemoryError("incomplete-bootstrap-candidate-identity", 2)
    if present_v2:
        try:
            identity = sequence_candidate_contract.validate_candidate_identity(
                raw["candidate_identity"], raw["candidate_fingerprint"],
            )
        except sequence_candidate_contract.CandidateContractError as exc:
            raise work_memory.WorkMemoryError(exc.code, 2) from exc
        provenance = raw["observer_provenance"]
        if (
            not isinstance(provenance, dict)
            or set(provenance) != {"decision_id", "observer_version", "rule_version"}
            or provenance["observer_version"] != 1 or provenance["rule_version"] != 1
        ):
            raise work_memory.WorkMemoryError("invalid-bootstrap-observer-provenance", 2)
        work_memory.require_uuid(provenance.get("decision_id"), "decision-id")
        normalized.update(
            candidate_identity=identity,
            candidate_fingerprint=raw["candidate_fingerprint"],
            observer_provenance=dict(provenance),
        )
    work_memory._validate_work_only(normalized)
    return normalized


def _validate_dependencies(
    dependencies: Sequence[dict[str, str]], repo_roots_file: str | None,
    repository_roots: dict[str, str] | None = None,
) -> None:
    roots = work_memory._repo_roots(repo_roots_file, snapshot=repository_roots)
    for dependency in dependencies:
        kind = dependency["kind"]
        repository_key = dependency["repository_key"]
        value = dependency["path_or_sequence_id"]
        if kind == "sequence":
            document = work_memory.ROOT / "operations/sequences" / value / "sequence.md"
            work_memory.resolve_bundle(
                mode="registered", subject_id=value, document=document,
                manifest=document.with_name("dependencies.json"),
                repo_roots_file=repo_roots_file, repository_roots=repository_roots,
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


def _prevention_identity(
    effect_id: str | None, preparation_sha256: str | None,
) -> dict[str, str] | None:
    if bool(effect_id) != bool(preparation_sha256):
        raise work_memory.WorkMemoryError("incomplete-prevention-effect-identity", 2)
    if effect_id is None:
        return None
    if (
        PREVENTION_ID_RE.fullmatch(effect_id) is None
        or PREVENTION_ID_RE.fullmatch(str(preparation_sha256)) is None
    ):
        raise work_memory.WorkMemoryError("invalid-prevention-effect-identity", 2)
    return {
        "effect_id": effect_id,
        "preparation_artifact_sha256": str(preparation_sha256),
    }


def _write_prevention_receipt(
    path: Path, *, identity: Mapping[str, str], status: str,
    source_identity: Mapping[str, Any],
) -> dict[str, Any]:
    receipt = {
        "schema_version": 1,
        "owner_sequence_id": "discovery-bootstrap",
        "profile_id": "start",
        **dict(identity),
        "status": status,
        "source_identity": dict(source_identity),
    }
    if path.is_file():
        existing = _read_json(path, "bootstrap-prevention-receipt-invalid")
        if existing == receipt:
            return receipt
        if not (
            existing.get("status") == "PREPARED"
            and status == "APPLIED"
            and all(
                existing.get(key) == receipt.get(key)
                for key in (
                    "schema_version", "owner_sequence_id", "profile_id",
                    "effect_id", "preparation_artifact_sha256", "source_identity",
                )
            )
        ):
            raise work_memory.WorkMemoryError(
                "bootstrap-prevention-receipt-conflict", 4
            )
    work_memory._atomic_write(path, work_memory.canonical_bytes(receipt))
    return receipt


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


def bootstrap(
    spec: dict[str, Any], *, root: Path, repo_roots_file: str | None,
    repository_roots: dict[str, str] | None = None,
    prevention_effect_id: str | None = None,
    prevention_preparation_sha256: str | None = None,
) -> dict[str, Any]:
    prevention_identity = _prevention_identity(
        prevention_effect_id, prevention_preparation_sha256,
    )
    work_memory.configure_root(root)
    if repo_roots_file and repository_roots is not None:
        raise work_memory.WorkMemoryError("bootstrap-repository-roots-conflict", 2)
    resolved_roots_file = str(Path(repo_roots_file).expanduser().resolve()) if repo_roots_file else None
    roots_snapshot = (
        {key: str(path) for key, path in work_memory._repo_roots(snapshot=repository_roots).items()}
        if repository_roots is not None else None
    )
    _validate_dependencies(spec["dependencies"], resolved_roots_file, roots_snapshot)
    request = {"spec": spec, "repo_roots_file": resolved_roots_file}
    if roots_snapshot is not None:
        request["repository_roots"] = roots_snapshot
    if prevention_identity is not None:
        request["prevention_identity"] = prevention_identity
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
        prevention_receipt_path = (
            task_dir / "prevention-effects" / f"{prevention_effect_id}.json"
            if prevention_identity is not None else None
        )
        prevention_source_identity = {
            "bootstrap_request_sha256": request_digest,
            "discovery_path": str(document_path),
            "manifest_path": str(manifest_path),
            "run_id": run_id,
            "event_id": event_id,
        }
        if prevention_receipt_path is not None:
            _write_prevention_receipt(
                prevention_receipt_path,
                identity=prevention_identity,
                status="PREPARED",
                source_identity=prevention_source_identity,
            )
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
            candidate_identity=spec.get("candidate_identity"),
            candidate_fingerprint=spec.get("candidate_fingerprint"),
            observer_provenance=spec.get("observer_provenance"),
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
                repo_roots_file=resolved_roots_file, repository_roots=roots_snapshot,
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
                if roots_snapshot is not None:
                    expected_selection["repository_roots"] = roots_snapshot
                if any(selection.get(key) != value for key, value in expected_selection.items()):
                    raise work_memory.WorkMemoryError("bootstrap-selection-conflict", 4)
            else:
                selection = work_memory.cmd_select(argparse.Namespace(
                    task_id=task_id, sequence_id=None, discovery_log=str(document_path),
                    fingerprint=None, verification_successor_of=None,
                    verifies_correction_id=None, repo_roots_file=resolved_roots_file,
                    repository_roots=roots_snapshot,
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

            durable_roots = roots_snapshot or {
                key: str(path)
                for key, path in work_memory._repo_roots(resolved_roots_file).items()
            }
            expected_run = {
                "run_id": run_id, "subject_id": manifest["lineage_id"],
                "lineage_id": lineage, "mode": "discovery",
                "operation_kind": spec["operation_kind"], "source_bundle": bundle,
                "source_bundle_hash": bundle_hash, "repository_roots": durable_roots,
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

            prevention_receipt = None
            if prevention_receipt_path is not None:
                prevention_receipt = _write_prevention_receipt(
                    prevention_receipt_path,
                    identity=prevention_identity,
                    status="APPLIED",
                    source_identity=prevention_source_identity,
                )

            result = {
                "ok": True, "bootstrap_request_sha256": request_digest,
                "discovery_path": str(document_path), "discovery_id": manifest["lineage_id"],
                "manifest_path": str(manifest_path), "task_id": task_id,
                "classification_receipt_hash": class_hash,
                "selection_receipt_hash": selection_hash,
                "source_bundle_hash": bundle_hash, "run_id": run_id,
                "event_id": event_id, "recovered": recovered,
            }
            if prevention_receipt is not None:
                result["preventionReceiptPath"] = str(prevention_receipt_path)
                result["preventionReceiptSha256"] = work_memory.sha256_bytes(
                    work_memory.canonical_bytes(prevention_receipt)
                )
            return result
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
    start.add_argument("--prevention-effect-id")
    start.add_argument("--prevention-preparation-sha256")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if not values:
        try:
            from scripts import sequence_intake_launch
        except ModuleNotFoundError:
            import sequence_intake_launch  # type: ignore
        return sequence_intake_launch.main_for_sequence(
            "discovery-bootstrap", [],
        )
    try:
        args = build_parser().parse_args(values)
        spec = normalize_spec(_load_json(args.spec))
        root = Path(args.root or ".").expanduser().resolve()
        result = bootstrap(
            spec, root=root, repo_roots_file=args.repo_roots_file,
            prevention_effect_id=args.prevention_effect_id,
            prevention_preparation_sha256=args.prevention_preparation_sha256,
        )
        if args.prevention_effect_id:
            result = {
                **result,
                "preventionEffectId": args.prevention_effect_id,
                "preventionPreparationSha256": args.prevention_preparation_sha256,
            }
        print(json.dumps(result, sort_keys=True))
        return 0
    except work_memory.WorkMemoryError as exc:
        print(json.dumps({"ok": False, "error": exc.code}, sort_keys=True), file=sys.stderr)
        return exc.exit_code
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__}, sort_keys=True), file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
