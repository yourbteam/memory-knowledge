"""Execute one prepared admitted atom; preserve stops and require explicit review-transfer authorization."""
import argparse,fcntl,hashlib,json,os,signal,subprocess,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
import atom_controller as controller
from driver_contract import Refusal,document,digest,read,reference,verify,save,validate,generated_request,generated_evidence,execution_snapshot
SOURCE=Path(__file__).resolve().parents[3]

def event(output,kind,**values):
    with (output/'events.jsonl').open('a') as stream:
        stream.write(json.dumps({'time':time.time(),'event':kind,**values},sort_keys=True)+'\n')

def execute(output,name,command,timeout=2700):
    folder=output/'commands'/name
    if folder.exists():
        receipt=read(folder/'receipt.json')
        if receipt['command']!=command or receipt['exit_code']!=0:raise Refusal(f'Previous {name} did not complete; inspect its preserved evidence')
        for key in ['stdout','stderr']:verify(receipt[key])
        return
    folder.mkdir(parents=True);event(output,'command-started',name=name,command=command)
    with (folder/'stdout.txt').open('wb') as out,(folder/'stderr.txt').open('wb') as err:
        p=subprocess.Popen(command,stdout=out,stderr=err,start_new_session=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
        try:p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid,signal.SIGTERM)
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
            save(folder/'timeout.json',{'timeout_seconds':timeout})
    receipt={'command':command,'exit_code':p.returncode,'stdout':reference(folder/'stdout.txt'),'stderr':reference(folder/'stderr.txt')};save(folder/'receipt.json',receipt)
    event(output,'command-finished',name=name,exit_code=p.returncode)
    if p.returncode:raise Refusal(f'{name} failed with exit {p.returncode}; inspect {folder}')

def adapter(request,stage,source,target,output):
    a=request[stage];verify(a['adapter'])
    values={'{python}':sys.executable,'{adapter}':a['adapter']['path'],'{input}':str(source),'{output}':str(target)}
    execute(output,stage,[values[v] for v in a['command']]);verify(a['adapter'])
    return read(target)

def safe_target(root,relative,allowed):
    p=Path(relative)
    if p.is_absolute() or '..' in p.parts or not any(p==Path(a) or Path(a) in p.parents for a in allowed):raise Refusal(f'Assembly path outside approved scope: {relative}')
    target=root/p
    for parent in [target,*target.parents]:
        if parent==root:break
        if parent.is_symlink():raise Refusal(f'Linked promotion path: {parent}')
    return target

