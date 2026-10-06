import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "skills/codebase-atlas-machinery/scripts/atlas.py"


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", os.fspath(repo), *args], text=True).strip()


class AtlasCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "atlas-test@example.invalid")
        git(self.repo, "config", "user.name", "Atlas Test")
        (self.repo / "a.txt").write_bytes(b"alpha\x00\n")
        (self.repo / "sub dir").mkdir()
        (self.repo / "sub dir" / "b.txt").write_bytes(b"beta\n")
        git(self.repo, "add", "--", ".")
        self.db = self.root / "atlas.sqlite"

    def tearDown(self):
        self.temp.cleanup()

    def cli(self, *args: str, expect=0):
        result = subprocess.run(
            [sys.executable, os.fspath(SCRIPT), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if expect is not None:
            self.assertEqual(result.returncode, expect, result.stderr)
        return result

    def index(self):
        return json.loads(self.cli("index", "--repo", os.fspath(self.repo), "--db", os.fspath(self.db)).stdout)

    def query(self, snapshot_id, *extra):
        return json.loads(self.cli(
            "query", "--db", os.fspath(self.db), "--snapshot", snapshot_id, *extra
        ).stdout)

    def graph(self, snapshot_id):
        return self.query(snapshot_id, "--graph")["source_graph"]

    def discover_routes(self, terms, max_tokens=10000, expect=0):
        return self.cli(
            "discover", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
            "--terms", *terms, "--max-tokens", str(max_tokens), expect=expect,
        )

    def evidence_pack(self, route_fact_id, max_tokens=100000, expect=0):
        return self.cli(
            "evidence-pack", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
            "--route-fact-id", route_fact_id, "--max-tokens", str(max_tokens), expect=expect,
        )

    def coverage(self, max_tokens=100000, offset=0, expect=0):
        return self.cli("coverage", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                        "--max-tokens", str(max_tokens), "--offset", str(offset), expect=expect)

    def refresh_fixture(self, claim_count=8):
        (self.repo / "Other.cs").write_text("class Other { int Read() { return 1; } }\n", encoding="utf-8")
        (self.repo / "Flow.cs").write_text('''namespace Demo;
[Route("api/customer")]
class CustomerController(IHandler handler)
{
    [HttpPost("save")]
    void Save() { handler.Handle(); }
}
''', encoding="utf-8")
        (self.repo / "Handler.cs").write_text('''namespace Demo;
class Handler(IStore store)
{
    void Handle() { store.SaveAsync(); store.GetAsync(); }
}
class Store { void SaveAsync() {} void GetAsync() {} }
class Registrations { void Add() { services.AddScoped<IHandler, Handler>(); services.AddScoped<IStore, Store>(); } }
''', encoding="utf-8")
        git(self.repo, "add", "--", "Other.cs", "Flow.cs", "Handler.cs")
        saved = self.index()
        graph = self.graph(saved["snapshot_id"])
        route = next(f for f in graph["facts"] if f["kind"] == "route_action")
        flow = {
            "overlay_schema_version": 1, "snapshot_id": saved["snapshot_id"],
            "extractor_identity": graph["extractor_identity"], "title": "Refresh carry fixture",
            "reviewed_conclusions": [
                {"claim": f"Reviewed route claim {index}.",
                 "evidence": [{"fact_id": route["id"], "source": route["source"]}]}
                for index in range(claim_count)
            ],
        }
        flow_path = self.root / "refresh.flow.json"
        flow_path.write_text(json.dumps(flow), encoding="utf-8")
        attached = json.loads(self.cli("flow-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"],
                                       "--input", os.fspath(flow_path)).stdout)
        receipt = {"receipt_schema_version": 1, "snapshot_id": saved["snapshot_id"],
                   "overlay_id": attached["overlay_id"], "overlay_content_hash": attached["content_hash"],
                   "extractor_identity": graph["extractor_identity"], "reviewer_identity": "fixture reviewer",
                   "reviewer_model": "GPT-6.1 Sol High", "decision": "accepted",
                   "reviewed_at": "2026-10-06T12:00:00Z", "review_basis": "Each route claim cites the saved route source fact."}
        receipt_path = self.root / "refresh.review.json"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        reviewed = json.loads(self.cli("flow-review", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"],
                                       "--overlay", attached["overlay_id"], "--input", os.fspath(receipt_path)).stdout)
        binding_path, _, _ = self.route_binding_document(saved, graph, route, attached, reviewed, "refresh-binding")
        self.cli("route-bind-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"],
                 "--input", os.fspath(binding_path))
        return saved, graph, route, attached, reviewed

    def route_refresh(self, saved, route, expect=0, max_tokens=100000):
        return self.cli("route-refresh", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                        "--from-snapshot", saved["snapshot_id"], "--route-fact-id", route["id"],
                        "--max-tokens", str(max_tokens), expect=expect)

    def coverage_fixture(self, count=6):
        methods = "\n".join(f'    [HttpGet("item-{index}")] void Item{index}() {{}}' for index in range(count))
        source = self.repo / "Routes.cs"
        source.write_text(f'''[Route("api/test")]
class TestController
{{
{methods}
}}
''', encoding="utf-8")
        git(self.repo, "add", "--", "Routes.cs")
        saved = self.index()
        graph = self.graph(saved["snapshot_id"])
        return saved, graph, sorted((fact for fact in graph["facts"] if fact["kind"] == "route_action"), key=lambda fact: fact["id"])

    def evidence_fixture(self, extra_registration="", shadow=False):
        handler_body = "store.SaveAsync(); store.GetAsync();"
        if shadow:
            handler_body = "var store = new Store(); store.SaveAsync(); store.GetAsync();"
        source = self.repo / "Flow.cs"
        source.write_text(f'''namespace Demo;
[Route("api/customer")]
class CustomerController(IHandler handler)
{{
    [HttpPost("save")]
    void Save() {{ handler.Handle(); }}
}}
class Handler(IStore store)
{{
    void Handle() {{ {handler_body} }}
}}
class Store {{ void SaveAsync() {{}} void GetAsync() {{}} }}
class Registrations {{ void Add() {{ services.AddScoped<IHandler, Handler>(); services.AddScoped<IStore, Store>(); {extra_registration} }} }}
''', encoding="utf-8")
        git(self.repo, "add", "--", "Flow.cs")
        saved = self.index()
        graph = self.graph(saved["snapshot_id"])
        route = next(f for f in graph["facts"] if f["kind"] == "route_action")
        return saved, graph, route

    def reviewed_route_map(self, saved, graph, route, title="Reviewed route map"):
        overlay = {
            "overlay_schema_version": 1,
            "snapshot_id": saved["snapshot_id"],
            "extractor_identity": graph["extractor_identity"],
            "title": title,
            "reviewed_conclusions": [{
                "claim": "The reviewed map describes the route action.",
                "evidence": [{"fact_id": route["id"], "source": route["source"]}],
            }],
        }
        overlay_path = self.root / f"{title.replace(' ', '-')}.flow.json"
        overlay_path.write_text(json.dumps(overlay), encoding="utf-8")
        attached = json.loads(self.cli(
            "flow-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"],
            "--input", os.fspath(overlay_path),
        ).stdout)
        receipt = {
            "receipt_schema_version": 1,
            "snapshot_id": saved["snapshot_id"],
            "overlay_id": attached["overlay_id"],
            "overlay_content_hash": attached["content_hash"],
            "extractor_identity": graph["extractor_identity"],
            "reviewer_identity": "independent fixture review",
            "reviewer_model": "GPT-6.1 Sol High",
            "decision": "accepted",
            "reviewed_at": "2026-10-06T12:00:00Z",
            "review_basis": "The route action citation and reviewed map wording were checked for this fixture.",
        }
        receipt_path = self.root / f"{title.replace(' ', '-')}.review.json"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        saved_receipt = json.loads(self.cli(
            "flow-review", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"],
            "--overlay", attached["overlay_id"], "--input", os.fspath(receipt_path),
        ).stdout)
        return attached, saved_receipt

    def route_binding_document(self, saved, graph, route, attached, flow_receipt, title="route-binding"):
        binding = {
            "binding_schema_version": 1,
            "snapshot_id": saved["snapshot_id"],
            "extractor_identity": graph["extractor_identity"],
            "route_fact_id": route["id"],
            "overlay_id": attached["overlay_id"],
            "flow_review_receipt_hash": flow_receipt["receipt_hash"],
        }
        binding_hash = hashlib.sha256(json.dumps(
            binding, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("ascii")).hexdigest()
        association_review = {
            "review_schema_version": 1,
            "binding_hash": binding_hash,
            **binding,
            "reviewer_identity": "independent route association reviewer",
            "reviewer_model": "GPT-6.1 Sol High",
            "decision": "accepted",
            "reviewed_at": "2026-10-06T12:30:00Z",
            "review_basis": "The route identity and selected flow purpose were checked against the cited evidence.",
        }
        path = self.root / f"{title}.binding.json"
        path.write_text(json.dumps({"binding": binding, "association_review": association_review}), encoding="utf-8")
        return path, binding, association_review

    def test_evidence_pack_cli_includes_root_and_two_candidate_levels(self):
        saved, graph, route = self.evidence_fixture()
        result = self.evidence_pack(route["id"])
        packet = json.loads(result.stdout)
        self.assertEqual(packet["snapshot_id"], saved["snapshot_id"])
        self.assertEqual(packet["extractor_identity"], graph["extractor_identity"])
        self.assertEqual(packet["route"]["http_method"], "POST")
        self.assertEqual(packet["route"]["route"], "api/customer/save")
        self.assertEqual(packet["root"]["action_method_name"], "Save")
        root_text = "\n".join(item["text"] for item in packet["source_snippets"])
        self.assertIn("handler.Handle()", root_text)
        methods = {method["method_name"] for bundle in packet["candidate_bundles"]
                   for injection in bundle["injection_candidates"] for registration in injection["registrations"]
                   for candidate in registration["implementation_candidates"] for method in candidate["methods"]}
        nested = {method["method_name"] for bundle in packet["candidate_bundles"]
                  for injection in bundle["injection_candidates"] for registration in injection["registrations"]
                  for candidate in registration["implementation_candidates"] for method in candidate["methods"]
                  for call in method.get("invocations", []) for nested_injection in call["injection_candidates"]
                  for nested_registration in nested_injection["registrations"] for nested_candidate in nested_registration["implementation_candidates"]
                  for nested_method in nested_candidate["methods"] for method in [nested_method]}
        self.assertIn("Handle", methods)
        self.assertEqual(nested, {"SaveAsync", "GetAsync"})
        self.assertTrue(packet["selection"]["complete"])
        self.assertEqual(packet["selection"]["omitted_candidate_bundles"], 0)
        self.assertTrue(all(item["sha256"] and item["span"]["offset_unit"] == "unicode_codepoint"
                            for item in packet["source_snippets"] + packet["candidate_snippets"]))
        cap = len(result.stdout.encode("ascii")) // 2
        bounded = json.loads(self.evidence_pack(route["id"], cap).stdout)
        self.assertEqual(bounded["selection"]["included_candidate_bundles"], 0)
        self.assertEqual(bounded["selection"]["omitted_candidate_bundles"], 1)
        self.assertFalse(bounded["selection"]["complete"])

    def test_evidence_pack_refuses_stale_unknown_wrong_kind_and_mandatory_over_cap(self):
        _saved, graph, route = self.evidence_fixture()
        stale = self.repo / "Flow.cs"
        stale.write_text(stale.read_text(encoding="utf-8") + "// changed\n", encoding="utf-8")
        result = self.evidence_pack(route["id"], expect=2)
        self.assertIn("no_saved_snapshot_matches_current_extractor_and_checkout", result.stderr)

        # Restore the saved checkout identity by indexing the new bytes; IDs remain deterministic only for these bytes.
        git(self.repo, "add", "--", "Flow.cs")
        saved = self.index()
        graph = self.graph(saved["snapshot_id"])
        route = next(f for f in graph["facts"] if f["kind"] == "route_action")
        unknown = self.evidence_pack("unknown-route-fact", expect=2)
        self.assertIn("unknown route fact ID", unknown.stderr)
        wrong = next(f["id"] for f in graph["facts"] if f["kind"] == "type_declaration")
        wrong_result = self.evidence_pack(wrong, expect=2)
        self.assertIn("wrong kind", wrong_result.stderr)
        capped = self.evidence_pack(route["id"], 100, expect=2)
        self.assertEqual(capped.stdout, "")
        self.assertIn("complete mandatory evidence pack requires", capped.stderr)

    def test_route_find_returns_structured_unmapped_evidence_pack_step(self):
        saved, graph, route = self.evidence_fixture()
        result = self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                          "--route-fact-id", route["id"], "--max-tokens", "10000")
        document = json.loads(result.stdout)
        self.assertEqual(document["result"], "unmapped")
        self.assertEqual(document["snapshot_id"], saved["snapshot_id"])
        self.assertEqual(document["association_count"], 0)
        self.assertEqual(document["next_step"]["command"], "evidence-pack")
        self.assertEqual(document["next_step"]["arguments"]["--route-fact-id"], route["id"])

    def test_route_binding_is_immutable_and_route_find_returns_complete_fresh_claims(self):
        saved, graph, route = self.evidence_fixture()
        attached, flow_receipt = self.reviewed_route_map(saved, graph, route)
        path, binding, association_review = self.route_binding_document(saved, graph, route, attached, flow_receipt)
        self.cli("route-bind-add", "--db", os.fspath(self.db), "--snapshot", "wrong-snapshot", "--input", os.fspath(path), expect=2)
        path.write_text(json.dumps({"binding": {**binding, "binding_hash": association_review["binding_hash"]},
                                   "association_review": association_review}), encoding="utf-8")
        self.cli("route-bind-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(path), expect=2)
        path.write_text(json.dumps({"binding": binding, "association_review": association_review}), encoding="utf-8")
        first = json.loads(self.cli("route-bind-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(path)).stdout)
        repeated = json.loads(self.cli("route-bind-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(path)).stdout)
        self.assertEqual(first, repeated)
        self.assertEqual(first["binding"]["route_fact_id"], route["id"])
        self.assertNotIn("binding_hash", first["binding"])

        found_result = self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                                "--route-fact-id", route["id"], "--max-tokens", "10000")
        found = json.loads(found_result.stdout)
        self.assertEqual(found["result"], "fresh")
        self.assertEqual(found["association_count"], 1)
        self.assertEqual(found["association"]["binding"], binding)
        self.assertEqual(found["association"]["association_review"]["binding_hash"], association_review["binding_hash"])
        self.assertEqual(found["claim_selection"]["omitted_claims"], 0)
        self.assertEqual(found["claim_selection"]["included_claims"], found["claim_selection"]["total_claims"])
        self.assertEqual(len(found["claims"]), 1)
        generous_size = len(found_result.stdout.encode("ascii"))
        self.assertEqual(found["budget"]["stdout_bytes_including_newline"], generous_size)
        # The limit itself is rendered in the document, so changing it can change
        # the output length by a digit. Compute the exact boundary for its own cap.
        exact_size = self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                              "--route-fact-id", route["id"], "--max-tokens", str(generous_size)).stdout
        exact_size = len(exact_size.encode("ascii"))
        exact = self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                         "--route-fact-id", route["id"], "--max-tokens", str(exact_size))
        self.assertEqual(len(exact.stdout.encode("ascii")), exact_size)
        short = self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                         "--route-fact-id", route["id"], "--max-tokens", str(exact_size - 1), expect=2)
        self.assertEqual(short.stdout, "")
        self.assertIn("complete route-find output requires", short.stderr)

        conflict = dict(association_review, review_basis="A conflicting association review cannot replace the immutable record.")
        path.write_text(json.dumps({"binding": binding, "association_review": conflict}), encoding="utf-8")
        self.cli("route-bind-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(path), expect=2)

    def test_route_find_requires_unique_current_snapshot_and_refuses_stale_sources(self):
        saved, graph, route = self.evidence_fixture()
        routes = self.repo / "Flow.cs"
        routes.write_text(routes.read_text(encoding="utf-8") + "// changed after capture\n", encoding="utf-8")
        stale = self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                         "--route-fact-id", route["id"], "--max-tokens", "10000", expect=2)
        self.assertIn("no_saved_snapshot_matches_current_extractor_and_checkout", stale.stderr)
        stale_coverage = self.coverage(expect=2)
        self.assertIn("no_saved_snapshot_matches_current_extractor_and_checkout", stale_coverage.stderr)

        git(self.repo, "add", "--", "Flow.cs")
        current = self.index()
        with sqlite3.connect(self.db) as connection:
            row = connection.execute("SELECT snapshot_id, payload_json FROM atlas_snapshots WHERE snapshot_id = ?", (current["snapshot_id"],)).fetchone()
            snapshot = json.loads(row[1])
            snapshot["source_graph"]["extractor_identity"] = "obsolete-extractor"
            connection.execute("UPDATE atlas_snapshots SET payload_json = ? WHERE snapshot_id = ?", (json.dumps(snapshot), row[0]))
        old_only = self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                            "--route-fact-id", route["id"], "--max-tokens", "10000", expect=2)
        self.assertIn("no_saved_snapshot_matches_current_extractor_and_checkout", old_only.stderr)
        old_coverage = self.coverage(expect=2)
        self.assertIn("no_saved_snapshot_matches_current_extractor_and_checkout", old_coverage.stderr)

        # Restore one current snapshot and insert a second distinct current row for the same live checkout.
        duplicate_id = current["snapshot_id"] + "-second"
        with sqlite3.connect(self.db) as connection:
            snapshot["source_graph"]["extractor_identity"] = graph["extractor_identity"]
            connection.execute("UPDATE atlas_snapshots SET payload_json = ? WHERE snapshot_id = ?", (json.dumps(snapshot), current["snapshot_id"]))
            duplicate = dict(snapshot, snapshot_id=duplicate_id)
            connection.execute("INSERT INTO atlas_snapshots(snapshot_id, evidence_fingerprint, captured_at, payload_json) VALUES (?, ?, ?, ?)",
                               (duplicate_id, duplicate["evidence_fingerprint"] + "-second", duplicate["captured_at"], json.dumps(duplicate)))
        multiple = self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                            "--route-fact-id", route["id"], "--max-tokens", "10000", expect=2)
        self.assertIn("multiple_saved_snapshots_match_current_extractor_and_checkout", multiple.stderr)
        multiple_coverage = self.coverage(expect=2)
        self.assertIn("multiple_saved_snapshots_match_current_extractor_and_checkout", multiple_coverage.stderr)

    def test_route_find_requires_valid_bindings_and_requires_selection_for_multiple_maps(self):
        saved, graph, route = self.evidence_fixture()
        first_flow, first_receipt = self.reviewed_route_map(saved, graph, route, "Map one")
        first_path, _first_binding, _first_review = self.route_binding_document(saved, graph, route, first_flow, first_receipt, "first")
        self.cli("route-bind-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(first_path))
        second_flow, second_receipt = self.reviewed_route_map(saved, graph, route, "Map two")
        second_path, _second_binding, _second_review = self.route_binding_document(saved, graph, route, second_flow, second_receipt, "second")
        self.cli("route-bind-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(second_path))
        multiple = json.loads(self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                                       "--route-fact-id", route["id"], "--max-tokens", "30000").stdout)
        self.assertEqual(multiple["result"], "selection_required")
        self.assertEqual(len(multiple["associations"]), 2)
        self.assertNotIn("claims", multiple)

        with sqlite3.connect(self.db) as connection:
            row = connection.execute("SELECT payload_json FROM atlas_route_bindings WHERE overlay_id = ?", (first_flow["overlay_id"],)).fetchone()
            tampered = json.loads(row[0])
            tampered["binding"]["overlay_id"] = second_flow["overlay_id"]
            connection.execute("UPDATE atlas_route_bindings SET payload_json = ? WHERE overlay_id = ?",
                               (json.dumps(tampered), first_flow["overlay_id"]))
        refused = self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                           "--route-fact-id", route["id"], "--max-tokens", "30000", expect=2)
        self.assertIn("payload does not match its registry key", refused.stderr)
        coverage_refused = self.coverage(expect=2)
        self.assertIn("payload does not match its registry key", coverage_refused.stderr)

    def test_route_find_refuses_binding_with_tampered_route_registry_key(self):
        saved, graph, route = self.evidence_fixture()
        attached, flow_receipt = self.reviewed_route_map(saved, graph, route)
        path, _binding, _review = self.route_binding_document(saved, graph, route, attached, flow_receipt)
        self.cli("route-bind-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(path))
        with sqlite3.connect(self.db) as connection:
            connection.execute("UPDATE atlas_route_bindings SET route_fact_id = ? WHERE snapshot_id = ? AND route_fact_id = ?",
                               ("tampered-route-key", saved["snapshot_id"], route["id"]))
        result = self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                          "--route-fact-id", route["id"], "--max-tokens", "10000", expect=2)
        self.assertIn("registry key", result.stderr)
        self.assertIn("registry key", self.coverage(expect=2).stderr)

        with sqlite3.connect(self.db) as connection:
            connection.execute("UPDATE atlas_route_bindings SET route_fact_id = ? WHERE snapshot_id = ?",
                               (route["id"], saved["snapshot_id"]))
        with sqlite3.connect(self.db) as connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute("UPDATE atlas_route_bindings SET snapshot_id = ? WHERE route_fact_id = ?",
                               ("tampered-snapshot-key", route["id"]))
        result = self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                          "--route-fact-id", route["id"], "--max-tokens", "10000", expect=2)
        self.assertIn("registry key", result.stderr)

    def test_route_refresh_carries_complete_route_map_through_all_consumers(self):
        saved, _graph, route, attached, reviewed = self.refresh_fixture()
        (self.repo / "Other.cs").write_text("class Other { int Read() { return 2; } }\n", encoding="utf-8")
        self.index()
        refreshed = json.loads(self.route_refresh(saved, route).stdout)
        target = refreshed["snapshot_id"]
        self.assertEqual(refreshed["result"], "carried")
        self.assertEqual(refreshed["carry_provenance"]["origin_snapshot_id"], saved["snapshot_id"])
        self.assertEqual(refreshed["carry_provenance"]["origin_overlay_id"], attached["overlay_id"])
        self.assertEqual(refreshed["carry_provenance"]["origin_review_receipt_hash"], reviewed["receipt_hash"])

        found = json.loads(self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                                    "--route-fact-id", route["id"], "--max-tokens", "100000").stdout)
        self.assertEqual(found["snapshot_id"], target)
        self.assertEqual(found["overlay_id"], attached["overlay_id"])
        self.assertEqual(found["claim_selection"]["included_claims"], 8)
        self.assertEqual(found["claim_selection"]["omitted_claims"], 0)
        self.assertEqual(found["reviewer"]["identity"], "fixture reviewer")
        self.assertEqual(found["reviewer"]["reviewed_at"], "2026-10-06T12:00:00Z")
        for field, value in refreshed["carry_provenance"].items():
            self.assertEqual(found["carry_provenance"][field], value)

        focus = json.loads(self.cli("focus", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                                    "--snapshot", target, "--overlay", attached["overlay_id"],
                                    "--max-tokens", "100000").stdout)
        self.assertEqual(focus["snapshot_id"], target)
        self.assertEqual(focus["claim_selection"]["included_claims"], 8)
        self.assertEqual(focus["carry_provenance"]["origin_snapshot_id"], saved["snapshot_id"])
        flow = json.loads(self.cli("flow-query", "--db", os.fspath(self.db), "--snapshot", target,
                                   "--overlay", attached["overlay_id"]).stdout)
        self.assertEqual(flow["snapshot_id"], target)
        self.assertEqual(flow["review_status"], "accepted")
        self.assertEqual(flow["review_receipt"]["receipt_hash"], reviewed["receipt_hash"])
        self.assertEqual(flow["carry_provenance"]["origin_snapshot_id"], saved["snapshot_id"])

        question, draft = self.root / "question.txt", self.root / "draft.txt"
        question.write_text("What does this reviewed route map say?", encoding="utf-8")
        draft.write_text("The reviewed map contains eight route claims.", encoding="utf-8")
        answer_args = ("answer-check", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                       "--snapshot", target, "--overlay", attached["overlay_id"],
                       "--question-file", os.fspath(question), "--draft-file", os.fspath(draft))
        packet = json.loads(self.cli(*answer_args).stdout)
        self.assertEqual(packet["binding"]["snapshot_id"], target)
        self.assertEqual(packet["binding"]["overlay_id"], attached["overlay_id"])
        self.assertEqual(packet["review_provenance"]["reviewer"]["identity"], "fixture reviewer")
        self.assertEqual(packet["review_provenance"]["review_receipt_hash"], reviewed["receipt_hash"])
        self.assertEqual(packet["review_provenance"]["carry_provenance"]["origin_snapshot_id"], saved["snapshot_id"])
        self.assertEqual(len(packet["claims"]), 8)
        answer_review = {"packet_sha256": hashlib.sha256(json.dumps(packet, ensure_ascii=True, sort_keys=True,
                                separators=(",", ":")).encode("ascii") + b"\n").hexdigest(),
                         "decision": "accepted", "reviewer_identity": "answer reviewer", "reviewer_model": "GPT-6.1 Sol High",
                         "claim_reviews": [{"claim_number": index, "disposition": "covered",
                                            "basis": "The draft covers the complete claim set in this fixture."}
                                           for index in range(1, 9)]}
        answer_review_path = self.root / "answer.review.json"
        answer_review_path.write_text(json.dumps(answer_review), encoding="utf-8")
        accepted = self.cli(*answer_args, "--review", os.fspath(answer_review_path))
        self.assertEqual(accepted.stdout.encode("utf-8"), draft.read_bytes())

        repeated = json.loads(self.route_refresh(saved, route).stdout)
        self.assertEqual(repeated, refreshed)

    def test_route_refresh_refuses_changed_route_handler(self):
        saved, _graph, route, _attached, _reviewed = self.refresh_fixture()
        source = self.repo / "Handler.cs"
        source.write_text(source.read_text(encoding="utf-8").replace("store.SaveAsync(); store.GetAsync();",
                                                                    "store.GetAsync(); store.SaveAsync();"), encoding="utf-8")
        current = self.index()
        target_routes = [fact for fact in self.graph(current["snapshot_id"])["facts"] if fact.get("id") == route["id"]]
        self.assertEqual(target_routes, [route])
        refused = self.route_refresh(saved, route, expect=2)
        self.assertIn("cited source hash changed", refused.stderr)
        with sqlite3.connect(self.db) as connection:
            exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='atlas_route_carries'").fetchone()
            count = connection.execute("SELECT COUNT(*) FROM atlas_route_carries").fetchone()[0] if exists else 0
        self.assertEqual(count, 0)

    def test_route_refresh_refuses_unchanged_origin_without_poisoning_review(self):
        saved, _graph, route, attached, _reviewed = self.refresh_fixture()
        refused = self.route_refresh(saved, route, expect=2)
        self.assertIn("target equals the accepted origin", refused.stderr)
        found = json.loads(self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                                    "--route-fact-id", route["id"], "--max-tokens", "100000").stdout)
        self.assertEqual(found["overlay_id"], attached["overlay_id"])
        self.assertEqual(found["claim_selection"]["included_claims"], 8)

    def test_route_refresh_refuses_change_just_before_commit(self):
        saved, _graph, route, _attached, _reviewed = self.refresh_fixture()
        other = self.repo / "Other.cs"
        other.write_text("class Other { int Read() { return 2; } }\n", encoding="utf-8")
        handler = self.repo / "Handler.cs"
        spec = importlib.util.spec_from_file_location("atlas_refresh_race_test", SCRIPT)
        atlas = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(atlas)
        original_connect = atlas._connect_for_index

        def change_at_connect(path):
            handler.write_text(handler.read_text(encoding="utf-8").replace("store.SaveAsync(); store.GetAsync();",
                                                                              "store.GetAsync(); store.SaveAsync();"), encoding="utf-8")
            return original_connect(path)

        with mock.patch.object(sys, "path", [os.fspath(SCRIPT.parent), *sys.path]), mock.patch.object(
                atlas, "_connect_for_index", side_effect=change_at_connect):
            with self.assertRaisesRegex(atlas.AtlasError, "changed before route refresh commit"):
                atlas.route_refresh(os.fspath(self.db), os.fspath(self.repo), saved["snapshot_id"], route["id"], 100000)
        with sqlite3.connect(self.db) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM atlas_snapshots").fetchone()[0], 1)
            exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='atlas_route_carries'").fetchone()
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM atlas_route_carries").fetchone()[0] if exists else 0, 0)

    def test_route_refresh_refuses_new_candidate_declaration_and_registration(self):
        saved, _graph, route, _attached, _reviewed = self.refresh_fixture()
        extra = self.repo / "ExtraCandidate.cs"
        extra.write_text("class Handler { void Handle() {} }\n", encoding="utf-8")
        git(self.repo, "add", "--", "ExtraCandidate.cs")
        self.index()
        declaration_refusal = self.route_refresh(saved, route, expect=2)
        self.assertIn("evidence packet changed", declaration_refusal.stderr)

    def test_route_refresh_refuses_new_matching_registration(self):
        saved, _graph, route, _attached, _reviewed = self.refresh_fixture()
        registration = self.repo / "Other.cs"
        registration.write_text("class Other { int Read() { return 1; } }\nclass ExtraHandler { void Handle() {} }\n"
                                "class MoreRegistrations { void Add() { services.AddScoped<IHandler, ExtraHandler>(); } }\n", encoding="utf-8")
        git(self.repo, "add", "--", "Other.cs")
        self.index()
        registration_refusal = self.route_refresh(saved, route, expect=2)
        self.assertIn("evidence packet changed", registration_refusal.stderr)

    def test_route_refresh_refuses_tampered_origin_review_provenance(self):
        saved, _graph, route, _attached, _reviewed = self.refresh_fixture()
        (self.repo / "Other.cs").write_text("class Other { int Read() { return 2; } }\n", encoding="utf-8")
        self.index()
        refreshed = json.loads(self.route_refresh(saved, route).stdout)
        with sqlite3.connect(self.db) as connection:
            connection.execute("UPDATE atlas_flow_reviews SET receipt_json = replace(receipt_json, 'fixture reviewer', 'tampered reviewer') WHERE snapshot_id=?",
                               (saved["snapshot_id"],))
        refused = self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                           "--route-fact-id", route["id"], "--max-tokens", "100000", expect=2)
        self.assertIn("review receipt content hash is invalid", refused.stderr)
        self.assertEqual(refreshed["result"], "carried")

    def test_route_refresh_refuses_tampered_carry_overlay_identity(self):
        saved, _graph, route, _attached, _reviewed = self.refresh_fixture()
        (self.repo / "Other.cs").write_text("class Other { int Read() { return 2; } }\n", encoding="utf-8")
        self.route_refresh(saved, route)
        with sqlite3.connect(self.db) as connection:
            connection.execute("UPDATE atlas_route_carries SET origin_overlay_id = ?", ("wrong-overlay",))
        refused = self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                           "--route-fact-id", route["id"], "--max-tokens", "100000", expect=2)
        self.assertIn("registry identity differs", refused.stderr)

    def test_route_refresh_rolls_back_target_snapshot_when_carry_insert_fails(self):
        saved, _graph, route, _attached, _reviewed = self.refresh_fixture()
        (self.repo / "Other.cs").write_text("class Other { int Read() { return 2; } }\n", encoding="utf-8")
        too_small = self.route_refresh(saved, route, expect=2, max_tokens=1)
        self.assertIn("complete route-find output requires", too_small.stderr)
        with sqlite3.connect(self.db) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM atlas_snapshots").fetchone()[0], 1)
        with sqlite3.connect(self.db) as connection:
            connection.execute("""CREATE TABLE atlas_route_carries (
                target_snapshot_id TEXT NOT NULL, route_fact_id TEXT NOT NULL, overlay_id TEXT NOT NULL,
                origin_snapshot_id TEXT NOT NULL, origin_overlay_id TEXT NOT NULL, origin_receipt_hash TEXT NOT NULL,
                binding_hash TEXT NOT NULL, association_review_hash TEXT NOT NULL, packet_sha256 TEXT NOT NULL,
                PRIMARY KEY(target_snapshot_id, route_fact_id))""")
            connection.execute("CREATE TRIGGER refuse_route_carry BEFORE INSERT ON atlas_route_carries BEGIN SELECT RAISE(ABORT, 'test carry failure'); END")
        refused = self.route_refresh(saved, route, expect=2)
        self.assertIn("test carry failure", refused.stderr)
        with sqlite3.connect(self.db) as connection:
            snapshots = connection.execute("SELECT snapshot_id FROM atlas_snapshots ORDER BY snapshot_id").fetchall()
            carries = connection.execute("SELECT COUNT(*) FROM atlas_route_carries").fetchone()[0]
        self.assertEqual([row[0] for row in snapshots], [saved["snapshot_id"]])
        self.assertEqual(carries, 0)

    def test_route_find_refuses_flow_receipt_column_tampering(self):
        saved, graph, route = self.evidence_fixture()
        attached, flow_receipt = self.reviewed_route_map(saved, graph, route)
        path, _binding, _review = self.route_binding_document(saved, graph, route, attached, flow_receipt)
        self.cli("route-bind-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(path))
        with sqlite3.connect(self.db) as connection:
            connection.execute("UPDATE atlas_flow_reviews SET receipt_hash = ? WHERE snapshot_id = ? AND overlay_id = ?",
                               ("0" * 64, saved["snapshot_id"], attached["overlay_id"]))
        refused = self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                           "--route-fact-id", route["id"], "--max-tokens", "10000", expect=2)
        self.assertIn("flow review receipt registry hash", refused.stderr)
        self.assertIn("flow review receipt registry hash", self.coverage(expect=2).stderr)

    def test_coverage_pages_all_routes_once_with_global_counts_and_exact_byte_boundary(self):
        saved, graph, routes = self.coverage_fixture()
        self.assertEqual(len(routes), 6)
        too_small = self.coverage(max_tokens=1, expect=2)
        self.assertEqual(too_small.stdout, "")
        required = int(too_small.stderr.split("requires ", 1)[1].split(" ASCII", 1)[0])
        adjusted = self.coverage(max_tokens=required, expect=2)
        required = int(adjusted.stderr.split("requires ", 1)[1].split(" ASCII", 1)[0])
        boundary = self.coverage(max_tokens=required)
        first = json.loads(boundary.stdout)
        self.assertEqual(first["snapshot"]["snapshot_id"], saved["snapshot_id"])
        self.assertEqual(first["snapshot"]["extractor_identity"], graph["extractor_identity"])
        self.assertEqual(first["current_checkout"]["repository_root"], os.fspath(self.repo.resolve()))
        self.assertEqual(len(first["routes"]), 1)
        self.assertEqual(first["included_routes"], 1)
        self.assertEqual(first["remaining_routes"], 5)
        self.assertEqual(first["next_offset"], 1)
        self.assertEqual(first["budget"]["stdout_bytes_including_newline"], len(self.coverage(max_tokens=required).stdout.encode("ascii")))
        one_short = self.coverage(max_tokens=required - 1, expect=2)
        self.assertEqual(one_short.stdout, "")
        self.assertIn(f"requires {required} ASCII stdout bytes", one_short.stderr)

        seen = [row["route_fact_id"] for row in first["routes"]]
        page = first
        while page["next_offset"] is not None:
            page_offset = page["next_offset"]
            page_result = self.coverage(max_tokens=required + 10, offset=page_offset, expect=None)
            if page_result.returncode:
                page_required = int(page_result.stderr.split("requires ", 1)[1].split(" ASCII", 1)[0])
                page_result = self.coverage(max_tokens=page_required + 10, offset=page_offset)
            page = json.loads(page_result.stdout)
            seen.extend(row["route_fact_id"] for row in page["routes"])
        self.assertEqual(seen, [route["id"] for route in routes])
        self.assertEqual(len(set(seen)), len(routes))
        self.assertEqual(first["counts"], {"open": 6, "one_reviewed_link": 0, "selection_required": 0, "total_routes": 6})
        eof = json.loads(self.coverage(max_tokens=required, offset=len(routes)).stdout)
        self.assertEqual(eof["routes"], [])
        self.assertIsNone(eof["next_offset"])
        self.assertEqual(eof["remaining_routes"], 0)
        self.assertEqual(self.coverage(max_tokens=required, offset=len(routes) + 1, expect=2).stdout, "")
        self.assertEqual(self.coverage(max_tokens=required, offset=-1, expect=2).stdout, "")

    def test_coverage_reports_open_single_and_multiple_reviewed_associations(self):
        saved, graph, routes = self.coverage_fixture(count=3)
        for route, suffix in ((routes[1], "single"), (routes[2], "multiple-a"), (routes[2], "multiple-b")):
            attached, receipt = self.reviewed_route_map(saved, graph, route, f"Coverage {suffix}")
            path, _binding, _review = self.route_binding_document(saved, graph, route, attached, receipt, f"coverage-{suffix}")
            self.cli("route-bind-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(path))
        document = json.loads(self.coverage().stdout)
        self.assertEqual(document["counts"], {"open": 1, "one_reviewed_link": 1, "selection_required": 1, "total_routes": 3})
        by_id = {row["route_fact_id"]: row for row in document["routes"]}
        self.assertEqual(by_id[routes[0]["id"]]["association_state"], "open")
        self.assertEqual(by_id[routes[1]["id"]]["reviewed_association_count"], 1)
        self.assertEqual(by_id[routes[2]["id"]]["association_state"], "selection_required")
        self.assertEqual(by_id[routes[2]["id"]]["reviewed_association_count"], 2)

    def test_coverage_accepts_missing_binding_table_and_zero_routes(self):
        self.index()
        no_routes = json.loads(self.coverage().stdout)
        self.assertEqual(no_routes["counts"]["total_routes"], 0)
        self.assertEqual(no_routes["routes"], [])
        self.assertIsNone(no_routes["next_offset"])

        # A fresh database has no binding registry table; all saved routes remain open.
        self.db = self.root / "no-bindings.sqlite"
        _saved, _graph, routes = self.coverage_fixture(count=2)
        result = json.loads(self.coverage().stdout)
        self.assertEqual(result["counts"]["open"], len(routes))

    def test_coverage_rejects_corrupt_route_metadata(self):
        saved, _graph, routes = self.coverage_fixture(count=2)
        with sqlite3.connect(self.db) as connection:
            row = connection.execute("SELECT payload_json FROM atlas_snapshots WHERE snapshot_id = ?", (saved["snapshot_id"],)).fetchone()
            snapshot = json.loads(row[0])
            route = next(fact for fact in snapshot["source_graph"]["facts"] if fact.get("id") == routes[0]["id"])
            route["action_name"] = None
            connection.execute("UPDATE atlas_snapshots SET payload_json = ? WHERE snapshot_id = ?", (json.dumps(snapshot), saved["snapshot_id"]))
        refused = self.coverage(expect=2)
        self.assertIn("invalid action_name", refused.stderr)

    def test_coverage_rejects_nonstring_and_duplicate_route_ids(self):
        saved, _graph, routes = self.coverage_fixture(count=2)
        with sqlite3.connect(self.db) as connection:
            row = connection.execute("SELECT payload_json FROM atlas_snapshots WHERE snapshot_id = ?", (saved["snapshot_id"],)).fetchone()
            original = json.loads(row[0])
        for mutate, expected in (
            (lambda snapshot: next(fact for fact in snapshot["source_graph"]["facts"] if fact.get("id") == routes[0]["id"]).update({"id": 7}), "non-string or empty id"),
            (lambda snapshot: next(fact for fact in snapshot["source_graph"]["facts"] if fact.get("id") == routes[1]["id"]).update({"id": routes[0]["id"]}), "ID is duplicated"),
        ):
            changed = json.loads(json.dumps(original))
            mutate(changed)
            with sqlite3.connect(self.db) as connection:
                connection.execute("UPDATE atlas_snapshots SET payload_json = ? WHERE snapshot_id = ?", (json.dumps(changed), saved["snapshot_id"]))
            self.assertIn(expected, self.coverage(expect=2).stderr)
        with sqlite3.connect(self.db) as connection:
            connection.execute("UPDATE atlas_snapshots SET payload_json = ? WHERE snapshot_id = ?", (json.dumps(original), saved["snapshot_id"]))

    def test_coverage_rejects_missing_or_malformed_fact_lists_and_cross_kind_id_collisions(self):
        saved, _graph, routes = self.coverage_fixture(count=2)
        with sqlite3.connect(self.db) as connection:
            row = connection.execute("SELECT payload_json FROM atlas_snapshots WHERE snapshot_id = ?", (saved["snapshot_id"],)).fetchone()
            original = json.loads(row[0])
        graph_original = original["source_graph"]

        for graph, expected in (
            ({key: value for key, value in graph_original.items() if key != "facts"}, "facts must be a list of objects"),
            ({**graph_original, "facts": {}}, "facts must be a list of objects"),
            ({**graph_original, "facts": [*graph_original["facts"], "not-a-fact"]}, "facts must be a list of objects"),
        ):
            changed = json.loads(json.dumps(original))
            changed["source_graph"] = graph
            with sqlite3.connect(self.db) as connection:
                connection.execute("UPDATE atlas_snapshots SET payload_json = ? WHERE snapshot_id = ?", (json.dumps(changed), saved["snapshot_id"]))
            self.assertIn(expected, self.coverage(expect=2).stderr)

        changed = json.loads(json.dumps(original))
        changed["source_graph"]["facts"].append({"id": routes[0]["id"], "kind": "type_declaration"})
        with sqlite3.connect(self.db) as connection:
            connection.execute("UPDATE atlas_snapshots SET payload_json = ? WHERE snapshot_id = ?", (json.dumps(changed), saved["snapshot_id"]))
        self.assertIn("not unique across source graph facts", self.coverage(expect=2).stderr)
        ambiguous = self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                             "--route-fact-id", routes[0]["id"], "--max-tokens", "10000", expect=2)
        self.assertIn("wrong kind or is ambiguous", ambiguous.stderr)

        with sqlite3.connect(self.db) as connection:
            connection.execute("UPDATE atlas_snapshots SET payload_json = ? WHERE snapshot_id = ?", (json.dumps(original), saved["snapshot_id"]))

    def test_evidence_pack_preserves_registration_ambiguity_and_shadowing(self):
        _saved, graph, route = self.evidence_fixture(
            extra_registration="services.AddTransient<IHandler, OtherHandler>();", shadow=True,
        )
        packet = json.loads(self.evidence_pack(route["id"]).stdout)
        handler_call = packet["candidate_bundles"][0]
        injection = handler_call["injection_candidates"][0]
        self.assertEqual(injection["registration_match_count"], 2)
        self.assertEqual(len(injection["registrations"]), 2)
        reasons = [item["reason"] for call in handler_call["injection_candidates"][0]["registrations"][0]
                   ["implementation_candidates"][0]["methods"][0]["invocations"] for item in call["unresolved"]]
        self.assertTrue(any("shadow" in reason for reason in reasons))
        self.assertTrue(all(candidate.get("traversable") is False
                            for registration in injection["registrations"]
                            for candidate in registration["implementation_candidates"]))

    def test_evidence_pack_excludes_sibling_action_authorization(self):
        source = self.repo / "Auth.cs"
        source.write_text('''[Authorize]
[Route("api/auth")]
class AuthController
{
    [HttpPost("admin/login")]
    [Authorize(Policy = "Login")]
    void AdminLogin() {}

    [HttpPost("admin/logout")]
    [Authorize(Policy = "Logout")]
    void AdminLogout() {}
}
''', encoding="utf-8")
        git(self.repo, "add", "--", "Auth.cs")
        saved = self.index()
        graph = self.graph(saved["snapshot_id"])
        route = next(f for f in graph["facts"] if f.get("kind") == "route_action" and f.get("route_literal") == "api/auth/admin/login")
        sibling = next(f for f in graph["facts"] if f.get("kind") == "authorization_attribute" and f.get("method_id")
                       and next(m for m in graph["facts"] if m.get("id") == f["method_id"])["method_name"] == "AdminLogout")
        packet = json.loads(self.evidence_pack(route["id"]).stdout)
        included = set(packet["route"]["authorization_fact_ids"])
        self.assertIn(sibling["owner_type_id"], {route["controller_type_id"]})
        self.assertNotIn(sibling["id"], included)
        self.assertEqual(len(included), 2)  # Controller authorization and AdminLogin authorization.

    def test_evidence_pack_fails_closed_on_missing_implementation_candidate_fact(self):
        saved, graph, route = self.evidence_fixture()
        with sqlite3.connect(self.db) as connection:
            row = connection.execute("SELECT payload_json FROM atlas_snapshots WHERE snapshot_id = ?", (saved["snapshot_id"],)).fetchone()
            payload = json.loads(row[0])
            candidate = next(c for c in payload["source_graph"]["candidates"]
                             if c.get("expression_side") == "implementation"
                             and any(f.get("kind") == "dependency_registration" and f["id"] == c["subject_fact_id"]
                                     and f.get("implementation_type_expression") == "Handler"
                                     for f in payload["source_graph"]["facts"]))
            candidate["candidate_fact_ids"] = ["missing-declaration-fact"]
            connection.execute("UPDATE atlas_snapshots SET payload_json = ? WHERE snapshot_id = ?", (json.dumps(payload), saved["snapshot_id"]))
        result = self.evidence_pack(route["id"], expect=2)
        self.assertEqual(result.stdout, "")
        self.assertIn("missing or wrong-kind declaration fact ID", result.stderr)

    def test_evidence_pack_render_stabilizes_byte_count_at_digit_boundary(self):
        spec = importlib.util.spec_from_file_location("atlas_under_test", SCRIPT)
        atlas = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(atlas)
        document = {"budget": {"stdout_bytes_including_newline": 0}, "padding": "x" * 9936}
        with self.assertRaises(atlas.AtlasError):
            atlas._evidence_pack_render(document, 10000)
        rendered = atlas._evidence_pack_render(document, 20000)
        self.assertEqual(document["budget"]["stdout_bytes_including_newline"], len(rendered))

    def test_discover_ranks_multiple_routes_and_respects_exact_output_cap(self):
        routes = self.repo / "Routes.cs"
        routes.write_text('''using Microsoft.AspNetCore.Mvc;
namespace Demo;
[ApiController]
[Route("api/customer")]
class PhotoController
{
    [HttpPost("photo/upload")] void UploadPhoto() {}
    [HttpPost("photo/submit-image")] void SubmitImage() {}
}
[Route("api/admin")]
class OtherController
{
    [HttpPost("photo/upload")] void UploadPhoto() {}
}
''', encoding="utf-8")
        git(self.repo, "add", "--", "Routes.cs")
        saved = self.index()
        terms = ["customer", "photo", "upload", "image", "selfie"]

        full = self.discover_routes(terms)
        document = json.loads(full.stdout)
        exact_size = len(full.stdout.encode("ascii"))
        self.assertEqual(document["snapshot_id"], saved["snapshot_id"])
        self.assertEqual(document["result"], "candidates")
        self.assertEqual(document["budget"]["stdout_bytes_including_newline"], exact_size)
        self.assertEqual(document["candidate_selection"], {"included_candidates": 3, "omitted_candidates": 0, "total_candidates": 3})
        self.assertEqual([item["route"] for item in document["candidates"][:2]], ["api/customer/photo/submit-image", "api/customer/photo/upload"])
        self.assertEqual([item["lexical_score"] for item in document["candidates"]], [3, 3, 2])
        for item in document["candidates"]:
            self.assertTrue(item["fact_id"])
            self.assertEqual(set(item["action_source"]), {"fact_id", "path", "sha256", "span"})
            self.assertEqual(set(item["controller_source"]), {"fact_id", "path", "sha256", "span"})
            self.assertTrue(item["action_source"]["span"])
            self.assertTrue(item["controller_source"]["span"])
            self.assertEqual(item["action_source"]["sha256"], item["controller_source"]["sha256"])

        exact = None
        for _ in range(5):
            exact = self.discover_routes(terms, exact_size)
            measured = len(exact.stdout.encode("ascii"))
            if measured == exact_size:
                break
            exact_size = measured
        self.assertIsNotNone(exact)
        self.assertEqual(len(exact.stdout.encode("ascii")), exact_size)
        self.assertEqual(json.loads(exact.stdout)["candidate_selection"]["included_candidates"], 3)
        one_short = self.discover_routes(terms, exact_size - 1)
        shortened = json.loads(one_short.stdout)
        self.assertLessEqual(len(one_short.stdout.encode("ascii")), exact_size - 1)
        self.assertEqual(shortened["candidate_selection"]["omitted_candidates"], 1)
        self.assertEqual(shortened["candidates"], document["candidates"][:2])

        too_small = self.discover_routes(terms, 1, expect=2)
        self.assertEqual(too_small.stdout, "")
        self.assertIn("complete discover output requires", too_small.stderr)
        self.assertIn("stdout withheld", too_small.stderr)

        unmatched = self.discover_routes(["unrelated-term"], 10000)
        unmatched_json = json.loads(unmatched.stdout)
        self.assertEqual(unmatched_json["result"], "no_lexical_matches")
        self.assertEqual(unmatched_json["candidate_selection"]["total_candidates"], 0)
        self.assertEqual(unmatched_json["unmatched_route_count"], 3)

    def test_discover_refuses_same_status_changed_bytes_and_caps_stale_diagnostics(self):
        routes = self.repo / "Routes.cs"
        routes.write_text('namespace Demo; [Route("api/customer")] class CustomerController { [HttpPost("photo/upload")] void UploadPhoto() {} }\n', encoding="utf-8")
        git(self.repo, "add", "--", "Routes.cs")
        self.index()

        routes.write_text('namespace Demo; [Route("api/customer")] class CustomerController { [HttpPost("photo/upload")] void UploadPhoto() { } }\n', encoding="utf-8")
        first_status = git(self.repo, "status", "--porcelain=v1", "-z")
        first = self.discover_routes(["customer", "photo", "upload"], 10000, expect=3)
        stale = json.loads(first.stdout)
        self.assertEqual(stale["result"], "refused")
        self.assertEqual(stale["candidate_selection"]["total_candidates"], 0)
        self.assertTrue(any("content hash changed" in reason for mismatch in stale["source_mismatches"] for reason in mismatch["reasons"]))
        exact_size = len(first.stdout.encode("ascii"))
        self.assertEqual(stale["budget"]["stdout_bytes_including_newline"], exact_size)

        routes.write_text('namespace Demo; [Route("api/customer")] class CustomerController { [HttpPost("photo/upload")] void UploadPhoto(){} }\n', encoding="utf-8")
        self.assertEqual(git(self.repo, "status", "--porcelain=v1", "-z"), first_status)
        second = self.discover_routes(["customer", "photo", "upload"], exact_size, expect=3)
        second_json = json.loads(second.stdout)
        self.assertLessEqual(len(second.stdout.encode("ascii")), exact_size)
        self.assertEqual(second_json["budget"]["stdout_bytes_including_newline"], len(second.stdout.encode("ascii")))
        short = self.discover_routes(["customer", "photo", "upload"], 1, expect=2)
        self.assertEqual(short.stdout, "")
        self.assertIn("complete discover output requires", short.stderr)
        self.assertIn("stdout withheld", short.stderr)

    def test_discover_refuses_snapshot_with_old_extractor(self):
        routes = self.repo / "Routes.cs"
        routes.write_text('namespace Demo; [Route("api/customer")] class CustomerController { [HttpPost("photo/upload")] void UploadPhoto() {} }\n', encoding="utf-8")
        git(self.repo, "add", "--", "Routes.cs")
        saved = self.index()
        with sqlite3.connect(self.db) as connection:
            row = connection.execute("SELECT payload_json FROM atlas_snapshots WHERE snapshot_id = ?", (saved["snapshot_id"],)).fetchone()
            payload = json.loads(row[0])
            payload["source_graph"]["extractor_identity"] = "csharp-lexical-facts-v6:python-stdlib-lexer"
            connection.execute("UPDATE atlas_snapshots SET payload_json = ? WHERE snapshot_id = ?", (json.dumps(payload), saved["snapshot_id"]))
        result = self.discover_routes(["customer", "photo", "upload"], 10000, expect=3)
        document = json.loads(result.stdout)
        self.assertEqual(document["reason"], "no_saved_snapshot_matches_current_extractor_and_checkout")
        self.assertEqual(document["compatible_snapshot_count"], 0)
        self.assertEqual(document["candidate_selection"]["total_candidates"], 0)

    def test_discover_refuses_multiple_current_snapshot_matches(self):
        routes = self.repo / "Routes.cs"
        routes.write_text('namespace Demo; [Route("api/customer")] class CustomerController { [HttpPost("photo/upload")] void UploadPhoto() {} }\n', encoding="utf-8")
        git(self.repo, "add", "--", "Routes.cs")
        saved = self.index()
        with sqlite3.connect(self.db) as connection:
            row = connection.execute(
                "SELECT captured_at, payload_json FROM atlas_snapshots WHERE snapshot_id = ?",
                (saved["snapshot_id"],),
            ).fetchone()
            payload = json.loads(row[1])
            payload["snapshot_id"] = "atlas-test-duplicate"
            connection.execute(
                "INSERT INTO atlas_snapshots(snapshot_id, evidence_fingerprint, captured_at, payload_json) VALUES (?, ?, ?, ?)",
                (payload["snapshot_id"], "duplicate-evidence-fingerprint", row[0], json.dumps(payload)),
            )
        result = self.discover_routes(["customer", "photo", "upload"], 10000, expect=3)
        document = json.loads(result.stdout)
        self.assertEqual(document["reason"], "multiple_saved_snapshots_match_current_extractor_and_checkout")
        self.assertEqual(len(document["matching_snapshot_ids"]), 2)
        self.assertEqual(document["candidate_selection"]["total_candidates"], 0)

    def test_persists_and_queries_in_separate_process_with_nul_safe_paths(self):
        first = self.index()
        self.assertEqual(first["schema_version"], 2)
        self.assertIsNone(first["head"])
        self.assertTrue(first["head_ref"].startswith("refs/heads/"))
        self.assertEqual(first["inventory_basis"], "git-index-paths+working-tree-bytes")
        self.assertEqual(first["tracked_count"], 2)
        a_file = next(item for item in first["files"] if item["path"] == "a.txt")
        self.assertEqual(a_file["sha256"], hashlib.sha256(b"alpha\x00\n").hexdigest())
        self.assertEqual(a_file["size_bytes"], 7)

        reopened = self.query(first["snapshot_id"])
        self.assertEqual(reopened["files"], first["files"])
        exact = self.query(first["snapshot_id"], "--path", "sub dir/b.txt")
        self.assertEqual(exact["matched_count"], 1)
        self.assertEqual(exact["files"][0]["sha256"], hashlib.sha256(b"beta\n").hexdigest())

    def test_fingerprint_repeats_without_capture_time_and_changes_for_dirty_bytes(self):
        first = self.index()
        repeated = self.index()
        self.assertEqual(first["snapshot_id"], repeated["snapshot_id"])
        self.assertEqual(first["evidence_fingerprint"], repeated["evidence_fingerprint"])
        self.assertEqual(first["captured_at"], repeated["captured_at"])

        (self.repo / "a.txt").write_bytes(b"changed while HEAD stays fixed")
        changed = self.index()
        self.assertNotEqual(changed["snapshot_id"], first["snapshot_id"])
        self.assertNotEqual(changed["evidence_fingerprint"], first["evidence_fingerprint"])
        self.assertIsNone(changed["head"])
        self.assertEqual(changed["head_ref"], first["head_ref"])
        self.assertEqual(self.query(first["snapshot_id"])["files"], first["files"])
        self.assertEqual(self.query(changed["snapshot_id"])["head"], first["head"])

    def test_untracked_files_appear_only_in_status_and_capture_is_repeatable(self):
        (self.repo / "untracked.bin").write_bytes(b"outside inventory")
        snap = self.index()
        self.assertNotIn("untracked.bin", [entry["path"] for entry in snap["files"]])
        self.assertIn("untracked.bin", [entry["path"] for entry in snap["status"]])

    def test_failed_capture_does_not_add_partial_snapshot_and_missing_query_does_not_create_db(self):
        saved = self.index()
        with sqlite3.connect(self.db) as connection:
            before = connection.execute("SELECT count(*) FROM atlas_snapshots").fetchone()[0]
        self.cli("index", "--repo", os.fspath(self.root / "not-a-repo"), "--db", os.fspath(self.db), expect=2)
        with sqlite3.connect(self.db) as connection:
            after = connection.execute("SELECT count(*) FROM atlas_snapshots").fetchone()[0]
        self.assertEqual(after, before)
        self.assertEqual(self.query(saved["snapshot_id"])["snapshot_id"], saved["snapshot_id"])

        absent_db = self.root / "absent.sqlite"
        failed = subprocess.run(
            [sys.executable, os.fspath(SCRIPT), "query", "--db", os.fspath(absent_db), "--snapshot", "missing"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.assertEqual(failed.returncode, 2)
        self.assertFalse(absent_db.exists())

    def test_missing_tracked_path_is_explicit(self):
        (self.repo / "a.txt").unlink()
        snap = self.index()
        missing = next(item for item in snap["files"] if item["path"] == "a.txt")
        self.assertEqual(missing["presence"], "missing")
        self.assertIsNone(missing["sha256"])

    def test_intermediate_symlink_is_rejected_and_previous_snapshot_remains_queryable(self):
        saved = self.index()
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "b.txt").write_bytes(b"outside secret bytes")
        tracked_parent = self.repo / "sub dir"
        (tracked_parent / "b.txt").unlink()
        tracked_parent.rmdir()
        tracked_parent.symlink_to(outside, target_is_directory=True)

        with sqlite3.connect(self.db) as connection:
            before = connection.execute("SELECT count(*) FROM atlas_snapshots").fetchone()[0]
        failure = self.cli(
            "index", "--repo", os.fspath(self.repo), "--db", os.fspath(self.db), expect=2
        )
        self.assertIn("unsafe tracked path 'sub dir/b.txt'", failure.stderr)
        self.assertIn("cannot open parent component 'sub dir'", failure.stderr)
        self.assertNotIn("outside secret bytes", failure.stderr)
        with sqlite3.connect(self.db) as connection:
            after = connection.execute("SELECT count(*) FROM atlas_snapshots").fetchone()[0]
        self.assertEqual(after, before)
        self.assertEqual(self.query(saved["snapshot_id"])["files"], saved["files"])

    def test_direct_leaf_symlink_is_recorded_without_reading_its_target(self):
        outside = self.root / "outside secret"
        outside.write_bytes(b"must not be read")
        leaf = self.repo / "leaf-link"
        leaf.symlink_to(outside)
        git(self.repo, "add", "--", "leaf-link")

        saved = self.index()
        evidence = next(entry for entry in saved["files"] if entry["path"] == "leaf-link")
        link_bytes = os.fsencode(os.readlink(leaf))
        self.assertEqual(evidence["type"], "symlink")
        self.assertEqual(evidence["size_bytes"], len(link_bytes))
        self.assertEqual(evidence["sha256"], hashlib.sha256(link_bytes).hexdigest())
        self.assertNotEqual(evidence["sha256"], hashlib.sha256(outside.read_bytes()).hexdigest())

    def test_query_database_paths_with_uri_delimiters_and_no_unintended_files(self):
        expected_entries = {"repo"}
        for name in ("question?mark.sqlite", "hash#mark.sqlite", "percent%mark.sqlite"):
            with self.subTest(name=name):
                db = self.root / name
                indexed = json.loads(self.cli(
                    "index", "--repo", os.fspath(self.repo), "--db", os.fspath(db)
                ).stdout)
                queried = json.loads(self.cli(
                    "query", "--db", os.fspath(db), "--snapshot", indexed["snapshot_id"]
                ).stdout)
                self.assertEqual(queried["snapshot_id"], indexed["snapshot_id"])
                expected_entries.add(name)
                self.assertEqual({path.name for path in self.root.iterdir()}, expected_entries)

    def test_missing_database_is_refused_without_creation(self):
        absent_db = self.root / "absent.sqlite"
        failed = subprocess.run(
            [sys.executable, os.fspath(SCRIPT), "query", "--db", os.fspath(absent_db), "--snapshot", "missing"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.assertEqual(failed.returncode, 2)
        self.assertIn("database does not exist", failed.stderr)
        self.assertFalse(absent_db.exists())

    def test_source_graph_ignores_decoys_and_keeps_ambiguous_or_shadowed_cases_unresolved(self):
        source = self.repo / "GraphFixture.cs"
        source.write_text(r'''namespace Demo;
interface IHandler<T> {}
class Query {}
class Box<TLeft, TRight> {}
class Handler : IHandler<Box<Query, string>> {}
[Route(@"api/customer")]
class FeedController(IHandler<Box<Query, string>> handler)
{
    [HttpGet("images/\u0061")]
    public void GetImages() { handler.Run(); }
    [HttpPost($"fake/{1}")]
    public void Interpolated() { handler.Fake(); }
    public void Decoys()
    {
        var one = "[HttpPost(\"fake\")] handler.Nope()";
        var two = @"handler.Nope()";
        var three = """handler.Nope()""";
        // [HttpPost("comment")] handler.Nope();
        /* handler.Nope(); */
    }
    public void Shadowed()
    {
        var handler = new Handler();
        handler.Hidden();
    }
}
class Setup
{
    void Configure(IServiceCollection services)
    {
        services.AddScoped<IHandler<Box<Query, string>>, Handler>();
        services.AddScoped<IHandler<Box<Query, string>>, Handler>();
    }
}
''', encoding="utf-8")
        git(self.repo, "add", "--", "GraphFixture.cs")

        saved = self.index()
        graph = self.graph(saved["snapshot_id"])
        route = next(fact for fact in graph["facts"] if fact["kind"] == "route_action" and fact["action_name"] == "GetImages")
        self.assertEqual(route["route_literal"], "api/customer/images/a")
        self.assertEqual(route["source"]["path"], "GraphFixture.cs")
        self.assertGreater(route["source"]["span"]["end_offset"], route["source"]["span"]["start_offset"])

        calls = [fact for fact in graph["facts"] if fact["kind"] == "receiver_invocation_syntax" and fact["source"]["path"] == "GraphFixture.cs"]
        self.assertEqual([fact["member_name"] for fact in calls], ["Run", "Fake", "Hidden"])
        self.assertFalse(any(fact.get("action_name") == "Interpolated" for fact in graph["facts"]))
        self.assertTrue(any(item["kind"] == "route_action" and "interpolated" in item["reason"] for item in graph["unresolved"]))
        self.assertTrue(any(item["kind"] == "receiver_invocation_syntax" and "shadow" in item["reason"] for item in graph["unresolved"]))
        self.assertFalse(any(link["kind"] == "invocation_uses_injection" for link in graph["links"]))
        injection = next(fact for fact in graph["facts"] if fact["kind"] == "constructor_injection" and fact["owner_type_id"].endswith("FeedController`0"))
        self.assertNotIn("resolved_type_id", injection)
        candidate = next(item for item in graph["candidates"] if item["subject_fact_id"] == injection["id"])
        self.assertFalse(candidate["traversable"])
        self.assertTrue(candidate["candidate_fact_ids"])
        self.assertTrue(any(item["kind"] == "type_binding_candidate" and item["fact_id"] == injection["id"] for item in graph["unresolved"]))
        self.assertEqual(graph["extractor_identity"], "csharp-lexical-facts-v7:python-stdlib-lexer")
        self.assertTrue(graph["limitations"])

    def test_ambiguous_namespace_type_identity_is_not_joined(self):
        source = self.repo / "Ambiguous.cs"
        source.write_text('''namespace Left { class Service {} }\nnamespace Right { class Service {} }\nnamespace Consumer { class Owner(Service service) {} }\n''', encoding="utf-8")
        git(self.repo, "add", "--", "Ambiguous.cs")
        saved = self.index()
        graph = self.graph(saved["snapshot_id"])
        owner = next(fact for fact in graph["facts"] if fact["kind"] == "constructor_injection" and fact["owner_type_id"] == "Consumer.Owner`0")
        self.assertNotIn("resolved_type_id", owner)
        candidates = next(item for item in graph["candidates"] if item["subject_fact_id"] == owner["id"])
        self.assertFalse(candidates["traversable"])

    def test_alias_interpolated_string_foreach_shadow_and_absolute_route_stay_unlinked(self):
        source = self.repo / "BoundaryCases.cs"
        source.write_text(r'''using Implementation = External.Implementation;
namespace Local { class Implementation {} }
namespace Demo;
interface IService {}
class Owner(IService service)
{
    [Route("api/demo")]
    class NestedController
    {
        [HttpGet("/absolute")]
        void Absolute() {}
    }
    void Run(System.Collections.Generic.IEnumerable<IService> others)
    {
        foreach (var service in others) { service.Ping(); }
        var text = $"{ "services.AddScoped<IService, Implementation>()" }";
    }
}
class Setup { void Configure() { services.AddScoped<IService, Implementation>(); } }
''', encoding="utf-8")
        git(self.repo, "add", "--", "BoundaryCases.cs")
        saved = self.index()
        graph = self.graph(saved["snapshot_id"])
        facts = graph["facts"]

        registration = next(f for f in facts if f["kind"] == "dependency_registration")
        self.assertNotIn("implementation_type_id", registration)
        self.assertFalse(any(link["kind"] == "registration_implements_type" and link["from_fact_id"] == registration["id"] for link in graph["links"]))
        self.assertTrue(any(item.get("fact_id") == registration["id"] and "alias" in item["reason"] for item in graph["unresolved"]))

        self.assertEqual(len([f for f in facts if f["kind"] == "dependency_registration"]), 1)
        self.assertTrue(any(f["kind"] == "receiver_invocation_syntax" and f["member_name"] == "Ping" for f in facts))
        self.assertTrue(any(item["kind"] == "receiver_invocation_syntax" and "shadow" in item["reason"] for item in graph["unresolved"]))

        absolute = next(f for f in facts if f["kind"] == "route_action" and f["action_name"] == "Absolute")
        self.assertEqual(absolute["route_literal"], "absolute")
        self.assertIsNone(absolute["controller_route_literal"])
        self.assertFalse(any("type_id" in fact and fact["kind"] in {"constructor_injection", "dependency_registration"} for fact in facts))
        self.assertFalse(any(link["kind"] in {"registration_implements_type", "injection_resolved_by_registration"} for link in graph["links"]))

    def test_typed_lambda_receiver_spelling_is_nontraversable_candidate(self):
        source = self.repo / "LambdaReceiver.cs"
        source.write_text('''namespace Demo;
interface IService {}
class Owner(IService service)
{
    void Run() { values.Select((IService service) => service.Ping()); }
}
''', encoding="utf-8")
        git(self.repo, "add", "--", "LambdaReceiver.cs")
        saved = self.index()
        graph = self.graph(saved["snapshot_id"])
        injection = next(f for f in graph["facts"] if f["kind"] == "constructor_injection" and f["parameter_name"] == "service")
        invocation = next(f for f in graph["facts"] if f["kind"] == "receiver_invocation_syntax" and f["member_name"] == "Ping")
        self.assertNotIn("injection_fact_id", invocation)
        self.assertFalse(any(link["kind"] == "invocation_uses_injection" for link in graph["links"]))
        candidate = next(c for c in graph["candidates"] if c["subject_fact_id"] == invocation["id"])
        self.assertFalse(candidate["traversable"])
        self.assertIn(injection["id"], candidate["candidate_fact_ids"])
        self.assertTrue(any(u["kind"] == "receiver_invocation_syntax" and u["fact_id"] == invocation["id"] for u in graph["unresolved"]))

    def test_using_alias_on_constructor_injection_does_not_resolve_to_local_same_name(self):
        source = self.repo / "InjectionAlias.cs"
        source.write_text('''using Service = External.Service;
namespace Local { class Service {} }
namespace Demo { class Owner(Service service) { void Run() { service.Ping(); } } class Setup { void Configure() { services.AddScoped<Local.Service, Local.Service>(); } } }
''', encoding="utf-8")
        git(self.repo, "add", "--", "InjectionAlias.cs")
        saved = self.index()
        graph = self.graph(saved["snapshot_id"])
        injection = next(f for f in graph["facts"] if f["kind"] == "constructor_injection" and f["owner_type_id"] == "Demo.Owner`0")
        self.assertNotIn("resolved_type_id", injection)
        self.assertTrue(any(item["subject_fact_id"] == injection["id"] for item in graph["candidates"]))
        self.assertFalse(any(link["kind"] == "injection_resolved_by_registration" and link["from_fact_id"] == injection["id"] for link in graph["links"]))

    def test_unimported_namespace_type_is_only_a_nontraversable_candidate(self):
        source = self.repo / "NamespaceScope.cs"
        source.write_text('''using Imported;
using External;
namespace Local { class Service {} }
namespace Imported { class ImportedService {} }
namespace Consumer { class InScope {} class Owner(Service missing, InScope local, ImportedService imported) {} class Setup { void Configure() { services.AddScoped<InScope, InScope>(); services.AddScoped<ImportedService, ImportedService>(); } } }
''', encoding="utf-8")
        git(self.repo, "add", "--", "NamespaceScope.cs")
        saved = self.index()
        graph = self.graph(saved["snapshot_id"])
        injections = {f["parameter_name"]: f for f in graph["facts"] if f["kind"] == "constructor_injection" and f["owner_type_id"] == "Consumer.Owner`0"}
        self.assertNotIn("resolved_type_id", injections["missing"])
        self.assertTrue({item["subject_fact_id"] for item in graph["candidates"]} >= {fact["id"] for fact in injections.values()})
        self.assertTrue(all(item["traversable"] is False for item in graph["candidates"]))
        self.assertFalse(any(link["kind"] == "injection_resolved_by_registration" and link["from_fact_id"] == injections["missing"]["id"] for link in graph["links"]))

    def test_multiline_raw_route_literal_is_unresolved(self):
        source = self.repo / "RawRoute.cs"
        source.write_text('''namespace Demo;
[Route("""
    api/demo
    """)]
class Controller { [HttpGet] void Get() {} }
''', encoding="utf-8")
        git(self.repo, "add", "--", "RawRoute.cs")
        saved = self.index()
        graph = self.graph(saved["snapshot_id"])
        self.assertFalse(any(f["kind"] == "route_action" and f["source"]["path"] == "RawRoute.cs" for f in graph["facts"]))
        self.assertTrue(any(item["kind"] == "controller_route" and "multiline raw" in item["reason"] for item in graph["unresolved"]))
        self.assertTrue(any(item["kind"] == "route_action" and "suppressed" in item["reason"] for item in graph["unresolved"]))

    def test_reviewed_flow_overlay_round_trip_and_rejects_stale_or_mismatched_evidence(self):
        source = self.repo / "Overlay.cs"
        source.write_text('''namespace Demo; [Route("api/demo")] class Controller { [HttpGet("items")] void Get() {} }
''', encoding="utf-8")
        git(self.repo, "add", "--", "Overlay.cs")
        saved = self.index()
        graph = self.graph(saved["snapshot_id"])
        route = next(fact for fact in graph["facts"] if fact["kind"] == "route_action")
        overlay = {
            "overlay_schema_version": 1,
            "snapshot_id": saved["snapshot_id"],
            "extractor_identity": graph["extractor_identity"],
            "title": "Reviewed demo browsing flow",
            "reviewed_conclusions": [{
                "claim": "The cited action serves the route recorded in this reviewed flow.",
                "evidence": [{"fact_id": route["id"], "source": route["source"]}],
            }],
        }
        overlay_path = self.root / "flow.json"

        def write_overlay(value):
            overlay_path.write_text(json.dumps(value), encoding="utf-8")

        write_overlay(overlay)
        attached = json.loads(self.cli("flow-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(overlay_path)).stdout)
        overlay_id = attached["overlay_id"]
        reopened = json.loads(self.cli("flow-query", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--overlay", overlay_id).stdout)
        self.assertEqual(reopened["overlay"]["title"], overlay["title"])
        self.assertEqual(reopened["overlay"]["content_hash"], overlay_id)
        self.assertEqual(reopened["review_status"], "unreviewed")
        self.assertIn("not mechanically validated", reopened["validation"])
        self.cli("focus", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo), "--snapshot", saved["snapshot_id"], "--overlay", overlay_id, "--max-tokens", "10000", expect=2)

        receipt = {
            "receipt_schema_version": 1,
            "snapshot_id": saved["snapshot_id"],
            "overlay_id": overlay_id,
            "overlay_content_hash": attached["content_hash"],
            "extractor_identity": graph["extractor_identity"],
            "reviewer_identity": "independent review",
            "reviewer_model": "GPT-6.1 Sol High",
            "decision": "accepted",
            "reviewed_at": "2026-10-06T12:00:00Z",
            "review_basis": "All five reviewed conclusions are supported by the cited spans; the distributed cache wording does not claim durable shared storage.",
        }
        receipt_path = self.root / "review.json"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        receipt_result = json.loads(self.cli("flow-review", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--overlay", overlay_id, "--input", os.fspath(receipt_path)).stdout)
        accepted = json.loads(self.cli("flow-query", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--overlay", overlay_id).stdout)
        self.assertEqual(accepted["review_status"], "accepted")
        self.assertEqual(accepted["review_receipt"]["receipt_hash"], receipt_result["receipt_hash"])
        large = self.cli("focus", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo), "--snapshot", saved["snapshot_id"], "--overlay", overlay_id, "--max-tokens", "5000")
        large_json = json.loads(large.stdout)
        exact_size = large_json["budget"]["stdout_bytes_including_newline"]
        self.assertEqual(len(large.stdout.encode("ascii")), exact_size)
        exact = self.cli("focus", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo), "--snapshot", saved["snapshot_id"], "--overlay", overlay_id, "--max-tokens", str(exact_size))
        self.assertEqual(len(exact.stdout.encode("ascii")), exact_size)
        one_short = self.cli("focus", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo), "--snapshot", saved["snapshot_id"], "--overlay", overlay_id, "--max-tokens", str(exact_size - 1))
        short_json = json.loads(one_short.stdout)
        self.assertLessEqual(len(one_short.stdout.encode("ascii")), exact_size - 1)
        self.assertEqual(short_json["claim_selection"]["omitted_claims"], 1)
        repeated_short = self.cli("focus", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo), "--snapshot", saved["snapshot_id"], "--overlay", overlay_id, "--max-tokens", str(exact_size - 1))
        repeated_json = json.loads(repeated_short.stdout)
        self.assertEqual(repeated_json["claims"], short_json["claims"])
        self.assertEqual(repeated_json["claim_selection"], short_json["claim_selection"])
        replaced_receipt = dict(receipt, decision="rejected", review_basis="Attempted conflicting receipt.")
        receipt_path.write_text(json.dumps(replaced_receipt), encoding="utf-8")
        self.cli("flow-review", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--overlay", overlay_id, "--input", os.fspath(receipt_path), expect=2)
        still_accepted = json.loads(self.cli("flow-query", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--overlay", overlay_id).stdout)
        self.assertEqual(still_accepted["review_status"], "accepted")

        stale = dict(overlay, snapshot_id="atlas-v2-stale")
        write_overlay(stale)
        self.cli("flow-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(overlay_path), expect=2)
        unknown_fact = json.loads(json.dumps(overlay))
        unknown_fact["reviewed_conclusions"][0]["evidence"][0]["fact_id"] = "missing-fact"
        write_overlay(unknown_fact)
        self.cli("flow-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(overlay_path), expect=2)
        wrong_extractor = dict(overlay, extractor_identity="different-extractor")
        write_overlay(wrong_extractor)
        self.cli("flow-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(overlay_path), expect=2)
        wrong_source = json.loads(json.dumps(overlay))
        wrong_source["reviewed_conclusions"][0]["evidence"][0]["source"]["sha256"] = "0" * 64
        write_overlay(wrong_source)
        self.cli("flow-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(overlay_path), expect=2)

        changed_claim = json.loads(json.dumps(overlay))
        changed_claim["reviewed_conclusions"][0]["claim"] += " Revised wording."
        write_overlay(changed_claim)
        changed = json.loads(self.cli("flow-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(overlay_path)).stdout)
        changed_status = json.loads(self.cli("flow-query", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--overlay", changed["overlay_id"]).stdout)
        self.assertNotEqual(changed["overlay_id"], overlay_id)
        self.assertEqual(changed_status["review_status"], "unreviewed")

        mismatch = dict(receipt, overlay_id=changed["overlay_id"])
        receipt_path.write_text(json.dumps(mismatch), encoding="utf-8")
        self.cli("flow-review", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--overlay", changed["overlay_id"], "--input", os.fspath(receipt_path), expect=2)
        rejected = dict(receipt, overlay_id=changed["overlay_id"], overlay_content_hash=changed["content_hash"], decision="rejected", review_basis="Changed claim wording has not received semantic review.")
        receipt_path.write_text(json.dumps(rejected), encoding="utf-8")
        self.cli("flow-review", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--overlay", changed["overlay_id"], "--input", os.fspath(receipt_path))
        rejected_status = json.loads(self.cli("flow-query", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--overlay", changed["overlay_id"]).stdout)
        self.assertEqual(rejected_status["review_status"], "rejected")
        self.cli("focus", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo), "--snapshot", saved["snapshot_id"], "--overlay", changed["overlay_id"], "--max-tokens", "10000", expect=2)

    def test_focus_refuses_same_status_different_bytes_and_missing_source(self):
        source = self.repo / "Tracked.cs"
        source.write_text("namespace Demo; class Widget {}\n", encoding="utf-8")
        git(self.repo, "add", "--", "Tracked.cs")
        saved = self.index()
        graph = self.graph(saved["snapshot_id"])
        fact = next(f for f in graph["facts"] if f["kind"] == "type_declaration" and f["source"]["path"] == "Tracked.cs")
        overlay = {
            "overlay_schema_version": 1,
            "snapshot_id": saved["snapshot_id"],
            "extractor_identity": graph["extractor_identity"],
            "title": "Fixture reviewed flow",
            "reviewed_conclusions": [{"claim": "The fixture declares Widget.", "evidence": [{"fact_id": fact["id"], "source": fact["source"]}]}],
        }
        overlay_path = self.root / "focus-flow.json"
        overlay_path.write_text(json.dumps(overlay), encoding="utf-8")
        attached = json.loads(self.cli("flow-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(overlay_path)).stdout)
        receipt = {
            "receipt_schema_version": 1, "snapshot_id": saved["snapshot_id"],
            "overlay_id": attached["overlay_id"], "overlay_content_hash": attached["content_hash"],
            "extractor_identity": graph["extractor_identity"], "reviewer_identity": "reviewer",
            "reviewer_model": "test model", "decision": "accepted",
            "reviewed_at": "2026-10-06T12:00:00Z", "review_basis": "Fixture evidence reviewed.",
        }
        receipt_path = self.root / "focus-review.json"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        self.cli("flow-review", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--overlay", attached["overlay_id"], "--input", os.fspath(receipt_path))

        source.write_text("namespace Demo; class Widget { int Value => 1; }\n", encoding="utf-8")
        first = self.cli("focus", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo), "--snapshot", saved["snapshot_id"], "--overlay", attached["overlay_id"], "--max-tokens", "10000", expect=3)
        first_json = json.loads(first.stdout)
        first_status = first_json["freshness"]["structured_status"]
        first_head = first_json["freshness"]["head"]
        self.assertEqual(first_json["result"], "stale_refused")
        self.assertEqual(first_json["claims"], [])
        self.assertEqual(first_json["freshness"]["changed_paths"], ["Tracked.cs"])
        stale_size = len(first.stdout.encode("ascii"))
        self.assertEqual(first_json["budget"]["stdout_bytes_including_newline"], stale_size)
        exact_stale = self.cli(
            "focus", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
            "--snapshot", saved["snapshot_id"], "--overlay", attached["overlay_id"],
            "--max-tokens", str(stale_size), expect=3,
        )
        self.assertEqual(len(exact_stale.stdout.encode("ascii")), stale_size)
        short_stale = self.cli(
            "focus", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
            "--snapshot", saved["snapshot_id"], "--overlay", attached["overlay_id"],
            "--max-tokens", str(stale_size - 1), expect=2,
        )
        self.assertEqual(short_stale.stdout, "")
        self.assertIn(f"requires {stale_size} ASCII stdout bytes", short_stale.stderr)
        self.assertIn("diagnostic and claims withheld", short_stale.stderr)

        source.write_text("namespace Demo; class Widget { string? Name; }\n", encoding="utf-8")
        second = self.cli("focus", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo), "--snapshot", saved["snapshot_id"], "--overlay", attached["overlay_id"], "--max-tokens", "10000", expect=3)
        second_json = json.loads(second.stdout)
        self.assertEqual(second_json["freshness"]["head"], first_head)
        self.assertEqual(second_json["freshness"]["structured_status"], first_status)
        self.assertEqual(second_json["freshness"]["changed_paths"], ["Tracked.cs"])
        self.assertTrue(any("content hash changed" in reason for reason in second_json["freshness"]["reasons"]))

        source.unlink()
        missing = self.cli("focus", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo), "--snapshot", saved["snapshot_id"], "--overlay", attached["overlay_id"], "--max-tokens", "10000", expect=3)
        missing_json = json.loads(missing.stdout)
        self.assertEqual(missing_json["claims"], [])
        self.assertEqual(missing_json["freshness"]["changed_paths"], ["Tracked.cs"])

    def test_answer_check_binds_complete_fresh_packet_and_preserves_exact_accepted_draft(self):
        source = self.repo / "Answer.cs"
        source.write_text('namespace Demo; class Widget { bool Success; int MatchedCount; }\n', encoding="utf-8")
        git(self.repo, "add", "--", "Answer.cs")
        saved = self.index()
        graph = self.graph(saved["snapshot_id"])
        fact = next(item for item in graph["facts"] if item["kind"] == "type_declaration" and item["source"]["path"] == "Answer.cs")
        overlay = {
            "overlay_schema_version": 1,
            "snapshot_id": saved["snapshot_id"],
            "extractor_identity": graph["extractor_identity"],
            "title": "Answer fixture map",
            "reviewed_conclusions": [
                {"claim": "The response has success = false and matched_count = 0.", "evidence": [{"fact_id": fact["id"], "source": fact["source"]}]},
                {"claim": "The controller is declared as a C# class.", "evidence": [{"fact_id": fact["id"], "source": fact["source"]}]},
            ],
        }
        overlay_file = self.root / "answer-flow.json"
        overlay_file.write_text(json.dumps(overlay), encoding="utf-8")
        attached = json.loads(self.cli("flow-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(overlay_file)).stdout)
        review_receipt = {
            "receipt_schema_version": 1, "snapshot_id": saved["snapshot_id"],
            "overlay_id": attached["overlay_id"], "overlay_content_hash": attached["content_hash"],
            "extractor_identity": graph["extractor_identity"], "reviewer_identity": "independent reviewer",
            "reviewer_model": "GPT-6.1 Sol High", "decision": "accepted",
            "reviewed_at": "2026-10-06T12:00:00Z", "review_basis": "The source spans support both map claims.",
        }
        receipt_file = self.root / "answer-flow-review.json"
        receipt_file.write_text(json.dumps(review_receipt), encoding="utf-8")
        self.cli("flow-review", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--overlay", attached["overlay_id"], "--input", os.fspath(receipt_file))
        question_file = self.root / "question.txt"
        draft_file = self.root / "draft.txt"
        question_file.write_bytes("What does selfie upload return?\n".encode())
        draft_bytes = "It returns success=false, matched_count=0, history, and no new rows.\n".encode()
        draft_file.write_bytes(draft_bytes)

        args = ("answer-check", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo), "--snapshot", saved["snapshot_id"], "--overlay", attached["overlay_id"], "--question-file", os.fspath(question_file), "--draft-file", os.fspath(draft_file))
        prepared = self.cli(*args)
        packet = json.loads(prepared.stdout)
        self.assertEqual(packet["result"], "semantic_review_required")
        self.assertEqual(packet["question"], question_file.read_text())
        self.assertEqual(packet["draft"], draft_file.read_text())
        self.assertEqual([claim["claim_number"] for claim in packet["claims"]], [1, 2])
        self.assertEqual(packet["binding"]["overlay_content_hash"], attached["content_hash"])
        self.assertEqual(packet["binding"]["question_sha256"], hashlib.sha256(question_file.read_bytes()).hexdigest())
        packet_hash = hashlib.sha256(prepared.stdout.encode("ascii")).hexdigest()

        review_file = self.root / "answer-review.json"
        review = {
            "packet_sha256": packet_hash,
            "decision": "accepted",
            "reviewer_identity": "sol-high-review-session",
            "reviewer_model": "GPT-6.1 Sol High",
            "claim_reviews": [
                {"claim_number": 1, "disposition": "covered", "basis": "Both response fields are relevant to the question and appear with their exact values."},
                {"claim_number": 2, "disposition": "not_relevant", "basis": "The C# declaration form does not answer what the upload operation returns."},
            ],
        }
        review_file.write_text(json.dumps(review), encoding="utf-8")
        accepted = self.cli(*args, "--review", os.fspath(review_file))
        self.assertEqual(accepted.stdout.encode(), draft_bytes)

        bare = json.loads(json.dumps(review))
        bare["claim_reviews"][0]["basis"] = "used"
        review_file.write_text(json.dumps(bare), encoding="utf-8")
        self.cli(*args, "--review", os.fspath(review_file), expect=2)
        invalid_disposition = json.loads(json.dumps(review))
        invalid_disposition["claim_reviews"][0]["disposition"] = "supported"
        review_file.write_text(json.dumps(invalid_disposition), encoding="utf-8")
        self.cli(*args, "--review", os.fspath(review_file), expect=2)
        duplicate_claim = json.loads(json.dumps(review))
        duplicate_claim["claim_reviews"][1]["claim_number"] = 1
        review_file.write_text(json.dumps(duplicate_claim), encoding="utf-8")
        self.cli(*args, "--review", os.fspath(review_file), expect=2)
        missing_identity = json.loads(json.dumps(review))
        del missing_identity["reviewer_model"]
        review_file.write_text(json.dumps(missing_identity), encoding="utf-8")
        self.cli(*args, "--review", os.fspath(review_file), expect=2)
        changed = dict(review, packet_sha256="0" * 64)
        review_file.write_text(json.dumps(changed), encoding="utf-8")
        self.cli(*args, "--review", os.fspath(review_file), expect=2)

    def test_answer_check_refuses_unaccepted_or_stale_focus(self):
        source = self.repo / "Answer.cs"
        source.write_text("namespace Demo; class Widget {}\n", encoding="utf-8")
        git(self.repo, "add", "--", "Answer.cs")
        saved = self.index()
        graph = self.graph(saved["snapshot_id"])
        fact = next(item for item in graph["facts"] if item["kind"] == "type_declaration" and item["source"]["path"] == "Answer.cs")
        overlay = {"overlay_schema_version": 1, "snapshot_id": saved["snapshot_id"], "extractor_identity": graph["extractor_identity"], "title": "Map", "reviewed_conclusions": [{"claim": "Widget exists.", "evidence": [{"fact_id": fact["id"], "source": fact["source"]}]}]}
        overlay_file = self.root / "unaccepted-flow.json"
        overlay_file.write_text(json.dumps(overlay), encoding="utf-8")
        attached = json.loads(self.cli("flow-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(overlay_file)).stdout)
        question_file, draft_file = self.root / "q.txt", self.root / "d.txt"
        question_file.write_text("What exists?")
        draft_file.write_text("Widget exists.")
        args = ("answer-check", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo), "--snapshot", saved["snapshot_id"], "--overlay", attached["overlay_id"], "--question-file", os.fspath(question_file), "--draft-file", os.fspath(draft_file))
        self.cli(*args, expect=2)

        receipt = {"receipt_schema_version": 1, "snapshot_id": saved["snapshot_id"], "overlay_id": attached["overlay_id"], "overlay_content_hash": attached["content_hash"], "extractor_identity": graph["extractor_identity"], "reviewer_identity": "reviewer", "reviewer_model": "test", "decision": "accepted", "reviewed_at": "2026-10-06T12:00:00Z", "review_basis": "Widget claim checked against source."}
        receipt_file = self.root / "review.json"
        receipt_file.write_text(json.dumps(receipt), encoding="utf-8")
        self.cli("flow-review", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--overlay", attached["overlay_id"], "--input", os.fspath(receipt_file))
        source.write_text("namespace Demo; class Widget { int Value; }\n", encoding="utf-8")
        self.cli(*args, expect=2)

    def test_answer_check_refuses_incomplete_focus(self):
        spec = importlib.util.spec_from_file_location("atlas_answer_check_test", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        incomplete = {"result": "fresh", "claim_selection": {"included_claims": 1, "total_claims": 2, "omitted_claims": 1}, "claims": []}
        with mock.patch.object(module, "focus", return_value=(incomplete, b"{}\n", 0)):
            with self.assertRaisesRegex(module.AtlasError, "requires every reviewed claim"):
                module.answer_check("unused", "unused", "snapshot", "overlay", "unused", "unused", None)


if __name__ == "__main__":
    unittest.main()
