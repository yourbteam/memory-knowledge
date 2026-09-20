"""Paired real-phase comparison; no live-loop mutation or automatic repair."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import time
P=Path(__file__).resolve().parent
sys.path.insert(0,str(P/'runtime'))
import ask,configure,followup,handoff
import run as review

def verify():
    for name,digest in review.read(P/'manifest.json')['files'].items():
        if hashlib.sha256((P/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Frozen comparison input changed: '+name)

def factory(folder):
    wrapped=review.CodexTransport(folder,review.read(P/'model-settings.json'))
    class Budgeted:
        mode='live'
        def call(self,stage,prompt,schema,session):
            log=P/'call-ledger.jsonl'
            rows=log.read_text().splitlines() if log.exists() else []
            if len(rows)>=2:raise RuntimeError('Two-call budget reached; no automatic additional calls')
            with log.open('a') as f:f.write(json.dumps({'number':len(rows)+1,'stage':stage,'folder':str(folder.relative_to(P)),'started':time.time()})+'\n')
            return wrapped.call(stage,prompt,schema,session)
    return Budgeted()

def main():
    import checkpoint
    verify()
    out=P/'short';out.mkdir(exist_ok=True)
    questions=review.read(P/'questions.json');contexts=review.read(P/'contexts.json')
    question=questions['questions'][0]
    state=review.eng.new_run(question,contexts[question['id']])
    answer,session=checkpoint.call(out/'initial','00-direct',review.eng.producer_prompt(state),review.eng.submission_schema(),factory)
    review.validate(answer,review.eng.submission_schema())
    for name,value in [('questions.json',questions),('contexts.json',contexts)]:review.save(out/name,value)
    item={'question':question,'initial_answer':answer,'final_answer':answer,'session':session,'execution_mode':'live'}
    contents=handoff.packet(out,{'answers':[item],'history':[]})
    review.save(out/'check-input.json',contents)
    verdict=handoff.check_one(out/'bounded-final-check',item,contents,factory)
    review.save(P/'short-answer.json',answer)
    review.save(P/'execution-result.json',{'status':'outputs_saved','short_check':verdict,'fresh_calls':len((P/'call-ledger.jsonl').read_text().splitlines()),'automatic_revisions':0,'live_loop_updated':False})
    verify()
    print(json.dumps(review.read(P/'execution-result.json')),flush=True)

if __name__=='__main__':main()
