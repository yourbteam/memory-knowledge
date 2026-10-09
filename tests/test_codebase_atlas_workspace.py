"""Tests for the durable Atlas operator entry point and workspace contract.

Synthetic review records in this module test only the mechanics of the existing
review boundary. They are not Sol decisions or evidence of semantic acceptance.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "skills/codebase-atlas-machinery/scripts"
sys.path.insert(0, str(SCRIPT_DIR))
LAUNCHER_SPEC = importlib.util.spec_from_file_location(
    "atlas_workspace_launcher_test_module", SCRIPT_DIR / "atlas_launch.py"
)
LAUNCHER = importlib.util.module_from_spec(LAUNCHER_SPEC)
assert LAUNCHER_SPEC.loader is not None
LAUNCHER_SPEC.loader.exec_module(LAUNCHER)
WORKSPACE = LAUNCHER.workspace


class AtlasWorkspaceLauncherTests(unittest.TestCase):
    def run_launcher(self, answers: list[str], *, dotnet: str = "/sdk/dotnet"):
        output = io.StringIO()
        error = io.StringIO()
        with (mock.patch("builtins.input", side_effect=answers),
              mock.patch.dict("os.environ", {"ATLAS_DOTNET": dotnet}),
              contextlib.redirect_stdout(output), contextlib.redirect_stderr(error)):
            code = LAUNCHER.main()
        return code, output.getvalue(), error.getvalue()

    @staticmethod
    def result_json(output: str):
        return json.loads(output[output.index("{"):])

    def test_prepare_choice_forwards_exact_nonsecret_inputs(self):
        expected = {"result": "prepared", "snapshot_id": "fixture-snapshot"}
        inputs = ["1", "/private/tmp/state", "/private/tmp/repo", "src/Api.csproj",
                  "net8.0", "Demo.IStorage", "/private/tmp/seed.sqlite"]
        with mock.patch.object(LAUNCHER.workspace, "prepare", return_value=expected) as prepare:
            code, output, error = self.run_launcher(inputs)
        self.assertEqual(code, 0, error)
        prepare.assert_called_once_with("/private/tmp/repo", "/private/tmp/state", "src/Api.csproj",
                                        "net8.0", "Demo.IStorage", "/sdk/dotnet",
                                        "/private/tmp/seed.sqlite")
        self.assertEqual(self.result_json(output), expected)

    def test_status_and_publish_choices_dispatch_without_other_workspace_actions(self):
        status_result = {"result": "status", "pending_route_reviews": 1}
        with mock.patch.object(LAUNCHER.workspace, "status", return_value=status_result) as status, \
                mock.patch.object(LAUNCHER.workspace, "prepare") as prepare, \
                mock.patch.object(LAUNCHER.workspace, "publish") as publish, \
                mock.patch.object(LAUNCHER.workspace, "correct") as correct, \
                mock.patch.object(LAUNCHER.workspace, "publish_reviews", create=True) as publish_reviews:
            code, output, error = self.run_launcher(["2", "/private/tmp/state"])
        self.assertEqual(code, 0, error)
        status.assert_called_once_with("/private/tmp/state")
        prepare.assert_not_called()
        publish.assert_not_called()
        correct.assert_not_called()
        publish_reviews.assert_not_called()
        self.assertEqual(self.result_json(output), status_result)

        publish_result = {"result": "published", "route_fact_id": "route-fixture"}
        with mock.patch.object(LAUNCHER.workspace, "status") as status, \
                mock.patch.object(LAUNCHER.workspace, "prepare") as prepare, \
                mock.patch.object(LAUNCHER.workspace, "publish", return_value=publish_result) as publish, \
                mock.patch.object(LAUNCHER.workspace, "correct") as correct, \
                mock.patch.object(LAUNCHER.workspace, "publish_reviews", create=True) as publish_reviews:
            code, output, error = self.run_launcher(
                ["3", "/private/tmp/state", "route-fixture", "/private/tmp/review.json"]
            )
        self.assertEqual(code, 0, error)
        publish.assert_called_once_with("/private/tmp/state", "route-fixture", "/private/tmp/review.json")
        status.assert_not_called()
        prepare.assert_not_called()
        correct.assert_not_called()
        publish_reviews.assert_not_called()
        self.assertEqual(self.result_json(output), publish_result)

        correction_result = {"result": "correction-prepared", "route_fact_id": "route-fixture"}
        with mock.patch.object(LAUNCHER.workspace, "correct", return_value=correction_result) as correct, \
                mock.patch.object(LAUNCHER.workspace, "status") as status, \
                mock.patch.object(LAUNCHER.workspace, "prepare") as prepare, \
                mock.patch.object(LAUNCHER.workspace, "publish") as publish, \
                mock.patch.object(LAUNCHER.workspace, "publish_reviews", create=True) as publish_reviews:
            code, output, error = self.run_launcher(
                ["4", "/private/tmp/state", "route-fixture", "/private/tmp/correction.json"]
            )
        self.assertEqual(code, 0, error)
        correct.assert_called_once_with("/private/tmp/state", "route-fixture", "/private/tmp/correction.json")
        status.assert_not_called()
        prepare.assert_not_called()
        publish.assert_not_called()
        publish_reviews.assert_not_called()
        self.assertEqual(self.result_json(output), correction_result)

        batch_result = {"result": "published", "outcomes": [{"route_fact_id": "route-fixture"}]}
        with mock.patch.object(LAUNCHER.workspace, "publish_reviews", return_value=batch_result, create=True) as publish_reviews, \
                mock.patch.object(LAUNCHER.workspace, "status") as status, \
                mock.patch.object(LAUNCHER.workspace, "prepare") as prepare, \
                mock.patch.object(LAUNCHER.workspace, "publish") as publish, \
                mock.patch.object(LAUNCHER.workspace, "correct") as correct:
            code, output, error = self.run_launcher(["5", "/private/tmp/state", "/private/tmp/reviews"])
        self.assertEqual(code, 0, error)
        publish_reviews.assert_called_once_with("/private/tmp/state", "/private/tmp/reviews")
        status.assert_not_called()
        prepare.assert_not_called()
        publish.assert_not_called()
        correct.assert_not_called()
        self.assertEqual(self.result_json(output), batch_result)

    def test_invalid_menu_choice_stops_before_workspace_dispatch(self):
        with mock.patch.object(LAUNCHER.workspace, "status") as status, \
                mock.patch.object(LAUNCHER.workspace, "prepare") as prepare, \
                mock.patch.object(LAUNCHER.workspace, "publish") as publish, \
                mock.patch.object(LAUNCHER.workspace, "correct") as correct, \
                mock.patch.object(LAUNCHER.workspace, "publish_reviews", create=True) as publish_reviews:
            code, output, error = self.run_launcher(["9"])
        self.assertEqual(code, 2)
        self.assertEqual(output.splitlines()[-5:], [
            "1. Prepare or resume workspace",
            "2. Read workspace status",
            "3. Publish an independently reviewed route map",
            "4. Correct a rejected map",
            "5. Publish a review directory",
        ])
        self.assertIn("choose one listed option: 1, 2, 3, 4, or 5", error)
        status.assert_not_called()
        prepare.assert_not_called()
        publish.assert_not_called()
        correct.assert_not_called()
        publish_reviews.assert_not_called()


class AtlasWorkspaceReadOnlyContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir="/private/tmp/atlas-durable-integration-20261009")
        self.root = Path(self.temp.name)
        self.state = self.root / "state"
        self.state.mkdir()
        self.database = self.state / "atlas.sqlite"
        with sqlite3.connect(self.database):
            pass
        self.manifest_path = self.state / "workspace.json"
        self.manifest = {
            "schema_version": 1,
            "inputs": {"repository_root": "/private/tmp/fixture-repository"},
            "database_path": str(self.database),
            "snapshot_id": "snapshot-fixture",
            "extractor_identity": "fixture-extractor",
            "compiler_supplement_sha256": "a" * 64,
            "runtime_profiles": {},
            "historical": {},
            "routes": [],
            "producer_identity": WORKSPACE._producer_identity(),
        }
        self.save_manifest()

    def tearDown(self):
        self.temp.cleanup()

    def save_manifest(self):
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")

    def state_bytes(self):
        return {path.relative_to(self.state).as_posix(): path.read_bytes()
                for path in sorted(self.state.rglob("*")) if path.is_file()}

    def test_status_refuses_noncanonical_manifest_and_stale_producer_without_writing(self):
        self.manifest["unrecognized"] = "must not be ignored"
        self.save_manifest()
        before = self.state_bytes()
        with self.assertRaisesRegex(WORKSPACE.WorkspaceError, "noncanonical schema"):
            WORKSPACE.status(str(self.state))
        self.assertEqual(self.state_bytes(), before)

        self.manifest.pop("unrecognized")
        self.manifest["producer_identity"] = {"atlas_sha256": "0" * 64}
        self.save_manifest()
        before = self.state_bytes()
        with self.assertRaisesRegex(WORKSPACE.WorkspaceError, "producer files changed"):
            WORKSPACE.status(str(self.state))
        self.assertEqual(self.state_bytes(), before)

    def test_prepare_rejects_state_inside_checkout_before_creating_artifacts(self):
        repo = self.root / "repo"
        repo.mkdir()
        (repo / ".git").mkdir()
        state = repo / ".atlas-state"
        with self.assertRaisesRegex(WORKSPACE.WorkspaceError, "outside the target repository"):
            WORKSPACE.prepare(str(repo), str(state), "Api.csproj", "net8.0", "Demo.IStorage", "/sdk/dotnet")
        self.assertFalse(state.exists())

    def test_status_rejects_symlinked_state_ancestor_before_reading(self):
        alias = self.root / "state-alias"
        alias.symlink_to(self.state, target_is_directory=True)
        with self.assertRaisesRegex(WORKSPACE.WorkspaceError, "symbolic link"):
            WORKSPACE.status(str(alias))
        self.assertEqual(self.state_bytes()["workspace.json"], self.manifest_path.read_bytes())


class AtlasWorkspaceProducerStabilityTests(unittest.TestCase):
    def test_prepare_does_not_publish_manifest_if_producer_identity_changes(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp/atlas-durable-integration-20261009") as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            (repo / ".git").mkdir()
            (repo / "Api.csproj").write_text("<Project />\n", encoding="utf-8")
            state = root / "state"

            snapshot = {"snapshot_id": "snapshot-stability", "source_graph": {
                "extractor_identity": "fixture-extractor"}}
            compiler_hash = "a" * 64
            compiler_supplement = {"binding": {"project_path": "Api.csproj", "target_framework": "net8.0"},
                                   "content_sha256": compiler_hash}
            runtime_observations = [
                {"binding": {"project_path": "Api.csproj", "interface_type": "Demo.IStorage",
                             "profile": "local-storage", "candidate_type": "Demo.LocalStorage"},
                 "capture": {"observed_runtime_type": "Demo.LocalStorage"}, "input_sha256": "b" * 64},
                {"binding": {"project_path": "Api.csproj", "interface_type": "Demo.IStorage",
                             "profile": "cloud-storage", "candidate_type": "Demo.CloudStorage"},
                 "capture": {"observed_runtime_type": "Demo.CloudStorage"}, "input_sha256": "c" * 64},
            ]

            def fake_command(args, *, dotnet=None):
                if args[0] == "index":
                    return {"snapshot_id": "snapshot-stability", "extractor_identity": "fixture-extractor"}
                if args[0] == "compiler-index":
                    return {"content_sha256": compiler_hash}
                if args[0] == "runtime-index":
                    return {"observations": [{"profile": "local-storage"}, {"profile": "cloud-storage"}]}
                self.fail(f"unexpected Atlas command in bounded producer-race test: {args[0]}")

            original_identity = {"atlas_sha256": "1" * 64, "workspace_sha256": "2" * 64,
                                "route_coordinator_sha256": "3" * 64, "launcher_sha256": "4" * 64}
            changed_identity = {**original_identity, "workspace_sha256": "5" * 64}
            atlas_module = importlib.import_module("atlas")
            with (mock.patch.object(WORKSPACE, "_producer_identity",
                                    side_effect=[original_identity, changed_identity]),
                  mock.patch.object(WORKSPACE, "_command", side_effect=fake_command),
                  mock.patch.object(atlas_module, "_current_route_snapshot",
                                    return_value=(snapshot, [snapshot], "fixture-extractor",
                                                  {"repository_root": os.fspath(repo)})),
                  mock.patch.object(atlas_module, "_current_compiler_supplements",
                                    return_value=[compiler_supplement]),
                  mock.patch.object(atlas_module, "_current_runtime_observations",
                                    return_value=runtime_observations),
                  mock.patch.object(WORKSPACE, "_historical_routes_from_database", return_value=([], {}))):
                with self.assertRaisesRegex(WORKSPACE.WorkspaceError,
                                            "producer files changed during prepare; partial artifacts were preserved"):
                    WORKSPACE.prepare(os.fspath(repo), os.fspath(state), "Api.csproj", "net8.0",
                                      "Demo.IStorage", sys.executable)

            self.assertFalse((state / "workspace.json").exists())
            self.assertTrue((state / "workspace-initializing.json").is_file())
            self.assertTrue((state / "atlas.sqlite").is_file())
            self.assertEqual((state / ".gitignore").read_text(encoding="utf-8"), "*\n")
            initializing = json.loads((state / "workspace-initializing.json").read_text(encoding="utf-8"))
            self.assertEqual(initializing["schema_version"], 1)
            self.assertEqual(initializing["inputs"]["repository_root"], os.fspath(repo))

@unittest.skipUnless(os.environ.get("ATLAS_DOTNET"), "workspace integration fixture requires the approved local dotnet SDK")
class AtlasWorkspaceRealHostTests(unittest.TestCase):
    """Exercise workspace preparation on a disposable, framework-only application host."""

    def attach_synthetic_seed_map(self, database: Path, repo: Path) -> tuple[str, str, str, str, str]:
        """Create a mechanics-only accepted origin map with one citation outside route evidence."""
        indexed = WORKSPACE._command(["index", "--repo", os.fspath(repo), "--db", os.fspath(database)])
        snapshot_id = indexed["snapshot_id"]
        graph = WORKSPACE._command(["query", "--db", os.fspath(database),
                                    "--snapshot", snapshot_id, "--graph"])["source_graph"]
        route = next(item for item in graph["facts"] if item.get("kind") == "route_action"
                     and item.get("route_literal") == "api/workspace/read")
        context_route = next(item for item in graph["facts"] if item.get("kind") == "route_action"
                             and item.get("route_literal") == "api/workspace/context")
        historical = next(item for item in graph["facts"] if item.get("kind") == "type_declaration"
                          and item.get("type_id") == "Fixture.HistoricalNote`0")
        flow = {
            "overlay_schema_version": 1,
            "snapshot_id": snapshot_id,
            "extractor_identity": graph["extractor_identity"],
            "title": "Synthetic prior map for workspace mechanics",
            "reviewed_conclusions": [
                {"claim": "The selected route reads through the asset storage handler.",
                 "evidence": [{"fact_id": route["id"], "source": route["source"]}]},
                {"claim": "The synthetic prior map also cites the sibling route and historical note.",
                 "evidence": [{"fact_id": context_route["id"], "source": context_route["source"]},
                              {"fact_id": historical["id"], "source": historical["source"]}]},
            ],
        }
        flow_path = repo.parent / "synthetic-origin-flow.json"
        flow_path.write_text(json.dumps(flow), encoding="utf-8")
        attached = WORKSPACE._command(["flow-add", "--db", os.fspath(database),
                                       "--snapshot", snapshot_id, "--input", os.fspath(flow_path)])
        receipt = {
            "receipt_schema_version": 1, "snapshot_id": snapshot_id,
            "overlay_id": attached["overlay_id"], "overlay_content_hash": attached["content_hash"],
            "extractor_identity": graph["extractor_identity"], "decision": "accepted",
            "reviewer_identity": "synthetic workspace mechanics fixture",
            "reviewer_model": "GPT-6.1 Sol High", "review_basis": "Mechanics fixture only; not an actual semantic review.",
            "reviewed_at": "2026-10-09T16:00:00Z",
        }
        receipt_path = repo.parent / "synthetic-origin-receipt.json"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        reviewed = WORKSPACE._command(["flow-review", "--db", os.fspath(database),
                                       "--snapshot", snapshot_id, "--overlay", attached["overlay_id"],
                                       "--input", os.fspath(receipt_path)])
        binding = {
            "binding_schema_version": 1, "snapshot_id": snapshot_id,
            "extractor_identity": graph["extractor_identity"], "route_fact_id": route["id"],
            "overlay_id": attached["overlay_id"],
            "flow_review_receipt_hash": reviewed["receipt_hash"],
        }
        binding_hash = hashlib.sha256(json.dumps(
            binding, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("ascii")).hexdigest()
        association_review = {
            "review_schema_version": 1, "binding_hash": binding_hash,
            **{key: binding[key] for key in ("snapshot_id", "extractor_identity", "route_fact_id",
                                               "overlay_id", "flow_review_receipt_hash")},
            "decision": "accepted", "reviewer_identity": "synthetic workspace mechanics fixture",
            "reviewer_model": "GPT-6.1 Sol High",
            "review_basis": "Mechanics fixture only; association hashes and keys are correctly joined.",
            "reviewed_at": "2026-10-09T16:00:00Z",
        }
        binding_path = repo.parent / "synthetic-origin-binding.json"
        binding_path.write_text(json.dumps({"binding": binding, "association_review": association_review}),
                                encoding="utf-8")
        WORKSPACE._command(["route-bind-add", "--db", os.fspath(database), "--snapshot", snapshot_id,
                            "--input", os.fspath(binding_path)])
        return snapshot_id, route["id"], historical["id"], attached["overlay_id"], context_route["id"]

    def test_prepare_indexes_compiler_and_both_profiles_for_same_database(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp/atlas-durable-integration-20261009") as temporary:
            root = Path(temporary)
            repo = root / "fixture-repo"
            repo.mkdir()
            state = root / "state"
            subprocess.run(["git", "init", "-q", os.fspath(repo)], check=True)
            subprocess.run(["git", "-C", os.fspath(repo), "config", "user.email", "atlas@example.invalid"], check=True)
            subprocess.run(["git", "-C", os.fspath(repo), "config", "user.name", "Atlas Test"], check=True)
            (repo / "FixtureHost.csproj").write_text(
                '<Project Sdk="Microsoft.NET.Sdk.Web"><PropertyGroup><TargetFramework>net8.0</TargetFramework>'
                '<ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable>'
                '<AssemblyName>FixtureHost</AssemblyName></PropertyGroup></Project>\n',
                encoding="utf-8",
            )
            (repo / "Program.cs").write_text('''using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.DependencyInjection;
using Fixture;
using Taggable.Api.Infrastructure.AdminTourManagement;
var builder = WebApplication.CreateBuilder(args);
builder.Services.AddControllers();
builder.Services.AddScoped<IHandler<Request>, AssetHandler>();
if (!string.IsNullOrEmpty(builder.Configuration["AdminTourManagement:Storage:TourImage:AccountName"]))
    builder.Services.AddScoped<ITourAssetStorage, AzureBlobTourAssetStorage>();
else
    builder.Services.AddScoped<ITourAssetStorage, LocalDiskTourAssetStorage>();
var app = builder.Build();
app.MapControllers();
''', encoding="utf-8")
            (repo / "Storage.cs").write_text('''namespace Taggable.Api.Infrastructure.AdminTourManagement;
public interface ITourAssetStorage { string Read(); }
public sealed class LocalDiskTourAssetStorage : ITourAssetStorage { public string Read() => "local"; }
public sealed class AzureBlobTourAssetStorage : ITourAssetStorage { public string Read() => "cloud"; }
''', encoding="utf-8")
            (repo / "Api.cs").write_text('''using Microsoft.AspNetCore.Mvc;
using Taggable.Api.Infrastructure.AdminTourManagement;
namespace Fixture;
public sealed record Request;
public interface IHandler<T> { string Handle(T value); }
public sealed class AssetHandler(ITourAssetStorage storage) : IHandler<Request>
{
    public string Handle(Request value) => storage.Read();
}
[ApiController]
[Route("api/workspace")]
public sealed class AssetController(IHandler<Request> handler) : ControllerBase
{
    [HttpGet("read")]
    public IActionResult Read() { _ = handler.Handle(new Request()); return Ok(); }
}
''', encoding="utf-8")
            (repo / "Extras.cs").write_text("namespace Fixture; public sealed class HistoricalNote {}\n",
                                             encoding="utf-8")
            (repo / "HistoricalEndpoint.cs").write_text('''using Microsoft.AspNetCore.Mvc;
namespace Fixture;
[ApiController]
[Route("api/workspace")]
public sealed class HistoricalController : ControllerBase
{
    [HttpGet("context")]
    public IActionResult Context() => Ok();
}
''', encoding="utf-8")
            subprocess.run(["git", "-C", os.fspath(repo), "add", "--", "FixtureHost.csproj", "Program.cs",
                            "Storage.cs", "Api.cs", "Extras.cs", "HistoricalEndpoint.cs"], check=True)
            feed = root / "empty-feed"
            feed.mkdir()
            nuget = root / "NuGet.Config"
            nuget.write_text(
                '<?xml version="1.0" encoding="utf-8"?><configuration><packageSources><clear/>'
                '<add key="empty" value="' + feed.as_posix() + '"/></packageSources></configuration>',
                encoding="utf-8",
            )
            dotnet = Path(os.environ["ATLAS_DOTNET"]).expanduser().resolve(strict=True)
            restore = subprocess.run([dotnet.as_posix(), "restore", (repo / "FixtureHost.csproj").as_posix(),
                                     "--configfile", nuget.as_posix(), "--ignore-failed-sources"],
                                    cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, timeout=90, check=False)
            self.assertEqual(restore.returncode, 0, restore.stderr or restore.stdout)

            seed = root / "seed-atlas.sqlite"
            origin_snapshot_id, route_id, historical_fact_id, origin_overlay_id, context_route_id = \
                self.attach_synthetic_seed_map(seed, repo)
            project_file = repo / "FixtureHost.csproj"
            project_file.write_text(project_file.read_text(encoding="utf-8").replace(
                "<AssemblyName>FixtureHost</AssemblyName>",
                "<AssemblyName>FixtureHost</AssemblyName><Description>workspace reindex</Description>",
            ), encoding="utf-8")
            subprocess.run(["git", "-C", os.fspath(repo), "add", "--", "FixtureHost.csproj"], check=True)
            restore_after_edit = subprocess.run(
                [dotnet.as_posix(), "restore", (repo / "FixtureHost.csproj").as_posix(),
                 "--configfile", nuget.as_posix(), "--ignore-failed-sources"],
                cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=90, check=False,
            )
            self.assertEqual(restore_after_edit.returncode, 0, restore_after_edit.stderr or restore_after_edit.stdout)

            result = WORKSPACE.prepare(
                os.fspath(repo), os.fspath(state), "FixtureHost.csproj", "net8.0",
                "Taggable.Api.Infrastructure.AdminTourManagement.ITourAssetStorage",
                dotnet.as_posix(), seed_db_arg=os.fspath(seed), max_bytes=131_072,
            )
            self.assertEqual(result["result"], "prepared")
            self.assertNotEqual(result["snapshot_id"], origin_snapshot_id)
            self.assertEqual(set(result["runtime_profiles"]), {"local-storage", "cloud-storage"})
            self.assertEqual(result["historical"]["terminal_route_count"], 1)
            self.assertEqual(len(result["routes"]), 1)
            self.assertEqual(result["routes"][0]["route_fact_id"], route_id)
            self.assertEqual(result["pending_route_reviews"], 1)
            packet = json.loads(Path(result["routes"][0]["packet_path"]).read_text(encoding="utf-8"))
            self.assertEqual(packet["historical_origin"]["snapshot_id"], origin_snapshot_id)
            self.assertEqual(packet["historical_origin"]["overlay_id"], origin_overlay_id)
            historical_context_ids = {item["fact_id"] for item in packet["historical_context_snippets"]}
            self.assertIn(historical_fact_id, historical_context_ids)
            self.assertIn(context_route_id, historical_context_ids)
            self.assertTrue(packet["complete_evidence_packet"]["selection"]["complete"])

            database = Path(result["database_path"])
            with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
                self.assertEqual(connection.execute("SELECT count(*) FROM atlas_compiler_supplements").fetchone()[0], 1)
                profiles = {row[0] for row in connection.execute(
                    "SELECT profile FROM atlas_runtime_observations")}
            self.assertEqual(profiles, {"local-storage", "cloud-storage"})

            graph_result = subprocess.run(
                [sys.executable, os.fspath(SCRIPT_DIR / "atlas.py"), "query", "--db", os.fspath(database),
                 "--snapshot", result["snapshot_id"], "--graph"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False,
            )
            self.assertEqual(graph_result.returncode, 0, graph_result.stderr)
            graph = json.loads(graph_result.stdout)["source_graph"]
            route = next(fact for fact in graph["facts"] if fact.get("kind") == "route_action")
            self.assertEqual(route["route_literal"], "api/workspace/read")
            context_route = next(fact for fact in graph["facts"] if fact.get("id") == context_route_id)
            context_snippet = next(item for item in packet["historical_context_snippets"]
                                   if item.get("fact_id") == context_route_id)
            self.assertEqual({key: context_snippet[key] for key in ("path", "sha256", "span")},
                             context_route["source"])

            impact = subprocess.run(
                [sys.executable, os.fspath(SCRIPT_DIR / "atlas.py"), "impact", "--db", os.fspath(database),
                 "--repo", os.fspath(repo), "--method",
                 "Taggable.Api.Infrastructure.AdminTourManagement.LocalDiskTourAssetStorage.Read",
                 "--max-tokens", "65536"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False,
            )
            self.assertEqual(impact.returncode, 0, impact.stderr)
            impact_document = json.loads(impact.stdout)
            receipts = [receipt for path in impact_document.get("compiler_associated_route_paths", [])
                        for hop in path.get("call_chain", [])
                        for receipt in hop.get("runtime_startup_observations", [])]
            self.assertIn("local-storage", {item["profile"] for item in receipts})

            evidence = subprocess.run(
                [sys.executable, os.fspath(SCRIPT_DIR / "atlas.py"), "evidence-pack", "--db", os.fspath(database),
                 "--repo", os.fspath(repo), "--route-fact-id", route_id, "--max-tokens", "65536"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False,
            )
            self.assertEqual(evidence.returncode, 0, evidence.stderr)
            evidence_document = json.loads(evidence.stdout)
            self.assertEqual(evidence_document["route"]["fact_id"], route_id)
            self.assertTrue(evidence_document["selection"]["complete"])
            profile_pairs = {(item["candidate_type"].split(".")[-1], receipt["profile"])
                             for item in evidence_document["runtime_startup_candidate_evidence"]
                             for receipt in item["runtime_startup_observations"]}
            self.assertIn(("LocalDiskTourAssetStorage", "local-storage"), profile_pairs)
            self.assertIn(("AzureBlobTourAssetStorage", "cloud-storage"), profile_pairs)

            route_lookup = subprocess.run(
                [sys.executable, os.fspath(SCRIPT_DIR / "atlas.py"), "route-find", "--db", os.fspath(database),
                 "--repo", os.fspath(repo), "--route-fact-id", route_id, "--max-tokens", "65536"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False,
            )
            self.assertEqual(route_lookup.returncode, 0, route_lookup.stderr)
            self.assertEqual(json.loads(route_lookup.stdout)["result"], "unmapped")

            state_files_before = {path.relative_to(state).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                                  for path in sorted(state.rglob("*")) if path.is_file()}
            status = WORKSPACE.status(os.fspath(state))
            state_files_after = {path.relative_to(state).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                                 for path in sorted(state.rglob("*")) if path.is_file()}
            self.assertEqual(status["snapshot_id"], result["snapshot_id"])
            self.assertEqual(state_files_after, state_files_before)

            # The preserved SQLite history is authoritative for the review queue.
            # A plausible but incomplete manifest must not hide a historical route.
            workspace_manifest_path = state / "workspace.json"
            workspace_manifest_raw = workspace_manifest_path.read_bytes()
            workspace_manifest = json.loads(workspace_manifest_raw)
            workspace_manifest["routes"] = []
            workspace_manifest_path.write_text(json.dumps(workspace_manifest), encoding="utf-8")
            omitted_state = {path.relative_to(state).as_posix(): path.read_bytes()
                             for path in sorted(state.rglob("*")) if path.is_file()}
            with self.assertRaisesRegex(WORKSPACE.WorkspaceError,
                                        "workspace route queue does not match all accepted historical routes"):
                WORKSPACE.status(os.fspath(state))
            self.assertEqual({path.relative_to(state).as_posix(): path.read_bytes()
                              for path in sorted(state.rglob("*")) if path.is_file()}, omitted_state)
            workspace_manifest_path.write_bytes(workspace_manifest_raw)

            # Rehashing packet bytes and the coordinator artifact table cannot
            # make substituted origin, claim, or historical context authoritative.
            atlas_module = importlib.import_module("atlas")
            coordinator = importlib.import_module("route_coordinator")
            packet_path = Path(result["routes"][0]["packet_path"])
            run_dir = state / "route-runs" / route["id"]
            coordinator_manifest_path = run_dir / coordinator.MANIFEST
            original_packet_raw = packet_path.read_bytes()
            original_coordinator_manifest = coordinator_manifest_path.read_bytes()
            original_packet = json.loads(original_packet_raw)
            tamper_cases = []
            wrong_origin = json.loads(original_packet_raw)
            wrong_origin["historical_origin"]["overlay_id"] = "0" * 64
            tamper_cases.append(("origin", wrong_origin,
                                 "historical origin for route .* is missing, superseded, or ambiguous"))
            wrong_claim = json.loads(original_packet_raw)
            draft = json.loads(wrong_claim["draft"])
            draft["reviewed_conclusions"][0]["claim"] += " substituted"
            wrong_claim["draft"] = json.dumps(draft, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            wrong_claim["draft_sha256"] = hashlib.sha256(wrong_claim["draft"].encode("utf-8")).hexdigest()
            wrong_claim["claims"][0]["claim"] += " substituted"
            tamper_cases.append(("claim", wrong_claim,
                                 "historical route draft must preserve the exact origin title"))
            wrong_context = json.loads(original_packet_raw)
            wrong_context["historical_context_snippets"][0]["text"] += " substituted"
            tamper_cases.append(("context", wrong_context,
                                 "historical cross-route context differs from exact current source spans"))
            for _label, changed_packet, expected_diagnostic in tamper_cases:
                changed_packet["packet_sha256"] = atlas_module._route_map_packet_digest(changed_packet)
                changed_raw = atlas_module._canonical_json(changed_packet) + b"\n"
                packet_path.write_bytes(changed_raw)
                coordinator_manifest = json.loads(original_coordinator_manifest)
                coordinator_manifest["artifacts"]["review-packet.json"] = {
                    "sha256": hashlib.sha256(changed_raw).hexdigest(), "bytes": len(changed_raw),
                }
                coordinator._write_manifest(coordinator_manifest_path, coordinator_manifest)
                tampered_state = {path.relative_to(state).as_posix(): path.read_bytes()
                                  for path in sorted(state.rglob("*")) if path.is_file()}
                with self.assertRaisesRegex(WORKSPACE.WorkspaceError, expected_diagnostic):
                    WORKSPACE.status(os.fspath(state))
                self.assertEqual({path.relative_to(state).as_posix(): path.read_bytes()
                                  for path in sorted(state.rglob("*")) if path.is_file()}, tampered_state)
            packet_path.write_bytes(original_packet_raw)
            coordinator_manifest_path.write_bytes(original_coordinator_manifest)
            self.assertEqual(json.loads(packet_path.read_bytes()), original_packet)

            # State-owned database and artifact paths are checked before their
            # symlink destinations are read or changed.
            external_database = root / "external-atlas.sqlite"
            external_database.write_bytes(database.read_bytes())
            database.rename(root / "workspace-atlas.sqlite")
            database.symlink_to(external_database)
            external_database_before = external_database.read_bytes()
            with self.assertRaisesRegex(WORKSPACE.WorkspaceError, "symbolic link"):
                WORKSPACE.status(os.fspath(state))
            self.assertEqual(external_database.read_bytes(), external_database_before)
            database.unlink()
            (root / "workspace-atlas.sqlite").rename(database)

            candidates = state / "candidates"
            external_candidates = root / "external-candidates"
            candidates.rename(external_candidates)
            candidates.symlink_to(external_candidates, target_is_directory=True)
            external_candidate_before = {
                path.relative_to(external_candidates).as_posix(): path.read_bytes()
                for path in external_candidates.rglob("*") if path.is_file()
            }
            with self.assertRaisesRegex(WORKSPACE.WorkspaceError, "symbolic link"):
                WORKSPACE.status(os.fspath(state))
            self.assertEqual({path.relative_to(external_candidates).as_posix(): path.read_bytes()
                              for path in external_candidates.rglob("*") if path.is_file()},
                             external_candidate_before)
            candidates.unlink()
            external_candidates.rename(candidates)

            run_directory = state / "route-runs"
            external_runs = root / "external-route-runs"
            run_directory.rename(external_runs)
            run_directory.symlink_to(external_runs, target_is_directory=True)
            external_run_before = {
                path.relative_to(external_runs).as_posix(): path.read_bytes()
                for path in external_runs.rglob("*") if path.is_file()
            }
            with self.assertRaisesRegex(WORKSPACE.WorkspaceError, "symbolic link"):
                WORKSPACE.status(os.fspath(state))
            self.assertEqual({path.relative_to(external_runs).as_posix(): path.read_bytes()
                              for path in external_runs.rglob("*") if path.is_file()}, external_run_before)
            run_directory.unlink()
            external_runs.rename(run_directory)

            init_record = state / "workspace-initializing.json"
            external_init = root / "external-initializing.json"
            external_init.write_bytes(b"preserve this initialization record")
            init_record.symlink_to(external_init)
            external_init_before = external_init.read_bytes()
            with self.assertRaisesRegex(WORKSPACE.WorkspaceError, "symbolic link"):
                WORKSPACE.prepare(
                    os.fspath(repo), os.fspath(state), "FixtureHost.csproj", "net8.0",
                    "Taggable.Api.Infrastructure.AdminTourManagement.ITourAssetStorage",
                    dotnet.as_posix(), seed_db_arg=os.fspath(seed), max_bytes=131_072,
                )
            self.assertEqual(external_init.read_bytes(), external_init_before)
            self.assertTrue(init_record.is_symlink())
            init_record.unlink()

            retry_state_before = {path.relative_to(state).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                                  for path in sorted(state.rglob("*")) if path.is_file()}
            retried = WORKSPACE.prepare(
                os.fspath(repo), os.fspath(state), "FixtureHost.csproj", "net8.0",
                "Taggable.Api.Infrastructure.AdminTourManagement.ITourAssetStorage",
                dotnet.as_posix(), seed_db_arg=os.fspath(seed), max_bytes=131_072,
            )
            retry_state_after = {path.relative_to(state).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                                 for path in sorted(state.rglob("*")) if path.is_file()}
            self.assertEqual(retried["snapshot_id"], result["snapshot_id"])
            changed_retry_files = sorted(key for key in set(retry_state_before) | set(retry_state_after)
                                         if retry_state_before.get(key) != retry_state_after.get(key))
            self.assertEqual(retry_state_after, retry_state_before,
                             f"exact Prepare retry changed workspace files: {changed_retry_files}")

            run_dir = state / "route-runs" / route["id"]
            rejection = {
                "review_schema_version": 1,
                "packet_sha256": packet["packet_sha256"],
                "evidence_sha256": packet["evidence_sha256"],
                "draft_sha256": packet["draft_sha256"],
                "reviewer_identity": "synthetic rejection mechanics fixture",
                "reviewer_model": "GPT-6.1 Sol High",
                "reviewed_at": "2026-10-09T16:30:00Z",
                "decision": "rejected",
                "assignment_review": {"decision": "accepted", "basis": "Synthetic mechanics record accepts the assignment."},
                "route_association_review": {"decision": "accepted", "basis": "Synthetic mechanics record accepts route association."},
                "conclusion_reviews": [
                    {"conclusion_number": 1, "decision": "accepted",
                     "basis": "Synthetic mechanics record accepts this conclusion."},
                    {"conclusion_number": 2, "decision": "rejected",
                     "basis": "Synthetic mechanics record rejects this conclusion for correction."},
                ],
            }
            rejected_review = root / "synthetic-rejected-review.json"
            rejected_review.write_text(json.dumps(rejection), encoding="utf-8")
            database_before_rejection = database.read_bytes()
            publication = WORKSPACE.publish(os.fspath(state), route_id, os.fspath(rejected_review))
            self.assertEqual(publication["result"], "rejected")
            self.assertEqual(database.read_bytes(), database_before_rejection)
            self.assertEqual(publication["status"]["routes"][0]["state"], "review-rejected")

            batch_dir = root / "review-batch"
            batch_dir.mkdir()
            batch_review_path = batch_dir / f"{route_id}.json"
            with self.assertRaisesRegex(WORKSPACE.WorkspaceError, "at least one known route review"):
                WORKSPACE.publish_reviews(os.fspath(state), os.fspath(batch_dir))
            batch_review_path.write_bytes(rejected_review.read_bytes())
            state_before_bad_batch = {
                path.relative_to(state).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(state.rglob("*")) if path.is_file()
            }
            (batch_dir / "unknown-route.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(WORKSPACE.WorkspaceError, "unknown route review file"):
                WORKSPACE.publish_reviews(os.fspath(state), os.fspath(batch_dir))
            (batch_dir / "unknown-route.json").unlink()
            (batch_dir / "notes.txt").write_text("not a review", encoding="utf-8")
            with self.assertRaisesRegex(WORKSPACE.WorkspaceError, "only regular .*json files"):
                WORKSPACE.publish_reviews(os.fspath(state), os.fspath(batch_dir))
            (batch_dir / "notes.txt").unlink()
            self.assertEqual({
                path.relative_to(state).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(state.rglob("*")) if path.is_file()
            }, state_before_bad_batch)
            r0_review_artifacts_before_batch = {
                name: (run_dir / name).read_bytes() for name in ("review-packet.json", "sol-review.json")
            }
            batch_review_path.write_bytes(rejected_review.read_bytes())
            with mock.patch.object(WORKSPACE, "status", wraps=WORKSPACE.status) as final_status:
                rejected_batch = WORKSPACE.publish_reviews(os.fspath(state), os.fspath(batch_dir))
                final_status.assert_called_once_with(os.fspath(state))
            self.assertEqual(rejected_batch["result"], "partial")
            self.assertEqual(rejected_batch["routes"][0]["result"], "rejected")
            self.assertEqual(rejected_batch["routes"][0]["state"], "review-rejected")
            self.assertEqual(database.read_bytes(), database_before_rejection)
            self.assertEqual({name: (run_dir / name).read_bytes()
                              for name in r0_review_artifacts_before_batch}, r0_review_artifacts_before_batch)

            r0_packet_path = run_dir / "review-packet.json"
            r0_review_path = run_dir / "sol-review.json"
            r0_manifest_path = run_dir / coordinator.MANIFEST
            r0_packet_raw = r0_packet_path.read_bytes()
            r0_review_raw = r0_review_path.read_bytes()
            r0_manifest_raw = r0_manifest_path.read_bytes()
            r0_files_before = {path.relative_to(run_dir).as_posix(): path.read_bytes()
                               for path in run_dir.rglob("*") if path.is_file()}

            # A rehashed attempt to turn the validated rejection into acceptance
            # cannot authorize a correction against the unchanged R0 record.
            forged_review = json.loads(r0_review_raw)
            forged_review["decision"] = "accepted"
            forged_review_raw = json.dumps(forged_review, ensure_ascii=True, sort_keys=True,
                                           separators=(",", ":")).encode("ascii") + b"\n"
            r0_review_path.write_bytes(forged_review_raw)
            forged_manifest = json.loads(r0_manifest_raw)
            forged_manifest["artifacts"]["sol-review.json"] = {
                "sha256": hashlib.sha256(forged_review_raw).hexdigest(), "bytes": len(forged_review_raw),
            }
            coordinator._write_manifest(r0_manifest_path, forged_manifest)
            with self.assertRaisesRegex(WORKSPACE.WorkspaceError,
                                        "review decision must be rejected based on all independent decisions"):
                WORKSPACE.correct(os.fspath(state), route_id, os.fspath(rejected_review))
            r0_review_path.write_bytes(r0_review_raw)
            r0_manifest_path.write_bytes(r0_manifest_raw)

            candidate_draft_path = state / "candidates" / f"{route_id}.json"
            original_draft = json.loads(candidate_draft_path.read_text(encoding="utf-8"))
            unauthorized_text = json.loads(json.dumps(original_draft))
            unauthorized_text["reviewed_conclusions"][0]["claim"] += " unauthorized"
            unauthorized_path = root / "unauthorized-accepted-text.json"
            unauthorized_path.write_text(json.dumps(unauthorized_text), encoding="utf-8")
            with self.assertRaisesRegex(
                    WORKSPACE.WorkspaceError,
                    "R1 correction draft failed source-bound preflight: historical correction may change text only for conclusions rejected in R0"):
                WORKSPACE.correct(os.fspath(state), route_id, os.fspath(unauthorized_path))
            self.assertFalse((state / "correction-runs").exists())

            changed_citation = json.loads(json.dumps(original_draft))
            changed_citation["reviewed_conclusions"][1]["evidence"][0] = {
                "fact_id": route_id, "source": route["source"],
            }
            changed_citation_path = root / "changed-citation.json"
            changed_citation_path.write_text(json.dumps(changed_citation), encoding="utf-8")
            with self.assertRaisesRegex(
                    WORKSPACE.WorkspaceError,
                    "R1 correction draft failed source-bound preflight: historical correction must preserve every original citation byte-for-byte"):
                WORKSPACE.correct(os.fspath(state), route_id, os.fspath(changed_citation_path))
            self.assertFalse((state / "correction-runs").exists())

            corrected_draft = json.loads(json.dumps(original_draft))
            corrected_draft["reviewed_conclusions"][1]["claim"] += " corrected after independent feedback"
            corrected_path = root / "corrected-draft.json"
            corrected_path.write_text(json.dumps(corrected_draft), encoding="utf-8")
            correction = WORKSPACE.correct(os.fspath(state), route_id, os.fspath(corrected_path))
            self.assertEqual(correction["result"], "correction-prepared")
            correction_run = Path(correction["correction_run_dir"])
            self.assertEqual(correction_run, state / "correction-runs" / route_id / "r1")
            self.assertEqual(Path(correction["prior_run_dir"]), run_dir)
            self.assertEqual(correction["state"], "review-ready")
            r1_packet = json.loads(Path(correction["packet_path"]).read_text(encoding="utf-8"))
            lineage = r1_packet["historical_correction"]
            self.assertEqual(lineage["schema_version"], 1)
            self.assertEqual(lineage["prior_packet"], json.loads(r0_packet_raw))
            self.assertEqual(lineage["prior_review"], json.loads(r0_review_raw))
            self.assertEqual(lineage["prior_packet_sha256"], json.loads(r0_packet_raw)["packet_sha256"])
            self.assertEqual(lineage["prior_review_sha256"],
                             hashlib.sha256(atlas_module._canonical_json(json.loads(r0_review_raw))).hexdigest())
            r1_context_route = next(item for item in r1_packet["historical_context_snippets"]
                                    if item["fact_id"] == context_route_id)
            self.assertEqual({key: r1_context_route[key] for key in ("path", "sha256", "span")},
                             context_route["source"])
            self.assertEqual({path.relative_to(run_dir).as_posix(): path.read_bytes()
                              for path in run_dir.rglob("*") if path.is_file()}, r0_files_before)

            active_status = WORKSPACE.status(os.fspath(state))
            active_route = next(item for item in active_status["routes"] if item["route_fact_id"] == route_id)
            self.assertEqual(active_route["run_dir"], os.fspath(correction_run))
            self.assertEqual(active_route["state"], "review-ready")

            accepted_r1 = {
                "review_schema_version": 1,
                "packet_sha256": r1_packet["packet_sha256"],
                "evidence_sha256": r1_packet["evidence_sha256"],
                "draft_sha256": r1_packet["draft_sha256"],
                "reviewer_identity": "synthetic R1 acceptance mechanics fixture",
                "reviewer_model": "GPT-6.1 Sol High",
                "reviewed_at": "2026-10-09T16:45:00Z",
                "decision": "accepted",
                "assignment_review": {"decision": "accepted", "basis": "Synthetic mechanics record accepts the corrected assignment."},
                "route_association_review": {"decision": "accepted", "basis": "Synthetic mechanics record accepts the corrected association."},
                "conclusion_reviews": [
                    {"conclusion_number": index, "decision": "accepted",
                     "basis": "Synthetic mechanics record accepts this corrected conclusion."}
                    for index, _claim in enumerate(r1_packet["claims"], start=1)
                ],
            }
            accepted_r1_path = root / "synthetic-accepted-r1.json"
            accepted_r1_path.write_text(json.dumps(accepted_r1), encoding="utf-8")
            batch_review_path.write_bytes(accepted_r1_path.read_bytes())
            with mock.patch.object(WORKSPACE, "status", wraps=WORKSPACE.status) as final_status:
                publication_r1 = WORKSPACE.publish_reviews(os.fspath(state), os.fspath(batch_dir))
                final_status.assert_called_once_with(os.fspath(state))
            self.assertEqual(publication_r1["result"], "published")
            self.assertEqual(publication_r1["routes"][0]["state"], "published")
            self.assertEqual(database.read_bytes() != database_before_rejection, True)
            self.assertEqual({path.relative_to(run_dir).as_posix(): path.read_bytes()
                              for path in run_dir.rglob("*") if path.is_file()}, r0_files_before)
            cold_status = WORKSPACE.status(os.fspath(state))
            active_route = next(item for item in cold_status["routes"] if item["route_fact_id"] == route_id)
            self.assertEqual(active_route["run_dir"], os.fspath(correction_run))
            self.assertEqual(active_route["state"], "published")

            (run_dir / ".manifest.json.123.tmp").write_bytes(b"interrupted manifest replacement")
            interrupted_state = {path.relative_to(state).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                                 for path in sorted(state.rglob("*")) if path.is_file()}
            with self.assertRaisesRegex(WORKSPACE.WorkspaceError, "interrupted R0 write"):
                WORKSPACE.status(os.fspath(state))
            after_refusal = {path.relative_to(state).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                             for path in sorted(state.rglob("*")) if path.is_file()}
            self.assertEqual(after_refusal, interrupted_state)

if __name__ == "__main__":
    unittest.main()
