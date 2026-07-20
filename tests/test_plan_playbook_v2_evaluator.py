from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts/evaluate_plan_playbook_v2.py"
SPEC = importlib.util.spec_from_file_location("plan_v2_evaluator", SCRIPT)
assert SPEC and SPEC.loader
evaluator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluator)


def test_dynamic_module_loaders_do_not_write_bytecode(tmp_path: Path) -> None:
    plan_package = evaluator.plan_owner()
    original = sys.dont_write_bytecode
    try:
        for index, loader in enumerate((evaluator.module_from_path, plan_package.module_from_path)):
            source = tmp_path / f"owner_{index}.py"
            source.write_text(f"VALUE = {index}\n", encoding="utf-8")
            sys.dont_write_bytecode = False

            module = loader(f"bytecode_safety_owner_{index}", source)

            assert module.VALUE == index
            assert sys.dont_write_bytecode is False
            assert not (tmp_path / "__pycache__").exists()
    finally:
        sys.dont_write_bytecode = original


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def pointer_value(document: object, pointer: str) -> object:
    return evaluator.json_pointer(document, pointer)


def test_public_implementer_contract_exposes_evaluator_action_shapes() -> None:
    contract = json.loads(
        (ROOT / "tests/fixtures/plan-playbook-v2/implementer-output-contract.json").read_text(
            encoding="utf-8"
        )
    )
    implementation = contract["properties"]["implementation_actions"]["items"]
    verification = contract["properties"]["verification_actions"]["items"]
    assert set(implementation["properties"]) == evaluator.IMPLEMENTATION_ACTION_FIELDS
    assert set(implementation["required"]) == evaluator.IMPLEMENTATION_ACTION_FIELDS
    assert implementation["additionalProperties"] is False
    assert set(verification["properties"]) == evaluator.VERIFICATION_ACTION_FIELDS
    assert set(verification["required"]) == evaluator.VERIFICATION_ACTION_FIELDS
    assert verification["additionalProperties"] is False
    source_rule = contract["properties"]["consulted_sources"]["description"]
    assert "sorted unique union" in source_rule
    assert "must be empty when both action arrays are empty" in source_rule
    for action in (implementation, verification):
        action_source_rule = action["properties"]["consulted_source_paths"]["description"]
        assert "Only authorized implementation-source snapshot paths" in action_source_rule
        assert "Do not include the input envelope, plan, output contract" in action_source_rule
    artifact = contract["x-consulted-sources-artifact"]
    assert set(artifact["json_schema"]["properties"]) == evaluator.CONSULTED_SOURCES_FIELDS
    assert set(artifact["json_schema"]["required"]) == evaluator.CONSULTED_SOURCES_FIELDS
    assert artifact["json_schema"]["additionalProperties"] is False


@pytest.mark.parametrize("arm", ["legacy", "v2"])
def test_public_planner_contract_exposes_exact_evaluator_fields_and_rules(arm: str) -> None:
    row = {"arm": arm, "case_id": "case-a", "phase": "initial"}
    contract = evaluator.planner_public_output_contract(row)
    expected = (
        evaluator.CANDIDATE_PLANNER_OUTPUT_FIELDS
        if arm == "v2"
        else evaluator.LEGACY_PLANNER_OUTPUT_FIELDS
    )
    schema = contract["json_schema"]
    assert set(schema["properties"]) == expected
    assert set(schema["required"]) == expected
    assert schema["additionalProperties"] is False
    assert any("PASS requires plan_path" in rule for rule in contract["terminal_rules"])
    assert any("BLOCKED requires plan_path" in rule for rule in contract["terminal_rules"])
    sources_contract = evaluator.consulted_sources_public_contract()["json_schema"]
    assert set(sources_contract["properties"]) == evaluator.CONSULTED_SOURCES_FIELDS
    assert set(sources_contract["required"]) == evaluator.CONSULTED_SOURCES_FIELDS
    assert sources_contract["additionalProperties"] is False


def test_public_routing_contract_exposes_exact_evaluator_fields() -> None:
    contract = evaluator.routing_public_output_contract()
    schema = contract["json_schema"]
    assert set(schema["properties"]) == evaluator.ROUTING_OUTPUT_FIELDS
    assert set(schema["required"]) == evaluator.ROUTING_OUTPUT_FIELDS
    assert schema["additionalProperties"] is False


