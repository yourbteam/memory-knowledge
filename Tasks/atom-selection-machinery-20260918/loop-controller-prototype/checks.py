"""Saved-real-input checks. No provider calls; replay/terminal probes are labelled."""
import copy
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
import loop

ROOT=Path(__file__).resolve().parents[3]
BASE=ROOT/'Tasks/atom-selection-machinery-20260918'
LIVE=Path(__file__).parent/'live'

def run():
    results=[]
    assessment=loop.read(BASE/'citation-connected-final-v1/handoff.json')
    assert loop.assessment_action(assessment)=='incremental'
    results.append('Real historical assessment routes to incremental, not goal completion')
    # These are schema-enum branch tests, explicitly not recorded goal-completion evidence.
    for value,action in [('established','goal_complete'),('cannot_assess','assessment_needs_attention')]:
        sample=copy.deepcopy(assessment);sample['assessment']['goal_completion']['judgment']=value
        assert loop.assessment_action(sample)==action
    results.append('Controlled enum branches stop for established and surface cannot_assess')
    prior=loop.read(LIVE/'state.json')
    request=loop.read(ROOT/'Tasks/input-interview-machinery-20260916/code-owned-lenses-prototype/acceptance-operator-control/interview/followups/6ba949b3-0032-4893-871a-afe0a4d73be7/request.json')
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as td:
        r=Path(td);s=copy.deepcopy(prior)
        (r/'goal.txt').write_bytes((LIVE/'goal.txt').read_bytes())
        pending={'action':'ask_user','request':request,'tool':'functions.request_user_input_async','arguments':{'questions':[{'title':request['question']}]}}
        s.update(stage='incremental',pending=pending);loop.save(r/'state.json',s)
        with patch.object(loop,'call',side_effect=AssertionError('Pending question must not execute work')):
            assert loop.advance(r)==pending
        results.append('Actual captured owner question survives save/resume verbatim and blocks advancement')
        s.update(stage='goal_complete',pending=None,last_assessment=loop.ref(BASE/'citation-connected-final-v1/handoff.json',ROOT));loop.save(r/'state.json',s)
        with patch.object(loop,'call',side_effect=AssertionError('Terminal state must not execute work')):
            assert loop.advance(r)['action']=='goal_complete'
        results.append('Controlled terminal-state probe starts no later stage')
        # False attachment must be rejected by the installed assessment collector, not interpreted by loop.
        s.update(cycle_number=0,candidate_review={'path':'previous-cycle-review'});loop.new_cycle(r,s,s['answers']);c=loop.read(s['cycle'])
        assert 'candidate_review' not in s
        assert c['selection'] is None and c['build'] is None and c['assessment'] is None
        results.append('New cycle leaves all unperformed stages empty')
    loop.save(Path(__file__).parent/'mechanical-checks.json',{'checks':results,'all_passed':True,'scope':'Captured record routing plus explicitly controlled enum/terminal probes; no live build claim'})
    print(json.dumps(results,indent=2))

if __name__=='__main__':run()
