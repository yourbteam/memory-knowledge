import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = Path(__file__).with_name("loop.py")
SPEC = importlib.util.spec_from_file_location("loop_controller", MODULE_PATH)
loop = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(loop)


def reference(path, root):
    return {"path": str(path.relative_to(root)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


class ResearchBridgeTest(unittest.TestCase):
    def test_attachment_advances_to_assessment_and_clears_stale_error(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run = root / "run"
            cycle_path = run / "cycles" / "cycle-0001" / "cycle.json"
            cycle_path.parent.mkdir(parents=True)
            goal_path = root / "goal.json"
            selection_path = root / "selection.json"
            evidence_path = root / "evidence.json"
            for path in [goal_path, selection_path, evidence_path]:
                path.write_text('{}\n')
            goal = reference(goal_path, root)
            selection = reference(selection_path, root)
            cycle_path.write_text(json.dumps({"goal": goal, "selection": selection,
                                              "build": None, "assessment": None}))
            result_path = root / "research-result.json"
            result_path.write_text(json.dumps({
                "kind": "selected_research_result",
                "goal": goal,
                "selection": selection,
                "evidence": [reference(evidence_path, root)],
            }))
            state = {"root": str(root), "cycle": str(cycle_path), "stage": "build",
                     "pending": {"action": "prepare_build"}, "error": "stale review error"}
            loop.attach_research(run, state, result_path)
            saved_state = json.loads((run / "state.json").read_text())
            saved_cycle = json.loads(cycle_path.read_text())
            self.assertEqual(saved_state["stage"], "assessment")
            self.assertIsNone(saved_state["pending"])
            self.assertNotIn("error", saved_state)
            self.assertEqual(saved_cycle["research_result"], reference(result_path, root))
            self.assertIsNone(saved_cycle["build"])


if __name__ == "__main__":
    unittest.main()
