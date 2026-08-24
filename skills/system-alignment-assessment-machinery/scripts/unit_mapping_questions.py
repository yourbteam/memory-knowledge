#!/usr/bin/env python3
"""Create and verify the complete alignment-unit mapping question catalog."""
from __future__ import annotations
import argparse,hashlib,json,sys
from pathlib import Path
import mapping_question_evidence as evidence_contract
import mapping_question_units as unit_contract

CONTRACT=1;ARTIFACT_TYPE="system-alignment-unit-mapping-questions";CHOICES=["mapped","needs-source","not-applicable"]
class MappingQuestionError(RuntimeError):pass
def canonical(v):return json.dumps(v,sort_keys=True,separators=(",",":")).encode()
def document(v):return json.dumps(v,indent=2,sort_keys=True).encode()+b"\n"
def load(p,label):
    try:v=json.loads(p.read_bytes())
    except (OSError,UnicodeDecodeError,json.JSONDecodeError) as e:raise MappingQuestionError(f"{label} unavailable or invalid: {e}") from None
    if type(v) is not dict:raise MappingQuestionError(f"{label} must be one object")
    return v
def create_value(spec):
    if type(spec) is not dict or set(spec)!={"schema_version","units","actual_trace","reference_trace"}:raise MappingQuestionError("question specification fields changed")
    if spec["schema_version"]!=CONTRACT:raise MappingQuestionError("question schema_version changed")
    try:units_ref,units=unit_contract.load_units(spec["units"]);actual_ref,actual=evidence_contract.load_trace(spec["actual_trace"],"actual");reference_ref,reference=evidence_contract.load_trace(spec["reference_trace"],"reference")
    except (unit_contract.MappingUnitError,evidence_contract.MappingEvidenceError) as e:raise MappingQuestionError(str(e)) from None
    questions=[]
    for unit in units:
        questions.append({"question_id":f"map:{unit['unit_id']}","sequence":unit["sequence"],"unit":{"unit_id":unit["unit_id"],"label":unit["label"],"subject":unit["subject"],"intent_statements":unit["intent_statements"]},"prompt":"Map this exact unit to the actual and reference trace evidence, or declare why more source evidence is needed or the unit is not applicable.","allowed_answers":CHOICES,"actual_evidence_choices":actual,"reference_evidence_choices":reference})
    body={"schema_version":CONTRACT,"artifact_type":ARTIFACT_TYPE,"units":units_ref,"actual_trace":actual_ref,"reference_trace":reference_ref,"question_count":len(questions),"questions":questions,"presentation":"one-question-at-a-time","status":"questions-ready"}
    return {**body,"artifact_sha256":hashlib.sha256(canonical(body)).hexdigest()}
def create(p):return create_value(load(p,"question specification"))
def write_once(v,p):
    p.parent.mkdir(parents=True,exist_ok=True)
    try:
        with p.open("xb") as f:f.write(document(v))
    except FileExistsError:raise MappingQuestionError(f"question catalog already exists: {p}") from None
def verify(p):
    value=load(p,"question catalog")
    if p.read_bytes()!=document(value):raise MappingQuestionError("question catalog bytes are not canonical")
    expected={"schema_version","artifact_type","units","actual_trace","reference_trace","question_count","questions","presentation","status","artifact_sha256"}
    if set(value)!=expected or value["artifact_type"]!=ARTIFACT_TYPE or value["status"]!="questions-ready" or value["presentation"]!="one-question-at-a-time":raise MappingQuestionError("question catalog identity, fields, or status changed")
    rebuilt=create_value({k:value[k] for k in ("schema_version","units","actual_trace","reference_trace")})
    if rebuilt!=value:raise MappingQuestionError("question catalog no longer matches live inputs")
    return value
def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest="command",required=True);c=s.add_parser("create");c.add_argument("--spec",type=Path,required=True);c.add_argument("--output",type=Path,required=True);v=s.add_parser("verify");v.add_argument("catalog",type=Path);a=p.parse_args(argv)
    try:
        if a.command=="create":value=create(a.spec);write_once(value,a.output)
        else:value=verify(a.catalog)
    except MappingQuestionError as e:print(str(e),file=sys.stderr);return 2
    print(json.dumps({"artifact_sha256":value["artifact_sha256"],"question_count":value["question_count"],"status":value["status"]},sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
