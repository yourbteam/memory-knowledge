import importlib.util
import copy
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    "promote_plan_playbook", ROOT / "scripts/promote_plan_playbook.py"
)
PROMOTION = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(PROMOTION)


def write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_slot_ledger(
    path: Path,
    agent_id: str,
    state: str,
    *,
    output_sha256: str | None = None,
) -> None:
    timestamps = {
        "acquired_at": 1,
        "bound_at": 2,
        "completed_at": 3,
        "closed_at": 4 if state in {"closed", "released"} else None,
        "released_at": 5 if state == "released" else None,
    }
    close = (
        f"multi_agent-close-agent:completed:{output_sha256}"
        if state in {"closed", "released"} and output_sha256
        else None
    )
    PROMOTION.write_json(path, {
        "version": 2,
        "max": 1,
        "slots": [{
            "id": "s1",
            "label": PROMOTION.LIVE_SLOT_LABEL,
            "state": state,
            "agent_id": agent_id,
            **timestamps,
            "evidence": {"close": close},
        }],
    })


def copy_candidate_fixture(destination: Path) -> None:
    source = ROOT / "skills/plan-playbook-v2"
    if source.exists():
        shutil.copytree(source, destination)
        return

    shutil.copytree(ROOT / "skills/plan-playbook", destination)
    skill_path = destination / "SKILL.md"
    skill = skill_path.read_text(encoding="utf-8")
    skill = skill.replace("name: plan-playbook\n", "name: plan-playbook-v2\n", 1)
    skill = skill.replace("# Plan Playbook\n", "# Plan Playbook V2 Candidate\n", 1)
    skill = skill.replace(
        "# Plan Playbook V2 Candidate\n",
        "# Plan Playbook V2 Candidate\n\n"
        "This candidate is explicit-only. Do not select it from an ordinary planning request and do not replace or modify canonical `plan-playbook` routing during candidate evaluation.\n",
        1,
    )
    skill = skill.replace(
        "The parent must invoke this playbook directly; never delegate the whole planning run to a",
        "The parent must invoke this candidate directly; never delegate the whole Planner v2 run to a",
        1,
    )
    skill = skill.replace(
        "The comparison contract formerly stored in `references/evaluation.md` is historical promotion evidence, not a runtime planning gate. Secrets, commits, pushes, deployments, and external messages retain their separate approval boundaries.",
        "Use [evaluation.md](references/evaluation.md) for candidate evaluation. Promotion, canonical replacement, installed-skill replacement, secrets, commits, and pushes require their separately authorized operations.",
        1,
    )
    skill_path.write_text(skill, encoding="utf-8")
    metadata = destination / "agents/openai.yaml"
    metadata.write_text(
        metadata.read_text(encoding="utf-8").replace("$plan-playbook", "$plan-playbook-v2"),
        encoding="utf-8",
    )
    write(destination / "references/evaluation.md", "# Candidate evaluation\n")
    routing = destination / "references/approval-and-routing.md"
    routing.write_text(
        routing.read_text(encoding="utf-8")
        .replace(
            "Ordinary planning selects canonical `$plan-playbook`. The playbook performs planning only: it does not implement, review code, replace installed skills, commit, or push.",
            "The candidate is selected only by explicit `$plan-playbook-v2` invocation. Ordinary planning continues to select canonical `plan-playbook` during evaluation. The candidate performs planning only: it does not implement, review code, promote itself, replace installed skills, commit, or push.",
        )
        .replace("consume the canonical package", "consume the candidate package"),
        encoding="utf-8",
    )


