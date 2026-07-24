from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    "promote_research_playbook", ROOT / "scripts/promote_research_playbook.py"
)
promotion = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(promotion)


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def passing_score() -> dict:
    return {
        "schema_version": 1,
        "verdict": "PASS",
        "matrix_complete": True,
        "predicates": {
            "budget_compliance": {"pass": True},
            "complete_critical_recall": {
                "pass": True, "ratio": 1.0, "recalled": 8, "total": 8,
            },
            "planner_pass_every_case": {"pass": True},
            "v2_false_material_gaps_no_worse_than_legacy": {
                "pass": True, "legacy_count": 0, "v2_count": 0,
            },
            "zero_invented_evidence": {
                "pass": True, "invented_claim_count": 0, "invented_evidence_count": 0,
            },
            "zero_scope_maturity_drift": {
                "pass": True, "scope_drift_count": 0, "maturity_drift_count": 0,
            },
        },
    }


def write_legacy_skill(path: Path) -> None:
    (path / "agents").mkdir(parents=True)
    (path / "SKILL.md").write_text(
        "---\nname: research-playbook\ndescription: Legacy research skill.\n---\n\n# Playbook: Research\n",
        encoding="utf-8",
    )
    (path / "agents/openai.yaml").write_text(
        "interface:\n  display_name: Research Playbook\n  short_description: Legacy\n"
        "  default_prompt: Use $research-playbook.\n",
        encoding="utf-8",
    )


def write_candidate_skill(path: Path) -> None:
    (path / "agents").mkdir(parents=True)
    (path / "references").mkdir()
    (path / "scripts").mkdir()
    (path / "SKILL.md").write_text(
        "---\n"
        "name: research-playbook-v2\n"
        "description: Candidate research skill.\n"
        "---\n\n"
        "# Research Playbook V2\n\n"
        "- Do not promote this skill, replace `research-playbook`, or alter routing.\n\n"
        "Use [evaluation.md](references/evaluation.md) when validating this skill against the legacy playbook before promotion.\n",
        encoding="utf-8",
    )
    (path / "agents/openai.yaml").write_text(
        "interface:\n  display_name: Research Playbook V2\n  short_description: Candidate\n"
        "  default_prompt: Use $research-playbook-v2.\n"
        "policy:\n  allow_implicit_invocation: false\n",
        encoding="utf-8",
    )
    (path / "references/lenses-and-findings.md").write_text(
        "python3 skills/research-playbook-v2/scripts/research_package.py hash-json input.json\n",
        encoding="utf-8",
    )
    (path / "references/evaluation.md").write_text(
        "# Comparative Evaluation Contract\n\n"
        "- 6 v2 research executions using explicit `$research-playbook-v2`;\n"
        "- explicit v2 invocation selects v2 in a fresh task;\n"
        "- an ordinary research prompt still selects legacy in a fresh task;\n"
        "- every pre-existing managed Codex skill remains byte-identical after installation, with only `research-playbook-v2` added.\n\n"
        "reduces live executions; it does not create a smaller fixture corpus or weaken a predicate. Legacy\n"
        "replacement remains a separate approval after this comparison passes.\n",
        encoding="utf-8",
    )
    (path / "scripts/research_package.py").write_text("print('candidate')\n", encoding="utf-8")