def authority_fixture(root: Path) -> tuple[Path, dict]:
    sources = root / "sources"
    sources.mkdir(parents=True)
    cases = []
    for index, case_id in enumerate(evaluator.CASE_IDS):
        source_relative = f"sources/grounded-{index}.md"
        source = root / source_relative
        source.write_text("grounded authority source\n", encoding="utf-8")
        source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
        case = {
            "case_id": case_id,
            "request": f"Grounded request {index}",
            "visible_evidence": [{
                "evidence_id": f"E{index}",
                "path": source_relative,
                "sha256": source_sha,
            }],
            "canonical_requirement_ids": [f"R{index}"],
            "canonical_obligation_ids": [f"O{index}"],
            "negative_boundaries": [{
                "boundary_id": f"B{index}",
                "statement": f"Boundary {index}",
            }],
            "forbidden_scope_claims": [{
                "id": f"FS{index}",
                "claim": f"Forbidden scope {index}",
                "evidence_ids": [f"E{index}"],
            }],
            "forbidden_evidence_claims": [{
                "id": f"FE{index}",
                "claim": f"Forbidden evidence {index}",
                "evidence_ids": [f"E{index}"],
            }],
            "expected_transitions": {
                "legacy": [{"phase": "initial", "terminal_verdict": "PASS", "blocker_code": None}],
                "v2": [{"phase": "initial", "terminal_verdict": "PASS", "blocker_code": None}],
            },
            "implementation_roots": [{
                "repository_key": "memory-knowledge",
                "path": "skills/sequence-runner",
                "tree_sha256": evaluator.tree_owner().TREE_SHA256_V1(ROOT / "skills/sequence-runner"),
            }],
            "derivations": [],
        }
        cases.append(case)
    authority = {
        "schema_version": 1,
        "authority_id": "pending",
        "source_bundle_sha256": "pending",
        "cases": cases,
        "created_at_utc": "2026-07-19T00:00:00Z",
    }
    for index, case in enumerate(cases):
        for pointer in sorted(evaluator.expected_derivation_pointers(case, index)):
            assert pointer_value(authority, pointer) is not None or pointer.endswith("/blocker_code")
            case["derivations"].append({
                "authority_pointer": pointer,
                "source_evidence_id": f"E{index}",
                "source_path": f"sources/grounded-{index}.md",
                "source_sha256": case["visible_evidence"][0]["sha256"],
                "source_selector": "L1-L1",
                "source_excerpt": "grounded authority source",
                "source_excerpt_sha256": hashlib.sha256(b"grounded authority source").hexdigest(),
            })
    authority["source_bundle_sha256"] = hashlib.sha256(
        evaluator.canonical_bytes(evaluator.source_bundle_records(authority))
    ).hexdigest()
    identity = {
        key: authority[key]
        for key in evaluator.AUTHORITY_FIELDS - {"authority_id", "created_at_utc"}
    }
    authority["authority_id"] = "plan-v2-fixture-authority-" + hashlib.sha256(
        evaluator.canonical_bytes(identity)
    ).hexdigest()[:24]
    path = root / "fixture-authority.json"
    write_json(path, authority)
    return path, authority


def write_slot_ledger(path: Path, *, state: str, agent_id: str | None) -> None:
    slot = {
        "id": "s1", "label": "fixture-authority-review", "state": state,
        "agent_id": agent_id, "acquired_at": 1, "evidence": {},
    }
    if state == "released":
        slot.update({
            "bound_at": 2, "completed_at": 3, "closed_at": 4, "released_at": 5,
            "evidence": {"close": "independent review completed"},
        })
    write_json(path, {"version": 2, "max": 1, "slots": [slot]})


def valid_review_output(authority: dict, authority_path: Path) -> dict:
    authority_receipt = evaluator.validate_fixture_authority(authority_path.parent, authority_path)
    return {
        "schema_version": 1,
        "authority_sha256": authority_receipt["authority_sha256"],
        "source_bundle_sha256": authority_receipt["source_bundle_sha256"],
        "case_assessments": [
            {
                "case_id": case_id,
                "request_preserves_intent": True,
                "visible_evidence_sufficient": True,
                "ids_source_derived": True,
                "boundaries_complete": True,
                "forbidden_claims_complete": True,
                "transitions_correct": True,
                "implementation_roots_real": True,
                "evidence": evaluator.authority_case_evidence(authority, index),
            }
            for index, case_id in enumerate(evaluator.CASE_IDS)
        ],
        "untraceable_pointers": [],
        "weakened_or_substituted_values": [],
        "verdict": "PASS",
    }


def completed_authority_review(root: Path) -> tuple[Path, Path, Path, dict]:
    authority_path, authority = authority_fixture(root)
    ledger = root / "slot-ledger.json"
    write_slot_ledger(ledger, state="reserved", agent_id=None)
    token_path = root / "authority-review/attempt-token.json"
    evaluator.prepare_fixture_authority_review(
        root, authority_path, "s1", ledger, token_path,
        now="2026-07-19T01:00:00Z",
    )
    output_path = root / "raw-review-output.json"
    write_json(output_path, valid_review_output(authority, authority_path))
    write_slot_ledger(ledger, state="released", agent_id="reviewer-1")
    evaluator.finalize_fixture_authority_review(
        token_path, ledger, "SUCCEEDED", runtime_agent_id="reviewer-1",
        output_path=output_path, now="2026-07-19T01:01:00Z",
    )
    receipt = evaluator.record_fixture_authority_review(
        root, authority_path, token_path, ledger, output_path,
        root / "fixture-authority-review.json", now="2026-07-19T01:02:00Z",
    )
    return authority_path, token_path, ledger, receipt


