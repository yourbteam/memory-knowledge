import importlib.util
import json
from pathlib import Path
import sys
import unittest


BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
SPEC = importlib.util.spec_from_file_location('prepared_execution_runtime_permissions', BASE / 'prepared_execution.py')
prepared = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepared)


class RuntimePermissionContractTest(unittest.TestCase):
    def test_complete_execution_contract_has_explicit_precedence(self):
        request = {
            'allowed_paths': ['experiment/runtime-artifact.bin'],
            'context': json.dumps({
                'assignment': {
                    'execution_plan': (
                        'Map a temporary write to experiment/runtime-artifact.bin.'
                    )
                }
            }),
            'constraints': 'old constraints',
        }
        runtime = {
            'schema_version': 1,
            'kind': 'docker',
            'entrypoint': {'timeout_seconds': 180},
            'path_mapping': {},
            'filesystem': {},
            'environment': {},
            'verified_runtime': {},
            'isolation': {},
        }
        contract = prepared.builder_execution_contract(runtime, request['allowed_paths'])

        result = prepared.generation_request(request, contract)
        supplied = json.loads(result['context'])['builder_execution_contract']

        self.assertEqual(supplied, contract)
        self.assertIn('follow this contract', supplied['authority']['this_contract'])
        self.assertIn('supersedes conflicting execution mechanics', result['constraints'])
        self.assertEqual(result['allowed_paths'], ['experiment/runtime-artifact.bin'])
        self.assertEqual(supplied['write_contract']['code_edit_paths'], result['allowed_paths'])
        self.assertEqual(supplied['write_contract']['runtime_write_directories'], ['experiment/results'])
        self.assertIn('Map a temporary write', json.loads(result['context'])['assignment']['execution_plan'])

    def test_evidence_contract_matches_downstream_reader(self):
        runtime = {
            'schema_version': 1,
            'kind': 'docker',
            'entrypoint': {'timeout_seconds': 180},
            'path_mapping': {},
            'filesystem': {},
            'environment': {},
            'verified_runtime': {'status': 'verified-before-generation'},
            'isolation': {},
        }
        contract = prepared.builder_execution_contract(runtime, ['experiment/run.py'])

        self.assertEqual(contract['runtime']['entrypoint']['timeout_seconds'], 180)
        self.assertEqual(contract['evidence']['output_root'], 'experiment/results')
        self.assertEqual(contract['evidence']['report_path'], 'experiment/report.md')
        self.assertEqual(contract['evidence']['case_trace']['filename_suffix'], '.trace.json')
        self.assertEqual(contract['evidence']['case_trace']['required_status'], 'checked')
        self.assertEqual(contract['evidence']['process_record']['filename_suffix'], '.process.json')
        self.assertEqual(contract['evidence']['review_transport_limits_bytes'], {
            'report': prepared.MAX_REVIEW_REPORT_BYTES,
            'artifact': prepared.MAX_REVIEW_ARTIFACT_BYTES,
            'json_field': prepared.MAX_REVIEW_JSON_FIELD_BYTES,
        })


if __name__ == '__main__':
    unittest.main()
