from __future__ import annotations
import hashlib, importlib.util, json, sys
from copy import deepcopy
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]; SCRIPT=ROOT/'skills/system-alignment-assessment-machinery/scripts/path_inventory.py'
def module():
 spec=importlib.util.spec_from_file_location('path_inventory',SCRIPT); assert spec and spec.loader
 value=importlib.util.module_from_spec(spec); sys.modules['path_inventory']=value; spec.loader.exec_module(value); return value
def write(path,value): path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def fixture(tmp_path):
 units=tmp_path/'units.json'; body={'schema_version':1,'artifact_type':'system-alignment-assessment-units','source_artifact':{'path':'/tmp/source','sha256':'a'},'unit_count':1,'units':[{'unit_id':'u1'}],'status':'units-admitted'}; body['artifact_sha256']=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':')).encode()).hexdigest(); write(units,body)
 spec={'schema_version':1,'units_package':{'path':str(units),'sha256':sha(units),'artifact_sha256':body['artifact_sha256']},'paths':[{'path_id':'current','role':'actual','stages':[{'stage_id':'visible','sequence':1,'kind':'observable','purpose':'Visible value'},{'stage_id':'api','sequence':2,'kind':'service','purpose':'API value'}]},{'path_id':'reference','role':'reference','stages':[{'stage_id':'v3','sequence':1,'kind':'reference','purpose':'Reference value'}]}],'comparison':{'actual_stage_id':'api','reference_stage_id':'v3','purpose':'Compare value assembly'}}
 path=tmp_path/'spec.json'; write(path,spec); return module(),units,spec,path
def test_round_trip(tmp_path):
 m,_,_,p=fixture(tmp_path); value=m.create(p); out=tmp_path/'inventory.json'; m._write_once(value,out); assert m.verify(out)==value; assert [x['role'] for x in value['paths']]==['actual','reference']
def test_changed_units_refuses(tmp_path):
 m,units,_,p=fixture(tmp_path); units.write_text('{}\n');
 with pytest.raises(m.PathInventoryError,match='bytes changed'): m.create(p)
def test_duplicate_stage_refuses(tmp_path):
 m,_,spec,p=fixture(tmp_path); spec['paths'][0]['stages'][1]['stage_id']='visible'; write(p,spec)
 with pytest.raises(m.PathInventoryError,match='duplicated'): m.create(p)
def test_wrong_comparison_lane_refuses(tmp_path):
 m,_,spec,p=fixture(tmp_path); spec['comparison']['actual_stage_id']='v3'; write(p,spec)
 with pytest.raises(m.PathInventoryError,match='actual_stage_id'): m.create(p)
def test_unknown_kind_refuses(tmp_path):
 m,_,spec,p=fixture(tmp_path); spec['paths'][0]['stages'][0]['kind']='dashboard'; write(p,spec)
 with pytest.raises(m.PathInventoryError,match='kind must be one of'): m.create(p)
def test_write_once(tmp_path):
 m,_,_,p=fixture(tmp_path); value=m.create(p); out=tmp_path/'inventory.json'; m._write_once(value,out)
 with pytest.raises(m.PathInventoryError,match='already exists'): m._write_once(value,out)
