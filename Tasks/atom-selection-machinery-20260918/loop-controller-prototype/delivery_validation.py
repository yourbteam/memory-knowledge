"""Run the frozen verifier against the applied source using the existing executor."""
import hashlib,importlib.util,json,sys
from pathlib import Path

def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def module(name,reference):
 p=Path(reference['path'])
 if sha(p)!=reference['sha256']:raise ValueError('Changed validation dependency: '+str(p))
 spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def run(atom_run,output):
 atom_run=Path(atom_run);output=Path(output);config=read(output.parent.parent/'preparation/validation.json')
 sys.path.insert(0,config['builder_scripts']);import atom_controller as controller
 state=controller._state(atom_run);atom=controller._request(atom_run)
 if state['stage']!='validation':raise ValueError('Applied-source validation requires recorded promotion')
 root=Path(read(atom_run/'inputs/change-baseline.json')['repository_root'])
 executor=module('frozen_executor',config['executor']);judge=module('frozen_judge',config['judge'])
 results=[]
 for case in atom['captured_cases']:
  cid=case['case_id'];folder=output.with_suffix('.evidence')/cid
  if folder.exists():raise ValueError('Existing validation evidence needs inspection: '+str(folder))
  raw=executor.run_case(root,cid,folder);good,reason=judge.assess(raw);source=folder/'result.json'
  results.append({'case_id':cid,'verdict':'satisfied' if good else 'not-satisfied','reason':reason,'evidence':[{'case_id':cid,'path':str(source),'sha256':sha(source)}]})
 output.write_text(json.dumps({'schema_version':1,'status':'completed','atomic_step_id':atom['atomic_step_id'],'promotion_event_sha256':state['current_promotion']['event_sha256'],'cases':results},indent=2)+'\n')

if __name__=='__main__':run(*sys.argv[1:])
