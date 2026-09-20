"""Connect proven verification to the existing candidate builder's prepare-only path.

No model calls, product writes, admission grants, or driver execution. The supplied
historical creation template contributes dependency context, never old authorization.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import xml.etree.ElementTree as ET


def read(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Required regular preparation input missing: ' + str(path))
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ref(path):
    return {'path': str(Path(path).absolute()), 'sha256': sha(path)}


def save(path, data):
    path = Path(path)
    raw = (json.dumps(data, indent=2, ensure_ascii=False) + '\n').encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError('Prepared output changed: ' + str(path))
    else:
        path.write_bytes(raw)


def verify(reference):
    path = Path(reference['path'])
    if not path.is_absolute() or path.is_symlink() or not path.is_file() or sha(path) != reference['sha256']:
        raise ValueError('Changed preparation evidence: ' + str(path))
    return path


def relative(path):
    p = PurePosixPath(path)
    if p.is_absolute() or '..' in p.parts or str(p) != path:
        raise ValueError('Unsafe relative preparation path: ' + path)
    return path


def prepare(state, verification, assignment_run, template_path, repository, output):
    verification, assignment_run, template_path, repository, output = map(
        lambda p: Path(p).absolute(), [verification, assignment_run, template_path, repository, output])
    root = Path(state['root'])
    cycle = read(state['cycle'])
    if state['stage'] != 'build' or (state.get('pending') or {}).get('action') != 'prepare_build':
        raise ValueError('Verification preparation requires the pending selected build')
    selection = verify({'path': str(root / cycle['selection']['path']), 'sha256': cycle['selection']['sha256']})
    lineage = read(assignment_run / 'sources.json')
    for key, expected in [('selection', cycle['selection']), ('goal_context', state['goal']), ('current_answers', state['answers'])]:
        if lineage[key]['sha256'] != expected['sha256'] or sha(assignment_run / 'sources' / (key + '.json')) != expected['sha256']:
            raise ValueError('Assignment belongs to a different ' + key)
    assignment_path = assignment_run / 'assignment.json'
    assignment = read(assignment_path)
    if assignment['missing_information']:
        raise ValueError('Assignment still needs information: ' + str(assignment['missing_information']))
    manifest = read(verification / 'sources.json')
    refs = [ref(selection), ref(assignment_path), ref(assignment_run / 'sources.json'), ref(template_path)]
    for row in manifest.values():
        p = verification / relative(row['copy'])
        verify({'path': str(p), 'sha256': row['sha256']})
        refs.append(ref(p))
    if manifest['assignment']['sha256'] != sha(assignment_path):
        raise ValueError('Verification assessed a different assignment')
    assessment = read(verification / 'assessment.json')
    if assessment != read(verification / 'model/attempts/0001/answer.json'):
        raise ValueError('Verification decision differs from the saved model answer')
    report = read(verification / 'result.json')
    frozen = read(verification / 'input-state.json')
    if assessment['decision'] != 'reuse' or assessment['needed_changes'] or report['status'] != 'prototype_passed':
        raise ValueError('Verification is not an unchanged, proven reuse decision')
    ids = assignment['case_ids']
    mapping = {x['case_id']: x['test_method'] for x in assessment['cases']}
    if len(mapping) != len(assessment['cases']) or set(mapping) != set(ids):
        raise ValueError('Verification must cover every assigned case exactly once')
    test = verification / manifest['test']['copy']
    expected_pairs = {(r, c) for r in ['baseline', 'historical-control'] for c in ids}
    observed = set()
    for row in report['execution']:
        pair = (row['root'], row['case_id'])
        if pair not in expected_pairs or pair in observed:
            raise ValueError('Unexpected or duplicate verification case: ' + str(pair))
        observed.add(pair)
        evidence = verification / 'execution' / row['root'] / row['case_id']
        if read(evidence / 'result.json') != row or row['test_sha256'] != sha(test):
            raise ValueError('Execution record or test binding changed: ' + str(pair))
        xml = evidence / 'junit.xml'
        verify({'path': str(xml), 'sha256': row['junit_sha256']})
        nodes = ET.parse(xml).getroot().findall('.//testcase')
        if len(nodes) != 1 or nodes[0].get('name') != mapping[row['case_id']]:
            raise ValueError('JUnit does not execute the selected method: ' + str(pair))
        node = nodes[0]
        if node.findall('error') or node.findall('skipped'):
            raise ValueError('Verification has a runtime error or skipped case: ' + str(pair))
        if row['root'] == 'historical-control':
            if row['returncode'] != 0 or node.findall('failure') or int(node.get('assertions', 0)) <= 0:
                raise ValueError('Historical control did not pass: ' + str(pair))
        else:
            failures = node.findall('failure')
            missing = [str(verification / 'baseline' / p) for p, present in frozen['product_paths_present'].items() if not present]
            if row['returncode'] != 1 or len(failures) != 1 or not any('Missing product file: ' + p in (failures[0].text or '') for p in missing):
                raise ValueError('Baseline failure was not the demonstrated missing feature: ' + str(pair))
        refs.extend([ref(evidence / 'result.json'), ref(xml)])
    if observed != expected_pairs:
        raise ValueError('Missing verification executions: ' + str(expected_pairs - observed))
    for name in ['sources.json', 'assessment.json', 'result.json', 'input-state.json', 'model/attempts/0001/answer.json']:
        refs.append(ref(verification / name))
    def git(*args):
        return subprocess.run(['git', '-C', str(repository), *args], capture_output=True, check=True).stdout
    commit = git('rev-parse', frozen['branch']).decode().strip()
    if commit != frozen['commit']:
        raise ValueError('Delivery branch moved since verification; refresh baseline evidence')
    template = read(template_path)
    output.mkdir(parents=True, exist_ok=True)
    baseline = output / 'baseline'
    baseline.mkdir(exist_ok=True)
    # Historical source-unit names select context; all existing source comes from
    # the frozen delivery commit, never the current working checkout or old code.
    paths = set(assignment['allowed_paths']) | {'composer.json', 'composer.lock'}
    paths.update(relative(u['path'].removeprefix(repository.name + '/')) for u in template['source_units'])
    for path in sorted(paths):
        relative(path)
        if not git('ls-tree', commit, '--', path).strip():
            continue
        raw = git('show', commit + ':' + path)
        target = baseline / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != raw:
            raise ValueError('Builder baseline changed: ' + path)
        target.write_bytes(raw)
    files = [{'path': p.relative_to(baseline).as_posix(), 'sha256': sha(p)} for p in sorted(baseline.rglob('*')) if p.is_file()]
    baseline_expected = {p for p in paths if git('ls-tree', commit, '--', p).strip()}
    if {r['path'] for r in files} != baseline_expected:
        raise ValueError('Builder baseline contains files outside its committed source catalog')
    units = [{'path': r['path'], 'text': (baseline / r['path']).read_text()} for r in files if r['path'] != 'composer.lock']
    historical_context = json.loads(template['context'])
    test_paths = [p for p in assignment['allowed_paths'] if Path(p).name == test.name]
    if len(test_paths) != 1:
        raise ValueError('Frozen verification needs one matching test destination in the assigned paths')
    verification_context = {'test': {'destination': test_paths[0], 'sha256': sha(test), 'text': test.read_text()},
                            'selected_cases': assessment['cases'],
                            'actual_comparison': {k: report[k] for k in ['historical_cases_passed', 'baseline_cases_detecting_missing_feature', 'cases_per_root']},
                            'unverified_obligations': assessment['outside_test_coverage'],
                            'runtime': frozen['runtime']}
    creation = {'schema_version': 1, 'outcome': assignment['outcome'],
                'constraints': 'Implement only the admitted assignment within its allowed paths. Preserve unrelated behavior. The supplied verification source is frozen: reuse its exact bytes when adding its declared test file; do not weaken or rewrite it. Do not treat historical-control success as a completed product build. Retain the assignment stopping condition and all unverified obligations for later review and validation. No deployment, external systems or authorization is granted by this preparation.',
                'allowed_paths': assignment['allowed_paths'], 'baseline': str(baseline), 'files': files,
                'source_units': units,
                'context': json.dumps({'selected_atom': read(selection), 'assignment': assignment,
                     'verification': verification_context,
                     'historical_schema_evidence': historical_context.get('existing_schema'),
                     'schema_evidence_boundary': 'Historical supplied schema evidence; verify target compatibility as required by the assignment. Not a current database execution.'}, ensure_ascii=False)}
    save(output / 'creation-request.json', creation)
    save(output / 'verification.json', verification_context)
    script = Path(state['skills']) / 'atom-building-machinery/scripts/candidate_builder.py'
    preview = output / 'builder-preview'
    if preview.exists():
        if (preview / 'request.json').read_bytes() != (output / 'creation-request.json').read_bytes():
            raise ValueError('Saved builder preview belongs to another preparation')
        # Check the exact deterministic prompt on resume, without a paid call.
        sys.path.insert(0, str(script.parent))
        from candidate_builder import INSTRUCTION
        from candidate_builder_contract import prepare as builder_prepare
        expected = INSTRUCTION + '\n' + json.dumps(builder_prepare(creation), ensure_ascii=False)
        if (preview / 'prompt.txt').read_text() != expected:
            raise ValueError('Builder preview changed after preparation')
    else:
        proc = subprocess.run([sys.executable, '-B', str(script), str(output / 'creation-request.json'), str(preview), '--prepare-only'], capture_output=True, text=True)
        if proc.returncode:
            raise ValueError('Existing builder refused prepared verification: ' + proc.stdout + proc.stderr)
    refs.extend([ref(script), ref(script.with_name('candidate_builder_contract.py'))])
    handoff = {'schema_version': 1, 'status': 'verification_prepared', 'selection': ref(selection),
               'assignment': ref(assignment_path), 'baseline_commit': commit,
               'creation_request': ref(output / 'creation-request.json'), 'verification': ref(output / 'verification.json'),
               'builder_prompt': ref(preview / 'prompt.txt'), 'evidence': refs,
               'product_started': False, 'model_calls': 0,
               'remaining': ['Authorized candidate build and complete experiment/review/validation preparation remain required.'],
               'unverified_obligations': assessment['outside_test_coverage']}
    save(output / 'handoff.json', handoff)
    return output / 'handoff.json'
