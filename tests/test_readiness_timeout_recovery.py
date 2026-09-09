"""Captured answers and no-answer stream; only the external process is replaced."""
import base64
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('recovery_cases',Path(__file__).with_name('test_requirement_to_atom_readiness.py'))
cases=importlib.util.module_from_spec(spec);spec.loader.exec_module(cases)
CAPTURE=Path(__file__).parent/'fixtures/readiness-transport/timeout-stdout.jsonl'

class RecoveryTests(unittest.TestCase):
    def exercise(self, modes):
        e=cases.CodexLaunchTests();e.setUp()
        plan={**e.plan,'timeout_ms':250}
        seen=[]; responses=[]
        for original,item in zip(cases.InterviewEngineTests.captured_responses,e.state['pending']['envelopes']):
            row=copy.deepcopy(original)
            for key in ('run_id','node_id','family','attempt','seat','envelope_sha256'):
                row[key]=item['envelope'][key]
            responses.append(row)
        def argv(plan,seat,cwd,schema,response):
            seen.append((seat['seat'],str(cwd),seat['prompt_sha256']))
            mode=modes[len(seen)-1]
            if mode=='timeout-expire':
                e.auth['expires_at_utc']='2000-01-01T00:00:00+00:00'
            if mode in ('timeout','timeout-expire'):
                return [sys.executable,'-c','import sys,time;sys.stdout.buffer.write('+repr(CAPTURE.read_bytes())+');sys.stdout.flush();time.sleep(30)']
            if mode=='failure':
                return [sys.executable,'-c','import sys;sys.exit(9)']
            raw=json.dumps(responses[int(seat['seat'][-1])-1])
            return [sys.executable,'-c','from pathlib import Path;Path('+repr(str(response))+').write_text('+repr(raw)+');print(\'{"type":"turn.completed"}\')']
        with tempfile.TemporaryDirectory(prefix='bounded-recovery-',dir='/private/tmp') as temp:
            root=Path(temp)
            for seat in plan['seats']:(root/seat['seat']).mkdir()
            with patch.object(e.k,'runtime_identity',return_value={'codex':plan['launcher']}),patch.object(e.m,'argv_for',side_effect=argv):
                answers,histories,error=e.m.run_seats(e.k,plan,root,e.auth)
            proof={'pending_sha256':plan['pending_sha256'],'plan_sha256':plan['plan_sha256'],'error':error,'seats':[]}
            for seat in plan['seats']:
                history=histories[seat['seat']]
                last=history[-1] if history else {'files':{},'truncations':{}}
                proof['seats'].append({'seat':seat['seat'],'files':last['files'],'truncations':last['truncations'],'attempts':history})
            state={'launches':[{'plan':plan}],'pending':e.state['pending'],'launch_results':[]}
            e.m.validate_finish(e.k,proof,state)
        return e,answers,proof,state,seen,responses

    def test_only_timed_out_second_seat_retries(self):
        e,answers,proof,state,seen,expected=self.exercise(['success','timeout','success'])
        self.assertEqual([s[0] for s in seen],['seat-1','seat-2','seat-2'])
        self.assertEqual(answers,expected)
        self.assertEqual(seen[1][2],seen[2][2])
        self.assertNotEqual(seen[1][1],seen[2][1])
        self.assertEqual(len(proof['seats'][0]['attempts']),1)
        self.assertEqual([a['outcome'] for a in proof['seats'][1]['attempts']],['timeout','completed'])
        self.assertIsNone(proof['error'])

    def test_two_timeouts_stop_without_other_seat(self):
        _,answers,proof,_,seen,_=self.exercise(['timeout','timeout'])
        self.assertEqual([s[0] for s in seen],['seat-1','seat-1'])
        self.assertEqual(answers,[])
        self.assertEqual(proof['seats'][1]['attempts'],[])
        self.assertIsNotNone(proof['error'])

    def test_non_timeout_does_not_retry(self):
        _,answers,proof,_,seen,_=self.exercise(['failure'])
        self.assertEqual(len(seen),1)
        self.assertEqual(answers,[])
        self.assertEqual(proof['seats'][0]['attempts'][0]['outcome'],'failed')

    def test_both_seats_timeout_once_maximum_four_calls(self):
        _,answers,proof,_,seen,expected=self.exercise(['timeout','success','timeout','success'])
        self.assertEqual(len(seen),4)
        self.assertEqual(answers,expected)
        self.assertIsNone(proof['error'])

    def test_replay_refuses_history_tampering(self):
        e,_,proof,state,_,_=self.exercise(['success','timeout','success'])
        for change in ('third','non-timeout','short','prompt','selected'):
            with self.subTest(change=change):
                bad=json.loads(json.dumps(proof));seat=bad['seats'][1]
                if change=='third':seat['attempts'].append(copy.deepcopy(seat['attempts'][-1]))
                if change=='non-timeout':seat['attempts'][0]['outcome']='failed'
                if change=='short':seat['attempts'][0]['elapsed_ms']=0
                if change=='prompt':seat['attempts'][0]['files']['prompt.txt']=base64.b64encode(b'changed').decode()
                if change=='selected':seat['files']['response.json']=base64.b64encode(b'{}').decode()
                with self.assertRaises(e.k.Refused):e.m.validate_finish(e.k,bad,state)

    def test_upfront_budget_is_required(self):
        e=cases.CodexLaunchTests();e.setUp()
        for budget in (2,3,5,True):
            with self.subTest(budget=budget),self.assertRaises(e.k.Refused):
                e.m.validate_authority(e.k,e.plan,{**e.auth,'max_calls':budget},e.m.now())

    def test_expired_authority_stops_before_retry_process(self):
        _,answers,proof,_,seen,_=self.exercise(['timeout-expire'])
        self.assertEqual(len(seen),1)
        self.assertEqual(answers,[])
        self.assertIn('expired',proof['error'])
        self.assertEqual(proof['seats'][0]['attempts'][-1]['outcome'],'failed')
