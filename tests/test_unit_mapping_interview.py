import importlib.util,json,sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1];SCRIPT=ROOT/'skills/system-alignment-assessment-machinery/scripts/unit_mapping_interview.py'
def m():s=importlib.util.spec_from_file_location('unit_mapping_interview',SCRIPT);assert s and s.loader;v=importlib.util.module_from_spec(s);sys.modules['unit_mapping_interview']=v;s.loader.exec_module(v);return v
def write(p,v):p.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
def fixture(tmp):
 mod=m();q={'question_id':'map:u1','sequence':1,'unit':{},'prompt':'map','allowed_answers':['mapped','needs-source','not-applicable'],'actual_evidence_choices':[{'evidence_id':'actual:a:1'}],'reference_evidence_choices':[{'evidence_id':'reference:r:1'}]};catalog={'schema_version':1,'artifact_type':'system-alignment-unit-mapping-questions','units':{},'actual_trace':{},'reference_trace':{},'question_count':1,'questions':[q],'presentation':'one-question-at-a-time','status':'questions-ready'};catalog['artifact_sha256']=mod.hashlib.sha256(mod.canonical(catalog)).hexdigest();p=tmp/'catalog.json';write(p,catalog);return mod,p
def response(answer='mapped'):
 return {'schema_version':1,'question_id':'map:u1','answer':answer,'actual_evidence_ids':['actual:a:1'] if answer=='mapped' else [],'reference_evidence_ids':['reference:r:1'] if answer=='mapped' else [],'actual_expression':'a' if answer=='mapped' else '','reference_expression':'r' if answer=='mapped' else '','missing_stage_ids':['client'] if answer=='needs-source' else [],'reason':'grounded reason'}
def test_one_question_and_completion(tmp_path):
 mod,c=fixture(tmp_path);work=tmp_path/'work';assert mod.prepare(c,work)['question']['question_id']=='map:u1';rp=tmp_path/'r.json';write(rp,response());state=mod.answer(work,rp);assert state['status']=='completed';assert (work/'mappings.json').is_file()
def test_unknown_evidence_refuses(tmp_path):
 mod,c=fixture(tmp_path);work=tmp_path/'work';mod.prepare(c,work);r=response();r['actual_evidence_ids']=['ghost'];p=tmp_path/'r.json';write(p,r)
 with pytest.raises(mod.MappingInterviewError,match='presented evidence'):mod.answer(work,p)
def test_not_applicable_cannot_carry_mapping(tmp_path):
 mod,c=fixture(tmp_path);work=tmp_path/'work';mod.prepare(c,work);r=response('not-applicable');r['actual_expression']='leak';p=tmp_path/'r.json';write(p,r)
 with pytest.raises(mod.MappingInterviewError,match='only its reason'):mod.answer(work,p)
def test_ledger_tamper_refuses(tmp_path):
 mod,c=fixture(tmp_path);work=tmp_path/'work';mod.prepare(c,work);ledger=work/'ledger.jsonl';ledger.write_text(ledger.read_text().replace('question_asked','changed',1))
 with pytest.raises(mod.MappingInterviewError,match='ledger changed'):mod.current(work)
