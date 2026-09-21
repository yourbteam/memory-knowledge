import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = Path(__file__).with_name("launch_prepared_build.py")
SPEC = importlib.util.spec_from_file_location("launch_prepared_build", MODULE_PATH)
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


class PreparedBuildLauncherTest(unittest.TestCase):
    def fixture(self, stage="build", action="prepare_build"):
        temp = tempfile.TemporaryDirectory()
        base = Path(temp.name)
        run = base / "live"
        cycle_dir = run / "cycles" / "cycle-0004"
        cycle_dir.mkdir(parents=True)
        (cycle_dir / "cycle.json").write_text("{}")
        runtime = base / "runtime.json"
        runtime.write_text('{"adapter":"fixture"}\n')
        model_io = base / "skills" / "atom-building-machinery" / "scripts" / "model_io.py"
        model_io.parent.mkdir(parents=True)
        model_io.write_text("# fixture model call\n")
        prepared_execution = base / "prepared_execution.py"
        prepared_execution.write_text("# fixture prepared execution\n")
        state = {
            "stage": stage,
            "pending": {
                "action": action,
                "selection": {"path": "selection.json", "sha256": "selection"},
                "selection_preparation": {"path": "preparation.json", "sha256": "preparation"},
            },
            "cycle": str(cycle_dir / "cycle.json"),
            "cycle_number": 4,
            "prepared_execution": None,
            "root": str(base),
            "skills": str(base / "skills"),
        }
        (run / "state.json").write_text(json.dumps(state))
        config = base / "prepared_build_launch.json"
        config.write_text(json.dumps({
            "schema_version": 1,
            "run": "live",
            "runtime_config": "runtime.json",
            "runtime_config_sha256": launcher.sha256(runtime),
            "builder_model_io_sha256": launcher.sha256(model_io),
            "prepared_execution_sha256": launcher.sha256(prepared_execution),
            "model_timeout_seconds": 900,
        }))
        return temp, base, cycle_dir, config

    def test_selects_first_unused_attempt(self):
        temp, base, cycle_dir, config = self.fixture()
        self.addCleanup(temp.cleanup)
        for attempt in range(1, 7):
            launcher.attempt_path(cycle_dir, attempt).mkdir()
        result = launcher.plan(base, config)
        self.assertEqual(result["attempt"], 7)
        self.assertFalse(result["resumed"])
        self.assertEqual(result["model_calls"], 2)
        self.assertEqual(result["model_timeout_seconds"], 900)
        self.assertEqual(Path(result["output"]), (cycle_dir / "prepared-execution-attempt7").resolve())

    def test_resumes_receipted_execution_without_handoff(self):
        temp, base, cycle_dir, config = self.fixture()
        self.addCleanup(temp.cleanup)
        abandoned = launcher.attempt_path(cycle_dir, 1)
        (abandoned / "receipts").mkdir(parents=True)
        (abandoned / "receipts" / "generation.json").write_text("{}")
        resumable = launcher.attempt_path(cycle_dir, 2)
        (resumable / "receipts").mkdir(parents=True)
        (resumable / "execution").mkdir()
        (resumable / "receipts" / "generation.json").write_text("{}")
        (resumable / "execution" / "result.json").write_text("{}")
        result = launcher.plan(base, config)
        self.assertEqual(result["attempt"], 2)
        self.assertTrue(result["resumed"])
        self.assertEqual(result["model_calls"], 1)

    def test_does_not_resume_attempt_with_handoff(self):
        temp, base, cycle_dir, config = self.fixture()
        self.addCleanup(temp.cleanup)
        completed = launcher.attempt_path(cycle_dir, 1)
        (completed / "receipts").mkdir(parents=True)
        (completed / "execution").mkdir()
        (completed / "receipts" / "generation.json").write_text("{}")
        (completed / "execution" / "result.json").write_text("{}")
        (completed / "handoff.json").write_text("{}")
        result = launcher.plan(base, config)
        self.assertEqual(result["attempt"], 2)
        self.assertFalse(result["resumed"])

    def test_resumes_attached_completed_handoff_without_model_calls(self):
        temp, base, cycle_dir, config = self.fixture()
        self.addCleanup(temp.cleanup)
        completed = launcher.attempt_path(cycle_dir, 1)
        completed.mkdir()
        handoff = completed / "handoff.json"
        handoff.write_text('{"status":"experiment_supported"}\n')
        reference = {"path": str(handoff.relative_to(base)), "sha256": launcher.sha256(handoff)}
        state_path = base / "live" / "state.json"
        state = json.loads(state_path.read_text())
        state["prepared_execution"] = reference
        state["pending"]["prepared_execution"] = reference
        state_path.write_text(json.dumps(state))
        result = launcher.plan(base, config)
        self.assertEqual(result["attempt"], 1)
        self.assertTrue(result["resumed"])
        self.assertTrue(result["completed_handoff"])
        self.assertEqual(result["model_calls"], 0)

    def test_rejects_wrong_loop_stage(self):
        temp, base, _, config = self.fixture(stage="assessment", action=None)
        self.addCleanup(temp.cleanup)
        with self.assertRaisesRegex(ValueError, "not waiting"):
            launcher.plan(base, config)

    def test_rejects_changed_runtime_config(self):
        temp, base, _, config = self.fixture()
        self.addCleanup(temp.cleanup)
        (base / "runtime.json").write_text('{"adapter":"changed"}\n')
        with self.assertRaisesRegex(ValueError, "changed"):
            launcher.plan(base, config)

    def test_rejects_invalid_timeout(self):
        temp, base, _, config = self.fixture()
        self.addCleanup(temp.cleanup)
        value = json.loads(config.read_text())
        value["model_timeout_seconds"] = 3600
        config.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "timeout"):
            launcher.plan(base, config)

    def test_rejects_changed_builder_model_call(self):
        temp, base, _, config = self.fixture()
        self.addCleanup(temp.cleanup)
        model_io = base / "skills" / "atom-building-machinery" / "scripts" / "model_io.py"
        model_io.write_text("# changed\n")
        with self.assertRaisesRegex(ValueError, "model-call implementation changed"):
            launcher.plan(base, config)

    def test_rejects_changed_prepared_execution(self):
        temp, base, _, config = self.fixture()
        self.addCleanup(temp.cleanup)
        (base / "prepared_execution.py").write_text("# changed\n")
        with self.assertRaisesRegex(ValueError, "prepared-execution implementation changed"):
            launcher.plan(base, config)


if __name__ == "__main__":
    unittest.main()
