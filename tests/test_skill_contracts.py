import unittest
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).parents[1]/"skills"


class ContractTests(unittest.TestCase):
    def test_write_code_routes_grounded_prototype_work(self):
        write_code=(ROOT/"write-code-playbook/SKILL.md").read_text()
        prototype=(ROOT/"prototype-driven-implementation/SKILL.md").read_text()
        managed=(ROOT/"managed-skills.txt").read_text().splitlines()
        self.assertIn("`prototype-driven-implementation`",write_code)
        self.assertIn("real captured success and failure cases",prototype)
        self.assertIn("promote",prototype)
        self.assertIn("revise",prototype)
        self.assertIn("discard",prototype)
        self.assertIn("prototype-driven-implementation",managed)

    def test_convergence_contracts(self):
        convergence=(ROOT/"playbook-convergence-loop/SKILL.md").read_text()
        self.assertIn("bounded autonomy",convergence); self.assertIn("close_agent",convergence); self.assertIn("guard-baseline",convergence)
        stage_order=convergence.split("## Stage Order",1)[1].split("## Review Loop",1)[0]
        playbooks=("plan-playbook","write-code-playbook")
        positions=[stage_order.index(f"`{name}`") for name in playbooks]
        self.assertEqual(positions,sorted(positions))
        self.assertNotIn("standalone review controller",stage_order)
        self.assertLess(stage_order.index("PDI-owned retained-surface inspection"),stage_order.index("`verify-work`"))
        verify=(ROOT/"verify-work/SKILL.md").read_text()
        for phrase in ("staged changes","unstaged changes","untracked files","assessment-only","Do not commit by default"):
            self.assertIn(phrase,verify)

    def test_working_agreement_has_no_range(self):
        text=(ROOT/"working-agreement/SKILL.md").read_text()
        self.assertNotIn("G0-G6",text); self.assertIn("all current",text); self.assertIn("projectless",text)

    def test_planner_v2_requires_repository_native_regression_verification(self):
        candidate=ROOT/"plan-playbook"
        entry=(candidate/"references/entry-and-evidence.md").read_text()
        package=(candidate/"references/plan-package.md").read_text()
        lenses=(candidate/"references/hardening-lenses.md").read_text()
        for text in (entry,package,lenses):
            self.assertIn("native full",text)
            self.assertIn("focused",text)
        self.assertIn("evidence-backed absence",entry)
        self.assertIn("no native full-suite command exists",package)

    def test_delegated_skills_preserve_evidence_but_not_rationale(self):
        for name in ("doc-gap-closure-loop","requirements-coverage-gap-loop","requirements-satisfaction-gap-loop","verify-plan","verify-analysis","verify-work"):
            text=(ROOT/name/"SKILL.md").read_text()
            self.assertIn("assessment-only",text,name); self.assertIn("evidence",text,name)
        convergence=(ROOT/"playbook-convergence-loop/SKILL.md").read_text()
        self.assertIn("excludes producer rationale",convergence); self.assertIn("authoritative source roots",convergence)

    def test_no_automatic_commit_in_weekly_job(self):
        text=(Path(__file__).parents[1]/"working-agreement/weekly-review.sh").read_text()
        self.assertNotIn("git commit",text); self.assertNotIn("git add",text)

    def test_reproduce_first_skill_matches_handoff(self):
        text=(ROOT/"reproduce-first-verify/SKILL.md").read_text()
        for phrase in ("### 1. CAPTURE","### 2. REPRODUCE","### 3. TRUSTWORTHINESS GATE","### 4. VERIFY","### 5. INSERT + ONE Live Confirmation","### 6. REPORT","GF-N3-LEASE-ORPHAN","GF-N3-RESEARCH-ACTIVE-RUN-NOT-ADOPTED","runtime close_agent"):
            self.assertIn(phrase,text)
        self.assertIn("red-before / green-after",text.lower())
        for flag in ("--resume-from-checkpoint","--expected-spec-hash","--validate-only","--start-validation-round","--start-feature-index"):
            self.assertIn(flag,text)

    def test_verify_plan_owns_obligation_level_completion(self):
        text=(ROOT/"verify-plan/SKILL.md").read_text()
        for phrase in (
            "--plan-sha256",
            "--evidence-revision-sha256",
            "next-assignment",
            "assigned obligation IDs",
            "SUPPORTED",
            "GAP",
            "BLOCKED",
            "inventory completeness",
            ".verify-plan/critic-outputs/",
            "BLOCKED never counts as complete",
            "section, evidence, and dependency bindings",
        ):
            self.assertIn(phrase,text)
        self.assertIn("coarse coverage status cannot establish completion",text)

    def test_planner_v2_staged_consumers_share_one_canonical_provider(self):
        repo=Path(__file__).parents[1]
        candidate=ROOT/"plan-playbook"
        with tempfile.TemporaryDirectory() as raw:
            skills=Path(raw)/"skills"
            shutil.copytree(candidate,skills/"plan-playbook")
            shutil.rmtree(skills/"plan-playbook"/"integration")
            shutil.copytree(ROOT/"_shared",skills/"_shared")
            for name in ("task-workflow","playbook-convergence-loop"):
                destination=skills/name
                destination.mkdir()
                shutil.copy2(candidate/"integration"/f"{name}.SKILL.md",destination/"SKILL.md")

            provider=skills/"plan-playbook"/"scripts"/"plan_package.py"
            outer=skills/"_shared"/"convergence_state.py"
            provider_help=subprocess.run(
                [sys.executable,str(provider),"--help"],
                cwd=Path(raw),capture_output=True,text=True,check=True,
            ).stdout
            outer_help=subprocess.run(
                [sys.executable,str(outer),"--help"],
                cwd=Path(raw),capture_output=True,text=True,check=True,
            ).stdout
            provider_commands=set(re.findall(r"\b[a-z][a-z-]+\b",provider_help))
            outer_commands=set(re.findall(r"\b[a-z][a-z-]+\b",outer_help))

            task=(skills/"task-workflow"/"SKILL.md").read_text()
            convergence=(skills/"playbook-convergence-loop"/"SKILL.md").read_text()
            for text in (task,convergence):
                referenced=set(re.findall(
                    r"skills/plan-playbook/scripts/plan_package\.py ([a-z][a-z-]+)",text,
                ))
                self.assertTrue(referenced)
                self.assertEqual(referenced-provider_commands,set())

            referenced_outer=set(re.findall(
                r"skills/_shared/convergence_state\.py ([a-z][a-z-]+)",convergence,
            ))
            self.assertTrue(referenced_outer)
            self.assertEqual(referenced_outer-outer_commands,set())
            self.assertEqual(task.count("Invoke canonical `$plan-playbook` exactly once"),1)
            self.assertEqual(convergence.count("Invoke canonical `plan-playbook` exactly once"),1)
            self.assertIn("analysis.md` is a non-package sibling",task)
            self.assertIn("<task-root>/.plan-playbook/",task)
            self.assertIn("IMPLEMENTATION_APPROVAL_REQUIRED",task)
            self.assertIn("validate-package",task)
            self.assertIn("validate-implementation-authorization",task)
            self.assertIn("never asks the user twice",convergence)
            self.assertIn("Pass its result file unchanged",convergence)
            self.assertIn("Do not invoke `verify-plan`",convergence)
            research_stages=convergence.split("## Stage Order",1)[1].split(
                "## Planner Integration",1
            )[0]
            self.assertIn("research-owned and are not plan gates",research_stages)
            for text in (task,convergence):
                self.assertNotIn("$plan-playbook-v2",text)
                self.assertNotIn("skills/plan-playbook-v2/",text)
            self.assertTrue((repo/"skills/task-workflow/SKILL.md").is_file())
            self.assertTrue((repo/"skills/playbook-convergence-loop/SKILL.md").is_file())


if __name__ == "__main__": unittest.main()
