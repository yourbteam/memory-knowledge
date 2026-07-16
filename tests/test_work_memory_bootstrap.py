from __future__ import annotations

import base64
import json
import types
import uuid
from pathlib import Path

import pytest

from scripts import directive_guard
from scripts import work_memory_bootstrap as bootstrap
from scripts import work_memory_bootstrap_launcher as launcher


def _load_controller(source: bytes, logical_path: Path):
    module = types.ModuleType("_fixture_work_memory")
    module.__file__ = str(logical_path)
    module.__package__ = ""
    exec(compile(source, str(logical_path), "exec"), module.__dict__)
    return module


@pytest.fixture
def bootstrap_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "repo"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    controller_source = (Path(__file__).parents[1] / "scripts/work_memory.py").read_bytes()
    bootstrap_source = (Path(__file__).parents[1] / "scripts/work_memory_bootstrap.py").read_bytes()
    launcher_source = (
        Path(__file__).parents[1] / "scripts/work_memory_bootstrap_launcher.py"
    ).read_bytes()
    controller_path = scripts / "work_memory.py"
    bootstrap_path = scripts / "work_memory_bootstrap.py"
    launcher_path = scripts / "work_memory_bootstrap_launcher.py"
    controller_path.write_bytes(controller_source)
    bootstrap_path.write_bytes(bootstrap_source)
    launcher_path.write_bytes(launcher_source)
    target = scripts / "target.py"
    target.write_text("before\n")

    lineage = "discovery-bootstrap-test"
    document = root / "operations/sequences/discovery/bootstrap-test.md"
    document.parent.mkdir(parents=True)
    document.write_text(
        f"# Bootstrap Test\n\nDiscoveryId: {lineage}\nCreatedAtUtc: 2026-07-15T00:00:00Z\n\n"
        "## Intended Outcome\nAtomic correction.\n\n"
        "## Why This Looks Repeatable\nController upgrades recur.\n\n"
        "## Required Inputs, Auth, Or Environment\nLocal repository.\n\n"
        "## Commands And Observations\nNo commands yet.\n\n"
        "python3 scripts/work_memory_bootstrap_launcher.py correct\n"
        "python3 scripts/work_memory_bootstrap_launcher.py run-close\n\n"
        "## Failure Handling\nFail closed.\n\n"
        "## Verified Path\nPending.\n\n"
        "## Promotion Readiness\nNot ready.\n"
    )
    manifest = document.with_suffix(".dependencies.json")
    manifest.write_text(json.dumps({
        "schema_version": 1,
        "lineage_id": lineage,
        "dependencies": [
            {"kind": "file", "repository_key": "memory-knowledge", "path_or_sequence_id": "scripts/target.py"},
        ],
    }, sort_keys=True) + "\n")

    controller = _load_controller(controller_source, controller_path)
    bundle, bundle_hash, resolved_lineage = controller.resolve_bundle(
        mode="discovery", subject_id=lineage, document=document, manifest=manifest,
        include_bootstrap_trust_anchors=True,
    )
    assert resolved_lineage == lineage
    assert {
        item["path"] for item in bundle if item["repository_key"] == "memory-knowledge"
    }.issuperset(controller.BOOTSTRAP_TRUST_ANCHORS)
    task_id = "bootstrap-test"
    classification = {
        "schema_version": 1, "task_id": task_id, "operation_kind": "other",
        "repeatable": True, "meaningful_steps": 3, "verdict": "operational",
        "reason": "repeatable-or-multistep", "created_at_utc": "2026-07-15T00:00:00Z",
        "expires_at_utc": "2030-07-15T00:00:00Z",
    }
    class_hash = bootstrap._sha256(bootstrap._canonical_bytes(classification))
    selection = {
        "schema_version": 1, "task_id": task_id,
        "classification_receipt_hash": class_hash,
        "mode": "discovery", "subject_id": lineage, "lineage_id": lineage,
        "document": str(document), "manifest": str(manifest),
        "source_bundle": bundle, "source_bundle_hash": bundle_hash,
        "repository_roots_file": None,
    }
    selection_hash = bootstrap._sha256(bootstrap._canonical_bytes(selection))
    receipt_root = tmp_path / "receipts"
    task_receipts = receipt_root / task_id
    task_receipts.mkdir(parents=True)
    (task_receipts / "classification.json").write_bytes(bootstrap._canonical_bytes(classification))
    (task_receipts / "selection.json").write_bytes(bootstrap._canonical_bytes(selection))
    state = {
        "schema_version": 1, "task_id": task_id, "activated_at_utc": "2026-07-15T00:00:00Z",
        "mode": "discovery", "subject_id": lineage, "lineage_id": lineage,
        "document": str(document), "classification_receipt_hash": class_hash,
        "selection_receipt_hash": selection_hash, "source_bundle_hash": bundle_hash,
        "sealed_controller_path": "scripts/work_memory.py",
        "sealed_controller_sha256": controller.sha256_bytes(controller_source),
        "sealed_controller_b64": base64.b64encode(controller_source).decode("ascii"),
        "bootstrap_path": "scripts/work_memory_bootstrap.py",
        "bootstrap_sha256": controller.sha256_bytes(bootstrap_source),
        "sealed_bootstrap_b64": base64.b64encode(bootstrap_source).decode("ascii"),
        "bootstrap_launcher_path": "scripts/work_memory_bootstrap_launcher.py",
        "bootstrap_launcher_sha256": controller.sha256_bytes(launcher_source),
    }
    state_path = task_receipts / "active.json"
    state_path.write_bytes(bootstrap._canonical_bytes(state))
    directives_path = root / "DIRECTIVES.md"
    directives_path.write_text("# test directives\n")
    directive_state = tmp_path / "directive-state.json"
    directive_guard.write_directive_read_state(
        directives_path=directives_path, state_path=directive_state, mode="Write code",
    )

    run_id = str(uuid.uuid4())
    blocker_id = "blk-" + "1" * 24
    occurrence_id = str(uuid.uuid4())
    start = controller._event(
        "run_started", run_id=run_id, subject_id=lineage, lineage_id=lineage,
        mode="discovery", operation_kind="other", source_bundle=bundle,
        source_bundle_hash=bundle_hash, classification_receipt_hash=class_hash,
        selection_receipt_hash=selection_hash, started_at_utc="2026-07-15T00:00:00Z",
    )
    opened = controller._event(
        "blocker_opened", run_id=run_id, blocker_id=blocker_id,
        occurrence_id=occurrence_id, fingerprint="1" * 64, subject_id=lineage,
        lineage_id=lineage, step_id="correct-controller", surface="bootstrap",
        symptom="controller changed", evidence="captured", impact="blocked",
        boundary="sealed controller", status="open",
    )
    controller.transact({"schema_version": 1, "expected_ledger_hash": None, "events": [start, opened]})

    monkeypatch.setattr(bootstrap, "ROOT", root)
    monkeypatch.setattr(bootstrap, "BOOTSTRAP_PATH", bootstrap_path)
    monkeypatch.setattr(bootstrap, "RECEIPT_ROOT", receipt_root)
    monkeypatch.setattr(bootstrap, "_require_directives", lambda args: None)
    monkeypatch.setattr(launcher, "ROOT", root)
    monkeypatch.setattr(launcher, "LAUNCHER_PATH", launcher_path)
    monkeypatch.setattr(launcher, "RECEIPT_ROOT", receipt_root)
    controller_path.write_text("this is not valid python\n")
    target.write_text("after\n")
    return {
        "root": root, "controller": controller, "task_id": task_id,
        "state_path": state_path, "run_id": run_id, "blocker_id": blocker_id,
        "occurrence_id": occurrence_id, "target": target,
        "bootstrap_path": bootstrap_path,
        "directives_path": directives_path, "directive_state": directive_state,
    }


