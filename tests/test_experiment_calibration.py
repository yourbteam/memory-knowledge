"""Frozen positive/negative evaluator calibration through the real CLI."""
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

_spec=importlib.util.spec_from_file_location('calibration_quality_fixture',Path(__file__).with_name('test_experiment_quality.py'))
_fixture=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_fixture)
runner,SCRIPTS=_fixture.runner,_fixture.SCRIPTS


class CalibrationTests(unittest.TestCase):
    tearDown=_fixture.QualityTests.tearDown

    def setUp(self):
        _fixture.QualityTests.setUp(self)
        self.calibration=self.root/'cases.json'
        self.cases={'schema_version':1,'cases':[
            {'id':'positive','outcome':{'judgments':[{'verdict':'clear','action':'Replace the missing month.'}]},'expected_metrics':{'quality':1}},
            {'id':'negative','outcome':{'judgments':[{'verdict':'revise','quote':'Long words without an actionable recommendation.'}]},'expected_metrics':{'quality':0}}]}
        self.freeze()

    def freeze(self):
        self.calibration.write_text(json.dumps(self.cases))
        self.spec['evaluation']['calibration']={'path':self.calibration.name,'sha256':runner._digest_file(self.calibration)}

    def run_cli(self):
        self.spec['evaluation']['evaluator']['adapter']['sha256']=runner._digest_file(self.evaluator)
        path=self.root/'spec.json';path.write_text(json.dumps(self.spec))
        completed=subprocess.run([sys.executable,str(SCRIPTS/'run_experiment.py'),'--spec',str(path),'--output',str(self.root/'output')],capture_output=True,text=True)
        summary_path=self.root/'output/summary.json'
        return completed,json.loads(summary_path.read_text()) if summary_path.exists() else None

    def no_launches(self,summary):
        self.assertEqual(summary['evaluation_error']['stage'],'evaluator-preflight')
        self.assertEqual(summary['variants'],[])
        self.assertIsNone(summary['champion'])
        events=[json.loads(line) for line in (self.root/'output/ledger.jsonl').read_text().splitlines()]
        self.assertFalse(any(row['event']=='variant_started' for row in events))
        self.assertEqual(events[-1]['event'],'experiment_failed')

    def test_compatible_judge_passes_before_real_candidates(self):
        completed,summary=self.run_cli()
        self.assertEqual(completed.returncode,0,completed.stderr)
        self.assertEqual(len(summary['variants']),2)
        events=[json.loads(line) for line in (self.root/'output/ledger.jsonl').read_text().splitlines()]
        event_names=[row['event'] for row in events]
        self.assertLess(event_names.index('evaluator_preflight_passed'),event_names.index('variant_started'))
        request=json.loads((self.root/'output/calibration/evaluation/request.json').read_text())
        self.assertEqual([row['variant_id'] for row in request['candidates']],['positive','negative'])
        self.assertTrue(all(set(row)=={'variant_id','execution','output'} for row in request['candidates']))

    def test_numeric_protocol_refuses_before_launch(self):
        self.evaluator.write_text("import json,sys\nfrom pathlib import Path\nPath(sys.argv[2]).write_text(json.dumps({'schema_version':1,'scores':[]}))\n")
        completed,summary=self.run_cli()
        self.assertNotEqual(completed.returncode,0)
        self.no_launches(summary)

    def test_always_pass_judge_fails_negative_control(self):
        self.evaluator.write_text(self.evaluator.read_text().replace("'satisfied' if passed else 'not-satisfied'","'satisfied'"))
        _,summary=self.run_cli();self.no_launches(summary)
        self.assertIn("'negative'",summary['evaluation_error']['message'])
        self.assertIn('expected',summary['evaluation_error']['message'])

    def test_timeout_is_preflight_and_zero_launches(self):
        self.evaluator.write_text('import time\ntime.sleep(5)\n')
        self.spec['execution_limits']['evaluator_timeout_ms']=50
        _,summary=self.run_cli();self.no_launches(summary)
        self.assertEqual(summary['evaluation_error']['kind'],'timeout')

    def test_case_snapshot_tamper_is_rejected_before_launch(self):
        self.evaluator.write_text(self.evaluator.read_text()+"\np=Path(sys.argv[1]).parents[2]/'calibration.json'\np.chmod(0o644)\np.write_text('{}')\n")
        _,summary=self.run_cli();self.no_launches(summary)
        self.assertIn('calibration cases changed',summary['evaluation_error']['message'])

    def test_presented_request_tamper_is_rejected_before_launch(self):
        self.evaluator.write_text(self.evaluator.read_text()+"\nPath(sys.argv[1]).write_text('{}')\n")
        _,summary=self.run_cli();self.no_launches(summary)
        self.assertIn('request changed',summary['evaluation_error']['message'])

    def test_wrong_hash_refuses_without_output(self):
        self.spec['evaluation']['calibration']['sha256']='0'*64
        completed,summary=self.run_cli()
        self.assertEqual(completed.returncode,2)
        self.assertIsNone(summary)
        self.assertFalse((self.root/'output').exists())

    def test_missing_negative_coverage_refuses_without_output(self):
        self.cases['cases'][1]['expected_metrics']['quality']=1;self.freeze()
        completed,summary=self.run_cli()
        self.assertEqual(completed.returncode,2)
        self.assertIn('zero and one',completed.stderr)
        self.assertIsNone(summary)

    def test_missing_raw_output_is_invalid_before_launch(self):
        self.cases['cases'][1]['outcome']={};self.freeze()
        completed,_=self.run_cli();self.assertEqual(completed.returncode,2)
        self.assertIn('raw-output',completed.stderr)

    def test_v4_cannot_claim_observation_calibration(self):
        self.spec['schema_version']=4;del self.spec['evaluation']['assessment']
        completed,_=self.run_cli();self.assertEqual(completed.returncode,2)