def fixture(tmp_path: Path) -> dict[str, Path]:
    repo = tmp_path / "repo"
    skills = repo / "skills"
    installed = tmp_path / "installed"
    for path in (repo / "scripts", repo / "tests", repo / "working-agreement", installed):
        path.mkdir(parents=True, exist_ok=True)
    write_legacy_skill(skills / "research-playbook")
    write_candidate_skill(skills / "research-playbook-v2")
    (skills / "managed-skills.txt").write_text(
        "research-playbook\nresearch-playbook-v2\n", encoding="utf-8"
    )
    (repo / "scripts/evaluate_research_playbook_v2.py").write_text(
        'row = {"invocation": "ordinary research prompt" if arm == "legacy" else "$research-playbook-v2",}\n'
        'trees = (("legacy", "skills/research-playbook"),\n'
        '        ("v2", "skills/research-playbook-v2"),)\n',
        encoding="utf-8",
    )
    (repo / "tests/test_research_playbook_v2.py").write_text(
        'MODULE_PATH = ROOT / "skills/research-playbook-v2/scripts/research_package.py"\n'
        'LENSES = ROOT / "skills/research-playbook-v2/references/lenses-and-findings.md"\n'
        'REFERENCES = Path(__file__).parents[1] / "skills/research-playbook-v2/references"\n',
        encoding="utf-8",
    )
    (repo / "tests/test_validate_skills.py").write_text(
        '    def test_research_playbook_v2_is_managed_and_explicit_only(self):\n'
        '        managed=(ROOT/"skills/managed-skills.txt").read_text().splitlines()\n'
        '        self.assertIn("research-playbook-v2",managed)\n'
        '        metadata=(ROOT/"skills/research-playbook-v2/agents/openai.yaml").read_text()\n'
        '        self.assertIn("policy:\\n  allow_implicit_invocation: false\\n",metadata)\n'
        '        self.assertEqual(v.validate_openai(ROOT/"skills/research-playbook-v2/agents/openai.yaml"),[])\n',
        encoding="utf-8",
    )
    shutil.copytree(skills / "research-playbook", installed / "research-playbook")
    shutil.copytree(skills / "research-playbook-v2", installed / "research-playbook-v2")
    score = tmp_path / "score.json"
    plan = tmp_path / "plan.json"
    validation = tmp_path / "validation.json"
    live = tmp_path / "live.json"
    write_json(score, passing_score())
    return {
        "repo": repo,
        "installed": installed,
        "score": score,
        "plan": plan,
        "validation": validation,
        "live": live,
        "backup": tmp_path / "backup",
    }


def build_fixture_plan(paths: dict[str, Path]) -> dict:
    plan = promotion.build_plan(
        paths["repo"], paths["installed"], paths["score"],
        validation_receipt=paths["validation"], live_receipt=paths["live"],
    )
    write_json(paths["plan"], plan)
    return plan


def test_plan_is_read_only_and_locks_exact_six_gates(tmp_path: Path) -> None:
    paths = fixture(tmp_path)
    before = {
        name: promotion.path_state(path)
        for name, path in promotion.tracked_paths(paths["repo"], paths["installed"]).items()
    }

    plan = build_fixture_plan(paths)

    after = {
        name: promotion.path_state(path)
        for name, path in promotion.tracked_paths(paths["repo"], paths["installed"]).items()
    }
    assert before == after
    assert tuple(plan["completion_gates"]) == promotion.PLAN_GATES
    assert promotion.load_plan(paths["plan"])["plan_sha256"] == plan["plan_sha256"]


def test_plan_rejects_any_failed_promotion_threshold(tmp_path: Path) -> None:
    paths = fixture(tmp_path)
    score = passing_score()
    score["predicates"]["zero_invented_evidence"]["pass"] = False
    write_json(paths["score"], score)

    with pytest.raises(promotion.PromotionError, match="candidate-predicate-failed"):
        promotion.build_plan(paths["repo"], paths["installed"], paths["score"])


def test_preconditions_reject_rehashed_plan_with_redirected_path(tmp_path: Path) -> None:
    paths = fixture(tmp_path)
    plan = build_fixture_plan(paths)
    plan["paths"]["canonical_source"]["path"] = str(tmp_path / "redirected")
    plan_without_hash = {key: value for key, value in plan.items() if key != "plan_sha256"}
    plan["plan_sha256"] = promotion.hashlib.sha256(
        promotion.canonical_bytes(plan_without_hash)
    ).hexdigest()

    with pytest.raises(promotion.PromotionError, match="plan-path-set-mismatch"):
        promotion.validate_preconditions(plan)


def copying_installer(repo: Path, installed: Path, state: Path) -> None:
    del state
    target = installed / "research-playbook"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(repo / "skills/research-playbook", target)