def test_validate_fixture_authority_accepts_exact_grounded_projection(tmp_path: Path) -> None:
    path, authority = authority_fixture(tmp_path)

    receipt = evaluator.validate_fixture_authority(tmp_path, path)

    assert receipt == {
        "schema_version": 1,
        "valid": True,
        "authority_id": authority["authority_id"],
        "authority_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source_bundle_sha256": authority["source_bundle_sha256"],
        "case_ids": list(evaluator.CASE_IDS),
        "source_records": evaluator.source_bundle_records(authority),
        "implementation_root_snapshots": evaluator.implementation_root_snapshots(authority),
    }


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("missing-derivation", "INVALID_DERIVATION"),
        ("forged-id", "AUTHORITY_ID_MISMATCH"),
        ("traversal", "INVALID_PATH"),
    ],
)
def test_validate_fixture_authority_rejects_single_faults(
    tmp_path: Path, mutation: str, code: str,
) -> None:
    path, authority = authority_fixture(tmp_path)
    changed = copy.deepcopy(authority)
    if mutation == "missing-derivation":
        changed["cases"][0]["derivations"].pop()
    elif mutation == "forged-id":
        changed["authority_id"] = "plan-v2-fixture-authority-" + "0" * 24
    else:
        changed["cases"][0]["derivations"][0]["source_path"] = "../outside.md"
    write_json(path, changed)

    with pytest.raises(evaluator.EvaluationError) as caught:
        evaluator.validate_fixture_authority(tmp_path, path)

    assert caught.value.code == code


def test_validate_fixture_authority_rejects_source_tamper(tmp_path: Path) -> None:
    path, _authority = authority_fixture(tmp_path)
    (tmp_path / "sources/grounded-0.md").write_text("changed\n", encoding="utf-8")

    with pytest.raises(evaluator.EvaluationError) as caught:
        evaluator.validate_fixture_authority(tmp_path, path)

    assert caught.value.code == "SOURCE_TAMPER"


def test_validate_fixture_authority_rejects_computed_root_digest_claim(tmp_path: Path) -> None:
    path, authority = authority_fixture(tmp_path)
    changed = copy.deepcopy(authority)
    changed["cases"][0]["implementation_roots"][0]["tree_sha256"] = "0" * 64
    identity = {
        key: changed[key]
        for key in evaluator.AUTHORITY_FIELDS - {"authority_id", "created_at_utc"}
    }
    changed["authority_id"] = "plan-v2-fixture-authority-" + hashlib.sha256(
        evaluator.canonical_bytes(identity)
    ).hexdigest()[:24]
    write_json(path, changed)

    with pytest.raises(evaluator.EvaluationError) as caught:
        evaluator.validate_fixture_authority(tmp_path, path)

    assert caught.value.code == "IMPLEMENTATION_ROOT_MISMATCH"


def test_computed_integrity_fields_are_not_semantic_derivations(tmp_path: Path) -> None:
    _path, authority = authority_fixture(tmp_path)
    pointers = evaluator.expected_derivation_pointers(authority["cases"][0], 0)

    assert "/cases/0/visible_evidence/0/sha256" not in pointers
    assert "/cases/0/implementation_roots/0/tree_sha256" not in pointers


def test_approved_coherent_source_snapshots_are_byte_exact() -> None:
    source_root = ROOT / "tests/fixtures/plan-playbook-v2/sources"
    expected = {
        "E10-readiness-analysis.md": "0f441a8e98866839f974d93d6bfcbb2094924a1993440bf984061f7543eede74",
        "E10-readiness-plan.md": "cec1dae63630741d490ee0eb33bc6b7aa5e2144e4ec32755a12c266615b7c542",
        "E11-memory-directives-analysis.md": "d1257f64b049ad26ee024419cbe13ec92143bc7302937160ddb649b1b05c8267",
        "E11-endpoint-decision.md": "d09e874603345708af8313e3c76c903208e05c361b521fefbc98964d34bb2a19",
        "E11-memory-directives-plan.md": "43a8e2308e0aab9e5f2fcf8a5753a518b06158cef40c56a12a6e2c19e5d3f8cc",
        "E12-coverage-audit.md": "e30ac6fc67f4efdb128d5c685f6574bbd061a0202ac1c898323fdca5dff7f0cd",
        "E13-satisfaction-audit.md": "66e6136ec48b2f4a713ff04f3034d8483f8d1c2bff2573a40cdf7b3595bd86fd",
        "E14-consolidation-plan.md": "88aa14be4bcc8e4c64af58026e94f861f3e74c8835b62e382c4cab7e70d34bad",
        "E14-consolidation-research.md": "71578b268b3f5bb7df7ce75e8939a634c5c9d7de2fbbcbde0aa8d097e731694b",
    }
    assert sorted(path.name for path in source_root.iterdir()) == sorted(expected)
    for name, digest in expected.items():
        assert hashlib.sha256((source_root / name).read_bytes()).hexdigest() == digest


def test_authority_review_lifecycle_records_and_recursively_replays(tmp_path: Path) -> None:
    authority_path, token_path, ledger, receipt = completed_authority_review(tmp_path)

    replay = evaluator.validate_fixture_authority_review(
        tmp_path, authority_path, token_path, ledger,
        tmp_path / "fixture-authority-review.json",
    )
    recorded_replay = evaluator.record_fixture_authority_review(
        tmp_path, authority_path, token_path, ledger,
        tmp_path / "authority-review/output.json",
        tmp_path / "fixture-authority-review.json",
        now="2099-01-01T00:00:00Z",
    )

    assert replay == receipt
    assert recorded_replay == receipt
    assert receipt["recorded_at_utc"] == "2026-07-19T01:02:00Z"
    assert receipt["reviewer_runtime_agent_id"] == "reviewer-1"


