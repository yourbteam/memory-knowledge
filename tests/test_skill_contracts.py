import unittest
from pathlib import Path

ROOT=Path(__file__).parents[1]/"skills"


class ContractTests(unittest.TestCase):
    def test_convergence_contracts(self):
        convergence=(ROOT/"playbook-convergence-loop/SKILL.md").read_text()
        self.assertIn("bounded autonomy",convergence); self.assertIn("close_agent",convergence); self.assertIn("guard-baseline",convergence)
        stage_order=convergence.split("## Stage Order",1)[1].split("## Review Loop",1)[0]
        playbooks=("research-playbook","plan-playbook","write-code-playbook","review-playbook")
        positions=[stage_order.index(f"`{name}`") for name in playbooks]
        self.assertEqual(positions,sorted(positions))
        self.assertLess(stage_order.index("`review-playbook`"),stage_order.index("`verify-work`"))
        review=(ROOT/"review-playbook/SKILL.md").read_text()
        for phrase in ("playbook-convergence-loop","guard-baseline","assessment-only","stage-result envelope","Default commit policy is `none`"):
            self.assertIn(phrase,review)
        verify=(ROOT/"verify-work/SKILL.md").read_text()
        for phrase in ("staged changes","unstaged changes","untracked files","assessment-only","Do not commit by default"):
            self.assertIn(phrase,verify)

    def test_working_agreement_has_no_range(self):
        text=(ROOT/"working-agreement/SKILL.md").read_text()
        self.assertNotIn("G0-G6",text); self.assertIn("all current",text); self.assertIn("projectless",text)

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


if __name__ == "__main__": unittest.main()
