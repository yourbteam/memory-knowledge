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

    def test_compacts_large_generated_report_but_preserves_primary_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            report = root / "report.md"
            trace = root / "case.trace.json"
            report.write_text("summary" * (prepared_execution.MAX_REVIEW_REPORT_BYTES // 7 + 1))
            trace.write_text(json.dumps({"status": "observed", "checks": [{"ok": True}]}))
            report_item, trace_item = prepared_execution.review_evidence_set(
                [self.reference(report), self.reference(trace)])
        metadata = json.loads(report_item["text"])
        self.assertEqual(report_item["transport"], "verified_metadata_only")
        self.assertFalse(metadata["content_included"])
        self.assertIn("primary code and trace evidence", metadata["omission_reason"])
        self.assertEqual(trace_item["transport"], "bounded_json_projection")
        self.assertEqual(json.loads(trace_item["text"])["checks"], [{"ok": True}])

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

    def test_protected_source_comparison_exports_unchanged_hash_pairs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "experiment" / "run.py"
            report = root / "experiment" / "report.md"
            source.parent.mkdir(parents=True)
            source.write_text("print('run')\n")
            report.write_text("before\n")
            before = [self.reference(source), self.reference(report)]
            report.write_text("after\n")
            results = root / "experiment" / "results"
            results.mkdir()
            (results / "case.trace.json").write_text("{}\n")
            comparison = prepared_execution.protected_source_comparison(root, before)
        self.assertEqual(comparison["status"], "verified_unchanged")
        self.assertEqual(comparison["changes"], [])
        self.assertEqual(comparison["protected_source_count"], 1)
        self.assertEqual(comparison["files"][0]["before_sha256"], comparison["files"][0]["after_sha256"])

    def test_protected_source_comparison_reports_changed_missing_and_added_source(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            changed = root / "experiment" / "changed.py"
            missing = root / "experiment" / "missing.py"
            changed.parent.mkdir(parents=True)
            changed.write_text("before\n")
            missing.write_text("before\n")
            before = [self.reference(changed), self.reference(missing)]
            changed.write_text("after\n")
            missing.unlink()
            added = root / "experiment" / "added.py"
            added.write_text("added\n")
            comparison = prepared_execution.protected_source_comparison(root, before)
        self.assertEqual(comparison["status"], "changed")
        self.assertEqual(comparison["changes"], [
            "experiment/added.py", "experiment/changed.py", "experiment/missing.py"])
        statuses = {item["path"]: item["status"] for item in comparison["files"]}
        self.assertEqual(statuses, {
            "experiment/added.py": "added",
            "experiment/changed.py": "changed",
            "experiment/missing.py": "missing",
        })

    def test_correction_uses_prior_changed_paths_not_every_allowed_path(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original = root / "original"
            candidate = root / "candidate"
            original.mkdir();candidate.mkdir()
            (original / "source.php").write_text("original\n")
            run = candidate / "experiment" / "run.py"
            run.parent.mkdir()
            run.write_text("print('corrected')\n")
            request = {
                "baseline": str(original),
                "allowed_paths": ["experiment/run.py", "experiment/selfie.png"],
                "source_units": [{"path": "source.php", "text": "original\n"}],
            }
            generated = {"changed_paths": ["experiment/run.py"]}
            baseline = root / "correction-baseline"
            sources = prepared_execution.overlay_correction_generation(
                request, candidate, generated, baseline,
                lambda path: [{"path": str(item.relative_to(path))}
                              for item in path.rglob("*") if item.is_file()])

            self.assertEqual((baseline / "experiment" / "run.py").read_text(), "print('corrected')\n")
            self.assertFalse((baseline / "experiment" / "selfie.png").exists())
            self.assertEqual(set(sources), {"experiment/run.py"})
            self.assertIn(
                {"path": "experiment/run.py", "text": "print('corrected')\n"},
                request["source_units"],
            )

    def test_transports_identical_artifact_content_once(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first = root / "probe.php"
            duplicate = root / "executed-harness.php"
            first.write_text("<?php observed();")
            duplicate.write_bytes(first.read_bytes())
            items = prepared_execution.review_evidence_set(
                [self.reference(first), self.reference(duplicate)])
        self.assertEqual(items[0]["transport"], "full_text")
        self.assertEqual(items[1]["transport"], "verified_duplicate")
        metadata = json.loads(items[1]["text"])
        self.assertEqual(metadata["duplicate_of"], str(first))
        self.assertFalse(metadata["content_included"])

    def test_assessment_facts_use_the_same_bounded_outputs_as_independent_review(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "attempt"
            experiment = output / "execution" / "source" / "experiment"
            results = experiment / "results"
            details = results / "details"
            details.mkdir(parents=True)
            aggregate = results / "aggregate.trace.json"
            detail = details / "detail.trace.json"
            process = results / "aggregate.process.json"
            aggregate.write_text(json.dumps({
                "status": "checked",
                "checks": [{"name": "all cases", "observed_expected": True}],
            }))
            detail.write_text(json.dumps({
                "status": "observed",
                "process_record": "aggregate.process.json",
                "checks": [{"name": "one internal step", "observed_expected": True}],
            }))
            process.write_text(json.dumps({"exit_status": 0, "stderr": ""}))
            generation = output / "generation.json"
            generation.write_text("{}\n")
            detail_reference = self.reference(detail)
            receipt = output / "execution" / "result.json"
            receipt.write_text(json.dumps({
                "returncode": 0,
                "timed_out": False,
                "protected_changes": [],
                "generated_report_changed": True,
                "output_files": [self.reference(aggregate), self.reference(detail),
                                 self.reference(process)],
            }))
            request = output / "request.json"
            request.write_text(json.dumps({
                "allowed_paths": ["experiment/run.py"],
                "context": json.dumps({
                    "builder_execution_contract": prepared_execution.builder_execution_contract({
                        "schema_version": 1,
                        "entrypoint": {"timeout_seconds": 30},
                    }, ["experiment/run.py"]),
                }),
            }))
            (output / "bindings.json").write_text(json.dumps({
                "request": self.reference(request),
            }))
            (output / "source-provenance.json").write_text(json.dumps({
                "commit": "abc123", "parents": ["base123"],
                "commit_changes": [{"status": "A", "path": "feature.py"}],
                "source_files": []}))
            facts, evidence = prepared_execution.compact_execution_facts(
                output, {"execution": self.reference(receipt),
                         "generation": self.reference(generation)}, root)
        self.assertEqual(facts["trace_count"], 1)
        self.assertEqual(facts["process_count"], 1)
        self.assertTrue(facts["all_trace_checks_passed"])
        self.assertNotIn(detail_reference, evidence)

    def test_review_execution_projects_large_manifest_as_one_identity(self):
        output_files = [
            {"path": "/tmp/evidence-%04d.json" % index, "sha256": "%064x" % index}
            for index in range(1000)
        ]
        result = {"returncode": 0, "timed_out": False, "output_files": output_files}
        projected = prepared_execution.review_execution_projection(result)
        self.assertNotIn("output_files", projected)
        self.assertEqual(projected["output_file_manifest"]["count"], 1000)
        self.assertEqual(len(projected["output_file_manifest"]["sha256"]), 64)
        self.assertFalse(projected["output_file_manifest"]["content_included"])

    def test_review_selects_code_traces_processes_and_failed_check_detail(self):
        with tempfile.TemporaryDirectory() as folder:
            experiment = Path(folder) / "experiment"
            results = experiment / "results"
            results.mkdir(parents=True)
            runner = experiment / "runner.py"
            trace = results / "case.trace.json"
            process = results / "case.process.json"
            failed = results / "case.check-001.json"
            successful = results / "case.check-002.json"
            snapshot = results / "case.stage-001.payment.json"
            runner.write_text("print('run')")
            trace.write_text(json.dumps({"status": "blocked", "checks": [
                {"observed_expected": False, "evidence_file": failed.name},
                {"observed_expected": True, "evidence_file": successful.name},
            ]}))
            process.write_text(json.dumps({"exit_status": 2, "stderr": ""}))
            failed.write_text(json.dumps({"observed": "wrong"}))
            successful.write_text(json.dumps({"observed": "right"}))
            snapshot.write_text(json.dumps({"rows": list(range(100))}))
            references = [self.reference(path) for path in
                          [runner, trace, process, failed, successful, snapshot]]
            selected = prepared_execution.review_output_references(experiment, references)
        paths = {Path(item["path"]).name for item in selected}
        self.assertEqual(paths, {runner.name, trace.name, process.name, failed.name})

    def test_review_omits_successful_per_check_trace_from_aggregate_packet(self):
        with tempfile.TemporaryDirectory() as folder:
            experiment = Path(folder) / "experiment"
            results = experiment / "results"
            results.mkdir(parents=True)
            aggregate = results / "case.trace.json"
            detail = results / "case.check-001.trace.json"
            aggregate.write_text(json.dumps({
                "status": "observed",
                "checks": [{"observed_expected": True}],
            }))
            detail.write_text(json.dumps({
                "status": "observed",
                "process_record": "case.process.json",
                "checks": [{"observed_expected": True}],
            }))
            selected = prepared_execution.review_output_references(
                experiment, [self.reference(aggregate), self.reference(detail)])
        self.assertEqual([Path(item["path"]).name for item in selected], [aggregate.name])

    def test_materializes_the_projected_text_that_the_reviewer_quoted(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "case.trace.json"
            source.write_text(json.dumps({
                "status": "observed",
                "checks": [{"name": "held", "observed_expected": True}],
                "queries": ["x" * prepared_execution.MAX_REVIEW_JSON_FIELD_BYTES],
            }, indent=2))
            citation = {
                "evidence_path": str(source),
                "quote": '"name":"held","observed_expected":true',
            }
            source_ref, text, transport = prepared_execution.citation_representation(citation, root)
            evidence = prepared_execution.materialize_citation_representation(
                root / "attempt", source_ref, text, transport)
            materialized = root / evidence["path"]
            self.assertEqual(transport, "bounded_json_projection")
            self.assertNotEqual(evidence, source_ref)
            self.assertIn(citation["quote"], materialized.read_text())
            self.assertEqual(evidence["sha256"], hashlib.sha256(materialized.read_bytes()).hexdigest())

    def test_corrected_export_is_saved_beside_an_immutable_failed_export(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "research-result.json"
            prepared_execution.save(path, {"status": "old"})
            corrected = prepared_execution.save_versioned_json(path, {"status": "corrected"})
        self.assertNotEqual(corrected, path)
        self.assertEqual(corrected.name[:16], "research-result-")

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
            evidence_root = output / "execution" / "source" / "experiment" / "results"
            evidence_root.mkdir(parents=True)
            generation = output / "generation" / "result.json"
            execution = output / "execution" / "result.json"
            protected = output / "execution" / "protected-source-comparison.json"
            evidence = output / "execution" / "observed.txt"
            process = evidence_root / "case.process.json"
            trace = evidence_root / "case.trace.json"
            generation.write_text('{}\n')
            evidence.write_text('observed exact fact\n')
            process.write_text(json.dumps({"exit_status": 0, "stderr": ""}) + "\n")
            trace.write_text(json.dumps({"status": "checked", "checks": [
                {"name": "case held", "observed_expected": True}]}) + "\n")
            protected.write_text(json.dumps({
                "status": "verified_unchanged", "protected_source_count": 2,
            }) + "\n")
            execution.write_text(json.dumps({
                "returncode": 0, "timed_out": False, "protected_changes": [],
                "generated_report_changed": True,
                "output_files": [prepared_execution.ref(process), prepared_execution.ref(trace)],
                "protected_source_comparison": prepared_execution.ref(protected),
            }) + "\n")
            request = output / "request.json"
            request.write_text(json.dumps({
                "allowed_paths": ["experiment/run.py"],
                "context": json.dumps({
                    "builder_execution_contract": prepared_execution.builder_execution_contract({
                        "schema_version": 1,
                        "entrypoint": {"timeout_seconds": 30},
                    }, ["experiment/run.py"]),
                }),
            }) + "\n")
            (output / "bindings.json").write_text(json.dumps({
                "request": prepared_execution.ref(request),
            }) + "\n")
            (output / "source-provenance.json").write_text(json.dumps({
                "commit": "abc123", "parents": ["base123"],
                "commit_changes": [{"status": "A", "path": "feature.py"}],
                "source_files": [
                    {"path": "app/Foo.php", "role": "current product"},
                    {"path": "references/Foo.php", "role": "archived reference"},
                ]}) + "\n")
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
            original_admission = prepared_execution.verify_assessment_admission
            prepared_execution.resume_bindings = lambda *_args, **_kwargs: {"selection": selection}
            prepared_execution.prepare = lambda *_args, **_kwargs: self.fail("prepare must not run")
            prepared_execution.verify_assessment_admission = lambda *_args, **_kwargs: {
                "collection_status": "references_verified"}
            try:
                result = prepared_execution.execute(state, output)
            finally:
                prepared_execution.resume_bindings = original_resume
                prepared_execution.prepare = original_prepare
                prepared_execution.verify_assessment_admission = original_admission
            self.assertEqual(result["model_calls"], 0)
            exported = json.loads(Path(result["research_result"]).read_text())
            self.assertEqual(exported["kind"], "selected_research_result")
            self.assertEqual(exported["goal"], goal)
            self.assertEqual(exported["selection"], selection)
            self.assertIn(prepared_execution.root_ref(trace, root), exported["evidence"])
            self.assertIn(prepared_execution.root_ref(process, root), exported["evidence"])
            package_ref = exported["assessment_package"]
            package = json.loads((root / package_ref["path"]).read_text())
            self.assertEqual(package["kind"], "selected_research_assessment_package")
            self.assertEqual(package["schema_version"], 2)
            self.assertEqual(package["goal"], goal)
            self.assertEqual(package["selection"], selection)
            self.assertEqual(package["raw_evidence"], [prepared_execution.root_ref(evidence, root)])
            citation = package["review"]["cases"][0]["citations"][0]
            self.assertEqual(citation["evidence"], prepared_execution.root_ref(evidence, root))
            self.assertEqual(citation["quote"], "exact fact")
            self.assertEqual(citation["occurrences"], [{"start": 9, "end": 19}])
            facts = package["execution_facts"]
            self.assertEqual(facts["source_commit"], "abc123")
            self.assertEqual(facts["process_count"], 1)
            self.assertEqual(facts["trace_count"], 1)
            self.assertTrue(facts["all_processes_passed"])
            self.assertTrue(facts["all_trace_checks_passed"])
            self.assertEqual(facts["version_reconciliation"]["direct_parents"], ["base123"])
            self.assertEqual(facts["version_reconciliation"]["commit_changes"], [
                {"status": "A", "path": "feature.py"}])
            self.assertEqual(facts["write_boundary"]["status"], "verified")

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

    def test_completed_handoff_accepts_a_quote_from_the_bounded_projection(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "attempt"
            (output / "generation").mkdir(parents=True)
            (output / "execution").mkdir()
            generation = output / "generation" / "result.json"
            execution = output / "execution" / "result.json"
            trace = output / "execution" / "case.trace.json"
            generation.write_text('{}\n')
            execution.write_text('{}\n')
            trace.write_text(json.dumps({"status": "observed", "checks": [
                {"name": "held", "observed_expected": True}],
                "queries": ["x" * prepared_execution.MAX_REVIEW_JSON_FIELD_BYTES]}, indent=2))
            selection = {"path": "selection.json", "sha256": "selection-sha"}
            cycle = root / "cycle.json"
            cycle.write_text(json.dumps({"goal": {}, "selection": selection}))
            handoff = {
                "selection": selection,
                "generation": prepared_execution.ref(generation),
                "execution": prepared_execution.ref(execution),
                "review": {"cases": [{"id": "case-1", "citations": [{
                    "evidence_path": str(trace),
                    "quote": '"name":"held","observed_expected":true'}]}]},
            }
            (output / "handoff.json").write_text(json.dumps(handoff))
            accepted = prepared_execution.completed_handoff(
                {"root": str(root), "cycle": str(cycle)}, output, {"selection": selection})
        self.assertEqual(accepted, handoff)


if __name__ == "__main__":
    unittest.main()
