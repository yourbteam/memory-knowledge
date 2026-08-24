import importlib.util,json,sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1];S=ROOT/'skills/system-alignment-assessment-machinery/scripts/comparison_interview.py'
def m():s=importlib.util.spec_from_file_location('comparison_interview',S);assert s and s.loader;v=importlib.util.module_from_spec(s);sys.modules['comparison_interview']=v;s.loader.exec_module(v);return v
def w(p,v):p.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
def fix(t):
 mod=m();q={'question_id':'compare:u1','actual_evidence_ids':['a'],'reference_evidence_ids':['r'],'allowed_verdicts':['aligned','misaligned','cannot-assess']};c={'artifact_type':'system-alignment-comparison-questions','artifact_sha256':'h','question_count':1,'questions':[q],'dispositions':[],'presentation':'one-question-at-a-time','status':'comparison-questions-ready'};p=t/'c.json';w(p,c);return mod,p
def resp():return {'schema_version':1,'question_id':'compare:u1','verdict':'aligned','measure':{'kind':'formula-equivalence','expected':'r','actual':'a'},'reason':'same','evidence_ids':['a','r']}
def test_complete(tmp_path):mod,c=fix(tmp_path);work=tmp_path/'w';mod.prepare(c,work);p=tmp_path/'r.json';w(p,resp());assert mod.answer(work,p)['status']=='completed'
def test_unknown_evidence(tmp_path):
 mod,c=fix(tmp_path);work=tmp_path/'w';mod.prepare(c,work);r=resp();r['evidence_ids']=['ghost'];p=tmp_path/'r.json';w(p,r)
 with pytest.raises(mod.ComparisonInterviewError,match='presented'):mod.answer(work,p)
def test_unknown_measure(tmp_path):
 mod,c=fix(tmp_path);work=tmp_path/'w';mod.prepare(c,work);r=resp();r['measure']['kind']='opinion';p=tmp_path/'r.json';w(p,r)
 with pytest.raises(mod.ComparisonInterviewError,match='measure'):mod.answer(work,p)