def test_authority_review_receipt_revalidates_without_mutable_slot_ledger(tmp_path: Path) -> None:
    authority_path, _token_path, ledger, receipt = completed_authority_review(tmp_path)
    ledger.unlink()

    replay = evaluator.validate_fixture_authority_review_receipt(
        tmp_path, authority_path, tmp_path / "fixture-authority-review.json",
    )

    assert replay == receipt


def test_offline_authority_review_rejects_released_projection_tamper(tmp_path: Path) -> None:
    authority_path, _token_path, _ledger, _receipt = completed_authority_review(tmp_path)
    released_path = tmp_path / "authority-review/released-slot.json"
    released = json.loads(released_path.read_text(encoding="utf-8"))
    released["evidence"]["close"] = "changed after review"
    write_json(released_path, released)

    with pytest.raises(evaluator.EvaluationError) as caught:
        evaluator.validate_fixture_authority_review_receipt(
            tmp_path, authority_path, tmp_path / "fixture-authority-review.json",
        )

    assert caught.value.code == "INVALID_REVIEW_RECEIPT"


def test_prepare_authority_review_rejects_noncanonical_output_path(tmp_path: Path) -> None:
    authority_path, _authority = authority_fixture(tmp_path)
    ledger = tmp_path / "slot-ledger.json"
    write_slot_ledger(ledger, state="reserved", agent_id=None)

    with pytest.raises(evaluator.EvaluationError) as caught:
        evaluator.prepare_fixture_authority_review(
            tmp_path, authority_path, "s1", ledger, tmp_path / "token.json",
        )

    assert caught.value.code == "INVALID_PATH"


def test_prepare_authority_review_replaces_abandoned_different_authority(tmp_path: Path) -> None:
    authority_path, authority = authority_fixture(tmp_path)
    ledger = tmp_path / "slot-ledger.json"
    write_slot_ledger(ledger, state="reserved", agent_id=None)
    token_path = tmp_path / "authority-review/attempt-token.json"
    first = evaluator.prepare_fixture_authority_review(
        tmp_path, authority_path, "s1", ledger, token_path,
        now="2026-07-19T01:00:00Z",
    )
    authority["created_at_utc"] = "2026-07-19T02:00:00Z"
    write_json(authority_path, authority)

    replacement = evaluator.prepare_fixture_authority_review(
        tmp_path, authority_path, "s1", ledger, token_path,
        now="2026-07-19T02:01:00Z",
    )

    assert replacement["authority_sha256"] == hashlib.sha256(authority_path.read_bytes()).hexdigest()
    assert replacement["authority_sha256"] != first["authority_sha256"]
    assert replacement["prepared_at_utc"] == "2026-07-19T02:01:00Z"
    assert json.loads(token_path.read_text(encoding="utf-8")) == replacement


def test_prepare_authority_review_rejects_replacement_after_terminal_artifact(tmp_path: Path) -> None:
    authority_path, authority = authority_fixture(tmp_path)
    ledger = tmp_path / "slot-ledger.json"
    write_slot_ledger(ledger, state="reserved", agent_id=None)
    token_path = tmp_path / "authority-review/attempt-token.json"
    evaluator.prepare_fixture_authority_review(tmp_path, authority_path, "s1", ledger, token_path)
    write_json(tmp_path / "authority-review/attempt.json", {})
    authority["created_at_utc"] = "2026-07-19T02:00:00Z"
    write_json(authority_path, authority)

    with pytest.raises(evaluator.EvaluationError) as caught:
        evaluator.prepare_fixture_authority_review(
            tmp_path, authority_path, "s1", ledger, token_path,
        )

    assert caught.value.code == "REVIEW_REPLAY_CONFLICT"


def test_finalize_authority_review_rejects_parent_runtime_identity_mismatch(tmp_path: Path) -> None:
    authority_path, authority = authority_fixture(tmp_path)
    ledger = tmp_path / "slot-ledger.json"
    write_slot_ledger(ledger, state="reserved", agent_id=None)
    token_path = tmp_path / "authority-review/attempt-token.json"
    evaluator.prepare_fixture_authority_review(tmp_path, authority_path, "s1", ledger, token_path)
    raw_output = tmp_path / "raw-output.json"
    write_json(raw_output, valid_review_output(authority, authority_path))
    write_slot_ledger(ledger, state="released", agent_id="reviewer-1")

    with pytest.raises(evaluator.EvaluationError) as caught:
        evaluator.finalize_fixture_authority_review(
            token_path, ledger, "SUCCEEDED", runtime_agent_id="forged-reviewer",
            output_path=raw_output,
        )

    assert caught.value.code == "INVALID_RUNTIME_ID"
    assert not (tmp_path / "authority-review/attempt.json").exists()


