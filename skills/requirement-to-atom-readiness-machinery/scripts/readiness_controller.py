"""Opt-in readiness contracts. Runtime capabilities are added independently."""
import argparse
import json
import re

REQUEST_FIELDS = ('schema_version', 'feature_id', 'runtime_boundary', 'model_runtime',
                  'execution_limits', 'description_handoff', 'requirements_handoff',
                  'boundaries', 'evidence_manifests', 'machinery_contracts',
                  'telemetry_manifests', 'blocker_ledgers', 'owner_records')
RUNTIME_BOUNDARY_FIELDS = ('authorized_root', 'target_repositories', 'product_edit_boundaries')
MODEL_RUNTIME_FIELDS = ('provider', 'model', 'reasoning_effort')
EXECUTION_LIMITS_FIELDS = ('max_input_files', 'max_single_file_bytes', 'max_total_input_bytes',
                         'model_timeout_ms', 'max_model_attempts_per_seat')
FILE_FIELDS = ('path', 'sha256')
CONTRACT_FIELDS = ('role', 'path', 'sha256')
PROVIDER_VALUES = ('openai-codex-cli',)
REASONING_EFFORT_VALUES = ('none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max', 'ultra')
REQUIRED_ROLES = ('working-agreement', 'description-skill', 'description-exporter-source',
                  'requirements-skill', 'requirements-controller-source', 'info-intake-skill',
                  'sequence-runner-skill', 'experiment-machinery-skill',
                  'prototype-driven-implementation-skill', 'atom-building-skill',
                  'atom-controller-source', 'blocker-catalog-source')
LIMIT_CEILINGS = (10000, 1073741824, 10737418240, 600000, 2)
SHA256 = re.compile(r'^[0-9a-f]{64}$')


def request_schema():
    """Describe shape only; this command neither admits inputs nor creates runs."""
    def obj(fields, properties):
        return {'type': 'object', 'additionalProperties': False,
                'required': list(fields), 'properties': properties}
    def array(items, minimum=0):
        return {'type': 'array', 'items': items, 'minItems': minimum, 'uniqueItems': True}
    text = {'type': 'string', 'minLength': 1, 'pattern': r'\S'}
    path = {'type': 'string', 'minLength': 1, 'pattern': '^/'}
    digest = {'$ref': '#/$defs/sha256'}
    file = obj(FILE_FIELDS, {'path': path, 'sha256': digest})
    contract = obj(CONTRACT_FIELDS, {'role': {'enum': list(REQUIRED_ROLES)},
                                     'path': path, 'sha256': digest})
    properties = {
        'schema_version': {'type': 'integer', 'const': 1}, 'feature_id': text,
        'runtime_boundary': obj(RUNTIME_BOUNDARY_FIELDS, {
            'authorized_root': path, 'target_repositories': array(path, 1),
            'product_edit_boundaries': array(path, 1)}),
        'model_runtime': obj(MODEL_RUNTIME_FIELDS, {
            'provider': {'enum': list(PROVIDER_VALUES)}, 'model': text,
            'reasoning_effort': {'enum': list(REASONING_EFFORT_VALUES)}}),
        'execution_limits': obj(EXECUTION_LIMITS_FIELDS, {
            key: {'type': 'integer', 'minimum': 1, 'maximum': ceiling}
            for key, ceiling in zip(EXECUTION_LIMITS_FIELDS, LIMIT_CEILINGS)}),
        'description_handoff': file, 'requirements_handoff': file, 'boundaries': file,
        'evidence_manifests': array(file), 'machinery_contracts': array(contract, len(REQUIRED_ROLES)),
        'telemetry_manifests': array(file), 'blocker_ledgers': array(file), 'owner_records': array(file)}
    properties['machinery_contracts']['allOf'] = [
        {'contains': {'properties': {'role': {'const': role}}, 'required': ['role']},
         'minContains': 1, 'maxContains': 1} for role in REQUIRED_ROLES]
    schema = obj(REQUEST_FIELDS, properties)
    schema.update({'$schema': 'https://json-schema.org/draft/2020-12/schema',
                   '$defs': {'sha256': {'type': 'string', 'pattern': SHA256.pattern,
                                        'minLength': 64, 'maxLength': 64}}})
    return schema


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('schema', allow_abbrev=False)
    parser.parse_args()
    print(json.dumps(request_schema(), sort_keys=True, indent=2))
    return 0



# Atom 4: durable mechanics only. Upstream semantics remain the adapters' duty.
import contextlib
import fcntl
import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import uuid
from datetime import datetime, timezone

EVENT_FIELDS = ('schema_version', 'sequence', 'event', 'previous', 'payload', 'sha256')
START_FIELDS = ('request_sha256', 'runtime', 'controller_sha256', 'recorded_at', 'upstream', 'evidence_graph', 'interview_state')
INPUT_FIELDS = ('identity', 'role', 'origin', 'sha256', 'size', 'object_path', 'imported_at')
GENESIS = '0' * 64


class Refused(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf-8')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def decode(raw, label):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise Refused(f'{label}: duplicate key {key!r}; supply each key once')
            result[key] = value
        return result
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(
                              Refused(f'{label}: {value} is not finite JSON')))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise Refused(f'{label}: malformed UTF-8 JSON: {error}') from None


def validate_shape(value, schema, label='request', root=None):
    root = schema if root is None else root
    if '$ref' in schema:
        return validate_shape(value, root['$defs'][schema['$ref'].split('/')[-1]], label, root)
    if 'anyOf' in schema:
        failures = []
        for choice in schema['anyOf']:
            try:
                return validate_shape(value, choice, label, root)
            except Refused as error:
                failures.append(str(error))
        raise Refused(f'{label}: got {value!r}; none of the declared alternatives matched: {failures}')
    kind = schema.get('type')
    matches = {'object': type(value) is dict, 'array': type(value) is list,
               'integer': type(value) is int, 'string': type(value) is str,
               'null': value is None, 'boolean': type(value) is bool}
    if kind and not matches[kind]:
        raise Refused(f'{label}: got {type(value).__name__}; expected {kind}')
    if 'const' in schema and value != schema['const']:
        raise Refused(f'{label}: got {value!r}; expected {schema["const"]!r}')
    if 'enum' in schema and value not in schema['enum']:
        raise Refused(f'{label}: got {value!r}; expected one of {schema["enum"]!r}')
    if kind == 'object':
        missing = set(schema['required']) - set(value)
        extra = set(value) - set(schema['properties'])
        if missing or extra:
            raise Refused(f'{label}: missing {sorted(missing)}, unexpected {sorted(extra)}; use exactly the declared fields')
        for key, child in schema['properties'].items():
            validate_shape(value[key], child, f'{label}.{key}', root)
    if kind == 'array':
        if len(value) > schema.get('maxItems', len(value)):
            raise Refused(f'{label}: got {len(value)} items; maximum is {schema["maxItems"]}')
        if len(value) < schema.get('minItems', 0):
            raise Refused(f'{label}: got {len(value)} items; need at least {schema["minItems"]}')
        if len({canonical(x) for x in value}) != len(value):
            raise Refused(f'{label}: duplicate items; provide unique entries')
        for index, item in enumerate(value):
            validate_shape(item, schema['items'], f'{label}[{index}]', root)
    if kind == 'string':
        if len(value) < schema.get('minLength', 0) or len(value) > schema.get('maxLength', len(value)) or ('pattern' in schema and not re.search(schema['pattern'], value)):
            raise Refused(f'{label}: {value!r} violates declared string length or pattern; use the schema format')
    if kind == 'integer' and not schema.get('minimum', value) <= value <= schema.get('maximum', value):
        raise Refused(f'{label}: got {value}; expected {schema.get("minimum")} through {schema.get("maximum")}')


