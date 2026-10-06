import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
COORDINATOR = ROOT / "skills/codebase-atlas-machinery/scripts/route_coordinator.py"
ATLAS_TESTS_PATH = Path(__file__).with_name("test_codebase_atlas.py")
SPEC = importlib.util.spec_from_file_location("atlas_coordinator_atlas_tests", ATLAS_TESTS_PATH)
ATLAS_TESTS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ATLAS_TESTS)


class RouteCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ATLAS_TESTS.AtlasCliTests()
        self.fixture.setUp()
        self.run_dir = self.fixture.root / "coordinator-run"
        self._saved, graph, route = self.fixture.evidence_fixture()
        self.route = route
        self.draft = {
            "overlay_schema_version": 1,
            "snapshot_id": self._saved["snapshot_id"],
            "extractor_identity": graph["extractor_identity"],
            "title": "Coordinator route map",
            "reviewed_conclusions": [{
                "claim": "The selected route invokes its saved action method.",
                "evidence": [{"fact_id": route["id"], "source": route["source"]}],
            }],
        }
        self.draft_path = self.fixture.root / "luna-draft.json"
        self.draft_path.write_text(json.dumps(self.draft), encoding="utf-8")

    def tearDown(self):
        self.fixture.tearDown()

    def cli(self, command, *extra, expect=0):
        result = subprocess.run(
            [sys.executable, str(COORDINATOR), command,
             "--repo", str(self.fixture.repo), "--db", str(self.fixture.db),
             "--route-fact-id", self.route["id"], "--run-dir", str(self.run_dir), *map(str, extra)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.assertEqual(result.returncode, expect, result.stderr)
        return result

    def prepare_and_draft(self):
        self.cli("prepare")
        self.cli("draft", "--draft-file", self.draft_path)
        packet = json.loads((self.run_dir / "review-packet.json").read_text(encoding="utf-8"))
        review = {
            "review_schema_version": 1,
            "packet_sha256": packet["packet_sha256"],
            "evidence_sha256": packet["evidence_sha256"],
            "draft_sha256": packet["draft_sha256"],
            "reviewer_identity": "synthetic coordinator mechanics fixture",
            "reviewer_model": "GPT-6.1 Sol High",
            "reviewed_at": "2026-10-06T12:00:00Z",
            "decision": "accepted",
            "assignment_review": {
                "decision": "accepted",
                "basis": "The assignment stays within this route and its complete packet.",
            },
            "conclusion_reviews": [{
                "conclusion_number": 1,
                "decision": "accepted",
                "basis": "The conclusion matches its cited route action source span.",
            }],
            "route_association_review": {
                "decision": "accepted",
                "basis": "This map is correctly associated with the selected route action.",
            },
        }
        self.review_path = self.fixture.root / "sol-review.json"
        self.review_path.write_text(json.dumps(review), encoding="utf-8")
        return packet, review

    def crash_publish(self, hook):
        args = ["publish", "--repo", str(self.fixture.repo), "--db", str(self.fixture.db),
                "--route-fact-id", self.route["id"], "--run-dir", str(self.run_dir),
                "--review-file", str(self.review_path)]
        helper = self.fixture.root / "interrupt_coordinator.py"
        helper.write_text(
            "import os, sys\n"
            f"sys.path.insert(0, {str(COORDINATOR.parent)!r})\n"
            "import route_coordinator as rc\n"
            + hook + "\n"
            + f"raise SystemExit(rc.main({args!r}))\n",
            encoding="utf-8",
        )
        return subprocess.run([sys.executable, str(helper)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_real_cli_prepare_draft_review_publish_and_fresh_retrieval(self):
        self.prepare_and_draft()
        result = json.loads(self.cli("publish", "--review-file", self.review_path).stdout)
        self.assertEqual(result["result"], "published_and_fresh")
        self.assertEqual(result["route_fact_id"], self.route["id"])
        status = json.loads(self.cli("status").stdout)
        self.assertEqual(status["result"], "published_and_fresh")
        self.assertGreaterEqual(status["stage_count"], 4)
        self.assertTrue(all("elapsed_ms" in stage and "artifact_bytes" in stage for stage in status["stages"]))
        self.assertTrue(all(stage["provider_model_tokens"] == "unavailable_without_provider_telemetry" for stage in status["stages"]))

    def test_rejected_review_and_stale_source_leave_atlas_database_unchanged(self):
        packet, review = self.prepare_and_draft()
        before = hashlib.sha256(self.fixture.db.read_bytes()).hexdigest()
        review["decision"] = "rejected"
        review["assignment_review"]["decision"] = "rejected"
        self.review_path.write_text(json.dumps(review), encoding="utf-8")
        rejected = json.loads(self.cli("publish", "--review-file", self.review_path).stdout)
        self.assertEqual(rejected["result"], "rejected")
        self.assertEqual(hashlib.sha256(self.fixture.db.read_bytes()).hexdigest(), before)

        # A fresh run reaches Atlas's source-freshness rejection before publication.
        self.fixture.tearDown()
        self.fixture = ATLAS_TESTS.AtlasCliTests()
        self.fixture.setUp()
        self.run_dir = self.fixture.root / "stale-run"
        self._saved, graph, route = self.fixture.evidence_fixture()
        self.route = route
        self.draft.update({"snapshot_id": self._saved["snapshot_id"], "extractor_identity": graph["extractor_identity"],
                           "reviewed_conclusions": [{"claim": "The route invokes its saved action method.",
                               "evidence": [{"fact_id": route["id"], "source": route["source"]}]}]})
        self.draft_path = self.fixture.root / "luna-draft.json"
        self.draft_path.write_text(json.dumps(self.draft), encoding="utf-8")
        self.prepare_and_draft()
        review = json.loads(self.review_path.read_text(encoding="utf-8"))
        self.review_path.write_text(json.dumps(review), encoding="utf-8")
        source = self.fixture.repo / "Flow.cs"
        source.write_text(source.read_text(encoding="utf-8") + "// source changed\n", encoding="utf-8")
        before = hashlib.sha256(self.fixture.db.read_bytes()).hexdigest()
        refused = self.cli("publish", "--review-file", self.review_path, expect=2)
        self.assertIn("no_saved_snapshot_matches_current_extractor_and_checkout", refused.stderr)
        self.assertEqual(hashlib.sha256(self.fixture.db.read_bytes()).hexdigest(), before)
        manifest = json.loads((self.run_dir / "manifest.json").read_text(encoding="utf-8"))
        failed = [stage for stage in manifest["stages"] if stage["stage"] == "route-find-before-publish"][-1]
        self.assertGreater(failed["atlas_stderr_bytes"], 0)
        self.assertIn("elapsed_ms", failed)

    def test_committed_publish_resumes_from_stale_manifest_without_duplicate_binding(self):
        self.prepare_and_draft()
        hook = (
            "original = rc._write_once\n"
            "def interrupt(path, raw):\n"
            "    original(path, raw)\n"
            "    if path.name == 'publish-result.json':\n"
            "        os._exit(91)\n"
            "rc._write_once = interrupt"
        )
        interrupted = self.crash_publish(hook)
        self.assertEqual(interrupted.returncode, 91)
        self.assertTrue((self.run_dir / "publish-result.json").is_file())
        resumed_status = json.loads(self.cli("status").stdout)
        self.assertEqual(resumed_status["result"], "published_and_fresh")
        resumed = json.loads(self.cli("publish", "--review-file", self.review_path).stdout)
        self.assertTrue(resumed["idempotent_recovery"])
        repeated = json.loads(self.cli("publish", "--review-file", self.review_path).stdout)
        self.assertTrue(repeated["idempotent_recovery"])
        found = json.loads(self.fixture.cli(
            "route-find", "--db", str(self.fixture.db), "--repo", str(self.fixture.repo),
            "--route-fact-id", self.route["id"], "--max-tokens", "100000",
        ).stdout)
        self.assertEqual(found["result"], "fresh")
        self.assertEqual(found["association_count"], 1)

    def test_interrupted_manifest_replace_is_reconciled_from_valid_temp(self):
        self.prepare_and_draft()
        hook = (
            "original = rc.os.replace\n"
            "def interrupt(source, target):\n"
            "    source, target = __import__('pathlib').Path(source), __import__('pathlib').Path(target)\n"
            "    if target.name == 'manifest.json' and (source.parent / 'publish-result.json').exists():\n"
            "        candidate = __import__('json').loads(source.read_text(encoding='utf-8'))\n"
            "        if 'publish-result.json' in candidate.get('artifacts', {}):\n"
            "            os._exit(92)\n"
            "    original(source, target)\n"
            "rc.os.replace = interrupt"
        )
        interrupted = self.crash_publish(hook)
        self.assertEqual(interrupted.returncode, 92)
        self.assertTrue(list(self.run_dir.glob(".manifest.json.*.tmp")))
        status = json.loads(self.cli("status").stdout)
        self.assertEqual(status["result"], "published_and_fresh")
        self.assertFalse(list(self.run_dir.glob(".manifest.json.*.tmp")))
        repeated = json.loads(self.cli("publish", "--review-file", self.review_path).stdout)
        self.assertTrue(repeated["idempotent_recovery"])

    def test_routes_prepared_together_publish_sequentially_as_database_changes(self):
        saved, graph, routes = self.fixture.coverage_fixture(count=2)
        prepared_runs = []
        for index, route in enumerate(routes):
            run_dir = self.fixture.root / f"parallel-prepared-{index}"
            draft_path = self.fixture.root / f"luna-{index}.json"
            draft_path.write_text(json.dumps({
                "overlay_schema_version": 1,
                "snapshot_id": saved["snapshot_id"],
                "extractor_identity": graph["extractor_identity"],
                "title": f"Route {index}",
                "reviewed_conclusions": [{
                    "claim": "This selected route declares the cited action.",
                    "evidence": [{"fact_id": route["id"], "source": route["source"]}],
                }],
            }), encoding="utf-8")
            self.route = route
            self.run_dir = run_dir
            self.cli("prepare")
            self.cli("draft", "--draft-file", draft_path)
            packet = json.loads((run_dir / "review-packet.json").read_text(encoding="utf-8"))
            review_path = self.fixture.root / f"sol-{index}.json"
            review_path.write_text(json.dumps({
                "review_schema_version": 1,
                "packet_sha256": packet["packet_sha256"],
                "evidence_sha256": packet["evidence_sha256"],
                "draft_sha256": packet["draft_sha256"],
                "reviewer_identity": "synthetic sequential mechanics fixture",
                "reviewer_model": "GPT-6.1 Sol High",
                "reviewed_at": "2026-10-06T12:00:00Z",
                "decision": "accepted",
                "assignment_review": {"decision": "accepted", "basis": "This assignment is confined to the selected route."},
                "conclusion_reviews": [{"conclusion_number": 1, "decision": "accepted",
                                        "basis": "The conclusion matches the exact selected route evidence."}],
                "route_association_review": {"decision": "accepted", "basis": "This map is associated with its selected route."},
            }), encoding="utf-8")
            prepared_runs.append((route, run_dir, review_path))
        outcomes = []
        for route, run_dir, review_path in prepared_runs:
            self.route = route
            self.run_dir = run_dir
            outcomes.append(json.loads(self.cli("publish", "--review-file", review_path).stdout))
        self.assertEqual([item["result"] for item in outcomes], ["published_and_fresh"] * len(prepared_runs))
        self.assertEqual(len({item["route_fact_id"] for item in outcomes}), len(prepared_runs))

    def test_changed_run_artifacts_and_cross_route_identity_are_refused(self):
        self.prepare_and_draft()
        other = self.cli("status", "--route-fact-id", "different-route-id", expect=2)
        self.assertIn("different repository, database, or route fact", other.stderr)
        evidence = self.run_dir / "evidence-pack.json"
        evidence.write_bytes(evidence.read_bytes() + b" ")
        changed = self.cli("status", expect=2)
        self.assertIn("changed", changed.stderr)


if __name__ == "__main__":
    unittest.main()
