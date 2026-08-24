#!/usr/bin/env python3
"""Assemble one verified downstream-ready assessment package."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

CONTRACT=1
_SCRIPT_DIR=Path(__file__).resolve().parent

def _load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None: raise RuntimeError(f"{name} is unavailable")
    module=importlib.util.module_from_spec(spec); sys.modules[spec.name]=module; spec.loader.exec_module(module); return module

journal=_load_module("assessment_package_journal",_SCRIPT_DIR/"projection_interview.py")
charter_contract=_load_module("assessment_package_charter",_SCRIPT_DIR/"assessment_charter.py")
evidence_contract=_load_module("assessment_package_evidence",_SCRIPT_DIR/"assessment_evidence.py")
sufficiency_contract=_load_module("assessment_package_sufficiency",_SCRIPT_DIR/"assessment_sufficiency.py")
verdict_contract=_load_module("assessment_package_verdicts",_SCRIPT_DIR/"assessment_verdicts.py")
request_contract=_load_module("assessment_package_requests",_SCRIPT_DIR/"assessment_gap_requests.py")

class AssessmentPackageError(RuntimeError): pass

def _canonical(value): return json.dumps(value,sort_keys=True,separators=(",",":")).encode()
def _digest(value): return hashlib.sha256(value).hexdigest()
def _load(path,label):
    try: raw=path.read_bytes(); value=json.loads(raw)
    except (OSError,json.JSONDecodeError) as error: raise AssessmentPackageError(f"{label} is unavailable or invalid JSON: {error}") from error
    if not isinstance(value,dict): raise AssessmentPackageError(f"{label} must contain one object")
    return value,raw
def _ref(path,raw,value): return {"path":str(path.resolve()),"sha256":_digest(raw),"artifact_sha256":value.get("artifact_sha256")}

def _verified(path,label,contract):
    try: contract.verify(path)
    except Exception as error: raise AssessmentPackageError(str(error)) from error
    value,raw=_load(path,label); return value,_ref(path,raw,value)

def _sources(charter_path,evidence_path,sufficiency_path,verdict_path,request_path):
    charter,charter_ref=_verified(charter_path,"assessment charter",charter_contract)
    evidence,evidence_ref=_verified(evidence_path,"assessment evidence",evidence_contract)
    sufficiency,sufficiency_ref=_verified(sufficiency_path,"assessment sufficiency",sufficiency_contract)
    verdicts,verdict_ref=_verified(verdict_path,"assessment verdicts",verdict_contract)
    requests,request_ref=_verified(request_path,"assessment gap requests",request_contract)
    errors=[]
    if sufficiency.get("charter_source")!=charter_ref: errors.append("sufficiency charter source does not match the supplied charter")
    if sufficiency.get("evidence_source")!=evidence_ref: errors.append("sufficiency evidence source does not match the supplied evidence")
    if verdicts.get("evidence_source")!=evidence_ref: errors.append("verdict evidence source does not match the supplied evidence")
    if verdicts.get("sufficiency_source")!=sufficiency_ref: errors.append("verdict sufficiency source does not match the supplied sufficiency")
    if requests.get("sufficiency_source")!=sufficiency_ref: errors.append("request sufficiency source does not match the supplied sufficiency")
    counts={evidence.get("unit_count",len(evidence.get("units",[]))),sufficiency.get("unit_count"),verdicts.get("unit_count")}
    if len(counts)!=1: errors.append(f"unit counts received {sorted(str(item) for item in counts)!r}; provide one identical count")
    expected=[gap["gap_id"] for gap in sufficiency.get("gaps",[])]
    received=requests.get("covered_gap_ids",[])
    if len(received)!=len(expected) or sorted(received)!=sorted(expected):
        errors.append(f"request gap coverage received missing={sorted(set(expected)-set(received))!r}, duplicate={sorted({item for item in received if received.count(item)>1})!r}, unknown={sorted(set(received)-set(expected))!r}; cover every exact gap once")
    if errors: raise AssessmentPackageError("; ".join(errors))
    return charter,evidence,sufficiency,verdicts,requests,{"charter":charter_ref,"evidence":evidence_ref,"sufficiency":sufficiency_ref,"verdicts":verdict_ref,"requests":request_ref}

def _artifact(charter,evidence,sufficiency,verdicts,requests,refs):
    evidence_by_id={unit["unit_id"]:unit for unit in evidence["units"]}
    findings=[]
    for result in verdicts["units"]:
        unit=evidence_by_id[result["unit_id"]]
        findings.append({"unit_id":result["unit_id"],"label":unit["label"],"subject":unit["subject"],"verdict":result["verdict"],"measure":result["measure"],"reason":result["reason"],"evidence_ids":result["evidence_ids"],"gap_ids":result["gap_ids"],"missing_evidence":result["missing_evidence"]})
    misaligned=[item for item in findings if item["verdict"]=="misaligned"]
    incomplete=[item for item in findings if item["verdict"]=="incomplete"]
    value={
      "schema_version":CONTRACT,"artifact_type":"info-intake-assessment-package","status":"assessment-ready","sources":refs,
      "purpose":charter["assessment"]["purpose"],"decision":charter["assessment"]["decision"],
      "summary":{"unit_count":len(findings),"verdict_counts":verdicts["verdict_counts"],"confirmed_misalignment_count":len(misaligned),"incomplete_unit_count":len(incomplete),"gap_count":sufficiency["gap_count"],"source_request_count":requests["request_count"]},
      "findings":findings,"confirmed_misalignments":misaligned,"unresolved_source_requests":requests["requests"],
      "prototype_handoff":{"status":"ready" if misaligned else "no-confirmed-misalignment","recommended_skill":"prototype-driven-implementation","objective":"Resolve each confirmed misalignment without weakening incomplete findings.","captured_cases":[{"case_id":f"assessment-{item['unit_id']}","unit_id":item["unit_id"],"verdict":item["verdict"],"measure":item["measure"],"evidence_ids":item["evidence_ids"]} for item in misaligned]},
      "experiment_handoff":{"status":"ready" if misaligned else "not-needed","recommended_skill":"experiment-machinery","candidate_case_ids":[f"assessment-{item['unit_id']}" for item in misaligned],"evaluation":"A candidate must correct the measured misalignment and preserve all other findings."}
    }
    value["artifact_sha256"]=_digest(_canonical(value)); return value

def run(charter_path,evidence_path,sufficiency_path,verdict_path,request_path,work_dir):
    charter,evidence,sufficiency,verdicts,requests,refs=_sources(charter_path,evidence_path,sufficiency_path,verdict_path,request_path)
    artifact=_artifact(charter,evidence,sufficiency,verdicts,requests,refs); payload=json.dumps(artifact,indent=2,sort_keys=True).encode()+b"\n"
    work_dir.mkdir(parents=True,exist_ok=True); path=work_dir/"assessment-package.json"; ledger_path=work_dir/"ledger.jsonl"
    if path.exists():
        if path.read_bytes()!=payload: raise AssessmentPackageError("assessment package already exists with different bytes")
        return verify(path)
    if ledger_path.exists(): raise AssessmentPackageError("assessment package ledger exists without its artifact")
    journal._append(ledger_path,"assessment_package_started",{"sources":refs}); journal._append(ledger_path,"assessment_package_completed",{"artifact_path":"assessment-package.json","artifact_sha256":_digest(payload)}); path.write_bytes(payload); return artifact

def verify(path):
    value,_raw=_load(path,"assessment package")
    if value.get("artifact_type")!="info-intake-assessment-package" or value.get("status")!="assessment-ready": raise AssessmentPackageError("assessment package type or status is invalid")
    refs=value.get("sources",{}); paths=[Path(str(refs.get(name,{}).get("path"))) for name in ("charter","evidence","sufficiency","verdicts","requests")]
    charter,evidence,sufficiency,verdicts,requests,fresh_refs=_sources(*paths)
    if refs!=fresh_refs: raise AssessmentPackageError("assessment package source bindings changed")
    if _artifact(charter,evidence,sufficiency,verdicts,requests,fresh_refs)!=value: raise AssessmentPackageError("assessment package findings or handoff changed")
    return value

def main():
    parser=argparse.ArgumentParser(description=__doc__); commands=parser.add_subparsers(dest="command",required=True); create=commands.add_parser("run")
    for name in ("charter","evidence","sufficiency","verdicts","requests","work"): create.add_argument(f"--{name}",type=Path,required=True)
    check=commands.add_parser("verify"); check.add_argument("artifact",type=Path); args=parser.parse_args()
    try: result=run(args.charter,args.evidence,args.sufficiency,args.verdicts,args.requests,args.work) if args.command=="run" else verify(args.artifact)
    except AssessmentPackageError as error: print(str(error),file=sys.stderr); return 2
    print(json.dumps(result,indent=2,sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
