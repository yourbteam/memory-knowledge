"""Hash-bound prepared inputs for one atom execution; no business-specific decisions."""
import hashlib,json,subprocess,sys
from pathlib import Path

class Refusal(ValueError):
    pass

def document(value):
    return (json.dumps(value,indent=2,sort_keys=True)+'\n').encode()

def digest(data):
    return hashlib.sha256(data).hexdigest()

def read(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file():
        raise Refusal(f'Required regular input unavailable: {path}')
    return json.loads(path.read_text())

def reference(path):
    path=Path(path).absolute()
    return {'path':str(path),'sha256':digest(path.read_bytes())}

def verify(ref):
    if not isinstance(ref,dict) or set(ref)!={'path','sha256'}:
        raise Refusal('File reference requires exactly path and sha256')
    p=Path(ref['path'])
    if not p.is_absolute() or p.is_symlink() or not p.is_file() or digest(p.read_bytes())!=ref['sha256']:
        raise Refusal(f'Changed or unavailable prepared input: {p}')
    return p

def save(path,value):
    path=Path(path);data=document(value)
    if path.exists():
        if path.is_symlink() or path.read_bytes()!=data:
            raise Refusal(f'Existing evidence differs: {path}')
    else:
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream:stream.write(data)
    return path

def validate(request,source_root):
    fields={'schema_version','repository_root','atom_request','value_packet','value_receipt','experiment_request','prepared_files','source_trees','review','validation'}
    if set(request)!=fields or request['schema_version']!=1:
        raise Refusal('Driver request must use the complete version-one prepared-atom contract')
    root=Path(request['repository_root'])
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise Refusal('repository_root must be an existing absolute directory')
    refs=[request[k] for k in ['atom_request','value_packet','value_receipt','experiment_request']]+request['prepared_files']
    for ref in refs:verify(ref)
    for tree in request['source_trees']:
        p=Path(tree['path'])
        if not p.is_absolute() or p.is_symlink() or not p.is_dir():raise Refusal(f'Unavailable source tree: {p}')
        result=subprocess.run([sys.executable,str(source_root/'skills/experiment-machinery/scripts/run_experiment.py'),'--hash-source',str(p)],capture_output=True,text=True,timeout=60)
        if result.returncode or result.stdout.strip()!=tree['sha256']:raise Refusal(f'Changed prepared source tree: {p}')
    registered={(r['path'],r['sha256']) for r in refs}
    for stage in ['review','validation']:
        a=request[stage]
        if set(a)!={'adapter','command'} or (a['adapter']['path'],a['adapter']['sha256']) not in registered:
            raise Refusal(f'{stage} adapter must be hash-bound in prepared_files')
        verify(a['adapter']);wanted={'{python}','{adapter}','{input}','{output}'}
        if not isinstance(a['command'],list) or len(a['command'])!=4 or set(a['command'])!=wanted:
            raise Refusal(f'{stage} command must contain python, adapter, input and output exactly once')
    return root

def generated_request(request, output, source_root):
    """Bind one generated approach into the existing prepared driver contract.

    Requirements, controls, oracle and dependency context remain prepared inputs.
    No model code is edited here and no new execution stages replace the driver.
    """
    from candidate_builder_contract import snapshot, prepare
    import atom_controller as controller
    fields={'schema_version','template','generation','probe_id','approach_id','review_context'}
    if set(request)!=fields or request['schema_version']!=2:
        raise Refusal('Generated driver request requires template, generation, probe_id, approach_id and review_context')
    for name in ['template','generation','review_context']:verify(request[name])
    result_path=Path(request['generation']['path']);generation=result_path.parent
    result=read(result_path);creation=read(generation/'request.json');prepare(creation)
    raw=(generation/'raw-answer.txt').read_bytes();proposal=read(generation/'proposal.json')
    if result.get('status')!='candidate' or result.get('request_sha256')!=digest((generation/'request.json').read_bytes()) or result.get('raw_answer_sha256')!=digest(raw) or json.loads(raw)!=proposal or result.get('proposal_sha256')!=digest(json.dumps(proposal,sort_keys=True).encode()):
        raise Refusal('Generated candidate lineage differs from its preserved builder answer')
    candidate=Path(result['source'])
    if snapshot(candidate)!=result['files']:
        raise Refusal('Generated candidate changed after creation; do not edit the model output')
    before={v['path']:v['sha256'] for v in creation['files']};after={v['path']:v['sha256'] for v in result['files']}
    changed=sorted(p for p in set(before)|set(after) if before.get(p)!=after.get(p))
    if changed!=result['changed_paths'] or not changed or any(p not in creation['allowed_paths'] for p in changed):
        raise Refusal('Generated delta is outside the approved creation boundary')
    template=read(request['template']['path'])
    validate(template,source_root)
    atom=read(template['atom_request']['path']);root=Path(template['repository_root'])
    output=Path(output).absolute()
    if not output.is_relative_to(root):raise Refusal('Generated driver output must be within repository_root')
    controller._require_disjoint_run(output,root,atom['allowed_paths'])
    if any(p.is_symlink() for p in [output,*output.parents]):raise Refusal('Linked generated output path')
    output.mkdir(parents=True,exist_ok=True)
    save(output/'generated-input.json',request)
    # A resume uses the original forecast rather than deriving a new baseline after promotion.
    normalized=output/'generated-request.json'
    if normalized.exists():
        saved=read(normalized);validate(saved,source_root);return saved
    # All original references were validated before deriving any replacement.
    if creation['allowed_paths']!=atom['allowed_paths']:
        raise Refusal('Builder file scope differs from the admitted product atom')
    controller._require_disjoint_run(output,root,atom['allowed_paths'])
    baseline=controller._baseline_document(atom,root)
    baseline_map={v['path']:v for v in baseline['files']}
    if any(before.get(p)!=v['sha256'] for p,v in baseline_map.items()):
        raise Refusal('Operator checkout differs from the generator baseline')
    experiment=read(template['experiment_request']['path']);found=0;generated_files=[]
    for probe in experiment['probe_requests']:
        if probe['probe_id']!=request['probe_id']:continue
        cross_path=Path(probe['request'])
        if digest(cross_path.read_bytes())!=probe['request_sha256']:raise Refusal('Probe request changed')
        cross=read(cross_path)
        for approach in cross['approach_build_requests']:
            if approach['approach_id']!=request['approach_id']:continue
            build=read(approach['request'])
            if Path(build['source']['baseline'])!=Path(creation['baseline']):raise Refusal('Experiment and builder baselines differ')
            build['source']['candidate']=str(candidate)
            path=save(output/'generated-build.json',build);generated_files.append(reference(path));approach['request']=str(path);found+=1
        path=save(output/'generated-cross-case.json',cross);generated_files.append(reference(path))
        probe.update({'request':str(path),'request_sha256':digest(path.read_bytes())})
    if found!=1:raise Refusal('Declare exactly one generated probe/approach in the experiment')
    path=save(output/'generated-experiment.json',experiment);template['experiment_request']=reference(path)
    generated_files.append(reference(path))
    tree_command=[sys.executable,str(source_root/'skills/experiment-machinery/scripts/run_experiment.py'),'--hash-source',str(candidate)]
    hashed=subprocess.run(tree_command,capture_output=True,text=True,timeout=60)
    if hashed.returncode:raise Refusal('Cannot hash generated candidate: '+hashed.stderr)
    # The template supplies the baseline as its placeholder candidate. Never require a golden implementation.
    template['source_trees'].append({'path':str(candidate),'sha256':hashed.stdout.strip()})
    surface_changes=[];sources=[]
    for p in changed:
        prior=baseline_map.get(p)
        if p in before and prior is None:raise Refusal('Changed source absent from operator baseline: '+p)
        surface_changes.append({'path':p,'kind':'changed' if prior else 'added','before_sha256':prior['sha256'] if prior else None,'after_sha256':after[p],'before_mode':prior['mode'] if prior else None,'after_mode':prior['mode'] if prior else 0o644})
        for role,origin in [('before',Path(creation['baseline'])/p),('after',candidate/p)]:
            if role=='before' and prior is None:continue
            data=origin.read_bytes();sources.append({'id':role+'-'+str(len(sources)),'role':role,'path':p,'origin':str(origin),'sha256':digest(data),'text':data.decode()})
    surface={'schema_version':1,'atomic_step_id':atom['atomic_step_id'],'repository_root':str(root),'baseline_sha256':digest(controller._document(baseline)),'changes':surface_changes}
    # Forecast is retained separately; the driver derives the actual surface before reviewing it.
    save(output/'generated-surface-forecast.json',surface)
    context=read(request['review_context']['path'])
    if any(s['role'] in ['before','after'] for s in context['sources']):raise Refusal('Review template must contain only prepared requirements, dependencies and evidence; generated code is added by machinery')
    context['sources']+=sources;context['surface_sha256']=digest(document(surface))
    path=save(output/'source-review-context.json',context);generated_files.append(reference(path))
    generated_files += [request['generation'],request['template'],request['review_context']]
    generated_files += [reference(generation/name) for name in ['request.json','raw-answer.txt','proposal.json']]
    template['prepared_files']+=generated_files
    validate(template,source_root)
    save(normalized,template)
    return template


def generated_evidence(request, execution):
    """Export verified source-bearing records, not a claim that generation happened."""
    from candidate_builder_contract import prepare, snapshot
    from candidate_builder import INSTRUCTION
    execution=Path(execution)
    path=execution/'generated-input.json'
    if not path.exists():
        if (execution/'generated-request.json').exists():raise Refusal('Generated execution is missing its original generation input')
        return None
    registered={(r['path'],r['sha256']) for r in request['prepared_files']}
    def bound(ref):
        if (ref['path'],ref['sha256']) not in registered:
            raise Refusal('Generated evidence is not registered: '+ref['path'])
        return verify(ref)
    generated=read(path)
    result_path=bound(generated['generation']);folder=result_path.parent
    result=read(result_path)
    refs={name:reference(folder/name) for name in ['request.json','raw-answer.txt','proposal.json']}
    for ref in refs.values():bound(ref)
    creation=read(refs['request.json']['path']);packet=prepare(creation)
    raw=Path(refs['raw-answer.txt']['path']).read_bytes();proposal=read(refs['proposal.json']['path'])
    if result.get('status')!='candidate' or result.get('request_sha256')!=refs['request.json']['sha256'] or result.get('raw_answer_sha256')!=digest(raw) or json.loads(raw)!=proposal or result.get('proposal_sha256')!=digest(json.dumps(proposal,sort_keys=True).encode()):
        raise Refusal('Generated lineage no longer matches the preserved builder answer')
    prompt=(folder/'prompt.txt').read_bytes()
    if prompt!=(INSTRUCTION+'\n'+json.dumps(packet,ensure_ascii=False)).encode():
        raise Refusal('Builder prompt differs from the verified creation input')
    invocation=read(folder/'model/invocation.json')
    if invocation.get('prompt_sha256')!=digest(prompt) or (folder/'model/prompt.txt').read_bytes()!=prompt or (folder/'model/answer.txt').read_bytes().strip()!=raw.strip():
        raise Refusal('Model invocation, transmitted prompt or returned answer differs from builder lineage')
    candidate=Path(result['source'])
    if snapshot(candidate)!=result['files']:raise Refusal('Generated source changed after creation')
    before={v['path']:v['sha256'] for v in creation['files']};after={v['path']:v['sha256'] for v in result['files']}
    changed=sorted(p for p in set(before)|set(after) if before.get(p)!=after.get(p))
    surface=read(execution/'promotion-surface.json')
    if changed!=result['changed_paths'] or changed!=sorted(c['path'] for c in surface['changes']) or any(p not in creation['allowed_paths'] for p in changed):
        raise Refusal('Generated changed paths differ from the promoted surface')
    sources=[]
    for change in surface['changes']:
        p=change['path']
        if change['before_sha256']!=before.get(p) or change['after_sha256']!=after.get(p):
            raise Refusal('Generated bytes differ from promoted surface: '+p)
        for role,origin in [('before',Path(creation['baseline'])/p),('after',candidate/p)]:
            if role=='before' and p not in before:continue
            ref={'path':str(origin),'sha256':before[p] if role=='before' else after[p]}
            sources.append({'role':role,'source_path':p,'reference':ref,'text':verify(ref).read_text()})
        verify({'path':str(Path(request['repository_root'])/p),'sha256':after[p]})
    refs.update({'prompt.txt':reference(folder/'prompt.txt'),'result.json':generated['generation']})
    for name in ['events.jsonl','model/invocation.json','model/prompt.txt','model/answer.txt','model/events.jsonl']:
        refs[name]=reference(folder/name)
    return {'generated_input':{'reference':reference(path),'text':path.read_text()},
            'builder_records':{name:{'reference':ref,'text':verify(ref).read_text()} for name,ref in refs.items()},
            'sources':sources}


def execution_snapshot(path):
    """Bind every original receipt and execution byte for an immutable recheck."""
    path=Path(path)
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):raise Refusal('Linked original execution')
    result=[]
    for p in sorted(path.rglob('*')):
        if p.is_symlink():raise Refusal('Linked original evidence: '+str(p))
        if p.is_file():result.append(reference(p))
    return result
