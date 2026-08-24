import hashlib,importlib.util,json,sys
from copy import deepcopy
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1];SCRIPT=ROOT/'skills/system-alignment-assessment-machinery/scripts/trace_capture.py'
def mod():
 s=importlib.util.spec_from_file_location('trace_capture',SCRIPT);assert s and s.loader;m=importlib.util.module_from_spec(s);sys.modules['trace_capture']=m;s.loader.exec_module(m);return m
def write(p,v):p.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def fix(tmp):
 code=tmp/'code.py';code.write_text('one\ntwo\nthree\n'); inv=tmp/'inventory.json';body={'schema_version':1,'artifact_type':'system-alignment-path-inventory','units_package':{},'paths':[{'path_id':'a','role':'actual','stages':[{'stage_id':'one','sequence':1,'kind':'observable','purpose':'x'},{'stage_id':'two','sequence':2,'kind':'service','purpose':'y'}]},{'path_id':'r','role':'reference','stages':[{'stage_id':'ref','sequence':1,'kind':'reference','purpose':'z'}]}],'comparison':{},'status':'path-inventory-ready'};body['artifact_sha256']=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':')).encode()).hexdigest();write(inv,body)
 def ref(line):return {'repository':'repo','path':str(code),'sha256':sha(code),'start_line':line,'end_line':line,'excerpt_sha256':hashlib.sha256(code.read_text().splitlines(keepends=True)[line-1].encode()).hexdigest(),'reason':'grounds stage'}
 spec={'schema_version':1,'path_inventory':{'path':str(inv),'sha256':sha(inv),'artifact_sha256':body['artifact_sha256']},'lane_role':'actual','traces':[{'stage_id':'one','sequence':1,'next_stage_id':'two','evidence':[ref(1)]},{'stage_id':'two','sequence':2,'next_stage_id':None,'evidence':[ref(2)]}]};p=tmp/'spec.json';write(p,spec);return mod(),code,spec,p
def test_roundtrip(tmp_path):m,_,_,p=fix(tmp_path);v=m.create(p);o=tmp_path/'trace.json';m._write_once(v,o);assert m.verify(o)==v;assert len(v['traces'])==2
def test_missing_stage(tmp_path):
 m,_,spec,p=fix(tmp_path);spec['traces'].pop();write(p,spec)
 with pytest.raises(m.TraceCaptureError,match='coverage'):m.create(p)
def test_bad_successor(tmp_path):
 m,_,spec,p=fix(tmp_path);spec['traces'][0]['next_stage_id']=None;write(p,spec)
 with pytest.raises(m.TraceCaptureError,match='successor'):m.create(p)
def test_changed_evidence(tmp_path):
 m,code,_,p=fix(tmp_path);code.write_text('changed\n')
 with pytest.raises(m.TraceCaptureError,match='file bytes changed'):m.create(p)
