"""Separate component authorship from comparable whole-task intervention evidence."""
import json
import re

BOUNDARY = 'approved-task-and-repository-through-installed-validation-v1'


def trace(path, evidence):
    sources = {item['path']: item['text'] for item in evidence}
    if path not in sources:
        raise ValueError('Workflow trace is not registered evidence: ' + str(path))
    value = json.loads(sources[path])
    required = {'boundary', 'input_sha256', 'complete', 'interventions'}
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError('Workflow trace must contain boundary, input_sha256, complete and interventions')
    if value['boundary'] != BOUNDARY or value['complete'] is not True:
        raise ValueError('Workflow dependence is unknown: require the complete task-to-installed-validation trace, including preparation and recovery')
    if not isinstance(value['input_sha256'], str) or not re.fullmatch('[a-f0-9]{64}', value['input_sha256']):
        raise ValueError('Workflow trace needs the frozen task input SHA-256')
    if not isinstance(value['interventions'], list):
        raise ValueError('Workflow interventions must be a list of actual events')
    seen = set()
    for event in value['interventions']:
        if not isinstance(event, dict) or set(event) != {'id', 'actor', 'action', 'evidence'}:
            raise ValueError('Each intervention needs id, actor, action and evidence')
        if not isinstance(event['id'], str) or not event['id'] or event['id'] in seen:
            raise ValueError('Intervention IDs must be nonempty and unique')
        seen.add(event['id'])
        if event['actor'] not in ('assistant', 'owner', 'host-approval') or not isinstance(event['action'], str) or not event['action'].strip():
            raise ValueError('Intervention needs its actual actor and concrete action')
        refs = event['evidence']
        if not isinstance(refs, list) or not refs:
            raise ValueError('Each intervention needs source-quoted execution evidence')
        for ref in refs:
            if (not isinstance(ref, dict) or set(ref) != {'path', 'quote'} or
                    not isinstance(ref['quote'], str) or not ref['quote'] or
                    ref['path'] not in sources or ref['quote'] not in sources[ref['path']]):
                raise ValueError('Intervention quote must occur in registered execution evidence')
    return value


def selection(packet):
    if packet['progress']['kind'] != 'autonomy-transfer':
        return None
    contract = packet['progress'].get('workflow')
    if not isinstance(contract, dict) or set(contract) != {'baseline', 'remove_ids'}:
        raise ValueError('Autonomy selection withheld before model review: supply progress.workflow with a registered complete baseline trace and remove_ids; component authorship alone does not establish reduced workflow dependence')
    before = trace(contract['baseline'], packet['evidence'])
    ids = contract['remove_ids']
    available = {e['id'] for e in before['interventions'] if e['actor'] == 'assistant'}
    if (not isinstance(ids, list) or not ids or any(not isinstance(i, str) for i in ids)
            or len(set(ids)) != len(ids) or not set(ids).issubset(available)):
        raise ValueError('remove_ids must identify existing assistant interventions in the complete baseline; owner and host approvals cannot be relabeled as removed development work')
    return before


def compare(packet, result):
    if packet['progress']['kind'] != 'autonomy-transfer':
        return {'status': 'not-applicable'}
    unknown = {'status': 'not-established', 'reason': 'No comparable complete intervention traces supplied'}
    contract = packet['progress'].get('workflow')
    actual = result.get('workflow') if isinstance(result, dict) else None
    if not contract or not isinstance(actual, dict) or set(actual) != {'after'}:
        return unknown
    before = trace(contract['baseline'], packet['evidence'])
    after = trace(actual['after'], result['evidence'])
    if before['input_sha256'] != after['input_sha256']:
        return {'status': 'not-established', 'reason': 'Task inputs differ; intervention counts are not comparable'}
    counts = lambda t: {actor: sum(e['actor'] == actor for e in t['interventions']) for actor in ('assistant', 'owner', 'host-approval')}
    b, a = counts(before), counts(after)
    removed = set(contract['remove_ids']).isdisjoint(e['id'] for e in after['interventions'])
    improved = removed and a['assistant'] < b['assistant'] and sum(a.values()) < sum(b.values()) and all(a[k] <= b[k] for k in a)
    return {'status': 'measured-reduction' if improved else 'not-established', 'before': b, 'after': a,
            'reason': 'Counts include preparation, recovery, owner decisions and host approvals; independent review must verify trace completeness and that work was not relocated or renamed'}


def summarize_completion(value):
    component = value.get('component_achieved', value.get('achieved', False)) is True
    workflow = value.get('workflow_progress', {'status': 'not-established', 'reason': 'Historical component receipt has no whole-workflow intervention measure'})
    return {'component_achieved': component, 'workflow_progress': workflow,
            'workflow_reduction_proven': workflow.get('status') == 'proven'}