def _correct_args(flow: dict[str, object]) -> list[str]:
    correction_id = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"memory-knowledge:{flow['run_id']}:{flow['blocker_id']}:{flow['occurrence_id']}",
    )
    return [
        "correct", "--task-id", str(flow["task_id"]), "--state", str(flow["state_path"]),
        "--run-id", str(flow["run_id"]), "--blocker-id", str(flow["blocker_id"]),
        "--occurrence-id", str(flow["occurrence_id"]), "--step-id", "correct-controller",
        "--changed-artifact", str(Path(flow["root"]) / "scripts/work_memory.py"),
        "--changed-artifact", str(flow["target"]),
        "--solution", "execute the sealed controller atomically",
        "--reusable-behavior-changed", "yes",
        "--correction-id", str(correction_id),
        "--directives-path", str(flow["directives_path"]),
        "--directive-state", str(flow["directive_state"]),
    ]


def test_correct_parser_preserves_multiple_supersession_ids():
    first, second = str(uuid.uuid4()), str(uuid.uuid4())
    args = bootstrap.build_parser().parse_args([
        "correct", "--task-id", "bootstrap-test", "--run-id", str(uuid.uuid4()),
        "--blocker-id", "blk-" + "1" * 24, "--occurrence-id", str(uuid.uuid4()),
        "--step-id", "correct-controller", "--changed-artifact", "scripts/target.py",
        "--solution", "preserve the correction contract", "--reusable-behavior-changed", "yes",
        "--supersedes-correction-id", first, "--supersedes-correction-id", second,
    ])

    assert args.supersedes_correction_id == [first, second]


