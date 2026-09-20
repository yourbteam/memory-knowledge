"""Prepare selected-atom experiments and independent review from proven inputs.

The historical implementation is a rehearsal candidate only. This module does not
grant admission, generate product code, run a review model or promote a candidate.
"""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys

from build_preparation import read, ref, save, sha, verify

P = Path(__file__).resolve().parent
HISTORY = P.parents[2] / 'Tasks/taggable-cross-location-discount-atoms-20260911/tour-prerequisite-structure'


def invoke(argv):
    p = subprocess.run(argv, capture_output=True, text=True)
    if p.returncode:
        raise ValueError('Preparation command failed: ' + p.stdout + p.stderr)
    return p.stdout


def tree_hash(skills, path):
    return invoke([sys.executable, '-B', str(skills / 'experiment-machinery/scripts/run_experiment.py'), '--hash-source', str(path)]).strip()


def prepare(state, output):
    output = Path(output).resolve()
    root = Path(state['root'])
    prepared_path = verify({'path': str(root / state['build_preparation']['path']), 'sha256': state['build_preparation']['sha256']})
    prepared = read(prepared_path)
    for reference in prepared['evidence'] + [prepared['creation_request'], prepared['verification'], prepared['assignment'], prepared['selection']]:
        verify(reference)
    cycle = read(state['cycle'])
    if prepared['selection']['sha256'] != cycle['selection']['sha256'] or state['stage'] != 'build':
        raise ValueError('Preparation must belong to the current unstarted selected build')
    assignment = read(prepared['assignment']['path'])
    verification = read(prepared['verification']['path'])
    creation = read(prepared['creation_request']['path'])
    skills = Path(state['skills'])
    output.mkdir(parents=True, exist_ok=True)
    save(output / 'input.json', {'build_preparation': ref(prepared_path), 'mode': 'historical rehearsal; no product admission'})
    admitted = read(P / 'assignment-admission-probe-v1/admission-only/atom-request.json')
    if admitted['outcome'] != assignment['outcome'] or admitted['allowed_paths'] != assignment['allowed_paths']:
        raise ValueError('Admitted assignment and prepared verification differ')
    case_root = output / 'case-sources'
    case_root.mkdir(exist_ok=True)
    for c in admitted['captured_cases']:
        source = P / 'assignment-admission-probe-v1/admission-only' / c['source_ref']
        assert sha(source) == c['sha256']
        target = case_root / c['source_ref']
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():shutil.copy2(source, target)
        assert sha(target) == c['sha256']
    manifest = read(HISTORY / 'comparison-manifest.json')
    manifest['case_source_root'] = str(case_root)
    manifest['atomic_step'] = {'id': admitted['atomic_step_id'], **{k: admitted[k] for k in ['outcome', 'practical_value', 'stopping_condition']},
                              'captured_cases': [{'id': c['case_id'], **{k: v for k, v in c.items() if k != 'case_id'}} for c in admitted['captured_cases']]}
    probe = manifest['mini_probes'][0]
    probe.update(goal=admitted['outcome'], practical_value=admitted['practical_value'], allowed_paths=admitted['allowed_paths'],
                 work_type_reason='Compare unchanged baseline with a candidate using the independently selected frozen tests.')
    probe['approaches'][1].update(hypothesis='The candidate satisfies all five selected cases.',
                                  implementation='Execute the exact frozen tests against the candidate source.',
                                  predicted_tradeoff='SQLite functional proof; MySQL compatibility remains a separate review obligation.')
    probe['winner_output']['description'] = 'Candidate source passing all declared functional cases; not product completion.'
    manifest['composition']['assembly_contract'] = 'Compose only the three allowed source paths and execute the frozen tests unchanged.'
    save(output / 'manifest.json', manifest)
    invoke([sys.executable, '-B', str(skills / 'experiment-machinery/scripts/development_probe_manifest.py'), 'validate', str(output / 'manifest.json')])
    baseline = output / 'baseline'
    if not baseline.exists():shutil.copytree(creation['baseline'], baseline)
    # Reuse the proven executor, adapting only its source root and frozen test path.
    source = (HISTORY / 'execution_adapter.py').read_text()
    old = "TEST = HOME_TASK / 'verification-live-01/candidate/taggable-server/tests/Unit/TourDiscountPrerequisitesTest.php'"
    assert old in source
    test = P / 'verification-preparation-probe-v1/sources/TourDiscountPrerequisitesTest.php'
    source = source.replace(old, 'TEST = Path(' + repr(str(test)) + ')')
    assert "Path(__file__).parent / 'taggable-server'" in source
    source = source.replace("Path(__file__).parent / 'taggable-server'", 'Path(__file__).parent')
    entry = baseline / 'probe.py'
    if entry.exists():assert entry.read_text() == source
    else:entry.write_text(source)
    # The eventual generated candidate must share the experiment baseline, including
    # the unchanged executor. The executor remains outside the product edit scope.
    generation = copy.deepcopy(creation)
    generation['baseline'] = str(baseline)
    generation['files'] = [{'path': p.relative_to(baseline).as_posix(), 'sha256': sha(p)}
                           for p in sorted(baseline.rglob('*')) if p.is_file()]
    save(output / 'creation-request.json', generation)
    if not (output / 'candidate-preview').exists():
        invoke([sys.executable, '-B', str(skills / 'atom-building-machinery/scripts/candidate_builder.py'),
                str(output / 'creation-request.json'), str(output / 'candidate-preview'), '--prepare-only'])
    candidate = output / 'historical-rehearsal-candidate'
    if not candidate.exists():
        shutil.copytree(baseline, candidate)
        for path in assignment['allowed_paths']:
            source_path = test if path == verification['test']['destination'] else P / 'verification-preparation-probe-v1/historical-control' / path
            target = candidate / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target)
    for name in ['judge.py', 'comparison-reference.json']:
        target = output / name
        if not target.exists():shutil.copy2(HISTORY / name, target)
    # Calibration uses this run's measured negative and positive observations.
    measured = read(P / 'verification-preparation-probe-v1/result.json')
    calibration = {'schema_version': 1, 'cases': []}
    for label in ['baseline', 'historical-control']:
        row = next(r for r in measured['execution'] if r['root'] == label)
        raw = {k: row[k] for k in ['case_id', 'returncode', 'test_sha256', 'junit_sha256']}
        raw['tests'] = [{**t, 'failures': len(t['failures']), 'errors': len(t['errors'])} for t in row['tests']]
        calibration['cases'].append({'id': label, 'outcome': {'raw': raw}, 'expected_metrics': {'correct-decision': 0 if label == 'baseline' else 1}})
    save(output / 'calibration.json', calibration)
    for name, source_root in [('control', baseline), ('candidate', candidate)]:
        save(output / ('build-' + name + '.json'), {'schema_version': 1, 'development_manifest': str(output / 'manifest.json'),
             'probe_id': probe['id'], 'approach_id': name,
             'source': {'baseline': str(baseline), 'candidate': str(source_root), 'entrypoint': 'probe.py'},
             'execution': {'protocol': 'experiment-result-v1', 'command': ['{python}', '{candidate-entrypoint}']}})
    cross = read(HISTORY / 'comparison-cross-case.json')
    cross['development_manifest'] = str(output / 'manifest.json')
    for item in cross['approach_build_requests']:item['request'] = str(output / ('build-' + item['approach_id'] + '.json'))
    cross['evaluator']['adapter'] = ref(output / 'judge.py')
    cross['assessment']['reference'] = ref(output / 'comparison-reference.json')
    cross['calibration'] = ref(output / 'calibration.json')
    save(output / 'cross-case.json', cross)
    experiment = read(HISTORY / 'comparison-run-request.json')
    experiment['development_manifest'] = ref(output / 'manifest.json')
    experiment['baseline'] = {'path': str(baseline), 'sha256': tree_hash(skills, baseline)}
    experiment['probe_requests'] = [{'probe_id': probe['id'], 'request': str(output / 'cross-case.json'), 'request_sha256': sha(output / 'cross-case.json')}]
    experiment['assessment']['adapter'] = ref(output / 'judge.py')
    save(output / 'experiment-request.json', experiment)
    # Preserve requirements verbatim; do not infer a passing review from tests.
    requirement = output / 'assignment.txt'
    requirement_text = '\n\n'.join(assignment[k] for k in ['outcome', 'stopping_condition', 'proof'])
    if requirement.exists():assert requirement.read_text() == requirement_text
    else:requirement.write_text(requirement_text)
    def review_source(path, role, identity):
        return {'id': identity, 'role': role, 'path': str(path), 'origin': str(path), 'sha256': sha(path), 'text': path.read_text()}
    sources = [review_source(requirement, 'requirement', 'current-assignment'),
               review_source(P / 'assignment-admission-probe-v1/admission-only/atom-request.json', 'requirement', 'assigned-cases'),
               review_source(baseline / 'composer.json', 'context', 'current-dependencies'),
               review_source(baseline / 'app/Tours.php', 'context', 'current-tour-model')]
    old_review = read(HISTORY / 'promotion-input/source-review-context.json')
    for s in old_review['sources']:
        if s['id'] in ['tour-schema', 'tour-index-ddl']:
            verify({'path': s['origin'], 'sha256': s['sha256']})
            sources.append(s)
    obligations = [{'id': c['case_id'], 'evidence': [{'source_id': 'assigned-cases', 'quote': c['expected_outcome']}]} for c in admitted['captured_cases']]
    obligations += [{'id': name, 'evidence': [{'source_id': 'current-assignment', 'quote': assignment[field]}]}
                    for name, field in [('assignment-boundary', 'stopping_condition'), ('required-proof', 'proof')]]
    review = {'schema_version': 1, 'surface_sha256': None, 'outcome': assignment['outcome'], 'obligations': obligations, 'sources': sources}
    save(output / 'review-template.json', review)
    save(output / 'plan.json', {'status': 'prepared_for_rehearsal', 'build_preparation': ref(prepared_path),
         'experiment': ref(output / 'experiment-request.json'), 'review_template': ref(output / 'review-template.json'),
         'candidate_binding': 'Replace only the candidate source reference with the verified actual candidate, then regenerate hashes before execution.',
         'review_binding': 'Bind actual changed sources and matching experiment evidence after execution; invoke existing independent source review.',
         'product_execution_authorized': False, 'paid_model_calls': 0})
    return output / 'plan.json'


