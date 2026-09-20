"""Bind the reviewed candidate to the existing builder in its delivery worktree."""
import copy,json,subprocess,sys
from pathlib import Path
from build_preparation import read,ref,save,sha,verify
from candidate_execution import verify_generation

P=Path(__file__).resolve().parent

def prepare(state,worktree):
 root=Path(state['root']);skills=Path(state['skills']);worktree=Path(worktree).resolve()
 if state['stage']!='build':raise ValueError('Delivery requires the selected build stage')
 def state_ref(key):return verify({'path':str(root/state[key]['path']),'sha256':state[key]['sha256']})
 reviewed_path=state_ref('candidate_review');reviewed=read(reviewed_path);review_dir=reviewed_path.parent
 if reviewed.get('candidate_suitable_to_apply') is not True or reviewed.get('atom_complete') is not False:
  raise ValueError('Delivery requires a passed application review, not a completion claim')
 if reviewed['selection']['sha256']!=read(state['cycle'])['selection']['sha256']:raise ValueError('Review belongs to another selected atom')
 prep=read(state_ref('experiment_preparation'));creation_path=verify(prep['creation_request']);creation=read(creation_path)
 execution=verify(reviewed['generation']).parent.parent
 candidate=verify_generation(execution/'generation',creation_path,skills)
 old_surface=review_dir/'promotion-surface.json';old_review=verify(reviewed['review'])
 if read(old_review)['change_surface_sha256']!=sha(old_surface):raise ValueError('Review surface changed')
 evidence=read(review_dir/'evidence/build-evidence.json')
 branch=evidence['delivery_branch'];commit=evidence['baseline_commit'];repository=Path(evidence['runtime_record']['phpunit']).parents[2]
 def git(at,*args):return subprocess.check_output(['git','-C',str(at),*args]).decode().strip()
 if git(repository,'rev-parse',branch)!=commit:raise ValueError('Delivery branch moved from the reviewed baseline')
 if not worktree.exists():subprocess.run(['git','-C',str(repository),'worktree','add',str(worktree),branch],check=True)
 if git(worktree,'branch','--show-current')!=branch or git(worktree,'rev-parse','HEAD')!=commit:
  raise ValueError('Worktree must be on the exact approved branch and baseline')
 if git(worktree,'diff','--name-only','HEAD'):raise ValueError('Delivery worktree has unrelated tracked changes')
 dest=worktree/'.atom-delivery';prepared=dest/'preparation';output=dest/'build';prepared.mkdir(parents=True,exist_ok=True)
 sys.path.insert(0,str(skills/'atom-building-machinery/scripts'))
 import atom_controller as controller,build_admission,driver_contract,atom_sequence
 admission=P/'assignment-admission-probe-v1/admission-only'
 packet=copy.deepcopy(read(admission/'packet.json'));atom=packet['atom_request']
 if atom['allowed_paths']!=creation['allowed_paths']:raise ValueError('Admission and candidate edit boundaries differ')
 # Keep source quotes and full proof exactly; only rebind the recorded authorization and evidence location.
 for row in packet['evidence']:
  source=admission/row['path'];verify({'path':str(source),'sha256':row['sha256']})
  target=prepared/source.name;target.write_bytes(source.read_bytes());row['path']=str(target.relative_to(worktree))
 packet['bindings']={k:str((prepared/Path(v).name).relative_to(worktree)) for k,v in packet['bindings'].items()}
 packet['state']={'selection':read(verify(reviewed['selection'])),'execution':'Approved delivery of the already reviewed candidate; no new candidate generation.'}
 save(prepared/'delivery-state.json',packet['state']);packet['bindings']['state']=str((prepared/'delivery-state.json').relative_to(worktree))
 authority={'approved':True,'repository_root':str(worktree),'atom_request_sha256':build_admission.digest(atom),
            'authorization_reference':'User: apply to product, install, commit and push; then: you are approved to close that mechanical connection.',
            'scope':'Apply only the saved reviewed candidate for this selected atom to auto-50-perc-off and validate; preserve other work.'}
 save(prepared/'delivery-approval.json',authority)
 packet['approval']={'path':str((prepared/'delivery-approval.json').relative_to(worktree)),'quote':authority['scope']}
 for side in ['before','after']:
  for q in packet['progress'][side].get('evidence',[]):q['path']=str((prepared/Path(q['path']).name).relative_to(worktree))
 files=[prepared/Path(r['path']).name for r in packet['evidence'] if Path(r['path']).name not in ['state.json','approval.json']]+[prepared/'delivery-state.json',prepared/'delivery-approval.json']
 packet['evidence']=[{'path':str(f.relative_to(worktree)),'sha256':sha(f),'text':f.read_text()} for f in files]
 save(prepared/'atom-request.json',atom);save(prepared/'packet.json',packet)
 goal=verify({'path':str(root/state['goal']['path']),'sha256':state['goal']['sha256']})
 receipt=build_admission.prepare(packet,goal,worktree);save(prepared/'receipt.json',receipt)
 baseline=controller._baseline_document(atom,worktree)
 if baseline['files']:raise ValueError('Restoration target unexpectedly already contains allowed source files')
 forecast={'schema_version':1,'atomic_step_id':atom['atomic_step_id'],'repository_root':str(worktree),
           'baseline_sha256':driver_contract.digest(controller._document(baseline)),'changes':read(old_surface)['changes']}
 save(prepared/'forecast.json',forecast)
 packet_path=review_dir/'review.json.source-review/packet.json';answer_path=review_dir/'review.json.source-review/model/answer.txt'
 reuse={'forecast':ref(prepared/'forecast.json'),'surface':ref(old_surface),'review':ref(old_review),'packet':ref(packet_path),'answer':ref(answer_path),
        'builder_scripts':str(skills/'atom-building-machinery/scripts'),
        'candidate_files':[{'relative':c['path'],**ref(candidate/c['path'])} for c in forecast['changes']]}
 save(prepared/'review-reuse.json',reuse)
 judge=Path(prep['review_template']['path']).parent/'judge.py'
 save(prepared/'validation.json',{'builder_scripts':str(skills/'atom-building-machinery/scripts'),'executor':ref(Path(creation['baseline'])/'probe.py'),'judge':ref(judge)})
 context=read(review_dir/'source-review-context.json');context['sources']=[s for s in context['sources'] if s['role'] not in ['before','after']]
 save(prepared/'review-context.json',context)
 template={'schema_version':1,'repository_root':str(worktree),'atom_request':ref(prepared/'atom-request.json'),'value_packet':ref(prepared/'packet.json'),
           'value_receipt':ref(prepared/'receipt.json'),'experiment_request':prep['experiment_rehearsal_request'],
           'prepared_files':[ref(p) for p in [prepared/'review-reuse.json',prepared/'forecast.json',prepared/'validation.json',P/'delivery_review.py',P/'delivery_validation.py',judge,Path(creation['baseline'])/'probe.py']],
           'source_trees':[],
           'review':{'adapter':ref(P/'delivery_review.py'),'command':['{python}','{adapter}','{input}','{output}']},
           'validation':{'adapter':ref(P/'delivery_validation.py'),'command':['{python}','{adapter}','{input}','{output}']}}
 save(prepared/'driver-template.json',template)
 request={'schema_version':2,'template':ref(prepared/'driver-template.json'),'generation':reviewed['generation'],
          'probe_id':read(prep['experiment_rehearsal_request']['path'])['probe_requests'][0]['probe_id'],'approach_id':'candidate','review_context':ref(prepared/'review-context.json')}
 save(prepared/'driver-request.json',request)
 # Use the driver's own generated-input preparation and verify its forecast before launch.
 normalized=driver_contract.generated_request(request,output,skills.parent)
 if read(output/'generated-surface-forecast.json')!=forecast:raise ValueError('Driver forecast differs from approved delivery binding')
 registry=atom_sequence.registry()/(atom_sequence.digest(receipt['goal_context']['goal']['id'].encode())+'.json')
 if not registry.exists():atom_sequence.initialize(goal)
 else:
  registered=read(registry)
  if registered['goal']!=ref(goal) or (registered['active'] and registered['active']['run']!=str(output/'atom')):
   raise ValueError('Existing goal sequence has another active atom; cannot replace it')
 manifest={'request':ref(prepared/'driver-request.json'),'output':str(output),'worktree':str(worktree),'branch':branch,'baseline_commit':commit,
           'review':reviewed['review'],'selection':reviewed['selection'],'product_promoted':False,'model_calls':0}
 result=Path(state['cycle']).parent/'delivery-preparation.json';save(result,manifest)
 return result
