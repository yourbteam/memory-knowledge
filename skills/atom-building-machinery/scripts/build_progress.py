"""Fixed goal context and typed, source-bound progress claims."""
import hashlib
import json
from pathlib import Path

KINDS = ('product', 'machinery-reliability', 'autonomy-transfer')


def nonempty(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + ' must be nonempty text')


def exact(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError(label + ' has missing or unexpected fields')


def read(path):
    path = Path(path).absolute()
    if path.is_symlink() or not path.is_file():
        raise ValueError('Goal context must be an existing regular file')
    return path, path.read_bytes()


def create_context(source, output):
    _, data = read(source)
    goal = json.loads(data)
    if not isinstance(goal, dict):
        raise ValueError('Approved goal must be an object')
    for field in ('id', 'outcome'):
        nonempty(goal.get(field), 'Goal ' + field)
    context = {'schema_version': 1, 'goal': goal,
               'approved_source_sha256': hashlib.sha256(data).hexdigest()}
    path = Path(output).absolute()
    with path.open('x') as stream:
        json.dump(context, stream, indent=2)
    return bind_context(goal, path)


def bind_context(goal, path):
    if path is None:
        raise ValueError('An approved fixed goal context is required')
    path, data = read(path)
    context = json.loads(data)
    exact(context, ('schema_version', 'goal', 'approved_source_sha256'), 'Goal context')
    if context['schema_version'] != 1 or context['goal'] != goal:
        raise ValueError('Packet goal differs from the fixed goal context')
    for field in ('id', 'outcome'):
        nonempty(goal.get(field), 'Goal ' + field)
    return {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest(), 'goal': goal}


def verify_context(packet, binding):
    exact(binding, ('path', 'sha256', 'goal'), 'Receipt goal binding')
    if bind_context(packet['goal'], binding['path']) != binding:
        raise ValueError('Fixed goal context changed after admission')


def references(refs, evidence, label):
    if not isinstance(refs, list) or not refs:
        raise ValueError(label + ' requires source evidence')
    sources = {e['path']: e['text'] for e in evidence}
    for ref in refs:
        exact(ref, ('path', 'quote'), label + ' reference')
        nonempty(ref['quote'], label + ' quote')
        if ref['path'] not in sources or ref['quote'] not in sources[ref['path']]:
            raise ValueError(label + ' quote is not verbatim in registered evidence')


def validate_claim(packet):
    claim = packet.get('progress')
    fields = ('kind', 'claim', 'responsibility', 'before', 'after', 'proof')
    if isinstance(claim, dict) and 'workflow' in claim:
        fields += ('workflow',)
    exact(claim, fields, 'Progress contract')
    if claim['kind'] not in KINDS:
        raise ValueError('Unknown progress kind')
    for field in ('claim', 'proof'):
        nonempty(claim[field], 'Progress ' + field)
    exact(claim['before'], ('description', 'evidence'), 'Before state')
    exact(claim['after'], ('description', 'owner'), 'Proposed after state')
    nonempty(claim['before']['description'], 'Before description')
    nonempty(claim['after']['description'], 'After description')
    nonempty(claim['after']['owner'], 'After owner')
    references(claim['before']['evidence'], packet['evidence'], 'Before state')
    if claim['kind'] == 'autonomy-transfer':
        nonempty(claim['responsibility'], 'Transferred manual development responsibility')
    elif claim['responsibility'] is not None:
        raise ValueError('Only autonomy-transfer may claim a transferred responsibility')
    return claim


def validate_result(packet, value, source_root=None):
    fields = ('kind', 'observations', 'before', 'after', 'evidence')
    if isinstance(value, dict) and 'workflow' in value:
        fields += ('workflow',)
    exact(value, fields, 'Progress result')
    if value['kind'] != packet['progress']['kind']:
        raise ValueError('Closeout progress kind differs from admission')
    nonempty(value['observations'], 'Observed progress')
    if not isinstance(value['evidence'], list):
        raise ValueError('Progress result evidence must be a source register')
    seen = set()
    for e in value['evidence']:
        exact(e, ('path', 'sha256', 'text'), 'Progress evidence')
        if not isinstance(e['path'], str) or not isinstance(e['text'], str) or e['path'] in seen:
            raise ValueError('Progress evidence paths must be unique strings')
        seen.add(e['path'])
        if hashlib.sha256(e['text'].encode()).hexdigest() != e['sha256']:
            raise ValueError('Progress evidence hash changed')
        if source_root is not None:
            root = Path(source_root).resolve()
            path = root / e['path']
            if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != e['sha256']:
                raise ValueError('Live progress evidence changed: ' + e['path'])
    # Every before and after observation is tied to the supplied closeout register.
    references(value['before'], value['evidence'], 'Observed before state')
    references(value['after'], value['evidence'], 'Observed after state')
    return value


def report(binding, claim):
    text = 'goal: ' + binding['goal']['id'] + ' | progress: ' + claim['kind']
    if claim['kind'] == 'autonomy-transfer':
        text += ' | responsibility: ' + claim['responsibility']
    return text