def review_prepare(state, output):
    """Rehearse the exact review entrypoint using the actual experiment assembly."""
    output = Path(output).resolve()
    summary = read(output / 'rehearsal/development-probe-summary.json')
    assembly = output / 'rehearsal/composition/assembly'
    spec = read(assembly / 'assembly.json')
    review = read(output / 'review-template.json')
    changes = []
    for op in spec['operations']:
        assert op['action'] == 'add', op
        path = assembly / 'source' / op['path']
        assert sha(path) == op['sha256']
        changes.append({'path': op['path'], 'kind': 'added', 'before_sha256': None, 'after_sha256': sha(path), 'before_mode': None, 'after_mode': 0o644})
        review['sources'].append({'id': 'after-' + str(len(changes)), 'role': 'after', 'path': op['path'], 'origin': str(path), 'sha256': sha(path), 'text': path.read_text()})
    evidence = output / 'rehearsal/development-probe-summary.json'
    review['sources'].append({'id': 'matching-experiment', 'role': 'evidence', 'path': str(evidence), 'origin': str(evidence), 'sha256': sha(evidence), 'text': evidence.read_text()})
    dest = output / 'review-rehearsal'
    surface = {'schema_version': 1, 'changes': sorted(changes, key=lambda c: c['path'])}
    save(dest / 'promotion-surface.json', surface)
    review['surface_sha256'] = sha(dest / 'promotion-surface.json')
    save(dest / 'source-review-context.json', review)
    save(dest / 'request.json', {'prepared_files': [ref(dest / 'source-review-context.json')]})
    script = Path(state['skills']) / 'atom-building-machinery/scripts/source_review.py'
    result = invoke([sys.executable, '-B', str(script), str(dest / 'promotion-surface.json'), str(dest / 'review.json'), '--prepare-only'])
    save(output / 'review-preparation-result.json', json.loads(result))
    return json.loads(result)