def promote(request,output,run,state,root):
    atom=controller._request(run);baseline,baseline_hash=controller._baseline(run,atom)
    experiment=Path(state['current_experiment']['experiment_path']);assembly=experiment/'composition/assembly'
    controller._verify_assembly(experiment,atom,state['current_experiment']['assembly_sha256'])
    spec=read(assembly/'assembly.json');old={f['path']:f for f in baseline['files']};changes=[]
    for op in spec['operations']:
        if op['action'] not in ['add','change']:raise Refusal('Deletion needs separate destructive-operation authorization; this driver handles additions and changes')
        relative=op['path'];safe_target(root,relative,atom['allowed_paths']);prior=old.get(relative)
        source=assembly/'source'/relative
        if source.is_symlink() or digest(source.read_bytes())!=op['sha256']:raise Refusal(f'Assembly bytes changed: {relative}')
        changes.append({'path':relative,'kind':'changed' if prior else 'added','before_sha256':prior['sha256'] if prior else None,'after_sha256':op['sha256'],'before_mode':prior['mode'] if prior else None,'after_mode':prior['mode'] if prior else 0o644})
    changes.sort(key=lambda v:v['path'])
    surface={'schema_version':1,'atomic_step_id':atom['atomic_step_id'],'repository_root':str(root),'baseline_sha256':baseline_hash,'changes':changes}
    surface_path=save(output/'promotion-surface.json',surface)
    review_path=output/'review.json';review=adapter(request,'review',surface_path,review_path,output)
    expected={'schema_version':1,'status':'completed','verdict':'passed','change_surface_sha256':digest(surface_path.read_bytes()),'blocking_findings':[]}
    if review!=expected:raise Refusal('Promotion review did not pass for the exact surface; no files applied')
    journal=output/'promotion-authorized.json'
    current=controller._snapshot(root,atom['allowed_paths'],'driver-promotion');current_map={v['path']:v for v in current};changed={v['path']:v for v in changes}
    for rel in set(old)|set(current_map)|set(changed):
        actual=current_map.get(rel);before=old.get(rel);change=changed.get(rel)
        if actual==before:continue
        if not journal.exists() or not change or not actual or actual['sha256']!=change['after_sha256'] or actual['mode']!=change['after_mode']:
            raise Refusal(f'Product baseline changed outside recorded promotion: {rel}')
    save(journal,{'surface':reference(surface_path),'review':reference(review_path)})
    validate(request,SOURCE)
    for change in changes:
        target=safe_target(root,change['path'],atom['allowed_paths']);data=(assembly/'source'/change['path']).read_bytes()
        if target.is_file() and digest(target.read_bytes())==change['after_sha256']:continue
        prior=old.get(change['path'])
        if prior and (not target.is_file() or digest(target.read_bytes())!=prior['sha256']):raise Refusal(f'Baseline changed immediately before write: {target}')
        if not prior and target.exists():raise Refusal(f'New destination appeared: {target}')
        target.parent.mkdir(parents=True,exist_ok=True);temp=target.with_name(target.name+'.atom-driver.tmp')
        with temp.open('xb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
        temp.chmod(change['after_mode']);os.replace(temp,target);event(output,'file-promoted',path=change['path'],sha256=change['after_sha256'])
    if controller._derive_change_surface(run,atom)!=surface:raise Refusal('Live promoted surface differs from the reviewed assembly')
    # The imported final verdict is case evidence; its complete execution observations remain in the original experiment.
    original=output/'experiment/validation/executions'
    receipt={'schema_version':1,'status':'promoted','atomic_step_id':atom['atomic_step_id'],'controller':'prototype-driven-implementation','experiment_event_sha256':state['current_experiment']['event_sha256'],'experiment_assembly_sha256':state['current_experiment']['assembly_sha256'],'contract_surface':atom['contract_surface'],'changed_paths':[v['path'] for v in changes],'change_surface':reference(surface_path),'review':reference(review_path),'evidence':[{'case_id':c['case_id'],**reference(original/c['case_id']/'stdout.txt')} for c in atom['captured_cases']]}
    path=save(output/'promotion.json',receipt);controller.record_promotion(run,path);event(output,'promotion-recorded')

def closeout(request,output,run,approved_transfer,execution=None,delivery_context=None):
    execution=output if execution is None else execution
    authorization=controller._authorize_validation(run)
    authorization_path=save(output/'authorizations'/(digest(document(authorization))+'.json'),authorization)
    event(output,'authorization-checked',authorization=reference(authorization_path))
    if not (output/'authorization.json').exists():save(output/'authorization.json',authorization)
    packet=read(request['value_packet']['path'])
    records,_=controller._read_ledger(run)
    recorded=next(record['payload'] for record in reversed(records) if record['event']=='validation-recorded')
    frozen=verify({'path':recorded['receipt_path'],'sha256':recorded['receipt_sha256']})
    verify({'path':str(execution/'validation.json'),'sha256':recorded['receipt_sha256']})
    validation=read(frozen)
    observations=[]
    for case in validation['cases']:
        observations.append({'case':case,'evidence':[{'reference':ref,'text':verify({'path':ref['path'],'sha256':ref['sha256']}).read_text()} for ref in case['evidence']]})
    result={'controller_state':controller._state(run),'authorization':authorization,'validation':observations,'driver_events':(execution/'events.jsonl').read_text()}
    lineage=generated_evidence(request,execution)
    if lineage is not None:result['generated_candidate']=lineage
    if execution!=output:
        original=read(output/'recheck-source.json')
        result['original_execution']={'reference':reference(output/'recheck-source.json'),'original':original['original'],'driver_source':original['driver_source']}
    if delivery_context is not None:
        from completion_evidence import collect
        result['delivery_evidence']=collect(delivery_context,request,execution,output)
    result_path=output/'actual-result.txt'
    if not result_path.exists():save(result_path,result)
    text=result_path.read_text();relative=str(result_path.relative_to(Path(request['repository_root'])))
    evidence=packet['evidence']+[{'path':relative,'sha256':digest(text.encode()),'text':text}]
    progress={'kind':packet['progress']['kind'],'observations':'Driver dispatched experiment, promotion, actual-source validation and controller closeout. Inspect the recorded review command for judgment provenance. Generated-input evidence, when present, identifies machine-authored candidate lineage; requirements and other prepared inputs remain supplied.','before':packet['progress']['before']['evidence'],'after':[{'path':relative,'quote':'"authorized": true'}],'evidence':evidence}
    progress_path=save(output/'progress-result.json',progress)
    payload=save(output/'contribution-input.json',{'goal':packet['goal'],'contribution':packet['candidate']['contribution'],'proof':packet['candidate']['proof'],'progress':packet['progress'],'progress_result':progress,'result':text})
    payload_hash=digest(payload.read_bytes())
    if not (output/'contribution/completion.json').exists():
        if approved_transfer!=payload_hash:
            event(output,'approval-needed',payload=reference(payload));return {'status':'approval-needed','payload':reference(payload),'bytes':payload.stat().st_size}
        gate=(Path(__file__).with_name('build_completion.py') if packet.get('schema_version')=='build-1' else SOURCE/'skills/atom-selection-gate/gate.py')
        execute(output,'contribution',[sys.executable,str(gate),'complete','--case',request['value_packet']['path'],'--receipt',request['value_receipt']['path'],'--result',str(result_path),'--progress-result',str(progress_path),'--output',str(output/'contribution'),'--source-root',request['repository_root']])
    receipt=read(output/'contribution/completion.json')
    if receipt.get('achieved') is not True:raise Refusal('Independent contribution remains unproven')
    import atom_sequence
    atom_sequence.record_completion(run, output/'contribution/completion.json')
    controller.authorize_next(run)
    return completed_result(output,run)

def completed_result(output,run):
    """Save the evidence handoff before returning the completed driver's response."""
    from build_handoff import export
    handoff=export(output,output/'handoff.json')
    return {'status':'complete','atom_run':str(run),'contribution':reference(output/'contribution/completion.json'),
            'handoff':str(handoff),'handoff_sha256':reference(handoff)['sha256']}

def drive(path,output,approved_transfer=None,delivery_context=None):
    request=read(path);output=output.absolute()
    if request.get('schema_version')==2:request=generated_request(request,output,SOURCE)
    root=validate(request,SOURCE)
    if not output.is_relative_to(root):raise Refusal('Driver output must be within repository_root for source-bound closeout')
    atom=read(request['atom_request']['path']);controller._require_disjoint_run(output,root,atom['allowed_paths'])
    output.mkdir(parents=True,exist_ok=True)
    with (output/'lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        save(output/'request.json',request);save(output/'driver-source.json',{'driver_sha256':digest(Path(__file__).read_bytes()),'contract_sha256':digest(Path(__file__).with_name('driver_contract.py').read_bytes())})
        prior=Path.cwd();os.chdir(root)
        try:
            run=output/'atom'
            if not run.exists():
                controller.start(Path(request['atom_request']['path']),run,value_packet=Path(request['value_packet']['path']),value_receipt=Path(request['value_receipt']['path']));event(output,'atom-started')
            for step in range(4):
                validate(request,SOURCE);state=controller._state(run);stage=state['stage'];event(output,'state-read',stage=stage)
                if stage=='experiment':
                    if (output/'experiment-recorded.json').exists():raise Refusal('Validation returned to experiment; a reviewed repair is needed')
                    execute(output,'experiment',[sys.executable,str(SOURCE/'skills/experiment-machinery/scripts/development_probe_run.py'),'run',request['experiment_request']['path'],str(output/'experiment')])
                    controller.record_experiment(run,output/'experiment');save(output/'experiment-recorded.json',{'recorded':True});event(output,'experiment-recorded')
                elif stage=='promotion':promote(request,output,run,state,root)
                elif stage=='validation':
                    path=output/'validation.json';adapter(request,'validation',run,path,output);controller.record_validation(run,path);event(output,'validation-recorded')
                elif stage=='complete':return closeout(request,output,run,approved_transfer,delivery_context=delivery_context)
                else:raise Refusal(f'Unsupported verified state: {stage}')
            raise Refusal('Expected bounded stage sequence did not complete')
        finally:os.chdir(prior)

def recheck_closeout(path,output,original,approved_transfer=None,delivery_context=None):
    """Re-assess a completed execution in a separate immutable evidence namespace."""
    original=Path(original).absolute();output=Path(output).absolute()
    request=read(path)
    if request!=read(original/'request.json'):
        raise Refusal('Recheck requires the exact original normalized request')
    root=validate(request,SOURCE)
    if output==original or original in output.parents or output in original.parents:
        raise Refusal('Recheck output must be disjoint from the original execution')
    if not output.is_relative_to(root) or any(p.is_symlink() for p in [output,*output.parents]):
        raise Refusal('Recheck output must be an unlinked directory within repository_root')
    atom=read(request['atom_request']['path']);controller._require_disjoint_run(output,root,atom['allowed_paths'])
    run=original/'atom';state=controller._state(run)
    if state['stage']!='complete' or (len(state['supersession_chain'])>1 and not state['supersession_chain_closed']):
        raise Refusal('Recheck requires an already completed controller and closed supersession chain')
    # Re-derive the actual source boundary before accepting historical validation.
    if controller._derive_change_surface(run,controller._request(run))!=read(original/'promotion-surface.json'):
        raise Refusal('Current product differs from the original promoted surface')
    generated_evidence(request,original)
    snapshot={'original':str(original),'request':reference(original/'request.json'),
              'driver_source':read(original/'driver-source.json'),'files':execution_snapshot(original)}
    output.mkdir(parents=True,exist_ok=True)
    with (output/'lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        save(output/'recheck-source.json',snapshot)
        save(output/'request.json',request)
        save(output/'driver-source.json',{'driver_sha256':digest(Path(__file__).read_bytes()),'contract_sha256':digest(Path(__file__).with_name('driver_contract.py').read_bytes())})
        prior=Path.cwd();os.chdir(root)
        try:return closeout(request,output,run,approved_transfer,execution=original,delivery_context=delivery_context)
        finally:os.chdir(prior)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('request');parser.add_argument('output');parser.add_argument('--approved-transfer-sha256');parser.add_argument('--recheck-closeout-from');parser.add_argument('--delivery-context',type=Path);args=parser.parse_args()
    output=Path(args.output).absolute()
    try:
        result=(recheck_closeout(Path(args.request),output,Path(args.recheck_closeout_from),args.approved_transfer_sha256,args.delivery_context) if args.recheck_closeout_from else drive(Path(args.request),output,args.approved_transfer_sha256,args.delivery_context));print(json.dumps(result));return 0 if result['status']=='complete' else 3
    except (Refusal,controller.AtomError,OSError,ValueError,KeyError,subprocess.SubprocessError) as error:
        if output.is_dir():event(output,'stopped',reason=str(error))
        print(json.dumps({'status':'stopped','reason':str(error)}));return 2
if __name__=='__main__':raise SystemExit(main())
