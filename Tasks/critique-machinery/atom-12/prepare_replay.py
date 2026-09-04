#!/usr/bin/env python3
"""Relocate the frozen attempt-1 controller record without changing admitted evidence bytes."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    atom = Path(__file__).resolve().parent
    source = atom / "frozen-red" / "attempt-1" / "controller-run"
    target = atom / "experiment" / "replay-source" / "atom-s12-approve-door-attempt-1"
    if target.exists():
        raise SystemExit(f"refuse existing replay target: {target}")
    shutil.copytree(source, target, copy_function=shutil.copy2)

    source_lines = (source / "ledger.jsonl").read_bytes().splitlines()
    records = [json.loads(line) for line in source_lines]
    old_path = records[1]["payload"]["experiment_path"]
    records[1]["payload"]["experiment_path"] = str(
        (target / "evidence" / "experiment-000002").resolve()
    )
    previous = None
    output_lines = []
    for sequence, record in enumerate(records, start=1):
        record["sequence"] = sequence
        record["previous_event_sha256"] = previous
        line = json.dumps(record, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        output_lines.append(line)
        previous = digest(line)
    (target / "ledger.jsonl").write_bytes(b"".join(output_lines))

    receipt = {
        "schema_version": 1,
        "source_run": str(source),
        "replay_run": str(target),
        "only_relocated_field": "ledger[1].payload.experiment_path",
        "source_experiment_path": old_path,
        "replay_experiment_path": records[1]["payload"]["experiment_path"],
        "source_evidence_sha256": digest(
            (source / "evidence" / "experiment-000002" / "development-probe-summary.json").read_bytes()
        ),
        "replay_evidence_sha256": digest(
            (target / "evidence" / "experiment-000002" / "development-probe-summary.json").read_bytes()
        ),
        "replay_latest_event_sha256": previous,
    }
    path = target.parent / "relocation-receipt.json"
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
