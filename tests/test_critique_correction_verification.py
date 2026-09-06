"""Correction receipt boundaries with captured real finding/source text.

Reader verdicts below are test controls for receipt mechanics, not quality evidence.
Live renderer-produced success/failure cases are validated by the atom experiment.
"""
from __future__ import annotations
import copy
import importlib.util
import json
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
UNIT = {'anchor_score': 93, 'label': 'Owner control message test', 'payload_paths': ['$.activation_cards[1]'], 'payload_sha256': '5ae825e38294fae70c2ea7de258455c2824291843d14d4ecf04f8af7d7bc4cb3', 'territory_blocks': [22, 23, 24, 25, 26, 27], 'territory_sha256': '0a6e1bf1c7706a4286927dc0094a9b903037ea7bb963efd253d1b8c5458e90ed', 'text': "### Owner control message test\n\n**Insight.** Elena's preference for control and visibility is a strong hypothesis, but it is not settled buyer truth until owners compare the messages.\n\n**Idea.** Test a control-led message against an AI-capability message, both anchored in The Stop Line.\n\n**Engagement — the mechanic.** Owners react to plain-language options that show visibility, ownership and early risk detection without asking them to become technical buyers.\n\n**Desired outcome.** The B Team learns whether control should lead owner-facing communication before scaling the message.  ·  **Targets.** In Month 3, read the Launch message with the owner and get their written confirmation that it reflects their preference, is easy to understand, builds trust and supports the meeting’s purpose before it is sent.  ·  **Approver.** Kamen Kamenov\n\n**Signature.** Restraint is the proof.  ·  **KPI.** Owner message preference — percentage, Owner message-test preference report · Plain-language comprehension — 1-5 score, Owner comprehension rubric · Meeting intent after message exposure — percentage, Owner test intent register  ·  **Month.** 3", 'unit_id': 'u-007-d8edfee5'}
SOURCES = [{'source_id': 'measurement-framework', 'text': 'Owner control comprehension\n\nIncrease understanding among owners of midsize businesses that The Stop Line gives more control and visibility.\n\nMeasures the share of sampled owners who correctly explain that The Stop Line shows proof, senior responsibility and the limit the system will not cross.\n\nBaseline not established; it will be set in the first owner message test before launch.\n\nThe target is set in the same test after the baseline is read.\n\nThe target assumes message-testing budget, owner recruitment, approved test copy and a plain-language scoring guide.\n\nUnited Partners controls the test design and scoring, while owner understanding depends on sample quality and the clarity of approved claims.\n\nOwner message test.\n\nAfter each message-testing wave.\n\nUP account lead.\n\nBy market, owner profile, message route and explanation quality.\n\nChange is described as contributed to only when the test compares The Stop Line against a defined alternative message in the same wave.', 'value_sha256': '1b6dc88e2b5bf074d29afa2269e16f00a6325c7b1dbb6ac686e410b1071f19c6'}, {'source_id': 'execution-toolkit', 'text': 'Before anything publishes, Kamen Kamenov gives final sign-off on positioning, proof lane, claims and public references. Matthew Maday gives technical confirmation for claim-level and AI-language approvals before release.', 'value_sha256': 'cd65a8d0271f2e1b70a688d3e7963d166a9afa2093c4a5f4e8e07618fd13e738'}]
REPLY = {'judgments': [{'end_line': 11, 'findings': [{'end_line': 9, 'practical_consequence': "A single owner's confirmation of one Launch message cannot establish the comparative owner preference that the test is meant to measure, so the team could scale the control-led message without the required comparison evidence.", 'reason': 'The target operationalizes the test as reading one Launch message with "the owner" and obtaining written confirmation, while the producer commitment requires sampled owners to compare The Stop Line against a defined alternative message in the same wave.', 'source_end_line': 23, 'source_id': 'measurement-framework', 'source_start_line': 1, 'start_line': 9}, {'end_line': 9, 'practical_consequence': 'AI-capability test copy could be sent with only positioning approval and without the required technical confirmation of its AI language.', 'reason': "The unit names Kamen Kamenov as the sole approver even though the producer source requires Matthew Maday's technical confirmation for claim-level and AI-language approvals before release.", 'source_end_line': 1, 'source_id': 'execution-toolkit', 'source_start_line': 1, 'start_line': 9}], 'lens': 'upstream-trace', 'source_end_line': 1, 'source_id': 'execution-toolkit', 'source_start_line': 1, 'start_line': 5, 'verdict': 'revise'}]}

@pytest.fixture
def critic():
    spec=importlib.util.spec_from_file_location("critique_correction",ROOT/"skills/critique-machinery/scripts/critique.py")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

