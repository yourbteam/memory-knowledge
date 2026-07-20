from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).parents[1]
LEDGER = ROOT / "skills/_shared/verification_ledger.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


AUTHORITY = _load("plan_v2_revision_authority_helpers", ROOT / "tests/test_plan_playbook_v2_authority.py")
LIFECYCLE = _load("plan_v2_revision_lifecycle_helpers", ROOT / "tests/test_plan_playbook_v2_package_lifecycle.py")

canonical_bytes = AUTHORITY.canonical_bytes
run_controller = AUTHORITY.run_controller
sha256_bytes = AUTHORITY.sha256_bytes
write_json = AUTHORITY.write_json


def _draft_args(workspace: dict) -> tuple[object, ...]:
    plan = workspace["repository"] / "plan.md"
    return (
        "record-draft",
        workspace["state"],
        "--plan",
        plan,
        "--surface-map",
        plan.with_name("surface-map.json"),
        "--decisions",
        plan.with_name("decisions.json"),
        "--verification-ledger",
        plan.with_name("verification-ledger.json"),
    )


def test_record_draft_reuses_orphan_receipt_and_exact_replay_bytes(tmp_path: Path) -> None:
    workspace = AUTHORITY._workspace(tmp_path)
    AUTHORITY._init(workspace)
    initial_state = workspace["state"].read_bytes()
    AUTHORITY._draft(workspace)

    run_root = Path(json.loads(workspace["state"].read_text())["run_root"])
    receipts = list((run_root / "revisions").glob("1-*.json"))
    assert len(receipts) == 1
    receipt_path = receipts[0]
    receipt_bytes = receipt_path.read_bytes()

    completed_state = workspace["state"].read_bytes()
    run_controller(*_draft_args(workspace))
    assert workspace["state"].read_bytes() == completed_state
    assert receipt_path.read_bytes() == receipt_bytes
    assert list((run_root / "revisions").glob("1-*.json")) == [receipt_path]

    workspace["state"].write_bytes(initial_state)
    run_controller(*_draft_args(workspace))
    recovered = json.loads(workspace["state"].read_text())
    assert recovered["status"] == "DRAFTED"
    assert recovered["revision_history"][0]["receipt_path"] == receipt_path.relative_to(run_root).as_posix()
    assert receipt_path.read_bytes() == receipt_bytes
    assert list((run_root / "revisions").glob("1-*.json")) == [receipt_path]


def test_verification_ledger_snapshot_retains_relative_evidence_files(tmp_path: Path) -> None:
    workspace = AUTHORITY._workspace(tmp_path)
    AUTHORITY._draft(workspace)
    state = json.loads(workspace["state"].read_text(encoding="utf-8"))
    snapshot = (
        Path(state["run_root"])
        / "snapshots"
        / "verification-ledger"
        / state["verification_ledger_sha256"]
    )

    assert (snapshot / "verification-ledger.json").is_file()
    assert (snapshot / "plan.md").read_bytes() == (workspace["repository"] / "plan.md").read_bytes()
    (workspace["repository"] / "plan.md").unlink()
    (workspace["repository"] / "verification-ledger.json").unlink()

    summary = tmp_path / "verify-summary.md"
    run_controller(
        "render-verify-summary",
        workspace["state"],
        "--out",
        summary,
    )
    assert summary.is_file()

def test_record_draft_rejects_conflicting_companion_and_candidate_sets_without_state_mutation(
    tmp_path: Path,
) -> None:
    workspace = AUTHORITY._workspace(tmp_path)
    AUTHORITY._draft(workspace)
    state_bytes = workspace["state"].read_bytes()
    run_root = Path(json.loads(state_bytes)["run_root"])
    receipt = next((run_root / "revisions").glob("1-*.json"))
    decisions_path = workspace["repository"] / "decisions.json"

    write_json(
        decisions_path,
        {
            "schema_version": 1,
            "decisions": [
                {
                    "id": "D1",
                    "requirement_ids": ["R1"],
                    "question": "Which fixture boundary is authoritative?",
                    "selected_decision": "Use source.txt.",
                    "rejected_alternatives": [],
                    "evidence_ids": ["E1"],
                    "status": "LOCKED",
                }
            ],
        },
    )
    _result, conflict = run_controller(*_draft_args(workspace), ok=False)
    assert conflict["code"] == "REVISION_RECEIPT_CONFLICT"
    assert workspace["state"].read_bytes() == state_bytes
    assert len(list((run_root / "revisions").glob("1-*.json"))) == 1

    write_json(decisions_path, {"schema_version": 1, "decisions": []})
    initial = json.loads(state_bytes)
    initial.update(
        status="INITIALIZED",
        revision=0,
        plan_sha256=None,
        surface_map_sha256=None,
        decisions_sha256=None,
        verification_ledger_sha256=None,
        source_snapshots=[],
        revision_history=[],
    )
    workspace["state"].write_bytes(canonical_bytes(initial))
    receipt.write_bytes(b"{}")
    before = workspace["state"].read_bytes()
    _result, malformed = run_controller(*_draft_args(workspace), ok=False)
    assert malformed["code"] in {"INVALID_SCHEMA", "REVISION_RECEIPT_CONFLICT"}
    assert workspace["state"].read_bytes() == before

    duplicate = receipt.with_name("1-duplicate.json")
    duplicate.write_bytes(b"{}")
    _result, multiple = run_controller(*_draft_args(workspace), ok=False)
    assert multiple["code"] == "REVISION_RECEIPT_CONFLICT"
    assert workspace["state"].read_bytes() == before


