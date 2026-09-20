"""One Astra assignment call, then existing builder admission in an isolated root."""
import copy,hashlib,json,sys,subprocess
from pathlib import Path
P=Path(__file__).resolve().parent
ROOT=P.parents[3]
SKILLS=Path('/private/tmp/memory-knowledge-atom-selection-publish/skills')
sys.path.insert(0,str(SKILLS/'input-interview-machinery/scripts'))
import run as review,checkpoint
sys.path.insert(0,str(SKILLS/'atom-building-machinery/scripts'))
import build_admission,atom_controller
save=review.save;read=review.read
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def prepare():
 selection=ROOT/'Tasks/atom-selection-machinery-20260918/loop-controller-prototype/live/cycles/cycle-0003/selection/handoff.json'
 history=ROOT/'Tasks/taggable-cross-location-discount-atoms-20260911/tour-prerequisite-structure/atom-request.json'
 case_source=history.with_name('value-packet.json');historical=read(history)
 assert all(c['sha256']==sha(case_source) for c in historical['captured_cases'])
 sources={'selection':selection,'current_answers':Path(read(selection)['input']),
 'goal_context':ROOT/'Tasks/atom-selection-machinery-20260918/goal-record-v1/goal-context.json',
 'historical_request':history,'historical_cases':case_source}
 snapshot=P/'sources';snapshot.mkdir(exist_ok=True)
 manifest={}
 for key,path in sources.items():
  target=snapshot/(key+'.json');raw=path.read_bytes()
  if target.exists():assert target.read_bytes()==raw
  else:target.write_bytes(raw)
  manifest[key]={'origin':str(path),'sha256':sha(target)}
 save(P/'sources.json',manifest)
 paths=[x.removeprefix('taggable-server/') for x in historical['allowed_paths']]
 case_catalog=[{k:v for k,v in c.items() if k not in ['sha256','source_ref']} for c in historical['captured_cases']]
 payload={'selection':read(selection),'current_answers':read(sources['current_answers']),
  'fixed_goal':read(sources['goal_context'])['goal'],
  'available_historical_paths':paths,'captured_case_catalog':case_catalog,
  'boundary':'Historical controlled cases, not production captures. Actual product checkout is untouched. This prepares an assignment, not code or owner authorization.'}
 text={'type':'string'}
 array=lambda item:{'type':'array','items':item}
 schema=review.eng.obj({k:text for k in ['outcome','practical_value','stopping_condition','contribution','proof','before_description','before_quote'] } | {'allowed_paths':array({'type':'string','enum':paths}),'case_ids':array({'type':'string','enum':[c['case_id'] for c in case_catalog]}),'missing_information':array(text)})
 prompt='''Turn the selected atom into one bounded builder assignment. Do not choose another atom or implement it. Preserve its exact business purpose and completion conditions. Choose edit paths and captured cases from the supplied historical catalog only when needed for this restoration. Historical cases are controlled examples, not production evidence. Keep branch isolation and compatibility checks inside this job. Do not add checkout integration, a UI, recognition changes, deployment or new authorization. If information needed to specify this assignment is missing, name it in missing_information instead of guessing. Unknown test results belong to execution, not missing assignment information. Supply a short exact before_quote from the selection chosen_atom. Python owns identities, hashes, evidence references, authorization and serialization. Return only the specified JSON. No tools.\n'''+json.dumps(payload,ensure_ascii=False)
 save(P/'schema.json',schema);(P/'prompt.txt').write_text(prompt)
 save(P/'settings.json',{'provider':'codex','model':'gpt-6-astra','reasoning':'medium'})
 return prompt,schema

