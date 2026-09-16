"""Host patch admission must match the controller's active goal sequence."""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import atom_sequence


def evaluate(event, policy_path):
    if event.get('hook_event_name') != 'PreToolUse' or event.get('tool_name') != 'apply_patch':
        return {}
    try:
        policy = atom_sequence.read(policy_path)
        command = event['tool_input']['command']
        if not isinstance(command, str) or not command.startswith('*** Begin Patch\n') or command.rstrip().splitlines()[-1] != '*** End Patch':
            raise ValueError('Patch must use the canonical envelope')
        targets = []
        for line in command.splitlines():
            for prefix in ('*** Add File: ', '*** Update File: ', '*** Delete File: ', '*** Move to: '):
                if line.startswith(prefix):
                    target = Path(line[len(prefix):])
                    targets.append(str((Path(event['cwd']) / target).resolve()))
        if not targets:
            raise ValueError('Patch contains no file operations')
        packet = atom_sequence.read(policy['packet'])
        receipt = atom_sequence.read(policy['receipt'])
        atom_sequence.authorize_host(packet, receipt, targets)
        return {}
    except Exception as error:
        return {'hookSpecificOutput': {'hookEventName': 'PreToolUse',
                'permissionDecision': 'deny', 'permissionDecisionReason': 'Atom lifecycle withheld: ' + str(error)}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--policy', required=True)
    args = parser.parse_args()
    try:
        result = evaluate(json.load(sys.stdin), args.policy)
    except Exception as error:
        print('Lifecycle hook input failed: ' + str(error), file=sys.stderr)
        raise SystemExit(2)
    print(json.dumps(result))
