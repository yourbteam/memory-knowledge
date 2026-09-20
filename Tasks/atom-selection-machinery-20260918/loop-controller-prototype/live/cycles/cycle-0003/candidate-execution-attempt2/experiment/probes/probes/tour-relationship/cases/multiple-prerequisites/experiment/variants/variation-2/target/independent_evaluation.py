"""Evidence-bound observations and deterministic satisfaction scoring.

This contract validates provenance and accounting, not semantic truth. Frozen judges
must also be calibrated with independently expected positive and negative examples.
"""
import copy
import hashlib
import json
import re
from pathlib import Path

ASSESSMENT_FIELDS = {"reference", "output_fields", "criteria"}
SECTION_KEYS = ["reference", "output_fields", "criteria"]


def exact(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(f"{label} must contain exactly {sorted(keys)}")


def pointer(document, value):
    if not isinstance(value, str) or (value and not value.startswith('/')):
        raise ValueError(f"invalid JSON pointer {value!r}")
    current = document
    for encoded in value.split('/')[1:] if value else []:
        if re.search(r'~(?![01])', encoded):
            raise ValueError(f"invalid JSON pointer escape {value!r}")
        key = encoded.replace('~1', '/').replace('~0', '~')
        try:
            if isinstance(current, list):
                if not re.fullmatch(r'0|[1-9][0-9]*', key):
                    raise ValueError('array index must be canonical')
                current = current[int(key)]
            elif isinstance(current, dict):
                current = current[key]
            else:
                raise ValueError('pointer traverses a scalar')
        except (KeyError, IndexError, ValueError) as error:
            raise ValueError(f"JSON pointer {value!r} does not resolve in presented evidence") from error
    return current


def normalize_reference(assessment, base_directory):
    """Keep reference identity while making request-relative location explicit."""
    exact(assessment, ASSESSMENT_FIELDS, 'evaluation.assessment')
    normalized = copy.deepcopy(assessment)
    exact(normalized['reference'], {'path', 'sha256'}, 'assessment.reference')
    value = normalized['reference']['path']
    if not isinstance(value, str) or not value:
        raise ValueError('assessment.reference.path must be nonempty')
    path = Path(value)
    if not path.is_absolute():
        path = Path(base_directory) / path
    normalized['reference']['path'] = str(path.absolute())
    return normalized


def validate(assessment, metrics, spec_path):
    exact(assessment, ASSESSMENT_FIELDS, 'evaluation.assessment')
    ref = assessment['reference']
    exact(ref, {'path', 'sha256'}, 'assessment.reference')
    if not isinstance(ref['path'], str) or not ref['path']:
        raise ValueError('assessment.reference.path must be nonempty')
    path = Path(ref['path'])
    path = path if path.is_absolute() else Path(spec_path).parent / path
    if path.is_symlink() or not path.is_file():
        raise ValueError('assessment.reference must be an existing regular unlinked file')
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != ref['sha256']:
        raise ValueError('assessment.reference SHA-256 does not match frozen reference')
    reference = json.loads(payload)
    fields = assessment['output_fields']
    if (not isinstance(fields, list) or not fields or
        any(not isinstance(field, str) or not field for field in fields) or
        len(set(fields)) != len(fields)):
        raise ValueError('assessment.output_fields must be nonempty unique field names')
    criteria = assessment['criteria']
    if not isinstance(criteria, list) or not criteria:
        raise ValueError('assessment.criteria must be nonempty')
    names = {metric['name'] for metric in metrics}
    if any(metric['direction'] != 'maximize' for metric in metrics):
        raise ValueError('observation satisfaction fractions require maximize metrics')
    seen = set()
    covered = set()
    for criterion in criteria:
        exact(criterion, {'id', 'metric', 'reference_pointer'}, 'assessment criterion')
        identity = criterion['id']
        if not isinstance(identity, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', identity) or identity in seen:
            raise ValueError('assessment criterion IDs must be unique lowercase identities')
        seen.add(identity)
        if not isinstance(criterion['metric'], str) or criterion['metric'] not in names:
            raise ValueError('assessment criterion metric must name a declared metric')
        covered.add(criterion['metric'])
        pointer(reference, criterion['reference_pointer'])
    if covered != names:
        raise ValueError('assessment criteria must cover every declared metric')
    return {'bytes': payload, 'reference': reference, 'sha256': ref['sha256']}


def project(spec, results, reference):
    assessment = spec['evaluation']['assessment']
    candidates = []
    for row in results:
        if not row['eligible']:
            continue
        outcome = row.get('outcome')
        if not isinstance(outcome, dict):
            raise ValueError('candidate outcome must be an object for raw-output projection')
        missing = [field for field in assessment['output_fields'] if field not in outcome]
        if missing:
            raise ValueError(f"candidate {row['variant_id']} lacks declared raw-output fields {missing}")
        candidates.append({'variant_id': row['variant_id'],
            'execution': {name: row[name] for name in ('status', 'exit_code', 'duration_ms', 'timed_out')},
            'output': {field: copy.deepcopy(outcome[field]) for field in assessment['output_fields']}})
    return {'schema_version': 2, 'experiment_id': spec['experiment_id'],
        'metrics': copy.deepcopy(spec['evaluation']['metrics']), 'reference': copy.deepcopy(reference),
        'criteria': copy.deepcopy(assessment['criteria']), 'candidates': candidates}


def score(response, request):
    exact(response, {'schema_version', 'judgments'}, 'observation response')
    if type(response['schema_version']) is not int or response['schema_version'] != 2:
        raise ValueError('observation response schema_version must be 2')
    rows = response['judgments']
    if not isinstance(rows, list) or len(rows) != len(request['candidates']):
        raise ValueError('observation response must cover every candidate exactly once in order')
    accepted = {}
    for row, candidate in zip(rows, request['candidates']):
        exact(row, {'variant_id', 'observations'}, 'candidate judgment')
        if row['variant_id'] != candidate['variant_id']:
            raise ValueError('candidate judgments must preserve presented identity and order')
        observations = row['observations']
        if not isinstance(observations, list) or len(observations) != len(request['criteria']):
            raise ValueError('observations must cover every criterion exactly once in order')
        counts = {metric['name']: [0, 0] for metric in request['metrics']}
        for obs, criterion in zip(observations, request['criteria']):
            exact(obs, {'criterion_id', 'verdict', 'output_pointer', 'reference_pointer', 'reason'}, 'observation')
            if obs['criterion_id'] != criterion['id']:
                raise ValueError('observations must preserve criterion identity and order')
            if obs['reference_pointer'] != criterion['reference_pointer']:
                raise ValueError('observation must cite its frozen criterion reference pointer')
            pointer(request['reference'], obs['reference_pointer'])
            pointer(candidate['output'], obs['output_pointer'])
            if not isinstance(obs['reason'], str) or not obs['reason'].strip():
                raise ValueError('observation must explain its evidence-bound judgment')
            if obs['verdict'] not in ('satisfied', 'not-satisfied', 'cannot-assess'):
                raise ValueError('observation verdict is not allowed')
            if obs['verdict'] == 'cannot-assess':
                raise ValueError(f"candidate {row['variant_id']} criterion {criterion['id']} cannot-assess: {obs['reason']}")
            counts[criterion['metric']][0] += obs['verdict'] == 'satisfied'
            counts[criterion['metric']][1] += 1
        accepted[row['variant_id']] = {name: count / total for name, (count, total) in counts.items()}
    return accepted
