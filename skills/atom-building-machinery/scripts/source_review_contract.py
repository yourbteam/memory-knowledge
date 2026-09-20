"""Bind a bounded source review to exact code, declared obligations and cited evidence."""
import hashlib
import json
from pathlib import Path


class ReviewError(ValueError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def regular(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ReviewError(f"Source {path} is unavailable or linked; supply a regular file")
    return path.read_bytes()


def exact(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ReviewError(f"{label} requires exactly {list(fields)}; received {list(value) if isinstance(value, dict) else type(value).__name__}")


def nonempty(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ReviewError(f"{label} is empty; supply a nonempty string")


def citations(items, sources, label):
    if not isinstance(items, list) or not items:
        raise ReviewError(f"{label} has no evidence; cite at least one supplied source verbatim")
    for item in items:
        exact(item, ('source_id', 'quote'), label + ' citation')
        source = sources.get(item['source_id'])
        if source is None or not isinstance(item['quote'], str) or not item['quote'] or item['quote'] not in source['text']:
            raise ReviewError(f"{label} citation {item!r} is not in its source; provide a nonempty contiguous verbatim quote from a registered source")


def prepare(surface_path, context_path):
    raw = regular(surface_path)
    surface = json.loads(raw)
    context = json.loads(regular(context_path))
    exact(context, ('schema_version', 'surface_sha256', 'outcome', 'obligations', 'sources'), 'Review context')
    if type(context['schema_version']) is not int or context['schema_version'] != 1 or context['surface_sha256'] != digest(raw):
        raise ReviewError('Review context version or surface hash differs; prepare version one against the exact promotion surface')
    nonempty(context['outcome'], 'Review outcome')
    if not isinstance(surface.get('changes'), list) or not surface['changes']:
        raise ReviewError('Promotion surface has no changes; provide the actual nonempty driver surface')
    sources = {}
    for source in context['sources']:
        exact(source, ('id', 'role', 'path', 'origin', 'sha256', 'text'), 'Source')
        nonempty(source['id'], 'Source id')
        if source['id'] in sources or source['role'] not in ('before', 'after', 'requirement', 'context', 'evidence'):
            raise ReviewError(f"Source {source['id']} has a duplicate identity or invalid role")
        data = regular(source['origin'])
        if digest(data) != source['sha256'] or data.decode('utf-8') != source['text']:
            raise ReviewError(f"Source {source['id']} changed; rebuild the review input from its exact current bytes")
        sources[source['id']] = source
    if not sources:
        raise ReviewError('Review sources are empty; supply the changed code and requirements')
    expected = []
    paths = []
    for change in surface['changes']:
        path = change['path']
        if path in paths or change['kind'] not in ('added', 'changed'):
            raise ReviewError(f'Change {path} is duplicate or unsupported; supply unique additions or changes')
        paths.append(path)
        for role in ('before', 'after'):
            sha = change[role + '_sha256']
            if sha is None:
                if role != 'before' or change['kind'] != 'added':
                    raise ReviewError(f'Change {path} has no {role} hash; supply the exact source hash')
                continue
            matches = [s for s in sources.values() if s['role'] == role and s['path'] == path and s['sha256'] == sha]
            if len(matches) != 1:
                raise ReviewError(f'Change {path} needs exactly one {role} source matching {sha}; received {len(matches)}')
            expected.append(matches[0]['id'])
    actual = [s['id'] for s in sources.values() if s['role'] in ('before', 'after')]
    if set(actual) != set(expected):
        raise ReviewError('Before/after sources include code outside the promotion surface; move relevant unchanged dependencies to context')
    if not isinstance(context['obligations'], list) or not context['obligations']:
        raise ReviewError('No declared obligations; supply source-quoted expectations before review')
    ids = []
    for obligation in context['obligations']:
        exact(obligation, ('id', 'evidence'), 'Obligation')
        nonempty(obligation['id'], 'Obligation id')
        if obligation['id'] in ids:
            raise ReviewError(f"Obligation {obligation['id']} is repeated; provide unique identities")
        ids.append(obligation['id'])
        citations(obligation['evidence'], sources, obligation['id'])
        if any(sources[e['source_id']]['role'] != 'requirement' for e in obligation['evidence']):
            raise ReviewError(f"Obligation {obligation['id']} cites non-requirement evidence; cite its authoritative expectation")
    return {'schema_version': 1, 'decision': 'candidate_application',
            'surface_sha256': digest(raw), 'outcome': context['outcome'],
            'changes': surface['changes'], 'obligations': context['obligations'],
            'sources': [{k: v for k, v in s.items() if k != 'origin'} for s in sources.values()]}


def schema():
    def obj(properties):
        return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}
    string = {'type': 'string'}
    evidence = {'type': 'array', 'items': obj({'source_id': string, 'quote': string})}
    def judgment(key):
        return obj({key: string, 'verdict': {'type': 'string', 'enum': ['satisfied', 'not-satisfied', 'cannot-assess']}, 'reason': string, 'evidence': evidence})
    return obj({'obligations': {'type': 'array', 'items': judgment('id')},
                'changes': {'type': 'array', 'items': judgment('path')},
                'blocking_findings': {'type': 'array', 'items': obj({'path': string, 'reason': string, 'evidence': evidence})}})


def receipt(packet, answer):
    exact(answer, ('obligations', 'changes', 'blocking_findings'), 'Review answer')
    sources = {s['id']: s for s in packet['sources']}
    failures = []
    for group, key, expected in (
        ('obligations', 'id', [o['id'] for o in packet['obligations']]),
        ('changes', 'path', [c['path'] for c in packet['changes']]),
    ):
        rows = answer[group]
        if not isinstance(rows, list) or [r.get(key) for r in rows if isinstance(r, dict)] != expected:
            raise ReviewError(f'{group} coverage differs; return exactly {expected} in order')
        for row in rows:
            exact(row, (key, 'verdict', 'reason', 'evidence'), group + ' judgment')
            label = str(row[key]); nonempty(row['reason'], label + ' reason')
            citations(row['evidence'], sources, label)
            if row['verdict'] not in ('satisfied', 'not-satisfied', 'cannot-assess'):
                raise ReviewError(f"{label} verdict {row['verdict']!r} is invalid; use satisfied, not-satisfied or cannot-assess")
            if group == 'changes' and not any(sources[e['source_id']]['role'] == 'after' and sources[e['source_id']]['path'] == label for e in row['evidence']):
                raise ReviewError(f'{label} review does not cite its candidate code; quote its after source')
            if row['verdict'] != 'satisfied':
                failures.append(label + ': ' + row['reason'])
    if not isinstance(answer['blocking_findings'], list):
        raise ReviewError('blocking_findings must be an array; use an empty array only when none were found')
    paths = {c['path'] for c in packet['changes']}
    for finding in answer['blocking_findings']:
        exact(finding, ('path', 'reason', 'evidence'), 'Blocking finding')
        if finding['path'] not in paths:
            raise ReviewError(f"Finding path {finding['path']} is outside the change; name an affected changed path")
        nonempty(finding['reason'], 'Finding reason'); citations(finding['evidence'], sources, finding['path'])
        failures.append(finding['path'] + ': ' + finding['reason'])
    return {'schema_version': 1, 'status': 'completed', 'verdict': 'failed' if failures else 'passed',
            'change_surface_sha256': packet['surface_sha256'], 'blocking_findings': failures}
