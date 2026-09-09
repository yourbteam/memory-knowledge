"""Installed entrypoint checks using real canonical skill bytes and provenance."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
NAME = 'requirement-to-atom-readiness-machinery'
SOURCE = REPO/'skills'/NAME


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runtime = load('readiness_installation', SOURCE/'scripts/installation_runtime.py')
installer = load('readiness_managed_installer', REPO/'working-agreement/install_skills.py')


class InstalledReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.client = self.root/'codex'
        self.skill = self.client/'skills'/NAME
        shutil.copytree(SOURCE, self.skill, ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        self.record = self.client/runtime.RECORD
        self.data = installer.managed_source_record(REPO/'skills')
        self.save()
        self.entry = self.skill/'scripts/readiness_controller.py'

    def save(self):
        self.record.write_text(json.dumps(self.data))

    def test_both_client_layouts_resolve_both_public_entrypoints(self):
        for client in ('codex','claude'):
            with self.subTest(client=client):
                if client == 'claude':
                    target = self.root/client
                    shutil.copytree(self.client, target)
                else:
                    target = self.client
                for name in runtime.ENTRYPOINTS:
                    entry = target/'skills'/NAME/'scripts'/name
                    self.assertEqual(runtime.canonical_entrypoint(entry), SOURCE/'scripts'/name)

    def test_public_schema_and_canary_help_match_canonical(self):
        for name, argument in [('readiness_controller.py','schema'),('run_canary.py','--help')]:
            with self.subTest(entry=name):
                def run(path):
                    return subprocess.run([sys.executable,str(path),argument],capture_output=True,text=True,timeout=10)
                canonical = run(SOURCE/'scripts'/name)
                installed = run(self.skill/'scripts'/name)
                self.assertEqual(canonical.returncode,0,canonical.stderr)
                self.assertEqual(installed.returncode,0,installed.stderr)
                self.assertEqual(installed.stdout,canonical.stdout)

    def test_missing_provenance_refuses_before_work_creation(self):
        self.record.unlink()
        work = self.root/'must-not-exist'
        result = subprocess.run([sys.executable,str(self.entry),'start','/missing-request',str(work),
                                 '--expected-tip','0'*64],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,2)
        self.assertIn('installation refused',result.stderr)
        self.assertFalse(work.exists())

    def test_changed_support_hash_refuses(self):
        self.data['support_files']['scripts/work_memory.py'] = '0'*64
        self.save()
        with self.assertRaisesRegex(runtime.InstallationRefused,'support bytes changed'):
            runtime.canonical_entrypoint(self.entry)

    def test_changed_skill_bytes_refuse(self):
        with self.entry.open('a') as stream:
            stream.write('\n# controlled mutation of the real copied entrypoint\n')
        with self.assertRaisesRegex(runtime.InstallationRefused,'differs from its canonical source'):
            runtime.canonical_entrypoint(self.entry)

    def test_missing_skill_member_refuses(self):
        (self.skill/'references/request-contract.md').unlink()
        with self.assertRaisesRegex(runtime.InstallationRefused,'differs from its canonical source'):
            runtime.canonical_entrypoint(self.entry)

    def test_incomplete_extra_and_duplicate_records_refuse(self):
        original = dict(self.data)
        for change in ('missing','extra','duplicate'):
            with self.subTest(change=change):
                self.data = dict(original)
                if change == 'missing': self.data.pop('support_files')
                if change == 'extra': self.data['unapproved_source'] = str(REPO)
                self.save()
                if change == 'duplicate':
                    self.record.write_text(self.record.read_text()[:-1]+',"schema_version":1}')
                with self.assertRaises(runtime.InstallationRefused):
                    runtime.canonical_entrypoint(self.entry)

    def test_linked_provenance_refuses(self):
        original = self.root/'retained-record.json'
        self.record.rename(original)
        self.record.symlink_to(original)
        with self.assertRaisesRegex(runtime.InstallationRefused,'linked source'):
            runtime.canonical_entrypoint(self.entry)

    def test_self_referential_source_refuses(self):
        (self.client/'scripts').mkdir()
        for name in runtime.SUPPORT:
            shutil.copyfile(REPO/name,self.client/name)
        self.data['source_repository_root'] = str(self.client)
        self.save()
        with self.assertRaisesRegex(runtime.InstallationRefused,'points back'):
            runtime.canonical_entrypoint(self.entry)

    def test_another_client_cannot_be_a_canonical_source(self):
        other = self.root/'claude'
        shutil.copytree(self.client,other)
        (other/'scripts').mkdir()
        for name in runtime.SUPPORT:
            shutil.copyfile(REPO/name,other/name)
        # Real copied skill and support hashes alone do not authorize a chain
        # of client-to-client redirects; a managed source repository is required.
        self.data['source_repository_root'] = str(other)
        self.save()
        with self.assertRaises(FileNotFoundError):
            runtime.canonical_entrypoint(self.entry)
