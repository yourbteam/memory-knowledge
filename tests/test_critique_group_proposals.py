"""Exact captured partitions prove non-destructive consensus and separate obligations."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CAPTURE = json.loads((ROOT / 'tests/fixtures/critique-grouping/partitions.json').read_text())


def load_module():
    spec = importlib.util.spec_from_file_location('critique_group_test', ROOT / 'skills/critique-machinery/scripts/critique.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_captured_header_observations_are_only_proposed_not_merged():
    module = load_module()
    case = copy.deepcopy(CAPTURE['repeated-header'])
    before = copy.deepcopy(case)
    result = module.consensus_issue_proposals(case['readers'], case['ids'])
    assert case == before
    assert len(result['proposed_groups']) == 1
    group = result['proposed_groups'][0]
    assert set(group['finding_ids']) == set(case['ids']) and len(group['finding_ids']) == 12
    assert group['status'] == 'proposed-for-owner-review'
    assert len(group['reader_explanations']) == 2


def test_distinct_required_measures_remain_separate():
    module = load_module()
    case = CAPTURE['distinct-measures']
    result = module.consensus_issue_proposals(case['readers'], case['ids'])
    assert sorted(len(group['finding_ids']) for group in result['proposed_groups']) == [2, 2]
    assert {identity for group in result['proposed_groups'] for identity in group['finding_ids']} == set(case['ids'])


def test_disagreement_retains_unmatched_observation():
    module = load_module()
    case = copy.deepcopy(CAPTURE['repeated-header'])
    separate = case['ids'][0]
    group = case['readers'][1]['groups'][0]
    group['finding_ids'].remove(separate)
    case['readers'][1]['groups'].append({'finding_ids': [separate], 'issue': 'Deliberate disagreement fault', 'why_same_issue': 'Singleton'})
    result = module.consensus_issue_proposals(case['readers'], case['ids'])
    assert result['ungrouped_finding_ids'] == [separate]
    assert len(result['proposed_groups'][0]['finding_ids']) == 11


def test_duplicate_identity_is_refused():
    module = load_module()
    case = copy.deepcopy(CAPTURE['repeated-header'])
    case['readers'][1]['groups'][0]['finding_ids'].append(case['ids'][0])
    with pytest.raises(module.Refusal, match='incomplete or repeated'):
        module.consensus_issue_proposals(case['readers'], case['ids'])


def test_failed_reader_cannot_authorize_any_group():
    module = load_module()
    case = copy.deepcopy(CAPTURE['repeated-header'])
    case['readers'][1] = {'status': 'cannot-assess', 'error': 'Deliberate failed-reader fault', 'groups': []}
    result = module.consensus_issue_proposals(case['readers'], case['ids'])
    assert result['status'] == 'cannot-assess' and result['proposed_groups'] == []
    assert result['ungrouped_finding_ids'] == case['ids']
