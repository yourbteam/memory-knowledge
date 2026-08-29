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

    def test_legacy_phase_categorization_foundry_is_retired(self):
        managed=(ROOT/"managed-skills.txt").read_text().splitlines()
        current=" ".join((ROOT/"phase-ledger-category-contract-foundry/SKILL.md").read_text().split())
        self.assertFalse((ROOT/"phase-categorization-foundry/SKILL.md").exists())
        self.assertNotIn("phase-categorization-foundry",managed)
        self.assertIn("phase-ledger-category-contract-foundry",managed)
        for phrase in (
            "phase_purpose",
            "input_context",
            "upstream inputs",
            "downstream consumers",
            "universal orchestration contract",
            "general hollow personas",
            "general contract manager",
            "without phase-specific persona instructions",
        ):
            self.assertIn(phrase,current)

    def test_blocker_catalog_is_code_owned_not_selectable(self):
        agreement=(ROOT/"working-agreement/SKILL.md").read_text()
        pdi=(ROOT/"prototype-driven-implementation/SKILL.md").read_text()
        runner=(ROOT/"sequence-runner/SKILL.md").read_text()
        managed=(ROOT/"managed-skills.txt").read_text().splitlines()
        self.assertFalse((ROOT/"blocker-catalog").exists())
        self.assertNotIn("blocker-catalog",managed)
        for owner in (agreement,pdi,runner):
            self.assertIn("python3 scripts/blocker_catalog.py open",owner)
        self.assertIn("first execution error once immediately",agreement)
        self.assertIn("same-path verification",runner)

    def test_task_intake_is_retired_without_losing_code_classification(self):
        agreement=(ROOT/"working-agreement/SKILL.md").read_text()
        runner=(ROOT/"sequence-runner/SKILL.md").read_text()
        managed=(ROOT/"managed-skills.txt").read_text().splitlines()
        self.assertFalse((ROOT/"task-intake").exists())
        self.assertNotIn("task-intake",managed)
        self.assertIn("python3 scripts/work_memory.py classify",agreement)
        self.assertIn("`non-operational`",agreement)
        self.assertIn("canonical code classifier",runner)
        for kind in (
            "image", "container", "auth", "deploy", "workflow-drive", "package",
            "database", "remote-operator", "cleanup", "publish", "other", "read-only",
            "single-test", "single-build",
        ):
            self.assertIn(kind,agreement)

    def test_plan_playbook_is_retired_into_direct_planning_and_pdi_support(self):
        repo=Path(__file__).parents[1]
        pdi=(ROOT/"prototype-driven-implementation/SKILL.md").read_text()
        plan_support=(ROOT/"prototype-driven-implementation/references/plan-support.md").read_text()
        plan_contract=(ROOT/"prototype-driven-implementation/contracts/plan-support.md").read_text()
        intake=(ROOT/"working-agreement/SKILL.md").read_text()
        managed=(ROOT/"managed-skills.txt").read_text().splitlines()
        self.assertFalse((ROOT/"plan-playbook").exists())
        self.assertNotIn("plan-playbook",managed)
        self.assertNotIn("plan-playbook",intake+pdi+plan_support)
        self.assertIn("Plan: direct inspection of declared real evidence",intake)
        self.assertIn("contracts/plan-support.md",plan_support)
        self.assertIn("behavioral boundary",plan_support)
        self.assertIn("PDI alone",plan_contract)
        self.assertIn("name: prototype-driven-implementation",pdi)
        self.assertIn("Write code: `prototype-driven-implementation`",intake)
        self.assertFalse((repo/"skills/task-workflow").exists())
        self.assertIn("prototype-driven-implementation",managed)


if __name__ == "__main__": unittest.main()
