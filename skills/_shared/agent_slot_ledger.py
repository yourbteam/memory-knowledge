#!/usr/bin/env python3
"""Stateful subagent slot ledger.

The runtime agent must be closed before its logical slot can be released. This
helper records that proof; it never closes runtime agents itself.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

ACTIVE = {"reserved", "running", "completed"}
RELEASABLE = {"closed", "abandoned", "released"}
VERSION = 2

_RELEASED_SLOT_TIMESTAMPS = (
    "acquired_at", "bound_at", "completed_at", "closed_at", "abandoned_at",
    "released_at",
)


def released_slot_projection(slot: dict) -> dict:
    """Validate a released ledger slot and return its canonical projection."""
    if not isinstance(slot, dict):
        raise ValueError("released slot must be an object")
    for field in ("id", "label"):
        if not isinstance(slot.get(field), str) or not slot[field]:
            raise ValueError(f"released slot {field} must be a non-empty string")
    if slot.get("state") != "released":
        raise ValueError("released slot state must be released")
    agent_id = slot.get("agent_id")
    if agent_id is not None and (not isinstance(agent_id, str) or not agent_id):
        raise ValueError("released slot agent_id must be null or a non-empty string")
    for field in _RELEASED_SLOT_TIMESTAMPS:
        value = slot.get(field)
        if value is not None and (not isinstance(value, int) or isinstance(value, bool)):
            raise ValueError(f"released slot {field} must be null or an integer")

    evidence = slot.get("evidence", {})
    if not isinstance(evidence, dict):
        raise ValueError("released slot evidence must be an object")
    unknown_evidence = set(evidence) - {"close", "abandon_reason"}
    if unknown_evidence:
        raise ValueError("released slot evidence contains unknown fields")
    for field in ("close", "abandon_reason"):
        value = evidence.get(field)
        if value is not None and (not isinstance(value, str) or not value):
            raise ValueError(f"released slot evidence.{field} must be null or a non-empty string")

    return {
        "id": slot["id"],
        "label": slot["label"],
        "state": "released",
        "agent_id": agent_id,
        "acquired_at": slot.get("acquired_at"),
        "bound_at": slot.get("bound_at"),
        "completed_at": slot.get("completed_at"),
        "closed_at": slot.get("closed_at"),
        "abandoned_at": slot.get("abandoned_at"),
        "released_at": slot.get("released_at"),
        "evidence": {
            "close": evidence.get("close"),
            "abandon_reason": evidence.get("abandon_reason"),
        },
    }


def released_slot_close_evidence_sha256(slot: dict) -> str:
    """Hash the exact canonical released-slot projection bytes."""
    projection = released_slot_projection(slot)
    canonical = json.dumps(
        projection,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def atomic_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".slot-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def load(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"ledger not found: {path}")
    data = json.loads(path.read_text())
    if "version" not in data:
        if data.get("slots"):
            raise SystemExit("BLOCKED: non-empty legacy ledger requires runtime audit")
        data = {"version": VERSION, "max": int(data.get("max", 1)), "slots": []}
        atomic_write(path, data)
    if data.get("version") != VERSION:
        raise SystemExit(f"unsupported ledger version: {data.get('version')}")
    return data


def active_count(data: dict) -> int:
    return sum(slot["state"] in ACTIVE for slot in data["slots"])


def select(data: dict, args: argparse.Namespace, *, bind: bool = False) -> dict:
    selectors = []
    if getattr(args, "slot_id", None):
        selectors.append(("id", args.slot_id))
    if getattr(args, "label", None):
        selectors.append(("label", args.label))
    if not bind and getattr(args, "agent_id", None):
        selectors.append(("agent_id", args.agent_id))
    if len(selectors) != 1:
        raise SystemExit("exactly one slot selector is required")
    key, value = selectors[0]
    matches = [slot for slot in data["slots"] if slot.get(key) == value]
    if len(matches) != 1:
        raise SystemExit(f"selector matched {len(matches)} slots")
    return matches[0]


def save(path: Path, data: dict, message: str) -> int:
    atomic_write(path, data)
    print(message)
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    if args.max < 1:
        raise SystemExit("--max must be >= 1")
    path = Path(args.ledger)
    if path.exists() and not args.force:
        data = load(path)
        if active_count(data):
            raise SystemExit("BLOCKED: cannot initialize while slots are active")
    return save(path, {"version": VERSION, "max": args.max, "slots": []}, "initialized")


def cmd_guard(args: argparse.Namespace) -> int:
    data = load(Path(args.ledger))
    used = active_count(data)
    if used >= data["max"]:
        print(f"BLOCKED: {used}/{data['max']} active")
        return 3
    print(f"OK: {used}/{data['max']} active")
    return 0


def cmd_acquire(args: argparse.Namespace) -> int:
    path, data = Path(args.ledger), load(Path(args.ledger))
    if active_count(data) >= data["max"]:
        return 3
    if any(slot["label"] == args.label and slot["state"] != "released" for slot in data["slots"]):
        raise SystemExit("label already active")
    next_id = 1 + max([int(s["id"][1:]) for s in data["slots"] if s["id"].startswith("s")] or [0])
    data["slots"].append({
        "id": f"s{next_id}", "label": args.label, "state": "reserved",
        "agent_id": None, "acquired_at": int(time.time()), "evidence": {},
    })
    return save(path, data, f"reserved s{next_id} {args.label}")


def cmd_bind(args: argparse.Namespace) -> int:
    path, data = Path(args.ledger), load(Path(args.ledger))
    slot = select(data, args, bind=True)
    if slot["state"] == "running" and slot.get("agent_id") == args.agent_id:
        return 0
    if slot["state"] != "reserved" or slot.get("agent_id"):
        raise SystemExit("bind requires an unbound reserved slot")
    if any(s.get("agent_id") == args.agent_id for s in data["slots"]):
        raise SystemExit("agent id already bound")
    slot.update(state="running", agent_id=args.agent_id, bound_at=int(time.time()))
    return save(path, data, "bound")


def cmd_completed(args: argparse.Namespace) -> int:
    path, data = Path(args.ledger), load(Path(args.ledger))
    slot = select(data, args)
    if slot["state"] == "completed":
        return 0
    if slot["state"] != "running":
        raise SystemExit("mark-completed requires running state")
    slot.update(state="completed", completed_at=int(time.time()))
    return save(path, data, "completed")


def cmd_closed(args: argparse.Namespace) -> int:
    path, data = Path(args.ledger), load(Path(args.ledger))
    slot = select(data, args)
    if slot["state"] == "closed":
        return 0
    if slot["state"] not in {"running", "completed"}:
        raise SystemExit("mark-closed requires running or completed state")
    if not args.close_evidence:
        raise SystemExit("--close-evidence is required")
    slot["state"] = "closed"
    slot["closed_at"] = int(time.time())
    slot["evidence"]["close"] = args.close_evidence
    return save(path, data, "closed")


def cmd_abandon(args: argparse.Namespace) -> int:
    path, data = Path(args.ledger), load(Path(args.ledger))
    slot = select(data, args)
    if slot["state"] == "abandoned":
        if (
            slot.get("agent_id") == args.runtime_agent_id
            and slot.get("evidence", {}).get("close") == args.close_evidence
            and slot.get("evidence", {}).get("abandon_reason") == args.reason
        ):
            return 0
        raise SystemExit("conflicting abandon replay")
    if slot["state"] != "reserved":
        raise SystemExit("abandon requires reserved state")
    if args.runtime_agent_id and not args.close_evidence:
        raise SystemExit("runtime agent abandonment requires close evidence")
    if args.runtime_agent_id and any(
        other is not slot and other.get("agent_id") == args.runtime_agent_id
        for other in data["slots"]
    ):
        raise SystemExit("runtime agent id already exists in another slot")
    slot.update(state="abandoned", abandoned_at=int(time.time()))
    slot["evidence"]["abandon_reason"] = args.reason
    if args.runtime_agent_id:
        slot["agent_id"] = args.runtime_agent_id
        slot["evidence"]["close"] = args.close_evidence
    return save(path, data, "abandoned")


def cmd_release(args: argparse.Namespace) -> int:
    path, data = Path(args.ledger), load(Path(args.ledger))
    slot = select(data, args)
    if slot["state"] == "released":
        return 0
    if slot["state"] not in {"closed", "abandoned"}:
        raise SystemExit("BLOCKED: release requires closed or abandoned state")
    slot.update(state="released", released_at=int(time.time()))
    return save(path, data, "released")


def cmd_reap(args: argparse.Namespace) -> int:
    path, data = Path(args.ledger), load(Path(args.ledger))
    count = 0
    for slot in data["slots"]:
        if slot["state"] in {"closed", "abandoned"}:
            slot.update(state="released", released_at=int(time.time()))
            count += 1
    return save(path, data, f"reaped {count} releasable slots")


def cmd_compact(args: argparse.Namespace) -> int:
    path, data = Path(args.ledger), load(Path(args.ledger))
    if active_count(data):
        raise SystemExit("BLOCKED: cannot compact active ledger")
    before = len(data["slots"])
    data["slots"] = [slot for slot in data["slots"] if slot["state"] != "released"]
    return save(path, data, f"compacted {before - len(data['slots'])} tombstones")


def cmd_status(args: argparse.Namespace) -> int:
    data = load(Path(args.ledger))
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(f"{active_count(data)}/{data['max']} active")
        for slot in data["slots"]:
            print(f"{slot['id']} {slot['label']} {slot['state']} {slot.get('agent_id') or '-'}")
    return 0


def add_selector(parser: argparse.ArgumentParser, *, bind: bool = False) -> None:
    parser.add_argument("--slot-id")
    parser.add_argument("--label")
    if not bind:
        parser.add_argument("--agent-id")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("init"); p.add_argument("ledger"); p.add_argument("--max", type=int, default=1); p.add_argument("--force", action="store_true"); p.set_defaults(func=cmd_init)
    p = sub.add_parser("guard"); p.add_argument("ledger"); p.set_defaults(func=cmd_guard)
    p = sub.add_parser("acquire"); p.add_argument("ledger"); p.add_argument("--label", required=True); p.set_defaults(func=cmd_acquire)
    p = sub.add_parser("bind-agent"); p.add_argument("ledger"); add_selector(p, bind=True); p.add_argument("--agent-id", required=True); p.set_defaults(func=cmd_bind)
    p = sub.add_parser("mark-completed"); p.add_argument("ledger"); add_selector(p); p.set_defaults(func=cmd_completed)
    p = sub.add_parser("mark-closed"); p.add_argument("ledger"); add_selector(p); p.add_argument("--close-evidence", required=True); p.set_defaults(func=cmd_closed)
    p = sub.add_parser("abandon"); p.add_argument("ledger"); add_selector(p); p.add_argument("--reason", required=True); p.add_argument("--runtime-agent-id"); p.add_argument("--close-evidence"); p.set_defaults(func=cmd_abandon)
    p = sub.add_parser("release"); p.add_argument("ledger"); add_selector(p); p.set_defaults(func=cmd_release)
    p = sub.add_parser("reap"); p.add_argument("ledger"); p.set_defaults(func=cmd_reap)
    p = sub.add_parser("compact"); p.add_argument("ledger"); p.set_defaults(func=cmd_compact)
    p = sub.add_parser("status"); p.add_argument("ledger"); p.add_argument("--json", action="store_true"); p.set_defaults(func=cmd_status)
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    raise SystemExit(args.func(args))
