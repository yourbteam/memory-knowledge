#!/usr/bin/env python3
"""Run an append-only, one-question-at-a-time unit-mapping interview."""
from __future__ import annotations
import argparse,hashlib,json,shutil,sys
from pathlib import Path

ANSWERS={"mapped","needs-source","not-applicable"}
class MappingInterviewError(RuntimeError):pass
def canonical(v):return json.dumps(v,sort_keys=True,separators=(",",":")).encode()
def document(v):return json.dumps(v,indent=2,sort_keys=True).encode()+b"\n"
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p,label):
 try:v=json.loads(p.read_bytes())
 except (OSError,UnicodeDecodeError,json.JSONDecodeError) as e:raise MappingInterviewError(f"{label} unavailable or invalid: {e}") from None
 if type(v) is not dict:raise MappingInterviewError(f"{label} must be one object")
 return v
def append(ledger,payload):
 entries=replay(ledger) if ledger.exists() else [];body={"sequence":len(entries)+1,"previous_entry_sha256":entries[-1]["entry_sha256"] if entries else None,**payload};entry={**body,"entry_sha256":hashlib.sha256(canonical(body)).hexdigest()}
 with ledger.open("ab") as f:f.write(json.dumps(entry,sort_keys=True).encode()+b"\n")
 return entry
def replay(ledger):
 prev=None;entries=[]
 for seq,line in enumerate(ledger.read_text().splitlines(),1):
  e=json.loads(line);recorded=e.get("entry_sha256");body={k:v for k,v in e.items() if k!="entry_sha256"}
  if e.get("sequence")!=seq or e.get("previous_entry_sha256")!=prev or recorded!=hashlib.sha256(canonical(body)).hexdigest():raise MappingInterviewError(f"interview ledger changed at entry {seq}")
  prev=recorded;entries.append(e)
 return entries
def prepare(catalog_path,work):
 if work.exists():raise MappingInterviewError(f"interview work already exists: {work}")
 catalog=load(catalog_path,"question catalog")
 if catalog.get("artifact_type")!="system-alignment-unit-mapping-questions" or catalog.get("status")!="questions-ready" or catalog.get("presentation")!="one-question-at-a-time":raise MappingInterviewError("question catalog identity or status changed")
 work.mkdir(parents=True);(work/'answers').mkdir();manifest={"schema_version":1,"artifact_type":"system-alignment-unit-mapping-interview","catalog":{"path":str(catalog_path.resolve()),"sha256":sha(catalog_path),"artifact_sha256":catalog["artifact_sha256"]},"question_count":catalog["question_count"]};manifest["artifact_sha256"]=hashlib.sha256(canonical(manifest)).hexdigest();(work/'session.json').write_bytes(document(manifest));append(work/'ledger.jsonl',{"event":"interview_started","session_sha256":manifest["artifact_sha256"]});append(work/'ledger.jsonl',{"event":"question_asked","question_id":catalog["questions"][0]["question_id"],"position":1});return current(work)
def context(work):
 session=load(work/'session.json',"session");catalog_path=Path(session["catalog"]["path"])
 if sha(catalog_path)!=session["catalog"]["sha256"]:raise MappingInterviewError("question catalog bytes changed")
 catalog=load(catalog_path,"question catalog");entries=replay(work/'ledger.jsonl');answers=[e for e in entries if e["event"]=="answer_recorded"]
 return session,catalog,entries,answers
def current(work):
 _,catalog,entries,answers=context(work);complete=any(e["event"]=="interview_completed" for e in entries)
 return {"status":"completed" if complete else "needs-model-answer","answered_count":len(answers),"question_count":catalog["question_count"],"question":None if complete else catalog["questions"][len(answers)]}
def validate(question,response):
 fields={"schema_version","question_id","answer","actual_evidence_ids","reference_evidence_ids","actual_expression","reference_expression","missing_stage_ids","reason"}
 if type(response) is not dict or set(response)!=fields or response["schema_version"]!=1 or response["question_id"]!=question["question_id"]:raise MappingInterviewError("response shape or question identity changed")
 answer=response["answer"]
 if answer not in ANSWERS:raise MappingInterviewError(f"answer must be one of {sorted(ANSWERS)}")
 allowed_actual={x["evidence_id"] for x in question["actual_evidence_choices"]};allowed_reference={x["evidence_id"] for x in question["reference_evidence_choices"]}
 for name,allowed in (("actual_evidence_ids",allowed_actual),("reference_evidence_ids",allowed_reference)):
  value=response[name]
  if type(value) is not list or len(value)!=len(set(value)) or any(x not in allowed for x in value):raise MappingInterviewError(f"{name} must contain unique presented evidence ids")
 if type(response["missing_stage_ids"]) is not list or len(response["missing_stage_ids"])!=len(set(response["missing_stage_ids"])):raise MappingInterviewError("missing_stage_ids must be a unique list")
 if type(response["reason"]) is not str or not response["reason"]:raise MappingInterviewError("reason is required")
 if answer=="mapped" and (not response["actual_evidence_ids"] or not response["reference_evidence_ids"] or not response["actual_expression"] or not response["reference_expression"] or response["missing_stage_ids"]):raise MappingInterviewError("mapped requires both evidence sets and expressions, with no missing stages")
 if answer=="needs-source" and (not response["missing_stage_ids"]):raise MappingInterviewError("needs-source requires missing_stage_ids")
 if answer=="not-applicable" and (response["actual_evidence_ids"] or response["reference_evidence_ids"] or response["actual_expression"] or response["reference_expression"] or response["missing_stage_ids"]):raise MappingInterviewError("not-applicable accepts only its reason")
 return response
def answer(work,response_path):
 _,catalog,entries,answers=context(work)
 if any(e["event"]=="interview_completed" for e in entries):raise MappingInterviewError("interview is already completed")
 question=catalog["questions"][len(answers)];response=validate(question,load(response_path,"model response"));position=len(answers)+1;target=work/'answers'/f'answer-{position:06d}.json'
 if target.exists():raise MappingInterviewError(f"answer source already exists: {target}")
 target.write_bytes(document(response));append(work/'ledger.jsonl',{"event":"answer_recorded","question_id":question["question_id"],"position":position,"answer_source":{"path":str(target),"sha256":sha(target)},"answer":response["answer"]})
 if position==catalog["question_count"]:
  append(work/'ledger.jsonl',{"event":"interview_completed","answer_count":position});result={"schema_version":1,"artifact_type":"system-alignment-unit-mappings","catalog_artifact_sha256":catalog["artifact_sha256"],"answers":[load(work/'answers'/f'answer-{i:06d}.json',f'answer {i}') for i in range(1,position+1)],"status":"mapping-interview-complete"};result["artifact_sha256"]=hashlib.sha256(canonical(result)).hexdigest();(work/'mappings.json').write_bytes(document(result))
 else:append(work/'ledger.jsonl',{"event":"question_asked","question_id":catalog["questions"][position]["question_id"],"position":position+1})
 return current(work)
def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest="command",required=True);a=s.add_parser("prepare");a.add_argument("--catalog",type=Path,required=True);a.add_argument("--work",type=Path,required=True);n=s.add_parser("next");n.add_argument("--work",type=Path,required=True);r=s.add_parser("answer");r.add_argument("--work",type=Path,required=True);r.add_argument("--response",type=Path,required=True);x=p.parse_args(argv)
 try:v=prepare(x.catalog,x.work) if x.command=="prepare" else current(x.work) if x.command=="next" else answer(x.work,x.response)
 except MappingInterviewError as e:print(str(e),file=sys.stderr);return 2
 print(json.dumps(v,sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
