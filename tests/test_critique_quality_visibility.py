"""Declared-check visibility; model recall is not under test."""
import json
import pytest
import importlib.util
from pathlib import Path
_fixture_spec = importlib.util.spec_from_file_location('visibility_fixture', Path(__file__).with_name('test_critique_quality_acceptance.py'))
_fixture_module = importlib.util.module_from_spec(_fixture_spec)
_fixture_spec.loader.exec_module(_fixture_module)
context = _fixture_module.context


def test_unplanned_and_pending_are_not_passing(context):
    m, run, criteria, root = context
    assert m.matrix_status(run)['quality_assessment']['status'] == 'not-planned'
    m.plan_quality(run, criteria)
    view = m.matrix_status(run)['quality_assessment']
    assert view['status'] == 'pending'
    assert view['criteria'] == [{'criterion_id': 'captured-calendar', 'verdict': 'pending'}]


def test_unread_assessment_remains_visible(context):
    m, run, criteria, root = context
    m.plan_quality(run, criteria)
    m.assess_quality(run, root / 'assessment')
    view = m.matrix_status(run)['quality_assessment']
    assert view['status'] == 'cannot-assess'
    assert view['criteria'][0]['verdict'] == 'cannot-assess'


@pytest.mark.parametrize('target', ['receipt', 'matrix', 'pointer', 'plan'])
def test_changed_evidence_cannot_keep_a_current_verdict(context, target):
    m, run, criteria, root = context
    m.plan_quality(run, criteria)
    m.assess_quality(run, root / 'assessment')
    path = {'receipt': root / 'assessment/result.json', 'matrix': run / 'matrix.json',
            'pointer': run / 'quality-assessment-current.json', 'plan': run / 'quality-plan.json'}[target]
    if target == 'pointer':
        path.write_text('{}')
    else:
        path.write_bytes(path.read_bytes() + b' ')
    assert m.matrix_status(run)['quality_assessment']['status'] == 'stale'


def test_receipt_refresh_preserves_the_prior_receipt(context):
    m, run, criteria, root = context
    m.plan_quality(run, criteria)
    m.assess_quality(run, root / 'first')
    original = (root / 'first/result.json').read_bytes()
    m.assess_quality(run, root / 'second')
    assert (root / 'first/result.json').read_bytes() == original
    assert m.quality_status(run)['receipt'] == str(root / 'second/result.json')


def test_reports_expose_assessment_without_replacing_findings(context, monkeypatch):
    m, run, criteria, root = context
    m.plan_quality(run, criteria)
    # Isolate output formatting; real unfinished runs retain the existing owner/coverage gates.
    monkeypatch.setattr(m, 'completeness_refusal', lambda *a: None)
    monkeypatch.setattr(m, 'unresolved_cells', lambda *a: [])
    report = m.reporting_route(run, 'report')
    assert report['quality_assessment']['status'] == 'pending'
    output = m.reporting_route(run, 'document')
    text = __import__('pathlib').Path(output['path']).read_text()
    assert 'captured-calendar: pending' in text
    assert 'not complete source coverage' in text


def test_missing_assessed_plan_is_stale_not_unplanned(context):
    m, run, criteria, root = context
    m.plan_quality(run, criteria)
    m.assess_quality(run, root / 'assessment')
    (run / 'quality-plan.json').unlink()
    assert m.matrix_status(run)['quality_assessment']['status'] == 'stale'
