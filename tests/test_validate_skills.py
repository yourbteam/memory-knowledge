import importlib.util
import tempfile
import unittest
import os
from pathlib import Path

ROOT=Path(__file__).parents[1]; spec=importlib.util.spec_from_file_location("validator",ROOT/"working-agreement/validate_skills.py"); v=importlib.util.module_from_spec(spec); spec.loader.exec_module(v)


class ValidatorTests(unittest.TestCase):
    def validate_openai(self, content):
        with tempfile.TemporaryDirectory() as raw:
            path=Path(raw)/"openai.yaml"; path.write_text(content)
            return v.validate_openai(path)

    def test_block_description_and_metadata(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); skill=root/"sample"; skill.mkdir(); (root/"managed-skills.txt").write_text("sample\n")
            (skill/"SKILL.md").write_text("---\nname: sample\ndescription: |\n  line one\n  line two\nmetadata:\n  ignored: yes\n---\n# Sample\n")
            self.assertEqual(v.validate(root,root/"managed-skills.txt"),[])

    def test_junk_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); skill=root/"sample"; skill.mkdir(); (root/"managed-skills.txt").write_text("sample\n")
            (skill/"SKILL.md").write_text("---\nname: sample\ndescription: ok\n---\n")
            (skill/".DS_Store").write_text("x")
            self.assertTrue(v.validate(root,root/"managed-skills.txt"))

    def test_duplicate_frontmatter_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); skill=root/"sample"; skill.mkdir(); (root/"managed-skills.txt").write_text("sample\n")
            (skill/"SKILL.md").write_text("---\nname: sample\nname: sample\ndescription: ok\n---\n")
            self.assertTrue(v.validate(root,root/"managed-skills.txt"))

    def test_wrong_ui_root_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); skill=root/"sample"; (skill/"agents").mkdir(parents=True); (root/"managed-skills.txt").write_text("sample\n")
            (skill/"SKILL.md").write_text("---\nname: sample\ndescription: ok\n---\n")
            (skill/"agents/openai.yaml").write_text("wrong_root:\n  display_name: x\n  short_description: y\n  default_prompt: z\n")
            self.assertTrue(v.validate(root,root/"managed-skills.txt"))

    def test_empty_shared_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); (root/"_shared").mkdir(); (root/"managed-skills.txt").write_text("_shared\n")
            self.assertTrue(v.validate(root,root/"managed-skills.txt"))

    def test_yaml_non_string_scalars_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); skill=root/"sample"; (skill/"agents").mkdir(parents=True); (root/"managed-skills.txt").write_text("sample\n")
            (skill/"SKILL.md").write_text("---\nname: sample\ndescription: null\n---\n")
            (skill/"agents/openai.yaml").write_text("interface:\n  display_name: null\n  short_description: true\n  default_prompt: 123\n")
            self.assertTrue(v.validate(root,root/"managed-skills.txt"))

    def test_candidate_explicit_only_metadata_is_valid(self):
        errors=self.validate_openai(
            "interface:\n"
            "  display_name: Research Playbook V2\n"
            "  short_description: Research policy\n"
            "  default_prompt: Run the research playbook\n"
            "policy:\n"
            "  allow_implicit_invocation: false\n"
        )
        self.assertEqual(errors,[])

    def test_blocker_catalog_skill_is_retired_without_losing_ledger_ownership(self):
        managed=(ROOT/"skills/managed-skills.txt").read_text().splitlines()
        projections=(ROOT/"working-agreement/client-skill-projections.json").read_text()
        agreement=(ROOT/"skills/working-agreement/SKILL.md").read_text()
        pdi=(ROOT/"skills/prototype-driven-implementation/SKILL.md").read_text()
        runner=(ROOT/"skills/sequence-runner/SKILL.md").read_text()
        self.assertFalse((ROOT/"skills/blocker-catalog").exists())
        self.assertTrue((ROOT/"scripts/blocker_catalog.py").is_file())
        self.assertNotIn("blocker-catalog",managed)
        self.assertNotIn('"blocker-catalog"',projections)
        for owner in (agreement,pdi,runner):
            self.assertIn("python3 scripts/blocker_catalog.py open",owner)

    def test_task_intake_is_retired_into_working_agreement_classifier(self):
        managed=(ROOT/"skills/managed-skills.txt").read_text().splitlines()
        projections=(ROOT/"working-agreement/client-skill-projections.json").read_text()
        agreement=(ROOT/"skills/working-agreement/SKILL.md").read_text()
        runner=(ROOT/"skills/sequence-runner/SKILL.md").read_text()
        self.assertFalse((ROOT/"skills/task-intake").exists())
        self.assertNotIn("task-intake",managed)
        self.assertNotIn('"task-intake"',projections)
        self.assertIn("python3 scripts/work_memory.py classify",agreement)
        self.assertIn("`operational` receipt",runner)

    def test_research_playbook_is_retired(self):
        managed=(ROOT/"skills/managed-skills.txt").read_text().splitlines()
        self.assertNotIn("research-playbook",managed)
        self.assertNotIn("research-playbook-v2",managed)
        self.assertFalse((ROOT/"skills/research-playbook").exists())

    def test_doc_gap_closure_loop_is_retired(self):
        managed=(ROOT/"skills/managed-skills.txt").read_text().splitlines()
        projections=(ROOT/"working-agreement/client-skill-projections.json").read_text()
        self.assertNotIn("doc-gap-closure-loop",managed)
        self.assertNotIn('"doc-gap-closure-loop"',projections)
        self.assertFalse((ROOT/"skills/doc-gap-closure-loop").exists())

    def test_verify_analysis_is_retired(self):
        managed=(ROOT/"skills/managed-skills.txt").read_text().splitlines()
        projections=(ROOT/"working-agreement/client-skill-projections.json").read_text()
        self.assertNotIn("verify-analysis",managed)
        self.assertNotIn('"verify-analysis"',projections)
        self.assertFalse((ROOT/"skills/verify-analysis").exists())

    def test_verify_plan_is_retired_with_standalone_direct_planning(self):
        managed=(ROOT/"skills/managed-skills.txt").read_text().splitlines()
        projections=(ROOT/"working-agreement/client-skill-projections.json").read_text()
        intake=(ROOT/"skills/working-agreement/SKILL.md").read_text()
        self.assertNotIn("verify-plan",managed)
        self.assertNotIn('"verify-plan"',projections)
        self.assertFalse((ROOT/"skills/verify-plan").exists())
        self.assertNotIn("`verify-plan`",intake)
        self.assertIn("Plan: direct inspection of declared real evidence",intake)

    def test_task_workflow_is_retired_into_direct_mode_routes(self):
        managed=(ROOT/"skills/managed-skills.txt").read_text().splitlines()
        projections=(ROOT/"working-agreement/client-skill-projections.json").read_text()
        intake=(ROOT/"skills/working-agreement/SKILL.md").read_text()
        pdi=(ROOT/"skills/prototype-driven-implementation/SKILL.md").read_text()
        self.assertNotIn("task-workflow",managed)
        self.assertNotIn('"task-workflow"',projections)
        self.assertFalse((ROOT/"skills/task-workflow").exists())
        self.assertNotIn("task-workflow",intake+pdi)
        self.assertIn("sequence-runner",intake)
        self.assertIn("name: prototype-driven-implementation",pdi)

    def test_plan_playbook_is_retired_into_direct_planning_and_pdi_support(self):
        managed=(ROOT/"skills/managed-skills.txt").read_text().splitlines()
        projections=(ROOT/"working-agreement/client-skill-projections.json").read_text()
        intake=(ROOT/"skills/working-agreement/SKILL.md").read_text()
        pdi=(ROOT/"skills/prototype-driven-implementation/SKILL.md").read_text()
        support=(ROOT/"skills/prototype-driven-implementation/references/plan-support.md").read_text()
        contract=(ROOT/"skills/prototype-driven-implementation/contracts/plan-support.md").read_text()
        directives=(ROOT/"working-agreement/DIRECTIVES.md").read_text()
        self.assertNotIn("plan-playbook",managed)
        self.assertNotIn('"plan-playbook"',projections)
        self.assertFalse((ROOT/"skills/plan-playbook").exists())
        self.assertNotIn("plan-playbook",intake+pdi+support+directives)
        self.assertIn("Plan: direct inspection of declared real evidence",intake)
        self.assertIn("contracts/plan-support.md",support)
        self.assertIn("PDI alone",contract)

    def test_write_code_playbook_is_retired_into_pdi_internal_support(self):
        managed=(ROOT/"skills/managed-skills.txt").read_text().splitlines()
        projections=(ROOT/"working-agreement/client-skill-projections.json").read_text()
        pdi=(ROOT/"skills/prototype-driven-implementation/SKILL.md").read_text()
        support=(ROOT/"skills/prototype-driven-implementation/references/write-code-support.md").read_text()
        directives=(ROOT/"working-agreement/DIRECTIVES.md").read_text()
        self.assertNotIn("write-code-playbook",managed)
        self.assertNotIn('"write-code-playbook"',projections)
        self.assertFalse((ROOT/"skills/write-code-playbook").exists())
        self.assertNotIn("standalone Plan and Write-code",pdi)
        self.assertNotIn("write-code-playbook",pdi+directives)
        self.assertIn("contracts/write-code-support.md",support)
        self.assertIn("Central controller for every code implementation",pdi)

    def test_auto_capture_is_retired_while_explicit_corpus_add_remains(self):
        managed=(ROOT/"skills/managed-skills.txt").read_text().splitlines()
        projections=(ROOT/"working-agreement/client-skill-projections.json").read_text()
        agreement=(ROOT/"skills/working-agreement/SKILL.md").read_text()
        setup=(ROOT/"working-agreement/SETUP-claude.md").read_text()
        self.assertNotIn("auto-capture",managed)
        self.assertNotIn('"auto-capture"',projections)
        self.assertFalse((ROOT/"skills/auto-capture").exists())
        self.assertNotIn("auto-capture",agreement+setup)
        self.assertIn("corpus-add",managed)
        self.assertTrue((ROOT/"skills/corpus-add/SKILL.md").is_file())

    def test_requirements_coverage_gap_loop_is_retired(self):
        managed=(ROOT/"skills/managed-skills.txt").read_text().splitlines()
        projections=(ROOT/"working-agreement/client-skill-projections.json").read_text()
        self.assertNotIn("requirements-coverage-gap-loop",managed)
        self.assertNotIn('"requirements-coverage-gap-loop"',projections)
        self.assertFalse((ROOT/"skills/requirements-coverage-gap-loop").exists())

    def test_requirements_satisfaction_gap_loop_is_retired(self):
        managed=(ROOT/"skills/managed-skills.txt").read_text().splitlines()
        projections=(ROOT/"working-agreement/client-skill-projections.json").read_text()
        self.assertNotIn("requirements-satisfaction-gap-loop",managed)
        self.assertNotIn('"requirements-satisfaction-gap-loop"',projections)
        self.assertFalse((ROOT/"skills/requirements-satisfaction-gap-loop").exists())

    def test_policy_accepts_exact_unquoted_yaml_booleans(self):
        for value in ("true","false"):
            with self.subTest(value=value):
                errors=self.validate_openai(
                    "interface:\n"
                    "  display_name: Sample\n"
                    "  short_description: Sample policy\n"
                    "  default_prompt: Run sample\n"
                    "policy:\n"
                    f"  allow_implicit_invocation: {value}\n"
                )
                self.assertEqual(errors,[])

    def test_policy_rejects_quoted_booleans(self):
        for value in ('"false"',"'true'"):
            with self.subTest(value=value):
                errors=self.validate_openai(
                    "interface:\n"
                    "  display_name: Sample\n"
                    "  short_description: Sample policy\n"
                    "  default_prompt: Run sample\n"
                    "policy:\n"
                    f"  allow_implicit_invocation: {value}\n"
                )
                self.assertTrue(any("must be an unquoted YAML boolean" in error for error in errors))

    def test_unknown_duplicate_and_malformed_policy_shapes_are_rejected(self):
        base=(
            "interface:\n"
            "  display_name: Sample\n"
            "  short_description: Sample policy\n"
            "  default_prompt: Run sample\n"
        )
        cases={
            "unknown section": base+"permissions:\n  allow_implicit_invocation: false\n",
            "duplicate policy section": base+"policy:\n  allow_implicit_invocation: false\npolicy:\n  allow_implicit_invocation: true\n",
            "scalar policy section": base+"policy: false\n",
            "missing policy key": base+"policy:\n",
            "unknown policy key": base+"policy:\n  implicit: false\n",
            "duplicate policy key": base+"policy:\n  allow_implicit_invocation: false\n  allow_implicit_invocation: true\n",
            "malformed policy key": base+"policy:\n    allow_implicit_invocation: false\n",
        }
        for name,content in cases.items():
            with self.subTest(name=name):
                self.assertTrue(self.validate_openai(content))

    def test_policy_does_not_bypass_interface_validation(self):
        errors=self.validate_openai(
            "interface:\n"
            "  display_name: Sample\n"
            "policy:\n"
            "  allow_implicit_invocation: false\n"
        )
        self.assertTrue(any("missing interface.short_description" in error for error in errors))
        self.assertTrue(any("missing interface.default_prompt" in error for error in errors))

    def test_documented_wrappers_are_executable(self):
        for name in ("validate-skills.sh","install-skills.sh","sync-corpus.sh"):
            self.assertTrue(os.access(ROOT/"working-agreement"/name,os.X_OK),name)


if __name__ == "__main__": unittest.main()
