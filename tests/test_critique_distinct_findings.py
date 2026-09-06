"""Captured roadmap owner-measurement findings, experiment03 reader1.

Two actual independent findings retained: comparative measurement and approval.
Producer excerpts are verbatim; their line coordinates are rebased within excerpts.
No source text, reason, or consequence is invented by this fixture.
"""
from __future__ import annotations
import copy
import importlib.util
import json
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]
UNIT = {'anchor_score': 93, 'label': 'Owner control message test', 'payload_paths': ['$.activation_cards[1]'], 'payload_sha256': '5ae825e38294fae70c2ea7de258455c2824291843d14d4ecf04f8af7d7bc4cb3', 'territory_blocks': [22, 23, 24, 25, 26, 27], 'territory_sha256': '0a6e1bf1c7706a4286927dc0094a9b903037ea7bb963efd253d1b8c5458e90ed', 'text': "### Owner control message test\n\n**Insight.** Elena's preference for control and visibility is a strong hypothesis, but it is not settled buyer truth until owners compare the messages.\n\n**Idea.** Test a control-led message against an AI-capability message, both anchored in The Stop Line.\n\n**Engagement — the mechanic.** Owners react to plain-language options that show visibility, ownership and early risk detection without asking them to become technical buyers.\n\n**Desired outcome.** The B Team learns whether control should lead owner-facing communication before scaling the message.  ·  **Targets.** In Month 3, read the Launch message with the owner and get their written confirmation that it reflects their preference, is easy to understand, builds trust and supports the meeting’s purpose before it is sent.  ·  **Approver.** Kamen Kamenov\n\n**Signature.** Restraint is the proof.  ·  **KPI.** Owner message preference — percentage, Owner message-test preference report · Plain-language comprehension — 1-5 score, Owner comprehension rubric · Meeting intent after message exposure — percentage, Owner test intent register  ·  **Month.** 3", 'unit_id': 'u-007-d8edfee5'}
SOURCES = [{'source_id': 'measurement-framework', 'text': 'Owner control comprehension\n\nIncrease understanding among owners of midsize businesses that The Stop Line gives more control and visibility.\n\nMeasures the share of sampled owners who correctly explain that The Stop Line shows proof, senior responsibility and the limit the system will not cross.\n\nBaseline not established; it will be set in the first owner message test before launch.\n\nThe target is set in the same test after the baseline is read.\n\nThe target assumes message-testing budget, owner recruitment, approved test copy and a plain-language scoring guide.\n\nUnited Partners controls the test design and scoring, while owner understanding depends on sample quality and the clarity of approved claims.\n\nOwner message test.\n\nAfter each message-testing wave.\n\nUP account lead.\n\nBy market, owner profile, message route and explanation quality.\n\nChange is described as contributed to only when the test compares The Stop Line against a defined alternative message in the same wave.', 'value_sha256': '1b6dc88e2b5bf074d29afa2269e16f00a6325c7b1dbb6ac686e410b1071f19c6'}, {'source_id': 'execution-toolkit', 'text': 'Before anything publishes, Kamen Kamenov gives final sign-off on positioning, proof lane, claims and public references. Matthew Maday gives technical confirmation for claim-level and AI-language approvals before release.', 'value_sha256': 'cd65a8d0271f2e1b70a688d3e7963d166a9afa2093c4a5f4e8e07618fd13e738'}]
REPLY = {'judgments': [{'end_line': 11, 'findings': [{'end_line': 9, 'practical_consequence': "A single owner's confirmation of one Launch message cannot establish the comparative owner preference that the test is meant to measure, so the team could scale the control-led message without the required comparison evidence.", 'reason': 'The target operationalizes the test as reading one Launch message with "the owner" and obtaining written confirmation, while the producer commitment requires sampled owners to compare The Stop Line against a defined alternative message in the same wave.', 'source_end_line': 23, 'source_id': 'measurement-framework', 'source_start_line': 1, 'start_line': 9}, {'end_line': 9, 'practical_consequence': 'AI-capability test copy could be sent with only positioning approval and without the required technical confirmation of its AI language.', 'reason': "The unit names Kamen Kamenov as the sole approver even though the producer source requires Matthew Maday's technical confirmation for claim-level and AI-language approvals before release.", 'source_end_line': 1, 'source_id': 'execution-toolkit', 'source_start_line': 1, 'start_line': 9}], 'lens': 'upstream-trace', 'source_end_line': 1, 'source_id': 'execution-toolkit', 'source_start_line': 1, 'start_line': 5, 'verdict': 'revise'}]}

