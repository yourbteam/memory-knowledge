#!/usr/bin/env python3
"""Measure one Atom 15 candidate against one frozen real case."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def emit(path: Path, event: str, message: str, evidence: bytes, **observations: object) -> None:
    record = {
        "schema_version": 1,
        "sequence": emit.sequence,
        "event": event,
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "variant_id": os.environ.get("EXPERIMENT_VARIANT_ID", "control"),
        "message": message,
        "evidence_sha256": hashlib.sha256(evidence).hexdigest(),
        "observations": observations,
    }
    emit.sequence += 1
    with path.open("a") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")


emit.sequence = int(os.environ.get("EXPERIMENT_TELEMETRY_SEQUENCE_START", "1"))


def main() -> int:
    frozen_input, result_path, telemetry_path = map(Path, sys.argv[1:4])
    tree = Path(__file__).resolve().parent
    swift = (tree / "skills/atom-building-machinery/scripts/prose_waiver_approval.swift").read_text()
    controller = (tree / "skills/atom-building-machinery/scripts/atom_controller.py").read_text()
    installer = (tree / "working-agreement/install_skills.py").read_text()
    guidance = (tree / "skills/atom-building-machinery/SKILL.md").read_text()
    parent_function = swift.split("func parentName", 1)[-1].split("func authorize", 1)[0]
    before = digest(frozen_input)
    metrics = {
        "visible-exact-request-identity": int(
            'Atom: \\(atomicStep)' in swift
            and 'Request SHA-256: \\(requestSHA)' in swift
            and 'for atom \\(atomicStep), request \\(requestSHA)' in swift
        ),
        "signed-atom-and-request-binding": int(
            '"atomic_step_id": atomicStep' in swift
            and 'SIGNED_AUTHORIZATION_FIELDS = LEGACY_SIGNED_AUTHORIZATION_FIELDS | {"atomic_step_id"}' in controller
            and 'signed authorization atomic_step_id differs from the bound request' in controller
        ),
        "managed-closeout-provenance": int(
            'MANAGED_SOURCE_RECORD_NAME = ".managed-skills-source.json"' in installer
            and "def managed_source_record" in installer
            and "def _blocker_support_root" in controller
            and "managed blocker support hash differs" in controller
        ),
        "bounded-legacy-receipt-compatibility": int(
            "LEGACY_SIGNED_AUTHORIZATION_FIELDS" in controller
            and "bounded legacy shape" in controller
        ),
        "truthful-parent-telemetry": int(
            "proc_pidpath" in parent_function
            and '?? "unavailable"' in parent_function
            and '?? "unknown"' not in parent_function
        ),
        "accurate-operator-guidance": int(
            "Never grant Keychain access" in guidance
            and "dialog left unanswered is not proof" in guidance
            and "support modules are never copied" in guidance
        ),
        "frozen-input-unchanged": int(digest(frozen_input) == before),
    }
    outcome = {"case_sha256": before, "source_checks": metrics}
    evidence = json.dumps(outcome, sort_keys=True).encode()
    emit(telemetry_path, "work_completed", "measured Atom 15 boundaries", evidence, **metrics)
    emit(telemetry_path, "decision_recorded", "recorded Atom 15 candidate metrics", evidence, **metrics)
    result_path.write_text(json.dumps({
        "schema_version": 1,
        "variant_id": os.environ.get("EXPERIMENT_VARIANT_ID", "control"),
        "status": "completed",
        "outcome": outcome,
        "metrics": metrics,
        "error": None,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
