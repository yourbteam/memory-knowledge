"""Atom-one real runner checks and observation boundary adversarial cases."""
import asyncio
import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/experiment-machinery/scripts'
spec = importlib.util.spec_from_file_location('quality_runner', SCRIPTS / 'run_experiment.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
independent = runner._independent


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.target = self.root / 'target'
        self.target.mkdir()
        self.adapter = self.target / 'candidate.py'
        self.adapter.write_text('''import json, os
from pathlib import Path
variant=json.loads(Path(os.environ['EXPERIMENT_VARIANT_PATH']).read_text())
result={'schema_version':1,'variant_id':os.environ['EXPERIMENT_VARIANT_ID'],'status':'completed',
'outcome':{'judgments':[{'verdict':'clear','quote':'Long page quotation is not actionable advice.'}],
'actionable_quote_count':variant['configuration']['count']},'metrics':{'quality':999},'error':None}
Path(os.environ['EXPERIMENT_RESULT_PATH']).write_text(json.dumps(result))
''')
        self.evaluator = self.root / 'judge.py'
        self.evaluator.write_text('''import json, sys
from pathlib import Path
request=json.loads(Path(sys.argv[1]).read_text())
assert request['schema_version']==2
judgments=[]
for candidate in request['candidates']:
 assert set(candidate)=={'variant_id','execution','output'}
 assert set(candidate['output'])=={'judgments'}
 observations=[]
 for criterion in request['criteria']:
  item=candidate['output']['judgments'][0]
  passed=item.get('verdict')=='clear' if criterion['id']=='classification' else bool(item.get('action'))
  observations.append({'criterion_id':criterion['id'],'verdict':'satisfied' if passed else 'not-satisfied',
   'output_pointer':'/judgments/0','reference_pointer':criterion['reference_pointer'],
   'reason':'Inspected verdict and action fields against frozen reference; quotation length gives no action credit.'})
 judgments.append({'variant_id':candidate['variant_id'],'observations':observations})
Path(sys.argv[2]).write_text(json.dumps({'schema_version':2,'judgments':judgments}))
''')
        self.reference = self.root / 'reference.json'
        self.reference.write_text(json.dumps({'classification':'clear','action':'an explicit action must exist'}))
        frozen = self.root / 'input.json'
        frozen.write_text('{}')
        ref=lambda path: {'path':str(path),'sha256':runner._digest_file(path)}
        self.spec={'schema_version':5,'experiment_id':'observation-test','hypothesis':'Claim mutations cannot improve independent scores.',
          'target':{'machinery':'sample','phase':'judgment','source':{'path':str(self.target),'sha256':runner._snapshot_source(self.target)[1]},'entrypoint':'candidate.py'},
          'frozen_input':ref(frozen),'execution_limits':{'variant_timeout_ms':5000,'evaluator_timeout_ms':5000},
          'variants':[{'id':identity,'command':[sys.executable,str(self.adapter)],'adapter':ref(self.adapter),'configuration':{'count':count}} for identity,count in [('control',0),('inflated',999)]],
          'evaluation':{'metrics':[{'name':'quality','direction':'maximize'}],
          'evaluator':{'adapter':ref(self.evaluator),'command':['{python}','{evaluation-adapter}','{evaluation-request}','{evaluation-response}']},
          'assessment':{'reference':ref(self.reference),'output_fields':['judgments'],'criteria':[
          {'id':'classification','metric':'quality','reference_pointer':'/classification'},
          {'id':'action','metric':'quality','reference_pointer':'/action'}]}}}

    def tearDown(self):
        self.temp.cleanup()

    def run_spec(self):
        path=self.root/'spec.json'
        path.write_text(json.dumps(self.spec))
        return asyncio.run(runner.run(path,self.root/'output'))

    def test_real_runner_claim_mutations_and_long_quote(self):
        summary=self.run_spec()
        self.assertEqual(summary['status'],'completed',summary)
        self.assertEqual([row['metrics']['quality'] for row in summary['variants']],[0.5,0.5])
        request=json.loads((self.root/'output/evaluation/request.json').read_text())
        self.assertEqual(request['reference'],json.loads(self.reference.read_text()))
        self.assertEqual(request['candidates'][0]['output'],request['candidates'][1]['output'])
        self.assertNotIn('result_sha256',request['candidates'][0])
        self.assertEqual((self.root/'output/assessment-reference.json').read_bytes(),self.reference.read_bytes())

    def response(self):
        self.run_spec()
        return (json.loads((self.root/'output/evaluation/response.json').read_text()),
                json.loads((self.root/'output/evaluation/request.json').read_text()))

    def test_numeric_scores_are_rejected(self):
        response,request=self.response()
        with self.assertRaises(ValueError):
            independent.score({'schema_version':1,'scores':[{'variant_id':'control','metrics':{'quality':999}}]},request)

    def test_invalid_observations_fail_closed(self):
        response,request=self.response()
        mutations=[lambda row:row['observations'].reverse(),
                   lambda row:row['observations'].pop(),
                   lambda row:row['observations'][0].update(output_pointer='/actionable_quote_count'),
                   lambda row:row['observations'][0].update(reference_pointer='/action'),
                   lambda row:row['observations'][0].update(verdict='cannot-assess'),
                   lambda row:row['observations'][0].update(reason='')]
        for mutation in mutations:
            bad=copy.deepcopy(response)
            mutation(bad['judgments'][0])
            with self.assertRaises(ValueError): independent.score(bad,request)

    def test_root_pointer_can_report_absence(self):
        response,request=self.response()
        response['judgments'][0]['observations'][1]['output_pointer']=''
        self.assertEqual(independent.score(response,request)['control']['quality'],0.5)

    def test_reference_drift_preflight_is_output_free(self):
        self.reference.write_text('{}')
        with self.assertRaises(runner.ExperimentError):self.run_spec()
        self.assertFalse((self.root/'output').exists())

    def test_cannot_assess_terminalizes(self):
        self.evaluator.write_text(self.evaluator.read_text().replace("'satisfied' if passed else 'not-satisfied'","'cannot-assess'"))
        self.spec['evaluation']['evaluator']['adapter']['sha256']=runner._digest_file(self.evaluator)
        summary=self.run_spec()
        self.assertEqual(summary['status'],'failed')
        self.assertIsNone(summary['champion'])
        self.assertIn('cannot-assess',summary['evaluation_error']['message'])

    def test_original_reference_change_does_not_replace_frozen_expectation(self):
        original=runner._execute
        async def execute(*args, **kwargs):
            self.reference.write_text('{"classification":"reject"}')
            return await original(*args, **kwargs)
        with patch.object(runner, '_execute', execute):
            summary=self.run_spec()
        self.assertEqual(summary['status'],'completed')
        request=json.loads((self.root/'output/evaluation/request.json').read_text())
        self.assertEqual(request['reference']['classification'],'clear')

    def test_frozen_reference_mutation_fails(self):
        original=runner._execute
        async def execute(*args, **kwargs):
            reference=self.root/'output/assessment-reference.json'
            reference.chmod(0o644)
            reference.write_text('{}')
            return await original(*args, **kwargs)
        with patch.object(runner, '_execute', execute):
            summary=self.run_spec()
        self.assertEqual(summary['status'],'failed')
        self.assertIsNone(summary['champion'])
        self.assertIn('reference changed',summary['evaluation_error']['message'])

    def test_evaluator_cannot_rewrite_presented_request(self):
        self.evaluator.write_text(self.evaluator.read_text() + "\nPath(sys.argv[1]).write_text('{}')\n")
        self.spec['evaluation']['evaluator']['adapter']['sha256']=runner._digest_file(self.evaluator)
        summary=self.run_spec()
        self.assertEqual(summary['status'],'failed')
        self.assertIn('request changed',summary['evaluation_error']['message'])

    def test_v4_legacy_numeric_evaluator_remains_runnable(self):
        self.spec['schema_version']=4
        del self.spec['evaluation']['assessment']
        self.evaluator.write_text("import json,sys\nfrom pathlib import Path\nr=json.loads(Path(sys.argv[1]).read_text())\nPath(sys.argv[2]).write_text(json.dumps({'schema_version':1,'scores':[{'variant_id':c['variant_id'],'metrics':{'quality':0}} for c in r['candidates']]}))\n")
        self.spec['evaluation']['evaluator']['adapter']['sha256']=runner._digest_file(self.evaluator)
        summary=self.run_spec()
        self.assertEqual(summary['status'],'completed')

if __name__=='__main__': unittest.main()

class PipelineQualityTests(unittest.TestCase):
    def test_full_pipeline_preserves_relative_reference_and_observation_scores(self):
        """Move the reference through full-run, all-probe, cross-case and single-case seams."""
        fixture_path = Path(__file__).with_name('test_development_probe_candidate.py')
        fixture_spec = importlib.util.spec_from_file_location('quality_pipeline_fixture', fixture_path)
        fixture = importlib.util.module_from_spec(fixture_spec)
        fixture_spec.loader.exec_module(fixture)
        for name, filename in {
            'CANDIDATE': 'development_probe_candidate.py', 'RUNNER': 'run_experiment.py',
            'LAUNCHER': 'development_probe_experiment.py', 'CROSS_CASE': 'development_probe_cross_case.py',
            'ALL_PROBES': 'development_probe_all_probes.py', 'COMPOSE': 'development_probe_compose.py',
            'FINAL_VALIDATION': 'development_probe_final_validation.py', 'FULL_RUN': 'development_probe_run.py',
        }.items():
            setattr(fixture, name, SCRIPTS / filename)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            _, baseline, all_request, _, _ = fixture._composition_fixture(root)
            all_value = json.loads(all_request.read_text())
            judge = root / 'independent-observer.py'
            judge.write_text('''import json,sys
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text())
answers=[]
for c in r['candidates']:
 assert set(c['output'])=={'features'}
 observations=[]
 for criterion in r['criteria']:
  expected=r['reference']['required_feature']
  actual=c['output']['features']
  observations.append({'criterion_id':criterion['id'],
   'verdict':'satisfied' if expected in actual else 'not-satisfied',
   'output_pointer':'/features','reference_pointer':criterion['reference_pointer'],
   'reason':f'Actual features {actual!r}; independently required feature {expected!r}.'})
 answers.append({'variant_id':c['variant_id'],'observations':observations})
Path(sys.argv[2]).write_text(json.dumps({'schema_version':2,'judgments':answers}))
''')
            references = {}
            for item in all_value['probe_requests']:
                probe = item['probe_id']
                path = Path(item['request'])
                reference = root / f'{probe}-reference.json'
                reference.write_text(json.dumps({'required_feature': 'runner-a' if probe == 'runner' else 'selector-b'}))
                references[probe] = reference
                value = json.loads(path.read_text())
                value['assessment'] = {
                    'reference': {'path': reference.name, 'sha256': fixture._digest(reference)},
                    'output_fields': ['features'],
                    'criteria': [{'id':'feature-present','metric':'quality','reference_pointer':'/required_feature'}],
                }
                value['evaluator']['adapter'] = {'path':str(judge),'sha256':fixture._digest(judge)}
                path.write_text(json.dumps(value))
            final_judge = root / 'final-judge.py'
            final_judge.write_text(fixture._assessment_adapter({'works':'satisfied','refuses':'satisfied'}))
            request = fixture._whole_run_request(root/'full.json',all_request,baseline,final_judge)
            output = root / 'output'
            completed = fixture._run_whole_process(request,output)
            self.assertEqual(completed.returncode,0,completed.stderr)
            self.assertEqual(json.loads(completed.stdout)['verdict'],'passed')
            experiments = list(output.glob('probes/probes/*/cases/*/experiment.json'))
            self.assertEqual(len(experiments),4)
            for path in experiments:
                specification = json.loads(path.read_text())
                self.assertEqual(specification['schema_version'],5)
                self.assertTrue(Path(specification['evaluation']['assessment']['reference']['path']).is_absolute())
                experiment = path.parent/'experiment'
                presented = json.loads((experiment/'evaluation/request.json').read_text())
                self.assertEqual(presented['schema_version'],2)
                self.assertIn(presented['reference']['required_feature'],('runner-a','selector-b'))
                summary = json.loads((experiment/'summary.json').read_text())
                self.assertEqual({row['metrics']['quality'] for row in summary['variants']},{0.0,1.0})
