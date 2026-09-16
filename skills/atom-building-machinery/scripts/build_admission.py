"""Bind supplied owner authorization to one build contract, without selecting work.

An approval source records authorization already given by the owner/calling workflow.
It is not a human-presence proof or permission to manufacture owner authorization.
"""
import argparse
import hashlib
import json
from pathlib import Path
import build_progress as progress
import build_workflow as workflow

FIELDS = {'schema_version','goal','state','candidate','atom_request','bindings','evidence','progress','approval'}

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def read(path):
    p=Path(path).absolute()
    if p.is_symlink() or not p.is_file() or p.resolve()!=p:
        raise ValueError('Build evidence must be an existing unlinked regular file: '+str(p))
    return json.loads(p.read_text())

def validate(packet,root):
    root=Path(root).resolve()
    if not isinstance(packet,dict) or set(packet)!=FIELDS or packet['schema_version']!='build-1':
        raise ValueError('Require the exact build-1 handoff contract')
    if set(packet['candidate'])!={'outcome','contribution','proof'}:
        raise ValueError('Build promise contains outcome, contribution and proof only; selection stays outside the builder')
    for k,v in packet['candidate'].items():progress.nonempty(v,'Build '+k)
    if packet['candidate']['outcome']!=packet['atom_request']['outcome']:
        raise ValueError('Build promise differs from the exact atom outcome')
    evidence=packet['evidence']
    if not isinstance(evidence,list) or not evidence or len({e['path'] for e in evidence})!=len(evidence):
        raise ValueError('Build evidence must be a nonempty unique register')
    for e in evidence:
        relative=Path(e['path']);p=root/relative
        if relative.is_absolute() or '..' in relative.parts or p.resolve()!=p or not p.is_file():
            raise ValueError('Build source must be an unlinked repository-relative regular file')
        raw=p.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=e['sha256'] or raw.decode()!=e['text']:
            raise ValueError('Build source changed: '+e['path'])
    sources={e['path']:e for e in evidence}
    if set(packet['bindings'])!={'goal','state'}:raise ValueError('Build bindings require goal and state only')
    for k in ['goal','state']:
        name=packet['bindings'][k]
        if name not in sources or read(root/name)!=packet[k]:raise ValueError('Build '+k+' binding differs')
    approval=packet['approval']
    if set(approval)!={'path','quote'} or approval['path'] not in sources or not approval['quote'] or approval['quote'] not in sources[approval['path']]['text']:
        raise ValueError('Build approval requires its exact registered source and quote')
    value=read(root/approval['path'])
    if value.get('approved') is not True or value.get('atom_request_sha256')!=digest(packet['atom_request']) or value.get('repository_root')!=str(root):
        raise ValueError('Owner authorization must approve this exact request and repository')
    progress.nonempty(value.get('authorization_reference'),'Existing owner authorization reference')
    progress.validate_claim(packet);workflow.selection(packet)
    return packet

def prepare(packet,goal_context,root):
    validate(packet,root)
    receipt={'schema_version':'build-1','goal_context':progress.bind_context(packet['goal'],goal_context),'packet_sha256':digest(packet),'admit':True}
    receipt['receipt_sha256']=digest(receipt)
    return receipt

def authorize(packet,receipt,root):
    validate(packet,root)
    fields={'schema_version','goal_context','packet_sha256','admit','receipt_sha256'}
    if set(receipt)!=fields or receipt['schema_version']!='build-1' or receipt['admit'] is not True:
        raise ValueError('Require an admitted build-1 receipt')
    if digest({k:v for k,v in receipt.items() if k!='receipt_sha256'})!=receipt['receipt_sha256'] or digest(packet)!=receipt['packet_sha256']:
        raise ValueError('Build approval receipt or packet changed')
    progress.verify_context(packet,receipt['goal_context'])
    return True

def main():
    p=argparse.ArgumentParser();p.add_argument('packet',type=Path);p.add_argument('output',type=Path);p.add_argument('--goal-context',required=True,type=Path);p.add_argument('--source-root',required=True,type=Path);a=p.parse_args()
    receipt=prepare(read(a.packet),a.goal_context,a.source_root)
    with a.output.open('x') as f:json.dump(receipt,f,indent=2)
    print('BUILD ADMISSION: prepared exact approved request; no comparative judgment')

if __name__=='__main__':main()
