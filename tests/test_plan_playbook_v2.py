from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
CONTROLLER = ROOT / "skills/plan-playbook/scripts/plan_package.py"

CONTROLLER_SPEC = importlib.util.spec_from_file_location("plan_playbook_v2_package", CONTROLLER)
assert CONTROLLER_SPEC is not None and CONTROLLER_SPEC.loader is not None
PLAN_PACKAGE = importlib.util.module_from_spec(CONTROLLER_SPEC)
CONTROLLER_SPEC.loader.exec_module(PLAN_PACKAGE)

pytestmark = pytest.mark.skipif(
    not CONTROLLER.is_file(),
    reason="Planner controller is being implemented by the controller lane",
)

SUCCESS_FIELDS = {"schema_version", "command", "ok", "status", "state_sha256", "code"}
HASH_FIELDS = {"schema_version", "sha256"}
PACKAGE_RECEIPT_FIELDS = {
    "schema_version",
    "valid",
    "package_id",
    "revision",
    "profile",
    "terminal_verdict",
    "manifest_sha256",
    "owned_files",
}
STATE_FIELDS = {
    "schema_version",
    "package_id",
    "task_root",
    "run_root",
    "status",
    "revision",
    "entry_mode",
    "approval_context",
    "approval_authorization_path",
    "approval_authorization_sha256",
    "implementation_approval_status",
    "implementation_authorization_request_path",
    "implementation_authorization_request_sha256",
    "implementation_authorization_path",
    "implementation_authorization_sha256",
    "profile",
    "started_at_utc",
    "deadline_at_utc",
    "cap_reason",
    "cap_reached_at_utc",
    "cap_stage",
    "cap_completed_verification_iteration",
    "charter",
    "charter_sha256",
    "requirements",
    "requirements_sha256",
    "evidence_index_sha256",
    "lens_contract_id",
    "lens_contract_path",
    "lens_contract_sha256",
    "supplied_input_root",
    "source_snapshots",
    "plan_sha256",
    "surface_map_sha256",
    "decisions_sha256",
    "verification_ledger_sha256",
    "budgets",
    "revision_history",
    "emission_history",
    "attempts",
    "stage_results",
    "findings",
    "dispositions",
    "finding_transitions",
    "blockers",
}
COMMANDS = {
    "hash-json",
    "migrate-run-root",
    "init",
    "prepare-resume-bundle",
    "resume",
    "scope-check",
    "record-draft",
    "prepare-attempt",
    "finalize-attempt",
    "escalate-profile",
    "record-runtime-blocker",
    "materialize-artifact",
    "record-stage",
    "record-findings",
    "record-verification-ledger",
    "render-verify-summary",
    "prepare-continuation-approval",
    "continue-hardening",
    "prepare-revision",
    "record-revision",
    "emit-package",
    "validate-package",
    "prepare-implementation-authorization",
    "record-implementation-authorization",
    "validate-implementation-authorization",
    "stage-result",
    "show",
}


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_json(path: Path, value: object) -> Path:
    path.write_bytes(canonical_bytes(value))
    return path


