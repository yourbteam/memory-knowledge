#!/usr/bin/env python3
"""Preserve UP events omitted from main without admitting legacy lifecycle states.

The archive is read-only historical evidence. Creation requires the complete
legacy ledger. Verification checks byte integrity and conflicts against the
current active ledger; it does not treat archived statuses as active.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "operations/work-memory/legacy-up-20261018"
ARCHIVE = DIRECTORY / ("events" + ".jsonl.gz")
MANIFEST = DIRECTORY / "manifest.json"
ACTIVE = ROOT / "operations/work-memory" / ("events" + ".jsonl")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_lines(raw: bytes) -> list[tuple[bytes, dict]]:
    rows = []
    seen = set()
    for line in raw.splitlines(keepends=True):
        if not line.strip():
            continue
        if not line.endswith(b"\n"):
            raise ValueError("ledger has a nonterminated event")
        event = json.loads(line)
        if not isinstance(event, dict) or not isinstance(event.get("event_id"), str) or not event["event_id"]:
            raise ValueError("ledger event must have a nonempty string event_id")
        identity = event["event_id"]
        if identity in seen:
            raise ValueError(f"duplicate event id: {identity}")
        seen.add(identity)
        rows.append((line, event))
    return rows


def select_legacy_up(source: bytes, active: bytes) -> list[tuple[bytes, dict]]:
    old = read_lines(source)
    main = {event["event_id"]: line for line, event in read_lines(active)}
    for line, event in old:
        prior = main.get(event["event_id"])
        if prior is not None and json.loads(prior) != event:
            raise ValueError(f"event id conflicts with main: {event['event_id']}")
    missing = [(line, event) for line, event in old if event["event_id"] not in main]
    up_runs = {event["run_id"] for _line, event in old
               if event["event_type"] == "run_started"
               and ("united-partners" in (event.get("repository_roots") or {})
                    or b"united-partners" in _line)}
    up_tasks = {event["task_id"] for line, event in missing
                if b"united-partners" in line and event.get("task_id")}
    return [(line, event) for line, event in missing
            if event.get("run_id") in up_runs
            or event.get("task_id") in up_tasks
            or b"united-partners" in line]


def create(source_path: Path) -> None:
    source, active = source_path.read_bytes(), ACTIVE.read_bytes()
    selected = select_legacy_up(source, active)
    raw = b"".join(line for line, _event in selected)
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    # mtime=0 makes the compressed artifact reproducible from the same source.
    with ARCHIVE.open("wb") as stream:
        with gzip.GzipFile(fileobj=stream, mode="wb", filename="", mtime=0) as zipped:
            zipped.write(raw)
    manifest = {
        "schema": "legacy-up-events/v1", "status": "read-only-historical",
        "source_event_count": len(read_lines(source)),
        "source_ledger_sha256": sha(source), "active_ledger_at_capture_sha256": sha(active),
        "active_ledger_event_count_at_capture": len(read_lines(active)),
        "archive_sha256": sha(raw), "event_count": len(selected),
        "first_recorded_at_utc": min(event["recorded_at_utc"] for _line, event in selected),
        "last_recorded_at_utc": max(event["recorded_at_utc"] for _line, event in selected),
        "selection": "old-only IDs for UP repository runs, UP task IDs, or explicit UP references",
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    verify(source_path)


def verify(source_path: Path | None = None) -> None:
    manifest = json.loads(MANIFEST.read_text())
    if manifest.get("schema") != "legacy-up-events/v1" or manifest.get("status") != "read-only-historical":
        raise ValueError("archive manifest identity changed")
    raw = gzip.decompress(ARCHIVE.read_bytes())
    rows = read_lines(raw)
    if sha(raw) != manifest["archive_sha256"] or len(rows) != manifest["event_count"]:
        raise ValueError("archived event bytes changed")
    active = {event["event_id"]: event for _line, event in read_lines(ACTIVE.read_bytes())}
    for _line, event in rows:
        current = active.get(event["event_id"])
        if current is not None and current != event:
            raise ValueError(f"archived event conflicts with main: {event['event_id']}")
    if source_path is not None:
        source = source_path.read_bytes()
        if sha(source) != manifest["source_ledger_sha256"]:
            raise ValueError("source ledger changed since capture")
        expected = [line for line, _event in select_legacy_up(source, ACTIVE.read_bytes())]
        if b"".join(expected) != raw:
            raise ValueError("UP selection differs from captured source")
    print(f"verified {len(rows)} historical UP events; active ledger unchanged")


def historical_status(
    *, active_path: Path, run_id: str | None = None, blocker_id: str | None = None,
    archive_path: Path = ARCHIVE, manifest_path: Path = MANIFEST,
) -> dict:
    """Read recorded standing through a read-only structural event contract."""
    if (run_id is None) == (blocker_id is None):
        raise ValueError("exactly one run_id or blocker_id is required")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema") != "legacy-up-events/v1" or manifest.get("status") != "read-only-historical":
        raise ValueError("archive manifest identity changed")
    archive_raw = gzip.decompress(archive_path.read_bytes())
    archived = read_lines(archive_raw)
    if sha(archive_raw) != manifest.get("archive_sha256") or len(archived) != manifest.get("event_count"):
        raise ValueError("archived event bytes changed")
    active_raw = active_path.read_bytes()
    active_rows = read_lines(active_raw)
    active_by_id = {event["event_id"]: (line, event) for line, event in active_rows}
    for line, event in archived:
        current = active_by_id.get(event["event_id"])
        if current is not None and current[0] != line:
            raise ValueError(f"archived event conflicts with active ledger: {event['event_id']}")

    population = [
        {"_source": "active-ledger", "_source_index": index, "event": event}
        for index, (_line, event) in enumerate(active_rows)
    ]
    population_ids = {item["event"]["event_id"] for item in population}
    population.extend(
        {"_source": "legacy-up-archive", "_source_index": index, "event": event}
        for index, (_line, event) in enumerate(archived)
        if event["event_id"] not in population_ids
    )
    selected = []
    for item in population:
        event = item["event"]
        matches = (
            event.get("run_id") == run_id
            if run_id is not None else (
                event.get("blocker_id") == blocker_id
                or blocker_id in event.get("blocker_ids", [])
            )
        )
        if matches:
            selected.append(item)
    if not selected:
        raise ValueError("historical-record-not-found")

    timestamps: dict[str, set[str]] = {}
    for item in selected:
        event = item["event"]
        timestamp = event.get("recorded_at_utc")
        if not isinstance(timestamp, str) or not timestamp:
            raise ValueError(f"historical event has no timestamp: {event.get('event_id')}")
        sources = timestamps.setdefault(timestamp, set())
        sources.add(item["_source"])
        if len(sources) > 1:
            raise ValueError(f"historical-event-order-ambiguous:{timestamp}")
    lineage = sorted(selected, key=lambda item: (item["event"]["recorded_at_utc"], item["_source_index"]))
    if sha(active_path.read_bytes()) != sha(active_raw):
        raise ValueError("active ledger changed during historical query")

    if run_id is not None:
        starts = [item for item in lineage if item["event"].get("event_type") == "run_started"]
        terminals = [item for item in lineage if item["event"].get("event_type") in {"run_closed", "run_abandoned"}]
        if len(starts) != 1 or len(terminals) > 1:
            raise ValueError("historical-run-lifecycle-ambiguous")
        latest = terminals[-1] if terminals else starts[0]
        status = latest["event"].get("result") if latest["event"].get("event_type") == "run_closed" else latest["event"].get("event_type")
        if not terminals:
            status = "open"
    else:
        status_events = [item for item in lineage if item["event"].get("event_type") in {
            "blocker_opened", "blocker_recurred", "blocker_transitioned",
            "pre_run_blocker_opened", "pre_run_blocker_transitioned",
        }]
        if not status_events:
            raise ValueError("historical-blocker-status-not-found")
        event = status_events[-1]["event"]
        status = event.get("to_status") or event.get("status")
        if not isinstance(status, str) or not status:
            raise ValueError(f"historical-blocker-status-unreadable:{event.get('event_id')}")
        # A blocker may be verified by a run-level verification whose event names
        # blocker_ids rather than blocker_id. Include that proof and its exact close
        # event/transitions so callers can inspect the recorded binding end to end.
        verification_rows = [
            item for item in lineage
            if item["event"].get("event_type") in {
                "verification_recorded", "late_verification_recorded",
            }
            and blocker_id in item["event"].get("blocker_ids", [])
        ]
        verification_ids = {item["event"]["event_id"] for item in verification_rows}
        verification_runs = {item["event"].get("run_id") for item in verification_rows}
        existing_ids = {item["event"]["event_id"] for item in lineage}
        for item in [
            *verification_rows,
            *(
                candidate for candidate in population
                if candidate["event"].get("event_type") == "blocker_transitioned"
                and candidate["event"].get("verification_event_id") in verification_ids
            ),
            *(
                candidate for candidate in population
                if candidate["event"].get("event_type") == "run_closed"
                and candidate["event"].get("run_id") in verification_runs
            ),
        ]:
            event_id = item["event"]["event_id"]
            if event_id not in existing_ids:
                lineage.append(item)
                existing_ids.add(event_id)
        lineage.sort(key=lambda item: (item["event"]["recorded_at_utc"], item["_source_index"]))

    return {
        "schema": "legacy-up-status/v1",
        "query": {"kind": "run" if run_id is not None else "blocker",
                  "id": run_id if run_id is not None else blocker_id},
        "recorded_standing": status,
        "authority": "historical-record-only",
        "currently_proven_active_authority": False,
        "source": {
            "source_ledger_sha256": manifest["source_ledger_sha256"],
            "archive_sha256": manifest["archive_sha256"],
            "active_ledger_sha256": sha(active_raw),
            "active_ledger_event_count": len(active_rows),
        },
        "event_lineage": [{
            "event_id": item["event"]["event_id"],
            "event_type": item["event"].get("event_type"),
            "recorded_at_utc": item["event"]["recorded_at_utc"],
            "source": item["_source"],
            **({"recorded_result": item["event"].get("result")}
               if item["event"].get("event_type") == "run_closed" else {}),
            **({"recorded_status": item["event"].get("to_status") or item["event"].get("status")}
               if item["event"].get("event_type") in {
                   "blocker_opened", "blocker_recurred", "blocker_transitioned",
                   "pre_run_blocker_opened", "pre_run_blocker_transitioned",
               } else {}),
            **({"recorded_evidence": item["event"].get("evidence")}
               if "evidence" in item["event"] else {}),
            **({"recorded_source_bundle_hash": item["event"].get("source_bundle_hash")}
               if "source_bundle_hash" in item["event"] else {}),
            **({"recorded_blocker_ids": item["event"].get("blocker_ids")}
               if "blocker_ids" in item["event"] else {}),
            **({"recorded_correction_ids": item["event"].get("correction_ids")}
               if "correction_ids" in item["event"] else {}),
            **({"recorded_changed_artifact_hashes": item["event"].get("changed_artifact_hashes")}
               if "changed_artifact_hashes" in item["event"] else {}),
            **({"recorded_evidence_artifacts": item["event"].get("evidence_artifacts")}
               if "evidence_artifacts" in item["event"] else {}),
            **({"target_run_close_event_id": item["event"].get("target_run_close_event_id")}
               if "target_run_close_event_id" in item["event"] else {}),
            **({"verification_event_id": item["event"].get("verification_event_id")}
               if "verification_event_id" in item["event"] else {}),
        } for item in lineage],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("create", "verify"))
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    if args.action == "create":
        if args.source is None:
            parser.error("create requires --source")
        create(args.source)
    else:
        verify(args.source)


if __name__ == "__main__":
    main()
