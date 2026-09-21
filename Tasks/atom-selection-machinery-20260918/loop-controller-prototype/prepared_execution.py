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
MAX_REVIEW_ARTIFACT_BYTES = 500000
MAX_REVIEW_JSON_FIELD_BYTES = 16000


def json_field_metadata(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    result = {
        'transport': 'verified_json_field_metadata',
        'sha256': hashlib.sha256(raw).hexdigest(),
        'serialized_bytes': len(raw),
        'raw_evidence_preserved': True,
        'content_included': False,
    }
    if isinstance(value, (dict, list)):
        result['item_count'] = len(value)
    return result


def bounded_json_projection(path):
    try:
        value = json.loads(path.read_text())
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, None
    if path.name.endswith('.process.json') and isinstance(value, dict):
        return {
            key: json_field_metadata(item) if key in ('stdout', 'stderr') else item
            for key, item in value.items()
        }, 'process_projection'
    if path.name.endswith('.trace.json') and isinstance(value, dict):
        result = {}
        for key, item in value.items():
            raw = json.dumps(item, ensure_ascii=False, separators=(',', ':')).encode()
            result[key] = item if len(raw) <= MAX_REVIEW_JSON_FIELD_BYTES else json_field_metadata(item)
        return result, 'bounded_json_projection'
    return None, None


def source_manifest(source_units):
    result = []
    for unit in source_units:
        text = unit['text']
        raw = text.encode()
        result.append({'path': unit['path'], 'sha256': hashlib.sha256(raw).hexdigest(),
                       'size_bytes': len(raw), 'content_included': False})
    return result


def review_evidence(reference):
    """Return reviewable text without discarding oversized raw evidence."""
    path = verify(reference)
    if path.suffix not in ('.php', '.py', '.json', '.md', '.txt'):
        return None
    size = path.stat().st_size
    projected, transport = bounded_json_projection(path) if path.suffix == '.json' else (None, None)
    paired_trace = path.name.endswith('.stdout.txt') and path.with_name(
        path.name.replace('.stdout.txt', '.trace.json')).exists()
    if projected is not None:
        text = json.dumps(projected, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    elif size <= MAX_REVIEW_ARTIFACT_BYTES and not paired_trace:
        text = path.read_text()
        transport = 'full_text'
    else:
        text = json.dumps({
            'transport': 'verified_metadata_only',
            'path': reference['path'],
            'sha256': reference['sha256'],
            'size_bytes': size,
            'raw_evidence_preserved': True,
            'content_included': False,
        }, ensure_ascii=False, sort_keys=True)
        transport = 'verified_metadata_only'
    return {'path': reference['path'], 'sha256': reference['sha256'],
            'size_bytes': size, 'transport': transport, 'text': text}


def review_schema(ids, evidence_paths, obj, array, text):
    """Require every citation to identify one file and one contiguous quote."""
    citation = obj({
        'evidence_path': {'type': 'string', 'enum': evidence_paths},
        'quote': text,
    })
    return obj({'cases': array(obj({
                    'id': {'type': 'string', 'enum': ids},
                    'verdict': {'type': 'string', 'enum': ['supported', 'unsupported', 'cannot_assess']},
                    'reason': text,
                    'citations': array(citation),
                })),
                'conclusion': text,
                'implementation_consequence': text})


def citation_repair_schema(ids, evidence_paths, obj, array, text):
    citation = obj({
        'evidence_path': {'type': 'string', 'enum': evidence_paths},
        'quote': text,
    })
    return obj({'cases': array(obj({
        'id': {'type': 'string', 'enum': ids},
        'citations': array(citation),
    }))})


def validate_review_citations(answer, ids, texts):
    if [case['id'] for case in answer['cases']] != ids:
        raise ValueError('Review omitted or reordered assigned cases')
    for case in answer['cases']:
        citations = case.get('citations')
        if not citations:
            raise ValueError('Review has no citation: ' + case['id'])
        for citation in citations:
            path = citation['evidence_path']
            quote = citation['quote']
            if not quote.strip() or quote not in texts.get(path, ''):
                raise ValueError('Review citation does not resolve: ' + case['id'])


def saved_legacy_review(folder, ids):
    """Identify the one superseded single-citation contract without translating it."""
    folder = Path(folder)
    step_path = folder / 'step.json'
    if not step_path.exists():
        return None
    step = read(step_path)
    if step.get('status') != 'completed':
        return None
    answer = read(folder / step['answer_file'])
    cases = answer.get('cases')
    if not isinstance(cases, list) or [case.get('id') for case in cases] != ids:
        return None
    if not all(set(case) == {'id', 'verdict', 'reason', 'evidence_path', 'quote'} for case in cases):
        return None
    return answer, step['session']


def repair_legacy_review(output, legacy, session, ids, texts, checkpoint, review, obj, array, text):
    """Ask the original reviewer only to restate citations under the corrected contract."""
    evidence_paths = list(texts)
    schema = citation_repair_schema(ids, evidence_paths, obj, array, text)
    prompt = (
        'Restate only the citations for your completed experiment review. Preserve the prior '
        'verdicts, reasons, conclusion and implementation consequence; do not reassess them. '
        'Return every case once in the supplied order. Each citation must name exactly one '
        'allowed evidence_path and quote one non-empty, exact, contiguous fragment from that '
        'file. Use multiple citation objects when a judgment needs multiple files or fragments. '
        'Never join paths or quotes with semicolons. No tools.\n' +
        json.dumps({'case_ids': ids, 'prior_review': legacy,
                    'allowed_evidence_paths': evidence_paths},
                   ensure_ascii=False, separators=(',', ':'))
    )
    repaired, _ = checkpoint.call(
        Path(output) / 'review-citation-repair',
        'experiment-review-citation-repair',
        prompt,
        schema,
        lambda path: review.CodexTransport(path, {
            'provider': 'codex', 'model': 'gpt-6-astra', 'reasoning': 'medium'}),
        session=session,
    )
    if [case['id'] for case in repaired['cases']] != ids:
        raise ValueError('Citation repair omitted or reordered assigned cases')
    citations = {case['id']: case['citations'] for case in repaired['cases']}
    answer = {
        'cases': [{
            'id': case['id'],
            'verdict': case['verdict'],
            'reason': case['reason'],
            'citations': citations[case['id']],
        } for case in legacy['cases']],
        'conclusion': legacy['conclusion'],
        'implementation_consequence': legacy['implementation_consequence'],
    }
    validate_review_citations(answer, ids, texts)
    return answer


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


def resume_bindings(state, output):
    """Reuse immutable preparation only after generation and execution are receipted."""
    output = Path(output).resolve()
    bindings_path = output / 'bindings.json'
    generation_receipt = output / 'receipts' / 'generation.json'
    execution_receipt = output / 'execution' / 'result.json'
    if not bindings_path.exists():
        return None
    if not generation_receipt.is_file() or not execution_receipt.is_file():
        return None
    if state['stage'] != 'build' or (state.get('pending') or {}).get('action') != 'prepare_build':
        raise ValueError('Requires the pending selected experiment')
    root = Path(state['root'])
    cycle = read(state['cycle'])
    bound = read(bindings_path)
    expected_preparation = ref(root / state['selection_preparation']['path'])
    if bound.get('preparation') != expected_preparation:
        raise ValueError('Saved execution belongs to another preparation')
    if bound.get('selection') != cycle['selection']:
        raise ValueError('Saved execution belongs to another selection')
    for key in ['preparation', 'original_request', 'request', 'assignment', 'builder']:
        verify(bound[key])
    verify(bound['runtime']['receipt'])
    verify(ref(generation_receipt))
    verify(ref(execution_receipt))
    return bound


def root_ref(path, root):
    """Create the loop's root-relative, content-bound reference."""
    root = Path(root).resolve()
    path = Path(path)
    if not path.is_absolute():
        path = root / path
    if path.is_symlink():
        raise ValueError('Research evidence is not a regular file under the loop root: ' + str(path))
    path = path.resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError('Research evidence is not a regular file under the loop root: ' + str(path))
    return {'path': str(path.relative_to(root)), 'sha256': sha(path)}


def completed_handoff(state, output, bound):
    """Verify a completed experiment handoff before reusing it without model calls."""
    output = Path(output).resolve()
    handoff_path = output / 'handoff.json'
    if not handoff_path.exists():
        return None
    handoff = read(handoff_path)
    cycle = read(state['cycle'])
    if handoff.get('selection') != bound['selection'] or handoff['selection'] != cycle['selection']:
        raise ValueError('Prepared execution handoff belongs to another selection')
    expected = {
        'generation': output / 'generation' / 'result.json',
        'execution': output / 'execution' / 'result.json',
    }
    for key, expected_path in expected.items():
        actual_path = verify(handoff[key])
        if actual_path.resolve() != expected_path.resolve():
            raise ValueError('Prepared execution handoff has a changed ' + key)
    cases = handoff.get('review', {}).get('cases')
    if not isinstance(cases, list) or not cases:
        raise ValueError('Prepared execution handoff has no completed review cases')
    root = Path(state['root'])
    for case in cases:
        citations = case.get('citations')
        if not isinstance(citations, list) or not citations:
            raise ValueError('Prepared execution handoff has an uncited review case')
        for citation in citations:
            evidence = root_ref(citation['evidence_path'], root)
            text = (root / evidence['path']).read_text()
            if not citation.get('quote', '').strip() or citation['quote'] not in text:
                raise ValueError('Prepared execution handoff citation no longer resolves: ' + case.get('id', 'unknown'))
    return handoff


def research_result_from_handoff(state, output, handoff_path, handoff):
    """Mechanically bind reviewed experiment evidence to the current cycle."""
    root = Path(state['root'])
    cycle = read(state['cycle'])
    if handoff.get('selection') != cycle['selection']:
        raise ValueError('Prepared experiment result belongs to another selection')
    paths = [handoff_path, handoff['generation']['path'], handoff['execution']['path']]
    for case in handoff['review']['cases']:
        paths.extend(citation['evidence_path'] for citation in case['citations'])
    evidence = []
    seen = set()
    for path in paths:
        reference = root_ref(path, root)
        if reference['path'] not in seen:
            evidence.append(reference)
            seen.add(reference['path'])
    result = {
        'kind': 'selected_research_result',
        'goal': cycle['goal'],
        'selection': cycle['selection'],
        'evidence': evidence,
    }
    destination = Path(output) / 'research-result.json'
    save(destination, result)
    return destination


def completed_execution(output, request, skills):
    """Load and verify completed generation/execution without reopening runtime."""
    output = Path(output).resolve()
    receipt = output / 'execution' / 'result.json'
    if not receipt.exists():
        return None
    verify_generation(output / 'generation', request, skills)
    result = read(receipt)
    for r in result['output_files'] + [result['stdout'], result['stderr'], result['command'], result['isolation']]:
        verify(r)
    return result


def execute(state, output, php=None, autoload=None, prepare_only=False, docker_config=None, runtime_config=None):
    output = Path(output).resolve()
    bound = resume_bindings(state, output) or prepare(state, output, php, autoload, docker_config, runtime_config)
    saved_handoff = completed_handoff(state, output, bound)
    if saved_handoff is not None:
        research_result = research_result_from_handoff(
            state, output, output / 'handoff.json', saved_handoff)
        return {'action': saved_handoff['status'], 'handoff': str(output / 'handoff.json'),
                'research_result': str(research_result), 'model_calls': 0}
    if prepare_only:
        return {'action': 'execution_prepared', 'bindings': str(output / 'bindings.json'),
                'model_calls': 2, 'stages': ['generation', 'confined_execution', 'independent_review']}
    request = verify(bound['request']);assignment = read(verify(bound['assignment']))
    skills = Path(state['skills'])
    generation = output / 'generation'
    run = output / 'execution'
    receipt = run / 'result.json'
    result = completed_execution(output, request, skills)
    if result is None:
        import runtime_adapters
        runtime = bound['runtime']
        isolation = runtime_adapters.isolation(runtime, output / 'isolation')
        once(output, 'generation', [sys.executable, '-B', str(verify(bound['builder'])), str(request), str(generation)],
             generation, generation / 'result.json')
        candidate = verify_generation(generation, request, skills)
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
    if result['protected_changes']: raise ValueError('Generated probe modified protected inputs: ' + str(result['protected_changes']))
    # Review observed execution even when it fails. Failure cannot become completion.
    sys.path.insert(0, str(skills / 'input-interview-machinery/scripts'))
    import checkpoint
    import run as review
    from selection_preparation import obj, array, TEXT
    evidence = []
    for r in result['output_files'] + [result['stdout'], result['stderr']]:
        item = review_evidence(r)
        if item is not None:
            evidence.append(item)
    packet = {'assignment': assignment, 'execution': result, 'evidence': evidence,
              'original_source_manifest': source_manifest(read(request)['source_units'])}
    sys.path.insert(0, str(skills / 'atom-assessment-machinery/scripts'))
    from evidence_transport import pack, unpack
    packed = pack(packet)
    if unpack(packed) != packet: raise ValueError('Review transport changed evidence')
    prompt = ('Assess this actual disposable experiment against each assigned case. Use code and bounded trace projections, not the generated report alone. '
              'Determine whether the real source ran, whether assumptions replaced missing product behavior, and whether the observation supports the case. '
              'A correctly demonstrated missing product connection can satisfy this research experiment. An execution failure cannot. '
              'Return every case once with supported, unsupported or cannot_assess, explain why and cite captured evidence. '
              'Each citation must identify exactly one supplied evidence path and one exact contiguous quote from that file. '
              'Use multiple citation objects when a judgment needs multiple files or fragments; never join paths or quotes. '
              'Metadata-only entries prove artifact identity and preservation, not omitted content. '
              'Do not claim live identity, payment-provider or full checkout proof. No tools.\n' + json.dumps(packed, ensure_ascii=False, separators=(',', ':')))
    if len(prompt) > 1048576: raise ValueError('Review exceeds CLI input limit; no call made')
    ids = [c['id'] for c in assignment['cases']]
    texts = {x['path']: x['text'] for x in evidence}
    legacy = saved_legacy_review(output / 'review', ids)
    if legacy:
        answer = repair_legacy_review(output, legacy[0], legacy[1], ids, texts,
                                      checkpoint, review, obj, array, TEXT)
    else:
        schema = review_schema(ids, list(texts), obj, array, TEXT)
        answer, _ = checkpoint.call(
            output / 'review', 'experiment-review', prompt, schema,
            lambda p: review.CodexTransport(p, {
                'provider':'codex', 'model':'gpt-6-astra', 'reasoning':'medium'}))
        validate_review_citations(answer, ids, texts)
    complete = result['returncode'] == 0 and not result['timed_out'] and all(c['verdict']=='supported' for c in answer['cases'])
    handoff = {'status': 'experiment_supported' if complete else 'experiment_needs_attention',
               'selection': bound['selection'], 'generation': ref(generation / 'result.json'),
               'execution': ref(receipt), 'review': answer, 'product_modified': False, 'goal_complete': False}
    save(output / 'handoff.json', handoff)
    research_result = research_result_from_handoff(
        state, output, output / 'handoff.json', handoff)
    return {'action': handoff['status'], 'handoff': str(output / 'handoff.json'),
            'research_result': str(research_result)}
