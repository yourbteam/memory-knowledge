"""Review presentation uses captured real findings and partitions; no semantic votes."""
import copy
import importlib.util
import json
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT/'tests/fixtures/critique-grouping/review-packets.json').read_text())
def module():
    spec=importlib.util.spec_from_file_location('review_packet',ROOT/'skills/critique-machinery/scripts/critique.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

@pytest.mark.parametrize('name',list(CASES))
def test_every_captured_finding_has_evidence_and_location(name):
    m=module();case=copy.deepcopy(CASES[name]);before=copy.deepcopy(case)
    text='\n'.join(m.group_review_lines(case['material'],case['result']))
    assert case==before
    for f in case['material']['findings']:
        assert text.count('### Finding '+f['finding_id'])==1
        assert f['reason'] in text and f['practical_consequence'] in text
        for key in ['quote','source_quote']:
            for line in (f.get(key) or '').splitlines():assert '> '+line in text
        for o in f['observations']:assert o['cell_id'] in text and o['seat'] in text
    assert 'Grouping is not a verdict' in text


def test_distinct_measures_keep_their_two_proposals():
    case=CASES['distinct-measures'];text='\n'.join(module().group_review_lines(case['material'],case['result']))
    assert text.count('## Proposal ')==2


def test_failed_grouping_keeps_every_finding_separate():
    m=module();case=copy.deepcopy(CASES['repeated-header']);ids=case['result']['selected_finding_ids']
    failed=m.consensus_issue_proposals([{'status':'cannot-assess','groups':[],'error':'Explicit transport fault'},case['result']['readers'][1]],ids)
    text='\n'.join(m.group_review_lines(case['material'],failed))
    assert 'Grouping could not be established' in text
    assert text.count('### Finding ')==len(ids)
    assert '## Proposal ' not in text


def test_empty_selection_is_an_explicit_empty_packet():
    text='\n'.join(module().group_review_lines({'findings':[]},{'status':'completed','proposed_groups':[],'ungrouped_finding_ids':[]}))
    assert 'Selected findings: 0.' in text


@pytest.mark.parametrize('bad', [None, [], 'invalid'])
def test_malformed_receipt_is_refused_before_loading_run(tmp_path, bad):
    m=module();(tmp_path/'.git').mkdir();work=tmp_path/'run';work.mkdir();receipt=tmp_path/'receipt';receipt.mkdir()
    (receipt/'input.json').write_text('{}');(receipt/'result.json').write_text(json.dumps(bad))
    out=tmp_path/'review.md'
    with pytest.raises(m.Refusal,match='must be objects'):
        m.review_finding_groups(work,receipt,out)
    assert not out.exists()
