import importlib.util
import tempfile
import unittest
import os
from pathlib import Path

ROOT=Path(__file__).parents[1]; spec=importlib.util.spec_from_file_location("validator",ROOT/"working-agreement/validate_skills.py"); v=importlib.util.module_from_spec(spec); spec.loader.exec_module(v)


class ValidatorTests(unittest.TestCase):
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

    def test_documented_wrappers_are_executable(self):
        for name in ("validate-skills.sh","install-skills.sh","sync-corpus.sh"):
            self.assertTrue(os.access(ROOT/"working-agreement"/name,os.X_OK),name)


if __name__ == "__main__": unittest.main()