def finish(state, output):
    """Real loop preparation: validate experiment and review without product work."""
    output = Path(output).resolve()
    prepare(state, output)
    if not (output / 'rehearsal').exists():
        invoke([sys.executable, '-B', str(Path(state['skills']) / 'experiment-machinery/scripts/development_probe_run.py'),
                'run', str(output / 'experiment-request.json'), str(output / 'rehearsal')])
    final = read(output / 'rehearsal/development-probe-summary.json')
    if final.get('verdict') != 'passed' or final.get('promotion_applied') is not False:
        raise ValueError('Experiment preparation rehearsal did not pass without promotion')
    if not (output / 'review-preparation-result.json').exists():review_prepare(state, output)
    reviewed = read(output / 'review-preparation-result.json')
    if reviewed.get('status') != 'prepared' or sha(reviewed['prompt']) != reviewed['sha256']:
        raise ValueError('Independent review preparation changed or did not prepare')
    handoff = {'schema_version': 1, 'status': 'experiment_and_review_prepared',
               'selection': read(Path(state['root']) / state['build_preparation']['path'])['selection'],
               'creation_request': ref(output / 'creation-request.json'),
               'experiment_rehearsal_request': ref(output / 'experiment-request.json'),
               'experiment_rehearsal_result': ref(output / 'rehearsal/development-probe-summary.json'),
               'review_template': ref(output / 'review-template.json'),
               'review_rehearsal_prompt': ref(reviewed['prompt']),
               'model_calls': 0, 'product_started': False,
               'next': 'Generate the actual bounded candidate from creation_request, bind that candidate to a fresh experiment, then obtain its independent review. Historical rehearsal is not that candidate.',
               'full_driver_admission': 'Not granted by preparation; the prior receipt remains disposable-root-only.'}
    save(output / 'handoff.json', handoff)
    return output / 'handoff.json'


if __name__ == '__main__':
    state = read(P / 'live/state.json')
    output = P / 'execution-preparation-v1'
    if sys.argv[1] == 'prepare':print(prepare(state, output))
    elif sys.argv[1] == 'review':print(json.dumps(review_prepare(state, output)))
    else:raise SystemExit('Use prepare or review')
