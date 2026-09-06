"""Whole-artifact delivery checks using the repository's captured real BTM roadmap."""
from __future__ import annotations
import importlib.util
import json
import shutil
from pathlib import Path
from types import SimpleNamespace
import pytest
ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/critique-machinery/scripts/critique.py"
CASES = ROOT / "Tasks/critique-machinery/evidence/cases/atom-01/btm-roadmap"

@pytest.fixture
def critic():
    spec=importlib.util.spec_from_file_location("critique_context",SCRIPT)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

@pytest.fixture
def work(critic,tmp_path):
    (tmp_path/".git").mkdir()
    shutil.copyfile(CASES/"page.md",tmp_path/"page.md")
    shutil.copyfile(CASES/"state.json",tmp_path/"state.json")
    case=json.loads((CASES/"case.json").read_text())
    work=tmp_path/"run"
    critic.open_run(tmp_path/"page.md",tmp_path/"state.json",case["payload_key"],work,
        no_reference="Captured runtime probe has no professional reference.",
        no_upstream="Captured runtime probe verifies artifact delivery, not source semantics.")
    return work

def test_complete_page_payload_and_units_roundtrip_without_clipping(critic,work):
    manifest,_=critic.load_matrix(work)
    context=critic.artifact_context_for_run(work,manifest)
    page=Path(manifest["page"]["path"]).read_text()
    assert len(page)>25000
    assert context["page_text"]==page
    assert context["page_text"].splitlines()[0]==page.splitlines()[0]
    assert context["page_byte_count"]==len(page.encode())
    assert context["units"]==manifest["units"]
    assert critic.digest_bytes(critic.canonical(context["payload"]))==manifest["payload"]["value_sha256"]

@pytest.mark.parametrize("key",["page","payload"])
def test_changed_bound_inputs_refuse_before_reading(critic,work,key):
    manifest,_=critic.load_matrix(work)
    path=Path(manifest[key]["path" if key=="page" else "state_path"])
    path.write_bytes(path.read_bytes()+b"\n")
    with pytest.raises(critic.Refusal,match="changed since open"):
        critic.artifact_context_for_run(work,manifest)

@pytest.mark.parametrize("entry",["read-cell","read-run","retry-failed"])
def test_all_public_reader_entrypoints_receive_complete_context(critic,work,monkeypatch,entry):
    seen=[]
    def failed(root,source_context,focus,unit,lenses,**kwargs):
        context=kwargs["artifact_context"]
        assert context["scope"]=="complete-delivered-artifact-and-bound-payload"
        assert len(context["page_text"])>25000
        seen.append(context)
        kwargs["evidence_root"].mkdir(parents=True)
        return critic.classify_reader_reply(b"",critic.reader_schema(lenses),lenses,
            batch_id=kwargs["batch_id"],seat=kwargs["seat"],attempt=kwargs["attempt"],
            evidence_path=str(kwargs["evidence_root"]),forced_outcome="timeout",exit_code=None)
    monkeypatch.setattr(critic,"_reader_judgments",failed)
    _,matrix=critic.load_matrix(work)
    cell=next(cell for cell in matrix["cells"] if cell["lens"]=="buyer-read")
    if entry=="read-run":critic.read_run(work)
    else:
        critic.read_cell(work,cell["cell_id"])
        if entry=="retry-failed":
            seen.clear()
            critic.retry_failed(work)
    assert seen
    assert len({critic.digest_bytes(critic.canonical(context)) for context in seen})==1

def test_actual_reader_evidence_binds_unclipped_context_and_prompt(critic,work,monkeypatch):
    manifest,_=critic.load_matrix(work)
    context=critic.artifact_context_for_run(work,manifest)
    projection=work/"projection"
    (projection/"scripts").mkdir(parents=True)
    (projection/"client-model-policy.json").write_text(json.dumps({"required_runtime":"codex exec","fail_closed":True}))
    monkeypatch.setattr(critic,"__file__",str(projection/"scripts/critique.py"))
    monkeypatch.setattr(critic.shutil,"which",lambda client:"/reader/codex")
    monkeypatch.setattr(critic.subprocess,"run",lambda *args,**kwargs:SimpleNamespace(returncode=1,stdout="",stderr="Runtime boundary test: no provider call"))
    evidence=work/"context-evidence"
    result=critic._reader_judgments(work.parent,"Captured context",critic.LENS_QUESTIONS["buyer-read"],manifest["units"][0],["buyer-read"],evidence_root=evidence,artifact_context=context)
    expected=critic.digest_bytes(critic.canonical(context))
    assert result["intake"]["artifact_context_sha256"]==expected
    assert critic.digest_file(evidence/"artifact-context.json")==expected
    assert json.loads((evidence/"reader-input-envelope.json").read_text())["artifact_context_sha256"]==expected
    prompt=(evidence/"reader-prompt.txt").read_text()
    page_part=prompt.split("COMPLETE DELIVERED PAGE — numbered page lines\n",1)[1].split("\n\nCOMPLETE UNIT INDEX",1)[0]
    assert page_part=="\n".join(f"{i}: {line}" for i,line in enumerate(context["page_text"].splitlines(),1))
    assert "not proof of visible rendering" in prompt
    assert "check each separately against the complete artifact" in prompt
    assert "Finish that inventory before choosing the final findings list" in prompt
