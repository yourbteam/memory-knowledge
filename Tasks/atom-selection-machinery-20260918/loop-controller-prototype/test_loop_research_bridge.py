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
    def test_prior_cycle_reset_removes_all_operational_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            old = root / 'run' / 'cycles' / 'cycle-0001'
            current = root / 'run' / 'cycles' / 'cycle-0002'
            old.mkdir(parents=True);current.mkdir(parents=True)
            cycle = current / 'cycle.json';cycle.write_text('{}')
            state = {
                'root': str(root),
                'selection_preparation': {'path': str((old / 'preparation.json').relative_to(root))},
                'prepared_execution': {'path': str((old / 'execution.json').relative_to(root))},
                'research_correction': {'path': str((old / 'correction.json').relative_to(root))},
                'assessment_attempt': 2,
            }

            removed = loop.clear_prior_cycle_state(state, cycle)

            self.assertEqual(
                {'selection_preparation', 'prepared_execution', 'research_correction', 'assessment_attempt'},
                set(removed),
            )
            self.assertEqual({'root'}, set(state))

    def test_prior_cycle_reset_preserves_current_cycle_preparation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            old = root / 'run' / 'cycles' / 'cycle-0001'
            current = root / 'run' / 'cycles' / 'cycle-0002'
            old.mkdir(parents=True);current.mkdir(parents=True)
            cycle = current / 'cycle.json';cycle.write_text('{}')
            preparation = {'path': str((current / 'preparation.json').relative_to(root))}
            state = {
                'root': str(root),
                'selection_preparation': preparation,
                'prepared_execution': {'path': str((old / 'execution.json').relative_to(root))},
                'research_correction': {'path': str((old / 'correction.json').relative_to(root))},
                'assessment_attempt': 2,
            }

            removed = loop.clear_prior_cycle_state(state, cycle)

            self.assertEqual(preparation, state['selection_preparation'])
            self.assertEqual({'prepared_execution', 'research_correction', 'assessment_attempt'}, set(removed))

    def test_success_state_write_clears_old_error_but_plain_failure_write_preserves_it(self):
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder)
            recovered = {'stage': 'build', 'error': 'old failure'}

            loop.save_success_state(run, recovered)

            self.assertNotIn('error', recovered)
            self.assertNotIn('error', json.loads((run / 'state.json').read_text()))
            failed = {'stage': 'build', 'error': 'current failure'}
            loop.save(run / 'state.json', failed)
            self.assertEqual('current failure', json.loads((run / 'state.json').read_text())['error'])

    def test_only_failure_handler_writes_state_without_success_helper(self):
        source = MODULE_PATH.read_text()
        self.assertEqual(1, source.count("save(run/'state.json',s)"))
        self.assertIn("s['error']=str(exc);save(run/'state.json',s)", source)

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

    def test_attachment_can_replace_only_an_unassessed_research_export(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run = root / "run"
            cycle_path = run / "cycles" / "cycle-0001" / "cycle.json"
            cycle_path.parent.mkdir(parents=True)
            goal_path = root / "goal.json"
            selection_path = root / "selection.json"
            old_path = root / "old-research.json"
            evidence_path = root / "evidence.json"
            for path in [goal_path, selection_path, old_path, evidence_path]:
                path.write_text('{}\n')
            goal = reference(goal_path, root)
            selection = reference(selection_path, root)
            cycle_path.write_text(json.dumps({
                "goal": goal, "selection": selection, "build": None, "assessment": None,
                "research_result": reference(old_path, root),
            }))
            corrected_path = root / "corrected-research.json"
            corrected_path.write_text(json.dumps({
                "kind": "selected_research_result", "goal": goal, "selection": selection,
                "evidence": [reference(evidence_path, root)],
            }))
            state = {"root": str(root), "cycle": str(cycle_path), "stage": "assessment",
                     "pending": None, "error": "invalid assessment input"}
            loop.attach_research(run, state, corrected_path)
            saved_cycle = json.loads(cycle_path.read_text())
            self.assertEqual(saved_cycle["research_result"], reference(corrected_path, root))
            saved_state = json.loads((run / "state.json").read_text())
            self.assertEqual(saved_state["stage"], "assessment")
            self.assertEqual(saved_state["assessment_attempt"], 2)

    def test_assessment_attention_reopens_only_the_same_research_job(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run = root / "run"
            cycle_path = run / "cycles" / "cycle-0004" / "cycle.json"
            cycle_path.parent.mkdir(parents=True)
            records = {}
            for name, value in {
                "goal.json": {"goal": {"id": "goal-1"}},
                "selection.json": {"chosen": "research"},
                "preparation/handoff.json": {"status": "assignment_prepared"},
                "prepared/handoff.json": {"status": "experiment_needs_attention"},
            }.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(value) + "\n")
                records[name] = reference(path, root)
            package_path = root / "package.json"
            package_path.write_text(json.dumps({
                "status": "experiment_needs_attention",
                "review": {"cases": [{"id": "case-1", "verdict": "supported"}]},
            }) + "\n")
            research_path = root / "research.json"
            research_path.write_text(json.dumps({
                "kind": "selected_research_result",
                "assessment_package": reference(package_path, root),
            }) + "\n")
            records["research.json"] = reference(research_path, root)
            assessment_path = root / "assessment.json"
            assessment_path.write_text(json.dumps({
                "kind": "atom_assessment", "mode": "research_assessment", "cycle_id": "cycle-0004",
                "assessment": {
                    "selected_work_completion": {"judgment": "not_established", "reason": "correct expectation"},
                    "remaining": [{"statement": "correct expectation", "evidence": ["E1"]}],
                    "goal_completion": {"judgment": "not_established", "reason": "goal remains"},
                },
            }) + "\n")
            assessment = reference(assessment_path, root)
            cycle = {
                "cycle_id": "cycle-0004", "goal": records["goal.json"],
                "selection": records["selection.json"], "research_result": records["research.json"],
                "assessment": assessment, "build": None,
            }
            cycle_path.write_text(json.dumps(cycle) + "\n")
            state = {
                "root": str(root), "cycle": str(cycle_path), "stage": "assessment_needs_attention",
                "pending": {"action": "assessment_needs_attention", "assessment": assessment},
                "selection_preparation": records["preparation/handoff.json"],
                "prepared_execution": records["prepared/handoff.json"],
            }
            prior_correction_path = cycle_path.parent / "research-correction.json"
            prior_correction_path.write_text(json.dumps({"prior": "preserved"}) + "\n")
            prior_correction_bytes = prior_correction_path.read_bytes()
            loop.save(run / "state.json", state)
            correction_path = loop.resume_research_correction(run, state)
            saved_state = json.loads((run / "state.json").read_text())
            saved_cycle = json.loads(cycle_path.read_text())
            correction = json.loads(correction_path.read_text())
            self.assertNotEqual(correction_path, prior_correction_path)
            self.assertEqual(prior_correction_path.read_bytes(), prior_correction_bytes)
            self.assertTrue(correction_path.name.startswith("research-correction-"))
            self.assertEqual(saved_state["stage"], "build")
            self.assertEqual(saved_state["pending"]["action"], "prepare_build")
            self.assertEqual(
                saved_state["pending"]["selection_preparation"],
                records["preparation/handoff.json"],
            )
            self.assertEqual(saved_state["assessment_attempt"], 2)
            self.assertEqual(correction["selection"], cycle["selection"])
            self.assertEqual(correction["prior_research_result"], cycle["research_result"])
            self.assertEqual(correction["prior_review"]["cases"][0]["id"], "case-1")
            self.assertIsNone(saved_cycle["assessment"])
            self.assertEqual(saved_cycle["research_corrections"][0]["assessment"], assessment)


if __name__ == "__main__":
    unittest.main()
