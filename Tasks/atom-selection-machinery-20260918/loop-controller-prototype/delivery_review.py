"""Reuse an independent application review only for exactly the reviewed change."""
import hashlib,json,sys
from pathlib import Path

def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def verified(r):
 p=Path(r['path'])
 if p.is_symlink() or not p.is_file() or sha(p)!=r['sha256']:raise ValueError('Changed review input: '+str(p))
 return p

def run(surface,output):
 surface=Path(surface);output=Path(output)
 config=read(output.parent.parent/'preparation/review-reuse.json')
 actual=read(surface);forecast=read(verified(config['forecast']))
 if actual!=forecast:raise ValueError('Delivery surface differs from its bound branch/baseline forecast')
 prior=read(verified(config['surface']));result=read(verified(config['review']))
 packet=read(verified(config['packet']));answer=read(verified(config['answer']))
 if packet.get('decision')!='candidate_application' or result['verdict']!='passed' or result['blocking_findings']:
  raise ValueError('No passed independent application review')
 if result['change_surface_sha256']!=sha(verified(config['surface'])) or actual['changes']!=prior['changes']:
  raise ValueError('Delivery files differ from the independently reviewed changes')
 # Recheck the model judgment mechanically with the existing citation/coverage contract.
 sys.path.insert(0,config['builder_scripts'])
 from source_review_contract import receipt
 if receipt(packet,answer)!=result:raise ValueError('Saved review differs from its model answer')
 for c in actual['changes']:
  r=next(r for r in config['candidate_files'] if r['relative']==c['path'])
  verified({'path':r['path'],'sha256':c['after_sha256']})
 value={**result,'change_surface_sha256':sha(surface)}
 output.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
 output.with_suffix('.reuse.json').write_text(json.dumps({'independent_review':config['review'],'surface':config['surface'],'delivery_forecast':config['forecast'],'model_calls':0},indent=2)+'\n')

if __name__=='__main__':run(*sys.argv[1:])
