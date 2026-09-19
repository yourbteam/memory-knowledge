import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'skills/atom-selection-machinery/scripts/atom_selection.py'
SPEC = importlib.util.spec_from_file_location('atom_selection', SCRIPT)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)
CAPTURED = ROOT / 'tests/fixtures/atom-selection-machinery'


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.goal = self.root / 'goal.txt'
        self.goal.write_text(json.loads((CAPTURED / 'protocol.json').read_text())['owner_clarification'])
        self.run = self.root / 'run'
        self.calls = []
        self.prepare()

    def prepare(self):
        result = subprocess.run([sys.executable, '-B', str(SCRIPT), 'start', '--input',
                                 str(CAPTURED / 'input.json'), '--goal', str(self.goal),
                                 '--run', str(self.run), '--prepare-only'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def replay(self, directory, prompt, settings):
        stage = directory.parent.name
        source = CAPTURED / 'provider' / stage
        if stage == 'distillation':
            source = CAPTURED / 'distillation-v2/provider/narrowing'
        self.calls.append(stage)
        # Only the external model boundary is replayed. The runtime owns all stages/export.
        (directory / 'answer.json').write_bytes((source / 'answer.json').read_bytes())
        (directory / 'events.jsonl').write_bytes((source / 'events.jsonl').read_bytes())
        return json.loads((source / 'answer.json').read_text())

    def test_real_answers_export_and_idempotent_resume(self):
        with patch.object(m, 'invoke', self.replay):
            result = m.execute(self.run)
            self.assertEqual(result['completed_calls'], 6)
            output = m.read(self.run / 'handoff.json')
            expected = m.read(CAPTURED / 'distillation-v2/result.json')['analysis']
            self.assertEqual(output['chosen_atom'], expected)
            self.assertFalse(output['execution_authorized'])
            m.execute(self.run)
        self.assertEqual(len(self.calls), 6)

    def test_failure_resumes_only_unfinished_stage(self):
        def fail(directory, prompt, settings):
            if directory.parent.name == 'dependencies':
                raise RuntimeError('Captured provider interruption boundary')
            return self.replay(directory, prompt, settings)
        with patch.object(m, 'invoke', fail), self.assertRaises(RuntimeError):
            m.execute(self.run)
        self.assertEqual(len(self.calls), 2)
        with patch.object(m, 'invoke', self.replay):
            m.execute(self.run)
        self.assertEqual(len(self.calls), 6)
        self.assertTrue((self.run / 'calls/dependencies/attempt-001/prompt.txt').exists())
        self.assertTrue((self.run / 'calls/dependencies/attempt-002/answer.json').exists())

    def test_provider_completion_survives_local_interruption(self):
        def interrupt(directory, prompt, settings):
            self.replay(directory, prompt, settings)
            raise RuntimeError('Interrupted after provider completion, before checkpoint')
        with patch.object(m, 'invoke', interrupt), self.assertRaises(RuntimeError):
            m.execute(self.run)
        with patch.object(m, 'invoke', self.replay):
            m.execute(self.run)
        self.assertEqual(len(self.calls), 6)

    def test_changed_input_and_saved_answer_rejected_without_calls(self):
        original = (self.run / 'input.json').read_bytes()
        (self.run / 'input.json').write_text('{}')
        with patch.object(m, 'invoke') as call, self.assertRaisesRegex(ValueError, 'Frozen run input changed'):
            m.execute(self.run)
        call.assert_not_called()
        (self.run / 'input.json').write_bytes(original)
        with patch.object(m, 'invoke', self.replay):
            m.execute(self.run)
        (self.run / 'calls/selection/attempt-001/answer.json').write_text('{"analysis":"changed"}')
        with patch.object(m, 'invoke') as call, self.assertRaisesRegex(ValueError, 'Saved stage changed'):
            m.execute(self.run)
        call.assert_not_called()

    def test_unready_answer_refused(self):
        data = m.read(CAPTURED / 'input.json')
        data['questions'][0]['final_answer']['self_assessment']['choice'] = 'needs_input'
        with self.assertRaisesRegex(ValueError, 'not ready'):
            m.validate_input(data)

    def test_standalone_public_cli_with_recorded_provider_responses(self):
        package = self.root / 'standalone'
        shutil.copytree(SCRIPT.parent, package)
        replay_cli = self.root / 'recorded-cli'
        replay_cli.write_text('#!' + sys.executable + '\n' +
            'import sys,json\nfrom pathlib import Path\n' +
            'out=Path(sys.argv[sys.argv.index("--output-last-message")+1])\n' +
            'stage=out.parent.parent.name\n' +
            'root=Path(' + repr(str(CAPTURED)) + ')\n' +
            'source=root/"provider"/stage\n' +
            'if stage=="distillation": source=root/"distillation-v2/provider/narrowing"\n' +
            'out.write_bytes((source/"answer.json").read_bytes())\n' +
            'print((source/"events.jsonl").read_text())\n')
        replay_cli.chmod(0o700)
        settings = m.read(package / 'settings.json')
        settings['cli'] = str(replay_cli)
        m.save(package / 'settings.json', settings)
        run = self.root / 'public-run'
        command = [sys.executable, '-B', str(package / SCRIPT.name)]
        result = subprocess.run(command + ['start', '--input', str(CAPTURED / 'input.json'),
                                '--goal', str(self.goal), '--run', str(run)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        handoff = m.read(run / 'handoff.json')
        self.assertEqual(handoff['chosen_atom'], m.read(CAPTURED / 'distillation-v2/result.json')['analysis'])
        replay_cli.unlink()  # Completed resume must not require or invoke the provider again.
        result = subprocess.run(command + ['resume', '--run', str(run)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(list((run / 'calls').glob('*/attempt-*'))), 6)


if __name__ == '__main__':
    unittest.main()
