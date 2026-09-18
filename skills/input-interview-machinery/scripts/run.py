"""Code-owned fixed eight-lens review, using the existing Codex transport."""
import argparse
import difflib
import importlib.util
import json
from pathlib import Path
import sys

P = Path(__file__).resolve().parent
import interview as eng

LENS_IDS = ('connections', 'conditions', 'support', 'use', 'consistency',
            'unanswered-dependencies', 'decision-boundary', 'exact-relationship')
# Preserved byte-for-byte from the validated sequential comparison.
COMMON = ('Review the supplied starting answer to the original question using the lens instructions. '
 'The archived records are the available task context. Apply the lenses in their listed order. '
 'Do not search for a predetermined error or manufacture findings. No change is valid. '
 'Revise only consequential supported issues, preserving earlier valid facts, evidence, permitted assumptions and limits. '
 'Do not broaden the original question or demand a different evidence level. '
 'Return a complete self-contained answer, not a critique, delta or summary. No tools. ')


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def validate(value, schema, where='response'):
    """Validate the small existing JSON contract; never decide semantic quality."""
    kind = schema['type']
    if kind == 'object':
        if not isinstance(value, dict) or set(value) != set(schema['properties']):
            raise ValueError(f'{where}: fields must match the declared contract')
        for key, sub in schema['properties'].items():
            validate(value[key], sub, where + '.' + key)
    elif kind == 'array':
        if not isinstance(value, list):
            raise ValueError(f'{where}: expected array')
        for item in value:
            validate(item, schema['items'], where + '[]')
    elif kind == 'string':
        if not isinstance(value, str):
            raise ValueError(f'{where}: expected string')
        if 'enum' in schema and value not in schema['enum']:
            raise ValueError(f'{where}: expected one of {schema["enum"]}')
    else:
        raise ValueError(f'Unsupported schema type: {kind}')


def response_schema():
    return eng.obj({'lens_assessment': eng.obj({
        'decision': {'type': 'string', 'enum': ['changed', 'no_change', 'not_applicable']},
        'reason': eng.TEXT}), 'complete_answer': eng.submission_schema()})


def build_prompt(data, current, lens, session):
    packet = {'original_question': data['question'],
              'latest_complete_answer': current, 'lens': lens}
    if session is None:
        packet['private_context'] = data['private_context']
    return (COMMON + 'Apply ONLY the single lens in this turn. '
            + ('Continue with the original source context supplied in this same session. ' if session else '')
            + 'Return lens_assessment and complete_answer.\n'
            + json.dumps(packet, ensure_ascii=False))


class RecordedReplay:
    """Replay actual responses only when prompt/schema/session match the captured call."""
    mode = 'recorded_replay'

    def __init__(self, source, output):
        self.source, self.output = Path(source), Path(output)

    def call(self, stage, prompt, schema, session):
        recorded = self.source / 'probe' / stage
        invocation = read(recorded / 'invocation.json')
        completion = read(recorded / 'completion.json')
        if prompt != (recorded / 'prompt.txt').read_text():
            raise ValueError(f'{stage}: prompt differs from captured real request')
        if schema != read(recorded / 'schema.json') or invocation['session'] != session:
            raise ValueError(f'{stage}: schema/session differs from captured real request')
        if not completion['completed']:
            raise ValueError(f'{stage}: captured call did not complete')
        response = read(recorded / 'answer.json')
        save(self.output / 'probe' / stage / 'replay.json', {
            'mode': self.mode, 'source': str(recorded.resolve()),
            'session': completion['session'], 'new_model_calls': 0})
        return response, completion['session']


class CodexTransport:
    mode = 'live'

    def __init__(self, output, model_settings=None):
        import configure
        chosen = configure.settings(model_settings or configure.DEFAULT)
        spec = importlib.util.spec_from_file_location('lens_codex_transport', P / 'provider.py')
        self.worker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.worker)
        self.worker.P = output
        self.worker.MODEL = chosen["model"]
        self.worker.REASONING = chosen["reasoning"]

    def call(self, stage, prompt, schema, session):
        return self.worker.call('provider', stage, prompt, schema, session=session, persistent=True)