def absolute(value):
    if type(value) is not str or not value.startswith('/') or str(Path(value)) != value or '..' in Path(value).parts:
        raise Refused(f'path {value!r}: provide a normalized absolute path without traversal')
    return Path(value)


def validate_request(value):
    schema = request_schema()
    if type(value) is not dict or set(value) != set(REQUEST_FIELDS):
        missing = sorted(set(REQUEST_FIELDS) - set(value)) if type(value) is dict else list(REQUEST_FIELDS)
        extra = sorted(set(value) - set(REQUEST_FIELDS)) if type(value) is dict else []
        raise Refused(f'request: missing {missing}, unexpected {extra}; provide exactly the request schema fields')
    fields = (
        ('schema_version', value['schema_version']), ('feature_id', value['feature_id']),
        ('runtime_boundary', value['runtime_boundary']), ('model_runtime', value['model_runtime']),
        ('execution_limits', value['execution_limits']), ('description_handoff', value['description_handoff']),
        ('requirements_handoff', value['requirements_handoff']), ('boundaries', value['boundaries']),
        ('evidence_manifests', value['evidence_manifests']), ('machinery_contracts', value['machinery_contracts']),
        ('telemetry_manifests', value['telemetry_manifests']), ('blocker_ledgers', value['blocker_ledgers']),
        ('owner_records', value['owner_records']))
    for name, content in fields:
        validate_shape(content, schema['properties'][name], 'request.' + name, schema)