def test_sealed_hash_adapter_rejects_repository_roots_drift():
    class ControllerError(Exception):
        pass

    module = types.SimpleNamespace(WorkMemoryError=ControllerError)
    sealed = bootstrap._sealed_artifact_hashes(
        module,
        [{"repository_key": "external", "path": "src/target.py"}],
        ["a" * 64],
        "/tmp/repository-roots.json",
    )

    assert sealed(["/tmp/external/src/target.py"], "/tmp/repository-roots.json") == (
        [{"repository_key": "external", "path": "src/target.py"}],
        ["a" * 64],
    )
    with pytest.raises(ControllerError, match="bootstrap-repository-roots-mismatch"):
        sealed(["/tmp/external/src/target.py"], "/tmp/other-roots.json")

    snapshot = {"external": "/tmp/external"}
    snapshot_sealed = bootstrap._sealed_artifact_hashes(
        module,
        [{"repository_key": "external", "path": "src/target.py"}],
        ["a" * 64],
        None,
        snapshot,
    )
    assert snapshot_sealed(
        ["/tmp/external/src/target.py"], repository_roots=snapshot,
    ) == (
        [{"repository_key": "external", "path": "src/target.py"}],
        ["a" * 64],
    )
    with pytest.raises(ControllerError, match="bootstrap-repository-roots-mismatch"):
        snapshot_sealed(
            ["/tmp/external/src/target.py"],
            repository_roots={"external": "/tmp/other"},
        )


def test_sealed_hash_adapter_accepts_snapshotted_repository_roots_keyword():
    class ControllerError(Exception):
        pass

    module = types.SimpleNamespace(WorkMemoryError=ControllerError)
    roots = {"memory-knowledge": "/tmp/memory-knowledge"}
    sealed = bootstrap._sealed_artifact_hashes(
        module, ["scripts/target.py"], ["a" * 64], None, roots,
    )

    assert sealed(
        ["scripts/target.py"], repository_roots=roots,
    ) == (["scripts/target.py"], ["a" * 64])
    with pytest.raises(ControllerError, match="bootstrap-repository-roots-mismatch"):
        sealed(["scripts/target.py"], repository_roots=None)


def test_bootstrap_artifact_identity_preserves_repository_qualification():
    assert bootstrap._artifact_identity("scripts/target.py") == (
        "memory-knowledge", "scripts/target.py",
    )
    assert bootstrap._artifact_identity({
        "repository_key": "external", "path": "src/target.py",
    }) == ("external", "src/target.py")


