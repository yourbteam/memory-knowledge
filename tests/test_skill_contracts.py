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

    def test_plan_playbook_owns_obligation_level_completion(self):
        lifecycle=(ROOT/"plan-playbook/references/hardening-lifecycle.md").read_text()
        ledger=(ROOT/"_shared/verification_ledger.py").read_text()
        for phrase in (
            "VERIFY_PLAN=PASS",
            "approved finite inventory",
            "critic-approved `SUPPORTED`",
            "zero GAP/BLOCKED obligations",
            "Coarse section coverage cannot pass this gate",
        ):
            self.assertIn(phrase,lifecycle)
        for phrase in (
            "--plan-sha256",
            "--evidence-revision-sha256",
            "next-assignment",
        ):
            self.assertIn(phrase,ledger)

    def test_planner_v2_staged_consumers_share_one_canonical_provider(self):
        repo=Path(__file__).parents[1]
        candidate=ROOT/"plan-playbook"
        with tempfile.TemporaryDirectory() as raw:
            skills=Path(raw)/"skills"
            shutil.copytree(candidate,skills/"plan-playbook")
            shutil.rmtree(skills/"plan-playbook"/"integration")
            shutil.copytree(ROOT/"_shared",skills/"_shared")
            for name in ("task-workflow",):
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
            for text in (task,):
                referenced=set(re.findall(
                    r"skills/plan-playbook/scripts/plan_package\.py ([a-z][a-z-]+)",text,
                ))
                self.assertTrue(referenced)
                self.assertEqual(referenced-provider_commands,set())

            self.assertEqual(task.count("Invoke canonical `$plan-playbook` exactly once"),1)
            self.assertIn("analysis.md` is a non-package sibling",task)
            self.assertIn("<task-root>/.plan-playbook/",task)
            self.assertIn("IMPLEMENTATION_APPROVAL_REQUIRED",task)
            self.assertIn("validate-package",task)
            self.assertIn("validate-implementation-authorization",task)
            for text in (task,):
                self.assertNotIn("$plan-playbook-v2",text)
                self.assertNotIn("skills/plan-playbook-v2/",text)
            self.assertTrue((repo/"skills/task-workflow/SKILL.md").is_file())


if __name__ == "__main__": unittest.main()
