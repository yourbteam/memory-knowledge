from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
LEDGER = ROOT / "skills/_shared/verification_ledger.py"
HELPERS_PATH = ROOT / "tests/test_plan_playbook_v2.py"
HELPERS_SPEC = importlib.util.spec_from_file_location(
    "plan_v2_authority_test_helpers", HELPERS_PATH
)
assert HELPERS_SPEC is not None and HELPERS_SPEC.loader is not None
HELPERS = importlib.util.module_from_spec(HELPERS_SPEC)
HELPERS_SPEC.loader.exec_module(HELPERS)

SUCCESS_FIELDS = HELPERS.SUCCESS_FIELDS
canonical_bytes = HELPERS.canonical_bytes
behavior_matrix = HELPERS.behavior_matrix
requirement = HELPERS.requirement
role_input = HELPERS.role_input
run_controller = HELPERS.run_controller
sha256_bytes = HELPERS.sha256_bytes
slot_ledger = HELPERS.slot_ledger
write_json = HELPERS.write_json
PLAN_PACKAGE = HELPERS.PLAN_PACKAGE

SOURCE_SNAPSHOT_FIELDS = {
    "repository_key",
    "source_path",
    "source_tree_sha256",
    "snapshot_path",
    "snapshot_tree_sha256",
    "manifest_path",
    "manifest_sha256",
    "created_at_utc",
}
CONVERGENCE_PROJECTION_FIELDS = {
    "schema_version",
    "task_id",
    "outer_iteration",
    "status",
    "objective",
    "requirements",
    "repository_roots",
    "managed_roots",
    "allowed_paths",
    "source_state_path",
    "source_state_sha256",
}


def _workspace(tmp_path: Path) -> dict:
    repository = tmp_path / "repository"
    repository.mkdir()
    source = repository / "source.txt"
    source.write_text("authoritative fixture\n", encoding="utf-8")
    (repository / ".DS_Store").write_text("excluded\n", encoding="utf-8")
    git_metadata = repository / ".git"
    git_metadata.mkdir()
    (git_metadata / "excluded").write_text("metadata\n", encoding="utf-8")

    task_root = repository / "Tasks" / "planner-v2-authority"
    task_root.mkdir(parents=True)
    charter = {
        "schema_version": 1,
        "objective": "Produce a grounded implementation plan.",
        "allowed_repositories": {"fixture": str(repository.resolve())},
        "allowed_paths": [{"repository_key": "fixture", "path": "source.txt"}],
        "supplied_input_root": None,
        "exclusions": ["No deployment."],
        "deliverables": ["A validated plan package."],
        "approval_boundaries": ["Implementation requires authorization."],
        "change_characteristics": ["NONE"],
    }
    evidence = [
        {
            "id": "E1",
            "requirement_ids": ["R1"],
            "facets": [
                "ACCEPTANCE_OBSERVABLE",
                "CURRENT_BEHAVIOR",
                "IMPLEMENTATION_OWNERSHIP",
            ],
            "source": {
                "kind": "LOCAL_FILE",
                "repository_key": "fixture",
                "path": "source.txt",
                "sha256": sha256_bytes(source.read_bytes()),
            },
            "supported_claim": "The fixture source is the current implementation boundary.",
            "limitations": "Supports only this fixture boundary.",
        }
    ]
    return {
        "repository": repository,
        "source": source,
        "task_root": task_root,
        "state": task_root / ".plan-playbook/state.json",
        "charter": charter,
        "charter_path": write_json(tmp_path / "charter.json", charter),
        "requirements_path": write_json(tmp_path / "requirements.json", [requirement()]),
        "evidence_path": write_json(tmp_path / "evidence-index.json", evidence),
    }


