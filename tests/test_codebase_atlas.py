import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


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


if __name__ == "__main__":
    unittest.main()
