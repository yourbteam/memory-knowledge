"""Mechanical connection: existing builder -> actual experiment -> source reviewer.

No product promotion. A completed stage is reused only after its saved bytes verify.
An interrupted ambiguous model call stops rather than silently paying for a retry.
"""
import json
from pathlib import Path
import subprocess
import sys
import time

from build_preparation import read, ref, save, sha, verify


def emit(output, event, **details):
    row = {'time': time.time(), 'event': event, **details}
    with (output / 'events.jsonl').open('a') as stream:
        stream.write(json.dumps(row) + '\n')
    print(json.dumps(row), flush=True)


def files(root):
    result = []
    for p in sorted(root.rglob('*')):
        if p.is_symlink():raise ValueError('Linked execution evidence: ' + str(p))
        if p.is_file():result.append(ref(p))
    return result


def once(output, name, argv, work, final):
    receipt = output / 'receipts' / (name + '.json')
    command = {'argv': argv}
    save(output / 'commands' / (name + '.json'), command)
    if receipt.exists():
        saved = read(receipt)
        if saved['argv'] != argv:raise ValueError('Changed command on resume: ' + name)
        for reference in saved['files']:verify(reference)
        verify(saved['final'])
        emit(output, 'stage_reused', stage=name)
        return
    if work.exists():
        raise ValueError('Unreceipted ' + name + ' output exists; inspect its preserved result before any paid retry: ' + str(work))
    emit(output, 'stage_started', stage=name)
    with (output / 'commands' / (name + '.stdout')).open('w') as out, (output / 'commands' / (name + '.stderr')).open('w') as err:
        completed = subprocess.run(argv, stdout=out, stderr=err, env={**__import__('os').environ, 'PYTHONDONTWRITEBYTECODE': '1'})
    emit(output, 'stage_returned', stage=name, exit_code=completed.returncode)
    if completed.returncode or not final.is_file():
        raise ValueError(name + ' did not complete; inspect commands/' + name + '.stdout and .stderr; no later stage ran')
    save(receipt, {'argv': argv, 'files': files(work), 'final': ref(final)})


def verify_generation(generation, request_path, skills):
    sys.path.insert(0, str(skills / 'atom-building-machinery/scripts'))
    from candidate_builder_contract import snapshot, prepare, digest
    from candidate_builder import INSTRUCTION
    request = read(request_path)
    packet = prepare(request)
    if (generation / 'request.json').read_bytes() != request_path.read_bytes():
        raise ValueError('Builder output belongs to a different creation request')
    result = read(generation / 'result.json')
    raw = (generation / 'raw-answer.txt').read_bytes()
    proposal = read(generation / 'proposal.json')
    if result.get('status') != 'candidate' or result['request_sha256'] != sha(request_path) or result['raw_answer_sha256'] != digest(raw) or json.loads(raw) != proposal:
        raise ValueError('Candidate differs from its untouched builder answer')
    if result['proposal_sha256'] != digest(json.dumps(proposal, sort_keys=True).encode()):
        raise ValueError('Candidate proposal hash differs')
    candidate = Path(result['source'])
    if snapshot(candidate) != result['files']:raise ValueError('Candidate source changed after generation')
    before = {x['path']: x['sha256'] for x in request['files']}
    after = {x['path']: x['sha256'] for x in result['files']}
    changed = sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))
    if changed != result['changed_paths'] or any(p not in request['allowed_paths'] for p in changed):
        raise ValueError('Candidate delta differs from its allowed creation boundary')
    if result.get('prompt_format') == 'sections-v1':
        from builder_prompt import render
        prompt = render(INSTRUCTION, packet).encode()
    elif 'prompt_format' not in result:
        # Exact historical builder format; never rewrite old generation records.
        prompt = (INSTRUCTION + '\n' + json.dumps(packet, ensure_ascii=False)).encode()
    else:
        raise ValueError('Unknown preserved builder prompt format')
    if (generation / 'prompt.txt').read_bytes() != prompt or (generation / 'model/prompt.txt').read_bytes() != prompt:
        raise ValueError('Candidate prompt differs from the prepared request')
    invocation = read(generation / 'model/invocation.json')
    if invocation['prompt_sha256'] != digest(prompt) or (generation / 'model/answer.txt').read_bytes() != raw:
        raise ValueError('Model invocation or answer differs from candidate lineage')
    return candidate


