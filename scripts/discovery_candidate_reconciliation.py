#!/usr/bin/env python3
"""Audit discovery candidates and execute an explicitly approved disposition manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

try:
    from scripts import discovery_promotion_lifecycle, sequence_discovery_log, work_memory
except ImportError:
    import discovery_promotion_lifecycle  # type: ignore
    import sequence_discovery_log  # type: ignore
    import work_memory  # type: ignore


class ReconciliationError(RuntimeError):
    pass


SCHEMA_VERSION = 3
DISPOSITIONS = {
    "promote", "absorb", "remain-discovery", "supersede", "quarantine",
    "already-promoted",
}
TERMINAL_DISPOSITIONS = {"promote", "absorb", "supersede", "already-promoted"}
PROMOTION_FIELDS = {
    "sequence_id", "use_when", "operation_kinds", "automation_display",
    "pass_signal", "max_qualification_runs",
}
ROLLING_POLICY = "rolling-retain-only"
SEQUENCE_ID = "discovery-candidate-reconciliation"
ROLLING_BASELINE = "operations/sequences/discovery/reconciliation-policy.json"
ACTIVE_INDEX = "operations/sequences/discovery/ACTIVE.md"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(_canonical(payload) + b"\n")
    temporary.replace(path)


def _git_head(root: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        text=True, capture_output=True, check=False,
    )
    if completed.returncode:
        raise ReconciliationError("git-head-unavailable")
    return completed.stdout.strip()


def _candidate_paths(root: Path) -> list[str]:
    folder = root / "operations/sequences/discovery"
    return sorted(
        str(path.relative_to(root))
        for path in folder.glob("*.md")
        if path.is_file() and path.name not in {"ACTIVE.md", "README.md"}
    )


def _candidate_hashes(root: Path, paths: list[str]) -> dict[str, str]:
    return {
        relative: hashlib.sha256((root / relative).read_bytes()).hexdigest()
        for relative in paths
    }


def _metadata(text: str, name: str) -> str | None:
    return sequence_discovery_log._metadata(text, name) or None


def _title(text: str, path: Path) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem


def _registered_bundle_hash(root: Path, sequence_id: str) -> str:
    document = root / "operations/sequences" / sequence_id / "sequence.md"
    manifest = document.with_name("dependencies.json")
    if not document.is_file() or not manifest.is_file():
        raise ReconciliationError(f"registered-target-missing:{sequence_id}")
    _, bundle_hash, _ = work_memory.resolve_bundle(
        mode="registered", subject_id=sequence_id, document=document, manifest=manifest,
        repo_roots_file=None, include_bootstrap_trust_anchors=True,
    )
    return bundle_hash


def _candidate_row(root: Path, relative: str, registry: list[dict[str, str]]) -> dict[str, Any]:
    path = root / relative
    text = path.read_text(encoding="utf-8")
    discovery_id = _metadata(text, "DiscoveryId")
    promoted = _metadata(text, "PromotedSequenceId")
    registered_match = _metadata(text, "RegisteredSequenceMatch")
    try:
        state = sequence_discovery_log.discovery_state(path, require_bound=False)
        inspection_error = None
    except (OSError, work_memory.WorkMemoryError, ValueError) as exc:
        state = {
            "status": "invalid", "successful_runs": 0, "unmet_predicates": [],
            "open_blocker_ids": [], "source_bundle_hash": None, "lineage_id": None,
        }
        inspection_error = getattr(exc, "code", type(exc).__name__)
    lineage = state.get("lineage_id") or discovery_id
    registry_matches = sorted(
        row["sequence_id"] for row in registry
        if row.get("lineage_id") == lineage or row.get("sequence_id") in {promoted, registered_match}
    )
    registered_target_verified: bool | None = None
    registered_target_bundle_hash: str | None = None
    if inspection_error:
        suggested = "quarantine"
    elif promoted and promoted in registry_matches:
        try:
            registered_target_bundle_hash = _registered_bundle_hash(root, promoted)
            registered_target_verified = discovery_promotion_lifecycle._registered_verified(
                promoted, repo_roots_file=None,
            )
        except (OSError, work_memory.WorkMemoryError, ValueError) as exc:
            registered_target_verified = False
            inspection_error = f"registered-target-verification:{getattr(exc, 'code', type(exc).__name__)}"
        if registered_target_verified:
            suggested = "already-promoted"
        else:
            inspection_error = inspection_error or "registered-target-not-verified"
            suggested = "quarantine"
    elif state["status"] in {"ready", "overdue"}:
        suggested = "promotion-review"
    else:
        suggested = "remain-discovery"
    return {
        "path": relative,
        "title": _title(text, path),
        "discovery_id": discovery_id,
        "lineage_id": lineage,
        "lifecycle_status": state["status"],
        "successful_runs": state["successful_runs"],
        "unmet_predicates": state["unmet_predicates"],
        "open_blocker_ids": state["open_blocker_ids"],
        "source_bundle_hash": state["source_bundle_hash"],
        "promoted_sequence_id": promoted,
        "registered_sequence_match": registered_match,
        "registry_matches": registry_matches,
        "registered_target_verified": registered_target_verified,
        "registered_target_bundle_hash": registered_target_bundle_hash,
        "inspection_error": inspection_error,
        "suggested_disposition": suggested,
        "disposition": "pending",
        "decision_reason": None,
        "target_sequence_id": None,
        "promotion": None,
    }


def audit(root: Path) -> dict[str, Any]:
    paths = _candidate_paths(root)
    registry, registry_hash = work_memory.registry_rows(
        root / "operations/sequences/SEQUENCES.md"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "repository_root": str(root),
        "snapshot": {
            "head": _git_head(root),
            "candidate_paths": paths,
            "candidate_set_hash": _sha(paths),
            "candidate_hashes": _candidate_hashes(root, paths),
            "registry_hash": registry_hash,
        },
        "generated_at_utc": _utc_now(),
        "approval": {"approved": False, "approved_by": None, "approved_at_utc": None},
        "candidates": [_candidate_row(root, path, registry) for path in paths],
    }


def cmd_audit(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    output = Path(args.output).resolve()
    payload = audit(root)
    _atomic_json(output, payload)
    counts: dict[str, int] = {}
    for row in payload["candidates"]:
        key = row["suggested_disposition"]
        counts[key] = counts.get(key, 0) + 1
    return {
        "ok": True, "manifest": str(output), "head": payload["snapshot"]["head"],
        "candidate_count": len(payload["candidates"]), "suggested_counts": counts,
    }


def _decision_reason(row: dict[str, Any]) -> str:
    suggested = row["suggested_disposition"]
    error = row.get("inspection_error") or ""
    if suggested == "already-promoted":
        return "Approved terminal allowlist target has current same-path verification and a frozen source-bundle hash."
    if error == "discovery-id-missing":
        return "Legacy log lacks a governed DiscoveryId; preserve it in quarantine."
    if error == "missing-repository-root":
        return "Required repository root is missing; preserve it in quarantine."
    if error == "registered-target-not-verified":
        return "Registered target lacks current same-path verification; preserve it in quarantine."
    if error.startswith("registered-target-verification:"):
        return "Registered target verification cannot resolve; preserve it in quarantine."
    if suggested == "remain-discovery":
        return "Approved rolling policy retains this candidate in the active discovery queue."
    return "Preserve in quarantine pending evidence repair."


def _load_rolling_baseline(path: Path) -> dict[str, Any]:
    try:
        baseline = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReconciliationError("invalid-rolling-baseline") from exc
    approval = baseline.get("approval")
    if not isinstance(approval, dict) or approval.get("approved") is not True:
        raise ReconciliationError("rolling-baseline-not-approved")
    if approval.get("policy") != ROLLING_POLICY:
        raise ReconciliationError("invalid-rolling-policy")
    allowlist = approval.get("terminal_allowlist")
    if not isinstance(allowlist, list) or not allowlist or len(set(allowlist)) != len(allowlist):
        raise ReconciliationError("invalid-terminal-allowlist")
    if not isinstance(baseline.get("candidates"), list):
        raise ReconciliationError("invalid-rolling-baseline")
    return baseline


def _apply_rolling_policy(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    approval = baseline["approval"]
    baseline_rows = {row.get("path"): row for row in baseline["candidates"]}
    current_rows = {row.get("path"): row for row in current["candidates"]}
    missing = sorted(set(baseline_rows) - set(current_rows))
    if missing:
        raise ReconciliationError(f"rolling-baseline-candidate-missing:{missing[0]}")
    for path, row in current_rows.items():
        prior = baseline_rows.get(path)
        suggested = row["suggested_disposition"]
        if prior is None:
            if suggested != "remain-discovery":
                raise ReconciliationError(f"rolling-new-candidate-not-retain:{path}:{suggested}")
            disposition = "remain-discovery"
        else:
            disposition = prior.get("disposition")
            if disposition != suggested:
                raise ReconciliationError(
                    f"rolling-existing-disposition-changed:{path}:{disposition}->{suggested}"
                )
        if disposition not in {"remain-discovery", "quarantine", "already-promoted"}:
            raise ReconciliationError(f"rolling-disposition-not-supported:{path}:{disposition}")
        row["disposition"] = disposition
        row["decision_reason"] = _decision_reason(row)
        row["target_sequence_id"] = (
            row["promoted_sequence_id"] if disposition == "already-promoted" else None
        )
    allowlist = sorted(approval["terminal_allowlist"])
    actual = sorted(
        row["promoted_sequence_id"] for row in current["candidates"]
        if row["disposition"] == "already-promoted"
    )
    if actual != allowlist:
        raise ReconciliationError("rolling-terminal-allowlist-mismatch")
    current["approval"] = dict(approval)
    return current


def _registered_target(root: Path, sequence_id: str) -> Path:
    if not sequence_id or Path(sequence_id).name != sequence_id:
        raise ReconciliationError("invalid-target-sequence-id")
    document = root / "operations/sequences" / sequence_id / "sequence.md"
    if not document.is_file() or not document.with_name("dependencies.json").is_file():
        raise ReconciliationError(f"registered-target-missing:{sequence_id}")
    return document


def _validate_promotion(row: dict[str, Any]) -> None:
    promotion = row.get("promotion")
    if not isinstance(promotion, dict) or set(promotion) != PROMOTION_FIELDS:
        raise ReconciliationError(f"invalid-promotion-fields:{row['path']}")
    if any(not promotion[key] for key in PROMOTION_FIELDS - {"max_qualification_runs"}):
        raise ReconciliationError(f"incomplete-promotion-metadata:{row['path']}")
    kinds = promotion["operation_kinds"]
    if not isinstance(kinds, list) or not kinds or any(kind not in work_memory.OPERATION_KINDS for kind in kinds):
        raise ReconciliationError(f"invalid-promotion-operation-kinds:{row['path']}")
    if not isinstance(promotion["max_qualification_runs"], int) or promotion["max_qualification_runs"] < 1:
        raise ReconciliationError(f"invalid-qualification-limit:{row['path']}")


def validate_manifest(path: Path, root: Path, *, require_approval: bool = True) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReconciliationError("invalid-manifest-json") from exc
    if payload.get("schema_version") != SCHEMA_VERSION or not isinstance(payload.get("candidates"), list):
        raise ReconciliationError("invalid-manifest-schema")
    snapshot = payload.get("snapshot")
    if not isinstance(snapshot, dict):
        raise ReconciliationError("missing-manifest-snapshot")
    current_paths = _candidate_paths(root)
    if snapshot.get("head") != _git_head(root):
        raise ReconciliationError("repository-head-drift")
    if snapshot.get("candidate_paths") != current_paths or snapshot.get("candidate_set_hash") != _sha(current_paths):
        raise ReconciliationError("candidate-set-drift")
    if snapshot.get("candidate_hashes") != _candidate_hashes(root, current_paths):
        raise ReconciliationError("candidate-content-drift")
    _, registry_hash = work_memory.registry_rows(root / "operations/sequences/SEQUENCES.md")
    if snapshot.get("registry_hash") != registry_hash:
        raise ReconciliationError("registry-drift")
    rows = payload["candidates"]
    if [row.get("path") for row in rows] != current_paths:
        raise ReconciliationError("manifest-candidate-order-mismatch")
    approval = payload.get("approval", {})
    if require_approval and (
        approval.get("approved") is not True
        or not approval.get("approved_by") or not approval.get("approved_at_utc")
    ):
        raise ReconciliationError("manifest-not-approved")
    for row in rows:
        disposition = row.get("disposition")
        if disposition not in DISPOSITIONS:
            raise ReconciliationError(f"invalid-or-pending-disposition:{row.get('path')}")
        if not isinstance(row.get("decision_reason"), str) or not row["decision_reason"].strip():
            raise ReconciliationError(f"decision-reason-required:{row['path']}")
        if disposition == "promote":
            _validate_promotion(row)
        elif disposition in {"absorb", "supersede", "already-promoted"}:
            target = row.get("target_sequence_id")
            _registered_target(root, target)
            frozen_bundle = row.get("registered_target_bundle_hash")
            if not isinstance(frozen_bundle, str) or not frozen_bundle:
                raise ReconciliationError(f"registered-target-bundle-required:{row['path']}")
            if _registered_bundle_hash(root, target) != frozen_bundle:
                raise ReconciliationError(f"registered-target-bundle-drift:{target}")
        if disposition == "already-promoted" and row.get("promoted_sequence_id") != row.get("target_sequence_id"):
            raise ReconciliationError(f"promoted-target-mismatch:{row['path']}")
    return payload


def cmd_validate(args: argparse.Namespace) -> dict[str, Any]:
    payload = validate_manifest(Path(args.manifest).resolve(), Path(args.root).resolve())
    return {"ok": True, "candidate_count": len(payload["candidates"]), "manifest_hash": _sha(payload)}


def _run_lifecycle(row: dict[str, Any], root: Path) -> dict[str, Any]:
    promotion = row["promotion"]
    command = [
        "python3", "scripts/discovery_promotion_lifecycle.py", "drive",
        "--file", row["path"], "--sequence-id", promotion["sequence_id"],
        "--use-when", promotion["use_when"],
        "--automation-display", promotion["automation_display"],
        "--pass-signal", promotion["pass_signal"],
        "--max-qualification-runs", str(promotion["max_qualification_runs"]),
    ]
    for kind in promotion["operation_kinds"]:
        command.extend(["--operation-kind", kind])
    completed = subprocess.run(command, cwd=root, text=True, capture_output=True, check=False)
    stream = completed.stdout if completed.returncode == 0 else completed.stderr
    lines = [line for line in stream.splitlines() if line.strip()]
    try:
        result = json.loads(lines[-1]) if lines else {}
    except json.JSONDecodeError as exc:
        raise ReconciliationError(f"lifecycle-non-json:{row['path']}") from exc
    if completed.returncode or result.get("ok") is False or result.get("stage") != "complete":
        raise ReconciliationError(f"lifecycle-failed:{row['path']}:{result.get('error', completed.returncode)}")
    return result


def _checkpoint_path(manifest: Path) -> Path:
    return manifest.with_suffix(manifest.suffix + ".checkpoint.json")


def _load_checkpoint(manifest: Path, manifest_hash: str) -> dict[str, Any]:
    path = _checkpoint_path(manifest)
    if not path.is_file():
        return {"schema_version": 1, "manifest_hash": manifest_hash, "completed": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or payload.get("manifest_hash") != manifest_hash:
        raise ReconciliationError("checkpoint-manifest-mismatch")
    if not isinstance(payload.get("completed"), dict):
        raise ReconciliationError("invalid-checkpoint")
    return payload


def _render_active_index(payload: dict[str, Any], checkpoint: dict[str, Any]) -> str:
    lines = [
        "# Active Discovery Candidates", "",
        f"Manifest-SHA256: `{checkpoint['manifest_hash']}`", "",
        "Terminal decisions are omitted; original discovery logs remain preserved.", "",
        "| candidate | disposition | reason |", "| --- | --- | --- |",
    ]
    for row in payload["candidates"]:
        disposition = row["disposition"]
        if disposition in TERMINAL_DISPOSITIONS and row["path"] in checkpoint["completed"]:
            continue
        lines.append(f"| `{row['path']}` | `{disposition}` | {row['decision_reason']} |")
    return "\n".join(lines).rstrip() + "\n"


def _safe_index(root: Path, raw: str) -> Path:
    path = Path(raw)
    target = (path if path.is_absolute() else root / path).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ReconciliationError("active-index-outside-repository") from exc
    return target


def cmd_execute(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    manifest = Path(args.manifest).resolve()
    payload = validate_manifest(manifest, root)
    manifest_hash = _sha(payload)
    checkpoint = _load_checkpoint(manifest, manifest_hash)
    for row in payload["candidates"]:
        key = row["path"]
        if key in checkpoint["completed"]:
            continue
        disposition = row["disposition"]
        if disposition == "promote":
            result = _run_lifecycle(row, root)
        elif disposition in {"absorb", "supersede", "already-promoted"}:
            target = row["target_sequence_id"]
            _registered_target(root, target)
            if not discovery_promotion_lifecycle._registered_verified(target, repo_roots_file=None):
                raise ReconciliationError(f"registered-target-not-verified:{target}")
            result = {"target_sequence_id": target, "registered_verified": True}
        else:
            result = {"retained_active": True}
        checkpoint["completed"][key] = {
            "disposition": disposition, "completed_at_utc": _utc_now(), "result": result,
        }
        _atomic_json(_checkpoint_path(manifest), checkpoint)
    index = _safe_index(root, args.active_index)
    index.parent.mkdir(parents=True, exist_ok=True)
    temporary = index.with_name(index.name + ".tmp")
    temporary.write_text(_render_active_index(payload, checkpoint), encoding="utf-8")
    temporary.replace(index)
    return {
        "ok": True, "manifest_hash": manifest_hash,
        "completed_count": len(checkpoint["completed"]),
        "active_index": str(index), "checkpoint": str(_checkpoint_path(manifest)),
    }


def _stable_snapshot(left: dict[str, Any], right: dict[str, Any]) -> bool:
    keys = {"head", "candidate_paths", "candidate_set_hash", "candidate_hashes", "registry_hash"}
    if not all(left["snapshot"].get(key) == right["snapshot"].get(key) for key in keys):
        return False
    def terminal_bundles(payload: dict[str, Any]) -> list[tuple[str, str | None]]:
        return [
            (row["target_sequence_id"], row.get("registered_target_bundle_hash"))
            for row in payload["candidates"] if row["disposition"] == "already-promoted"
        ]
    return terminal_bundles(left) == terminal_bundles(right)


def cmd_execute_rolling(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    baseline_path = Path(args.baseline).resolve()
    baseline = _load_rolling_baseline(baseline_path)
    output_root = Path(args.output_dir).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    invocation_dir = output_root / f"run-{uuid4().hex}"
    invocation_dir.mkdir()
    if args.max_attempts < 1:
        raise ReconciliationError("invalid-rolling-attempt-limit")
    for attempt in range(1, args.max_attempts + 1):
        current = _apply_rolling_policy(audit(root), baseline)
        manifest = invocation_dir / f"attempt-{attempt}.json"
        _atomic_json(manifest, current)
        try:
            execution = cmd_execute(argparse.Namespace(
                root=str(root), manifest=str(manifest), active_index=args.active_index,
            ))
        except ReconciliationError as exc:
            if str(exc) == "candidate-set-drift":
                continue
            raise
        post = _apply_rolling_policy(audit(root), baseline)
        if not _stable_snapshot(current, post):
            continue
        return {
            "ok": True,
            "policy": ROLLING_POLICY,
            "attempt": attempt,
            "candidate_count": len(current["candidates"]),
            "terminal_count": sum(
                row["disposition"] in TERMINAL_DISPOSITIONS for row in current["candidates"]
            ),
            "manifest": str(manifest),
            "manifest_hash": execution["manifest_hash"],
            "invocation_dir": str(invocation_dir),
            "active_index": execution["active_index"],
            "checkpoint": execution["checkpoint"],
        }
    raise ReconciliationError("rolling-attempts-exhausted")


def _lifecycle_call(function: Any, /, *args: Any, **kwargs: Any) -> Any:
    try:
        return function(*args, **kwargs)
    except discovery_promotion_lifecycle.LifecycleError as exc:
        raise ReconciliationError(exc.code) from exc


def _verify_current_bundle(
    *, task_id: str, root: Path, document: Path,
) -> dict[str, Any]:
    pending = _lifecycle_call(
        discovery_promotion_lifecycle._pending_correction, SEQUENCE_ID,
    )
    open_blockers = _lifecycle_call(
        discovery_promotion_lifecycle._open_blocker_ids, SEQUENCE_ID,
    )
    if open_blockers:
        raise ReconciliationError(f"correction-required:{','.join(open_blockers)}")
    if pending is None and discovery_promotion_lifecycle._registered_verified(
        SEQUENCE_ID, repo_roots_file=None,
    ):
        return {"already_verified": True}
    _lifecycle_call(
        discovery_promotion_lifecycle._classify,
        task_id, root=root, operation_kind="other",
    )
    run_id, receipt = _lifecycle_call(
        discovery_promotion_lifecycle._select_and_start,
        task_id=task_id, discovery=None, sequence_id=SEQUENCE_ID, root=root,
        repo_roots_file=None, pending=pending,
    )
    result = _lifecycle_call(
        discovery_promotion_lifecycle._verify_run,
        run_id=run_id, receipt=receipt, document=document, task_id=task_id,
        root=root,
        command=_lifecycle_call(discovery_promotion_lifecycle._verification_command, document),
        source="sequence_doc", subject_id=SEQUENCE_ID,
    )
    if not discovery_promotion_lifecycle._registered_verified(
        SEQUENCE_ID, repo_roots_file=None,
    ):
        raise ReconciliationError("current-bundle-verification-not-recorded")
    return {"already_verified": False, **result}


def _catalog_drive_failure(
    *, run_id: str, root: Path, step_id: str, error_code: str,
) -> dict[str, Any]:
    return _lifecycle_call(
        discovery_promotion_lifecycle._json_command,
        [
            "python3", "scripts/blocker_catalog.py", "open",
            "--run-id", run_id, "--subject-id", SEQUENCE_ID,
            "--step-id", step_id,
            "--surface", "scripts/discovery_candidate_reconciliation.py",
            "--error-signature", error_code,
            "--symptom", f"The one-shot reconciliation drive failed at {step_id}.",
            "--evidence", f"The guarded controller returned {error_code}.",
            "--impact", "The rolling reconciliation run stopped before governed closure.",
            "--boundary", "The registered one-shot reconciliation command and its runtime dependencies.",
        ],
        root=root,
    )


def _run_live_rolling(
    *, task_id: str, output_root: Path, root: Path, document: Path,
) -> dict[str, Any]:
    _lifecycle_call(
        discovery_promotion_lifecycle._classify,
        task_id, root=root, operation_kind="other",
    )
    run_id, _ = _lifecycle_call(
        discovery_promotion_lifecycle._select_and_start,
        task_id=task_id, discovery=None, sequence_id=SEQUENCE_ID, root=root,
        repo_roots_file=None, pending=None,
    )
    command = [
        "python3", "scripts/discovery_candidate_reconciliation.py", "execute-rolling",
        "--baseline", ROLLING_BASELINE,
        "--output-dir", str(output_root),
        "--active-index", ACTIVE_INDEX,
        "--max-attempts", "6",
    ]
    try:
        _lifecycle_call(
            discovery_promotion_lifecycle._json_command,
            [
                "python3", "scripts/sequence_guard.py", "guard",
                "--step", "execute-rolling", "--command", shlex.join(command),
                "--source", "sequence_doc", "--source-ref", str(document),
                "--task-id", task_id, "--root", str(root),
            ],
            root=root,
        )
        rolling = _lifecycle_call(
            discovery_promotion_lifecycle._json_command, command, root=root,
        )
    except ReconciliationError as exc:
        blocker = _catalog_drive_failure(
            run_id=run_id, root=root, step_id="execute-rolling", error_code=str(exc),
        )
        raise ReconciliationError(
            f"rolling-execution-failed-blocker-cataloged:{blocker['blocker_id']}"
        ) from exc
    evidence = (
        "The guard-authorized execute-rolling command completed successfully with "
        f"manifest {rolling['manifest_hash']}, {rolling['candidate_count']} candidates, "
        f"and {rolling['terminal_count']} terminal dispositions."
    )
    try:
        verification = _lifecycle_call(
            discovery_promotion_lifecycle._json_command,
            [
                "python3", "scripts/work_memory.py", "verify", "--run-id", run_id,
                "--outcome", "passed", "--quality", "same-path", "--evidence", evidence,
            ],
            root=root,
        )
        _lifecycle_call(
            discovery_promotion_lifecycle._json_command,
            [
                "python3", "scripts/work_memory.py", "run-close", "--run-id", run_id,
                "--result", "passed",
            ],
            root=root,
        )
    except ReconciliationError as exc:
        blocker = _catalog_drive_failure(
            run_id=run_id, root=root, step_id="record-and-close", error_code=str(exc),
        )
        raise ReconciliationError(
            f"run-closure-failed-blocker-cataloged:{blocker['blocker_id']}"
        ) from exc
    return {
        "run_id": run_id,
        "verification_event_id": verification["event_id"],
        "active_count": rolling["candidate_count"] - rolling["terminal_count"],
        **rolling,
    }


def cmd_drive(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    document = root / f"operations/sequences/{SEQUENCE_ID}/sequence.md"
    if not document.is_file():
        raise ReconciliationError("registered-sequence-document-missing")
    output_root = Path(args.output_root)
    output_root = (output_root if output_root.is_absolute() else root / output_root).resolve()
    verification = _verify_current_bundle(
        task_id=f"{args.task_id}-verify", root=root, document=document,
    )
    live = _run_live_rolling(
        task_id=f"{args.task_id}-live", output_root=output_root,
        root=root, document=document,
    )
    return {
        "ok": True,
        "stage": "complete",
        "sequence_id": SEQUENCE_ID,
        "bundle_verification": verification,
        "live_run": live,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(work_memory.ROOT))
    sub = parser.add_subparsers(dest="command", required=True)
    audit_p = sub.add_parser("audit")
    audit_p.add_argument("--output", required=True)
    audit_p.set_defaults(func=cmd_audit)
    validate_p = sub.add_parser("validate")
    validate_p.add_argument("--manifest", required=True)
    validate_p.set_defaults(func=cmd_validate)
    execute_p = sub.add_parser("execute")
    execute_p.add_argument("--manifest", required=True)
    execute_p.add_argument("--active-index", required=True)
    execute_p.set_defaults(func=cmd_execute)
    rolling_p = sub.add_parser("execute-rolling")
    rolling_p.add_argument("--baseline", required=True)
    rolling_p.add_argument("--output-dir", required=True)
    rolling_p.add_argument("--active-index", required=True)
    rolling_p.add_argument("--max-attempts", type=int, default=6)
    rolling_p.set_defaults(func=cmd_execute_rolling)
    drive_p = sub.add_parser("drive")
    drive_p.add_argument("--task-id", required=True)
    drive_p.add_argument("--output-root", required=True)
    drive_p.set_defaults(func=cmd_drive)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        print(json.dumps(args.func(args), sort_keys=True))
        return 0
    except (ReconciliationError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
