"""Execute an admitted disposable experiment; no product promotion or goal completion.

Reuses candidate generation and lineage verification. OS confinement owns runtime
isolation; a separate model assesses raw captured evidence against the saved cases.
"""
import json
import hashlib
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys

from build_preparation import read, ref, save, sha, verify
from candidate_execution import once, verify_generation, emit, files

RUNTIME_DIRECTORIES = ['experiment/results']
RUNTIME_FILES = ['experiment/report.md']


def generation_request(data):
    """Keep code edits separate from execution writes in the authoritative request."""
    data = json.loads(json.dumps(data))
    context = json.loads(data['context'])
    context['execution_permissions'] = {
        'generated_files': data['allowed_paths'],
        'runtime_output_directories': RUNTIME_DIRECTORIES,
        'runtime_output_files': RUNTIME_FILES,
        'temporary_directory': 'Use the supplied TMPDIR',
        'network': 'denied', 'product_source': 'read-only'}
    data['context'] = json.dumps(context, ensure_ascii=False)
    data['constraints'] = (
        'The allowed_paths list limits files in your returned code edits only. '
        'Generate only the assigned files. At execution time the generated program '
        'IS permitted to create directories and evidence files under experiment/results/, '
        'write experiment/report.md, and use the supplied TMPDIR for temporary files. '
        'Do not return generated evidence or results-directory entries as code edits. '
        'All other existing files, including generated executable code and frozen cases, are read-only at runtime. '
        'No live services, credentials, external writes, installation or deployment. '
        'Preserve all selected cases and source-grounded limits. '
        'Do not implement missing product behavior to make a probe pass.')
    return data


def source_provenance(handoff, request):
    """Bind supplied source bytes to Git without asking the builder to infer ancestry."""
    repository = Path(handoff['repository'])
    commit = handoff['commit']
    def git(*args):
        return subprocess.run(['git', '-C', str(repository), *args], capture_output=True, check=True).stdout
    identity = git('rev-list', '--parents', '-n', '1', commit).decode().strip().split()
    if not identity or identity[0] != commit: raise ValueError('Cannot resolve the prepared source commit')
    source_rows = []
    for row in request['files']:
        path = row['path'];local = Path(request['baseline']) / path
        if sha(local) != row['sha256']: raise ValueError('Prepared source changed: ' + path)
        if path.startswith('references/'):
            source_rows.append({**row, 'role': 'archived reference; not installed product'})
            continue
        raw = git('show', commit + ':' + path)
        if raw != local.read_bytes(): raise ValueError('Source snapshot differs from commit: ' + path)
        source_rows.append({**row, 'role': 'current product', 'commit': commit})
    changes = []
    for line in git('diff-tree', '--root', '--no-commit-id', '--name-status', '-r', '--no-renames', commit).decode().splitlines():
        status, path = line.split('\t', 1)
        item = {'status': status, 'path': path}
        if status != 'D': item['sha256'] = hashlib.sha256(git('show', commit + ':' + path)).hexdigest()
        changes.append(item)
    return {'commit': commit, 'parents': identity[1:], 'commit_changes': changes,
            'snapshot_root': request['baseline'], 'source_files': source_rows,
            'verification': 'Controller compared every current-product snapshot file byte-for-byte with git show at this commit. Archived references are separately identified by SHA-256. Runtime should verify snapshot hashes; Git access is unnecessary.'}


def prepare(state, output, php=None, autoload=None, docker_config=None, runtime_config=None):
    root = Path(state['root']);output = Path(output).resolve()
    if state['stage'] != 'build' or (state.get('pending') or {}).get('action') != 'prepare_build':
        raise ValueError('Requires the pending selected experiment')
    bound = state['selection_preparation']
    handoff_path = verify({'path': str(root / bound['path']), 'sha256': bound['sha256']})
    handoff = read(handoff_path);cycle = read(state['cycle'])
    for key, expected in [('selection', cycle['selection']), ('goal', state['goal']), ('answers', state['answers'])]:
        actual = handoff['bindings'][key]
        if actual != ref(root / expected['path']) or actual['sha256'] != expected['sha256']:
            raise ValueError('Prepared experiment belongs to another ' + key)
    request = verify(handoff['creation_request']);assignment = verify(handoff['assignment'])
    verify(handoff['verification_plan'])
    data = read(request)
    sys.path.insert(0, str(Path(state['skills']) / 'atom-building-machinery/scripts'))
    import runtime_adapters
    if runtime_config and (php or autoload or docker_config):
        raise ValueError('Use --runtime-config alone, or the legacy PHP arguments')
    config = read(runtime_config) if runtime_config else runtime_adapters.legacy_config(php,autoload,docker_config)
    runtime = runtime_adapters.prepare(config,data['baseline'],data,output/'runtime')
    scripts = Path(state['skills']) / 'atom-building-machinery/scripts'
    derived = generation_request(data)
    provenance = source_provenance(handoff, data)
    context = json.loads(derived['context'])
    context['source_provenance'] = provenance
    context['runtime_observations'] = runtime
    derived['context'] = json.dumps(context, ensure_ascii=False)
    save(output / 'source-provenance.json', provenance)
    sys.path.insert(0, str(scripts))
    from candidate_builder_contract import prepare as validate_request
    validate_request(derived)
    save(output / 'creation-request.json', derived)
    result = {'preparation': ref(handoff_path), 'original_request': ref(request), 'request': ref(output / 'creation-request.json'), 'assignment': ref(assignment),
              'runtime': runtime, 'builder': ref(scripts / 'candidate_builder.py'),
              'connection': ref(Path(__file__)), 'selection': cycle['selection']}
    save(output / 'bindings.json', result)
    return result


