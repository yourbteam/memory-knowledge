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
            if len(rows)>=11:raise RuntimeError('Eleven-call budget reached; no automatic additional calls')
            with log.open('a') as f:f.write(json.dumps({'number':len(rows)+1,'stage':stage,'folder':str(folder.relative_to(P)),'started':time.time()})+'\n')
            return wrapped.call(stage,prompt,schema,session)
    return Budgeted()

def main():
    verify()
    control=P/'control'
    ask.ask(P/'questions.json',P/'contexts.json',control,transport_factory=factory,model_settings_path=P/'model-settings.json')
    state=followup.load(control)
    contents=handoff.packet(control,state)
    item=state['answers'][0]
    control_verdict=handoff.check_one(control/'bounded-final-check',item,contents,factory)
    review.save(P/'control-answer.json',item['final_answer'])
    # Preserve identical original question/context; remove only eight lenses' answer changes.
    shorter=copy.deepcopy(contents)
    short_item=shorter['questions_and_answers'][0]
    short_item['final_answer']=copy.deepcopy(item['initial_answer'])
    short=P/'short';short.mkdir(exist_ok=True)
    review.save(short/'input.json',shorter)
    short_verdict=handoff.check_one(short/'bounded-final-check',short_item,shorter,factory)
    review.save(P/'short-answer.json',short_item['final_answer'])
    review.save(P/'execution-result.json',{'status':'comparison_outputs_saved','control_check':control_verdict,'short_check':short_verdict,'fresh_calls':len((P/'call-ledger.jsonl').read_text().splitlines()),'answers_changed':item['initial_answer']!=item['final_answer'],'automatic_revisions':0,'live_loop_updated':False})
    verify()
    print(json.dumps(review.read(P/'execution-result.json')),flush=True)

if __name__=='__main__':main()
