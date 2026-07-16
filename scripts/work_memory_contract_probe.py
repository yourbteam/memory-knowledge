#!/usr/bin/env python3
"""Probe shared skill wording and receipt refusal/success contracts without operations."""

from __future__ import annotations

import argparse
import json
import tempfile
import uuid
from argparse import Namespace
from pathlib import Path

try:
    from scripts import sequence_guard, work_memory
except ImportError:  # direct script execution
    import sequence_guard  # type: ignore
    import work_memory  # type: ignore


SKILLS = ("working-agreement", "task-intake", "sequence-runner", "blocker-catalog")
REQUIRED = {
    "working-agreement": ("task-intake", "sequence-runner", "blocker-catalog", "auto-capture"),
    "task-intake": ("work_memory.py classify", "operation receipt"),
    "sequence-runner": ("work_memory.py select", "--task-id", "run-start", "same-path"),
    "blocker-catalog": ("blocker_catalog.py open", "work_memory.py correct", "same-path"),
}


def inspect_skills(root: Path) -> dict[str, str]:
    hashes = {}
    for name in SKILLS:
        path = root / name / "SKILL.md"
        if not path.is_file():
            raise RuntimeError(f"missing-skill:{name}")
        text = path.read_text()
        missing = [token for token in REQUIRED[name] if token not in text]
        if missing:
            raise RuntimeError(f"skill-contract-gap:{name}:{','.join(missing)}")
        hashes[name] = work_memory.sha256_bytes(path.read_bytes())
    return hashes


def discovery_fixture(root: Path) -> Path:
    path = root / "operations/sequences/discovery/probe.md"
    path.parent.mkdir(parents=True)
    discovery_id = "discovery-" + str(uuid.uuid4())
    path.write_text(f"""# Sequence Discovery Log: probe

DiscoveryId: {discovery_id}
Status: discovery
CreatedAtUtc: 2026-01-01T00:00:00Z
RegisteredSequenceMatch: none

## Intended Outcome

Probe receipt behavior.

## Why This Looks Repeatable

Contract verification.

## Required Inputs, Auth, Or Environment

- isolated fixture

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| probe | echo probe | passed | none |

## Failure Handling

Stop on any mismatch.

## Verified Path

- Receipt verification passed.

## Promotion Readiness

- [x] Commands are stable enough to script or document.
- [x] Required inputs are known.
- [x] Failure handling is known.
- [x] Verification evidence is known.
- [x] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
""")
    path.with_suffix(".dependencies.json").write_text(json.dumps(
        {"schema_version": 1, "lineage_id": discovery_id, "dependencies": []},
        sort_keys=True,
    ) + "\n")
    return path


def registered_fixture(root: Path) -> Path:
    path = root / "operations/sequences/probe/sequence.md"
    path.parent.mkdir(parents=True)
    path.write_text("# Probe\n\n```bash\necho probe\n```\n")
    path.with_name("dependencies.json").write_text(json.dumps({
        "schema_version": 1, "lineage_id": "probe", "dependencies": [],
    }, sort_keys=True) + "\n")
    return path


def trust_anchor_fixture(root: Path) -> None:
    for relative in work_memory.BOOTSTRAP_TRUST_ANCHORS:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# probe fixture: {relative}\n")


def run_probe(skills_root: Path, mode: str) -> dict:
    hashes = inspect_skills(skills_root)
    old_receipts, old_root = work_memory.RECEIPT_ROOT, work_memory.ROOT
    old_registry_rows = work_memory.registry_rows
    with tempfile.TemporaryDirectory(prefix="work-memory-probe-") as raw:
        temp = Path(raw)
        work_memory.RECEIPT_ROOT = temp / "receipts"
        task_id = f"probe-{mode}"
        refused = False
        try:
            sequence_guard.verify_receipts(task_id)
        except work_memory.WorkMemoryError as exc:
            refused = exc.exit_code == 4 and exc.code == "missing-classification-receipt"
        if not refused:
            raise RuntimeError("missing-receipts-were-not-refused")
        work_memory.cmd_classify(Namespace(
            task_id=task_id, operation_kind="workflow-drive" if mode == "registered" else "other",
            repeatable="yes", meaningful_steps=3,
        ))
        work_memory.ROOT = temp.resolve()
        trust_anchor_fixture(work_memory.ROOT)
        if mode == "registered":
            registered = registered_fixture(work_memory.ROOT)
            work_memory.registry_rows = lambda: ([{
                "sequence_id": "probe", "folder": "operations/sequences/probe/",
                "operation_kinds": "workflow-drive", "lineage_id": "probe",
            }], "f" * 64)
            selection = work_memory.cmd_select(Namespace(
                task_id=task_id, sequence_id="probe",
                discovery_log=None, fingerprint=None, verification_successor_of=None,
                verifies_correction_id=None, repo_roots_file=None,
            ))
        else:
            discovery = discovery_fixture(work_memory.ROOT)
            selection = work_memory.cmd_select(Namespace(
                task_id=task_id, sequence_id=None, discovery_log=str(discovery),
                fingerprint=None, verification_successor_of=None,
                verifies_correction_id=None, repo_roots_file=None,
            ))
        verified = sequence_guard.verify_receipts(task_id)
        work_memory.RECEIPT_ROOT, work_memory.ROOT = old_receipts, old_root
        work_memory.registry_rows = old_registry_rows
        return {
            "ok": True, "mode": mode, "skills_root": str(skills_root),
            "missing_receipts_refused": refused, "subject_id": selection["subject_id"],
            "source_bundle_hash": verified["source_bundle_hash"], "skill_hashes": hashes,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skills-root", type=Path, required=True)
    parser.add_argument("--mode", choices=["registered", "discovery"], required=True)
    args = parser.parse_args()
    print(json.dumps(run_probe(args.skills_root.resolve(), args.mode), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