def test_finalize_authority_review_rejects_self_asserted_pass_without_evidence(tmp_path: Path) -> None:
    authority_path, authority = authority_fixture(tmp_path)
    ledger = tmp_path / "slot-ledger.json"
    write_slot_ledger(ledger, state="reserved", agent_id=None)
    token_path = tmp_path / "authority-review/attempt-token.json"
    evaluator.prepare_fixture_authority_review(tmp_path, authority_path, "s1", ledger, token_path)
    output = valid_review_output(authority, authority_path)
    output["case_assessments"][0]["evidence"] = []
    raw_output = tmp_path / "raw-output.json"
    write_json(raw_output, output)
    write_slot_ledger(ledger, state="released", agent_id="reviewer-1")

    with pytest.raises(evaluator.EvaluationError) as caught:
        evaluator.finalize_fixture_authority_review(
            token_path, ledger, "SUCCEEDED", runtime_agent_id="reviewer-1",
            output_path=raw_output,
        )

    assert caught.value.code == "INVALID_REVIEW_OUTPUT"


def test_recursive_review_validation_rejects_post_review_authority_edit(tmp_path: Path) -> None:
    authority_path, token_path, ledger, _receipt = completed_authority_review(tmp_path)
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    authority["cases"][0]["request"] = "changed after review"
    write_json(authority_path, authority)

    with pytest.raises(evaluator.EvaluationError):
        evaluator.validate_fixture_authority_review(
            tmp_path, authority_path, token_path, ledger,
            tmp_path / "fixture-authority-review.json",
        )


def managed_roots(tmp_path: Path) -> tuple[Path, Path, Path]:
    manifest = tmp_path / "managed.txt"
    manifest.write_text("legacy\ncandidate\nshared\n", encoding="utf-8")
    installed = tmp_path / "installed"
    installed.mkdir()
    (installed / "legacy").mkdir()
    (installed / "legacy/SKILL.md").write_text("legacy\n", encoding="utf-8")
    (installed / "shared").mkdir()
    (installed / "shared/helper.py").write_text("before\n", encoding="utf-8")
    return manifest, installed, tmp_path / "backups"


def attempt_run(tmp_path: Path) -> tuple[Path, Path, Path]:
    fixture_root = ROOT / "tests/fixtures/plan-playbook-v2"
    run_root = tmp_path / "run"
    run_root.mkdir()
    evaluator.prepare(
        fixture_root,
        fixture_root / "fixture-authority.json",
        fixture_root / "fixture-authority-review.json",
        run_root,
    )
    row_input = run_root / "rows/legacy-small-planner/input.json"
    ledger = tmp_path / "attempt-ledger.json"
    return run_root, row_input, ledger


def released_attempt_ledger(
    path: Path, *, slot_id: str, agent_id: str | None,
    abandoned: bool = False,
) -> None:
    slot = {
        "id": slot_id, "label": "evaluator-attempt", "state": "released",
        "agent_id": agent_id, "acquired_at": 1, "bound_at": None,
        "completed_at": None, "closed_at": None, "abandoned_at": None,
        "released_at": 5,
        "evidence": {"close": None, "abandon_reason": None},
    }
    if abandoned:
        slot["abandoned_at"] = 2
        slot["evidence"]["abandon_reason"] = "spawn or bind failed"
        if agent_id is not None:
            slot["evidence"]["close"] = "runtime closed before bind"
    else:
        slot.update({"bound_at": 2, "completed_at": 3, "closed_at": 4})
        slot["evidence"]["close"] = "agent completed and closed"
    write_json(path, {"version": 2, "max": 1, "slots": [slot]})


def test_managed_snapshot_compare_and_restore_round_trip(tmp_path: Path) -> None:
    manifest, installed, backups = managed_roots(tmp_path)
    before_path = tmp_path / "before.json"
    before = evaluator.snapshot_managed(
        manifest, installed, backups / "before", before_path,
        now="2026-07-19T02:00:00Z",
    )
    assert [row["installed_state"] for row in before["skills"]] == [
        "PRESENT", "ABSENT", "PRESENT",
    ]
    (installed / "candidate").mkdir()
    (installed / "candidate/SKILL.md").write_text("candidate\n", encoding="utf-8")
    (installed / "shared/helper.py").write_text("after\n", encoding="utf-8")
    after_path = tmp_path / "after.json"
    evaluator.snapshot_managed(
        manifest, installed, backups / "after", after_path,
        now="2026-07-19T02:01:00Z",
    )

    comparison = evaluator.compare_managed(
        before_path, after_path, ["candidate"], ["shared"],
    )
    restored = evaluator.restore_managed(before_path, installed)

    assert comparison["passed"] is True
    assert comparison["added"] == ["candidate"]
    assert comparison["changed"] == ["shared"]
    assert restored == {
        "schema_version": 1, "restored": ["legacy", "shared"],
        "removed": ["candidate"],
    }
    assert not (installed / "candidate").exists()
    assert (installed / "shared/helper.py").read_text(encoding="utf-8") == "before\n"


def test_managed_skill_name_contract_accepts_canonical_shared_and_rejects_traversal() -> None:
    assert evaluator.SAFE_SKILL_NAME_RE.fullmatch("_shared")
    assert evaluator.SAFE_SKILL_NAME_RE.fullmatch("..") is None


