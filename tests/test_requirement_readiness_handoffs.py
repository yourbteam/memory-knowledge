"""Schema publication remains separate from run certification."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "skills/description-machinery/scripts/export_handoff.py"
SCHEMA = ROOT / "skills/requirement-to-atom-readiness-machinery/schemas/description-handoff.schema.json"

class DescriptionHandoffSchemaTests(unittest.TestCase):
    def test_digest_rejects_trailing_newline(self):
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest("Run schema validation with the project .venv Python")
        schema = json.loads(SCHEMA.read_text())
        digest = schema["properties"]["handoff_sha256"]
        if "$ref" in digest:
            digest = schema["$defs"]["sha256"]
        validator = Draft202012Validator(digest)
        self.assertTrue(validator.is_valid("a" * 64))
        for malformed in ("a" * 64 + "\n", "A" * 64, "a" * 63, "a" * 65):
            self.assertFalse(validator.is_valid(malformed), repr(malformed))

    def test_cli_matches_saved_schema(self):
        run = subprocess.run([sys.executable, str(MODULE), "--schema"],
                             capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(run.stdout), json.loads(SCHEMA.read_text()))
        self.assertEqual(run.stderr, "")

    def test_run_export_and_abbreviated_flags_are_not_exposed(self):
        for args in ([], ["--schema", str(MODULE)], ["--sch"]):
            run = subprocess.run([sys.executable, str(MODULE), *args],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 2)
            self.assertEqual(run.stdout, "")

    def test_each_render_is_independent(self):
        spec = importlib.util.spec_from_file_location("handoff_contract", MODULE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        first = module.handoff_schema()
        first["required"].clear()
        first["properties"]["description"]["required"].clear()
        second = module.handoff_schema()
        self.assertEqual(second["required"], list(module.HANDOFF_FIELDS))
        self.assertEqual(second["properties"]["description"]["required"], ["path", "sha256"])

if __name__ == "__main__":
    unittest.main()
