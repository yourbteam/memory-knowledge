import unittest
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).parents[1]/"skills"


class ContractTests(unittest.TestCase):
    def test_pdi_owns_grounded_write_code_work_and_internal_support(self):
        prototype=(ROOT/"prototype-driven-implementation/SKILL.md").read_text()
        write_support=(ROOT/"prototype-driven-implementation/references/write-code-support.md").read_text()
        managed=(ROOT/"managed-skills.txt").read_text().splitlines()
        self.assertFalse((ROOT/"write-code-playbook").exists())
        self.assertNotIn("write-code-playbook",managed)
        self.assertIn("real captured success and failure cases",prototype)
        self.assertIn("promote",prototype)
        self.assertIn("revise",prototype)
        self.assertIn("discard",prototype)
        self.assertIn("prototype-driven-implementation",managed)
        self.assertIn("contracts/write-code-support.md",write_support)
        self.assertIn("Change only the approved delta",write_support)
        self.assertIn("Return control",write_support)

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

    def test_planner_and_pdi_are_direct_lifecycle_owners(self):
        repo=Path(__file__).parents[1]
        plan=(ROOT/"plan-playbook/SKILL.md").read_text()
        pdi=(ROOT/"prototype-driven-implementation/SKILL.md").read_text()
        intake=(ROOT/"task-intake/SKILL.md").read_text()
        managed=(ROOT/"managed-skills.txt").read_text().splitlines()
        provider=ROOT/"plan-playbook/scripts/plan_package.py"
        provider_help=subprocess.run(
            [sys.executable,str(provider),"--help"],
            cwd=repo,capture_output=True,text=True,check=True,
        ).stdout

        self.assertIn("validate-package",provider_help)
        self.assertIn("validate-implementation-authorization",provider_help)
        self.assertIn("name: plan-playbook",plan)
        self.assertIn("name: prototype-driven-implementation",pdi)
        self.assertIn("`plan-playbook` for Plan",intake)
        self.assertIn("`prototype-driven-implementation` for Write code",intake)
        self.assertNotIn("task-workflow",plan+intake)
        self.assertFalse((repo/"skills/task-workflow").exists())
        self.assertIn("plan-playbook",managed)
        self.assertIn("prototype-driven-implementation",managed)


if __name__ == "__main__": unittest.main()
