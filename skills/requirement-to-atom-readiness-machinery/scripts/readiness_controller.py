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
START_FIELDS = ('request_sha256', 'runtime', 'controller_sha256', 'recorded_at')
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
    kind = schema.get('type')
    matches = {'object': type(value) is dict, 'array': type(value) is list,
               'integer': type(value) is int, 'string': type(value) is str}
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
    return {'schema_version': 1, 'feature_id': request['feature_id'],
            'status': 'initialized', 'readiness': 'not-assessed',
            'ledger_tip': events[-1]['sha256'], 'event_count': len(events),
            'request_sha256': events[0]['payload']['request_sha256'],
            'runtime': events[0]['payload']['runtime'],
            'inputs': [e['payload'] for e in events[1:]]}


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
        runtime = runtime_identity()
        now = datetime.now(timezone.utc).isoformat()
        request_bytes = canonical(request) + b'\n'
        records = [('run_started', {'request_sha256': digest(request_bytes), 'runtime': runtime,
                    'controller_sha256': digest(Path(__file__).read_bytes()), 'recorded_at': now})]
        files = {'request.json': request_bytes}
        for identity, role, item, raw in captured:
            relative = 'inputs/objects/' + item['sha256']
            files[relative] = raw
            records.append(('input_admitted', {'identity': identity, 'role': role, 'origin': item['path'],
                            'sha256': item['sha256'], 'size': len(raw), 'object_path': relative, 'imported_at': now}))
        events = chain(records)
        files['ledger.jsonl'] = b''.join(canonical(e) + b'\n' for e in events)
        files['state.json'] = canonical(projection(events, request)) + b'\n'
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


def replay(work):
    work = absolute(str(work))
    fd = directory(work)
    try:
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
        if first['request_sha256'] != digest(raw_request) or first['controller_sha256'] != digest(Path(__file__).read_bytes()):
            raise Refused('run identity: request or controller bytes differ; resume with the frozen version')
        if first['runtime'] != runtime_identity():
            raise Refused('runtime identity differs from start; resume with the recorded Python and Codex installation')
        expected_files = {'request.json', 'ledger.jsonl', 'state.json'}
        for event, (identity, role, item) in zip(events[1:], items):
            value = event['payload']
            relative = 'inputs/objects/' + item['sha256']
            data = read_file(base / relative, request['execution_limits']['max_single_file_bytes'])
            expected = {'identity': identity, 'role': role, 'origin': item['path'], 'sha256': item['sha256'],
                        'size': len(data), 'object_path': relative, 'imported_at': first['recorded_at']}
            if value != expected or digest(data) != item['sha256']:
                raise Refused(f'{identity}: snapshot or admission record differs; restore the frozen object')
            expected_files.add(relative)
        actual_files = set()
        expected_dirs = {'inputs', 'inputs/objects'}
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
        result = projection(events, request)
        if read_file(base / 'state.json', 33554432) != canonical(result) + b'\n':
            raise Refused('stored projection differs from ledger replay; do not trust the cached state')
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
    for name in ('status', 'verify-replay'):
        commands.add_parser(name, allow_abbrev=False).add_argument('work')
    args = parser.parse_args()
    try:
        if args.command == 'schema':
            print(json.dumps(request_schema(), sort_keys=True, indent=2))
            return 0
        result = start(args.request, args.work, args.expected_tip) if args.command == 'start' else replay(args.work)
        print(canonical(result).decode('utf-8'))
        return 0
    except (Refused, OSError, subprocess.SubprocessError, RuntimeError) as error:
        print(f'refused: {error}', file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(kernel_main())
