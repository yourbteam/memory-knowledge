from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "skills" / "experiment-machinery" / "scripts" / "run_experiment.py"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    adapter = tmp_path / "adapter.py"
    adapter.write_text(
        "import json, os\n"
        "from pathlib import Path\n"
        "ADAPTER_VALUE = 1\n"
        "variant = os.environ['EXPERIMENT_VARIANT_ID']\n"
        "metrics = {'adapter-value': ADAPTER_VALUE}\n"
        "Path(os.environ['EXPERIMENT_RESULT_PATH']).write_text(json.dumps({"
        "'schema_version': 1, 'variant_id': variant, 'status': 'completed', "
        "'outcome': {'value': ADAPTER_VALUE}, 'metrics': metrics, 'error': None}) + '\\\n')\n",
        encoding="utf-8",
    )
    frozen = tmp_path / "input.json"
    _write_json(frozen, {"case": "adapter-binding"})
    target = tmp_path / "target"
    target.mkdir()
    (target / "entry.txt").write_text("stable\n", encoding="utf-8")
    target_hash = subprocess.run(
        [sys.executable, str(RUNNER), "--hash-source", str(target)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    spec = {
        "schema_version": 2,
        "experiment_id": "test-adapter-binding",
        "hypothesis": "Changed adapter bytes refuse the frozen experiment.",
        "target": {
            "machinery": "experiment-machinery",
            "phase": "adapter-binding",
            "source": {"path": str(target), "sha256": target_hash},
            "entrypoint": "entry.txt",
        },
        "frozen_input": {"path": str(frozen), "sha256": _sha256(frozen)},
        "variants": [
            {
                "id": variant_id,
                "command": [sys.executable, str(adapter)],
                "adapter": {"path": str(adapter), "sha256": _sha256(adapter)},
                "configuration": {},
            }
            for variant_id in ("control", "variation")
        ],
        "evaluation": {
            "metrics": [{"name": "adapter-value", "direction": "maximize"}]
        },
    }
    spec_path = tmp_path / "experiment.json"
    _write_json(spec_path, spec)
    return spec_path, adapter


def _run(spec: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RUNNER), "--spec", str(spec), "--output", str(output)],
        capture_output=True,
        text=True,
    )


def test_adapter_bytes_are_bound_before_output_and_recorded(tmp_path: Path) -> None:
    spec, adapter = _fixture(tmp_path)
    first_output = tmp_path / "first"
    first = _run(spec, first_output)
    assert first.returncode == 0, first.stderr

    events = [
        json.loads(line)
        for line in (first_output / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    started = next(event for event in events if event["event"] == "experiment_started")
    variant_started = [event for event in events if event["event"] == "variant_started"]
    expected_hash = _sha256(adapter)
    assert {row["sha256"] for row in started["adapters"]} == {expected_hash}
    assert {event["adapter_sha256"] for event in variant_started} == {expected_hash}
    assert {event["adapter_snapshot_sha256"] for event in variant_started} == {expected_hash}

    adapter.write_text(
        adapter.read_text(encoding="utf-8").replace("ADAPTER_VALUE = 1", "ADAPTER_VALUE = 2"),
        encoding="utf-8",
    )
    changed_output = tmp_path / "changed"
    changed = _run(spec, changed_output)
    assert changed.returncode == 2
    assert "adapter changed" in changed.stderr
    assert not changed_output.exists()


def test_unbound_version_one_spec_is_refused(tmp_path: Path) -> None:
    spec_path, _ = _fixture(tmp_path)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    spec["schema_version"] = 1
    for variant in spec["variants"]:
        variant.pop("adapter")
    _write_json(spec_path, spec)

    output = tmp_path / "legacy"
    result = _run(spec_path, output)
    assert result.returncode == 2
    assert "expected 2" in result.stderr
    assert not output.exists()


def test_adapter_must_be_the_executed_operand_and_not_a_symlink(tmp_path: Path) -> None:
    spec_path, adapter = _fixture(tmp_path)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    decoy = tmp_path / "decoy.py"
    decoy.write_text("DECOY = True\n", encoding="utf-8")
    spec["variants"][1]["command"].append(str(decoy))
    spec["variants"][1]["adapter"] = {"path": str(decoy), "sha256": _sha256(decoy)}
    _write_json(spec_path, spec)

    decoy_result = _run(spec_path, tmp_path / "decoy-output")
    assert decoy_result.returncode == 2
    assert "command[1] launches" in decoy_result.stderr

    link = tmp_path / "adapter-link.py"
    link.symlink_to(adapter)
    spec["variants"][1]["command"] = [sys.executable, str(link)]
    spec["variants"][1]["adapter"] = {"path": str(link), "sha256": _sha256(adapter)}
    _write_json(spec_path, spec)

    link_result = _run(spec_path, tmp_path / "link-output")
    assert link_result.returncode == 2
    assert "must not be a symbolic link" in link_result.stderr


def test_development_probe_specs_bind_the_candidate_adapter() -> None:
    source = (
        ROOT
        / "skills"
        / "experiment-machinery"
        / "scripts"
        / "development_probe_experiment.py"
    ).read_text(encoding="utf-8")
    assert "EXPERIMENT_SPEC_CONTRACT = 2" in source
    assert '"adapter": {"path": str(candidate), "sha256": _digest(candidate.read_bytes())}' in source
