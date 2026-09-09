"""Code-owned, one-question invocation preparation; never grants model authority."""
import fcntl
import os
from pathlib import Path
import sys
import uuid

QUESTIONS = (
    ('feature_id', 'Which stable feature identity is being assessed?'),
    ('repositories', 'Which target repositories and product edit boundaries are authorized?'),
    ('description_handoff', 'Where is the sealed Description handoff?'),
    ('requirements_handoff', 'Where is the sealed Requirements handoff for that Description?'),
    ('boundaries', 'Where is the recorded task and authority boundary document?'),
    ('evidence_manifests', 'Which explicit evidence manifests belong to this assessment? Use [] if none.'),
    ('telemetry_manifests', 'Which telemetry manifests belong to this assessment? Use [] if none.'),
    ('blocker_ledgers', 'Which complete blocker ledgers belong to this assessment? Use [] if none.'),
    ('owner_records', 'Which owner records belong to this assessment? Use [] if none. This grants no authority.'),
    ('model_runtime', 'Which explicit supported provider, model and effort should be frozen? This does not authorize a call.'),
    ('execution_limits', 'What explicit input and model execution limits apply?'),
    ('authorized_root', 'Which existing external directory may contain the run? It must be disjoint from every input source directory and repository.'),
)
CONTRACT_PATHS = (
    ('working-agreement', 'working-agreement/DIRECTIVES.md'),
    ('description-skill', 'skills/description-machinery/SKILL.md'),
    ('description-exporter-source', 'skills/description-machinery/scripts/export_handoff.py'),
    ('requirements-skill', 'skills/requirements-machinery/SKILL.md'),
    ('requirements-controller-source', 'skills/requirements-machinery/scripts/cover.py'),
    ('info-intake-skill', 'skills/info-intake-machinery/SKILL.md'),
    ('sequence-runner-skill', 'skills/sequence-runner/SKILL.md'),
    ('experiment-machinery-skill', 'skills/experiment-machinery/SKILL.md'),
    ('prototype-driven-implementation-skill', 'skills/prototype-driven-implementation/SKILL.md'),
    ('atom-building-skill', 'skills/atom-building-machinery/SKILL.md'),
    ('atom-controller-source', 'skills/atom-building-machinery/scripts/atom_controller.py'),
    ('blocker-catalog-source', 'scripts/blocker_catalog.py'),
)
FILE_QUESTIONS = ('description_handoff', 'requirements_handoff', 'boundaries')
LIST_QUESTIONS = ('evidence_manifests', 'telemetry_manifests', 'blocker_ledgers', 'owner_records')
STATE_FIELDS = {'schema_version', 'code_sha256', 'answers', 'prepared', 'launch'}


def code_hash(api):
    return api.digest(api.read_file(Path(__file__), 1048576) + api.read_file(Path(api.__file__), 4194304))


def external_directory(api, path):
    path = api.absolute(str(path))
    for parent in (path, *path.parents):
        if parent.name == 'Tasks' or (parent / '.git').exists() or (parent / '.git').is_symlink():
            raise api.Refused(f'{path}: invocation state must be outside repository and Tasks ancestry')
    fd = api.directory(path)
    os.close(fd)
    return path