def test_managed_compare_rejects_unallowed_or_unused_drift(tmp_path: Path) -> None:
    manifest, installed, backups = managed_roots(tmp_path)
    before_path = tmp_path / "before.json"
    evaluator.snapshot_managed(manifest, installed, backups / "before", before_path)
    (installed / "shared/helper.py").write_text("after\n", encoding="utf-8")
    after_path = tmp_path / "after.json"
    evaluator.snapshot_managed(manifest, installed, backups / "after", after_path)

    comparison = evaluator.compare_managed(
        before_path, after_path, ["candidate"], [],
    )

    assert comparison["passed"] is False
    assert comparison["unexpected_changed"] == ["shared"]
    assert comparison["unused_added_allowances"] == ["candidate"]


def test_managed_restore_rejects_backup_tamper(tmp_path: Path) -> None:
    manifest, installed, backups = managed_roots(tmp_path)
    snapshot_path = tmp_path / "before.json"
    snapshot = evaluator.snapshot_managed(manifest, installed, backups, snapshot_path)
    legacy = next(row for row in snapshot["skills"] if row["name"] == "legacy")
    (backups / legacy["backup_relpath"] / "SKILL.md").write_text("tampered\n", encoding="utf-8")

    with pytest.raises(evaluator.EvaluationError) as caught:
        evaluator.restore_managed(snapshot_path, installed)

    assert caught.value.code == "BACKUP_TAMPER"


def test_outer_and_routing_attempts_share_sequence_and_finalize_from_slot_evidence(
    tmp_path: Path,
) -> None:
    run_root, row_input, ledger = attempt_run(tmp_path)
    write_json(ledger, {
        "version": 2, "max": 1,
        "slots": [{
            "id": "outer-slot", "label": "outer", "state": "reserved",
            "agent_id": None, "acquired_at": 1, "evidence": {},
        }],
    })
    outer_out = run_root / "rows/legacy-small-planner/attempts/plan-v2-attempt-placeholder/token.json"
    sequence = 1
    outer_id = "plan-v2-attempt-" + hashlib.sha256(evaluator.canonical_bytes({
        "run_id": "legacy-small-planner", "sequence": sequence,
        "input_sha256": hashlib.sha256(row_input.read_bytes()).hexdigest(),
        "slot_id": "outer-slot",
    })).hexdigest()[:24]
    outer_out = run_root / f"rows/legacy-small-planner/attempts/{outer_id}/token.json"
    outer_token = evaluator.prepare_attempt(
        run_root, "legacy-small-planner", "outer-slot", ledger, row_input, outer_out,
        now="2026-07-19T03:00:00Z",
    )
    raw_outer = tmp_path / "outer-output.json"
    write_json(raw_outer, {"schema_version": 1, "ok": True})
    released_attempt_ledger(ledger, slot_id="outer-slot", agent_id="outer-agent")
    outer = evaluator.finalize_attempt(
        run_root, outer_out, ledger, "SUCCEEDED", "outer-agent", raw_outer,
        now="2026-07-19T03:01:00Z",
    )
    write_json(ledger, {
        "version": 2, "max": 1,
        "slots": [{
            "id": "probe-slot", "label": "probe", "state": "reserved",
            "agent_id": None, "acquired_at": 6, "evidence": {},
        }],
    })
    explicit = run_root / "candidate-checks/requests/explicit.json"
    routing_id = "plan-v2-routing-" + hashlib.sha256(evaluator.canonical_bytes({
        "probe": "CANDIDATE_EXPLICIT", "sequence": 2,
        "input_sha256": hashlib.sha256(explicit.read_bytes()).hexdigest(),
        "slot_id": "probe-slot",
    })).hexdigest()[:24]
    routing_out = run_root / f"candidate-checks/attempts/{routing_id}/token.json"
    routing_token = evaluator.prepare_routing_probe(
        run_root, "CANDIDATE_EXPLICIT", "probe-slot", ledger, routing_out,
        now="2026-07-19T03:02:00Z",
    )
    raw_routing = tmp_path / "routing-output.json"
    write_json(raw_routing, {"schema_version": 1, "selected_skill": "plan-playbook-v2"})
    released_attempt_ledger(ledger, slot_id="probe-slot", agent_id="probe-agent")
    routing = evaluator.finalize_routing_probe(
        run_root, routing_out, ledger, "SUCCEEDED", "probe-agent", raw_routing,
        now="2026-07-19T03:03:00Z",
    )

    assert outer_token["attempt_sequence"] == 1
    assert outer["runtime_agent_id"] == "outer-agent"
    assert routing_token["attempt_sequence"] == 2
    assert routing["released_slot_path"].endswith("/released-slot.json")


