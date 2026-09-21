"""Mechanical goal loop. Existing machinery owns judgments and stage-local recovery."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def read(p): return json.loads(Path(p).read_text())
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p, data):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+'.tmp')
    with tmp.open('w') as f:
        json.dump(data,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    os.replace(tmp,p)

def ref(p, root):
    root=Path(root).resolve();p=Path(p).resolve();return {'path':str(p.relative_to(root)), 'sha256':sha(p)}
def resolve(r, root):
    root=Path(root).resolve();p=root/r['path']
    if not p.resolve().is_relative_to(root) or sha(p)!=r['sha256']:raise ValueError('Changed or out-of-root record: '+r['path'])
    return p

def event(run, kind, **data):
    item={'time':time.time(),'event':kind,**data}
    with (run/'events.jsonl').open('a') as f:f.write(json.dumps(item)+'\n')
    print(json.dumps(item),flush=True)

def call(run, name, argv):
    folder=run/'commands';folder.mkdir(exist_ok=True)
    n=len(list(folder.glob('*.json')))+1;p=folder/f'{n:04d}-{name}'
    save(p.with_suffix('.json'),{'argv':argv,'started':time.time()})
    event(run,'stage_started',stage=name)
    with p.with_suffix('.out').open('w') as out,p.with_suffix('.err').open('w') as err:
        proc=subprocess.run(argv,stdout=out,stderr=err,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
    results=[]
    for line in p.with_suffix('.out').read_text().splitlines():
        try:results.append(json.loads(line))
        except ValueError:pass
    result=results[-1] if results else None
    if proc.returncode and not (proc.returncode==3 and result and result.get('status')=='approval-needed'):
        raise RuntimeError(f'{name} exit {proc.returncode}; inspect {p}.err and {p}.out')
    if not isinstance(result,dict):raise ValueError('Stage returned no JSON action: '+name)
    event(run,'stage_returned',stage=name,result=result)
    return result

def tool(s, name):
    names={'interview':('input-interview-machinery','input_interview.py'),
           'selection':('atom-selection-machinery','atom_selection.py'),
           'assessment':('atom-assessment-machinery','atom_assessment.py'),
           'build':('atom-building-machinery','atom_driver.py')}
    skill,script=names[name];return [sys.executable,'-B',str(Path(s['skills'])/skill/'scripts'/script)]

def new_cycle(run,s,answers,previous=None):
    root=Path(s['root']);number=s.get('cycle_number',0)+1
    path=run/'cycles'/f'cycle-{number:04d}'/'cycle.json'
    value={'schema_version':1,'cycle_id':f'cycle-{number:04d}','goal_id':read(resolve(s['goal'],root))['goal']['id'],
           'goal':s['goal'],'input_answers':answers,'selection':None,'build':None,'assessment':None,'previous_cycle':previous}
    # Replay after a crash before the state pointer was committed.
    if path.exists() and read(path)!=value:raise ValueError('Existing next cycle differs')
    save(path,value);s.update(cycle_number=number,cycle=str(path),stage='selection',answers=answers,pending=None)
    s.pop('build_request',None)
    s.pop('build_preparation',None)
    s.pop('experiment_preparation',None)
    s.pop('candidate_execution',None)
    s.pop('candidate_review',None)
    s.pop('build_output',None)
    s.pop('build_recheck_from',None)
    s.pop('delivery_context',None)
    s.pop('delivery_preparation',None)
    s.pop('build_attempt',None)
    s.pop('previous_build_attempts',None)
    s.pop('approved_transfer',None)

def initialize(args):
    root=args.root.resolve();run=args.run.resolve();goal=ref(args.goal,root);answers=ref(args.answers,root)
    data=read(args.answers)
    if data.get('snapshot',{}).get('fixed_goal')!=goal:raise ValueError('Answers must reference this exact fixed goal')
    if data.get('status','completed')!='completed':raise ValueError('Initial answer set is incomplete')
    if not run.is_relative_to(root):raise ValueError('Loop run must be inside the evidence repository')
    if args.incremental_run and not args.assessment:raise ValueError('Reusing an incremental run requires its assessment')
    run.mkdir(parents=True,exist_ok=False)
    s={'version':1,'root':str(root),'skills':str(args.skills.resolve()),'goal':goal,'answers':answers,'stage':'selection','pending':None,'cycle_number':0}
    (run/'goal.txt').write_text(read(args.goal)['goal']['outcome'])
    s['goal_text_sha256']=sha(run/'goal.txt')
    if args.assessment:
        s['bootstrap_assessment']=ref(args.assessment,root)
        s['stage']='incremental'
        s['incremental_run']=str(args.incremental_run.resolve()) if args.incremental_run else str(run/'bootstrap-interview')
    else:new_cycle(run,s,answers)
    save(run/'state.json',s);return s

def assessment_action(data):
    if data.get('kind')!='atom_assessment':raise ValueError('Not an assessment handoff')
    if data.get('mode') == 'research_assessment':
        if data['assessment']['selected_work_completion']['judgment'] != 'established':
            return 'assessment_needs_attention'
    judgment=data['assessment']['goal_completion']['judgment']
    if judgment=='established':return 'goal_complete'
    if judgment=='not_established':return 'incremental'
    if judgment=='cannot_assess':return 'assessment_needs_attention'
    raise ValueError('Unknown goal-completion judgment: '+str(judgment))

def resolve_decision(run, s, path):
    root=Path(s['root']);cp=Path(s['cycle']);c=read(cp);d=read(path)
    decision_ref=ref(path,root)
    if c.get('decision_resolution')==decision_ref and s['stage']=='incremental':return
    if s['stage']!='build' or (s.get('pending') or {}).get('action')!='prepare_build':
        raise ValueError('Only an unstarted selected job may be resolved by an owner decision')
    if d.get('kind')!='owner_decision_resolution' or d.get('selection')!=c['selection'] or d.get('goal')!=c['goal']:
        raise ValueError('Decision must bind this exact selection and goal')
    if not d.get('owner_response',{}).get('text','').strip() or not d['owner_response'].get('source','').strip():
        raise ValueError('Decision requires the actual owner response and its source')
    if not d.get('outcome','').strip() or not d.get('evidence'):raise ValueError('Decision needs its bounded outcome and evidence')
    for evidence in d['evidence']:resolve(evidence,root)
    if c['build'] is not None or c['assessment'] is not None:raise ValueError('Cannot replace performed build stages')
    c['decision_resolution']=decision_ref;save(cp,c)
    s.update(stage='incremental',pending=None,update_decision=decision_ref,incremental_run=str(cp.parent/'decision-interview'))
    save(run/'state.json',s)

def attach_research(run, s, path):
    root=Path(s['root']);cp=Path(s['cycle']);c=read(cp);d=read(path)
    r=ref(path,root)
    if c.get('research_result')==r and s['stage']=='assessment':return
    if s['stage']!='build' or (s.get('pending') or {}).get('action')!='prepare_build':
        raise ValueError('Research can only complete an unstarted selected job')
    if d.get('kind')!='selected_research_result' or d.get('goal')!=c['goal'] or d.get('selection')!=c['selection']:
        raise ValueError('Research result must bind this exact selection and goal')
    if not d.get('evidence'):raise ValueError('Research result requires saved evidence')
    for e in d['evidence']:resolve(e,root)
    if c['build'] is not None or c['assessment'] is not None:raise ValueError('Cannot replace completed stages')
    c['research_result']=r;save(cp,c)
    s.update(stage='assessment',pending=None);s.pop('update_decision',None);s.pop('error',None)
    save(run/'state.json',s)


def advance(run, stop_after=None):
    s=read(run/'state.json');root=Path(s['root'])
    resolve(s['goal'],root);resolve(s['answers'],root)
    if sha(run/'goal.txt')!=s['goal_text_sha256']:raise ValueError('Fixed goal text changed')
    s.pop('error',None)
    while True:
        stage=s['stage']
        if s.get('pending'):return s['pending']
        if stage=='goal_complete':return {'action':'goal_complete','assessment':s['last_assessment']}
        if stage=='incremental':
            role='decision' if s.get('update_decision') else 'assessment'
            assessment=s.get('update_decision') or s.get('last_assessment',s.get('bootstrap_assessment'));ap=resolve(assessment,root)
            # Historical bootstrap assessments seed input; they never complete a new goal cycle.
            dest=Path(s['incremental_run']);args=tool(s,'interview')+['incremental']
            if (dest/'manifest.json').exists():
                bindings=read(dest/'bindings.json')
                for key,r in [('previous',s['answers']),(role,assessment),('goal',s['goal'])]:
                    if bindings[key]['sha256']!=r['sha256']:raise ValueError('Incremental run has different '+key)
                args+=['continue','--run',str(dest)]
            else:args+=['start','--previous',str(resolve(s['answers'],root)),'--'+role,str(ap),'--goal',str(resolve(s['goal'],root)),'--run',str(dest)]
            result=call(run,'incremental',args)
            if result.get('action')!='complete':s['pending']=result;save(run/'state.json',s);return result
            updated=ref(result['handoff'],root)
            previous=None
            if s.get('cycle'):
                previous=ref(s['cycle'],root)
            new_cycle(run,s,updated,previous);save(run/'state.json',s)
        elif stage=='selection':
            cp=Path(s['cycle']);c=read(cp);dest=cp.parent/'selection'
            # Completed export can be recovered after the process returned but before state save.
            args=tool(s,'selection')
            if (dest/'manifest.json').exists():args+=['resume','--run',str(dest)]
            else:args+=['start','--input',str(resolve(c['input_answers'],root)),'--goal',str(run/'goal.txt'),'--run',str(dest)]
            result=call(run,'selection',args)
            if result.get('action')!='review_recommendation':raise ValueError('Unexpected selector action')
            selected=read(result['handoff'])
            if selected['input_sha256']!=c['input_answers']['sha256'] or selected['goal']!=read(resolve(s['goal'],root))['goal']['outcome']:raise ValueError('Selection input/goal mismatch')
            c['selection']=ref(result['handoff'],root);save(cp,c)
            s.update(stage='build',pending={'action':'prepare_build','selection':c['selection'],
                'instruction':'Calling assistant must review the recommendation and use the existing builder admission process. Supply an authorized prepared driver request bound to this selection; do not infer permission from prose.'})
            save(run/'state.json',s);return s['pending']
        elif stage=='build':
            cp=Path(s['cycle']);c=read(cp);request=resolve(s['build_request'],root)
            args=tool(s,'build')+[str(request),s.get('build_output',str(cp.parent/'build'))]
            if s.get('build_recheck_from'):args+=['--recheck-closeout-from',s['build_recheck_from']]
            if s.get('delivery_context'):args+=['--delivery-context',str(resolve(s['delivery_context'],root))]
            if s.get('approved_transfer'):args+=['--approved-transfer-sha256',s['approved_transfer']]
            result=call(run,'build',args)
            if result.get('status')!='complete':s['pending']=result;save(run/'state.json',s);return result
            handoff=Path(result['handoff'])
            if not handoff.resolve().is_relative_to(root.resolve()):
                expected=Path(s['build_output'])/'handoff.json'
                if handoff!=expected or sha(handoff)!=result['handoff_sha256']:raise ValueError('External builder handoff differs from the authorized output')
                imported=cp.parent/'build-handoff.json'
                if imported.exists() and imported.read_bytes()!=handoff.read_bytes():raise ValueError('Saved builder handoff changed')
                imported.write_bytes(handoff.read_bytes());handoff=imported
            c['build']=ref(handoff,root);save(cp,c);s.update(stage='assessment',pending=None);save(run/'state.json',s)
        elif stage=='assessment':
            cp=Path(s['cycle']);c=read(cp);dest=cp.parent/'assessment';args=tool(s,'assessment')
            if (dest/'manifest.json').exists():args+=['resume','--run',str(dest)]
            else:args+=['start','--root',str(root),'--cycle',str(cp),'--run',str(dest)]
            result=call(run,'assessment',args)
            if result.get('status')!='completed':raise ValueError('Unexpected assessment action')
            data=read(result['handoff'])
            if data.get('mode')!=('research_assessment' if c.get('research_result') else 'cycle_assessment') or data.get('cycle_id')!=c['cycle_id']:raise ValueError('Assessment does not belong to this cycle')
            c['assessment']=ref(result['handoff'],root);save(cp,c)
            s.update(last_assessment=c['assessment'],stage=assessment_action(data),incremental_run=str(cp.parent/'incremental'),pending=None)
            s.pop('update_decision',None)
            if s['stage']=='assessment_needs_attention':s['pending']={'action':'assessment_needs_attention','assessment':c['assessment'],'reason':data['assessment'].get('selected_work_completion',data['assessment']['goal_completion'])['reason']}
            save(run/'state.json',s)
        else:raise ValueError('Unsupported stage '+stage)
        if stop_after == stage:
            return {'action':'stage_completed','stage':stage,'next':s['stage'],'pending':s.get('pending')}


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='op',required=True)
    start=sub.add_parser('start');start.add_argument('--root',type=Path,required=True);start.add_argument('--goal',type=Path,required=True);start.add_argument('--answers',type=Path,required=True);start.add_argument('--assessment',type=Path);start.add_argument('--incremental-run',type=Path);start.add_argument('--skills',type=Path,default=Path.home()/'.codex/skills');start.add_argument('--prepare-only',action='store_true')
    for name in ['resume','status','user','reply','attach-build','prepare-build','prepare-selection','execute-prepared','prepare-experiments','execute-candidate','review-candidate','prepare-delivery','prepare-completion','approve-transfer','resolve-decision','attach-research']:sub.add_parser(name)
    for cmd in sub.choices.values():cmd.add_argument('--run',type=Path,required=True)
    sub.choices['execute-prepared'].add_argument('--php',type=Path)
    sub.choices['execute-prepared'].add_argument('--runtime-config',type=Path)
    sub.choices['execute-prepared'].add_argument('--docker-runtime',type=Path)
    sub.choices['execute-prepared'].add_argument('--autoload',type=Path)
    sub.choices['execute-prepared'].add_argument('--prepare-only',action='store_true')
    sub.choices['execute-prepared'].add_argument('--attempt',type=int,default=1)
    sub.choices['prepare-selection'].add_argument('--repository',type=Path,required=True)
    sub.choices['prepare-selection'].add_argument('--prepare-only',action='store_true')
    sub.choices['prepare-selection'].add_argument('--reference-root',type=Path,action='append',default=[])
    sub.choices['prepare-selection'].add_argument('--attempt',type=int,default=1)
    sub.choices['prepare-selection'].add_argument('--previous',type=Path)
    sub.choices['prepare-selection'].add_argument('--max-calls',type=int,default=4)
    for name in ['resume', 'approve-transfer']:
        sub.choices[name].add_argument('--stop-after', choices=['build', 'assessment'])
    sub.choices['reply'].add_argument('--request-id',required=True);sub.choices['reply'].add_argument('--reply',type=Path,required=True)
    sub.choices['attach-build'].add_argument('--request',type=Path,required=True);sub.choices['attach-build'].add_argument('--selection-sha256',required=True)
    for flag in ['verification','assignment-run','creation-template','repository']:
        sub.choices['prepare-build'].add_argument('--'+flag,type=Path,required=True)
    sub.choices['prepare-build'].add_argument('--attempt',type=int,default=1)
    sub.choices['review-candidate'].add_argument('--attempt',type=int,required=True)
    sub.choices['review-candidate'].add_argument('--prepare-only',action='store_true')
    sub.choices['prepare-completion'].add_argument('--schema-export',type=Path,required=True)
    sub.choices['prepare-completion'].add_argument('--table',action='append',required=True)
    sub.choices['prepare-delivery'].add_argument('--worktree',type=Path,required=True)
    sub.choices['approve-transfer'].add_argument('--sha256',required=True)
    sub.choices['attach-research'].add_argument('--result',type=Path,required=True)
    sub.choices['resolve-decision'].add_argument('--decision',type=Path,required=True)
    sub.choices['resolve-decision'].add_argument('--skills',type=Path)
    a=p.parse_args();run=a.run.resolve()
    if a.op=='start':initialize(a)
    if a.op=='status':print(json.dumps(read(run/'state.json')));return
    with (run/'lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        s=read(run/'state.json')
        try:
            if a.op=='execute-prepared':
                from prepared_execution import execute
                if a.attempt < 1: raise ValueError('Execution attempt must be positive')
                suffix='' if a.attempt==1 else '-attempt'+str(a.attempt)
                result=execute(s,Path(s['cycle']).parent/('prepared-execution'+suffix),a.php,a.autoload,a.prepare_only,a.docker_runtime,a.runtime_config)
                if result.get('handoff'):
                    s['prepared_execution']=ref(result['handoff'],Path(s['root']))
                    s['pending']['prepared_execution']=s['prepared_execution']
                    if result.get('research_result'):
                        attach_research(run,s,Path(result['research_result']))
                    else:
                        save(run/'state.json',s)
                event(run,'prepared_execution_returned',result=result)
                print(json.dumps(result));return
            if a.op=='prepare-selection':
                from selection_preparation import prepare
                if a.attempt < 1: raise ValueError('Preparation attempt must be positive')
                suffix='' if a.attempt==1 else '-attempt'+str(a.attempt)
                result=prepare(s,a.repository,Path(s['cycle']).parent/('selection-preparation'+suffix),a.prepare_only,
                               reference_roots=a.reference_root,previous=a.previous,max_calls=a.max_calls)
                if result['action']=='assignment_prepared':
                    s['selection_preparation']=ref(result['handoff'],Path(s['root']))
                    s['pending']['selection_preparation']=s['selection_preparation']
                    save(run/'state.json',s)
                event(run,'selection_preparation_returned',result=result)
                print(json.dumps(result));return
            if a.op=='prepare-delivery':
                from delivery_connection import prepare
                result=prepare(s,a.worktree);delivery=read(result)
                request=Path(s['cycle']).parent/'delivery-request.json'
                value=read(delivery['request']['path'])
                if sha(Path(delivery['request']['path']))!=delivery['request']['sha256']:raise ValueError('Prepared delivery request changed')
                if request.exists() and read(request)!=value:raise ValueError('Saved delivery request differs')
                save(request,value)
                s.update(delivery_preparation=ref(result,Path(s['root'])),build_request=ref(request,Path(s['root'])),build_output=delivery['output'],pending=None)
                save(run/'state.json',s)
                print(json.dumps({'action':'delivery_prepared','preparation':str(result),'product_promoted':False}));return
            if a.op=='review-candidate':
                from candidate_execution import rereview
                result=rereview(s,a.attempt,a.prepare_only)
                if not a.prepare_only:
                    s['candidate_review']=ref(result,Path(s['root']))
                    s['pending']['candidate_review']=s['candidate_review']
                    save(run/'state.json',s)
                print(json.dumps({'action':'review_prepared' if a.prepare_only else read(result)['status'],'result':str(result),'product_promoted':False}));return
            if a.op=='execute-candidate':
                from candidate_execution import execute
                suffix='' if s.get('build_attempt',1)==1 else '-attempt'+str(s['build_attempt'])
                handoff=execute(s,Path(s['cycle']).parent/('candidate-execution'+suffix))
                result=read(handoff)
                s['candidate_execution']=ref(handoff,Path(s['root']))
                s['pending']['candidate_execution']=s['candidate_execution']
                save(run/'state.json',s)
                print(json.dumps({'action':result['status'],'handoff':str(handoff),'product_promoted':False}));return
            if a.op=='prepare-experiments':
                from experiment_preparation import finish
                suffix='' if s.get('build_attempt',1)==1 else '-attempt'+str(s['build_attempt'])
                handoff=finish(s,Path(s['cycle']).parent/('execution-preparation'+suffix))
                s['experiment_preparation']=ref(handoff,Path(s['root']))
                s['pending']['experiment_and_review_prepared']=s['experiment_preparation']
                save(run/'state.json',s)
                event(run,'experiment_and_review_prepared',handoff=str(handoff),model_calls=0,product_started=False)
                print(json.dumps({'action':'experiment_and_review_prepared','handoff':str(handoff),'pending':'prepare_build'}));return
            if a.op=='prepare-build':
                from build_preparation import prepare
                if a.attempt<max(1,s.get('build_attempt',1)):raise ValueError('Cannot rewind an existing build attempt')
                suffix='' if a.attempt==1 else '-attempt'+str(a.attempt)
                handoff=prepare(s,a.verification,a.assignment_run,a.creation_template,a.repository,Path(s['cycle']).parent/('build-preparation'+suffix))
                if a.attempt>s.get('build_attempt',1):
                    s.setdefault('previous_build_attempts',[]).append({k:s[k] for k in ['build_attempt','build_preparation','experiment_preparation','candidate_execution','candidate_review','error'] if k in s})
                    s.pop('candidate_review',None);s['pending'].pop('candidate_review',None)
                    s.pop('experiment_preparation',None);s.pop('candidate_execution',None);s.pop('error',None)
                    s['pending'].pop('experiment_and_review_prepared',None);s['pending'].pop('candidate_execution',None)
                s['build_attempt']=a.attempt
                s['build_preparation']=ref(handoff,Path(s['root']))
                s['pending']['verification_prepared']=s['build_preparation']
                save(run/'state.json',s)
                event(run,'verification_prepared',handoff=str(handoff),model_calls=0,product_started=False)
                print(json.dumps({'action':'verification_prepared','handoff':str(handoff),'pending':'prepare_build'}));return
            if a.op=='prepare-completion':
                from completion_preparation import prepare
                prepared=prepare(s,a.schema_export,a.table)
                local=Path(s['cycle']).parent/'completion-request.json'
                save(local,read(prepared['request']['path']))
                s.update(build_request=ref(local,Path(s['root'])),build_output=prepared['output'],build_recheck_from=prepared['original'],delivery_context=ref(prepared['config']['path'],Path(s['root'])),pending=None)
                s.pop('approved_transfer',None);save(run/'state.json',s)
                print(json.dumps(advance(run,'build')));return
            if a.op=='attach-research':
                attach_research(run,s,a.result)
                print(json.dumps({'action':'research_recorded','next':'assessment','run':str(run)}));return
            if a.op=='resolve-decision':
                resolve_decision(run,s,a.decision)
                if a.skills:s['skills']=str(a.skills.resolve());save(run/'state.json',s)
                print(json.dumps({'action':'decision_recorded','next':'incremental','run':str(run)}));return
            if a.op=='start' and a.prepare_only:result={'action':'prepared'}
            else:
                if a.op=='attach-build':
                    c=read(s['cycle'])
                    if s['stage']!='build' or a.selection_sha256!=c['selection']['sha256']:raise ValueError('Build must bind the current selection')
                    # Existing driver validates the full admission receipt, approval and edit boundary.
                    s.update(build_request=ref(a.request,Path(s['root'])),pending=None);save(run/'state.json',s)
                elif a.op=='approve-transfer':
                    if s.get('pending',{}).get('status')!='approval-needed' or s['pending']['payload']['sha256']!=a.sha256:raise ValueError('Approval must name the exact pending payload')
                    s.update(approved_transfer=a.sha256,pending=None);save(run/'state.json',s)
                elif a.op=='reply':
                    pending=s.get('pending') or {}
                    if pending.get('action') not in ['ask_user','resolve_input']:raise ValueError('No interview question is pending')
                    if pending['request']['id']!=a.request_id:raise ValueError('Reply must name the exact pending request')
                    interview=pending['interview_run']
                    call(run,'reply',tool(s,'interview')+['reply','--run',interview,'--request-id',a.request_id,'--reply',str(a.reply.resolve())])
                    s['pending']=None;save(run/'state.json',s)
                elif a.op=='user':
                    pending=s.get('pending') or {}
                    if pending.get('action') not in ['ask_user','resolve_input']:raise ValueError('No interview question is pending')
                    result=call(run,'user',tool(s,'interview')+['user','--run',pending['interview_run'],'--request-id',pending['request']['id']])
                    s['pending']={**pending,**result};save(run/'state.json',s)
                result=advance(run, getattr(a,'stop_after',None))
            print(json.dumps(result),flush=True)
        except Exception as exc:
            s=read(run/'state.json');s['error']=str(exc);save(run/'state.json',s);event(run,'failed',reason=str(exc));raise

if __name__=='__main__':main()
