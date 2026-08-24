#!/usr/bin/env python3
"""Conduct the code-controlled alignment comparison interview."""
from __future__ import annotations
import argparse,hashlib,json,sys
from pathlib import Path

VERDICTS={"aligned","misaligned","cannot-assess"};MEASURES={"formula-equivalence","availability","scope","value"}
class ComparisonInterviewError(RuntimeError):pass
def canon(v):return json.dumps(v,sort_keys=True,separators=(",",":")).encode()
def doc(v):return json.dumps(v,indent=2,sort_keys=True).encode()+b"\n"
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p,l):
 try:v=json.loads(p.read_bytes())
 except Exception as e:raise ComparisonInterviewError(f"{l} unavailable or invalid: {e}") from None
 if type(v) is not dict:raise ComparisonInterviewError(f"{l} must be one object")
 return v
def replay(p):
 prev=None;out=[]
 for i,line in enumerate(p.read_text().splitlines(),1):
  e=json.loads(line);h=e.get("entry_sha256");b={k:v for k,v in e.items() if k!="entry_sha256"}
  if e.get("sequence")!=i or e.get("previous_entry_sha256")!=prev or h!=hashlib.sha256(canon(b)).hexdigest():raise ComparisonInterviewError(f"ledger changed at {i}")
  prev=h;out.append(e)
 return out
def append(p,payload):
 es=replay(p) if p.exists() else [];b={"sequence":len(es)+1,"previous_entry_sha256":es[-1]["entry_sha256"] if es else None,**payload};e={**b,"entry_sha256":hashlib.sha256(canon(b)).hexdigest()};p.open("ab").write(json.dumps(e,sort_keys=True).encode()+b"\n")
def context(work):
 session=load(work/'session.json','session');p=Path(session['catalog']['path'])
 if sha(p)!=session['catalog']['sha256']:raise ComparisonInterviewError('catalog bytes changed')
 c=load(p,'catalog');es=replay(work/'ledger.jsonl');answers=[e for e in es if e['event']=='answer_recorded'];return c,es,answers
def current(work):
 c,es,a=context(work);done=any(e['event']=='interview_completed' for e in es);return {'status':'completed' if done else 'needs-model-answer','answered_count':len(a),'question_count':c['question_count'],'question':None if done else c['questions'][len(a)]}
def prepare(catalog,work):
 if work.exists():raise ComparisonInterviewError(f"work exists: {work}")
 c=load(catalog,'catalog')
 if c.get('artifact_type')!='system-alignment-comparison-questions' or c.get('status')!='comparison-questions-ready' or c.get('presentation')!='one-question-at-a-time':raise ComparisonInterviewError('catalog identity changed')
 work.mkdir(parents=True);(work/'answers').mkdir();s={'schema_version':1,'catalog':{'path':str(catalog.resolve()),'sha256':sha(catalog),'artifact_sha256':c['artifact_sha256']}};s['artifact_sha256']=hashlib.sha256(canon(s)).hexdigest();(work/'session.json').write_bytes(doc(s));append(work/'ledger.jsonl',{'event':'interview_started'});append(work/'ledger.jsonl',{'event':'question_asked','question_id':c['questions'][0]['question_id'],'position':1});return current(work)
def validate(q,r):
 fields={'schema_version','question_id','verdict','measure','reason','evidence_ids'}
 if type(r) is not dict or set(r)!=fields or r['schema_version']!=1 or r['question_id']!=q['question_id'] or r['verdict'] not in VERDICTS:raise ComparisonInterviewError('response shape, identity, or verdict changed')
 measure=r['measure']
 if type(measure) is not dict or set(measure)!={'kind','expected','actual'} or measure['kind'] not in MEASURES or any(type(measure[x]) is not str or not measure[x] for x in ('expected','actual')):raise ComparisonInterviewError('measure must use an allowed kind with expected and actual values')
 allowed=set(q['actual_evidence_ids']+q['reference_evidence_ids'])
 if type(r['evidence_ids']) is not list or not r['evidence_ids'] or len(r['evidence_ids'])!=len(set(r['evidence_ids'])) or any(x not in allowed for x in r['evidence_ids']):raise ComparisonInterviewError('evidence_ids must be unique presented ids')
 if type(r['reason']) is not str or not r['reason']:raise ComparisonInterviewError('reason is required')
 return r
def answer(work,response_path):
 c,es,a=context(work)
 if any(e['event']=='interview_completed' for e in es):raise ComparisonInterviewError('interview completed')
 q=c['questions'][len(a)];r=validate(q,load(response_path,'response'));pos=len(a)+1;target=work/'answers'/f'answer-{pos:06d}.json';target.write_bytes(doc(r));append(work/'ledger.jsonl',{'event':'answer_recorded','question_id':q['question_id'],'position':pos,'answer_source':{'path':str(target),'sha256':sha(target)},'verdict':r['verdict']})
 if pos==c['question_count']:
  append(work/'ledger.jsonl',{'event':'interview_completed','answer_count':pos});result={'schema_version':1,'artifact_type':'system-alignment-comparison-results','catalog_artifact_sha256':c['artifact_sha256'],'results':[load(work/'answers'/f'answer-{i:06d}.json',f'answer {i}') for i in range(1,pos+1)],'dispositions':c['dispositions'],'status':'comparison-complete'};result['artifact_sha256']=hashlib.sha256(canon(result)).hexdigest();(work/'comparison-results.json').write_bytes(doc(result))
 else:append(work/'ledger.jsonl',{'event':'question_asked','question_id':c['questions'][pos]['question_id'],'position':pos+1})
 return current(work)
def main(argv=None):
 p=argparse.ArgumentParser();s=p.add_subparsers(dest='c',required=True);x=s.add_parser('prepare');x.add_argument('--catalog',type=Path,required=True);x.add_argument('--work',type=Path,required=True);n=s.add_parser('next');n.add_argument('--work',type=Path,required=True);a=s.add_parser('answer');a.add_argument('--work',type=Path,required=True);a.add_argument('--response',type=Path,required=True);z=p.parse_args(argv)
 try:v=prepare(z.catalog,z.work) if z.c=='prepare' else current(z.work) if z.c=='next' else answer(z.work,z.response)
 except ComparisonInterviewError as e:print(str(e),file=sys.stderr);return 2
 print(json.dumps(v,sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
