"""Environment-neutral dispatch. Only verified registered adapters may execute."""
from pathlib import Path
import json
from runtime_common import ref,read,save,verify

REGISTRY={'php-composer': 'php_runtime_adapter'}


def identify(source):
    source=Path(source)
    if not source.is_dir():raise ValueError('Project source directory is unavailable: '+str(source))
    dotnet=sorted(p.name for pattern in ('*.sln','*.slnx','*.csproj','*.fsproj') for p in source.glob(pattern))
    markers=[]
    if (source/'composer.json').is_file():markers.append('php-composer')
    if dotnet:markers.append('dotnet')
    if (source/'package.json').is_file():markers.append('node')
    if not markers and list(source.glob('*.html')):markers.append('html')
    return markers or ['unidentified']


def resolve(config,source):
    markers=identify(source)
    if config is None:
        raise ValueError('No runtime adapter configured for '+', '.join(markers)+'. Available adapter: php-composer. No model call was made.')
    if not isinstance(config,dict) or set(config)!={'schema_version','adapter','settings'} or config['schema_version']!=1 or not isinstance(config['settings'],dict):
        raise ValueError('Runtime configuration requires schema_version=1, adapter and settings')
    name=config['adapter']
    if name not in REGISTRY:raise ValueError('Unsupported runtime adapter '+str(name)+'. Detected project: '+', '.join(markers)+'. Available adapter: php-composer. No model call was made.')
    if name not in markers:raise ValueError('Runtime adapter '+name+' does not match project '+', '.join(markers)+'. No model call was made.')
    if 'dotnet' in markers or ('node' in markers and name=='php-composer'):
        raise ValueError('Multiple project environments detected: '+', '.join(markers)+'. Select the intended component source root before preparation; no model call was made.')
    return name,__import__(REGISTRY[name])


def prepare(config,source,assignment,output):
    name,adapter=resolve(config,source)
    adapter.validate_assignment(assignment)
    payload=adapter.prepare(config['settings'],source,Path(output)/'adapter')
    receipt={'schema_version':1,'adapter':name,'implementation':adapter.identities(),'payload':payload}
    save(Path(output)/'receipt.json',receipt)
    return {'receipt':ref(Path(output)/'receipt.json'),'adapter':name,'facts':adapter.facts(payload)}


def open_runtime(handle):
    receipt=read(verify(handle['receipt']));name=receipt['adapter']
    if name not in REGISTRY or name!=handle['adapter']:raise ValueError('Unknown or changed runtime adapter identity')
    adapter=__import__(REGISTRY[name])
    if receipt['implementation']!=adapter.identities():raise ValueError('Runtime adapter implementation changed after preparation')
    adapter.recheck(receipt['payload']);return adapter,receipt['payload']


def isolation(handle,output):
    adapter,payload=open_runtime(handle)
    return adapter.isolation(payload,Path(output))


def execute(handle,candidate,output):
    adapter,payload=open_runtime(handle)
    return adapter.execute(payload,Path(candidate),Path(output))


def legacy_config(php,autoload,docker_config):
    # CLI compatibility only; environment-specific interpretation lives in the adapter.
    if not php and not docker_config:return None
    if php and docker_config:raise ValueError('Choose one legacy runtime or --runtime-config')
    settings={'autoload':str(autoload) if autoload else None}
    if docker_config:settings.update(backend='docker',docker=read(docker_config))
    else:settings.update(backend='host',php=str(php))
    return {'schema_version':1,'adapter':'php-composer','settings':settings}
