import hashlib,importlib.util,json,sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1];S=ROOT/'skills/system-alignment-assessment-machinery/scripts/comparison_questions.py'
def m():s=importlib.util.spec_from_file_location('comparison_questions',S);assert s and s.loader;v=importlib.util.module_from_spec(s);sys.modules['comparison_questions']=v;s.loader.exec_module(v);return v
def w(p,v):p.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
def sh(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def fixture(t):
 mod=m();u=t/'u.json';uv={'artifact_type':'system-alignment-assessment-units','units':[{'unit_id':'u1','label':'x','subject':{},'intent_statements':[]},{'unit_id':'u2','label':'y','subject':{},'intent_statements':[]}],'status':'units-admitted'};uv['artifact_sha256']=hashlib.sha256(mod.canon(uv)).hexdigest();w(u,uv);mp=t/'m.json';mv={'artifact_type':'system-alignment-unit-mappings','answers':[{'question_id':'map:u1','answer':'mapped','actual_expression':'a','reference_expression':'r','actual_evidence_ids':['a1'],'reference_evidence_ids':['r1'],'reason':'x'},{'question_id':'map:u2','answer':'not-applicable','actual_expression':'','reference_expression':'','actual_evidence_ids':[],'reference_evidence_ids':[],'reason':'control'}],'status':'mapping-interview-complete'};mv['artifact_sha256']=hashlib.sha256(mod.canon(mv)).hexdigest();w(mp,mv);spec={'schema_version':1,'units':{'path':str(u),'sha256':sh(u),'artifact_sha256':uv['artifact_sha256']},'mappings':{'path':str(mp),'sha256':sh(mp),'artifact_sha256':mv['artifact_sha256']}};p=t/'s.json';w(p,spec);return mod,mp,spec,p
def test_complete_split(tmp_path):mod,_,_,p=fixture(tmp_path);v=mod.create(p);assert v['question_count']==1;assert len(v['dispositions'])==1
def test_missing_mapping_refuses(tmp_path):
 mod,mp,_,p=fixture(tmp_path);v=json.loads(mp.read_text());v['answers'].pop();w(mp,v);spec=json.loads(p.read_text());spec['mappings']['sha256']=sh(mp);w(p,spec)
 with pytest.raises(mod.ComparisonQuestionError,match='coverage'):mod.create(p)
def test_roundtrip(tmp_path):mod,_,_,p=fixture(tmp_path);v=mod.create(p);o=tmp_path/'o.json';mod.write(v,o);assert mod.verify(o)==v
