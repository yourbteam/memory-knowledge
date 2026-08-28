#!/usr/bin/env python3
"""Promote the validated plan playbook candidate into the canonical skill."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Callable, Sequence


SCHEMA_VERSION = 1
CANONICAL = "plan-playbook"
CANDIDATE = "plan-playbook-v2"
PLAN_GATES = (
    "validated-practical-scenarios",
    "canonical-source-replacement",
    "candidate-alias-retirement",
    "canonical-routing-and-install",
    "rollback-and-validation-evidence",
    "fresh-canonical-runtime-smoke",
)
LIVE_SLOT_LABEL = "plan-playbook-canonical-routing-smoke"
TRUSTED_REPO_ROOT = Path(__file__).resolve().parents[1]
TRUSTED_INSTALLED_ROOTS = (
    (Path.home() / ".codex/skills").resolve(),
    (Path.home() / ".claude/skills").resolve(),
)
TARGET_REPO_ROOT = (Path.home() / "agentic-trading").resolve()
PRACTICAL_TASK_ROOT = TRUSTED_REPO_ROOT / "Tasks/plan-playbook-assessment-v2"
TRUSTED_SCENARIOS: dict[str, dict[str, Any]] = {
    "news-sweep-output-validation": {
        "repository": str(TARGET_REPO_ROOT),
        "plan_path": str(PRACTICAL_TASK_ROOT / "practical-scenario-1-plan.md"),
        "allowed_paths": [
            "tools/news_sweep_collector.py",
            "tests/test_news_sweep_collector.py",
        ],
        "focused_command": [
            str(TARGET_REPO_ROOT / ".venv/bin/python"), "-m", "pytest", "-q",
            "tests/test_news_sweep_collector.py",
        ],
        "full_command": ["make", "test", "PYTHON=.venv/bin/python"],
        "review_path": str(PRACTICAL_TASK_ROOT / "practical-scenario-1-review.json"),
    },
    "regime-aware-gatherer-time-stops": {
        "repository": str(TARGET_REPO_ROOT),
        "plan_path": str(PRACTICAL_TASK_ROOT / "practical-scenario-2-plan.md"),
        "allowed_paths": [
            "tools/shared_utils.py",
            "tools/morning_gatherer.py",
            "tools/exit_review_gatherer.py",
            "tests/test_gatherer_regime_time_stops.py",
            "tools/harness/datastore.py",
            "tests/harness/test_harness_datastore.py",
        ],
        "focused_command": [
            str(TARGET_REPO_ROOT / ".venv/bin/python"), "-m", "pytest", "-q",
            "tests/test_gatherer_regime_time_stops.py",
            "tests/test_strategy_improvements.py",
            "tests/harness/test_harness_datastore.py",
        ],
        "full_command": ["make", "test", "PYTHON=.venv/bin/python"],
        "review_path": str(PRACTICAL_TASK_ROOT / "practical-scenario-2-review.json"),
    },
}


class PromotionError(RuntimeError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    for item in sorted(
        candidate for candidate in path.rglob("*")
        if candidate.is_file()
        and "__pycache__" not in candidate.parts
        and candidate.suffix != ".pyc"
    ):
        digest.update(item.relative_to(path).as_posix().encode() + b"\0")
        digest.update(item.read_bytes())
    return digest.hexdigest()


def path_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"kind": "absent", "sha256": None}
    if path.is_dir():
        return {"kind": "tree", "sha256": tree_hash(path)}
    if path.is_file():
        return {"kind": "file", "sha256": sha256_file(path)}
    raise PromotionError(f"unsupported-path-kind:{path}")


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PromotionError(f"invalid-json:{path}") from exc
    if not isinstance(value, dict):
        raise PromotionError(f"json-object-required:{path}")
    return value


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def write_json(path: Path, value: dict[str, Any]) -> None:
    atomic_write(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def load_evaluator(repo_root: Path) -> Any:
    path = repo_root / "scripts/evaluate_plan_playbook_v2.py"
    spec = importlib.util.spec_from_file_location("promotion_plan_evaluator", path)
    if spec is None or spec.loader is None:
        raise PromotionError("evaluator-import-failed")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_score(repo_root: Path, score_path: Path) -> dict[str, Any]:
    try:
        receipt = load_evaluator(repo_root).validate_score(score_path)
    except Exception as exc:
        raise PromotionError(f"candidate-score-invalid:{type(exc).__name__}") from exc
    score = read_json(score_path)
    if score.get("all_passed") is not True or receipt.get("valid") is not True:
        raise PromotionError("candidate-score-not-pass")
    return receipt


def validate_practical_evidence(repo_root: Path, evidence_path: Path) -> dict[str, Any]:
    evidence = read_json(evidence_path)
    if set(evidence) != {
        "schema_version", "candidate_tree_sha256", "scenarios", "all_passed"
    }:
        raise PromotionError("practical-evidence-schema-invalid")
    if evidence.get("schema_version") != 1 or evidence.get("all_passed") is not True:
        raise PromotionError("practical-evidence-not-pass")
    candidate_hash = tree_hash(repo_root / "skills" / CANDIDATE)
    if evidence.get("candidate_tree_sha256") != candidate_hash:
        raise PromotionError("practical-evidence-candidate-mismatch")
    scenarios = evidence.get("scenarios")
    if not isinstance(scenarios, list) or len(scenarios) < 2:
        raise PromotionError("practical-evidence-scenarios-incomplete")
    required = {
        "scenario_id", "repository", "plan_path", "plan_sha256", "allowed_paths",
        "implementation_files", "focused_command", "full_command", "review_path",
        "review_sha256", "verdict",
    }
    ids: set[str] = set()
    validation_records: list[dict[str, Any]] = []
    for scenario in scenarios:
        if not isinstance(scenario, dict) or set(scenario) != required:
            raise PromotionError("practical-scenario-schema-invalid")
        scenario_id = scenario.get("scenario_id")
        if not isinstance(scenario_id, str) or not scenario_id or scenario_id in ids:
            raise PromotionError("practical-scenario-identity-invalid")
        ids.add(scenario_id)
        contract = TRUSTED_SCENARIOS.get(scenario_id)
        if contract is None or any(
            scenario.get(field) != contract[field]
            for field in (
                "repository", "plan_path", "allowed_paths", "focused_command",
                "full_command", "review_path",
            )
        ):
            raise PromotionError(f"practical-scenario-contract-mismatch:{scenario_id}")
        plan_path = Path(str(scenario.get("plan_path", "")))
        allowed_paths = scenario.get("allowed_paths")
        repository = Path(str(scenario.get("repository", "")))
        implementation_files = scenario.get("implementation_files")
        commands = (scenario.get("focused_command"), scenario.get("full_command"))
        review_path = Path(str(scenario.get("review_path", "")))
        review = read_json(review_path) if review_path.is_file() else {}
        implementation_valid = (
            isinstance(implementation_files, list)
            and len(implementation_files) == len(allowed_paths or [])
            and all(isinstance(item, dict) for item in implementation_files)
            and {item.get("path") for item in implementation_files} == set(allowed_paths or [])
            and all(
                set(item) == {"path", "sha256"}
                and (repository / item["path"]).is_file()
                and sha256_file(repository / item["path"]) == item["sha256"]
                for item in implementation_files
            )
        )
        review_valid = (
            set(review) == {
                "schema_version", "scenario_id", "repository", "reviewer_agent_id",
                "reviewed_files", "findings", "verdict",
            }
            and review.get("schema_version") == 1
            and review.get("scenario_id") == scenario_id
            and Path(str(review.get("repository", ""))).resolve() == repository.resolve()
            and isinstance(review.get("reviewer_agent_id"), str)
            and bool(review.get("reviewer_agent_id"))
            and isinstance(review.get("reviewed_files"), list)
            and set(review["reviewed_files"]) == set(allowed_paths or [])
            and review.get("findings") == []
            and review.get("verdict") == "PASS"
        )
        if (
            not plan_path.is_file()
            or sha256_file(plan_path) != scenario.get("plan_sha256")
            or not isinstance(allowed_paths, list)
            or not allowed_paths
            or any(not isinstance(path, str) or not path for path in allowed_paths)
            or not repository.is_dir()
            or not implementation_valid
            or any(
                not isinstance(command, list)
                or not command
                or any(not isinstance(argument, str) or not argument for argument in command)
                for command in commands
            )
            or not review_path.is_file()
            or sha256_file(review_path) != scenario.get("review_sha256")
            or not review_valid
            or scenario.get("verdict") != "PASS"
        ):
            raise PromotionError(f"practical-scenario-not-pass:{scenario_id}")
        command_records: list[dict[str, Any]] = []
        for label, command in zip(("focused", "full"), commands, strict=True):
            result = subprocess.run(
                command, cwd=repository, capture_output=True, text=False,
                check=False, timeout=1800,
            )
            command_records.append({
                "label": label,
                "argv": command,
                "exit_code": result.returncode,
                "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(),
                "stderr_sha256": hashlib.sha256(result.stderr).hexdigest(),
            })
            if result.returncode != 0:
                raise PromotionError(f"practical-scenario-command-failed:{scenario_id}:{label}")
        validation_records.append({
            "scenario_id": scenario_id,
            "implementation_files": implementation_files,
            "review_sha256": scenario["review_sha256"],
            "commands": command_records,
        })
    return {
        "valid": True,
        "scenario_count": len(scenarios),
        "scenario_ids": sorted(ids),
        "validation_records": validation_records,
    }


def tracked_paths(repo_root: Path, installed_root: Path) -> dict[str, Path]:
    return {
        "canonical_source": repo_root / "skills" / CANONICAL,
        "candidate_source": repo_root / "skills" / CANDIDATE,
        "managed_manifest": repo_root / "skills/managed-skills.txt",
        "evaluator": repo_root / "scripts/evaluate_plan_playbook_v2.py",
        "plan_tests": repo_root / "tests/test_plan_playbook_v2.py",
        "plan_attempt_tests": repo_root / "tests/test_plan_playbook_v2_attempt_policy.py",
        "plan_authority_tests": repo_root / "tests/test_plan_playbook_v2_authority.py",
        "plan_continuation_tests": repo_root / "tests/test_plan_playbook_v2_continuation.py",
        "plan_evaluator_tests": repo_root / "tests/test_plan_playbook_v2_evaluator.py",
        "plan_lifecycle_tests": repo_root / "tests/test_plan_playbook_v2_package_lifecycle.py",
        "plan_revision_tests": repo_root / "tests/test_plan_playbook_v2_revision_recovery.py",
        "skill_contract_tests": repo_root / "tests/test_skill_contracts.py",
        "validator_tests": repo_root / "tests/test_validate_skills.py",
        "legacy_fixture": repo_root / "tests/fixtures/plan-playbook-legacy",
        "task_workflow_source": repo_root / "skills/task-workflow/SKILL.md",
        "installed_canonical": installed_root / CANONICAL,
        "installed_candidate": installed_root / CANDIDATE,
        "installed_shared": installed_root / "_shared",
        "installed_research": installed_root / "research-playbook",
        "installed_task_workflow": installed_root / "task-workflow",
    }


def validate_operation_roots(repo_root: Path, installed_root: Path) -> None:
    if repo_root.resolve() != TRUSTED_REPO_ROOT:
        raise PromotionError("untrusted-repository-root")
    if installed_root.expanduser().resolve() not in TRUSTED_INSTALLED_ROOTS:
        raise PromotionError("untrusted-installed-root")


def validate_plan_paths(plan: dict[str, Any]) -> dict[str, Path]:
    repo_root = Path(plan["repo_root"]).resolve()
    installed_root = Path(plan["installed_root"]).expanduser().resolve()
    validate_operation_roots(repo_root, installed_root)
    expected = tracked_paths(repo_root, installed_root)
    supplied = {
        name: Path(item["path"]).expanduser().resolve()
        for name, item in plan["paths"].items()
    }
    if supplied != expected:
        raise PromotionError("plan-path-set-mismatch")
    return supplied


def _assert_candidate_inputs(paths: dict[str, Path]) -> None:
    for name in (
        "canonical_source",
        "candidate_source",
        "managed_manifest",
        "evaluator",
        "plan_tests",
        "plan_attempt_tests",
        "plan_authority_tests",
        "plan_continuation_tests",
        "plan_evaluator_tests",
        "plan_lifecycle_tests",
        "plan_revision_tests",
        "skill_contract_tests",
        "validator_tests",
        "task_workflow_source",
    ):
        if not paths[name].exists():
            raise PromotionError(f"required-path-missing:{name}")
    skill = (paths["candidate_source"] / "SKILL.md").read_text(encoding="utf-8")
    if "name: plan-playbook-v2\n" not in skill:
        raise PromotionError("candidate-identity-mismatch")
    managed = [
        line.strip() for line in paths["managed_manifest"].read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if managed.count(CANONICAL) != 1 or managed.count(CANDIDATE) != 1:
        raise PromotionError("managed-manifest-precondition-failed")


def build_plan(
    repo_root: Path,
    installed_root: Path,
    practical_evidence_path: Path,
    *,
    score_path: Path | None = None,
    validation_receipt: Path | None = None,
    live_receipt: Path | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    installed_root = installed_root.expanduser().resolve()
    validate_operation_roots(repo_root, installed_root)
    practical_evidence_path = practical_evidence_path.resolve()
    paths = tracked_paths(repo_root, installed_root)
    _assert_candidate_inputs(paths)
    practical_receipt = validate_practical_evidence(repo_root, practical_evidence_path)
    plan: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "verdict": "READY",
        "repo_root": str(repo_root),
        "installed_root": str(installed_root),
        "practical_evidence_path": str(practical_evidence_path),
        "practical_evidence_sha256": sha256_file(practical_evidence_path),
        "practical_evidence_validation": practical_receipt,
        "secondary_score_path": str(score_path.resolve()) if score_path else None,
        "secondary_score_sha256": sha256_file(score_path.resolve()) if score_path else None,
        "secondary_score_validation": validate_score(repo_root, score_path.resolve()) if score_path else None,
        "paths": {
            name: {"path": str(path), "before": path_state(path)}
            for name, path in paths.items()
        },
        "completion_gates": list(PLAN_GATES),
        "validation_receipt": str(
            (validation_receipt or Path("/private/tmp/plan-playbook-promotion-validation.json")).resolve()
        ),
        "live_receipt": str(
            (live_receipt or Path("/private/tmp/plan-playbook-canonical-live-smoke.json")).resolve()
        ),
    }
    plan["plan_sha256"] = hashlib.sha256(canonical_bytes(plan)).hexdigest()
    return plan


def load_plan(path: Path) -> dict[str, Any]:
    plan = read_json(path)
    expected_hash = plan.pop("plan_sha256", None)
    observed_hash = hashlib.sha256(canonical_bytes(plan)).hexdigest()
    plan["plan_sha256"] = expected_hash
    if plan.get("schema_version") != SCHEMA_VERSION or plan.get("verdict") != "READY":
        raise PromotionError("invalid-plan-schema")
    if expected_hash != observed_hash:
        raise PromotionError("plan-hash-mismatch")
    if tuple(plan.get("completion_gates", [])) != PLAN_GATES:
        raise PromotionError("plan-gates-mismatch")
    return plan


def validate_preconditions(plan: dict[str, Any]) -> dict[str, Path]:
    paths = validate_plan_paths(plan)
    evidence_path = Path(plan["practical_evidence_path"])
    if sha256_file(evidence_path) != plan["practical_evidence_sha256"]:
        raise PromotionError("practical-evidence-changed-after-plan")
    validate_practical_evidence(Path(plan["repo_root"]), evidence_path)
    if plan.get("secondary_score_path") is not None:
        score_path = Path(plan["secondary_score_path"])
        if sha256_file(score_path) != plan["secondary_score_sha256"]:
            raise PromotionError("secondary-score-changed-after-plan")
        validate_score(Path(plan["repo_root"]), score_path)
    for name, path in paths.items():
        if path_state(path) != plan["paths"][name]["before"]:
            raise PromotionError(f"path-changed-after-plan:{name}")
    return paths


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise PromotionError(f"rewrite-precondition-failed:{label}")
    return text.replace(old, new, 1)


def stage_canonical(candidate: Path, stage: Path) -> None:
    shutil.copytree(candidate, stage, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    skill_path = stage / "SKILL.md"
    skill = skill_path.read_text(encoding="utf-8")
    skill = _replace_once(skill, "name: plan-playbook-v2\n", "name: plan-playbook\n", "skill-name")
    description = (
        "description: Use when a goal must become a controller-bound, decision-complete implementation "
        "plan before code is written. Freeze grounded evidence, require the behavioral boundary matrix, "
        "and harden one plan revision through verify-plan plus independent internal-readiness, requirements-"
        "coverage, and requirements-satisfaction lenses. Do not use for open-ended research, code changes, "
        "or diff review."
    )
    skill, count = re.subn(r"^description: .+$", description, skill, count=1, flags=re.MULTILINE)
    if count != 1:
        raise PromotionError("rewrite-precondition-failed:skill-description")
    skill = _replace_once(skill, "# Plan Playbook V2 Candidate", "# Plan Playbook", "skill-title")
    skill = _replace_once(
        skill,
        "This candidate is explicit-only. Do not select it from an ordinary planning request and do not replace or modify canonical `plan-playbook` routing during candidate evaluation.\n\n",
        "",
        "promotion-boundary",
    )
    skill = _replace_once(
        skill,
        "The parent must invoke this candidate directly; never delegate the whole Planner v2 run to a",
        "The parent must invoke this playbook directly; never delegate the whole planning run to a",
        "candidate-ownership",
    )
    skill = _replace_once(
        skill,
        "Use [evaluation.md](references/evaluation.md) for candidate evaluation. Promotion, canonical replacement, installed-skill replacement, secrets, commits, and pushes require their separately authorized operations.",
        "The comparison contract formerly stored in `references/evaluation.md` is historical promotion evidence, not a runtime planning gate. Secrets, commits, pushes, deployments, and external messages retain their separate approval boundaries.",
        "evaluation-note",
    )
    skill_path.write_text(skill, encoding="utf-8")

    (stage / "agents/openai.yaml").write_text(
        'interface:\n'
        '  display_name: "Plan Playbook"\n'
        '  short_description: "Controller-backed implementation planning"\n'
        '  default_prompt: "Use $plan-playbook to produce and harden a decision-complete implementation plan package."\n',
        encoding="utf-8",
    )
    evaluation = stage / "references/evaluation.md"
    evaluation.unlink()
    routing_path = stage / "references/approval-and-routing.md"
    routing = routing_path.read_text(encoding="utf-8")
    routing = _replace_once(
        routing,
        "The candidate is selected only by explicit `$plan-playbook-v2` invocation. Ordinary planning continues to select canonical `plan-playbook` during evaluation. The candidate performs planning only: it does not implement, review code, promote itself, replace installed skills, commit, or push.",
        "Ordinary planning selects canonical `$plan-playbook`. The playbook performs planning only: it does not implement, review code, replace installed skills, commit, or push.",
        "routing-reference",
    )
    routing = routing.replace("consume the candidate package", "consume the canonical package")
    routing_path.write_text(routing, encoding="utf-8")
    skill_text = skill_path.read_text(encoding="utf-8")
    metadata_text = (stage / "agents/openai.yaml").read_text(encoding="utf-8")
    if "$plan-playbook-v2" in skill_text + metadata_text or "explicit-only" in skill_text + metadata_text:
        raise PromotionError("candidate-routing-remains-in-canonical")


def transformed_files(paths: dict[str, Path]) -> dict[str, str]:
    managed = paths["managed_manifest"].read_text(encoding="utf-8")
    managed_lines = managed.splitlines()
    if managed_lines.count(CANDIDATE) != 1:
        raise PromotionError("managed-candidate-line-mismatch")
    managed_text = "\n".join(line for line in managed_lines if line != CANDIDATE) + "\n"

    evaluator = paths["evaluator"].read_text(encoding="utf-8").replace(
        "skills/plan-playbook-v2/scripts/plan_package.py",
        "skills/plan-playbook/scripts/plan_package.py",
    ).replace(
        'TREE_SHA256_V1(REPO_ROOT / "skills/plan-playbook-v2")',
        'TREE_SHA256_V1(REPO_ROOT / "skills/plan-playbook")',
    )
    if "skills/plan-playbook-v2/" in evaluator:
        raise PromotionError("evaluator-candidate-path-remains")

    transformed: dict[str, str] = {
        "managed_manifest": managed_text,
        "evaluator": evaluator,
    }
    for name in (
        "plan_tests", "plan_attempt_tests", "plan_authority_tests",
        "plan_continuation_tests", "plan_evaluator_tests", "plan_lifecycle_tests",
        "plan_revision_tests", "skill_contract_tests",
    ):
        text = paths[name].read_text(encoding="utf-8")
        text = text.replace("skills/plan-playbook-v2/", "skills/plan-playbook/")
        text = text.replace('ROOT/"plan-playbook-v2"', 'ROOT/"plan-playbook"')
        text = text.replace('ROOT / "skills/plan-playbook-v2"', 'ROOT / "skills/plan-playbook"')
        if name == "skill_contract_tests":
            text = text.replace(
                'self.assertNotIn("skills/plan-playbook/",text)',
                'self.assertNotIn("skills/plan-playbook-v2/",text)',
            )
        transformed[name] = text
    transformed["validator_tests"] = paths["validator_tests"].read_text(encoding="utf-8")
    transformed["task_workflow_source"] = (
        paths["candidate_source"] / "integration/task-workflow.SKILL.md"
    ).read_text(encoding="utf-8")
    return transformed


def _copy_path(source: Path, destination: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def create_backup(paths: dict[str, Path], backup_root: Path, plan: dict[str, Any]) -> dict[str, Any]:
    if backup_root.exists():
        raise PromotionError("backup-root-already-exists")
    backup_root.mkdir(parents=True)
    entries: dict[str, Any] = {}
    for name, path in paths.items():
        before = path_state(path)
        entry = {"path": str(path), "before": before, "backup": None}
        if before["kind"] != "absent":
            destination = backup_root / "paths" / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            _copy_path(path, destination)
            if path_state(destination) != before:
                raise PromotionError(f"backup-hash-mismatch:{name}")
            entry["backup"] = str(destination)
        entries[name] = entry
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "plan_sha256": plan["plan_sha256"],
        "entries": entries,
    }
    write_json(backup_root / "backup-manifest.json", manifest)
    return manifest


def restore_backup(manifest: dict[str, Any]) -> None:
    for name, entry in reversed(list(manifest["entries"].items())):
        path = Path(entry["path"])
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
        if entry["before"]["kind"] != "absent":
            _copy_path(Path(entry["backup"]), path)
        if path_state(path) != entry["before"]:
            raise PromotionError(f"rollback-hash-mismatch:{name}")


def load_bound_manifest(plan: dict[str, Any], backup_root: Path) -> dict[str, Any]:
    validate_plan_paths(plan)
    manifest = read_json(backup_root / "backup-manifest.json")
    if set(manifest) != {"schema_version", "plan_sha256", "entries"}:
        raise PromotionError("backup-manifest-schema-invalid")
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("plan_sha256") != plan["plan_sha256"]
    ):
        raise PromotionError("backup-plan-mismatch")
    expected = {
        name: (str(Path(item["path"]).expanduser().resolve()), item["before"])
        for name, item in plan["paths"].items()
    }
    entries = manifest.get("entries")
    if not isinstance(entries, dict) or set(entries) != set(expected):
        raise PromotionError("backup-path-set-mismatch")
    for name, (path, before) in expected.items():
        entry = entries[name]
        expected_backup = (
            None if before["kind"] == "absent"
            else str(backup_root / "paths" / name)
        )
        if (
            not isinstance(entry, dict)
            or set(entry) != {"path", "before", "backup"}
            or entry.get("path") != path
            or entry.get("before") != before
            or entry.get("backup") != expected_backup
            or (expected_backup is not None and path_state(Path(expected_backup)) != before)
        ):
            raise PromotionError(f"backup-entry-mismatch:{name}")
    return manifest


def write_journal(
    backup_root: Path,
    plan: dict[str, Any],
    state: str,
    stage_path: Path | None = None,
) -> None:
    write_json(backup_root / "promotion-journal.json", {
        "schema_version": 1,
        "plan_sha256": plan["plan_sha256"],
        "state": state,
        "stage_path": str(stage_path) if stage_path is not None else None,
    })


def load_bound_journal(plan: dict[str, Any], backup_root: Path) -> dict[str, Any]:
    journal = read_json(backup_root / "promotion-journal.json")
    if (
        set(journal) != {"schema_version", "plan_sha256", "state", "stage_path"}
        or journal.get("schema_version") != 1
        or journal.get("plan_sha256") != plan["plan_sha256"]
    ):
        raise PromotionError("promotion-journal-invalid")
    stage_value = journal.get("stage_path")
    if stage_value is not None:
        stage = Path(str(stage_value)).resolve()
        skills_root = (Path(plan["repo_root"]) / "skills").resolve()
        if (
            stage.parent != skills_root
            or not stage.name.startswith(".plan-playbook-promotion-")
        ):
            raise PromotionError("promotion-journal-stage-invalid")
    return journal


def cleanup_recorded_stage(plan: dict[str, Any], journal: dict[str, Any]) -> None:
    stage_value = journal.get("stage_path")
    if stage_value is None:
        return
    stage = Path(stage_value)
    if stage.is_dir():
        shutil.rmtree(stage)
    elif stage.exists():
        stage.unlink()


def load_installer(repo_root: Path) -> Any:
    path = repo_root / "working-agreement/install_skills.py"
    spec = importlib.util.spec_from_file_location("promotion_install_skills", path)
    if spec is None or spec.loader is None:
        raise PromotionError("installer-import-failed")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def install_canonical(repo_root: Path, installed_root: Path, state_dir: Path) -> None:
    installer = load_installer(repo_root)
    installer.install(
        repo_root / "skills",
        repo_root / "skills/managed-skills.txt",
        [installed_root],
        state_dir,
        only=["_shared", CANONICAL, "research-playbook", "task-workflow"],
    )


def apply_plan(
    plan: dict[str, Any],
    backup_root: Path,
    *,
    installer: Callable[[Path, Path, Path], None] = install_canonical,
) -> dict[str, Any]:
    paths = validate_preconditions(plan)
    repo_root = Path(plan["repo_root"])
    installed_root = Path(plan["installed_root"])
    backup_root = backup_root.expanduser().resolve()
    transformed = transformed_files(paths)
    stage = repo_root / "skills" / f".plan-playbook-promotion-{uuid.uuid4().hex}"
    manifest: dict[str, Any] | None = None
    try:
        manifest = create_backup(paths, backup_root, plan)
        write_journal(backup_root, plan, "BACKED_UP", stage)
        stage_canonical(paths["candidate_source"], stage)
        shutil.copytree(paths["canonical_source"], paths["legacy_fixture"])
        shutil.rmtree(paths["canonical_source"])
        os.replace(stage, paths["canonical_source"])
        write_journal(backup_root, plan, "SOURCE_REPLACED", stage)
        for name, content in transformed.items():
            atomic_write(paths[name], content)
        write_journal(backup_root, plan, "FILES_REWRITTEN", stage)
        shutil.rmtree(paths["candidate_source"])
        write_journal(backup_root, plan, "CANDIDATE_RETIRED", stage)
        installer(repo_root, installed_root, backup_root / "installer-state")
        if paths["installed_candidate"].exists():
            shutil.rmtree(paths["installed_candidate"])
        source_installed_pairs = {
            "installed_shared": repo_root / "skills/_shared",
            "installed_canonical": paths["canonical_source"],
            "installed_research": repo_root / "skills/research-playbook",
            "installed_task_workflow": repo_root / "skills/task-workflow",
        }
        for installed_name, source in source_installed_pairs.items():
            if tree_hash(paths[installed_name]) != tree_hash(source):
                raise PromotionError(f"installed-tree-hash-mismatch:{installed_name}")
        write_journal(backup_root, plan, "INSTALLED", stage)
        structural = verify_structure(plan, backup_root, require_receipts=False)
        receipt = {
            "schema_version": SCHEMA_VERSION,
            "ok": True,
            "plan_sha256": plan["plan_sha256"],
            "canonical_tree_sha256": tree_hash(paths["canonical_source"]),
            "structural_gates": structural["gates"],
        }
        write_json(backup_root / "apply-receipt.json", receipt)
        write_journal(backup_root, plan, "APPLIED", stage)
        return receipt
    except BaseException as exc:
        if stage.exists():
            shutil.rmtree(stage)
        if manifest is not None:
            try:
                restore_backup(manifest)
            except BaseException as rollback_exc:
                raise PromotionError(
                    f"promotion-failed-and-rollback-failed:{type(exc).__name__}:{type(rollback_exc).__name__}"
                ) from rollback_exc
        elif backup_root.exists():
            shutil.rmtree(backup_root)
        raise
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def _validate_backup(plan: dict[str, Any], backup_root: Path) -> bool:
    try:
        manifest = load_bound_manifest(plan, backup_root)
    except (OSError, PromotionError):
        return False
    for entry in manifest.get("entries", {}).values():
        before = entry.get("before", {})
        if before.get("kind") == "absent":
            if entry.get("backup") is not None:
                return False
            continue
        backup = Path(str(entry.get("backup")))
        if path_state(backup) != before:
            return False
    return True


def _validation_receipt_ok(plan: dict[str, Any], canonical_hash: str) -> bool:
    receipt = read_json(Path(plan["validation_receipt"]))
    expected_commands = validation_commands(Path(plan["repo_root"]))
    commands = receipt.get("commands")
    return (
        receipt.get("schema_version") == 1
        and receipt.get("plan_sha256") == plan["plan_sha256"]
        and receipt.get("all_passed") is True
        and isinstance(commands, list)
        and len(commands) == len(expected_commands)
        and all(
            item.get("sequence") == sequence
            and item.get("argv") == argv
            and item.get("exit_code") == 0
            for sequence, (item, argv) in enumerate(
                zip(commands, expected_commands, strict=True), 1
            )
        )
        and receipt.get("canonical_tree_sha256") == canonical_hash
    )


def _live_receipt_ok(plan: dict[str, Any], canonical_hash: str) -> bool:
    receipt = read_json(Path(plan["live_receipt"]))
    input_path = Path(str(receipt.get("agent_input_path", "")))
    output_path = Path(str(receipt.get("agent_output_path", "")))
    ledger_path = Path(str(receipt.get("runtime_slot_ledger_path", "")))
    try:
        ledger = read_json(ledger_path)
    except PromotionError:
        ledger = {}
    slots = ledger.get("slots", []) if isinstance(ledger, dict) else []
    matching_slots = [
        slot for slot in slots
        if isinstance(slot, dict)
        and slot.get("agent_id") == receipt.get("runtime_agent_id")
        and slot.get("label") == LIVE_SLOT_LABEL
    ] if isinstance(slots, list) else []
    runtime_slot = matching_slots[0] if len(matching_slots) == 1 else {}
    runtime_evidence = runtime_slot.get("evidence", {})
    if not isinstance(runtime_evidence, dict):
        runtime_evidence = {}
    expected_close_evidence = (
        "multi_agent-close-agent:completed:"
        + str(receipt.get("agent_output_sha256", ""))
    )
    return (
        receipt.get("schema_version") == 1
        and receipt.get("plan_sha256") == plan["plan_sha256"]
        and receipt.get("input_sha256") == receipt.get("agent_input_sha256")
        and input_path.is_file()
        and output_path.is_file()
        and sha256_file(input_path) == receipt.get("agent_input_sha256")
        and sha256_file(output_path) == receipt.get("agent_output_sha256")
        and isinstance(receipt.get("runtime_agent_id"), str)
        and bool(receipt.get("runtime_agent_id"))
        and ledger.get("version") == 2
        and runtime_slot.get("state") == "released"
        and isinstance(runtime_slot.get("completed_at"), int)
        and isinstance(runtime_slot.get("closed_at"), int)
        and isinstance(runtime_slot.get("released_at"), int)
        and runtime_evidence.get("close") == expected_close_evidence
        and receipt.get("selected_skill") == CANONICAL
        and receipt.get("invocation") is None
        and receipt.get("terminal_probe") in {"PRODUCE_DRAFT", "RETURN_TO_RESEARCH"}
        and receipt.get("canonical_tree_sha256") == canonical_hash
    )


def verify_structure(
    plan: dict[str, Any], backup_root: Path, *, require_receipts: bool = True
) -> dict[str, Any]:
    paths = {name: Path(item["path"]) for name, item in plan["paths"].items()}
    canonical_hash = tree_hash(paths["canonical_source"])
    managed = paths["managed_manifest"].read_text(encoding="utf-8").splitlines()
    canonical_text = "\n".join(
        item.read_text(encoding="utf-8")
        for item in paths["canonical_source"].rglob("*")
        if item.is_file() and "__pycache__" not in item.parts and item.suffix != ".pyc"
    )
    installed_text = "\n".join(
        item.read_text(encoding="utf-8")
        for item in paths["installed_canonical"].rglob("*")
        if item.is_file() and "__pycache__" not in item.parts and item.suffix != ".pyc"
    ) if paths["installed_canonical"].is_dir() else ""
    metadata = (paths["canonical_source"] / "agents/openai.yaml").read_text(encoding="utf-8")
    gates: dict[str, bool] = {
        "validated-practical-scenarios": (
            sha256_file(Path(plan["practical_evidence_path"]))
            == plan["practical_evidence_sha256"]
            and plan.get("practical_evidence_validation", {}).get("valid") is True
        ),
        "canonical-source-replacement": (
            canonical_hash is not None
            and (paths["canonical_source"] / "scripts/plan_package.py").is_file()
            and tree_hash(paths["legacy_fixture"]) == plan["paths"]["canonical_source"]["before"]["sha256"]
        ),
        "candidate-alias-retirement": (
            not paths["candidate_source"].exists()
            and not paths["installed_candidate"].exists()
            and "$plan-playbook-v2" not in canonical_text
            and "skills/plan-playbook-v2/" not in canonical_text
            and "$plan-playbook-v2" not in installed_text
            and "skills/plan-playbook-v2/" not in installed_text
            and CANDIDATE not in managed
        ),
        "canonical-routing-and-install": (
            managed.count(CANONICAL) == 1
            and tree_hash(paths["installed_canonical"]) == canonical_hash
            and tree_hash(paths["installed_task_workflow"]) == tree_hash(paths["task_workflow_source"].parent)
            and "$plan-playbook" in metadata
            and "allow_implicit_invocation: false" not in metadata
            and "skills/plan-playbook-v2/" not in paths["evaluator"].read_text(encoding="utf-8")
            and "skills/plan-playbook-v2/" not in paths["plan_tests"].read_text(encoding="utf-8")
        ),
        "rollback-and-validation-evidence": _validate_backup(plan, backup_root),
        "fresh-canonical-runtime-smoke": False,
    }
    if require_receipts:
        gates["rollback-and-validation-evidence"] = (
            gates["rollback-and-validation-evidence"]
            and _validation_receipt_ok(plan, str(canonical_hash))
        )
        gates["fresh-canonical-runtime-smoke"] = _live_receipt_ok(plan, str(canonical_hash))
    verdict = "PASS" if all(gates.values()) else "FAIL"
    return {
        "schema_version": SCHEMA_VERSION,
        "verdict": verdict,
        "matrix_complete": set(gates) == set(PLAN_GATES),
        "gates": gates,
        "canonical_tree_sha256": canonical_hash,
        "backup_root": str(backup_root),
    }


def cmd_plan(args: argparse.Namespace) -> dict[str, Any]:
    plan = build_plan(
        args.repo_root,
        args.installed_root,
        args.practical_evidence,
        score_path=args.score,
        validation_receipt=args.validation_receipt,
        live_receipt=args.live_receipt,
    )
    write_json(args.output, plan)
    return {
        "ok": True,
        "verdict": plan["verdict"],
        "plan": str(args.output.resolve()),
        "plan_sha256": plan["plan_sha256"],
        "completion_gates": plan["completion_gates"],
    }


def cmd_apply(args: argparse.Namespace) -> dict[str, Any]:
    plan = load_plan(args.plan)
    return apply_plan(plan, args.backup_root)


def validation_commands(repo_root: Path) -> list[list[str]]:
    focused = [
        "tests/test_plan_playbook_v2.py",
        "tests/test_plan_playbook_v2_attempt_policy.py",
        "tests/test_plan_playbook_v2_authority.py",
        "tests/test_plan_playbook_v2_continuation.py",
        "tests/test_plan_playbook_v2_evaluator.py",
        "tests/test_plan_playbook_v2_package_lifecycle.py",
        "tests/test_plan_playbook_v2_revision_recovery.py",
        "tests/test_skill_contracts.py",
        "tests/test_validate_skills.py",
        "tests/test_install_skills.py",
        "tests/test_agent_slot_ledger.py",
        "tests/test_promote_plan_playbook.py",
    ]
    return [
        [str(repo_root / "working-agreement/validate-skills.sh")],
        [str(repo_root / "scripts/run_pytest.sh"), *focused],
    ]


def rollback(plan: dict[str, Any], backup_root: Path, reason: str, out: Path) -> dict[str, Any]:
    manifest = load_bound_manifest(plan, backup_root)
    try:
        journal = load_bound_journal(plan, backup_root)
    except (OSError, PromotionError):
        journal = {}
    cleanup_recorded_stage(plan, journal)
    restore_backup(manifest)
    write_journal(backup_root, plan, "ROLLED_BACK")
    receipt = {
        "schema_version": 1,
        "plan_sha256": plan["plan_sha256"],
        "reason": reason,
        "all_restored": all(
            path_state(Path(item["path"])) == item["before"]
            for item in manifest["entries"].values()
        ),
    }
    write_json(out, receipt)
    return receipt


def cmd_validate(args: argparse.Namespace) -> dict[str, Any]:
    plan = load_plan(args.plan)
    backup_root = args.backup_root.resolve()
    records: list[dict[str, Any]] = []
    try:
        out = args.out.resolve()
        if out != Path(plan["validation_receipt"]):
            raise PromotionError("validation-receipt-path-mismatch")
        structural = verify_structure(plan, backup_root, require_receipts=False)
        if structural["verdict"] != "FAIL" or any(
            not value for key, value in structural["gates"].items()
            if key != "fresh-canonical-runtime-smoke"
        ):
            raise PromotionError("promotion-structure-invalid-before-validation")
        for sequence, argv in enumerate(validation_commands(Path(plan["repo_root"])), 1):
            result = subprocess.run(
                argv, cwd=plan["repo_root"], capture_output=True, text=False, check=False,
            )
            records.append({
                "sequence": sequence,
                "argv": argv,
                "exit_code": result.returncode,
                "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(),
                "stderr_sha256": hashlib.sha256(result.stderr).hexdigest(),
            })
            if result.returncode != 0:
                raise PromotionError(f"validation-command-failed:{sequence}")
        receipt = {
            "schema_version": 1,
            "plan_sha256": plan["plan_sha256"],
            "canonical_tree_sha256": tree_hash(Path(plan["repo_root"]) / "skills/plan-playbook"),
            "commands": records,
            "all_passed": True,
        }
        write_json(out, receipt)
        return receipt
    except BaseException:
        rollback(plan, backup_root, "VALIDATE_FAILED", backup_root / "rollback-receipt.json")
        raise


def cmd_record_live(args: argparse.Namespace) -> dict[str, Any]:
    plan = load_plan(args.plan)
    backup_root = args.backup_root.resolve()
    try:
        if not _validation_receipt_ok(plan, str(tree_hash(Path(plan["repo_root"]) / "skills/plan-playbook"))):
            raise PromotionError("validation-receipt-invalid")
        request = read_json(args.agent_input)
        output = read_json(args.agent_output)
        request_bytes = args.agent_input.resolve().read_bytes()
        ledger = read_json(args.slot_ledger.resolve())
        matching_slots = [
            slot for slot in ledger.get("slots", [])
            if isinstance(slot, dict)
            and slot.get("agent_id") == args.runtime_agent_id
            and slot.get("label") == LIVE_SLOT_LABEL
        ]
        if (
            ledger.get("version") != 2
            or len(matching_slots) != 1
            or matching_slots[0].get("state") != "completed"
            or not isinstance(matching_slots[0].get("completed_at"), int)
        ):
            raise PromotionError("live-agent-lifecycle-invalid")
        if (
        set(request) != {"schema_version", "request", "installed_root", "output_contract"}
        or request.get("schema_version") != 1
        or request.get("output_contract") != "PLAN_PLAYBOOK_LIVE_V1"
        or request.get("installed_root") != plan["installed_root"]
        or not isinstance(request.get("request"), str)
        or "plan-playbook" in request["request"].lower()
        ):
            raise PromotionError("live-agent-input-invalid")
        canonical_hash = str(tree_hash(Path(plan["repo_root"]) / "skills/plan-playbook"))
        if (
        set(output) != {
            "schema_version", "input_sha256", "invocation", "selected_skill",
            "selected_tree_sha256", "terminal_probe",
        }
        or output.get("schema_version") != 1
        or output.get("input_sha256") != hashlib.sha256(request_bytes).hexdigest()
        or output.get("invocation") is not None
        or output.get("selected_skill") != CANONICAL
        or output.get("selected_tree_sha256") != canonical_hash
        or output.get("terminal_probe") not in {"PRODUCE_DRAFT", "RETURN_TO_RESEARCH"}
        ):
            raise PromotionError("live-agent-output-invalid")
        receipt = {
            **output, "canonical_tree_sha256": canonical_hash,
            "plan_sha256": plan["plan_sha256"],
            "agent_input_path": str(args.agent_input.resolve()),
            "agent_output_path": str(args.agent_output.resolve()),
            "agent_input_sha256": hashlib.sha256(request_bytes).hexdigest(),
            "agent_output_sha256": sha256_file(args.agent_output.resolve()),
            "runtime_agent_id": args.runtime_agent_id,
            "runtime_slot_ledger_path": str(args.slot_ledger.resolve()),
        }
        out = args.out.resolve()
        if out != Path(plan["live_receipt"]):
            raise PromotionError("live-receipt-path-mismatch")
        write_json(out, receipt)
        return receipt
    except BaseException:
        rollback(plan, backup_root, "LIVE_RECORD_FAILED", backup_root / "rollback-receipt.json")
        raise


def cmd_verify(args: argparse.Namespace) -> dict[str, Any]:
    plan = load_plan(args.plan)
    backup_root = args.backup_root.resolve()
    try:
        result = verify_structure(plan, backup_root, require_receipts=True)
        if result["verdict"] != "PASS":
            raise PromotionError("promotion-verification-failed:" + ",".join(
                name for name, passed in result["gates"].items() if not passed
            ))
        return result
    except BaseException:
        rollback(plan, backup_root, "VERIFY_FAILED", backup_root / "rollback-receipt.json")
        raise


def cmd_abort(args: argparse.Namespace) -> dict[str, Any]:
    plan = load_plan(args.plan)
    return rollback(plan, args.backup_root.resolve(), args.reason_code, args.out.resolve())


def cmd_recover(args: argparse.Namespace) -> dict[str, Any]:
    plan = load_plan(args.plan)
    backup_root = args.backup_root.resolve()
    load_bound_manifest(plan, backup_root)
    try:
        journal = load_bound_journal(plan, backup_root)
    except (OSError, PromotionError):
        return rollback(plan, backup_root, "RECOVERED", args.out.resolve())
    if journal.get("state") != "APPLIED":
        return rollback(plan, backup_root, "RECOVERED", args.out.resolve())
    try:
        structural = verify_structure(plan, backup_root, require_receipts=False)
        applied = all(
            value for key, value in structural["gates"].items()
            if key != "fresh-canonical-runtime-smoke"
        )
    except (OSError, PromotionError):
        applied = False
    if applied:
        return {"schema_version": 1, "state": "APPLIED", "restored": False}
    return rollback(plan, backup_root, "RECOVERED", args.out.resolve())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--repo-root", type=Path, required=True)
    plan.add_argument("--installed-root", type=Path, required=True)
    plan.add_argument("--practical-evidence", type=Path, required=True)
    plan.add_argument("--score", type=Path)
    plan.add_argument("--output", type=Path, required=True)
    plan.add_argument("--validation-receipt", type=Path)
    plan.add_argument("--live-receipt", type=Path)
    plan.set_defaults(func=cmd_plan)
    apply = sub.add_parser("apply")
    apply.add_argument("--plan", type=Path, required=True)
    apply.add_argument("--backup-root", type=Path, required=True)
    apply.set_defaults(func=cmd_apply)
    validate = sub.add_parser("validate")
    validate.add_argument("--plan", type=Path, required=True)
    validate.add_argument("--backup-root", type=Path, required=True)
    validate.add_argument("--out", type=Path, required=True)
    validate.set_defaults(func=cmd_validate)
    live = sub.add_parser("record-live")
    live.add_argument("--plan", type=Path, required=True)
    live.add_argument("--backup-root", type=Path, required=True)
    live.add_argument("--agent-input", type=Path, required=True)
    live.add_argument("--agent-output", type=Path, required=True)
    live.add_argument("--runtime-agent-id", required=True)
    live.add_argument("--slot-ledger", type=Path, required=True)
    live.add_argument("--out", type=Path, required=True)
    live.set_defaults(func=cmd_record_live)
    verify = sub.add_parser("verify")
    verify.add_argument("--plan", type=Path, required=True)
    verify.add_argument("--backup-root", type=Path, required=True)
    verify.set_defaults(func=cmd_verify)
    abort = sub.add_parser("abort")
    abort.add_argument("--plan", type=Path, required=True)
    abort.add_argument("--backup-root", type=Path, required=True)
    abort.add_argument("--reason-code", required=True)
    abort.add_argument("--out", type=Path, required=True)
    abort.set_defaults(func=cmd_abort)
    recover = sub.add_parser("recover")
    recover.add_argument("--plan", type=Path, required=True)
    recover.add_argument("--backup-root", type=Path, required=True)
    recover.add_argument("--out", type=Path, required=True)
    recover.set_defaults(func=cmd_recover)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        print(json.dumps(args.func(args), sort_keys=True))
        return 0
    except PromotionError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 3
    except OSError as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__}, sort_keys=True), file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
