import importlib.util
import hashlib
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
    def test_install_records_hash_bound_canonical_blocker_support(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); repository = root/"repository"; source = repository/"skills"
            dest = root/"client"/"skills"; state = root/"state"
            (source/"one").mkdir(parents=True)
            (source/"one/SKILL.md").write_text("---\nname: one\ndescription: test\n---\n")
            (repository/"scripts").mkdir()
            (repository/"scripts/blocker_catalog.py").write_text("BLOCKER = 1\n")
            (repository/"scripts/work_memory.py").write_text("MEMORY = 1\n")
            manifest = source/"managed-skills.txt"; manifest.write_text("one\n")

            installer.install(source, manifest, [dest], state)

            record = json.loads((root/"client/.managed-skills-source.json").read_text())
            self.assertEqual(record["schema_version"], 1)
            self.assertEqual(record["source_repository_root"], str(repository.resolve()))
            self.assertEqual(record["support_files"], {
                name: hashlib.sha256((repository/name).read_bytes()).hexdigest()
                for name in ("scripts/blocker_catalog.py", "scripts/work_memory.py")
            })

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

    def test_only_replaces_selected_managed_skill(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); source = root/"source"; dest = root/"dest"; state = root/"state"
            for name in ("one", "two"):
                (source/name).mkdir(parents=True)
                (source/name/"SKILL.md").write_text(f"---\nname: {name}\ndescription: test\n---\nnew-{name}\n")
                (dest/name).mkdir(parents=True)
                (dest/name/"SKILL.md").write_text(f"old-{name}\n")
            (dest/"two/nested").mkdir()
            (dest/"two/nested/keep").write_text("untouched\n")
            manifest = source/"managed-skills.txt"; manifest.write_text("one\ntwo\n")
            untouched_before = installer.tree_hash(dest/"two")

            installer.install(source, manifest, [dest], state, only=["one"])

            self.assertIn("new-one", (dest/"one/SKILL.md").read_text())
            self.assertEqual(installer.tree_hash(dest/"two"), untouched_before)

    def test_only_rejects_unknown_or_duplicate_names_before_mutation(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); source = root/"source"; dest = root/"dest"; state = root/"state"
            (source/"one").mkdir(parents=True)
            (source/"one/SKILL.md").write_text("---\nname: one\ndescription: test\n---\n")
            manifest = source/"managed-skills.txt"; manifest.write_text("one\n")
            with self.assertRaisesRegex(SystemExit, "not managed"):
                installer.install(source, manifest, [dest], state, only=["two"])
            with self.assertRaisesRegex(SystemExit, "unique"):
                installer.install(source, manifest, [dest], state, only=["one", "one"])
            self.assertFalse(dest.exists())

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

    def _gate_fixture(self, root: Path):
        source = root/"source"; claude = root/"claude"; state = root/"state"
        (source/"one").mkdir(parents=True)
        (source/"one/SKILL.md").write_text("---\nname: one\ndescription: test\n---\nbody\n")
        manifest = source/"managed-skills.txt"; manifest.write_text("one\n")
        return source, manifest, claude, state

    def _run_main(self, source, manifest, claude, state, *extra):
        command = [sys.executable, str(ROOT/"working-agreement/install_skills.py"),
                   "--source", str(source), "--manifest", str(manifest),
                   "--claude-root", str(claude), "--state-dir", str(state), *extra]
        return subprocess.run(command, capture_output=True, text=True)

    def test_claude_target_without_reconciliation_is_refused(self):
        with tempfile.TemporaryDirectory() as raw:
            source, manifest, claude, state = self._gate_fixture(Path(raw))
            result = self._run_main(source, manifest, claude, state, "--target", "claude")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("requires --reconciliation", result.stderr)
            self.assertFalse(claude.exists())

    def test_incomplete_or_nonterminal_reconciliation_is_refused(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); source, manifest, claude, state = self._gate_fixture(root)
            reconciliation = root/"reconciliation.json"
            reconciliation.write_text(json.dumps({"rows": []}))
            result = self._run_main(source, manifest, claude, state,
                                    "--target", "claude", "--reconciliation", str(reconciliation))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("lacks a decision", result.stderr)
            reconciliation.write_text(json.dumps({"rows": [{"name": "one", "status": "claude-divergent-preserved"}]}))
            result = self._run_main(source, manifest, claude, state,
                                    "--target", "claude", "--reconciliation", str(reconciliation))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("not a terminal reconciliation decision", result.stderr)
            self.assertFalse(claude.exists())

    def test_projection_manifest_reconciliation_fails_closed_on_drift(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); source, manifest, claude, state = self._gate_fixture(root)
            entry = {"disposition": "SHARED_IDENTICAL", "targets": ["codex", "claude"],
                     "scenario_groups": ["CAP-SHARED"], "canonical_tree_sha256": installer.tree_hash(source/"one"),
                     "projected_tree_sha256": installer.tree_hash(source/"one"), "generator": None,
                     "generator_sha256": None, "divergence_reason": None}
            reconciliation = root/"projections.json"
            reconciliation.write_text(json.dumps({"schema_version": 1, "entries": {"one": entry}}))
            ok = self._run_main(source, manifest, claude, state,
                                "--target", "claude", "--reconciliation", str(reconciliation))
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertEqual(installer.tree_hash(claude/"one"), entry["canonical_tree_sha256"])
            (source/"one/SKILL.md").write_text("---\nname: one\ndescription: test\n---\ndrifted\n")
            drifted = self._run_main(source, manifest, claude, state,
                                     "--target", "claude", "--reconciliation", str(reconciliation))
            self.assertNotEqual(drifted.returncode, 0)
            self.assertIn("canonical tree changed after projection", drifted.stderr)

    def test_generated_projection_install_keeps_each_client_provider_bound(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); source = root/"source"; state = root/"state"
            name = "atom-building-machinery"
            (source/name).mkdir(parents=True)
            (source/name/"SKILL.md").write_text(
                f"---\nname: {name}\ndescription: test\n---\nbody\n")
            manifest = source/"managed-skills.txt"; manifest.write_text(name + "\n")
            reconciliation = root/"projections.json"
            reconciliation.write_text(json.dumps({"schema_version": 1, "entries": {
                name: {
                    "disposition": "GENERATED_CLIENT_PROJECTION",
                    "targets": ["codex", "claude"],
                    "scenario_groups": ["CAP-SHARED"],
                    "canonical_tree_sha256": None,
                    "projected_tree_sha256": None,
                    "projected_tree_sha256_by_client": None,
                    "generator": "machinery-client-model-v1",
                    "generator_sha256": None,
                    "divergence_reason": "The invoking client owns model selection.",
                }
            }}) + "\n")
            pcs = installer._projection_module()
            self.assertEqual(pcs.generate(source, manifest, reconciliation), 0)
            codex = root/"codex"; claude = root/"claude"
            command = [sys.executable, str(ROOT/"working-agreement/install_skills.py"),
                       "--source", str(source), "--manifest", str(manifest),
                       "--target", "both", "--accept-cross-client",
                       "--codex-root", str(codex), "--claude-root", str(claude),
                       "--state-dir", str(state), "--reconciliation", str(reconciliation)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            codex_policy = json.loads((codex/name/"client-model-policy.json").read_text())
            claude_policy = json.loads((claude/name/"client-model-policy.json").read_text())
            self.assertEqual(codex_policy["required_runtime"], "codex exec")
            self.assertEqual(claude_policy["required_runtime"], "claude -p")
            self.assertNotEqual(installer.tree_hash(codex/name), installer.tree_hash(claude/name))

    def test_unmanaged_installed_skills_are_preserved_and_reported(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); source, manifest, claude, state = self._gate_fixture(root)
            (claude/"legacy-loop").mkdir(parents=True); (claude/"legacy-loop/keep").write_text("yes")
            entry = {"disposition": "SHARED_IDENTICAL", "targets": ["codex", "claude"],
                     "scenario_groups": ["CAP-SHARED"], "canonical_tree_sha256": installer.tree_hash(source/"one"),
                     "projected_tree_sha256": installer.tree_hash(source/"one"), "generator": None,
                     "generator_sha256": None, "divergence_reason": None}
            reconciliation = root/"projections.json"
            reconciliation.write_text(json.dumps({"schema_version": 1, "entries": {"one": entry}}))
            result = self._run_main(source, manifest, claude, state,
                                    "--target", "claude", "--reconciliation", str(reconciliation))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("unmanaged preserved", result.stdout)
            self.assertIn("legacy-loop", result.stdout)
            self.assertEqual((claude/"legacy-loop/keep").read_text(), "yes")

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
