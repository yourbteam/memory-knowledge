"""Exercise existing public operators without model transmission or product execution.

The blocked run and eligible interview are intentionally separate. A successful
report is evidence, not installation, owner approval, or an implementation start.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

FIELDS = {'schema_version', 'blocked_request', 'description_run', 'description_sources',
          'requirements_run', 'requirements_document', 'requirements_coverage_sha256',
          'eligible_work', 'green_work', 'expected_sequence_sha256', 'operator_repository'}
HERE = Path(__file__).resolve().parent
SKILLS = HERE.parent.parent
REPOSITORY = SKILLS.parent
CASE_NAMES = (
    'blocked_mysql_first', 'shared_semantic_node', 'owner_only_gap',
    'inaccessible_and_stale_evidence', 'upstream_integrity', 'invalid_model_responses',
    'cycle_and_unresolved_contradiction', 'producer_cannot_grade_itself',
    'incomplete_blocker_closeout', 'ready_does_not_mean_approved', 'stale_sequence_approval',
    'approved_ordered_export', 'missing_completion_blocks_successor',
    'no_product_work_directory', 'no_repository_model_context', 'replay_preserves_packages')
REQUIREMENT_CASES = {'R1':[9,10,11,12,13,16], 'R2':[1,2,3,4,5,6,7,16],
                     'R3':[10,12,16], 'R4':[1,3,4,5,6,7,9,14,15],
                     'R5':[3,10,11,12,13], 'R6':[1,5,14,16], 'R7':[1,3,10,12]}
TEST_FILES = (
    'test_requirement_to_atom_readiness_operator.py', 'test_requirement_to_atom_readiness.py',
    'test_requirement_readiness_handoffs.py', 'test_readiness_criterion_agreement.py',
    'test_readiness_input_limits.py', 'test_readiness_reference_slots.py',
    'test_readiness_request_diagnostics.py', 'test_readiness_timeout_diagnostics.py',
    'test_readiness_timeout_recovery.py', 'test_readiness_transport_failures.py',
    'test_readiness_verification_admission.py')


class Refused(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Refused(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def regular(path):
    path = Path(path)
    require(path.is_absolute(), f'{path}: require an absolute path')
    require('..' not in path.parts, f'{path}: parent traversal is forbidden')
    require(not any(p.is_symlink() for p in (path, *path.parents)), f'{path}: linked paths are forbidden')
    require(path.is_file() and path.stat().st_nlink == 1, f'{path}: require a regular, unlinked file')
    require(path.stat().st_size <= 64 * 1024 * 1024, f'{path}: file exceeds 64 MiB')
    return path.read_bytes()


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, f'duplicate JSON key {key!r}')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(Refused(f'nonfinite JSON {value}')))


def descriptor(row):
    require(type(row) is dict and set(row) == {'path', 'sha256'}, 'descriptor: require exactly path and sha256')
    raw = regular(row['path'])
    require(digest(raw) == row['sha256'], f"{row['path']}: bytes differ from the supplied SHA-256")
    return raw


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def snapshot(root):
    return {str(p.relative_to(root)): digest(regular(p))
            for p in sorted(root.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}


class Observer:
    def __init__(self, output):
        self.output = output
        self.calls = []

    def event(self, stage, outcome):
        row = {'sequence':len(self.calls), 'stage':stage, 'outcome':outcome,
               'recorded_at_utc':datetime.now(timezone.utc).isoformat()}
        with (self.output/'telemetry.jsonl').open('a') as stream:
            stream.write(json.dumps(row)+'\n')
        print(json.dumps(row), flush=True)

    def call(self, module, *arguments, expected=0):
        command = [sys.executable, str(module), *map(str, arguments)]
        self.event(str(arguments[0]), 'started')
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=120,
                                    env={**os.environ, 'PYTHONDONTWRITEBYTECODE':'1'})
            record = {'command':command,'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
        except subprocess.TimeoutExpired as error:
            record = {'command':command, 'exit':None, 'stdout':str(error.stdout or ''),
                      'stderr':'120-second canary command deadline exceeded'}
        name = f'command-{len(self.calls):03d}.json'
        write(self.output/name, record)
        self.calls.append(name)
        self.event(str(arguments[0]), 'completed' if record['exit'] == expected else 'failed')
        require(record['exit'] == expected,
                f"{arguments[0]} returned {record['exit']}, expected {expected}: {record['stderr']}")
        return decode(record['stdout']) if expected == 0 else record


def checked_suite(xml_bytes):
    tree = ET.fromstring(xml_bytes)
    cases = list(tree.iter('testcase'))
    required = [f'test_c{i:02d}_{name}' for i,name in enumerate(CASE_NAMES,1)]
    require(cases and not any(list(c) for c in cases),
            'regression suite contains failures, errors, skips or unexamined test output; activation refused')
    for name in required:
        require(sum(c.get('name') == name for c in cases) == 1,
                f'required captured check {name} must pass exactly once')
    return {'tests':len(cases),'integration_cases':required,'requirements':REQUIREMENT_CASES}


def tested_sources():
    sources = [*HERE.glob('*.py'), *[REPOSITORY/'tests'/name for name in TEST_FILES],
               HERE.parent/'SKILL.md', HERE.parent/'agents/openai.yaml']
    return [{'path':str(p),'sha256':digest(regular(p))} for p in sorted(sources)]


def regression_gate(observer, operator):
    output = observer.output
    command = [str(operator/'scripts/run_pytest.sh'),
               *[str(REPOSITORY/'tests'/name) for name in TEST_FILES],
               '-q','--junitxml',str(output/'regressions.xml')]
    observer.event('regression-suite','started')
    result = subprocess.run(command,capture_output=True,text=True,timeout=120,
                            env={**os.environ,'READINESS_CANARY_REPORT':str(output/'operator-observations.json')})
    write(output/'regressions.json',{'command':command,'exit':result.returncode,
                                  'stdout':result.stdout,'stderr':result.stderr})
    require(result.returncode == 0, f'regression suite returned {result.returncode}; inspect regressions.json; activation refused')
    coverage = checked_suite(regular(output/'regressions.xml'))
    observer.event('regression-suite','passed')
    return coverage


def run(spec_path, output):
    raw = regular(spec_path)
    spec = decode(raw)
    require(type(spec) is dict and set(spec) == FIELDS and type(spec['schema_version']) is int
            and spec['schema_version'] == 1, f'canary input: require version 1 with exactly {sorted(FIELDS)}')
    request = decode(descriptor(spec['blocked_request']))
    # These are the production request fields, not a separate permissive boundary.
    boundary = request['runtime_boundary']
    limits = request['execution_limits']
    require(type(limits['model_timeout_ms']) is int and limits['model_timeout_ms'] > 0,
            'execution_limits.model_timeout_ms must be a positive integer')
    output = Path(output)
    require(output.is_absolute() and '..' not in output.parts and not output.exists(),
            'output: provide a new absolute directory without parent traversal')
    require(not any(p.is_symlink() for p in (output, *output.parents)), 'output: linked ancestry is forbidden')
    require(output.is_relative_to(Path(boundary['authorized_root'])), 'output: outside the authorized runtime root')
    protected = [Path(p) for p in boundary['target_repositories'] + boundary['product_edit_boundaries']]
    protected += [Path(spec[k]) for k in ('description_run','requirements_run','eligible_work','green_work')]
    for path in protected:
        require(path.is_absolute() and '..' not in path.parts and not any(p.is_symlink() for p in (path,*path.parents)), f'{path}: unsafe protected path')
        require(not output.is_relative_to(path) and not path.is_relative_to(output), f'output overlaps protected path {path}')
    descriptor(spec['description_sources'])
    descriptor(spec['requirements_document'])
    operator = Path(spec['operator_repository'])
    require(str(operator) in boundary['target_repositories'], 'operator_repository must be a declared repository')
    operator_scripts = operator/'skills/requirement-to-atom-readiness-machinery/scripts'
    # Existing ledgers bind upstream member locations, not only their bytes. Use
    # their unchanged installed operators as read-only dependencies, not rewritten
    # copies of history. Refuse a dependency that differs from this tested source.
    for source in HERE.glob('*.py'):
        if source.name != 'run_canary.py':
            require(regular(source) == regular(operator_scripts/source.name), f'{source.name}: installed operator differs from tested bytes')
    source_baseline = tested_sources()
    output.mkdir()
    observer = Observer(output)
    controller = operator_scripts/'readiness_controller.py'
    before = {str(p):snapshot(p) for p in protected if p in [Path(spec['description_run']),Path(spec['requirements_run'])]}
    try:
        exports = output/'exports'
        exports.mkdir()
        flags = []
        for path in boundary['target_repositories']:
            flags += ['--target-repository',path]
        for path in boundary['product_edit_boundaries']:
            flags += ['--product-boundary',path]
        observer.call(SKILLS/'description-machinery/scripts/export_handoff.py',
                      '--run',spec['description_run'],'--source-snapshots',spec['description_sources']['path'],
                      '--output-root',exports,'--output',exports/'description.json',*flags)
        observer.call(SKILLS/'requirements-machinery/scripts/cover.py','export-handoff',
                      '--work',spec['requirements_run'],'--document',spec['requirements_document']['path'],
                      '--expected-coverage-sha256',spec['requirements_coverage_sha256'],
                      '--output-root',exports,'--output',exports/'requirements.json',*flags)
        handoff = decode(regular(exports/'requirements.json'))
        inputs = output/'inputs'
        inputs.mkdir()
        request['description_handoff'] = {'path':str(exports/'description.json'),'sha256':digest(regular(exports/'description.json'))}
        request['requirements_handoff'] = {'path':str(exports/'requirements.json'),'sha256':digest(regular(exports/'requirements.json'))}
        for index, item in enumerate(request['evidence_manifests']):
            manifest = decode(descriptor(item))
            manifest['requirements_handoff_sha256'] = handoff['handoff_sha256']
            path = inputs/f'evidence-{index}.json'
            write(path, manifest)
            item.update(path=str(path),sha256=digest(regular(path)))
        request_path = output/'blocked-request.json'
        write(request_path,request)
        work = output/'blocked-work'
        work.mkdir()
        state = observer.call(controller,'start',request_path,work,'--expected-tip','0'*64)
        require(state['status'] == 'blocked' and state['next_action']['condition_id'] == 'mysql-query-timeout',
                'blocked case: expected MySQL evidence first, never a model or owner substitute')
        require(len(decode(regular(work/'run/queue.json'))) == 7, 'blocked case: expected all seven captured conditions')
        state = observer.call(controller,'verify-replay',work)
        observer.call(controller,'prepare-interview',work,'--expected-tip',state['ledger_tip'],expected=2)
        require(observer.call(controller,'verify-replay',work) == state, 'refused interview changed blocked state')
        observer.call(controller,'export-next-atom',work,'--expected-tip',state['ledger_tip'],expected=2)
        require(observer.call(controller,'verify-replay',work) == state, 'refused export changed blocked state')
        packaged = observer.call(controller,'compile-package',work,'--expected-tip',state['ledger_tip'])
        require(packaged['readiness'] == 'blocked', 'blocked package incorrectly became ready')
        require(observer.call(controller,'verify-replay',work) == packaged, 'blocked package replay differs')
        eligible = observer.call(controller,'verify-replay',spec['eligible_work'])
        proposals = eligible['interview_state']['proposals']
        require(len(proposals) == 1 and proposals[0]['family'] == 'verification-adequacy'
                and proposals[0]['verdict'] == 'inadequate', 'eligible case: expected independent rejection of producer self-grading')
        require(eligible['status'] != 'ready', 'a model proposal granted readiness')
        events = [decode(regular(p)) for p in sorted((Path(spec['eligible_work'])/'run/interviews').glob('*/event.json'))]
        completed = [e for e in events if e['event'] == 'interview_launch_finished']
        require(len(completed) == 1 and completed[0]['payload']['error'] is None
                and len(completed[0]['payload']['seats']) == 2,
                'eligible case: a submitted answer is not a retained provider launch')
        green = observer.call(controller,'verify-replay',spec['green_work'])
        require(green['readiness'] == 'ready' and green['approval_state'] == 'approved', 'green case lacks readiness or owner approval')
        require(green['interview_state']['compilation']['sequence_sha256'] == spec['expected_sequence_sha256'], 'green sequence differs from the declared capture')
        require(green['exported_atoms'] == 2, 'green capture must prove first release and exactly one successor')
        observer.call(controller,'export-next-atom',spec['green_work'],'--expected-tip',green['ledger_tip'],expected=2)
        require(observer.call(controller,'verify-replay',spec['green_work']) == green, 'refused successor changed green capture')
        require(all(snapshot(Path(path)) == value for path,value in before.items()), 'an upstream source run changed during the canary')
        report = {'schema_version':1,'status':'operator-paths-passed','activation_allowed':False,
                  'remaining':'Accumulated seven-requirement and sixteen-case coverage must pass before activation.',
                  'source_sha256':digest(raw),'commands':observer.calls,'model_calls':0,
                  'blocked_next':'mysql-query-timeout','blocked_conditions':7,
                  'eligible_verdict':'inadequate','green_exported_atoms':2,
                  'green_evidence':'Current replay of captured approval and release history; not a new build or owner decision.'}
        write(output/'operator-observations.json',report)
        report['coverage'] = regression_gate(observer,operator)
        report.update(status='passed',activation_allowed=True,
                      remaining=None,
                      activation_meaning='Eligible for reviewed promotion only; this command never installs or edits a skill.')
        require(tested_sources() == source_baseline, 'tested source changed during execution; activation refused')
        report['tested_sources'] = source_baseline
        report['artifacts'] = [{'path':p.name,'sha256':digest(regular(p))} for p in sorted(output.glob('*.json'))]
        report['regression_xml_sha256'] = digest(regular(output/'regressions.xml'))
        write(output/'report.json',report)
        return report
    except (Refused, OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        write(output/'report.json',{'schema_version':1,'status':'failed','activation_allowed':False,
                                  'reason':str(error),'commands':observer.calls})
        raise


def verify_report(path):
    report = decode(regular(path))
    require(report.get('status') == 'passed' and report.get('activation_allowed') is True,
            'report is incomplete or failed; activation refused')
    require(report['tested_sources'] == tested_sources(), 'tested source inventory or bytes differ')
    expected_artifacts = ['blocked-request.json', *[f'command-{i:03d}.json' for i in range(14)],
                          'operator-observations.json', 'regressions.json']
    require([row['path'] for row in report['artifacts']] == sorted(expected_artifacts),
            'report artifact inventory is incomplete or substituted')
    for row in report['artifacts']:
        require(Path(row['path']).name == row['path'], 'report artifact path is not a direct child')
        descriptor({'path':str(path.parent/row['path']),'sha256':row['sha256']})
    regression = decode(regular(path.parent/'regressions.json'))
    require(regression['exit'] == 0, 'regression execution did not pass')
    raw = regular(path.parent/'regressions.xml')
    require(digest(raw) == report['regression_xml_sha256'], 'regression report bytes changed')
    require(checked_suite(raw) == report['coverage'], 'derived coverage differs from the report')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest='operation',required=True)
    trial = sub.add_parser('run',allow_abbrev=False)
    trial.add_argument('request')
    trial.add_argument('output')
    check = sub.add_parser('verify',allow_abbrev=False)
    check.add_argument('report')
    args = parser.parse_args()
    try:
        result = run(Path(args.request),Path(args.output)) if args.operation == 'run' else verify_report(Path(args.report))
        print(json.dumps(result))
        return 0
    except (Refused,OSError,ValueError,KeyError,TypeError,subprocess.TimeoutExpired) as error:
        print(f'refused: {error}',file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
