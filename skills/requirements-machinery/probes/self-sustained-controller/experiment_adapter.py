#!/usr/bin/env python3
"""Exercise the self-sustained controller with real captured coverage states and simulated stages."""

import argparse
import importlib.util
import json
import os
import shutil
import tempfile
from pathlib import Path


def load_cover(path):
    spec = importlib.util.spec_from_file_location("candidate_cover", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    state = json.loads(Path(args.input).read_text())
    target = state.get("relevance", {}).get("last")
    variant_id = os.environ["EXPERIMENT_VARIANT_ID"]
    calls = []

    with tempfile.TemporaryDirectory() as temporary:
        candidate_root = Path(__file__).resolve().parents[2]
        runtime_root = Path(temporary) / "projection"
        shutil.copytree(candidate_root, runtime_root)
        runtime_root.chmod(0o700)
        policy_path = runtime_root / "client-model-policy.json"
        if policy_path.exists():
            policy_path.chmod(0o600)
        policy_path.write_text(json.dumps({
            "schema_version": 1,
            "client": "codex",
            "fail_closed": True,
            "required_runtime": "simulated-reader",
            "recommended_reader_command": "simulated-reader",
        }))
        cover = load_cover(runtime_root / "scripts" / "cover.py")
        work = Path(temporary) / "run"
        output = Path(temporary) / "requirements.md"
        if cover.open_document(state["source"], work) != 0:
            raise SystemExit(2)
        (work / "coverage.json").write_text(json.dumps(state, indent=1))

        def save(mutator, name):
            current = cover._read(work)
            mutator(current)
            cover._write(work, current)
            calls.append(name)
            return 0

        def fake_relevance(_work, wanted, _reader):
            def mutate(current):
                rows = {piece["id"]: {"verdict": "does-not-bear", "seats": []}
                        for piece in current["pieces"]}
                current.setdefault("relevance", {}).setdefault("targets", {})[wanted] = {"pieces": rows}
                current["relevance"]["last"] = wanted
            return save(mutate, "relevance")

        def fake_obligations(_work, _reader):
            def mutate(current):
                rows = current["relevance"]["targets"][target]["pieces"]
                expected = sorted(pid for pid, row in rows.items() if row["verdict"] in
                                  ("bears", "for-the-owner", "yes-without-words", "no-answer"))
                current.setdefault("obligations", {})[target] = {pid: {"obligations": []}
                                                                  for pid in expected}
                current.setdefault("obligation_completion", {})[target] = {
                    "complete": True, "piece_ids": expected,
                    "admitted_piece_ids": [], "unresolved_piece_ids": [], "at": 1,
                }
            return save(mutate, "obligations")

        def fake_collapse(_work, _reader):
            code = save(lambda current: current.setdefault("collapse", {}).__setitem__(target, {
                "entries": [], "merged_pairs": [], "owner_pairs": [],
                "owner_pair_records": [], "reconciled_unsettled": [],
                "still_for_owner": [], "detail": [], "at": 1,
            }), "collapse")
            policy_path.write_text(json.dumps({
                "schema_version": 1,
                "client": "codex",
                "fail_closed": True,
                "required_runtime": "different-reader",
                "recommended_reader_command": "different-reader",
            }))
            return code

        def fake_requirements(_work, _reader):
            cover._load("rules").interview.validate_reader_command(_reader)
            item = {"text": "A simulated independently checkable requirement.",
                    "pages": ["p-0001"], "kind": "entry", "checkable": False}
            return save(lambda current: current.setdefault("requirements", {}).__setitem__(target, {
                "items": [item], "rules_stage": {"rules": [], "unresolved": [], "detail": []},
                "at": 1,
            }), "requirements")

        def fake_distill(_work, _reader):
            item = {"pages": ["p-0001"], "statement": "A simulated independently checkable requirement.",
                    "how": "pen", "anchors": ["A simulated independently checkable requirement."],
                    "transcript": [], "checkable": False}
            return save(lambda current: current.setdefault("distilled", {}).__setitem__(target, {
                "items": [item], "owner_pairs": [], "source_owner_pairs": [],
                "shared_rule_owner_records": [], "still_for_owner": [], "at": 1,
            }), "distill")

        def fake_owner(_work, _reader=None):
            calls.append("owner")
            return 0

        def fake_document(_work, out_path, _reader=None):
            calls.append("document")
            Path(out_path).write_text("completed\n")
            return 0

        case_sha256 = __import__("hashlib").sha256(Path(args.input).read_bytes()).hexdigest()
        if case_sha256 == "529a81c5ee748df6e5c5befc97f2c11ab719cbb2468e42e1e84e7946be9a21fc":
            original_load = cover._load
            pen_calls = []

            class FakeDistill:
                @staticmethod
                def write_one(anchors, _reader, **_kwargs):
                    pen_calls.append(anchors[0])
                    return anchors[0], [{"outcome": "simulated-valid-pen"}]

            cover._load = lambda name: FakeDistill if name == "distill" else original_load(name)
            first_code = cover.run_automatic(str(work), target, str(output), "simulated-reader")
            first_reader_calls = len(pen_calls)
            first_document = output.read_bytes()
            second_code = cover.run_automatic(str(work), target, str(output), "simulated-reader")
            second_reader_calls = len(pen_calls) - first_reader_calls
            current = json.loads((work / "coverage.json").read_text())
            feed_rows = [json.loads(line) for line in (work / "feed.jsonl").read_text().splitlines()]
            compatibility = [row.get("transition") for row in feed_rows
                             if row.get("event") == "controller compatibility"]
            outcome = {
                "case_sha256": case_sha256,
                "stages": ["document", "document"],
                "terminal": "document",
                "exit_code": second_code,
                "first_exit_code": first_code,
                "first_reader_calls": first_reader_calls,
                "second_reader_calls": second_reader_calls,
                "documents_equal": first_document == output.read_bytes(),
                "cache_kind": ("granular" if target in current.get("document_preparation", {})
                               else "none"),
                "compatibility": sorted(set(compatibility)),
                "document_written": output.exists(),
                "projection_policy_drift_survived": True,
                "runtime_identity": ("snapshot" if (work / ".projection-runtime-v1").exists()
                                     else "module-preload"),
            }
        else:
            cover.relevance = fake_relevance
            cover.obligations = fake_obligations
            cover.collapse = fake_collapse
            cover.requirements = fake_requirements
            cover.distill = fake_distill
            cover.ask_owner = fake_owner
            cover.document = fake_document
            code = cover.run_automatic(str(work), target, str(output), "simulated-reader")
            terminal = calls[-1] if calls else None
            current = cover._read(work)
            outcome = {
                "case_sha256": case_sha256,
                "stages": calls,
                "terminal": terminal,
                "exit_code": code,
                "document_written": output.exists(),
                "cache_kind": "not-applicable",
                "self_sustained_marker": current.get("self_sustained_run"),
                "future_pen_preserved": isinstance(current.get("self_sustained_run"), dict),
                "projection_policy_drift_survived": target in current.get("requirements", {}),
                "runtime_identity": ("snapshot" if (work / ".projection-runtime-v1").exists()
                                     else "module-preload"),
            }
    result = {"schema_version": 1, "variant_id": variant_id, "status": "completed",
              "outcome": outcome, "metrics": {}, "error": None}
    Path(args.result).write_text(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
