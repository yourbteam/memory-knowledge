"""Replay captured review evidence against the real promotion and assessment boundaries."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
from build_preparation import read, sha

P = Path(__file__).resolve().parent


def run():
    s = read(P / 'live/state.json'); root = Path(s['root']); skills = Path(s['skills'])
    execution = Path(s['cycle']).parent / 'candidate-execution-attempt2'
    review = execution / 'review-attempt3'
    old = read(execution / 'review-attempt2/preview.json.source-review/packet.json')
    new = read(review / 'preview.json.source-review/packet.json')
    assert new['decision'] == 'candidate_application'
    assert old['obligations'] == new['obligations'] and old['outcome'] == new['outcome']
    assert old['changes'] == new['changes']
    # Exercise the actual writer's refusal using the captured failed review. Only
    # the already-verified admission/assembly setup and model adapter are isolated.
    sys.path.insert(0, str(skills / 'atom-building-machinery/scripts'))
    import atom_driver as driver
    assignment = read(P / 'assignment-admission-probe-v1/admission-only/atom-request.json')
    failed = read(execution / 'review-attempt2/review.json')
    def failed_adapter(request, stage, surface, target, output):
        # Bind the saved negative judgment to this test's temporary surface so
        # refusal tests the failed verdict, not an unrelated hash mismatch.
        return {**failed, 'change_surface_sha256': sha(surface)}
    experiment_state = {'current_experiment': {'experiment_path': str(execution / 'experiment'), 'assembly_sha256': 'already-verified-by-saved-experiment'}}
    with tempfile.TemporaryDirectory(dir=P) as temp:
        dest = Path(temp)
        with patch.object(driver.controller, '_request', return_value=assignment), \
             patch.object(driver.controller, '_baseline', return_value=({'files': []}, 'isolated-admission-setup')), \
             patch.object(driver.controller, '_verify_assembly'), \
             patch.object(driver, 'adapter', side_effect=failed_adapter), \
             patch.object(driver.os, 'replace', side_effect=AssertionError('Failed review attempted a write')):
            try:driver.promote({}, dest, dest / 'atom', experiment_state, dest / 'product')
            except driver.Refusal as error:blocked = str(error)
            else:raise AssertionError('Failed review allowed application')
        assert not (dest / 'promotion-authorized.json').exists()
        assert not (dest / 'product').exists()
        spec = importlib.util.spec_from_file_location('assessment_context', skills / 'atom-assessment-machinery/scripts/context.py')
        module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        actual = module.assemble(root, Path(s['cycle']))
        assert any(x['role'] == 'build' and x['code'] == 'missing_record' for x in actual['missing_or_inconsistent'])
        # Deliberately attach the real candidate handoff as if it were a completed
        # build. This negative boundary probe must refuse it before model calls.
        cycle = copy.deepcopy(read(s['cycle']))
        candidate = review / 'handoff.json'
        if not candidate.exists():candidate = execution / 'review-attempt2/handoff.json'
        cycle['build'] = {'path': str(candidate.relative_to(root)), 'sha256': sha(candidate)}
        altered = dest / 'cycle.json';altered.write_text(json.dumps(cycle))
        rejected = module.assemble(root, altered)
        assert any(x['code'] == 'build_not_completed' for x in rejected['missing_or_inconsistent'])
    result = {'unchanged_full_requirements': True, 'unchanged_candidate_surface': True,
              'failed_review_blocks_actual_writer': blocked,
              'negative_writer_test_boundary': 'Saved failed model verdict; admitted setup isolated, real promote function and no-write boundary exercised.',
              'actual_cycle_without_delivery_needs_build': True,
              'candidate_handoff_rejected_as_completed_build': True, 'paid_calls': 0}
    (review / 'stage-boundary-checks.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':run()
