"""Code-owned locations for every leaf in a frozen JSON packet."""
import copy
import json


def get(packet, pointer):
    value = packet
    for key in pointer.split('/')[1:]:
        key = key.replace('~1', '/').replace('~0', '~')
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def build(packet):
    rows = []
    def visit(value, pointer):
        if isinstance(value, dict) and value:
            for key, item in value.items():
                visit(item, pointer + '/' + key.replace('~', '~0').replace('/', '~1'))
        elif isinstance(value, list) and value:
            for i, item in enumerate(value):
                visit(item, pointer + '/' + str(i))
        else:
            text = value if isinstance(value, str) else json.dumps(value)
            lines = text.splitlines(keepends=True) or ['']
            start = 0
            for i in range(0, len(lines), 12):
                passage = ''.join(lines[i:i+12])
                rows.append({'id': 'E%04d' % (len(rows)+1), 'pointer': pointer,
                             'start': start, 'end': start+len(passage), 'text': passage,
                             'encoding': 'string' if isinstance(value, str) else 'json'})
                start += len(passage)
    visit(packet, '')
    groups = {}
    for row in rows:
        groups.setdefault((row['encoding'], row['text']), []).append(row)
    entries = []
    for group in groups.values():
        entry = dict(group[0])
        entry['other_locations'] = [{k:r[k] for k in ['pointer','start','end']} for r in group[1:]]
        entries.append(entry)
    result = {'entries': entries, 'original_passages': len(rows)}
    for entry in entries:
        resolve(packet, entry)
    return result


def resolve(packet, entry):
    for location in [entry] + entry['other_locations']:
        value = get(packet, location['pointer'])
        text = value if entry['encoding'] == 'string' else json.dumps(value)
        if text[location['start']:location['end']] != entry['text']:
            raise ValueError('Evidence no longer matches its frozen location: ' + entry['id'])
    return entry


def final_schema(template, catalog):
    schema = copy.deepcopy(template)
    ids = [e['id'] for e in catalog['entries']]
    for key, section in schema['properties'].items():
        item = section if key == 'goal_completion' else section['items']
        item['properties']['evidence']['items']['enum'] = ids
    return schema


def prompt_catalog(catalog):
    return [{k:v for k,v in e.items() if k != 'other_locations'} for e in catalog['entries']]


def selected(packet, catalog, assessment):
    ids = set()
    for key, section in assessment.items():
        for item in [section] if key == 'goal_completion' else section:
            ids.update(item['evidence'])
    lookup = {e['id']:e for e in catalog['entries']}
    return {i:resolve(packet, lookup[i]) for i in sorted(ids)}
