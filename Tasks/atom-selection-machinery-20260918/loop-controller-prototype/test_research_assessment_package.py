import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


CONTEXT = Path('/private/tmp/memory-knowledge-atom-selection-publish/skills/atom-assessment-machinery/scripts/context.py')
spec = importlib.util.spec_from_file_location('assessment_context_contract', CONTEXT)
context = importlib.util.module_from_spec(spec)
spec.loader.exec_module(context)


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    return {'path': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


class ResearchAssessmentPackageTest(unittest.TestCase):
    def fixture(self, root):
        goal = {'goal': {'id': 'goal-1', 'outcome': 'deliver feature'}}
        goal_ref = save(root / 'goal.json', goal)
        answers_ref = save(root / 'answers.json', {'snapshot': {'fixed_goal': goal_ref}})
        selection_ref = save(root / 'selection.json', {
            'goal': 'deliver feature', 'input_sha256': answers_ref['sha256']})
        raw = root / 'trace.txt'
        raw.write_text('prefix exact observed fact suffix\n')
        raw_ref = {'path': raw.name, 'sha256': hashlib.sha256(raw.read_bytes()).hexdigest()}
        process_ref = save(root / 'case.process.json', {'exit_status': 0, 'stderr': ''})
        trace_ref = save(root / 'case.trace.json', {'status': 'checked', 'checks': [
            {'name': 'held', 'observed_expected': True}]})
        execution_ref = save(root / 'execution.json', {
            'returncode': 0, 'timed_out': False, 'protected_changes': [],
            'generated_report_changed': True})
        generation_ref = save(root / 'generation.json', {})
        bindings_ref = save(root / 'bindings.json', {})
        provenance_ref = save(root / 'provenance.json', {
            'commit': 'abc123', 'source_files': [{'path': 'app/Foo.php', 'role': 'current product'}]})
        admitted = [raw_ref, process_ref, trace_ref, execution_ref, generation_ref,
                    bindings_ref, provenance_ref]
        package = {
            'schema_version': 2, 'kind': 'selected_research_assessment_package',
            'goal': goal_ref, 'selection': selection_ref, 'status': 'experiment_supported',
            'product_modified': False, 'goal_complete': False,
            'generation': generation_ref, 'execution': execution_ref,
            'execution_facts': {
                'execution_receipt': execution_ref, 'generation_receipt': generation_ref,
                'bindings': bindings_ref, 'source_provenance': provenance_ref,
                'source_commit': 'abc123', 'source_file_count': 1,
                'returncode': 0, 'timed_out': False, 'protected_changes': [],
                'generated_report_changed': True,
                'process_count': 1, 'trace_count': 1,
                'all_processes_passed': True, 'all_trace_checks_passed': True,
                'outcomes': [
                    {'evidence': process_ref, 'kind': 'process', 'exit_status': 0, 'stderr_empty': True},
                    {'evidence': trace_ref, 'kind': 'trace', 'status': 'checked',
                     'check_count': 1, 'failed_checks': []},
                ],
            },
            'review': {'cases': [{'id': 'case-1', 'verdict': 'supported', 'reason': 'observed',
                       'citations': [{'evidence': raw_ref, 'quote': 'exact observed fact',
                                      'occurrences': [{'start': 7, 'end': 26}]}]}],
                       'conclusion': 'supported', 'implementation_consequence': 'continue'},
            'raw_evidence': [raw_ref],
        }
        package_ref = save(root / 'package.json', package)
        result_ref = save(root / 'result.json', {
            'kind': 'selected_research_result', 'goal': goal_ref, 'selection': selection_ref,
            'evidence': admitted, 'assessment_package': package_ref})
        cycle = {'cycle_id': 'cycle-1', 'goal_id': 'goal-1', 'goal': goal_ref,
                 'input_answers': answers_ref, 'selection': selection_ref,
                 'research_result': result_ref, 'build': None, 'previous_cycle': None}
        return root / 'cycle.json', cycle, package

    def test_verifies_raw_evidence_without_putting_it_in_model_context(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cycle_path, cycle, _ = self.fixture(root)
            save(cycle_path, cycle)
            packet = context.assemble(root, cycle_path)
            self.assertEqual(packet['collection_status'], 'references_verified')
            self.assertIn('research_assessment_package', packet['records'])
            self.assertNotIn('research_evidence_0', packet['records'])

    def test_rejects_a_quote_whose_recorded_location_does_not_match(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cycle_path, cycle, package = self.fixture(root)
            package['review']['cases'][0]['citations'][0]['occurrences'][0]['start'] = 8
            cycle['research_result'] = save(root / 'result.json', {
                'kind': 'selected_research_result', 'goal': cycle['goal'],
                'selection': cycle['selection'],
                'evidence': [package['raw_evidence'][0],
                             package['execution_facts']['outcomes'][0]['evidence'],
                             package['execution_facts']['outcomes'][1]['evidence'],
                             package['execution_facts']['execution_receipt'],
                             package['execution_facts']['generation_receipt'],
                             package['execution_facts']['bindings'],
                             package['execution_facts']['source_provenance']],
                'assessment_package': save(root / 'package.json', package)})
            save(cycle_path, cycle)
            packet = context.assemble(root, cycle_path)
            self.assertEqual(packet['collection_status'], 'needs_inputs')
            self.assertEqual(packet['missing_or_inconsistent'][0]['code'], 'citation_mismatch')

    def test_rejects_an_execution_summary_that_disagrees_with_raw_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cycle_path, cycle, package = self.fixture(root)
            package['execution_facts']['all_processes_passed'] = False
            cycle['research_result'] = save(root / 'result.json', {
                'kind': 'selected_research_result', 'goal': cycle['goal'],
                'selection': cycle['selection'],
                'evidence': [package['raw_evidence'][0],
                             package['execution_facts']['outcomes'][0]['evidence'],
                             package['execution_facts']['outcomes'][1]['evidence'],
                             package['execution_facts']['execution_receipt'],
                             package['execution_facts']['generation_receipt'],
                             package['execution_facts']['bindings'],
                             package['execution_facts']['source_provenance']],
                'assessment_package': save(root / 'package.json', package)})
            save(cycle_path, cycle)
            packet = context.assemble(root, cycle_path)
            self.assertEqual(packet['collection_status'], 'needs_inputs')
            self.assertTrue(any(item['code'] == 'execution_fact_mismatch'
                                for item in packet['missing_or_inconsistent']))


if __name__ == '__main__':
    unittest.main()