def directory(path):
    """Open each component without following links; caller closes returned fd."""
    path = absolute(str(path))
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_file(path, limit):
    path = absolute(str(path))
    parent = directory(path.parent)
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:
                raise Refused(f'{path}: require one unlinked regular file of at most {limit} bytes')
            with os.fdopen(os.dup(fd), 'rb') as stream:
                raw = stream.read(limit + 1)
            after = os.fstat(fd)
            if len(raw) > limit or (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise Refused(f'{path}: bytes changed during reading; freeze the input and retry')
            return raw
        finally:
            os.close(fd)
    finally:
        os.close(parent)


def overlaps(a, b):
    return a == b or a in b.parents or b in a.parents


def boundaries(request, work):
    boundary = request['runtime_boundary']
    root = absolute(boundary['authorized_root'])
    if root == Path('/') or not (work == root or root in work.parents):
        raise Refused(f'{work}: must be within the explicit non-root authorized directory {root}')
    fd = directory(root)
    os.close(fd)
    targets = [absolute(p) for p in boundary['target_repositories'] + boundary['product_edit_boundaries']]
    for target in targets:
        for part in (target, *target.parents):
            if part.is_symlink():
                raise Refused(f'{target}: linked protected boundary; provide the real path')
        if overlaps(work, target):
            raise Refused(f'{work}: overlaps protected boundary {target}; choose a disjoint work directory')
    for parent in (work, *work.parents):
        if parent.name == 'Tasks' or (parent / '.git').exists() or (parent / '.git').is_symlink():
            raise Refused(f'{work}: repository or Tasks ancestry is forbidden; use an external work directory')


def descriptors(request):
    result = []
    for key in ('description_handoff', 'requirements_handoff', 'boundaries'):
        result.append((key, key, request[key]))
    for key in ('evidence_manifests', 'machinery_contracts', 'telemetry_manifests', 'blocker_ledgers', 'owner_records'):
        for index, item in enumerate(request[key]):
            result.append((f'{key}:{index}', item.get('role', key), item))
    roles = [x['role'] for x in request['machinery_contracts']]
    missing = set(REQUIRED_ROLES) - set(roles)
    if missing or len(set(roles)) != len(roles):
        raise Refused(f'machinery_contracts: missing roles {sorted(missing)} or duplicate roles; provide each required role exactly once')
    return result


def runtime_identity():
    def identity(launcher):
        path = absolute(str(Path(launcher).absolute()))
        target = path.resolve(strict=True)
        raw = read_file(target, 1073741824)
        return {'launcher': str(path), 'target': str(target), 'sha256': digest(raw)}
    python = identity(sys.executable)
    python['version'] = sys.version
    launcher = shutil.which('codex')
    if not launcher:
        raise Refused('runtime: codex is absent from PATH; install the approved CLI before starting')
    codex = identity(launcher)
    version = subprocess.run([launcher, '--version'], capture_output=True, text=True, timeout=10)
    if version.returncode or not version.stdout.strip():
        raise Refused('runtime: codex --version failed; repair the installed CLI before starting')
    codex['version'] = version.stdout.strip()
    if identity(launcher) != {k: v for k, v in codex.items() if k != 'version'}:
        raise Refused('runtime: Codex changed during identification; use a stable installation')
    return {'python': python, 'codex': codex}


def require_tip(expected, actual):
    if type(expected) is not str or not SHA256.fullmatch(expected) or expected != actual:
        raise Refused(f'expected tip {expected!r} differs from current {actual}; read status and retry with that exact tip')


def chain(records):
    previous = GENESIS
    result = []
    for kind, payload in records:
        event = {'schema_version': 1, 'sequence': len(result) + 1, 'event': kind,
                 'previous': previous, 'payload': payload}
        event['sha256'] = digest(canonical(event))
        previous = event['sha256']
        result.append(event)
    return result


def projection(events, request):
    result = {'schema_version': 1, 'feature_id': request['feature_id'],
            'status': 'initialized', 'readiness': 'not-assessed',
            'ledger_tip': events[-1]['sha256'], 'event_count': len(events),
            'request_sha256': events[0]['payload']['request_sha256'],
            'runtime': events[0]['payload']['runtime'],
            'inputs': [e['payload'] for e in events[1:]],
            'upstream': events[0]['payload']['upstream'],
            'interview_state': events[0]['payload']['interview_state']}
    graph = events[0]['payload']['evidence_graph']
    if graph is not None:
        result.update({key: graph['result'][key] for key in ('status', 'readiness', 'graph_sha256', 'next_action')})
        result['queue_count'] = len(graph['result']['queue'])
    return result


def start(request_path, work, expected_tip):
    require_tip(expected_tip, GENESIS)
    work = absolute(str(work))
    raw_request = read_file(request_path, 16777216)
    request = decode(raw_request, 'request')
    validate_request(request)
    boundaries(request, work)
    items = descriptors(request)
    limits = request['execution_limits']
    if len(items) > limits['max_input_files']:
        raise Refused(f'inputs: {len(items)} files exceed max_input_files {limits["max_input_files"]}')
    work_fd = directory(work)
    stage = '.staging-' + uuid.uuid4().hex
    created = False
    try:
        fcntl.flock(work_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if os.listdir(work_fd):
            raise Refused(f'{work}: start requires an existing empty work directory')
        captured = []
        total = 0
        for identity, role, item in items:
            path = absolute(item['path'])
            if overlaps(work, path.parent):
                raise Refused(f'{path}: source directory overlaps work; use a separate input location')
            raw = read_file(path, limits['max_single_file_bytes'])
            total += len(raw)
            if total > limits['max_total_input_bytes']:
                raise Refused(f'inputs: {total} bytes exceed max_total_input_bytes {limits["max_total_input_bytes"]}')
            if digest(raw) != item['sha256']:
                raise Refused(f'{identity}: {path} digest mismatch; supply the exact frozen bytes and hash')
            captured.append((identity, role, item, raw))
        upstream = collect_upstreams(request, captured, work, total)
        runtime = runtime_identity()
        now = datetime.now(timezone.utc).isoformat()
        graph = collect_graph(request, captured, work, upstream, now)
        request_bytes = canonical(request) + b'\n'
        records = [('run_started', {'request_sha256': digest(request_bytes), 'runtime': runtime,
                    'controller_sha256': adapter_code_sha256(), 'recorded_at': now, 'upstream': upstream, 'evidence_graph': graph,
                    'interview_state': initial_interview_state()})]
        files = {'request.json': request_bytes}
        for identity, role, item, raw in captured:
            relative = 'inputs/objects/' + item['sha256']
            files[relative] = raw
            records.append(('input_admitted', {'identity': identity, 'role': role, 'origin': item['path'],
                            'sha256': item['sha256'], 'size': len(raw), 'object_path': relative, 'imported_at': now}))
        if graph is not None:
            files['graph.json'] = canonical(graph['result']['graph']) + b'\n'
            files['queue.json'] = canonical(graph['result']['queue']) + b'\n'
        events = chain(records)
        files['ledger.jsonl'] = b''.join(canonical(e) + b'\n' for e in events)
        files['state.json'] = canonical(projection(events, request)) + b'\n'
        files['interview-head.json'] = canonical({'ledger_tip': events[-1]['sha256'], 'event_count': len(events)}) + b'\n'
        os.mkdir(stage, 0o700, dir_fd=work_fd)
        created = True
        stage_fd = os.open(stage, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=work_fd)
        try:
            os.mkdir('inputs', 0o700, dir_fd=stage_fd)
            inputs_fd = os.open('inputs', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=stage_fd)
            try:
                os.mkdir('objects', 0o700, dir_fd=inputs_fd)
                objects_fd = os.open('objects', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=inputs_fd)
                try:
                    for name, raw in files.items():
                        parent_fd = objects_fd if name.startswith('inputs/objects/') else stage_fd
                        file_fd = os.open(name.split('/')[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent_fd)
                        with os.fdopen(file_fd, 'wb') as stream:
                            stream.write(raw)
                            stream.flush()
                            os.fchmod(stream.fileno(), 0o444)
                            os.fsync(stream.fileno())
                    os.fsync(objects_fd)
                finally:
                    os.close(objects_fd)
                os.fsync(inputs_fd)
            finally:
                os.close(inputs_fd)
            os.fsync(stage_fd)
        finally:
            os.close(stage_fd)
        # Recheck the named directory and input bytes before publishing any run state.
        check_fd = directory(work)
        try:
            if os.fstat(check_fd).st_ino != os.fstat(work_fd).st_ino or os.fstat(check_fd).st_dev != os.fstat(work_fd).st_dev:
                raise Refused(f'{work}: work directory changed during start; retry from a stable location')
        finally:
            os.close(check_fd)
        for name, expected_bytes in files.items():
            if read_file(work / stage / name, len(expected_bytes)) != expected_bytes:
                raise Refused(f'{name}: staged copy differs from frozen bytes; retry on reliable storage')
        for identity, role, item, raw in captured:
            if read_file(item['path'], limits['max_single_file_bytes']) != raw:
                raise Refused(f'{identity}: source changed before publication; freeze it and retry')
        if read_file(request_path, 16777216) != raw_request or runtime_identity() != runtime:
            raise Refused('request or runtime changed before publication; freeze them and retry')
        os.rename(stage, 'run', src_dir_fd=work_fd, dst_dir_fd=work_fd)
        created = False
        os.fsync(work_fd)
        return projection(events, request)
    finally:
        if created:
            shutil.rmtree(stage, dir_fd=work_fd)
        os.close(work_fd)


def replay(work, *, locked=False):
    work = absolute(str(work))
    fd = directory(work)
    try:
        if not locked:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        if os.listdir(fd) != ['run']:
            raise Refused(f'{work}: expected exactly the published run directory; incomplete or extra state is forbidden')
        base = work / 'run'
        raw_request = read_file(base / 'request.json', 16777216)
        request = decode(raw_request, 'stored request')
        validate_request(request)
        boundaries(request, work)
        items = descriptors(request)
        if raw_request != canonical(request) + b'\n':
            raise Refused('stored request: noncanonical bytes; preserve the original snapshot')
        raw = read_file(base / 'ledger.jsonl', 33554432)
        events = [decode(line, f'ledger line {i+1}') for i, line in enumerate(raw.splitlines())]
        if not events or type(events[0]) is not dict or type(events[0].get('payload')) is not dict:
            raise Refused('ledger: missing the complete start event')
        upstream = events[0]['payload'].get('upstream')
        if type(upstream) is not dict or set(upstream) != {'members', 'description_record', 'requirements_record', 'question_source_sha256', 'runtime_sha256'} or type(upstream['members']) is not list:
            raise Refused('start event: require the exact upstream import records and member list')
        for member in upstream['members']:
            if type(member) is not dict or set(member) != {'identity', 'role', 'path', 'sha256'} or member['role'] != 'upstream-evidence':
                raise Refused('upstream member: require exact identity, role, path and hash fields')
            items.append((member['identity'], member['role'], {'path': member['path'], 'sha256': member['sha256']}))
        graph = events[0]['payload'].get('evidence_graph')
        if graph is not None:
            if type(graph) is not dict or set(graph) != {'members', 'before_sha256', 'after_sha256', 'result'} or type(graph['members']) is not list:
                raise Refused('graph admission: require exact snapshot members, before/after hashes and result')
            for member in graph['members']:
                if type(member) is not dict or set(member) != {'identity', 'role', 'path', 'sha256'} or member['role'] != 'graph-evidence':
                    raise Refused('graph member: require exact identity, role, path and hash')
                items.append((member['identity'], member['role'], {'path': member['path'], 'sha256': member['sha256']}))
        if len(events) != len(items) + 1:
            raise Refused('ledger: missing or extra input events; restore the exact complete ledger')
        records = []
        for index, event in enumerate(events):
            if type(event) is not dict or set(event) != set(EVENT_FIELDS):
                raise Refused(f'ledger event {index+1}: use exactly the closed event fields')
            kind = 'input_admitted' if index else 'run_started'
            fields = INPUT_FIELDS if index else START_FIELDS
            if event['event'] != kind or type(event['payload']) is not dict or set(event['payload']) != set(fields):
                raise Refused(f'ledger event {index+1}: expected {kind} and its exact payload fields')
            records.append((kind, event['payload']))
        expected_events = chain(records)
        if events != expected_events or raw != b''.join(canonical(e) + b'\n' for e in expected_events):
            raise Refused('ledger: sequence, predecessor, hash, or canonical bytes differ; restore the original chain')
        first = events[0]['payload']
        if first['request_sha256'] != digest(raw_request) or first['controller_sha256'] != adapter_code_sha256():
            raise Refused('run identity: request or controller bytes differ; resume with the frozen version')
        if first['runtime'] != runtime_identity():
            raise Refused('runtime identity differs from start; resume with the recorded Python and Codex installation')
        expected_files = {'request.json', 'ledger.jsonl', 'state.json', 'interview-head.json'}
        frozen = {}
        for event, (identity, role, item) in zip(events[1:], items):
            value = event['payload']
            relative = 'inputs/objects/' + item['sha256']
            data = read_file(base / relative, request['execution_limits']['max_single_file_bytes'])
            expected = {'identity': identity, 'role': role, 'origin': item['path'], 'sha256': item['sha256'],
                        'size': len(data), 'object_path': relative, 'imported_at': first['recorded_at']}
            if value != expected or digest(data) != item['sha256']:
                raise Refused(f'{identity}: snapshot or admission record differs; restore the frozen object')
            expected_files.add(relative)
            if item['path'] in frozen and frozen[item['path']] != data:
                raise Refused('stored inputs bind one origin to conflicting bytes')
            frozen[item['path']] = data
        consumed = set()
        def snapshot_read(path, expected):
            path = str(absolute(str(path)))
            if path not in frozen or digest(frozen[path]) != expected:
                raise Refused(f'{path}: missing or changed frozen upstream member')
            consumed.add(path)
            return frozen[path]
        checked = verify_upstreams(request, snapshot_read)
        if checked != {key: value for key, value in upstream.items() if key != 'members'}:
            raise Refused('upstream import projection differs from replayed evidence')
        if any(row['path'] not in consumed for row in upstream['members']):
            raise Refused('upstream import contains a foreign unused member')
        rebuilt = verify_graph(request, checked, snapshot_read, first['recorded_at'])
        if (rebuilt is None) != (graph is None):
            raise Refused('graph admission differs from the declared manifests')
        if graph is not None:
            if rebuilt != graph['result'] or graph['before_sha256'] != GENESIS or graph['after_sha256'] != rebuilt['graph_sha256']:
                raise Refused('graph admission differs from frozen evidence replay')
            if any(row['path'] not in consumed for row in graph['members']):
                raise Refused('graph admission contains an unused source member')
            for name, value in [('graph.json', rebuilt['graph']), ('queue.json', rebuilt['queue'])]:
                expected_files.add(name)
                if read_file(base / name, 33554432) != canonical(value) + b'\n':
                    raise Refused(f'{name}: projection differs from frozen graph replay')
        result = projection(events, request)
        if read_file(base / 'state.json', 33554432) != canonical(result) + b'\n':
            raise Refused('stored projection differs from ledger replay; do not trust the cached state')
        interview_state, interview_files, interview_dirs = replay_interviews(
            work, events, request, rebuilt)
        result['interview_state'] = interview_state
        result['ledger_tip'] = events[-1]['sha256']
        result['event_count'] = len(events)
        expected_files.update(interview_files)
        actual_files = set()
        expected_dirs = {'inputs', 'inputs/objects'} | interview_dirs
        for path in base.rglob('*'):
            rel = path.relative_to(base).as_posix()
            if path.is_symlink():
                raise Refused(f'{path}: linked run member is forbidden')
            if path.is_dir():
                if rel not in expected_dirs:
                    raise Refused(f'{path}: unexpected run directory')
            else:
                actual_files.add(rel)
        if actual_files != expected_files:
            raise Refused('run membership differs from admitted inputs; restore the exact run members')
        return result
    finally:
        os.close(fd)


def kernel_main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('schema', allow_abbrev=False)
    begin = commands.add_parser('start', allow_abbrev=False)
    begin.add_argument('request')
    begin.add_argument('work')
    begin.add_argument('--expected-tip', required=True)
    for name in ('status', 'verify-replay', 'advance'):
        commands.add_parser(name, allow_abbrev=False).add_argument('work')
    commands.add_parser('response-schema', allow_abbrev=False)
    for name in ('prepare-interview', 'admit-interview', 'prepare-launch', 'launch-interview'):
        command = commands.add_parser(name, allow_abbrev=False)
        command.add_argument('work')
        command.add_argument('--expected-tip', required=True)
        if name == 'admit-interview':
            command.add_argument('submission')
        if name in ('prepare-launch', 'launch-interview'):
            command.add_argument('launch_directory')
        if name == 'launch-interview':
            command.add_argument('authorization')
    args = parser.parse_args()
    try:
        if args.command == 'schema':
            print(json.dumps(request_schema(), sort_keys=True, indent=2))
            return 0
        if args.command == 'response-schema':
            print(json.dumps(model_response_schema(), sort_keys=True, indent=2))
            return 0
        if args.command in ('prepare-launch', 'launch-interview'):
            result = launcher_module().dispatch(kernel_api(), args)
        elif args.command in ('prepare-interview', 'admit-interview'):
            result = interview_action(args.command, args.work, args.expected_tip, getattr(args, 'submission', None))
        else:
            result = start(args.request, args.work, args.expected_tip) if args.command == 'start' else replay(args.work)
        print(canonical(result).decode('utf-8'))
        return 0
    except (Refused, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, RuntimeError) as error:
        print(f'refused: {error}', file=sys.stderr)
        return 2


def upstream_modules():
    """Load only installed local code, never executable bytes named by an input manifest."""
    import importlib.util
    root = Path(__file__).resolve().parents[2]
    files = {'description-exporter': root / 'description-machinery/scripts/export_handoff.py',
             'description-questions': root / 'description-machinery/from_intent.py',
             'requirements-exporter': root / 'requirements-machinery/scripts/cover.py'}
    runtime = {p.name: read_file(p, 33554432) for p in sorted(files['requirements-exporter'].parent.glob('*.py'))}
    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        exec(compile(read_file(path, 33554432), str(path), 'exec'), module.__dict__)
        return module
    return (files, runtime, load('readiness_description_exporter', files['description-exporter']),
            load('readiness_requirements_exporter', files['requirements-exporter']),
            load('readiness_description_adapter', Path(__file__).parent / 'description_adapter.py'),
            load('readiness_requirements_adapter', Path(__file__).parent / 'requirements_adapter.py'))


def verify_upstreams(request, read):
    try:
        return _verify_upstreams(request, read)
    except Exception as error:
        raise Refused(f'upstream verification refused ({type(error).__name__}): {error}') from error


def _verify_upstreams(request, read):
    files, runtime, description_exporter, requirements_exporter, description_adapter, requirements_adapter = upstream_modules()
    contracts = {row['role']: row for row in request['machinery_contracts']}
    for role, local in [('description-exporter-source', files['description-exporter']),
                        ('requirements-controller-source', files['requirements-exporter'])]:
        declared = contracts[role]
        original = read(Path(declared['path']), declared['sha256'])
        installed = read_file(local, 33554432)
        if original != installed:
            raise Refused(f'{role}: request source differs from the installed trusted exporter; use its exact version')
    description = decode(read(Path(request['description_handoff']['path']), request['description_handoff']['sha256']), 'Description handoff')
    requirements = decode(read(Path(request['requirements_handoff']['path']), request['requirements_handoff']['sha256']), 'Requirements handoff')
    if type(description) is not dict or type(requirements) is not dict:
        raise Refused('upstream handoffs must be sealed JSON objects, not loose text or arrays')
    if description.get('exporter_source_sha256') != contracts['description-exporter-source']['sha256']:
        raise Refused('Description handoff exporter identity differs from the declared contract source')
    question_bytes = read_file(files['description-questions'], 33554432)
    question_hash = digest(question_bytes)
    read(files['description-questions'], question_hash)
    description_record = description_adapter.verify(description, read, description_exporter, question_bytes)
    requirements_record = requirements_adapter.verify(requirements, read, requirements_exporter, runtime)
    if requirements['source']['sha256'] != description['description']['sha256']:
        raise Refused('Requirements source differs from the sealed Description output; use the matching upstream pair')
    return {'description_record': description_record, 'requirements_record': requirements_record,
            'question_source_sha256': question_hash,
            'runtime_sha256': digest(canonical([{'path': name, 'sha256': digest(raw)} for name, raw in sorted(runtime.items())]))}


def collect_upstreams(request, captured, work, total):
    known = {str(item['path']): raw for _, _, item, raw in captured}
    members = []
    limits = request['execution_limits']
    def read(path, expected):
        nonlocal total
        path = absolute(str(path))
        if path not in (Path(p) for p in known):
            if overlaps(work, path.parent):
                raise Refused(f'{path}: upstream evidence overlaps work; choose disjoint source storage')
            raw = read_file(path, limits['max_single_file_bytes'])
            if digest(raw) != expected:
                raise Refused(f'{path}: upstream member digest differs; restore its exact sealed bytes')
            total += len(raw)
            if len(captured) + 1 > limits['max_input_files'] or total > limits['max_total_input_bytes']:
                raise Refused('upstream evidence exceeds the explicit file or total-byte limit; raise the authorized limit or reduce inputs')
            identity = f'upstream-member-{len(members)+1:04d}'
            item = {'path': str(path), 'sha256': expected}
            members.append({'identity': identity, 'role': 'upstream-evidence', **item})
            captured.append((identity, 'upstream-evidence', item, raw))
            known[str(path)] = raw
        raw = known[str(path)]
        if digest(raw) != expected:
            raise Refused(f'{path}: conflicting sealed identities for one upstream file')
        return raw
    records = verify_upstreams(request, read)
    return {'members': members, **records}


def adapter_code_sha256():
    return digest(canonical([{'path': name, 'sha256': digest(read_file(Path(__file__).parent / name, 33554432))}
                             for name in ('readiness_controller.py', 'description_adapter.py', 'requirements_adapter.py', 'evidence_adapter.py', 'model_interview.py')]))


def launcher_module():
    import importlib.util
    path = Path(__file__).parent / 'model_interview.py'
    spec = importlib.util.spec_from_file_location('readiness_model_interview', path)
    module = importlib.util.module_from_spec(spec)
    exec(compile(read_file(path, 33554432), str(path), 'exec'), module.__dict__)
    return module


def kernel_api():
    from types import SimpleNamespace
    return SimpleNamespace(**globals())


def evidence_module():
    import importlib.util
    path = Path(__file__).parent / 'evidence_adapter.py'
    spec = importlib.util.spec_from_file_location('readiness_evidence_adapter', path)
    module = importlib.util.module_from_spec(spec)
    exec(compile(read_file(path, 33554432), str(path), 'exec'), module.__dict__)
    return module


def verify_graph(request, upstream, read, now):
    manifests = []
    for field, kind in [('evidence_manifests', 'evidence'), ('telemetry_manifests', 'telemetry'), ('blocker_ledgers', 'blockers')]:
        for item in request[field]:
            manifest = decode(read(Path(item['path']), item['sha256']), field)
            if type(manifest) is not dict or manifest.get('kind') != kind:
                raise Refused(f'{field}: expected an explicit {kind} manifest, not raw data')
            manifests.append(manifest)
    if not manifests:
        return None
    handoff = decode(read(Path(request['requirements_handoff']['path']), request['requirements_handoff']['sha256']), 'Requirements handoff')
    requirements = {**upstream['requirements_record'],
                    'current_document_sha256': handoff['requirements_document']['sha256']}
    parser = canonical_blocker_parser(request, read) if request['blocker_ledgers'] else None
    try:
        return evidence_module().build_graph(manifests, requirements, read, now, parser)
    except Exception as error:
        raise Refused(f'evidence admission: {error}; correct the named record against its source contract') from error


def canonical_blocker_parser(request, read):
    import importlib
    import types
    root = Path(__file__).resolve().parents[3] / 'scripts'
    names = ('blocker_catalog.py', 'work_memory.py', 'sequence_candidate_contract.py', 'prevention_registry.py', 'prevention_adapters.py', 'prevention_contract.py')
    declared = next(row for row in request['machinery_contracts'] if row['role'] == 'blocker-catalog-source')
    if read(Path(declared['path']), declared['sha256']) != read_file(root / names[0], 33554432):
        raise Refused('blocker contract differs from the installed canonical validator; declare its current source')
    for name in names:
        raw = read_file(root / name, 33554432)
        if read(root / name, digest(raw)) != raw:
            raise Refused(f'{name}: blocker runtime differs from captured source')
    saved = {name: module for name, module in sys.modules.items() if name == 'scripts' or name.startswith('scripts.')}
    for name in saved:
        del sys.modules[name]
    package = types.ModuleType('scripts')
    package.__path__ = [str(root)]
    sys.modules['scripts'] = package
    try:
        module = importlib.import_module('scripts.work_memory')
        if Path(module.__file__).resolve() != (root / 'work_memory.py').resolve():
            raise Refused('blocker validator loaded outside the installed source boundary')
        return module.parse_ledger_bytes
    finally:
        for name in list(sys.modules):
            if name == 'scripts' or name.startswith('scripts.'):
                del sys.modules[name]
        sys.modules.update(saved)


def collect_graph(request, captured, work, upstream, now):
    known = {str(item['path']): raw for _, _, item, raw in captured}
    members = []
    limits = request['execution_limits']
    total = sum(len(raw) for _, _, _, raw in captured)
    def read(path, expected):
        nonlocal total
        path = absolute(str(path))
        if str(path) not in known:
            if overlaps(work, path.parent):
                raise Refused(f'{path}: graph source overlaps work; freeze it in disjoint storage')
            raw = read_file(path, limits['max_single_file_bytes'])
            if digest(raw) != expected:
                raise Refused(f'{path}: graph source digest mismatch; restore exact declared bytes')
            total += len(raw)
            if len(captured) + 1 > limits['max_input_files'] or total > limits['max_total_input_bytes']:
                raise Refused('graph evidence exceeds the declared input count or byte limit')
            identity = f'graph-member-{len(members)+1:04d}'
            item = {'path': str(path), 'sha256': expected}
            members.append({'identity': identity, 'role': 'graph-evidence', **item})
            captured.append((identity, 'graph-evidence', item, raw))
            known[str(path)] = raw
        if digest(known[str(path)]) != expected:
            raise Refused(f'{path}: conflicting graph source identity')
        return known[str(path)]
    result = verify_graph(request, upstream, read, now)
    if result is None:
        return None
    return {'members': members, 'before_sha256': GENESIS,
            'after_sha256': result['graph_sha256'], 'result': result}

# Interview engine v1. Submissions are judgments, never launcher or owner authorization.
import base64

FAMILY_VERDICTS = {
    'evidence-bearing': ('supports', 'refutes', 'irrelevant', 'cannot_assess'),
    'evidence-sufficiency': ('satisfied', 'insufficient', 'contradictory', 'cannot_assess'),
    'dependency-discovery': ('dependency', 'none', 'cannot_assess'),
    'contradiction-assessment': ('compatible', 'conflict', 'cannot_assess'),
    'verification-adequacy': ('adequate', 'inadequate', 'cannot_assess'),
    'atom-cohesion': ('cohesive', 'must_split', 'cannot_assess'),
    'owner-question-formulation': ('formulated',),
}
INTERVIEW_QUESTIONS = {
    'evidence-bearing': 'Does this exact evidence item support, refute, or not bear on this exact requirement claim?',
    'evidence-sufficiency': 'Does the admitted evidence establish every listed criterion of this requirement at its declared maturity?',
    'dependency-discovery': 'Which one listed dependency must hold before this requirement can be tested independently, or are there no more?',
    'contradiction-assessment': 'Can these two registered requirement claims both hold in one implementation?',
    'verification-adequacy': 'Would the listed observable and rejection criteria prove the practical outcome without trusting the producer conclusion?',
    'atom-cohesion': 'Does this proposed atom express one independently testable outcome with complete prerequisites and no hidden second behavior?',
    'owner-question-formulation': 'What one practical question requests this owner decision using exactly the complete declared answer type and choices?',
}
PROPOSED_FACTS = {
    family: {verdict: family + ':' + verdict for verdict in verdicts if verdict != 'cannot_assess'}
    for family, verdicts in FAMILY_VERDICTS.items()
}
FORBIDDEN_JUDGMENTS = ('owner authority', 'requirements creation', 'scope expansion',
                       'legal or commercial policy approval', 'model sharing authorization',
                       'implementation approval', 'execution', 'readiness certification')
INTERVIEW_LIMIT = 1048576


def initial_interview_state():
    return {'schema_version': 1, 'pending': None, 'attempts': {}, 'proposals': [],
            'rejections': [], 'status': 'idle', 'launches': [], 'launch_results': []}


def family_response_schema(family):
    if family not in FAMILY_VERDICTS:
        raise Refused(f'family {family!r}: select one of {tuple(FAMILY_VERDICTS)}')
    def obj(properties):
        return {'type': 'object', 'additionalProperties': False,
                'required': list(properties), 'properties': properties}
    text = {'type': 'string', 'minLength': 1, 'maxLength': 8192, 'pattern': r'\S'}
    ids = {'type': 'array', 'items': text, 'uniqueItems': True, 'minItems': 1, 'maxItems': 256}
    fields = {
        'schema_version': {'type': 'integer', 'const': 1},
        'run_id': {'type': 'string', 'pattern': SHA256.pattern},
        'node_id': text, 'family': {'type': 'string', 'const': family},
        'attempt': {'type': 'integer', 'minimum': 1, 'maximum': 2},
        'seat': {'type': 'string', 'enum': ['seat-1', 'seat-2']},
        'envelope_sha256': {'type': 'string', 'pattern': SHA256.pattern},
        'verdict': {'type': 'string', 'enum': list(FAMILY_VERDICTS[family])},
        'evidence_ids': ids,
        'quotes': {'type': 'array', 'minItems': 1, 'maxItems': 256, 'uniqueItems': True,
                   'items': obj({'evidence_id': text, 'quote': text})},
        'reason': text,
    }
    if family in ('evidence-sufficiency', 'verification-adequacy'):
        fields['criteria'] = {'type': 'array', 'minItems': 1, 'maxItems': 256, 'items': obj({
            'criterion_id': text, 'verdict': {'type': 'string', 'enum': ['satisfied', 'unsatisfied', 'cannot_assess']},
            'evidence_ids': ids, 'reason': text})}
    if family == 'dependency-discovery':
        fields['dependency_id'] = {'anyOf': [text, {'type': 'null'}]}
        fields['relation'] = {'type': 'string', 'enum': ['requires', 'none']}
    if family == 'atom-cohesion':
        fields['requirement_ids'] = ids
    if family == 'owner-question-formulation':
        fields.update({'question': {**text, 'maxLength': 500},
                       'answer_type': {'type': 'string', 'enum': ['enum-choice', 'free-text']},
                       'choices': {'type': 'array', 'maxItems': 256, 'uniqueItems': True,
                                   'items': obj({'choice_id': text, 'label': text})}})
    # JSON round-trip removes every shared schema-field alias before specialization.
    return decode(canonical(obj(fields)), 'response schema')


def model_response_schema():
    return {'$schema': 'https://json-schema.org/draft/2020-12/schema',
            'title': 'Readiness model response v1; preparation further binds exact identities',
            'oneOf': [family_response_schema(family) for family in FAMILY_VERDICTS]}


def prepare_payload(work, events, request, graph, state):
    if state['pending'] is not None:
        raise Refused('interview already prepared: submit against the retained seat envelopes; do not prepare duplicate calls')
    if graph is None or not graph['queue']:
        raise Refused('queue has no pending semantic obligation; admit explicit evidence and a family-bound condition first')
    item = graph['queue'][0]
    node = next(n for n in graph['graph']['nodes'] if n['id'] == item['node_id'])
    spec = node['record'].get('interview')
    if item['blocking_class'] not in ('semantic', 'owner') or spec is None:
        raise Refused(f"queue head {item['condition_id']}: no eligible explicit interview contract; resolve the head or admit its family, criteria and evidence references")
    node_id = node['id']; family = spec['family']
    prior = [fact for fact in state['proposals'] if fact['node_id'] == node_id]
    if prior and (family != 'dependency-discovery' or any(f['verdict'] == 'none' for f in prior)):
        raise Refused(f'node {node_id}: its semantic fact was already proposed; the phase router must consume it, not interview it again')
    previous_dependencies = [fact['dependency_id'] for fact in prior]
    attempt_key = node_id + ':' + str(len(prior))
    attempt = state['attempts'].get(attempt_key, 0) + 1
    if attempt > request['execution_limits']['max_model_attempts_per_seat']:
        raise Refused(f'node {node_id}: declared attempt budget exhausted; requires a new explicit recovery decision, not another call')
    evidence_nodes = {n['record']['evidence']['evidence_id']: n['record'] for n in graph['graph']['nodes'] if n['type'] == 'evidence'}
    evidence = []
    for ref in spec['evidence_refs']:
        record = evidence_nodes[ref['evidence_id']]
        if not record['fitness']['fit']:
            raise Refused(f"evidence {ref['evidence_id']}: failed mechanical fitness; recapture it before preparing a semantic judgment")
        evidence.append({**record['evidence'], 'excerpt': ref['quote'], 'fitness': record['fitness']})
    semantic = {'family': family, 'question': INTERVIEW_QUESTIONS[family],
                'required_maturity': spec['required_maturity'],
                'subjects': [n for n in graph['graph']['nodes'] if n['id'] in spec['subject_ids']],
                'evidence': evidence, 'criteria': spec['criteria'],
                'dependency_ids': [i for i in spec['dependency_ids'] if i not in previous_dependencies],
                'choices': spec['choices'], 'answer_type': spec['answer_type'], 'candidate': spec['candidate'],
                'allowed_verdicts': list(FAMILY_VERDICTS[family]), 'forbidden_judgments': list(FORBIDDEN_JUDGMENTS)}
    seats = ('seat-1',) if family == 'owner-question-formulation' else ('seat-1', 'seat-2')
    run_id = events[0]['sha256']; prefix = f'interviews/{len(events):08d}'
    envelopes = []
    for seat in seats:
        envelope = {'schema_version': 1, 'run_id': run_id, 'node_id': node_id,
                    'family': family, 'attempt': attempt, 'seat': seat,
                    'semantic_payload': semantic, 'semantic_payload_sha256': digest(canonical(semantic)),
                    'predecessor_sha256': events[-1]['sha256'], 'launcher': events[0]['payload']['runtime']['codex'],
                    'model_runtime': request['model_runtime'],
                    'timeout_ms': request['execution_limits']['model_timeout_ms'],
                    'response_path': str(work / 'run' / prefix / (seat + '-response.json')),
                    'authorization': 'not-granted; preparation and submitted responses do not authorize a launch'}
        envelope['envelope_sha256'] = digest(canonical(envelope))
        schema = family_response_schema(family)
        for key in ('run_id', 'node_id', 'family', 'attempt', 'seat', 'envelope_sha256'):
            schema['properties'][key]['const'] = envelope[key]
        schema['properties']['evidence_ids']['items']['enum'] = [r['evidence_id'] for r in spec['evidence_refs']]
        if 'criteria' in schema['properties']:
            schema['properties']['criteria']['items']['properties']['criterion_id']['enum'] = [c['criterion_id'] for c in spec['criteria']]
        envelopes.append({'envelope': envelope, 'response_schema': schema})
    return {'node_id': node_id, 'family': family, 'attempt': attempt, 'attempt_key': attempt_key, 'envelopes': envelopes}


def evaluate_submission(pending, raw, graph, proposals=()):
    """Derive one finite proposed fact; free text never controls state or authority."""
    try:
        if pending is None:
            raise Refused('no pending interview: duplicate, foreign or exhausted submission retained without semantic advancement; inspect current status')
        rows = decode(raw, 'seat response submission')
        if type(rows) is not list or len(rows) != len(pending['envelopes']):
            raise Refused(f"seat response submission: expected exactly {len(pending['envelopes'])} ordered seat objects, got {type(rows).__name__} with {len(rows) if isinstance(rows, (list, dict)) else 'unknown'} entries")
        spec = pending['envelopes'][0]['envelope']['semantic_payload']
        evidence_ids = [e['evidence_id'] for e in spec['evidence']]
        expected_quotes = {e['evidence_id']: e['excerpt'] for e in spec['evidence']}
        criterion_ids = [c['criterion_id'] for c in spec['criteria']]
        comparable = []
        for row, seat in zip(rows, pending['envelopes']):
            validate_shape(row, seat['response_schema'], 'response.' + seat['envelope']['seat'])
            if set(row['evidence_ids']) != set(evidence_ids):
                raise Refused(f"{row['seat']}: incomplete evidence_ids {row['evidence_ids']!r}; provide exactly {evidence_ids!r}")
            if len(row['quotes']) != len(expected_quotes) or {r['evidence_id']: r['quote'] for r in row['quotes']} != expected_quotes:
                raise Refused(f"{row['seat']}: unsupported or incomplete quotes; copy each exact evidence excerpt from its envelope once")
            verdict = row['verdict']; family = row['family']
            if verdict == 'cannot_assess':
                raise Refused(f"{row['seat']}: cannot_assess is not a supported fact; retain the gap and supply missing evidence")
            key = {'verdict': verdict}
            if 'criteria' in row:
                criteria = row['criteria']
                if [c['criterion_id'] for c in criteria] != criterion_ids:
                    raise Refused(f"{row['seat']}: criterion coverage/order differs; answer exactly {criterion_ids!r}")
                for criterion in criteria:
                    if not set(criterion['evidence_ids']) <= set(evidence_ids):
                        raise Refused(f"criterion {criterion['criterion_id']}: foreign evidence_ids; use only {evidence_ids!r}")
                    if criterion['verdict'] == 'cannot_assess':
                        raise Refused(f"criterion {criterion['criterion_id']}: cannot_assess leaves this obligation unresolved")
                satisfied = all(c['verdict'] == 'satisfied' for c in criteria)
                if (verdict in ('adequate', 'satisfied')) != satisfied:
                    raise Refused(f"{row['seat']}: verdict {verdict} contradicts its criterion outcomes; positive verdict requires all criteria satisfied")
                key['criteria'] = [{k: c[k] for k in ('criterion_id', 'verdict', 'evidence_ids')} for c in criteria]
            if family == 'dependency-discovery':
                selected = row['dependency_id']
                if verdict == 'dependency':
                    if selected not in spec['dependency_ids'] or row['relation'] != 'requires':
                        raise Refused(f"{row['seat']}: dependency {selected!r} is foreign or repeated; choose one of {spec['dependency_ids']!r} with requires")
                    subject = spec['subjects'][0]['id']
                    targets = {q['condition_id']: q['node_id'] for q in graph['queue']}
                    proposed = {'type': 'requires', 'source': subject, 'target': targets.get(selected, selected)}
                    prior_edges = [{'type': 'requires', 'source': fact['subject_id'], 'target': targets.get(fact['dependency_id'], fact['dependency_id'])} for fact in proposals if fact['family'] == 'dependency-discovery' and fact['verdict'] == 'dependency']
                    evidence_module().verify_edges(graph['graph']['nodes'], graph['graph']['edges'] + prior_edges + [proposed])
                elif selected is not None or row['relation'] != 'none':
                    raise Refused(f"{row['seat']}: none requires null dependency_id and relation none")
                key.update(dependency_id=selected, relation=row['relation'], subject_id=spec['subjects'][0]['id'])
            if family == 'atom-cohesion' and set(row['requirement_ids']) != {n['id'] for n in spec['subjects']}:
                raise Refused(f"{row['seat']}: atom requirement_ids differ; return the complete code-listed set")
            if family == 'owner-question-formulation':
                if row['answer_type'] != spec['answer_type'] or row['choices'] != spec['choices']:
                    raise Refused('owner formulation changes the answer contract; preserve its exact type and complete ordered choices')
                if row['question'].count('?') != 1 or not row['question'].endswith('?') or '\n' in row['question']:
                    raise Refused('owner formulation must be one line ending in exactly one question mark; no additional instructions')
                key.update(question=row['question'], answer_type=row['answer_type'], choices=row['choices'])
            comparable.append(key)
        if any(row != comparable[0] for row in comparable[1:]):
            raise Refused('blind seats disagree on verdict or structured criterion/dependency facts; no fact admitted, retain both responses')
        return {'status': 'admitted', 'fact': {'node_id': pending['node_id'], 'family': pending['family'],
                'attempt': pending['attempt'], 'fact_type': PROPOSED_FACTS[pending['family']][rows[0]['verdict']],
                'evidence_ids': evidence_ids, 'subject_ids': [n['id'] for n in spec['subjects']],
                'authority': 'proposed-only', **comparable[0]}, 'rejection': None}
    except (ValueError, KeyError, TypeError) as error:
        return {'status': 'rejected', 'fact': None, 'rejection': str(error)}


def fold_interview(state, event, work, events, request, graph):
    state = decode(canonical(state), 'interview state')
    kind = event['event']; payload = event['payload']
    if kind == 'interview_prepared':
        expected = prepare_payload(work, events, request, graph, state)
        if payload != expected:
            raise Refused('interview preparation differs from the replayed queue, evidence or identities; restore its immutable event')
        state['pending'] = payload
        state['attempts'][payload['attempt_key']] = payload['attempt']
        state['status'] = 'awaiting-responses'
    elif kind == 'interview_launch_reserved':
        if payload['plan']['work'] != str(work) or payload['plan']['ledger_tip'] != events[-1]['sha256']:
            raise Refused('launch reservation work or predecessor differs from the current run; regenerate its exact plan')
        launcher_module().validate_reservation(kernel_api(), payload, state)
        state['launches'].append(payload)
    elif kind == 'interview_launch_finished':
        launcher_module().validate_finish(kernel_api(), payload, state)
        state['launch_results'].append(payload)
    elif kind in ('interview_admitted', 'interview_rejected'):
        if type(payload) is not dict or set(payload) != {'submission_base64', 'submission_sha256', 'result'}:
            raise Refused('interview admission has no prepared seat set or has unexpected payload fields; preserve the ordered transition chain')
        raw = base64.b64decode(payload['submission_base64'], validate=True)
        if len(raw) > INTERVIEW_LIMIT or digest(raw) != payload['submission_sha256']:
            raise Refused('interview submission bytes exceed the limit or differ from their retained digest')
        result = evaluate_submission(state['pending'], raw, graph, state['proposals'])
        if payload['result'] != result or kind != 'interview_' + result['status']:
            raise Refused('interview result differs from independent replay validation of retained response bytes')
        if result['status'] == 'admitted':
            state['proposals'].append(result['fact']); state['status'] = 'proposal-pending'
        else:
            state['rejections'].append({'node_id': state['pending']['node_id'] if state['pending'] else None, 'attempt': state['pending']['attempt'] if state['pending'] else None,
                                        'submission_sha256': payload['submission_sha256'], 'reason': result['rejection']})
            state['status'] = 'blocked'
        state['pending'] = None
    else:
        raise Refused(f'interview event {kind!r}: expected prepared, admitted or rejected')
    return state


def transition_files(event):
    files = {'event.json': canonical(event) + b'\n'}
    if event['event'] == 'interview_prepared':
        for seat in event['payload']['envelopes']:
            name = seat['envelope']['seat']
            files[name + '-envelope.json'] = canonical(seat['envelope']) + b'\n'
            files[name + '-schema.json'] = canonical(seat['response_schema']) + b'\n'
    if event['event'] == 'interview_launch_finished':
        for seat in event['payload']['seats']:
            for name, encoded in seat['files'].items():
                files[seat['seat'] + '--' + name] = base64.b64decode(encoded, validate=True)
    return files


def replay_interviews(work, events, request, graph):
    state = events[0]['payload']['interview_state']
    if canonical(state) != canonical(initial_interview_state()):
        raise Refused('initial interview_state differs from the empty version-one state')
    expected_files = set(); expected_dirs = {'interviews'}
    root = work / 'run/interviews'
    if root.is_symlink():
        raise Refused('interviews directory is linked; restore the run-owned regular directory')
    if root.exists():
        paths = sorted(root.iterdir())
        if len(paths) > 1024:
            raise Refused('interview history exceeds 1024 transitions; obtain an explicit bounded continuation')
        for path in paths:
            name = f'{len(events):08d}'
            if path.name != name or path.is_symlink() or not path.is_dir():
                raise Refused(f'interview transaction {path.name!r}: expected unlinked directory {name}; restore the complete ordered history')
            raw = read_file(path / 'event.json', 4194304)
            event = decode(raw, 'interview event')
            if type(event) is not dict or set(event) != set(EVENT_FIELDS):
                raise Refused('interview event must contain exactly the closed ledger fields')
            expected = chain([(e['event'], e['payload']) for e in events] + [(event['event'], event['payload'])])[-1]
            if raw != canonical(expected) + b'\n':
                raise Refused('interview ledger predecessor, sequence or hash differs; restore its chain')
            state = fold_interview(state, event, work, events, request, graph)
            for file, data in transition_files(event).items():
                if read_file(path / file, 4194304) != data:
                    raise Refused(f'{path.name}/{file}: bytes differ from the replayed interview')
                expected_files.add('interviews/' + name + '/' + file)
            expected_dirs.add('interviews/' + name)
            events.append(event)
    expected_head = canonical({'ledger_tip': events[-1]['sha256'], 'event_count': len(events)}) + b'\n'
    if read_file(work / 'run/interview-head.json', 4096) != expected_head:
        raise Refused('interview head differs from the complete event history; restore the missing tail or interrupted publication before resuming')
    return state, expected_files, expected_dirs


def interview_action(command, work, expected_tip, submission=None):
    work = absolute(str(work)); fd = directory(work)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = replay(work, locked=True)
        require_tip(expected_tip, result['ledger_tip'])
        base = work / 'run'
        request = decode(read_file(base / 'request.json', 16777216), 'stored request')
        events = [decode(line, 'ledger') for line in read_file(base / 'ledger.jsonl', 33554432).splitlines()]
        graph = events[0]['payload']['evidence_graph']
        graph = graph['result'] if graph is not None else None
        state, _, _ = replay_interviews(work, events, request, graph)
        if len(events) - len(result['inputs']) - 1 >= 1024:
            raise Refused('interview transition budget exhausted; obtain an explicit bounded continuation')
        if command == 'prepare-interview':
            payload = prepare_payload(work, events, request, graph, state); kind = 'interview_prepared'
        elif command == 'reserve-interview-launch':
            payload = decode(read_file(submission, INTERVIEW_LIMIT), 'launch reservation')
            launcher_module().validate_reservation(kernel_api(), payload, state)
            kind = 'interview_launch_reserved'
        elif command == 'finish-interview-launch':
            payload = decode(read_file(submission, 3145728), 'launch completion')
            launcher_module().validate_finish(kernel_api(), payload, state)
            kind = 'interview_launch_finished'
        else:
            raw = read_file(submission, INTERVIEW_LIMIT)
            assessment = evaluate_submission(state['pending'], raw, graph, state['proposals'])
            payload = {'submission_base64': base64.b64encode(raw).decode('ascii'),
                       'submission_sha256': digest(raw), 'result': assessment}
            kind = 'interview_' + assessment['status']
        event = chain([(e['event'], e['payload']) for e in events] + [(kind, payload)])[-1]
        if len(canonical(event)) + 1 > 4194304:
            raise Refused('interview transaction exceeds 4 MiB; narrow the explicit semantic obligation before publication')
        fold_interview(state, event, work, events, request, graph)
        root = base / 'interviews'
        if not root.exists():
            root.mkdir(mode=0o700)
        root_fd = directory(root); stage = '.pending-' + uuid.uuid4().hex
        try:
            os.mkdir(stage, 0o700, dir_fd=root_fd)
            stage_fd = os.open(stage, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
            try:
                for name, raw in transition_files(event).items():
                    file_fd = os.open(name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=stage_fd)
                    with os.fdopen(file_fd, 'wb') as stream:
                        stream.write(raw); stream.flush(); os.fchmod(stream.fileno(), 0o444); os.fsync(stream.fileno())
                os.fsync(stage_fd)
            finally:
                os.close(stage_fd)
            # No old bytes are replaced. Incomplete publication remains visibly refused on replay.
            check = directory(work)
            try:
                if (os.fstat(check).st_dev, os.fstat(check).st_ino) != (os.fstat(fd).st_dev, os.fstat(fd).st_ino):
                    raise Refused('work directory changed before interview publication; restore its original boundary')
            finally:
                os.close(check)
            os.rename(stage, f'{len(events):08d}', src_dir_fd=root_fd, dst_dir_fd=root_fd)
            os.fsync(root_fd)
            base_fd = directory(base)
            try:
                head_name = '.head-' + uuid.uuid4().hex
                head_fd = os.open(head_name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=base_fd)
                with os.fdopen(head_fd, 'wb') as stream:
                    stream.write(canonical({'ledger_tip': event['sha256'], 'event_count': len(events) + 1}) + b'\n')
                    stream.flush(); os.fchmod(stream.fileno(), 0o444); os.fsync(stream.fileno())
                os.rename(head_name, 'interview-head.json', src_dir_fd=base_fd, dst_dir_fd=base_fd)
                os.fsync(base_fd)
            finally:
                os.close(base_fd)
        finally:
            os.close(root_fd)
        return replay(work, locked=True)
    finally:
        os.close(fd)


if __name__ == '__main__':
    raise SystemExit(kernel_main())