def bind_experiment(prepared, generation, output, skills):
    request_path = verify(prepared['creation_request'])
    candidate = verify_generation(generation, request_path, skills)
    creation = read(request_path)
    context = json.loads(creation['context'])
    test = context['verification']['test']
    if sha(candidate / test['destination']) != test['sha256']:
        raise ValueError('Generated candidate changed or omitted the frozen verification source')
    original = read(verify(prepared['experiment_rehearsal_request']))
    if len(original['probe_requests']) != 1:raise ValueError('This connection expects one prepared functional probe')
    experiment = json.loads(json.dumps(original))
    probe = experiment['probe_requests'][0]
    cross_path = verify({'path': probe['request'], 'sha256': probe['request_sha256']})
    cross = read(cross_path)
    matches = [a for a in cross['approach_build_requests'] if a['approach_id'] == 'candidate']
    if len(matches) != 1:raise ValueError('Prepared experiment must name one candidate approach')
    build = read(matches[0]['request'])
    if build['source']['baseline'] != creation['baseline'] or original['baseline']['path'] != creation['baseline']:
        raise ValueError('Generator and experiment baselines differ')
    build['source']['candidate'] = str(candidate)
    save(output / 'candidate-build.json', build)
    matches[0]['request'] = str(output / 'candidate-build.json')
    save(output / 'cross-case.json', cross)
    probe.update(request=str(output / 'cross-case.json'), request_sha256=sha(output / 'cross-case.json'))
    save(output / 'experiment-request.json', experiment)
    return output / 'experiment-request.json'


def prepare_review(prepared, output, skills, review=None):
    experiment = output / 'experiment'
    summary_path = experiment / 'development-probe-summary.json'
    summary = read(summary_path)
    verdict_path = experiment / 'validation/final-verdict.json'
    verify({'path': str(verdict_path), 'sha256': summary['final_verdict_sha256']})
    if summary['verdict'] != 'passed' or summary['promotion_applied'] is not False:
        raise ValueError('Actual candidate experiment did not pass; review cannot advance it')
    assembly = experiment / 'composition/assembly'
    checked = subprocess.run([sys.executable, '-B', str(skills / 'experiment-machinery/scripts/development_probe_compose.py'), 'verify', str(assembly)], capture_output=True, text=True)
    if checked.returncode:raise ValueError('Actual assembly verification failed: ' + checked.stderr + checked.stdout)
    spec = read(assembly / 'assembly.json')
    creation = read(verify(prepared['creation_request']))
    before = {x['path']: x['sha256'] for x in creation['files']}
    context = read(verify(prepared['review_template']))
    changes = []
    for op in spec['operations']:
        if op['path'] not in creation['allowed_paths'] or op['action'] not in ['add', 'change']:
            raise ValueError('Review surface exceeds the authorized additive candidate boundary')
        p = op['path'];after = assembly / 'source' / p
        verify({'path': str(after), 'sha256': op['sha256']})
        changes.append({'path': p, 'kind': 'changed' if p in before else 'added', 'before_sha256': before.get(p), 'after_sha256': sha(after), 'before_mode': 0o644 if p in before else None, 'after_mode': 0o644})
        for role, source in [('before', Path(creation['baseline']) / p), ('after', after)]:
            if role == 'before' and p not in before:continue
            context['sources'].append({'id': role + '-' + str(len(changes)), 'role': role, 'path': p,
                                      'origin': str(source), 'sha256': sha(source), 'text': source.read_text()})
    # The review receives this candidate's actual raw results, not the rehearsal verdict.
    review = review or output / 'review-input'
    from review_evidence import collect
    evidence = [summary_path, verdict_path] + sorted((experiment / 'validation/executions').glob('*/stdout.txt'))
    evidence += collect(prepared, output, review / 'evidence')
    for index, source in enumerate(evidence):
        context['sources'].append({'id': 'actual-execution-' + str(index), 'role': 'evidence', 'path': str(source),
                                  'origin': str(source), 'sha256': sha(source), 'text': source.read_text()})
    save(review / 'promotion-surface.json', {'schema_version': 1, 'changes': sorted(changes, key=lambda x: x['path'])})
    context['surface_sha256'] = sha(review / 'promotion-surface.json')
    save(review / 'source-review-context.json', context)
    save(review / 'request.json', {'prepared_files': [ref(review / 'source-review-context.json')]})
    return review / 'promotion-surface.json'