def run(input_path, output, replay_from=None, transport_factory=None, initial_session=None, model_settings_path=None):
    data = read(input_path)
    for key in ('question', 'private_context', 'starting_answer'):
        if key not in data:
            raise ValueError(f'Input requires {key}')
    validate(data['question'], eng.obj({'id': eng.TEXT, 'text': eng.TEXT, 'consumer_use': eng.TEXT}), 'question')
    validate(data['private_context'], eng.array(eng.obj({'id': eng.TEXT, 'text': eng.TEXT})), 'private_context')
    validate(data['starting_answer'], eng.submission_schema(), 'starting_answer')
    lenses = read(P / 'lenses.json')
    if tuple(x['id'] for x in lenses) != LENS_IDS:
        raise ValueError('Fixed eight-lens definition has changed order or membership')
    for lens in lenses:
        validate(lens, eng.obj({'id': eng.TEXT, 'name': eng.TEXT, 'instruction': eng.TEXT}), 'lens')
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)  # Never overwrite or silently restart.
    if transport_factory is None and replay_from is None:
        import configure
        chosen = configure.new_settings(model_settings_path)
        save(output / 'model-settings.json', chosen)
        transport_factory = configure.factory_for(output)
    save(output / 'input.json', data)
    save(output / 'lenses.json', lenses)
    versions = []
    save(output / 'versions.json', versions)
    session = initial_session
    current = data['starting_answer']
    mode = 'not_started'
    stage = None
    try:
        transport = (transport_factory(output) if transport_factory else
                     RecordedReplay(replay_from, output) if replay_from else CodexTransport(output))
        mode = transport.mode
        for index, lens in enumerate(lenses, 1):
            stage = f'{index:02}-{lens["id"]}'
            folder = output / 'probe' / stage
            folder.mkdir(parents=True)
            prompt = build_prompt(data, current, lens, session)
            schema = response_schema()
            (folder / 'prompt.txt').write_text(prompt)
            save(folder / 'schema.json', schema)
            response, returned_session = transport.call(stage, prompt, schema, session)
            if not returned_session or (session is not None and session != returned_session):
                raise ValueError('Model response came from a different interview session')
            validate(response, schema)
            save(folder / 'answer.json', response)
            revised = response['complete_answer']
            validate_question = revised['self_assessment']
            if bool(validate_question['question'].strip()) != (validate_question['choice'] == 'needs_input'):
                raise ValueError('Answer must pair needs_input with a question, or ready with no question')
            session = returned_session
            (folder / 'changes.diff').write_text(''.join(difflib.unified_diff(
                json.dumps(current, ensure_ascii=False, indent=2).splitlines(True),
                json.dumps(revised, ensure_ascii=False, indent=2).splitlines(True),
                fromfile='previous-answer', tofile='current-answer')))
            versions.append({'index': index, 'stage': stage, 'lens': lens,
                             'session': session, 'assessment': response['lens_assessment'],
                             'answer_changed': current != revised, 'answer': revised})
            save(output / 'versions.json', versions)
            current = revised  # Never use readiness or assessment to select/skip a lens.
        save(output / 'final-answer.json', current)
        result = {'completed': True, 'execution_mode': mode, 'lens_calls': len(versions),
                  'new_model_calls': 0 if mode == 'recorded_replay' else len(versions),
                  'session': session, 'final_readiness': current['self_assessment']['choice'],
                  'meaning': 'All fixed lens passes completed; this is not a claim of semantic completeness.'}
        save(output / 'result.json', result)
        return result
    except Exception as exc:
        save(output / 'result.json', {'completed': False, 'execution_mode': mode,
             'completed_lenses': len(versions), 'failed_stage': stage, 'error': str(exc)})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--settings', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--replay-from', type=Path,
                        help='Replay a saved real sequential run; makes no model calls.')
    args = parser.parse_args()
    print(json.dumps(run(args.input, args.output, args.replay_from, model_settings_path=args.settings), ensure_ascii=False))
