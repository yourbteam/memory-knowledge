"""Codex CLI adapter extracted from the proven transport; settings supplied per interview."""
import json,subprocess,threading,time,difflib
from pathlib import Path
import interview as eng
P=Path(__file__).resolve().parent
CLI='/Applications/ChatGPT.app/Contents/Resources/codex'
LOCK=threading.Lock()
MODEL="gpt-5.5"
REASONING="high"
import hashlib

def read(p):
    return json.loads(p.read_text())

def save(p, x):
    p.write_text(json.dumps(x, ensure_ascii=False, indent=2) + '\n')

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def log(**x):
    x['time'] = time.time()
    with LOCK:
        with (P / 'events.jsonl').open('a') as f:
            f.write(json.dumps(x) + '\n')
        print(json.dumps(x), flush=True)

def call(q, stage, prompt, schema, session=None, persistent=False):
    d = P / q / stage
    d.mkdir(parents=True)
    (d / 'prompt.txt').write_text(prompt)
    save(d / 'schema.json', schema)
    cmd = [CLI, 'exec', '--ignore-user-config', '--skip-git-repo-check', '--sandbox', 'read-only', '--model', MODEL, '-c', 'model_reasoning_effort=' + json.dumps(REASONING), '-c', 'project_doc_max_bytes=0', '-c', 'web_search="disabled"', '-c', 'features.shell_tool=false', '--cd', str(P)]
    if session:
        cmd += ['resume', session]
    elif not persistent:
        cmd += ['--ephemeral']
    cmd += ['--json', '--output-schema', str(d / 'schema.json'), '--output-last-message', str(d / 'answer.json'), '-']
    save(d / 'invocation.json', {'command': cmd, 'model': MODEL, 'reasoning': REASONING, 'session': session, 'prompt_sha256': sha(d / 'prompt.txt')})
    log(case=q, stage=stage, event='started')
    started = time.time()
    with (d / 'events.jsonl').open('w') as out, (d / 'stderr.txt').open('w') as err:
        proc = subprocess.run(cmd, input=prompt, text=True, stdout=out, stderr=err, timeout=300)
    if proc.returncode:
        raise RuntimeError(f'{stage}: CLI exit {proc.returncode}')
    events = [json.loads(l) for l in (d / 'events.jsonl').read_text().splitlines() if l.strip()]
    completed = [e for e in events if e['type'] == 'turn.completed']
    ids = [e['thread_id'] for e in events if e['type'] == 'thread.started']
    if not completed or not ids:
        raise RuntimeError(stage + ': missing completion/session')
    if session and ids[0] != session:
        raise RuntimeError('Resumed wrong session')
    if any((e.get('item', {}).get('type') == 'command_execution' for e in events)):
        raise RuntimeError('Unexpected tool execution')
    answer = read(d / 'answer.json')
    save(d / 'completion.json', {'session': ids[0], 'elapsed': time.time() - started, 'usage': completed[-1].get('usage'), 'completed': True})
    log(case=q, stage=stage, event='completed')
    return (answer, ids[0])
