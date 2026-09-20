"""Collect retained build provenance for review; never infer promotion or approval."""
import difflib
import hashlib
import json
from pathlib import Path
import subprocess
from build_preparation import read, ref, save, sha, verify


def collect(prepared, execution, destination):
    plan = read(Path(prepared['review_template']['path']).parent / 'plan.json')
    build = read(verify(plan['build_preparation']))
    # The plan must point back to the exact review template being consumed.
    if plan['review_template'] != prepared['review_template']:
        raise ValueError('Review provenance plan belongs to a different template')
    inputs = [verify(r) for r in build['evidence']]
    frozen_paths = [p for p in inputs if p.name == 'input-state.json']
    if len(frozen_paths) != 1:
        raise ValueError('Review needs exactly one retained build baseline/runtime record')
    frozen_path = frozen_paths[0]; frozen = read(frozen_path)
    creation = read(verify(prepared['creation_request']))
    context = json.loads(creation['context'])
    runtime = frozen['runtime']
    repository = Path(runtime['phpunit']).parents[2]
    def cmd(argv):
        return subprocess.run(argv, capture_output=True, check=True).stdout
    def git(*args):return cmd(['git', '-C', str(repository), *args])
    untracked = git('ls-files', '--others', '--exclude-standard', '-z').split(b'\0')
    current = {'branch': git('branch', '--show-current').decode().strip(),
               'head': git('rev-parse', 'HEAD').decode().strip(),
               'diff_sha256': hashlib.sha256(git('diff', 'HEAD', '--binary')).hexdigest(),
               'untracked': {n.decode(): sha(repository / n.decode()) for n in untracked if n and (repository / n.decode()).is_file()}}
    if current != frozen['checkout_before']:
        raise ValueError('Current checkout differs from recorded pre-build state; inspect preservation before review')
    if git('rev-parse', frozen['branch']).decode().strip() != frozen['commit']:
        raise ValueError('Delivery branch moved; this candidate baseline needs reassessment')
    for key, path in [('autoload_sha256', Path(runtime['autoload'])),
                      ('phpunit_sha256', Path(runtime['phpunit'])),
                      ('installed_sha256', repository / 'vendor/composer/installed.json')]:
        if sha(path) != runtime[key]:raise ValueError('Dependency changed since execution preparation: ' + str(path))
    php_version = cmd([runtime['php'], '--version']).decode()
    if php_version != runtime['php_version']:raise ValueError('PHP runtime changed since execution preparation')
    assembly = execution / 'experiment/composition/assembly'
    spec = read(assembly / 'assembly.json')
    before = {r['path']: r['sha256'] for r in creation['files']}
    diff = []; provenance = []
    historical = {r['path']: r for r in context['historical_implementation']}
    for op in spec['operations']:
        path = op['path']; after = assembly / 'source' / path
        verify({'path': str(after), 'sha256': op['sha256']})
        old = Path(creation['baseline']) / path
        old_text = verify({'path': str(old), 'sha256': before[path]}).read_text() if path in before else ''
        diff.extend(difflib.unified_diff(old_text.splitlines(True), after.read_text().splitlines(True), fromfile='baseline/' + path, tofile='candidate/' + path))
        if path in historical:
            record = historical[path]
            if hashlib.sha256(record['text'].encode()).hexdigest() != record['sha256']:
                raise ValueError('Historical source content differs from its retained hash: ' + path)
            provenance.append({'path': path, 'historical_origin': record['origin'], 'historical_sha256': record['sha256'],
                               'candidate_sha256': sha(after), 'unchanged_historical_reuse': sha(after) == record['sha256']})
    destination.mkdir(parents=True, exist_ok=True)
    diff_path = destination / 'candidate.diff'
    raw = ''.join(diff)
    if diff_path.exists() and diff_path.read_text() != raw:raise ValueError('Retained candidate diff changed')
    if not diff_path.exists():diff_path.write_text(raw)
    record = {'build_preparation': plan['build_preparation'], 'baseline_commit': build['baseline_commit'],
              'delivery_branch': frozen['branch'], 'retained_candidate': ref(assembly / 'assembly.json'),
              'retained_diff': ref(diff_path), 'historical_reuse': provenance,
              'checkout_before': frozen['checkout_before'], 'checkout_after': current,
              'checkout_preserved': True, 'runtime_record': runtime,
              'runtime_recheck': 'PHP version and installed-package metadata, PHPUnit and autoload hashes still match the saved pre-execution record. This is an after-run recheck, not continuous monitoring.',
              'isolation': 'Candidate and assembly are retained outside the product checkout. The delivery branch still points to the recorded baseline. No checkout switch, delivery-branch application or product promotion has been performed.',
              'database_limitations': context['verification']['unverified_obligations'],
              'proof_boundary': 'Actual tests used isolated SQLite and current dependencies. Supplied historical MySQL DDL supports source inspection only; no actual MySQL migration execution occurred. PHP 8.5 is outside the declared Composer constraint; focused tests do not prove full application compatibility.',
              'promotion_applied': False, 'atom_complete': False}
    save(destination / 'build-evidence.json', record)
    return [frozen_path, destination / 'build-evidence.json', diff_path,
            execution / 'generation/result.json', assembly / 'assembly.json',
            Path(creation['baseline']) / 'probe.py']
