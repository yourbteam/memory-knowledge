"""Validate saved live experiment/review preparation without paid calls."""
import json
from pathlib import Path
import sys
import tempfile

from build_preparation import read, verify, sha

P = Path(__file__).resolve().parent


def main():
    state = read(P / 'live/state.json')
    path = Path(state['root']) / state['experiment_preparation']['path']
    assert sha(path) == state['experiment_preparation']['sha256']
    handoff = read(path)
    for key in ['creation_request', 'experiment_rehearsal_request', 'experiment_rehearsal_result', 'review_template', 'review_rehearsal_prompt']:
        verify(handoff[key])
    output = path.parent
    summary = read(output / 'rehearsal/development-probe-summary.json')
    assert summary['verdict'] == 'passed' and summary['promotion_applied'] is False
    verdict_path = output / 'rehearsal/validation/final-verdict.json'
    assert sha(verdict_path) == summary['final_verdict_sha256']
    verdict = read(verdict_path)
    assert len(verdict['cases']) == 5 and all(c['verdict'] == 'satisfied' for c in verdict['cases'])
    packet = read(output / 'review-rehearsal/review.json.source-review/packet.json')
    assert len(packet['changes']) == 3 and len(packet['obligations']) == 7
    assert {'tour-schema', 'tour-index-ddl', 'matching-experiment'} <= {x['id'] for x in packet['sources']}
    assert not (output / 'review-rehearsal/review.json').exists()
    assert not (output / 'candidate-preview/model').exists()
    sys.path.insert(0, str(Path(state['skills']) / 'atom-building-machinery/scripts'))
    from source_review_contract import prepare, ReviewError
    with tempfile.TemporaryDirectory() as temporary:
        changed = Path(temporary) / 'changed-surface.json'
        surface = read(output / 'review-rehearsal/promotion-surface.json')
        surface['changes'][0]['after_sha256'] = '0' * 64
        changed.write_text(json.dumps(surface))
        try:
            prepare(changed, output / 'review-rehearsal/source-review-context.json')
        except ReviewError as error:
            refusal = str(error)
        else:
            raise AssertionError('Changed review surface accepted')
    sys.path.insert(0, str(P / 'verification-preparation-probe-v1'))
    import probe
    assert probe.checkout_fingerprint() == read(P / 'verification-preparation-probe-v1/input-state.json')['checkout_before']
    assert read(Path(state['cycle']))['build'] is None
    result = {'status': 'prepared_and_rehearsed', 'experiment_cases_satisfied': 5,
              'composition_passed': True, 'review_input_accepted': True, 'review_obligations': 7,
              'changed_files_for_review': 3, 'changed_surface_rejected': refusal,
              'live_loop_connected': True, 'model_calls': 0, 'product_changed': False,
              'review_judgment_not_run': True,
              'remaining': 'Generate and bind the real candidate, obtain repository-bound build admission and conduct its actual independent review before promotion. Historical candidate is rehearsal only.'}
    (output / 'preparation-validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
