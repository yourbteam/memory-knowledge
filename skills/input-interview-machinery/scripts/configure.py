"""Create/edit reusable question templates and model settings without model calls."""
import argparse
import json
from pathlib import Path
import re

P=Path(__file__).resolve().parent
DEFAULT={'provider':'codex','model':'gpt-5.5','reasoning':'high'}


def read(path):return json.loads(Path(path).read_text())


def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    temporary.replace(path)


def question(value):
    if not isinstance(value,dict) or set(value)!={'id','text','consumer_use'}:
        raise ValueError('Question requires id, text and consumer_use')
    if any(not isinstance(v,str) or not v.strip() for v in value.values()):
        raise ValueError('Question fields must be nonempty strings')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',value['id']):
        raise ValueError('Question ID must use letters, digits, underscores or hyphens')


def template(value):
    if not isinstance(value,dict) or set(value)!={'id','questions'}:
        raise ValueError('Template requires id and questions')
    if not isinstance(value['id'],str) or not value['id'].strip() or not isinstance(value['questions'],list):
        raise ValueError('Template needs a nonempty ID and a question list')
    for q in value['questions']:question(q)
    ids=[q['id'] for q in value['questions']]
    if len(ids)!=len(set(ids)):raise ValueError('Question IDs must be unique')
    return value


def settings(value):
    if not isinstance(value,dict) or set(value)!={'provider','model','reasoning'}:
        raise ValueError('Settings require provider, model and reasoning')
    if value['provider']!='codex':raise ValueError('Only the Codex CLI adapter is implemented')
    if any(not isinstance(v,str) or not v.strip() for v in value.values()):
        raise ValueError('Settings must be nonempty strings')
    return dict(value)


def new_settings(path=None):
    return settings(read(path or P/'model-settings.json'))


def run_settings(root):
    file=Path(root)/'model-settings.json'
    # Older runs were made before configuration and are known to use these fixed settings.
    return settings(read(file)) if file.exists() else dict(DEFAULT)


def factory_for(root):
    import run as review
    frozen=run_settings(root)
    return lambda output:review.CodexTransport(output, frozen)


def editable(path):
    if (Path(path).parent/'session-binding.json').exists() or (Path(path).parent/'followup-state.json').exists():
        raise ValueError('This is an interview snapshot; edit the reusable template/settings instead')


def change(path,operation,identifier=None,value=None,order=None):
    path=Path(path);editable(path)
    if operation=='create':
        if path.exists():raise ValueError('Template already exists')
        data={'id':identifier,'questions':[]}
    else:
        data=template(read(path))
        ids=[q['id'] for q in data['questions']]
        if operation=='add':
            question(value)
            if value['id'] in ids:raise ValueError('Question ID already exists')
            data['questions'].append(value)
        elif operation in ('edit','remove'):
            if identifier not in ids:raise ValueError('Question ID not found')
            index=ids.index(identifier)
            if operation=='remove':data['questions'].pop(index)
            else:
                question(value)
                if value['id']!=identifier:raise ValueError('Editing preserves the stable question ID')
                data['questions'][index]=value
        elif operation=='reorder':
            if not isinstance(order,list) or len(order)!=len(ids) or set(order)!=set(ids):
                raise ValueError('Order must contain every question ID exactly once')
            by_id={q['id']:q for q in data['questions']}
            data['questions']=[by_id[q] for q in order]
        else:raise ValueError('Unknown template operation')
    template(data);write(path,data);return data


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation',choices=['create','show','add','edit','remove','reorder','model'])
    p.add_argument('--file',type=Path,required=True)
    p.add_argument('--id');p.add_argument('--question',type=Path);p.add_argument('--order',type=Path)
    p.add_argument('--provider',default='codex');p.add_argument('--model');p.add_argument('--reasoning',default='high')
    a=p.parse_args()
    if a.operation=='show':result=read(a.file)
    elif a.operation=='model':
        editable(a.file);result=settings({'provider':a.provider,'model':a.model,'reasoning':a.reasoning});write(a.file,result)
    else:result=change(a.file,a.operation,a.id,read(a.question) if a.question else None,read(a.order) if a.order else None)
    print(json.dumps(result,ensure_ascii=False))


def incremental_policy(root):
    """Absent policy preserves legacy/full interviews, including interrupted runs."""
    import hashlib
    file = Path(root)/'incremental-policy.json'
    if not file.exists(): return None
    policy = read(file)
    if policy.get('mode') != 'direct-update':
        raise ValueError('Unknown incremental policy; expected direct-update')
    previous = Path(root)/'incremental-previous.json'
    if hashlib.sha256(previous.read_bytes()).hexdigest() != policy['previous_sha256']:
        raise ValueError('Incremental previous answers changed; restore the frozen snapshot')
    return policy


def refine(root, input_path, output, **kwargs):
    """Incremental answers already received their model call; full intake keeps all lenses."""
    import run as review
    if incremental_policy(root) is None:
        return review.run(input_path, output, **kwargs)
    data = read(input_path)
    answer = data['starting_answer']
    review.validate(answer, review.eng.submission_schema())
    choice = answer['self_assessment']
    if bool(choice['question'].strip()) != (choice['choice'] == 'needs_input'):
        raise ValueError('Answer must pair needs_input with a question, or ready with no question')
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    for name, value in [('input.json', data), ('final-answer.json', answer)]:
        if (output/name).exists() and read(output/name) != value:
            raise ValueError('Cannot reuse changed direct-update output: '+name)
        review.save(output/name, value)
    result = {'completed':True, 'execution_mode':'direct-update', 'lens_calls':0,
              'new_model_calls':0, 'session':kwargs.get('initial_session'),
              'final_readiness':choice['choice'],
              'meaning':'Direct incremental answer preserved; final dependency review still required.'}
    review.save(output/'result.json', result)
    return result
