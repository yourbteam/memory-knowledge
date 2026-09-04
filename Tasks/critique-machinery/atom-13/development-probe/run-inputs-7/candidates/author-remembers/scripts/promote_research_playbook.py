#!/usr/bin/env python3
"""Promote the validated research playbook candidate into the canonical skill."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Callable, Sequence


SCHEMA_VERSION = 1
CANONICAL = "research-playbook"
CANDIDATE = "research-playbook-v2"
PLAN_GATES = (
    "validated-candidate-score",
    "canonical-source-replacement",
    "candidate-alias-retirement",
    "canonical-routing-and-install",
    "rollback-and-validation-evidence",
    "fresh-canonical-runtime-smoke",
)


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
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
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
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def write_json(path: Path, value: dict[str, Any]) -> None:
    atomic_write(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def validate_score(score: dict[str, Any]) -> dict[str, Any]:
    predicates = score.get("predicates")
    if score.get("schema_version") != 1 or score.get("verdict") != "PASS":
        raise PromotionError("candidate-score-not-pass")
    if score.get("matrix_complete") is not True or not isinstance(predicates, dict):
        raise PromotionError("candidate-matrix-incomplete")
    required = {
        "budget_compliance",
        "complete_critical_recall",
        "planner_pass_every_case",
        "v2_false_material_gaps_no_worse_than_legacy",
        "zero_invented_evidence",
        "zero_scope_maturity_drift",
    }
    if set(predicates) != required or any(
        not isinstance(predicates[name], dict) or predicates[name].get("pass") is not True
        for name in required
    ):
        raise PromotionError("candidate-predicate-failed")
    recall = predicates["complete_critical_recall"]
    if (
        recall.get("ratio") != 1.0
        or not isinstance(recall.get("total"), int)
        or recall["total"] <= 0
        or recall.get("recalled") != recall["total"]
    ):
        raise PromotionError("candidate-critical-recall-incomplete")
    invented = predicates["zero_invented_evidence"]
    drift = predicates["zero_scope_maturity_drift"]
    if invented.get("invented_claim_count") != 0 or invented.get("invented_evidence_count") != 0:
        raise PromotionError("candidate-invented-evidence")
    if drift.get("scope_drift_count") != 0 or drift.get("maturity_drift_count") != 0:
        raise PromotionError("candidate-scope-maturity-drift")
    return {name: predicates[name] for name in sorted(required)}


def tracked_paths(repo_root: Path, installed_root: Path) -> dict[str, Path]:
    return {
        "canonical_source": repo_root / "skills" / CANONICAL,
        "candidate_source": repo_root / "skills" / CANDIDATE,
        "managed_manifest": repo_root / "skills/managed-skills.txt",
        "evaluator": repo_root / "scripts/evaluate_research_playbook_v2.py",
        "research_tests": repo_root / "tests/test_research_playbook_v2.py",
        "validator_tests": repo_root / "tests/test_validate_skills.py",
        "legacy_fixture": repo_root / "tests/fixtures/research-playbook-legacy",
        "installed_canonical": installed_root / CANONICAL,
        "installed_candidate": installed_root / CANDIDATE,
    }


def _assert_candidate_inputs(paths: dict[str, Path]) -> None:
    for name in (
        "canonical_source",
        "candidate_source",
        "managed_manifest",
        "evaluator",
        "research_tests",
        "validator_tests",
    ):
        if not paths[name].exists():
            raise PromotionError(f"required-path-missing:{name}")
    skill = (paths["candidate_source"] / "SKILL.md").read_text(encoding="utf-8")
    if "name: research-playbook-v2\n" not in skill:
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
    score_path: Path,
    *,
    validation_receipt: Path | None = None,
    live_receipt: Path | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    installed_root = installed_root.expanduser().resolve()
    score_path = score_path.resolve()
    paths = tracked_paths(repo_root, installed_root)
    _assert_candidate_inputs(paths)
    predicate_evidence = validate_score(read_json(score_path))
    plan: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "verdict": "READY",
        "repo_root": str(repo_root),
        "installed_root": str(installed_root),
        "score_path": str(score_path),
        "score_sha256": sha256_file(score_path),
        "score_predicates": predicate_evidence,
        "paths": {
            name: {"path": str(path), "before": path_state(path)}
            for name, path in paths.items()
        },
        "completion_gates": list(PLAN_GATES),
        "validation_receipt": str(
            (validation_receipt or Path("/private/tmp/research-playbook-promotion-validation.json")).resolve()
        ),
        "live_receipt": str(
            (live_receipt or Path("/private/tmp/research-playbook-canonical-live-smoke.json")).resolve()
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
    score_path = Path(plan["score_path"])
    if sha256_file(score_path) != plan["score_sha256"]:
        raise PromotionError("score-changed-after-plan")
    validate_score(read_json(score_path))
    paths = {
        name: Path(item["path"]).expanduser().resolve()
        for name, item in plan["paths"].items()
    }
    expected_paths = tracked_paths(
        Path(plan["repo_root"]).resolve(), Path(plan["installed_root"]).resolve()
    )
    if paths != expected_paths:
        raise PromotionError("plan-path-set-mismatch")
    for name, path in paths.items():
        if path_state(path) != plan["paths"][name]["before"]:
            raise PromotionError(f"path-changed-after-plan:{name}")
    return paths


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise PromotionError(f"rewrite-precondition-failed:{label}")
    return text.replace(old, new, 1)


def stage_canonical(candidate: Path, stage: Path) -> None:
    shutil.copytree(candidate, stage)
    skill_path = stage / "SKILL.md"
    skill = skill_path.read_text(encoding="utf-8")
    skill = _replace_once(skill, "name: research-playbook-v2\n", "name: research-playbook\n", "skill-name")
    description = (
        "description: Use when research is intended to feed an implementation plan and must produce "
        "a build-bound, planner-ready package through a bounded independent-subagent workflow. Freeze "
        "scope and requirement maturity, run a core researcher plus internal-readiness, requirements-coverage, "
        "and requirements-satisfaction lenses on identical evidence, adjudicate findings, and emit a concise "
        "handoff for a fresh one-shot implementation planner. Do not use for implementation planning, code "
        "changes, or diff review."
    )
    skill, count = re.subn(r"^description: .+$", description, skill, count=1, flags=re.MULTILINE)
    if count != 1:
        raise PromotionError("rewrite-precondition-failed:skill-description")
    skill = _replace_once(skill, "# Research Playbook V2", "# Research Playbook", "skill-title")
    skill = _replace_once(
        skill,
        "- Do not promote this skill, replace `research-playbook`, or alter routing.\n",
        "",
        "promotion-boundary",
    )
    skill = _replace_once(
        skill,
        "Use [evaluation.md](references/evaluation.md) when validating this skill against the legacy playbook before promotion.",
        "The comparison record in [evaluation.md](references/evaluation.md) is historical promotion evidence, not a runtime gate.",
        "evaluation-note",
    )
    skill_path.write_text(skill, encoding="utf-8")

    (stage / "agents/openai.yaml").write_text(
        'interface:\n'
        '  display_name: "Research Playbook"\n'
        '  short_description: "Bounded research for one-shot plans"\n'
        '  default_prompt: "Use $research-playbook to produce a planner-ready research package."\n',
        encoding="utf-8",
    )
    lenses = stage / "references/lenses-and-findings.md"
    lenses.write_text(
        lenses.read_text(encoding="utf-8").replace(
            "skills/research-playbook-v2/", "skills/research-playbook/"
        ),
        encoding="utf-8",
    )
    evaluation = stage / "references/evaluation.md"
    evaluation_text = evaluation.read_text(encoding="utf-8")
    replacements = {
        "# Comparative Evaluation Contract": "# Comparative Evaluation Contract (Historical Promotion Evidence)",
        "- 6 v2 research executions using explicit `$research-playbook-v2`;": "- 6 candidate research executions using the isolated candidate tree;",
        "- explicit v2 invocation selects v2 in a fresh task;": "- a fresh canonical invocation selects `research-playbook`;",
        "- an ordinary research prompt still selects legacy in a fresh task;": "- canonical routing metadata permits the governed research entry point;",
        "- every pre-existing managed Codex skill remains byte-identical after installation, with only `research-playbook-v2` added.": "- every unrelated managed Codex skill remains byte-identical, the canonical skill is replaced, and no candidate alias remains installed.",
        "reduces live executions; it does not create a smaller fixture corpus or weaken a predicate. Legacy\nreplacement remains a separate approval after this comparison passes.": "reduces live executions; it does not create a smaller fixture corpus or weaken a predicate. The\nreplacement approval followed this comparison; this file now preserves its evidence contract only.",
    }
    for old, new in replacements.items():
        evaluation_text = _replace_once(evaluation_text, old, new, f"evaluation:{old[:24]}")
    evaluation.write_text(evaluation_text, encoding="utf-8")
    for item in stage.rglob("*"):
        if item.is_file() and CANDIDATE in item.read_text(encoding="utf-8"):
            raise PromotionError(f"candidate-alias-remains-in-canonical:{item.relative_to(stage)}")


def transformed_files(paths: dict[str, Path]) -> dict[str, str]:
    managed = paths["managed_manifest"].read_text(encoding="utf-8")
    managed_lines = managed.splitlines()
    if managed_lines.count(CANDIDATE) != 1:
        raise PromotionError("managed-candidate-line-mismatch")
    managed_text = "\n".join(line for line in managed_lines if line != CANDIDATE) + "\n"

    evaluator = paths["evaluator"].read_text(encoding="utf-8")
    evaluator = _replace_once(
        evaluator, '"invocation": "ordinary research prompt" if arm == "legacy" else "$research-playbook-v2",',
        '"invocation": "ordinary research prompt" if arm == "legacy" else "$research-playbook",',
        "evaluator-invocation",
    )
    evaluator = _replace_once(
        evaluator, '("legacy", "skills/research-playbook"),\n        ("v2", "skills/research-playbook-v2"),',
        '("legacy", "tests/fixtures/research-playbook-legacy"),\n        ("v2", "skills/research-playbook"),',
        "evaluator-skill-trees",
    )

    research_tests = paths["research_tests"].read_text(encoding="utf-8")
    for old, new, label in (
        ("skills/research-playbook-v2/scripts/research_package.py", "skills/research-playbook/scripts/research_package.py", "test-module"),
        ("skills/research-playbook-v2/references/lenses-and-findings.md", "skills/research-playbook/references/lenses-and-findings.md", "test-lenses"),
        ('Path(__file__).parents[1] / "skills/research-playbook-v2/references"', 'Path(__file__).parents[1] / "skills/research-playbook/references"', "test-references"),
    ):
        research_tests = _replace_once(research_tests, old, new, label)

    validator_tests = paths["validator_tests"].read_text(encoding="utf-8")
    old_block = '''    def test_research_playbook_v2_is_managed_and_explicit_only(self):
        managed=(ROOT/"skills/managed-skills.txt").read_text().splitlines()
        self.assertIn("research-playbook-v2",managed)
        metadata=(ROOT/"skills/research-playbook-v2/agents/openai.yaml").read_text()
        self.assertIn("policy:\\n  allow_implicit_invocation: false\\n",metadata)
        self.assertEqual(v.validate_openai(ROOT/"skills/research-playbook-v2/agents/openai.yaml"),[])
'''
    new_block = '''    def test_research_playbook_is_managed_canonical_entrypoint(self):
        managed=(ROOT/"skills/managed-skills.txt").read_text().splitlines()
        self.assertIn("research-playbook",managed)
        self.assertNotIn("research-playbook-v2",managed)
        metadata=(ROOT/"skills/research-playbook/agents/openai.yaml").read_text()
        self.assertIn("$research-playbook",metadata)
        self.assertNotIn("allow_implicit_invocation: false",metadata)
        self.assertEqual(v.validate_openai(ROOT/"skills/research-playbook/agents/openai.yaml"),[])
'''
    validator_tests = _replace_once(validator_tests, old_block, new_block, "validator-test")
    return {
        "managed_manifest": managed_text,
        "evaluator": evaluator,
        "research_tests": research_tests,
        "validator_tests": validator_tests,
    }


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
        only=[CANONICAL],
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
    stage = repo_root / "skills" / f".research-playbook-promotion-{uuid.uuid4().hex}"
    manifest: dict[str, Any] | None = None
    try:
        stage_canonical(paths["candidate_source"], stage)
        manifest = create_backup(paths, backup_root, plan)
        shutil.copytree(paths["canonical_source"], paths["legacy_fixture"])
        shutil.rmtree(paths["canonical_source"])
        os.replace(stage, paths["canonical_source"])
        shutil.rmtree(paths["candidate_source"])
        for name, content in transformed.items():
            atomic_write(paths[name], content)
        installer(repo_root, installed_root, backup_root / "installer-state")
        if tree_hash(paths["installed_canonical"]) != tree_hash(paths["canonical_source"]):
            raise PromotionError("installed-canonical-hash-mismatch")
        if paths["installed_candidate"].exists():
            shutil.rmtree(paths["installed_candidate"])
        structural = verify_structure(plan, backup_root, require_receipts=False)
        receipt = {
            "schema_version": SCHEMA_VERSION,
            "ok": True,
            "plan_sha256": plan["plan_sha256"],
            "canonical_tree_sha256": tree_hash(paths["canonical_source"]),
            "structural_gates": structural["gates"],
        }
        write_json(backup_root / "apply-receipt.json", receipt)
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
    manifest = read_json(backup_root / "backup-manifest.json")
    if manifest.get("plan_sha256") != plan["plan_sha256"]:
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
    return (
        receipt.get("schema_version") == 1
        and receipt.get("focused_tests_exit") == 0
        and receipt.get("full_tests_exit") == 0
        and receipt.get("skill_validation_exit") == 0
        and receipt.get("canonical_tree_sha256") == canonical_hash
    )


def _live_receipt_ok(plan: dict[str, Any], canonical_hash: str) -> bool:
    receipt = read_json(Path(plan["live_receipt"]))
    roles = receipt.get("roles")
    required_roles = {
        "core",
        "internal_readiness",
        "requirements_coverage",
        "requirements_satisfaction",
        "adjudicator",
    }
    return (
        receipt.get("schema_version") == 1
        and receipt.get("skill_name") == CANONICAL
        and receipt.get("invocation") == "$research-playbook"
        and receipt.get("package_validation") == "PASS"
        and receipt.get("all_slots_closed") is True
        and receipt.get("canonical_tree_sha256") == canonical_hash
        and isinstance(roles, dict)
        and set(roles) == required_roles
        and len(set(roles.values())) == len(required_roles)
        and all(isinstance(value, str) and value.strip() for value in roles.values())
    )


def verify_structure(
    plan: dict[str, Any], backup_root: Path, *, require_receipts: bool = True
) -> dict[str, Any]:
    paths = {name: Path(item["path"]) for name, item in plan["paths"].items()}
    canonical_hash = tree_hash(paths["canonical_source"])
    managed = paths["managed_manifest"].read_text(encoding="utf-8").splitlines()
    canonical_text = "\n".join(
        item.read_text(encoding="utf-8")
        for item in paths["canonical_source"].rglob("*") if item.is_file()
    )
    installed_text = "\n".join(
        item.read_text(encoding="utf-8")
        for item in paths["installed_canonical"].rglob("*") if item.is_file()
    ) if paths["installed_canonical"].is_dir() else ""
    metadata = (paths["canonical_source"] / "agents/openai.yaml").read_text(encoding="utf-8")
    gates: dict[str, bool] = {
        "validated-candidate-score": bool(validate_score(read_json(Path(plan["score_path"])))),
        "canonical-source-replacement": (
            canonical_hash is not None
            and (paths["canonical_source"] / "scripts/research_package.py").is_file()
            and tree_hash(paths["legacy_fixture"]) == plan["paths"]["canonical_source"]["before"]["sha256"]
        ),
        "candidate-alias-retirement": (
            not paths["candidate_source"].exists()
            and not paths["installed_candidate"].exists()
            and CANDIDATE not in canonical_text
            and CANDIDATE not in installed_text
            and CANDIDATE not in managed
        ),
        "canonical-routing-and-install": (
            managed.count(CANONICAL) == 1
            and tree_hash(paths["installed_canonical"]) == canonical_hash
            and "$research-playbook" in metadata
            and "allow_implicit_invocation: false" not in metadata
            and "skills/research-playbook-v2/" not in paths["evaluator"].read_text(encoding="utf-8")
            and "skills/research-playbook-v2/" not in paths["research_tests"].read_text(encoding="utf-8")
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
        args.score,
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


def cmd_verify(args: argparse.Namespace) -> dict[str, Any]:
    plan = load_plan(args.plan)
    result = verify_structure(plan, args.backup_root.resolve(), require_receipts=True)
    if result["verdict"] != "PASS":
        raise PromotionError("promotion-verification-failed:" + ",".join(
            name for name, passed in result["gates"].items() if not passed
        ))
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--repo-root", type=Path, required=True)
    plan.add_argument("--installed-root", type=Path, required=True)
    plan.add_argument("--score", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    plan.add_argument("--validation-receipt", type=Path)
    plan.add_argument("--live-receipt", type=Path)
    plan.set_defaults(func=cmd_plan)
    apply = sub.add_parser("apply")
    apply.add_argument("--plan", type=Path, required=True)
    apply.add_argument("--backup-root", type=Path, required=True)
    apply.set_defaults(func=cmd_apply)
    verify = sub.add_parser("verify")
    verify.add_argument("--plan", type=Path, required=True)
    verify.add_argument("--backup-root", type=Path, required=True)
    verify.set_defaults(func=cmd_verify)
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
