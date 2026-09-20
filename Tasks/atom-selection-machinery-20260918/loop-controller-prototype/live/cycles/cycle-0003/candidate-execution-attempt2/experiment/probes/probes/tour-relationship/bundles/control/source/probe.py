"""Execute frozen machine-authored PHPUnit tests; contain no product assertions."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

HOME_TASK = Path('/Users/kamenkamenov/memory-knowledge/Tasks/taggable-cross-location-discount-atoms-20260911/tour-prerequisite-structure')
TEST = Path('/Users/kamenkamenov/memory-knowledge/Tasks/atom-selection-machinery-20260918/loop-controller-prototype/verification-preparation-probe-v1/sources/TourDiscountPrerequisitesTest.php')
TEST_SHA = 'cf6953d7521fc8a091da4e0bdd17d1f2fdb8a4a5193522d4dc293815e051e3e5'
METHODS = dict(zip(
    ['configured-checkout-tour', 'multiple-prerequisites', 'unconfigured-checkout-tour', 'relationship-direction', 'isolated-migration-rollback'],
    ['testConfiguredCheckoutTourReturnsItsPrerequisite', 'testMultiplePrerequisitesArePreserved', 'testUnconfiguredCheckoutTourHasNoPrerequisites', 'testRelationshipDirectionDoesNotConfigureThePrerequisiteTour', 'testIsolatedMigrationRollbackPreservesExistingTours']))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def run_case(product_root, case_id, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    assert sha(TEST) == TEST_SHA, 'Frozen verification source changed'
    installed_test = product_root / 'tests/Unit/TourDiscountPrerequisitesTest.php'
    if installed_test.exists():
        assert sha(installed_test) == TEST_SHA, 'Selected test differs from frozen verification'
    command = ['/opt/homebrew/bin/php', '-d', 'error_reporting=8191',
               '/Users/kamenkamenov/taggable-server/vendor/bin/phpunit', '--no-configuration',
               '--bootstrap', '/Users/kamenkamenov/taggable-server/vendor/autoload.php',
               '--filter', METHODS[case_id] + '$', '--log-junit', str(output / 'junit.xml'), str(TEST)]
    env = os.environ.copy()
    env['TAGGABLE_SOURCE_ROOT'] = str(product_root)
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=60)
    (output / 'stdout.txt').write_text(result.stdout)
    (output / 'stderr.txt').write_text(result.stderr)
    cases = ET.parse(output / 'junit.xml').getroot().findall('.//testcase')
    raw = {'case_id': case_id, 'returncode': result.returncode, 'test_sha256': sha(TEST),
           'tests': [{'name': c.attrib['name'], 'assertions': int(c.attrib.get('assertions', 0)),
                      'failures': len(c.findall('failure')), 'errors': len(c.findall('error')),
                      'skipped': len(c.findall('skipped'))} for c in cases],
           'junit_sha256': sha(output / 'junit.xml')}
    (output / 'result.json').write_text(json.dumps(raw, indent=2) + '\n')
    return raw

if __name__ == '__main__':
    if os.environ['EXPERIMENT_VARIANT_ID'] == 'assembly':
        case = Path(os.environ['EXPERIMENT_INPUT_PATH']).stem
    else:
        case = json.loads(Path(os.environ['EXPERIMENT_VARIANT_PATH']).read_text())['configuration']['case_id']
    work = Path(os.environ['EXPERIMENT_RESULT_PATH']).parent / 'phpunit-evidence'
    raw = run_case(Path(__file__).parent, case, work)
    row = {'schema_version': 1, 'sequence': int(os.environ.get('EXPERIMENT_TELEMETRY_SEQUENCE_START', '1')),
           'variant_id': os.environ['EXPERIMENT_VARIANT_ID'], 'recorded_at': datetime.now(timezone.utc).isoformat(),
           'event': 'work_completed', 'message': 'Executed one frozen machine-authored PHPUnit case against the selected source and isolated SQLite database',
           'evidence_sha256': raw['junit_sha256'], 'observations': raw}
    with Path(os.environ['EXPERIMENT_TELEMETRY_PATH']).open('a') as f:
        f.write(json.dumps(row) + '\n')
    Path(os.environ['EXPERIMENT_RESULT_PATH']).write_text(json.dumps({'schema_version': 1,
        'variant_id': os.environ['EXPERIMENT_VARIANT_ID'], 'status': 'completed', 'outcome': {'raw': raw}, 'metrics': {}, 'error': None}))
    print(json.dumps({'raw': raw}))