def test_record_revision_reuses_orphan_receipt_binds_predecessor_and_rejects_changed_companion(
    tmp_path: Path,
) -> None:
    workspace = LIFECYCLE._make_emittable(tmp_path)
    LIFECYCLE._emit(workspace)
    predecessor_state = workspace["state"].read_bytes()
    predecessor = json.loads(predecessor_state)["revision_history"][0]["receipt_sha256"]
    run_root = Path(json.loads(predecessor_state)["run_root"])
    proposal = run_root / "proposed-revisions" / "2"
    run_controller("prepare-revision", workspace["state"])
    (proposal / "plan.md").write_text("# Revision two\n\nImplement the corrected fixture.\n", encoding="utf-8")
    plan_sha = sha256_bytes((proposal / "plan.md").read_bytes())
    revised_ledger = tmp_path / "revision-two-ledger.json"
    subprocess.run(
        [
            "python3", str(LEDGER), "init", "--kind", "plan", "--target", "plan.md",
            "--plan-sha256", plan_sha, "--evidence-revision-sha256",
            json.loads(predecessor_state)["evidence_index_sha256"], "--output", str(revised_ledger),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    (proposal / "verification-ledger.json").write_bytes(revised_ledger.read_bytes())

    run_controller("record-revision", workspace["state"], "--proposal", proposal)
    completed_state = workspace["state"].read_bytes()
    receipt_path = next((run_root / "revisions").glob("2-*.json"))
    receipt_bytes = receipt_path.read_bytes()
    assert json.loads(receipt_bytes)["predecessor_receipt_sha256"] == predecessor

    run_controller("record-revision", workspace["state"], "--proposal", proposal)
    assert workspace["state"].read_bytes() == completed_state
    assert receipt_path.read_bytes() == receipt_bytes

    workspace["state"].write_bytes(predecessor_state)
    invalidation = workspace["task_root"] / ".plan-package-invalidated.json"
    invalidation.unlink(missing_ok=True)
    run_controller("record-revision", workspace["state"], "--proposal", proposal)
    assert receipt_path.read_bytes() == receipt_bytes
    assert len(list((run_root / "revisions").glob("2-*.json"))) == 1

    stable_state = workspace["state"].read_bytes()
    decisions = json.loads((proposal / "decisions.json").read_text())
    decisions["decisions"].append(
        {
            "id": "D2", "requirement_ids": ["R1"], "question": "Which source?",
            "selected_decision": "Use source.txt.", "rejected_alternatives": [],
            "evidence_ids": ["E1"], "status": "LOCKED",
        }
    )
    (proposal / "decisions.json").write_bytes(canonical_bytes(decisions))
    _result, conflict = run_controller(
        "record-revision", workspace["state"], "--proposal", proposal, ok=False
    )
    assert conflict["code"] == "REVISION_RECEIPT_CONFLICT"
    assert workspace["state"].read_bytes() == stable_state
    assert len(list((run_root / "revisions").glob("2-*.json"))) == 1


def test_state_validation_rejects_mixed_hashes_noncontiguous_history_and_receipt_tamper(
    tmp_path: Path,
) -> None:
    workspace = AUTHORITY._workspace(tmp_path)
    AUTHORITY._draft(workspace)
    stable = workspace["state"].read_bytes()
    state = json.loads(stable)

    state["decisions_sha256"] = None
    workspace["state"].write_bytes(canonical_bytes(state))
    _result, mixed = run_controller("show", workspace["state"], ok=False)
    assert mixed["code"] == "INVALID_STATE"

    state = json.loads(stable)
    state["revision_history"][0]["revision"] = 2
    workspace["state"].write_bytes(canonical_bytes(state))
    _result, history = run_controller("show", workspace["state"], ok=False)
    assert history["code"] == "INVALID_STATE"

    workspace["state"].write_bytes(stable)
    receipt_path = Path(state["run_root"]) / json.loads(stable)["revision_history"][0]["receipt_path"]
    receipt = json.loads(receipt_path.read_text())
    receipt["profile"] = "SUBSTANTIAL"
    receipt_path.write_bytes(canonical_bytes(receipt))
    _result, tamper = run_controller("show", workspace["state"], ok=False)
    assert tamper["code"] == "STATE_TAMPER"


def test_package_validation_rejects_manifest_identity_and_gate_binding_drift(
    tmp_path: Path,
) -> None:
    workspace = LIFECYCLE._make_emittable(tmp_path)
    LIFECYCLE._emit(workspace)
    manifest_path = workspace["task_root"] / "manifest.json"
    stable_manifest = manifest_path.read_bytes()
    manifest = json.loads(stable_manifest)

    manifest["plan_sha256"] = "0" * 64
    manifest_path.write_bytes(canonical_bytes(manifest))
    _result, identity = run_controller("validate-package", workspace["task_root"], ok=False)
    assert identity["code"] == "INVALID_PACKAGE"

    manifest_path.write_bytes(stable_manifest)
    gate_path = workspace["task_root"] / "gate-results.json"
    stable_gate = gate_path.read_bytes()
    gate = json.loads(stable_gate)
    gate["profile"] = "SUBSTANTIAL"
    gate_path.write_bytes(canonical_bytes(gate))
    _result, gate_drift = run_controller("validate-package", workspace["task_root"], ok=False)
    assert gate_drift["code"] in {"PACKAGE_TAMPER", "INVALID_PACKAGE"}
