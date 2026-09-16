"""Goal-bound lifecycle interlock shared by controller, driver and host hook."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import atom_controller as controller

def registry():
    return controller._blocker_support_root('sequence') / 'operations' / 'atom-sequences'


class Refused(ValueError):
    pass


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def document(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def read(path):
    path = Path(path).absolute()
    if path.is_symlink() or not path.is_file() or path.resolve() != path:
        raise Refused('Require an existing unlinked evidence file: ' + str(path))
    return json.loads(path.read_bytes())


def ref(path):
    path = Path(path).absolute()
    read(path)
    return {'path': str(path), 'sha256': digest(path.read_bytes())}


def verify(item):
    value = read(item['path'])
    if ref(item['path']) != item:
        raise Refused('Evidence changed: ' + item['path'])
    return value


def context(path):
    value = read(path)
    goal_id = value['goal']['id']
    if not isinstance(goal_id, str) or not goal_id.strip():
        raise Refused('Goal needs its existing nonempty id')
    return goal_id, ref(path)


def active_run(path, goal):
    path = Path(path).absolute()
    state = controller._state(path)
    admission = read(path / 'inputs/value-admission.json')
    binding = admission['receipt']['goal_context']
    if {'path': binding['path'], 'sha256': binding['sha256']} != goal:
        raise Refused('Atom run belongs to a different fixed goal')
    return {'run': str(path), 'request': ref(path / 'inputs/atom-request.json'),
            'selection_receipt_sha256': admission['receipt']['receipt_sha256'],
            'progress_kind': admission['packet']['progress']['kind']}, state


def contribution(active, goal, completion_ref):
    completion = verify(completion_ref)
    if completion.get('achieved') is not True:
        raise Refused('Current atom contribution is not achieved; repair this atom before advancing')
    review = completion['review']
    if review.get('verdict') != 'supported' or review.get('progress_verdict') != 'supported':
        raise Refused('Contribution lacks supported outcome and progress judgments')
    if completion['selection_receipt_sha256'] != active['selection_receipt_sha256']:
        raise Refused('Contribution belongs to a different atom admission')
    binding = completion['goal_context']
    if {'path': binding['path'], 'sha256': binding['sha256']} != goal:
        raise Refused('Contribution belongs to a different fixed goal')
    if completion['progress_kind'] != active['progress_kind']:
        raise Refused('Contribution changed the admitted progress kind')
    if active['progress_kind'] == 'autonomy-transfer' and completion.get('workflow_progress', {}).get('status') != 'proven':
        raise Refused('Autonomy contribution requires proven workflow reduction')
    directory = Path(completion_ref['path']).parent.parent
    result_path = directory / 'actual-result.txt'
    result = read(result_path)
    raw = result_path.read_bytes()
    if digest(raw) != completion['result_sha256']:
        raise Refused('Contribution result bytes changed')
    quote = review.get('quote', '')
    if not quote or quote not in raw.decode():
        raise Refused('Contribution quote is absent from its actual result')
    if digest(document(completion['progress_result'])) != completion['progress_result_sha256']:
        raise Refused('Contribution progress evidence changed')
    run = Path(active['run'])
    if directory != run.parent:
        correction = read(directory / 'recheck-source.json')
        if Path(correction['original']).absolute() != run.parent:
            raise Refused('Corrected contribution refers to a different original execution')
        verify(correction['request'])
        for item in correction['files']:
            if digest(Path(item['path']).read_bytes()) != item['sha256']:
                raise Refused('Corrected execution evidence changed: ' + item['path'])
    current = controller._state(run)
    recorded = result['controller_state']
    for field in ['atomic_step_id', 'latest_event_sha256', 'stage']:
        if current[field] != recorded[field]:
            raise Refused('Contribution no longer describes current atom state: ' + field)
    controller._authorize_validation(run)  # preserve validation and blocker checks
    return {'completion': completion_ref, 'result': ref(result_path)}


@contextmanager
def locked(goal_path):
    goal_id, goal = context(goal_path)
    root = registry()
    root.mkdir(parents=True, exist_ok=True)
    if any(p.is_symlink() for p in [root, *root.parents]):
        raise Refused('Sequence registry must not use linked directories')
    key = digest(goal_id.encode())
    path = root / (key + '.json')
    lock_path = root / (key + '.lock')
    if lock_path.is_symlink():
        raise Refused('Sequence lock must not be linked')
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = read(path) if path.exists() else None
        if state is not None and state['goal'] != goal:
            raise Refused('Existing sequence uses a different goal context; reset refused')
        yield path, goal, state


def save(path, value):
    temporary = path.with_suffix('.pending')
    if temporary.is_symlink():
        raise Refused('Sequence temporary file must not be linked')
    with temporary.open('w') as stream:
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def initialize(goal_path, existing_run=None):
    with locked(goal_path) as (path, goal, state):
        if state is not None:
            raise Refused('Sequence already registered; use its active atom')
        active = active_run(existing_run, goal)[0] if existing_run else None
        save(path, {'goal': goal, 'active': active, 'proof': None, 'history': []})
        return {'status': 'initialized', 'sequence': str(path)}


def run_goal(run):
    return read(Path(run) / 'inputs/value-admission.json')['receipt']['goal_context']['path']


def finished(state, goal, run):
    if state is None or state['active'] is None or state['active']['run'] != str(Path(run).absolute()):
        raise Refused('Run is not the registered active atom')
    if state['proof'] is None:
        raise Refused('Active atom has no verified contribution; repair or complete it before advancing')
    return contribution(state['active'], goal, state['proof']['completion'])


def record_completion(run, completion_path):
    with locked(run_goal(run)) as (path, goal, state):
        if state is None or state['active'] is None or state['active']['run'] != str(Path(run).absolute()):
            raise Refused('Completion must belong to the registered active atom')
        proof = contribution(state['active'], goal, ref(completion_path))
        state['proof'] = proof
        save(path, state)
        return {'status': 'contribution-verified', 'sequence': str(path)}


def authorize_next(run):
    with locked(run_goal(run)) as (_, goal, state):
        proof = finished(state, goal, run)
        result = controller._authorize_validation(Path(run))
        return dict(result, contribution=proof)


def start(request_path, run, supersedes, waiver, packet_path, receipt_path):
    if packet_path is None or receipt_path is None:
        raise Refused('Start requires current atom admission and registered goal sequence')
    receipt = read(receipt_path)
    goal_path = receipt['goal_context']['path']
    request = read(request_path)
    with locked(goal_path) as (path, goal, state):
        if state is None:
            raise Refused('No goal sequence registered; explicitly initialize the first atom')
        previous = state['active']
        if previous is not None:
            old_request = verify(previous['request'])
            if request['atomic_step_id'] == old_request['atomic_step_id']:
                if state['proof'] is not None or supersedes is None or str(Path(supersedes).absolute()) != previous['run']:
                    raise Refused('Same-atom start requires its active unfinished predecessor via supersedes')
            else:
                finished(state, goal, previous['run'])
        # The existing admission/contract checks still run before product/run mutation.
        result = controller._start_unsequenced(request_path, run, supersedes, waiver, packet_path, receipt_path)
        current, _ = active_run(run, goal)
        if previous is not None:
            state['history'].append({'active': previous, 'proof': state['proof']})
        state['active'] = current
        state['proof'] = None
        save(path, state)
        return result


def authorize_host(packet, receipt, targets):
    with locked(receipt['goal_context']['path']) as (_, goal, state):
        if any(Path(target).resolve() == registry().resolve() or registry().resolve() in Path(target).resolve().parents for target in targets):
            raise Refused('Ordinary edits cannot modify sequence authority')
        if state is None or state['active'] is None:
            raise Refused('No active atom is registered for this goal')
        active = state['active']
        if state['proof'] is not None:
            raise Refused('Active atom is closed; admit and start its verified successor before editing')
        original = read(Path(active['run']) / 'inputs/value-admission.json')
        if original['packet'] != packet or original['receipt'] != receipt:
            raise Refused('Host admission differs from the registered active atom')
        active_run(active['run'], goal)
        return True


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='action', required=True)
    initial = sub.add_parser('initialize')
    initial.add_argument('--goal', required=True)
    initial.add_argument('--existing-run')
    complete = sub.add_parser('record-completion')
    complete.add_argument('--run', required=True)
    complete.add_argument('--completion', required=True)
    args = parser.parse_args()
    try:
        result = initialize(args.goal, args.existing_run) if args.action == 'initialize' else record_completion(args.run, args.completion)
        print(json.dumps(result))
        return 0
    except (ValueError, KeyError, TypeError, OSError, controller.AtomError) as error:
        print(json.dumps({'status': 'refused', 'reason': str(error)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
