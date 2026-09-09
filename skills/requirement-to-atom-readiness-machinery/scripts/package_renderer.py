"""Closed, read-only readiness package contract. Publication belongs to the controller."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import uuid

MANIFEST_FIELDS = ('schema_version', 'run_sha256', 'input_sha256', 'controller_sha256',
                   'ledger_prefix_tip', 'predecessor_manifest_sha256', 'readiness',
                   'approval_state', 'atom_sequence_sha256', 'members')
MEMBER_FIELDS = ('path', 'size', 'sha256', 'schema_version')
VERDICT_FIELDS = ('schema_version', 'readiness', 'requirements', 'next_action')
REQUIREMENT_FIELDS = ('requirement_id', 'disposition', 'maturity', 'reason')
READINESS_VALUES = ('blocked', 'needs_owner', 'ready')
APPROVAL_VALUES = ('not-approved', 'approved', 'rejected')


def package_schema():
    def closed(fields, properties):
        return {'type': 'object', 'additionalProperties': False,
                'required': list(fields), 'properties': properties}
    sha = {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}
    nullable_sha = {'anyOf': [sha, {'type': 'null'}]}
    member = closed(MEMBER_FIELDS, {
        'path': {'type': 'string', 'pattern': r'^(?!manifest\.json$)(?!/)(?!.*(?:^|/)\.{1,2}(?:/|$))[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*$'},
        'size': {'type': 'integer', 'minimum': 0}, 'sha256': sha,
        'schema_version': {'type': 'integer', 'const': 1}})
    result = closed(MANIFEST_FIELDS, {
        'schema_version': {'type': 'integer', 'const': 1},
        'run_sha256': sha, 'input_sha256': sha, 'controller_sha256': sha,
        'ledger_prefix_tip': sha, 'predecessor_manifest_sha256': nullable_sha,
        'readiness': {'enum': list(READINESS_VALUES)},
        'approval_state': {'enum': list(APPROVAL_VALUES)},
        'atom_sequence_sha256': nullable_sha,
        'members': {'type': 'array', 'minItems': 1, 'uniqueItems': True, 'items': member}})
    result['$schema'] = 'https://json-schema.org/draft/2020-12/schema'
    return result


def verdict(k, graph, state):
    """Derive reasons from admitted records; never ask a model to certify readiness."""
    effective = k.routed_graph(graph, state)
    if effective is None:
        raise k.Refused('package: no admitted requirement graph; admit source-bound evidence first')
    queue = effective['queue']
    requirements = [n for n in effective['graph']['nodes'] if n['type'] == 'requirement']
    settled = bool(requirements) and not queue and state.get('compilation') is not None
    settled = settled and state['pending'] is None and state['routing']['pending'] is None
    rows = []
    for node in requirements:
        record = node['record']
        satisfied = record['disposition'] == 'satisfied'
        settled = settled and satisfied
        rows.append({'requirement_id': node['id'], 'disposition': record['disposition'],
                     'maturity': record['maturity'], 'reason':
                     ('Satisfied by the retained evidence and independent assessment at the recorded maturity.'
                      if satisfied else 'The admitted requirement is not satisfied; its unresolved evidence remains blocking.')})
    readiness = 'ready' if settled else ('needs_owner' if queue and queue[0]['blocking_class'] == 'owner' else 'blocked')
    next_action = queue[0] if queue else (None if settled else {
        'action': 'complete-readiness-evidence',
        'reason': 'Complete requirement assessment and atom compilation before readiness can be granted.'})
    return effective, {'schema_version': 1, 'readiness': readiness, 'requirements': rows, 'next_action': next_action}


def preparation(k, graph, state):
    effective, answer = verdict(k, graph, state)
    prior = state.get('package')
    return {'graph_sha256': effective['graph_sha256'], 'readiness': answer['readiness'],
            'predecessor_manifest_sha256': prior['manifest_sha256'] if prior else None}


def approval(k, state, sequence_hash):
    record = state.get('atom_approval')
    if record is None:
        return 'not-approved'
    if record['atom_sequence_sha256'] != sequence_hash:
        raise k.Refused('approval sequence differs from the compiled sequence; obtain approval for the current bytes')
    if record['decision'] not in ('approved', 'rejected'):
        raise k.Refused('approval decision must be approved or rejected')
    return record['decision']


def render(k, events, request, graph, state):
    """Pure reconstruction from the verified closed prefix ending at package_prepared."""
    if not events or events[-1]['event'] != 'package_prepared':
        raise k.Refused('package ledger must end at package_prepared, before the event that hashes its manifest')
    if k.chain([(e['event'], e['payload']) for e in events]) != events:
        raise k.Refused('package prefix chain differs; use the verified closed ledger prefix')
    effective, answer = verdict(k, graph, state)
    if events[-1]['payload'] != preparation(k, graph, state):
        raise k.Refused('package preparation differs from the replayed graph or predecessor generation')
    nodes = effective['graph']['nodes']
    def document(value):
        return k.canonical(value) + b'\n'
    members = {'ledger.jsonl': b''.join(document(e) for e in events),
               'graph.json': document(effective['graph']), 'queue.json': document(effective['queue']),
               'verdict.json': document(answer)}
    for name, kind in [('requirements','requirement'), ('evidence','evidence'),
                       ('decisions','authority_decision'), ('verification','verification')]:
        members[name + '.json'] = document({'schema_version': 1, 'nodes': [n for n in nodes if n['type'] == kind]})
    compilation = state.get('compilation')
    sequence_hash = None
    if answer['readiness'] == 'ready':
        sequence_hash = compilation['sequence_sha256']
        if sequence_hash != k.digest(k.canonical(compilation['requests'])):
            raise k.Refused('package atom sequence hash differs from the compiled requests')
        members['atom-sequence.json'] = document(compilation)
        for i, row in enumerate(compilation['requests'], 1):
            identity = row['atomic_step_id']
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', identity):
                raise k.Refused('package atom identity is not a safe directory component')
            raw = document(row['request'])
            if k.digest(raw) != row['request_sha256']:
                raise k.Refused('package atom request differs from its compiled hash')
            members[f'atoms/{i:04d}-{identity}/atom-request.json'] = raw
    approval_state = approval(k, state, sequence_hash)
    if state.get('atom_approval') is not None:
        members['approval.json'] = document(state['atom_approval'])
    report = ['# Readiness', '', 'Verdict: ' + answer['readiness'], '', 'Approval: ' + approval_state.replace('-', ' '), '']
    report.extend(f"- {r['requirement_id']}: {r['disposition']} ({r['maturity']}). {r['reason']}" for r in answer['requirements'])
    if answer['next_action'] is not None:
        report += ['', 'Next action:', k.canonical(answer['next_action']).decode()]
    members['report.md'] = ('\n'.join(report) + '\n').encode()
    # A receipt binds only prior reconstructed members, never itself or the manifest.
    members['replay-receipt.json'] = document({'schema_version': 1, 'ledger_prefix_tip': events[-1]['sha256'],
        'graph_sha256': effective['graph_sha256'], 'member_hashes':
        [{'path': p, 'sha256': k.digest(raw)} for p, raw in sorted(members.items())]})
    manifest = {'schema_version': 1, 'run_sha256': events[0]['sha256'],
        'input_sha256': events[0]['payload']['request_sha256'], 'controller_sha256': events[0]['payload']['controller_sha256'],
        'ledger_prefix_tip': events[-1]['sha256'],
        'predecessor_manifest_sha256': events[-1]['payload']['predecessor_manifest_sha256'],
        'readiness': answer['readiness'], 'approval_state': approval_state, 'atom_sequence_sha256': sequence_hash,
        'members': [{'path': p, 'size': len(raw), 'sha256': k.digest(raw), 'schema_version': 1} for p, raw in sorted(members.items())]}
    k.validate_shape(manifest, package_schema(), 'package manifest')
    members['manifest.json'] = document(manifest)
    return members, manifest


def verify(k, root, expected):
    """Verify an exact reconstruction, not a manifest's claims about its own bytes."""
    root = Path(root)
    fd = k.directory(root)
    os.close(fd)
    actual = set()
    directories = {str(Path(name).parent) for name in expected}
    directories |= {str(p) for name in expected for p in Path(name).parents}
    for path in root.rglob('*'):
        name = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise k.Refused('package member is linked: ' + name)
        if path.is_dir():
            if name not in directories:
                raise k.Refused('package contains an unexpected directory: ' + name)
        else:
            actual.add(name)
    if actual != set(expected):
        raise k.Refused('package membership differs from replay; missing or extra files are forbidden')
    manifest = k.decode(k.read_file(root / 'manifest.json', 33554432), 'package manifest')
    k.validate_shape(manifest, package_schema(), 'package manifest')
    if manifest['schema_version'] != 1 or manifest['approval_state'] not in APPROVAL_VALUES or manifest['readiness'] not in READINESS_VALUES:
        raise k.Refused('package version, approval or readiness is unsupported')
    if [r['path'] for r in manifest['members']] != sorted(set(expected) - {'manifest.json'}):
        raise k.Refused('package manifest must list every other member once, never itself')
    for name, raw in expected.items():
        if k.read_file(root / name, max(len(raw), 1)) != raw:
            raise k.Refused('package member differs from closed-prefix replay: ' + name)
    return k.digest(expected['manifest.json'])