@pytest.fixture
def runs(critic,tmp_path):
    (tmp_path/".git").mkdir()
    def opened(name,changed_sources=False):
        page_text=UNIT["text"] + ("\n\n" + SOURCES[1]["text"] if name=="after" else "")
        page=tmp_path/f"{name}.md";page.write_text(page_text)
        state=tmp_path/f"{name}.json"
        source_values={source["source_id"]:{"text":source["text"]} for source in SOURCES}
        if changed_sources:source_values[SOURCES[0]["source_id"]]["extra"]=SOURCES[1]["text"]
        state.write_text(json.dumps({"payload":{"rendered":page_text},"sources":source_values}))
        work=tmp_path/name
        _,manifest=critic.open_run(page,state,"payload",work,no_reference="Runtime receipt test supplies no benchmark",
            upstream_sources=[(source["source_id"],state,"sources."+source["source_id"]) for source in SOURCES])
        return work,manifest
    before,bm=opened("before");after,am=opened("after")
    claims={}
    for seat in critic.READER_SEATS:
        result=critic.classify_reader_reply(json.dumps(REPLY),critic.reader_schema(["upstream-trace"]),["upstream-trace"],batch_id="captured",seat=seat,attempt=1,evidence_path="captured")
        result=critic.ground_reader_result(result,bm["units"][0],critic.upstream_sources_for_run(before,bm))
        claims[seat]=critic._claims_from_reader_result(result,["upstream-trace"])["upstream-trace"]
    cell=critic.record_cell_readers(before,bm["units"][0]["unit_id"]+"::upstream-trace",claims)
    finding=cell["readers"]["reader-1"]["findings"][1]
    assert finding["status"]=="grounded"
    return before,after,am["units"][0]["unit_id"],finding,opened

def tree_hashes(critic,root):return {str(p.relative_to(root)):critic.digest_file(p) for p in root.rglob("*") if p.is_file()}

@pytest.mark.parametrize("responses,status",[( ["clear","clear"],"corrected"),(["revise","revise"],"not-corrected"),(["clear","revise"],"cannot-assess"),(["timeout","clear"],"cannot-assess"),(["ungrounded","clear"],"cannot-assess")])
def test_scoped_receipt_preserves_other_findings_and_both_runs(critic,runs,tmp_path,monkeypatch,responses,status):
    before,after,unit_id,finding,_=runs
    before_hashes=tree_hashes(critic,before);after_hashes=tree_hashes(critic,after)
    observed=[]
    def reader(root,context,focus,unit,lenses,**kwargs):
        observed.append(kwargs)
        assert kwargs["finding_scope"]["finding_id"]==finding["finding_id"]
        assert kwargs["artifact_context"]["scope"]=="complete-delivered-artifact-and-bound-payload"
        verdict="revise" if kwargs["finding_scope"]["evaluation_phase"]=="before" else responses[len(observed)-3]
        if verdict=="timeout":
            return critic.classify_reader_reply(b"",critic.reader_schema(lenses),lenses,batch_id=kwargs["batch_id"],seat=kwargs["seat"],attempt=1,evidence_path=str(kwargs["evidence_root"]),forced_outcome="timeout")
        raw=copy.deepcopy(REPLY);j=raw["judgments"][0]
        j["verdict"]="clear" if verdict=="clear" else "revise"
        j["findings"]=[] if verdict=="clear" else [j["findings"][1]]
        if verdict=="clear":
            for key in ["source_id","source_start_line","source_end_line"]:j[key]=None
        if verdict=="ungrounded":j["findings"][0]["source_end_line"]=999999
        result=critic.classify_reader_reply(json.dumps(raw),critic.reader_schema(lenses),lenses,batch_id=kwargs["batch_id"],seat=kwargs["seat"],attempt=1,evidence_path=str(kwargs["evidence_root"]))
        return critic.ground_reader_result(result,unit,kwargs["upstream_sources"])
    monkeypatch.setattr(critic,"_reader_judgments",reader)
    receipt=critic.verify_correction(before,after,finding["finding_id"],unit_id,tmp_path/"receipt")
    assert receipt["status"]==status and receipt["scope"]=="specified-finding-only"
    assert receipt["whole_artifact_clear"] is False
    assert receipt["after_outstanding"]["unread_cell_ids"]
    assert len(receipt["other_before_findings_not_reassessed"])==1
    assert receipt["other_before_findings_not_reassessed"][0]["reason"]==REPLY["judgments"][0]["findings"][0]["reason"]
    assert tree_hashes(critic,before)==before_hashes and tree_hashes(critic,after)==after_hashes
    assert len(observed)==4
    assert set(receipt["before_readers"])==set(critic.READER_SEATS)

def test_changed_source_values_refuse_before_reader(critic,runs,tmp_path,monkeypatch):
    before,_,_,finding,opened=runs;after,manifest=opened("changed",True)
    monkeypatch.setattr(critic,"_reader_judgments",lambda *a,**k:pytest.fail("Reader should not run"))
    with pytest.raises(critic.Refusal,match="unchanged registered source identities"):
        critic.verify_correction(before,after,finding["finding_id"],manifest["units"][0]["unit_id"],tmp_path/"receipt")
    assert not (tmp_path/"receipt").exists()

@pytest.mark.parametrize("where",["inside-before","inside-after","existing"])
def test_output_cannot_mutate_existing_run_or_evidence(critic,runs,tmp_path,where):
    before,after,unit_id,finding,_=runs
    out=before/"receipt" if where=="inside-before" else after/"receipt" if where=="inside-after" else tmp_path
    with pytest.raises(critic.Refusal,match="new directory outside"):
        critic.verify_correction(before,after,finding["finding_id"],unit_id,out)

