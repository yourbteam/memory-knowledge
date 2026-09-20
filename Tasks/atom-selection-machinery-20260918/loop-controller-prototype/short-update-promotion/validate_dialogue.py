"""Exercise full intake and short-path dialogue with captured owner interaction."""
import sys,json,tempfile,hashlib,copy
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1])/'scripts'))
import input_interview as entry,run as review,followup
B=Path('/Users/kamenkamenov/memory-knowledge/Tasks/input-interview-machinery-20260916/code-owned-lenses-prototype/acceptance-operator-control')
h=review.read(B/'interview/followup-state.json')['history'][0];qid=h['request']['question_id'];question=h['request']['original_question']
context=review.read(B/'interview/contexts.json')[qid]
class Edge:
 mode='recorded_dialogue_control'
 def __init__(self):self.calls=[];self.checks=0
 def __call__(self,folder):return self
 def call(self,stage,prompt,schema,session):
  self.calls.append(stage)
  if stage=='00-direct':answer=h['previous_answer']
  elif stage=='00-followup':
   assert h['reply']['text'] in prompt
   answer=h['final_answer']
  elif stage=='cross-question':
   self.checks+=1
   answer={'decision':'keep','reason':'Captured owner decision is supplied.'}
  elif stage=='revise':answer=h['final_answer']
  else:
   packet=json.loads(prompt.split('Return lens_assessment and complete_answer.\n')[1])
   answer={'lens_assessment':{'decision':'no_change','reason':'Control retains captured response.'},'complete_answer':packet['latest_complete_answer']}
  return answer,'captured-'+str(len(self.calls))
results=[]
with tempfile.TemporaryDirectory() as t:
 t=Path(t)
 for direct in [False,True]:
  run=t/('direct' if direct else 'full');run.mkdir();edge=Edge()
  review.save(t/'questions.json',{'id':'captured-owner-question','questions':[question]});review.save(t/'contexts.json',{qid:context})
  if direct:
   review.save(run/'incremental-previous.json',{'questions':[{'question':question,'final_answer':h['previous_answer'],'session':'captured'}]})
   review.save(run/'incremental-policy.json',{'mode':'direct-update','previous_sha256':hashlib.sha256((run/'incremental-previous.json').read_bytes()).hexdigest()})
  a=entry.main(['start','--questions',str(t/'questions.json'),'--contexts',str(t/'contexts.json'),'--run',str(run)],edge)
  assert a['action']=='resolve_input';rid=a['request']['id'];assert not (run/'handoff.json').exists()
  assert len(edge.calls)==(1 if direct else 9)
  ui=entry.main(['user','--run',str(run),'--request-id',rid],edge)
  assert ui['arguments']['questions'][0]['title']==h['previous_answer']['self_assessment']['question']
  review.save(t/'reply.json',h['reply'])
  a=entry.main(['reply','--run',str(run),'--request-id',rid,'--reply',str(t/'reply.json')],edge)
  assert a['action']=='complete';assert len(edge.calls)==(3 if direct else 19)
  assert review.read(run/'handoff.json')['questions'][0]['final_answer']==h['final_answer']
  results.append({'mode':'direct' if direct else 'full','stages':edge.calls,'passed':True})
 # A captured old answer corrected by the captured owner answer exercises revise/recheck.
 run=t/'revision';run.mkdir();edge=Edge();review.save(run/'questions.json',{'id':'revision','questions':[question]});review.save(run/'contexts.json',{qid:context})
 old=copy.deepcopy(h['previous_answer']);old['self_assessment']={'choice':'ready','reason':'Control injection forces closure over the captured old text.','question':''}
 review.save(run/'incremental-previous.json',{'questions':[{'question':question,'final_answer':old,'session':'captured'}]})
 review.save(run/'incremental-policy.json',{'mode':'direct-update','previous_sha256':hashlib.sha256((run/'incremental-previous.json').read_bytes()).hexdigest()})
 review.save(run/'followup-state.json',{'answers':[{'question':question,'initial_answer':old,'final_answer':old,'session':'captured'}],'history':[h],'exchanges':{qid:1},'pending':None,'status':'finished'})
 class Revision(Edge):
  def call(self,stage,prompt,schema,session):
   if stage=='cross-question' and self.checks==0:
    self.calls.append(stage);self.checks+=1
    return {'decision':'revise','reason':'Captured owner feedback replaces the old cap premise.'},'captured-check'
   return super().call(stage,prompt,schema,session)
 edge=Revision();a=entry.main(['next','--run',str(run)],edge)
 assert a['action']=='complete';assert edge.calls==['cross-question','revise','cross-question']
 assert review.read(run/'handoff.json')['questions'][0]['final_answer']==h['final_answer']
 results.append({'mode':'direct-revision','stages':edge.calls,'passed':True})
print(json.dumps(results))
if len(sys.argv)>2:Path(sys.argv[2]).write_text(json.dumps({'results':results,'provider_calls':0,'meaning':'Control-path tests with captured answers; injected review verdict, not live semantic proof.'},indent=2)+'\n')