def admit(answer):
 if answer['missing_information']:raise ValueError('Assignment needs information: '+str(answer['missing_information']))
 h=read(P/'sources/historical_request.json');selection=read(P/'sources/selection.json');goal_context=read(P/'sources/goal_context.json')
 paths=answer['allowed_paths'];ids=answer['case_ids']
 assert paths and len(paths)==len(set(paths));assert ids and len(ids)==len(set(ids))
 assert answer['before_quote'] and answer['before_quote'] in selection['chosen_atom']
 sandbox=P/'admission-only';sandbox.mkdir(exist_ok=True)
 for key in ['selection','historical_cases']:(sandbox/(key+'.json')).write_bytes((P/'sources'/(key+'.json')).read_bytes())
 cases=[]
 for cid in ids:
  c=copy.deepcopy(next(c for c in h['captured_cases'] if c['case_id']==cid));c.update(source_ref='historical_cases.json',sha256=sha(sandbox/'historical_cases.json'));cases.append(c)
 atom={'schema_version':1,'atomic_step_id':'selected-'+sha(P/'sources/selection.json')[:16],
  **{k:answer[k] for k in ['outcome','practical_value','stopping_condition','allowed_paths']},'captured_cases':cases,
  'contract_surface':{'kind':'behavior','source_paths':paths,'case_ids':ids}}
 atom_controller._validate_request(atom,require_contract_surface=True,repository_root=sandbox)
 save(sandbox/'atom-request.json',atom);save(sandbox/'goal.json',goal_context['goal']);save(sandbox/'goal-context.json',goal_context)
 state={'selection':selection,'execution':'admission-only prototype; no product execution authorized'};save(sandbox/'state.json',state)
 authority={'approved':True,'repository_root':str(sandbox),'atom_request_sha256':build_admission.digest(atom),
 'authorization_reference':'Current user: approved to proceed with this — proposal explicitly limited to prototype assignment admission before implementation.',
 'scope':'Admission validation in this disposable root only. No Taggable build or execution is authorized.'};save(sandbox/'approval.json',authority)
 names=['goal.json','state.json','approval.json','selection.json','historical_cases.json']
 evidence=[{'path':n,'sha256':sha(sandbox/n),'text':(sandbox/n).read_text()} for n in names]
 packet={'schema_version':'build-1','goal':goal_context['goal'],'state':state,'candidate':{k:answer[k] for k in ['outcome','contribution','proof']},'atom_request':atom,
 'bindings':{'goal':'goal.json','state':'state.json'},'evidence':evidence,'approval':{'path':'approval.json','quote':authority['scope']},
 'progress':{'kind':'product','claim':answer['contribution'],'responsibility':None,'before':{'description':answer['before_description'],'evidence':[{'path':'selection.json','quote':answer['before_quote']}]},'after':{'description':answer['outcome'],'owner':'atom builder'},'proof':answer['proof']}}
 save(sandbox/'packet.json',packet)
 receipt_path=sandbox/'receipt.json'
 if not receipt_path.exists():
  subprocess.run([sys.executable,'-B',str(SKILLS/'atom-building-machinery/scripts/build_admission.py'),str(sandbox/'packet.json'),str(receipt_path),'--goal-context',str(sandbox/'goal-context.json'),'--source-root',str(sandbox)],check=True)
 receipt=read(receipt_path);assert build_admission.authorize(packet,receipt,sandbox)
 changed=copy.deepcopy(packet);changed['atom_request']['outcome']+=' Also change payment behavior.';changed['candidate']['outcome']=changed['atom_request']['outcome']
 try:build_admission.authorize(changed,receipt,sandbox)
 except ValueError as e:refusal=str(e)
 else:raise AssertionError('Changed assignment accepted')
 try:build_admission.authorize(packet,receipt,Path('/Users/kamenkamenov/taggable-server'))
 except ValueError:pass
 else:raise AssertionError('Test admission usable against product root')
 save(P/'result.json',{'status':'admission_passed','model':'gpt-6-astra','reasoning':'medium','manual_answer_edits':0,'changed_assignment_refused':refusal,'product_root_refused':True,'implementation_started':False,'live_loop_changed':False,'semantic_review':'pending','remaining':'A full prepared driver also requires experiments, candidates and review/validation adapters; this test covers assignment admission only.'})
if __name__=='__main__':
 if sys.argv[-1]=='prepare':prepare()
 elif sys.argv[-1]=='run':
  prompt,schema=prepare();settings=read(P/'settings.json')
  answer,_=checkpoint.call(P/'model','assignment',prompt,schema,lambda folder:review.CodexTransport(folder,settings));save(P/'assignment.json',answer);admit(answer)
 else:raise SystemExit('Use prepare or run')
