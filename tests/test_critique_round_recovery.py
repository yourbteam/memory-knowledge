"""Coordination boundaries on the captured calendar page; reader answers are test-controlled.
Real semantic bytes are tested separately in the full-round captured experiment.
"""
import json
import pytest
from tests.test_critique_quality_acceptance import context


def reader(m, monkeypatch, failure_attempts):
    calls = []
    def run(repo, context, focus, unit, lenses, **kw):
        calls.append((kw['seat'], kw['attempt']))
        root = kw['evidence_root']; root.mkdir(parents=True)
        failed = kw['seat'] == 'reader-1' and kw['attempt'] in failure_attempts
        raw = json.dumps({'judgments': [{'lens': lens, 'verdict': 'clear',
            'start_line': 1, 'end_line': len(unit['text'].splitlines()),
            'findings': []} for lens in lenses]})
        result = m.classify_reader_reply(raw, m.reader_schema(lenses), lenses,
            batch_id=kw['batch_id'], seat=kw['seat'], attempt=kw['attempt'],
            evidence_path=str(root), forced_outcome='timeout' if failed else None)
        result = m.ground_reader_result(result, unit, kw['upstream_sources'])
        (root/'reader-response.json').write_bytes(m.canonical(result))
        return result
    monkeypatch.setattr(m, '_reader_judgments', run)
    return calls


@pytest.mark.parametrize('planned', [False, True])
@pytest.mark.parametrize('failures,state,retries', [(set(), 'not-needed', 0), ({1}, 'recovered', 1), ({1,2}, 'exhausted', 1)])
def test_round_returns_honest_recovery_without_extra_reads(context, monkeypatch, capsys, planned, failures, state, retries):
    m, run, criteria, root = context
    if planned: m.plan_quality(run, criteria)
    calls = reader(m, monkeypatch, failures)
    assert m.main(['read-run','--work',str(run),'--recover-failed']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['recovery']['state'] == state
    assert result['reader_calls'] == len(calls) == 2 + retries
    assert calls.count(('reader-2', 1)) == 1 and ('reader-2', 2) not in calls
    assert result['retry_exhausted_seat_count'] == (1 if state == 'exhausted' else 0)
    assert result['quality_assessment']['status'] != 'satisfied'
    before = len(calls)
    m.retry_failed(run)
    assert len(calls) == before
    if planned and retries:
        assert m._quality_recovery_bound(run, *m.load_matrix(run))
        (run/'sources.json').write_text('{}')
        assert not m._quality_recovery_bound(run, *m.load_matrix(run))
        (run/'sources.json').unlink()
    if planned:
        assert m.main(['read-run','--work',str(run),'--recover-failed']) == 2
        assert len(calls) == before
    events = [json.loads(x) for x in (run/'round-progress.jsonl').read_text().splitlines()]
    assert any(e['event']=='round-completed' and e['recovery_state']==state for e in events)


def test_unflagged_read_keeps_manual_retry_boundary(context, monkeypatch, capsys):
    m, run, criteria, root = context
    calls = reader(m, monkeypatch, {1})
    assert m.main(['read-run','--work',str(run)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['retryable_failed_seat_count'] == 1
    assert len(calls) == 2
    assert not (run/'round-progress.jsonl').exists()


def test_failed_initial_execution_never_starts_recovery(context, monkeypatch):
    m, run, criteria, root = context
    m.plan_quality(run, criteria)
    def fail(*args, **kwargs): raise m.Refusal('Captured interruption boundary')
    monkeypatch.setattr(m, '_reader_judgments', fail)
    monkeypatch.setattr(m, 'retry_failed', lambda *args: pytest.fail('Must not retry an interrupted initial round'))
    assert m.main(['read-run','--work',str(run),'--recover-failed']) == 2
    assert json.loads((run/'quality-execution.json').read_text())['status'] == 'started'
    assert json.loads((run/'round-progress.jsonl').read_text().splitlines()[-1])['event'] == 'round-failed'
