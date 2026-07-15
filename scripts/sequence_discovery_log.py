#!/usr/bin/env python3
"""Create, harden, and evaluate repeatable-sequence discovery logs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Sequence

try:
    from scripts import work_memory
except ImportError:
    import work_memory  # type: ignore


DISCOVERY_DIR = Path("operations/sequences/discovery")
READINESS = {
    "commands": "Commands are stable enough to script or document.",
    "inputs": "Required inputs are known.",
    "failure-handling": "Failure handling is known.",
    "verification": "Verification evidence is known.",
    "promotion": "Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.",
}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "unnamed-sequence"


def _root(value: str | None) -> Path:
    return Path(value or ".").resolve()


def _atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = Path(raw)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data); handle.flush(); os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _write_json(path: Path, value: dict[str, Any]) -> None:
    _atomic(path, work_memory.canonical_bytes(value))


def _discovery_id(root: Path, path: Path) -> str:
    relative = str(path.resolve().relative_to(root.resolve()))
    return "discovery-" + str(uuid.uuid5(uuid.NAMESPACE_URL, f"memory-knowledge:{relative}"))


def _metadata(text: str, name: str) -> str | None:
    match = re.search(rf"^{re.escape(name)}:\s*(.*?)\s*$", text, re.M)
    return match.group(1) if match else None


def _replace_metadata(text: str, name: str, value: str | None) -> str:
    pattern = re.compile(rf"^{re.escape(name)}:.*(?:\n|$)", re.M)
    if value is None:
        return pattern.sub("", text)
    line = f"{name}: {value}\n"
    if pattern.search(text):
        return pattern.sub(line, text, count=1)
    title_end = text.find("\n") + 1
    return text[:title_end] + line + text[title_end:]


def _replace_section(text: str, heading: str, body: str) -> str:
    pattern = re.compile(rf"(^## {re.escape(heading)}\s*$\n)(.*?)(?=^## |\Z)", re.M | re.S)
    if not pattern.search(text):
        raise work_memory.WorkMemoryError(f"missing-discovery-section:{heading}", 3)
    return pattern.sub(lambda match: match.group(1) + "\n" + body.strip() + "\n\n", text, count=1)


def _section(text: str, heading: str) -> str:
    match = re.search(rf"^## {re.escape(heading)}\s*$\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not match:
        raise work_memory.WorkMemoryError(f"missing-discovery-section:{heading}", 3)
    return match.group(1).strip()


def _bundle(
    path: Path, *, repo_roots_file: str | None = None,
) -> tuple[list[dict[str, str]], str, str]:
    text = path.read_text()
    discovery_id = _metadata(text, "DiscoveryId")
    if not discovery_id:
        raise work_memory.WorkMemoryError("discovery-id-missing", 3)
    return work_memory.resolve_bundle(
        mode="discovery", subject_id=discovery_id, document=path,
        manifest=path.with_suffix(".dependencies.json"),
        repo_roots_file=repo_roots_file,
    )


def cmd_start(args: argparse.Namespace) -> dict[str, Any]:
    root = _root(args.root)
    date_text = args.date or datetime.now(UTC).strftime("%Y-%m-%d")
    path = root / DISCOVERY_DIR / f"{date_text}-{_slug(args.sequence_name)}.md"
    if path.exists() and not args.force:
        raise work_memory.WorkMemoryError("discovery-log-exists", 3)
    discovery_id = _discovery_id(root, path)
    text = f"""# Sequence Discovery Log: {args.sequence_name}

DiscoveryId: {discovery_id}
Status: discovery
CreatedAtUtc: {work_memory.utc_now()}
RegisteredSequenceMatch: none

## Intended Outcome

{args.outcome.strip()}

## Why This Looks Repeatable

{args.why_repeatable.strip()}

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |

## Failure Handling

TBD while discovering.

## Verified Path

- Not verified yet.

## Promotion Readiness

