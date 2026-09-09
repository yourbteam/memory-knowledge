"""Real captured no-answer stream at the external process edge only.

These tests prove diagnostic retention, not repair of the upstream provider.
"""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('timeout_cases',Path(__file__).with_name('test_requirement_to_atom_readiness.py'))
cases=importlib.util.module_from_spec(spec);spec.loader.exec_module(cases)
CAPTURE=Path(__file__).parent/'fixtures/readiness-transport/timeout-stdout.jsonl'

class TimeoutDiagnosticsTests(unittest.TestCase):
    def test_captured_silent_timeout_keeps_warning_and_progress(self):
        e=cases.CodexLaunchTests();e.setUp()
        captured=CAPTURE.read_bytes()
        self.assertEqual([json.loads(l)['type'] for l in captured.splitlines()],['thread.started','turn.started'])
        command=[sys.executable,'-c','import os,sys,time;sys.stdout.buffer.write('+repr(captured)+');sys.stdout.flush();sys.stderr.write(os.environ.get("RUST_LOG","missing"));sys.stderr.flush();time.sleep(30)']
        plan={**e.plan,'timeout_ms':350}
        with tempfile.TemporaryDirectory(dir='/private/tmp',prefix='timeout-proof-') as temp:
            seat=Path(temp)/'seat-1';seat.mkdir()
            with patch.object(e.k,'runtime_identity',return_value={'codex':plan['launcher']}),patch.object(e.m,'argv_for',return_value=command),patch.object(e.m,'PROGRESS_INTERVAL_SECONDS',.05,create=True),patch.dict('os.environ',{'RUST_LOG':'trace'}):
                with self.assertRaisesRegex(e.m.SeatTimeout,'provider exceeded'):
                    e.m.call_seat(e.k,plan,plan['seats'][0],seat,e.auth)
            self.assertEqual((seat/'stdout.jsonl').read_bytes(),captured)
            self.assertEqual((seat/'stderr.txt').read_text(),'warn')
            rows=[json.loads(line) for line in (Path(temp)/'telemetry.jsonl').read_text().splitlines()]
            self.assertTrue(any(r['event']=='seat-waiting' for r in rows))
            end=rows[-1]
            self.assertEqual(end['event'],'seat-timeout')
            self.assertEqual(end['cause'],'unconfirmed')
            self.assertEqual(end['stdout_bytes'],len(captured))
            self.assertFalse(end['response_present'])
            self.assertFalse((seat/'assembled-response.json').exists())
            self.assertEqual(sum(r['event']=='seat-starting' for r in rows),1)