def write_evidence(paths: dict[str, Path], plan: dict) -> None:
    canonical_hash = promotion.tree_hash(paths["repo"] / "skills/research-playbook")
    write_json(paths["validation"], {
        "schema_version": 1,
        "focused_tests_exit": 0,
        "full_tests_exit": 0,
        "skill_validation_exit": 0,
        "canonical_tree_sha256": canonical_hash,
    })
    write_json(paths["live"], {
        "schema_version": 1,
        "skill_name": "research-playbook",
        "invocation": "$research-playbook",
        "package_validation": "PASS",
        "all_slots_closed": True,
        "canonical_tree_sha256": canonical_hash,
        "roles": {
            "core": "agent-core",
            "internal_readiness": "agent-internal",
            "requirements_coverage": "agent-coverage",
            "requirements_satisfaction": "agent-satisfaction",
            "adjudicator": "agent-adjudicator",
        },
    })


def test_apply_replaces_canonical_retires_alias_and_verifies(tmp_path: Path) -> None:
    paths = fixture(tmp_path)
    plan = build_fixture_plan(paths)
    old_canonical_hash = promotion.tree_hash(paths["repo"] / "skills/research-playbook")

    result = promotion.apply_plan(plan, paths["backup"], installer=copying_installer)
    write_evidence(paths, plan)
    verification = promotion.verify_structure(plan, paths["backup"])

    assert result["ok"] is True
    assert verification["verdict"] == "PASS"
    assert all(verification["gates"].values())
    assert not (paths["repo"] / "skills/research-playbook-v2").exists()
    assert not (paths["installed"] / "research-playbook-v2").exists()
    assert promotion.tree_hash(paths["repo"] / "tests/fixtures/research-playbook-legacy") == old_canonical_hash
    assert promotion.tree_hash(paths["repo"] / "skills/research-playbook") == promotion.tree_hash(
        paths["installed"] / "research-playbook"
    )


def test_apply_restores_every_path_when_installer_fails(tmp_path: Path) -> None:
    paths = fixture(tmp_path)
    plan = build_fixture_plan(paths)
    tracked = promotion.tracked_paths(paths["repo"], paths["installed"])
    before = {name: promotion.path_state(path) for name, path in tracked.items()}

    def failed_installer(repo: Path, installed: Path, state: Path) -> None:
        del repo, installed, state
        raise RuntimeError("injected-installer-failure")

    with pytest.raises(RuntimeError, match="injected-installer-failure"):
        promotion.apply_plan(plan, paths["backup"], installer=failed_installer)

    assert {name: promotion.path_state(path) for name, path in tracked.items()} == before
    assert (paths["backup"] / "backup-manifest.json").is_file()


def test_apply_cleans_staging_when_candidate_transform_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = fixture(tmp_path)
    plan = build_fixture_plan(paths)

    def failed_stage(candidate: Path, stage: Path) -> None:
        del candidate
        stage.mkdir()
        (stage / "partial").write_text("partial\n", encoding="utf-8")
        raise promotion.PromotionError("injected-stage-failure")

    monkeypatch.setattr(promotion, "stage_canonical", failed_stage)
    with pytest.raises(promotion.PromotionError, match="injected-stage-failure"):
        promotion.apply_plan(plan, paths["backup"], installer=copying_installer)

    assert not list((paths["repo"] / "skills").glob(".research-playbook-promotion-*"))
    assert not paths["backup"].exists()


def test_apply_cleans_partial_backup_when_backup_creation_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = fixture(tmp_path)
    plan = build_fixture_plan(paths)

    def failed_backup(tracked: dict, backup_root: Path, planned: dict) -> dict:
        del tracked, planned
        backup_root.mkdir(parents=True)
        (backup_root / "partial").write_text("partial\n", encoding="utf-8")
        raise OSError("injected-backup-failure")

    monkeypatch.setattr(promotion, "create_backup", failed_backup)
    with pytest.raises(OSError, match="injected-backup-failure"):
        promotion.apply_plan(plan, paths["backup"], installer=copying_installer)

    assert not paths["backup"].exists()
    assert not list((paths["repo"] / "skills").glob(".research-playbook-promotion-*"))
