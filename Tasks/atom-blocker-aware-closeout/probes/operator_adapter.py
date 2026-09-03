#!/usr/bin/env python3
"""Exercise blocker-aware atom closeout through the real catalog and controller CLIs."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CONTROLLER = ROOT / "skills/atom-building-machinery/scripts/atom_controller.py"
CATALOG = ROOT / "scripts/blocker_catalog.py"
COMPOSE = ROOT / "skills/experiment-machinery/scripts/development_probe_compose.py"
sys.path.insert(0, str(ROOT))
from scripts import work_memory


def load_atom_tests():
    path = ROOT / "tests/test_atom_building_machinery.py"
    spec = importlib.util.spec_from_file_location("atom_closeout_fixtures", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("atom test fixture unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def command(*args: object, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *(str(item) for item in args)], cwd=cwd,
        text=True, capture_output=True, check=False,
    )


def assembly_fixture(work: Path):
    tests = load_atom_tests()
    fixture_root = work / "assembly"
    fixture_root.mkdir()
    manifest_path, assembly = tests._assembled_fixture(fixture_root)
    manifest = json.loads(manifest_path.read_text())["atomic_step"]
    verified = command(COMPOSE, "verify", assembly)
    if verified.returncode != 0:
        raise RuntimeError(verified.stderr)
    assembly_sha256 = json.loads(verified.stdout)["assembly_sha256"]
    return tests, (assembly, manifest, assembly_sha256)


def prepare_atom(path: Path, tests, fixture):
    path.mkdir(parents=True)
    run = tests.start(path, fixture)
    experiment = path / "experiment"
    tests.experiment(experiment, fixture)
    state = json.loads(command(CONTROLLER, "record-experiment", run, experiment).stdout)
    promotion = path / "promotion.json"
    tests.promotion_receipt(promotion, run, state)
    promoted = command(CONTROLLER, "record-promotion", run, promotion)
    if promoted.returncode != 0:
        raise RuntimeError(promoted.stderr)
    return run, json.loads(promoted.stdout)


def seed_run(root: Path) -> tuple[str, str]:
    work_memory.configure_root(root)
    run_id = str(uuid.uuid4())
    subject_id = "atom-closeout-operator"
    task_id = "atom-closeout-operator-task"
    writer_id = os.environ.setdefault("CODEX_THREAD_ID", str(uuid.uuid4()))
    claim_id = str(uuid.uuid4())
    claim = work_memory._event(
        "task_writer_claimed", claim_id, task_id=task_id,
        writer_thread_id=writer_id, ownership_generation=1,
    )
    source_bundle_hash = work_memory.sha256_bytes(work_memory.canonical_bytes([]))
    started = work_memory._event(
        "run_started", run_id=run_id, subject_id=subject_id,
        lineage_id="atom-closeout-lineage", mode="registered",
        operation_kind="workflow-drive", source_bundle=[],
        source_bundle_hash=source_bundle_hash,
        classification_receipt_hash="1" * 64,
        selection_receipt_hash="2" * 64,
        started_at_utc=work_memory.utc_now(),
        task_id=task_id, writer_thread_id=writer_id, ownership_generation=1,
        ownership_event_id=claim_id,
        ownership_sha256=work_memory._ownership_sha256(
            task_id, writer_id, 1, claim_id,
        ),
    )
    work_memory.transact({
        "schema_version": 1, "expected_ledger_hash": None, "events": [claim, started],
    })
    return run_id, subject_id


def open_blocker(root: Path, atom_run: Path, run_id: str, subject_id: str, name: str):
    result = command(
        CATALOG, "--root", root, "open", "--run-id", run_id,
        "--subject-id", subject_id, "--atom-run", atom_run,
        "--step-id", name, "--surface", "atom-closeout",
        "--error-signature", f"{name}-failure", "--symptom", f"{name} remains",
        "--evidence", f"operator evidence for {name}", "--impact", "atom cannot close",
        "--boundary", "atom blocker closeout",
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return json.loads(result.stdout)


def transition(root: Path, run_id: str, blocker_id: str, status: str, *extra: str):
    result = command(
        CATALOG, "--root", root, "transition", "--run-id", run_id,
        "--blocker-id", blocker_id, "--to-status", status, *extra,
    )
    return result


def correction(root: Path, run_id: str, opened: dict[str, str]):
    work_memory.configure_root(root)
    correction_id = str(uuid.uuid4())
    artifact_hash = "3" * 64
    event = work_memory._event(
        "correction_recorded", run_id=run_id, blocker_id=opened["blocker_id"],
        occurrence_id=opened["occurrence_id"], correction_id=correction_id,
        subject_id="atom-closeout-operator", lineage_id="atom-closeout-lineage",
        step_id="closed", changed_artifacts=["scripts/fix.py"],
        changed_artifact_hashes=[artifact_hash], reusable_behavior_changed=False,
        solution="bounded fix",
    )
    work_memory.transact({
        "schema_version": 1, "expected_ledger_hash": None, "events": [event],
    })
    fixed = transition(root, run_id, opened["blocker_id"], "fixed-awaiting-verification")
    if fixed.returncode != 0:
        raise RuntimeError(fixed.stderr)
    return correction_id, artifact_hash


def verify(root: Path, run_id: str, opened: dict[str, str], correction_id: str, artifact_hash: str):
    work_memory.configure_root(root)
    events, _ = work_memory.load_ledger()
    original = next(
        item for item in events
        if item["event_type"] == "run_started" and item["run_id"] == run_id
    )
    successor_run_id = str(uuid.uuid4())
    successor = work_memory._event(
        "run_started", run_id=successor_run_id,
        subject_id=original["subject_id"], lineage_id=original["lineage_id"],
        mode="registered", operation_kind=original["operation_kind"],
        source_bundle=original["source_bundle"],
        source_bundle_hash=original["source_bundle_hash"],
        classification_receipt_hash="4" * 64,
        selection_receipt_hash="5" * 64,
        started_at_utc=work_memory.utc_now(), predecessor_run_id=run_id,
        verifies_correction_ids=[correction_id], task_id=original["task_id"],
        writer_thread_id=original["writer_thread_id"],
        ownership_generation=original["ownership_generation"],
        ownership_event_id=original["ownership_event_id"],
        ownership_sha256=original["ownership_sha256"],
    )
    work_memory.transact({
        "schema_version": 1, "expected_ledger_hash": None, "events": [successor],
    })
    verification_id = str(uuid.uuid4())
    event = work_memory._event(
        "verification_recorded", verification_id, run_id=successor_run_id,
        subject_id="atom-closeout-operator", lineage_id="atom-closeout-lineage",
        source_bundle_hash=work_memory.sha256_bytes(work_memory.canonical_bytes([])),
        outcome="passed", quality="same-path", evidence="real operator path passed",
        blocker_ids=[opened["blocker_id"]], correction_ids=[correction_id],
        changed_artifact_hashes=[artifact_hash],
    )
    work_memory.transact({
        "schema_version": 1, "expected_ledger_hash": None, "events": [event],
    })
    result = transition(
        root, successor_run_id, opened["blocker_id"], "verified",
        "--verification-event-id", verification_id,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return verification_id, successor_run_id


def validate(path: Path, tests, run: Path, state: dict[str, object]):
    receipt = path / "validation.json"
    tests.validation_receipt(receipt, state)
    result = command(CONTROLLER, "record-validation", run, receipt)
    return result, json.loads(result.stdout) if result.returncode == 0 else {}


def run_probe(work: Path) -> dict[str, int]:
    work.mkdir(parents=True, exist_ok=True)
    tests, fixture = assembly_fixture(work)
    opened_events = []
    unresolved_results = []
    for status in ("open", "fixed-awaiting-verification", "verified"):
        root = work / f"unresolved-{status}"
        atom_run, state = prepare_atom(root, tests, fixture)
        run_id, subject_id = seed_run(root)
        opened = open_blocker(root, atom_run, run_id, subject_id, status)
        opened_events.append((root, opened))
        if status != "open":
            correction_id, artifact_hash = correction(root, run_id, opened)
            if status == "verified":
                verify(root, run_id, opened, correction_id, artifact_hash)
        recorded, derived = validate(root, tests, atom_run, state)
        authorized = command(CONTROLLER, "authorize-next", atom_run)
        unresolved_results.append(
            recorded.returncode == 0
            and derived.get("stage") != "complete"
            and authorized.returncode != 0
        )

    valid_root = work / "valid"
    atom_run, state = prepare_atom(valid_root, tests, fixture)
    run_id, subject_id = seed_run(valid_root)
    closed = open_blocker(valid_root, atom_run, run_id, subject_id, "closed")
    correction_id, artifact_hash = correction(valid_root, run_id, closed)
    verification_id, verification_run_id = verify(
        valid_root, run_id, closed, correction_id, artifact_hash,
    )
    closed_result = transition(
        valid_root, verification_run_id, closed["blocker_id"], "closed",
        "--verification-event-id", verification_id, "--remaining-work", "none",
    )

    incidental = open_blocker(valid_root, atom_run, run_id, subject_id, "incidental")
    assigned = command(
        CATALOG, "--root", valid_root, "assign-downstream", "--run-id", run_id,
        "--blocker-id", incidental["blocker_id"], "--downstream-owner", "ops-owner",
        "--evidence", "tracked outside this atom",
    )

    successor = open_blocker(valid_root, atom_run, run_id, subject_id, "successor")
    successor_assigned = command(
        CATALOG, "--root", valid_root, "assign-downstream", "--run-id", run_id,
        "--blocker-id", successor["blocker_id"], "--downstream-owner", "ops-owner",
        "--evidence", "successor is explicitly owned",
    )
    superseded = open_blocker(valid_root, atom_run, run_id, subject_id, "superseded")
    invalid_supersession = transition(
        valid_root, run_id, superseded["blocker_id"], "superseded",
        "--supersession-evidence", "replaced by successor",
        "--superseded-by-blocker-id", successor["blocker_id"],
        "--superseded-by-occurrence-id", str(uuid.uuid4()),
    )
    valid_supersession = transition(
        valid_root, run_id, superseded["blocker_id"], "superseded",
        "--supersession-evidence", "replaced by successor",
        "--superseded-by-blocker-id", successor["blocker_id"],
        "--superseded-by-occurrence-id", successor["occurrence_id"],
    )

    non_gap = open_blocker(valid_root, atom_run, run_id, subject_id, "non-gap")
    work_memory.configure_root(valid_root)
    non_gap_verification = str(uuid.uuid4())
    work_memory.transact({
        "schema_version": 1, "expected_ledger_hash": None,
        "events": [work_memory._event(
            "verification_recorded", non_gap_verification, run_id=run_id,
            subject_id=subject_id, lineage_id="atom-closeout-lineage",
            source_bundle_hash=work_memory.sha256_bytes(work_memory.canonical_bytes([])),
            outcome="passed", quality="same-path", evidence="classification verified",
            blocker_ids=[non_gap["blocker_id"]], correction_ids=[],
            changed_artifact_hashes=[],
        )],
    })
    non_gap_result = transition(
        valid_root, run_id, non_gap["blocker_id"], "non-gap",
        "--verification-event-id", non_gap_verification,
        "--non-gap-evidence", "real classification path found no gap",
    )
    recorded, derived = validate(valid_root, tests, atom_run, state)
    authorized = command(CONTROLLER, "authorize-next", atom_run)
    latest = json.loads((atom_run / "ledger.jsonl").read_text().splitlines()[-1])
    closeout_ref = latest.get("payload", {}).get("blocker_closeout", {})
    closeout = (
        json.loads(Path(closeout_ref["path"]).read_text())
        if isinstance(closeout_ref, dict) and Path(closeout_ref.get("path", "")).is_file()
        else {}
    )

    late = open_blocker(valid_root, atom_run, run_id, subject_id, "late")
    late_authorized = command(CONTROLLER, "authorize-next", atom_run)
    identity_bound = True
    for event_root, opened_event in opened_events + [
        (valid_root, item) for item in [closed, incidental, successor, superseded, non_gap, late]
    ]:
        work_memory.configure_root(event_root)
        events, _ = work_memory.load_ledger()
        matching = [
            item for item in events if item.get("event_id") == opened_event["event_id"]
        ]
        identity_bound = identity_bound and bool(matching) and all(
            field in matching[0]
            for field in ("atomic_step_id", "atom_request_sha256", "atom_run_id", "atom_attempt")
        ) and isinstance(matching[0]["atom_attempt"], int) and matching[0]["atom_attempt"] >= 1
    dispositions = closeout.get("dispositions", [])
    return {
        "identity-binding": int(identity_bound),
        "unresolved-blocked": int(all(unresolved_results)),
        "valid-dispositions": int(
            all(item.returncode == 0 for item in [closed_result, assigned, successor_assigned, valid_supersession, non_gap_result])
            and recorded.returncode == 0 and derived.get("stage") == "complete"
            and authorized.returncode == 0
        ),
        "invalid-supersession-refused": int(invalid_supersession.returncode != 0),
        "summary-preserved": int(bool(closeout) and closeout.get("linked_occurrence_count") == 5),
        "zero-undispositioned": int(
            closeout.get("clear") is True
            and len(dispositions) == 5
            and all(item.get("disposition") for item in dispositions)
        ),
        "authorization-recheck": int(late_authorized.returncode != 0),
        "attempt-identity": int(identity_bound),
    }


def main() -> int:
    work = Path(os.environ["EXPERIMENT_WORK_DIR"])
    frozen = Path(os.environ["EXPERIMENT_INPUT_PATH"])
    case_id = json.loads(frozen.read_text())["case_id"]
    metrics = run_probe(work / "operator")
    event = {
        "schema_version": 1,
        "sequence": int(os.environ.get("EXPERIMENT_TELEMETRY_SEQUENCE_START", "1")),
        "event": "work_completed",
        "recorded_at": datetime.now(UTC).isoformat(),
        "variant_id": os.environ["EXPERIMENT_VARIANT_ID"],
        "message": "Exercised blocker closeout through the catalog and Atom Controller CLIs.",
        "evidence_sha256": hashlib.sha256(frozen.read_bytes()).hexdigest(),
        "observations": {"case_id": case_id, "metrics": metrics},
    }
    with Path(os.environ["EXPERIMENT_TELEMETRY_PATH"]).open("a") as stream:
        stream.write(json.dumps(event, sort_keys=True) + "\n")
    Path(os.environ["EXPERIMENT_RESULT_PATH"]).write_text(json.dumps({
        "schema_version": 1,
        "variant_id": os.environ["EXPERIMENT_VARIANT_ID"],
        "status": "completed",
        "outcome": {"case_id": case_id},
        "metrics": metrics,
        "error": None,
    }, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
