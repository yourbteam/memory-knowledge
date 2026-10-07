import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
AREA = ROOT / "skills/codebase-atlas-machinery/scripts/area_coordinator.py"
ROUTE_COORDINATOR = ROOT / "skills/codebase-atlas-machinery/scripts/route_coordinator.py"
ATLAS_TEST_PATH = Path(__file__).with_name("test_codebase_atlas.py")
ATLAS_TEST_SPEC = importlib.util.spec_from_file_location("atlas_area_fixture_tests", ATLAS_TEST_PATH)
ATLAS_TESTS = importlib.util.module_from_spec(ATLAS_TEST_SPEC)
ATLAS_TEST_SPEC.loader.exec_module(ATLAS_TESTS)


class AtlasAreaCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ATLAS_TESTS.AtlasCliTests()
        self.fixture.setUp()
        self.area_dir = self.fixture.root / "area-run"
        self.saved, _graph, self.routes = self.fixture.coverage_fixture(count=3)
        self.anchor = self.routes[0]["id"]

    def tearDown(self):
        self.fixture.tearDown()

    def cli(self, command, *, anchor=None, area=None, max_bytes=None, expect=0):
        extra = ["--max-bytes", str(max_bytes)] if max_bytes is not None else []
        result = subprocess.run(
            [sys.executable, str(AREA), command,
             "--repo", str(self.fixture.repo), "--db", str(self.fixture.db),
             "--anchor-route-fact-id", anchor or self.anchor,
             "--area-dir", str(area or self.area_dir), *extra],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.assertEqual(result.returncode, expect, result.stderr)
        return result

    def child(self, route_id):
        name = hashlib.sha256(route_id.encode("utf-8")).hexdigest()
        return self.area_dir / "routes" / name

    def bind_fixture_map(self, saved, graph, route, title):
        attached, receipt = self.fixture.reviewed_route_map(saved, graph, route, title)
        path, _binding, _review = self.fixture.route_binding_document(
            saved, graph, route, attached, receipt, title=f"binding-{title}")
        self.fixture.cli("route-bind-add", "--db", str(self.fixture.db), "--snapshot",
                         saved["snapshot_id"], "--input", str(path))

    def child_cli(self, command, route_id, run_dir, *args, max_bytes):
        result = subprocess.run(
            [sys.executable, str(ROUTE_COORDINATOR), command,
             "--repo", str(self.fixture.repo), "--db", str(self.fixture.db),
             "--route-fact-id", route_id, "--run-dir", str(run_dir),
             "--max-bytes", str(max_bytes), *map(str, args)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def test_enumerates_only_anchor_controller_and_repeat_prepare_resumes(self):
        (self.fixture.repo / "Other.cs").write_text(
            '[Route("api/other")] class OtherController { [HttpGet("x")] void X() {} }\n', encoding="utf-8")
        ATLAS_TESTS.git(self.fixture.repo, "add", "--", "Other.cs")
        self.saved = self.fixture.index()
        graph = self.fixture.graph(self.saved["snapshot_id"])
        routes = [f for f in graph["facts"] if f["kind"] == "route_action"]
        self.routes = sorted(routes, key=lambda item: item["id"])
        self.anchor = self.routes[0]["id"]

        db_before = hashlib.sha256(self.fixture.db.read_bytes()).hexdigest()
        first = json.loads(self.cli("prepare").stdout)
        self.assertEqual(hashlib.sha256(self.fixture.db.read_bytes()).hexdigest(), db_before)
        self.assertEqual(first["result"], "prepared")
        manifest = json.loads((self.area_dir / "area-manifest.json").read_text())
        controller = next(f for f in graph["facts"] if f["id"] == self.anchor)["controller_type_id"]
        expected = sorted(f["id"] for f in routes if f["controller_type_id"] == controller)
        self.assertEqual(sorted(item["route_fact_id"] for item in manifest["routes"]), expected)
        self.assertEqual(first["open_count"], len(expected))
        second = json.loads(self.cli("prepare").stdout)
        self.assertEqual(second["result"], "prepared")
        self.assertEqual(second["route_count"], len(expected))

    def test_reviewed_routes_count_as_existing_and_ambiguous_links_refuse(self):
        saved, graph, routes = self.fixture.coverage_fixture(count=2)
        self.bind_fixture_map(saved, graph, routes[0], "Reviewed route one")
        self.bind_fixture_map(saved, graph, routes[1], "Reviewed route two")
        self.anchor = routes[0]["id"]
        db_before = hashlib.sha256(self.fixture.db.read_bytes()).hexdigest()
        result = json.loads(self.cli("prepare").stdout)
        self.assertEqual(hashlib.sha256(self.fixture.db.read_bytes()).hexdigest(), db_before)
        self.assertTrue(result["ready"])
        self.assertEqual((result["reviewed_count"], result["open_count"]), (2, 0))
        self.assertEqual(list((self.area_dir / "routes").iterdir()), [])

        # Rebuild a fresh two-route fixture, then attach a second accepted association to one route.
        self.fixture.tearDown()
        self.fixture = ATLAS_TESTS.AtlasCliTests()
        self.fixture.setUp()
        self.area_dir = self.fixture.root / "ambiguous-area"
        saved, graph, routes = self.fixture.coverage_fixture(count=2)
        self.bind_fixture_map(saved, graph, routes[0], "Ambiguous route one")
        self.bind_fixture_map(saved, graph, routes[0], "Ambiguous route two")
        self.anchor = routes[0]["id"]
        refused = self.cli("prepare", expect=2)
        self.assertIn("multiple reviewed associations", refused.stderr)
        self.assertFalse(self.area_dir.exists())

    def test_missing_child_can_be_prepared_but_nonempty_partial_child_refuses(self):
        (self.fixture.repo / "Routes.cs").write_text(
            '[Route("api/test")] class TestController { [HttpGet("a")] void A() {} [HttpGet("b")] void B() {} }\n',
            encoding="utf-8")
        ATLAS_TESTS.git(self.fixture.repo, "add", "--", "Routes.cs")
        saved = self.fixture.index()
        routes = [f for f in self.fixture.graph(saved["snapshot_id"])["facts"] if f["kind"] == "route_action"]
        self.routes = sorted(routes, key=lambda item: item["id"])
        self.anchor = self.routes[0]["id"]
        json.loads(self.cli("prepare").stdout)
        second_route = next(item["id"] for item in self.routes if item["id"] != self.anchor)
        second_child = self.child(second_route)
        for path in second_child.iterdir():
            if path.is_file():
                path.unlink()
        second_child.rmdir()
        resumed = json.loads(self.cli("prepare").stdout)
        self.assertTrue(resumed["ready"])
        (second_child / "evidence-pack.json").unlink()
        missing_artifact = self.cli("prepare", expect=2)
        self.assertIn("run artifact is missing: evidence-pack.json", missing_artifact.stderr)
        for path in second_child.iterdir():
            if path.is_file():
                path.unlink()
        second_child.rmdir()
        json.loads(self.cli("prepare").stdout)
        (second_child / "manifest.json").unlink()
        (second_child / "evidence-pack.json").write_text("partial")
        refused = self.cli("prepare", expect=2)
        self.assertIn("missing manifest.json", refused.stderr)
        self.assertTrue((second_child / "evidence-pack.json").exists())

    def test_cross_route_identity_stale_checkout_and_corrupt_child_fail_closed(self):
        json.loads(self.cli("prepare").stdout)
        other_route = next(item["id"] for item in self.routes if item["id"] != self.anchor)
        cross_route = self.cli("status", anchor=other_route, expect=2)
        self.assertIn("identity or evidence budget differs", cross_route.stderr)
        child = self.child(self.anchor)
        packet = child / "evidence-pack.json"
        packet.write_bytes(packet.read_bytes() + b" ")
        corrupt = self.cli("status", expect=2)
        self.assertIn("changed", corrupt.stderr)
        packet.write_bytes(packet.read_bytes()[:-1])
        (self.fixture.repo / "Routes.cs").write_text(
            (self.fixture.repo / "Routes.cs").read_text(encoding="utf-8") + "// stale\n", encoding="utf-8")
        stale = self.cli("status", expect=2)
        self.assertIn("no_saved_snapshot_matches_current_extractor_and_checkout", stale.stderr)

    def test_published_child_transitions_from_open_and_next_child_remains_usable(self):
        max_bytes = 100000
        result = json.loads(self.cli("prepare", max_bytes=max_bytes).stdout)
        self.assertEqual(result["open_count"], 3)
        budget_mismatch = self.cli("status", max_bytes=max_bytes + 1, expect=2)
        self.assertIn("evidence budget differs", budget_mismatch.stderr)
        route = self.routes[0]
        child = self.child(route["id"])
        graph = self.fixture.graph(self.saved["snapshot_id"])
        draft_path = self.fixture.root / "child-draft.json"
        draft_path.write_text(json.dumps({
            "overlay_schema_version": 1,
            "snapshot_id": self.saved["snapshot_id"],
            "extractor_identity": graph["extractor_identity"],
            "title": "Area child review map",
            "reviewed_conclusions": [{
                "claim": "This selected controller route declares the cited action.",
                "evidence": [{"fact_id": route["id"], "source": route["source"]}],
            }],
        }), encoding="utf-8")
        self.child_cli("draft", route["id"], child, "--draft-file", draft_path, max_bytes=max_bytes)
        packet = json.loads((child / "review-packet.json").read_text(encoding="utf-8"))
        review_path = self.fixture.root / "child-review.json"
        review_path.write_text(json.dumps({
            "review_schema_version": 1,
            "packet_sha256": packet["packet_sha256"],
            "evidence_sha256": packet["evidence_sha256"],
            "draft_sha256": packet["draft_sha256"],
            "reviewer_identity": "synthetic area mechanics fixture",
            "reviewer_model": "GPT-6.1 Sol High",
            "reviewed_at": "2026-10-07T12:00:00Z",
            "decision": "accepted",
            "assignment_review": {"decision": "accepted", "basis": "The assignment stays within this child's complete route packet."},
            "conclusion_reviews": [{"conclusion_number": 1, "decision": "accepted",
                                    "basis": "The conclusion matches its exact selected route source."}],
            "route_association_review": {"decision": "accepted", "basis": "The map is associated with this exact route action."},
        }), encoding="utf-8")
        published = json.loads(self.child_cli("publish", route["id"], child, "--review-file", review_path,
                                              max_bytes=max_bytes).stdout)
        self.assertEqual(published["result"], "published_and_fresh")

        progressed = json.loads(self.cli("status", max_bytes=max_bytes).stdout)
        self.assertEqual((progressed["reviewed_count"], progressed["open_count"]), (1, 2))
        self.assertEqual(progressed["result"], "ready")
        next_route = self.routes[1]
        next_child = self.child(next_route["id"])
        second_draft = json.loads(draft_path.read_text(encoding="utf-8"))
        second_draft["title"] = "Next area child map"
        second_draft["reviewed_conclusions"][0]["evidence"][0] = {
            "fact_id": next_route["id"], "source": next_route["source"]}
        draft_path.write_text(json.dumps(second_draft), encoding="utf-8")
        next_result = json.loads(self.child_cli("draft", next_route["id"], next_child,
                                                "--draft-file", draft_path,
                                                max_bytes=max_bytes).stdout)
        self.assertEqual(next_result["result"], "review_ready")
        after_second_draft = json.loads(self.cli("status", max_bytes=max_bytes).stdout)
        self.assertEqual((after_second_draft["reviewed_count"], after_second_draft["open_count"]), (1, 2))


if __name__ == "__main__":
    unittest.main()