def finalize(k, base, members):
    root = base / 'package'
    if not root.exists():
        root.mkdir(mode=0o700)
    fd = k.directory(root)
    stage = root / ('.pending-' + uuid.uuid4().hex)
    identity = k.digest(members['manifest.json'])
    final = root / identity
    try:
        stage.mkdir(mode=0o700)
        for name, raw in members.items():
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(raw); stream.flush(); os.fchmod(stream.fileno(), 0o444); os.fsync(stream.fileno())
        verify(k, stage, members)
        for directory in sorted([p for p in stage.rglob('*') if p.is_dir()], reverse=True) + [stage]:
            child_fd = k.directory(directory)
            os.fsync(child_fd); os.close(child_fd)
        if final.exists():
            raise k.Refused('package generation already exists; never replace immutable generations')
        os.rename(stage, final)
        os.fsync(fd)
        return identity
    finally:
        os.close(fd)
        if stage.exists():
            shutil.rmtree(stage)


def append_event(k, work, events, kind, payload):
    event = k.chain([(e['event'], e['payload']) for e in events] + [(kind, payload)])[-1]
    if len(k.canonical(event)) + 1 > 4194304:
        raise k.Refused('transaction exceeds the 4 MiB replay limit; supply a bounded source before publication')
    base = work / 'run'; root = base / 'interviews'
    root.mkdir(exist_ok=True, mode=0o700)
    root_fd = k.directory(root)
    stage = root / ('.pending-' + uuid.uuid4().hex)
    try:
        stage.mkdir(mode=0o700)
        with (stage / 'event.json').open('xb') as stream:
            stream.write(k.canonical(event) + b'\n'); stream.flush(); os.fchmod(stream.fileno(), 0o444); os.fsync(stream.fileno())
        stage_fd = k.directory(stage); os.fsync(stage_fd); os.close(stage_fd)
        final = root / f'{len(events):08d}'
        if final.exists():
            raise k.Refused('package journal position already exists; reread the current ledger tip')
        os.rename(stage, final); os.fsync(root_fd)
        head = base / ('.head-' + uuid.uuid4().hex)
        with head.open('xb') as stream:
            stream.write(k.canonical({'ledger_tip': event['sha256'], 'event_count': len(events) + 1}) + b'\n')
            stream.flush(); os.fchmod(stream.fileno(), 0o444); os.fsync(stream.fileno())
        os.replace(head, base / 'interview-head.json')
        base_fd = k.directory(base); os.fsync(base_fd); os.close(base_fd)
        events.append(event)
        return event
    finally:
        os.close(root_fd)


def compile_package(k, work, events, request, graph, state):
    payload = preparation(k, graph, state)
    prepared = append_event(k, work, events, 'package_prepared', payload)
    try:
        members, manifest = render(k, events, request, graph, state)
        identity = finalize(k, work / 'run', members)
    except (OSError, ValueError, KeyError, TypeError) as error:
        append_event(k, work, events, 'package_failed', {'prepared_sha256': prepared['sha256'],
            'error_kind': type(error).__name__, 'error_sha256': k.digest(str(error).encode())})
        raise
    append_event(k, work, events, 'package_compiled', {'prepared_sha256': prepared['sha256'],
        'manifest_sha256': identity, 'readiness': manifest['readiness']})
    return k.replay(work, locked=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('command', choices=['schema'])
    parser.parse_args()
    print(json.dumps(package_schema(), sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
