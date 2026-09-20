"""Prepare a source-bound completion recheck without rebuilding the atom."""
import hashlib
import re
from pathlib import Path
from build_preparation import read, ref, save, verify


def prepare(state, dump, tables):
    original = Path(state['build_output'])
    if state['stage'] != 'build' or not (original/'contribution/completion.json').exists():
        raise ValueError('Completion recheck requires a saved assessed build')
    request = read(original/'request.json')
    root = Path(request['repository_root'])
    target = original.parent/'completion-recheck'
    evidence = Path(state['cycle']).parent/'completion-preparation'
    evidence.mkdir(parents=True, exist_ok=True)
    # Extract only complete CREATE/ALTER statements for explicitly named tables.
    # No INSERT statements or row data enter the model payload.
    patterns = [re.compile(r'^(?:CREATE|ALTER) TABLE `' + re.escape(t) + r'`(?:\s|$)') for t in tables]
    digest = hashlib.sha256(); sections = []; active = None
    before = Path(dump).stat()
    with Path(dump).open('rb') as stream:
        for number, line in enumerate(stream, 1):
            digest.update(line)
            text = line.decode('utf-8')
            if active is None and any(p.match(text) for p in patterns):
                active = {'line': number, 'text': ''}
            if active is not None:
                active['text'] += text
                if text.rstrip().endswith(';'):
                    sections.append(active); active = None
    after = Path(dump).stat()
    if active or not sections or (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
        raise ValueError('Schema extraction incomplete or source changed during collection')
    schema = evidence/'mysql-schema.json'
    save(schema, {'source':str(Path(dump).resolve()), 'source_sha256':digest.hexdigest(),
                  'tables':tables, 'statements':sections,
                  'scope':'Saved owner-provided export, not a current production database observation.'})
    baseline = Path(__file__).parent/'verification-preparation-probe-v1/input-state.json'
    config = evidence/'delivery-context.json'
    save(config, {'repository_root':str(root),'baseline':ref(baseline),
                  'preserved_checkout':str(Path(read(baseline)['runtime']['phpunit']).parents[2]),
                  'schema_evidence':[ref(schema)]})
    return {'original':str(original),'output':str(target),'request':ref(original/'request.json'),'config':ref(config)}
