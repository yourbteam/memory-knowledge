import os,sys,json,hashlib,copy,argparse
from pathlib import Path
from datetime import datetime,timezone
sys.dont_write_bytecode=True
root=Path(__file__).resolve().parent;sys.path.insert(0,str(root))
from scripts import work_memory as w
work=Path(os.environ['EXPERIMENT_WORK_DIR']);work.mkdir(parents=True,exist_ok=True)
x=json.loads(Path(os.environ['EXPERIMENT_INPUT_PATH']).read_text());rows=copy.deepcopy(x['events']);run=x['run_id']
doc=work/x['document_path'];doc.parent.mkdir(parents=True,exist_ok=True);doc.write_text(x['document'])
for e in rows:
 if e['event_type']=='run_started':e['repository_roots']={**e['repository_roots'],'memory-knowledge':str(work)}
start=next(e for e in rows if e['event_type']=='run_started' and e['run_id']==run)
correction=next(e for e in rows if e['event_type']=='correction_recorded' and e['run_id']==run)
expected_id=correction['correction_id'];before=copy.deepcopy(rows)
raw={'selection':False,'identities_preserved':False,'guards':{},'lower_terminal_guards':{},'unchanged':False}
try:
 q=w._successor_selection_request(rows,run)
 raw['selection']=True;raw['identities_preserved']=q['task_id']==start['task_id'] and q['verifies_correction_ids']==[expected_id] and q['verification_successor_of']==run and q['discovery_log']==str(doc.resolve())
except w.WorkMemoryError as e:raw['error']=str(e)
terminal=lambda rs:[e for e in rs if e.get('run_id')==run and e['event_type'] in {'run_closed','run_abandoned'}]
for mode in ['nonterminal','successful','duplicate-terminal','no-correction','reopened','wrong-occurrence']:
 z=copy.deepcopy(rows)
 if mode=='nonterminal':z=[e for e in z if e not in terminal(z)]
 elif mode=='successful':t=terminal(z)[0];t['event_type']='run_closed';t['result']='passed'
 elif mode=='duplicate-terminal':z.append(copy.deepcopy(terminal(z)[0]))
 elif mode=='no-correction':z=[e for e in z if e['event_type']!='correction_recorded']
 elif mode=='reopened':z.append({'event_type':'blocker_transitioned','blocker_id':correction['blocker_id'],'to_status':'open'})
 else:
  for e in z:
   if e['event_type']=='correction_recorded' and e['correction_id']==expected_id:e['occurrence_id']='wrong-occurrence'
 try:w._successor_selection_request(z,run);raw['guards'][mode]=False
 except w.WorkMemoryError:raw['guards'][mode]=True
 if mode == 'nonterminal':
  try:w._validate_successor_corrections(z,lineage_id=start['lineage_id'],source_bundle=start['source_bundle'],predecessor_run_id=run,correction_ids=[expected_id],repository_roots=start['repository_roots']);raw['lower_terminal_guards'][mode]=False
  except w.WorkMemoryError as e:raw['lower_terminal_guards'][mode]=str(e)=='successor-predecessor-not-terminal'
raw['unchanged']=rows==before
out={'raw':raw};print(json.dumps(out),flush=True);artifact=work/'observed.json';artifact.write_text(json.dumps(out));v=os.environ['EXPERIMENT_VARIANT_ID']
event={'schema_version':1,'sequence':int(os.environ.get('EXPERIMENT_TELEMETRY_SEQUENCE_START','1')),'event':'work_completed','recorded_at':datetime.now(timezone.utc).isoformat(),'variant_id':v,'message':'Captured predecessor selection and six invalid-history probes through canonical ledger functions.','evidence_sha256':hashlib.sha256(artifact.read_bytes()).hexdigest(),'observations':{'evidence_file':str(artifact)}}
with Path(os.environ['EXPERIMENT_TELEMETRY_PATH']).open('a') as f:f.write(json.dumps(event)+'\n')
Path(os.environ['EXPERIMENT_RESULT_PATH']).write_text(json.dumps({'schema_version':1,'variant_id':v,'status':'completed','outcome':out,'metrics':{},'error':None}))
