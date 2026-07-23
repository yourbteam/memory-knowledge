#!/usr/bin/env python3
"""Drive discovery qualification, promotion, and registered verification."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

try:
    from scripts import prevention_source_receipt, sequence_discovery_log, work_memory
except ImportError:
    import prevention_source_receipt  # type: ignore
    import sequence_discovery_log  # type: ignore
    import work_memory  # type: ignore


class LifecycleError(RuntimeError):
    def __init__(self, code: str, *, details: dict[str, Any] | None = None):
        super().__init__(code)
        self.code = code
        self.details = details or {}


@dataclass(frozen=True)
class PendingCorrection:
    blocker_id: str
    correction_id: str
    predecessor_run_id: str
    task_id: str
    co_corrections: tuple[tuple[str, str], ...] = ()

    @property
    def pairs(self) -> tuple[tuple[str, str], ...]:
        return ((self.blocker_id, self.correction_id), *self.co_corrections)

    @property
    def blocker_ids(self) -> tuple[str, ...]:
        return tuple(blocker_id for blocker_id, _ in self.pairs)

    @property
    def correction_ids(self) -> tuple[str, ...]:
        return tuple(correction_id for _, correction_id in self.pairs)


PROTECTED_CORRECTION_PATHS = {
    "scripts/discovery_promotion_lifecycle.py",
    "scripts/work_memory.py",
    "scripts/work_memory_bootstrap.py",
}
IMMUTABLE_LAUNCHER_PATH = "scripts/work_memory_bootstrap_launcher.py"


def _metadata(path: Path, name: str) -> str:
    value = sequence_discovery_log._metadata(path.read_text(encoding="utf-8"), name)
    if not value:
        raise LifecycleError(f"missing-metadata:{name}")
    return value


def _verification_command(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and cells[0] == "verify-automation":
            command = cells[1]
            if not command or re.search(r"<[^>]+>", command):
                raise LifecycleError("verification-command-has-placeholders")
            return command
    raise LifecycleError("missing-verify-automation-command")


def _json_command(command: list[str], *, root: Path) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=root, text=True, capture_output=True, check=False)
    stream = completed.stdout if completed.returncode == 0 else completed.stderr
    lines = [line for line in stream.splitlines() if line.strip()]
    try:
        payload = json.loads(lines[-1]) if lines else {}
    except json.JSONDecodeError as exc:
        raise LifecycleError(
            "non-json-control-command",
            details={
                "command": command,
                "exit_code": completed.returncode,
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-4000:],
            },
        ) from exc
    if completed.returncode != 0 or payload.get("ok") is False:
        raise LifecycleError(
            str(payload.get("error", "control-command-failed")),
            details={"command": command, "exit_code": completed.returncode, "payload": payload},
        )
    return payload


def _classify(task_id: str, *, root: Path, operation_kind: str) -> None:
    _json_command([
        "python3", "scripts/work_memory.py", "classify", "--task-id", task_id,
        "--operation-kind", operation_kind, "--repeatable", "yes",
        "--meaningful-steps", "8",
    ], root=root)


def _pending_correction(discovery_id: str) -> PendingCorrection | None:
    events, _ = work_memory.load_ledger()
    blockers: dict[str, dict[str, Any]] = {}
    corrections: dict[str, dict[str, Any]] = {}
    verified_correction_ids = {
        correction_id
        for event in events
        if (
            event.get("event_type") == "verification_recorded"
            and event.get("outcome") == "passed"
        )
        for correction_id in event.get("correction_ids", [])
    }
    run_task_ids = {
        event["run_id"]: event["task_id"]
        for event in events
        if event.get("event_type") == "run_started" and event.get("task_id")
    }
    for event in events:
        kind = event.get("event_type")
        if kind == "blocker_opened":
            if event.get("subject_id") != discovery_id and event.get("lineage_id") != discovery_id:
                continue
            blockers[event["blocker_id"]] = {
                "status": "open", "run_id": event["run_id"],
            }
        elif kind == "blocker_recurred" and event["blocker_id"] in blockers:
            blockers[event["blocker_id"]].update(status="open", run_id=event["run_id"])
        elif kind == "correction_recorded" and event["blocker_id"] in blockers:
            corrections[event["blocker_id"]] = event
        elif kind == "blocker_transitioned" and event["blocker_id"] in blockers:
            blockers[event["blocker_id"]]["status"] = event["to_status"]
    candidates = []
    for blocker_id, state in blockers.items():
        correction = corrections.get(blocker_id)
        if (
            state["status"] == "fixed-awaiting-verification"
            and correction
            and correction["correction_id"] not in verified_correction_ids
        ):
            task_id = run_task_ids.get(correction["run_id"])
            if task_id is None:
                raise LifecycleError("pending-correction-task-id-missing")
            candidates.append(PendingCorrection(
                blocker_id=blocker_id,
                correction_id=correction["correction_id"],
                predecessor_run_id=correction["run_id"],
                task_id=task_id,
            ))
    if not candidates:
        return None
    primary = candidates[0]
    if any(
        candidate.predecessor_run_id != primary.predecessor_run_id
        or candidate.task_id != primary.task_id
        for candidate in candidates[1:]
    ):
        raise LifecycleError("multiple-pending-correction-groups")
    return PendingCorrection(
        blocker_id=primary.blocker_id,
        correction_id=primary.correction_id,
        predecessor_run_id=primary.predecessor_run_id,
        task_id=primary.task_id,
        co_corrections=tuple(
            (candidate.blocker_id, candidate.correction_id)
            for candidate in candidates[1:]
        ),
    )


def _open_blocker_ids(subject_id: str) -> list[str]:
    events, _ = work_memory.load_ledger()
    states: dict[str, str] = {}
    for event in events:
        blocker_id = event.get("blocker_id")
        if event.get("event_type") == "blocker_opened":
            if event.get("subject_id") != subject_id and event.get("lineage_id") != subject_id:
                continue
            states[blocker_id] = "open"
        elif event.get("event_type") == "blocker_recurred" and blocker_id in states:
            states[blocker_id] = "open"
        elif event.get("event_type") == "blocker_transitioned" and blocker_id in states:
            states[blocker_id] = event["to_status"]
    return sorted(blocker_id for blocker_id, status in states.items() if status == "open")


def _registered_verified(sequence_id: str, *, repo_roots_file: str | None) -> bool:
    document = work_memory.ROOT / f"operations/sequences/{sequence_id}/sequence.md"
    manifest = document.with_name("dependencies.json")
    if not document.is_file() or not manifest.is_file():
        return False
    _, bundle_hash, _ = work_memory.resolve_bundle(
        mode="registered", subject_id=sequence_id, document=document, manifest=manifest,
        repo_roots_file=repo_roots_file,
        include_bootstrap_trust_anchors=True,
    )
    events, _ = work_memory.load_ledger()
    runs: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.get("subject_id") != sequence_id:
            continue
        if event.get("event_type") == "run_started" and event.get("source_bundle_hash") == bundle_hash:
            runs[event["run_id"]] = {"verified": False, "closed": False}
        elif event.get("run_id") in runs and event.get("event_type") == "verification_recorded":
            runs[event["run_id"]]["verified"] = (
                event.get("outcome") == "passed" and event.get("quality") == "same-path"
            )
        elif event.get("run_id") in runs and event.get("event_type") == "run_closed":
            runs[event["run_id"]]["closed"] = event.get("result") == "passed"
    return any(item["verified"] and item["closed"] for item in runs.values())


def _select_and_start(
    *, task_id: str, discovery: Path | None, sequence_id: str | None,
    root: Path, repo_roots_file: str | None, pending: PendingCorrection | None = None,
) -> tuple[str, dict[str, Any]]:
    select = ["python3", "scripts/work_memory.py", "select", "--task-id", task_id]
    if discovery is not None:
        select.extend(["--discovery-log", str(discovery)])
    else:
        select.extend(["--sequence-id", str(sequence_id)])
    if pending:
        select.extend([
            "--verification-successor-of", pending.predecessor_run_id,
        ])
        for correction_id in pending.correction_ids:
            select.extend(["--verifies-correction-id", correction_id])
    if repo_roots_file:
        select.extend(["--repo-roots-file", repo_roots_file])
    receipt = _json_command(select, root=root)
    activate = ["python3", "scripts/sequence_guard.py", "activate", "--task-id", task_id,
                "--root", str(root)]
    if discovery is not None:
        activate.extend(["--discovery-log", str(discovery)])
    else:
        activate.extend(["--sequence-doc", receipt["document"]])
    _json_command(activate, root=root)
    started = _json_command([
        "python3", "scripts/work_memory.py", "run-start", "--task-id", task_id,
    ], root=root)
    return started["run_id"], receipt


def _guard_and_verify(
    *, task_id: str, root: Path, document: Path, source: str, command: str,
) -> subprocess.CompletedProcess[str]:
    _json_command([
        "python3", "scripts/sequence_guard.py", "guard", "--step", "verify-automation",
        "--command", command, "--source", source, "--source-ref", str(document),
        "--task-id", task_id, "--root", str(root),
    ], root=root)
    return subprocess.run(shlex.split(command), cwd=root, text=True, capture_output=True, check=False)


def _catalog_verification_failure(
    *, run_id: str, discovery_id: str, exit_code: int, root: Path,
) -> dict[str, Any]:
    return _json_command([
        "python3", "scripts/blocker_catalog.py", "open", "--run-id", run_id,
        "--subject-id", discovery_id, "--step-id", "verify-automation",
        "--surface", "discovery-promotion-lifecycle",
        "--error-signature", f"verification-command-exit-{exit_code}",
        "--symptom", "The documented same-path verification command failed.",
        "--evidence", f"The guarded verification command exited {exit_code}; output remains in the operator terminal.",
        "--impact", "Qualification, promotion, and registered verification are stopped.",
        "--boundary", "The discovery document's verify-automation command and its runtime dependencies.",
    ], root=root)


def _verify_run(
    *, run_id: str, receipt: dict[str, Any], document: Path, task_id: str,
    root: Path, command: str, source: str, subject_id: str,
) -> dict[str, Any]:
    completed = _guard_and_verify(
        task_id=task_id, root=root, document=document, source=source, command=command,
    )
    if completed.returncode != 0:
        blocker = _catalog_verification_failure(
            run_id=run_id, discovery_id=subject_id,
            exit_code=completed.returncode, root=root,
        )
        raise LifecycleError(
            "verification-failed-blocker-cataloged",
            details={"run_id": run_id, "task_id": task_id, **blocker},
        )
    pending_ids = receipt.get("verifies_correction_ids", [])
    relevant = receipt.get("relevant_blocker_ids", [])
    verify = [
        "python3", "scripts/work_memory.py", "verify", "--run-id", run_id,
        "--outcome", "passed", "--quality", "same-path",
        "--evidence", "The controller executed the exact guard-authorized verify-automation command successfully.",
    ]
    pending_blockers: tuple[str, ...] = ()
    if pending_ids:
        pending = _pending_correction(subject_id)
        if (
            pending is None
            or set(pending.correction_ids) != set(pending_ids)
            or not set(pending.blocker_ids).issubset(relevant)
        ):
            raise LifecycleError("successor-receipt-correction-mismatch")
        pending_blockers = pending.blocker_ids
        for blocker_id, correction_id in pending.pairs:
            verify.extend([
                "--blocker-id", blocker_id,
                "--correction-id", correction_id,
            ])
    verification = _json_command(verify, root=root)
    for blocker_id in pending_blockers:
        for status in ("verified", "closed"):
            _json_command([
                "python3", "scripts/blocker_catalog.py", "transition", "--run-id", run_id,
                "--blocker-id", blocker_id, "--to-status", status,
                "--verification-event-id", verification["event_id"],
                *(
                    ["--remaining-work", "none"]
                    if status == "closed" else []
                ),
            ], root=root)
    _json_command([
        "python3", "scripts/work_memory.py", "run-close", "--run-id", run_id,
        "--result", "passed",
    ], root=root)
    return {"run_id": run_id, "verification_event_id": verification["event_id"]}


def _qualify_once(args: argparse.Namespace, state: dict[str, Any]) -> dict[str, Any]:
    root = Path(args.root).resolve()
    discovery = Path(args.file).resolve()
    pending = _pending_correction(state["discovery_id"])
    task_id = (
        pending.task_id
        if pending is not None
        else f"discovery-promote-{args.sequence_id}-{args.operation_kind[0]}"
    )
    _classify(task_id, root=root, operation_kind=args.operation_kind[0])
    run_id, receipt = _select_and_start(
        task_id=task_id, discovery=discovery, sequence_id=None, root=root,
        repo_roots_file=args.repo_roots_file, pending=pending,
    )
    return _verify_run(
        run_id=run_id, receipt=receipt, document=discovery, task_id=task_id,
        root=root, command=_verification_command(discovery), source="discovery_log",
        subject_id=state["discovery_id"],
    )


def _promote(args: argparse.Namespace, *, root: Path) -> dict[str, Any]:
    _json_command([
        "python3", "scripts/sequence_discovery_log.py", "check", "--file", args.file,
        *(["--repo-roots-file", args.repo_roots_file] if args.repo_roots_file else []),
    ], root=root)
    _json_command([
        "python3", "scripts/sequence_discovery_log.py", "closeout", "--file", args.file,
        *(["--repo-roots-file", args.repo_roots_file] if args.repo_roots_file else []),
    ], root=root)
    command = [
        "python3", "scripts/sequence_promote.py", "promote", "--file", args.file,
        "--sequence-id", args.sequence_id, "--use-when", args.use_when,
        "--automation-display", args.automation_display, "--pass-signal", args.pass_signal,
    ]
    for kind in args.operation_kind:
        command.extend(["--operation-kind", kind])
    if args.repo_roots_file:
        command.extend(["--repo-roots-file", args.repo_roots_file])
    return _json_command(command, root=root)


def _verify_registered(args: argparse.Namespace, *, root: Path) -> dict[str, Any]:
    if _registered_verified(args.sequence_id, repo_roots_file=args.repo_roots_file):
        return {"already_verified": True}
    pending = _pending_correction(args.sequence_id)
    task_id = (
        pending.task_id
        if pending is not None
        else f"registered-verify-{args.sequence_id}-{args.operation_kind[0]}"
    )
    _classify(task_id, root=root, operation_kind=args.operation_kind[0])
    document = root / f"operations/sequences/{args.sequence_id}/sequence.md"
    run_id, receipt = _select_and_start(
        task_id=task_id, discovery=None, sequence_id=args.sequence_id, root=root,
        repo_roots_file=args.repo_roots_file, pending=pending,
    )
    return _verify_run(
        run_id=run_id, receipt=receipt, document=document, task_id=task_id,
        root=root, command=_verification_command(document), source="sequence_doc",
        subject_id=args.sequence_id,
    )


def cmd_status(args: argparse.Namespace) -> dict[str, Any]:
    discovery = Path(args.file).resolve()
    state = sequence_discovery_log.discovery_state(
        discovery, require_bound=False, repo_roots_file=args.repo_roots_file,
    )
    registered_pending = (
        _pending_correction(args.sequence_id) if state["status"] == "promoted" else None
    )
    registered_open = (
        _open_blocker_ids(args.sequence_id) if state["status"] == "promoted" else []
    )
    registered_verified = (
        _registered_verified(args.sequence_id, repo_roots_file=args.repo_roots_file)
        if state["status"] == "promoted" else False
    )
    if registered_open:
        stage = "correction-required"
    elif registered_pending:
        stage = "registered-successor-verification"
    elif registered_verified:
        stage = "complete"
    elif state["status"] == "promoted":
        stage = "registered-verification"
    elif state["status"] in {"ready", "overdue"}:
        stage = "promotion"
    elif _pending_correction(state["discovery_id"]):
        stage = "successor-verification"
    elif state["open_blocker_ids"]:
        stage = "correction-required"
    else:
        stage = "qualification"
    if registered_open:
        state = {**state, "open_blocker_ids": registered_open}
    return {"ok": True, "stage": stage, "state": state,
            "registered_verified": registered_verified}


def _declare_bootstrap_readiness(
    args: argparse.Namespace, state: dict[str, Any], *, root: Path,
) -> bool:
    """Declare derived readiness before qualification changes the proven bundle."""
    unmet = set(state.get("unmet_predicates", []))
    if "readiness" not in unmet or unmet - {"readiness", "two-same-path-successes"}:
        return False
    discovery = Path(args.file).resolve()
    bootstrap_digest = sequence_discovery_log._metadata(
        discovery.read_text(encoding="utf-8"), "BootstrapRequestSha256",
    )
    if not bootstrap_digest:
        return False
    for item in sorted(sequence_discovery_log.READINESS):
        _json_command([
            "python3", "scripts/sequence_discovery_log.py", "set-readiness",
            "--file", str(discovery), "--item", item, "--checked", "yes",
        ], root=root)
    return True


def cmd_drive(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    runs = []
    for _ in range(args.max_qualification_runs + 6):
        status = cmd_status(args)
        stage = status["stage"]
        if stage == "complete":
            return {"ok": True, "stage": "complete", "qualification_runs": runs}
        if stage == "correction-required":
            raise LifecycleError(
                "correction-required",
                details={"open_blocker_ids": status["state"]["open_blocker_ids"]},
            )
        if stage == "qualification" and _declare_bootstrap_readiness(
            args, status["state"], root=root,
        ):
            continue
        if stage in {"qualification", "successor-verification"}:
            if len(runs) >= args.max_qualification_runs:
                raise LifecycleError(
                    "qualification-run-limit-exceeded", details={"runs": runs},
                )
            runs.append(_qualify_once(args, status["state"]))
            continue
        if stage == "promotion":
            _promote(args, root=root)
            continue
        if stage == "registered-verification":
            _verify_registered(args, root=root)
            continue
        if stage == "registered-successor-verification":
            _verify_registered(args, root=root)
            continue
        raise LifecycleError(f"unknown-stage:{stage}")
    raise LifecycleError("lifecycle-transition-limit-exceeded", details={"runs": runs})


def _correct_subject(args: argparse.Namespace, subject_id: str) -> dict[str, Any]:
    root = Path(args.root).resolve()
    events, _ = work_memory.load_ledger()
    blockers: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.get("event_type") == "blocker_opened":
            if event.get("subject_id") != subject_id and event.get("lineage_id") != subject_id:
                continue
            blockers[event["blocker_id"]] = dict(event, status="open")
        elif event.get("event_type") == "blocker_recurred" and event["blocker_id"] in blockers:
            blockers[event["blocker_id"]].update(
                status="open", run_id=event["run_id"], occurrence_id=event["occurrence_id"],
            )
        elif event.get("event_type") == "blocker_transitioned" and event["blocker_id"] in blockers:
            blockers[event["blocker_id"]]["status"] = event["to_status"]
    open_items = [item for item in blockers.values() if item["status"] == "open"]
    pending = _pending_correction(subject_id)
    co_blockers: list[dict[str, Any]] = []
    if open_items:
        blocker = open_items[0]
        co_blockers = open_items[1:]
    elif not open_items and pending is not None:
        blocker = blockers[pending.blocker_id]
    else:
        raise LifecycleError("expected-one-open-blocker", details={"count": len(open_items)})
    if any(item["run_id"] != blocker["run_id"] for item in co_blockers):
        raise LifecycleError(
            "open-blockers-span-multiple-runs",
            details={"blocker_ids": [item["blocker_id"] for item in open_items]},
        )
    artifacts: list[str] = list(args.changed_artifact or [])
    if args.changed_artifacts_file:
        try:
            materialized = json.loads(
                Path(args.changed_artifacts_file).read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise LifecycleError("invalid-changed-artifacts-file") from exc
        if not isinstance(materialized, list) or not materialized:
            raise LifecycleError("invalid-changed-artifacts-file")
        roots = work_memory._repo_roots(args.repo_roots_file)
        for index, item in enumerate(materialized):
            if (
                not isinstance(item, dict)
                or set(item) != {"repository_key", "path"}
                or not isinstance(item["repository_key"], str)
                or not isinstance(item["path"], str)
                or item["repository_key"] not in roots
                or Path(item["path"]).is_absolute()
                or ".." in Path(item["path"]).parts
            ):
                raise LifecycleError(
                    "invalid-changed-artifact-identity",
                    details={"index": index},
                )
            repository_root = roots[item["repository_key"]]
            resolved = (repository_root / item["path"]).resolve()
            try:
                resolved.relative_to(repository_root)
            except ValueError as exc:
                raise LifecycleError(
                    "changed-artifact-root-escape", details={"index": index}
                ) from exc
            if not resolved.is_file():
                raise LifecycleError(
                    "changed-artifact-not-found", details={"index": index}
                )
            artifacts.append(str(resolved))
    artifacts = list(dict.fromkeys(artifacts))
    if not artifacts:
        raise LifecycleError("changed-artifacts-required")
    protected = False
    for artifact in artifacts:
        raw_path = Path(artifact)
        resolved = (raw_path if raw_path.is_absolute() else root / raw_path).resolve()
        try:
            relative = str(resolved.relative_to(root))
        except ValueError:
            continue
        if relative == IMMUTABLE_LAUNCHER_PATH:
            raise LifecycleError("immutable-bootstrap-launcher-change")
        protected = protected or relative in PROTECTED_CORRECTION_PATHS
    if protected and not args.task_id:
        raise LifecycleError("task-id-required-for-protected-correction")
    command = [
        "python3",
        "scripts/work_memory_bootstrap_launcher.py" if protected else "scripts/work_memory.py",
        "correct",
    ]
    if protected:
        command.extend(["--task-id", args.task_id])
    command.extend([
        "--run-id", blocker["run_id"],
        "--blocker-id", blocker["blocker_id"], "--occurrence-id", blocker["occurrence_id"],
        "--step-id", blocker["step_id"], "--solution", args.solution,
        "--reusable-behavior-changed", args.reusable_behavior_changed,
        "--correction-id", str(uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"memory-knowledge:{blocker['run_id']}:{blocker['blocker_id']}:{blocker['occurrence_id']}",
        )),
    ])
    for co_blocker in co_blockers:
        command.extend(["--co-blocker-id", co_blocker["blocker_id"]])
    if not protected:
        command.append("--finalize-failed-run")
    for artifact in artifacts:
        command.extend(["--changed-artifact", artifact])
    for correction_id in args.supersedes_correction_id or []:
        command.extend(["--supersedes-correction-id", correction_id])
    if args.repo_roots_file and not protected:
        command.extend(["--repo-roots-file", args.repo_roots_file])
    correction = _json_command(command, root=root)
    return {"ok": True, "correction_id": correction["correction_id"],
            "blocker_id": blocker["blocker_id"], "next_stage": "successor-verification"}


def cmd_correct(args: argparse.Namespace) -> dict[str, Any]:
    discovery = Path(args.file).resolve()
    return _correct_subject(args, _metadata(discovery, "DiscoveryId"))


def cmd_correct_registered(args: argparse.Namespace) -> dict[str, Any]:
    return _correct_subject(args, args.subject_id)


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--file", required=True)
    parser.add_argument("--sequence-id", required=True)
    parser.add_argument("--repo-roots-file")
    parser.add_argument("--root", default=str(work_memory.ROOT))
    parser.add_argument("--prevention-effect-id")
    parser.add_argument("--prevention-preparation-sha256")


def _correction_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--task-id")
    parser.add_argument("--solution", required=True)
    parser.add_argument("--changed-artifact", action="append")
    parser.add_argument("--changed-artifacts-file")
    parser.add_argument("--supersedes-correction-id", action="append")
    parser.add_argument("--reusable-behavior-changed", choices=("yes", "no"), required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status")
    _common(status)
    status.set_defaults(func=cmd_status)
    drive = sub.add_parser("drive")
    _common(drive)
    drive.add_argument("--use-when", required=True)
    drive.add_argument("--operation-kind", action="append", required=True)
    drive.add_argument("--automation-display", required=True)
    drive.add_argument("--pass-signal", required=True)
    drive.add_argument("--max-qualification-runs", type=int, default=3)
    drive.set_defaults(func=cmd_drive)
    correct = sub.add_parser("correct")
    _common(correct)
    _correction_arguments(correct)
    correct.set_defaults(func=cmd_correct)
    registered = sub.add_parser("correct-registered")
    registered.add_argument("--subject-id", required=True)
    registered.add_argument("--root", default=str(work_memory.ROOT))
    registered.add_argument("--repo-roots-file")
    registered.add_argument("--prevention-effect-id")
    registered.add_argument("--prevention-preparation-sha256")
    _correction_arguments(registered)
    registered.set_defaults(func=cmd_correct_registered)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if not values:
        try:
            from scripts import sequence_intake_launch
        except ModuleNotFoundError:
            import sequence_intake_launch  # type: ignore
        return sequence_intake_launch.main_for_sequence(
            "discovery-promotion-lifecycle", [],
        )
    try:
        args = build_parser().parse_args(values)
        source_identity = {
            "profile": args.command,
            "root_path_sha256": hashlib.sha256(
                str(Path(args.root).resolve()).encode("utf-8")
            ).hexdigest(),
            "input_identities": {
                name: (
                    hashlib.sha256(Path(value).read_bytes()).hexdigest()
                    if isinstance(value, str) and Path(value).is_file()
                    else hashlib.sha256(str(value).encode("utf-8")).hexdigest()
                )
                for name, value in sorted(vars(args).items())
                if name not in {
                    "func", "prevention_effect_id",
                    "prevention_preparation_sha256", "solution",
                } and value is not None
            },
            "solution_sha256": (
                hashlib.sha256(args.solution.encode("utf-8")).hexdigest()
                if getattr(args, "solution", None) else None
            ),
        }
        source_receipt = None
        if args.command != "status" and (
            args.prevention_effect_id or args.prevention_preparation_sha256
        ):
            source_receipt = prevention_source_receipt.prepare(
                owner_sequence_id="discovery-promotion-lifecycle",
                profile_id=args.command,
                effect_id=args.prevention_effect_id,
                preparation_artifact_sha256=args.prevention_preparation_sha256,
                source_identity=source_identity,
            )
        result = args.func(args)
        if source_receipt is not None:
            result_identity = {
                "ok": result.get("ok"),
                "result_sha256": hashlib.sha256(
                    json.dumps(
                        result, sort_keys=True, separators=(",", ":")
                    ).encode("utf-8")
                ).hexdigest(),
            }
            if args.command == "drive":
                result_identity["stage"] = result.get("stage")
            else:
                result_identity["next_stage"] = result.get("next_stage")
            source_receipt = prevention_source_receipt.complete(
                owner_sequence_id="discovery-promotion-lifecycle",
                profile_id=args.command,
                effect_id=args.prevention_effect_id,
                preparation_artifact_sha256=args.prevention_preparation_sha256,
                source_identity=source_identity,
                result_identity=result_identity,
            )
        if args.prevention_effect_id:
            result = {
                **result,
                "preventionEffectId": args.prevention_effect_id,
                "preventionPreparationSha256": args.prevention_preparation_sha256,
            }
            if source_receipt is not None:
                result["preventionSourceReceiptSha256"] = (
                    prevention_source_receipt.receipt_sha256(source_receipt)
                )
        print(json.dumps(result, sort_keys=True))
        return 0
    except (LifecycleError, work_memory.WorkMemoryError) as exc:
        code = exc.code if hasattr(exc, "code") else str(exc)
        details = exc.details if isinstance(exc, LifecycleError) else {}
        print(json.dumps({"ok": False, "error": code, **details}, sort_keys=True), file=sys.stderr)
        return 3
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__}, sort_keys=True), file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
