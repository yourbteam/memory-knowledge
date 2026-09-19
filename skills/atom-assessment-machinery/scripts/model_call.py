"""Bundled Codex transport from atom selection; schema supplied by the caller."""
import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path
from schema_check import validate
SCHEMA = {}

def read(path):
    return json.loads(path.read_text())


def save(path, data):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def answer_valid(value):
    validate(value, SCHEMA)


def event(stage, state):
    print(json.dumps({'stage': stage, 'event': state, 'time': time.time()}), flush=True)


def completed_attempt(directory):
    """Recover a completed provider call even if Python stopped before checkpointing."""
    if not (directory / 'answer.json').exists() or not (directory / 'events.jsonl').exists():
        return None
    events = []
    for line in (directory / 'events.jsonl').read_text().splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # Interrupted event line is not completion evidence.
    if any(e.get('item', {}).get('type') in {'command_execution', 'mcp_tool_call', 'web_search'} for e in events):
        raise ValueError('Unexpected tool execution in model call; inspect ' + str(directory))
    finals = [e for e in events if e.get('type') == 'turn.completed']
    sessions = [e['thread_id'] for e in events if e.get('type') == 'thread.started']
    if not finals or not sessions:
        return None
    answer = read(directory / 'answer.json')
    answer_valid(answer)
    return answer, sessions[0], finals[-1].get('usage')


def invoke(directory, prompt, settings):
    cli = shutil.which(settings['cli'])
    if not cli:
        raise ValueError('Codex CLI not found: ' + settings['cli'])
    command = [cli, 'exec', '--ignore-user-config', '--skip-git-repo-check',
               '--sandbox', 'read-only', '--model', settings['model'], '-c',
               'model_reasoning_effort=' + json.dumps(settings['reasoning']),
               '-c', 'project_doc_max_bytes=0', '-c', 'web_search="disabled"',
               '-c', 'features.shell_tool=false', '--cd', str(directory), '--json',
               '--output-schema', str(directory / 'schema.json'),
               '--output-last-message', str(directory / 'answer.json'), '-']
    save(directory / 'invocation.json', {'command': command, 'model': settings['model'],
                                      'reasoning': settings['reasoning']})
    began = time.monotonic()
    with (directory / 'events.jsonl').open('w') as out, (directory / 'stderr.txt').open('w') as err:
        proc = subprocess.run(command, input=prompt, text=True, stdout=out, stderr=err,
                              timeout=settings['timeout_seconds'])
    result = completed_attempt(directory)
    if proc.returncode or result is None:
        raise RuntimeError('Provider did not complete successfully. Inspect ' + str(directory))
    answer, session, usage = result
    save(directory / 'completion.json', {'session': session, 'usage': usage,
                                       'elapsed_seconds': time.monotonic() - began})
    return answer


def one_call(run, stage, prompt, state, settings):
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
    saved = state['stages'].get(stage)
    if saved:
        directory = run / saved['attempt']
        if saved['prompt_sha256'] != prompt_hash or digest(directory / 'answer.json') != saved['answer_sha256']:
            raise ValueError('Saved stage changed: ' + stage + '. Use a new run for changed inputs.')
        answer = read(directory / 'answer.json')
        answer_valid(answer)
        return answer
    parent = run / 'calls' / stage
    parent.mkdir(parents=True, exist_ok=True)
    attempts = sorted(parent.glob('attempt-*'))
    answer = None
    for directory in reversed(attempts):
        if (directory / 'prompt.txt').read_text() != prompt:
            raise ValueError('Attempt prompt changed: ' + stage)
        recovered = completed_attempt(directory)
        if recovered:
            answer = recovered[0]
            break
    if answer is None and attempts:
        raise RuntimeError('Incomplete saved call; inspect before authorizing a new run: ' + str(parent))
    if answer is None:
        directory = parent / ('attempt-%03d' % (len(attempts) + 1))
        directory.mkdir()
        (directory / 'prompt.txt').write_text(prompt)
        save(directory / 'schema.json', SCHEMA)
        state.update(status='running', active_stage=stage)
        save(run / 'state.json', state)
        event(stage, 'started')
        answer = invoke(directory, prompt, settings)
    state['stages'][stage] = {'attempt': str(directory.relative_to(run)),
                              'prompt_sha256': prompt_hash, 'answer_sha256': digest(directory / 'answer.json')}
    save(run / 'state.json', state)
    event(stage, 'completed')
    return answer
