"""One owner-approved, source-bound assignment correction; preserve the original."""
import json
import sys
from pathlib import Path

P = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(P))
import selection_preparation as prep

state = prep.read(P / 'live/state.json')
sys.path.insert(0, str(Path(state['skills']) / 'input-interview-machinery/scripts'))
import checkpoint
import run as provider

root = Path(state['cycle']).parent / 'selection-preparation-attempt3'
original = root / 'calls/03/attempts/0001/answer.json'
source = root / 'baseline/references/0/builder-live-01/candidate/test.php'
line = next(x for x in source.read_text().splitlines() if '$client=Mockery::mock' in x)
folder = root / 'calls/03/correction'
packet = {'assignment': prep.read(original), 'errors': [
    {'field': 'allowed_paths', 'value': 'experiment/results/',
     'correction': 'Remove this directory from the code file list. Retain its role as the runtime output directory in execution_plan. Do not add or change files.'},
    {'field': 'source_basis', 'source_path': 'references/0/builder-live-01/candidate/test.php',
     'exact_source_line': line, 'correction': 'Use the exact source line. JSON escaping must decode to the actual single backslash.'}]}
prompt = ('Correct only the two listed validation errors in this saved assignment. '
          'Preserve every other value, case, expectation and instruction exactly. '
          'Return the complete corrected assignment. No tools.\n' + json.dumps(packet, ensure_ascii=False))
settings = {'provider': 'codex', 'model': 'gpt-6-astra', 'reasoning': 'medium'}
answer, _ = checkpoint.call(folder, 'repair-assignment', prompt, prep.SCHEMA,
                            lambda p: provider.CodexTransport(p, settings))
step = prep.read(folder / 'step.json')
result = folder / step['answer_file']
prep.save(folder / 'handoff.json', {'original': prep.ref(original), 'source': prep.ref(source), 'answer': prep.ref(result)})
print(json.dumps({'action': 'correction_saved', 'handoff': str(folder / 'handoff.json')}))