def execute(state, output):
    output = Path(output).resolve()
    root = Path(state['root']);skills = Path(state['skills'])
    if state['stage'] != 'build' or (state.get('pending') or {}).get('action') != 'prepare_build':
        raise ValueError('Candidate connection requires the pending selected build')
    prepared_path = verify({'path': str(root / state['experiment_preparation']['path']), 'sha256': state['experiment_preparation']['sha256']})
    prepared = read(prepared_path)
    cycle = read(state['cycle'])
    if prepared['selection']['sha256'] != cycle['selection']['sha256']:
        raise ValueError('Execution preparation belongs to another selected atom')
    for key in ['creation_request', 'experiment_rehearsal_request', 'review_template']:verify(prepared[key])
    output.mkdir(parents=True, exist_ok=True)
    scripts = {name: skills / skill / 'scripts' / script for name, skill, script in [
        ('builder', 'atom-building-machinery', 'candidate_builder.py'),
        ('experiment', 'experiment-machinery', 'development_probe_run.py'),
        ('review', 'atom-building-machinery', 'source_review.py')]}
    bindings = {'preparation': ref(prepared_path), 'connection': ref(Path(__file__)),
                'scripts': {k: ref(v) for k, v in scripts.items()}}
    save(output / 'bindings.json', bindings)
    request = verify(prepared['creation_request']);generation = output / 'generation'
    once(output, 'generation', [sys.executable, '-B', str(scripts['builder']), str(request), str(generation)], generation, generation / 'result.json')
    experiment_request = bind_experiment(prepared, generation, output, skills)
    experiment = output / 'experiment'
    once(output, 'experiment', [sys.executable, '-B', str(scripts['experiment']), 'run', str(experiment_request), str(experiment)], experiment, experiment / 'development-probe-summary.json')
    surface = prepare_review(prepared, output, skills)
    review_result = surface.parent / 'review.json'
    once(output, 'review', [sys.executable, '-B', str(scripts['review']), str(surface), str(review_result)],
         surface.parent / 'review.json.source-review', review_result)
    verdict = read(review_result)
    if verdict['change_surface_sha256'] != sha(surface):raise ValueError('Review verdict belongs to another surface')
    # The receipt snapshots the model work directory; bind its adjacent verdict too.
    save(output / 'review-verdict-binding.json', ref(review_result))
    result = {'status': 'candidate_reviewed' if verdict['verdict'] == 'passed' else 'candidate_needs_correction',
              'review_decision': 'candidate_application', 'candidate_suitable_to_apply': verdict['verdict'] == 'passed',
              'atom_complete': False,
              'generation': ref(generation / 'result.json'), 'experiment': ref(experiment / 'development-probe-summary.json'),
              'review': ref(review_result), 'selection': prepared['selection'],
              'product_promoted': False, 'goal_complete': False}
    save(output / 'handoff.json', result)
    emit(output, result['status'], product_promoted=False)
    return output / 'handoff.json'


def rereview(state, attempt, prepare_only=False):
    """Review the saved candidate again without generation or experiment calls."""
    if attempt < 2 or state['stage'] != 'build':
        raise ValueError('Review retry requires a saved build and a new attempt number of at least 2')
    root = Path(state['root']); skills = Path(state['skills'])
    previous = verify({'path': str(root / state['candidate_execution']['path']),
                       'sha256': state['candidate_execution']['sha256']})
    output = previous.parent
    prepared = read(verify({'path': str(root / state['experiment_preparation']['path']),
                            'sha256': state['experiment_preparation']['sha256']}))
    if read(previous)['selection'] != prepared['selection'] or prepared['selection']['sha256'] != read(state['cycle'])['selection']['sha256']:
        raise ValueError('Saved candidate review belongs to a different selection')
    for stage in ['generation', 'experiment']:
        receipt = read(output / 'receipts' / (stage + '.json'))
        for reference in receipt['files'] + [receipt['final']]:verify(reference)
    verify_generation(output / 'generation', verify(prepared['creation_request']), skills)
    review = output / ('review-attempt' + str(attempt))
    surface = prepare_review(prepared, output, skills, review)
    if sha(surface) != sha(output / 'review-input/promotion-surface.json'):
        raise ValueError('Review retry changed the candidate surface')
    script = skills / 'atom-building-machinery/scripts/source_review.py'
    review.mkdir(exist_ok=True); (review / 'commands').mkdir(exist_ok=True)
    if prepare_only:
        final = review / 'preview.json.source-review/prompt.txt'
        once(review, 'prepare', [sys.executable, '-B', str(script), str(surface), str(review / 'preview.json'), '--prepare-only'], final.parent, final)
        return final
    result_path = review / 'review.json'
    once(review, 'review', [sys.executable, '-B', str(script), str(surface), str(result_path)],
         review / 'review.json.source-review', result_path)
    verdict = read(result_path)
    if verdict['change_surface_sha256'] != sha(surface):raise ValueError('Review retry verdict surface differs')
    handoff = {**read(previous), 'status': 'candidate_reviewed' if verdict['verdict'] == 'passed' else 'candidate_needs_correction',
               'review_decision': 'candidate_application', 'candidate_suitable_to_apply': verdict['verdict'] == 'passed',
               'atom_complete': False,
               'review': ref(result_path), 'previous_review': read(previous)['review'], 'model_calls': 1}
    save(review / 'handoff.json', handoff)
    return review / 'handoff.json'
