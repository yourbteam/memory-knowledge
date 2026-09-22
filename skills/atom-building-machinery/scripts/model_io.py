import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

MODEL = "gpt-6-astra"
EFFORT = "medium"
CODEX = "/Applications/ChatGPT.app/Contents/Resources/codex"
DEFAULT_TIMEOUT_SECONDS = 300
TIMEOUT_ENV = "ATOM_BUILDER_MODEL_TIMEOUT_SECONDS"
AUTH_FILE = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "auth.json"


def timeout_seconds():
    raw = os.environ.get(TIMEOUT_ENV)
    if raw is None:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(TIMEOUT_ENV + " must be a whole number") from exc
    if value < 60 or value > 1800:
        raise ValueError(TIMEOUT_ENV + " must be between 60 and 1800 seconds")
    return value

def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2)

def invoke(prompt, work, schema=None):
    timeout = timeout_seconds()
    work = Path(work).resolve()
    work.mkdir(parents=True, exist_ok=False)
    (work / 'prompt.txt').write_text(prompt)
    if not AUTH_FILE.is_file():
        raise RuntimeError('Codex authentication file is unavailable for isolated execution')
    with tempfile.TemporaryDirectory(prefix='atom-builder-codex-', dir='/private/tmp') as isolated:
        isolated_root = Path(isolated)
        isolated_home = isolated_root / 'home'
        isolated_workspace = isolated_root / 'workspace'
        isolated_home.mkdir()
        isolated_workspace.mkdir()
        isolated_auth = isolated_home / 'auth.json'
        shutil.copyfile(AUTH_FILE, isolated_auth)
        isolated_auth.chmod(0o600)
        command = [CODEX, 'exec', '--ignore-user-config', '--ignore-rules', '--ephemeral',
                   '--skip-git-repo-check', '--sandbox', 'read-only',
                   '--model', MODEL, '-c', 'model_reasoning_effort="' + EFFORT + '"',
                   '-c', 'project_doc_max_bytes=0', '-c', 'features.shell_tool=false',
                   '-c', 'web_search="disabled"',
                   '-c', 'suppress_unstable_features_warning=true',
                   '--cd', str(isolated_workspace), '--json',
                   '--output-last-message', str(work / 'answer.txt')]
        if schema:
            save(work / 'schema.json', schema)
            command += ['--output-schema', str(work / 'schema.json')]
        command += ['-']
        save(work / 'invocation.json', {'command': command, 'model': MODEL,
             'reasoning_effort': EFFORT, 'conversation': 'fresh; no resume',
             'isolation': 'temporary CODEX_HOME and non-project workspace; auth only',
             'timeout_seconds': timeout,
             'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest()})
        environment = os.environ.copy()
        environment['CODEX_HOME'] = str(isolated_home)
        with (work / 'events.jsonl').open('x') as stdout, (work / 'stderr.txt').open('x') as stderr:
            process = subprocess.run(command, input=prompt, text=True, stdout=stdout,
                                     stderr=stderr, timeout=timeout, env=environment)
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
