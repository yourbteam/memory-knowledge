"""Runtime regressions captured from technical-approval in the real roadmap study.

Unit is verbatim; producer excerpt retains the first three original source lines.
Captured input SHA256: e41dfb09acaa31421d46cca7fa7454a1a6d139564206ee2cd88727a5ca5efc9c
"""
from __future__ import annotations
import copy
import importlib.util
import itertools
import json
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]
UNIT = {'unit_id': 'u-011-7c949da8', 'text': '### Technical proof story\n\n**Insight.** Technical buyers need evidence that AI supports delivery without taking ownership away from senior people.\n\n**Idea.** Publish a technical proof story under The Stop Line showing the claim, proof type, senior owner and stated limit behind an AI-supported delivery example.\n\n**Engagement — the mechanic.** Technical buyers inspect the artifact and see what is confirmed, what is not claimed and who signs the boundary.\n\n**Desired outcome.** Technical trust grows without turning The Stop Line into an unbounded AI capability pitch.  ·  **Targets.** Read in Month 7 for artifact views, sales use and qualified technical conversations.  ·  **Approver.** Matthew Maday\n\n**Signature.** The Stop Line  ·  **KPI.** Technical artifact views — count, Technical artifact analytics report · Sales use of technical proof — count, Sales proof-use register · Qualified technical conversations — count, Technical buyer conversation log  ·  **Months.** 7 to 12'}
SOURCES = [{'source_id': 'communications-platform', 'text': 'The Stop Line\n\nThe B Team can own this platform if it makes restraint visible through approved proof, named senior responsibility and clear limits before any artificial intelligence claim reaches the market.'}]

@pytest.fixture
def critic():
    spec = importlib.util.spec_from_file_location("critique_runtime", ROOT / "skills/critique-machinery/scripts/critique.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def strict_objects(node):
    if isinstance(node, dict):
        if node.get("type") == "object":
            assert set(node["required"]) == set(node["properties"])
            assert node["additionalProperties"] is False
        for child in node.values():
            strict_objects(child)
    elif isinstance(node, list):
        for child in node:
            strict_objects(child)

def test_all_lens_subsets_have_strict_complete_object_schemas(critic):
    count = 0
    for size in range(1, len(critic.LENSES) + 1):
        for lenses in itertools.combinations(critic.LENSES, size):
            strict_objects(critic.reader_schema(list(lenses)))
            count += 1
    assert count == 255

def reply(critic, **changes):
    item = {"lens": "upstream-trace", "verdict": "clear", "start_line": 1, "end_line": 3,
            "source_id": None, "source_start_line": None, "source_end_line": None, "findings": []}
    item.update(changes)
    if item["verdict"] in {"revise", "reject"}:
        item["findings"] = [{"start_line": item["start_line"], "end_line": item["end_line"],
            "source_id": item["source_id"], "source_start_line": item["source_start_line"], "source_end_line": item["source_end_line"],
            "reason": "Runtime citation validation probe on captured source", "practical_consequence": "An ungrounded claim must remain unresolved"}]
    return critic.classify_reader_reply(json.dumps({"judgments": [item]}),
        critic.reader_schema(["upstream-trace"]), ["upstream-trace"],
        batch_id="technical-approval", seat="reader-1", attempt=1, evidence_path="captured-test")

def test_null_clear_and_exact_real_source_are_grounded(critic):
    result = critic.ground_reader_result(reply(critic), UNIT, SOURCES)
    assert result["outcome"] == "valid"
    assert "claim_error" not in result["judgments"][0]
    assert result["judgments"][0]["quote"] == "\n".join(UNIT["text"].splitlines()[:3])
    source = SOURCES[0]
    result = critic.ground_reader_result(reply(critic, verdict="revise", source_id=source["source_id"],
        source_start_line=3, source_end_line=3), UNIT, SOURCES)
    assert result["judgments"][0]["source_quote"] == source["text"].splitlines()[2]

@pytest.mark.parametrize("changes", [
    {"source_id": 42}, {"source_start_line": True}, {"source_end_line": "3"},
])
def test_wrong_citation_types_are_malformed(critic, changes):
    assert reply(critic, verdict="revise", **changes)["outcome"] == "malformed"

def test_omitted_source_fields_are_malformed(critic):
    schema = critic.reader_schema(["upstream-trace"])
    data = {"judgments": [{"lens":"upstream-trace", "verdict":"clear", "start_line":1, "end_line":3, "findings":[]}]}
    errors = critic._schema_problems(schema, data)
    assert len(errors) == 3
    assert all("is missing" in error for error in errors)

@pytest.mark.parametrize("changes", [
    {}, {"source_id": "unregistered", "source_start_line": 1, "source_end_line": 3},
    {"source_id": "communications-platform", "source_start_line": 1, "source_end_line": 999999},
])
def test_invalid_defect_citations_do_not_ground(critic, changes):
    result = critic.ground_reader_result(reply(critic, verdict="revise", **changes), UNIT, SOURCES)
    assert result["judgments"][0]["source_quote"] is None
    assert "invalid producer source/span" in result["judgments"][0]["claim_error"]

def test_missing_defect_citation_is_refused_by_durable_claim(critic, tmp_path):
    result = critic.ground_reader_result(reply(critic, verdict="revise"), UNIT, SOURCES)
    cell = {"cell_id":"captured-upstream", "unit_id":UNIT["unit_id"], "lens":"upstream-trace",
            "readers":{}, "status":"unresolved"}
    with pytest.raises(critic.Refusal, match="no producer evidence"):
        critic._apply_reader_claim(tmp_path, {"units":[UNIT]}, cell, "reader-1", "revise", result["judgments"][0]["quote"])

@pytest.mark.parametrize("from_environment", [False, True])
def test_relative_evidence_paths_resolve_before_isolated_reader(critic, tmp_path, monkeypatch, from_environment):
    projection = tmp_path / "projection"
    (projection / "scripts").mkdir(parents=True)
    (projection / "client-model-policy.json").write_text(json.dumps({"required_runtime":"codex exec", "fail_closed":True}))
    monkeypatch.setattr(critic, "__file__", str(projection / "scripts/critique.py"))
    monkeypatch.setattr(critic.shutil, "which", lambda client: "/captured/codex")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EXPERIMENT_RESULT_PATH", "relative/evidence/result.json")
    class Inspected(Exception): pass
    observed = []
    def inspect(argv, **kwargs):
        schema = Path(argv[argv.index("--output-schema") + 1])
        reply_path = Path(argv[argv.index("--output-last-message") + 1])
        assert schema.is_absolute() and reply_path.is_absolute()
        assert schema.is_file()
        assert schema.parent == (tmp_path / "relative/evidence").resolve()
        assert Path(kwargs["cwd"]) != tmp_path
        observed.append(argv)
        raise Inspected()
    monkeypatch.setattr(critic.subprocess, "run", inspect)
    with pytest.raises(Inspected):
        critic._reader_judgments(Path("relative"), "Captured roadmap", "Inspect upstream commitments", UNIT,
            ["upstream-trace"], evidence_root=None if from_environment else Path("relative/evidence"),
            upstream_sources=SOURCES, batch_id="technical-approval", seat="reader-1")
    assert len(observed) == 1
