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

    def test_schema_arguments_and_abbreviations_are_refused(self):
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

class DescriptionExporterBoundaryTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.temporary = tempfile.TemporaryDirectory(prefix="description-boundary-")
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name).resolve()
        spec = importlib.util.spec_from_file_location("description_exporter", MODULE)
        self.exporter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.exporter)

    def test_rejects_duplicate_json_keys(self):
        with self.assertRaisesRegex(self.exporter.ExportError, "duplicate JSON key"):
            self.exporter.json_value(b'{"id":"q1","id":"q1"}', "reader")

    def test_excluded_alias_is_refused_before_run_access(self):
        out = self.work / "output"
        out.mkdir()
        alias = self.work / "alias"
        alias.symlink_to(out, target_is_directory=True)
        with self.assertRaisesRegex(self.exporter.ExportError, "linked aliases are forbidden"):
            self.exporter.publish(self.work / "missing-run", out, out / "handoff.json", [alias], [MODULE])
        self.assertEqual(list(out.iterdir()), [])

    def test_duplicate_source_objects_violate_internal_contract(self):
        e = self.exporter
        h = {key: "a" * 64 for key in e.HANDOFF_FIELDS}
        h.update(schema_version=1, machinery="description-machinery", contract_version=1,
                 run_identity=str(self.work), terminal_state="complete",
                 description={"path": str(MODULE), "sha256": "a" * 64},
                 reader_records=[{"question_id": q, "seat": s, "path": str(MODULE),
                                  "sha256": "a" * 64, "answer_sha256": "a" * 64}
                                 for q in e.QUESTION_IDS for s in e.READER_SEATS],
                 source_objects=[{"origin": str(MODULE), "sha256": "a" * 64}] * 2)
        h["handoff_sha256"] = e.digest(e.canonical({k:v for k,v in h.items() if k != "handoff_sha256"}))
        with self.assertRaisesRegex(e.ExportError, "duplicate source objects"):
            e.validate_handoff(h)

    def test_rejects_nonfinite_json(self):
        with self.assertRaisesRegex(self.exporter.ExportError, "non-finite"):
            self.exporter.json_value(b'{"answer":NaN}', "reader")

    def test_parent_and_leaf_links_are_refused(self):
        directory = self.work / "actual"
        directory.mkdir()
        source = directory / "source"
        source.write_bytes(b"recorded evidence")
        alias = self.work / "alias"
        alias.symlink_to(directory, target_is_directory=True)
        leaf = self.work / "leaf"
        leaf.symlink_to(source)
        for path in (alias / "source", leaf):
            with self.assertRaises(OSError):
                self.exporter.read_regular(path)
        self.assertEqual(source.read_bytes(), b"recorded evidence")

    def test_hardlink_and_fifo_are_refused(self):
        import os
        source = self.work / "source"
        source.write_bytes(b"captured bytes")
        alias = self.work / "alias"
        os.link(source, alias)
        fifo = self.work / "fifo"
        os.mkfifo(fifo)
        for path in (source, alias, fifo):
            with self.assertRaises(self.exporter.ExportError):
                self.exporter.read_regular(path)

    def test_source_change_before_publication_is_refused(self):
        source = self.work / "source"
        source.write_bytes(b"first observed bytes")
        evidence = self.exporter.Evidence()
        self.assertEqual(evidence.read(source), b"first observed bytes")
        source.write_bytes(b"changed after reading")
        with self.assertRaisesRegex(self.exporter.ExportError, "evidence changed"):
            evidence.verify_unchanged()

    def test_existing_output_is_never_overwritten(self):
        out = self.work / "published"
        out.mkdir()
        target = out / "handoff.json"
        target.write_bytes(b"already published")
        with self.assertRaisesRegex(self.exporter.ExportError, "already exists"):
            self.exporter.publish(self.work / "run", out, target, [ROOT], [MODULE])
        self.assertEqual(target.read_bytes(), b"already published")
        self.assertEqual(list(out.iterdir()), [target])

    def test_export_requires_explicit_publication_boundaries(self):
        result = subprocess.run([sys.executable, str(MODULE), "--run", str(self.work)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("--target-repository", result.stderr)


if __name__ == "__main__":
    unittest.main()
