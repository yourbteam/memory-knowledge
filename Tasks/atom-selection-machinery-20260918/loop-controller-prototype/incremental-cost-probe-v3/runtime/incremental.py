"""Incremental template: select affected original questions, reuse intake, merge by ID."""
import argparse
import copy
import fcntl
import hashlib
import json
from pathlib import Path
import checkpoint
import configure
import run as review

P = Path(__file__).resolve().parent


def ref(path):
    return {'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def prepare(args):
    previous = review.read(args.previous)
    questions = previous.get('questions', [])
    ids = [x['question']['id'] for x in questions]
    if previous.get('status', 'completed') != 'completed' or not ids or len(ids) != len(set(ids)):
        raise ValueError('Supply a completed answer set with unique original question IDs.')
    for item in questions:
        configure.question(item['question'])
        review.validate(item['final_answer'], review.eng.submission_schema())
        if item['final_answer']['self_assessment']['choice'] != 'ready':
            raise ValueError('Previous answers must be ready.')
    role = 'decision' if getattr(args, 'decision', None) else 'assessment'
    update = review.read(getattr(args, role))
    expected = 'owner_decision_resolution' if role == 'decision' else 'atom_assessment'
    if update.get('kind') != expected:
        raise ValueError('Expected update kind: ' + expected)
    goal = review.read(args.goal)
    bindings = {k:ref(getattr(args,k)) for k in ['previous',role,'goal']}
    args.run.mkdir(parents=True, exist_ok=False)
    for name, value in [('previous.json',previous),(role+'.json',update),('goal.json',goal),
                        ('model-settings.json',configure.new_settings(args.settings)),
                        ('template.json',review.read(args.template)),('bindings.json',bindings)]:
        review.save(args.run/name,value)
    if role == 'decision':
        template = review.read(args.run/'template.json')
        for key in ['selection_question', 'update_instruction']:
            template[key] = template[key].replace('new assessment', 'owner decision and its recorded evidence').replace('supplied assessment', 'supplied owner decision')
        template['selection_question'] += ' An owner decision is not a completed build or a fresh inspection of product functionality. It can resolve the specific choice it states, not unrelated product gaps.'
        review.save(args.run/'template.json', template)
    files = {p.name:ref(p)['sha256'] for p in args.run.glob('*.json')}
    review.save(args.run/'manifest.json',{'files':files})
    return args.run.resolve()


def inputs(root):
    for name, expected in review.read(root/'manifest.json')['files'].items():
        if ref(root/name)['sha256'] != expected:
            raise ValueError('Frozen input changed: '+name)
    role = 'decision' if 'decision.json' in review.read(root/'manifest.json')['files'] else 'assessment'
    return {k:review.read(root/(k+'.json')) for k in ['previous',role,'goal']}


def plan(root, packet, factory):
    template = review.read(root/'template.json')
    fields = {q['question']['id']:review.eng.obj({
        'decision':{'type':'string','enum':['keep','update']}, 'reason':review.eng.TEXT})
        for q in packet['previous']['questions']}
    schema = review.eng.obj(fields)
    prompt = template['selection_question']+'\n'+json.dumps(packet,ensure_ascii=False,separators=(',',':'))
    response, session = checkpoint.call(root/'selection','affected-questions',prompt,schema,factory)
    review.validate(response,schema)
    if any(not row['reason'].strip() for row in response.values()):
        raise ValueError('Every question needs a reason for keep or update.')
    review.save(root/'selection.json',response)
    return response


def merge(root, packet, decisions, updated=None):
    role = 'decision' if 'decision' in packet else 'assessment'
    old=packet['previous'];result=copy.deepcopy(old)
    selected=[q['question']['id'] for q in old['questions'] if decisions[q['question']['id']]['decision']=='update']
    if selected:
        if updated is None or updated.get('status')!='completed':
            raise ValueError('Selected interview has not completed.')
        if [x['question']['id'] for x in updated['questions']]!=selected:
            raise ValueError('Updated answers do not match selected original question IDs.')
    changes=[]; replacements={x['question']['id']:x for x in (updated or {}).get('questions',[])}
    for index,original in enumerate(old['questions']):
        qid=original['question']['id']
        if qid not in replacements:continue
        item=replacements[qid]
        if item['answer_status']!='answered' or item['final_answer']['self_assessment']['choice']!='ready':
            raise ValueError('Selected answer remains unresolved: '+qid)
        if original['final_answer']==item['final_answer']:continue
        replacement=copy.deepcopy(item)
        replacement['question']=copy.deepcopy(original['question'])
        replacement['effective_question']=copy.deepcopy(original.get('effective_question',original['question']))
        replacement['incremental_provenance']={'interview':ref(root/'interview/handoff.json'),
            ('owner_decision' if role == 'decision' else role):review.read(root/'bindings.json')[role], 'decision':decisions[qid],
            'incremental_question':item['question']}
        result['questions'][index]=replacement
        changes.append({'question_id':qid,'evidence':replacement['incremental_provenance']})
    bindings=review.read(root/'bindings.json');snapshot=copy.deepcopy(old.get('snapshot',{}))
    snapshot.update(version=snapshot.get('version',0)+1,kind='incremental_update',previous_snapshot=bindings['previous'],
        updates=changes,selection=ref(root/'selection.json'),review_scope=selected,
        context_policy='Unchanged entries preserved. Changed answers copied verbatim from the incremental interview; no new product state inferred by code.')
    snapshot.pop('assessment', None)
    snapshot.pop('decision', None)
    snapshot[role] = bindings[role]
    result['snapshot']=snapshot
    result['cross_question_review']='selected_questions_only' if selected else 'no_questions_selected'
    result['checked_snapshot']=(updated or {}).get('checked_snapshot')
    if updated: result['model_settings']=updated['model_settings']
    result['status']='completed'
    destination=root/'current-answers.json'
    if destination.exists() and review.read(destination)!=result:
        raise ValueError('Existing completed snapshot differs; start a new incremental run.')
    review.save(destination,result)
    return {'action':'complete','handoff':str(destination),'updated_question_ids':[x['question_id'] for x in changes],
            'preserved_answers':len(old['questions'])-len(changes)}


def advance(root, plan_only=False, factory=None):
    import input_interview
    with (root/'incremental.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        packet=inputs(root);factory=factory or configure.factory_for(root)
        decisions=plan(root,packet,factory)
        selected=[q for q in packet['previous']['questions'] if decisions[q['question']['id']]['decision']=='update']
        if not selected:return merge(root,packet,decisions)
        if plan_only:return {'action':'updates_selected','selection':str(root/'selection.json'),
                             'question_ids':[q['question']['id'] for q in selected]}
        template=review.read(root/'template.json')
        questions={'id':'incremental','questions':[]};contexts={}
        source_list=[{'id':k,'text':json.dumps(v,ensure_ascii=False,separators=(',',':'))} for k,v in packet.items()]
        for item in selected:
            q=item['question'];qid=q['id']
            questions['questions'].append({'id':qid,'text':template['update_instruction']+'\nOriginal question: '+q['text'],
                'consumer_use':q['consumer_use']+' '+template['consumer_instruction']})
            contexts[qid]=source_list+[{'id':'update_reason','text':decisions[qid]['reason']}]
        for name,value in [('questions.json',questions),('contexts.json',contexts)]:
            path=root/name
            if path.exists() and review.read(path)!=value:raise ValueError('Incremental inputs changed.')
            review.save(path,value)
        run=root/'interview'
        if (run/'questions.json').exists():
            action=input_interview.main(['resume','--run',str(run)],factory)
        else:
            action=input_interview.main(['start','--questions',str(root/'questions.json'),'--contexts',str(root/'contexts.json'),
                '--settings',str(root/'model-settings.json'),'--run',str(run)],factory)
        if action['action']!='complete':
            return {**action,'incremental_run':str(root),'interview_run':str(run),
                    'continuation':'Handle this request through the existing interview commands, then incremental continue.'}
        return merge(root,packet,decisions,review.read(run/'handoff.json'))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='op',required=True)
    start=sub.add_parser('start')
    for name in ['previous','goal']:start.add_argument('--'+name,type=Path,required=True)
    source=start.add_mutually_exclusive_group(required=True)
    source.add_argument('--assessment',type=Path)
    source.add_argument('--decision',type=Path)
    start.add_argument('--template',type=Path,default=P/'incremental-template.json')
    start.add_argument('--settings',type=Path)
    start.add_argument('--prepare-only',action='store_true')
    cont=sub.add_parser('continue')
    for command in [start,cont]:
        command.add_argument('--run',type=Path,required=True);command.add_argument('--plan-only',action='store_true')
    args=parser.parse_args(argv);root=prepare(args) if args.op=='start' else args.run.resolve()
    result={'action':'prepared','run':str(root)} if getattr(args,'prepare_only',False) else advance(root,args.plan_only)
    print(json.dumps(result,ensure_ascii=False));return result


if __name__=='__main__':main()
