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
            if len(rows)>=12:raise RuntimeError('Twelve-call budget reached; no automatic additional calls')
            with log.open('a') as f:f.write(json.dumps({'number':len(rows)+1,'stage':stage,'folder':str(folder.relative_to(P)),'started':time.time()})+'\n')
            return wrapped.call(stage,prompt,schema,session)
    return Budgeted()

def main():
    import checkpoint
    verify()
    old=review.read(P/'previous.json');decisions=review.read(P/'selection.json');template=review.read(P/'template.json')
    selected=review.read(P/'experiment.json')['question_ids']
    sources=[{'id':k,'text':json.dumps(review.read(P/(k+'.json')),ensure_ascii=False,separators=(',',':'))} for k in ['previous','assessment','goal']]
    out=P/'combined';out.mkdir(exist_ok=True)
    items=[];contexts={};questions=[]
    for entry in old['questions']:
        q=copy.deepcopy(entry['question']);qid=q['id'];context=copy.deepcopy(sources)
        if qid in selected:
            q['text']=template['update_instruction']+'\nOriginal question: '+q['text']
            q['consumer_use']+=' '+template['consumer_instruction']
            context.append({'id':'update_reason','text':decisions[qid]['reason']})
            prompt=review.eng.producer_prompt(review.eng.new_run(q,context))
            answer,session=checkpoint.call(P/'updates'/qid,'00-direct',prompt,review.eng.submission_schema(),factory)
        elif qid=='current_position':
            answer=review.read(P/'validated-current-position.json');session=entry['session']
        else:answer=entry['final_answer'];session=entry['session']
        item={'question':q,'initial_answer':answer,'final_answer':answer,'session':session,'execution_mode':'live' if qid in selected else 'preserved_saved_answer'}
        items.append(item);contexts[qid]=context;questions.append(q)
        review.save(P/'partial-answers.json',items)
    review.save(out/'questions.json',{'id':'extended-incremental-probe','questions':questions});review.save(out/'contexts.json',contexts)
    contents=handoff.packet(out,{'answers':items,'history':[]});review.save(out/'check-input.json',contents)
    checks={}
    for item in items:
        qid=item['question']['id']
        if qid in selected:
            checks[qid]=handoff.check_one(P/'checks'/qid,item,contents,factory)
            review.save(P/'checks.json',checks)
    review.save(P/'combined-answers.json',{'status':'validation_only','questions':items,'checks':checks,'live_loop_updated':False})
    review.save(P/'execution-result.json',{'fresh_calls':len((P/'call-ledger.jsonl').read_text().splitlines()),'checks':checks,'automatic_revisions':0,'live_loop_updated':False})
    verify();print(json.dumps(review.read(P/'execution-result.json')),flush=True)

if __name__=='__main__':main()