def _init(workspace: dict, *, convergence_state: Path | None = None) -> dict:
    args: list[object] = [
        "init",
        workspace["state"],
        "--task-directory",
        workspace["task_root"],
        "--charter",
        workspace["charter_path"],
        "--entry-mode",
        "DIRECT",
        "--task-size",
        "light",
        "--approval-context",
        "CONVERGENCE" if convergence_state else "ORDINARY",
        "--requirements",
        workspace["requirements_path"],
        "--evidence-index",
        workspace["evidence_path"],
    ]
    if convergence_state:
        args.extend(["--convergence-state", convergence_state])
    _result, payload = run_controller(*args)
    assert set(payload) == SUCCESS_FIELDS
    return json.loads(workspace["state"].read_text(encoding="utf-8"))


def _draft(workspace: dict, *, convergence_state: Path | None = None) -> dict:
    state = _init(workspace, convergence_state=convergence_state)
    plan = tmp_file = workspace["task_root"].parent.parent / "plan.md"
    tmp_file.write_text("# Grounded plan\n\nImplement and verify the fixture boundary.\n", encoding="utf-8")
    plan_sha256 = sha256_bytes(plan.read_bytes())
    surface = {
        "schema_version": 1,
        "items": [
            {
                "id": "S1",
                "requirement_ids": ["R1"],
                "obligation_ids": ["P1"],
                "subsystem": "fixture",
                "files": [{"repository_key": "fixture", "path": "source.txt"}],
                "entry_points": ["source.txt"],
                "contracts": ["fixture source contract"],
                "implementation_steps": ["Update the fixture-owned source boundary."],
                "verification_steps": ["Run the focused fixture test."],
                "risk": "low",
                "evidence_ids": ["E1"],
                "status": "PLANNED",
            }
        ],
        "behavior_matrix": behavior_matrix(),
        "implementation_approval": {
            "granular_changes": [
                {
                    "id": "C1",
                    "repositories": ["fixture"],
                    "allowed_paths": ["source.txt"],
                    "change": "Update the fixture-owned source boundary.",
                }
            ],
            "practical_consequence": {
                "before": "The fixture is unchanged.",
                "after": "The fixture boundary is implemented.",
            },
            "estimated_cost": {
                "implementation_effort": "small",
                "verification_effort": "small",
                "complexity": "low",
                "note": "One local source and focused test.",
            },
        },
    }
    decisions = {"schema_version": 1, "decisions": []}
    surface_path = write_json(plan.with_name("surface-map.json"), surface)
    decisions_path = write_json(plan.with_name("decisions.json"), decisions)
    ledger_path = plan.with_name("verification-ledger.json")
    subprocess.run(
        [
            "python3",
            str(LEDGER),
            "init",
            "--kind",
            "plan",
            "--target",
            "plan.md",
            "--plan-sha256",
            plan_sha256,
            "--evidence-revision-sha256",
            state["evidence_index_sha256"],
            "--output",
            str(ledger_path),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    run_controller(
        "record-draft",
        workspace["state"],
        "--plan",
        plan,
        "--surface-map",
        surface_path,
        "--decisions",
        decisions_path,
        "--verification-ledger",
        ledger_path,
    )
    state = json.loads(workspace["state"].read_text(encoding="utf-8"))
    workspace["references"] = {
        "plan": {"path": f"snapshots/plan/{state['plan_sha256']}.md", "sha256": state["plan_sha256"]},
        "surface-map": {"path": f"snapshots/surface-map/{state['surface_map_sha256']}.json", "sha256": state["surface_map_sha256"]},
        "decisions": {"path": f"snapshots/decisions/{state['decisions_sha256']}.json", "sha256": state["decisions_sha256"]},
        "verification-ledger": {"path": f"snapshots/verification-ledger/{state['verification_ledger_sha256']}/verification-ledger.json", "sha256": state["verification_ledger_sha256"]},
    }
    return state


def _assert_source_snapshot(workspace: dict, state: dict) -> dict:
    assert len(state["source_snapshots"]) == 1
    snapshot = state["source_snapshots"][0]
    assert set(snapshot) == SOURCE_SNAPSHOT_FIELDS
    assert snapshot["repository_key"] == "fixture"
    assert snapshot["source_path"] == str(workspace["repository"].resolve())
    assert snapshot["source_tree_sha256"] == snapshot["snapshot_tree_sha256"]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T.*Z", snapshot["created_at_utc"])

    run_root = Path(state["run_root"])
    manifest_path = run_root / snapshot["manifest_path"]
    tree = run_root / snapshot["snapshot_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert set(manifest) == {"schema_version", "contract_id", "files"}
    assert manifest["schema_version"] == 1
    assert manifest["contract_id"] == "ASSESSMENT_SOURCE_SNAPSHOT_V1"
    expected_files = manifest["files"]
    paths = [item["path"] for item in expected_files]
    assert paths == sorted(set(paths), key=lambda path: path.encode("utf-8"))
    assert {"path": "source.txt", "sha256": sha256_bytes(workspace["source"].read_bytes())} in expected_files
    assert any(path.startswith("Tasks/planner-v2-authority/.plan-playbook/") for path in paths)
    assert not any(path == ".DS_Store" or path.startswith(".git/") for path in paths)
    assert not any("/source-snapshots/" in f"/{path}" for path in paths)
    for item in expected_files:
        copied = tree / item["path"]
        assert copied.is_file()
        assert sha256_bytes(copied.read_bytes()) == item["sha256"]
    assert snapshot["manifest_sha256"] == sha256_bytes(manifest_path.read_bytes())
    assert snapshot["manifest_path"] == f"source-snapshots/{snapshot['manifest_sha256']}/manifest.json"
    assert snapshot["snapshot_path"] == f"source-snapshots/{snapshot['manifest_sha256']}/tree"
    assert snapshot["source_tree_sha256"] == sha256_bytes(canonical_bytes(expected_files))
    assert (tree / "source.txt").read_bytes() == workspace["source"].read_bytes()
    assert not (tree / ".DS_Store").exists()
    assert not (tree / ".git").exists()
    return snapshot


def _prepare_verifier(workspace: dict, state: dict) -> tuple[Path, Path]:
    workspace["source_snapshot"] = state["source_snapshots"][0]
    input_path = write_json(
        workspace["task_root"].parent.parent / "input.json",
        role_input(state, workspace, "VERIFY_PLAN_VERIFIER"),
    )
    slots = slot_ledger(
        workspace["task_root"].parent.parent / "slots.json",
        state="reserved",
        agent_id=None,
    )
    token = workspace["task_root"].parent.parent / "attempt-token.json"
    run_controller(
        "prepare-attempt",
        workspace["state"],
        "--round",
        1,
        "--role",
        "VERIFY_PLAN_VERIFIER",
        "--verification-iteration",
        1,
        "--assigned-coverage-id",
        "C01",
        "--assigned-obligation-id",
        "P1",
        "--slot-id",
        "s1",
        "--slot-ledger",
        slots,
        "--input-envelope",
        input_path,
        "--out",
        token,
    )
    return token, slots


def _outer_state(workspace: dict) -> dict:
    root = str(workspace["repository"].resolve())
    requirement_text = requirement()["text"]
    return {
        "schema_version": 1,
        "task_id": "planner-v2-authority-fixture",
        "objective": workspace["charter"]["objective"],
        "status": "plan",
        "outer_iteration": 3,
        "requirements": {
            "R1": {
                "id": "R1",
                "text": requirement_text,
                "source": "task-intake:R1",
                "status": "open",
            }
        },
        "gaps": {},
        "blockers": {},
        "approvals": {},
        "repositories": {root: {"allowed_paths": ["source.txt"]}},
        "managed_paths": {},
        "stages": {},
        "artifacts": {},
        "blocked_from_status": None,
        "blocked_stage": None,
        "cap_from_status": None,
        "cap_stage": None,
        "cap_attempt": None,
        "created_at": "2026-07-19T00:00:00+00:00",
        "updated_at": "2026-07-19T00:00:00+00:00",
    }


def test_git_source_snapshot_excludes_ignored_environment_and_rejects_visible_symlink(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    (repository / ".gitignore").write_text(".venv/\n", encoding="utf-8")
    (repository / "source.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repository / ".env.remote.backup").write_text(
        "EXAMPLE_VALUE=not-a-secret\n", encoding="utf-8",
    )
    environment = repository / ".venv/bin"
    environment.mkdir(parents=True)
    (environment / "python").symlink_to("/usr/bin/python3")

    records, _payloads = PLAN_PACKAGE.enumerate_assessment_source(repository)

    paths = [item["path"] for item in records]
    assert ".gitignore" in paths
    assert "source.py" in paths
    assert ".env.remote.backup" not in paths
    assert not any(path.startswith(".venv/") for path in paths)

    (repository / "visible-link").symlink_to("source.py")
    with pytest.raises(PLAN_PACKAGE.PlanPackageError) as exc:
        PLAN_PACKAGE.enumerate_assessment_source(repository)
    assert exc.value.code == "UNSAFE_SOURCE_ENTRY"


def test_published_source_snapshot_is_read_only(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot"
    tree = snapshot / "tree/package"
    tree.mkdir(parents=True)
    source = tree / "module.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    (snapshot / "manifest.json").write_text("{}", encoding="utf-8")

    PLAN_PACKAGE.freeze_source_snapshot(snapshot)

    assert snapshot.stat().st_mode & 0o222 == 0
    assert tree.stat().st_mode & 0o222 == 0
    assert source.stat().st_mode & 0o222 == 0
    with pytest.raises(PermissionError):
        (tree / "__pycache__").mkdir()


def test_importing_from_published_snapshot_cannot_create_bytecode(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot"
    package = snapshot / "tree/package"
    package.mkdir(parents=True)
    (package / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (snapshot / "manifest.json").write_text("{}", encoding="utf-8")
    PLAN_PACKAGE.freeze_source_snapshot(snapshot)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.path.insert(0, '.'); import module; assert module.VALUE == 1",
        ],
        cwd=package,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not (package / "__pycache__").exists()


def test_record_draft_creates_controller_owned_source_snapshot_and_isolates_live_mutation(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    state = _draft(workspace)
    snapshot = _assert_source_snapshot(workspace, state)
    frozen = (Path(state["run_root"]) / snapshot["snapshot_path"] / "source.txt").read_bytes()

    workspace["source"].write_text("changed after snapshot\n", encoding="utf-8")
    token, _slots = _prepare_verifier(workspace, state)

    assert token.is_file()
    assert (Path(state["run_root"]) / snapshot["snapshot_path"] / "source.txt").read_bytes() == frozen


@pytest.mark.parametrize("tamper_target", ["snapshot", "manifest"])
def test_source_snapshot_or_manifest_tamper_fails_closed_at_finalization(
    tmp_path: Path, tamper_target: str
) -> None:
    workspace = _workspace(tmp_path)
    state = _draft(workspace)
    snapshot = _assert_source_snapshot(workspace, state)
    token, _slots = _prepare_verifier(workspace, state)
    run_root = Path(state["run_root"])
    if tamper_target == "snapshot":
        target = run_root / snapshot["snapshot_path"] / "source.txt"
        target.chmod(0o644)
        target.write_text(
            "tampered snapshot\n", encoding="utf-8"
        )
    else:
        target = run_root / snapshot["manifest_path"]
        target.chmod(0o644)
        target.write_bytes(
            canonical_bytes(
                {
                    "schema_version": 1,
                    "contract_id": "ASSESSMENT_SOURCE_SNAPSHOT_V1",
                    "files": [],
                }
            )
        )
    released = slot_ledger(
        workspace["task_root"].parent.parent / "released-slots.json",
        state="released",
        agent_id=None,
    )
    before = workspace["state"].read_bytes()
    _result, payload = run_controller(
        "finalize-attempt",
        workspace["state"],
        "--attempt-token",
        token,
        "--slot-ledger",
        released,
        "--status",
        "SPAWN_FAILED",
        ok=False,
    )
    assert payload["ok"] is False
    assert workspace["state"].read_bytes() == before


def test_convergence_init_derives_exact_immutable_entry_projection(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    outer_path = write_json(tmp_path / "outer-state.json", _outer_state(workspace))
    outer_sha256 = sha256_bytes(outer_path.read_bytes())

    state = _init(workspace, convergence_state=outer_path)
    projection_path = Path(state["run_root"]) / "authorizations/convergence-entry.json"
    projection = json.loads(projection_path.read_text(encoding="utf-8"))
    assert set(projection) == CONVERGENCE_PROJECTION_FIELDS
    assert projection == {
        "schema_version": 1,
        "task_id": "planner-v2-authority-fixture",
        "outer_iteration": 3,
        "status": "plan",
        "objective": workspace["charter"]["objective"],
        "requirements": [{"id": "R1", "text": requirement()["text"]}],
        "repository_roots": [str(workspace["repository"].resolve())],
        "managed_roots": [],
        "allowed_paths": [str(workspace["source"].resolve())],
        "source_state_path": str(outer_path.resolve()),
        "source_state_sha256": outer_sha256,
    }
    assert state["approval_authorization_path"] == "authorizations/convergence-entry.json"
    assert state["approval_authorization_sha256"] == sha256_bytes(projection_path.read_bytes())

    first_state = workspace["state"].read_bytes()
    first_projection = projection_path.read_bytes()
    replay = _init(workspace, convergence_state=outer_path)
    assert replay == state
    assert workspace["state"].read_bytes() == first_state
    assert projection_path.read_bytes() == first_projection


@pytest.mark.parametrize("invalid_kind", ["malformed", "scope-mismatch"])
def test_convergence_init_rejects_malformed_or_scope_mismatched_outer_state(
    tmp_path: Path, invalid_kind: str
) -> None:
    workspace = _workspace(tmp_path)
    outer = _outer_state(workspace)
    if invalid_kind == "malformed":
        outer["schema_version"] = 2
    else:
        root = str(workspace["repository"].resolve())
        outer["repositories"][root]["allowed_paths"] = []
    outer_path = write_json(tmp_path / "invalid-outer-state.json", outer)

    _result, payload = run_controller(
        "init",
        workspace["state"],
        "--task-directory",
        workspace["task_root"],
        "--charter",
        workspace["charter_path"],
        "--entry-mode",
        "DIRECT",
        "--task-size",
        "light",
        "--approval-context",
        "CONVERGENCE",
        "--convergence-state",
        outer_path,
        "--requirements",
        workspace["requirements_path"],
        "--evidence-index",
        workspace["evidence_path"],
        ok=False,
    )
    assert payload["ok"] is False
    assert payload["state_sha256"] is None
    assert not workspace["state"].exists()


@pytest.mark.parametrize("drift_target", ["outer-state", "projection"])
def test_convergence_init_replay_fails_closed_on_outer_state_or_projection_drift(
    tmp_path: Path, drift_target: str
) -> None:
    workspace = _workspace(tmp_path)
    outer_path = write_json(tmp_path / "outer-state.json", _outer_state(workspace))
    state = _init(workspace, convergence_state=outer_path)
    projection_path = Path(state["run_root"]) / state["approval_authorization_path"]
    if drift_target == "outer-state":
        outer = json.loads(outer_path.read_text(encoding="utf-8"))
        outer["status"] = "implementation"
        outer_path.write_bytes(canonical_bytes(outer))
    else:
        projection = json.loads(projection_path.read_text(encoding="utf-8"))
        projection["outer_iteration"] += 1
        projection_path.write_bytes(canonical_bytes(projection))

    before = workspace["state"].read_bytes()
    _result, payload = run_controller(
        "init",
        workspace["state"],
        "--task-directory",
        workspace["task_root"],
        "--charter",
        workspace["charter_path"],
        "--entry-mode",
        "DIRECT",
        "--task-size",
        "light",
        "--approval-context",
        "CONVERGENCE",
        "--convergence-state",
        outer_path,
        "--requirements",
        workspace["requirements_path"],
        "--evidence-index",
        workspace["evidence_path"],
        ok=False,
    )
    assert payload["ok"] is False
    assert workspace["state"].read_bytes() == before
