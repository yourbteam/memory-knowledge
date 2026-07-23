from __future__ import annotations

import base64
import gzip
import hashlib
import json
import subprocess
import types
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import directive_guard
from scripts import legacy_discovery_recovery_v1 as legacy_recovery
from scripts import work_memory as current_work_memory
from scripts import work_memory_bootstrap as bootstrap
from scripts import work_memory_bootstrap_launcher as launcher


CAPTURED_TRUST_FIXTURE = (
    Path(__file__).parent / "fixtures/captured_prevention_v4_trust_anchors.json"
)


def _captured_trust_bytes() -> dict[str, bytes]:
    fixture = json.loads(CAPTURED_TRUST_FIXTURE.read_text())
    result = {}
    for name in ("controller", "bootstrap", "launcher"):
        data = gzip.decompress(base64.b64decode(fixture[f"{name}_gzip_b64"]))
        assert hashlib.sha256(data).hexdigest() == fixture[f"{name}_sha256"]
        result[name] = data
    return result


def _load_controller(source: bytes, logical_path: Path):
    module = types.ModuleType("_fixture_work_memory")
    module.__file__ = str(logical_path)
    module.__package__ = ""
    exec(compile(source, str(logical_path), "exec"), module.__dict__)
    return module


@pytest.fixture
def bootstrap_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest):
    writer_thread_id = "019f75a9-fd91-7650-a43f-d20de5e3ae16"
    monkeypatch.setenv("CODEX_THREAD_ID", writer_thread_id)
    root = tmp_path / "repo"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    controller_source = (Path(__file__).parents[1] / "scripts/work_memory.py").read_bytes()
    bootstrap_source = (
        subprocess.run(
            ["git", "show", "HEAD:scripts/work_memory_bootstrap.py"],
            cwd=Path(__file__).parents[1], check=True, capture_output=True,
        ).stdout
        if getattr(request, "param", None) == "legacy-launcher"
        else (Path(__file__).parents[1] / "scripts/work_memory_bootstrap.py").read_bytes()
    )
    launcher_source = (
        launcher._read_head_launcher_blob()
        if getattr(request, "param", None) == "legacy-launcher"
        else (Path(__file__).parents[1] / "scripts/work_memory_bootstrap_launcher.py").read_bytes()
    )
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
    correction_commands = (
        "python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> "
        "--run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> "
        "--step-id <step-id> --changed-artifact <path> --solution <solution> "
        "--reusable-behavior-changed yes\n"
        "python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> "
        "--run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> "
        "--step-id <step-id> --changed-artifact <path> --solution <solution> "
        "--reusable-behavior-changed yes\n"
        if getattr(request, "param", None) != "missing-row" else ""
    )
    document.write_text(
        f"# Bootstrap Test\n\nDiscoveryId: {lineage}\nCreatedAtUtc: 2026-07-15T00:00:00Z\n\n"
        "## Intended Outcome\nAtomic correction.\n\n"
        "## Why This Looks Repeatable\nController upgrades recur.\n\n"
        "## Required Inputs, Auth, Or Environment\nLocal repository.\n\n"
        "## Commands And Observations\nNo commands yet.\n\n"
        f"{correction_commands}"
        "python3 scripts/work_memory_bootstrap.py run-close\n"
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
    receipt_root = tmp_path / "receipts"
    monkeypatch.setattr(controller, "RECEIPT_ROOT", receipt_root)
    monkeypatch.setattr(current_work_memory, "LEDGER", controller.LEDGER)
    monkeypatch.setattr(current_work_memory, "BLOCKER_VIEW", controller.BLOCKER_VIEW)
    monkeypatch.setattr(current_work_memory, "RECEIPT_ROOT", receipt_root)
    monkeypatch.setattr(bootstrap, "current_work_memory", current_work_memory)
    bundle, bundle_hash, resolved_lineage = controller.resolve_bundle(
        mode="discovery", subject_id=lineage, document=document, manifest=manifest,
        include_bootstrap_trust_anchors=True,
    )
    assert resolved_lineage == lineage
    assert {
        item["path"] for item in bundle if item["repository_key"] == "memory-knowledge"
    }.issuperset(controller.BOOTSTRAP_TRUST_ANCHORS)
    task_id = "bootstrap-test"
    owner_state = controller._claim_task_writer(task_id)
    ownership = controller._ownership_receipt_fields(task_id, owner_state)
    classification = {
        "schema_version": 1, "task_id": task_id, "operation_kind": "other",
        "repeatable": True, "meaningful_steps": 3, "verdict": "operational",
        "reason": "repeatable-or-multistep", "created_at_utc": "2026-07-15T00:00:00Z",
        "expires_at_utc": "2030-07-15T00:00:00Z",
        **ownership,
    }
    class_hash = bootstrap._sha256(bootstrap._canonical_bytes(classification))
    selection = {
        "schema_version": 1, "task_id": task_id,
        "classification_receipt_hash": class_hash,
        "mode": "discovery", "subject_id": lineage, "lineage_id": lineage,
        "document": str(document), "manifest": str(manifest),
        "source_bundle": bundle, "source_bundle_hash": bundle_hash,
        "repository_roots_file": None,
        **ownership,
    }
    selection_hash = bootstrap._sha256(bootstrap._canonical_bytes(selection))
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
        "sealed_bootstrap_launcher_b64": base64.b64encode(launcher_source).decode("ascii"),
        **ownership,
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
        task_id=task_id, **ownership,
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
        "launcher_path": launcher_path,
        "launcher_source": launcher_source,
        "directives_path": directives_path, "directive_state": directive_state,
    }


