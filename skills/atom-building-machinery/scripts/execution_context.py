"""Collect execution evidence from this installation, without model calls."""
import ast
import hashlib
import json
import subprocess
from pathlib import Path


def supporting_helpers(evidence):
    """Collect the experimentally validated direct, same-module function boundary."""
    helpers = []
    for item in evidence['launcher_sources']:
        path = Path(item['path'])
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != item['sha256']:
            raise ValueError(f"Launcher source changed before helper collection: {path}")
        source = raw.decode()
        definitions = {node.name: node for node in ast.parse(source).body
                       if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        launcher = definitions[item['function']]
        calls = sorted({node.func.id for node in ast.walk(launcher)
                        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id in definitions})
        for name in calls:
            helpers.append({'module': path.name, 'function': name,
                            'text': ast.get_source_segment(source, definitions[name])})
    return helpers


def collect(runtime):
    if not isinstance(runtime, dict) or set(runtime) != {"php", "phpunit", "bootstrap"}:
        raise ValueError("execution_runtime requires exactly php, phpunit and bootstrap paths")
    files = {}
    for name, value in runtime.items():
        if not isinstance(value, str) or not Path(value).is_absolute() or not Path(value).is_file():
            raise ValueError(f"execution_runtime {name} must name an existing absolute file: {value!r}")
        path = Path(value).resolve()
        files[name] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    scripts = Path(__file__).resolve().parents[2] / "experiment-machinery" / "scripts"
    sources = []
    for filename, function in [("development_probe_candidate.py", "execute_bundle"),
                               ("development_probe_compose.py", "execute"),
                               ("run_experiment.py", "_execute")]:
        path = scripts / filename
        raw = path.read_bytes(); source = raw.decode()
        nodes = [n for n in ast.parse(source).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == function]
        if len(nodes) != 1:
            raise ValueError(f"Expected exactly one launcher function {function} in {path}")
        sources.append({"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
                        "function": function, "text": ast.get_source_segment(source, nodes[0])})
    command = [files["php"]["path"], "-d", "error_reporting=8191", files["phpunit"]["path"], "--help"]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
    if completed.returncode != 0:
        raise ValueError(f"Installed test tool help failed ({completed.returncode}): {completed.stderr[:1000]}")
    for name, item in files.items():
        if hashlib.sha256(Path(item["path"]).read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError(f"Runtime file changed during collection: {name}")
    return {"runtime_files": files, "launcher_sources": sources,
            "tool_help": {"command": command, "stdout": completed.stdout, "stderr": completed.stderr},
            "instruction": "Use the actual child and assembly launcher source below to establish paths, arguments and environment. Treat inherited outer target variables according to their actual use in that source. Use only test options supported by the installed tool help. This evidence does not establish business requirements or prove generated code works."}
