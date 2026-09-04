#!/usr/bin/env python3
"""Regenerate the sequence intake contract binding after an adapter change.

`operations/sequences/sequence-intake-contracts.json` binds every runnable sequence to
its caller interface. Editing the shared adapter changes `adapter_source_sha256` on every
entry, so the dispatch gate refuses every sequence until the binding is regenerated. The
gate is documented but had no implementation: `build_intake_contracts` was reachable only
from `check_intake_contracts` and the tests, so an adapter change was a dead end.

Regenerating blindly would defeat the gate. Its purpose is to catch an adapter edit that
silently alters *another* sequence's caller interface, so this tool separates the two
cases:

  benign    -- new entries, and existing entries differing only in `adapter_source_sha256`
               (the shared-file hash every entry carries)
  interface -- an existing entry whose entrypoint, semantic fields, required or optional
               inputs, or argv shape changed

Benign drift writes. An interface change fails closed and must be acknowledged per
sequence with --accept-interface-change, so the acknowledgement is explicit and reviewable
rather than implied by running the tool.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sequence_intake_adapters as adapters  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
_HASH_ONLY_FIELD = "adapter_source_sha256"


def _classify(stored: dict, rebuilt: dict) -> tuple[list[str], dict[str, list[str]]]:
    """Split drift into added sequence ids and per-sequence interface changes."""

    stored_entries = {row.get("sequence_id"): row for row in stored.get("entries", [])}
    rebuilt_entries = {row["sequence_id"]: row for row in rebuilt["entries"]}
    added = sorted(set(rebuilt_entries) - set(stored_entries))
    interface_changes: dict[str, list[str]] = {}
    for sequence_id in sorted(set(stored_entries) & set(rebuilt_entries)):
        before = stored_entries[sequence_id]
        after = rebuilt_entries[sequence_id]
        changed = sorted(
            field
            for field in set(before) | set(after)
            if before.get(field) != after.get(field) and field != _HASH_ONLY_FIELD
        )
        if changed:
            interface_changes[sequence_id] = changed
    for sequence_id in sorted(set(stored_entries) - set(rebuilt_entries)):
        interface_changes[sequence_id] = ["removed-from-registry"]
    if stored.get("non_runnable") != rebuilt["non_runnable"]:
        interface_changes["<non-runnable-set>"] = ["non_runnable"]
    return added, interface_changes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--write",
        action="store_true",
        help="write the regenerated binding; without it the tool only reports drift",
    )
    parser.add_argument(
        "--accept-interface-change",
        action="append",
        default=[],
        metavar="SEQUENCE_ID",
        help=(
            "acknowledge that this sequence's caller interface changed on purpose "
            "(repeatable); required before --write can rewrite such an entry"
        ),
    )
    args = parser.parse_args(argv)

    stored_path = REPO_ROOT / adapters.INTAKE_CONTRACTS_PATH
    if not stored_path.is_file():
        print(f"intake contracts missing: {stored_path}", file=sys.stderr)
        return 2
    try:
        stored = json.loads(stored_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        print(f"intake contracts unreadable: {stored_path}: {exc}", file=sys.stderr)
        return 2
    rebuilt = adapters.build_intake_contracts(REPO_ROOT)

    if stored == rebuilt:
        print("intake contracts already current; nothing to regenerate.")
        return 0

    added, interface_changes = _classify(stored, rebuilt)
    hash_only = len(rebuilt["entries"]) - len(added) - len(interface_changes)
    print(f"adapter source: {stored['adapter_source_sha256'][:12]} -> "
          f"{rebuilt['adapter_source_sha256'][:12]}")
    print(f"entries added                 : {len(added)} {added if added else ''}")
    print(f"entries re-hashed only        : {hash_only}")
    print(f"entries with interface changes: {len(interface_changes)}")
    for sequence_id, fields in interface_changes.items():
        print(f"    {sequence_id}: {', '.join(fields)}")

    unacknowledged = sorted(set(interface_changes) - set(args.accept_interface_change))
    if not args.write:
        print("\nreport only; pass --write to regenerate.")
        return 1
    if unacknowledged:
        print(
            "\nrefusing to write: these caller interfaces changed and were not "
            "acknowledged:\n    " + "\n    ".join(unacknowledged)
            + "\nRe-verify each adapter, then repeat --accept-interface-change per "
            "sequence id.",
            file=sys.stderr,
        )
        return 3

    stored_path.write_text(
        json.dumps(rebuilt, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    remaining = adapters.check_intake_contracts(REPO_ROOT)
    if remaining:
        print(f"\nwrote binding but drift remains: {remaining}", file=sys.stderr)
        return 4
    print(f"\nwrote {stored_path.relative_to(REPO_ROOT)}; binding is current.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