def test_attempt_finalization_accepts_prebind_abandonment_and_rejects_reviewer_reuse(
    tmp_path: Path,
) -> None:
    run_root, row_input, ledger = attempt_run(tmp_path)
    write_json(ledger, {
        "version": 2, "max": 1,
        "slots": [{
            "id": "s2", "label": "outer", "state": "reserved",
            "agent_id": None, "acquired_at": 1, "evidence": {},
        }],
    })
    input_sha = hashlib.sha256(row_input.read_bytes()).hexdigest()
    attempt_id = "plan-v2-attempt-" + hashlib.sha256(evaluator.canonical_bytes({
        "run_id": "legacy-small-planner", "sequence": 1,
        "input_sha256": input_sha, "slot_id": "s2",
    })).hexdigest()[:24]
    token_path = run_root / f"rows/legacy-small-planner/attempts/{attempt_id}/token.json"
    evaluator.prepare_attempt(
        run_root, "legacy-small-planner", "s2", ledger, row_input, token_path,
    )
    released_attempt_ledger(ledger, slot_id="s2", agent_id="bind-agent", abandoned=True)

    finalized = evaluator.finalize_attempt(
        run_root, token_path, ledger, "BIND_FAILED", "bind-agent", None,
    )

    assert finalized["status"] == "BIND_FAILED"

    state = json.loads((run_root / "prepared-run.json").read_text(encoding="utf-8"))
    review = json.loads(
        (run_root / state["authority_review_path"]).read_text(encoding="utf-8")
    )
    state["outer_attempts"][0]["runtime_agent_id"] = review["reviewer_runtime_agent_id"]
    write_json(run_root / "prepared-run.json", state)
    with pytest.raises(evaluator.EvaluationError) as caught:
        evaluator.known_runtime_ids(run_root, state)
    assert caught.value.code == "DUPLICATE_RUNTIME_ID"


def test_repository_fixture_manifest_is_an_exact_reviewed_authority_projection() -> None:
    fixture = ROOT / "tests/fixtures/plan-playbook-v2"

    validated = evaluator.validate_fixture_manifest(fixture)

    assert [item["manifest"]["case_id"] for item in validated["cases"]] == list(
        evaluator.CASE_IDS
    )
    assert validated["manifest"]["source_bundle_sha256"] == validated["authority"][
        "source_bundle_sha256"
    ]


def test_prepare_freezes_exact_thirteen_row_matrix_and_controller_inputs(
    tmp_path: Path,
) -> None:
    fixture = ROOT / "tests/fixtures/plan-playbook-v2"
    run_root = tmp_path / "run"
    run_root.mkdir()

    prepared = evaluator.prepare(
        fixture,
        fixture / "fixture-authority.json",
        fixture / "fixture-authority-review.json",
        run_root,
    )

    assert set(prepared) == evaluator.PREPARED_RUN_FIELDS
    assert [row["run_id"] for row in prepared["matrix"]] == [
        "legacy-small-planner",
        "legacy-small-implementer",
        "legacy-substantial-planner",
        "legacy-substantial-implementer",
        "legacy-uncertain-planner",
        "legacy-uncertain-implementer",
        "v2-small-planner",
        "v2-small-implementer",
        "v2-substantial-planner",
        "v2-substantial-implementer",
        "v2-uncertain-initial-planner",
        "v2-uncertain-resumed-planner",
        "v2-uncertain-implementer",
    ]
    assert all(set(row) == evaluator.MATRIX_ROW_FIELDS for row in prepared["matrix"])
    assert sum(row["status"] == "PREPARED" for row in prepared["matrix"]) == 3
    assert sum(
        row["status"] == "WAITING_ON_INITIALIZATION" for row in prepared["matrix"]
    ) == 3
    assert sum(row["status"] == "WAITING_ON_RESUME" for row in prepared["matrix"]) == 1
    assert sum(row["status"] == "WAITING_ON_DEPENDENCY" for row in prepared["matrix"]) == 6
    assert evaluator.load_prepared_run(run_root)[2] == prepared
    assert evaluator.prepare(
        fixture,
        fixture / "fixture-authority.json",
        fixture / "fixture-authority-review.json",
        run_root,
    ) == prepared


def test_small_grounded_charter_includes_source_derived_test_surface() -> None:
    fixture_root = ROOT / "tests/fixtures/plan-playbook-v2"
    fixture = evaluator.validate_fixture_manifest(fixture_root)
    charter_ref = fixture["cases"][0]["charter_ref"]
    charter = json.loads((fixture_root / charter_ref["path"]).read_text(encoding="utf-8"))

    assert charter["allowed_paths"] == [
        {"path": "src/memory_knowledge/db", "repository_key": "memory-knowledge"},
        {"path": "tests/test_health.py", "repository_key": "memory-knowledge"},
    ]


def test_fixture_manifest_rejects_public_contract_that_drifted_from_authority(
    tmp_path: Path,
) -> None:
    source = ROOT / "tests/fixtures/plan-playbook-v2"
    fixture = tmp_path / "fixture"
    import shutil

    shutil.copytree(source, fixture)
    manifest = json.loads((fixture / "manifest.json").read_text(encoding="utf-8"))
    public_path = fixture / manifest["cases"][0]["public_contract"]["path"]
    public = json.loads(public_path.read_text(encoding="utf-8"))
    public["requirement_ids"] = ["invented"]
    write_json(public_path, public)
    manifest["cases"][0]["public_contract"]["sha256"] = hashlib.sha256(
        public_path.read_bytes()
    ).hexdigest()
    write_json(fixture / "manifest.json", manifest)

    with pytest.raises(evaluator.EvaluationError) as caught:
        evaluator.validate_fixture_manifest(fixture)

    assert caught.value.code == "AUTHORITY_PROJECTION_MISMATCH"


