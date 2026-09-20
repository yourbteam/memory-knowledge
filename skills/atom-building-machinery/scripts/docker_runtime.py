"""Pinned, network-free Docker runtime for prepared disposable experiments."""
import hashlib,json,os,subprocess,uuid,shutil
from pathlib import Path
from runtime_common import ref,save,verify,read


def tree(root):
    h=hashlib.sha256()
    for p in sorted(Path(root).rglob('*')):
        if p.is_symlink(): raise ValueError('Runtime dependencies contain a symlink: '+str(p))
        if p.is_file():
            h.update(str(p.relative_to(root)).encode()+b'\0');h.update(hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()


def base(image,source,vendor):
    return ['docker','run','--rm','--pull=never','--network=none','--read-only','--cap-drop=ALL',
            '--security-opt=no-new-privileges','--pids-limit=128','--memory=1g',
            '--mount',f'type=bind,src={source},dst={source},readonly',
            '--mount',f'type=bind,src={vendor},dst={vendor},readonly']


def prepare(config,source,autoload,output):
    output=Path(output);cfg=read(config);image=cfg['image']
    if not image.startswith('sha256:') or len(image)!=71:raise ValueError('Use an immutable Docker image SHA-256')
    actual=subprocess.check_output(['docker','image','inspect','--format','{{.Id}}',image],text=True).strip()
    if actual!=image:raise ValueError('Runtime image identity differs')
    source=Path(source).resolve();vendor=Path(autoload).resolve().parent
    composer_original=Path(cfg['composer']).resolve();output.mkdir(parents=True,exist_ok=True)
    composer=output/'composer.phar';shutil.copyfile(composer_original,composer)
    if ref(composer)['sha256']!=ref(composer_original)['sha256']:raise ValueError('Composer copy differs')
    dependency_hash=tree(vendor)
    rows=[]
    for suffix in [['--lock'],[]]:
        command=base(image,source,vendor)+['--mount',f'type=bind,src={composer},dst=/tools/composer.phar,readonly',
            '--env','COMPOSER_VENDOR_DIR='+str(vendor),'--env','COMPOSER_ALLOW_SUPERUSER=1',
            '--workdir',str(source),'--entrypoint','php',image,'/tools/composer.phar','--no-plugins','--no-scripts',
            '--no-interaction','check-platform-reqs',*suffix,'--format=json']
        p=subprocess.run(command,capture_output=True,text=True,timeout=60)
        row={'command':command,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
        path=output/('locked.json' if suffix else 'installed.json');save(path,row);rows.append(ref(path))
        if p.returncode:raise ValueError('Runtime compatibility check failed before generation: '+str(path))
    command=base(image,source,vendor)+['--entrypoint','python3',image,'-c',
        'import subprocess,json; print(json.dumps({"python":__import__("sys").version,"php":json.loads(subprocess.check_output(["php","-r",\'echo json_encode(["version"=>PHP_VERSION,"pdo_sqlite"=>extension_loaded("pdo_sqlite")]);\'],text=True))}))']
    p=subprocess.run(command,capture_output=True,text=True,timeout=30)
    save(output/'facts-process.json',{'command':command,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
    if p.returncode:raise ValueError('Runtime cannot execute Python and PHP: '+str(output/'facts-process.json'))
    facts=json.loads(p.stdout)
    if not facts['php']['pdo_sqlite']:raise ValueError('Runtime lacks required PDO SQLite')
    if tree(vendor)!=dependency_hash:raise ValueError('Dependencies changed during compatibility checking')
    result={'kind':'docker','image':image,'vendor':str(vendor),'vendor_sha256':dependency_hash,'autoload':ref(autoload),
            'composer':ref(composer),'checks':rows,'facts':facts,'php':'/usr/local/bin/php','python':'/usr/bin/python3',
            'project_files':[ref(source/'composer.json'),ref(source/'composer.lock')]}
    save(output/'runtime.json',result);return result


def recheck(runtime):
    verify(runtime['autoload']);verify(runtime['composer'])
    for r in runtime['project_files']+runtime['checks']:verify(r)
    if tree(runtime['vendor'])!=runtime['vendor_sha256']:raise ValueError('Verified runtime dependencies changed before execution')
    if subprocess.check_output(['docker','image','inspect','--format','{{.Id}}',runtime['image']],text=True).strip()!=runtime['image']:raise ValueError('Verified image changed')


def execute(runtime,candidate,output,probe=False):
    recheck(runtime);candidate=Path(candidate).resolve();output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    results=candidate/'experiment/results';results.mkdir(parents=True,exist_ok=True)
    report=candidate/'experiment/report.md'
    if not report.exists():report.write_text('')
    name='atom-probe-'+uuid.uuid4().hex
    command=base(runtime['image'],candidate,runtime['vendor'])+[
        '--name',name,'--mount',f'type=bind,src={results},dst={results}',
        '--mount',f'type=bind,src={report},dst={report}', '--tmpfs','/tmp:rw,nosuid,nodev,size=128m',
        '--env','TMPDIR=/tmp','--env','PYTHONDONTWRITEBYTECODE=1','--workdir',str(candidate),
        '--entrypoint',runtime['python'],runtime['image']]
    if probe:
        program='''import json,pathlib,socket,os
r=pathlib.Path.cwd();checks={}
(r/'experiment/results/allowed').write_text('ok');checks['results_write']=True
(r/'experiment/report.md').write_text('ok');checks['report_write']=True
for key,p in [('source_protected',r/'experiment/run.py'),('root_protected',pathlib.Path('/forbidden'))]:
 try:p.write_text('forbidden');checks[key]=False
 except OSError:checks[key]=True
checks['no_external_interface']=set(os.listdir('/sys/class/net'))=={'lo'}
checks['no_docker_socket']=not pathlib.Path('/var/run/docker.sock').exists()
print(json.dumps(checks))
'''
        command+=['-c',program]
    else:command+=['-B',str(candidate/'experiment/run.py'),'--source-root',str(candidate),'--autoload',runtime['autoload']['path'],'--php',runtime['php']]
    save(output/'command.json',{'argv':command,'timeout_seconds':180})
    with (output/'stdout.txt').open('w') as out,(output/'stderr.txt').open('w') as err:
        child=subprocess.Popen(command,stdout=out,stderr=err,start_new_session=True)
        timed_out=False
        try:code=child.wait(timeout=180)
        except subprocess.TimeoutExpired:
            timed_out=True;subprocess.run(['docker','kill',name],capture_output=True);child.kill();code=child.wait()
        finally:subprocess.run(['docker','rm','-f',name],capture_output=True)
    recheck(runtime)
    result={'returncode':code,'timed_out':timed_out,'stdout':ref(output/'stdout.txt'),'stderr':ref(output/'stderr.txt'),'command':ref(output/'command.json')}
    save(output/'process.json',result)
    if probe and (code or not all(json.loads((output/'stdout.txt').read_text()).values())):raise ValueError('Docker confinement probe failed')
    return result


def check_host(php,autoload,source,output):
    """Reject incompatible legacy host runtimes before any model invocation."""
    composer=shutil.which('composer')
    if not composer:raise ValueError('No Composer executable available for host compatibility validation')
    for label,flags in [('locked',['--lock']),('installed',[])]:
        argv=[str(php),composer,'--no-plugins','--no-scripts','--no-interaction','check-platform-reqs',*flags,'--format=json']
        p=subprocess.run(argv,cwd=source,env={**os.environ,'COMPOSER_VENDOR_DIR':str(Path(autoload).parent)},capture_output=True,text=True,timeout=60)
        save(Path(output)/(label+'.json'),{'command':argv,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
        if p.returncode:raise ValueError('Host runtime failed '+label+' compatibility check before generation; use a verified Docker runtime. Evidence: '+str(Path(output)/(label+'.json')))
