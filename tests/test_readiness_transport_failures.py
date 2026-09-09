"""Captured CLI failure replay. No provider requests or new semantic judgments."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('readiness_cases', Path(__file__).with_name('test_requirement_to_atom_readiness.py'))
cases = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cases)


class TransportFailureTests(unittest.TestCase):
    # First failure event retained from verification-interview-02, seat-1.
    captured = b'{"type":"error","message":"Reconnecting... 2/5 (stream disconnected before completion: Incomplete response returned, reason: max_output_tokens)"}\n'

    def setUp(self):
        self.edge = cases.CodexLaunchTests()
        self.edge.setUp()

    def test_running_process_stops_on_captured_failure(self):
        e = self.edge
        # Replace only the external process with a timed replay of the real event.
        # Baseline waits until its deadline and loses the specific failure reason.
        command = [sys.executable, '-c',
                   'import sys,time;sys.stdout.buffer.write(' + repr(self.captured) + ');sys.stdout.flush();time.sleep(30)']
        plan = {**e.plan, 'timeout_ms': 600}
        with tempfile.TemporaryDirectory(dir='/private/tmp', prefix='readiness-failure-') as temp:
            seat = Path(temp) / 'seat-1'; seat.mkdir()
            started = time.monotonic()
            with patch.object(e.k, 'runtime_identity', return_value={'codex': plan['launcher']}), patch.object(e.m, 'argv_for', return_value=command):
                with self.assertRaisesRegex(e.k.Refused, 'max_output_tokens'):
                    e.m.call_seat(e.k, plan, plan['seats'][0], seat, e.auth)
            self.assertLess(time.monotonic() - started, 0.55)
            self.assertEqual((seat / 'stdout.jsonl').read_bytes(), self.captured)
            self.assertFalse((seat / 'response.json').exists())

    def test_complete_lines_and_event_types_only(self):
        e = self.edge
        with tempfile.TemporaryDirectory(dir='/private/tmp', prefix='readiness-stream-') as temp:
            log = Path(temp) / 'stdout.jsonl'
            log.write_bytes(self.captured[:-1])
            e.m.check_provider_failure(e.k, log, 'seat-1')
            # The same words in an answer are evidence, not a transport failure.
            log.write_text(json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': self.captured.decode()}}) + '\n')
            e.m.check_provider_failure(e.k, log, 'seat-1')
            log.write_bytes(self.captured)
            with self.assertRaisesRegex(e.k.Refused, 'max_output_tokens'):
                e.m.check_provider_failure(e.k, log, 'seat-1')

    def test_terminal_and_item_errors_refuse(self):
        e = self.edge
        for event in ({'type': 'turn.failed', 'error': {'message': 'max_output_tokens'}},
                      {'type': 'item.completed', 'item': {'type': 'error', 'message': 'transport failed'}}):
            with self.subTest(event=event), tempfile.TemporaryDirectory(dir='/private/tmp') as temp:
                log = Path(temp) / 'stdout.jsonl'
                log.write_text(json.dumps(event) + '\n')
                with self.assertRaisesRegex(e.k.Refused, 'provider failure'):
                    e.m.check_provider_failure(e.k, log, 'seat-1')

    def pinned_case(self):
        import copy
        e = self.edge
        originals = []
        for item, captured in zip(e.state['pending']['envelopes'], cases.InterviewEngineTests.captured_responses):
            response = copy.deepcopy(captured)
            response['envelope_sha256'] = item['envelope']['envelope_sha256']
            originals.append(response)
            quote_schema = item['response_schema']['properties']['quotes']
            quote_schema['items'] = {'anyOf': [
                {'type': 'object', 'additionalProperties': False,
                 'properties': {'evidence_id': {'type': 'string', 'const': q['evidence_id']},
                                'quote': {'type': 'string', 'const': q['quote']}},
                 'required': ['evidence_id', 'quote']} for q in response['quotes']]}
        e.plan = e.m.plan_for(e.k, Path('/private/tmp/captured-readiness-work'), {'interview_state': e.state, 'ledger_tip': 'a'*64})
        e.auth['plan_sha256'] = e.plan['plan_sha256']
        original = originals[0]
        compact = copy.deepcopy(original)
        for q in compact['quotes']:
            del q['quote']
        return original, compact

    def test_compact_round_trip_preserves_captured_judgment(self):
        e = self.edge
        original, compact = self.pinned_case()
        schema = e.plan['seats'][0]['response_schema']
        before = e.k.canonical(schema)
        self.assertEqual(e.k.canonical(e.m.assemble_response(e.k, compact, schema, 'seat-1')), e.k.canonical(original))
        self.assertEqual(e.k.canonical(schema), before)
        self.assertLess(len(e.k.canonical(compact)), len(e.k.canonical(original)))
        self.assertEqual(compact['verdict'], original['verdict'])

    def test_compact_foreign_duplicate_or_supplied_quote_refused(self):
        import copy
        e = self.edge
        original, compact = self.pinned_case()
        schema = e.plan['seats'][0]['response_schema']
        for mode in ('foreign', 'duplicate', 'quote', 'identity'):
            changed = copy.deepcopy(compact)
            if mode == 'foreign': changed['quotes'][0]['evidence_id'] = 'foreign-evidence'
            if mode == 'duplicate': changed['quotes'].append(changed['quotes'][0])
            if mode == 'quote': changed['quotes'][0]['quote'] = original['quotes'][0]['quote']
            if mode == 'identity': changed['envelope_sha256'] = '0'*64
            with self.subTest(mode=mode), self.assertRaises(e.k.Refused):
                e.m.assemble_response(e.k, changed, schema, 'seat-1')

    def test_compact_provider_edge_retains_raw_and_assembled(self):
        from types import SimpleNamespace
        import base64
        e = self.edge
        original, compact = self.pinned_case()
        with tempfile.TemporaryDirectory(dir='/private/tmp', prefix='readiness-compact-') as temp:
            directory = Path(temp) / 'seat-1'; directory.mkdir()
            def popen(args, **kwargs):
                Path(args[args.index('--output-last-message')+1]).write_bytes(e.k.canonical(compact))
                kwargs['stdout'].write(b'{"type":"turn.completed"}\n'); kwargs['stdout'].flush()
                return SimpleNamespace(returncode=0, poll=lambda: 0, pid=2147483647, wait=lambda: 0)
            with patch.object(e.k, 'runtime_identity', return_value={'codex': e.plan['launcher']}), patch.object(e.m.subprocess, 'Popen', side_effect=popen) as process:
                result = e.m.call_seat(e.k, e.plan, e.plan['seats'][0], directory, e.auth)
            self.assertEqual(process.call_count, 1)
            self.assertEqual(result, original)
            self.assertEqual(json.loads((directory/'response.json').read_bytes()), compact)
            self.assertEqual(json.loads((directory/'assembled-response.json').read_bytes()), original)
            # Replay checks the relation, not merely the existence of both files.
            reservation = {'plan': e.plan, 'authorization': e.auth, 'reserved_at_utc': e.m.now()}
            e.state['launches'].append(reservation)
            rows = []
            for prepared in e.plan['seats']:
                files = {name: base64.b64encode((directory/name).read_bytes()).decode() for name in e.m.AUDIT_FILES}
                files['prompt.txt'] = prepared['prompt_base64']
                files['schema.json'] = base64.b64encode(e.k.canonical(prepared['provider_schema'])+b'\n').decode()
                # Only seat1 completed in this local edge probe; test refusal via
                # its altered assembly before the unstarted seat can be inspected.
                rows.append({'seat': prepared['seat'], 'files': files, 'truncations': {},
                             'attempts': [{'attempt': 1, 'outcome': 'completed', 'elapsed_ms': 0,
                                           'error': None, 'files': files, 'truncations': {}}]})
            tampered = dict(original, reason='altered model judgment')
            rows[0]['files']['assembled-response.json'] = base64.b64encode(e.k.canonical(tampered)).decode()
            payload = {'pending_sha256': e.plan['pending_sha256'], 'plan_sha256': e.plan['plan_sha256'], 'seats': rows, 'error': None}
            with self.assertRaisesRegex(e.k.Refused, 'assembled response differs'):
                e.m.validate_finish(e.k, payload, e.state)
