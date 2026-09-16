"""Validate a frozen source boundary and materialize model edits without interpreting code."""
import hashlib
import json
import json
import shutil
import stat
from pathlib import Path, PurePosixPath


class BuildError(ValueError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def relative(value):
    if not isinstance(value, str) or not value:
        raise BuildError('Supply a nonempty relative source path')
    p = PurePosixPath(value)
    if p.is_absolute() or '..' in p.parts or p.as_posix() != value or value == '.':
        raise BuildError('Noncanonical relative source path: ' + value)
    return value


def snapshot(root):
    root = Path(root)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise BuildError('Baseline must be an absolute regular directory')
    rows = []
    for p in sorted(root.rglob('*')):
        if p.is_symlink():
            raise BuildError('Linked baseline entry: ' + str(p))
        if p.is_dir():
            continue
        if not p.is_file():
            raise BuildError('Nonregular baseline entry: ' + str(p))
        rows.append({'path': p.relative_to(root).as_posix(), 'sha256': digest(p.read_bytes())})
    return rows


def prepare(request):
    fields = {'schema_version', 'outcome', 'constraints', 'allowed_paths', 'baseline', 'files', 'source_units', 'context'}
    version = request.get('schema_version') if isinstance(request, dict) else None
    if version == 2:
        fields = fields | {'execution_runtime'}
    if not isinstance(request, dict) or set(request) != fields or version not in (1, 2):
        raise BuildError('Use version one, or version two with execution_runtime')
    for key in ['outcome', 'constraints', 'context']:
        if not isinstance(request[key], str) or not request[key].strip():
            raise BuildError('Supply nonempty ' + key)
    allowed = request['allowed_paths']
    if not isinstance(allowed, list) or not allowed or len(allowed) != len(set(allowed)):
        raise BuildError('Supply unique allowed file paths')
    for path in allowed:
        relative(path)
    if snapshot(request['baseline']) != request['files']:
        raise BuildError('Baseline differs from its frozen file register')
    units = request['source_units']
    if not isinstance(units, list) or not units:
        raise BuildError('Supply the exact visible source units')
    for unit in units:
        if not isinstance(unit, dict) or set(unit) != {'path', 'text'}:
            raise BuildError('A source unit requires path and text')
        p = Path(request['baseline']) / relative(unit['path'])
        if not p.is_file() or not isinstance(unit['text'], str) or not unit['text'] or unit['text'] not in p.read_text():
            raise BuildError('Source unit is absent from baseline: ' + str(p))
    for path in allowed:
        p = Path(request['baseline']) / path
        if p.exists() and not p.is_file():
            raise BuildError('Allowed target is not a regular file: ' + path)
    packet = {key: request[key] for key in ['outcome', 'constraints', 'allowed_paths', 'source_units', 'context']}
    if version == 2:
        from execution_context import collect, supporting_helpers
        packet['execution_evidence'] = collect(request['execution_runtime'])
        packet['context'] += ('\nSupporting helper definitions (direct same-module calls):\n'
                              + json.dumps(supporting_helpers(packet['execution_evidence']), indent=2))
    return packet


def schema():
    edit = {'type': 'object', 'properties': {k: {'type': 'string'} for k in ['path', 'anchor', 'replacement']},
            'required': ['path', 'anchor', 'replacement'], 'additionalProperties': False}
    return {'type': 'object', 'properties': {'status': {'type': 'string', 'enum': ['candidate', 'blocked']},
            'reason': {'type': 'string'}, 'edits': {'type': 'array', 'items': edit}},
            'required': ['status', 'reason', 'edits'], 'additionalProperties': False}


def output_boundary(output, baseline):
    output = Path(output).absolute(); baseline = Path(baseline)
    if output.exists() or output.is_symlink() or output == baseline or baseline in output.parents or output in baseline.parents:
        raise BuildError('Candidate output must be new and disjoint from baseline')
    for parent in output.parents:
        if parent.is_symlink():
            raise BuildError('Linked candidate output parent: ' + str(parent))


def materialize(request, reply, output):
    prepare(request)
    if not isinstance(reply, dict) or set(reply) != {'status', 'reason', 'edits'}:
        raise BuildError('Builder response requires status, reason and edits')
    if not isinstance(reply['reason'], str) or not reply['reason'].strip():
        raise BuildError('Builder must explain its result')
    if reply['status'] == 'blocked':
        raise BuildError('Builder blocked: ' + reply['reason'])
    if reply['status'] != 'candidate' or not isinstance(reply['edits'], list) or not reply['edits']:
        raise BuildError('A candidate requires nonempty edits')
    baseline = Path(request['baseline']); output = Path(output).absolute()
    output_boundary(output, baseline)
    changes = {}
    for edit in reply['edits']:
        if not isinstance(edit, dict) or set(edit) != {'path', 'anchor', 'replacement'}:
            raise BuildError('Each edit requires path, anchor and replacement')
        path = relative(edit['path'])
        if path not in request['allowed_paths']:
            raise BuildError('Edit outside allowed paths: ' + path)
        if not isinstance(edit['anchor'], str) or not isinstance(edit['replacement'], str) or not edit['replacement'] or len(edit['replacement']) > 60000:
            raise BuildError('Edit requires a string anchor and nonempty replacement of at most 60000 characters')
        source = baseline / path
        if source.exists():
            original = source.read_text(); anchor = edit['anchor']
            visible = [u['text'] for u in request['source_units'] if u['path'] == path]
            if not anchor or original.count(anchor) != 1 or not any(anchor in text for text in visible):
                raise BuildError('Anchor must occur once and be visible in supplied source: ' + path)
        elif edit['anchor'] or path in changes:
            raise BuildError('New file needs one empty-anchor edit: ' + path)
        changes.setdefault(path, []).append(edit)
    payloads = {}
    for path, edits in changes.items():
        source = baseline / path
        if not source.exists():
            payloads[path] = edits[0]['replacement']; continue
        original = source.read_text()
        spans = sorted((original.index(e['anchor']), original.index(e['anchor']) + len(e['anchor']), e['replacement']) for e in edits)
        if any(a[1] > b[0] for a, b in zip(spans, spans[1:])):
            raise BuildError('Overlapping edits: ' + path)
        for start, end, replacement in reversed(spans):
            original = original[:start] + replacement + original[end:]
        if original.encode() == source.read_bytes():
            raise BuildError('Candidate contains a no-op change: ' + path)
        payloads[path] = original
    shutil.copytree(baseline, output)
    for p in [output, *output.rglob('*')]:
        p.chmod(p.stat().st_mode | stat.S_IWUSR | (stat.S_IXUSR if p.is_dir() else 0))
    for path, text in payloads.items():
        target = output / path; target.parent.mkdir(parents=True, exist_ok=True); target.write_text(text)
    if snapshot(baseline) != request['files']:
        raise BuildError('Baseline changed during materialization; discard this candidate')
    files = snapshot(output)
    before = {v['path']: v['sha256'] for v in request['files']}
    changed = [v['path'] for v in files if before.get(v['path']) != v['sha256']]
    if sorted(changes) != changed:
        raise BuildError('Materialized file delta differs from the model proposal')
    return {'status': 'candidate', 'source': str(output), 'changed_paths': changed, 'files': files,
            'proposal_sha256': digest(json.dumps(reply, sort_keys=True).encode())}