def fake_repository(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    repo = tmp_path / "repo"
    installed = tmp_path / "installed"
    PROMOTION.TRUSTED_REPO_ROOT = repo.resolve()
    PROMOTION.TRUSTED_INSTALLED_ROOTS = (installed.resolve(),)
    candidate = repo / "skills/plan-playbook-v2"
    copy_candidate_fixture(candidate)

    write(
        repo / "skills/plan-playbook/SKILL.md",
        "---\nname: plan-playbook\ndescription: legacy\n---\n# Legacy\n",
    )
    write(repo / "skills/plan-playbook/agents/openai.yaml", "interface:\n  display_name: Legacy\n")
    for name in ("_shared", "research-playbook"):
        write(repo / f"skills/{name}/placeholder.txt", name)
    write(
        repo / "skills/managed-skills.txt",
        "_shared\nplan-playbook\nplan-playbook-v2\n"
        "research-playbook\n",
    )

    write(repo / "scripts/evaluate_plan_playbook_v2.py", "skills/plan-playbook-v2/scripts/plan_package.py\n")
    for name in (
        "test_plan_playbook_v2.py",
        "test_plan_playbook_v2_attempt_policy.py",
        "test_plan_playbook_v2_authority.py",
        "test_plan_playbook_v2_continuation.py",
        "test_plan_playbook_v2_evaluator.py",
        "test_plan_playbook_v2_package_lifecycle.py",
        "test_plan_playbook_v2_revision_recovery.py",
        "test_skill_contracts.py",
        "test_validate_skills.py",
    ):
        write(repo / f"tests/{name}", "skills/plan-playbook-v2/scripts/plan_package.py\n")
    score = repo / "score.json"
    write(score, "{}\n")

    plans = []
    for scenario_id in ("scenario-1", "scenario-2"):
        plan = repo / f"{scenario_id}.md"
        write(plan, f"# {scenario_id}\n")
        implementation = repo / f"tools/{scenario_id}.py"
        write(implementation, "VALUE = 1\n")
        review = repo / f"{scenario_id}-review.json"
        allowed_paths = [f"tools/{scenario_id}.py"]
        PROMOTION.write_json(review, {
            "schema_version": 1,
            "scenario_id": scenario_id,
            "repository": str(repo),
            "reviewer_agent_id": f"fixture-reviewer-{scenario_id}",
            "reviewed_files": allowed_paths,
            "findings": [],
            "verdict": "PASS",
        })
        plans.append({
            "scenario_id": scenario_id,
            "repository": str(repo),
            "plan_path": str(plan),
            "plan_sha256": PROMOTION.sha256_file(plan),
            "allowed_paths": allowed_paths,
            "implementation_files": [{"path": f"tools/{scenario_id}.py", "sha256": PROMOTION.sha256_file(implementation)}],
            "focused_command": ["true"],
            "full_command": ["true"],
            "review_path": str(review),
            "review_sha256": PROMOTION.sha256_file(review),
            "verdict": "PASS",
        })
    practical = repo / "practical-evidence.json"
    PROMOTION.write_json(practical, {
        "schema_version": 1,
        "candidate_tree_sha256": PROMOTION.tree_hash(candidate),
        "scenarios": plans,
        "all_passed": True,
    })
    PROMOTION.TRUSTED_SCENARIOS = {
        scenario["scenario_id"]: {
            field: scenario[field]
            for field in (
                "repository", "plan_path", "allowed_paths", "focused_command",
                "full_command", "review_path",
            )
        }
        for scenario in plans
    }

    for name in (
        "_shared", "plan-playbook", "plan-playbook-v2", "research-playbook",
    ):
        source = repo / f"skills/{name}"
        if source.exists():
            shutil.copytree(source, installed / name)
    return repo, installed, score, practical


def install_from_source(repo: Path, installed: Path, _state: Path) -> None:
    for name in (
        "_shared", "plan-playbook", "research-playbook",
    ):
        destination = installed / name
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(repo / f"skills/{name}", destination)


def test_stage_canonical_removes_candidate_routing(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    copy_candidate_fixture(candidate)
    stage = tmp_path / "stage"
    PROMOTION.stage_canonical(candidate, stage)
    skill = (stage / "SKILL.md").read_text(encoding="utf-8")
    metadata = (stage / "agents/openai.yaml").read_text(encoding="utf-8")
    assert "name: plan-playbook\n" in skill
    assert "$plan-playbook-v2" not in skill + metadata
    assert "explicit-only" not in skill + metadata
    assert "INTERNAL_READINESS" in skill
    assert "REQUIREMENTS_COVERAGE" in skill
    assert "REQUIREMENTS_SATISFACTION" in skill
    assert "allow_implicit_invocation" not in metadata
    assert not (stage / "references/evaluation.md").exists()


def test_apply_installs_canonical_and_retires_alias(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, installed, score, practical = fake_repository(tmp_path)
    plan = PROMOTION.build_plan(repo, installed, practical)
    receipt = PROMOTION.apply_plan(
        plan, tmp_path / "backup",
        installer=lambda repo_root, installed_root, state: install_from_source(repo_root, installed_root, state),
    )
    assert receipt["ok"] is True
    assert not (repo / "skills/plan-playbook-v2").exists()
    assert not (installed / "plan-playbook-v2").exists()
    assert PROMOTION.tree_hash(repo / "skills/plan-playbook") == PROMOTION.tree_hash(installed / "plan-playbook")
    assert "plan-playbook-v2" not in (repo / "skills/managed-skills.txt").read_text().splitlines()
    assert not (repo / "skills/task-workflow").exists()
    assert not (installed / "task-workflow").exists()


def test_apply_failure_restores_every_tracked_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, installed, score, practical = fake_repository(tmp_path)
    plan = PROMOTION.build_plan(repo, installed, practical)
    before = {
        name: PROMOTION.path_state(Path(item["path"]))
        for name, item in plan["paths"].items()
    }

    def fail_install(*_args):
        raise RuntimeError("forced installer failure")

    with pytest.raises(RuntimeError, match="forced installer failure"):
        PROMOTION.apply_plan(plan, tmp_path / "backup", installer=fail_install)
    for name, item in plan["paths"].items():
        assert PROMOTION.path_state(Path(item["path"])) == before[name]


def test_parser_exposes_complete_promotion_lifecycle() -> None:
    parser = PROMOTION.build_parser()
    choices = parser._subparsers._group_actions[0].choices
    assert set(choices) == {"plan", "apply", "validate", "record-live", "verify", "abort", "recover"}


def test_validation_commands_are_planner_scoped() -> None:
    commands = PROMOTION.validation_commands(ROOT)

    assert len(commands) == 2
    assert commands[0] == [str(ROOT / "working-agreement/validate-skills.sh")]
    assert commands[1][0] == str(ROOT / "scripts/run_pytest.sh")
    assert "tests/test_promote_plan_playbook.py" in commands[1]


def test_validation_receipt_tracks_current_command_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = [["validate-skills"], ["run-focused-tests"]]
    monkeypatch.setattr(PROMOTION, "validation_commands", lambda _root: expected)
    receipt = tmp_path / "validation.json"
    PROMOTION.write_json(receipt, {
        "schema_version": 1,
        "all_passed": True,
        "commands": [
            {"sequence": index, "argv": argv, "exit_code": 0}
            for index, argv in enumerate(expected, 1)
        ],
        "canonical_tree_sha256": "a" * 64,
        "plan_sha256": "b" * 64,
    })
    plan = {"validation_receipt": str(receipt), "repo_root": str(tmp_path), "plan_sha256": "b" * 64}

    assert PROMOTION._validation_receipt_ok(plan, "a" * 64) is True


def test_plan_omits_secondary_score_without_weakening_practical_gate(tmp_path: Path) -> None:
    repo, installed, _score, practical = fake_repository(tmp_path)

    plan = PROMOTION.build_plan(repo, installed, practical)

    assert plan["secondary_score_path"] is None
    assert plan["secondary_score_sha256"] is None
    assert plan["secondary_score_validation"] is None
    assert plan["practical_evidence_validation"]["valid"] is True


def test_practical_evidence_rejects_changed_implementation(tmp_path: Path) -> None:
    repo, _installed, _score, practical = fake_repository(tmp_path)
    write(repo / "tools/scenario-1.py", "VALUE = 2\n")

    with pytest.raises(PROMOTION.PromotionError, match="practical-scenario-not-pass:scenario-1"):
        PROMOTION.validate_practical_evidence(repo, practical)


def test_practical_evidence_rejects_handwritten_pass_review(tmp_path: Path) -> None:
    repo, _installed, _score, practical = fake_repository(tmp_path)
    evidence = PROMOTION.read_json(practical)
    review = repo / "scenario-1-review.json"
    PROMOTION.write_json(review, {"verdict": "PASS"})
    evidence["scenarios"][0]["review_sha256"] = PROMOTION.sha256_file(review)
    PROMOTION.write_json(practical, evidence)

    with pytest.raises(PROMOTION.PromotionError, match="practical-scenario-not-pass:scenario-1"):
        PROMOTION.validate_practical_evidence(repo, practical)


def test_practical_evidence_rejects_untrusted_recorded_command(tmp_path: Path) -> None:
    repo, _installed, _score, practical = fake_repository(tmp_path)
    evidence = PROMOTION.read_json(practical)
    evidence["scenarios"][0]["focused_command"] = ["false"]
    PROMOTION.write_json(practical, evidence)

    with pytest.raises(PROMOTION.PromotionError, match="practical-scenario-contract-mismatch"):
        PROMOTION.validate_practical_evidence(repo, practical)


def test_practical_evidence_runs_trusted_command_and_rejects_failure(tmp_path: Path) -> None:
    repo, _installed, _score, practical = fake_repository(tmp_path)
    evidence = PROMOTION.read_json(practical)
    evidence["scenarios"][0]["focused_command"] = ["false"]
    PROMOTION.TRUSTED_SCENARIOS["scenario-1"]["focused_command"] = ["false"]
    PROMOTION.write_json(practical, evidence)

    with pytest.raises(
        PROMOTION.PromotionError,
        match="practical-scenario-command-failed:scenario-1:focused",
    ):
        PROMOTION.validate_practical_evidence(repo, practical)


def test_rollback_rejects_redirected_backup_manifest(tmp_path: Path) -> None:
    repo, installed, _score, practical = fake_repository(tmp_path)
    plan = PROMOTION.build_plan(repo, installed, practical)
    backup = tmp_path / "backup"
    PROMOTION.apply_plan(
        plan, backup,
        installer=lambda repo_root, installed_root, state: install_from_source(
            repo_root, installed_root, state
        ),
    )
    manifest_path = backup / "backup-manifest.json"
    manifest = PROMOTION.read_json(manifest_path)
    manifest["entries"]["canonical_source"]["backup"] = str(
        backup / "paths/candidate_source"
    )
    PROMOTION.write_json(manifest_path, manifest)

    with pytest.raises(PROMOTION.PromotionError, match="backup-entry-mismatch:canonical_source"):
        PROMOTION.rollback(plan, backup, "TEST", tmp_path / "rollback.json")
    assert not (repo / "skills/plan-playbook-v2").exists()


def test_recover_rolls_back_partial_apply_journal(tmp_path: Path) -> None:
    repo, installed, _score, practical = fake_repository(tmp_path)
    plan = PROMOTION.build_plan(repo, installed, practical)
    before = {
        name: PROMOTION.path_state(Path(item["path"]))
        for name, item in plan["paths"].items()
    }
    backup = tmp_path / "backup"
    PROMOTION.apply_plan(
        plan, backup,
        installer=lambda repo_root, installed_root, state: install_from_source(
            repo_root, installed_root, state
        ),
    )
    PROMOTION.write_journal(backup, plan, "FILES_REWRITTEN")
    plan_path = tmp_path / "plan.json"
    PROMOTION.write_json(plan_path, plan)

    receipt = PROMOTION.cmd_recover(SimpleNamespace(
        plan=plan_path,
        backup_root=backup,
        out=tmp_path / "recovery.json",
    ))

    assert receipt["all_restored"] is True
    for name, item in plan["paths"].items():
        assert PROMOTION.path_state(Path(item["path"])) == before[name]


def test_recover_restores_actual_interruption_with_missing_canonical(tmp_path: Path) -> None:
    repo, installed, _score, practical = fake_repository(tmp_path)
    plan = PROMOTION.build_plan(repo, installed, practical)
    paths = PROMOTION.validate_preconditions(plan)
    before = {
        name: PROMOTION.path_state(Path(item["path"]))
        for name, item in plan["paths"].items()
    }
    backup = tmp_path / "backup"
    PROMOTION.create_backup(paths, backup, plan)
    stage = repo / "skills/.plan-playbook-promotion-interrupted"
    PROMOTION.write_journal(backup, plan, "BACKED_UP", stage)
    PROMOTION.stage_canonical(paths["candidate_source"], stage)
    shutil.copytree(paths["canonical_source"], paths["legacy_fixture"])
    shutil.rmtree(paths["canonical_source"])
    plan_path = tmp_path / "plan.json"
    PROMOTION.write_json(plan_path, plan)

    receipt = PROMOTION.cmd_recover(SimpleNamespace(
        plan=plan_path,
        backup_root=backup,
        out=tmp_path / "recovery.json",
    ))

    assert receipt["all_restored"] is True
    assert not stage.exists()
    for name, item in plan["paths"].items():
        assert PROMOTION.path_state(Path(item["path"])) == before[name]


def test_rollback_rejects_forged_plan_path_set_before_deleting_path(tmp_path: Path) -> None:
    repo, installed, _score, practical = fake_repository(tmp_path)
    plan = PROMOTION.build_plan(repo, installed, practical)
    backup = tmp_path / "backup"
    paths = PROMOTION.validate_preconditions(plan)
    PROMOTION.create_backup(paths, backup, plan)
    PROMOTION.write_journal(backup, plan, "BACKED_UP")
    victim = tmp_path / "unrelated.txt"
    write(victim, "must survive\n")
    forged = copy.deepcopy(plan)
    forged["paths"]["canonical_source"] = {
        "path": str(victim),
        "before": PROMOTION.path_state(victim),
    }
    forged.pop("plan_sha256")
    forged["plan_sha256"] = PROMOTION.hashlib.sha256(
        PROMOTION.canonical_bytes(forged)
    ).hexdigest()

    with pytest.raises(PROMOTION.PromotionError, match="plan-path-set-mismatch"):
        PROMOTION.rollback(forged, backup, "FORGED", tmp_path / "rollback.json")
    assert victim.read_text(encoding="utf-8") == "must survive\n"


def test_apply_preconditions_reject_untrusted_root_before_importing_evaluator(
    tmp_path: Path,
) -> None:
    repo, installed, _score, practical = fake_repository(tmp_path)
    plan = PROMOTION.build_plan(repo, installed, practical)
    untrusted = tmp_path / "untrusted"
    marker = tmp_path / "evaluator-executed"
    write(
        untrusted / "scripts/evaluate_plan_playbook_v2.py",
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n",
    )
    score = untrusted / "score.json"
    write(score, "{}\n")
    forged = copy.deepcopy(plan)
    forged["repo_root"] = str(untrusted)
    forged["secondary_score_path"] = str(score)
    forged["secondary_score_sha256"] = PROMOTION.sha256_file(score)
    forged["secondary_score_validation"] = {"valid": True}

    with pytest.raises(PROMOTION.PromotionError, match="untrusted-repository-root"):
        PROMOTION.validate_preconditions(forged)
    assert not marker.exists()


def test_validation_preflight_exception_rolls_back(tmp_path: Path) -> None:
    repo, installed, _score, practical = fake_repository(tmp_path)
    validation = tmp_path / "validation.json"
    plan = PROMOTION.build_plan(repo, installed, practical, validation_receipt=validation)
    before = {
        name: PROMOTION.path_state(Path(item["path"]))
        for name, item in plan["paths"].items()
    }
    backup = tmp_path / "backup"
    PROMOTION.apply_plan(
        plan, backup,
        installer=lambda repo_root, installed_root, state: install_from_source(
            repo_root, installed_root, state
        ),
    )
    (repo / "skills/plan-playbook/agents/openai.yaml").unlink()
    plan_path = tmp_path / "plan.json"
    PROMOTION.write_json(plan_path, plan)

    with pytest.raises(OSError):
        PROMOTION.cmd_validate(SimpleNamespace(
            plan=plan_path,
            backup_root=backup,
            out=validation,
        ))
    for name, item in plan["paths"].items():
        assert PROMOTION.path_state(Path(item["path"])) == before[name]


def test_verification_receipt_exception_rolls_back(tmp_path: Path) -> None:
    repo, installed, _score, practical = fake_repository(tmp_path)
    plan = PROMOTION.build_plan(
        repo, installed, practical,
        validation_receipt=tmp_path / "missing-validation.json",
    )
    before = {
        name: PROMOTION.path_state(Path(item["path"]))
        for name, item in plan["paths"].items()
    }
    backup = tmp_path / "backup"
    PROMOTION.apply_plan(
        plan, backup,
        installer=lambda repo_root, installed_root, state: install_from_source(
            repo_root, installed_root, state
        ),
    )
    plan_path = tmp_path / "plan.json"
    PROMOTION.write_json(plan_path, plan)

    with pytest.raises(PROMOTION.PromotionError, match="invalid-json"):
        PROMOTION.cmd_verify(SimpleNamespace(plan=plan_path, backup_root=backup))
    for name, item in plan["paths"].items():
        assert PROMOTION.path_state(Path(item["path"])) == before[name]


def test_validation_receipt_rejects_plan_tamper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = [["validate-skills"]]
    monkeypatch.setattr(PROMOTION, "validation_commands", lambda _root: expected)
    receipt = tmp_path / "validation.json"
    PROMOTION.write_json(receipt, {
        "schema_version": 1,
        "all_passed": True,
        "commands": [{"sequence": 1, "argv": expected[0], "exit_code": 0}],
        "canonical_tree_sha256": "a" * 64,
        "plan_sha256": "b" * 64,
    })
    plan = {"validation_receipt": str(receipt), "repo_root": str(tmp_path), "plan_sha256": "c" * 64}

    assert PROMOTION._validation_receipt_ok(plan, "a" * 64) is False


def test_live_receipt_is_bound_to_persisted_input_and_output(tmp_path: Path) -> None:
    agent_input = tmp_path / "agent-input.json"
    agent_output = tmp_path / "agent-output.json"
    write(agent_input, "input\n")
    write(agent_output, "output\n")
    output_sha256 = PROMOTION.sha256_file(agent_output)
    agent_id = "runtime-agent-1"
    ledger = tmp_path / "slots.json"
    write_slot_ledger(ledger, agent_id, "released", output_sha256=output_sha256)
    receipt = tmp_path / "live.json"
    PROMOTION.write_json(receipt, {
        "schema_version": 1,
        "plan_sha256": "p" * 64,
        "input_sha256": PROMOTION.sha256_file(agent_input),
        "agent_input_path": str(agent_input),
        "agent_output_path": str(agent_output),
        "agent_input_sha256": PROMOTION.sha256_file(agent_input),
        "agent_output_sha256": output_sha256,
        "runtime_agent_id": agent_id,
        "runtime_slot_ledger_path": str(ledger),
        "selected_skill": "plan-playbook",
        "invocation": None,
        "terminal_probe": "PRODUCE_DRAFT",
        "canonical_tree_sha256": "c" * 64,
    })
    plan = {"live_receipt": str(receipt), "plan_sha256": "p" * 64}

    assert PROMOTION._live_receipt_ok(plan, "c" * 64) is True
    write_slot_ledger(ledger, agent_id, "completed")
    assert PROMOTION._live_receipt_ok(plan, "c" * 64) is False
    write_slot_ledger(ledger, agent_id, "released", output_sha256=output_sha256)
    write(agent_output, "tampered\n")
    assert PROMOTION._live_receipt_ok(plan, "c" * 64) is False


def test_failed_live_record_rolls_back_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, installed, _score, practical = fake_repository(tmp_path)
    validation = tmp_path / "validation.json"
    live = tmp_path / "live.json"
    plan = PROMOTION.build_plan(
        repo, installed, practical,
        validation_receipt=validation,
        live_receipt=live,
    )
    before = {
        name: PROMOTION.path_state(Path(item["path"]))
        for name, item in plan["paths"].items()
    }
    backup = tmp_path / "backup"
    PROMOTION.apply_plan(
        plan, backup,
        installer=lambda repo_root, installed_root, state: install_from_source(
            repo_root, installed_root, state
        ),
    )
    commands = [["true"]]
    monkeypatch.setattr(PROMOTION, "validation_commands", lambda _root: commands)
    PROMOTION.write_json(validation, {
        "schema_version": 1,
        "plan_sha256": plan["plan_sha256"],
        "all_passed": True,
        "commands": [{"sequence": 1, "argv": commands[0], "exit_code": 0}],
        "canonical_tree_sha256": PROMOTION.tree_hash(repo / "skills/plan-playbook"),
    })
    agent_input = tmp_path / "agent-input.json"
    agent_output = tmp_path / "agent-output.json"
    slot_ledger = tmp_path / "slots.json"
    runtime_agent_id = "runtime-agent-1"
    write_slot_ledger(slot_ledger, runtime_agent_id, "completed")
    PROMOTION.write_json(agent_input, {
        "schema_version": 1,
        "request": "Create an implementation plan for a bounded feature.",
        "installed_root": str(installed.resolve()),
        "output_contract": "PLAN_PLAYBOOK_LIVE_V1",
    })
    PROMOTION.write_json(agent_output, {"schema_version": 1, "invalid": True})
    plan_path = tmp_path / "plan.json"
    PROMOTION.write_json(plan_path, plan)

    with pytest.raises(PROMOTION.PromotionError, match="live-agent-output-invalid"):
        PROMOTION.cmd_record_live(SimpleNamespace(
            plan=plan_path,
            backup_root=backup,
            agent_input=agent_input,
            agent_output=agent_output,
            runtime_agent_id=runtime_agent_id,
            slot_ledger=slot_ledger,
            out=live,
        ))
    for name, item in plan["paths"].items():
        assert PROMOTION.path_state(Path(item["path"])) == before[name]
