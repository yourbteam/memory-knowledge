"""Assess observed PHPUnit results, not candidate-reported scores."""
import json
import sys
import hashlib
from pathlib import Path

TEST_SHA = 'cf6953d7521fc8a091da4e0bdd17d1f2fdb8a4a5193522d4dc293815e051e3e5'
METHODS = dict(zip(
    ['configured-checkout-tour', 'multiple-prerequisites', 'unconfigured-checkout-tour', 'relationship-direction', 'isolated-migration-rollback'],
    ['testConfiguredCheckoutTourReturnsItsPrerequisite', 'testMultiplePrerequisitesArePreserved', 'testUnconfiguredCheckoutTourHasNoPrerequisites', 'testRelationshipDirectionDoesNotConfigureThePrerequisiteTour', 'testIsolatedMigrationRollbackPreservesExistingTours']))

def assess(raw):
    tests = raw.get('tests', [])
    good = (raw.get('returncode') == 0 and raw.get('test_sha256') == TEST_SHA and len(tests) == 1
            and tests[0]['name'] == METHODS.get(raw.get('case_id')) and tests[0]['assertions'] > 0
            and tests[0]['failures'] == tests[0]['errors'] == tests[0]['skipped'] == 0)
    return good, ('Exact frozen test executed assertions successfully.' if good else 'Frozen test did not pass, was skipped, changed, or did not execute exactly its named case.')

if __name__ == '__main__':
    request = json.loads(Path(sys.argv[1]).read_text())
    if 'candidates' in request:
        result = {'schema_version': 2, 'judgments': []}
        for candidate in request['candidates']:
            good, reason = assess(candidate['output']['raw'])
            result['judgments'].append({'variant_id': candidate['variant_id'], 'observations': [
                {'criterion_id': c['id'], 'verdict': 'satisfied' if good else 'not-satisfied',
                 'output_pointer': '/raw', 'reference_pointer': c['reference_pointer'], 'reason': reason}
                for c in request['criteria']]})
    else:
        e = next(e for e in request['execution_evidence'] if e['id'] == 'candidate-stdout')
        data = Path(e['path']).read_bytes()
        assert hashlib.sha256(data).hexdigest() == e['sha256']
        raw = json.loads(data)['raw']
        assert raw['case_id'] == request['case_id']
        good, reason = assess(raw)
        result = {'case_id': request['case_id'], 'verdict': 'satisfied' if good else 'not-satisfied',
                  'reason': reason, 'evidence_pointers': ['candidate-stdout', 'candidate-telemetry']}
    with Path(sys.argv[2]).open('x') as f:
        json.dump(result, f, indent=2)
