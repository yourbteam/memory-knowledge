"""Disposable Atlas integration tests for the bounded native route batch.

Worker and reviewer result JSON used here is synthetic. These tests exercise the
admission and publication machinery; they are not semantic model reviews or live
native-host provenance.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
from copy import deepcopy
from unittest.mock import patch

from tests.test_codebase_atlas import AtlasCliTests, git

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "skills/codebase-atlas-machinery/scripts"
BATCH_SPEC = importlib.util.spec_from_file_location("atlas_route_batch_test_module", SCRIPT_DIR / "route_batch.py")
BATCH = importlib.util.module_from_spec(BATCH_SPEC)
assert BATCH_SPEC.loader is not None
BATCH_SPEC.loader.exec_module(BATCH)

CAPTURED_NATIVE_SOL_JSON = r'''{
  "review_schema_version": 1,
  "packet_sha256": "7c531e6f28790281c5670c87d876f8d244b2a728c8a0787ab528e112069d6469",
  "evidence_sha256": "c173c38d68b3843648fc569b2f10c2ef93913159e5deba96887beb5106fd4eaf",
  "draft_sha256": "5b9c87a485c5983eb04c05992bbc5642f31da97d553b75c0da054c989ec50e25",
  "reviewer_identity": "atlas_sol_review_0747255ab01cb4054a6edcc5",
  "reviewer_model": "GPT-6.1 Sol High",
  "reviewed_at": "2026-10-10T01:03:23Z",
  "decision": "accepted",
  "assignment_review": {
    "decision": "accepted",
    "basis": "The assignment is a source-evidence review of one selected route. The packet supplies exact source snippets for all four conclusions, compiler evidence associating the action with the command-handler implementation, and explicit limits on runtime evidence. The draft stays within this route and does not assert omitted helper behavior or runtime dispatch."
  },
  "conclusion_reviews": [
    {
      "conclusion_number": 1,
      "decision": "accepted",
      "basis": "Route fact 0747255ab01cb4054a6edcc5 cites AdminOrganizationsController.cs line 95, whose exact text is [HttpPost(\"~/api/admin/uploadLocationImage\")]. The packet's action snippet and route record associate it with UploadLocationImage. Authorization fact cbc7e1b7e827ef0ad7c1481c cites line 10 and explicitly names PassportAuthenticationExtensions.SchemeName. This supports the stated attribute reference, without establishing its underlying string value or runtime authentication behavior."
    },
    {
      "conclusion_number": 2,
      "decision": "accepted",
      "basis": "The cited action fact f1dbc3f7f1f21d699b348f5d covers AdminOrganizationsController.cs lines 95–100. Its exact snippet includes [Consumes(\"multipart/form-data\")] and constructs UploadAdminLocationImageCommand from form.file ?? throw new InvalidOperationException(\"A valid image file is required.\"). This directly supports the multipart declaration, non-null command argument, and null-file exception."
    },
    {
      "conclusion_number": 3,
      "decision": "accepted",
      "basis": "The cited handler fact 46422e129287d041473729aa covers AdminOrganizationHandlers.cs lines 1051–1060. The exact method body throws when command.File.Length <= 0, awaits tourAssetStorage.UploadLocationImageAsync(command.File, cancellationToken), and returns new AdminUploadedLocationImageResponse(true, imageUrl). The claim describes this method body and does not assert which storage implementation executes at runtime."
    },
    {
      "conclusion_number": 4,
      "decision": "accepted",
      "basis": "The exact cited Program.cs spans at lines 109 and 111 contain AddScoped<ITourAssetStorage, LocalDiskTourAssetStorage>( and AddScoped<ITourAssetStorage, AzureBlobTourAssetStorage>( respectively. They support the existence of both source registrations. These isolated spans do not establish runtime selection; the packet explicitly preserves that limitation. Profile-specific startup observations do not prove route execution."
    }
  ],
  "route_association_review": {
    "decision": "accepted",
    "basis": "The route record and action snippet identify POST api/admin/uploadLocationImage and UploadLocationImage. The action constructs UploadAdminLocationImageCommand and invokes the correspondingly typed handler parameter. The supplied compiler relationship confirms the interface Handle binding and matches UploadAdminLocationImageCommandHandler.Handle, with its source registration. That handler calls UploadLocationImageAsync on tourAssetStorage; the packet associates both storage candidates and registrations with this route. This supports source-map association while leaving runtime DI selection and runtime route reachability unproven."
  }
}'''


class AtlasRouteBatchFixture(unittest.TestCase):
    def setUp(self):
        self.atlas = AtlasCliTests("runTest")
        self.atlas.setUp()
        self.repo = self.atlas.repo
        self.db = self.atlas.db
        (self.repo / "Routes.cs").write_text('''using Microsoft.AspNetCore.Mvc;
namespace Demo.Customer
{
    [Route("api/customer")]
    public sealed class CustomerController : ControllerBase
    {
        [HttpPost("uploadTourImage")]
        public IActionResult UploadTourImage() => Ok();
        [HttpPost("uploadTourStockImage")]
        public IActionResult UploadTourStockImage() => Ok();
    }
}
namespace Demo.Admin
{
    [Route("api/admin")]
    public sealed class AdminController : ControllerBase
    {
        [HttpPost("uploadLocationImage")]
        public IActionResult UploadLocationImage() => Ok();
    }
}
''', encoding="utf-8")
        git(self.repo, "add", "--", "Routes.cs")
        self.indexed = self.atlas.index()
        graph = self.atlas.graph(self.indexed["snapshot_id"])
        self.extractor_identity = graph["extractor_identity"]
        routes = [item for item in graph["facts"] if item.get("kind") == "route_action"]
        self.routes = {item["route_literal"]: item for item in routes}
        self.assertEqual(set(self.routes), {
            "api/customer/uploadTourImage", "api/customer/uploadTourStockImage", "api/admin/uploadLocationImage",
        })
        self.route_ids = [self.routes[key]["id"] for key in sorted(self.routes)]
        self.run = self.atlas.root / "batch"

    def tearDown(self):
        self.atlas.tearDown()

    def index_files(self, root: Path) -> dict[str, str]:
        return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(root.rglob("*")) if path.is_file()}

    def prepare(self, route_ids: list[str] | None = None):
        return BATCH.prepare(os.fspath(self.repo), os.fspath(self.db), route_ids or self.route_ids,
                             os.fspath(self.run))

    def spawn(self, job: dict[str, object], task_name: str):
        return {
            "task_name": job["requested_task_name"],
            "model": job["model_request"],
            "reasoning_effort": job["reasoning_effort_request"],
            "fork_turns": job["fork_turns_request"],
            "message": job["spawn_message"],
        }

    def assert_short_assignment_allows_only_staged_result(self, job: dict[str, object]) -> None:
        message = str(job["spawn_message"])
        self.assertIn(os.fspath(Path(str(job["stage_path"])).resolve()), message)
        self.assertIn("You may create exactly one output file", message)
        self.assertIn("result_path=", message)
        self.assertIn("result_sha256=", message)
        self.assertIn("result_bytes=", message)
        lowered = message.lower()
        self.assertNotIn("do not edit files", lowered)
        self.assertNotIn("return the requested json", lowered)
        self.assertNotIn("return only the role result json", lowered)

    def staged_observation(self, job: dict[str, object], task_name: str, raw: bytes) -> dict[str, object]:
        stage_path = Path(str(job["stage_path"]))
        stage_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(stage_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
        return self.pointer_observation(job, task_name, raw)

    @staticmethod
    def pointer_observation(job: dict[str, object], task_name: str, raw: bytes,
                            *, path: str | None = None, sha256: str | None = None,
                            byte_count: int | None = None) -> dict[str, object]:
        pointer = {
            "result_path": path or os.fspath(Path(str(job["stage_path"]))),
            "result_sha256": sha256 or hashlib.sha256(raw).hexdigest(),
            "result_bytes": len(raw) if byte_count is None else byte_count,
        }
        return {
            "task_name": task_name,
            "status": "completed",
            "final_text": json.dumps(pointer, separators=(",", ":")),
        }

    def finish(self, job: dict[str, object], task_name: str, answer: dict[str, object]):
        raw = json.dumps(answer, separators=(",", ":")).encode("utf-8")
        observation = self.staged_observation(job, task_name, raw)
        return BATCH.finish_job(os.fspath(self.run), str(job["job_id"]), observation)

    def job_route_id(self, job: dict[str, object]) -> str:
        manifest = json.loads((self.run / BATCH.MANIFEST).read_text(encoding="utf-8"))
        saved = next(item for item in manifest["jobs"] if item["job_id"] == job["job_id"])
        return saved["route_fact_id"]

    def draft_for(self, route_id: str) -> dict[str, object]:
        route = next(item for item in self.routes.values() if item["id"] == route_id)
        return {
            "overlay_schema_version": 1,
            "snapshot_id": self.indexed["snapshot_id"],
            "extractor_identity": self.extractor_identity,
            "title": "Synthetic route-batch mechanics draft",
            "reviewed_conclusions": [{
                "claim": "This synthetic mechanics draft describes the selected route declaration.",
                "evidence": [{"fact_id": route_id, "source": route["source"]}],
            }],
        }

    @staticmethod
    def review_for(packet: dict[str, object]) -> dict[str, object]:
        return {
            "review_schema_version": 1,
            "packet_sha256": packet["packet_sha256"],
            "evidence_sha256": packet["evidence_sha256"],
            "draft_sha256": packet["draft_sha256"],
            "reviewer_identity": "synthetic native batch mechanics fixture",
            "reviewer_model": "GPT-6.1 Sol High",
            "reviewed_at": "2026-10-10T00:00:00Z",
            "decision": "accepted",
            "assignment_review": {
                "decision": "accepted",
                "basis": 'Synthetic mechanics fixture includes the quote-escaping sentinel [HttpPost("~/api/admin/uploadLocationImage")].',
            },
            "conclusion_reviews": [{"conclusion_number": 1, "decision": "accepted",
                                    "basis": "Synthetic fixture accepts this supported route conclusion."}],
            "route_association_review": {"decision": "accepted", "basis": "Synthetic fixture accepts the exact route association."},
        }

    @staticmethod
    def prompt_json_section(prompt: str, start_label: str, end_label: str) -> dict[str, object]:
        start = prompt.index(start_label) + len(start_label)
        end = prompt.index(end_label, start)
        return json.loads(prompt[start:end].strip())

    def test_luna_and_sol_assignments_bind_each_fact_to_its_canonical_source(self):
        route_id = self.routes["api/admin/uploadLocationImage"]["id"]
        self.prepare([route_id])
        luna = BATCH.next_job(os.fspath(self.run))
        self.assertEqual(luna["result"], "job_reserved")
        self.assertEqual(luna["role"], "luna_draft")

        evidence_path = self.run / "route-runs" / route_id / "evidence-pack.json"
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        prompt = Path(luna["prompt_path"]).read_text(encoding="utf-8")
        packet_marker = "\n\nCOMPLETE EVIDENCE PACKET:\n"
        catalogue_marker = "\n\nCANONICAL CITATION CATALOGUE (ordinary Atlas facts only; each fact_id is bound to its one saved fact.source):\n"
        contextual_marker = "\n\nCONTEXTUAL PACKET SOURCES (visible in the packet for reasoning; not canonical citation anchors for ordinary facts):\n"
        schema_marker = "\n\nEXACT STAGED ROUTE-MAP JSON SCHEMA:\n"
        self.assertIn(packet_marker, prompt)
        prompt_packet = self.prompt_json_section(prompt, packet_marker, catalogue_marker)
        catalogue = self.prompt_json_section(prompt, catalogue_marker, contextual_marker)
        contextual = self.prompt_json_section(prompt, contextual_marker, schema_marker)
        self.assertEqual(prompt_packet, evidence)

        # This Atlas fixture has the same structural ambiguity as the captured
        # stock-route packet: its route fact ID labels both the action source
        # and the controller-prefix context source.
        route = self.routes["api/admin/uploadLocationImage"]
        prefix_source = route["controller_route_source"]
        prefix_snippet = next(
            item for item in evidence["source_snippets"]
            if item["fact_id"] == route_id
            and {key: item[key] for key in ("path", "sha256", "span")} == prefix_source
        )
        self.assertEqual(prefix_snippet["text"], '[Route("api/admin")]')
        self.assertIn({"fact_id": route_id, "source": prefix_source}, contextual)

        graph = self.atlas.graph(self.indexed["snapshot_id"])
        graph_facts = {item["id"]: item for item in graph["facts"]}
        expected = {
            fact_id: graph_facts[fact_id]["source"]
            for fact_id in sorted({
                item["fact_id"]
                for field in ("source_snippets", "candidate_snippets")
                for item in evidence[field]
            })
        }
        self.assertEqual(len(catalogue), len(expected))
        self.assertEqual({item["fact_id"] for item in catalogue}, set(expected))
        self.assertEqual(len({item["fact_id"] for item in catalogue}), len(catalogue))
        self.assertEqual({item["fact_id"]: item["source"] for item in catalogue}, expected)
        self.assertEqual(expected[route_id], route["source"])
        self.assertNotEqual(expected[route_id], prefix_source)

        manifest = json.loads((self.run / BATCH.MANIFEST).read_text(encoding="utf-8"))
        current_snapshot, current_extractor, associations = BATCH._snapshot(self.repo, self.db)
        for mutation in ("missing", "duplicate"):
            with self.subTest(graph_source=mutation):
                altered = deepcopy(current_snapshot)
                facts = altered["source_graph"]["facts"]
                selected = next(item for item in facts if item["id"] == route_id)
                if mutation == "missing":
                    altered["source_graph"]["facts"] = [item for item in facts if item["id"] != route_id]
                else:
                    altered["source_graph"]["facts"] = [*facts, deepcopy(selected)]
                with patch.object(BATCH, "_snapshot", return_value=(altered, current_extractor, associations)):
                    with self.assertRaisesRegex(BATCH.BatchError, "missing or ambiguous canonical source identity"):
                        BATCH._canonical_citation_catalogue(manifest, evidence)

        schema = json.loads(Path(luna["schema_path"]).read_text(encoding="utf-8"))
        citation_schema = schema["properties"]["reviewed_conclusions"]["items"]["properties"]["evidence"]["items"]
        pair_options = citation_schema["oneOf"]
        self.assertEqual(len(pair_options), len(catalogue))
        for option, entry in zip(pair_options, catalogue):
            self.assertEqual(option["type"], "object")
            self.assertFalse(option["additionalProperties"])
            self.assertEqual(option["required"], ["fact_id", "source"])
            self.assertEqual(option["properties"]["fact_id"], {"const": entry["fact_id"]})
            self.assertEqual(option["properties"]["source"], {"const": entry["source"]})
        self.assertFalse(any(
            option["properties"]["fact_id"] == {"const": route_id}
            and option["properties"]["source"] == {"const": prefix_source}
            for option in pair_options
        ))
        for namespace_field in (
            "compiler_relationships", "compiler_source_snippets", "compiler_relationship_semantics",
            "runtime_startup_candidate_evidence", "runtime_observation_scope",
        ):
            if namespace_field in evidence:
                self.assertIn(json.dumps(evidence[namespace_field], ensure_ascii=False, sort_keys=True, indent=2), prompt)

        luna_name = "returned-luna-canonical-source-contract"
        BATCH.record_spawn(os.fspath(self.run), luna["job_id"], self.spawn(luna, luna_name), luna_name)
        self.finish(luna, luna_name, self.draft_for(route_id))
        sol = BATCH.next_job(os.fspath(self.run))
        self.assertEqual(sol["role"], "sol_review")
        sol_prompt = Path(sol["prompt_path"]).read_text(encoding="utf-8")
        sol_packet_marker = "\n\nEXACT REVIEW PACKET:\n"
        sol_packet = self.prompt_json_section(sol_prompt, sol_packet_marker, catalogue_marker)
        sol_contextual_marker = "\n\nCONTEXTUAL PACKET SOURCES (visible in the evidence packet for reasoning; not canonical citation anchors for ordinary facts):\n"
        sol_catalogue = self.prompt_json_section(sol_prompt, catalogue_marker, sol_contextual_marker)
        sol_contextual = self.prompt_json_section(sol_prompt, sol_contextual_marker,
                                                   "\n\nEXACT STAGED REVIEW JSON SCHEMA:\n")
        self.assertEqual(sol_catalogue, catalogue)
        self.assertEqual(sol_contextual, contextual)
        self.assertEqual(sol_packet["complete_evidence_packet"], evidence)
        for namespace_field in (
            "compiler_relationships", "compiler_source_snippets", "compiler_relationship_semantics",
            "runtime_startup_candidate_evidence", "runtime_observation_scope",
        ):
            if namespace_field in evidence:
                self.assertEqual(sol_packet["complete_evidence_packet"][namespace_field], evidence[namespace_field])

    def test_contextual_controller_prefix_citation_stays_refused_without_map_write(self):
        route = self.routes["api/admin/uploadLocationImage"]
        route_id = route["id"]
        primary_run = self.atlas.root / "contextual-prefix-refusal"
        BATCH.prepare(os.fspath(self.repo), os.fspath(self.db), [route_id], os.fspath(primary_run))
        evidence = json.loads((primary_run / "route-runs" / route_id / "evidence-pack.json").read_text(encoding="utf-8"))
        prefix_source = route["controller_route_source"]
        prefix_snippet = next(
            item for item in evidence["source_snippets"]
            if item["fact_id"] == route_id
            and {key: item[key] for key in ("path", "sha256", "span")} == prefix_source
        )
        draft = self.draft_for(route_id)
        route_citation = next(
            citation for conclusion in draft["reviewed_conclusions"]
            for citation in conclusion["evidence"] if citation["fact_id"] == route_id
        )
        self.assertEqual(prefix_snippet["text"], '[Route("api/admin")]')

        wrong_pairs = (
            (route_id, prefix_source, "contextual controller prefix"),
            (route_id, self.routes["api/customer/uploadTourImage"]["source"], "another fact's source"),
            ("0" * 24, route["source"], "unknown fact ID"),
        )
        self.assertNotEqual(wrong_pairs[-1][0], route_id)
        for index, (fact_id, source, label) in enumerate(wrong_pairs):
            with self.subTest(pair=label):
                run = primary_run if index == 0 else self.atlas.root / f"bad-citation-refusal-{index}"
                if index:
                    BATCH.prepare(os.fspath(self.repo), os.fspath(self.db), [route_id], os.fspath(run))
                luna = BATCH.next_job(os.fspath(run))
                bad_draft = self.draft_for(route_id)
                citation = next(
                    item for conclusion in bad_draft["reviewed_conclusions"]
                    for item in conclusion["evidence"] if item["fact_id"] == route_id
                )
                citation["fact_id"] = fact_id
                citation["source"] = source
                task_name = f"returned-luna-{index}-bad-citation"
                BATCH.record_spawn(os.fspath(run), luna["job_id"], self.spawn(luna, task_name), task_name)
                db_before = self.db.read_bytes()
                observation = self.staged_observation(luna, task_name,
                                                      json.dumps(bad_draft, separators=(",", ":")).encode("utf-8"))
                result = BATCH.finish_job(os.fspath(run), luna["job_id"], observation)
                self.assertEqual(result["result"], "refused")
                self.assertEqual(self.db.read_bytes(), db_before)
                manifest = json.loads((run / BATCH.MANIFEST).read_text(encoding="utf-8"))
                self.assertEqual(manifest["routes"][0]["state"], "refused")
                self.assertEqual(len(manifest["jobs"]), 1)
                self.assertEqual(manifest["jobs"][0]["role"], "luna_draft")

    def test_real_atlas_packets_native_job_admission_and_coordinator_publication(self):
        prepared = self.prepare()
        self.assertEqual(prepared["result"], "in_progress")
        self.assertEqual({item["route_fact_id"] for item in prepared["routes"]}, set(self.route_ids))
        self.assertEqual({item["state"] for item in prepared["routes"]}, {"luna_pending"})
        self.assertEqual({item["controller_type_id"] for item in self.routes.values()},
                         {"Demo.Customer.CustomerController`0", "Demo.Admin.AdminController`0"})

        before_status = self.index_files(self.run)
        db_before_status = self.db.read_bytes()
        status = BATCH.status(os.fspath(self.run))
        self.assertEqual(status["jobs_total"], 0)
        self.assertEqual(self.index_files(self.run), before_status)
        self.assertEqual(self.db.read_bytes(), db_before_status)

        job = BATCH.next_job(os.fspath(self.run))
        self.assertEqual(job["result"], "job_reserved")
        self.assertEqual(job["role"], "luna_draft")
        self.assertEqual(job["model_request"], "gpt-6-luna")
        self.assertEqual(job["reasoning_effort_request"], "high")
        self.assertEqual(job["fork_turns_request"], "none")
        prompt = Path(job["prompt_path"]).read_bytes()
        schema = Path(job["schema_path"]).read_bytes()
        self.assertEqual(hashlib.sha256(prompt).hexdigest(), BATCH._sha(prompt))
        self.assertEqual(hashlib.sha256(schema).hexdigest(), BATCH._sha(schema))
        short_message = str(job["spawn_message"])
        self.assertNotEqual(short_message, prompt.decode("utf-8"))
        self.assertIn(os.fspath(Path(job["prompt_path"]).resolve()), short_message)
        self.assertIn(hashlib.sha256(prompt).hexdigest(), short_message)
        self.assertIn(str(len(prompt)), short_message)
        self.assert_short_assignment_allows_only_staged_result(job)
        reserved = self.index_files(self.run)
        for bad in (
            {"model": "gpt-6.1-sol", "reasoning_effort": "high", "fork_turns": "none"},
            {"model": "gpt-6-luna", "reasoning_effort": "medium", "fork_turns": "none"},
            {"model": "gpt-6-luna", "reasoning_effort": "high", "fork_turns": "working-tree"},
        ):
            with self.assertRaises(BATCH.BatchError):
                BATCH.record_spawn(os.fspath(self.run), job["job_id"], bad, "returned-luna-task")
            self.assertEqual(self.index_files(self.run), reserved)
        for altered_message in (
            short_message.replace(hashlib.sha256(prompt).hexdigest(), "0" * 64),
            short_message.replace(os.fspath(Path(job["prompt_path"]).resolve()), "/outside/prompt.md"),
            short_message + "\nchanged",
        ):
            with self.assertRaises(BATCH.BatchError):
                BATCH.record_spawn(os.fspath(self.run), job["job_id"],
                                   dict(self.spawn(job, "returned-luna-task"), message=altered_message),
                                   "returned-luna-task")
            self.assertEqual(self.index_files(self.run), reserved)
        task_name = "returned-luna-task"
        good_spawn = self.spawn(job, task_name)
        BATCH.record_spawn(os.fspath(self.run), job["job_id"], good_spawn, task_name)
        self.assertEqual(BATCH.next_job(os.fspath(self.run))["result"], "awaiting_existing_worker")

        route_id = self.job_route_id(job)
        draft = self.draft_for(route_id)
        before_bad_finish = self.index_files(self.run)
        with self.assertRaisesRegex(BATCH.BatchError, "exact closed same-task native terminal record"):
            BATCH.finish_job(os.fspath(self.run), job["job_id"], {
                "task_name": "different-agent", "status": "completed",
                "final_text": json.dumps(draft, separators=(",", ":")),
            })
        self.assertEqual(self.index_files(self.run), before_bad_finish)

        luna_finished = self.finish(job, task_name, draft)
        self.assertEqual(luna_finished["result"], "review_ready")
        review_job = BATCH.next_job(os.fspath(self.run))
        self.assertEqual(review_job["role"], "sol_review")
        self.assert_short_assignment_allows_only_staged_result(review_job)
        self.assertEqual(review_job["model_request"], "gpt-6.1-sol")
        self.assertEqual(review_job["reasoning_effort_request"], "high")
        self.assertEqual(review_job["fork_turns_request"], "none")
        review_packet = json.loads((Path(self.run) / "route-runs" / route_id / "review-packet.json").read_text())
        review = self.review_for(review_packet)
        sol_task_name = "returned-sol-task"
        sol_spawn = self.spawn(review_job, sol_task_name)
        wrong_spawn = dict(sol_spawn, model="gpt-6-luna")
        before_wrong_sol_spawn = self.index_files(self.run)
        with self.assertRaises(BATCH.BatchError):
            BATCH.record_spawn(os.fspath(self.run), review_job["job_id"], wrong_spawn, sol_task_name)
        self.assertEqual(self.index_files(self.run), before_wrong_sol_spawn)
        BATCH.record_spawn(os.fspath(self.run), review_job["job_id"], sol_spawn, sol_task_name)
        published = self.finish(review_job, sol_task_name, review)
        self.assertEqual(published["result"], "published_and_fresh")
        sol_bytes = Path(review_job["stage_path"]).read_bytes()
        self.assertIn(b'\\"~/api/admin/uploadLocationImage\\"', sol_bytes)
        sol_answer = self.run / "workers" / route_id / "sol_review" / "answer.json"
        coordinator_sol_answer = self.run / "route-runs" / route_id / "sol-review.json"
        self.assertEqual(sol_answer.read_bytes(), sol_bytes)
        self.assertEqual(coordinator_sol_answer.read_bytes(), sol_bytes)
        found = self.atlas.route_find(route_id)
        self.assertEqual(json.loads(found.stdout)["result"], "fresh")
        final = BATCH.status(os.fspath(self.run))
        completed_route = next(item for item in final["routes"] if item["route_fact_id"] == route_id)
        self.assertEqual(completed_route["state"], "published")
        # Complete the remaining selected routes from their code-issued jobs,
        # then verify a fresh-process resume does not reserve or spawn anything.
        while True:
            current = BATCH.status(os.fspath(self.run))
            if current["result"] == "complete":
                break
            next_item = BATCH.next_job(os.fspath(self.run))
            self.assertEqual(next_item["result"], "job_reserved")
            current_job_id = str(next_item["job_id"])
            current_route_id = self.job_route_id(next_item)
            current_task = f"returned-{next_item['role']}-{current_route_id}"
            current_spawn = self.spawn(next_item, current_task)
            BATCH.record_spawn(os.fspath(self.run), current_job_id, current_spawn, current_task)
            if next_item["role"] == "luna_draft":
                self.finish(next_item, current_task, self.draft_for(current_route_id))
            else:
                packet_path = self.run / "route-runs" / current_route_id / "review-packet.json"
                current_packet = json.loads(packet_path.read_text(encoding="utf-8"))
                self.finish(next_item, current_task, self.review_for(current_packet))
        self.assertEqual(current["jobs_completed"], 6)
        self.assertEqual({item["state"] for item in current["routes"]}, {"published"})
        db_after_publish = self.db.read_bytes()
        final_paths = self.index_files(self.run)
        completed_resume = BATCH.next_job(os.fspath(self.run))
        self.assertEqual(completed_resume["result"], "complete")
        self.assertEqual(completed_resume["status"]["jobs_completed"], 6)
        self.assertEqual(self.db.read_bytes(), db_after_publish)
        self.assertEqual(self.index_files(self.run), final_paths)

    def test_duplicate_or_out_of_batch_route_ids_refuse_before_creating_run(self):
        with self.assertRaisesRegex(BATCH.BatchError, "unique route fact IDs"):
            self.prepare([self.route_ids[0], self.route_ids[0]])
        self.assertFalse(self.run.exists())
        with self.assertRaisesRegex(BATCH.BatchError, "one to three unique route fact IDs"):
            BATCH.prepare(os.fspath(self.repo), os.fspath(self.db), [], os.fspath(self.run))
        self.assertFalse(self.run.exists())
        with self.assertRaisesRegex(BATCH.BatchError, "24-character lowercase hexadecimal"):
            self.prepare(["not-a-fact-id"])
        self.assertFalse(self.run.exists())
        with self.assertRaisesRegex(BATCH.BatchError, "selected ID is not one current route_action fact"):
            self.prepare(["0" * 24])
        self.assertFalse(self.run.exists())

    def test_empty_tampered_route_registry_and_database_inside_checkout_refuse(self):
        self.prepare()
        manifest_path = self.run / BATCH.MANIFEST
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["routes"] = []
        manifest_path.write_bytes(BATCH._canonical(manifest))
        before = self.index_files(self.run)
        db_before = self.db.read_bytes()
        with self.assertRaisesRegex(BATCH.BatchError, "batch route/job registry shape is invalid"):
            BATCH.status(os.fspath(self.run))
        self.assertEqual(self.index_files(self.run), before)
        self.assertEqual(self.db.read_bytes(), db_before)

        inside_db = self.repo / "nested-atlas.sqlite"
        inside_db.write_bytes(b"disposable sentinel")
        with self.assertRaisesRegex(BATCH.BatchError, "database must be an existing regular nonsymlink file|outside the target repository"):
            BATCH.prepare(os.fspath(self.repo), os.fspath(inside_db), [self.route_ids[0]],
                          os.fspath(self.atlas.root / "inside-db-batch"))
        self.assertEqual(inside_db.read_bytes(), b"disposable sentinel")

    def test_current_source_change_makes_saved_batch_stale_and_read_only(self):
        self.prepare()
        job = BATCH.next_job(os.fspath(self.run))
        self.assertEqual(job["result"], "job_reserved")
        source = self.repo / "Routes.cs"
        source.write_text(source.read_text(encoding="utf-8") + "// changed\n", encoding="utf-8")
        git(self.repo, "add", "--", "Routes.cs")
        before = self.index_files(self.run)
        db_before = self.db.read_bytes()
        with self.assertRaisesRegex(BATCH.BatchError, "no_saved_snapshot_matches_current_extractor_and_checkout"):
            BATCH.status(os.fspath(self.run))
        with self.assertRaises(BATCH.BatchError):
            BATCH.next_job(os.fspath(self.run))
        spawn = self.spawn(job, "returned-stale-task")
        with self.assertRaises(BATCH.BatchError):
            BATCH.record_spawn(os.fspath(self.run), job["job_id"], spawn, "returned-stale-task")
        self.assertEqual(self.index_files(self.run), before)
        self.assertEqual(self.db.read_bytes(), db_before)

    def test_malformed_completed_native_json_is_terminal_without_publication_or_respawn(self):
        self.prepare([self.route_ids[0]])
        job = BATCH.next_job(os.fspath(self.run))
        task_name = "returned-malformed-task"
        BATCH.record_spawn(os.fspath(self.run), job["job_id"], self.spawn(job, task_name), task_name)
        db_before = self.db.read_bytes()
        refused = BATCH.finish_job(
            os.fspath(self.run), job["job_id"],
            self.staged_observation(job, task_name, b"{not-json"),
        )
        self.assertEqual(refused["result"], "refused")
        self.assertIn("staged result is not one valid JSON object", refused["reason"])
        status = BATCH.status(os.fspath(self.run))
        self.assertEqual(status["result"], "complete")
        self.assertEqual(status["routes"], [{
            "route_fact_id": self.route_ids[0], "state": "refused", "current_route_result": "unmapped",
            "overlay_id": None,
        }])
        self.assertEqual(BATCH.next_job(os.fspath(self.run))["result"], "complete")
        self.assertEqual(self.db.read_bytes(), db_before)

    def test_staged_pointer_and_file_integrity_failures_are_terminal_and_read_only(self):
        valid = json.dumps(self.draft_for(self.route_ids[0]), separators=(",", ":")).encode("utf-8")
        cases = (
            ("absent", "staged result is missing, symlinked, nonregular, or exceeds the frozen response byte limit", "missing"),
            ("path", "native final pointer path is not the code-issued staged-result path", "path"),
            ("sha", "staged result byte count or SHA-256 does not match native pointer", "sha"),
            ("length", "staged result byte count or SHA-256 does not match native pointer", "length"),
            ("malformed", "staged result is not one valid JSON object", "malformed"),
            ("oversize", "staged result exceeds the frozen response byte limit", "oversize"),
            ("symlink", "batch tree contains a symlink", "symlink"),
        )
        original_run = self.run
        try:
            for label, diagnostic, mutation in cases:
                with self.subTest(case=label):
                    self.run = self.atlas.root / f"batch-stage-{label}"
                    self.prepare([self.route_ids[0]])
                    job = BATCH.next_job(os.fspath(self.run))
                    task_name = f"returned-stage-{label}"
                    BATCH.record_spawn(os.fspath(self.run), job["job_id"], self.spawn(job, task_name), task_name)
                    stage = Path(str(job["stage_path"]))
                    stage.parent.mkdir(parents=True, exist_ok=True)
                    if mutation == "malformed":
                        pointer_raw = b"{not-json"
                    elif mutation == "oversize":
                        pointer_raw = b'{"pad":"' + b"x" * (BATCH.MAX_BYTES_DEFAULT + 1) + b'"}'
                    else:
                        pointer_raw = valid
                    if mutation == "missing":
                        pass
                    elif mutation == "symlink":
                        target = self.run / "outside-stage-target.json"
                        target.write_bytes(valid)
                        stage.symlink_to(target)
                    else:
                        stage.write_bytes(pointer_raw)

                    kwargs = {}
                    if mutation == "path":
                        kwargs["path"] = os.fspath(self.run / "wrong-stage.json")
                    elif mutation == "sha":
                        kwargs["sha256"] = "0" * 64
                    elif mutation == "length":
                        kwargs["byte_count"] = len(pointer_raw) + 1
                    observation = self.pointer_observation(job, task_name, pointer_raw, **kwargs)
                    db_before = self.db.read_bytes()
                    if mutation in {"oversize", "symlink"}:
                        with self.assertRaisesRegex(BATCH.BatchError, diagnostic):
                            BATCH.finish_job(os.fspath(self.run), str(job["job_id"]), observation)
                        self.assertEqual(self.db.read_bytes(), db_before)
                        continue
                    refused = BATCH.finish_job(os.fspath(self.run), str(job["job_id"]), observation)
                    self.assertEqual(refused["result"], "refused")
                    self.assertIn(diagnostic, refused["reason"])
                    status = BATCH.status(os.fspath(self.run))
                    self.assertEqual(status["result"], "complete")
                    self.assertEqual(status["routes"][0]["state"], "refused")
                    self.assertEqual(self.db.read_bytes(), db_before)
                    self.assertEqual(BATCH.next_job(os.fspath(self.run))["result"], "complete")
        finally:
            self.run = original_run

    def test_unregistered_staged_artifact_is_rejected_before_status_or_publication(self):
        self.prepare([self.route_ids[0]])
        job = BATCH.next_job(os.fspath(self.run))
        stage = Path(str(job["stage_path"]))
        stage.parent.mkdir(parents=True, exist_ok=True)
        stage.write_bytes(b"{}")
        extra = self.run / "workers" / "unexpected.json"
        extra.write_bytes(b"unregistered")
        before = self.index_files(self.run)
        db_before = self.db.read_bytes()
        with self.assertRaisesRegex(BATCH.BatchError, "batch artifact set differs from manifest"):
            BATCH.status(os.fspath(self.run))
        self.assertEqual(self.index_files(self.run), before)
        self.assertEqual(self.db.read_bytes(), db_before)

    def test_sol_rejection_is_terminal_and_does_not_add_an_atlas_association(self):
        self.prepare([self.route_ids[0]])
        luna = BATCH.next_job(os.fspath(self.run))
        luna_name = "returned-luna-for-rejected-review"
        BATCH.record_spawn(os.fspath(self.run), luna["job_id"], self.spawn(luna, luna_name), luna_name)
        self.finish(luna, luna_name, self.draft_for(self.route_ids[0]))
        sol = BATCH.next_job(os.fspath(self.run))
        coord = self.run / "route-runs" / self.route_ids[0]
        packet = json.loads((coord / "review-packet.json").read_text(encoding="utf-8"))
        review = self.review_for(packet)
        review["decision"] = "rejected"
        review["assignment_review"]["decision"] = "rejected"
        review["conclusion_reviews"][0]["decision"] = "rejected"
        review["route_association_review"]["decision"] = "rejected"
        sol_name = "returned-sol-rejection"
        BATCH.record_spawn(os.fspath(self.run), sol["job_id"], self.spawn(sol, sol_name), sol_name)
        before_publish = self.db.read_bytes()
        result = self.finish(sol, sol_name, review)
        self.assertEqual(result["result"], "rejected")
        self.assertEqual(self.db.read_bytes(), before_publish)
        status = BATCH.status(os.fspath(self.run))
        self.assertEqual(status["result"], "complete")
        self.assertEqual(status["routes"][0]["state"], "rejected")
        self.assertEqual(self.db.read_bytes(), before_publish)
        self.assertEqual(BATCH.next_job(os.fspath(self.run))["result"], "complete")

    def test_interrupted_core_publication_resumes_saved_response_without_a_new_worker(self):
        self.prepare([self.route_ids[0]])
        luna = BATCH.next_job(os.fspath(self.run))
        luna_name = "returned-luna-before-publication-recovery"
        BATCH.record_spawn(os.fspath(self.run), luna["job_id"], self.spawn(luna, luna_name), luna_name)
        self.finish(luna, luna_name, self.draft_for(self.route_ids[0]))
        sol = BATCH.next_job(os.fspath(self.run))
        coord = self.run / "route-runs" / self.route_ids[0]
        packet = json.loads((coord / "review-packet.json").read_text(encoding="utf-8"))
        sol_name = "returned-sol-before-publication-recovery"
        BATCH.record_spawn(os.fspath(self.run), sol["job_id"], self.spawn(sol, sol_name), sol_name)
        final_bytes = json.dumps(self.review_for(packet), separators=(",", ":")).encode("utf-8")
        original_publish = BATCH.route_coordinator.publish

        def publish_then_interrupt(*args, **kwargs):
            original_publish(*args, **kwargs)
            raise RuntimeError("injected interruption after coordinator publication")

        BATCH.route_coordinator.publish = publish_then_interrupt
        try:
            with self.assertRaisesRegex(RuntimeError, "injected interruption"):
                BATCH.finish_job(os.fspath(self.run), sol["job_id"],
                                 self.staged_observation(sol, sol_name, final_bytes))
        finally:
            BATCH.route_coordinator.publish = original_publish

        interrupted = json.loads((self.run / BATCH.MANIFEST).read_text(encoding="utf-8"))
        self.assertEqual(interrupted["active_job_id"], sol["job_id"])
        self.assertEqual(interrupted["jobs"][-1]["state"], "coordinator_pending")
        self.assertEqual((self.run / interrupted["jobs"][-1]["answer_path"]).read_bytes(), final_bytes)
        db_after_first_publish = self.db.read_bytes()
        jobs_before_resume = len(interrupted["jobs"])
        resumed = BATCH.next_job(os.fspath(self.run))
        self.assertEqual(resumed["result"], "published_and_fresh")
        self.assertEqual(self.db.read_bytes(), db_after_first_publish)
        completed = json.loads((self.run / BATCH.MANIFEST).read_text(encoding="utf-8"))
        self.assertEqual(len(completed["jobs"]), jobs_before_resume)
        self.assertEqual(completed["jobs"][-1]["state"], "completed")
        self.assertEqual(BATCH.status(os.fspath(self.run))["routes"][0]["state"], "published")

    def test_rehashed_publish_receipt_identity_tampering_refuses_read_only(self):
        self.prepare([self.route_ids[0]])
        luna = BATCH.next_job(os.fspath(self.run))
        luna_name = "returned-luna-for-receipt-tamper"
        BATCH.record_spawn(os.fspath(self.run), luna["job_id"], self.spawn(luna, luna_name), luna_name)
        self.finish(luna, luna_name, self.draft_for(self.route_ids[0]))
        sol = BATCH.next_job(os.fspath(self.run))
        coord = self.run / "route-runs" / self.route_ids[0]
        packet = json.loads((coord / "review-packet.json").read_text(encoding="utf-8"))
        sol_name = "returned-sol-for-receipt-tamper"
        BATCH.record_spawn(os.fspath(self.run), sol["job_id"], self.spawn(sol, sol_name), sol_name)
        self.finish(sol, sol_name, self.review_for(packet))

        receipt_path = coord / "publish-result.json"
        coordinator_manifest_path = coord / BATCH.route_coordinator.MANIFEST
        original_receipt = receipt_path.read_bytes()
        original_coordinator_manifest = coordinator_manifest_path.read_bytes()
        base_receipt = json.loads(original_receipt)
        db_before = self.db.read_bytes()
        for field in ("packet_sha256", "receipt_hash", "binding_hash"):
            with self.subTest(field=field):
                self.assertIn(field, base_receipt)
                mutated = dict(base_receipt)
                mutated[field] = "0" * 64
                raw = BATCH.route_coordinator._json_bytes(mutated)
                receipt_path.write_bytes(raw)
                coordinator_manifest = json.loads(original_coordinator_manifest)
                coordinator_manifest["artifacts"]["publish-result.json"] = {
                    "sha256": BATCH._sha(raw), "bytes": len(raw),
                }
                BATCH.route_coordinator._write_manifest(coordinator_manifest_path, coordinator_manifest)
                before_status = self.index_files(self.run)
                with self.assertRaisesRegex(
                    BATCH.BatchError,
                    "current route association and publish receipt do not match the exact native review",
                ):
                    BATCH.status(os.fspath(self.run))
                self.assertEqual(self.index_files(self.run), before_status)
                self.assertEqual(self.db.read_bytes(), db_before)
                receipt_path.write_bytes(original_receipt)
                coordinator_manifest_path.write_bytes(original_coordinator_manifest)

    def test_captured_real_sol_json_stage_is_lossless_but_not_authority_for_fixture_packet(self):
        raw = CAPTURED_NATIVE_SOL_JSON.encode("utf-8")
        self.assertEqual(len(raw), 3748)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         "c6b789233267f2f943de54aeaa509ab4f437d32ad3a196e99f515cb358cb4d70")
        parsed_capture = json.loads(raw)
        self.assertEqual(parsed_capture["decision"], "accepted")
        self.assertEqual(len(parsed_capture["conclusion_reviews"]), 4)
        self.assertIn(b'[HttpPost(\\"~/api/admin/uploadLocationImage\\")]', raw)

        self.prepare([self.route_ids[0]])
        luna = BATCH.next_job(os.fspath(self.run))
        luna_name = "returned-luna-before-captured-sol"
        BATCH.record_spawn(os.fspath(self.run), luna["job_id"], self.spawn(luna, luna_name), luna_name)
        self.finish(luna, luna_name, self.draft_for(self.route_ids[0]))
        sol = BATCH.next_job(os.fspath(self.run))
        sol_name = "returned-sol-captured-case"
        BATCH.record_spawn(os.fspath(self.run), sol["job_id"], self.spawn(sol, sol_name), sol_name)
        observation = self.staged_observation(sol, sol_name, raw)
        db_before = self.db.read_bytes()
        result = BATCH.finish_job(os.fspath(self.run), sol["job_id"], observation)
        self.assertEqual(result["result"], "refused")
        self.assertIn("does not match the exact complete-evidence/draft packet", result["reason"])
        job = json.loads((self.run / BATCH.MANIFEST).read_text(encoding="utf-8"))["jobs"][-1]
        self.assertEqual(Path(sol["stage_path"]).read_bytes(), raw)
        self.assertEqual((self.run / job["answer_path"]).read_bytes(), raw)
        self.assertEqual(job["state"], "refused")
        self.assertEqual(self.db.read_bytes(), db_before)


if __name__ == "__main__":
    unittest.main()
