import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
SPEC = importlib.util.spec_from_file_location("prepared_execution", BASE / "prepared_execution.py")
prepared_execution = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepared_execution)


class ReviewEvidenceTest(unittest.TestCase):
    def reference(self, path):
        return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def test_includes_small_text_verbatim(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.md"
            path.write_text("observed evidence")
            item = prepared_execution.review_evidence(self.reference(path))
        self.assertEqual(item["transport"], "full_text")
        self.assertEqual(item["text"], "observed evidence")

    def test_compacts_oversized_text_and_preserves_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "vendor.json"
            path.write_text("x" * (prepared_execution.MAX_REVIEW_ARTIFACT_BYTES + 1))
            reference = self.reference(path)
            item = prepared_execution.review_evidence(reference)
        metadata = json.loads(item["text"])
        self.assertEqual(item["transport"], "verified_metadata_only")
        self.assertEqual(metadata["sha256"], reference["sha256"])
        self.assertEqual(metadata["size_bytes"], prepared_execution.MAX_REVIEW_ARTIFACT_BYTES + 1)
        self.assertTrue(metadata["raw_evidence_preserved"])
        self.assertFalse(metadata["content_included"])

    def test_projects_process_without_repeating_streams(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "case.process.json"
            path.write_text(json.dumps({"command": ["php", "probe.php"], "exit_status": 0,
                                        "stdout": "result" * 100, "stderr": ""}))
            item = prepared_execution.review_evidence(self.reference(path))
        projection = json.loads(item["text"])
        self.assertEqual(item["transport"], "process_projection")
        self.assertEqual(projection["exit_status"], 0)
        self.assertFalse(projection["stdout"]["content_included"])

    def test_projects_large_trace_fields_without_losing_small_facts(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "case.trace.json"
            path.write_text(json.dumps({"status": "observed", "checks": [{"ok": True}],
                                        "queries": ["x" * prepared_execution.MAX_REVIEW_JSON_FIELD_BYTES]}))
            item = prepared_execution.review_evidence(self.reference(path))
        projection = json.loads(item["text"])
        self.assertEqual(item["transport"], "bounded_json_projection")
        self.assertEqual(projection["status"], "observed")
        self.assertEqual(projection["checks"], [{"ok": True}])
        self.assertFalse(projection["queries"]["content_included"])

    def test_retains_complete_trace_field_within_proven_sixteen_kilobyte_budget(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "case.trace.json"
            checks = [{"name": "x" * 15000, "observed_expected": True}]
            path.write_text(json.dumps({"status": "observed", "checks": checks}))
            item = prepared_execution.review_evidence(self.reference(path))
        projection = json.loads(item["text"])
        self.assertEqual(item["transport"], "bounded_json_projection")
        self.assertEqual(projection["checks"], checks)

    def test_paired_stdout_is_metadata_only(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            stdout = root / "case.stdout.txt"
            trace = root / "case.trace.json"
            stdout.write_text("duplicated observation")
            trace.write_text("{}")
            item = prepared_execution.review_evidence(self.reference(stdout))
        self.assertEqual(item["transport"], "verified_metadata_only")
        self.assertFalse(json.loads(item["text"])["content_included"])

    def test_source_manifest_preserves_identity_without_text(self):
        result = prepared_execution.source_manifest([{"path": "app/Foo.php", "text": "<?php echo 1;"}])
        self.assertEqual(result[0]["path"], "app/Foo.php")
        self.assertNotIn("text", result[0])
        self.assertFalse(result[0]["content_included"])

    def test_accepts_multiple_independently_resolving_citations(self):
        answer = {"cases": [{"id": "case-1", "verdict": "supported", "reason": "because",
                              "citations": [{"evidence_path": "one.json", "quote": "first"},
                                            {"evidence_path": "two.json", "quote": "second"}]}]}
        prepared_execution.validate_review_citations(
            answer, ["case-1"], {"one.json": "the first fact", "two.json": "the second fact"})

    def test_rejects_joined_paths_and_quotes(self):
        answer = {"cases": [{"id": "case-1", "verdict": "supported", "reason": "because",
                              "citations": [{"evidence_path": "one.json; two.json",
                                             "quote": "first; second"}]}]}
        with self.assertRaisesRegex(ValueError, "citation does not resolve"):
            prepared_execution.validate_review_citations(
                answer, ["case-1"], {"one.json": "first", "two.json": "second"})

    def test_recognizes_only_exact_superseded_review_shape(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "attempts" / "0001").mkdir(parents=True)
            answer = {"cases": [{"id": "case-1", "verdict": "supported", "reason": "because",
                                  "evidence_path": "one.json", "quote": "fact"}],
                      "conclusion": "done", "implementation_consequence": "next"}
            (root / "attempts" / "0001" / "answer.json").write_text(json.dumps(answer))
            (root / "step.json").write_text(json.dumps({
                "status": "completed", "session": "session-1",
                "answer_file": "attempts/0001/answer.json"}))
            saved = prepared_execution.saved_legacy_review(root, ["case-1"])
        self.assertEqual(saved, (answer, "session-1"))


class ResumeBindingsTest(unittest.TestCase):
    def test_reuses_receipted_execution_without_rewriting_bindings(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "attempt"
            (output / "receipts").mkdir(parents=True)
            (output / "execution").mkdir()
            preparation = root / "preparation.json"
            selection = root / "selection.json"
            cycle_path = root / "cycle.json"
            request = root / "request.json"
            assignment = root / "assignment.json"
            builder = root / "builder.py"
            runtime = root / "runtime.json"
            generation = output / "receipts" / "generation.json"
            execution = output / "execution" / "result.json"
            for path in [preparation, selection, request, assignment, runtime, generation, execution]:
                path.write_text("{}")
            builder.write_text("# builder\n")
            cycle_path.write_text(json.dumps({"selection": prepared_execution.ref(selection)}))
            bindings = {
                "preparation": prepared_execution.ref(preparation),
                "original_request": prepared_execution.ref(request),
                "request": prepared_execution.ref(request),
                "assignment": prepared_execution.ref(assignment),
                "builder": prepared_execution.ref(builder),
                "runtime": {"receipt": prepared_execution.ref(runtime)},
                "selection": prepared_execution.ref(selection),
            }
            bindings_path = output / "bindings.json"
            bindings_path.write_text(json.dumps(bindings))
            original = bindings_path.read_bytes()
            state = {
                "stage": "build",
                "pending": {"action": "prepare_build"},
                "root": str(root),
                "cycle": str(cycle_path),
                "selection_preparation": {
                    "path": preparation.name,
                    "sha256": prepared_execution.sha(preparation),
                },
            }
            result = prepared_execution.resume_bindings(state, output)
            self.assertEqual(result, bindings)
            self.assertEqual(bindings_path.read_bytes(), original)

    def test_completed_execution_loads_without_runtime_adapter(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "attempt"
            (output / "execution").mkdir(parents=True)
            for name in ["stdout.txt", "stderr.txt", "command.json", "isolation.json"]:
                (output / name).write_text("{}")
            result = {
                "output_files": [],
                "stdout": prepared_execution.ref(output / "stdout.txt"),
                "stderr": prepared_execution.ref(output / "stderr.txt"),
                "command": prepared_execution.ref(output / "command.json"),
                "isolation": prepared_execution.ref(output / "isolation.json"),
                "protected_changes": [],
            }
            (output / "execution" / "result.json").write_text(json.dumps(result))
            original_verify_generation = prepared_execution.verify_generation
            prepared_execution.verify_generation = lambda generation, request, skills: output / "candidate"
            try:
                loaded = prepared_execution.completed_execution(output, output / "request.json", root / "skills")
            finally:
                prepared_execution.verify_generation = original_verify_generation
            self.assertEqual(loaded, result)


class CompletedHandoffBridgeTest(unittest.TestCase):
    def test_reuses_completed_handoff_and_exports_bound_research_result(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "attempt"
            (output / "generation").mkdir(parents=True)
            (output / "execution").mkdir()
            generation = output / "generation" / "result.json"
            execution = output / "execution" / "result.json"
            evidence = output / "execution" / "observed.txt"
            generation.write_text('{}\n')
            execution.write_text('{}\n')
            evidence.write_text('observed exact fact\n')
            selection = {"path": "selection.json", "sha256": "selection-sha"}
            goal = {"path": "goal.json", "sha256": "goal-sha"}
            cycle = root / "cycle.json"
            cycle.write_text(json.dumps({"goal": goal, "selection": selection}))
            handoff = {
                "status": "experiment_needs_attention",
                "selection": selection,
                "generation": prepared_execution.ref(generation),
                "execution": prepared_execution.ref(execution),
                "review": {"cases": [{"id": "case-1", "citations": [{
                    "evidence_path": str(evidence), "quote": "exact fact"}]}]},
            }
            (output / "handoff.json").write_text(json.dumps(handoff))
            state = {"root": str(root), "cycle": str(cycle)}
            original_resume = prepared_execution.resume_bindings
            original_prepare = prepared_execution.prepare
            prepared_execution.resume_bindings = lambda *_args, **_kwargs: {"selection": selection}
            prepared_execution.prepare = lambda *_args, **_kwargs: self.fail("prepare must not run")
            try:
                result = prepared_execution.execute(state, output)
            finally:
                prepared_execution.resume_bindings = original_resume
                prepared_execution.prepare = original_prepare
            self.assertEqual(result["model_calls"], 0)
            exported = json.loads(Path(result["research_result"]).read_text())
            self.assertEqual(exported["kind"], "selected_research_result")
            self.assertEqual(exported["goal"], goal)
            self.assertEqual(exported["selection"], selection)
            self.assertEqual(len(exported["evidence"]), 4)

    def test_rejects_changed_cited_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "attempt"
            (output / "generation").mkdir(parents=True)
            (output / "execution").mkdir()
            generation = output / "generation" / "result.json"
            execution = output / "execution" / "result.json"
            evidence = output / "execution" / "observed.txt"
            generation.write_text('{}\n')
            execution.write_text('{}\n')
            evidence.write_text('different text\n')
            selection = {"path": "selection.json", "sha256": "selection-sha"}
            cycle = root / "cycle.json"
            cycle.write_text(json.dumps({"goal": {}, "selection": selection}))
            handoff = {
                "selection": selection,
                "generation": prepared_execution.ref(generation),
                "execution": prepared_execution.ref(execution),
                "review": {"cases": [{"id": "case-1", "citations": [{
                    "evidence_path": str(evidence), "quote": "missing quote"}]}]},
            }
            (output / "handoff.json").write_text(json.dumps(handoff))
            with self.assertRaisesRegex(ValueError, "citation no longer resolves"):
                prepared_execution.completed_handoff(
                    {"root": str(root), "cycle": str(cycle)}, output, {"selection": selection})


if __name__ == "__main__":
    unittest.main()
