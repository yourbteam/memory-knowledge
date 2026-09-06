"""Captured v7 calendar must not inherit an undeclared every-active-card requirement."""
import copy
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAPTURE = json.loads((ROOT / 'tests/fixtures/critique-calendar/captured.json').read_text())


def inputs():
    spec = importlib.util.spec_from_file_location('calendar_contract', ROOT / 'skills/critique-machinery/scripts/critique.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    unit = copy.deepcopy(CAPTURE['unit'])
    return module, unit, copy.deepcopy(CAPTURE['payload'])


def test_real_v7_calendar_matches_its_declared_entries():
    module, unit, payload = inputs()
    facts = module._check_calendar_phases_match_payload(unit, payload)
    assert len(facts) == 12
    assert all(fact['verdict'] == 'clear' for fact in facts)
    assert all(fact['check'] == 'calendar-phase-matches-payload' for fact in facts)


def test_explicit_phase_corruption_is_located():
    # Deliberate fault injected into a captured page, not a claimed historical defect.
    module, unit, payload = inputs()
    unit['text'] = unit['text'].replace('| Month 4 | Launch |', '| Month 4 | Sustain |')
    defects = [f for f in module._check_calendar_phases_match_payload(unit, payload) if f['verdict'] == 'defect']
    assert len(defects) == 1
    assert (defects[0]['subject'], defects[0]['expected'], defects[0]['actual']) == ('Month 4', 'Launch', 'Sustain')
    assert '| Month 4 | Sustain |' in unit['text'].splitlines()[defects[0]['line'] - 1]


def test_missing_declared_month_is_visible():
    module, unit, payload = inputs()
    unit['text'] = '\n'.join(line for line in unit['text'].splitlines() if not line.startswith('| Month 4 |'))
    defects = [f for f in module._check_calendar_phases_match_payload(unit, payload) if f['verdict'] == 'defect']
    assert len(defects) == 1 and defects[0]['actual'] == 'no such calendar row'


def test_unsupported_shape_is_not_falsely_cleared():
    module, unit, payload = inputs()
    unit['text'] = unit['text'].replace('| month | phase |', '| period | stage |')
    assert module._check_calendar_phases_match_payload(unit, payload) is None
