"""Acceptance boundaries use the captured calendar and real page-building path.

Semantic quality is exercised by live observers over captured full-round replies in
this atom's experiment. These tests make no claim that a test-controlled reader is
semantic evidence.
"""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def context(tmp_path):
    spec = importlib.util.spec_from_file_location('critique_quality_test', ROOT / 'skills/critique-machinery/scripts/critique.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    capture = json.loads((ROOT / 'tests/fixtures/critique-calendar/captured.json').read_text())
    (tmp_path / '.git').mkdir()
    page, state = tmp_path / 'page.md', tmp_path / 'state.json'
    page.write_text(capture['unit']['text'])
    state.write_text(json.dumps({'payload': capture['payload']}))
    run = tmp_path / 'run'
    m.open_run(page, state, 'payload', run, no_reference='No benchmark for boundary replay', no_upstream='No source judgment in boundary replay')
    manifest, matrix = m.load_matrix(run)
    cell = next(c for c in matrix['cells'] if c['lens'] == 'buyer-read')
    criteria = tmp_path / 'criteria.json'
    criteria.write_text(json.dumps([{'id': 'captured-calendar', 'unit_id': cell['unit_id'], 'lens': cell['lens'], 'requirement': 'Do not infer present asset readiness from future calendar slots.'}]))
    return m, run, criteria, tmp_path


def test_unread_round_cannot_qualify_or_call_observer(context, monkeypatch):
    m, run, criteria, root = context
    m.plan_quality(run, criteria)
    monkeypatch.setattr(m, '_assess_quality_case', lambda *a: pytest.fail('Unread round must not call a semantic observer'))
    result = m.assess_quality(run, root / 'assessment')
    assert result['verdict'] == 'cannot-assess'
    assert result['unread_cells'] and not result['full_round_execution_bound']


def test_plan_cannot_be_replaced_after_freezing(context):
    m, run, criteria, root = context
    m.plan_quality(run, criteria)
    with pytest.raises(m.Refusal, match='already exists'):
        m.plan_quality(run, criteria)


def test_missing_plan_does_not_admit_existing_results(context):
    m, run, criteria, root = context
    with pytest.raises(m.Refusal, match='before reading'):
        m.assess_quality(run, root / 'assessment')


def test_changed_source_boundary_refuses_assessment(context):
    m, run, criteria, root = context
    m.plan_quality(run, criteria)
    path = run / 'quality-plan.json'
    plan = json.loads(path.read_text())
    plan['reader_source_sha256'] = '0' * 64  # Explicit corruption, not a historical run.
    path.write_text(json.dumps(plan))
    with pytest.raises(m.Refusal, match='reader_source_sha256 changed'):
        m.assess_quality(run, root / 'assessment')


def test_duplicate_criteria_and_unavailable_lens_refused(context):
    m, run, criteria, root = context
    original = json.loads(criteria.read_text())
    criteria.write_text(json.dumps(original + original))
    with pytest.raises(m.Refusal, match='repeats id'):
        m.plan_quality(run, criteria)
    original[0]['lens'] = 'benchmark-vs-reference'
    criteria.write_text(json.dumps(original))
    with pytest.raises(m.Refusal, match='applicable model cell'):
        m.plan_quality(run, criteria)
