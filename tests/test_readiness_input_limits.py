import base64
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).parents[1]
SCRIPTS=ROOT/'skills/requirement-to-atom-readiness-machinery/scripts'
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
k=load('input_limit_kernel',SCRIPTS/'readiness_controller.py')
m=load('input_limit_transport',SCRIPTS/'model_interview.py')
FIXTURES=ROOT/'tests/fixtures/readiness-transport'
old=load('old_limit_transport',FIXTURES/'old_input_transport.py')
WORK=Path('/private/tmp/captured-input-limit-work')

class InputLimitTests(unittest.TestCase):
    def pending(self):
        event=json.loads((FIXTURES/'input-limit-pending.json').read_bytes())
        self.assertEqual(event['event'],'interview_prepared')
        return event['payload']

    def test_real_blocked_prompt_prepares_without_changing_bytes(self):
        pending=self.pending();state={'interview_state':{'pending':pending},'ledger_tip':'0'*64}
        with self.assertRaisesRegex(ValueError,'131072'):
            old.plan_for(k,WORK,state,disabled_skills=[])
        plan=m.plan_for(k,WORK,state,disabled_skills=[])
        for item,seat in zip(pending['envelopes'],plan['seats']):
            expected=m.INSTRUCTION.encode()+k.canonical(item['envelope'])+b'\n'
            self.assertEqual(base64.b64decode(seat['prompt_base64']),expected)
            self.assertGreater(len(expected),131072)
            with tempfile.TemporaryDirectory(dir='/private/tmp') as tmp:
                p=Path(tmp)/'prompt.txt';p.write_bytes(expected)
                raw,truncated=m.capture_file(k,p)
                self.assertEqual(base64.b64decode(raw),expected)
                self.assertIsNone(truncated)

    def test_input_cap_remains_bounded(self):
        pending=self.pending();state={'interview_state':{'pending':pending},'ledger_tip':'0'*64}
        with patch.object(m,'INSTRUCTION','x'*262145),self.assertRaisesRegex(ValueError,'262144'):
            m.plan_for(k,WORK,state,disabled_skills=[])

    def test_output_cap_and_truncation_are_unchanged(self):
        self.assertEqual(m.MAX_LOG_BYTES,131072)
        self.assertEqual(m.DIAGNOSTICS['max_metadata_bytes'],131072)
        for name in m.AUDIT_FILES:
            expected=262144 if name in ('prompt.txt','schema.json') else 131072
            self.assertEqual(m.artifact_limit(name),expected)
            with tempfile.TemporaryDirectory(dir='/private/tmp') as tmp:
                p=Path(tmp)/name;p.write_bytes(b'x'*(expected+1))
                raw,truncation=m.capture_file(k,p)
                self.assertEqual(len(base64.b64decode(raw)),expected)
                self.assertEqual(truncation['size'],expected+1)
