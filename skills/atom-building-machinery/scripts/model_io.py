import hashlib
import json
from pathlib import Path
import subprocess

MODEL = "gpt-6-astra"
EFFORT = "medium"
CODEX = "/Applications/ChatGPT.app/Contents/Resources/codex"

def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2)

def invoke(prompt, work, schema=None):
    work.mkdir(parents=True, exist_ok=False)
    (work / 'prompt.txt').write_text(prompt)
    command = [CODEX, 'exec', '--ignore-user-config', '--ephemeral',
               '--skip-git-repo-check', '--sandbox', 'read-only',
               '--model', MODEL, '-c', 'model_reasoning_effort="' + EFFORT + '"',
               '-c', 'project_doc_max_bytes=0', '-c', 'features.shell_tool=false',
               '-c', 'web_search="disabled"', '--cd', str(work), '--json',
               '--output-last-message', str(work / 'answer.txt')]
    if schema:
        save(work / 'schema.json', schema)
        command += ['--output-schema', str(work / 'schema.json')]
    command += ['-']
    save(work / 'invocation.json', {'command': command, 'model': MODEL,
         'reasoning_effort': EFFORT, 'conversation': 'fresh; no resume',
         'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest()})
    with (work / 'events.jsonl').open('x') as stdout, (work / 'stderr.txt').open('x') as stderr:
        process = subprocess.run(command, input=prompt, text=True, stdout=stdout,
                                 stderr=stderr, timeout=300)
    if process.returncode:
        raise RuntimeError('Codex failed; inspect ' + str(work / 'stderr.txt'))
    events = [json.loads(line) for line in (work / 'events.jsonl').read_text().splitlines() if line.strip()]
    tools = [e for e in events if e.get('type', '').startswith('item.') and
             e.get('item', {}).get('type') not in ('agent_message', 'reasoning', 'todo_list')]
    if tools:
        raise RuntimeError('Fresh text-only execution used an unexpected tool; isolation failed')
    if not any(e.get('type') == 'turn.completed' for e in events):
        raise RuntimeError('No completed model turn')
    return (work / 'answer.txt').read_text()
