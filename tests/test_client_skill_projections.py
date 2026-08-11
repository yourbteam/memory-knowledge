"""Focused tests for the deterministic client-skill projection manifest tool."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "working-agreement" / "project_client_skills.py"

spec = importlib.util.spec_from_file_location("project_client_skills", TOOL)
pcs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pcs)


def make_skill(root: Path, name: str, body: str = "content") -> None:
    skill = root / name
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(f"---\nname: {name}\ndescription: test\n---\n{body}\n")


def make_repo(base: Path, names: list[str]) -> tuple[Path, Path]:
    skills = base / "skills"
    skills.mkdir()
    for name in names:
        make_skill(skills, name)
    manifest = skills / "managed-skills.txt"
    manifest.write_text("\n".join(names) + "\n")
    return skills, manifest


def seed_projections(base: Path, skills: Path, names: list[str]) -> Path:
    entries = {
        name: {
            "disposition": "SHARED_IDENTICAL", "targets": ["codex", "claude"],
            "scenario_groups": ["CAP-SHARED"], "canonical_tree_sha256": None,
            "projected_tree_sha256": None, "generator": None, "generator_sha256": None,
            "divergence_reason": None,
        }
        for name in names
    }
    path = base / "client-skill-projections.json"
    path.write_text(json.dumps({"schema_version": 1, "entries": entries}) + "\n")
    return path


def run_tool(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL), *argv], capture_output=True, text=True)


class ProjectionManifestTests(unittest.TestCase):
    def test_generated_machinery_projection_binds_each_client_and_fails_closed(self):
        with TemporaryDirectory() as td:
            base = Path(td)
            skills, manifest = make_repo(base, ["implementation-machine"])
            projections = base / "client-skill-projections.json"
            projections.write_text(json.dumps({
                "schema_version": 1,
                "entries": {
                    "implementation-machine": {
                        "disposition": "GENERATED_CLIENT_PROJECTION",
                        "targets": ["codex", "claude"],
                        "scenario_groups": ["CAP-SHARED"],
                        "canonical_tree_sha256": None,
                        "projected_tree_sha256": None,
                        "projected_tree_sha256_by_client": None,
                        "generator": "machinery-client-model-v1",
                        "generator_sha256": None,
                        "divergence_reason": "The invoking client owns model selection.",
                    }
                },
            }) + "\n")

            generated = run_tool("generate", "--skills-root", str(skills),
                                 "--projections", str(projections))
            self.assertEqual(generated.returncode, 0, generated.stderr)

            data = json.loads(projections.read_text())
            row = data["entries"]["implementation-machine"]
            self.assertEqual(set(row["projected_tree_sha256_by_client"]), {"codex", "claude"})
            self.assertNotEqual(row["projected_tree_sha256_by_client"]["codex"],
                                row["projected_tree_sha256_by_client"]["claude"])

            for client, required, forbidden in (
                ("codex", "codex exec", "claude"),
                ("claude", "claude -p", "codex exec"),
            ):
                staging = base / f"staging-{client}"
                result = run_tool("build", "--client", client, "--skills-root", str(skills),
                                  "--projections", str(projections),
                                  "--staging-root", str(staging))
                self.assertEqual(result.returncode, 0, result.stderr)
                policy = json.loads((staging / "implementation-machine" /
                                     "client-model-policy.json").read_text())
                self.assertEqual(policy["client"], client)
                self.assertEqual(policy["required_runtime"], required)
                self.assertEqual(policy["forbidden_runtime"], forbidden)
                self.assertTrue(policy["fail_closed"])
                instructions = (staging / "implementation-machine" / "SKILL.md").read_text()
                self.assertIn(f"must resolve to `{required}`", instructions)
                self.assertIn(f"reject `{forbidden}`", instructions)

    def test_generate_binds_hashes_and_is_deterministic(self):
        with TemporaryDirectory() as td:
            base = Path(td)
            skills, manifest = make_repo(base, ["alpha", "beta"])
            projections = seed_projections(base, skills, ["alpha", "beta"])
            first = run_tool("generate", "--skills-root", str(skills), "--projections", str(projections))
            self.assertEqual(first.returncode, 0, first.stderr)
            once = projections.read_bytes()
            second = run_tool("generate", "--skills-root", str(skills), "--projections", str(projections))
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(once, projections.read_bytes())
            data = json.loads(once)
            row = data["entries"]["alpha"]
            self.assertEqual(row["canonical_tree_sha256"], pcs.tree_hash(skills / "alpha"))
            self.assertEqual(row["projected_tree_sha256"], row["canonical_tree_sha256"])

    def test_generate_refuses_managed_skill_without_disposition(self):
        with TemporaryDirectory() as td:
            base = Path(td)
            skills, manifest = make_repo(base, ["alpha", "beta"])
            projections = seed_projections(base, skills, ["alpha"])
            result = run_tool("generate", "--skills-root", str(skills), "--projections", str(projections))
            self.assertEqual(result.returncode, 1)
            self.assertIn("beta", result.stderr)

    def test_check_fails_closed_on_canonical_drift_after_projection(self):
        with TemporaryDirectory() as td:
            base = Path(td)
            skills, manifest = make_repo(base, ["alpha"])
            projections = seed_projections(base, skills, ["alpha"])
            run_tool("generate", "--skills-root", str(skills), "--projections", str(projections))
            (skills / "alpha" / "SKILL.md").write_text("---\nname: alpha\ndescription: test\n---\nchanged\n")
            result = run_tool("check", "--client", "claude", "--skills-root", str(skills),
                              "--projections", str(projections))
            self.assertEqual(result.returncode, 1)
            self.assertIn("canonical tree changed after projection", result.stdout)

    def test_check_reports_match_drift_missing_and_unmanaged(self):
        with TemporaryDirectory() as td:
            base = Path(td)
            skills, manifest = make_repo(base, ["alpha", "beta", "gamma"])
            projections = seed_projections(base, skills, ["alpha", "beta", "gamma"])
            run_tool("generate", "--skills-root", str(skills), "--projections", str(projections))
            installed = base / "installed"
            installed.mkdir()
            make_skill(installed, "alpha")                       # MATCH
            make_skill(installed, "beta", body="stale")          # DRIFT
            make_skill(installed, "legacy-loop")                 # UNMANAGED; gamma MISSING
            report = base / "report.json"
            result = run_tool("check", "--client", "claude", "--skills-root", str(skills),
                              "--projections", str(projections), "--installed-root", str(installed),
                              "--report", str(report))
            self.assertEqual(result.returncode, 1)
            payload = json.loads(report.read_text())
            states = {row["name"]: row["state"] for row in payload["rows"]}
            self.assertEqual(states, {"alpha": "MATCH", "beta": "DRIFT", "gamma": "MISSING"})
            self.assertEqual(payload["unmanaged_installed"], ["legacy-loop"])
            self.assertFalse(payload["parity"])

    def test_check_passes_when_installed_matches_projection(self):
        with TemporaryDirectory() as td:
            base = Path(td)
            skills, manifest = make_repo(base, ["alpha"])
            projections = seed_projections(base, skills, ["alpha"])
            run_tool("generate", "--skills-root", str(skills), "--projections", str(projections))
            installed = base / "installed"
            installed.mkdir()
            make_skill(installed, "alpha")
            result = run_tool("check", "--client", "claude", "--skills-root", str(skills),
                              "--projections", str(projections), "--installed-root", str(installed))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_build_stages_deterministically_and_fails_on_drift(self):
        with TemporaryDirectory() as td:
            base = Path(td)
            skills, manifest = make_repo(base, ["alpha"])
            projections = seed_projections(base, skills, ["alpha"])
            run_tool("generate", "--skills-root", str(skills), "--projections", str(projections))
            staging = base / "staging"
            result = run_tool("build", "--client", "claude", "--skills-root", str(skills),
                              "--projections", str(projections), "--staging-root", str(staging))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(pcs.tree_hash(staging / "alpha"), pcs.tree_hash(skills / "alpha"))
            self.assertTrue((staging / "projection-build.json").exists())
            (skills / "alpha" / "SKILL.md").write_text("---\nname: alpha\ndescription: test\n---\ndrifted\n")
            drifted = run_tool("build", "--client", "claude", "--skills-root", str(skills),
                               "--projections", str(projections), "--staging-root", str(base / "staging2"))
            self.assertEqual(drifted.returncode, 1)
            self.assertIn("canonical tree changed after projection", drifted.stderr)

    def test_blocked_disposition_prevents_build(self):
        with TemporaryDirectory() as td:
            base = Path(td)
            skills, manifest = make_repo(base, ["alpha"])
            projections = seed_projections(base, skills, ["alpha"])
            run_tool("generate", "--skills-root", str(skills), "--projections", str(projections))
            data = json.loads(projections.read_text())
            data["entries"]["alpha"]["disposition"] = "BLOCKED"
            projections.write_text(json.dumps(data) + "\n")
            result = run_tool("build", "--client", "claude", "--skills-root", str(skills),
                              "--projections", str(projections), "--staging-root", str(base / "staging"))
            self.assertEqual(result.returncode, 1)
            self.assertIn("blocked", result.stderr.lower())

    def test_repository_manifest_is_complete_and_current(self):
        result = run_tool("check", "--client", "claude")
        payload_errors = [line for line in result.stdout.splitlines() if line.startswith("ERROR")]
        self.assertEqual(payload_errors, [], result.stdout)


if __name__ == "__main__":
    unittest.main()