def execute(state, output, php=None, autoload=None, prepare_only=False, docker_config=None, runtime_config=None):
    output = Path(output).resolve();bound = prepare(state, output, php, autoload, docker_config, runtime_config)
    if prepare_only:
        return {'action': 'execution_prepared', 'bindings': str(output / 'bindings.json'),
                'model_calls': 2, 'stages': ['generation', 'confined_execution', 'independent_review']}
    request = verify(bound['request']);assignment = read(verify(bound['assignment']))
    import runtime_adapters
    runtime = bound['runtime'];skills = Path(state['skills'])
    isolation = runtime_adapters.isolation(runtime, output / 'isolation')
    generation = output / 'generation'
    once(output, 'generation', [sys.executable, '-B', str(verify(bound['builder'])), str(request), str(generation)],
         generation, generation / 'result.json')
    candidate = verify_generation(generation, request, skills)
    run = output / 'execution'
    receipt = run / 'result.json'
    if not receipt.exists():
        if run.exists(): raise ValueError('Interrupted execution exists; inspect before repeating the experiment')
        run.mkdir();scratch = run / 'tmp';scratch.mkdir()
        execution_source = run / 'source'
        shutil.copytree(candidate, execution_source)
        candidate = execution_source
        before = files(candidate)
        emit(output, 'isolated_execution_started')
        observed = runtime_adapters.execute(runtime,candidate,run)
        code = observed['returncode'];timed_out = observed['timed_out']
        changes = []
        for row in before:
            p = Path(row['path'])
            if not p.is_file() or sha(p) != row['sha256']: changes.append(str(p.relative_to(candidate)))
        protected_changes = [p for p in changes if p != 'experiment/report.md']
        result = {'returncode': code, 'timed_out': timed_out, 'protected_changes': protected_changes,
                  'generated_report_changed': 'experiment/report.md' in changes, 'isolation': isolation,
                  'stdout': ref(run / 'stdout.txt'), 'stderr': ref(run / 'stderr.txt'),
                  'output_files': files(candidate / 'experiment'), 'command': ref(run / 'command.json')}
        save(receipt, result);emit(output, 'isolated_execution_returned', returncode=code, timed_out=timed_out)
    result = read(receipt)
    for r in result['output_files'] + [result['stdout'], result['stderr'], result['command']]:verify(r)
    if result['protected_changes']: raise ValueError('Generated probe modified protected inputs: ' + str(result['protected_changes']))
    # Review observed execution even when it fails. Failure cannot become completion.
    sys.path.insert(0, str(skills / 'input-interview-machinery/scripts'))
    import checkpoint
    import run as review
    from selection_preparation import obj, array, TEXT
    evidence = []
    for r in result['output_files'] + [result['stdout'], result['stderr']]:
        p = verify(r)
        if p.suffix in ('.php', '.py', '.json', '.md', '.txt'):
            if p.stat().st_size > 500000: raise ValueError('Execution artifact too large for review: ' + str(p))
            evidence.append({'path': r['path'], 'sha256': r['sha256'], 'text': p.read_text()})
    packet = {'assignment': assignment, 'execution': result, 'evidence': evidence,
              'original_source': read(request)['source_units']}
    sys.path.insert(0, str(skills / 'atom-assessment-machinery/scripts'))
    from evidence_transport import pack, unpack
    packed = pack(packet)
    if unpack(packed) != packet: raise ValueError('Review transport changed evidence')
    prompt = ('Assess this actual disposable experiment against each assigned case. Use raw traces and code, not the generated report alone. '
              'Determine whether the real source ran, whether assumptions replaced missing product behavior, and whether the observation supports the case. '
              'A correctly demonstrated missing product connection can satisfy this research experiment. An execution failure cannot. '
              'Return every case once with supported, unsupported or cannot_assess, explain why and quote captured evidence. '
              'Do not claim live identity, payment-provider or full checkout proof. No tools.\n' + json.dumps(packed, ensure_ascii=False, separators=(',', ':')))
    if len(prompt) > 1048576: raise ValueError('Review exceeds CLI input limit; no call made')
    ids = [c['id'] for c in assignment['cases']]
    schema = obj({'cases': array(obj({'id': {'type': 'string', 'enum': ids},
                                     'verdict': {'type': 'string', 'enum': ['supported', 'unsupported', 'cannot_assess']},
                                     'reason': TEXT, 'evidence_path': TEXT, 'quote': TEXT})),
                  'conclusion': TEXT, 'implementation_consequence': TEXT})
    answer, _ = checkpoint.call(output / 'review', 'experiment-review', prompt, schema,
                                lambda p: review.CodexTransport(p, {'provider':'codex','model':'gpt-6-astra','reasoning':'medium'}))
    if [c['id'] for c in answer['cases']] != ids: raise ValueError('Review omitted or reordered assigned cases')
    texts = {x['path']: x['text'] for x in evidence}
    for c in answer['cases']:
        if not c['quote'].strip() or c['quote'] not in texts.get(c['evidence_path'], ''):
            raise ValueError('Review citation does not resolve: ' + c['id'])
    complete = result['returncode'] == 0 and not result['timed_out'] and all(c['verdict']=='supported' for c in answer['cases'])
    handoff = {'status': 'experiment_supported' if complete else 'experiment_needs_attention',
               'selection': bound['selection'], 'generation': ref(generation / 'result.json'),
               'execution': ref(receipt), 'review': answer, 'product_modified': False, 'goal_complete': False}
    save(output / 'handoff.json', handoff)
    return {'action': handoff['status'], 'handoff': str(output / 'handoff.json')}