FALSE_PILLAR_UNIT = {'anchor_score': 75, 'label': 'Technical proof story', 'payload_paths': ['$.activation_cards[5]'], 'payload_sha256': '3e5f5b82e2bda6331cafb34de10f950535c5983424bc3850ae4a3ff7f1b8a486', 'territory_blocks': [46, 47, 48, 49, 50, 51], 'territory_sha256': '317fb8cbb5072225d691b8a4447d22f96e8c1b04d2ce820e5e8b837729f034eb', 'text': '### Technical proof story\n\n**Insight.** Technical buyers need evidence that AI supports delivery without taking ownership away from senior people.\n\n**Idea.** Publish a technical proof story under The Stop Line showing the claim, proof type, senior owner and stated limit behind an AI-supported delivery example.\n\n**Engagement — the mechanic.** Technical buyers inspect the artifact and see what is confirmed, what is not claimed and who signs the boundary.\n\n**Desired outcome.** Technical trust grows without turning The Stop Line into an unbounded AI capability pitch.  ·  **Targets.** Read in Month 7 for artifact views, sales use and qualified technical conversations.  ·  **Approver.** Matthew Maday\n\n**Signature.** The Stop Line  ·  **KPI.** Technical artifact views — count, Technical artifact analytics report · Sales use of technical proof — count, Sales proof-use register · Qualified technical conversations — count, Technical buyer conversation log  ·  **Months.** 7 to 12', 'unit_id': 'u-011-7c949da8'}
FALSE_PILLAR_FINDING = {'end_line': 11, 'practical_consequence': 'The tactic reaches the calendar without an explicit communications-pillar trace, weakening the required audit trail between strategy and execution.', 'reason': 'The complete unit identifies an audience, message and campaign signature but does not identify the communications pillar required for every tactic before calendaring.', 'source_end_line': 1, 'source_id': 'communications-platform', 'source_start_line': 1, 'start_line': 1}
FALSE_PILLAR_SOURCE = 'The main tactics are The Stop Line proof page, Signed by Humans founder launch post, partner proof pack, owner control message test and senior craft story series. Each tactic must trace to an audience, a key message and a communications pillar before it goes on the calendar.'

def test_captured_false_pillar_not_established_before_is_never_corrected(critic,tmp_path,monkeypatch):
    # Captured false allegation; controlled before-clear tests the correction-status
    # boundary, not semantic refutation (proved separately by live full-artifact runs).
    (tmp_path/".git").mkdir()
    page=tmp_path/"page.md";page.write_text(FALSE_PILLAR_UNIT["text"])
    state=tmp_path/"state.json";state.write_text(json.dumps({"payload":{"rendered":FALSE_PILLAR_UNIT["text"]},"source":{"text":FALSE_PILLAR_SOURCE}}))
    manifests={}
    for name in ("before","after"):
        _,manifests[name]=critic.open_run(page,state,"payload",tmp_path/name,no_reference="Captured correction boundary probe",upstream_sources=[("communications-platform",state,"source")])
    unit=manifests["before"]["units"][0]
    raw={"judgments":[{"lens":"upstream-trace","verdict":"revise","start_line":1,"end_line":11,
        "source_id":"communications-platform","source_start_line":1,"source_end_line":1,"findings":[FALSE_PILLAR_FINDING]}]}
    claims={}
    for seat in critic.READER_SEATS:
        result=critic.classify_reader_reply(json.dumps(raw),critic.reader_schema(["upstream-trace"]),["upstream-trace"],batch_id="captured",seat=seat,attempt=1,evidence_path="captured")
        result=critic.ground_reader_result(result,unit,critic.upstream_sources_for_run(tmp_path/"before",manifests["before"]))
        claims[seat]=critic._claims_from_reader_result(result,["upstream-trace"])["upstream-trace"]
    recorded=critic.record_cell_readers(tmp_path/"before",unit["unit_id"]+"::upstream-trace",claims)
    finding_id=recorded["readers"]["reader-1"]["findings"][0]["finding_id"]
    def already_clear(root,context,focus,selected,lenses,**kwargs):
        reply=copy.deepcopy(raw);j=reply["judgments"][0];j.update(verdict="clear",findings=[],source_id=None,source_start_line=None,source_end_line=None)
        result=critic.classify_reader_reply(json.dumps(reply),critic.reader_schema(lenses),lenses,batch_id=kwargs["batch_id"],seat=kwargs["seat"],attempt=1,evidence_path=str(kwargs["evidence_root"]))
        return critic.ground_reader_result(result,selected,kwargs["upstream_sources"])
    monkeypatch.setattr(critic,"_reader_judgments",already_clear)
    receipt=critic.verify_correction(tmp_path/"before",tmp_path/"after",finding_id,unit["unit_id"],tmp_path/"receipt")
    assert receipt["status"]=="cannot-assess"
    assert receipt["reason"]=="original-finding-not-established"
    assert receipt["artifact_changed"] is False
    assert receipt["whole_artifact_clear"] is False