def test_atomic_bootstrap_corrects_with_unimportable_current_controller_and_closes_run(bootstrap_flow):
    flow = bootstrap_flow
    assert bootstrap.main(_correct_args(flow)) == 0
    events, _ = flow["controller"].load_ledger()
    correction = next(event for event in events if event["event_type"] == "correction_recorded")
    assert correction["changed_artifacts"] == ["scripts/work_memory.py", "scripts/target.py"]
    assert flow["controller"].BLOCKER_VIEW.is_file()
    assert any(event["event_type"] == "run_closed" for event in events)
    assert bootstrap.main(_correct_args(flow)) == 0
    events_after_retry, _ = flow["controller"].load_ledger()
    assert events_after_retry == events


def test_launcher_executes_sealed_old_bootstrap_to_correct_new_bootstrap(bootstrap_flow):
    flow = bootstrap_flow
    Path(flow["bootstrap_path"]).write_text("# authorized new bootstrap bytes\n")
    args = _correct_args(flow)
    solution_index = args.index("--solution")
    args[solution_index:solution_index] = [
        "--changed-artifact", str(flow["bootstrap_path"]),
    ]

    assert launcher.main(args) == 0

    events, _ = flow["controller"].load_ledger()
    correction = next(event for event in events if event["event_type"] == "correction_recorded")
    assert correction["changed_artifacts"] == [
        "scripts/work_memory.py", "scripts/target.py", "scripts/work_memory_bootstrap.py",
    ]
    assert any(event["event_type"] == "run_closed" for event in events)


def test_launcher_rejects_tampered_sealed_bootstrap_snapshot(bootstrap_flow):
    flow = bootstrap_flow
    state_path = Path(flow["state_path"])
    state = json.loads(state_path.read_text())
    state["sealed_bootstrap_b64"] = base64.b64encode(b"tampered\n").decode("ascii")
    state_path.write_bytes(bootstrap._canonical_bytes(state))

    assert launcher.main(_correct_args(flow)) == 4


def test_launcher_rejects_changed_launcher_bytes(bootstrap_flow, monkeypatch: pytest.MonkeyPatch):
    flow = bootstrap_flow
    changed_launcher = Path(flow["root"]) / "scripts/changed-launcher.py"
    changed_launcher.write_text("# changed trust anchor\n")
    monkeypatch.setattr(launcher, "LAUNCHER_PATH", changed_launcher)

    assert launcher.main(_correct_args(flow)) == 4


def test_discovery_bootstrap_ignores_unrelated_registry_change(bootstrap_flow):
    flow = bootstrap_flow
    registry = Path(flow["root"]) / "operations/sequences/SEQUENCES.md"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text("# Unrelated registered sequence change\n")

    assert bootstrap.main(_correct_args(flow)) == 0
    events, _ = flow["controller"].load_ledger()
    assert any(event["event_type"] == "correction_recorded" for event in events)


@pytest.mark.parametrize(
    "tamper",
    ["controller-bytes", "bootstrap-bytes", "missing-artifact", "legacy-state", "selection-receipt"],
)
def test_atomic_bootstrap_rejects_tampering_and_incomplete_drift(bootstrap_flow, tamper):
    flow = bootstrap_flow
    args = _correct_args(flow)
    if tamper == "controller-bytes":
        state = json.loads(Path(flow["state_path"]).read_text())
        state["sealed_controller_b64"] = base64.b64encode(b"tampered\n").decode("ascii")
        Path(flow["state_path"]).write_bytes(bootstrap._canonical_bytes(state))
    elif tamper == "bootstrap-bytes":
        bootstrap.BOOTSTRAP_PATH.write_text("tampered\n")
    elif tamper == "legacy-state":
        state = json.loads(Path(flow["state_path"]).read_text())
        del state["sealed_controller_b64"]
        Path(flow["state_path"]).write_bytes(bootstrap._canonical_bytes(state))
    elif tamper == "selection-receipt":
        selection_path = Path(flow["state_path"]).with_name("selection.json")
        selection = json.loads(selection_path.read_text())
        selection["subject_id"] = "tampered"
        selection_path.write_bytes(bootstrap._canonical_bytes(selection))
    else:
        index = args.index(str(flow["target"]))
        del args[index - 1:index + 1]

    assert bootstrap.main(args) == 4
    events, _ = flow["controller"].load_ledger()
    assert not any(event["event_type"] == "correction_recorded" for event in events)
