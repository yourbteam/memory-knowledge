import hashlib,importlib.util,json,sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1];SCRIPTS=ROOT/'skills/system-alignment-assessment-machinery/scripts'
def load(name):
 s=importlib.util.spec_from_file_location(name,SCRIPTS/f'{name}.py');assert s and s.loader;m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
def write(p,v):p.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def fixture(tmp):
 m1=load('mapping_question_units');m2=load('mapping_question_evidence');m=load('unit_mapping_questions')
 units=tmp/'units.json';u={'schema_version':1,'artifact_type':'system-alignment-assessment-units','source_artifact':{},'unit_count':1,'units':[{'unit_id':'u1','sequence':1,'label':'Value','subject':{'identity':'e1'},'intent_statements':[{'statement_id':'c1'}]}],'status':'units-admitted'};u['artifact_sha256']=hashlib.sha256(json.dumps(u,sort_keys=True,separators=(',',':')).encode()).hexdigest();write(units,u)
 def trace(role):
  p=tmp/f'{role}.json';v={'schema_version':1,'artifact_type':'system-alignment-implementation-trace','path_inventory':{},'lane_role':role,'traces':[{'stage_id':role,'sequence':1,'next_stage_id':None,'evidence':[{'repository':'r','path':'/x','sha256':'s','start_line':1,'end_line':2,'excerpt_sha256':'e','reason':'why'}]}],'status':'trace-complete'};v['artifact_sha256']=hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest();write(p,v);return p,v
 a,av=trace('actual');r,rv=trace('reference');spec={'schema_version':1,'units':{'path':str(units),'sha256':sha(units),'artifact_sha256':u['artifact_sha256']},'actual_trace':{'path':str(a),'sha256':sha(a),'artifact_sha256':av['artifact_sha256']},'reference_trace':{'path':str(r),'sha256':sha(r),'artifact_sha256':rv['artifact_sha256']}};p=tmp/'spec.json';write(p,spec);return m,units,a,spec,p
def test_catalog(tmp_path):m,_,_,_,p=fixture(tmp_path);v=m.create(p);assert v['question_count']==1;assert v['presentation']=='one-question-at-a-time';assert v['questions'][0]['allowed_answers']==['mapped','needs-source','not-applicable']
def test_changed_units(tmp_path):
 m,u,_,_,p=fixture(tmp_path);u.write_text('{}\n')
 with pytest.raises(m.MappingQuestionError,match='units bytes changed'):m.create(p)
def test_changed_trace(tmp_path):
 m,_,a,_,p=fixture(tmp_path);a.write_text('{}\n')
 with pytest.raises(m.MappingQuestionError,match='actual trace bytes changed'):m.create(p)
def test_write_verify(tmp_path):m,_,_,_,p=fixture(tmp_path);v=m.create(p);o=tmp_path/'out.json';m.write_once(v,o);assert m.verify(o)==v
