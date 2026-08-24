#!/usr/bin/env python3
"""Create and verify complete alignment comparison questions."""
from __future__ import annotations
import argparse,hashlib,json,sys
from pathlib import Path

class ComparisonQuestionError(RuntimeError):pass
def canon(v):return json.dumps(v,sort_keys=True,separators=(",",":")).encode()
def doc(v):return json.dumps(v,indent=2,sort_keys=True).encode()+b"\n"
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p,label):
 try:v=json.loads(p.read_bytes())
 except Exception as e:raise ComparisonQuestionError(f"{label} unavailable or invalid: {e}") from None
 if type(v) is not dict:raise ComparisonQuestionError(f"{label} must be one object")
 return v
def bound(ref,label,atype,status):
 if type(ref) is not dict or set(ref)!={"path","sha256","artifact_sha256"}:raise ComparisonQuestionError(f"{label} reference changed")
 p=Path(ref["path"])
 if not p.is_absolute() or p.is_symlink() or not p.is_file() or sha(p)!=ref["sha256"]:raise ComparisonQuestionError(f"{label} bytes changed or unavailable")
 v=load(p,label)
 if v.get("artifact_type")!=atype or v.get("artifact_sha256")!=ref["artifact_sha256"] or v.get("status")!=status:raise ComparisonQuestionError(f"{label} identity or status changed")
 return {"path":str(p),"sha256":sha(p),"artifact_sha256":ref["artifact_sha256"]},v
def create_value(spec):
 if type(spec) is not dict or set(spec)!={"schema_version","units","mappings"}:raise ComparisonQuestionError("comparison specification fields changed")
 uref,u=bound(spec["units"],"units","system-alignment-assessment-units","units-admitted");mref,m=bound(spec["mappings"],"mappings","system-alignment-unit-mappings","mapping-interview-complete")
 units=u["units"];answers=m["answers"]
 if len(answers)!=len(units) or [a["question_id"] for a in answers]!=[f"map:{x['unit_id']}" for x in units]:raise ComparisonQuestionError("mapping coverage or order changed")
 questions=[];dispositions=[]
 for unit,answer in zip(units,answers):
  if answer["answer"]=="mapped":questions.append({"question_id":f"compare:{unit['unit_id']}","sequence":len(questions)+1,"unit":{"unit_id":unit["unit_id"],"label":unit["label"],"subject":unit["subject"],"intent_statements":unit["intent_statements"]},"actual_expression":answer["actual_expression"],"reference_expression":answer["reference_expression"],"actual_evidence_ids":answer["actual_evidence_ids"],"reference_evidence_ids":answer["reference_evidence_ids"],"allowed_verdicts":["aligned","misaligned","cannot-assess"],"allowed_measure_kinds":["formula-equivalence","availability","scope","value"]})
  else:dispositions.append({"unit_id":unit["unit_id"],"mapping_answer":answer["answer"],"reason":answer["reason"]})
 if len(questions)+len(dispositions)!=len(units):raise ComparisonQuestionError("unit disposition coverage changed")
 body={"schema_version":1,"artifact_type":"system-alignment-comparison-questions","units":uref,"mappings":mref,"question_count":len(questions),"questions":questions,"dispositions":dispositions,"presentation":"one-question-at-a-time","status":"comparison-questions-ready"};return {**body,"artifact_sha256":hashlib.sha256(canon(body)).hexdigest()}
def create(p):return create_value(load(p,"comparison specification"))
def write(v,p):
 p.parent.mkdir(parents=True,exist_ok=True)
 try:
  with p.open("xb") as f:f.write(doc(v))
 except FileExistsError:raise ComparisonQuestionError(f"comparison catalog exists: {p}") from None
def verify(p):
 v=load(p,"comparison catalog")
 if p.read_bytes()!=doc(v):raise ComparisonQuestionError("comparison catalog bytes changed")
 rebuilt=create_value({"schema_version":v["schema_version"],"units":v["units"],"mappings":v["mappings"]})
 if rebuilt!=v:raise ComparisonQuestionError("comparison catalog no longer matches live inputs")
 return v
def main(argv=None):
 p=argparse.ArgumentParser();s=p.add_subparsers(dest="c",required=True);c=s.add_parser("create");c.add_argument("--spec",type=Path,required=True);c.add_argument("--output",type=Path,required=True);x=s.add_parser("verify");x.add_argument("catalog",type=Path);a=p.parse_args(argv)
 try:
  if a.c=="create":v=create(a.spec);write(v,a.output)
  else:v=verify(a.catalog)
 except ComparisonQuestionError as e:print(str(e),file=sys.stderr);return 2
 print(json.dumps({"artifact_sha256":v["artifact_sha256"],"question_count":v["question_count"],"disposition_count":len(v["dispositions"]),"status":v["status"]},sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
