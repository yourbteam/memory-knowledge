"""Verify Description provenance from bytes supplied by the controller; never write state."""
import ast
from pathlib import Path


def verify(handoff, read, exporter, question_source):
    exporter.validate_handoff(handoff)
    run = Path(handoff['run_identity'])
    state = exporter.json_value(read(run / 'input-state.json', handoff['input_state_sha256']), 'input-state')
    exporter.exact(state, ('contract', 'intent', 'context', 'owner_answers', 'questions_sha256'), 'input-state')
    if type(state['contract']) is not int or state['contract'] not in (1, 2, 3) or type(state['context']) is not list:
        raise ValueError('Description input-state: require supported contract and an ordered context list')
    if handoff['contract_version'] != (1 if state['contract'] == 1 else 2):
        raise ValueError('Description handoff version does not bind its input contract')
    producer, producer_bytes = exporter.trusted_producer(question_source)
    if handoff['contract_version'] == 2 and handoff['producer_source_sha256'] != exporter.digest(producer_bytes):
        raise ValueError('Description producer identity differs from sealed evidence')
    questions_doc = exporter.json_value(read(run / 'questions.json', handoff['questions_sha256']), 'questions')
    exporter.exact(questions_doc, ('questions',), 'questions')
    questions = questions_doc['questions']
    tree = ast.parse(question_source.decode('utf-8'))
    fixed = [ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.AnnAssign)
             and isinstance(n.target, ast.Name) and n.target.id == 'QUESTIONS']
    if len(fixed) != 1 or questions != fixed[0] or state['questions_sha256'] != exporter.digest(exporter.canonical(questions)):
        raise ValueError('Description questions differ from the fixed producer contract or registered digest')
    if [q['id'] for q in questions] != list(exporter.QUESTION_IDS):
        raise ValueError('Description questions: missing, duplicate or reordered question identity')
    context = exporter.json_value(read(run / 'context.json', handoff['context_sha256']), 'context')
    expected = {'context': [r['path'] for r in state['context']],
                'owner_answers': state['owner_answers']['path'] if state['owner_answers'] else None}
    if context != expected:
        raise ValueError('Description context differs from the bound source identities')
    sources = [state['intent'], *state['context']]
    if state['owner_answers'] is not None:
        sources.append(state['owner_answers'])
    for source in sources:
        exporter.source_binding(source, 'Description source')
    if len({s['path'] for s in sources}) != len(sources):
        raise ValueError('Description sources: duplicate logical identity')
    objects = {}
    for item in handoff['source_objects']:
        objects[item['sha256']] = read(Path(item['origin']), item['sha256']).decode('utf-8')
    if set(objects) != {s['sha256'] for s in sources}:
        raise ValueError('Description source objects: missing or foreign source hash')
    source_text = {s['path']: objects[s['sha256']] for s in sources}
    order = [(seat, qid) for seat in exporter.READER_SEATS for qid in exporter.QUESTION_IDS]
    if [(r['seat'], r['question_id']) for r in handoff['reader_records']] != order:
        raise ValueError('Description readers: require exact seat and question order')
    records = {}
    for item in handoff['reader_records']:
        path = run / item['seat'] / (item['question_id'] + '.json')
        if item['path'] != str(path):
            raise ValueError('Description reader location differs from its sealed run identity')
        raw = read(path, item['sha256'])
        row = exporter.json_value(raw, 'Description reader')
        exporter.exact(row, ('id', 'answered', 'answer', 'quoted_from', 'quote'), 'Description reader')
        if row['id'] != item['question_id'] or row['answered'] != 'yes' or type(row['answer']) is not str:
            raise ValueError('Description reader: wrong identity, missing answer or unanswered question')
        if type(row['quote']) is not str or not row['quote'].strip() or row['quoted_from'] not in source_text or row['quote'] not in source_text[row['quoted_from']]:
            raise ValueError('Description reader quote is absent from its bound source')
        if exporter.digest(exporter.canonical(row)) != item['answer_sha256']:
            raise ValueError('Description reader answer digest differs from its sealed record')
        records[(item['seat'], item['question_id'])] = row
    extras = handoff.get('evidence_records', [])
    by_path = {row['path']:row['sha256'] for row in extras}
    consumed = []
    def read_extra(name):
        path = str(run / name)
        if path not in by_path:
            raise ValueError(f'Description completion evidence missing: {name}')
        consumed.append(path)
        return exporter.json_value(read(Path(path), by_path[path]), name)
    ordered = [{qid:records[(seat,qid)] for qid in exporter.QUESTION_IDS} for seat in exporter.READER_SEATS]
    expected = producer.verify_complete(state, questions, context, source_text, ordered, read_extra)
    if consumed != [row['path'] for row in extras]:
        raise ValueError('Description completion evidence: missing, extra or reordered members')
    description = handoff['description']
    if description['path'] != str(run / 'description.md'):
        raise ValueError('Description output path differs from its sealed run')
    raw = read(Path(description['path']), description['sha256'])
    if raw != expected:
        raise ValueError('Description bytes differ from the complete agreed reader assembly')
    expected_sheet = ("# What only you can answer\n\n" + f"About: {state['intent']['path']}\n\n" +
                      "Everything was answered by what you gave. Nothing to ask.\n").encode('utf-8')
    read(run / 'to-ask.md', exporter.digest(expected_sheet))
    return {'schema_version': 1, 'record_id': 'description-' + handoff['handoff_sha256'],
            'handoff_sha256': handoff['handoff_sha256'], 'description': description,
            'reader_count': len(records), 'source_hashes': sorted(objects)}
