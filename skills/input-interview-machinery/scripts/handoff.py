"""Check cross-question effects in existing interview sessions; assemble answers without rewriting."""
import argparse
import hashlib
import json
from pathlib import Path
import followup
import run as review
import configure
import copy


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def packet(root, state):
    questions = review.read(root / 'questions.json')['questions']
    ids = [q['id'] for q in questions]
    actual = [a['question']['id'] for a in state['answers']]
    if len(set(ids)) != len(ids) or actual != ids:
        raise ValueError('Handoff requires every original question exactly once in original order')
    if any(a['question'] != q for a, q in zip(state['answers'], questions)):
        raise ValueError('Original question changed; preserve corrections separately')
    return {'questions_and_answers': state['answers'], 'feedback_history': state['history'],
            'reconciliations': state.get('reconciliations', []),
            'source_context_by_question': review.read(root / 'contexts.json')}


def assemble(root, state, checked=None):
    contents = packet(root, state)
    stopped = state['status'] == 'stopped'
    if not stopped and (state['pending'] or state['status'] != 'finished' or checked != digest(contents)):
        raise ValueError('Cannot export completion before current answers pass cross-question review')
    entries = []
    for item in state['answers']:
        qid = item['question']['id']
        answer = item['final_answer']
        ready = answer['self_assessment']['choice'] == 'ready'
        if not stopped and not ready:
            raise ValueError('Cannot mark an unresolved answer complete')
        entries.append({'question': item['question'],
            'effective_question': item.get('effective_question', item['question']),
            'final_answer': answer, 'answer_status': 'answered' if ready else 'unresolved',
            'session': item['session'],
            'followups': [x for x in state['history'] if x['request']['question_id'] == qid],
            'pending_followup': state['pending'] if state['pending'] and state['pending']['question_id'] == qid else None,
            'revisions': [x for x in state.get('reconciliations', []) if x['question_id'] == qid]})
    artifact = {'model_settings': configure.run_settings(root), 'status': 'stopped' if stopped else 'completed', 'questions': entries,
        'unresolved_question_ids': [e['question']['id'] for e in entries if e['answer_status'] == 'unresolved'],
        'operator_stop': state.get('stop_feedback'),
        'cross_question_review': 'not_required_for_stopped_export' if stopped else 'passed',
        'checked_snapshot': checked if not stopped else None,
        'meaning': 'Answers copied verbatim; readiness is the interviewed model judgment, not a guarantee of completeness.'}
    followup.save(root / 'handoff.json', artifact)
    return {'action': 'stopped' if stopped else 'complete', 'handoff': str(root / 'handoff.json'),
            'unresolved_question_ids': artifact['unresolved_question_ids']}


def check_one(folder, item, contents, factory):
    folder.mkdir(parents=True, exist_ok=True)
    prompt = ('Use the supplied complete interview context to continue work on the target question. '
        'Check whether YOUR latest saved answer remains usable after considering the other questions, '
        'their answers and all later operator feedback below. This is a dependency check, not a new '
        'context-blind assessor. Source IDs are scoped to their question. Owner corrections override '
        'rejected premises; another model answer is not independent source proof. Keep the answer if '
        'no consequential supported change is needed; do not manufacture inconsistencies. Choose revise '
        'only when you can identify a concrete affected claim, missing dependency or owner correction. '
        'Explain the evidence and consequence. Do not rewrite answers in this check. No tools.\n' +
        json.dumps({'target_question_id': item['question']['id'], 'interview': contents}, ensure_ascii=False))
    schema = review.eng.obj({'decision': {'type':'string','enum':['keep','revise']}, 'reason':review.eng.TEXT})
    (folder / 'prompt.txt').write_text(prompt)
    review.save(folder / 'schema.json', schema)
    import checkpoint
    response, session = checkpoint.call(folder, 'cross-question', prompt, schema, factory)
    review.validate(response, schema)
    if not response['reason'].strip():
        raise ValueError('Cross-question judgment requires a reason')
    review.save(folder / 'answer.json', response)
    return response


def close(root, transport_factory=None):
    root = Path(root).resolve()
    followup.next_action(root)
    factory = transport_factory or configure.factory_for(root)
    with followup.locked(root):
        state = followup.load(root)
        contents = packet(root, state)
        if state['status'] == 'stopped':
            return assemble(root, state)
        if state['status'] != 'finished' or state['pending']:
            return followup.action(state)
        fingerprint = digest(contents)
        if state.get('checked_snapshot') == fingerprint:
            return assemble(root, state, fingerprint)
        folder = root / 'closure' / fingerprint
        folder.mkdir(parents=True, exist_ok=True)
        review.save(folder / 'input.json', contents)
        checks = []
        before = copy.deepcopy(state)
        try:
            for item in state['answers']:
                target = folder / item['question']['id'] / 'check'
                # Successful checks are reusable only for this exact immutable snapshot.
                if (target / 'answer.json').exists(): verdict = review.read(target / 'answer.json')
                else: verdict = check_one(target, item, contents, factory)
                checks.append((item, verdict))
            changed = False
            for item, verdict in checks:
                if verdict['decision'] == 'keep': continue
                qid = item['question']['id']
                revision = folder / qid / 'revision'
                revision.mkdir(exist_ok=True)
                prompt = ('Use the supplied context to revise the answer to the target question using '
                    'the concrete cross-question finding and complete interview evidence below. Preserve '
                    'valid evidence and limits; respect owner corrections. Return a complete answer, '
                    'not a critique. If needed information remains missing, ask for it using needs_input. '
                    'Do not invent facts or broaden the task. No tools.\n' + json.dumps({
                    'question':item.get('effective_question', item['question']), 'finding':verdict,
                    'interview':contents}, ensure_ascii=False))
                initial = revision / 'initial';initial.mkdir(exist_ok=True)
                (initial / 'prompt.txt').write_text(prompt)
                schema = review.eng.submission_schema();review.save(initial / 'schema.json',schema)
                import checkpoint
                answer, session = checkpoint.call(initial, 'revise', prompt, schema, factory)
                review.validate(answer,schema)
                choice=answer['self_assessment']
                if bool(choice['question'].strip()) != (choice['choice']=='needs_input'):
                    raise ValueError('Revision readiness and follow-up question disagree')
                review.save(initial/'answer.json',answer)
                data={'question':item.get('effective_question',item['question']),
                      'private_context':[{'id':'complete-interview', 'text':json.dumps(contents,ensure_ascii=False)}], 'starting_answer':answer}
                review.save(revision/'input.json',data)
                review.run(revision/'input.json',revision/'review',transport_factory=factory,initial_session=session)
                final=review.read(revision/'review/final-answer.json')
                if final==item['final_answer']:
                    raise ValueError('Cross-question revision produced no change; requires operator review')
                state.setdefault('reconciliations',[]).append({'question_id':qid,'finding':verdict,
                    'previous_answer':item['final_answer'],'final_answer':final,'evidence':str(revision)})
                item['final_answer']=final;changed=True
            if changed:
                followup.advance(state)
                followup.save(followup.path(root),state)
                followup.save(root/'current-answers.json',state['answers'])
                return followup.action(state)
            state['checked_snapshot']=fingerprint
            followup.save(followup.path(root),state)
            return assemble(root,state,fingerprint)
        except Exception as exc:
            # Do not commit only part of a revision batch. Its completed calls remain reusable.
            state = before
            state['status']='failed';state['error']=str(exc);state['failed_phase']='closure'
            followup.save(followup.path(root),state)
            review.save(folder/'failure.json',{'error':str(exc)})
            raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True)
    print(json.dumps(close(p.parse_args().run),ensure_ascii=False))
