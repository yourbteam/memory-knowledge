"""Existing PHP host sandbox, owned by the PHP adapter."""
import json,os,signal,subprocess,sys
from pathlib import Path
from runtime_common import save,ref

def profile(candidate, vendor, scratch):
    def sub(p): return '(subpath ' + json.dumps(str(Path(p).resolve())) + ')'
    roots = ['/System', '/Library', '/usr', '/bin', '/sbin', '/opt/homebrew', '/private/etc', '/dev', candidate, vendor, scratch]
    return ('(version 1)\n(deny default)\n(allow process*)\n(allow sysctl-read)\n'
            '(allow mach-lookup)\n(allow file-read-metadata)\n'
            '(allow file-read* (literal "/") ' + ' '.join(sub(p) for p in roots) + ')\n'
            '(allow file-write* ' + ' '.join(sub(Path(candidate) / p) for p in RUNTIME_DIRECTORIES) + ' '
            + ' '.join('(literal ' + json.dumps(str(Path(candidate) / p)) + ')' for p in RUNTIME_FILES)
            + ' ' + sub(scratch) + ' (literal "/dev/null"))\n')


def isolation_probe(output, php, vendor):
    """Exercise the actual sandbox with permitted write, forbidden write and network."""
    root = output / 'isolation-probe';root.mkdir(parents=True, exist_ok=True)
    experiment = root / 'experiment';experiment.mkdir(exist_ok=True)
    (experiment / 'results').mkdir(exist_ok=True)
    (experiment / 'run.py').write_text('protected code')
    scratch = root / 'tmp';scratch.mkdir(exist_ok=True)
    policy = root / 'policy.sb';policy.write_text(profile(root, vendor, scratch))
    # A denied write targets this disposable probe root, never the product repository.
    source = root / 'probe.php'
    source.write_text('<?php $ok=file_put_contents(__DIR__."/experiment/results/allowed", "ok"); '
                      '$bad=@file_put_contents(__DIR__."/forbidden", "bad"); '
                      '$code=@file_put_contents(__DIR__."/experiment/run.py", "bad"); '
                      '$report=file_put_contents(__DIR__."/experiment/report.md", "ok"); '
                      '$sock=@stream_socket_server("tcp://127.0.0.1:0",$n,$e); '
                      'echo json_encode(["allowed"=>$ok===2,"outside_denied"=>$bad===false,"code_denied"=>$code===false,"report_allowed"=>$report===2,"network_denied"=>$sock===false]);')
    command = ['/usr/bin/sandbox-exec', '-f', str(policy), str(php), '-n', str(source)]
    proc = subprocess.run(command, capture_output=True, text=True, timeout=20)
    result = {'command': command, 'exit': proc.returncode, 'stdout': proc.stdout, 'stderr': proc.stderr}
    save(root / 'result.json', result)
    if proc.returncode or json.loads(proc.stdout) != {'allowed': True, 'outside_denied': True, 'code_denied': True, 'report_allowed': True, 'network_denied': True}:
        raise ValueError('OS isolation probe failed; generated code must not execute')
    return ref(root / 'result.json')



def execute(php,autoload,candidate,run):
    run.mkdir(parents=True,exist_ok=True)
    scratch=run/'tmp';scratch.mkdir(exist_ok=True)
    policy = run / 'policy.sb';policy.write_text(profile(candidate, autoload.parent, scratch))

    command = ['/usr/bin/sandbox-exec', '-f', str(policy), sys.executable, '-B',
               str(candidate / 'experiment/run.py'), '--source-root', str(candidate),
               '--autoload', str(autoload), '--php', str(php)]
    save(run / 'command.json', {'argv': command, 'cwd': str(candidate), 'timeout_seconds': 180})

    with (run / 'stdout.txt').open('w') as stdout, (run / 'stderr.txt').open('w') as stderr:
        child = subprocess.Popen(command, cwd=candidate, stdout=stdout, stderr=stderr,
                                 env={'PATH': '/opt/homebrew/bin:/usr/bin:/bin', 'HOME': str(scratch),
                                      'TMPDIR': str(scratch), 'PYTHONDONTWRITEBYTECODE': '1'}, start_new_session=True)
        timed_out = False
        try: code = child.wait(timeout=180)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL);code = child.wait();timed_out = True
    return {'returncode':code,'timed_out':timed_out}
