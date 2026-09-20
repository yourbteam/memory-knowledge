"""Collect observable delivery facts; the completion model judges sufficiency."""
import difflib
import hashlib
import subprocess
from pathlib import Path
from driver_contract import Refusal, read, reference, verify, save


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args])


def collect(config_path, request, execution, output):
    config_path = Path(config_path)
    config_ref = reference(config_path)
    config = read(config_path)
    save(output / 'delivery-context-binding.json', config_ref)
    root = Path(request['repository_root'])
    if str(root) != config['repository_root']:
        raise Refusal('Delivery context repository differs from the admitted repository')
    baseline_path = verify(config['baseline'])
    baseline = read(baseline_path)
    branch = git(root, 'branch', '--show-current').decode().strip()
    head = git(root, 'rev-parse', 'HEAD').decode().strip()
    if branch != baseline['branch'] or head != baseline['commit']:
        raise Refusal('Delivery branch or HEAD differs from the recorded pre-build baseline')
    surface = read(execution / 'promotion-surface.json')
    differences = []
    for change in surface['changes']:
        rel = change['path']; path = root / rel
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != change['after_sha256']:
            raise Refusal('Applied file differs from validated promotion: ' + rel)
        old = git(root, 'show', head + ':' + rel).decode() if change['before_sha256'] else ''
        if change['before_sha256'] and hashlib.sha256(old.encode()).hexdigest() != change['before_sha256']:
            raise Refusal('Committed baseline differs from promotion baseline: ' + rel)
        differences.extend(difflib.unified_diff(old.splitlines(True), path.read_text().splitlines(True), fromfile='baseline/' + rel, tofile='applied/' + rel))
    tracked = git(root, 'diff', '--name-only', 'HEAD', '-z').decode().split('\0')
    untracked = git(root, 'ls-files', '--others', '--exclude-standard', '-z').decode().split('\0')
    output_rel = str(execution.parent.relative_to(root)) + '/'
    observed = sorted(p for p in set(tracked + untracked) if p and not p.startswith(output_rel))
    expected = sorted(c['path'] for c in surface['changes'])
    other = Path(config['preserved_checkout'])
    before = baseline['checkout_before']
    now = {'branch': git(other, 'branch', '--show-current').decode().strip(),
           'head': git(other, 'rev-parse', 'HEAD').decode().strip(),
           'diff_sha256': hashlib.sha256(git(other, 'diff', 'HEAD', '--binary')).hexdigest()}
    checks = []
    for rel, expected_hash in before['untracked'].items():
        p = other / rel
        actual_hash = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() and not p.is_symlink() else None
        checks.append({'path': rel, 'before_sha256': expected_hash, 'after_sha256': actual_hash,
                       'unchanged': actual_hash == expected_hash})
    current_names = set(filter(None, git(other, 'ls-files', '--others', '--exclude-standard', '-z').decode().split('\0')))
    schemas = [{'reference': r, 'text': verify(r).read_text()} for r in config['schema_evidence']]
    result = {'baseline': config_ref, 'baseline_snapshot': reference(baseline_path),
              'delivery': {'branch': branch, 'head': head, 'observed_product_changes': observed,
                           'reviewed_paths': expected, 'only_reviewed_paths_changed': observed == expected,
                           'applied_diff': ''.join(differences), 'promotion_surface': reference(execution / 'promotion-surface.json')},
              'preservation': {'repository': str(other), 'before': before, 'after': now,
                               'branch_head_tracked_diff_unchanged': all(now[k] == before[k] for k in now),
                               'previous_untracked_files': checks,
                               'new_untracked_paths': sorted(current_names - set(before['untracked'])),
                               'observation_limit': 'Before/after observation only. Newly appearing or changed files are reported without inferring who changed them.'},
              'database': {'sources': schemas, 'evidence_level': 'Schema statements from the owner-supplied historical MySQL export. Not a live database inspection. No MySQL execution performed. Compatibility is for the assessor to judge; isolated execution used SQLite.'}}
    save(output / 'delivery-evidence.json', result)
    return result
