#!/usr/bin/env python3
"""Prepare the bounded atom that closes the promoted reader-test proof gap."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
OUT = Path(sys.argv[1]).resolve() if len(sys.argv) == 2 else Path(
    "/private/tmp/requirements-machinery-validation-fix"
)
ATOM_ID = "complete-requirements-machinery-promotion-validation"
TEST_NAME = "test_reader_execution_outcomes_fail_closed_before_semantic_parsing"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def copy(relative: str, target: Path) -> None:
    source = REPO / relative
    destination = target / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        shutil.copy2(source, destination)


FAKE_READER = """\
import sys
import time

mode = sys.argv[1]
if mode == "success":
    print("NO")
elif mode == "nonzero-stdout":
    print("YES")
    raise SystemExit(7)
elif mode == "timeout":
    time.sleep(1)
    print("YES")
elif mode == "malformed":
    print("MAYBE")
else:
    raise SystemExit(9)
"""


def replacement(strategy: str) -> str:
    lines = [
        f"def {TEST_NAME}(monkeypatch) -> None:",
        '    interview = load("requirements_interview_execution", MACHINERY / "scripts" / "interview.py")',
        "    with tempfile.TemporaryDirectory() as directory:",
        '        feed = Path(directory) / "feed.jsonl"',
        '        monkeypatch.setenv("REQ_MACHINERY_FEED", str(feed))',
        '        monkeypatch.setenv("REQ_MACHINERY_READER_TIMEOUT_SECONDS", "0.05")',
    ]
    if strategy == "temporary-reader-file":
        lines.extend([
            '        fixture = Path(directory) / "fake_reader.py"',
            f"        fixture.write_text({FAKE_READER!r}, encoding=\"utf-8\")",
            "",
            "        def command(mode: str) -> str:",
            '            return " ".join(shlex.quote(part) for part in (sys.executable, str(fixture), mode))',
        ])
    elif strategy == "inline-python-command":
        lines.extend([
            "        def command(mode: str) -> str:",
            '            return " ".join(shlex.quote(part) for part in (',
            f'                sys.executable, "-c", {FAKE_READER!r}, mode,',
            "            ))",
        ])
    else:
        raise ValueError(strategy)
    lines.extend([
        "",
        '        assert interview._spawn(command("success"), "question", "test") == "NO"',
        "        with pytest.raises(SystemExit) as nonzero:",
        '            interview._spawn(command("nonzero-stdout"), "question", "test")',
        "        assert nonzero.value.code == 4",
        "        with pytest.raises(SystemExit) as timeout:",
        '            interview._spawn(command("timeout"), "question", "test")',
        "        assert timeout.value.code == 4",
        "        answer, transcript = interview.ask_choice(",
        '            command("malformed"), "question", ["YES", "NO"])',
        "        assert answer is None and len(transcript) == 3",
        "",
        '        events = [json.loads(line) for line in feed.read_text(encoding="utf-8").splitlines()]',
        '        outcomes = {event.get("outcome") for event in events}',
        '        assert {"zero-exit", "nonzero-exit", "timeout", "malformed-reply"} <= outcomes',
        '        assert not any(event.get("outcome") == "valid-reply" for event in events)',
        '        assert "reader process" not in "".join(json.dumps(event) for event in events)',
        "",
        '    contract = (MACHINERY / "SKILL.md").read_text(encoding="utf-8")',
        '    assert "180 seconds by default" in contract',
        '    assert "only a zero-exit reply reaches semantic validation" in contract',
        "",
        "",
    ])
    return "\n".join(lines)


def patch_test(root: Path, strategy: str) -> None:
    path = root / "tests/test_requirements_machinery_cover.py"
    source = path.read_text(encoding="utf-8")
    start = source.index(f"def {TEST_NAME}")
    end = source.index("def test_reader_policy_is_validated_at_every_cli_command_boundary", start)
    path.write_text(source[:start] + replacement(strategy) + source[end:], encoding="utf-8")


OPERATOR = r'''from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
root = Path(__file__).resolve().parent
work = Path(os.environ["EXPERIMENT_WORK_DIR"])
case = json.loads(Path(os.environ["EXPERIMENT_INPUT_PATH"]).read_text())
test_path = root / "tests/test_requirements_machinery_cover.py"
env = dict(os.environ)
env["PYTHONDONTWRITEBYTECODE"] = "1"
env["PYTHONPYCACHEPREFIX"] = str(work / "pycache")
completed = subprocess.run(
    ["__PYTEST_PYTHON__", "-m", "pytest", "-p", "no:cacheprovider",
     f"{test_path}::test_reader_execution_outcomes_fail_closed_before_semantic_parsing"],
    cwd=root, env=env, capture_output=True, text=True,
)
source = test_path.read_text(encoding="utf-8")

spec = importlib.util.spec_from_file_location(
    "projection", root / "working-agreement/project_client_skills.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
names = module.manifest_names(root / "skills/managed-skills.txt")
entries = module.load_projections(root / "working-agreement/client-skill-projections.json")["entries"]
old_pattern = re.compile(r"requirements-machine(?!ry)")
routes = [
    root / "skills/working-agreement/SKILL.md",
    root / "skills/task-intake/SKILL.md",
    root / "skills/sequence-runner/SKILL.md",
]
routes_aligned = all(
    "requirements-machinery" in path.read_text()
    and not old_pattern.search(path.read_text()) for path in routes
)
new_skill = root / "skills/requirements-machinery"
client_projections = True
for client, required in (("codex", "codex exec"), ("claude", "claude -p")):
    writable = work / f"source-{client}"
    projected = work / f"projection-{client}"
    shutil.copytree(new_skill, writable)
    for path in writable.rglob("*"):
        path.chmod(0o755 if path.is_dir() else 0o644)
    module.project_skill(writable, projected, client, entries["requirements-machinery"])
    policy = json.loads((projected / "client-model-policy.json").read_text())
    client_projections = client_projections and policy.get("recommended_reader_command") == required

outcome = {
    "case_id": case["case_id"],
    "focused_test_passed": completed.returncode == 0,
    "external_task_dependency": "understand-requirements-machinery" in source,
    "real_subprocess_boundary": "interview._spawn" in source,
    "path_command_fidelity": "fake_reader.py" in source,
    "old_skill_absent": not (root / "skills/requirements-machine").exists(),
    "managed_identity_exact": "requirements-machinery" in names and "requirements-machine" not in names,
    "projection_identity_exact": "requirements-machinery" in entries and "requirements-machine" not in entries,
    "routes_aligned": routes_aligned,
    "client_projections_correct": client_projections,
    "pytest_stdout": completed.stdout[-2000:],
    "pytest_stderr": completed.stderr[-2000:],
}
result = {
    "schema_version": 1,
    "variant_id": os.environ["EXPERIMENT_VARIANT_ID"],
    "status": "completed",
    "outcome": outcome,
    "metrics": {
        "focused-proof-correctness": int(outcome["focused_test_passed"]),
        "path-command-fidelity": int(outcome["path_command_fidelity"]),
    },
    "error": None,
}
Path(os.environ["EXPERIMENT_RESULT_PATH"]).write_text(json.dumps(result, sort_keys=True) + "\n")
'''


EVALUATOR = r'''import json, sys
from pathlib import Path
request = json.loads(Path(sys.argv[1]).read_text())
scores = []
for candidate in request["candidates"]:
    outcome = candidate["outcome"]
    scores.append({
        "variant_id": candidate["variant_id"],
        "metrics": {
            "focused-proof-correctness": int(
                outcome.get("focused_test_passed") is True
                and outcome.get("external_task_dependency") is False
                and outcome.get("real_subprocess_boundary") is True
            ),
            "path-command-fidelity": int(outcome.get("path_command_fidelity") is True),
        },
    })
Path(sys.argv[2]).write_text(json.dumps({"schema_version": 1, "scores": scores}, sort_keys=True) + "\n")
'''


ASSESSMENT = r'''import json, sys
from pathlib import Path
question = json.loads(Path(sys.argv[1]).read_text())
outcome = question["execution_result"]["outcome"]
required = (
    "focused_test_passed", "old_skill_absent", "managed_identity_exact",
    "projection_identity_exact", "routes_aligned", "client_projections_correct",
)
satisfied = all(outcome.get(key) is True for key in required)
satisfied = satisfied and outcome.get("external_task_dependency") is False
response = {
    "case_id": question["case_id"],
    "verdict": "satisfied" if satisfied else "not-satisfied",
    "reason": (
        "The complete promoted requirements machinery and its self-contained reader proof work through the managed client path."
        if satisfied else
        "The promoted requirements machinery or its reader proof remains incomplete through the managed client path."
    ),
    "evidence_pointers": ["execution-result"],
}
Path(sys.argv[2]).write_text(json.dumps(response, sort_keys=True) + "\n")
'''


def main() -> None:
    if OUT.exists():
        raise SystemExit(f"refusing existing output: {OUT}")
    development = OUT / "development"
    baseline = development / "baseline"
    for relative in (
        "skills/requirements-machinery",
        "skills/managed-skills.txt",
        "skills/working-agreement/SKILL.md",
        "skills/task-intake/SKILL.md",
        "skills/sequence-runner/SKILL.md",
        "working-agreement/client-skill-projections.json",
        "working-agreement/machinery-client-model-v1.json",
        "working-agreement/machinery-client-model-v2.json",
        "working-agreement/project_client_skills.py",
        "tests/test_requirements_machinery_cover.py",
    ):
        copy(relative, baseline)
    pytest_python = REPO / ".venv/bin/python"
    if not pytest_python.is_file():
        raise RuntimeError(f"real test interpreter is absent: {pytest_python}")
    (baseline / "operator_probe.py").write_text(
        OPERATOR.replace("__PYTEST_PYTHON__", str(pytest_python)), encoding="utf-8")

    candidates = {}
    for approach in ("temporary-reader-file", "inline-python-command"):
        target = development / approach
        shutil.copytree(baseline, target)
        patch_test(target, approach)
        candidates[approach] = target

    cases = []
    for case_id, kind, expected in (
        ("missing-task-fixture", "failure", "The focused reader test passes without any task-only fixture path."),
        ("managed-dual-client-path", "success", "The retired skill stays absent and both managed client projections remain usable."),
    ):
        path = OUT / "cases" / f"{case_id}.json"
        write(path, {"case_id": case_id, "captured_failure": "task-only reader fixture is absent"})
        cases.append({
            "id": case_id, "source": str(path), "sha256": sha(path),
            "kind": kind, "expected_outcome": expected,
        })

    outcome = (
        "Only the latest requirements-machinery is canonical and usable through managed Codex "
        "and Claude projections, with a self-contained focused reader proof."
    )
    allowed = ["tests/test_requirements_machinery_cover.py"]
    atom_request = {
        "schema_version": 1,
        "atomic_step_id": ATOM_ID,
        "outcome": outcome,
        "practical_value": "The promoted skill can be trusted and regression-tested from a clean checkout without hidden task artifacts.",
        "stopping_condition": "Both captured cases pass through the assembled candidate, focused suite, managed projection build, and installed client validation.",
        "allowed_paths": allowed,
        "captured_cases": [{
            "case_id": case["id"], "source_ref": case["source"],
            "sha256": case["sha256"], "kind": case["kind"],
            "expected_outcome": case["expected_outcome"],
        } for case in cases],
    }
    write(OUT / "atom-request.json", atom_request)
    manifest = {
        "schema_version": 1,
        "atomic_step": {
            "id": ATOM_ID, "outcome": outcome,
            "practical_value": atom_request["practical_value"],
            "stopping_condition": atom_request["stopping_condition"],
            "captured_cases": cases,
        },
        "mini_probes": [{
            "id": "self-contained-reader-proof",
            "goal": "Make the reader execution proof independent of task-only artifacts while retaining the real subprocess boundary.",
            "practical_value": atom_request["practical_value"],
            "work_type": "code",
            "work_type_reason": "Fixture location, subprocess execution, exit status, timeout, and test outcome are deterministic boundaries.",
            "allowed_paths": allowed,
            "inputs": [{"case_id": case["id"]} for case in cases],
            "approaches": [
                {
                    "id": "temporary-reader-file",
                    "hypothesis": "A test-owned temporary reader file preserves the real executable-path boundary without repository-task dependencies.",
                    "implementation": "Write the four-mode reader into the test temporary directory and execute it as a real subprocess.",
                    "predicted_tradeoff": "Creates one temporary file but mirrors the real reader command shape.",
                },
                {
                    "id": "inline-python-command",
                    "hypothesis": "An inline Python command can exercise the same exits without any fixture file.",
                    "implementation": "Pass the four-mode reader through Python -c for each real subprocess execution.",
                    "predicted_tradeoff": "Avoids a temporary file but tests a less representative command shape.",
                },
            ],
            "proof": {
                "success_criterion": "The focused test passes from the immutable candidate with no task-only path and the real subprocess boundary remains exercised.",
                "failure_criterion": "The test fails, references the absent task tree, or replaces the subprocess boundary with a mock.",
            },
            "evaluation": {
                "metrics": [
                    {"name": "focused-proof-correctness", "direction": "maximize"},
                    {"name": "path-command-fidelity", "direction": "maximize"},
                ],
                "across_cases": [
                    {"name": "focused-proof-correctness", "method": "sum"},
                    {"name": "path-command-fidelity", "method": "sum"},
                ],
            },
            "winner_output": {
                "artifact": "self-contained-reader-test",
                "description": "The self-contained focused reader proof selected on correctness and real command fidelity.",
            },
        }],
        "composition": {
            "consumes": [{"probe_id": "self-contained-reader-proof", "artifact": "self-contained-reader-test"}],
            "assembly_contract": "Apply the selected self-contained reader proof to the already assembled promoted requirements skill boundary.",
            "final_validation": {
                "operator_path": "run the focused reader proof and build both managed client projections from the complete candidate",
                "case_ids": [case["id"] for case in cases],
                "success_criterion": "The focused test and complete managed requirements machinery pass for both clients.",
                "failure_criterion": "Any task-only dependency, old skill identity, route mismatch, projection failure, or focused test failure refuses completion.",
            },
        },
    }
    write(development / "manifest.json", manifest)
    (development / "evaluator.py").write_text(EVALUATOR, encoding="utf-8")
    (development / "assessment.py").write_text(ASSESSMENT, encoding="utf-8")

    approach_requests = []
    for approach, source in candidates.items():
        request = development / f"build-{approach}.json"
        write(request, {
            "schema_version": 1,
            "development_manifest": str(development / "manifest.json"),
            "probe_id": "self-contained-reader-proof",
            "approach_id": approach,
            "source": {
                "baseline": str(baseline), "candidate": str(source),
                "entrypoint": "operator_probe.py",
            },
            "execution": {"protocol": "experiment-result-v1", "command": ["{python}", "{candidate-entrypoint}"]},
        })
        approach_requests.append({"approach_id": approach, "request": str(request)})
    cross = development / "cross-self-contained-reader-proof.json"
    write(cross, {
        "schema_version": 1,
        "development_manifest": str(development / "manifest.json"),
        "probe_id": "self-contained-reader-proof",
        "approach_build_requests": approach_requests,
        "evaluator": {
            "adapter": {"path": str(development / "evaluator.py"), "sha256": sha(development / "evaluator.py")},
            "command": ["{python}", "{evaluation-adapter}", "{evaluation-request}", "{evaluation-response}"],
        },
    })
    write(development / "full-run.json", {
        "schema_version": 1,
        "development_manifest": {"path": str(development / "manifest.json"), "sha256": sha(development / "manifest.json")},
        "baseline": {
            "path": str(baseline),
            "sha256": subprocess.run(
                [sys.executable, str(REPO / "skills/experiment-machinery/scripts/run_experiment.py"),
                 "--hash-source", str(baseline)],
                check=True, capture_output=True, text=True,
            ).stdout.strip(),
        },
        "probe_requests": [{
            "probe_id": "self-contained-reader-proof",
            "request": str(cross), "request_sha256": sha(cross),
        }],
        "assessment": {
            "adapter": {"path": str(development / "assessment.py"), "sha256": sha(development / "assessment.py")},
            "command": ["{python}", "{assessment-adapter}", "{assessment-request}", "{assessment-response}"],
        },
    })
    print(json.dumps({"root": str(OUT), "atom_request": str(OUT / "atom-request.json"), "full_run": str(development / "full-run.json")}, sort_keys=True))


if __name__ == "__main__":
    main()
