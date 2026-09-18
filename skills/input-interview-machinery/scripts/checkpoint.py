"""Per-step call receipts: retain attempts and reuse only identical successful inputs."""
import hashlib
import json
from pathlib import Path
import time
import run as review


def call(folder, stage, prompt, schema, factory, session=None, stats=None):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    request = {'stage': stage, 'prompt': prompt, 'schema': schema, 'session': session}
    fingerprint = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
    receipt = folder / 'step.json'
    if receipt.exists():
        state = review.read(receipt)
        if state['fingerprint'] != fingerprint:
            raise ValueError(f'{stage}: saved input differs; do not reuse this step for changed work')
        if state['status'] == 'completed':
            answer = review.read(folder / state['answer_file'])
            review.validate(answer, schema)
            return answer, state['session']
        # Recover a completed provider call if the process died before committing our receipt.
        previous = folder / 'attempts' / f"{state['attempt']:04d}"
        completions = list(previous.glob('provider/*/completion.json'))
        if len(completions) == 1:
            completion = review.read(completions[0])
            answer = review.read(completions[0].parent / 'answer.json')
            review.validate(answer, schema)
            if completion.get('completed'):
                review.save(previous / 'answer.json', answer)
                state.update(status='completed', session=completion['session'],
                    answer_file=str((previous/'answer.json').relative_to(folder)))
                review.save(receipt, state)
                return answer, state['session']
    attempts = folder / 'attempts'
    attempts.mkdir(exist_ok=True)
    number = max([int(p.name) for p in attempts.iterdir() if p.is_dir()] or [0]) + 1
    attempt = attempts / f'{number:04d}'
    attempt.mkdir()
    review.save(attempt / 'request.json', request)
    state = {'fingerprint': fingerprint, 'stage': stage, 'attempt': number,
             'status': 'running', 'started': time.time()}
    review.save(receipt, state)
    try:
        if stats is not None:
            stats['calls'] += 1
        answer, returned_session = factory(attempt).call(stage, prompt, schema, session)
        review.validate(answer, schema)
        if not returned_session:
            raise ValueError(f'{stage}: missing response session')
        review.save(attempt / 'answer.json', answer)
        state.update(status='completed', session=returned_session,
                     answer_file=str((attempt / 'answer.json').relative_to(folder)))
        review.save(attempt / 'result.json', state)
        review.save(receipt, state)
        return answer, returned_session
    except Exception as exc:
        state.update(status='failed', error=str(exc))
        review.save(attempt / 'result.json', state)
        review.save(receipt, state)
        raise
