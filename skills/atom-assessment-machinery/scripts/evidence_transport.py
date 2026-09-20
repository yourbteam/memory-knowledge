"""Reversible evidence representation: structured embedded JSON and shared values."""
import collections
import hashlib
import json
from functools import lru_cache

REF = '$evidence_ref'
SERIAL = '$serialized_json'
LITERAL = '$literal_object'


def wire(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


@lru_cache(maxsize=256)
def structured(text):
    """Decode only containers whose exact text can be reconstructed; otherwise retain it."""
    if not text.lstrip().startswith(('{', '[')):
        return None
    try:
        value = json.loads(text)
    except ValueError:
        return None
    if not isinstance(value, (dict, list)):
        return None
    for indent in [None, 2, 4]:
        for ascii in [False, True]:
            for compact in [False, True]:
                options = {'indent': indent, 'ensure_ascii': ascii}
                if compact:
                    options['separators'] = (',', ':')
                rendered = json.dumps(value, **options)
                for suffix in ['', '\n']:
                    if rendered + suffix == text:
                        return value, {'indent': indent, 'ensure_ascii': ascii,
                                       'compact': compact, 'suffix': suffix}
    return None


def expand(value):
    if isinstance(value, str):
        parsed = structured(value)
        if parsed:
            data, style = parsed
            return {SERIAL: {'value': expand(data), 'style': style}}
    if isinstance(value, dict):
        result = {k: expand(v) for k, v in value.items()}
        return {LITERAL: result} if set(value) in [{REF}, {SERIAL}, {LITERAL}] else result
    if isinstance(value, list):
        return [expand(v) for v in value]
    return value


def pack(value):
    expanded = expand(value)
    counts = collections.Counter()
    values = {}

    def fingerprint(v):
        raw = wire(v)
        return hashlib.sha256(raw.encode()).hexdigest(), len(raw)

    def count(v):
        key, size = fingerprint(v)
        if size >= 512:
            counts[key] += 1
            values[key] = v
        if isinstance(v, dict):
            for child in v.values(): count(child)
        elif isinstance(v, list):
            for child in v: count(child)
    count(expanded)
    shared = {k for k, n in counts.items() if n > 1}
    definitions = {}
    ids = {}

    def encode(v, inline=False):
        key, _ = fingerprint(v)
        if not inline and key in shared:
            if key not in ids:
                ids[key] = 'D%04d' % (len(ids) + 1)
                definitions[ids[key]] = encode(v, True)
            return {REF: ids[key]}
        if isinstance(v, dict): return {k: encode(w) for k, w in v.items()}
        if isinstance(v, list): return [encode(w) for w in v]
        return v
    root = encode(expanded)
    result = {'format': 'shared-evidence-v1', 'instructions':
              'Read root and definitions together. $evidence_ref refers to the full value in definitions. '
              '$serialized_json.value contains the original JSON text decoded as data; style preserves its exact serialization. '
              '$literal_object escapes an original object using a reserved marker. Nothing is omitted or summarized.',
              'root': root, 'definitions': definitions}
    if unpack(result) != value:
        raise ValueError('Evidence transport failed exact reconstruction')
    return result


def unpack(packet):
    def restore(v):
        if isinstance(v, list): return [restore(w) for w in v]
        if not isinstance(v, dict): return v
        if set(v) == {REF}: return restore(packet['definitions'][v[REF]])
        if set(v) == {LITERAL}: return {k: restore(w) for k, w in v[LITERAL].items()}
        if set(v) == {SERIAL}:
            serial = restore(v[SERIAL]);style = serial['style']
            options = {'indent': style['indent'], 'ensure_ascii': style['ensure_ascii']}
            if style['compact']: options['separators'] = (',', ':')
            return json.dumps(serial['value'], **options) + style['suffix']
        return {k: restore(w) for k, w in v.items()}
    return restore(packet['root'])