def run_controller(*args: object, ok: bool | None = True) -> tuple[subprocess.CompletedProcess[str], dict]:
    result = subprocess.run(
        ["python3", str(CONTROLLER), *(str(arg) for arg in args)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if ok is True:
        assert result.returncode == 0, result.stderr or result.stdout
    elif ok is False:
        assert result.returncode != 0, result.stdout
    assert result.stdout.strip(), result.stderr
    payload = json.loads(result.stdout)
    assert isinstance(payload, dict)
    return result, payload


def requirement() -> dict:
    return {
        "id": "R1",
        "text": "Ground one local implementation boundary.",
        "source": "task-intake:R1",
        "operational_maturity": "CURRENT_RUNTIME",
        "evidence_availability": "AVAILABLE",
        "acceptance_intent": "The implementation and verification anchors are explicit.",
        "scope_id": "fixture-scope",
        "research_value_type": "string",
        "research_value": "The fixture source is authoritative.",
        "evidence_ids": ["E1"],
        "planner_obligations": [
            {
                "id": "P1",
                "description": "Plan the grounded local change.",
                "status": "READY",
                "implementation_anchors": ["Change the fixture-owned source boundary."],
                "verification_anchors": ["Run the fixture-owned focused test."],
                "required_inputs": [],
                "owner": "implementation owner",
                "closure_condition": "The focused test passes.",
                "evidence_ids": ["E1"],
            }
        ],
    }


def test_research_requirement_preserves_validated_source_evidence_order() -> None:
    value = requirement()
    value["evidence_ids"] = ["E1", "E4", "E10", "E14"]

    assert PLAN_PACKAGE.validate_requirements([value], direct=False) == [value]

    with pytest.raises(PLAN_PACKAGE.PlanPackageError, match="sorted and unique"):
        PLAN_PACKAGE.validate_requirements([value], direct=True)

    value["evidence_ids"].append("E4")
    with pytest.raises(
        PLAN_PACKAGE.PlanPackageError,
        match="research requirement evidence_ids must be unique",
    ):
        PLAN_PACKAGE.validate_requirements([value], direct=False)


def behavior_matrix() -> dict:
    return {
        "input_states": [
            {
                "id": "I-valid",
                "category": "valid",
                "description": "The authoritative fixture input is valid.",
                "requirement_ids": ["R1"],
                "obligation_ids": ["P1"],
                "evidence_ids": ["E1"],
            }
        ],
        "category_exclusions": [
            {
                "category": category,
                "reason": f"The fixture contract proves {category} is not applicable.",
                "evidence_ids": ["E1"],
            }
            for category in ("empty", "error", "malformed_success", "mixed", "boundary")
        ],
        "consumers": [
            {
                "id": "C-boundary",
                "kind": "boundary",
                "description": "The fixture-owned source boundary consumes the input.",
                "surface_item_ids": ["S1"],
            }
        ],
        "cases": [
            {
                "id": "TC-valid-boundary",
                "input_state_id": "I-valid",
                "consumer_id": "C-boundary",
                "expected_observable": "The fixture boundary is updated.",
                "test_command": "python3 -m pytest -q tests/test_fixture.py",
                "test_assertion": "The focused fixture assertion passes.",
            }
        ],
    }


def validate_behavior_matrix(matrix: dict, *, planned_ids: set[str] | None = None) -> None:
    PLAN_PACKAGE.validate_behavior_matrix(
        matrix,
        planned_ids={"S1"} if planned_ids is None else planned_ids,
        requirement_ids={"R1"},
        obligation_ids={"P1"},
        evidence_ids={"E1"},
    )


def test_behavior_matrix_requires_every_input_category_disposition() -> None:
    matrix = behavior_matrix()
    matrix["category_exclusions"] = [
        row for row in matrix["category_exclusions"]
        if row["category"] != "malformed_success"
    ]

    with pytest.raises(PLAN_PACKAGE.PlanPackageError) as exc:
        validate_behavior_matrix(matrix)

    assert exc.value.code == "INVALID_BEHAVIOR_MATRIX"


def test_behavior_matrix_requires_complete_state_consumer_cross_product() -> None:
    matrix = behavior_matrix()
    matrix["consumers"].append(
        {
            "id": "C-rendering",
            "kind": "rendering",
            "description": "A rendered output also consumes the valid state.",
            "surface_item_ids": ["S1"],
        }
    )

    with pytest.raises(PLAN_PACKAGE.PlanPackageError) as exc:
        validate_behavior_matrix(matrix)

    assert exc.value.code == "INVALID_BEHAVIOR_MATRIX"


def test_behavior_matrix_rejects_duplicate_state_consumer_case() -> None:
    matrix = behavior_matrix()
    duplicate = dict(matrix["cases"][0], id="TC-valid-boundary-duplicate")
    matrix["cases"].append(duplicate)

    with pytest.raises(PLAN_PACKAGE.PlanPackageError) as exc:
        validate_behavior_matrix(matrix)

    assert exc.value.code == "INVALID_BEHAVIOR_MATRIX"


def test_behavior_matrix_requires_every_planned_surface_consumer() -> None:
    with pytest.raises(PLAN_PACKAGE.PlanPackageError) as exc:
        validate_behavior_matrix(behavior_matrix(), planned_ids={"S1", "S2"})

    assert exc.value.code == "INVALID_BEHAVIOR_MATRIX"


def test_behavior_matrix_exclusions_require_authoritative_evidence() -> None:
    matrix = behavior_matrix()
    matrix["category_exclusions"][0]["evidence_ids"] = ["E-unknown"]

    with pytest.raises(PLAN_PACKAGE.PlanPackageError) as exc:
        validate_behavior_matrix(matrix)

    assert exc.value.code == "INVALID_BEHAVIOR_MATRIX"


def direct_workspace(tmp_path: Path, *, task_size: str = "light") -> dict:
    repository = tmp_path / "repository"
    repository.mkdir(parents=True)
    source = repository / "source.txt"
    source.write_text("authoritative fixture\n", encoding="utf-8")
    task_root = repository / "Tasks" / "planner-v2-fixture"
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
    charter_path = write_json(tmp_path / "charter.json", charter)
    requirements_path = write_json(tmp_path / "requirements.json", [requirement()])
    evidence_path = write_json(tmp_path / "evidence-index.json", evidence)
    state_path = task_root / ".plan-playbook" / "state.json"
    return {
        "repository": repository,
        "source": source,
        "task_root": task_root,
        "state": state_path,
        "charter": charter,
        "charter_path": charter_path,
        "requirements_path": requirements_path,
        "evidence_path": evidence_path,
        "task_size": task_size,
    }


def init_direct(workspace: dict) -> dict:
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
        workspace["task_size"],
        "--approval-context",
        "ORDINARY",
        "--requirements",
        workspace["requirements_path"],
        "--evidence-index",
        workspace["evidence_path"],
    )
    assert set(payload) == SUCCESS_FIELDS
    assert payload["ok"] is True
    assert payload["command"] == "init"
    return json.loads(workspace["state"].read_text(encoding="utf-8"))


def move_to_legacy_run_root(workspace: dict) -> Path:
    state = json.loads(workspace["state"].read_text(encoding="utf-8"))
    canonical_root = Path(state["run_root"])
    legacy_root = workspace["task_root"] / ".plan-playbook-v2"
    canonical_root.rename(legacy_root)
    state["run_root"] = str(legacy_root.resolve())
    write_json(legacy_root / "state.json", state)
    workspace["state"] = legacy_root / "state.json"
    return legacy_root


def drafted_workspace(tmp_path: Path) -> tuple[dict, dict]:
    workspace = direct_workspace(tmp_path)
    state = init_direct(workspace)
    run_root = Path(state["run_root"])

    artifacts = {
        "plan": ("md", b"# Plan\n\nGrounded fixture plan.\n"),
        "surface-map": ("json", canonical_bytes({"schema_version": 1})),
        "decisions": ("json", canonical_bytes({"schema_version": 1})),
        "verification-ledger": ("json", canonical_bytes({"kind": "plan"})),
    }
    references = {}
    for kind, (suffix, payload) in artifacts.items():
        digest = sha256_bytes(payload)
        relative = f"snapshots/{kind}/{digest}.{suffix}"
        target = run_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        references[kind] = {"path": relative, "sha256": digest}

    source_records = [{"path": "source.txt", "sha256": sha256_bytes(workspace["source"].read_bytes())}]
    source_tree_sha256 = sha256_bytes(canonical_bytes(source_records))
    manifest = {
        "schema_version": 1,
        "contract_id": "ASSESSMENT_SOURCE_SNAPSHOT_V1",
        "files": source_records,
    }
    manifest_sha256 = sha256_bytes(canonical_bytes(manifest))
    snapshot_relative = f"source-snapshots/{manifest_sha256}"
    snapshot_root = run_root / snapshot_relative
    snapshot_tree = snapshot_root / "tree"
    snapshot_tree.mkdir(parents=True)
    (snapshot_tree / "source.txt").write_bytes(workspace["source"].read_bytes())
    manifest_path = snapshot_root / "manifest.json"
    manifest_path.write_bytes(canonical_bytes(manifest))
    source_snapshot = {
        "repository_key": "fixture",
        "source_path": str(workspace["repository"].resolve()),
        "source_tree_sha256": source_tree_sha256,
        "snapshot_path": f"{snapshot_relative}/tree",
        "snapshot_tree_sha256": source_tree_sha256,
        "manifest_path": f"{snapshot_relative}/manifest.json",
        "manifest_sha256": manifest_sha256,
        "created_at_utc": "2026-07-19T00:00:00Z",
    }

    revision_basis = {
        "schema_version": 1,
        "package_id": state["package_id"],
        "revision": 1,
        "profile": state["profile"],
        "evidence_index_sha256": state["evidence_index_sha256"],
        "plan_sha256": references["plan"]["sha256"],
        "surface_map_sha256": references["surface-map"]["sha256"],
        "decisions_sha256": references["decisions"]["sha256"],
        "verification_ledger_sha256": references["verification-ledger"]["sha256"],
    }
    revision_receipt = {
        **revision_basis,
        "plan_snapshot_path": references["plan"]["path"],
        "revision_basis_sha256": sha256_bytes(canonical_bytes(revision_basis)),
        "predecessor_receipt_sha256": None,
        "published_at_utc": "2026-07-19T00:00:00Z",
    }
    revision_receipt_bytes = canonical_bytes(revision_receipt)
    revision_receipt_sha = sha256_bytes(revision_receipt_bytes)
    revision_receipt_relative = f"revisions/1-{revision_receipt_sha}.json"
    revision_receipt_path = run_root / revision_receipt_relative
    revision_receipt_path.parent.mkdir(parents=True)
    revision_receipt_path.write_bytes(revision_receipt_bytes)

    state.update(
        status="DRAFTED",
        revision=1,
        plan_sha256=references["plan"]["sha256"],
        surface_map_sha256=references["surface-map"]["sha256"],
        decisions_sha256=references["decisions"]["sha256"],
        verification_ledger_sha256=references["verification-ledger"]["sha256"],
        source_snapshots=[source_snapshot],
        revision_history=[
            {
                "revision": 1,
                "receipt_path": revision_receipt_relative,
                "receipt_sha256": revision_receipt_sha,
            }
        ],
    )
    workspace["state"].write_bytes(canonical_bytes(state))
    workspace["references"] = references
    workspace["source_snapshot"] = source_snapshot
    return workspace, state


def role_input(state: dict, workspace: dict, role: str) -> dict:
    verify_role = role.startswith("VERIFY_PLAN")
    assignments = ["P1"] if verify_role else []
    lens_contract = None
    if not verify_role:
        lens_contract = {
            "id": state["lens_contract_id"],
            "path": state["lens_contract_path"],
            "sha256": state["lens_contract_sha256"],
            "lens": role,
        }
    source = dict(workspace["source_snapshot"])
    source.pop("created_at_utc")
    return {
        "schema_version": 1,
        "role": role,
        "round": 1,
        "verification_iteration": 1,
        "assigned_coverage_ids": ["C01"] if verify_role else [],
        "assigned_obligation_ids": assignments,
        "lens_contract": lens_contract,
        "objective": state["charter"]["objective"],
        "charter": {
            "path": f"snapshots/charter/{state['charter_sha256']}.json",
            "sha256": state["charter_sha256"],
        },
        "requirements": {
            "path": f"snapshots/requirements/{state['requirements_sha256']}.json",
            "sha256": state["requirements_sha256"],
        },
        "plan": workspace["references"]["plan"],
        "evidence_index": {
            "path": f"snapshots/evidence-index/{state['evidence_index_sha256']}.json",
            "sha256": state["evidence_index_sha256"],
        },
        "surface_map": workspace["references"]["surface-map"],
        "verification_ledger": workspace["references"]["verification-ledger"] if verify_role else None,
        "raw_findings": None,
        "verifier_obligation_assessments": None,
        "authoritative_roots": [source],
    }


def slot_ledger(path: Path, *, state: str, agent_id: str | None) -> Path:
    timestamps = {
        "acquired_at": 1,
        "bound_at": 2 if agent_id else None,
        "completed_at": 3 if state == "released" else None,
        "closed_at": 4 if state == "released" else None,
        "abandoned_at": None,
        "released_at": 5 if state == "released" else None,
    }
    return write_json(
        path,
        {
            "version": 2,
            "max": 1,
            "next_slot_sequence": 2,
            "slots": [{
                "id": "s1",
                "label": "planner-v2-test",
                "state": state,
                "agent_id": agent_id,
                **timestamps,
                "evidence": {
                    "close": "wait returned terminal" if state == "released" else None,
                    "abandon_reason": None,
                },
            }],
        },
    )


def prepare_attempt(tmp_path: Path, workspace: dict, state: dict, role: str) -> tuple[Path, dict]:
    envelope_path = write_json(tmp_path / "role-input.json", role_input(state, workspace, role))
    ledger_path = slot_ledger(tmp_path / "slots.json", state="reserved", agent_id=None)
    token_path = tmp_path / "attempt-token.json"
    args = [
        "prepare-attempt", workspace["state"], "--round", 1, "--role", role,
        "--verification-iteration", 1,
    ]
    if role.startswith("VERIFY_PLAN"):
        args.extend(["--assigned-coverage-id", "C01", "--assigned-obligation-id", "P1"])
    args.extend([
        "--slot-id", "s1", "--slot-ledger", ledger_path,
        "--input-envelope", envelope_path, "--out", token_path,
    ])
    run_controller(*args)
    return token_path, json.loads(token_path.read_text(encoding="utf-8"))


def role_output(state: dict, token: dict, role: str, *, verdict: str | None = None) -> dict:
    report = f"# {role} report\n"
    finding = None
    disposition = None
    if verdict == "GAPS":
        evidence = [{
            "kind": "SOURCE",
            "repository_key": "fixture",
            "path": "source.txt",
            "line": 1,
            "claim": "The current boundary remains incomplete.",
        }]
        fingerprint_basis = {
            "stage": role,
            "requirement_ids": ["R1"],
            "obligation_ids": ["P1"],
            "coverage_ids": [],
            "practical_consequence": "The plan cannot yet be implemented reliably.",
            "evidence": evidence,
        }
        finding = {
            "id": "PPV2-F1",
            "fingerprint": sha256_bytes(canonical_bytes(fingerprint_basis)),
            "round": 1,
            "stage": role,
            "source_role": role,
            "requirement_ids": ["R1"],
            "obligation_ids": ["P1"],
            "coverage_ids": [],
            "practical_consequence": fingerprint_basis["practical_consequence"],
            "evidence": evidence,
            "source_classification": "ACTIONABLE",
        }
        disposition = {
            "finding_id": finding["id"],
            "finding_fingerprint": finding["fingerprint"],
            "decision": "FIX NOW",
            "rationale": "The implementation boundary must be explicit.",
            "parent_action": "Revise the plan.",
            "new_finding_classification": None,
        }
    terminal_envelope = None
    if verdict is not None:
        blocker = {
            "id": "PPV2-B1",
            "type": "RUNTIME",
            "practical_impact": "The assessment cannot complete.",
            "evidence": ["fixture:runtime-unavailable"],
            "required_resolution": "Restore the assessment runtime.",
        }
        terminal_envelope = {
            "stage": "plan-requirements-satisfaction",
            "iteration": 1,
            "attempt": 1,
            "assigned_requirement_ids": ["R1"],
            "assigned_gap_ids": [],
            "owned_blocker_ids": [blocker["id"]] if verdict == "BLOCKED" else [],
            "verdict": verdict,
            "open_gap_ids": [finding["id"]] if finding else [],
            "closed_gap_ids": [],
            "new_gaps": [finding] if finding else [],
            "new_blockers": [blocker] if verdict == "BLOCKED" else [],
            "record_transitions": [],
            "evidence": ["fixture:role-output"],
            "artifact_paths": [],
        }
    return {
        "schema_version": 1,
        "attempt_id": token["attempt_id"],
        "input_envelope_sha256": token["input_envelope_sha256"],
        "role": role,
        "round": 1,
        "verification_iteration": 1,
        "assigned_coverage_ids": ["C01"] if role.startswith("VERIFY_PLAN") else [],
        "assigned_obligation_ids": ["P1"] if role.startswith("VERIFY_PLAN") else [],
        "lens_contract_id": None if role.startswith("VERIFY_PLAN") else state["lens_contract_id"],
        "lens_contract_sha256": None if role.startswith("VERIFY_PLAN") else state["lens_contract_sha256"],
        "assessed_plan_sha256": state["plan_sha256"],
        "terminal_envelope": terminal_envelope,
        "findings": [finding] if finding else [],
        "dispositions": None if role == "VERIFY_PLAN_VERIFIER" else ([disposition] if disposition else []),
        "obligation_assessments": [{"obligation_id": "P1", "status": "SUPPORTED"}] if role == "VERIFY_PLAN_VERIFIER" else [],
        "inventory_approval": None,
        "assessment_approvals": None,
        "coverage_exclusion_approvals": None,
        "artifact_transfer": {
            "form": "INLINE",
            "target_path": None,
            "content_markdown": report,
            "sha256": sha256_bytes(report.encode("utf-8")),
        },
        "completed_at_utc": "2026-07-19T00:00:00Z",
    }


def assert_rejected_without_mutation(workspace: dict, *args: object) -> dict:
    before = workspace["state"].read_bytes()
    _result, payload = run_controller(*args, ok=False)
    assert set(payload) == SUCCESS_FIELDS
    assert payload["ok"] is False
    assert isinstance(payload["code"], str) and payload["code"]
    assert workspace["state"].read_bytes() == before
    assert payload["state_sha256"] == sha256_bytes(before)
    return payload


def test_cli_exposes_only_the_frozen_controller_commands() -> None:
    result = subprocess.run(
        ["python3", str(CONTROLLER), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    command_line = next(line for line in result.stdout.splitlines() if "{" in line and "}" in line)
    exposed = set(command_line.split("{", 1)[1].split("}", 1)[0].split(","))
    assert exposed == COMMANDS


def test_hash_json_uses_canonical_ascii_json_and_exact_output(tmp_path: Path) -> None:
    value = {"unicode": "\u03a9", "nested": {"z": None, "a": True}, "items": [2, 1]}
    source = tmp_path / "unordered.json"
    source.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")

    _result, payload = run_controller("hash-json", source)

    assert set(payload) == HASH_FIELDS
    assert payload == {"schema_version": 1, "sha256": sha256_bytes(canonical_bytes(value))}


@pytest.mark.parametrize(
    ("task_size", "profile", "max_rounds", "max_attempts", "max_elapsed"),
    [
        ("light", "LIGHT", 3, 10, 20 * 60),
        ("standard", "SUBSTANTIAL", 3, 23, 60 * 60),
        ("heavy", "SUBSTANTIAL", 3, 23, 60 * 60),
    ],
)
def test_init_freezes_exact_state_profile_and_budget(
    tmp_path: Path,
    task_size: str,
    profile: str,
    max_rounds: int,
    max_attempts: int,
    max_elapsed: int,
) -> None:
    workspace = direct_workspace(tmp_path, task_size=task_size)
    state = init_direct(workspace)

    charter_hash = sha256_bytes(canonical_bytes(workspace["charter"]))
    identity = {
        "schema_version": 1,
        "task_root": str(workspace["task_root"].resolve()),
        "charter_sha256": charter_hash,
    }
    assert set(state) == STATE_FIELDS
    assert state["package_id"] == f"plan-package-{sha256_bytes(canonical_bytes(identity))[:24]}"
    assert state["task_root"] == str(workspace["task_root"].resolve())
    assert state["run_root"] == str((workspace["task_root"] / ".plan-playbook").resolve())
    assert state["status"] == "INITIALIZED"
    assert state["revision"] == 0
    assert state["entry_mode"] == "DIRECT"
    assert state["approval_context"] == "ORDINARY"
    assert state["profile"] == profile
    assert state["charter"] == workspace["charter"]
    assert state["charter_sha256"] == charter_hash
    assert state["lens_contract_id"] == "PLAN_PLAYBOOK_V2_HARDENING_LENSES_V1"
    assert state["lens_contract_path"] == (
        f"snapshots/hardening-lenses/{state['lens_contract_sha256']}.md"
    )
    assert state["budgets"] == {
        "max_rounds": max_rounds,
        "max_agent_attempts": max_attempts,
        "used_agent_attempts": 0,
        "max_elapsed_seconds": max_elapsed,
        "reserved_later_stage_attempts": 3,
        "verify_plan_iteration_limit": 10,
        "continuation_approval_sha256": None,
    }
    for name in (
        "source_snapshots",
        "revision_history",
        "emission_history",
        "attempts",
        "stage_results",
        "findings",
        "dispositions",
        "finding_transitions",
        "blockers",
    ):
        assert state[name] == []
    for name in (
        "cap_reason",
        "cap_reached_at_utc",
        "cap_stage",
        "cap_completed_verification_iteration",
        "plan_sha256",
        "surface_map_sha256",
        "decisions_sha256",
        "verification_ledger_sha256",
    ):
        assert state[name] is None
    assert workspace["state"].read_bytes() == canonical_bytes(state)


def test_init_replay_and_show_are_byte_identical(tmp_path: Path) -> None:
    workspace = direct_workspace(tmp_path)
    first = init_direct(workspace)
    first_bytes = workspace["state"].read_bytes()

    replay = init_direct(workspace)
    _result, shown = run_controller("show", workspace["state"])

    assert replay == first
    assert workspace["state"].read_bytes() == first_bytes
    assert shown == first
    assert canonical_bytes(shown) == first_bytes


def test_migrate_run_root_moves_quiescent_legacy_state_once(tmp_path: Path) -> None:
    workspace = direct_workspace(tmp_path)
    init_direct(workspace)
    legacy_root = move_to_legacy_run_root(workspace)

    _result, migrated = run_controller(
        "migrate-run-root", "--task-directory", workspace["task_root"]
    )
    canonical_state = workspace["task_root"] / ".plan-playbook/state.json"
    persisted = json.loads(canonical_state.read_text(encoding="utf-8"))

    assert migrated["code"] == "RUN_ROOT_MIGRATED"
    assert not legacy_root.exists()
    assert persisted["run_root"] == str(canonical_state.parent.resolve())
    assert not (workspace["task_root"] / ".plan-playbook-migration.json").exists()
    _result, replay = run_controller(
        "migrate-run-root", "--task-directory", workspace["task_root"]
    )
    assert replay["code"] == "ALREADY_MIGRATED"


def test_migrate_run_root_rejects_state_hash_bound_blocked_run(tmp_path: Path) -> None:
    workspace = direct_workspace(tmp_path)
    state = init_direct(workspace)
    state["status"] = "BLOCKED"
    state["blockers"] = [
        {
            "id": "B1",
            "type": "EVIDENCE",
            "practical_impact": "Planning cannot continue.",
            "evidence": ["fixture:missing-evidence"],
            "required_resolution": "Supply grounded evidence.",
            "status": "OPEN",
            "resolution": None,
        }
    ]
    write_json(workspace["state"], state)
    legacy_root = move_to_legacy_run_root(workspace)
    before = (legacy_root / "state.json").read_bytes()

    _result, rejected = run_controller(
        "migrate-run-root",
        "--task-directory",
        workspace["task_root"],
        ok=False,
    )

    assert rejected["code"] == "MIGRATION_STATE_HASH_BOUND"
    assert (legacy_root / "state.json").read_bytes() == before
    assert not (workspace["task_root"] / ".plan-playbook").exists()


def test_migrate_run_root_rejects_dual_roots(tmp_path: Path) -> None:
    workspace = direct_workspace(tmp_path)
    init_direct(workspace)
    move_to_legacy_run_root(workspace)
    (workspace["task_root"] / ".plan-playbook").mkdir()

    _result, rejected = run_controller(
        "migrate-run-root",
        "--task-directory",
        workspace["task_root"],
        ok=False,
    )

    assert rejected["code"] == "MIGRATION_CONFLICT"


def test_init_snapshots_authorities_before_state_and_ignores_mutable_callers(tmp_path: Path) -> None:
    workspace = direct_workspace(tmp_path)
    state = init_direct(workspace)
    original_state = workspace["state"].read_bytes()
    run_root = Path(state["run_root"])

    assert (run_root / f"snapshots/charter/{state['charter_sha256']}.json").is_file()
    assert (run_root / f"snapshots/requirements/{state['requirements_sha256']}.json").is_file()
    assert (run_root / f"snapshots/evidence-index/{state['evidence_index_sha256']}.json").is_file()

    workspace["charter_path"].write_text("{}", encoding="utf-8")
    workspace["requirements_path"].write_text("[]", encoding="utf-8")
    workspace["evidence_path"].write_text("[]", encoding="utf-8")
    _result, shown = run_controller("show", workspace["state"])
    assert canonical_bytes(shown) == original_state


def test_init_rejects_wrong_state_path_unknown_fields_and_symlink_roots(tmp_path: Path) -> None:
    workspace = direct_workspace(tmp_path / "wrong-state")
    wrong_state = workspace["task_root"] / "state.json"
    _result, payload = run_controller(
        "init",
        wrong_state,
        "--task-directory",
        workspace["task_root"],
        "--charter",
        workspace["charter_path"],
        "--entry-mode",
        "DIRECT",
        "--task-size",
        "light",
        "--approval-context",
        "ORDINARY",
        "--requirements",
        workspace["requirements_path"],
        "--evidence-index",
        workspace["evidence_path"],
        ok=False,
    )
    assert set(payload) == SUCCESS_FIELDS
    assert payload["state_sha256"] is None
    assert not wrong_state.exists()

    workspace = direct_workspace(tmp_path / "unknown")
    charter = json.loads(workspace["charter_path"].read_text(encoding="utf-8"))
    charter["alternate_scope"] = []
    write_json(workspace["charter_path"], charter)
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
        "ORDINARY",
        "--requirements",
        workspace["requirements_path"],
        "--evidence-index",
        workspace["evidence_path"],
        ok=False,
    )
    assert set(payload) == SUCCESS_FIELDS
    assert payload["state_sha256"] is None

    real = tmp_path / "real-task"
    real.mkdir()
    linked = tmp_path / "linked-task"
    linked.symlink_to(real, target_is_directory=True)
    _result, payload = run_controller(
        "init",
        linked / ".plan-playbook/state.json",
        "--task-directory",
        linked,
        "--charter",
        workspace["charter_path"],
        "--entry-mode",
        "RESEARCH_PACKAGE",
        "--task-size",
        "light",
        "--approval-context",
        "ORDINARY",
        ok=False,
    )
    assert set(payload) == SUCCESS_FIELDS
    assert payload["state_sha256"] is None


def test_scope_change_and_illegal_lifecycle_commands_fail_without_mutation(tmp_path: Path) -> None:
    workspace = direct_workspace(tmp_path)
    init_direct(workspace)
    changed = dict(workspace["charter"])
    changed["objective"] = "A different objective."
    changed_path = write_json(tmp_path / "changed-charter.json", changed)

    scope = assert_rejected_without_mutation(
        workspace,
        "scope-check",
        workspace["state"],
        "--charter",
        changed_path,
        "--requirements",
        workspace["requirements_path"],
        "--evidence-index",
        workspace["evidence_path"],
    )
    assert scope["status"] == "BLOCKED"
    assert scope["code"] == "SCOPE_CHANGED"

    assert_rejected_without_mutation(
        workspace, "emit-package", workspace["state"], workspace["task_root"]
    )
    assert_rejected_without_mutation(
        workspace,
        "prepare-implementation-authorization",
        workspace["state"],
        "--out",
        tmp_path / "request.json",
    )
    assert_rejected_without_mutation(
        workspace,
        "prepare-revision",
        workspace["state"],
        "--evidence-index",
        workspace["evidence_path"],
    )


def test_attempt_preparation_is_pre_spawn_budgeted_and_fail_closed(tmp_path: Path) -> None:
    workspace = direct_workspace(tmp_path)
    state = init_direct(workspace)
    token = tmp_path / "attempt-token.json"
    input_envelope = write_json(tmp_path / "input.json", {"schema_version": 1})
    slot_ledger = write_json(
        tmp_path / "slots.json",
        {
            "schema_version": 2,
            "max": 1,
            "next_slot_sequence": 2,
            "slots": [
                {
                    "id": "s1",
                    "label": "verify-plan",
                    "state": "reserved",
                    "agent_id": None,
                    "acquired_at": 1,
                    "bound_at": None,
                    "completed_at": None,
                    "closed_at": None,
                    "abandoned_at": None,
                    "released_at": None,
                    "evidence": {"close": None, "abandon_reason": None},
                }
            ],
        },
    )

    payload = assert_rejected_without_mutation(
        workspace,
        "prepare-attempt",
        workspace["state"],
        "--round",
        1,
        "--role",
        "VERIFY_PLAN_VERIFIER",
        "--verification-iteration",
        1,
        "--assigned-obligation-id",
        "P1",
        "--slot-id",
        "s1",
        "--slot-ledger",
        slot_ledger,
        "--input-envelope",
        input_envelope,
        "--out",
        token,
    )
    assert payload["status"] == "INITIALIZED"
    assert json.loads(workspace["state"].read_text())["budgets"] == state["budgets"]
    assert not token.exists()


def test_stage_order_and_same_plan_identity_fail_closed_before_draft(tmp_path: Path) -> None:
    workspace = direct_workspace(tmp_path)
    init_direct(workspace)
    for stage in (
        "VERIFY_PLAN",
        "INTERNAL_READINESS",
        "REQUIREMENTS_COVERAGE",
        "REQUIREMENTS_SATISFACTION",
    ):
        payload = assert_rejected_without_mutation(
            workspace,
            "record-stage",
            workspace["state"],
            "--round",
            1,
            "--stage",
            stage,
        )
        assert payload["status"] == "INITIALIZED"


def test_research_entry_blocks_without_package_and_resume_rejects_unowned_bundle(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    task_root = repository / "Tasks" / "research-entry"
    task_root.mkdir(parents=True)
    charter = {
        "schema_version": 1,
        "objective": "Resume from a validated research package.",
        "allowed_repositories": {"fixture": str(repository.resolve())},
        "allowed_paths": [{"repository_key": "fixture", "path": "."}],
        "supplied_input_root": None,
        "exclusions": [],
        "deliverables": ["A validated plan package."],
        "approval_boundaries": ["Implementation requires authorization."],
        "change_characteristics": ["NONE"],
    }
    charter_path = write_json(tmp_path / "research-charter.json", charter)
    state_path = task_root / ".plan-playbook/state.json"
    _result, payload = run_controller(
        "init",
        state_path,
        "--task-directory",
        task_root,
        "--charter",
        charter_path,
        "--entry-mode",
        "RESEARCH_PACKAGE",
        "--task-size",
        "light",
        "--approval-context",
        "ORDINARY",
    )
    assert set(payload) == SUCCESS_FIELDS
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["status"] == "BLOCKED"
    assert state["requirements"] is None
    assert state["requirements_sha256"] is None
    assert state["evidence_index_sha256"] is None
    assert state["plan_sha256"] is None
    assert len(state["blockers"]) == 1
    blocker = state["blockers"][0]
    assert set(blocker) == {
        "id",
        "type",
        "practical_impact",
        "evidence",
        "required_resolution",
        "status",
        "resolution",
    }
    assert blocker["type"] == "EVIDENCE"
    assert blocker["status"] == "OPEN"
    assert blocker["resolution"] is None

    rejected = assert_rejected_without_mutation(
        {"state": state_path},
        "record-draft",
        state_path,
        "--plan",
        tmp_path / "blocked-plan.md",
        "--surface-map",
        tmp_path / "blocked-surface-map.json",
        "--decisions",
        tmp_path / "blocked-decisions.json",
        "--verification-ledger",
        tmp_path / "blocked-verification-ledger.json",
    )
    assert rejected["code"] == "INVALID_TRANSITION"

    fake_bundle = tmp_path / "foreign-bundle"
    fake_bundle.mkdir()
    write_json(fake_bundle / "receipt.json", {"schema_version": 1})
    before = state_path.read_bytes()
    _result, rejected = run_controller(
        "resume", state_path, "--resume-bundle", fake_bundle, ok=False
    )
    assert set(rejected) == SUCCESS_FIELDS
    assert state_path.read_bytes() == before


def test_state_tamper_and_unknown_state_fields_are_rejected(tmp_path: Path) -> None:
    workspace = direct_workspace(tmp_path)
    init_direct(workspace)
    state = json.loads(workspace["state"].read_text(encoding="utf-8"))
    state["budgets"]["used_agent_attempts"] = 1
    workspace["state"].write_bytes(canonical_bytes(state))
    _result, payload = run_controller("show", workspace["state"], ok=False)
    assert set(payload) == SUCCESS_FIELDS
    assert payload["ok"] is False

    state["unexpected"] = True
    workspace["state"].write_bytes(canonical_bytes(state))
    _result, payload = run_controller("show", workspace["state"], ok=False)
    assert set(payload) == SUCCESS_FIELDS
    assert payload["ok"] is False


def test_validate_package_rejects_empty_partial_and_symlink_packages(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    _result, payload = run_controller("validate-package", empty, ok=False)
    assert set(payload) == SUCCESS_FIELDS
    assert payload["ok"] is False

    partial = tmp_path / "partial"
    partial.mkdir()
    (partial / "plan.md").write_text("# partial\n", encoding="utf-8")
    _result, payload = run_controller("validate-package", partial, ok=False)
    assert set(payload) == SUCCESS_FIELDS
    assert payload["ok"] is False

    target = tmp_path / "target"
    target.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(target, target_is_directory=True)
    _result, payload = run_controller("validate-package", linked, ok=False)
    assert set(payload) == SUCCESS_FIELDS
    assert payload["ok"] is False


def test_ordinary_approval_requires_emitted_package_and_exact_raw_response(tmp_path: Path) -> None:
    workspace = direct_workspace(tmp_path)
    init_direct(workspace)
    request = write_json(tmp_path / "request.json", {"schema_version": 1})
    response = tmp_path / "response.txt"
    response.write_text("APPROVE IMPLEMENTATION " + "a" * 64, encoding="utf-8")

    payload = assert_rejected_without_mutation(
        workspace,
        "record-implementation-authorization",
        workspace["state"],
        "--request",
        request,
        "--approval-response",
        response,
    )
    assert payload["status"] == "INITIALIZED"


def test_convergence_only_arguments_are_exclusive_in_ordinary_mode(tmp_path: Path) -> None:
    workspace = direct_workspace(tmp_path)
    outer_state = write_json(
        tmp_path / "outer.json",
        {"schema_version": 1, "status": "plan", "objective": workspace["charter"]["objective"]},
    )
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
        "ORDINARY",
        "--convergence-state",
        outer_state,
        "--requirements",
        workspace["requirements_path"],
        "--evidence-index",
        workspace["evidence_path"],
        ok=False,
    )
    assert set(payload) == SUCCESS_FIELDS
    assert payload["state_sha256"] is None
    assert not workspace["state"].exists()


def test_every_rejection_is_json_only_with_stable_nonempty_code(tmp_path: Path) -> None:
    missing = tmp_path / "missing-state.json"
    first, first_payload = run_controller("show", missing, ok=False)
    second, second_payload = run_controller("show", missing, ok=False)

    assert first.stderr == ""
    assert second.stderr == ""
    assert set(first_payload) == SUCCESS_FIELDS
    assert set(second_payload) == SUCCESS_FIELDS
    assert first_payload == second_payload
    assert first_payload["ok"] is False
    assert first_payload["state_sha256"] is None
    assert isinstance(first_payload["code"], str) and first_payload["code"]


@pytest.mark.parametrize("fault", ["unknown-field", "mismatched-role", "verifier-terminal-claim"])
def test_succeeded_finalize_rejects_noncanonical_role_outputs(
    tmp_path: Path, fault: str
) -> None:
    workspace, state = drafted_workspace(tmp_path)
    token_path, token = prepare_attempt(
        tmp_path, workspace, state, "VERIFY_PLAN_VERIFIER"
    )
    slot_path = slot_ledger(
        tmp_path / "slots.json", state="released", agent_id="agent-verifier-1"
    )
    output = role_output(state, token, "VERIFY_PLAN_VERIFIER")
    if fault == "unknown-field":
        output["alternate_verdict"] = "PASS"
    elif fault == "mismatched-role":
        output["role"] = "INTERNAL_READINESS"
    else:
        output["terminal_envelope"] = {
            "stage": "plan-verify",
            "iteration": 1,
            "attempt": 1,
            "assigned_requirement_ids": ["R1"],
            "assigned_gap_ids": [],
            "owned_blocker_ids": [],
            "verdict": "PASS",
            "open_gap_ids": [],
            "closed_gap_ids": [],
            "new_gaps": [],
            "new_blockers": [],
            "record_transitions": [],
            "evidence": ["fixture:invalid-verifier-terminal-claim"],
            "artifact_paths": [],
        }
    output_path = write_json(tmp_path / f"{fault}.json", output)
    before = workspace["state"].read_bytes()

    result, payload = run_controller(
        "finalize-attempt",
        workspace["state"],
        "--attempt-token",
        token_path,
        "--slot-ledger",
        slot_path,
        "--status",
        "SUCCEEDED",
        "--runtime-agent-id",
        "agent-verifier-1",
        "--output",
        output_path,
        ok=None,
    )

    assert result.returncode != 0, payload
    assert payload["ok"] is False
    assert workspace["state"].read_bytes() == before


@pytest.mark.parametrize("mutate_verifier_snapshot", [False, True])
def test_critic_validates_copied_evidence_against_paired_verifier_attempt(
    tmp_path: Path, mutate_verifier_snapshot: bool
) -> None:
    workspace, state = drafted_workspace(tmp_path)
    verifier_token_path, verifier_token = prepare_attempt(
        tmp_path, workspace, state, "VERIFY_PLAN_VERIFIER"
    )
    assessment = {
        "iteration": 1,
        "obligation_id": "P1",
        "binding_sha256": "1" * 64,
        "status": "SUPPORTED",
        "evidence": [{
            "registry_kind": "PLAN_SECTION",
            "id": "S1",
            "claim": "The plan section supports the assigned obligation.",
        }],
        "finding_snapshots": [],
        "blocked_boundary": None,
    }
    assessment["assessment_fingerprint"] = sha256_bytes(canonical_bytes(assessment))
    verifier_output = role_output(state, verifier_token, "VERIFY_PLAN_VERIFIER")
    verifier_output["obligation_assessments"] = [assessment]
    verifier_output_path = write_json(tmp_path / "verifier-output.json", verifier_output)
    verifier_slots = slot_ledger(
        tmp_path / "verifier-slots.json",
        state="released",
        agent_id="agent-verifier-1",
    )
    run_controller(
        "finalize-attempt",
        workspace["state"],
        "--attempt-token",
        verifier_token_path,
        "--slot-ledger",
        verifier_slots,
        "--status",
        "SUCCEEDED",
        "--runtime-agent-id",
        "agent-verifier-1",
        "--output",
        verifier_output_path,
    )

    state = json.loads(workspace["state"].read_text(encoding="utf-8"))
    critic_token_path, critic_token = prepare_attempt(
        tmp_path, workspace, state, "VERIFY_PLAN_CRITIC"
    )
    critic_output = role_output(state, critic_token, "VERIFY_PLAN_CRITIC", verdict="PASS")
    critic_output["findings"] = verifier_output["findings"]
    critic_output["obligation_assessments"] = json.loads(
        json.dumps(verifier_output["obligation_assessments"])
    )
    critic_output["assessment_approvals"] = [{
        "iteration": 1,
        "obligation_id": "P1",
        "binding_sha256": assessment["binding_sha256"],
        "assessment_fingerprint": assessment["assessment_fingerprint"],
        "decision": "APPROVED",
        "rationale": "The verifier assessment is grounded in the assigned plan section.",
        "evidence": ["fixture:paired-verifier-assessment"],
    }]
    critic_output["coverage_exclusion_approvals"] = []
    critic_output["terminal_envelope"]["stage"] = "plan-verify"
    if mutate_verifier_snapshot:
        critic_output["obligation_assessments"][0]["status"] = "GAP"
    critic_output_path = write_json(tmp_path / "critic-output.json", critic_output)
    critic_slots = slot_ledger(
        tmp_path / "critic-slots.json",
        state="released",
        agent_id="agent-critic-1",
    )

    result, payload = run_controller(
        "finalize-attempt",
        workspace["state"],
        "--attempt-token",
        critic_token_path,
        "--slot-ledger",
        critic_slots,
        "--status",
        "SUCCEEDED",
        "--runtime-agent-id",
        "agent-critic-1",
        "--output",
        critic_output_path,
        ok=None,
    )

    assert (result.returncode != 0) is mutate_verifier_snapshot, payload
    if mutate_verifier_snapshot:
        assert payload["code"] == "INVALID_ROLE_OUTPUT"
    else:
        assert payload["code"] == "ATTEMPT_FINALIZED"


@pytest.mark.parametrize(
    ("verdict", "expected_status"),
    [("GAPS", "GAPS"), ("BLOCKED", "BLOCKED"), ("PASS", "READY")],
)
def test_final_stage_uses_assessor_terminal_envelope_verdict(
    tmp_path: Path, verdict: str, expected_status: str
) -> None:
    workspace, state = drafted_workspace(tmp_path)
    state["status"] = "HARDENING"
    state["stage_results"] = [
        {"round": 1, "stage": "VERIFY_PLAN", "terminal_verdict": "PASS"},
        {"round": 1, "stage": "INTERNAL_READINESS", "terminal_verdict": "PASS"},
        {"round": 1, "stage": "REQUIREMENTS_COVERAGE", "terminal_verdict": "PASS"},
    ]
    workspace["state"].write_bytes(canonical_bytes(state))
    token_path, token = prepare_attempt(
        tmp_path, workspace, state, "REQUIREMENTS_SATISFACTION"
    )
    slot_path = slot_ledger(
        tmp_path / "slots.json", state="released", agent_id="agent-satisfaction-1"
    )
    output_path = write_json(
        tmp_path / "satisfaction-output.json",
        role_output(state, token, "REQUIREMENTS_SATISFACTION", verdict=verdict),
    )
    run_controller(
        "finalize-attempt",
        workspace["state"],
        "--attempt-token",
        token_path,
        "--slot-ledger",
        slot_path,
        "--status",
        "SUCCEEDED",
        "--runtime-agent-id",
        "agent-satisfaction-1",
        "--output",
        output_path,
    )
    run_controller(
        "record-stage",
        workspace["state"],
        "--round",
        1,
        "--stage",
        "REQUIREMENTS_SATISFACTION",
        "--source-attempt-id",
        token["attempt_id"],
    )

    recorded = json.loads(workspace["state"].read_text(encoding="utf-8"))
    assert recorded["stage_results"][-1]["terminal_verdict"] == verdict
    assert recorded["status"] == expected_status
    if verdict in {"GAPS", "BLOCKED"}:
        assert recorded["status"] != "READY"


@pytest.mark.parametrize("tamper_target", ["input-snapshot", "source-snapshot"])
def test_finalize_fails_closed_after_pre_spawn_authority_tamper(
    tmp_path: Path, tamper_target: str
) -> None:
    workspace, state = drafted_workspace(tmp_path)
    token_path, token = prepare_attempt(
        tmp_path, workspace, state, "VERIFY_PLAN_VERIFIER"
    )
    if tamper_target == "input-snapshot":
        input_snapshot = (
            Path(state["run_root"])
            / "attempts"
            / token["attempt_id"]
            / "input.json"
        )
        changed = json.loads(input_snapshot.read_text(encoding="utf-8"))
        changed["objective"] = "tampered after preparation"
        input_snapshot.write_bytes(canonical_bytes(changed))
    else:
        snapshot_file = (
            Path(state["run_root"])
            / workspace["source_snapshot"]["snapshot_path"]
            / "source.txt"
        )
        snapshot_file.write_text("tampered after preparation\n", encoding="utf-8")
    slot_path = slot_ledger(
        tmp_path / "slots.json", state="released", agent_id="agent-verifier-1"
    )
    output_path = write_json(
        tmp_path / "verifier-output.json",
        role_output(state, token, "VERIFY_PLAN_VERIFIER"),
    )
    before = workspace["state"].read_bytes()

    result, payload = run_controller(
        "finalize-attempt",
        workspace["state"],
        "--attempt-token",
        token_path,
        "--slot-ledger",
        slot_path,
        "--status",
        "SUCCEEDED",
        "--runtime-agent-id",
        "agent-verifier-1",
        "--output",
        output_path,
        ok=None,
    )

    assert result.returncode != 0, payload
    assert payload["ok"] is False
    assert workspace["state"].read_bytes() == before


def test_record_findings_exact_replay_does_not_duplicate_occurrences(
    tmp_path: Path,
) -> None:
    workspace, state = drafted_workspace(tmp_path)
    state["status"] = "HARDENING"
    state["stage_results"] = [
        {"round": 1, "stage": "VERIFY_PLAN", "terminal_verdict": "PASS"},
        {"round": 1, "stage": "INTERNAL_READINESS", "terminal_verdict": "PASS"},
        {"round": 1, "stage": "REQUIREMENTS_COVERAGE", "terminal_verdict": "PASS"},
    ]
    workspace["state"].write_bytes(canonical_bytes(state))
    token_path, token = prepare_attempt(
        tmp_path, workspace, state, "REQUIREMENTS_SATISFACTION"
    )
    slot_path = slot_ledger(
        tmp_path / "slots.json", state="released", agent_id="agent-satisfaction-1"
    )
    output_path = write_json(
        tmp_path / "satisfaction-output.json",
        role_output(state, token, "REQUIREMENTS_SATISFACTION", verdict="GAPS"),
    )
    run_controller(
        "finalize-attempt",
        workspace["state"],
        "--attempt-token",
        token_path,
        "--slot-ledger",
        slot_path,
        "--status",
        "SUCCEEDED",
        "--runtime-agent-id",
        "agent-satisfaction-1",
        "--output",
        output_path,
    )
    finalized = json.loads(workspace["state"].read_text(encoding="utf-8"))
    owned_output = Path(finalized["run_root"]) / finalized["attempts"][-1]["output_path"]
    command = (
        "record-findings",
        workspace["state"],
        "--round",
        1,
        "--stage",
        "REQUIREMENTS_SATISFACTION",
        "--primary-output",
        owned_output,
    )
    run_controller(*command)
    first = workspace["state"].read_bytes()
    run_controller(*command)
    second = workspace["state"].read_bytes()
    state_after_replay = json.loads(second)

    assert second == first
    assert len(state_after_replay["findings"]) == 1
    assert len(state_after_replay["dispositions"]) == 1
