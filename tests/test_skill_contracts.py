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

    def test_no_automatic_commit_in_weekly_job(self):
        text=(Path(__file__).parents[1]/"working-agreement/weekly-review.sh").read_text()
        self.assertNotIn("git commit",text); self.assertNotIn("git add",text)

    def test_reproduce_first_is_internal_pdi_support_not_selectable(self):
        pdi=(ROOT/"prototype-driven-implementation/SKILL.md").read_text()
        contract=" ".join((ROOT/"prototype-driven-implementation/contracts/reproduce-first-support.md").read_text().split())
        managed=(ROOT/"managed-skills.txt").read_text().splitlines()
        self.assertFalse((ROOT/"reproduce-first-verify/SKILL.md").exists())
        self.assertNotIn("reproduce-first-verify",managed)
        self.assertIn("contracts/reproduce-first-support.md",pdi)
        for phrase in (
            "captured live failing state",
            "same real code path",
            "red-before / green-after",
            "one closest valid live confirmation",
            "normal direct prototype proof",
            "PDI retains lifecycle control",
        ):
            self.assertIn(phrase,contract)

    def test_plan_playbook_is_retired_into_direct_planning_and_pdi_support(self):
        repo=Path(__file__).parents[1]
        pdi=(ROOT/"prototype-driven-implementation/SKILL.md").read_text()
        plan_support=(ROOT/"prototype-driven-implementation/references/plan-support.md").read_text()
        plan_contract=(ROOT/"prototype-driven-implementation/contracts/plan-support.md").read_text()
        intake=(ROOT/"task-intake/SKILL.md").read_text()
        managed=(ROOT/"managed-skills.txt").read_text().splitlines()
        self.assertFalse((ROOT/"plan-playbook").exists())
        self.assertNotIn("plan-playbook",managed)
        self.assertNotIn("plan-playbook",intake+pdi+plan_support)
        self.assertIn("direct evidence inspection for Plan",intake)
        self.assertIn("contracts/plan-support.md",plan_support)
        self.assertIn("behavioral boundary",plan_support)
        self.assertIn("PDI alone",plan_contract)
        self.assertIn("name: prototype-driven-implementation",pdi)
        self.assertIn("`prototype-driven-implementation` for Write code",intake)
        self.assertFalse((repo/"skills/task-workflow").exists())
        self.assertIn("prototype-driven-implementation",managed)


if __name__ == "__main__": unittest.main()
