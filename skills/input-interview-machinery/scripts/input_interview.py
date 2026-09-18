"""Public entry point for the packaged, operator-controlled interview."""
import argparse
import json
from pathlib import Path
import runpy
import sys
import ask
import followup
import handoff
import run as review


def advance(root, result, transport_factory=None):
    while result['action'] == 'ready_for_handoff':
        result = handoff.close(root, transport_factory=transport_factory)
    if result['action'] == 'stopped' and 'handoff' not in result:
        result = handoff.close(root, transport_factory=transport_factory)
    return result


def main(argv=None, transport_factory=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == 'configure':
        saved = sys.argv
        try:
            sys.argv = [str(Path(__file__).with_name('configure.py'))] + argv[1:]
            runpy.run_path(sys.argv[0], run_name='__main__')
        finally:
            sys.argv = saved
        return
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='operation', required=True)
    start = sub.add_parser('start', help='Ask all questions and advance to input or final handoff')
    start.add_argument('--questions', type=Path, required=True)
    start.add_argument('--contexts', type=Path)
    start.add_argument('--caller-session')
    start.add_argument('--settings', type=Path)
    start.add_argument('--run', type=Path, required=True)
    for name in ['next', 'user', 'reply', 'stop']:
        command = sub.add_parser(name)
        command.add_argument('--run', type=Path, required=True)
        if name != 'next':
            command.add_argument('--request-id', required=True)
        if name in ['reply', 'stop']:
            command.add_argument('--reply', type=Path, required=True)
    sub.add_parser('configure', help='Template CRUD and model configuration; use configure --help')
    args = parser.parse_args(argv)
    if args.operation == 'start':
        result = ask.ask(args.questions, args.contexts, args.run,
                         transport_factory=transport_factory,
                         caller_session=args.caller_session,
                         model_settings_path=args.settings)['next_action']
    elif args.operation == 'next':
        result = followup.next_action(args.run)
    elif args.operation == 'user':
        result = followup.user_question(args.run, args.request_id)
    elif args.operation == 'reply':
        result = followup.submit(args.run, args.request_id, review.read(args.reply),
                                 transport_factory=transport_factory)
    else:
        result = followup.stop(args.run, args.request_id, review.read(args.reply))
    result = advance(args.run, result, transport_factory)
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == '__main__':
    main()