def write_at(api, fd, name, value):
    temp = '.pending-' + uuid.uuid4().hex
    try:
        out = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        with os.fdopen(out, 'wb') as stream:
            stream.write(api.canonical(value) + b'\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, name, src_dir_fd=fd, dst_dir_fd=fd)
        os.fsync(fd)
    finally:
        if temp in os.listdir(fd):
            os.unlink(temp, dir_fd=fd)


def schema(api, question):
    root = api.request_schema()
    props = root['properties']
    path = {'type': 'string', 'minLength': 1, 'pattern': '^/'}
    if question in FILE_QUESTIONS or question == 'authorized_root':
        return path
    if question in LIST_QUESTIONS:
        return {'type': 'array', 'items': path, 'uniqueItems': True, 'maxItems': 256}
    if question == 'repositories':
        keys = ('target_repositories', 'product_edit_boundaries')
        return {'type': 'object', 'required': list(keys), 'properties': {key: props['runtime_boundary']['properties'][key] for key in keys}, 'additionalProperties': False}
    return props[question]


def descriptor(api, path):
    path = api.absolute(path)
    return {'path': str(path), 'sha256': api.digest(api.read_file(path, 1073741824))}


def normalize(api, question, value):
    api.validate_shape(value, schema(api, question), 'answer.' + question, api.request_schema())
    if question in FILE_QUESTIONS:
        return descriptor(api, value)
    if question in LIST_QUESTIONS:
        return [descriptor(api, path) for path in value]
    if question == 'repositories':
        for paths in value.values():
            for path in paths:
                api.absolute(path)
                if any(p.is_symlink() for p in (Path(path), *Path(path).parents)):
                    raise api.Refused(f'{path}: linked repository boundary is forbidden')
    if question == 'authorized_root':
        external_directory(api, value)
        if value == '/':
            raise api.Refused('authorized_root: filesystem root is not an authorized runtime boundary')
    return value


def validate_state(api, data):
    if type(data) is not dict or set(data) != STATE_FIELDS or type(data['schema_version']) is not int or data['schema_version'] != 1:
        raise api.Refused('invocation state: invalid fields or version; restore the recorded state')
    if data['code_sha256'] != code_hash(api):
        raise api.Refused('invocation code changed; begin a fresh interview without reusing old answers')
    answers = data['answers']
    if type(answers) is not list or len(answers) > len(QUESTIONS):
        raise api.Refused('invocation answers: invalid ordered answer list')
    for index, row in enumerate(answers):
        if type(row) is not dict or set(row) != {'question', 'answer', 'value'} or row['question'] != QUESTIONS[index][0]:
            raise api.Refused(f'invocation answer {index}: skipped or foreign question')
        api.validate_shape(row['answer'], schema(api, row['question']), 'stored answer', api.request_schema())
        question = row['question']
        if question in FILE_QUESTIONS:
            api.validate_shape(row['value'], api.request_schema()['properties'][question], question, api.request_schema())
            if row['value']['path'] != row['answer']:
                raise api.Refused('stored descriptor differs from its supplied path')
        elif question in LIST_QUESTIONS:
            api.validate_shape(row['value'], api.request_schema()['properties'][question], question, api.request_schema())
            if [d['path'] for d in row['value']] != row['answer']:
                raise api.Refused('stored descriptors differ from their supplied paths')
        elif row['answer'] != row['value']:
            raise api.Refused('stored normalized answer differs from the supplied value')
    if data['prepared'] is not None:
        prepared = data['prepared']
        if len(answers) != len(QUESTIONS) or type(prepared) is not dict or set(prepared) != {'request', 'work', 'members', 'request_sha256'}:
            raise api.Refused('invocation preparation is incomplete or malformed')
        api.validate_request(prepared['request'])
        if api.digest(api.canonical(prepared['request']) + b'\n') != prepared['request_sha256']:
            raise api.Refused('prepared request digest differs')
        expected = request_from_answers(api, answers)
        if expected != prepared['request']:
            raise api.Refused('prepared request differs from the recorded answers or installed contracts')
        if Path(prepared['work']).parent != Path(expected['runtime_boundary']['authorized_root']):
            raise api.Refused('prepared work lies outside its authorized parent')
    if data['launch'] is not None and (data['prepared'] is None or data['launch'] not in ('reserved', 'completed', 'failed')):
        raise api.Refused('invalid invocation launch state')


def request_from_answers(api, answers):
    values = {row['question']: row['value'] for row in answers}
    canonical_root = Path(api.__file__).absolute().parents[3]
    request = {'schema_version': 1, 'feature_id': values['feature_id'],
               'runtime_boundary': {**values['repositories'], 'authorized_root': values['authorized_root']},
               'model_runtime': values['model_runtime'], 'execution_limits': values['execution_limits'],
               'machinery_contracts': [{'role': role, **descriptor(api, str(canonical_root / path))} for role, path in CONTRACT_PATHS]}
    for key in FILE_QUESTIONS + LIST_QUESTIONS:
        request[key] = values[key]
    return request


def prepare(api, session, answers):
    request = request_from_answers(api, answers)
    root = api.absolute(request['runtime_boundary']['authorized_root'])
    if api.overlaps(root, session):
        raise api.Refused(f'{root}: runtime root overlaps invocation state; choose a disjoint external directory')
    work = root / ('readiness-' + uuid.uuid4().hex)
    result = api.preflight(request, work)
    # Validate root itself, not just its random child: moving within a source tree
    # cannot conceal an invalid authorized location for another generated run.
    for _, _, item, _ in result['captured']:
        if api.overlaps(session, Path(item['path']).parent):
            raise api.Refused(f'{session}: invocation state overlaps input source directory {Path(item["path"]).parent}; begin a fresh interview in disjoint storage')
        if api.overlaps(root, Path(item['path']).parent):
            raise api.Refused(f'{root}: runtime root overlaps input source directory {Path(item["path"]).parent}; choose a disjoint external directory')
    return {'request': request, 'work': str(work),
            'members': [{'path': item['path'], 'sha256': item['sha256']} for _, _, item, _ in result['captured']],
            'request_sha256': api.digest(api.canonical(request) + b'\n')}


def status(api, session, data):
    result = {'status': 'interviewing', 'ledger_tip': api.digest(api.canonical(data)),
              'answers_recorded': len(data['answers']), 'model_calls': 0, 'next_question': None}
    if len(data['answers']) < len(QUESTIONS):
        question, prompt = QUESTIONS[len(data['answers'])]
        result['next_question'] = {'id': question, 'prompt': prompt, 'answer_schema': schema(api, question)}
    else:
        result['status'] = 'awaiting-preparation'
    if data['prepared'] is not None:
        result.update({'status': 'prepared', 'work': data['prepared']['work'], 'request': data['prepared']['request'],
                       'next_command': [sys.executable, api.__file__, 'invocation-start', str(session), '--expected-tip', result['ledger_tip']]})
    if data['launch'] is not None:
        result['status'] = 'launch-' + data['launch']
        if data['launch'] == 'completed':
            result['readiness'] = api.replay(data['prepared']['work'])
    return result


def dispatch(api, args):
    session = api.absolute(args.session)
    if args.command == 'invocation-open':
        if session.name == 'Tasks':
            raise api.Refused('invocation state cannot use Tasks ancestry')
        parent = external_directory(api, session.parent)
        fd = api.directory(parent)
        try:
            os.mkdir(session.name, 0o700, dir_fd=fd)
        finally:
            os.close(fd)
        data = {'schema_version': 1, 'code_sha256': code_hash(api), 'answers': [], 'prepared': None, 'launch': None}
        fd = api.directory(session)
        try:
            write_at(api, fd, 'interview.json', data)
        finally:
            os.close(fd)
        return status(api, session, data)
    external_directory(api, session)
    fd = api.directory(session)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        data = api.decode(api.read_file(session / 'interview.json', 16777216), 'invocation state')
        validate_state(api, data)
        if args.command == 'invocation-status':
            return status(api, session, data)
        api.require_tip(args.expected_tip, api.digest(api.canonical(data)))
        if data['launch'] is not None:
            raise api.Refused('launch already reserved; inspect invocation-status; never launch a duplicate run')
        if args.command == 'invocation-answer':
            current = status(api, session, data)['next_question']
            if current is None or args.question != current['id']:
                raise api.Refused(f'answer for {args.question!r}: expected {current}; answer only the current question')
            answer = api.decode(api.read_file(api.absolute(args.answer_json), 16777216), 'answer')
            value = normalize(api, args.question, answer)
            items = [value] if args.question in FILE_QUESTIONS else value if args.question in LIST_QUESTIONS else []
            for item in items:
                if api.overlaps(session, Path(item['path']).parent):
                    raise api.Refused(f'{item["path"]}: input source directory overlaps invocation state; begin a fresh interview in disjoint storage')
            row = {'question': args.question, 'answer': answer, 'value': value}
            if args.question == 'authorized_root':
                prepare(api, session, data['answers'] + [row])
            data['answers'].append(row)
        elif args.command == 'invocation-prepare':
            if len(data['answers']) != len(QUESTIONS):
                raise api.Refused('invocation interview incomplete; answer the returned current question before preparation')
            if data['prepared'] is not None:
                raise api.Refused('invocation already prepared; inspect invocation-status')
            data['prepared'] = prepare(api, session, data['answers'])
        elif args.command == 'invocation-start':
            if data['prepared'] is None:
                raise api.Refused('invocation is not prepared; complete the interview and prepare it first')
            prepared = data['prepared']
            api.preflight(prepared['request'], Path(prepared['work']))
            for member in prepared['members']:
                if descriptor(api, member['path']) != member:
                    raise api.Refused(f'{member["path"]}: input changed after preflight; begin a fresh interview')
            work = Path(prepared['work'])
            if work.exists() or work.is_symlink():
                raise api.Refused(f'{work}: prepared destination already exists; no overwrite or reuse permitted')
            data['launch'] = 'reserved'
            write_at(api, fd, 'interview.json', data)
            try:
                root_fd = api.directory(work.parent)
                try:
                    os.mkdir(work.name, 0o700, dir_fd=root_fd)
                finally:
                    os.close(root_fd)
                write_at(api, fd, 'request.json', prepared['request'])
                api.start(session / 'request.json', work, api.GENESIS)
                data['launch'] = 'completed'
            except Exception:
                data['launch'] = 'failed'
                write_at(api, fd, 'interview.json', data)
                raise
        else:
            raise api.Refused('unknown invocation command')
        write_at(api, fd, 'interview.json', data)
        return status(api, session, data)
    finally:
        os.close(fd)
