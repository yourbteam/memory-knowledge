"""Early paired visibility through read-run; replies deliberately fail, never inventing clears."""
import importlib.util
import json
import shutil
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_completed_pairs_are_visible_before_last_reader_and_report_stays_blocked(tmp_path):
    spec = importlib.util.spec_from_file_location('incremental_critic', ROOT/'skills/critique-machinery/scripts/critique.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    source = ROOT/'Tasks/critique-machinery/evidence/cases/atom-01/btm-roadmap'
    (tmp_path/'.git').mkdir()
    for name in ['page.md','state.json']:
        shutil.copyfile(source/name,tmp_path/name)
    case=json.loads((source/'case.json').read_text())
    work=tmp_path/'run'
    _,manifest=m.open_run(tmp_path/'page.md',tmp_path/'state.json',case['payload_key'],work,no_reference='No benchmark in this captured case.',no_upstream='This test concerns completion ordering.')
    last=manifest['units'][-1]['unit_id'];count=0;lock=threading.Lock();observed={};total=len(manifest['units'])*2
    def reader(root,context,focus,unit,lenses,**kwargs):
        nonlocal count
        if unit['unit_id']==last and kwargs['seat']=='reader-2':
            deadline=time.monotonic()+5
            while count<total-1 and time.monotonic()<deadline:time.sleep(.01)
            while m.matrix_status(work)['recorded_count']==0 and time.monotonic()<deadline:time.sleep(.01)
            observed.update(m.matrix_status(work))
            try:m.reporting_route(work,'report')
            except m.Refusal:observed['report_refused']=True
        with lock:count+=1
        return m.classify_reader_reply(b'',m.reader_schema(lenses),lenses,batch_id=kwargs['batch_id'],seat=kwargs['seat'],attempt=1,evidence_path=str(kwargs['evidence_root']),forced_outcome='timeout')
    m._reader_judgments=reader
    result=m.read_run(work)
    assert observed['recorded_count']>0
    assert observed['half_recorded_count']==0
    assert observed['unjudged_count']>0
    assert observed['report_refused']
    assert result['unjudged_count']==0
    assert result['status']=='partial'
    events=[json.loads(line) for line in (work/'reader-progress.jsonl').read_text().splitlines()]
    assert len(events)==total
    assert events[-1]['completed_reader_count']==total
