"""Qualification and cross-case ranking through real experiment entry points."""
import copy
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

_quality_spec = importlib.util.spec_from_file_location(
    'selection_quality_fixture', Path(__file__).with_name('test_experiment_quality.py'))
_quality = importlib.util.module_from_spec(_quality_spec)
_quality_spec.loader.exec_module(_quality)
QualityTests, runner, SCRIPTS = _quality.QualityTests, _quality.runner, _quality.SCRIPTS

sys.path.insert(0,str(SCRIPTS))
_cross_spec=importlib.util.spec_from_file_location('quality_cross_case',SCRIPTS/'development_probe_cross_case.py')
cross=importlib.util.module_from_spec(_cross_spec)
_cross_spec.loader.exec_module(cross)


class SelectionTests(QualityTests):
    def cli_scores(self, scores, minimums=None):
        self.spec['schema_version']=4
        self.spec['evaluation'].pop('assessment')
        self.spec['evaluation']['metrics']=[{'name':name,'direction':'maximize'} for name in scores['control']]
        if minimums is not None:self.spec['evaluation']['selection']={'minimums':minimums}
        self.evaluator.write_text('import json,sys\nfrom pathlib import Path\nr=json.loads(Path(sys.argv[1]).read_text())\nscores='+repr(scores)+"\nPath(sys.argv[2]).write_text(json.dumps({'schema_version':1,'scores':[{'variant_id':c['variant_id'],'metrics':scores[c['variant_id']]} for c in r['candidates']]}))\n")
        self.spec['evaluation']['evaluator']['adapter']['sha256']=runner._digest_file(self.evaluator)
        path=self.root/'spec.json';path.write_text(json.dumps(self.spec))
        completed=subprocess.run([sys.executable,str(SCRIPTS/'run_experiment.py'),'--spec',str(path),'--output',str(self.root/'output')],capture_output=True,text=True)
        return completed,json.loads((self.root/'output/summary.json').read_text())

    def test_groundless_leader_is_disqualified(self):
        completed,result=self.cli_scores({'control':{'classification':3,'grounded':0},'inflated':{'classification':2,'grounded':2}},{'grounded':1})
        self.assertEqual(completed.returncode,0,completed.stderr)
        self.assertEqual(result['champion'],'inflated')
        self.assertTrue(result['variants'][0]['eligible'])
        self.assertFalse(result['variants'][0]['qualified'])
        self.assertEqual(result['variants'][0]['metrics']['classification'],3)

    def test_qualified_exact_tie_is_no_advantage(self):
        completed,result=self.cli_scores({'control':{'quality':1},'inflated':{'quality':1}},{'quality':1})
        self.assertEqual(completed.returncode,0)
        self.assertIsNone(result['champion'])
        self.assertEqual(result['selection_outcome'],'no-demonstrated-advantage')
        self.assertEqual(len(result['ranking']),2)

    def test_all_unqualified_preserves_scores(self):
        completed,result=self.cli_scores({'control':{'quality':0},'inflated':{'quality':0}},{'quality':1})
        self.assertEqual(completed.returncode,0)
        self.assertEqual(result['selection_outcome'],'no-qualified-candidate')
        self.assertEqual(result['ranking'],[])
        self.assertEqual(len(result['variants']),2)

    def test_legacy_tie_remains_historical(self):
        _,result=self.cli_scores({'control':{'quality':1},'inflated':{'quality':1}})
        self.assertEqual(result['champion'],'control')

    def test_v5_defaults_to_all_criteria_satisfied(self):
        result=self.run_spec()
        self.assertIsNone(result['champion'])
        self.assertEqual(result['selection_outcome'],'no-qualified-candidate')

    def test_invalid_minimums_are_output_free(self):
        for minimums in ({},{'unknown':1},{'quality':float('nan')},{'quality':True},{'quality':2}):
            self.spec['evaluation']['selection']={'minimums':minimums}
            with self.assertRaises(runner.ExperimentError):self.run_spec()
            self.assertFalse((self.root/'output').exists())

    def test_explicit_subset_does_not_gate_optional_metric(self):
        _,result=self.cli_scores({'control':{'quality':1,'optional':0},'inflated':{'quality':0,'optional':10}},{'quality':1})
        self.assertEqual(result['champion'],'control')


class CrossCaseSelectionTests(unittest.TestCase):
    def probe(self):
        return {'id':'p','approaches':[{'id':'a'},{'id':'b'}],
          'evaluation':{'metrics':[{'name':'quality','direction':'maximize'}],
                        'across_cases':[{'name':'quality','method':'mean'}]}}

    def test_average_cannot_hide_one_failed_case(self):
        result=cross._aggregate(self.probe(),['red','green'],
          {'red':{'a':{'quality':0},'b':{'quality':1}},'green':{'a':{'quality':10},'b':{'quality':1}}},
          {'minimums':{'quality':1}})
        self.assertEqual(result['champion'],'b')
        self.assertFalse(result['qualifications'][0]['qualified'])
        self.assertEqual(result['qualifications'][0]['failures'][0]['case_id'],'red')

    def test_one_case_tie_does_not_prevent_global_winner(self):
        result=cross._aggregate(self.probe(),['red','green'],
          {'red':{'a':{'quality':1},'b':{'quality':1}},'green':{'a':{'quality':2},'b':{'quality':1}}},
          {'minimums':{'quality':1}})
        self.assertEqual(result['champion'],'a')

    def test_equal_aggregate_is_no_advantage(self):
        result=cross._aggregate(self.probe(),['red','green'],
          {'red':{'a':{'quality':1},'b':{'quality':2}},'green':{'a':{'quality':2},'b':{'quality':1}}},
          {'minimums':{'quality':1}})
        self.assertIsNone(result['champion'])
        self.assertEqual(result['selection_outcome'],'no-demonstrated-advantage')

class PipelineSelectionTests(unittest.TestCase):
    def test_full_comparison_preserves_all_cases_when_nobody_qualifies(self):
        import tempfile
        fixture_path=Path(__file__).with_name('test_development_probe_candidate.py')
        module_spec=importlib.util.spec_from_file_location('selection_fixture',fixture_path)
        fixture=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(fixture)
        for name,filename in {'RUNNER':'run_experiment.py','ALL_PROBES':'development_probe_all_probes.py'}.items():
            setattr(fixture,name,SCRIPTS/filename)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve()
            _,_,all_request,_,_=fixture._composition_fixture(root)
            for item in json.loads(all_request.read_text())['probe_requests']:
                path=Path(item['request']);value=json.loads(path.read_text())
                value['selection']={'minimums':{'quality':3}}
                path.write_text(json.dumps(value))
            output=root/'output'
            completed=subprocess.run([sys.executable,str(SCRIPTS/'development_probe_all_probes.py'),'run',str(all_request),str(output)],capture_output=True,text=True)
            self.assertEqual(completed.returncode,0,completed.stderr)
            self.assertEqual(json.loads(completed.stdout)['status'],'no-recommendation')
            self.assertFalse((output/'promotion-candidates.json').exists())
            cases=list(output.glob('probes/*/cases/*/launch-summary.json'))
            self.assertEqual(len(cases),4)
            for path in cases:
                result=json.loads(path.read_text())
                self.assertEqual(result['status'],'completed')
                self.assertEqual(result['selection_outcome'],'no-qualified-candidate')
                self.assertFalse((path.parent/'recommendation.json').exists())
