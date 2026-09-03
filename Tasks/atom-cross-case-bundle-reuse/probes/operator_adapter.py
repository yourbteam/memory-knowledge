#!/usr/bin/env python3
"""Exercise cross-case bundle reuse through Experiment Machinery's real CLIs."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "experiment-machinery" / "scripts"
CANDIDATE = SCRIPTS / "development_probe_candidate.py"
ALL_PROBES = SCRIPTS / "development_probe_all_probes.py"
RUNNER = SCRIPTS / "run_experiment.py"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(command: list[str], *, environment: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    active = dict(os.environ if environment is None else environment)
    active.pop("DEVELOPMENT_PROBE_TELEMETRY_PATH", None)
    return subprocess.run(command, cwd=ROOT, env=active, text=True, capture_output=True, check=False)


def normal_adapter(quality: int) -> str:
    return f'''from __future__ import annotations
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
variant = os.environ["EXPERIMENT_VARIANT_ID"]
source = Path(os.environ["EXPERIMENT_INPUT_PATH"])
result = Path(os.environ["EXPERIMENT_RESULT_PATH"])
telemetry = Path(os.environ["EXPERIMENT_TELEMETRY_PATH"])
event = {{"schema_version": 1, "sequence": 1, "event": "work_completed", "recorded_at": datetime.now(timezone.utc).isoformat(), "variant_id": variant, "message": "Executed the declared captured case.", "evidence_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "observations": {{"quality": {quality}}}}}
telemetry.write_text(json.dumps(event, sort_keys=True) + "\\n", encoding="utf-8")
result.write_text(json.dumps({{"schema_version": 1, "variant_id": variant, "status": "completed", "outcome": {{"quality": {quality}}}, "metrics": {{"quality": {quality}}}, "error": None}}, sort_keys=True) + "\\n", encoding="utf-8")
'''


def mutating_adapter() -> str:
    return '''from __future__ import annotations
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
entrypoint = Path(__file__)
entrypoint.chmod(0o644)
with entrypoint.open("a", encoding="utf-8") as stream:
    stream.write("# execution mutation\\n")
variant = os.environ["EXPERIMENT_VARIANT_ID"]
source = Path(os.environ["EXPERIMENT_INPUT_PATH"])
telemetry = Path(os.environ["EXPERIMENT_TELEMETRY_PATH"])
result = Path(os.environ["EXPERIMENT_RESULT_PATH"])
event = {"schema_version": 1, "sequence": 1, "event": "work_completed", "recorded_at": datetime.now(timezone.utc).isoformat(), "variant_id": variant, "message": "Mutated the execution-local source.", "evidence_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "observations": {"quality": 0}}
telemetry.write_text(json.dumps(event, sort_keys=True) + "\\n", encoding="utf-8")
result.write_text(json.dumps({"schema_version": 1, "variant_id": variant, "status": "completed", "outcome": {"quality": 0}, "metrics": {"quality": 0}, "error": None}, sort_keys=True) + "\\n", encoding="utf-8")
'''


def evaluator_source() -> str:
    return '''from __future__ import annotations
import json
import sys
from pathlib import Path
request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
scores = []
for candidate in request["candidates"]:
    telemetry = next(item["path"] for item in candidate["evidence"] if item["id"] == "telemetry")
    events = [json.loads(line) for line in Path(telemetry).read_text(encoding="utf-8").splitlines()]
    work = next(item for item in events if item.get("event") == "operator_work")
    scores.append({"variant_id": candidate["variant_id"], "metrics": {"quality": work["observations"]["quality"]}})
Path(sys.argv[2]).write_text(json.dumps({"schema_version": 1, "scores": scores}, sort_keys=True) + "\\n", encoding="utf-8")
'''


def operator_evaluator_source() -> str:
    return '''from __future__ import annotations
import json
import sys
from pathlib import Path
request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
scores = []
for candidate in request["candidates"]:
    telemetry = next(item["path"] for item in candidate["evidence"] if item["id"] == "telemetry")
    events = [json.loads(line) for line in Path(telemetry).read_text(encoding="utf-8").splitlines()]
    work = next(item for item in events if item.get("event") == "operator_work")
    observed = work["observations"]
    scores.append({"variant_id": candidate["variant_id"], "metrics": {"bundle-reuse": observed["bundle_reuse"], "execution-isolation": observed["execution_isolation"], "downstream-compatibility": observed["downstream_compatibility"]}})
Path(sys.argv[2]).write_text(json.dumps({"schema_version": 1, "scores": scores}, sort_keys=True) + "\\n", encoding="utf-8")
'''


def fixture_manifest(root: Path, case_files: list[tuple[str, Path]]) -> Path:
    captured = [
        {"id": case_id, "source_ref": source.relative_to(root).as_posix(), "sha256": digest(source), "kind": "success" if index == 0 else "failure", "expected_outcome": "The candidate completes without changing shared evidence."}
        for index, (case_id, source) in enumerate(case_files)
    ]
    manifest = {
        "schema_version": 2,
        "case_source_root": str(root),
        "atomic_step": {"id": "bundle-reuse-fixture", "outcome": "Reuse one bundle across cases.", "practical_value": "Candidate construction does not multiply with cases.", "stopping_condition": "Two bundles drive four executions.", "captured_cases": captured},
        "mini_probes": [{
            "id": "reuse",
            "goal": "Run each immutable approach across every case.",
            "practical_value": "One build identity is retained per approach.",
            "work_type": "code",
            "work_type_reason": "The boundary is deterministic.",
            "allowed_paths": ["adapter.py"],
            "inputs": [{"case_id": item[0]} for item in case_files],
            "approaches": [
                {"id": "control", "hypothesis": "The first implementation runs.", "implementation": "Use the first copied adapter.", "predicted_tradeoff": "Lower quality."},
                {"id": "variation", "hypothesis": "The second implementation runs.", "implementation": "Use the second copied adapter.", "predicted_tradeoff": "Higher quality."}
            ],
            "proof": {"success_criterion": "Every case execution completes.", "failure_criterion": "Changed evidence is refused."},
            "evaluation": {"metrics": [{"name": "quality", "direction": "maximize"}], "across_cases": [{"name": "quality", "method": "sum"}]},
            "winner_output": {"artifact": "reused-candidate", "description": "One verified bundle used by every case."}
        }],
        "composition": {"consumes": [{"probe_id": "reuse", "artifact": "reused-candidate"}], "assembly_contract": "Use the unchanged shared winner.", "final_validation": {"operator_path": "run the shared candidate", "case_ids": [item[0] for item in case_files], "success_criterion": "All case executions complete.", "failure_criterion": "Mutated evidence is refused."}}
    }
    target = root / "manifest.json"
    write_json(target, manifest)
    return target


def build_request(manifest: Path, baseline: Path, candidate: Path, approach: str) -> dict[str, object]:
    return {"schema_version": 1, "development_manifest": str(manifest), "probe_id": "reuse", "approach_id": approach, "source": {"baseline": str(baseline), "candidate": str(candidate), "entrypoint": "adapter.py"}, "execution": {"protocol": "experiment-result-v1", "command": ["{python}", "{candidate-entrypoint}"]}}


def build_amplification(root: Path, frozen_input: Path) -> dict[str, int]:
    fixture = root / "build-amplification"
    fixture.mkdir(parents=True)
    first = fixture / "case-a.json"
    second = fixture / "case-b.json"
    first.write_bytes(frozen_input.read_bytes())
    second.write_bytes((ROOT / "Tasks" / "atom-cross-case-bundle-reuse" / "captured" / "execution-mutation.json").read_bytes())
    manifest = fixture_manifest(fixture, [("case-a", first), ("case-b", second)])
    baseline = fixture / "baseline"
    control = fixture / "control"
    variation = fixture / "variation"
    for source, quality in ((baseline, 0), (control, 1), (variation, 2)):
        source.mkdir()
        (source / "adapter.py").write_text(normal_adapter(quality), encoding="utf-8")
    evaluator = fixture / "evaluator.py"
    evaluator.write_text(evaluator_source(), encoding="utf-8")
    builds = []
    for approach, source in (("control", control), ("variation", variation)):
        request = fixture / f"build-{approach}.json"
        write_json(request, build_request(manifest, baseline, source, approach))
        builds.append({"approach_id": approach, "request": str(request)})
    cross = fixture / "cross.json"
    write_json(cross, {"schema_version": 1, "development_manifest": str(manifest), "probe_id": "reuse", "approach_build_requests": builds, "evaluator": {"adapter": {"path": str(evaluator), "sha256": digest(evaluator)}, "command": ["{python}", "{evaluation-adapter}", "{evaluation-request}", "{evaluation-response}"]}})
    all_request = fixture / "all.json"
    write_json(all_request, {"schema_version": 1, "development_manifest": str(manifest), "probe_requests": [{"probe_id": "reuse", "request": str(cross)}]})
    output = fixture / "output"
    completed = run([sys.executable, str(ALL_PROBES), "run", str(all_request), str(output)])
    probe = output / "probes" / "reuse"
    bundles = sorted(probe.glob("bundles/*/bundle.json"))
    executions = sorted(probe.glob("cases/*/experiment/variants/*/result.json"))
    mappings: dict[str, list[tuple[Path, str]]] = {}
    for mapping_file in sorted(probe.glob("cases/*/variant-map.json")):
        mapping = json.loads(mapping_file.read_text(encoding="utf-8"))
        for item in mapping["variants"]:
            resolved = (mapping_file.parent / item["bundle"]).resolve()
            mappings.setdefault(item["approach_id"], []).append((resolved, item["bundle_sha256"]))
    shared = all(len({path for path, _ in rows}) == 1 and len({sha for _, sha in rows}) == 1 for rows in mappings.values())
    candidates = output / "promotion-candidates.json"
    return {
        "bundle_reuse": int(completed.returncode == 0 and len(bundles) == 2 and len(executions) == 4 and shared),
        "execution_isolation": int(completed.returncode == 0 and all(run([sys.executable, str(CANDIDATE), "verify", str(item.parent)]).returncode == 0 for item in bundles)),
        "downstream_compatibility": int(completed.returncode == 0 and candidates.is_file()),
    }


def execution_mutation(root: Path, frozen_input: Path) -> dict[str, int]:
    fixture = root / "execution-mutation"
    fixture.mkdir(parents=True)
    captured = fixture / "captured.json"
    captured.write_bytes(frozen_input.read_bytes())
    other = fixture / "other.json"
    other.write_bytes((ROOT / "Tasks" / "atom-cross-case-bundle-reuse" / "captured" / "build-amplification.json").read_bytes())
    manifest = fixture_manifest(fixture, [("execution-mutation", captured), ("other", other)])
    baseline = fixture / "baseline"
    normal = fixture / "normal"
    mutator = fixture / "mutator"
    for source, payload in ((baseline, normal_adapter(0)), (normal, normal_adapter(1)), (mutator, mutating_adapter())):
        source.mkdir()
        (source / "adapter.py").write_text(payload, encoding="utf-8")
    bundle_paths = {}
    for approach, source in (("control", normal), ("variation", mutator)):
        request = fixture / f"build-{approach}.json"
        write_json(request, build_request(manifest, baseline, source, approach))
        bundle = fixture / f"bundle-{approach}"
        built = run([sys.executable, str(CANDIDATE), "build", str(request), str(bundle)])
        if built.returncode != 0:
            return {"bundle_reuse": 0, "execution_isolation": 0, "downstream_compatibility": 0}
        bundle_paths[approach] = bundle
    mutator_digest = json.loads(run([sys.executable, str(CANDIDATE), "verify", str(bundle_paths["variation"])]).stdout)["bundle_sha256"]
    evaluator = fixture / "evaluator.py"
    evaluator.write_text(evaluator_source(), encoding="utf-8")
    hashed = run([sys.executable, str(RUNNER), "--hash-source", str(SCRIPTS)])
    spec = {
        "schema_version": 4,
        "experiment_id": "shared-bundle-mutation-boundary",
        "hypothesis": "A mutating execution is ineligible without changing its shared bundle.",
        "target": {"machinery": "experiment-machinery", "phase": "development-probe-candidate", "source": {"path": str(SCRIPTS), "sha256": hashed.stdout.strip()}, "entrypoint": CANDIDATE.name},
        "frozen_input": {"path": str(frozen_input), "sha256": digest(frozen_input)},
        "execution_limits": {"variant_timeout_ms": 60000, "evaluator_timeout_ms": 60000},
        "variants": [
            {"id": "control", "command": [sys.executable, str(CANDIDATE), "execute", str(bundle_paths["control"])], "adapter": {"path": str(CANDIDATE), "sha256": digest(CANDIDATE)}, "configuration": {"case_id": "execution-mutation"}},
            {"id": "variation-2", "command": [sys.executable, str(CANDIDATE), "execute", str(bundle_paths["variation"])], "adapter": {"path": str(CANDIDATE), "sha256": digest(CANDIDATE)}, "configuration": {"case_id": "execution-mutation"}}
        ],
        "evaluation": {"metrics": [{"name": "quality", "direction": "maximize"}], "evaluator": {"adapter": {"path": str(evaluator), "sha256": digest(evaluator)}, "command": ["{python}", "{evaluation-adapter}", "{evaluation-request}", "{evaluation-response}"]}}
    }
    spec_path = fixture / "experiment.json"
    write_json(spec_path, spec)
    experiment = fixture / "experiment"
    run([sys.executable, str(RUNNER), "--spec", str(spec_path), "--output", str(experiment)])
    summary = json.loads((experiment / "summary.json").read_text(encoding="utf-8"))
    mutated = next(item for item in summary["variants"] if item["variant_id"] == "variation-2")
    verified = run([sys.executable, str(CANDIDATE), "verify", str(bundle_paths["variation"])])
    intact = verified.returncode == 0 and json.loads(verified.stdout)["bundle_sha256"] == mutator_digest
    leftover = any(path.name == "candidate-source" for path in experiment.rglob("candidate-source"))
    return {"bundle_reuse": 1, "execution_isolation": int(mutated["eligible"] is False and intact and not leftover), "downstream_compatibility": int(intact)}


def main() -> int:
    case = json.loads(Path(os.environ["EXPERIMENT_INPUT_PATH"]).read_text(encoding="utf-8"))
    case_id = case["case_id"]
    work = Path(os.environ["EXPERIMENT_WORK_DIR"]) / "operator"
    work.mkdir()
    frozen = Path(os.environ["EXPERIMENT_INPUT_PATH"])
    observed = build_amplification(work, frozen) if case_id == "build-amplification" else execution_mutation(work, frozen)
    event = {"schema_version": 1, "sequence": int(os.environ.get("EXPERIMENT_TELEMETRY_SEQUENCE_START", "1")), "event": "work_completed", "recorded_at": datetime.now(timezone.utc).isoformat(), "variant_id": os.environ["EXPERIMENT_VARIANT_ID"], "message": "Exercised the real bundle reuse and isolation boundary.", "evidence_sha256": digest(frozen), "observations": observed}
    Path(os.environ["EXPERIMENT_TELEMETRY_PATH"]).write_text(json.dumps(event, sort_keys=True) + "\n", encoding="utf-8")
    result = {"schema_version": 1, "variant_id": os.environ["EXPERIMENT_VARIANT_ID"], "status": "completed", "outcome": observed, "metrics": {"bundle-reuse": observed["bundle_reuse"], "execution-isolation": observed["execution_isolation"], "downstream-compatibility": observed["downstream_compatibility"]}, "error": None}
    Path(os.environ["EXPERIMENT_RESULT_PATH"]).write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