@pytest.fixture
def critic():
    spec = importlib.util.spec_from_file_location("distinct_critique", ROOT / "skills/critique-machinery/scripts/critique.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

@pytest.fixture
def work(critic, tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    tmp_path = tmp_path / "work"
    tmp_path.mkdir()
    (tmp_path / "sources.json").write_text(json.dumps({"sources": SOURCES}))
    cell = {"cell_id":"captured-upstream", "unit_id":UNIT["unit_id"], "lens":"upstream-trace", "readers":{}, "status":"unjudged", "outcome":"pending"}
    manifest = {"units":[UNIT], "page":{"sha256":critic.digest_bytes(UNIT["text"].encode())}}
    matrix = {"cells":[cell], "lenses":["upstream-trace"]}
    (tmp_path / "matrix.json").write_text(json.dumps(matrix))
    def load(path):
        return manifest, json.loads((path / "matrix.json").read_text())
    monkeypatch.setattr(critic, "load_matrix", load)
    return tmp_path

def read(critic, work, seat, changes=None):
    reply = copy.deepcopy(REPLY)
    if changes:
        changes(reply["judgments"][0])
    evidence = work / "reader-evidence" / "captured" / seat / "attempt-001"
    evidence.mkdir(parents=True)
    result = critic.classify_reader_reply(json.dumps(reply), critic.reader_schema(["upstream-trace"]), ["upstream-trace"],
        batch_id="captured", seat=seat, attempt=1, evidence_path=str(evidence))
    result = critic.ground_reader_result(result, UNIT, SOURCES)
    (evidence / "reader-response.json").write_text(json.dumps({"judgments":result["judgments"]}))
    return critic._claims_from_reader_result(result, ["upstream-trace"])["upstream-trace"]

def test_captured_two_findings_survive_intake_state_and_completed_outputs(critic, work):
    claims = {seat:read(critic, work, seat) for seat in critic.READER_SEATS}
    cell = critic.record_cell_readers(work, "captured-upstream", claims)
    assert cell["outcome"] == "agreement-defect"
    assert all(len(reader["findings"]) == 2 for reader in cell["readers"].values())
    report = critic.reporting_route(work, "report")
    inventory = report["finding_inventory"]
    assert len(inventory["evidence_identical_groups"]) == 2
    assert inventory["independent_repair_count"] is None
    assert all(len(item["observations"]) == 2 for item in inventory["evidence_identical_groups"])
    document = critic.reporting_route(work, "document")
    text = Path(document["path"]).read_text()
    located = critic.located(work, "all")
    for finding in REPLY["judgments"][0]["findings"]:
        assert finding["reason"] in text and finding["practical_consequence"] in text
        assert finding["reason"] in located and finding["practical_consequence"] in located

def test_five_identical_lens_observations_are_not_five_repairs(critic, work):
    cells=[]
    for lens in ["buyer-read", "cfo", "journalist", "employee-insider", "upstream-trace"]:
        cell={"cell_id":lens,"lens":lens,"unit_id":UNIT["unit_id"],"status":"unjudged","outcome":"pending","readers":{}}
        for seat in critic.READER_SEATS:
            raw=copy.deepcopy(REPLY);raw["judgments"][0]["lens"]=lens
            if lens != "upstream-trace":
                for key in ("source_id","source_start_line","source_end_line"):
                    raw["judgments"][0].pop(key)
            result=critic.classify_reader_reply(json.dumps(raw),critic.reader_schema([lens]),[lens],batch_id=lens,seat=seat,attempt=1,evidence_path="captured")
            assert result["outcome"]=="valid"
            result=critic.ground_reader_result(result,UNIT,SOURCES)
            claim=critic._claims_from_reader_result(result,[lens])[lens]
            critic._apply_reader_claim(work,{"units":[UNIT]},cell,seat,claim["verdict"],claim["quote"],claim.get("source_id"),claim.get("source_quote"),claim["intake"],claim["findings"])
        cells.append(cell)
    items=critic.distinct_findings({"cells":cells})
    assert len(items)==2
    assert all(len(item["observations"])==10 for item in items)
    assert {item["reason"] for item in items} == {item["reason"] for item in REPLY["judgments"][0]["findings"]}

def test_same_verdict_different_findings_requires_owner(critic, work):
    claims={"reader-1":read(critic,work,"reader-1"), "reader-2":read(critic,work,"reader-2",lambda j:j.update(findings=j["findings"][:1]))}
    cell=critic.record_cell_readers(work,"captured-upstream",claims)
    assert cell["outcome"]=="disagreement" and cell["status"]=="unresolved"
    assert len(critic.owner_queue(work)["question"]["reader_evidence"]["reader-1"]["findings"])==2
    with pytest.raises(critic.Refusal,match="owner questions"):
        critic.reporting_route(work,"document")

def test_ungrounded_second_finding_is_preserved_and_blocks_completion(critic,work):
    def break_second(j):j["findings"][1]["source_end_line"]=999999
    claims={seat:read(critic,work,seat,break_second) for seat in critic.READER_SEATS}
    cell=critic.record_cell_readers(work,"captured-upstream",claims)
    assert cell["status"]=="unresolved"
    for reader in cell["readers"].values():
        assert [item["status"] for item in reader["findings"]]==["grounded","ungrounded"]
        assert "invalid producer" in reader["findings"][1]["claim_error"]
    assert critic.owner_queue(work)["open_count"]==1
    assert REPLY["judgments"][0]["findings"][1]["reason"] in critic.located(work,"all")

def test_clear_cannot_hide_findings_and_defect_cannot_be_empty(critic):
    for verdict,findings in [("clear",REPLY["judgments"][0]["findings"]),("revise",[])]:
        reply=copy.deepcopy(REPLY);reply["judgments"][0].update(verdict=verdict,findings=findings)
        result=critic.classify_reader_reply(json.dumps(reply),critic.reader_schema(["upstream-trace"]),["upstream-trace"],batch_id="captured",seat="reader-1",attempt=1,evidence_path="captured")
        assert result["outcome"]=="malformed"

def test_owner_grouping_keeps_all_evidence_and_rejects_unknown_ids(critic,work):
    # This is a recording-mechanism test, not an owner adjudication of the captured issues.
    claims={seat:read(critic,work,seat) for seat in critic.READER_SEATS}
    critic.record_cell_readers(work,"captured-upstream",claims)
    _,matrix=critic.load_matrix(work);ids=[item["finding_id"] for item in critic.distinct_findings(matrix)]
    with pytest.raises(critic.Refusal,match="grounded finding IDs"):
        critic.group_findings(work,[ids[0],"unknown"],"Test recording only")
    assert not (work/"owner-finding-groups.json").exists()
    # Do not invent an owner ruling for two genuinely different captured problems.
    assert len(critic.finding_inventory(work,matrix)["evidence_identical_groups"])==2

def test_owner_group_recording_preserves_observations_and_never_resolves_verdict(critic, work):
    # Exercise only explicit owner-input storage with captured grounded evidence.
    # The fixture decision is not an adjudication of this roadmap or a quality win.
    claims={seat:read(critic,work,seat) for seat in critic.READER_SEATS}
    critic.record_cell_readers(work,"captured-upstream",claims)
    _,before=critic.load_matrix(work)
    ids=[item["finding_id"] for item in critic.distinct_findings(before)]
    decision=critic.group_findings(work,ids,"Fixture owner-input storage check; no live adjudication")
    _,after=critic.load_matrix(work)
    assert before==after
    inventory=critic.finding_inventory(work,after)
    assert inventory["owner_confirmed_groups"]==[decision]
    assert len(inventory["evidence_identical_groups"])==2
    assert sum(len(item["observations"]) for item in inventory["evidence_identical_groups"])==4
    assert inventory["independent_repair_count"] is None
    with pytest.raises(critic.Refusal,match="already has an owner grouping"):
        critic.group_findings(work,ids,"Fixture duplicate decision")
