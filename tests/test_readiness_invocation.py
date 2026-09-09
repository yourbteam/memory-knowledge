"""Exercise invocation admission against the captured Taggable upstream case."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = ROOT / 'skills/requirement-to-atom-readiness-machinery/scripts/readiness_controller.py'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class CapturedInvocationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = load('captured_invocation_controller', CONTROLLER)
        cls.invocation = load('captured_invocation_module', CONTROLLER.with_name('invocation.py'))
        case_root = os.environ.get('READINESS_INVOCATION_CASE_ROOT')
        cls.case = cls.overlap = None
        if case_root:
            case_root = Path(case_root)
            if (case_root / 'disjoint-start.json').is_file() and (case_root / 'transitive-overlap.json').is_file():
                cls.case = json.loads((case_root / 'disjoint-start.json').read_text())
                cls.overlap = json.loads((case_root / 'transitive-overlap.json').read_text())

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='readiness-invocation-test-', dir='/private/tmp')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.session = self.base / 'interview'
        self.runtime = self.base / 'runtime'
        self.runtime.mkdir()
        self.request = (json.loads(json.dumps(self.case['request'])) if self.case
                        else {'feature_id': 'invocation-unit-test'})
        self.tip = None
        self.answer_index = 0

    def call(self, command, **values):
        args = SimpleNamespace(command='invocation-' + command, session=str(self.session),
                               expected_tip=self.tip, **values)
        result = self.invocation.dispatch(self.api, args)
        self.tip = result['ledger_tip']
        self.assertEqual(result['model_calls'], 0)
        return result

    def answer(self, question, value):
        self.answer_index += 1
        path = self.base / f'answer-{self.answer_index}.json'
        path.write_text(json.dumps(value))
        return self.call('answer', question=question, answer_json=str(path))

    def interview(self, root=None, through_root=True):
        result = self.call('open')
        for question, _ in self.invocation.QUESTIONS:
            if question == 'authorized_root' and not through_root:
                break
            self.assertEqual(result['next_question']['id'], question)
            if question == 'repositories':
                value = {key: self.request['runtime_boundary'][key]
                         for key in ('target_repositories', 'product_edit_boundaries')}
            elif question == 'authorized_root':
                value = str(root or self.runtime)
            elif question in self.invocation.FILE_QUESTIONS:
                value = self.request[question]['path']
            elif question in self.invocation.LIST_QUESTIONS:
                value = [row['path'] for row in self.request[question]]
            else:
                value = self.request[question]
            result = self.answer(question, value)
        return result

    def test_current_question_stale_tip_and_malformed_answer_preserve_state(self):
        opened = self.call('open')
        original = (self.session / 'interview.json').read_bytes()
        with self.assertRaisesRegex(self.api.Refused, 'current question'):
            self.answer('repositories', {})
        self.assertEqual((self.session / 'interview.json').read_bytes(), original)
        with self.assertRaises(self.api.Refused):
            self.answer('feature_id', [])
        malformed = self.base / 'malformed.json'
        malformed.write_text('{')
        with self.assertRaises(self.api.Refused):
            self.call('answer', question='feature_id', answer_json=str(malformed))
        self.assertEqual((self.session / 'interview.json').read_bytes(), original)
        current = self.answer('feature_id', self.request['feature_id'])
        self.tip = opened['ledger_tip']
        with self.assertRaises(self.api.Refused):
            self.answer('repositories', {})
        state = self.call('status')
        self.assertEqual(state['ledger_tip'], current['ledger_tip'])
        self.assertEqual(state['answers_recorded'], 1)

    def test_transitive_overlap_refused_before_work_creation(self):
        if self.case is None:
            self.skipTest('Set READINESS_INVOCATION_CASE_ROOT to replay captured upstream cases')
        root = Path(self.overlap['request']['runtime_boundary']['authorized_root'])
        before = set(root.iterdir())
        result = self.interview(through_root=False)
        self.assertEqual(result['answers_recorded'], 11)
        with self.assertRaisesRegex(self.api.Refused, 'overlap'):
            self.answer('authorized_root', str(root))
        self.assertEqual(set(root.iterdir()), before)
        state = self.call('status')
        self.assertEqual(state['answers_recorded'], 11)
        self.assertEqual(state['next_question']['id'], 'authorized_root')
        self.assertEqual(list(self.runtime.iterdir()), [])

    def test_complete_interview_prepare_start_queue_and_duplicate_refusal(self):
        if self.case is None:
            self.skipTest('Set READINESS_INVOCATION_CASE_ROOT to replay captured upstream cases')
        result = self.interview()
        self.assertEqual(result['status'], 'awaiting-preparation')
        prepared = self.call('prepare')
        work = Path(prepared['work'])
        self.assertFalse(work.exists())
        state = json.loads((self.session / 'interview.json').read_text())
        direct_count = len(self.api.descriptors(prepared['request']))
        self.assertGreater(len(state['prepared']['members']), direct_count)
        launched = self.call('start')
        self.assertEqual(launched['status'], 'launch-completed')
        self.assertEqual(launched['readiness']['queue_count'], 21)
        self.assertEqual(launched['readiness']['status'], 'blocked')
        self.assertEqual(launched['readiness']['readiness'], 'not-assessed')
        self.assertEqual(launched['readiness']['next_action']['condition_id'], 'real-mysql-discount-cases')
        self.assertTrue((work / 'run/ledger.jsonl').is_file())
        before = (work / 'run/ledger.jsonl').read_bytes()
        with self.assertRaisesRegex(self.api.Refused, 'duplicate'):
            self.call('start')
        self.assertEqual((work / 'run/ledger.jsonl').read_bytes(), before)
        self.assertEqual(list(self.runtime.iterdir()), [work])

    def test_changed_copied_source_refused_before_work_creation(self):
        if self.case is None:
            self.skipTest('Set READINESS_INVOCATION_CASE_ROOT to replay captured upstream cases')
        sources = self.base / 'sources'
        sources.mkdir()
        source = sources / 'boundaries.json'
        shutil.copyfile(self.request['boundaries']['path'], source)
        self.request['boundaries']['path'] = str(source)
        self.interview()
        prepared = self.call('prepare')
        with source.open('ab') as stream:
            stream.write(b'\n')
        with self.assertRaisesRegex(self.api.Refused, 'digest mismatch'):
            self.call('start')
        self.assertFalse(Path(prepared['work']).exists())
        state = self.call('status')
        self.assertEqual(state['status'], 'prepared')

    def test_open_tasks_name_refused_without_creating_session(self):
        self.session = self.base / 'Tasks'
        with self.assertRaisesRegex(self.api.Refused, 'Tasks'):
            self.call('open')
        self.assertFalse(self.session.exists())

    def test_direct_source_inside_session_refused_without_recording_answer(self):
        self.call('open')
        self.answer('feature_id', 'invocation-unit-test')
        self.answer('repositories', {'target_repositories': [str(self.base / 'product')],
                                     'product_edit_boundaries': [str(self.base / 'product/app')]})
        source = self.session / 'source.json'
        source.write_text('{}')
        before = (self.session / 'interview.json').read_bytes()
        with self.assertRaisesRegex(self.api.Refused, 'overlaps invocation state'):
            self.answer('description_handoff', str(source))
        self.assertEqual((self.session / 'interview.json').read_bytes(), before)
        self.assertEqual(self.call('status')['next_question']['id'], 'description_handoff')


if __name__ == '__main__':
    unittest.main()
