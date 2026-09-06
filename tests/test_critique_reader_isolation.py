"""Reader isolation regression: real captured transport, plus adversarial boundary probes.

Transport replay verifies intake admission; it is not a new semantic model experiment.
"""
import importlib.util,json,subprocess
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
# Captured real Codex reader recovery on the United Partners v7 calendar, 2026-09-06.
# Prompt SHA256 d78327b1bf7254f46007524fbf8bf54d2f0bdc2146d42eff9caca09558b32290
# Original trace SHA256 9ece1cae91fa27d9c08708ddefe9d780542d9e4a12cb510471995fa70ad1d949
# Original reply SHA256 679b03d80acef5f61ea48d1192aca81be2c7733e916e394d98d58ba27ee35545
# Embed exact transport bytes so this regression has no Tasks-directory dependency.
TRACE = '{"type":"thread.started","thread_id":"01a075e2-de8d-71f2-9500-003a9bf282c8"}\n{"type":"turn.started"}\n{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"{\\"judgments\\":[{\\"end_line\\":3,\\"findings\\":[],\\"lens\\":\\"buyer-read\\",\\"start_line\\":3,\\"verdict\\":\\"clear\\"}]}"}}\n{"type":"turn.completed","usage":{"input_tokens":55365,"cached_input_tokens":0,"cache_write_input_tokens":0,"output_tokens":790,"reasoning_output_tokens":748}}\n'
REPLY = b'{"judgments":[{"end_line":3,"findings":[],"lens":"buyer-read","start_line":3,"verdict":"clear"}]}'

def module(path):
    spec=importlib.util.spec_from_file_location('isolation_test_'+str(hash(path)),path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result

@pytest.fixture
def critic():
    return module(ROOT/'skills/critique-machinery/scripts/critique.py')

def stream(events):return '\n'.join(json.dumps(e) for e in events)+'\n'

def variants():
    events=[json.loads(l) for l in TRACE.splitlines()]
    yield 'tool',stream(events[:2]+[{'type':'item.completed','item':{'id':'tool','type':'command_execution','command':'cat ~/.codex/skills/working-agreement/SKILL.md','exit_code':0}}]+events[2:])
    yield 'unknown-item',stream(events[:2]+[{'type':'item.completed','item':{'id':'x','type':'new_capability'}}]+events[2:])
    yield 'failed',stream(events[:-1]+[{'type':'turn.failed','error':{'message':'failed'}}])
    yield 'error',stream(events[:2]+[{'type':'error','message':'failed'}]+events[2:])
    yield 'malformed',TRACE+'not json\n'
    yield 'incomplete',stream(events[:-1])
    yield 'empty',''
    yield 'non-object','[]\n'
    yield 'after-completion',TRACE+stream([{'type':'turn.started'}])
    yield 'unfinished-item',stream(events[:2]+[{'type':'item.started','item':{'id':'a','type':'reasoning'}}]+events[2:])
    yield 'repeated-completed',stream(events[:3]+events[2:])
    yield 'missing-turn-start',stream(events[:1]+events[2:])
    yield 'wrong-final',TRACE.replace('\\"clear\\"','\\"revise\\"')

BAD=list(variants())

def test_captured_trace(critic):
    assert critic.codex_reader_trace_error(TRACE,REPLY) is None

@pytest.mark.parametrize('name,trace',BAD)
def test_refusal(critic,name,trace):
    assert critic.codex_reader_trace_error(trace,REPLY)

def test_reasoning_lifecycle(critic):
    events=[json.loads(l) for l in TRACE.splitlines()]
    reasoning=[{'type':kind,'item':{'id':'reason','type':'reasoning','text':'Check supplied evidence'}} for kind in ['item.started','item.updated','item.completed']]
    assert critic.codex_reader_trace_error(stream(events[:2]+reasoning+events[2:]),REPLY) is None

@pytest.mark.parametrize('trace,expected',[(TRACE,'valid'),(BAD[0][1],'malformed'),('', 'malformed')])
def test_reader_transport_admission(critic,tmp_path,monkeypatch,trace,expected):
    # Replays the real successful reply/trace through the actual reader intake path;
    # this is boundary proof, not a new semantic experiment.
    projection=tmp_path/'projection';(projection/'scripts').mkdir(parents=True)
    (projection/'client-model-policy.json').write_text(json.dumps({'required_runtime':'codex exec','fail_closed':True}))
    monkeypatch.setattr(critic,'__file__',str(projection/'scripts/critique.py'))
    monkeypatch.setattr(critic.shutil,'which',lambda name:'/captured/codex')
    def run(argv,**kwargs):
        assert '--json' in argv and 'skills.include_instructions=false' in argv
        assert '--ignore-user-config' in argv and '--ignore-rules' in argv
        Path(argv[argv.index('--output-last-message')+1]).write_bytes(REPLY)
        return subprocess.CompletedProcess(argv,0,trace,'captured stderr')
    monkeypatch.setattr(critic,'run_reader_process',run)
    unit={'unit_id':'captured-calendar','text':'# Captured calendar\n\nThe roadmap schedules future assets across the twelve month calendar.'}
    evidence=tmp_path/'evidence'
    result=critic._reader_judgments(tmp_path,'Captured roadmap','Judge buyer reading',unit,['buyer-read'],evidence_root=evidence,batch_id='captured-calendar',seat='reader-2')
    assert result['outcome']==expected
    assert (evidence/'reader.stdout.txt').read_text()==trace
    assert (evidence/'reader.reply.txt').read_bytes()==REPLY
    assert (evidence/'reader-response.json').exists()==(expected=='valid')

def test_genuine_invocation_controls(critic,tmp_path):
    argv=critic.build_reader_argv(['codex','exec'],'/captured/codex',{},
        tmp_path/'schema.json',tmp_path/'reply.json',tmp_path,'Reader instructions')
    assert argv[:2]==['/captured/codex','exec']
    assert '--json' in argv and '--ignore-user-config' in argv and '--ignore-rules' in argv
    assert argv[argv.index('--sandbox')+1]=='read-only'
    overrides=[argv[i+1] for i,value in enumerate(argv[:-1]) if value=='-c']
    assert 'project_doc_max_bytes=0' in overrides
    assert 'skills.include_instructions=false' in overrides
    assert 'web_search="disabled"' in overrides
    disabled={argv[i+1] for i,value in enumerate(argv[:-1]) if value=='--disable'}
    assert disabled=={'shell_tool','plugins','apps','skill_search','hooks','multi_agent',
                      'image_generation','browser_use','computer_use','workspace_dependencies'}
    assert '--model' not in argv and '-m' not in argv
    assert argv[-1]=='-'


def test_embedded_capture_hashes():
    import hashlib
    assert hashlib.sha256(TRACE.encode()).hexdigest()=='9ece1cae91fa27d9c08708ddefe9d780542d9e4a12cb510471995fa70ad1d949'
    assert hashlib.sha256(REPLY).hexdigest()=='679b03d80acef5f61ea48d1192aca81be2c7733e916e394d98d58ba27ee35545'
