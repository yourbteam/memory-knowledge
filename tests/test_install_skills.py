import importlib.util
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


installer = load("installer", ROOT / "working-agreement/install_skills.py")


class InstallerTests(unittest.TestCase):
    def test_exact_replace_preserves_unrelated(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); source = root/"source"; dest = root/"dest"; state = root/"state"
            (source/"one").mkdir(parents=True); (source/"one/SKILL.md").write_text("---\nname: one\ndescription: test\n---\nnew\n")
            manifest = source/"managed-skills.txt"; manifest.write_text("one\n")
            (dest/"one").mkdir(parents=True); (dest/"one/stale").write_text("old")
            (dest/"unrelated").mkdir(); (dest/"unrelated/keep").write_text("yes")
            installer.install(source, manifest, [dest], state)
            self.assertFalse((dest/"one/stale").exists())
            self.assertIn("description: test", (dest/"one/SKILL.md").read_text())
            self.assertEqual((dest/"unrelated/keep").read_text(), "yes")
            self.assertFalse((state/"transaction.json").exists())

    def test_recover_applying_restores_backup(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); dest = root/"skill"; backup = root/"backup"; staged = root/"staged"
            dest.mkdir(); (dest/"value").write_text("partial")
            backup.mkdir(); (backup/"value").write_text("original")
            staged.mkdir(); (staged/"value").write_text("new")
            journal = root/"transaction.json"
            journal.write_text(json.dumps({"phase":"APPLYING","entries":[{"destination":str(dest),"backup":str(backup),"staged":str(staged),"original_exists":True,"mutation_started":True,"installed":True}]}))
            installer.recover(journal)
            self.assertEqual((dest/"value").read_text(), "original")
            self.assertFalse(journal.exists())

    def test_recover_prepared_does_not_touch_destination(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); dest=root/"skill"; dest.mkdir(); (dest/"value").write_text("original")
            staged=root/"staged"; staged.mkdir(); (staged/"value").write_text("new")
            backup=root/"backup"; journal=root/"transaction.json"
            journal.write_text(json.dumps({"phase":"PREPARED","entries":[{"destination":str(dest),"backup":str(backup),"staged":str(staged),"original_exists":True,"mutation_started":False,"installed":False}]}))
            installer.recover(journal)
            self.assertEqual((dest/"value").read_text(),"original")

    def test_both_requires_reconciled_record(self):
        text=(ROOT/"working-agreement/install_skills.py").read_text()
        self.assertIn("cross-client variants are not reconciled",text)
        self.assertIn("--reconciliation",text)

    def test_recover_new_install_after_rename_before_journal_bit(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); dest=root/"skill"; dest.mkdir(); (dest/"value").write_text("partial")
            staged=root/"staged"; backup=root/"backup"; journal=root/"transaction.json"
            journal.write_text(json.dumps({"phase":"APPLYING","entries":[{"destination":str(dest),"backup":str(backup),"staged":str(staged),"original_exists":False,"mutation_started":True,"installed":False}]}))
            installer.recover(journal)
            self.assertFalse(dest.exists()); self.assertFalse(journal.exists())

    def test_install_fsyncs_journal_and_destination_directories(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); source=root/"source"; dest=root/"dest"; state=root/"state"
            (source/"one").mkdir(parents=True); (source/"one/SKILL.md").write_text("---\nname: one\ndescription: test\n---\n")
            manifest=source/"managed-skills.txt"; manifest.write_text("one\n")
            real=installer.fsync_dir; seen=[]
            def observe(path): seen.append(Path(path)); real(Path(path))
            with patch.object(installer,"fsync_dir",side_effect=observe): installer.install(source,manifest,[dest],state)
            self.assertIn(state,seen); self.assertIn(dest,seen)

    def test_install_fsyncs_staged_payload_files(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); source=root/"source"; dest=root/"dest"; state=root/"state"
            (source/"one").mkdir(parents=True); (source/"one/SKILL.md").write_text("---\nname: one\ndescription: test\n---\n")
            manifest=source/"managed-skills.txt"; manifest.write_text("one\n"); events=[]; real_write=installer.write_json
            def observe_write(path,data): events.append(("journal",data["phase"])); real_write(path,data)
            with patch.object(installer,"fsync_file",side_effect=lambda path: events.append(("file",Path(path)))), patch.object(installer,"write_json",side_effect=observe_write):
                installer.install(source,manifest,[dest],state)
            payload_index=next(i for i,event in enumerate(events) if event[0] == "file" and event[1].name == "SKILL.md" and "staged" in event[1].parts)
            prepared_index=events.index(("journal","PREPARED")); self.assertLess(payload_index,prepared_index)

    def test_install_lock_fails_fast_and_journal_has_transaction_id(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); source=root/"source"; dest=root/"dest"; state=root/"state"; (source/"one").mkdir(parents=True); (source/"one/SKILL.md").write_text("---\nname: one\ndescription: test\n---\n"); manifest=source/"managed-skills.txt"; manifest.write_text("one\n")
            command=[sys.executable,str(ROOT/"working-agreement/install_skills.py"),"--source",str(source),"--manifest",str(manifest),"--codex-root",str(dest),"--state-dir",str(state)]
            first=subprocess.Popen(command+["--hold-lock","0.8"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True); time.sleep(0.15)
            started=time.monotonic(); second=subprocess.run(command,capture_output=True,text=True,timeout=0.5); elapsed=time.monotonic()-started
            self.assertNotEqual(second.returncode,0); self.assertIn("already running",second.stderr+second.stdout); self.assertLess(elapsed,0.5); first.communicate(timeout=3); self.assertEqual(first.returncode,0)
            journals=[]; real=installer.write_json
            def observe(path,data): journals.append(dict(data)); real(path,data)
            with patch.object(installer,"write_json",side_effect=observe): installer.install(source,manifest,[dest],state)
            ids={entry.get("transaction_id") for entry in journals}; self.assertEqual(len(ids),1); self.assertNotIn(None,ids)


if __name__ == "__main__": unittest.main()