def test_record_candidate_checks_derives_routing_and_managed_projection(
    tmp_path: Path,
) -> None:
    run_root, _row_input, ledger = attempt_run(tmp_path)
    slots = [
        {
            "id": slot_id, "label": probe, "state": "reserved",
            "agent_id": None, "acquired_at": index, "evidence": {},
        }
        for index, (slot_id, probe) in enumerate(
            (("explicit-slot", "explicit"), ("ordinary-slot", "ordinary")), start=1,
        )
    ]
    write_json(ledger, {"version": 2, "max": 2, "slots": slots})
    state = evaluator.load_prepared_run(run_root)[2]

    def token_path(probe: str, slot_id: str, sequence: int) -> Path:
        key = "explicit" if probe == "CANDIDATE_EXPLICIT" else "ordinary"
        request = run_root / state["candidate_check_requests"][f"{key}_path"]
        attempt_id = "plan-v2-routing-" + hashlib.sha256(evaluator.canonical_bytes({
            "probe": probe, "sequence": sequence,
            "input_sha256": hashlib.sha256(request.read_bytes()).hexdigest(),
            "slot_id": slot_id,
        })).hexdigest()[:24]
        return run_root / f"candidate-checks/attempts/{attempt_id}/token.json"

    explicit_token = token_path("CANDIDATE_EXPLICIT", "explicit-slot", 1)
    ordinary_token = token_path("ORDINARY_LEGACY", "ordinary-slot", 2)
    explicit = evaluator.prepare_routing_probe(
        run_root, "CANDIDATE_EXPLICIT", "explicit-slot", ledger, explicit_token,
    )
    ordinary = evaluator.prepare_routing_probe(
        run_root, "ORDINARY_LEGACY", "ordinary-slot", ledger, ordinary_token,
    )
    released = []
    for index, (slot, agent_id) in enumerate(
        ((slots[0], "explicit-agent"), (slots[1], "ordinary-agent")), start=1,
    ):
        released.append({
            **slot, "state": "released", "agent_id": agent_id,
            "bound_at": 10 + index, "completed_at": 20 + index,
            "closed_at": 30 + index, "released_at": 40 + index,
            "evidence": {"close": "routing completed", "abandon_reason": None},
        })
    write_json(ledger, {"version": 2, "max": 2, "slots": released})
    explicit_output = tmp_path / "explicit-output.json"
    ordinary_output = tmp_path / "ordinary-output.json"
    write_json(explicit_output, {
        "schema_version": 1, "input_sha256": explicit["input_sha256"],
        "invocation": "$plan-playbook-v2", "selected_skill": "plan-playbook-v2",
        "completed_at_utc": "2026-07-19T04:00:00Z",
    })
    write_json(ordinary_output, {
        "schema_version": 1, "input_sha256": ordinary["input_sha256"],
        "invocation": None, "selected_skill": "plan-playbook",
        "completed_at_utc": "2026-07-19T04:00:01Z",
    })
    evaluator.finalize_routing_probe(
        run_root, explicit_token, ledger, "SUCCEEDED", "explicit-agent", explicit_output,
    )
    evaluator.finalize_routing_probe(
        run_root, ordinary_token, ledger, "SUCCEEDED", "ordinary-agent", ordinary_output,
    )

    manifest = tmp_path / "managed.txt"
    manifest.write_text(
        "_shared\nplan-playbook\nplan-playbook-v2\nresearch-playbook\n",
        encoding="utf-8",
    )
    installed = tmp_path / "installed"
    installed.mkdir()
    for name in ("_shared", "plan-playbook", "research-playbook"):
        shutil.copytree(ROOT / f"skills/{name}", installed / name)
    before = tmp_path / "managed-before.json"
    evaluator.snapshot_managed(
        manifest, installed, tmp_path / "before-backups", before,
        now="2026-07-19T04:01:00Z",
    )
    shutil.copytree(ROOT / "skills/plan-playbook", installed / "plan-playbook-v2")
    (installed / "_shared/candidate-marker").write_text("candidate\n", encoding="utf-8")
    (installed / "research-playbook/candidate-marker").write_text(
        "candidate\n", encoding="utf-8",
    )
    after = tmp_path / "managed-after.json"
    evaluator.snapshot_managed(
        manifest, installed, tmp_path / "after-backups", after,
        now="2026-07-19T04:02:00Z",
    )

    evidence = evaluator.record_candidate_checks(
        run_root, explicit_token, ordinary_token, ledger, before, after,
        now="2026-07-19T04:03:00Z",
    )

    assert evidence["candidate_explicit_routing"] is True
    assert evidence["ordinary_legacy_routing"] is True
    assert evidence["managed_projection_clean"] is True
    assert evaluator.record_candidate_checks(
        run_root, explicit_token, ordinary_token, ledger, before, after,
    ) == evidence
    prepared = evaluator.load_prepared_run(run_root)[2]
    assert prepared["candidate_check_evidence_path"] == "candidate-checks/evidence.json"
    assert prepared["candidate_check_evidence_sha256"] == hashlib.sha256(
        (run_root / "candidate-checks/evidence.json").read_bytes()
    ).hexdigest()
