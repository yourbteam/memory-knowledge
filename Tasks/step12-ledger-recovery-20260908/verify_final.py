from pathlib import Path
import sys,json,hashlib,argparse,contextlib,io,shutil
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root))
from scripts import work_memory as w,blocker_catalog as bc
out=Path(__file__).resolve().parent/'final-replay';out.mkdir(exist_ok=True)
lines=w.LEDGER.read_bytes().splitlines(keepends=True);cut=next(i for i,line in enumerate(lines) if json.loads(line)['event_id']=='9efdc65a-0953-4ae5-a1c6-071c7f9df710');original=b''.join(lines[:cut])
receipt_source=w.RECEIPT_ROOT/'step12-two-clients-live'/'classification.json'
receipt_target=out/'receipts/step12-two-clients-live/classification.json';receipt_target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(receipt_source,receipt_target)
w.LEDGER=out/'events.jsonl';w.LEDGER.write_bytes(original);w.BLOCKER_VIEW=out/'BLOCKERS.md';w.RECEIPT_ROOT=out/'receipts'
old='14247c7c-fa77-4ef8-a135-1e22c48ffd75';b='blk-79460505a7c16ff9bc2af9c9';c='a12d8d76-44b5-4732-8e0b-c38bb2ffb0a6'
selection=w.cmd_select_successor(argparse.Namespace(predecessor_run_id=old));(out/'selection.json').write_text(json.dumps(selection))
# Use the actual CLI argument parser and handlers; only storage locations are isolated.
def call(module,args):
 s=io.StringIO()
 with contextlib.redirect_stdout(s):rc=module.main(args)
 value=json.loads(s.getvalue());assert rc in (None,0),value;return value
start=call(w,['run-start','--task-id','step12-two-clients-live']);run=start['run_id']
v=call(w,['verify','--run-id',run,'--outcome','passed','--quality','same-path','--evidence','Hash-verified original canonical checkpoint proof and both accepted exports; final public CLI replay checks append-only correction closure.','--blocker-id',b,'--correction-id',c])
for status in ['verified','closed']:
 args=['transition','--run-id',run,'--blocker-id',b,'--to-status',status,'--verification-event-id',v['event_id']]
 if status=='closed':args+=['--remaining-work','none']
 call(bc,args)
call(w,['run-close','--run-id',run,'--result','passed'])
assert w.LEDGER.read_bytes().startswith(original)
rows,h=w.load_ledger();last=next(e for e in reversed(rows) if e.get('blocker_id')==b);assert last['to_status']=='closed' and last['remaining_work']=='none'
try:w.cmd_select_successor(argparse.Namespace(predecessor_run_id=old));raise AssertionError('Closed correction selected again')
except w.WorkMemoryError as e:assert str(e)=='successor-correction-not-awaiting-verification'
result={'passed':True,'source_prefix_sha256':hashlib.sha256(original).hexdigest(),'source_prefix_preserved':True,'original_predecessor':old,'new_successor':run,'original_correction':c,'blocker_status':'closed','remaining_work':'none','run_result':'passed','already_closed_reselection':'rejected','final_code_sha256':hashlib.sha256((root/'scripts/work_memory.py').read_bytes()).hexdigest(),'ledger_sha256':h}
(out/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
