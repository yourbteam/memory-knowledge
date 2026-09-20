"""Exercise the connection through the actual loop CLI and builder preparation."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

P = Path(__file__).resolve().parent
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    proof = P / 'build-preparation-connection-proof-v1'
    proof.mkdir(exist_ok=False)
    before = sha(P / 'live/state.json')
    s = read(P / 'live/state.json')
    cycle = read(Path(s['cycle']))
    assert cycle['build'] is None and cycle['assessment'] is None
    (proof / 'cycle.json').write_text(json.dumps(cycle, indent=2))
    s['cycle'] = str(proof / 'cycle.json')
    (proof / 'state.json').write_text(json.dumps(s, indent=2))
    args = [sys.executable, '-B', str(P / 'loop.py'), 'prepare-build', '--run', str(proof),
            '--verification', str(P / 'verification-preparation-probe-v1'),
            '--assignment-run', str(P / 'assignment-admission-probe-v1'),
            '--creation-template', str(P.parents[2] / 'Tasks/taggable-cross-location-discount-atoms-20260911/tour-prerequisite-structure/implementation-creation-request.json'),
            '--repository', '/Users/kamenkamenov/taggable-server']
    # P is <repo>/Tasks/<task>/<prototype>, so repository root is parents[2].
    results = []
    for name in ['first', 'resume']:
        proc = subprocess.run(args, capture_output=True, text=True)
        (proof / (name + '.stdout')).write_text(proc.stdout)
        (proof / (name + '.stderr')).write_text(proc.stderr)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        action = json.loads(proc.stdout.splitlines()[-1])
        assert action['action'] == 'verification_prepared'
        results.append(action)
    h = read(proof / 'build-preparation/handoff.json')
    request = read(Path(h['creation_request']['path']))
    context = json.loads(request['context'])
    expected_test = (P / 'verification-preparation-probe-v1/sources/TourDiscountPrerequisitesTest.php').read_text()
    assert context['verification']['test']['text'] == expected_test
    assert context['assignment'] == read(P / 'assignment-admission-probe-v1/assignment.json')
    assert context['verification']['unverified_obligations'] == read(P / 'verification-preparation-probe-v1/assessment.json')['outside_test_coverage']
    assert len(context['verification']['selected_cases']) == 5
    assert request['allowed_paths'] == context['assignment']['allowed_paths']
    assert not (proof / 'build-preparation/builder-preview/model').exists()
    assert read(proof / 'state.json')['pending']['action'] == 'prepare_build'
    assert read(proof / 'cycle.json')['build'] is None
    assert sha(P / 'live/state.json') == before
    from build_preparation import prepare
    rejections = []
    changed = copy.deepcopy(s)
    changed['answers']['sha256'] = '0' * 64
    try:
        prepare(changed, P / 'verification-preparation-probe-v1', P / 'assignment-admission-probe-v1', Path(args[-3]), Path(args[-1]), proof / 'wrong-answers')
    except ValueError as e:
        assert 'different current_answers' in str(e), str(e)
        rejections.append(str(e))
    else:
        raise AssertionError('Changed input answers were accepted')
    broken = proof / 'changed-verification'
    shutil.copytree(P / 'verification-preparation-probe-v1', broken)
    data = read(broken / 'assessment.json')
    data['cases'][0]['test_method'] = data['cases'][1]['test_method']
    (broken / 'assessment.json').write_text(json.dumps(data))
    try:
        prepare(s, broken, P / 'assignment-admission-probe-v1', Path(args[-3]), Path(args[-1]), proof / 'changed-answer')
    except ValueError as e:
        assert 'differs from the saved model answer' in str(e), str(e)
        rejections.append(str(e))
    else:
        raise AssertionError('Edited model test mapping accepted')
    result = {'status': 'passed', 'actual_loop_cli': True, 'existing_builder_prepare_only': True,
              'resume_same_handoff': results[0] == results[1], 'test_source_preserved': True,
              'all_five_cases_preserved': True, 'coverage_limits_preserved': True,
              'assignment_preserved': True, 'model_calls': 0, 'live_state_unchanged': True,
              'product_build_not_marked_complete': True, 'rejections': rejections}
    (proof / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
