import base64
import copy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('observed_recovery_tests', Path(__file__).with_name('test_readiness_timeout_recovery.py'))
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)
CAPTURE = Path(__file__).parent / 'fixtures/readiness-transport/request-metadata.jsonl'


class RequestDiagnosticsTests(unittest.TestCase):
    def test_attempts_keep_diagnostics_and_replay_detects_tampering(self):
        e, answers, proof, state, seen, expected = recovery.RecoveryTests().exercise(['success', 'timeout', 'success'])
        self.assertEqual(answers, expected)
        for seat in proof['seats']:
            for attempt in seat['attempts']:
                self.assertIn('request-metadata.jsonl', attempt['files'])
                self.assertIn('diagnostics.json', attempt['files'])
                e.m.validate_diagnostics(e.k, attempt)
        for kind in ('missing', 'hash', 'count', 'forbidden-field'):
            with self.subTest(kind=kind):
                bad = copy.deepcopy(proof)
                attempt = bad['seats'][1]['attempts'][0]
                files = attempt['files']
                if kind == 'missing':
                    del files['request-metadata.jsonl']
                else:
                    summary = json.loads(base64.b64decode(files['diagnostics.json']))
                    if kind == 'hash': summary['metadata_sha256'] = '0' * 64
                    if kind == 'count': summary['record_count'] += 1
                    if kind == 'forbidden-field':
                        raw = b'{"event":"codex.api_request","received_elapsed_ms":1,"error_present":false,"prompt":"not allowed"}\n'
                        files['request-metadata.jsonl'] = base64.b64encode(raw).decode()
                        summary.update(metadata_sha256=e.k.digest(raw), record_count=1)
                    files['diagnostics.json'] = base64.b64encode(e.k.canonical(summary)).decode()
                with self.assertRaises(ValueError):
                    e.m.validate_finish(e.k, bad, state)

    def test_actual_live_metadata_validates_without_becoming_a_verdict(self):
        e = recovery.cases.CodexLaunchTests(); e.setUp()
        d = e.m.diagnostics_module()
        raw = CAPTURE.read_bytes()
        self.assertEqual(d.validate_metadata(raw), 15)
        self.assertNotIn('verdict', json.loads(raw.splitlines()[-1]))

    def test_collector_does_not_need_dns(self):
        import tempfile
        e = recovery.cases.CodexLaunchTests(); e.setUp()
        d = e.m.diagnostics_module()
        with tempfile.TemporaryDirectory(dir='/private/tmp') as temp, patch('socket.getfqdn', side_effect=AssertionError('DNS forbidden')):
            collector = d.Collector(Path(temp) / 'metadata.jsonl')
            collector.close()
            self.assertEqual(collector.summary()['record_count'], 0)

    def test_private_values_are_not_retained(self):
        e = recovery.cases.CodexLaunchTests(); e.setUp()
        d = e.m.diagnostics_module()
        attrs = {'event.name':'codex.api_request','user.email':'PRIVATE@example.com',
                 'prompt':'PRIVATE','endpoint':'https://example.com/responses?token=PRIVATE',
                 'error.message':'PRIVATE','http.response.status_code':'429'}
        row = d.sanitize({'attributes':[{'key':key,'value':{'stringValue':value}} for key,value in attrs.items()]})
        self.assertNotIn('PRIVATE', json.dumps(row))
        self.assertEqual(row['endpoint_class'], 'responses')
        self.assertTrue(row['error_present'])
