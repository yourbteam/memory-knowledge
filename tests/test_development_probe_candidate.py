from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "skills" / "experiment-machinery" / "scripts" / "development_probe_candidate.py"
RUNNER = ROOT / "skills" / "experiment-machinery" / "scripts" / "run_experiment.py"
LAUNCHER = ROOT / "skills" / "experiment-machinery" / "scripts" / "development_probe_experiment.py"
CROSS_CASE = ROOT / "skills" / "experiment-machinery" / "scripts" / "development_probe_cross_case.py"
ALL_PROBES = ROOT / "skills" / "experiment-machinery" / "scripts" / "development_probe_all_probes.py"
COMPOSE = ROOT / "skills" / "experiment-machinery" / "scripts" / "development_probe_compose.py"
FINAL_VALIDATION = ROOT / "skills" / "experiment-machinery" / "scripts" / "development_probe_final_validation.py"
FULL_RUN = ROOT / "skills" / "experiment-machinery" / "scripts" / "development_probe_run.py"
REPAIR_RUN = ROOT / "skills" / "experiment-machinery" / "scripts" / "development_probe_repair.py"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_digest(path: Path) -> str:
    completed = subprocess.run(
        [sys.executable, str(RUNNER), "--hash-source", str(path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


def _adapter(quality: int) -> str:
    return f"""from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from pathlib import Path

variant_id = os.environ["EXPERIMENT_VARIANT_ID"]
input_path = Path(os.environ["EXPERIMENT_INPUT_PATH"])
result_path = Path(os.environ["EXPERIMENT_RESULT_PATH"])
telemetry_path = Path(os.environ["EXPERIMENT_TELEMETRY_PATH"])
payload = json.loads(input_path.read_text(encoding="utf-8"))
telemetry = {{
    "schema_version": 1,
    "sequence": 1,
    "event": "candidate_finished",
    "recorded_at": datetime.now(timezone.utc).isoformat(),
    "variant_id": variant_id,
    "input_value": payload["value"],
}}
telemetry_path.write_text(json.dumps(telemetry, sort_keys=True) + "\\n", encoding="utf-8")
result = {{
    "schema_version": 1,
    "variant_id": variant_id,
    "status": "completed",
    "outcome": {{"value": payload["value"], "observed_quality": {quality}}},
    "metrics": {{"quality": {quality}}},
    "error": None,
}}
result_path.write_text(json.dumps(result, sort_keys=True) + "\\n", encoding="utf-8")
"""


def _case_scored_adapter(scores: dict[str, int]) -> str:
    return (
        _adapter(0)
        .replace(
            '"observed_quality": 0',
            f'"observed_quality": {scores!r}[payload["value"]]',
        )
        .replace(
            '"metrics": {"quality": 0}',
            f'"metrics": {{"quality": {scores!r}[payload["value"]]}}',
        )
    )


def _fixture(root: Path) -> tuple[Path, Path, Path, Path]:
    cases = root / "cases"
    cases.mkdir()
    works = cases / "works.json"
    refuses = cases / "refuses.json"
    works.write_text('{"value":"works"}\n', encoding="utf-8")
    refuses.write_text('{"value":"refuses"}\n', encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "atomic_step": {
            "id": "candidate-bundle",
            "outcome": "A declared approach becomes a runnable immutable candidate.",
            "practical_value": "Experiments execute candidates without editing product code.",
            "stopping_condition": "Two candidates run and one is recommended without promotion.",
            "captured_cases": [
                {
                    "id": "works",
                    "source": str(works),
                    "sha256": _digest(works),
                    "kind": "success",
                    "expected_outcome": "The candidate completes.",
                },
                {
                    "id": "refuses",
                    "source": str(refuses),
                    "sha256": _digest(refuses),
                    "kind": "failure",
                    "expected_outcome": "The candidate refuses invalid input.",
                },
            ],
        },
        "mini_probes": [
            {
                "id": "runner",
                "goal": "Run one declared approach.",
                "practical_value": "The approach can enter Experiment Machinery.",
                "work_type": "code",
                "work_type_reason": "Identity and execution are deterministic.",
                "allowed_paths": ["adapter.py"],
                "inputs": [{"case_id": "works"}, {"case_id": "refuses"}],
                "approaches": [
                    {
                        "id": "control",
                        "hypothesis": "The control can run.",
                        "implementation": "Execute a copied Python candidate.",
                        "predicted_tradeoff": "Lower quality score.",
                    },
                    {
                        "id": "variation",
                        "hypothesis": "The variation can run.",
                        "implementation": "Execute a separately copied Python candidate.",
                        "predicted_tradeoff": "Higher quality score.",
                    },
                ],
                "proof": {
                    "success_criterion": "The real candidate writes the experiment result.",
                    "failure_criterion": "Changed or undeclared evidence is refused.",
                },
                "evaluation": {
                    "metrics": [{"name": "quality", "direction": "maximize"}],
                    "across_cases": [{"name": "quality", "method": "sum"}],
                },
                "winner_output": {
                    "artifact": "runner-candidate",
                    "description": "The recommended runnable candidate bundle.",
                },
            }
        ],
        "composition": {
            "consumes": [{"probe_id": "runner", "artifact": "runner-candidate"}],
            "assembly_contract": "Use the recommended bundle in the atomic implementation.",
            "final_validation": {
                "operator_path": "run candidate comparison",
                "case_ids": ["works", "refuses"],
                "success_criterion": "The complete candidate works.",
                "failure_criterion": "The complete candidate refuses bad input.",
            },
        },
    }
    manifest_path = root / "development-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    baseline = root / "baseline"
    baseline.mkdir()
    (baseline / "adapter.py").write_text(_adapter(0), encoding="utf-8")
    control = root / "control"
    variation = root / "variation"
    control.mkdir()
    variation.mkdir()
    (control / "adapter.py").write_text(_adapter(1), encoding="utf-8")
    (variation / "adapter.py").write_text(_adapter(2), encoding="utf-8")
    return manifest_path, baseline, control, variation


def _request(
    manifest: Path,
    baseline: Path,
    candidate: Path,
    approach_id: str,
) -> dict:
    return {
        "schema_version": 1,
        "development_manifest": str(manifest),
        "probe_id": "runner",
        "approach_id": approach_id,
        "source": {
            "baseline": str(baseline),
            "candidate": str(candidate),
            "entrypoint": "adapter.py",
        },
        "execution": {
            "protocol": "experiment-result-v1",
            "command": ["{python}", "{candidate-entrypoint}"],
        },
    }


def _build(request: dict, request_path: Path, output: Path) -> subprocess.CompletedProcess[str]:
    request_path.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(CANDIDATE), "build", str(request_path), str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _evaluator(root: Path) -> dict:
    path = root / "independent-evaluator.py"
    if not path.exists():
        path.write_text(
            """from __future__ import annotations
import json
import sys
from pathlib import Path

request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
scores = []
for candidate in request["candidates"]:
    outcome = candidate["outcome"]
    if "observed_quality" in outcome:
        quality = outcome["observed_quality"]
    else:
        quality = sum(value not in {"base-a", "base-b"} for value in outcome.get("features", []))
    scores.append({"variant_id": candidate["variant_id"], "metrics": {"quality": quality}})
Path(sys.argv[2]).write_text(json.dumps({"schema_version": 1, "scores": scores}, sort_keys=True) + "\\n", encoding="utf-8")
""",
            encoding="utf-8",
        )
    return {
        "adapter": {"path": str(path), "sha256": _digest(path)},
        "command": [
            "{python}",
            "{evaluation-adapter}",
            "{evaluation-request}",
            "{evaluation-response}",
        ],
    }


def _launcher_request(
    root: Path,
    manifest: Path,
    baseline: Path,
    sources: dict[str, Path],
) -> tuple[Path, dict]:
    requests = []
    for approach_id, source in sources.items():
        request_path = root / f"build-{approach_id}.json"
        _write_json(request_path, _request(manifest, baseline, source, approach_id))
        requests.append({"approach_id": approach_id, "request": str(request_path)})
    launch = {
        "schema_version": 1,
        "development_manifest": str(manifest),
        "probe_id": "runner",
        "case_id": "works",
        "approach_build_requests": requests,
        "evaluator": _evaluator(root),
    }
    launch_path = root / "launch.json"
    _write_json(launch_path, launch)
    return launch_path, launch


def _launch(request: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(LAUNCHER), "run", str(request), str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _cross_case_request(
    root: Path,
    manifest: Path,
    baseline: Path,
    sources: dict[str, Path],
) -> Path:
    _, launch = _launcher_request(root, manifest, baseline, sources)
    launch.pop("case_id")
    request_path = root / "cross-case.json"
    _write_json(request_path, launch)
    return request_path


def _run_cross_case(request: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CROSS_CASE), "run", str(request), str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _all_probe_request(
    root: Path,
    manifest_path: Path,
    baseline: Path,
    sources: dict[str, Path],
) -> tuple[Path, dict[str, Path]]:
    manifest = json.loads(manifest_path.read_text())
    second = deepcopy(manifest["mini_probes"][0])
    second.update(
        {
            "id": "selector",
            "goal": "Select one declared approach.",
            "practical_value": "The second capability has its own proven winner.",
        }
    )
    second["winner_output"] = {
        "artifact": "selector-candidate",
        "description": "The recommended selector candidate bundle.",
    }
    manifest["mini_probes"].append(second)
    manifest["composition"]["consumes"].append({"probe_id": "selector", "artifact": "selector-candidate"})
    _write_json(manifest_path, manifest)

    cross_requests: dict[str, Path] = {}
    probe_requests = []
    for probe_id in ("runner", "selector"):
        build_requests = []
        for approach_id, source in sources.items():
            build = _request(manifest_path, baseline, source, approach_id)
            build["probe_id"] = probe_id
            build_path = root / f"build-{probe_id}-{approach_id}.json"
            _write_json(build_path, build)
            build_requests.append({"approach_id": approach_id, "request": str(build_path)})
        cross = {
            "schema_version": 1,
            "development_manifest": str(manifest_path),
            "probe_id": probe_id,
            "approach_build_requests": build_requests,
            "evaluator": _evaluator(root),
        }
        cross_path = root / f"cross-{probe_id}.json"
        _write_json(cross_path, cross)
        cross_requests[probe_id] = cross_path
        probe_requests.append({"probe_id": probe_id, "request": str(cross_path)})
    request_path = root / "all-probes.json"
    _write_json(
        request_path,
        {
            "schema_version": 1,
            "development_manifest": str(manifest_path),
            "probe_requests": probe_requests,
        },
    )
    return request_path, cross_requests


def _run_all_probes(request: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ALL_PROBES), "run", str(request), str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _composed_adapter() -> str:
    return """from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from feature_a import value as feature_a
from feature_b import value as feature_b

variant_id = os.environ["EXPERIMENT_VARIANT_ID"]
input_path = Path(os.environ["EXPERIMENT_INPUT_PATH"])
result_path = Path(os.environ["EXPERIMENT_RESULT_PATH"])
telemetry_path = Path(os.environ["EXPERIMENT_TELEMETRY_PATH"])
payload = json.loads(input_path.read_text(encoding="utf-8"))
telemetry = {
    "schema_version": 1,
    "sequence": 1,
    "event": "composed_candidate_finished",
    "recorded_at": datetime.now(timezone.utc).isoformat(),
    "variant_id": variant_id,
}
telemetry_path.write_text(json.dumps(telemetry, sort_keys=True) + "\\n", encoding="utf-8")
result = {
    "schema_version": 1,
    "variant_id": variant_id,
    "status": "completed",
    "outcome": {"value": payload["value"], "features": [feature_a(), feature_b()]},
    "metrics": {"quality": 1 if variant_id == "control" else 2},
    "error": None,
}
result_path.write_text(json.dumps(result, sort_keys=True) + "\\n", encoding="utf-8")
"""


def _write_source(root: Path, feature_a: str, feature_b: str) -> None:
    root.mkdir()
    (root / "adapter.py").write_text(_composed_adapter(), encoding="utf-8")
    (root / "feature_a.py").write_text(f"def value():\n    return {feature_a!r}\n", encoding="utf-8")
    (root / "feature_b.py").write_text(f"def value():\n    return {feature_b!r}\n", encoding="utf-8")


def _composition_fixture(
    root: Path,
) -> tuple[Path, Path, Path, dict[str, Path], dict[str, Path]]:
    cases = root / "composition-cases"
    cases.mkdir()
    works = cases / "works.json"
    refuses = cases / "refuses.json"
    works.write_text('{"value":"works"}\n', encoding="utf-8")
    refuses.write_text('{"value":"refuses"}\n', encoding="utf-8")
    baseline = root / "composition-baseline"
    _write_source(baseline, "base-a", "base-b")
    sources = {
        "runner-control": root / "runner-control",
        "runner-variation": root / "runner-variation",
        "selector-control": root / "selector-control",
        "selector-variation": root / "selector-variation",
    }
    _write_source(sources["runner-control"], "base-a", "base-b")
    _write_source(sources["runner-variation"], "runner-a", "base-b")
    _write_source(sources["selector-control"], "base-a", "base-b")
    _write_source(sources["selector-variation"], "base-a", "selector-b")
    manifest = {
        "schema_version": 1,
        "atomic_step": {
            "id": "composed-candidate",
            "outcome": "Independent winners become one runnable candidate.",
            "practical_value": "The full atomic behavior can be validated together.",
            "stopping_condition": "Both compatible winner changes execute in one source tree.",
            "captured_cases": [
                {
                    "id": "works",
                    "source": str(works),
                    "sha256": _digest(works),
                    "kind": "success",
                    "expected_outcome": "The assembled candidate completes.",
                },
                {
                    "id": "refuses",
                    "source": str(refuses),
                    "sha256": _digest(refuses),
                    "kind": "failure",
                    "expected_outcome": "The assembled candidate preserves failure evidence.",
                },
            ],
        },
        "mini_probes": [],
        "composition": {
            "consumes": [],
            "assembly_contract": "Combine compatible winner changes onto the verified baseline.",
            "final_validation": {
                "operator_path": "execute the isolated assembled candidate",
                "case_ids": ["works", "refuses"],
                "success_criterion": "Both winner behaviors are present.",
                "failure_criterion": "Incompatible winners are refused.",
            },
        },
    }
    for probe_id in ("runner", "selector"):
        manifest["mini_probes"].append(
            {
                "id": probe_id,
                "goal": f"Build the {probe_id} behavior.",
                "practical_value": f"The {probe_id} contribution is independently proven.",
                "work_type": "code",
                "work_type_reason": "The result is deterministic source code.",
                "allowed_paths": [
                    "feature_a.py" if probe_id == "runner" else "feature_b.py"
                ],
                "inputs": [{"case_id": "works"}, {"case_id": "refuses"}],
                "approaches": [
                    {
                        "id": "control",
                        "hypothesis": "The baseline behavior remains runnable.",
                        "implementation": "Retain the unchanged baseline source tree.",
                        "predicted_tradeoff": "It omits the new behavior.",
                    },
                    {
                        "id": "variation",
                        "hypothesis": f"The {probe_id} change remains runnable.",
                        "implementation": f"Change only the {probe_id} feature module.",
                        "predicted_tradeoff": "It adds one independently scoped behavior.",
                    },
                ],
                "proof": {
                    "success_criterion": "The candidate writes a completed result.",
                    "failure_criterion": "Changed evidence is refused.",
                },
                "evaluation": {
                    "metrics": [{"name": "quality", "direction": "maximize"}],
                    "across_cases": [{"name": "quality", "method": "sum"}],
                },
                "winner_output": {
                    "artifact": f"{probe_id}-candidate",
                    "description": f"The proven {probe_id} source bundle.",
                },
            }
        )
        manifest["composition"]["consumes"].append({"probe_id": probe_id, "artifact": f"{probe_id}-candidate"})
    manifest_path = root / "composition-manifest.json"
    _write_json(manifest_path, manifest)
    cross_requests: dict[str, Path] = {}
    build_requests: dict[str, Path] = {}
    all_entries = []
    for probe_id in ("runner", "selector"):
        approaches = []
        for approach_id in ("control", "variation"):
            source = sources[f"{probe_id}-{approach_id}"]
            build = _request(manifest_path, baseline, source, approach_id)
            build["probe_id"] = probe_id
            build_path = root / f"composition-build-{probe_id}-{approach_id}.json"
            _write_json(build_path, build)
            build_requests[f"{probe_id}-{approach_id}"] = build_path
            approaches.append({"approach_id": approach_id, "request": str(build_path)})
        cross_path = root / f"composition-cross-{probe_id}.json"
        _write_json(
            cross_path,
            {
                "schema_version": 1,
                "development_manifest": str(manifest_path),
                "probe_id": probe_id,
                "approach_build_requests": approaches,
                "evaluator": _evaluator(root),
            },
        )
        cross_requests[probe_id] = cross_path
        all_entries.append({"probe_id": probe_id, "request": str(cross_path)})
    all_path = root / "composition-all-probes.json"
    _write_json(
        all_path,
        {
            "schema_version": 1,
            "development_manifest": str(manifest_path),
            "probe_requests": all_entries,
        },
    )
    return manifest_path, baseline, all_path, sources, build_requests


def _compose_request(path: Path, manifest: Path, baseline: Path, candidates: Path) -> Path:
    _write_json(
        path,
        {
            "schema_version": 1,
            "development_manifest": str(manifest),
            "baseline": str(baseline),
            "promotion_candidates": str(candidates),
        },
    )
    return path


def _run_compose(request: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(COMPOSE), "run", str(request), str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _assembled_fixture(root: Path) -> tuple[Path, Path]:
    manifest, baseline, all_request, _, _ = _composition_fixture(root)
    probe_output = root / "final-all-probe-output"
    probes = _run_all_probes(all_request, probe_output)
    assert probes.returncode == 0, probes.stderr
    compose_request = _compose_request(
        root / "final-compose.json",
        manifest,
        baseline,
        probe_output / "promotion-candidates.json",
    )
    composition = root / "final-composition-output"
    composed = _run_compose(compose_request, composition)
    assert composed.returncode == 0, composed.stderr
    return manifest, composition / "assembly"


def _assessment_adapter(verdicts: dict[str, str], *, malformed: str | None = None) -> str:
    return f"""from __future__ import annotations
import json
import sys
from pathlib import Path

question = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
case_id = question["case_id"]
response = {{
    "case_id": case_id,
    "verdict": {verdicts!r}[case_id],
    "reason": "The recorded execution evidence determines this case.",
    "evidence_pointers": ["execution-result"],
}}
if {malformed!r} == "unknown-verdict":
    response["verdict"] = "looks-good"
elif {malformed!r} == "wrong-case":
    response["case_id"] = "another-case"
elif {malformed!r} == "missing-evidence":
    response["evidence_pointers"] = []
elif {malformed!r} == "ungrounded-evidence":
    response["evidence_pointers"] = ["not-presented"]
elif {malformed!r} == "status-only":
    response["evidence_pointers"] = ["execution-status"]
payload = [response] if {malformed!r} == "batch" else response
Path(sys.argv[2]).write_text(json.dumps(payload, sort_keys=True) + "\\n", encoding="utf-8")
"""


def _feature_assessment_adapter() -> str:
    return """from __future__ import annotations
import json
import sys
from pathlib import Path

question = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
features = question["execution_result"]["outcome"]["features"]
verdict = "satisfied" if question["case_id"] == "works" or features == ["runner-a", "selector-b"] else "not-satisfied"
response = {
    "case_id": question["case_id"],
    "verdict": verdict,
    "reason": f"Observed assembled features {features!r}.",
    "evidence_pointers": ["execution-result"],
}
Path(sys.argv[2]).write_text(json.dumps(response, sort_keys=True) + "\\n", encoding="utf-8")
"""


def _repair_planner_adapter() -> str:
    return """from __future__ import annotations
import json
import sys
from pathlib import Path

request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
allowed = request["allowed_paths"]
response = {
    "schema_version": 1,
    "approaches": [
        {
            "id": "retain-current",
            "hypothesis": "The current implementation is already correct.",
            "instructions": "Keep the current source unchanged.",
            "allowed_paths": allowed,
        },
        {
            "id": "correct-selector",
            "hypothesis": "Correcting the selected feature satisfies the failed evidence.",
            "instructions": "Return selector-b from feature_b.py.",
            "allowed_paths": allowed,
        },
    ],
}
Path(sys.argv[2]).write_text(json.dumps(response, sort_keys=True) + "\\n", encoding="utf-8")
"""


def _repair_builder_adapter() -> str:
    return """from __future__ import annotations
import json
import sys
from pathlib import Path

approach = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
candidate = Path(sys.argv[2])
if approach["id"] == "correct-selector":
    (candidate / "feature_b.py").write_text("def value():\\n    return 'selector-b'\\n", encoding="utf-8")
Path(sys.argv[3]).write_text(json.dumps({"status": "completed", "approach_id": approach["id"]}, sort_keys=True) + "\\n", encoding="utf-8")
"""


def _repair_routing_adapter() -> str:
    return """from __future__ import annotations
import json
import sys
from pathlib import Path

question = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
response = {
    "schema_version": 1,
    "question_id": question["question_id"],
    "answer": question["allowed_answers"][0],
}
Path(sys.argv[2]).write_text(json.dumps(response, sort_keys=True) + "\\n", encoding="utf-8")
"""


def _final_validation_request(path: Path, assembly: Path, adapter: Path) -> Path:
    _write_json(
        path,
        {
            "schema_version": 1,
            "assembly": str(assembly),
            "assessment": {
                "adapter": str(adapter),
                "command": [
                    "{python}",
                    "{assessment-adapter}",
                    "{assessment-request}",
                    "{assessment-response}",
                ],
            },
        },
    )
    return path


def _run_final_validation(request: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(FINAL_VALIDATION), "run", str(request), str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _whole_run_request(
    path: Path,
    all_probe_request: Path,
    baseline: Path,
    adapter: Path,
) -> Path:
    probes = json.loads(all_probe_request.read_text(encoding="utf-8"))
    manifest = Path(probes["development_manifest"])
    _write_json(
        path,
        {
            "schema_version": 1,
            "development_manifest": {
                "path": str(manifest),
                "sha256": _digest(manifest),
            },
            "baseline": {
                "path": str(baseline),
                "sha256": _source_digest(baseline),
            },
            "probe_requests": [
                {
                    "probe_id": item["probe_id"],
                    "request": item["request"],
                    "request_sha256": _digest(Path(item["request"])),
                }
                for item in probes["probe_requests"]
            ],
            "assessment": {
                "adapter": {
                    "path": str(adapter),
                    "sha256": _digest(adapter),
                },
                "command": [
                    "{python}",
                    "{assessment-adapter}",
                    "{assessment-request}",
                    "{assessment-response}",
                ],
            },
        },
    )
    return path


def _run_whole_process(request: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(FULL_RUN), "run", str(request), str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _run_repair_process(request: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REPAIR_RUN), "run", str(request), str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _cross_case_module():
    spec = importlib.util.spec_from_file_location("development_probe_cross_case", CROSS_CASE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(CROSS_CASE.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def _all_probe_module():
    spec = importlib.util.spec_from_file_location("development_probe_all_probes", ALL_PROBES)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ALL_PROBES.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def _final_validation_module():
    spec = importlib.util.spec_from_file_location("development_probe_final_validation", FINAL_VALIDATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(FINAL_VALIDATION.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def _whole_process_module():
    spec = importlib.util.spec_from_file_location("development_probe_run", FULL_RUN)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(FULL_RUN.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def _repair_process_module():
    spec = importlib.util.spec_from_file_location("development_probe_repair", REPAIR_RUN)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(REPAIR_RUN.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def test_build_is_write_once_and_verify_refuses_changed_candidate_source(tmp_path: Path) -> None:
    manifest, baseline, control, _ = _fixture(tmp_path)
    bundle = tmp_path / "bundle"
    request_path = tmp_path / "request.json"

    built = _build(_request(manifest, baseline, control, "control"), request_path, bundle)

    assert built.returncode == 0, built.stderr
    build_result = json.loads(built.stdout)
    assert build_result["status"] == "built"
    assert build_result["probe_id"] == "runner"
    assert build_result["approach_id"] == "control"
    assert len(build_result["bundle_sha256"]) == 64
    assert {path.name for path in bundle.iterdir()} == {
        "bundle.json",
        "development-manifest.json",
        "source",
    }
    assert all((path.stat().st_mode & 0o222) == 0 for path in bundle.rglob("*"))
    bundle_record = json.loads((bundle / "bundle.json").read_text())
    assert bundle_record["source"]["changed_paths"] == ["adapter.py"]
    assert bundle_record["source"]["baseline_files"]

    verified = subprocess.run(
        [sys.executable, str(CANDIDATE), "verify", str(bundle)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert verified.returncode == 0, verified.stderr
    assert json.loads(verified.stdout)["bundle_sha256"] == build_result["bundle_sha256"]

    duplicate = _build(
        _request(manifest, baseline, control, "control"),
        tmp_path / "duplicate-request.json",
        bundle,
    )
    assert duplicate.returncode == 2
    assert "already exists" in duplicate.stderr

    copied_source = bundle / "source" / "adapter.py"
    copied_source.chmod(0o644)
    copied_source.write_text(_adapter(99), encoding="utf-8")
    changed = subprocess.run(
        [sys.executable, str(CANDIDATE), "verify", str(bundle)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert changed.returncode == 2
    assert "changed" in changed.stderr


def test_build_refuses_every_changed_path_outside_probe_scope(tmp_path: Path) -> None:
    manifest, baseline, control, _ = _fixture(tmp_path)
    (control / "outside.txt").write_text("first unrelated change\n", encoding="utf-8")
    (control / "second.txt").write_text("second unrelated change\n", encoding="utf-8")

    completed = _build(
        _request(manifest, baseline, control, "control"),
        tmp_path / "outside-request.json",
        tmp_path / "outside-bundle",
    )

    assert completed.returncode == 2
    assert "outside.txt" in completed.stderr
    assert "second.txt" in completed.stderr
    assert "allowed_paths ['adapter.py']" in completed.stderr
    assert not (tmp_path / "outside-bundle").exists()


def test_verify_refuses_baseline_records_that_do_not_match_tree_digest(
    tmp_path: Path,
) -> None:
    manifest, baseline, control, _ = _fixture(tmp_path)
    bundle = tmp_path / "bundle"
    built = _build(
        _request(manifest, baseline, control, "control"),
        tmp_path / "request.json",
        bundle,
    )
    assert built.returncode == 0, built.stderr
    record_path = bundle / "bundle.json"
    record_path.chmod(0o644)
    record = json.loads(record_path.read_text())
    record["source"]["baseline_files"][0]["sha256"] = "0" * 64
    record_path.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    record_path.chmod(0o444)

    verified = subprocess.run(
        [sys.executable, str(CANDIDATE), "verify", str(bundle)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert verified.returncode == 2
    assert "baseline_files differ" in verified.stderr


def test_build_and_verify_refuse_symbolic_link_roots(tmp_path: Path) -> None:
    manifest, baseline, control, _ = _fixture(tmp_path)
    linked_source = tmp_path / "linked-source"
    linked_source.symlink_to(control, target_is_directory=True)

    built = _build(
        _request(manifest, baseline, linked_source, "control"),
        tmp_path / "linked-request.json",
        tmp_path / "linked-bundle",
    )

    assert built.returncode == 2
    assert "symbolic link" in built.stderr
    assert not (tmp_path / "linked-bundle").exists()

    real_bundle = tmp_path / "real-bundle"
    valid = _build(
        _request(manifest, baseline, control, "control"),
        tmp_path / "valid-request.json",
        real_bundle,
    )
    assert valid.returncode == 0, valid.stderr
    linked_bundle = tmp_path / "linked-bundle"
    linked_bundle.symlink_to(real_bundle, target_is_directory=True)
    verified = subprocess.run(
        [sys.executable, str(CANDIDATE), "verify", str(linked_bundle)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert verified.returncode == 2
    assert "stable directory" in verified.stderr


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda request: request.update({"approach_id": "missing"}), "declared"),
        (
            lambda request: request["execution"].update({"command": ["python adapter.py", "{candidate-entrypoint}"]}),
            "shell-like",
        ),
        (lambda request: request["execution"].pop("protocol"), "protocol"),
    ],
)
def test_build_refuses_invalid_identity_or_execution_contract(
    tmp_path: Path,
    mutate,
    message: str,
) -> None:
    manifest, baseline, control, _ = _fixture(tmp_path)
    request = _request(manifest, baseline, control, "control")
    mutate(request)

    completed = _build(request, tmp_path / "request.json", tmp_path / "bundle")

    assert completed.returncode == 2
    assert message in completed.stderr
    assert not (tmp_path / "bundle").exists()


def test_two_real_bundles_run_as_one_experiment_and_undeclared_case_is_refused(
    tmp_path: Path,
) -> None:
    manifest, baseline, control, variation = _fixture(tmp_path)
    bundles = {}
    for approach_id, source in (("control", control), ("variation", variation)):
        bundle = tmp_path / f"bundle-{approach_id}"
        built = _build(
            _request(manifest, baseline, source, approach_id),
            tmp_path / f"request-{approach_id}.json",
            bundle,
        )
        assert built.returncode == 0, built.stderr
        bundles[approach_id] = bundle

    spec = {
        "schema_version": 3,
        "experiment_id": "candidate-bundle-real-comparison",
        "hypothesis": "Both immutable candidates run and the declared quality metric selects variation.",
        "target": {
            "machinery": "experiment-machinery",
            "phase": "development-probe-candidate",
            "source": {
                "path": str(CANDIDATE.parent),
                "sha256": _source_digest(CANDIDATE.parent),
            },
            "entrypoint": CANDIDATE.name,
        },
        "frozen_input": {
            "path": json.loads(manifest.read_text())["atomic_step"]["captured_cases"][0]["source"],
            "sha256": json.loads(manifest.read_text())["atomic_step"]["captured_cases"][0]["sha256"],
        },
        "variants": [
            {
                "id": approach_id,
                "command": [sys.executable, str(CANDIDATE), "execute", str(bundle)],
                "adapter": {"path": str(CANDIDATE), "sha256": _digest(CANDIDATE)},
                "configuration": {"case_id": "works"},
            }
            for approach_id, bundle in bundles.items()
        ],
        "evaluation": {
            "metrics": [{"name": "quality", "direction": "maximize"}],
            "evaluator": _evaluator(tmp_path),
        },
    }
    spec_path = tmp_path / "experiment.json"
    spec_path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output = tmp_path / "run"

    completed = subprocess.run(
        [sys.executable, str(RUNNER), "--spec", str(spec_path), "--output", str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["champion"] == "variation"
    assert summary["promotion_applied"] is False
    assert [row["variant_id"] for row in summary["ranking"]] == ["variation", "control"]
    assert all(row["eligible"] for row in summary["variants"])
    for variant_id in ("control", "variation"):
        telemetry = (output / "variants" / variant_id / "telemetry.jsonl").read_text()
        assert "candidate_bundle_verified" in telemetry

    invalid_env = os.environ.copy()
    invalid_env.update(
        {
            "EXPERIMENT_ID": "candidate-bundle-real-comparison",
            "EXPERIMENT_VARIANT_ID": "control",
            "EXPERIMENT_WORK_DIR": str(tmp_path),
            "EXPERIMENT_INPUT_PATH": str(
                json.loads(manifest.read_text())["atomic_step"]["captured_cases"][0]["source"]
            ),
            "EXPERIMENT_VARIANT_PATH": str(tmp_path / "invalid-variant.json"),
            "EXPERIMENT_RESULT_PATH": str(tmp_path / "invalid-result.json"),
            "EXPERIMENT_TELEMETRY_PATH": str(tmp_path / "invalid-telemetry.jsonl"),
        }
    )
    (tmp_path / "invalid-variant.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "variant_id": "control",
                "configuration": {"case_id": "undeclared"},
            }
        ),
        encoding="utf-8",
    )
    refused = subprocess.run(
        [sys.executable, str(CANDIDATE), "execute", str(bundles["control"])],
        cwd=ROOT,
        env=invalid_env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert refused.returncode == 2
    assert "undeclared" in refused.stderr
    assert not (tmp_path / "invalid-result.json").exists()


def test_launcher_runs_every_approach_and_preserves_exact_recommendation(
    tmp_path: Path,
) -> None:
    manifest, baseline, control, variation = _fixture(tmp_path)
    request_path, _ = _launcher_request(tmp_path, manifest, baseline, {"control": control, "variation": variation})
    output = tmp_path / "launch-output"

    completed = _launch(request_path, output)

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["status"] == "recommended"
    assert result["approach_id"] == "variation"
    assert result["promotion_applied"] is False
    recommendation = json.loads((output / "recommendation.json").read_text())
    assert recommendation == result
    assert recommendation["variant_id"] == "variation-2"
    assert recommendation["case_id"] == "works"
    assert len(recommendation["bundle_sha256"]) == 64
    assert (output / "bundles" / "control" / "bundle.json").is_file()
    assert (output / "bundles" / "variation" / "bundle.json").is_file()
    build_results = json.loads((output / "build-results.json").read_text())
    assert [item["status"] for item in build_results["results"]] == ["built", "built"]
    assert len({item["candidate_sha256"] for item in build_results["results"]}) == 2
    summary = json.loads((output / "experiment" / "summary.json").read_text())
    assert summary["champion"] == "variation-2"
    assert all(row["eligible"] for row in summary["variants"])
    assert json.loads((output / "launch-summary.json").read_text())["status"] == "completed"

    repeated = _launch(request_path, output)
    assert repeated.returncode == 2
    assert "new" in repeated.stderr or "empty" in repeated.stderr


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda request: request["approach_build_requests"].pop(), "missing"),
        (lambda request: request.update({"case_id": "unknown"}), "undeclared"),
    ],
)
def test_launcher_refuses_incomplete_approaches_or_undeclared_case_with_evidence(
    tmp_path: Path,
    mutation,
    message: str,
) -> None:
    manifest, baseline, control, variation = _fixture(tmp_path)
    request_path, request = _launcher_request(
        tmp_path, manifest, baseline, {"control": control, "variation": variation}
    )
    mutation(request)
    _write_json(request_path, request)
    output = tmp_path / "launch-output"

    completed = _launch(request_path, output)

    assert completed.returncode == 2
    assert message in completed.stderr
    failure = json.loads((output / "launch-summary.json").read_text())
    assert failure["status"] == "failed"
    assert message in failure["error"]
    assert not (output / "recommendation.json").exists()
    assert not (output / "experiment").exists()


def test_launcher_refuses_byte_identical_candidates_before_experiment(
    tmp_path: Path,
) -> None:
    manifest, baseline, control, variation = _fixture(tmp_path)
    (variation / "adapter.py").write_bytes((control / "adapter.py").read_bytes())
    request_path, _ = _launcher_request(
        tmp_path, manifest, baseline, {"control": control, "variation": variation}
    )
    output = tmp_path / "launch-output"

    completed = _launch(request_path, output)

    assert completed.returncode == 2
    assert "byte-identical" in completed.stderr
    failure = json.loads((output / "launch-summary.json").read_text())
    assert failure["status"] == "failed"
    assert failure["stage"] == "validate-distinct-candidates"
    build_results = json.loads((output / "build-results.json").read_text())
    assert [item["status"] for item in build_results["results"]] == ["built", "built"]
    assert len({item["candidate_sha256"] for item in build_results["results"]}) == 1
    assert not (output / "experiment").exists()
    assert not (output / "recommendation.json").exists()


def test_launcher_preserves_all_build_results_and_does_not_run_incomplete_set(
    tmp_path: Path,
) -> None:
    manifest, baseline, control, variation = _fixture(tmp_path)
    request_path, request = _launcher_request(
        tmp_path, manifest, baseline, {"control": control, "variation": variation}
    )
    broken_path = Path(request["approach_build_requests"][1]["request"])
    broken = json.loads(broken_path.read_text())
    broken["execution"].pop("protocol")
    _write_json(broken_path, broken)
    output = tmp_path / "launch-output"

    completed = _launch(request_path, output)

    assert completed.returncode == 2
    failure = json.loads((output / "launch-summary.json").read_text())
    assert failure["status"] == "failed"
    assert failure["stage"] == "build-candidates"
    assert (output / "bundles" / "control" / "bundle.json").is_file()
    build_results = json.loads((output / "build-results.json").read_text())
    assert [item["status"] for item in build_results["results"]] == [
        "built",
        "build-refused",
    ]
    assert (output / "builds" / "variation" / "stderr.txt").is_file()
    assert "protocol" in (output / "builds" / "variation" / "stderr.txt").read_text()
    assert not (output / "experiment").exists()
    assert not (output / "recommendation.json").exists()


def test_launcher_refuses_partial_experiment_when_candidate_changes_its_bundle(
    tmp_path: Path,
) -> None:
    manifest, baseline, control, variation = _fixture(tmp_path)
    (variation / "adapter.py").write_text(
        _adapter(2)
        + """\nself_path = Path(__file__)\nself_path.chmod(0o644)\nself_path.write_text("changed during execution\\n", encoding="utf-8")\n""",
        encoding="utf-8",
    )
    request_path, _ = _launcher_request(tmp_path, manifest, baseline, {"control": control, "variation": variation})
    output = tmp_path / "launch-output"

    completed = _launch(request_path, output)

    assert completed.returncode == 2
    failure = json.loads((output / "launch-summary.json").read_text())
    assert failure["status"] == "failed"
    assert failure["stage"] == "verify-experiment"
    summary = json.loads((output / "experiment" / "summary.json").read_text())
    changed = next(row for row in summary["variants"] if row["variant_id"] == "variation-2")
    assert changed["eligible"] is False
    assert not (output / "recommendation.json").exists()


def test_cross_case_launcher_aggregates_every_case_into_one_probe_winner(
    tmp_path: Path,
) -> None:
    manifest, baseline, control, variation = _fixture(tmp_path)
    (control / "adapter.py").write_text(_case_scored_adapter({"works": 10, "refuses": 0}), encoding="utf-8")
    (variation / "adapter.py").write_text(_case_scored_adapter({"works": 4, "refuses": 8}), encoding="utf-8")
    request = _cross_case_request(tmp_path, manifest, baseline, {"control": control, "variation": variation})
    output = tmp_path / "cross-output"
    repeat_output = tmp_path / "cross-output-repeat"

    completed = _run_cross_case(request, output)
    repeated = _run_cross_case(request, repeat_output)

    assert completed.returncode == 0, completed.stderr
    assert repeated.returncode == 0, repeated.stderr
    recommendation = json.loads(completed.stdout)
    assert json.loads(repeated.stdout) == recommendation
    assert recommendation["status"] == "recommended"
    assert recommendation["approach_id"] == "variation"
    assert recommendation["aggregated_metrics"] == {"quality": 12.0}
    assert recommendation["case_ids"] == ["works", "refuses"]
    assert recommendation["case_count"] == 2
    assert recommendation["promotion_applied"] is False
    assert json.loads((output / "recommendation.json").read_text()) == recommendation
    assert json.loads((output / "cases" / "works" / "experiment" / "summary.json").read_text())["champion"] == "control"
    assert (
        json.loads((output / "cases" / "refuses" / "experiment" / "summary.json").read_text())["champion"]
        == "variation-2"
    )
    case_results = json.loads((output / "case-results.json").read_text())
    assert [item["case_id"] for item in case_results["results"]] == [
        "works",
        "refuses",
    ]
    assert all(item["status"] == "completed" for item in case_results["results"])


def test_cross_case_launcher_preserves_successful_case_when_another_case_fails(
    tmp_path: Path,
) -> None:
    manifest, baseline, control, variation = _fixture(tmp_path)
    captured = json.loads(manifest.read_text())["atomic_step"]["captured_cases"]
    Path(captured[1]["source"]).unlink()
    request = _cross_case_request(tmp_path, manifest, baseline, {"control": control, "variation": variation})
    output = tmp_path / "cross-output"

    completed = _run_cross_case(request, output)

    assert completed.returncode == 2
    failure = json.loads((output / "cross-case-summary.json").read_text())
    assert failure["status"] == "failed"
    assert failure["stage"] == "run-cases"
    results = json.loads((output / "case-results.json").read_text())["results"]
    assert [item["status"] for item in results] == ["completed", "failed"]
    assert (output / "cases" / "works" / "experiment" / "summary.json").is_file()
    assert (output / "case-logs" / "refuses" / "stderr.txt").is_file()
    assert not (output / "recommendation.json").exists()


def test_cross_case_launcher_refuses_undeclared_aggregation_with_evidence(
    tmp_path: Path,
) -> None:
    manifest, baseline, control, variation = _fixture(tmp_path)
    value = json.loads(manifest.read_text())
    value["mini_probes"][0]["evaluation"]["across_cases"][0]["method"] = "median"
    _write_json(manifest, value)
    request = _cross_case_request(tmp_path, manifest, baseline, {"control": control, "variation": variation})
    output = tmp_path / "cross-output"

    completed = _run_cross_case(request, output)

    assert completed.returncode == 2
    failure = json.loads((output / "cross-case-summary.json").read_text())
    assert failure["status"] == "failed"
    assert failure["stage"] == "validate-request"
    assert "sum" in failure["error"]
    assert not (output / "cases").exists()
    assert not (output / "recommendation.json").exists()


def test_cross_case_binding_refuses_differing_bundle_digests(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _cross_case_module()
    monkeypatch.setattr(
        module,
        "_fresh_digest",
        lambda path: "a" * 64 if "works" in path.parts else "b" * 64,
    )
    mappings = {
        case_id: {
            "control": {
                "bundle": "bundles/control",
                "bundle_sha256": "a" * 64 if case_id == "works" else "b" * 64,
            }
        }
        for case_id in ("works", "refuses")
    }
    aggregate = {
        "champion": "control",
        "ranking": [{"rank": 1, "approach_id": "control", "aggregated_metrics": {"quality": 2.0}}],
    }

    with pytest.raises(module.CrossCaseError, match="differing bundle digests"):
        module._bind_recommendation(
            tmp_path,
            {"atomic_step": {"id": "candidate-bundle"}},
            {"id": "runner"},
            ["works", "refuses"],
            aggregate,
            mappings,
        )


def test_all_probe_launcher_returns_one_verified_candidate_per_probe(
    tmp_path: Path,
) -> None:
    manifest, baseline, control, variation = _fixture(tmp_path)
    (control / "adapter.py").write_text(_case_scored_adapter({"works": 10, "refuses": 0}), encoding="utf-8")
    (variation / "adapter.py").write_text(_case_scored_adapter({"works": 4, "refuses": 8}), encoding="utf-8")
    request, _ = _all_probe_request(tmp_path, manifest, baseline, {"control": control, "variation": variation})
    output = tmp_path / "all-output"
    repeat = tmp_path / "all-output-repeat"

    completed = _run_all_probes(request, output)
    repeated = _run_all_probes(request, repeat)

    assert completed.returncode == 0, completed.stderr
    assert repeated.returncode == 0, repeated.stderr
    candidates = json.loads(completed.stdout)
    assert json.loads(repeated.stdout) == candidates
    assert candidates["status"] == "candidates-ready"
    assert candidates["promotion_applied"] is False
    assert [item["probe_id"] for item in candidates["candidates"]] == [
        "runner",
        "selector",
    ]
    assert [item["artifact"] for item in candidates["candidates"]] == [
        "runner-candidate",
        "selector-candidate",
    ]
    assert all(item["approach_id"] == "variation" for item in candidates["candidates"])
    assert all(len(item["bundle_sha256"]) == 64 for item in candidates["candidates"])
    assert all(
        (output / "probes" / probe_id / "cross-case-summary.json").is_file() for probe_id in ("runner", "selector")
    )
    results = json.loads((output / "probe-results.json").read_text())["results"]
    assert [item["probe_id"] for item in results] == ["runner", "selector"]
    assert all(item["status"] == "completed" for item in results)


def test_all_probe_launcher_preserves_success_when_another_probe_fails(
    tmp_path: Path,
) -> None:
    manifest, baseline, control, variation = _fixture(tmp_path)
    request, cross = _all_probe_request(tmp_path, manifest, baseline, {"control": control, "variation": variation})
    selector = json.loads(cross["selector"].read_text())
    broken_build = Path(selector["approach_build_requests"][1]["request"])
    broken = json.loads(broken_build.read_text())
    broken["source"]["candidate"] = str(tmp_path / "missing-candidate")
    _write_json(broken_build, broken)
    output = tmp_path / "all-output"

    completed = _run_all_probes(request, output)

    assert completed.returncode == 2
    summary = json.loads((output / "all-probes-summary.json").read_text())
    assert summary["status"] == "failed"
    assert summary["stage"] == "run-probes"
    results = json.loads((output / "probe-results.json").read_text())["results"]
    assert [item["status"] for item in results] == ["completed", "failed"]
    assert (output / "probes" / "runner" / "recommendation.json").is_file()
    assert (output / "probe-logs" / "selector" / "stderr.txt").is_file()
    assert not (output / "promotion-candidates.json").exists()


def test_all_probe_launcher_refuses_substituted_probe_request_before_launch(
    tmp_path: Path,
) -> None:
    manifest, baseline, control, variation = _fixture(tmp_path)
    request, _ = _all_probe_request(tmp_path, manifest, baseline, {"control": control, "variation": variation})
    value = json.loads(request.read_text())
    value["probe_requests"][1]["probe_id"] = "ghost"
    _write_json(request, value)
    output = tmp_path / "all-output"

    completed = _run_all_probes(request, output)

    assert completed.returncode == 2
    summary = json.loads((output / "all-probes-summary.json").read_text())
    assert summary["stage"] == "validate-request"
    assert "ghost" in summary["error"]
    assert "selector" in summary["error"]
    assert not (output / "probes").exists()
    assert not (output / "promotion-candidates.json").exists()


def test_all_probe_binding_refuses_candidate_changed_after_probe_run(
    tmp_path: Path,
) -> None:
    manifest_path, baseline, control, variation = _fixture(tmp_path)
    request, _ = _all_probe_request(
        tmp_path,
        manifest_path,
        baseline,
        {"control": control, "variation": variation},
    )
    output = tmp_path / "all-output"
    completed = _run_all_probes(request, output)
    assert completed.returncode == 0, completed.stderr
    module = _all_probe_module()
    manifest = json.loads(manifest_path.read_text())
    results = json.loads((output / "probe-results.json").read_text())["results"]
    summary_path = output / "probes" / "runner" / "cross-case-summary.json"
    summary = json.loads(summary_path.read_text())
    summary["promotion_applied"] = True
    _write_json(summary_path, summary)

    with pytest.raises(module.AllProbeError, match="summary promotion_applied"):
        module._bind_candidates(output, manifest, results)

    summary["promotion_applied"] = False
    _write_json(summary_path, summary)
    changed = output / "probes" / "runner" / "cases" / "works" / "bundles" / "variation" / "source" / "adapter.py"
    changed.chmod(0o644)
    changed.write_text(_adapter(99), encoding="utf-8")

    with pytest.raises(module.AllProbeError, match="candidate file size changed"):
        module._bind_candidates(output, manifest, results)


def test_composer_combines_disjoint_winners_into_one_runnable_candidate(
    tmp_path: Path,
) -> None:
    manifest, baseline, all_request, _, _ = _composition_fixture(tmp_path)
    probe_output = tmp_path / "all-probe-output"
    probes = _run_all_probes(all_request, probe_output)
    assert probes.returncode == 0, probes.stderr
    request = _compose_request(
        tmp_path / "compose.json",
        manifest,
        baseline,
        probe_output / "promotion-candidates.json",
    )
    output = tmp_path / "composition-output"
    repeat = tmp_path / "composition-output-repeat"

    completed = _run_compose(request, output)
    repeated = _run_compose(request, repeat)

    assert completed.returncode == 0, completed.stderr
    assert repeated.returncode == 0, repeated.stderr
    assembly = json.loads(completed.stdout)
    repeated_assembly = json.loads(repeated.stdout)
    assert assembly == repeated_assembly
    assert assembly["status"] == "assembled"
    assert assembly["promotion_applied"] is False
    assert [item["probe_id"] for item in assembly["candidates"]] == [
        "runner",
        "selector",
    ]
    assert (output / "assembly" / "source" / "feature_a.py").read_text().find("runner-a") >= 0
    assert (output / "assembly" / "source" / "feature_b.py").read_text().find("selector-b") >= 0
    execution = subprocess.run(
        [
            sys.executable,
            str(COMPOSE),
            "execute",
            str(output / "assembly"),
            "works",
            str(tmp_path / "assembled-execution"),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert execution.returncode == 0, execution.stderr
    result = json.loads(execution.stdout)
    assert result["outcome"]["features"] == ["runner-a", "selector-b"]


def test_composer_refuses_incompatible_winner_changes(
    tmp_path: Path,
) -> None:
    manifest, baseline, all_request, sources, _ = _composition_fixture(tmp_path)
    manifest_value = json.loads(manifest.read_text())
    manifest_value["mini_probes"][1]["allowed_paths"].append("feature_a.py")
    _write_json(manifest, manifest_value)
    (sources["selector-variation"] / "feature_a.py").write_text(
        "def value():\n    return 'selector-a'\n", encoding="utf-8"
    )
    (sources["selector-variation"] / "feature_b.py").write_text("def value():\n    return 'base-b'\n", encoding="utf-8")
    probe_output = tmp_path / "all-probe-output"
    probes = _run_all_probes(all_request, probe_output)
    assert probes.returncode == 0, probes.stderr
    request = _compose_request(
        tmp_path / "compose.json",
        manifest,
        baseline,
        probe_output / "promotion-candidates.json",
    )
    output = tmp_path / "composition-output"

    completed = _run_compose(request, output)

    assert completed.returncode == 2
    summary = json.loads((output / "composition-summary.json").read_text())
    assert summary["stage"] == "merge-winners"
    assert "feature_a.py" in summary["error"]
    assert "runner" in summary["error"]
    assert "selector" in summary["error"]
    assert not (output / "assembly").exists()


def test_composer_refuses_winners_with_different_execution_contracts(
    tmp_path: Path,
) -> None:
    manifest, baseline, all_request, _, build_requests = _composition_fixture(tmp_path)
    selector_build = build_requests["selector-variation"]
    value = json.loads(selector_build.read_text())
    value["execution"]["command"].append("selector-mode")
    _write_json(selector_build, value)
    probe_output = tmp_path / "all-probe-output"
    probes = _run_all_probes(all_request, probe_output)
    assert probes.returncode == 0, probes.stderr
    request = _compose_request(
        tmp_path / "compose.json",
        manifest,
        baseline,
        probe_output / "promotion-candidates.json",
    )
    output = tmp_path / "composition-output"

    completed = _run_compose(request, output)

    assert completed.returncode == 2
    summary = json.loads((output / "composition-summary.json").read_text())
    assert summary["stage"] == "bind-execution"
    assert "execution contracts differ" in summary["error"]
    assert not (output / "assembly").exists()


def test_composer_refuses_baseline_changed_after_candidates_were_built(
    tmp_path: Path,
) -> None:
    manifest, baseline, all_request, _, _ = _composition_fixture(tmp_path)
    probe_output = tmp_path / "all-probe-output"
    probes = _run_all_probes(all_request, probe_output)
    assert probes.returncode == 0, probes.stderr
    (baseline / "feature_a.py").write_text("def value():\n    return 'changed-after-proof'\n", encoding="utf-8")
    request = _compose_request(
        tmp_path / "compose.json",
        manifest,
        baseline,
        probe_output / "promotion-candidates.json",
    )
    output = tmp_path / "composition-output"

    completed = _run_compose(request, output)

    assert completed.returncode == 2
    summary = json.loads((output / "composition-summary.json").read_text())
    assert summary["stage"] == "verify-inputs"
    assert "baseline" in summary["error"]
    assert "changed" in summary["error"]
    assert not (output / "assembly").exists()


def test_composer_refuses_unsafe_execution_contract_added_after_assembly(
    tmp_path: Path,
) -> None:
    manifest, baseline, all_request, _, _ = _composition_fixture(tmp_path)
    probe_output = tmp_path / "all-probe-output"
    probes = _run_all_probes(all_request, probe_output)
    assert probes.returncode == 0, probes.stderr
    request = _compose_request(
        tmp_path / "compose.json",
        manifest,
        baseline,
        probe_output / "promotion-candidates.json",
    )
    output = tmp_path / "composition-output"
    completed = _run_compose(request, output)
    assert completed.returncode == 0, completed.stderr
    assembly_path = output / "assembly" / "assembly.json"
    assembly_path.chmod(0o644)
    assembly = json.loads(assembly_path.read_text())
    assembly["execution"]["command"] = ["sh; unsafe", "{candidate-entrypoint}"]
    _write_json(assembly_path, assembly)
    assembly_path.chmod(0o444)

    verified = subprocess.run(
        [sys.executable, str(COMPOSE), "verify", str(output / "assembly")],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert verified.returncode == 2
    assert "execution contract is invalid" in verified.stderr


def test_composer_does_not_add_failure_evidence_to_an_occupied_output(
    tmp_path: Path,
) -> None:
    manifest, baseline, _, _, _ = _composition_fixture(tmp_path)
    request = _compose_request(
        tmp_path / "compose.json",
        manifest,
        baseline,
        tmp_path / "not-needed-because-output-is-occupied.json",
    )
    output = tmp_path / "occupied-output"
    output.mkdir()
    sentinel = output / "owner.txt"
    sentinel.write_text("keep\n", encoding="utf-8")

    completed = _run_compose(request, output)

    assert completed.returncode == 2
    assert sentinel.read_text(encoding="utf-8") == "keep\n"
    assert sorted(path.name for path in output.iterdir()) == ["owner.txt"]


def test_final_validation_returns_pass_only_when_every_declared_case_is_satisfied(
    tmp_path: Path,
) -> None:
    _, assembly = _assembled_fixture(tmp_path)
    adapter = tmp_path / "assess.py"
    adapter.write_text(
        _assessment_adapter({"works": "satisfied", "refuses": "satisfied"}),
        encoding="utf-8",
    )
    request = _final_validation_request(tmp_path / "final-validation.json", assembly, adapter)
    output = tmp_path / "final-validation-output"
    repeat = tmp_path / "final-validation-repeat"

    completed = _run_final_validation(request, output)
    repeated = _run_final_validation(request, repeat)

    assert completed.returncode == 0, completed.stderr
    assert repeated.returncode == 0, repeated.stderr
    verdict = json.loads(completed.stdout)
    assert json.loads(repeated.stdout) == verdict
    assert verdict["verdict"] == "passed"
    assert verdict["promotion_applied"] is False
    assert [item["case_id"] for item in verdict["cases"]] == ["works", "refuses"]
    assert all(item["verdict"] == "satisfied" for item in verdict["cases"])
    results = json.loads((output / "case-results.json").read_text())
    assert [item["case_id"] for item in results["results"]] == ["works", "refuses"]
    assert all(item["status"] == "completed" for item in results["results"])


def test_final_validation_returns_failed_when_one_case_is_not_satisfied(
    tmp_path: Path,
) -> None:
    _, assembly = _assembled_fixture(tmp_path)
    adapter = tmp_path / "assess.py"
    adapter.write_text(
        _assessment_adapter({"works": "satisfied", "refuses": "not-satisfied"}),
        encoding="utf-8",
    )
    request = _final_validation_request(tmp_path / "final-validation.json", assembly, adapter)
    output = tmp_path / "final-validation-output"

    completed = _run_final_validation(request, output)

    assert completed.returncode == 0, completed.stderr
    verdict = json.loads(completed.stdout)
    assert verdict["verdict"] == "failed"
    assert next(item for item in verdict["cases"] if item["case_id"] == "refuses")["verdict"] == "not-satisfied"
    assert verdict["promotion_applied"] is False


def test_final_validation_returns_inconclusive_when_evidence_cannot_decide(
    tmp_path: Path,
) -> None:
    _, assembly = _assembled_fixture(tmp_path)
    adapter = tmp_path / "assess.py"
    adapter.write_text(
        _assessment_adapter({"works": "satisfied", "refuses": "cannot-assess"}),
        encoding="utf-8",
    )
    request = _final_validation_request(tmp_path / "final-validation.json", assembly, adapter)

    completed = _run_final_validation(request, tmp_path / "final-validation-output")

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["verdict"] == "inconclusive"


@pytest.mark.parametrize(
    ("malformed", "message"),
    [
        ("unknown-verdict", "allowed verdicts"),
        ("wrong-case", "case identity"),
        ("missing-evidence", "evidence"),
        ("ungrounded-evidence", "not grounded"),
        ("status-only", "satisfied verdict"),
        ("batch", "one object"),
    ],
)
def test_final_validation_refuses_invalid_model_answer_and_preserves_case_runs(
    tmp_path: Path, malformed: str, message: str
) -> None:
    _, assembly = _assembled_fixture(tmp_path)
    adapter = tmp_path / "assess.py"
    adapter.write_text(
        _assessment_adapter(
            {"works": "satisfied", "refuses": "satisfied"},
            malformed=malformed,
        ),
        encoding="utf-8",
    )
    request = _final_validation_request(tmp_path / "final-validation.json", assembly, adapter)
    output = tmp_path / "final-validation-output"

    completed = _run_final_validation(request, output)

    assert completed.returncode == 2
    assert message in completed.stderr
    summary = json.loads((output / "final-validation-summary.json").read_text())
    assert summary["stage"] == "assess-cases"
    assert (output / "case-results.json").is_file()
    assert not (output / "final-verdict.json").exists()


def test_final_validation_cannot_pass_an_incomplete_execution() -> None:
    module = _final_validation_module()
    question = {
        "case_id": "works",
        "allowed_verdicts": ["not-satisfied", "cannot-assess"],
        "execution_evidence": [{"id": "execution-status", "value": "incomplete"}],
    }
    response = {
        "case_id": "works",
        "verdict": "satisfied",
        "reason": "Treat the incomplete run as enough.",
        "evidence_pointers": ["execution-status"],
    }

    with pytest.raises(module.FinalValidationError, match="allowed verdicts"):
        module._validate_response(response, question)


def test_whole_process_runs_from_probe_experiments_to_passed_verdict(
    tmp_path: Path,
) -> None:
    _, baseline, all_request, _, _ = _composition_fixture(tmp_path)
    adapter = tmp_path / "assess.py"
    adapter.write_text(
        _assessment_adapter({"works": "satisfied", "refuses": "satisfied"}),
        encoding="utf-8",
    )
    request = _whole_run_request(tmp_path / "development-probe-run.json", all_request, baseline, adapter)
    output = tmp_path / "development-probe-output"
    repeat = tmp_path / "development-probe-repeat"

    completed = _run_whole_process(request, output)
    repeated = _run_whole_process(request, repeat)

    assert completed.returncode == 0, completed.stderr
    assert repeated.returncode == 0, repeated.stderr
    verdict = json.loads(completed.stdout)
    assert json.loads(repeated.stdout) == verdict
    assert verdict["verdict"] == "passed"
    assert verdict["promotion_applied"] is False
    assert json.loads((output / "final-verdict.json").read_text()) == verdict
    summary = json.loads((output / "development-probe-summary.json").read_text())
    assert summary["status"] == "completed"
    assert summary["verdict"] == "passed"
    assert [item["stage"] for item in summary["stages"]] == [
        "run-probes",
        "compose-winners",
        "final-validation",
    ]
    assert all(item["status"] == "completed" for item in summary["stages"])
    assert (output / "probes" / "promotion-candidates.json").is_file()
    assert (output / "composition" / "assembly" / "assembly.json").is_file()
    assert (output / "validation" / "final-verdict.json").is_file()


def test_whole_process_returns_semantic_failed_verdict_without_treating_it_as_a_run_error(
    tmp_path: Path,
) -> None:
    _, baseline, all_request, _, _ = _composition_fixture(tmp_path)
    adapter = tmp_path / "assess.py"
    adapter.write_text(
        _assessment_adapter({"works": "satisfied", "refuses": "not-satisfied"}),
        encoding="utf-8",
    )
    request = _whole_run_request(tmp_path / "run.json", all_request, baseline, adapter)
    output = tmp_path / "output"

    completed = _run_whole_process(request, output)

    assert completed.returncode == 0, completed.stderr
    verdict = json.loads(completed.stdout)
    assert verdict["verdict"] == "failed"
    assert json.loads((output / "development-probe-summary.json").read_text())["status"] == "completed"


def test_whole_process_returns_inconclusive_verdict_without_treating_it_as_a_run_error(
    tmp_path: Path,
) -> None:
    _, baseline, all_request, _, _ = _composition_fixture(tmp_path)
    adapter = tmp_path / "assess.py"
    adapter.write_text(
        _assessment_adapter({"works": "satisfied", "refuses": "cannot-assess"}),
        encoding="utf-8",
    )
    request = _whole_run_request(tmp_path / "run.json", all_request, baseline, adapter)

    completed = _run_whole_process(request, tmp_path / "output")

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["verdict"] == "inconclusive"


def test_whole_process_refuses_changed_bound_input_before_launch(tmp_path: Path) -> None:
    _, baseline, all_request, _, _ = _composition_fixture(tmp_path)
    adapter = tmp_path / "assess.py"
    adapter.write_text(
        _assessment_adapter({"works": "satisfied", "refuses": "satisfied"}),
        encoding="utf-8",
    )
    request = _whole_run_request(tmp_path / "run.json", all_request, baseline, adapter)
    value = json.loads(request.read_text())
    value["probe_requests"][1]["request_sha256"] = "0" * 64
    _write_json(request, value)
    output = tmp_path / "output"

    completed = _run_whole_process(request, output)

    assert completed.returncode == 2
    summary = json.loads((output / "development-probe-summary.json").read_text())
    assert summary["stage"] == "validate-request"
    assert "probe_requests[1].request" in summary["error"]
    assert "SHA-256" in summary["error"]
    assert not (output / "probes").exists()
    assert not (output / "composition").exists()
    assert not (output / "validation").exists()


def test_whole_process_stops_after_probe_failure_and_preserves_probe_evidence(
    tmp_path: Path,
) -> None:
    _, baseline, all_request, _, build_requests = _composition_fixture(tmp_path)
    broken_path = build_requests["selector-variation"]
    broken = json.loads(broken_path.read_text())
    broken["source"]["candidate"] = str(tmp_path / "missing-candidate")
    _write_json(broken_path, broken)
    adapter = tmp_path / "assess.py"
    adapter.write_text(
        _assessment_adapter({"works": "satisfied", "refuses": "satisfied"}),
        encoding="utf-8",
    )
    request = _whole_run_request(tmp_path / "run.json", all_request, baseline, adapter)
    output = tmp_path / "output"

    completed = _run_whole_process(request, output)

    assert completed.returncode == 2
    summary = json.loads((output / "development-probe-summary.json").read_text())
    assert summary["status"] == "failed"
    assert summary["stage"] == "run-probes"
    assert (output / "probes" / "probe-results.json").is_file()
    assert not (output / "composition").exists()
    assert not (output / "validation").exists()
    assert not (output / "final-verdict.json").exists()


def test_whole_process_stops_after_composition_conflict_and_preserves_probe_evidence(
    tmp_path: Path,
) -> None:
    manifest, baseline, all_request, sources, _ = _composition_fixture(tmp_path)
    manifest_value = json.loads(manifest.read_text())
    manifest_value["mini_probes"][1]["allowed_paths"].append("feature_a.py")
    _write_json(manifest, manifest_value)
    (sources["selector-variation"] / "feature_a.py").write_text(
        "def value():\n    return 'selector-a'\n", encoding="utf-8"
    )
    (sources["selector-variation"] / "feature_b.py").write_text("def value():\n    return 'base-b'\n", encoding="utf-8")
    adapter = tmp_path / "assess.py"
    adapter.write_text(
        _assessment_adapter({"works": "satisfied", "refuses": "satisfied"}),
        encoding="utf-8",
    )
    request = _whole_run_request(tmp_path / "run.json", all_request, baseline, adapter)
    output = tmp_path / "output"

    completed = _run_whole_process(request, output)

    assert completed.returncode == 2
    summary = json.loads((output / "development-probe-summary.json").read_text())
    assert summary["stage"] == "compose-winners"
    assert "feature_a.py" in summary["error"]
    assert (output / "probes" / "promotion-candidates.json").is_file()
    assert (output / "composition" / "composition-summary.json").is_file()
    assert not (output / "validation").exists()
    assert not (output / "final-verdict.json").exists()


def test_whole_process_preserves_upstream_evidence_when_assessment_is_invalid(
    tmp_path: Path,
) -> None:
    _, baseline, all_request, _, _ = _composition_fixture(tmp_path)
    adapter = tmp_path / "assess.py"
    adapter.write_text(
        _assessment_adapter({"works": "satisfied", "refuses": "satisfied"}, malformed="batch"),
        encoding="utf-8",
    )
    request = _whole_run_request(tmp_path / "run.json", all_request, baseline, adapter)
    output = tmp_path / "output"

    completed = _run_whole_process(request, output)

    assert completed.returncode == 2
    summary = json.loads((output / "development-probe-summary.json").read_text())
    assert summary["stage"] == "final-validation"
    assert (output / "probes" / "promotion-candidates.json").is_file()
    assert (output / "composition" / "assembly" / "assembly.json").is_file()
    assert (output / "validation" / "case-results.json").is_file()
    assert not (output / "final-verdict.json").exists()


def test_whole_process_does_not_touch_an_occupied_output(tmp_path: Path) -> None:
    request = tmp_path / "unused.json"
    request.write_text("{}\n", encoding="utf-8")
    output = tmp_path / "occupied"
    output.mkdir()
    sentinel = output / "owner.txt"
    sentinel.write_text("keep\n", encoding="utf-8")

    completed = _run_whole_process(request, output)

    assert completed.returncode == 2
    assert sentinel.read_text(encoding="utf-8") == "keep\n"
    assert sorted(path.name for path in output.iterdir()) == ["owner.txt"]


def test_whole_process_final_binding_refuses_changed_verdict_artifact(
    tmp_path: Path,
) -> None:
    _, baseline, all_request, _, _ = _composition_fixture(tmp_path)
    adapter = tmp_path / "assess.py"
    adapter.write_text(
        _assessment_adapter({"works": "satisfied", "refuses": "satisfied"}),
        encoding="utf-8",
    )
    request = _whole_run_request(tmp_path / "run.json", all_request, baseline, adapter)
    output = tmp_path / "output"
    completed = _run_whole_process(request, output)
    assert completed.returncode == 0, completed.stderr
    receipt = json.loads((output / "stage-receipts" / "final-validation" / "receipt.json").read_text())
    normalized = json.loads((output / "development-probe-request.json").read_text())
    artifact = output / "validation" / "final-verdict.json"
    artifact.chmod(0o644)
    value = json.loads(artifact.read_text())
    value["verdict"] = "failed"
    _write_json(artifact, value)

    module = _whole_process_module()
    with pytest.raises(module.DevelopmentProbeRunError, match="require recorded"):
        module._bind_final_result(output, normalized, receipt)


def test_repair_process_rebuilds_only_failed_probe_and_returns_passed_atomic_result(
    tmp_path: Path,
) -> None:
    manifest, baseline, all_request, sources, _ = _composition_fixture(tmp_path)
    manifest_value = json.loads(manifest.read_text(encoding="utf-8"))
    manifest_value["mini_probes"][0]["inputs"] = [{"case_id": "works"}]
    manifest_value["mini_probes"][1]["inputs"] = [{"case_id": "refuses"}]
    _write_json(manifest, manifest_value)
    (sources["selector-variation"] / "feature_b.py").write_text(
        "def value():\n    return 'broken-b'\n", encoding="utf-8"
    )
    assessment = tmp_path / "assess-features.py"
    assessment.write_text(_feature_assessment_adapter(), encoding="utf-8")
    whole_request = _whole_run_request(
        tmp_path / "whole-run.json", all_request, baseline, assessment
    )
    planner = tmp_path / "repair-planner.py"
    builder = tmp_path / "repair-builder.py"
    router = tmp_path / "repair-router.py"
    planner.write_text(_repair_planner_adapter(), encoding="utf-8")
    builder.write_text(_repair_builder_adapter(), encoding="utf-8")
    router.write_text(_repair_routing_adapter(), encoding="utf-8")
    request = tmp_path / "repair-run.json"
    _write_json(
        request,
        {
            "schema_version": 1,
            "whole_run": {"path": str(whole_request), "sha256": _digest(whole_request)},
            "repair_budget": 1,
            "probe_repairs": [
                {
                    "probe_id": "selector",
                    "allowed_paths": ["feature_b.py"],
                    "approach_ids": ["retain-current", "correct-selector"],
                }
            ],
            "planner": {
                "adapter": {"path": str(planner), "sha256": _digest(planner)},
                "command": [
                    "{python}",
                    "{planner-adapter}",
                    "{planner-request}",
                    "{planner-response}",
                ],
            },
            "builder": {
                "adapter": {"path": str(builder), "sha256": _digest(builder)},
                "command": [
                    "{python}",
                    "{builder-adapter}",
                    "{approach}",
                    "{candidate}",
                    "{builder-result}",
                ],
            },
            "routing": {
                "adapter": {"path": str(router), "sha256": _digest(router)},
                "command": [
                    "{python}",
                    "{routing-adapter}",
                    "{routing-question}",
                    "{routing-response}",
                ],
            },
        },
    )
    output = tmp_path / "repair-output"

    completed = _run_repair_process(request, output)

    assert completed.returncode == 0, completed.stderr
    terminal = json.loads(completed.stdout)
    assert terminal["status"] == "completed"
    assert terminal["terminal"] == "passed"
    assert terminal["rounds"] == 1
    assert terminal["promotion_applied"] is False
    initial = json.loads((output / "initial" / "final-verdict.json").read_text())
    assert initial["verdict"] == "failed"
    route = json.loads((output / "repairs" / "001" / "failure-route.json").read_text())
    assert route["route_kind"] == "probes"
    assert route["probe_ids"] == ["selector"]
    recommendation = json.loads(
        (output / "repairs" / "001" / "selector" / "experiment" / "recommendation.json").read_text()
    )
    assert recommendation["approach_id"] == "correct-selector"
    final = json.loads((output / "final-verdict.json").read_text())
    assert final["verdict"] == "passed"
    before = json.loads((output / "initial" / "probes" / "promotion-candidates.json").read_text())
    after = json.loads((output / "repairs" / "001" / "promotion-candidates.json").read_text())
    before_runner = next(item for item in before["candidates"] if item["probe_id"] == "runner")
    after_runner = next(item for item in after["candidates"] if item["probe_id"] == "runner")
    assert {key: value for key, value in after_runner.items() if key not in {"bundle", "recommendation"}} == {
        key: value for key, value in before_runner.items() if key not in {"bundle", "recommendation"}
    }
    assert after_runner["bundle_sha256"] == before_runner["bundle_sha256"]


def test_repair_plan_refuses_an_approach_that_can_change_an_unapproved_file() -> None:
    module = _repair_process_module()
    response = {
        "schema_version": 1,
        "approaches": [
            {
                "id": "retain-current",
                "hypothesis": "Retain the current behavior.",
                "instructions": "Keep the source unchanged.",
                "allowed_paths": ["feature_b.py"],
            },
            {
                "id": "correct-selector",
                "hypothesis": "Change both features.",
                "instructions": "Edit both modules.",
                "allowed_paths": ["feature_a.py"],
            },
        ],
    }
    contract = {
        "approach_ids": ["retain-current", "correct-selector"],
        "allowed_paths": ["feature_b.py"],
    }

    with pytest.raises(module.RepairError, match="feature_a.py"):
        module._validate_plan(response, contract)
