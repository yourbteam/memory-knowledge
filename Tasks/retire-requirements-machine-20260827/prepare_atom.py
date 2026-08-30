#!/usr/bin/env python3
"""Prepare the isolated Development-Probe run for requirements skill replacement."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
OUT = (
    Path(sys.argv[1]).resolve()
    if len(sys.argv) == 2
    else Path("/private/tmp/requirements-machinery-promotion-atom")
)
PROMOTION_COMMIT = "a996195703add8e98aa59b91ae8d6e7ade56ad94"
ATOMIC_STEP_ID = "promote-requirements-machinery-retire-machine"


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_file(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def git_bytes(revision: str, path: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{revision}:{path}"],
        cwd=REPO,
        check=True,
        capture_output=True,
    ).stdout


def tracked_paths(revision: str, boundary: str) -> list[str]:
    result = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", revision, "--", boundary],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def copy_revision_boundary(revision: str, boundary: str, destination: Path) -> None:
    for relative in tracked_paths(revision, boundary):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(git_bytes(revision, relative))


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location(f"projection_{digest_file(path)[:12]}", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def replace_exact(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count == 0:
        raise RuntimeError(f"{path}: required source text is absent: {old!r}")
    path.write_text(text.replace(old, new), encoding="utf-8")


def add_promoted_machinery(candidate: Path) -> None:
    copy_revision_boundary(PROMOTION_COMMIT, "skills/requirements-machinery", candidate)


def update_routes(candidate: Path) -> None:
    for relative in (
        "skills/working-agreement/SKILL.md",
        "skills/task-intake/SKILL.md",
        "skills/sequence-runner/SKILL.md",
    ):
        replace_exact(candidate / relative, "`requirements-machine`", "`requirements-machinery`")


def update_tests(candidate: Path) -> None:
    old_test = candidate / "tests/test_requirements_machinery.py"
    if old_test.exists():
        old_test.unlink()
    target = candidate / "tests/test_requirements_machinery_cover.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(git_bytes(PROMOTION_COMMIT, "tests/test_requirements_machinery_cover.py"))

    policy_test = candidate / "tests/test_machinery_client_model_policy.py"
    text = policy_test.read_text(encoding="utf-8")
    text = text.replace(
        '["implementation-machine", "description-machinery", "requirements-machine"]',
        '["implementation-machine", "description-machinery"]',
    )
    if "requirements-machine" in text:
        raise RuntimeError("legacy requirements-machine remains in client policy test")
    policy_test.write_text(text, encoding="utf-8")

    parity = candidate / "tests/test_claude_parity.py"
    text = parity.read_text(encoding="utf-8")
    text = text.replace(
        '("description-machinery", "implementation-machine", "requirements-machine")',
        '("description-machinery", "implementation-machine", "requirements-machinery")',
    )
    text = text.replace(
        '{"description-machinery", "implementation-machine", "requirements-machine"}',
        '{"description-machinery", "implementation-machine", "requirements-machinery"}',
    )
    old_block = '''    requirements = (SKILLS / "requirements-machine" / "SKILL.md").read_text()
    assert "complete local controller" in requirements
    assert "do not\\nput `task-intake`, `sequence-runner`, registry selection, or sequence discovery around it" in requirements
'''
    new_block = '''    requirements = (SKILLS / "requirements-machinery" / "SKILL.md").read_text()
    assert "## The front door" in requirements
    assert "nothing comes out while any part of the source is" in requirements
'''
    if old_block not in text:
        raise RuntimeError("expected legacy parity block is absent")
    text = text.replace(old_block, new_block)
    old_assert = '''                assert policy == {
                    "schema_version": 1,
                    "client": client,
                    "required_runtime": required,
                    "forbidden_runtime": forbidden,
                    "fail_closed": True,
                }
'''
    new_assert = '''                expected = {
                    "schema_version": 1,
                    "client": client,
                    "required_runtime": required,
                    "forbidden_runtime": forbidden,
                    "fail_closed": True,
                }
                if name == "requirements-machinery":
                    expected["recommended_reader_command"] = required
                assert policy == expected
'''
    if old_assert not in text:
        raise RuntimeError("expected client projection assertion is absent")
    text = text.replace(old_assert, new_assert)
    if "requirements-machine" in text.replace("requirements-machinery", ""):
        raise RuntimeError("legacy requirements-machine remains in parity test")
    parity.write_text(text, encoding="utf-8")


def apply_retirement(candidate: Path, *, remove_old: bool) -> None:
    add_promoted_machinery(candidate)
    update_routes(candidate)
    if remove_old:
        shutil.rmtree(candidate / "skills/requirements-machine")
        update_tests(candidate)


def versioned_projector(candidate: Path) -> None:
    projector = candidate / "working-agreement/project_client_skills.py"
    text = projector.read_text(encoding="utf-8")
    old_registry = '''GENERATOR_FILES = {
    "machinery-client-model-v1": Path(__file__).resolve().with_name("machinery-client-model-v1.json"),
}
'''
    new_registry = '''GENERATOR_FILES = {
    "machinery-client-model-v1": Path(__file__).resolve().with_name("machinery-client-model-v1.json"),
    "machinery-client-model-v2": Path(__file__).resolve().with_name("machinery-client-model-v2.json"),
}
'''
    if old_registry not in text:
        raise RuntimeError("projector generator registry changed unexpectedly")
    text = text.replace(old_registry, new_registry)
    old_policy = '''    policy = spec["clients"].get(client)
    if policy is None:
        raise RuntimeError(f"generator {generator} has no {client} policy")
    installed_policy = {
        "schema_version": 1,
        "client": client,
        "required_runtime": policy["required_runtime"],
        "forbidden_runtime": policy["forbidden_runtime"],
        "fail_closed": True,
    }
'''
    new_policy = '''    policy = spec["clients"].get(client)
    if policy is None:
        raise RuntimeError(f"generator {generator} has no {client} policy")
    policy_fields = {"display_name", "required_runtime", "forbidden_runtime"}
    if generator == "machinery-client-model-v2":
        policy_fields.add("recommended_reader_command")
    if set(policy) != policy_fields or any(
        not isinstance(policy[field], str) or not policy[field].strip()
        for field in policy_fields
    ):
        raise RuntimeError(
            f"generator {generator} {client} policy must contain exactly "
            f"{sorted(policy_fields)} as non-empty strings"
        )
    installed_policy = {
        "schema_version": 1,
        "client": client,
        "required_runtime": policy["required_runtime"],
        "forbidden_runtime": policy["forbidden_runtime"],
        "fail_closed": True,
    }
    if generator == "machinery-client-model-v2":
        installed_policy["recommended_reader_command"] = policy["recommended_reader_command"]
'''
    if old_policy not in text:
        raise RuntimeError("projector policy block changed unexpectedly")
    text = text.replace(old_policy, new_policy)
    text = text.replace(
        'f"`{policy[\'required_runtime\']}`; reject `{policy[\'forbidden_runtime\']}` before launch. "',
        'f"`{policy.get(\'recommended_reader_command\', policy[\'required_runtime\'])}`; "\n'
        '        f"reject `{policy[\'forbidden_runtime\']}` before launch. "',
    )
    projector.write_text(text, encoding="utf-8")

    spec = json.loads(git_bytes(PROMOTION_COMMIT, "working-agreement/machinery-client-model-v1.json"))
    spec["generator"] = "machinery-client-model-v2"
    write_json(candidate / "working-agreement/machinery-client-model-v2.json", spec)


def global_projector(candidate: Path) -> None:
    (candidate / "working-agreement/project_client_skills.py").write_bytes(
        git_bytes(PROMOTION_COMMIT, "working-agreement/project_client_skills.py")
    )
    (candidate / "working-agreement/machinery-client-model-v1.json").write_bytes(
        git_bytes(PROMOTION_COMMIT, "working-agreement/machinery-client-model-v1.json")
    )


def harden_projection_staging(candidate: Path) -> None:
    """Make generated projection staging independent of canonical source modes."""
    projector = candidate / "working-agreement/project_client_skills.py"
    text = projector.read_text(encoding="utf-8")
    old = '''    shutil.copytree(source, destination)
    if row.get("disposition") != "GENERATED_CLIENT_PROJECTION":
        return
'''
    new = '''    shutil.copytree(source, destination)
    if row.get("disposition") != "GENERATED_CLIENT_PROJECTION":
        return
    destination.chmod(0o755)
    for generated_path in (
        destination / "client-model-policy.json",
        destination / "SKILL.md",
    ):
        if generated_path.exists():
            generated_path.chmod(0o644)
'''
    if old not in text:
        raise RuntimeError("projector staging boundary changed unexpectedly")
    projector.write_text(text.replace(old, new), encoding="utf-8")


def register_and_generate(candidate: Path, generator: str) -> None:
    manifest = candidate / "skills/managed-skills.txt"
    names = [line for line in manifest.read_text(encoding="utf-8").splitlines() if line]
    if names.count("requirements-machine") != 1 or "requirements-machinery" in names:
        raise RuntimeError("managed requirements identity is not the expected legacy state")
    names[names.index("requirements-machine")] = "requirements-machinery"
    manifest.write_text("\n".join(names) + "\n", encoding="utf-8")

    projection_path = candidate / "working-agreement/client-skill-projections.json"
    data = json.loads(projection_path.read_text(encoding="utf-8"))
    data["entries"].pop("requirements-machine")
    data["entries"]["requirements-machinery"] = {
        "canonical_tree_sha256": None,
        "disposition": "GENERATED_CLIENT_PROJECTION",
        "divergence_reason": (
            "The invoking client owns the exact reader runtime policy while the coverage "
            "and requirements behavior remains shared."
        ),
        "generator": generator,
        "generator_sha256": None,
        "projected_tree_sha256": None,
        "projected_tree_sha256_by_client": {"claude": None, "codex": None},
        "scenario_groups": ["CAP-SHARED"],
        "targets": ["codex", "claude"],
    }
    write_json(projection_path, data)
    completed = subprocess.run(
        [
            sys.executable,
            str(candidate / "working-agreement/project_client_skills.py"),
            "generate",
            "--skills-root",
            str(candidate / "skills"),
            "--manifest",
            str(manifest),
            "--projections",
            str(projection_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"projection generation failed: {completed.stderr}{completed.stdout}")


def add_projection_test(candidate: Path) -> None:
    path = candidate / "tests/test_client_skill_projections.py"
    text = path.read_text(encoding="utf-8")
    marker = "\n\nif __name__ == \"__main__\":\n"
    if marker not in text:
        raise RuntimeError("client projection test insertion point is absent")
    method = r'''

    def test_versioned_requirements_projection_adds_reader_command_without_changing_v1(self):
        with TemporaryDirectory() as td:
            base = Path(td)
            skills, manifest = make_repo(base, ["requirements-machinery"])
            policy_source = skills / "requirements-machinery" / "client-model-policy.json"
            policy_source.write_text("{}\n")
            policy_source.chmod(0o444)
            (skills / "requirements-machinery" / "SKILL.md").chmod(0o444)
            projections = base / "client-skill-projections.json"
            projections.write_text(json.dumps({
                "schema_version": 1,
                "entries": {
                    "requirements-machinery": {
                        "disposition": "GENERATED_CLIENT_PROJECTION",
                        "targets": ["codex", "claude"],
                        "scenario_groups": ["CAP-SHARED"],
                        "canonical_tree_sha256": None,
                        "projected_tree_sha256": None,
                        "projected_tree_sha256_by_client": None,
                        "generator": "machinery-client-model-v2",
                        "generator_sha256": None,
                        "divergence_reason": "Reader runtime is client-owned.",
                    }
                },
            }) + "\n")
            generated = run_tool("generate", "--skills-root", str(skills),
                                 "--projections", str(projections))
            self.assertEqual(generated.returncode, 0, generated.stderr)
            for client, required in (("codex", "codex exec"), ("claude", "claude -p")):
                staging = base / f"staging-{client}"
                built = run_tool("build", "--client", client, "--skills-root", str(skills),
                                 "--projections", str(projections),
                                 "--staging-root", str(staging))
                self.assertEqual(built.returncode, 0, built.stderr)
                policy = json.loads((staging / "requirements-machinery" /
                                     "client-model-policy.json").read_text())
                self.assertEqual(policy["recommended_reader_command"], required)
'''
    path.write_text(text.replace(marker, method + marker), encoding="utf-8")


OPERATOR = r'''from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import sys
from pathlib import Path

sys.dont_write_bytecode = True


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("candidate_projection", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


root = Path(__file__).resolve().parent
case = json.loads(Path(os.environ["EXPERIMENT_INPUT_PATH"]).read_text(encoding="utf-8"))
work = Path(os.environ["EXPERIMENT_WORK_DIR"])
old_pattern = re.compile(r"requirements-machine(?!ry)")
new_skill = root / "skills/requirements-machinery"
old_skill = root / "skills/requirements-machine"
route_paths = [
    root / "skills/working-agreement/SKILL.md",
    root / "skills/task-intake/SKILL.md",
    root / "skills/sequence-runner/SKILL.md",
]
module = load_module(root / "working-agreement/project_client_skills.py")
new_hash = module.tree_hash(new_skill)
routes_aligned = all(
    "requirements-machinery" in path.read_text(encoding="utf-8")
    and not old_pattern.search(path.read_text(encoding="utf-8"))
    for path in route_paths
)
outcome = {
    "case_id": case["case_id"],
    "old_absent": not old_skill.exists(),
    "new_source_matches": new_hash == case["promoted_tree_sha256"],
    "routes_aligned": routes_aligned,
}
if case["case_id"] == "client-projection-management":
    names = module.manifest_names(root / "skills/managed-skills.txt")
    data = module.load_projections(root / "working-agreement/client-skill-projections.json")
    entries = data["entries"]
    manifest_exact = "requirements-machinery" in names and "requirements-machine" not in names
    entries_exact = "requirements-machinery" in entries and "requirements-machine" not in entries
    structural = module.structural_errors(entries, names)
    currency = module.currency_errors(root / "skills", entries, names)
    policies = {}
    builds_ok = True
    if manifest_exact and entries_exact and not structural and not currency:
        row = entries["requirements-machinery"]
        for client, required, forbidden in (
            ("codex", "codex exec", "claude"),
            ("claude", "claude -p", "codex exec"),
        ):
            destination = work / f"projection-{client}" / "requirements-machinery"
            try:
                # Development-Probe freezes assembled candidate files read-only. Rehydrate
                # the canonical skill into the writable mode it has in a real checkout so
                # the production projector can replace its generated policy normally.
                writable_source = work / f"source-{client}" / "requirements-machinery"
                shutil.copytree(new_skill, writable_source)
                for path in writable_source.rglob("*"):
                    path.chmod(0o755 if path.is_dir() else 0o644)
                module.project_skill(writable_source, destination, client, row)
                policy = json.loads((destination / "client-model-policy.json").read_text())
                policies[client] = policy
                builds_ok = builds_ok and policy == {
                    "schema_version": 1,
                    "client": client,
                    "required_runtime": required,
                    "forbidden_runtime": forbidden,
                    "recommended_reader_command": required,
                    "fail_closed": True,
                }
                builds_ok = builds_ok and module.tree_hash(destination) == (
                    row["projected_tree_sha256_by_client"][client]
                )
            except Exception as exc:
                policies[client] = {"error": str(exc)}
                builds_ok = False
    else:
        builds_ok = False
    baseline_v1 = case["baseline_v1_sha256"]
    v1_path = root / "working-agreement/machinery-client-model-v1.json"
    outcome.update({
        "manifest_exact": manifest_exact,
        "entries_exact": entries_exact,
        "structural_errors": structural,
        "currency_errors": currency,
        "client_projections_correct": builds_ok,
        "policies": policies,
        "unrelated_generator_churn": int(module.file_hash(v1_path) != baseline_v1),
    })

if case["case_id"] == "legacy-skill-discovery":
    score = sum(int(outcome[key]) for key in ("old_absent", "new_source_matches", "routes_aligned"))
    metrics = {"discovery-correctness": score}
else:
    score = sum(int(outcome[key]) for key in (
        "manifest_exact", "entries_exact", "client_projections_correct"
    ))
    score += int(not outcome["structural_errors"] and not outcome["currency_errors"])
    metrics = {
        "projection-correctness": score,
        "unrelated-projection-churn": outcome["unrelated_generator_churn"],
    }

result = {
    "schema_version": 1,
    "variant_id": os.environ["EXPERIMENT_VARIANT_ID"],
    "status": "completed",
    "outcome": outcome,
    "metrics": metrics,
    "error": None,
}
Path(os.environ["EXPERIMENT_RESULT_PATH"]).write_text(
    json.dumps(result, sort_keys=True) + "\n", encoding="utf-8"
)
'''


EVALUATOR = r'''from __future__ import annotations

import json
import sys
from pathlib import Path

request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
metric_names = [item["name"] for item in request["metrics"]]
scores = []
for candidate in request["candidates"]:
    outcome = candidate["outcome"]
    values = {}
    for name in metric_names:
        if name == "discovery-correctness":
            values[name] = sum(int(outcome.get(key) is True) for key in (
                "old_absent", "new_source_matches", "routes_aligned"
            ))
        elif name == "projection-correctness":
            values[name] = sum(int(outcome.get(key) is True) for key in (
                "manifest_exact", "entries_exact", "client_projections_correct"
            )) + int(not outcome.get("structural_errors") and not outcome.get("currency_errors"))
        elif name == "unrelated-projection-churn":
            values[name] = int(outcome.get("unrelated_generator_churn", 1))
        else:
            raise RuntimeError(f"unknown metric {name}")
    scores.append({"variant_id": candidate["variant_id"], "metrics": values})
Path(sys.argv[2]).write_text(
    json.dumps({"schema_version": 1, "scores": scores}, sort_keys=True) + "\n",
    encoding="utf-8",
)
'''


ASSESSMENT = r'''from __future__ import annotations

import json
import sys
from pathlib import Path

question = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
outcome = question["execution_result"]["outcome"]
if question["case_id"] == "legacy-skill-discovery":
    satisfied = all(outcome.get(key) is True for key in (
        "old_absent", "new_source_matches", "routes_aligned"
    ))
else:
    satisfied = all(outcome.get(key) is True for key in (
        "old_absent", "new_source_matches", "routes_aligned",
        "manifest_exact", "entries_exact", "client_projections_correct",
    )) and not outcome.get("structural_errors") and not outcome.get("currency_errors")
response = {
    "case_id": question["case_id"],
    "verdict": "satisfied" if satisfied else "not-satisfied",
    "reason": (
        "The assembled skill boundary exposes only the promoted requirements machinery through the declared client path."
        if satisfied else
        "The assembled skill boundary still exposes the retired skill or lacks one complete managed client projection."
    ),
    "evidence_pointers": ["execution-result"],
}
Path(sys.argv[2]).write_text(json.dumps(response, sort_keys=True) + "\n", encoding="utf-8")
'''


def main() -> int:
    if OUT.exists():
        raise SystemExit(f"refusing existing output: {OUT}")
    development = OUT / "development"
    baseline = development / "baseline"
    baseline.mkdir(parents=True)
    copy_revision_boundary("HEAD", "skills", baseline)
    for boundary in (
        "working-agreement/client-skill-projections.json",
        "working-agreement/machinery-client-model-v1.json",
        "working-agreement/project_client_skills.py",
        "tests/test_requirements_machinery.py",
        "tests/test_machinery_client_model_policy.py",
        "tests/test_claude_parity.py",
        "tests/test_client_skill_projections.py",
    ):
        copy_revision_boundary("HEAD", boundary, baseline)
    (baseline / "operator_probe.py").write_text(OPERATOR, encoding="utf-8")

    promoted_row = json.loads(
        git_bytes(PROMOTION_COMMIT, "working-agreement/client-skill-projections.json")
    )["entries"]["requirements-machinery"]
    promoted_tree_sha256 = promoted_row["canonical_tree_sha256"]
    baseline_v1_sha256 = digest_file(baseline / "working-agreement/machinery-client-model-v1.json")
    cases = [
        {
            "case_id": "legacy-skill-discovery",
            "captured_state": "requirements-machine is managed and installed while requirements-machinery is not canonical",
            "promoted_commit": PROMOTION_COMMIT,
            "promoted_tree_sha256": promoted_tree_sha256,
            "baseline_v1_sha256": baseline_v1_sha256,
        },
        {
            "case_id": "client-projection-management",
            "captured_state": "requirements-machinery installed copies are unmanaged and differ between clients",
            "promoted_commit": PROMOTION_COMMIT,
            "promoted_tree_sha256": promoted_tree_sha256,
            "baseline_v1_sha256": baseline_v1_sha256,
        },
    ]
    case_records = []
    for case in cases:
        path = OUT / "cases" / f"{case['case_id']}.json"
        write_json(path, case)
        case_records.append((case, path, digest_file(path)))

    replace = development / "replace-and-retire"
    coexist = development / "coexist-and-route"
    global_v1 = development / "evolve-global-v1"
    version_v2 = development / "versioned-v2"
    for target in (replace, coexist, global_v1, version_v2):
        shutil.copytree(baseline, target)
    apply_retirement(replace, remove_old=True)
    apply_retirement(coexist, remove_old=False)

    for target in (global_v1, version_v2):
        apply_retirement(target, remove_old=True)
        add_projection_test(target)
    global_projector(global_v1)
    harden_projection_staging(global_v1)
    register_and_generate(global_v1, "machinery-client-model-v1")
    versioned_projector(version_v2)
    harden_projection_staging(version_v2)
    register_and_generate(version_v2, "machinery-client-model-v2")

    (development / "evaluator.py").write_text(EVALUATOR, encoding="utf-8")
    (development / "assessment.py").write_text(ASSESSMENT, encoding="utf-8")

    allowed_paths = [
        "skills/requirements-machine",
        "skills/requirements-machinery",
        "skills/managed-skills.txt",
        "skills/task-intake/SKILL.md",
        "skills/sequence-runner/SKILL.md",
        "skills/working-agreement/SKILL.md",
        "working-agreement/client-skill-projections.json",
        "working-agreement/machinery-client-model-v1.json",
        "working-agreement/machinery-client-model-v2.json",
        "working-agreement/project_client_skills.py",
        "tests/test_requirements_machinery.py",
        "tests/test_requirements_machinery_cover.py",
        "tests/test_machinery_client_model_policy.py",
        "tests/test_claude_parity.py",
        "tests/test_client_skill_projections.py",
    ]
    atom_cases = [
        {
            "case_id": case["case_id"],
            "source_ref": str(path),
            "sha256": sha,
            "kind": "failure" if case["case_id"] == "legacy-skill-discovery" else "success",
            "expected_outcome": (
                "The retired requirements-machine is absent, the promoted requirements-machinery is exact, and every active route names only the promoted skill."
                if case["case_id"] == "legacy-skill-discovery" else
                "The common manager builds distinct valid Codex and Claude requirements-machinery projections without changing the existing v1 client contract."
            ),
        }
        for case, path, sha in case_records
    ]
    atom_request = {
        "schema_version": 1,
        "atomic_step_id": ATOMIC_STEP_ID,
        "outcome": "Only the latest promoted requirements-machinery is selectable and installed for Codex and Claude; requirements-machine is retired.",
        "practical_value": "Models cannot invoke the obsolete requirements path and both clients use the same upgraded coverage-guaranteed machinery through normal skill management.",
        "stopping_condition": "Canonical source, routing, managed registration, generated client policies, installed discovery, and focused tests all prove requirements-machine absent and requirements-machinery current for both clients.",
        "allowed_paths": allowed_paths,
        "captured_cases": atom_cases,
    }
    write_json(OUT / "atom-request.json", atom_request)

    manifest_cases = [
        {
            "id": item["case_id"],
            "source": item["source_ref"],
            "sha256": item["sha256"],
            "kind": item["kind"],
            "expected_outcome": item["expected_outcome"],
        }
        for item in atom_cases
    ]
    manifest = {
        "schema_version": 1,
        "atomic_step": {
            "id": ATOMIC_STEP_ID,
            "outcome": atom_request["outcome"],
            "practical_value": atom_request["practical_value"],
            "stopping_condition": atom_request["stopping_condition"],
            "captured_cases": manifest_cases,
        },
        "mini_probes": [
            {
                "id": "skill-retirement",
                "goal": "Replace the obsolete canonical skill and every active route with the exact promoted requirements machinery.",
                "practical_value": "Skill discovery cannot choose the obsolete requirements implementation.",
                "work_type": "code",
                "work_type_reason": "Canonical file presence, removal, hashes, and route identities are deterministic boundaries.",
                "allowed_paths": [
                    "skills/requirements-machine",
                    "skills/requirements-machinery",
                    "skills/task-intake/SKILL.md",
                    "skills/sequence-runner/SKILL.md",
                    "skills/working-agreement/SKILL.md",
                    "tests/test_requirements_machinery.py",
                    "tests/test_requirements_machinery_cover.py",
                    "tests/test_machinery_client_model_policy.py",
                    "tests/test_claude_parity.py",
                ],
                "inputs": [{"case_id": "legacy-skill-discovery"}],
                "approaches": [
                    {
                        "id": "replace-and-retire",
                        "hypothesis": "Removing the obsolete source while routing directly to the promoted machinery eliminates ambiguous discovery.",
                        "implementation": "Delete requirements-machine, import the promoted tree, migrate active routes, and replace obsolete tests.",
                        "predicted_tradeoff": "One exact supported skill remains; Git history is the recovery path for the retired implementation.",
                    },
                    {
                        "id": "coexist-and-route",
                        "hypothesis": "Keeping both skill directories while routing to the newer one is sufficient to prevent obsolete selection.",
                        "implementation": "Import requirements-machinery and update routes while leaving requirements-machine discoverable.",
                        "predicted_tradeoff": "Preserves the old files but leaves two selectable skills with overlapping names.",
                    },
                ],
                "proof": {
                    "success_criterion": "The promoted tree is exact, the retired directory is absent, and every active route names only requirements-machinery.",
                    "failure_criterion": "Any remaining requirements-machine directory or route makes obsolete model selection possible.",
                },
                "evaluation": {
                    "metrics": [{"name": "discovery-correctness", "direction": "maximize"}],
                    "across_cases": [{"name": "discovery-correctness", "method": "sum"}],
                },
                "winner_output": {
                    "artifact": "requirements-skill-boundary",
                    "description": "The canonical source and routing delta that exposes only the promoted machinery.",
                },
            },
            {
                "id": "client-projection",
                "goal": "Manage the promoted machinery through deterministic Codex and Claude projections without rewriting unrelated client contracts.",
                "practical_value": "Both clients install the upgraded reader-bound machinery through the normal manager while existing skills remain stable.",
                "work_type": "code",
                "work_type_reason": "Manifest identity, generator versioning, policy fields, hashes, and installation are deterministic enforcement.",
                "allowed_paths": allowed_paths,
                "inputs": [{"case_id": "client-projection-management"}],
                "approaches": [
                    {
                        "id": "evolve-global-v1",
                        "hypothesis": "Adding the reader-command field to the existing generator is the simplest valid common projection.",
                        "implementation": "Change generator v1 globally and regenerate every managed projection.",
                        "predicted_tradeoff": "The new skill works, but every existing generated skill receives an unrelated client-contract change.",
                    },
                    {
                        "id": "versioned-v2",
                        "hypothesis": "A versioned generator gives the new machinery its required reader field without changing existing projections.",
                        "implementation": "Register generator v2 for requirements-machinery only and preserve generator v1 byte-for-byte.",
                        "predicted_tradeoff": "Adds one explicit generator version while containing the behavioral change to the skill that needs it.",
                    },
                ],
                "proof": {
                    "success_criterion": "Both client projections build with exact reader policies and the managed manifest contains only requirements-machinery.",
                    "failure_criterion": "A missing client policy, manifest mismatch, stale hash, or unrelated v1 mutation fails the selected architecture.",
                },
                "evaluation": {
                    "metrics": [
                        {"name": "projection-correctness", "direction": "maximize"},
                        {"name": "unrelated-projection-churn", "direction": "minimize"},
                    ],
                    "across_cases": [
                        {"name": "projection-correctness", "method": "sum"},
                        {"name": "unrelated-projection-churn", "method": "sum"},
                    ],
                },
                "winner_output": {
                    "artifact": "requirements-client-projection",
                    "description": "The managed projection contract that installs the promoted machinery for both clients.",
                },
            },
        ],
        "composition": {
            "consumes": [
                {"probe_id": "skill-retirement", "artifact": "requirements-skill-boundary"},
                {"probe_id": "client-projection", "artifact": "requirements-client-projection"},
            ],
            "assembly_contract": "Merge identical promoted-source operations, remove the retired source, and apply the versioned managed projection and routes as one skill boundary.",
            "final_validation": {
                "operator_path": "execute the assembled skill-discovery and client-projection checks against the complete candidate source",
                "case_ids": ["legacy-skill-discovery", "client-projection-management"],
                "success_criterion": "Only requirements-machinery is canonical, routed, managed, and projected for both clients.",
                "failure_criterion": "Any discoverable requirements-machine or invalid client projection refuses completion.",
            },
        },
    }
    write_json(development / "manifest.json", manifest)

    builds = {
        "skill-retirement": [
            ("replace-and-retire", replace),
            ("coexist-and-route", coexist),
        ],
        "client-projection": [
            ("evolve-global-v1", global_v1),
            ("versioned-v2", version_v2),
        ],
    }
    cross_requests = []
    for probe_id, approaches in builds.items():
        approach_requests = []
        for approach_id, source in approaches:
            request_path = development / f"build-{approach_id}.json"
            write_json(request_path, {
                "schema_version": 1,
                "development_manifest": str(development / "manifest.json"),
                "probe_id": probe_id,
                "approach_id": approach_id,
                "source": {
                    "baseline": str(baseline),
                    "candidate": str(source),
                    "entrypoint": "operator_probe.py",
                },
                "execution": {
                    "protocol": "experiment-result-v1",
                    "command": ["{python}", "{candidate-entrypoint}"],
                },
            })
            approach_requests.append({"approach_id": approach_id, "request": str(request_path)})
        cross_path = development / f"cross-{probe_id}.json"
        write_json(cross_path, {
            "schema_version": 1,
            "development_manifest": str(development / "manifest.json"),
            "probe_id": probe_id,
            "approach_build_requests": approach_requests,
            "evaluator": {
                "adapter": {
                    "path": str(development / "evaluator.py"),
                    "sha256": digest_file(development / "evaluator.py"),
                },
                "command": [
                    "{python}", "{evaluation-adapter}",
                    "{evaluation-request}", "{evaluation-response}",
                ],
            },
        })
        cross_requests.append({
            "probe_id": probe_id,
            "request": str(cross_path),
            "request_sha256": digest_file(cross_path),
        })

    write_json(development / "all-probes.json", {
        "schema_version": 1,
        "development_manifest": str(development / "manifest.json"),
        "probe_requests": [
            {"probe_id": item["probe_id"], "request": item["request"]}
            for item in cross_requests
        ],
    })
    write_json(development / "full-run.json", {
        "schema_version": 1,
        "development_manifest": {
            "path": str(development / "manifest.json"),
            "sha256": digest_file(development / "manifest.json"),
        },
        "baseline": {
            "path": str(baseline),
            "sha256": subprocess.run(
                [sys.executable, str(REPO / "skills/experiment-machinery/scripts/run_experiment.py"),
                 "--hash-source", str(baseline)],
                check=True, capture_output=True, text=True,
            ).stdout.strip(),
        },
        "probe_requests": cross_requests,
        "assessment": {
            "adapter": {
                "path": str(development / "assessment.py"),
                "sha256": digest_file(development / "assessment.py"),
            },
            "command": [
                "{python}", "{assessment-adapter}",
                "{assessment-request}", "{assessment-response}",
            ],
        },
    })
    print(json.dumps({
        "ok": True,
        "root": str(OUT),
        "atom_request": str(OUT / "atom-request.json"),
        "manifest": str(development / "manifest.json"),
        "full_run": str(development / "full-run.json"),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