@pytest.fixture
def captured_legacy_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    writer_thread_id = "019f71de-c7e5-7c53-923a-ce516f9bc219"
    monkeypatch.setenv("CODEX_THREAD_ID", writer_thread_id)
    captured = _captured_trust_bytes()
    root = tmp_path / "repo"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    controller_path = scripts / "work_memory.py"
    bootstrap_path = scripts / "work_memory_bootstrap.py"
    launcher_path = scripts / "work_memory_bootstrap_launcher.py"
    controller_path.write_bytes(captured["controller"])
    bootstrap_path.write_bytes(captured["bootstrap"])
    launcher_path.write_bytes(captured["launcher"])
    target = scripts / "target.py"
    target.write_text("before\n")

    lineage = "discovery-captured-legacy"
    document = root / "operations/sequences/discovery/captured-legacy.md"
    document.parent.mkdir(parents=True)
    document.write_text(
        f"# Captured Legacy\n\nDiscoveryId: {lineage}\n"
        "CreatedAtUtc: 2026-07-18T14:37:54Z\n\n"
        "## Intended Outcome\nAtomic co-blocker correction.\n\n"
        "## Why This Looks Repeatable\nProtected recovery recurs.\n\n"
        "## Required Inputs, Auth, Or Environment\nCurrent owner.\n\n"
        "## Commands And Observations\n"
        "python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> "
        "--run-id <run-id> --blocker-id <blocker-id> --co-blocker-id <co-blocker-id> "
        "--occurrence-id <occurrence-id> --step-id <step-id> "
        "--changed-artifact <path> --solution <solution> "
        "--reusable-behavior-changed yes --correction-id <correction-id>\n"
        "python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> "
        "--run-id <run-id> --blocker-id <blocker-id> --co-blocker-id <co-blocker-id> "
        "--occurrence-id <occurrence-id> --step-id <step-id> "
        "--changed-artifact <path> --solution <solution> "
        "--reusable-behavior-changed yes --correction-id <correction-id>\n\n"
        "## Failure Handling\nFail closed.\n\n"
        "## Verified Path\nCaptured exact bridge.\n\n"
        "## Promotion Readiness\nNot ready.\n"
    )
    manifest = document.with_suffix(".dependencies.json")
    manifest.write_text(json.dumps({
        "schema_version": 1, "lineage_id": lineage,
        "dependencies": [{
            "kind": "file", "repository_key": "memory-knowledge",
            "path_or_sequence_id": "scripts/target.py",
        }],
    }, sort_keys=True) + "\n")

    controller = _load_controller(captured["controller"], controller_path)
    receipt_root = tmp_path / "receipts"
    monkeypatch.setattr(current_work_memory, "LEDGER", controller.LEDGER)
    monkeypatch.setattr(current_work_memory, "BLOCKER_VIEW", controller.BLOCKER_VIEW)
    monkeypatch.setattr(current_work_memory, "RECEIPT_ROOT", receipt_root)
    bundle, bundle_hash, resolved_lineage = controller.resolve_bundle(
        mode="discovery", subject_id=lineage, document=document, manifest=manifest,
        include_bootstrap_trust_anchors=True,
    )
    assert resolved_lineage == lineage
    task_id = "captured-legacy-task"
    old_classification = {
        "schema_version": 1, "task_id": task_id, "operation_kind": "other",
        "repeatable": True, "meaningful_steps": 3, "verdict": "operational",
        "reason": "repeatable-or-multistep", "created_at_utc": "2026-07-18T14:37:00Z",
        "expires_at_utc": "2030-07-18T14:37:00Z",
    }
    old_class_hash = current_work_memory.sha256_bytes(
        current_work_memory.canonical_bytes(old_classification)
    )
    old_selection = {
        "schema_version": 1, "task_id": task_id,
        "classification_receipt_hash": old_class_hash,
        "mode": "discovery", "subject_id": lineage, "lineage_id": lineage,
        "document": str(document), "manifest": str(manifest),
        "source_bundle": bundle, "source_bundle_hash": bundle_hash,
        "repository_roots_file": None,
    }
    old_selection_hash = current_work_memory.sha256_bytes(
        current_work_memory.canonical_bytes(old_selection)
    )
    receipt_dir = receipt_root / task_id
    receipt_dir.mkdir(parents=True)
    (receipt_dir / "classification.json").write_bytes(
        current_work_memory.canonical_bytes(old_classification)
    )
    (receipt_dir / "selection.json").write_bytes(
        current_work_memory.canonical_bytes(old_selection)
    )
    run_id = str(uuid.uuid4())
    blocker_id = "blk-" + "1" * 24
    co_blocker_id = "blk-" + "2" * 24
    occurrence_id = str(uuid.uuid4())
    co_occurrence_id = str(uuid.uuid4())
    legacy_events = [
        controller._event(
            "run_started", run_id=run_id, subject_id=lineage, lineage_id=lineage,
            mode="discovery", operation_kind="other", source_bundle=bundle,
            source_bundle_hash=bundle_hash,
            classification_receipt_hash=old_class_hash,
            selection_receipt_hash=old_selection_hash,
            started_at_utc="2026-07-18T14:37:54Z",
        ),
        controller._event(
            "blocker_opened", run_id=run_id, blocker_id=blocker_id,
            occurrence_id=occurrence_id, fingerprint="1" * 64,
            subject_id=lineage, lineage_id=lineage, step_id="record-protected-correction",
            surface="launcher", symptom="primary", evidence="captured",
            impact="blocked", boundary="trust rotation", status="open",
        ),
        controller._event(
            "blocker_opened", run_id=run_id, blocker_id=co_blocker_id,
            occurrence_id=co_occurrence_id, fingerprint="2" * 64,
            subject_id=lineage, lineage_id=lineage, step_id="record-co-correction",
            surface="launcher", symptom="co blocker", evidence="captured",
            impact="blocked", boundary="atomic correction", status="open",
        ),
    ]
    controller.transact({
        "schema_version": 1, "expected_ledger_hash": None, "events": legacy_events,
    })
    claim = current_work_memory._event(
        "task_writer_claimed", task_id=task_id,
        writer_thread_id=writer_thread_id, ownership_generation=1,
    )
    owner_state = {
        "writer_thread_id": writer_thread_id, "ownership_generation": 1,
        "ownership_event_id": claim["event_id"],
    }
    ownership = current_work_memory._ownership_receipt_fields(task_id, owner_state)
    binding = current_work_memory._event(
        "legacy_run_writer_bound", task_id=task_id, run_id=run_id,
        classification_receipt_hash=old_class_hash,
        selection_receipt_hash=old_selection_hash, **ownership,
    )
    current_work_memory.transact({
        "schema_version": 1, "expected_ledger_hash": None,
        "events": [claim, binding],
    })
    classification = {**old_classification, **ownership}
    class_hash = current_work_memory.sha256_bytes(
        current_work_memory.canonical_bytes(classification)
    )
    selection = {
        **old_selection, **ownership, "classification_receipt_hash": class_hash,
    }
    selection_hash = current_work_memory.sha256_bytes(
        current_work_memory.canonical_bytes(selection)
    )
    (receipt_dir / "classification.json").write_bytes(
        current_work_memory.canonical_bytes(classification)
    )
    (receipt_dir / "selection.json").write_bytes(
        current_work_memory.canonical_bytes(selection)
    )
    state = {
        "schema_version": 1, "task_id": task_id,
        "activated_at_utc": "2026-07-18T14:37:38Z",
        "mode": "discovery", "subject_id": lineage, "lineage_id": lineage,
        "document": str(document), "classification_receipt_hash": class_hash,
        "selection_receipt_hash": selection_hash, "source_bundle_hash": bundle_hash,
        "sealed_controller_path": "scripts/work_memory.py",
        "sealed_controller_sha256": hashlib.sha256(captured["controller"]).hexdigest(),
        "sealed_controller_b64": base64.b64encode(captured["controller"]).decode(),
        "bootstrap_path": "scripts/work_memory_bootstrap.py",
        "bootstrap_sha256": hashlib.sha256(captured["bootstrap"]).hexdigest(),
        "sealed_bootstrap_b64": base64.b64encode(captured["bootstrap"]).decode(),
        "bootstrap_launcher_path": "scripts/work_memory_bootstrap_launcher.py",
        "bootstrap_launcher_sha256": hashlib.sha256(captured["launcher"]).hexdigest(),
        **ownership,
    }
    state_path = receipt_dir / "active.json"
    state_path.write_bytes(current_work_memory.canonical_bytes(state))

    controller_path.write_bytes((Path(__file__).parents[1] / "scripts/work_memory.py").read_bytes())
    bootstrap_path.write_bytes((Path(__file__).parents[1] / "scripts/work_memory_bootstrap.py").read_bytes())
    launcher_path.write_bytes((Path(__file__).parents[1] / "scripts/work_memory_bootstrap_launcher.py").read_bytes())
    target.write_text("after\n")
    directives_path = root / "DIRECTIVES.md"
    directive_state = root / "directive-state.json"
    directives_path.write_text("# directives\n")
    directive_guard.write_directive_read_state(
        directives_path=directives_path, state_path=directive_state, mode="Write code",
    )
    monkeypatch.setattr(launcher, "ROOT", root)
    monkeypatch.setattr(launcher, "LAUNCHER_PATH", launcher_path)
    monkeypatch.setattr(launcher, "RECEIPT_ROOT", receipt_root)
    monkeypatch.setattr(launcher, "_read_head_launcher_blob", lambda: captured["launcher"])
    return {
        "root": root, "controller": current_work_memory, "task_id": task_id,
        "state_path": state_path, "run_id": run_id, "blocker_id": blocker_id,
        "co_blocker_id": co_blocker_id, "occurrence_id": occurrence_id,
        "co_occurrence_id": co_occurrence_id, "target": target,
        "controller_path": controller_path, "bootstrap_path": bootstrap_path,
        "launcher_path": launcher_path, "launcher_source": captured["launcher"],
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


def _trust_anchor_rotation_args(flow: dict[str, object]) -> list[str]:
    args = _correct_args(flow)
    solution_index = args.index("--solution")
    args[solution_index:solution_index] = [
        "--changed-artifact", str(flow["bootstrap_path"]),
        "--changed-artifact", str(flow["launcher_path"]),
    ]
    return args


def _add_co_blocker(flow: dict[str, object]) -> tuple[str, str]:
    controller = flow["controller"]
    co_blocker_id = "blk-" + "2" * 24
    co_occurrence_id = str(uuid.uuid4())
    opened = controller._event(
        "blocker_opened", run_id=flow["run_id"], blocker_id=co_blocker_id,
        occurrence_id=co_occurrence_id, fingerprint="2" * 64,
        subject_id="discovery-bootstrap-test", lineage_id="discovery-bootstrap-test",
        step_id="co-correction", surface="bootstrap", symptom="second defect",
        evidence="same correction fixes both", impact="blocked",
        boundary="correction transaction", status="open",
    )
    controller.transact({
        "schema_version": 1, "expected_ledger_hash": None, "events": [opened],
    })
    return co_blocker_id, co_occurrence_id


def _captured_correction_args(flow: dict[str, object]) -> list[str]:
    args = _trust_anchor_rotation_args(flow)
    args[args.index("correct-controller")] = "record-protected-correction"
    occurrence_index = args.index("--occurrence-id")
    args[occurrence_index:occurrence_index] = [
        "--co-blocker-id", str(flow["co_blocker_id"]),
    ]
    return args


@pytest.mark.parametrize("bootstrap_flow", ["missing-row"], indirect=True)
def test_legacy_recovery_executes_exact_missing_row_migration(
    bootstrap_flow, monkeypatch: pytest.MonkeyPatch,
) -> None:
    flow = bootstrap_flow
    assert bootstrap.main(_correct_args(flow)) == 4
    monkeypatch.setattr(legacy_recovery, "_authorize_recovery", lambda task_id, run_id: {})

    args = _correct_args(flow)
    args[1:1] = [
        "--authorization-task-id", "legacy-recovery-test",
        "--authorization-run-id", str(uuid.uuid4()),
    ]
    assert legacy_recovery.main(args) == 0

    events, _ = flow["controller"].load_ledger()
    related = [event for event in events if event.get("run_id") == flow["run_id"]]
    assert [event["event_type"] for event in related[-4:]] == [
        "correction_recorded", "bundle_transition_recorded",
        "blocker_transitioned", "run_closed",
    ]


def test_legacy_recovery_rejects_discovery_that_has_canonical_row(
    bootstrap_flow, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    flow = bootstrap_flow
    monkeypatch.setattr(legacy_recovery, "_authorize_recovery", lambda task_id, run_id: {})
    args = _correct_args(flow)
    args[1:1] = [
        "--authorization-task-id", "legacy-recovery-test",
        "--authorization-run-id", str(uuid.uuid4()),
    ]

    assert legacy_recovery.main(args) == 4
    assert "legacy-recovery-not-required" in capsys.readouterr().err


def test_legacy_recovery_does_not_treat_prefix_only_as_canonical_row() -> None:
    text = (
        "The controller eventually invokes `python3 scripts/work_memory_bootstrap.py correct` "
        "with arguments that are not recorded here."
    )

    assert legacy_recovery._has_canonical_correction_shape(text) is False


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


def test_preservation_parser_forwards_explicit_target_proof_and_preserved_ids():
    target, verification = str(uuid.uuid4()), str(uuid.uuid4())
    first, second = str(uuid.uuid4()), str(uuid.uuid4())
    args = bootstrap.build_parser().parse_args([
        "preserve-corrections", "--task-id", "remediation-successor",
        "--preserved-task-id", "original-task",
        "--target-correction-id", target,
        "--target-verification-event-id", verification,
        "--preserved-correction-id", first,
        "--preserved-correction-id", second,
    ])

    assert args.target_correction_id == target
    assert args.target_verification_event_id == verification
    assert args.preserved_correction_id == [first, second]


def test_bootstrap_preservation_uses_selected_current_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    document = tmp_path / "sequence.md"
    document.write_text(
        "python3 scripts/work_memory_bootstrap_launcher.py preserve-corrections\n"
    )
    captured = {}

    class ControllerError(Exception):
        def __init__(self, code: str, exit_code: int = 3):
            self.code = code
            self.exit_code = exit_code

    def preserve(args):
        captured["bundle"] = args.authenticated_source_bundle
        captured["bundle_hash"] = args.authenticated_source_bundle_hash
        return {"ok": True, "target_bundle_hash": "a" * 64}

    target_id, verification_id = str(uuid.uuid4()), str(uuid.uuid4())
    target_run, verification_run = str(uuid.uuid4()), str(uuid.uuid4())
    target = {
        "event_type": "correction_recorded", "correction_id": target_id,
        "run_id": target_run,
    }
    verification = {
        "event_type": "verification_recorded", "event_id": verification_id,
        "run_id": verification_run, "correction_ids": [target_id],
        "outcome": "passed", "quality": "same-path", "source_bundle_hash": "a" * 64,
        "subject_id": "subject", "lineage_id": "lineage",
    }
    verification_start = {
        "event_type": "run_started", "run_id": verification_run,
        "selection_receipt_hash": "e" * 64, "predecessor_run_id": target_run,
        "verifies_correction_ids": [target_id],
    }
    module = types.SimpleNamespace(
        cmd_preserve_corrections=preserve, WorkMemoryError=ControllerError,
        load_ledger=lambda: ([target, verification_start, verification], "d" * 64),
        _ownership_snapshot=lambda events: (
            {}, {target_run: "remediation-successor",
                 verification_run: "remediation-successor"},
        ),
    )
    bundle = [{
        "repository_key": "memory-knowledge", "path": "scripts/work_memory.py",
        "sha256": "b" * 64,
    }]
    monkeypatch.setattr(bootstrap, "_load_context", lambda args: {
        "module": module,
        "selection": {
            "document": str(document), "source_bundle": bundle,
            "source_bundle_hash": "a" * 64, "subject_id": "subject",
            "lineage_id": "lineage", "predecessor_run_id": target_run,
            "verifies_correction_ids": [target_id],
        },
        "current_bundle": bundle,
        "current_bundle_hash": "a" * 64,
        "state": {
            "sealed_controller_sha256": "c" * 64,
            "selection_receipt_hash": "e" * 64,
        },
    })
    args = bootstrap.build_parser().parse_args([
        "preserve-corrections", "--task-id", "remediation-successor",
        "--preserved-task-id", "original-task",
        "--target-correction-id", target_id,
        "--target-verification-event-id", verification_id,
        "--preserved-correction-id", str(uuid.uuid4()),
    ])

    result = bootstrap.cmd_preserve_corrections(args)

    assert result["bootstrap_atomic"] is True
    assert captured["bundle_hash"] == "a" * 64
    assert captured["bundle"][0]["path"] == "scripts/work_memory.py"


def test_bootstrap_preservation_rejects_stale_activation_before_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    document = tmp_path / "sequence.md"
    document.write_text(
        "python3 scripts/work_memory_bootstrap_launcher.py preserve-corrections\n"
    )
    called = False

    def preserve(args):
        nonlocal called
        called = True
        return {"target_bundle_hash": "b" * 64}

    module = types.SimpleNamespace(cmd_preserve_corrections=preserve)
    monkeypatch.setattr(bootstrap, "_load_context", lambda args: {
        "module": module,
        "selection": {
            "document": str(document), "source_bundle": [],
            "source_bundle_hash": "a" * 64,
        },
        "current_bundle": [{
            "repository_key": "memory-knowledge", "path": "scripts/work_memory.py",
            "sha256": "c" * 64,
        }],
        "current_bundle_hash": "b" * 64,
    })
    args = bootstrap.build_parser().parse_args([
        "preserve-corrections", "--task-id", "remediation-successor",
        "--preserved-task-id", "original-task",
        "--target-correction-id", str(uuid.uuid4()),
        "--target-verification-event-id", str(uuid.uuid4()),
        "--preserved-correction-id", str(uuid.uuid4()),
    ])

    with pytest.raises(bootstrap.BootstrapError, match="preservation-selected-bundle-stale"):
        bootstrap.cmd_preserve_corrections(args)

    assert called is False


def test_bootstrap_preservation_rejects_same_bundle_from_different_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    document = tmp_path / "sequence.md"
    document.write_text(
        "python3 scripts/work_memory_bootstrap_launcher.py preserve-corrections\n"
    )
    target_id, verification_id = str(uuid.uuid4()), str(uuid.uuid4())
    target_run, verification_run = str(uuid.uuid4()), str(uuid.uuid4())
    called = False

    def preserve(args):
        nonlocal called
        called = True
        return {"target_bundle_hash": "a" * 64}

    events = [
        {"event_type": "correction_recorded", "correction_id": target_id,
         "run_id": target_run},
        {"event_type": "run_started", "run_id": verification_run,
         "selection_receipt_hash": "f" * 64,
         "predecessor_run_id": target_run,
         "verifies_correction_ids": [target_id]},
        {"event_type": "verification_recorded", "event_id": verification_id,
         "run_id": verification_run, "correction_ids": [target_id],
         "outcome": "passed", "quality": "same-path",
         "source_bundle_hash": "a" * 64, "subject_id": "subject",
         "lineage_id": "lineage"},
    ]
    module = types.SimpleNamespace(
        cmd_preserve_corrections=preserve,
        load_ledger=lambda: (events, "d" * 64),
        _ownership_snapshot=lambda rows: (
            {}, {target_run: "remediation-successor",
                 verification_run: "remediation-successor"},
        ),
    )
    bundle = [{
        "repository_key": "memory-knowledge", "path": "scripts/work_memory.py",
        "sha256": "b" * 64,
    }]
    monkeypatch.setattr(bootstrap, "_load_context", lambda args: {
        "module": module,
        "selection": {
            "document": str(document), "source_bundle": bundle,
            "source_bundle_hash": "a" * 64, "subject_id": "subject",
            "lineage_id": "lineage", "predecessor_run_id": target_run,
            "verifies_correction_ids": [target_id],
        },
        "current_bundle": bundle, "current_bundle_hash": "a" * 64,
        "state": {"selection_receipt_hash": "e" * 64},
    })
    args = bootstrap.build_parser().parse_args([
        "preserve-corrections", "--task-id", "remediation-successor",
        "--preserved-task-id", "original-task",
        "--target-correction-id", target_id,
        "--target-verification-event-id", verification_id,
        "--preserved-correction-id", str(uuid.uuid4()),
    ])

    with pytest.raises(bootstrap.BootstrapError, match="preservation-selected-proof-mismatch"):
        bootstrap.cmd_preserve_corrections(args)

    assert called is False


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


def test_launcher_finalizes_exact_existing_correction_without_duplicate_events(
    bootstrap_flow,
):
    flow = bootstrap_flow
    argv = _correct_args(flow)
    correction_id = argv[argv.index("--correction-id") + 1]
    direct = SimpleNamespace(
        run_id=flow["run_id"], blocker_id=flow["blocker_id"],
        occurrence_id=flow["occurrence_id"], co_blocker_id=None,
        step_id="correct-controller",
        changed_artifact=[
            str(Path(flow["root"]) / "scripts/work_memory.py"),
            str(flow["target"]),
        ],
        solution="execute the sealed controller atomically",
        reusable_behavior_changed="yes", supersedes_correction_id=None,
        correction_id=correction_id, event_id=None, transition_event_id=None,
        repo_roots_file=None, finalize_failed_run=False,
    )

    recorded = flow["controller"].cmd_correct(direct)
    before, _ = flow["controller"].load_ledger()
    assert recorded["correction_id"] == correction_id
    assert not any(event["event_type"] == "run_closed" for event in before)

    assert launcher.main(argv) == 0
    finalized, _ = flow["controller"].load_ledger()
    assert sum(event["event_type"] == "correction_recorded" for event in finalized) == 1
    assert sum(
        event["event_type"] == "bundle_transition_recorded" for event in finalized
    ) == 1
    assert sum(event["event_type"] == "blocker_transitioned" for event in finalized) == 1
    assert sum(event["event_type"] == "run_closed" for event in finalized) == 1

    assert launcher.main(argv) == 0
    replayed, _ = flow["controller"].load_ledger()
    assert replayed == finalized


def test_protected_launcher_atomically_corrects_explicit_co_blocker(bootstrap_flow):
    flow = bootstrap_flow
    co_blocker_id, co_occurrence_id = _add_co_blocker(flow)
    args = _correct_args(flow)
    occurrence_index = args.index("--occurrence-id")
    args[occurrence_index:occurrence_index] = ["--co-blocker-id", co_blocker_id]

    assert launcher.main(args) == 0
    events, _ = flow["controller"].load_ledger()

    corrections = [
        event for event in events if event["event_type"] == "correction_recorded"
    ]
    assert len(corrections) == 2
    primary, co = corrections
    assert co["blocker_id"] == co_blocker_id
    assert co["occurrence_id"] == co_occurrence_id
    assert co["primary_correction_id"] == primary["correction_id"]
    transition = next(
        event for event in events if event["event_type"] == "bundle_transition_recorded"
    )
    assert transition["correction_ids"] == [
        primary["correction_id"], co["correction_id"],
    ]
    assert launcher.main(args) == 0


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


def test_sealed_launcher_rotates_all_changed_trust_anchors(
    bootstrap_flow, monkeypatch: pytest.MonkeyPatch,
):
    flow = bootstrap_flow
    monkeypatch.setattr(
        launcher,
        "_read_head_launcher_blob",
        lambda: pytest.fail("legacy HEAD recovery must not run for sealed launcher states"),
    )
    Path(flow["bootstrap_path"]).write_text("# authorized new bootstrap bytes\n")
    Path(flow["launcher_path"]).write_text("# authorized new launcher bytes\n")
    args = _trust_anchor_rotation_args(flow)

    assert launcher.main(args) == 0

    events, _ = flow["controller"].load_ledger()
    correction = next(event for event in events if event["event_type"] == "correction_recorded")
    assert correction["changed_artifacts"] == [
        "scripts/work_memory.py", "scripts/target.py",
        "scripts/work_memory_bootstrap.py",
        "scripts/work_memory_bootstrap_launcher.py",
    ]


def test_sealed_launcher_rotation_rejects_incomplete_drift(bootstrap_flow):
    flow = bootstrap_flow
    before = flow["controller"].LEDGER.read_bytes()
    Path(flow["bootstrap_path"]).write_text("# authorized new bootstrap bytes\n")
    Path(flow["launcher_path"]).write_text("# authorized new launcher bytes\n")
    args = _correct_args(flow)
    solution_index = args.index("--solution")
    args[solution_index:solution_index] = [
        "--changed-artifact", str(flow["bootstrap_path"]),
    ]

    assert launcher.main(args) == 4
    assert flow["controller"].LEDGER.read_bytes() == before


@pytest.mark.parametrize("bootstrap_flow", ["legacy-launcher"], indirect=True)
def test_legacy_head_launcher_blob_rotates_all_changed_trust_anchors(
    bootstrap_flow, monkeypatch: pytest.MonkeyPatch,
):
    flow = bootstrap_flow
    state_path = Path(flow["state_path"])
    state = json.loads(state_path.read_text())
    del state["sealed_bootstrap_launcher_b64"]
    state_path.write_bytes(bootstrap._canonical_bytes(state))
    Path(flow["bootstrap_path"]).write_text("# authorized new bootstrap bytes\n")
    Path(flow["launcher_path"]).write_text("# authorized new launcher bytes\n")
    monkeypatch.setattr(
        launcher, "_read_head_launcher_blob", lambda: flow["launcher_source"],
    )

    assert launcher.main(_trust_anchor_rotation_args(flow)) == 0


def test_captured_ownershipless_predecessor_protected_co_correction_succeeds(
    captured_legacy_flow,
):
    flow = captured_legacy_flow
    args = _captured_correction_args(flow)

    assert launcher.main(args) == 0
    events, _ = current_work_memory.load_ledger()
    related = [event for event in events if event.get("run_id") == flow["run_id"]]
    corrections = [
        event for event in related if event["event_type"] == "correction_recorded"
    ]
    assert len(corrections) == 2
    assert corrections[1]["blocker_id"] == flow["co_blocker_id"]
    assert corrections[1]["occurrence_id"] == flow["co_occurrence_id"]
    assert corrections[1]["primary_correction_id"] == corrections[0]["correction_id"]
    assert related[-1]["event_type"] == "run_closed"
    assert launcher.main(args) == 0


@pytest.mark.parametrize(
    "tamper", [
        "foreign-owner", "head-blob", "controller-snapshot", "bootstrap-snapshot",
    ],
)
def test_captured_protected_co_correction_rejects_untrusted_inputs_without_ledger_write(
    captured_legacy_flow, monkeypatch: pytest.MonkeyPatch, tamper: str,
):
    flow = captured_legacy_flow
    before = current_work_memory.LEDGER.read_bytes()
    if tamper == "foreign-owner":
        monkeypatch.setenv("CODEX_THREAD_ID", "019ee569-0b44-7292-b806-a19fc34c09a2")
    elif tamper == "head-blob":
        monkeypatch.setattr(launcher, "_read_head_launcher_blob", lambda: b"tampered\n")
    else:
        state_path = Path(flow["state_path"])
        state = json.loads(state_path.read_text())
        field = (
            "sealed_controller_b64"
            if tamper == "controller-snapshot" else "sealed_bootstrap_b64"
        )
        state[field] = base64.b64encode(b"tampered\n").decode()
        state_path.write_bytes(current_work_memory.canonical_bytes(state))
    args = _captured_correction_args(flow)

    assert launcher.main(args) == 4
    assert current_work_memory.LEDGER.read_bytes() == before


@pytest.mark.parametrize("bootstrap_flow", ["legacy-launcher"], indirect=True)
@pytest.mark.parametrize(
    "tamper", ["foreign-owner", "head-blob", "bootstrap-snapshot", "incomplete-drift"],
)
def test_legacy_head_launcher_rotation_rejects_untrusted_bridge_inputs(
    bootstrap_flow, monkeypatch: pytest.MonkeyPatch, tamper: str,
):
    flow = bootstrap_flow
    before = flow["controller"].LEDGER.read_bytes()
    state_path = Path(flow["state_path"])
    state = json.loads(state_path.read_text())
    del state["sealed_bootstrap_launcher_b64"]
    if tamper == "bootstrap-snapshot":
        state["sealed_bootstrap_b64"] = base64.b64encode(b"tampered\n").decode()
    state_path.write_bytes(bootstrap._canonical_bytes(state))
    Path(flow["bootstrap_path"]).write_text("# authorized new bootstrap bytes\n")
    Path(flow["launcher_path"]).write_text("# authorized new launcher bytes\n")
    monkeypatch.setattr(
        launcher,
        "_read_head_launcher_blob",
        lambda: b"tampered\n" if tamper == "head-blob" else flow["launcher_source"],
    )
    if tamper == "foreign-owner":
        monkeypatch.setenv("CODEX_THREAD_ID", "019ee569-0b44-7292-b806-a19fc34c09a2")
    args = _trust_anchor_rotation_args(flow)
    if tamper == "incomplete-drift":
        index = args.index(str(flow["launcher_path"]))
        del args[index - 1:index + 1]

    assert launcher.main(args) == 4
    assert flow["controller"].LEDGER.read_bytes() == before


def test_launcher_rejects_tampered_sealed_bootstrap_snapshot(bootstrap_flow):
    flow = bootstrap_flow
    state_path = Path(flow["state_path"])
    state = json.loads(state_path.read_text())
    state["sealed_bootstrap_b64"] = base64.b64encode(b"tampered\n").decode("ascii")
    state_path.write_bytes(bootstrap._canonical_bytes(state))

    assert launcher.main(_correct_args(flow)) == 4


def test_launcher_rejects_tampered_sealed_launcher_snapshot(bootstrap_flow):
    flow = bootstrap_flow
    state_path = Path(flow["state_path"])
    state = json.loads(state_path.read_text())
    state["sealed_bootstrap_launcher_b64"] = base64.b64encode(b"tampered\n").decode()
    state_path.write_bytes(bootstrap._canonical_bytes(state))
    Path(flow["launcher_path"]).write_text("# authorized new launcher bytes\n")

    assert launcher.main(_correct_args(flow)) == 4


def test_launcher_rejects_changed_launcher_bytes(bootstrap_flow, monkeypatch: pytest.MonkeyPatch):
    flow = bootstrap_flow
    changed_launcher = Path(flow["root"]) / "scripts/changed-launcher.py"
    changed_launcher.write_text("# changed trust anchor\n")
    monkeypatch.setattr(launcher, "LAUNCHER_PATH", changed_launcher)

    assert launcher.main(_correct_args(flow)) == 4


def test_launcher_rejects_foreign_writer_before_sealed_bootstrap_mutation(
    bootstrap_flow, monkeypatch: pytest.MonkeyPatch,
):
    flow = bootstrap_flow
    before = flow["controller"].LEDGER.read_bytes()
    monkeypatch.setenv("CODEX_THREAD_ID", "019ee569-0b44-7292-b806-a19fc34c09a2")

    assert launcher.main(_correct_args(flow)) == 4
    assert flow["controller"].LEDGER.read_bytes() == before


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
