"""Recorded Step12 correction histories retain one recovery eligibility rule."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts import work_memory as w

CASES = Path(__file__).resolve().parents[1] / 'Tasks/step12-ledger-recovery-20260908/cases'

@pytest.fixture(params=['abandoned', 'failed'])
def captured(request, tmp_path):
    source = json.loads((CASES / f'{request.param}.json').read_text())
    rows = source['events']
    doc = tmp_path / source['document_path']
    doc.parent.mkdir(parents=True)
    doc.write_text(source['document'])
    for row in rows:
        if row['event_type'] == 'run_started':
            row['repository_roots']['memory-knowledge'] = str(tmp_path)
    return rows, source['run_id']

def test_public_entrypoints_preserve_recorded_recovery(captured, monkeypatch):
    rows, run_id = captured
    before = copy.deepcopy(rows)
    expected = next(r for r in rows if r['event_type'] == 'correction_recorded' and r['run_id'] == run_id)
    monkeypatch.setattr(w, 'load_ledger', lambda: (rows, 'a' * 64))
    # The persistence edge is observed; both public selection routes must derive identities.
    monkeypatch.setattr(w, '_cmd_select_for_task', lambda args: vars(args))
    for result in [w.cmd_select(SimpleNamespace(verification_successor_of=run_id)),
                   w.cmd_select_successor(SimpleNamespace(predecessor_run_id=run_id))]:
        assert result['verifies_correction_id'] == [expected['correction_id']]
        assert result['verification_successor_of'] == run_id
        assert result['task_id'] == 'step12-two-clients-live'
    assert rows == before

@pytest.mark.parametrize('mode', ['nonterminal', 'successful', 'duplicate'])
def test_public_boundary_rejects_invalid_predecessors(captured, mode):
    rows, run_id = captured
    start = next(r for r in rows if r['event_type'] == 'run_started' and r['run_id'] == run_id)
    terminal = next(r for r in rows if r.get('run_id') == run_id and r['event_type'] in {'run_closed', 'run_abandoned'})
    if mode == 'nonterminal':
        rows.remove(terminal)
    elif mode == 'successful':
        terminal.update(event_type='run_closed', result='passed')
    else:
        rows.append(copy.deepcopy(terminal))
    with pytest.raises(w.WorkMemoryError, match='successor-predecessor-not-terminal'):
        w._successor_selection_request(rows, run_id)
    if mode == 'nonterminal':
        with pytest.raises(w.WorkMemoryError, match='successor-predecessor-not-terminal'):
            w._validate_successor_corrections(rows, lineage_id=start['lineage_id'], source_bundle=start['source_bundle'], predecessor_run_id=run_id, correction_ids=[])