""" + "".join(f"- [ ] {label}\n" for label in READINESS.values())
    manifest = {"schema_version": 1, "lineage_id": discovery_id, "dependencies": []}
    _atomic(path, text.encode())
    _write_json(path.with_suffix(".dependencies.json"), manifest)
    return {"ok": True, "path": str(path), "manifest_path": str(path.with_suffix('.dependencies.json')),
            "discovery_id": discovery_id}


def cmd_append_step(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.file).resolve()
    if not path.is_file():
        raise work_memory.WorkMemoryError("discovery-log-not-found", 3)
    text = path.read_text()
    marker = "| step | command or action | result | correction or note |\n| --- | --- | --- | --- |\n"
    if marker not in text:
        raise work_memory.WorkMemoryError("commands-table-missing", 3)
    values = [args.step, args.command, args.result, args.note]
    if any("|" in value or "\n" in value for value in values):
        raise work_memory.WorkMemoryError("invalid-command-row", 2)
    row = "| " + " | ".join(value.strip() for value in values) + " |\n"
    _atomic(path, text.replace(marker, marker + row, 1).encode())
    return {"ok": True, "path": str(path), "row_hash": hashlib.sha256(row.encode()).hexdigest()}


def cmd_set_inputs(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.file).resolve(); text = path.read_text()
    if any(not item.strip() or "TBD" in item.upper() for item in args.input):
        raise work_memory.WorkMemoryError("invalid-discovery-input", 2)
    body = "\n".join(f"- {item.strip()}" for item in args.input)
    _atomic(path, _replace_section(text, "Required Inputs, Auth, Or Environment", body).encode())
    return {"ok": True, "path": str(path), "inputs_hash": hashlib.sha256(body.encode()).hexdigest()}


def cmd_set_section(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.file).resolve(); text = path.read_text()
    value = (args.text if hasattr(args, "text") else args.evidence).strip()
    if not value or "TBD" in value.upper() or value.lower() in {"not verified", "not verified yet"}:
        raise work_memory.WorkMemoryError("invalid-discovery-section-value", 2)
    heading = "Failure Handling" if hasattr(args, "text") else "Verified Path"
    body = value if heading == "Failure Handling" else f"- {value}"
    _atomic(path, _replace_section(text, heading, body).encode())
    return {"ok": True, "path": str(path), "section_hash": hashlib.sha256(body.encode()).hexdigest()}


def cmd_set_readiness(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.file).resolve(); text = path.read_text()
    label = READINESS[args.item]
    pattern = re.compile(rf"^- \[[ xX]\] {re.escape(label)}$", re.M)
    if not pattern.search(text):
        raise work_memory.WorkMemoryError("readiness-item-missing", 3)
    checked = args.checked == "yes"
    updated = pattern.sub(f"- [{'x' if checked else ' '}] {label}", text, count=1)
    _atomic(path, updated.encode())
    return {"ok": True, "path": str(path), "item": args.item, "checked": checked}


def cmd_set_dependencies(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.file).resolve(); text = path.read_text()
    discovery_id = _metadata(text, "DiscoveryId")
    try:
        source = json.loads(Path(args.dependencies_json).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise work_memory.WorkMemoryError("invalid-dependencies-json", 2) from exc
    if set(source) == {"dependencies"}:
        source = {"schema_version": 1, "lineage_id": discovery_id, **source}
    if source.get("schema_version") != 1 or source.get("lineage_id") != discovery_id or not isinstance(source.get("dependencies"), list):
        raise work_memory.WorkMemoryError("invalid-dependency-manifest", 2)
    target = path.with_suffix(".dependencies.json")
    _write_json(target, source)
    _, digest, _ = _bundle(path, repo_roots_file=args.repo_roots_file)
    return {"ok": True, "path": str(path), "manifest_path": str(target), "source_bundle_hash": digest}


def discovery_state(
    path: Path,
    now: datetime | None = None,
    *,
    require_bound: bool = True,
    repo_roots_file: str | None = None,
) -> dict[str, Any]:
    text = path.read_text(); discovery_id = _metadata(text, "DiscoveryId")
    if not discovery_id:
        raise work_memory.WorkMemoryError("discovery-id-missing", 3)
    _, bundle_hash, lineage = _bundle(path, repo_roots_file=repo_roots_file)
    events, ledger_hash = work_memory.load_ledger()
    starts = {event["run_id"]: event for event in events if event["event_type"] == "run_started" and event["mode"] == "discovery" and event["subject_id"] == discovery_id}
    if require_bound and not starts:
        raise work_memory.WorkMemoryError("discovery-not-bound-to-run", 3)
    verifications = {event["run_id"] for event in events if event["event_type"] == "verification_recorded" and event["subject_id"] == discovery_id and event["source_bundle_hash"] == bundle_hash and event["outcome"] == "passed" and event["quality"] == "same-path"}
    closes = [event for event in events if event["event_type"] == "run_closed" and event["subject_id"] == discovery_id and event["result"] == "passed" and event["run_id"] in starts and starts[event["run_id"]]["source_bundle_hash"] == bundle_hash and event["run_id"] in verifications]
    closes.sort(key=lambda event: (event["completed_at_utc"], event["run_id"]))
    open_blockers: set[str] = set()
    for event in events:
        if event["event_type"] == "blocker_opened" and event["lineage_id"] == lineage:
            open_blockers.add(event["blocker_id"])
        elif event["event_type"] == "blocker_recurred":
            open_blockers.add(event["blocker_id"])
        elif event["event_type"] == "blocker_transitioned" and event["blocker_id"] in open_blockers and event["to_status"] in {"closed", "superseded", "non-gap"}:
            open_blockers.discard(event["blocker_id"])
    inputs = _section(text, "Required Inputs, Auth, Or Environment")
    commands = _section(text, "Commands And Observations")
    failure = _section(text, "Failure Handling")
    verified = _section(text, "Verified Path")
    readiness = _section(text, "Promotion Readiness")
    unmet = []
    if len(closes) < 2: unmet.append("two-same-path-successes")
    if "TBD" in inputs.upper(): unmet.append("inputs")
    if len([line for line in commands.splitlines() if line.startswith("|")]) <= 2: unmet.append("commands")
    if not failure or "TBD" in failure.upper(): unmet.append("failure-handling")
    if not verified or "not verified" in verified.lower(): unmet.append("verified-path")
    if readiness.count("- [x]") + readiness.count("- [X]") != len(READINESS): unmet.append("readiness")
    if open_blockers: unmet.append("open-blockers")
    ready_at = closes[1]["completed_at_utc"] if len(closes) >= 2 else None
    current = now or datetime.now(UTC)
    status = "ready" if not unmet else "discovery"
    if status == "ready" and (len(closes) >= 3 or current >= work_memory.parse_utc(ready_at) + timedelta(hours=168)):
        status = "overdue"
    if _metadata(text, "PromotedSequenceId"):
        status = "promoted"
    return {"ok": True, "path": str(path), "discovery_id": discovery_id, "lineage_id": lineage,
            "status": status, "ready_at_utc": ready_at, "successful_runs": len(closes),
            "latest_validation_at_utc": closes[-1]["completed_at_utc"] if closes else None,
            "source_bundle_hash": bundle_hash, "ledger_hash": ledger_hash,
            "open_blocker_ids": sorted(open_blockers), "unmet_predicates": unmet}


def cmd_check(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.file).resolve()
    state = discovery_state(path, repo_roots_file=args.repo_roots_file)
    text = path.read_text()
    for legacy in ("SuccessfulRuns", "LastValidatedAtUtc"):
        text = _replace_metadata(text, legacy, None)
    text = _replace_metadata(text, "Status", state["status"])
    text = _replace_metadata(text, "ReadyAtUtc", state["ready_at_utc"])
    before = work_memory.semantic_discovery_bytes(path)
    _atomic(path, text.encode())
    after = work_memory.semantic_discovery_bytes(path)
    if before != after:
        raise work_memory.WorkMemoryError("helper-rewrite-changed-semantic-bundle", 3)
    return state


def cmd_backlog(args: argparse.Namespace) -> dict[str, Any]:
    root = _root(args.root); records = []
    for path in sorted((root / DISCOVERY_DIR).glob("*.md")):
        try:
            records.append(discovery_state(
                path,
                require_bound=False,
                repo_roots_file=args.repo_roots_file,
            ))
        except work_memory.WorkMemoryError as exc:
            records.append({"path": str(path), "status": "invalid", "error": exc.code,
                            "successful_runs": 0, "ready_at_utc": None, "discovery_id": path.stem})
    rank = {"overdue": 0, "ready": 1}
    records.sort(key=lambda item: (rank.get(item["status"], 2), -item.get("successful_runs", 0),
                                   item.get("ready_at_utc") or "", item.get("discovery_id", "")))
    return {"ok": True, "records": records,
            "overdue_count": sum(item["status"] == "overdue" for item in records)}


def cmd_closeout(args: argparse.Namespace) -> dict[str, Any]:
    state = discovery_state(
        Path(args.file).resolve(), repo_roots_file=args.repo_roots_file,
    )
    if state["status"] == "overdue":
        raise work_memory.WorkMemoryError("discovery-promotion-overdue", 3)
    return state


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start"); start.add_argument("--sequence-name", required=True); start.add_argument("--outcome", required=True)
    start.add_argument("--why-repeatable", required=True); start.add_argument("--root"); start.add_argument("--date"); start.add_argument("--force", action="store_true"); start.set_defaults(func=cmd_start)
    append = sub.add_parser("append-step"); append.add_argument("--file", required=True); append.add_argument("--step", required=True)
    append.add_argument("--command", required=True); append.add_argument("--result", required=True); append.add_argument("--note", default=""); append.set_defaults(func=cmd_append_step)
    inputs = sub.add_parser("set-inputs"); inputs.add_argument("--file", required=True); inputs.add_argument("--input", action="append", required=True); inputs.set_defaults(func=cmd_set_inputs)
    failure = sub.add_parser("set-failure-handling"); failure.add_argument("--file", required=True); failure.add_argument("--text", required=True); failure.set_defaults(func=cmd_set_section)
    verified = sub.add_parser("set-verified-path"); verified.add_argument("--file", required=True); verified.add_argument("--evidence", required=True); verified.set_defaults(func=cmd_set_section)
    readiness = sub.add_parser("set-readiness"); readiness.add_argument("--file", required=True); readiness.add_argument("--item", choices=sorted(READINESS), required=True); readiness.add_argument("--checked", choices=["yes", "no"], required=True); readiness.set_defaults(func=cmd_set_readiness)
    dependencies = sub.add_parser("set-dependencies"); dependencies.add_argument("--file", required=True); dependencies.add_argument("--dependencies-json", required=True); dependencies.add_argument("--repo-roots-file"); dependencies.set_defaults(func=cmd_set_dependencies)
    check = sub.add_parser("check"); check.add_argument("--file", required=True); check.add_argument("--repo-roots-file"); check.set_defaults(func=cmd_check)
    backlog = sub.add_parser("backlog"); backlog.add_argument("--root"); backlog.add_argument("--repo-roots-file"); backlog.set_defaults(func=cmd_backlog)
    closeout = sub.add_parser("closeout"); closeout.add_argument("--file", required=True); closeout.add_argument("--repo-roots-file"); closeout.set_defaults(func=cmd_closeout)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv); print(json.dumps(args.func(args), sort_keys=True)); return 0
    except work_memory.WorkMemoryError as exc:
        print(json.dumps({"ok": False, "error": exc.code}, sort_keys=True), file=sys.stderr); return exc.exit_code
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__}, sort_keys=True), file=sys.stderr); return 5


if __name__ == "__main__":
    raise SystemExit(main())
