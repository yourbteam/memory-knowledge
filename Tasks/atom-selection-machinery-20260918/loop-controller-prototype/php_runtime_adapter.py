"""PHP/Composer implementation of the shared runtime interface."""
from pathlib import Path
from runtime_common import ref,save,verify
import docker_runtime
import php_host_runtime


def identities():
    return [ref(Path(__file__)),ref(Path(docker_runtime.__file__)),ref(Path(php_host_runtime.__file__))]


def validate_assignment(data):
    paths=data['allowed_paths']
    if 'experiment/run.py' not in paths:raise ValueError('PHP experiment adapter requires its experiment/run.py entrypoint')
    if any(not p.startswith('experiment/') for p in paths):raise ValueError('PHP experiment adapter permits only disposable experiment files')


def prepare(settings,source,output):
    backend=settings.get('backend');autoload=settings.get('autoload')
    if not autoload or not Path(autoload).is_file():raise ValueError('PHP adapter requires an existing autoload file')
    if backend=='docker':
        if set(settings)!={'backend','autoload','docker'}:raise ValueError('PHP Docker settings require backend, autoload and docker')
        save(output/'config.json',settings['docker'])
        return {'backend':backend,'binding':docker_runtime.prepare(output/'config.json',source,autoload,output/'checks')}
    if backend=='host':
        if set(settings)!={'backend','autoload','php'}:raise ValueError('PHP host settings require backend, autoload and php')
        php=Path(settings['php']).resolve()
        if not php.is_file():raise ValueError('PHP adapter executable is unavailable')
        docker_runtime.check_host(php,autoload,source,output/'checks')
        return {'backend':backend,'binding':{'php':ref(php),'autoload':ref(autoload),'vendor_sha256':docker_runtime.tree(Path(autoload).parent),'checks':[ref(output/'checks'/n) for n in ['locked.json','installed.json']]}}
    raise ValueError('Unsupported PHP execution backend: '+str(backend))


def facts(payload):
    return payload['binding']


def recheck(payload):
    b=payload['binding']
    if payload['backend']=='docker':docker_runtime.recheck(b)
    elif payload['backend']=='host':
        verify(b['php']);verify(b['autoload'])
        for r in b['checks']:verify(r)
        if docker_runtime.tree(Path(b['autoload']['path']).parent)!=b['vendor_sha256']:raise ValueError('PHP host dependencies changed')
    else:raise ValueError('Unknown saved PHP backend')


def isolation(payload,output):
    recheck(payload);b=payload['binding']
    if payload['backend']=='host':return php_host_runtime.isolation_probe(output,verify(b['php']),Path(b['autoload']['path']).parent)
    probe=output/'source';(probe/'experiment').mkdir(parents=True)
    (probe/'experiment/run.py').write_text('protected')
    docker_runtime.execute(b,probe,output/'execution',probe=True)
    return ref(output/'execution/process.json')


def execute(payload,candidate,output):
    recheck(payload);b=payload['binding']
    if payload['backend']=='docker':return docker_runtime.execute(b,candidate,output)
    result=php_host_runtime.execute(verify(b['php']),verify(b['autoload']),candidate,output)
    recheck(payload);return result
