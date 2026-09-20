"""Public-path integration using recorded real model outputs; zero provider calls.
Checks orchestration and prompt/source preservation, not a fresh model quality assessment.
"""
import copy,json,sys,tempfile,hashlib
from pathlib import Path
S=Path(sys.argv[1]).resolve();sys.path.insert(0,str(S/'scripts'))
import input_interview,incremental,configure,run as review
B=Path('/Users/kamenkamenov/memory-knowledge/Tasks/atom-selection-machinery-20260918/loop-controller-prototype')
V=B/'incremental-cost-probe-v3';read=lambda p:json.loads(p.read_text())
expected={q['question']['id']:q['final_answer'] for q in read(V/'combined-answers.json')['questions']}
selected=[k for k,v in read(V/'selection.json').items() if v['decision']=='update']
seen=[];interrupted=False;fail_once=True
class Replay:
 mode='recorded_replay'
 def call(self,stage,prompt,schema,session):
  global interrupted
  assert session is None
  if stage=='affected-questions':return read(V/'selection.json'),'recorded-selection'
  if stage=='00-direct':
   packet=json.loads(prompt.split('\n',1)[1]);qid=packet['question']['id']
   if qid=='obstacle_observations' and fail_once and not interrupted:
    interrupted=True;raise RuntimeError('injected interruption at provider boundary')
   if qid!='current_position':
    source=read(V/'updates'/qid/'attempts/0001/request.json')
    assert prompt==source['prompt'],qid
    assert schema==source['schema']
   seen.append((stage,qid));return expected[qid],'recorded-'+qid
  if stage=='cross-question':
   packet=json.loads(prompt.split('\n',1)[1]);qid=packet['target_question_id'];contents=packet['interview']
   answers={q['question']['id']:q['final_answer'] for q in contents['questions_and_answers']}
   assert answers==expected,'check must see all ten final answers together'
   seen.append((stage,qid))
   # Reuse the recorded keep decision, with no claim of identical full check prompt.
   return (read(V/'checks.json').get(qid) or {'decision':'keep','reason':'Recorded v2 current-position check accepted.'}),'recorded-check-'+qid
  raise AssertionError('Unexpected model stage (including intake lens): '+stage)
def factory(folder):return Replay()
with tempfile.TemporaryDirectory(prefix='incremental-promotion-') as tmp:
 root=Path(tmp)/'run'
 args=['incremental','start','--previous',str(V/'previous.json'),'--assessment',str(V/'assessment.json'),'--goal',str(V/'goal.json'),'--run',str(root),'--prepare-only','--template',str(V/'runtime/incremental-template.json')]
 input_interview.main(args,factory)
 try: input_interview.main(['incremental','continue','--run',str(root)],factory)
 except RuntimeError as exc:assert 'injected interruption' in str(exc)
 else:raise AssertionError('interruption did not occur')
 assert not (root/'current-answers.json').exists()
 result=input_interview.main(['incremental','continue','--run',str(root)],factory)
 assert result['action']=='complete'
 actual=read(root/'current-answers.json');old=read(V/'previous.json')
 assert {q['question']['id']:q['final_answer'] for q in actual['questions']}==expected
 for a,b in zip(actual['questions'],old['questions']):
  if a['question']['id'] not in selected:assert a==b
 assert len(seen)==14 and len(set(seen))==14,seen
 before=(root/'current-answers.json').read_bytes()
 input_interview.main(['incremental','continue','--run',str(root)],factory)
 assert before==(root/'current-answers.json').read_bytes() and len(seen)==14
 # Corruption rejects before using stale context or making another model call.
 (root/'interview/incremental-previous.json').write_text('{}')
 try:input_interview.main(['incremental','continue','--run',str(root)],factory)
 except ValueError as exc:assert 'previous answers changed' in str(exc)
 else:raise AssertionError('changed source accepted')
 assert len(seen)==14
 # No policy: full initial interview still dispatches through the original lens engine.
 full=Path(tmp)/'full';full.mkdir();assert configure.incremental_policy(full) is None
 original=review.run
 try:
  review.run=lambda *a,**kw: 'full-lens-engine'
  assert configure.refine(full,'unused','unused')=='full-lens-engine'
 finally:review.run=original
report={'passed':True,'source':str(S),'provider_calls':0,'recorded_answer_updates':7,'combined_answer_checks':7,'exact_direct_prompt_matches':6,'checks':['all ten final answers preserved','three untouched entries identical','failure before export then resume','completed steps not repeated','unchanged replay export','corrupt source rejected','full intake retains lens engine'],'limits':'Recorded responses verify installed orchestration; check prompts contain updated combined context and were not newly submitted to a model.'}
print(json.dumps(report))
if len(sys.argv)>2:Path(sys.argv[2]).write_text(json.dumps(report,indent=2)+'\n')
