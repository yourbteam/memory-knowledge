"""Save existing completed-build evidence for a downstream assessor; no model calls."""
import argparse
import hashlib
import json
from pathlib import Path

from driver_contract import Refusal, read, reference, save, verify


def export(closeout, output):
    closeout, output = Path(closeout).absolute(), Path(output).absolute()
    sources = {}

    def load(name, path, expected=None):
        path = Path(path)
        if expected is not None:
            verify(expected)
        value = read(path)
        sources[name] = reference(path)
        return value

    request = load('driver_request', closeout / 'request.json')
    completion = load('completion', closeout / 'contribution/completion.json')
    if completion.get('achieved') is not True:
        raise Refusal('Build contribution is not achieved; no completed-build handoff can be saved')
    atom = load('atom_request', request['atom_request']['path'], request['atom_request'])
    packet = load('build_packet', request['value_packet']['path'], request['value_packet'])
    admission = load('build_receipt', request['value_receipt']['path'], request['value_receipt'])
    payload = load('assessment_input', closeout / 'contribution-input.json')
    progress = load('progress_result', closeout / 'progress-result.json')
    result_path = closeout / 'actual-result.txt'
    result = load('actual_result', result_path)
    if sources['actual_result']['sha256'] != completion['result_sha256']:
        raise Refusal('Actual result differs from the independently reviewed result')
    if payload['result'] != result_path.read_text():
        raise Refusal('Assessment input does not contain the exact actual result')
    progress_hash = hashlib.sha256(json.dumps(progress, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if progress != payload['progress_result'] or progress != completion['progress_result'] or progress_hash != completion['progress_result_sha256']:
        raise Refusal('Progress evidence differs from the independently reviewed progress')
    if admission['receipt_sha256'] != completion['selection_receipt_sha256']:
        raise Refusal('Completion belongs to a different build admission')
    binding = completion['goal_context']
    goal = load('goal_context', binding['path'], {'path': binding['path'], 'sha256': binding['sha256']})
    if not (goal['goal'] == binding['goal'] == packet['goal'] == payload['goal']):
        raise Refusal('Goal differs between build inputs and completed review')
    if atom != packet['atom_request']:
        raise Refusal('Atom request differs from the admitted build packet')
    for key, expected in [('contribution', packet['candidate']['contribution']),
                          ('proof', packet['candidate']['proof']), ('progress', packet['progress'])]:
        if payload[key] != expected:
            raise Refusal('Assessment input differs from admitted ' + key)
    if result['controller_state']['stage'] != 'complete':
        raise Refusal('Recorded controller state is not complete')
    # Preserve all original wording, limitations and evidence. No new success judgment.
    handoff = {'schema_version': 1, 'kind': 'completed_atom_evidence',
               'atom_request': atom, 'assessment_input': payload,
               'completion': completion, 'sources': sources}
    for ref in sources.values():
        verify(ref)
    if output in [Path(ref['path']) for ref in sources.values()]:
        raise Refusal('Handoff output must not replace a source record')
    save(output, handoff)
    if read(output) != handoff:
        raise Refusal('Saved handoff failed JSON round-trip validation')
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--closeout', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        path = export(args.closeout, args.output)
        print(json.dumps({'handoff': str(path), 'sha256': reference(path)['sha256']}))
        return 0
    except (Refusal, OSError, ValueError, KeyError) as error:
        print(json.dumps({'status': 'refused', 'reason': str(error)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
